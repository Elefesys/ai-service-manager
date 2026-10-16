"""Closed Telegram V2 provenance and material context; exact 0011 reversal.

ORIGINAL contains immutable source definitions, not runtime catalog snapshots.
No historical rows or applied migrations are rewritten.
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

ORIGINAL = {
    "telegram_ingest(3)": r"""CREATE OR REPLACE FUNCTION platform.telegram_ingest(p_bot text,p_projection jsonb,p_correlation uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE p jsonb; e jsonb; digest bytea; rec platform.telegram_update_receipts%ROWTYPE;
        route platform.channel_routes%ROWTYPE; s platform.telegram_connection_state%ROWTYPE;
        result text; inbox uuid; job uuid; fresh boolean:=true; received timestamptz:=clock_timestamp();
      BEGIN
        PERFORM platform.turn_require_isolation();
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
                PERFORM 1 FROM app.channel_connections WHERE workspace_id=route.workspace_id AND id=route.connection_id FOR SHARE;
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
    "messaging_process_inbox(2)": r"""CREATE OR REPLACE FUNCTION platform.messaging_process_inbox(p_job uuid,p_claim uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE j platform.messaging_jobs%ROWTYPE; inbox platform.inbox_events%ROWTYPE; e jsonb;
        c app.channel_connections%ROWTYPE; identity app.client_identities%ROWTYPE; conv app.conversations%ROWTYPE;
        msg app.messages%ROWTYPE; client uuid; code text; state text; fingerprint bytea;
      BEGIN
        j:=platform.messaging_guard(p_job,p_claim);
        IF j.kind<>'PROCESS_INBOX' THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        SELECT * INTO STRICT inbox FROM platform.inbox_events WHERE workspace_id=j.workspace_id AND id=j.inbox_id FOR NO KEY UPDATE;
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
        IF code='PROCESSED' THEN
          PERFORM 1 FROM app.conversations WHERE workspace_id=j.workspace_id AND id=msg.conversation_id FOR NO KEY UPDATE;
          UPDATE app.conversations SET version=version+1,
            last_client_inbound_at=CASE WHEN e->>'provider'='TELEGRAM' THEN greatest(last_client_inbound_at,least(msg.occurred_at,inbox.received_at)) ELSE last_client_inbound_at END
            WHERE workspace_id=j.workspace_id AND id=msg.conversation_id;
          PERFORM platform.turn_group_message(j.workspace_id,msg.id,j.correlation_id);
        END IF;
        PERFORM platform.messaging_guard(p_job,p_claim);
        UPDATE platform.inbox_events SET status=state,result_code=code,message_id=msg.id,completed_at=clock_timestamp(),version=version+1 WHERE workspace_id=j.workspace_id AND id=inbox.id;
        UPDATE platform.messaging_jobs SET status=CASE WHEN state='FAILED' THEN 'DEAD' ELSE 'SUCCEEDED' END,error_code=CASE WHEN state='FAILED' THEN code END,
          claim_token=NULL,lease_until=NULL,worker_id=NULL,completed_at=clock_timestamp(),version=version+1 WHERE id=j.id;
        RETURN jsonb_build_object('code',code,'inbox_id',inbox.id,'message_id',msg.id,'status',state);
      END $$""",
    "files_plan(3)": r"""CREATE OR REPLACE FUNCTION platform.files_plan(p_workspace uuid,p_message uuid,p_correlation uuid) RETURNS void
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE m app.messages%ROWTYPE; f app.file_objects%ROWTYPE;
      BEGIN
        SELECT * INTO STRICT m FROM app.messages WHERE workspace_id=p_workspace AND id=p_message;
        IF m.direction<>'INBOUND' OR m.content_type<>'IMAGE_REFERENCE' OR p_correlation IS NULL THEN
          RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        INSERT INTO app.file_objects(workspace_id,message_id,connection_id,conversation_id)
        VALUES(m.workspace_id,m.id,m.connection_id,m.conversation_id) ON CONFLICT(workspace_id,message_id) DO NOTHING;
        SELECT * INTO STRICT f FROM app.file_objects WHERE workspace_id=m.workspace_id AND message_id=m.id;
        INSERT INTO platform.messaging_jobs(workspace_id,connection_id,kind,file_id,correlation_id)
        VALUES(m.workspace_id,m.connection_id,'FETCH_IMAGE',f.id,p_correlation)
        ON CONFLICT(workspace_id,file_id) DO NOTHING;
      END $$""",
    "turn_group_message(3)": r"""CREATE OR REPLACE FUNCTION platform.turn_group_message(ws uuid,p_message uuid,corr uuid) RETURNS void
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE m app.messages%ROWTYPE; origin platform.inbox_events%ROWTYPE; t app.conversation_turns%ROWTYPE;
        conv app.conversations%ROWTYPE; file uuid; late boolean:=false; fresh boolean:=false; generation bigint;
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
        generation:=coalesce(origin.turn_control_generation,1);
        -- A delayed old origin cannot close a newer group, even if it has already sealed.
        late:=EXISTS(SELECT 1 FROM app.conversation_turns WHERE workspace_id=ws AND conversation_id=conv.id AND
          (control_generation>generation OR (control_generation=generation AND ingress_control_mode IS NOT NULL AND origin.turn_control_mode IS NULL)));
        SELECT * INTO t FROM app.conversation_turns WHERE workspace_id=ws AND conversation_id=conv.id AND state='COLLECTING' FOR NO KEY UPDATE;
        IF late OR (FOUND AND origin.turn_ingress_at<t.first_ingress_at) THEN
          late:=true; t.id:=NULL;
        ELSIF FOUND AND ((t.control_generation,t.ingress_control_mode,t.activation_fence_seq) IS DISTINCT FROM
          (generation,origin.turn_control_mode,origin.turn_activation_fence_seq) OR origin.turn_ingress_at>=least(t.quiet_at,t.hard_at) OR t.member_count>=t.max_members OR
          (t.media_group_id IS NOT NULL AND m.media_group_id IS NOT NULL AND t.media_group_id<>m.media_group_id)) THEN
          PERFORM platform.turn_seal(ws,t.id,least(origin.turn_ingress_at,t.quiet_at,t.hard_at),corr,true);
          t.id:=NULL;
        END IF;
        IF t.id IS NULL THEN
          fresh:=true;
          -- Out-of-order input must not move/close the existing collecting window.
          -- The new singleton is sealed immediately; its media budget starts at ingress.
          INSERT INTO app.conversation_turns(workspace_id,conversation_id,connection_id,provider_chat_id,control_generation,ingress_control_mode,activation_fence_seq,state,
            first_ingress_at,last_ingress_at,hard_at,quiet_at,media_deadline_at,media_group_id,seal_time,closed_at)
          VALUES(ws,conv.id,m.connection_id,m.provider_chat_id,generation,origin.turn_control_mode,origin.turn_activation_fence_seq,CASE WHEN late THEN 'WAITING_MEDIA' ELSE 'COLLECTING' END,
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
      END $$""",
    "turn_member_check(0)": r"""CREATE OR REPLACE FUNCTION platform.turn_member_check() RETURNS trigger
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE t app.conversation_turns%ROWTYPE; i platform.inbox_events%ROWTYPE; m app.messages%ROWTYPE;
      BEGIN
        SELECT * INTO STRICT t FROM app.conversation_turns WHERE workspace_id=NEW.workspace_id AND id=NEW.turn_id;
        SELECT * INTO STRICT i FROM platform.inbox_events WHERE workspace_id=NEW.workspace_id AND id=NEW.origin_inbox_id;
        SELECT * INTO STRICT m FROM app.messages WHERE workspace_id=NEW.workspace_id AND id=NEW.message_id;
        IF (t.control_generation,t.ingress_control_mode,t.activation_fence_seq) IS DISTINCT FROM
          (coalesce(i.turn_control_generation,1),i.turn_control_mode,i.turn_activation_fence_seq) OR (t.state<>'COLLECTING' AND t.member_count<>0) OR i.turn_ingress_seq IS NULL OR
          (NEW.turn_ingress_at,NEW.turn_ingress_seq) IS DISTINCT FROM (i.turn_ingress_at,i.turn_ingress_seq) OR
          i.normalized_event->>'kind'<>'CLIENT_MESSAGE' OR
          (i.connection_id,i.normalized_event->>'chat_id',i.normalized_event->>'message_id') IS DISTINCT FROM
          (m.connection_id,m.provider_chat_id,m.provider_message_id) THEN
          RAISE EXCEPTION 'invalid turn origin/membership' USING ERRCODE='23514'; END IF;
        RETURN NEW;
      END $$""",
    "turn_members_consistent(0)": r"""CREATE OR REPLACE FUNCTION platform.turn_members_consistent() RETURNS trigger
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
      END $$""",
    "turn_immutable(0)": r"""CREATE OR REPLACE FUNCTION platform.turn_immutable() RETURNS trigger
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
      END $$""",
    "turn_material(0)": r"""CREATE OR REPLACE FUNCTION platform.turn_material() RETURNS trigger
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
      END $$""",
    "turn_seal(5)": r"""CREATE OR REPLACE FUNCTION platform.turn_seal(ws uuid,p_turn uuid,p_seal timestamptz,corr uuid,bump boolean) RETURNS void
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
      END $$""",
    "turn_enqueue(3)": r"""CREATE OR REPLACE FUNCTION platform.turn_enqueue(ws uuid,p_turn uuid,corr uuid) RETURNS void
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
        IF t.state='READY' AND current_database() IN ('asm_local','asm_test')
          AND platform.conversation_turn_activation_matches(ws,t.id) IS TRUE
          AND EXISTS(SELECT 1 FROM app.channel_connections WHERE workspace_id=ws AND id=t.connection_id AND provider='CONTROLLED')
          AND EXISTS(SELECT 1 FROM platform.conversation_control_receipts WHERE workspace_id=ws AND conversation_id=t.conversation_id
            AND accepted_generation=t.control_generation AND activation_fence_seq=t.activation_fence_seq
            AND guard_profile='CONTROLLED_GUARDS_V1' AND operation='RESUME') THEN
          INSERT INTO platform.messaging_jobs(workspace_id,connection_id,kind,turn_id,turn_revision,step,correlation_id)
            VALUES(ws,t.connection_id,'PROCESS_TURN',t.id,t.revision,CASE WHEN EXISTS(SELECT 1 FROM app.conversation_turn_messages tm JOIN app.messages m
          ON (m.workspace_id,m.id)=(tm.workspace_id,tm.message_id)
          WHERE tm.workspace_id=ws AND tm.turn_id=p_turn AND m.direction='INBOUND'
            AND m.content_type='TEXT' AND m.text='CONTROLLED ESCALATION TEST') THEN 'ESCALATE_OWNER' ELSE 'GUARDED_TEXT' END,corr)
            ON CONFLICT(workspace_id,turn_id,turn_revision,step) DO NOTHING;
        END IF;
      END $$""",
    "conversation_turn_activation_matches(2)": r"""CREATE OR REPLACE FUNCTION platform.conversation_turn_activation_matches(ws uuid,p_turn uuid) RETURNS boolean
      LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
        SELECT coalesce((SELECT t.ingress_control_mode='AI' AND t.activation_fence_seq IS NOT NULL AND c.control_mode='AI'
          AND (t.control_generation,t.activation_fence_seq)=(c.control_generation,c.activation_fence_seq)
          AND t.member_count>0 AND NOT EXISTS(
            SELECT 1 FROM app.conversation_turn_messages m JOIN platform.inbox_events i ON (i.workspace_id,i.id)=(m.workspace_id,m.origin_inbox_id)
            WHERE m.workspace_id=ws AND m.turn_id=t.id AND
              ((i.turn_control_generation,i.turn_control_mode,i.turn_activation_fence_seq) IS DISTINCT FROM
                (t.control_generation,t.ingress_control_mode,t.activation_fence_seq) OR
                i.turn_ingress_seq IS NULL OR i.turn_ingress_seq<=t.activation_fence_seq))
          FROM app.conversation_turns t JOIN app.conversations c ON (c.workspace_id,c.id)=(t.workspace_id,t.conversation_id)
          WHERE t.workspace_id=ws AND t.id=p_turn),false)
      $$""",
    "guard_require_current(4)": r"""CREATE OR REPLACE FUNCTION platform.guard_require_current(ws uuid,p_turn uuid,p_resume uuid,p_context bigint) RETURNS text
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
        IF EXISTS(SELECT 1 FROM app.conversation_turn_messages tm JOIN app.messages m
          ON (m.workspace_id,m.id)=(tm.workspace_id,tm.message_id)
          WHERE tm.workspace_id=ws AND tm.turn_id=p_turn AND m.direction='INBOUND'
            AND m.content_type='TEXT' AND m.text='CONTROLLED ESCALATION TEST') OR EXISTS(SELECT 1 FROM app.escalations WHERE workspace_id=ws AND
          (turn_id=p_turn OR (conversation_id=c.id AND status='PENDING'))) THEN RETURN 'NOT_ALLOWED'; END IF;
        RETURN 'CURRENT';
      END $$""",
    "turn_snapshot(2)": r"""CREATE OR REPLACE FUNCTION platform.turn_snapshot(ws uuid,p_turn uuid) RETURNS jsonb
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
      END $$""",
    "turn_consumer_finalize(3)": r"""CREATE OR REPLACE FUNCTION platform.turn_consumer_finalize(p_job uuid,p_claim uuid,p_result jsonb) RETURNS jsonb
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
      END $$""",
    "turn_supersede(1)": """CREATE OR REPLACE FUNCTION platform.turn_supersede(j platform.messaging_jobs) RETURNS boolean
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$ DECLARE timer_e app.escalations%ROWTYPE; timer_moment timestamptz; timer_due timestamptz;
        timer_validity text; timer_outcome text; timer_error text; timer_recorded timestamptz;
        fault_schema text; fault_table text; fault_constraint text; BEGIN
        IF j.kind='ESCALATION_TIMER' THEN\x20
        SELECT * INTO STRICT timer_e FROM app.escalations WHERE workspace_id=j.workspace_id AND id=j.escalation_id;
        timer_moment:=platform.escalation_now();
        timer_due:=CASE j.step WHEN 'REMIND_1' THEN timer_e.due_at WHEN 'REMIND_2' THEN timer_e.second_reminder_at WHEN 'EXPIRE' THEN timer_e.expires_at END;
        IF timer_due IS NULL THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        IF timer_moment<timer_due THEN RAISE EXCEPTION 'not yet due' USING ERRCODE='P3001'; END IF;
        timer_validity:=platform.escalation_validity(j.workspace_id,timer_e.id,timer_moment);
        BEGIN
          IF timer_e.status<>'PENDING' THEN
            timer_outcome:='NOOP_TERMINAL'; timer_recorded:=timer_e.completed_at;
          ELSIF timer_validity IN ('CONTROL_CHANGED','CONTEXT_CHANGED','ASSIGNEE_REVOKED','EXPIRED') THEN
            timer_outcome:=CASE WHEN timer_validity='EXPIRED' THEN 'EXPIRED' ELSE 'CANCELLED' END;
            UPDATE app.escalations SET status=timer_outcome,version=2,
              closure_reason=CASE WHEN timer_validity='EXPIRED' THEN 'DEADLINE_ELAPSED' ELSE timer_validity END,
              completed_at=timer_moment WHERE workspace_id=j.workspace_id AND id=timer_e.id;
            -- Material invalidation already owns its counter change. Revocation
            -- and expiry close first, then consume the reserved increment.
            IF timer_validity IN ('ASSIGNEE_REVOKED','EXPIRED') THEN
              UPDATE app.conversations SET version=version+1 WHERE workspace_id=j.workspace_id AND id=timer_e.conversation_id;
            END IF;
            timer_recorded:=timer_moment;
\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20
          END IF;
        EXCEPTION WHEN check_violation THEN
          GET STACKED DIAGNOSTICS fault_schema=SCHEMA_NAME,fault_table=TABLE_NAME,fault_constraint=CONSTRAINT_NAME;
          IF fault_schema IS DISTINCT FROM 'app' OR fault_table IS DISTINCT FROM 'escalations' OR
            fault_constraint IS NULL OR fault_constraint NOT IN ('escalations_lifecycle_check','escalations_reminders_check','escalations_immutable_check') THEN RAISE; END IF;
          -- Only the domain subtransaction is rolled back. Prior row locks and
          -- the outer transaction survive; a failed DEAD write is never caught.
          timer_outcome:=NULL; timer_recorded:=NULL; timer_error:='INVALID_INPUT';
        END;
        IF timer_outcome IS NOT NULL OR timer_error IS NOT NULL THEN
          UPDATE platform.messaging_jobs SET status=CASE WHEN timer_error IS NULL THEN 'SUCCEEDED' ELSE 'DEAD' END,
            escalation_outcome=timer_outcome,error_code=timer_error,
            attempt_count=greatest(1,attempt_count),first_started_at=coalesce(first_started_at,clock_timestamp()),
            claim_token=NULL,lease_until=NULL,worker_id=NULL,completed_at=clock_timestamp(),version=version+1 WHERE id=j.id;
        END IF;
     RETURN timer_outcome IS NOT NULL OR timer_error IS NOT NULL; END IF;
        IF j.kind='PROCESS_TURN' AND j.step<>'ESCALATE_OWNER' AND EXISTS(SELECT 1 FROM app.conversation_turns
          WHERE workspace_id=j.workspace_id AND id=j.turn_id AND revision<>j.turn_revision) THEN
          UPDATE platform.messaging_jobs SET status='SUCCEEDED',turn_outcome='SUPERSEDED',error_code=NULL,
            attempt_count=greatest(1,attempt_count),first_started_at=coalesce(first_started_at,clock_timestamp()),
            claim_token=NULL,lease_until=NULL,worker_id=NULL,completed_at=clock_timestamp(),version=version+1 WHERE id=j.id;
          RETURN true;
        END IF; RETURN false;
      END $$""",
    "files_read_manifest(3)": r"""CREATE OR REPLACE FUNCTION platform.files_read_manifest(p_conversation uuid,p_message uuid,p_file uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE ws uuid; actor uuid; result jsonb;
      BEGIN
        ws:=app.current_messaging_owner_workspace_id();
        actor:=nullif(current_setting('asm.actor_id',true),'')::uuid;
        IF ws IS NULL OR platform.messaging_lock_owner(ws,actor) IS NOT TRUE THEN
          RAISE EXCEPTION 'ACCESS_DENIED' USING ERRCODE='P2001'; END IF;
        IF p_conversation IS NULL OR p_message IS NULL OR p_file IS NULL THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        SELECT jsonb_build_object('workspace_id',f.workspace_id,'conversation_id',c.id,'message_id',m.id,'file_id',f.id,'storage_key',u.storage_key,
          'manifest',platform.files_upload_json(u)->'manifest') INTO result
        FROM app.file_objects f JOIN app.messages m ON (m.workspace_id,m.id,m.connection_id,m.conversation_id)=(f.workspace_id,f.message_id,f.connection_id,f.conversation_id)
        JOIN app.conversations c ON (c.workspace_id,c.id,c.connection_id)=(m.workspace_id,m.conversation_id,m.connection_id)
        JOIN platform.file_object_uploads u ON (u.workspace_id,u.file_id,u.id)=(f.workspace_id,f.id,f.winner_intent_id)
        WHERE f.workspace_id=ws AND f.id=p_file AND m.id=p_message AND c.id=p_conversation AND f.status='READY' AND u.status='WINNER';
        IF result IS NULL THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P2001'; END IF;
        RETURN result;
      END $$""",
    "messaging_read_messages(4)": r"""CREATE OR REPLACE FUNCTION platform.messaging_read_messages(p_conversation uuid,p_limit integer,p_at timestamptz,p_id uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE ws uuid; result jsonb;
      BEGIN
        ws:=app.current_messaging_owner_workspace_id();
        IF ws IS NULL OR platform.messaging_lock_owner(ws,nullif(current_setting('asm.actor_id',true),'')::uuid) IS NOT TRUE THEN RAISE EXCEPTION 'ACCESS_DENIED' USING ERRCODE='P2001'; END IF;
        IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 101 OR (p_at IS NULL)<>(p_id IS NULL) OR (p_at IS NOT NULL AND NOT isfinite(p_at)) THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        IF NOT EXISTS(SELECT 1 FROM app.conversations WHERE workspace_id=ws AND id=p_conversation) THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P2001'; END IF;
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
      END $$""",
}


def _replace(name: str, *changes: tuple[str, str]) -> None:
    body = ORIGINAL[name]
    for before, after in changes:
        assert body.count(before) == 1, (name, before)
        body = body.replace(before, after)
    op.execute(body)


TABLES = (
    "platform.telegram_provenance",
    "platform.message_material_targets",
    "platform.message_material_effects",
    "platform.message_initial_suppressions",
)
PUBLIC_FUNCTIONS = (
    "platform.telegram_replay_v1(text,jsonb)",
    "platform.material_processing_replay(uuid,uuid)",
)
PRIVATE_FUNCTIONS = (
    "platform.material_object(jsonb,text[])",
    "platform.material_content_valid(jsonb)",
    "platform.material_semantic(jsonb)",
    "platform.material_state_valid(jsonb)",
    "platform.telegram_validate_v2(text,jsonb)",
    "platform.telegram_fingerprint_v2(text,jsonb)",
    "platform.telegram_receipt_json(platform.telegram_update_receipts,text)",
    "platform.material_result_valid(jsonb)",
    "platform.material_integrity()",
    "platform.material_target_check()",
    "platform.material_suppression_check()",
    "platform.material_no_file()",
    "platform.message_effective(uuid,uuid)",
    "platform.material_turn_usable(uuid,uuid)",
    "platform.material_identity(uuid,uuid,jsonb)",
    "platform.material_fold(uuid,uuid,uuid)",
    "platform.material_apply(uuid,uuid,uuid)",
    "platform.material_apply_context(uuid,uuid,uuid)",
    "platform.material_bump_turns(uuid,uuid[],uuid)",
    "platform.material_bind(uuid,uuid,boolean,uuid)",
    "platform.material_process(platform.messaging_jobs)",
)


def _validation() -> None:
    op.execute("""CREATE FUNCTION platform.material_object(p jsonb,keys text[]) RETURNS boolean
      LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $$
      SELECT CASE WHEN jsonb_typeof(p)='object' THEN p ?& keys AND
        (SELECT count(*) FROM jsonb_object_keys(p))=cardinality(keys) ELSE false END $$""")
    op.execute("""CREATE FUNCTION platform.material_content_valid(c jsonb) RETURNS boolean
      LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $$ BEGIN
        IF c->>'kind'='TEXT' THEN
          RETURN platform.material_object(c,ARRAY['kind','text']) AND jsonb_typeof(c->'text')='string'
            AND char_length(c->>'text') BETWEEN 1 AND 4096 AND octet_length(c->>'text')<=16384;
        ELSIF c->>'kind'='PHOTO' THEN
          RETURN platform.material_object(c,ARRAY['kind','caption','selected_file_id','selected_unique_id'])
            AND jsonb_typeof(c->'caption') IN ('string','null')
            AND (c->>'caption' IS NULL OR (char_length(c->>'caption')<=4096 AND octet_length(c->>'caption')<=16384))
            AND jsonb_typeof(c->'selected_file_id')='string' AND platform.messaging_valid_id(c->>'selected_file_id',1024,4096)
            AND jsonb_typeof(c->'selected_unique_id') IN ('string','null')
            AND (c->>'selected_unique_id' IS NULL OR platform.messaging_valid_id(c->>'selected_unique_id',1024,4096));
        ELSIF c->>'kind'='UNSUPPORTED' THEN
          RETURN platform.material_object(c,ARRAY['kind','reason']) AND c->>'reason' IN ('UNSUPPORTED_MEDIA','EMPTY_CONTENT');
        END IF; RETURN false;
      END $$""")
    op.execute("""CREATE FUNCTION platform.material_semantic(c jsonb) RETURNS jsonb
      LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $$
      SELECT CASE WHEN c IS NULL OR c='null'::jsonb THEN NULL WHEN c->>'kind'='UNSUPPORTED' THEN
        '{"state":"UNSUPPORTED_CONTENT","content":null}'::jsonb
      ELSE jsonb_build_object('state','VISIBLE','content',c-'selected_unique_id') END $$""")
    op.execute("""CREATE FUNCTION platform.material_state_valid(v jsonb) RETURNS boolean
      LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $$
      SELECT (platform.material_object(v,ARRAY['state','content']) AND
        ((v->>'state' IN ('DELETED','ORDER_UNCERTAIN','UNSUPPORTED_CONTENT') AND v->'content'='null'::jsonb) OR
         (v->>'state'='VISIBLE' AND (v->'content'->>'kind'='TEXT' AND platform.material_content_valid(v->'content') OR
           v->'content'->>'kind'='PHOTO' AND platform.material_object(v->'content',ARRAY['kind','caption','selected_file_id'])
             AND platform.material_content_valid((v->'content')||'{"selected_unique_id":null}'::jsonb))))) IS TRUE $$""")
    op.execute(r"""CREATE FUNCTION platform.telegram_validate_v2(bot text,p jsonb) RETURNS jsonb
      LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
      DECLARE l jsonb; e jsonb; o jsonb; c jsonb; d text; k text; moment timestamptz;
      BEGIN
        IF platform.material_object(p,ARRAY['codec','bot','update_id','legacy_v1','discriminator','connection',
          'chat_id','message_id','sent_at','edited_at','chat_type','origin','content','unsupported_reason']) IS NOT TRUE
          OR octet_length(p::text)>65536 OR p->>'codec' IS DISTINCT FROM 'TELEGRAM_PROVENANCE_V2'
          OR p->>'bot' IS DISTINCT FROM bot OR jsonb_typeof(p->'bot')<>'string' THEN
          RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        l:=platform.telegram_validate_projection(bot,p->'legacy_v1'); d:=p->>'discriminator';
        IF d IS NULL OR d NOT IN ('NEW','EDIT','DELETE','LIFECYCLE','UNSUPPORTED') OR
          p->'update_id' IS DISTINCT FROM l->'update_id' OR p->'connection' IS DISTINCT FROM l->'external_connection_id'
          OR l->>'kind' IS DISTINCT FROM (CASE d WHEN 'NEW' THEN 'BUSINESS_MESSAGE' WHEN 'EDIT' THEN 'EDITED_BUSINESS_MESSAGE'
            WHEN 'DELETE' THEN 'DELETED_BUSINESS_MESSAGES' WHEN 'LIFECYCLE' THEN 'BUSINESS_CONNECTION' ELSE 'UNSUPPORTED' END) THEN
          RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        IF d IN ('NEW','EDIT') THEN
          e:=l->'event'; o:=p->'origin'; c:=p->'content';
          IF platform.material_object(o,ARRAY['sender_id','sender_is_bot','sender_business_bot_id','offline']) IS NOT TRUE
            OR platform.material_content_valid(c) IS NOT TRUE OR
            (p->'chat_id',p->'message_id',p->'sent_at',o->'sender_id',o->'sender_business_bot_id') IS DISTINCT FROM
            (e->'chat_id',e->'message_id',e->'occurred_at',e->'sender_id',l->'sender_business_bot_id') OR
            platform.telegram_numeric_id(p->>'chat_id') IS NOT TRUE OR platform.telegram_numeric_id(p->>'message_id') IS NOT TRUE
            OR p->>'sent_at' IS NULL OR p->>'chat_type' IS NULL OR p->>'chat_type' NOT IN ('PRIVATE','UNSUPPORTED')
            OR o->>'sender_is_bot' IS NULL OR o->>'sender_is_bot' NOT IN ('TRUE','FALSE','MISSING')
            OR ((o->>'sender_id' IS NULL)<>(o->>'sender_is_bot'='MISSING'))
            OR o->>'offline' IS NULL OR o->>'offline' NOT IN ('TRUE','MISSING')
            OR p->>'unsupported_reason' IS NULL OR p->>'unsupported_reason' NOT IN
              ('NONE','NONPRIVATE','BOT_SENDER','SENDER_CHAT','GUEST','UNSUPPORTED_MEDIA','EMPTY_CONTENT','AMBIGUOUS_SENDER')
            OR (p->>'chat_type'='UNSUPPORTED' AND p->>'unsupported_reason'<>'NONPRIVATE')
            OR (p->>'chat_type'='PRIVATE' AND o->>'sender_is_bot'='TRUE' AND p->>'unsupported_reason'<>'BOT_SENDER')
            OR (p->>'unsupported_reason'='NONE' AND (o->>'sender_id' IS DISTINCT FROM p->>'chat_id'
              OR o->>'sender_is_bot'<>'FALSE' OR c->>'kind'='UNSUPPORTED')) THEN
            RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
          IF (d='EDIT' AND e->>'kind'<>'MESSAGE_EDITED') OR (d='NEW' AND e->>'kind' IS DISTINCT FROM
            CASE WHEN p->>'unsupported_reason'='NONE' THEN 'CLIENT_MESSAGE' ELSE 'UNSUPPORTED' END) OR
            (c->>'kind'='TEXT' AND (c->'text' IS DISTINCT FROM e->'text' OR e->>'image_file_id' IS NOT NULL)) OR
            (c->>'kind'='PHOTO' AND (c->'caption',c->'selected_file_id') IS DISTINCT FROM (e->'text',e->'image_file_id')) THEN
            RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
          FOREACH k IN ARRAY ARRAY['sent_at','edited_at'] LOOP
            IF jsonb_typeof(p->k) NOT IN ('string','null') OR (k='sent_at' AND p->>k IS NULL) THEN
              RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
            IF p->>k IS NOT NULL THEN
              BEGIN moment:=(p->>k)::timestamptz;
              EXCEPTION WHEN OTHERS THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END;
              IF NOT isfinite(moment) OR to_char(moment AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"') IS DISTINCT FROM p->>k THEN
                RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
            END IF;
          END LOOP;
        ELSE
          FOREACH k IN ARRAY ARRAY['message_id','sent_at','edited_at','chat_type','origin','content'] LOOP
            IF p->k IS DISTINCT FROM 'null'::jsonb THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
          END LOOP;
          IF p->>'unsupported_reason' IS DISTINCT FROM (CASE WHEN d='UNSUPPORTED' THEN 'NONBUSINESS' ELSE 'NONE' END)
            OR (d='DELETE' AND (p->'chat_id' IS DISTINCT FROM l->'deleted_chat_id' OR jsonb_array_length(l->'deleted_message_ids')>100))
            OR (d<>'DELETE' AND p->>'chat_id' IS NOT NULL)
            OR (d='UNSUPPORTED' AND p->>'connection' IS NOT NULL) THEN
            RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        END IF;
        RETURN p;
      END $$""")
    op.execute(r"""CREATE FUNCTION platform.telegram_fingerprint_v2(bot text,p jsonb) RETURNS bytea
      LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $$
      DECLARE encoded bytea:=convert_to(E'asm:m3:telegram_provenance:v2\n','UTF8'); v text;
      BEGIN
        FOREACH v IN ARRAY ARRAY[bot,p->>'update_id',encode(platform.telegram_fingerprint(bot,p->'legacy_v1'),'hex'),
          p->>'discriminator',p->>'chat_type',p->'origin'->>'sender_is_bot',p->'origin'->>'offline',
          p->>'unsupported_reason',p->>'edited_at',p->'content'->>'kind',p->'content'->>'selected_unique_id',p->'content'->>'reason'] LOOP
          encoded:=encoded||convert_to(CASE WHEN v IS NULL THEN E'-1:\n' ELSE octet_length(v)::text||':'||v||E'\n' END,'UTF8');
        END LOOP; RETURN sha256(encoded);
      END $$""")
    op.execute(r"""CREATE FUNCTION platform.material_result_valid(a jsonb) RETURNS boolean
      LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
      DECLARE r jsonb; n integer:=0; k text; v numeric; old_v numeric;
      BEGIN
        IF jsonb_typeof(a) IS DISTINCT FROM 'array' OR octet_length(a::text)>65536 OR jsonb_array_length(a) NOT BETWEEN 1 AND 100 THEN RETURN false; END IF;
        FOR r IN SELECT value FROM jsonb_array_elements(a) LOOP
          n:=n+1;
          IF platform.material_object(r,ARRAY['ordinal','code','target_id','message_id','effect_id','audit_event_id','previous_version','accepted_version']) IS NOT TRUE
            OR r->'ordinal' IS DISTINCT FROM to_jsonb(n) OR r->>'code' IS NULL THEN RETURN false; END IF;
          FOREACH k IN ARRAY ARRAY['target_id','message_id','effect_id','audit_event_id'] LOOP
            IF jsonb_typeof(r->k) NOT IN ('string','null') THEN RETURN false; END IF;
            IF r->>k IS NOT NULL AND (r->>k)::uuid::text IS DISTINCT FROM r->>k THEN RETURN false; END IF;
          END LOOP;
          FOREACH k IN ARRAY ARRAY['previous_version','accepted_version'] LOOP
            IF jsonb_typeof(r->k) NOT IN ('string','null') OR (r->>k IS NOT NULL AND NOT platform.telegram_numeric_id(r->>k)) THEN RETURN false; END IF;
          END LOOP;
          old_v:=(r->>'previous_version')::numeric; v:=(r->>'accepted_version')::numeric;
          IF r->>'code'='APPLIED' THEN
            IF r->>'target_id' IS NULL OR r->>'message_id' IS NULL OR r->>'effect_id' IS NULL OR r->>'audit_event_id' IS NULL
              OR old_v IS NULL OR v IS NULL OR v<>old_v+1 THEN RETURN false; END IF;
          ELSIF r->>'code' IN ('NOOP_CONTENT','STALE_EDIT','ALREADY_DELETED','ALREADY_UNCERTAIN') THEN
            IF r->>'target_id' IS NULL OR r->>'message_id' IS NULL OR r->>'effect_id' IS NOT NULL OR r->>'audit_event_id' IS NOT NULL
              OR old_v IS NULL OR v IS DISTINCT FROM old_v THEN RETURN false; END IF;
          ELSIF r->>'code' IN ('DEFERRED_TARGET','IDENTITY_CONFLICT') THEN
            IF ((r->>'target_id' IS NOT NULL)<>(r->>'code'='DEFERRED_TARGET')) OR r->>'message_id' IS NOT NULL
              OR r->>'effect_id' IS NOT NULL OR r->>'audit_event_id' IS NOT NULL OR old_v IS NOT NULL OR v IS NOT NULL THEN RETURN false; END IF;
          ELSE RETURN false; END IF;
        END LOOP; RETURN true;
      EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN RETURN false;
      END $$""")


OLD_INBOX_CHECK = r"""(status='PENDING' AND result_code IS NULL AND message_id IS NULL AND completed_at IS NULL) OR
       (status='PROCESSED' AND result_code IS NOT NULL AND result_code IN ('PROCESSED','DUPLICATE') AND message_id IS NOT NULL AND completed_at IS NOT NULL) OR
       (status='IGNORED' AND result_code IS NOT NULL AND result_code IN ('IGNORED_NATIVE_OWNER_MESSAGE','IGNORED_MESSAGE_EDITED','IGNORED_MESSAGE_DELETED','IGNORED_UNSUPPORTED') AND message_id IS NULL AND completed_at IS NOT NULL) OR
       (status='FAILED' AND result_code IS NOT NULL AND result_code IN ('MESSAGE_ID_CONFLICT','CONVERSATION_IDENTITY_CONFLICT','RETRY_EXHAUSTED','DEPENDENCY_TIMEOUT','DEPENDENCY_UNAVAILABLE','INVALID_INPUT') AND message_id IS NULL AND completed_at IS NOT NULL)"""

OLD_RECEIPT_CHECK = r"""(workspace_id IS NULL AND connection_id IS NULL AND inbox_id IS NULL AND kind='UNSUPPORTED' AND result_code='IGNORED_UNSUPPORTED') OR
        (workspace_id IS NOT NULL AND connection_id IS NOT NULL AND
          ((result_code='QUEUED' AND kind='BUSINESS_MESSAGE' AND inbox_id IS NOT NULL) OR (result_code<>'QUEUED' AND inbox_id IS NULL)))"""

OLD_MEMBER_CHECK = r"""(content_type='TEXT' AND file_id IS NULL) OR (content_type='IMAGE_REFERENCE' AND file_id IS NOT NULL)"""

OLD_AUDIT_CHECK = """
\x20\x20\x20\x20\x20\x20
      (event_type='WORKSPACE_BILLING_PROVISIONED' AND
 actor_kind='LOCAL_PROVISIONER' AND actor_user_account_id IS NULL AND
 object_type='WORKSPACE_BILLING_ACCOUNT' AND payload='{}'::jsonb) OR
 (event_type='BILLING_ACCOUNT_CONTACT_UPDATED' AND actor_kind='USER_ACCOUNT' AND
 actor_user_account_id IS NOT NULL AND object_type='WORKSPACE_BILLING_ACCOUNT' AND
 payload='{"changed_fields":["contact_display_name"]}'::jsonb) OR (event_type='MESSAGE_SEND_REQUESTED' AND actor_kind='USER_ACCOUNT' AND actor_user_account_id IS NOT NULL AND object_type='MESSAGE' AND object_version=1 AND payload='{"content_type":"TEXT"}'::jsonb) OR ((
        event_type IN ('CONVERSATION_TAKEN_OVER','CONVERSATION_RESUMED') AND actor_kind='USER_ACCOUNT'
        AND actor_user_account_id IS NOT NULL AND object_type='CONVERSATION' AND object_version>0
        AND conversation_object_id IS NOT NULL AND conversation_control_generation IS NOT NULL
        AND payload=jsonb_build_object('previous_mode',payload->>'previous_mode','control_mode',payload->>'control_mode',
          'previous_generation',payload->>'previous_generation','control_generation',payload->>'control_generation')
        AND payload->>'previous_mode' IN ('HUMAN','AI')
        AND payload->>'control_mode'=CASE event_type WHEN 'CONVERSATION_TAKEN_OVER' THEN 'HUMAN' ELSE 'AI' END
        AND CASE WHEN payload->>'previous_generation' ~ '^[1-9][0-9]{0,18}$'
                   AND payload->>'control_generation' ~ '^[1-9][0-9]{0,18}$'
          THEN (payload->>'previous_generation')::numeric<9223372036854775807
            AND (payload->>'control_generation')::numeric=(payload->>'previous_generation')::numeric+1
          ELSE false END) IS TRUE) OR ((event_type='ESCALATION_DECIDED' AND actor_kind='USER_ACCOUNT'
        AND actor_user_account_id IS NOT NULL AND object_type='ESCALATION' AND object_version=2
        AND escalation_object_id IS NOT NULL AND escalation_operation IS NOT NULL AND
        payload IN ('{"operation":"RESOLVE","status":"RESOLVED"}'::jsonb,'{"operation":"CANCEL","status":"CANCELLED"}'::jsonb)) IS TRUE)"""


def _schema() -> None:
    op.execute("""LOCK TABLE platform.telegram_update_receipts,platform.telegram_connection_state,
      platform.inbox_events,app.messages,app.outbox_events,app.conversation_turns,
      app.conversation_turn_messages,app.audit_events IN ACCESS EXCLUSIVE MODE""")
    op.execute("""ALTER TABLE platform.telegram_connection_state ADD COLUMN material_enabled boolean NOT NULL DEFAULT false;
      ALTER TABLE platform.telegram_update_receipts ADD COLUMN codec smallint CHECK(codec=2),
        ADD CONSTRAINT telegram_material_identity_key UNIQUE(id,codec,bot_identity,update_id,workspace_id,connection_id,inbox_id),
        ADD CONSTRAINT telegram_material_source_key UNIQUE(workspace_id,id),
        DROP CONSTRAINT telegram_update_receipts_check""")
    op.execute(f"""ALTER TABLE platform.telegram_update_receipts ADD CONSTRAINT telegram_update_receipts_check CHECK(
      (codec IS NULL AND ({OLD_RECEIPT_CHECK})) OR
      (codec=2 AND ((workspace_id IS NULL AND connection_id IS NULL AND inbox_id IS NULL AND kind='UNSUPPORTED' AND result_code='IGNORED_UNSUPPORTED') OR
        (workspace_id IS NOT NULL AND connection_id IS NOT NULL AND ((result_code='QUEUED' AND kind IN
          ('BUSINESS_MESSAGE','EDITED_BUSINESS_MESSAGE','DELETED_BUSINESS_MESSAGES') AND inbox_id IS NOT NULL) OR
          (result_code<>'QUEUED' AND inbox_id IS NULL))))) IS TRUE)""")
    op.execute("""ALTER TABLE platform.inbox_events ADD COLUMN material_result jsonb,ADD COLUMN material_claim_token uuid,
      ADD CONSTRAINT inbox_material_identity_key UNIQUE(workspace_id,id,connection_id,bot_identity,event_id),
      DROP CONSTRAINT inbox_events_check""")
    op.execute(f"""ALTER TABLE platform.inbox_events ADD CONSTRAINT inbox_events_check CHECK(
      ((material_result IS NULL AND material_claim_token IS NULL AND ({OLD_INBOX_CHECK})) OR
      (status='PROCESSED' AND result_code='MATERIAL_PROCESSED' AND message_id IS NULL AND completed_at IS NOT NULL
        AND material_claim_token IS NOT NULL AND platform.material_result_valid(material_result) IS TRUE)) IS TRUE)""")
    op.execute("""CREATE TABLE platform.telegram_provenance(
      receipt_id uuid PRIMARY KEY,codec smallint NOT NULL DEFAULT 2 CHECK(codec=2),
      bot_identity text NOT NULL,update_id text NOT NULL,workspace_id uuid,connection_id uuid,inbox_id uuid,
      projection jsonb NOT NULL,material_enabled boolean NOT NULL,
      UNIQUE(workspace_id,receipt_id),UNIQUE(workspace_id,inbox_id),
      FOREIGN KEY(receipt_id) REFERENCES platform.telegram_update_receipts(id) ON DELETE RESTRICT,
      FOREIGN KEY(receipt_id,codec,bot_identity,update_id,workspace_id,connection_id,inbox_id)
        REFERENCES platform.telegram_update_receipts(id,codec,bot_identity,update_id,workspace_id,connection_id,inbox_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,inbox_id,connection_id,bot_identity,update_id)
        REFERENCES platform.inbox_events(workspace_id,id,connection_id,bot_identity,event_id) ON DELETE RESTRICT,
      CHECK(projection=platform.telegram_validate_v2(bot_identity,projection)),
      CHECK((workspace_id IS NULL AND connection_id IS NULL AND inbox_id IS NULL AND projection->>'discriminator'='UNSUPPORTED') OR
        (workspace_id IS NOT NULL AND connection_id IS NOT NULL AND projection->>'discriminator'<>'UNSUPPORTED')))
      """)
    op.execute("""ALTER TABLE app.messages
      ADD CONSTRAINT messages_material_identity_key UNIQUE(workspace_id,id,connection_id,conversation_id,provider_chat_id,direction),
      ADD CONSTRAINT messages_material_inbound_key UNIQUE(workspace_id,id,provider_message_id,direction);
      ALTER TABLE app.outbox_events ADD CONSTRAINT outbox_material_sent_key
        UNIQUE(workspace_id,id,message_id,connection_id,status,provider_message_id);
      ALTER TABLE app.conversation_turns ADD COLUMN material_invalidated boolean NOT NULL DEFAULT false""")
    op.execute("""CREATE TABLE platform.message_material_targets(
      workspace_id uuid NOT NULL,id uuid NOT NULL DEFAULT uuidv7(),connection_id uuid NOT NULL,
      provider_chat_id text NOT NULL CHECK(platform.telegram_numeric_id(provider_chat_id)),
      provider_message_id text NOT NULL CHECK(platform.telegram_numeric_id(provider_message_id)),
      message_id uuid,conversation_id uuid,client_id uuid,direction text,outbox_id uuid,
      inbound_provider_id text,required_sent text,
      quarantined boolean NOT NULL DEFAULT false,original_grouping_closed boolean NOT NULL DEFAULT false,origin_identity jsonb,
      deleted boolean NOT NULL DEFAULT false,undated_seen boolean NOT NULL DEFAULT false,
      max_edit_at timestamptz CHECK(isfinite(max_edit_at)),candidate jsonb,dated_conflict boolean NOT NULL DEFAULT false,
      delete_receipt uuid,undated_receipt uuid,candidate_receipt uuid,conflict_receipt uuid,
      current_material jsonb CHECK(current_material IS NULL OR platform.material_state_valid(current_material)),
      PRIMARY KEY(workspace_id,id),UNIQUE(workspace_id,connection_id,provider_chat_id,provider_message_id),
      UNIQUE(workspace_id,id,message_id),
      FOREIGN KEY(workspace_id,connection_id) REFERENCES app.channel_connections(workspace_id,id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,message_id,connection_id,conversation_id,provider_chat_id,direction)
        REFERENCES app.messages(workspace_id,id,connection_id,conversation_id,provider_chat_id,direction) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,conversation_id,client_id) REFERENCES app.conversations(workspace_id,id,client_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,message_id,inbound_provider_id,direction)
        REFERENCES app.messages(workspace_id,id,provider_message_id,direction) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,outbox_id,message_id,connection_id,required_sent,provider_message_id)
        REFERENCES app.outbox_events(workspace_id,id,message_id,connection_id,status,provider_message_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,delete_receipt) REFERENCES platform.telegram_provenance(workspace_id,receipt_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,undated_receipt) REFERENCES platform.telegram_provenance(workspace_id,receipt_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,candidate_receipt) REFERENCES platform.telegram_provenance(workspace_id,receipt_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,conflict_receipt) REFERENCES platform.telegram_provenance(workspace_id,receipt_id) ON DELETE RESTRICT,
      CHECK((message_id IS NULL AND conversation_id IS NULL AND client_id IS NULL AND direction IS NULL AND outbox_id IS NULL
        AND inbound_provider_id IS NULL AND required_sent IS NULL AND current_material IS NULL) OR
        (message_id IS NOT NULL AND conversation_id IS NOT NULL AND client_id IS NOT NULL AND direction IS NOT NULL
          AND current_material IS NOT NULL AND NOT quarantined AND
          ((direction='INBOUND' AND inbound_provider_id=provider_message_id AND inbound_provider_id IS NOT NULL AND outbox_id IS NULL AND required_sent IS NULL) OR
           (direction='OUTBOUND' AND inbound_provider_id IS NULL AND outbox_id IS NOT NULL AND required_sent='SENT' AND required_sent IS NOT NULL)))),
      CHECK((deleted AND delete_receipt IS NOT NULL AND NOT undated_seen AND NOT dated_conflict AND max_edit_at IS NULL AND candidate IS NULL
        AND undated_receipt IS NULL AND candidate_receipt IS NULL AND conflict_receipt IS NULL) OR
        (NOT deleted AND delete_receipt IS NULL AND (undated_seen=(undated_receipt IS NOT NULL)) AND
          ((max_edit_at IS NULL AND candidate IS NULL AND candidate_receipt IS NULL AND conflict_receipt IS NULL AND NOT dated_conflict) OR
           (max_edit_at IS NOT NULL AND candidate_receipt IS NOT NULL AND
             ((dated_conflict AND candidate IS NULL AND conflict_receipt IS NOT NULL) OR
              (NOT dated_conflict AND candidate IS NOT NULL AND conflict_receipt IS NULL AND platform.material_content_valid(candidate) IS TRUE)))))))""")
    op.execute("""CREATE UNIQUE INDEX message_material_bound_key ON platform.message_material_targets(workspace_id,message_id) WHERE message_id IS NOT NULL;
      ALTER TABLE app.audit_events ADD COLUMN material_target_id uuid GENERATED ALWAYS AS
        (CASE WHEN event_type='MESSAGE_MATERIAL_CHANGED' THEN (payload->>'target_id')::uuid END) STORED,
      ADD COLUMN material_source_receipt_id uuid GENERATED ALWAYS AS
        (CASE WHEN event_type='MESSAGE_MATERIAL_CHANGED' THEN (payload->>'source_receipt_id')::uuid END) STORED,
      ADD CONSTRAINT audit_material_target_fkey FOREIGN KEY(workspace_id,material_target_id,object_id)
        REFERENCES platform.message_material_targets(workspace_id,id,message_id) ON DELETE RESTRICT,
      ADD CONSTRAINT audit_material_source_fkey FOREIGN KEY(workspace_id,material_source_receipt_id)
        REFERENCES platform.telegram_provenance(workspace_id,receipt_id) ON DELETE RESTRICT,
      ADD CONSTRAINT audit_material_ref_key UNIQUE(workspace_id,audit_event_id,object_id,event_type,object_version,material_target_id,material_source_receipt_id),
      DROP CONSTRAINT audit_events_discriminator_payload_check""")
    op.execute(f"""ALTER TABLE app.audit_events ADD CONSTRAINT audit_events_discriminator_payload_check CHECK(
      ({OLD_AUDIT_CHECK}) OR ((event_type='MESSAGE_MATERIAL_CHANGED' AND actor_kind='CHANNEL_EVENT'
        AND actor_user_account_id IS NULL AND object_type='MESSAGE' AND material_target_id IS NOT NULL AND material_source_receipt_id IS NOT NULL
        AND platform.material_object(payload,ARRAY['target_id','source_receipt_id','previous_version','accepted_version','reason'])
        AND payload->>'target_id'=material_target_id::text AND payload->>'source_receipt_id'=material_source_receipt_id::text
        AND jsonb_typeof(payload->'previous_version')='string' AND jsonb_typeof(payload->'accepted_version')='string'
        AND platform.telegram_numeric_id(payload->>'previous_version') AND platform.telegram_numeric_id(payload->>'accepted_version')
        AND (payload->>'previous_version')::numeric+1=object_version AND payload->>'accepted_version'=object_version::text
        AND payload->>'reason' IN ('CONTENT_CHANGED','DELETED','ORDER_UNCERTAIN','ORDER_RESTORED','UNSUPPORTED_CONTENT')) IS TRUE))""")
    op.execute("""CREATE TABLE platform.message_material_effects(
      workspace_id uuid NOT NULL,id uuid NOT NULL DEFAULT uuidv7(),target_id uuid NOT NULL,message_id uuid NOT NULL,
      source_receipt_id uuid NOT NULL,audit_event_id uuid NOT NULL,
      event_type text NOT NULL DEFAULT 'MESSAGE_MATERIAL_CHANGED' CHECK(event_type='MESSAGE_MATERIAL_CHANGED'),
      previous_version bigint NOT NULL CHECK(previous_version>0),accepted_version bigint NOT NULL CHECK(accepted_version::numeric=previous_version::numeric+1),
      reason text NOT NULL CHECK(reason IN ('CONTENT_CHANGED','DELETED','ORDER_UNCERTAIN','ORDER_RESTORED','UNSUPPORTED_CONTENT')),
      accepted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      PRIMARY KEY(workspace_id,id),UNIQUE(source_receipt_id,message_id),
      UNIQUE(workspace_id,id,target_id,message_id,source_receipt_id,previous_version,accepted_version),
      FOREIGN KEY(workspace_id,target_id,message_id) REFERENCES platform.message_material_targets(workspace_id,id,message_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,source_receipt_id) REFERENCES platform.telegram_provenance(workspace_id,receipt_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,audit_event_id,message_id,event_type,accepted_version,target_id,source_receipt_id)
        REFERENCES app.audit_events(workspace_id,audit_event_id,object_id,event_type,object_version,material_target_id,material_source_receipt_id) ON DELETE RESTRICT)""")
    op.execute("""CREATE TABLE platform.message_initial_suppressions(
      workspace_id uuid NOT NULL,id uuid NOT NULL DEFAULT uuidv7(),message_id uuid NOT NULL,target_id uuid NOT NULL,
      origin_inbox_id uuid NOT NULL,effect_id uuid NOT NULL,source_receipt_id uuid NOT NULL,
      previous_version bigint NOT NULL DEFAULT 1 CHECK(previous_version=1),accepted_version bigint NOT NULL DEFAULT 2 CHECK(accepted_version=2),
      initial_material jsonb NOT NULL,fold_witnesses uuid[] NOT NULL CHECK(cardinality(fold_witnesses) BETWEEN 1 AND 3),
      membership_disposition text NOT NULL CHECK(membership_disposition IN ('HIDDEN','INELIGIBLE_ORIGIN','ELIGIBLE_VISIBLE')),
      PRIMARY KEY(workspace_id,id),UNIQUE(workspace_id,message_id),
      UNIQUE(workspace_id,id,message_id,origin_inbox_id,membership_disposition),
      FOREIGN KEY(workspace_id,message_id) REFERENCES app.messages(workspace_id,id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,origin_inbox_id) REFERENCES platform.inbox_events(workspace_id,id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,effect_id,target_id,message_id,source_receipt_id,previous_version,accepted_version)
        REFERENCES platform.message_material_effects(workspace_id,id,target_id,message_id,source_receipt_id,previous_version,accepted_version) ON DELETE RESTRICT)""")
    op.execute("""ALTER TABLE app.conversation_turn_messages
      ADD COLUMN membership_form text,ADD COLUMN initial_suppression_id uuid,
      ADD COLUMN suppression_disposition text GENERATED ALWAYS AS
        (CASE WHEN membership_form='INITIAL_FOLD_SUPPRESSED' THEN 'ELIGIBLE_VISIBLE' END) STORED,
      ADD CONSTRAINT turn_member_suppression_fkey FOREIGN KEY(workspace_id,initial_suppression_id,message_id,origin_inbox_id,suppression_disposition)
        REFERENCES platform.message_initial_suppressions(workspace_id,id,message_id,origin_inbox_id,membership_disposition) ON DELETE RESTRICT,
      DROP CONSTRAINT conversation_turn_messages_check""")
    op.execute(f"""ALTER TABLE app.conversation_turn_messages ADD CONSTRAINT conversation_turn_messages_check CHECK(
      (membership_form IS NULL AND initial_suppression_id IS NULL AND ({OLD_MEMBER_CHECK})) OR
      (membership_form='INITIAL_FOLD_SUPPRESSED' AND membership_form IS NOT NULL AND initial_suppression_id IS NOT NULL
        AND content_type='IMAGE_REFERENCE' AND direction='INBOUND' AND file_id IS NULL) IS TRUE)""")
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY material_migrator ON {table} TO asm_migrator USING(true) WITH CHECK(true)"
        )
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC,asm_runtime")
        if table != "platform.message_material_targets":
            op.execute(
                f"CREATE TRIGGER material_immutable BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION platform.turn_immutable()"
            )
    op.execute("""CREATE TRIGGER material_receipt_immutable BEFORE UPDATE ON platform.telegram_update_receipts
      FOR EACH ROW EXECUTE FUNCTION platform.messaging_immutable('codec')""")


def _ingress() -> None:
    op.execute("""CREATE FUNCTION platform.telegram_receipt_json(r platform.telegram_update_receipts,code text) RETURNS jsonb
      LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      SELECT jsonb_build_object('code',code,'receipt_id',r.id,'workspace_id',r.workspace_id,'connection_id',r.connection_id,
        'inbox_id',r.inbox_id,'job_id',(SELECT id FROM platform.messaging_jobs WHERE workspace_id=r.workspace_id AND inbox_id=r.inbox_id),
        'accepted_at',r.received_at,'result_code',r.result_code) $$""")
    op.execute("""CREATE FUNCTION platform.telegram_replay_v1(p_bot text,p_projection jsonb) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE p jsonb; r platform.telegram_update_receipts%ROWTYPE;
      BEGIN
        PERFORM platform.turn_require_isolation();
        p:=platform.telegram_validate_projection(p_bot,p_projection);
        SELECT * INTO r FROM platform.telegram_update_receipts WHERE bot_identity=p_bot AND update_id=p->>'update_id' AND codec IS NULL;
        IF NOT FOUND THEN RETURN NULL; END IF;
        IF r.fingerprint<>platform.telegram_fingerprint(p_bot,p) THEN RAISE EXCEPTION 'EVENT_ID_CONFLICT' USING ERRCODE='P2001'; END IF;
        RETURN platform.telegram_receipt_json(r,'DUPLICATE');
      END $$""")
    op.execute("""CREATE OR REPLACE FUNCTION platform.telegram_ingest(p_bot text,p_projection jsonb,p_correlation uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE p jsonb; l jsonb; e jsonb; r platform.telegram_update_receipts%ROWTYPE;
        route platform.channel_routes%ROWTYPE; s platform.telegram_connection_state%ROWTYPE;
        outcome text; inbox uuid; received timestamptz; enabled boolean:=false;
      BEGIN
        PERFORM platform.turn_require_isolation();
        IF p_correlation IS NULL THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        -- Final locked namespace recheck also accepts only replay of a legacy projection.
        l:=platform.telegram_validate_projection(p_bot,CASE WHEN p_projection ? 'legacy_v1' THEN p_projection->'legacy_v1' ELSE p_projection END);
        PERFORM pg_advisory_xact_lock(hashtextextended(p_bot||':'||(l->>'update_id'),2008));
        SELECT * INTO r FROM platform.telegram_update_receipts WHERE bot_identity=p_bot AND update_id=l->>'update_id';
        IF FOUND AND r.codec IS NULL THEN
          IF r.fingerprint<>platform.telegram_fingerprint(p_bot,l) THEN RAISE EXCEPTION 'EVENT_ID_CONFLICT' USING ERRCODE='P2001'; END IF;
          RETURN platform.telegram_receipt_json(r,'DUPLICATE');
        END IF;
        p:=platform.telegram_validate_v2(p_bot,p_projection);
        IF r.id IS NOT NULL THEN
          IF r.fingerprint<>platform.telegram_fingerprint_v2(p_bot,p) THEN RAISE EXCEPTION 'EVENT_ID_CONFLICT' USING ERRCODE='P2001'; END IF;
          RETURN platform.telegram_receipt_json(r,'DUPLICATE');
        END IF;
        received:=clock_timestamp();
        IF p->>'discriminator'='UNSUPPORTED' THEN outcome:='IGNORED_UNSUPPORTED';
        ELSE
          SELECT * INTO route FROM platform.channel_routes WHERE provider='TELEGRAM' AND bot_identity=p_bot AND route_key=p->>'connection';
          IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P2001'; END IF;
          PERFORM 1 FROM app.channel_connections WHERE workspace_id=route.workspace_id AND id=route.connection_id FOR SHARE;
          SELECT * INTO STRICT s FROM platform.telegram_connection_state WHERE workspace_id=route.workspace_id AND connection_id=route.connection_id;
          enabled:=s.material_enabled;
          IF p->>'discriminator'='LIFECYCLE' THEN
            IF l->>'owner_user_id' IS DISTINCT FROM s.owner_user_id THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
            UPDATE platform.telegram_connection_state SET generation=generation+1,observation_version=observation_version+1
              WHERE workspace_id=s.workspace_id AND connection_id=s.connection_id;
            outcome:='LIFECYCLE_INVALIDATED';
          ELSIF p->>'discriminator' IN ('EDIT','DELETE') THEN
            IF NOT enabled THEN outcome:=CASE p->>'discriminator' WHEN 'EDIT' THEN 'IGNORED_MESSAGE_EDITED' ELSE 'IGNORED_MESSAGE_DELETED' END;
            ELSE
              outcome:='QUEUED';
              e:=CASE WHEN p->>'discriminator'='EDIT' THEN l->'event' ELSE jsonb_build_object(
                'provider','TELEGRAM','bot_identity',p_bot,'event_id',p->>'update_id','kind','MESSAGE_DELETED',
                'external_connection_id',p->>'connection','chat_id',p->>'chat_id','message_id',NULL,'sender_id',NULL,
                'occurred_at',NULL,'text',NULL,'image_file_id',NULL,'media_group_id',NULL) END;
            END IF;
          ELSE
            e:=l->'event';
            IF l->>'sender_business_bot_id' IS NOT NULL THEN outcome:='IGNORED_ECHO';
            ELSIF e->>'sender_id'=s.owner_user_id THEN outcome:='IGNORED_NATIVE_OWNER_MESSAGE';
            ELSIF e->>'sender_id'=s.bot_identity OR e->>'kind'<>'CLIENT_MESSAGE' THEN outcome:='IGNORED_UNSUPPORTED';
            ELSE outcome:='QUEUED'; END IF;
          END IF;
          IF outcome='QUEUED' THEN
            -- Capture mutations under the same C barrier without synthesizing original ingress.
            PERFORM 1 FROM app.conversations WHERE workspace_id=route.workspace_id AND connection_id=route.connection_id
              AND provider_chat_id=p->>'chat_id' FOR NO KEY UPDATE;
            INSERT INTO platform.inbox_events(workspace_id,connection_id,provider,bot_identity,external_connection_id,event_id,normalized_event,event_fingerprint,correlation_id,received_at)
              VALUES(route.workspace_id,route.connection_id,'TELEGRAM',p_bot,p->>'connection',p->>'update_id',e,platform.messaging_fingerprint(e,false),p_correlation,received) RETURNING id INTO inbox;
            INSERT INTO platform.messaging_jobs(workspace_id,connection_id,kind,inbox_id,correlation_id)
              VALUES(route.workspace_id,route.connection_id,'PROCESS_INBOX',inbox,p_correlation);
          END IF;
        END IF;
        INSERT INTO platform.telegram_update_receipts(bot_identity,update_id,fingerprint,kind,result_code,workspace_id,connection_id,inbox_id,received_at,codec)
          VALUES(p_bot,p->>'update_id',platform.telegram_fingerprint_v2(p_bot,p),l->>'kind',outcome,route.workspace_id,route.connection_id,inbox,received,2) RETURNING * INTO r;
        INSERT INTO platform.telegram_provenance(receipt_id,bot_identity,update_id,workspace_id,connection_id,inbox_id,projection,material_enabled)
          VALUES(r.id,p_bot,r.update_id,r.workspace_id,r.connection_id,r.inbox_id,p,enabled);
        RETURN platform.telegram_receipt_json(r,'ACCEPTED');
      END $$""")


def _integrity() -> None:
    op.execute("""CREATE FUNCTION platform.material_integrity() RETURNS trigger
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE r platform.telegram_update_receipts%ROWTYPE; s platform.telegram_provenance%ROWTYPE;
        i platform.inbox_events%ROWTYPE; expected jsonb; result jsonb; ids text[]; k integer;
      BEGIN
        IF TG_TABLE_NAME='telegram_update_receipts' THEN
          SELECT * INTO r FROM platform.telegram_update_receipts WHERE id=CASE WHEN TG_OP='DELETE' THEN OLD.id ELSE NEW.id END;
        ELSIF TG_TABLE_NAME='telegram_provenance' THEN
          SELECT * INTO r FROM platform.telegram_update_receipts WHERE id=CASE WHEN TG_OP='DELETE' THEN OLD.receipt_id ELSE NEW.receipt_id END;
        ELSE
          IF TG_OP='UPDATE' AND OLD.status<>'PENDING' AND (NEW.material_result,NEW.material_claim_token) IS DISTINCT FROM (OLD.material_result,OLD.material_claim_token) THEN
            RAISE EXCEPTION 'immutable material result/token' USING ERRCODE='23514'; END IF;
          SELECT * INTO r FROM platform.telegram_update_receipts WHERE workspace_id=CASE WHEN TG_OP='DELETE' THEN OLD.workspace_id ELSE NEW.workspace_id END AND inbox_id=CASE WHEN TG_OP='DELETE' THEN OLD.id ELSE NEW.id END;
        END IF;
        IF r.id IS NULL THEN
          IF TG_TABLE_NAME='inbox_events' THEN
            IF TG_OP<>'DELETE' AND (NEW.material_result IS NOT NULL OR NEW.material_claim_token IS NOT NULL) THEN RAISE EXCEPTION 'missing V2 binding' USING ERRCODE='23514'; END IF;
          END IF;
          RETURN NULL;
        END IF;
        SELECT * INTO s FROM platform.telegram_provenance WHERE receipt_id=r.id;
        IF r.codec IS NULL THEN
          IF s.receipt_id IS NOT NULL THEN RAISE EXCEPTION 'V1 sidecar' USING ERRCODE='23514'; END IF;
          IF EXISTS(SELECT 1 FROM platform.inbox_events WHERE workspace_id=r.workspace_id AND id=r.inbox_id
            AND (material_result IS NOT NULL OR material_claim_token IS NOT NULL)) THEN
            RAISE EXCEPTION 'V1 material completion' USING ERRCODE='23514'; END IF;
          RETURN NULL;
        END IF;
        IF s.receipt_id IS NULL OR (s.codec,s.bot_identity,s.update_id,s.workspace_id,s.connection_id,s.inbox_id) IS DISTINCT FROM
          (r.codec,r.bot_identity,r.update_id,r.workspace_id,r.connection_id,r.inbox_id) OR
          r.fingerprint<>platform.telegram_fingerprint_v2(r.bot_identity,s.projection) THEN
          RAISE EXCEPTION 'invalid provenance binding' USING ERRCODE='23514'; END IF;
        IF r.inbox_id IS NOT NULL THEN
          SELECT * INTO STRICT i FROM platform.inbox_events WHERE workspace_id=r.workspace_id AND id=r.inbox_id;
          expected:=s.projection->'legacy_v1'->'event';
          IF s.projection->>'discriminator'='DELETE' THEN
            expected:=jsonb_build_object('provider','TELEGRAM','bot_identity',r.bot_identity,'event_id',r.update_id,'kind','MESSAGE_DELETED',
              'external_connection_id',s.projection->>'connection','chat_id',s.projection->>'chat_id','message_id',NULL,'sender_id',NULL,
              'occurred_at',NULL,'text',NULL,'image_file_id',NULL,'media_group_id',NULL);
          END IF;
          IF i.normalized_event IS DISTINCT FROM expected OR i.event_fingerprint<>platform.messaging_fingerprint(expected,false)
            OR (i.provider,i.bot_identity,i.event_id,i.external_connection_id) IS DISTINCT FROM
              ('TELEGRAM',r.bot_identity,r.update_id,s.projection->>'connection') OR
            (s.projection->>'discriminator' IN ('EDIT','DELETE') AND NOT s.material_enabled) THEN
            RAISE EXCEPTION 'invalid queued provenance' USING ERRCODE='23514'; END IF;
          IF i.result_code='MATERIAL_PROCESSED' THEN
            IF s.projection->>'discriminator' NOT IN ('EDIT','DELETE') THEN RAISE EXCEPTION 'invalid mutation completion' USING ERRCODE='23514'; END IF;
            IF s.projection->>'discriminator'='EDIT' THEN ids:=ARRAY[s.projection->>'message_id'];
            ELSE SELECT array_agg(v ORDER BY v::bigint) INTO ids FROM (SELECT DISTINCT value AS v FROM jsonb_array_elements_text(s.projection->'legacy_v1'->'deleted_message_ids')) q; END IF;
            IF jsonb_array_length(i.material_result)<>cardinality(ids) THEN RAISE EXCEPTION 'invalid target count' USING ERRCODE='23514'; END IF;
            k:=0;
            FOR result IN SELECT value FROM jsonb_array_elements(i.material_result) LOOP
              k:=k+1;
              IF result->>'target_id' IS NOT NULL AND NOT EXISTS(SELECT 1 FROM platform.message_material_targets t
                WHERE t.workspace_id=r.workspace_id AND t.id=(result->>'target_id')::uuid AND t.connection_id=r.connection_id
                  AND t.provider_chat_id=s.projection->>'chat_id' AND t.provider_message_id=ids[k]
                  AND (result->>'message_id' IS NULL OR t.message_id=(result->>'message_id')::uuid)) THEN
                RAISE EXCEPTION 'invalid target result identity' USING ERRCODE='23514'; END IF;
              IF result->>'code'='APPLIED' AND NOT EXISTS(SELECT 1 FROM platform.message_material_effects f
                WHERE f.workspace_id=r.workspace_id AND f.id=(result->>'effect_id')::uuid AND f.source_receipt_id=r.id
                  AND f.target_id=(result->>'target_id')::uuid AND f.message_id=(result->>'message_id')::uuid
                  AND f.audit_event_id=(result->>'audit_event_id')::uuid AND f.previous_version::text=result->>'previous_version'
                  AND f.accepted_version::text=result->>'accepted_version') THEN
                RAISE EXCEPTION 'invalid applied result' USING ERRCODE='23514'; END IF;
            END LOOP;
          ELSIF i.status='PROCESSED' AND s.projection->>'discriminator' IN ('EDIT','DELETE') THEN
            RAISE EXCEPTION 'invalid legacy completion for mutation' USING ERRCODE='23514';
          END IF;
        END IF;
        RETURN NULL;
      END $$""")
    for table in (
        "platform.telegram_update_receipts",
        "platform.telegram_provenance",
        "platform.inbox_events",
    ):
        op.execute(
            f"CREATE CONSTRAINT TRIGGER material_integrity AFTER INSERT OR UPDATE OR DELETE ON {table} DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.material_integrity()"
        )
    op.execute("""CREATE FUNCTION platform.material_target_check() RETURNS trigger
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE source uuid; p jsonb; q jsonb; current_target platform.message_material_targets%ROWTYPE; expected jsonb;
      BEGIN
        IF TG_WHEN='AFTER' THEN
          SELECT * INTO current_target FROM platform.message_material_targets WHERE workspace_id=NEW.workspace_id AND id=NEW.id;
          IF current_target.message_id IS NOT NULL THEN
            expected:=CASE WHEN current_target.deleted THEN '{"state":"DELETED","content":null}'::jsonb
              WHEN current_target.undated_seen OR current_target.dated_conflict THEN '{"state":"ORDER_UNCERTAIN","content":null}'::jsonb
              WHEN current_target.candidate IS NOT NULL THEN platform.material_semantic(current_target.candidate) ELSE current_target.current_material END;
            IF current_target.current_material IS DISTINCT FROM expected THEN RAISE EXCEPTION 'unapplied material fact' USING ERRCODE='23514'; END IF;
          END IF;
          RETURN NULL;
        END IF;
        IF TG_OP='UPDATE' THEN
          IF (NEW.workspace_id,NEW.id,NEW.connection_id,NEW.provider_chat_id,NEW.provider_message_id) IS DISTINCT FROM
            (OLD.workspace_id,OLD.id,OLD.connection_id,OLD.provider_chat_id,OLD.provider_message_id) OR
            (OLD.message_id IS NOT NULL AND (NEW.message_id,NEW.conversation_id,NEW.client_id,NEW.direction,NEW.outbox_id,NEW.inbound_provider_id,NEW.required_sent) IS DISTINCT FROM
             (OLD.message_id,OLD.conversation_id,OLD.client_id,OLD.direction,OLD.outbox_id,OLD.inbound_provider_id,OLD.required_sent)) OR
            (OLD.quarantined AND NOT NEW.quarantined) OR (OLD.original_grouping_closed AND NOT NEW.original_grouping_closed) OR (OLD.deleted AND NOT NEW.deleted) OR
            (OLD.undated_seen AND NOT NEW.undated_seen AND NOT NEW.deleted) THEN
            RAISE EXCEPTION 'immutable target identity/safety' USING ERRCODE='23514'; END IF;
        END IF;
        FOREACH source IN ARRAY ARRAY[NEW.delete_receipt,NEW.undated_receipt,NEW.candidate_receipt,NEW.conflict_receipt] LOOP
          IF source IS NULL THEN CONTINUE; END IF;
          SELECT projection INTO p FROM platform.telegram_provenance WHERE workspace_id=NEW.workspace_id AND receipt_id=source AND connection_id=NEW.connection_id AND material_enabled;
          IF p IS NULL OR p->>'chat_id' IS DISTINCT FROM NEW.provider_chat_id OR NOT
            ((p->>'discriminator'='EDIT' AND p->>'message_id'=NEW.provider_message_id) OR
             (p->>'discriminator'='DELETE' AND p->'legacy_v1'->'deleted_message_ids' ? NEW.provider_message_id)) THEN
            RAISE EXCEPTION 'invalid material witness' USING ERRCODE='23514'; END IF;
          IF NEW.message_id IS NOT NULL AND platform.material_identity(NEW.workspace_id,NEW.message_id,p) IS NOT TRUE THEN
            RAISE EXCEPTION 'invalid bound witness identity' USING ERRCODE='23514'; END IF;
          IF (source=NEW.delete_receipt AND p->>'discriminator'<>'DELETE') OR
            (source=NEW.undated_receipt AND (p->>'discriminator'<>'EDIT' OR
              (p->>'edited_at' IS NOT NULL AND (p->>'edited_at')::timestamptz >= (p->>'sent_at')::timestamptz))) OR
            (source IN (NEW.candidate_receipt,NEW.conflict_receipt) AND (p->>'discriminator'<>'EDIT' OR
              (p->>'edited_at')::timestamptz IS DISTINCT FROM NEW.max_edit_at)) OR
            (source=NEW.candidate_receipt AND NOT NEW.dated_conflict AND p->'content' IS DISTINCT FROM NEW.candidate) THEN
            RAISE EXCEPTION 'invalid folded witness basis' USING ERRCODE='23514'; END IF;
        END LOOP;
        IF NEW.dated_conflict THEN
          SELECT projection INTO p FROM platform.telegram_provenance WHERE receipt_id=NEW.candidate_receipt;
          SELECT projection INTO q FROM platform.telegram_provenance WHERE receipt_id=NEW.conflict_receipt;
          IF platform.material_semantic(p->'content') IS NOT DISTINCT FROM platform.material_semantic(q->'content') THEN
            RAISE EXCEPTION 'invalid equal-date conflict' USING ERRCODE='23514'; END IF;
        END IF;
        RETURN NEW;
      END $$""")
    op.execute(
        "CREATE TRIGGER material_target_check BEFORE INSERT OR UPDATE ON platform.message_material_targets FOR EACH ROW EXECUTE FUNCTION platform.material_target_check()"
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER material_target_consistency AFTER INSERT OR UPDATE ON platform.message_material_targets DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.material_target_check()"
    )
    op.execute("""CREATE FUNCTION platform.material_no_file() RETURNS trigger
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$ BEGIN
        IF EXISTS(SELECT 1 FROM platform.message_initial_suppressions WHERE workspace_id=NEW.workspace_id AND message_id=NEW.message_id) THEN
          RAISE EXCEPTION 'initial original file suppressed' USING ERRCODE='23514'; END IF; RETURN NEW;
      END $$""")
    op.execute(
        "CREATE TRIGGER material_no_file BEFORE INSERT ON app.file_objects FOR EACH ROW EXECUTE FUNCTION platform.material_no_file()"
    )


def _material() -> None:
    op.execute("""CREATE FUNCTION platform.message_effective(ws uuid,p_message uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE m app.messages%ROWTYPE; material jsonb; c jsonb; availability text; status text;
      BEGIN
        SELECT * INTO STRICT m FROM app.messages WHERE workspace_id=ws AND id=p_message;
        SELECT current_material INTO material FROM platform.message_material_targets WHERE workspace_id=ws AND message_id=m.id;
        material:=coalesce(material,jsonb_build_object('state','VISIBLE','content',CASE WHEN m.content_type='TEXT'
          THEN jsonb_build_object('kind','TEXT','text',m.text) ELSE jsonb_build_object('kind','PHOTO','caption',m.text,'selected_file_id',m.image_file_id) END));
        c:=material->'content';
        IF material->>'state'<>'VISIBLE' THEN availability:='HIDDEN'; c:=NULL;
        ELSIF c->>'kind'='TEXT' THEN availability:='NOT_APPLICABLE';
        ELSIF c->>'selected_file_id' IS DISTINCT FROM m.image_file_id THEN availability:='MEDIA_REPLACED_UNAVAILABLE';
        ELSE
          SELECT f.status INTO status FROM app.file_objects f WHERE f.workspace_id=ws AND f.message_id=m.id;
          availability:=CASE WHEN status IS NULL THEN 'ORIGINAL_NOT_FETCHED' ELSE 'ORIGINAL_'||status END;
        END IF;
        RETURN jsonb_build_object('schema_version',1,'state',material->>'state','content_type',c->>'kind',
          'text',CASE WHEN c->>'kind'='TEXT' THEN c->>'text' ELSE c->>'caption' END,'image_availability',availability,'changed',m.version>1);
      END $$""")
    op.execute("""CREATE FUNCTION platform.material_turn_usable(ws uuid,p_turn uuid) RETURNS boolean
      LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      SELECT coalesce((SELECT NOT t.material_invalidated AND EXISTS(SELECT 1 FROM app.conversation_turn_messages m
        WHERE m.workspace_id=ws AND m.turn_id=t.id AND platform.message_effective(ws,m.message_id)->>'state'='VISIBLE')
        FROM app.conversation_turns t WHERE t.workspace_id=ws AND t.id=p_turn),false) $$""")
    op.execute("""CREATE FUNCTION platform.material_identity(ws uuid,p_message uuid,p jsonb) RETURNS boolean
      LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE m app.messages%ROWTYPE; c app.conversations%ROWTYPE; s platform.telegram_connection_state%ROWTYPE;
        conn app.channel_connections%ROWTYPE; sender text;
      BEGIN
        SELECT * INTO STRICT m FROM app.messages WHERE workspace_id=ws AND id=p_message;
        SELECT * INTO STRICT c FROM app.conversations WHERE workspace_id=ws AND id=m.conversation_id;
        SELECT * INTO STRICT conn FROM app.channel_connections WHERE workspace_id=ws AND id=m.connection_id;
        SELECT * INTO s FROM platform.telegram_connection_state WHERE workspace_id=ws AND connection_id=m.connection_id;
        IF s.connection_id IS NULL OR (p->>'bot',p->>'connection',p->>'chat_id') IS DISTINCT FROM
          (s.bot_identity,conn.external_connection_id,m.provider_chat_id) OR c.connection_id<>m.connection_id OR c.business_id<>conn.business_id THEN RETURN false; END IF;
        IF p->>'discriminator'='DELETE' THEN RETURN true; END IF;
        IF p->>'chat_type'<>'PRIVATE' THEN RETURN false; END IF;
        sender:=p->'origin'->>'sender_id';
        IF m.direction='INBOUND' THEN
          RETURN p->'origin'->>'sender_is_bot'='FALSE' AND p->'origin'->>'sender_business_bot_id' IS NULL
            AND (p->>'sent_at')::timestamptz=m.occurred_at AND EXISTS(SELECT 1 FROM app.client_identities
              WHERE workspace_id=ws AND id=c.identity_id AND client_id=c.client_id AND provider='TELEGRAM' AND external_user_id=sender);
        END IF;
        RETURN EXISTS(SELECT 1 FROM app.outbox_events WHERE workspace_id=ws AND message_id=m.id AND status='SENT'
          AND provider_message_id=p->>'message_id') AND
          (p->'origin'->>'sender_business_bot_id'=s.bot_identity OR
            (p->'origin'->>'sender_business_bot_id' IS NULL AND sender=s.owner_user_id AND p->'origin'->>'sender_is_bot'='FALSE'));
      END $$""")
    op.execute("""CREATE FUNCTION platform.material_fold(ws uuid,p_target uuid,p_source uuid) RETURNS text
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE t platform.message_material_targets%ROWTYPE; p jsonb; edit_at timestamptz; identity jsonb;
      BEGIN
        SELECT * INTO STRICT t FROM platform.message_material_targets WHERE workspace_id=ws AND id=p_target FOR UPDATE;
        SELECT projection INTO STRICT p FROM platform.telegram_provenance WHERE workspace_id=ws AND receipt_id=p_source;
        IF t.quarantined OR (t.message_id IS NOT NULL AND platform.material_identity(ws,t.message_id,p) IS NOT TRUE) THEN RETURN 'IDENTITY_CONFLICT'; END IF;
        IF t.deleted THEN RETURN 'ALREADY_DELETED'; END IF;
        IF p->>'discriminator'='DELETE' THEN
          UPDATE platform.message_material_targets SET deleted=true,delete_receipt=p_source,undated_seen=false,max_edit_at=NULL,candidate=NULL,
            dated_conflict=false,undated_receipt=NULL,candidate_receipt=NULL,conflict_receipt=NULL,origin_identity=NULL WHERE workspace_id=ws AND id=t.id;
          RETURN 'DELETED';
        END IF;
        identity:=jsonb_build_object('sender',(p->'origin')-'offline','sent_at',p->'sent_at','chat_type',p->'chat_type');
        IF t.message_id IS NULL AND t.origin_identity IS NOT NULL AND t.origin_identity<>identity THEN
          UPDATE platform.message_material_targets SET quarantined=true WHERE workspace_id=ws AND id=t.id;
          RETURN 'IDENTITY_CONFLICT';
        END IF;
        UPDATE platform.message_material_targets SET origin_identity=coalesce(origin_identity,identity) WHERE workspace_id=ws AND id=t.id;
        edit_at:=(p->>'edited_at')::timestamptz;
        IF edit_at IS NULL OR edit_at<(p->>'sent_at')::timestamptz THEN
          IF NOT t.undated_seen THEN UPDATE platform.message_material_targets SET undated_seen=true,undated_receipt=p_source WHERE workspace_id=ws AND id=t.id; END IF;
          RETURN 'ALREADY_UNCERTAIN';
        ELSIF t.max_edit_at IS NOT NULL AND edit_at<t.max_edit_at THEN RETURN 'STALE_EDIT';
        ELSIF t.max_edit_at IS NULL OR edit_at>t.max_edit_at THEN
          UPDATE platform.message_material_targets SET max_edit_at=edit_at,candidate=p->'content',candidate_receipt=p_source,dated_conflict=false,conflict_receipt=NULL WHERE workspace_id=ws AND id=t.id;
        ELSIF t.dated_conflict THEN RETURN 'ALREADY_UNCERTAIN';
        ELSIF platform.material_semantic(t.candidate) IS DISTINCT FROM platform.material_semantic(p->'content') THEN
          UPDATE platform.message_material_targets SET candidate=NULL,dated_conflict=true,conflict_receipt=p_source WHERE workspace_id=ws AND id=t.id;
          RETURN 'ALREADY_UNCERTAIN';
        END IF;
        RETURN CASE WHEN t.undated_seen THEN 'ALREADY_UNCERTAIN' ELSE 'NOOP_CONTENT' END;
      END $$""")
    op.execute("""CREATE FUNCTION platform.material_apply_context(ws uuid,p_message uuid,corr uuid) RETURNS void
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE cid uuid;
      BEGIN
        SELECT conversation_id INTO STRICT cid FROM app.messages WHERE workspace_id=ws AND id=p_message;
        PERFORM 1 FROM app.conversations WHERE workspace_id=ws AND id=cid FOR NO KEY UPDATE;
        PERFORM 1 FROM app.messages WHERE workspace_id=ws AND id=p_message FOR NO KEY UPDATE;
        PERFORM 1 FROM app.conversation_turns WHERE workspace_id=ws AND id IN
          (SELECT turn_id FROM app.conversation_turn_messages WHERE workspace_id=ws AND message_id=p_message) ORDER BY id FOR NO KEY UPDATE;
        UPDATE app.messages SET version=version+1 WHERE workspace_id=ws AND id=p_message;
        UPDATE app.conversations SET version=version+1 WHERE workspace_id=ws AND id=cid;
        PERFORM platform.material_bump_turns(ws,ARRAY[p_message],corr);
      END $$""")
    op.execute("""CREATE FUNCTION platform.material_apply(ws uuid,p_target uuid,corr uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE t platform.message_material_targets%ROWTYPE; material jsonb; source uuid; reason text;
        m app.messages%ROWTYPE; audit uuid; effect uuid; before_version bigint;
      BEGIN
        SELECT * INTO STRICT t FROM platform.message_material_targets WHERE workspace_id=ws AND id=p_target FOR UPDATE;
        IF t.message_id IS NULL OR t.quarantined THEN RETURN NULL; END IF;
        material:=CASE WHEN t.deleted THEN '{"state":"DELETED","content":null}'::jsonb
          WHEN t.undated_seen OR t.dated_conflict THEN '{"state":"ORDER_UNCERTAIN","content":null}'::jsonb
          WHEN t.candidate IS NOT NULL THEN platform.material_semantic(t.candidate) ELSE t.current_material END;
        IF material=t.current_material THEN RETURN NULL; END IF;
        source:=coalesce(t.delete_receipt,t.undated_receipt,t.conflict_receipt,t.candidate_receipt);
        IF source IS NULL THEN RAISE EXCEPTION 'invalid material source' USING ERRCODE='23514'; END IF;
        SELECT * INTO STRICT m FROM app.messages WHERE workspace_id=ws AND id=t.message_id FOR NO KEY UPDATE;
        before_version:=m.version;
        reason:=CASE WHEN material->>'state'<>'VISIBLE' THEN material->>'state'
          WHEN t.current_material->>'state'='ORDER_UNCERTAIN' THEN 'ORDER_RESTORED' ELSE 'CONTENT_CHANGED' END;
        UPDATE platform.message_material_targets SET current_material=material WHERE workspace_id=ws AND id=t.id;
        PERFORM platform.material_apply_context(ws,m.id,corr);
        INSERT INTO app.audit_events(workspace_id,actor_kind,actor_user_account_id,correlation_id,event_type,object_type,object_id,object_version,payload)
          VALUES(ws,'CHANNEL_EVENT',NULL,corr,'MESSAGE_MATERIAL_CHANGED','MESSAGE',m.id,before_version+1,
            jsonb_build_object('target_id',t.id,'source_receipt_id',source,'previous_version',before_version::text,'accepted_version',(before_version+1)::text,'reason',reason)) RETURNING audit_event_id INTO audit;
        INSERT INTO platform.message_material_effects(workspace_id,target_id,message_id,source_receipt_id,audit_event_id,previous_version,accepted_version,reason)
          VALUES(ws,t.id,m.id,source,audit,before_version,before_version+1,reason) RETURNING id INTO effect;
        RETURN jsonb_build_object('code','APPLIED','target_id',t.id,'message_id',m.id,'effect_id',effect,'audit_event_id',audit,
          'previous_version',before_version::text,'accepted_version',(before_version+1)::text);
      END $$""")
    op.execute("""CREATE FUNCTION platform.material_bump_turns(ws uuid,messages uuid[],corr uuid) RETURNS void
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$ DECLARE tid uuid; touched uuid[]:='{}'; batch text;
      BEGIN
        batch:=current_setting('asm.material_batch_xid',true);
        IF batch=pg_current_xact_id()::text THEN touched:=coalesce(nullif(current_setting('asm.material_batch_turns',true),'')::uuid[],'{}'); END IF;
        FOR tid IN SELECT DISTINCT turn_id FROM app.conversation_turn_messages WHERE workspace_id=ws AND message_id=ANY(messages) ORDER BY turn_id LOOP
          IF tid=ANY(touched) THEN CONTINUE; END IF;
          PERFORM 1 FROM app.conversation_turns WHERE workspace_id=ws AND id=tid FOR NO KEY UPDATE;
          UPDATE app.conversation_turns SET material_invalidated=true,revision=revision+1 WHERE workspace_id=ws AND id=tid;
          PERFORM platform.turn_enqueue(ws,tid,corr);
          touched:=array_append(touched,tid);
        END LOOP;
        IF batch=pg_current_xact_id()::text THEN PERFORM set_config('asm.material_batch_turns',touched::text,true); END IF;
      END $$""")
    op.execute("""CREATE FUNCTION platform.material_bind(ws uuid,p_message uuid,initial boolean,corr uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE m app.messages%ROWTYPE; t platform.message_material_targets%ROWTYPE; provider_id text; box uuid; n integer;
        c app.conversations%ROWTYPE; origin platform.inbox_events%ROWTYPE; p jsonb; source uuid; result jsonb; disposition text;
        j platform.messaging_jobs%ROWTYPE;
      BEGIN
        SELECT * INTO STRICT m FROM app.messages WHERE workspace_id=ws AND id=p_message;
        SELECT * INTO STRICT c FROM app.conversations WHERE workspace_id=ws AND id=m.conversation_id FOR NO KEY UPDATE;
        provider_id:=m.provider_message_id;
        IF m.direction='OUTBOUND' THEN SELECT id,provider_message_id INTO box,provider_id FROM app.outbox_events WHERE workspace_id=ws AND message_id=m.id AND status='SENT'; END IF;
        IF provider_id IS NULL THEN RETURN NULL; END IF;
        SELECT * INTO t FROM platform.message_material_targets WHERE workspace_id=ws AND connection_id=m.connection_id
          AND provider_chat_id=m.provider_chat_id AND provider_message_id=provider_id FOR UPDATE;
        IF NOT FOUND OR t.quarantined THEN RETURN NULL; END IF;
        IF t.message_id IS NOT NULL THEN
          IF t.message_id<>m.id THEN RAISE EXCEPTION 'conflicting canonical target' USING ERRCODE='23514'; END IF;
          RETURN NULL;
        END IF;
        SELECT count(*) INTO n FROM app.messages a LEFT JOIN app.outbox_events b ON (b.workspace_id,b.message_id)=(a.workspace_id,a.id)
          WHERE a.workspace_id=ws AND a.connection_id=m.connection_id AND a.provider_chat_id=m.provider_chat_id
            AND (a.provider_message_id=provider_id OR (b.status='SENT' AND b.provider_message_id=provider_id));
        IF n<>1 THEN UPDATE platform.message_material_targets SET quarantined=true WHERE workspace_id=ws AND id=t.id; RETURN NULL; END IF;
        IF t.origin_identity IS NOT NULL THEN
          SELECT projection INTO p FROM platform.telegram_provenance WHERE workspace_id=ws AND receipt_id=coalesce(t.undated_receipt,t.candidate_receipt,t.conflict_receipt);
          p:=p||jsonb_build_object('origin',t.origin_identity->'sender','sent_at',t.origin_identity->'sent_at','chat_type',t.origin_identity->'chat_type');
          IF platform.material_identity(ws,m.id,p) IS NOT TRUE THEN
            UPDATE platform.message_material_targets SET quarantined=true WHERE workspace_id=ws AND id=t.id; RETURN NULL;
          END IF;
        END IF;
        FOREACH source IN ARRAY ARRAY[t.delete_receipt,t.undated_receipt,t.candidate_receipt,t.conflict_receipt] LOOP
          IF source IS NULL THEN CONTINUE; END IF;
          SELECT projection INTO STRICT p FROM platform.telegram_provenance WHERE workspace_id=ws AND receipt_id=source;
          IF platform.material_identity(ws,m.id,p) IS NOT TRUE THEN
            UPDATE platform.message_material_targets SET quarantined=true WHERE workspace_id=ws AND id=t.id; RETURN NULL;
          END IF;
        END LOOP;
        UPDATE platform.message_material_targets SET message_id=m.id,conversation_id=m.conversation_id,client_id=c.client_id,direction=m.direction,
          outbox_id=box,inbound_provider_id=CASE WHEN m.direction='INBOUND' THEN provider_id END,required_sent=CASE WHEN box IS NOT NULL THEN 'SENT' END,
          current_material=jsonb_build_object('state','VISIBLE','content',CASE WHEN m.content_type='TEXT' THEN jsonb_build_object('kind','TEXT','text',m.text)
            ELSE jsonb_build_object('kind','PHOTO','caption',m.text,'selected_file_id',m.image_file_id) END) WHERE workspace_id=ws AND id=t.id;
        result:=platform.material_apply(ws,t.id,corr);
        IF result IS NULL THEN RETURN NULL; END IF;
        IF initial THEN
          SELECT * INTO origin FROM platform.inbox_events WHERE workspace_id=ws AND connection_id=m.connection_id
            AND normalized_event->>'kind'='CLIENT_MESSAGE' AND normalized_event->>'chat_id'=m.provider_chat_id
            AND normalized_event->>'message_id'=m.provider_message_id ORDER BY turn_ingress_seq NULLS FIRST,id LIMIT 1;
          UPDATE platform.message_material_targets SET original_grouping_closed=(current_material->>'state'<>'VISIBLE' OR origin.turn_ingress_seq IS NULL)
            WHERE workspace_id=ws AND id=t.id;
        END IF;
        IF initial AND m.content_type='IMAGE_REFERENCE' THEN
          SELECT * INTO STRICT t FROM platform.message_material_targets WHERE workspace_id=ws AND id=t.id;
          IF t.current_material->>'state'<>'VISIBLE' OR t.current_material->'content'->>'kind'='TEXT' OR
            t.current_material->'content'->>'selected_file_id' IS DISTINCT FROM m.image_file_id THEN
            j:=platform.messaging_guard(nullif(current_setting('asm.job_id',true),'')::uuid,nullif(current_setting('asm.claim_token',true),'')::uuid);
            IF j.kind<>'PROCESS_INBOX' OR j.workspace_id<>ws OR j.connection_id<>m.connection_id OR m.direction<>'INBOUND' OR m.version<>1 OR
              NOT EXISTS(SELECT 1 FROM app.messages WHERE workspace_id=ws AND id=m.id AND xmin::text=pg_current_xact_id()::text) THEN
              RAISE EXCEPTION 'invalid initial material capability' USING ERRCODE='23514'; END IF;
            SELECT * INTO origin FROM platform.inbox_events WHERE workspace_id=ws AND connection_id=m.connection_id
              AND normalized_event->>'kind'='CLIENT_MESSAGE' AND normalized_event->>'chat_id'=m.provider_chat_id
              AND normalized_event->>'message_id'=m.provider_message_id ORDER BY turn_ingress_seq NULLS FIRST,id LIMIT 1;
            IF origin.id IS NULL THEN RAISE EXCEPTION 'missing original' USING ERRCODE='23514'; END IF;
            disposition:=CASE WHEN t.current_material->>'state'<>'VISIBLE' THEN 'HIDDEN' WHEN origin.turn_ingress_seq IS NULL THEN 'INELIGIBLE_ORIGIN' ELSE 'ELIGIBLE_VISIBLE' END;
            INSERT INTO platform.message_initial_suppressions(workspace_id,message_id,target_id,origin_inbox_id,effect_id,source_receipt_id,initial_material,fold_witnesses,membership_disposition)
              VALUES(ws,m.id,t.id,origin.id,(result->>'effect_id')::uuid,(SELECT source_receipt_id FROM platform.message_material_effects WHERE workspace_id=ws AND id=(result->>'effect_id')::uuid),
                t.current_material,array_remove(ARRAY[t.delete_receipt,t.undated_receipt,t.candidate_receipt,t.conflict_receipt],NULL),disposition);
          END IF;
        END IF;
        RETURN result;
      END $$""")


def _suppression() -> None:
    op.execute("""CREATE FUNCTION platform.material_suppression_check() RETURNS trigger
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE s platform.message_initial_suppressions%ROWTYPE; m app.messages%ROWTYPE;
        origin platform.inbox_events%ROWTYPE; t platform.message_material_targets%ROWTYPE;
        effect platform.message_material_effects%ROWTYPE; j platform.messaging_jobs%ROWTYPE; n integer; first_origin uuid;
      BEGIN
        IF TG_WHEN='BEFORE' THEN s:=NEW;
        ELSE SELECT * INTO s FROM platform.message_initial_suppressions WHERE workspace_id=NEW.workspace_id AND message_id=NEW.message_id; END IF;
        IF s.id IS NULL THEN RETURN NEW; END IF;
        SELECT * INTO STRICT m FROM app.messages WHERE workspace_id=s.workspace_id AND id=s.message_id;
        SELECT * INTO STRICT origin FROM platform.inbox_events WHERE workspace_id=s.workspace_id AND id=s.origin_inbox_id;
        SELECT * INTO STRICT effect FROM platform.message_material_effects WHERE workspace_id=s.workspace_id AND id=s.effect_id;
        IF m.direction<>'INBOUND' OR m.content_type<>'IMAGE_REFERENCE' OR origin.normalized_event->>'kind'<>'CLIENT_MESSAGE' OR
          (origin.connection_id,origin.normalized_event->>'chat_id',origin.normalized_event->>'message_id',origin.normalized_event->>'image_file_id',origin.normalized_event->>'text',
            (origin.normalized_event->>'occurred_at')::timestamptz) IS DISTINCT FROM
          (m.connection_id,m.provider_chat_id,m.provider_message_id,m.image_file_id,m.text,m.occurred_at) OR
          platform.messaging_fingerprint(origin.normalized_event,true)<>m.projection_fingerprint OR
          EXISTS(SELECT 1 FROM app.file_objects WHERE workspace_id=s.workspace_id AND message_id=m.id) THEN
          RAISE EXCEPTION 'invalid initial suppression identity/file' USING ERRCODE='23514'; END IF;
        IF TG_WHEN='BEFORE' THEN
          j:=platform.messaging_guard(nullif(current_setting('asm.job_id',true),'')::uuid,nullif(current_setting('asm.claim_token',true),'')::uuid);
          SELECT id INTO first_origin FROM platform.inbox_events WHERE workspace_id=s.workspace_id AND connection_id=m.connection_id
            AND normalized_event->>'kind'='CLIENT_MESSAGE' AND normalized_event->>'chat_id'=m.provider_chat_id
            AND normalized_event->>'message_id'=m.provider_message_id ORDER BY turn_ingress_seq NULLS FIRST,id LIMIT 1;
          SELECT * INTO STRICT t FROM platform.message_material_targets WHERE workspace_id=s.workspace_id AND id=s.target_id;
          IF j.kind<>'PROCESS_INBOX' OR j.workspace_id<>s.workspace_id OR j.connection_id<>m.connection_id OR m.version<>2 OR
            NOT EXISTS(SELECT 1 FROM app.messages WHERE workspace_id=s.workspace_id AND id=m.id AND xmin::text=pg_current_xact_id()::text) OR
            EXISTS(SELECT 1 FROM app.conversation_turn_messages WHERE workspace_id=s.workspace_id AND message_id=m.id) OR
            first_origin IS DISTINCT FROM origin.id OR (effect.target_id,effect.message_id,effect.source_receipt_id,effect.previous_version,effect.accepted_version) IS DISTINCT FROM
              (s.target_id,s.message_id,s.source_receipt_id,1::bigint,2::bigint) OR
            s.initial_material IS DISTINCT FROM t.current_material OR s.fold_witnesses IS DISTINCT FROM array_remove(ARRAY[t.delete_receipt,t.undated_receipt,t.candidate_receipt,t.conflict_receipt],NULL) OR
            s.source_receipt_id IS DISTINCT FROM coalesce(t.delete_receipt,t.undated_receipt,t.conflict_receipt,t.candidate_receipt) OR
            (s.initial_material->>'state'='VISIBLE' AND s.initial_material->'content'->>'kind'='PHOTO' AND s.initial_material->'content'->>'selected_file_id'=m.image_file_id) OR
            s.membership_disposition IS DISTINCT FROM (CASE WHEN s.initial_material->>'state'<>'VISIBLE' THEN 'HIDDEN'
              WHEN origin.turn_ingress_seq IS NULL THEN 'INELIGIBLE_ORIGIN' ELSE 'ELIGIBLE_VISIBLE' END) THEN
            RAISE EXCEPTION 'invalid first-original suppression proof' USING ERRCODE='23514'; END IF;
          RETURN NEW;
        END IF;
        SELECT count(*) INTO n FROM app.conversation_turn_messages WHERE workspace_id=s.workspace_id AND message_id=m.id;
        IF (s.membership_disposition='ELIGIBLE_VISIBLE' AND (n<>1 OR NOT EXISTS(SELECT 1 FROM app.conversation_turn_messages
            WHERE workspace_id=s.workspace_id AND message_id=m.id AND initial_suppression_id=s.id AND membership_form='INITIAL_FOLD_SUPPRESSED')))
          OR (s.membership_disposition<>'ELIGIBLE_VISIBLE' AND n<>0) THEN
          RAISE EXCEPTION 'incomplete initial suppression membership' USING ERRCODE='23514'; END IF;
        RETURN NULL;
      END $$""")
    op.execute(
        "CREATE TRIGGER material_suppression_authority BEFORE INSERT ON platform.message_initial_suppressions FOR EACH ROW EXECUTE FUNCTION platform.material_suppression_check()"
    )
    for table in ("platform.message_initial_suppressions", "app.conversation_turn_messages"):
        op.execute(
            f"CREATE CONSTRAINT TRIGGER material_suppression_completeness AFTER INSERT OR UPDATE ON {table} DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.material_suppression_check()"
        )


def _worker() -> None:
    op.execute("""CREATE FUNCTION platform.material_processing_replay(p_job uuid,p_claim uuid) RETURNS jsonb
      LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      SELECT jsonb_build_object('code','MATERIAL_PROCESSED','status','PROCESSED','inbox_id',i.id,'message_id',NULL)
        FROM platform.messaging_jobs j JOIN platform.inbox_events i
          ON (i.workspace_id,i.id,i.connection_id)=(j.workspace_id,j.inbox_id,j.connection_id)
        JOIN platform.telegram_provenance s ON (s.workspace_id,s.inbox_id,s.connection_id,s.bot_identity,s.update_id)
          =(i.workspace_id,i.id,i.connection_id,i.bot_identity,i.event_id)
        WHERE j.id=p_job AND j.kind='PROCESS_INBOX' AND j.status='SUCCEEDED' AND i.material_claim_token=p_claim
          AND i.result_code='MATERIAL_PROCESSED' AND i.status='PROCESSED'
          AND s.codec=2 AND s.material_enabled AND s.projection->>'discriminator' IN ('EDIT','DELETE') $$""")
    op.execute("""CREATE FUNCTION platform.material_process(j platform.messaging_jobs) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE s platform.telegram_provenance%ROWTYPE; i platform.inbox_events%ROWTYPE;
        t platform.message_material_targets%ROWTYPE; c app.conversations%ROWTYPE; ids text[]; provider_id text;
        msg uuid; n integer; ordinal integer:=0; outcome text; result jsonb; results jsonb:='[]'; changed uuid[]:='{}'; observed_version bigint;
      BEGIN
        SELECT * INTO s FROM platform.telegram_provenance WHERE workspace_id=j.workspace_id AND inbox_id=j.inbox_id;
        IF NOT FOUND OR s.projection->>'discriminator' NOT IN ('EDIT','DELETE') THEN RETURN NULL; END IF;
        IF NOT s.material_enabled THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        SELECT * INTO STRICT i FROM platform.inbox_events WHERE workspace_id=j.workspace_id AND id=j.inbox_id FOR NO KEY UPDATE;
        PERFORM 1 FROM app.channel_connections WHERE workspace_id=j.workspace_id AND id=j.connection_id FOR UPDATE;
        SELECT * INTO c FROM app.conversations WHERE workspace_id=j.workspace_id AND connection_id=j.connection_id
          AND provider_chat_id=s.projection->>'chat_id' FOR NO KEY UPDATE;
        PERFORM platform.messaging_guard(j.id,j.claim_token);
        IF s.projection->>'discriminator'='EDIT' THEN ids:=ARRAY[s.projection->>'message_id'];
        ELSE SELECT array_agg(v ORDER BY v::bigint) INTO ids FROM (SELECT DISTINCT value AS v FROM jsonb_array_elements_text(s.projection->'legacy_v1'->'deleted_message_ids')) q; END IF;
        PERFORM set_config('asm.material_batch_xid',pg_current_xact_id()::text,true),set_config('asm.material_batch_turns','{}',true);
        -- The connection/C barrier serializes this chat; reserve all sorted stable targets first.
        FOREACH provider_id IN ARRAY ids LOOP
          INSERT INTO platform.message_material_targets(workspace_id,connection_id,provider_chat_id,provider_message_id)
            VALUES(j.workspace_id,j.connection_id,s.projection->>'chat_id',provider_id) ON CONFLICT DO NOTHING;
          PERFORM 1 FROM platform.message_material_targets WHERE workspace_id=j.workspace_id AND connection_id=j.connection_id
            AND provider_chat_id=s.projection->>'chat_id' AND provider_message_id=provider_id FOR UPDATE;
        END LOOP;
        FOR msg IN SELECT m.id FROM app.messages m LEFT JOIN app.outbox_events b ON (b.workspace_id,b.message_id)=(m.workspace_id,m.id)
          WHERE m.workspace_id=j.workspace_id AND m.conversation_id=c.id AND (m.provider_message_id=ANY(ids) OR (b.status='SENT' AND b.provider_message_id=ANY(ids))) ORDER BY m.id LOOP
          PERFORM 1 FROM app.messages WHERE workspace_id=j.workspace_id AND id=msg FOR NO KEY UPDATE;
        END LOOP;
        PERFORM 1 FROM app.conversation_turns WHERE workspace_id=j.workspace_id AND conversation_id=c.id ORDER BY id FOR NO KEY UPDATE;
        FOREACH provider_id IN ARRAY ids LOOP
          ordinal:=ordinal+1; msg:=NULL; result:=NULL;
          SELECT * INTO STRICT t FROM platform.message_material_targets WHERE workspace_id=j.workspace_id AND connection_id=j.connection_id
            AND provider_chat_id=s.projection->>'chat_id' AND provider_message_id=provider_id;
          SELECT count(*),(array_agg(m.id ORDER BY m.id))[1] INTO n,msg FROM app.messages m LEFT JOIN app.outbox_events b ON (b.workspace_id,b.message_id)=(m.workspace_id,m.id)
            WHERE m.workspace_id=j.workspace_id AND m.conversation_id=c.id AND (m.provider_message_id=provider_id OR (b.status='SENT' AND b.provider_message_id=provider_id));
          IF n>1 OR t.quarantined OR (n=1 AND platform.material_identity(j.workspace_id,msg,s.projection) IS NOT TRUE) THEN
            outcome:='IDENTITY_CONFLICT';
          ELSE
            IF msg IS NOT NULL AND t.message_id IS NULL THEN
              result:=platform.material_bind(j.workspace_id,msg,false,j.correlation_id);
              -- Existing deferred facts normally bind in the original/SENT atom.
              IF result IS NOT NULL THEN RAISE EXCEPTION 'missed original binding' USING ERRCODE='23514'; END IF;
            END IF;
            outcome:=platform.material_fold(j.workspace_id,t.id,s.receipt_id);
            SELECT * INTO STRICT t FROM platform.message_material_targets WHERE workspace_id=j.workspace_id AND id=t.id;
            IF outcome<>'IDENTITY_CONFLICT' THEN
              IF t.message_id IS NULL THEN outcome:='DEFERRED_TARGET';
              ELSE
                result:=platform.material_apply(j.workspace_id,t.id,j.correlation_id);
                IF result IS NOT NULL THEN changed:=array_append(changed,t.message_id); outcome:='APPLIED'; END IF;
              END IF;
            END IF;
          END IF;
          IF result IS NULL THEN
            IF outcome NOT IN ('DEFERRED_TARGET','IDENTITY_CONFLICT') THEN
              SELECT m.version INTO STRICT observed_version FROM app.messages m WHERE m.workspace_id=j.workspace_id AND m.id=t.message_id;
            ELSE observed_version:=NULL; END IF;
            result:=jsonb_build_object('code',outcome,'target_id',CASE WHEN outcome<>'IDENTITY_CONFLICT' THEN t.id END,
              'message_id',CASE WHEN outcome NOT IN ('IDENTITY_CONFLICT','DEFERRED_TARGET') THEN t.message_id END,
              'effect_id',NULL,'audit_event_id',NULL,'previous_version',observed_version::text,'accepted_version',observed_version::text);
          END IF;
          results:=results||jsonb_build_array(result||jsonb_build_object('ordinal',ordinal));
        END LOOP;
        PERFORM platform.messaging_guard(j.id,j.claim_token);
        UPDATE platform.inbox_events SET status='PROCESSED',result_code='MATERIAL_PROCESSED',material_result=results,material_claim_token=j.claim_token,completed_at=clock_timestamp(),version=version+1
          WHERE workspace_id=j.workspace_id AND id=j.inbox_id;
        UPDATE platform.messaging_jobs SET status='SUCCEEDED',error_code=NULL,claim_token=NULL,lease_until=NULL,worker_id=NULL,
          completed_at=clock_timestamp(),version=version+1 WHERE id=j.id;
        RETURN jsonb_build_object('code','MATERIAL_PROCESSED','status','PROCESSED','inbox_id',j.inbox_id,'message_id',NULL);
      END $$""")
    _replace(
        "messaging_process_inbox(2)",
        (
            "          fingerprint:=platform.messaging_fingerprint(e,true);",
            """          PERFORM pg_advisory_xact_lock(hashtextextended(j.workspace_id::text||':'||(e->>'provider')||':'||(e->>'sender_id'),2005));
          PERFORM 1 FROM app.conversations WHERE workspace_id=j.workspace_id AND connection_id=j.connection_id AND provider_chat_id=e->>'chat_id' FOR NO KEY UPDATE;
          fingerprint:=platform.messaging_fingerprint(e,true);""",
        ),
        (
            "              PERFORM pg_advisory_xact_lock(hashtextextended(j.workspace_id::text||':'||(e->>'provider')||':'||(e->>'sender_id'),2005));\n",
            "",
        ),
        ("fingerprint bytea;", "fingerprint bytea; material_result jsonb;"),
        (
            "        e:=inbox.normalized_event;",
            """        material_result:=platform.material_process(j);
        IF material_result IS NOT NULL THEN RETURN material_result; END IF;
        e:=inbox.normalized_event;""",
        ),
        (
            "        IF state='PROCESSED' AND msg.content_type='IMAGE_REFERENCE' THEN\n          PERFORM platform.files_plan(j.workspace_id,msg.id,j.correlation_id);\n        END IF;\n",
            "",
        ),
        (
            "          PERFORM platform.turn_group_message(j.workspace_id,msg.id,j.correlation_id);",
            """          PERFORM platform.material_bind(j.workspace_id,msg.id,true,j.correlation_id);
          IF msg.content_type='IMAGE_REFERENCE' THEN PERFORM platform.files_plan(j.workspace_id,msg.id,j.correlation_id); END IF;
          PERFORM platform.turn_group_message(j.workspace_id,msg.id,j.correlation_id);""",
        ),
        (
            "        PERFORM platform.messaging_guard(p_job,p_claim);",
            """        IF code='DUPLICATE' AND msg.content_type='IMAGE_REFERENCE' THEN
          PERFORM platform.files_plan(j.workspace_id,msg.id,j.correlation_id);
        END IF;
        PERFORM platform.messaging_guard(p_job,p_claim);""",
        ),
    )
    _replace(
        "files_plan(3)",
        (
            "        INSERT INTO app.file_objects(",
            """        IF EXISTS(SELECT 1 FROM platform.message_initial_suppressions WHERE workspace_id=p_workspace AND message_id=p_message) THEN RETURN; END IF;
        INSERT INTO app.file_objects(""",
        ),
    )


def _shared() -> None:
    _replace(
        "turn_immutable(0)",
        (
            "ELSIF OLD.state<>'COLLECTING'",
            """ELSIF OLD.material_invalidated AND NOT NEW.material_invalidated THEN
        RAISE EXCEPTION 'sticky material invalidation' USING ERRCODE='23514';
      ELSIF OLD.state<>'COLLECTING'""",
        ),
        (
            "OLD.state='FAILED' AND NEW IS DISTINCT FROM OLD",
            "OLD.state='FAILED' AND (to_jsonb(NEW)-'revision'-'material_invalidated') IS DISTINCT FROM (to_jsonb(OLD)-'revision'-'material_invalidated')",
        ),
    )
    _replace(
        "turn_group_message(3)",
        (
            "fresh boolean:=false; generation bigint;",
            "fresh boolean:=false; generation bigint; suppression platform.message_initial_suppressions%ROWTYPE;",
        ),
        (
            "        IF EXISTS(SELECT 1 FROM app.conversation_turn_messages",
            """        SELECT * INTO suppression FROM platform.message_initial_suppressions WHERE workspace_id=ws AND message_id=m.id;
        IF (suppression.id IS NOT NULL AND suppression.membership_disposition<>'ELIGIBLE_VISIBLE') OR
          platform.message_effective(ws,m.id)->>'state'<>'VISIBLE' OR EXISTS(SELECT 1 FROM platform.message_material_targets
            WHERE workspace_id=ws AND message_id=m.id AND original_grouping_closed) THEN RETURN; END IF;
        IF EXISTS(SELECT 1 FROM app.conversation_turn_messages""",
        ),
        (
            "ELSIF FOUND AND ((t.control_generation",
            "ELSIF FOUND AND (t.material_invalidated OR (t.control_generation",
        ),
        (
            "turn_ingress_seq,file_id)\n          VALUES",
            "turn_ingress_seq,file_id,membership_form,initial_suppression_id)\n          VALUES",
        ),
        (
            "origin.turn_ingress_seq,file);",
            "origin.turn_ingress_seq,file,CASE WHEN suppression.id IS NOT NULL THEN 'INITIAL_FOLD_SUPPRESSED' END,suppression.id);",
        ),
    )
    _replace(
        "turn_member_check(0)",
        (
            "        RETURN NEW;",
            """        IF EXISTS(SELECT 1 FROM platform.message_material_targets WHERE workspace_id=NEW.workspace_id AND message_id=m.id AND original_grouping_closed) THEN
          RAISE EXCEPTION 'initially excluded membership' USING ERRCODE='23514'; END IF;
        IF NEW.membership_form IS NOT NULL AND NOT EXISTS(SELECT 1 FROM platform.message_initial_suppressions s
          WHERE (s.workspace_id,s.id,s.message_id,s.origin_inbox_id,s.membership_disposition)=
            (NEW.workspace_id,NEW.initial_suppression_id,NEW.message_id,NEW.origin_inbox_id,'ELIGIBLE_VISIBLE')) THEN
          RAISE EXCEPTION 'invalid suppression member' USING ERRCODE='23514'; END IF;
        RETURN NEW;""",
        ),
    )
    _replace(
        "turn_members_consistent(0)",
        (
            "        RETURN NULL;",
            """        IF EXISTS(SELECT 1 FROM app.conversation_turn_messages m WHERE m.workspace_id=NEW.workspace_id AND m.turn_id=NEW.id
          AND m.membership_form IS NOT NULL AND NOT EXISTS(SELECT 1 FROM platform.message_initial_suppressions s
            WHERE (s.workspace_id,s.id,s.message_id,s.origin_inbox_id,s.membership_disposition)=
              (m.workspace_id,m.initial_suppression_id,m.message_id,m.origin_inbox_id,'ELIGIBLE_VISIBLE'))) THEN
          RAISE EXCEPTION 'inconsistent suppression member' USING ERRCODE='23514'; END IF;
        RETURN NULL;""",
        ),
    )
    _replace(
        "turn_seal(5)",
        (
            """        SELECT coalesce(bool_or(f.status='PENDING'),false),coalesce(bool_and(f.status='READY'),true)
          INTO pending,complete FROM app.conversation_turn_messages m
          JOIN app.file_objects f ON (f.workspace_id,f.id)=(m.workspace_id,m.file_id)
          WHERE m.workspace_id=ws AND m.turn_id=t.id;""",
            """        SELECT coalesce(bool_or(e.body->>'image_availability'='ORIGINAL_PENDING'),false),
          coalesce(bool_and(e.body->>'state'='VISIBLE' AND e.body->>'image_availability' IN ('NOT_APPLICABLE','ORIGINAL_READY')),false)
          INTO pending,complete FROM app.conversation_turn_messages m
          CROSS JOIN LATERAL (SELECT platform.message_effective(ws,m.message_id) AS body) e
          WHERE m.workspace_id=ws AND m.turn_id=t.id;""",
        ),
    )
    _replace(
        "turn_enqueue(3)",
        (
            "        IF t.state='FAILED' THEN RETURN; END IF;",
            """        IF t.state='FAILED' OR (t.state='READY' AND platform.material_turn_usable(ws,t.id) IS NOT TRUE) THEN RETURN; END IF;""",
        ),
    )
    _replace(
        "conversation_turn_activation_matches(2)",
        (
            "SELECT t.ingress_control_mode='AI'",
            "SELECT platform.material_turn_usable(ws,t.id) AND t.ingress_control_mode='AI'",
        ),
    )
    _replace(
        "guard_require_current(4)",
        (
            "IF t.state<>'READY'",
            "IF platform.material_turn_usable(ws,t.id) IS NOT TRUE OR t.state<>'READY'",
        ),
    )
    _replace(
        "turn_supersede(1)",
        (
            "AND revision<>j.turn_revision)",
            "AND (revision<>j.turn_revision OR (j.step NOT IN ('GROUP','MEDIA') AND platform.material_turn_usable(j.workspace_id,id) IS NOT TRUE)))",
        ),
    )
    _replace(
        "turn_material(0)",
        (
            "        IF TG_TABLE_NAME='file_objects' THEN",
            """        IF TG_TABLE_NAME='outbox_events' THEN
          IF NEW.status='SENT' THEN
          SELECT correlation_id INTO STRICT corr FROM platform.messaging_jobs WHERE workspace_id=ws AND outbox_id=NEW.id;
          -- Only an already existing target can bind; no new connection FK or foreign Job lock.
          PERFORM platform.material_bind(ws,NEW.message_id,false,corr);
          END IF;
        END IF;
        IF TG_TABLE_NAME='file_objects' THEN
          IF platform.message_effective(ws,NEW.message_id)->>'image_availability' NOT IN ('ORIGINAL_READY','ORIGINAL_FAILED') THEN RETURN NEW; END IF;""",
        ),
    )
    _replace(
        "turn_snapshot(2)",
        (
            "'ingress_at',tm.turn_ingress_at",
            """'membership_form',tm.membership_form,'initial_suppression_id',tm.initial_suppression_id,
          'current',platform.message_effective(ws,m.id),'ingress_at',tm.turn_ingress_at""",
        ),
        (
            "SELECT jsonb_build_object('workspace_id',ws",
            "SELECT jsonb_build_object('schema_version',2,'workspace_id',ws",
        ),
    )
    _replace(
        "turn_consumer_finalize(3)",
        (
            "WHERE m->'file'->>'status'='READY'",
            "WHERE CASE WHEN j.turn_input->>'schema_version'='2' THEN m->'current'->>'image_availability'='ORIGINAL_READY' ELSE m->'file'->>'status'='READY' END",
        ),
        (
            "WHERE m->'file'->>'wait_expired'='true'",
            "WHERE CASE WHEN j.turn_input->>'schema_version'='2' THEN m->'current'->>'image_availability'='ORIGINAL_PENDING' ELSE m->'file'->>'wait_expired'='true' END",
        ),
    )
    _replace(
        "files_read_manifest(3)",
        (
            "AND f.status='READY' AND u.status='WINNER'",
            "AND f.status='READY' AND u.status='WINNER' AND platform.message_effective(ws,m.id)->>'image_availability'='ORIGINAL_READY'",
        ),
    )
    _replace(
        "messaging_read_messages(4)",
        (
            "m.version::text AS version,",
            "m.version::text AS version,platform.message_effective(ws,m.id) AS current,",
        ),
    )


def upgrade() -> None:
    _validation()
    _schema()
    _ingress()
    _integrity()
    _material()
    _suppression()
    _worker()
    _shared()
    for signature in (*PRIVATE_FUNCTIONS, *PUBLIC_FUNCTIONS):
        op.execute(f"ALTER FUNCTION {signature} OWNER TO asm_migrator")
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC,asm_runtime")
    for signature in PUBLIC_FUNCTIONS:
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO asm_runtime")


def downgrade() -> None:
    op.execute("""LOCK TABLE platform.telegram_update_receipts,platform.telegram_provenance,
      platform.message_material_targets,platform.message_material_effects,platform.message_initial_suppressions,
      platform.inbox_events,app.conversation_turns,app.conversation_turn_messages,app.audit_events,
      platform.telegram_connection_state IN ACCESS EXCLUSIVE MODE""")
    # First statements only lock/read. No DDL or history removal precedes refusal.
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM platform.telegram_update_receipts WHERE codec IS NOT NULL) OR
        EXISTS(SELECT 1 FROM platform.telegram_provenance) OR EXISTS(SELECT 1 FROM platform.message_material_targets) OR
        EXISTS(SELECT 1 FROM platform.message_material_effects) OR EXISTS(SELECT 1 FROM platform.message_initial_suppressions) OR
        EXISTS(SELECT 1 FROM platform.inbox_events WHERE material_result IS NOT NULL OR material_claim_token IS NOT NULL OR result_code='MATERIAL_PROCESSED') OR
        EXISTS(SELECT 1 FROM app.conversation_turns WHERE material_invalidated) OR
        EXISTS(SELECT 1 FROM app.conversation_turn_messages WHERE membership_form IS NOT NULL OR initial_suppression_id IS NOT NULL) OR
        EXISTS(SELECT 1 FROM app.audit_events WHERE event_type='MESSAGE_MATERIAL_CHANGED') OR
        EXISTS(SELECT 1 FROM platform.telegram_connection_state WHERE material_enabled) THEN
        RAISE EXCEPTION 'Material history prevents downgrade' USING ERRCODE='55000'; END IF;
      END $$""")
    for body in ORIGINAL.values():
        op.execute(body)
    for table in (
        "platform.telegram_update_receipts",
        "platform.telegram_provenance",
        "platform.inbox_events",
    ):
        op.execute(f"DROP TRIGGER material_integrity ON {table}")
    op.execute("DROP TRIGGER material_receipt_immutable ON platform.telegram_update_receipts")
    op.execute("DROP TRIGGER material_no_file ON app.file_objects")
    op.execute("DROP TRIGGER material_suppression_completeness ON app.conversation_turn_messages")
    op.execute("""ALTER TABLE app.conversation_turn_messages DROP CONSTRAINT turn_member_suppression_fkey,
      DROP CONSTRAINT conversation_turn_messages_check,DROP COLUMN suppression_disposition,
      DROP COLUMN membership_form,DROP COLUMN initial_suppression_id""")
    op.execute(
        f"ALTER TABLE app.conversation_turn_messages ADD CONSTRAINT conversation_turn_messages_check CHECK({OLD_MEMBER_CHECK})"
    )
    op.execute("DROP TABLE platform.message_initial_suppressions")
    op.execute("DROP TABLE platform.message_material_effects")
    op.execute("""ALTER TABLE app.audit_events DROP CONSTRAINT audit_events_discriminator_payload_check,
      DROP CONSTRAINT audit_material_ref_key,DROP CONSTRAINT audit_material_target_fkey,DROP CONSTRAINT audit_material_source_fkey,
      DROP COLUMN material_target_id,DROP COLUMN material_source_receipt_id""")
    op.execute(
        f"ALTER TABLE app.audit_events ADD CONSTRAINT audit_events_discriminator_payload_check CHECK({OLD_AUDIT_CHECK})"
    )
    op.execute("DROP TABLE platform.message_material_targets")
    op.execute("DROP TABLE platform.telegram_provenance")
    op.execute(
        """ALTER TABLE platform.inbox_events DROP CONSTRAINT inbox_events_check,DROP CONSTRAINT inbox_material_identity_key,DROP COLUMN material_result,DROP COLUMN material_claim_token"""
    )
    op.execute(
        f"ALTER TABLE platform.inbox_events ADD CONSTRAINT inbox_events_check CHECK({OLD_INBOX_CHECK})"
    )
    op.execute("""ALTER TABLE platform.telegram_update_receipts DROP CONSTRAINT telegram_update_receipts_check,
      DROP CONSTRAINT telegram_material_identity_key,DROP CONSTRAINT telegram_material_source_key,DROP COLUMN codec""")
    op.execute(
        f"ALTER TABLE platform.telegram_update_receipts ADD CONSTRAINT telegram_update_receipts_check CHECK({OLD_RECEIPT_CHECK})"
    )
    op.execute("""ALTER TABLE app.messages DROP CONSTRAINT messages_material_identity_key,DROP CONSTRAINT messages_material_inbound_key;
      ALTER TABLE app.outbox_events DROP CONSTRAINT outbox_material_sent_key;
      ALTER TABLE app.conversation_turns DROP COLUMN material_invalidated;
      ALTER TABLE platform.telegram_connection_state DROP COLUMN material_enabled""")
    for signature in (*PUBLIC_FUNCTIONS, *reversed(PRIVATE_FUNCTIONS)):
        op.execute(f"DROP FUNCTION {signature}")
