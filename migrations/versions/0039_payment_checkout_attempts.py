"""Bind a YooKassa TEST checkout and its Outbox to the chosen hold."""

import hashlib
import re

from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None

PROFILE = "platform.payment_checkout_schema_profile()"
PREVIOUS_PROFILE = "platform.payment_obligation_schema_profile()"
NONFUNCTION = "243f593aa289ba930561195a9199aaa9e4d65e42cb2b00450420a553c9af696a"
KIND = "SEND_PAYMENT_LINK"
SCOPED = "platform.payment_obligation_scoped(uuid,jsonb,uuid,text,boolean)"
REGISTER = "platform.payment_checkout_register_test_shop(uuid,uuid,text,text)"
OWNER = "platform.payment_checkout_owner(jsonb,uuid,text,uuid)"
PROVIDER_BEGIN = "platform.payment_checkout_provider_begin(uuid,uuid,jsonb,boolean)"
PROVIDER_FINISH = "platform.payment_checkout_provider_finish(uuid,uuid,jsonb)"
PROBE = "platform.payment_checkout_send_probe(uuid,uuid)"
SEND = "platform.payment_checkout_send_begin(uuid,uuid,bigint,bigint,jsonb)"

REFERENCE_KEYS = (
    (
        "app.payment_obligations",
        "checkout_obligation_ref",
        "workspace_id,business_id,id,session_id,terms_sha256,amount_minor,currency",
    ),
    (
        "app.reservation_holds",
        "checkout_hold_ref",
        "workspace_id,business_id,id,session_id,allocation_id",
    ),
)

TABLES = {
    "platform.payment_checkout_test_shops": r"""CREATE TABLE platform.payment_checkout_test_shops (
      workspace_id uuid NOT NULL,
      business_id uuid NOT NULL,
      shop_id text NOT NULL CHECK(shop_id ~ '^[0-9]{1,20}$'),
      return_url text NOT NULL CHECK(return_url ~ '^https://[^/?#@]+/payment-return$'),
      PRIMARY KEY(workspace_id,business_id),
      UNIQUE(shop_id),
      UNIQUE(workspace_id,business_id,shop_id),
      FOREIGN KEY(workspace_id,business_id) REFERENCES app.businesses(workspace_id,id)
    )""",
    "app.payment_checkout_attempts": r"""CREATE TABLE app.payment_checkout_attempts (
      workspace_id uuid NOT NULL,
      business_id uuid NOT NULL,
      id uuid NOT NULL,
      obligation_id uuid NOT NULL,
      session_id uuid NOT NULL,
      terms_sha256 text NOT NULL,
      amount_minor bigint NOT NULL,
      currency text NOT NULL,
      hold_id uuid NOT NULL,
      allocation_id uuid NOT NULL,
      expires_at timestamptz NOT NULL CHECK(isfinite(expires_at)),
      timezone text NOT NULL,
      client_id uuid NOT NULL,
      conversation_id uuid NOT NULL,
      connection_id uuid NOT NULL,
      control_generation bigint NOT NULL,
      scheduling_run_id uuid,
      shop_id text NOT NULL,
      idempotence_key uuid NOT NULL UNIQUE,
      request_body text NOT NULL,
      request_sha256 text NOT NULL CHECK(request_sha256 ~ '^[a-f0-9]{64}$'),
      first_request_at timestamptz CHECK(isfinite(first_request_at)),
      provider_id text CHECK(provider_id ~ '^[a-zA-Z0-9_-]{1,64}$'),
      provider_status text CHECK(provider_status IN ('pending','canceled','succeeded','waiting_for_capture')),
      confirmation_url text CHECK(confirmation_url ~ '^https://(yoomoney|yookassa)\.ru([:]443)?/' AND length(confirmation_url)<=2048),
      status text NOT NULL CHECK(status IN ('QUEUED','UNKNOWN','WAITING','READY','NO_LINK','CANCELED','BLOCKED')),
      reason text CHECK(reason IN ('CARD_MINIMUM','STORE_UNAVAILABLE','HOLD_INACTIVE',
        'CONTEXT_CHANGED','CHANNEL_RIGHTS_UNAVAILABLE','PROVIDER_UNKNOWN','IDEMPOTENCE_EXPIRED')),
      created_at timestamptz NOT NULL CHECK(isfinite(created_at) AND created_at<expires_at),
      message_id uuid,
      outbox_id uuid,
      send_job_id uuid,
      PRIMARY KEY(workspace_id,business_id,id),
      UNIQUE(workspace_id,message_id),
      UNIQUE(workspace_id,outbox_id),
      UNIQUE(workspace_id,send_job_id),
      UNIQUE(shop_id,provider_id),
      FOREIGN KEY(workspace_id,business_id,shop_id)
        REFERENCES platform.payment_checkout_test_shops(workspace_id,business_id,shop_id),
      FOREIGN KEY(workspace_id,business_id,obligation_id,session_id,terms_sha256,amount_minor,currency)
        REFERENCES app.payment_obligations(workspace_id,business_id,id,session_id,terms_sha256,amount_minor,currency),
      FOREIGN KEY(workspace_id,business_id,hold_id,session_id,allocation_id)
        REFERENCES app.reservation_holds(workspace_id,business_id,id,session_id,allocation_id),
      FOREIGN KEY(workspace_id,conversation_id,client_id) REFERENCES app.conversations(workspace_id,id,client_id),
      FOREIGN KEY(workspace_id,connection_id) REFERENCES app.channel_connections(workspace_id,id),
      FOREIGN KEY(workspace_id,scheduling_run_id) REFERENCES platform.scheduling_turn_actions(workspace_id,run_id),
      FOREIGN KEY(workspace_id,message_id) REFERENCES app.messages(workspace_id,id) DEFERRABLE INITIALLY DEFERRED,
      FOREIGN KEY(workspace_id,outbox_id) REFERENCES app.outbox_events(workspace_id,id) DEFERRABLE INITIALLY DEFERRED,
      FOREIGN KEY(workspace_id,send_job_id) REFERENCES platform.messaging_jobs(workspace_id,id) DEFERRABLE INITIALLY DEFERRED,
      CHECK((status='READY')=(confirmation_url IS NOT NULL)),
      CHECK((provider_id IS NULL)=(provider_status IS NULL)),
      CHECK(status<>'CANCELED' OR provider_status='canceled'),
      CHECK((status IN ('WAITING','READY','NO_LINK','CANCELED'))=(provider_id IS NOT NULL)),
      CHECK((status IN ('QUEUED','BLOCKED'))=(first_request_at IS NULL)),
      CHECK(first_request_at IS NULL OR first_request_at>=created_at),
      CHECK((message_id IS NULL)=(outbox_id IS NULL) AND (outbox_id IS NULL)=(send_job_id IS NULL))
    )""",
    "platform.payment_checkout_receipts": r"""CREATE TABLE platform.payment_checkout_receipts (
      workspace_id uuid NOT NULL,
      business_id uuid NOT NULL,
      actor_id uuid NOT NULL,
      command_key text NOT NULL CHECK(command_key ~ '^[A-Za-z0-9._:-]{1,128}$'),
      hold_id uuid NOT NULL,
      replace_id uuid,
      attempt_id uuid NOT NULL,
      PRIMARY KEY(workspace_id,actor_id,command_key),
      FOREIGN KEY(workspace_id,actor_id) REFERENCES platform.workspace_memberships(workspace_id,user_account_id),
      FOREIGN KEY(workspace_id,business_id,hold_id) REFERENCES app.reservation_holds(workspace_id,business_id,id),
      FOREIGN KEY(workspace_id,business_id,attempt_id) REFERENCES app.payment_checkout_attempts(workspace_id,business_id,id),
      FOREIGN KEY(workspace_id,business_id,replace_id) REFERENCES app.payment_checkout_attempts(workspace_id,business_id,id)
    )""",
}

INDEXES = (
    """CREATE UNIQUE INDEX payment_checkout_open_intent
        ON app.payment_checkout_attempts(workspace_id,business_id,obligation_id) WHERE status<>'CANCELED'""",
    """CREATE INDEX payment_checkout_history
        ON app.payment_checkout_attempts(workspace_id,business_id,obligation_id,created_at DESC,id DESC)""",
)

TEXT = "platform.payment_checkout_text(app.payment_checkout_attempts)"
ENQUEUE = "platform.payment_checkout_enqueue(app.payment_checkout_attempts,uuid)"
QUEUE = "platform.payment_checkout_queue(uuid,jsonb,uuid,uuid,uuid,uuid)"
LIVE = "platform.payment_checkout_hold_live(app.payment_checkout_attempts)"
GUARD = "platform.payment_checkout_delivery_block(app.payment_checkout_attempts)"
JOB = "platform.payment_checkout_job_attempt(platform.messaging_jobs)"

FUNCTIONS = {
    REGISTER: r"""CREATE FUNCTION platform.payment_checkout_register_test_shop(
      ws uuid,business uuid,p_shop text,p_return_url text
    ) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    BEGIN
      IF current_database()<>'asm_test' OR coalesce(current_setting('asm.actor_kind',true),'')<>''
        OR NOT EXISTS(SELECT 1 FROM app.businesses WHERE (workspace_id,id,status)=(ws,business,'ACTIVE'))
        THEN RETURN false; END IF;
      INSERT INTO platform.payment_checkout_test_shops(workspace_id,business_id,shop_id,return_url)
        VALUES(ws,business,p_shop,p_return_url) ON CONFLICT DO NOTHING;
      RETURN EXISTS(SELECT 1 FROM platform.payment_checkout_test_shops
        WHERE (workspace_id,business_id,shop_id,return_url)=(ws,business,p_shop,p_return_url));
    END $$""",
    TEXT: r"""CREATE FUNCTION platform.payment_checkout_text(a app.payment_checkout_attempts)
    RETURNS text LANGUAGE sql STABLE SET search_path=pg_catalog,pg_temp AS $$
      SELECT 'Предоплата '||(a.amount_minor/100)::text||
        CASE WHEN a.amount_minor%100<>0 THEN ','||lpad((a.amount_minor%100)::text,2,'0') ELSE '' END||
        ' ₽. Время удержано до '||to_char(a.expires_at AT TIME ZONE a.timezone,'DD.MM.YYYY HH24:MI:SS')||
        ' ('||a.timezone||').'||chr(10)||'Ссылка на оплату: '
    $$""",
    ENQUEUE: r"""CREATE FUNCTION platform.payment_checkout_enqueue(
      a app.payment_checkout_attempts,correlation uuid
    ) RETURNS void LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
    DECLARE c app.conversations%ROWTYPE;
    BEGIN
      SELECT * INTO STRICT c FROM app.conversations
        WHERE (workspace_id,business_id,id,client_id,connection_id)
          =(a.workspace_id,a.business_id,a.conversation_id,a.client_id,a.connection_id);
      INSERT INTO app.messages(workspace_id,id,conversation_id,connection_id,provider_chat_id,direction,content_type,text,occurred_at)
        VALUES(a.workspace_id,a.message_id,c.id,c.connection_id,c.provider_chat_id,'OUTBOUND','TEXT',
          platform.payment_checkout_text(a)||'[скрыта]',a.created_at);
      INSERT INTO app.outbox_events(workspace_id,id,connection_id,message_id,kind)
        VALUES(a.workspace_id,a.outbox_id,c.connection_id,a.message_id,'SEND_PAYMENT_LINK');
      INSERT INTO platform.messaging_jobs(workspace_id,id,connection_id,kind,outbox_id,correlation_id)
        VALUES(a.workspace_id,a.send_job_id,c.connection_id,'SEND_PAYMENT_LINK',a.outbox_id,correlation);
    END $$""",
    QUEUE: r"""CREATE FUNCTION platform.payment_checkout_queue(
      ws uuid,p_selection jsonb,p_hold uuid,p_run uuid,p_correlation uuid,p_replace uuid
    ) RETURNS app.payment_checkout_attempts LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
    DECLARE business uuid:=(p_selection->>'business_id')::uuid; payment jsonb;
      q app.quotes%ROWTYPE; c app.conversations%ROWTYPE; shop platform.payment_checkout_test_shops%ROWTYPE;
      a app.payment_checkout_attempts%ROWTYPE; h app.reservation_holds%ROWTYPE; zone text;
      aid uuid:=uuidv7(); message uuid; box uuid; job uuid; body text; moment timestamptz;
      kopecks bigint; obligation uuid; problem text;
    BEGIN
      SELECT * INTO shop FROM platform.payment_checkout_test_shops
        WHERE (workspace_id,business_id)=(ws,business) FOR SHARE;
      IF NOT FOUND THEN RETURN NULL; END IF;
      q:=platform.scheduling_agreement(ws,p_selection);
      IF q.material->'deposit'->>'mode'='NONE' THEN RETURN NULL; END IF;

      -- Same order as scheduling intent and worker admission: conversation
      -- before resource. The owner path takes this lock before the resource too.
      SELECT * INTO STRICT c FROM app.conversations
        WHERE (workspace_id,business_id,id,client_id)=(ws,business,q.conversation_id,q.client_id)
        FOR NO KEY UPDATE;
      payment:=platform.payment_obligation_scoped(ws,p_selection,p_hold,NULL,true);
      obligation:=(payment->'obligation'->>'id')::uuid;
      SELECT * INTO a FROM app.payment_checkout_attempts
        WHERE (workspace_id,business_id,obligation_id)=(ws,business,obligation)
        ORDER BY created_at DESC,id DESC LIMIT 1;
      IF FOUND THEN
        IF p_replace IS NULL THEN RETURN CASE WHEN a.hold_id=p_hold THEN a ELSE NULL END; END IF;
        IF (a.id,a.status) IS DISTINCT FROM (p_replace,'CANCELED')
          THEN RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P3101'; END IF;
      ELSIF p_replace IS NOT NULL THEN
        RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P3101';
      END IF;
      SELECT * INTO STRICT h FROM app.reservation_holds
        WHERE (workspace_id,business_id,id)=(ws,business,p_hold);
      SELECT f.timezone INTO STRICT zone
        FROM app.availability_options opt JOIN app.availability_offers f
          ON (f.workspace_id,f.business_id,f.id)=(opt.workspace_id,opt.business_id,opt.offer_id)
        WHERE (opt.workspace_id,opt.business_id,opt.id)=(ws,business,h.option_id);
      moment:=clock_timestamp();
      IF h.expires_at<=moment THEN RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P3101'; END IF;
      kopecks:=(payment->'obligation'->>'amount_minor')::bigint;
      body:=jsonb_build_object(
        'amount',jsonb_build_object('value',(kopecks/100)::text||'.'||lpad((kopecks%100)::text,2,'0'),'currency','RUB'),
        'capture',true,'confirmation',jsonb_build_object('type','redirect','return_url',shop.return_url),
        'payment_method_data',jsonb_build_object('type','bank_card'),'metadata',jsonb_build_object('asm_attempt_id',aid),
        'description','Предоплата за визит')::text;
      problem:=CASE WHEN kopecks<100 THEN 'CARD_MINIMUM' END;
      IF problem IS NULL THEN message:=uuidv7(); box:=uuidv7(); job:=uuidv7(); END IF;
      INSERT INTO app.payment_checkout_attempts(workspace_id,business_id,id,obligation_id,session_id,
        terms_sha256,amount_minor,currency,hold_id,allocation_id,expires_at,timezone,client_id,conversation_id,
        connection_id,control_generation,scheduling_run_id,shop_id,idempotence_key,request_body,request_sha256,
        status,reason,created_at,message_id,outbox_id,send_job_id)
      VALUES(ws,business,aid,obligation,h.session_id,q.terms_sha256,kopecks,'RUB',h.id,h.allocation_id,
        h.expires_at,zone,c.client_id,c.id,c.connection_id,c.control_generation,p_run,shop.shop_id,
        gen_random_uuid(),body,encode(sha256(convert_to(body,'UTF8')),'hex'),
        CASE WHEN problem IS NULL THEN 'QUEUED' ELSE 'BLOCKED' END,problem,moment,message,box,job)
      RETURNING * INTO a;
      -- The chat command finishes its no-reply decision before inserting
      -- the message, so the prepared outbound does not change its snapshot.
      IF job IS NOT NULL AND p_run IS NULL THEN
        PERFORM platform.payment_checkout_enqueue(a,p_correlation);
      END IF;
      RETURN a;
    END $$""",
    LIVE: r"""CREATE FUNCTION platform.payment_checkout_hold_live(a app.payment_checkout_attempts)
    RETURNS boolean LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
    DECLARE resource uuid; moment timestamptz;
    BEGIN
      SELECT id INTO STRICT resource FROM app.scheduling_resources
        WHERE (workspace_id,business_id)=(a.workspace_id,a.business_id) FOR UPDATE;
      moment:=clock_timestamp();
      RETURN EXISTS(
        SELECT 1 FROM app.reservation_holds h
        JOIN app.resource_allocations l ON (l.workspace_id,l.business_id,l.resource_id,l.id,l.session_id)
          =(h.workspace_id,h.business_id,h.resource_id,h.allocation_id,h.session_id)
        JOIN app.availability_options o ON (o.workspace_id,o.business_id,o.id)=(h.workspace_id,h.business_id,h.option_id)
        JOIN app.availability_offers f ON (f.workspace_id,f.business_id,f.id)=(o.workspace_id,o.business_id,o.offer_id)
        JOIN app.payment_obligations payment ON (payment.workspace_id,payment.business_id,payment.id)
          =(a.workspace_id,a.business_id,a.obligation_id)
        JOIN app.service_sessions s ON (s.workspace_id,s.id,s.order_id)=(payment.workspace_id,payment.session_id,payment.order_id)
        JOIN app.quotes q ON (q.workspace_id,q.id)=(payment.workspace_id,payment.quote_id)
        JOIN app.service_requests d ON (d.workspace_id,d.id,d.business_id,d.conversation_id,d.client_id)
          =(q.workspace_id,q.request_id,q.business_id,q.conversation_id,q.client_id)
        WHERE (h.workspace_id,h.business_id,h.resource_id,h.id,h.session_id,h.allocation_id,h.expires_at)
          =(a.workspace_id,a.business_id,resource,a.hold_id,a.session_id,a.allocation_id,a.expires_at)
          AND (f.client_id,f.conversation_id,f.request_id,f.quote_id,f.order_id,f.terms_sha256,f.timezone)
            =(a.client_id,a.conversation_id,d.id,q.id,payment.order_id,a.terms_sha256,a.timezone)
          AND (f.session_id,f.resource_id,f.deposit)=(h.session_id,h.resource_id,q.material->'deposit')
          AND (q.client_id,q.conversation_id)=(a.client_id,a.conversation_id)
          AND l.kind='HOLD' AND l.released_at IS NULL AND h.expires_at>moment
          AND l.occupied=tstzrange(o.busy_start,o.busy_end,'[)')
          AND s.status='PLANNED' AND s.scheduled_at IS NULL
      );
    END $$""",
    GUARD: r"""CREATE FUNCTION platform.payment_checkout_delivery_block(a app.payment_checkout_attempts)
    RETURNS text LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
    DECLARE c app.conversations%ROWTYPE; conn app.channel_connections%ROWTYPE;
      rights platform.telegram_connection_state%ROWTYPE;
      pick platform.scheduling_turn_actions%ROWTYPE;
    BEGIN
      PERFORM 1 FROM app.businesses WHERE (workspace_id,id,status)=(a.workspace_id,a.business_id,'ACTIVE') FOR SHARE;
      IF NOT FOUND THEN RETURN 'CHANNEL_RIGHTS_UNAVAILABLE'; END IF;
      SELECT * INTO conn FROM app.channel_connections
        WHERE (workspace_id,business_id,id,status)=(a.workspace_id,a.business_id,a.connection_id,'ACTIVE') FOR SHARE;
      IF NOT FOUND THEN RETURN 'CHANNEL_RIGHTS_UNAVAILABLE'; END IF;
      PERFORM platform.messaging_lock_billing_workspace(a.workspace_id);
      SELECT * INTO rights FROM platform.telegram_connection_state
        WHERE (workspace_id,connection_id)=(a.workspace_id,a.connection_id) FOR NO KEY UPDATE;
      SELECT * INTO c FROM app.conversations
        WHERE (workspace_id,business_id,id,client_id,connection_id)
          =(a.workspace_id,a.business_id,a.conversation_id,a.client_id,a.connection_id) FOR NO KEY UPDATE;
      IF NOT FOUND OR c.control_mode<>'AI' OR c.control_generation<>a.control_generation THEN RETURN 'CONTEXT_CHANGED'; END IF;
      IF NOT EXISTS(SELECT 1 FROM platform.conversation_control_receipts r
          WHERE (r.workspace_id,r.conversation_id,r.client_id,r.accepted_generation,r.activation_fence_seq)
            =(c.workspace_id,c.id,c.client_id,c.control_generation,c.activation_fence_seq)
            AND r.operation='RESUME' AND r.accepted_mode='AI')
        OR platform.human_context_admission(a.workspace_id,c.id,NULL) IS DISTINCT FROM 'CURRENT'
        THEN RETURN 'CONTEXT_CHANGED'; END IF;
      IF a.scheduling_run_id IS NOT NULL THEN
        SELECT * INTO pick FROM platform.scheduling_turn_actions
          WHERE (workspace_id,business_id,run_id,conversation_id,client_id,phase)
            =(a.workspace_id,a.business_id,a.scheduling_run_id,a.conversation_id,a.client_id,'DONE');
        IF NOT FOUND OR pick.result->>'hold_id' IS DISTINCT FROM a.hold_id::text
          OR platform.scheduling_chat_sources_current(pick) IS NOT TRUE
          THEN RETURN 'CONTEXT_CHANGED'; END IF;
      END IF;
      IF platform.payment_checkout_hold_live(a) IS NOT TRUE THEN RETURN 'HOLD_INACTIVE'; END IF;
      -- Before a Telegram probe or an owner replay, use the last known rights on
      -- this generation. The dispatch transaction separately requires a fresh observation.
      IF platform.messaging_manual_send_allowed(a.workspace_id) IS NOT TRUE
        OR (conn.provider='TELEGRAM' AND (
          rights.observed_generation IS DISTINCT FROM rights.generation OR rights.error_code IS NOT NULL
          OR rights.is_enabled IS NOT TRUE OR rights.can_reply IS NOT TRUE
          OR c.last_client_inbound_at IS NULL OR clock_timestamp()>=c.last_client_inbound_at+interval '24 hours'
        ))
        THEN RETURN 'CHANNEL_RIGHTS_UNAVAILABLE'; END IF;
      RETURN NULL;
    EXCEPTION WHEN SQLSTATE 'P2301' THEN RETURN 'CHANNEL_RIGHTS_UNAVAILABLE';
    END $$""",
    JOB: r"""CREATE FUNCTION platform.payment_checkout_job_attempt(j platform.messaging_jobs)
    RETURNS app.payment_checkout_attempts LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
    DECLARE a app.payment_checkout_attempts%ROWTYPE;
    BEGIN
      IF j.kind<>'SEND_PAYMENT_LINK' OR current_database()<>'asm_test'
        OR NOT EXISTS(SELECT 1 FROM app.outbox_events b WHERE (b.workspace_id,b.id,b.kind,b.status)
          =(j.workspace_id,j.outbox_id,j.kind,'PENDING'))
        THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
      SELECT * INTO STRICT a FROM app.payment_checkout_attempts
        WHERE (workspace_id,connection_id,send_job_id,outbox_id)=(j.workspace_id,j.connection_id,j.id,j.outbox_id)
        FOR NO KEY UPDATE;
      RETURN a;
    END $$""",
    PROVIDER_BEGIN: r"""CREATE FUNCTION platform.payment_checkout_provider_begin(
      p_job uuid,p_claim uuid,p_shops jsonb,p_telegram_allowed boolean
    )
    RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    DECLARE j platform.messaging_jobs%ROWTYPE:=platform.messaging_guard(p_job,p_claim);
      a app.payment_checkout_attempts%ROWTYPE:=platform.payment_checkout_job_attempt(j); problem text;
      moment timestamptz;
    BEGIN
      IF a.shop_id IS DISTINCT FROM p_shops->>a.business_id::text THEN problem:='STORE_UNAVAILABLE';
      ELSIF p_telegram_allowed IS NOT TRUE AND EXISTS(SELECT 1 FROM app.channel_connections
        WHERE (workspace_id,id,provider)=(a.workspace_id,a.connection_id,'TELEGRAM'))
        THEN problem:='CHANNEL_RIGHTS_UNAVAILABLE';
      ELSIF a.status IN ('NO_LINK','CANCELED','BLOCKED') THEN
        PERFORM platform.messaging_reschedule(j.id,'NOT_ALLOWED',false); RETURN NULL;
      ELSIF a.status<>'WAITING' THEN
        -- A known object without a link can be investigated using authenticated GET.
        problem:=platform.payment_checkout_delivery_block(a);
      END IF;
      moment:=clock_timestamp();
      IF problem IS NULL AND a.status='UNKNOWN' AND a.first_request_at+interval '24 hours'<=moment+interval '10 seconds'
        THEN problem:='IDEMPOTENCE_EXPIRED'; END IF;
      PERFORM platform.messaging_guard(p_job,p_claim);
      IF problem IS NOT NULL THEN
        UPDATE app.payment_checkout_attempts SET reason=problem,
          status=CASE WHEN status='QUEUED' THEN 'BLOCKED' ELSE status END
          WHERE (workspace_id,business_id,id)=(a.workspace_id,a.business_id,a.id);
        PERFORM platform.messaging_reschedule(j.id,'NOT_ALLOWED',false); RETURN NULL;
      END IF;
      IF a.status='READY' THEN RETURN jsonb_build_object('action','SEND'); END IF;
      IF j.lease_until<=moment+interval '11 seconds' THEN
        PERFORM platform.messaging_reschedule(j.id,'DEPENDENCY_TIMEOUT',true); RETURN NULL;
      END IF;
      IF a.status IN ('QUEUED','UNKNOWN') THEN
        UPDATE app.payment_checkout_attempts SET status='UNKNOWN',reason='PROVIDER_UNKNOWN',
          first_request_at=coalesce(first_request_at,moment)
          WHERE (workspace_id,business_id,id)=(a.workspace_id,a.business_id,a.id);
      END IF;
      RETURN jsonb_build_object('action',CASE WHEN a.provider_id IS NULL THEN 'POST' ELSE 'GET' END,
        'attempt_id',a.id,'business_id',a.business_id,'amount_minor',a.amount_minor,'provider_id',a.provider_id,
        'idempotence_key',a.idempotence_key,'request_body',a.request_body,'request_sha256',a.request_sha256);
    END $$""",
    PROVIDER_FINISH: r"""CREATE FUNCTION platform.payment_checkout_provider_finish(p_job uuid,p_claim uuid,p jsonb)
    RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    DECLARE j platform.messaging_jobs%ROWTYPE:=platform.messaging_guard(p_job,p_claim);
      a app.payment_checkout_attempts%ROWTYPE:=platform.payment_checkout_job_attempt(j);
      object_id text:=p->>'id'; link text:=p->>'link'; new_status text;
    BEGIN
      IF a.status NOT IN ('UNKNOWN','WAITING') THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
      IF p IS NOT NULL THEN
        IF object_id IS NULL OR (a.provider_id IS NOT NULL AND a.provider_id<>object_id) THEN
          RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        new_status:=CASE p->>'status'
          WHEN 'pending' THEN CASE WHEN link IS NULL THEN 'WAITING' ELSE 'READY' END
          WHEN 'canceled' THEN 'CANCELED'
          WHEN 'succeeded' THEN 'NO_LINK'
          WHEN 'waiting_for_capture' THEN 'NO_LINK' END;
        IF new_status IS NULL OR (new_status<>'READY' AND link IS NOT NULL) THEN
          RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        UPDATE app.payment_checkout_attempts SET status=new_status,provider_id=object_id,
          provider_status=p->>'status',confirmation_url=link,reason=NULL WHERE (workspace_id,business_id,id)=(a.workspace_id,a.business_id,a.id);
      END IF;
      IF new_status='READY' THEN RETURN true; END IF;
      PERFORM platform.messaging_reschedule(j.id,'DEPENDENCY_UNAVAILABLE',
        new_status IS NULL OR new_status='WAITING');
      RETURN false;
    END $$""",
    PROBE: r"""CREATE FUNCTION platform.payment_checkout_send_probe(p_job uuid,p_claim uuid)
    RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    DECLARE j platform.messaging_jobs%ROWTYPE:=platform.messaging_guard(p_job,p_claim);
      a app.payment_checkout_attempts%ROWTYPE:=platform.payment_checkout_job_attempt(j);
      s platform.telegram_connection_state%ROWTYPE;
    BEGIN
      IF a.status<>'READY' OR platform.payment_checkout_delivery_block(a) IS NOT NULL THEN RETURN NULL; END IF;
      PERFORM platform.messaging_guard(p_job,p_claim);
      SELECT * INTO s FROM platform.telegram_connection_state WHERE (workspace_id,connection_id)=(j.workspace_id,j.connection_id);
      IF NOT FOUND THEN RETURN NULL; END IF;
      UPDATE platform.messaging_jobs SET telegram_probe_claim=p_claim,telegram_probe_generation=s.generation,
        telegram_probe_version=s.observation_version WHERE id=j.id;
      RETURN platform.telegram_probe_json(s);
    END $$""",
    SEND: r"""CREATE FUNCTION platform.payment_checkout_send_begin(
      p_job uuid,p_claim uuid,p_generation bigint,p_version bigint,p_observation jsonb
    ) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    DECLARE j platform.messaging_jobs%ROWTYPE:=platform.messaging_guard(p_job,p_claim);
      a app.payment_checkout_attempts%ROWTYPE:=platform.payment_checkout_job_attempt(j);
      conn app.channel_connections%ROWTYPE; msg app.messages%ROWTYPE; observation jsonb; problem text;
      dispatch uuid:=gen_random_uuid();
    BEGIN
      IF a.status<>'READY' THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
      problem:=platform.payment_checkout_delivery_block(a);
      SELECT * INTO STRICT conn FROM app.channel_connections WHERE (workspace_id,id)=(a.workspace_id,a.connection_id);
      IF problem IS NULL AND conn.provider='TELEGRAM' THEN
        IF p_observation IS NULL THEN problem:='CHANNEL_RIGHTS_UNAVAILABLE';
        ELSE
          IF (j.telegram_probe_claim,j.telegram_probe_generation,j.telegram_probe_version)
            IS DISTINCT FROM (p_claim,p_generation,p_version)
            THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
          observation:=platform.telegram_save_observation(a.workspace_id,a.connection_id,p_generation,p_version,p_observation);
          IF observation->>'code'='UNAVAILABLE'
            AND (observation->>'generation')::bigint=p_generation
            AND (observation->>'observation_version')::bigint>p_version THEN
            -- A newer observation on this generation may have won the write.
            -- Recheck eligibility and let the leased job obtain fresh rights.
            problem:=platform.payment_checkout_delivery_block(a);
            IF problem IS NULL THEN
              RETURN jsonb_build_object('code','UNAVAILABLE','status',
                platform.messaging_reschedule(j.id,'DEPENDENCY_UNAVAILABLE',true)->>'status');
            END IF;
          ELSIF observation->>'code' IS DISTINCT FROM 'OBSERVED'
            OR platform.telegram_can_send(a.workspace_id,a.connection_id,a.conversation_id,true) IS NOT TRUE
            THEN problem:='CHANNEL_RIGHTS_UNAVAILABLE'; END IF;
        END IF;
      END IF;
      IF problem IS NULL THEN problem:=platform.payment_checkout_delivery_block(a); END IF;
      PERFORM platform.messaging_guard(p_job,p_claim);
      IF problem IS NOT NULL THEN
        UPDATE app.payment_checkout_attempts SET reason=problem
          WHERE (workspace_id,business_id,id)=(a.workspace_id,a.business_id,a.id);
        PERFORM platform.messaging_reschedule(j.id,'NOT_ALLOWED',false);
        RETURN jsonb_build_object('code','NOT_ALLOWED','status','FAILED');
      END IF;
      SELECT m.* INTO STRICT msg FROM app.messages m JOIN app.conversations c
        ON (c.workspace_id,c.id,c.client_id,c.connection_id,c.provider_chat_id)
          =(m.workspace_id,m.conversation_id,a.client_id,m.connection_id,m.provider_chat_id)
        JOIN app.outbox_events b ON (b.workspace_id,b.id,b.message_id,b.connection_id)
          =(m.workspace_id,a.outbox_id,m.id,m.connection_id)
        WHERE (m.workspace_id,m.id,m.conversation_id,m.connection_id,m.direction,m.content_type,m.text)
          =(a.workspace_id,a.message_id,a.conversation_id,a.connection_id,'OUTBOUND','TEXT',
            platform.payment_checkout_text(a)||'[скрыта]');
      UPDATE app.outbox_events SET status='DISPATCHING',attempt_id=dispatch,error_code=NULL,version=version+1
        WHERE (workspace_id,id)=(a.workspace_id,a.outbox_id);
      RETURN jsonb_build_object('code','PERMITTED','job_id',j.id,'claim_token',p_claim,'attempt_id',dispatch,
        'workspace_id',j.workspace_id,'connection_id',j.connection_id,'provider',conn.provider,
        'bot_identity',conn.bot_identity,'external_connection_id',conn.external_connection_id,
        'chat_id',msg.provider_chat_id,'text',platform.payment_checkout_text(a)||a.confirmation_url);
    END $$""",
    OWNER: r"""CREATE FUNCTION platform.payment_checkout_owner(p_selection jsonb,p_hold uuid,p_key text,p_replace uuid)
    RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    DECLARE business uuid:=(p_selection->>'business_id')::uuid;
      ws uuid:=platform.scheduling_owner_scope(business,'schedule');
      actor uuid:=nullif(current_setting('asm.actor_id',true),'')::uuid; payment jsonb;
      a app.payment_checkout_attempts%ROWTYPE; receipt platform.payment_checkout_receipts%ROWTYPE; view jsonb;
      sent text;
    BEGIN
      IF p_key IS NOT NULL THEN
        IF p_key !~ '^[A-Za-z0-9._:-]{1,128}$' THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P3101'; END IF;
        PERFORM pg_advisory_xact_lock(hashtextextended(ws::text||':'||actor::text||':'||p_key,2039));
      END IF;
      payment:=platform.payment_obligation_scoped(ws,p_selection,p_hold,NULL,false);
      IF p_key IS NOT NULL THEN
        SELECT * INTO receipt FROM platform.payment_checkout_receipts WHERE (workspace_id,actor_id,command_key)=(ws,actor,p_key);
        IF FOUND AND (receipt.business_id,receipt.hold_id,receipt.replace_id)
          IS DISTINCT FROM (business,p_hold,p_replace)
          THEN RAISE EXCEPTION 'IDEMPOTENCY_KEY_CONFLICT' USING ERRCODE='P3101'; END IF;
      END IF;

      IF receipt.attempt_id IS NOT NULL THEN
        SELECT * INTO STRICT a FROM app.payment_checkout_attempts WHERE (workspace_id,business_id,id)=(ws,business,receipt.attempt_id);
      ELSIF p_key IS NOT NULL AND (payment->>'hold_status'='HELD' AND payment->>'requires_prepayment'='true') THEN
        -- A concurrent worker may already be admitting delivery of this attempt.
        -- Match its channel, billing, Telegram state, conversation and resource order.
        PERFORM 1 FROM app.channel_connections conn JOIN app.conversations c
          ON (c.workspace_id,c.business_id,c.connection_id)=(conn.workspace_id,conn.business_id,conn.id)
          WHERE (c.workspace_id,c.business_id,c.id)=(ws,business,(p_selection->>'conversation_id')::uuid)
          FOR SHARE OF conn;
        PERFORM platform.messaging_lock_billing_workspace(ws);
        PERFORM 1 FROM platform.telegram_connection_state state JOIN app.conversations c
          ON (c.workspace_id,c.connection_id)=(state.workspace_id,state.connection_id)
          WHERE (c.workspace_id,c.business_id,c.id)=(ws,business,(p_selection->>'conversation_id')::uuid)
          FOR NO KEY UPDATE OF state;
        a:=platform.payment_checkout_queue(ws,p_selection,p_hold,NULL,gen_random_uuid(),p_replace);
        IF a.id IS NOT NULL THEN
          INSERT INTO platform.payment_checkout_receipts(workspace_id,business_id,actor_id,command_key,hold_id,replace_id,attempt_id)
            VALUES(ws,business,actor,p_key,p_hold,p_replace,a.id);
        ELSIF p_replace IS NOT NULL THEN RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P3101';
        END IF;
      ELSE
        SELECT * INTO a FROM app.payment_checkout_attempts p WHERE (p.workspace_id,p.business_id,p.hold_id,p.obligation_id)
          =(ws,business,p_hold,(payment->'obligation'->>'id')::uuid)
          ORDER BY p.created_at DESC,p.id DESC LIMIT 1;
        IF p_key IS NOT NULL AND (p_replace IS NOT NULL OR (a.id IS NULL AND payment->>'requires_prepayment'='true'))
          THEN RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P3101'; END IF;
      END IF;
      IF a.id IS NOT NULL THEN
        SELECT status INTO sent FROM app.outbox_events WHERE (workspace_id,id)=(ws,a.outbox_id);
        view:=jsonb_build_object('id',a.id,'obligation_id',a.obligation_id,'hold_id',a.hold_id,
          'expires_at',platform.quote_timestamp(a.expires_at),'status',a.status,'reason',a.reason,'delivery',sent);
      END IF;
      IF p_key IS NULL THEN RETURN jsonb_build_object('checkout',view); END IF;
      RETURN jsonb_build_object('checkout',view,'confirmation_url',CASE WHEN a.status='READY' AND a.reason IS NULL
        AND platform.payment_checkout_delivery_block(a) IS NULL THEN a.confirmation_url END);
    END $$""",
}

RUNTIME = (REGISTER, OWNER, PROVIDER_BEGIN, PROVIDER_FINISH, PROBE, SEND)


def dependencies():
    scripts = op.get_context().script
    if scripts is None:
        from pathlib import Path

        from alembic.script import ScriptDirectory

        scripts = ScriptDirectory(str(Path(__file__).resolve().parents[1]))
    prior = scripts.get_revision("0038").module
    quotes, scheduling = prior.dependencies()
    return prior, quotes, scheduling, scripts.get_revision("0029").module


def replace(sql, old, new):
    assert sql.count(old) == 1, old
    return sql.replace(old, new, 1)


def kernel_changes(delivery):
    original, upgraded = {}, {}
    for signature, source in delivery.KERNEL_FUNCTIONS_0028.items():
        if signature.startswith("platform.messaging_job_json("):
            continue
        if signature == "platform.turn_material()":
            before = source.replace(
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
            after = replace(
                before,
                "          ) THEN RETURN NEW; END IF;",
                """          ) OR EXISTS(SELECT 1 FROM app.payment_checkout_attempts a
            WHERE (a.workspace_id,a.message_id,a.connection_id)=(NEW.workspace_id,NEW.id,NEW.connection_id)
          ) THEN RETURN NEW; END IF;""",
            )
            after = replace(
                after,
                "NEW.kind='SEND_QUOTE_TEXT'",
                "NEW.kind IN ('SEND_QUOTE_TEXT','SEND_PAYMENT_LINK')",
            )
        else:
            before = source.replace("'SEND_AI_PHOTO'", "'SEND_AI_PHOTO','SEND_QUOTE_TEXT'")
            after = before.replace("'SEND_QUOTE_TEXT'", "'SEND_QUOTE_TEXT','SEND_PAYMENT_LINK'")
        if after != before:
            original[signature], upgraded[signature] = before, after
    return original, upgraded


def command_changes(prior, scheduling, delivery):
    previous, current = kernel_changes(delivery)
    previous[prior.OWNER] = prior.FUNCTIONS[prior.OWNER]
    scoped = (
        prior.FUNCTIONS[prior.OWNER]
        .replace(
            "CREATE FUNCTION platform.payment_obligation_owner(\n      p_selection jsonb,p_hold uuid,p_key text",
            "CREATE FUNCTION platform.payment_obligation_scoped(\n      ws uuid,p_selection jsonb,p_hold uuid,p_key text,p_automatic boolean",
        )
        .replace(" SECURITY DEFINER", "")
        .replace("      ws uuid:=platform.scheduling_owner_scope(business,'schedule');", "")
    )
    # The scoped path reuses the immutable accepted-money basis. Only owner
    # commands can add the original M8.1A actor receipts.
    scoped = replace(
        scoped,
        "        -- M7 takes this same resource lock before changing its allocations.",
        """      END IF;
      IF p_key IS NOT NULL OR p_automatic THEN
        -- M7 takes this same resource lock before changing its allocations.""",
    )
    scoped = replace(
        scoped,
        "(p_key IS NULL OR h.resource_id=resource)",
        "(NOT p_automatic AND p_key IS NULL OR h.resource_id=resource)",
    )
    scoped = replace(
        scoped,
        "IF p_key IS NOT NULL AND mode<>'NONE'",
        "IF (p_key IS NOT NULL OR p_automatic) AND mode<>'NONE'",
    )
    scoped = replace(
        scoped,
        "hold_status<>'HELD' AND NOT EXISTS(",
        "hold_status<>'HELD' AND (p_automatic OR NOT EXISTS(",
    )
    scoped = replace(
        scoped, ") THEN RAISE EXCEPTION 'STALE_STATE'", ")) THEN RAISE EXCEPTION 'STALE_STATE'"
    )
    scoped = replace(
        scoped,
        "IF prior.command_key IS NULL THEN",
        "IF p_key IS NOT NULL AND prior.command_key IS NULL THEN",
    )
    current[SCOPED] = scoped
    current[prior.OWNER] = r"""CREATE OR REPLACE FUNCTION platform.payment_obligation_owner(
      p_selection jsonb,p_hold uuid,p_key text
    ) RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      SELECT platform.payment_obligation_scoped(
        platform.scheduling_owner_scope((p_selection->>'business_id')::uuid,'schedule'),p_selection,p_hold,p_key,false)
    $$"""
    _, reschedule, appointments, holds, availability, _, _ = scheduling.dependencies()
    _, scoped_commands = scheduling.scoped_functions(reschedule, appointments, holds, availability)
    previous[scheduling.CLIENT_COMMAND] = scoped_commands[scheduling.CLIENT_COMMAND]
    current[
        scheduling.CLIENT_COMMAND
    ] = r"""CREATE OR REPLACE FUNCTION platform.scheduling_client_command(
      p_selection jsonb,p_client uuid,p_conversation uuid,p_action text,p_target uuid,p_key text,
      p_eligible boolean,p_options jsonb
    ) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    DECLARE business uuid:=(p_selection->>'business_id')::uuid;
      ws uuid:=platform.scheduling_owner_scope(business,'schedule');
      checkout boolean; result jsonb;
    BEGIN
      checkout:=p_action='select' AND EXISTS(SELECT 1 FROM platform.payment_checkout_test_shops
        WHERE (workspace_id,business_id)=(ws,business));
      IF checkout THEN
        -- Lock the target conversation before the scheduling resource.
        PERFORM 1 FROM app.conversations WHERE (workspace_id,business_id,id,client_id)=(ws,business,p_conversation,p_client)
          FOR NO KEY UPDATE;
      END IF;
      result:=platform.scheduling_scoped_client(ws,p_selection,p_client,p_conversation,
        p_action,p_target,p_key,p_eligible,p_options);
      IF checkout AND result->>'outcome'='HELD' THEN
        BEGIN
          PERFORM platform.payment_checkout_queue(ws,p_selection,(result->>'hold_id')::uuid,NULL,gen_random_uuid(),NULL);
        EXCEPTION WHEN SQLSTATE 'P3101' THEN
          IF SQLERRM NOT IN ('NEEDS_CLARIFICATION','STALE_STATE') THEN RAISE; END IF;
        END;
      END IF;
      RETURN result;
    END $$"""
    previous[scheduling.COMMAND] = scheduling.FUNCTIONS[scheduling.COMMAND]
    command = replace(
        previous[scheduling.COMMAND],
        "      state jsonb; outcome text; key text; seen jsonb; prior jsonb;",
        """      state jsonb; outcome text; key text; seen jsonb; prior jsonb;
      checkout app.payment_checkout_attempts%ROWTYPE;""",
    )
    command = replace(
        command,
        "        UPDATE platform.scheduling_turn_actions SET phase='READY',result=response WHERE",
        """        IF outcome='HELD' AND EXISTS(SELECT 1 FROM platform.payment_checkout_test_shops
            WHERE (workspace_id,business_id)=(r.workspace_id,r.business_id)) THEN
          BEGIN
            checkout:=platform.payment_checkout_queue(r.workspace_id,a.selection,(response->>'hold_id')::uuid,
              r.id,(SELECT correlation_id FROM platform.messaging_jobs WHERE id=p_job),NULL);
            IF checkout.send_job_id IS NOT NULL THEN
              response:=response||jsonb_build_object('checkout_queued',true);
            END IF;
          EXCEPTION WHEN SQLSTATE 'P3101' THEN
            IF SQLERRM NOT IN ('NEEDS_CLARIFICATION','STALE_STATE') THEN RAISE; END IF;
          END;
        END IF;
        UPDATE platform.scheduling_turn_actions SET phase='READY',result=response WHERE""",
    )
    current[scheduling.COMMAND] = replace(
        command,
        "coalesce(a.result->>'outcome'='REPEAT',false)",
        "coalesce(a.result->>'outcome'='REPEAT',false) OR coalesce((a.result->>'checkout_queued')::boolean,false)",
    ).replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
    current[scheduling.COMMAND] = replace(
        current[scheduling.COMMAND],
        "        RETURN response;\n      END IF;\n      RAISE EXCEPTION 'INVALID_INPUT'",
        """        IF coalesce((a.result->>'checkout_queued')::boolean,false) THEN
          SELECT * INTO checkout FROM app.payment_checkout_attempts
            WHERE (workspace_id,scheduling_run_id)=(r.workspace_id,r.id);
          IF FOUND THEN
            PERFORM platform.payment_checkout_enqueue(checkout,
              (SELECT correlation_id FROM platform.messaging_jobs WHERE id=p_job));
          END IF;
        END IF;
        RETURN response;
      END IF;
      RAISE EXCEPTION 'INVALID_INPUT'""",
    )
    # Keep the phase predicate grouped with its null-text comparison.
    current[scheduling.COMMAND] = replace(
        current[scheduling.COMMAND],
        "FROM coalesce(a.result->>'outcome'='REPEAT',false) OR coalesce((a.result->>'checkout_queued')::boolean,false) THEN",
        "FROM (coalesce(a.result->>'outcome'='REPEAT',false) OR coalesce((a.result->>'checkout_queued')::boolean,false)) THEN",
    )
    return previous, current


def schema_sql(prior, quotes, scheduling, changes, runtime):
    old, callers, _ = prior.schema_sql(scheduling, prior.quote_changes(quotes))
    new_callers = tuple(
        sql.replace(PREVIOUS_PROFILE, PROFILE).replace("'0038'", "'0039'") for sql in callers
    )
    holds = scheduling.dependencies()[3]
    definitions = (
        changes
        | {PREVIOUS_PROFILE: old}
        | dict(zip(holds.PROFILE_CALLERS, new_callers, strict=True))
    )
    profile = old.replace(PREVIOUS_PROFILE, PROFILE)
    additions = []
    for signature, sql in definitions.items():
        header, body, _ = sql.split("$$")
        name = (
            signature.replace(PREVIOUS_PROFILE, PROFILE)
            if signature != PREVIOUS_PROFILE
            else signature
        )
        existing = re.search(r"\('" + re.escape(name) + r"',[a-f0-9'\w,]+\)", profile)
        execute = signature in runtime or (
            existing is not None and existing.group().endswith(",true)")
        )
        if existing:
            profile = profile[: existing.start()] + profile[existing.end() + 2 :]
        additions.append(
            f"('{signature}','{hashlib.sha256(body.encode()).hexdigest()}',"
            f"'{('plpgsql' if 'LANGUAGE plpgsql' in header else 'sql')}',"
            f"{str('SECURITY DEFINER' in header).lower()},"
            f"'{('s' if ' STABLE ' in header else 'v')}',{str(execute).lower()})"
        )
    columns = []
    for table, sql in TABLES.items():
        names = re.findall(r"^      ([a-z_0-9]+) (?:uuid|text|bigint|timestamptz)\b", sql, re.M)
        columns.append(f"('{table}',ARRAY[{','.join(repr(name) for name in names)}]::text[])")
    extra = len(FUNCTIONS) + 2
    profile = (
        profile.replace(" AS (VALUES ", " AS (VALUES " + ",\n".join(additions) + ",\n", 1)
        .replace(
            "columns_expected(table_name,column_names) AS (VALUES ",
            "columns_expected(table_name,column_names) AS (VALUES " + ",\n".join(columns) + ",\n",
        )
        .replace("FROM functions)=456", f"FROM functions)={456 + extra}")
        .replace("FROM expected)=455", f"FROM expected)={455 + extra}")
        .replace("FROM tables)=101", "FROM tables)=104")
        .replace("FROM columns_expected)=101", "FROM columns_expected)=104")
        .replace(
            "AND NOT EXISTS(SELECT 1 FROM tables WHERE name IN (",
            "AND NOT EXISTS(SELECT 1 FROM tables WHERE name IN ("
            + ",".join(repr(table) for table in TABLES)
            + ",",
        )
        .replace("'0038'", "'0039'")
        .replace(prior.NONFUNCTION, NONFUNCTION)
    )
    return profile, new_callers, callers


def kernel_constraints(delivery, forward):
    for (table, constraint), check in delivery.KERNEL_CHECKS_0028.items():
        kinds = "'SEND_AI_PHOTO','SEND_QUOTE_TEXT'"
        if forward:
            kinds += ",'SEND_PAYMENT_LINK'"
        op.execute(
            f"ALTER TABLE {table} DROP CONSTRAINT {constraint}, ADD CONSTRAINT {constraint} "
            + check.replace("'SEND_AI_PHOTO'", kinds)
        )


def upgrade():
    prior, quotes, scheduling, delivery = dependencies()
    for relation, name, columns in REFERENCE_KEYS:
        op.execute(f"ALTER TABLE {relation} ADD CONSTRAINT {name} UNIQUE ({columns})")
    for table, ddl in TABLES.items():
        op.execute(ddl)
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY checkout_migrator ON {table} TO asm_migrator USING(true) WITH CHECK(true)"
        )
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC,asm_runtime")
    for sql in INDEXES:
        op.execute(sql)
    kernel_constraints(delivery, True)
    _, changed = command_changes(prior, scheduling, delivery)
    op.execute(changed[SCOPED])
    op.execute(f"REVOKE ALL ON FUNCTION {SCOPED} FROM PUBLIC,asm_runtime")
    for signature, sql in FUNCTIONS.items():
        op.execute(sql)
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC,asm_runtime")
    for signature in RUNTIME:
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO asm_runtime")
    for signature, sql in changed.items():
        if signature != SCOPED:
            op.execute(sql)
    profile, callers, _ = schema_sql(prior, quotes, scheduling, changed | FUNCTIONS, RUNTIME)
    for sql in callers:
        op.execute(sql)
    op.execute(profile)
    op.execute(f"REVOKE ALL ON FUNCTION {PROFILE} FROM PUBLIC,asm_runtime")


def downgrade():
    prior, quotes, scheduling, delivery = dependencies()
    op.execute(
        "LOCK TABLE app.payment_checkout_attempts,platform.payment_checkout_test_shops IN ACCESS EXCLUSIVE MODE"
    )
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM app.payment_checkout_attempts)
        OR EXISTS(SELECT 1 FROM platform.payment_checkout_test_shops)
        THEN RAISE EXCEPTION 'PAYMENT_CHECKOUT_DURABLE_DATA' USING ERRCODE='55000'; END IF;
    END $$""")
    original, changed = command_changes(prior, scheduling, delivery)
    _, _, callers = schema_sql(prior, quotes, scheduling, changed | FUNCTIONS, RUNTIME)
    for sql in callers:
        op.execute(sql)
    op.execute(f"DROP FUNCTION {PROFILE}")
    for sql in original.values():
        op.execute(sql.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1))
    for signature in reversed(FUNCTIONS):
        op.execute(f"DROP FUNCTION {signature}")
    op.execute(f"DROP FUNCTION {SCOPED}")
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE {table}")
    kernel_constraints(delivery, False)
    for relation, name, _ in reversed(REFERENCE_KEYS):
        op.execute(f"ALTER TABLE {relation} DROP CONSTRAINT {name}")
