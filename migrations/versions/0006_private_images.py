"""M2.2 private images: canonical file capabilities and fenced upload cleanup.

The embedded 0005 definitions restore only changed functions on TEST downgrade.
Applied migrations remain byte-for-byte unchanged. No provider or storage I/O.
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

PUBLIC_FUNCTIONS = (
    "platform.files_begin_fetch(uuid,uuid)",
    "platform.files_prepare_upload(uuid,uuid,jsonb)",
    "platform.files_finish_fetch(uuid,uuid,uuid)",
    "platform.files_claim_cleanup(integer)",
    "platform.files_finish_cleanup(uuid,uuid,text)",
    "platform.files_read_manifest(uuid,uuid,uuid)",
)
PRIVATE_FUNCTIONS = (
    "platform.files_plan(uuid,uuid,uuid)",
    "platform.files_manifest_valid(jsonb)",
    "platform.files_upload_json(platform.file_object_uploads)",
    "platform.files_immutable()",
)

MESSAGING_JOB_JSON_0005 = """CREATE FUNCTION platform.messaging_job_json(j platform.messaging_jobs) RETURNS jsonb
      LANGUAGE sql STABLE SET search_path=pg_catalog,pg_temp AS $$ SELECT jsonb_build_object(
      'job_id',j.id,'kind',j.kind,'workspace_id',j.workspace_id,'connection_id',j.connection_id,
      'inbox_id',j.inbox_id,'outbox_id',j.outbox_id,'claim_token',j.claim_token,'lease_until',j.lease_until,
      'correlation_id',j.correlation_id,'attempt_count',j.attempt_count) $$"""

MESSAGING_RESCHEDULE_0005 = """CREATE FUNCTION platform.messaging_reschedule(p_job uuid,p_error text,p_retry boolean) RETURNS jsonb
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
      END $$"""

MESSAGING_PROCESS_INBOX_0005 = """CREATE FUNCTION platform.messaging_process_inbox(p_job uuid,p_claim uuid) RETURNS jsonb
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
      END $$"""


def upgrade() -> None:
    _tables()
    _helpers()
    _fetch()
    _cleanup()
    _read()
    _extend_kernel()
    for relation in ("app.file_objects", "platform.file_object_uploads"):
        op.execute(f"ALTER TABLE {relation} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {relation} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY files_migrator ON {relation} TO asm_migrator USING(true) WITH CHECK(true)"
        )
    op.execute("""CREATE POLICY files_owner_read ON app.file_objects FOR SELECT TO asm_runtime
      USING(workspace_id=(SELECT app.current_messaging_owner_workspace_id()))""")
    op.execute("GRANT SELECT ON app.file_objects TO asm_runtime")
    for function in (*PUBLIC_FUNCTIONS, *PRIVATE_FUNCTIONS):
        op.execute(f"REVOKE ALL ON FUNCTION {function} FROM PUBLIC")
    for function in PUBLIC_FUNCTIONS:
        op.execute(f"GRANT EXECUTE ON FUNCTION {function} TO asm_runtime")
    # Existing messages, including disconnected connections, are never rewritten.
    op.execute("""SELECT platform.files_plan(m.workspace_id,m.id,coalesce(
      (SELECT i.correlation_id FROM platform.inbox_events i
       WHERE i.workspace_id=m.workspace_id AND i.message_id=m.id AND i.status='PROCESSED'
       ORDER BY i.received_at,i.id LIMIT 1),uuidv7()))
      FROM app.messages m WHERE m.direction='INBOUND' AND m.content_type='IMAGE_REFERENCE'""")


def _tables() -> None:
    op.execute("""ALTER TABLE app.messages ADD CONSTRAINT messages_file_source_key
      UNIQUE(workspace_id,id,connection_id,conversation_id,direction,content_type)""")
    op.execute("""CREATE TABLE app.file_objects(
      workspace_id uuid NOT NULL, id uuid NOT NULL DEFAULT uuidv7(),
      message_id uuid NOT NULL, connection_id uuid NOT NULL, conversation_id uuid NOT NULL,
      required_direction text NOT NULL DEFAULT 'INBOUND' CHECK(required_direction='INBOUND'),
      required_content_type text NOT NULL DEFAULT 'IMAGE_REFERENCE' CHECK(required_content_type='IMAGE_REFERENCE'),
      status text NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','READY','FAILED')),
      winner_intent_id uuid,
      winner_state text GENERATED ALWAYS AS(CASE WHEN status='READY' THEN 'WINNER' END) STORED,
      storage_key text, mime_type text, size_bytes bigint, sha256 text, width integer, height integer,
      error_code text CHECK(error_code IS NULL OR error_code IN ('INVALID_INPUT','DEPENDENCY_TIMEOUT','DEPENDENCY_UNAVAILABLE','RETRY_EXHAUSTED')),
      version bigint NOT NULL DEFAULT 1 CHECK(version>0),
      created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK(isfinite(created_at)),
      completed_at timestamptz CHECK(isfinite(completed_at)),
      PRIMARY KEY(workspace_id,id), UNIQUE(workspace_id,message_id), UNIQUE(workspace_id,id,connection_id),
      CONSTRAINT file_objects_message_fkey FOREIGN KEY(workspace_id,message_id,connection_id,conversation_id,required_direction,required_content_type)
        REFERENCES app.messages(workspace_id,id,connection_id,conversation_id,direction,content_type) ON DELETE RESTRICT,
      CHECK((status='PENDING' AND completed_at IS NULL AND error_code IS NULL) OR
            (status='READY' AND completed_at IS NOT NULL AND error_code IS NULL) OR
            (status='FAILED' AND completed_at IS NOT NULL AND error_code IS NOT NULL)),
      CHECK((status='READY' AND winner_intent_id IS NOT NULL AND storage_key IS NOT NULL AND
             mime_type IS NOT NULL AND size_bytes IS NOT NULL AND sha256 IS NOT NULL AND width IS NOT NULL AND height IS NOT NULL) OR
            (status<>'READY' AND winner_intent_id IS NULL AND storage_key IS NULL AND mime_type IS NULL AND
             size_bytes IS NULL AND sha256 IS NULL AND width IS NULL AND height IS NULL)))""")
    op.execute("""ALTER TABLE platform.messaging_jobs
      ADD COLUMN file_id uuid,
      DROP CONSTRAINT messaging_jobs_kind_check, DROP CONSTRAINT messaging_jobs_check,
      ADD CONSTRAINT messaging_jobs_kind_check CHECK(kind IN ('PROCESS_INBOX','SEND_MANUAL_TEXT','FETCH_IMAGE')),
      ADD CONSTRAINT messaging_jobs_check CHECK(
        (kind='PROCESS_INBOX' AND inbox_id IS NOT NULL AND outbox_id IS NULL AND file_id IS NULL) OR
        (kind='SEND_MANUAL_TEXT' AND outbox_id IS NOT NULL AND inbox_id IS NULL AND file_id IS NULL) OR
        (kind='FETCH_IMAGE' AND file_id IS NOT NULL AND inbox_id IS NULL AND outbox_id IS NULL)),
      ADD CONSTRAINT messaging_jobs_file_key UNIQUE(workspace_id,file_id),
      ADD CONSTRAINT messaging_jobs_file_ref_key UNIQUE(workspace_id,id,file_id),
      ADD CONSTRAINT messaging_jobs_file_fkey FOREIGN KEY(workspace_id,file_id,connection_id)
        REFERENCES app.file_objects(workspace_id,id,connection_id) ON DELETE RESTRICT""")
    op.execute("""CREATE TABLE platform.file_object_uploads(
      workspace_id uuid NOT NULL, id uuid NOT NULL DEFAULT uuidv7(), file_id uuid NOT NULL,
      job_id uuid NOT NULL, claim_token uuid NOT NULL,
      storage_key text NOT NULL UNIQUE,
      mime_type text NOT NULL CHECK(mime_type IN ('image/jpeg','image/png','image/webp')),
      size_bytes bigint NOT NULL CHECK(size_bytes BETWEEN 1 AND 10485760),
      sha256 text NOT NULL CHECK(sha256 ~ '^[0-9a-f]{64}$'),
      width integer NOT NULL CHECK(width BETWEEN 1 AND 8192),
      height integer NOT NULL CHECK(height BETWEEN 1 AND 8192),
      status text NOT NULL DEFAULT 'PREPARED' CHECK(status IN ('PREPARED','WINNER','ABANDONED')),
      cleanup_claim_token uuid, cleanup_lease_until timestamptz CHECK(isfinite(cleanup_lease_until)),
      cleanup_attempts integer NOT NULL DEFAULT 0 CHECK(cleanup_attempts BETWEEN 0 AND 20),
      next_check_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK(isfinite(next_check_at)),
      last_checked_at timestamptz CHECK(isfinite(last_checked_at)),
      cleanup_outcome text CHECK(cleanup_outcome IS NULL OR cleanup_outcome IN ('DELETED','DEPENDENCY_TIMEOUT','DEPENDENCY_UNAVAILABLE')),
      version bigint NOT NULL DEFAULT 1 CHECK(version>0),
      created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK(isfinite(created_at)),
      PRIMARY KEY(workspace_id,id), UNIQUE(id), UNIQUE(job_id,claim_token),
      UNIQUE(workspace_id,file_id,id,status,storage_key,mime_type,size_bytes,sha256,width,height),
      FOREIGN KEY(workspace_id,file_id) REFERENCES app.file_objects(workspace_id,id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,job_id,file_id) REFERENCES platform.messaging_jobs(workspace_id,id,file_id) ON DELETE RESTRICT,
      CHECK(width::bigint*height<=20000000),
      CHECK(storage_key='workspaces/'||workspace_id::text||'/files/'||file_id::text||'/attempts/'||id::text),
      CHECK((cleanup_claim_token IS NULL AND cleanup_lease_until IS NULL) OR
            (status='ABANDONED' AND cleanup_claim_token IS NOT NULL AND cleanup_lease_until IS NOT NULL)))""")
    # Deferred NO ACTION only permits ordered TEST deletion of the whole FK graph.
    # The immediate status/key/manifest trigger prevents mutation of a live winner.
    op.execute("""ALTER TABLE app.file_objects ADD CONSTRAINT file_objects_winner_fkey
      FOREIGN KEY(workspace_id,id,winner_intent_id,winner_state,storage_key,mime_type,size_bytes,sha256,width,height)
      REFERENCES platform.file_object_uploads(workspace_id,file_id,id,status,storage_key,mime_type,size_bytes,sha256,width,height)
      DEFERRABLE INITIALLY DEFERRED""")
    op.execute("""CREATE INDEX file_upload_cleanup_due_idx ON platform.file_object_uploads(next_check_at,id)
      WHERE status='ABANDONED'""")


def _helpers() -> None:
    op.execute("""CREATE FUNCTION platform.files_immutable() RETURNS trigger
      LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
      BEGIN
        IF TG_TABLE_NAME='file_objects' THEN
          IF OLD.status IN ('READY','FAILED') AND NEW IS DISTINCT FROM OLD THEN
            RAISE EXCEPTION 'immutable terminal file' USING ERRCODE='23514'; END IF;
        ELSIF OLD.status='WINNER' AND NEW IS DISTINCT FROM OLD OR
              OLD.status='ABANDONED' AND NEW.status<>'ABANDONED' THEN
          RAISE EXCEPTION 'immutable upload disposition' USING ERRCODE='23514';
        END IF;
        RETURN NEW;
      END $$""")
    for relation, fields in (
        (
            "app.file_objects",
            "'workspace_id','id','message_id','connection_id','conversation_id','required_direction','required_content_type','created_at'",
        ),
        (
            "platform.file_object_uploads",
            "'workspace_id','id','file_id','job_id','claim_token','storage_key','mime_type','size_bytes','sha256','width','height','created_at'",
        ),
    ):
        op.execute(
            f"CREATE TRIGGER files_identity BEFORE UPDATE ON {relation} FOR EACH ROW EXECUTE FUNCTION platform.messaging_immutable({fields})"
        )
        op.execute(
            f"CREATE TRIGGER files_terminal BEFORE UPDATE ON {relation} FOR EACH ROW EXECUTE FUNCTION platform.files_immutable()"
        )
    op.execute("""CREATE FUNCTION platform.files_manifest_valid(m jsonb) RETURNS boolean
      LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $$
      BEGIN
        IF m IS NULL OR jsonb_typeof(m)<>'object' OR NOT m ?& ARRAY['mime_type','size_bytes','sha256','width','height'] OR
           m-ARRAY['mime_type','size_bytes','sha256','width','height']<>'{}'::jsonb OR
           m->>'mime_type' NOT IN ('image/jpeg','image/png','image/webp') OR
           jsonb_typeof(m->'mime_type')<>'string' OR jsonb_typeof(m->'sha256')<>'string' OR
           NOT (m->>'sha256' ~ '^[0-9a-f]{64}$') OR
           jsonb_typeof(m->'size_bytes')<>'number' OR jsonb_typeof(m->'width')<>'number' OR jsonb_typeof(m->'height')<>'number' OR
           NOT (m->>'size_bytes' ~ '^[0-9]+$') OR NOT (m->>'width' ~ '^[0-9]+$') OR NOT (m->>'height' ~ '^[0-9]+$') THEN RETURN false; END IF;
        RETURN (m->>'size_bytes')::bigint BETWEEN 1 AND 10485760 AND
               (m->>'width')::bigint BETWEEN 1 AND 8192 AND (m->>'height')::bigint BETWEEN 1 AND 8192 AND
               (m->>'width')::bigint*(m->>'height')::bigint<=20000000;
      EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN RETURN false;
      END $$""")
    op.execute("""CREATE FUNCTION platform.files_upload_json(u platform.file_object_uploads) RETURNS jsonb
      LANGUAGE sql STABLE SET search_path=pg_catalog,pg_temp AS $$ SELECT jsonb_build_object(
      'intent_id',u.id,'job_id',u.job_id,'claim_token',u.claim_token,'workspace_id',u.workspace_id,'file_id',u.file_id,'storage_key',u.storage_key,
      'manifest',jsonb_build_object('mime_type',u.mime_type,'size_bytes',u.size_bytes,'sha256',u.sha256,'width',u.width,'height',u.height)) $$""")
    op.execute("""CREATE FUNCTION platform.files_plan(p_workspace uuid,p_message uuid,p_correlation uuid) RETURNS void
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
      END $$""")


def _fetch() -> None:
    op.execute("""CREATE FUNCTION platform.files_begin_fetch(p_job uuid,p_claim uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE j platform.messaging_jobs%ROWTYPE; result jsonb;
      BEGIN
        j:=platform.messaging_guard(p_job,p_claim);
        IF j.kind<>'FETCH_IMAGE' THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        SELECT jsonb_build_object('job_id',j.id,'claim_token',j.claim_token,'workspace_id',j.workspace_id,'connection_id',j.connection_id,
          'file_id',f.id,'message_id',m.id,'conversation_id',m.conversation_id,'provider',c.provider,'bot_identity',c.bot_identity,
          'external_connection_id',c.external_connection_id,'image_file_id',m.image_file_id)
        INTO result FROM app.file_objects f
        JOIN app.messages m ON (m.workspace_id,m.id,m.connection_id,m.conversation_id)=(f.workspace_id,f.message_id,f.connection_id,f.conversation_id)
        JOIN app.channel_connections c ON (c.workspace_id,c.id)=(m.workspace_id,m.connection_id)
        WHERE f.workspace_id=j.workspace_id AND f.id=j.file_id AND f.connection_id=j.connection_id AND f.status='PENDING'
          AND m.direction='INBOUND' AND m.content_type='IMAGE_REFERENCE';
        IF result IS NULL THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
        RETURN result;
      END $$""")
    op.execute("""CREATE FUNCTION platform.files_prepare_upload(p_job uuid,p_claim uuid,p_manifest jsonb) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE j platform.messaging_jobs%ROWTYPE; f app.file_objects%ROWTYPE; u platform.file_object_uploads%ROWTYPE; identifier uuid;
      BEGIN
        j:=platform.messaging_guard(p_job,p_claim);
        IF j.kind<>'FETCH_IMAGE' OR platform.files_manifest_valid(p_manifest) IS NOT TRUE THEN
          RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        SELECT * INTO STRICT f FROM app.file_objects WHERE workspace_id=j.workspace_id AND id=j.file_id FOR UPDATE;
        IF f.status<>'PENDING' THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
        SELECT * INTO u FROM platform.file_object_uploads WHERE job_id=j.id AND claim_token=p_claim FOR UPDATE;
        IF FOUND THEN
          IF u.status<>'PREPARED' OR platform.files_upload_json(u)->'manifest'<>p_manifest THEN
            RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
          RETURN platform.files_upload_json(u);
        END IF;
        identifier:=uuidv7();
        INSERT INTO platform.file_object_uploads(workspace_id,id,file_id,job_id,claim_token,storage_key,mime_type,size_bytes,sha256,width,height)
        VALUES(j.workspace_id,identifier,f.id,j.id,p_claim,'workspaces/'||j.workspace_id::text||'/files/'||f.id::text||'/attempts/'||identifier::text,
          p_manifest->>'mime_type',(p_manifest->>'size_bytes')::bigint,p_manifest->>'sha256',(p_manifest->>'width')::integer,(p_manifest->>'height')::integer)
        RETURNING * INTO u;
        RETURN platform.files_upload_json(u);
      END $$""")
    op.execute("""CREATE FUNCTION platform.files_finish_fetch(p_job uuid,p_claim uuid,p_intent uuid) RETURNS jsonb
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
      END $$""")


def _cleanup() -> None:
    op.execute("""CREATE FUNCTION platform.files_claim_cleanup(p_limit integer) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE u platform.file_object_uploads%ROWTYPE; results jsonb:='[]'::jsonb;
      BEGIN
        IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 100 OR coalesce(current_setting('asm.actor_kind',true),'')<>'' THEN
          RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        FOR u IN SELECT * FROM platform.file_object_uploads WHERE status='ABANDONED' AND next_check_at<=clock_timestamp() AND
          (cleanup_lease_until IS NULL OR cleanup_lease_until<=clock_timestamp()) ORDER BY next_check_at,id FOR UPDATE SKIP LOCKED LIMIT p_limit LOOP
          UPDATE platform.file_object_uploads SET cleanup_claim_token=gen_random_uuid(),cleanup_lease_until=clock_timestamp()+interval '30 seconds',
            cleanup_attempts=least(20,cleanup_attempts+1),version=version+1 WHERE id=u.id RETURNING * INTO u;
          results:=results||jsonb_build_array(jsonb_build_object('intent_id',u.id,'claim_token',u.cleanup_claim_token,
            'workspace_id',u.workspace_id,'file_id',u.file_id,'storage_key',u.storage_key,'lease_until',u.cleanup_lease_until));
        END LOOP;
        RETURN results;
      END $$""")
    op.execute("""CREATE FUNCTION platform.files_finish_cleanup(p_intent uuid,p_claim uuid,p_error text) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE u platform.file_object_uploads%ROWTYPE;
      BEGIN
        IF coalesce(current_setting('asm.actor_kind',true),'')<>'' OR
           (p_error IS NOT NULL AND p_error NOT IN ('DEPENDENCY_TIMEOUT','DEPENDENCY_UNAVAILABLE')) THEN
          RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        SELECT * INTO u FROM platform.file_object_uploads WHERE id=p_intent FOR UPDATE;
        IF NOT FOUND OR u.status<>'ABANDONED' OR u.cleanup_claim_token IS DISTINCT FROM p_claim OR
           u.cleanup_claim_token IS NULL OR u.cleanup_lease_until<=clock_timestamp() OR
           EXISTS(SELECT 1 FROM app.file_objects WHERE workspace_id=u.workspace_id AND winner_intent_id=u.id) THEN
          RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
        UPDATE platform.file_object_uploads SET cleanup_claim_token=NULL,cleanup_lease_until=NULL,last_checked_at=clock_timestamp(),
          cleanup_outcome=coalesce(p_error,'DELETED'),cleanup_attempts=CASE WHEN p_error IS NULL THEN 0 ELSE cleanup_attempts END,
          next_check_at=clock_timestamp()+CASE WHEN p_error IS NULL THEN interval '1 hour'
            ELSE make_interval(secs=>least(3600.0,power(2.0,least(12,u.cleanup_attempts)))) END,
          version=version+1 WHERE id=u.id RETURNING * INTO u;
        RETURN jsonb_build_object('code',CASE WHEN p_error IS NULL THEN 'CHECKED' ELSE 'RETRY_SCHEDULED' END,
          'intent_id',u.id,'next_check_at',u.next_check_at);
      END $$""")


def _read() -> None:
    op.execute("""CREATE FUNCTION platform.files_read_manifest(p_conversation uuid,p_message uuid,p_file uuid) RETURNS jsonb
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
      END $$""")


def _extend_kernel() -> None:
    op.execute(
        MESSAGING_JOB_JSON_0005.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1).replace(
            "'inbox_id',j.inbox_id,'outbox_id',j.outbox_id,",
            "'inbox_id',j.inbox_id,'outbox_id',j.outbox_id,'file_id',j.file_id,",
        )
    )
    op.execute(
        MESSAGING_PROCESS_INBOX_0005.replace(
            "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1
        ).replace(
            "        PERFORM platform.messaging_guard(p_job,p_claim);",
            """        IF state='PROCESSED' AND msg.content_type='IMAGE_REFERENCE' THEN
          PERFORM platform.files_plan(j.workspace_id,msg.id,j.correlation_id);
        END IF;
        PERFORM platform.messaging_guard(p_job,p_claim);""",
        )
    )
    op.execute(
        MESSAGING_RESCHEDULE_0005.replace(
            "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1
        ).replace(
            "        IF j.kind='PROCESS_INBOX' AND NOT retry THEN",
            """        IF j.kind='FETCH_IMAGE' THEN
          -- A winner is terminal; ordinary retry admission can never reach it.
          UPDATE platform.file_object_uploads SET status='ABANDONED',next_check_at=clock_timestamp(),version=version+1
            WHERE workspace_id=j.workspace_id AND file_id=j.file_id AND status='PREPARED';
          IF NOT retry THEN
            UPDATE app.file_objects SET status='FAILED',error_code=final_error,completed_at=clock_timestamp(),version=version+1
              WHERE workspace_id=j.workspace_id AND id=j.file_id AND status='PENDING';
          END IF;
        ELSIF j.kind='PROCESS_INBOX' AND NOT retry THEN""",
        )
    )


def downgrade() -> None:
    # Only file metadata is removed. Disposable bucket cleanup is test infrastructure.
    for name in PUBLIC_FUNCTIONS:
        op.execute(f"DROP FUNCTION {name}")
    for original in (
        MESSAGING_PROCESS_INBOX_0005,
        MESSAGING_RESCHEDULE_0005,
        MESSAGING_JOB_JSON_0005,
    ):
        op.execute(original.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1))
    op.execute("DROP FUNCTION platform.files_plan(uuid,uuid,uuid)")
    op.execute("DROP FUNCTION platform.files_upload_json(platform.file_object_uploads)")
    op.execute("DROP FUNCTION platform.files_manifest_valid(jsonb)")
    op.execute("ALTER TABLE app.file_objects DROP CONSTRAINT file_objects_winner_fkey")
    op.execute("DROP TABLE platform.file_object_uploads")
    op.execute("DELETE FROM platform.messaging_jobs WHERE kind='FETCH_IMAGE'")
    op.execute("""ALTER TABLE platform.messaging_jobs DROP CONSTRAINT messaging_jobs_kind_check,
      DROP CONSTRAINT messaging_jobs_check, DROP COLUMN file_id,
      ADD CONSTRAINT messaging_jobs_kind_check CHECK(kind IN ('PROCESS_INBOX','SEND_MANUAL_TEXT')),
      ADD CONSTRAINT messaging_jobs_check CHECK((kind='PROCESS_INBOX' AND inbox_id IS NOT NULL AND outbox_id IS NULL) OR
        (kind='SEND_MANUAL_TEXT' AND outbox_id IS NOT NULL AND inbox_id IS NULL))""")
    op.execute("DROP TABLE app.file_objects")
    op.execute("DROP FUNCTION platform.files_immutable()")
    op.execute("ALTER TABLE app.messages DROP CONSTRAINT messages_file_source_key")
