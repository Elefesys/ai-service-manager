"""Synthetic application AI delivery; historical migrations 0001–0014 are immutable.

Selected result and action commit together. New delivery enrollment is explicit;
old DB-only runs cannot gain actions. All transports remain application-injected.
"""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

ORIGINAL = {
    "platform.messaging_reschedule(uuid,text,boolean,integer,boolean)": r"""CREATE OR REPLACE FUNCTION platform.messaging_reschedule(p_job uuid,p_error text,p_retry boolean,p_delay integer,p_nowait boolean) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE j platform.messaging_jobs%ROWTYPE; retry boolean; final_error text; delivery text; due timestamptz;
      BEGIN
        SELECT * INTO STRICT j FROM platform.messaging_jobs WHERE id=p_job FOR UPDATE;
        IF j.status NOT IN ('READY','RUNNING') THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
        IF p_delay IS NOT NULL AND (p_delay NOT BETWEEN 1 AND 86400 OR p_retry IS NOT TRUE) THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        due:=clock_timestamp()+make_interval(secs=>random()*least(60.0,power(2.0,greatest(j.attempt_count-1,0))));
        IF p_delay IS NOT NULL THEN due:=greatest(due,clock_timestamp()+make_interval(secs=>p_delay)); END IF;
        retry:=p_retry AND j.attempt_count<5 AND clock_timestamp()<j.first_started_at+interval '15 minutes'
          AND (p_delay IS NULL OR due<j.first_started_at+interval '15 minutes');
        IF p_nowait THEN
          BEGIN
            PERFORM platform.turn_preflight(j,true,NOT retry);
          EXCEPTION WHEN lock_not_available THEN RAISE EXCEPTION 'preflight busy' USING ERRCODE='P3001'; END;
        ELSE
          PERFORM platform.turn_preflight(j,false,NOT retry);
        END IF;
        IF current_setting('asm.actor_kind',true)='worker_job' THEN PERFORM platform.messaging_guard(j.id,j.claim_token); END IF;
        IF platform.turn_supersede(j) THEN
          IF j.kind='ESCALATION_TIMER' THEN
            SELECT status,error_code INTO delivery,final_error FROM platform.messaging_jobs WHERE id=j.id;
            RETURN jsonb_build_object('code',coalesce(final_error,'SUPERSEDED'),'status',delivery,'job_id',j.id,'outbox_id',NULL);
          END IF;
          RETURN jsonb_build_object('code','SUPERSEDED','status','SUCCEEDED','job_id',j.id,'outbox_id',NULL);
        END IF;
        IF j.kind='ESCALATION_TIMER' THEN
          retry:=p_retry AND j.attempt_count<5 AND clock_timestamp()<j.first_started_at+interval '15 minutes'
            AND (p_delay IS NULL OR due<j.first_started_at+interval '15 minutes');
        END IF;
        IF j.context_block_reason='CONTEXT_INPUT_PENDING' AND (p_error='RETRY_EXHAUSTED' OR (p_retry AND p_error='DEPENDENCY_TIMEOUT' AND current_setting('asm.actor_kind',true) IS DISTINCT FROM 'worker_job')) THEN
          RETURN platform.human_context_wait(j.id,CASE WHEN current_setting('asm.actor_kind',true)='worker_job' THEN j.claim_token END,'CONTEXT_INPUT_PENDING'); END IF;
        final_error:=CASE WHEN (p_retry AND NOT retry) OR (j.kind='ESCALATION_TIMER' AND NOT retry AND p_error<>'INVALID_INPUT') THEN 'RETRY_EXHAUSTED' ELSE p_error END;
        IF j.kind='FETCH_IMAGE' THEN
          IF NOT EXISTS(SELECT 1 FROM app.file_objects WHERE workspace_id=j.workspace_id AND id=j.file_id AND status='PENDING') THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
          UPDATE platform.file_object_uploads SET status='ABANDONED',next_check_at=clock_timestamp(),version=version+1
            WHERE workspace_id=j.workspace_id AND file_id=j.file_id AND status='PREPARED';
          IF NOT retry THEN
            UPDATE app.file_objects SET status='FAILED',error_code=final_error,completed_at=clock_timestamp(),version=version+1 WHERE workspace_id=j.workspace_id AND id=j.file_id;
          END IF;
        ELSIF j.kind='PROCESS_INBOX' AND NOT retry THEN
          UPDATE platform.inbox_events SET status='FAILED',result_code=final_error,completed_at=clock_timestamp(),version=version+1 WHERE workspace_id=j.workspace_id AND id=j.inbox_id;
        ELSIF j.kind IN ('SEND_MANUAL_TEXT','SEND_GUARDED_TEXT') THEN
          delivery:=CASE WHEN retry THEN 'PENDING' ELSE 'FAILED' END;
          UPDATE app.outbox_events SET status=delivery,error_code=final_error,completed_at=CASE WHEN retry THEN NULL ELSE clock_timestamp() END,version=version+1 WHERE workspace_id=j.workspace_id AND id=j.outbox_id;
        ELSIF j.kind='PROCESS_TURN' AND j.step NOT IN ('GUARDED_TEXT','ESCALATE_OWNER','AI_GENERATE') AND NOT retry THEN
          UPDATE app.conversation_turns SET state='FAILED',error_code=final_error,revision=revision+1 WHERE workspace_id=j.workspace_id AND id=j.turn_id;
        END IF;
        UPDATE platform.messaging_jobs SET context_block_reason=NULL,context_wait_claim_token=NULL,context_wait_result=NULL,status=CASE WHEN retry THEN 'READY' ELSE 'DEAD' END,
          claim_token=NULL,lease_until=NULL,worker_id=NULL,error_code=final_error,available_at=due,
          turn_outcome=CASE WHEN kind='PROCESS_TURN' AND NOT retry THEN 'FAILED' END,
          completed_at=CASE WHEN retry THEN NULL ELSE clock_timestamp() END,version=version+1 WHERE id=j.id;
        RETURN jsonb_build_object('code',CASE WHEN retry THEN 'RETRY_SCHEDULED' ELSE final_error END,'status',coalesce(delivery,CASE WHEN retry THEN 'READY' ELSE 'DEAD' END),'job_id',j.id,'outbox_id',j.outbox_id);
      END $$""",
    "platform.messaging_retry(uuid,uuid,text,boolean)": r"""CREATE OR REPLACE FUNCTION platform.messaging_retry(p_job uuid,p_claim uuid,p_error text,p_retry boolean) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE j platform.messaging_jobs%ROWTYPE; state text;
      BEGIN
        j:=platform.messaging_guard(p_job,p_claim);
        IF p_error IS NULL OR p_error NOT IN ('DEPENDENCY_TIMEOUT','DEPENDENCY_UNAVAILABLE','INVALID_INPUT') OR p_retry IS NULL OR (p_retry AND p_error='INVALID_INPUT') THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        IF j.kind IN ('SEND_MANUAL_TEXT','SEND_GUARDED_TEXT') THEN
          SELECT status INTO state FROM app.outbox_events WHERE workspace_id=j.workspace_id AND id=j.outbox_id FOR UPDATE;
          IF state<>'PENDING' THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
        END IF;
        RETURN platform.messaging_reschedule(p_job,p_error,p_retry);
      END $$""",
    "platform.messaging_recover_expired(timestamptz,timestamptz,uuid)": r"""CREATE OR REPLACE FUNCTION platform.messaging_recover_expired(p_until timestamptz,p_at timestamptz,p_id uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE j platform.messaging_jobs%ROWTYPE; cutoff timestamptz:=coalesce(p_until,clock_timestamp()); pos timestamptz; state text; terminal boolean;
      BEGIN
        PERFORM platform.turn_require_isolation();
        IF coalesce(current_setting('asm.actor_kind',true),'')<>'' OR NOT isfinite(cutoff) OR
          ((p_at IS NULL)<>(p_id IS NULL)) OR (p_at IS NOT NULL AND NOT isfinite(p_at)) THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        BEGIN
          SELECT * INTO j FROM platform.messaging_jobs WHERE status='RUNNING' AND lease_until<=least(cutoff,clock_timestamp())
            AND (p_at IS NULL OR (lease_until,id)>(p_at,p_id)) ORDER BY lease_until,id FOR UPDATE SKIP LOCKED LIMIT 1;
          IF NOT FOUND THEN RETURN jsonb_build_object('step','END','scan_until',cutoff); END IF;
          pos:=j.lease_until;
          IF j.kind IN ('SEND_MANUAL_TEXT','SEND_GUARDED_TEXT') THEN SELECT status INTO state FROM app.outbox_events WHERE workspace_id=j.workspace_id AND id=j.outbox_id; END IF;
          terminal:=state='DISPATCHING' OR j.attempt_count>=5 OR j.first_started_at+interval '15 minutes'<=clock_timestamp();
          BEGIN
            PERFORM platform.turn_preflight(j,true,coalesce(terminal,false));
          EXCEPTION WHEN lock_not_available THEN RAISE EXCEPTION 'preflight busy' USING ERRCODE='P3001'; END;
          IF platform.turn_supersede(j) THEN NULL;
          ELSIF state='DISPATCHING' THEN
            UPDATE app.outbox_events SET status='UNKNOWN',error_code='UNKNOWN_EXTERNAL_RESULT',completed_at=clock_timestamp(),version=version+1 WHERE workspace_id=j.workspace_id AND id=j.outbox_id;
            UPDATE platform.messaging_jobs SET status='DEAD',error_code='UNKNOWN_EXTERNAL_RESULT',claim_token=NULL,lease_until=NULL,worker_id=NULL,completed_at=clock_timestamp(),version=version+1 WHERE id=j.id;
          ELSE PERFORM platform.messaging_reschedule(j.id,'DEPENDENCY_TIMEOUT',true,NULL,true);
          END IF;
          RETURN jsonb_build_object('step','RECOVERED','scan_until',cutoff,'at',pos,'id',j.id);
        EXCEPTION WHEN SQLSTATE 'P3001' THEN
          RETURN jsonb_build_object('step','BUSY','scan_until',cutoff,'at',pos,'id',j.id);
        END;
      END $$""",
    "platform.messaging_finish_send(uuid,uuid,uuid,text,text,text,integer)": r"""CREATE OR REPLACE FUNCTION platform.messaging_finish_send(p_job uuid,p_claim uuid,p_attempt uuid,p_outcome text,p_provider_message text,p_error text,p_retry_after_seconds integer) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE j platform.messaging_jobs%ROWTYPE; box app.outbox_events%ROWTYPE; result jsonb; state text;
      BEGIN
        IF p_retry_after_seconds IS NOT NULL AND (p_retry_after_seconds NOT BETWEEN 1 AND 86400 OR p_outcome IS DISTINCT FROM 'NOT_SENT_RETRYABLE') THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        IF p_outcome IS NULL OR p_outcome NOT IN ('SUCCESS','NOT_SENT_RETRYABLE','NOT_SENT_PERMANENT','UNKNOWN') OR p_attempt IS NULL OR p_claim IS NULL OR
          (p_outcome='SUCCESS' AND (NOT platform.messaging_valid_id(p_provider_message,256,1024) OR p_error IS NOT NULL)) OR
          (p_outcome<>'SUCCESS' AND (p_provider_message IS NOT NULL OR p_error IS NULL OR p_error NOT IN ('NOT_ALLOWED','DEPENDENCY_TIMEOUT','DEPENDENCY_UNAVAILABLE','UNKNOWN_EXTERNAL_RESULT','INVALID_INPUT'))) OR
          (p_outcome='UNKNOWN' AND p_error<>'UNKNOWN_EXTERNAL_RESULT') OR
          (p_outcome<>'UNKNOWN' AND p_error='UNKNOWN_EXTERNAL_RESULT') OR
          (p_outcome='NOT_SENT_RETRYABLE' AND p_error NOT IN ('DEPENDENCY_TIMEOUT','DEPENDENCY_UNAVAILABLE')) THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        IF coalesce(current_setting('asm.actor_kind',true),'')<>'' THEN RAISE EXCEPTION 'ACCESS_DENIED' USING ERRCODE='P2001'; END IF;
        -- Lock protects exact canonical recognition against concurrent next-attempt start.
        -- This path changes neither authority GUC nor saved state.
        SELECT * INTO j FROM platform.messaging_jobs WHERE id=p_job FOR UPDATE;
        IF NOT FOUND OR j.kind NOT IN ('SEND_MANUAL_TEXT','SEND_GUARDED_TEXT') THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
        SELECT * INTO STRICT box FROM app.outbox_events WHERE workspace_id=j.workspace_id AND id=j.outbox_id FOR UPDATE;
        IF j.last_attempt_id=p_attempt AND j.last_claim_token=p_claim AND j.last_outcome=p_outcome AND
           j.last_provider_message_id IS NOT DISTINCT FROM p_provider_message AND j.last_error_code IS NOT DISTINCT FROM p_error AND j.last_retry_after_seconds IS NOT DISTINCT FROM p_retry_after_seconds AND box.attempt_id=p_attempt THEN
          RETURN jsonb_build_object('code','ALREADY_FINALIZED','status',box.status,'job_id',j.id,'outbox_id',box.id,'attempt_id',p_attempt) || CASE WHEN p_retry_after_seconds IS NULL THEN '{}'::jsonb ELSE jsonb_build_object('retry_after_seconds',p_retry_after_seconds,'available_at',(SELECT last_retry_due FROM platform.messaging_jobs WHERE id=j.id)) END;
        END IF;
        PERFORM platform.messaging_admit(p_job,p_claim);
        j:=platform.messaging_guard(p_job,p_claim);
        IF box.status<>'DISPATCHING' OR box.attempt_id IS DISTINCT FROM p_attempt THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
        IF p_outcome IN ('SUCCESS','UNKNOWN') THEN
          PERFORM platform.turn_preflight(j,false,true);
          PERFORM platform.messaging_guard(p_job,p_claim);
        END IF;
        IF p_outcome='SUCCESS' THEN
          state:='SENT';
          UPDATE app.outbox_events SET status=state,provider_message_id=p_provider_message,error_code=NULL,completed_at=clock_timestamp(),version=version+1 WHERE workspace_id=j.workspace_id AND id=box.id;
          UPDATE platform.messaging_jobs SET status='SUCCEEDED',claim_token=NULL,lease_until=NULL,worker_id=NULL,error_code=NULL,completed_at=clock_timestamp(),version=version+1 WHERE id=j.id;
        ELSIF p_outcome='UNKNOWN' THEN
          state:='UNKNOWN';
          UPDATE app.outbox_events SET status=state,error_code='UNKNOWN_EXTERNAL_RESULT',completed_at=clock_timestamp(),version=version+1 WHERE workspace_id=j.workspace_id AND id=box.id;
          UPDATE platform.messaging_jobs SET status='DEAD',claim_token=NULL,lease_until=NULL,worker_id=NULL,error_code='UNKNOWN_EXTERNAL_RESULT',completed_at=clock_timestamp(),version=version+1 WHERE id=j.id;
        ELSE
          result:=platform.messaging_reschedule(j.id,p_error,p_outcome='NOT_SENT_RETRYABLE',p_retry_after_seconds);
          state:=result->>'status';
        END IF;
        UPDATE platform.messaging_jobs SET last_attempt_id=p_attempt,last_claim_token=p_claim,last_outcome=p_outcome,last_provider_message_id=p_provider_message,last_error_code=p_error,last_retry_after_seconds=p_retry_after_seconds,last_retry_due=CASE WHEN p_retry_after_seconds IS NOT NULL THEN available_at END WHERE id=j.id;
        RETURN jsonb_build_object('code','FINALIZED','status',state,'job_id',j.id,'outbox_id',box.id,'attempt_id',p_attempt) || CASE WHEN p_retry_after_seconds IS NULL THEN '{}'::jsonb ELSE jsonb_build_object('retry_after_seconds',p_retry_after_seconds,'available_at',(SELECT last_retry_due FROM platform.messaging_jobs WHERE id=j.id)) END;
      END $$""",
    "platform.turn_preflight(platform.messaging_jobs,boolean,boolean)": r"""CREATE OR REPLACE FUNCTION platform.turn_preflight(j platform.messaging_jobs,p_nowait boolean,p_terminal boolean) RETURNS void
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE lock_suffix text:=CASE WHEN p_nowait THEN ' NOWAIT' ELSE '' END;
        conv uuid; tid uuid; timer_actor uuid; disposition text; file app.file_objects%ROWTYPE;
      BEGIN
        IF j.kind='PROCESS_INBOX' THEN
          EXECUTE 'SELECT id FROM platform.inbox_events WHERE workspace_id=$1 AND id=$2 FOR NO KEY UPDATE'||lock_suffix USING j.workspace_id,j.inbox_id;
        ELSIF j.kind='FETCH_IMAGE' THEN
          EXECUTE 'SELECT * FROM app.file_objects WHERE workspace_id=$1 AND id=$2 FOR UPDATE'||lock_suffix INTO STRICT file USING j.workspace_id,j.file_id;
          EXECUTE 'SELECT id FROM platform.file_object_uploads WHERE workspace_id=$1 AND file_id=$2 AND status=''PREPARED'' ORDER BY id FOR UPDATE'||lock_suffix USING j.workspace_id,j.file_id;
          IF p_terminal AND file.status='PENDING' THEN
            conv:=file.conversation_id;
            SELECT turn_id INTO tid FROM app.conversation_turn_messages WHERE workspace_id=j.workspace_id AND message_id=file.message_id;
          END IF;
        ELSIF j.kind IN ('SEND_MANUAL_TEXT','SEND_GUARDED_TEXT') THEN
          EXECUTE 'SELECT status FROM app.outbox_events WHERE workspace_id=$1 AND id=$2 FOR UPDATE'||lock_suffix INTO STRICT disposition USING j.workspace_id,j.outbox_id;
          IF p_terminal AND disposition IN ('PENDING','DISPATCHING') THEN
            SELECT m.conversation_id INTO STRICT conv FROM app.messages m JOIN app.outbox_events b
              ON (b.workspace_id,b.message_id)=(m.workspace_id,m.id) WHERE b.workspace_id=j.workspace_id AND b.id=j.outbox_id;
          END IF;
        ELSIF j.kind='ESCALATION_TIMER' THEN
          SELECT conversation_id,assignee_user_account_id INTO STRICT conv,timer_actor FROM app.escalations
            WHERE workspace_id=j.workspace_id AND id=j.escalation_id;
          EXECUTE 'SELECT id FROM platform.workspaces WHERE id=$1 FOR SHARE'||lock_suffix USING j.workspace_id;
          EXECUTE 'SELECT id FROM platform.user_accounts WHERE id=$1 FOR SHARE'||lock_suffix USING timer_actor;
          EXECUTE 'SELECT user_account_id FROM platform.workspace_memberships WHERE workspace_id=$1 AND user_account_id=$2 FOR SHARE'||lock_suffix USING j.workspace_id,timer_actor;
          EXECUTE 'SELECT id FROM app.conversations WHERE workspace_id=$1 AND id=$2 FOR NO KEY UPDATE'||lock_suffix USING j.workspace_id,conv;
          EXECUTE 'SELECT id FROM app.escalations WHERE workspace_id=$1 AND id=$2 FOR NO KEY UPDATE'||lock_suffix USING j.workspace_id,j.escalation_id;
          RETURN;
        ELSE
          SELECT conversation_id,id INTO STRICT conv,tid FROM app.conversation_turns WHERE workspace_id=j.workspace_id AND id=j.turn_id;
        END IF;
        IF conv IS NOT NULL THEN
          EXECUTE 'SELECT id FROM app.conversations WHERE workspace_id=$1 AND id=$2 FOR NO KEY UPDATE'||lock_suffix USING j.workspace_id,conv;
        END IF;
        IF tid IS NOT NULL THEN
          EXECUTE 'SELECT id FROM app.conversation_turns WHERE workspace_id=$1 AND id=$2 FOR NO KEY UPDATE'||lock_suffix USING j.workspace_id,tid;
        END IF;
      END $$""",
    "platform.messaging_claim(text,timestamptz,timestamptz,uuid)": r"""CREATE OR REPLACE FUNCTION platform.messaging_claim(p_worker text,p_until timestamptz,p_at timestamptz,p_id uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE j platform.messaging_jobs%ROWTYPE; cutoff timestamptz:=coalesce(p_until,clock_timestamp()); pos timestamptz; exhausted boolean; t app.conversation_turns%ROWTYPE;
      BEGIN
        PERFORM platform.turn_require_isolation();
        IF NOT platform.messaging_valid_id(p_worker,128,512) OR coalesce(current_setting('asm.actor_kind',true),'')<>'' OR
          NOT isfinite(cutoff) OR ((p_at IS NULL)<>(p_id IS NULL)) OR (p_at IS NOT NULL AND NOT isfinite(p_at)) THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        BEGIN
          SELECT * INTO j FROM platform.messaging_jobs WHERE status='READY' AND available_at<=least(cutoff,clock_timestamp())
            AND (p_at IS NULL OR (available_at,id)>(p_at,p_id)) ORDER BY available_at,id FOR UPDATE SKIP LOCKED LIMIT 1;
          IF NOT FOUND THEN RETURN jsonb_build_object('step','END','scan_until',cutoff); END IF;
          pos:=j.available_at;
          exhausted:=j.attempt_count>=5 OR (j.first_started_at IS NOT NULL AND j.first_started_at+interval '15 minutes'<=clock_timestamp());
          BEGIN
            IF exhausted OR j.kind IN ('PROCESS_TURN','ESCALATION_TIMER') THEN PERFORM platform.turn_preflight(j,true,exhausted); END IF;
          EXCEPTION WHEN lock_not_available THEN RAISE EXCEPTION 'preflight busy' USING ERRCODE='P3001'; END;
          -- Re-evaluate age after preflight waits; timer due/relevance in
          -- turn_supersede precedes every attempt/first-start/exhaustion write.
          exhausted:=j.attempt_count>=5 OR (j.first_started_at IS NOT NULL AND j.first_started_at+interval '15 minutes'<=clock_timestamp());
          IF platform.turn_supersede(j) THEN
            RETURN jsonb_build_object('step','TERMINALIZED','scan_until',cutoff,'at',pos,'id',j.id);
          ELSIF exhausted THEN
            PERFORM platform.messaging_reschedule(j.id,'RETRY_EXHAUSTED',false,NULL,true);
            RETURN jsonb_build_object('step','TERMINALIZED','scan_until',cutoff,'at',pos,'id',j.id);
          END IF;
          IF j.kind='PROCESS_TURN' THEN
            SELECT * INTO STRICT t FROM app.conversation_turns WHERE workspace_id=j.workspace_id AND id=j.turn_id;
            IF (j.step='GROUP' AND clock_timestamp()<least(t.quiet_at,t.hard_at)) OR
              (j.step='MEDIA' AND clock_timestamp()<t.media_deadline_at) THEN
              RAISE EXCEPTION 'not yet due' USING ERRCODE='P3001';
            END IF;
          END IF;
          UPDATE platform.messaging_jobs SET context_wait_claim_token=NULL,context_wait_result=NULL,status='RUNNING',claim_token=gen_random_uuid(),lease_until=clock_timestamp()+interval '30 seconds',worker_id=p_worker,
            attempt_count=attempt_count+1,first_started_at=coalesce(first_started_at,clock_timestamp()),
            last_attempt_id=NULL,last_claim_token=NULL,last_outcome=NULL,last_provider_message_id=NULL,last_error_code=NULL,
            last_retry_after_seconds=NULL,last_retry_due=NULL,telegram_probe_claim=NULL,telegram_probe_generation=NULL,telegram_probe_version=NULL,version=version+1
            WHERE id=j.id RETURNING * INTO j;
          UPDATE platform.messaging_jobs SET turn_input=NULL WHERE id=j.id;
          RETURN jsonb_build_object('step','CLAIMED','scan_until',cutoff,'at',pos,'id',j.id,'claim',platform.messaging_job_json(j));
        EXCEPTION WHEN SQLSTATE 'P3001' THEN
          -- The entire subtransaction (including candidate job lock) was rolled back.
          RETURN jsonb_build_object('step','BUSY','scan_until',cutoff,'at',pos,'id',j.id);
        END;
      END $$""",
    "platform.ai_runtime_command(uuid,uuid,text,jsonb)": r"""CREATE FUNCTION platform.ai_runtime_command(p_job uuid,p_claim uuid,p_op text,p jsonb) RETURNS jsonb
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
      END $$""",
    "platform.escalation_request_for_turn(uuid,uuid)": r"""CREATE OR REPLACE FUNCTION platform.escalation_request_for_turn(p_job uuid,p_claim uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE native_saved jsonb; j platform.messaging_jobs%ROWTYPE; t app.conversation_turns%ROWTYPE; c app.conversations%ROWTYPE;
        r platform.conversation_control_receipts%ROWTYPE; e app.escalations%ROWTYPE;
        ws uuid; p_turn uuid; outcome text; prior uuid; allowed boolean; owner_live boolean; moment timestamptz;
      BEGIN
        BEGIN RETURN platform.escalation_request_replay(p_job,p_claim); EXCEPTION WHEN SQLSTATE 'P2001' THEN IF SQLERRM<>'STALE_CLAIM' THEN RAISE; END IF; END;
        SELECT platform.human_context_work_lookup(p_job,p_claim) INTO native_saved; IF native_saved IS NOT NULL THEN RETURN native_saved; END IF;
        j:=platform.messaging_guard(p_job,p_claim);
        IF j.kind<>'PROCESS_TURN' OR j.step<>'ESCALATE_OWNER' THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        ws:=j.workspace_id; p_turn:=j.turn_id;
        SELECT * INTO STRICT t FROM app.conversation_turns WHERE workspace_id=ws AND id=p_turn;
        SELECT * INTO STRICT c FROM app.conversations WHERE workspace_id=ws AND id=t.conversation_id;
        SELECT * INTO r FROM platform.conversation_control_receipts WHERE workspace_id=ws AND conversation_id=c.id
          AND accepted_generation=t.control_generation AND operation='RESUME';
        IF r.id IS NOT NULL THEN owner_live:=platform.messaging_lock_owner(ws,r.actor_user_account_id); END IF;
        PERFORM 1 FROM app.businesses WHERE workspace_id=ws AND id=c.business_id FOR SHARE;
        PERFORM 1 FROM app.channel_connections WHERE workspace_id=ws AND id=j.connection_id FOR SHARE;
        PERFORM platform.messaging_lock_billing_workspace(ws);
        SELECT * INTO STRICT c FROM app.conversations WHERE workspace_id=ws AND id=t.conversation_id FOR NO KEY UPDATE;
        PERFORM 1 FROM app.escalations WHERE workspace_id=ws AND conversation_id=c.id AND status='PENDING' FOR NO KEY UPDATE;
        SELECT * INTO STRICT t FROM app.conversation_turns WHERE workspace_id=ws AND id=p_turn FOR NO KEY UPDATE;
        PERFORM platform.messaging_guard(p_job,p_claim);
        SELECT id INTO prior FROM app.escalations WHERE workspace_id=ws AND turn_id=p_turn;
        IF FOUND THEN outcome:='ALREADY_ESCALATED';
        ELSIF EXISTS(SELECT 1 FROM platform.turn_guard_receipts g WHERE g.workspace_id=ws AND g.turn_id=p_turn AND g.outcome='ACCEPTED') THEN
          outcome:='ALREADY_ACCEPTED';
        ELSE
          SELECT id INTO prior FROM app.escalations WHERE workspace_id=ws AND conversation_id=c.id AND status='PENDING';
          IF FOUND THEN outcome:='WAITING_EXISTS';
          ELSIF t.revision<>j.turn_revision THEN outcome:='SUPERSEDED';
          ELSIF t.state<>'READY' OR platform.conversation_turn_activation_matches(ws,t.id) IS NOT TRUE OR r.id IS NULL OR
            (r.conversation_id,r.client_id,r.accepted_generation,r.activation_fence_seq) IS DISTINCT FROM
            (c.id,c.client_id,t.control_generation,t.activation_fence_seq) THEN outcome:='STALE';
          ELSIF current_database() NOT IN ('asm_local','asm_test') OR r.guard_profile IS DISTINCT FROM 'CONTROLLED_GUARDS_V1' OR
            owner_live IS NOT TRUE OR (r.human_context_revision_id IS NULL AND EXISTS(SELECT 1 FROM app.channel_connections WHERE workspace_id=ws AND id=c.connection_id AND human_context_policy<>'OFF_UNUSED')) OR NOT (EXISTS(SELECT 1 FROM app.conversation_turn_messages tm JOIN app.messages m
          ON (m.workspace_id,m.id)=(tm.workspace_id,tm.message_id)
          WHERE tm.workspace_id=ws AND tm.turn_id=p_turn AND m.direction='INBOUND'
            AND m.content_type='TEXT' AND m.text='CONTROLLED ESCALATION TEST')) OR
            NOT EXISTS(SELECT 1 FROM app.businesses WHERE workspace_id=ws AND id=c.business_id AND status='ACTIVE') OR
            NOT EXISTS(SELECT 1 FROM app.channel_connections WHERE workspace_id=ws AND id=j.connection_id
              AND id=c.connection_id AND business_id=c.business_id AND provider='CONTROLLED' AND status='ACTIVE') THEN outcome:='NOT_ALLOWED';
          ELSE
            BEGIN allowed:=platform.messaging_manual_send_allowed(ws);
            EXCEPTION WHEN SQLSTATE 'P2301' THEN RAISE EXCEPTION 'DEPENDENCY_UNAVAILABLE' USING ERRCODE='P2001'; END;
            IF allowed IS NOT TRUE OR c.version>9223372036854775805 THEN outcome:='NOT_ALLOWED'; END IF;
          END IF;
        END IF;
        PERFORM platform.messaging_guard(p_job,p_claim);
        IF outcome IS NULL THEN
          IF EXISTS(SELECT 1 FROM app.channel_connections WHERE workspace_id=ws AND id=c.connection_id AND human_context_policy<>'OFF_UNUSED') AND platform.material_turn_usable(ws,t.id) IS NOT TRUE THEN outcome:='STALE'; ELSE
            outcome:=nullif(platform.human_context_admission(ws,c.id,NULL),'CURRENT'); END IF;
        END IF;
        IF outcome IN ('CONTEXT_INPUT_PENDING','CONTEXT_POLICY_PAUSED','CONTEXT_CONFIRMATION_REQUIRED','CONTEXT_UNRESOLVED',
          'NEW_OBSERVATION','CONTEXT_INPUT_UNRESOLVED','CONTEXT_COVERAGE_REQUIRED','CONTEXT_TOO_LARGE') THEN
          RETURN platform.human_context_wait(j.id,p_claim,outcome); END IF;
        IF outcome IS NOT NULL THEN
          UPDATE platform.messaging_jobs SET status='SUCCEEDED',turn_outcome=outcome,error_code=NULL,context_block_reason=NULL,context_wait_claim_token=NULL,context_wait_result=NULL,
            claim_token=NULL,lease_until=NULL,worker_id=NULL,completed_at=clock_timestamp(),version=version+1 WHERE id=j.id;
          RETURN jsonb_build_object('code',outcome,'source_job_id',j.id,'turn_id',t.id,'turn_revision',j.turn_revision,'escalation_id',prior);
        END IF;
        moment:=platform.escalation_now();
        e.workspace_id:=ws; e.id:=uuidv7(); e.namespace:='ESCALATION_REQUEST_V1';
        e.conversation_id:=c.id; e.client_id:=c.client_id; e.connection_id:=j.connection_id; e.turn_id:=t.id;
        e.source_job_id:=j.id; e.source_job_kind:=j.kind; e.source_job_step:=j.step; e.source_claim_token:=p_claim;
        e.turn_revision:=t.revision; e.resume_receipt_id:=r.id; e.control_generation:=t.control_generation;
        e.activation_fence_seq:=t.activation_fence_seq; e.input_context_version:=c.version; e.waiting_context_version:=c.version+1;
        e.request_snapshot:=(platform.turn_snapshot(j.workspace_id,t.id)-'snapshot_digest'-'code'-'job_id') ||
        jsonb_build_object('conversation_id',c.id,'client_id',c.client_id,'business_id',c.business_id,
          'resume_receipt_id',r.id,'activation_fence_seq',t.activation_fence_seq,
          'source_job_id',j.id,'source_job_kind',j.kind,'source_job_step',j.step,'source_claim_token',j.claim_token); e.context_fingerprint:=sha256(convert_to(e.request_snapshot::text,'UTF8'));
        e.reason:='OWNER_DECISION_REQUIRED'; e.assignee_user_account_id:=r.actor_user_account_id;
        e.question:='CONTROLLED ESCALATION TEST: требуется решение владельца.'; e.policy:='LOCAL_TEST_OWNER_WAIT_V1'; e.request_fingerprint:=sha256(convert_to(E'asm:m3:escalation_request:v1\n'||jsonb_build_object(
        'snapshot',e.request_snapshot,'reason',e.reason,'assignee_user_account_id',e.assignee_user_account_id,
        'question',e.question,'policy',e.policy)::text,'UTF8'));
        e.created_at:=moment; e.due_at:=moment+interval '2 minutes'; e.second_reminder_at:=moment+interval '5 minutes'; e.expires_at:=moment+interval '10 minutes';
        e.version:=1; e.status:='PENDING'; e.creation_result:=jsonb_build_object('code','ESCALATED','workspace_id',e.workspace_id,'source_job_id',e.source_job_id,
        'escalation_id',e.id,'conversation_id',e.conversation_id,'client_id',e.client_id,'turn_id',e.turn_id,
        'resume_receipt_id',e.resume_receipt_id,'turn_revision',e.turn_revision,'input_context_version',e.input_context_version,
        'waiting_context_version',e.waiting_context_version,'control_generation',e.control_generation,
        'context_fingerprint',encode(e.context_fingerprint,'hex'),'request_fingerprint',encode(e.request_fingerprint,'hex'),
        'initial_version',1,'initial_status','PENDING','created_at',e.created_at,'due_at',e.due_at,
        'second_reminder_at',e.second_reminder_at,'expires_at',e.expires_at);
        outcome:=platform.human_context_snapshot_check(e.request_snapshot,'ESCALATION');
        IF outcome IN ('CONTEXT_INPUT_PENDING','CONTEXT_POLICY_PAUSED','CONTEXT_CONFIRMATION_REQUIRED','CONTEXT_UNRESOLVED',
          'NEW_OBSERVATION','CONTEXT_INPUT_UNRESOLVED','CONTEXT_COVERAGE_REQUIRED','CONTEXT_TOO_LARGE') THEN
          RETURN platform.human_context_wait(j.id,p_claim,outcome); END IF;
        -- Increment first; the material trigger sees no new pending request yet.
        UPDATE app.conversations SET version=version+1 WHERE workspace_id=ws AND id=c.id;
        INSERT INTO app.escalations SELECT e.*;
        INSERT INTO platform.messaging_jobs(workspace_id,connection_id,kind,escalation_id,step,available_at,correlation_id)
          VALUES(ws,e.connection_id,'ESCALATION_TIMER',e.id,'REMIND_1',e.due_at,j.correlation_id),
                (ws,e.connection_id,'ESCALATION_TIMER',e.id,'REMIND_2',e.second_reminder_at,j.correlation_id),
                (ws,e.connection_id,'ESCALATION_TIMER',e.id,'EXPIRE',e.expires_at,j.correlation_id);
        PERFORM platform.messaging_guard(p_job,p_claim);
        UPDATE platform.messaging_jobs SET status='SUCCEEDED',turn_outcome='ESCALATED',error_code=NULL,context_block_reason=NULL,context_wait_claim_token=NULL,context_wait_result=NULL,
          claim_token=NULL,lease_until=NULL,worker_id=NULL,completed_at=clock_timestamp(),version=version+1 WHERE id=j.id;
        RETURN e.creation_result;
      END $$""",
    "platform.escalation_immutable()": r"""CREATE OR REPLACE FUNCTION platform.escalation_immutable() RETURNS trigger
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE e app.escalations%ROWTYPE; j platform.messaging_jobs%ROWTYPE; t app.conversation_turns%ROWTYPE;
        c app.conversations%ROWTYPE; r platform.conversation_control_receipts%ROWTYPE; expected jsonb;
      BEGIN
        IF TG_OP='UPDATE' THEN
          IF (OLD.status<>'PENDING' AND NEW IS DISTINCT FROM OLD) OR
            (to_jsonb(NEW)-ARRAY['version','status','closure_reason','completed_at','answer_text','decided_by_user_account_id','first_reminded_at','second_reminded_at']) IS DISTINCT FROM
            (to_jsonb(OLD)-ARRAY['version','status','closure_reason','completed_at','answer_text','decided_by_user_account_id','first_reminded_at','second_reminded_at']) OR
            (OLD.first_reminded_at IS NOT NULL AND NEW.first_reminded_at IS DISTINCT FROM OLD.first_reminded_at) OR
            (OLD.second_reminded_at IS NOT NULL AND NEW.second_reminded_at IS DISTINCT FROM OLD.second_reminded_at) OR
            (NEW.status<>'PENDING' AND (NEW.first_reminded_at,NEW.second_reminded_at) IS DISTINCT FROM (OLD.first_reminded_at,OLD.second_reminded_at)) THEN
            RAISE EXCEPTION 'immutable escalation' USING ERRCODE='23514',SCHEMA='app',TABLE='escalations',CONSTRAINT='escalations_immutable_check';
          END IF;
          RETURN NEW;
        END IF;
        e:=NEW;
        SELECT * INTO j FROM platform.messaging_jobs WHERE id=e.source_job_id AND workspace_id=e.workspace_id;
        SELECT * INTO t FROM app.conversation_turns WHERE workspace_id=e.workspace_id AND id=e.turn_id;
        SELECT * INTO c FROM app.conversations WHERE workspace_id=e.workspace_id AND id=e.conversation_id;
        SELECT * INTO r FROM platform.conversation_control_receipts WHERE workspace_id=e.workspace_id AND id=e.resume_receipt_id;
        expected:=((platform.turn_snapshot(j.workspace_id,t.id)-'snapshot_digest'-'code'-'job_id') ||
        jsonb_build_object('conversation_id',c.id,'client_id',c.client_id,'business_id',c.business_id,
          'resume_receipt_id',r.id,'activation_fence_seq',t.activation_fence_seq,
          'source_job_id',j.id,'source_job_kind',j.kind,'source_job_step',j.step,'source_claim_token',j.claim_token)) || jsonb_build_object('context_version',e.input_context_version);
        IF e.request_snapshot->>'schema_version'='3' AND platform.human_context_snapshot_valid(e.request_snapshot,'ESCALATION') IS NOT TRUE THEN
          RAISE EXCEPTION 'invalid native escalation snapshot' USING ERRCODE='23514',SCHEMA='app',TABLE='escalations',CONSTRAINT='escalations_immutable_check'; END IF;
        IF (j.status,j.claim_token,t.revision,t.state,c.version,c.control_generation,c.control_mode,
              r.operation,r.actor_user_account_id,r.activation_fence_seq,r.guard_profile) IS DISTINCT FROM
             ('RUNNING'::text,e.source_claim_token,e.turn_revision,'READY'::text,e.waiting_context_version,e.control_generation,'AI'::text,
              'RESUME'::text,e.assignee_user_account_id,e.activation_fence_seq,'CONTROLLED_GUARDS_V1'::text) OR
            e.request_snapshot IS DISTINCT FROM expected OR
            e.context_fingerprint IS DISTINCT FROM sha256(convert_to(e.request_snapshot::text,'UTF8')) OR
            e.request_fingerprint IS DISTINCT FROM sha256(convert_to(E'asm:m3:escalation_request:v1\n'||jsonb_build_object(
        'snapshot',e.request_snapshot,'reason',e.reason,'assignee_user_account_id',e.assignee_user_account_id,
        'question',e.question,'policy',e.policy)::text,'UTF8')) OR
            e.creation_result IS DISTINCT FROM jsonb_build_object('code','ESCALATED','workspace_id',e.workspace_id,'source_job_id',e.source_job_id,
        'escalation_id',e.id,'conversation_id',e.conversation_id,'client_id',e.client_id,'turn_id',e.turn_id,
        'resume_receipt_id',e.resume_receipt_id,'turn_revision',e.turn_revision,'input_context_version',e.input_context_version,
        'waiting_context_version',e.waiting_context_version,'control_generation',e.control_generation,
        'context_fingerprint',encode(e.context_fingerprint,'hex'),'request_fingerprint',encode(e.request_fingerprint,'hex'),
        'initial_version',1,'initial_status','PENDING','created_at',e.created_at,'due_at',e.due_at,
        'second_reminder_at',e.second_reminder_at,'expires_at',e.expires_at) OR
            e.status<>'PENDING' OR e.version<>1 OR e.first_reminded_at IS NOT NULL OR e.second_reminded_at IS NOT NULL THEN
          RAISE EXCEPTION 'invalid escalation origin' USING ERRCODE='23514',SCHEMA='app',TABLE='escalations',CONSTRAINT='escalations_immutable_check';
        END IF;
        RETURN NEW;
      END $$""",
    "platform.human_context_snapshot_valid(jsonb,text)": r"""CREATE FUNCTION platform.human_context_snapshot_valid(s jsonb,shape text) RETURNS boolean
      LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE keys text[]; r jsonb; row jsonb; field text; value jsonb; body jsonb;
      BEGIN
        IF shape IS NULL OR shape NOT IN ('BASE','GUARDED','ESCALATION') THEN RETURN false; END IF;
        keys:=ARRAY['schema_version','workspace_id','connection_id','turn_id','turn_revision','context_version','control_generation',
          'readiness','members','human_context','context_policy_epoch','human_observation_epoch','resume_receipt_id',
          'recent_messages','history_truncated','coverage_status','context_coverage','context_limitations'];
        IF shape IN ('BASE','GUARDED') THEN keys:=keys||ARRAY['snapshot_digest'];
        ELSIF shape<>'ESCALATION' THEN RETURN false; END IF;
        IF shape='GUARDED' THEN keys:=keys||ARRAY['conversation_id','client_id','business_id','activation_fence_seq','consumer'];
        ELSIF shape='ESCALATION' THEN keys:=keys||ARRAY['conversation_id','client_id','business_id','activation_fence_seq',
          'source_job_id','source_job_kind','source_job_step','source_claim_token']; END IF;
        IF (platform.material_object(s,keys) IS NOT TRUE OR jsonb_typeof(s->'schema_version')<>'number' OR s->>'schema_version'<>'3'
          OR jsonb_typeof(s->'history_truncated')<>'boolean' OR s->>'readiness' NOT IN ('COMPLETE','PARTIAL')
          OR s->>'context_coverage'<>'OWNER_ASSERTED_TEXT_ONLY' OR jsonb_typeof(s->'members')<>'array'
          OR jsonb_array_length(s->'members') NOT BETWEEN 1 AND 64 OR jsonb_typeof(s->'recent_messages')<>'array'
          OR jsonb_array_length(s->'recent_messages')>16) IS NOT FALSE THEN RETURN false; END IF;
        FOREACH field IN ARRAY ARRAY['workspace_id','connection_id','turn_id','resume_receipt_id'] LOOP
          IF (NOT platform.human_context_uuid(s->field)) IS NOT FALSE THEN RETURN false; END IF;
        END LOOP;
        FOREACH field IN ARRAY ARRAY['turn_revision','context_version','control_generation'] LOOP
          IF (jsonb_typeof(s->field)<>'number' OR s->>field !~ '^[1-9][0-9]{0,18}$' OR (s->>field)::numeric>9223372036854775807) IS NOT FALSE THEN RETURN false; END IF;
        END LOOP;
        IF (NOT platform.human_context_decimal(s->'context_policy_epoch',true) OR NOT platform.human_context_decimal(s->'human_observation_epoch',false)) IS NOT FALSE THEN RETURN false; END IF;
        r:=s->'human_context';
        IF (platform.material_object(r,ARRAY['revision_id','revision_no','previous_revision_id','actor_user_account_id','accepted_at',
          'disposition','text','source_media','coverage','confirmed_generation','accepted_context_version','policy_epoch','observation_epoch',
          'reviewed_ingress_checkpoint','reviewed_input_state_hash']) IS NOT TRUE OR NOT platform.human_context_uuid(r->'revision_id')
          OR NOT platform.human_context_uuid(r->'actor_user_account_id') OR NOT (r->'previous_revision_id'='null'::jsonb OR platform.human_context_uuid(r->'previous_revision_id'))
          OR r->>'coverage'<>'OWNER_ASSERTED_TEXT_ONLY' OR r->>'source_media' NOT IN ('NONE','UNAVAILABLE')
          OR (r->'policy_epoch',r->'observation_epoch') IS DISTINCT FROM (s->'context_policy_epoch',s->'human_observation_epoch')
          OR jsonb_typeof(r->'reviewed_input_state_hash')<>'string' OR r->>'reviewed_input_state_hash' !~ '^[0-9a-f]{64}$') IS NOT FALSE THEN RETURN false; END IF;
        FOREACH field IN ARRAY ARRAY['revision_no','confirmed_generation','accepted_context_version','policy_epoch','observation_epoch','reviewed_ingress_checkpoint'] LOOP
          IF (NOT platform.human_context_decimal(r->field,field NOT IN ('observation_epoch','reviewed_ingress_checkpoint'))) IS NOT FALSE THEN RETURN false; END IF;
        END LOOP;
        IF ((r->>'confirmed_generation')::numeric+1<>(s->>'control_generation')::numeric) IS NOT FALSE THEN RETURN false; END IF;
        IF (r->>'disposition'='OWNER_TEXT' AND jsonb_typeof(r->'text')='string' AND platform.human_context_text_valid(r->>'text')
            AND s->>'coverage_status'='OWNER_TEXT') OR
          (r->>'disposition'='CANONICAL_SUFFICIENT' AND r->'text'='null'::jsonb AND r->>'source_media'='NONE'
            AND s->'history_truncated'='false'::jsonb AND s->>'coverage_status'='CANONICAL_COMPLETE') THEN NULL; ELSE RETURN false; END IF;
        IF (s->'context_limitations' IS DISTINCT FROM (CASE WHEN r->>'source_media'='UNAVAILABLE'
          THEN '["PROVIDER_HISTORY_UNVERIFIED","NATIVE_MEDIA_UNAVAILABLE"]'::jsonb ELSE '["PROVIDER_HISTORY_UNVERIFIED"]'::jsonb END)
          OR (r->>'source_media'='UNAVAILABLE' AND s->>'readiness'<>'PARTIAL')) IS NOT FALSE THEN RETURN false; END IF;
        IF (jsonb_typeof(r->'accepted_at')<>'string' OR to_char((r->>'accepted_at')::timestamptz AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"') IS DISTINCT FROM r->>'accepted_at') IS NOT FALSE THEN RETURN false; END IF;
        FOR row IN SELECT v FROM jsonb_array_elements(s->'members') a(v) LOOP
          IF (platform.material_object(row,ARRAY['message_id','message_version','content_type','membership_form','initial_suppression_id','current','ingress_at','ingress_seq','file']) IS NOT TRUE
            OR NOT platform.human_context_uuid(row->'message_id') OR jsonb_typeof(row->'message_version')<>'number'
            OR row->>'message_version' !~ '^[1-9][0-9]{0,18}$' OR jsonb_typeof(row->'ingress_seq')<>'number' OR row->>'ingress_seq' !~ '^[1-9][0-9]{0,18}$'
            OR row->>'content_type' NOT IN ('TEXT','IMAGE_REFERENCE')
            OR NOT (row->'membership_form'='null'::jsonb OR row->>'membership_form' IN ('INITIAL_FOLD_SUPPRESSED'))
            OR NOT (row->'initial_suppression_id'='null'::jsonb OR platform.human_context_uuid(row->'initial_suppression_id'))) IS NOT FALSE THEN RETURN false; END IF;
          IF ((row->'membership_form'='null'::jsonb AND row->'initial_suppression_id'='null'::jsonb AND
              ((row->>'content_type'='IMAGE_REFERENCE')=(row->'file'<>'null'::jsonb))) OR
            (row->>'membership_form'='INITIAL_FOLD_SUPPRESSED' AND platform.human_context_uuid(row->'initial_suppression_id')
              AND row->'file'='null'::jsonb AND row->>'content_type'='IMAGE_REFERENCE' AND row->'current'->'changed'='true'::jsonb)) IS NOT TRUE THEN RETURN false; END IF;
          IF (row->'current'->'changed' IS DISTINCT FROM to_jsonb((row->>'message_version')::numeric>1)
            OR (row->>'message_version')::numeric>9223372036854775807 OR (row->>'ingress_seq')::numeric>9223372036854775807
            OR jsonb_typeof(row->'ingress_at')<>'string' OR row->>'ingress_at' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}'
            OR NOT isfinite((row->>'ingress_at')::timestamptz)) IS NOT FALSE THEN RETURN false; END IF;
          value:=row->'current';
          IF (platform.human_context_current_valid(value) IS NOT TRUE) IS NOT FALSE THEN RETURN false; END IF;
          IF row->'file'<>'null'::jsonb THEN
            IF (platform.material_object(row->'file',ARRAY['file_id','version','status','error_code','wait_expired']) IS NOT TRUE
              OR NOT platform.human_context_uuid(row->'file'->'file_id') OR jsonb_typeof(row->'file'->'version')<>'number'
              OR row->'file'->>'version' !~ '^[1-9][0-9]{0,18}$' OR row->'file'->>'status' NOT IN ('PENDING','READY','FAILED')
              OR jsonb_typeof(row->'file'->'wait_expired')<>'boolean') IS NOT FALSE THEN RETURN false; END IF;
          END IF;
          IF row->'file'<>'null'::jsonb THEN
            IF ((row->'file'->>'version')::numeric>9223372036854775807 OR row->'file'->'wait_expired' IS DISTINCT FROM to_jsonb(row->'file'->>'status'='PENDING')
              OR NOT ((row->'file'->>'status' IN ('PENDING','READY') AND row->'file'->'error_code'='null'::jsonb) OR
                (row->'file'->>'status'='FAILED' AND jsonb_typeof(row->'file'->'error_code')='string' AND row->'file'->>'error_code' IN
                  ('INVALID_INPUT','DEPENDENCY_TIMEOUT','DEPENDENCY_UNAVAILABLE','RETRY_EXHAUSTED')))) IS NOT FALSE THEN RETURN false; END IF;
          END IF;
        END LOOP;
        FOR row IN SELECT v FROM jsonb_array_elements(s->'recent_messages') a(v) LOOP
          IF (platform.material_object(row,ARRAY['message_id','version','direction','origin','created_at','current','delivery','file']) IS NOT TRUE
            OR NOT platform.human_context_uuid(row->'message_id') OR NOT platform.human_context_decimal(row->'version',true)
            OR row->>'direction' NOT IN ('INBOUND','OUTBOUND') OR row->>'origin' NOT IN ('CLIENT_INBOUND','OWNER_MANUAL','CONTROLLED_AUTOMATION','LEGACY_UNATTRIBUTED')
            OR jsonb_typeof(row->'created_at')<>'string' OR to_char((row->>'created_at')::timestamptz AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"') IS DISTINCT FROM row->>'created_at'
            OR platform.human_context_current_valid(row->'current') IS NOT TRUE) IS NOT FALSE THEN RETURN false; END IF;
          IF (row->'file'<>'null'::jsonb AND (platform.material_object(row->'file',ARRAY['file_id','version','status']) IS NOT TRUE
            OR NOT platform.human_context_uuid(row->'file'->'file_id') OR NOT platform.human_context_decimal(row->'file'->'version',true)
            OR row->'file'->>'status' NOT IN ('PENDING','READY','FAILED'))) IS NOT FALSE THEN RETURN false; END IF;
          IF (row->'current'->'changed' IS DISTINCT FROM to_jsonb((row->>'version')::numeric>1)
            OR (row->>'direction'='INBOUND' AND (row->>'origin'<>'CLIENT_INBOUND' OR row->'delivery'<>'null'::jsonb))
            OR (row->>'direction'='OUTBOUND' AND (row->>'origin'='CLIENT_INBOUND' OR row->'file'<>'null'::jsonb))) IS NOT FALSE THEN RETURN false; END IF;
          IF row->'delivery'<>'null'::jsonb THEN
            value:=row->'delivery';
            IF value->'completed_at'<>'null'::jsonb THEN
              IF (jsonb_typeof(value->'completed_at')<>'string'
                OR value->>'completed_at' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}[.][0-9]{6}Z$') IS NOT FALSE THEN RETURN false; END IF;
              IF (NOT isfinite((value->>'completed_at')::timestamptz)
                OR to_char((value->>'completed_at')::timestamptz AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
                  IS DISTINCT FROM value->>'completed_at') IS NOT FALSE THEN RETURN false; END IF;
            END IF;
            IF (((value->>'status' IN ('SENT','FAILED','UNKNOWN'))<>(value->'completed_at'<>'null'::jsonb))
              OR NOT (value->'error_code'='null'::jsonb OR (jsonb_typeof(value->'error_code')='string' AND value->>'error_code' IN
                ('INVALID_INPUT','NOT_ALLOWED','RETRY_EXHAUSTED','DEPENDENCY_TIMEOUT','DEPENDENCY_UNAVAILABLE','UNKNOWN_EXTERNAL_RESULT')))
              OR (value->>'status'='SENT' AND value->'error_code'<>'null'::jsonb)
              OR (value->>'status' IN ('FAILED','UNKNOWN') AND value->'error_code'='null'::jsonb)) IS NOT FALSE THEN RETURN false; END IF;
          END IF;
          IF (row->'delivery'<>'null'::jsonb AND (platform.material_object(row->'delivery',ARRAY['status','error_code','completed_at','version']) IS NOT TRUE
            OR row->'delivery'->>'status' NOT IN ('PENDING','DISPATCHING','SENT','FAILED','UNKNOWN') OR NOT platform.human_context_decimal(row->'delivery'->'version',true))) IS NOT FALSE THEN RETURN false; END IF;
        END LOOP;
        IF ((SELECT count(DISTINCT v->>'message_id') FROM jsonb_array_elements(s->'members') a(v))<>jsonb_array_length(s->'members')
          OR (SELECT count(DISTINCT v->>'message_id') FROM jsonb_array_elements(s->'recent_messages') a(v))<>jsonb_array_length(s->'recent_messages')
          OR (s->'history_truncated'='true'::jsonb AND jsonb_array_length(s->'recent_messages')<>16)
          OR EXISTS(SELECT 1 FROM (SELECT v->>'created_at' AS at,v->>'message_id' AS id,
            lag(v->>'created_at') OVER (ORDER BY n) AS previous_at,lag(v->>'message_id') OVER (ORDER BY n) AS previous_id
            FROM jsonb_array_elements(s->'recent_messages') WITH ORDINALITY a(v,n)) q WHERE (previous_at,previous_id)>=(at,id))) IS NOT FALSE THEN RETURN false; END IF;
        IF shape<>'BASE' THEN
          FOREACH field IN ARRAY ARRAY['conversation_id','client_id','business_id'] LOOP IF (NOT platform.human_context_uuid(s->field)) IS NOT FALSE THEN RETURN false; END IF; END LOOP;
          IF (jsonb_typeof(s->'activation_fence_seq')<>'number' OR s->>'activation_fence_seq' !~ '^[1-9][0-9]{0,18}$') IS NOT FALSE THEN RETURN false; END IF;
        END IF;
        IF (shape='GUARDED' AND s->>'consumer'<>'CONTROLLED_GUARDS_V1') IS NOT FALSE THEN RETURN false; END IF;
        IF (shape='ESCALATION' AND (NOT platform.human_context_uuid(s->'source_job_id') OR NOT platform.human_context_uuid(s->'source_claim_token')
          OR s->>'source_job_kind'<>'PROCESS_TURN' OR s->>'source_job_step'<>'ESCALATE_OWNER')) IS NOT FALSE THEN RETURN false; END IF;
        body:=s-'snapshot_digest';
        IF (octet_length(convert_to(body::text,'UTF8'))>2097152) IS NOT FALSE THEN RETURN false; END IF;
        IF (shape<>'ESCALATION' AND (jsonb_typeof(s->'snapshot_digest')<>'string' OR s->>'snapshot_digest' IS DISTINCT FROM encode(sha256(convert_to(body::text,'UTF8')),'hex'))) IS NOT FALSE THEN RETURN false; END IF;
        RETURN true;
      EXCEPTION WHEN invalid_text_representation OR datetime_field_overflow OR invalid_datetime_format OR numeric_value_out_of_range OR invalid_parameter_value THEN RETURN false;
      END $$""",
    "platform.human_context_policy_command(uuid,uuid,text,text,text,bigint,jsonb,jsonb)": r"""CREATE FUNCTION platform.human_context_policy_command(ws uuid,p_connection uuid,p_operation text,p_key text,
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
          OR jsonb_typeof(p_profile->'schema_revision')<>'string' OR p_profile->>'schema_revision'<>'0013'
          OR jsonb_typeof(p_profile->'profile_sha256')<>'string' OR p_profile->>'profile_sha256' !~ '^[0-9a-f]{64}$'
          OR p_profile->'drain_confirmed' IS DISTINCT FROM 'true'::jsonb THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2601'; END IF;
        SELECT platform.human_context_schema_profile() INTO profile;
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
        SELECT platform.human_context_schema_profile() INTO profile;
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
    "platform.telegram_worker_probe(uuid,uuid)": r"""CREATE FUNCTION platform.telegram_worker_probe(p_job uuid,p_claim uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE j platform.messaging_jobs%ROWTYPE; conn app.channel_connections%ROWTYPE; state text; s platform.telegram_connection_state%ROWTYPE;
      BEGIN
        j:=platform.messaging_guard(p_job,p_claim);
        IF j.kind<>'SEND_MANUAL_TEXT' THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        SELECT status INTO STRICT state FROM app.outbox_events WHERE workspace_id=j.workspace_id AND id=j.outbox_id FOR UPDATE;
        IF state<>'PENDING' THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
        SELECT * INTO STRICT conn FROM app.channel_connections WHERE workspace_id=j.workspace_id AND id=j.connection_id;
        IF conn.provider='CONTROLLED' THEN RETURN NULL; END IF;
        SELECT * INTO STRICT s FROM platform.telegram_connection_state WHERE workspace_id=j.workspace_id AND connection_id=j.connection_id;
        UPDATE platform.messaging_jobs SET telegram_probe_claim=p_claim,telegram_probe_generation=s.generation,telegram_probe_version=s.observation_version WHERE id=j.id;
        RETURN platform.telegram_probe_json(s);
      END $$""",
}

PATCHES = (
    (
        "platform.messaging_reschedule(uuid,text,boolean,integer,boolean)",
        "('SEND_MANUAL_TEXT','SEND_GUARDED_TEXT')",
        "('SEND_MANUAL_TEXT','SEND_GUARDED_TEXT','SEND_AI_TEXT')",
        1,
    ),
    (
        "platform.messaging_retry(uuid,uuid,text,boolean)",
        "('SEND_MANUAL_TEXT','SEND_GUARDED_TEXT')",
        "('SEND_MANUAL_TEXT','SEND_GUARDED_TEXT','SEND_AI_TEXT')",
        1,
    ),
    (
        "platform.messaging_recover_expired(timestamptz,timestamptz,uuid)",
        "('SEND_MANUAL_TEXT','SEND_GUARDED_TEXT')",
        "('SEND_MANUAL_TEXT','SEND_GUARDED_TEXT','SEND_AI_TEXT')",
        1,
    ),
    (
        "platform.messaging_finish_send(uuid,uuid,uuid,text,text,text,integer)",
        "('SEND_MANUAL_TEXT','SEND_GUARDED_TEXT')",
        "('SEND_MANUAL_TEXT','SEND_GUARDED_TEXT','SEND_AI_TEXT')",
        1,
    ),
    (
        "platform.turn_preflight(platform.messaging_jobs,boolean,boolean)",
        "('SEND_MANUAL_TEXT','SEND_GUARDED_TEXT')",
        "('SEND_MANUAL_TEXT','SEND_GUARDED_TEXT','SEND_AI_TEXT')",
        1,
    ),
    (
        "platform.messaging_claim(text,timestamptz,timestamptz,uuid)",
        "WHERE status='READY' AND available_at",
        "WHERE NOT EXISTS(SELECT 1 FROM platform.ai_deliveries d WHERE d.job_id=platform.messaging_jobs.id) AND status='READY' AND available_at",
        1,
    ),
    (
        "platform.messaging_reschedule(uuid,text,boolean,integer,boolean)",
        "        IF p_nowait THEN",
        "        IF j.step='AI_GENERATE' AND EXISTS(SELECT 1 FROM platform.ai_deliveries WHERE job_id=j.id) THEN retry:=false; END IF;\n        IF p_nowait THEN",
        1,
    ),
    (
        "platform.ai_runtime_command(uuid,uuid,text,jsonb)",
        "          UPDATE platform.messaging_jobs SET status='SUCCEEDED',turn_outcome='OBSERVED'",
        "          PERFORM platform.ai_delivery_select(j,r);\n          UPDATE platform.messaging_jobs SET status='SUCCEEDED',turn_outcome='OBSERVED'",
        1,
    ),
    (
        "platform.escalation_request_for_turn(uuid,uuid)",
        "j.step<>'ESCALATE_OWNER'",
        "j.step NOT IN ('ESCALATE_OWNER','AI_GENERATE')",
        1,
    ),
    (
        "platform.escalation_request_for_turn(uuid,uuid)",
        "        ws:=j.workspace_id; p_turn:=j.turn_id;",
        "        IF j.step='AI_GENERATE' THEN\n          IF NOT EXISTS(SELECT 1 FROM platform.ai_deliveries d JOIN platform.ai_runs a ON (a.workspace_id,a.job_id)=(d.workspace_id,d.job_id)\n            WHERE d.job_id=j.id AND a.result->>'kind'='handoff' AND a.winning_claim_hash=sha256(convert_to(p_claim::text,'UTF8'))) THEN\n            RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;\n        END IF;\n        ws:=j.workspace_id; p_turn:=j.turn_id;",
        1,
    ),
    (
        "platform.escalation_request_for_turn(uuid,uuid)",
        "          ELSIF current_database() NOT IN ('asm_local','asm_test') OR r.guard_profile IS DISTINCT FROM 'CONTROLLED_GUARDS_V1' OR\n            owner_live IS NOT TRUE OR (r.human_context_revision_id IS NULL AND EXISTS(SELECT 1 FROM app.channel_connections WHERE workspace_id=ws AND id=c.connection_id AND human_context_policy<>'OFF_UNUSED')) OR NOT (EXISTS(SELECT 1 FROM app.conversation_turn_messages tm JOIN app.messages m\n          ON (m.workspace_id,m.id)=(tm.workspace_id,tm.message_id)\n          WHERE tm.workspace_id=ws AND tm.turn_id=p_turn AND m.direction='INBOUND'\n            AND m.content_type='TEXT' AND m.text='CONTROLLED ESCALATION TEST')) OR\n            NOT EXISTS(SELECT 1 FROM app.businesses WHERE workspace_id=ws AND id=c.business_id AND status='ACTIVE') OR\n            NOT EXISTS(SELECT 1 FROM app.channel_connections WHERE workspace_id=ws AND id=j.connection_id\n              AND id=c.connection_id AND business_id=c.business_id AND provider='CONTROLLED' AND status='ACTIVE') THEN outcome:='NOT_ALLOWED';\n",
        "          ELSIF j.step='AI_GENERATE' THEN\n            PERFORM platform.ai_runtime_current(j,(SELECT snapshot FROM platform.ai_runs WHERE job_id=j.id));\n          ELSIF current_database() NOT IN ('asm_local','asm_test') OR r.guard_profile IS DISTINCT FROM 'CONTROLLED_GUARDS_V1' OR\n            owner_live IS NOT TRUE OR (r.human_context_revision_id IS NULL AND EXISTS(SELECT 1 FROM app.channel_connections WHERE workspace_id=ws AND id=c.connection_id AND human_context_policy<>'OFF_UNUSED')) OR NOT (EXISTS(SELECT 1 FROM app.conversation_turn_messages tm JOIN app.messages m\n          ON (m.workspace_id,m.id)=(tm.workspace_id,tm.message_id)\n          WHERE tm.workspace_id=ws AND tm.turn_id=p_turn AND m.direction='INBOUND'\n            AND m.content_type='TEXT' AND m.text='CONTROLLED ESCALATION TEST')) OR\n            NOT EXISTS(SELECT 1 FROM app.businesses WHERE workspace_id=ws AND id=c.business_id AND status='ACTIVE') OR\n            NOT EXISTS(SELECT 1 FROM app.channel_connections WHERE workspace_id=ws AND id=j.connection_id\n              AND id=c.connection_id AND business_id=c.business_id AND provider='CONTROLLED' AND status='ACTIVE') THEN outcome:='NOT_ALLOWED';\n",
        1,
    ),
    (
        "platform.escalation_immutable()",
        "e.activation_fence_seq,'CONTROLLED_GUARDS_V1'::text)",
        "e.activation_fence_seq,CASE WHEN j.step='AI_GENERATE' THEN r.guard_profile ELSE 'CONTROLLED_GUARDS_V1'::text END)",
        1,
    ),
    (
        "platform.human_context_snapshot_valid(jsonb,text)",
        "s->>'source_job_step'<>'ESCALATE_OWNER'",
        "s->>'source_job_step' NOT IN ('ESCALATE_OWNER','AI_GENERATE')",
        1,
    ),
    (
        "platform.human_context_policy_command(uuid,uuid,text,text,text,bigint,jsonb,jsonb)",
        "p_profile->>'schema_revision'<>'0013'",
        "p_profile->>'schema_revision'<>'0015'",
        1,
    ),
    (
        "platform.human_context_policy_command(uuid,uuid,text,text,text,bigint,jsonb,jsonb)",
        "platform.human_context_schema_profile()",
        "platform.ai_delivery_schema_profile()",
        2,
    ),
    (
        "platform.telegram_worker_probe(uuid,uuid)",
        "j.kind<>'SEND_MANUAL_TEXT'",
        "j.kind NOT IN ('SEND_MANUAL_TEXT','SEND_AI_TEXT')",
        1,
    ),
)


def replacements():
    result = {
        signature: sql.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
        for signature, sql in ORIGINAL.items()
    }
    for signature, old, new, count in PATCHES:
        assert result[signature].count(old) == count
        result[signature] = result[signature].replace(old, new)
    return result


# One row per explicitly enrolled application Turn; zero retroactive enrollment.
TABLE_SQL = """CREATE TABLE platform.ai_deliveries(
  workspace_id uuid NOT NULL, job_id uuid NOT NULL, source_job_id uuid NOT NULL,
  source_claim_hash bytea NOT NULL CHECK(octet_length(source_claim_hash)=32),
  connection_id uuid NOT NULL, turn_id uuid NOT NULL, turn_revision bigint NOT NULL CHECK(turn_revision>0),
  kind text NOT NULL DEFAULT 'PROCESS_TURN' CHECK(kind='PROCESS_TURN'),
  step text NOT NULL DEFAULT 'AI_GENERATE' CHECK(step='AI_GENERATE'),
  run_id uuid, selected_kind text CHECK(selected_kind IN ('reply','handoff','no_reply')),
  message_id uuid, outbox_id uuid, send_job_id uuid, escalation_id uuid,
  intent_context_version bigint CHECK(intent_context_version>0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY(workspace_id,job_id), UNIQUE(workspace_id,source_job_id), UNIQUE(workspace_id,turn_id,turn_revision),
  UNIQUE(workspace_id,run_id), UNIQUE(workspace_id,outbox_id), UNIQUE(workspace_id,send_job_id),
  FOREIGN KEY(workspace_id,job_id,connection_id,kind,turn_id,turn_revision,step)
    REFERENCES platform.messaging_jobs(workspace_id,id,connection_id,kind,turn_id,turn_revision,step) ON DELETE RESTRICT,
  FOREIGN KEY(workspace_id,source_job_id) REFERENCES platform.messaging_jobs(workspace_id,id) ON DELETE RESTRICT,
  FOREIGN KEY(workspace_id,run_id) REFERENCES platform.ai_runs(workspace_id,id) ON DELETE RESTRICT,
  FOREIGN KEY(workspace_id,message_id) REFERENCES app.messages(workspace_id,id) ON DELETE RESTRICT,
  FOREIGN KEY(workspace_id,outbox_id) REFERENCES app.outbox_events(workspace_id,id) ON DELETE RESTRICT,
  FOREIGN KEY(workspace_id,send_job_id) REFERENCES platform.messaging_jobs(workspace_id,id) ON DELETE RESTRICT,
  FOREIGN KEY(workspace_id,escalation_id) REFERENCES app.escalations(workspace_id,id) ON DELETE RESTRICT,
  CHECK((selected_kind IS NULL AND run_id IS NULL AND message_id IS NULL AND outbox_id IS NULL AND send_job_id IS NULL AND escalation_id IS NULL AND intent_context_version IS NULL)
    OR (selected_kind IS NOT NULL AND run_id IS NOT NULL AND
      ((selected_kind='reply' AND message_id IS NOT NULL AND outbox_id IS NOT NULL AND send_job_id IS NOT NULL AND intent_context_version IS NOT NULL AND escalation_id IS NULL)
       OR (selected_kind='handoff' AND escalation_id IS NOT NULL AND message_id IS NULL AND outbox_id IS NULL AND send_job_id IS NULL AND intent_context_version IS NULL)
       OR (selected_kind='no_reply' AND escalation_id IS NULL AND message_id IS NULL AND outbox_id IS NULL AND send_job_id IS NULL AND intent_context_version IS NULL)))))"""

FUNCTIONS = (
    "ai_delivery_enqueue(uuid,uuid)",
    "ai_delivery_command(uuid,uuid,text,jsonb)",
    "ai_delivery_claim(text,timestamptz,timestamptz,uuid)",
    "ai_delivery_begin(uuid,uuid,bigint,bigint,jsonb)",
    "ai_delivery_select(platform.messaging_jobs,platform.ai_runs)",
    "ai_delivery_current(platform.messaging_jobs,platform.ai_deliveries,platform.ai_runs)",
    "ai_delivery_immutable()",
    "ai_delivery_schema_profile()",
)
PUBLIC = FUNCTIONS[:4]


def _enqueue():
    op.execute("""CREATE FUNCTION platform.ai_delivery_enqueue(p_job uuid,p_claim uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE j platform.messaging_jobs%ROWTYPE; source platform.messaging_jobs%ROWTYPE;
        d platform.ai_deliveries%ROWTYPE; next_job uuid;
      BEGIN
        PERFORM platform.turn_require_isolation();
        IF coalesce(current_setting('asm.actor_kind',true),'')<>'' OR current_database() NOT IN ('asm_local','asm_test') THEN
          RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
        SELECT * INTO d FROM platform.ai_deliveries WHERE source_job_id=p_job;
        IF FOUND THEN
          IF d.source_claim_hash IS DISTINCT FROM sha256(convert_to(p_claim::text,'UTF8')) THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
          RETURN jsonb_build_object('job_id',d.job_id);
        END IF;
        BEGIN PERFORM platform.messaging_admit(p_job,p_claim);
        EXCEPTION WHEN SQLSTATE 'P2001' THEN
          IF SQLERRM<>'STALE_CLAIM' THEN RAISE; END IF;
          SELECT * INTO d FROM platform.ai_deliveries WHERE source_job_id=p_job AND source_claim_hash=sha256(convert_to(p_claim::text,'UTF8'));
          IF NOT FOUND THEN RAISE; END IF;
          RETURN jsonb_build_object('job_id',d.job_id);
        END;
        source:=platform.messaging_guard(p_job,p_claim); j:=source;
        IF j.kind<>'PROCESS_TURN' OR j.step NOT IN ('TEST_CONSUME','GUARDED_TEXT','ESCALATE_OWNER') THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        -- This local composite only selects the base snapshot shape. Authority
        -- remains the actual admitted source job/XID and its server-owned Turn.
        j.step:='TEST_CONSUME';
        PERFORM platform.ai_runtime_current(j,NULL);
        IF EXISTS(SELECT 1 FROM platform.messaging_jobs WHERE workspace_id=j.workspace_id AND turn_id=j.turn_id AND turn_revision=j.turn_revision AND step='AI_GENERATE') THEN
          RAISE EXCEPTION 'IDEMPOTENCY_KEY_CONFLICT' USING ERRCODE='P2001'; END IF;
        INSERT INTO platform.messaging_jobs(workspace_id,connection_id,kind,turn_id,turn_revision,step,correlation_id)
          VALUES(j.workspace_id,j.connection_id,'PROCESS_TURN',j.turn_id,j.turn_revision,'AI_GENERATE',j.correlation_id) RETURNING id INTO next_job;
        INSERT INTO platform.ai_deliveries(workspace_id,job_id,source_job_id,source_claim_hash,connection_id,turn_id,turn_revision)
          VALUES(j.workspace_id,next_job,j.id,sha256(convert_to(p_claim::text,'UTF8')),j.connection_id,j.turn_id,j.turn_revision);
        PERFORM platform.messaging_guard(p_job,p_claim);
        UPDATE platform.messaging_jobs SET status='SUCCEEDED',turn_outcome='OBSERVED',error_code=NULL,claim_token=NULL,lease_until=NULL,
          worker_id=NULL,completed_at=clock_timestamp(),version=version+1 WHERE id=j.id;
        RETURN jsonb_build_object('job_id',next_job);
      END $$""")


def _command():
    op.execute("""CREATE FUNCTION platform.ai_delivery_command(p_job uuid,p_claim uuid,p_op text,p jsonb) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE j platform.messaging_jobs%ROWTYPE; r platform.ai_runs%ROWTYPE; result jsonb;
      BEGIN
        j:=platform.messaging_guard(p_job,p_claim);
        IF NOT EXISTS(SELECT 1 FROM platform.ai_deliveries WHERE workspace_id=j.workspace_id AND job_id=j.id) THEN
          RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
        IF p_op='STOP' THEN
          IF p<>'{}'::jsonb THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
          RETURN platform.messaging_reschedule(j.id,'DEPENDENCY_UNAVAILABLE',false,NULL,false);
        END IF;
        IF p_op='ENQUEUE' THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
        result:=platform.ai_runtime_command(p_job,p_claim,p_op,p);
        IF p_op='PREPARE' THEN
          SELECT * INTO STRICT r FROM platform.ai_runs WHERE workspace_id=j.workspace_id AND job_id=j.id;
          PERFORM platform.messaging_guard(p_job,p_claim);
          -- One finite extension, bounded by the original first start; repeated
          -- PREPARE cannot slide the deadline. Other Jobs retain their 30s lease.
          UPDATE platform.messaging_jobs SET lease_until=least(r.deadline+interval '5 seconds',first_started_at+interval '125 seconds')
            WHERE id=j.id;
        END IF;
        RETURN result;
      END $$""")
    source = ORIGINAL["platform.messaging_claim(text,timestamptz,timestamptz,uuid)"]
    op.execute(
        source.replace("platform.messaging_claim(", "platform.ai_delivery_claim(", 1).replace(
            "WHERE status='READY' AND available_at",
            "WHERE EXISTS(SELECT 1 FROM platform.ai_deliveries d WHERE d.job_id=platform.messaging_jobs.id) AND status='READY' AND available_at",
            1,
        )
    )


def _select():
    op.execute("""CREATE FUNCTION platform.ai_delivery_select(j platform.messaging_jobs,r platform.ai_runs) RETURNS void
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE d platform.ai_deliveries%ROWTYPE; c app.conversations%ROWTYPE; conn app.channel_connections%ROWTYPE;
        msg uuid; box uuid; send uuid; intent_context bigint; e jsonb;
      BEGIN
        SELECT * INTO d FROM platform.ai_deliveries WHERE workspace_id=j.workspace_id AND job_id=j.id FOR UPDATE;
        IF NOT FOUND THEN RETURN; END IF; -- historical DB-only run: no retroactive intent
        IF d.selected_kind IS NOT NULL OR r.result IS NULL OR r.winning_claim_hash IS DISTINCT FROM sha256(convert_to(j.claim_token::text,'UTF8')) THEN
          RAISE EXCEPTION 'IDEMPOTENCY_KEY_CONFLICT' USING ERRCODE='P2001'; END IF;
        PERFORM platform.ai_runtime_current(j,r.snapshot);
        SELECT * INTO STRICT c FROM app.conversations WHERE workspace_id=j.workspace_id AND id=r.conversation_id;
        SELECT * INTO STRICT conn FROM app.channel_connections WHERE workspace_id=j.workspace_id AND id=j.connection_id;
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
        ELSIF r.result->>'kind'='handoff' THEN
          e:=platform.escalation_request_for_turn(j.id,j.claim_token);
          IF e->>'code' IS DISTINCT FROM 'ESCALATED' THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
        END IF;
        IF j.lease_until<=clock_timestamp() THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
        UPDATE platform.ai_deliveries SET run_id=r.id,selected_kind=r.result->>'kind',message_id=msg,outbox_id=box,send_job_id=send,
          intent_context_version=intent_context,escalation_id=(e->>'escalation_id')::uuid WHERE workspace_id=j.workspace_id AND job_id=j.id;
      END $$""")
    op.execute("""CREATE FUNCTION platform.ai_delivery_immutable() RETURNS trigger
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      BEGIN
        IF OLD.selected_kind IS NOT NULL OR
          (to_jsonb(OLD)-ARRAY['run_id','selected_kind','message_id','outbox_id','send_job_id','escalation_id','intent_context_version']) IS DISTINCT FROM
          (to_jsonb(NEW)-ARRAY['run_id','selected_kind','message_id','outbox_id','send_job_id','escalation_id','intent_context_version']) OR
          NOT EXISTS(SELECT 1 FROM platform.ai_runs r WHERE r.workspace_id=NEW.workspace_id AND r.id=NEW.run_id AND r.job_id=NEW.job_id AND r.result->>'kind'=NEW.selected_kind) THEN
          RAISE EXCEPTION 'immutable AI delivery' USING ERRCODE='23514'; END IF;
        RETURN NEW;
      END $$""")
    op.execute(
        "CREATE TRIGGER ai_delivery_immutable BEFORE UPDATE ON platform.ai_deliveries FOR EACH ROW EXECUTE FUNCTION platform.ai_delivery_immutable()"
    )


def _current():
    op.execute("""CREATE FUNCTION platform.ai_delivery_current(j platform.messaging_jobs,d platform.ai_deliveries,r platform.ai_runs) RETURNS boolean
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE t app.conversation_turns%ROWTYPE; c app.conversations%ROWTYPE; resume platform.conversation_control_receipts%ROWTYPE;
        allowed boolean;
      BEGIN
        SELECT * INTO STRICT resume FROM platform.conversation_control_receipts WHERE workspace_id=j.workspace_id AND id=r.resume_receipt_id;
        IF platform.messaging_lock_owner(j.workspace_id,resume.actor_user_account_id) IS NOT TRUE THEN RETURN false; END IF;
        PERFORM 1 FROM app.businesses WHERE (workspace_id,id)=(j.workspace_id,r.business_id) AND status='ACTIVE' FOR SHARE;
        IF NOT FOUND THEN RETURN false; END IF;
        PERFORM 1 FROM app.channel_connections WHERE (workspace_id,id,business_id)=(j.workspace_id,j.connection_id,r.business_id)
          AND status='ACTIVE' AND (provider='CONTROLLED' OR (current_database()='asm_test' AND provider='TELEGRAM')) FOR SHARE;
        IF NOT FOUND THEN RETURN false; END IF;
        PERFORM platform.messaging_lock_billing_workspace(j.workspace_id);
        SELECT * INTO STRICT c FROM app.conversations WHERE workspace_id=j.workspace_id AND id=r.conversation_id FOR NO KEY UPDATE;
        SELECT * INTO STRICT t FROM app.conversation_turns WHERE workspace_id=j.workspace_id AND id=r.turn_id FOR NO KEY UPDATE;
        PERFORM 1 FROM app.clients WHERE (workspace_id,id)=(j.workspace_id,r.client_id) FOR SHARE;
        IF NOT FOUND THEN RETURN false; END IF;
        PERFORM platform.messaging_guard(j.id,j.claim_token);
        IF (c.client_id,c.business_id,c.connection_id,c.version,t.revision,t.state,t.control_generation,t.activation_fence_seq) IS DISTINCT FROM
          (r.client_id,r.business_id,r.connection_id,d.intent_context_version,r.turn_revision,'READY',r.control_generation,(r.binding->>'activation_fence_seq')::bigint)
          OR (resume.operation,resume.conversation_id,resume.client_id,resume.accepted_generation,resume.activation_fence_seq) IS DISTINCT FROM
            ('RESUME',c.id,c.client_id,t.control_generation,t.activation_fence_seq)
          OR platform.conversation_turn_activation_matches(j.workspace_id,t.id) IS NOT TRUE
          OR platform.material_turn_usable(j.workspace_id,t.id) IS NOT TRUE
          OR platform.human_context_admission(j.workspace_id,c.id,r.snapshot-'code'-'job_id') IS DISTINCT FROM 'CURRENT'
          OR EXISTS(SELECT 1 FROM app.escalations WHERE workspace_id=j.workspace_id AND conversation_id=c.id AND status='PENDING') THEN RETURN false; END IF;
        BEGIN allowed:=platform.messaging_manual_send_allowed(j.workspace_id);
        EXCEPTION WHEN SQLSTATE 'P2301' THEN RETURN false; END;
        RETURN allowed IS TRUE;
      END $$""")


def _begin():
    op.execute("""CREATE FUNCTION platform.ai_delivery_begin(p_job uuid,p_claim uuid,p_generation bigint,p_version bigint,p_observation jsonb) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE j platform.messaging_jobs%ROWTYPE; d platform.ai_deliveries%ROWTYPE; r platform.ai_runs%ROWTYPE;
        box app.outbox_events%ROWTYPE; msg app.messages%ROWTYPE; conn app.channel_connections%ROWTYPE; observation jsonb; allowed boolean; attempt uuid;
      BEGIN
        j:=platform.messaging_guard(p_job,p_claim);
        IF j.kind<>'SEND_AI_TEXT' OR current_database() NOT IN ('asm_local','asm_test') THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
        SELECT * INTO STRICT box FROM app.outbox_events WHERE workspace_id=j.workspace_id AND id=j.outbox_id FOR UPDATE;
        IF box.status<>'PENDING' OR box.kind<>'SEND_AI_TEXT' THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
        SELECT * INTO STRICT d FROM platform.ai_deliveries WHERE workspace_id=j.workspace_id AND send_job_id=j.id AND outbox_id=box.id AND message_id=box.message_id AND selected_kind='reply';
        SELECT * INTO STRICT r FROM platform.ai_runs WHERE workspace_id=j.workspace_id AND id=d.run_id;
        allowed:=platform.ai_delivery_current(j,d,r);
        SELECT * INTO STRICT conn FROM app.channel_connections WHERE workspace_id=j.workspace_id AND id=j.connection_id;
        IF conn.provider='TELEGRAM' AND allowed THEN
          IF j.telegram_probe_claim IS DISTINCT FROM p_claim OR j.telegram_probe_generation IS DISTINCT FROM p_generation OR j.telegram_probe_version IS DISTINCT FROM p_version THEN
            RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
          observation:=platform.telegram_save_observation(j.workspace_id,j.connection_id,p_generation,p_version,p_observation);
          allowed:=observation->>'code'='OBSERVED' AND platform.telegram_can_send(j.workspace_id,j.connection_id,r.conversation_id,true);
        ELSIF conn.provider='CONTROLLED' AND p_observation IS NOT NULL THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        -- All waits are over; recheck generation/native/time/claim at the start boundary.
        allowed:=allowed AND platform.ai_delivery_current(j,d,r);
        IF conn.provider='TELEGRAM' THEN allowed:=allowed AND platform.telegram_can_send(j.workspace_id,j.connection_id,r.conversation_id,true); END IF;
        PERFORM platform.messaging_guard(p_job,p_claim);
        IF allowed IS NOT TRUE THEN
          PERFORM platform.messaging_reschedule(j.id,'NOT_ALLOWED',false,NULL,false);
          RETURN jsonb_build_object('code','NOT_ALLOWED','status','FAILED');
        END IF;
        SELECT * INTO STRICT msg FROM app.messages WHERE workspace_id=j.workspace_id AND id=box.message_id;
        IF (msg.conversation_id,msg.connection_id,msg.direction,msg.content_type,msg.text) IS DISTINCT FROM
          (r.conversation_id,r.connection_id,'OUTBOUND','TEXT',r.result->>'text') THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        attempt:=gen_random_uuid();
        UPDATE app.outbox_events SET status='DISPATCHING',attempt_id=attempt,error_code=NULL,version=version+1 WHERE workspace_id=j.workspace_id AND id=box.id;
        RETURN jsonb_build_object('code','PERMITTED','job_id',j.id,'claim_token',p_claim,'attempt_id',attempt,
          'workspace_id',j.workspace_id,'connection_id',j.connection_id,'provider',conn.provider,'bot_identity',conn.bot_identity,
          'external_connection_id',conn.external_connection_id,'chat_id',msg.provider_chat_id,'text',msg.text,'ai_delivery',true);
      END $$""")


# Generated from closed effective source; populated after the source/DDL audit.
PROFILE_SQL = r"""CREATE FUNCTION platform.ai_delivery_schema_profile() RETURNS jsonb
      LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      WITH expected(signature,body_hash,language,security_definer,volatility,runtime_execute) AS (VALUES ('app.current_messaging_owner_workspace_id()','8ffbd40db1c507c7384981d683bf671cc1914b088d61aa543c8a2a2d44debee6','plpgsql',true,'s',true),('app.current_workspace_id()','f6c6760e5de3ce4885b0c27daf1ab82867438c4c1ec19d95cb084bb4e799475d','plpgsql',true,'s',true),('platform.ai_delivery_begin(uuid,uuid,bigint,bigint,jsonb)','0b18a70e13146c177f4c3188808f0dfd46ec7fa2f51cac8d91bd254ddd4e0362','plpgsql',true,'v',true),('platform.ai_delivery_claim(text,timestamptz,timestamptz,uuid)','7ee3ed1d45d79873dd709a53473da3ffa98d9b150c949c814d552603a5b6fdf6','plpgsql',true,'v',true),('platform.ai_delivery_command(uuid,uuid,text,jsonb)','9d5038f9c26d8876321cb98493c355f502d9b29e3bb97c53e6ce82b04a516c13','plpgsql',true,'v',true),('platform.ai_delivery_current(platform.messaging_jobs,platform.ai_deliveries,platform.ai_runs)','06204da3d01ba76cd26f11f2e42c9e18759ee852470885ac60bcdf9e12d54ccb','plpgsql',true,'v',false),('platform.ai_delivery_enqueue(uuid,uuid)','c933c3e6c1381db9fe7e5234beab38c17ad53adad3829a6760755f6a2f0fc1e1','plpgsql',true,'v',true),('platform.ai_delivery_immutable()','086e4771a6a2c48536e3833b47894da99070f559e55e8e3178ba37537cb0de63','plpgsql',true,'v',false),('platform.ai_delivery_select(platform.messaging_jobs,platform.ai_runs)','b40ce7be68bef556999950227fab8236d90672ec03590baf643bfb4bc834eb55','plpgsql',true,'v',false),('platform.ai_runtime_command(uuid,uuid,text,jsonb)','9725fb95ca4b67b9080e18591b0ff86c709e9eb1fc344c78339af8eb93ad306f','plpgsql',true,'v',true),('platform.ai_runtime_completion_valid(jsonb)','4675d7ce837be36341cdc60deff5c216786ad7f42441bb4bda43bfe5e0dcfb0d','plpgsql',true,'i',false),('platform.ai_runtime_config_valid(jsonb)','20241427cbe5024f6a5876184f29895f28a83191519bf4d99a4e6e6993baf00c','plpgsql',true,'i',false),('platform.ai_runtime_current(platform.messaging_jobs,jsonb)','fdcd7bd225f37b6edaf1bbddb019846f3be8dd9c652da610eaf5a1f983ccca13','plpgsql',true,'v',false),('platform.ai_runtime_receipt(platform.ai_runs)','f027eda65acd1f3d580afbd441ba6009efe88bc430020424af73d1003ae1d2a5','sql',true,'s',false),('platform.ai_runtime_replay(uuid,uuid,jsonb)','36b9248da5aff70b2fec73a85303716769350732f5cee03deb719a9f6d0a17c3','plpgsql',true,'v',true),('platform.ai_runtime_result_valid(jsonb)','7f81305118ab1bff57585a409c91b04ff2eb44d24722d74b35ae05379d5e21d1','plpgsql',true,'i',false),('platform.ai_runtime_view(platform.ai_runs)','4b7264f6dfc835152a5d7e1ade4fdf70b50daaddbc8264fc766ad1fce707b048','sql',true,'s',false),('platform.auth_bootstrap(text,integer)','6eb28b55313391c9d0eb07ca055ff8754e49b83cfeef132d9ba413077545c5dd','plpgsql',true,'v',true),('platform.auth_lock_session(text,boolean)','55ca74ab7475f964865b6d3a6b73778f7139add6a1531781b14362fef0f30428','plpgsql',true,'v',false),('platform.auth_login(text,uuid,bigint,bigint,text,integer)','3f975835d787dd8531c415783aa7492facafcbd5d9def911703780bb1bfc83c1','plpgsql',true,'v',true),('platform.auth_logout(text)','67f05d0d9e47e103cd71365e8f9e574bdd6bcff42dbe156d9f6a68c1b04149e2','plpgsql',true,'v',true),('platform.auth_memberships(text)','0e684da56252678c7bc27b962a49c4213c3de9865a63b43e552221b36ab9b7fb','plpgsql',true,'v',true),('platform.auth_password_lookup(text)','a972cb3994842757f18045afae2ac0f00d90020d482a62043376ecd3ee5b22e3','sql',true,'s',true),('platform.auth_rotate(text,text)','7978763cff421212ae6e184771aa26468cf6be997f29ac386c256dfc0b0640b4','plpgsql',true,'v',true),('platform.auth_session(text)','5e1e2ceaad4b2b1452a02d4d04f7f5d53ebf40e5067b7223baf5a2edc65253f4','plpgsql',true,'v',true),('platform.conversation_control_execute(uuid,uuid,text,text,bigint,bigint)','b8fcb2df6bdb6564b8c68b05d1341e0979a89c9fae1af6244084e1d9fac15ea3','plpgsql',true,'v',true),('platform.conversation_control_fingerprint(uuid,uuid,uuid,uuid,text,bigint,bigint)','60cd026890baa0f09e98c3742ab8da80d5a44fd243fa16d983ea42dcabd2459a','sql',false,'i',false),('platform.conversation_control_locked(uuid,uuid,text,text,bigint,bigint)','0609192f801e87cb185525047a79af365e868c19f6974ce0d35c4a33388d96d0','plpgsql',true,'v',false),('platform.conversation_control_prepare(uuid,uuid,text,text,bigint,bigint)','3d9ce63a7e8b9787adfe7ae96e77a42d6e1af57835f57351fb8846d7e3e07c35','plpgsql',true,'v',true),('platform.conversation_control_read(uuid)','e30448916cece6ee18500c1ef5e9399b1c50dd8a2fad7f95c3cded2cf512f9b8','plpgsql',true,'v',true),('platform.conversation_manual_prelock(uuid,text,text)','0cf8c71a6028ddd08508f9132991d891b6cada8e50c2c5b831b9bc4be2d3c65f','plpgsql',true,'v',true),('platform.conversation_manual_takeover(uuid,uuid)','88a05e4aa03904af8f8ec54e8544dbe867b1f7f22404becef415b76cdf3e3d29','plpgsql',true,'v',false),('platform.conversation_turn_activation_matches(uuid,uuid)','ed3f021b97d11656125233eac69944bfb4a3cf09abe761d63c8cc14d531e90a5','sql',true,'v',false),('platform.escalation_command(uuid,uuid,uuid,text,text,bigint,bigint,bigint,text)','eab7c452b759ae2dd95796b4f8e962f41406896de1ca612638a3f1b7db562152','plpgsql',true,'v',true),('platform.escalation_command_fingerprint(uuid,uuid,uuid,uuid,uuid,text,bigint,bigint,bigint,text)','83bc68632b05e2b1cc74ecb8ac81c595034dccb634182b93fa5335633ebd5c0c','sql',false,'i',false),('platform.escalation_context_changed()','e9653e9625316e84df64a98386a5b4b8addd534032076eb236433f655b65b67f','plpgsql',true,'v',false),('platform.escalation_immutable()','a00c618cdc817b68495e090c143285e7b5832292ebe87ec92a33b1fb62ab23bd','plpgsql',true,'v',false),('platform.escalation_list(integer,text,timestamptz,uuid)','97c703f4dfa2237dc30359661cd53d06c698383556ad45f52a13fa01c1f5b6a0','plpgsql',true,'v',true),('platform.escalation_now()','31ebb037ed35337329fa522d1b51d159d7ed91eccc95e3694b2338abbcea74b1','sql',false,'v',false),('platform.escalation_read(uuid)','baecd1393cd666b40ff743464e5280ee5f07cb61189400eafab5392280cf548a','plpgsql',true,'v',true),('platform.escalation_request_for_turn(uuid,uuid)','f3a9d542a46754fbad85510a192230865a7fe76dcdfe17918330244a55cdac37','plpgsql',true,'v',true),('platform.escalation_request_replay(uuid,uuid)','1e10c8742b9e58fee2780d55d44af2bfb097b0114afae0b2647a201f0416f989','plpgsql',true,'s',true),('platform.escalation_timer_execute(uuid,uuid)','0bbd68c40bcae571fde899c57a51f1628fea26238e662ff015ed428ca8dfd7b3','plpgsql',true,'v',true),('platform.escalation_validity(uuid,uuid,timestamptz)','2185d597e6ae580e5c48d4c03bda56f44865d7d2ef89a94b4815741c8ead7b1e','sql',true,'s',false),('platform.files_begin_fetch(uuid,uuid)','b613633a1c13e033a051e593182d275502a7b1ed9e586a8351e494ca7f394347','plpgsql',true,'v',true),('platform.files_claim_cleanup(integer)','5961679941084084fb083ec755861f9db3ecb0792f57e24fe338eb6df42bf143','plpgsql',true,'v',true),('platform.files_finish_cleanup(uuid,uuid,text)','f25b769900d682dbf58e53f68dad2952162604bcde386343115f86b504aba39d','plpgsql',true,'v',true),('platform.files_finish_fetch(uuid,uuid,uuid)','185f336920b32f3f5c21f300ee76f456610e65164b2a39eca7539948e4c00932','plpgsql',true,'v',true),('platform.files_immutable()','da3e6c650e8c2ed10ad61169127e0808370857c1d458e05b49c37b7db78c4bc2','plpgsql',false,'v',false),('platform.files_manifest_valid(jsonb)','3a4dbfe98efa8df5455d6ac60aeec88250d7ea110408aed5a323557b480eaf67','plpgsql',false,'i',false),('platform.files_plan(uuid,uuid,uuid)','ec5f05ae04a2d4bc0ee91f99a6db768801c78890761f255a86001e8f413ead22','plpgsql',true,'v',false),('platform.files_prepare_upload(uuid,uuid,jsonb)','da20120cf752fc9a0be9b31d19efdd081949391b3ff3b12b72f68e3254192a9f','plpgsql',true,'v',true),('platform.files_read_manifest(uuid,uuid,uuid)','586d58424a80d3eca338f74863d5b2ce4b0b4d97ad62d7aa72862d0374f4bfd7','plpgsql',true,'v',true),('platform.files_upload_json(platform.file_object_uploads)','56d0788594b3d549f87cac1980dd152d902cebb3ba9cd758066fa281c1449c40','sql',false,'s',false),('platform.guard_entitlement()','bed228f9542f5a6f85f28e17f47ab11f3524ab52fb648f4452c9dca4485efe06','plpgsql',false,'v',false),('platform.guard_plan_revision()','9ae94c6c1e0a8b05eeeac31db412d4cd5c8f4157bdae437664c82f5f0fc2c33b','plpgsql',false,'v',false),('platform.guard_require_current(uuid,uuid,uuid,bigint)','b5cce50ac291e7fe75adb5cb2e3c41bef3e7c67ba6229db8131b956d7560e0c8','plpgsql',true,'v',false),('platform.guard_send_begin(uuid,uuid)','af4661dcc860cc13fffc459bfa85f07cfae8c6a45e33ba2e0292f2baf54af835','plpgsql',true,'v',true),('platform.guard_text_fingerprint(jsonb,text)','d22ae019b3f8391ee43bb7e5f8889364694e8c59924f1712cc8533074da76bc2','sql',false,'i',false),('platform.guard_turn_accept(uuid,uuid,text,text)','43ca3517c109f27bc9c0b9d75fc18567b2b9dc9a9e3c730bb05299a266438671','plpgsql',true,'v',true),('platform.guard_turn_prepare(uuid,uuid)','f3487b85737dc4ad58025c176fbfaab7b4d1ec6c0dbac17bb2d9fa066dee6ddd','plpgsql',true,'v',true),('platform.guard_turn_replay(uuid,uuid,text,text)','e919531e4ea823def1545555aa00c91d9ac1b8b0ce9e67d8f2c698bfcb875889','plpgsql',true,'s',true),('platform.human_context_admission(uuid,uuid,jsonb)','155c83c42e96db76b7abfa55efc9823942325094c58bbcec6475f4517e1b15eb','plpgsql',true,'v',false),('platform.human_context_basic_current(uuid,uuid,uuid,bigint)','a60e4a7d9e3d44c08d72f9dfe32dfeffaba0201cf5f702f292679551c811147b','plpgsql',true,'v',false),('platform.human_context_consistent()','6e2d888a129131ecdf801a25fbcdc2f10304e2837e8937a8244d63421361db0f','plpgsql',true,'v',false),('platform.human_context_current_valid(jsonb)','c239ee7a7ee200b392aad3735a5410cfab6cb1f79d4f0eee6e41a115ef498b85','sql',true,'i',false),('platform.human_context_decimal(jsonb,boolean)','9e2e793224366ce5c3ceaa841c0f71ce7de25c0c2ab55b56618634a6852c8cff','sql',true,'i',false),('platform.human_context_effective(app.messages,jsonb,text)','5a4d2518416cc75f3e8740364fac3baf6aa104f8aa05ad9ab992b05d9e81bbfe','sql',true,'s',false),('platform.human_context_escalation_hold(uuid,uuid,timestamptz)','148e7567b42294c742d26858d7cf65acafa2b20125d880d2738f36c131145546','sql',true,'s',false),('platform.human_context_hash(text,text[])','9056f96e6302bd0d4a27b8cf393b33fbdafaaa39b5900ad41516bf4a066be1fc','sql',true,'i',false),('platform.human_context_integrity()','56aa7388cfa150391a0ee3ee7ddc520058147f89d234bf1234fc56a45a5f5ca4','plpgsql',true,'v',false),('platform.human_context_observation_digest(uuid,uuid,uuid,uuid,jsonb)','6c60ce9d15916b797ade41ea410c19ff3b5b5be75f42e7e06cb982cbf654b0e7','sql',true,'i',false),('platform.human_context_observations(uuid,integer,jsonb)','525edce2323e2ab781d46c115990d916f81eea6d0e9d9c1006798cdb01be00cc','plpgsql',true,'v',true),('platform.human_context_observe(platform.telegram_update_receipts,jsonb)','002b6410107e55a5025d49178b127a672e642ec3418eb2bcac7f038f6ae6fe3d','plpgsql',true,'v',false),('platform.human_context_policy_command(uuid,uuid,text,text,text,bigint,jsonb,jsonb)','7f61285125cb8f04a21d4c7d1748f315ece530c5f619317ba61ab51740b032b8','plpgsql',true,'v',false),('platform.human_context_policy_guard()','9fad112676add9ee5c5874ab9d79583053161024f361c5f8cfb7d5caca7970aa','plpgsql',true,'v',false),('platform.human_context_policy_result(platform.human_context_policy_receipts)','14a64a6a05514af4312ef42d62554b396dc2d885235424bcb13f68b7aac3edb6','sql',true,'s',false),('platform.human_context_preview(jsonb)','edd77e725660f24f41d2a96424e2434bec0c58432b8a7ceb0b6dd1bb57a3e381','sql',true,'i',false),('platform.human_context_projection(uuid,uuid,timestamptz)','8d38da64c526acb61365aa06eb293d117e1d8af93b598b5a507da3a23bc17b51','sql',true,'s',false),('platform.human_context_read(uuid)','513256e45b12356cdd149e934bf11c56fefe44a321bfdfe498e0dbf0a1939b1c','plpgsql',true,'v',true),('platform.human_context_reason(jsonb,boolean)','799072de08ee913f09c11686e9a8300e55602ae7d5bf3f8610bb1a35a6d2cb19','sql',true,'i',false),('platform.human_context_reconcile(uuid,text,jsonb)','d75cd2b145fbe84ec26923b924b744f9a728546ee7f2254c9f62e5d2ca26546d','plpgsql',true,'v',true),('platform.human_context_reconcile_result(platform.human_context_reconciliations)','a2645c2165f2eee80027b426b5377c233f3412b4c52e32c7aab04708e011790d','sql',true,'s',false),('platform.human_context_revision_json(platform.human_context_reconciliations)','83a0d64f71b77f9dc8633c7f52498355c758cccdf2bc96d0908c4a125d362094','sql',true,'s',false),('platform.ai_delivery_schema_profile()','527fce5681d5345369cd88b555a302df6d305ef8566cf12a666198eb64a6f4ac','sql',true,'s',false),('platform.human_context_snapshot_check(jsonb,text)','220cf8e65eb0c0b72fd03a87b3b97f834f738215ce7ec7461ccd0f32af12c110','plpgsql',true,'s',false),('platform.human_context_snapshot_valid(jsonb,text)','9db423e054719c6ddc7f6bd5a90307ba8b95523b9ce036098ba2d75bf97f84f4','plpgsql',true,'s',false),('platform.human_context_stale()','355dfcb1e982c63fee2e5d2f9df0bae68218e5c211b80ed1aaa14b6fe353f68a','plpgsql',true,'s',false),('platform.human_context_test_guard(platform.messaging_jobs,jsonb)','5600ba815891a13dcbfddb224575d449d1b14c2121e6ea10fb5f4e2bb597639f','plpgsql',true,'v',false),('platform.human_context_test_prelock(platform.messaging_jobs)','4ec2eb2e2e5b65b433ef05e6aed5a7a4bf0008a86871562307dbddd42a2de2d7','plpgsql',true,'v',false),('platform.human_context_text_valid(text)','efcf1bcedf46ec93feb243adb5b1d719e0d1d17658094a54a1a4152504b865b8','sql',true,'i',false),('platform.human_context_turn_projection(uuid,uuid,timestamptz)','6fbe7e7d06fd7818fd7b5c0b0a1df0f5f132fc734cbb2e74a90964edf17edd92','sql',true,'s',false),('platform.human_context_uuid(jsonb)','033d0b6c405aa313bece14c3338046b7624d0da096e3c6b60e9e15417e77ff77','sql',true,'i',false),('platform.human_context_wait(uuid,uuid,text)','34666cb91739199ba976e2af87a4d6cb40afa12bfa00d72d3bda3cb8d7ab69af','plpgsql',true,'v',false),('platform.human_context_work_lookup(uuid,uuid)','13969135268d8f00c990b49ff1d2aaed5e79a9ee9602fdd3d8f5ce366cd18be9','sql',true,'s',false),('platform.human_context_work_replay(uuid,uuid)','28bc46d45b5b5306e3ce4b0fa6fc0c47fb6b300ab7e28541c4d7df58c2ba6946','sql',true,'s',true),('platform.human_context_work_valid(platform.messaging_jobs)','bc7c086476e335c5f58cd1cddc409018f81f40d7995e383d7734ccfde58a93db','sql',true,'s',false),('platform.initialize_local_billing(uuid,text,integer,text,text,text,timestamptz,timestamptz,text)','20b0e1ea5d37d8710b485232cff1441ea7c6998d431233877d2ab1814f620e83','plpgsql',true,'v',false),('platform.initialize_local_messaging_billing(uuid,text,timestamptz,timestamptz)','2863259a15ff3178525d044704c26dbc57c35e4322f5412bed6dd13989098f7d','plpgsql',true,'v',false),('platform.initialize_telegram_connection(uuid,uuid,text,text,text,jsonb)','bfae87784d2145810f9ed12f1dfab4416d8041c9d2044c1397204bbe0f8275bf','plpgsql',true,'v',false),('platform.material_apply(uuid,uuid,uuid,jsonb)','529e701178043d44c7e5cbee6c4651fae3e6a3a6be36412764ac1e8b60ac7c39','plpgsql',true,'v',false),('platform.material_apply_context(uuid,uuid,uuid,boolean)','22636529fed5a35055d99e9a42f52615626150300ad08d62918bbbfc9bce3069','plpgsql',true,'v',false),('platform.material_bind(uuid,uuid,boolean,uuid)','8afd09d2d0576c14480ce5a5414aa5d924082a007888932aec43dec185a19408','plpgsql',true,'v',false),('platform.material_bump_turns(uuid,uuid[],uuid)','0019faf314594758579f035373f6e5d14d37a4cb9d3b75b4bb9c0a0116e09020','plpgsql',true,'v',false),('platform.material_content_valid(jsonb)','c89faf57741e2b8d179b4201aac7979e891984e867ecb27bfc455a66c0104da4','plpgsql',false,'i',false),('platform.material_fold(uuid,uuid,uuid)','74d5202cf7fe15ae866dbd81eb88e635564a189db0195a9c0311c15fe76cecf8','plpgsql',true,'v',false),('platform.material_identity(uuid,uuid,jsonb)','d4bb3911e0b35af35585df2307496147b4c02ab6ac6b4869fe53a3445eb9dca3','plpgsql',true,'s',false),('platform.material_integrity()','292dd9cbb24f1d2289b6e6b628160a8755841ecc4fbc4ab2a26a3c5c54cab7f7','plpgsql',true,'v',false),('platform.material_no_file()','5b01911a52d5fc64edbf23895a31d8316d34221fc4c399524f4932f4496ef892','plpgsql',true,'v',false),('platform.material_object(jsonb,text[])','aa02c1b4b7f6ad7ac3687dccee0f680b231876af0bc78d5d149b4cc6d08d40bf','sql',false,'i',false),('platform.material_process(platform.messaging_jobs)','351d28449ee12317a4f046b8f70998b0e51206954146e45e91a6491995cdcd09','plpgsql',true,'v',false),('platform.material_processing_replay(uuid,uuid)','5d04cfdae703e4786f4d61975d484ec2c1686fcbec620c98e33dab7eafe94a96','sql',true,'s',true),('platform.material_result_valid(jsonb)','6070c0641ab897095effdd4f841e0e34e8cc1b788d33dd64c5ef6d4cf2f6e9b6','plpgsql',false,'v',false),('platform.material_semantic(jsonb)','f1ec36fd862ecf60cd69b1f1d1e41b7c09cfab38a689f6127d0969541985bb92','sql',false,'i',false),('platform.material_state_valid(jsonb)','a2344f16e36d45187529757a8bd2c9fad1f0b2c6c6887ab81b631279a65f10c1','sql',false,'i',false),('platform.material_suppression_check()','6d19f17d542008095defb943095c9f9c894aa7441123806b24df110903cbaa52','plpgsql',true,'v',false),('platform.material_target_check()','0c41bd7a4b3399c47a7cae6707e9bb28d98ed248e687b26ec58c094a9c6dd7b1','plpgsql',true,'v',false),('platform.material_turn_usable(uuid,uuid)','9f2f31ab578bb9d66f1bd8ed9d57f6dd9ae5a06b9427c1138d85f8121452c893','sql',true,'v',false),('platform.message_effective(uuid,uuid)','7354f194d5c35a121421f41aad9740686de71519aea9879e762c111353777e82','plpgsql',true,'v',false),('platform.messaging_admit(uuid,uuid)','27d0551d90b2f854b54a8b9fff35ff92bff9b131de4653000015026460fefc31','plpgsql',true,'v',true),('platform.messaging_begin_send(uuid,uuid)','ced9aced8fef1976bae75cedc268ed5a25b651c01fb276502bcc77badc8453e1','plpgsql',true,'v',true),('platform.messaging_claim(text,timestamptz,timestamptz,uuid)','1e88ecfd996f7b98034e20a8b8143de35ca3e576d252c182e89f61ea27bcad01','plpgsql',true,'v',true),('platform.messaging_fingerprint(jsonb,boolean)','d64c3b2ea0f53e0861315883b7420e5aee652b28dffa093bce0d3fff2986a342','plpgsql',false,'i',false),('platform.messaging_finish_send(uuid,uuid,uuid,text,text,text)','4c6db15c26212a1a943e58eaf3f6355988380106a2be7ed04832ab6c8c673a0b','sql',true,'v',true),('platform.messaging_finish_send(uuid,uuid,uuid,text,text,text,integer)','be8b1b54e4cf59d45544aca490b7b7863cdbcb7b0601174919967558994bd632','plpgsql',true,'v',true),('platform.messaging_guard(uuid,uuid)','0a57433b9b39446547a2f2accfeb9516238ae8c9210f67773e30f749a756adb5','plpgsql',true,'v',false),('platform.messaging_immutable()','3971e82a86a3826eeaf7b9e24458fbb1adc64cce0e8f2cb43a46384348519934','plpgsql',false,'v',false),('platform.messaging_ingest(text,text,jsonb,uuid)','2833a40d4ec37a014eab30fcbe2893a590d50c909b71eebc754e1c575ecb9f32','plpgsql',true,'v',true),('platform.messaging_job_json(platform.messaging_jobs)','7ccc5395def311a662f2b4845b33ce5e85af7c94d5920ddb03b97bcb2d37a5f3','sql',false,'s',false),('platform.messaging_lock_billing()','69f212c164437a4b39942e87f32c53df5cb4fb8e5f2bf9da2e1952e98be180eb','plpgsql',true,'v',true),('platform.messaging_lock_billing_workspace(uuid)','8797320c11ace5b9c44b37ed511293f0f61af6c0ba1b58abcd5cd60b5ec27204','plpgsql',true,'v',false),('platform.messaging_lock_owner(uuid,uuid)','11168bbd30eec24cfdb0ad9de67c70f767c0bf62480c7579638e58ecfb42bce1','plpgsql',true,'v',false),('platform.messaging_manual_send_allowed(uuid)','4ce13d4ca64dbc09aada275a295d76a01a08ac809768a2448fb1e1f074cd4bd6','plpgsql',true,'v',false),('platform.messaging_prepare_text(uuid,text,text)','39c14deb5337876f28970605ea399f9106f5e768e9f8f8c54b2e3746d570bca9','plpgsql',true,'v',true),('platform.messaging_process_inbox(uuid,uuid)','5a63a698c440120cebeaf4c6ebf8133f04abf41f610ef2ad3c3e34312b4ef2e3','plpgsql',true,'v',true),('platform.messaging_read_connections(integer,timestamptz,uuid)','242c6123fd6c57c44eb8c9ff658fe437700144b9e6525fff6c2ccf24c892511b','plpgsql',true,'v',true),('platform.messaging_read_conversations(integer)','aaeb0c33dd9e7501e92c3bcb599e38073bfeef8c3f3b7352cd22ef4a4b60e040','plpgsql',true,'v',true),('platform.messaging_read_conversations(integer,timestamptz,uuid)','81949cfd2357e8886003e7c5618fed4a7ce2b4d4474c2764c377783e97ed9658','plpgsql',true,'v',true),('platform.messaging_read_delivery(uuid)','f3cdd1d7de19b740961b0f4a6aece317b4fdd4ef1dafcfc9ce25ab6908bc29ed','plpgsql',true,'v',true),('platform.messaging_read_inbox(uuid)','7666d3eb0bc87de36bb75b4a7a8f9ab4e31f329f5fcd2fbaccc275d819b6d171','plpgsql',true,'v',true),('platform.messaging_read_messages(uuid,integer)','fcfa6f29a181d0e97ce52ae98ec0d008859e6568ad118e89234a5ed5b932a460','plpgsql',true,'v',true),('platform.messaging_read_messages(uuid,integer,timestamptz,uuid)','9e0828d184e46ded7e48e437be6a1a7737b96b2a90fb761fce6eafbfb5c5185f','plpgsql',true,'v',true),('platform.messaging_recover_expired(timestamptz,timestamptz,uuid)','1b040cbb1c6fc0183aed53681ef4394a2bc3b8d94715f76757563c9b778271f0','plpgsql',true,'v',true),('platform.messaging_request_text(uuid,text,text)','13dc01a5b25f4b2d5da4835fa8aabf14f33f98573532e730929006688be7059c','plpgsql',true,'v',true),('platform.messaging_reschedule(uuid,text,boolean)','6409aa21554ccaa346587c2f4da07bc6941e27c4736db9bd518f26e4c7947438','sql',true,'v',false),('platform.messaging_reschedule(uuid,text,boolean,integer)','21e8b16de21a18ff5646eeb28f7eceb801da8ab5bfc7d8e1799e6a91b9a2d074','sql',true,'v',false),('platform.messaging_reschedule(uuid,text,boolean,integer,boolean)','78922f1c89a00c0ae7a18e8d4fc509e2a529ce5e10c76b86e072a7fe9b1bff85','plpgsql',true,'v',false),('platform.messaging_retry(uuid,uuid,text,boolean)','6bf436d91a4d47932ff12e24d74c57f8dfa2d1102e470456c6706b62c0f2d64f','plpgsql',true,'v',true),('platform.messaging_valid_id(text,integer,integer)','9e1cf327f38fa1437a5a755e3c68d531c0209b585722755c865b395f616419f5','sql',false,'i',false),('platform.messaging_validate_event(jsonb)','1f7a2405bde9171aa196355bfae185cbc4084aeffbbdfda20d4f8828fdb95791','plpgsql',false,'v',false),('platform.resolve_workspace_membership(uuid,uuid)','8ce9bdd67c17bc83442bea3a5e7a15337a51074e0ea6408855b10542e39ceb39','sql',true,'v',true),('platform.telegram_begin_send(uuid,uuid,bigint,bigint,jsonb)','c8f15c23837fa40b86451574ee3e04cc4292dd91b2929a891424e0d8acec556d','plpgsql',true,'v',true),('platform.telegram_can_send(uuid,uuid,uuid,boolean)','b273ad02ca6825bdf6b037173c3be840a615d551283c3e922357bee3f7f16811','plpgsql',true,'v',false),('platform.telegram_fingerprint(text,jsonb)','449929a9e41d6e4f38d30341fcb7c7a488d55f06169dbaca2c18df461effdc06','plpgsql',false,'i',false),('platform.telegram_fingerprint_v2(text,jsonb)','4499d0bd8bc0ad010d856d3e20b21847a9cfedfaeced5c14ace118443c2a940f','plpgsql',false,'i',false),('platform.telegram_ingest(text,jsonb,uuid)','0b4d1cc97c47522e9abde484362aad3cd4967ae9c256e7719d310c09702f7c09','plpgsql',true,'v',true),('platform.telegram_numeric_id(text)','1519829aa6e3dfc1ac03180377c72929d7a7a3dcedd1b037ae7d3ea4872413cf','sql',false,'i',false),('platform.telegram_owner_observe(uuid,bigint,bigint,jsonb)','8ecd18d13fe815311aa9b076b3313efb98bbc3276962c44932516c5692666380','plpgsql',true,'v',true),('platform.telegram_probe_json(platform.telegram_connection_state)','bce40873beb21b5aa8c5b850468f9f5fce85a865a60567066129998f75e0c273','sql',false,'s',false),('platform.telegram_receipt_json(platform.telegram_update_receipts,text)','d6c81a402d8c8b53aab72685cff893e34100973ed8c7a2aefa2ab3e9a6ef5800','sql',true,'s',false),('platform.telegram_replay_v1(text,jsonb)','a3598d76df2c0bf876945fa306e0410e3249c2018ff62b21e4da2968beaacf32','plpgsql',true,'v',true),('platform.telegram_save_observation(uuid,uuid,bigint,bigint,jsonb)','97d4fe38521a276d4aac005feddf587a6c296e5e58ca909167cbcbb123be4816','plpgsql',true,'v',false),('platform.telegram_validate_observation(jsonb)','5aefbca98cb203f4bfc5e65101fbb6432c492858ac55fdae0b48fec520855ffc','plpgsql',false,'v',false),('platform.telegram_validate_projection(text,jsonb)','0d088863a241460dcc16b7ea45072bb7ac03303bfba9f4d2e13e0b91b5e4500b','plpgsql',false,'v',false),('platform.telegram_validate_v2(text,jsonb)','7304efba94d26f93ba4d7a69030878056eb611f855ee4620a3ea6cdf61f79003','plpgsql',false,'v',false),('platform.telegram_worker_probe(uuid,uuid)','164d96bf050df8a95185269431fbff8d72f408fc0706d8d95286329b8ccde8f1','plpgsql',true,'v',true),('platform.turn_consumer_finalize(uuid,uuid,jsonb)','503318da5d3265664ba4416752a0c745550cafb6f1cdb18ee66ac40065e31eb6','plpgsql',true,'v',true),('platform.turn_consumer_replay(uuid,uuid)','4469b30f0df26f6bfb02777b2c5c8da184abc5b3bcae8dcdf45c871d9bbb7e6c','plpgsql',true,'s',true),('platform.turn_enqueue(uuid,uuid,uuid)','383110c7c42c8979410560f3d0d98b784844f5da16a0a1d7f8d04fb71bd26e5f','plpgsql',true,'v',false),('platform.turn_execute(uuid,uuid)','3bbd3e507d1b11425c2541d8300ca9d9e2c4cda172b77c05e2cc94b8d19c3b0d','plpgsql',true,'v',true),('platform.turn_group_message(uuid,uuid,uuid)','89687e327f17d1a00751192fda5a56e7aeac8297b539fe95b1317d01de8d78f7','plpgsql',true,'v',false),('platform.turn_immutable()','bfc42050fa3442c8eed763a861d16ae7fc6ea3f5f3646a193e54fe22704a7df9','plpgsql',false,'v',false),('platform.turn_ingress()','d8e6040eae9ce55f0e6d8f2b1338d4ea2e3b6b8a7d25f2e7da8963032e6488f0','plpgsql',true,'v',false),('platform.turn_material()','be30caa9fdb5cf0c3ca22e41559232e6cbe8d6246c62e9c343db539ec4303f3d','plpgsql',true,'v',false),('platform.turn_member_check()','8cbbd5b8ccd97858edc24ba68fd904e5b4af3068b355e506d7d5cc03af5b6293','plpgsql',true,'v',false),('platform.turn_members_consistent()','3acccfede293794fcc84890da99535a2730217fd1f11eb37c7ed153e2c675405','plpgsql',true,'v',false),('platform.turn_preflight(platform.messaging_jobs,boolean,boolean)','73f139ddac65b5e5b1098e40d1aaed541c140e7fcf00d4d0df8b45a15563034e','plpgsql',true,'v',false),('platform.turn_require_isolation()','ba0e99b67e71fc6d6fa6886967282f9c5bcf7b0046e5812d34dfdfc5df8dd5d3','plpgsql',false,'v',false),('platform.turn_seal(uuid,uuid,timestamptz,uuid,boolean)','bc83afb9ce59538928edfe86cdc74c7ab1951640244570d05177aa3bcd08676f','plpgsql',true,'v',false),('platform.turn_snapshot(uuid,uuid)','ffac09fed2777b0439558faa5b071445fb1d6c74e605ff7331e29b67788e9e3e','plpgsql',true,'v',false),('platform.turn_supersede(platform.messaging_jobs)','6a26f30e71da741ab60ca4c4a191fa44aab528f36588a564bcb5a0069f8eeab2','plpgsql',true,'v',false),('platform.update_billing_contact(bigint,text,text)','80d0ce6854e33601584fe350ee4b586796d0066b6288bf9a26aeec80aa23f3ed','plpgsql',true,'v',true)),
      columns_expected(table_name,column_names) AS (VALUES ('app.audit_events',ARRAY['workspace_id','audit_event_id','occurred_at','actor_kind','actor_user_account_id','correlation_id','event_type','object_type','object_id','object_version','payload','billing_account_object_id','message_object_id','conversation_object_id','conversation_control_generation','escalation_object_id','escalation_operation','material_target_id','material_source_receipt_id','native_revision_id','native_policy_receipt_id','native_connection_id','native_conversation_id']::text[]),('app.business_members',ARRAY['workspace_id','id','business_id','user_account_id','name','role','status','version','created_at']::text[]),('app.businesses',ARRAY['workspace_id','id','name','status','version','created_at']::text[]),('app.channel_connections',ARRAY['workspace_id','id','business_id','provider','bot_identity','external_connection_id','status','version','created_at','human_context_policy','human_context_policy_epoch']::text[]),('app.client_identities',ARRAY['workspace_id','id','client_id','provider','external_user_id','created_at']::text[]),('app.clients',ARRAY['workspace_id','id','version','created_at']::text[]),('app.conversation_turn_messages',ARRAY['workspace_id','message_id','turn_id','conversation_id','connection_id','direction','content_type','origin_inbox_id','turn_ingress_at','turn_ingress_seq','file_id','membership_form','initial_suppression_id','suppression_disposition']::text[]),('app.conversation_turns',ARRAY['workspace_id','id','conversation_id','connection_id','provider_chat_id','revision','control_generation','state','policy_version','debounce_ms','group_ms','media_ms','max_members','member_count','media_group_id','first_ingress_at','last_ingress_at','hard_at','quiet_at','media_deadline_at','seal_time','closed_at','ready_at','readiness','error_code','created_at','ingress_control_mode','activation_fence_seq','material_invalidated']::text[]),('app.conversations',ARRAY['workspace_id','id','connection_id','business_id','client_id','identity_id','provider_chat_id','version','created_at','last_client_inbound_at','control_mode','control_generation','activation_fence_seq','human_observation_epoch','human_context_revision_id']::text[]),('app.escalations',ARRAY['workspace_id','id','namespace','conversation_id','client_id','connection_id','turn_id','source_job_id','source_job_kind','source_job_step','source_claim_token','turn_revision','resume_receipt_id','control_generation','activation_fence_seq','input_context_version','waiting_context_version','request_snapshot','context_fingerprint','request_fingerprint','creation_result','reason','assignee_user_account_id','question','policy','created_at','due_at','second_reminder_at','expires_at','first_reminded_at','second_reminded_at','version','status','closure_reason','completed_at','answer_text','decided_by_user_account_id']::text[]),('app.file_objects',ARRAY['workspace_id','id','message_id','connection_id','conversation_id','required_direction','required_content_type','status','winner_intent_id','winner_state','storage_key','mime_type','size_bytes','sha256','width','height','error_code','version','created_at','completed_at']::text[]),('app.locations',ARRAY['workspace_id','id','business_id','name','status','version','created_at']::text[]),('app.messages',ARRAY['workspace_id','id','conversation_id','connection_id','provider_chat_id','provider_message_id','direction','content_type','text','image_file_id','media_group_id','occurred_at','projection_fingerprint','version','created_at']::text[]),('app.outbox_events',ARRAY['workspace_id','id','connection_id','message_id','kind','required_direction','status','attempt_id','provider_message_id','error_code','completed_at','version','created_at']::text[]),('platform.ai_deliveries',ARRAY['workspace_id','job_id','source_job_id','source_claim_hash','connection_id','turn_id','turn_revision','kind','step','run_id','selected_kind','message_id','outbox_id','send_job_id','escalation_id','intent_context_version','created_at']::text[]),('platform.ai_provider_calls',ARRAY['workspace_id','run_id','sequence','claim_hash','attempt_count','budget','completion','reserved_at','completed_at']::text[]),('platform.ai_runs',ARRAY['workspace_id','id','job_id','connection_id','conversation_id','client_id','business_id','kind','step','turn_id','turn_revision','resume_receipt_id','control_generation','binding','snapshot','snapshot_digest','storage_fingerprint','config','config_fingerprint','deadline','calls_used','reads_used','tokens_reserved','cost_reserved','read_audit','result','selected_at','winning_claim_hash','created_at']::text[]),('platform.alembic_version',ARRAY['version_num']::text[]),('platform.auth_credentials',ARRAY['user_account_id','login','password_hash','version','created_at']::text[]),('platform.auth_sessions',ARRAY['token_hash','user_account_id','credential_version','account_version','created_at','expires_at','revoked_at']::text[]),('platform.billing_contact_command_receipts',ARRAY['workspace_id','receipt_id','billing_account_id','operation','idempotency_key','request_fingerprint','expected_version','status','result_version','result_outcome','created_at','completed_at']::text[]),('platform.channel_routes',ARRAY['workspace_id','id','connection_id','provider','bot_identity','route_key','created_at']::text[]),('platform.conversation_control_receipts',ARRAY['workspace_id','id','operation_namespace','operation','idempotency_key','conversation_id','client_id','actor_user_account_id','correlation_id','expected_generation','expected_context_version','previous_mode','accepted_mode','previous_generation','accepted_generation','context_version','activation_fence_seq','request_fingerprint','audit_event_id','audit_event_type','accepted_at','result','guard_profile','human_context_revision_id','human_context_policy_epoch','human_observation_epoch']::text[]),('platform.escalation_command_receipts',ARRAY['workspace_id','id','namespace','idempotency_key','escalation_id','conversation_id','client_id','actor_user_account_id','correlation_id','operation','expected_version','expected_control_generation','expected_context_version','accepted_version','accepted_status','accepted_context_version','request_fingerprint','audit_event_id','audit_event_type','accepted_at','result']::text[]),('platform.file_object_uploads',ARRAY['workspace_id','id','file_id','job_id','claim_token','storage_key','mime_type','size_bytes','sha256','width','height','status','cleanup_claim_token','cleanup_lease_until','cleanup_attempts','next_check_at','last_checked_at','cleanup_outcome','version','created_at']::text[]),('platform.human_context_observations',ARRAY['workspace_id','id','conversation_id','client_id','connection_id','provider_chat_id','epoch','policy_epoch','control_generation','first_source_receipt_id','classification','semantic_digest','accepted_at']::text[]),('platform.human_context_policy_receipts',ARRAY['workspace_id','id','connection_id','business_id','provider','bot_identity','external_connection_id','owner_user_id','actor_db_role','namespace','idempotency_key','request_fingerprint','operation','expected_policy','expected_policy_epoch','accepted_policy','accepted_policy_epoch','change','source_profile','audit_event_id','event_type','accepted_at','result']::text[]),('platform.human_context_reconciliations',ARRAY['workspace_id','id','conversation_id','client_id','connection_id','provider_chat_id','actor_user_account_id','namespace','idempotency_key','request_fingerprint','correlation_id','previous_revision_id','revision_no','expected_generation','expected_context_version','accepted_context_version','policy_epoch','observation_epoch','reviewed_ingress_seq','reviewed_input_state_hash','reviewed_gap_digest','reviewed_gap_overflow','disposition','context_text','source_media','attestation','audit_event_id','event_type','accepted_at','result']::text[]),('platform.inbox_events',ARRAY['workspace_id','id','connection_id','provider','bot_identity','external_connection_id','required_direction','event_id','normalized_event','event_fingerprint','correlation_id','received_at','status','result_code','message_id','completed_at','version','turn_ingress_at','turn_ingress_seq','turn_control_generation','turn_control_mode','turn_activation_fence_seq','material_result','material_claim_token','human_context_source_receipt_id','human_context_observation_id']::text[]),('platform.message_initial_suppressions',ARRAY['workspace_id','id','message_id','target_id','origin_inbox_id','effect_id','source_receipt_id','previous_version','accepted_version','initial_material','fold_witnesses','membership_disposition']::text[]),('platform.message_material_effects',ARRAY['workspace_id','id','target_id','message_id','source_receipt_id','audit_event_id','event_type','previous_version','accepted_version','reason','accepted_at']::text[]),('platform.message_material_targets',ARRAY['workspace_id','id','connection_id','provider_chat_id','provider_message_id','message_id','conversation_id','client_id','direction','outbox_id','inbound_provider_id','required_sent','quarantined','original_grouping_closed','origin_identity','deleted','undated_seen','max_edit_at','candidate','dated_conflict','delete_receipt','undated_receipt','candidate_receipt','conflict_receipt','current_material']::text[]),('platform.messaging_command_receipts',ARRAY['workspace_id','id','operation','idempotency_key','request_fingerprint','actor_user_account_id','correlation_id','message_id','outbox_id','audit_event_id','accepted_at']::text[]),('platform.messaging_jobs',ARRAY['workspace_id','id','connection_id','kind','inbox_id','outbox_id','correlation_id','status','available_at','claim_token','lease_until','worker_id','attempt_count','first_started_at','error_code','completed_at','last_attempt_id','last_claim_token','last_outcome','last_provider_message_id','last_error_code','version','created_at','file_id','last_retry_after_seconds','last_retry_due','telegram_probe_claim','telegram_probe_generation','telegram_probe_version','turn_id','turn_revision','step','turn_outcome','turn_input','guard_rejection','escalation_id','escalation_outcome','context_block_reason','context_wait_claim_token','context_wait_result']::text[]),('platform.plan_entitlements',ARRAY['plan_revision_id','capability_key','value_kind','enabled','limit_value','criticality','created_at']::text[]),('platform.saas_plan_revisions',ARRAY['plan_revision_id','plan_id','revision','publication_state','published_at','created_at']::text[]),('platform.saas_plans',ARRAY['plan_id','code','display_name','status','created_at']::text[]),('platform.telegram_connection_state',ARRAY['workspace_id','connection_id','provider','bot_identity','external_connection_id','owner_user_id','generation','observation_version','observed_generation','observed_at','observation_xid','is_enabled','can_reply','error_code','material_enabled']::text[]),('platform.telegram_provenance',ARRAY['receipt_id','codec','bot_identity','update_id','workspace_id','connection_id','inbox_id','projection','material_enabled','human_context_observation_id']::text[]),('platform.telegram_update_receipts',ARRAY['id','bot_identity','update_id','fingerprint','kind','result_code','workspace_id','connection_id','inbox_id','received_at','codec']::text[]),('platform.turn_consumer_receipts',ARRAY['workspace_id','job_id','connection_id','kind','turn_id','turn_revision','step','consumer','winning_claim_token','input_context_version','input_control_generation','snapshot_digest','result','accepted_at']::text[]),('platform.turn_guard_receipts',ARRAY['workspace_id','job_id','winning_claim_token','connection_id','conversation_id','client_id','turn_id','turn_revision','resume_receipt_id','input_control_generation','activation_fence_seq','input_context_version','snapshot_digest','consumer','request_fingerprint','result_text','outcome','accepted_at','intent_context_version','message_id','outbox_id','send_job_id','namespace','kind','step','direction','content_type','send_kind']::text[]),('platform.user_accounts',ARRAY['id','status','version','created_at']::text[]),('platform.workspace_billing_accounts',ARRAY['workspace_id','billing_account_id','contact_display_name','version','created_at','updated_at']::text[]),('platform.workspace_memberships',ARRAY['workspace_id','user_account_id','role','status','version','created_at']::text[]),('platform.workspace_service_modes',ARRAY['workspace_id','service_mode_id','mode','reason_code','effective_from','effective_until','version','created_at','updated_at']::text[]),('platform.workspace_subscriptions',ARRAY['workspace_id','subscription_id','plan_revision_id','required_publication_state','status','funding_mode','effective_from','effective_until','version','created_at','updated_at']::text[]),('platform.workspaces',ARRAY['id','status','version','created_at']::text[])),
      functions AS MATERIALIZED (SELECT p.*,n.nspname||'.'||p.proname AS name,l.lanname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        JOIN pg_language l ON l.oid=p.prolang WHERE n.nspname IN ('app','platform') AND p.prokind='f'),
      tables AS MATERIALIZED (SELECT r.oid,n.nspname||'.'||r.relname AS name,r.relowner,r.relrowsecurity,r.relforcerowsecurity,r.relacl,
        array_agg(a.attname::text ORDER BY a.attnum) AS columns FROM pg_class r JOIN pg_namespace n ON n.oid=r.relnamespace
        JOIN pg_attribute a ON a.attrelid=r.oid AND a.attnum>0 AND NOT a.attisdropped WHERE n.nspname IN ('app','platform') AND r.relkind='r'
        GROUP BY r.oid,n.nspname,r.relname,r.relowner,r.relrowsecurity,r.relforcerowsecurity,r.relacl),
      validity AS MATERIALIZED (SELECT
        (SELECT count(*) FROM functions)=183 AND (SELECT count(DISTINCT to_regprocedure(signature)) FROM expected)=182
        AND NOT EXISTS(SELECT 1 FROM expected e LEFT JOIN functions f ON f.oid=to_regprocedure(e.signature)
          WHERE f.oid IS NULL OR encode(sha256(convert_to(f.prosrc,'UTF8')),'hex')<>e.body_hash OR f.lanname<>e.language
            OR f.prosecdef<>e.security_definer OR f.provolatile::text<>e.volatility OR f.proowner<>'asm_migrator'::regrole
            OR has_function_privilege('asm_runtime',f.oid,'EXECUTE')<>e.runtime_execute
            OR f.proconfig IS DISTINCT FROM ARRAY['search_path=pg_catalog, pg_temp']
            OR EXISTS(SELECT 1 FROM aclexplode(f.proacl) a WHERE a.grantee=0 AND a.privilege_type='EXECUTE'))
        AND EXISTS(SELECT 1 FROM functions f WHERE f.oid='platform.ai_delivery_schema_profile()'::regprocedure
          AND f.proowner='asm_migrator'::regrole AND f.lanname='sql' AND f.prosecdef AND f.provolatile='s'
          AND f.proconfig=ARRAY['search_path=pg_catalog, pg_temp'] AND NOT has_function_privilege('asm_runtime',f.oid,'EXECUTE')
          AND NOT EXISTS(SELECT 1 FROM aclexplode(f.proacl) a WHERE a.grantee=0 AND a.privilege_type='EXECUTE'))
        AND EXISTS(SELECT 1 FROM pg_roles WHERE rolname='asm_runtime' AND rolcanlogin AND NOT rolsuper AND NOT rolbypassrls
          AND NOT rolinherit AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolreplication)
        AND NOT EXISTS(SELECT 1 FROM pg_auth_members WHERE member='asm_runtime'::regrole)
        AND (SELECT count(*) FROM tables)=48 AND NOT EXISTS(SELECT 1 FROM columns_expected e LEFT JOIN tables t ON t.name=e.table_name
          WHERE t.oid IS NULL OR t.columns IS DISTINCT FROM e.column_names)
        AND NOT EXISTS(SELECT 1 FROM tables WHERE name IN ('platform.human_context_observations','platform.human_context_reconciliations','platform.human_context_policy_receipts','platform.ai_runs','platform.ai_provider_calls','platform.ai_deliveries')
          AND (relowner<>'asm_migrator'::regrole OR NOT relrowsecurity OR NOT relforcerowsecurity OR has_table_privilege('asm_runtime',oid,'SELECT,INSERT,UPDATE,DELETE')))
        AND (SELECT version_num FROM platform.alembic_version)='0015' AS valid),
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
      SELECT jsonb_build_object('schema_revision','0015','valid',coalesce(v.valid,false)
        AND encode(sha256(convert_to((c.value-'functions')::text,'UTF8')),'hex')='e939e9f303843a84256f9315e6016e1a888aea0c18469539aa53147c6d339bee',
        'profile_sha256',encode(sha256(convert_to(E'asm:m3:native_schema:v1\n'||c.value::text,'UTF8')),'hex')) FROM validity v CROSS JOIN catalog c $$"""


def upgrade():
    op.execute(
        "LOCK TABLE platform.messaging_jobs,app.outbox_events,app.escalations IN ACCESS EXCLUSIVE MODE"
    )
    op.execute(TABLE_SQL)
    op.execute("ALTER TABLE platform.ai_deliveries ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE platform.ai_deliveries FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY ai_migrator ON platform.ai_deliveries TO asm_migrator USING(true) WITH CHECK(true)"
    )
    op.execute("REVOKE ALL ON platform.ai_deliveries FROM PUBLIC,asm_runtime")
    _constraints(True)
    _enqueue()
    _command()
    _select()
    _current()
    _begin()
    for sql in replacements().values():
        op.execute(sql)
    if PROFILE_SQL:
        op.execute(PROFILE_SQL)
    for signature in FUNCTIONS:
        if signature != "ai_delivery_schema_profile()" or PROFILE_SQL:
            op.execute(f"REVOKE ALL ON FUNCTION platform.{signature} FROM PUBLIC,asm_runtime")
    for signature in PUBLIC:
        op.execute(f"GRANT EXECUTE ON FUNCTION platform.{signature} TO asm_runtime")


def downgrade():
    op.execute("""LOCK TABLE platform.messaging_jobs,platform.ai_deliveries,app.outbox_events,app.escalations IN ACCESS EXCLUSIVE MODE;
      DO $$ BEGIN IF EXISTS(SELECT 1 FROM platform.ai_deliveries) OR EXISTS(SELECT 1 FROM platform.messaging_jobs WHERE kind='SEND_AI_TEXT')
        OR EXISTS(SELECT 1 FROM app.outbox_events WHERE kind='SEND_AI_TEXT') OR EXISTS(SELECT 1 FROM app.escalations WHERE source_job_step='AI_GENERATE') THEN
          RAISE EXCEPTION 'AI_DELIVERY_DURABLE_DATA' USING ERRCODE='55000'; END IF; END $$""")
    for sql in ORIGINAL.values():
        op.execute(sql.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1))
    op.execute("DROP TRIGGER ai_delivery_immutable ON platform.ai_deliveries")
    for signature in FUNCTIONS:
        op.execute(f"DROP FUNCTION platform.{signature}")
    op.execute("DROP TABLE platform.ai_deliveries")
    _constraints(False)


CHECKS = (
    (
        "platform.messaging_jobs",
        "messaging_jobs_kind_check",
        "kind IN ('PROCESS_INBOX','SEND_MANUAL_TEXT','SEND_GUARDED_TEXT','FETCH_IMAGE','PROCESS_TURN','ESCALATION_TIMER')",
        "kind IN ('PROCESS_INBOX','SEND_MANUAL_TEXT','SEND_GUARDED_TEXT','SEND_AI_TEXT','FETCH_IMAGE','PROCESS_TURN','ESCALATION_TIMER')",
    ),
    (
        "platform.messaging_jobs",
        "messaging_jobs_check",
        "((kind='PROCESS_INBOX' AND inbox_id IS NOT NULL AND outbox_id IS NULL AND file_id IS NULL AND turn_id IS NULL) OR\n        (kind IN ('SEND_MANUAL_TEXT','SEND_GUARDED_TEXT') AND outbox_id IS NOT NULL AND inbox_id IS NULL AND file_id IS NULL AND turn_id IS NULL) OR\n        (kind='FETCH_IMAGE' AND file_id IS NOT NULL AND inbox_id IS NULL AND outbox_id IS NULL AND turn_id IS NULL) OR\n        (kind='PROCESS_TURN' AND turn_id IS NOT NULL AND inbox_id IS NULL AND outbox_id IS NULL AND file_id IS NULL) OR (kind='ESCALATION_TIMER' AND escalation_id IS NOT NULL AND inbox_id IS NULL AND outbox_id IS NULL AND file_id IS NULL AND turn_id IS NULL))",
        "((kind='PROCESS_INBOX' AND inbox_id IS NOT NULL AND outbox_id IS NULL AND file_id IS NULL AND turn_id IS NULL) OR\n        (kind IN ('SEND_MANUAL_TEXT','SEND_GUARDED_TEXT','SEND_AI_TEXT') AND outbox_id IS NOT NULL AND inbox_id IS NULL AND file_id IS NULL AND turn_id IS NULL) OR\n        (kind='FETCH_IMAGE' AND file_id IS NOT NULL AND inbox_id IS NULL AND outbox_id IS NULL AND turn_id IS NULL) OR\n        (kind='PROCESS_TURN' AND turn_id IS NOT NULL AND inbox_id IS NULL AND outbox_id IS NULL AND file_id IS NULL) OR (kind='ESCALATION_TIMER' AND escalation_id IS NOT NULL AND inbox_id IS NULL AND outbox_id IS NULL AND file_id IS NULL AND turn_id IS NULL))",
    ),
    (
        "app.outbox_events",
        "outbox_events_kind_check",
        "kind IN ('SEND_MANUAL_TEXT','SEND_GUARDED_TEXT')",
        "kind IN ('SEND_MANUAL_TEXT','SEND_GUARDED_TEXT','SEND_AI_TEXT')",
    ),
    (
        "app.escalations",
        "escalations_source_job_step_check",
        "source_job_step='ESCALATE_OWNER'",
        "source_job_step IN ('ESCALATE_OWNER','AI_GENERATE')",
    ),
)


def _constraints(forward):
    for table, name, old, new in CHECKS:
        check = new if forward else old
        op.execute(
            f"ALTER TABLE {table} DROP CONSTRAINT {name}, ADD CONSTRAINT {name} CHECK({check})"
        )
