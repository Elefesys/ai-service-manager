"""Confirm a selected session without prepayment and preserve its allocation."""

import hashlib
import re

from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None

PREVIOUS_PROFILE = "platform.scheduling_hold_schema_profile()"
THIS_PROFILE = "platform.scheduling_appointment_schema_profile()"
NONFUNCTION_SHA256 = "a4f5ebec5251129b25a4ecd7cb9de3cfd8ba00135d5f37628f44b4209d3fc2db"
APPOINTMENTS = "app.appointments"
ACTIVE_ALLOCATIONS = "platform.scheduling_active_allocations(uuid,uuid,uuid,timestamptz)"
EXPIRE_HOLDS = "platform.scheduling_expire_holds(uuid,uuid,uuid,tstzrange,uuid,timestamptz)"
CALENDAR_PROTECTED = "platform.scheduling_calendar_protected()"
HOLD_VIEW = "platform.scheduling_hold_view(app.reservation_holds,timestamptz)"
CLIENT_COMMAND = "platform.scheduling_client_command(jsonb,uuid,uuid,text,uuid,text,boolean,jsonb)"
OWNER_BLOCK = "platform.scheduling_owner_block(uuid,text,timestamptz,timestamptz,uuid)"
OWNER_BOOKING = "platform.scheduling_owner_booking(jsonb)"
APPOINTMENT_VIEW = "platform.scheduling_appointment_view(app.appointments)"
COMPLETE_CHOICE = (
    "platform.scheduling_complete_choice(app.reservation_holds,app.quotes,timestamptz)"
)

TABLE_SQL = r"""CREATE TABLE app.appointments (
      workspace_id uuid NOT NULL, business_id uuid NOT NULL, resource_id uuid NOT NULL,
      id uuid NOT NULL DEFAULT uuidv7(),
      hold_id uuid NOT NULL, session_id uuid NOT NULL, allocation_id uuid NOT NULL,
      status text NOT NULL CHECK(status='CONFIRMED'),
      visit_start timestamptz NOT NULL CHECK(isfinite(visit_start)),
      visit_end timestamptz NOT NULL CHECK(isfinite(visit_end) AND visit_end>visit_start),
      timezone text NOT NULL,
      confirmed_at timestamptz NOT NULL CHECK(isfinite(confirmed_at) AND confirmed_at<=visit_start),
      PRIMARY KEY(workspace_id,business_id,id),
      UNIQUE(workspace_id,business_id,hold_id),
      UNIQUE(workspace_id,business_id,allocation_id),
      FOREIGN KEY(workspace_id,business_id,resource_id,hold_id,session_id,allocation_id)
        REFERENCES app.reservation_holds(workspace_id,business_id,resource_id,id,session_id,allocation_id)
    )"""

FUNCTIONS = {
    APPOINTMENT_VIEW: r"""CREATE FUNCTION platform.scheduling_appointment_view(
      a app.appointments
    ) RETURNS jsonb LANGUAGE sql STABLE SET search_path=pg_catalog,pg_temp AS $$
      SELECT jsonb_build_object('outcome',a.status,'appointment_id',a.id,'hold_id',a.hold_id,
        'allocation_id',a.allocation_id,'session_id',a.session_id,
        'visit_start',a.visit_start,'visit_end',a.visit_end,'timezone',a.timezone)
    $$""",
    COMPLETE_CHOICE: r"""CREATE FUNCTION platform.scheduling_complete_choice(
      h app.reservation_holds,q app.quotes,moment timestamptz
    ) RETURNS jsonb LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
    DECLARE booking app.appointments%ROWTYPE; offered app.availability_offers%ROWTYPE;
      slot app.availability_options%ROWTYPE; response jsonb;
    BEGIN
      -- The caller already locked the resource. An appointment stays
      -- authoritative after the expiration time of the originating hold.
      SELECT p.* INTO booking FROM app.appointments p
        WHERE (p.workspace_id,p.business_id,p.hold_id)=(h.workspace_id,h.business_id,h.id);
      IF FOUND THEN RETURN platform.scheduling_appointment_view(booking); END IF;
      response:=platform.scheduling_hold_view(h,moment);
      IF response->>'outcome' IS DISTINCT FROM 'HELD'
        OR q.material->'deposit'->>'mode' IS DISTINCT FROM 'NONE' THEN RETURN response; END IF;

      SELECT o.* INTO STRICT slot FROM app.availability_options o
        WHERE (o.workspace_id,o.business_id,o.id)=(h.workspace_id,h.business_id,h.option_id);
      SELECT f.* INTO STRICT offered FROM app.availability_offers f
        WHERE (f.workspace_id,f.business_id,f.id)=(slot.workspace_id,slot.business_id,slot.offer_id);
      IF (offered.resource_id,offered.session_id,offered.client_id,offered.conversation_id,
          offered.request_id,offered.quote_id,offered.terms_sha256)
        IS DISTINCT FROM (h.resource_id,h.session_id,q.client_id,q.conversation_id,q.request_id,q.id,q.terms_sha256)
        OR q.material->'deposit' IS DISTINCT FROM offered.deposit
        OR offered.deposit IS DISTINCT FROM jsonb_build_object('mode','NONE','amount_minor',NULL,'percent',NULL)
        OR q.material->>'deposit_terms_version' IS DISTINCT FROM q.release_id::text
        OR (q.material->>'occupied_minutes',q.material->>'duration_reference_id')
          IS DISTINCT FROM (offered.occupied_minutes::text,offered.duration_reference_id::text)
        OR NOT (
          offered.duration_reference_id::text IS NOT DISTINCT FROM q.material->>'assessment_id'
          OR offered.duration_reference_id::text IS NOT DISTINCT FROM q.material->>'decision_id'
        )
        OR slot.visit_end IS DISTINCT FROM slot.visit_start+make_interval(mins=>offered.occupied_minutes)
        OR slot.busy_start<moment
        THEN RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P3101'; END IF;

      UPDATE app.resource_allocations a SET kind='APPOINTMENT'
        WHERE (a.workspace_id,a.business_id,a.resource_id,a.id,a.session_id)
          =(h.workspace_id,h.business_id,h.resource_id,h.allocation_id,h.session_id)
          AND a.kind='HOLD' AND a.released_at IS NULL AND h.expires_at>moment
          AND a.occupied=tstzrange(slot.busy_start,slot.busy_end,'[)');
      IF NOT FOUND THEN RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P3101'; END IF;
      INSERT INTO app.appointments(workspace_id,business_id,resource_id,hold_id,session_id,
        allocation_id,status,visit_start,visit_end,timezone,confirmed_at)
      VALUES(h.workspace_id,h.business_id,h.resource_id,h.id,h.session_id,h.allocation_id,
        'CONFIRMED',slot.visit_start,slot.visit_end,offered.timezone,moment) RETURNING * INTO booking;
      RETURN platform.scheduling_appointment_view(booking);
    END $$""",
    OWNER_BOOKING: r"""CREATE FUNCTION platform.scheduling_owner_booking(
      p_selection jsonb
    ) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    DECLARE business uuid:=(p_selection->>'business_id')::uuid;
      session uuid:=(p_selection->>'session_id')::uuid;
      ws uuid:=platform.scheduling_owner_scope(business,'schedule');
      moment timestamptz; snapshot jsonb;
    BEGIN
      PERFORM platform.scheduling_agreement(ws,p_selection);
      moment:=clock_timestamp();
      -- Choose the currently assigned booking. If all attempts ended, keep
      -- showing the latest hold and its actual expiration or release.
      SELECT CASE WHEN p.id IS NULL THEN platform.scheduling_hold_view(h,moment)
          ELSE platform.scheduling_appointment_view(p)-'session_id' END || jsonb_build_object(
          'resource_id',h.resource_id,'busy_start',lower(a.occupied),'busy_end',upper(a.occupied))
        INTO snapshot
        FROM app.reservation_holds h
        JOIN app.resource_allocations a ON (a.workspace_id,a.business_id,a.id)
          =(h.workspace_id,h.business_id,h.allocation_id)
        LEFT JOIN app.appointments p ON (p.workspace_id,p.business_id,p.hold_id)
          =(h.workspace_id,h.business_id,h.id)
        WHERE (h.workspace_id,h.business_id,h.session_id)=(ws,business,session)
        ORDER BY (p.id IS NOT NULL) DESC,
          (a.released_at IS NULL AND h.expires_at>moment) DESC,h.created_at DESC,h.id DESC
        LIMIT 1;
      RETURN jsonb_build_object('session_id',session,'booking',snapshot);
    END $$""",
}


def previous_scheduling():
    scripts = op.get_context().script
    if scripts is None:
        from pathlib import Path

        from alembic.script import ScriptDirectory

        scripts = ScriptDirectory(str(Path(__file__).resolve().parents[1]))
    return scripts.get_revision(down_revision).module


def replace(sql: str, old: str, new: str) -> str:
    assert sql.count(old) == 1, old
    return sql.replace(old, new)


def replacement_sql(prior) -> dict[str, str]:
    active = replace(prior.FUNCTIONS[ACTIVE_ALLOCATIONS], "a.kind='BLOCK' OR", "a.kind<>'HOLD' OR")
    expire = replace(
        prior.FUNCTIONS[EXPIRE_HOLDS],
        "AND a.released_at IS NULL AND h.expires_at<=moment",
        "AND a.kind='HOLD' AND a.released_at IS NULL AND h.expires_at<=moment",
    )
    calendar = replace(
        prior.FUNCTIONS[CALENDAR_PROTECTED],
        """      SELECT jsonb_agg(jsonb_build_object('kind','HOLD','id',h.id) ORDER BY h.id)
        INTO affected FROM platform.scheduling_active_allocations(NEW.workspace_id,NEW.business_id,NEW.id,moment) a
        JOIN app.reservation_holds h ON (h.workspace_id,h.business_id,h.allocation_id)
          =(a.workspace_id,a.business_id,a.id)
        WHERE upper(a.occupied)>moment""",
        """      SELECT jsonb_agg(jsonb_build_object('kind',a.kind,'id',coalesce(p.id,h.id)) ORDER BY coalesce(p.id,h.id))
        INTO affected FROM platform.scheduling_active_allocations(NEW.workspace_id,NEW.business_id,NEW.id,moment) a
        LEFT JOIN app.reservation_holds h ON (h.workspace_id,h.business_id,h.allocation_id)
          =(a.workspace_id,a.business_id,a.id)
        LEFT JOIN app.appointments p ON (p.workspace_id,p.business_id,p.allocation_id)
          =(a.workspace_id,a.business_id,a.id)
        WHERE a.kind IN ('HOLD','APPOINTMENT') AND upper(a.occupied)>moment""",
    )
    hold = replace(
        prior.FUNCTIONS[HOLD_VIEW],
        "'outcome',CASE WHEN a.release_reason IS NOT NULL THEN a.release_reason",
        """'outcome',CASE WHEN a.kind='APPOINTMENT' THEN 'CONVERTED'
          WHEN a.release_reason IS NOT NULL THEN a.release_reason""",
    )
    client = replace(
        prior.FUNCTIONS[CLIENT_COMMAND],
        "            RETURN platform.scheduling_hold_view(hold,moment);",
        """            RETURN CASE WHEN p_action='select' THEN platform.scheduling_complete_choice(hold,q,moment)
              ELSE platform.scheduling_hold_view(hold,moment) END;""",
    )
    client = replace(
        client,
        "(ws,business,hold.allocation_id) AND released_at IS NULL;",
        "(ws,business,hold.allocation_id) AND kind='HOLD' AND released_at IS NULL;",
    )
    client = replace(
        client,
        "        IF FOUND THEN\n          response:=platform.scheduling_hold_view(hold,moment);",
        "        IF FOUND THEN\n          response:=platform.scheduling_complete_choice(hold,q,moment);",
    )
    client = replace(
        client,
        "              response:=platform.scheduling_hold_view(hold,moment);",
        "              response:=platform.scheduling_complete_choice(hold,q,moment);",
    )
    client = replace(
        client,
        "AND a.kind='HOLD' AND a.released_at IS NULL)",
        "AND a.released_at IS NULL)",
    )
    owner_block = replace(
        prior.FUNCTIONS[OWNER_BLOCK],
        "jsonb_build_object('kind',a.kind,'id',coalesce(h.id,a.id))",
        "jsonb_build_object('kind',a.kind,'id',coalesce(p.id,h.id,a.id))",
    )
    owner_block = replace(
        owner_block,
        """            ON (h.workspace_id,h.business_id,h.allocation_id)=(a.workspace_id,a.business_id,a.id)
          WHERE""",
        """            ON (h.workspace_id,h.business_id,h.allocation_id)=(a.workspace_id,a.business_id,a.id)
          LEFT JOIN app.appointments p ON (p.workspace_id,p.business_id,p.allocation_id)
            =(a.workspace_id,a.business_id,a.id)
          WHERE""",
    )
    return {
        signature: sql.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
        for signature, sql in {
            ACTIVE_ALLOCATIONS: active,
            EXPIRE_HOLDS: expire,
            CALENDAR_PROTECTED: calendar,
            HOLD_VIEW: hold,
            CLIENT_COMMAND: client,
            OWNER_BLOCK: owner_block,
        }.items()
    }


def profile_sql(prior, availability, functions: dict[str, str]) -> str:
    previous_functions = prior.FUNCTIONS | {prior.SNAPSHOT: prior.snapshot_sql(availability)}
    profile_before = prior.profile_sql(availability, previous_functions)
    callers = dict(
        zip(
            prior.PROFILE_CALLERS,
            prior.callers_sql(availability, THIS_PROFILE, "'0034'"),
            strict=True,
        )
    )
    replacements = functions | callers | {PREVIOUS_PROFILE: profile_before}
    runtime = prior.RUNTIME_FUNCTIONS | {OWNER_BOOKING}
    profile = profile_before.replace(PREVIOUS_PROFILE, THIS_PROFILE)
    for signature in replacements:
        profile = re.sub(r"\('" + re.escape(signature) + r"',[^\n]+\),\n", "", profile)
    expected = []
    for signature, sql in sorted(replacements.items()):
        header, body, _ = sql.split("$$")
        digest = hashlib.sha256(body.encode()).hexdigest()
        language = "plpgsql" if "LANGUAGE plpgsql" in header else "sql"
        definer = str("SECURITY DEFINER" in header).lower()
        volatility = "s" if " STABLE " in header else "v"
        can_execute = str(signature in runtime).lower()
        expected.append(
            f"('{signature}','{digest}','{language}',{definer},'{volatility}',{can_execute})"
        )
    names = re.findall(r"(?:\(|,)\s*([a-z_][a-z_0-9]*)\s+(?:uuid|text|timestamptz)\b", TABLE_SQL)
    columns = ",".join(f"'{name}'" for name in names)
    return (
        profile.replace(" AS (VALUES ", " AS (VALUES " + ",\n".join(expected) + ",\n", 1)
        .replace(
            "columns_expected(table_name,column_names) AS (VALUES ",
            f"columns_expected(table_name,column_names) AS (VALUES ('{APPOINTMENTS}',ARRAY[{columns}]::text[]),\n",
            1,
        )
        .replace("FROM functions)=430", f"FROM functions)={430 + len(FUNCTIONS) + 1}")
        .replace("FROM expected)=429", f"FROM expected)={429 + len(FUNCTIONS) + 1}")
        .replace("FROM tables)=96", "FROM tables)=97")
        .replace("FROM tables WHERE name IN (", f"FROM tables WHERE name IN ('{APPOINTMENTS}',", 1)
        .replace("'0033'", "'0034'")
        .replace(prior.NONFUNCTION_SHA256, NONFUNCTION_SHA256)
    )


def upgrade() -> None:
    prior = previous_scheduling()
    availability = prior.previous_scheduling()
    op.execute("""ALTER TABLE app.resource_allocations
      DROP CONSTRAINT resource_allocations_kind_check,
      DROP CONSTRAINT resource_allocations_check1,
      ADD CONSTRAINT resource_allocations_kind_check CHECK(kind IN ('HOLD','BLOCK','APPOINTMENT')),
      ADD CONSTRAINT resource_allocations_check1 CHECK((session_id IS NOT NULL)=(kind<>'BLOCK'))""")
    op.execute("DROP INDEX app.resource_allocation_active_session")
    op.execute("""CREATE UNIQUE INDEX resource_allocation_active_session
      ON app.resource_allocations(workspace_id,business_id,session_id)
      WHERE session_id IS NOT NULL AND released_at IS NULL""")
    op.execute("""ALTER TABLE app.reservation_holds ADD CONSTRAINT reservation_holds_appointment_source
      UNIQUE(workspace_id,business_id,resource_id,id,session_id,allocation_id)""")
    op.execute(TABLE_SQL)
    op.execute("ALTER TABLE app.appointments ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE app.appointments FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY scheduling_migrator ON app.appointments
      TO asm_migrator USING(true) WITH CHECK(true)""")
    op.execute("REVOKE ALL ON app.appointments FROM PUBLIC,asm_runtime")
    op.execute("""CREATE UNIQUE INDEX appointment_confirmed_session
      ON app.appointments(workspace_id,business_id,session_id) WHERE status='CONFIRMED'""")
    op.execute("""CREATE TRIGGER scheduling_fact_immutable BEFORE UPDATE OR DELETE ON app.appointments
      FOR EACH ROW EXECUTE FUNCTION platform.scheduling_fact_immutable()""")
    functions = FUNCTIONS | replacement_sql(prior)
    runtime = prior.RUNTIME_FUNCTIONS | {OWNER_BOOKING}
    for signature, sql in functions.items():
        op.execute(sql)
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC,asm_runtime")
        if signature in runtime:
            op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO asm_runtime")
    for sql in prior.callers_sql(availability, THIS_PROFILE, "'0034'"):
        op.execute(sql)
    op.execute(profile_sql(prior, availability, functions))
    op.execute(f"REVOKE ALL ON FUNCTION {THIS_PROFILE} FROM PUBLIC,asm_runtime")


def downgrade() -> None:
    prior = previous_scheduling()
    availability = prior.previous_scheduling()
    op.execute(
        "LOCK TABLE app.resource_allocations,app.reservation_holds,app.appointments IN ACCESS EXCLUSIVE MODE"
    )
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM app.appointments)
        OR EXISTS(SELECT 1 FROM app.resource_allocations WHERE kind='APPOINTMENT')
        THEN RAISE EXCEPTION 'SCHEDULING_APPOINTMENTS_DURABLE_DATA' USING ERRCODE='55000'; END IF;
    END $$""")
    for sql in prior.callers_sql(availability, PREVIOUS_PROFILE, "'0033'"):
        op.execute(sql)
    op.execute(f"DROP FUNCTION {THIS_PROFILE}")
    for signature in replacement_sql(prior):
        op.execute(
            prior.FUNCTIONS[signature].replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
        )
    for signature in reversed(FUNCTIONS):
        op.execute(f"DROP FUNCTION {signature}")
    op.execute("DROP TABLE app.appointments")
    op.execute(
        "ALTER TABLE app.reservation_holds DROP CONSTRAINT reservation_holds_appointment_source"
    )
    op.execute("DROP INDEX app.resource_allocation_active_session")
    op.execute(prior.INDEXES[0])
    op.execute("""ALTER TABLE app.resource_allocations
      DROP CONSTRAINT resource_allocations_kind_check,
      DROP CONSTRAINT resource_allocations_check1,
      ADD CONSTRAINT resource_allocations_kind_check CHECK(kind IN ('HOLD','BLOCK')),
      ADD CONSTRAINT resource_allocations_check1 CHECK((session_id IS NOT NULL)=(kind='HOLD'))""")
