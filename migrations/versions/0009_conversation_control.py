"""Owner CONTROL commands, immutable receipts and ingress activation fences.

Applied migrations 0001--0008 remain immutable. The four exact prior definitions
below are retained for a CONTROL-clean downgrade; no data is rewritten on upgrade.
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

ORIGINAL = {
    "turn_ingress": r"""CREATE FUNCTION platform.turn_ingress() RETURNS trigger
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
      END $$""",
    "turn_member_check": r"""CREATE FUNCTION platform.turn_member_check() RETURNS trigger
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
      END $$""",
    "turn_group_message": r"""CREATE FUNCTION platform.turn_group_message(ws uuid,p_message uuid,corr uuid) RETURNS void
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
          IF conn.provider='TELEGRAM' THEN
            IF platform.telegram_can_send(ws,conn.id,conv.id,true) IS NOT TRUE THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
            IF platform.messaging_manual_send_allowed(ws) IS NOT TRUE THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
            -- The reply window can expire while acquiring the billing locks.
            IF platform.telegram_can_send(ws,conn.id,conv.id,true) IS NOT TRUE THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
          END IF;
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
}

OLD_AUDIT_CHECK = r"""(event_type='WORKSPACE_BILLING_PROVISIONED' AND
 actor_kind='LOCAL_PROVISIONER' AND actor_user_account_id IS NULL AND
 object_type='WORKSPACE_BILLING_ACCOUNT' AND payload='{}'::jsonb) OR
 (event_type='BILLING_ACCOUNT_CONTACT_UPDATED' AND actor_kind='USER_ACCOUNT' AND
 actor_user_account_id IS NOT NULL AND object_type='WORKSPACE_BILLING_ACCOUNT' AND
 payload='{"changed_fields":["contact_display_name"]}'::jsonb) OR (event_type='MESSAGE_SEND_REQUESTED' AND actor_kind='USER_ACCOUNT' AND actor_user_account_id IS NOT NULL AND object_type='MESSAGE' AND object_version=1 AND payload='{"content_type":"TEXT"}'::jsonb)"""

OWNER_FUNCTIONS = (
    "platform.conversation_control_read(uuid)",
    "platform.conversation_control_prepare(uuid,uuid,text,text,bigint,bigint)",
    "platform.conversation_control_execute(uuid,uuid,text,text,bigint,bigint)",
    "platform.conversation_manual_prelock(uuid,text,text)",
)
PRIVATE_FUNCTIONS = (
    "platform.conversation_control_fingerprint(uuid,uuid,uuid,uuid,text,bigint,bigint)",
    "platform.conversation_control_locked(uuid,uuid,text,text,bigint,bigint)",
    "platform.conversation_manual_takeover(uuid,uuid)",
    "platform.conversation_turn_activation_matches(uuid,uuid)",
)


def _replace(name: str, *changes: tuple[str, str]) -> None:
    body = ORIGINAL[name].replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
    for before, after in changes:
        assert body.count(before) == 1, (name, before)
        body = body.replace(before, after)
    op.execute(body)


def _schema() -> None:
    # Drained cutover, but still prove the only historical generation we can infer.
    op.execute(
        "LOCK TABLE app.conversations,platform.inbox_events,app.conversation_turns IN ACCESS EXCLUSIVE MODE"
    )
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM app.conversations WHERE control_mode<>'HUMAN' OR control_generation<>1)
        OR EXISTS(SELECT 1 FROM app.conversation_turns WHERE control_generation<>1) THEN
        RAISE EXCEPTION 'CONTROL upgrade requires canonical 0008' USING ERRCODE='55000'; END IF;
      END $$""")
    op.execute("""ALTER TABLE app.conversations
      DROP CONSTRAINT conversations_control_mode_check,
      ADD COLUMN activation_fence_seq bigint,
      ADD CONSTRAINT conversations_control_mode_check CHECK(
        (control_mode='HUMAN' AND activation_fence_seq IS NULL) OR
        (control_mode='AI' AND control_generation>=2 AND activation_fence_seq IS NOT NULL AND activation_fence_seq>0)),
      ADD CONSTRAINT conversations_control_client_key UNIQUE(workspace_id,id,client_id)""")
    op.execute("""ALTER TABLE platform.inbox_events
      ADD COLUMN turn_control_generation bigint,
      ADD COLUMN turn_control_mode text,
      ADD COLUMN turn_activation_fence_seq bigint,
      ADD CONSTRAINT inbox_control_capture_check CHECK(
        (turn_control_generation IS NULL AND turn_control_mode IS NULL AND turn_activation_fence_seq IS NULL) OR
        (turn_control_generation IS NOT NULL AND turn_control_generation>0 AND turn_control_mode IS NOT NULL
          AND turn_ingress_seq IS NOT NULL AND normalized_event->>'kind'='CLIENT_MESSAGE' AND
          ((turn_control_mode='HUMAN' AND turn_activation_fence_seq IS NULL) OR
           (turn_control_mode='AI' AND turn_control_generation>=2 AND turn_activation_fence_seq IS NOT NULL
             AND turn_activation_fence_seq>0 AND turn_ingress_seq>turn_activation_fence_seq))))""")
    op.execute("""ALTER TABLE app.conversation_turns
      ADD COLUMN ingress_control_mode text,
      ADD COLUMN activation_fence_seq bigint,
      ADD CONSTRAINT turn_control_capture_check CHECK(
        (ingress_control_mode IS NULL AND activation_fence_seq IS NULL AND control_generation=1) OR
        (ingress_control_mode IS NOT NULL AND
          ((ingress_control_mode='HUMAN' AND activation_fence_seq IS NULL) OR
           (ingress_control_mode='AI' AND control_generation>=2 AND activation_fence_seq IS NOT NULL AND activation_fence_seq>0))))""")
    op.execute("""CREATE FUNCTION platform.conversation_control_fingerprint(
      ws uuid,actor uuid,conversation uuid,client uuid,operation text,generation bigint,context bigint)
      RETURNS bytea LANGUAGE sql IMMUTABLE STRICT SET search_path=pg_catalog,pg_temp AS $$
        SELECT sha256(convert_to(E'asm:m3:conversation_control:v1\n'||ws::text||E'\n'||actor::text||E'\n'||
          conversation::text||E'\n'||client::text||E'\n'||operation||E'\n'||generation::text||E'\n'||context::text,'UTF8'))
      $$""")
    op.execute("""ALTER TABLE app.audit_events
      ADD COLUMN conversation_object_id uuid GENERATED ALWAYS AS (CASE WHEN object_type='CONVERSATION' THEN object_id END) STORED,
      ADD COLUMN conversation_control_generation bigint GENERATED ALWAYS AS
        (CASE WHEN event_type IN ('CONVERSATION_TAKEN_OVER','CONVERSATION_RESUMED') THEN (payload->>'control_generation')::bigint END) STORED,
      ADD CONSTRAINT audit_events_conversation_fkey FOREIGN KEY(workspace_id,conversation_object_id)
        REFERENCES app.conversations(workspace_id,id) ON DELETE RESTRICT,
      ADD CONSTRAINT audit_events_control_ref_key UNIQUE(workspace_id,audit_event_id,conversation_object_id,
        conversation_control_generation,event_type,actor_user_account_id,object_version),
      DROP CONSTRAINT audit_events_discriminator_payload_check""")
    op.execute(f"""ALTER TABLE app.audit_events ADD CONSTRAINT audit_events_discriminator_payload_check CHECK(
      {OLD_AUDIT_CHECK} OR ((
        event_type IN ('CONVERSATION_TAKEN_OVER','CONVERSATION_RESUMED') AND actor_kind='USER_ACCOUNT'
        AND actor_user_account_id IS NOT NULL AND object_type='CONVERSATION' AND object_version>0
        AND conversation_object_id IS NOT NULL AND conversation_control_generation IS NOT NULL
        AND payload=jsonb_build_object('previous_mode',payload->>'previous_mode','control_mode',payload->>'control_mode',
          'previous_generation',payload->>'previous_generation','control_generation',payload->>'control_generation')
        AND payload->>'previous_mode' IN ('HUMAN','AI')
        AND payload->>'control_mode'=CASE event_type WHEN 'CONVERSATION_TAKEN_OVER' THEN 'HUMAN' ELSE 'AI' END
        AND CASE WHEN payload->>'previous_generation' ~ '^[1-9][0-9]{{0,18}}$'
                   AND payload->>'control_generation' ~ '^[1-9][0-9]{{0,18}}$'
          THEN (payload->>'previous_generation')::numeric<9223372036854775807
            AND (payload->>'control_generation')::numeric=(payload->>'previous_generation')::numeric+1
          ELSE false END) IS TRUE))""")
    op.execute("""CREATE TABLE platform.conversation_control_receipts(
      workspace_id uuid NOT NULL,id uuid NOT NULL DEFAULT uuidv7(),
      operation_namespace text NOT NULL DEFAULT 'CONVERSATION_CONTROL_V1' CHECK(operation_namespace='CONVERSATION_CONTROL_V1'),
      operation text NOT NULL CHECK(operation IN ('TAKEOVER','RESUME')),
      idempotency_key text NOT NULL CHECK(idempotency_key ~ '^[A-Za-z0-9._:-]{1,128}$'),
      conversation_id uuid NOT NULL,client_id uuid NOT NULL,actor_user_account_id uuid NOT NULL,correlation_id uuid NOT NULL,
      expected_generation bigint NOT NULL CHECK(expected_generation>0),
      expected_context_version bigint NOT NULL CHECK(expected_context_version>0),
      previous_mode text NOT NULL CHECK(previous_mode IN ('HUMAN','AI')),
      accepted_mode text NOT NULL CHECK(accepted_mode IN ('HUMAN','AI')),
      previous_generation bigint NOT NULL CHECK(previous_generation=expected_generation),
      accepted_generation bigint NOT NULL CHECK(accepted_generation::numeric=expected_generation::numeric+1),
      context_version bigint NOT NULL CHECK(context_version=expected_context_version),
      activation_fence_seq bigint,
      request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32),
      audit_event_id uuid NOT NULL,
      audit_event_type text GENERATED ALWAYS AS
        (CASE operation WHEN 'TAKEOVER' THEN 'CONVERSATION_TAKEN_OVER' ELSE 'CONVERSATION_RESUMED' END) STORED NOT NULL,
      accepted_at timestamptz NOT NULL CHECK(isfinite(accepted_at)),result jsonb NOT NULL,
      PRIMARY KEY(workspace_id,id),UNIQUE(workspace_id,operation_namespace,idempotency_key),
      UNIQUE(workspace_id,conversation_id,accepted_generation),UNIQUE(workspace_id,audit_event_id),
      FOREIGN KEY(workspace_id,conversation_id,client_id) REFERENCES app.conversations(workspace_id,id,client_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,actor_user_account_id) REFERENCES platform.workspace_memberships(workspace_id,user_account_id) ON DELETE RESTRICT,
      CONSTRAINT conversation_control_receipts_audit_fk
        FOREIGN KEY(workspace_id,audit_event_id,conversation_id,accepted_generation,audit_event_type,actor_user_account_id,context_version)
        REFERENCES app.audit_events(workspace_id,audit_event_id,conversation_object_id,conversation_control_generation,event_type,actor_user_account_id,object_version) ON DELETE RESTRICT,
      CHECK((operation='TAKEOVER' AND accepted_mode='HUMAN' AND activation_fence_seq IS NULL) OR
        (operation='RESUME' AND accepted_mode='AI' AND activation_fence_seq IS NOT NULL AND activation_fence_seq>0)),
      CHECK(request_fingerprint=platform.conversation_control_fingerprint(workspace_id,actor_user_account_id,conversation_id,client_id,operation,expected_generation,expected_context_version)),
      CHECK(result=jsonb_build_object('workspace_id',workspace_id,'conversation_id',conversation_id,'client_id',client_id,
        'receipt_id',id,'audit_event_id',audit_event_id,'operation',operation,'previous_mode',previous_mode,'accepted_mode',accepted_mode,
        'previous_generation',previous_generation::text,'accepted_generation',accepted_generation::text,'context_version',context_version::text,
        'accepted_at',to_char(accepted_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'))))""")
    op.execute("ALTER TABLE platform.conversation_control_receipts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE platform.conversation_control_receipts FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY control_migrator ON platform.conversation_control_receipts TO asm_migrator USING(true) WITH CHECK(true)"
    )
    op.execute("REVOKE ALL ON platform.conversation_control_receipts FROM PUBLIC,asm_runtime")
    op.execute(
        "CREATE TRIGGER control_receipt_immutable BEFORE UPDATE ON platform.conversation_control_receipts FOR EACH ROW EXECUTE FUNCTION platform.turn_immutable()"
    )


def _commands() -> None:
    op.execute("""CREATE FUNCTION platform.conversation_control_locked(
      p_conversation uuid,p_client uuid,p_operation text,p_key text,p_generation bigint,p_context bigint)
      RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE ws uuid; actor uuid; fingerprint bytea; rec platform.conversation_control_receipts%ROWTYPE;
        conv app.conversations%ROWTYPE;
      BEGIN
        PERFORM platform.turn_require_isolation();
        ws:=app.current_messaging_owner_workspace_id(); actor:=nullif(current_setting('asm.actor_id',true),'')::uuid;
        IF ws IS NULL OR nullif(current_setting('asm.correlation_id',true),'') IS NULL
          OR platform.messaging_lock_owner(ws,actor) IS NOT TRUE THEN
          RAISE EXCEPTION 'ACCESS_DENIED' USING ERRCODE='P2401'; END IF;
        IF p_conversation IS NULL OR p_client IS NULL OR p_operation IS NULL OR p_operation NOT IN ('TAKEOVER','RESUME')
          OR p_key IS NULL OR p_key !~ '^[A-Za-z0-9._:-]{1,128}$' OR p_generation IS NULL OR p_generation<1
          OR p_context IS NULL OR p_context<1 THEN RAISE EXCEPTION 'INVALID_REQUEST' USING ERRCODE='P2401'; END IF;
        fingerprint:=platform.conversation_control_fingerprint(ws,actor,p_conversation,p_client,p_operation,p_generation,p_context);
        PERFORM pg_advisory_xact_lock(hashtextextended(ws::text||':CONVERSATION_CONTROL_V1:'||p_key,2009));
        SELECT * INTO rec FROM platform.conversation_control_receipts
          WHERE workspace_id=ws AND operation_namespace='CONVERSATION_CONTROL_V1' AND idempotency_key=p_key;
        IF FOUND THEN
          IF rec.request_fingerprint<>fingerprint THEN RAISE EXCEPTION 'IDEMPOTENCY_KEY_CONFLICT' USING ERRCODE='P2401'; END IF;
          IF NOT EXISTS(SELECT 1 FROM app.conversations WHERE workspace_id=ws AND id=rec.conversation_id AND client_id=rec.client_id) THEN
            RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P2401'; END IF;
          RETURN jsonb_build_object('code','REPLAY','result',rec.result,'request_fingerprint',encode(fingerprint,'hex'));
        END IF;
        SELECT * INTO conv FROM app.conversations WHERE workspace_id=ws AND id=p_conversation AND client_id=p_client;
        IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P2401'; END IF;
        PERFORM 1 FROM app.businesses WHERE workspace_id=ws AND id=conv.business_id FOR SHARE;
        PERFORM 1 FROM app.channel_connections WHERE workspace_id=ws AND id=conv.connection_id FOR SHARE;
        IF p_operation='RESUME' THEN PERFORM platform.messaging_lock_billing_workspace(ws); END IF;
        SELECT * INTO conv FROM app.conversations WHERE workspace_id=ws AND id=p_conversation AND client_id=p_client FOR NO KEY UPDATE;
        IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P2401'; END IF;
        RETURN jsonb_build_object('code','NEW','request_fingerprint',encode(fingerprint,'hex'));
      END $$""")
    op.execute("""CREATE FUNCTION platform.conversation_control_prepare(
      p_conversation uuid,p_client uuid,p_operation text,p_key text,p_generation bigint,p_context bigint)
      RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$ BEGIN
        RETURN platform.conversation_control_locked(p_conversation,p_client,p_operation,p_key,p_generation,p_context);
      END $$""")
    op.execute("""CREATE FUNCTION platform.conversation_control_execute(
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
      END $$""")
    op.execute("""CREATE FUNCTION platform.conversation_control_read(p_conversation uuid) RETURNS jsonb
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
      END $$""")


def _manual() -> None:
    op.execute("""CREATE FUNCTION platform.conversation_manual_prelock(p_conversation uuid,p_text text,p_key text) RETURNS void
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE prepared jsonb; ws uuid; conv app.conversations%ROWTYPE;
      BEGIN
        PERFORM platform.turn_require_isolation();
        prepared:=platform.messaging_prepare_text(p_conversation,p_text,p_key);
        IF prepared->>'code'='REPLAY' THEN RETURN; END IF;
        ws:=app.current_messaging_owner_workspace_id();
        SELECT * INTO STRICT conv FROM app.conversations WHERE workspace_id=ws AND id=p_conversation;
        IF prepared->>'provider'='TELEGRAM' THEN
          PERFORM 1 FROM platform.telegram_connection_state WHERE workspace_id=ws AND connection_id=conv.connection_id FOR UPDATE;
        END IF;
        PERFORM platform.messaging_lock_billing_workspace(ws);
        PERFORM 1 FROM app.conversations WHERE workspace_id=ws AND id=p_conversation FOR NO KEY UPDATE;
      END $$""")
    op.execute("""CREATE FUNCTION platform.conversation_manual_takeover(ws uuid,p_conversation uuid) RETURNS void
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE conv app.conversations%ROWTYPE;
      BEGIN
        PERFORM platform.turn_require_isolation();
        SELECT * INTO STRICT conv FROM app.conversations WHERE workspace_id=ws AND id=p_conversation FOR NO KEY UPDATE;
        IF conv.control_generation=9223372036854775807 OR conv.version=9223372036854775807 THEN
          RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
        UPDATE app.conversations SET control_mode='HUMAN',control_generation=control_generation+1,activation_fence_seq=NULL
          WHERE workspace_id=ws AND id=p_conversation;
        -- The existing outbound Message material trigger owns the single context bump.
      END $$""")
    _replace(
        "messaging_request_text",
        (
            "          IF conn.provider='TELEGRAM' THEN",
            """          IF conn.provider='TELEGRAM' THEN
            PERFORM 1 FROM platform.telegram_connection_state WHERE workspace_id=ws AND connection_id=conn.id FOR SHARE;
            PERFORM platform.messaging_lock_billing_workspace(ws);
          END IF;
          PERFORM 1 FROM app.conversations WHERE workspace_id=ws AND id=conv.id FOR NO KEY UPDATE;
          IF conn.provider='TELEGRAM' THEN""",
        ),
        (
            "          INSERT INTO app.messages(",
            "          PERFORM platform.conversation_manual_takeover(ws,conv.id);\n          INSERT INTO app.messages(",
        ),
    )


def _capture() -> None:
    _replace(
        "turn_ingress",
        ("AS $$ BEGIN", "AS $$ DECLARE conv app.conversations%ROWTYPE; BEGIN"),
        (
            "NEW.turn_ingress_seq IS NOT NULL THEN",
            """NEW.turn_ingress_seq IS NOT NULL OR
          NEW.turn_control_generation IS NOT NULL OR NEW.turn_control_mode IS NOT NULL OR NEW.turn_activation_fence_seq IS NOT NULL THEN""",
        ),
        (
            "        NEW.turn_ingress_at:=",
            """        SELECT * INTO conv FROM app.conversations WHERE workspace_id=NEW.workspace_id AND connection_id=NEW.connection_id
          AND provider_chat_id=NEW.normalized_event->>'chat_id' FOR NO KEY UPDATE;
        IF FOUND THEN
          NEW.turn_control_generation:=conv.control_generation; NEW.turn_control_mode:=conv.control_mode;
          NEW.turn_activation_fence_seq:=conv.activation_fence_seq;
        ELSE NEW.turn_control_generation:=1; NEW.turn_control_mode:='HUMAN'; END IF;
        NEW.turn_ingress_at:=""",
        ),
    )
    _replace(
        "turn_member_check",
        (
            "IF (t.state<>",
            """IF (t.control_generation,t.ingress_control_mode,t.activation_fence_seq) IS DISTINCT FROM
          (coalesce(i.turn_control_generation,1),i.turn_control_mode,i.turn_activation_fence_seq) OR (t.state<>""",
        ),
    )
    _replace(
        "turn_group_message",
        (
            "late boolean:=false; fresh boolean:=false;",
            "late boolean:=false; fresh boolean:=false; generation bigint;",
        ),
        (
            "        SELECT * INTO t FROM app.conversation_turns",
            """        generation:=coalesce(origin.turn_control_generation,1);
        -- A delayed old origin cannot close a newer group, even if it has already sealed.
        late:=EXISTS(SELECT 1 FROM app.conversation_turns WHERE workspace_id=ws AND conversation_id=conv.id AND
          (control_generation>generation OR (control_generation=generation AND ingress_control_mode IS NOT NULL AND origin.turn_control_mode IS NULL)));
        SELECT * INTO t FROM app.conversation_turns""",
        ),
        (
            "        IF FOUND AND origin.turn_ingress_at<t.first_ingress_at THEN",
            "        IF late OR (FOUND AND origin.turn_ingress_at<t.first_ingress_at) THEN",
        ),
        (
            "ELSIF FOUND AND (origin.turn_ingress_at>=",
            """ELSIF FOUND AND ((t.control_generation,t.ingress_control_mode,t.activation_fence_seq) IS DISTINCT FROM
          (generation,origin.turn_control_mode,origin.turn_activation_fence_seq) OR origin.turn_ingress_at>=""",
        ),
        (
            "provider_chat_id,control_generation,state,",
            "provider_chat_id,control_generation,ingress_control_mode,activation_fence_seq,state,",
        ),
        (
            "m.provider_chat_id,conv.control_generation,CASE",
            "m.provider_chat_id,generation,origin.turn_control_mode,origin.turn_activation_fence_seq,CASE",
        ),
    )
    op.execute("DROP TRIGGER turn_ingress_immutable ON platform.inbox_events")
    op.execute("""CREATE TRIGGER turn_ingress_immutable BEFORE UPDATE ON platform.inbox_events FOR EACH ROW
      EXECUTE FUNCTION platform.messaging_immutable('turn_ingress_at','turn_ingress_seq','turn_control_generation','turn_control_mode','turn_activation_fence_seq')""")
    op.execute("DROP TRIGGER turn_identity ON app.conversation_turns")
    op.execute("""CREATE TRIGGER turn_identity BEFORE UPDATE ON app.conversation_turns FOR EACH ROW
      EXECUTE FUNCTION platform.messaging_immutable('workspace_id','id','conversation_id','connection_id','provider_chat_id','control_generation','first_ingress_at','hard_at','policy_version','debounce_ms','group_ms','media_ms','max_members','created_at','ingress_control_mode','activation_fence_seq')""")
    op.execute("""CREATE FUNCTION platform.conversation_turn_activation_matches(ws uuid,p_turn uuid) RETURNS boolean
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
      $$""")


def upgrade() -> None:
    _schema()
    _commands()
    _manual()
    _capture()
    for function in OWNER_FUNCTIONS + PRIVATE_FUNCTIONS:
        op.execute(f"ALTER FUNCTION {function} OWNER TO asm_migrator")
        op.execute(f"REVOKE ALL ON FUNCTION {function} FROM PUBLIC,asm_runtime")
    for function in OWNER_FUNCTIONS:
        op.execute(f"GRANT EXECUTE ON FUNCTION {function} TO asm_runtime")


def downgrade() -> None:
    # This is the first statement: populated CONTROL must refuse before any DDL.
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM platform.conversation_control_receipts)
        OR EXISTS(SELECT 1 FROM app.audit_events WHERE event_type IN ('CONVERSATION_TAKEN_OVER','CONVERSATION_RESUMED'))
        OR EXISTS(SELECT 1 FROM app.conversations WHERE control_mode<>'HUMAN' OR control_generation<>1 OR activation_fence_seq IS NOT NULL)
        OR EXISTS(SELECT 1 FROM platform.inbox_events WHERE turn_control_generation IS NOT NULL OR turn_control_mode IS NOT NULL OR turn_activation_fence_seq IS NOT NULL)
        OR EXISTS(SELECT 1 FROM app.conversation_turns WHERE ingress_control_mode IS NOT NULL OR activation_fence_seq IS NOT NULL) THEN
        RAISE EXCEPTION 'CONTROL data prevents downgrade' USING ERRCODE='55000'; END IF;
      END $$""")
    for body in ORIGINAL.values():
        op.execute(body.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1))
    op.execute("DROP TABLE platform.conversation_control_receipts")
    # Drop callers before their helpers; no CASCADE can hide an unexpected dependency.
    for function in OWNER_FUNCTIONS + tuple(reversed(PRIVATE_FUNCTIONS)):
        op.execute(f"DROP FUNCTION {function}")
    op.execute(
        "ALTER TABLE app.audit_events DROP CONSTRAINT audit_events_discriminator_payload_check, DROP CONSTRAINT audit_events_control_ref_key, DROP CONSTRAINT audit_events_conversation_fkey, DROP COLUMN conversation_control_generation, DROP COLUMN conversation_object_id"
    )
    op.execute(
        f"ALTER TABLE app.audit_events ADD CONSTRAINT audit_events_discriminator_payload_check CHECK({OLD_AUDIT_CHECK})"
    )
    op.execute("DROP TRIGGER turn_ingress_immutable ON platform.inbox_events")
    op.execute(
        "CREATE TRIGGER turn_ingress_immutable BEFORE UPDATE ON platform.inbox_events FOR EACH ROW EXECUTE FUNCTION platform.messaging_immutable('turn_ingress_at','turn_ingress_seq')"
    )
    op.execute("DROP TRIGGER turn_identity ON app.conversation_turns")
    op.execute("""CREATE TRIGGER turn_identity BEFORE UPDATE ON app.conversation_turns FOR EACH ROW
      EXECUTE FUNCTION platform.messaging_immutable('workspace_id','id','conversation_id','connection_id','provider_chat_id','control_generation','first_ingress_at','hard_at','policy_version','debounce_ms','group_ms','media_ms','max_members','created_at')""")
    op.execute(
        "ALTER TABLE platform.inbox_events DROP CONSTRAINT inbox_control_capture_check, DROP COLUMN turn_control_generation, DROP COLUMN turn_control_mode, DROP COLUMN turn_activation_fence_seq"
    )
    op.execute(
        "ALTER TABLE app.conversation_turns DROP CONSTRAINT turn_control_capture_check, DROP COLUMN ingress_control_mode, DROP COLUMN activation_fence_seq"
    )
    op.execute(
        "ALTER TABLE app.conversations DROP CONSTRAINT conversations_control_client_key, DROP CONSTRAINT conversations_control_mode_check, DROP COLUMN activation_fence_seq, ADD CONSTRAINT conversations_control_mode_check CHECK(control_mode='HUMAN')"
    )
