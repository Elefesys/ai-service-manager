"""Owner-confirmed service request drafts from a current intake projection."""

from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None

TABLES = {
    "app.service_requests": r"""CREATE TABLE app.service_requests (
      workspace_id uuid NOT NULL,
      id uuid NOT NULL DEFAULT uuidv7(),
      business_id uuid NOT NULL,
      conversation_id uuid NOT NULL,
      client_id uuid NOT NULL,
      intent_message_id uuid NOT NULL,
      intent_source_version text NOT NULL CHECK(intent_source_version ~ '^[a-f0-9]{64}$'),
      release_id uuid NOT NULL,
      service_id text NOT NULL CHECK(service_id ~ '^[a-z][a-z0-9_-]{0,39}$'),
      service_name text NOT NULL CHECK(char_length(service_name) BETWEEN 1 AND 100),
      template_revision text NOT NULL CHECK(template_revision='tattoo_intake_v1'),
      state text NOT NULL DEFAULT 'DRAFT' CHECK(state='DRAFT'),
      revision bigint NOT NULL DEFAULT 1 CHECK(revision>0),
      facts jsonb NOT NULL CHECK(jsonb_typeof(facts)='array' AND octet_length(facts::text)<=8192),
      missing jsonb NOT NULL CHECK(jsonb_typeof(missing)='array' AND octet_length(missing::text)<=256),
      conflicts jsonb NOT NULL CHECK(jsonb_typeof(conflicts)='array' AND octet_length(conflicts::text)<=256),
      question text CHECK(question IS NULL OR char_length(question) BETWEEN 1 AND 300),
      created_at timestamptz NOT NULL DEFAULT clock_timestamp() CHECK(isfinite(created_at)),
      PRIMARY KEY(workspace_id,id),
      UNIQUE(workspace_id,conversation_id,intent_message_id),
      FOREIGN KEY(workspace_id,conversation_id,client_id)
        REFERENCES app.conversations(workspace_id,id,client_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,intent_message_id)
        REFERENCES app.messages(workspace_id,id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,business_id,release_id)
        REFERENCES platform.business_configuration_releases(workspace_id,business_id,id) ON DELETE RESTRICT
    )""",
    "platform.service_request_receipts": r"""CREATE TABLE platform.service_request_receipts (
      workspace_id uuid NOT NULL,
      actor_user_account_id uuid NOT NULL,
      command_key text NOT NULL CHECK(command_key ~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$'),
      correlation_id uuid NOT NULL,
      request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32),
      request_id uuid NOT NULL,
      accepted_revision bigint NOT NULL CHECK(accepted_revision>0),
      effect text NOT NULL CHECK(effect IN ('CREATE','REVISE','OPEN')),
      recorded_at timestamptz NOT NULL DEFAULT clock_timestamp() CHECK(isfinite(recorded_at)),
      PRIMARY KEY(workspace_id,actor_user_account_id,command_key),
      FOREIGN KEY(workspace_id,actor_user_account_id)
        REFERENCES platform.workspace_memberships(workspace_id,user_account_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,request_id)
        REFERENCES app.service_requests(workspace_id,id) ON DELETE RESTRICT,
      CHECK((effect='CREATE' AND accepted_revision=1)
        OR (effect='REVISE' AND accepted_revision>1) OR effect='OPEN')
    )""",
}

FUNCTIONS = {
    "platform.service_request_owner_scope(uuid,uuid)": r"""CREATE FUNCTION platform.service_request_owner_scope(
      p_business uuid,p_conversation uuid
    ) RETURNS app.conversations
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    DECLARE ws uuid; scope app.conversations%ROWTYPE;
    BEGIN
      BEGIN
        ws:=platform.knowledge_owner_lock(p_business);
      EXCEPTION WHEN SQLSTATE 'P2801' THEN
        RAISE EXCEPTION '%',SQLERRM USING ERRCODE='P3101';
      END;
      -- Match intake_owner and the worker: configuration, channel, conversation.
      PERFORM 1 FROM app.channel_connections cc
        JOIN app.conversations c ON (c.workspace_id,c.connection_id,c.business_id)
          =(cc.workspace_id,cc.id,cc.business_id)
        WHERE (c.workspace_id,c.business_id,c.id)=(ws,p_business,p_conversation)
        FOR SHARE OF cc;
      IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P3101'; END IF;
      SELECT c.* INTO scope FROM app.conversations c
        WHERE (c.workspace_id,c.business_id,c.id)=(ws,p_business,p_conversation)
        FOR NO KEY UPDATE;
      IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P3101'; END IF;
      RETURN scope;
    END $$""",
    "platform.service_request_owner_create(uuid,uuid,text,jsonb)": r"""CREATE FUNCTION platform.service_request_owner_create(
      p_business uuid,p_conversation uuid,p_key text,p_request jsonb
    ) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    <<create_draft>>
    DECLARE
      scope app.conversations%ROWTYPE;
      draft app.service_requests%ROWTYPE; receipt platform.service_request_receipts%ROWTYPE;
      anchor app.messages%ROWTYPE; next_anchor app.messages%ROWTYPE;
      actor uuid; request_fingerprint bytea;
      projection jsonb; service jsonb; release_id uuid; fields jsonb; start_source jsonb;
      fact jsonb; facts jsonb; missing jsonb; conflicts jsonb; question text; effect text;
    BEGIN
      scope:=platform.service_request_owner_scope(p_business,p_conversation);
      actor:=nullif(current_setting('asm.actor_id',true),'')::uuid;
      IF p_key IS NULL OR p_key !~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$'
        OR octet_length(p_request::text)>4096
        OR platform.material_object(p_request,ARRAY[
          'expected_version','expected_fingerprint','intent_source','fields','selection'
        ]) IS NOT TRUE
        OR platform.human_context_decimal(p_request->'expected_version',false) IS NOT TRUE
        OR jsonb_typeof(p_request->'expected_fingerprint') IS DISTINCT FROM 'string'
        OR (p_request->>'expected_fingerprint' ~ '^[a-f0-9]{64}$') IS NOT TRUE
        OR (p_request->>'selection' IN ('ONE_WORK','UNCLEAR')) IS NOT TRUE THEN
        RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P3101';
      END IF;
      fields:=p_request->'fields';
      start_source:=p_request->'intent_source';
      IF jsonb_typeof(fields) IS DISTINCT FROM 'array'
        OR platform.material_object(start_source,ARRAY['message_id','source_version']) IS NOT TRUE
        OR platform.human_context_uuid(start_source->'message_id') IS NOT TRUE
        OR jsonb_typeof(start_source->'source_version') IS DISTINCT FROM 'string'
        OR (start_source->>'source_version' ~ '^[a-f0-9]{64}$') IS NOT TRUE THEN
        RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P3101';
      END IF;
      IF jsonb_array_length(fields)>5 OR EXISTS(
        SELECT 1 FROM jsonb_array_elements(fields) AS f(value)
        WHERE f.value NOT IN ('"idea"','"placement"','"approximate_size"','"style"','"references"')
      ) OR (SELECT count(DISTINCT value) FROM jsonb_array_elements(fields))<>jsonb_array_length(fields) THEN
        RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P3101';
      END IF;

      -- Serialize technical keys across all of this owner's conversations.
      PERFORM pg_advisory_xact_lock(hashtextextended(
        scope.workspace_id::text||':'||actor::text||':'||p_key||'|SERVICE_REQUEST_V1',2025));
      request_fingerprint:=sha256(convert_to(
        jsonb_build_array(scope.business_id,scope.id,scope.client_id,p_request)::text,'UTF8'));
      SELECT r.* INTO receipt FROM platform.service_request_receipts r
        WHERE (r.workspace_id,r.actor_user_account_id,r.command_key)=(scope.workspace_id,actor,p_key);
      IF FOUND THEN
        IF receipt.request_fingerprint IS DISTINCT FROM request_fingerprint THEN
          RAISE EXCEPTION 'IDEMPOTENCY_KEY_CONFLICT' USING ERRCODE='P3101';
        END IF;
        IF NOT EXISTS(
          SELECT 1 FROM app.service_requests d
            WHERE (d.workspace_id,d.id,d.business_id,d.conversation_id,d.client_id)
              =(scope.workspace_id,receipt.request_id,scope.business_id,scope.id,scope.client_id)
        ) THEN
          RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P3101';
        END IF;
        RETURN jsonb_build_object('request_id',receipt.request_id);
      END IF;
      IF p_request->>'selection'='UNCLEAR' THEN
        RAISE EXCEPTION 'NEEDS_CLARIFICATION' USING ERRCODE='P3101';
      END IF;

      projection:=platform.intake_project(scope.workspace_id,p_business,p_conversation,scope.client_id);
      IF p_request->>'expected_version' IS DISTINCT FROM projection->>'version'
        OR p_request->>'expected_fingerprint' IS DISTINCT FROM projection->>'fingerprint' THEN
        RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P3101';
      END IF;
      IF projection->>'category' IN ('FAQ_ONLY','AMBIGUOUS')
        OR projection->>'service_id' IS NULL OR projection->>'template_revision' IS NULL THEN
        RAISE EXCEPTION 'NEEDS_CLARIFICATION' USING ERRCODE='P3101';
      END IF;
      release_id:=(projection->>'release_id')::uuid;
      SELECT s.value INTO service
        FROM platform.business_configuration_state active
        JOIN platform.business_configuration_releases published
          ON (published.workspace_id,published.business_id,published.id)
            =(active.workspace_id,active.business_id,active.active_release_id)
        CROSS JOIN LATERAL jsonb_array_elements(published.body->'services') s(value)
        WHERE (active.workspace_id,active.business_id,active.active_release_id)
            =(scope.workspace_id,scope.business_id,release_id)
          AND s.value->>'id'=projection->>'service_id' AND s.value->>'active'='true';
      IF platform.intake_template(service) IS NOT TRUE THEN
        RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P3101';
      END IF;

      SELECT m.* INTO anchor FROM app.messages m
        WHERE (m.workspace_id,m.conversation_id,m.connection_id,m.id)
          =(scope.workspace_id,scope.id,scope.connection_id,(start_source->>'message_id')::uuid)
          AND m.direction='INBOUND';
      IF NOT FOUND OR NOT EXISTS(
        SELECT 1 FROM jsonb_array_elements(projection->'sources') AS s(value)
        WHERE s.value->'message_id'=start_source->'message_id'
          AND s.value->'source_version'=start_source->'source_version'
      ) OR platform.intake_source_current(
        scope.workspace_id,scope.business_id,scope.id,scope.client_id,start_source
      ) IS NOT TRUE THEN
        RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P3101';
      END IF;
      -- A separate confirmed start is an upper bound on the current work.
      SELECT m.* INTO next_anchor FROM app.service_requests d
        JOIN app.messages m ON (m.workspace_id,m.id)=(d.workspace_id,d.intent_message_id)
        WHERE (d.workspace_id,d.business_id,d.conversation_id,d.client_id)
          =(scope.workspace_id,scope.business_id,scope.id,scope.client_id)
          AND (m.created_at,m.id)>(anchor.created_at,anchor.id)
        ORDER BY m.created_at,m.id LIMIT 1;

      SELECT coalesce(jsonb_agg(f.value ORDER BY f.value->>'field'),'[]') INTO facts
        FROM jsonb_array_elements(projection->'facts') f(value)
        WHERE fields ? (f.value->>'field');
      IF jsonb_array_length(facts)<>jsonb_array_length(fields) THEN
        RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P3101';
      END IF;
      FOR fact IN SELECT value FROM jsonb_array_elements(facts) LOOP
        IF platform.intake_source_current(
          scope.workspace_id,scope.business_id,scope.id,scope.client_id,fact->'source'
        ) IS NOT TRUE THEN
          RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P3101';
        END IF;
        IF NOT EXISTS (
          SELECT 1 FROM app.messages m
          WHERE (m.workspace_id,m.conversation_id,m.id)
            =(scope.workspace_id,scope.id,(fact->'source'->>'message_id')::uuid)
            AND (m.created_at,m.id)>=(anchor.created_at,anchor.id)
            AND (next_anchor.id IS NULL OR (m.created_at,m.id)<(next_anchor.created_at,next_anchor.id))
        ) THEN
          RAISE EXCEPTION 'NEEDS_CLARIFICATION' USING ERRCODE='P3101';
        END IF;
      END LOOP;
      -- Record the source identity, including image analysis pins, without its quoted text.
      SELECT coalesce(jsonb_agg(jsonb_set(f.value,'{source,quote}','""') ORDER BY f.ordinal),'[]')
        INTO facts FROM jsonb_array_elements(facts) WITH ORDINALITY f(value,ordinal);
      SELECT coalesce(jsonb_agg(f.value->>'id' ORDER BY f.ordinal),'[]') INTO missing
        FROM jsonb_array_elements(service->'intake_fields') WITH ORDINALITY f(value,ordinal)
        WHERE f.value->>'required'='true' AND NOT EXISTS(
          SELECT 1 FROM jsonb_array_elements(facts) v(value) WHERE v.value->>'field'=f.value->>'id'
            AND v.value->>'status' IN ('client-stated','owner-confirmed')
            AND v.value->>'conflict'='false');
      SELECT coalesce(jsonb_agg(f.value->>'field' ORDER BY f.ordinal),'[]') INTO conflicts
        FROM jsonb_array_elements(facts) WITH ORDINALITY f(value,ordinal)
        WHERE f.value->>'conflict'='true';
      question:=CASE
        WHEN projection->>'status'='OWNER_HANDOFF' THEN projection->>'question'
        WHEN jsonb_array_length(conflicts)>0 THEN 'Уточните противоречивое поле: '||(conflicts->>0)||'.'
        ELSE CASE missing->>0
          WHEN 'idea' THEN 'Какую идею или сюжет вы хотите?'
          WHEN 'placement' THEN 'На каком месте тела вы хотите татуировку?'
          WHEN 'approximate_size' THEN 'Какой примерный размер вы представляете, в сантиметрах?'
          WHEN 'style' THEN 'Какой стиль вам нравится?'
        END
      END;

      SELECT d.* INTO draft FROM app.service_requests d
        WHERE (d.workspace_id,d.business_id,d.conversation_id,d.client_id,d.intent_message_id)
          =(scope.workspace_id,scope.business_id,scope.id,scope.client_id,anchor.id)
        FOR NO KEY UPDATE;
      IF NOT FOUND THEN
        INSERT INTO app.service_requests
          (workspace_id,business_id,conversation_id,client_id,intent_message_id,intent_source_version,
           release_id,service_id,service_name,template_revision,facts,missing,conflicts,question)
          VALUES(scope.workspace_id,scope.business_id,scope.id,scope.client_id,anchor.id,
            start_source->>'source_version',release_id,service->>'id',service->>'name',
            projection->>'template_revision',facts,missing,conflicts,question)
          RETURNING * INTO draft;
        effect:='CREATE';
      ELSIF draft.service_id<>service->>'id' THEN
        RAISE EXCEPTION 'NEEDS_CLARIFICATION' USING ERRCODE='P3101';
      ELSIF (draft.intent_source_version,draft.release_id,draft.service_name,draft.template_revision,
          draft.facts,draft.missing,draft.conflicts,draft.question) IS DISTINCT FROM
        (start_source->>'source_version',release_id,service->>'name',projection->>'template_revision',
          facts,missing,conflicts,question) THEN
        IF draft.revision=9223372036854775807 THEN
          RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P3101';
        END IF;
        -- Qualify local values to distinguish them from the draft columns.
        UPDATE app.service_requests d
          SET (intent_source_version,release_id,service_name,template_revision,facts,missing,
            conflicts,question,revision)=(start_source->>'source_version',create_draft.release_id,
            service->>'name',projection->>'template_revision',create_draft.facts,create_draft.missing,
            create_draft.conflicts,create_draft.question,d.revision+1)
          WHERE (d.workspace_id,d.id)=(draft.workspace_id,draft.id)
          RETURNING d.* INTO draft;
        effect:='REVISE';
      ELSE
        effect:='OPEN';
      END IF;
      INSERT INTO platform.service_request_receipts
        (workspace_id,actor_user_account_id,command_key,correlation_id,request_fingerprint,
         request_id,accepted_revision,effect)
        VALUES(scope.workspace_id,actor,p_key,nullif(current_setting('asm.correlation_id',true),'')::uuid,
          request_fingerprint,draft.id,draft.revision,effect);
      RETURN jsonb_build_object('request_id',draft.id);
    END $$""",
    "platform.service_request_owner_read(uuid,uuid,uuid)": r"""CREATE FUNCTION platform.service_request_owner_read(
      p_business uuid,p_conversation uuid,p_request uuid
    ) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    DECLARE scope app.conversations%ROWTYPE; draft app.service_requests%ROWTYPE;
    BEGIN
      scope:=platform.service_request_owner_scope(p_business,p_conversation);
      SELECT d.* INTO draft FROM app.service_requests d
        WHERE (d.workspace_id,d.business_id,d.conversation_id,d.client_id)
            =(scope.workspace_id,scope.business_id,scope.id,scope.client_id)
          AND (p_request IS NULL OR d.id=p_request)
        ORDER BY d.created_at DESC,d.id DESC LIMIT 1;
      IF NOT FOUND THEN
        IF p_request IS NOT NULL THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P3101'; END IF;
        RETURN NULL;
      END IF;
      RETURN jsonb_build_object(
        'request_id',draft.id,'workspace_id',draft.workspace_id,'business_id',draft.business_id,
        'conversation_id',draft.conversation_id,'client_id',draft.client_id,
        'service_id',draft.service_id,'service_name',draft.service_name,'release_id',draft.release_id,
        'template_revision',draft.template_revision,'revision',draft.revision::text,'state',draft.state,
        'intent_source',jsonb_build_object(
          'message_id',draft.intent_message_id,'source_version',draft.intent_source_version),
        'facts',draft.facts,'missing',draft.missing,'conflicts',draft.conflicts,'question',draft.question);
    END $$""",
}

RUNTIME_FUNCTIONS = (
    "platform.service_request_owner_create(uuid,uuid,text,jsonb)",
    "platform.service_request_owner_read(uuid,uuid,uuid)",
)


SCHEMA_GATES_0024 = (
    r"""CREATE OR REPLACE FUNCTION platform.ai_provider_session(p jsonb,p_enable boolean) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE s platform.ai_provider_sessions%ROWTYPE; old platform.ai_provider_sessions%ROWTYPE;
BEGIN
  IF session_user<>'asm_migrator' OR current_database()<>'asm_test' OR p_enable IS NULL THEN
    RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
  IF p_enable IS FALSE THEN
    IF NOT platform.material_object(p,ARRAY['session_id']) THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
    UPDATE platform.ai_provider_sessions SET active=false WHERE id=(p->>'session_id')::uuid;
    IF NOT FOUND THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
    RETURN jsonb_build_object('code','DISABLED');
  END IF;
  IF NOT platform.material_object(p,ARRAY['session_id','workspace_id','connection_id','conversation_id','client_id','chat_id','bot_identity','data_profile','starts_at','expires_at','max_calls','max_rub','review_sha256','review_checked_at','config'])
    OR platform.ai_provider_config_valid(p->'config') IS NOT TRUE
    OR (p->>'data_profile',p->'config'->>'prompt_revision') NOT IN
      (('SYNTHETIC_TEXT_V1','conversation_v2'),('SYNTHETIC_PUBLISHED_KNOWLEDGE_V1','conversation_v3'))
    OR p->'config'->>'revision' IS DISTINCT FROM 'polza-'||(p->>'session_id')||'-'||(p->>'review_sha256')
    OR (platform.intake_v7_schema_profile()->>'valid')::boolean IS NOT TRUE THEN
    RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
  s:=jsonb_populate_record(NULL::platform.ai_provider_sessions,(p-'session_id')||jsonb_build_object('id',p->>'session_id','active',true,'created_at',clock_timestamp()));
  IF s.starts_at>clock_timestamp() OR s.expires_at<=clock_timestamp() OR s.review_checked_at>clock_timestamp()
    OR s.review_checked_at<clock_timestamp()-interval '24 hours'
    OR (s.config->'limits'->>'call_cost_reservation')::numeric*s.max_calls>s.max_rub
    OR NOT EXISTS(SELECT 1 FROM app.conversations c JOIN app.channel_connections cc ON (cc.workspace_id,cc.id)=(c.workspace_id,c.connection_id)
      WHERE (c.workspace_id,c.id,c.connection_id,c.client_id,c.provider_chat_id)=(s.workspace_id,s.conversation_id,s.connection_id,s.client_id,s.chat_id)
      AND cc.provider='TELEGRAM' AND cc.bot_identity=s.bot_identity AND cc.status='ACTIVE') THEN
    RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
  SELECT * INTO old FROM platform.ai_provider_sessions WHERE id=s.id FOR UPDATE;
  IF FOUND THEN
    IF (to_jsonb(old)-'created_at') IS DISTINCT FROM (to_jsonb(s)-'created_at') THEN
      RAISE EXCEPTION 'IDEMPOTENCY_KEY_CONFLICT' USING ERRCODE='P2001'; END IF;
    RETURN jsonb_build_object('code','ALREADY_ENABLED');
  END IF;
  INSERT INTO platform.ai_provider_sessions SELECT s.*;
  RETURN jsonb_build_object('code','ENABLED');
END $$""",
    r"""CREATE OR REPLACE FUNCTION platform.human_context_policy_command(ws uuid,p_connection uuid,p_operation text,p_key text,
        p_expected_policy text,p_expected_epoch bigint,p_binding jsonb,p_profile jsonb) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE c app.channel_connections%ROWTYPE; s platform.telegram_connection_state%ROWTYPE;
        r platform.human_context_policy_receipts%ROWTYPE; prior platform.human_context_policy_receipts%ROWTYPE;
        profile jsonb; fingerprint bytea; binding jsonb; allowed boolean; moment timestamptz; corr uuid;
      BEGIN
        IF session_user<>'asm_migrator' OR current_database() NOT IN ('asm_local','asm_test') THEN RAISE EXCEPTION 'ACCESS_DENIED' USING ERRCODE='P2601'; END IF;
        PERFORM platform.turn_require_isolation();
        IF ws IS NULL OR p_connection IS NULL OR p_operation IS NULL OR p_operation NOT IN ('ENABLE','PAUSE') OR p_key IS NULL OR p_key !~ '^[A-Za-z0-9._:-]{1,128}$'
          OR p_expected_policy IS NULL OR p_expected_policy NOT IN ('OFF_UNUSED','ON','PAUSED') OR p_expected_epoch IS NULL OR p_expected_epoch<0
          OR platform.material_object(p_binding,ARRAY['business_id','provider','bot_identity','external_connection_id','owner_user_id']) IS NOT TRUE
          OR platform.material_object(p_profile,ARRAY['source_tree','schema_revision','profile_sha256','drain_confirmed']) IS NOT TRUE THEN
          RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2601'; END IF;
        IF NOT platform.human_context_uuid(p_binding->'business_id') OR jsonb_typeof(p_binding->'provider')<>'string' OR p_binding->>'provider' NOT IN ('CONTROLLED','TELEGRAM')
          OR jsonb_typeof(p_binding->'bot_identity')<>'string' OR platform.messaging_valid_id(p_binding->>'bot_identity',128,512) IS NOT TRUE
          OR jsonb_typeof(p_binding->'external_connection_id')<>'string' OR platform.messaging_valid_id(p_binding->>'external_connection_id',256,1024) IS NOT TRUE
          OR NOT ((p_binding->>'provider'='CONTROLLED' AND p_binding->'owner_user_id'='null'::jsonb) OR
            (p_binding->>'provider'='TELEGRAM' AND jsonb_typeof(p_binding->'owner_user_id')='string' AND platform.telegram_numeric_id(p_binding->>'owner_user_id') IS TRUE
              AND platform.telegram_numeric_id(p_binding->>'bot_identity') IS TRUE))
          OR jsonb_typeof(p_profile->'source_tree')<>'string' OR p_profile->>'source_tree' !~ '^[0-9a-f]{40}$'
          OR jsonb_typeof(p_profile->'schema_revision')<>'string' OR p_profile->>'schema_revision'<>'0024'
          OR jsonb_typeof(p_profile->'profile_sha256')<>'string' OR p_profile->>'profile_sha256' !~ '^[0-9a-f]{64}$'
          OR p_profile->'drain_confirmed' IS DISTINCT FROM 'true'::jsonb THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2601'; END IF;
        SELECT platform.intake_v7_schema_profile() INTO profile;
        IF profile->'valid' IS DISTINCT FROM 'true'::jsonb OR p_profile->>'profile_sha256' IS DISTINCT FROM profile->>'profile_sha256' THEN
          RAISE EXCEPTION 'POLICY_PREREQUISITE_FAILED' USING ERRCODE='P2601'; END IF;
        PERFORM 1 FROM platform.workspaces WHERE id=ws FOR SHARE;
        IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P2601'; END IF;
        PERFORM pg_advisory_xact_lock(hashtextextended(ws::text||':HUMAN_CONTEXT_POLICY_V1:'||p_key,2013));
        SELECT * INTO c FROM app.channel_connections WHERE workspace_id=ws AND id=p_connection;
        IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P2601'; END IF;
        PERFORM 1 FROM app.businesses WHERE workspace_id=ws AND id=c.business_id FOR SHARE;
        SELECT * INTO STRICT c FROM app.channel_connections WHERE workspace_id=ws AND id=p_connection FOR UPDATE;
        SELECT * INTO s FROM platform.telegram_connection_state WHERE workspace_id=ws AND connection_id=c.id FOR SHARE;
        binding:=jsonb_build_object('business_id',c.business_id,'provider',c.provider,'bot_identity',c.bot_identity,
          'external_connection_id',c.external_connection_id,'owner_user_id',CASE WHEN c.provider='TELEGRAM' THEN s.owner_user_id END);
        IF binding IS DISTINCT FROM p_binding OR NOT EXISTS(SELECT 1 FROM platform.channel_routes WHERE workspace_id=ws AND connection_id=c.id
          AND provider=c.provider AND bot_identity=c.bot_identity AND route_key=c.external_connection_id) OR
          (c.provider='TELEGRAM' AND (s.bot_identity,s.external_connection_id,s.owner_user_id) IS DISTINCT FROM
            (c.bot_identity,c.external_connection_id,p_binding->>'owner_user_id')) THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P2601'; END IF;
        SELECT platform.intake_v7_schema_profile() INTO profile;
        IF session_user<>'asm_migrator' OR profile->'valid' IS DISTINCT FROM 'true'::jsonb OR p_profile->>'profile_sha256' IS DISTINCT FROM profile->>'profile_sha256' THEN
          RAISE EXCEPTION 'POLICY_PREREQUISITE_FAILED' USING ERRCODE='P2601'; END IF;
        fingerprint:=platform.human_context_hash(E'asm:m3:human_context_policy:v1\n',ARRAY[ws::text,session_user::text,c.id::text,p_operation,p_expected_policy,p_expected_epoch::text,
          p_binding->>'business_id',p_binding->>'provider',p_binding->>'bot_identity',p_binding->>'external_connection_id',p_binding->>'owner_user_id',
          p_profile->>'source_tree',p_profile->>'schema_revision',p_profile->>'profile_sha256','true']);
        SELECT * INTO prior FROM platform.human_context_policy_receipts WHERE workspace_id=ws AND namespace='HUMAN_CONTEXT_POLICY_V1' AND idempotency_key=p_key;
        IF FOUND THEN
          IF prior.request_fingerprint<>fingerprint THEN RAISE EXCEPTION 'IDEMPOTENCY_KEY_CONFLICT' USING ERRCODE='P2601'; END IF;
          RETURN jsonb_build_object('outcome','REPLAY','result',prior.result);
        END IF;
        IF (c.human_context_policy,c.human_context_policy_epoch) IS DISTINCT FROM (p_expected_policy,p_expected_epoch) THEN RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P2601'; END IF;
        IF p_operation='PAUSE' AND c.human_context_policy='OFF_UNUSED' THEN RAISE EXCEPTION 'CONTEXT_POLICY_INACTIVE' USING ERRCODE='P2601'; END IF;
        IF p_operation='ENABLE' THEN
          IF NOT EXISTS(SELECT 1 FROM platform.workspaces WHERE id=ws AND status='ACTIVE')
            OR NOT EXISTS(SELECT 1 FROM app.businesses WHERE workspace_id=ws AND id=c.business_id AND status='ACTIVE') OR c.status<>'ACTIVE'
            OR (c.provider='TELEGRAM' AND s.material_enabled IS NOT TRUE) THEN RAISE EXCEPTION 'POLICY_PREREQUISITE_FAILED' USING ERRCODE='P2601'; END IF;
          BEGIN allowed:=platform.messaging_manual_send_allowed(ws);
            EXCEPTION WHEN SQLSTATE 'P2301' THEN RAISE EXCEPTION 'UNAVAILABLE' USING ERRCODE='P2601'; END;
          IF allowed IS NOT TRUE THEN RAISE EXCEPTION 'POLICY_PREREQUISITE_FAILED' USING ERRCODE='P2601'; END IF;
          IF c.human_context_policy='PAUSED' AND c.human_context_policy_epoch=9223372036854775807 THEN
            RAISE EXCEPTION 'POLICY_VERSION_EXHAUSTED' USING ERRCODE='P2601'; END IF;
        END IF;
        r.workspace_id:=ws; r.id:=uuidv7(); r.connection_id:=c.id; r.business_id:=c.business_id; r.provider:=c.provider;
        r.bot_identity:=c.bot_identity; r.external_connection_id:=c.external_connection_id; r.owner_user_id:=p_binding->>'owner_user_id';
        r.actor_db_role:=session_user; r.namespace:='HUMAN_CONTEXT_POLICY_V1'; r.idempotency_key:=p_key; r.request_fingerprint:=fingerprint;
        r.operation:=p_operation; r.expected_policy:=p_expected_policy; r.expected_policy_epoch:=p_expected_epoch;
        r.accepted_policy:=CASE WHEN p_operation='ENABLE' THEN 'ON' ELSE 'PAUSED' END;
        r.accepted_policy_epoch:=p_expected_epoch+CASE WHEN p_operation='ENABLE' AND p_expected_policy<>'ON' THEN 1 ELSE 0 END;
        r.change:=CASE WHEN r.accepted_policy=p_expected_policy THEN 'UNCHANGED' WHEN p_operation='ENABLE' THEN 'ENABLED' ELSE 'PAUSED' END;
        r.source_profile:=p_profile; r.event_type:='HUMAN_CONTEXT_POLICY_COMMANDED'; r.accepted_at:=clock_timestamp(); corr:=uuidv7();
        INSERT INTO app.audit_events(workspace_id,actor_kind,actor_user_account_id,correlation_id,event_type,object_type,object_id,object_version,payload)
          VALUES(ws,'LOCAL_PROVISIONER',NULL,corr,r.event_type,'CHANNEL_CONNECTION',c.id,r.accepted_policy_epoch,
            jsonb_build_object('receipt_id',r.id,'operation',r.operation,'change',r.change,'previous_policy',r.expected_policy,'accepted_policy',r.accepted_policy,
              'previous_policy_epoch',r.expected_policy_epoch::text,'accepted_policy_epoch',r.accepted_policy_epoch::text)) RETURNING audit_event_id INTO r.audit_event_id;
        r.result:=platform.human_context_policy_result(r);
        INSERT INTO platform.human_context_policy_receipts SELECT r.*;
        IF r.change<>'UNCHANGED' THEN UPDATE app.channel_connections SET human_context_policy=r.accepted_policy,
          human_context_policy_epoch=r.accepted_policy_epoch WHERE workspace_id=ws AND id=c.id; END IF;
        RETURN jsonb_build_object('outcome','ACCEPTED','result',r.result);
      END $$""",
)

PROFILE = r"""CREATE FUNCTION platform.service_request_schema_profile() RETURNS jsonb
      LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      WITH expected(signature,body_hash,language,security_definer,volatility,runtime_execute) AS (VALUES ('app.current_messaging_owner_workspace_id()','8ffbd40db1c507c7384981d683bf671cc1914b088d61aa543c8a2a2d44debee6','plpgsql',true,'s',true),
('app.current_workspace_id()','f6c6760e5de3ce4885b0c27daf1ab82867438c4c1ec19d95cb084bb4e799475d','plpgsql',true,'s',true),
('platform.ai_delivery_begin(uuid,uuid,bigint,bigint,jsonb)','5573f154a508e3a3a53f77b4dd93a275dd2ac7524f075d63b29971764852c7e0','plpgsql',true,'v',true),
('platform.ai_delivery_claim(text,timestamptz,timestamptz,uuid)','7ee3ed1d45d79873dd709a53473da3ffa98d9b150c949c814d552603a5b6fdf6','plpgsql',true,'v',true),
('platform.ai_delivery_command(uuid,uuid,text,jsonb)','9d5038f9c26d8876321cb98493c355f502d9b29e3bb97c53e6ce82b04a516c13','plpgsql',true,'v',true),
('platform.ai_delivery_current(platform.messaging_jobs,platform.ai_deliveries,platform.ai_runs)','234be32399cb86ad5f96c4667428df64dad88352c12ec1ada4954e6327ee5a0a','plpgsql',true,'v',false),
('platform.ai_delivery_enqueue(uuid,uuid)','c933c3e6c1381db9fe7e5234beab38c17ad53adad3829a6760755f6a2f0fc1e1','plpgsql',true,'v',true),
('platform.ai_delivery_immutable()','b9a99ff57ecaedc39983206f2d6df7381c41ade5860fde9c438f86acab030998','plpgsql',true,'v',false),
('platform.ai_delivery_schema_profile()','2af634ab2afb3b2b9a536453ce6c735b6be57a1018fdd0893d707d3d5dca5f36','sql',true,'s',false),
('platform.ai_delivery_select(platform.messaging_jobs,platform.ai_runs)','9a6a2181bf5c3de115b2414f1e2ffd09fdfef9328908b7241a336d6f87c7216d','plpgsql',true,'v',false),
('platform.ai_knowledge_current(platform.ai_runs)','d98f7f41bb5010bd967004794410eff26d7c0203207104190a0a4909df42de8f','plpgsql',true,'v',false),
('platform.ai_knowledge_immutable()','a5dc3e44d61c74d3ad36a048961eed0ca3df662cbf7da9025a839c5aa0754a1b','plpgsql',true,'v',false),
('platform.ai_knowledge_snapshot(uuid,uuid)','14c077414a0063174421f6f9bd8a240d77b2700c198d22e8f9ec07a0be9f8ff5','plpgsql',true,'v',false),
('platform.ai_knowledge_valid(jsonb,jsonb,uuid,uuid)','c9cfe061cdecded77ee5f40e5a2775908382eba3996b61824636cc7e5eeed51e','plpgsql',true,'i',false),
('platform.ai_provider_command(uuid,uuid,uuid,text,jsonb)','24672f24048580bb314ed845a9d1e4869dee15d519063dedb029e82d0b4e2c60','plpgsql',true,'v',true),
('platform.ai_provider_config_valid(jsonb)','38064b38949e67306db7dbbcbf150dfd6d2b2195ad8aac77267ab1f6939a30af','plpgsql',true,'i',false),
('platform.ai_provider_enqueue(uuid,uuid,uuid)','91e5c0e7e3ae24516d55c68d9cda830fc8d52f15701cce31d7cdb65289583096','plpgsql',true,'v',true),
('platform.ai_provider_guard(uuid,platform.messaging_jobs,jsonb)','4beb6f775cc17a68fbd068c2b69692f2b2e4ef5c2b78753e119bd679f16666c3','plpgsql',true,'v',false),
('platform.ai_provider_schema_profile()','f2b1f7dbdea1f41244094a101d7d4802927a550078ac260e14c7ffb997bd1986','sql',true,'s',false),
('platform.ai_provider_session(jsonb,boolean)','5ba5125578d3da5f509ebe4f5235b8dcad01f73868461c17689cdca853c37675','plpgsql',true,'v',false),
('platform.ai_reply_rights_commit(uuid,uuid,uuid,bigint,bigint,jsonb,jsonb)','5e977dd4c1fb4a616a7dabce2fd099247646091e2e2c9b577ff00ca3368bf0df','plpgsql',true,'v',true),
('platform.ai_reply_rights_current(uuid,uuid,uuid)','0c38889d00c0cf1415a890273eebd8f593ed40fe166436a5ad434079d1d30fe7','plpgsql',true,'v',false),
('platform.ai_reply_rights_probe(uuid,uuid,uuid)','9ca90da38d173e7294f77cd7dbdd25492f02fe2cd699562c823c42fbfcb3b01d','plpgsql',true,'v',true),
('platform.ai_reply_rights_schema_profile()','6b635b12b8d2e7f0f69500792d7ec3b1c71cd0f85c51e810e3332b910b6189c0','sql',true,'s',false),
('platform.ai_runtime_command(uuid,uuid,text,jsonb)','339608bba7d81f2d27e8b55e006117d8fe77c6be011f72e4a0ce0d4a083551e2','plpgsql',true,'v',true),
('platform.ai_runtime_completion_valid(jsonb)','4675d7ce837be36341cdc60deff5c216786ad7f42441bb4bda43bfe5e0dcfb0d','plpgsql',true,'i',false),
('platform.ai_runtime_config_valid(jsonb)','a6d4e29eada1c608381d528e55cbc8108903d263f74bfbdd450adddff3ed2742','sql',true,'i',false),
('platform.ai_runtime_current(platform.messaging_jobs,jsonb)','c86bbe138ddabb5197dfbe4453e5b3f4f586099ebdfc62e463814198f3973e86','plpgsql',true,'v',false),
('platform.ai_runtime_receipt(platform.ai_runs)','14519c468cdcdbfca3b8f0e5332e1ecb377871b19b8de05b5af27afdc47a1db4','sql',true,'s',false),
('platform.ai_runtime_replay(uuid,uuid,jsonb)','36b9248da5aff70b2fec73a85303716769350732f5cee03deb719a9f6d0a17c3','plpgsql',true,'v',true),
('platform.ai_runtime_result_valid(jsonb)','7f81305118ab1bff57585a409c91b04ff2eb44d24722d74b35ae05379d5e21d1','plpgsql',true,'i',false),
('platform.ai_runtime_view(platform.ai_runs)','ebfb0382fb632ea8ae5b0cc6d2a7976647ee9cbbad89810973d1ec3e15e45298','sql',true,'s',false),
('platform.ai_synthetic_config_valid(jsonb)','20241427cbe5024f6a5876184f29895f28a83191519bf4d99a4e6e6993baf00c','plpgsql',true,'i',false),
('platform.auth_bootstrap(text,integer)','6eb28b55313391c9d0eb07ca055ff8754e49b83cfeef132d9ba413077545c5dd','plpgsql',true,'v',true),
('platform.auth_lock_session(text,boolean)','55ca74ab7475f964865b6d3a6b73778f7139add6a1531781b14362fef0f30428','plpgsql',true,'v',false),
('platform.auth_login(text,uuid,bigint,bigint,text,integer)','3f975835d787dd8531c415783aa7492facafcbd5d9def911703780bb1bfc83c1','plpgsql',true,'v',true),
('platform.auth_logout(text)','67f05d0d9e47e103cd71365e8f9e574bdd6bcff42dbe156d9f6a68c1b04149e2','plpgsql',true,'v',true),
('platform.auth_memberships(text)','0e684da56252678c7bc27b962a49c4213c3de9865a63b43e552221b36ab9b7fb','plpgsql',true,'v',true),
('platform.auth_password_lookup(text)','a972cb3994842757f18045afae2ac0f00d90020d482a62043376ecd3ee5b22e3','sql',true,'s',true),
('platform.auth_rotate(text,text)','7978763cff421212ae6e184771aa26468cf6be997f29ac386c256dfc0b0640b4','plpgsql',true,'v',true),
('platform.auth_session(text)','5e1e2ceaad4b2b1452a02d4d04f7f5d53ebf40e5067b7223baf5a2edc65253f4','plpgsql',true,'v',true),
('platform.business_configuration_schema_profile()','0f9dcf5d0a11c56e4d78f76626c70ea7f705962aa6bbd71a1cde183f5c530498','sql',true,'s',false),
('platform.configuration_active_read(uuid)','949fadc182665711e552e99f4520cf804ea6037634408d0252319c62127049c7','plpgsql',true,'v',true),
('platform.configuration_bundle_shape(jsonb)','563b4db3737b7bc1c66ed9f5e36e8d41e053f3bcc5d7c5bbcbd68bfb67a6e7f7','plpgsql',true,'i',false),
('platform.configuration_command(uuid,text,text,jsonb)','785ae59704a1ed262baa7dd197cd828e91fdc4890582236849539e36450b8b4c','plpgsql',true,'v',true),
('platform.configuration_immutable()','8cfeca7ce51a6990dcc48424553b948f985b75dfe187e29254f511bcd8063ef5','plpgsql',true,'v',false),
('platform.configuration_owner_read(uuid)','dc3b1b9ca35196841da4128296a971899eb693a1b6dfc75a2be8809aec5df24f','plpgsql',true,'v',true),
('platform.configuration_text_valid(jsonb,integer,boolean)','9b046fad55f926ead378d901bacd12edeb2f249d64f3fe913f604be3bb274cfa','sql',true,'i',false),
('platform.configuration_validate(jsonb)','18247df6a24c7ba1ba7b79b74d390e183fbda805d33a12b71e95c022ab8c89b3','plpgsql',true,'i',false),
('platform.conversation_control_execute(uuid,uuid,text,text,bigint,bigint)','b8fcb2df6bdb6564b8c68b05d1341e0979a89c9fae1af6244084e1d9fac15ea3','plpgsql',true,'v',true),
('platform.conversation_control_fingerprint(uuid,uuid,uuid,uuid,text,bigint,bigint)','60cd026890baa0f09e98c3742ab8da80d5a44fd243fa16d983ea42dcabd2459a','sql',false,'i',false),
('platform.conversation_control_locked(uuid,uuid,text,text,bigint,bigint)','0609192f801e87cb185525047a79af365e868c19f6974ce0d35c4a33388d96d0','plpgsql',true,'v',false),
('platform.conversation_control_prepare(uuid,uuid,text,text,bigint,bigint)','3d9ce63a7e8b9787adfe7ae96e77a42d6e1af57835f57351fb8846d7e3e07c35','plpgsql',true,'v',true),
('platform.conversation_control_read(uuid)','e30448916cece6ee18500c1ef5e9399b1c50dd8a2fad7f95c3cded2cf512f9b8','plpgsql',true,'v',true),
('platform.conversation_manual_prelock(uuid,text,text)','0cf8c71a6028ddd08508f9132991d891b6cada8e50c2c5b831b9bc4be2d3c65f','plpgsql',true,'v',true),
('platform.conversation_manual_takeover(uuid,uuid)','88a05e4aa03904af8f8ec54e8544dbe867b1f7f22404becef415b76cdf3e3d29','plpgsql',true,'v',false),
('platform.conversation_turn_activation_matches(uuid,uuid)','ed3f021b97d11656125233eac69944bfb4a3cf09abe761d63c8cc14d531e90a5','sql',true,'v',false),
('platform.duration_case_valid(jsonb)','353ff3d8b2a9b803f7a450bf5948228b475df13d1d2d8c8a59a3b2e65c06ffd5','plpgsql',true,'i',false),
('platform.duration_source_current(uuid,uuid,uuid,uuid)','c7c67464d97acba8e8b8e2ec811d6667c4246f313ab09921208cedcb9f47cb3d','sql',true,'s',false),
('platform.escalation_command(uuid,uuid,uuid,text,text,bigint,bigint,bigint,text)','d78188b472c058faa457ea118928fe5e27e64798206fa826548f120821d1db39','plpgsql',true,'v',true),
('platform.escalation_command_fingerprint(uuid,uuid,uuid,uuid,uuid,text,bigint,bigint,bigint,text)','83bc68632b05e2b1cc74ecb8ac81c595034dccb634182b93fa5335633ebd5c0c','sql',false,'i',false),
('platform.escalation_context_changed()','2f46330f429632c4704fde14a4002b4ac30b30fa496394216766d62ab02cc392','plpgsql',true,'v',false),
('platform.escalation_immutable()','19c64f64d5352a55d4667f6902ebbb9afe163a66ff4f2d97c390defae6a237ed','plpgsql',true,'v',false),
('platform.escalation_list(integer,text,timestamptz,uuid)','5ff87e52a9a7dd67668f0b29766c75ed5736aa8229bcf7b6f353de3ea5d637e5','plpgsql',true,'v',true),
('platform.escalation_now()','31ebb037ed35337329fa522d1b51d159d7ed91eccc95e3694b2338abbcea74b1','sql',false,'v',false),
('platform.escalation_read(uuid)','ead5ea146752eaeeaa0d22b4b9dda62f869b2a19352c1ea6694141e9da4bff10','plpgsql',true,'v',true),
('platform.escalation_request_for_turn(uuid,uuid)','f3a9d542a46754fbad85510a192230865a7fe76dcdfe17918330244a55cdac37','plpgsql',true,'v',true),
('platform.escalation_request_replay(uuid,uuid)','1e10c8742b9e58fee2780d55d44af2bfb097b0114afae0b2647a201f0416f989','plpgsql',true,'s',true),
('platform.escalation_timer_execute(uuid,uuid)','0bbd68c40bcae571fde899c57a51f1628fea26238e662ff015ed428ca8dfd7b3','plpgsql',true,'v',true),
('platform.escalation_validity(uuid,uuid,timestamptz)','dcf8133b6d2d080091ec392b4eea9c64792d6aecb09ca163fba1084228f92beb','sql',true,'s',false),
('platform.files_begin_fetch(uuid,uuid)','b613633a1c13e033a051e593182d275502a7b1ed9e586a8351e494ca7f394347','plpgsql',true,'v',true),
('platform.files_claim_cleanup(integer)','5961679941084084fb083ec755861f9db3ecb0792f57e24fe338eb6df42bf143','plpgsql',true,'v',true),
('platform.files_finish_cleanup(uuid,uuid,text)','f25b769900d682dbf58e53f68dad2952162604bcde386343115f86b504aba39d','plpgsql',true,'v',true),
('platform.files_finish_fetch(uuid,uuid,uuid)','185f336920b32f3f5c21f300ee76f456610e65164b2a39eca7539948e4c00932','plpgsql',true,'v',true),
('platform.files_immutable()','da3e6c650e8c2ed10ad61169127e0808370857c1d458e05b49c37b7db78c4bc2','plpgsql',false,'v',false),
('platform.files_manifest_valid(jsonb)','3a4dbfe98efa8df5455d6ac60aeec88250d7ea110408aed5a323557b480eaf67','plpgsql',false,'i',false),
('platform.files_plan(uuid,uuid,uuid)','ec5f05ae04a2d4bc0ee91f99a6db768801c78890761f255a86001e8f413ead22','plpgsql',true,'v',false),
('platform.files_prepare_upload(uuid,uuid,jsonb)','da20120cf752fc9a0be9b31d19efdd081949391b3ff3b12b72f68e3254192a9f','plpgsql',true,'v',true),
('platform.files_read_manifest(uuid,uuid,uuid)','586d58424a80d3eca338f74863d5b2ce4b0b4d97ad62d7aa72862d0374f4bfd7','plpgsql',true,'v',true),
('platform.files_upload_json(platform.file_object_uploads)','56d0788594b3d549f87cac1980dd152d902cebb3ba9cd758066fa281c1449c40','sql',false,'s',false),
('platform.guard_entitlement()','bed228f9542f5a6f85f28e17f47ab11f3524ab52fb648f4452c9dca4485efe06','plpgsql',false,'v',false),
('platform.guard_plan_revision()','9ae94c6c1e0a8b05eeeac31db412d4cd5c8f4157bdae437664c82f5f0fc2c33b','plpgsql',false,'v',false),
('platform.guard_require_current(uuid,uuid,uuid,bigint)','b5cce50ac291e7fe75adb5cb2e3c41bef3e7c67ba6229db8131b956d7560e0c8','plpgsql',true,'v',false),
('platform.guard_send_begin(uuid,uuid)','af4661dcc860cc13fffc459bfa85f07cfae8c6a45e33ba2e0292f2baf54af835','plpgsql',true,'v',true),
('platform.guard_text_fingerprint(jsonb,text)','d22ae019b3f8391ee43bb7e5f8889364694e8c59924f1712cc8533074da76bc2','sql',false,'i',false),
('platform.guard_turn_accept(uuid,uuid,text,text)','43ca3517c109f27bc9c0b9d75fc18567b2b9dc9a9e3c730bb05299a266438671','plpgsql',true,'v',true),
('platform.guard_turn_prepare(uuid,uuid)','f3487b85737dc4ad58025c176fbfaab7b4d1ec6c0dbac17bb2d9fa066dee6ddd','plpgsql',true,'v',true),
('platform.guard_turn_replay(uuid,uuid,text,text)','e919531e4ea823def1545555aa00c91d9ac1b8b0ce9e67d8f2c698bfcb875889','plpgsql',true,'s',true),
('platform.human_context_admission(uuid,uuid,jsonb)','488b415fb0b393233901c3124b9b20f0b2dacde2cb4fc7da6b7e5768e0f52584','plpgsql',true,'v',false),
('platform.human_context_basic_current(uuid,uuid,uuid,bigint)','a60e4a7d9e3d44c08d72f9dfe32dfeffaba0201cf5f702f292679551c811147b','plpgsql',true,'v',false),
('platform.human_context_consistent()','6e2d888a129131ecdf801a25fbcdc2f10304e2837e8937a8244d63421361db0f','plpgsql',true,'v',false),
('platform.human_context_current_valid(jsonb)','c239ee7a7ee200b392aad3735a5410cfab6cb1f79d4f0eee6e41a115ef498b85','sql',true,'i',false),
('platform.human_context_decimal(jsonb,boolean)','9e2e793224366ce5c3ceaa841c0f71ce7de25c0c2ab55b56618634a6852c8cff','sql',true,'i',false),
('platform.human_context_effective(app.messages,jsonb,text)','22b84266fb2a1c048c0216d23d554bc10c9f65b1f2fc822bef65c3e211ed0a49','sql',true,'s',false),
('platform.human_context_escalation_hold(uuid,uuid,timestamptz)','148e7567b42294c742d26858d7cf65acafa2b20125d880d2738f36c131145546','sql',true,'s',false),
('platform.human_context_hash(text,text[])','9056f96e6302bd0d4a27b8cf393b33fbdafaaa39b5900ad41516bf4a066be1fc','sql',true,'i',false),
('platform.human_context_integrity()','56aa7388cfa150391a0ee3ee7ddc520058147f89d234bf1234fc56a45a5f5ca4','plpgsql',true,'v',false),
('platform.human_context_observation_digest(uuid,uuid,uuid,uuid,jsonb)','6c60ce9d15916b797ade41ea410c19ff3b5b5be75f42e7e06cb982cbf654b0e7','sql',true,'i',false),
('platform.human_context_observations(uuid,integer,jsonb)','525edce2323e2ab781d46c115990d916f81eea6d0e9d9c1006798cdb01be00cc','plpgsql',true,'v',true),
('platform.human_context_observe(platform.telegram_update_receipts,jsonb)','002b6410107e55a5025d49178b127a672e642ec3418eb2bcac7f038f6ae6fe3d','plpgsql',true,'v',false),
('platform.human_context_policy_command(uuid,uuid,text,text,text,bigint,jsonb,jsonb)','9769c8f0f06f077ce9939f18d735c004a7dca7df34482181ece1bf99d370f84e','plpgsql',true,'v',false),
('platform.human_context_policy_guard()','9fad112676add9ee5c5874ab9d79583053161024f361c5f8cfb7d5caca7970aa','plpgsql',true,'v',false),
('platform.human_context_policy_result(platform.human_context_policy_receipts)','14a64a6a05514af4312ef42d62554b396dc2d885235424bcb13f68b7aac3edb6','sql',true,'s',false),
('platform.human_context_preview(jsonb)','edd77e725660f24f41d2a96424e2434bec0c58432b8a7ceb0b6dd1bb57a3e381','sql',true,'i',false),
('platform.human_context_projection(uuid,uuid,timestamptz)','9b01b599b0cb9022d067dea451b48a6abb1c534bbc064b3e0b2c0ed41230234f','sql',true,'s',false),
('platform.human_context_read(uuid)','513256e45b12356cdd149e934bf11c56fefe44a321bfdfe498e0dbf0a1939b1c','plpgsql',true,'v',true),
('platform.human_context_reason(jsonb,boolean)','799072de08ee913f09c11686e9a8300e55602ae7d5bf3f8610bb1a35a6d2cb19','sql',true,'i',false),
('platform.human_context_reconcile(uuid,text,jsonb)','d75cd2b145fbe84ec26923b924b744f9a728546ee7f2254c9f62e5d2ca26546d','plpgsql',true,'v',true),
('platform.human_context_reconcile_result(platform.human_context_reconciliations)','a2645c2165f2eee80027b426b5377c233f3412b4c52e32c7aab04708e011790d','sql',true,'s',false),
('platform.human_context_revision_json(platform.human_context_reconciliations)','83a0d64f71b77f9dc8633c7f52498355c758cccdf2bc96d0908c4a125d362094','sql',true,'s',false),
('platform.human_context_schema_profile()','527fce5681d5345369cd88b555a302df6d305ef8566cf12a666198eb64a6f4ac','sql',true,'s',false),
('platform.human_context_snapshot_check(jsonb,text)','220cf8e65eb0c0b72fd03a87b3b97f834f738215ce7ec7461ccd0f32af12c110','plpgsql',true,'s',false),
('platform.human_context_snapshot_valid(jsonb,text)','17668f832ac5559e5b04e42912c362dce35f818856c19dbbe732c4074aae67a7','plpgsql',true,'s',false),
('platform.human_context_stale()','355dfcb1e982c63fee2e5d2f9df0bae68218e5c211b80ed1aaa14b6fe353f68a','plpgsql',true,'s',false),
('platform.human_context_test_guard(platform.messaging_jobs,jsonb)','5600ba815891a13dcbfddb224575d449d1b14c2121e6ea10fb5f4e2bb597639f','plpgsql',true,'v',false),
('platform.human_context_test_prelock(platform.messaging_jobs)','4ec2eb2e2e5b65b433ef05e6aed5a7a4bf0008a86871562307dbddd42a2de2d7','plpgsql',true,'v',false),
('platform.human_context_text_valid(text)','efcf1bcedf46ec93feb243adb5b1d719e0d1d17658094a54a1a4152504b865b8','sql',true,'i',false),
('platform.human_context_turn_projection(uuid,uuid,timestamptz)','93808034183e13274dd55c03b175a89b0db43434c0d88167b1a29d6eed42f2ed','sql',true,'s',false),
('platform.human_context_uuid(jsonb)','033d0b6c405aa313bece14c3338046b7624d0da096e3c6b60e9e15417e77ff77','sql',true,'i',false),
('platform.human_context_wait(uuid,uuid,text)','34666cb91739199ba976e2af87a4d6cb40afa12bfa00d72d3bda3cb8d7ab69af','plpgsql',true,'v',false),
('platform.human_context_work_lookup(uuid,uuid)','13969135268d8f00c990b49ff1d2aaed5e79a9ee9602fdd3d8f5ce366cd18be9','sql',true,'s',false),
('platform.human_context_work_replay(uuid,uuid)','28bc46d45b5b5306e3ce4b0fa6fc0c47fb6b300ab7e28541c4d7df58c2ba6946','sql',true,'s',true),
('platform.human_context_work_valid(platform.messaging_jobs)','bc7c086476e335c5f58cd1cddc409018f81f40d7995e383d7734ccfde58a93db','sql',true,'s',false),
('platform.initialize_local_billing(uuid,text,integer,text,text,text,timestamptz,timestamptz,text)','20b0e1ea5d37d8710b485232cff1441ea7c6998d431233877d2ab1814f620e83','plpgsql',true,'v',false),
('platform.initialize_local_messaging_billing(uuid,text,timestamptz,timestamptz)','2863259a15ff3178525d044704c26dbc57c35e4322f5412bed6dd13989098f7d','plpgsql',true,'v',false),
('platform.initialize_telegram_connection(uuid,uuid,text,text,text,jsonb)','bfae87784d2145810f9ed12f1dfab4416d8041c9d2044c1397204bbe0f8275bf','plpgsql',true,'v',false),
('platform.intake_apply(platform.ai_runs,jsonb)','2cd34b223afd4cac720ad64d0b103d35c37dac14bea36944da1d84114b6a330f','plpgsql',true,'v',false),
('platform.intake_candidates_valid(jsonb)','8341249f2e0a5b4a546b7685134aec687fb8065624c72acfea2700a13863632e','plpgsql',true,'i',false),
('platform.intake_current(platform.ai_runs)','1d3b0395102b257d83c46ff69dda128436c840b229c71480d4efcfe03e0d9e3f','plpgsql',true,'s',false),
('platform.intake_delivery_guard(platform.ai_runs)','dc64fc2273a9197d65b5c01fc931174a7b91913dc5521f5fb12d4b47918c2e47','plpgsql',true,'v',false),
('platform.intake_delivery_session_lock(uuid,uuid,uuid,numeric)','193b23fc217a3d439d03acaccdd44887d0723e8f94c04429968c8a881ab424b5','plpgsql',true,'v',false),
('platform.intake_escalation_decorate(jsonb)','d4ea1bcf1556f3593c24c2844c248634490272d8ffa3c79bd6cfd0fcb5a75dfe','plpgsql',true,'v',false),
('platform.intake_owner(uuid,uuid,text,text,jsonb)','c940819b500be416ee02e8faa269072d2e3a9f0de1337efe00f325778fd3010e','plpgsql',true,'v',true),
('platform.intake_project(uuid,uuid,uuid,uuid)','68363d82af951fef71220a60cd921e173e6d502df2d099c46c66d83d47216491','plpgsql',true,'s',false),
('platform.intake_result_valid(jsonb)','ddba46cf9b1b02521b42687743544d031f22cfcc94aff0c132f1053935088993','sql',true,'i',false),
('platform.intake_runtime_pin(uuid,uuid,uuid,uuid)','e2731baa38c541254ec9244f3337e236c9735c4fe77d484f35d9c9947ed35380','sql',true,'s',false),
('platform.intake_schema_profile()','87197672ba2e5476ec2657e5c1d96c49ef78eff6892c26258f0fb3eb8c07e899','sql',true,'s',false),
('platform.intake_source_current(uuid,uuid,uuid,uuid,jsonb)','9890f8c873dc797bdb7633f2d09f6e24f617bd38419308b407f372075a66f486','sql',true,'s',false),
('platform.intake_sources(uuid,uuid,uuid,uuid)','378973095bceb7241fa8c68a0146feef3d77820f59846d1a2921690e216a1608','sql',true,'s',false),
('platform.intake_template(jsonb)','2e33bbbba0580bcca22a35d0af0cf2037c7283a71c7c679dac88533c02da8c45','sql',true,'i',false),
('platform.intake_turn_sources(jsonb,jsonb)','a29d09a0b400d4101edd9a309b49c4039a9d8c8ac08584d2d23c674453f39435','sql',true,'i',false),
('platform.intake_v7_schema_profile()','ab79bb829f4c2262557732cd4bfff38145231038c5504d0edfca58845a98ceac','sql',true,'s',false),
('platform.knowledge_availability(uuid,uuid,uuid,bigint)','761a7fc9b4bb29495753b6aae909101d2851590782e08e418093a6bd90521a3c','plpgsql',true,'s',false),
('platform.knowledge_build_apply(uuid,uuid,uuid,jsonb)','752e201d6f9ac957e1ba8af2104c96784e6179261de8298ed0b00475e9551fae','plpgsql',true,'v',true),
('platform.knowledge_build_create(uuid,uuid,uuid,jsonb)','3885ad0fa5ae7fde118a9b27fbc37d7361e24e9fb0192cc291c899b6c7265092','plpgsql',true,'v',false),
('platform.knowledge_build_reserve(uuid,uuid,integer)','9fb8a604d1832b79524aae3022179ed1f4356b390087a752031e3f134de65b3b','plpgsql',true,'v',true),
('platform.knowledge_build_valid(uuid,uuid,uuid,boolean)','4902ae09b677a5a4ede126ad49c82fbac3596909e24fe93573b253cc3ae7bc1f','plpgsql',true,'s',false),
('platform.knowledge_build_wire(uuid,uuid,uuid,integer)','b4148eb3afce3271c1e7e6e9e7cc0df1b8e162265b54742718d1529bb3cdeebc','sql',true,'s',false),
('platform.knowledge_embedding_complete(uuid,uuid,jsonb)','16b7393f4b545e590ebf2105f73de39dfcc376f4832fe73b9384c1b1f038c941','plpgsql',true,'v',true),
('platform.knowledge_immutable()','1897bb95918979697e9a10bd2879a1ba5e76a24b92106f760404f1dadf7ed02a','plpgsql',true,'v',false),
('platform.knowledge_normalize(text)','7fe8049f4bcf381a33239ae6159e63d7e5033b873df4300c025ccdb4accfb210','sql',true,'i',false),
('platform.knowledge_owner_command(uuid,text,text,jsonb)','bfe770b1cab3b9925eb9f53e68039a18cb1a7149c52773ab3a44e81c10325fa5','plpgsql',true,'v',true),
('platform.knowledge_owner_lock(uuid)','313973899661e37362466afc57c9563bdd90edf6d9bc0b4be4cf23efaf564ed4','plpgsql',true,'v',false),
('platform.knowledge_owner_read(uuid)','287ffe30f39b032a2a687c6ebcb1b863e7d5e0cb128d8de312a72fe7bf8ab07e','plpgsql',true,'v',true),
('platform.knowledge_plan(text)','ca5a10644839c0c953c774164b5fe0d381ca94efe547c803047116ba39ffd6b0','plpgsql',true,'i',false),
('platform.knowledge_projection(platform.ai_runs)','507393c915bdc73cc8c566b7bf3cb62ad5c177b0ea68b7b7367acdb64a2d43af','plpgsql',true,'s',false),
('platform.knowledge_query_apply(uuid,uuid,uuid,uuid,uuid,jsonb)','459b65e5a74b6d69db5d45df9aec6b0cd063aae6988df12e587a5d5670fd4c8b','plpgsql',true,'v',true),
('platform.knowledge_query_reserve(uuid,uuid,uuid,jsonb)','27f88286d8f9ca56d94a1746acb2134d19e7abfc592035c001c1597ba94b6f30','plpgsql',true,'v',true),
('platform.knowledge_query_text(platform.ai_runs)','469e436d447aa95b851f496d04d25c74eb81c2d90d826803be4100f4976cba0e','sql',true,'s',false),
('platform.knowledge_refs_valid(jsonb)','268218810b11013177caae64ed9dc87b356c81250d9eed7c986a9018bf58e320','plpgsql',true,'i',false),
('platform.knowledge_release_eligible(uuid,uuid,uuid)','3f66e97fc2fa974c00841c25880bf4558bca81a7fc59d05c698620cc5318aaf2','plpgsql',true,'s',false),
('platform.knowledge_runtime_current(platform.ai_runs)','c1c2c16a2c90e8a4d75b37aec8c4695dfcb7a42b56b4df92a206c5445c9f33c8','plpgsql',true,'v',false),
('platform.knowledge_runtime_read(uuid,uuid,uuid,jsonb)','e861159f7f70d825715d5d09bf4c599a08c1dbfa315d75b3f937ce63e1e7f004','plpgsql',true,'v',true),
('platform.knowledge_search_pin_valid(jsonb)','deee343f7367c1009e8a1047ff1459cd8840be5eadf0b108359ffbba701faa24','plpgsql',true,'i',false),
('platform.knowledge_search_schema_profile()','cf34e26318a521e4b02103597962c97b03f89c74990937264db6c7b0236e3c46','sql',true,'s',false),
('platform.knowledge_select(platform.ai_runs,extensions.vector,text)','d2c8a6db1d9503daf73eaa97696095d9fd316b3b3370f7cd820b80049341d8c2','plpgsql',true,'s',false),
('platform.knowledge_sources_hash(uuid,uuid)','deb8bce83c9d6ba25816ab11a2495dea12147951db86d5f9d4db22fb44570a63','sql',true,'s',false),
('platform.knowledge_vectors_valid(jsonb,integer)','2a0dea2e4902e5610fbde9c087087658ba660e9949bf4550ad365b4a1bb39a76','plpgsql',true,'i',false),
('platform.material_apply(uuid,uuid,uuid,jsonb)','529e701178043d44c7e5cbee6c4651fae3e6a3a6be36412764ac1e8b60ac7c39','plpgsql',true,'v',false),
('platform.material_apply_context(uuid,uuid,uuid,boolean)','22636529fed5a35055d99e9a42f52615626150300ad08d62918bbbfc9bce3069','plpgsql',true,'v',false),
('platform.material_bind(uuid,uuid,boolean,uuid)','8afd09d2d0576c14480ce5a5414aa5d924082a007888932aec43dec185a19408','plpgsql',true,'v',false),
('platform.material_bump_turns(uuid,uuid[],uuid)','0019faf314594758579f035373f6e5d14d37a4cb9d3b75b4bb9c0a0116e09020','plpgsql',true,'v',false),
('platform.material_content_valid(jsonb)','c89faf57741e2b8d179b4201aac7979e891984e867ecb27bfc455a66c0104da4','plpgsql',false,'i',false),
('platform.material_fold(uuid,uuid,uuid)','74d5202cf7fe15ae866dbd81eb88e635564a189db0195a9c0311c15fe76cecf8','plpgsql',true,'v',false),
('platform.material_identity(uuid,uuid,jsonb)','d4bb3911e0b35af35585df2307496147b4c02ab6ac6b4869fe53a3445eb9dca3','plpgsql',true,'s',false),
('platform.material_integrity()','292dd9cbb24f1d2289b6e6b628160a8755841ecc4fbc4ab2a26a3c5c54cab7f7','plpgsql',true,'v',false),
('platform.material_no_file()','5b01911a52d5fc64edbf23895a31d8316d34221fc4c399524f4932f4496ef892','plpgsql',true,'v',false),
('platform.material_object(jsonb,text[])','aa02c1b4b7f6ad7ac3687dccee0f680b231876af0bc78d5d149b4cc6d08d40bf','sql',false,'i',false),
('platform.material_process(platform.messaging_jobs)','351d28449ee12317a4f046b8f70998b0e51206954146e45e91a6491995cdcd09','plpgsql',true,'v',false),
('platform.material_processing_replay(uuid,uuid)','5d04cfdae703e4786f4d61975d484ec2c1686fcbec620c98e33dab7eafe94a96','sql',true,'s',true),
('platform.material_result_valid(jsonb)','6070c0641ab897095effdd4f841e0e34e8cc1b788d33dd64c5ef6d4cf2f6e9b6','plpgsql',false,'v',false),
('platform.material_semantic(jsonb)','f1ec36fd862ecf60cd69b1f1d1e41b7c09cfab38a689f6127d0969541985bb92','sql',false,'i',false),
('platform.material_state_valid(jsonb)','a2344f16e36d45187529757a8bd2c9fad1f0b2c6c6887ab81b631279a65f10c1','sql',false,'i',false),
('platform.material_suppression_check()','6d19f17d542008095defb943095c9f9c894aa7441123806b24df110903cbaa52','plpgsql',true,'v',false),
('platform.material_target_check()','0c41bd7a4b3399c47a7cae6707e9bb28d98ed248e687b26ec58c094a9c6dd7b1','plpgsql',true,'v',false),
('platform.material_turn_usable(uuid,uuid)','9f2f31ab578bb9d66f1bd8ed9d57f6dd9ae5a06b9427c1138d85f8121452c893','sql',true,'v',false),
('platform.message_effective(uuid,uuid)','bb68c0a9240ef18ecf1112a4467f0f2eaa6fd4cc72ec2276423cd77accff0d7b','plpgsql',true,'v',false),
('platform.messaging_admit(uuid,uuid)','27d0551d90b2f854b54a8b9fff35ff92bff9b131de4653000015026460fefc31','plpgsql',true,'v',true),
('platform.messaging_begin_send(uuid,uuid)','ced9aced8fef1976bae75cedc268ed5a25b651c01fb276502bcc77badc8453e1','plpgsql',true,'v',true),
('platform.messaging_claim(text,timestamptz,timestamptz,uuid)','1e88ecfd996f7b98034e20a8b8143de35ca3e576d252c182e89f61ea27bcad01','plpgsql',true,'v',true),
('platform.messaging_fingerprint(jsonb,boolean)','d64c3b2ea0f53e0861315883b7420e5aee652b28dffa093bce0d3fff2986a342','plpgsql',false,'i',false),
('platform.messaging_finish_send(uuid,uuid,uuid,text,text,text)','4c6db15c26212a1a943e58eaf3f6355988380106a2be7ed04832ab6c8c673a0b','sql',true,'v',true),
('platform.messaging_finish_send(uuid,uuid,uuid,text,text,text,integer)','6cbcc9ca7875728a015ddd3e7fa23a88f999d03824a5e652203329efd09d1dba','plpgsql',true,'v',true),
('platform.messaging_guard(uuid,uuid)','0a57433b9b39446547a2f2accfeb9516238ae8c9210f67773e30f749a756adb5','plpgsql',true,'v',false),
('platform.messaging_immutable()','3971e82a86a3826eeaf7b9e24458fbb1adc64cce0e8f2cb43a46384348519934','plpgsql',false,'v',false),
('platform.messaging_ingest(text,text,jsonb,uuid)','2833a40d4ec37a014eab30fcbe2893a590d50c909b71eebc754e1c575ecb9f32','plpgsql',true,'v',true),
('platform.messaging_job_json(platform.messaging_jobs)','7ccc5395def311a662f2b4845b33ce5e85af7c94d5920ddb03b97bcb2d37a5f3','sql',false,'s',false),
('platform.messaging_lock_billing()','69f212c164437a4b39942e87f32c53df5cb4fb8e5f2bf9da2e1952e98be180eb','plpgsql',true,'v',true),
('platform.messaging_lock_billing_workspace(uuid)','8797320c11ace5b9c44b37ed511293f0f61af6c0ba1b58abcd5cd60b5ec27204','plpgsql',true,'v',false),
('platform.messaging_lock_owner(uuid,uuid)','11168bbd30eec24cfdb0ad9de67c70f767c0bf62480c7579638e58ecfb42bce1','plpgsql',true,'v',false),
('platform.messaging_manual_send_allowed(uuid)','4ce13d4ca64dbc09aada275a295d76a01a08ac809768a2448fb1e1f074cd4bd6','plpgsql',true,'v',false),
('platform.messaging_prepare_text(uuid,text,text)','39c14deb5337876f28970605ea399f9106f5e768e9f8f8c54b2e3746d570bca9','plpgsql',true,'v',true),
('platform.messaging_process_inbox(uuid,uuid)','5a63a698c440120cebeaf4c6ebf8133f04abf41f610ef2ad3c3e34312b4ef2e3','plpgsql',true,'v',true),
('platform.messaging_read_connections(integer,timestamptz,uuid)','242c6123fd6c57c44eb8c9ff658fe437700144b9e6525fff6c2ccf24c892511b','plpgsql',true,'v',true),
('platform.messaging_read_conversations(integer)','aaeb0c33dd9e7501e92c3bcb599e38073bfeef8c3f3b7352cd22ef4a4b60e040','plpgsql',true,'v',true),
('platform.messaging_read_conversations(integer,timestamptz,uuid)','81949cfd2357e8886003e7c5618fed4a7ce2b4d4474c2764c377783e97ed9658','plpgsql',true,'v',true),
('platform.messaging_read_delivery(uuid)','f3cdd1d7de19b740961b0f4a6aece317b4fdd4ef1dafcfc9ce25ab6908bc29ed','plpgsql',true,'v',true),
('platform.messaging_read_inbox(uuid)','7666d3eb0bc87de36bb75b4a7a8f9ab4e31f329f5fcd2fbaccc275d819b6d171','plpgsql',true,'v',true),
('platform.messaging_read_messages(uuid,integer)','fcfa6f29a181d0e97ce52ae98ec0d008859e6568ad118e89234a5ed5b932a460','plpgsql',true,'v',true),
('platform.messaging_read_messages(uuid,integer,timestamptz,uuid)','d9d749ed13a17d253ec6369b4a1b52c5a166cd9f51c7d9c5c999a827a2f5942d','plpgsql',true,'v',true),
('platform.messaging_recover_expired(timestamptz,timestamptz,uuid)','4ebe01b000f3d9da6cb3d45e2d7e2d22d4b4d773cef5d44bbf279bae6e8d206a','plpgsql',true,'v',true),
('platform.messaging_request_text(uuid,text,text)','13dc01a5b25f4b2d5da4835fa8aabf14f33f98573532e730929006688be7059c','plpgsql',true,'v',true),
('platform.messaging_reschedule(uuid,text,boolean)','6409aa21554ccaa346587c2f4da07bc6941e27c4736db9bd518f26e4c7947438','sql',true,'v',false),
('platform.messaging_reschedule(uuid,text,boolean,integer)','21e8b16de21a18ff5646eeb28f7eceb801da8ab5bfc7d8e1799e6a91b9a2d074','sql',true,'v',false),
('platform.messaging_reschedule(uuid,text,boolean,integer,boolean)','beba5651f47d8fe17d7d9fe3faa4c66242dc17bc94c78170a6301320c6ec6347','plpgsql',true,'v',false),
('platform.messaging_retry(uuid,uuid,text,boolean)','087a5b1c00ca662ee70824437e819d8ff3296df76e8d2013abc639e4b6f980f5','plpgsql',true,'v',true),
('platform.messaging_valid_id(text,integer,integer)','9e1cf327f38fa1437a5a755e3c68d531c0209b585722755c865b395f616419f5','sql',false,'i',false),
('platform.messaging_validate_event(jsonb)','1f7a2405bde9171aa196355bfae185cbc4084aeffbbdfda20d4f8828fdb95791','plpgsql',false,'v',false),
('platform.portfolio_analysis_query(platform.vision_analyses)','e93ce052dee1ef828d8c62e065839593d39020f9d0313d0b114de6bb4a379357','sql',true,'s',false),
('platform.portfolio_analysis_view(platform.vision_analyses)','b72ff76e7b7ba0186565966ea46b08e108425c13add3bf84466c8a37bd695617','sql',true,'s',false),
('platform.portfolio_attributes_valid(jsonb)','5abdce55307335325b3eceb300cd24ca4ad809b101d77f4fe9ac8035ab11b1f5','plpgsql',true,'i',false),
('platform.portfolio_auxiliary_cost(uuid,uuid,uuid,uuid,jsonb,uuid)','a416cffa366268714d9d7f16c8ac448786919e3ca814fca127d1fa3b6b992ad7','sql',true,'s',false),
('platform.portfolio_availability(uuid,uuid,uuid,bigint)','432252608679d18b7af1cfeb4f4e9d9e0f4d8681f88253de1888afe071ae8dc4','plpgsql',true,'s',false),
('platform.portfolio_build_apply(uuid,uuid,uuid,jsonb)','53005646855e2aabf7f0b54a9be785ab7f4c097b7f49ab3abf322c17940d44bb','plpgsql',true,'v',true),
('platform.portfolio_build_create(uuid,uuid,uuid,jsonb)','82f645ec4455b119eb81e030b9111a5fe316fc0dada2e11af6de1158e2c51518','plpgsql',true,'v',false),
('platform.portfolio_build_reserve(uuid,uuid,uuid)','7cce9556aa90d5d3bfdaa8f7f8570166c40029cf023638712d42553c85ea7957','plpgsql',true,'v',true),
('platform.portfolio_build_valid(uuid,uuid,uuid,boolean)','0991d6bc039b8c2be4cb105a4fe0d718736f6cc36c0438d3ddce9e1f40da9819','plpgsql',true,'s',false),
('platform.portfolio_cleanup_claim(integer)','ec424d412e013af8bbeb2928348f872e2825a1af4eb48b739eccead450f484de','plpgsql',true,'v',true),
('platform.portfolio_cleanup_complete(uuid,uuid,text)','47aff27b1c3a3074e17335958b3f669505d3850883a828b682cb174c55bd1f8c','plpgsql',true,'v',true),
('platform.portfolio_client_guard(uuid,uuid,uuid)','f5cb47236138fdd8e29a809cf53a77d7be65114292187a00a4d7dc905b71a43a','plpgsql',true,'v',false),
('platform.portfolio_clip(text,integer)','1daf26cfba3cb3786ea276448a143c857add55ccb06cf2ac77c9d52e1ac4804a','plpgsql',true,'i',false),
('platform.portfolio_conversation_read(uuid,uuid)','6c51b0d119ad04f08c3a2da3d813fcf5ab9007258eac8fec662ab2c2fa126186','plpgsql',true,'v',true),
('platform.portfolio_delivery_attest(platform.messaging_jobs,platform.ai_runs,jsonb)','829c12122db7f409706acc85eab5bc9f5f1122a5dcda40ef1f15d22a68364abf','plpgsql',true,'v',false),
('platform.portfolio_delivery_begin(uuid,uuid,uuid,bigint,bigint,jsonb,text)','671251ebf476c91f98c5d6c71b3436418e1f3f34394c3a8f80f6f4aa2f7bc0ff','plpgsql',true,'v',true),
('platform.portfolio_delivery_current_valid(jsonb)','0afa2b97c307693bd803ba179c17b973118f80b25dafd60ef62aa3126b03fdca','sql',true,'i',false),
('platform.portfolio_delivery_eligible(platform.ai_runs)','8eb83ee8c1028cec33ac026ec8619e4efb7af8d4ebd777b85d54b37c1fa5bb0a','sql',true,'s',false),
('platform.portfolio_delivery_immutable()','1b26b5780fc46363019a7c5a8b17426a549a556793a3e3158a69433826576512','plpgsql',true,'v',false),
('platform.portfolio_delivery_intent_current(platform.messaging_jobs,platform.ai_deliveries,platform.ai_runs,platform.portfolio_delivery_intents)','d469e850a3c1cad8f2787634f8c87a94606fb55113ea5512c07700a163feb8ae','plpgsql',true,'v',false),
('platform.portfolio_delivery_manifest_valid(platform.portfolio_asset_versions)','ee9bd049b1f34cba0964f6c8ad79d70af159926e63f38a4778862c1431879dd8','sql',true,'i',false),
('platform.portfolio_delivery_message_current(app.messages)','d0cf32bf455805f9225f65314738e58d4788ed78910db2e9be4f98c0de194a23','sql',true,'s',false),
('platform.portfolio_delivery_read(uuid,uuid)','0c9d8658c39e7ad389fca988f31eb0970f65b76d58ce66cd79658374f9c19f64','plpgsql',true,'v',true),
('platform.portfolio_delivery_result_valid(jsonb)','939c9cc596e95a4b34f2c3aea2aef13d714d608dcb4239bf01ced89fba4fd7d2','plpgsql',true,'i',false),
('platform.portfolio_delivery_schema_profile()','499d3b25887b3dd50f0a2f8f7e7b324d8cca226a270a3dd99e5506e376733bf0','sql',true,'s',false),
('platform.portfolio_delivery_selection_valid(jsonb)','f7cad56274eaee2f77862a88e41e13e9836f343096c0d7bbd79607ab483bec5f','sql',true,'i',false),
('platform.portfolio_delivery_session_lock(uuid,uuid,uuid,numeric)','33bc31ad79cc21a61bd8720ff2aea1ececca52b0fac3e0f320d6426f8279c913','plpgsql',true,'v',false),
('platform.portfolio_delivery_source(platform.ai_runs,jsonb)','531c7a5f0be3c208a1925ceaca3e44e7e6b89f87f680b02fe3ab4212eb903db9','sql',true,'s',false),
('platform.portfolio_embedding_wire(jsonb)','622fa395f652d59a99ef80f5ecf3799677f5afde640231505e1d7798024864a1','sql',true,'i',false),
('platform.portfolio_immutable()','2eae411a3c35ccbef14852e62453e1489bacee416637ac59727dd213f0805244','plpgsql',true,'v',false),
('platform.portfolio_invalidate(uuid,uuid,uuid)','4eb7d16be630508c98072762cbd8b2fa484c5adf09b44dbd15dcd310e9217ab8','plpgsql',true,'v',false),
('platform.portfolio_items_hash(uuid,uuid)','b6e98ba33a55365230bbb07ec4e148ab50f6508a7a7b784b2d2ed2e1253116a5','sql',true,'s',false),
('platform.portfolio_manifest(platform.portfolio_asset_versions)','de6ae7a3eb0b6b3370317caf3a6a92ef52990a01d38604d7f2d079185ba85e13','sql',true,'s',false),
('platform.portfolio_media_pin(uuid,uuid,uuid,uuid,boolean)','8db3d248ad6275aa16bb193b9fcf8272c6f895dab57c359fefaf81a64cbe193c','plpgsql',true,'s',false),
('platform.portfolio_media_pin_valid(jsonb)','9ee77be6c2f01104a0e92581da325ae9ffa6a0f09ff0542f74e272845a6bf78a','sql',true,'i',false),
('platform.portfolio_owner_command(uuid,text,text,jsonb)','4980b9469e2c2e4ca2782af12427cd9ccf7f1d3ac9ba48c475945648d89943f9','plpgsql',true,'v',true),
('platform.portfolio_owner_lookup_apply(uuid,uuid,uuid,jsonb)','07246671899bd414436563583e4a6e470cb6a2117e676847c7ef67b7efae38e6','plpgsql',true,'v',true),
('platform.portfolio_owner_lookup_reserve(uuid,uuid,uuid)','7e3c5a5971769523f4b4806bfbd46d2d416741376d7dca082b9e424c87422d8c','plpgsql',true,'v',true),
('platform.portfolio_owner_read(uuid)','5e5e725c919385ef27315f076644e8b97a79acea5d1c8a521fa00b3c5dffd34e','plpgsql',true,'v',true),
('platform.portfolio_pin_valid(jsonb)','e8c532b48fda863e0f9140633bbb1893bae50c9df88ea708310d123264f68a94','sql',true,'i',false),
('platform.portfolio_preview(uuid,uuid,uuid)','c75999a600839989ca5ea44376c5841ea0f1bb940585013c2d6b4722eff58b47','plpgsql',true,'v',true),
('platform.portfolio_projection(platform.ai_runs)','64eac804a77248bd0961d96dd05af32a97a6e4a8a71db8b2d3f6804b1cd429ad','plpgsql',true,'s',false),
('platform.portfolio_purge_begin(uuid,uuid,uuid)','20d1b99bf5de769ff2013379528c6f4015fb4a0a942b97a651cddbfa72339eb3','plpgsql',true,'v',true),
('platform.portfolio_purge_complete(uuid,uuid,text)','bf2c5c852a1d2d77353142ea864a9684ac94b1e287e6a726d48d14ad8b14fbe4','plpgsql',true,'v',true),
('platform.portfolio_query_apply(uuid,uuid,uuid,uuid,uuid,jsonb)','7122c29e686118f85615077e31fb028e0c62c49ece6e130e17a169549b31016e','plpgsql',true,'v',true),
('platform.portfolio_query_reserve(uuid,uuid,uuid,jsonb)','6a09996a8f49197c6fb717335ed560950880b75bc756227b840ff1c18422cca2','plpgsql',true,'v',true),
('platform.portfolio_refs(jsonb)','9b992ad8ecdea455a2303458f421a2c1e171d5f6e38a9fc136f307d1bd6e0624','sql',true,'i',false),
('platform.portfolio_refs_valid(jsonb)','bfb584ddfdabb7407cf68878313e454bd74219a943dc57324555e589132031b5','plpgsql',true,'i',false),
('platform.portfolio_run_query(platform.ai_runs)','d3ebd9e619af66505665438a41577f20a3ccde6b051b0d02be1fdf3ace1d4423','plpgsql',true,'s',false),
('platform.portfolio_runtime_current(platform.ai_runs)','56de471d2925698628801d6ed1ae36a061c3bf3f1cb7d9e23ad6b3f5dce60d20','plpgsql',true,'v',false),
('platform.portfolio_runtime_data(platform.ai_runs)','cce4d3f8a3eb252b2be0432744d69656631cdd8619264276b3d292747c54c70f','plpgsql',true,'s',false),
('platform.portfolio_runtime_read(uuid,uuid,uuid,jsonb)','f81e46fee79022a4022568608b0ea3245f450255454b085ab44e145538be1c64','plpgsql',true,'v',true),
('platform.portfolio_schema_profile()','df2ab97e8fe09ead37d2dd16f70526f4f47073eaed3314686ceb319e7773d06b','sql',true,'s',false),
('platform.portfolio_select(uuid,uuid,jsonb,extensions.vector,text)','39460c29d3c4dcbf5efb4d3f044e8db4bdb89554a5cf3ced30df436b1a57249a','plpgsql',true,'s',false),
('platform.portfolio_session_admit(uuid,uuid,jsonb)','17ec13ddc4c460ce0a79fdd1b0d8884259d683fa049e937bae6fe4136042f09f','plpgsql',true,'v',true),
('platform.portfolio_session_lock(uuid,uuid,uuid,numeric)','386ace56e6fd2a11ce9f83c4685811533f390557b260536b0f203076d5965b97','plpgsql',true,'v',false),
('platform.portfolio_session_usage(uuid,uuid,uuid)','51057dd53b2f15951fcb63b1282d7581ba94217cff81d4271bf4d4d744623a41','sql',true,'s',false),
('platform.portfolio_text_valid(text,integer)','d98c95fcb948cb7f6afad5f26a93440629661e7991f3f8d8055644e95272354d','sql',true,'i',false),
('platform.portfolio_upload_begin(uuid,uuid,uuid,uuid)','1313e4b020befeff7a0b7d3519bf22fdf24026df2ae8f10e8677fda9d37e498e','plpgsql',true,'v',true),
('platform.portfolio_upload_complete(uuid,uuid,jsonb)','684afc3d4e29f69610835373455a2e5613dc6cbba8993290cb6210b7e4152dad','plpgsql',true,'v',true),
('platform.portfolio_upload_prepare(uuid,uuid,uuid,uuid,uuid,jsonb)','eb895fcd29065e34d54b400368d59153bca5fecce3b179df55768642bda878e4','plpgsql',true,'v',true),
('platform.portfolio_upload_recover(uuid,uuid,uuid,uuid)','e1c66eb556121f8e3d895d4bdafcff271936936e1be0fc341245e50c43d93167','plpgsql',true,'v',true),
('platform.portfolio_version_private(platform.portfolio_asset_versions,uuid)','7c8a9f7ba78c0da2b8cc36d876495cd55c947231e2d0b945b9240a2f3d61df91','sql',true,'s',false),
('platform.published_knowledge_schema_profile()','93c1c8615c17619929194606686ebd21b7f99afa7698cfd425bb6b65035137f5','sql',true,'s',false),
('platform.resolve_workspace_membership(uuid,uuid)','8ce9bdd67c17bc83442bea3a5e7a15337a51074e0ea6408855b10542e39ceb39','sql',true,'v',true),
('platform.service_request_owner_create(uuid,uuid,text,jsonb)','45874c3ff85dd8b1b090b7dbce353ab36b96d0bddc495996efb597df4efeb8ec','plpgsql',true,'v',true),
('platform.service_request_owner_read(uuid,uuid,uuid)','4d7a6b09b54341176b12f315c6c08d21c654f891403bb93216070890cf3b6ea3','plpgsql',true,'v',true),
('platform.service_request_owner_scope(uuid,uuid)','68d56b048f60af95d6cc0280d2219ac18f467cb18403f5e252157533c1e26a8a','plpgsql',true,'v',false),
('platform.telegram_begin_send(uuid,uuid,bigint,bigint,jsonb)','c8f15c23837fa40b86451574ee3e04cc4292dd91b2929a891424e0d8acec556d','plpgsql',true,'v',true),
('platform.telegram_can_send(uuid,uuid,uuid,boolean)','b273ad02ca6825bdf6b037173c3be840a615d551283c3e922357bee3f7f16811','plpgsql',true,'v',false),
('platform.telegram_fingerprint(text,jsonb)','449929a9e41d6e4f38d30341fcb7c7a488d55f06169dbaca2c18df461effdc06','plpgsql',false,'i',false),
('platform.telegram_fingerprint_v2(text,jsonb)','4499d0bd8bc0ad010d856d3e20b21847a9cfedfaeced5c14ace118443c2a940f','plpgsql',false,'i',false),
('platform.telegram_ingest(text,jsonb,uuid)','0b4d1cc97c47522e9abde484362aad3cd4967ae9c256e7719d310c09702f7c09','plpgsql',true,'v',true),
('platform.telegram_numeric_id(text)','1519829aa6e3dfc1ac03180377c72929d7a7a3dcedd1b037ae7d3ea4872413cf','sql',false,'i',false),
('platform.telegram_owner_observe(uuid,bigint,bigint,jsonb)','8ecd18d13fe815311aa9b076b3313efb98bbc3276962c44932516c5692666380','plpgsql',true,'v',true),
('platform.telegram_probe_json(platform.telegram_connection_state)','bce40873beb21b5aa8c5b850468f9f5fce85a865a60567066129998f75e0c273','sql',false,'s',false),
('platform.telegram_receipt_json(platform.telegram_update_receipts,text)','d6c81a402d8c8b53aab72685cff893e34100973ed8c7a2aefa2ab3e9a6ef5800','sql',true,'s',false),
('platform.telegram_replay_v1(text,jsonb)','a3598d76df2c0bf876945fa306e0410e3249c2018ff62b21e4da2968beaacf32','plpgsql',true,'v',true),
('platform.telegram_save_observation(uuid,uuid,bigint,bigint,jsonb)','97d4fe38521a276d4aac005feddf587a6c296e5e58ca909167cbcbb123be4816','plpgsql',true,'v',false),
('platform.telegram_validate_observation(jsonb)','5aefbca98cb203f4bfc5e65101fbb6432c492858ac55fdae0b48fec520855ffc','plpgsql',false,'v',false),
('platform.telegram_validate_projection(text,jsonb)','0d088863a241460dcc16b7ea45072bb7ac03303bfba9f4d2e13e0b91b5e4500b','plpgsql',false,'v',false),
('platform.telegram_validate_v2(text,jsonb)','7304efba94d26f93ba4d7a69030878056eb611f855ee4620a3ea6cdf61f79003','plpgsql',false,'v',false),
('platform.telegram_worker_probe(uuid,uuid)','9d8aa7df2e545161463af049002faf93d152a41339c665a32e133c03761139db','plpgsql',true,'v',true),
('platform.turn_consumer_finalize(uuid,uuid,jsonb)','e6b87fe26f51c45161000665e4221c11ed48a307608cb352cbd0706aa308d759','plpgsql',true,'v',true),
('platform.turn_consumer_replay(uuid,uuid)','4469b30f0df26f6bfb02777b2c5c8da184abc5b3bcae8dcdf45c871d9bbb7e6c','plpgsql',true,'s',true),
('platform.turn_enqueue(uuid,uuid,uuid)','383110c7c42c8979410560f3d0d98b784844f5da16a0a1d7f8d04fb71bd26e5f','plpgsql',true,'v',false),
('platform.turn_execute(uuid,uuid)','3bbd3e507d1b11425c2541d8300ca9d9e2c4cda172b77c05e2cc94b8d19c3b0d','plpgsql',true,'v',true),
('platform.turn_group_message(uuid,uuid,uuid)','89687e327f17d1a00751192fda5a56e7aeac8297b539fe95b1317d01de8d78f7','plpgsql',true,'v',false),
('platform.turn_immutable()','bfc42050fa3442c8eed763a861d16ae7fc6ea3f5f3646a193e54fe22704a7df9','plpgsql',false,'v',false),
('platform.turn_ingress()','d8e6040eae9ce55f0e6d8f2b1338d4ea2e3b6b8a7d25f2e7da8963032e6488f0','plpgsql',true,'v',false),
('platform.turn_material()','be30caa9fdb5cf0c3ca22e41559232e6cbe8d6246c62e9c343db539ec4303f3d','plpgsql',true,'v',false),
('platform.turn_member_check()','8cbbd5b8ccd97858edc24ba68fd904e5b4af3068b355e506d7d5cc03af5b6293','plpgsql',true,'v',false),
('platform.turn_members_consistent()','3acccfede293794fcc84890da99535a2730217fd1f11eb37c7ed153e2c675405','plpgsql',true,'v',false),
('platform.turn_preflight(platform.messaging_jobs,boolean,boolean)','fac7b52770d6129f0f01cd48411157552d4a43153eecfb7c3d7a8bf60d7d43f7','plpgsql',true,'v',false),
('platform.turn_require_isolation()','ba0e99b67e71fc6d6fa6886967282f9c5bcf7b0046e5812d34dfdfc5df8dd5d3','plpgsql',false,'v',false),
('platform.turn_seal(uuid,uuid,timestamptz,uuid,boolean)','bc83afb9ce59538928edfe86cdc74c7ab1951640244570d05177aa3bcd08676f','plpgsql',true,'v',false),
('platform.turn_snapshot(uuid,uuid)','ffac09fed2777b0439558faa5b071445fb1d6c74e605ff7331e29b67788e9e3e','plpgsql',true,'v',false),
('platform.turn_supersede(platform.messaging_jobs)','6a26f30e71da741ab60ca4c4a191fa44aab528f36588a564bcb5a0069f8eeab2','plpgsql',true,'v',false),
('platform.update_billing_contact(bigint,text,text)','80d0ce6854e33601584fe350ee4b586796d0066b6288bf9a26aeec80aa23f3ed','plpgsql',true,'v',true),
('platform.vision_apply(uuid,uuid,uuid)','729cfc85ebc52093cf7de488c165f5d8cee1313da9211d54d186610ccb60f9d6','plpgsql',true,'v',true),
('platform.vision_authorize(uuid,uuid,uuid)','6db16bbc758b9ca99a7c8ce64bf3d36dfdd06d7580ac679d53fd42a5c3b007d5','plpgsql',true,'v',true),
('platform.vision_client_reserve(uuid,uuid,uuid)','09fa5f373008fbb380834d34a42bc6bfedd98932b1e6506e340809be601e49dc','plpgsql',true,'v',true),
('platform.vision_complete(uuid,uuid,jsonb)','33c0cd63931508bd2e8396f9a22ee809ee101030d8f226899a561eeef273b973','plpgsql',true,'v',true),
('platform.vision_owner_reserve(uuid,uuid,uuid,uuid)','4fe5c0d0b5e23c227d7c9fbef1b8a3aaccb2d537d1e6375198c887dc9894d711','plpgsql',true,'v',true),
('platform.vision_private_reserve(uuid,uuid,text,uuid,uuid,uuid)','efb991868e4a66746ebfbdac038f106d717177beee332f74ea024c6f6037685c','plpgsql',true,'v',false),
('platform.vision_result_valid(jsonb)','8fbcaa4b9eb91b941e14c8163bea88042e97fe14c6336c35c007c87f80616eec','plpgsql',true,'i',false)),
 columns_expected(table_name,column_names) AS (VALUES ('app.audit_events',ARRAY['workspace_id','audit_event_id','occurred_at','actor_kind','actor_user_account_id','correlation_id','event_type','object_type','object_id','object_version','payload','billing_account_object_id','message_object_id','conversation_object_id','conversation_control_generation','escalation_object_id','escalation_operation','material_target_id','material_source_receipt_id','native_revision_id','native_policy_receipt_id','native_connection_id','native_conversation_id']::text[]),
('app.business_members',ARRAY['workspace_id','id','business_id','user_account_id','name','role','status','version','created_at']::text[]),
('app.businesses',ARRAY['workspace_id','id','name','status','version','created_at']::text[]),
('app.channel_connections',ARRAY['workspace_id','id','business_id','provider','bot_identity','external_connection_id','status','version','created_at','human_context_policy','human_context_policy_epoch']::text[]),
('app.client_identities',ARRAY['workspace_id','id','client_id','provider','external_user_id','created_at']::text[]),
('app.clients',ARRAY['workspace_id','id','version','created_at']::text[]),
('app.conversation_turn_messages',ARRAY['workspace_id','message_id','turn_id','conversation_id','connection_id','direction','content_type','origin_inbox_id','turn_ingress_at','turn_ingress_seq','file_id','membership_form','initial_suppression_id','suppression_disposition']::text[]),
('app.conversation_turns',ARRAY['workspace_id','id','conversation_id','connection_id','provider_chat_id','revision','control_generation','state','policy_version','debounce_ms','group_ms','media_ms','max_members','member_count','media_group_id','first_ingress_at','last_ingress_at','hard_at','quiet_at','media_deadline_at','seal_time','closed_at','ready_at','readiness','error_code','created_at','ingress_control_mode','activation_fence_seq','material_invalidated']::text[]),
('app.conversations',ARRAY['workspace_id','id','connection_id','business_id','client_id','identity_id','provider_chat_id','version','created_at','last_client_inbound_at','control_mode','control_generation','activation_fence_seq','human_observation_epoch','human_context_revision_id']::text[]),
('app.escalations',ARRAY['workspace_id','id','namespace','conversation_id','client_id','connection_id','turn_id','source_job_id','source_job_kind','source_job_step','source_claim_token','turn_revision','resume_receipt_id','control_generation','activation_fence_seq','input_context_version','waiting_context_version','request_snapshot','context_fingerprint','request_fingerprint','creation_result','reason','assignee_user_account_id','question','policy','created_at','due_at','second_reminder_at','expires_at','first_reminded_at','second_reminded_at','version','status','closure_reason','completed_at','answer_text','decided_by_user_account_id']::text[]),
('app.file_objects',ARRAY['workspace_id','id','message_id','connection_id','conversation_id','required_direction','required_content_type','status','winner_intent_id','winner_state','storage_key','mime_type','size_bytes','sha256','width','height','error_code','version','created_at','completed_at']::text[]),
('app.locations',ARRAY['workspace_id','id','business_id','name','status','version','created_at']::text[]),
('app.messages',ARRAY['workspace_id','id','conversation_id','connection_id','provider_chat_id','provider_message_id','direction','content_type','text','image_file_id','media_group_id','occurred_at','projection_fingerprint','version','created_at']::text[]),
('app.outbox_events',ARRAY['workspace_id','id','connection_id','message_id','kind','required_direction','status','attempt_id','provider_message_id','error_code','completed_at','version','created_at']::text[]),
('app.service_requests',ARRAY['workspace_id','id','business_id','conversation_id','client_id','intent_message_id','intent_source_version','release_id','service_id','service_name','template_revision','state','revision','facts','missing','conflicts','question','created_at']::text[]),
('platform.ai_deliveries',ARRAY['workspace_id','job_id','source_job_id','source_claim_hash','connection_id','turn_id','turn_revision','kind','step','run_id','selected_kind','message_id','outbox_id','send_job_id','escalation_id','intent_context_version','created_at','provider_session_id','knowledge_pin','search_pin','portfolio_pin','media_pin']::text[]),
('platform.ai_provider_calls',ARRAY['workspace_id','run_id','sequence','claim_hash','attempt_count','budget','completion','reserved_at','completed_at','portfolio_session_id']::text[]),
('platform.ai_provider_sessions',ARRAY['id','workspace_id','connection_id','conversation_id','client_id','chat_id','bot_identity','data_profile','starts_at','expires_at','max_calls','max_rub','review_sha256','review_checked_at','config','active','created_at']::text[]),
('platform.ai_runs',ARRAY['workspace_id','id','job_id','connection_id','conversation_id','client_id','business_id','kind','step','turn_id','turn_revision','resume_receipt_id','control_generation','binding','snapshot','snapshot_digest','storage_fingerprint','config','config_fingerprint','deadline','calls_used','reads_used','tokens_reserved','cost_reserved','read_audit','result','selected_at','winning_claim_hash','created_at','knowledge_pin','active_projection','knowledge_release_id','search_pin','search_refs','search_build_id','portfolio_pin','media_pin','portfolio_refs','portfolio_session_id','portfolio_build_id','delivery_read_audit','intake_pin']::text[]),
('platform.alembic_version',ARRAY['version_num']::text[]),
('platform.auth_credentials',ARRAY['user_account_id','login','password_hash','version','created_at']::text[]),
('platform.auth_sessions',ARRAY['token_hash','user_account_id','credential_version','account_version','created_at','expires_at','revoked_at']::text[]),
('platform.billing_contact_command_receipts',ARRAY['workspace_id','receipt_id','billing_account_id','operation','idempotency_key','request_fingerprint','expected_version','status','result_version','result_outcome','created_at','completed_at']::text[]),
('platform.business_configuration_receipts',ARRAY['workspace_id','business_id','id','operation','idempotency_key','actor_user_account_id','correlation_id','request_fingerprint','result','recorded_at']::text[]),
('platform.business_configuration_releases',ARRAY['workspace_id','business_id','id','source_draft_version','body','published_by','published_at']::text[]),
('platform.business_configuration_state',ARRAY['workspace_id','business_id','draft_version','draft_body','active_release_id','activation_version','updated_at']::text[]),
('platform.channel_routes',ARRAY['workspace_id','id','connection_id','provider','bot_identity','route_key','created_at']::text[]),
('platform.conversation_control_receipts',ARRAY['workspace_id','id','operation_namespace','operation','idempotency_key','conversation_id','client_id','actor_user_account_id','correlation_id','expected_generation','expected_context_version','previous_mode','accepted_mode','previous_generation','accepted_generation','context_version','activation_fence_seq','request_fingerprint','audit_event_id','audit_event_type','accepted_at','result','guard_profile','human_context_revision_id','human_context_policy_epoch','human_observation_epoch']::text[]),
('platform.duration_cases',ARRAY['workspace_id','id','business_id','version','state','data','asset_id','asset_version_id','created_by','confirmed_by']::text[]),
('platform.escalation_command_receipts',ARRAY['workspace_id','id','namespace','idempotency_key','escalation_id','conversation_id','client_id','actor_user_account_id','correlation_id','operation','expected_version','expected_control_generation','expected_context_version','accepted_version','accepted_status','accepted_context_version','request_fingerprint','audit_event_id','audit_event_type','accepted_at','result']::text[]),
('platform.file_object_uploads',ARRAY['workspace_id','id','file_id','job_id','claim_token','storage_key','mime_type','size_bytes','sha256','width','height','status','cleanup_claim_token','cleanup_lease_until','cleanup_attempts','next_check_at','last_checked_at','cleanup_outcome','version','created_at']::text[]),
('platform.human_context_observations',ARRAY['workspace_id','id','conversation_id','client_id','connection_id','provider_chat_id','epoch','policy_epoch','control_generation','first_source_receipt_id','classification','semantic_digest','accepted_at']::text[]),
('platform.human_context_policy_receipts',ARRAY['workspace_id','id','connection_id','business_id','provider','bot_identity','external_connection_id','owner_user_id','actor_db_role','namespace','idempotency_key','request_fingerprint','operation','expected_policy','expected_policy_epoch','accepted_policy','accepted_policy_epoch','change','source_profile','audit_event_id','event_type','accepted_at','result']::text[]),
('platform.human_context_reconciliations',ARRAY['workspace_id','id','conversation_id','client_id','connection_id','provider_chat_id','actor_user_account_id','namespace','idempotency_key','request_fingerprint','correlation_id','previous_revision_id','revision_no','expected_generation','expected_context_version','accepted_context_version','policy_epoch','observation_epoch','reviewed_ingress_seq','reviewed_input_state_hash','reviewed_gap_digest','reviewed_gap_overflow','disposition','context_text','source_media','attestation','audit_event_id','event_type','accepted_at','result']::text[]),
('platform.inbox_events',ARRAY['workspace_id','id','connection_id','provider','bot_identity','external_connection_id','required_direction','event_id','normalized_event','event_fingerprint','correlation_id','received_at','status','result_code','message_id','completed_at','version','turn_ingress_at','turn_ingress_seq','turn_control_generation','turn_control_mode','turn_activation_fence_seq','material_result','material_claim_token','human_context_source_receipt_id','human_context_observation_id']::text[]),
('platform.intake_escalation_links',ARRAY['workspace_id','escalation_id','business_id','conversation_id','client_id','pin','summary']::text[]),
('platform.intake_receipts',ARRAY['workspace_id','id','business_id','actor_id','command_key','request_hash','result','payload','created_at']::text[]),
('platform.intake_state',ARRAY['workspace_id','id','business_id','conversation_id','client_id','service_id','pin','category','facts','version']::text[]),
('platform.knowledge_build_chunks',ARRAY['workspace_id','business_id','build_id','chunk_id','position','batch_no','embedding']::text[]),
('platform.knowledge_builds',ARRAY['workspace_id','business_id','id','version','state','profile_id','preprocessing','manifest','manifest_hash','plan','chunk_count','created_by','created_at','deadline','error_code']::text[]),
('platform.knowledge_chunks',ARRAY['workspace_id','business_id','id','revision_id','ordinal','text','sha256','fts']::text[]),
('platform.knowledge_embedding_calls',ARRAY['workspace_id','business_id','id','kind','execution','build_id','batch_no','run_id','actor_user_account_id','claim_hash','profile_id','request_sha256','request_bytes','input_count','token_ceiling','ticket_hash','state','reserved_cost','reserved_at','deadline','outcome','completed_at','vectors_sha256','applied_at','query_vector','portfolio_build_id','owner_analysis_id','portfolio_session_id','portfolio_lookup_pin']::text[]),
('platform.knowledge_release_builds',ARRAY['workspace_id','business_id','release_id','build_id']::text[]),
('platform.knowledge_revisions',ARRAY['workspace_id','business_id','id','source_id','revision_no','title','format','canonical_text','canonical_sha256','source_label','author_label','service_id','category','claim_key','effective_from','effective_until','created_by','created_at','confirmed','confirmed_by','confirmed_at','confirmed_epoch']::text[]),
('platform.knowledge_sources',ARRAY['workspace_id','business_id','id','version','state','head_revision_id','confirmed_revision_id','revocation_epoch','revoked_at','deleted_at','created_at']::text[]),
('platform.message_initial_suppressions',ARRAY['workspace_id','id','message_id','target_id','origin_inbox_id','effect_id','source_receipt_id','previous_version','accepted_version','initial_material','fold_witnesses','membership_disposition']::text[]),
('platform.message_material_effects',ARRAY['workspace_id','id','target_id','message_id','source_receipt_id','audit_event_id','event_type','previous_version','accepted_version','reason','accepted_at']::text[]),
('platform.message_material_targets',ARRAY['workspace_id','id','connection_id','provider_chat_id','provider_message_id','message_id','conversation_id','client_id','direction','outbox_id','inbound_provider_id','required_sent','quarantined','original_grouping_closed','origin_identity','deleted','undated_seen','max_edit_at','candidate','dated_conflict','delete_receipt','undated_receipt','candidate_receipt','conflict_receipt','current_material']::text[]),
('platform.messaging_command_receipts',ARRAY['workspace_id','id','operation','idempotency_key','request_fingerprint','actor_user_account_id','correlation_id','message_id','outbox_id','audit_event_id','accepted_at']::text[]),
('platform.messaging_jobs',ARRAY['workspace_id','id','connection_id','kind','inbox_id','outbox_id','correlation_id','status','available_at','claim_token','lease_until','worker_id','attempt_count','first_started_at','error_code','completed_at','last_attempt_id','last_claim_token','last_outcome','last_provider_message_id','last_error_code','version','created_at','file_id','last_retry_after_seconds','last_retry_due','telegram_probe_claim','telegram_probe_generation','telegram_probe_version','turn_id','turn_revision','step','turn_outcome','turn_input','guard_rejection','escalation_id','escalation_outcome','context_block_reason','context_wait_claim_token','context_wait_result']::text[]),
('platform.plan_entitlements',ARRAY['plan_revision_id','capability_key','value_kind','enabled','limit_value','criticality','created_at']::text[]),
('platform.portfolio_ai_sessions',ARRAY['workspace_id','business_id','id','actor_user_account_id','conversation_id','client_id','profile_id','execution','eligibility','max_calls','max_cost','expires_at','created_at','revoked_at']::text[]),
('platform.portfolio_asset_versions',ARRAY['workspace_id','business_id','asset_id','id','upload_id','expected_asset_version','storage_key','mime_type','size_bytes','sha256','width','height','state','receive_ticket_hash','operation_deadline','put_outcome','recovery_ticket_hash','recovery_deadline','recovery_outcome','purge_ticket_hash','purge_deadline','purge_outcome','cleanup_claim','cleanup_lease_until','cleanup_attempts','next_check_at','last_checked_at','cleanup_outcome','created_by','created_at','expires_at','finalized_at']::text[]),
('platform.portfolio_assets',ARRAY['workspace_id','business_id','id','origin','version','epoch','state','accepted_version_id','pending_version_id','created_by','created_at','deleted_at']::text[]),
('platform.portfolio_build_items',ARRAY['workspace_id','business_id','build_id','item_id','revision_id','position','text','sha256','fts','embedding']::text[]),
('platform.portfolio_builds',ARRAY['workspace_id','business_id','id','version','state','profile_id','preprocessing','manifest','manifest_hash','wire','wire_sha256','input_count','token_ceiling','session_id','created_by','created_at','deadline','error_code']::text[]),
('platform.portfolio_delivery_intents',ARRAY['workspace_id','id','business_id','run_id','conversation_id','client_id','connection_id','message_id','outbox_id','send_job_id','item_id','revision_id','asset_id','asset_version_id','source_sha256','caption','request_fingerprint','context_sha256','read_ticket_hash','read_claim_hash','created_at']::text[]),
('platform.portfolio_items',ARRAY['workspace_id','business_id','id','asset_id','version','epoch','state','head_revision_id','confirmed_revision_id','show_permission','created_by','created_at','deleted_at']::text[]),
('platform.portfolio_release_builds',ARRAY['workspace_id','business_id','release_id','build_id']::text[]),
('platform.portfolio_revisions',ARRAY['workspace_id','business_id','id','item_id','revision_no','asset_id','asset_version_id','source_sha256','asset_epoch','description','attributes','service_id','analysis_id','canonical_sha256','confirmed','confirmed_by','confirmed_at','confirmed_epoch','created_by','created_at']::text[]),
('platform.saas_plan_revisions',ARRAY['plan_revision_id','plan_id','revision','publication_state','published_at','created_at']::text[]),
('platform.saas_plans',ARRAY['plan_id','code','display_name','status','created_at']::text[]),
('platform.service_request_receipts',ARRAY['workspace_id','actor_user_account_id','command_key','correlation_id','request_fingerprint','request_id','accepted_revision','effect','recorded_at']::text[]),
('platform.telegram_connection_state',ARRAY['workspace_id','connection_id','provider','bot_identity','external_connection_id','owner_user_id','generation','observation_version','observed_generation','observed_at','observation_xid','is_enabled','can_reply','error_code','material_enabled']::text[]),
('platform.telegram_provenance',ARRAY['receipt_id','codec','bot_identity','update_id','workspace_id','connection_id','inbox_id','projection','material_enabled','human_context_observation_id']::text[]),
('platform.telegram_update_receipts',ARRAY['id','bot_identity','update_id','fingerprint','kind','result_code','workspace_id','connection_id','inbox_id','received_at','codec']::text[]),
('platform.turn_consumer_receipts',ARRAY['workspace_id','job_id','connection_id','kind','turn_id','turn_revision','step','consumer','winning_claim_token','input_context_version','input_control_generation','snapshot_digest','result','accepted_at']::text[]),
('platform.turn_guard_receipts',ARRAY['workspace_id','job_id','winning_claim_token','connection_id','conversation_id','client_id','turn_id','turn_revision','resume_receipt_id','input_control_generation','activation_fence_seq','input_context_version','snapshot_digest','consumer','request_fingerprint','result_text','outcome','accepted_at','intent_context_version','message_id','outbox_id','send_job_id','namespace','kind','step','direction','content_type','send_kind']::text[]),
('platform.user_accounts',ARRAY['id','status','version','created_at']::text[]),
('platform.vision_analyses',ARRAY['workspace_id','business_id','id','source_kind','asset_id','asset_version_id','asset_epoch','conversation_id','client_id','message_id','file_id','message_version','file_version','media_pin','source_sha256','vision_profile','preprocessing','schema_revision','identity_sha256','state','session_id','reserved_cost','ticket_hash','reserved_at','deadline','completion','completed_at','matches','lookup_query_sha256','lookup_portfolio_pin','derivative_sha256','applied_at','invalidated_at','created_by']::text[]),
('platform.workspace_billing_accounts',ARRAY['workspace_id','billing_account_id','contact_display_name','version','created_at','updated_at']::text[]),
('platform.workspace_memberships',ARRAY['workspace_id','user_account_id','role','status','version','created_at']::text[]),
('platform.workspace_service_modes',ARRAY['workspace_id','service_mode_id','mode','reason_code','effective_from','effective_until','version','created_at','updated_at']::text[]),
('platform.workspace_subscriptions',ARRAY['workspace_id','subscription_id','plan_revision_id','required_publication_state','status','funding_mode','effective_from','effective_until','version','created_at','updated_at']::text[]),
('platform.workspaces',ARRAY['id','status','version','created_at']::text[])),
 functions AS MATERIALIZED (SELECT p.*,n.nspname||'.'||p.proname AS name,l.lanname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        JOIN pg_language l ON l.oid=p.prolang WHERE n.nspname IN ('app','platform') AND p.prokind='f'),
      tables AS MATERIALIZED (SELECT r.oid,n.nspname||'.'||r.relname AS name,r.relowner,r.relrowsecurity,r.relforcerowsecurity,r.relacl,
        array_agg(a.attname::text ORDER BY a.attnum) AS columns FROM pg_class r JOIN pg_namespace n ON n.oid=r.relnamespace
        JOIN pg_attribute a ON a.attrelid=r.oid AND a.attnum>0 AND NOT a.attisdropped WHERE n.nspname IN ('app','platform') AND r.relkind='r'
        GROUP BY r.oid,n.nspname,r.relname,r.relowner,r.relrowsecurity,r.relforcerowsecurity,r.relacl),
      validity AS MATERIALIZED (SELECT
        (SELECT count(*) FROM functions)=325 AND (SELECT count(DISTINCT to_regprocedure(signature)) FROM expected)=324
        AND NOT EXISTS(SELECT 1 FROM expected e LEFT JOIN functions f ON f.oid=to_regprocedure(e.signature)
          WHERE f.oid IS NULL OR encode(sha256(convert_to(f.prosrc,'UTF8')),'hex')<>e.body_hash OR f.lanname<>e.language
            OR f.prosecdef<>e.security_definer OR f.provolatile::text<>e.volatility OR f.proowner<>'asm_migrator'::regrole
            OR has_function_privilege('asm_runtime',f.oid,'EXECUTE')<>e.runtime_execute
            OR f.proconfig IS DISTINCT FROM ARRAY['search_path=pg_catalog, pg_temp']
            OR EXISTS(SELECT 1 FROM aclexplode(f.proacl) a WHERE a.grantee=0 AND a.privilege_type='EXECUTE'))
        AND EXISTS(SELECT 1 FROM functions f WHERE f.oid='platform.service_request_schema_profile()'::regprocedure
          AND f.proowner='asm_migrator'::regrole AND f.lanname='sql' AND f.prosecdef AND f.provolatile='s'
          AND f.proconfig=ARRAY['search_path=pg_catalog, pg_temp'] AND NOT has_function_privilege('asm_runtime',f.oid,'EXECUTE')
          AND NOT EXISTS(SELECT 1 FROM aclexplode(f.proacl) a WHERE a.grantee=0 AND a.privilege_type='EXECUTE'))
        AND EXISTS(SELECT 1 FROM pg_roles WHERE rolname='asm_runtime' AND rolcanlogin AND NOT rolsuper AND NOT rolbypassrls
          AND NOT rolinherit AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolreplication)
        AND NOT EXISTS(SELECT 1 FROM pg_auth_members WHERE member='asm_runtime'::regrole)
        AND (SELECT count(*) FROM tables)=75 AND NOT EXISTS(SELECT 1 FROM columns_expected e LEFT JOIN tables t ON t.name=e.table_name
          WHERE t.oid IS NULL OR t.columns IS DISTINCT FROM e.column_names)
        AND NOT EXISTS(SELECT 1 FROM tables WHERE name IN ('platform.business_configuration_state','platform.business_configuration_releases','platform.business_configuration_receipts','platform.human_context_observations','platform.human_context_reconciliations','platform.human_context_policy_receipts','platform.ai_runs','platform.ai_provider_calls','platform.ai_deliveries','platform.ai_provider_sessions','platform.knowledge_sources','platform.knowledge_revisions','platform.knowledge_chunks','platform.knowledge_builds','platform.knowledge_build_chunks','platform.knowledge_release_builds','platform.knowledge_embedding_calls','platform.portfolio_assets','platform.portfolio_asset_versions','platform.portfolio_ai_sessions','platform.vision_analyses','platform.portfolio_items','platform.portfolio_revisions','platform.portfolio_builds','platform.portfolio_build_items','platform.portfolio_release_builds','platform.portfolio_delivery_intents')
          AND (relowner<>'asm_migrator'::regrole OR NOT relrowsecurity OR NOT relforcerowsecurity OR has_table_privilege('asm_runtime',oid,'SELECT,INSERT,UPDATE,DELETE')))
        AND (SELECT version_num FROM platform.alembic_version)='0025' AS valid),
      catalog AS MATERIALIZED (SELECT jsonb_build_object(
        'functions',(SELECT jsonb_agg(jsonb_build_array(oid::regprocedure::text,pg_get_functiondef(oid),proacl::text,proowner::regrole::text) ORDER BY oid::regprocedure::text) FROM functions),
        'columns',(SELECT jsonb_agg(jsonb_build_array(t.name,a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,a.attgenerated,pg_get_expr(d.adbin,d.adrelid)) ORDER BY t.name,a.attnum)
          FROM tables t JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum>0 AND NOT a.attisdropped LEFT JOIN pg_attrdef d ON (d.adrelid,d.adnum)=(a.attrelid,a.attnum)),
        'constraints',(SELECT jsonb_agg(jsonb_build_array(t.name,k.conname,pg_get_constraintdef(k.oid),k.convalidated) ORDER BY t.name,k.conname) FROM tables t JOIN pg_constraint k ON k.conrelid=t.oid),
        'indices',(SELECT jsonb_agg(jsonb_build_array(schemaname,tablename,indexname,indexdef) ORDER BY schemaname,tablename,indexname) FROM pg_indexes WHERE schemaname IN ('app','platform')),
        'policies',(SELECT jsonb_agg(to_jsonb(p) ORDER BY schemaname,tablename,policyname) FROM pg_policies p WHERE schemaname IN ('app','platform')),
        'triggers',(SELECT jsonb_agg(jsonb_build_array(t.name,g.tgname,pg_get_triggerdef(g.oid),g.tgenabled) ORDER BY t.name,g.tgname) FROM tables t JOIN pg_trigger g ON g.tgrelid=t.oid AND NOT g.tgisinternal),
        'relations',(SELECT jsonb_agg(jsonb_build_array(name,relowner::regrole::text,relrowsecurity,relforcerowsecurity,relacl::text) ORDER BY name) FROM tables),
        'sequences',(SELECT jsonb_agg(jsonb_build_array(n.nspname,r.relname,r.relowner::regrole::text,r.relacl::text,
          s.seqtypid::regtype::text,s.seqstart,s.seqincrement,s.seqmin,s.seqmax,s.seqcache,s.seqcycle) ORDER BY n.nspname,r.relname)
          FROM pg_sequence s JOIN pg_class r ON r.oid=s.seqrelid JOIN pg_namespace n ON n.oid=r.relnamespace WHERE n.nspname IN ('app','platform')),
        'schemas',(SELECT jsonb_agg(jsonb_build_array(nspname,nspowner::regrole::text,nspacl::text) ORDER BY nspname) FROM pg_namespace WHERE nspname IN ('app','platform')),
        'extensions',(SELECT jsonb_agg(jsonb_build_array(e.extname,e.extversion,n.nspname) ORDER BY e.extname)
          FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname IN ('vector','btree_gist'))) AS value)
      SELECT jsonb_build_object('schema_revision','0025','valid',coalesce(v.valid,false)
        AND encode(sha256(convert_to((c.value-'functions')::text,'UTF8')),'hex')='421339b8ed8e33f168a087f1e2b1ca8f8f719a7f8be9efe2eb0ec7e2bedbedd2',
        'profile_sha256',encode(sha256(convert_to(E'asm:m3:native_schema:v1\n'||c.value::text,'UTF8')),'hex')) FROM validity v CROSS JOIN catalog c $$"""


def upgrade():
    for table, sql in TABLES.items():
        op.execute(sql)
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY service_request_migrator ON {table} TO asm_migrator USING(true) WITH CHECK(true)"
        )
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC,asm_runtime")
    op.execute(
        "CREATE INDEX service_requests_conversation_latest ON app.service_requests"
        "(workspace_id,business_id,conversation_id,created_at DESC,id DESC)"
    )
    for signature, sql in FUNCTIONS.items():
        op.execute(sql)
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC,asm_runtime")
    for signature in RUNTIME_FUNCTIONS:
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO asm_runtime")

    op.execute(PROFILE)
    op.execute("REVOKE ALL ON FUNCTION platform.service_request_schema_profile() FROM PUBLIC,asm_runtime")
    for sql in SCHEMA_GATES_0024:
        op.execute(
            sql.replace("platform.intake_v7_schema_profile()", "platform.service_request_schema_profile()")
            .replace("'0024'", "'0025'")
        )


def downgrade():
    op.execute(
        "LOCK TABLE app.service_requests,platform.service_request_receipts IN ACCESS EXCLUSIVE MODE"
    )
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM app.service_requests)
        OR EXISTS(SELECT 1 FROM platform.service_request_receipts) THEN
        RAISE EXCEPTION 'SERVICE_REQUEST_DURABLE_DATA' USING ERRCODE='55000';
      END IF;
    END $$""")
    for sql in SCHEMA_GATES_0024:
        op.execute(sql)
    op.execute("DROP FUNCTION platform.service_request_schema_profile()")
    for signature in reversed(FUNCTIONS):
        op.execute(f"DROP FUNCTION {signature}")
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE {table}")
