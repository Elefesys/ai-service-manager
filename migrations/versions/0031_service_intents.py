"""Admit synthetic v8 commercial intent proposals through the current Turn."""

from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None

RESULT_VALID = r"""CREATE FUNCTION platform.service_intent_result_valid(p jsonb) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE intents jsonb; item jsonb; source jsonb;
BEGIN
  IF NOT (p ? 'intents') THEN RETURN platform.intake_result_valid(p); END IF;
  intents:=p->'intents';
  IF p->>'kind' IS DISTINCT FROM 'no_reply' OR p->'intake'->>'category' IS DISTINCT FROM 'NEW_TATTOO'
    OR platform.intake_result_valid(p-'intents') IS NOT TRUE OR jsonb_typeof(intents) IS DISTINCT FROM 'array'
    THEN RETURN false; END IF;
  IF jsonb_array_length(intents) NOT IN (1,2) THEN RETURN false; END IF;
  FOR item IN SELECT value FROM jsonb_array_elements(intents) LOOP
    source:=item->'source';
    IF platform.material_object(item,ARRAY['name','source']) IS NOT TRUE
      OR item->>'name' IS NULL OR item->>'name' NOT IN ('prepare_service_request','request_owner_decision')
      OR platform.material_object(source,ARRAY['message_id','source_version']) IS NOT TRUE
      OR platform.human_context_uuid(source->'message_id') IS NOT TRUE
      OR jsonb_typeof(source->'source_version') IS DISTINCT FROM 'string'
      OR source->>'source_version' !~ '^[0-9a-f]{64}$' THEN RETURN false; END IF;
  END LOOP;
  RETURN jsonb_array_length(intents)=1 OR (
    intents->0->>'name'='prepare_service_request' AND intents->1->>'name'='request_owner_decision'
    AND (intents->0->'source')=(intents->1->'source')
  );
END $$"""


V7_CONSTRAINTS = {
    ("platform.ai_runs", "ai_run_result"): "CHECK(result IS NULL OR (CASE WHEN "
    "config->>'prompt_revision'='conversation_v7' "
    "THEN "
    "platform.intake_result_valid(result) "
    "WHEN "
    "config->>'prompt_revision'='conversation_v6' "
    "THEN "
    "platform.portfolio_delivery_result_valid(result) "
    "ELSE "
    "platform.ai_runtime_result_valid(result) "
    "END) IS TRUE)",
    ("platform.ai_runs", "ai_knowledge_shape"): "CHECK((knowledge_pin IS NULL AND "
    "active_projection IS NULL AND "
    "config->>'prompt_revision'='conversation_v2') "
    "OR (knowledge_pin IS NOT NULL "
    "AND active_projection IS NOT "
    "NULL AND "
    "config->>'prompt_revision' IN "
    "('conversation_v3','conversation_v4','conversation_v5','conversation_v6','conversation_v7') "
    "AND "
    "platform.ai_knowledge_valid(knowledge_pin,active_projection,workspace_id,business_id) "
    "IS TRUE))",
    ("platform.ai_runs", "ai_search_shape"): "CHECK((config->>'prompt_revision' "
    "IN "
    "('conversation_v4','conversation_v5','conversation_v6','conversation_v7') "
    "AND search_pin IS NOT NULL AND "
    "platform.knowledge_search_pin_valid(search_pin) "
    "IS TRUE AND "
    "search_pin->>'business_id'=business_id::text "
    "AND "
    "search_pin->'release_id'=knowledge_pin->'release_id' "
    "AND "
    "search_pin->'activation_version'=knowledge_pin->'activation_version') "
    "OR (config->>'prompt_revision' NOT "
    "IN "
    "('conversation_v4','conversation_v5','conversation_v6','conversation_v7') "
    "AND search_pin IS NULL AND "
    "search_refs IS NULL))",
    ("platform.ai_runs", "ai_portfolio_shape"): "CHECK((config->>'prompt_revision' "
    "IN "
    "('conversation_v5','conversation_v6','conversation_v7') "
    "AND portfolio_pin IS NOT NULL "
    "AND "
    "platform.portfolio_pin_valid(portfolio_pin) "
    "IS TRUE AND "
    "portfolio_pin->>'business_id'=business_id::text "
    "AND "
    "portfolio_pin->'release_id'=knowledge_pin->'release_id' "
    "AND "
    "portfolio_pin->'activation_version'=knowledge_pin->'activation_version' "
    "AND media_pin IS NOT NULL AND "
    "platform.portfolio_media_pin_valid(media_pin) "
    "IS TRUE AND "
    "media_pin->>'business_id'=business_id::text "
    "AND "
    "media_pin->>'client_id'=client_id::text "
    "AND "
    "media_pin->>'conversation_id'=conversation_id::text "
    "AND portfolio_session_id IS NOT "
    "NULL) OR "
    "(config->>'prompt_revision' NOT "
    "IN "
    "('conversation_v5','conversation_v6','conversation_v7') "
    "AND portfolio_pin IS NULL AND "
    "media_pin IS NULL AND "
    "portfolio_refs IS NULL AND "
    "portfolio_session_id IS NULL))",
    (
        "platform.portfolio_ai_sessions",
        "portfolio_ai_sessions_profile_id_check",
    ): "CHECK(profile_id "
    "IN "
    "('SYNTHETIC_VISION_PORTFOLIO_V1','SYNTHETIC_PORTFOLIO_PHOTO_V1','SYNTHETIC_INTAKE_V1'))",
    ("platform.ai_runs", "ai_runs_check4"): "CHECK(delivery_read_audit IS NULL OR "
    "config->>'prompt_revision' IN "
    "('conversation_v6','conversation_v7') "
    "AND reads_used=1 AND "
    "jsonb_typeof(delivery_read_audit)='object' "
    "AND "
    "octet_length(delivery_read_audit::text)<=2048)",
    ("platform.ai_runs", "ai_runs_check5"): "CHECK(intake_pin IS NULL OR "
    "config->>'prompt_revision'='conversation_v7' "
    "AND intake_pin ~ '^[0-9a-f]{64}$')",
}

V8_CONSTRAINTS = {
    ("platform.ai_runs", "ai_run_result"): "CHECK(result IS NULL OR (CASE WHEN "
    "config->>'prompt_revision'='conversation_v8' "
    "THEN "
    "platform.service_intent_result_valid(result)\n"
    "            WHEN "
    "config->>'prompt_revision'='conversation_v7' "
    "THEN "
    "platform.intake_result_valid(result) "
    "WHEN "
    "config->>'prompt_revision'='conversation_v6' "
    "THEN "
    "platform.portfolio_delivery_result_valid(result) "
    "ELSE "
    "platform.ai_runtime_result_valid(result) "
    "END) IS TRUE)",
    ("platform.ai_runs", "ai_knowledge_shape"): "CHECK((knowledge_pin IS NULL AND "
    "active_projection IS NULL AND "
    "config->>'prompt_revision'='conversation_v2') "
    "OR (knowledge_pin IS NOT NULL "
    "AND active_projection IS NOT "
    "NULL AND "
    "config->>'prompt_revision' IN "
    "('conversation_v3','conversation_v4','conversation_v5','conversation_v6','conversation_v7','conversation_v8') "
    "AND "
    "platform.ai_knowledge_valid(knowledge_pin,active_projection,workspace_id,business_id) "
    "IS TRUE))",
    ("platform.ai_runs", "ai_search_shape"): "CHECK((config->>'prompt_revision' "
    "IN "
    "('conversation_v4','conversation_v5','conversation_v6','conversation_v7','conversation_v8') "
    "AND search_pin IS NOT NULL AND "
    "platform.knowledge_search_pin_valid(search_pin) "
    "IS TRUE AND "
    "search_pin->>'business_id'=business_id::text "
    "AND "
    "search_pin->'release_id'=knowledge_pin->'release_id' "
    "AND "
    "search_pin->'activation_version'=knowledge_pin->'activation_version') "
    "OR (config->>'prompt_revision' NOT "
    "IN "
    "('conversation_v4','conversation_v5','conversation_v6','conversation_v7','conversation_v8') "
    "AND search_pin IS NULL AND "
    "search_refs IS NULL))",
    ("platform.ai_runs", "ai_portfolio_shape"): "CHECK((config->>'prompt_revision' "
    "IN "
    "('conversation_v5','conversation_v6','conversation_v7','conversation_v8') "
    "AND portfolio_pin IS NOT NULL "
    "AND "
    "platform.portfolio_pin_valid(portfolio_pin) "
    "IS TRUE AND "
    "portfolio_pin->>'business_id'=business_id::text "
    "AND "
    "portfolio_pin->'release_id'=knowledge_pin->'release_id' "
    "AND "
    "portfolio_pin->'activation_version'=knowledge_pin->'activation_version' "
    "AND media_pin IS NOT NULL AND "
    "platform.portfolio_media_pin_valid(media_pin) "
    "IS TRUE AND "
    "media_pin->>'business_id'=business_id::text "
    "AND "
    "media_pin->>'client_id'=client_id::text "
    "AND "
    "media_pin->>'conversation_id'=conversation_id::text "
    "AND portfolio_session_id IS NOT "
    "NULL) OR "
    "(config->>'prompt_revision' NOT "
    "IN "
    "('conversation_v5','conversation_v6','conversation_v7','conversation_v8') "
    "AND portfolio_pin IS NULL AND "
    "media_pin IS NULL AND "
    "portfolio_refs IS NULL AND "
    "portfolio_session_id IS NULL))",
    (
        "platform.portfolio_ai_sessions",
        "portfolio_ai_sessions_profile_id_check",
    ): "CHECK(profile_id "
    "IN "
    "('SYNTHETIC_VISION_PORTFOLIO_V1','SYNTHETIC_PORTFOLIO_PHOTO_V1','SYNTHETIC_INTAKE_V1','SYNTHETIC_SERVICE_INTENTS_V1'))",
    ("platform.ai_runs", "ai_runs_check4"): "CHECK(delivery_read_audit IS NULL OR "
    "config->>'prompt_revision' IN "
    "('conversation_v6','conversation_v7','conversation_v8') "
    "AND reads_used=1 AND "
    "jsonb_typeof(delivery_read_audit)='object' "
    "AND "
    "octet_length(delivery_read_audit::text)<=2048)",
    ("platform.ai_runs", "ai_runs_check5"): "CHECK(intake_pin IS NULL OR "
    "config->>'prompt_revision' IN "
    "('conversation_v7','conversation_v8') "
    "AND intake_pin ~ '^[0-9a-f]{64}$')",
}

V7_FUNCTIONS = {
    "platform.ai_runtime_config_valid": r"""CREATE OR REPLACE FUNCTION platform.ai_runtime_config_valid(p jsonb) RETURNS boolean
LANGUAGE sql IMMUTABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
SELECT (p->>'prompt_revision'='conversation_v7' AND p->>'schema_revision'='conversation_result_v3' AND p->'limits'->>'currency'='RUB' AND platform.ai_synthetic_config_valid(jsonb_set(jsonb_set(p,'{prompt_revision}','"conversation_v2"'::jsonb),'{schema_revision}','"conversation_result_v1"'::jsonb))) OR (p->>'prompt_revision'='conversation_v6' AND p->>'schema_revision'='conversation_result_v2'
 AND p->'limits'->>'currency'='RUB'
 AND platform.ai_synthetic_config_valid(jsonb_set(jsonb_set(p,'{prompt_revision}','"conversation_v2"'::jsonb),'{schema_revision}','"conversation_result_v1"'::jsonb))) OR (p->>'prompt_revision' IN ('conversation_v4','conversation_v5') AND (p->>'prompt_revision'<>'conversation_v5' OR p->'limits'->>'currency'='RUB') AND platform.ai_synthetic_config_valid(jsonb_set(p,'{prompt_revision}','"conversation_v2"'::jsonb))) OR platform.ai_synthetic_config_valid(p) OR platform.ai_provider_config_valid(p) OR
  (p->>'prompt_revision'='conversation_v3' AND
    platform.ai_synthetic_config_valid(jsonb_set(p,'{prompt_revision}','"conversation_v2"'::jsonb))) $$""",
    "platform.ai_runtime_view": r"""CREATE OR REPLACE FUNCTION platform.ai_runtime_view(r platform.ai_runs) RETURNS jsonb
      LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      SELECT jsonb_build_object('run_id',r.id,'binding',r.binding,'snapshot',r.snapshot,'storage_fingerprint',r.storage_fingerprint,
        'config',r.config,'deadline',r.deadline,'reads_used',r.reads_used,'budget',jsonb_build_object(
          'calls_used',r.calls_used,'reads_reserved',r.reads_used,'tokens_reserved',r.tokens_reserved,
          'cost_reserved',r.cost_reserved::text,'currency',r.config->'limits'->>'currency'))
        ||CASE WHEN r.knowledge_pin IS NULL THEN '{}'::jsonb ELSE
          jsonb_build_object('knowledge_pin',r.knowledge_pin,'active_projection',r.active_projection) END
        ||CASE WHEN r.search_pin IS NOT NULL THEN jsonb_build_object('search_pin',r.search_pin,'search_refs',r.search_refs) ELSE '{}'::jsonb END||platform.portfolio_runtime_data(r)||CASE WHEN r.config->>'prompt_revision'='conversation_v7' THEN jsonb_build_object('intake',platform.intake_project(r.workspace_id,r.business_id,r.conversation_id,r.client_id)) ELSE '{}'::jsonb END $$""",
    "platform.ai_runtime_receipt": r"""CREATE OR REPLACE FUNCTION platform.ai_runtime_receipt(r platform.ai_runs) RETURNS jsonb
      LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      SELECT jsonb_build_object('run_id',r.id,'job_id',r.job_id,'turn_id',r.turn_id,'turn_revision',r.turn_revision,
        'selected_at',r.selected_at,'result',r.result,'send_permit',false)
        ||CASE WHEN r.knowledge_pin IS NULL THEN '{}'::jsonb ELSE jsonb_build_object('knowledge_pin',r.knowledge_pin) END
        ||CASE WHEN r.search_pin IS NOT NULL THEN jsonb_build_object('search_pin',r.search_pin,'search_refs',r.search_refs) ELSE '{}'::jsonb END||CASE WHEN r.config->>'prompt_revision' IN ('conversation_v5','conversation_v6','conversation_v7') THEN jsonb_build_object('portfolio_pin',r.portfolio_pin,'media_pin',r.media_pin,'portfolio_refs',r.portfolio_refs) ELSE '{}'::jsonb END $$""",
    "platform.ai_runtime_command": r"""CREATE OR REPLACE FUNCTION platform.ai_runtime_command(p_job uuid,p_claim uuid,p_op text,p jsonb) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE j platform.messaging_jobs%ROWTYPE; r platform.ai_runs%ROWTYPE; previous platform.ai_provider_calls%ROWTYPE;
        fresh jsonb; knowledge jsonb; search jsonb; portfolio jsonb; media jsonb; session uuid; auxiliary numeric:=0; b jsonb; cfg jsonb; lim jsonb; expiry timestamptz; next_job uuid; n integer; tokens integer; cost numeric;
      BEGIN
        PERFORM platform.turn_require_isolation();
        j:=platform.messaging_guard(p_job,p_claim);
        IF current_database() NOT IN ('asm_local','asm_test') OR jsonb_typeof(p) IS DISTINCT FROM 'object' OR octet_length(p::text)>32768 THEN
          RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
        IF p_op='ENQUEUE' THEN
          IF j.kind<>'PROCESS_TURN' OR j.step<>'TEST_CONSUME' OR p<>'{}'::jsonb THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
          PERFORM platform.ai_runtime_current(j,NULL);
          INSERT INTO platform.messaging_jobs(workspace_id,connection_id,kind,turn_id,turn_revision,step,correlation_id)
            VALUES(j.workspace_id,j.connection_id,'PROCESS_TURN',j.turn_id,j.turn_revision,'AI_GENERATE',j.correlation_id)
            ON CONFLICT(workspace_id,turn_id,turn_revision,step) DO NOTHING;
          SELECT id INTO STRICT next_job FROM platform.messaging_jobs WHERE workspace_id=j.workspace_id AND turn_id=j.turn_id AND turn_revision=j.turn_revision AND step='AI_GENERATE';
          RETURN jsonb_build_object('job_id',next_job);
        END IF;
        IF j.kind<>'PROCESS_TURN' OR j.step<>'AI_GENERATE' THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
        SELECT * INTO r FROM platform.ai_runs WHERE workspace_id=j.workspace_id AND job_id=j.id FOR UPDATE;
        IF p_op='PREPARE' THEN
          cfg:=p->'config';
          IF NOT platform.material_object(p,ARRAY['config','deadline']||CASE WHEN cfg->>'prompt_revision' IN ('conversation_v5','conversation_v6','conversation_v7') THEN ARRAY['portfolio_session_id'] ELSE ARRAY[]::text[] END) OR jsonb_typeof(p->'deadline') IS DISTINCT FROM 'string'
            OR platform.ai_runtime_config_valid(cfg) IS NOT TRUE OR cfg->>'prompt_revision' NOT IN ('conversation_v3','conversation_v4','conversation_v5','conversation_v6','conversation_v7') THEN
            RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
          IF r.id IS NOT NULL AND r.config IS DISTINCT FROM cfg THEN RAISE EXCEPTION 'IDEMPOTENCY_KEY_CONFLICT' USING ERRCODE='P2001'; END IF;
          BEGIN fresh:=platform.ai_runtime_current(j,r.snapshot);
          EXCEPTION WHEN SQLSTATE 'P2001' THEN
            IF r.id IS NOT NULL AND SQLERRM='AI_STALE' THEN RAISE EXCEPTION 'IDEMPOTENCY_KEY_CONFLICT' USING ERRCODE='P2001'; END IF;
            RAISE;
          END;
          IF cfg->'route'->>'execution'='PROVIDER' THEN
            PERFORM platform.ai_provider_guard((SELECT provider_session_id FROM platform.ai_deliveries WHERE job_id=j.id),j,cfg);
          ELSIF (SELECT provider_session_id FROM platform.ai_deliveries WHERE job_id=j.id) IS NOT NULL THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
          IF r.id IS NOT NULL THEN
            IF fresh->'binding' IS DISTINCT FROM r.binding OR platform.ai_knowledge_current(r) IS NOT TRUE OR platform.knowledge_runtime_current(r) IS NOT TRUE THEN RAISE EXCEPTION 'IDEMPOTENCY_KEY_CONFLICT' USING ERRCODE='P2001'; END IF;
            RETURN platform.ai_runtime_view(r);
          END IF;
          expiry:=least((p->>'deadline')::timestamptz,clock_timestamp()+(cfg->'limits'->>'duration_seconds')::numeric*interval '1 second');
          IF NOT isfinite(expiry) OR expiry<=clock_timestamp() THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
          b:=fresh->'binding';
          knowledge:=platform.ai_knowledge_snapshot(j.workspace_id,(b->>'business_id')::uuid);
          search:=CASE WHEN cfg->>'prompt_revision' IN ('conversation_v4','conversation_v5','conversation_v6','conversation_v7') THEN platform.knowledge_availability(j.workspace_id,(b->>'business_id')::uuid,(knowledge->'knowledge_pin'->>'release_id')::uuid,(knowledge->'knowledge_pin'->>'activation_version')::bigint) END;
          IF cfg->>'prompt_revision' IN ('conversation_v5','conversation_v6','conversation_v7') THEN
            IF platform.human_context_uuid(p->'portfolio_session_id') IS NOT TRUE THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
            session:=(p->>'portfolio_session_id')::uuid;
            IF cfg->>'prompt_revision' IN ('conversation_v6','conversation_v7') THEN PERFORM platform.intake_delivery_session_lock(j.workspace_id,(b->>'business_id')::uuid,session,0); ELSE PERFORM platform.portfolio_session_lock(j.workspace_id,(b->>'business_id')::uuid,session,0); END IF;
            IF NOT EXISTS(SELECT 1 FROM platform.portfolio_ai_sessions WHERE id=session AND conversation_id=(b->>'conversation_id')::uuid AND client_id=(b->>'client_id')::uuid AND profile_id=CASE WHEN cfg->>'prompt_revision'='conversation_v7' THEN 'SYNTHETIC_INTAKE_V1' WHEN cfg->>'prompt_revision'='conversation_v6' THEN 'SYNTHETIC_PORTFOLIO_PHOTO_V1' ELSE 'SYNTHETIC_VISION_PORTFOLIO_V1' END) THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
            portfolio:=platform.portfolio_availability(j.workspace_id,(b->>'business_id')::uuid,(knowledge->'knowledge_pin'->>'release_id')::uuid,(knowledge->'knowledge_pin'->>'activation_version')::bigint);
            media:=platform.portfolio_media_pin(j.workspace_id,(b->>'business_id')::uuid,(b->>'client_id')::uuid,(b->>'conversation_id')::uuid,true);
            auxiliary:=platform.portfolio_auxiliary_cost(j.workspace_id,(b->>'business_id')::uuid,(b->>'client_id')::uuid,(b->>'conversation_id')::uuid,media,NULL);
            IF auxiliary>(cfg->'limits'->>'cost_budget')::numeric THEN RAISE EXCEPTION 'AI_BUDGET' USING ERRCODE='P2001'; END IF;
          END IF;
          INSERT INTO platform.ai_runs(workspace_id,job_id,connection_id,conversation_id,client_id,business_id,turn_id,turn_revision,
            resume_receipt_id,control_generation,binding,snapshot,snapshot_digest,storage_fingerprint,config,config_fingerprint,deadline,knowledge_pin,active_projection,search_pin,portfolio_pin,media_pin,portfolio_session_id,cost_reserved)
          VALUES(j.workspace_id,j.id,j.connection_id,(b->>'conversation_id')::uuid,(b->>'client_id')::uuid,(b->>'business_id')::uuid,j.turn_id,j.turn_revision,
            (b->>'resume_receipt_id')::uuid,(b->>'control_generation')::bigint,b,fresh->'snapshot',b->>'snapshot_digest',encode(sha256(convert_to((fresh->'snapshot')::text,'UTF8')),'hex'),cfg,encode(sha256(convert_to(cfg::text,'UTF8')),'hex'),expiry,knowledge->'knowledge_pin',knowledge->'active_projection',search,portfolio,media,session,auxiliary) RETURNING * INTO r;
          IF cfg->>'prompt_revision'='conversation_v7' THEN UPDATE platform.ai_runs SET intake_pin=platform.intake_runtime_pin(r.workspace_id,r.business_id,r.conversation_id,r.client_id) WHERE workspace_id=r.workspace_id AND id=r.id RETURNING * INTO r; END IF;
          RETURN platform.ai_runtime_view(r);
        END IF;
        IF r.id IS NULL OR p->>'run_id' IS DISTINCT FROM r.id::text THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
        IF p_op='COMPLETE' THEN
          IF NOT platform.material_object(p,ARRAY['run_id','sequence','completion']) OR platform.ai_runtime_completion_valid(p->'completion') IS NOT TRUE THEN
            RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
          SELECT * INTO previous FROM platform.ai_provider_calls WHERE workspace_id=j.workspace_id AND run_id=r.id AND sequence=(p->>'sequence')::int FOR UPDATE;
          IF previous.claim_hash IS DISTINCT FROM sha256(convert_to(p_claim::text,'UTF8')) OR previous.attempt_count IS DISTINCT FROM j.attempt_count THEN
            RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
          IF previous.completed_at IS NOT NULL THEN
            IF previous.completion IS DISTINCT FROM p->'completion' THEN RAISE EXCEPTION 'IDEMPOTENCY_KEY_CONFLICT' USING ERRCODE='P2001'; END IF;
          ELSE
            UPDATE platform.ai_provider_calls SET completion=p->'completion',completed_at=clock_timestamp()
              WHERE workspace_id=j.workspace_id AND run_id=r.id AND sequence=previous.sequence;
          END IF;
          RETURN jsonb_build_object('recorded',true);
        END IF;
        fresh:=platform.ai_runtime_current(j,r.snapshot);
        IF fresh->'binding' IS DISTINCT FROM r.binding OR platform.ai_knowledge_current(r) IS NOT TRUE OR platform.knowledge_runtime_current(r) IS NOT TRUE THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
        IF r.deadline<=clock_timestamp() OR r.result IS NOT NULL THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
        IF r.config->'route'->>'execution'='PROVIDER' THEN
          PERFORM platform.ai_provider_guard((SELECT provider_session_id FROM platform.ai_deliveries WHERE job_id=j.id),j,r.config);
        END IF;
        IF r.config->>'prompt_revision' IN ('conversation_v4','conversation_v5','conversation_v6','conversation_v7') AND r.search_refs IS NULL THEN RAISE EXCEPTION 'AI_INCOMPLETE' USING ERRCODE='P2001'; END IF;
        lim:=r.config->'limits';
        SELECT * INTO previous FROM platform.ai_provider_calls WHERE workspace_id=j.workspace_id AND run_id=r.id AND sequence=r.calls_used;
        IF p_op='DELIVERY_READ' THEN RETURN platform.portfolio_delivery_attest(j,r,p); END IF;
        IF p_op IN ('AUTHORIZE','READ') THEN
          IF p->'binding' IS DISTINCT FROM r.binding OR p->'knowledge_pin' IS DISTINCT FROM r.knowledge_pin OR (r.config->>'prompt_revision' IN ('conversation_v4','conversation_v5','conversation_v6','conversation_v7') AND p->'search_pin' IS DISTINCT FROM r.search_pin) OR (r.config->>'prompt_revision' IN ('conversation_v5','conversation_v6','conversation_v7') AND (p->'portfolio_pin' IS DISTINCT FROM r.portfolio_pin OR p->'media_pin' IS DISTINCT FROM r.media_pin)) THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
          IF (p_op='AUTHORIZE' AND (NOT platform.material_object(p,ARRAY['run_id','binding','knowledge_pin','boundary']||CASE WHEN r.config->>'prompt_revision' IN ('conversation_v4','conversation_v5','conversation_v6','conversation_v7') THEN ARRAY['search_pin']||CASE WHEN r.config->>'prompt_revision' IN ('conversation_v5','conversation_v6','conversation_v7') THEN ARRAY['portfolio_pin','media_pin'] ELSE ARRAY[]::text[] END ELSE ARRAY[]::text[] END) OR p->>'boundary' NOT IN ('MODEL','READ','FOLLOWUP','CANDIDATE')))
            OR (p_op='READ' AND NOT platform.material_object(p,ARRAY['run_id','binding','knowledge_pin']||CASE WHEN r.config->>'prompt_revision' IN ('conversation_v4','conversation_v5','conversation_v6','conversation_v7') THEN ARRAY['search_pin']||CASE WHEN r.config->>'prompt_revision' IN ('conversation_v5','conversation_v6','conversation_v7') THEN ARRAY['portfolio_pin','media_pin'] ELSE ARRAY[]::text[] END ELSE ARRAY[]::text[] END)) THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
          IF p->>'boundary'='MODEL' AND r.calls_used<>0 THEN RAISE EXCEPTION 'AI_INCOMPLETE' USING ERRCODE='P2001'; END IF;
          IF p_op='READ' OR p->>'boundary' IN ('READ','FOLLOWUP') THEN
            IF r.calls_used<>1 OR previous.completed_at IS NULL OR previous.completion->>'kind'<>'TOOLS'
              OR (lim->>'read_executions')::int<1 THEN RAISE EXCEPTION 'AI_BUDGET' USING ERRCODE='P2001'; END IF;
            IF (p_op='READ' OR p->>'boundary'='READ') AND r.reads_used<>0 OR p->>'boundary'='FOLLOWUP' AND r.reads_used<>1 THEN
              RAISE EXCEPTION 'AI_BUDGET' USING ERRCODE='P2001'; END IF;
          END IF;
          IF p->>'boundary'='CANDIDATE' AND (r.calls_used=0 OR previous.completed_at IS NULL OR previous.completion->>'kind'<>'OUTPUT') THEN
            RAISE EXCEPTION 'AI_INCOMPLETE' USING ERRCODE='P2001'; END IF;
          IF p_op='READ' THEN
            UPDATE platform.ai_runs SET reads_used=1,read_audit=jsonb_build_object('outcome','READ','context_version',r.binding->'context_version',
              'turn_revision',r.turn_revision,'native',r.binding->'native','knowledge_pin',r.knowledge_pin,'at',clock_timestamp())||CASE WHEN r.search_pin IS NOT NULL THEN jsonb_build_object('search_pin_sha256',encode(sha256(convert_to(r.search_pin::text,'UTF8')),'hex')) ELSE '{}'::jsonb END WHERE workspace_id=j.workspace_id AND id=r.id;
            RETURN jsonb_build_object('binding',r.binding,'snapshot',r.snapshot,
              'knowledge_pin',r.knowledge_pin,'active_projection',r.active_projection)||CASE WHEN r.config->>'prompt_revision'='conversation_v7' THEN jsonb_build_object('intake',platform.intake_project(r.workspace_id,r.business_id,r.conversation_id,r.client_id)) ELSE '{}'::jsonb END
              ||CASE WHEN r.search_pin IS NOT NULL THEN jsonb_build_object('search_pin',r.search_pin,'search_refs',r.search_refs,'search_projection',platform.knowledge_projection(r)) ELSE '{}'::jsonb END||platform.portfolio_runtime_data(r)||CASE WHEN r.config->>'prompt_revision' IN ('conversation_v6','conversation_v7') THEN jsonb_build_object('delivery_eligible',platform.portfolio_delivery_eligible(r)) ELSE '{}'::jsonb END||CASE WHEN r.config->>'prompt_revision' IN ('conversation_v5','conversation_v6','conversation_v7') THEN jsonb_build_object('portfolio_projection',platform.portfolio_projection(r)) ELSE '{}'::jsonb END;
          END IF;
          RETURN jsonb_build_object('allowed',true);
        ELSIF p_op='RESERVE' THEN
          b:=p->'budget'; n:=r.calls_used+1;
          IF NOT platform.material_object(p,ARRAY['run_id','budget']) OR NOT platform.material_object(b,ARRAY['calls_used','reads_reserved','tokens_reserved','cost_reserved','currency'])
            OR jsonb_typeof(b->'calls_used')<>'number' OR jsonb_typeof(b->'reads_reserved')<>'number' OR jsonb_typeof(b->'tokens_reserved')<>'number' THEN
            RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
          tokens:=(b->>'tokens_reserved')::int; cost:=(b->>'cost_reserved')::numeric;
          IF n>2 OR n>(lim->>'model_calls')::int OR (b->>'calls_used')::int<>n OR (b->>'reads_reserved')::int<>r.reads_used
            OR b->>'currency' IS DISTINCT FROM lim->>'currency' OR tokens<=r.tokens_reserved OR tokens>(lim->>'total_tokens')::int
            OR tokens-r.tokens_reserved>(lim->>'input_tokens')::int+(lim->>'output_tokens')::int
            OR cost<>r.cost_reserved+(lim->>'call_cost_reservation')::numeric OR cost>(lim->>'cost_budget')::numeric
            OR (n=2 AND (r.reads_used<>1 OR previous.completed_at IS NULL OR previous.completion->>'kind'<>'TOOLS')) THEN
            RAISE EXCEPTION 'AI_BUDGET' USING ERRCODE='P2001'; END IF;
          IF r.config->'route'->>'execution'='PROVIDER' AND EXISTS(
            SELECT 1 FROM platform.ai_provider_sessions s WHERE s.id=(SELECT provider_session_id FROM platform.ai_deliveries WHERE job_id=j.id) AND
            (EXISTS(SELECT 1 FROM platform.ai_provider_calls pc JOIN platform.ai_runs ar ON (ar.workspace_id,ar.id)=(pc.workspace_id,pc.run_id)
              JOIN platform.ai_deliveries d ON (d.workspace_id,d.job_id)=(ar.workspace_id,ar.job_id)
              WHERE d.provider_session_id=s.id AND (pc.completed_at IS NULL OR pc.completion->>'kind'='UNKNOWN'
                OR pc.completion->'cost'->>'status'='UNKNOWN'
                OR (pc.completion->'cost'->>'amount')::numeric>(ar.config->'limits'->>'call_cost_reservation')::numeric))
            OR (SELECT count(*) FROM platform.ai_provider_calls pc JOIN platform.ai_deliveries d ON (d.workspace_id,d.job_id)=(pc.workspace_id,(SELECT job_id FROM platform.ai_runs WHERE workspace_id=pc.workspace_id AND id=pc.run_id)) WHERE d.provider_session_id=s.id)>=s.max_calls
            OR (SELECT coalesce(sum(greatest((ar.config->'limits'->>'call_cost_reservation')::numeric,coalesce((pc.completion->'cost'->>'amount')::numeric,0))),0)
              FROM platform.ai_provider_calls pc JOIN platform.ai_runs ar ON (ar.workspace_id,ar.id)=(pc.workspace_id,pc.run_id)
              JOIN platform.ai_deliveries d ON (d.workspace_id,d.job_id)=(ar.workspace_id,ar.job_id) WHERE d.provider_session_id=s.id)
              +(lim->>'call_cost_reservation')::numeric>s.max_rub)) THEN
            RAISE EXCEPTION 'AI_BUDGET' USING ERRCODE='P2001'; END IF;
          IF r.config->>'prompt_revision' IN ('conversation_v5','conversation_v6','conversation_v7') THEN
            auxiliary:=platform.portfolio_auxiliary_cost(r.workspace_id,r.business_id,r.client_id,r.conversation_id,r.media_pin,r.id);
            SELECT auxiliary+coalesce(sum(greatest((lim->>'call_cost_reservation')::numeric,
              coalesce((pc.completion->'cost'->>'amount')::numeric,(lim->>'call_cost_reservation')::numeric))),0)
              +(lim->>'call_cost_reservation')::numeric INTO auxiliary
              FROM platform.ai_provider_calls pc WHERE pc.workspace_id=r.workspace_id AND pc.run_id=r.id;
            IF greatest(cost,auxiliary)>(lim->>'cost_budget')::numeric THEN RAISE EXCEPTION 'AI_BUDGET' USING ERRCODE='P2001'; END IF;
            IF r.config->>'prompt_revision' IN ('conversation_v6','conversation_v7') THEN PERFORM platform.intake_delivery_session_lock(r.workspace_id,r.business_id,r.portfolio_session_id,(lim->>'call_cost_reservation')::numeric); ELSE PERFORM platform.portfolio_session_lock(r.workspace_id,r.business_id,r.portfolio_session_id,(lim->>'call_cost_reservation')::numeric); END IF;
            cost:=greatest(cost,auxiliary);
          END IF;
          INSERT INTO platform.ai_provider_calls(workspace_id,run_id,sequence,claim_hash,attempt_count,budget,portfolio_session_id)
            VALUES(j.workspace_id,r.id,n,sha256(convert_to(p_claim::text,'UTF8')),j.attempt_count,b,r.portfolio_session_id);
          UPDATE platform.ai_runs SET calls_used=n,tokens_reserved=tokens,cost_reserved=cost WHERE workspace_id=j.workspace_id AND id=r.id;
          RETURN jsonb_build_object('sequence',n);
        ELSIF p_op='COMMIT' THEN
          IF NOT platform.material_object(p,ARRAY['run_id','result']) OR (CASE WHEN r.config->>'prompt_revision'='conversation_v7' THEN platform.intake_result_valid(p->'result') WHEN r.config->>'prompt_revision'='conversation_v6' THEN platform.portfolio_delivery_result_valid(p->'result') ELSE platform.ai_runtime_result_valid(p->'result') END) IS NOT TRUE THEN
            RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
          IF r.calls_used=0 OR previous.completed_at IS NULL OR previous.completion->>'kind'<>'OUTPUT' THEN RAISE EXCEPTION 'AI_INCOMPLETE' USING ERRCODE='P2001'; END IF;
          PERFORM platform.messaging_guard(p_job,p_claim);
          PERFORM platform.intake_apply(r,p->'result'->'intake');
          UPDATE platform.ai_runs SET intake_pin=CASE WHEN r.config->>'prompt_revision'='conversation_v7' THEN platform.intake_runtime_pin(r.workspace_id,r.business_id,r.conversation_id,r.client_id) ELSE NULL END,result=p->'result',selected_at=clock_timestamp(),winning_claim_hash=sha256(convert_to(p_claim::text,'UTF8'))
            WHERE workspace_id=j.workspace_id AND id=r.id AND result IS NULL RETURNING * INTO r;
          PERFORM platform.ai_delivery_select(j,r);
          UPDATE platform.messaging_jobs SET status='SUCCEEDED',turn_outcome='OBSERVED',error_code=NULL,claim_token=NULL,lease_until=NULL,
            worker_id=NULL,completed_at=clock_timestamp(),version=version+1 WHERE id=j.id;
          RETURN platform.ai_runtime_receipt(r);
        END IF;
        RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001';
      EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range OR invalid_datetime_format OR datetime_field_overflow THEN
        RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001';
      END $$""",
    "platform.ai_delivery_select": r"""CREATE OR REPLACE FUNCTION platform.ai_delivery_select(j platform.messaging_jobs,r platform.ai_runs) RETURNS void
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE d platform.ai_deliveries%ROWTYPE; c app.conversations%ROWTYPE; conn app.channel_connections%ROWTYPE;
        msg uuid; box uuid; send uuid; intent_context bigint; e jsonb; ref jsonb; v platform.portfolio_asset_versions%ROWTYPE;
      BEGIN
        SELECT * INTO d FROM platform.ai_deliveries WHERE workspace_id=j.workspace_id AND job_id=j.id FOR UPDATE;
        IF NOT FOUND THEN RETURN; END IF; -- historical DB-only run: no retroactive intent
        IF d.selected_kind IS NOT NULL OR r.result IS NULL OR r.winning_claim_hash IS DISTINCT FROM sha256(convert_to(j.claim_token::text,'UTF8')) THEN
          RAISE EXCEPTION 'IDEMPOTENCY_KEY_CONFLICT' USING ERRCODE='P2001'; END IF;
        PERFORM platform.ai_runtime_current(j,r.snapshot);
        IF platform.ai_knowledge_current(r) IS NOT TRUE OR platform.knowledge_runtime_current(r) IS NOT TRUE THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
        SELECT * INTO STRICT c FROM app.conversations WHERE workspace_id=j.workspace_id AND id=r.conversation_id;
        SELECT * INTO STRICT conn FROM app.channel_connections WHERE workspace_id=j.workspace_id AND id=j.connection_id;
        PERFORM platform.intake_delivery_guard(r);
        IF r.result->>'kind'='reply' THEN
          IF conn.provider='TELEGRAM' AND platform.telegram_can_send(j.workspace_id,j.connection_id,c.id,false) IS NOT TRUE THEN
            RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
          INSERT INTO app.messages(workspace_id,conversation_id,connection_id,provider_chat_id,direction,content_type,text,occurred_at)
            VALUES(j.workspace_id,c.id,j.connection_id,c.provider_chat_id,'OUTBOUND','TEXT',r.result->>'text',clock_timestamp()) RETURNING id INTO msg;
          SELECT version INTO STRICT intent_context FROM app.conversations WHERE workspace_id=j.workspace_id AND id=c.id;
          IF intent_context::numeric<>(r.binding->>'context_version')::numeric+1 THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
          INSERT INTO app.outbox_events(workspace_id,connection_id,message_id,kind)
            VALUES(j.workspace_id,j.connection_id,msg,'SEND_AI_TEXT') RETURNING id INTO box;
          INSERT INTO platform.messaging_jobs(workspace_id,connection_id,kind,outbox_id,correlation_id)
            VALUES(j.workspace_id,j.connection_id,'SEND_AI_TEXT',box,j.correlation_id) RETURNING id INTO send;
        ELSIF r.result->>'kind'='portfolio_photo' THEN
          ref:=r.result->'selection';
          IF r.config->>'prompt_revision' NOT IN ('conversation_v6','conversation_v7') OR r.config->>'schema_revision'<>(CASE WHEN r.config->>'prompt_revision'='conversation_v7' THEN 'conversation_result_v3' ELSE 'conversation_result_v2' END)
            OR d.provider_session_id IS NOT NULL OR r.reads_used<>1 OR r.calls_used<>2
            OR r.delivery_read_audit IS NULL OR NOT (r.delivery_read_audit->'shown_refs') @> jsonb_build_array(ref)
            OR platform.portfolio_delivery_result_valid(r.result-'intake') IS NOT TRUE OR platform.portfolio_runtime_current(r) IS NOT TRUE
            OR platform.portfolio_delivery_source(r,ref) IS NOT TRUE THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
          IF conn.provider='TELEGRAM' AND platform.telegram_can_send(j.workspace_id,j.connection_id,c.id,false) IS NOT TRUE THEN
            RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
          SELECT * INTO STRICT v FROM platform.portfolio_asset_versions WHERE workspace_id=r.workspace_id AND business_id=r.business_id AND id=(ref->>'asset_version_id')::uuid;
          INSERT INTO app.messages(workspace_id,conversation_id,connection_id,provider_chat_id,direction,content_type,text,occurred_at)
            VALUES(j.workspace_id,c.id,j.connection_id,c.provider_chat_id,'OUTBOUND','PORTFOLIO_PHOTO',r.result->>'caption',clock_timestamp()) RETURNING id INTO msg;
          SELECT version INTO STRICT intent_context FROM app.conversations WHERE workspace_id=j.workspace_id AND id=c.id;
          IF intent_context::numeric<>(r.binding->>'context_version')::numeric+1 THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
          INSERT INTO app.outbox_events(workspace_id,connection_id,message_id,kind) VALUES(j.workspace_id,j.connection_id,msg,'SEND_AI_PHOTO') RETURNING id INTO box;
          INSERT INTO platform.messaging_jobs(workspace_id,connection_id,kind,outbox_id,correlation_id) VALUES(j.workspace_id,j.connection_id,'SEND_AI_PHOTO',box,j.correlation_id) RETURNING id INTO send;
          INSERT INTO platform.portfolio_delivery_intents(workspace_id,business_id,run_id,conversation_id,client_id,connection_id,message_id,outbox_id,send_job_id,item_id,revision_id,asset_id,asset_version_id,source_sha256,caption,request_fingerprint,context_sha256)
          VALUES(r.workspace_id,r.business_id,r.id,r.conversation_id,r.client_id,r.connection_id,msg,box,send,(ref->>'item_id')::uuid,(ref->>'revision_id')::uuid,v.asset_id,v.id,v.sha256,r.result->>'caption',
            encode(sha256(convert_to(E'asm:m5:portfolio_delivery:v1\n'||r.id::text||E'\n'||r.result::text,'UTF8')),'hex'),r.delivery_read_audit->>'context_sha256');
        ELSIF r.result->>'kind'='handoff' THEN
          e:=platform.escalation_request_for_turn(j.id,j.claim_token);
          IF e->>'code' IS DISTINCT FROM 'ESCALATED' THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
          IF r.config->>'prompt_revision'='conversation_v7' THEN INSERT INTO platform.intake_escalation_links(workspace_id,escalation_id,business_id,conversation_id,client_id,pin,summary) VALUES(r.workspace_id,(e->>'escalation_id')::uuid,r.business_id,r.conversation_id,r.client_id,platform.intake_runtime_pin(r.workspace_id,r.business_id,r.conversation_id,r.client_id),(platform.intake_project(r.workspace_id,r.business_id,r.conversation_id,r.client_id)-'sources')||jsonb_build_object('sources','[]'::jsonb)); END IF;
        END IF;
        IF j.lease_until<=clock_timestamp() THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
        UPDATE platform.ai_deliveries SET knowledge_pin=r.knowledge_pin,search_pin=r.search_pin,portfolio_pin=r.portfolio_pin,media_pin=r.media_pin,run_id=r.id,selected_kind=r.result->>'kind',message_id=msg,outbox_id=box,send_job_id=send,
          intent_context_version=intent_context,escalation_id=(e->>'escalation_id')::uuid WHERE workspace_id=j.workspace_id AND job_id=j.id;
      END $$""",
    "platform.ai_reply_rights_commit": r"""CREATE OR REPLACE FUNCTION platform.ai_reply_rights_commit(p_job uuid,p_claim uuid,p_run uuid,p_generation bigint,p_version bigint,p_observation jsonb,p_result jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE j platform.messaging_jobs%ROWTYPE; r platform.ai_runs%ROWTYPE; conn app.channel_connections%ROWTYPE; s platform.telegram_connection_state%ROWTYPE; observed jsonb;
BEGIN
  r:=platform.ai_reply_rights_current(p_job,p_claim,p_run);
  j:=platform.messaging_guard(p_job,p_claim);
  IF (CASE WHEN r.config->>'prompt_revision'='conversation_v7' THEN platform.intake_result_valid(p_result) WHEN r.config->>'prompt_revision'='conversation_v6' THEN platform.portfolio_delivery_result_valid(p_result) ELSE platform.ai_runtime_result_valid(p_result) END) IS NOT TRUE OR p_result->>'kind' NOT IN ('reply','portfolio_photo') THEN
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
    "platform.knowledge_runtime_current": r"""CREATE OR REPLACE FUNCTION platform.knowledge_runtime_current(r platform.ai_runs) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE j platform.messaging_jobs%ROWTYPE; state platform.business_configuration_state%ROWTYPE;
BEGIN
  IF r.config->>'prompt_revision' NOT IN ('conversation_v4','conversation_v5','conversation_v6','conversation_v7') THEN RETURN true; END IF;
  j:=platform.messaging_guard(nullif(current_setting('asm.job_id',true),'')::uuid,nullif(current_setting('asm.claim_token',true),'')::uuid);
  IF j.workspace_id<>r.workspace_id OR j.connection_id<>r.connection_id THEN RETURN false; END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(r.workspace_id::text||':'||r.business_id::text||'|CONFIGURATION_V1',2018));
  SELECT * INTO state FROM platform.business_configuration_state WHERE workspace_id=r.workspace_id AND business_id=r.business_id;
  RETURN r.search_pin IS NOT NULL AND r.search_pin=platform.knowledge_availability(r.workspace_id,r.business_id,state.active_release_id,coalesce(state.activation_version,0)) AND platform.portfolio_runtime_current(r) AND platform.intake_current(r);
END $$""",
    "platform.portfolio_runtime_current": r"""CREATE OR REPLACE FUNCTION platform.portfolio_runtime_current(r platform.ai_runs) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE state platform.business_configuration_state%ROWTYPE;
BEGIN
 IF r.config->>'prompt_revision' NOT IN ('conversation_v5','conversation_v6','conversation_v7') THEN RETURN true; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended(r.workspace_id::text||':'||r.business_id::text||'|CONFIGURATION_V1',2018));
 SELECT * INTO state FROM platform.business_configuration_state WHERE workspace_id=r.workspace_id AND business_id=r.business_id;
 RETURN r.portfolio_pin IS NOT NULL AND r.media_pin IS NOT NULL
  AND r.portfolio_pin=platform.portfolio_availability(r.workspace_id,r.business_id,state.active_release_id,coalesce(state.activation_version,0))
  AND r.media_pin=platform.portfolio_media_pin(r.workspace_id,r.business_id,r.client_id,r.conversation_id,true)
  AND EXISTS(SELECT 1 FROM platform.portfolio_ai_sessions s
   JOIN platform.workspaces w ON w.id=s.workspace_id
   JOIN platform.workspace_memberships wm ON wm.workspace_id=s.workspace_id AND wm.user_account_id=s.actor_user_account_id
   JOIN platform.user_accounts ua ON ua.id=wm.user_account_id
   WHERE s.workspace_id=r.workspace_id AND s.business_id=r.business_id AND s.id=r.portfolio_session_id
    AND s.profile_id=CASE WHEN r.config->>'prompt_revision'='conversation_v7' THEN 'SYNTHETIC_INTAKE_V1' WHEN r.config->>'prompt_revision'='conversation_v6' THEN 'SYNTHETIC_PORTFOLIO_PHOTO_V1' ELSE 'SYNTHETIC_VISION_PORTFOLIO_V1' END
    AND s.conversation_id=r.conversation_id AND s.client_id=r.client_id AND s.revoked_at IS NULL AND s.expires_at>clock_timestamp()
    AND w.status='ACTIVE' AND ua.status='ACTIVE' AND wm.role='OWNER' AND wm.status='ACTIVE');
END $$""",
    "platform.portfolio_runtime_data": r"""CREATE OR REPLACE FUNCTION platform.portfolio_runtime_data(r platform.ai_runs) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE a platform.vision_analyses%ROWTYPE;
BEGIN
 IF r.config->>'prompt_revision' NOT IN ('conversation_v5','conversation_v6','conversation_v7') THEN RETURN '{}'::jsonb; END IF;
 SELECT * INTO a FROM platform.vision_analyses WHERE workspace_id=r.workspace_id AND business_id=r.business_id AND id=(r.media_pin->>'analysis_id')::uuid AND conversation_id=r.conversation_id AND client_id=r.client_id;
 RETURN jsonb_build_object('portfolio_pin',r.portfolio_pin,'media_pin',r.media_pin,'portfolio_refs',r.portfolio_refs,'portfolio_session_id',r.portfolio_session_id,'search_query',platform.portfolio_run_query(r),'vision_analysis',platform.portfolio_analysis_view(a));
END $$""",
    "platform.portfolio_query_reserve": r"""CREATE OR REPLACE FUNCTION platform.portfolio_query_reserve(p_job uuid,p_claim uuid,p_run uuid,p_pin jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE j platform.messaging_jobs%ROWTYPE; r platform.ai_runs%ROWTYPE; ec platform.knowledge_embedding_calls%ROWTYPE; fresh jsonb; query text; wire text; empty jsonb;
 ticket uuid:=gen_random_uuid(); s platform.portfolio_ai_sessions%ROWTYPE; moment timestamptz:=clock_timestamp();
BEGIN
 PERFORM platform.turn_require_isolation();j:=platform.messaging_guard(p_job,p_claim);
 SELECT * INTO r FROM platform.ai_runs WHERE workspace_id=j.workspace_id AND job_id=j.id AND id=p_run FOR UPDATE;
 IF r.id IS NULL OR r.config->>'prompt_revision' NOT IN ('conversation_v5','conversation_v6','conversation_v7') OR r.calls_used<>0 OR r.result IS NOT NULL OR r.deadline<=moment THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
 fresh:=platform.ai_runtime_current(j,r.snapshot);
 IF fresh->'binding' IS DISTINCT FROM r.binding OR platform.ai_knowledge_current(r) IS NOT TRUE OR platform.knowledge_runtime_current(r) IS NOT TRUE OR platform.portfolio_runtime_current(r) IS NOT TRUE
  OR p_pin IS DISTINCT FROM jsonb_build_object('search_pin',r.search_pin,'portfolio_pin',r.portfolio_pin,'media_pin',r.media_pin) THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
 SELECT * INTO ec FROM platform.knowledge_embedding_calls WHERE workspace_id=r.workspace_id AND run_id=r.id;
 IF FOUND THEN RETURN jsonb_build_object('status','REPLAY','call_id',ec.id,'ticket',NULL,'wire',NULL,'wire_sha256',ec.request_sha256,'profile_id',ec.profile_id,'deadline',ec.deadline,'reserved_cost','0.08','currency','RUB'); END IF;
 query:=platform.portfolio_run_query(r);
 IF r.search_refs IS NOT NULL OR query='' OR NOT EXISTS(SELECT 1 FROM platform.knowledge_build_chunks WHERE workspace_id=r.workspace_id AND business_id=r.business_id AND build_id=(r.search_pin->>'build_id')::uuid AND embedding IS NOT NULL)
  AND NOT EXISTS(SELECT 1 FROM platform.portfolio_build_items WHERE workspace_id=r.workspace_id AND business_id=r.business_id AND build_id=(r.portfolio_pin->>'build_id')::uuid AND embedding IS NOT NULL) THEN
  IF r.search_refs IS NULL THEN
   empty:=jsonb_build_object('revision','business_knowledge_search_result_v1','profile_id','polza_openai_text_embedding3small_1536_cosine_v1','query_sha256',encode(sha256(convert_to(query,'UTF8')),'hex'),'status','EMPTY','reason_code',CASE WHEN query='' THEN 'NO_QUERY' ELSE 'NO_ELIGIBLE_SOURCE' END,'references','[]'::jsonb,'conflicts','[]'::jsonb);
   UPDATE platform.ai_runs SET search_refs=empty,portfolio_refs=platform.portfolio_refs(platform.portfolio_select(r.workspace_id,r.business_id,r.portfolio_pin,NULL,query)) WHERE workspace_id=r.workspace_id AND id=r.id;
  END IF;
  RETURN jsonb_build_object('status','REPLAY','call_id',NULL,'ticket',NULL,'wire',NULL,'wire_sha256',NULL,'profile_id','polza_openai_text_embedding3small_1536_cosine_v1','deadline',NULL,'reserved_cost','0.00','currency','RUB');
 END IF;
 wire:=platform.portfolio_embedding_wire(jsonb_build_array(query));
 IF octet_length(wire)>8192 THEN RAISE EXCEPTION 'WIRE_LIMIT' USING ERRCODE='P2901'; END IF;
 IF r.config->>'prompt_revision'='conversation_v7' THEN
  s:=platform.intake_delivery_session_lock(r.workspace_id,r.business_id,r.portfolio_session_id,0.08);
  IF s.profile_id IS DISTINCT FROM 'SYNTHETIC_INTAKE_V1' THEN RAISE EXCEPTION 'SESSION_NOT_ALLOWED' USING ERRCODE='P2901'; END IF;
 ELSIF r.config->>'prompt_revision'='conversation_v6' THEN
  s:=platform.portfolio_delivery_session_lock(r.workspace_id,r.business_id,r.portfolio_session_id,0.08);
 ELSE
  s:=platform.portfolio_session_lock(r.workspace_id,r.business_id,r.portfolio_session_id,0.08);
 END IF;
 IF s.conversation_id IS DISTINCT FROM r.conversation_id OR s.client_id IS DISTINCT FROM r.client_id THEN RAISE EXCEPTION 'SESSION_NOT_ALLOWED' USING ERRCODE='P2901'; END IF;
 IF greatest(r.cost_reserved,platform.portfolio_auxiliary_cost(r.workspace_id,r.business_id,r.client_id,r.conversation_id,r.media_pin,r.id))+0.08>(r.config->'limits'->>'cost_budget')::numeric THEN RAISE EXCEPTION 'BUDGET_EXHAUSTED' USING ERRCODE='P2901'; END IF;
 INSERT INTO platform.knowledge_embedding_calls(workspace_id,business_id,kind,run_id,claim_hash,profile_id,request_sha256,request_bytes,input_count,token_ceiling,ticket_hash,state,reserved_at,deadline,portfolio_session_id)
 VALUES(r.workspace_id,r.business_id,'QUERY',r.id,sha256(convert_to(p_claim::text,'UTF8')),'polza_openai_text_embedding3small_1536_cosine_v1',encode(sha256(convert_to(wire,'UTF8')),'hex'),octet_length(wire),1,octet_length(query),sha256(convert_to(ticket::text,'UTF8')),'RESERVED',moment,least(moment+interval '10 seconds',r.deadline,s.expires_at),s.id) RETURNING * INTO ec;
 UPDATE platform.ai_runs SET cost_reserved=greatest(r.cost_reserved,platform.portfolio_auxiliary_cost(r.workspace_id,r.business_id,r.client_id,r.conversation_id,r.media_pin,r.id)) WHERE workspace_id=r.workspace_id AND id=r.id;
 RETURN jsonb_build_object('status','RESERVED','call_id',ec.id,'ticket',ticket,'wire',wire,'wire_sha256',ec.request_sha256,'profile_id',ec.profile_id,'deadline',ec.deadline,'reserved_cost','0.08','currency','RUB');
END $$""",
    "platform.portfolio_query_apply": r"""CREATE OR REPLACE FUNCTION platform.portfolio_query_apply(p_job uuid,p_claim uuid,p_run uuid,p_call uuid,p_ticket uuid,vectors jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE j platform.messaging_jobs%ROWTYPE; r platform.ai_runs%ROWTYPE; ec platform.knowledge_embedding_calls%ROWTYPE; fresh jsonb; query text; wire text; refs jsonb; portfolio jsonb;
BEGIN
 PERFORM platform.turn_require_isolation();j:=platform.messaging_guard(p_job,p_claim);
 SELECT * INTO r FROM platform.ai_runs WHERE workspace_id=j.workspace_id AND job_id=j.id AND id=p_run FOR UPDATE;
 PERFORM pg_advisory_xact_lock(hashtextextended(j.workspace_id::text||':'||r.business_id::text||'|CONFIGURATION_V1',2018));
 SELECT * INTO ec FROM platform.knowledge_embedding_calls WHERE workspace_id=j.workspace_id AND run_id=p_run AND id=p_call FOR UPDATE;
 IF r.id IS NULL OR r.config->>'prompt_revision' NOT IN ('conversation_v5','conversation_v6','conversation_v7') OR ec.id IS NULL OR ec.kind<>'QUERY' OR ec.state<>'SUCCESS' OR r.calls_used<>0 OR r.result IS NOT NULL OR r.deadline<=clock_timestamp()
  OR p_ticket IS NULL OR ec.ticket_hash IS DISTINCT FROM sha256(convert_to(p_ticket::text,'UTF8')) OR ec.claim_hash IS DISTINCT FROM sha256(convert_to(p_claim::text,'UTF8')) OR ec.portfolio_session_id IS DISTINCT FROM r.portfolio_session_id THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
 fresh:=platform.ai_runtime_current(j,r.snapshot);
 IF fresh->'binding' IS DISTINCT FROM r.binding OR platform.ai_knowledge_current(r) IS NOT TRUE OR platform.knowledge_runtime_current(r) IS NOT TRUE OR platform.portfolio_runtime_current(r) IS NOT TRUE THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
 IF ec.applied_at IS NOT NULL THEN RETURN jsonb_build_object('knowledge',platform.knowledge_projection(r),'portfolio',platform.portfolio_projection(r))||platform.portfolio_runtime_data(r)||CASE WHEN r.config->>'prompt_revision' IN ('conversation_v6','conversation_v7') THEN jsonb_build_object('delivery_eligible',platform.portfolio_delivery_eligible(r)) ELSE '{}'::jsonb END; END IF;
 IF ec.reserved_at+interval '30 seconds'<=clock_timestamp() OR platform.knowledge_vectors_valid(vectors,1) IS NOT TRUE OR ec.vectors_sha256 IS DISTINCT FROM encode(sha256(convert_to(vectors::text,'UTF8')),'hex') THEN RAISE EXCEPTION 'INVALID_VECTOR' USING ERRCODE='P2901'; END IF;
 query:=platform.portfolio_run_query(r);wire:=platform.portfolio_embedding_wire(jsonb_build_array(query));
 IF ec.request_sha256<>encode(sha256(convert_to(wire,'UTF8')),'hex') THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
 refs:=platform.knowledge_select(r,(vectors->0)::text::extensions.vector(1536),query);
 portfolio:=platform.portfolio_select(r.workspace_id,r.business_id,r.portfolio_pin,(vectors->0)::text::extensions.vector(1536),query);
 UPDATE platform.ai_runs SET search_refs=refs,portfolio_refs=platform.portfolio_refs(portfolio) WHERE workspace_id=r.workspace_id AND id=r.id RETURNING * INTO r;
 UPDATE platform.knowledge_embedding_calls SET query_vector=(vectors->0)::text::extensions.vector(1536),applied_at=clock_timestamp() WHERE id=ec.id;
 IF platform.portfolio_runtime_current(r) IS NOT TRUE THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
 RETURN jsonb_build_object('knowledge',platform.knowledge_projection(r),'portfolio',platform.portfolio_projection(r))||platform.portfolio_runtime_data(r)||CASE WHEN r.config->>'prompt_revision' IN ('conversation_v6','conversation_v7') THEN jsonb_build_object('delivery_eligible',platform.portfolio_delivery_eligible(r)) ELSE '{}'::jsonb END;
END $$""",
    "platform.portfolio_runtime_read": r"""CREATE OR REPLACE FUNCTION platform.portfolio_runtime_read(p_job uuid,p_claim uuid,p_run uuid,p_pin jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE j platform.messaging_jobs%ROWTYPE; r platform.ai_runs%ROWTYPE; fresh jsonb;
BEGIN
 PERFORM platform.turn_require_isolation();j:=platform.messaging_guard(p_job,p_claim);
 SELECT * INTO r FROM platform.ai_runs WHERE workspace_id=j.workspace_id AND job_id=j.id AND id=p_run FOR UPDATE;
 IF r.id IS NULL OR r.config->>'prompt_revision' NOT IN ('conversation_v5','conversation_v6','conversation_v7') OR r.result IS NOT NULL OR r.deadline<=clock_timestamp() THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
 fresh:=platform.ai_runtime_current(j,r.snapshot);
 IF fresh->'binding' IS DISTINCT FROM r.binding OR platform.ai_knowledge_current(r) IS NOT TRUE OR platform.knowledge_runtime_current(r) IS NOT TRUE OR platform.portfolio_runtime_current(r) IS NOT TRUE
  OR p_pin IS DISTINCT FROM jsonb_build_object('search_pin',r.search_pin,'portfolio_pin',r.portfolio_pin,'media_pin',r.media_pin) THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
 RETURN jsonb_build_object('knowledge',platform.knowledge_projection(r),'portfolio',platform.portfolio_projection(r))||platform.portfolio_runtime_data(r)||CASE WHEN r.config->>'prompt_revision' IN ('conversation_v6','conversation_v7') THEN jsonb_build_object('delivery_eligible',platform.portfolio_delivery_eligible(r)) ELSE '{}'::jsonb END;
END $$""",
    "platform.portfolio_delivery_attest": r"""CREATE OR REPLACE FUNCTION platform.portfolio_delivery_attest(j platform.messaging_jobs,r platform.ai_runs,p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE eligible jsonb; ref jsonb; proof jsonb;
BEGIN
 IF r.config->>'prompt_revision' NOT IN ('conversation_v6','conversation_v7') OR r.reads_used<>1 OR r.calls_used<>1
  OR r.result IS NOT NULL OR r.deadline<=clock_timestamp()
  OR platform.material_object(p,ARRAY['run_id','binding','knowledge_pin','search_pin','portfolio_pin','media_pin','context_sha256','shown_refs']) IS NOT TRUE
  OR p->'binding' IS DISTINCT FROM r.binding OR p->'knowledge_pin' IS DISTINCT FROM r.knowledge_pin
  OR p->'search_pin' IS DISTINCT FROM r.search_pin OR p->'portfolio_pin' IS DISTINCT FROM r.portfolio_pin OR p->'media_pin' IS DISTINCT FROM r.media_pin
  OR jsonb_typeof(p->'context_sha256')<>'string' OR p->>'context_sha256' !~ '^[0-9a-f]{64}$'
  OR jsonb_typeof(p->'shown_refs')<>'array' OR jsonb_array_length(p->'shown_refs')>3
  OR NOT EXISTS(SELECT 1 FROM platform.ai_provider_calls WHERE workspace_id=r.workspace_id AND run_id=r.id AND sequence=1
   AND completed_at IS NOT NULL AND completion->>'kind'='TOOLS' AND claim_hash=sha256(convert_to(j.claim_token::text,'UTF8')) AND attempt_count=j.attempt_count)
 THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
 eligible:=platform.portfolio_delivery_eligible(r);
 IF (SELECT count(DISTINCT v->>'item_id') FROM jsonb_array_elements(p->'shown_refs') x(v))<>jsonb_array_length(p->'shown_refs') THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
 FOR ref IN SELECT v FROM jsonb_array_elements(p->'shown_refs') x(v) LOOP
  IF platform.portfolio_delivery_selection_valid(ref) IS NOT TRUE OR NOT eligible @> jsonb_build_array(ref) THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
 END LOOP;
 proof:=jsonb_build_object('revision','portfolio_delivery_read_v1','context_sha256',p->'context_sha256','shown_refs',p->'shown_refs');
 IF r.delivery_read_audit IS NOT NULL AND r.delivery_read_audit IS DISTINCT FROM proof THEN RAISE EXCEPTION 'IDEMPOTENCY_KEY_CONFLICT' USING ERRCODE='P2001'; END IF;
 IF r.delivery_read_audit IS NULL THEN UPDATE platform.ai_runs SET delivery_read_audit=proof WHERE workspace_id=r.workspace_id AND id=r.id; END IF;
 RETURN jsonb_build_object('recorded',true);
END $$""",
    "platform.portfolio_delivery_intent_current": r"""CREATE OR REPLACE FUNCTION platform.portfolio_delivery_intent_current(j platform.messaging_jobs,d platform.ai_deliveries,r platform.ai_runs,p platform.portfolio_delivery_intents) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
 IF j.kind<>'SEND_AI_PHOTO' OR r.config->>'prompt_revision' NOT IN ('conversation_v6','conversation_v7') OR r.config->>'schema_revision'<>(CASE WHEN r.config->>'prompt_revision'='conversation_v7' THEN 'conversation_result_v3' ELSE 'conversation_result_v2' END)
  OR d.selected_kind<>'portfolio_photo' OR d.provider_session_id IS NOT NULL OR r.result->>'kind'<>'portfolio_photo'
  OR (p.workspace_id,p.business_id,p.run_id,p.conversation_id,p.client_id,p.connection_id,p.message_id,p.outbox_id,p.send_job_id,p.caption,p.context_sha256) IS DISTINCT FROM
     (r.workspace_id,r.business_id,r.id,r.conversation_id,r.client_id,r.connection_id,d.message_id,d.outbox_id,j.id,r.result->>'caption',r.delivery_read_audit->>'context_sha256')
  OR r.result->'selection' IS DISTINCT FROM jsonb_build_object('item_id',p.item_id,'revision_id',p.revision_id,'asset_version_id',p.asset_version_id,'source_sha256',p.source_sha256)
 THEN RETURN false; END IF;
 RETURN platform.ai_delivery_current(j,d,r) AND platform.portfolio_runtime_current(r) AND platform.portfolio_delivery_source(r,r.result->'selection');
EXCEPTION WHEN SQLSTATE 'P2001' THEN
 IF SQLERRM='AI_STALE' THEN RETURN false; END IF;
 RAISE;
END $$""",
    "platform.intake_current": r"""CREATE OR REPLACE FUNCTION platform.intake_current(r platform.ai_runs) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
 IF r.config->>'prompt_revision'<>'conversation_v7' THEN RETURN true; END IF;
 RETURN r.intake_pin=platform.intake_runtime_pin(r.workspace_id,r.business_id,r.conversation_id,r.client_id);
END $$""",
    "platform.intake_apply": r"""CREATE OR REPLACE FUNCTION platform.intake_apply(r platform.ai_runs,p jsonb) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE projection jsonb; service jsonb; sources jsonb; facts jsonb; f jsonb; old jsonb; fact jsonb; source jsonb; pin jsonb; selected_service_id text;
BEGIN
 IF r.config->>'prompt_revision'<>'conversation_v7' THEN RETURN; END IF;
 IF platform.intake_candidates_valid(p) IS NOT TRUE OR platform.intake_current(r) IS NOT TRUE THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
 projection:=platform.intake_project(r.workspace_id,r.business_id,r.conversation_id,r.client_id);
 IF r.search_refs->>'status'='CONFLICT' AND (p->>'category'<>'OTHER_COMPLEX'
  OR p->>'service_id' IS DISTINCT FROM projection->>'service_id'
  OR p->'switch_request' IS DISTINCT FROM 'false'::jsonb OR p->'facts' IS DISTINCT FROM '[]'::jsonb) THEN
  RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
 IF p->>'category'='FAQ_ONLY' THEN RETURN; END IF;
 SELECT x INTO service FROM jsonb_array_elements(r.active_projection->'bundle'->'services') x WHERE x->>'id'=p->>'service_id' AND x->>'active'='true';
 IF p->>'service_id' IS NOT NULL AND service IS NULL OR p->>'service_id' IS NULL AND p->>'category' NOT IN ('AMBIGUOUS','COVER_UP','OTHER_COMPLEX')
  OR p->'facts'<>'[]'::jsonb AND platform.intake_template(service) IS NOT TRUE THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
 IF projection->>'service_id' IS NOT NULL AND p->>'service_id' IS DISTINCT FROM projection->>'service_id' AND p->>'switch_request'<>'true' AND p->>'category'<>'AMBIGUOUS' THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
 selected_service_id:=p->>'service_id';
 facts:=projection->'facts';
 IF p->>'category'='AMBIGUOUS' THEN
  selected_service_id:=projection->>'service_id';
 ELSIF p->>'switch_request'='true' THEN
  IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(p->'facts') x WHERE x->>'status'='client-stated') THEN
   RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001';
  END IF;
  facts:='[]';
 END IF;
 sources:=platform.intake_turn_sources(r.snapshot,projection->'sources');
 FOR f IN SELECT value FROM jsonb_array_elements(p->'facts') LOOP
  SELECT x INTO source FROM jsonb_array_elements(sources) x WHERE x->'message_id'=f->'source'->'message_id' AND x->'source_version'=f->'source'->'source_version';
  IF source IS NULL THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
  IF f->>'status'='client-stated' AND (f->'source'->>'analysis_id' IS NOT NULL OR length(f->'source'->>'quote')=0
   OR position(f->'source'->>'quote' IN source->>'text')=0 OR position(f->>'value' IN f->'source'->>'quote')=0) THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
  IF f->>'status'='observed' AND (f->>'field' IN ('approximate_size','placement') OR f->'source'->>'analysis_id' IS NULL
   OR f->'source'->>'message_id' IS DISTINCT FROM r.media_pin->>'message_id' OR f->'source'->>'analysis_id' IS DISTINCT FROM r.media_pin->>'analysis_id' OR f->'source'->>'analysis_sha256' IS DISTINCT FROM r.media_pin->>'analysis_sha256') THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
  SELECT x INTO old FROM jsonb_array_elements(facts) x WHERE x->'field'=f->'field';
  IF old IS NOT NULL AND old->'value'=f->'value'
   AND (old->>'status'<>'observed' OR old->>'conflict'='true' OR f->>'status'='observed') THEN
   IF NOT (old->>'conflict'='true' AND f->>'status'='client-stated' AND f->>'explicit_correction'='true'
    AND (old->'source'->>'message_id' IS DISTINCT FROM f->'source'->>'message_id')) THEN CONTINUE; END IF;
   IF old->>'status'='owner-confirmed' THEN
    -- Keep the confirmation and its source. The run retains the clarification.
    SELECT jsonb_agg(CASE WHEN x->'field'=f->'field' THEN x||jsonb_build_object('conflict',false) ELSE x END ORDER BY ordinal)
    INTO facts FROM jsonb_array_elements(facts) WITH ORDINALITY t(x,ordinal);
    CONTINUE;
   END IF;
  END IF;
  IF old IS NOT NULL AND old->'value' IS DISTINCT FROM f->'value'
   AND (f->>'explicit_correction'<>'true' OR (old->>'conflict'='true' AND f->>'status'='observed')) THEN
   SELECT coalesce(jsonb_agg(CASE WHEN x->'field'=f->'field' THEN x||jsonb_build_object('conflict',true) ELSE x END),'[]') INTO facts FROM jsonb_array_elements(facts) x;
  ELSE
   fact:=(f-'explicit_correction')||jsonb_build_object('confirmed_by',NULL,'conflict',false);
   SELECT coalesce(jsonb_agg(x),'[]') INTO facts FROM jsonb_array_elements(facts) x WHERE x->'field'<>f->'field';facts:=facts||jsonb_build_array(fact);
  END IF;
 END LOOP;
 pin:=jsonb_build_object('release_id',projection->'release_id','activation_version',projection->'activation_version','control_generation',projection->'control_generation');
 INSERT INTO platform.intake_state(workspace_id,business_id,conversation_id,client_id,service_id,pin,category,facts)
 VALUES(r.workspace_id,r.business_id,r.conversation_id,r.client_id,selected_service_id,pin,p->>'category',facts)
 ON CONFLICT(workspace_id,conversation_id) DO UPDATE
 SET service_id=excluded.service_id,pin=excluded.pin,category=excluded.category,facts=excluded.facts,version=platform.intake_state.version+1
 WHERE (platform.intake_state.service_id,platform.intake_state.pin,platform.intake_state.category,platform.intake_state.facts)
  IS DISTINCT FROM (excluded.service_id,excluded.pin,excluded.category,excluded.facts);
END $$""",
    "platform.intake_delivery_guard": r"""CREATE OR REPLACE FUNCTION platform.intake_delivery_guard(r platform.ai_runs) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE p jsonb;
BEGIN
 IF r.config->>'prompt_revision'<>'conversation_v7' OR r.result->'intake'->>'category'='FAQ_ONLY' THEN RETURN; END IF;
 p:=platform.intake_project(r.workspace_id,r.business_id,r.conversation_id,r.client_id);
 IF p->>'status'='OWNER_HANDOFF' AND r.result->>'kind'<>'handoff'
  OR p->>'status'='CLARIFY' AND (r.result->>'kind'<>'reply' OR r.result->>'text' IS DISTINCT FROM p->>'question')
  OR p->>'status'='PRELIMINARILY_COMPLETE' AND (r.result->>'kind' NOT IN ('reply','portfolio_photo') OR r.result->>'kind'='reply' AND r.result->>'text'<>'Предварительные сведения собраны. Мастер проверит детали; цена, длительность и запись пока не согласованы.') THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
END $$""",
    "platform.intake_escalation_decorate": r"""CREATE OR REPLACE FUNCTION platform.intake_escalation_decorate(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE link platform.intake_escalation_links%ROWTYPE; fresh boolean; client_question text;
BEGIN
 SELECT * INTO link FROM platform.intake_escalation_links WHERE workspace_id=(p->>'workspace_id')::uuid AND escalation_id=(p->>'escalation_id')::uuid;
 IF NOT FOUND THEN RETURN p; END IF;
 PERFORM platform.knowledge_owner_lock(link.business_id);
 fresh:=link.pin=platform.intake_runtime_pin(link.workspace_id,link.business_id,link.conversation_id,link.client_id);
 IF fresh AND p->>'validity'='CURRENT' THEN
  -- Show the current inbound text captured by the run that opened this card.
  SELECT nullif(btrim(left(platform.knowledge_query_text(r),300)),'') INTO client_question
  FROM app.escalations e JOIN platform.ai_runs r ON (r.workspace_id,r.job_id)=(e.workspace_id,e.source_job_id)
  WHERE (e.workspace_id,e.id)=(link.workspace_id,link.escalation_id)
   AND (r.business_id,r.conversation_id,r.client_id)=(link.business_id,link.conversation_id,link.client_id)
   AND r.config->>'prompt_revision'='conversation_v7' AND r.result->>'kind'='handoff'
   AND r.search_refs->>'status'='CONFLICT' AND r.search_refs->>'reason_code'='OWNER_LABEL_CONFLICT';
 END IF;
 RETURN p||jsonb_build_object('policy','PRELIMINARY_INTAKE_OWNER_V1','question',coalesce(client_question,link.summary->>'question'),'summary',CASE WHEN fresh THEN link.summary END,'summary_current',fresh,'validity',CASE WHEN NOT fresh AND p->>'validity'='CURRENT' THEN 'SOURCE_CHANGED' ELSE p->>'validity' END,'waiting',CASE WHEN fresh THEN p->>'waiting' END,'context_hold',CASE WHEN fresh THEN p->'context_hold' END,'can_resolve',fresh AND (p->>'can_resolve')::boolean);
END $$""",
    "platform.portfolio_session_admit": r"""CREATE OR REPLACE FUNCTION platform.portfolio_session_admit(business uuid,conversation uuid,p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE ws uuid:=platform.knowledge_owner_lock(business); actor uuid:=nullif(current_setting('asm.actor_id',true),'')::uuid; c app.conversations%ROWTYPE; s platform.portfolio_ai_sessions%ROWTYPE; moment timestamptz:=clock_timestamp();
BEGIN
 IF current_database() NOT IN ('asm_local','asm_test') OR platform.material_object(p,ARRAY['profile_id','execution','eligibility','max_calls','max_cost','duration_seconds']) IS NOT TRUE
   OR p->>'profile_id' NOT IN ('SYNTHETIC_VISION_PORTFOLIO_V1','SYNTHETIC_PORTFOLIO_PHOTO_V1','SYNTHETIC_INTAKE_V1') OR p->>'execution' IS DISTINCT FROM 'CONTROLLED' OR p->>'eligibility' IS DISTINCT FROM 'EVAL_ONLY'
   OR jsonb_typeof(p->'max_calls') IS DISTINCT FROM 'number' OR p->>'max_calls' !~ '^[1-4]$'
   OR jsonb_typeof(p->'max_cost') IS DISTINCT FROM 'string' OR p->>'max_cost' !~ '^(0|[1-9][0-9]?)([.][0-9]{1,9})?$' OR (p->>'max_cost')::numeric<=0 OR (p->>'max_cost')::numeric>10
   OR jsonb_typeof(p->'duration_seconds') IS DISTINCT FROM 'number' OR p->>'duration_seconds' !~ '^[1-9][0-9]{0,2}$' OR (p->>'duration_seconds')::integer>900 THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2901'; END IF;
 IF conversation IS NOT NULL THEN
  SELECT * INTO c FROM app.conversations WHERE workspace_id=ws AND business_id=business AND id=conversation;
  IF c.id IS NULL THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P2901'; END IF;
 END IF;
 INSERT INTO platform.portfolio_ai_sessions(workspace_id,business_id,actor_user_account_id,conversation_id,client_id,profile_id,execution,eligibility,max_calls,max_cost,created_at,expires_at)
 VALUES(ws,business,actor,conversation,c.client_id,p->>'profile_id',p->>'execution',p->>'eligibility',(p->>'max_calls')::integer,(p->>'max_cost')::numeric,moment,moment+(p->>'duration_seconds')::integer*interval '1 second') RETURNING * INTO s;
 RETURN jsonb_build_object('workspace_id',ws,'business_id',business,'session_id',s.id,'conversation_id',conversation,'client_id',c.client_id,'expires_at',s.expires_at,'max_calls',s.max_calls,'max_cost',s.max_cost::text);
END $$""",
    "platform.intake_delivery_session_lock": r"""CREATE OR REPLACE FUNCTION platform.intake_delivery_session_lock(ws uuid,business uuid,session uuid,reservation numeric) RETURNS platform.portfolio_ai_sessions
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE s platform.portfolio_ai_sessions%ROWTYPE; u jsonb; actor uuid:=nullif(current_setting('asm.actor_id',true),'')::uuid;
BEGIN
 SELECT * INTO s FROM platform.portfolio_ai_sessions WHERE workspace_id=ws AND business_id=business AND id=session FOR UPDATE;
 IF current_database() NOT IN ('asm_local','asm_test') OR s.id IS NULL OR s.execution<>'CONTROLLED' OR s.eligibility<>'EVAL_ONLY' OR s.profile_id NOT IN ('SYNTHETIC_PORTFOLIO_PHOTO_V1','SYNTHETIC_INTAKE_V1')
   OR s.revoked_at IS NOT NULL OR s.expires_at<=clock_timestamp() OR reservation<0 OR reservation>3.89
   OR NOT EXISTS(SELECT 1 FROM platform.workspaces w
    JOIN platform.workspace_memberships wm ON wm.workspace_id=w.id AND wm.user_account_id=s.actor_user_account_id
    JOIN platform.user_accounts ua ON ua.id=wm.user_account_id
    WHERE w.id=s.workspace_id AND w.status='ACTIVE' AND ua.status='ACTIVE' AND wm.role='OWNER' AND wm.status='ACTIVE') THEN RAISE EXCEPTION 'SESSION_NOT_ALLOWED' USING ERRCODE='P2901'; END IF;
 IF actor IS NOT NULL AND s.actor_user_account_id<>actor THEN RAISE EXCEPTION 'ACCESS_DENIED' USING ERRCODE='P2901'; END IF;
 u:=platform.portfolio_session_usage(ws,business,session);
 IF (u->>'calls')::integer>=s.max_calls OR (u->>'held_cost')::numeric+reservation>s.max_cost THEN RAISE EXCEPTION 'BUDGET_EXHAUSTED' USING ERRCODE='P2901'; END IF;
 RETURN s;
END $$""",
    "platform.ai_provider_session": r"""CREATE OR REPLACE FUNCTION platform.ai_provider_session(p jsonb,p_enable boolean) RETURNS jsonb
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
    OR (platform.quote_acceptance_schema_profile()->>'valid')::boolean IS NOT TRUE THEN
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
    "platform.human_context_policy_command": r"""CREATE OR REPLACE FUNCTION platform.human_context_policy_command(ws uuid,p_connection uuid,p_operation text,p_key text,
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
          OR jsonb_typeof(p_profile->'schema_revision')<>'string' OR p_profile->>'schema_revision'<>'0030'
          OR jsonb_typeof(p_profile->'profile_sha256')<>'string' OR p_profile->>'profile_sha256' !~ '^[0-9a-f]{64}$'
          OR p_profile->'drain_confirmed' IS DISTINCT FROM 'true'::jsonb THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2601'; END IF;
        SELECT platform.quote_acceptance_schema_profile() INTO profile;
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
        SELECT platform.quote_acceptance_schema_profile() INTO profile;
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
}

V8_FUNCTIONS = {
    "platform.ai_runtime_config_valid": r"""CREATE OR REPLACE FUNCTION platform.ai_runtime_config_valid(p jsonb) RETURNS boolean
LANGUAGE sql IMMUTABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
SELECT (((p->>'prompt_revision'='conversation_v7' AND p->>'schema_revision'='conversation_result_v3')
  OR (p->>'prompt_revision'='conversation_v8' AND p->>'schema_revision'='conversation_result_v4')) AND p->'limits'->>'currency'='RUB' AND platform.ai_synthetic_config_valid(jsonb_set(jsonb_set(p,'{prompt_revision}','"conversation_v2"'::jsonb),'{schema_revision}','"conversation_result_v1"'::jsonb))) OR (p->>'prompt_revision'='conversation_v6' AND p->>'schema_revision'='conversation_result_v2'
 AND p->'limits'->>'currency'='RUB'
 AND platform.ai_synthetic_config_valid(jsonb_set(jsonb_set(p,'{prompt_revision}','"conversation_v2"'::jsonb),'{schema_revision}','"conversation_result_v1"'::jsonb))) OR (p->>'prompt_revision' IN ('conversation_v4','conversation_v5') AND (p->>'prompt_revision'<>'conversation_v5' OR p->'limits'->>'currency'='RUB') AND platform.ai_synthetic_config_valid(jsonb_set(p,'{prompt_revision}','"conversation_v2"'::jsonb))) OR platform.ai_synthetic_config_valid(p) OR platform.ai_provider_config_valid(p) OR
  (p->>'prompt_revision'='conversation_v3' AND
    platform.ai_synthetic_config_valid(jsonb_set(p,'{prompt_revision}','"conversation_v2"'::jsonb))) $$""",
    "platform.ai_runtime_view": r"""CREATE OR REPLACE FUNCTION platform.ai_runtime_view(r platform.ai_runs) RETURNS jsonb
      LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      SELECT jsonb_build_object('run_id',r.id,'binding',r.binding,'snapshot',r.snapshot,'storage_fingerprint',r.storage_fingerprint,
        'config',r.config,'deadline',r.deadline,'reads_used',r.reads_used,'budget',jsonb_build_object(
          'calls_used',r.calls_used,'reads_reserved',r.reads_used,'tokens_reserved',r.tokens_reserved,
          'cost_reserved',r.cost_reserved::text,'currency',r.config->'limits'->>'currency'))
        ||CASE WHEN r.knowledge_pin IS NULL THEN '{}'::jsonb ELSE
          jsonb_build_object('knowledge_pin',r.knowledge_pin,'active_projection',r.active_projection) END
        ||CASE WHEN r.search_pin IS NOT NULL THEN jsonb_build_object('search_pin',r.search_pin,'search_refs',r.search_refs) ELSE '{}'::jsonb END||platform.portfolio_runtime_data(r)||CASE WHEN r.config->>'prompt_revision' IN ('conversation_v7','conversation_v8') THEN jsonb_build_object('intake',platform.intake_project(r.workspace_id,r.business_id,r.conversation_id,r.client_id)) ELSE '{}'::jsonb END $$""",
    "platform.ai_runtime_receipt": r"""CREATE OR REPLACE FUNCTION platform.ai_runtime_receipt(r platform.ai_runs) RETURNS jsonb
      LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      SELECT jsonb_build_object('run_id',r.id,'job_id',r.job_id,'turn_id',r.turn_id,'turn_revision',r.turn_revision,
        'selected_at',r.selected_at,'result',r.result,'send_permit',false)
        ||CASE WHEN r.knowledge_pin IS NULL THEN '{}'::jsonb ELSE jsonb_build_object('knowledge_pin',r.knowledge_pin) END
        ||CASE WHEN r.search_pin IS NOT NULL THEN jsonb_build_object('search_pin',r.search_pin,'search_refs',r.search_refs) ELSE '{}'::jsonb END||CASE WHEN r.config->>'prompt_revision' IN ('conversation_v5','conversation_v6','conversation_v7','conversation_v8') THEN jsonb_build_object('portfolio_pin',r.portfolio_pin,'media_pin',r.media_pin,'portfolio_refs',r.portfolio_refs) ELSE '{}'::jsonb END
        ||CASE WHEN r.config->>'prompt_revision'='conversation_v8'
          THEN jsonb_build_object('service_intents',platform.service_request_agent_result(r))
          ELSE '{}'::jsonb END $$""",
    "platform.ai_runtime_command": r"""CREATE OR REPLACE FUNCTION platform.ai_runtime_command(p_job uuid,p_claim uuid,p_op text,p jsonb) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE j platform.messaging_jobs%ROWTYPE; r platform.ai_runs%ROWTYPE; previous platform.ai_provider_calls%ROWTYPE;
        fresh jsonb; knowledge jsonb; search jsonb; portfolio jsonb; media jsonb; session uuid; auxiliary numeric:=0; b jsonb; cfg jsonb; lim jsonb; expiry timestamptz; next_job uuid; n integer; tokens integer; cost numeric;
      BEGIN
        PERFORM platform.turn_require_isolation();
        j:=platform.messaging_guard(p_job,p_claim);
        IF current_database() NOT IN ('asm_local','asm_test') OR jsonb_typeof(p) IS DISTINCT FROM 'object' OR octet_length(p::text)>32768 THEN
          RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
        IF p_op='ENQUEUE' THEN
          IF j.kind<>'PROCESS_TURN' OR j.step<>'TEST_CONSUME' OR p<>'{}'::jsonb THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
          PERFORM platform.ai_runtime_current(j,NULL);
          INSERT INTO platform.messaging_jobs(workspace_id,connection_id,kind,turn_id,turn_revision,step,correlation_id)
            VALUES(j.workspace_id,j.connection_id,'PROCESS_TURN',j.turn_id,j.turn_revision,'AI_GENERATE',j.correlation_id)
            ON CONFLICT(workspace_id,turn_id,turn_revision,step) DO NOTHING;
          SELECT id INTO STRICT next_job FROM platform.messaging_jobs WHERE workspace_id=j.workspace_id AND turn_id=j.turn_id AND turn_revision=j.turn_revision AND step='AI_GENERATE';
          RETURN jsonb_build_object('job_id',next_job);
        END IF;
        IF j.kind<>'PROCESS_TURN' OR j.step<>'AI_GENERATE' THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
        SELECT * INTO r FROM platform.ai_runs WHERE workspace_id=j.workspace_id AND job_id=j.id FOR UPDATE;
        IF p_op='PREPARE' THEN
          cfg:=p->'config';
          IF NOT platform.material_object(p,ARRAY['config','deadline']||CASE WHEN cfg->>'prompt_revision' IN ('conversation_v5','conversation_v6','conversation_v7','conversation_v8') THEN ARRAY['portfolio_session_id'] ELSE ARRAY[]::text[] END) OR jsonb_typeof(p->'deadline') IS DISTINCT FROM 'string'
            OR platform.ai_runtime_config_valid(cfg) IS NOT TRUE OR cfg->>'prompt_revision' NOT IN ('conversation_v3','conversation_v4','conversation_v5','conversation_v6','conversation_v7','conversation_v8') THEN
            RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
          IF r.id IS NOT NULL AND r.config IS DISTINCT FROM cfg THEN RAISE EXCEPTION 'IDEMPOTENCY_KEY_CONFLICT' USING ERRCODE='P2001'; END IF;
          BEGIN fresh:=platform.ai_runtime_current(j,r.snapshot);
          EXCEPTION WHEN SQLSTATE 'P2001' THEN
            IF r.id IS NOT NULL AND SQLERRM='AI_STALE' THEN RAISE EXCEPTION 'IDEMPOTENCY_KEY_CONFLICT' USING ERRCODE='P2001'; END IF;
            RAISE;
          END;
          IF cfg->'route'->>'execution'='PROVIDER' THEN
            PERFORM platform.ai_provider_guard((SELECT provider_session_id FROM platform.ai_deliveries WHERE job_id=j.id),j,cfg);
          ELSIF (SELECT provider_session_id FROM platform.ai_deliveries WHERE job_id=j.id) IS NOT NULL THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
          IF r.id IS NOT NULL THEN
            IF fresh->'binding' IS DISTINCT FROM r.binding OR platform.ai_knowledge_current(r) IS NOT TRUE OR platform.knowledge_runtime_current(r) IS NOT TRUE THEN RAISE EXCEPTION 'IDEMPOTENCY_KEY_CONFLICT' USING ERRCODE='P2001'; END IF;
            RETURN platform.ai_runtime_view(r);
          END IF;
          expiry:=least((p->>'deadline')::timestamptz,clock_timestamp()+(cfg->'limits'->>'duration_seconds')::numeric*interval '1 second');
          IF NOT isfinite(expiry) OR expiry<=clock_timestamp() THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
          IF cfg->>'prompt_revision'='conversation_v8' AND (current_database()<>'asm_test'
            OR NOT EXISTS(SELECT 1 FROM platform.ai_deliveries WHERE workspace_id=j.workspace_id AND job_id=j.id)
            OR NOT EXISTS(SELECT 1 FROM app.channel_connections WHERE workspace_id=j.workspace_id
              AND id=j.connection_id AND provider='CONTROLLED')) THEN
            RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
          b:=fresh->'binding';
          knowledge:=platform.ai_knowledge_snapshot(j.workspace_id,(b->>'business_id')::uuid);
          search:=CASE WHEN cfg->>'prompt_revision' IN ('conversation_v4','conversation_v5','conversation_v6','conversation_v7','conversation_v8') THEN platform.knowledge_availability(j.workspace_id,(b->>'business_id')::uuid,(knowledge->'knowledge_pin'->>'release_id')::uuid,(knowledge->'knowledge_pin'->>'activation_version')::bigint) END;
          IF cfg->>'prompt_revision' IN ('conversation_v5','conversation_v6','conversation_v7','conversation_v8') THEN
            IF platform.human_context_uuid(p->'portfolio_session_id') IS NOT TRUE THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
            session:=(p->>'portfolio_session_id')::uuid;
            IF cfg->>'prompt_revision' IN ('conversation_v6','conversation_v7','conversation_v8') THEN PERFORM platform.intake_delivery_session_lock(j.workspace_id,(b->>'business_id')::uuid,session,0); ELSE PERFORM platform.portfolio_session_lock(j.workspace_id,(b->>'business_id')::uuid,session,0); END IF;
            IF NOT EXISTS(SELECT 1 FROM platform.portfolio_ai_sessions WHERE id=session AND conversation_id=(b->>'conversation_id')::uuid AND client_id=(b->>'client_id')::uuid AND profile_id=CASE WHEN cfg->>'prompt_revision'='conversation_v8' THEN 'SYNTHETIC_SERVICE_INTENTS_V1'
                 WHEN cfg->>'prompt_revision'='conversation_v7' THEN 'SYNTHETIC_INTAKE_V1' WHEN cfg->>'prompt_revision'='conversation_v6' THEN 'SYNTHETIC_PORTFOLIO_PHOTO_V1' ELSE 'SYNTHETIC_VISION_PORTFOLIO_V1' END) THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
            portfolio:=platform.portfolio_availability(j.workspace_id,(b->>'business_id')::uuid,(knowledge->'knowledge_pin'->>'release_id')::uuid,(knowledge->'knowledge_pin'->>'activation_version')::bigint);
            media:=platform.portfolio_media_pin(j.workspace_id,(b->>'business_id')::uuid,(b->>'client_id')::uuid,(b->>'conversation_id')::uuid,true);
            auxiliary:=platform.portfolio_auxiliary_cost(j.workspace_id,(b->>'business_id')::uuid,(b->>'client_id')::uuid,(b->>'conversation_id')::uuid,media,NULL);
            IF auxiliary>(cfg->'limits'->>'cost_budget')::numeric THEN RAISE EXCEPTION 'AI_BUDGET' USING ERRCODE='P2001'; END IF;
          END IF;
          INSERT INTO platform.ai_runs(workspace_id,job_id,connection_id,conversation_id,client_id,business_id,turn_id,turn_revision,
            resume_receipt_id,control_generation,binding,snapshot,snapshot_digest,storage_fingerprint,config,config_fingerprint,deadline,knowledge_pin,active_projection,search_pin,portfolio_pin,media_pin,portfolio_session_id,cost_reserved)
          VALUES(j.workspace_id,j.id,j.connection_id,(b->>'conversation_id')::uuid,(b->>'client_id')::uuid,(b->>'business_id')::uuid,j.turn_id,j.turn_revision,
            (b->>'resume_receipt_id')::uuid,(b->>'control_generation')::bigint,b,fresh->'snapshot',b->>'snapshot_digest',encode(sha256(convert_to((fresh->'snapshot')::text,'UTF8')),'hex'),cfg,encode(sha256(convert_to(cfg::text,'UTF8')),'hex'),expiry,knowledge->'knowledge_pin',knowledge->'active_projection',search,portfolio,media,session,auxiliary) RETURNING * INTO r;
          IF cfg->>'prompt_revision' IN ('conversation_v7','conversation_v8') THEN UPDATE platform.ai_runs SET intake_pin=platform.intake_runtime_pin(r.workspace_id,r.business_id,r.conversation_id,r.client_id),
            service_request_pin=CASE WHEN cfg->>'prompt_revision'='conversation_v8' THEN platform.service_request_agent_pin(r) END
            WHERE workspace_id=r.workspace_id AND id=r.id RETURNING * INTO r; END IF;
          RETURN platform.ai_runtime_view(r);
        END IF;
        IF r.id IS NULL OR p->>'run_id' IS DISTINCT FROM r.id::text THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
        IF p_op='COMPLETE' THEN
          IF NOT platform.material_object(p,ARRAY['run_id','sequence','completion']) OR platform.ai_runtime_completion_valid(p->'completion') IS NOT TRUE THEN
            RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
          SELECT * INTO previous FROM platform.ai_provider_calls WHERE workspace_id=j.workspace_id AND run_id=r.id AND sequence=(p->>'sequence')::int FOR UPDATE;
          IF previous.claim_hash IS DISTINCT FROM sha256(convert_to(p_claim::text,'UTF8')) OR previous.attempt_count IS DISTINCT FROM j.attempt_count THEN
            RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
          IF previous.completed_at IS NOT NULL THEN
            IF previous.completion IS DISTINCT FROM p->'completion' THEN RAISE EXCEPTION 'IDEMPOTENCY_KEY_CONFLICT' USING ERRCODE='P2001'; END IF;
          ELSE
            UPDATE platform.ai_provider_calls SET completion=p->'completion',completed_at=clock_timestamp()
              WHERE workspace_id=j.workspace_id AND run_id=r.id AND sequence=previous.sequence;
          END IF;
          RETURN jsonb_build_object('recorded',true);
        END IF;
        fresh:=platform.ai_runtime_current(j,r.snapshot);
        IF fresh->'binding' IS DISTINCT FROM r.binding OR platform.ai_knowledge_current(r) IS NOT TRUE OR platform.knowledge_runtime_current(r) IS NOT TRUE THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
        IF r.deadline<=clock_timestamp() OR r.result IS NOT NULL THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
        IF r.config->'route'->>'execution'='PROVIDER' THEN
          PERFORM platform.ai_provider_guard((SELECT provider_session_id FROM platform.ai_deliveries WHERE job_id=j.id),j,r.config);
        END IF;
        IF r.config->>'prompt_revision' IN ('conversation_v4','conversation_v5','conversation_v6','conversation_v7','conversation_v8') AND r.search_refs IS NULL THEN RAISE EXCEPTION 'AI_INCOMPLETE' USING ERRCODE='P2001'; END IF;
        lim:=r.config->'limits';
        SELECT * INTO previous FROM platform.ai_provider_calls WHERE workspace_id=j.workspace_id AND run_id=r.id AND sequence=r.calls_used;
        IF p_op='DELIVERY_READ' THEN RETURN platform.portfolio_delivery_attest(j,r,p); END IF;
        IF p_op IN ('AUTHORIZE','READ') THEN
          IF p->'binding' IS DISTINCT FROM r.binding OR p->'knowledge_pin' IS DISTINCT FROM r.knowledge_pin OR (r.config->>'prompt_revision' IN ('conversation_v4','conversation_v5','conversation_v6','conversation_v7','conversation_v8') AND p->'search_pin' IS DISTINCT FROM r.search_pin) OR (r.config->>'prompt_revision' IN ('conversation_v5','conversation_v6','conversation_v7','conversation_v8') AND (p->'portfolio_pin' IS DISTINCT FROM r.portfolio_pin OR p->'media_pin' IS DISTINCT FROM r.media_pin)) THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
          IF (p_op='AUTHORIZE' AND (NOT platform.material_object(p,ARRAY['run_id','binding','knowledge_pin','boundary']||CASE WHEN r.config->>'prompt_revision' IN ('conversation_v4','conversation_v5','conversation_v6','conversation_v7','conversation_v8') THEN ARRAY['search_pin']||CASE WHEN r.config->>'prompt_revision' IN ('conversation_v5','conversation_v6','conversation_v7','conversation_v8') THEN ARRAY['portfolio_pin','media_pin'] ELSE ARRAY[]::text[] END ELSE ARRAY[]::text[] END) OR p->>'boundary' NOT IN ('MODEL','READ','FOLLOWUP','CANDIDATE')))
            OR (p_op='READ' AND NOT platform.material_object(p,ARRAY['run_id','binding','knowledge_pin']||CASE WHEN r.config->>'prompt_revision' IN ('conversation_v4','conversation_v5','conversation_v6','conversation_v7','conversation_v8') THEN ARRAY['search_pin']||CASE WHEN r.config->>'prompt_revision' IN ('conversation_v5','conversation_v6','conversation_v7','conversation_v8') THEN ARRAY['portfolio_pin','media_pin'] ELSE ARRAY[]::text[] END ELSE ARRAY[]::text[] END)) THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
          IF p->>'boundary'='MODEL' AND r.calls_used<>0 THEN RAISE EXCEPTION 'AI_INCOMPLETE' USING ERRCODE='P2001'; END IF;
          IF p_op='READ' OR p->>'boundary' IN ('READ','FOLLOWUP') THEN
            IF r.calls_used<>1 OR previous.completed_at IS NULL OR previous.completion->>'kind'<>'TOOLS'
              OR (lim->>'read_executions')::int<1 THEN RAISE EXCEPTION 'AI_BUDGET' USING ERRCODE='P2001'; END IF;
            IF (p_op='READ' OR p->>'boundary'='READ') AND r.reads_used<>0 OR p->>'boundary'='FOLLOWUP' AND r.reads_used<>1 THEN
              RAISE EXCEPTION 'AI_BUDGET' USING ERRCODE='P2001'; END IF;
          END IF;
          IF p->>'boundary'='CANDIDATE' AND (r.calls_used=0 OR previous.completed_at IS NULL OR previous.completion->>'kind'<>'OUTPUT') THEN
            RAISE EXCEPTION 'AI_INCOMPLETE' USING ERRCODE='P2001'; END IF;
          IF p_op='READ' THEN
            UPDATE platform.ai_runs SET reads_used=1,read_audit=jsonb_build_object('outcome','READ','context_version',r.binding->'context_version',
              'turn_revision',r.turn_revision,'native',r.binding->'native','knowledge_pin',r.knowledge_pin,'at',clock_timestamp())||CASE WHEN r.search_pin IS NOT NULL THEN jsonb_build_object('search_pin_sha256',encode(sha256(convert_to(r.search_pin::text,'UTF8')),'hex')) ELSE '{}'::jsonb END WHERE workspace_id=j.workspace_id AND id=r.id;
            RETURN jsonb_build_object('binding',r.binding,'snapshot',r.snapshot,
              'knowledge_pin',r.knowledge_pin,'active_projection',r.active_projection)||CASE WHEN r.config->>'prompt_revision' IN ('conversation_v7','conversation_v8') THEN jsonb_build_object('intake',platform.intake_project(r.workspace_id,r.business_id,r.conversation_id,r.client_id)) ELSE '{}'::jsonb END
              ||CASE WHEN r.search_pin IS NOT NULL THEN jsonb_build_object('search_pin',r.search_pin,'search_refs',r.search_refs,'search_projection',platform.knowledge_projection(r)) ELSE '{}'::jsonb END||platform.portfolio_runtime_data(r)||CASE WHEN r.config->>'prompt_revision' IN ('conversation_v6','conversation_v7','conversation_v8') THEN jsonb_build_object('delivery_eligible',platform.portfolio_delivery_eligible(r)) ELSE '{}'::jsonb END||CASE WHEN r.config->>'prompt_revision' IN ('conversation_v5','conversation_v6','conversation_v7','conversation_v8') THEN jsonb_build_object('portfolio_projection',platform.portfolio_projection(r)) ELSE '{}'::jsonb END;
          END IF;
          RETURN jsonb_build_object('allowed',true);
        ELSIF p_op='RESERVE' THEN
          b:=p->'budget'; n:=r.calls_used+1;
          IF NOT platform.material_object(p,ARRAY['run_id','budget']) OR NOT platform.material_object(b,ARRAY['calls_used','reads_reserved','tokens_reserved','cost_reserved','currency'])
            OR jsonb_typeof(b->'calls_used')<>'number' OR jsonb_typeof(b->'reads_reserved')<>'number' OR jsonb_typeof(b->'tokens_reserved')<>'number' THEN
            RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
          tokens:=(b->>'tokens_reserved')::int; cost:=(b->>'cost_reserved')::numeric;
          IF n>2 OR n>(lim->>'model_calls')::int OR (b->>'calls_used')::int<>n OR (b->>'reads_reserved')::int<>r.reads_used
            OR b->>'currency' IS DISTINCT FROM lim->>'currency' OR tokens<=r.tokens_reserved OR tokens>(lim->>'total_tokens')::int
            OR tokens-r.tokens_reserved>(lim->>'input_tokens')::int+(lim->>'output_tokens')::int
            OR cost<>r.cost_reserved+(lim->>'call_cost_reservation')::numeric OR cost>(lim->>'cost_budget')::numeric
            OR (n=2 AND (r.reads_used<>1 OR previous.completed_at IS NULL OR previous.completion->>'kind'<>'TOOLS')) THEN
            RAISE EXCEPTION 'AI_BUDGET' USING ERRCODE='P2001'; END IF;
          IF r.config->'route'->>'execution'='PROVIDER' AND EXISTS(
            SELECT 1 FROM platform.ai_provider_sessions s WHERE s.id=(SELECT provider_session_id FROM platform.ai_deliveries WHERE job_id=j.id) AND
            (EXISTS(SELECT 1 FROM platform.ai_provider_calls pc JOIN platform.ai_runs ar ON (ar.workspace_id,ar.id)=(pc.workspace_id,pc.run_id)
              JOIN platform.ai_deliveries d ON (d.workspace_id,d.job_id)=(ar.workspace_id,ar.job_id)
              WHERE d.provider_session_id=s.id AND (pc.completed_at IS NULL OR pc.completion->>'kind'='UNKNOWN'
                OR pc.completion->'cost'->>'status'='UNKNOWN'
                OR (pc.completion->'cost'->>'amount')::numeric>(ar.config->'limits'->>'call_cost_reservation')::numeric))
            OR (SELECT count(*) FROM platform.ai_provider_calls pc JOIN platform.ai_deliveries d ON (d.workspace_id,d.job_id)=(pc.workspace_id,(SELECT job_id FROM platform.ai_runs WHERE workspace_id=pc.workspace_id AND id=pc.run_id)) WHERE d.provider_session_id=s.id)>=s.max_calls
            OR (SELECT coalesce(sum(greatest((ar.config->'limits'->>'call_cost_reservation')::numeric,coalesce((pc.completion->'cost'->>'amount')::numeric,0))),0)
              FROM platform.ai_provider_calls pc JOIN platform.ai_runs ar ON (ar.workspace_id,ar.id)=(pc.workspace_id,pc.run_id)
              JOIN platform.ai_deliveries d ON (d.workspace_id,d.job_id)=(ar.workspace_id,ar.job_id) WHERE d.provider_session_id=s.id)
              +(lim->>'call_cost_reservation')::numeric>s.max_rub)) THEN
            RAISE EXCEPTION 'AI_BUDGET' USING ERRCODE='P2001'; END IF;
          IF r.config->>'prompt_revision' IN ('conversation_v5','conversation_v6','conversation_v7','conversation_v8') THEN
            auxiliary:=platform.portfolio_auxiliary_cost(r.workspace_id,r.business_id,r.client_id,r.conversation_id,r.media_pin,r.id);
            SELECT auxiliary+coalesce(sum(greatest((lim->>'call_cost_reservation')::numeric,
              coalesce((pc.completion->'cost'->>'amount')::numeric,(lim->>'call_cost_reservation')::numeric))),0)
              +(lim->>'call_cost_reservation')::numeric INTO auxiliary
              FROM platform.ai_provider_calls pc WHERE pc.workspace_id=r.workspace_id AND pc.run_id=r.id;
            IF greatest(cost,auxiliary)>(lim->>'cost_budget')::numeric THEN RAISE EXCEPTION 'AI_BUDGET' USING ERRCODE='P2001'; END IF;
            IF r.config->>'prompt_revision' IN ('conversation_v6','conversation_v7','conversation_v8') THEN PERFORM platform.intake_delivery_session_lock(r.workspace_id,r.business_id,r.portfolio_session_id,(lim->>'call_cost_reservation')::numeric); ELSE PERFORM platform.portfolio_session_lock(r.workspace_id,r.business_id,r.portfolio_session_id,(lim->>'call_cost_reservation')::numeric); END IF;
            cost:=greatest(cost,auxiliary);
          END IF;
          INSERT INTO platform.ai_provider_calls(workspace_id,run_id,sequence,claim_hash,attempt_count,budget,portfolio_session_id)
            VALUES(j.workspace_id,r.id,n,sha256(convert_to(p_claim::text,'UTF8')),j.attempt_count,b,r.portfolio_session_id);
          UPDATE platform.ai_runs SET calls_used=n,tokens_reserved=tokens,cost_reserved=cost WHERE workspace_id=j.workspace_id AND id=r.id;
          RETURN jsonb_build_object('sequence',n);
        ELSIF p_op='COMMIT' THEN
          IF NOT platform.material_object(p,ARRAY['run_id','result']) OR (CASE WHEN r.config->>'prompt_revision'='conversation_v8' THEN platform.service_intent_result_valid(p->'result')
             WHEN r.config->>'prompt_revision'='conversation_v7' THEN platform.intake_result_valid(p->'result') WHEN r.config->>'prompt_revision'='conversation_v6' THEN platform.portfolio_delivery_result_valid(p->'result') ELSE platform.ai_runtime_result_valid(p->'result') END) IS NOT TRUE THEN
            RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
          IF r.calls_used=0 OR previous.completed_at IS NULL OR previous.completion->>'kind'<>'OUTPUT' THEN RAISE EXCEPTION 'AI_INCOMPLETE' USING ERRCODE='P2001'; END IF;
          PERFORM platform.messaging_guard(p_job,p_claim);
          PERFORM platform.intake_apply(r,p->'result'->'intake');
          IF r.config->>'prompt_revision'='conversation_v8' AND (p->'result') ? 'intents' THEN
            PERFORM platform.service_request_agent_begin(r,j,p->'result');
          END IF;
          UPDATE platform.ai_runs SET intake_pin=CASE WHEN r.config->>'prompt_revision' IN ('conversation_v7','conversation_v8') THEN platform.intake_runtime_pin(r.workspace_id,r.business_id,r.conversation_id,r.client_id) ELSE NULL END,result=p->'result',selected_at=clock_timestamp(),winning_claim_hash=sha256(convert_to(p_claim::text,'UTF8'))
            WHERE workspace_id=j.workspace_id AND id=r.id AND result IS NULL RETURNING * INTO r;
          PERFORM platform.ai_delivery_select(j,r);
          UPDATE platform.messaging_jobs SET status='SUCCEEDED',turn_outcome='OBSERVED',error_code=NULL,claim_token=NULL,lease_until=NULL,
            worker_id=NULL,completed_at=clock_timestamp(),version=version+1 WHERE id=j.id;
          RETURN platform.ai_runtime_receipt(r);
        END IF;
        RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001';
      EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range OR invalid_datetime_format OR datetime_field_overflow THEN
        RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001';
      END $$""",
    "platform.ai_delivery_select": r"""CREATE OR REPLACE FUNCTION platform.ai_delivery_select(j platform.messaging_jobs,r platform.ai_runs) RETURNS void
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE d platform.ai_deliveries%ROWTYPE; c app.conversations%ROWTYPE; conn app.channel_connections%ROWTYPE;
        msg uuid; box uuid; send uuid; intent_context bigint; e jsonb; ref jsonb; v platform.portfolio_asset_versions%ROWTYPE;
      BEGIN
        SELECT * INTO d FROM platform.ai_deliveries WHERE workspace_id=j.workspace_id AND job_id=j.id FOR UPDATE;
        IF NOT FOUND THEN RETURN; END IF; -- historical DB-only run: no retroactive intent
        IF d.selected_kind IS NOT NULL OR r.result IS NULL OR r.winning_claim_hash IS DISTINCT FROM sha256(convert_to(j.claim_token::text,'UTF8')) THEN
          RAISE EXCEPTION 'IDEMPOTENCY_KEY_CONFLICT' USING ERRCODE='P2001'; END IF;
        PERFORM platform.ai_runtime_current(j,r.snapshot);
        IF platform.ai_knowledge_current(r) IS NOT TRUE OR platform.knowledge_runtime_current(r) IS NOT TRUE THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
        SELECT * INTO STRICT c FROM app.conversations WHERE workspace_id=j.workspace_id AND id=r.conversation_id;
        SELECT * INTO STRICT conn FROM app.channel_connections WHERE workspace_id=j.workspace_id AND id=j.connection_id;
        PERFORM platform.intake_delivery_guard(r);
        IF r.result->>'kind'='reply' THEN
          IF conn.provider='TELEGRAM' AND platform.telegram_can_send(j.workspace_id,j.connection_id,c.id,false) IS NOT TRUE THEN
            RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
          INSERT INTO app.messages(workspace_id,conversation_id,connection_id,provider_chat_id,direction,content_type,text,occurred_at)
            VALUES(j.workspace_id,c.id,j.connection_id,c.provider_chat_id,'OUTBOUND','TEXT',r.result->>'text',clock_timestamp()) RETURNING id INTO msg;
          SELECT version INTO STRICT intent_context FROM app.conversations WHERE workspace_id=j.workspace_id AND id=c.id;
          IF intent_context::numeric<>(r.binding->>'context_version')::numeric+1 THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
          INSERT INTO app.outbox_events(workspace_id,connection_id,message_id,kind)
            VALUES(j.workspace_id,j.connection_id,msg,'SEND_AI_TEXT') RETURNING id INTO box;
          INSERT INTO platform.messaging_jobs(workspace_id,connection_id,kind,outbox_id,correlation_id)
            VALUES(j.workspace_id,j.connection_id,'SEND_AI_TEXT',box,j.correlation_id) RETURNING id INTO send;
        ELSIF r.result->>'kind'='portfolio_photo' THEN
          ref:=r.result->'selection';
          IF r.config->>'prompt_revision' NOT IN ('conversation_v6','conversation_v7','conversation_v8') OR r.config->>'schema_revision'<>(CASE WHEN r.config->>'prompt_revision'='conversation_v8' THEN 'conversation_result_v4'
                 WHEN r.config->>'prompt_revision'='conversation_v7' THEN 'conversation_result_v3' ELSE 'conversation_result_v2' END)
            OR d.provider_session_id IS NOT NULL OR r.reads_used<>1 OR r.calls_used<>2
            OR r.delivery_read_audit IS NULL OR NOT (r.delivery_read_audit->'shown_refs') @> jsonb_build_array(ref)
            OR platform.portfolio_delivery_result_valid(r.result-'intake') IS NOT TRUE OR platform.portfolio_runtime_current(r) IS NOT TRUE
            OR platform.portfolio_delivery_source(r,ref) IS NOT TRUE THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
          IF conn.provider='TELEGRAM' AND platform.telegram_can_send(j.workspace_id,j.connection_id,c.id,false) IS NOT TRUE THEN
            RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
          SELECT * INTO STRICT v FROM platform.portfolio_asset_versions WHERE workspace_id=r.workspace_id AND business_id=r.business_id AND id=(ref->>'asset_version_id')::uuid;
          INSERT INTO app.messages(workspace_id,conversation_id,connection_id,provider_chat_id,direction,content_type,text,occurred_at)
            VALUES(j.workspace_id,c.id,j.connection_id,c.provider_chat_id,'OUTBOUND','PORTFOLIO_PHOTO',r.result->>'caption',clock_timestamp()) RETURNING id INTO msg;
          SELECT version INTO STRICT intent_context FROM app.conversations WHERE workspace_id=j.workspace_id AND id=c.id;
          IF intent_context::numeric<>(r.binding->>'context_version')::numeric+1 THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
          INSERT INTO app.outbox_events(workspace_id,connection_id,message_id,kind) VALUES(j.workspace_id,j.connection_id,msg,'SEND_AI_PHOTO') RETURNING id INTO box;
          INSERT INTO platform.messaging_jobs(workspace_id,connection_id,kind,outbox_id,correlation_id) VALUES(j.workspace_id,j.connection_id,'SEND_AI_PHOTO',box,j.correlation_id) RETURNING id INTO send;
          INSERT INTO platform.portfolio_delivery_intents(workspace_id,business_id,run_id,conversation_id,client_id,connection_id,message_id,outbox_id,send_job_id,item_id,revision_id,asset_id,asset_version_id,source_sha256,caption,request_fingerprint,context_sha256)
          VALUES(r.workspace_id,r.business_id,r.id,r.conversation_id,r.client_id,r.connection_id,msg,box,send,(ref->>'item_id')::uuid,(ref->>'revision_id')::uuid,v.asset_id,v.id,v.sha256,r.result->>'caption',
            encode(sha256(convert_to(E'asm:m5:portfolio_delivery:v1\n'||r.id::text||E'\n'||r.result::text,'UTF8')),'hex'),r.delivery_read_audit->>'context_sha256');
        ELSIF r.result->>'kind'='handoff' THEN
          e:=platform.escalation_request_for_turn(j.id,j.claim_token);
          IF e->>'code' IS DISTINCT FROM 'ESCALATED' THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
          IF r.config->>'prompt_revision' IN ('conversation_v7','conversation_v8') THEN INSERT INTO platform.intake_escalation_links(workspace_id,escalation_id,business_id,conversation_id,client_id,pin,summary) VALUES(r.workspace_id,(e->>'escalation_id')::uuid,r.business_id,r.conversation_id,r.client_id,platform.intake_runtime_pin(r.workspace_id,r.business_id,r.conversation_id,r.client_id),(platform.intake_project(r.workspace_id,r.business_id,r.conversation_id,r.client_id)-'sources')||jsonb_build_object('sources','[]'::jsonb)); END IF;
        END IF;
        IF j.lease_until<=clock_timestamp() THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
        UPDATE platform.ai_deliveries SET knowledge_pin=r.knowledge_pin,search_pin=r.search_pin,portfolio_pin=r.portfolio_pin,media_pin=r.media_pin,run_id=r.id,selected_kind=r.result->>'kind',message_id=msg,outbox_id=box,send_job_id=send,
          intent_context_version=intent_context,escalation_id=(e->>'escalation_id')::uuid WHERE workspace_id=j.workspace_id AND job_id=j.id;
      END $$""",
    "platform.ai_reply_rights_commit": r"""CREATE OR REPLACE FUNCTION platform.ai_reply_rights_commit(p_job uuid,p_claim uuid,p_run uuid,p_generation bigint,p_version bigint,p_observation jsonb,p_result jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE j platform.messaging_jobs%ROWTYPE; r platform.ai_runs%ROWTYPE; conn app.channel_connections%ROWTYPE; s platform.telegram_connection_state%ROWTYPE; observed jsonb;
BEGIN
  r:=platform.ai_reply_rights_current(p_job,p_claim,p_run);
  j:=platform.messaging_guard(p_job,p_claim);
  IF (CASE WHEN r.config->>'prompt_revision'='conversation_v8' THEN platform.service_intent_result_valid(p_result)
             WHEN r.config->>'prompt_revision'='conversation_v7' THEN platform.intake_result_valid(p_result) WHEN r.config->>'prompt_revision'='conversation_v6' THEN platform.portfolio_delivery_result_valid(p_result) ELSE platform.ai_runtime_result_valid(p_result) END) IS NOT TRUE OR p_result->>'kind' NOT IN ('reply','portfolio_photo') THEN
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
    "platform.knowledge_runtime_current": r"""CREATE OR REPLACE FUNCTION platform.knowledge_runtime_current(r platform.ai_runs) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE j platform.messaging_jobs%ROWTYPE; state platform.business_configuration_state%ROWTYPE;
BEGIN
  IF r.config->>'prompt_revision' NOT IN ('conversation_v4','conversation_v5','conversation_v6','conversation_v7','conversation_v8') THEN RETURN true; END IF;
  j:=platform.messaging_guard(nullif(current_setting('asm.job_id',true),'')::uuid,nullif(current_setting('asm.claim_token',true),'')::uuid);
  IF j.workspace_id<>r.workspace_id OR j.connection_id<>r.connection_id THEN RETURN false; END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(r.workspace_id::text||':'||r.business_id::text||'|CONFIGURATION_V1',2018));
  SELECT * INTO state FROM platform.business_configuration_state WHERE workspace_id=r.workspace_id AND business_id=r.business_id;
  RETURN r.search_pin IS NOT NULL AND r.search_pin=platform.knowledge_availability(r.workspace_id,r.business_id,state.active_release_id,coalesce(state.activation_version,0)) AND platform.portfolio_runtime_current(r) AND platform.intake_current(r);
END $$""",
    "platform.portfolio_runtime_current": r"""CREATE OR REPLACE FUNCTION platform.portfolio_runtime_current(r platform.ai_runs) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE state platform.business_configuration_state%ROWTYPE;
BEGIN
 IF r.config->>'prompt_revision' NOT IN ('conversation_v5','conversation_v6','conversation_v7','conversation_v8') THEN RETURN true; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended(r.workspace_id::text||':'||r.business_id::text||'|CONFIGURATION_V1',2018));
 SELECT * INTO state FROM platform.business_configuration_state WHERE workspace_id=r.workspace_id AND business_id=r.business_id;
 RETURN r.portfolio_pin IS NOT NULL AND r.media_pin IS NOT NULL
  AND r.portfolio_pin=platform.portfolio_availability(r.workspace_id,r.business_id,state.active_release_id,coalesce(state.activation_version,0))
  AND r.media_pin=platform.portfolio_media_pin(r.workspace_id,r.business_id,r.client_id,r.conversation_id,true)
  AND EXISTS(SELECT 1 FROM platform.portfolio_ai_sessions s
   JOIN platform.workspaces w ON w.id=s.workspace_id
   JOIN platform.workspace_memberships wm ON wm.workspace_id=s.workspace_id AND wm.user_account_id=s.actor_user_account_id
   JOIN platform.user_accounts ua ON ua.id=wm.user_account_id
   WHERE s.workspace_id=r.workspace_id AND s.business_id=r.business_id AND s.id=r.portfolio_session_id
    AND s.profile_id=CASE WHEN r.config->>'prompt_revision'='conversation_v8' THEN 'SYNTHETIC_SERVICE_INTENTS_V1'
                 WHEN r.config->>'prompt_revision'='conversation_v7' THEN 'SYNTHETIC_INTAKE_V1' WHEN r.config->>'prompt_revision'='conversation_v6' THEN 'SYNTHETIC_PORTFOLIO_PHOTO_V1' ELSE 'SYNTHETIC_VISION_PORTFOLIO_V1' END
    AND s.conversation_id=r.conversation_id AND s.client_id=r.client_id AND s.revoked_at IS NULL AND s.expires_at>clock_timestamp()
    AND w.status='ACTIVE' AND ua.status='ACTIVE' AND wm.role='OWNER' AND wm.status='ACTIVE');
END $$""",
    "platform.portfolio_runtime_data": r"""CREATE OR REPLACE FUNCTION platform.portfolio_runtime_data(r platform.ai_runs) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE a platform.vision_analyses%ROWTYPE;
BEGIN
 IF r.config->>'prompt_revision' NOT IN ('conversation_v5','conversation_v6','conversation_v7','conversation_v8') THEN RETURN '{}'::jsonb; END IF;
 SELECT * INTO a FROM platform.vision_analyses WHERE workspace_id=r.workspace_id AND business_id=r.business_id AND id=(r.media_pin->>'analysis_id')::uuid AND conversation_id=r.conversation_id AND client_id=r.client_id;
 RETURN jsonb_build_object('portfolio_pin',r.portfolio_pin,'media_pin',r.media_pin,'portfolio_refs',r.portfolio_refs,'portfolio_session_id',r.portfolio_session_id,'search_query',platform.portfolio_run_query(r),'vision_analysis',platform.portfolio_analysis_view(a));
END $$""",
    "platform.portfolio_query_reserve": r"""CREATE OR REPLACE FUNCTION platform.portfolio_query_reserve(p_job uuid,p_claim uuid,p_run uuid,p_pin jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE j platform.messaging_jobs%ROWTYPE; r platform.ai_runs%ROWTYPE; ec platform.knowledge_embedding_calls%ROWTYPE; fresh jsonb; query text; wire text; empty jsonb;
 ticket uuid:=gen_random_uuid(); s platform.portfolio_ai_sessions%ROWTYPE; moment timestamptz:=clock_timestamp();
BEGIN
 PERFORM platform.turn_require_isolation();j:=platform.messaging_guard(p_job,p_claim);
 SELECT * INTO r FROM platform.ai_runs WHERE workspace_id=j.workspace_id AND job_id=j.id AND id=p_run FOR UPDATE;
 IF r.id IS NULL OR r.config->>'prompt_revision' NOT IN ('conversation_v5','conversation_v6','conversation_v7','conversation_v8') OR r.calls_used<>0 OR r.result IS NOT NULL OR r.deadline<=moment THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
 fresh:=platform.ai_runtime_current(j,r.snapshot);
 IF fresh->'binding' IS DISTINCT FROM r.binding OR platform.ai_knowledge_current(r) IS NOT TRUE OR platform.knowledge_runtime_current(r) IS NOT TRUE OR platform.portfolio_runtime_current(r) IS NOT TRUE
  OR p_pin IS DISTINCT FROM jsonb_build_object('search_pin',r.search_pin,'portfolio_pin',r.portfolio_pin,'media_pin',r.media_pin) THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
 SELECT * INTO ec FROM platform.knowledge_embedding_calls WHERE workspace_id=r.workspace_id AND run_id=r.id;
 IF FOUND THEN RETURN jsonb_build_object('status','REPLAY','call_id',ec.id,'ticket',NULL,'wire',NULL,'wire_sha256',ec.request_sha256,'profile_id',ec.profile_id,'deadline',ec.deadline,'reserved_cost','0.08','currency','RUB'); END IF;
 query:=platform.portfolio_run_query(r);
 IF r.search_refs IS NOT NULL OR query='' OR NOT EXISTS(SELECT 1 FROM platform.knowledge_build_chunks WHERE workspace_id=r.workspace_id AND business_id=r.business_id AND build_id=(r.search_pin->>'build_id')::uuid AND embedding IS NOT NULL)
  AND NOT EXISTS(SELECT 1 FROM platform.portfolio_build_items WHERE workspace_id=r.workspace_id AND business_id=r.business_id AND build_id=(r.portfolio_pin->>'build_id')::uuid AND embedding IS NOT NULL) THEN
  IF r.search_refs IS NULL THEN
   empty:=jsonb_build_object('revision','business_knowledge_search_result_v1','profile_id','polza_openai_text_embedding3small_1536_cosine_v1','query_sha256',encode(sha256(convert_to(query,'UTF8')),'hex'),'status','EMPTY','reason_code',CASE WHEN query='' THEN 'NO_QUERY' ELSE 'NO_ELIGIBLE_SOURCE' END,'references','[]'::jsonb,'conflicts','[]'::jsonb);
   UPDATE platform.ai_runs SET search_refs=empty,portfolio_refs=platform.portfolio_refs(platform.portfolio_select(r.workspace_id,r.business_id,r.portfolio_pin,NULL,query)) WHERE workspace_id=r.workspace_id AND id=r.id;
  END IF;
  RETURN jsonb_build_object('status','REPLAY','call_id',NULL,'ticket',NULL,'wire',NULL,'wire_sha256',NULL,'profile_id','polza_openai_text_embedding3small_1536_cosine_v1','deadline',NULL,'reserved_cost','0.00','currency','RUB');
 END IF;
 wire:=platform.portfolio_embedding_wire(jsonb_build_array(query));
 IF octet_length(wire)>8192 THEN RAISE EXCEPTION 'WIRE_LIMIT' USING ERRCODE='P2901'; END IF;
 IF r.config->>'prompt_revision' IN ('conversation_v7','conversation_v8') THEN
  s:=platform.intake_delivery_session_lock(r.workspace_id,r.business_id,r.portfolio_session_id,0.08);
  IF s.profile_id IS DISTINCT FROM (
    CASE WHEN r.config->>'prompt_revision'='conversation_v8' THEN 'SYNTHETIC_SERVICE_INTENTS_V1'
      ELSE 'SYNTHETIC_INTAKE_V1' END) THEN RAISE EXCEPTION 'SESSION_NOT_ALLOWED' USING ERRCODE='P2901'; END IF;
 ELSIF r.config->>'prompt_revision'='conversation_v6' THEN
  s:=platform.portfolio_delivery_session_lock(r.workspace_id,r.business_id,r.portfolio_session_id,0.08);
 ELSE
  s:=platform.portfolio_session_lock(r.workspace_id,r.business_id,r.portfolio_session_id,0.08);
 END IF;
 IF s.conversation_id IS DISTINCT FROM r.conversation_id OR s.client_id IS DISTINCT FROM r.client_id THEN RAISE EXCEPTION 'SESSION_NOT_ALLOWED' USING ERRCODE='P2901'; END IF;
 IF greatest(r.cost_reserved,platform.portfolio_auxiliary_cost(r.workspace_id,r.business_id,r.client_id,r.conversation_id,r.media_pin,r.id))+0.08>(r.config->'limits'->>'cost_budget')::numeric THEN RAISE EXCEPTION 'BUDGET_EXHAUSTED' USING ERRCODE='P2901'; END IF;
 INSERT INTO platform.knowledge_embedding_calls(workspace_id,business_id,kind,run_id,claim_hash,profile_id,request_sha256,request_bytes,input_count,token_ceiling,ticket_hash,state,reserved_at,deadline,portfolio_session_id)
 VALUES(r.workspace_id,r.business_id,'QUERY',r.id,sha256(convert_to(p_claim::text,'UTF8')),'polza_openai_text_embedding3small_1536_cosine_v1',encode(sha256(convert_to(wire,'UTF8')),'hex'),octet_length(wire),1,octet_length(query),sha256(convert_to(ticket::text,'UTF8')),'RESERVED',moment,least(moment+interval '10 seconds',r.deadline,s.expires_at),s.id) RETURNING * INTO ec;
 UPDATE platform.ai_runs SET cost_reserved=greatest(r.cost_reserved,platform.portfolio_auxiliary_cost(r.workspace_id,r.business_id,r.client_id,r.conversation_id,r.media_pin,r.id)) WHERE workspace_id=r.workspace_id AND id=r.id;
 RETURN jsonb_build_object('status','RESERVED','call_id',ec.id,'ticket',ticket,'wire',wire,'wire_sha256',ec.request_sha256,'profile_id',ec.profile_id,'deadline',ec.deadline,'reserved_cost','0.08','currency','RUB');
END $$""",
    "platform.portfolio_query_apply": r"""CREATE OR REPLACE FUNCTION platform.portfolio_query_apply(p_job uuid,p_claim uuid,p_run uuid,p_call uuid,p_ticket uuid,vectors jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE j platform.messaging_jobs%ROWTYPE; r platform.ai_runs%ROWTYPE; ec platform.knowledge_embedding_calls%ROWTYPE; fresh jsonb; query text; wire text; refs jsonb; portfolio jsonb;
BEGIN
 PERFORM platform.turn_require_isolation();j:=platform.messaging_guard(p_job,p_claim);
 SELECT * INTO r FROM platform.ai_runs WHERE workspace_id=j.workspace_id AND job_id=j.id AND id=p_run FOR UPDATE;
 PERFORM pg_advisory_xact_lock(hashtextextended(j.workspace_id::text||':'||r.business_id::text||'|CONFIGURATION_V1',2018));
 SELECT * INTO ec FROM platform.knowledge_embedding_calls WHERE workspace_id=j.workspace_id AND run_id=p_run AND id=p_call FOR UPDATE;
 IF r.id IS NULL OR r.config->>'prompt_revision' NOT IN ('conversation_v5','conversation_v6','conversation_v7','conversation_v8') OR ec.id IS NULL OR ec.kind<>'QUERY' OR ec.state<>'SUCCESS' OR r.calls_used<>0 OR r.result IS NOT NULL OR r.deadline<=clock_timestamp()
  OR p_ticket IS NULL OR ec.ticket_hash IS DISTINCT FROM sha256(convert_to(p_ticket::text,'UTF8')) OR ec.claim_hash IS DISTINCT FROM sha256(convert_to(p_claim::text,'UTF8')) OR ec.portfolio_session_id IS DISTINCT FROM r.portfolio_session_id THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
 fresh:=platform.ai_runtime_current(j,r.snapshot);
 IF fresh->'binding' IS DISTINCT FROM r.binding OR platform.ai_knowledge_current(r) IS NOT TRUE OR platform.knowledge_runtime_current(r) IS NOT TRUE OR platform.portfolio_runtime_current(r) IS NOT TRUE THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
 IF ec.applied_at IS NOT NULL THEN RETURN jsonb_build_object('knowledge',platform.knowledge_projection(r),'portfolio',platform.portfolio_projection(r))||platform.portfolio_runtime_data(r)||CASE WHEN r.config->>'prompt_revision' IN ('conversation_v6','conversation_v7','conversation_v8') THEN jsonb_build_object('delivery_eligible',platform.portfolio_delivery_eligible(r)) ELSE '{}'::jsonb END; END IF;
 IF ec.reserved_at+interval '30 seconds'<=clock_timestamp() OR platform.knowledge_vectors_valid(vectors,1) IS NOT TRUE OR ec.vectors_sha256 IS DISTINCT FROM encode(sha256(convert_to(vectors::text,'UTF8')),'hex') THEN RAISE EXCEPTION 'INVALID_VECTOR' USING ERRCODE='P2901'; END IF;
 query:=platform.portfolio_run_query(r);wire:=platform.portfolio_embedding_wire(jsonb_build_array(query));
 IF ec.request_sha256<>encode(sha256(convert_to(wire,'UTF8')),'hex') THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
 refs:=platform.knowledge_select(r,(vectors->0)::text::extensions.vector(1536),query);
 portfolio:=platform.portfolio_select(r.workspace_id,r.business_id,r.portfolio_pin,(vectors->0)::text::extensions.vector(1536),query);
 UPDATE platform.ai_runs SET search_refs=refs,portfolio_refs=platform.portfolio_refs(portfolio) WHERE workspace_id=r.workspace_id AND id=r.id RETURNING * INTO r;
 UPDATE platform.knowledge_embedding_calls SET query_vector=(vectors->0)::text::extensions.vector(1536),applied_at=clock_timestamp() WHERE id=ec.id;
 IF platform.portfolio_runtime_current(r) IS NOT TRUE THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
 RETURN jsonb_build_object('knowledge',platform.knowledge_projection(r),'portfolio',platform.portfolio_projection(r))||platform.portfolio_runtime_data(r)||CASE WHEN r.config->>'prompt_revision' IN ('conversation_v6','conversation_v7','conversation_v8') THEN jsonb_build_object('delivery_eligible',platform.portfolio_delivery_eligible(r)) ELSE '{}'::jsonb END;
END $$""",
    "platform.portfolio_runtime_read": r"""CREATE OR REPLACE FUNCTION platform.portfolio_runtime_read(p_job uuid,p_claim uuid,p_run uuid,p_pin jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE j platform.messaging_jobs%ROWTYPE; r platform.ai_runs%ROWTYPE; fresh jsonb;
BEGIN
 PERFORM platform.turn_require_isolation();j:=platform.messaging_guard(p_job,p_claim);
 SELECT * INTO r FROM platform.ai_runs WHERE workspace_id=j.workspace_id AND job_id=j.id AND id=p_run FOR UPDATE;
 IF r.id IS NULL OR r.config->>'prompt_revision' NOT IN ('conversation_v5','conversation_v6','conversation_v7','conversation_v8') OR r.result IS NOT NULL OR r.deadline<=clock_timestamp() THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
 fresh:=platform.ai_runtime_current(j,r.snapshot);
 IF fresh->'binding' IS DISTINCT FROM r.binding OR platform.ai_knowledge_current(r) IS NOT TRUE OR platform.knowledge_runtime_current(r) IS NOT TRUE OR platform.portfolio_runtime_current(r) IS NOT TRUE
  OR p_pin IS DISTINCT FROM jsonb_build_object('search_pin',r.search_pin,'portfolio_pin',r.portfolio_pin,'media_pin',r.media_pin) THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
 RETURN jsonb_build_object('knowledge',platform.knowledge_projection(r),'portfolio',platform.portfolio_projection(r))||platform.portfolio_runtime_data(r)||CASE WHEN r.config->>'prompt_revision' IN ('conversation_v6','conversation_v7','conversation_v8') THEN jsonb_build_object('delivery_eligible',platform.portfolio_delivery_eligible(r)) ELSE '{}'::jsonb END;
END $$""",
    "platform.portfolio_delivery_attest": r"""CREATE OR REPLACE FUNCTION platform.portfolio_delivery_attest(j platform.messaging_jobs,r platform.ai_runs,p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE eligible jsonb; ref jsonb; proof jsonb;
BEGIN
 IF r.config->>'prompt_revision' NOT IN ('conversation_v6','conversation_v7','conversation_v8') OR r.reads_used<>1 OR r.calls_used<>1
  OR r.result IS NOT NULL OR r.deadline<=clock_timestamp()
  OR platform.material_object(p,ARRAY['run_id','binding','knowledge_pin','search_pin','portfolio_pin','media_pin','context_sha256','shown_refs']) IS NOT TRUE
  OR p->'binding' IS DISTINCT FROM r.binding OR p->'knowledge_pin' IS DISTINCT FROM r.knowledge_pin
  OR p->'search_pin' IS DISTINCT FROM r.search_pin OR p->'portfolio_pin' IS DISTINCT FROM r.portfolio_pin OR p->'media_pin' IS DISTINCT FROM r.media_pin
  OR jsonb_typeof(p->'context_sha256')<>'string' OR p->>'context_sha256' !~ '^[0-9a-f]{64}$'
  OR jsonb_typeof(p->'shown_refs')<>'array' OR jsonb_array_length(p->'shown_refs')>3
  OR NOT EXISTS(SELECT 1 FROM platform.ai_provider_calls WHERE workspace_id=r.workspace_id AND run_id=r.id AND sequence=1
   AND completed_at IS NOT NULL AND completion->>'kind'='TOOLS' AND claim_hash=sha256(convert_to(j.claim_token::text,'UTF8')) AND attempt_count=j.attempt_count)
 THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
 eligible:=platform.portfolio_delivery_eligible(r);
 IF (SELECT count(DISTINCT v->>'item_id') FROM jsonb_array_elements(p->'shown_refs') x(v))<>jsonb_array_length(p->'shown_refs') THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
 FOR ref IN SELECT v FROM jsonb_array_elements(p->'shown_refs') x(v) LOOP
  IF platform.portfolio_delivery_selection_valid(ref) IS NOT TRUE OR NOT eligible @> jsonb_build_array(ref) THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
 END LOOP;
 proof:=jsonb_build_object('revision','portfolio_delivery_read_v1','context_sha256',p->'context_sha256','shown_refs',p->'shown_refs');
 IF r.delivery_read_audit IS NOT NULL AND r.delivery_read_audit IS DISTINCT FROM proof THEN RAISE EXCEPTION 'IDEMPOTENCY_KEY_CONFLICT' USING ERRCODE='P2001'; END IF;
 IF r.delivery_read_audit IS NULL THEN UPDATE platform.ai_runs SET delivery_read_audit=proof WHERE workspace_id=r.workspace_id AND id=r.id; END IF;
 RETURN jsonb_build_object('recorded',true);
END $$""",
    "platform.portfolio_delivery_intent_current": r"""CREATE OR REPLACE FUNCTION platform.portfolio_delivery_intent_current(j platform.messaging_jobs,d platform.ai_deliveries,r platform.ai_runs,p platform.portfolio_delivery_intents) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
 IF j.kind<>'SEND_AI_PHOTO' OR r.config->>'prompt_revision' NOT IN ('conversation_v6','conversation_v7','conversation_v8') OR r.config->>'schema_revision'<>(CASE WHEN r.config->>'prompt_revision'='conversation_v8' THEN 'conversation_result_v4'
                 WHEN r.config->>'prompt_revision'='conversation_v7' THEN 'conversation_result_v3' ELSE 'conversation_result_v2' END)
  OR d.selected_kind<>'portfolio_photo' OR d.provider_session_id IS NOT NULL OR r.result->>'kind'<>'portfolio_photo'
  OR (p.workspace_id,p.business_id,p.run_id,p.conversation_id,p.client_id,p.connection_id,p.message_id,p.outbox_id,p.send_job_id,p.caption,p.context_sha256) IS DISTINCT FROM
     (r.workspace_id,r.business_id,r.id,r.conversation_id,r.client_id,r.connection_id,d.message_id,d.outbox_id,j.id,r.result->>'caption',r.delivery_read_audit->>'context_sha256')
  OR r.result->'selection' IS DISTINCT FROM jsonb_build_object('item_id',p.item_id,'revision_id',p.revision_id,'asset_version_id',p.asset_version_id,'source_sha256',p.source_sha256)
 THEN RETURN false; END IF;
 RETURN platform.ai_delivery_current(j,d,r) AND platform.portfolio_runtime_current(r) AND platform.portfolio_delivery_source(r,r.result->'selection');
EXCEPTION WHEN SQLSTATE 'P2001' THEN
 IF SQLERRM='AI_STALE' THEN RETURN false; END IF;
 RAISE;
END $$""",
    "platform.intake_current": r"""CREATE OR REPLACE FUNCTION platform.intake_current(r platform.ai_runs) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
 IF r.config->>'prompt_revision' NOT IN ('conversation_v7','conversation_v8') THEN RETURN true; END IF;
 RETURN r.intake_pin=platform.intake_runtime_pin(r.workspace_id,r.business_id,r.conversation_id,r.client_id);
END $$""",
    "platform.intake_apply": r"""CREATE OR REPLACE FUNCTION platform.intake_apply(r platform.ai_runs,p jsonb) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE projection jsonb; service jsonb; sources jsonb; facts jsonb; f jsonb; old jsonb; fact jsonb; source jsonb; pin jsonb; selected_service_id text;
BEGIN
 IF r.config->>'prompt_revision' NOT IN ('conversation_v7','conversation_v8') THEN RETURN; END IF;
 IF platform.intake_candidates_valid(p) IS NOT TRUE OR platform.intake_current(r) IS NOT TRUE THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
 projection:=platform.intake_project(r.workspace_id,r.business_id,r.conversation_id,r.client_id);
 IF r.search_refs->>'status'='CONFLICT' AND (p->>'category'<>'OTHER_COMPLEX'
  OR p->>'service_id' IS DISTINCT FROM projection->>'service_id'
  OR p->'switch_request' IS DISTINCT FROM 'false'::jsonb OR p->'facts' IS DISTINCT FROM '[]'::jsonb) THEN
  RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
 IF p->>'category'='FAQ_ONLY' THEN RETURN; END IF;
 SELECT x INTO service FROM jsonb_array_elements(r.active_projection->'bundle'->'services') x WHERE x->>'id'=p->>'service_id' AND x->>'active'='true';
 IF p->>'service_id' IS NOT NULL AND service IS NULL OR p->>'service_id' IS NULL AND p->>'category' NOT IN ('AMBIGUOUS','COVER_UP','OTHER_COMPLEX')
  OR p->'facts'<>'[]'::jsonb AND platform.intake_template(service) IS NOT TRUE THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
 IF projection->>'service_id' IS NOT NULL AND p->>'service_id' IS DISTINCT FROM projection->>'service_id' AND p->>'switch_request'<>'true' AND p->>'category'<>'AMBIGUOUS' THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
 selected_service_id:=p->>'service_id';
 facts:=projection->'facts';
 IF p->>'category'='AMBIGUOUS' THEN
  selected_service_id:=projection->>'service_id';
 ELSIF p->>'switch_request'='true' THEN
  IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(p->'facts') x WHERE x->>'status'='client-stated') THEN
   RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001';
  END IF;
  facts:='[]';
 END IF;
 sources:=platform.intake_turn_sources(r.snapshot,projection->'sources');
 FOR f IN SELECT value FROM jsonb_array_elements(p->'facts') LOOP
  SELECT x INTO source FROM jsonb_array_elements(sources) x WHERE x->'message_id'=f->'source'->'message_id' AND x->'source_version'=f->'source'->'source_version';
  IF source IS NULL THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
  IF f->>'status'='client-stated' AND (f->'source'->>'analysis_id' IS NOT NULL OR length(f->'source'->>'quote')=0
   OR position(f->'source'->>'quote' IN source->>'text')=0 OR position(f->>'value' IN f->'source'->>'quote')=0) THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
  IF f->>'status'='observed' AND (f->>'field' IN ('approximate_size','placement') OR f->'source'->>'analysis_id' IS NULL
   OR f->'source'->>'message_id' IS DISTINCT FROM r.media_pin->>'message_id' OR f->'source'->>'analysis_id' IS DISTINCT FROM r.media_pin->>'analysis_id' OR f->'source'->>'analysis_sha256' IS DISTINCT FROM r.media_pin->>'analysis_sha256') THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
  SELECT x INTO old FROM jsonb_array_elements(facts) x WHERE x->'field'=f->'field';
  IF old IS NOT NULL AND old->'value'=f->'value'
   AND (old->>'status'<>'observed' OR old->>'conflict'='true' OR f->>'status'='observed') THEN
   IF NOT (old->>'conflict'='true' AND f->>'status'='client-stated' AND f->>'explicit_correction'='true'
    AND (old->'source'->>'message_id' IS DISTINCT FROM f->'source'->>'message_id')) THEN CONTINUE; END IF;
   IF old->>'status'='owner-confirmed' THEN
    -- Keep the confirmation and its source. The run retains the clarification.
    SELECT jsonb_agg(CASE WHEN x->'field'=f->'field' THEN x||jsonb_build_object('conflict',false) ELSE x END ORDER BY ordinal)
    INTO facts FROM jsonb_array_elements(facts) WITH ORDINALITY t(x,ordinal);
    CONTINUE;
   END IF;
  END IF;
  IF old IS NOT NULL AND old->'value' IS DISTINCT FROM f->'value'
   AND (f->>'explicit_correction'<>'true' OR (old->>'conflict'='true' AND f->>'status'='observed')) THEN
   SELECT coalesce(jsonb_agg(CASE WHEN x->'field'=f->'field' THEN x||jsonb_build_object('conflict',true) ELSE x END),'[]') INTO facts FROM jsonb_array_elements(facts) x;
  ELSE
   fact:=(f-'explicit_correction')||jsonb_build_object('confirmed_by',NULL,'conflict',false);
   SELECT coalesce(jsonb_agg(x),'[]') INTO facts FROM jsonb_array_elements(facts) x WHERE x->'field'<>f->'field';facts:=facts||jsonb_build_array(fact);
  END IF;
 END LOOP;
 pin:=jsonb_build_object('release_id',projection->'release_id','activation_version',projection->'activation_version','control_generation',projection->'control_generation');
 INSERT INTO platform.intake_state(workspace_id,business_id,conversation_id,client_id,service_id,pin,category,facts)
 VALUES(r.workspace_id,r.business_id,r.conversation_id,r.client_id,selected_service_id,pin,p->>'category',facts)
 ON CONFLICT(workspace_id,conversation_id) DO UPDATE
 SET service_id=excluded.service_id,pin=excluded.pin,category=excluded.category,facts=excluded.facts,version=platform.intake_state.version+1
 WHERE (platform.intake_state.service_id,platform.intake_state.pin,platform.intake_state.category,platform.intake_state.facts)
  IS DISTINCT FROM (excluded.service_id,excluded.pin,excluded.category,excluded.facts);
END $$""",
    "platform.intake_delivery_guard": r"""CREATE OR REPLACE FUNCTION platform.intake_delivery_guard(r platform.ai_runs) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE p jsonb;
BEGIN
 IF r.config->>'prompt_revision' NOT IN ('conversation_v7','conversation_v8') OR r.result->'intake'->>'category'='FAQ_ONLY' THEN RETURN; END IF;
 p:=platform.intake_project(r.workspace_id,r.business_id,r.conversation_id,r.client_id);
 IF r.config->>'prompt_revision'='conversation_v8' AND r.result ? 'intents' THEN
   IF p->>'status' IS DISTINCT FROM 'PRELIMINARILY_COMPLETE' OR p->>'category' IS DISTINCT FROM 'NEW_TATTOO' THEN
     RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
   RETURN;
 END IF;
 IF p->>'status'='OWNER_HANDOFF' AND r.result->>'kind'<>'handoff'
  OR p->>'status'='CLARIFY' AND (r.result->>'kind'<>'reply' OR r.result->>'text' IS DISTINCT FROM p->>'question')
  OR p->>'status'='PRELIMINARILY_COMPLETE' AND (r.result->>'kind' NOT IN ('reply','portfolio_photo') OR r.result->>'kind'='reply' AND r.result->>'text'<>'Предварительные сведения собраны. Мастер проверит детали; цена, длительность и запись пока не согласованы.') THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
END $$""",
    "platform.intake_escalation_decorate": r"""CREATE OR REPLACE FUNCTION platform.intake_escalation_decorate(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE link platform.intake_escalation_links%ROWTYPE; fresh boolean; client_question text;
BEGIN
 SELECT * INTO link FROM platform.intake_escalation_links WHERE workspace_id=(p->>'workspace_id')::uuid AND escalation_id=(p->>'escalation_id')::uuid;
 IF NOT FOUND THEN RETURN p; END IF;
 PERFORM platform.knowledge_owner_lock(link.business_id);
 fresh:=link.pin=platform.intake_runtime_pin(link.workspace_id,link.business_id,link.conversation_id,link.client_id);
 IF fresh AND p->>'validity'='CURRENT' THEN
  -- Show the current inbound text captured by the run that opened this card.
  SELECT nullif(btrim(left(platform.knowledge_query_text(r),300)),'') INTO client_question
  FROM app.escalations e JOIN platform.ai_runs r ON (r.workspace_id,r.job_id)=(e.workspace_id,e.source_job_id)
  WHERE (e.workspace_id,e.id)=(link.workspace_id,link.escalation_id)
   AND (r.business_id,r.conversation_id,r.client_id)=(link.business_id,link.conversation_id,link.client_id)
   AND r.config->>'prompt_revision' IN ('conversation_v7','conversation_v8') AND r.result->>'kind'='handoff'
   AND r.search_refs->>'status'='CONFLICT' AND r.search_refs->>'reason_code'='OWNER_LABEL_CONFLICT';
 END IF;
 RETURN p||jsonb_build_object('policy','PRELIMINARY_INTAKE_OWNER_V1','question',coalesce(client_question,link.summary->>'question'),'summary',CASE WHEN fresh THEN link.summary END,'summary_current',fresh,'validity',CASE WHEN NOT fresh AND p->>'validity'='CURRENT' THEN 'SOURCE_CHANGED' ELSE p->>'validity' END,'waiting',CASE WHEN fresh THEN p->>'waiting' END,'context_hold',CASE WHEN fresh THEN p->'context_hold' END,'can_resolve',fresh AND (p->>'can_resolve')::boolean);
END $$""",
    "platform.portfolio_session_admit": r"""CREATE OR REPLACE FUNCTION platform.portfolio_session_admit(business uuid,conversation uuid,p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE ws uuid:=platform.knowledge_owner_lock(business); actor uuid:=nullif(current_setting('asm.actor_id',true),'')::uuid; c app.conversations%ROWTYPE; s platform.portfolio_ai_sessions%ROWTYPE; moment timestamptz:=clock_timestamp();
BEGIN
 IF current_database() NOT IN ('asm_local','asm_test') OR platform.material_object(p,ARRAY['profile_id','execution','eligibility','max_calls','max_cost','duration_seconds']) IS NOT TRUE
   OR p->>'profile_id' NOT IN ('SYNTHETIC_VISION_PORTFOLIO_V1','SYNTHETIC_PORTFOLIO_PHOTO_V1','SYNTHETIC_INTAKE_V1','SYNTHETIC_SERVICE_INTENTS_V1')
   OR (p->>'profile_id'='SYNTHETIC_SERVICE_INTENTS_V1' AND (current_database()<>'asm_test' OR conversation IS NULL)) OR p->>'execution' IS DISTINCT FROM 'CONTROLLED' OR p->>'eligibility' IS DISTINCT FROM 'EVAL_ONLY'
   OR jsonb_typeof(p->'max_calls') IS DISTINCT FROM 'number' OR p->>'max_calls' !~ '^[1-4]$'
   OR jsonb_typeof(p->'max_cost') IS DISTINCT FROM 'string' OR p->>'max_cost' !~ '^(0|[1-9][0-9]?)([.][0-9]{1,9})?$' OR (p->>'max_cost')::numeric<=0 OR (p->>'max_cost')::numeric>10
   OR jsonb_typeof(p->'duration_seconds') IS DISTINCT FROM 'number' OR p->>'duration_seconds' !~ '^[1-9][0-9]{0,2}$' OR (p->>'duration_seconds')::integer>900 THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2901'; END IF;
 IF conversation IS NOT NULL THEN
  SELECT * INTO c FROM app.conversations WHERE workspace_id=ws AND business_id=business AND id=conversation;
  IF c.id IS NULL THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P2901'; END IF;
 END IF;
 INSERT INTO platform.portfolio_ai_sessions(workspace_id,business_id,actor_user_account_id,conversation_id,client_id,profile_id,execution,eligibility,max_calls,max_cost,created_at,expires_at)
 VALUES(ws,business,actor,conversation,c.client_id,p->>'profile_id',p->>'execution',p->>'eligibility',(p->>'max_calls')::integer,(p->>'max_cost')::numeric,moment,moment+(p->>'duration_seconds')::integer*interval '1 second') RETURNING * INTO s;
 RETURN jsonb_build_object('workspace_id',ws,'business_id',business,'session_id',s.id,'conversation_id',conversation,'client_id',c.client_id,'expires_at',s.expires_at,'max_calls',s.max_calls,'max_cost',s.max_cost::text);
END $$""",
    "platform.intake_delivery_session_lock": r"""CREATE OR REPLACE FUNCTION platform.intake_delivery_session_lock(ws uuid,business uuid,session uuid,reservation numeric) RETURNS platform.portfolio_ai_sessions
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE s platform.portfolio_ai_sessions%ROWTYPE; u jsonb; actor uuid:=nullif(current_setting('asm.actor_id',true),'')::uuid;
BEGIN
 SELECT * INTO s FROM platform.portfolio_ai_sessions WHERE workspace_id=ws AND business_id=business AND id=session FOR UPDATE;
 IF current_database() NOT IN ('asm_local','asm_test') OR s.id IS NULL OR s.execution<>'CONTROLLED' OR s.eligibility<>'EVAL_ONLY' OR s.profile_id NOT IN ('SYNTHETIC_PORTFOLIO_PHOTO_V1','SYNTHETIC_INTAKE_V1','SYNTHETIC_SERVICE_INTENTS_V1')
   OR s.revoked_at IS NOT NULL OR s.expires_at<=clock_timestamp() OR reservation<0 OR reservation>3.89
   OR NOT EXISTS(SELECT 1 FROM platform.workspaces w
    JOIN platform.workspace_memberships wm ON wm.workspace_id=w.id AND wm.user_account_id=s.actor_user_account_id
    JOIN platform.user_accounts ua ON ua.id=wm.user_account_id
    WHERE w.id=s.workspace_id AND w.status='ACTIVE' AND ua.status='ACTIVE' AND wm.role='OWNER' AND wm.status='ACTIVE') THEN RAISE EXCEPTION 'SESSION_NOT_ALLOWED' USING ERRCODE='P2901'; END IF;
 IF actor IS NOT NULL AND s.actor_user_account_id<>actor THEN RAISE EXCEPTION 'ACCESS_DENIED' USING ERRCODE='P2901'; END IF;
 u:=platform.portfolio_session_usage(ws,business,session);
 IF (u->>'calls')::integer>=s.max_calls OR (u->>'held_cost')::numeric+reservation>s.max_cost THEN RAISE EXCEPTION 'BUDGET_EXHAUSTED' USING ERRCODE='P2901'; END IF;
 RETURN s;
END $$""",
    "platform.ai_provider_session": r"""CREATE OR REPLACE FUNCTION platform.ai_provider_session(p jsonb,p_enable boolean) RETURNS jsonb
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
    OR (platform.service_intent_schema_profile()->>'valid')::boolean IS NOT TRUE THEN
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
    "platform.human_context_policy_command": r"""CREATE OR REPLACE FUNCTION platform.human_context_policy_command(ws uuid,p_connection uuid,p_operation text,p_key text,
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
          OR jsonb_typeof(p_profile->'schema_revision')<>'string' OR p_profile->>'schema_revision'<>'0031'
          OR jsonb_typeof(p_profile->'profile_sha256')<>'string' OR p_profile->>'profile_sha256' !~ '^[0-9a-f]{64}$'
          OR p_profile->'drain_confirmed' IS DISTINCT FROM 'true'::jsonb THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2601'; END IF;
        SELECT platform.service_intent_schema_profile() INTO profile;
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
        SELECT platform.service_intent_schema_profile() INTO profile;
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
}

AGENT_INTENT_TABLE = """
CREATE TABLE platform.service_request_agent_intents (
  workspace_id uuid NOT NULL,
  run_id uuid NOT NULL,
  actor_kind text NOT NULL DEFAULT 'AI_AGENT' CHECK(actor_kind='AI_AGENT'),
  owner_user_account_id uuid NOT NULL,
  source_message_id uuid NOT NULL,
  request_id uuid NOT NULL,
  request_revision bigint NOT NULL CHECK(request_revision>0),
  prepare_requested boolean NOT NULL,
  approval_requested boolean NOT NULL,
  approval_id uuid,
  quote_id uuid,
  quote_input jsonb,
  transaction_id xid8 NOT NULL,
  lease_until timestamptz NOT NULL,
  phase text NOT NULL CHECK(phase IN ('ASSESS','QUOTE','DONE')),
  PRIMARY KEY(workspace_id,run_id),
  FOREIGN KEY(workspace_id,run_id) REFERENCES platform.ai_runs(workspace_id,id),
  FOREIGN KEY(workspace_id,owner_user_account_id)
    REFERENCES platform.workspace_memberships(workspace_id,user_account_id),
  FOREIGN KEY(workspace_id,source_message_id) REFERENCES app.messages(workspace_id,id),
  FOREIGN KEY(workspace_id,request_id) REFERENCES app.service_requests(workspace_id,id),
  FOREIGN KEY(workspace_id,approval_id) REFERENCES app.approval_requests(workspace_id,id),
  FOREIGN KEY(workspace_id,quote_id) REFERENCES app.quotes(workspace_id,id),
  CHECK(prepare_requested OR approval_requested),
  CHECK(phase='QUOTE' OR quote_input IS NULL),
  CHECK(phase='DONE' OR quote_id IS NULL),
  CHECK(approval_requested OR approval_id IS NULL)
)
"""

AGENT_DOMAIN_FUNCTIONS = {
    "platform.service_request_agent_pin(platform.ai_runs)": r"""
CREATE FUNCTION platform.service_request_agent_pin(r platform.ai_runs)
RETURNS text LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
  SELECT platform.quote_hash(coalesce(jsonb_agg(jsonb_build_array(d.id,d.revision) ORDER BY d.id),'[]'))
  FROM app.service_requests d
  WHERE (d.workspace_id,d.business_id,d.conversation_id,d.client_id)
    =(r.workspace_id,r.business_id,r.conversation_id,r.client_id)
$$""",
    "platform.service_request_agent_source_available(app.conversations,uuid,uuid)": r"""
CREATE FUNCTION platform.service_request_agent_source_available(
  c app.conversations,p_request uuid,p_message uuid
) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
  SELECT NOT EXISTS(
    SELECT 1 FROM app.service_requests d
    WHERE (d.workspace_id,d.business_id,d.conversation_id,d.client_id)
      =(c.workspace_id,c.business_id,c.id,c.client_id) AND d.id IS DISTINCT FROM p_request
      AND (d.intent_message_id=p_message OR EXISTS(
        SELECT 1 FROM jsonb_array_elements(d.facts) f
        WHERE f->'source'->>'message_id'=p_message::text
      ) OR d.complex_work->'source'->>'message_id'=p_message::text)
  )
$$""",
    "platform.service_request_agent_mentions(text,text)": r"""
CREATE FUNCTION platform.service_request_agent_mentions(message text,idea text)
RETURNS boolean LANGUAGE sql IMMUTABLE STRICT SET search_path=pg_catalog,pg_temp AS $$
  SELECT length(trim(regexp_replace(idea COLLATE pg_catalog.pg_c_utf8,'[^[:alnum:]]+',' ','g')))>=2
    AND position(
      ' '||trim(regexp_replace(lower(idea COLLATE pg_catalog.pg_c_utf8),'[^[:alnum:]]+',' ','g'))||' '
      IN ' '||trim(regexp_replace(lower(message COLLATE pg_catalog.pg_c_utf8),'[^[:alnum:]]+',' ','g'))||' '
    )>0
$$""",
    "platform.service_request_agent_prepare(platform.ai_runs,app.conversations,jsonb,boolean)": r"""
CREATE FUNCTION platform.service_request_agent_prepare(
  r platform.ai_runs,c app.conversations,p jsonb,p_prepare boolean
) RETURNS app.service_requests
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE
  source jsonb:=p->'intents'->0->'source';
  projection jsonb; source_message app.messages%ROWTYPE;
  anchor app.messages%ROWTYPE; next_anchor app.messages%ROWTYPE;
  d app.service_requests%ROWTYPE; source_text text; fact jsonb; fact_message app.messages%ROWTYPE;
  intent_source jsonb; fields jsonb; target_ids uuid[]; saved_request uuid;
  new_work boolean; has_work boolean; explicit_reference boolean;
  work_prefix constant text:='^[[:space:]]*((хочу|и)[[:space:]]+)?(отдельн(ая|ую)[[:space:]]+(татуировк(а|у)|работ(а|у))|ещ[её][[:space:]]+одн(а|у)[[:space:]]+(татуировк(а|у)|работ(а|у))|втор(ая|ую)[[:space:]]+(татуировк(а|у)|работ(а|у))|separate tattoo|second tattoo|another tattoo)([^[:alnum:]]|$)';
BEGIN
  IF platform.intake_source_current(c.workspace_id,c.business_id,c.id,c.client_id,source) IS NOT TRUE
    THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
  SELECT m.* INTO source_message FROM app.messages m
    JOIN app.conversation_turn_messages tm ON (tm.workspace_id,tm.message_id)=(m.workspace_id,m.id)
    WHERE (m.workspace_id,m.conversation_id,m.connection_id,m.id,tm.turn_id)
      =(c.workspace_id,c.id,c.connection_id,(source->>'message_id')::uuid,r.turn_id)
      AND m.direction='INBOUND';
  IF NOT FOUND THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
  source_text:=platform.message_effective(c.workspace_id,source_message.id)->>'text';
  projection:=platform.intake_project(c.workspace_id,c.business_id,c.id,c.client_id);
  IF source_text IS NULL OR projection->>'category' IN ('FAQ_ONLY','AMBIGUOUS')
    OR projection->>'service_id' IS NULL OR projection->>'template_revision' IS NULL
    OR projection->'release_id' IS DISTINCT FROM r.active_projection->'release_id'
    OR projection->'activation_version' IS DISTINCT FROM r.active_projection->'activation_version'
    OR projection->'conflicts'<>'[]'::jsonb THEN RETURN NULL; END IF;

  SELECT count(*)>0, array_agg(x.id) FILTER (WHERE x.intent_message_id=source_message.id OR EXISTS (
    SELECT 1 FROM jsonb_array_elements(x.facts) f WHERE f->>'field'='idea' AND f->>'conflict'='false'
      AND platform.intake_source_current(c.workspace_id,c.business_id,c.id,c.client_id,f->'source')
      AND platform.service_request_agent_mentions(source_text,f->>'value')
  )) INTO has_work,target_ids
  FROM app.service_requests x
  WHERE (x.workspace_id,x.business_id,x.conversation_id,x.client_id)
    =(c.workspace_id,c.business_id,c.id,c.client_id);

  new_work:=has_work AND coalesce(p->'intake'->>'switch_request'='true',false)
    AND source_text COLLATE pg_catalog.pg_c_utf8 ~* work_prefix;
  IF new_work THEN target_ids:=NULL; END IF;
  IF coalesce(cardinality(target_ids),0)>1 THEN RETURN NULL; END IF;
  IF target_ids IS NOT NULL THEN
    SELECT * INTO STRICT d FROM app.service_requests WHERE (workspace_id,id)=(c.workspace_id,target_ids[1])
      FOR NO KEY UPDATE;
    IF d.service_id IS DISTINCT FROM projection->>'service_id' OR EXISTS(
      SELECT 1 FROM app.quote_acceptances a WHERE (a.workspace_id,a.request_id)=(d.workspace_id,d.id)
    ) THEN RETURN NULL; END IF;
    intent_source:=jsonb_build_object('message_id',d.intent_message_id,'source_version',d.intent_source_version);
  ELSIF p_prepare AND (NOT has_work OR new_work) THEN
    SELECT jsonb_build_object('message_id',f->'source'->'message_id','source_version',f->'source'->'source_version')
      INTO intent_source FROM jsonb_array_elements(projection->'facts') f
      WHERE f->>'field'='idea' AND f->>'status'='client-stated' AND f->>'conflict'='false'
        AND (NOT new_work OR f->'source'->>'message_id'=source_message.id::text);
    IF intent_source IS NULL OR NOT EXISTS(
      SELECT 1 FROM jsonb_array_elements(projection->'facts') f WHERE f->'source'->>'message_id'=source_message.id::text
    ) THEN RETURN NULL; END IF;
  ELSE RETURN NULL;
  END IF;

  IF platform.intake_source_current(c.workspace_id,c.business_id,c.id,c.client_id,intent_source) IS NOT TRUE
    THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
  SELECT * INTO STRICT anchor FROM app.messages WHERE (workspace_id,id)=(c.workspace_id,(intent_source->>'message_id')::uuid);
  SELECT m.* INTO next_anchor FROM app.service_requests x
    JOIN app.messages m ON (m.workspace_id,m.id)=(x.workspace_id,x.intent_message_id)
    WHERE (x.workspace_id,x.business_id,x.conversation_id,x.client_id)
      =(c.workspace_id,c.business_id,c.id,c.client_id)
      AND (m.created_at,m.id)>(anchor.created_at,anchor.id)
    ORDER BY m.created_at,m.id LIMIT 1;

  -- A later source needs an explicit reference to this work if another work
  -- has started since its anchor. An exact match is resolved above under lock.
  explicit_reference:=d.id IS NOT NULL AND source_message.id<>anchor.id;
  IF (source_message.created_at,source_message.id)<(anchor.created_at,anchor.id)
    OR (next_anchor.id IS NOT NULL AND (source_message.created_at,source_message.id)>=(next_anchor.created_at,next_anchor.id)
      AND NOT explicit_reference)
    OR platform.service_request_agent_source_available(c,d.id,source_message.id) IS NOT TRUE
    THEN RETURN NULL; END IF;

  FOR fact IN SELECT value FROM jsonb_array_elements(projection->'facts') LOOP
    IF fact->>'conflict' IS DISTINCT FROM 'false'
      OR platform.intake_source_current(c.workspace_id,c.business_id,c.id,c.client_id,fact->'source') IS NOT TRUE
      THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
    SELECT * INTO STRICT fact_message FROM app.messages
      WHERE (workspace_id,id)=(c.workspace_id,(fact->'source'->>'message_id')::uuid);
    IF platform.service_request_agent_source_available(c,d.id,fact_message.id) IS NOT TRUE
      OR (fact_message.created_at,fact_message.id)<(anchor.created_at,anchor.id)
      OR (next_anchor.id IS NOT NULL AND (fact_message.created_at,fact_message.id)>=(next_anchor.created_at,next_anchor.id)
        AND NOT (explicit_reference AND fact_message.id=source_message.id
          OR d.facts @> jsonb_build_array(jsonb_set(fact,'{source,quote}','""'))))
      THEN RETURN NULL; END IF;
  END LOOP;

  IF d.id IS NOT NULL AND EXISTS(
    SELECT 1 FROM jsonb_array_elements(d.facts) f
    WHERE platform.intake_source_current(c.workspace_id,c.business_id,c.id,c.client_id,f->'source') IS NOT TRUE
      AND (NOT p_prepare OR NOT EXISTS(
        SELECT 1 FROM jsonb_array_elements(projection->'facts') fresh WHERE fresh->'field'=f->'field'
      ))
  ) THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
  IF d.complex_work IS NOT NULL AND platform.intake_source_current(
    c.workspace_id,c.business_id,c.id,c.client_id,d.complex_work->'source'
  ) IS NOT TRUE THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;

  IF NOT p_prepare THEN RETURN d; END IF;
  IF d.id IS NULL THEN
    SELECT coalesce(jsonb_agg(f->'field' ORDER BY f->>'field'),'[]') INTO fields
      FROM jsonb_array_elements(projection->'facts') f;
    saved_request:=(platform.service_request_create_scoped(c,NULL,NULL,NULL,jsonb_build_object(
      'expected_version',projection->'version','expected_fingerprint',projection->'fingerprint',
      'intent_source',intent_source,'fields',fields,'selection','ONE_WORK'
    ))->>'request_id')::uuid;
    SELECT * INTO STRICT d FROM app.service_requests WHERE (workspace_id,id)=(c.workspace_id,saved_request);
    RETURN d;
  END IF;
  FOR fact IN SELECT value FROM jsonb_array_elements(projection->'facts') LOOP
    IF d.facts @> jsonb_build_array(jsonb_set(fact,'{source,quote}','""')) THEN CONTINUE; END IF;
    PERFORM platform.service_request_revise_scoped(c,NULL,NULL,d.id,NULL,jsonb_build_object(
      'expected_revision',d.revision::text,'expected_version',projection->'version',
      'expected_fingerprint',projection->'fingerprint','field',fact->'field',
      'source',jsonb_build_object('message_id',fact->'source'->'message_id','source_version',fact->'source'->'source_version'),
      'selection','ONE_WORK'
    ));
    SELECT * INTO STRICT d FROM app.service_requests WHERE (workspace_id,id)=(c.workspace_id,d.id);
  END LOOP;
  IF projection->>'category' IN ('COVER_UP','OTHER_COMPLEX')
    AND platform.service_request_complex_work(c,d.id,d.service_id,jsonb_build_array(source)) IS NOT NULL THEN
    PERFORM platform.service_request_revise_scoped(c,NULL,NULL,d.id,NULL,jsonb_build_object(
      'expected_revision',d.revision::text,'expected_version',projection->'version',
      'expected_fingerprint',projection->'fingerprint','field',NULL,'source',source,'selection','ONE_WORK'
    ));
    SELECT * INTO STRICT d FROM app.service_requests WHERE (workspace_id,id)=(c.workspace_id,d.id);
  END IF;
  RETURN d;
END $$""",
    "platform.service_request_agent_begin(platform.ai_runs,platform.messaging_jobs,jsonb)": r"""
CREATE FUNCTION platform.service_request_agent_begin(
  r platform.ai_runs,j platform.messaging_jobs,p jsonb
) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE c app.conversations%ROWTYPE; d app.service_requests%ROWTYPE; owner_id uuid;
  prepare boolean; approval boolean; session_expiry timestamptz;
BEGIN
  IF p->'intents' IS NULL OR p->'intents'='[]'::jsonb THEN RETURN; END IF;
  IF r.config->>'prompt_revision' IS DISTINCT FROM 'conversation_v8'
    OR r.config->'route'->>'execution' IS DISTINCT FROM 'FAKE' OR current_database()<>'asm_test'
    OR p->>'kind' IS DISTINCT FROM 'no_reply' OR p->'text' IS DISTINCT FROM 'null'::jsonb
    OR (r.workspace_id,r.job_id,r.turn_id,r.connection_id) IS DISTINCT FROM (j.workspace_id,j.id,j.turn_id,j.connection_id)
    OR r.service_request_pin IS DISTINCT FROM platform.service_request_agent_pin(r)
    THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
  PERFORM platform.messaging_guard(j.id,j.claim_token);
  SELECT * INTO STRICT c FROM app.conversations WHERE (workspace_id,business_id,id,client_id,connection_id)
    =(r.workspace_id,r.business_id,r.conversation_id,r.client_id,r.connection_id) FOR NO KEY UPDATE;
  SELECT a.actor_user_account_id INTO STRICT owner_id FROM platform.conversation_control_receipts a
    WHERE (a.workspace_id,a.id,a.conversation_id,a.client_id,a.accepted_generation)
      =(r.workspace_id,r.resume_receipt_id,c.id,c.client_id,c.control_generation)
      AND a.operation='RESUME' AND a.accepted_mode='AI';
  IF c.control_mode<>'AI' OR c.control_generation<>r.control_generation
    OR platform.messaging_lock_owner(c.workspace_id,owner_id) IS NOT TRUE OR NOT EXISTS(
      SELECT 1 FROM app.channel_connections cc WHERE (cc.workspace_id,cc.id,cc.business_id)
        =(c.workspace_id,c.connection_id,c.business_id) AND cc.provider='CONTROLLED' AND cc.status='ACTIVE'
    ) THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
  SELECT s.expires_at INTO session_expiry FROM platform.portfolio_ai_sessions s
    WHERE (s.workspace_id,s.id,s.business_id,s.conversation_id,s.client_id,s.actor_user_account_id)
      =(r.workspace_id,r.portfolio_session_id,r.business_id,r.conversation_id,r.client_id,owner_id)
      AND s.profile_id='SYNTHETIC_SERVICE_INTENTS_V1' AND s.execution='CONTROLLED' AND s.eligibility='EVAL_ONLY'
      AND s.revoked_at IS NULL AND s.expires_at>clock_timestamp() FOR SHARE;
  IF NOT FOUND THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
  prepare:=p->'intents'->0->>'name'='prepare_service_request';
  approval:=p->'intents'->(jsonb_array_length(p->'intents')-1)->>'name'='request_owner_decision';
  d:=platform.service_request_agent_prepare(r,c,p,prepare);
  IF d.id IS NULL THEN RAISE EXCEPTION 'AI_INTENT_AMBIGUOUS' USING ERRCODE='P2001'; END IF;
  INSERT INTO platform.service_request_agent_intents(
    workspace_id,run_id,owner_user_account_id,source_message_id,request_id,request_revision,
    prepare_requested,approval_requested,transaction_id,lease_until,phase)
  VALUES(r.workspace_id,r.id,owner_id,(p->'intents'->0->'source'->>'message_id')::uuid,d.id,d.revision,
    prepare,approval,pg_current_xact_id(),least(j.lease_until,session_expiry),'ASSESS');
EXCEPTION WHEN SQLSTATE 'P3101' THEN
  RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001';
END $$""",
    "platform.service_request_agent_result(platform.ai_runs)": r"""
CREATE FUNCTION platform.service_request_agent_result(r platform.ai_runs)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
  SELECT jsonb_build_object('request_id',x.request_id,'approval_id',x.approval_id,'quote_id',x.quote_id)
  FROM platform.service_request_agent_intents x
  WHERE (x.workspace_id,x.run_id)=(r.workspace_id,r.id) AND x.phase='DONE'
$$""",
    "platform.service_request_agent_continue(uuid,uuid,uuid,text,jsonb)": r"""
CREATE FUNCTION platform.service_request_agent_continue(
  p_job uuid,p_claim uuid,p_run uuid,p_step text,p_payload jsonb
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE a platform.service_request_agent_intents%ROWTYPE; r platform.ai_runs%ROWTYPE;
  d app.service_requests%ROWTYPE; j platform.messaging_jobs%ROWTYPE; prepared_quote jsonb;
  approval jsonb; chosen_approval uuid; current_basis jsonb; saved jsonb; saved_quote_id uuid;
BEGIN
  PERFORM platform.turn_require_isolation();
  SELECT ar.* INTO r FROM platform.ai_runs ar WHERE ar.job_id=p_job AND ar.id=p_run;
  SELECT * INTO a FROM platform.service_request_agent_intents WHERE (workspace_id,run_id)=(r.workspace_id,r.id) FOR UPDATE;
  IF a.run_id IS NULL OR current_setting('asm.actor_kind',true) IS DISTINCT FROM 'worker_job'
    OR coalesce(current_setting('asm.actor_id',true),'')<>''
    OR current_setting('asm.job_id',true) IS DISTINCT FROM p_job::text
    OR current_setting('asm.claim_token',true) IS DISTINCT FROM p_claim::text
    OR current_setting('asm.workspace_id',true) IS DISTINCT FROM r.workspace_id::text
    OR current_setting('asm.connection_id',true) IS DISTINCT FROM r.connection_id::text
    OR current_setting('asm.context_xid',true) IS DISTINCT FROM a.transaction_id::text
    OR pg_current_xact_id_if_assigned() IS DISTINCT FROM a.transaction_id
    OR a.lease_until<=clock_timestamp() OR r.deadline<=clock_timestamp()
    OR r.config->>'prompt_revision' IS DISTINCT FROM 'conversation_v8'
    OR r.result->>'kind' IS DISTINCT FROM 'no_reply'
    OR r.winning_claim_hash IS DISTINCT FROM sha256(convert_to(p_claim::text,'UTF8'))
    THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
  SELECT * INTO STRICT j FROM platform.messaging_jobs WHERE (workspace_id,id)=(r.workspace_id,p_job);
  IF j.status<>'SUCCEEDED' OR j.turn_id IS DISTINCT FROM r.turn_id
    OR current_setting('asm.correlation_id',true) IS DISTINCT FROM j.correlation_id::text
    THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;

  SELECT * INTO STRICT d FROM app.service_requests WHERE
    (workspace_id,business_id,conversation_id,client_id,id,revision)
    =(r.workspace_id,r.business_id,r.conversation_id,r.client_id,a.request_id,a.request_revision)
    FOR SHARE;

  IF p_step='PLAN' AND a.phase='ASSESS' AND p_payload='{}'::jsonb THEN
    RETURN platform.service_assessment_material(d);
  ELSIF p_step='ASSESS' AND a.phase='ASSESS' THEN
    PERFORM platform.service_assessment_record_scoped(d,NULL,j.correlation_id,p_payload);
    PERFORM platform.price_calculate_scoped(d,NULL,j.correlation_id,d.revision::text);
    IF a.approval_requested THEN
      current_basis:=platform.approval_basis(d);
      IF current_basis->'can_approve'='true'::jsonb AND (current_basis->>'occupied_minutes' IS NULL
        OR (current_basis->>'amount_minor' IS NULL AND current_basis->>'price_range' IS NULL)) THEN
        SELECT p.id INTO chosen_approval FROM app.approval_requests p
          JOIN platform.service_request_agent_intents prior ON (prior.workspace_id,prior.approval_id)=(p.workspace_id,p.id)
          WHERE (p.workspace_id,p.request_id,p.request_revision,p.assignee_user_account_id)
            =(d.workspace_id,d.id,d.revision,a.owner_user_account_id) AND p.basis=current_basis
          ORDER BY p.created_at DESC,p.id DESC LIMIT 1;
        IF chosen_approval IS NULL THEN
          approval:=platform.approval_open_scoped(d,a.owner_user_account_id,d.revision::text);
          chosen_approval:=(approval->>'approval_id')::uuid;
        END IF;
      END IF;
    END IF;
    IF a.prepare_requested THEN prepared_quote:=platform.quote_prepare_scoped(d); END IF;
    UPDATE platform.service_request_agent_intents
      SET phase='QUOTE',quote_input=prepared_quote,approval_id=chosen_approval
      WHERE (workspace_id,run_id)=(r.workspace_id,r.id);
    RETURN prepared_quote;
  ELSIF p_step='FINISH' AND a.phase='QUOTE' THEN
    IF a.quote_input IS NOT NULL THEN
      IF p_payload-'text' IS DISTINCT FROM a.quote_input OR jsonb_typeof(p_payload->'text') IS DISTINCT FROM 'string'
        THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
      saved:=platform.quote_record_scoped(d,a.owner_user_account_id,j.correlation_id,true,p_payload);
      saved_quote_id:=(saved->'quote'->>'quote_id')::uuid;
      IF saved_quote_id IS DISTINCT FROM (a.quote_input->>'quote_id')::uuid
        THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
    ELSIF p_payload IS DISTINCT FROM '{}'::jsonb THEN
      RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001';
    END IF;
    UPDATE platform.service_request_agent_intents
      SET phase='DONE',quote_input=NULL,quote_id=saved_quote_id
      WHERE (workspace_id,run_id)=(r.workspace_id,r.id);
    -- Refuse a commit if the admission expired while building the result.
    IF a.lease_until<=clock_timestamp() OR r.deadline<=clock_timestamp()
      THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
    RETURN platform.service_request_agent_result(r);
  END IF;
  RAISE EXCEPTION 'AI_INCOMPLETE' USING ERRCODE='P2001';
EXCEPTION WHEN SQLSTATE 'P3101' THEN
  RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001';
END $$""",
    "platform.service_request_agent_must_finish()": r"""
CREATE FUNCTION platform.service_request_agent_must_finish()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
  IF EXISTS(SELECT 1 FROM platform.service_request_agent_intents x
    WHERE (x.workspace_id,x.run_id)=(NEW.workspace_id,NEW.run_id) AND x.phase<>'DONE')
    THEN RAISE EXCEPTION 'AI_INCOMPLETE' USING ERRCODE='P2001'; END IF;
  RETURN NULL;
END $$""",
}
# Freeze the accepted owner commands for downgrade and derive their shared internal bodies.
AGENT_OWNER_COMMANDS_0030 = {
    "platform.service_request_owner_create(uuid,uuid,text,jsonb)": r"""CREATE OR REPLACE FUNCTION platform.service_request_owner_create(
      p_business uuid,p_conversation uuid,p_key text,p_request jsonb
    ) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    DECLARE
      scope app.conversations%ROWTYPE; draft app.service_requests%ROWTYPE;
      anchor app.messages%ROWTYPE; next_anchor app.messages%ROWTYPE; command record;
      projection jsonb; service jsonb; release_id uuid; fields jsonb; start_source jsonb;
      fact jsonb; facts jsonb; summary jsonb; effect text; complexity jsonb;
    BEGIN
      scope:=platform.service_request_owner_scope(p_business,p_conversation);
      SELECT * INTO command FROM platform.service_request_command(scope,p_key,'CREATE',NULL,p_request);
      IF command.replay_id IS NOT NULL THEN
        RETURN jsonb_build_object('request_id',command.replay_id);
      END IF;
      IF platform.material_object(p_request,ARRAY[
          'expected_version','expected_fingerprint','intent_source','fields','selection'
        ]) IS NOT TRUE THEN
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

      projection:=platform.service_request_intake(scope,p_request);
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
      SELECT d.* INTO draft FROM app.service_requests d
        WHERE (d.workspace_id,d.business_id,d.conversation_id,d.client_id,d.intent_message_id)
          =(scope.workspace_id,scope.business_id,scope.id,scope.client_id,anchor.id);
      IF FOUND THEN
        effect:='OPEN';
      ELSE
        release_id:=(projection->>'release_id')::uuid;
        SELECT s.value INTO service
          FROM platform.business_configuration_releases published
          CROSS JOIN LATERAL jsonb_array_elements(published.body->'services') s(value)
          WHERE (published.workspace_id,published.business_id,published.id)
              =(scope.workspace_id,scope.business_id,release_id)
            AND s.value->>'id'=projection->>'service_id' AND s.value->>'active'='true';
        IF platform.intake_template(service) IS NOT TRUE THEN
          RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P3101';
        END IF;
        -- A newly created draft takes facts from its own segment of the dialogue.
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
          IF platform.service_request_fact_available(scope,NULL,fact) IS NOT TRUE OR NOT EXISTS (
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
        complexity:=platform.service_request_complex_work(scope,NULL,projection->>'service_id',
          jsonb_build_array(start_source)||jsonb_path_query_array(facts,'$[*].source'));
        summary:=platform.service_request_summary(service,facts,
          CASE WHEN complexity IS NOT NULL THEN 'Мастер, уточните, можно ли продолжить консультацию по этому запросу.'
            WHEN projection->>'status'='OWNER_HANDOFF' AND projection->>'category' NOT IN ('COVER_UP','OTHER_COMPLEX')
            THEN projection->>'question' END);
        INSERT INTO app.service_requests
          (workspace_id,business_id,conversation_id,client_id,intent_message_id,intent_source_version,
           release_id,service_id,service_name,template_revision,facts,missing,conflicts,question,complex_work)
          VALUES(scope.workspace_id,scope.business_id,scope.id,scope.client_id,anchor.id,
            start_source->>'source_version',release_id,service->>'id',service->>'name',
            projection->>'template_revision',facts,summary->'missing',summary->'conflicts',summary->>'question',complexity)
          RETURNING * INTO draft;
        effect:='CREATE';
      END IF;
      INSERT INTO platform.service_request_receipts
        (workspace_id,actor_user_account_id,command_key,correlation_id,request_fingerprint,
         request_id,accepted_revision,effect)
        VALUES(scope.workspace_id,command.actor,p_key,
          nullif(current_setting('asm.correlation_id',true),'')::uuid,
          command.fingerprint,draft.id,draft.revision,effect);
      RETURN jsonb_build_object('request_id',draft.id);
    END $$""",
    "platform.service_request_owner_revise(uuid,uuid,uuid,text,jsonb)": r"""CREATE OR REPLACE FUNCTION platform.service_request_owner_revise(
      p_business uuid,p_conversation uuid,p_target uuid,p_key text,p_request jsonb
    ) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    DECLARE
      scope app.conversations%ROWTYPE; draft app.service_requests%ROWTYPE; command record;
      projection jsonb; service jsonb; requested_source jsonb; selected_field text;
      fact jsonb; revised_facts jsonb; summary jsonb; effect text:='OPEN'; complexity jsonb;
    BEGIN
      scope:=platform.service_request_owner_scope(p_business,p_conversation);
      SELECT * INTO command FROM platform.service_request_command(scope,p_key,'REVISE',p_target,p_request);
      IF command.replay_id IS NOT NULL THEN
        RETURN jsonb_build_object('request_id',command.replay_id);
      END IF;
      requested_source:=p_request->'source';
      selected_field:=p_request->>'field';
      IF p_target IS NULL OR platform.material_object(p_request,ARRAY[
          'expected_revision','expected_version','expected_fingerprint','field','source','selection'
        ]) IS NOT TRUE
        OR platform.human_context_decimal(p_request->'expected_revision',true) IS NOT TRUE
        OR (p_request->'field' IS DISTINCT FROM 'null'::jsonb
          AND (selected_field IN ('idea','placement','approximate_size','style','references')) IS NOT TRUE)
        OR platform.material_object(requested_source,ARRAY['message_id','source_version']) IS NOT TRUE
        OR platform.human_context_uuid(requested_source->'message_id') IS NOT TRUE
        OR jsonb_typeof(requested_source->'source_version') IS DISTINCT FROM 'string'
        OR (requested_source->>'source_version' ~ '^[a-f0-9]{64}$') IS NOT TRUE THEN
        RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P3101';
      END IF;

      SELECT d.* INTO draft FROM app.service_requests d
        WHERE (d.workspace_id,d.business_id,d.conversation_id,d.client_id,d.id)
          =(scope.workspace_id,scope.business_id,scope.id,scope.client_id,p_target)
        FOR NO KEY UPDATE;
      IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P3101'; END IF;
      IF draft.revision::text IS DISTINCT FROM p_request->>'expected_revision' THEN
        RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P3101';
      END IF;
      projection:=platform.service_request_intake(scope,p_request);
      IF (draft.service_id,draft.template_revision) IS DISTINCT FROM
        (projection->>'service_id',projection->>'template_revision') THEN
        RAISE EXCEPTION 'NEEDS_CLARIFICATION' USING ERRCODE='P3101';
      END IF;
      IF selected_field IS NULL THEN
        IF platform.intake_source_current(
          scope.workspace_id,scope.business_id,scope.id,scope.client_id,requested_source
        ) IS NOT TRUE THEN
          RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P3101';
        END IF;
        revised_facts:=draft.facts;
      ELSE
        SELECT f.value INTO fact FROM jsonb_array_elements(projection->'facts') f(value)
          WHERE f.value->>'field'=selected_field
            AND f.value->'source'->'message_id'=requested_source->'message_id'
            AND f.value->'source'->'source_version'=requested_source->'source_version';
        IF NOT FOUND OR platform.intake_source_current(
          scope.workspace_id,scope.business_id,scope.id,scope.client_id,fact->'source'
        ) IS NOT TRUE THEN
          RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P3101';
        END IF;
        -- A source assigned to another work contradicts the owner's selection.
        IF fact->>'conflict' IS DISTINCT FROM 'false'
          OR platform.service_request_fact_available(scope,draft.id,fact) IS NOT TRUE THEN
          RAISE EXCEPTION 'NEEDS_CLARIFICATION' USING ERRCODE='P3101';
        END IF;
        SELECT jsonb_agg(f.value ORDER BY f.value->>'field') INTO revised_facts FROM (
          SELECT f.value FROM jsonb_array_elements(draft.facts) f(value)
            WHERE f.value->>'field'<>selected_field
          UNION ALL SELECT jsonb_set(fact,'{source,quote}','""')
        ) f(value);
      END IF;

      complexity:=platform.service_request_complex_work(
        scope,draft.id,draft.service_id,jsonb_build_array(requested_source));
      IF selected_field IS NULL AND complexity IS NULL THEN
        RAISE EXCEPTION 'NEEDS_CLARIFICATION' USING ERRCODE='P3101';
      END IF;
      complexity:=coalesce(complexity,draft.complex_work);
      IF (revised_facts,complexity) IS DISTINCT FROM (draft.facts,draft.complex_work) THEN
        IF draft.revision=9223372036854775807 THEN
          RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P3101';
        END IF;
        SELECT s.value INTO service
          FROM platform.business_configuration_releases published
          CROSS JOIN LATERAL jsonb_array_elements(published.body->'services') s(value)
          WHERE (published.workspace_id,published.business_id,published.id)
              =(draft.workspace_id,draft.business_id,draft.release_id)
            AND s.value->>'id'=draft.service_id;
        IF platform.intake_template(service) IS NOT TRUE THEN
          RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P3101';
        END IF;
        summary:=platform.service_request_summary(service,revised_facts,CASE
          WHEN complexity IS NOT NULL OR
            draft.question='Мастер, уточните, можно ли продолжить консультацию по этому запросу.'
          THEN 'Мастер, уточните, можно ли продолжить консультацию по этому запросу.' END);
        UPDATE app.service_requests d
          SET (facts,missing,conflicts,question,revision,complex_work)=(revised_facts,summary->'missing',
            summary->'conflicts',summary->>'question',d.revision+1,complexity)
          WHERE (d.workspace_id,d.id)=(draft.workspace_id,draft.id)
          RETURNING d.* INTO draft;
        effect:='REVISE';
      END IF;
      INSERT INTO platform.service_request_receipts
        (workspace_id,actor_user_account_id,command_key,correlation_id,request_fingerprint,
         request_id,accepted_revision,effect)
        VALUES(scope.workspace_id,command.actor,p_key,
          nullif(current_setting('asm.correlation_id',true),'')::uuid,
          command.fingerprint,draft.id,draft.revision,effect);
      RETURN jsonb_build_object('request_id',draft.id);
    END $$""",
    "platform.service_assessment_record(uuid,uuid,uuid,jsonb)": r"""CREATE OR REPLACE FUNCTION platform.service_assessment_record(
      p_business uuid,p_conversation uuid,p_request uuid,p_result jsonb
    ) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    DECLARE
      draft app.service_requests%ROWTYPE; saved app.service_assessments%ROWTYPE;
      material jsonb; duration jsonb; size_rule jsonb; outcome text; reason text; field text; rule_id text;
      limit_value integer; size_mm integer; occupied integer;
    BEGIN
      draft:=platform.service_assessment_scope(p_business,p_conversation,p_request);
      IF octet_length(p_result::text)>4096 OR platform.material_object(p_result,ARRAY[
          'expected_revision','authority_sha256','outcome','reason','field','rule_id',
          'limit','size_mm','occupied_minutes'
        ]) IS NOT TRUE THEN
        RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P3101';
      END IF;
      IF platform.human_context_decimal(p_result->'expected_revision',true) IS NOT TRUE
        OR jsonb_typeof(p_result->'authority_sha256') IS DISTINCT FROM 'string'
        OR (p_result->>'authority_sha256' ~ '^[a-f0-9]{64}$') IS NOT TRUE
        OR NOT (p_result->'field'='null'::jsonb OR p_result->'field' IN (
          '"idea"','"placement"','"approximate_size"','"style"','"references"'))
        OR NOT (p_result->'rule_id'='null'::jsonb OR (
          jsonb_typeof(p_result->'rule_id')='string' AND p_result->>'rule_id' ~ '^[a-z][a-z0-9_-]{0,39}$'))
        OR EXISTS(SELECT 1 FROM jsonb_each(p_result) item(name,value)
          WHERE item.name IN ('limit','size_mm','occupied_minutes') AND item.value<>'null'::jsonb
            AND (jsonb_typeof(item.value)<>'number' OR item.value::text !~ '^[1-9][0-9]{0,4}$')) THEN
        RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P3101';
      END IF;
      outcome:=p_result->>'outcome'; reason:=p_result->>'reason';
      field:=p_result->>'field'; rule_id:=p_result->>'rule_id';
      limit_value:=(p_result->>'limit')::integer;
      size_mm:=(p_result->>'size_mm')::integer;
      occupied:=(p_result->>'occupied_minutes')::integer;
      IF (CASE outcome
          WHEN 'FEASIBLE' THEN reason IN ('FIXED_DURATION','SIZE_DURATION_RULE')
          WHEN 'NEEDS_DATA' THEN reason IN ('MISSING_FACT','CONFLICTING_FACT','SOURCE_CHANGED',
            'SIZE_NEEDS_CONFIRMATION','MIN_AGE_UNCONFIRMED')
          WHEN 'NEEDS_OWNER' THEN reason IN ('OWNER_HANDOFF','OWNER_DURATION','SERVICE_UNAVAILABLE','DURATION_UNPUBLISHED')
          WHEN 'DECLINED' THEN reason='SIZE_LIMIT_EXCEEDED'
        END) IS NOT TRUE
        OR ((outcome='FEASIBLE') IS DISTINCT FROM (occupied IS NOT NULL))
        OR limit_value>1000 OR size_mm>1000 OR occupied>10080 THEN
        RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P3101';
      END IF;
      IF draft.revision::text IS DISTINCT FROM p_result->>'expected_revision' THEN
        RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P3101';
      END IF;
      material:=platform.service_assessment_material(draft);
      IF material->>'authority_sha256' IS DISTINCT FROM p_result->>'authority_sha256' THEN
        RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P3101';
      END IF;
      IF material ? 'complex_work' AND outcome<>'NEEDS_OWNER' THEN
        RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P3101';
      END IF;

      duration:=material->'service'->'duration';
      size_rule:=duration->'size_rule';
      -- Even the typed domain result cannot write minutes outside its published policy.
      IF reason='FIXED_DURATION' AND (duration->>'mode' IS DISTINCT FROM 'FIXED'
        OR occupied IS DISTINCT FROM (duration->>'minutes')::integer)
        OR reason='SIZE_DURATION_RULE' AND (duration->>'mode' IS DISTINCT FROM 'CONFIGURED_RULE'
          OR size_mm IS NULL OR occupied IS DISTINCT FROM CASE
            WHEN size_mm<=(size_rule->>'threshold_mm')::integer THEN (size_rule->>'at_or_below_minutes')::integer
            ELSE (size_rule->>'above_minutes')::integer END) THEN
        RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P3101';
      END IF;

      SELECT a.* INTO saved FROM app.service_assessments a
        WHERE (a.workspace_id,a.request_id,a.authority_sha256)
          =(draft.workspace_id,draft.id,material->>'authority_sha256');
      IF FOUND THEN
        IF (saved.outcome,saved.reason,saved.field,saved.rule_id,saved.limit_value,saved.size_mm,
          saved.occupied_minutes) IS DISTINCT FROM (outcome,reason,field,rule_id,limit_value,size_mm,occupied) THEN
          RAISE EXCEPTION 'IDEMPOTENCY_KEY_CONFLICT' USING ERRCODE='P3101';
        END IF;
        RETURN platform.service_assessment_result(saved,true);
      END IF;
      INSERT INTO app.service_assessments
        (workspace_id,business_id,request_id,request_revision,service_id,release_id,activation_version,
         authority_sha256,owner_handoff,duration_policy,rules,evidence,unavailable_fields,
         outcome,reason,field,rule_id,limit_value,size_mm,occupied_minutes,actor_user_account_id,
         correlation_id,complex_work)
        VALUES(draft.workspace_id,draft.business_id,draft.id,draft.revision,draft.service_id,
          (material->>'release_id')::uuid,(material->>'activation_version')::bigint,
          material->>'authority_sha256',(material->>'owner_handoff')::boolean,duration,
          material->'rules',material->'facts',material->'unavailable_fields',outcome,reason,
          field,rule_id,limit_value,size_mm,occupied,nullif(current_setting('asm.actor_id',true),'')::uuid,
          nullif(current_setting('asm.correlation_id',true),'')::uuid,material->'complex_work')
        RETURNING * INTO saved;
      RETURN platform.service_assessment_result(saved,true);
    END $$""",
    "platform.price_calculate(uuid,uuid,uuid,text)": r"""CREATE OR REPLACE FUNCTION platform.price_calculate(
      p_business uuid,p_conversation uuid,p_request uuid,p_revision text
    ) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    DECLARE draft app.service_requests%ROWTYPE; saved app.price_calculations%ROWTYPE;
      material jsonb; policy jsonb; rule jsonb; mm integer; step_mm integer; steps integer;
      amount bigint; low bigint; high bigint; extra bigint; outcome text:='NEEDS_HUMAN';
      authority text; reason text:='PRICE_UNPUBLISHED'; fingerprint text;
    BEGIN
      draft:=platform.service_assessment_scope(p_business,p_conversation,p_request);
      IF platform.human_context_decimal(to_jsonb(p_revision),true) IS NOT TRUE THEN
        RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P3101';
      END IF;
      IF draft.revision::text IS DISTINCT FROM p_revision THEN
        RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P3101';
      END IF;
      material:=platform.price_material(draft);
      fingerprint:=material->>'authority_sha256';
      SELECT a.* INTO saved FROM app.price_calculations a
        WHERE (a.workspace_id,a.request_id,a.authority_sha256)=(draft.workspace_id,draft.id,fingerprint);
      IF FOUND THEN RETURN platform.price_result(saved,true); END IF;
      policy:=nullif(material->'policy','null'::jsonb);
      rule:=policy->'size_formula';
      mm:=(material->>'size_mm')::integer;
      IF policy IS NULL THEN reason:='SERVICE_UNAVAILABLE';
      ELSIF policy->>'mode'='OWNER_QUOTE' THEN reason:='OWNER_QUOTE';
      ELSIF policy->>'mode'='FIXED' AND (policy->>'amount_minor')::bigint BETWEEN 1 AND 100000000000 THEN
        outcome:='EXACT'; authority:='CONFIRMED'; reason:='FIXED_PRICE';
        amount:=(policy->>'amount_minor')::bigint;
      ELSIF policy->>'mode'='CONFIGURED_FORMULA' AND platform.configuration_price_formula_valid(rule) IS TRUE THEN
        IF mm IS NULL THEN outcome:='NEEDS_INPUT'; reason:='SIZE_REQUIRED';
        ELSIF mm>(rule->>'max_size_mm')::integer THEN reason:='SIZE_OUTSIDE_RULE';
        ELSE
          step_mm:=(rule->>'step_mm')::integer;
          steps:=(mm+step_mm-1)/step_mm;
          reason:='SIZE_FORMULA';
          amount:=(rule->>'base_minor')::bigint+steps*(rule->>'step_minor')::bigint;
          extra:=(rule->>'range_add_minor')::bigint;
          IF extra IS NULL THEN outcome:='EXACT'; authority:='CONFIRMED';
          ELSE
            outcome:='RANGE'; authority:='PROVISIONAL'; low:=amount; high:=amount+extra; amount:=NULL;
          END IF;
        END IF;
      END IF;
      INSERT INTO app.price_calculations
        (workspace_id,business_id,request_id,request_revision,release_id,activation_version,
         authority_sha256,policy,size_fact,size_mm,steps,outcome,authority,reason,
         amount_minor,lower_minor,upper_minor,actor_user_account_id,correlation_id)
        VALUES (draft.workspace_id,draft.business_id,draft.id,draft.revision,(material->>'release_id')::uuid,
          (material->>'activation_version')::bigint,fingerprint,policy,nullif(material->'size_fact','null'::jsonb),
          mm,steps,outcome,authority,reason,amount,low,high,nullif(current_setting('asm.actor_id',true),'')::uuid,
          nullif(current_setting('asm.correlation_id',true),'')::uuid)
        RETURNING * INTO saved;
      RETURN platform.price_result(saved,true);
    END $$""",
    "platform.approval_owner_open(uuid,uuid,uuid,text)": r"""CREATE OR REPLACE FUNCTION platform.approval_owner_open(
      p_business uuid,p_conversation uuid,p_request uuid,p_revision text
    ) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    DECLARE d app.service_requests%ROWTYPE; p app.approval_requests%ROWTYPE;
      actor uuid:=nullif(current_setting('asm.actor_id',true),'')::uuid; material jsonb; validity text;
      member_version bigint; user_version bigint; moment timestamptz;
    BEGIN
      d:=platform.service_assessment_scope(p_business,p_conversation,p_request);
      IF d.revision::text IS DISTINCT FROM p_revision THEN RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P3101'; END IF;
      material:=platform.approval_basis(d);
      IF material IS NULL THEN RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P3101'; END IF;
      IF (material->'amount_minor'<>'null'::jsonb OR material->'price_range'<>'null'::jsonb)
        AND material->'occupied_minutes'<>'null'::jsonb AND material->'can_approve'='true'::jsonb
        THEN RETURN NULL; END IF;
      SELECT a.* INTO p FROM app.approval_requests a
        WHERE (a.workspace_id,a.request_id)=(d.workspace_id,d.id) AND a.retired_at IS NULL FOR UPDATE;
      moment:=clock_timestamp();
      IF p.id IS NOT NULL THEN
        validity:=platform.approval_validity(p,d,moment);
        IF validity='CURRENT' THEN RETURN platform.approval_view(p,d,moment); END IF;
        UPDATE app.approval_requests SET retired_at=moment,retired_reason=validity,retired_by=actor
          WHERE (workspace_id,id)=(p.workspace_id,p.id);
      END IF;
      SELECT m.version,u.version INTO STRICT member_version,user_version
        FROM platform.workspace_memberships m JOIN platform.user_accounts u ON u.id=m.user_account_id
        WHERE (m.workspace_id,m.user_account_id)=(d.workspace_id,actor)
          AND m.role='OWNER' AND m.status='ACTIVE' AND u.status='ACTIVE';
      INSERT INTO app.approval_requests(workspace_id,business_id,conversation_id,client_id,request_id,
        request_revision,assignee_user_account_id,membership_version,account_version,basis,created_at,expires_at)
      VALUES(d.workspace_id,d.business_id,d.conversation_id,d.client_id,d.id,d.revision,actor,
        member_version,user_version,material,moment,moment+interval '24 hours') RETURNING * INTO p;
      RETURN platform.approval_view(p,d,moment);
    END $$""",
    "platform.quote_owner_prepare(uuid,uuid,uuid)": r"""CREATE OR REPLACE FUNCTION platform.quote_owner_prepare(
      p_business uuid,p_conversation uuid,p_request uuid
    ) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    DECLARE d app.service_requests%ROWTYPE; q app.quotes%ROWTYPE; current_material jsonb;
      quote_id uuid; expiry timestamptz;
    BEGIN
      d:=platform.service_assessment_scope(p_business,p_conversation,p_request);
      IF EXISTS(SELECT 1 FROM app.quote_acceptances a WHERE (a.workspace_id,a.request_id)=(d.workspace_id,d.id))
        THEN RETURN NULL; END IF;
      current_material:=platform.quote_basis(d,clock_timestamp())->'material';
      IF current_material IS NULL THEN RETURN NULL; END IF;
      SELECT * INTO q FROM app.quotes WHERE (workspace_id,request_id,basis_sha256)
        =(d.workspace_id,d.id,platform.quote_hash(current_material));
      expiry:=coalesce(q.expires_at,platform.quote_expiry(current_material));
      IF q.id IS NULL AND expiry<=clock_timestamp() THEN RETURN NULL; END IF;
      quote_id:=coalesce(q.id,uuidv7());
      RETURN jsonb_build_object('quote_id',quote_id,'code',platform.quote_code(quote_id),
        'expires_at',platform.quote_timestamp(expiry),'material',current_material);
    END $$""",
    "platform.quote_owner_record(uuid,uuid,uuid,jsonb)": r"""CREATE OR REPLACE FUNCTION platform.quote_owner_record(
      p_business uuid,p_conversation uuid,p_request uuid,p_payload jsonb
    ) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    DECLARE d app.service_requests%ROWTYPE; c app.conversations%ROWTYPE; q app.quotes%ROWTYPE;
      material jsonb; basis text; text_body text; quote_id uuid; code text; created timestamptz; expiry timestamptz;
      actor uuid:=nullif(current_setting('asm.actor_id',true),'')::uuid;
      correlation uuid:=nullif(current_setting('asm.correlation_id',true),'')::uuid;
      member_version bigint; user_version bigint; next_version bigint; hold_reason text;
    BEGIN
      d:=platform.service_assessment_scope(p_business,p_conversation,p_request);
      IF EXISTS(SELECT 1 FROM app.quote_acceptances a WHERE (a.workspace_id,a.request_id)=(d.workspace_id,d.id))
        THEN RETURN platform.quote_owner_read(p_business,p_conversation,p_request); END IF;
      SELECT * INTO STRICT c FROM app.conversations WHERE (workspace_id,id)=(d.workspace_id,d.conversation_id);
      material:=platform.quote_basis(d,clock_timestamp())->'material';
      IF material IS NULL OR platform.quote_expiry(material)<=clock_timestamp() THEN
        RETURN platform.quote_owner_read(p_business,p_conversation,p_request);
      END IF;
      IF material IS DISTINCT FROM p_payload->'material'
        THEN RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P3101'; END IF;
      basis:=platform.quote_hash(material);
      SELECT * INTO q FROM app.quotes WHERE (workspace_id,request_id,basis_sha256)=(d.workspace_id,d.id,basis);
      IF FOUND THEN
        -- An ordinary readiness replay can recheck an unqueued intent. A
        -- prepared HUMAN quote still requires the current explicit Resume.
        IF EXISTS(SELECT 1 FROM platform.quote_delivery_intents i
            WHERE (i.workspace_id,i.quote_id)=(q.workspace_id,q.id) AND i.send_job_id IS NULL)
          AND correlation IS NOT NULL AND platform.quote_block(q,c,c.control_generation) IS NULL
          THEN PERFORM platform.quote_queue(q,c,correlation); END IF;
        RETURN platform.quote_view(q,c);
      END IF;
      IF platform.material_object(p_payload,ARRAY['quote_id','code','expires_at','material','text']) IS NOT TRUE
        OR platform.human_context_uuid(p_payload->'quote_id') IS NOT TRUE
        OR jsonb_typeof(p_payload->'text') IS DISTINCT FROM 'string' OR correlation IS NULL
        THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P3101'; END IF;
      quote_id:=(p_payload->>'quote_id')::uuid;
      code:=platform.quote_code(quote_id);
      created:=transaction_timestamp();
      expiry:=platform.quote_expiry(material);
      text_body:=p_payload->>'text';
      IF uuid_extract_version(quote_id) IS DISTINCT FROM 7 OR p_payload->>'code' IS DISTINCT FROM code
        OR p_payload->>'expires_at' IS DISTINCT FROM platform.quote_timestamp(expiry)
        OR char_length(text_body) NOT BETWEEN 1 AND 4096 OR octet_length(text_body)>16384
        OR right(text_body,char_length(E'\nПринимаю '||code)) IS DISTINCT FROM E'\nПринимаю '||code
        THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P3101'; END IF;
      SELECT m.version,u.version INTO STRICT member_version,user_version
        FROM platform.workspace_memberships m JOIN platform.user_accounts u ON u.id=m.user_account_id
        WHERE (m.workspace_id,m.user_account_id)=(d.workspace_id,actor)
          AND m.role='OWNER' AND m.status='ACTIVE' AND u.status='ACTIVE';
      SELECT coalesce(max(version),0)+1 INTO next_version FROM app.quotes
        WHERE (workspace_id,request_id)=(d.workspace_id,d.id);
      INSERT INTO app.quotes(workspace_id,id,business_id,conversation_id,client_id,request_id,request_revision,
        version,code,material,basis_sha256,terms_sha256,text,release_id,prepared_by,membership_version,
        account_version,created_at,expires_at)
        VALUES(d.workspace_id,quote_id,d.business_id,d.conversation_id,d.client_id,d.id,d.revision,next_version,
          code,material,basis,platform.quote_hash(jsonb_build_array('quote_v1',quote_id,next_version,code,
            platform.quote_timestamp(expiry),material,text_body)),text_body,(material->>'release_id')::uuid,
          actor,member_version,user_version,created,expiry) RETURNING * INTO q;
      hold_reason:=platform.quote_block(q,c,c.control_generation);
      INSERT INTO platform.quote_delivery_intents(workspace_id,quote_id,connection_id,control_generation,hold_reason)
        VALUES(q.workspace_id,q.id,c.connection_id,c.control_generation,hold_reason);
      IF hold_reason IS NULL THEN PERFORM platform.quote_queue(q,c,correlation); END IF;
      RETURN platform.quote_view(q,c);
    END $$""",
}

AGENT_SHARED_COMMANDS = {
    "platform.service_request_owner_create(uuid,uuid,text,jsonb)": (
        "platform.service_request_create_scoped(app.conversations,uuid,uuid,text,jsonb)",
        "scope app.conversations,p_actor uuid,p_correlation uuid,p_key text,p_request jsonb",
        "platform.service_request_owner_scope(p_business,p_conversation),{actor},{correlation},p_key,p_request",
    ),
    "platform.service_request_owner_revise(uuid,uuid,uuid,text,jsonb)": (
        "platform.service_request_revise_scoped(app.conversations,uuid,uuid,uuid,text,jsonb)",
        "scope app.conversations,p_actor uuid,p_correlation uuid,p_target uuid,p_key text,p_request jsonb",
        "platform.service_request_owner_scope(p_business,p_conversation),{actor},{correlation},p_target,p_key,p_request",
    ),
    "platform.service_assessment_record(uuid,uuid,uuid,jsonb)": (
        "platform.service_assessment_record_scoped(app.service_requests,uuid,uuid,jsonb)",
        "draft app.service_requests,p_actor uuid,p_correlation uuid,p_result jsonb",
        "platform.service_assessment_scope(p_business,p_conversation,p_request),{actor},{correlation},p_result",
    ),
    "platform.price_calculate(uuid,uuid,uuid,text)": (
        "platform.price_calculate_scoped(app.service_requests,uuid,uuid,text)",
        "draft app.service_requests,p_actor uuid,p_correlation uuid,p_revision text",
        "platform.service_assessment_scope(p_business,p_conversation,p_request),{actor},{correlation},p_revision",
    ),
    "platform.approval_owner_open(uuid,uuid,uuid,text)": (
        "platform.approval_open_scoped(app.service_requests,uuid,text)",
        "d app.service_requests,p_actor uuid,p_revision text",
        "platform.service_assessment_scope(p_business,p_conversation,p_request),{actor},p_revision",
    ),
    "platform.quote_owner_prepare(uuid,uuid,uuid)": (
        "platform.quote_prepare_scoped(app.service_requests)",
        "d app.service_requests",
        "platform.service_assessment_scope(p_business,p_conversation,p_request)",
    ),
    "platform.quote_owner_record(uuid,uuid,uuid,jsonb)": (
        "platform.quote_record_scoped(app.service_requests,uuid,uuid,boolean,jsonb)",
        "d app.service_requests,p_actor uuid,p_correlation uuid,p_agent boolean,p_payload jsonb",
        "platform.service_assessment_scope(p_business,p_conversation,p_request),{actor},{correlation},false,p_payload",
    ),
}


def _agent_shared_bodies():
    actor = "nullif(current_setting('asm.actor_id',true),'')::uuid"
    correlation = "nullif(current_setting('asm.correlation_id',true),'')::uuid"
    properties = (
        "RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp"
    )
    for name, original in AGENT_OWNER_COMMANDS_0030.items():
        signature, arguments, owner_args = AGENT_SHARED_COMMANDS[name]
        common = signature.partition("(")[0]
        head, body = original.split(") RETURNS jsonb", 1)
        body = body.split("AS $$\n", 1)[1]
        if common.startswith(
            ("platform.service_request_create", "platform.service_request_revise")
        ):
            body = body.replace("scope app.conversations%ROWTYPE; ", "")
            gate, start, rest = body.partition("      SELECT * INTO command")
            assert start
            gate = gate.replace(
                "      scope:=platform.service_request_owner_scope(p_business,p_conversation);\n",
                "",
            )
            admission, finish, tail = rest.partition("      END IF;\n")
            assert finish
            before, receipt, after = tail.partition(
                "      INSERT INTO platform.service_request_receipts"
            )
            assert receipt
            write, end, after = after.partition("      RETURN jsonb_build_object('request_id'")
            assert end
            body = (
                gate
                + "      IF p_actor IS NOT NULL THEN\n"
                + start
                + admission
                + finish
                + "      END IF;\n"
                + before
                + "      IF p_actor IS NOT NULL THEN\n"
                + receipt
                + write.replace(correlation, "p_correlation")
                + "      END IF;\n"
                + end
                + after
            )
        else:
            body = body.replace("draft app.service_requests%ROWTYPE; ", "")
            body = body.replace("d app.service_requests%ROWTYPE; ", "")
            body = body.replace(
                "      draft:=platform.service_assessment_scope(p_business,p_conversation,p_request);\n",
                "",
            )
            body = body.replace(
                "      d:=platform.service_assessment_scope(p_business,p_conversation,p_request);\n",
                "",
            )
            body = body.replace(f"actor uuid:={actor};", "actor uuid:=p_actor;")
            body = body.replace(
                f"correlation uuid:={correlation};", "correlation uuid:=p_correlation;"
            )
            body = body.replace(actor, "p_actor").replace(correlation, "p_correlation")
            if common == "platform.quote_record_scoped":
                body = body.replace(
                    "platform.quote_owner_read(p_business,p_conversation,p_request)",
                    "CASE WHEN p_agent THEN NULL ELSE platform.quote_owner_read(d.business_id,d.conversation_id,d.id) END",
                )
        yield (
            signature,
            f"CREATE FUNCTION {common}({arguments}) {properties} AS $$\n{body}",
            f"""{head}) {properties} AS $$
            BEGIN
              RETURN {common}({owner_args.format(actor=actor, correlation=correlation)});
            END $$""",
        )


def upgrade_agent_domain():
    for table in ("app.service_assessments", "app.price_calculations"):
        op.execute(f"ALTER TABLE {table} ALTER COLUMN actor_user_account_id DROP NOT NULL")
    op.execute(AGENT_INTENT_TABLE)
    table = "platform.service_request_agent_intents"
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY agent_intent_migrator ON {table} TO asm_migrator USING(true) WITH CHECK(true)"
    )
    op.execute(f"REVOKE ALL ON {table} FROM PUBLIC,asm_runtime")
    for signature, body, wrapper in _agent_shared_bodies():
        op.execute(body)
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC,asm_runtime")
        op.execute(wrapper)
    for signature, sql in AGENT_DOMAIN_FUNCTIONS.items():
        op.execute(sql.strip())
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC,asm_runtime")
    op.execute(
        "GRANT EXECUTE ON FUNCTION platform.service_request_agent_continue(uuid,uuid,uuid,text,jsonb) TO asm_runtime"
    )
    op.execute("""
      CREATE CONSTRAINT TRIGGER service_request_agent_must_finish
      AFTER INSERT ON platform.service_request_agent_intents DEFERRABLE INITIALLY DEFERRED
      FOR EACH ROW EXECUTE FUNCTION platform.service_request_agent_must_finish()
    """)


def downgrade_agent_domain():
    op.execute("LOCK TABLE platform.service_request_agent_intents IN ACCESS EXCLUSIVE MODE")
    op.execute("""
      DO $$ BEGIN
        IF EXISTS(SELECT 1 FROM platform.service_request_agent_intents)
          THEN RAISE EXCEPTION 'AGENT_SERVICE_INTENT_DURABLE_DATA' USING ERRCODE='55000'; END IF;
      END $$
    """)
    op.execute(
        "DROP TRIGGER service_request_agent_must_finish ON platform.service_request_agent_intents"
    )
    for signature in reversed(AGENT_DOMAIN_FUNCTIONS):
        op.execute(f"DROP FUNCTION {signature}")
    for sql in AGENT_OWNER_COMMANDS_0030.values():
        op.execute(sql)
    for signature, _, _ in reversed(tuple(_agent_shared_bodies())):
        op.execute(f"DROP FUNCTION {signature}")
    op.execute("DROP TABLE platform.service_request_agent_intents")
    for table in ("app.service_assessments", "app.price_calculations"):
        op.execute(f"ALTER TABLE {table} ALTER COLUMN actor_user_account_id SET NOT NULL")


PROFILE = r"""CREATE FUNCTION platform.service_intent_schema_profile() RETURNS jsonb
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
('platform.ai_delivery_select(platform.messaging_jobs,platform.ai_runs)','94bacdd91a5a75671bef991683d336ccf613e02e9a231fc7ac70ae8033648b17','plpgsql',true,'v',false),
('platform.ai_knowledge_current(platform.ai_runs)','d98f7f41bb5010bd967004794410eff26d7c0203207104190a0a4909df42de8f','plpgsql',true,'v',false),
('platform.ai_knowledge_immutable()','a5dc3e44d61c74d3ad36a048961eed0ca3df662cbf7da9025a839c5aa0754a1b','plpgsql',true,'v',false),
('platform.ai_knowledge_snapshot(uuid,uuid)','14c077414a0063174421f6f9bd8a240d77b2700c198d22e8f9ec07a0be9f8ff5','plpgsql',true,'v',false),
('platform.ai_knowledge_valid(jsonb,jsonb,uuid,uuid)','c9cfe061cdecded77ee5f40e5a2775908382eba3996b61824636cc7e5eeed51e','plpgsql',true,'i',false),
('platform.ai_provider_command(uuid,uuid,uuid,text,jsonb)','24672f24048580bb314ed845a9d1e4869dee15d519063dedb029e82d0b4e2c60','plpgsql',true,'v',true),
('platform.ai_provider_config_valid(jsonb)','38064b38949e67306db7dbbcbf150dfd6d2b2195ad8aac77267ab1f6939a30af','plpgsql',true,'i',false),
('platform.ai_provider_enqueue(uuid,uuid,uuid)','91e5c0e7e3ae24516d55c68d9cda830fc8d52f15701cce31d7cdb65289583096','plpgsql',true,'v',true),
('platform.ai_provider_guard(uuid,platform.messaging_jobs,jsonb)','4beb6f775cc17a68fbd068c2b69692f2b2e4ef5c2b78753e119bd679f16666c3','plpgsql',true,'v',false),
('platform.ai_provider_schema_profile()','f2b1f7dbdea1f41244094a101d7d4802927a550078ac260e14c7ffb997bd1986','sql',true,'s',false),
('platform.ai_provider_session(jsonb,boolean)','170ae8ce45c4bea89108c03757d80f0bc16dbaa7f194eb4b04cb32a2a25d4eec','plpgsql',true,'v',false),
('platform.ai_reply_rights_commit(uuid,uuid,uuid,bigint,bigint,jsonb,jsonb)','4673129cca72678c0ffb5aa48d5d967b7f92befdce011a82a885c32e87e6cdb4','plpgsql',true,'v',true),
('platform.ai_reply_rights_current(uuid,uuid,uuid)','0c38889d00c0cf1415a890273eebd8f593ed40fe166436a5ad434079d1d30fe7','plpgsql',true,'v',false),
('platform.ai_reply_rights_probe(uuid,uuid,uuid)','9ca90da38d173e7294f77cd7dbdd25492f02fe2cd699562c823c42fbfcb3b01d','plpgsql',true,'v',true),
('platform.ai_reply_rights_schema_profile()','6b635b12b8d2e7f0f69500792d7ec3b1c71cd0f85c51e810e3332b910b6189c0','sql',true,'s',false),
('platform.ai_runtime_command(uuid,uuid,text,jsonb)','fcbab61cea598ca651114ec95baa5e923053cbc7e1f8d85303074c098107b5a3','plpgsql',true,'v',true),
('platform.ai_runtime_completion_valid(jsonb)','4675d7ce837be36341cdc60deff5c216786ad7f42441bb4bda43bfe5e0dcfb0d','plpgsql',true,'i',false),
('platform.ai_runtime_config_valid(jsonb)','0301c3f9d568695e29eaee8fd0567979cd6a51c755a6245c2a2ba6ef0736bf23','sql',true,'i',false),
('platform.ai_runtime_current(platform.messaging_jobs,jsonb)','c86bbe138ddabb5197dfbe4453e5b3f4f586099ebdfc62e463814198f3973e86','plpgsql',true,'v',false),
('platform.ai_runtime_receipt(platform.ai_runs)','cccfd3aedcd1e2be02e6de687d7f38b3e23ad04bc694674a8dd2a66f39884b59','sql',true,'s',false),
('platform.ai_runtime_replay(uuid,uuid,jsonb)','36b9248da5aff70b2fec73a85303716769350732f5cee03deb719a9f6d0a17c3','plpgsql',true,'v',true),
('platform.ai_runtime_result_valid(jsonb)','7f81305118ab1bff57585a409c91b04ff2eb44d24722d74b35ae05379d5e21d1','plpgsql',true,'i',false),
('platform.ai_runtime_view(platform.ai_runs)','00d0cb67e10ced313f36798aa93030c0dd712ab0c98db44270f162069d8299a3','sql',true,'s',false),
('platform.ai_synthetic_config_valid(jsonb)','20241427cbe5024f6a5876184f29895f28a83191519bf4d99a4e6e6993baf00c','plpgsql',true,'i',false),
('platform.approval_basis(app.service_requests)','5b5eea8bb476bb527727d4b041eeb53f5c8ae3976ff199299f945e5db2f26b6e','plpgsql',false,'s',false),
('platform.approval_open_scoped(app.service_requests,uuid,text)','6c18b0c35fdc0fc2927076b7266981390853f3741e3854d75ec9ec9ac64916aa','plpgsql',true,'v',false),
('platform.approval_owner_decide(uuid,uuid,uuid,uuid,jsonb)','b16c2f8ecd6a1d200f5dff646607bbd6890a55ba63d445c8c9100ee49f612699','plpgsql',true,'v',true),
('platform.approval_owner_list(uuid)','1882ad6ed68216fc6b3d4ed1442949bea2e4aaa71a4bae1c253da365acadfe67','plpgsql',true,'v',true),
('platform.approval_owner_open(uuid,uuid,uuid,text)','b65ed2a6c2897bdb731e0c5b68e13ba2dedd629e99276e7de546eb1dcd9eae9c','plpgsql',true,'v',true),
('platform.approval_owner_read(uuid,uuid,uuid,uuid)','e5dc57c5686640d84d8b1843e6d92f3cd963201dd98f9f578236c1684bc2d7de','plpgsql',true,'v',true),
('platform.approval_owner_source(uuid,uuid,uuid,uuid,uuid,text)','c9ae6cb29d799a71290acffd5c21a570e030496ec7414a8055f7bf073fc71189','plpgsql',true,'v',true),
('platform.approval_related_escalation(app.service_requests)','c49c9c357fed4f07393e06724a245e438d9d3389c1b7bed93153f62e557412e7','sql',false,'s',false),
('platform.approval_validity(app.approval_requests,app.service_requests,timestamptz)','73f00e321cf6c690277ce321e967baeba6a27167cbdfb3339c9fa92ae3fe8d37','plpgsql',false,'s',false),
('platform.approval_view(app.approval_requests,app.service_requests,timestamptz)','5d83e2877cb5813c648ea1d91b9e069039f71087063a3738b3fec2fb51192802','plpgsql',false,'s',false),
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
('platform.configuration_bundle_shape(jsonb)','966abf76449cceca1a4e4cb2dee90b14ca7217f65886323c9c385edca2793a3d','plpgsql',true,'i',false),
('platform.configuration_command(uuid,text,text,jsonb)','785ae59704a1ed262baa7dd197cd828e91fdc4890582236849539e36450b8b4c','plpgsql',true,'v',true),
('platform.configuration_immutable()','8cfeca7ce51a6990dcc48424553b948f985b75dfe187e29254f511bcd8063ef5','plpgsql',true,'v',false),
('platform.configuration_owner_read(uuid)','dc3b1b9ca35196841da4128296a971899eb693a1b6dfc75a2be8809aec5df24f','plpgsql',true,'v',true),
('platform.configuration_price_formula_valid(jsonb)','31fda026bec4f1dbd4fd601d220f42576de70182a4b10cebf4c596e82c7365d1','plpgsql',false,'i',false),
('platform.configuration_text_valid(jsonb,integer,boolean)','9b046fad55f926ead378d901bacd12edeb2f249d64f3fe913f604be3bb274cfa','sql',true,'i',false),
('platform.configuration_validate(jsonb)','ab8bf3d75797d8a9f8528c5cdca7ec7d93762c194fb8869312956846337a230f','plpgsql',true,'i',false),
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
('platform.human_context_policy_command(uuid,uuid,text,text,text,bigint,jsonb,jsonb)','9ae17a41463ec5ff671fe40ca8336906d15f9195724f4f53ec842de794cec54e','plpgsql',true,'v',false),
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
('platform.intake_apply(platform.ai_runs,jsonb)','feb06ead89045199ae986f1da796faf3670a1f5e07aae70275145720ea17fb3b','plpgsql',true,'v',false),
('platform.intake_candidates_valid(jsonb)','8341249f2e0a5b4a546b7685134aec687fb8065624c72acfea2700a13863632e','plpgsql',true,'i',false),
('platform.intake_current(platform.ai_runs)','180fc2562bcd5fc869269d1e3c489be4cde72a2cdb036de6b4e7c09f05bdea81','plpgsql',true,'s',false),
('platform.intake_delivery_guard(platform.ai_runs)','39be297435647f8884b2de99797b6e7b99b23333255e78aece06f99a0bcd1be6','plpgsql',true,'v',false),
('platform.intake_delivery_session_lock(uuid,uuid,uuid,numeric)','9675d03387482177e3e372b9864ec895f0a34c3a455f5e01a96fd2e8482e2f60','plpgsql',true,'v',false),
('platform.intake_escalation_decorate(jsonb)','06526a8b03ba842a18d12db40c251c49d4b2eb40dfa2cbacb0a867a9d1fc11ee','plpgsql',true,'v',false),
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
('platform.knowledge_runtime_current(platform.ai_runs)','a6dd598976ca12f90702d66f99767461989bec6e8ae1fa8036c650c02b1778e7','plpgsql',true,'v',false),
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
('platform.messaging_finish_send(uuid,uuid,uuid,text,text,text,integer)','c70503a40630a3e8d0dad9d402b4a5820ea0d5bde7a30ac9ae83932204daec9c','plpgsql',true,'v',true),
('platform.messaging_guard(uuid,uuid)','0a57433b9b39446547a2f2accfeb9516238ae8c9210f67773e30f749a756adb5','plpgsql',true,'v',false),
('platform.messaging_immutable()','3971e82a86a3826eeaf7b9e24458fbb1adc64cce0e8f2cb43a46384348519934','plpgsql',false,'v',false),
('platform.messaging_ingest(text,text,jsonb,uuid)','2833a40d4ec37a014eab30fcbe2893a590d50c909b71eebc754e1c575ecb9f32','plpgsql',true,'v',true),
('platform.messaging_job_json(platform.messaging_jobs)','765953cdac89862123a1e6d384504d668dc04bf4ad22de002a121f5a347e358b','sql',false,'s',false),
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
('platform.messaging_recover_expired(timestamptz,timestamptz,uuid)','1eafd46bd7482c814d9405d0921d9c03fc48b8037929cd7af24d25f1b539d71f','plpgsql',true,'v',true),
('platform.messaging_request_text(uuid,text,text)','13dc01a5b25f4b2d5da4835fa8aabf14f33f98573532e730929006688be7059c','plpgsql',true,'v',true),
('platform.messaging_reschedule(uuid,text,boolean)','6409aa21554ccaa346587c2f4da07bc6941e27c4736db9bd518f26e4c7947438','sql',true,'v',false),
('platform.messaging_reschedule(uuid,text,boolean,integer)','21e8b16de21a18ff5646eeb28f7eceb801da8ab5bfc7d8e1799e6a91b9a2d074','sql',true,'v',false),
('platform.messaging_reschedule(uuid,text,boolean,integer,boolean)','4467dca0370c5da544be20d4b06402dfdba4d925d55da78571033f0fd1a90e83','plpgsql',true,'v',false),
('platform.messaging_retry(uuid,uuid,text,boolean)','f91798c1c89796bf2633462892e71546e632d5d386256e517e678dc8b59d32ba','plpgsql',true,'v',true),
('platform.messaging_valid_id(text,integer,integer)','9e1cf327f38fa1437a5a755e3c68d531c0209b585722755c865b395f616419f5','sql',false,'i',false),
('platform.messaging_validate_event(jsonb)','1f7a2405bde9171aa196355bfae185cbc4084aeffbbdfda20d4f8828fdb95791','plpgsql',false,'v',false),
('platform.owner_decision_immutable()','eeda7b8e4c14e5248943f891f075daffd35ee9f1441ca475d90d1811a0a561ab','plpgsql',false,'v',false),
('platform.owner_decision_schema_profile()','8635a1c904931cc941fda92baedf24f895d1d8a329269d297fca6c04522efc08','sql',true,'s',false),
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
('platform.portfolio_delivery_attest(platform.messaging_jobs,platform.ai_runs,jsonb)','5614d261197fb9a29c87d4a38cc34c17b653400f0946d726bc2ec3c595ffc872','plpgsql',true,'v',false),
('platform.portfolio_delivery_begin(uuid,uuid,uuid,bigint,bigint,jsonb,text)','671251ebf476c91f98c5d6c71b3436418e1f3f34394c3a8f80f6f4aa2f7bc0ff','plpgsql',true,'v',true),
('platform.portfolio_delivery_current_valid(jsonb)','0afa2b97c307693bd803ba179c17b973118f80b25dafd60ef62aa3126b03fdca','sql',true,'i',false),
('platform.portfolio_delivery_eligible(platform.ai_runs)','8eb83ee8c1028cec33ac026ec8619e4efb7af8d4ebd777b85d54b37c1fa5bb0a','sql',true,'s',false),
('platform.portfolio_delivery_immutable()','1b26b5780fc46363019a7c5a8b17426a549a556793a3e3158a69433826576512','plpgsql',true,'v',false),
('platform.portfolio_delivery_intent_current(platform.messaging_jobs,platform.ai_deliveries,platform.ai_runs,platform.portfolio_delivery_intents)','180a20e75e36698c3fa4a07aa1aed2547051d77a85cd5df34b3b22e697948c60','plpgsql',true,'v',false),
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
('platform.portfolio_query_apply(uuid,uuid,uuid,uuid,uuid,jsonb)','84338bac51d5df6667fdb4116f2bf0c4b4a161f901c1cfb06f6945dff04a2f2a','plpgsql',true,'v',true),
('platform.portfolio_query_reserve(uuid,uuid,uuid,jsonb)','9c75e67139224fe86b16e366f51a7d9cd4d2c66d7acb60ecb47e711807161b93','plpgsql',true,'v',true),
('platform.portfolio_refs(jsonb)','9b992ad8ecdea455a2303458f421a2c1e171d5f6e38a9fc136f307d1bd6e0624','sql',true,'i',false),
('platform.portfolio_refs_valid(jsonb)','bfb584ddfdabb7407cf68878313e454bd74219a943dc57324555e589132031b5','plpgsql',true,'i',false),
('platform.portfolio_run_query(platform.ai_runs)','d3ebd9e619af66505665438a41577f20a3ccde6b051b0d02be1fdf3ace1d4423','plpgsql',true,'s',false),
('platform.portfolio_runtime_current(platform.ai_runs)','f63225228f51828012df8c1595f3a7d3c35273d1678c4f5b7b741bbb7fd79a93','plpgsql',true,'v',false),
('platform.portfolio_runtime_data(platform.ai_runs)','9c78fbcfcd32488639bcf5d223a1e319a07fbf51dee90c728811ee184ed2543e','plpgsql',true,'s',false),
('platform.portfolio_runtime_read(uuid,uuid,uuid,jsonb)','6fdad1fb5e5835db8f3b77f05d24ff16d55157448521e329e340b3cbef5b32b3','plpgsql',true,'v',true),
('platform.portfolio_schema_profile()','df2ab97e8fe09ead37d2dd16f70526f4f47073eaed3314686ceb319e7773d06b','sql',true,'s',false),
('platform.portfolio_select(uuid,uuid,jsonb,extensions.vector,text)','39460c29d3c4dcbf5efb4d3f044e8db4bdb89554a5cf3ced30df436b1a57249a','plpgsql',true,'s',false),
('platform.portfolio_session_admit(uuid,uuid,jsonb)','05322023e00a59fdcd0ad87f91015761a8d312cd3e209c20d6376e8e1312bf90','plpgsql',true,'v',true),
('platform.portfolio_session_lock(uuid,uuid,uuid,numeric)','386ace56e6fd2a11ce9f83c4685811533f390557b260536b0f203076d5965b97','plpgsql',true,'v',false),
('platform.portfolio_session_usage(uuid,uuid,uuid)','51057dd53b2f15951fcb63b1282d7581ba94217cff81d4271bf4d4d744623a41','sql',true,'s',false),
('platform.portfolio_text_valid(text,integer)','d98c95fcb948cb7f6afad5f26a93440629661e7991f3f8d8055644e95272354d','sql',true,'i',false),
('platform.portfolio_upload_begin(uuid,uuid,uuid,uuid)','1313e4b020befeff7a0b7d3519bf22fdf24026df2ae8f10e8677fda9d37e498e','plpgsql',true,'v',true),
('platform.portfolio_upload_complete(uuid,uuid,jsonb)','684afc3d4e29f69610835373455a2e5613dc6cbba8993290cb6210b7e4152dad','plpgsql',true,'v',true),
('platform.portfolio_upload_prepare(uuid,uuid,uuid,uuid,uuid,jsonb)','eb895fcd29065e34d54b400368d59153bca5fecce3b179df55768642bda878e4','plpgsql',true,'v',true),
('platform.portfolio_upload_recover(uuid,uuid,uuid,uuid)','e1c66eb556121f8e3d895d4bdafcff271936936e1be0fc341245e50c43d93167','plpgsql',true,'v',true),
('platform.portfolio_version_private(platform.portfolio_asset_versions,uuid)','7c8a9f7ba78c0da2b8cc36d876495cd55c947231e2d0b945b9240a2f3d61df91','sql',true,'s',false),
('platform.price_calculate(uuid,uuid,uuid,text)','6996607a3e387ae9371fa902b2d3b713131015dc9cd187d33f0bd6fc911c827f','plpgsql',true,'v',true),
('platform.price_calculate_scoped(app.service_requests,uuid,uuid,text)','4be95710f54c6e7275175818effd02688a0689a1e891902f0a705f89e3503496','plpgsql',true,'v',false),
('platform.price_calculation_immutable()','bc41eaad85c67d6647badfdb8eacbffb2407a870b95857a810d4777f4f17e313','plpgsql',false,'v',false),
('platform.price_history(uuid,uuid,uuid,uuid)','2079f35617b90cc005abe3886efa309244866782716993434018a7798984eca6','plpgsql',true,'v',true),
('platform.price_material(app.service_requests)','a9b53d2bfd12753994f8a25157a92a7b5981909ff3d1bcf66d024c701c5c4a06','plpgsql',false,'s',false),
('platform.price_result(app.price_calculations,boolean)','6381f7bc947ab584f5e606049f6b5ab2652ad77837ea4db8157fcc272a8cd21e','sql',false,'s',false),
('platform.price_schema_profile()','1c7fff96f1e69fbd1cacc4724f15155d596aef3620d3d363c918c215fd18ab9b','sql',true,'s',false),
('platform.price_size_mm(text)','e0393c004439cedd55091f61509fd1fec009e7ebecc99670067a31b2d48b2525','plpgsql',false,'i',false),
('platform.published_knowledge_schema_profile()','93c1c8615c17619929194606686ebd21b7f99afa7698cfd425bb6b65035137f5','sql',true,'s',false),
('platform.quote_acceptance_schema_profile()','d0667d174310adceddd05fbb476fbe3e5694d3dee4d048f34d4e664ae19c7dd9','sql',true,'s',false),
('platform.quote_agreement_owner_read(uuid,uuid,uuid)','adae10a3ee485b175765759e88f5811570f45d6afd858a92aeb3b1a4019104ad','plpgsql',true,'v',false),
('platform.quote_apply_reply(platform.quote_reply_events,app.messages,uuid)','780fa29a83d00d97be7091cc346c0888f1202c0f03c341b95533d3b6ad6889bf','plpgsql',false,'v',false),
('platform.quote_authority(app.quotes,app.conversations,bigint)','d4354fa2822d200c6a2d51caeb801f3c8f8b257d44a471e4dc4dca6bdcf8f231','plpgsql',false,'v',false),
('platform.quote_basis(app.service_requests,timestamptz)','823b48c8cb65e2f4200debd4789f48312bdb9b15926814d8739a63901bfed237','plpgsql',false,'s',false),
('platform.quote_block(app.quotes,app.conversations,bigint)','80fb5643f858a7f98a092812f84d875ab383413916ad36bac8611cfbdc4e40fe','plpgsql',false,'v',false),
('platform.quote_capture_controlled_reply()','8c16a24d2c2bdb45c6a26b40383b6b380862a8e9b0227528699ffb5f1bbf17f4','plpgsql',true,'v',false),
('platform.quote_code(uuid)','8fc9c15c54ca4746ec129f66313ff1da3deaa3453687e9d7c6b002ff72289e48','sql',false,'i',false),
('platform.quote_dispatch_scope(app.quotes,uuid)','bfa5d26e6cd766e8981db5784cafd184b5c35e8c4c55cb0385424fac6cd15e4e','plpgsql',false,'v',false),
('platform.quote_expiry(jsonb)','f16dfa38d17861e0f5037260c25353a87b4bf3f5dd2efc86ff9cca069c81dde4','sql',false,'s',false),
('platform.quote_fail_pending_replies()','5e1cfd52de92fca390bbbfe4ccf35c7bd15d3adf70f7016897230ca22d051240','plpgsql',true,'v',false),
('platform.quote_hash(jsonb)','39c6235034994a21858476d2b5942dbc916a3c733404d7e4e5c07586ef6ef35d','sql',false,'i',false),
('platform.quote_immutable()','53bcffa39c87ef26910c57488f342bd68c05ecf9cba299054439d32631291bbb','plpgsql',false,'v',false),
('platform.quote_lock_reply_queue(uuid,uuid,text)','6ba099f9bb95fc0c58f4071d4b12d99fcf3892d43c85b7f29aa7c376d479bbae','sql',false,'v',false),
('platform.quote_open_at(app.quotes,timestamptz)','7b812455050ac6cb0e23f49402abad1453b7fcc2aee9f7b29cb96648f5edb652','sql',false,'s',false),
('platform.quote_owner_prepare(uuid,uuid,uuid)','9b16651fee7b0b1a3cca342db32a943a85a7e1ab529fcf326224804f2b02d446','plpgsql',true,'v',true),
('platform.quote_owner_read(uuid,uuid,uuid)','c7a8cf423a3128a2da136782ab47f7cbf9961f8ede1e5ef34d9636188e43bdd9','plpgsql',true,'v',true),
('platform.quote_owner_record(uuid,uuid,uuid,jsonb)','5eed73bd3f78afdd869890eb50ddf9e82b2b23c3218d08acef8e975ea07855d5','plpgsql',true,'v',true),
('platform.quote_prepare_scoped(app.service_requests)','f4989a92b020acf76c125600c6beaf3e0ea60067cbaef3b875735cfdb131e04d','plpgsql',true,'v',false),
('platform.quote_process_inbox(uuid,uuid)','bb4b043d21700552b259141ed89941d7f0f261c62c53d7a8eb4764d9876e2efd','plpgsql',true,'v',true),
('platform.quote_process_replay(uuid,uuid)','9a2ae5d4c42fbb493f2aa79e256ea3579a105502979434fc9019eb8e34bc1714','sql',true,'v',true),
('platform.quote_queue(app.quotes,app.conversations,uuid)','63fdf1216fb6aa19de4037ce0423f61f5815858eba26236edfe14f662a1acf18','plpgsql',false,'v',false),
('platform.quote_record_scoped(app.service_requests,uuid,uuid,boolean,jsonb)','87f6d9a5f7841f192bf0bc0409d949e170dba4359165df086e282499f4b5d71b','plpgsql',true,'v',false),
('platform.quote_reply_result(platform.quote_reply_events)','0e7db1e2bb6cdd7fdb548750afcd59fed6d07ddc9fc8fea52bc926a442a9e950','sql',false,'s',false),
('platform.quote_reply_snapshot(uuid,uuid,jsonb,timestamptz)','03dbbb16390abb91c6a0227d6511c1ccc89cc9c6730d34fd57ee0b9c1fa9b5ea','plpgsql',false,'v',false),
('platform.quote_requeue(app.quotes,app.conversations,app.outbox_events,platform.messaging_jobs)','330e2443c2bffcc8d0af4d1c847234f94a780588c8efebfbbd3b9793cc7fd9f1','plpgsql',false,'v',false),
('platform.quote_resume()','172bf601df5b72d2f286241292b9898240d60dfc70a15317881f68fe36fcb48f','plpgsql',false,'v',false),
('platform.quote_schema_profile()','44596761e8003b068323bccc1f0937cb4fcb1116543796096a78de0e267f3f0f','sql',true,'s',false),
('platform.quote_send_begin(uuid,uuid,bigint,bigint,jsonb)','b034f259a4e702c1f2092cb9e5e831ad830b88125048835df8ffbfca2ae12978','plpgsql',true,'v',true),
('platform.quote_send_probe(uuid,uuid)','d301df2b37a96ddbaaffa31ed5a5c9f0098cc989d600252c62049465bdce0c08','plpgsql',true,'v',true),
('platform.quote_timestamp(timestamptz)','2e5b1223a7976432ffbc795a2d2c4c2e6d7770d02529bfd30617d5ad2a06eae5','sql',false,'s',false),
('platform.quote_view(app.quotes,app.conversations)','88295759706eacd2f81becd27a3a4f027cb451c0b16a140c2f3e7a6a06e8dca7','plpgsql',false,'v',false),
('platform.resolve_workspace_membership(uuid,uuid)','8ce9bdd67c17bc83442bea3a5e7a15337a51074e0ea6408855b10542e39ceb39','sql',true,'v',true),
('platform.service_assessment_immutable()','bb7b369ae4c8eff6280b650ddf07efaab07e6a93ef775825115377f9a3156873','plpgsql',false,'v',false),
('platform.service_assessment_material(app.service_requests)','1aa629e9c025608366eb7d01e0d6a3450665b176d1aedcf902d4557709a5c825','plpgsql',true,'s',false),
('platform.service_assessment_prepare(uuid,uuid,uuid,text)','f1093e5b02baef993686df197d29100c6d0a36093a2897c3f204d9da45a81f32','plpgsql',true,'v',true),
('platform.service_assessment_read(uuid,uuid,uuid)','044364ffbd44f3c2b742dfed17186d66cdb5f9b998bad88a1fe04f69a9050f37','plpgsql',true,'v',true),
('platform.service_assessment_record(uuid,uuid,uuid,jsonb)','52c09d0097f037c6e7a14da2277cd469f8287a3ed3d8a5fc9ffb6e480f773116','plpgsql',true,'v',true),
('platform.service_assessment_record_scoped(app.service_requests,uuid,uuid,jsonb)','a2d827c6bde7bc7cf88cdd274c2c3d50929d0dbbf2ce5b260aebc65f97918b76','plpgsql',true,'v',false),
('platform.service_assessment_result(app.service_assessments,boolean)','3497b9c9d3d63bcd3362a523550479c28303c4b1124158e1f608cbeb6a9d3985','sql',false,'s',false),
('platform.service_assessment_schema_profile()','c7c9624fcc55e4ff00a3b4abf7ec8e907f099898ec41a21fc3fbfef5d68493f8','sql',true,'s',false),
('platform.service_assessment_scope(uuid,uuid,uuid)','b72a864f00155d155619709b948da072b15f72902c4c899c9229043ddbffba16','plpgsql',true,'v',false),
('platform.service_intent_result_valid(jsonb)','28daec93bf9fc3289228101392b61adc8d7997d49ee90690e27916f5413f8869','plpgsql',true,'i',false),
('platform.service_request_agent_begin(platform.ai_runs,platform.messaging_jobs,jsonb)','26dce9624a95b65acdc35f26bd0e750ebc6446849aee4765d72b275646d62dde','plpgsql',true,'v',false),
('platform.service_request_agent_continue(uuid,uuid,uuid,text,jsonb)','ad849974bd8411cc01a4a6160098c2cf78796b1b0da6b2048e6b950b2952ebb0','plpgsql',true,'v',true),
('platform.service_request_agent_mentions(text,text)','97c70308f40a345666e0acb1f7031c0a74ce96805293620fe803eba2cee6f33a','sql',false,'i',false),
('platform.service_request_agent_must_finish()','13bd81c537e2a36a70eb5e4b3d04a88724cc55134d10323049ad62d6da825cbd','plpgsql',true,'v',false),
('platform.service_request_agent_pin(platform.ai_runs)','a3f11e1d66132c3a46a32ada2d4681ffa0eca550a98da47b559b47fb87a71997','sql',true,'s',false),
('platform.service_request_agent_prepare(platform.ai_runs,app.conversations,jsonb,boolean)','374e3e4c5282df8cf65376f0d45ed51783fb5ff5553ea1989f500dc341a3fdb0','plpgsql',true,'v',false),
('platform.service_request_agent_result(platform.ai_runs)','bcb3be996923062fec341f074743c803cc302719e7751d8f63bfb39ed3486915','sql',true,'s',false),
('platform.service_request_agent_source_available(app.conversations,uuid,uuid)','e3c88b4802a9e2a10609d709028d357c55cccc97ed25eb6d0b0981975df6e863','sql',true,'s',false),
('platform.service_request_command(app.conversations,text,text,uuid,jsonb)','0888dee140c0e7f35cf2a95a15709a9f040ce9447ca2f402be1ffa340858623f','plpgsql',true,'v',false),
('platform.service_request_complex_work(app.conversations,uuid,text,jsonb)','9a9db2ad05f6a6001fd822bfff5360ed0843e87f5ab49e40b7559a6fdea023db','plpgsql',true,'s',false),
('platform.service_request_create_scoped(app.conversations,uuid,uuid,text,jsonb)','434cca9a7cf8b6bc842bb3693aec20d3c95827c7bfeb25e2cc95684c0bd45c3a','plpgsql',true,'v',false),
('platform.service_request_fact_available(app.conversations,uuid,jsonb)','63e601011da084f50e8774622a3355b1d1decc5d25662826596dc327696bf688','sql',true,'s',false),
('platform.service_request_intake(app.conversations,jsonb)','3f61b1943c618871b3448bce6d5a35df1bc11cfe0f2ba622fbe0844e3c6c1365','plpgsql',true,'s',false),
('platform.service_request_owner_create(uuid,uuid,text,jsonb)','79ddd82635551cbf7fe74e4de51b09a498ca6ae51add762337e203a051fee862','plpgsql',true,'v',true),
('platform.service_request_owner_list(uuid,uuid)','54c403414b2ca804d89c0dcc5322a50424ffe1a66f361063190752b505ca9434','plpgsql',true,'v',true),
('platform.service_request_owner_read(uuid,uuid,uuid)','4d7a6b09b54341176b12f315c6c08d21c654f891403bb93216070890cf3b6ea3','plpgsql',true,'v',true),
('platform.service_request_owner_revise(uuid,uuid,uuid,text,jsonb)','e96fc9b11f3b002d59496b720d4f44e2ae712334a56c090731eef86487282819','plpgsql',true,'v',true),
('platform.service_request_owner_scope(uuid,uuid)','68d56b048f60af95d6cc0280d2219ac18f467cb18403f5e252157533c1e26a8a','plpgsql',true,'v',false),
('platform.service_request_revise_scoped(app.conversations,uuid,uuid,uuid,text,jsonb)','909375139a73d2c4f729a357bb724b5f520da1a6d28e58080d63a87a3c6051f8','plpgsql',true,'v',false),
('platform.service_request_schema_profile()','b6fb012dec5fcc2e74b1ed83ff11a3c2d02ac82cdb819a7062a6d70abdbd95a0','sql',true,'s',false),
('platform.service_request_summary(jsonb,jsonb,text)','69b1c509de00d7e8b7c6efed748390c9f973fade292e4d91b2d5cec2df7e76d4','plpgsql',false,'i',false),
('platform.telegram_begin_send(uuid,uuid,bigint,bigint,jsonb)','c8f15c23837fa40b86451574ee3e04cc4292dd91b2929a891424e0d8acec556d','plpgsql',true,'v',true),
('platform.telegram_can_send(uuid,uuid,uuid,boolean)','b273ad02ca6825bdf6b037173c3be840a615d551283c3e922357bee3f7f16811','plpgsql',true,'v',false),
('platform.telegram_fingerprint(text,jsonb)','449929a9e41d6e4f38d30341fcb7c7a488d55f06169dbaca2c18df461effdc06','plpgsql',false,'i',false),
('platform.telegram_fingerprint_v2(text,jsonb)','4499d0bd8bc0ad010d856d3e20b21847a9cfedfaeced5c14ace118443c2a940f','plpgsql',false,'i',false),
('platform.telegram_ingest(text,jsonb,uuid)','0b4d1cc97c47522e9abde484362aad3cd4967ae9c256e7719d310c09702f7c09','plpgsql',true,'v',true),
('platform.telegram_ingest_own_text(text,jsonb,uuid)','c5445bb9edf14e94c96140f95a635056f425b8ac505fb8f3b026ea10cb0161d0','plpgsql',true,'v',true),
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
('platform.turn_material()','0bd75f21bfe65124a70db5e7021db814db82ea4fc829ef83528932e35d033df0','plpgsql',true,'v',false),
('platform.turn_member_check()','8cbbd5b8ccd97858edc24ba68fd904e5b4af3068b355e506d7d5cc03af5b6293','plpgsql',true,'v',false),
('platform.turn_members_consistent()','3acccfede293794fcc84890da99535a2730217fd1f11eb37c7ed153e2c675405','plpgsql',true,'v',false),
('platform.turn_preflight(platform.messaging_jobs,boolean,boolean)','6cb38ed3df6e7d1be1f89d8cbf9cbcf537097d72156dbeeed960e088f7b4ed9a','plpgsql',true,'v',false),
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
columns_expected(table_name,column_names) AS (VALUES ('app.approval_requests',ARRAY['workspace_id','id','business_id','conversation_id','client_id','request_id','request_revision','assignee_user_account_id','membership_version','account_version','action','basis','created_at','expires_at','retired_at','retired_reason','retired_by']::text[]),
('app.audit_events',ARRAY['workspace_id','audit_event_id','occurred_at','actor_kind','actor_user_account_id','correlation_id','event_type','object_type','object_id','object_version','payload','billing_account_object_id','message_object_id','conversation_object_id','conversation_control_generation','escalation_object_id','escalation_operation','material_target_id','material_source_receipt_id','native_revision_id','native_policy_receipt_id','native_connection_id','native_conversation_id']::text[]),
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
('app.owner_decisions',ARRAY['workspace_id','id','approval_id','actor_user_account_id','operation','submitted','decided_at','authorized_action','amount_minor','lower_minor','upper_minor','occupied_minutes','price_reference_id','duration_reference_id']::text[]),
('app.price_calculations',ARRAY['workspace_id','id','business_id','request_id','request_revision','release_id','activation_version','authority_sha256','currency','policy','size_fact','size_mm','steps','outcome','authority','reason','amount_minor','lower_minor','upper_minor','actor_user_account_id','correlation_id','created_at']::text[]),
('app.quote_acceptances',ARRAY['workspace_id','id','request_id','quote_id','conversation_id','connection_id','message_id','inbox_id','direction','content_type','source_version','accepted_at']::text[]),
('app.quotes',ARRAY['workspace_id','id','business_id','conversation_id','client_id','request_id','request_revision','version','code','material','basis_sha256','terms_sha256','text','release_id','prepared_by','membership_version','account_version','created_at','expires_at']::text[]),
('app.service_assessments',ARRAY['workspace_id','id','business_id','request_id','request_revision','service_id','release_id','activation_version','authority_sha256','owner_handoff','duration_policy','rules','evidence','unavailable_fields','outcome','reason','field','rule_id','limit_value','size_mm','occupied_minutes','actor_user_account_id','correlation_id','created_at','complex_work']::text[]),
('app.service_orders',ARRAY['workspace_id','id','request_id','acceptance_id']::text[]),
('app.service_requests',ARRAY['workspace_id','id','business_id','conversation_id','client_id','intent_message_id','intent_source_version','release_id','service_id','service_name','template_revision','state','revision','facts','missing','conflicts','question','created_at','complex_work']::text[]),
('app.service_sessions',ARRAY['workspace_id','id','order_id','status','scheduled_at']::text[]),
('platform.ai_deliveries',ARRAY['workspace_id','job_id','source_job_id','source_claim_hash','connection_id','turn_id','turn_revision','kind','step','run_id','selected_kind','message_id','outbox_id','send_job_id','escalation_id','intent_context_version','created_at','provider_session_id','knowledge_pin','search_pin','portfolio_pin','media_pin']::text[]),
('platform.ai_provider_calls',ARRAY['workspace_id','run_id','sequence','claim_hash','attempt_count','budget','completion','reserved_at','completed_at','portfolio_session_id']::text[]),
('platform.ai_provider_sessions',ARRAY['id','workspace_id','connection_id','conversation_id','client_id','chat_id','bot_identity','data_profile','starts_at','expires_at','max_calls','max_rub','review_sha256','review_checked_at','config','active','created_at']::text[]),
('platform.ai_runs',ARRAY['workspace_id','id','job_id','connection_id','conversation_id','client_id','business_id','kind','step','turn_id','turn_revision','resume_receipt_id','control_generation','binding','snapshot','snapshot_digest','storage_fingerprint','config','config_fingerprint','deadline','calls_used','reads_used','tokens_reserved','cost_reserved','read_audit','result','selected_at','winning_claim_hash','created_at','knowledge_pin','active_projection','knowledge_release_id','search_pin','search_refs','search_build_id','portfolio_pin','media_pin','portfolio_refs','portfolio_session_id','portfolio_build_id','delivery_read_audit','intake_pin','service_request_pin']::text[]),
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
('platform.quote_delivery_intents',ARRAY['workspace_id','quote_id','connection_id','control_generation','message_id','outbox_id','send_job_id','hold_reason']::text[]),
('platform.quote_reply_events',ARRAY['workspace_id','inbox_id','conversation_id','client_id','quote_id','kind','control_generation','outcome','message_id','claim_token','clarification_quote_ids']::text[]),
('platform.saas_plan_revisions',ARRAY['plan_revision_id','plan_id','revision','publication_state','published_at','created_at']::text[]),
('platform.saas_plans',ARRAY['plan_id','code','display_name','status','created_at']::text[]),
('platform.service_request_agent_intents',ARRAY['workspace_id','run_id','actor_kind','owner_user_account_id','source_message_id','request_id','request_revision','prepare_requested','approval_requested','approval_id','quote_id','quote_input','transaction_id','lease_until','phase']::text[]),
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
        (SELECT count(*) FROM functions)=407 AND (SELECT count(DISTINCT to_regprocedure(signature)) FROM expected)=406
        AND NOT EXISTS(SELECT 1 FROM expected e LEFT JOIN functions f ON f.oid=to_regprocedure(e.signature)
          WHERE f.oid IS NULL OR encode(sha256(convert_to(f.prosrc,'UTF8')),'hex')<>e.body_hash OR f.lanname<>e.language
            OR f.prosecdef<>e.security_definer OR f.provolatile::text<>e.volatility OR f.proowner<>'asm_migrator'::regrole
            OR has_function_privilege('asm_runtime',f.oid,'EXECUTE')<>e.runtime_execute
            OR f.proconfig IS DISTINCT FROM ARRAY['search_path=pg_catalog, pg_temp']
            OR EXISTS(SELECT 1 FROM aclexplode(f.proacl) a WHERE a.grantee=0 AND a.privilege_type='EXECUTE'))
        AND EXISTS(SELECT 1 FROM functions f WHERE f.oid='platform.service_intent_schema_profile()'::regprocedure
          AND f.proowner='asm_migrator'::regrole AND f.lanname='sql' AND f.prosecdef AND f.provolatile='s'
          AND f.proconfig=ARRAY['search_path=pg_catalog, pg_temp'] AND NOT has_function_privilege('asm_runtime',f.oid,'EXECUTE')
          AND NOT EXISTS(SELECT 1 FROM aclexplode(f.proacl) a WHERE a.grantee=0 AND a.privilege_type='EXECUTE'))
        AND EXISTS(SELECT 1 FROM pg_roles WHERE rolname='asm_runtime' AND rolcanlogin AND NOT rolsuper AND NOT rolbypassrls
          AND NOT rolinherit AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolreplication)
        AND NOT EXISTS(SELECT 1 FROM pg_auth_members WHERE member='asm_runtime'::regrole)
        AND (SELECT count(*) FROM tables)=86 AND NOT EXISTS(SELECT 1 FROM columns_expected e LEFT JOIN tables t ON t.name=e.table_name
          WHERE t.oid IS NULL OR t.columns IS DISTINCT FROM e.column_names)
        AND NOT EXISTS(SELECT 1 FROM tables WHERE name IN ('platform.service_request_agent_intents','platform.business_configuration_state','platform.business_configuration_releases','platform.business_configuration_receipts','platform.human_context_observations','platform.human_context_reconciliations','platform.human_context_policy_receipts','platform.ai_runs','platform.ai_provider_calls','platform.ai_deliveries','platform.ai_provider_sessions','platform.knowledge_sources','platform.knowledge_revisions','platform.knowledge_chunks','platform.knowledge_builds','platform.knowledge_build_chunks','platform.knowledge_release_builds','platform.knowledge_embedding_calls','platform.portfolio_assets','platform.portfolio_asset_versions','platform.portfolio_ai_sessions','platform.vision_analyses','platform.portfolio_items','platform.portfolio_revisions','platform.portfolio_builds','platform.portfolio_build_items','platform.portfolio_release_builds','platform.portfolio_delivery_intents','app.service_assessments','app.price_calculations','app.approval_requests','app.owner_decisions','app.quotes','platform.quote_delivery_intents','app.quote_acceptances','app.service_orders','app.service_sessions','platform.quote_reply_events')
          AND (relowner<>'asm_migrator'::regrole OR NOT relrowsecurity OR NOT relforcerowsecurity OR has_table_privilege('asm_runtime',oid,'SELECT,INSERT,UPDATE,DELETE')))
        AND (SELECT version_num FROM platform.alembic_version)='0031' AS valid),
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
      SELECT jsonb_build_object('schema_revision','0031','valid',coalesce(v.valid,false)
        AND encode(sha256(convert_to((c.value-'functions')::text,'UTF8')),'hex')='102f76177a579c854fafc90752f6dce2a1a57c98c0a82a657de79fa4570b2a39',
        'profile_sha256',encode(sha256(convert_to(E'asm:m3:native_schema:v1\n'||c.value::text,'UTF8')),'hex')) FROM validity v CROSS JOIN catalog c $$"""


def _set_constraints(constraints):
    for (table, name), definition in constraints.items():
        op.execute(
            f"ALTER TABLE {table} DROP CONSTRAINT {name}, ADD CONSTRAINT {name} {definition}"
        )


def upgrade():
    op.execute("""ALTER TABLE platform.ai_runs ADD COLUMN service_request_pin text
      CHECK(service_request_pin IS NULL OR config->>'prompt_revision'='conversation_v8'
        AND service_request_pin ~ '^[0-9a-f]{64}$')""")
    op.execute(RESULT_VALID)
    op.execute(
        "REVOKE ALL ON FUNCTION platform.service_intent_result_valid(jsonb) FROM PUBLIC,asm_runtime"
    )
    _set_constraints(V8_CONSTRAINTS)
    upgrade_agent_domain()
    for sql in V8_FUNCTIONS.values():
        op.execute(sql)
    op.execute(PROFILE)
    op.execute(
        "REVOKE ALL ON FUNCTION platform.service_intent_schema_profile() FROM PUBLIC,asm_runtime"
    )


def downgrade():
    op.execute(
        "LOCK TABLE platform.ai_runs,platform.portfolio_ai_sessions IN ACCESS EXCLUSIVE MODE"
    )
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM platform.ai_runs WHERE config->>'prompt_revision'='conversation_v8')
        OR EXISTS(SELECT 1 FROM platform.portfolio_ai_sessions WHERE profile_id='SYNTHETIC_SERVICE_INTENTS_V1')
      THEN RAISE EXCEPTION 'SERVICE_INTENT_DURABLE_DATA' USING ERRCODE='55000'; END IF;
    END $$""")
    for sql in V7_FUNCTIONS.values():
        op.execute(sql)
    op.execute("DROP FUNCTION platform.service_intent_schema_profile()")
    downgrade_agent_domain()
    _set_constraints(V7_CONSTRAINTS)
    op.execute("DROP FUNCTION platform.service_intent_result_valid(jsonb)")
    op.execute("ALTER TABLE platform.ai_runs DROP COLUMN service_request_pin")
