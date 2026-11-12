"""Claim-bound Telegram observation before selecting a canonical AI reply.

Reuses the existing job probe columns and observation CAS. HTTP never runs in
these capabilities; final SEND_AI_TEXT admission and historical functions stay
unchanged. Negative observations commit without selecting a result or Outbox.
"""

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

PREVIOUS_PROBE_CHECK = """CHECK (
  (telegram_probe_claim IS NULL AND telegram_probe_generation IS NULL AND telegram_probe_version IS NULL) OR
  (kind IN ('SEND_MANUAL_TEXT','SEND_AI_TEXT') AND telegram_probe_claim IS NOT NULL AND telegram_probe_generation IS NOT NULL AND telegram_probe_version IS NOT NULL))"""
REPLY_PROBE_CHECK = """CHECK (
  (telegram_probe_claim IS NULL AND telegram_probe_generation IS NULL AND telegram_probe_version IS NULL) OR
  ((kind IN ('SEND_MANUAL_TEXT','SEND_AI_TEXT') OR (kind='PROCESS_TURN' AND step='AI_GENERATE'))
    AND telegram_probe_claim IS NOT NULL AND telegram_probe_generation IS NOT NULL AND telegram_probe_version IS NOT NULL))"""

# Only the current profile dispatcher changes in these existing capabilities.
CURRENT_ORIGINAL = {
    "platform.ai_provider_session(jsonb,boolean)": """CREATE FUNCTION platform.ai_provider_session(p jsonb,p_enable boolean) RETURNS jsonb
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
    OR p->'config'->>'revision' IS DISTINCT FROM 'polza-'||(p->>'session_id')||'-'||(p->>'review_sha256')
    OR (platform.ai_provider_schema_profile()->>'valid')::boolean IS NOT TRUE THEN
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
    "platform.human_context_policy_command(uuid,uuid,text,text,text,bigint,jsonb,jsonb)": """CREATE OR REPLACE FUNCTION platform.human_context_policy_command(ws uuid,p_connection uuid,p_operation text,p_key text,
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
          OR jsonb_typeof(p_profile->'schema_revision')<>'string' OR p_profile->>'schema_revision'<>'0016'
          OR jsonb_typeof(p_profile->'profile_sha256')<>'string' OR p_profile->>'profile_sha256' !~ '^[0-9a-f]{64}$'
          OR p_profile->'drain_confirmed' IS DISTINCT FROM 'true'::jsonb THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2601'; END IF;
        SELECT platform.ai_provider_schema_profile() INTO profile;
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
        SELECT platform.ai_provider_schema_profile() INTO profile;
        IF session_user<>'asm_migrator' OR profile->'valid' IS DISTINCT FROM 'true'::jsonb OR p_profile->>'profile_sha256' IS DISTINCT FROM profile->>'profile_sha256' THEN
          RAISE EXCEPTION 'POLICY_PREREQUISITE_FAILED' USING ERRCODE='P2601'; END IF;
        fingerprint:=platform.human_context_hash(E'asm:m3:human_context_policy:v1\\n',ARRAY[ws::text,session_user::text,c.id::text,p_operation,p_expected_policy,p_expected_epoch::text,
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
}
CURRENT_FUNCTIONS = {
    "platform.ai_provider_session(jsonb,boolean)": """CREATE OR REPLACE FUNCTION platform.ai_provider_session(p jsonb,p_enable boolean) RETURNS jsonb
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
    OR p->'config'->>'revision' IS DISTINCT FROM 'polza-'||(p->>'session_id')||'-'||(p->>'review_sha256')
    OR (platform.ai_reply_rights_schema_profile()->>'valid')::boolean IS NOT TRUE THEN
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
    "platform.human_context_policy_command(uuid,uuid,text,text,text,bigint,jsonb,jsonb)": """CREATE OR REPLACE FUNCTION platform.human_context_policy_command(ws uuid,p_connection uuid,p_operation text,p_key text,
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
          OR jsonb_typeof(p_profile->'schema_revision')<>'string' OR p_profile->>'schema_revision'<>'0017'
          OR jsonb_typeof(p_profile->'profile_sha256')<>'string' OR p_profile->>'profile_sha256' !~ '^[0-9a-f]{64}$'
          OR p_profile->'drain_confirmed' IS DISTINCT FROM 'true'::jsonb THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2601'; END IF;
        SELECT platform.ai_reply_rights_schema_profile() INTO profile;
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
        SELECT platform.ai_reply_rights_schema_profile() INTO profile;
        IF session_user<>'asm_migrator' OR profile->'valid' IS DISTINCT FROM 'true'::jsonb OR p_profile->>'profile_sha256' IS DISTINCT FROM profile->>'profile_sha256' THEN
          RAISE EXCEPTION 'POLICY_PREREQUISITE_FAILED' USING ERRCODE='P2601'; END IF;
        fingerprint:=platform.human_context_hash(E'asm:m3:human_context_policy:v1\\n',ARRAY[ws::text,session_user::text,c.id::text,p_operation,p_expected_policy,p_expected_epoch::text,
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
}

FUNCTIONS = {
    "ai_reply_rights_current(uuid,uuid,uuid)": """CREATE FUNCTION platform.ai_reply_rights_current(p_job uuid,p_claim uuid,p_run uuid) RETURNS platform.ai_runs
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE j platform.messaging_jobs%ROWTYPE; r platform.ai_runs%ROWTYPE; d platform.ai_deliveries%ROWTYPE; fresh jsonb;
BEGIN
  PERFORM platform.turn_require_isolation();
  j:=platform.messaging_guard(p_job,p_claim);
  IF j.kind<>'PROCESS_TURN' OR j.step<>'AI_GENERATE' THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
  SELECT * INTO r FROM platform.ai_runs WHERE workspace_id=j.workspace_id AND job_id=j.id AND id=p_run FOR UPDATE;
  SELECT * INTO d FROM platform.ai_deliveries WHERE workspace_id=j.workspace_id AND job_id=j.id FOR UPDATE;
  IF r.id IS NULL OR d.job_id IS NULL OR r.result IS NOT NULL OR d.selected_kind IS NOT NULL OR r.deadline<=clock_timestamp()
    OR r.calls_used=0 OR NOT EXISTS(SELECT 1 FROM platform.ai_provider_calls WHERE workspace_id=r.workspace_id AND run_id=r.id
      AND sequence=r.calls_used AND completed_at IS NOT NULL AND completion->>'kind'='OUTPUT'
      AND claim_hash=sha256(convert_to(p_claim::text,'UTF8')) AND attempt_count=j.attempt_count) THEN
    RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
  fresh:=platform.ai_runtime_current(j,r.snapshot);
  IF fresh->'binding' IS DISTINCT FROM r.binding THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
  IF d.provider_session_id IS NOT NULL THEN PERFORM platform.ai_provider_guard(d.provider_session_id,j,r.config); END IF;
  RETURN r;
END $$""",
    "ai_reply_rights_probe(uuid,uuid,uuid)": """CREATE FUNCTION platform.ai_reply_rights_probe(p_job uuid,p_claim uuid,p_run uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE r platform.ai_runs%ROWTYPE; conn app.channel_connections%ROWTYPE; s platform.telegram_connection_state%ROWTYPE;
BEGIN
  r:=platform.ai_reply_rights_current(p_job,p_claim,p_run);
  SELECT * INTO STRICT conn FROM app.channel_connections WHERE workspace_id=r.workspace_id AND id=r.connection_id;
  IF conn.provider='CONTROLLED' THEN RETURN NULL; END IF;
  IF conn.provider<>'TELEGRAM' THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
  SELECT * INTO STRICT s FROM platform.telegram_connection_state WHERE workspace_id=r.workspace_id AND connection_id=r.connection_id FOR SHARE;
  IF (conn.bot_identity,conn.external_connection_id) IS DISTINCT FROM (s.bot_identity,s.external_connection_id) THEN
    RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
  UPDATE platform.messaging_jobs SET telegram_probe_claim=p_claim,telegram_probe_generation=s.generation,telegram_probe_version=s.observation_version WHERE id=p_job;
  RETURN platform.telegram_probe_json(s);
END $$""",
    "ai_reply_rights_commit(uuid,uuid,uuid,bigint,bigint,jsonb,jsonb)": """CREATE FUNCTION platform.ai_reply_rights_commit(p_job uuid,p_claim uuid,p_run uuid,p_generation bigint,p_version bigint,p_observation jsonb,p_result jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE j platform.messaging_jobs%ROWTYPE; r platform.ai_runs%ROWTYPE; conn app.channel_connections%ROWTYPE; s platform.telegram_connection_state%ROWTYPE; observed jsonb;
BEGIN
  r:=platform.ai_reply_rights_current(p_job,p_claim,p_run);
  j:=platform.messaging_guard(p_job,p_claim);
  IF platform.ai_runtime_result_valid(p_result) IS NOT TRUE OR p_result->>'kind' IS DISTINCT FROM 'reply' THEN
    RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
  IF j.telegram_probe_claim IS DISTINCT FROM p_claim OR j.telegram_probe_generation IS DISTINCT FROM p_generation
    OR j.telegram_probe_version IS DISTINCT FROM p_version OR p_generation IS NULL OR p_version IS NULL THEN
    RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
  SELECT * INTO STRICT conn FROM app.channel_connections WHERE workspace_id=r.workspace_id AND id=r.connection_id;
  SELECT * INTO STRICT s FROM platform.telegram_connection_state WHERE workspace_id=r.workspace_id AND connection_id=r.connection_id FOR UPDATE;
  IF conn.provider<>'TELEGRAM' OR (conn.bot_identity,conn.external_connection_id) IS DISTINCT FROM (s.bot_identity,s.external_connection_id) THEN
    RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
  observed:=platform.telegram_save_observation(r.workspace_id,r.connection_id,p_generation,p_version,p_observation);
  IF observed->>'code' IS DISTINCT FROM 'OBSERVED' OR platform.telegram_can_send(r.workspace_id,r.connection_id,r.conversation_id,true) IS NOT TRUE THEN
    RETURN jsonb_build_object('code','RIGHTS_REJECTED');
  END IF;
  -- Same transaction: the existing canonical selector rechecks all authority,
  -- deadline and TTL30 guards after the fresh observation has been stored.
  RETURN platform.ai_delivery_command(p_job,p_claim,'COMMIT',jsonb_build_object('run_id',r.id,'result',p_result));
END $$""",
}

PROFILE_SQL = """CREATE FUNCTION platform.ai_reply_rights_schema_profile() RETURNS jsonb
      LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      WITH expected(signature,body_hash,language,security_definer,volatility,runtime_execute) AS (VALUES ('app.current_messaging_owner_workspace_id()','8ffbd40db1c507c7384981d683bf671cc1914b088d61aa543c8a2a2d44debee6','plpgsql',true,'s',true),('app.current_workspace_id()','f6c6760e5de3ce4885b0c27daf1ab82867438c4c1ec19d95cb084bb4e799475d','plpgsql',true,'s',true),('platform.ai_delivery_begin(uuid,uuid,bigint,bigint,jsonb)','5573f154a508e3a3a53f77b4dd93a275dd2ac7524f075d63b29971764852c7e0','plpgsql',true,'v',true),('platform.ai_delivery_claim(text,timestamptz,timestamptz,uuid)','7ee3ed1d45d79873dd709a53473da3ffa98d9b150c949c814d552603a5b6fdf6','plpgsql',true,'v',true),('platform.ai_delivery_command(uuid,uuid,text,jsonb)','9d5038f9c26d8876321cb98493c355f502d9b29e3bb97c53e6ce82b04a516c13','plpgsql',true,'v',true),('platform.ai_delivery_current(platform.messaging_jobs,platform.ai_deliveries,platform.ai_runs)','4651caab37aa322745bbb73ae62d634a2e443d1da1d7460474a1a3f1df2cb1a1','plpgsql',true,'v',false),('platform.ai_delivery_enqueue(uuid,uuid)','c933c3e6c1381db9fe7e5234beab38c17ad53adad3829a6760755f6a2f0fc1e1','plpgsql',true,'v',true),('platform.ai_delivery_immutable()','086e4771a6a2c48536e3833b47894da99070f559e55e8e3178ba37537cb0de63','plpgsql',true,'v',false),('platform.ai_delivery_schema_profile()','2af634ab2afb3b2b9a536453ce6c735b6be57a1018fdd0893d707d3d5dca5f36','sql',true,'s',false),('platform.ai_delivery_select(platform.messaging_jobs,platform.ai_runs)','b40ce7be68bef556999950227fab8236d90672ec03590baf643bfb4bc834eb55','plpgsql',true,'v',false),('platform.ai_provider_command(uuid,uuid,uuid,text,jsonb)','24672f24048580bb314ed845a9d1e4869dee15d519063dedb029e82d0b4e2c60','plpgsql',true,'v',true),('platform.ai_provider_config_valid(jsonb)','7f8e651b4acb1fe3068a160361a68adf0810d9f0890cf0648224b8efdd1b1803','plpgsql',true,'i',false),('platform.ai_provider_enqueue(uuid,uuid,uuid)','91e5c0e7e3ae24516d55c68d9cda830fc8d52f15701cce31d7cdb65289583096','plpgsql',true,'v',true),('platform.ai_provider_guard(uuid,platform.messaging_jobs,jsonb)','4beb6f775cc17a68fbd068c2b69692f2b2e4ef5c2b78753e119bd679f16666c3','plpgsql',true,'v',false),('platform.ai_provider_schema_profile()','f2b1f7dbdea1f41244094a101d7d4802927a550078ac260e14c7ffb997bd1986','sql',true,'s',false),('platform.ai_provider_session(jsonb,boolean)','606d122fc0cad9e3143ef33919e5f7fe33617550ee0d66d45ccaef121e3d9704','plpgsql',true,'v',false),('platform.ai_reply_rights_commit(uuid,uuid,uuid,bigint,bigint,jsonb,jsonb)','9ebfd03c8c3c1de581329f2aef49b3a4327916923295bac2616036be7b07b1ee','plpgsql',true,'v',true),('platform.ai_reply_rights_current(uuid,uuid,uuid)','2823f332ca3da5e2429607dc28be0aa6d1b673019f2781168b414c16d8e9fd6e','plpgsql',true,'v',false),('platform.ai_reply_rights_probe(uuid,uuid,uuid)','9ca90da38d173e7294f77cd7dbdd25492f02fe2cd699562c823c42fbfcb3b01d','plpgsql',true,'v',true),('platform.ai_runtime_command(uuid,uuid,text,jsonb)','cb3157c6b2b882e9c04ac83c53b4d22af03aaf3a51bab20a457f6f2bccbc35a3','plpgsql',true,'v',true),('platform.ai_runtime_completion_valid(jsonb)','4675d7ce837be36341cdc60deff5c216786ad7f42441bb4bda43bfe5e0dcfb0d','plpgsql',true,'i',false),('platform.ai_runtime_config_valid(jsonb)','d85e586c95e9ba8082c9d523fded85c8e9b3cb11ab70a9de25fd2dc61d37a8e7','sql',true,'i',false),('platform.ai_runtime_current(platform.messaging_jobs,jsonb)','fdcd7bd225f37b6edaf1bbddb019846f3be8dd9c652da610eaf5a1f983ccca13','plpgsql',true,'v',false),('platform.ai_runtime_receipt(platform.ai_runs)','f027eda65acd1f3d580afbd441ba6009efe88bc430020424af73d1003ae1d2a5','sql',true,'s',false),('platform.ai_runtime_replay(uuid,uuid,jsonb)','36b9248da5aff70b2fec73a85303716769350732f5cee03deb719a9f6d0a17c3','plpgsql',true,'v',true),('platform.ai_runtime_result_valid(jsonb)','7f81305118ab1bff57585a409c91b04ff2eb44d24722d74b35ae05379d5e21d1','plpgsql',true,'i',false),('platform.ai_runtime_view(platform.ai_runs)','4b7264f6dfc835152a5d7e1ade4fdf70b50daaddbc8264fc766ad1fce707b048','sql',true,'s',false),('platform.ai_synthetic_config_valid(jsonb)','20241427cbe5024f6a5876184f29895f28a83191519bf4d99a4e6e6993baf00c','plpgsql',true,'i',false),('platform.auth_bootstrap(text,integer)','6eb28b55313391c9d0eb07ca055ff8754e49b83cfeef132d9ba413077545c5dd','plpgsql',true,'v',true),('platform.auth_lock_session(text,boolean)','55ca74ab7475f964865b6d3a6b73778f7139add6a1531781b14362fef0f30428','plpgsql',true,'v',false),('platform.auth_login(text,uuid,bigint,bigint,text,integer)','3f975835d787dd8531c415783aa7492facafcbd5d9def911703780bb1bfc83c1','plpgsql',true,'v',true),('platform.auth_logout(text)','67f05d0d9e47e103cd71365e8f9e574bdd6bcff42dbe156d9f6a68c1b04149e2','plpgsql',true,'v',true),('platform.auth_memberships(text)','0e684da56252678c7bc27b962a49c4213c3de9865a63b43e552221b36ab9b7fb','plpgsql',true,'v',true),('platform.auth_password_lookup(text)','a972cb3994842757f18045afae2ac0f00d90020d482a62043376ecd3ee5b22e3','sql',true,'s',true),('platform.auth_rotate(text,text)','7978763cff421212ae6e184771aa26468cf6be997f29ac386c256dfc0b0640b4','plpgsql',true,'v',true),('platform.auth_session(text)','5e1e2ceaad4b2b1452a02d4d04f7f5d53ebf40e5067b7223baf5a2edc65253f4','plpgsql',true,'v',true),('platform.conversation_control_execute(uuid,uuid,text,text,bigint,bigint)','b8fcb2df6bdb6564b8c68b05d1341e0979a89c9fae1af6244084e1d9fac15ea3','plpgsql',true,'v',true),('platform.conversation_control_fingerprint(uuid,uuid,uuid,uuid,text,bigint,bigint)','60cd026890baa0f09e98c3742ab8da80d5a44fd243fa16d983ea42dcabd2459a','sql',false,'i',false),('platform.conversation_control_locked(uuid,uuid,text,text,bigint,bigint)','0609192f801e87cb185525047a79af365e868c19f6974ce0d35c4a33388d96d0','plpgsql',true,'v',false),('platform.conversation_control_prepare(uuid,uuid,text,text,bigint,bigint)','3d9ce63a7e8b9787adfe7ae96e77a42d6e1af57835f57351fb8846d7e3e07c35','plpgsql',true,'v',true),('platform.conversation_control_read(uuid)','e30448916cece6ee18500c1ef5e9399b1c50dd8a2fad7f95c3cded2cf512f9b8','plpgsql',true,'v',true),('platform.conversation_manual_prelock(uuid,text,text)','0cf8c71a6028ddd08508f9132991d891b6cada8e50c2c5b831b9bc4be2d3c65f','plpgsql',true,'v',true),('platform.conversation_manual_takeover(uuid,uuid)','88a05e4aa03904af8f8ec54e8544dbe867b1f7f22404becef415b76cdf3e3d29','plpgsql',true,'v',false),('platform.conversation_turn_activation_matches(uuid,uuid)','ed3f021b97d11656125233eac69944bfb4a3cf09abe761d63c8cc14d531e90a5','sql',true,'v',false),('platform.escalation_command(uuid,uuid,uuid,text,text,bigint,bigint,bigint,text)','eab7c452b759ae2dd95796b4f8e962f41406896de1ca612638a3f1b7db562152','plpgsql',true,'v',true),('platform.escalation_command_fingerprint(uuid,uuid,uuid,uuid,uuid,text,bigint,bigint,bigint,text)','83bc68632b05e2b1cc74ecb8ac81c595034dccb634182b93fa5335633ebd5c0c','sql',false,'i',false),('platform.escalation_context_changed()','e9653e9625316e84df64a98386a5b4b8addd534032076eb236433f655b65b67f','plpgsql',true,'v',false),('platform.escalation_immutable()','a00c618cdc817b68495e090c143285e7b5832292ebe87ec92a33b1fb62ab23bd','plpgsql',true,'v',false),('platform.escalation_list(integer,text,timestamptz,uuid)','97c703f4dfa2237dc30359661cd53d06c698383556ad45f52a13fa01c1f5b6a0','plpgsql',true,'v',true),('platform.escalation_now()','31ebb037ed35337329fa522d1b51d159d7ed91eccc95e3694b2338abbcea74b1','sql',false,'v',false),('platform.escalation_read(uuid)','baecd1393cd666b40ff743464e5280ee5f07cb61189400eafab5392280cf548a','plpgsql',true,'v',true),('platform.escalation_request_for_turn(uuid,uuid)','f3a9d542a46754fbad85510a192230865a7fe76dcdfe17918330244a55cdac37','plpgsql',true,'v',true),('platform.escalation_request_replay(uuid,uuid)','1e10c8742b9e58fee2780d55d44af2bfb097b0114afae0b2647a201f0416f989','plpgsql',true,'s',true),('platform.escalation_timer_execute(uuid,uuid)','0bbd68c40bcae571fde899c57a51f1628fea26238e662ff015ed428ca8dfd7b3','plpgsql',true,'v',true),('platform.escalation_validity(uuid,uuid,timestamptz)','2185d597e6ae580e5c48d4c03bda56f44865d7d2ef89a94b4815741c8ead7b1e','sql',true,'s',false),('platform.files_begin_fetch(uuid,uuid)','b613633a1c13e033a051e593182d275502a7b1ed9e586a8351e494ca7f394347','plpgsql',true,'v',true),('platform.files_claim_cleanup(integer)','5961679941084084fb083ec755861f9db3ecb0792f57e24fe338eb6df42bf143','plpgsql',true,'v',true),('platform.files_finish_cleanup(uuid,uuid,text)','f25b769900d682dbf58e53f68dad2952162604bcde386343115f86b504aba39d','plpgsql',true,'v',true),('platform.files_finish_fetch(uuid,uuid,uuid)','185f336920b32f3f5c21f300ee76f456610e65164b2a39eca7539948e4c00932','plpgsql',true,'v',true),('platform.files_immutable()','da3e6c650e8c2ed10ad61169127e0808370857c1d458e05b49c37b7db78c4bc2','plpgsql',false,'v',false),('platform.files_manifest_valid(jsonb)','3a4dbfe98efa8df5455d6ac60aeec88250d7ea110408aed5a323557b480eaf67','plpgsql',false,'i',false),('platform.files_plan(uuid,uuid,uuid)','ec5f05ae04a2d4bc0ee91f99a6db768801c78890761f255a86001e8f413ead22','plpgsql',true,'v',false),('platform.files_prepare_upload(uuid,uuid,jsonb)','da20120cf752fc9a0be9b31d19efdd081949391b3ff3b12b72f68e3254192a9f','plpgsql',true,'v',true),('platform.files_read_manifest(uuid,uuid,uuid)','586d58424a80d3eca338f74863d5b2ce4b0b4d97ad62d7aa72862d0374f4bfd7','plpgsql',true,'v',true),('platform.files_upload_json(platform.file_object_uploads)','56d0788594b3d549f87cac1980dd152d902cebb3ba9cd758066fa281c1449c40','sql',false,'s',false),('platform.guard_entitlement()','bed228f9542f5a6f85f28e17f47ab11f3524ab52fb648f4452c9dca4485efe06','plpgsql',false,'v',false),('platform.guard_plan_revision()','9ae94c6c1e0a8b05eeeac31db412d4cd5c8f4157bdae437664c82f5f0fc2c33b','plpgsql',false,'v',false),('platform.guard_require_current(uuid,uuid,uuid,bigint)','b5cce50ac291e7fe75adb5cb2e3c41bef3e7c67ba6229db8131b956d7560e0c8','plpgsql',true,'v',false),('platform.guard_send_begin(uuid,uuid)','af4661dcc860cc13fffc459bfa85f07cfae8c6a45e33ba2e0292f2baf54af835','plpgsql',true,'v',true),('platform.guard_text_fingerprint(jsonb,text)','d22ae019b3f8391ee43bb7e5f8889364694e8c59924f1712cc8533074da76bc2','sql',false,'i',false),('platform.guard_turn_accept(uuid,uuid,text,text)','43ca3517c109f27bc9c0b9d75fc18567b2b9dc9a9e3c730bb05299a266438671','plpgsql',true,'v',true),('platform.guard_turn_prepare(uuid,uuid)','f3487b85737dc4ad58025c176fbfaab7b4d1ec6c0dbac17bb2d9fa066dee6ddd','plpgsql',true,'v',true),('platform.guard_turn_replay(uuid,uuid,text,text)','e919531e4ea823def1545555aa00c91d9ac1b8b0ce9e67d8f2c698bfcb875889','plpgsql',true,'s',true),('platform.human_context_admission(uuid,uuid,jsonb)','155c83c42e96db76b7abfa55efc9823942325094c58bbcec6475f4517e1b15eb','plpgsql',true,'v',false),('platform.human_context_basic_current(uuid,uuid,uuid,bigint)','a60e4a7d9e3d44c08d72f9dfe32dfeffaba0201cf5f702f292679551c811147b','plpgsql',true,'v',false),('platform.human_context_consistent()','6e2d888a129131ecdf801a25fbcdc2f10304e2837e8937a8244d63421361db0f','plpgsql',true,'v',false),('platform.human_context_current_valid(jsonb)','c239ee7a7ee200b392aad3735a5410cfab6cb1f79d4f0eee6e41a115ef498b85','sql',true,'i',false),('platform.human_context_decimal(jsonb,boolean)','9e2e793224366ce5c3ceaa841c0f71ce7de25c0c2ab55b56618634a6852c8cff','sql',true,'i',false),('platform.human_context_effective(app.messages,jsonb,text)','5a4d2518416cc75f3e8740364fac3baf6aa104f8aa05ad9ab992b05d9e81bbfe','sql',true,'s',false),('platform.human_context_escalation_hold(uuid,uuid,timestamptz)','148e7567b42294c742d26858d7cf65acafa2b20125d880d2738f36c131145546','sql',true,'s',false),('platform.human_context_hash(text,text[])','9056f96e6302bd0d4a27b8cf393b33fbdafaaa39b5900ad41516bf4a066be1fc','sql',true,'i',false),('platform.human_context_integrity()','56aa7388cfa150391a0ee3ee7ddc520058147f89d234bf1234fc56a45a5f5ca4','plpgsql',true,'v',false),('platform.human_context_observation_digest(uuid,uuid,uuid,uuid,jsonb)','6c60ce9d15916b797ade41ea410c19ff3b5b5be75f42e7e06cb982cbf654b0e7','sql',true,'i',false),('platform.human_context_observations(uuid,integer,jsonb)','525edce2323e2ab781d46c115990d916f81eea6d0e9d9c1006798cdb01be00cc','plpgsql',true,'v',true),('platform.human_context_observe(platform.telegram_update_receipts,jsonb)','002b6410107e55a5025d49178b127a672e642ec3418eb2bcac7f038f6ae6fe3d','plpgsql',true,'v',false),('platform.human_context_policy_command(uuid,uuid,text,text,text,bigint,jsonb,jsonb)','5837edd864b922e9ef990aeda924547a02b572c61007a6b3e52d74b0b96201e9','plpgsql',true,'v',false),('platform.human_context_policy_guard()','9fad112676add9ee5c5874ab9d79583053161024f361c5f8cfb7d5caca7970aa','plpgsql',true,'v',false),('platform.human_context_policy_result(platform.human_context_policy_receipts)','14a64a6a05514af4312ef42d62554b396dc2d885235424bcb13f68b7aac3edb6','sql',true,'s',false),('platform.human_context_preview(jsonb)','edd77e725660f24f41d2a96424e2434bec0c58432b8a7ceb0b6dd1bb57a3e381','sql',true,'i',false),('platform.human_context_projection(uuid,uuid,timestamptz)','8d38da64c526acb61365aa06eb293d117e1d8af93b598b5a507da3a23bc17b51','sql',true,'s',false),('platform.human_context_read(uuid)','513256e45b12356cdd149e934bf11c56fefe44a321bfdfe498e0dbf0a1939b1c','plpgsql',true,'v',true),('platform.human_context_reason(jsonb,boolean)','799072de08ee913f09c11686e9a8300e55602ae7d5bf3f8610bb1a35a6d2cb19','sql',true,'i',false),('platform.human_context_reconcile(uuid,text,jsonb)','d75cd2b145fbe84ec26923b924b744f9a728546ee7f2254c9f62e5d2ca26546d','plpgsql',true,'v',true),('platform.human_context_reconcile_result(platform.human_context_reconciliations)','a2645c2165f2eee80027b426b5377c233f3412b4c52e32c7aab04708e011790d','sql',true,'s',false),('platform.human_context_revision_json(platform.human_context_reconciliations)','83a0d64f71b77f9dc8633c7f52498355c758cccdf2bc96d0908c4a125d362094','sql',true,'s',false),('platform.human_context_schema_profile()','527fce5681d5345369cd88b555a302df6d305ef8566cf12a666198eb64a6f4ac','sql',true,'s',false),('platform.human_context_snapshot_check(jsonb,text)','220cf8e65eb0c0b72fd03a87b3b97f834f738215ce7ec7461ccd0f32af12c110','plpgsql',true,'s',false),('platform.human_context_snapshot_valid(jsonb,text)','9db423e054719c6ddc7f6bd5a90307ba8b95523b9ce036098ba2d75bf97f84f4','plpgsql',true,'s',false),('platform.human_context_stale()','355dfcb1e982c63fee2e5d2f9df0bae68218e5c211b80ed1aaa14b6fe353f68a','plpgsql',true,'s',false),('platform.human_context_test_guard(platform.messaging_jobs,jsonb)','5600ba815891a13dcbfddb224575d449d1b14c2121e6ea10fb5f4e2bb597639f','plpgsql',true,'v',false),('platform.human_context_test_prelock(platform.messaging_jobs)','4ec2eb2e2e5b65b433ef05e6aed5a7a4bf0008a86871562307dbddd42a2de2d7','plpgsql',true,'v',false),('platform.human_context_text_valid(text)','efcf1bcedf46ec93feb243adb5b1d719e0d1d17658094a54a1a4152504b865b8','sql',true,'i',false),('platform.human_context_turn_projection(uuid,uuid,timestamptz)','6fbe7e7d06fd7818fd7b5c0b0a1df0f5f132fc734cbb2e74a90964edf17edd92','sql',true,'s',false),('platform.human_context_uuid(jsonb)','033d0b6c405aa313bece14c3338046b7624d0da096e3c6b60e9e15417e77ff77','sql',true,'i',false),('platform.human_context_wait(uuid,uuid,text)','34666cb91739199ba976e2af87a4d6cb40afa12bfa00d72d3bda3cb8d7ab69af','plpgsql',true,'v',false),('platform.human_context_work_lookup(uuid,uuid)','13969135268d8f00c990b49ff1d2aaed5e79a9ee9602fdd3d8f5ce366cd18be9','sql',true,'s',false),('platform.human_context_work_replay(uuid,uuid)','28bc46d45b5b5306e3ce4b0fa6fc0c47fb6b300ab7e28541c4d7df58c2ba6946','sql',true,'s',true),('platform.human_context_work_valid(platform.messaging_jobs)','bc7c086476e335c5f58cd1cddc409018f81f40d7995e383d7734ccfde58a93db','sql',true,'s',false),('platform.initialize_local_billing(uuid,text,integer,text,text,text,timestamptz,timestamptz,text)','20b0e1ea5d37d8710b485232cff1441ea7c6998d431233877d2ab1814f620e83','plpgsql',true,'v',false),('platform.initialize_local_messaging_billing(uuid,text,timestamptz,timestamptz)','2863259a15ff3178525d044704c26dbc57c35e4322f5412bed6dd13989098f7d','plpgsql',true,'v',false),('platform.initialize_telegram_connection(uuid,uuid,text,text,text,jsonb)','bfae87784d2145810f9ed12f1dfab4416d8041c9d2044c1397204bbe0f8275bf','plpgsql',true,'v',false),('platform.material_apply(uuid,uuid,uuid,jsonb)','529e701178043d44c7e5cbee6c4651fae3e6a3a6be36412764ac1e8b60ac7c39','plpgsql',true,'v',false),('platform.material_apply_context(uuid,uuid,uuid,boolean)','22636529fed5a35055d99e9a42f52615626150300ad08d62918bbbfc9bce3069','plpgsql',true,'v',false),('platform.material_bind(uuid,uuid,boolean,uuid)','8afd09d2d0576c14480ce5a5414aa5d924082a007888932aec43dec185a19408','plpgsql',true,'v',false),('platform.material_bump_turns(uuid,uuid[],uuid)','0019faf314594758579f035373f6e5d14d37a4cb9d3b75b4bb9c0a0116e09020','plpgsql',true,'v',false),('platform.material_content_valid(jsonb)','c89faf57741e2b8d179b4201aac7979e891984e867ecb27bfc455a66c0104da4','plpgsql',false,'i',false),('platform.material_fold(uuid,uuid,uuid)','74d5202cf7fe15ae866dbd81eb88e635564a189db0195a9c0311c15fe76cecf8','plpgsql',true,'v',false),('platform.material_identity(uuid,uuid,jsonb)','d4bb3911e0b35af35585df2307496147b4c02ab6ac6b4869fe53a3445eb9dca3','plpgsql',true,'s',false),('platform.material_integrity()','292dd9cbb24f1d2289b6e6b628160a8755841ecc4fbc4ab2a26a3c5c54cab7f7','plpgsql',true,'v',false),('platform.material_no_file()','5b01911a52d5fc64edbf23895a31d8316d34221fc4c399524f4932f4496ef892','plpgsql',true,'v',false),('platform.material_object(jsonb,text[])','aa02c1b4b7f6ad7ac3687dccee0f680b231876af0bc78d5d149b4cc6d08d40bf','sql',false,'i',false),('platform.material_process(platform.messaging_jobs)','351d28449ee12317a4f046b8f70998b0e51206954146e45e91a6491995cdcd09','plpgsql',true,'v',false),('platform.material_processing_replay(uuid,uuid)','5d04cfdae703e4786f4d61975d484ec2c1686fcbec620c98e33dab7eafe94a96','sql',true,'s',true),('platform.material_result_valid(jsonb)','6070c0641ab897095effdd4f841e0e34e8cc1b788d33dd64c5ef6d4cf2f6e9b6','plpgsql',false,'v',false),('platform.material_semantic(jsonb)','f1ec36fd862ecf60cd69b1f1d1e41b7c09cfab38a689f6127d0969541985bb92','sql',false,'i',false),('platform.material_state_valid(jsonb)','a2344f16e36d45187529757a8bd2c9fad1f0b2c6c6887ab81b631279a65f10c1','sql',false,'i',false),('platform.material_suppression_check()','6d19f17d542008095defb943095c9f9c894aa7441123806b24df110903cbaa52','plpgsql',true,'v',false),('platform.material_target_check()','0c41bd7a4b3399c47a7cae6707e9bb28d98ed248e687b26ec58c094a9c6dd7b1','plpgsql',true,'v',false),('platform.material_turn_usable(uuid,uuid)','9f2f31ab578bb9d66f1bd8ed9d57f6dd9ae5a06b9427c1138d85f8121452c893','sql',true,'v',false),('platform.message_effective(uuid,uuid)','7354f194d5c35a121421f41aad9740686de71519aea9879e762c111353777e82','plpgsql',true,'v',false),('platform.messaging_admit(uuid,uuid)','27d0551d90b2f854b54a8b9fff35ff92bff9b131de4653000015026460fefc31','plpgsql',true,'v',true),('platform.messaging_begin_send(uuid,uuid)','ced9aced8fef1976bae75cedc268ed5a25b651c01fb276502bcc77badc8453e1','plpgsql',true,'v',true),('platform.messaging_claim(text,timestamptz,timestamptz,uuid)','1e88ecfd996f7b98034e20a8b8143de35ca3e576d252c182e89f61ea27bcad01','plpgsql',true,'v',true),('platform.messaging_fingerprint(jsonb,boolean)','d64c3b2ea0f53e0861315883b7420e5aee652b28dffa093bce0d3fff2986a342','plpgsql',false,'i',false),('platform.messaging_finish_send(uuid,uuid,uuid,text,text,text)','4c6db15c26212a1a943e58eaf3f6355988380106a2be7ed04832ab6c8c673a0b','sql',true,'v',true),('platform.messaging_finish_send(uuid,uuid,uuid,text,text,text,integer)','be8b1b54e4cf59d45544aca490b7b7863cdbcb7b0601174919967558994bd632','plpgsql',true,'v',true),('platform.messaging_guard(uuid,uuid)','0a57433b9b39446547a2f2accfeb9516238ae8c9210f67773e30f749a756adb5','plpgsql',true,'v',false),('platform.messaging_immutable()','3971e82a86a3826eeaf7b9e24458fbb1adc64cce0e8f2cb43a46384348519934','plpgsql',false,'v',false),('platform.messaging_ingest(text,text,jsonb,uuid)','2833a40d4ec37a014eab30fcbe2893a590d50c909b71eebc754e1c575ecb9f32','plpgsql',true,'v',true),('platform.messaging_job_json(platform.messaging_jobs)','7ccc5395def311a662f2b4845b33ce5e85af7c94d5920ddb03b97bcb2d37a5f3','sql',false,'s',false),('platform.messaging_lock_billing()','69f212c164437a4b39942e87f32c53df5cb4fb8e5f2bf9da2e1952e98be180eb','plpgsql',true,'v',true),('platform.messaging_lock_billing_workspace(uuid)','8797320c11ace5b9c44b37ed511293f0f61af6c0ba1b58abcd5cd60b5ec27204','plpgsql',true,'v',false),('platform.messaging_lock_owner(uuid,uuid)','11168bbd30eec24cfdb0ad9de67c70f767c0bf62480c7579638e58ecfb42bce1','plpgsql',true,'v',false),('platform.messaging_manual_send_allowed(uuid)','4ce13d4ca64dbc09aada275a295d76a01a08ac809768a2448fb1e1f074cd4bd6','plpgsql',true,'v',false),('platform.messaging_prepare_text(uuid,text,text)','39c14deb5337876f28970605ea399f9106f5e768e9f8f8c54b2e3746d570bca9','plpgsql',true,'v',true),('platform.messaging_process_inbox(uuid,uuid)','5a63a698c440120cebeaf4c6ebf8133f04abf41f610ef2ad3c3e34312b4ef2e3','plpgsql',true,'v',true),('platform.messaging_read_connections(integer,timestamptz,uuid)','242c6123fd6c57c44eb8c9ff658fe437700144b9e6525fff6c2ccf24c892511b','plpgsql',true,'v',true),('platform.messaging_read_conversations(integer)','aaeb0c33dd9e7501e92c3bcb599e38073bfeef8c3f3b7352cd22ef4a4b60e040','plpgsql',true,'v',true),('platform.messaging_read_conversations(integer,timestamptz,uuid)','81949cfd2357e8886003e7c5618fed4a7ce2b4d4474c2764c377783e97ed9658','plpgsql',true,'v',true),('platform.messaging_read_delivery(uuid)','f3cdd1d7de19b740961b0f4a6aece317b4fdd4ef1dafcfc9ce25ab6908bc29ed','plpgsql',true,'v',true),('platform.messaging_read_inbox(uuid)','7666d3eb0bc87de36bb75b4a7a8f9ab4e31f329f5fcd2fbaccc275d819b6d171','plpgsql',true,'v',true),('platform.messaging_read_messages(uuid,integer)','fcfa6f29a181d0e97ce52ae98ec0d008859e6568ad118e89234a5ed5b932a460','plpgsql',true,'v',true),('platform.messaging_read_messages(uuid,integer,timestamptz,uuid)','9e0828d184e46ded7e48e437be6a1a7737b96b2a90fb761fce6eafbfb5c5185f','plpgsql',true,'v',true),('platform.messaging_recover_expired(timestamptz,timestamptz,uuid)','1b040cbb1c6fc0183aed53681ef4394a2bc3b8d94715f76757563c9b778271f0','plpgsql',true,'v',true),('platform.messaging_request_text(uuid,text,text)','13dc01a5b25f4b2d5da4835fa8aabf14f33f98573532e730929006688be7059c','plpgsql',true,'v',true),('platform.messaging_reschedule(uuid,text,boolean)','6409aa21554ccaa346587c2f4da07bc6941e27c4736db9bd518f26e4c7947438','sql',true,'v',false),('platform.messaging_reschedule(uuid,text,boolean,integer)','21e8b16de21a18ff5646eeb28f7eceb801da8ab5bfc7d8e1799e6a91b9a2d074','sql',true,'v',false),('platform.messaging_reschedule(uuid,text,boolean,integer,boolean)','78922f1c89a00c0ae7a18e8d4fc509e2a529ce5e10c76b86e072a7fe9b1bff85','plpgsql',true,'v',false),('platform.messaging_retry(uuid,uuid,text,boolean)','6bf436d91a4d47932ff12e24d74c57f8dfa2d1102e470456c6706b62c0f2d64f','plpgsql',true,'v',true),('platform.messaging_valid_id(text,integer,integer)','9e1cf327f38fa1437a5a755e3c68d531c0209b585722755c865b395f616419f5','sql',false,'i',false),('platform.messaging_validate_event(jsonb)','1f7a2405bde9171aa196355bfae185cbc4084aeffbbdfda20d4f8828fdb95791','plpgsql',false,'v',false),('platform.resolve_workspace_membership(uuid,uuid)','8ce9bdd67c17bc83442bea3a5e7a15337a51074e0ea6408855b10542e39ceb39','sql',true,'v',true),('platform.telegram_begin_send(uuid,uuid,bigint,bigint,jsonb)','c8f15c23837fa40b86451574ee3e04cc4292dd91b2929a891424e0d8acec556d','plpgsql',true,'v',true),('platform.telegram_can_send(uuid,uuid,uuid,boolean)','b273ad02ca6825bdf6b037173c3be840a615d551283c3e922357bee3f7f16811','plpgsql',true,'v',false),('platform.telegram_fingerprint(text,jsonb)','449929a9e41d6e4f38d30341fcb7c7a488d55f06169dbaca2c18df461effdc06','plpgsql',false,'i',false),('platform.telegram_fingerprint_v2(text,jsonb)','4499d0bd8bc0ad010d856d3e20b21847a9cfedfaeced5c14ace118443c2a940f','plpgsql',false,'i',false),('platform.telegram_ingest(text,jsonb,uuid)','0b4d1cc97c47522e9abde484362aad3cd4967ae9c256e7719d310c09702f7c09','plpgsql',true,'v',true),('platform.telegram_numeric_id(text)','1519829aa6e3dfc1ac03180377c72929d7a7a3dcedd1b037ae7d3ea4872413cf','sql',false,'i',false),('platform.telegram_owner_observe(uuid,bigint,bigint,jsonb)','8ecd18d13fe815311aa9b076b3313efb98bbc3276962c44932516c5692666380','plpgsql',true,'v',true),('platform.telegram_probe_json(platform.telegram_connection_state)','bce40873beb21b5aa8c5b850468f9f5fce85a865a60567066129998f75e0c273','sql',false,'s',false),('platform.telegram_receipt_json(platform.telegram_update_receipts,text)','d6c81a402d8c8b53aab72685cff893e34100973ed8c7a2aefa2ab3e9a6ef5800','sql',true,'s',false),('platform.telegram_replay_v1(text,jsonb)','a3598d76df2c0bf876945fa306e0410e3249c2018ff62b21e4da2968beaacf32','plpgsql',true,'v',true),('platform.telegram_save_observation(uuid,uuid,bigint,bigint,jsonb)','97d4fe38521a276d4aac005feddf587a6c296e5e58ca909167cbcbb123be4816','plpgsql',true,'v',false),('platform.telegram_validate_observation(jsonb)','5aefbca98cb203f4bfc5e65101fbb6432c492858ac55fdae0b48fec520855ffc','plpgsql',false,'v',false),('platform.telegram_validate_projection(text,jsonb)','0d088863a241460dcc16b7ea45072bb7ac03303bfba9f4d2e13e0b91b5e4500b','plpgsql',false,'v',false),('platform.telegram_validate_v2(text,jsonb)','7304efba94d26f93ba4d7a69030878056eb611f855ee4620a3ea6cdf61f79003','plpgsql',false,'v',false),('platform.telegram_worker_probe(uuid,uuid)','3cd244acf19fe8e8916c9f339342056f3da7b7665e1d8e5cea27cf277220ee20','plpgsql',true,'v',true),('platform.turn_consumer_finalize(uuid,uuid,jsonb)','503318da5d3265664ba4416752a0c745550cafb6f1cdb18ee66ac40065e31eb6','plpgsql',true,'v',true),('platform.turn_consumer_replay(uuid,uuid)','4469b30f0df26f6bfb02777b2c5c8da184abc5b3bcae8dcdf45c871d9bbb7e6c','plpgsql',true,'s',true),('platform.turn_enqueue(uuid,uuid,uuid)','383110c7c42c8979410560f3d0d98b784844f5da16a0a1d7f8d04fb71bd26e5f','plpgsql',true,'v',false),('platform.turn_execute(uuid,uuid)','3bbd3e507d1b11425c2541d8300ca9d9e2c4cda172b77c05e2cc94b8d19c3b0d','plpgsql',true,'v',true),('platform.turn_group_message(uuid,uuid,uuid)','89687e327f17d1a00751192fda5a56e7aeac8297b539fe95b1317d01de8d78f7','plpgsql',true,'v',false),('platform.turn_immutable()','bfc42050fa3442c8eed763a861d16ae7fc6ea3f5f3646a193e54fe22704a7df9','plpgsql',false,'v',false),('platform.turn_ingress()','d8e6040eae9ce55f0e6d8f2b1338d4ea2e3b6b8a7d25f2e7da8963032e6488f0','plpgsql',true,'v',false),('platform.turn_material()','be30caa9fdb5cf0c3ca22e41559232e6cbe8d6246c62e9c343db539ec4303f3d','plpgsql',true,'v',false),('platform.turn_member_check()','8cbbd5b8ccd97858edc24ba68fd904e5b4af3068b355e506d7d5cc03af5b6293','plpgsql',true,'v',false),('platform.turn_members_consistent()','3acccfede293794fcc84890da99535a2730217fd1f11eb37c7ed153e2c675405','plpgsql',true,'v',false),('platform.turn_preflight(platform.messaging_jobs,boolean,boolean)','73f139ddac65b5e5b1098e40d1aaed541c140e7fcf00d4d0df8b45a15563034e','plpgsql',true,'v',false),('platform.turn_require_isolation()','ba0e99b67e71fc6d6fa6886967282f9c5bcf7b0046e5812d34dfdfc5df8dd5d3','plpgsql',false,'v',false),('platform.turn_seal(uuid,uuid,timestamptz,uuid,boolean)','bc83afb9ce59538928edfe86cdc74c7ab1951640244570d05177aa3bcd08676f','plpgsql',true,'v',false),('platform.turn_snapshot(uuid,uuid)','ffac09fed2777b0439558faa5b071445fb1d6c74e605ff7331e29b67788e9e3e','plpgsql',true,'v',false),('platform.turn_supersede(platform.messaging_jobs)','6a26f30e71da741ab60ca4c4a191fa44aab528f36588a564bcb5a0069f8eeab2','plpgsql',true,'v',false),('platform.update_billing_contact(bigint,text,text)','80d0ce6854e33601584fe350ee4b586796d0066b6288bf9a26aeec80aa23f3ed','plpgsql',true,'v',true)),
      columns_expected(table_name,column_names) AS (VALUES ('app.audit_events',ARRAY['workspace_id','audit_event_id','occurred_at','actor_kind','actor_user_account_id','correlation_id','event_type','object_type','object_id','object_version','payload','billing_account_object_id','message_object_id','conversation_object_id','conversation_control_generation','escalation_object_id','escalation_operation','material_target_id','material_source_receipt_id','native_revision_id','native_policy_receipt_id','native_connection_id','native_conversation_id']::text[]),('app.business_members',ARRAY['workspace_id','id','business_id','user_account_id','name','role','status','version','created_at']::text[]),('app.businesses',ARRAY['workspace_id','id','name','status','version','created_at']::text[]),('app.channel_connections',ARRAY['workspace_id','id','business_id','provider','bot_identity','external_connection_id','status','version','created_at','human_context_policy','human_context_policy_epoch']::text[]),('app.client_identities',ARRAY['workspace_id','id','client_id','provider','external_user_id','created_at']::text[]),('app.clients',ARRAY['workspace_id','id','version','created_at']::text[]),('app.conversation_turn_messages',ARRAY['workspace_id','message_id','turn_id','conversation_id','connection_id','direction','content_type','origin_inbox_id','turn_ingress_at','turn_ingress_seq','file_id','membership_form','initial_suppression_id','suppression_disposition']::text[]),('app.conversation_turns',ARRAY['workspace_id','id','conversation_id','connection_id','provider_chat_id','revision','control_generation','state','policy_version','debounce_ms','group_ms','media_ms','max_members','member_count','media_group_id','first_ingress_at','last_ingress_at','hard_at','quiet_at','media_deadline_at','seal_time','closed_at','ready_at','readiness','error_code','created_at','ingress_control_mode','activation_fence_seq','material_invalidated']::text[]),('app.conversations',ARRAY['workspace_id','id','connection_id','business_id','client_id','identity_id','provider_chat_id','version','created_at','last_client_inbound_at','control_mode','control_generation','activation_fence_seq','human_observation_epoch','human_context_revision_id']::text[]),('app.escalations',ARRAY['workspace_id','id','namespace','conversation_id','client_id','connection_id','turn_id','source_job_id','source_job_kind','source_job_step','source_claim_token','turn_revision','resume_receipt_id','control_generation','activation_fence_seq','input_context_version','waiting_context_version','request_snapshot','context_fingerprint','request_fingerprint','creation_result','reason','assignee_user_account_id','question','policy','created_at','due_at','second_reminder_at','expires_at','first_reminded_at','second_reminded_at','version','status','closure_reason','completed_at','answer_text','decided_by_user_account_id']::text[]),('app.file_objects',ARRAY['workspace_id','id','message_id','connection_id','conversation_id','required_direction','required_content_type','status','winner_intent_id','winner_state','storage_key','mime_type','size_bytes','sha256','width','height','error_code','version','created_at','completed_at']::text[]),('app.locations',ARRAY['workspace_id','id','business_id','name','status','version','created_at']::text[]),('app.messages',ARRAY['workspace_id','id','conversation_id','connection_id','provider_chat_id','provider_message_id','direction','content_type','text','image_file_id','media_group_id','occurred_at','projection_fingerprint','version','created_at']::text[]),('app.outbox_events',ARRAY['workspace_id','id','connection_id','message_id','kind','required_direction','status','attempt_id','provider_message_id','error_code','completed_at','version','created_at']::text[]),('platform.ai_deliveries',ARRAY['workspace_id','job_id','source_job_id','source_claim_hash','connection_id','turn_id','turn_revision','kind','step','run_id','selected_kind','message_id','outbox_id','send_job_id','escalation_id','intent_context_version','created_at','provider_session_id']::text[]),('platform.ai_provider_calls',ARRAY['workspace_id','run_id','sequence','claim_hash','attempt_count','budget','completion','reserved_at','completed_at']::text[]),('platform.ai_provider_sessions',ARRAY['id','workspace_id','connection_id','conversation_id','client_id','chat_id','bot_identity','data_profile','starts_at','expires_at','max_calls','max_rub','review_sha256','review_checked_at','config','active','created_at']::text[]),('platform.ai_runs',ARRAY['workspace_id','id','job_id','connection_id','conversation_id','client_id','business_id','kind','step','turn_id','turn_revision','resume_receipt_id','control_generation','binding','snapshot','snapshot_digest','storage_fingerprint','config','config_fingerprint','deadline','calls_used','reads_used','tokens_reserved','cost_reserved','read_audit','result','selected_at','winning_claim_hash','created_at']::text[]),('platform.alembic_version',ARRAY['version_num']::text[]),('platform.auth_credentials',ARRAY['user_account_id','login','password_hash','version','created_at']::text[]),('platform.auth_sessions',ARRAY['token_hash','user_account_id','credential_version','account_version','created_at','expires_at','revoked_at']::text[]),('platform.billing_contact_command_receipts',ARRAY['workspace_id','receipt_id','billing_account_id','operation','idempotency_key','request_fingerprint','expected_version','status','result_version','result_outcome','created_at','completed_at']::text[]),('platform.channel_routes',ARRAY['workspace_id','id','connection_id','provider','bot_identity','route_key','created_at']::text[]),('platform.conversation_control_receipts',ARRAY['workspace_id','id','operation_namespace','operation','idempotency_key','conversation_id','client_id','actor_user_account_id','correlation_id','expected_generation','expected_context_version','previous_mode','accepted_mode','previous_generation','accepted_generation','context_version','activation_fence_seq','request_fingerprint','audit_event_id','audit_event_type','accepted_at','result','guard_profile','human_context_revision_id','human_context_policy_epoch','human_observation_epoch']::text[]),('platform.escalation_command_receipts',ARRAY['workspace_id','id','namespace','idempotency_key','escalation_id','conversation_id','client_id','actor_user_account_id','correlation_id','operation','expected_version','expected_control_generation','expected_context_version','accepted_version','accepted_status','accepted_context_version','request_fingerprint','audit_event_id','audit_event_type','accepted_at','result']::text[]),('platform.file_object_uploads',ARRAY['workspace_id','id','file_id','job_id','claim_token','storage_key','mime_type','size_bytes','sha256','width','height','status','cleanup_claim_token','cleanup_lease_until','cleanup_attempts','next_check_at','last_checked_at','cleanup_outcome','version','created_at']::text[]),('platform.human_context_observations',ARRAY['workspace_id','id','conversation_id','client_id','connection_id','provider_chat_id','epoch','policy_epoch','control_generation','first_source_receipt_id','classification','semantic_digest','accepted_at']::text[]),('platform.human_context_policy_receipts',ARRAY['workspace_id','id','connection_id','business_id','provider','bot_identity','external_connection_id','owner_user_id','actor_db_role','namespace','idempotency_key','request_fingerprint','operation','expected_policy','expected_policy_epoch','accepted_policy','accepted_policy_epoch','change','source_profile','audit_event_id','event_type','accepted_at','result']::text[]),('platform.human_context_reconciliations',ARRAY['workspace_id','id','conversation_id','client_id','connection_id','provider_chat_id','actor_user_account_id','namespace','idempotency_key','request_fingerprint','correlation_id','previous_revision_id','revision_no','expected_generation','expected_context_version','accepted_context_version','policy_epoch','observation_epoch','reviewed_ingress_seq','reviewed_input_state_hash','reviewed_gap_digest','reviewed_gap_overflow','disposition','context_text','source_media','attestation','audit_event_id','event_type','accepted_at','result']::text[]),('platform.inbox_events',ARRAY['workspace_id','id','connection_id','provider','bot_identity','external_connection_id','required_direction','event_id','normalized_event','event_fingerprint','correlation_id','received_at','status','result_code','message_id','completed_at','version','turn_ingress_at','turn_ingress_seq','turn_control_generation','turn_control_mode','turn_activation_fence_seq','material_result','material_claim_token','human_context_source_receipt_id','human_context_observation_id']::text[]),('platform.message_initial_suppressions',ARRAY['workspace_id','id','message_id','target_id','origin_inbox_id','effect_id','source_receipt_id','previous_version','accepted_version','initial_material','fold_witnesses','membership_disposition']::text[]),('platform.message_material_effects',ARRAY['workspace_id','id','target_id','message_id','source_receipt_id','audit_event_id','event_type','previous_version','accepted_version','reason','accepted_at']::text[]),('platform.message_material_targets',ARRAY['workspace_id','id','connection_id','provider_chat_id','provider_message_id','message_id','conversation_id','client_id','direction','outbox_id','inbound_provider_id','required_sent','quarantined','original_grouping_closed','origin_identity','deleted','undated_seen','max_edit_at','candidate','dated_conflict','delete_receipt','undated_receipt','candidate_receipt','conflict_receipt','current_material']::text[]),('platform.messaging_command_receipts',ARRAY['workspace_id','id','operation','idempotency_key','request_fingerprint','actor_user_account_id','correlation_id','message_id','outbox_id','audit_event_id','accepted_at']::text[]),('platform.messaging_jobs',ARRAY['workspace_id','id','connection_id','kind','inbox_id','outbox_id','correlation_id','status','available_at','claim_token','lease_until','worker_id','attempt_count','first_started_at','error_code','completed_at','last_attempt_id','last_claim_token','last_outcome','last_provider_message_id','last_error_code','version','created_at','file_id','last_retry_after_seconds','last_retry_due','telegram_probe_claim','telegram_probe_generation','telegram_probe_version','turn_id','turn_revision','step','turn_outcome','turn_input','guard_rejection','escalation_id','escalation_outcome','context_block_reason','context_wait_claim_token','context_wait_result']::text[]),('platform.plan_entitlements',ARRAY['plan_revision_id','capability_key','value_kind','enabled','limit_value','criticality','created_at']::text[]),('platform.saas_plan_revisions',ARRAY['plan_revision_id','plan_id','revision','publication_state','published_at','created_at']::text[]),('platform.saas_plans',ARRAY['plan_id','code','display_name','status','created_at']::text[]),('platform.telegram_connection_state',ARRAY['workspace_id','connection_id','provider','bot_identity','external_connection_id','owner_user_id','generation','observation_version','observed_generation','observed_at','observation_xid','is_enabled','can_reply','error_code','material_enabled']::text[]),('platform.telegram_provenance',ARRAY['receipt_id','codec','bot_identity','update_id','workspace_id','connection_id','inbox_id','projection','material_enabled','human_context_observation_id']::text[]),('platform.telegram_update_receipts',ARRAY['id','bot_identity','update_id','fingerprint','kind','result_code','workspace_id','connection_id','inbox_id','received_at','codec']::text[]),('platform.turn_consumer_receipts',ARRAY['workspace_id','job_id','connection_id','kind','turn_id','turn_revision','step','consumer','winning_claim_token','input_context_version','input_control_generation','snapshot_digest','result','accepted_at']::text[]),('platform.turn_guard_receipts',ARRAY['workspace_id','job_id','winning_claim_token','connection_id','conversation_id','client_id','turn_id','turn_revision','resume_receipt_id','input_control_generation','activation_fence_seq','input_context_version','snapshot_digest','consumer','request_fingerprint','result_text','outcome','accepted_at','intent_context_version','message_id','outbox_id','send_job_id','namespace','kind','step','direction','content_type','send_kind']::text[]),('platform.user_accounts',ARRAY['id','status','version','created_at']::text[]),('platform.workspace_billing_accounts',ARRAY['workspace_id','billing_account_id','contact_display_name','version','created_at','updated_at']::text[]),('platform.workspace_memberships',ARRAY['workspace_id','user_account_id','role','status','version','created_at']::text[]),('platform.workspace_service_modes',ARRAY['workspace_id','service_mode_id','mode','reason_code','effective_from','effective_until','version','created_at','updated_at']::text[]),('platform.workspace_subscriptions',ARRAY['workspace_id','subscription_id','plan_revision_id','required_publication_state','status','funding_mode','effective_from','effective_until','version','created_at','updated_at']::text[]),('platform.workspaces',ARRAY['id','status','version','created_at']::text[])),
      functions AS MATERIALIZED (SELECT p.*,n.nspname||'.'||p.proname AS name,l.lanname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        JOIN pg_language l ON l.oid=p.prolang WHERE n.nspname IN ('app','platform') AND p.prokind='f'),
      tables AS MATERIALIZED (SELECT r.oid,n.nspname||'.'||r.relname AS name,r.relowner,r.relrowsecurity,r.relforcerowsecurity,r.relacl,
        array_agg(a.attname::text ORDER BY a.attnum) AS columns FROM pg_class r JOIN pg_namespace n ON n.oid=r.relnamespace
        JOIN pg_attribute a ON a.attrelid=r.oid AND a.attnum>0 AND NOT a.attisdropped WHERE n.nspname IN ('app','platform') AND r.relkind='r'
        GROUP BY r.oid,n.nspname,r.relname,r.relowner,r.relrowsecurity,r.relforcerowsecurity,r.relacl),
      validity AS MATERIALIZED (SELECT
        (SELECT count(*) FROM functions)=194 AND (SELECT count(DISTINCT to_regprocedure(signature)) FROM expected)=193
        AND NOT EXISTS(SELECT 1 FROM expected e LEFT JOIN functions f ON f.oid=to_regprocedure(e.signature)
          WHERE f.oid IS NULL OR encode(sha256(convert_to(f.prosrc,'UTF8')),'hex')<>e.body_hash OR f.lanname<>e.language
            OR f.prosecdef<>e.security_definer OR f.provolatile::text<>e.volatility OR f.proowner<>'asm_migrator'::regrole
            OR has_function_privilege('asm_runtime',f.oid,'EXECUTE')<>e.runtime_execute
            OR f.proconfig IS DISTINCT FROM ARRAY['search_path=pg_catalog, pg_temp']
            OR EXISTS(SELECT 1 FROM aclexplode(f.proacl) a WHERE a.grantee=0 AND a.privilege_type='EXECUTE'))
        AND EXISTS(SELECT 1 FROM functions f WHERE f.oid='platform.ai_reply_rights_schema_profile()'::regprocedure
          AND f.proowner='asm_migrator'::regrole AND f.lanname='sql' AND f.prosecdef AND f.provolatile='s'
          AND f.proconfig=ARRAY['search_path=pg_catalog, pg_temp'] AND NOT has_function_privilege('asm_runtime',f.oid,'EXECUTE')
          AND NOT EXISTS(SELECT 1 FROM aclexplode(f.proacl) a WHERE a.grantee=0 AND a.privilege_type='EXECUTE'))
        AND EXISTS(SELECT 1 FROM pg_roles WHERE rolname='asm_runtime' AND rolcanlogin AND NOT rolsuper AND NOT rolbypassrls
          AND NOT rolinherit AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolreplication)
        AND NOT EXISTS(SELECT 1 FROM pg_auth_members WHERE member='asm_runtime'::regrole)
        AND (SELECT count(*) FROM tables)=49 AND NOT EXISTS(SELECT 1 FROM columns_expected e LEFT JOIN tables t ON t.name=e.table_name
          WHERE t.oid IS NULL OR t.columns IS DISTINCT FROM e.column_names)
        AND NOT EXISTS(SELECT 1 FROM tables WHERE name IN ('platform.human_context_observations','platform.human_context_reconciliations','platform.human_context_policy_receipts','platform.ai_runs','platform.ai_provider_calls','platform.ai_deliveries','platform.ai_provider_sessions')
          AND (relowner<>'asm_migrator'::regrole OR NOT relrowsecurity OR NOT relforcerowsecurity OR has_table_privilege('asm_runtime',oid,'SELECT,INSERT,UPDATE,DELETE')))
        AND (SELECT version_num FROM platform.alembic_version)='0017' AS valid),
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
      SELECT jsonb_build_object('schema_revision','0017','valid',coalesce(v.valid,false)
        AND encode(sha256(convert_to((c.value-'functions')::text,'UTF8')),'hex')='ab6bbeed0be3e8596f7ee76d235d709dc29866808491741dfacc68d8af64955d',
        'profile_sha256',encode(sha256(convert_to(E'asm:m3:native_schema:v1\\n'||c.value::text,'UTF8')),'hex')) FROM validity v CROSS JOIN catalog c $$"""


def upgrade():
    op.execute("LOCK TABLE platform.messaging_jobs IN ACCESS EXCLUSIVE MODE")
    op.execute(
        "ALTER TABLE platform.messaging_jobs DROP CONSTRAINT messaging_jobs_telegram_probe_check"
    )
    op.execute(
        "ALTER TABLE platform.messaging_jobs ADD CONSTRAINT messaging_jobs_telegram_probe_check "
        + REPLY_PROBE_CHECK
    )
    for sql in CURRENT_FUNCTIONS.values():
        op.execute(sql)
    for sql in FUNCTIONS.values():
        op.execute(sql)
    for signature in FUNCTIONS:
        op.execute(f"REVOKE ALL ON FUNCTION platform.{signature} FROM PUBLIC,asm_runtime")
    for signature in (
        "ai_reply_rights_probe(uuid,uuid,uuid)",
        "ai_reply_rights_commit(uuid,uuid,uuid,bigint,bigint,jsonb,jsonb)",
    ):
        op.execute(f"GRANT EXECUTE ON FUNCTION platform.{signature} TO asm_runtime")
    if PROFILE_SQL:
        op.execute(PROFILE_SQL)
        op.execute(
            "REVOKE ALL ON FUNCTION platform.ai_reply_rights_schema_profile() FROM PUBLIC,asm_runtime"
        )


def downgrade():
    op.execute("LOCK TABLE platform.messaging_jobs IN ACCESS EXCLUSIVE MODE")
    # Discard only ephemeral generation-job probe metadata. Canonical results,
    # calls, reservations, Outbox and final-send probes remain unchanged.
    op.execute(
        "UPDATE platform.messaging_jobs SET telegram_probe_claim=NULL,telegram_probe_generation=NULL,telegram_probe_version=NULL WHERE kind='PROCESS_TURN' AND step='AI_GENERATE' AND telegram_probe_claim IS NOT NULL"
    )
    op.execute(
        "ALTER TABLE platform.messaging_jobs DROP CONSTRAINT messaging_jobs_telegram_probe_check"
    )
    op.execute(
        "ALTER TABLE platform.messaging_jobs ADD CONSTRAINT messaging_jobs_telegram_probe_check "
        + PREVIOUS_PROBE_CHECK
    )
    for sql in CURRENT_ORIGINAL.values():
        op.execute(sql.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1))
    if PROFILE_SQL:
        op.execute("DROP FUNCTION platform.ai_reply_rights_schema_profile()")
    for signature in reversed(tuple(FUNCTIONS)):
        op.execute(f"DROP FUNCTION platform.{signature}")
