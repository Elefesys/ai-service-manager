"""Atomically replace or cancel the current appointment, retaining its history."""

import hashlib
import re

from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None

PREVIOUS_PROFILE = "platform.scheduling_appointment_schema_profile()"
THIS_PROFILE = "platform.scheduling_reschedule_schema_profile()"
NONFUNCTION_SHA256 = "fbb12c3304ea5d08d1b27b3cf5360839f040eac534ebb58cc0115d9a57521c72"
APPOINTMENTS = "app.appointments"
OFFERS = "app.availability_offers"
TRANSITION = "platform.scheduling_appointment_transition()"
BOOKING_VIEW = "platform.scheduling_booking_appointment(app.appointments)"
OWNER_APPOINTMENT = "platform.scheduling_owner_appointment(jsonb,text,uuid,jsonb)"
SNAPSHOT = "platform.scheduling_snapshot(uuid,uuid,text,date,timestamptz)"
EXCLUDING = "platform.scheduling_snapshot_excluding(uuid,uuid,text,date,timestamptz,uuid)"
SAVE_OFFER = "platform.scheduling_save_offer(app.quotes,app.scheduling_resources,uuid,uuid,date,text,jsonb,timestamptz)"
SAVE_WINDOW_OFFER = (
    "platform.scheduling_save_window_offer(app.quotes,app.scheduling_resources,uuid,uuid,date,text,"
    "jsonb,timestamptz,app.appointments)"
)

APPOINTMENT_COLUMNS = (
    "previous_appointment_id",
    "reschedule_option_id",
    "cancelled_at",
    "cancelled_by",
    "cancel_reason",
)
OFFER_COLUMNS = ("replacement_appointment_id",)

APPOINTMENT_DDL = r"""ALTER TABLE app.appointments
      DROP CONSTRAINT appointments_status_check,
      ALTER COLUMN hold_id DROP NOT NULL,
      ADD COLUMN previous_appointment_id uuid,
      ADD COLUMN reschedule_option_id uuid,
      ADD COLUMN cancelled_at timestamptz,
      ADD COLUMN cancelled_by uuid,
      ADD COLUMN cancel_reason text,
      ADD CONSTRAINT appointment_lifecycle CHECK(
        (status='CONFIRMED' AND cancelled_at IS NULL AND cancelled_by IS NULL AND cancel_reason IS NULL)
        OR (status='CANCELLED' AND cancelled_at IS NOT NULL AND isfinite(cancelled_at)
          AND cancelled_at>=confirmed_at AND cancelled_by IS NOT NULL AND cancel_reason IS NOT NULL
          AND cancel_reason=btrim(cancel_reason) AND char_length(cancel_reason) BETWEEN 1 AND 300
          AND cancel_reason ~ '[^[:space:]]')),
      ADD CONSTRAINT appointment_provenance CHECK(
        (hold_id IS NOT NULL AND previous_appointment_id IS NULL AND reschedule_option_id IS NULL)
        OR (hold_id IS NULL AND previous_appointment_id IS NOT NULL AND previous_appointment_id<>id
          AND reschedule_option_id IS NOT NULL)),
      ADD CONSTRAINT appointment_scoped_identity UNIQUE(workspace_id,business_id,resource_id,session_id,id),
      ADD CONSTRAINT appointment_one_successor UNIQUE(workspace_id,business_id,previous_appointment_id),
      ADD CONSTRAINT appointment_option_once UNIQUE(workspace_id,business_id,reschedule_option_id),
      ADD CONSTRAINT appointment_predecessor FOREIGN KEY(workspace_id,business_id,resource_id,session_id,
        previous_appointment_id) REFERENCES app.appointments(workspace_id,business_id,resource_id,session_id,id),
      ADD CONSTRAINT appointment_allocation FOREIGN KEY(workspace_id,business_id,resource_id,allocation_id,
        session_id) REFERENCES app.resource_allocations(workspace_id,business_id,resource_id,id,session_id),
      ADD CONSTRAINT appointment_reschedule_source FOREIGN KEY(workspace_id,business_id,reschedule_option_id)
        REFERENCES app.availability_options(workspace_id,business_id,id),
      ADD CONSTRAINT appointment_cancel_author FOREIGN KEY(cancelled_by) REFERENCES platform.user_accounts(id)"""

OFFER_DDL = r"""ALTER TABLE app.availability_offers
      ADD COLUMN replacement_appointment_id uuid,
      ADD CONSTRAINT availability_offer_replacement FOREIGN KEY(workspace_id,business_id,resource_id,
        session_id,replacement_appointment_id) REFERENCES app.appointments(workspace_id,business_id,resource_id,
        session_id,id),
      ADD CONSTRAINT availability_offer_replacement_key CHECK(replacement_appointment_id IS NULL
        OR command_key IS NULL)"""

RECEIPT_CHECK = r"""ALTER TABLE platform.scheduling_command_receipts
      DROP CONSTRAINT scheduling_command_receipts_check1,
      ADD CONSTRAINT scheduling_command_receipts_check1 CHECK(
        (subject_kind='CLIENT' AND action IN ('select','release'))
        OR (subject_kind='OWNER' AND action IN ('block','unblock','reschedule_offer','reschedule','cancel_appointment'))
        OR (subject_kind='OWNER_OFFER' AND action='issue'))"""

FUNCTIONS = {
    TRANSITION: r"""CREATE FUNCTION platform.scheduling_appointment_transition()
    RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
    BEGIN
      IF TG_OP='UPDATE' AND OLD.status='CONFIRMED' AND NEW.status='CANCELLED'
        AND (to_jsonb(OLD)-ARRAY['status','cancelled_at','cancelled_by','cancel_reason'])
          IS NOT DISTINCT FROM (to_jsonb(NEW)-ARRAY['status','cancelled_at','cancelled_by','cancel_reason'])
        AND EXISTS(SELECT 1 FROM app.resource_allocations a
          WHERE (a.workspace_id,a.business_id,a.id)=(OLD.workspace_id,OLD.business_id,OLD.allocation_id)
            AND a.kind='APPOINTMENT' AND a.released_at=NEW.cancelled_at AND a.release_reason='RELEASED')
        THEN RETURN NEW; END IF;
      RAISE EXCEPTION 'SCHEDULING_FACT_IMMUTABLE' USING ERRCODE='23514';
    END $$""",
    BOOKING_VIEW: r"""CREATE FUNCTION platform.scheduling_booking_appointment(
      p app.appointments
    ) RETURNS jsonb LANGUAGE sql STABLE SET search_path=pg_catalog,pg_temp AS $$
      SELECT (platform.scheduling_appointment_view(p)-'session_id') || jsonb_build_object(
        'resource_id',p.resource_id,'busy_start',lower(a.occupied),'busy_end',upper(a.occupied),
        'previous_appointment_id',p.previous_appointment_id,'reschedule_option_id',p.reschedule_option_id,
        'cancelled_at',p.cancelled_at,'cancelled_by',p.cancelled_by,'cancel_reason',p.cancel_reason)
      FROM app.resource_allocations a
      WHERE (a.workspace_id,a.business_id,a.resource_id,a.id,a.session_id)
        =(p.workspace_id,p.business_id,p.resource_id,p.allocation_id,p.session_id)
    $$""",
    OWNER_APPOINTMENT: r"""CREATE FUNCTION platform.scheduling_owner_appointment(
      p_selection jsonb,p_action text,p_expected uuid,p_body jsonb
    ) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    DECLARE business uuid:=(p_selection->>'business_id')::uuid;
      session uuid:=(p_selection->>'session_id')::uuid;
      ws uuid:=platform.scheduling_owner_scope(business,'schedule');
      actor uuid:=nullif(current_setting('asm.actor_id',true),'')::uuid;
      q app.quotes%ROWTYPE:=platform.scheduling_agreement(ws,p_selection);
      resource app.scheduling_resources%ROWTYPE; current_booking app.appointments%ROWTYPE;
      selected_offer app.availability_offers%ROWTYPE; option_row app.availability_options%ROWTYPE;
      policy app.scheduling_policy_revisions%ROWTYPE;
      prior platform.scheduling_command_receipts%ROWTYPE;
      moment timestamptz; requested_date date; supplied_key text:=p_body->>'key';
      reason text; action text; target uuid; new_allocation uuid;
      requested jsonb; response jsonb; affected jsonb; occupied_range tstzrange;
    BEGIN
      IF current_database() NOT IN ('asm_local','asm_test')
        THEN RAISE EXCEPTION 'ACCESS_DENIED' USING ERRCODE='P3101'; END IF;
      IF p_expected IS NULL OR jsonb_typeof(p_body) IS DISTINCT FROM 'object'
        OR p_action IS NULL OR p_action NOT IN ('state','issue','reschedule','cancel')
        OR supplied_key IS NULL OR supplied_key !~ '^[A-Za-z0-9._:-]{1,128}$'
        THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P3101'; END IF;

      requested:=jsonb_build_object('appointment_id',p_expected,'session_id',session);
      IF p_action IN ('state','issue') THEN
        action:='reschedule_offer';
        requested_date:=(p_body->>'date')::date;
        requested:=requested||jsonb_build_object('date',requested_date);
      ELSE
        reason:=p_body->>'reason';
        IF reason IS NULL OR jsonb_typeof(p_body->'reason') IS DISTINCT FROM 'string'
          OR reason<>btrim(reason) OR char_length(reason) NOT BETWEEN 1 AND 300
          OR reason !~ '[^[:space:]]'
          THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P3101'; END IF;
        requested:=requested||jsonb_build_object('reason',reason);
        IF p_action='reschedule' THEN
          target:=(p_body->>'option_id')::uuid;
          IF target IS NULL THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P3101'; END IF;
          action:='reschedule';
          requested:=requested||jsonb_build_object('option_id',target);
        ELSE action:='cancel_appointment'; END IF;
      END IF;

      SELECT * INTO resource FROM app.scheduling_resources
        WHERE (workspace_id,business_id)=(ws,business) FOR UPDATE;
      IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P3101'; END IF;
      moment:=clock_timestamp();
      SELECT c.* INTO prior FROM platform.scheduling_command_receipts c
        WHERE (c.workspace_id,c.business_id,c.subject_kind,c.subject_id,c.command_key)
          =(ws,business,'OWNER',actor,supplied_key);
      IF FOUND THEN
        IF (prior.action,prior.payload) IS DISTINCT FROM (action,requested)
          THEN RAISE EXCEPTION 'IDEMPOTENCY_KEY_CONFLICT' USING ERRCODE='P3101'; END IF;
        RETURN CASE WHEN p_action='state' THEN jsonb_build_object('schedule',NULL,'offer',prior.result)
          ELSE prior.result END;
      END IF;

      SELECT p.* INTO current_booking FROM app.appointments p
        WHERE (p.workspace_id,p.business_id,p.resource_id,p.session_id,p.id)
          =(ws,business,resource.id,session,p_expected);
      IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P3101'; END IF;
      IF current_booking.status<>'CONFIRMED' OR NOT EXISTS(SELECT 1 FROM app.resource_allocations a
        WHERE (a.workspace_id,a.business_id,a.resource_id,a.session_id,a.id)
          =(ws,business,resource.id,session,current_booking.allocation_id)
          AND a.kind='APPOINTMENT' AND a.released_at IS NULL)
        THEN RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P3101'; END IF;

      IF p_action='state' THEN
        RETURN jsonb_build_object('offer',NULL,'schedule',platform.scheduling_snapshot_excluding(
          ws,business,q.material->>'service_id',requested_date,moment,current_booking.allocation_id));
      ELSIF p_action='issue' THEN
        response:=platform.scheduling_save_window_offer(q,resource,(p_selection->>'order_id')::uuid,
          session,requested_date,NULL,p_body->'options',moment,current_booking);
      ELSE
        IF p_action='reschedule' THEN
          SELECT f.* INTO selected_offer FROM app.availability_offers f
            JOIN app.availability_options x
              ON (x.workspace_id,x.business_id,x.offer_id)=(f.workspace_id,f.business_id,f.id)
            WHERE (x.workspace_id,x.business_id,x.id)=(ws,business,target)
              AND (f.workspace_id,f.business_id,f.resource_id,f.client_id,f.conversation_id,f.request_id,
                f.quote_id,f.order_id,f.session_id,f.replacement_appointment_id)
              =(ws,business,resource.id,q.client_id,q.conversation_id,q.request_id,q.id,
                (p_selection->>'order_id')::uuid,session,p_expected);
          IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P3101'; END IF;
          SELECT x.* INTO STRICT option_row FROM app.availability_options x
            WHERE (x.workspace_id,x.business_id,x.id)=(ws,business,target);
          SELECT p.* INTO policy FROM app.scheduling_policy_activations a JOIN app.scheduling_policy_revisions p
            ON (p.workspace_id,p.business_id,p.resource_id,p.service_id,p.id)
              =(a.workspace_id,a.business_id,a.resource_id,a.service_id,a.policy_id)
            WHERE (a.workspace_id,a.business_id,a.resource_id,a.service_id)
              =(ws,business,resource.id,q.material->>'service_id');
          occupied_range:=tstzrange(option_row.busy_start,option_row.busy_end,'[)');
          IF (policy.id,resource.timezone,q.terms_sha256,q.material->>'occupied_minutes',
                q.material->>'duration_reference_id',q.material->'deposit') IS DISTINCT FROM
              (selected_offer.policy_id,selected_offer.timezone,selected_offer.terms_sha256,
                selected_offer.occupied_minutes::text,selected_offer.duration_reference_id::text,
                selected_offer.deposit)
            OR moment>=selected_offer.expires_at
            OR option_row.visit_start<moment+make_interval(mins=>policy.minimum_notice_minutes)
            OR option_row.busy_start<moment
            OR option_row.busy_end>moment+make_interval(hours=>24*policy.horizon_days)
            OR NOT platform.scheduling_contains(ws,business,resource.id,resource.timezone,occupied_range)
            THEN RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P3101'; END IF;

          IF (current_booking.visit_start,current_booking.visit_end)
            =(option_row.visit_start,option_row.visit_end) THEN
            response:=jsonb_build_object('outcome','UNCHANGED','session_id',session,
              'booking',platform.scheduling_booking_appointment(current_booking));
          ELSE
            SELECT jsonb_agg(jsonb_build_object('kind',a.kind,'id',coalesce(p.id,h.id,a.id)) ORDER BY a.id)
              INTO affected FROM platform.scheduling_active_allocations(ws,business,resource.id,moment) a
              LEFT JOIN app.appointments p ON (p.workspace_id,p.business_id,p.allocation_id)
                =(a.workspace_id,a.business_id,a.id)
              LEFT JOIN app.reservation_holds h ON (h.workspace_id,h.business_id,h.allocation_id)
                =(a.workspace_id,a.business_id,a.id)
              WHERE a.id<>current_booking.allocation_id AND a.occupied && occupied_range;
            IF affected IS NOT NULL
              THEN RAISE EXCEPTION 'CALENDAR_CONFLICT' USING ERRCODE='P3101',DETAIL=affected::text; END IF;
            PERFORM platform.scheduling_expire_holds(ws,business,resource.id,occupied_range,session,moment);
          END IF;
        END IF;

        IF response IS NULL THEN
          -- Resource lock and the exclusion constraint protect both intervals at commit.
          UPDATE app.resource_allocations a SET released_at=moment,release_reason='RELEASED'
            WHERE (a.workspace_id,a.business_id,a.resource_id,a.session_id,a.id)
              =(ws,business,resource.id,session,current_booking.allocation_id)
              AND a.kind='APPOINTMENT' AND a.released_at IS NULL;
          IF NOT FOUND THEN RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P3101'; END IF;
          UPDATE app.appointments p SET status='CANCELLED',cancelled_at=moment,
            cancelled_by=actor,cancel_reason=reason
            WHERE (p.workspace_id,p.business_id,p.id)=(ws,business,p_expected)
            RETURNING * INTO current_booking;
          IF p_action='reschedule' THEN
            INSERT INTO app.resource_allocations(workspace_id,business_id,resource_id,kind,session_id,
              occupied,created_at) VALUES(ws,business,resource.id,'APPOINTMENT',session,occupied_range,moment)
              RETURNING id INTO new_allocation;
            INSERT INTO app.appointments(workspace_id,business_id,resource_id,session_id,allocation_id,status,
              visit_start,visit_end,timezone,confirmed_at,previous_appointment_id,reschedule_option_id)
            VALUES(ws,business,resource.id,session,new_allocation,'CONFIRMED',option_row.visit_start,
              option_row.visit_end,selected_offer.timezone,moment,p_expected,target) RETURNING * INTO current_booking;
          END IF;
          response:=jsonb_build_object('outcome',CASE p_action WHEN 'reschedule' THEN 'RESCHEDULED'
              ELSE 'CANCELLED' END,'session_id',session,'booking',platform.scheduling_booking_appointment(current_booking));
        END IF;
      END IF;
      INSERT INTO platform.scheduling_command_receipts(workspace_id,business_id,resource_id,subject_kind,
        subject_id,command_key,action,payload,result,recorded_at)
      VALUES(ws,business,resource.id,'OWNER',actor,supplied_key,action,requested,response,moment);
      RETURN response;
    END $$""",
}

OWNER_BOOKING_SQL = r"""CREATE OR REPLACE FUNCTION platform.scheduling_owner_booking(
      p_selection jsonb
    ) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    DECLARE business uuid:=(p_selection->>'business_id')::uuid;
      session uuid:=(p_selection->>'session_id')::uuid;
      ws uuid:=platform.scheduling_owner_scope(business,'schedule');
      moment timestamptz; snapshot jsonb; history jsonb;
    BEGIN
      PERFORM platform.scheduling_agreement(ws,p_selection);
      moment:=clock_timestamp();
      WITH appointment_rows AS (
        SELECT p.id,p.status,p.confirmed_at,p.cancelled_at,platform.scheduling_booking_appointment(p) AS value
        FROM app.appointments p WHERE (p.workspace_id,p.business_id,p.session_id)=(ws,business,session)
      ), candidates(priority,created_at,id,value) AS (
        SELECT CASE status WHEN 'CONFIRMED' THEN 1 ELSE 3 END,confirmed_at,id,value FROM appointment_rows
        UNION ALL
        SELECT CASE WHEN a.released_at IS NULL AND h.expires_at>moment THEN 2 ELSE 4 END,h.created_at,h.id,
          platform.scheduling_hold_view(h,moment)||jsonb_build_object(
            'resource_id',h.resource_id,'busy_start',lower(a.occupied),'busy_end',upper(a.occupied))
        FROM app.reservation_holds h JOIN app.resource_allocations a
          ON (a.workspace_id,a.business_id,a.id)=(h.workspace_id,h.business_id,h.allocation_id)
        WHERE (h.workspace_id,h.business_id,h.session_id)=(ws,business,session) AND a.kind='HOLD'
      )
      SELECT (SELECT value FROM candidates ORDER BY priority,created_at DESC,id DESC LIMIT 1),
        coalesce((SELECT jsonb_agg(value ORDER BY cancelled_at DESC,id DESC) FROM appointment_rows
          WHERE status='CANCELLED'),'[]'::jsonb) INTO snapshot,history;
      RETURN jsonb_build_object('session_id',session,'booking',snapshot,'history',history);
    END $$"""


def previous_scheduling():
    scripts = op.get_context().script
    if scripts is None:
        from pathlib import Path

        from alembic.script import ScriptDirectory

        scripts = ScriptDirectory(str(Path(__file__).resolve().parents[1]))
    return scripts.get_revision(down_revision).module


def window_offer_sql(holds):
    sql = holds.FUNCTIONS[SAVE_OFFER]
    sql = holds_replace(
        sql,
        "FUNCTION platform.scheduling_save_offer(",
        "FUNCTION platform.scheduling_save_window_offer(",
    )
    sql = holds_replace(
        sql,
        "p_day date,p_key text,p_options jsonb,moment timestamptz",
        "p_day date,p_key text,p_options jsonb,moment timestamptz,p_replaced app.appointments",
    )
    sql = holds_replace(
        sql,
        "WHERE a.occupied && tstzrange(x.busy_start,x.busy_end,'[)')))",
        "WHERE a.id IS DISTINCT FROM p_replaced.allocation_id\n"
        "              AND a.occupied && tstzrange(x.busy_start,x.busy_end,'[)')))",
    )
    sql = holds_replace(
        sql,
        "command_key,issued_at,expires_at)\n      VALUES(",
        "command_key,issued_at,expires_at,replacement_appointment_id)\n      VALUES(",
    )
    return holds_replace(
        sql,
        "p_key,moment,moment+make_interval(mins=>p.offer_ttl_minutes))",
        "p_key,moment,moment+make_interval(mins=>p.offer_ttl_minutes),p_replaced.id)",
    )


def holds_replace(sql, old, replacement):
    assert sql.count(old) == 1, old
    return sql.replace(old, replacement)


def snapshot_excluding_sql(holds, availability):
    sql = holds.snapshot_sql(availability)
    sql = holds_replace(
        sql,
        "FUNCTION platform.scheduling_snapshot(",
        "FUNCTION platform.scheduling_snapshot_excluding(",
    )
    sql = holds_replace(
        sql,
        "p_date date,now_at timestamptz",
        "p_date date,now_at timestamptz,p_excluded uuid",
    )
    return holds_replace(
        sql,
        "WHERE a.occupied && tstzrange(",
        "WHERE a.id IS DISTINCT FROM p_excluded AND a.occupied && tstzrange(",
    )


def prior_definitions(prior, holds, availability):
    return (
        holds.FUNCTIONS
        | {SNAPSHOT: holds.snapshot_sql(availability)}
        | prior.FUNCTIONS
        | prior.replacement_sql(holds)
    )


def replacements_sql(prior, before):
    held = holds_replace(
        before[prior.HOLD_VIEW],
        "'outcome',CASE WHEN a.kind='APPOINTMENT' THEN 'CONVERTED'",
        """'outcome',CASE WHEN a.kind='APPOINTMENT' THEN
          CASE WHEN p.status='CANCELLED' THEN 'CANCELLED' ELSE 'CONVERTED' END""",
    )
    held = holds_replace(
        held,
        "      WHERE (a.workspace_id,a.business_id,a.id)=",
        """      LEFT JOIN app.appointments p ON (p.workspace_id,p.business_id,p.hold_id)
        =(h.workspace_id,h.business_id,h.id)
      WHERE (a.workspace_id,a.business_id,a.id)=""",
    )
    client = holds_replace(
        before[prior.CLIENT_COMMAND],
        """            IF prior.result->>'outcome'='ALREADY_CONFIRMED' OR NOT (prior.result ? 'hold_id')
              THEN RETURN prior.result; END IF;""",
        """            IF prior.result->>'outcome' IN ('ALREADY_CONFIRMED','CANCELLED')
              AND prior.result ? 'appointment_id' THEN
              RETURN coalesce((
                SELECT CASE WHEN recorded.status='CANCELLED' THEN platform.scheduling_appointment_view(recorded)
                  ELSE prior.result END
                FROM app.appointments recorded
                WHERE (recorded.workspace_id,recorded.business_id,recorded.session_id,recorded.id)
                  =(ws,business,session,(prior.result->>'appointment_id')::uuid)
              ),prior.result);
            END IF;
            IF NOT (prior.result ? 'hold_id') THEN RETURN prior.result; END IF;""",
    )
    client = holds_replace(
        client,
        """          WHERE (o.workspace_id,o.business_id,o.id)=(ws,business,p_target)
            AND (f.resource_id""",
        """          WHERE (o.workspace_id,o.business_id,o.id)=(ws,business,p_target)
            AND f.replacement_appointment_id IS NULL
            AND (f.resource_id""",
    )
    client = holds_replace(
        client,
        """            SELECT platform.scheduling_appointment_view(a)||jsonb_build_object('outcome','ALREADY_CONFIRMED')
              INTO response FROM app.appointments a
              WHERE (a.workspace_id,a.business_id,a.resource_id,a.session_id,a.status)
                =(ws,business,r.id,session,'CONFIRMED');""",
        """            SELECT CASE WHEN a.status='CONFIRMED' THEN platform.scheduling_appointment_view(a)
                || jsonb_build_object('outcome','ALREADY_CONFIRMED') ELSE platform.scheduling_appointment_view(a) END
              INTO response FROM app.appointments a
              WHERE (a.workspace_id,a.business_id,a.resource_id,a.session_id)=(ws,business,r.id,session)
                AND (a.status='CONFIRMED' OR a.cancelled_at>=offer.issued_at)
              ORDER BY (a.status='CONFIRMED') DESC,a.cancelled_at DESC,a.id DESC LIMIT 1;""",
    )
    return {
        prior.HOLD_VIEW: held,
        prior.CLIENT_COMMAND: client,
        prior.OWNER_BOOKING: OWNER_BOOKING_SQL,
        SNAPSHOT: r"""CREATE OR REPLACE FUNCTION platform.scheduling_snapshot(
      ws uuid,p_business uuid,p_service text,p_date date,now_at timestamptz
    ) RETURNS jsonb LANGUAGE sql SET search_path=pg_catalog,pg_temp AS $$
      SELECT platform.scheduling_snapshot_excluding(ws,p_business,p_service,p_date,now_at,NULL)
    $$""",
        SAVE_OFFER: r"""CREATE OR REPLACE FUNCTION platform.scheduling_save_offer(
      q app.quotes,r app.scheduling_resources,p_order uuid,p_session uuid,
      p_day date,p_key text,p_options jsonb,moment timestamptz
    ) RETURNS jsonb LANGUAGE sql SET search_path=pg_catalog,pg_temp AS $$
      SELECT platform.scheduling_save_window_offer(q,r,p_order,p_session,p_day,p_key,p_options,moment,NULL)
    $$""",
    }


def profile_sql(prior, holds, availability, before, functions):
    profile_before = prior.profile_sql(
        holds, availability, prior.FUNCTIONS | prior.replacement_sql(holds)
    )
    callers = dict(
        zip(
            holds.PROFILE_CALLERS,
            holds.callers_sql(availability, THIS_PROFILE, "'0035'"),
            strict=True,
        )
    )
    replacements = functions | callers | {PREVIOUS_PROFILE: profile_before}
    runtime = holds.RUNTIME_FUNCTIONS | {prior.OWNER_BOOKING, OWNER_APPOINTMENT}
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
    for table, sql, additions in (
        (APPOINTMENTS, prior.TABLE_SQL, APPOINTMENT_COLUMNS),
        (OFFERS, holds.TABLES[OFFERS], OFFER_COLUMNS),
    ):
        names = re.findall(
            r"(?:\(|,)\s*([a-z_][a-z_0-9]*)\s+(?:uuid|text|integer|bigint|timestamptz|date|jsonb)\b",
            sql,
        )
        columns = ",".join(f"'{name}'" for name in names)
        continued = columns + "," + ",".join(f"'{name}'" for name in additions)
        profile = holds_replace(
            profile,
            f"('{table}',ARRAY[{columns}]::text[])",
            f"('{table}',ARRAY[{continued}]::text[])",
        )
    growth = len(functions.keys() - before.keys()) + 1
    return (
        profile.replace(" AS (VALUES ", " AS (VALUES " + ",\n".join(expected) + ",\n", 1)
        .replace("FROM functions)=434", f"FROM functions)={434 + growth}")
        .replace("FROM expected)=433", f"FROM expected)={433 + growth}")
        .replace("'0034'", "'0035'")
        .replace(prior.NONFUNCTION_SHA256, NONFUNCTION_SHA256)
    )


def upgrade() -> None:
    prior = previous_scheduling()
    holds = prior.previous_scheduling()
    availability = holds.previous_scheduling()
    before = prior_definitions(prior, holds, availability)
    op.execute(APPOINTMENT_DDL)
    op.execute(OFFER_DDL)
    op.execute(RECEIPT_CHECK)
    helpers = {
        EXCLUDING: snapshot_excluding_sql(holds, availability),
        SAVE_WINDOW_OFFER: window_offer_sql(holds),
    }
    replacements = replacements_sql(prior, before)
    # SQL-language helpers can resolve their references at CREATE time.
    functions = helpers | replacements | FUNCTIONS
    runtime = holds.RUNTIME_FUNCTIONS | {prior.OWNER_BOOKING, OWNER_APPOINTMENT}
    for signature, sql in functions.items():
        op.execute(sql)
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC,asm_runtime")
        if signature in runtime:
            op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO asm_runtime")
    op.execute("DROP TRIGGER scheduling_fact_immutable ON app.appointments")
    op.execute("""CREATE TRIGGER scheduling_appointment_transition BEFORE UPDATE OR DELETE ON app.appointments
      FOR EACH ROW EXECUTE FUNCTION platform.scheduling_appointment_transition()""")
    for sql in holds.callers_sql(availability, THIS_PROFILE, "'0035'"):
        op.execute(sql)
    op.execute(profile_sql(prior, holds, availability, before, functions))
    op.execute(f"REVOKE ALL ON FUNCTION {THIS_PROFILE} FROM PUBLIC,asm_runtime")


def downgrade() -> None:
    prior = previous_scheduling()
    holds = prior.previous_scheduling()
    availability = holds.previous_scheduling()
    before = prior_definitions(prior, holds, availability)
    op.execute(
        "LOCK TABLE app.resource_allocations,app.availability_offers,app.appointments,"
        "platform.scheduling_command_receipts IN ACCESS EXCLUSIVE MODE"
    )
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM app.appointments WHERE status='CANCELLED' OR previous_appointment_id IS NOT NULL)
        OR EXISTS(SELECT 1 FROM app.availability_offers WHERE replacement_appointment_id IS NOT NULL)
        OR EXISTS(SELECT 1 FROM platform.scheduling_command_receipts
          WHERE action IN ('reschedule_offer','reschedule','cancel_appointment'))
        THEN RAISE EXCEPTION 'SCHEDULING_RESCHEDULE_DURABLE_DATA' USING ERRCODE='55000'; END IF;
    END $$""")
    for sql in holds.callers_sql(availability, PREVIOUS_PROFILE, "'0034'"):
        op.execute(sql)
    op.execute(f"DROP FUNCTION {THIS_PROFILE}")
    op.execute("DROP TRIGGER scheduling_appointment_transition ON app.appointments")
    for signature in replacements_sql(prior, before):
        sql = before[signature].replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
        op.execute(sql)
    for signature in (OWNER_APPOINTMENT, BOOKING_VIEW, TRANSITION, SAVE_WINDOW_OFFER, EXCLUDING):
        op.execute(f"DROP FUNCTION {signature}")
    op.execute("""CREATE TRIGGER scheduling_fact_immutable BEFORE UPDATE OR DELETE ON app.appointments
      FOR EACH ROW EXECUTE FUNCTION platform.scheduling_fact_immutable()""")
    op.execute(
        holds_replace(RECEIPT_CHECK, ",'reschedule_offer','reschedule','cancel_appointment'", "")
    )
    op.execute("""ALTER TABLE app.availability_offers
      DROP CONSTRAINT availability_offer_replacement,DROP CONSTRAINT availability_offer_replacement_key,
      DROP COLUMN replacement_appointment_id""")
    op.execute("""ALTER TABLE app.appointments
      DROP CONSTRAINT appointment_predecessor,DROP CONSTRAINT appointment_reschedule_source,
      DROP CONSTRAINT appointment_one_successor,DROP CONSTRAINT appointment_option_once,
      DROP CONSTRAINT appointment_scoped_identity,DROP CONSTRAINT appointment_lifecycle,
      DROP CONSTRAINT appointment_provenance,DROP CONSTRAINT appointment_allocation,
      DROP CONSTRAINT appointment_cancel_author,
      DROP COLUMN previous_appointment_id,DROP COLUMN reschedule_option_id,
      DROP COLUMN cancelled_at,DROP COLUMN cancelled_by,DROP COLUMN cancel_reason,
      ALTER COLUMN hold_id SET NOT NULL,
      ADD CONSTRAINT appointments_status_check CHECK(status='CONFIRMED')""")
