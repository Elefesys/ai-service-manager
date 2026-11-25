"""Project one scoped calendar day from its existing scheduling facts."""

import hashlib
import re

from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None

OWNER_DAY = "platform.scheduling_owner_day(uuid,date)"
THIS_PROFILE = "platform.scheduling_owner_day_schema_profile()"

OWNER_DAY_SQL = r"""CREATE FUNCTION platform.scheduling_owner_day(
      p_business uuid,p_date date
    ) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    DECLARE ws uuid:=platform.scheduling_owner_scope(p_business,'schedule');
      moment timestamptz:=clock_timestamp();
    BEGIN
      IF p_date IS NOT NULL AND (p_date<DATE '0001-01-01' OR p_date>DATE '9999-12-31')
        THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P3101'; END IF;
      RETURN (
        WITH resource AS (
          SELECT r.id,r.timezone,coalesce(r.schedule_version,0) AS schedule_version,
            coalesce(p_date,(moment AT TIME ZONE coalesce(r.timezone,'UTC'))::date) AS local_date
          FROM (VALUES (1)) seed(one) LEFT JOIN app.scheduling_resources r
            ON (r.workspace_id,r.business_id)=(ws,p_business)
        ), day AS (
          SELECT r.*,o.windows AS override_windows,bounds.span
          FROM resource r LEFT JOIN app.availability_overrides o
            ON (o.workspace_id,o.business_id,o.resource_id,o.local_date)=(ws,p_business,r.id,r.local_date)
          LEFT JOIN LATERAL (
            SELECT tstzrange(min(boundary),max(boundary),'[)') AS span FROM (
              -- Prefer the first midnight when a clock rollback repeats it.
              SELECT least(m.local_time AT TIME ZONE r.timezone,
                CASE WHEN earlier.instant AT TIME ZONE r.timezone=m.local_time
                  THEN earlier.instant END) AS boundary
              FROM (VALUES (r.local_date::timestamp),((r.local_date+1)::timestamp)) m(local_time)
              CROSS JOIN LATERAL (
                SELECT ((m.local_time-interval '1 day') AT TIME ZONE r.timezone)+interval '24 hours'
                  AS instant
              ) earlier
            ) edges
          ) bounds ON r.id IS NOT NULL
        ), allocations AS (
          SELECT a.* FROM day d JOIN app.resource_allocations a
            ON (a.workspace_id,a.business_id,a.resource_id)=(ws,p_business,d.id)
          WHERE a.occupied && d.span
        ), bookings AS (
          SELECT p.id,p.session_id,lower(a.occupied) AS starts_at,p.status='CONFIRMED' AS active,
            jsonb_build_object('kind','APPOINTMENT','booking',platform.scheduling_booking_appointment(p),
              'successor',CASE WHEN n.id IS NOT NULL THEN jsonb_build_object('appointment_id',n.id,
                'date',(n.visit_start AT TIME ZONE d.timezone)::date) END) AS item
          FROM allocations a JOIN app.appointments p
            ON (p.workspace_id,p.business_id,p.resource_id,p.allocation_id,p.session_id)
              =(a.workspace_id,a.business_id,a.resource_id,a.id,a.session_id)
          JOIN day d ON d.id=a.resource_id
          LEFT JOIN app.appointments n ON (n.workspace_id,n.business_id,n.previous_appointment_id)
            =(p.workspace_id,p.business_id,p.id)
          WHERE a.kind='APPOINTMENT'
          UNION ALL
          SELECT h.id,h.session_id,lower(a.occupied),a.released_at IS NULL AND h.expires_at>moment,
            jsonb_build_object('kind','HOLD','booking',platform.scheduling_hold_view(h,moment)
              ||jsonb_build_object('resource_id',h.resource_id,
                'busy_start',lower(a.occupied),'busy_end',upper(a.occupied)))
          FROM allocations a JOIN app.reservation_holds h
            ON (h.workspace_id,h.business_id,h.resource_id,h.allocation_id,h.session_id)
              =(a.workspace_id,a.business_id,a.resource_id,a.id,a.session_id)
          WHERE a.kind='HOLD'
        ), rows AS (
          SELECT b.id,b.starts_at,b.active,b.item||jsonb_build_object(
            'selection',jsonb_build_object('client_id',c.client_id,'conversation_id',c.id,
              'request_id',d.id,'quote_id',q.id,'order_id',o.id,'session_id',s.id),
            'work_label',concat_ws(' · ',coalesce(f.idea,btrim(d.service_name)),f.placement)) AS item
          FROM bookings b JOIN app.service_sessions s ON (s.workspace_id,s.id)=(ws,b.session_id)
          JOIN app.service_orders o ON (o.workspace_id,o.id)=(ws,s.order_id)
          JOIN app.quote_acceptances k ON (k.workspace_id,k.request_id,k.id)=(ws,o.request_id,o.acceptance_id)
          JOIN app.quotes q ON (q.workspace_id,q.business_id,q.request_id,q.conversation_id,q.id)
            =(ws,p_business,o.request_id,k.conversation_id,k.quote_id)
          JOIN app.service_requests d ON (d.workspace_id,d.business_id,d.conversation_id,d.client_id,d.id)
            =(ws,p_business,q.conversation_id,q.client_id,o.request_id)
          JOIN app.conversations c ON (c.workspace_id,c.business_id,c.client_id,c.id)
            =(ws,p_business,d.client_id,d.conversation_id)
          CROSS JOIN LATERAL (
            SELECT max(nullif(btrim(f->>'value'),'')) FILTER (WHERE f->>'field'='idea') AS idea,
              max(nullif(btrim(f->>'value'),'')) FILTER (WHERE f->>'field'='placement') AS placement
            FROM jsonb_array_elements(d.facts) AS facts(f)
          ) f
          UNION ALL
          SELECT a.id,lower(a.occupied),true,jsonb_build_object('kind','BLOCK','block_id',a.id,
            'start',lower(a.occupied),'end',upper(a.occupied),'timezone',d.timezone)
          FROM allocations a JOIN day d ON d.id=a.resource_id
          WHERE a.kind='BLOCK' AND a.released_at IS NULL
        )
        SELECT jsonb_build_object('date',d.local_date,'now',moment,'timezone',d.timezone,'resource_id',d.id,
          'schedule_version',d.schedule_version,
          'exception',CASE WHEN d.override_windows IS NOT NULL THEN
            jsonb_build_object('date',d.local_date,'windows',d.override_windows) END,
          'working_intervals',coalesce(d.override_windows,(SELECT jsonb_agg(jsonb_build_object(
            'start_minute',w.start_minute,'end_minute',w.end_minute) ORDER BY w.start_minute)
            FROM app.availability_rules w WHERE (w.workspace_id,w.business_id,w.resource_id,w.weekday)
              =(ws,p_business,d.id,extract(isodow FROM d.local_date)::integer-1)),'[]'::jsonb),
          'entries',coalesce(r.entries,'[]'::jsonb),'history',coalesce(r.history,'[]'::jsonb))
        FROM day d CROSS JOIN (
          SELECT jsonb_agg(item ORDER BY starts_at,id) FILTER (WHERE active) AS entries,
            jsonb_agg(item ORDER BY starts_at,id) FILTER (WHERE NOT active) AS history
          FROM rows
        ) r);
    END $$"""


def previous_scheduling():
    scripts = op.get_context().script
    if scripts is None:
        from pathlib import Path

        from alembic.script import ScriptDirectory

        scripts = ScriptDirectory(str(Path(__file__).resolve().parents[1]))
    return scripts.get_revision(down_revision).module


def profile_sql(prior, holds, availability, callers: tuple[str, ...]) -> str:
    appointments = prior.previous_scheduling()
    before = prior.prior_definitions(appointments, holds, availability)
    functions = (
        {
            prior.EXCLUDING: prior.snapshot_excluding_sql(holds, availability),
            prior.SAVE_WINDOW_OFFER: prior.window_offer_sql(holds),
        }
        | prior.replacements_sql(appointments, before)
        | prior.FUNCTIONS
    )
    previous = prior.profile_sql(appointments, holds, availability, before, functions)
    changes = dict(zip(holds.PROFILE_CALLERS, callers, strict=True)) | {
        prior.THIS_PROFILE: previous,
        OWNER_DAY: OWNER_DAY_SQL,
    }
    profile = previous.replace(prior.THIS_PROFILE, THIS_PROFILE)
    additions = []
    for signature, sql in sorted(changes.items()):
        profile = re.sub(r"\('" + re.escape(signature) + r"',[^\n]+\),\n", "", profile)
        header, body, _ = sql.split("$$")
        digest = hashlib.sha256(body.encode()).hexdigest()
        language = "plpgsql" if "LANGUAGE plpgsql" in header else "sql"
        volatility = "s" if " STABLE " in header else "v"
        can_execute = str(signature == OWNER_DAY).lower()
        additions.append(
            f"('{signature}','{digest}','{language}',true,'{volatility}',{can_execute})"
        )
    return (
        profile.replace(" AS (VALUES ", " AS (VALUES " + ",\n".join(additions) + ",\n", 1)
        .replace("FROM functions)=440", "FROM functions)=442")
        .replace("FROM expected)=439", "FROM expected)=441")
        .replace("'0035'", "'0036'")
    )


def upgrade() -> None:
    prior = previous_scheduling()
    holds = prior.previous_scheduling().previous_scheduling()
    availability = holds.previous_scheduling()
    callers = holds.callers_sql(availability, THIS_PROFILE, "'0036'")
    op.execute(OWNER_DAY_SQL)
    op.execute(f"REVOKE ALL ON FUNCTION {OWNER_DAY} FROM PUBLIC,asm_runtime")
    op.execute(f"GRANT EXECUTE ON FUNCTION {OWNER_DAY} TO asm_runtime")
    for sql in callers:
        op.execute(sql)
    op.execute(profile_sql(prior, holds, availability, callers))
    op.execute(f"REVOKE ALL ON FUNCTION {THIS_PROFILE} FROM PUBLIC,asm_runtime")


def downgrade() -> None:
    prior = previous_scheduling()
    holds = prior.previous_scheduling().previous_scheduling()
    availability = holds.previous_scheduling()
    for sql in holds.callers_sql(availability, prior.THIS_PROFILE, "'0035'"):
        op.execute(sql)
    op.execute(f"DROP FUNCTION {THIS_PROFILE}")
    op.execute(f"DROP FUNCTION {OWNER_DAY}")
