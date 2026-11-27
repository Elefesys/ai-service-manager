"""Freeze accepted prepayment terms after an authorized opening of a live hold."""

import hashlib
import re

from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None

THIS_PROFILE = "platform.payment_obligation_schema_profile()"
OWNER = "platform.payment_obligation_owner(jsonb,uuid,text)"
ROUND = "platform.percent_prepayment_minor(bigint,integer)"
QUOTE_BASIS = "platform.quote_basis(app.service_requests,timestamptz)"
QUOTE_AUTHORITY = "platform.quote_authority(app.quotes,app.conversations,bigint)"
QUOTE_OPEN_AT = "platform.quote_open_at(app.quotes,timestamptz)"
QUOTE_PREPARE = "platform.quote_prepare_scoped(app.service_requests)"
QUOTE_RECORD = "platform.quote_record_scoped(app.service_requests,uuid,uuid,boolean,jsonb)"
PREVIOUS_NONFUNCTION = "6cf7f7e07901adba39b00776e99cd89f0583611717fa69e6bb622a08777bac4a"
NONFUNCTION = "47979fec991896acf7e6eff01631b2007143a8b14add0aee2f921827bba468c7"

# These keys bind each edge of the accepted quote, order and session.
REFERENCE_KEYS = (
    (
        "app.quotes",
        "payment_quote_ref",
        "workspace_id,business_id,id,version,terms_sha256,release_id",
    ),
    ("app.quote_acceptances", "payment_acceptance_ref", "workspace_id,id,quote_id"),
    ("app.service_orders", "payment_order_ref", "workspace_id,id,acceptance_id"),
    ("app.service_sessions", "payment_session_ref", "workspace_id,id,order_id"),
)

TABLES = {
    "app.payment_obligations": r"""CREATE TABLE app.payment_obligations (
      workspace_id uuid NOT NULL,
      business_id uuid NOT NULL,
      id uuid NOT NULL DEFAULT uuidv7(),
      quote_id uuid NOT NULL,
      quote_version bigint NOT NULL,
      terms_sha256 text NOT NULL,
      deposit_terms_version uuid NOT NULL,
      acceptance_id uuid NOT NULL,
      order_id uuid NOT NULL,
      session_id uuid NOT NULL,
      currency text NOT NULL CHECK(currency='RUB'),
      price_minor bigint CHECK(price_minor BETWEEN 1 AND 100000000000),
      price_lower_minor bigint CHECK(price_lower_minor BETWEEN 1 AND 100000000000),
      price_upper_minor bigint CHECK(price_upper_minor BETWEEN 1 AND 100000000000),
      mode text NOT NULL CHECK(mode IN ('FIXED_DEPOSIT','PERCENT_DEPOSIT','FULL_PREPAYMENT')),
      amount_minor bigint NOT NULL CHECK(amount_minor BETWEEN 1 AND 100000000000),
      percent integer CHECK(percent BETWEEN 1 AND 100),
      rounding_version text CHECK(rounding_version='HALF_UP_V1'),
      created_at timestamptz NOT NULL CHECK(isfinite(created_at)),
      PRIMARY KEY(workspace_id,business_id,id),
      UNIQUE(workspace_id,session_id,terms_sha256),
      FOREIGN KEY(workspace_id,business_id,quote_id,quote_version,terms_sha256,deposit_terms_version)
        REFERENCES app.quotes(workspace_id,business_id,id,version,terms_sha256,release_id),
      FOREIGN KEY(workspace_id,acceptance_id,quote_id)
        REFERENCES app.quote_acceptances(workspace_id,id,quote_id),
      FOREIGN KEY(workspace_id,order_id,acceptance_id)
        REFERENCES app.service_orders(workspace_id,id,acceptance_id),
      FOREIGN KEY(workspace_id,session_id,order_id)
        REFERENCES app.service_sessions(workspace_id,id,order_id),
      CHECK((price_lower_minor IS NULL)=(price_upper_minor IS NULL)),
      CHECK((price_minor IS NULL)<>(price_lower_minor IS NULL)),
      CHECK(price_lower_minor IS NULL OR (price_lower_minor<price_upper_minor AND mode='FIXED_DEPOSIT')),
      CHECK((mode='PERCENT_DEPOSIT')=(percent IS NOT NULL)),
      CHECK(rounding_version IS NULL OR mode='PERCENT_DEPOSIT'),
      CHECK(mode<>'FULL_PREPAYMENT' OR amount_minor=price_minor)
    )""",
    "platform.payment_obligation_receipts": r"""CREATE TABLE platform.payment_obligation_receipts (
      workspace_id uuid NOT NULL,
      business_id uuid NOT NULL,
      actor_id uuid NOT NULL,
      command_key text NOT NULL CHECK(command_key ~ '^[A-Za-z0-9._:-]{1,128}$'),
      hold_id uuid NOT NULL,
      obligation_id uuid NOT NULL,
      PRIMARY KEY(workspace_id,actor_id,command_key),
      FOREIGN KEY(workspace_id,actor_id) REFERENCES platform.workspace_memberships(workspace_id,user_account_id),
      FOREIGN KEY(workspace_id,business_id,hold_id) REFERENCES app.reservation_holds(workspace_id,business_id,id),
      FOREIGN KEY(workspace_id,business_id,obligation_id) REFERENCES app.payment_obligations(workspace_id,business_id,id)
    )""",
}

FUNCTIONS = {
    ROUND: r"""CREATE FUNCTION platform.percent_prepayment_minor(p_price bigint,p_percent integer)
    RETURNS bigint LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $$
      SELECT (p_price*p_percent+50)/100
    $$""",
    OWNER: r"""CREATE FUNCTION platform.payment_obligation_owner(
      p_selection jsonb,p_hold uuid,p_key text
    ) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    DECLARE
      business uuid:=(p_selection->>'business_id')::uuid;
      session uuid:=(p_selection->>'session_id')::uuid;
      target_order uuid:=(p_selection->>'order_id')::uuid;
      actor uuid:=nullif(current_setting('asm.actor_id',true),'')::uuid;
      ws uuid:=platform.scheduling_owner_scope(business,'schedule');
      q app.quotes%ROWTYPE:=platform.scheduling_agreement(ws,p_selection);
      resource uuid; allocation uuid; acceptance uuid; deadline timestamptz; moment timestamptz;
      hold_status text; mode text:=q.material->'deposit'->>'mode';
      price bigint; price_lower bigint; price_upper bigint; payable bigint;
      percent integer; rounding text; prior platform.payment_obligation_receipts%ROWTYPE;
      obligation app.payment_obligations%ROWTYPE;
    BEGIN
      IF q.basis_sha256 IS DISTINCT FROM platform.quote_hash(q.material)
        OR q.terms_sha256 IS DISTINCT FROM platform.quote_hash(jsonb_build_array(
          'quote_v1',q.id,q.version,q.code,platform.quote_timestamp(q.expires_at),q.material,q.text))
        OR (q.material->>'deposit_terms_version')::uuid IS DISTINCT FROM q.release_id
        OR NOT EXISTS(SELECT 1 FROM app.service_requests d
          WHERE (d.workspace_id,d.id,d.business_id,d.conversation_id,d.client_id)
            =(ws,q.request_id,business,q.conversation_id,q.client_id))
        THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P3101'; END IF;

      IF p_key IS NOT NULL THEN
        IF p_key !~ '^[A-Za-z0-9._:-]{1,128}$'
          THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P3101'; END IF;
        -- Serialize the actor's key even if a repeat points to another business.
        PERFORM pg_advisory_xact_lock(hashtextextended(ws::text||':'||actor::text||':'||p_key,2038));
        -- M7 takes this same resource lock before changing its allocations.
        SELECT r.id INTO resource FROM app.scheduling_resources r
          WHERE (r.workspace_id,r.business_id)=(ws,business) FOR UPDATE;
      END IF;
      moment:=clock_timestamp();
      SELECT h.expires_at,a.id,
        CASE WHEN a.kind='APPOINTMENT' THEN
          CASE WHEN a.released_at IS NULL THEN 'CONFIRMED' ELSE 'RELEASED' END
        WHEN a.release_reason IS NOT NULL THEN a.release_reason
        WHEN h.expires_at<=moment THEN 'EXPIRED' ELSE 'HELD' END
      INTO deadline,allocation,hold_status
      FROM app.reservation_holds h
      JOIN app.resource_allocations a
        ON (a.workspace_id,a.business_id,a.resource_id,a.id,a.session_id)
          =(h.workspace_id,h.business_id,h.resource_id,h.allocation_id,h.session_id)
      JOIN app.availability_options opt
        ON (opt.workspace_id,opt.business_id,opt.id)=(h.workspace_id,h.business_id,h.option_id)
      JOIN app.availability_offers f
        ON (f.workspace_id,f.business_id,f.id,f.resource_id,f.session_id)
          =(opt.workspace_id,opt.business_id,opt.offer_id,h.resource_id,h.session_id)
      WHERE (h.workspace_id,h.business_id,h.id,h.session_id)=(ws,business,p_hold,session)
        AND (p_key IS NULL OR h.resource_id=resource)
        AND (f.client_id,f.conversation_id,f.request_id,f.quote_id,f.order_id,f.terms_sha256,f.service_id)
          =(q.client_id,q.conversation_id,q.request_id,q.id,target_order,q.terms_sha256,q.material->>'service_id')
        AND f.deposit=q.material->'deposit'
        AND a.occupied=tstzrange(opt.busy_start,opt.busy_end,'[)')
        AND a.kind IN ('HOLD','APPOINTMENT');
      IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P3101'; END IF;

      IF p_key IS NOT NULL THEN
        SELECT * INTO prior FROM platform.payment_obligation_receipts r
          WHERE (r.workspace_id,r.actor_id,r.command_key)=(ws,actor,p_key);
        IF FOUND AND (prior.business_id,prior.hold_id) IS DISTINCT FROM (business,p_hold)
          THEN RAISE EXCEPTION 'IDEMPOTENCY_KEY_CONFLICT' USING ERRCODE='P3101'; END IF;
      END IF;

      SELECT * INTO obligation FROM app.payment_obligations payment
        WHERE (payment.workspace_id,payment.business_id,payment.session_id,payment.terms_sha256)
          =(ws,business,session,q.terms_sha256);
      IF p_key IS NOT NULL AND mode<>'NONE' THEN
        -- An obligation is shared by the session, while a successful opening is specific to a Hold.
        IF hold_status<>'HELD' AND NOT EXISTS(
          SELECT 1 FROM platform.payment_obligation_receipts r
          WHERE (r.workspace_id,r.business_id,r.hold_id,r.obligation_id)=(ws,business,p_hold,obligation.id)
        ) THEN RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P3101'; END IF;
        IF obligation.id IS NULL THEN
          price:=(q.material->>'amount_minor')::bigint;
          price_lower:=(q.material->'price_range'->>'lower_minor')::bigint;
          price_upper:=(q.material->'price_range'->>'upper_minor')::bigint;
          CASE mode
            WHEN 'FIXED_DEPOSIT' THEN payable:=(q.material->'deposit'->>'amount_minor')::bigint;
            WHEN 'FULL_PREPAYMENT' THEN payable:=price;
            WHEN 'PERCENT_DEPOSIT' THEN
              percent:=(q.material->'deposit'->>'percent')::integer;
              IF q.material ? 'percent_prepayment' THEN
                rounding:=q.material->'percent_prepayment'->>'rounding_version';
                payable:=(q.material->'percent_prepayment'->>'amount_minor')::bigint;
                IF rounding IS DISTINCT FROM 'HALF_UP_V1'
                  OR payable IS DISTINCT FROM platform.percent_prepayment_minor(price,percent)
                  THEN RAISE EXCEPTION 'NEEDS_CLARIFICATION' USING ERRCODE='P3101'; END IF;
              ELSIF (price*percent)%100=0 THEN
                payable:=price*percent/100;
              END IF;
            ELSE NULL;
          END CASE;
          IF payable IS NULL OR payable<1 OR q.material->>'currency' IS DISTINCT FROM 'RUB'
            THEN RAISE EXCEPTION 'NEEDS_CLARIFICATION' USING ERRCODE='P3101'; END IF;
          SELECT qa.id INTO STRICT acceptance FROM app.quote_acceptances qa
            WHERE (qa.workspace_id,qa.quote_id)=(ws,q.id);
          INSERT INTO app.payment_obligations(workspace_id,business_id,quote_id,quote_version,terms_sha256,
            deposit_terms_version,acceptance_id,order_id,session_id,currency,price_minor,price_lower_minor,
            price_upper_minor,mode,amount_minor,percent,rounding_version,created_at)
          VALUES(ws,business,q.id,q.version,q.terms_sha256,q.release_id,acceptance,target_order,session,
            'RUB',price,price_lower,price_upper,mode,payable,percent,rounding,moment)
          RETURNING * INTO obligation;
        END IF;
        IF prior.command_key IS NULL THEN
          INSERT INTO platform.payment_obligation_receipts(workspace_id,business_id,actor_id,command_key,
            hold_id,obligation_id) VALUES(ws,business,actor,p_key,p_hold,obligation.id);
        END IF;
      END IF;

      RETURN jsonb_build_object('hold_id',p_hold,'allocation_id',allocation,
        'expires_at',platform.quote_timestamp(deadline),'hold_status',hold_status,
        'requires_prepayment',mode<>'NONE',
        'obligation',CASE WHEN obligation.id IS NOT NULL THEN jsonb_build_object(
          'id',obligation.id,'status','UNPAID','quote_version',obligation.quote_version::text,
          'terms_sha256',obligation.terms_sha256,'deposit_terms_version',obligation.deposit_terms_version,
          'acceptance_id',obligation.acceptance_id,'currency',obligation.currency,'price_minor',obligation.price_minor,
          'price_range',CASE WHEN obligation.price_lower_minor IS NOT NULL THEN jsonb_build_object(
            'authority','PROVISIONAL','lower_minor',obligation.price_lower_minor,'upper_minor',obligation.price_upper_minor
          ) END,'mode',obligation.mode,'amount_minor',obligation.amount_minor,'percent',obligation.percent,
          'rounding_version',obligation.rounding_version) END);
    END $$""",
}


def quote_basis_sql(original):
    # Only new percent quotes gain the calculated terms. Existing quote rows,
    # hashes and acceptance evidence are kept byte-for-byte.
    return (
        original.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
        .replace(
            "price_outcome text; mode text; conditions jsonb;",
            "price_outcome text; mode text; conditions jsonb; payable bigint; prepayment jsonb:='{}';",
        )
        .replace(
            "      SELECT coalesce(jsonb_agg(rule.value",
            """      IF b->'deposit'->>'mode'='PERCENT_DEPOSIT' THEN
        payable:=platform.percent_prepayment_minor(amount,(b->'deposit'->>'percent')::integer);
        IF payable IS NULL OR payable<1
          THEN RETURN jsonb_build_object('reason','DEPOSIT_TERMS_UNCLEAR'); END IF;
        prepayment:=jsonb_build_object('percent_prepayment',jsonb_build_object(
          'amount_minor',payable,'rounding_version','HALF_UP_V1'));
      END IF;
      SELECT coalesce(jsonb_agg(rule.value""",
        )
        .replace(
            "'duration_reference_id',duration_reference));",
            "'duration_reference_id',duration_reference)||prepayment);",
        )
    )


def exact_percent_minor_sql(material):
    price = f"({material}->>'amount_minor')::bigint"
    percent = f"({material}->'deposit'->>'percent')::integer"
    return f"({price}*{percent})%100=0"


def quote_material_matches_sql(moment):
    # A historical offer can omit the rounded amount only if the original
    # price and percentage determine an exact number of kopecks.
    return f"""EXISTS(
          WITH basis AS MATERIALIZED (SELECT platform.quote_basis(d,{moment})->'material' AS material)
          SELECT 1 FROM basis WHERE q.material=basis.material OR (
            basis.material ? 'percent_prepayment'
            AND q.material=basis.material-'percent_prepayment'
            AND q.material->'deposit'->>'mode'='PERCENT_DEPOSIT'
            AND {exact_percent_minor_sql("q.material")}
          ))"""


def legacy_quote_replay_sql(material):
    # Match the immutable snapshot through the existing unique key. Delivery
    # and client decisions are checked by the respective commands.
    return f"""
      IF NOT FOUND AND {material} ? 'percent_prepayment' AND {exact_percent_minor_sql(material)} THEN
        DECLARE legacy_material jsonb:={material}-'percent_prepayment';
        BEGIN
          SELECT saved.* INTO q FROM app.quotes saved
            WHERE (saved.workspace_id,saved.request_id,saved.basis_sha256)
              =(d.workspace_id,d.id,platform.quote_hash(legacy_material))
              AND saved.material=legacy_material;
        END;
      END IF;"""


def quote_changes(originals):
    authority = "q.material IS DISTINCT FROM platform.quote_basis(d,clock_timestamp())->'material'"
    open_at = "q.material=platform.quote_basis(d,moment)->'material'"
    prepare_lookup = """      SELECT * INTO q FROM app.quotes WHERE (workspace_id,request_id,basis_sha256)
        =(d.workspace_id,d.id,platform.quote_hash(current_material));"""
    record_lookup = """      basis:=platform.quote_hash(material);
      SELECT * INTO q FROM app.quotes WHERE (workspace_id,request_id,basis_sha256)=(d.workspace_id,d.id,basis);"""
    record_guard = """      IF material IS DISTINCT FROM p_payload->'material'
        THEN RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P3101'; END IF;"""
    assert (
        originals[QUOTE_AUTHORITY].count(authority) == originals[QUOTE_OPEN_AT].count(open_at) == 1
    )
    assert originals[QUOTE_PREPARE].count(prepare_lookup) == 1
    assert originals[QUOTE_RECORD].count(record_guard + "\n" + record_lookup) == 1
    return {
        QUOTE_BASIS: quote_basis_sql(originals[QUOTE_BASIS]),
        QUOTE_AUTHORITY: originals[QUOTE_AUTHORITY]
        .replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
        .replace(authority, "NOT " + quote_material_matches_sql("clock_timestamp()"), 1),
        QUOTE_OPEN_AT: originals[QUOTE_OPEN_AT]
        .replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
        .replace(open_at, quote_material_matches_sql("moment"), 1),
        QUOTE_PREPARE: originals[QUOTE_PREPARE]
        .replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
        .replace(prepare_lookup, prepare_lookup + legacy_quote_replay_sql("current_material"), 1)
        .replace(
            "'material',current_material", "'material',coalesce(q.material,current_material)", 1
        ),
        QUOTE_RECORD: originals[QUOTE_RECORD]
        .replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
        .replace(
            record_guard + "\n" + record_lookup,
            record_lookup
            + legacy_quote_replay_sql("material")
            + "\n"
            + record_guard.replace("IF material ", "IF coalesce(q.material,material) ", 1),
            1,
        ),
    }


def dependencies():
    scripts = op.get_context().script
    if scripts is None:
        from pathlib import Path

        from alembic.script import ScriptDirectory

        scripts = ScriptDirectory(str(Path(__file__).resolve().parents[1]))
    delivery = scripts.get_revision("0029").module
    acceptance = scripts.get_revision("0030").module
    intents = scripts.get_revision("0031").module
    scheduling = scripts.get_revision(down_revision).module
    scoped_quotes = {
        name: body
        for name, body, _ in intents._agent_shared_bodies()
        if name in {QUOTE_PREPARE, QUOTE_RECORD}
    }
    return {
        QUOTE_BASIS: delivery.FUNCTIONS[QUOTE_BASIS],
        QUOTE_AUTHORITY: acceptance.FUNCTIONS[QUOTE_AUTHORITY],
        QUOTE_OPEN_AT: acceptance.FUNCTIONS[QUOTE_OPEN_AT],
        **scoped_quotes,
    }, scheduling


def schema_sql(scheduling, quotes):
    owner_day, reschedule, appointments, holds, availability, intents, portfolio = (
        scheduling.dependencies()
    )
    previous_callers = holds.callers_sql(availability, scheduling.THIS_PROFILE, "'0037'")
    conversation = scheduling.conversation_functions(intents, portfolio)
    _, scoped = scheduling.scoped_functions(reschedule, appointments, holds, availability)
    previous_profile = scheduling.profile_sql(
        owner_day,
        reschedule,
        holds,
        availability,
        conversation | scoped | scheduling.FUNCTIONS,
        previous_callers,
    )
    callers = holds.callers_sql(availability, THIS_PROFILE, "'0038'")
    changes = (
        FUNCTIONS
        | quotes
        | {scheduling.THIS_PROFILE: previous_profile}
        | dict(zip(holds.PROFILE_CALLERS, callers, strict=True))
    )
    profile = previous_profile.replace(scheduling.THIS_PROFILE, THIS_PROFILE)
    additions = []
    for signature, sql in changes.items():
        header, body, _ = sql.split("$$")
        profile = re.sub(r"\('" + re.escape(signature) + r"',[^\n]+\),\n", "", profile)
        language = "plpgsql" if "LANGUAGE plpgsql" in header else "sql"
        volatility = "s" if " STABLE " in header else "i" if " IMMUTABLE " in header else "v"
        definer = str("SECURITY DEFINER" in header).lower()
        execute = str(signature == OWNER or signature in holds.PROFILE_CALLERS).lower()
        if signature in holds.PROFILE_CALLERS:
            previous = re.search(r"\('" + re.escape(signature) + r"',[^\n]+\)", previous_profile)
            assert previous is not None
            execute = previous.group().rsplit(",", 1)[-1].rstrip(")")
        digest = hashlib.sha256(body.encode()).hexdigest()
        additions.append(
            f"('{signature}','{digest}','{language}',{definer},'{volatility}',{execute})"
        )
    columns = []
    for table, sql in TABLES.items():
        names = re.findall(
            r"^      ([a-z_0-9]+) (?:uuid|text|bigint|integer|timestamptz)\b", sql, re.M
        )
        columns.append(f"('{table}',ARRAY[{','.join(repr(name) for name in names)}]::text[])")
    profile = (
        profile.replace(" AS (VALUES ", " AS (VALUES " + ",\n".join(additions) + ",\n", 1)
        .replace(
            "columns_expected(table_name,column_names) AS (VALUES ",
            "columns_expected(table_name,column_names) AS (VALUES " + ",\n".join(columns) + ",\n",
        )
        .replace("FROM functions)=453", "FROM functions)=456")
        .replace("FROM expected)=452", "FROM expected)=455")
        .replace("FROM tables)=99", "FROM tables)=101")
        .replace("FROM columns_expected)=99", "FROM columns_expected)=101")
        .replace(
            "AND NOT EXISTS(SELECT 1 FROM tables WHERE name IN (",
            "AND NOT EXISTS(SELECT 1 FROM tables WHERE name IN ("
            "'app.payment_obligations','platform.payment_obligation_receipts',",
        )
        .replace("'0037'", "'0038'")
        .replace(PREVIOUS_NONFUNCTION, NONFUNCTION)
    )
    return profile, callers, previous_callers


def upgrade():
    originals, scheduling = dependencies()
    for relation, name, columns in REFERENCE_KEYS:
        op.execute(f"ALTER TABLE {relation} ADD CONSTRAINT {name} UNIQUE ({columns})")
    for table, sql in TABLES.items():
        op.execute(sql)
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY payment_migrator ON {table} TO asm_migrator USING(true) WITH CHECK(true)"
        )
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC,asm_runtime")
        op.execute(f"""CREATE TRIGGER payment_fact_immutable BEFORE UPDATE OR DELETE ON {table}
          FOR EACH ROW EXECUTE FUNCTION platform.scheduling_fact_immutable()""")
    for signature, sql in FUNCTIONS.items():
        op.execute(sql)
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC,asm_runtime")
    op.execute(f"GRANT EXECUTE ON FUNCTION {OWNER} TO asm_runtime")
    quotes = quote_changes(originals)
    for sql in quotes.values():
        op.execute(sql)
    profile, callers, _ = schema_sql(scheduling, quotes)
    for sql in callers:
        op.execute(sql)
    op.execute(profile)
    op.execute(f"REVOKE ALL ON FUNCTION {THIS_PROFILE} FROM PUBLIC,asm_runtime")


def downgrade():
    originals, scheduling = dependencies()
    op.execute("LOCK TABLE app.payment_obligations,app.quotes IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM app.payment_obligations)
        OR EXISTS(SELECT 1 FROM app.quotes WHERE material ? 'percent_prepayment')
        THEN RAISE EXCEPTION 'PAYMENT_OBLIGATION_DURABLE_DATA' USING ERRCODE='55000'; END IF;
      END $$""")
    _, _, previous_callers = schema_sql(scheduling, quote_changes(originals))
    for sql in previous_callers:
        op.execute(sql)
    op.execute(f"DROP FUNCTION {THIS_PROFILE}")
    for sql in originals.values():
        op.execute(sql.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1))
    for signature in reversed(FUNCTIONS):
        op.execute(f"DROP FUNCTION {signature}")
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE {table}")
    for relation, name, _ in reversed(REFERENCE_KEYS):
        op.execute(f"ALTER TABLE {relation} DROP CONSTRAINT {name}")
