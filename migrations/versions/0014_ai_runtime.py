"""DB-only synthetic AI authority. Application readiness deliberately stays at 0013."""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

TURN_CHECK = """(kind NOT IN ('PROCESS_TURN','ESCALATION_TIMER') AND turn_revision IS NULL AND step IS NULL AND turn_outcome IS NULL) OR
 (kind='PROCESS_TURN' AND turn_revision IS NOT NULL AND turn_revision>0 AND step IS NOT NULL
 AND step IN ('GROUP','MEDIA','TEST_CONSUME','GUARDED_TEXT','ESCALATE_OWNER'{ai})
 AND (turn_outcome IS NULL OR turn_outcome IN ('GROUPED','WAITING_MEDIA','OBSERVED','STALE','SUPERSEDED','FAILED','ACCEPTED','NOT_ALLOWED','ALREADY_ACCEPTED','ESCALATED','ALREADY_ESCALATED','WAITING_EXISTS')))
 OR (kind='ESCALATION_TIMER' AND turn_revision IS NULL AND turn_outcome IS NULL AND step IS NOT NULL AND step IN ('REMIND_1','REMIND_2','EXPIRE'))"""

FUNCTIONS = (
    "ai_runtime_replay(uuid,uuid,jsonb)",
    "ai_runtime_command(uuid,uuid,text,jsonb)",
    "ai_runtime_current(platform.messaging_jobs,jsonb)",
    "ai_runtime_view(platform.ai_runs)",
    "ai_runtime_receipt(platform.ai_runs)",
    "ai_runtime_config_valid(jsonb)",
    "ai_runtime_result_valid(jsonb)",
    "ai_runtime_completion_valid(jsonb)",
)
PUBLIC = FUNCTIONS[:2]


def _job_delta(forward: bool) -> None:
    op.execute(
        "ALTER TABLE platform.messaging_jobs DROP CONSTRAINT messaging_jobs_turn_check, "
        "ADD CONSTRAINT messaging_jobs_turn_check CHECK("
        + TURN_CHECK.format(ai=",'AI_GENERATE'" if forward else "")
        + ")"
    )
    old = "j.step NOT IN ('GUARDED_TEXT','ESCALATE_OWNER')"
    new = "j.step NOT IN ('GUARDED_TEXT','ESCALATE_OWNER','AI_GENERATE')"
    source, target = (old, new) if forward else (new, old)
    # Retain the installed 0013 body, including native work rules. Change only
    # terminal retry's canonical-turn mutation for the new independent AI job.
    op.execute(f"""DO $patch$ DECLARE body text; needle text:=$needle${source}$needle$;
      BEGIN SELECT pg_get_functiondef('platform.messaging_reschedule(uuid,text,boolean,integer,boolean)'::regprocedure) INTO body;
        IF (length(body)-length(replace(body,needle,'')))/length(needle)<>1 THEN
          RAISE EXCEPTION 'AI_RUNTIME_RESCHEDULE_SOURCE_MISMATCH'; END IF;
        EXECUTE replace(body,needle,$replacement${target}$replacement$);
      END $patch$""")


def upgrade() -> None:
    op.execute("LOCK TABLE platform.messaging_jobs IN ACCESS EXCLUSIVE MODE")
    _job_delta(True)
    op.execute("""CREATE TABLE platform.ai_runs(
      workspace_id uuid NOT NULL, id uuid NOT NULL DEFAULT uuidv7(), job_id uuid NOT NULL,
      connection_id uuid NOT NULL, conversation_id uuid NOT NULL, client_id uuid NOT NULL, business_id uuid NOT NULL,
      kind text NOT NULL DEFAULT 'PROCESS_TURN' CHECK(kind='PROCESS_TURN'),
      step text NOT NULL DEFAULT 'AI_GENERATE' CHECK(step='AI_GENERATE'),
      turn_id uuid NOT NULL, turn_revision bigint NOT NULL CHECK(turn_revision>0),
      resume_receipt_id uuid NOT NULL, control_generation bigint NOT NULL CHECK(control_generation>0),
      binding jsonb NOT NULL CHECK(jsonb_typeof(binding)='object' AND octet_length(binding::text)<=4096),
      snapshot jsonb NOT NULL CHECK(jsonb_typeof(snapshot)='object' AND octet_length(snapshot::text)<=262144),
      snapshot_digest text NOT NULL CHECK(snapshot_digest ~ '^[0-9a-f]{64}$'),
      storage_fingerprint text NOT NULL CHECK(storage_fingerprint=encode(sha256(convert_to(snapshot::text,'UTF8')),'hex')),
      config jsonb NOT NULL CHECK(jsonb_typeof(config)='object' AND octet_length(config::text)<=8192),
      config_fingerprint text NOT NULL CHECK(config_fingerprint=encode(sha256(convert_to(config::text,'UTF8')),'hex')),
      deadline timestamptz NOT NULL CHECK(isfinite(deadline)),
      calls_used integer NOT NULL DEFAULT 0 CHECK(calls_used BETWEEN 0 AND 2),
      reads_used integer NOT NULL DEFAULT 0 CHECK(reads_used BETWEEN 0 AND 1),
      tokens_reserved integer NOT NULL DEFAULT 0 CHECK(tokens_reserved BETWEEN 0 AND 417792),
      cost_reserved numeric(18,9) NOT NULL DEFAULT 0 CHECK(cost_reserved>=0),
      read_audit jsonb CHECK(jsonb_typeof(read_audit)='object' AND octet_length(read_audit::text)<=1024),
      result jsonb, selected_at timestamptz CHECK(isfinite(selected_at)), winning_claim_hash bytea,
      created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      PRIMARY KEY(workspace_id,id), UNIQUE(workspace_id,job_id), UNIQUE(workspace_id,turn_id,turn_revision),
      FOREIGN KEY(workspace_id,job_id,connection_id,kind,turn_id,turn_revision,step)
        REFERENCES platform.messaging_jobs(workspace_id,id,connection_id,kind,turn_id,turn_revision,step) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,turn_id,connection_id,conversation_id)
        REFERENCES app.conversation_turns(workspace_id,id,connection_id,conversation_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,conversation_id,client_id)
        REFERENCES app.conversations(workspace_id,id,client_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,connection_id,business_id)
        REFERENCES app.channel_connections(workspace_id,id,business_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,resume_receipt_id,conversation_id,client_id,control_generation)
        REFERENCES platform.conversation_control_receipts(workspace_id,id,conversation_id,client_id,accepted_generation) ON DELETE RESTRICT,
      CHECK((reads_used=0 AND read_audit IS NULL) OR (reads_used=1 AND read_audit IS NOT NULL)),
      CHECK((result IS NULL AND selected_at IS NULL AND winning_claim_hash IS NULL) OR
        (result IS NOT NULL AND jsonb_typeof(result)='object' AND octet_length(result::text)<=20000
         AND selected_at IS NOT NULL AND winning_claim_hash IS NOT NULL AND octet_length(winning_claim_hash)=32)))""")
    op.execute("""CREATE TABLE platform.ai_provider_calls(
      workspace_id uuid NOT NULL, run_id uuid NOT NULL, sequence integer NOT NULL CHECK(sequence BETWEEN 1 AND 2),
      claim_hash bytea NOT NULL CHECK(octet_length(claim_hash)=32), attempt_count integer NOT NULL CHECK(attempt_count BETWEEN 1 AND 5),
      budget jsonb NOT NULL CHECK(jsonb_typeof(budget)='object' AND octet_length(budget::text)<=1024),
      completion jsonb NOT NULL DEFAULT '{"kind":"UNKNOWN","usage":{"input_tokens":null,"output_tokens":null},"cost":{"status":"UNKNOWN","amount":null,"currency":null},"error":null}',
      reserved_at timestamptz NOT NULL DEFAULT clock_timestamp(), completed_at timestamptz CHECK(isfinite(completed_at)),
      PRIMARY KEY(workspace_id,run_id,sequence),
      FOREIGN KEY(workspace_id,run_id) REFERENCES platform.ai_runs(workspace_id,id) ON DELETE RESTRICT,
      CHECK(jsonb_typeof(completion)='object' AND octet_length(completion::text)<=2048),
      CHECK(completed_at IS NOT NULL OR completion->>'kind'='UNKNOWN'))""")
    for table in ("ai_runs", "ai_provider_calls"):
        op.execute(f"ALTER TABLE platform.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE platform.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY ai_migrator ON platform.{table} TO asm_migrator USING(true) WITH CHECK(true)"
        )
        op.execute(f"REVOKE ALL ON platform.{table} FROM PUBLIC,asm_runtime")
    _validators()
    op.execute(
        "ALTER TABLE platform.ai_runs ADD CONSTRAINT ai_run_config CHECK(platform.ai_runtime_config_valid(config)), ADD CONSTRAINT ai_run_result CHECK(result IS NULL OR platform.ai_runtime_result_valid(result))"
    )
    op.execute(
        "ALTER TABLE platform.ai_provider_calls ADD CONSTRAINT ai_call_completion CHECK(platform.ai_runtime_completion_valid(completion))"
    )
    _current()
    _views()
    _command()
    _replay()
    for signature in FUNCTIONS:
        op.execute(f"REVOKE ALL ON FUNCTION platform.{signature} FROM PUBLIC,asm_runtime")
    for signature in PUBLIC:
        op.execute(f"GRANT EXECUTE ON FUNCTION platform.{signature} TO asm_runtime")


def _validators() -> None:
    op.execute(r"""CREATE FUNCTION platform.ai_runtime_config_valid(p jsonb) RETURNS boolean
      LANGUAGE plpgsql IMMUTABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE r jsonb:=p->'route'; l jsonb:=p->'limits'; v text;
      BEGIN
        IF NOT platform.material_object(p,ARRAY['revision','route','prompt_revision','schema_revision','limits']) OR
          NOT platform.material_object(r,ARRAY['branch','adapter','execution','endpoint','model','upstream','eligibility']) OR
          NOT platform.material_object(l,ARRAY['model_calls','read_executions','input_bytes','output_bytes','input_tokens','output_tokens','total_tokens','duration_seconds','currency','cost_budget','call_cost_reservation']) THEN RETURN false; END IF;
        IF p->>'prompt_revision' IS DISTINCT FROM 'conversation_v2' OR p->>'schema_revision' IS DISTINCT FROM 'conversation_result_v1'
          OR r->>'execution' IS DISTINCT FROM 'FAKE' OR r->>'adapter' IS DISTINCT FROM 'fake'
          OR r->>'eligibility' IS DISTINCT FROM 'EVAL_ONLY' OR r->>'endpoint' IS DISTINCT FROM 'https://fake.invalid/v1'
          OR r->>'branch' NOT IN ('RU_AGGREGATOR','DIRECT_PROVIDER') THEN RETURN false; END IF;
        FOREACH v IN ARRAY ARRAY[p->>'revision',r->>'model',r->>'upstream'] LOOP
          IF v IS NULL OR v !~ '^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$' THEN RETURN false; END IF;
        END LOOP;
        FOREACH v IN ARRAY ARRAY['model_calls','read_executions','input_bytes','output_bytes','input_tokens','output_tokens','total_tokens'] LOOP
          IF jsonb_typeof(l->v) IS DISTINCT FROM 'number' OR l->>v !~ '^[0-9]{1,7}$' THEN RETURN false; END IF;
        END LOOP;
        RETURN coalesce((l->>'model_calls')::int BETWEEN 0 AND 2 AND (l->>'read_executions')::int BETWEEN 0 AND 1
          AND (l->>'input_bytes')::int BETWEEN 1 AND 131072 AND (l->>'output_bytes')::int BETWEEN 1 AND 65536
          AND (l->>'input_tokens')::int BETWEEN 1 AND 131072 AND (l->>'output_tokens')::int BETWEEN 1 AND 8192
          AND (l->>'total_tokens')::int BETWEEN 0 AND 417792 AND jsonb_typeof(l->'duration_seconds')='number'
          AND (l->>'duration_seconds')::numeric>0 AND (l->>'duration_seconds')::numeric<=120
          AND l->>'currency' IN ('RUB','USD') AND jsonb_typeof(l->'cost_budget')='string'
          AND jsonb_typeof(l->'call_cost_reservation')='string'
          AND l->>'cost_budget' ~ '^[0-9]{1,18}(\.[0-9]{1,18})?([eE][+-]?[0-9]{1,2})?$'
          AND l->>'call_cost_reservation' ~ '^[0-9]{1,18}(\.[0-9]{1,18})?([eE][+-]?[0-9]{1,2})?$'
          AND (l->>'cost_budget')::numeric BETWEEN 0 AND 1000000 AND (l->>'call_cost_reservation')::numeric BETWEEN 0 AND 1000000
          AND (l->>'cost_budget')::numeric=round((l->>'cost_budget')::numeric,9)
          AND (l->>'call_cost_reservation')::numeric=round((l->>'call_cost_reservation')::numeric,9),false);
      EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN RETURN false;
      END $$""")
    op.execute(r"""CREATE FUNCTION platform.ai_runtime_result_valid(p jsonb) RETURNS boolean
      LANGUAGE plpgsql IMMUTABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE k text:=p->>'kind'; t text:=p->>'text'; r text:=p->>'reason';
        spaces text:=chr(9)||chr(10)||chr(11)||chr(12)||chr(13)||chr(28)||chr(29)||chr(30)||chr(31)||chr(32)||chr(133)||chr(160)||chr(5760)||chr(8192)||chr(8193)||chr(8194)||chr(8195)||chr(8196)||chr(8197)||chr(8198)||chr(8199)||chr(8200)||chr(8201)||chr(8202)||chr(8232)||chr(8233)||chr(8239)||chr(8287)||chr(12288);
      BEGIN
        RETURN coalesce(platform.material_object(p,ARRAY['kind','text','reason'])
          AND (p->'text'='null'::jsonb OR (jsonb_typeof(p->'text')='string' AND char_length(t) BETWEEN 1 AND 4000 AND btrim(t,spaces)<>''))
          AND (p->'reason'='null'::jsonb OR (jsonb_typeof(p->'reason')='string' AND char_length(r) BETWEEN 1 AND 500 AND btrim(r,spaces)<>''))
          AND ((k='reply' AND t IS NOT NULL AND r IS NULL) OR (k='handoff' AND r IS NOT NULL) OR (k='no_reply' AND t IS NULL AND r IS NOT NULL)),false);
      END $$""")
    op.execute(r"""CREATE FUNCTION platform.ai_runtime_completion_valid(p jsonb) RETURNS boolean
      LANGUAGE plpgsql IMMUTABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE u jsonb:=p->'usage'; c jsonb:=p->'cost'; v text;
      BEGIN
        IF NOT platform.material_object(p,ARRAY['kind','usage','cost','error']) OR NOT platform.material_object(u,ARRAY['input_tokens','output_tokens'])
          OR NOT platform.material_object(c,ARRAY['status','amount','currency']) THEN RETURN false; END IF;
        FOREACH v IN ARRAY ARRAY['input_tokens','output_tokens'] LOOP
          IF u->v<>'null'::jsonb AND (jsonb_typeof(u->v)<>'number' OR u->>v !~ '^[0-9]{1,8}$' OR (u->>v)::numeric>10000000) THEN RETURN false; END IF;
        END LOOP;
        RETURN coalesce(p->>'kind' IN ('OUTPUT','TOOLS','REFUSAL','TRUNCATED','ERROR','UNKNOWN')
          AND (p->'error'='null'::jsonb OR p->>'error' IN ('ADAPTER_ERROR','CANCELLED','INVALID_RESPONSE'))
          AND (c->'currency'='null'::jsonb OR c->>'currency' IN ('RUB','USD'))
          AND ((c->>'status'='UNKNOWN' AND c->'amount'='null'::jsonb)
            OR (c->>'status' IN ('CONFIRMED','ESTIMATE') AND c->>'currency' IN ('RUB','USD')
              AND jsonb_typeof(c->'amount')='string' AND c->>'amount' ~ '^[0-9]{1,9}(\.[0-9]{1,9})?$')),false);
      EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN RETURN false;
      END $$""")


def _current() -> None:
    op.execute("""CREATE FUNCTION platform.ai_runtime_current(j platform.messaging_jobs,saved jsonb) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE t app.conversation_turns%ROWTYPE; c app.conversations%ROWTYPE;
        r platform.conversation_control_receipts%ROWTYPE; s jsonb; b jsonb; allowed boolean;
      BEGIN
        IF current_database() NOT IN ('asm_local','asm_test') OR j.kind<>'PROCESS_TURN' OR j.step NOT IN ('TEST_CONSUME','AI_GENERATE') THEN
          RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
        SELECT * INTO STRICT t FROM app.conversation_turns WHERE (workspace_id,id)=(j.workspace_id,j.turn_id);
        SELECT * INTO STRICT c FROM app.conversations WHERE (workspace_id,id)=(j.workspace_id,t.conversation_id);
        SELECT * INTO r FROM platform.conversation_control_receipts WHERE workspace_id=j.workspace_id
          AND conversation_id=c.id AND accepted_generation=t.control_generation AND operation='RESUME';
        IF r.id IS NULL OR platform.messaging_lock_owner(j.workspace_id,r.actor_user_account_id) IS NOT TRUE THEN
          RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
        PERFORM 1 FROM app.businesses WHERE (workspace_id,id)=(j.workspace_id,c.business_id) AND status='ACTIVE' FOR SHARE;
        IF NOT FOUND THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
        PERFORM 1 FROM app.channel_connections WHERE (workspace_id,id,business_id)=(j.workspace_id,j.connection_id,c.business_id)
          AND (provider='CONTROLLED' OR (current_database()='asm_test' AND provider='TELEGRAM'))
          AND status='ACTIVE' FOR SHARE;
        IF NOT FOUND THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
        PERFORM platform.messaging_lock_billing_workspace(j.workspace_id);
        SELECT * INTO STRICT c FROM app.conversations WHERE (workspace_id,id)=(j.workspace_id,t.conversation_id) FOR NO KEY UPDATE;
        SELECT * INTO STRICT t FROM app.conversation_turns WHERE (workspace_id,id)=(j.workspace_id,j.turn_id) FOR NO KEY UPDATE;
        PERFORM 1 FROM app.clients WHERE (workspace_id,id)=(j.workspace_id,c.client_id) FOR SHARE;
        IF NOT FOUND THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
        PERFORM platform.messaging_guard(j.id,j.claim_token);
        IF (t.connection_id,c.connection_id,t.revision,t.state) IS DISTINCT FROM (j.connection_id,j.connection_id,j.turn_revision,'READY')
          OR platform.conversation_turn_activation_matches(j.workspace_id,t.id) IS NOT TRUE
          OR platform.material_turn_usable(j.workspace_id,t.id) IS NOT TRUE
          OR (r.conversation_id,r.client_id,r.accepted_generation,r.activation_fence_seq) IS DISTINCT FROM
             (c.id,c.client_id,t.control_generation,t.activation_fence_seq) THEN
          RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
        BEGIN allowed:=platform.messaging_manual_send_allowed(j.workspace_id);
        EXCEPTION WHEN SQLSTATE 'P2301' THEN RAISE EXCEPTION 'DEPENDENCY_UNAVAILABLE' USING ERRCODE='P2001'; END;
        IF allowed IS NOT TRUE OR EXISTS(SELECT 1 FROM app.escalations WHERE workspace_id=j.workspace_id AND conversation_id=c.id AND status='PENDING') THEN
          RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
        IF platform.human_context_admission(j.workspace_id,c.id,saved-'code'-'job_id') IS DISTINCT FROM 'CURRENT' THEN
          RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
        s:=platform.turn_snapshot(j.workspace_id,t.id);
        IF s IS NULL OR s->>'schema_version' NOT IN ('2','3') THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
        IF saved IS NOT NULL AND s IS DISTINCT FROM (saved-'code'-'job_id') THEN
          RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
        b:=jsonb_build_object('workspace_id',j.workspace_id,'client_id',c.client_id,'conversation_id',c.id,
          'business_id',c.business_id,'connection_id',j.connection_id,'job_id',j.id,'turn_id',t.id,'turn_revision',t.revision,
          'context_version',c.version,'control_generation',t.control_generation,'activation_fence_seq',t.activation_fence_seq,
          'resume_receipt_id',r.id,'snapshot_digest',s->>'snapshot_digest','native',
          CASE WHEN s->>'schema_version'='2' THEN NULL ELSE jsonb_build_object(
            'revision_id',s->'human_context'->>'revision_id','revision_no',(s->'human_context'->>'revision_no')::bigint,
            'policy_epoch',(s->>'context_policy_epoch')::bigint,'observation_epoch',(s->>'human_observation_epoch')::bigint,
            'reviewed_ingress_checkpoint',(s->'human_context'->>'reviewed_ingress_checkpoint')::bigint,
            'reviewed_input_state_hash',s->'human_context'->>'reviewed_input_state_hash') END);
        RETURN jsonb_build_object('binding',b,'snapshot',s||jsonb_build_object('code','SNAPSHOT','job_id',j.id));
      END $$""")


def _views() -> None:
    op.execute("""CREATE FUNCTION platform.ai_runtime_view(r platform.ai_runs) RETURNS jsonb
      LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      SELECT jsonb_build_object('run_id',r.id,'binding',r.binding,'snapshot',r.snapshot,'storage_fingerprint',r.storage_fingerprint,
        'config',r.config,'deadline',r.deadline,'reads_used',r.reads_used,'budget',jsonb_build_object(
          'calls_used',r.calls_used,'reads_reserved',r.reads_used,'tokens_reserved',r.tokens_reserved,
          'cost_reserved',r.cost_reserved::text,'currency',r.config->'limits'->>'currency')) $$""")
    op.execute("""CREATE FUNCTION platform.ai_runtime_receipt(r platform.ai_runs) RETURNS jsonb
      LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      SELECT jsonb_build_object('run_id',r.id,'job_id',r.job_id,'turn_id',r.turn_id,'turn_revision',r.turn_revision,
        'selected_at',r.selected_at,'result',r.result,'send_permit',false) $$""")


def _command() -> None:
    op.execute("""CREATE FUNCTION platform.ai_runtime_command(p_job uuid,p_claim uuid,p_op text,p jsonb) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE j platform.messaging_jobs%ROWTYPE; r platform.ai_runs%ROWTYPE; previous platform.ai_provider_calls%ROWTYPE;
        fresh jsonb; b jsonb; cfg jsonb; lim jsonb; expiry timestamptz; next_job uuid; n integer; tokens integer; cost numeric;
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
          IF NOT platform.material_object(p,ARRAY['config','deadline']) OR jsonb_typeof(p->'deadline') IS DISTINCT FROM 'string'
            OR platform.ai_runtime_config_valid(cfg) IS NOT TRUE THEN
            RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
          IF r.id IS NOT NULL AND r.config IS DISTINCT FROM cfg THEN RAISE EXCEPTION 'IDEMPOTENCY_KEY_CONFLICT' USING ERRCODE='P2001'; END IF;
          BEGIN fresh:=platform.ai_runtime_current(j,r.snapshot);
          EXCEPTION WHEN SQLSTATE 'P2001' THEN
            IF r.id IS NOT NULL AND SQLERRM='AI_STALE' THEN RAISE EXCEPTION 'IDEMPOTENCY_KEY_CONFLICT' USING ERRCODE='P2001'; END IF;
            RAISE;
          END;
          IF r.id IS NOT NULL THEN
            IF fresh->'binding' IS DISTINCT FROM r.binding THEN RAISE EXCEPTION 'IDEMPOTENCY_KEY_CONFLICT' USING ERRCODE='P2001'; END IF;
            RETURN platform.ai_runtime_view(r);
          END IF;
          expiry:=least((p->>'deadline')::timestamptz,clock_timestamp()+(cfg->'limits'->>'duration_seconds')::numeric*interval '1 second');
          IF NOT isfinite(expiry) OR expiry<=clock_timestamp() THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
          b:=fresh->'binding';
          INSERT INTO platform.ai_runs(workspace_id,job_id,connection_id,conversation_id,client_id,business_id,turn_id,turn_revision,
            resume_receipt_id,control_generation,binding,snapshot,snapshot_digest,storage_fingerprint,config,config_fingerprint,deadline)
          VALUES(j.workspace_id,j.id,j.connection_id,(b->>'conversation_id')::uuid,(b->>'client_id')::uuid,(b->>'business_id')::uuid,j.turn_id,j.turn_revision,
            (b->>'resume_receipt_id')::uuid,(b->>'control_generation')::bigint,b,fresh->'snapshot',b->>'snapshot_digest',encode(sha256(convert_to((fresh->'snapshot')::text,'UTF8')),'hex'),cfg,encode(sha256(convert_to(cfg::text,'UTF8')),'hex'),expiry) RETURNING * INTO r;
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
        IF fresh->'binding' IS DISTINCT FROM r.binding THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
        IF r.deadline<=clock_timestamp() OR r.result IS NOT NULL THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
        lim:=r.config->'limits';
        SELECT * INTO previous FROM platform.ai_provider_calls WHERE workspace_id=j.workspace_id AND run_id=r.id AND sequence=r.calls_used;
        IF p_op IN ('AUTHORIZE','READ') THEN
          IF p->'binding' IS DISTINCT FROM r.binding THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
          IF (p_op='AUTHORIZE' AND (NOT platform.material_object(p,ARRAY['run_id','binding','boundary']) OR p->>'boundary' NOT IN ('MODEL','READ','FOLLOWUP','CANDIDATE')))
            OR (p_op='READ' AND NOT platform.material_object(p,ARRAY['run_id','binding'])) THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
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
              'turn_revision',r.turn_revision,'native',r.binding->'native','at',clock_timestamp()) WHERE workspace_id=j.workspace_id AND id=r.id;
            RETURN jsonb_build_object('binding',r.binding,'snapshot',r.snapshot);
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
          INSERT INTO platform.ai_provider_calls(workspace_id,run_id,sequence,claim_hash,attempt_count,budget)
            VALUES(j.workspace_id,r.id,n,sha256(convert_to(p_claim::text,'UTF8')),j.attempt_count,b);
          UPDATE platform.ai_runs SET calls_used=n,tokens_reserved=tokens,cost_reserved=cost WHERE workspace_id=j.workspace_id AND id=r.id;
          RETURN jsonb_build_object('sequence',n);
        ELSIF p_op='COMMIT' THEN
          IF NOT platform.material_object(p,ARRAY['run_id','result']) OR platform.ai_runtime_result_valid(p->'result') IS NOT TRUE THEN
            RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
          IF r.calls_used=0 OR previous.completed_at IS NULL OR previous.completion->>'kind'<>'OUTPUT' THEN RAISE EXCEPTION 'AI_INCOMPLETE' USING ERRCODE='P2001'; END IF;
          PERFORM platform.messaging_guard(p_job,p_claim);
          UPDATE platform.ai_runs SET result=p->'result',selected_at=clock_timestamp(),winning_claim_hash=sha256(convert_to(p_claim::text,'UTF8'))
            WHERE workspace_id=j.workspace_id AND id=r.id AND result IS NULL RETURNING * INTO r;
          UPDATE platform.messaging_jobs SET status='SUCCEEDED',turn_outcome='OBSERVED',error_code=NULL,claim_token=NULL,lease_until=NULL,
            worker_id=NULL,completed_at=clock_timestamp(),version=version+1 WHERE id=j.id;
          RETURN platform.ai_runtime_receipt(r);
        END IF;
        RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001';
      EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range OR invalid_datetime_format OR datetime_field_overflow THEN
        RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001';
      END $$""")


def _replay() -> None:
    op.execute("""CREATE FUNCTION platform.ai_runtime_replay(p_job uuid,p_claim uuid,p jsonb) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE r platform.ai_runs%ROWTYPE;
      BEGIN
        PERFORM platform.turn_require_isolation();
        IF current_database() NOT IN ('asm_local','asm_test') OR nullif(current_setting('asm.actor_kind',true),'') IS NOT NULL THEN
          RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
        SELECT a.* INTO r FROM platform.ai_runs a JOIN platform.messaging_jobs j ON (j.workspace_id,j.id)=(a.workspace_id,a.job_id)
          WHERE j.id=p_job AND j.status='SUCCEEDED' AND j.step='AI_GENERATE' AND a.result IS NOT NULL
            AND a.winning_claim_hash=sha256(convert_to(p_claim::text,'UTF8'));
        IF r.id IS NULL THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
        IF p->'config' IS DISTINCT FROM r.config OR (p ? 'result' AND p->'result' IS DISTINCT FROM r.result) THEN
          RAISE EXCEPTION 'IDEMPOTENCY_KEY_CONFLICT' USING ERRCODE='P2001'; END IF;
        RETURN platform.ai_runtime_receipt(r);
      END $$""")


def downgrade() -> None:
    # Refuse before any DDL/data change. A queued AI intent is already durable.
    op.execute("""LOCK TABLE platform.messaging_jobs,platform.ai_runs,platform.ai_provider_calls IN ACCESS EXCLUSIVE MODE;
      DO $$ BEGIN IF EXISTS(SELECT 1 FROM platform.ai_runs) OR EXISTS(SELECT 1 FROM platform.ai_provider_calls)
        OR EXISTS(SELECT 1 FROM platform.messaging_jobs WHERE step='AI_GENERATE') THEN
          RAISE EXCEPTION 'AI_RUNTIME_DURABLE_DATA' USING ERRCODE='55000'; END IF; END $$""")
    op.execute("ALTER TABLE platform.ai_provider_calls DROP CONSTRAINT ai_call_completion")
    op.execute(
        "ALTER TABLE platform.ai_runs DROP CONSTRAINT ai_run_config, DROP CONSTRAINT ai_run_result"
    )
    for signature in FUNCTIONS:
        op.execute(f"DROP FUNCTION platform.{signature}")
    op.execute("DROP TABLE platform.ai_provider_calls,platform.ai_runs")
    _job_delta(False)
