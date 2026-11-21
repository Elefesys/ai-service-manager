"""Immutable client quotes and guarded delivery through the durable text Outbox."""

from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None

TABLES = {
    "app.quotes": r"""CREATE TABLE app.quotes (
      workspace_id uuid NOT NULL,
      id uuid NOT NULL,
      business_id uuid NOT NULL,
      conversation_id uuid NOT NULL,
      client_id uuid NOT NULL,
      request_id uuid NOT NULL,
      request_revision bigint NOT NULL CHECK(request_revision>0),
      version bigint NOT NULL CHECK(version>0),
      code text NOT NULL CHECK(code ~ '^Q-[0-9A-F]{10}$'),
      material jsonb NOT NULL CHECK(jsonb_typeof(material)='object' AND octet_length(material::text)<=16384),
      basis_sha256 text NOT NULL CHECK(basis_sha256 ~ '^[0-9a-f]{64}$'),
      terms_sha256 text NOT NULL CHECK(terms_sha256 ~ '^[0-9a-f]{64}$'),
      text text NOT NULL CHECK(char_length(text) BETWEEN 1 AND 4096 AND octet_length(text)<=16384),
      release_id uuid NOT NULL,
      prepared_by uuid NOT NULL,
      membership_version bigint NOT NULL CHECK(membership_version>0),
      account_version bigint NOT NULL CHECK(account_version>0),
      created_at timestamptz NOT NULL CHECK(isfinite(created_at)),
      expires_at timestamptz NOT NULL CHECK(isfinite(expires_at) AND expires_at>created_at
        AND expires_at-created_at<=interval '24 hours'),
      PRIMARY KEY(workspace_id,id),
      UNIQUE (workspace_id,request_id,version),
      UNIQUE (workspace_id,request_id,basis_sha256),
      UNIQUE (workspace_id,conversation_id,code),
      FOREIGN KEY(workspace_id,request_id) REFERENCES app.service_requests(workspace_id,id),
      FOREIGN KEY(workspace_id,conversation_id,client_id)
        REFERENCES app.conversations(workspace_id,id,client_id),
      FOREIGN KEY(workspace_id,business_id,release_id)
        REFERENCES platform.business_configuration_releases(workspace_id,business_id,id),
      FOREIGN KEY(workspace_id,prepared_by)
        REFERENCES platform.workspace_memberships(workspace_id,user_account_id)
    )""",
    "platform.quote_delivery_intents": r"""CREATE TABLE platform.quote_delivery_intents (
      workspace_id uuid NOT NULL,
      quote_id uuid NOT NULL,
      connection_id uuid NOT NULL,
      control_generation bigint NOT NULL CHECK(control_generation>0),
      message_id uuid,
      outbox_id uuid,
      send_job_id uuid,
      hold_reason text CHECK(hold_reason ~ '^[A-Z_]{1,60}$'),
      PRIMARY KEY(workspace_id,quote_id),
      UNIQUE (workspace_id,message_id),
      UNIQUE (workspace_id,outbox_id),
      UNIQUE (send_job_id),
      FOREIGN KEY(workspace_id,quote_id) REFERENCES app.quotes(workspace_id,id),
      FOREIGN KEY(workspace_id,connection_id) REFERENCES app.channel_connections(workspace_id,id),
      FOREIGN KEY(workspace_id,message_id,connection_id)
        REFERENCES app.messages(workspace_id,id,connection_id) DEFERRABLE INITIALLY DEFERRED,
      FOREIGN KEY(workspace_id,outbox_id,message_id)
        REFERENCES app.outbox_events(workspace_id,id,message_id) DEFERRABLE INITIALLY DEFERRED,
      FOREIGN KEY(workspace_id,send_job_id)
        REFERENCES platform.messaging_jobs(workspace_id,id) DEFERRABLE INITIALLY DEFERRED,
      CHECK ((message_id IS NULL)=(outbox_id IS NULL) AND (outbox_id IS NULL)=(send_job_id IS NULL))
    )""",
}

FUNCTIONS = {
    "platform.quote_timestamp(timestamptz)": r"""CREATE FUNCTION platform.quote_timestamp(value timestamptz)
    RETURNS text LANGUAGE sql STABLE SET search_path=pg_catalog,pg_temp AS $$
      SELECT to_char(value AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"') $$""",
    "platform.quote_hash(jsonb)": r"""CREATE FUNCTION platform.quote_hash(value jsonb)
    RETURNS text LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $$
      SELECT encode(sha256(convert_to(value::text,'UTF8')),'hex') $$""",
    "platform.quote_code(uuid)": r"""CREATE FUNCTION platform.quote_code(quote_id uuid)
    RETURNS text LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $$
      SELECT 'Q-'||upper(substr(encode(sha256(uuid_send(quote_id)),'hex'),1,10)) $$""",
    "platform.quote_basis(app.service_requests,timestamptz)": r"""CREATE FUNCTION platform.quote_basis(
      d app.service_requests,moment timestamptz
    ) RETURNS jsonb LANGUAGE plpgsql STABLE SET search_path=pg_catalog,pg_temp AS $$
    DECLARE b jsonb; a app.approval_requests%ROWTYPE; r app.owner_decisions%ROWTYPE;
      amount bigint; price_range jsonb; minutes integer; price_reference uuid; duration_reference uuid;
      price_outcome text; mode text; conditions jsonb;
    BEGIN
      b:=platform.approval_basis(d);
      IF d.state<>'DRAFT' OR b IS NULL THEN RETURN '{}'::jsonb; END IF;
      IF b->'intent_current' IS DISTINCT FROM 'true'::jsonb
        OR b->'unavailable_fields' IS DISTINCT FROM '[]'::jsonb
        OR b->'complex_work'->'source_current'='false'::jsonb
        THEN RETURN jsonb_build_object('reason','STALE'); END IF;

      amount:=(b->>'amount_minor')::bigint;
      price_range:=nullif(b->'price_range','null'::jsonb);
      minutes:=(b->>'occupied_minutes')::integer;
      price_reference:=(b->>'price_calculation_id')::uuid;
      duration_reference:=(b->>'assessment_id')::uuid;
      IF NOT ((amount IS NOT NULL OR price_range IS NOT NULL) AND minutes IS NOT NULL
          AND b->'can_approve'='true'::jsonb) THEN
        SELECT p.* INTO a FROM app.approval_requests p
          WHERE (p.workspace_id,p.business_id,p.conversation_id,p.client_id,p.request_id,p.request_revision)
            =(d.workspace_id,d.business_id,d.conversation_id,d.client_id,d.id,d.revision)
            AND p.retired_at IS NULL AND p.action='PREPARE_QUOTE';
        IF a.id IS NOT NULL AND platform.approval_validity(a,d,moment)='CURRENT' THEN
          SELECT o.* INTO r FROM app.owner_decisions o
            WHERE (o.workspace_id,o.approval_id,o.actor_user_account_id)
              =(a.workspace_id,a.id,a.assignee_user_account_id);
        END IF;
        CASE r.operation
          WHEN 'CLARIFY' THEN RETURN jsonb_build_object('reason','APPROVAL_CLARIFICATION');
          WHEN 'DECLINE' THEN RETURN jsonb_build_object('reason','APPROVAL_DECLINED');
          WHEN 'APPROVE' THEN
            amount:=r.amount_minor;
            price_range:=CASE WHEN r.lower_minor IS NOT NULL THEN
              jsonb_build_object('authority','PROVISIONAL','lower_minor',r.lower_minor,'upper_minor',r.upper_minor) END;
            minutes:=r.occupied_minutes;
            price_reference:=r.price_reference_id;
            duration_reference:=r.duration_reference_id;
          ELSE
            mode:=b->'deposit'->>'mode';
            SELECT p.outcome INTO price_outcome FROM app.price_calculations p
              WHERE (p.workspace_id,p.id)=(d.workspace_id,price_reference);
            IF price_outcome='RANGE' AND mode IN ('PERCENT_DEPOSIT','FULL_PREPAYMENT') THEN
              RETURN jsonb_build_object('reason','EXACT_PRICE_REQUIRED');
            ELSIF mode='FIXED_DEPOSIT' AND (
                b->'deposit'->>'amount_minor' IS NULL
                OR (amount IS NOT NULL AND (b->'deposit'->>'amount_minor')::bigint>amount)
                OR (price_outcome='RANGE' AND price_range IS NULL)
              ) THEN RETURN jsonb_build_object('reason','DEPOSIT_TERMS_UNCLEAR');
            END IF;
            RETURN jsonb_build_object('reason','AWAITING_TERMS');
        END CASE;
      END IF;
      SELECT coalesce(jsonb_agg(rule.value ORDER BY rule.ordinal),'[]'::jsonb) INTO conditions
        FROM jsonb_array_elements(platform.service_assessment_material(d)->'rules')
          WITH ORDINALITY rule(value,ordinal)
        WHERE rule.value->>'kind' IN ('MIN_AGE','MAX_SIZE_MM');
      RETURN jsonb_build_object('material',jsonb_build_object(
        'workspace_id',d.workspace_id,'business_id',d.business_id,'conversation_id',d.conversation_id,
        'client_id',d.client_id,'request_id',d.id,'request_revision',d.revision::text,
        'service_id',d.service_id,'service_name',b->'service_name','facts',b->'facts',
        'intent_source',b->'intent_source','complex_work',b->'complex_work',
        'release_id',b->'release_id','activation_version',b->'activation_version',
        'deposit_terms_version',b->'release_id','deposit',b->'deposit','conditions',conditions,
        'currency','RUB','amount_minor',amount,'price_range',price_range,'occupied_minutes',minutes,
        'assessment_id',b->'assessment_id','assessment_reason',b->'assessment_reason',
        'price_calculation_id',b->'price_calculation_id','price_reason',b->'price_reason',
        'approval_id',CASE WHEN r.id IS NOT NULL THEN a.id END,'decision_id',r.id,
        'price_reference_id',price_reference,'duration_reference_id',duration_reference));
    END $$""",
    "platform.quote_expiry(jsonb)": r"""CREATE FUNCTION platform.quote_expiry(material jsonb)
    RETURNS timestamptz LANGUAGE sql STABLE SET search_path=pg_catalog,pg_temp AS $$
      SELECT least(transaction_timestamp()+interval '24 hours',(
        SELECT a.expires_at FROM app.approval_requests a
          WHERE (a.workspace_id,a.id)=((material->>'workspace_id')::uuid,(material->>'approval_id')::uuid)
      )) $$""",
    "platform.quote_block(app.quotes,app.conversations,bigint)": r"""CREATE FUNCTION platform.quote_block(
      q app.quotes,c app.conversations,generation bigint
    ) RETURNS text LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
    DECLARE conn app.channel_connections%ROWTYPE; d app.service_requests%ROWTYPE; a app.approval_requests%ROWTYPE;
      native_reason text; validity text;
    BEGIN
      IF NOT (current_database() IN ('asm_local','asm_test')) THEN RETURN 'CHANNEL_UNAVAILABLE'; END IF;
      IF q.expires_at<=clock_timestamp() THEN RETURN 'EXPIRED'; END IF;
      IF (c.workspace_id,c.business_id,c.id,c.client_id) IS DISTINCT FROM
        (q.workspace_id,q.business_id,q.conversation_id,q.client_id) THEN RETURN 'STALE'; END IF;
      IF NOT EXISTS(SELECT 1 FROM platform.workspaces w JOIN platform.workspace_memberships m ON m.workspace_id=w.id
          JOIN platform.user_accounts u ON u.id=m.user_account_id
          WHERE (w.id,m.user_account_id,m.version,u.version)
            =(q.workspace_id,q.prepared_by,q.membership_version,q.account_version)
            AND w.status='ACTIVE' AND m.role='OWNER' AND m.status='ACTIVE' AND u.status='ACTIVE')
        THEN RETURN 'REVOKED'; END IF;
      SELECT r.* INTO d FROM app.service_requests r
        WHERE (r.workspace_id,r.id,r.business_id,r.conversation_id,r.client_id,r.revision)
          =(q.workspace_id,q.request_id,q.business_id,q.conversation_id,q.client_id,q.request_revision);
      IF NOT FOUND THEN RETURN 'STALE'; END IF;
      IF q.material->>'approval_id' IS NOT NULL THEN
        SELECT p.* INTO a FROM app.approval_requests p
          WHERE (p.workspace_id,p.id)=(q.workspace_id,(q.material->>'approval_id')::uuid);
        IF NOT FOUND THEN RETURN 'STALE'; END IF;
        validity:=platform.approval_validity(a,d,clock_timestamp());
        IF validity<>'CURRENT' THEN RETURN validity; END IF;
      END IF;
      IF q.material IS DISTINCT FROM platform.quote_basis(d,clock_timestamp())->'material'
        THEN RETURN 'STALE'; END IF;
      IF c.control_mode='HUMAN' THEN RETURN 'HUMAN_CONTROL'; END IF;
      IF c.control_generation IS DISTINCT FROM generation THEN RETURN 'CONTROL_CHANGED'; END IF;
      IF NOT EXISTS(SELECT 1 FROM platform.conversation_control_receipts r
          WHERE (r.workspace_id,r.conversation_id,r.client_id,r.accepted_generation,r.activation_fence_seq)
            =(c.workspace_id,c.id,c.client_id,c.control_generation,c.activation_fence_seq)
            AND r.operation='RESUME' AND r.accepted_mode='AI')
        THEN RETURN 'ACTIVATION_REQUIRED'; END IF;
      native_reason:=platform.human_context_admission(c.workspace_id,c.id,NULL);
      IF native_reason IS DISTINCT FROM 'CURRENT'
        THEN RETURN coalesce(native_reason,'CONTEXT_CONFIRMATION_REQUIRED'); END IF;
      SELECT k.* INTO conn FROM app.channel_connections k
        JOIN app.businesses b ON (b.workspace_id,b.id)=(k.workspace_id,k.business_id)
        WHERE (k.workspace_id,k.id,k.business_id)=(c.workspace_id,c.connection_id,c.business_id)
          AND k.status='ACTIVE' AND b.status='ACTIVE';
      IF NOT FOUND OR NOT (conn.provider='CONTROLLED' OR (
          conn.provider='TELEGRAM' AND current_database()='asm_test'
        )) THEN RETURN 'CHANNEL_UNAVAILABLE'; END IF;
      IF conn.provider='TELEGRAM' THEN
        IF c.last_client_inbound_at IS NULL OR clock_timestamp()>=c.last_client_inbound_at+interval '24 hours'
          THEN RETURN 'CHANNEL_WINDOW_CLOSED'; END IF;
        -- A recent cached timestamp cannot be required before queuing an async
        -- answer. Require the last locally observed rights on the same connection
        -- generation here; begin also requires a fresh, same-transaction observation.
        IF NOT EXISTS(SELECT 1 FROM platform.telegram_connection_state s
            WHERE (s.workspace_id,s.connection_id)=(c.workspace_id,c.connection_id)
              AND s.observed_generation=s.generation AND s.error_code IS NULL
              AND s.is_enabled IS TRUE AND s.can_reply IS TRUE)
          THEN RETURN 'CHANNEL_RIGHTS_UNAVAILABLE'; END IF;
      END IF;
      BEGIN
        IF platform.messaging_manual_send_allowed(c.workspace_id) IS NOT TRUE
          THEN RETURN 'CHANNEL_UNAVAILABLE'; END IF;
      EXCEPTION WHEN SQLSTATE 'P2301' THEN RETURN 'CHANNEL_UNAVAILABLE'; END;
      RETURN NULL;
    END $$""",
    "platform.quote_view(app.quotes,app.conversations)": r"""CREATE FUNCTION platform.quote_view(
      q app.quotes,c app.conversations
    ) RETURNS jsonb LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
    DECLARE i platform.quote_delivery_intents%ROWTYPE; box app.outbox_events%ROWTYPE;
      status text; reason text;
    BEGIN
      SELECT * INTO STRICT i FROM platform.quote_delivery_intents
        WHERE (workspace_id,quote_id)=(q.workspace_id,q.id);
      SELECT * INTO box FROM app.outbox_events WHERE (workspace_id,id)=(i.workspace_id,i.outbox_id);
      IF box.status='SENT' THEN status:='SENT';
      ELSIF box.status='UNKNOWN' THEN status:='UNKNOWN'; reason:=box.error_code;
      ELSIF box.status='FAILED' THEN
        status:=CASE WHEN i.hold_reason IS NULL THEN 'FAILED' ELSE 'HELD' END;
        reason:=coalesce(i.hold_reason,box.error_code);
      ELSIF box.status='DISPATCHING' THEN status:='QUEUED';
      ELSE
        reason:=coalesce(platform.quote_block(q,c,i.control_generation),i.hold_reason);
        status:=CASE WHEN reason IS NOT NULL THEN 'HELD' WHEN box.id IS NULL THEN 'PREPARED' ELSE 'QUEUED' END;
      END IF;
      RETURN jsonb_build_object('status',status,'reason',reason,'quote',jsonb_build_object(
        'quote_id',q.id,'code',q.code,'version',q.version::text,'material',q.material,'text',q.text,
        'terms_sha256',q.terms_sha256,'created_at',platform.quote_timestamp(q.created_at),
        'expires_at',platform.quote_timestamp(q.expires_at)));
    END $$""",
    "platform.quote_queue(app.quotes,app.conversations,uuid)": r"""CREATE FUNCTION platform.quote_queue(
      q app.quotes,c app.conversations,correlation uuid
    ) RETURNS void LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
    DECLARE message uuid:=uuidv7(); box uuid:=uuidv7(); job uuid:=uuidv7();
    BEGIN
      -- Bind the intent before inserting the planned message. The links are
      -- checked at commit, but the material trigger can identify it immediately.
      UPDATE platform.quote_delivery_intents
        SET control_generation=c.control_generation,hold_reason=NULL,message_id=message,outbox_id=box,send_job_id=job
        WHERE (workspace_id,quote_id)=(q.workspace_id,q.id) AND send_job_id IS NULL;
      IF NOT FOUND THEN RAISE EXCEPTION 'QUOTE_DELIVERY_ALREADY_QUEUED' USING ERRCODE='23514'; END IF;
      INSERT INTO app.messages(workspace_id,id,conversation_id,connection_id,provider_chat_id,direction,content_type,text,occurred_at)
        VALUES(q.workspace_id,message,c.id,c.connection_id,c.provider_chat_id,'OUTBOUND','TEXT',q.text,clock_timestamp());
      INSERT INTO app.outbox_events(workspace_id,id,connection_id,message_id,kind)
        VALUES(q.workspace_id,box,c.connection_id,message,'SEND_QUOTE_TEXT');
      INSERT INTO platform.messaging_jobs(workspace_id,id,connection_id,kind,outbox_id,correlation_id)
        VALUES(q.workspace_id,job,c.connection_id,'SEND_QUOTE_TEXT',box,correlation);
    END $$""",
    "platform.quote_owner_prepare(uuid,uuid,uuid)": r"""CREATE FUNCTION platform.quote_owner_prepare(
      p_business uuid,p_conversation uuid,p_request uuid
    ) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    DECLARE d app.service_requests%ROWTYPE; q app.quotes%ROWTYPE; current_material jsonb;
      quote_id uuid; expiry timestamptz;
    BEGIN
      d:=platform.service_assessment_scope(p_business,p_conversation,p_request);
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
    "platform.quote_owner_record(uuid,uuid,uuid,jsonb)": r"""CREATE FUNCTION platform.quote_owner_record(
      p_business uuid,p_conversation uuid,p_request uuid,p_payload jsonb
    ) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    DECLARE d app.service_requests%ROWTYPE; c app.conversations%ROWTYPE; q app.quotes%ROWTYPE;
      material jsonb; basis text; text_body text; quote_id uuid; code text; created timestamptz; expiry timestamptz;
      actor uuid:=nullif(current_setting('asm.actor_id',true),'')::uuid;
      correlation uuid:=nullif(current_setting('asm.correlation_id',true),'')::uuid;
      member_version bigint; user_version bigint; next_version bigint; hold_reason text;
    BEGIN
      d:=platform.service_assessment_scope(p_business,p_conversation,p_request);
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
    "platform.quote_owner_read(uuid,uuid,uuid)": r"""CREATE FUNCTION platform.quote_owner_read(
      p_business uuid,p_conversation uuid,p_request uuid
    ) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    DECLARE d app.service_requests%ROWTYPE; c app.conversations%ROWTYPE; q app.quotes%ROWTYPE; reason text;
    BEGIN
      d:=platform.service_assessment_scope(p_business,p_conversation,p_request);
      SELECT * INTO q FROM app.quotes WHERE (workspace_id,request_id)=(d.workspace_id,d.id)
        ORDER BY version DESC LIMIT 1;
      IF FOUND THEN
        SELECT * INTO STRICT c FROM app.conversations WHERE (workspace_id,id)=(d.workspace_id,d.conversation_id);
        RETURN platform.quote_view(q,c);
      END IF;
      reason:=platform.quote_basis(d,clock_timestamp())->>'reason';
      RETURN jsonb_build_object('quote',NULL,'reason',reason,'status',CASE
        WHEN reason IN ('EXACT_PRICE_REQUIRED','DEPOSIT_TERMS_UNCLEAR','APPROVAL_CLARIFICATION')
          THEN 'NEEDS_CLARIFICATION' END);
    END $$""",
    "platform.quote_immutable()": r"""CREATE FUNCTION platform.quote_immutable()
    RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
    BEGIN
      RAISE EXCEPTION 'QUOTE_IMMUTABLE' USING ERRCODE='23514';
    END $$""",
    "platform.quote_dispatch_scope(app.quotes,uuid)": r"""CREATE FUNCTION platform.quote_dispatch_scope(
      q app.quotes,p_connection uuid
    ) RETURNS app.conversations LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
    DECLARE c app.conversations%ROWTYPE;
    BEGIN
      PERFORM platform.messaging_lock_owner(q.workspace_id,q.prepared_by);
      PERFORM 1 FROM app.businesses WHERE (workspace_id,id)=(q.workspace_id,q.business_id) FOR SHARE;
      -- Preserve the owner and AI admission order: configuration, channel, conversation.
      PERFORM pg_advisory_xact_lock(hashtextextended(
        q.workspace_id::text||':'||q.business_id::text||'|CONFIGURATION_V1',2018));
      PERFORM 1 FROM app.channel_connections WHERE (workspace_id,id)=(q.workspace_id,p_connection) FOR SHARE;
      PERFORM platform.messaging_lock_billing_workspace(q.workspace_id);
      -- Telegram lifecycle/ingress obtains connection state before the conversation.
      PERFORM 1 FROM platform.telegram_connection_state
        WHERE (workspace_id,connection_id)=(q.workspace_id,p_connection) FOR NO KEY UPDATE;
      SELECT * INTO STRICT c FROM app.conversations
        WHERE (workspace_id,id)=(q.workspace_id,q.conversation_id) FOR NO KEY UPDATE;
      RETURN c;
    END $$""",
    "platform.quote_requeue(app.quotes,app.conversations,app.outbox_events,platform.messaging_jobs)": r"""CREATE FUNCTION platform.quote_requeue(
      q app.quotes,c app.conversations,box app.outbox_events,j platform.messaging_jobs
    ) RETURNS void LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
    BEGIN
      -- Reuse the same intent, Outbox and Job only when no attempt passed
      -- dispatch admission under the older control generation.
      IF box.attempt_id IS NOT NULL OR box.status NOT IN ('PENDING','FAILED')
        THEN RAISE EXCEPTION 'QUOTE_ALREADY_DISPATCHED' USING ERRCODE='23514'; END IF;
      UPDATE app.outbox_events SET status='PENDING',error_code=NULL,completed_at=NULL,version=version+1
        WHERE (workspace_id,id)=(q.workspace_id,box.id);
      UPDATE platform.messaging_jobs SET status='READY',error_code=NULL,completed_at=NULL,available_at=clock_timestamp(),
        claim_token=NULL,lease_until=NULL,worker_id=NULL,attempt_count=0,first_started_at=NULL,
        telegram_probe_claim=NULL,telegram_probe_generation=NULL,telegram_probe_version=NULL,version=version+1
        WHERE (workspace_id,id)=(q.workspace_id,j.id);
      UPDATE platform.quote_delivery_intents SET hold_reason=NULL,control_generation=c.control_generation
        WHERE (workspace_id,quote_id)=(q.workspace_id,q.id);
    END $$""",
    "platform.quote_resume()": r"""CREATE FUNCTION platform.quote_resume()
    RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
    DECLARE i platform.quote_delivery_intents%ROWTYPE; q app.quotes%ROWTYPE;
      c app.conversations%ROWTYPE; j platform.messaging_jobs%ROWTYPE; box app.outbox_events%ROWTYPE; reason text;
    BEGIN
      SELECT * INTO STRICT c FROM app.conversations
        WHERE (workspace_id,id,client_id)=(NEW.workspace_id,NEW.conversation_id,NEW.client_id);
      -- Resume already owns the conversation. Publishers hold this row but
      -- never wait for a conversation. Worker admission holds the advisory
      -- configuration lock and can wait for Resume without blocking this read.
      PERFORM 1 FROM platform.business_configuration_state
        WHERE (workspace_id,business_id)=(c.workspace_id,c.business_id) FOR SHARE;
      FOR i IN SELECT d.* FROM platform.quote_delivery_intents d
          JOIN app.quotes offer ON (offer.workspace_id,offer.id)=(d.workspace_id,d.quote_id)
          LEFT JOIN app.outbox_events o ON (o.workspace_id,o.id)=(d.workspace_id,d.outbox_id)
          WHERE (offer.workspace_id,offer.conversation_id,offer.client_id)=(c.workspace_id,c.id,c.client_id)
            AND d.control_generation<c.control_generation AND o.attempt_id IS NULL
            AND (o.id IS NULL OR o.status='PENDING' OR (o.status='FAILED' AND d.hold_reason IS NOT NULL))
          ORDER BY offer.id LOOP
        SELECT * INTO STRICT q FROM app.quotes WHERE (workspace_id,id)=(i.workspace_id,i.quote_id);
        PERFORM platform.messaging_lock_owner(q.workspace_id,q.prepared_by);
        reason:=platform.quote_block(q,c,c.control_generation);
        IF i.send_job_id IS NULL THEN
          IF reason IS NULL THEN
            PERFORM platform.quote_queue(q,c,NEW.correlation_id);
          ELSE
            UPDATE platform.quote_delivery_intents SET hold_reason=reason
              WHERE (workspace_id,quote_id)=(q.workspace_id,q.id);
          END IF;
        ELSIF reason IS NULL THEN
          -- Workers lock Job then conversation. A worker holding its Job lock
          -- will observe the new generation and discard its old claim itself.
          SELECT * INTO j FROM platform.messaging_jobs
            WHERE (workspace_id,id)=(i.workspace_id,i.send_job_id) FOR UPDATE SKIP LOCKED;
          IF FOUND THEN
            SELECT * INTO STRICT box FROM app.outbox_events
              WHERE (workspace_id,id)=(i.workspace_id,i.outbox_id) FOR UPDATE;
            IF box.attempt_id IS NULL AND box.status IN ('PENDING','FAILED') THEN
              PERFORM platform.quote_requeue(q,c,box,j);
            END IF;
          END IF;
        END IF;
      END LOOP;
      RETURN NEW;
    END $$""",
    "platform.quote_send_probe(uuid,uuid)": r"""CREATE FUNCTION platform.quote_send_probe(p_job uuid,p_claim uuid)
    RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    DECLARE j platform.messaging_jobs%ROWTYPE; i platform.quote_delivery_intents%ROWTYPE;
      q app.quotes%ROWTYPE; c app.conversations%ROWTYPE; s platform.telegram_connection_state%ROWTYPE;
    BEGIN
      j:=platform.messaging_guard(p_job,p_claim);
      IF j.kind<>'SEND_QUOTE_TEXT' THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
      PERFORM 1 FROM app.outbox_events WHERE (workspace_id,id,kind,status)
        =(j.workspace_id,j.outbox_id,j.kind,'PENDING') FOR UPDATE;
      IF NOT FOUND THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
      SELECT * INTO STRICT i FROM platform.quote_delivery_intents
        WHERE (workspace_id,send_job_id,outbox_id,connection_id)=(j.workspace_id,j.id,j.outbox_id,j.connection_id);
      SELECT * INTO STRICT q FROM app.quotes WHERE (workspace_id,id)=(i.workspace_id,i.quote_id);
      c:=platform.quote_dispatch_scope(q,j.connection_id);
      PERFORM platform.messaging_guard(p_job,p_claim);
      IF c.connection_id<>j.connection_id OR platform.quote_block(q,c,i.control_generation) IS NOT NULL THEN RETURN NULL; END IF;
      SELECT * INTO s FROM platform.telegram_connection_state
        WHERE (workspace_id,connection_id)=(j.workspace_id,j.connection_id);
      IF NOT FOUND THEN RETURN NULL; END IF;
      UPDATE platform.messaging_jobs SET telegram_probe_claim=p_claim,telegram_probe_generation=s.generation,
        telegram_probe_version=s.observation_version WHERE id=j.id;
      RETURN platform.telegram_probe_json(s);
    END $$""",
    "platform.quote_send_begin(uuid,uuid,bigint,bigint,jsonb)": r"""CREATE FUNCTION platform.quote_send_begin(
      p_job uuid,p_claim uuid,p_generation bigint,p_version bigint,p_observation jsonb
    ) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    DECLARE j platform.messaging_jobs%ROWTYPE; i platform.quote_delivery_intents%ROWTYPE;
      q app.quotes%ROWTYPE; c app.conversations%ROWTYPE; conn app.channel_connections%ROWTYPE;
      box app.outbox_events%ROWTYPE; msg app.messages%ROWTYPE; observation jsonb; attempt uuid; reason text;
    BEGIN
      j:=platform.messaging_guard(p_job,p_claim);
      IF j.kind<>'SEND_QUOTE_TEXT' THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
      SELECT * INTO STRICT box FROM app.outbox_events WHERE (workspace_id,id)=(j.workspace_id,j.outbox_id) FOR UPDATE;
      IF (box.kind,box.status) IS DISTINCT FROM (j.kind,'PENDING')
        THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
      SELECT * INTO STRICT i FROM platform.quote_delivery_intents WHERE
        (workspace_id,send_job_id,outbox_id,message_id,connection_id)
          =(j.workspace_id,j.id,box.id,box.message_id,j.connection_id);
      SELECT * INTO STRICT q FROM app.quotes WHERE (workspace_id,id)=(i.workspace_id,i.quote_id);
      c:=platform.quote_dispatch_scope(q,j.connection_id);
      SELECT * INTO STRICT conn FROM app.channel_connections WHERE (workspace_id,id)=(j.workspace_id,j.connection_id);
      PERFORM platform.messaging_guard(p_job,p_claim);
      reason:=CASE WHEN c.connection_id<>j.connection_id THEN 'STALE' ELSE platform.quote_block(q,c,i.control_generation) END;
      IF reason='CONTROL_CHANGED' AND i.control_generation<c.control_generation AND box.attempt_id IS NULL THEN
        reason:=platform.quote_block(q,c,c.control_generation);
        IF reason IS NULL THEN
          PERFORM platform.quote_requeue(q,c,box,j);
          RETURN jsonb_build_object('code','UNAVAILABLE','status','PENDING');
        END IF;
      END IF;
      IF reason IS NULL AND conn.provider='TELEGRAM' THEN
        IF p_observation IS NULL THEN
          reason:='CHANNEL_RIGHTS_UNAVAILABLE';
        ELSE
          IF (j.telegram_probe_claim,j.telegram_probe_generation,j.telegram_probe_version)
              IS DISTINCT FROM (p_claim,p_generation,p_version)
            THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
          observation:=platform.telegram_save_observation(j.workspace_id,j.connection_id,p_generation,p_version,p_observation);
          IF observation->>'code'='UNAVAILABLE' THEN
            RETURN jsonb_build_object('code','UNAVAILABLE','status',
              platform.messaging_reschedule(j.id,'DEPENDENCY_UNAVAILABLE',true)->>'status');
          END IF;
          reason:=platform.quote_block(q,c,i.control_generation);
          IF reason IS NULL AND (observation->>'code'<>'OBSERVED'
              OR platform.telegram_can_send(j.workspace_id,j.connection_id,c.id,true) IS NOT TRUE)
            THEN reason:='CHANNEL_RIGHTS_UNAVAILABLE'; END IF;
        END IF;
      ELSIF reason IS NULL AND (p_generation IS NOT NULL OR p_version IS NOT NULL OR p_observation IS NOT NULL)
        THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
      -- Re-evaluate time-sensitive admission after locks and observation.
      IF reason IS NULL THEN reason:=platform.quote_block(q,c,i.control_generation); END IF;
      PERFORM platform.messaging_guard(p_job,p_claim);
      IF reason IS NOT NULL THEN
        UPDATE platform.quote_delivery_intents SET hold_reason=reason WHERE (workspace_id,quote_id)=(q.workspace_id,q.id);
        PERFORM platform.messaging_reschedule(j.id,'NOT_ALLOWED',false);
        RETURN jsonb_build_object('code','NOT_ALLOWED','status','FAILED');
      END IF;
      SELECT * INTO STRICT msg FROM app.messages WHERE (workspace_id,id)=(j.workspace_id,box.message_id);
      IF (msg.conversation_id,msg.connection_id,msg.provider_chat_id,msg.direction,msg.content_type,msg.text) IS DISTINCT FROM
        (c.id,c.connection_id,c.provider_chat_id,'OUTBOUND','TEXT',q.text)
        THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
      attempt:=gen_random_uuid();
      UPDATE app.outbox_events SET status='DISPATCHING',attempt_id=attempt,error_code=NULL,version=version+1
        WHERE (workspace_id,id)=(j.workspace_id,box.id);
      RETURN jsonb_build_object('code','PERMITTED','job_id',j.id,'claim_token',p_claim,'attempt_id',attempt,
        'workspace_id',j.workspace_id,'connection_id',j.connection_id,'provider',conn.provider,
        'bot_identity',conn.bot_identity,'external_connection_id',conn.external_connection_id,
        'chat_id',msg.provider_chat_id,'text',msg.text,'quote_delivery',true,'quote_id',q.id);
    END $$""",
}

RUNTIME_FUNCTIONS = (
    "platform.quote_owner_prepare(uuid,uuid,uuid)",
    "platform.quote_owner_record(uuid,uuid,uuid,jsonb)",
    "platform.quote_owner_read(uuid,uuid,uuid)",
    "platform.quote_send_probe(uuid,uuid)",
    "platform.quote_send_begin(uuid,uuid,bigint,bigint,jsonb)",
)


def upgrade():
    for table, sql in TABLES.items():
        op.execute(sql)
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY quote_migrator ON {table} TO asm_migrator USING(true) WITH CHECK(true)"
        )
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC,asm_runtime")
    _update_kernel(forward=True)
    for signature, sql in FUNCTIONS.items():
        op.execute(sql)
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC,asm_runtime")
    for signature in RUNTIME_FUNCTIONS:
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO asm_runtime")
    op.execute("""CREATE TRIGGER quote_immutable BEFORE UPDATE OR DELETE ON app.quotes
      FOR EACH ROW EXECUTE FUNCTION platform.quote_immutable()""")
    op.execute("""CREATE TRIGGER quote_on_resume AFTER INSERT ON platform.conversation_control_receipts
      FOR EACH ROW WHEN (NEW.operation='RESUME') EXECUTE FUNCTION platform.quote_resume()""")
    op.execute(PROFILE)
    op.execute("REVOKE ALL ON FUNCTION platform.quote_schema_profile() FROM PUBLIC,asm_runtime")
    for sql in SCHEMA_GATES_0028:
        op.execute(
            sql.replace(
                "platform.owner_decision_schema_profile()", "platform.quote_schema_profile()"
            ).replace("'0028'", "'0029'")
        )


def downgrade():
    op.execute("LOCK TABLE app.quotes,platform.quote_delivery_intents IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM app.quotes)
        THEN RAISE EXCEPTION 'QUOTE_DURABLE_DATA' USING ERRCODE='55000'; END IF;
    END $$""")
    for sql in SCHEMA_GATES_0028:
        op.execute(sql)
    op.execute("DROP FUNCTION platform.quote_schema_profile()")
    op.execute("DROP TRIGGER quote_on_resume ON platform.conversation_control_receipts")
    op.execute("DROP TRIGGER quote_immutable ON app.quotes")
    for signature in reversed(FUNCTIONS):
        op.execute(f"DROP FUNCTION {signature}")
    _update_kernel(forward=False)
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE {table}")


def _update_kernel(forward):
    for (table, constraint), source in KERNEL_CHECKS_0028.items():
        check = (
            source.replace("'SEND_AI_PHOTO'", "'SEND_AI_PHOTO','SEND_QUOTE_TEXT'")
            if forward
            else source
        )
        op.execute(
            f"ALTER TABLE {table} DROP CONSTRAINT {constraint}, ADD CONSTRAINT {constraint} {check}"
        )
    for signature, source in KERNEL_FUNCTIONS_0028.items():
        sql = source.replace("CREATE FUNCTION ", "CREATE OR REPLACE FUNCTION ", 1)
        if forward:
            if signature == "platform.messaging_job_json(platform.messaging_jobs)":
                sql = (
                    sql.removesuffix(" $$")
                    + """ || CASE WHEN j.kind='SEND_QUOTE_TEXT' THEN
                  jsonb_build_object('quote_id',(SELECT i.quote_id FROM platform.quote_delivery_intents i
                    WHERE (i.workspace_id,i.send_job_id)=(j.workspace_id,j.id)))
                  ELSE '{}'::jsonb END $$"""
                )
            elif signature == "platform.turn_material()":
                sql = sql.replace(
                    "IF NEW.direction<>'OUTBOUND' THEN RETURN NEW; END IF;",
                    """-- A prepared quote does not change the visible conversation.
          -- Delivery can update the context and invalidate a pending escalation.
          IF NEW.direction<>'OUTBOUND' OR EXISTS(
            SELECT 1 FROM platform.quote_delivery_intents i WHERE
              (i.workspace_id,i.message_id,i.connection_id)=(NEW.workspace_id,NEW.id,NEW.connection_id)
          ) THEN RETURN NEW; END IF;""",
                ).replace(
                    "SELECT conversation_id INTO STRICT conv FROM app.messages WHERE workspace_id=ws AND id=NEW.message_id;",
                    """IF NEW.kind='SEND_QUOTE_TEXT' AND NEW.status='FAILED' AND NEW.attempt_id IS NULL THEN RETURN NEW; END IF;
          SELECT conversation_id INTO STRICT conv FROM app.messages WHERE workspace_id=ws AND id=NEW.message_id;""",
                )
            else:
                sql = sql.replace("'SEND_AI_PHOTO'", "'SEND_AI_PHOTO','SEND_QUOTE_TEXT'")
        op.execute(sql)


# Exact predecessor kernel and gates.
KERNEL_CHECKS_0028 = {
    (
        "platform.messaging_jobs",
        "messaging_jobs_kind_check",
    ): r"""CHECK(kind IN ('PROCESS_INBOX','SEND_MANUAL_TEXT','SEND_GUARDED_TEXT','SEND_AI_TEXT','SEND_AI_PHOTO','FETCH_IMAGE','PROCESS_TURN','ESCALATION_TIMER'))""",
    (
        "platform.messaging_jobs",
        "messaging_jobs_check",
    ): r"""CHECK(((kind='PROCESS_INBOX' AND inbox_id IS NOT NULL AND outbox_id IS NULL AND file_id IS NULL AND turn_id IS NULL) OR
        (kind IN ('SEND_MANUAL_TEXT','SEND_GUARDED_TEXT','SEND_AI_TEXT','SEND_AI_PHOTO') AND outbox_id IS NOT NULL AND inbox_id IS NULL AND file_id IS NULL AND turn_id IS NULL) OR
        (kind='FETCH_IMAGE' AND file_id IS NOT NULL AND inbox_id IS NULL AND outbox_id IS NULL AND turn_id IS NULL) OR
        (kind='PROCESS_TURN' AND turn_id IS NOT NULL AND inbox_id IS NULL AND outbox_id IS NULL AND file_id IS NULL) OR (kind='ESCALATION_TIMER' AND escalation_id IS NOT NULL AND inbox_id IS NULL AND outbox_id IS NULL AND file_id IS NULL AND turn_id IS NULL)))""",
    ("platform.messaging_jobs", "messaging_jobs_telegram_probe_check"): r"""CHECK (
  (telegram_probe_claim IS NULL AND telegram_probe_generation IS NULL AND telegram_probe_version IS NULL) OR
  ((kind IN ('SEND_MANUAL_TEXT','SEND_AI_TEXT','SEND_AI_PHOTO') OR (kind='PROCESS_TURN' AND step='AI_GENERATE'))
    AND telegram_probe_claim IS NOT NULL AND telegram_probe_generation IS NOT NULL AND telegram_probe_version IS NOT NULL))""",
    (
        "app.outbox_events",
        "outbox_events_kind_check",
    ): r"""CHECK(kind IN ('SEND_MANUAL_TEXT','SEND_GUARDED_TEXT','SEND_AI_TEXT','SEND_AI_PHOTO'))""",
}

KERNEL_FUNCTIONS_0028 = {
    "platform.messaging_job_json(platform.messaging_jobs)": r"""CREATE OR REPLACE FUNCTION platform.messaging_job_json(j platform.messaging_jobs) RETURNS jsonb
      LANGUAGE sql STABLE SET search_path=pg_catalog,pg_temp AS $$ SELECT jsonb_build_object(
      'job_id',j.id,'kind',j.kind,'workspace_id',j.workspace_id,'connection_id',j.connection_id,
      'inbox_id',j.inbox_id,'outbox_id',j.outbox_id,'file_id',j.file_id,'claim_token',j.claim_token,'lease_until',j.lease_until,
      'correlation_id',j.correlation_id,'attempt_count',j.attempt_count) ||
          CASE WHEN j.kind='PROCESS_TURN' THEN jsonb_build_object('turn_id',j.turn_id,'turn_revision',j.turn_revision,'step',j.step) WHEN j.kind='ESCALATION_TIMER' THEN jsonb_build_object('escalation_id',j.escalation_id,'step',j.step) ELSE '{}'::jsonb END $$""",
    "platform.turn_material()": r"""CREATE OR REPLACE FUNCTION platform.turn_material() RETURNS trigger
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
        IF TG_TABLE_NAME='outbox_events' THEN
          IF NEW.status='SENT' THEN
          SELECT correlation_id INTO STRICT corr FROM platform.messaging_jobs WHERE workspace_id=ws AND outbox_id=NEW.id;
          -- Changed binding includes delivery+material in one C UPDATE; no current-XID FK recheck.
          -- Only an already existing target can bind; no new target or foreign Job lock.
          IF platform.material_bind(ws,NEW.message_id,false,corr) IS NOT NULL THEN RETURN NEW; END IF;
          END IF;
        END IF;
        UPDATE app.conversations SET version=version+1 WHERE workspace_id=ws AND id=conv;
        IF TG_TABLE_NAME='file_objects' THEN
          IF platform.message_effective(ws,NEW.message_id)->>'image_availability' NOT IN ('ORIGINAL_READY','ORIGINAL_FAILED') THEN RETURN NEW; END IF;
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
    "platform.messaging_retry(uuid,uuid,text,boolean)": r"""CREATE OR REPLACE FUNCTION platform.messaging_retry(p_job uuid,p_claim uuid,p_error text,p_retry boolean) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE j platform.messaging_jobs%ROWTYPE; state text;
      BEGIN
        j:=platform.messaging_guard(p_job,p_claim);
        IF p_error IS NULL OR p_error NOT IN ('DEPENDENCY_TIMEOUT','DEPENDENCY_UNAVAILABLE','INVALID_INPUT') OR p_retry IS NULL OR (p_retry AND p_error='INVALID_INPUT') THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        IF j.kind IN ('SEND_MANUAL_TEXT','SEND_GUARDED_TEXT','SEND_AI_TEXT','SEND_AI_PHOTO') THEN
          SELECT status INTO state FROM app.outbox_events WHERE workspace_id=j.workspace_id AND id=j.outbox_id FOR UPDATE;
          IF state<>'PENDING' THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
        END IF;
        RETURN platform.messaging_reschedule(p_job,p_error,p_retry);
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
        IF NOT FOUND OR j.kind NOT IN ('SEND_MANUAL_TEXT','SEND_GUARDED_TEXT','SEND_AI_TEXT','SEND_AI_PHOTO') THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
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
        ELSIF j.kind IN ('SEND_MANUAL_TEXT','SEND_GUARDED_TEXT','SEND_AI_TEXT','SEND_AI_PHOTO') THEN
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
        IF j.step='AI_GENERATE' AND EXISTS(SELECT 1 FROM platform.ai_deliveries WHERE job_id=j.id) THEN retry:=false; END IF;
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
        ELSIF j.kind IN ('SEND_MANUAL_TEXT','SEND_GUARDED_TEXT','SEND_AI_TEXT','SEND_AI_PHOTO') THEN
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
          IF j.kind IN ('SEND_MANUAL_TEXT','SEND_GUARDED_TEXT','SEND_AI_TEXT','SEND_AI_PHOTO') THEN SELECT status INTO state FROM app.outbox_events WHERE workspace_id=j.workspace_id AND id=j.outbox_id; END IF;
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
}

SCHEMA_GATES_0028 = (
    r"""CREATE OR REPLACE FUNCTION platform.ai_provider_session(p jsonb,p_enable boolean) RETURNS jsonb
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
    OR (platform.owner_decision_schema_profile()->>'valid')::boolean IS NOT TRUE THEN
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
    r"""CREATE OR REPLACE FUNCTION platform.human_context_policy_command(ws uuid,p_connection uuid,p_operation text,p_key text,
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
          OR jsonb_typeof(p_profile->'schema_revision')<>'string' OR p_profile->>'schema_revision'<>'0028'
          OR jsonb_typeof(p_profile->'profile_sha256')<>'string' OR p_profile->>'profile_sha256' !~ '^[0-9a-f]{64}$'
          OR p_profile->'drain_confirmed' IS DISTINCT FROM 'true'::jsonb THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2601'; END IF;
        SELECT platform.owner_decision_schema_profile() INTO profile;
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
        SELECT platform.owner_decision_schema_profile() INTO profile;
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
)

# Generated from the effective function bodies and the ordered table inventory.
PROFILE = r"""CREATE FUNCTION platform.quote_schema_profile() RETURNS jsonb
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
('platform.ai_delivery_select(platform.messaging_jobs,platform.ai_runs)','9a6a2181bf5c3de115b2414f1e2ffd09fdfef9328908b7241a336d6f87c7216d','plpgsql',true,'v',false),
('platform.ai_knowledge_current(platform.ai_runs)','d98f7f41bb5010bd967004794410eff26d7c0203207104190a0a4909df42de8f','plpgsql',true,'v',false),
('platform.ai_knowledge_immutable()','a5dc3e44d61c74d3ad36a048961eed0ca3df662cbf7da9025a839c5aa0754a1b','plpgsql',true,'v',false),
('platform.ai_knowledge_snapshot(uuid,uuid)','14c077414a0063174421f6f9bd8a240d77b2700c198d22e8f9ec07a0be9f8ff5','plpgsql',true,'v',false),
('platform.ai_knowledge_valid(jsonb,jsonb,uuid,uuid)','c9cfe061cdecded77ee5f40e5a2775908382eba3996b61824636cc7e5eeed51e','plpgsql',true,'i',false),
('platform.ai_provider_command(uuid,uuid,uuid,text,jsonb)','24672f24048580bb314ed845a9d1e4869dee15d519063dedb029e82d0b4e2c60','plpgsql',true,'v',true),
('platform.ai_provider_config_valid(jsonb)','38064b38949e67306db7dbbcbf150dfd6d2b2195ad8aac77267ab1f6939a30af','plpgsql',true,'i',false),
('platform.ai_provider_enqueue(uuid,uuid,uuid)','91e5c0e7e3ae24516d55c68d9cda830fc8d52f15701cce31d7cdb65289583096','plpgsql',true,'v',true),
('platform.ai_provider_guard(uuid,platform.messaging_jobs,jsonb)','4beb6f775cc17a68fbd068c2b69692f2b2e4ef5c2b78753e119bd679f16666c3','plpgsql',true,'v',false),
('platform.ai_provider_schema_profile()','f2b1f7dbdea1f41244094a101d7d4802927a550078ac260e14c7ffb997bd1986','sql',true,'s',false),
('platform.ai_provider_session(jsonb,boolean)','1a757a440c9c04297e28d3cafbe19a2d9510ed26e5389778e9bbb9d3407784d2','plpgsql',true,'v',false),
('platform.ai_reply_rights_commit(uuid,uuid,uuid,bigint,bigint,jsonb,jsonb)','5e977dd4c1fb4a616a7dabce2fd099247646091e2e2c9b577ff00ca3368bf0df','plpgsql',true,'v',true),
('platform.ai_reply_rights_current(uuid,uuid,uuid)','0c38889d00c0cf1415a890273eebd8f593ed40fe166436a5ad434079d1d30fe7','plpgsql',true,'v',false),
('platform.ai_reply_rights_probe(uuid,uuid,uuid)','9ca90da38d173e7294f77cd7dbdd25492f02fe2cd699562c823c42fbfcb3b01d','plpgsql',true,'v',true),
('platform.ai_reply_rights_schema_profile()','6b635b12b8d2e7f0f69500792d7ec3b1c71cd0f85c51e810e3332b910b6189c0','sql',true,'s',false),
('platform.ai_runtime_command(uuid,uuid,text,jsonb)','339608bba7d81f2d27e8b55e006117d8fe77c6be011f72e4a0ce0d4a083551e2','plpgsql',true,'v',true),
('platform.ai_runtime_completion_valid(jsonb)','4675d7ce837be36341cdc60deff5c216786ad7f42441bb4bda43bfe5e0dcfb0d','plpgsql',true,'i',false),
('platform.ai_runtime_config_valid(jsonb)','a6d4e29eada1c608381d528e55cbc8108903d263f74bfbdd450adddff3ed2742','sql',true,'i',false),
('platform.ai_runtime_current(platform.messaging_jobs,jsonb)','c86bbe138ddabb5197dfbe4453e5b3f4f586099ebdfc62e463814198f3973e86','plpgsql',true,'v',false),
('platform.ai_runtime_receipt(platform.ai_runs)','14519c468cdcdbfca3b8f0e5332e1ecb377871b19b8de05b5af27afdc47a1db4','sql',true,'s',false),
('platform.ai_runtime_replay(uuid,uuid,jsonb)','36b9248da5aff70b2fec73a85303716769350732f5cee03deb719a9f6d0a17c3','plpgsql',true,'v',true),
('platform.ai_runtime_result_valid(jsonb)','7f81305118ab1bff57585a409c91b04ff2eb44d24722d74b35ae05379d5e21d1','plpgsql',true,'i',false),
('platform.ai_runtime_view(platform.ai_runs)','ebfb0382fb632ea8ae5b0cc6d2a7976647ee9cbbad89810973d1ec3e15e45298','sql',true,'s',false),
('platform.ai_synthetic_config_valid(jsonb)','20241427cbe5024f6a5876184f29895f28a83191519bf4d99a4e6e6993baf00c','plpgsql',true,'i',false),
('platform.approval_basis(app.service_requests)','5b5eea8bb476bb527727d4b041eeb53f5c8ae3976ff199299f945e5db2f26b6e','plpgsql',false,'s',false),
('platform.approval_owner_decide(uuid,uuid,uuid,uuid,jsonb)','b16c2f8ecd6a1d200f5dff646607bbd6890a55ba63d445c8c9100ee49f612699','plpgsql',true,'v',true),
('platform.approval_owner_list(uuid)','1882ad6ed68216fc6b3d4ed1442949bea2e4aaa71a4bae1c253da365acadfe67','plpgsql',true,'v',true),
('platform.approval_owner_open(uuid,uuid,uuid,text)','6f372c2354e3a52d54107b3c288eda912f9b0ada5265289170bf4c832c85a0f6','plpgsql',true,'v',true),
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
('platform.human_context_policy_command(uuid,uuid,text,text,text,bigint,jsonb,jsonb)','d7ff1d466db06ceaf681137facb22f55977e3c49d5cc0d740a13965600ac68d2','plpgsql',true,'v',false),
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
('platform.intake_apply(platform.ai_runs,jsonb)','2cd34b223afd4cac720ad64d0b103d35c37dac14bea36944da1d84114b6a330f','plpgsql',true,'v',false),
('platform.intake_candidates_valid(jsonb)','8341249f2e0a5b4a546b7685134aec687fb8065624c72acfea2700a13863632e','plpgsql',true,'i',false),
('platform.intake_current(platform.ai_runs)','1d3b0395102b257d83c46ff69dda128436c840b229c71480d4efcfe03e0d9e3f','plpgsql',true,'s',false),
('platform.intake_delivery_guard(platform.ai_runs)','dc64fc2273a9197d65b5c01fc931174a7b91913dc5521f5fb12d4b47918c2e47','plpgsql',true,'v',false),
('platform.intake_delivery_session_lock(uuid,uuid,uuid,numeric)','193b23fc217a3d439d03acaccdd44887d0723e8f94c04429968c8a881ab424b5','plpgsql',true,'v',false),
('platform.intake_escalation_decorate(jsonb)','d4ea1bcf1556f3593c24c2844c248634490272d8ffa3c79bd6cfd0fcb5a75dfe','plpgsql',true,'v',false),
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
('platform.knowledge_runtime_current(platform.ai_runs)','c1c2c16a2c90e8a4d75b37aec8c4695dfcb7a42b56b4df92a206c5445c9f33c8','plpgsql',true,'v',false),
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
('platform.portfolio_delivery_attest(platform.messaging_jobs,platform.ai_runs,jsonb)','829c12122db7f409706acc85eab5bc9f5f1122a5dcda40ef1f15d22a68364abf','plpgsql',true,'v',false),
('platform.portfolio_delivery_begin(uuid,uuid,uuid,bigint,bigint,jsonb,text)','671251ebf476c91f98c5d6c71b3436418e1f3f34394c3a8f80f6f4aa2f7bc0ff','plpgsql',true,'v',true),
('platform.portfolio_delivery_current_valid(jsonb)','0afa2b97c307693bd803ba179c17b973118f80b25dafd60ef62aa3126b03fdca','sql',true,'i',false),
('platform.portfolio_delivery_eligible(platform.ai_runs)','8eb83ee8c1028cec33ac026ec8619e4efb7af8d4ebd777b85d54b37c1fa5bb0a','sql',true,'s',false),
('platform.portfolio_delivery_immutable()','1b26b5780fc46363019a7c5a8b17426a549a556793a3e3158a69433826576512','plpgsql',true,'v',false),
('platform.portfolio_delivery_intent_current(platform.messaging_jobs,platform.ai_deliveries,platform.ai_runs,platform.portfolio_delivery_intents)','d469e850a3c1cad8f2787634f8c87a94606fb55113ea5512c07700a163feb8ae','plpgsql',true,'v',false),
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
('platform.portfolio_query_apply(uuid,uuid,uuid,uuid,uuid,jsonb)','7122c29e686118f85615077e31fb028e0c62c49ece6e130e17a169549b31016e','plpgsql',true,'v',true),
('platform.portfolio_query_reserve(uuid,uuid,uuid,jsonb)','6a09996a8f49197c6fb717335ed560950880b75bc756227b840ff1c18422cca2','plpgsql',true,'v',true),
('platform.portfolio_refs(jsonb)','9b992ad8ecdea455a2303458f421a2c1e171d5f6e38a9fc136f307d1bd6e0624','sql',true,'i',false),
('platform.portfolio_refs_valid(jsonb)','bfb584ddfdabb7407cf68878313e454bd74219a943dc57324555e589132031b5','plpgsql',true,'i',false),
('platform.portfolio_run_query(platform.ai_runs)','d3ebd9e619af66505665438a41577f20a3ccde6b051b0d02be1fdf3ace1d4423','plpgsql',true,'s',false),
('platform.portfolio_runtime_current(platform.ai_runs)','56de471d2925698628801d6ed1ae36a061c3bf3f1cb7d9e23ad6b3f5dce60d20','plpgsql',true,'v',false),
('platform.portfolio_runtime_data(platform.ai_runs)','cce4d3f8a3eb252b2be0432744d69656631cdd8619264276b3d292747c54c70f','plpgsql',true,'s',false),
('platform.portfolio_runtime_read(uuid,uuid,uuid,jsonb)','f81e46fee79022a4022568608b0ea3245f450255454b085ab44e145538be1c64','plpgsql',true,'v',true),
('platform.portfolio_schema_profile()','df2ab97e8fe09ead37d2dd16f70526f4f47073eaed3314686ceb319e7773d06b','sql',true,'s',false),
('platform.portfolio_select(uuid,uuid,jsonb,extensions.vector,text)','39460c29d3c4dcbf5efb4d3f044e8db4bdb89554a5cf3ced30df436b1a57249a','plpgsql',true,'s',false),
('platform.portfolio_session_admit(uuid,uuid,jsonb)','17ec13ddc4c460ce0a79fdd1b0d8884259d683fa049e937bae6fe4136042f09f','plpgsql',true,'v',true),
('platform.portfolio_session_lock(uuid,uuid,uuid,numeric)','386ace56e6fd2a11ce9f83c4685811533f390557b260536b0f203076d5965b97','plpgsql',true,'v',false),
('platform.portfolio_session_usage(uuid,uuid,uuid)','51057dd53b2f15951fcb63b1282d7581ba94217cff81d4271bf4d4d744623a41','sql',true,'s',false),
('platform.portfolio_text_valid(text,integer)','d98c95fcb948cb7f6afad5f26a93440629661e7991f3f8d8055644e95272354d','sql',true,'i',false),
('platform.portfolio_upload_begin(uuid,uuid,uuid,uuid)','1313e4b020befeff7a0b7d3519bf22fdf24026df2ae8f10e8677fda9d37e498e','plpgsql',true,'v',true),
('platform.portfolio_upload_complete(uuid,uuid,jsonb)','684afc3d4e29f69610835373455a2e5613dc6cbba8993290cb6210b7e4152dad','plpgsql',true,'v',true),
('platform.portfolio_upload_prepare(uuid,uuid,uuid,uuid,uuid,jsonb)','eb895fcd29065e34d54b400368d59153bca5fecce3b179df55768642bda878e4','plpgsql',true,'v',true),
('platform.portfolio_upload_recover(uuid,uuid,uuid,uuid)','e1c66eb556121f8e3d895d4bdafcff271936936e1be0fc341245e50c43d93167','plpgsql',true,'v',true),
('platform.portfolio_version_private(platform.portfolio_asset_versions,uuid)','7c8a9f7ba78c0da2b8cc36d876495cd55c947231e2d0b945b9240a2f3d61df91','sql',true,'s',false),
('platform.price_calculate(uuid,uuid,uuid,text)','0fd33eaedfd9c7b773b1dd5182c2957c52d76debb0f9290ae585ebca8637180f','plpgsql',true,'v',true),
('platform.price_calculation_immutable()','bc41eaad85c67d6647badfdb8eacbffb2407a870b95857a810d4777f4f17e313','plpgsql',false,'v',false),
('platform.price_history(uuid,uuid,uuid,uuid)','2079f35617b90cc005abe3886efa309244866782716993434018a7798984eca6','plpgsql',true,'v',true),
('platform.price_material(app.service_requests)','a9b53d2bfd12753994f8a25157a92a7b5981909ff3d1bcf66d024c701c5c4a06','plpgsql',false,'s',false),
('platform.price_result(app.price_calculations,boolean)','6381f7bc947ab584f5e606049f6b5ab2652ad77837ea4db8157fcc272a8cd21e','sql',false,'s',false),
('platform.price_schema_profile()','1c7fff96f1e69fbd1cacc4724f15155d596aef3620d3d363c918c215fd18ab9b','sql',true,'s',false),
('platform.price_size_mm(text)','e0393c004439cedd55091f61509fd1fec009e7ebecc99670067a31b2d48b2525','plpgsql',false,'i',false),
('platform.published_knowledge_schema_profile()','93c1c8615c17619929194606686ebd21b7f99afa7698cfd425bb6b65035137f5','sql',true,'s',false),
('platform.quote_basis(app.service_requests,timestamptz)','823b48c8cb65e2f4200debd4789f48312bdb9b15926814d8739a63901bfed237','plpgsql',false,'s',false),
('platform.quote_block(app.quotes,app.conversations,bigint)','d4354fa2822d200c6a2d51caeb801f3c8f8b257d44a471e4dc4dca6bdcf8f231','plpgsql',false,'v',false),
('platform.quote_code(uuid)','8fc9c15c54ca4746ec129f66313ff1da3deaa3453687e9d7c6b002ff72289e48','sql',false,'i',false),
('platform.quote_dispatch_scope(app.quotes,uuid)','bfa5d26e6cd766e8981db5784cafd184b5c35e8c4c55cb0385424fac6cd15e4e','plpgsql',false,'v',false),
('platform.quote_expiry(jsonb)','f16dfa38d17861e0f5037260c25353a87b4bf3f5dd2efc86ff9cca069c81dde4','sql',false,'s',false),
('platform.quote_hash(jsonb)','39c6235034994a21858476d2b5942dbc916a3c733404d7e4e5c07586ef6ef35d','sql',false,'i',false),
('platform.quote_immutable()','53bcffa39c87ef26910c57488f342bd68c05ecf9cba299054439d32631291bbb','plpgsql',false,'v',false),
('platform.quote_owner_prepare(uuid,uuid,uuid)','b129b4430e92dbc7c339b6167259855b414698faa0fe43425068f93152c28bd7','plpgsql',true,'v',true),
('platform.quote_owner_read(uuid,uuid,uuid)','00c1501378bc5b6c54ee8f28ef0edca22e94a251932ce3ac2599c654a498e519','plpgsql',true,'v',true),
('platform.quote_owner_record(uuid,uuid,uuid,jsonb)','d69250e9330092f57312eade4788eb7d2dd561ba8e5efc1dff3a9ed7fddfdab3','plpgsql',true,'v',true),
('platform.quote_queue(app.quotes,app.conversations,uuid)','63fdf1216fb6aa19de4037ce0423f61f5815858eba26236edfe14f662a1acf18','plpgsql',false,'v',false),
('platform.quote_requeue(app.quotes,app.conversations,app.outbox_events,platform.messaging_jobs)','330e2443c2bffcc8d0af4d1c847234f94a780588c8efebfbbd3b9793cc7fd9f1','plpgsql',false,'v',false),
('platform.quote_resume()','172bf601df5b72d2f286241292b9898240d60dfc70a15317881f68fe36fcb48f','plpgsql',false,'v',false),
('platform.quote_send_begin(uuid,uuid,bigint,bigint,jsonb)','b034f259a4e702c1f2092cb9e5e831ad830b88125048835df8ffbfca2ae12978','plpgsql',true,'v',true),
('platform.quote_send_probe(uuid,uuid)','d301df2b37a96ddbaaffa31ed5a5c9f0098cc989d600252c62049465bdce0c08','plpgsql',true,'v',true),
('platform.quote_timestamp(timestamptz)','2e5b1223a7976432ffbc795a2d2c4c2e6d7770d02529bfd30617d5ad2a06eae5','sql',false,'s',false),
('platform.quote_view(app.quotes,app.conversations)','c3a00a3cf4caa532286fdac808d363718859017e1ff276f9ed3d00487f17fe13','plpgsql',false,'v',false),
('platform.resolve_workspace_membership(uuid,uuid)','8ce9bdd67c17bc83442bea3a5e7a15337a51074e0ea6408855b10542e39ceb39','sql',true,'v',true),
('platform.service_assessment_immutable()','bb7b369ae4c8eff6280b650ddf07efaab07e6a93ef775825115377f9a3156873','plpgsql',false,'v',false),
('platform.service_assessment_material(app.service_requests)','1aa629e9c025608366eb7d01e0d6a3450665b176d1aedcf902d4557709a5c825','plpgsql',true,'s',false),
('platform.service_assessment_prepare(uuid,uuid,uuid,text)','f1093e5b02baef993686df197d29100c6d0a36093a2897c3f204d9da45a81f32','plpgsql',true,'v',true),
('platform.service_assessment_read(uuid,uuid,uuid)','044364ffbd44f3c2b742dfed17186d66cdb5f9b998bad88a1fe04f69a9050f37','plpgsql',true,'v',true),
('platform.service_assessment_record(uuid,uuid,uuid,jsonb)','1dea30e785de3c9ab6218149b9aeb04a0cb81409fdd41d2e6268f1844df0c29d','plpgsql',true,'v',true),
('platform.service_assessment_result(app.service_assessments,boolean)','3497b9c9d3d63bcd3362a523550479c28303c4b1124158e1f608cbeb6a9d3985','sql',false,'s',false),
('platform.service_assessment_schema_profile()','c7c9624fcc55e4ff00a3b4abf7ec8e907f099898ec41a21fc3fbfef5d68493f8','sql',true,'s',false),
('platform.service_assessment_scope(uuid,uuid,uuid)','b72a864f00155d155619709b948da072b15f72902c4c899c9229043ddbffba16','plpgsql',true,'v',false),
('platform.service_request_command(app.conversations,text,text,uuid,jsonb)','0888dee140c0e7f35cf2a95a15709a9f040ce9447ca2f402be1ffa340858623f','plpgsql',true,'v',false),
('platform.service_request_complex_work(app.conversations,uuid,text,jsonb)','9a9db2ad05f6a6001fd822bfff5360ed0843e87f5ab49e40b7559a6fdea023db','plpgsql',true,'s',false),
('platform.service_request_fact_available(app.conversations,uuid,jsonb)','63e601011da084f50e8774622a3355b1d1decc5d25662826596dc327696bf688','sql',true,'s',false),
('platform.service_request_intake(app.conversations,jsonb)','3f61b1943c618871b3448bce6d5a35df1bc11cfe0f2ba622fbe0844e3c6c1365','plpgsql',true,'s',false),
('platform.service_request_owner_create(uuid,uuid,text,jsonb)','881c468683f7024abc34b5a89614aec4c9147c4f2619a4b4c03081f7d95ea691','plpgsql',true,'v',true),
('platform.service_request_owner_list(uuid,uuid)','54c403414b2ca804d89c0dcc5322a50424ffe1a66f361063190752b505ca9434','plpgsql',true,'v',true),
('platform.service_request_owner_read(uuid,uuid,uuid)','4d7a6b09b54341176b12f315c6c08d21c654f891403bb93216070890cf3b6ea3','plpgsql',true,'v',true),
('platform.service_request_owner_revise(uuid,uuid,uuid,text,jsonb)','66e022b02dcf43a07cccd6938bbee76863a2b1a080d03910659f01794e326a7a','plpgsql',true,'v',true),
('platform.service_request_owner_scope(uuid,uuid)','68d56b048f60af95d6cc0280d2219ac18f467cb18403f5e252157533c1e26a8a','plpgsql',true,'v',false),
('platform.service_request_schema_profile()','b6fb012dec5fcc2e74b1ed83ff11a3c2d02ac82cdb819a7062a6d70abdbd95a0','sql',true,'s',false),
('platform.service_request_summary(jsonb,jsonb,text)','69b1c509de00d7e8b7c6efed748390c9f973fade292e4d91b2d5cec2df7e76d4','plpgsql',false,'i',false),
('platform.telegram_begin_send(uuid,uuid,bigint,bigint,jsonb)','c8f15c23837fa40b86451574ee3e04cc4292dd91b2929a891424e0d8acec556d','plpgsql',true,'v',true),
('platform.telegram_can_send(uuid,uuid,uuid,boolean)','b273ad02ca6825bdf6b037173c3be840a615d551283c3e922357bee3f7f16811','plpgsql',true,'v',false),
('platform.telegram_fingerprint(text,jsonb)','449929a9e41d6e4f38d30341fcb7c7a488d55f06169dbaca2c18df461effdc06','plpgsql',false,'i',false),
('platform.telegram_fingerprint_v2(text,jsonb)','4499d0bd8bc0ad010d856d3e20b21847a9cfedfaeced5c14ace118443c2a940f','plpgsql',false,'i',false),
('platform.telegram_ingest(text,jsonb,uuid)','0b4d1cc97c47522e9abde484362aad3cd4967ae9c256e7719d310c09702f7c09','plpgsql',true,'v',true),
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
('app.quotes',ARRAY['workspace_id','id','business_id','conversation_id','client_id','request_id','request_revision','version','code','material','basis_sha256','terms_sha256','text','release_id','prepared_by','membership_version','account_version','created_at','expires_at']::text[]),
('app.service_assessments',ARRAY['workspace_id','id','business_id','request_id','request_revision','service_id','release_id','activation_version','authority_sha256','owner_handoff','duration_policy','rules','evidence','unavailable_fields','outcome','reason','field','rule_id','limit_value','size_mm','occupied_minutes','actor_user_account_id','correlation_id','created_at','complex_work']::text[]),
('app.service_requests',ARRAY['workspace_id','id','business_id','conversation_id','client_id','intent_message_id','intent_source_version','release_id','service_id','service_name','template_revision','state','revision','facts','missing','conflicts','question','created_at','complex_work']::text[]),
('platform.ai_deliveries',ARRAY['workspace_id','job_id','source_job_id','source_claim_hash','connection_id','turn_id','turn_revision','kind','step','run_id','selected_kind','message_id','outbox_id','send_job_id','escalation_id','intent_context_version','created_at','provider_session_id','knowledge_pin','search_pin','portfolio_pin','media_pin']::text[]),
('platform.ai_provider_calls',ARRAY['workspace_id','run_id','sequence','claim_hash','attempt_count','budget','completion','reserved_at','completed_at','portfolio_session_id']::text[]),
('platform.ai_provider_sessions',ARRAY['id','workspace_id','connection_id','conversation_id','client_id','chat_id','bot_identity','data_profile','starts_at','expires_at','max_calls','max_rub','review_sha256','review_checked_at','config','active','created_at']::text[]),
('platform.ai_runs',ARRAY['workspace_id','id','job_id','connection_id','conversation_id','client_id','business_id','kind','step','turn_id','turn_revision','resume_receipt_id','control_generation','binding','snapshot','snapshot_digest','storage_fingerprint','config','config_fingerprint','deadline','calls_used','reads_used','tokens_reserved','cost_reserved','read_audit','result','selected_at','winning_claim_hash','created_at','knowledge_pin','active_projection','knowledge_release_id','search_pin','search_refs','search_build_id','portfolio_pin','media_pin','portfolio_refs','portfolio_session_id','portfolio_build_id','delivery_read_audit','intake_pin']::text[]),
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
('platform.saas_plan_revisions',ARRAY['plan_revision_id','plan_id','revision','publication_state','published_at','created_at']::text[]),
('platform.saas_plans',ARRAY['plan_id','code','display_name','status','created_at']::text[]),
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
        (SELECT count(*) FROM functions)=377 AND (SELECT count(DISTINCT to_regprocedure(signature)) FROM expected)=376
        AND NOT EXISTS(SELECT 1 FROM expected e LEFT JOIN functions f ON f.oid=to_regprocedure(e.signature)
          WHERE f.oid IS NULL OR encode(sha256(convert_to(f.prosrc,'UTF8')),'hex')<>e.body_hash OR f.lanname<>e.language
            OR f.prosecdef<>e.security_definer OR f.provolatile::text<>e.volatility OR f.proowner<>'asm_migrator'::regrole
            OR has_function_privilege('asm_runtime',f.oid,'EXECUTE')<>e.runtime_execute
            OR f.proconfig IS DISTINCT FROM ARRAY['search_path=pg_catalog, pg_temp']
            OR EXISTS(SELECT 1 FROM aclexplode(f.proacl) a WHERE a.grantee=0 AND a.privilege_type='EXECUTE'))
        AND EXISTS(SELECT 1 FROM functions f WHERE f.oid='platform.owner_decision_schema_profile()'::regprocedure
          AND f.proowner='asm_migrator'::regrole AND f.lanname='sql' AND f.prosecdef AND f.provolatile='s'
          AND f.proconfig=ARRAY['search_path=pg_catalog, pg_temp'] AND NOT has_function_privilege('asm_runtime',f.oid,'EXECUTE')
          AND NOT EXISTS(SELECT 1 FROM aclexplode(f.proacl) a WHERE a.grantee=0 AND a.privilege_type='EXECUTE'))
        AND EXISTS(SELECT 1 FROM pg_roles WHERE rolname='asm_runtime' AND rolcanlogin AND NOT rolsuper AND NOT rolbypassrls
          AND NOT rolinherit AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolreplication)
        AND NOT EXISTS(SELECT 1 FROM pg_auth_members WHERE member='asm_runtime'::regrole)
        AND (SELECT count(*) FROM tables)=81 AND NOT EXISTS(SELECT 1 FROM columns_expected e LEFT JOIN tables t ON t.name=e.table_name
          WHERE t.oid IS NULL OR t.columns IS DISTINCT FROM e.column_names)
        AND NOT EXISTS(SELECT 1 FROM tables WHERE name IN ('platform.business_configuration_state','platform.business_configuration_releases','platform.business_configuration_receipts','platform.human_context_observations','platform.human_context_reconciliations','platform.human_context_policy_receipts','platform.ai_runs','platform.ai_provider_calls','platform.ai_deliveries','platform.ai_provider_sessions','platform.knowledge_sources','platform.knowledge_revisions','platform.knowledge_chunks','platform.knowledge_builds','platform.knowledge_build_chunks','platform.knowledge_release_builds','platform.knowledge_embedding_calls','platform.portfolio_assets','platform.portfolio_asset_versions','platform.portfolio_ai_sessions','platform.vision_analyses','platform.portfolio_items','platform.portfolio_revisions','platform.portfolio_builds','platform.portfolio_build_items','platform.portfolio_release_builds','platform.portfolio_delivery_intents','app.service_assessments','app.price_calculations','app.approval_requests','app.owner_decisions','app.quotes','platform.quote_delivery_intents')
          AND (relowner<>'asm_migrator'::regrole OR NOT relrowsecurity OR NOT relforcerowsecurity OR has_table_privilege('asm_runtime',oid,'SELECT,INSERT,UPDATE,DELETE')))
        AND (SELECT version_num FROM platform.alembic_version)='0029' AS valid),
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
      SELECT jsonb_build_object('schema_revision','0029','valid',coalesce(v.valid,false)
        AND encode(sha256(convert_to((c.value-'functions')::text,'UTF8')),'hex')='aaef3e6283c30f4713c4400672cc410dd3309e18da0f345aa8eff4935798c0db',
        'profile_sha256',encode(sha256(convert_to(E'asm:m3:native_schema:v1\n'||c.value::text,'UTF8')),'hex')) FROM validity v CROSS JOIN catalog c $$"""
