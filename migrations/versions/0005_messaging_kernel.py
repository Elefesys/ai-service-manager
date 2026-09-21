"""M2.1 controlled messaging: durable Inbox/Jobs and fenced manual sends.

Capabilities own all writes. A claim is a short lease, never provider idempotency.
All SECURITY DEFINER functions pin search_path and are individually granted.
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

PUBLIC_FUNCTIONS = (
    "app.current_messaging_owner_workspace_id()",
    "platform.messaging_ingest(text,text,jsonb,uuid)",
    "platform.messaging_claim(text)",
    "platform.messaging_admit(uuid,uuid)",
    "platform.messaging_process_inbox(uuid,uuid)",
    "platform.messaging_request_text(uuid,text,text)",
    "platform.messaging_begin_send(uuid,uuid)",
    "platform.messaging_finish_send(uuid,uuid,uuid,text,text,text)",
    "platform.messaging_retry(uuid,uuid,text,boolean)",
    "platform.messaging_recover_expired(integer)",
    "platform.messaging_read_conversations(integer)",
    "platform.messaging_read_messages(uuid,integer)",
    "platform.messaging_read_delivery(uuid)",
    "platform.messaging_read_inbox(uuid)",
)
PRIVATE_FUNCTIONS = (
    "platform.messaging_valid_id(text,integer,integer)",
    "platform.messaging_validate_event(jsonb)",
    "platform.messaging_fingerprint(jsonb,boolean)",
    "platform.messaging_immutable()",
    "platform.messaging_job_json(platform.messaging_jobs)",
    "platform.messaging_guard(uuid,uuid)",
    "platform.messaging_reschedule(uuid,text,boolean)",
    "platform.messaging_lock_owner(uuid,uuid)",
)
TABLES = (
    "app.channel_connections",
    "platform.channel_routes",
    "app.clients",
    "app.client_identities",
    "app.conversations",
    "app.messages",
    "platform.inbox_events",
    "app.outbox_events",
    "platform.messaging_jobs",
    "platform.messaging_command_receipts",
)
BILLING_AUDIT_CHECK = """(event_type='WORKSPACE_BILLING_PROVISIONED' AND
 actor_kind='LOCAL_PROVISIONER' AND actor_user_account_id IS NULL AND
 object_type='WORKSPACE_BILLING_ACCOUNT' AND payload='{}'::jsonb) OR
 (event_type='BILLING_ACCOUNT_CONTACT_UPDATED' AND actor_kind='USER_ACCOUNT' AND
 actor_user_account_id IS NOT NULL AND object_type='WORKSPACE_BILLING_ACCOUNT' AND
 payload='{"changed_fields":["contact_display_name"]}'::jsonb)"""


def upgrade() -> None:
    _tables()
    _audit()
    _helpers()
    _ingest()
    _worker()
    _commands()
    _send()
    _reads()
    for relation in TABLES:
        op.execute(f"ALTER TABLE {relation} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {relation} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY messaging_migrator ON {relation} TO asm_migrator USING(true) WITH CHECK(true)"
        )
    for relation in (
        "app.channel_connections",
        "app.clients",
        "app.client_identities",
        "app.conversations",
        "app.messages",
    ):
        op.execute(
            f"CREATE POLICY messaging_owner_read ON {relation} FOR SELECT TO asm_runtime USING(workspace_id=(SELECT app.current_messaging_owner_workspace_id()))"
        )
        op.execute(f"GRANT SELECT ON {relation} TO asm_runtime")
    for function in (*PUBLIC_FUNCTIONS, *PRIVATE_FUNCTIONS):
        op.execute(f"REVOKE ALL ON FUNCTION {function} FROM PUBLIC")
    for function in PUBLIC_FUNCTIONS:
        op.execute(f"GRANT EXECUTE ON FUNCTION {function} TO asm_runtime")


def _tables() -> None:
    op.execute("""CREATE TABLE app.channel_connections(
      workspace_id uuid NOT NULL REFERENCES platform.workspaces(id) ON DELETE RESTRICT,
      id uuid NOT NULL DEFAULT uuidv7(), business_id uuid NOT NULL,
      provider text NOT NULL CHECK(provider='CONTROLLED'), bot_identity text NOT NULL,
      external_connection_id text NOT NULL, status text NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','INACTIVE')),
      version bigint NOT NULL DEFAULT 1 CHECK(version>0),
      created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK(isfinite(created_at)),
      PRIMARY KEY(workspace_id,id),
      FOREIGN KEY(workspace_id,business_id) REFERENCES app.businesses(workspace_id,id) ON DELETE RESTRICT,
      UNIQUE(provider,bot_identity,external_connection_id),
      UNIQUE(workspace_id,id,business_id), UNIQUE(workspace_id,id,provider,bot_identity,external_connection_id))""")
    op.execute("""CREATE TABLE platform.channel_routes(
      workspace_id uuid NOT NULL, id uuid NOT NULL DEFAULT uuidv7(), connection_id uuid NOT NULL,
      provider text NOT NULL, bot_identity text NOT NULL, route_key text NOT NULL,
      created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK(isfinite(created_at)),
      PRIMARY KEY(workspace_id,id), UNIQUE(provider,bot_identity,route_key),
      FOREIGN KEY(workspace_id,connection_id,provider,bot_identity,route_key)
        REFERENCES app.channel_connections(workspace_id,id,provider,bot_identity,external_connection_id) ON DELETE RESTRICT)""")
    op.execute("""CREATE TABLE app.clients(
      workspace_id uuid NOT NULL REFERENCES platform.workspaces(id) ON DELETE RESTRICT,
      id uuid NOT NULL DEFAULT uuidv7(), version bigint NOT NULL DEFAULT 1 CHECK(version>0),
      created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK(isfinite(created_at)),
      PRIMARY KEY(workspace_id,id))""")
    op.execute("""CREATE TABLE app.client_identities(
      workspace_id uuid NOT NULL, id uuid NOT NULL DEFAULT uuidv7(), client_id uuid NOT NULL,
      provider text NOT NULL CHECK(provider='CONTROLLED'), external_user_id text NOT NULL,
      created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK(isfinite(created_at)),
      PRIMARY KEY(workspace_id,id), UNIQUE(workspace_id,provider,external_user_id),
      UNIQUE(workspace_id,id,client_id),
      FOREIGN KEY(workspace_id,client_id) REFERENCES app.clients(workspace_id,id) ON DELETE RESTRICT)""")
    op.execute("""CREATE TABLE app.conversations(
      workspace_id uuid NOT NULL, id uuid NOT NULL DEFAULT uuidv7(), connection_id uuid NOT NULL,
      business_id uuid NOT NULL, client_id uuid NOT NULL, identity_id uuid NOT NULL,
      provider_chat_id text NOT NULL, version bigint NOT NULL DEFAULT 1 CHECK(version>0),
      created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK(isfinite(created_at)),
      PRIMARY KEY(workspace_id,id), UNIQUE(workspace_id,connection_id,provider_chat_id),
      UNIQUE(workspace_id,id,connection_id,provider_chat_id),
      FOREIGN KEY(workspace_id,connection_id,business_id) REFERENCES app.channel_connections(workspace_id,id,business_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,identity_id,client_id) REFERENCES app.client_identities(workspace_id,id,client_id) ON DELETE RESTRICT)""")
    op.execute("""CREATE TABLE app.messages(
      workspace_id uuid NOT NULL, id uuid NOT NULL DEFAULT uuidv7(), conversation_id uuid NOT NULL,
      connection_id uuid NOT NULL, provider_chat_id text NOT NULL, provider_message_id text,
      direction text NOT NULL CHECK(direction IN ('INBOUND','OUTBOUND')),
      content_type text NOT NULL CHECK(content_type IN ('TEXT','IMAGE_REFERENCE')),
      text text, image_file_id text, media_group_id text, occurred_at timestamptz NOT NULL CHECK(isfinite(occurred_at)),
      projection_fingerprint bytea, version bigint NOT NULL DEFAULT 1 CHECK(version>0),
      created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK(isfinite(created_at)),
      PRIMARY KEY(workspace_id,id), UNIQUE(workspace_id,id,connection_id),
      UNIQUE(workspace_id,id,connection_id,direction),
      UNIQUE(workspace_id,connection_id,provider_chat_id,provider_message_id),
      FOREIGN KEY(workspace_id,conversation_id,connection_id,provider_chat_id) REFERENCES app.conversations(workspace_id,id,connection_id,provider_chat_id) ON DELETE RESTRICT,
      CHECK((content_type='TEXT' AND text IS NOT NULL AND char_length(text)>0 AND image_file_id IS NULL) OR (content_type='IMAGE_REFERENCE' AND image_file_id IS NOT NULL)),
      CHECK(text IS NULL OR (char_length(text)<=4096 AND octet_length(text)<=16384)),
      CHECK((direction='INBOUND' AND provider_message_id IS NOT NULL AND projection_fingerprint IS NOT NULL AND octet_length(projection_fingerprint)=32) OR (direction='OUTBOUND' AND provider_message_id IS NULL AND content_type='TEXT' AND projection_fingerprint IS NULL)))""")
    op.execute(
        "CREATE INDEX messages_chronological_idx ON app.messages(workspace_id,conversation_id,created_at,id)"
    )
    op.execute("""CREATE TABLE platform.inbox_events(
      workspace_id uuid NOT NULL, id uuid NOT NULL DEFAULT uuidv7(), connection_id uuid NOT NULL,
      provider text NOT NULL, bot_identity text NOT NULL, external_connection_id text NOT NULL,
      required_direction text NOT NULL DEFAULT 'INBOUND' CHECK(required_direction='INBOUND'),
      event_id text NOT NULL, normalized_event jsonb NOT NULL, event_fingerprint bytea NOT NULL CHECK(octet_length(event_fingerprint)=32),
      correlation_id uuid NOT NULL, received_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK(isfinite(received_at)),
      status text NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','PROCESSED','IGNORED','FAILED')),
      result_code text, message_id uuid, completed_at timestamptz CHECK(isfinite(completed_at)),
      version bigint NOT NULL DEFAULT 1 CHECK(version>0),
      PRIMARY KEY(workspace_id,id), UNIQUE(provider,bot_identity,event_id), UNIQUE(workspace_id,id,connection_id),
      FOREIGN KEY(workspace_id,connection_id,provider,bot_identity,external_connection_id) REFERENCES app.channel_connections(workspace_id,id,provider,bot_identity,external_connection_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,message_id,connection_id,required_direction) REFERENCES app.messages(workspace_id,id,connection_id,direction) ON DELETE RESTRICT,
      CHECK((status='PENDING' AND result_code IS NULL AND message_id IS NULL AND completed_at IS NULL) OR
       (status='PROCESSED' AND result_code IS NOT NULL AND result_code IN ('PROCESSED','DUPLICATE') AND message_id IS NOT NULL AND completed_at IS NOT NULL) OR
       (status='IGNORED' AND result_code IS NOT NULL AND result_code IN ('IGNORED_NATIVE_OWNER_MESSAGE','IGNORED_MESSAGE_EDITED','IGNORED_MESSAGE_DELETED','IGNORED_UNSUPPORTED') AND message_id IS NULL AND completed_at IS NOT NULL) OR
       (status='FAILED' AND result_code IS NOT NULL AND result_code IN ('MESSAGE_ID_CONFLICT','CONVERSATION_IDENTITY_CONFLICT','RETRY_EXHAUSTED','DEPENDENCY_TIMEOUT','DEPENDENCY_UNAVAILABLE','INVALID_INPUT') AND message_id IS NULL AND completed_at IS NOT NULL)))""")
    op.execute("""CREATE TABLE app.outbox_events(
      workspace_id uuid NOT NULL, id uuid NOT NULL DEFAULT uuidv7(), connection_id uuid NOT NULL, message_id uuid NOT NULL,
      kind text NOT NULL DEFAULT 'SEND_MANUAL_TEXT' CHECK(kind='SEND_MANUAL_TEXT'),
      required_direction text NOT NULL DEFAULT 'OUTBOUND' CHECK(required_direction='OUTBOUND'),
      status text NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','DISPATCHING','SENT','FAILED','UNKNOWN')),
      attempt_id uuid, provider_message_id text, error_code text, completed_at timestamptz CHECK(isfinite(completed_at)),
      version bigint NOT NULL DEFAULT 1 CHECK(version>0),
      created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK(isfinite(created_at)),
      PRIMARY KEY(workspace_id,id), UNIQUE(workspace_id,message_id), UNIQUE(workspace_id,id,connection_id), UNIQUE(workspace_id,id,message_id),
      FOREIGN KEY(workspace_id,message_id,connection_id,required_direction) REFERENCES app.messages(workspace_id,id,connection_id,direction) ON DELETE RESTRICT,
      CHECK((status='PENDING' AND provider_message_id IS NULL AND completed_at IS NULL) OR
       (status='DISPATCHING' AND attempt_id IS NOT NULL AND provider_message_id IS NULL AND error_code IS NULL AND completed_at IS NULL) OR
       (status='SENT' AND attempt_id IS NOT NULL AND provider_message_id IS NOT NULL AND error_code IS NULL AND completed_at IS NOT NULL) OR
       (status IN ('FAILED','UNKNOWN') AND provider_message_id IS NULL AND error_code IS NOT NULL AND completed_at IS NOT NULL)),
      CHECK(status<>'UNKNOWN' OR attempt_id IS NOT NULL),
      CHECK((status='UNKNOWN' AND error_code IS NOT NULL AND error_code='UNKNOWN_EXTERNAL_RESULT') OR
       (status<>'UNKNOWN' AND (error_code IS NULL OR error_code<>'UNKNOWN_EXTERNAL_RESULT'))),
      CHECK(status<>'PENDING' OR error_code IS NULL OR error_code IN ('DEPENDENCY_TIMEOUT','DEPENDENCY_UNAVAILABLE')),
      CHECK(error_code IS NULL OR error_code IN ('NOT_ALLOWED','RETRY_EXHAUSTED','DEPENDENCY_TIMEOUT','DEPENDENCY_UNAVAILABLE','UNKNOWN_EXTERNAL_RESULT','INVALID_INPUT')))""")
    op.execute("""CREATE TABLE platform.messaging_jobs(
      workspace_id uuid NOT NULL, id uuid NOT NULL DEFAULT uuidv7(), connection_id uuid NOT NULL,
      kind text NOT NULL CHECK(kind IN ('PROCESS_INBOX','SEND_MANUAL_TEXT')), inbox_id uuid, outbox_id uuid,
      correlation_id uuid NOT NULL, status text NOT NULL DEFAULT 'READY' CHECK(status IN ('READY','RUNNING','SUCCEEDED','DEAD')),
      available_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK(isfinite(available_at)),
      claim_token uuid, lease_until timestamptz CHECK(isfinite(lease_until)), worker_id text,
      attempt_count integer NOT NULL DEFAULT 0 CHECK(attempt_count BETWEEN 0 AND 5), first_started_at timestamptz CHECK(isfinite(first_started_at)),
      error_code text, completed_at timestamptz CHECK(isfinite(completed_at)),
      last_attempt_id uuid, last_claim_token uuid, last_outcome text, last_provider_message_id text, last_error_code text,
      version bigint NOT NULL DEFAULT 1 CHECK(version>0),
      created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK(isfinite(created_at)),
      PRIMARY KEY(workspace_id,id), UNIQUE(id), UNIQUE(workspace_id,inbox_id), UNIQUE(workspace_id,outbox_id),
      FOREIGN KEY(workspace_id,inbox_id,connection_id) REFERENCES platform.inbox_events(workspace_id,id,connection_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,outbox_id,connection_id) REFERENCES app.outbox_events(workspace_id,id,connection_id) ON DELETE RESTRICT,
      CHECK((kind='PROCESS_INBOX' AND inbox_id IS NOT NULL AND outbox_id IS NULL) OR (kind='SEND_MANUAL_TEXT' AND outbox_id IS NOT NULL AND inbox_id IS NULL)),
      CHECK((status='RUNNING' AND claim_token IS NOT NULL AND lease_until IS NOT NULL AND worker_id IS NOT NULL AND completed_at IS NULL) OR
       (status='READY' AND claim_token IS NULL AND lease_until IS NULL AND worker_id IS NULL AND completed_at IS NULL) OR
       (status IN ('SUCCEEDED','DEAD') AND claim_token IS NULL AND lease_until IS NULL AND worker_id IS NULL AND completed_at IS NOT NULL)),
      CHECK(error_code IS NULL OR error_code IN ('NOT_ALLOWED','RETRY_EXHAUSTED','DEPENDENCY_TIMEOUT','DEPENDENCY_UNAVAILABLE','UNKNOWN_EXTERNAL_RESULT','INVALID_INPUT','MESSAGE_ID_CONFLICT','CONVERSATION_IDENTITY_CONFLICT')),
      CHECK((status='SUCCEEDED' AND error_code IS NULL) OR (status='DEAD' AND error_code IS NOT NULL) OR status IN ('READY','RUNNING')),
      CHECK(last_error_code IS NULL OR last_error_code IN ('NOT_ALLOWED','DEPENDENCY_TIMEOUT','DEPENDENCY_UNAVAILABLE','UNKNOWN_EXTERNAL_RESULT','INVALID_INPUT')),
      CHECK(status='READY' OR attempt_count>0),
      CHECK((attempt_count=0 AND first_started_at IS NULL) OR (attempt_count>0 AND first_started_at IS NOT NULL)),
      CHECK((last_attempt_id IS NULL AND last_claim_token IS NULL AND last_outcome IS NULL AND last_provider_message_id IS NULL AND last_error_code IS NULL) OR
       (last_attempt_id IS NOT NULL AND last_claim_token IS NOT NULL AND last_outcome IS NOT NULL AND last_outcome IN ('SUCCESS','NOT_SENT_RETRYABLE','NOT_SENT_PERMANENT','UNKNOWN') AND
        ((last_outcome='SUCCESS' AND last_provider_message_id IS NOT NULL AND last_error_code IS NULL) OR (last_outcome<>'SUCCESS' AND last_provider_message_id IS NULL AND last_error_code IS NOT NULL)))))""")
    op.execute(
        "CREATE INDEX messaging_jobs_due_idx ON platform.messaging_jobs(available_at,id) WHERE status='READY'"
    )
    op.execute(
        "CREATE INDEX messaging_jobs_expired_idx ON platform.messaging_jobs(lease_until,id) WHERE status='RUNNING'"
    )


def _audit() -> None:
    op.execute(
        "ALTER TABLE app.audit_events DROP CONSTRAINT audit_events_object_fkey, DROP CONSTRAINT audit_events_discriminator_payload_check"
    )
    op.execute("""ALTER TABLE app.audit_events
      ADD COLUMN billing_account_object_id uuid GENERATED ALWAYS AS (CASE WHEN object_type='WORKSPACE_BILLING_ACCOUNT' THEN object_id END) STORED,
      ADD COLUMN message_object_id uuid GENERATED ALWAYS AS (CASE WHEN object_type='MESSAGE' THEN object_id END) STORED,
      ADD CONSTRAINT audit_events_billing_object_fkey FOREIGN KEY(workspace_id,billing_account_object_id) REFERENCES platform.workspace_billing_accounts(workspace_id,billing_account_id) ON DELETE RESTRICT,
      ADD CONSTRAINT audit_events_message_object_fkey FOREIGN KEY(workspace_id,message_object_id) REFERENCES app.messages(workspace_id,id) ON DELETE RESTRICT,
      ADD CONSTRAINT audit_events_message_ref_key UNIQUE(workspace_id,audit_event_id,message_object_id)""")
    op.execute(
        f"""ALTER TABLE app.audit_events ADD CONSTRAINT audit_events_discriminator_payload_check CHECK ({BILLING_AUDIT_CHECK} OR (event_type='MESSAGE_SEND_REQUESTED' AND actor_kind='USER_ACCOUNT' AND actor_user_account_id IS NOT NULL AND object_type='MESSAGE' AND object_version=1 AND payload='{{"content_type":"TEXT"}}'::jsonb))"""
    )
    op.execute(
        "CREATE UNIQUE INDEX audit_events_message_send_key ON app.audit_events(workspace_id,message_object_id,event_type) WHERE event_type='MESSAGE_SEND_REQUESTED'"
    )
    op.execute("""CREATE TABLE platform.messaging_command_receipts(
      workspace_id uuid NOT NULL, id uuid NOT NULL DEFAULT uuidv7(), operation text NOT NULL DEFAULT 'SEND_MANUAL_TEXT' CHECK(operation='SEND_MANUAL_TEXT'),
      idempotency_key text NOT NULL CHECK(idempotency_key ~ '^[A-Za-z0-9._:-]{1,128}$'),
      request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32), actor_user_account_id uuid NOT NULL,
      correlation_id uuid NOT NULL, message_id uuid NOT NULL, outbox_id uuid NOT NULL, audit_event_id uuid NOT NULL,
      accepted_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK(isfinite(accepted_at)),
      PRIMARY KEY(workspace_id,id), UNIQUE(workspace_id,operation,idempotency_key), UNIQUE(workspace_id,message_id),
      FOREIGN KEY(workspace_id,actor_user_account_id) REFERENCES platform.workspace_memberships(workspace_id,user_account_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,outbox_id,message_id) REFERENCES app.outbox_events(workspace_id,id,message_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,audit_event_id,message_id) REFERENCES app.audit_events(workspace_id,audit_event_id,message_object_id) ON DELETE RESTRICT)""")


def _helpers() -> None:
    op.execute(r"""CREATE FUNCTION platform.messaging_valid_id(value text,max_chars integer,max_bytes integer)
      RETURNS boolean LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $$
      SELECT value IS NOT NULL AND char_length(value) BETWEEN 1 AND max_chars AND octet_length(value)<=max_bytes AND value !~ '[\x01-\x1F\x7F-\x9F]' $$""")
    op.execute(r"""CREATE FUNCTION platform.messaging_validate_event(e jsonb) RETURNS jsonb
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
          BEGIN occurred:=(e->>'occurred_at')::timestamptz;
          EXCEPTION WHEN OTHERS THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END;
          IF NOT isfinite(occurred) THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
          normalized:=jsonb_set(e,'{occurred_at}',to_jsonb(to_char(occurred AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"')));
        END IF;
        IF e->>'kind'='CLIENT_MESSAGE' AND (e->>'chat_id' IS NULL OR e->>'message_id' IS NULL OR e->>'sender_id' IS NULL OR occurred IS NULL OR
          (coalesce(char_length(e->>'text'),0)=0 AND e->>'image_file_id' IS NULL)) THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        RETURN normalized;
      END $$""")
    op.execute(r"""CREATE FUNCTION platform.messaging_fingerprint(e jsonb,projection boolean)
      RETURNS bytea LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $$
      DECLARE encoded bytea:=convert_to(E'asm:m2:normalized_event:v1\n','UTF8'); key text; value text;
      BEGIN
        FOREACH key IN ARRAY ARRAY['provider','bot_identity','event_id','kind','external_connection_id','chat_id','message_id','sender_id','occurred_at','text','image_file_id','media_group_id'] LOOP
          IF projection AND key='event_id' THEN CONTINUE; END IF;
          value:=e->>key;
          IF value IS NULL THEN encoded:=encoded||convert_to(E'-1:\n','UTF8');
          ELSE encoded:=encoded||convert_to(octet_length(value)::text||':'||value||E'\n','UTF8'); END IF;
        END LOOP;
        RETURN sha256(encoded);
      END $$""")
    op.execute("""CREATE FUNCTION platform.messaging_immutable() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
      DECLARE field text;
      BEGIN
        FOREACH field IN ARRAY TG_ARGV LOOP
          IF to_jsonb(NEW)->field IS DISTINCT FROM to_jsonb(OLD)->field THEN RAISE EXCEPTION 'immutable messaging identity' USING ERRCODE='23514'; END IF;
        END LOOP;
        RETURN NEW;
      END $$""")
    immutable = {
        "app.channel_connections": (
            "workspace_id",
            "id",
            "business_id",
            "provider",
            "bot_identity",
            "external_connection_id",
        ),
        "platform.channel_routes": (
            "workspace_id",
            "id",
            "connection_id",
            "provider",
            "bot_identity",
            "route_key",
        ),
        "app.client_identities": (
            "workspace_id",
            "id",
            "client_id",
            "provider",
            "external_user_id",
        ),
        "app.conversations": (
            "workspace_id",
            "id",
            "business_id",
            "connection_id",
            "client_id",
            "identity_id",
            "provider_chat_id",
        ),
        "app.messages": (
            "workspace_id",
            "id",
            "conversation_id",
            "connection_id",
            "provider_chat_id",
            "provider_message_id",
            "direction",
            "content_type",
            "text",
            "image_file_id",
            "media_group_id",
            "occurred_at",
            "projection_fingerprint",
        ),
        "platform.inbox_events": (
            "workspace_id",
            "id",
            "connection_id",
            "provider",
            "bot_identity",
            "external_connection_id",
            "event_id",
            "normalized_event",
            "event_fingerprint",
            "correlation_id",
            "received_at",
        ),
        "platform.messaging_command_receipts": (
            "workspace_id",
            "id",
            "operation",
            "idempotency_key",
            "request_fingerprint",
            "actor_user_account_id",
            "correlation_id",
            "message_id",
            "outbox_id",
            "audit_event_id",
            "accepted_at",
        ),
    }
    for relation, fields in immutable.items():
        arguments = ",".join(f"'{field}'" for field in fields)
        op.execute(
            f"CREATE TRIGGER messaging_immutable BEFORE UPDATE ON {relation} FOR EACH ROW EXECUTE FUNCTION platform.messaging_immutable({arguments})"
        )
    for relation, column, chars, size in (
        ("app.channel_connections", "bot_identity", 256, 1024),
        ("app.channel_connections", "external_connection_id", 256, 1024),
        ("app.client_identities", "external_user_id", 256, 1024),
        ("app.conversations", "provider_chat_id", 256, 1024),
        ("app.messages", "provider_chat_id", 256, 1024),
        ("app.messages", "provider_message_id", 256, 1024),
        ("app.messages", "image_file_id", 1024, 4096),
        ("app.messages", "media_group_id", 256, 1024),
        ("app.outbox_events", "provider_message_id", 256, 1024),
        ("platform.inbox_events", "event_id", 256, 1024),
    ):
        op.execute(
            f"ALTER TABLE {relation} ADD CONSTRAINT {column}_bounds CHECK({column} IS NULL OR platform.messaging_valid_id({column},{chars},{size}))"
        )
    op.execute("""CREATE FUNCTION app.current_messaging_owner_workspace_id() RETURNS uuid
      LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE ws uuid; actor uuid;
      BEGIN
        ws:=app.current_workspace_id();
        actor:=nullif(current_setting('asm.actor_id',true),'')::uuid;
        IF ws IS NOT NULL AND EXISTS(SELECT 1 FROM platform.workspace_memberships WHERE workspace_id=ws AND user_account_id=actor AND role='OWNER' AND status='ACTIVE') THEN RETURN ws; END IF;
        RETURN NULL;
      EXCEPTION WHEN invalid_text_representation THEN RETURN NULL;
      END $$""")
    op.execute("""CREATE FUNCTION platform.messaging_lock_owner(ws uuid,actor uuid) RETURNS boolean
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE wstate text; ustate text; member platform.workspace_memberships%ROWTYPE;
      BEGIN
        SELECT status INTO wstate FROM platform.workspaces WHERE id=ws FOR SHARE;
        SELECT status INTO ustate FROM platform.user_accounts WHERE id=actor FOR SHARE;
        SELECT * INTO member FROM platform.workspace_memberships WHERE workspace_id=ws AND user_account_id=actor FOR SHARE;
        RETURN wstate='ACTIVE' AND ustate='ACTIVE' AND member.role='OWNER' AND member.status='ACTIVE';
      END $$""")
    op.execute("""CREATE FUNCTION platform.messaging_job_json(j platform.messaging_jobs) RETURNS jsonb
      LANGUAGE sql STABLE SET search_path=pg_catalog,pg_temp AS $$ SELECT jsonb_build_object(
      'job_id',j.id,'kind',j.kind,'workspace_id',j.workspace_id,'connection_id',j.connection_id,
      'inbox_id',j.inbox_id,'outbox_id',j.outbox_id,'claim_token',j.claim_token,'lease_until',j.lease_until,
      'correlation_id',j.correlation_id,'attempt_count',j.attempt_count) $$""")
    op.execute("""CREATE FUNCTION platform.messaging_guard(p_job uuid,p_claim uuid) RETURNS platform.messaging_jobs
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
      END $$""")
    op.execute("""CREATE FUNCTION platform.messaging_reschedule(p_job uuid,p_error text,p_retry boolean) RETURNS jsonb
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
        IF j.kind='PROCESS_INBOX' AND NOT retry THEN
          UPDATE platform.inbox_events SET status='FAILED',result_code=final_error,completed_at=clock_timestamp(),version=version+1 WHERE workspace_id=j.workspace_id AND id=j.inbox_id;
        ELSIF j.kind='SEND_MANUAL_TEXT' THEN
          delivery:=CASE WHEN retry THEN 'PENDING' ELSE 'FAILED' END;
          UPDATE app.outbox_events SET status=delivery,error_code=final_error,completed_at=CASE WHEN retry THEN NULL ELSE clock_timestamp() END,version=version+1 WHERE workspace_id=j.workspace_id AND id=j.outbox_id;
        END IF;
        RETURN jsonb_build_object('code',CASE WHEN retry THEN 'RETRY_SCHEDULED' ELSE final_error END,'status',coalesce(delivery,CASE WHEN retry THEN 'READY' ELSE 'DEAD' END),'job_id',j.id,'outbox_id',j.outbox_id);
      END $$""")


def _ingest() -> None:
    op.execute("""CREATE FUNCTION platform.messaging_ingest(p_provider text,p_bot text,p_event jsonb,p_correlation uuid) RETURNS jsonb
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
      END $$""")


def _worker() -> None:
    op.execute("""CREATE FUNCTION platform.messaging_claim(p_worker text) RETURNS jsonb
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
      END $$""")
    op.execute("""CREATE FUNCTION platform.messaging_admit(p_job uuid,p_claim uuid) RETURNS jsonb
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
      END $$""")
    op.execute("""CREATE FUNCTION platform.messaging_process_inbox(p_job uuid,p_claim uuid) RETURNS jsonb
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
        PERFORM platform.messaging_guard(p_job,p_claim);
        UPDATE platform.inbox_events SET status=state,result_code=code,message_id=msg.id,completed_at=clock_timestamp(),version=version+1 WHERE workspace_id=j.workspace_id AND id=inbox.id;
        UPDATE platform.messaging_jobs SET status=CASE WHEN state='FAILED' THEN 'DEAD' ELSE 'SUCCEEDED' END,error_code=CASE WHEN state='FAILED' THEN code END,
          claim_token=NULL,lease_until=NULL,worker_id=NULL,completed_at=clock_timestamp(),version=version+1 WHERE id=j.id;
        RETURN jsonb_build_object('code',code,'inbox_id',inbox.id,'message_id',msg.id,'status',state);
      END $$""")
    op.execute("""CREATE FUNCTION platform.messaging_retry(p_job uuid,p_claim uuid,p_error text,p_retry boolean) RETURNS jsonb
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
      END $$""")
    op.execute("""CREATE FUNCTION platform.messaging_recover_expired(p_limit integer) RETURNS jsonb
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
      END $$""")


def _commands() -> None:
    op.execute(r"""CREATE FUNCTION platform.messaging_request_text(p_conversation uuid,p_text text,p_key text) RETURNS jsonb
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
      END $$""")


def _send() -> None:
    op.execute("""CREATE FUNCTION platform.messaging_begin_send(p_job uuid,p_claim uuid) RETURNS jsonb
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
      END $$""")
    op.execute("""CREATE FUNCTION platform.messaging_finish_send(p_job uuid,p_claim uuid,p_attempt uuid,p_outcome text,p_provider_message text,p_error text) RETURNS jsonb
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
      END $$""")


def _reads() -> None:
    op.execute("""CREATE FUNCTION platform.messaging_read_conversations(p_limit integer) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE ws uuid; result jsonb;
      BEGIN
        ws:=app.current_messaging_owner_workspace_id();
        IF ws IS NULL THEN RAISE EXCEPTION 'ACCESS_DENIED' USING ERRCODE='P2001'; END IF;
        IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 100 THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        SELECT coalesce(jsonb_agg(to_jsonb(items)),'[]'::jsonb) INTO result FROM
          (SELECT workspace_id,id AS conversation_id,connection_id,business_id,client_id,identity_id,provider_chat_id,version,created_at
           FROM app.conversations WHERE workspace_id=ws ORDER BY created_at DESC,id DESC LIMIT p_limit) items;
        RETURN result;
      END $$""")
    op.execute("""CREATE FUNCTION platform.messaging_read_messages(p_conversation uuid,p_limit integer) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE ws uuid; result jsonb;
      BEGIN
        ws:=app.current_messaging_owner_workspace_id();
        IF ws IS NULL THEN RAISE EXCEPTION 'ACCESS_DENIED' USING ERRCODE='P2001'; END IF;
        IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 100 THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        IF NOT EXISTS(SELECT 1 FROM app.conversations WHERE workspace_id=ws AND id=p_conversation) THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P2001'; END IF;
        SELECT coalesce(jsonb_agg(to_jsonb(items)),'[]'::jsonb) INTO result FROM
          (SELECT workspace_id,id AS message_id,conversation_id,connection_id,provider_chat_id,provider_message_id,direction,content_type,text,image_file_id,media_group_id,occurred_at,created_at,version
           FROM app.messages WHERE workspace_id=ws AND conversation_id=p_conversation ORDER BY created_at DESC,id DESC LIMIT p_limit) items;
        RETURN result;
      END $$""")
    op.execute("""CREATE FUNCTION platform.messaging_read_delivery(p_message uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE ws uuid; result jsonb;
      BEGIN
        ws:=app.current_messaging_owner_workspace_id();
        IF ws IS NULL THEN RAISE EXCEPTION 'ACCESS_DENIED' USING ERRCODE='P2001'; END IF;
        SELECT jsonb_build_object('workspace_id',workspace_id,'outbox_id',id,'message_id',message_id,'connection_id',connection_id,'kind',kind,'status',status,'provider_message_id',provider_message_id,'error_code',error_code,'completed_at',completed_at,'created_at',created_at,'version',version)
        INTO result FROM app.outbox_events WHERE workspace_id=ws AND message_id=p_message;
        IF result IS NULL THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P2001'; END IF;
        RETURN result;
      END $$""")
    op.execute("""CREATE FUNCTION platform.messaging_read_inbox(p_inbox uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE ws uuid; result jsonb;
      BEGIN
        ws:=app.current_messaging_owner_workspace_id();
        IF ws IS NULL THEN RAISE EXCEPTION 'ACCESS_DENIED' USING ERRCODE='P2001'; END IF;
        SELECT jsonb_build_object('workspace_id',workspace_id,'inbox_id',id,'connection_id',connection_id,'status',status,'result_code',result_code,'message_id',message_id,'received_at',received_at,'completed_at',completed_at)
        INTO result FROM platform.inbox_events WHERE workspace_id=ws AND id=p_inbox;
        IF result IS NULL THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P2001'; END IF;
        RETURN result;
      END $$""")


def downgrade() -> None:
    # Disposable TEST only: inbound/outbound history is intentionally removed.
    # Preserve every billing Audit row and billing command receipt.
    for relation in (
        "app.channel_connections",
        "app.clients",
        "app.client_identities",
        "app.conversations",
        "app.messages",
    ):
        op.execute(f"DROP POLICY messaging_owner_read ON {relation}")
    for function in reversed(PUBLIC_FUNCTIONS):
        op.execute(f"DROP FUNCTION {function}")
    for relation in TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS messaging_immutable ON {relation}")
    op.execute("DROP TABLE platform.messaging_command_receipts")
    op.execute("DELETE FROM app.audit_events WHERE event_type='MESSAGE_SEND_REQUESTED'")
    op.execute("DROP INDEX app.audit_events_message_send_key")
    op.execute("""ALTER TABLE app.audit_events DROP CONSTRAINT audit_events_discriminator_payload_check,
      DROP CONSTRAINT audit_events_message_ref_key, DROP CONSTRAINT audit_events_message_object_fkey,
      DROP CONSTRAINT audit_events_billing_object_fkey, DROP COLUMN billing_account_object_id, DROP COLUMN message_object_id""")
    op.execute(
        f"ALTER TABLE app.audit_events ADD CONSTRAINT audit_events_discriminator_payload_check CHECK({BILLING_AUDIT_CHECK})"
    )
    op.execute(
        "ALTER TABLE app.audit_events ADD CONSTRAINT audit_events_object_fkey FOREIGN KEY(workspace_id,object_id) REFERENCES platform.workspace_billing_accounts(workspace_id,billing_account_id) ON DELETE RESTRICT"
    )
    # Drop composite-return helpers before their table types; ID checks after tables.
    for function in reversed(PRIVATE_FUNCTIONS):
        if function != "platform.messaging_valid_id(text,integer,integer)":
            op.execute(f"DROP FUNCTION {function}")
    for relation in reversed(TABLES[:-1]):
        op.execute(f"DROP TABLE {relation}")
    op.execute("DROP FUNCTION platform.messaging_valid_id(text,integer,integer)")
