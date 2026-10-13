"""LOCAL/TEST guarded turns and dispatch; exact unused-schema reversal to 0009.

Applied 0001--0009 are immutable. ORIGINAL contains the exact accepted capability
bodies replaced below, including their whitespace/security/search_path profiles.
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

ORIGINAL = {
    "conversation_control_execute": r"""CREATE OR REPLACE FUNCTION platform.conversation_control_execute(
      p_conversation uuid,p_client uuid,p_operation text,p_key text,p_generation bigint,p_context bigint)
      RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE ws uuid; actor uuid; corr uuid; prepared jsonb; conv app.conversations%ROWTYPE;
        allowed boolean; target text; fence bigint; moment timestamptz; receipt uuid; audit uuid; result jsonb;
      BEGIN
        prepared:=platform.conversation_control_locked(p_conversation,p_client,p_operation,p_key,p_generation,p_context);
        IF prepared->>'code'='REPLAY' THEN RETURN prepared; END IF;
        ws:=app.current_messaging_owner_workspace_id(); actor:=nullif(current_setting('asm.actor_id',true),'')::uuid;
        corr:=nullif(current_setting('asm.correlation_id',true),'')::uuid;
        SELECT * INTO STRICT conv FROM app.conversations WHERE workspace_id=ws AND id=p_conversation;
        IF p_operation='RESUME' THEN
          -- Structural product failures precede availability, which precedes CAS.
          allowed:=platform.messaging_manual_send_allowed(ws);
          IF allowed IS NOT TRUE OR NOT EXISTS(SELECT 1 FROM app.businesses WHERE workspace_id=ws AND id=conv.business_id AND status='ACTIVE')
            OR NOT EXISTS(SELECT 1 FROM app.channel_connections WHERE workspace_id=ws AND id=conv.connection_id AND status='ACTIVE') THEN
            RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2401'; END IF;
        END IF;
        IF conv.control_generation<>p_generation OR conv.version<>p_context THEN
          RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P2401'; END IF;
        IF conv.control_generation=9223372036854775807 THEN
          RAISE EXCEPTION 'CONTROL_VERSION_EXHAUSTED' USING ERRCODE='P2401'; END IF;
        target:=CASE p_operation WHEN 'TAKEOVER' THEN 'HUMAN' ELSE 'AI' END;
        IF p_operation='RESUME' THEN fence:=nextval('platform.turn_ingress_seq'); END IF;
        moment:=clock_timestamp(); receipt:=uuidv7();
        UPDATE app.conversations SET control_mode=target,control_generation=control_generation+1,activation_fence_seq=fence
          WHERE workspace_id=ws AND id=conv.id;
        INSERT INTO app.audit_events(workspace_id,actor_kind,actor_user_account_id,correlation_id,event_type,object_type,object_id,object_version,payload)
          VALUES(ws,'USER_ACCOUNT',actor,corr,CASE p_operation WHEN 'TAKEOVER' THEN 'CONVERSATION_TAKEN_OVER' ELSE 'CONVERSATION_RESUMED' END,
            'CONVERSATION',conv.id,conv.version,jsonb_build_object('previous_mode',conv.control_mode,'control_mode',target,
              'previous_generation',conv.control_generation::text,'control_generation',(conv.control_generation+1)::text)) RETURNING audit_event_id INTO audit;
        result:=jsonb_build_object('workspace_id',ws,'conversation_id',conv.id,'client_id',conv.client_id,'receipt_id',receipt,'audit_event_id',audit,
          'operation',p_operation,'previous_mode',conv.control_mode,'accepted_mode',target,'previous_generation',conv.control_generation::text,
          'accepted_generation',(conv.control_generation+1)::text,'context_version',conv.version::text,
          'accepted_at',to_char(moment AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'));
        INSERT INTO platform.conversation_control_receipts(workspace_id,id,operation,idempotency_key,conversation_id,client_id,actor_user_account_id,correlation_id,
          expected_generation,expected_context_version,previous_mode,accepted_mode,previous_generation,accepted_generation,context_version,
          activation_fence_seq,request_fingerprint,audit_event_id,accepted_at,result)
          VALUES(ws,receipt,p_operation,p_key,conv.id,conv.client_id,actor,corr,p_generation,p_context,conv.control_mode,target,conv.control_generation,
            conv.control_generation+1,conv.version,fence,decode(prepared->>'request_fingerprint','hex'),audit,moment,result);
        RETURN jsonb_build_object('code','ACCEPTED','result',result,'request_fingerprint',prepared->>'request_fingerprint');
      END $$""",
    "conversation_control_read": r"""CREATE OR REPLACE FUNCTION platform.conversation_control_read(p_conversation uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE ws uuid; result jsonb;
      BEGIN
        PERFORM platform.turn_require_isolation(); ws:=app.current_messaging_owner_workspace_id();
        IF ws IS NULL OR platform.messaging_lock_owner(ws,nullif(current_setting('asm.actor_id',true),'')::uuid) IS NOT TRUE THEN
          RAISE EXCEPTION 'ACCESS_DENIED' USING ERRCODE='P2401'; END IF;
        SELECT jsonb_build_object('workspace_id',c.workspace_id,'conversation_id',c.id,'client_id',c.client_id,'control_mode',c.control_mode,
          'control_generation',c.control_generation::text,'context_version',c.version::text,
          'observed_at',to_char(clock_timestamp() AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
          'manual_delivery',jsonb_build_object(
            'has_dispatching',EXISTS(SELECT 1 FROM app.messages m JOIN app.outbox_events o ON (o.workspace_id,o.message_id)=(m.workspace_id,m.id)
              WHERE m.workspace_id=ws AND m.conversation_id=c.id AND o.status='DISPATCHING'),
            'has_unknown',EXISTS(SELECT 1 FROM app.messages m JOIN app.outbox_events o ON (o.workspace_id,o.message_id)=(m.workspace_id,m.id)
              WHERE m.workspace_id=ws AND m.conversation_id=c.id AND o.status='UNKNOWN')))
          INTO result FROM app.conversations c WHERE c.workspace_id=ws AND c.id=p_conversation;
        IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P2401'; END IF;
        RETURN result;
      END $$""",
    "turn_enqueue": r"""CREATE OR REPLACE FUNCTION platform.turn_enqueue(ws uuid,p_turn uuid,corr uuid) RETURNS void
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE t app.conversation_turns%ROWTYPE; stage text; due timestamptz;
      BEGIN
        SELECT * INTO STRICT t FROM app.conversation_turns WHERE workspace_id=ws AND id=p_turn;
        IF t.state='FAILED' THEN RETURN; END IF;
        stage:=CASE t.state WHEN 'COLLECTING' THEN 'GROUP' WHEN 'WAITING_MEDIA' THEN 'MEDIA' ELSE 'TEST_CONSUME' END;
        due:=CASE t.state WHEN 'COLLECTING' THEN least(t.quiet_at,t.hard_at) WHEN 'WAITING_MEDIA' THEN t.media_deadline_at ELSE clock_timestamp() END;
        INSERT INTO platform.messaging_jobs(workspace_id,connection_id,kind,turn_id,turn_revision,step,available_at,correlation_id)
          VALUES(ws,t.connection_id,'PROCESS_TURN',t.id,t.revision,stage,due,corr)
          ON CONFLICT(workspace_id,turn_id,turn_revision,step) DO NOTHING;
      END $$""",
    "turn_execute": r"""CREATE OR REPLACE FUNCTION platform.turn_execute(p_job uuid,p_claim uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE j platform.messaging_jobs%ROWTYPE; t app.conversation_turns%ROWTYPE; input jsonb; outcome text;
      BEGIN
        j:=platform.messaging_guard(p_job,p_claim);
        IF j.kind<>'PROCESS_TURN' THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        PERFORM platform.turn_preflight(j,false,false);
        PERFORM platform.messaging_guard(p_job,p_claim);
        IF platform.turn_supersede(j) THEN
          RETURN jsonb_build_object('code','SUPERSEDED','job_id',j.id,'turn_id',j.turn_id,'turn_revision',j.turn_revision);
        END IF;
        SELECT * INTO STRICT t FROM app.conversation_turns WHERE workspace_id=j.workspace_id AND id=j.turn_id;
        IF j.step='TEST_CONSUME' THEN
          IF t.state<>'READY' THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
          input:=coalesce(j.turn_input,platform.turn_snapshot(j.workspace_id,j.turn_id));
          IF j.turn_input IS NULL THEN UPDATE platform.messaging_jobs SET turn_input=input WHERE id=j.id; END IF;
          RETURN input || jsonb_build_object('code','SNAPSHOT','job_id',j.id);
        END IF;
        IF (j.step='GROUP' AND (t.state<>'COLLECTING' OR clock_timestamp()<least(t.quiet_at,t.hard_at))) OR
          (j.step='MEDIA' AND (t.state<>'WAITING_MEDIA' OR clock_timestamp()<t.media_deadline_at)) THEN
          RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        PERFORM platform.turn_seal(j.workspace_id,t.id,coalesce(t.seal_time,least(t.quiet_at,t.hard_at)),j.correlation_id,true);
        SELECT * INTO STRICT t FROM app.conversation_turns WHERE workspace_id=j.workspace_id AND id=j.turn_id;
        outcome:=CASE WHEN t.state='WAITING_MEDIA' THEN 'WAITING_MEDIA' ELSE 'GROUPED' END;
        UPDATE platform.messaging_jobs SET status='SUCCEEDED',turn_outcome=outcome,error_code=NULL,claim_token=NULL,lease_until=NULL,worker_id=NULL,
          completed_at=clock_timestamp(),version=version+1 WHERE id=j.id;
        RETURN jsonb_build_object('code',outcome,'job_id',j.id,'turn_id',t.id,'turn_revision',t.revision);
      END $$""",
    "turn_preflight": r"""CREATE OR REPLACE FUNCTION platform.turn_preflight(j platform.messaging_jobs,p_nowait boolean,p_terminal boolean) RETURNS void
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE lock_suffix text:=CASE WHEN p_nowait THEN ' NOWAIT' ELSE '' END;
        conv uuid; tid uuid; disposition text; file app.file_objects%ROWTYPE;
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
        ELSIF j.kind='SEND_MANUAL_TEXT' THEN
          EXECUTE 'SELECT status FROM app.outbox_events WHERE workspace_id=$1 AND id=$2 FOR UPDATE'||lock_suffix INTO STRICT disposition USING j.workspace_id,j.outbox_id;
          IF p_terminal AND disposition IN ('PENDING','DISPATCHING') THEN
            SELECT m.conversation_id INTO STRICT conv FROM app.messages m JOIN app.outbox_events b
              ON (b.workspace_id,b.message_id)=(m.workspace_id,m.id) WHERE b.workspace_id=j.workspace_id AND b.id=j.outbox_id;
          END IF;
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
    "messaging_reschedule": r"""CREATE OR REPLACE FUNCTION platform.messaging_reschedule(p_job uuid,p_error text,p_retry boolean,p_delay integer,p_nowait boolean) RETURNS jsonb
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
        IF platform.turn_supersede(j) THEN RETURN jsonb_build_object('code','SUPERSEDED','status','SUCCEEDED','job_id',j.id,'outbox_id',NULL); END IF;
        final_error:=CASE WHEN p_retry AND NOT retry THEN 'RETRY_EXHAUSTED' ELSE p_error END;
        IF j.kind='FETCH_IMAGE' THEN
          IF NOT EXISTS(SELECT 1 FROM app.file_objects WHERE workspace_id=j.workspace_id AND id=j.file_id AND status='PENDING') THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
          UPDATE platform.file_object_uploads SET status='ABANDONED',next_check_at=clock_timestamp(),version=version+1
            WHERE workspace_id=j.workspace_id AND file_id=j.file_id AND status='PREPARED';
          IF NOT retry THEN
            UPDATE app.file_objects SET status='FAILED',error_code=final_error,completed_at=clock_timestamp(),version=version+1 WHERE workspace_id=j.workspace_id AND id=j.file_id;
          END IF;
        ELSIF j.kind='PROCESS_INBOX' AND NOT retry THEN
          UPDATE platform.inbox_events SET status='FAILED',result_code=final_error,completed_at=clock_timestamp(),version=version+1 WHERE workspace_id=j.workspace_id AND id=j.inbox_id;
        ELSIF j.kind='SEND_MANUAL_TEXT' THEN
          delivery:=CASE WHEN retry THEN 'PENDING' ELSE 'FAILED' END;
          UPDATE app.outbox_events SET status=delivery,error_code=final_error,completed_at=CASE WHEN retry THEN NULL ELSE clock_timestamp() END,version=version+1 WHERE workspace_id=j.workspace_id AND id=j.outbox_id;
        ELSIF j.kind='PROCESS_TURN' AND NOT retry THEN
          UPDATE app.conversation_turns SET state='FAILED',error_code=final_error,revision=revision+1 WHERE workspace_id=j.workspace_id AND id=j.turn_id;
        END IF;
        UPDATE platform.messaging_jobs SET status=CASE WHEN retry THEN 'READY' ELSE 'DEAD' END,
          claim_token=NULL,lease_until=NULL,worker_id=NULL,error_code=final_error,available_at=due,
          turn_outcome=CASE WHEN kind='PROCESS_TURN' AND NOT retry THEN 'FAILED' END,
          completed_at=CASE WHEN retry THEN NULL ELSE clock_timestamp() END,version=version+1 WHERE id=j.id;
        RETURN jsonb_build_object('code',CASE WHEN retry THEN 'RETRY_SCHEDULED' ELSE final_error END,'status',coalesce(delivery,CASE WHEN retry THEN 'READY' ELSE 'DEAD' END),'job_id',j.id,'outbox_id',j.outbox_id);
      END $$""",
    "messaging_retry": r"""CREATE OR REPLACE FUNCTION platform.messaging_retry(p_job uuid,p_claim uuid,p_error text,p_retry boolean) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE j platform.messaging_jobs%ROWTYPE; state text;
      BEGIN
        j:=platform.messaging_guard(p_job,p_claim);
        IF p_error IS NULL OR p_error NOT IN ('DEPENDENCY_TIMEOUT','DEPENDENCY_UNAVAILABLE','INVALID_INPUT') OR p_retry IS NULL OR (p_retry AND p_error='INVALID_INPUT') THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        IF j.kind='SEND_MANUAL_TEXT' THEN
          SELECT status INTO state FROM app.outbox_events WHERE workspace_id=j.workspace_id AND id=j.outbox_id FOR UPDATE;
          IF state<>'PENDING' THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
        END IF;
        RETURN platform.messaging_reschedule(p_job,p_error,p_retry);
      END $$""",
    "messaging_recover_expired": r"""CREATE OR REPLACE FUNCTION platform.messaging_recover_expired(p_until timestamptz,p_at timestamptz,p_id uuid) RETURNS jsonb
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
          IF j.kind='SEND_MANUAL_TEXT' THEN SELECT status INTO state FROM app.outbox_events WHERE workspace_id=j.workspace_id AND id=j.outbox_id; END IF;
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
    "messaging_finish_send": r"""CREATE OR REPLACE FUNCTION platform.messaging_finish_send(p_job uuid,p_claim uuid,p_attempt uuid,p_outcome text,p_provider_message text,p_error text,p_retry_after_seconds integer) RETURNS jsonb
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
        IF NOT FOUND OR j.kind<>'SEND_MANUAL_TEXT' THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
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
}

PUBLIC_FUNCTIONS = (
    "platform.guard_turn_prepare(uuid,uuid)",
    "platform.guard_turn_accept(uuid,uuid,text,text)",
    "platform.guard_turn_replay(uuid,uuid,text,text)",
    "platform.guard_send_begin(uuid,uuid)",
)
PRIVATE_FUNCTIONS = (
    "platform.guard_require_current(uuid,uuid,uuid,bigint)",
    "platform.guard_text_fingerprint(jsonb,text)",
)

# Fixed old checks, not recovered from a mutable runtime database.
OLD_CHECKS = {
    "messaging_jobs_kind_check": "kind IN ('PROCESS_INBOX','SEND_MANUAL_TEXT','FETCH_IMAGE','PROCESS_TURN')",
    "messaging_jobs_check": """(kind='PROCESS_INBOX' AND inbox_id IS NOT NULL AND outbox_id IS NULL AND file_id IS NULL AND turn_id IS NULL) OR
        (kind='SEND_MANUAL_TEXT' AND outbox_id IS NOT NULL AND inbox_id IS NULL AND file_id IS NULL AND turn_id IS NULL) OR
        (kind='FETCH_IMAGE' AND file_id IS NOT NULL AND inbox_id IS NULL AND outbox_id IS NULL AND turn_id IS NULL) OR
        (kind='PROCESS_TURN' AND turn_id IS NOT NULL AND inbox_id IS NULL AND outbox_id IS NULL AND file_id IS NULL)""",
    "messaging_jobs_turn_check": """(kind<>'PROCESS_TURN' AND turn_revision IS NULL AND step IS NULL AND turn_outcome IS NULL) OR
        (kind='PROCESS_TURN' AND turn_revision IS NOT NULL AND turn_revision>0 AND step IS NOT NULL
          AND step IN ('GROUP','MEDIA','TEST_CONSUME') AND (turn_outcome IS NULL OR turn_outcome IN ('GROUPED','WAITING_MEDIA','OBSERVED','STALE','SUPERSEDED','FAILED')))""",
    "messaging_jobs_turn_input_check": "turn_input IS NULL OR (kind='PROCESS_TURN' AND step='TEST_CONSUME' AND jsonb_typeof(turn_input)='object')",
}


def _replace(name: str, *changes: tuple[str, str]) -> None:
    body = ORIGINAL[name]
    for before, after in changes:
        assert body.count(before) == 1, (name, before)
        body = body.replace(before, after)
    op.execute(body)


def _schema() -> None:
    op.execute("""LOCK TABLE platform.conversation_control_receipts,platform.messaging_jobs,
      app.outbox_events IN ACCESS EXCLUSIVE MODE""")
    op.execute("""ALTER TABLE platform.conversation_control_receipts
      ADD COLUMN guard_profile text,
      ADD CONSTRAINT control_guard_profile_check CHECK(guard_profile IS NULL OR
        (guard_profile='CONTROLLED_GUARDS_V1' AND operation='RESUME' AND accepted_mode='AI')),
      ADD CONSTRAINT control_guard_reference_key UNIQUE(workspace_id,id,conversation_id,client_id,accepted_generation)""")
    for name, old in OLD_CHECKS.items():
        new = old.replace(
            "kind='SEND_MANUAL_TEXT'", "kind IN ('SEND_MANUAL_TEXT','SEND_GUARDED_TEXT')"
        )
        new = new.replace(
            "'SEND_MANUAL_TEXT','FETCH_IMAGE'",
            "'SEND_MANUAL_TEXT','SEND_GUARDED_TEXT','FETCH_IMAGE'",
        )
        new = new.replace(
            "'GROUP','MEDIA','TEST_CONSUME'", "'GROUP','MEDIA','TEST_CONSUME','GUARDED_TEXT'"
        )
        new = new.replace(
            "'SUPERSEDED','FAILED'",
            "'SUPERSEDED','FAILED','ACCEPTED','NOT_ALLOWED','ALREADY_ACCEPTED'",
        )
        new = new.replace("step='TEST_CONSUME'", "step IN ('TEST_CONSUME','GUARDED_TEXT')")
        op.execute(
            f"ALTER TABLE platform.messaging_jobs DROP CONSTRAINT {name}, ADD CONSTRAINT {name} CHECK({new})"
        )
    op.execute("""ALTER TABLE app.outbox_events DROP CONSTRAINT outbox_events_kind_check,
      ADD CONSTRAINT outbox_events_kind_check CHECK(kind IN ('SEND_MANUAL_TEXT','SEND_GUARDED_TEXT')),
      ADD CONSTRAINT outbox_guard_kind_key UNIQUE(workspace_id,id,connection_id,kind)""")
    op.execute("""ALTER TABLE platform.messaging_jobs
      ADD COLUMN guard_rejection text,
      ADD CONSTRAINT messaging_guard_rejection_check CHECK(guard_rejection IS NULL OR
        (guard_rejection IN ('STALE','SUPERSEDED','NOT_ALLOWED') AND kind='SEND_GUARDED_TEXT'
          AND status='DEAD' AND error_code IS NOT NULL AND error_code='NOT_ALLOWED')),
      ADD CONSTRAINT messaging_guard_send_key UNIQUE(workspace_id,id,outbox_id,kind),
      ADD CONSTRAINT messaging_send_kind_fkey FOREIGN KEY(workspace_id,outbox_id,connection_id,kind)
        REFERENCES app.outbox_events(workspace_id,id,connection_id,kind) ON DELETE RESTRICT""")
    op.execute("""CREATE FUNCTION platform.guard_text_fingerprint(p_input jsonb,p_text text) RETURNS bytea
      LANGUAGE sql IMMUTABLE STRICT SET search_path=pg_catalog,pg_temp AS $$
        SELECT sha256(convert_to(E'asm:m3:guarded_text:v1\\n'||p_input::text||E'\\n'||p_text,'UTF8'))
      $$""")
    op.execute("""CREATE TABLE platform.turn_guard_receipts(
      workspace_id uuid NOT NULL,job_id uuid NOT NULL,winning_claim_token uuid NOT NULL,
      connection_id uuid NOT NULL,conversation_id uuid NOT NULL,client_id uuid NOT NULL,
      turn_id uuid NOT NULL,turn_revision bigint NOT NULL CHECK(turn_revision>0),
      resume_receipt_id uuid NOT NULL,input_control_generation bigint NOT NULL CHECK(input_control_generation>0),
      activation_fence_seq bigint NOT NULL CHECK(activation_fence_seq>0),
      input_context_version bigint NOT NULL CHECK(input_context_version>0),
      snapshot_digest text NOT NULL CHECK(snapshot_digest ~ '^[0-9a-f]{64}$'),
      consumer text NOT NULL DEFAULT 'CONTROLLED_GUARDS_V1' CHECK(consumer='CONTROLLED_GUARDS_V1'),
      request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32),
      result_text text NOT NULL CHECK(char_length(result_text) BETWEEN 1 AND 4096 AND octet_length(result_text)<=16384),
      outcome text NOT NULL CHECK(outcome IN ('ACCEPTED','STALE','SUPERSEDED','NOT_ALLOWED')),
      accepted_at timestamptz NOT NULL DEFAULT clock_timestamp() CHECK(isfinite(accepted_at)),
      intent_context_version bigint,message_id uuid,outbox_id uuid,send_job_id uuid,
      namespace text NOT NULL DEFAULT 'GUARDED_TEXT_V1' CHECK(namespace='GUARDED_TEXT_V1'),
      kind text NOT NULL DEFAULT 'PROCESS_TURN' CHECK(kind='PROCESS_TURN'),
      step text NOT NULL DEFAULT 'GUARDED_TEXT' CHECK(step='GUARDED_TEXT'),
      direction text NOT NULL DEFAULT 'OUTBOUND' CHECK(direction='OUTBOUND'),
      content_type text NOT NULL DEFAULT 'TEXT' CHECK(content_type='TEXT'),
      send_kind text NOT NULL DEFAULT 'SEND_GUARDED_TEXT' CHECK(send_kind='SEND_GUARDED_TEXT'),
      PRIMARY KEY(workspace_id,job_id),UNIQUE(workspace_id,outbox_id),
      FOREIGN KEY(workspace_id,job_id,connection_id,kind,turn_id,turn_revision,step)
        REFERENCES platform.messaging_jobs(workspace_id,id,connection_id,kind,turn_id,turn_revision,step) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,turn_id,connection_id,conversation_id)
        REFERENCES app.conversation_turns(workspace_id,id,connection_id,conversation_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,conversation_id,client_id)
        REFERENCES app.conversations(workspace_id,id,client_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,resume_receipt_id,conversation_id,client_id,input_control_generation)
        REFERENCES platform.conversation_control_receipts(workspace_id,id,conversation_id,client_id,accepted_generation) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,message_id,connection_id,conversation_id,direction,content_type)
        REFERENCES app.messages(workspace_id,id,connection_id,conversation_id,direction,content_type) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,outbox_id,message_id) REFERENCES app.outbox_events(workspace_id,id,message_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,send_job_id,outbox_id,send_kind)
        REFERENCES platform.messaging_jobs(workspace_id,id,outbox_id,kind) ON DELETE RESTRICT,
      CONSTRAINT guard_intent_shape CHECK(
        (outcome='ACCEPTED' AND intent_context_version IS NOT NULL AND message_id IS NOT NULL AND outbox_id IS NOT NULL AND send_job_id IS NOT NULL
          AND input_context_version<9223372036854775807 AND intent_context_version::numeric=input_context_version::numeric+1) OR
        (outcome<>'ACCEPTED' AND intent_context_version IS NULL AND message_id IS NULL AND outbox_id IS NULL AND send_job_id IS NULL)))""")
    op.execute(
        "CREATE UNIQUE INDEX guard_one_intent_per_turn ON platform.turn_guard_receipts(workspace_id,turn_id) WHERE outcome='ACCEPTED'"
    )
    op.execute("ALTER TABLE platform.turn_guard_receipts OWNER TO asm_migrator")
    op.execute("ALTER TABLE platform.turn_guard_receipts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE platform.turn_guard_receipts FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY guard_migrator ON platform.turn_guard_receipts TO asm_migrator USING(true) WITH CHECK(true)"
    )
    op.execute("REVOKE ALL ON platform.turn_guard_receipts FROM PUBLIC,asm_runtime")
    op.execute(
        "CREATE TRIGGER guard_receipt_immutable BEFORE UPDATE ON platform.turn_guard_receipts FOR EACH ROW EXECUTE FUNCTION platform.turn_immutable()"
    )


# These are SQL source fragments, not additional database capabilities. Every
# caller first locks its admitted Job (and its Outbox for dispatch). No material
# hook uses this authority/billing chain. Only immutable Resume refs are read
# before locks; mutable rows and time are re-read after the last wait.
LOCKS = """
        SELECT * INTO STRICT t FROM app.conversation_turns WHERE workspace_id=j.workspace_id AND id=target_turn;
        SELECT * INTO STRICT conv FROM app.conversations WHERE workspace_id=j.workspace_id AND id=t.conversation_id;
        SELECT * INTO rec FROM platform.conversation_control_receipts
          WHERE workspace_id=j.workspace_id AND conversation_id=conv.id AND accepted_generation=t.control_generation AND operation='RESUME';
        IF rec.id IS NOT NULL THEN PERFORM platform.messaging_lock_owner(j.workspace_id,rec.actor_user_account_id); END IF;
        PERFORM 1 FROM app.businesses WHERE workspace_id=j.workspace_id AND id=conv.business_id FOR SHARE;
        PERFORM 1 FROM app.channel_connections WHERE workspace_id=j.workspace_id AND id=j.connection_id FOR SHARE;
        PERFORM platform.messaging_lock_billing_workspace(j.workspace_id);
        SELECT * INTO STRICT conv FROM app.conversations WHERE workspace_id=j.workspace_id AND id=t.conversation_id FOR NO KEY UPDATE;
        SELECT * INTO STRICT t FROM app.conversation_turns WHERE workspace_id=j.workspace_id AND id=target_turn FOR NO KEY UPDATE;
        PERFORM platform.messaging_guard(p_job,p_claim);
"""
RECEIPT_JSON = """jsonb_build_object('code',r.outcome,'workspace_id',r.workspace_id,'job_id',r.job_id,
        'connection_id',r.connection_id,'conversation_id',r.conversation_id,'client_id',r.client_id,
        'turn_id',r.turn_id,'turn_revision',r.turn_revision,'resume_receipt_id',r.resume_receipt_id,
        'input_control_generation',r.input_control_generation,'activation_fence_seq',r.activation_fence_seq,
        'input_context_version',r.input_context_version,'snapshot_digest',r.snapshot_digest,'consumer',r.consumer,
        'request_fingerprint',encode(r.request_fingerprint,'hex'),'result_text',r.result_text,'accepted_at',r.accepted_at,
        'intent_context_version',r.intent_context_version,'message_id',r.message_id,'outbox_id',r.outbox_id,'send_job_id',r.send_job_id)"""
PROGRESS_JSON = """jsonb_build_object('code',outcome,'job_id',j.id,'turn_id',j.turn_id,'turn_revision',j.turn_revision,
        'accepted_job_id',prior.job_id,'message_id',prior.message_id,'outbox_id',prior.outbox_id,'send_job_id',prior.send_job_id)"""
TERMINAL_JOB = """UPDATE platform.messaging_jobs SET status='SUCCEEDED',turn_outcome=outcome,error_code=NULL,
        claim_token=NULL,lease_until=NULL,worker_id=NULL,completed_at=clock_timestamp(),version=version+1 WHERE id=j.id;"""
ALREADY = f"""
        SELECT * INTO prior FROM platform.turn_guard_receipts g WHERE g.workspace_id=j.workspace_id AND g.turn_id=j.turn_id AND g.outcome='ACCEPTED';
        IF FOUND THEN
          outcome:='ALREADY_ACCEPTED'; {TERMINAL_JOB}
          RETURN {PROGRESS_JSON};
        END IF;
"""


def _capabilities() -> None:
    op.execute("""CREATE FUNCTION platform.guard_require_current(ws uuid,p_turn uuid,p_resume uuid,p_context bigint) RETURNS text
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE t app.conversation_turns%ROWTYPE; c app.conversations%ROWTYPE;
        r platform.conversation_control_receipts%ROWTYPE; allowed boolean;
      BEGIN
        -- Private check under the caller's complete lock chain. The current
        -- database and canonical provider are independent of user GUC/payload.
        SELECT * INTO STRICT t FROM app.conversation_turns WHERE workspace_id=ws AND id=p_turn;
        SELECT * INTO STRICT c FROM app.conversations WHERE workspace_id=ws AND id=t.conversation_id;
        SELECT * INTO r FROM platform.conversation_control_receipts WHERE workspace_id=ws AND id=p_resume;
        IF t.state<>'READY' OR c.version IS DISTINCT FROM p_context OR
          platform.conversation_turn_activation_matches(ws,p_turn) IS NOT TRUE THEN RETURN 'STALE'; END IF;
        IF r.id IS NULL OR (r.conversation_id,r.client_id,r.accepted_generation,r.activation_fence_seq) IS DISTINCT FROM
          (c.id,c.client_id,t.control_generation,t.activation_fence_seq) THEN RETURN 'STALE'; END IF;
        IF current_database() NOT IN ('asm_local','asm_test') OR r.operation<>'RESUME' OR
          r.guard_profile IS DISTINCT FROM 'CONTROLLED_GUARDS_V1' OR
          platform.messaging_lock_owner(ws,r.actor_user_account_id) IS NOT TRUE OR
          NOT EXISTS(SELECT 1 FROM app.businesses WHERE workspace_id=ws AND id=c.business_id AND status='ACTIVE') OR
          NOT EXISTS(SELECT 1 FROM app.channel_connections WHERE workspace_id=ws AND id=t.connection_id
            AND id=c.connection_id AND business_id=c.business_id AND provider='CONTROLLED' AND status='ACTIVE') THEN RETURN 'NOT_ALLOWED'; END IF;
        BEGIN allowed:=platform.messaging_manual_send_allowed(ws);
        EXCEPTION WHEN SQLSTATE 'P2301' THEN RAISE EXCEPTION 'DEPENDENCY_UNAVAILABLE' USING ERRCODE='P2001'; END;
        IF allowed IS NOT TRUE THEN RETURN 'NOT_ALLOWED'; END IF;
        RETURN 'CURRENT';
      END $$""")
    op.execute(f"""CREATE FUNCTION platform.guard_turn_prepare(p_job uuid,p_claim uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE j platform.messaging_jobs%ROWTYPE; t app.conversation_turns%ROWTYPE; conv app.conversations%ROWTYPE;
        rec platform.conversation_control_receipts%ROWTYPE; prior platform.turn_guard_receipts%ROWTYPE;
        target_turn uuid; input jsonb; outcome text;
      BEGIN
        j:=platform.messaging_guard(p_job,p_claim);
        IF j.kind<>'PROCESS_TURN' OR j.step<>'GUARDED_TEXT' THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        target_turn:=j.turn_id;
        {LOCKS}
        {ALREADY}
        outcome:=CASE WHEN t.revision<>j.turn_revision THEN 'SUPERSEDED' ELSE
          platform.guard_require_current(j.workspace_id,t.id,rec.id,coalesce((j.turn_input->>'context_version')::bigint,conv.version)) END;
        PERFORM platform.messaging_guard(p_job,p_claim);
        IF outcome<>'CURRENT' THEN
          {TERMINAL_JOB}
          RETURN {PROGRESS_JSON};
        END IF;
        input:=j.turn_input;
        IF input IS NULL THEN
          input:=(platform.turn_snapshot(j.workspace_id,t.id)-'snapshot_digest') ||
            jsonb_build_object('conversation_id',conv.id,'client_id',conv.client_id,'business_id',conv.business_id,
              'activation_fence_seq',t.activation_fence_seq,'resume_receipt_id',rec.id,'consumer','CONTROLLED_GUARDS_V1');
          input:=input || jsonb_build_object('snapshot_digest',encode(sha256(convert_to(input::text,'UTF8')),'hex'));
          UPDATE platform.messaging_jobs SET turn_input=input WHERE id=j.id;
        END IF;
        RETURN input || jsonb_build_object('code','SNAPSHOT','job_id',j.id);
      END $$""")
    op.execute(f"""CREATE FUNCTION platform.guard_turn_replay(p_job uuid,p_claim uuid,p_digest text,p_text text) RETURNS jsonb
      LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE saved jsonb; fingerprint bytea; expected bytea; digest text;
      BEGIN
        -- One statement binds the winning token, terminal Job and immutable input.
        SELECT {RECEIPT_JSON},r.request_fingerprint,platform.guard_text_fingerprint(j.turn_input,p_text),r.snapshot_digest
          INTO saved,fingerprint,expected,digest FROM platform.turn_guard_receipts r JOIN platform.messaging_jobs j
          ON (j.workspace_id,j.id,j.connection_id,j.kind,j.turn_id,j.turn_revision,j.step)=
             (r.workspace_id,r.job_id,r.connection_id,r.kind,r.turn_id,r.turn_revision,r.step)
          WHERE j.id=p_job AND r.winning_claim_token=p_claim AND j.status='SUCCEEDED' AND j.turn_outcome=r.outcome;
        IF NOT FOUND THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
        IF digest IS DISTINCT FROM p_digest THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        IF fingerprint IS DISTINCT FROM expected THEN RAISE EXCEPTION 'IDEMPOTENCY_KEY_CONFLICT' USING ERRCODE='P2001'; END IF;
        RETURN saved;
      END $$""")
    op.execute(f"""CREATE FUNCTION platform.guard_turn_accept(p_job uuid,p_claim uuid,p_digest text,p_text text) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE j platform.messaging_jobs%ROWTYPE; t app.conversation_turns%ROWTYPE; conv app.conversations%ROWTYPE;
        rec platform.conversation_control_receipts%ROWTYPE; prior platform.turn_guard_receipts%ROWTYPE; r platform.turn_guard_receipts%ROWTYPE;
        target_turn uuid; input jsonb; outcome text; whitespace text; msg uuid; box uuid; send uuid; intent_context bigint;
      BEGIN
        PERFORM platform.turn_require_isolation();
        BEGIN RETURN platform.guard_turn_replay(p_job,p_claim,p_digest,p_text);
        EXCEPTION WHEN SQLSTATE 'P2001' THEN IF SQLERRM<>'STALE_CLAIM' THEN RAISE; END IF; END;
        BEGIN PERFORM platform.messaging_admit(p_job,p_claim);
        EXCEPTION WHEN SQLSTATE 'P2001' THEN
          IF SQLERRM<>'STALE_CLAIM' THEN RAISE; END IF;
          RETURN platform.guard_turn_replay(p_job,p_claim,p_digest,p_text);
        END;
        j:=platform.messaging_guard(p_job,p_claim);
        IF j.kind<>'PROCESS_TURN' OR j.step<>'GUARDED_TEXT' OR j.turn_input IS NULL OR
          j.turn_input->>'snapshot_digest' IS DISTINCT FROM p_digest THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        whitespace:=chr(9)||chr(10)||chr(11)||chr(12)||chr(13)||chr(28)||chr(29)||chr(30)||chr(31)||chr(32)||chr(133)||chr(160)||chr(5760)||chr(8192)||chr(8193)||chr(8194)||chr(8195)||chr(8196)||chr(8197)||chr(8198)||chr(8199)||chr(8200)||chr(8201)||chr(8202)||chr(8232)||chr(8233)||chr(8239)||chr(8287)||chr(12288);
        IF p_text IS NULL OR char_length(p_text) NOT BETWEEN 1 AND 4096 OR octet_length(p_text)>16384 OR btrim(p_text,whitespace)='' THEN
          RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        target_turn:=j.turn_id; input:=j.turn_input;
        {LOCKS}
        {ALREADY}
        outcome:=CASE WHEN t.revision<>j.turn_revision THEN 'SUPERSEDED' ELSE
          platform.guard_require_current(j.workspace_id,t.id,(input->>'resume_receipt_id')::uuid,(input->>'context_version')::bigint) END;
        PERFORM platform.messaging_guard(p_job,p_claim);
        IF outcome='CURRENT' THEN
          outcome:='ACCEPTED';
          INSERT INTO app.messages(workspace_id,conversation_id,connection_id,provider_chat_id,direction,content_type,text,occurred_at)
            VALUES(j.workspace_id,conv.id,t.connection_id,conv.provider_chat_id,'OUTBOUND','TEXT',p_text,clock_timestamp()) RETURNING id INTO msg;
          SELECT version INTO STRICT intent_context FROM app.conversations WHERE workspace_id=j.workspace_id AND id=conv.id;
          IF intent_context::numeric<>(input->>'context_version')::numeric+1 THEN
            RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
          INSERT INTO app.outbox_events(workspace_id,connection_id,message_id,kind)
            VALUES(j.workspace_id,t.connection_id,msg,'SEND_GUARDED_TEXT') RETURNING id INTO box;
          INSERT INTO platform.messaging_jobs(workspace_id,connection_id,kind,outbox_id,correlation_id)
            VALUES(j.workspace_id,t.connection_id,'SEND_GUARDED_TEXT',box,j.correlation_id) RETURNING id INTO send;
        END IF;
        INSERT INTO platform.turn_guard_receipts(workspace_id,job_id,winning_claim_token,connection_id,conversation_id,client_id,
          turn_id,turn_revision,resume_receipt_id,input_control_generation,activation_fence_seq,input_context_version,
          snapshot_digest,request_fingerprint,result_text,outcome,intent_context_version,message_id,outbox_id,send_job_id)
          VALUES(j.workspace_id,j.id,p_claim,j.connection_id,(input->>'conversation_id')::uuid,(input->>'client_id')::uuid,
            j.turn_id,j.turn_revision,(input->>'resume_receipt_id')::uuid,(input->>'control_generation')::bigint,
            (input->>'activation_fence_seq')::bigint,(input->>'context_version')::bigint,p_digest,
            platform.guard_text_fingerprint(input,p_text),p_text,outcome,intent_context,msg,box,send) RETURNING * INTO r;
        {TERMINAL_JOB}
        RETURN {RECEIPT_JSON};
      END $$""")
    op.execute(f"""CREATE FUNCTION platform.guard_send_begin(p_job uuid,p_claim uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE j platform.messaging_jobs%ROWTYPE; t app.conversation_turns%ROWTYPE; conv app.conversations%ROWTYPE;
        rec platform.conversation_control_receipts%ROWTYPE; r platform.turn_guard_receipts%ROWTYPE;
        box app.outbox_events%ROWTYPE; msg app.messages%ROWTYPE; conn app.channel_connections%ROWTYPE;
        target_turn uuid; outcome text; attempt uuid;
      BEGIN
        j:=platform.messaging_guard(p_job,p_claim);
        IF j.kind<>'SEND_GUARDED_TEXT' THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        SELECT * INTO STRICT box FROM app.outbox_events WHERE workspace_id=j.workspace_id AND id=j.outbox_id FOR UPDATE;
        IF box.status<>'PENDING' OR box.kind<>'SEND_GUARDED_TEXT' THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
        SELECT * INTO STRICT r FROM platform.turn_guard_receipts g WHERE g.workspace_id=j.workspace_id AND g.send_job_id=j.id
          AND g.outbox_id=box.id AND g.message_id=box.message_id AND g.outcome='ACCEPTED';
        target_turn:=r.turn_id;
        {LOCKS}
        outcome:=CASE WHEN t.revision<>r.turn_revision THEN 'SUPERSEDED' ELSE
          platform.guard_require_current(j.workspace_id,t.id,r.resume_receipt_id,r.intent_context_version) END;
        PERFORM platform.messaging_guard(p_job,p_claim);
        IF outcome<>'CURRENT' THEN
          UPDATE app.outbox_events SET status='FAILED',error_code='NOT_ALLOWED',completed_at=clock_timestamp(),version=version+1
            WHERE workspace_id=j.workspace_id AND id=box.id;
          UPDATE platform.messaging_jobs SET status='DEAD',error_code='NOT_ALLOWED',guard_rejection=outcome,
            claim_token=NULL,lease_until=NULL,worker_id=NULL,completed_at=clock_timestamp(),version=version+1 WHERE id=j.id;
          RETURN jsonb_build_object('code','NOT_ALLOWED','status','FAILED');
        END IF;
        SELECT * INTO STRICT msg FROM app.messages WHERE workspace_id=j.workspace_id AND id=box.message_id;
        SELECT * INTO STRICT conn FROM app.channel_connections WHERE workspace_id=j.workspace_id AND id=j.connection_id;
        IF (msg.conversation_id,msg.connection_id,msg.direction,msg.content_type,msg.text) IS DISTINCT FROM
          (r.conversation_id,r.connection_id,'OUTBOUND'::text,'TEXT'::text,r.result_text) THEN
          RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        attempt:=gen_random_uuid();
        UPDATE app.outbox_events SET status='DISPATCHING',attempt_id=attempt,error_code=NULL,version=version+1
          WHERE workspace_id=j.workspace_id AND id=box.id;
        RETURN jsonb_build_object('code','PERMITTED','job_id',j.id,'claim_token',p_claim,'attempt_id',attempt,
          'workspace_id',j.workspace_id,'connection_id',j.connection_id,'provider',conn.provider,
          'bot_identity',conn.bot_identity,'external_connection_id',conn.external_connection_id,'chat_id',msg.provider_chat_id,'text',msg.text);
      END $$""")


def _extend() -> None:
    _replace(
        "conversation_control_execute",
        (
            "activation_fence_seq,request_fingerprint,audit_event_id,accepted_at,result)",
            "activation_fence_seq,request_fingerprint,audit_event_id,accepted_at,result,guard_profile)",
        ),
        (
            "audit,moment,result);",
            """audit,moment,result,CASE WHEN p_operation='RESUME' AND current_database() IN ('asm_local','asm_test')
              AND EXISTS(SELECT 1 FROM app.channel_connections WHERE workspace_id=ws AND id=conv.connection_id AND provider='CONTROLLED')
              THEN 'CONTROLLED_GUARDS_V1' END);""",
        ),
    )
    _replace(
        "conversation_control_read",
        ("AND o.status='DISPATCHING'", "AND o.kind='SEND_MANUAL_TEXT' AND o.status='DISPATCHING'"),
        ("AND o.status='UNKNOWN'", "AND o.kind='SEND_MANUAL_TEXT' AND o.status='UNKNOWN'"),
    )
    _replace(
        "turn_enqueue",
        (
            "      END $$",
            """        IF t.state='READY' AND current_database() IN ('asm_local','asm_test')
          AND platform.conversation_turn_activation_matches(ws,t.id) IS TRUE
          AND EXISTS(SELECT 1 FROM app.channel_connections WHERE workspace_id=ws AND id=t.connection_id AND provider='CONTROLLED')
          AND EXISTS(SELECT 1 FROM platform.conversation_control_receipts WHERE workspace_id=ws AND conversation_id=t.conversation_id
            AND accepted_generation=t.control_generation AND activation_fence_seq=t.activation_fence_seq
            AND guard_profile='CONTROLLED_GUARDS_V1' AND operation='RESUME') THEN
          INSERT INTO platform.messaging_jobs(workspace_id,connection_id,kind,turn_id,turn_revision,step,correlation_id)
            VALUES(ws,t.connection_id,'PROCESS_TURN',t.id,t.revision,'GUARDED_TEXT',corr)
            ON CONFLICT(workspace_id,turn_id,turn_revision,step) DO NOTHING;
        END IF;
      END $$""",
        ),
    )
    _replace(
        "turn_execute",
        (
            "IF j.kind<>'PROCESS_TURN' THEN",
            "IF j.kind<>'PROCESS_TURN' OR j.step NOT IN ('GROUP','MEDIA','TEST_CONSUME') THEN",
        ),
    )
    for name in (
        "turn_preflight",
        "messaging_reschedule",
        "messaging_retry",
        "messaging_recover_expired",
    ):
        changes = [
            ("j.kind='SEND_MANUAL_TEXT'", "j.kind IN ('SEND_MANUAL_TEXT','SEND_GUARDED_TEXT')")
        ]
        if name == "messaging_reschedule":
            changes.append(
                (
                    "ELSIF j.kind='PROCESS_TURN' AND NOT retry THEN",
                    "ELSIF j.kind='PROCESS_TURN' AND j.step<>'GUARDED_TEXT' AND NOT retry THEN",
                )
            )
        _replace(name, *changes)
    _replace(
        "messaging_finish_send",
        ("j.kind<>'SEND_MANUAL_TEXT'", "j.kind NOT IN ('SEND_MANUAL_TEXT','SEND_GUARDED_TEXT')"),
    )


def upgrade() -> None:
    _schema()
    _capabilities()
    _extend()
    for signature in (*PUBLIC_FUNCTIONS, *PRIVATE_FUNCTIONS):
        op.execute(f"ALTER FUNCTION {signature} OWNER TO asm_migrator")
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC,asm_runtime")
    for signature in PUBLIC_FUNCTIONS:
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO asm_runtime")


def downgrade() -> None:
    # Lock+refusal are the first operations. Terminal usage is still usage.
    op.execute("""LOCK TABLE platform.turn_guard_receipts,platform.conversation_control_receipts,
      platform.messaging_jobs,app.outbox_events IN ACCESS EXCLUSIVE MODE""")
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM platform.turn_guard_receipts) OR
        EXISTS(SELECT 1 FROM platform.conversation_control_receipts WHERE guard_profile IS NOT NULL) OR
        EXISTS(SELECT 1 FROM platform.messaging_jobs WHERE kind='SEND_GUARDED_TEXT' OR step='GUARDED_TEXT' OR guard_rejection IS NOT NULL) OR
        EXISTS(SELECT 1 FROM app.outbox_events WHERE kind='SEND_GUARDED_TEXT') THEN
        RAISE EXCEPTION 'GUARDS data prevents downgrade' USING ERRCODE='55000'; END IF;
      END $$""")
    for body in ORIGINAL.values():
        op.execute(body)
    op.execute("DROP TABLE platform.turn_guard_receipts")
    for signature in (
        *PUBLIC_FUNCTIONS[:2],
        PUBLIC_FUNCTIONS[3],
        PUBLIC_FUNCTIONS[2],
        *PRIVATE_FUNCTIONS,
    ):
        op.execute(f"DROP FUNCTION {signature}")
    op.execute("""ALTER TABLE platform.messaging_jobs DROP CONSTRAINT messaging_send_kind_fkey,
      DROP CONSTRAINT messaging_guard_send_key,DROP CONSTRAINT messaging_guard_rejection_check,DROP COLUMN guard_rejection""")
    op.execute("""ALTER TABLE app.outbox_events DROP CONSTRAINT outbox_guard_kind_key,DROP CONSTRAINT outbox_events_kind_check,
      ADD CONSTRAINT outbox_events_kind_check CHECK(kind='SEND_MANUAL_TEXT')""")
    for name, old in OLD_CHECKS.items():
        op.execute(
            f"ALTER TABLE platform.messaging_jobs DROP CONSTRAINT {name},ADD CONSTRAINT {name} CHECK({old})"
        )
    op.execute("""ALTER TABLE platform.conversation_control_receipts DROP CONSTRAINT control_guard_reference_key,
      DROP CONSTRAINT control_guard_profile_check,DROP COLUMN guard_profile""")
