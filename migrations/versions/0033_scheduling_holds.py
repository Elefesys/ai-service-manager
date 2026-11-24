"""Persist issued options and serialize holds and calendar blocks for one resource."""

import hashlib
import re

from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None

TABLES = {
    "app.availability_offers": r"""CREATE TABLE app.availability_offers (
      workspace_id uuid NOT NULL, business_id uuid NOT NULL, resource_id uuid NOT NULL,
      id uuid NOT NULL DEFAULT uuidv7(),
      client_id uuid NOT NULL, conversation_id uuid NOT NULL, request_id uuid NOT NULL,
      quote_id uuid NOT NULL, order_id uuid NOT NULL, session_id uuid NOT NULL,
      service_id text NOT NULL, policy_id uuid NOT NULL, schedule_version bigint NOT NULL,
      local_date date NOT NULL CHECK(isfinite(local_date)),
      requested_date date CHECK(isfinite(requested_date)),
      timezone text NOT NULL,
      occupied_minutes integer NOT NULL CHECK(occupied_minutes BETWEEN 1 AND 10080),
      duration_reference_id uuid NOT NULL,
      terms_sha256 text NOT NULL CHECK(terms_sha256 ~ '^[0-9a-f]{64}$'),
      deposit jsonb NOT NULL CHECK(jsonb_typeof(deposit)='object'),
      command_key text NOT NULL CHECK(command_key ~ '^[A-Za-z0-9._:-]{1,128}$'),
      issued_at timestamptz NOT NULL CHECK(isfinite(issued_at)),
      expires_at timestamptz NOT NULL CHECK(isfinite(expires_at) AND expires_at>issued_at),
      PRIMARY KEY(workspace_id,business_id,id),
      UNIQUE(workspace_id,business_id,session_id,command_key),
      FOREIGN KEY(workspace_id,business_id,resource_id,service_id,policy_id)
        REFERENCES app.scheduling_policy_revisions(workspace_id,business_id,resource_id,service_id,id),
      FOREIGN KEY(workspace_id,conversation_id,client_id)
        REFERENCES app.conversations(workspace_id,id,client_id),
      FOREIGN KEY(workspace_id,quote_id,request_id,conversation_id)
        REFERENCES app.quotes(workspace_id,id,request_id,conversation_id),
      FOREIGN KEY(workspace_id,order_id) REFERENCES app.service_orders(workspace_id,id),
      FOREIGN KEY(workspace_id,session_id) REFERENCES app.service_sessions(workspace_id,id)
    )""",
    "app.availability_options": r"""CREATE TABLE app.availability_options (
      workspace_id uuid NOT NULL, business_id uuid NOT NULL, offer_id uuid NOT NULL,
      id uuid NOT NULL DEFAULT uuidv7(),
      visit_start timestamptz NOT NULL CHECK(isfinite(visit_start)),
      visit_end timestamptz NOT NULL CHECK(isfinite(visit_end)),
      busy_start timestamptz NOT NULL CHECK(isfinite(busy_start)),
      busy_end timestamptz NOT NULL CHECK(isfinite(busy_end)),
      PRIMARY KEY(workspace_id,business_id,id),
      UNIQUE(workspace_id,business_id,offer_id,visit_start),
      FOREIGN KEY(workspace_id,business_id,offer_id)
        REFERENCES app.availability_offers(workspace_id,business_id,id),
      CHECK(busy_start<=visit_start AND visit_start<visit_end AND visit_end<=busy_end)
    )""",
    "app.resource_allocations": r"""CREATE TABLE app.resource_allocations (
      workspace_id uuid NOT NULL, business_id uuid NOT NULL, resource_id uuid NOT NULL,
      id uuid NOT NULL DEFAULT uuidv7(),
      kind text NOT NULL CHECK(kind IN ('HOLD','BLOCK')),
      session_id uuid,
      occupied tstzrange NOT NULL,
      created_at timestamptz NOT NULL CHECK(isfinite(created_at)),
      released_at timestamptz CHECK(isfinite(released_at) AND released_at>=created_at),
      release_reason text CHECK(release_reason IN ('EXPIRED','RELEASED')),
      PRIMARY KEY(workspace_id,business_id,id),
      UNIQUE(workspace_id,business_id,resource_id,id,session_id),
      FOREIGN KEY(workspace_id,business_id,resource_id)
        REFERENCES app.scheduling_resources(workspace_id,business_id,id),
      FOREIGN KEY(workspace_id,session_id) REFERENCES app.service_sessions(workspace_id,id),
      CHECK((session_id IS NOT NULL)=(kind='HOLD')),
      CHECK((released_at IS NULL)=(release_reason IS NULL)),
      CHECK(release_reason IS DISTINCT FROM 'EXPIRED' OR kind='HOLD'),
      CHECK(NOT isempty(occupied) AND lower_inc(occupied) AND NOT upper_inc(occupied)
        AND NOT lower_inf(occupied) AND NOT upper_inf(occupied)
        AND isfinite(lower(occupied)) AND isfinite(upper(occupied))),
      CONSTRAINT resource_allocation_no_overlap EXCLUDE USING gist (
        workspace_id extensions.gist_uuid_ops WITH =,
        business_id extensions.gist_uuid_ops WITH =,
        resource_id extensions.gist_uuid_ops WITH =, occupied WITH &&
      ) WHERE (released_at IS NULL)
    )""",
    "app.reservation_holds": r"""CREATE TABLE app.reservation_holds (
      workspace_id uuid NOT NULL, business_id uuid NOT NULL, resource_id uuid NOT NULL,
      id uuid NOT NULL DEFAULT uuidv7(),
      option_id uuid NOT NULL, session_id uuid NOT NULL, allocation_id uuid NOT NULL,
      created_at timestamptz NOT NULL CHECK(isfinite(created_at)),
      expires_at timestamptz NOT NULL CHECK(isfinite(expires_at) AND expires_at>created_at),
      PRIMARY KEY(workspace_id,business_id,id),
      UNIQUE(workspace_id,business_id,option_id),
      UNIQUE(workspace_id,business_id,allocation_id),
      FOREIGN KEY(workspace_id,business_id,option_id)
        REFERENCES app.availability_options(workspace_id,business_id,id),
      FOREIGN KEY(workspace_id,business_id,resource_id,allocation_id,session_id)
        REFERENCES app.resource_allocations(workspace_id,business_id,resource_id,id,session_id)
    )""",
    "platform.scheduling_command_receipts": r"""CREATE TABLE platform.scheduling_command_receipts (
      workspace_id uuid NOT NULL, business_id uuid NOT NULL, resource_id uuid NOT NULL,
      subject_kind text NOT NULL CHECK(subject_kind IN ('CLIENT','OWNER')),
      subject_id uuid NOT NULL,
      command_key text NOT NULL CHECK(command_key ~ '^[A-Za-z0-9._:-]{1,128}$'),
      action text NOT NULL,
      payload jsonb NOT NULL CHECK(jsonb_typeof(payload)='object'),
      result jsonb NOT NULL CHECK(jsonb_typeof(result)='object'),
      recorded_at timestamptz NOT NULL CHECK(isfinite(recorded_at)),
      PRIMARY KEY(workspace_id,business_id,subject_kind,subject_id,command_key),
      FOREIGN KEY(workspace_id,business_id,resource_id)
        REFERENCES app.scheduling_resources(workspace_id,business_id,id),
      CHECK((subject_kind='CLIENT' AND action IN ('select','release'))
        OR (subject_kind='OWNER' AND action IN ('block','unblock')))
    )""",
}

INDEXES = (
    """CREATE UNIQUE INDEX resource_allocation_active_session
      ON app.resource_allocations(workspace_id,business_id,session_id)
      WHERE kind='HOLD' AND released_at IS NULL""",
    """CREATE INDEX scheduling_receipt_rejected_option
      ON platform.scheduling_command_receipts(workspace_id,business_id,subject_id,(payload->>'id'))
      WHERE subject_kind='CLIENT' AND action='select' AND NOT (result ? 'hold_id')""",
)

FUNCTIONS = {
    "platform.scheduling_fact_immutable()": r"""CREATE FUNCTION platform.scheduling_fact_immutable()
    RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
    BEGIN
      RAISE EXCEPTION 'SCHEDULING_FACT_IMMUTABLE' USING ERRCODE='23514';
    END $$""",
    "platform.scheduling_agreement(uuid,jsonb)": r"""CREATE FUNCTION platform.scheduling_agreement(
      ws uuid,p_selection jsonb
    ) RETURNS app.quotes LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
    DECLARE accepted app.quotes%ROWTYPE;
    BEGIN
      IF ws IS NULL OR p_selection->>'workspace_id' IS DISTINCT FROM ws::text
        THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P3101'; END IF;
      SELECT q.* INTO accepted FROM app.quotes q
        JOIN app.quote_acceptances qa ON (qa.workspace_id,qa.quote_id)=(q.workspace_id,q.id)
        JOIN app.service_orders o ON (o.workspace_id,o.acceptance_id)=(qa.workspace_id,qa.id)
        JOIN app.service_sessions s ON (s.workspace_id,s.order_id)=(o.workspace_id,o.id)
        JOIN app.conversations c ON (c.workspace_id,c.id,c.business_id,c.client_id)
          =(q.workspace_id,q.conversation_id,q.business_id,q.client_id)
        WHERE (q.workspace_id,q.business_id,q.conversation_id,q.client_id,q.request_id,q.id,o.id,s.id)
          =(ws,(p_selection->>'business_id')::uuid,(p_selection->>'conversation_id')::uuid,
            (p_selection->>'client_id')::uuid,(p_selection->>'request_id')::uuid,
            (p_selection->>'quote_id')::uuid,(p_selection->>'order_id')::uuid,
            (p_selection->>'session_id')::uuid)
          AND s.status='PLANNED' AND s.scheduled_at IS NULL;
      IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P3101'; END IF;
      RETURN accepted;
    END $$""",
    "platform.scheduling_active_allocations(uuid,uuid,uuid,timestamptz)": r"""CREATE FUNCTION platform.scheduling_active_allocations(
      ws uuid,business uuid,resource uuid,moment timestamptz
    ) RETURNS SETOF app.resource_allocations LANGUAGE sql STABLE SET search_path=pg_catalog,pg_temp AS $$
      SELECT a.* FROM app.resource_allocations a
      LEFT JOIN app.reservation_holds h ON (h.workspace_id,h.business_id,h.allocation_id)
        =(a.workspace_id,a.business_id,a.id)
      WHERE (a.workspace_id,a.business_id,a.resource_id)=(ws,business,resource)
        AND a.released_at IS NULL AND (a.kind='BLOCK' OR h.expires_at>moment)
    $$""",
    "platform.scheduling_expire_holds(uuid,uuid,uuid,tstzrange,uuid,timestamptz)": r"""CREATE FUNCTION platform.scheduling_expire_holds(
      ws uuid,business uuid,resource uuid,target tstzrange,session uuid,moment timestamptz
    ) RETURNS void LANGUAGE sql SET search_path=pg_catalog,pg_temp AS $$
      UPDATE app.resource_allocations a SET released_at=moment,release_reason='EXPIRED'
      FROM app.reservation_holds h
      WHERE (a.workspace_id,a.business_id,a.resource_id)=(ws,business,resource)
        AND (h.workspace_id,h.business_id,h.allocation_id)=(a.workspace_id,a.business_id,a.id)
        AND a.released_at IS NULL AND h.expires_at<=moment
        AND (a.occupied && target OR a.session_id=session)
    $$""",
    "platform.scheduling_contains(uuid,uuid,uuid,text,tstzrange)": r"""CREATE FUNCTION platform.scheduling_contains(
      ws uuid,business uuid,resource uuid,zone text,target tstzrange
    ) RETURNS boolean LANGUAGE sql STABLE SET search_path=pg_catalog,pg_temp AS $$
      WITH local_minutes AS (
        SELECT instant AT TIME ZONE zone AS wall
        FROM generate_series(lower(target),upper(target)-interval '1 microsecond',interval '1 minute') g(instant)
      ), bounds AS (
        SELECT min(wall)::date AS day,max(wall)::date AS last_day,
          min(extract(hour FROM wall)*60+extract(minute FROM wall)) AS first_minute,
          max(extract(hour FROM wall)*60+extract(minute FROM wall)) AS last_minute
        FROM local_minutes
      ), override AS (
        SELECT o.windows FROM app.availability_overrides o,bounds b
        WHERE (o.workspace_id,o.business_id,o.resource_id,o.local_date)=(ws,business,resource,b.day)
      ), spans AS (
        SELECT w.start_minute,w.end_minute FROM override o,
          jsonb_to_recordset(o.windows) w(start_minute integer,end_minute integer)
        UNION ALL
        SELECT w.start_minute,w.end_minute FROM app.availability_rules w,bounds b
        WHERE (w.workspace_id,w.business_id,w.resource_id,w.weekday)
          =(ws,business,resource,extract(isodow FROM b.day)-1)
          AND NOT EXISTS(SELECT 1 FROM override)
      )
      SELECT EXISTS(SELECT 1 FROM spans s,bounds b WHERE b.day=b.last_day
        AND s.start_minute<=b.first_minute AND b.last_minute<s.end_minute)
    $$""",
    "platform.scheduling_calendar_protected()": r"""CREATE FUNCTION platform.scheduling_calendar_protected()
    RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
    DECLARE affected jsonb; moment timestamptz:=clock_timestamp();
    BEGIN
      SELECT jsonb_agg(jsonb_build_object('kind','HOLD','id',h.id) ORDER BY h.id)
        INTO affected FROM platform.scheduling_active_allocations(NEW.workspace_id,NEW.business_id,NEW.id,moment) a
        JOIN app.reservation_holds h ON (h.workspace_id,h.business_id,h.allocation_id)
          =(a.workspace_id,a.business_id,a.id)
        WHERE upper(a.occupied)>moment
          AND NOT platform.scheduling_contains(NEW.workspace_id,NEW.business_id,NEW.id,NEW.timezone,a.occupied);
      IF affected IS NOT NULL THEN
        RAISE EXCEPTION 'CALENDAR_CONFLICT' USING ERRCODE='P3101',DETAIL=affected::text;
      END IF;
      RETURN NEW;
    END $$""",
    "platform.scheduling_owner_read(uuid,text,date)": r"""CREATE OR REPLACE FUNCTION platform.scheduling_owner_read(
      p_business uuid,p_service text,p_date date
    ) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    DECLARE ws uuid:=platform.scheduling_owner_scope(p_business,p_service);
    BEGIN
      RETURN platform.scheduling_snapshot(ws,p_business,p_service,p_date,clock_timestamp());
    END $$""",
    "platform.scheduling_offer_view(app.availability_offers)": r"""CREATE FUNCTION platform.scheduling_offer_view(
      offer app.availability_offers
    ) RETURNS jsonb LANGUAGE sql STABLE SET search_path=pg_catalog,pg_temp AS $$
      SELECT jsonb_build_object('offer_id',offer.id,'date',offer.local_date,'timezone',offer.timezone,
        'expires_at',offer.expires_at,'options',coalesce((
          SELECT jsonb_agg(jsonb_build_object('option_id',o.id,'visit_start',o.visit_start,
            'visit_end',o.visit_end,'busy_start',o.busy_start,'busy_end',o.busy_end) ORDER BY o.visit_start)
          FROM app.availability_options o
          WHERE (o.workspace_id,o.business_id,o.offer_id)=(offer.workspace_id,offer.business_id,offer.id)
        ),'[]'::jsonb))
    $$""",
    "platform.scheduling_owner_offer(jsonb,text,date,text,jsonb)": r"""CREATE FUNCTION platform.scheduling_owner_offer(
      p_selection jsonb,p_action text,p_day date,p_key text,p_options jsonb
    ) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    DECLARE business uuid:=(p_selection->>'business_id')::uuid;
      ws uuid:=platform.scheduling_owner_scope(business,'schedule');
      q app.quotes%ROWTYPE:=platform.scheduling_agreement(ws,p_selection);
      r app.scheduling_resources%ROWTYPE; p app.scheduling_policy_revisions%ROWTYPE;
      offer app.availability_offers%ROWTYPE; session uuid:=(p_selection->>'session_id')::uuid;
      moment timestamptz; chosen_date date; snapshot jsonb; minutes integer; duration_ref uuid;
    BEGIN
      SELECT * INTO r FROM app.scheduling_resources
        WHERE (workspace_id,business_id)=(ws,business) FOR UPDATE;
      moment:=clock_timestamp();
      snapshot:=platform.scheduling_snapshot(ws,business,q.material->>'service_id',p_day,moment);
      IF p_action='state' THEN RETURN snapshot; END IF;
      IF p_action IS DISTINCT FROM 'issue' OR p_key IS NULL OR p_key !~ '^[A-Za-z0-9._:-]{1,128}$'
        OR jsonb_typeof(p_options) IS DISTINCT FROM 'array' OR jsonb_array_length(p_options)>8
        THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P3101'; END IF;
      SELECT * INTO offer FROM app.availability_offers o
        WHERE (o.workspace_id,o.business_id,o.session_id,o.command_key)=(ws,business,session,p_key);
      IF FOUND THEN
        IF offer.requested_date IS DISTINCT FROM p_day
          THEN RAISE EXCEPTION 'IDEMPOTENCY_KEY_CONFLICT' USING ERRCODE='P3101'; END IF;
        RETURN platform.scheduling_offer_view(offer);
      END IF;
      chosen_date:=(snapshot->>'date')::date;
      IF p_options='[]'::jsonb THEN RETURN jsonb_build_object(
        'offer_id',NULL,'date',chosen_date,'timezone',r.timezone,'expires_at',NULL,'options','[]'::jsonb);
      END IF;

      SELECT rev.* INTO p FROM app.scheduling_policy_revisions rev
        WHERE (rev.workspace_id,rev.business_id,rev.resource_id,rev.service_id,rev.id)
          =(ws,business,r.id,q.material->>'service_id',(snapshot->'policy'->>'policy_id')::uuid);
      minutes:=(q.material->>'occupied_minutes')::integer;
      duration_ref:=(q.material->>'duration_reference_id')::uuid;
      IF minutes IS NULL OR duration_ref IS NULL OR NOT (
        duration_ref IS NOT DISTINCT FROM (q.material->>'assessment_id')::uuid
        OR duration_ref IS NOT DISTINCT FROM (q.material->>'decision_id')::uuid)
        THEN RAISE EXCEPTION 'DURATION_UNAVAILABLE' USING ERRCODE='P3101'; END IF;
      IF p.id IS NULL THEN RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P3101'; END IF;
      IF EXISTS(SELECT 1 FROM jsonb_to_recordset(p_options) x(
        visit_start timestamptz,visit_end timestamptz,busy_start timestamptz,busy_end timestamptz)
        WHERE x.visit_end IS DISTINCT FROM x.visit_start+make_interval(mins=>minutes)
          OR x.busy_start IS DISTINCT FROM x.visit_start-make_interval(mins=>p.buffer_before_minutes)
          OR x.busy_end IS DISTINCT FROM x.visit_end+make_interval(mins=>p.buffer_after_minutes)
          OR x.visit_start IS NULL OR NOT isfinite(x.visit_start)
          OR (x.visit_start AT TIME ZONE r.timezone)::date<>chosen_date
          OR x.visit_start<moment+make_interval(mins=>p.minimum_notice_minutes)
          OR x.busy_start<moment OR x.busy_end>moment+make_interval(hours=>24*p.horizon_days)
          OR NOT platform.scheduling_contains(ws,business,r.id,r.timezone,tstzrange(x.busy_start,x.busy_end,'[)'))
          OR EXISTS(SELECT 1 FROM platform.scheduling_active_allocations(ws,business,r.id,moment) a
            WHERE a.occupied && tstzrange(x.busy_start,x.busy_end,'[)')))
        THEN RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P3101'; END IF;

      INSERT INTO app.availability_offers(workspace_id,business_id,resource_id,client_id,
        conversation_id,request_id,quote_id,order_id,session_id,service_id,policy_id,schedule_version,
        local_date,requested_date,timezone,occupied_minutes,duration_reference_id,terms_sha256,deposit,
        command_key,issued_at,expires_at)
      VALUES(ws,business,r.id,q.client_id,q.conversation_id,q.request_id,q.id,
        (p_selection->>'order_id')::uuid,session,p.service_id,p.id,r.schedule_version,
        chosen_date,p_day,r.timezone,minutes,duration_ref,q.terms_sha256,q.material->'deposit',
        p_key,moment,moment+make_interval(mins=>p.offer_ttl_minutes))
      RETURNING * INTO offer;
      INSERT INTO app.availability_options(workspace_id,business_id,offer_id,visit_start,visit_end,busy_start,busy_end)
        SELECT ws,business,offer.id,x.* FROM jsonb_to_recordset(p_options) x(
          visit_start timestamptz,visit_end timestamptz,busy_start timestamptz,busy_end timestamptz);
      RETURN platform.scheduling_offer_view(offer);
    END $$""",
    "platform.scheduling_hold_view(app.reservation_holds,timestamptz)": r"""CREATE FUNCTION platform.scheduling_hold_view(
      h app.reservation_holds,moment timestamptz
    ) RETURNS jsonb LANGUAGE sql STABLE SET search_path=pg_catalog,pg_temp AS $$
      SELECT jsonb_build_object(
        'outcome',CASE WHEN a.release_reason IS NOT NULL THEN a.release_reason
          WHEN h.expires_at<=moment THEN 'EXPIRED' ELSE 'HELD' END,
        'hold_id',h.id,'allocation_id',h.allocation_id,'expires_at',h.expires_at,
        'visit_start',o.visit_start,'visit_end',o.visit_end,'timezone',f.timezone)
      FROM app.resource_allocations a
      JOIN app.availability_options o ON (o.workspace_id,o.business_id,o.id)=(h.workspace_id,h.business_id,h.option_id)
      JOIN app.availability_offers f ON (f.workspace_id,f.business_id,f.id)=(o.workspace_id,o.business_id,o.offer_id)
      WHERE (a.workspace_id,a.business_id,a.id)=(h.workspace_id,h.business_id,h.allocation_id)
    $$""",
    "platform.scheduling_client_command(jsonb,uuid,uuid,text,uuid,text,boolean)": r"""CREATE FUNCTION platform.scheduling_client_command(
      p_selection jsonb,p_client uuid,p_conversation uuid,p_action text,p_target uuid,p_key text,p_eligible boolean
    ) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    DECLARE business uuid:=(p_selection->>'business_id')::uuid;
      session uuid:=(p_selection->>'session_id')::uuid;
      ws uuid:=platform.scheduling_owner_scope(business,'schedule');
      q app.quotes%ROWTYPE:=platform.scheduling_agreement(ws,p_selection);
      r app.scheduling_resources%ROWTYPE; p app.scheduling_policy_revisions%ROWTYPE;
      offer app.availability_offers%ROWTYPE; option_row app.availability_options%ROWTYPE;
      hold app.reservation_holds%ROWTYPE; prior platform.scheduling_command_receipts%ROWTYPE;
      moment timestamptz; occupied_range tstzrange; allocation uuid;
      request jsonb:=jsonb_build_object('id',p_target); response jsonb;
    BEGIN
      -- M7.1B is called by an authenticated application transaction with a
      -- separate trusted client identity. Never treat the option ID as identity.
      IF current_database() NOT IN ('asm_local','asm_test')
        THEN RAISE EXCEPTION 'ACCESS_DENIED' USING ERRCODE='P3101'; END IF;
      IF (p_client,p_conversation) IS DISTINCT FROM (q.client_id,q.conversation_id)
        THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P3101'; END IF;
      IF p_action IS NULL OR p_action NOT IN ('state','select','release') OR p_target IS NULL OR
        (p_action<>'state' AND (p_key IS NULL OR p_key !~ '^[A-Za-z0-9._:-]{1,128}$'))
        THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P3101'; END IF;

      SELECT * INTO r FROM app.scheduling_resources
        WHERE (workspace_id,business_id)=(ws,business) FOR UPDATE;
      moment:=clock_timestamp();
      IF r.id IS NULL THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P3101'; END IF;

      IF p_action<>'state' THEN
        SELECT * INTO prior FROM platform.scheduling_command_receipts c
          WHERE (c.workspace_id,c.business_id,c.subject_kind,c.subject_id,c.command_key)
            =(ws,business,'CLIENT',session,p_key);
        IF FOUND THEN
          IF (p_action,request) IS DISTINCT FROM (prior.action,prior.payload)
            THEN RAISE EXCEPTION 'IDEMPOTENCY_KEY_CONFLICT' USING ERRCODE='P3101'; END IF;
          IF NOT (prior.result ? 'hold_id') THEN RETURN prior.result; END IF;
          SELECT * INTO STRICT hold FROM app.reservation_holds h
            WHERE (h.workspace_id,h.business_id,h.id,h.session_id)
              =(ws,business,(prior.result->>'hold_id')::uuid,session);
          RETURN platform.scheduling_hold_view(hold,moment);
        END IF;
      END IF;

      IF p_action='release' THEN
        SELECT * INTO hold FROM app.reservation_holds h
          WHERE (h.workspace_id,h.business_id,h.id,h.session_id,h.resource_id)
            =(ws,business,p_target,session,r.id);
        IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P3101'; END IF;
        UPDATE app.resource_allocations
          SET released_at=moment,release_reason=CASE WHEN hold.expires_at<=moment THEN 'EXPIRED' ELSE 'RELEASED' END
          WHERE (workspace_id,business_id,id)=(ws,business,hold.allocation_id) AND released_at IS NULL;
        response:=platform.scheduling_hold_view(hold,moment);
      ELSE
        SELECT o.* INTO option_row FROM app.availability_options o
          JOIN app.availability_offers f ON (f.workspace_id,f.business_id,f.id)=(o.workspace_id,o.business_id,o.offer_id)
          WHERE (o.workspace_id,o.business_id,o.id)=(ws,business,p_target)
            AND (f.resource_id,f.session_id,f.client_id,f.conversation_id,f.request_id,f.quote_id,f.order_id)
              =(r.id,session,q.client_id,q.conversation_id,q.request_id,q.id,(p_selection->>'order_id')::uuid);
        IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P3101'; END IF;
        SELECT f.* INTO STRICT offer FROM app.availability_offers f
          WHERE (f.workspace_id,f.business_id,f.id)=(ws,business,option_row.offer_id);
        IF p_action='state' THEN RETURN jsonb_build_object(
          'schedule',platform.scheduling_snapshot(ws,business,offer.service_id,offer.local_date,moment),
          'terms',q.material,'option',jsonb_build_object('option_id',option_row.id,
            'visit_start',option_row.visit_start,'visit_end',option_row.visit_end,
            'busy_start',option_row.busy_start,'busy_end',option_row.busy_end)); END IF;

        SELECT * INTO hold FROM app.reservation_holds h
          WHERE (h.workspace_id,h.business_id,h.option_id)=(ws,business,option_row.id);
        IF FOUND THEN
          response:=platform.scheduling_hold_view(hold,moment);
        ELSE
          SELECT rev.* INTO p FROM app.scheduling_policy_activations a JOIN app.scheduling_policy_revisions rev
            ON (rev.workspace_id,rev.business_id,rev.resource_id,rev.service_id,rev.id)
              =(a.workspace_id,a.business_id,a.resource_id,a.service_id,a.policy_id)
            WHERE (a.workspace_id,a.business_id,a.resource_id,a.service_id)=(ws,business,r.id,offer.service_id);
          occupied_range:=tstzrange(option_row.busy_start,option_row.busy_end,'[)');
          IF p_eligible IS NOT TRUE OR moment>=offer.expires_at OR p.id IS DISTINCT FROM offer.policy_id
            OR r.timezone<>offer.timezone OR q.terms_sha256<>offer.terms_sha256
            OR (q.material->>'occupied_minutes',q.material->>'duration_reference_id') IS DISTINCT FROM
              (offer.occupied_minutes::text,offer.duration_reference_id::text)
            OR option_row.visit_start<moment+make_interval(mins=>p.minimum_notice_minutes)
            OR option_row.busy_start<moment OR option_row.busy_end>moment+make_interval(hours=>24*p.horizon_days)
            OR NOT platform.scheduling_contains(ws,business,r.id,r.timezone,occupied_range)
            OR EXISTS(SELECT 1 FROM platform.scheduling_command_receipts c
              WHERE (c.workspace_id,c.business_id,c.subject_kind,c.subject_id,c.action,c.payload->>'id')
                =(ws,business,'CLIENT',session,'select',p_target::text) AND NOT (c.result ? 'hold_id'))
            THEN response:=jsonb_build_object('outcome','OPTION_UNAVAILABLE');
          ELSE
            PERFORM platform.scheduling_expire_holds(ws,business,r.id,occupied_range,session,moment);
            IF EXISTS(SELECT 1 FROM app.resource_allocations a
              WHERE (a.workspace_id,a.business_id,a.session_id)=(ws,business,session)
                AND a.kind='HOLD' AND a.released_at IS NULL)
              THEN response:=jsonb_build_object('outcome','SESSION_HELD');
            ELSIF EXISTS(SELECT 1 FROM app.resource_allocations a
              WHERE (a.workspace_id,a.business_id,a.resource_id)=(ws,business,r.id)
                AND a.released_at IS NULL AND a.occupied && occupied_range)
              THEN response:=jsonb_build_object('outcome','OPTION_UNAVAILABLE');
            ELSE
              INSERT INTO app.resource_allocations(workspace_id,business_id,resource_id,kind,session_id,occupied,created_at)
                VALUES(ws,business,r.id,'HOLD',session,occupied_range,moment) RETURNING id INTO allocation;
              INSERT INTO app.reservation_holds(workspace_id,business_id,resource_id,option_id,session_id,allocation_id,created_at,expires_at)
                VALUES(ws,business,r.id,option_row.id,session,allocation,moment,moment+make_interval(mins=>p.hold_ttl_minutes))
                RETURNING * INTO hold;
              response:=platform.scheduling_hold_view(hold,moment);
            END IF;
          END IF;
        END IF;
      END IF;

      INSERT INTO platform.scheduling_command_receipts(workspace_id,business_id,resource_id,subject_kind,
        subject_id,command_key,action,payload,result,recorded_at)
        VALUES(ws,business,r.id,'CLIENT',session,p_key,p_action,request,response,moment);
      RETURN response;
    END $$""",
    "platform.scheduling_owner_block(uuid,text,timestamptz,timestamptz,uuid)": r"""CREATE FUNCTION platform.scheduling_owner_block(
      business uuid,p_key text,p_start timestamptz,p_end timestamptz,p_block uuid
    ) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    DECLARE ws uuid:=platform.scheduling_owner_scope(business,'schedule');
      actor uuid:=nullif(current_setting('asm.actor_id',true),'')::uuid;
      resource uuid; block app.resource_allocations%ROWTYPE; prior platform.scheduling_command_receipts%ROWTYPE;
      moment timestamptz; target tstzrange; affected jsonb; response jsonb; request jsonb; operation text;
    BEGIN
      IF p_key IS NULL OR p_key !~ '^[A-Za-z0-9._:-]{1,128}$' OR
        (CASE WHEN p_block IS NULL THEN p_start IS NULL OR p_end IS NULL OR
          NOT isfinite(p_start) OR NOT isfinite(p_end) OR p_start>=p_end
        ELSE p_start IS NOT NULL OR p_end IS NOT NULL END)
        THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P3101'; END IF;
      SELECT id INTO resource FROM app.scheduling_resources
        WHERE (workspace_id,business_id)=(ws,business) FOR UPDATE;
      IF NOT FOUND THEN RAISE EXCEPTION 'NEEDS_CLARIFICATION' USING ERRCODE='P3101'; END IF;
      moment:=clock_timestamp();
      IF p_block IS NULL THEN
        operation:='block';
        request:=jsonb_build_object('start',p_start,'end',p_end);
      ELSE
        operation:='unblock';
        request:=jsonb_build_object('id',p_block);
      END IF;
      SELECT * INTO prior FROM platform.scheduling_command_receipts c
        WHERE (c.workspace_id,c.business_id,c.subject_kind,c.subject_id,c.command_key)
          =(ws,business,'OWNER',actor,p_key);
      IF FOUND THEN
        IF (operation,request) IS DISTINCT FROM (prior.action,prior.payload)
          THEN RAISE EXCEPTION 'IDEMPOTENCY_KEY_CONFLICT' USING ERRCODE='P3101'; END IF;
        IF prior.result ? 'block_id' THEN
          SELECT a.* INTO STRICT block FROM app.resource_allocations a WHERE
            (a.workspace_id,a.business_id,a.resource_id,a.id,a.kind)
              =(ws,business,resource,(prior.result->>'block_id')::uuid,'BLOCK');
        ELSE RETURN prior.result;
        END IF;
      ELSIF p_block IS NOT NULL THEN
        UPDATE app.resource_allocations SET released_at=coalesce(released_at,moment),release_reason='RELEASED'
          WHERE (workspace_id,business_id,resource_id,id,kind)=(ws,business,resource,p_block,'BLOCK')
          RETURNING * INTO block;
        IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P3101'; END IF;
      ELSE
        IF p_start<moment THEN RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P3101'; END IF;
        target:=tstzrange(p_start,p_end,'[)');
        PERFORM platform.scheduling_expire_holds(ws,business,resource,target,NULL,moment);
        SELECT jsonb_agg(jsonb_build_object('kind',a.kind,'id',coalesce(h.id,a.id)) ORDER BY a.id)
          INTO affected FROM app.resource_allocations a LEFT JOIN app.reservation_holds h
            ON (h.workspace_id,h.business_id,h.allocation_id)=(a.workspace_id,a.business_id,a.id)
          WHERE (a.workspace_id,a.business_id,a.resource_id)=(ws,business,resource)
            AND a.released_at IS NULL AND a.occupied && target;
        IF affected IS NULL THEN
          INSERT INTO app.resource_allocations(workspace_id,business_id,resource_id,kind,occupied,created_at)
            VALUES(ws,business,resource,'BLOCK',target,moment) RETURNING * INTO block;
        ELSE response:=jsonb_build_object('outcome','CALENDAR_CONFLICT','affected',affected);
        END IF;
      END IF;
      IF block.id IS NOT NULL THEN
        response:=jsonb_build_object('outcome',CASE WHEN block.released_at IS NULL THEN 'BLOCKED' ELSE 'RELEASED' END,
          'block_id',block.id,'start',lower(block.occupied),'end',upper(block.occupied));
      END IF;
      IF prior.command_key IS NULL THEN
        INSERT INTO platform.scheduling_command_receipts(workspace_id,business_id,resource_id,subject_kind,
          subject_id,command_key,action,payload,result,recorded_at)
          VALUES(ws,business,resource,'OWNER',actor,p_key,operation,request,response,moment);
      END IF;
      RETURN response;
    END $$""",
}

RUNTIME_FUNCTIONS = {
    "platform.scheduling_owner_read(uuid,text,date)",
    "platform.scheduling_owner_offer(jsonb,text,date,text,jsonb)",
    "platform.scheduling_client_command(jsonb,uuid,uuid,text,uuid,text,boolean)",
    "platform.scheduling_owner_block(uuid,text,timestamptz,timestamptz,uuid)",
}


OWNER_READ = "platform.scheduling_owner_read(uuid,text,date)"
SNAPSHOT = "platform.scheduling_snapshot(uuid,uuid,text,date,timestamptz)"
PREVIOUS_PROFILE = "platform.scheduling_availability_schema_profile()"
THIS_PROFILE = "platform.scheduling_hold_schema_profile()"
NONFUNCTION_SHA256 = "aaee2b7f8bf6f434abeaa37058d2b048fd1e534c9e4421fa68116da2d568024b"
PROFILE_CALLERS = (
    "platform.ai_provider_session(jsonb,boolean)",
    "platform.human_context_policy_command(uuid,uuid,text,text,text,bigint,jsonb,jsonb)",
)

IMMUTABLE_TABLES = ("app.availability_offers", "app.availability_options", "app.reservation_holds")


def snapshot_sql(prior) -> str:
    return (
        prior.FUNCTIONS[OWNER_READ]
        .replace("platform.scheduling_owner_read(", "platform.scheduling_snapshot(")
        .replace(
            "p_business uuid,p_service text,p_date date",
            "ws uuid,p_business uuid,p_service text,p_date date,now_at timestamptz",
        )
        .replace("SECURITY DEFINER ", "")
        .replace(
            "    DECLARE ws uuid:=platform.scheduling_owner_scope(p_business,p_service); now_at timestamptz;\n",
            "",
        )
        .replace("      now_at:=clock_timestamp();\n", "")
        .replace(
            "          'policy',",
            """          'occupancy',coalesce((
            SELECT jsonb_agg(jsonb_build_object('busy_start',lower(a.occupied),
              'busy_end',upper(a.occupied)) ORDER BY lower(a.occupied))
            FROM platform.scheduling_active_allocations(ws,p_business,s.id,now_at) a
            WHERE a.occupied && tstzrange(
              (s.local_date::timestamp AT TIME ZONE s.timezone)-interval '24 hours',
              ((s.local_date+1)::timestamp AT TIME ZONE s.timezone)+interval '24 hours','[)')
          ),'[]'::jsonb),
          'policy',""",
        )
    )


def callers_sql(prior, profile: str, schema: str) -> tuple[str, ...]:
    return tuple(
        sql.replace("platform.service_intent_schema_profile()", profile).replace("'0031'", schema)
        for sql in prior.PREVIOUS_PROFILE_CALLERS
    )


def profile_sql(prior, functions: dict[str, str]) -> str:
    # Retain the already attested projection and fingerprints for every
    # unchanged 0032 object. Add the new inventory and pin the new digest.
    replacements = dict(
        zip(PROFILE_CALLERS, callers_sql(prior, THIS_PROFILE, "'0033'"), strict=True)
    )
    additions = functions | replacements | {PREVIOUS_PROFILE: prior.PROFILE}
    profile = prior.PROFILE.replace(PREVIOUS_PROFILE, THIS_PROFILE)
    for signature in additions:
        profile = re.sub(r"\('" + re.escape(signature) + r"',[^\n]+\),\n", "", profile)
    expected = []
    for signature, sql in sorted(additions.items()):
        header, body, _ = sql.split("$$")
        digest = hashlib.sha256(body.encode()).hexdigest()
        language = "plpgsql" if "LANGUAGE plpgsql" in header else "sql"
        definer = str("SECURITY DEFINER" in header).lower()
        volatility = "s" if " STABLE " in header else "v"
        runtime = str(signature in RUNTIME_FUNCTIONS).lower()
        expected.append(
            f"('{signature}','{digest}','{language}',{definer},'{volatility}',{runtime})"
        )
    profile = profile.replace(" AS (VALUES ", " AS (VALUES " + ",\n".join(expected) + ",\n", 1)
    columns = []
    for table, table_sql in TABLES.items():
        names = re.findall(
            r"(?:\(|,)\s*([a-z_][a-z_0-9]*)\s+(?:uuid|text|integer|bigint|timestamptz|date|jsonb|tstzrange)\b",
            table_sql,
        )
        array = ",".join(f"'{name}'" for name in names)
        columns.append(f"('{table}',ARRAY[{array}]::text[])")
    profile = profile.replace(
        "columns_expected(table_name,column_names) AS (VALUES ",
        "columns_expected(table_name,column_names) AS (VALUES " + ",\n".join(columns) + ",\n",
        1,
    )
    entirely_new = len(functions.keys() - prior.FUNCTIONS.keys()) + 1
    profile = profile.replace("FROM functions)=416", f"FROM functions)={416 + entirely_new}")
    profile = profile.replace("FROM expected)=415", f"FROM expected)={415 + entirely_new}")
    profile = profile.replace("FROM tables)=91", f"FROM tables)={91 + len(TABLES)}")
    profile = profile.replace(
        "FROM tables WHERE name IN (",
        "FROM tables WHERE name IN (" + ",".join(f"'{table}'" for table in TABLES) + ",",
    )
    return profile.replace("'0032'", "'0033'").replace(
        "b31332ca0d1cfb8298e6955cac0bb686746c3a6d7a2708a7de50b9a4f81fc728", NONFUNCTION_SHA256
    )


def previous_scheduling():
    scripts = op.get_context().script
    if scripts is None:
        # Operations can execute a revision directly without an Alembic
        # EnvironmentContext. Locate the same registered predecessor then.
        from pathlib import Path

        from alembic.script import ScriptDirectory

        scripts = ScriptDirectory(str(Path(__file__).resolve().parents[1]))
    return scripts.get_revision(down_revision).module


def upgrade() -> None:
    prior = previous_scheduling()
    for table, sql in TABLES.items():
        op.execute(sql)
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY scheduling_migrator ON {table} TO asm_migrator USING(true) WITH CHECK(true)"
        )
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC,asm_runtime")
    for sql in INDEXES:
        op.execute(sql)
    functions = FUNCTIONS | {SNAPSHOT: snapshot_sql(prior)}
    for signature, sql in functions.items():
        op.execute(sql)
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC,asm_runtime")
        if signature in RUNTIME_FUNCTIONS:
            op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO asm_runtime")
    for table in IMMUTABLE_TABLES:
        op.execute(
            f"CREATE TRIGGER scheduling_fact_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION platform.scheduling_fact_immutable()"
        )
    op.execute("""CREATE TRIGGER scheduling_calendar_protected AFTER UPDATE ON app.scheduling_resources
      FOR EACH ROW EXECUTE FUNCTION platform.scheduling_calendar_protected()""")
    for sql in callers_sql(prior, THIS_PROFILE, "'0033'"):
        op.execute(sql)
    op.execute(profile_sql(prior, functions))
    op.execute(f"REVOKE ALL ON FUNCTION {THIS_PROFILE} FROM PUBLIC,asm_runtime")


def downgrade() -> None:
    prior = previous_scheduling()
    op.execute(f"LOCK TABLE {','.join(TABLES)} IN ACCESS EXCLUSIVE MODE")
    durable = " OR ".join(f"EXISTS(SELECT 1 FROM {table})" for table in TABLES)
    op.execute(f"""DO $$ BEGIN
      IF {durable} THEN RAISE EXCEPTION 'SCHEDULING_HOLDS_DURABLE_DATA' USING ERRCODE='55000'; END IF;
    END $$""")
    for sql in callers_sql(prior, PREVIOUS_PROFILE, "'0032'"):
        op.execute(sql)
    op.execute(f"DROP FUNCTION {THIS_PROFILE}")
    op.execute("DROP TRIGGER scheduling_calendar_protected ON app.scheduling_resources")
    for table in IMMUTABLE_TABLES:
        op.execute(f"DROP TRIGGER scheduling_fact_immutable ON {table}")
    op.execute(
        prior.FUNCTIONS[OWNER_READ].replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
    )
    op.execute(f"DROP FUNCTION {SNAPSHOT}")
    for signature in reversed(FUNCTIONS):
        if signature != OWNER_READ:
            op.execute(f"DROP FUNCTION {signature}")
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE {table}")
