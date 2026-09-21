"""M2.3 Telegram receipts, immutable binding, observation fences and owner API.

Only two new tables; the 0006 durable kernel remains the source of Inbox/Jobs and
outbound effects. Embedded 0006 definitions restore changed capabilities exactly.
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

# Accepted 0006 SQL snapshots; 0001--0006 remain immutable.
ORIGINAL = {
    "messaging_validate_event": r"""CREATE FUNCTION platform.messaging_validate_event(e jsonb) RETURNS jsonb
      LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
      DECLARE key text; value text; occurred timestamptz; normalized jsonb;
      fields constant text[]:=ARRAY['provider','bot_identity','event_id','kind','external_connection_id','chat_id','message_id','sender_id','occurred_at','text','image_file_id','media_group_id'];
      BEGIN
        IF e IS NULL OR jsonb_typeof(e)<>'object' OR octet_length(e::text)>65536 OR
          (SELECT count(*) FROM jsonb_object_keys(e))<>12 OR NOT e ?& fields THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        FOREACH key IN ARRAY fields LOOP
          IF jsonb_typeof(e->key) NOT IN ('string','null') THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        END LOOP;
        IF e->>'provider' IS DISTINCT FROM 'CONTROLLED' OR e->>'kind' IS NULL OR
           e->>'kind' NOT IN ('CLIENT_MESSAGE','NATIVE_OWNER_MESSAGE','MESSAGE_EDITED','MESSAGE_DELETED','UNSUPPORTED') THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        FOREACH key IN ARRAY ARRAY['bot_identity','event_id','external_connection_id'] LOOP
          IF NOT platform.messaging_valid_id(e->>key,256,1024) THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        END LOOP;
        FOREACH key IN ARRAY ARRAY['chat_id','message_id','sender_id','media_group_id'] LOOP
          IF e->>key IS NOT NULL AND NOT platform.messaging_valid_id(e->>key,256,1024) THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        END LOOP;
        IF (e->>'image_file_id' IS NOT NULL AND NOT platform.messaging_valid_id(e->>'image_file_id',1024,4096)) OR
           (e->>'text' IS NOT NULL AND (char_length(e->>'text')>4096 OR octet_length(e->>'text')>16384)) THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        normalized:=e;
        IF e->>'occurred_at' IS NOT NULL THEN
          -- Reject relative PostgreSQL timestamps: fingerprint bytes cannot depend on DB time.
          IF e->>'occurred_at' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}[.][0-9]{6}Z$' THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
          BEGIN occurred:=(e->>'occurred_at')::timestamptz;
          EXCEPTION WHEN OTHERS THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END;
          IF NOT isfinite(occurred) OR to_char(occurred AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"') IS DISTINCT FROM e->>'occurred_at' THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        END IF;
        IF e->>'kind'='CLIENT_MESSAGE' AND (e->>'chat_id' IS NULL OR e->>'message_id' IS NULL OR e->>'sender_id' IS NULL OR occurred IS NULL OR
          (coalesce(char_length(e->>'text'),0)=0 AND e->>'image_file_id' IS NULL)) THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        RETURN normalized;
      END $$""",
    "messaging_reschedule": r"""CREATE FUNCTION platform.messaging_reschedule(p_job uuid,p_error text,p_retry boolean) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE j platform.messaging_jobs%ROWTYPE; retry boolean; final_error text; delivery text;
      BEGIN
        SELECT * INTO STRICT j FROM platform.messaging_jobs WHERE id=p_job FOR UPDATE;
        retry:=p_retry AND j.attempt_count<5 AND clock_timestamp()<j.first_started_at+interval '15 minutes';
        final_error:=CASE WHEN p_retry AND NOT retry THEN 'RETRY_EXHAUSTED' ELSE p_error END;
        UPDATE platform.messaging_jobs SET status=CASE WHEN retry THEN 'READY' ELSE 'DEAD' END,
          claim_token=NULL,lease_until=NULL,worker_id=NULL,error_code=final_error,
          available_at=clock_timestamp()+make_interval(secs=>random()*least(60.0,power(2.0,greatest(j.attempt_count-1,0)))),
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
    "messaging_ingest": r"""CREATE FUNCTION platform.messaging_ingest(p_provider text,p_bot text,p_event jsonb,p_correlation uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE e jsonb; route platform.channel_routes%ROWTYPE; c app.channel_connections%ROWTYPE;
        inbox platform.inbox_events%ROWTYPE; fingerprint bytea; job uuid; fresh boolean;
      BEGIN
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
    "messaging_claim": r"""CREATE FUNCTION platform.messaging_claim(p_worker text) RETURNS jsonb
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
            last_attempt_id=NULL,last_claim_token=NULL,last_outcome=NULL,last_provider_message_id=NULL,last_error_code=NULL,version=version+1
            WHERE id=j.id RETURNING * INTO j;
          RETURN platform.messaging_job_json(j);
        END LOOP;
      END $$""",
    "messaging_process_inbox": r"""CREATE FUNCTION platform.messaging_process_inbox(p_job uuid,p_claim uuid) RETURNS jsonb
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
        IF state='PROCESSED' AND msg.content_type='IMAGE_REFERENCE' THEN
          PERFORM platform.files_plan(j.workspace_id,msg.id,j.correlation_id);
        END IF;
        PERFORM platform.messaging_guard(p_job,p_claim);
        UPDATE platform.inbox_events SET status=state,result_code=code,message_id=msg.id,completed_at=clock_timestamp(),version=version+1 WHERE workspace_id=j.workspace_id AND id=inbox.id;
        UPDATE platform.messaging_jobs SET status=CASE WHEN state='FAILED' THEN 'DEAD' ELSE 'SUCCEEDED' END,error_code=CASE WHEN state='FAILED' THEN code END,
          claim_token=NULL,lease_until=NULL,worker_id=NULL,completed_at=clock_timestamp(),version=version+1 WHERE id=j.id;
        RETURN jsonb_build_object('code',code,'inbox_id',inbox.id,'message_id',msg.id,'status',state);
      END $$""",
    "messaging_request_text": r"""CREATE FUNCTION platform.messaging_request_text(p_conversation uuid,p_text text,p_key text) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE ws uuid; actor uuid; corr uuid; fingerprint bytea; rec platform.messaging_command_receipts%ROWTYPE;
        conv app.conversations%ROWTYPE; conn app.channel_connections%ROWTYPE; business_status text;
        message uuid; outbox uuid; audit uuid; replay boolean:=false; whitespace text;
      BEGIN
        ws:=app.current_messaging_owner_workspace_id();
        IF ws IS NULL THEN RAISE EXCEPTION 'ACCESS_DENIED' USING ERRCODE='P2001'; END IF;
        actor:=nullif(current_setting('asm.actor_id',true),'')::uuid; corr:=nullif(current_setting('asm.correlation_id',true),'')::uuid;
        IF corr IS NULL OR platform.messaging_lock_owner(ws,actor) IS NOT TRUE THEN RAISE EXCEPTION 'ACCESS_DENIED' USING ERRCODE='P2001'; END IF;
        -- Exact Python str.isspace set for Unicode scalar values, including U+001C..001F.
        whitespace:=chr(9)||chr(10)||chr(11)||chr(12)||chr(13)||chr(28)||chr(29)||chr(30)||chr(31)||chr(32)||chr(133)||chr(160)||chr(5760)||chr(8192)||chr(8193)||chr(8194)||chr(8195)||chr(8196)||chr(8197)||chr(8198)||chr(8199)||chr(8200)||chr(8201)||chr(8202)||chr(8232)||chr(8233)||chr(8239)||chr(8287)||chr(12288);
        IF p_conversation IS NULL OR p_text IS NULL OR char_length(p_text) NOT BETWEEN 1 AND 4096 OR octet_length(p_text)>16384 OR btrim(p_text,whitespace)='' OR p_key IS NULL OR p_key !~ '^[A-Za-z0-9._:-]{1,128}$' THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        fingerprint:=sha256(convert_to(E'asm:m2:send_manual_text:v1\n'||ws::text||E'\n'||actor::text||E'\n'||p_conversation::text||E'\n'||p_text,'UTF8'));
        PERFORM pg_advisory_xact_lock(hashtextextended(ws::text||':'||p_key,2006));
        SELECT * INTO rec FROM platform.messaging_command_receipts WHERE workspace_id=ws AND operation='SEND_MANUAL_TEXT' AND idempotency_key=p_key;
        IF FOUND THEN
          IF rec.request_fingerprint<>fingerprint THEN RAISE EXCEPTION 'IDEMPOTENCY_KEY_CONFLICT' USING ERRCODE='P2001'; END IF;
          replay:=true;
        ELSE
          SELECT * INTO conv FROM app.conversations WHERE workspace_id=ws AND id=p_conversation;
          IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P2001'; END IF;
          SELECT status INTO business_status FROM app.businesses WHERE workspace_id=ws AND id=conv.business_id FOR SHARE;
          SELECT * INTO STRICT conn FROM app.channel_connections WHERE workspace_id=ws AND id=conv.connection_id FOR SHARE;
          IF business_status<>'ACTIVE' OR conn.status<>'ACTIVE' THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
          INSERT INTO app.messages(workspace_id,conversation_id,connection_id,provider_chat_id,direction,content_type,text,occurred_at)
          VALUES(ws,conv.id,conn.id,conv.provider_chat_id,'OUTBOUND','TEXT',p_text,clock_timestamp()) RETURNING id INTO message;
          INSERT INTO app.outbox_events(workspace_id,connection_id,message_id) VALUES(ws,conn.id,message) RETURNING id INTO outbox;
          INSERT INTO app.audit_events(workspace_id,actor_kind,actor_user_account_id,correlation_id,event_type,object_type,object_id,object_version,payload)
          VALUES(ws,'USER_ACCOUNT',actor,corr,'MESSAGE_SEND_REQUESTED','MESSAGE',message,1,'{"content_type":"TEXT"}') RETURNING audit_event_id INTO audit;
          INSERT INTO platform.messaging_command_receipts(workspace_id,idempotency_key,request_fingerprint,actor_user_account_id,correlation_id,message_id,outbox_id,audit_event_id)
          VALUES(ws,p_key,fingerprint,actor,corr,message,outbox,audit) RETURNING * INTO rec;
          INSERT INTO platform.messaging_jobs(workspace_id,connection_id,kind,outbox_id,correlation_id) VALUES(ws,conn.id,'SEND_MANUAL_TEXT',outbox,corr);
        END IF;
        RETURN jsonb_build_object('code',CASE WHEN replay THEN 'REPLAY' ELSE 'ACCEPTED' END,'workspace_id',ws,'receipt_id',rec.id,'message_id',rec.message_id,'outbox_id',rec.outbox_id,'audit_event_id',rec.audit_event_id,'accepted_at',rec.accepted_at,'request_fingerprint',encode(rec.request_fingerprint,'hex'));
      END $$""",
    "messaging_begin_send": r"""CREATE FUNCTION platform.messaging_begin_send(p_job uuid,p_claim uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE j platform.messaging_jobs%ROWTYPE; box app.outbox_events%ROWTYPE; rec platform.messaging_command_receipts%ROWTYPE;
        msg app.messages%ROWTYPE; conn app.channel_connections%ROWTYPE; business_status text; allowed boolean; attempt uuid;
      BEGIN
        j:=platform.messaging_guard(p_job,p_claim);
        IF j.kind<>'SEND_MANUAL_TEXT' THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        SELECT * INTO STRICT box FROM app.outbox_events WHERE workspace_id=j.workspace_id AND id=j.outbox_id FOR UPDATE;
        IF box.status<>'PENDING' THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
        SELECT * INTO STRICT rec FROM platform.messaging_command_receipts WHERE workspace_id=j.workspace_id AND outbox_id=box.id;
        SELECT * INTO STRICT msg FROM app.messages WHERE workspace_id=j.workspace_id AND id=box.message_id;
        allowed:=platform.messaging_lock_owner(j.workspace_id,rec.actor_user_account_id);
        SELECT * INTO STRICT conn FROM app.channel_connections WHERE workspace_id=j.workspace_id AND id=j.connection_id;
        SELECT status INTO business_status FROM app.businesses WHERE workspace_id=j.workspace_id AND id=conn.business_id FOR SHARE;
        SELECT * INTO STRICT conn FROM app.channel_connections WHERE workspace_id=j.workspace_id AND id=j.connection_id FOR SHARE;
        IF allowed IS NOT TRUE OR business_status<>'ACTIVE' OR conn.status<>'ACTIVE' THEN
          PERFORM platform.messaging_reschedule(j.id,'NOT_ALLOWED',false);
          RETURN jsonb_build_object('code','NOT_ALLOWED','status','FAILED');
        END IF;
        PERFORM platform.messaging_guard(p_job,p_claim);
        attempt:=gen_random_uuid();
        UPDATE app.outbox_events SET status='DISPATCHING',attempt_id=attempt,error_code=NULL,version=version+1 WHERE workspace_id=j.workspace_id AND id=box.id;
        -- Clear any older definite NOT_SENT receipt when the next attempt starts.
        UPDATE platform.messaging_jobs SET last_attempt_id=NULL,last_claim_token=NULL,last_outcome=NULL,last_provider_message_id=NULL,last_error_code=NULL,version=version+1 WHERE id=j.id;
        RETURN jsonb_build_object('code','PERMITTED','job_id',j.id,'claim_token',p_claim,'attempt_id',attempt,'workspace_id',j.workspace_id,'connection_id',j.connection_id,'provider',conn.provider,'bot_identity',conn.bot_identity,'external_connection_id',conn.external_connection_id,'chat_id',msg.provider_chat_id,'text',msg.text);
      END $$""",
    "messaging_finish_send": r"""CREATE FUNCTION platform.messaging_finish_send(p_job uuid,p_claim uuid,p_attempt uuid,p_outcome text,p_provider_message text,p_error text) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE j platform.messaging_jobs%ROWTYPE; box app.outbox_events%ROWTYPE; result jsonb; state text;
      BEGIN
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
           j.last_provider_message_id IS NOT DISTINCT FROM p_provider_message AND j.last_error_code IS NOT DISTINCT FROM p_error AND box.attempt_id=p_attempt THEN
          RETURN jsonb_build_object('code','ALREADY_FINALIZED','status',box.status,'job_id',j.id,'outbox_id',box.id,'attempt_id',p_attempt);
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
          result:=platform.messaging_reschedule(j.id,p_error,p_outcome='NOT_SENT_RETRYABLE');
          state:=result->>'status';
        END IF;
        UPDATE platform.messaging_jobs SET last_attempt_id=p_attempt,last_claim_token=p_claim,last_outcome=p_outcome,last_provider_message_id=p_provider_message,last_error_code=p_error WHERE id=j.id;
        RETURN jsonb_build_object('code','FINALIZED','status',state,'job_id',j.id,'outbox_id',box.id,'attempt_id',p_attempt);
      END $$""",
}

PUBLIC_FUNCTIONS = (
    "platform.telegram_ingest(text,jsonb,uuid)",
    "platform.messaging_prepare_text(uuid,text,text)",
    "platform.telegram_owner_observe(uuid,bigint,bigint,jsonb)",
    "platform.telegram_worker_probe(uuid,uuid)",
    "platform.telegram_begin_send(uuid,uuid,bigint,bigint,jsonb)",
    "platform.messaging_lock_billing()",
    "platform.messaging_read_connections(integer,timestamp with time zone,uuid)",
    "platform.messaging_read_conversations(integer,timestamp with time zone,uuid)",
    "platform.messaging_read_messages(uuid,integer,timestamp with time zone,uuid)",
    "platform.messaging_finish_send(uuid,uuid,uuid,text,text,text,integer)",
)
PRIVATE_FUNCTIONS = (
    "platform.telegram_numeric_id(text)",
    "platform.telegram_validate_projection(text,jsonb)",
    "platform.telegram_fingerprint(text,jsonb)",
    "platform.telegram_validate_observation(jsonb)",
    "platform.telegram_probe_json(platform.telegram_connection_state)",
    "platform.telegram_save_observation(uuid,uuid,bigint,bigint,jsonb)",
    "platform.telegram_can_send(uuid,uuid,uuid,boolean)",
    "platform.messaging_lock_billing_workspace(uuid)",
    "platform.messaging_manual_send_allowed(uuid)",
    "platform.messaging_reschedule(uuid,text,boolean,integer)",
    "platform.initialize_telegram_connection(uuid,uuid,text,text,text,jsonb)",
    "platform.initialize_local_messaging_billing(uuid,text,timestamp with time zone,timestamp with time zone)",
)
TABLES = ("platform.telegram_connection_state", "platform.telegram_update_receipts")


def _replace(name: str, *changes: tuple[str, str]) -> None:
    sql = ORIGINAL[name].replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
    for before, after in changes:
        assert before in sql, (name, before)
        sql = sql.replace(before, after)
    op.execute(sql)


def upgrade() -> None:
    _validation()
    _schema()
    _billing()
    _observations()
    _ingress()
    _owner()
    _worker()
    _retry()
    _reads()
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY telegram_migrator ON {table} TO asm_migrator USING(true) WITH CHECK(true)"
        )
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC,asm_runtime")
    for signature in (*PUBLIC_FUNCTIONS, *PRIVATE_FUNCTIONS):
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC,asm_runtime")
    for signature in PUBLIC_FUNCTIONS:
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO asm_runtime")


def _validation() -> None:
    op.execute(r"""CREATE FUNCTION platform.telegram_numeric_id(value text) RETURNS boolean
      LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $$
      SELECT value IS NOT NULL AND value ~ '^[1-9][0-9]{0,18}$' AND
        CASE WHEN value ~ '^[1-9][0-9]{0,18}$' THEN value::numeric<=9223372036854775807 ELSE false END $$""")
    _replace(
        "messaging_validate_event",
        (
            "e->>'provider' IS DISTINCT FROM 'CONTROLLED'",
            "(e->>'provider' IS NULL OR e->>'provider' NOT IN ('CONTROLLED','TELEGRAM'))",
        ),
    )
    op.execute(r"""CREATE FUNCTION platform.telegram_validate_projection(bot text,p jsonb) RETURNS jsonb
      LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
      DECLARE key text; e jsonb; ids jsonb; moment timestamptz;
        fields constant text[]:=ARRAY['update_id','kind','external_connection_id','event','owner_user_id','deleted_message_ids','deleted_chat_id','sender_business_bot_id','is_enabled','can_reply','lifecycle_date'];
      BEGIN
        IF NOT platform.telegram_numeric_id(bot) OR p IS NULL OR jsonb_typeof(p)<>'object' OR octet_length(p::text)>65536 OR
          (SELECT count(*) FROM jsonb_object_keys(p))<>11 OR NOT p ?& fields THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        FOREACH key IN ARRAY ARRAY['update_id','kind','external_connection_id','owner_user_id','deleted_chat_id','sender_business_bot_id','lifecycle_date'] LOOP
          IF jsonb_typeof(p->key) NOT IN ('string','null') THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        END LOOP;
        IF NOT platform.telegram_numeric_id(p->>'update_id') OR p->>'kind' IS NULL OR p->>'kind' NOT IN ('BUSINESS_MESSAGE','BUSINESS_CONNECTION','EDITED_BUSINESS_MESSAGE','DELETED_BUSINESS_MESSAGES','UNSUPPORTED') THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        FOREACH key IN ARRAY ARRAY['owner_user_id','sender_business_bot_id','deleted_chat_id'] LOOP
          IF p->>key IS NOT NULL AND NOT platform.telegram_numeric_id(p->>key) THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        END LOOP;
        IF p->>'external_connection_id' IS NOT NULL AND NOT platform.messaging_valid_id(p->>'external_connection_id',256,1024) THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        FOREACH key IN ARRAY ARRAY['is_enabled','can_reply'] LOOP
          IF jsonb_typeof(p->key) NOT IN ('boolean','null') THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        END LOOP;
        IF p->>'kind'<>'UNSUPPORTED' AND p->>'external_connection_id' IS NULL THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        IF p->>'kind' IN ('BUSINESS_MESSAGE','EDITED_BUSINESS_MESSAGE') THEN
          e:=platform.messaging_validate_event(p->'event');
          IF e->>'provider' IS DISTINCT FROM 'TELEGRAM' OR e->>'bot_identity' IS DISTINCT FROM bot OR e->>'event_id' IS DISTINCT FROM p->>'update_id' OR e->>'external_connection_id' IS DISTINCT FROM p->>'external_connection_id' THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
          FOREACH key IN ARRAY ARRAY['chat_id','message_id','sender_id'] LOOP
            IF e->>key IS NOT NULL AND NOT platform.telegram_numeric_id(e->>key) THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
          END LOOP;
          IF p->>'kind'='BUSINESS_MESSAGE' AND e->>'kind' NOT IN ('CLIENT_MESSAGE','UNSUPPORTED') THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
          IF p->>'kind'='EDITED_BUSINESS_MESSAGE' AND e->>'kind' NOT IN ('MESSAGE_EDITED','UNSUPPORTED') THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
          IF e->>'kind'='CLIENT_MESSAGE' AND e->>'sender_id' IS DISTINCT FROM e->>'chat_id' THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        ELSIF p->'event'<>'null'::jsonb THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        IF p->>'kind'='BUSINESS_CONNECTION' THEN
          IF p->>'owner_user_id' IS NULL OR p->>'is_enabled' IS NULL OR p->>'can_reply' IS NULL OR
            p->>'lifecycle_date' IS NULL OR p->>'lifecycle_date' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}[.][0-9]{6}Z$' THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
          BEGIN moment:=(p->>'lifecycle_date')::timestamptz;
          EXCEPTION WHEN OTHERS THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END;
          IF NOT isfinite(moment) OR to_char(moment AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"') IS DISTINCT FROM p->>'lifecycle_date' THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        ELSIF p->>'owner_user_id' IS NOT NULL OR p->>'is_enabled' IS NOT NULL OR p->>'can_reply' IS NOT NULL OR p->>'lifecycle_date' IS NOT NULL THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        IF p->>'kind'='DELETED_BUSINESS_MESSAGES' THEN
          ids:=p->'deleted_message_ids';
          IF p->>'deleted_chat_id' IS NULL OR jsonb_typeof(ids)<>'array' OR jsonb_array_length(ids) NOT BETWEEN 1 AND 1000 THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
          IF EXISTS(SELECT 1 FROM jsonb_array_elements(ids) AS a(value) WHERE jsonb_typeof(value)<>'string' OR NOT platform.telegram_numeric_id(value#>>'{}')) THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        ELSIF p->'deleted_message_ids'<>'null'::jsonb OR p->>'deleted_chat_id' IS NOT NULL THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        IF p->>'kind' NOT IN ('BUSINESS_MESSAGE','EDITED_BUSINESS_MESSAGE') AND p->>'sender_business_bot_id' IS NOT NULL THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        RETURN p;
      END $$""")
    op.execute(r"""CREATE FUNCTION platform.telegram_fingerprint(bot text,p jsonb) RETURNS bytea
      LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $$
      DECLARE encoded bytea:=convert_to(E'asm:m2:telegram_update:v1\n','UTF8'); value text; scalar_values text[]; deleted text;
      BEGIN
        IF p->'deleted_message_ids'<>'null'::jsonb THEN
          SELECT string_agg(v,',' ORDER BY ord) INTO deleted FROM jsonb_array_elements_text(p->'deleted_message_ids') WITH ORDINALITY a(v,ord);
          deleted:=coalesce(deleted,'');
        END IF;
        scalar_values:=ARRAY[bot,p->>'update_id',p->>'kind',p->>'external_connection_id',p->>'owner_user_id',p->>'sender_business_bot_id',p->>'is_enabled',p->>'can_reply',p->>'lifecycle_date',CASE WHEN p->'event'<>'null'::jsonb THEN encode(platform.messaging_fingerprint(p->'event',false),'hex') END,p->>'deleted_chat_id',deleted];
        FOREACH value IN ARRAY scalar_values LOOP
          IF value IS NULL THEN encoded:=encoded||convert_to(E'-1:\n','UTF8');
          ELSE encoded:=encoded||convert_to(octet_length(value)::text||':'||value||E'\n','UTF8'); END IF;
        END LOOP;
        RETURN sha256(encoded);
      END $$""")
    op.execute("""CREATE FUNCTION platform.telegram_validate_observation(o jsonb) RETURNS void
      LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
      DECLARE key text;
      BEGIN
        IF o IS NULL OR jsonb_typeof(o)<>'object' OR (SELECT count(*) FROM jsonb_object_keys(o))<>6 OR
          NOT o ?& ARRAY['bot_identity','external_connection_id','owner_user_id','is_enabled','can_reply','error_code'] THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        FOREACH key IN ARRAY ARRAY['bot_identity','external_connection_id','owner_user_id','error_code'] LOOP
          IF jsonb_typeof(o->key) NOT IN ('string','null') THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        END LOOP;
        FOREACH key IN ARRAY ARRAY['is_enabled','can_reply'] LOOP
          IF jsonb_typeof(o->key) NOT IN ('boolean','null') THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        END LOOP;
        IF o->>'error_code' IS NULL THEN
          IF NOT platform.telegram_numeric_id(o->>'bot_identity') OR NOT platform.telegram_numeric_id(o->>'owner_user_id') OR NOT platform.messaging_valid_id(o->>'external_connection_id',256,1024) OR o->>'is_enabled' IS NULL OR o->>'can_reply' IS NULL THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        ELSIF o->>'error_code' NOT IN ('DEPENDENCY_TIMEOUT','DEPENDENCY_UNAVAILABLE','NOT_ALLOWED','INVALID_INPUT') OR
          o->>'bot_identity' IS NOT NULL OR o->>'owner_user_id' IS NOT NULL OR o->>'external_connection_id' IS NOT NULL OR o->>'is_enabled' IS NOT NULL OR o->>'can_reply' IS NOT NULL THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
      END $$""")


def _schema() -> None:
    for table in ("app.channel_connections", "app.client_identities"):
        op.execute(
            f"ALTER TABLE {table} DROP CONSTRAINT {table.split('.')[1]}_provider_check, ADD CONSTRAINT {table.split('.')[1]}_provider_check CHECK(provider IN ('CONTROLLED','TELEGRAM'))"
        )
    op.execute(
        "ALTER TABLE app.channel_connections ADD CONSTRAINT channel_connections_telegram_bot_check CHECK(provider<>'TELEGRAM' OR platform.telegram_numeric_id(bot_identity))"
    )
    op.execute(
        "ALTER TABLE app.client_identities ADD CONSTRAINT client_identities_telegram_user_check CHECK(provider<>'TELEGRAM' OR platform.telegram_numeric_id(external_user_id))"
    )
    op.execute(
        "ALTER TABLE app.conversations ADD COLUMN last_client_inbound_at timestamptz CHECK(isfinite(last_client_inbound_at))"
    )
    op.execute("""ALTER TABLE platform.messaging_jobs
      ADD COLUMN last_retry_after_seconds integer CHECK(last_retry_after_seconds BETWEEN 1 AND 86400),
      ADD COLUMN last_retry_due timestamptz CHECK(isfinite(last_retry_due)),
      ADD COLUMN telegram_probe_claim uuid,
      ADD COLUMN telegram_probe_generation bigint CHECK(telegram_probe_generation>0),
      ADD COLUMN telegram_probe_version bigint CHECK(telegram_probe_version>0),
      ADD CONSTRAINT messaging_jobs_telegram_probe_check CHECK(
        (telegram_probe_claim IS NULL AND telegram_probe_generation IS NULL AND telegram_probe_version IS NULL) OR
        (kind='SEND_MANUAL_TEXT' AND telegram_probe_claim IS NOT NULL AND telegram_probe_generation IS NOT NULL AND telegram_probe_version IS NOT NULL)),
      ADD CONSTRAINT messaging_jobs_retry_delay_check CHECK(
        (last_retry_after_seconds IS NULL AND last_retry_due IS NULL) OR
        (last_retry_after_seconds IS NOT NULL AND last_retry_due IS NOT NULL AND last_outcome IS NOT NULL AND last_outcome='NOT_SENT_RETRYABLE'))""")
    op.execute("""CREATE TABLE platform.telegram_connection_state(
      workspace_id uuid NOT NULL,connection_id uuid NOT NULL,
      provider text NOT NULL DEFAULT 'TELEGRAM' CHECK(provider='TELEGRAM'),bot_identity text NOT NULL,
      external_connection_id text NOT NULL,owner_user_id text NOT NULL CHECK(platform.telegram_numeric_id(owner_user_id)),
      generation bigint NOT NULL DEFAULT 1 CHECK(generation>0),observation_version bigint NOT NULL DEFAULT 1 CHECK(observation_version>0),
      observed_generation bigint CHECK(observed_generation>0),observed_at timestamptz CHECK(isfinite(observed_at)),observation_xid xid8,
      is_enabled boolean,can_reply boolean,error_code text CHECK(error_code IN ('DEPENDENCY_TIMEOUT','DEPENDENCY_UNAVAILABLE','NOT_ALLOWED','INVALID_INPUT')),
      PRIMARY KEY(workspace_id,connection_id),UNIQUE(workspace_id,connection_id,bot_identity),
      FOREIGN KEY(workspace_id,connection_id,provider,bot_identity,external_connection_id) REFERENCES app.channel_connections(workspace_id,id,provider,bot_identity,external_connection_id) ON DELETE RESTRICT,
      CHECK((observed_at IS NULL AND observed_generation IS NULL AND observation_xid IS NULL AND is_enabled IS NULL AND can_reply IS NULL AND error_code IS NULL) OR
        (observed_at IS NOT NULL AND observed_generation IS NOT NULL AND observation_xid IS NOT NULL AND
          ((error_code IS NULL AND is_enabled IS NOT NULL AND can_reply IS NOT NULL) OR (error_code IS NOT NULL AND is_enabled IS NULL AND can_reply IS NULL)))))""")
    op.execute(
        """CREATE TRIGGER telegram_state_immutable BEFORE UPDATE ON platform.telegram_connection_state FOR EACH ROW EXECUTE FUNCTION platform.messaging_immutable('workspace_id','connection_id','provider','bot_identity','external_connection_id','owner_user_id')"""
    )
    op.execute("""CREATE TABLE platform.telegram_update_receipts(
      id uuid PRIMARY KEY DEFAULT uuidv7(),bot_identity text NOT NULL CHECK(platform.telegram_numeric_id(bot_identity)),
      update_id text NOT NULL CHECK(platform.telegram_numeric_id(update_id)),fingerprint bytea NOT NULL CHECK(octet_length(fingerprint)=32),
      kind text NOT NULL CHECK(kind IN ('BUSINESS_MESSAGE','BUSINESS_CONNECTION','EDITED_BUSINESS_MESSAGE','DELETED_BUSINESS_MESSAGES','UNSUPPORTED')),
      result_code text NOT NULL CHECK(result_code IN ('QUEUED','LIFECYCLE_INVALIDATED','IGNORED_NATIVE_OWNER_MESSAGE','IGNORED_ECHO','IGNORED_MESSAGE_EDITED','IGNORED_MESSAGE_DELETED','IGNORED_UNSUPPORTED')),
      workspace_id uuid,connection_id uuid,inbox_id uuid,
      received_at timestamptz NOT NULL DEFAULT clock_timestamp() CHECK(isfinite(received_at)),
      UNIQUE(bot_identity,update_id),
      FOREIGN KEY(workspace_id,connection_id,bot_identity) REFERENCES platform.telegram_connection_state(workspace_id,connection_id,bot_identity) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,inbox_id,connection_id) REFERENCES platform.inbox_events(workspace_id,id,connection_id) ON DELETE RESTRICT,
      CHECK((workspace_id IS NULL AND connection_id IS NULL AND inbox_id IS NULL AND kind='UNSUPPORTED' AND result_code='IGNORED_UNSUPPORTED') OR
        (workspace_id IS NOT NULL AND connection_id IS NOT NULL AND
          ((result_code='QUEUED' AND kind='BUSINESS_MESSAGE' AND inbox_id IS NOT NULL) OR (result_code<>'QUEUED' AND inbox_id IS NULL)))))""")
    op.execute(
        """CREATE TRIGGER telegram_receipt_immutable BEFORE UPDATE ON platform.telegram_update_receipts FOR EACH ROW EXECUTE FUNCTION platform.messaging_immutable('id','bot_identity','update_id','fingerprint','kind','result_code','workspace_id','connection_id','inbox_id','received_at')"""
    )


def _billing() -> None:
    op.execute("""CREATE FUNCTION platform.messaging_lock_billing_workspace(ws uuid) RETURNS void
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      BEGIN
        PERFORM 1 FROM platform.workspace_billing_accounts WHERE workspace_id=ws FOR SHARE;
        PERFORM 1 FROM platform.workspace_service_modes WHERE workspace_id=ws FOR SHARE;
        PERFORM 1 FROM platform.workspace_subscriptions WHERE workspace_id=ws ORDER BY subscription_id FOR SHARE;
        PERFORM 1 FROM platform.saas_plan_revisions WHERE plan_revision_id IN (SELECT plan_revision_id FROM platform.workspace_subscriptions WHERE workspace_id=ws) ORDER BY plan_revision_id FOR SHARE;
        PERFORM 1 FROM platform.saas_plans WHERE plan_id IN (SELECT r.plan_id FROM platform.saas_plan_revisions r JOIN platform.workspace_subscriptions s USING(plan_revision_id) WHERE s.workspace_id=ws) ORDER BY plan_id FOR SHARE;
        PERFORM 1 FROM platform.plan_entitlements WHERE plan_revision_id IN (SELECT plan_revision_id FROM platform.workspace_subscriptions WHERE workspace_id=ws) ORDER BY plan_revision_id,capability_key FOR SHARE;
      END $$""")
    op.execute("""CREATE FUNCTION platform.messaging_lock_billing() RETURNS void
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE ws uuid;
      BEGIN
        ws:=app.current_messaging_owner_workspace_id();
        IF ws IS NULL OR platform.messaging_lock_owner(ws,nullif(current_setting('asm.actor_id',true),'')::uuid) IS NOT TRUE THEN RAISE EXCEPTION 'ACCESS_DENIED' USING ERRCODE='P2001'; END IF;
        PERFORM platform.messaging_lock_billing_workspace(ws);
      END $$""")
    op.execute("""CREATE FUNCTION platform.messaging_manual_send_allowed(ws uuid) RETURNS boolean
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE moment timestamptz:=clock_timestamp(); mode platform.workspace_service_modes%ROWTYPE;
        sub platform.workspace_subscriptions%ROWTYPE; ent platform.plan_entitlements%ROWTYPE;
      BEGIN
        PERFORM platform.messaging_lock_billing_workspace(ws);
        IF NOT EXISTS(SELECT 1 FROM platform.workspace_billing_accounts WHERE workspace_id=ws) OR
          NOT EXISTS(SELECT 1 FROM platform.workspace_service_modes WHERE workspace_id=ws) OR
          NOT EXISTS(SELECT 1 FROM platform.workspace_subscriptions WHERE workspace_id=ws) THEN
          RAISE EXCEPTION 'BILLING_STATE_UNAVAILABLE' USING ERRCODE='P2301',DETAIL='BILLING_STATE_MISSING'; END IF;
        IF EXISTS(SELECT 1 FROM platform.workspace_subscriptions s LEFT JOIN platform.saas_plan_revisions r USING(plan_revision_id) LEFT JOIN platform.saas_plans p USING(plan_id)
          WHERE s.workspace_id=ws AND (r.plan_revision_id IS NULL OR r.publication_state<>'SEALED' OR r.published_at IS NULL OR p.plan_id IS NULL)) THEN
          RAISE EXCEPTION 'BILLING_STATE_UNAVAILABLE' USING ERRCODE='P2301',DETAIL='REVISION_INVALID'; END IF;
        SELECT * INTO sub FROM platform.workspace_subscriptions WHERE workspace_id=ws AND effective_from<=moment AND moment<effective_until;
        IF NOT FOUND THEN RETURN false; END IF;
        SELECT * INTO STRICT mode FROM platform.workspace_service_modes WHERE workspace_id=ws;
        IF NOT (mode.effective_from<=moment AND (mode.effective_until IS NULL OR moment<mode.effective_until)) THEN RETURN false; END IF;
        SELECT * INTO ent FROM platform.plan_entitlements WHERE plan_revision_id=sub.plan_revision_id AND capability_key='messaging.manual_send';
        IF NOT FOUND THEN RETURN false; END IF;
        IF mode.mode='SUSPENDED' OR ent.criticality<>'ESSENTIAL' OR ent.value_kind<>'BOOLEAN' OR ent.enabled IS NOT TRUE OR ent.limit_value IS NOT NULL THEN RETURN false; END IF;
        RETURN true;
      END $$""")
    op.execute(r"""CREATE FUNCTION platform.initialize_local_messaging_billing(p_workspace uuid,p_contact text,p_from timestamptz,p_until timestamptz) RETURNS text
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE plan uuid; v_revision uuid; account platform.workspace_billing_accounts%ROWTYPE; manifest text; sub_count integer; mode_count integer; audit_count integer;
      BEGIN
        PERFORM pg_advisory_xact_lock(1295070019,1);
        IF p_workspace IS NULL OR p_contact IS NULL OR p_contact<>btrim(p_contact,' ') OR char_length(p_contact) NOT BETWEEN 1 AND 200 OR octet_length(p_contact)>800 OR p_contact ~ '[\x00-\x1F\x7F]' OR p_from IS NULL OR p_until IS NULL OR NOT isfinite(p_from) OR NOT isfinite(p_until) OR p_from>=p_until THEN RAISE EXCEPTION 'CONFLICT_INPUT_MISMATCH' USING ERRCODE='P1301'; END IF;
        PERFORM 1 FROM platform.workspaces WHERE id=p_workspace AND status='ACTIVE' FOR UPDATE;
        IF NOT FOUND THEN RAISE EXCEPTION 'CONFLICT_PARTIAL_STATE' USING ERRCODE='P1301'; END IF;
        SELECT plan_id INTO plan FROM platform.saas_plans WHERE code='test_messaging';
        IF NOT FOUND THEN
          INSERT INTO platform.saas_plans(code,display_name,status) VALUES('test_messaging','M2.3 TEST messaging','ACTIVE') RETURNING plan_id INTO plan;
          INSERT INTO platform.saas_plan_revisions(plan_id,revision,publication_state) VALUES(plan,1,'DRAFT') RETURNING plan_revision_id INTO v_revision;
          INSERT INTO platform.plan_entitlements(plan_revision_id,capability_key,value_kind,enabled,limit_value,criticality) VALUES(v_revision,'messaging.manual_send','BOOLEAN',true,NULL,'ESSENTIAL');
          UPDATE platform.saas_plan_revisions SET publication_state='SEALED',published_at=clock_timestamp() WHERE plan_revision_id=v_revision;
        ELSE
          SELECT r.plan_revision_id INTO v_revision FROM platform.saas_plan_revisions r WHERE r.plan_id=plan AND r.revision=1 AND r.publication_state='SEALED';
          IF v_revision IS NULL OR NOT EXISTS(SELECT 1 FROM platform.saas_plans WHERE plan_id=plan AND status='ACTIVE' AND display_name='M2.3 TEST messaging') OR
            (SELECT count(*) FROM platform.saas_plan_revisions WHERE plan_id=plan)<>1 THEN RAISE EXCEPTION 'CONFLICT_CATALOG_MISMATCH' USING ERRCODE='P1301'; END IF;
        END IF;
        SELECT string_agg(capability_key||chr(9)||value_kind||chr(9)||CASE WHEN value_kind='BOOLEAN' THEN enabled::text ELSE limit_value::text END||chr(9)||criticality||chr(10),'' ORDER BY convert_to(capability_key,'UTF8')) INTO manifest FROM platform.plan_entitlements WHERE plan_revision_id=v_revision;
        IF manifest IS DISTINCT FROM E'messaging.manual_send\tBOOLEAN\ttrue\tESSENTIAL\n' OR (SELECT count(*) FROM platform.plan_entitlements WHERE plan_revision_id=v_revision)<>1 THEN RAISE EXCEPTION 'CONFLICT_CATALOG_MISMATCH' USING ERRCODE='P1301'; END IF;
        SELECT * INTO account FROM platform.workspace_billing_accounts WHERE workspace_id=p_workspace FOR UPDATE;
        SELECT count(*) INTO sub_count FROM platform.workspace_subscriptions WHERE workspace_id=p_workspace;
        SELECT count(*) INTO mode_count FROM platform.workspace_service_modes WHERE workspace_id=p_workspace;
        SELECT count(*) INTO audit_count FROM app.audit_events WHERE workspace_id=p_workspace AND event_type='WORKSPACE_BILLING_PROVISIONED';
        IF account.workspace_id IS NOT NULL OR sub_count+mode_count+audit_count>0 THEN
          IF account.workspace_id IS NULL OR sub_count<>1 OR mode_count<>1 OR audit_count<>1 THEN RAISE EXCEPTION 'CONFLICT_PARTIAL_STATE' USING ERRCODE='P1301'; END IF;
          IF account.contact_display_name<>p_contact OR account.version<>1 OR NOT EXISTS(SELECT 1 FROM platform.workspace_subscriptions WHERE workspace_id=p_workspace AND plan_revision_id=v_revision AND status='ACTIVE' AND funding_mode='COMPED' AND effective_from=p_from AND effective_until=p_until AND version=1) OR
            NOT EXISTS(SELECT 1 FROM platform.workspace_service_modes WHERE workspace_id=p_workspace AND mode='NORMAL' AND reason_code='PROVISIONED_LOCAL' AND effective_from=p_from AND effective_until=p_until AND version=1) OR
            NOT EXISTS(SELECT 1 FROM app.audit_events WHERE workspace_id=p_workspace AND event_type='WORKSPACE_BILLING_PROVISIONED' AND object_id=account.billing_account_id AND object_version=1) THEN RAISE EXCEPTION 'CONFLICT_STATE_DRIFT' USING ERRCODE='P1301'; END IF;
          RETURN 'NOOP';
        END IF;
        INSERT INTO platform.workspace_billing_accounts(workspace_id,contact_display_name) VALUES(p_workspace,p_contact) RETURNING * INTO account;
        INSERT INTO platform.workspace_subscriptions(workspace_id,plan_revision_id,required_publication_state,status,funding_mode,effective_from,effective_until) VALUES(p_workspace,v_revision,'SEALED','ACTIVE','COMPED',p_from,p_until);
        INSERT INTO platform.workspace_service_modes(workspace_id,mode,reason_code,effective_from,effective_until) VALUES(p_workspace,'NORMAL','PROVISIONED_LOCAL',p_from,p_until);
        INSERT INTO app.audit_events(workspace_id,actor_kind,correlation_id,event_type,object_type,object_id,object_version,payload) VALUES(p_workspace,'LOCAL_PROVISIONER',uuidv7(),'WORKSPACE_BILLING_PROVISIONED','WORKSPACE_BILLING_ACCOUNT',account.billing_account_id,1,'{}');
        RETURN 'CREATED';
      END $$""")


def _observations() -> None:
    op.execute("""CREATE FUNCTION platform.telegram_probe_json(s platform.telegram_connection_state) RETURNS jsonb
      LANGUAGE sql STABLE SET search_path=pg_catalog,pg_temp AS $$ SELECT jsonb_build_object(
        'workspace_id',s.workspace_id,'connection_id',s.connection_id,'bot_identity',s.bot_identity,
        'external_connection_id',s.external_connection_id,'owner_user_id',s.owner_user_id,
        'generation',s.generation,'observation_version',s.observation_version) $$""")
    op.execute("""CREATE FUNCTION platform.initialize_telegram_connection(p_workspace uuid,p_business uuid,p_bot text,p_external text,p_owner text,p_observation jsonb) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE conn app.channel_connections%ROWTYPE; state platform.telegram_connection_state%ROWTYPE;
      BEGIN
        PERFORM platform.telegram_validate_observation(p_observation);
        IF p_workspace IS NULL OR p_business IS NULL OR NOT platform.telegram_numeric_id(p_bot) OR NOT platform.telegram_numeric_id(p_owner) OR NOT platform.messaging_valid_id(p_external,256,1024) OR
          p_observation->>'error_code' IS NOT NULL OR p_observation->>'bot_identity' IS DISTINCT FROM p_bot OR p_observation->>'external_connection_id' IS DISTINCT FROM p_external OR p_observation->>'owner_user_id' IS DISTINCT FROM p_owner THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
        PERFORM 1 FROM platform.workspaces WHERE id=p_workspace AND status='ACTIVE' FOR SHARE;
        IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P2001'; END IF;
        PERFORM 1 FROM app.businesses WHERE workspace_id=p_workspace AND id=p_business AND status='ACTIVE' FOR SHARE;
        IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P2001'; END IF;
        PERFORM pg_advisory_xact_lock(hashtextextended(p_bot||':'||p_external,2007));
        SELECT * INTO conn FROM app.channel_connections WHERE provider='TELEGRAM' AND bot_identity=p_bot AND external_connection_id=p_external;
        IF FOUND THEN
          SELECT * INTO state FROM platform.telegram_connection_state WHERE workspace_id=conn.workspace_id AND connection_id=conn.id;
          IF conn.workspace_id<>p_workspace OR conn.business_id<>p_business OR state.owner_user_id IS DISTINCT FROM p_owner OR NOT EXISTS(SELECT 1 FROM platform.channel_routes WHERE workspace_id=p_workspace AND connection_id=conn.id AND provider='TELEGRAM' AND bot_identity=p_bot AND route_key=p_external) THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
          RETURN jsonb_build_object('code','NOOP','connection_id',conn.id);
        END IF;
        INSERT INTO app.channel_connections(workspace_id,business_id,provider,bot_identity,external_connection_id) VALUES(p_workspace,p_business,'TELEGRAM',p_bot,p_external) RETURNING * INTO conn;
        INSERT INTO platform.telegram_connection_state(workspace_id,connection_id,bot_identity,external_connection_id,owner_user_id,observed_generation,observed_at,observation_xid,is_enabled,can_reply)
          VALUES(p_workspace,conn.id,p_bot,p_external,p_owner,1,clock_timestamp(),pg_current_xact_id(),(p_observation->>'is_enabled')::boolean,(p_observation->>'can_reply')::boolean);
        INSERT INTO platform.channel_routes(workspace_id,connection_id,provider,bot_identity,route_key) VALUES(p_workspace,conn.id,'TELEGRAM',p_bot,p_external);
        RETURN jsonb_build_object('code','CREATED','connection_id',conn.id);
      END $$""")
    op.execute("""CREATE FUNCTION platform.telegram_save_observation(ws uuid,conn uuid,p_generation bigint,p_version bigint,o jsonb) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE s platform.telegram_connection_state%ROWTYPE; failure text;
      BEGIN
        PERFORM platform.telegram_validate_observation(o);
        SELECT * INTO STRICT s FROM platform.telegram_connection_state WHERE workspace_id=ws AND connection_id=conn FOR UPDATE;
        IF p_generation IS NULL OR p_version IS NULL OR s.generation<>p_generation OR s.observation_version<>p_version THEN
          RETURN jsonb_build_object('code','UNAVAILABLE','generation',s.generation,'observation_version',s.observation_version); END IF;
        failure:=o->>'error_code';
        IF failure IS NULL AND (o->>'bot_identity' IS DISTINCT FROM s.bot_identity OR o->>'external_connection_id' IS DISTINCT FROM s.external_connection_id OR o->>'owner_user_id' IS DISTINCT FROM s.owner_user_id) THEN failure:='NOT_ALLOWED'; END IF;
        UPDATE platform.telegram_connection_state SET observed_generation=generation,observed_at=clock_timestamp(),observation_xid=pg_current_xact_id(),observation_version=observation_version+1,
          is_enabled=CASE WHEN failure IS NULL THEN (o->>'is_enabled')::boolean END,
          can_reply=CASE WHEN failure IS NULL THEN (o->>'can_reply')::boolean END,error_code=failure
          WHERE workspace_id=ws AND connection_id=conn RETURNING * INTO s;
        RETURN jsonb_build_object('code',CASE WHEN failure IS NULL THEN 'OBSERVED' WHEN failure IN ('NOT_ALLOWED','INVALID_INPUT') THEN 'NOT_ALLOWED' ELSE 'UNAVAILABLE' END,'generation',s.generation,'observation_version',s.observation_version);
      END $$""")
    op.execute("""CREATE FUNCTION platform.telegram_can_send(ws uuid,conn uuid,conversation uuid,same_uow boolean) RETURNS boolean
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE s platform.telegram_connection_state%ROWTYPE; inbound timestamptz;
      BEGIN
        SELECT * INTO STRICT s FROM platform.telegram_connection_state WHERE workspace_id=ws AND connection_id=conn FOR SHARE;
        SELECT last_client_inbound_at INTO inbound FROM app.conversations WHERE workspace_id=ws AND id=conversation AND connection_id=conn;
        RETURN s.observed_generation=s.generation AND s.error_code IS NULL AND s.is_enabled IS TRUE AND s.can_reply IS TRUE AND
          s.observed_at>clock_timestamp()-interval '30 seconds' AND (NOT same_uow OR s.observation_xid=pg_current_xact_id()) AND
          inbound IS NOT NULL AND clock_timestamp()<inbound+interval '24 hours';
      END $$""")


def _ingress() -> None:
    # The former entrypoint remains CONTROLLED-only. TELEGRAM cannot evade receipts.
    _replace(
        "messaging_ingest",
        (
            "        e:=platform.messaging_validate_event(p_event);",
            """        IF p_provider IS DISTINCT FROM 'CONTROLLED' THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        e:=platform.messaging_validate_event(p_event);""",
        ),
    )
    op.execute("""CREATE FUNCTION platform.telegram_ingest(p_bot text,p_projection jsonb,p_correlation uuid) RETURNS jsonb
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
      END $$""")
    _replace(
        "messaging_process_inbox",
        (
            "        IF state='PROCESSED' AND msg.content_type='IMAGE_REFERENCE' THEN",
            """        IF code='PROCESSED' AND e->>'provider'='TELEGRAM' THEN
          UPDATE app.conversations SET last_client_inbound_at=greatest(last_client_inbound_at,least(msg.occurred_at,inbox.received_at)),version=version+1
            WHERE workspace_id=j.workspace_id AND id=msg.conversation_id;
        END IF;
        IF state='PROCESSED' AND msg.content_type='IMAGE_REFERENCE' THEN""",
        ),
    )


def _owner() -> None:
    # Preparation reuses the exact accepted body/key/fingerprint/admission prefix.
    prefix = ORIGINAL["messaging_request_text"].split("        IF FOUND THEN", 1)[0]
    prefix = prefix.replace("messaging_request_text", "messaging_prepare_text", 1)
    op.execute(
        prefix
        + """        IF FOUND THEN
          IF rec.request_fingerprint<>fingerprint THEN RAISE EXCEPTION 'IDEMPOTENCY_KEY_CONFLICT' USING ERRCODE='P2001'; END IF;
          RETURN jsonb_build_object('code','REPLAY','workspace_id',ws,'receipt_id',rec.id,'message_id',rec.message_id,'outbox_id',rec.outbox_id,'audit_event_id',rec.audit_event_id,'accepted_at',rec.accepted_at,'request_fingerprint',encode(rec.request_fingerprint,'hex'));
        END IF;
        SELECT * INTO conv FROM app.conversations WHERE workspace_id=ws AND id=p_conversation;
        IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P2001'; END IF;
        PERFORM 1 FROM app.businesses WHERE workspace_id=ws AND id=conv.business_id FOR SHARE;
        SELECT * INTO STRICT conn FROM app.channel_connections WHERE workspace_id=ws AND id=conv.connection_id FOR SHARE;
        RETURN jsonb_build_object('code','NEW','provider',conn.provider,'probe',
          CASE WHEN conn.provider='TELEGRAM' THEN (SELECT platform.telegram_probe_json(s) FROM platform.telegram_connection_state s WHERE s.workspace_id=ws AND s.connection_id=conn.id) END);
      END $$"""
    )
    op.execute("""CREATE FUNCTION platform.telegram_owner_observe(p_conversation uuid,p_generation bigint,p_observation_version bigint,p_observation jsonb) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE ws uuid; conv app.conversations%ROWTYPE; conn app.channel_connections%ROWTYPE; business_status text; result jsonb;
      BEGIN
        ws:=app.current_messaging_owner_workspace_id();
        IF ws IS NULL OR platform.messaging_lock_owner(ws,nullif(current_setting('asm.actor_id',true),'')::uuid) IS NOT TRUE THEN RAISE EXCEPTION 'ACCESS_DENIED' USING ERRCODE='P2001'; END IF;
        SELECT * INTO conv FROM app.conversations WHERE workspace_id=ws AND id=p_conversation;
        IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P2001'; END IF;
        SELECT status INTO business_status FROM app.businesses WHERE workspace_id=ws AND id=conv.business_id FOR SHARE;
        SELECT * INTO STRICT conn FROM app.channel_connections WHERE workspace_id=ws AND id=conv.connection_id FOR SHARE;
        IF conn.provider<>'TELEGRAM' THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        result:=platform.telegram_save_observation(ws,conn.id,p_generation,p_observation_version,p_observation);
        IF result->>'code'='OBSERVED' AND (business_status<>'ACTIVE' OR conn.status<>'ACTIVE' OR platform.telegram_can_send(ws,conn.id,conv.id,true) IS NOT TRUE) THEN
          result:=jsonb_set(result,'{code}','"NOT_ALLOWED"'); END IF;
        RETURN result;
      END $$""")
    _replace(
        "messaging_request_text",
        (
            "          INSERT INTO app.messages(workspace_id,conversation_id,connection_id,provider_chat_id,direction,content_type,text,occurred_at)",
            """          IF conn.provider='TELEGRAM' THEN
            IF platform.telegram_can_send(ws,conn.id,conv.id,true) IS NOT TRUE THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
            IF platform.messaging_manual_send_allowed(ws) IS NOT TRUE THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
          END IF;
          INSERT INTO app.messages(workspace_id,conversation_id,connection_id,provider_chat_id,direction,content_type,text,occurred_at)""",
        ),
    )


def _worker() -> None:
    op.execute("""CREATE FUNCTION platform.telegram_worker_probe(p_job uuid,p_claim uuid) RETURNS jsonb
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
      END $$""")
    # No caller may use the old entrypoint for Telegram, even after a cached refresh.
    _replace(
        "messaging_begin_send",
        (
            "        IF allowed IS NOT TRUE OR business_status<>'ACTIVE' OR conn.status<>'ACTIVE' THEN",
            """        IF conn.provider='TELEGRAM' THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
        IF allowed IS NOT TRUE OR business_status<>'ACTIVE' OR conn.status<>'ACTIVE' THEN""",
        ),
        (
            "last_provider_message_id=NULL,last_error_code=NULL,version=version+1",
            "last_provider_message_id=NULL,last_error_code=NULL,last_retry_after_seconds=NULL,last_retry_due=NULL,version=version+1",
        ),
    )
    source = ORIGINAL["messaging_begin_send"].replace(
        "platform.messaging_begin_send(p_job uuid,p_claim uuid)",
        "platform.telegram_begin_send(p_job uuid,p_claim uuid,p_generation bigint,p_observation_version bigint,p_observation jsonb)",
        1,
    )
    source = source.replace(
        "allowed boolean; attempt uuid;", "allowed boolean; attempt uuid; observation jsonb;"
    )
    source = source.replace(
        "        PERFORM platform.messaging_guard(p_job,p_claim);",
        """        IF conn.provider<>'TELEGRAM' THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        IF j.telegram_probe_claim IS DISTINCT FROM p_claim OR j.telegram_probe_generation IS DISTINCT FROM p_generation OR j.telegram_probe_version IS DISTINCT FROM p_observation_version THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
        observation:=platform.telegram_save_observation(j.workspace_id,j.connection_id,p_generation,p_observation_version,p_observation);
        IF observation->>'code'='UNAVAILABLE' THEN
          PERFORM platform.messaging_reschedule(j.id,'DEPENDENCY_UNAVAILABLE',true);
          RETURN jsonb_build_object('code','UNAVAILABLE','status',(SELECT status FROM app.outbox_events WHERE workspace_id=j.workspace_id AND id=box.id));
        END IF;
        IF observation->>'code'='NOT_ALLOWED' OR platform.telegram_can_send(j.workspace_id,j.connection_id,msg.conversation_id,true) IS NOT TRUE THEN
          PERFORM platform.messaging_reschedule(j.id,'NOT_ALLOWED',false);
          RETURN jsonb_build_object('code','NOT_ALLOWED','status','FAILED');
        END IF;
        BEGIN
          allowed:=platform.messaging_manual_send_allowed(j.workspace_id);
        EXCEPTION WHEN SQLSTATE 'P2301' THEN
          PERFORM platform.messaging_reschedule(j.id,'DEPENDENCY_UNAVAILABLE',true);
          RETURN jsonb_build_object('code','UNAVAILABLE','status',(SELECT status FROM app.outbox_events WHERE workspace_id=j.workspace_id AND id=box.id));
        END;
        IF allowed IS NOT TRUE THEN
          PERFORM platform.messaging_reschedule(j.id,'NOT_ALLOWED',false);
          RETURN jsonb_build_object('code','NOT_ALLOWED','status','FAILED');
        END IF;
        PERFORM platform.messaging_guard(p_job,p_claim);""",
    )
    source = source.replace(
        "last_provider_message_id=NULL,last_error_code=NULL,version=version+1",
        "last_provider_message_id=NULL,last_error_code=NULL,last_retry_after_seconds=NULL,last_retry_due=NULL,version=version+1",
    )
    op.execute(source)
    _replace(
        "messaging_claim",
        (
            "last_provider_message_id=NULL,last_error_code=NULL,version=version+1",
            "last_provider_message_id=NULL,last_error_code=NULL,last_retry_after_seconds=NULL,last_retry_due=NULL,telegram_probe_claim=NULL,telegram_probe_generation=NULL,telegram_probe_version=NULL,version=version+1",
        ),
    )


def _retry() -> None:
    sql = ORIGINAL["messaging_reschedule"].replace(
        "platform.messaging_reschedule(p_job uuid,p_error text,p_retry boolean)",
        "platform.messaging_reschedule(p_job uuid,p_error text,p_retry boolean,p_delay integer)",
        1,
    )
    sql = sql.replace("delivery text;", "delivery text; due timestamptz;")
    sql = sql.replace(
        "        retry:=p_retry",
        """        IF p_delay IS NOT NULL AND (p_delay NOT BETWEEN 1 AND 86400 OR p_retry IS NOT TRUE) THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        due:=clock_timestamp()+make_interval(secs=>random()*least(60.0,power(2.0,greatest(j.attempt_count-1,0))));
        IF p_delay IS NOT NULL THEN due:=greatest(due,clock_timestamp()+make_interval(secs=>p_delay)); END IF;
        retry:=p_retry""",
    )
    sql = sql.replace(
        "clock_timestamp()<j.first_started_at+interval '15 minutes';",
        "clock_timestamp()<j.first_started_at+interval '15 minutes' AND (p_delay IS NULL OR due<j.first_started_at+interval '15 minutes');",
    )
    sql = sql.replace(
        "available_at=clock_timestamp()+make_interval(secs=>random()*least(60.0,power(2.0,greatest(j.attempt_count-1,0)))),",
        "available_at=due,",
    )
    op.execute(sql)
    op.execute("""CREATE OR REPLACE FUNCTION platform.messaging_reschedule(p_job uuid,p_error text,p_retry boolean) RETURNS jsonb
      LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      SELECT platform.messaging_reschedule(p_job,p_error,p_retry,NULL::integer) $$""")
    sql = ORIGINAL["messaging_finish_send"].replace(
        "p_provider_message text,p_error text)",
        "p_provider_message text,p_error text,p_retry_after_seconds integer)",
        1,
    )
    sql = sql.replace(
        "        IF p_outcome IS NULL",
        """        IF p_retry_after_seconds IS NOT NULL AND (p_retry_after_seconds NOT BETWEEN 1 AND 86400 OR p_outcome IS DISTINCT FROM 'NOT_SENT_RETRYABLE') THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        IF p_outcome IS NULL""",
    )
    sql = sql.replace(
        "AND box.attempt_id=p_attempt THEN",
        "AND j.last_retry_after_seconds IS NOT DISTINCT FROM p_retry_after_seconds AND box.attempt_id=p_attempt THEN",
    )
    sql = sql.replace(
        "platform.messaging_reschedule(j.id,p_error,p_outcome='NOT_SENT_RETRYABLE')",
        "platform.messaging_reschedule(j.id,p_error,p_outcome='NOT_SENT_RETRYABLE',p_retry_after_seconds)",
    )
    sql = sql.replace(
        "last_error_code=p_error WHERE id=j.id;",
        "last_error_code=p_error,last_retry_after_seconds=p_retry_after_seconds,last_retry_due=CASE WHEN p_retry_after_seconds IS NOT NULL THEN available_at END WHERE id=j.id;",
    )
    sql = sql.replace(
        "'attempt_id',p_attempt);",
        """'attempt_id',p_attempt) || CASE WHEN p_retry_after_seconds IS NULL THEN '{}'::jsonb ELSE jsonb_build_object('retry_after_seconds',p_retry_after_seconds,'available_at',(SELECT last_retry_due FROM platform.messaging_jobs WHERE id=j.id)) END;""",
    )
    op.execute(sql)
    op.execute("""CREATE OR REPLACE FUNCTION platform.messaging_finish_send(p_job uuid,p_claim uuid,p_attempt uuid,p_outcome text,p_provider_message text,p_error text) RETURNS jsonb
      LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      SELECT platform.messaging_finish_send(p_job,p_claim,p_attempt,p_outcome,p_provider_message,p_error,NULL::integer) $$""")


def _reads() -> None:
    common = """        ws:=app.current_messaging_owner_workspace_id();
        IF ws IS NULL OR platform.messaging_lock_owner(ws,nullif(current_setting('asm.actor_id',true),'')::uuid) IS NOT TRUE THEN RAISE EXCEPTION 'ACCESS_DENIED' USING ERRCODE='P2001'; END IF;
        IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 101 OR (p_at IS NULL)<>(p_id IS NULL) OR (p_at IS NOT NULL AND NOT isfinite(p_at)) THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
"""
    op.execute(
        """CREATE FUNCTION platform.messaging_read_connections(p_limit integer,p_at timestamptz,p_id uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE ws uuid; result jsonb;
      BEGIN
"""
        + common
        + """        IF p_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM app.channel_connections WHERE workspace_id=ws AND id=p_id AND created_at=p_at) THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        SELECT coalesce(jsonb_agg(to_jsonb(items)),'[]'::jsonb) INTO result FROM
          (SELECT c.id AS connection_id,c.business_id,c.provider,
            CASE WHEN c.provider='CONTROLLED' THEN CASE WHEN c.status='ACTIVE' THEN 'AVAILABLE' ELSE 'DISABLED' END
              WHEN c.status<>'ACTIVE' THEN 'DISABLED'
              WHEN s.observed_at IS NULL OR s.observed_generation<>s.generation OR s.observed_at<=clock_timestamp()-interval '30 seconds' THEN 'UNVERIFIED'
              WHEN s.error_code IS NOT NULL THEN 'UNAVAILABLE'
              WHEN s.is_enabled IS NOT TRUE THEN 'DISABLED'
              WHEN s.can_reply IS NOT TRUE THEN 'RIGHTS_MISSING' ELSE 'AVAILABLE' END AS state,
            CASE WHEN c.provider='TELEGRAM' THEN s.observed_at END AS observed_at,c.created_at,
            CASE WHEN c.provider='TELEGRAM' THEN greatest(c.version,s.observation_version) ELSE c.version END::text AS version
            FROM app.channel_connections c LEFT JOIN platform.telegram_connection_state s ON s.workspace_id=c.workspace_id AND s.connection_id=c.id
            WHERE c.workspace_id=ws AND (p_id IS NULL OR (c.created_at,c.id)<(p_at,p_id)) ORDER BY c.created_at DESC,c.id DESC LIMIT p_limit) items;
        RETURN result;
      END $$"""
    )
    op.execute(
        """CREATE FUNCTION platform.messaging_read_conversations(p_limit integer,p_at timestamptz,p_id uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE ws uuid; result jsonb;
      BEGIN
"""
        + common
        + """        IF p_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM app.conversations WHERE workspace_id=ws AND id=p_id AND created_at=p_at) THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        SELECT coalesce(jsonb_agg(to_jsonb(items)),'[]'::jsonb) INTO result FROM
          (SELECT c.id AS conversation_id,c.connection_id,c.business_id,c.client_id,c.created_at,c.version::text AS version,
            CASE WHEN conn.provider='TELEGRAM' THEN c.last_client_inbound_at+interval '24 hours' END AS reply_window_expires_at
            FROM app.conversations c JOIN app.channel_connections conn ON conn.workspace_id=c.workspace_id AND conn.id=c.connection_id
            WHERE c.workspace_id=ws AND (p_id IS NULL OR (c.created_at,c.id)<(p_at,p_id)) ORDER BY c.created_at DESC,c.id DESC LIMIT p_limit) items;
        RETURN result;
      END $$"""
    )
    op.execute(
        """CREATE FUNCTION platform.messaging_read_messages(p_conversation uuid,p_limit integer,p_at timestamptz,p_id uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE ws uuid; result jsonb;
      BEGIN
"""
        + common
        + """        IF NOT EXISTS(SELECT 1 FROM app.conversations WHERE workspace_id=ws AND id=p_conversation) THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P2001'; END IF;
        IF p_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM app.messages WHERE workspace_id=ws AND conversation_id=p_conversation AND id=p_id AND created_at=p_at) THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        SELECT coalesce(jsonb_agg(to_jsonb(items)),'[]'::jsonb) INTO result FROM
          (SELECT m.id AS message_id,m.conversation_id,m.direction,m.content_type,m.text,m.occurred_at,m.created_at,m.version::text AS version,
            CASE WHEN f.id IS NOT NULL THEN jsonb_build_object('file_id',f.id,'status',f.status,'error_code',f.error_code,'manifest',
              CASE WHEN f.status='READY' THEN jsonb_build_object('mime_type',f.mime_type,'size_bytes',f.size_bytes::text,'width',f.width,'height',f.height) END) END AS file,
            CASE WHEN b.id IS NOT NULL THEN jsonb_build_object('status',b.status,'error_code',b.error_code,'completed_at',b.completed_at,'version',b.version::text) END AS delivery
            FROM app.messages m LEFT JOIN app.file_objects f ON f.workspace_id=m.workspace_id AND f.message_id=m.id
            LEFT JOIN app.outbox_events b ON b.workspace_id=m.workspace_id AND b.message_id=m.id
            WHERE m.workspace_id=ws AND m.conversation_id=p_conversation AND (p_id IS NULL OR (m.created_at,m.id)<(p_at,p_id)) ORDER BY m.created_at DESC,m.id DESC LIMIT p_limit) items;
        RETURN result;
      END $$"""
    )


def downgrade() -> None:
    # This check deliberately precedes every ALTER/DROP/DELETE. TEST cleanup is explicit.
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM app.channel_connections WHERE provider='TELEGRAM') OR
        EXISTS(SELECT 1 FROM app.client_identities WHERE provider='TELEGRAM') OR
        EXISTS(SELECT 1 FROM platform.telegram_update_receipts) OR EXISTS(SELECT 1 FROM platform.telegram_connection_state) OR
        EXISTS(SELECT 1 FROM platform.inbox_events WHERE provider='TELEGRAM') THEN
        RAISE EXCEPTION 'Telegram history prevents downgrade' USING ERRCODE='55000'; END IF;
      END $$""")
    for signature in PUBLIC_FUNCTIONS:
        op.execute(f"DROP FUNCTION {signature}")
    for original in ORIGINAL.values():
        op.execute(original.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1))
    # Drop callers before their private callees and state row type.
    for signature in (
        "platform.initialize_telegram_connection(uuid,uuid,text,text,text,jsonb)",
        "platform.initialize_local_messaging_billing(uuid,text,timestamp with time zone,timestamp with time zone)",
        "platform.telegram_save_observation(uuid,uuid,bigint,bigint,jsonb)",
        "platform.telegram_can_send(uuid,uuid,uuid,boolean)",
        "platform.telegram_probe_json(platform.telegram_connection_state)",
        "platform.telegram_validate_projection(text,jsonb)",
        "platform.telegram_fingerprint(text,jsonb)",
        "platform.telegram_validate_observation(jsonb)",
        "platform.messaging_manual_send_allowed(uuid)",
        "platform.messaging_lock_billing_workspace(uuid)",
        "platform.messaging_reschedule(uuid,text,boolean,integer)",
    ):
        op.execute(f"DROP FUNCTION {signature}")
    op.execute("DROP TABLE platform.telegram_update_receipts")
    op.execute("DROP TABLE platform.telegram_connection_state")
    op.execute("ALTER TABLE app.conversations DROP COLUMN last_client_inbound_at")
    op.execute(
        "ALTER TABLE platform.messaging_jobs DROP CONSTRAINT messaging_jobs_retry_delay_check,DROP COLUMN last_retry_after_seconds,DROP COLUMN last_retry_due,DROP CONSTRAINT messaging_jobs_telegram_probe_check,DROP COLUMN telegram_probe_claim,DROP COLUMN telegram_probe_generation,DROP COLUMN telegram_probe_version"
    )
    op.execute(
        "ALTER TABLE app.channel_connections DROP CONSTRAINT channel_connections_telegram_bot_check"
    )
    op.execute(
        "ALTER TABLE app.client_identities DROP CONSTRAINT client_identities_telegram_user_check"
    )
    for table in ("app.channel_connections", "app.client_identities"):
        op.execute(
            f"ALTER TABLE {table} DROP CONSTRAINT {table.split('.')[1]}_provider_check, ADD CONSTRAINT {table.split('.')[1]}_provider_check CHECK(provider='CONTROLLED')"
        )
    op.execute("DROP FUNCTION platform.telegram_numeric_id(text)")
