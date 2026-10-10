"""M3.1 durable conversation turns and bounded worker capabilities.

0001--0007 are immutable. Exact 0007 definitions below restore clean downgrades;
all PostgreSQL authority and writes remain in narrow migration-owned functions.
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

# Exact accepted 0007 capability bodies, including inherited 0005/0006 functions.
ORIGINAL = {
    "messaging_job_json": r"""CREATE OR REPLACE FUNCTION platform.messaging_job_json(j platform.messaging_jobs) RETURNS jsonb
      LANGUAGE sql STABLE SET search_path=pg_catalog,pg_temp AS $$ SELECT jsonb_build_object(
      'job_id',j.id,'kind',j.kind,'workspace_id',j.workspace_id,'connection_id',j.connection_id,
      'inbox_id',j.inbox_id,'outbox_id',j.outbox_id,'file_id',j.file_id,'claim_token',j.claim_token,'lease_until',j.lease_until,
      'correlation_id',j.correlation_id,'attempt_count',j.attempt_count) $$""",
    "messaging_guard": r"""CREATE OR REPLACE FUNCTION platform.messaging_guard(p_job uuid,p_claim uuid) RETURNS platform.messaging_jobs
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE j platform.messaging_jobs%ROWTYPE;
      BEGIN
        SELECT * INTO j FROM platform.messaging_jobs WHERE id=p_job FOR UPDATE;
        IF NOT FOUND OR j.status<>'RUNNING' OR j.claim_token IS DISTINCT FROM p_claim OR j.lease_until<=clock_timestamp() OR
           current_setting('asm.actor_kind',true) IS DISTINCT FROM 'worker_job' OR
           coalesce(current_setting('asm.actor_id',true),'')<>'' OR
           current_setting('asm.job_id',true) IS DISTINCT FROM j.id::text OR
           current_setting('asm.claim_token',true) IS DISTINCT FROM p_claim::text OR
           current_setting('asm.workspace_id',true) IS DISTINCT FROM j.workspace_id::text OR
           current_setting('asm.connection_id',true) IS DISTINCT FROM j.connection_id::text OR
           current_setting('asm.correlation_id',true) IS DISTINCT FROM j.correlation_id::text OR
           pg_current_xact_id_if_assigned() IS NULL OR
           current_setting('asm.context_xid',true) IS DISTINCT FROM pg_current_xact_id_if_assigned()::text THEN
          RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
        RETURN j;
      END $$""",
    "messaging_ingest": r"""CREATE OR REPLACE FUNCTION platform.messaging_ingest(p_provider text,p_bot text,p_event jsonb,p_correlation uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE e jsonb; route platform.channel_routes%ROWTYPE; c app.channel_connections%ROWTYPE;
        inbox platform.inbox_events%ROWTYPE; fingerprint bytea; job uuid; fresh boolean;
      BEGIN
        IF p_provider IS DISTINCT FROM 'CONTROLLED' THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        e:=platform.messaging_validate_event(p_event);
        IF p_correlation IS NULL OR p_provider IS DISTINCT FROM e->>'provider' OR p_bot IS DISTINCT FROM e->>'bot_identity' THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        SELECT * INTO route FROM platform.channel_routes WHERE provider=p_provider AND bot_identity=p_bot AND route_key=e->>'external_connection_id';
        IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P2001'; END IF;
        SELECT * INTO c FROM app.channel_connections WHERE workspace_id=route.workspace_id AND id=route.connection_id FOR SHARE;
        fingerprint:=platform.messaging_fingerprint(e,false);
        SELECT * INTO inbox FROM platform.inbox_events WHERE provider=p_provider AND bot_identity=p_bot AND event_id=e->>'event_id';
        IF FOUND THEN
          IF inbox.event_fingerprint<>fingerprint THEN RAISE EXCEPTION 'EVENT_ID_CONFLICT' USING ERRCODE='P2001'; END IF;
          fresh:=false;
        ELSE
          IF c.status<>'ACTIVE' THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
          INSERT INTO platform.inbox_events(workspace_id,connection_id,provider,bot_identity,external_connection_id,event_id,normalized_event,event_fingerprint,correlation_id)
          VALUES(route.workspace_id,route.connection_id,p_provider,p_bot,e->>'external_connection_id',e->>'event_id',e,fingerprint,p_correlation)
          ON CONFLICT(provider,bot_identity,event_id) DO NOTHING RETURNING * INTO inbox;
          fresh:=FOUND;
          IF NOT fresh THEN
            SELECT * INTO STRICT inbox FROM platform.inbox_events WHERE provider=p_provider AND bot_identity=p_bot AND event_id=e->>'event_id';
            IF inbox.event_fingerprint<>fingerprint THEN RAISE EXCEPTION 'EVENT_ID_CONFLICT' USING ERRCODE='P2001'; END IF;
          ELSE
            INSERT INTO platform.messaging_jobs(workspace_id,connection_id,kind,inbox_id,correlation_id)
            VALUES(inbox.workspace_id,inbox.connection_id,'PROCESS_INBOX',inbox.id,inbox.correlation_id);
          END IF;
        END IF;
        SELECT id INTO STRICT job FROM platform.messaging_jobs WHERE workspace_id=inbox.workspace_id AND inbox_id=inbox.id;
        RETURN jsonb_build_object('code',CASE WHEN fresh THEN 'ACCEPTED' ELSE 'DUPLICATE' END,'workspace_id',inbox.workspace_id,'inbox_id',inbox.id,'job_id',job,'accepted_at',inbox.received_at);
      END $$""",
    "messaging_claim": r"""CREATE OR REPLACE FUNCTION platform.messaging_claim(p_worker text) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE j platform.messaging_jobs%ROWTYPE; scanned integer:=0;
      BEGIN
        IF NOT platform.messaging_valid_id(p_worker,128,512) OR coalesce(current_setting('asm.actor_kind',true),'')<>'' THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        LOOP
          SELECT * INTO j FROM platform.messaging_jobs WHERE status='READY' AND available_at<=clock_timestamp() ORDER BY available_at,id FOR UPDATE SKIP LOCKED LIMIT 1;
          IF NOT FOUND THEN RETURN NULL; END IF;
          IF j.attempt_count>=5 OR (j.first_started_at IS NOT NULL AND j.first_started_at+interval '15 minutes'<=clock_timestamp()) THEN
            PERFORM platform.messaging_reschedule(j.id,'RETRY_EXHAUSTED',false);
            scanned:=scanned+1; IF scanned>=100 THEN RETURN NULL; END IF; CONTINUE;
          END IF;
          UPDATE platform.messaging_jobs SET status='RUNNING',claim_token=gen_random_uuid(),lease_until=clock_timestamp()+interval '30 seconds',worker_id=p_worker,
            attempt_count=attempt_count+1,first_started_at=coalesce(first_started_at,clock_timestamp()),
            last_attempt_id=NULL,last_claim_token=NULL,last_outcome=NULL,last_provider_message_id=NULL,last_error_code=NULL,last_retry_after_seconds=NULL,last_retry_due=NULL,telegram_probe_claim=NULL,telegram_probe_generation=NULL,telegram_probe_version=NULL,version=version+1
            WHERE id=j.id RETURNING * INTO j;
          RETURN platform.messaging_job_json(j);
        END LOOP;
      END $$""",
    "messaging_admit": r"""CREATE OR REPLACE FUNCTION platform.messaging_admit(p_job uuid,p_claim uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE j platform.messaging_jobs%ROWTYPE;
      BEGIN
        IF coalesce(current_setting('asm.actor_kind',true),'')<>'' THEN RAISE EXCEPTION 'ACCESS_DENIED' USING ERRCODE='P2001'; END IF;
        SELECT * INTO j FROM platform.messaging_jobs WHERE id=p_job FOR UPDATE;
        IF NOT FOUND OR j.status<>'RUNNING' OR j.claim_token IS DISTINCT FROM p_claim OR j.lease_until<=clock_timestamp() THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
        PERFORM set_config('asm.actor_kind','worker_job',true),set_config('asm.actor_id','',true),
          set_config('asm.workspace_id',j.workspace_id::text,true),set_config('asm.connection_id',j.connection_id::text,true),
          set_config('asm.job_id',j.id::text,true),set_config('asm.claim_token',j.claim_token::text,true),
          set_config('asm.correlation_id',j.correlation_id::text,true),set_config('asm.context_xid',pg_current_xact_id()::text,true);
        RETURN platform.messaging_job_json(j);
      END $$""",
    "messaging_process_inbox": r"""CREATE OR REPLACE FUNCTION platform.messaging_process_inbox(p_job uuid,p_claim uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE j platform.messaging_jobs%ROWTYPE; inbox platform.inbox_events%ROWTYPE; e jsonb;
        c app.channel_connections%ROWTYPE; identity app.client_identities%ROWTYPE; conv app.conversations%ROWTYPE;
        msg app.messages%ROWTYPE; client uuid; code text; state text; fingerprint bytea;
      BEGIN
        j:=platform.messaging_guard(p_job,p_claim);
        IF j.kind<>'PROCESS_INBOX' THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        SELECT * INTO STRICT inbox FROM platform.inbox_events WHERE workspace_id=j.workspace_id AND id=j.inbox_id FOR UPDATE;
        IF inbox.status<>'PENDING' THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
        e:=inbox.normalized_event;
        IF e->>'kind'<>'CLIENT_MESSAGE' THEN
          state:='IGNORED';code:='IGNORED_'||(e->>'kind');
        ELSE
          -- Serialize writers sharing a connection, then sender identity across connections.
          SELECT * INTO STRICT c FROM app.channel_connections WHERE workspace_id=j.workspace_id AND id=j.connection_id FOR UPDATE;
          fingerprint:=platform.messaging_fingerprint(e,true);
          SELECT * INTO msg FROM app.messages WHERE workspace_id=j.workspace_id AND connection_id=j.connection_id AND provider_chat_id=e->>'chat_id' AND provider_message_id=e->>'message_id';
          IF FOUND THEN
            IF msg.projection_fingerprint=fingerprint THEN state:='PROCESSED';code:='DUPLICATE';
            ELSE state:='FAILED';code:='MESSAGE_ID_CONFLICT';msg.id:=NULL; END IF;
          ELSE
            SELECT * INTO conv FROM app.conversations WHERE workspace_id=j.workspace_id AND connection_id=j.connection_id AND provider_chat_id=e->>'chat_id';
            IF FOUND AND NOT EXISTS(SELECT 1 FROM app.client_identities WHERE workspace_id=j.workspace_id AND id=conv.identity_id AND provider=e->>'provider' AND external_user_id=e->>'sender_id') THEN
              state:='FAILED';code:='CONVERSATION_IDENTITY_CONFLICT';
            ELSE
              -- Transaction advisory hash locks only serialize identity creation, never grant authority.
              PERFORM pg_advisory_xact_lock(hashtextextended(j.workspace_id::text||':'||(e->>'provider')||':'||(e->>'sender_id'),2005));
              SELECT * INTO identity FROM app.client_identities WHERE workspace_id=j.workspace_id AND provider=e->>'provider' AND external_user_id=e->>'sender_id';
              IF NOT FOUND THEN
                INSERT INTO app.clients(workspace_id) VALUES(j.workspace_id) RETURNING id INTO client;
                INSERT INTO app.client_identities(workspace_id,client_id,provider,external_user_id) VALUES(j.workspace_id,client,e->>'provider',e->>'sender_id') RETURNING * INTO identity;
              END IF;
              IF conv.id IS NULL THEN
                INSERT INTO app.conversations(workspace_id,connection_id,business_id,client_id,identity_id,provider_chat_id)
                VALUES(j.workspace_id,c.id,c.business_id,identity.client_id,identity.id,e->>'chat_id') RETURNING * INTO conv;
              END IF;
              INSERT INTO app.messages(workspace_id,conversation_id,connection_id,provider_chat_id,provider_message_id,direction,content_type,text,image_file_id,media_group_id,occurred_at,projection_fingerprint)
              VALUES(j.workspace_id,conv.id,j.connection_id,e->>'chat_id',e->>'message_id','INBOUND',CASE WHEN e->>'image_file_id' IS NULL THEN 'TEXT' ELSE 'IMAGE_REFERENCE' END,e->>'text',e->>'image_file_id',e->>'media_group_id',(e->>'occurred_at')::timestamptz,fingerprint) RETURNING * INTO msg;
              state:='PROCESSED';code:='PROCESSED';
            END IF;
          END IF;
        END IF;
        IF code='PROCESSED' AND e->>'provider'='TELEGRAM' THEN
          UPDATE app.conversations SET last_client_inbound_at=greatest(last_client_inbound_at,least(msg.occurred_at,inbox.received_at)),version=version+1
            WHERE workspace_id=j.workspace_id AND id=msg.conversation_id;
        END IF;
        IF state='PROCESSED' AND msg.content_type='IMAGE_REFERENCE' THEN
          PERFORM platform.files_plan(j.workspace_id,msg.id,j.correlation_id);
        END IF;
        PERFORM platform.messaging_guard(p_job,p_claim);
        UPDATE platform.inbox_events SET status=state,result_code=code,message_id=msg.id,completed_at=clock_timestamp(),version=version+1 WHERE workspace_id=j.workspace_id AND id=inbox.id;
        UPDATE platform.messaging_jobs SET status=CASE WHEN state='FAILED' THEN 'DEAD' ELSE 'SUCCEEDED' END,error_code=CASE WHEN state='FAILED' THEN code END,
          claim_token=NULL,lease_until=NULL,worker_id=NULL,completed_at=clock_timestamp(),version=version+1 WHERE id=j.id;
        RETURN jsonb_build_object('code',code,'inbox_id',inbox.id,'message_id',msg.id,'status',state);
      END $$""",
    "messaging_recover_expired": r"""CREATE OR REPLACE FUNCTION platform.messaging_recover_expired(p_limit integer) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE j platform.messaging_jobs%ROWTYPE; state text; recovered integer:=0;
      BEGIN
        IF p_limit IS NULL OR p_limit<1 OR p_limit>1000 OR coalesce(current_setting('asm.actor_kind',true),'')<>'' THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        FOR j IN SELECT * FROM platform.messaging_jobs WHERE status='RUNNING' AND lease_until<=clock_timestamp() ORDER BY lease_until,id FOR UPDATE SKIP LOCKED LIMIT p_limit LOOP
          state:=NULL;
          IF j.kind='SEND_MANUAL_TEXT' THEN SELECT status INTO state FROM app.outbox_events WHERE workspace_id=j.workspace_id AND id=j.outbox_id FOR UPDATE; END IF;
          IF state='DISPATCHING' THEN
            UPDATE app.outbox_events SET status='UNKNOWN',error_code='UNKNOWN_EXTERNAL_RESULT',completed_at=clock_timestamp(),version=version+1 WHERE workspace_id=j.workspace_id AND id=j.outbox_id;
            UPDATE platform.messaging_jobs SET status='DEAD',error_code='UNKNOWN_EXTERNAL_RESULT',claim_token=NULL,lease_until=NULL,worker_id=NULL,completed_at=clock_timestamp(),version=version+1 WHERE id=j.id;
          ELSE
            PERFORM platform.messaging_reschedule(j.id,'DEPENDENCY_TIMEOUT',true);
          END IF;
          recovered:=recovered+1;
        END LOOP;
        RETURN jsonb_build_object('recovered',recovered);
      END $$""",
    "telegram_ingest": r"""CREATE OR REPLACE FUNCTION platform.telegram_ingest(p_bot text,p_projection jsonb,p_correlation uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE p jsonb; e jsonb; digest bytea; rec platform.telegram_update_receipts%ROWTYPE;
        route platform.channel_routes%ROWTYPE; s platform.telegram_connection_state%ROWTYPE;
        result text; inbox uuid; job uuid; fresh boolean:=true; received timestamptz:=clock_timestamp();
      BEGIN
        p:=platform.telegram_validate_projection(p_bot,p_projection);
        IF p_correlation IS NULL THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        digest:=platform.telegram_fingerprint(p_bot,p);
        PERFORM pg_advisory_xact_lock(hashtextextended(p_bot||':'||(p->>'update_id'),2008));
        SELECT * INTO rec FROM platform.telegram_update_receipts WHERE bot_identity=p_bot AND update_id=p->>'update_id';
        IF FOUND THEN
          IF rec.fingerprint<>digest THEN RAISE EXCEPTION 'EVENT_ID_CONFLICT' USING ERRCODE='P2001'; END IF;
          fresh:=false;
        ELSE
          IF p->>'external_connection_id' IS NULL THEN
            result:='IGNORED_UNSUPPORTED';
          ELSE
            SELECT * INTO route FROM platform.channel_routes WHERE provider='TELEGRAM' AND bot_identity=p_bot AND route_key=p->>'external_connection_id';
            IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P2001'; END IF;
            SELECT * INTO STRICT s FROM platform.telegram_connection_state WHERE workspace_id=route.workspace_id AND connection_id=route.connection_id;
            IF p->>'kind'='BUSINESS_CONNECTION' THEN
              IF p->>'owner_user_id' IS DISTINCT FROM s.owner_user_id THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
              UPDATE platform.telegram_connection_state SET generation=generation+1,observation_version=observation_version+1
                WHERE workspace_id=s.workspace_id AND connection_id=s.connection_id;
              result:='LIFECYCLE_INVALIDATED';
            ELSIF p->>'kind'='DELETED_BUSINESS_MESSAGES' THEN result:='IGNORED_MESSAGE_DELETED';
            ELSIF p->>'kind'='EDITED_BUSINESS_MESSAGE' THEN result:='IGNORED_MESSAGE_EDITED';
            ELSIF p->>'kind'='UNSUPPORTED' THEN result:='IGNORED_UNSUPPORTED';
            ELSE
              e:=p->'event';
              IF p->>'sender_business_bot_id' IS NOT NULL THEN result:='IGNORED_ECHO';
              ELSIF e->>'sender_id'=s.owner_user_id THEN result:='IGNORED_NATIVE_OWNER_MESSAGE';
              ELSIF e->>'sender_id'=s.bot_identity OR e->>'kind'<>'CLIENT_MESSAGE' THEN result:='IGNORED_UNSUPPORTED';
              ELSE
                INSERT INTO platform.inbox_events(workspace_id,connection_id,provider,bot_identity,external_connection_id,event_id,normalized_event,event_fingerprint,correlation_id,received_at)
                  VALUES(route.workspace_id,route.connection_id,'TELEGRAM',p_bot,p->>'external_connection_id',p->>'update_id',e,platform.messaging_fingerprint(e,false),p_correlation,received) RETURNING id INTO inbox;
                INSERT INTO platform.messaging_jobs(workspace_id,connection_id,kind,inbox_id,correlation_id) VALUES(route.workspace_id,route.connection_id,'PROCESS_INBOX',inbox,p_correlation) RETURNING id INTO job;
                result:='QUEUED';
              END IF;
            END IF;
          END IF;
          INSERT INTO platform.telegram_update_receipts(bot_identity,update_id,fingerprint,kind,result_code,workspace_id,connection_id,inbox_id,received_at)
            VALUES(p_bot,p->>'update_id',digest,p->>'kind',result,route.workspace_id,route.connection_id,inbox,received) RETURNING * INTO rec;
        END IF;
        IF rec.inbox_id IS NOT NULL THEN SELECT id INTO STRICT job FROM platform.messaging_jobs WHERE workspace_id=rec.workspace_id AND inbox_id=rec.inbox_id; END IF;
        RETURN jsonb_build_object('code',CASE WHEN fresh THEN 'ACCEPTED' ELSE 'DUPLICATE' END,'receipt_id',rec.id,
          'workspace_id',rec.workspace_id,'connection_id',rec.connection_id,'inbox_id',rec.inbox_id,'job_id',job,'accepted_at',rec.received_at,'result_code',rec.result_code);
      END $$""",
    "messaging_reschedule": r"""CREATE OR REPLACE FUNCTION platform.messaging_reschedule(p_job uuid,p_error text,p_retry boolean,p_delay integer) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE j platform.messaging_jobs%ROWTYPE; retry boolean; final_error text; delivery text; due timestamptz;
      BEGIN
        SELECT * INTO STRICT j FROM platform.messaging_jobs WHERE id=p_job FOR UPDATE;
        IF p_delay IS NOT NULL AND (p_delay NOT BETWEEN 1 AND 86400 OR p_retry IS NOT TRUE) THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        due:=clock_timestamp()+make_interval(secs=>random()*least(60.0,power(2.0,greatest(j.attempt_count-1,0))));
        IF p_delay IS NOT NULL THEN due:=greatest(due,clock_timestamp()+make_interval(secs=>p_delay)); END IF;
        retry:=p_retry AND j.attempt_count<5 AND clock_timestamp()<j.first_started_at+interval '15 minutes' AND (p_delay IS NULL OR due<j.first_started_at+interval '15 minutes');
        final_error:=CASE WHEN p_retry AND NOT retry THEN 'RETRY_EXHAUSTED' ELSE p_error END;
        UPDATE platform.messaging_jobs SET status=CASE WHEN retry THEN 'READY' ELSE 'DEAD' END,
          claim_token=NULL,lease_until=NULL,worker_id=NULL,error_code=final_error,
          available_at=due,
          completed_at=CASE WHEN retry THEN NULL ELSE clock_timestamp() END,version=version+1 WHERE id=j.id;
        IF j.kind='FETCH_IMAGE' THEN
          -- A winner is terminal; ordinary retry admission can never reach it.
          UPDATE platform.file_object_uploads SET status='ABANDONED',next_check_at=clock_timestamp(),version=version+1
            WHERE workspace_id=j.workspace_id AND file_id=j.file_id AND status='PREPARED';
          IF NOT retry THEN
            UPDATE app.file_objects SET status='FAILED',error_code=final_error,completed_at=clock_timestamp(),version=version+1
              WHERE workspace_id=j.workspace_id AND id=j.file_id AND status='PENDING';
          END IF;
        ELSIF j.kind='PROCESS_INBOX' AND NOT retry THEN
          UPDATE platform.inbox_events SET status='FAILED',result_code=final_error,completed_at=clock_timestamp(),version=version+1 WHERE workspace_id=j.workspace_id AND id=j.inbox_id;
        ELSIF j.kind='SEND_MANUAL_TEXT' THEN
          delivery:=CASE WHEN retry THEN 'PENDING' ELSE 'FAILED' END;
          UPDATE app.outbox_events SET status=delivery,error_code=final_error,completed_at=CASE WHEN retry THEN NULL ELSE clock_timestamp() END,version=version+1 WHERE workspace_id=j.workspace_id AND id=j.outbox_id;
        END IF;
        RETURN jsonb_build_object('code',CASE WHEN retry THEN 'RETRY_SCHEDULED' ELSE final_error END,'status',coalesce(delivery,CASE WHEN retry THEN 'READY' ELSE 'DEAD' END),'job_id',j.id,'outbox_id',j.outbox_id);
      END $$""",
}

# Exact inherited 0006 body also restores the added terminal prelock hook.
ORIGINAL[
    "files_finish_fetch"
] = r"""CREATE OR REPLACE FUNCTION platform.files_finish_fetch(p_job uuid,p_claim uuid,p_intent uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE j platform.messaging_jobs%ROWTYPE; f app.file_objects%ROWTYPE; u platform.file_object_uploads%ROWTYPE; result_code text;
      BEGIN
        IF coalesce(current_setting('asm.actor_kind',true),'')<>'' THEN RAISE EXCEPTION 'ACCESS_DENIED' USING ERRCODE='P2001'; END IF;
        -- Consistent lock order with reschedule/prepare avoids job/file/intent deadlocks.
        SELECT * INTO j FROM platform.messaging_jobs WHERE id=p_job FOR UPDATE;
        IF NOT FOUND OR j.kind<>'FETCH_IMAGE' THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
        SELECT * INTO STRICT f FROM app.file_objects WHERE workspace_id=j.workspace_id AND id=j.file_id FOR UPDATE;
        SELECT * INTO u FROM platform.file_object_uploads WHERE workspace_id=j.workspace_id AND id=p_intent AND job_id=j.id AND file_id=f.id AND claim_token=p_claim FOR UPDATE;
        IF NOT FOUND THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
        IF f.status='READY' AND f.winner_intent_id=u.id AND u.status='WINNER' AND j.status='SUCCEEDED' THEN
          result_code:='ALREADY_FINALIZED';
        ELSE
          PERFORM platform.messaging_admit(p_job,p_claim);
          PERFORM platform.messaging_guard(p_job,p_claim);
          IF f.status<>'PENDING' OR u.status<>'PREPARED' THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
          UPDATE platform.file_object_uploads SET status='WINNER',version=version+1 WHERE workspace_id=j.workspace_id AND id=u.id;
          UPDATE app.file_objects SET status='READY',winner_intent_id=u.id,storage_key=u.storage_key,mime_type=u.mime_type,
            size_bytes=u.size_bytes,sha256=u.sha256,width=u.width,height=u.height,completed_at=clock_timestamp(),version=version+1
            WHERE workspace_id=j.workspace_id AND id=f.id;
          UPDATE platform.messaging_jobs SET status='SUCCEEDED',error_code=NULL,claim_token=NULL,lease_until=NULL,worker_id=NULL,
            completed_at=clock_timestamp(),version=version+1 WHERE id=j.id;
          result_code:='FINALIZED';
        END IF;
        RETURN jsonb_build_object('code',result_code,'status','READY','job_id',j.id,'file_id',f.id,'intent_id',u.id);
      END $$"""

ORIGINAL[
    "messaging_finish_send"
] = r"""CREATE OR REPLACE FUNCTION platform.messaging_finish_send(p_job uuid,p_claim uuid,p_attempt uuid,p_outcome text,p_provider_message text,p_error text,p_retry_after_seconds integer) RETURNS jsonb
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
      END $$"""

TABLES = (
    "app.conversation_turns",
    "app.conversation_turn_messages",
    "platform.turn_consumer_receipts",
)
PUBLIC_FUNCTIONS = (
    "platform.messaging_claim(text,timestamp with time zone,timestamp with time zone,uuid)",
    "platform.messaging_recover_expired(timestamp with time zone,timestamp with time zone,uuid)",
    "platform.turn_execute(uuid,uuid)",
    "platform.turn_consumer_finalize(uuid,uuid,jsonb)",
    "platform.turn_consumer_replay(uuid,uuid)",
)
PRIVATE_FUNCTIONS = (
    "platform.turn_require_isolation()",
    "platform.turn_ingress()",
    "platform.turn_immutable()",
    "platform.turn_member_check()",
    "platform.turn_members_consistent()",
    "platform.turn_enqueue(uuid,uuid,uuid)",
    "platform.turn_seal(uuid,uuid,timestamp with time zone,uuid,boolean)",
    "platform.turn_group_message(uuid,uuid,uuid)",
    "platform.turn_material()",
    "platform.turn_preflight(platform.messaging_jobs,boolean,boolean)",
    "platform.turn_supersede(platform.messaging_jobs)",
    "platform.turn_snapshot(uuid,uuid)",
)


def _replace(name: str, *changes: tuple[str, str]) -> None:
    sql = ORIGINAL[name]
    for before, after in changes:
        assert before in sql, (name, before)
        sql = sql.replace(before, after)
    op.execute(sql)


def _schema() -> None:
    # Nullable without a volatile DEFAULT: pre-cutover rows stay NULL forever.
    op.execute("LOCK TABLE platform.inbox_events IN ACCESS EXCLUSIVE MODE")
    op.execute("""ALTER TABLE platform.inbox_events
      ADD COLUMN turn_ingress_at timestamptz,
      ADD COLUMN turn_ingress_seq bigint,
      ADD CONSTRAINT inbox_turn_ingress_check CHECK(
        (turn_ingress_at IS NULL AND turn_ingress_seq IS NULL) OR
        (turn_ingress_at IS NOT NULL AND isfinite(turn_ingress_at) AND turn_ingress_seq>0
          AND turn_ingress_seq IS NOT NULL AND normalized_event->>'kind'='CLIENT_MESSAGE'))""")
    op.execute("CREATE SEQUENCE platform.turn_ingress_seq AS bigint MINVALUE 1 NO CYCLE CACHE 1")
    op.execute("REVOKE ALL ON SEQUENCE platform.turn_ingress_seq FROM PUBLIC,asm_runtime")
    op.execute("""CREATE INDEX inbox_turn_origin_idx ON platform.inbox_events
      (workspace_id,connection_id,(normalized_event->>'chat_id'),(normalized_event->>'message_id'),turn_ingress_seq)
      WHERE normalized_event->>'kind'='CLIENT_MESSAGE'""")
    op.execute("""ALTER TABLE app.conversations
      ADD COLUMN control_mode text NOT NULL DEFAULT 'HUMAN' CHECK(control_mode='HUMAN'),
      ADD COLUMN control_generation bigint NOT NULL DEFAULT 1 CHECK(control_generation>0)""")
    op.execute("""CREATE TABLE app.conversation_turns(
      workspace_id uuid NOT NULL, id uuid NOT NULL DEFAULT uuidv7(),
      conversation_id uuid NOT NULL, connection_id uuid NOT NULL, provider_chat_id text NOT NULL,
      revision bigint NOT NULL DEFAULT 1 CHECK(revision>0), control_generation bigint NOT NULL CHECK(control_generation>0),
      state text NOT NULL CHECK(state IN ('COLLECTING','WAITING_MEDIA','READY','FAILED')),
      policy_version integer NOT NULL DEFAULT 1 CHECK(policy_version=1),
      debounce_ms integer NOT NULL DEFAULT 2000 CHECK(debounce_ms BETWEEN 100 AND 5000),
      group_ms integer NOT NULL DEFAULT 10000 CHECK(group_ms BETWEEN debounce_ms AND 30000),
      media_ms integer NOT NULL DEFAULT 15000 CHECK(media_ms BETWEEN 0 AND 30000),
      max_members integer NOT NULL DEFAULT 32 CHECK(max_members BETWEEN 1 AND 64),
      member_count integer NOT NULL DEFAULT 0 CHECK(member_count BETWEEN 0 AND max_members),
      media_group_id text, first_ingress_at timestamptz NOT NULL CHECK(isfinite(first_ingress_at)),
      last_ingress_at timestamptz NOT NULL CHECK(isfinite(last_ingress_at)),
      hard_at timestamptz NOT NULL CHECK(isfinite(hard_at)), quiet_at timestamptz NOT NULL CHECK(isfinite(quiet_at)),
      media_deadline_at timestamptz NOT NULL CHECK(isfinite(media_deadline_at)),
      seal_time timestamptz CHECK(isfinite(seal_time)), closed_at timestamptz CHECK(isfinite(closed_at)),
      ready_at timestamptz CHECK(isfinite(ready_at)), readiness text CHECK(readiness IN ('COMPLETE','PARTIAL')),
      error_code text CHECK(error_code IN ('INVALID_INPUT','DEPENDENCY_TIMEOUT','DEPENDENCY_UNAVAILABLE','RETRY_EXHAUSTED')),
      created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      PRIMARY KEY(workspace_id,id),
      UNIQUE(workspace_id,id,connection_id), UNIQUE(workspace_id,id,connection_id,conversation_id),
      FOREIGN KEY(workspace_id,conversation_id,connection_id,provider_chat_id)
        REFERENCES app.conversations(workspace_id,id,connection_id,provider_chat_id) ON DELETE RESTRICT,
      CHECK(last_ingress_at>=first_ingress_at AND quiet_at<=hard_at AND quiet_at>=first_ingress_at),
      CHECK(hard_at=first_ingress_at+group_ms*interval '1 millisecond'),
      CHECK(media_deadline_at<=hard_at+media_ms*interval '1 millisecond'),
      CHECK((state='COLLECTING' AND seal_time IS NULL AND closed_at IS NULL AND readiness IS NULL AND ready_at IS NULL AND error_code IS NULL) OR
        (state='WAITING_MEDIA' AND seal_time IS NOT NULL AND closed_at IS NOT NULL AND readiness IS NULL AND ready_at IS NULL AND error_code IS NULL) OR
        (state='READY' AND seal_time IS NOT NULL AND closed_at IS NOT NULL AND readiness IS NOT NULL AND ready_at IS NOT NULL AND error_code IS NULL) OR
        (state='FAILED' AND error_code IS NOT NULL)),
      CHECK(seal_time IS NULL OR (seal_time>=first_ingress_at AND seal_time<=quiet_at AND
        media_deadline_at=least(seal_time+media_ms*interval '1 millisecond',hard_at+media_ms*interval '1 millisecond'))))""")
    op.execute("""CREATE UNIQUE INDEX conversation_turn_collecting_key ON app.conversation_turns(workspace_id,conversation_id)
      WHERE state='COLLECTING'""")
    op.execute("""ALTER TABLE app.file_objects ADD CONSTRAINT file_objects_turn_ref_key
      UNIQUE(workspace_id,id,message_id,connection_id,conversation_id)""")
    op.execute("""CREATE TABLE app.conversation_turn_messages(
      workspace_id uuid NOT NULL, message_id uuid NOT NULL, turn_id uuid NOT NULL,
      conversation_id uuid NOT NULL, connection_id uuid NOT NULL,
      direction text NOT NULL DEFAULT 'INBOUND' CHECK(direction='INBOUND'), content_type text NOT NULL,
      origin_inbox_id uuid NOT NULL, turn_ingress_at timestamptz NOT NULL CHECK(isfinite(turn_ingress_at)),
      turn_ingress_seq bigint NOT NULL CHECK(turn_ingress_seq>0), file_id uuid,
      PRIMARY KEY(workspace_id,message_id),
      FOREIGN KEY(workspace_id,turn_id,connection_id,conversation_id)
        REFERENCES app.conversation_turns(workspace_id,id,connection_id,conversation_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,message_id,connection_id,conversation_id,direction,content_type)
        REFERENCES app.messages(workspace_id,id,connection_id,conversation_id,direction,content_type) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,origin_inbox_id,connection_id)
        REFERENCES platform.inbox_events(workspace_id,id,connection_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,file_id,message_id,connection_id,conversation_id)
        REFERENCES app.file_objects(workspace_id,id,message_id,connection_id,conversation_id) ON DELETE RESTRICT,
      CHECK((content_type='TEXT' AND file_id IS NULL) OR (content_type='IMAGE_REFERENCE' AND file_id IS NOT NULL)))""")
    op.execute(
        "CREATE INDEX turn_members_order_idx ON app.conversation_turn_messages(workspace_id,turn_id,turn_ingress_at,turn_ingress_seq,message_id)"
    )
    op.execute("""ALTER TABLE platform.messaging_jobs
      ADD COLUMN turn_id uuid, ADD COLUMN turn_revision bigint, ADD COLUMN step text, ADD COLUMN turn_outcome text,
      DROP CONSTRAINT messaging_jobs_kind_check, DROP CONSTRAINT messaging_jobs_check,
      ADD CONSTRAINT messaging_jobs_kind_check CHECK(kind IN ('PROCESS_INBOX','SEND_MANUAL_TEXT','FETCH_IMAGE','PROCESS_TURN')),
      ADD CONSTRAINT messaging_jobs_check CHECK(
        (kind='PROCESS_INBOX' AND inbox_id IS NOT NULL AND outbox_id IS NULL AND file_id IS NULL AND turn_id IS NULL) OR
        (kind='SEND_MANUAL_TEXT' AND outbox_id IS NOT NULL AND inbox_id IS NULL AND file_id IS NULL AND turn_id IS NULL) OR
        (kind='FETCH_IMAGE' AND file_id IS NOT NULL AND inbox_id IS NULL AND outbox_id IS NULL AND turn_id IS NULL) OR
        (kind='PROCESS_TURN' AND turn_id IS NOT NULL AND inbox_id IS NULL AND outbox_id IS NULL AND file_id IS NULL)),
      ADD CONSTRAINT messaging_jobs_turn_check CHECK(
        (kind<>'PROCESS_TURN' AND turn_revision IS NULL AND step IS NULL AND turn_outcome IS NULL) OR
        (kind='PROCESS_TURN' AND turn_revision IS NOT NULL AND turn_revision>0 AND step IS NOT NULL
          AND step IN ('GROUP','MEDIA','TEST_CONSUME') AND (turn_outcome IS NULL OR turn_outcome IN ('GROUPED','WAITING_MEDIA','OBSERVED','STALE','SUPERSEDED','FAILED')))),
      ADD CONSTRAINT messaging_jobs_turn_fkey FOREIGN KEY(workspace_id,turn_id,connection_id)
        REFERENCES app.conversation_turns(workspace_id,id,connection_id) ON DELETE RESTRICT,
      ADD CONSTRAINT messaging_jobs_turn_step_key UNIQUE(workspace_id,turn_id,turn_revision,step),
      ADD CONSTRAINT messaging_jobs_turn_receipt_key UNIQUE(workspace_id,id,connection_id,kind,turn_id,turn_revision,step)""")
    op.execute("""CREATE TABLE platform.turn_consumer_receipts(
      workspace_id uuid NOT NULL, job_id uuid NOT NULL, connection_id uuid NOT NULL,
      kind text NOT NULL DEFAULT 'PROCESS_TURN' CHECK(kind='PROCESS_TURN'),
      turn_id uuid NOT NULL, turn_revision bigint NOT NULL CHECK(turn_revision>0),
      step text NOT NULL DEFAULT 'TEST_CONSUME' CHECK(step='TEST_CONSUME'),
      consumer text NOT NULL DEFAULT 'TURN_TEST_V1' CHECK(consumer='TURN_TEST_V1'),
      winning_claim_token uuid NOT NULL, input_context_version bigint NOT NULL CHECK(input_context_version>0),
      input_control_generation bigint NOT NULL CHECK(input_control_generation>0),
      snapshot_digest text NOT NULL CHECK(snapshot_digest ~ '^[0-9a-f]{64}$'),
      result jsonb NOT NULL CHECK(jsonb_typeof(result)='object'), accepted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      PRIMARY KEY(workspace_id,job_id), UNIQUE(workspace_id,turn_id,turn_revision,consumer),
      FOREIGN KEY(workspace_id,job_id,connection_id,kind,turn_id,turn_revision,step)
        REFERENCES platform.messaging_jobs(workspace_id,id,connection_id,kind,turn_id,turn_revision,step) ON DELETE RESTRICT)""")
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY turns_migrator ON {table} TO asm_migrator USING(true) WITH CHECK(true)"
        )
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC,asm_runtime")


def _guards() -> None:
    op.execute("""CREATE FUNCTION platform.turn_require_isolation() RETURNS void
      LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$ BEGIN
      IF current_setting('transaction_isolation')<>'read committed' THEN
        RAISE EXCEPTION 'TRANSACTION_STATE' USING ERRCODE='P2001'; END IF;
      END $$""")
    op.execute("""CREATE FUNCTION platform.turn_ingress() RETURNS trigger
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$ BEGIN
      PERFORM platform.turn_require_isolation();
      IF NEW.turn_ingress_at IS NOT NULL OR NEW.turn_ingress_seq IS NOT NULL THEN
        RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
      IF NEW.normalized_event->>'kind'='CLIENT_MESSAGE' THEN
        PERFORM 1 FROM app.channel_connections WHERE workspace_id=NEW.workspace_id AND id=NEW.connection_id FOR SHARE;
        IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P2001'; END IF;
        NEW.turn_ingress_at:=clock_timestamp(); NEW.turn_ingress_seq:=nextval('platform.turn_ingress_seq');
      END IF;
      RETURN NEW;
      END $$""")
    op.execute(
        "CREATE TRIGGER turn_ingress BEFORE INSERT ON platform.inbox_events FOR EACH ROW EXECUTE FUNCTION platform.turn_ingress()"
    )
    op.execute(
        "CREATE TRIGGER turn_ingress_immutable BEFORE UPDATE ON platform.inbox_events FOR EACH ROW EXECUTE FUNCTION platform.messaging_immutable('turn_ingress_at','turn_ingress_seq')"
    )
    op.execute("""CREATE FUNCTION platform.turn_immutable() RETURNS trigger
      LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$ BEGIN
      IF TG_TABLE_NAME<>'conversation_turns' THEN
        IF NEW IS DISTINCT FROM OLD THEN RAISE EXCEPTION 'immutable turn record' USING ERRCODE='23514'; END IF;
      ELSIF OLD.state<>'COLLECTING' AND OLD.member_count>0 THEN
        IF (NEW.state='COLLECTING') OR
          (NEW.member_count,NEW.last_ingress_at,NEW.quiet_at,NEW.media_deadline_at,NEW.seal_time,NEW.closed_at,NEW.media_group_id)
          IS DISTINCT FROM (OLD.member_count,OLD.last_ingress_at,OLD.quiet_at,OLD.media_deadline_at,OLD.seal_time,OLD.closed_at,OLD.media_group_id) THEN
          RAISE EXCEPTION 'sealed turn membership/deadline' USING ERRCODE='23514'; END IF;
        IF OLD.state='FAILED' AND NEW IS DISTINCT FROM OLD THEN RAISE EXCEPTION 'terminal turn' USING ERRCODE='23514'; END IF;
      END IF; RETURN NEW;
      END $$""")
    for table in TABLES:
        op.execute(
            f"CREATE TRIGGER turn_immutable BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION platform.turn_immutable()"
        )
    op.execute("""CREATE TRIGGER turn_identity BEFORE UPDATE ON app.conversation_turns FOR EACH ROW
      EXECUTE FUNCTION platform.messaging_immutable('workspace_id','id','conversation_id','connection_id','provider_chat_id','control_generation','first_ingress_at','hard_at','policy_version','debounce_ms','group_ms','media_ms','max_members','created_at')""")
    op.execute("""CREATE TRIGGER turn_job_identity BEFORE UPDATE ON platform.messaging_jobs FOR EACH ROW
      EXECUTE FUNCTION platform.messaging_immutable('workspace_id','id','connection_id','kind','inbox_id','outbox_id','file_id','turn_id','turn_revision','step','correlation_id')""")
    op.execute("""CREATE FUNCTION platform.turn_member_check() RETURNS trigger
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE t app.conversation_turns%ROWTYPE; i platform.inbox_events%ROWTYPE; m app.messages%ROWTYPE;
      BEGIN
        SELECT * INTO STRICT t FROM app.conversation_turns WHERE workspace_id=NEW.workspace_id AND id=NEW.turn_id;
        SELECT * INTO STRICT i FROM platform.inbox_events WHERE workspace_id=NEW.workspace_id AND id=NEW.origin_inbox_id;
        SELECT * INTO STRICT m FROM app.messages WHERE workspace_id=NEW.workspace_id AND id=NEW.message_id;
        IF (t.state<>'COLLECTING' AND t.member_count<>0) OR i.turn_ingress_seq IS NULL OR
          (NEW.turn_ingress_at,NEW.turn_ingress_seq) IS DISTINCT FROM (i.turn_ingress_at,i.turn_ingress_seq) OR
          i.normalized_event->>'kind'<>'CLIENT_MESSAGE' OR
          (i.connection_id,i.normalized_event->>'chat_id',i.normalized_event->>'message_id') IS DISTINCT FROM
          (m.connection_id,m.provider_chat_id,m.provider_message_id) THEN
          RAISE EXCEPTION 'invalid turn origin/membership' USING ERRCODE='23514'; END IF;
        RETURN NEW;
      END $$""")
    op.execute(
        "CREATE TRIGGER turn_member_check BEFORE INSERT ON app.conversation_turn_messages FOR EACH ROW EXECUTE FUNCTION platform.turn_member_check()"
    )
    op.execute("""CREATE FUNCTION platform.turn_members_consistent() RETURNS trigger
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE actual_count integer; expected_count integer; first_at timestamptz; saved_first timestamptz;
      BEGIN
        SELECT member_count,first_ingress_at INTO expected_count,saved_first FROM app.conversation_turns
          WHERE workspace_id=NEW.workspace_id AND id=NEW.id;
        IF NOT FOUND THEN RETURN NULL; END IF;
        SELECT count(*),min(turn_ingress_at) INTO actual_count,first_at FROM app.conversation_turn_messages
          WHERE workspace_id=NEW.workspace_id AND turn_id=NEW.id;
        IF actual_count=0 OR actual_count<>expected_count OR first_at IS DISTINCT FROM saved_first THEN
          RAISE EXCEPTION 'inconsistent turn membership' USING ERRCODE='23514'; END IF;
        RETURN NULL;
      END $$""")
    op.execute("""CREATE CONSTRAINT TRIGGER turn_members_consistent AFTER INSERT OR UPDATE ON app.conversation_turns
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.turn_members_consistent()""")


def _grouping() -> None:
    op.execute("""CREATE FUNCTION platform.turn_enqueue(ws uuid,p_turn uuid,corr uuid) RETURNS void
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
      END $$""")
    op.execute("""CREATE FUNCTION platform.turn_seal(ws uuid,p_turn uuid,p_seal timestamptz,corr uuid,bump boolean) RETURNS void
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE t app.conversation_turns%ROWTYPE; pending boolean; complete boolean; deadline timestamptz;
      BEGIN
        SELECT * INTO STRICT t FROM app.conversation_turns WHERE workspace_id=ws AND id=p_turn FOR NO KEY UPDATE;
        IF t.state='FAILED' THEN RETURN; END IF;
        SELECT coalesce(bool_or(f.status='PENDING'),false),coalesce(bool_and(f.status='READY'),true)
          INTO pending,complete FROM app.conversation_turn_messages m
          JOIN app.file_objects f ON (f.workspace_id,f.id)=(m.workspace_id,m.file_id)
          WHERE m.workspace_id=ws AND m.turn_id=t.id;
        deadline:=CASE WHEN t.state='COLLECTING' THEN least(p_seal+t.media_ms*interval '1 millisecond',t.media_deadline_at) ELSE t.media_deadline_at END;
        UPDATE app.conversation_turns SET revision=revision+CASE WHEN bump THEN 1 ELSE 0 END,
          seal_time=coalesce(seal_time,p_seal),closed_at=coalesce(closed_at,clock_timestamp()),media_deadline_at=deadline,
          state=CASE WHEN pending AND clock_timestamp()<deadline AND t.state<>'READY' THEN 'WAITING_MEDIA' ELSE 'READY' END,
          readiness=CASE WHEN pending AND clock_timestamp()<deadline AND t.state<>'READY' THEN NULL WHEN complete THEN 'COMPLETE' ELSE 'PARTIAL' END,
          ready_at=CASE WHEN pending AND clock_timestamp()<deadline AND t.state<>'READY' THEN NULL ELSE coalesce(ready_at,clock_timestamp()) END
          WHERE workspace_id=ws AND id=t.id;
        PERFORM platform.turn_enqueue(ws,t.id,corr);
      END $$""")
    op.execute("""CREATE FUNCTION platform.turn_group_message(ws uuid,p_message uuid,corr uuid) RETURNS void
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE m app.messages%ROWTYPE; origin platform.inbox_events%ROWTYPE; t app.conversation_turns%ROWTYPE;
        conv app.conversations%ROWTYPE; file uuid; late boolean:=false; fresh boolean:=false;
      BEGIN
        PERFORM platform.turn_require_isolation();
        SELECT * INTO STRICT m FROM app.messages WHERE workspace_id=ws AND id=p_message;
        -- The caller holds connection UPDATE; this is a separate post-barrier snapshot.
        SELECT * INTO origin FROM platform.inbox_events
          WHERE workspace_id=ws AND connection_id=m.connection_id AND normalized_event->>'kind'='CLIENT_MESSAGE'
            AND normalized_event->>'chat_id'=m.provider_chat_id AND normalized_event->>'message_id'=m.provider_message_id
          ORDER BY turn_ingress_seq NULLS FIRST,id LIMIT 1;
        IF NOT FOUND OR origin.turn_ingress_seq IS NULL THEN RETURN; END IF;
        IF EXISTS(SELECT 1 FROM app.conversation_turn_messages WHERE workspace_id=ws AND message_id=m.id) THEN RETURN; END IF;
        SELECT * INTO STRICT conv FROM app.conversations WHERE workspace_id=ws AND id=m.conversation_id FOR NO KEY UPDATE;
        SELECT * INTO t FROM app.conversation_turns WHERE workspace_id=ws AND conversation_id=conv.id AND state='COLLECTING' FOR NO KEY UPDATE;
        IF FOUND AND origin.turn_ingress_at<t.first_ingress_at THEN
          late:=true; t.id:=NULL;
        ELSIF FOUND AND (origin.turn_ingress_at>=least(t.quiet_at,t.hard_at) OR t.member_count>=t.max_members OR
          (t.media_group_id IS NOT NULL AND m.media_group_id IS NOT NULL AND t.media_group_id<>m.media_group_id)) THEN
          PERFORM platform.turn_seal(ws,t.id,least(origin.turn_ingress_at,t.quiet_at,t.hard_at),corr,true);
          t.id:=NULL;
        END IF;
        IF t.id IS NULL THEN
          fresh:=true;
          -- Out-of-order input must not move/close the existing collecting window.
          -- The new singleton is sealed immediately; its media budget starts at ingress.
          INSERT INTO app.conversation_turns(workspace_id,conversation_id,connection_id,provider_chat_id,control_generation,state,
            first_ingress_at,last_ingress_at,hard_at,quiet_at,media_deadline_at,media_group_id,seal_time,closed_at)
          VALUES(ws,conv.id,m.connection_id,m.provider_chat_id,conv.control_generation,CASE WHEN late THEN 'WAITING_MEDIA' ELSE 'COLLECTING' END,
            origin.turn_ingress_at,origin.turn_ingress_at,origin.turn_ingress_at+interval '10 seconds',origin.turn_ingress_at+interval '2 seconds',
            origin.turn_ingress_at+CASE WHEN late THEN interval '15 seconds' ELSE interval '25 seconds' END,m.media_group_id,
            CASE WHEN late THEN origin.turn_ingress_at END,CASE WHEN late THEN clock_timestamp() END) RETURNING * INTO t;
        END IF;
        SELECT id INTO file FROM app.file_objects WHERE workspace_id=ws AND message_id=m.id;
        INSERT INTO app.conversation_turn_messages(workspace_id,message_id,turn_id,conversation_id,connection_id,content_type,origin_inbox_id,turn_ingress_at,turn_ingress_seq,file_id)
          VALUES(ws,m.id,t.id,conv.id,m.connection_id,m.content_type,origin.id,origin.turn_ingress_at,origin.turn_ingress_seq,file);
        UPDATE app.conversation_turns SET member_count=member_count+1,revision=revision+CASE WHEN fresh THEN 0 ELSE 1 END,
          last_ingress_at=greatest(last_ingress_at,origin.turn_ingress_at),
          quiet_at=least(greatest(last_ingress_at,origin.turn_ingress_at)+debounce_ms*interval '1 millisecond',hard_at),
          media_group_id=coalesce(media_group_id,m.media_group_id)
          WHERE workspace_id=ws AND id=t.id RETURNING * INTO t;
        IF late THEN
          PERFORM platform.turn_seal(ws,t.id,t.seal_time,corr,false);
        ELSIF t.member_count=t.max_members THEN
          PERFORM platform.turn_seal(ws,t.id,least(origin.turn_ingress_at,t.quiet_at,t.hard_at),corr,false);
        ELSIF clock_timestamp()>=least(t.quiet_at,t.hard_at) THEN
          PERFORM platform.turn_seal(ws,t.id,least(t.quiet_at,t.hard_at),corr,false);
        ELSE PERFORM platform.turn_enqueue(ws,t.id,corr);
        END IF;
      END $$""")
    op.execute("""CREATE FUNCTION platform.turn_material() RETURNS trigger
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE ws uuid; conv uuid; tid uuid; t app.conversation_turns%ROWTYPE; corr uuid;
      BEGIN
        ws:=NEW.workspace_id;
        IF TG_TABLE_NAME='messages' THEN
          IF NEW.direction<>'OUTBOUND' THEN RETURN NEW; END IF;
          conv:=NEW.conversation_id;
        ELSIF TG_TABLE_NAME='outbox_events' THEN
          IF OLD.status NOT IN ('PENDING','DISPATCHING') OR NEW.status NOT IN ('SENT','FAILED','UNKNOWN') THEN RETURN NEW; END IF;
          SELECT conversation_id INTO STRICT conv FROM app.messages WHERE workspace_id=ws AND id=NEW.message_id;
        ELSE
          IF OLD.status<>'PENDING' OR NEW.status NOT IN ('READY','FAILED') THEN RETURN NEW; END IF;
          conv:=NEW.conversation_id;
        END IF;
        PERFORM 1 FROM app.conversations WHERE workspace_id=ws AND id=conv FOR NO KEY UPDATE;
        UPDATE app.conversations SET version=version+1 WHERE workspace_id=ws AND id=conv;
        IF TG_TABLE_NAME='file_objects' THEN
          SELECT turn_id INTO tid FROM app.conversation_turn_messages WHERE workspace_id=ws AND message_id=NEW.message_id;
          IF tid IS NOT NULL THEN
            SELECT * INTO STRICT t FROM app.conversation_turns WHERE workspace_id=ws AND id=tid FOR NO KEY UPDATE;
            IF t.state<>'FAILED' THEN
              SELECT correlation_id INTO STRICT corr FROM platform.messaging_jobs WHERE workspace_id=ws AND file_id=NEW.id;
              UPDATE app.conversation_turns SET revision=revision+1 WHERE workspace_id=ws AND id=tid;
              IF t.state<>'COLLECTING' OR clock_timestamp()>=least(t.quiet_at,t.hard_at) THEN
                PERFORM platform.turn_seal(ws,tid,coalesce(t.seal_time,least(t.quiet_at,t.hard_at)),corr,false);
              ELSE PERFORM platform.turn_enqueue(ws,tid,corr);
              END IF;
            END IF;
          END IF;
        END IF;
        RETURN NEW;
      END $$""")
    op.execute(
        "CREATE TRIGGER turn_manual_material AFTER INSERT ON app.messages FOR EACH ROW EXECUTE FUNCTION platform.turn_material()"
    )
    op.execute(
        "CREATE TRIGGER turn_delivery_material AFTER UPDATE OF status ON app.outbox_events FOR EACH ROW EXECUTE FUNCTION platform.turn_material()"
    )
    op.execute(
        "CREATE TRIGGER turn_file_material AFTER UPDATE OF status ON app.file_objects FOR EACH ROW EXECUTE FUNCTION platform.turn_material()"
    )


def _maintenance() -> None:
    op.execute("""CREATE FUNCTION platform.turn_preflight(j platform.messaging_jobs,p_nowait boolean,p_terminal boolean) RETURNS void
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
      END $$""")
    op.execute("""CREATE FUNCTION platform.turn_supersede(j platform.messaging_jobs) RETURNS boolean
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$ BEGIN
        IF j.kind='PROCESS_TURN' AND EXISTS(SELECT 1 FROM app.conversation_turns
          WHERE workspace_id=j.workspace_id AND id=j.turn_id AND revision<>j.turn_revision) THEN
          UPDATE platform.messaging_jobs SET status='SUCCEEDED',turn_outcome='SUPERSEDED',error_code=NULL,
            attempt_count=greatest(1,attempt_count),first_started_at=coalesce(first_started_at,clock_timestamp()),
            claim_token=NULL,lease_until=NULL,worker_id=NULL,completed_at=clock_timestamp(),version=version+1 WHERE id=j.id;
          RETURN true;
        END IF; RETURN false;
      END $$""")
    op.execute("""CREATE OR REPLACE FUNCTION platform.messaging_reschedule(p_job uuid,p_error text,p_retry boolean,p_delay integer) RETURNS jsonb
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
        PERFORM platform.turn_preflight(j,false,NOT retry);
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
      END $$""")
    # Old batch operations must not remain as callable overloads.
    op.execute("DROP FUNCTION platform.messaging_claim(text)")
    op.execute("DROP FUNCTION platform.messaging_recover_expired(integer)")
    op.execute("""CREATE FUNCTION platform.messaging_claim(p_worker text,p_until timestamptz,p_at timestamptz,p_id uuid) RETURNS jsonb
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
            IF exhausted OR j.kind='PROCESS_TURN' THEN PERFORM platform.turn_preflight(j,true,exhausted); END IF;
          EXCEPTION WHEN lock_not_available THEN RAISE EXCEPTION 'preflight busy' USING ERRCODE='P3001'; END;
          IF platform.turn_supersede(j) THEN
            RETURN jsonb_build_object('step','TERMINALIZED','scan_until',cutoff,'at',pos,'id',j.id);
          ELSIF exhausted THEN
            PERFORM platform.messaging_reschedule(j.id,'RETRY_EXHAUSTED',false);
            RETURN jsonb_build_object('step','TERMINALIZED','scan_until',cutoff,'at',pos,'id',j.id);
          END IF;
          IF j.kind='PROCESS_TURN' THEN
            SELECT * INTO STRICT t FROM app.conversation_turns WHERE workspace_id=j.workspace_id AND id=j.turn_id;
            IF (j.step='GROUP' AND clock_timestamp()<least(t.quiet_at,t.hard_at)) OR
              (j.step='MEDIA' AND clock_timestamp()<t.media_deadline_at) THEN
              RAISE EXCEPTION 'not yet due' USING ERRCODE='P3001';
            END IF;
          END IF;
          UPDATE platform.messaging_jobs SET status='RUNNING',claim_token=gen_random_uuid(),lease_until=clock_timestamp()+interval '30 seconds',worker_id=p_worker,
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
      END $$""")
    op.execute("""CREATE FUNCTION platform.messaging_recover_expired(p_until timestamptz,p_at timestamptz,p_id uuid) RETURNS jsonb
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
          ELSE PERFORM platform.messaging_reschedule(j.id,'DEPENDENCY_TIMEOUT',true);
          END IF;
          RETURN jsonb_build_object('step','RECOVERED','scan_until',cutoff,'at',pos,'id',j.id);
        EXCEPTION WHEN SQLSTATE 'P3001' THEN
          RETURN jsonb_build_object('step','BUSY','scan_until',cutoff,'at',pos,'id',j.id);
        END;
      END $$""")


def _consumer() -> None:
    op.execute("""ALTER TABLE platform.messaging_jobs ADD COLUMN turn_input jsonb,
      ADD CONSTRAINT messaging_jobs_turn_input_check CHECK(turn_input IS NULL OR
        (kind='PROCESS_TURN' AND step='TEST_CONSUME' AND jsonb_typeof(turn_input)='object'))""")
    op.execute("""CREATE FUNCTION platform.turn_snapshot(ws uuid,p_turn uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE result jsonb; members jsonb;
      BEGIN
        SELECT jsonb_agg(jsonb_build_object('message_id',m.id,'message_version',m.version,'content_type',m.content_type,
          'ingress_at',tm.turn_ingress_at,'ingress_seq',tm.turn_ingress_seq,
          'file',CASE WHEN f.id IS NULL THEN NULL ELSE jsonb_build_object('file_id',f.id,'version',f.version,
            'status',f.status,'error_code',f.error_code,'wait_expired',f.status='PENDING') END)
          ORDER BY tm.turn_ingress_at,tm.turn_ingress_seq,tm.message_id)
          INTO members FROM app.conversation_turn_messages tm JOIN app.messages m ON (m.workspace_id,m.id)=(tm.workspace_id,tm.message_id)
          LEFT JOIN app.file_objects f ON (f.workspace_id,f.id)=(tm.workspace_id,tm.file_id)
          WHERE tm.workspace_id=ws AND tm.turn_id=p_turn;
        IF members IS NULL THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        SELECT jsonb_build_object('workspace_id',ws,'connection_id',t.connection_id,'turn_id',t.id,'turn_revision',t.revision,
          'context_version',c.version,'control_generation',t.control_generation,'readiness',t.readiness,'members',members)
          INTO STRICT result FROM app.conversation_turns t JOIN app.conversations c ON (c.workspace_id,c.id)=(t.workspace_id,t.conversation_id)
          WHERE t.workspace_id=ws AND t.id=p_turn AND t.state='READY';
        RETURN result || jsonb_build_object('snapshot_digest',encode(sha256(convert_to(result::text,'UTF8')),'hex'));
      END $$""")
    op.execute("""CREATE FUNCTION platform.turn_execute(p_job uuid,p_claim uuid) RETURNS jsonb
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
      END $$""")
    op.execute("""CREATE FUNCTION platform.turn_consumer_replay(p_job uuid,p_claim uuid) RETURNS jsonb
      LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE saved jsonb;
      BEGIN
        -- One statement/snapshot: never observe a receipt without its terminal job.
        SELECT r.result INTO saved FROM platform.turn_consumer_receipts r JOIN platform.messaging_jobs j
          ON (j.workspace_id,j.id,j.connection_id,j.kind,j.turn_id,j.turn_revision,j.step)=
             (r.workspace_id,r.job_id,r.connection_id,r.kind,r.turn_id,r.turn_revision,r.step)
          WHERE j.id=p_job AND j.status='SUCCEEDED' AND j.kind='PROCESS_TURN' AND j.step='TEST_CONSUME'
            AND r.winning_claim_token=p_claim AND j.turn_outcome IN ('OBSERVED','STALE');
        IF NOT FOUND THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
        RETURN saved;
      END $$""")
    op.execute("""CREATE FUNCTION platform.turn_consumer_finalize(p_job uuid,p_claim uuid,p_result jsonb) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE j platform.messaging_jobs%ROWTYPE; t app.conversation_turns%ROWTYPE; c app.conversations%ROWTYPE;
        expected jsonb; result jsonb; code text; accepted timestamptz;
      BEGIN
        PERFORM platform.turn_require_isolation();
        -- Terminal replay admits only the winning read capability, not a new mutation.
        BEGIN RETURN platform.turn_consumer_replay(p_job,p_claim);
        EXCEPTION WHEN SQLSTATE 'P2001' THEN
          IF SQLERRM<>'STALE_CLAIM' THEN RAISE; END IF;
        END;
        BEGIN
          PERFORM platform.messaging_admit(p_job,p_claim);
        EXCEPTION WHEN SQLSTATE 'P2001' THEN
          IF SQLERRM<>'STALE_CLAIM' THEN RAISE; END IF;
          -- Another finalizer may have committed while admission waited for
          -- the job lock. Re-read the narrow capability in a fresh statement.
          RETURN platform.turn_consumer_replay(p_job,p_claim);
        END;
        j:=platform.messaging_guard(p_job,p_claim);
        IF j.kind<>'PROCESS_TURN' OR j.step<>'TEST_CONSUME' THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        PERFORM platform.turn_preflight(j,false,false);
        PERFORM platform.messaging_guard(p_job,p_claim);
        IF platform.turn_supersede(j) THEN RETURN jsonb_build_object('code','SUPERSEDED','job_id',j.id,'turn_id',j.turn_id,'turn_revision',j.turn_revision); END IF;
        IF j.turn_input IS NULL THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        SELECT jsonb_build_object('consumer','TURN_TEST_V1','snapshot_digest',j.turn_input->>'snapshot_digest',
          'member_count',jsonb_array_length(j.turn_input->'members'),
          'ready_file_count',(SELECT count(*) FROM jsonb_array_elements(j.turn_input->'members') m WHERE m->'file'->>'status'='READY'),
          'wait_expired_count',(SELECT count(*) FROM jsonb_array_elements(j.turn_input->'members') m WHERE m->'file'->>'wait_expired'='true')) INTO expected;
        IF p_result IS DISTINCT FROM expected THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        SELECT * INTO STRICT t FROM app.conversation_turns WHERE workspace_id=j.workspace_id AND id=j.turn_id;
        SELECT * INTO STRICT c FROM app.conversations WHERE workspace_id=j.workspace_id AND id=t.conversation_id;
        code:=CASE WHEN c.version=(j.turn_input->>'context_version')::bigint AND c.control_generation=(j.turn_input->>'control_generation')::bigint THEN 'OBSERVED' ELSE 'STALE' END;
        accepted:=clock_timestamp();
        result:=jsonb_build_object('code',code,'job_id',j.id,'workspace_id',j.workspace_id,'connection_id',j.connection_id,
          'turn_id',j.turn_id,'turn_revision',j.turn_revision,'consumer','TURN_TEST_V1',
          'input_context_version',(j.turn_input->>'context_version')::bigint,'input_control_generation',(j.turn_input->>'control_generation')::bigint,
          'snapshot_digest',j.turn_input->>'snapshot_digest','accepted_at',accepted,'result',expected);
        INSERT INTO platform.turn_consumer_receipts(workspace_id,job_id,connection_id,turn_id,turn_revision,winning_claim_token,
          input_context_version,input_control_generation,snapshot_digest,result,accepted_at)
        VALUES(j.workspace_id,j.id,j.connection_id,j.turn_id,j.turn_revision,j.claim_token,
          (j.turn_input->>'context_version')::bigint,(j.turn_input->>'control_generation')::bigint,j.turn_input->>'snapshot_digest',result,accepted);
        UPDATE platform.messaging_jobs SET status='SUCCEEDED',turn_outcome=code,error_code=NULL,claim_token=NULL,lease_until=NULL,worker_id=NULL,
          completed_at=accepted,version=version+1 WHERE id=j.id;
        RETURN result;
      END $$""")


def _extend_kernel() -> None:
    _replace(
        "messaging_finish_send",
        (
            "        IF p_outcome='SUCCESS' THEN\n",
            "        IF p_outcome IN ('SUCCESS','UNKNOWN') THEN\n          PERFORM platform.turn_preflight(j,false,true);\n          PERFORM platform.messaging_guard(p_job,p_claim);\n        END IF;\n        IF p_outcome='SUCCESS' THEN\n",
        ),
    )
    _replace(
        "files_finish_fetch",
        (
            "          UPDATE platform.file_object_uploads SET status='WINNER'",
            "          PERFORM platform.turn_preflight(j,false,true);\n          PERFORM platform.messaging_guard(p_job,p_claim);\n          UPDATE platform.file_object_uploads SET status='WINNER'",
        ),
    )
    for name in ("messaging_guard", "messaging_admit", "messaging_ingest", "telegram_ingest"):
        changes = [
            ("      BEGIN\n", "      BEGIN\n        PERFORM platform.turn_require_isolation();\n")
        ]
        if name == "telegram_ingest":
            changes.append(
                (
                    "                INSERT INTO platform.inbox_events(",
                    "                PERFORM 1 FROM app.channel_connections WHERE workspace_id=route.workspace_id AND id=route.connection_id FOR SHARE;\n                INSERT INTO platform.inbox_events(",
                )
            )
        _replace(name, *changes)
    _replace(
        "messaging_process_inbox",
        ("id=j.inbox_id FOR UPDATE;", "id=j.inbox_id FOR NO KEY UPDATE;"),
        (
            """        IF code='PROCESSED' AND e->>'provider'='TELEGRAM' THEN
          UPDATE app.conversations SET last_client_inbound_at=greatest(last_client_inbound_at,least(msg.occurred_at,inbox.received_at)),version=version+1
            WHERE workspace_id=j.workspace_id AND id=msg.conversation_id;
        END IF;
""",
            "",
        ),
        (
            "        PERFORM platform.messaging_guard(p_job,p_claim);",
            """        IF code='PROCESSED' THEN
          PERFORM 1 FROM app.conversations WHERE workspace_id=j.workspace_id AND id=msg.conversation_id FOR NO KEY UPDATE;
          UPDATE app.conversations SET version=version+1,
            last_client_inbound_at=CASE WHEN e->>'provider'='TELEGRAM' THEN greatest(last_client_inbound_at,least(msg.occurred_at,inbox.received_at)) ELSE last_client_inbound_at END
            WHERE workspace_id=j.workspace_id AND id=msg.conversation_id;
          PERFORM platform.turn_group_message(j.workspace_id,msg.id,j.correlation_id);
        END IF;
        PERFORM platform.messaging_guard(p_job,p_claim);""",
        ),
    )
    _replace(
        "messaging_job_json",
        (
            "'correlation_id',j.correlation_id,'attempt_count',j.attempt_count) $$",
            """'correlation_id',j.correlation_id,'attempt_count',j.attempt_count) ||
          CASE WHEN j.kind='PROCESS_TURN' THEN jsonb_build_object('turn_id',j.turn_id,'turn_revision',j.turn_revision,'step',j.step) ELSE '{}'::jsonb END $$""",
        ),
    )


def upgrade() -> None:
    _schema()
    _guards()
    _grouping()
    _maintenance()
    _consumer()
    _extend_kernel()
    for signature in (*PRIVATE_FUNCTIONS, *PUBLIC_FUNCTIONS):
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC,asm_runtime")
    for signature in PUBLIC_FUNCTIONS:
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO asm_runtime")


def downgrade() -> None:
    # First operation; populated refusal must leave all data/functions/grants intact.
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM app.conversation_turns) OR EXISTS(SELECT 1 FROM app.conversation_turn_messages) OR
        EXISTS(SELECT 1 FROM platform.turn_consumer_receipts) OR EXISTS(SELECT 1 FROM platform.messaging_jobs WHERE kind='PROCESS_TURN') OR
        EXISTS(SELECT 1 FROM platform.inbox_events WHERE turn_ingress_seq IS NOT NULL OR turn_ingress_at IS NOT NULL) THEN
        RAISE EXCEPTION 'M3 history prevents downgrade' USING ERRCODE='55000'; END IF;
      END $$""")
    for signature in PUBLIC_FUNCTIONS:
        op.execute(f"DROP FUNCTION {signature}")
    for sql in ORIGINAL.values():
        op.execute(sql)
    op.execute(
        "REVOKE ALL ON FUNCTION platform.messaging_claim(text),platform.messaging_recover_expired(integer) FROM PUBLIC,asm_runtime"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION platform.messaging_claim(text),platform.messaging_recover_expired(integer) TO asm_runtime"
    )
    for name, table in (
        ("turn_ingress", "platform.inbox_events"),
        ("turn_ingress_immutable", "platform.inbox_events"),
        ("turn_job_identity", "platform.messaging_jobs"),
        ("turn_manual_material", "app.messages"),
        ("turn_delivery_material", "app.outbox_events"),
        ("turn_file_material", "app.file_objects"),
    ):
        op.execute(f"DROP TRIGGER {name} ON {table}")
    for table in TABLES:
        op.execute(f"DROP TRIGGER turn_immutable ON {table}")
    op.execute("DROP TRIGGER turn_member_check ON app.conversation_turn_messages")
    op.execute("DROP TRIGGER turn_members_consistent ON app.conversation_turns")
    # PL/pgSQL callers do not retain body dependencies; remove callers first.
    for signature in reversed(PRIVATE_FUNCTIONS):
        op.execute(f"DROP FUNCTION {signature}")
    op.execute("DROP TABLE platform.turn_consumer_receipts")
    op.execute("DROP TABLE app.conversation_turn_messages")
    op.execute("""ALTER TABLE platform.messaging_jobs DROP CONSTRAINT messaging_jobs_turn_fkey,
      DROP CONSTRAINT messaging_jobs_turn_step_key,DROP CONSTRAINT messaging_jobs_turn_receipt_key,
      DROP CONSTRAINT messaging_jobs_turn_check,DROP CONSTRAINT messaging_jobs_turn_input_check,
      DROP CONSTRAINT messaging_jobs_kind_check,DROP CONSTRAINT messaging_jobs_check,
      DROP COLUMN turn_id,DROP COLUMN turn_revision,DROP COLUMN step,DROP COLUMN turn_outcome,DROP COLUMN turn_input,
      ADD CONSTRAINT messaging_jobs_kind_check CHECK(kind IN ('PROCESS_INBOX','SEND_MANUAL_TEXT','FETCH_IMAGE')),
      ADD CONSTRAINT messaging_jobs_check CHECK(
        (kind='PROCESS_INBOX' AND inbox_id IS NOT NULL AND outbox_id IS NULL AND file_id IS NULL) OR
        (kind='SEND_MANUAL_TEXT' AND outbox_id IS NOT NULL AND inbox_id IS NULL AND file_id IS NULL) OR
        (kind='FETCH_IMAGE' AND file_id IS NOT NULL AND inbox_id IS NULL AND outbox_id IS NULL))""")
    op.execute("DROP TABLE app.conversation_turns")
    op.execute("ALTER TABLE app.file_objects DROP CONSTRAINT file_objects_turn_ref_key")
    op.execute("DROP INDEX platform.inbox_turn_origin_idx")
    op.execute(
        "ALTER TABLE platform.inbox_events DROP CONSTRAINT inbox_turn_ingress_check,DROP COLUMN turn_ingress_at,DROP COLUMN turn_ingress_seq"
    )
    op.execute("DROP SEQUENCE platform.turn_ingress_seq")
    op.execute(
        "ALTER TABLE app.conversations DROP COLUMN control_mode,DROP COLUMN control_generation"
    )
