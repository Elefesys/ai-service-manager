"""Owner-confirmed native context, bounded recovery and exact unused 0012 reversal.

The literal ORIGINAL bodies and baseline fingerprints are frozen source, never
captured from an installed database. No applied migration is changed.
"""

import hashlib
import re

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

ORIGINAL = {
    "telegram_ingest(3)": r"""CREATE OR REPLACE FUNCTION platform.telegram_ingest(p_bot text,p_projection jsonb,p_correlation uuid) RETURNS jsonb
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
      END $$""",
    "conversation_control_execute(6)": r"""CREATE OR REPLACE FUNCTION platform.conversation_control_execute(
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
          activation_fence_seq,request_fingerprint,audit_event_id,accepted_at,result,guard_profile)
          VALUES(ws,receipt,p_operation,p_key,conv.id,conv.client_id,actor,corr,p_generation,p_context,conv.control_mode,target,conv.control_generation,
            conv.control_generation+1,conv.version,fence,decode(prepared->>'request_fingerprint','hex'),audit,moment,result,CASE WHEN p_operation='RESUME' AND current_database() IN ('asm_local','asm_test')
              AND EXISTS(SELECT 1 FROM app.channel_connections WHERE workspace_id=ws AND id=conv.connection_id AND provider='CONTROLLED')
              THEN 'CONTROLLED_GUARDS_V1' END);
        RETURN jsonb_build_object('code','ACCEPTED','result',result,'request_fingerprint',prepared->>'request_fingerprint');
      END $$""",
    "turn_snapshot(2)": r"""CREATE OR REPLACE FUNCTION platform.turn_snapshot(ws uuid,p_turn uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE result jsonb; members jsonb;
      BEGIN
        SELECT jsonb_agg(jsonb_build_object('message_id',m.id,'message_version',m.version,'content_type',m.content_type,
          'membership_form',tm.membership_form,'initial_suppression_id',tm.initial_suppression_id,
          'current',platform.message_effective(ws,m.id),'ingress_at',tm.turn_ingress_at,'ingress_seq',tm.turn_ingress_seq,
          'file',CASE WHEN f.id IS NULL THEN NULL ELSE jsonb_build_object('file_id',f.id,'version',f.version,
            'status',f.status,'error_code',f.error_code,'wait_expired',f.status='PENDING') END)
          ORDER BY tm.turn_ingress_at,tm.turn_ingress_seq,tm.message_id)
          INTO members FROM app.conversation_turn_messages tm JOIN app.messages m ON (m.workspace_id,m.id)=(tm.workspace_id,tm.message_id)
          LEFT JOIN app.file_objects f ON (f.workspace_id,f.id)=(tm.workspace_id,tm.file_id)
          WHERE tm.workspace_id=ws AND tm.turn_id=p_turn;
        IF members IS NULL THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        SELECT jsonb_build_object('schema_version',2,'workspace_id',ws,'connection_id',t.connection_id,'turn_id',t.id,'turn_revision',t.revision,
          'context_version',c.version,'control_generation',t.control_generation,'readiness',t.readiness,'members',members)
          INTO STRICT result FROM app.conversation_turns t JOIN app.conversations c ON (c.workspace_id,c.id)=(t.workspace_id,t.conversation_id)
          WHERE t.workspace_id=ws AND t.id=p_turn AND t.state='READY';
        RETURN result || jsonb_build_object('snapshot_digest',encode(sha256(convert_to(result::text,'UTF8')),'hex'));
      END $$""",
    "turn_execute(2)": r"""CREATE OR REPLACE FUNCTION platform.turn_execute(p_job uuid,p_claim uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE j platform.messaging_jobs%ROWTYPE; t app.conversation_turns%ROWTYPE; input jsonb; outcome text;
      BEGIN
        j:=platform.messaging_guard(p_job,p_claim);
        IF j.kind<>'PROCESS_TURN' OR j.step NOT IN ('GROUP','MEDIA','TEST_CONSUME') THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
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
          'ready_file_count',(SELECT count(*) FROM jsonb_array_elements(j.turn_input->'members') m WHERE CASE WHEN j.turn_input->>'schema_version'='2' THEN m->'current'->>'image_availability'='ORIGINAL_READY' ELSE m->'file'->>'status'='READY' END),
          'wait_expired_count',(SELECT count(*) FROM jsonb_array_elements(j.turn_input->'members') m WHERE CASE WHEN j.turn_input->>'schema_version'='2' THEN m->'current'->>'image_availability'='ORIGINAL_PENDING' ELSE m->'file'->>'wait_expired'='true' END)) INTO expected;
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
        IF platform.material_turn_usable(ws,t.id) IS NOT TRUE OR t.state<>'READY' OR c.version IS DISTINCT FROM p_context OR
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
    "guard_turn_prepare(2)": (
        r"""CREATE OR REPLACE FUNCTION platform.guard_turn_prepare(p_job uuid,p_claim uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE j platform.messaging_jobs%ROWTYPE; t app.conversation_turns%ROWTYPE; conv app.conversations%ROWTYPE;
        rec platform.conversation_control_receipts%ROWTYPE; prior platform.turn_guard_receipts%ROWTYPE;
        target_turn uuid; input jsonb; outcome text;
      BEGIN
        j:=platform.messaging_guard(p_job,p_claim);
        IF j.kind<>'PROCESS_TURN' OR j.step<>'GUARDED_TEXT' THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        target_turn:=j.turn_id;
"""
        "        \n"
        r"""        SELECT * INTO STRICT t FROM app.conversation_turns WHERE workspace_id=j.workspace_id AND id=target_turn;
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
        "        \n"
        r"""        SELECT * INTO prior FROM platform.turn_guard_receipts g WHERE g.workspace_id=j.workspace_id AND g.turn_id=j.turn_id AND g.outcome='ACCEPTED';
        IF FOUND THEN
          outcome:='ALREADY_ACCEPTED'; UPDATE platform.messaging_jobs SET status='SUCCEEDED',turn_outcome=outcome,error_code=NULL,
        claim_token=NULL,lease_until=NULL,worker_id=NULL,completed_at=clock_timestamp(),version=version+1 WHERE id=j.id;
          RETURN jsonb_build_object('code',outcome,'job_id',j.id,'turn_id',j.turn_id,'turn_revision',j.turn_revision,
        'accepted_job_id',prior.job_id,'message_id',prior.message_id,'outbox_id',prior.outbox_id,'send_job_id',prior.send_job_id);
        END IF;

        outcome:=CASE WHEN t.revision<>j.turn_revision THEN 'SUPERSEDED' ELSE
          platform.guard_require_current(j.workspace_id,t.id,rec.id,coalesce((j.turn_input->>'context_version')::bigint,conv.version)) END;
        PERFORM platform.messaging_guard(p_job,p_claim);
        IF outcome<>'CURRENT' THEN
          UPDATE platform.messaging_jobs SET status='SUCCEEDED',turn_outcome=outcome,error_code=NULL,
        claim_token=NULL,lease_until=NULL,worker_id=NULL,completed_at=clock_timestamp(),version=version+1 WHERE id=j.id;
          RETURN jsonb_build_object('code',outcome,'job_id',j.id,'turn_id',j.turn_id,'turn_revision',j.turn_revision,
        'accepted_job_id',prior.job_id,'message_id',prior.message_id,'outbox_id',prior.outbox_id,'send_job_id',prior.send_job_id);
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
      END $$"""
    ),
    "guard_turn_accept(4)": (
        r"""CREATE OR REPLACE FUNCTION platform.guard_turn_accept(p_job uuid,p_claim uuid,p_digest text,p_text text) RETURNS jsonb
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
"""
        "        \n"
        r"""        SELECT * INTO STRICT t FROM app.conversation_turns WHERE workspace_id=j.workspace_id AND id=target_turn;
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
        "        \n"
        r"""        SELECT * INTO prior FROM platform.turn_guard_receipts g WHERE g.workspace_id=j.workspace_id AND g.turn_id=j.turn_id AND g.outcome='ACCEPTED';
        IF FOUND THEN
          outcome:='ALREADY_ACCEPTED'; UPDATE platform.messaging_jobs SET status='SUCCEEDED',turn_outcome=outcome,error_code=NULL,
        claim_token=NULL,lease_until=NULL,worker_id=NULL,completed_at=clock_timestamp(),version=version+1 WHERE id=j.id;
          RETURN jsonb_build_object('code',outcome,'job_id',j.id,'turn_id',j.turn_id,'turn_revision',j.turn_revision,
        'accepted_job_id',prior.job_id,'message_id',prior.message_id,'outbox_id',prior.outbox_id,'send_job_id',prior.send_job_id);
        END IF;

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
        UPDATE platform.messaging_jobs SET status='SUCCEEDED',turn_outcome=outcome,error_code=NULL,
        claim_token=NULL,lease_until=NULL,worker_id=NULL,completed_at=clock_timestamp(),version=version+1 WHERE id=j.id;
        RETURN jsonb_build_object('code',r.outcome,'workspace_id',r.workspace_id,'job_id',r.job_id,
        'connection_id',r.connection_id,'conversation_id',r.conversation_id,'client_id',r.client_id,
        'turn_id',r.turn_id,'turn_revision',r.turn_revision,'resume_receipt_id',r.resume_receipt_id,
        'input_control_generation',r.input_control_generation,'activation_fence_seq',r.activation_fence_seq,
        'input_context_version',r.input_context_version,'snapshot_digest',r.snapshot_digest,'consumer',r.consumer,
        'request_fingerprint',encode(r.request_fingerprint,'hex'),'result_text',r.result_text,'accepted_at',r.accepted_at,
        'intent_context_version',r.intent_context_version,'message_id',r.message_id,'outbox_id',r.outbox_id,'send_job_id',r.send_job_id);
      END $$"""
    ),
    "guard_send_begin(2)": (
        r"""CREATE OR REPLACE FUNCTION platform.guard_send_begin(p_job uuid,p_claim uuid) RETURNS jsonb
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
"""
        "        \n"
        r"""        SELECT * INTO STRICT t FROM app.conversation_turns WHERE workspace_id=j.workspace_id AND id=target_turn;
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
      END $$"""
    ),
    "escalation_request_for_turn(2)": r"""CREATE OR REPLACE FUNCTION platform.escalation_request_for_turn(p_job uuid,p_claim uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE j platform.messaging_jobs%ROWTYPE; t app.conversation_turns%ROWTYPE; c app.conversations%ROWTYPE;
        r platform.conversation_control_receipts%ROWTYPE; e app.escalations%ROWTYPE;
        ws uuid; p_turn uuid; outcome text; prior uuid; allowed boolean; owner_live boolean; moment timestamptz;
      BEGIN
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
            owner_live IS NOT TRUE OR NOT (EXISTS(SELECT 1 FROM app.conversation_turn_messages tm JOIN app.messages m
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
        IF outcome IS NOT NULL THEN
          UPDATE platform.messaging_jobs SET status='SUCCEEDED',turn_outcome=outcome,error_code=NULL,
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
        -- Increment first; the material trigger sees no new pending request yet.
        UPDATE app.conversations SET version=version+1 WHERE workspace_id=ws AND id=c.id;
        INSERT INTO app.escalations SELECT e.*;
        INSERT INTO platform.messaging_jobs(workspace_id,connection_id,kind,escalation_id,step,available_at,correlation_id)
          VALUES(ws,e.connection_id,'ESCALATION_TIMER',e.id,'REMIND_1',e.due_at,j.correlation_id),
                (ws,e.connection_id,'ESCALATION_TIMER',e.id,'REMIND_2',e.second_reminder_at,j.correlation_id),
                (ws,e.connection_id,'ESCALATION_TIMER',e.id,'EXPIRE',e.expires_at,j.correlation_id);
        PERFORM platform.messaging_guard(p_job,p_claim);
        UPDATE platform.messaging_jobs SET status='SUCCEEDED',turn_outcome='ESCALATED',error_code=NULL,
          claim_token=NULL,lease_until=NULL,worker_id=NULL,completed_at=clock_timestamp(),version=version+1 WHERE id=j.id;
        RETURN e.creation_result;
      END $$""",
    "escalation_command(9)": r"""CREATE OR REPLACE FUNCTION platform.escalation_command(p_escalation uuid,p_conversation uuid,p_client uuid,p_operation text,p_key text,
      p_version bigint,p_generation bigint,p_context bigint,p_answer text) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE ws uuid; actor uuid; corr uuid; c app.conversations%ROWTYPE; e app.escalations%ROWTYPE;
        saved platform.escalation_command_receipts%ROWTYPE; fingerprint bytea; result jsonb;
        validity text; moment timestamptz; receipt uuid; audit uuid; accepted text;
      BEGIN
        PERFORM platform.turn_require_isolation(); ws:=app.current_messaging_owner_workspace_id();
        actor:=nullif(current_setting('asm.actor_id',true),'')::uuid;
        IF ws IS NULL OR platform.messaging_lock_owner(ws,actor) IS NOT TRUE THEN RAISE EXCEPTION 'ACCESS_DENIED' USING ERRCODE='P2501'; END IF;
        corr:=nullif(current_setting('asm.correlation_id',true),'')::uuid;
        IF p_escalation IS NULL OR p_conversation IS NULL OR p_client IS NULL OR p_key IS NULL OR p_key !~ '^[A-Za-z0-9._:-]{1,128}$' OR
          p_operation IS NULL OR p_operation NOT IN ('RESOLVE','CANCEL') OR p_version IS NULL OR p_version<=0 OR
          p_generation IS NULL OR p_generation<=0 OR p_context IS NULL OR p_context<=0 OR
          (p_operation='CANCEL' AND p_answer IS NOT NULL) OR
          (p_operation='RESOLVE' AND (p_answer IS NULL OR char_length(p_answer) NOT BETWEEN 1 AND 512 OR octet_length(p_answer)>2048 OR btrim(p_answer,chr(9)||chr(10)||chr(11)||chr(12)||chr(13)||chr(28)||chr(29)||chr(30)||chr(31)||chr(32)||chr(133)||chr(160)||chr(5760)||chr(8192)||chr(8193)||chr(8194)||chr(8195)||chr(8196)||chr(8197)||chr(8198)||chr(8199)||chr(8200)||chr(8201)||chr(8202)||chr(8232)||chr(8233)||chr(8239)||chr(8287)||chr(12288))='')) THEN
          RAISE EXCEPTION 'INVALID_REQUEST' USING ERRCODE='P2501'; END IF;
        PERFORM pg_advisory_xact_lock(hashtextextended('escalation-decision:'||ws::text||':'||p_key,0));
        IF NOT EXISTS(SELECT 1 FROM app.escalations WHERE workspace_id=ws AND id=p_escalation AND conversation_id=p_conversation AND client_id=p_client) THEN
          RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P2501'; END IF;
        fingerprint:=platform.escalation_command_fingerprint(ws,actor,p_escalation,p_conversation,p_client,p_operation,p_version,p_generation,p_context,p_answer);
        SELECT * INTO saved FROM platform.escalation_command_receipts WHERE workspace_id=ws AND namespace='ESCALATION_DECISION_V1' AND idempotency_key=p_key;
        IF FOUND THEN
          IF saved.request_fingerprint IS DISTINCT FROM fingerprint THEN RAISE EXCEPTION 'IDEMPOTENCY_KEY_CONFLICT' USING ERRCODE='P2501'; END IF;
          RETURN jsonb_build_object('code','REPLAY','result',saved.result,'request_fingerprint',encode(saved.request_fingerprint,'hex'));
        END IF;
        SELECT * INTO STRICT c FROM app.conversations WHERE workspace_id=ws AND id=p_conversation FOR NO KEY UPDATE;
        SELECT * INTO STRICT e FROM app.escalations WHERE workspace_id=ws AND id=p_escalation FOR NO KEY UPDATE;
        IF (e.conversation_id,e.client_id,c.client_id) IS DISTINCT FROM (p_conversation,p_client,p_client) THEN
          RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P2501'; END IF;
        IF e.status='EXPIRED' THEN RAISE EXCEPTION 'ESCALATION_EXPIRED' USING ERRCODE='P2501';
        ELSIF e.status<>'PENDING' THEN RAISE EXCEPTION 'ESCALATION_FINAL' USING ERRCODE='P2501'; END IF;
        moment:=platform.escalation_now(); validity:=platform.escalation_validity(ws,e.id,moment);
        IF validity IN ('CONTROL_CHANGED','CONTEXT_CHANGED') THEN RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P2501'; END IF;
        IF moment>=e.expires_at THEN RAISE EXCEPTION 'ESCALATION_EXPIRED' USING ERRCODE='P2501'; END IF;
        IF p_operation='RESOLVE' AND (e.assignee_user_account_id<>actor OR validity<>'CURRENT') THEN RAISE EXCEPTION 'ACCESS_DENIED' USING ERRCODE='P2501'; END IF;
        IF (e.version,c.control_generation,c.version) IS DISTINCT FROM (p_version,p_generation,p_context) THEN RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P2501'; END IF;
        IF c.version=9223372036854775807 THEN RAISE EXCEPTION 'VERSION_EXHAUSTED' USING ERRCODE='P2501'; END IF;
        accepted:=CASE p_operation WHEN 'RESOLVE' THEN 'RESOLVED' ELSE 'CANCELLED' END;
        receipt:=uuidv7();
        UPDATE app.escalations SET status=accepted,version=2,answer_text=p_answer,completed_at=moment,decided_by_user_account_id=actor,
          closure_reason=CASE WHEN p_operation='CANCEL' THEN 'OWNER_CANCELLED' END WHERE workspace_id=ws AND id=e.id;
        INSERT INTO app.audit_events(workspace_id,actor_kind,actor_user_account_id,correlation_id,event_type,object_type,object_id,object_version,payload)
          VALUES(ws,'USER_ACCOUNT',actor,corr,'ESCALATION_DECIDED','ESCALATION',e.id,2,jsonb_build_object('operation',p_operation,'status',accepted))
          RETURNING audit_event_id INTO audit;
        result:=jsonb_build_object('workspace_id',ws,'escalation_id',e.id,'conversation_id',e.conversation_id,'client_id',e.client_id,
          'receipt_id',receipt,'audit_event_id',audit,'operation',p_operation,'accepted_status',accepted,'previous_version',e.version::text,
          'accepted_version','2','accepted_context_version',(c.version+1)::text,'control_generation',c.control_generation::text,'accepted_at',to_char(moment AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'));
        INSERT INTO platform.escalation_command_receipts(workspace_id,id,idempotency_key,escalation_id,conversation_id,client_id,
          actor_user_account_id,correlation_id,operation,expected_version,expected_control_generation,expected_context_version,
          accepted_version,accepted_status,accepted_context_version,request_fingerprint,audit_event_id,accepted_at,result)
          VALUES(ws,receipt,p_key,e.id,e.conversation_id,e.client_id,actor,corr,p_operation,p_version,p_generation,p_context,
            2,accepted,c.version+1,fingerprint,audit,moment,result);
        UPDATE app.conversations SET version=version+1 WHERE workspace_id=ws AND id=c.id;
        RETURN jsonb_build_object('code','ACCEPTED','result',result,'request_fingerprint',encode(fingerprint,'hex'));
      END $$""",
    "escalation_read(1)": r"""CREATE OR REPLACE FUNCTION platform.escalation_read(p_escalation uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE ws uuid; actor uuid; result jsonb;
      BEGIN
        PERFORM platform.turn_require_isolation(); ws:=app.current_messaging_owner_workspace_id();
        actor:=nullif(current_setting('asm.actor_id',true),'')::uuid;
        IF ws IS NULL OR platform.messaging_lock_owner(ws,actor) IS NOT TRUE THEN RAISE EXCEPTION 'ACCESS_DENIED' USING ERRCODE='P2501'; END IF;
        WITH clock AS MATERIALIZED (SELECT platform.escalation_now() AS moment)
          SELECT jsonb_build_object(
      'workspace_id',e.workspace_id,'escalation_id',e.id,'conversation_id',e.conversation_id,'client_id',e.client_id,
      'turn_id',e.turn_id,'assignee_user_account_id',e.assignee_user_account_id,
      'reason',e.reason,'question',e.question,'policy',e.policy,'version',e.version::text,'status',e.status,
      'bound_context',jsonb_build_object('turn_revision',e.turn_revision::text,'control_generation',e.control_generation::text,
        'context_version',e.waiting_context_version::text,'fingerprint',encode(e.context_fingerprint,'hex')),
      'current_context',jsonb_build_object('control_mode',c.control_mode,'control_generation',c.control_generation::text,'context_version',c.version::text),
      'validity',v.validity,'waiting',CASE WHEN e.status='PENDING' AND v.validity='CURRENT' THEN 'WAITING_FOR_HUMAN' END,
      'created_at',to_char(e.created_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),'due_at',to_char(e.due_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),'second_reminder_at',to_char(e.second_reminder_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
      'expires_at',to_char(e.expires_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),'observed_at',to_char(clock.moment AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
      'reminders',jsonb_build_array(
        jsonb_build_object('ordinal',1,'due_at',to_char(e.due_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),'recorded_at',to_char(e.first_reminded_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"')),
        jsonb_build_object('ordinal',2,'due_at',to_char(e.second_reminder_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),'recorded_at',to_char(e.second_reminded_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'))),
      'maintenance',CASE WHEN EXISTS(SELECT 1 FROM platform.messaging_jobs j WHERE j.workspace_id=e.workspace_id AND j.escalation_id=e.id AND j.status='DEAD') THEN 'FAILED'
        WHEN (SELECT count(*) FROM platform.messaging_jobs j WHERE j.workspace_id=e.workspace_id AND j.escalation_id=e.id AND j.status='SUCCEEDED')=3 THEN 'COMPLETE' ELSE 'SCHEDULED' END,
      'resolution',CASE WHEN e.status='RESOLVED' THEN jsonb_build_object('answer_text',e.answer_text,'actor_user_account_id',e.decided_by_user_account_id,'completed_at',to_char(e.completed_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"')) END,
      'closure',CASE WHEN e.status IN ('CANCELLED','EXPIRED') THEN jsonb_build_object('reason',e.closure_reason,'actor_user_account_id',e.decided_by_user_account_id,'completed_at',to_char(e.completed_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"')) END,
      'can_resolve',e.status='PENDING' AND v.validity='CURRENT' AND e.assignee_user_account_id=actor,
      'can_cancel',e.status='PENDING' AND v.validity IN ('CURRENT','ASSIGNEE_REVOKED') AND clock.moment<e.expires_at) INTO result FROM app.escalations e JOIN app.conversations c ON (c.workspace_id,c.id)=(e.workspace_id,e.conversation_id)
      CROSS JOIN clock CROSS JOIN LATERAL (SELECT platform.escalation_validity(e.workspace_id,e.id,clock.moment) AS validity) v WHERE e.workspace_id=ws AND e.id=p_escalation;
        IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P2501'; END IF;
        RETURN result;
      END $$""",
    "escalation_list(4)": r"""CREATE OR REPLACE FUNCTION platform.escalation_list(p_count integer,p_status text,p_at timestamptz,p_id uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE ws uuid; actor uuid; result jsonb;
      BEGIN
        PERFORM platform.turn_require_isolation(); ws:=app.current_messaging_owner_workspace_id();
        actor:=nullif(current_setting('asm.actor_id',true),'')::uuid;
        IF ws IS NULL OR platform.messaging_lock_owner(ws,actor) IS NOT TRUE THEN RAISE EXCEPTION 'ACCESS_DENIED' USING ERRCODE='P2501'; END IF;
        IF p_count IS NULL OR p_count NOT BETWEEN 1 AND 101 OR p_status IS NULL OR p_status NOT IN ('PENDING','RESOLVED','CANCELLED','EXPIRED','ALL') OR
          ((p_at IS NULL)<>(p_id IS NULL)) OR (p_at IS NOT NULL AND (NOT isfinite(p_at) OR NOT EXISTS(
            SELECT 1 FROM app.escalations WHERE workspace_id=ws AND id=p_id AND created_at=p_at))) THEN
          RAISE EXCEPTION 'INVALID_REQUEST' USING ERRCODE='P2501'; END IF;
        WITH clock AS MATERIALIZED (SELECT platform.escalation_now() AS moment), items AS (
          SELECT jsonb_build_object(
      'workspace_id',e.workspace_id,'escalation_id',e.id,'conversation_id',e.conversation_id,'client_id',e.client_id,
      'turn_id',e.turn_id,'assignee_user_account_id',e.assignee_user_account_id,
      'reason',e.reason,'question',e.question,'policy',e.policy,'version',e.version::text,'status',e.status,
      'bound_context',jsonb_build_object('turn_revision',e.turn_revision::text,'control_generation',e.control_generation::text,
        'context_version',e.waiting_context_version::text,'fingerprint',encode(e.context_fingerprint,'hex')),
      'current_context',jsonb_build_object('control_mode',c.control_mode,'control_generation',c.control_generation::text,'context_version',c.version::text),
      'validity',v.validity,'waiting',CASE WHEN e.status='PENDING' AND v.validity='CURRENT' THEN 'WAITING_FOR_HUMAN' END,
      'created_at',to_char(e.created_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),'due_at',to_char(e.due_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),'second_reminder_at',to_char(e.second_reminder_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
      'expires_at',to_char(e.expires_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),'observed_at',to_char(clock.moment AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
      'reminders',jsonb_build_array(
        jsonb_build_object('ordinal',1,'due_at',to_char(e.due_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),'recorded_at',to_char(e.first_reminded_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"')),
        jsonb_build_object('ordinal',2,'due_at',to_char(e.second_reminder_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),'recorded_at',to_char(e.second_reminded_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'))),
      'maintenance',CASE WHEN EXISTS(SELECT 1 FROM platform.messaging_jobs j WHERE j.workspace_id=e.workspace_id AND j.escalation_id=e.id AND j.status='DEAD') THEN 'FAILED'
        WHEN (SELECT count(*) FROM platform.messaging_jobs j WHERE j.workspace_id=e.workspace_id AND j.escalation_id=e.id AND j.status='SUCCEEDED')=3 THEN 'COMPLETE' ELSE 'SCHEDULED' END,
      'resolution',CASE WHEN e.status='RESOLVED' THEN jsonb_build_object('answer_text',e.answer_text,'actor_user_account_id',e.decided_by_user_account_id,'completed_at',to_char(e.completed_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"')) END,
      'closure',CASE WHEN e.status IN ('CANCELLED','EXPIRED') THEN jsonb_build_object('reason',e.closure_reason,'actor_user_account_id',e.decided_by_user_account_id,'completed_at',to_char(e.completed_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"')) END,
      'can_resolve',e.status='PENDING' AND v.validity='CURRENT' AND e.assignee_user_account_id=actor,
      'can_cancel',e.status='PENDING' AND v.validity IN ('CURRENT','ASSIGNEE_REVOKED') AND clock.moment<e.expires_at) AS value,e.created_at,e.id FROM app.escalations e JOIN app.conversations c ON (c.workspace_id,c.id)=(e.workspace_id,e.conversation_id)
      CROSS JOIN clock CROSS JOIN LATERAL (SELECT platform.escalation_validity(e.workspace_id,e.id,clock.moment) AS validity) v
          WHERE e.workspace_id=ws AND (p_status='ALL' OR e.status=p_status) AND (p_at IS NULL OR (e.created_at,e.id)<(p_at,p_id))
          ORDER BY e.created_at DESC,e.id DESC LIMIT p_count)
          SELECT jsonb_build_object(
            'items',(SELECT coalesce(jsonb_agg(value ORDER BY created_at DESC,id DESC),'[]'::jsonb) FROM items),
            'observed_at',to_char(clock.moment AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"')) INTO result FROM clock;
        RETURN result;
      END $$""",
    "escalation_immutable(0)": r"""CREATE OR REPLACE FUNCTION platform.escalation_immutable() RETURNS trigger
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
          (SELECT m.id AS message_id,m.conversation_id,m.direction,m.content_type,m.text,m.occurred_at,m.created_at,m.version::text AS version,platform.message_effective(ws,m.id) AS current,
            CASE WHEN f.id IS NOT NULL THEN jsonb_build_object('file_id',f.id,'status',f.status,'error_code',f.error_code,'manifest',
              CASE WHEN f.status='READY' THEN jsonb_build_object('mime_type',f.mime_type,'size_bytes',f.size_bytes::text,'width',f.width,'height',f.height) END) END AS file,
            CASE WHEN b.id IS NOT NULL THEN jsonb_build_object('status',b.status,'error_code',b.error_code,'completed_at',b.completed_at,'version',b.version::text) END AS delivery
            FROM app.messages m LEFT JOIN app.file_objects f ON f.workspace_id=m.workspace_id AND f.message_id=m.id
            LEFT JOIN app.outbox_events b ON b.workspace_id=m.workspace_id AND b.message_id=m.id
            WHERE m.workspace_id=ws AND m.conversation_id=p_conversation AND (p_id IS NULL OR (m.created_at,m.id)<(p_at,p_id)) ORDER BY m.created_at DESC,m.id DESC LIMIT p_limit) items;
        RETURN result;
      END $$""",
    "messaging_claim(4)": r"""CREATE OR REPLACE FUNCTION platform.messaging_claim(p_worker text,p_until timestamptz,p_at timestamptz,p_id uuid) RETURNS jsonb
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
      END $$""",
    "messaging_reschedule(5)": r"""CREATE OR REPLACE FUNCTION platform.messaging_reschedule(p_job uuid,p_error text,p_retry boolean,p_delay integer,p_nowait boolean) RETURNS jsonb
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
        ELSIF j.kind='PROCESS_TURN' AND j.step NOT IN ('GUARDED_TEXT','ESCALATE_OWNER') AND NOT retry THEN
          UPDATE app.conversation_turns SET state='FAILED',error_code=final_error,revision=revision+1 WHERE workspace_id=j.workspace_id AND id=j.turn_id;
        END IF;
        UPDATE platform.messaging_jobs SET status=CASE WHEN retry THEN 'READY' ELSE 'DEAD' END,
          claim_token=NULL,lease_until=NULL,worker_id=NULL,error_code=final_error,available_at=due,
          turn_outcome=CASE WHEN kind='PROCESS_TURN' AND NOT retry THEN 'FAILED' END,
          completed_at=CASE WHEN retry THEN NULL ELSE clock_timestamp() END,version=version+1 WHERE id=j.id;
        RETURN jsonb_build_object('code',CASE WHEN retry THEN 'RETRY_SCHEDULED' ELSE final_error END,'status',coalesce(delivery,CASE WHEN retry THEN 'READY' ELSE 'DEAD' END),'job_id',j.id,'outbox_id',j.outbox_id);
      END $$""",
    "turn_supersede(1)": (
        r"""CREATE OR REPLACE FUNCTION platform.turn_supersede(j platform.messaging_jobs) RETURNS boolean
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$ DECLARE timer_e app.escalations%ROWTYPE; timer_moment timestamptz; timer_due timestamptz;
        timer_validity text; timer_outcome text; timer_error text; timer_recorded timestamptz;
        fault_schema text; fault_table text; fault_constraint text; BEGIN
        IF j.kind='ESCALATION_TIMER' THEN"""
        " \n"
        r"""        SELECT * INTO STRICT timer_e FROM app.escalations WHERE workspace_id=j.workspace_id AND id=j.escalation_id;
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
"""
        "          \n"
        r"""          END IF;
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
          WHERE workspace_id=j.workspace_id AND id=j.turn_id AND (revision<>j.turn_revision OR (j.step NOT IN ('GROUP','MEDIA') AND platform.material_turn_usable(j.workspace_id,id) IS NOT TRUE))) THEN
          UPDATE platform.messaging_jobs SET status='SUCCEEDED',turn_outcome='SUPERSEDED',error_code=NULL,
            attempt_count=greatest(1,attempt_count),first_started_at=coalesce(first_started_at,clock_timestamp()),
            claim_token=NULL,lease_until=NULL,worker_id=NULL,completed_at=clock_timestamp(),version=version+1 WHERE id=j.id;
          RETURN true;
        END IF; RETURN false;
      END $$"""
    ),
    "turn_preflight(3)": r"""CREATE OR REPLACE FUNCTION platform.turn_preflight(j platform.messaging_jobs,p_nowait boolean,p_terminal boolean) RETURNS void
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
}

OLD_AUDIT_CHECK = (
    r"""
      (
"""
    "      \n"
    r"""      (event_type='WORKSPACE_BILLING_PROVISIONED' AND
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
        payload IN ('{"operation":"RESOLVE","status":"RESOLVED"}'::jsonb,'{"operation":"CANCEL","status":"CANCELLED"}'::jsonb)) IS TRUE)) OR ((event_type='MESSAGE_MATERIAL_CHANGED' AND actor_kind='CHANNEL_EVENT'
        AND actor_user_account_id IS NULL AND object_type='MESSAGE' AND material_target_id IS NOT NULL AND material_source_receipt_id IS NOT NULL
        AND platform.material_object(payload,ARRAY['target_id','source_receipt_id','previous_version','accepted_version','reason'])
        AND payload->>'target_id'=material_target_id::text AND payload->>'source_receipt_id'=material_source_receipt_id::text
        AND jsonb_typeof(payload->'previous_version')='string' AND jsonb_typeof(payload->'accepted_version')='string'
        AND platform.telegram_numeric_id(payload->>'previous_version') AND platform.telegram_numeric_id(payload->>'accepted_version')
        AND (payload->>'previous_version')::numeric+1=object_version AND payload->>'accepted_version'=object_version::text
        AND payload->>'reason' IN ('CONTENT_CHANGED','DELETED','ORDER_UNCERTAIN','ORDER_RESTORED','UNSUPPORTED_CONTENT')) IS TRUE)"""
)

TABLES = (
    "platform.human_context_observations",
    "platform.human_context_reconciliations",
    "platform.human_context_policy_receipts",
)
FUNCTIONS = {}


def _define(sql: str) -> None:
    match = re.search(r"FUNCTION ([a-z0-9_.]+)\((.*?)\)\s+RETURNS", sql, re.S)
    assert match, sql[:120]
    args = []
    for part in match[2].split(",") if match[2].strip() else []:
        words = part.strip().split()
        args.append(words[1])
    signature = match[1] + "(" + ",".join(args) + ")"
    FUNCTIONS[signature] = sql
    op.execute(sql)


def _replace(name: str, *changes: tuple[str, str]) -> None:
    sql = ORIGINAL[name]
    for before, after in changes:
        assert before in sql, (name, before)
        sql = sql.replace(before, after)
    _define(sql)


PUBLIC_FUNCTIONS = (
    "platform.human_context_read(uuid)",
    "platform.human_context_observations(uuid,integer,jsonb)",
    "platform.human_context_reconcile(uuid,text,jsonb)",
    "platform.human_context_work_replay(uuid,uuid)",
)
PERMANENT_REASONS = (
    "CONTEXT_POLICY_PAUSED",
    "CONTEXT_CONFIRMATION_REQUIRED",
    "CONTEXT_UNRESOLVED",
    "NEW_OBSERVATION",
    "CONTEXT_INPUT_UNRESOLVED",
    "CONTEXT_COVERAGE_REQUIRED",
    "CONTEXT_TOO_LARGE",
)
WHITESPACE = "||".join(
    f"chr({n})"
    for n in (
        9,
        10,
        11,
        12,
        13,
        28,
        29,
        30,
        31,
        32,
        133,
        160,
        5760,
        8192,
        8193,
        8194,
        8195,
        8196,
        8197,
        8198,
        8199,
        8200,
        8201,
        8202,
        8232,
        8233,
        8239,
        8287,
        12288,
    )
)
RELEVANT = "normalized_event->>'kind' IN ('CLIENT_MESSAGE','MESSAGE_EDITED','MESSAGE_DELETED')"
UNSEQUENCED = "((normalized_event->>'kind'='CLIENT_MESSAGE' AND turn_ingress_seq IS NULL) OR (normalized_event->>'kind' IN ('MESSAGE_EDITED','MESSAGE_DELETED') AND human_context_observation_id IS NULL))"


def _primitives() -> None:
    _define(r"""CREATE FUNCTION platform.human_context_hash(prefix text,parts text[]) RETURNS bytea
      LANGUAGE sql IMMUTABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      SELECT sha256(convert_to(prefix||coalesce(string_agg(CASE WHEN v IS NULL THEN E'-1:\n'
        ELSE octet_length(convert_to(v,'UTF8'))::text||':'||v||E'\n' END,'' ORDER BY n),''),'UTF8'))
      FROM unnest(parts) WITH ORDINALITY AS a(v,n) $$""")
    _define(f"""CREATE FUNCTION platform.human_context_text_valid(value text) RETURNS boolean
      LANGUAGE sql IMMUTABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      SELECT value IS NOT NULL AND char_length(value) BETWEEN 1 AND 4096
        AND octet_length(value)<=16384 AND btrim(value,{WHITESPACE})<>'' $$""")
    _define(r"""CREATE FUNCTION platform.human_context_decimal(value jsonb,positive boolean) RETURNS boolean
      LANGUAGE sql IMMUTABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      SELECT CASE WHEN jsonb_typeof(value)='string' AND value#>>'{}' ~ '^(0|[1-9][0-9]{0,18})$'
        THEN (value#>>'{}')::numeric BETWEEN CASE WHEN positive THEN 1 ELSE 0 END AND 9223372036854775807
        ELSE false END $$""")
    _define(r"""CREATE FUNCTION platform.human_context_uuid(value jsonb) RETURNS boolean
      LANGUAGE sql IMMUTABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      SELECT coalesce(jsonb_typeof(value)='string' AND value#>>'{}' ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',false) $$""")


def _schema() -> None:
    op.execute("""LOCK TABLE app.channel_connections,app.conversations,app.audit_events,
      platform.conversation_control_receipts,platform.inbox_events,platform.messaging_jobs,
      platform.telegram_provenance IN ACCESS EXCLUSIVE MODE""")
    op.execute("""ALTER TABLE app.channel_connections
      ADD COLUMN human_context_policy text NOT NULL DEFAULT 'OFF_UNUSED',
      ADD COLUMN human_context_policy_epoch bigint NOT NULL DEFAULT 0,
      ADD CONSTRAINT native_connection_binding_key UNIQUE(workspace_id,id,business_id,provider,bot_identity,external_connection_id),
      ADD CONSTRAINT native_policy_check CHECK(((human_context_policy='OFF_UNUSED' AND human_context_policy_epoch=0)
        OR (human_context_policy IN ('ON','PAUSED') AND human_context_policy_epoch>0)) IS TRUE);
      ALTER TABLE app.conversations ADD COLUMN human_observation_epoch bigint,
      ADD COLUMN human_context_revision_id uuid,
      ADD CONSTRAINT native_conversation_epoch_check CHECK(human_observation_epoch IS NULL OR human_observation_epoch>=0),
      ADD CONSTRAINT native_conversation_pointer_check CHECK(human_context_revision_id IS NULL OR human_observation_epoch IS NOT NULL),
      ADD CONSTRAINT native_conversation_identity_key UNIQUE(workspace_id,id,client_id,connection_id,provider_chat_id);
      ALTER TABLE platform.telegram_provenance ADD COLUMN human_context_observation_id uuid,
      ADD CONSTRAINT native_source_link_check CHECK((human_context_observation_id IS NULL OR (workspace_id IS NOT NULL AND connection_id IS NOT NULL)) IS TRUE);
      ALTER TABLE platform.inbox_events ADD COLUMN human_context_source_receipt_id uuid,
      ADD COLUMN human_context_observation_id uuid,
      ADD CONSTRAINT native_inbox_link_check CHECK(human_context_observation_id IS NULL OR human_context_source_receipt_id IS NOT NULL);
      ALTER TABLE platform.conversation_control_receipts ADD COLUMN human_context_revision_id uuid,
      ADD COLUMN human_context_policy_epoch bigint, ADD COLUMN human_observation_epoch bigint,
      ADD CONSTRAINT native_control_link_check CHECK(((human_context_revision_id IS NULL AND human_context_policy_epoch IS NULL AND human_observation_epoch IS NULL)
        OR (operation='RESUME' AND human_context_revision_id IS NOT NULL AND human_context_policy_epoch IS NOT NULL
          AND human_context_policy_epoch>0 AND human_observation_epoch IS NOT NULL AND human_observation_epoch>=0)) IS TRUE);
      ALTER TABLE platform.messaging_jobs ADD COLUMN context_block_reason text,
      ADD COLUMN context_wait_claim_token uuid, ADD COLUMN context_wait_result jsonb""")
    op.execute("""CREATE TABLE platform.human_context_observations(
      workspace_id uuid NOT NULL,id uuid NOT NULL DEFAULT uuidv7(),conversation_id uuid NOT NULL,client_id uuid NOT NULL,
      connection_id uuid NOT NULL,provider_chat_id text NOT NULL,epoch bigint NOT NULL CHECK(epoch>0),
      policy_epoch bigint NOT NULL CHECK(policy_epoch>0),control_generation bigint NOT NULL CHECK(control_generation>0),
      first_source_receipt_id uuid NOT NULL,classification text NOT NULL CHECK(classification IN
        ('NATIVE_CANDIDATE','AMBIGUOUS_NONCLIENT','CANONICAL_MUTATION','UNBOUND_MUTATION')),
      semantic_digest bytea NOT NULL CHECK(octet_length(semantic_digest)=32),accepted_at timestamptz NOT NULL CHECK(isfinite(accepted_at)),
      PRIMARY KEY(workspace_id,id),UNIQUE(workspace_id,conversation_id,epoch),UNIQUE(workspace_id,conversation_id,semantic_digest),
      UNIQUE(workspace_id,conversation_id,client_id,id),UNIQUE(workspace_id,id,connection_id),
      FOREIGN KEY(workspace_id,conversation_id,client_id,connection_id,provider_chat_id)
        REFERENCES app.conversations(workspace_id,id,client_id,connection_id,provider_chat_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,first_source_receipt_id) REFERENCES platform.telegram_provenance(workspace_id,receipt_id)
        ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED)
      """)
    op.execute("""ALTER TABLE app.audit_events
      ADD COLUMN native_revision_id uuid GENERATED ALWAYS AS
        (CASE WHEN event_type='HUMAN_CONTEXT_RECONCILED' THEN (payload->>'revision_id')::uuid END) STORED,
      ADD COLUMN native_policy_receipt_id uuid GENERATED ALWAYS AS
        (CASE WHEN event_type='HUMAN_CONTEXT_POLICY_COMMANDED' THEN (payload->>'receipt_id')::uuid END) STORED,
      ADD COLUMN native_connection_id uuid GENERATED ALWAYS AS
        (CASE WHEN event_type='HUMAN_CONTEXT_POLICY_COMMANDED' THEN object_id END) STORED,
      ADD COLUMN native_conversation_id uuid GENERATED ALWAYS AS
        (CASE WHEN event_type='HUMAN_CONTEXT_RECONCILED' THEN object_id END) STORED,
      ADD CONSTRAINT native_audit_conversation_fkey FOREIGN KEY(workspace_id,native_conversation_id)
        REFERENCES app.conversations(workspace_id,id) ON DELETE RESTRICT,
      ADD CONSTRAINT native_audit_connection_fkey FOREIGN KEY(workspace_id,native_connection_id)
        REFERENCES app.channel_connections(workspace_id,id) ON DELETE RESTRICT,
      ADD CONSTRAINT native_audit_revision_key UNIQUE(workspace_id,audit_event_id,object_id,event_type,object_version,actor_user_account_id,native_revision_id),
      ADD CONSTRAINT native_audit_policy_key UNIQUE(workspace_id,audit_event_id,object_id,event_type,object_version,native_policy_receipt_id),
      DROP CONSTRAINT audit_events_discriminator_payload_check""")
    op.execute(f"""ALTER TABLE app.audit_events ADD CONSTRAINT audit_events_discriminator_payload_check CHECK(
      ({OLD_AUDIT_CHECK}) OR ((event_type='HUMAN_CONTEXT_RECONCILED' AND actor_kind='USER_ACCOUNT'
        AND actor_user_account_id IS NOT NULL AND object_type='CONVERSATION' AND object_version>1
        AND native_revision_id IS NOT NULL AND native_conversation_id IS NOT NULL
        AND platform.material_object(payload,ARRAY['revision_id','previous_revision_id','disposition','source_media',
          'control_generation','previous_context_version','accepted_context_version','policy_epoch','observation_epoch','reviewed_ingress_checkpoint'])
        AND payload->>'revision_id'=native_revision_id::text
        AND (payload->'previous_revision_id'='null'::jsonb OR platform.human_context_uuid(payload->'previous_revision_id'))
        AND payload->>'disposition' IN ('OWNER_TEXT','CANONICAL_SUFFICIENT','UNRESOLVED')
        AND payload->>'source_media' IN ('NONE','UNAVAILABLE')
        AND platform.human_context_decimal(payload->'control_generation',true)
        AND platform.human_context_decimal(payload->'previous_context_version',true)
        AND platform.human_context_decimal(payload->'accepted_context_version',true)
        AND (payload->>'accepted_context_version')::numeric=(payload->>'previous_context_version')::numeric+1
        AND payload->>'accepted_context_version'=object_version::text
        AND platform.human_context_decimal(payload->'policy_epoch',true)
        AND platform.human_context_decimal(payload->'observation_epoch',false)
        AND platform.human_context_decimal(payload->'reviewed_ingress_checkpoint',false)) IS TRUE)
      OR ((event_type='HUMAN_CONTEXT_POLICY_COMMANDED' AND actor_kind='LOCAL_PROVISIONER' AND actor_user_account_id IS NULL
        AND object_type='CHANNEL_CONNECTION' AND object_version>0 AND native_policy_receipt_id IS NOT NULL AND native_connection_id IS NOT NULL
        AND platform.material_object(payload,ARRAY['receipt_id','operation','change','previous_policy','accepted_policy','previous_policy_epoch','accepted_policy_epoch'])
        AND payload->>'receipt_id'=native_policy_receipt_id::text AND payload->>'operation' IN ('ENABLE','PAUSE')
        AND payload->>'change' IN ('ENABLED','PAUSED','UNCHANGED') AND payload->>'previous_policy' IN ('OFF_UNUSED','ON','PAUSED')
        AND payload->>'accepted_policy' IN ('ON','PAUSED')
        AND platform.human_context_decimal(payload->'previous_policy_epoch',false)
        AND platform.human_context_decimal(payload->'accepted_policy_epoch',true)
        AND payload->>'accepted_policy_epoch'=object_version::text) IS TRUE))""")
    op.execute("""CREATE TABLE platform.human_context_reconciliations(
      workspace_id uuid NOT NULL,id uuid NOT NULL DEFAULT uuidv7(),conversation_id uuid NOT NULL,client_id uuid NOT NULL,
      connection_id uuid NOT NULL,provider_chat_id text NOT NULL,actor_user_account_id uuid NOT NULL,
      namespace text NOT NULL DEFAULT 'HUMAN_CONTEXT_RECONCILE_V1' CHECK(namespace='HUMAN_CONTEXT_RECONCILE_V1'),
      idempotency_key text NOT NULL CHECK(idempotency_key ~ '^[A-Za-z0-9._:-]{1,128}$'),
      request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32),correlation_id uuid NOT NULL,
      previous_revision_id uuid,revision_no bigint NOT NULL CHECK(revision_no>0),expected_generation bigint NOT NULL CHECK(expected_generation>0),
      expected_context_version bigint NOT NULL CHECK(expected_context_version BETWEEN 1 AND 9223372036854775806),
      accepted_context_version bigint NOT NULL CHECK(accepted_context_version::numeric=expected_context_version::numeric+1),
      policy_epoch bigint NOT NULL CHECK(policy_epoch>0),observation_epoch bigint NOT NULL CHECK(observation_epoch>=0),
      reviewed_ingress_seq bigint NOT NULL CHECK(reviewed_ingress_seq>=0),reviewed_input_state_hash text NOT NULL CHECK(reviewed_input_state_hash ~ '^[0-9a-f]{64}$'),
      reviewed_gap_digest bytea CHECK(octet_length(reviewed_gap_digest)=32),reviewed_gap_overflow boolean NOT NULL,
      disposition text NOT NULL CHECK(disposition IN ('OWNER_TEXT','CANONICAL_SUFFICIENT','UNRESOLVED')),context_text text,
      source_media text NOT NULL CHECK(source_media IN ('NONE','UNAVAILABLE')),
      attestation text NOT NULL CHECK(attestation='REVIEWED_AVAILABLE_CONTEXT'),
      audit_event_id uuid NOT NULL,event_type text NOT NULL DEFAULT 'HUMAN_CONTEXT_RECONCILED' CHECK(event_type='HUMAN_CONTEXT_RECONCILED'),
      accepted_at timestamptz NOT NULL CHECK(isfinite(accepted_at)),result jsonb NOT NULL,
      PRIMARY KEY(workspace_id,id),UNIQUE(workspace_id,namespace,idempotency_key),UNIQUE(workspace_id,conversation_id,revision_no),
      UNIQUE(workspace_id,conversation_id,client_id,id),
      UNIQUE(workspace_id,conversation_id,client_id,id,expected_generation,accepted_context_version,policy_epoch,observation_epoch),
      FOREIGN KEY(workspace_id,conversation_id,client_id,connection_id,provider_chat_id)
        REFERENCES app.conversations(workspace_id,id,client_id,connection_id,provider_chat_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,actor_user_account_id) REFERENCES platform.workspace_memberships(workspace_id,user_account_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,conversation_id,client_id,previous_revision_id)
        REFERENCES platform.human_context_reconciliations(workspace_id,conversation_id,client_id,id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,audit_event_id,conversation_id,event_type,accepted_context_version,actor_user_account_id,id)
        REFERENCES app.audit_events(workspace_id,audit_event_id,object_id,event_type,object_version,actor_user_account_id,native_revision_id) ON DELETE RESTRICT,
      CHECK(((NOT reviewed_gap_overflow AND reviewed_gap_digest IS NOT NULL) OR (reviewed_gap_overflow AND reviewed_gap_digest IS NULL)) IS TRUE),
      CHECK(((disposition='CANONICAL_SUFFICIENT' AND context_text IS NULL AND source_media='NONE')
        OR (disposition='OWNER_TEXT' AND platform.human_context_text_valid(context_text))
        OR (disposition='UNRESOLVED' AND (context_text IS NULL OR platform.human_context_text_valid(context_text)))) IS TRUE))""")
    op.execute("""CREATE TABLE platform.human_context_policy_receipts(
      workspace_id uuid NOT NULL,id uuid NOT NULL DEFAULT uuidv7(),connection_id uuid NOT NULL,business_id uuid NOT NULL,
      provider text NOT NULL CHECK(provider IN ('CONTROLLED','TELEGRAM')),bot_identity text NOT NULL,external_connection_id text NOT NULL,owner_user_id text,
      actor_db_role text NOT NULL CHECK(actor_db_role='asm_migrator'),
      namespace text NOT NULL DEFAULT 'HUMAN_CONTEXT_POLICY_V1' CHECK(namespace='HUMAN_CONTEXT_POLICY_V1'),
      idempotency_key text NOT NULL CHECK(idempotency_key ~ '^[A-Za-z0-9._:-]{1,128}$'),
      request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32),operation text NOT NULL CHECK(operation IN ('ENABLE','PAUSE')),
      expected_policy text NOT NULL CHECK(expected_policy IN ('OFF_UNUSED','ON','PAUSED')),expected_policy_epoch bigint NOT NULL CHECK(expected_policy_epoch>=0),
      accepted_policy text NOT NULL CHECK(accepted_policy IN ('ON','PAUSED')),accepted_policy_epoch bigint NOT NULL CHECK(accepted_policy_epoch>0),
      change text NOT NULL CHECK(change IN ('ENABLED','PAUSED','UNCHANGED')),source_profile jsonb NOT NULL,
      audit_event_id uuid NOT NULL,event_type text NOT NULL DEFAULT 'HUMAN_CONTEXT_POLICY_COMMANDED' CHECK(event_type='HUMAN_CONTEXT_POLICY_COMMANDED'),
      accepted_at timestamptz NOT NULL CHECK(isfinite(accepted_at)),result jsonb NOT NULL,
      PRIMARY KEY(workspace_id,id),UNIQUE(workspace_id,namespace,idempotency_key),
      FOREIGN KEY(workspace_id,connection_id,business_id,provider,bot_identity,external_connection_id)
        REFERENCES app.channel_connections(workspace_id,id,business_id,provider,bot_identity,external_connection_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,audit_event_id,connection_id,event_type,accepted_policy_epoch,id)
        REFERENCES app.audit_events(workspace_id,audit_event_id,object_id,event_type,object_version,native_policy_receipt_id) ON DELETE RESTRICT,
      CHECK(((provider='CONTROLLED' AND owner_user_id IS NULL) OR (provider='TELEGRAM' AND owner_user_id IS NOT NULL AND platform.telegram_numeric_id(owner_user_id))) IS TRUE),
      CONSTRAINT native_policy_receipt_transition_check CHECK(((operation='ENABLE' AND accepted_policy='ON' AND
        ((expected_policy='OFF_UNUSED' AND expected_policy_epoch=0 AND accepted_policy_epoch=1 AND change='ENABLED') OR
         (expected_policy='PAUSED' AND expected_policy_epoch>0 AND accepted_policy_epoch::numeric=expected_policy_epoch::numeric+1 AND change='ENABLED') OR
         (expected_policy='ON' AND expected_policy_epoch>0 AND accepted_policy_epoch=expected_policy_epoch AND change='UNCHANGED')))
        OR (operation='PAUSE' AND accepted_policy='PAUSED' AND expected_policy_epoch>0 AND accepted_policy_epoch=expected_policy_epoch AND
          ((expected_policy='ON' AND change='PAUSED') OR (expected_policy='PAUSED' AND change='UNCHANGED')))) IS TRUE))""")
    op.execute("""ALTER TABLE app.conversations ADD CONSTRAINT native_conversation_revision_fkey
      FOREIGN KEY(workspace_id,id,client_id,human_context_revision_id)
      REFERENCES platform.human_context_reconciliations(workspace_id,conversation_id,client_id,id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;
      ALTER TABLE platform.conversation_control_receipts ADD CONSTRAINT native_control_revision_fkey
      FOREIGN KEY(workspace_id,conversation_id,client_id,human_context_revision_id,previous_generation,context_version,human_context_policy_epoch,human_observation_epoch)
      REFERENCES platform.human_context_reconciliations(workspace_id,conversation_id,client_id,id,expected_generation,accepted_context_version,policy_epoch,observation_epoch) ON DELETE RESTRICT;
      ALTER TABLE platform.telegram_provenance ADD CONSTRAINT native_source_observation_fkey
      FOREIGN KEY(workspace_id,human_context_observation_id,connection_id)
      REFERENCES platform.human_context_observations(workspace_id,id,connection_id) ON DELETE RESTRICT;
      ALTER TABLE platform.inbox_events ADD CONSTRAINT native_inbox_source_fkey
      FOREIGN KEY(workspace_id,human_context_source_receipt_id) REFERENCES platform.telegram_provenance(workspace_id,receipt_id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
      ADD CONSTRAINT native_inbox_observation_fkey FOREIGN KEY(workspace_id,human_context_observation_id,connection_id)
      REFERENCES platform.human_context_observations(workspace_id,id,connection_id) ON DELETE RESTRICT;
      CREATE INDEX native_source_observation_idx ON platform.telegram_provenance(workspace_id,human_context_observation_id,receipt_id)
        WHERE human_context_observation_id IS NOT NULL;
      CREATE INDEX native_job_work_idx ON platform.messaging_jobs(workspace_id,turn_id,context_block_reason,available_at,id)
        WHERE context_block_reason IS NOT NULL""")
    for label, predicate, suffix in (
        (
            "checkpoint",
            "normalized_event->>'kind'='CLIENT_MESSAGE' AND turn_ingress_seq IS NOT NULL",
            "turn_ingress_seq DESC",
        ),
        ("pending", f"status='PENDING' AND {RELEVANT}", "id"),
        ("failed", f"status='FAILED' AND {RELEVANT}", "id"),
        ("unsequenced", f"status<>'PENDING' AND {RELEVANT} AND {UNSEQUENCED}", "id"),
    ):
        op.execute(
            f"CREATE INDEX native_inbox_{label}_idx ON platform.inbox_events(workspace_id,connection_id,(normalized_event->>'chat_id'),{suffix}) WHERE {predicate}"
        )
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} OWNER TO asm_migrator")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY native_migrator ON {table} TO asm_migrator USING(true) WITH CHECK(true)"
        )
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC,asm_runtime")
        op.execute(
            f"CREATE TRIGGER native_immutable BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION platform.turn_immutable()"
        )


def _projection() -> None:
    _define(r"""CREATE FUNCTION platform.human_context_revision_json(r platform.human_context_reconciliations) RETURNS jsonb
      LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      SELECT CASE WHEN r.id IS NULL THEN NULL ELSE jsonb_build_object('revision_id',r.id,'revision_no',r.revision_no::text,
        'previous_revision_id',r.previous_revision_id,'actor_user_account_id',r.actor_user_account_id,
        'accepted_at',to_char(r.accepted_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
        'disposition',r.disposition,'text',r.context_text,'source_media',r.source_media,'coverage','OWNER_ASSERTED_TEXT_ONLY',
        'confirmed_generation',r.expected_generation::text,'accepted_context_version',r.accepted_context_version::text,
        'policy_epoch',r.policy_epoch::text,'observation_epoch',r.observation_epoch::text,
        'reviewed_ingress_checkpoint',r.reviewed_ingress_seq::text,'reviewed_input_state_hash',r.reviewed_input_state_hash) END $$""")
    _define(r"""CREATE FUNCTION platform.human_context_effective(m app.messages,material jsonb,file_status text) RETURNS jsonb
      LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      WITH state AS (SELECT coalesce(material,jsonb_build_object('state','VISIBLE','content',CASE WHEN m.content_type='TEXT'
        THEN jsonb_build_object('kind','TEXT','text',m.text) ELSE jsonb_build_object('kind','PHOTO','caption',m.text,'selected_file_id',m.image_file_id) END)) AS v),
      content AS (SELECT v,CASE WHEN v->>'state'='VISIBLE' THEN v->'content' END AS c FROM state)
      SELECT jsonb_build_object('schema_version',1,'state',v->>'state','content_type',c->>'kind',
        'text',CASE WHEN c->>'kind'='TEXT' THEN c->>'text' ELSE c->>'caption' END,
        'image_availability',CASE WHEN v->>'state'<>'VISIBLE' THEN 'HIDDEN' WHEN c->>'kind'='TEXT' THEN 'NOT_APPLICABLE'
          WHEN c->>'selected_file_id' IS DISTINCT FROM m.image_file_id THEN 'MEDIA_REPLACED_UNAVAILABLE'
          WHEN file_status IS NULL THEN 'ORIGINAL_NOT_FETCHED' ELSE 'ORIGINAL_'||file_status END,'changed',m.version>1) FROM content $$""")
    _define(f"""CREATE FUNCTION platform.human_context_projection(ws uuid,p_conversation uuid,p_clock timestamptz) RETURNS jsonb
      LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      WITH scope AS MATERIALIZED (
        SELECT c.*,cc.human_context_policy AS policy,cc.human_context_policy_epoch AS p
        FROM app.conversations c JOIN app.channel_connections cc ON (cc.workspace_id,cc.id)=(c.workspace_id,c.connection_id)
        WHERE c.workspace_id=ws AND c.id=p_conversation),
      revision AS MATERIALIZED (SELECT r.* FROM scope c JOIN platform.human_context_reconciliations r
        ON (r.workspace_id,r.id,r.conversation_id,r.client_id)=(c.workspace_id,c.human_context_revision_id,c.id,c.client_id)),
      activation AS MATERIALIZED (SELECT r.* FROM scope c JOIN platform.conversation_control_receipts r
        ON (r.workspace_id,r.conversation_id,r.client_id,r.accepted_generation)=(c.workspace_id,c.id,c.client_id,c.control_generation)
        WHERE r.operation='RESUME'),
      last_activation AS MATERIALIZED (SELECT r.human_observation_epoch AS n FROM scope c
        JOIN platform.conversation_control_receipts r ON (r.workspace_id,r.conversation_id,r.client_id)=(c.workspace_id,c.id,c.client_id)
        WHERE r.operation='RESUME' ORDER BY r.accepted_generation DESC LIMIT 1),
      tail AS MATERIALIZED (SELECT m.* FROM scope c JOIN app.messages m ON (m.workspace_id,m.conversation_id)=(c.workspace_id,c.id)
        ORDER BY m.created_at DESC,m.id DESC LIMIT 17),
      recent AS MATERIALIZED (SELECT jsonb_agg(value ORDER BY created_at,id) AS items FROM (
        SELECT m.created_at,m.id,jsonb_build_object('message_id',m.id,'version',m.version::text,'direction',m.direction,
          'origin',CASE WHEN m.direction='INBOUND' THEN 'CLIENT_INBOUND' WHEN b.kind='SEND_MANUAL_TEXT' THEN 'OWNER_MANUAL'
            WHEN b.kind='SEND_GUARDED_TEXT' THEN 'CONTROLLED_AUTOMATION' ELSE 'LEGACY_UNATTRIBUTED' END,
          'created_at',to_char(m.created_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
          'current',platform.human_context_effective(m,mt.current_material,f.status),
          'delivery',CASE WHEN b.id IS NOT NULL THEN jsonb_build_object('status',b.status,'error_code',b.error_code,'completed_at',b.completed_at,'version',b.version::text) END,
          'file',CASE WHEN f.id IS NOT NULL THEN jsonb_build_object('file_id',f.id,'version',f.version::text,'status',f.status) END) AS value
        FROM (SELECT * FROM tail ORDER BY created_at DESC,id DESC LIMIT 16) m
        LEFT JOIN platform.message_material_targets mt ON (mt.workspace_id,mt.message_id)=(m.workspace_id,m.id)
        LEFT JOIN app.file_objects f ON (f.workspace_id,f.message_id)=(m.workspace_id,m.id)
        LEFT JOIN app.outbox_events b ON (b.workspace_id,b.message_id)=(m.workspace_id,m.id)) q),
      checkpoint AS MATERIALIZED (SELECT coalesce((SELECT i.turn_ingress_seq FROM scope c JOIN platform.inbox_events i
        ON (i.workspace_id,i.connection_id,i.normalized_event->>'chat_id')=(c.workspace_id,c.connection_id,c.provider_chat_id)
        WHERE i.normalized_event->>'kind'='CLIENT_MESSAGE' AND i.turn_ingress_seq IS NOT NULL ORDER BY i.turn_ingress_seq DESC LIMIT 1),0) AS seq),
      flags AS MATERIALIZED (SELECT
        EXISTS(SELECT 1 FROM scope c JOIN platform.inbox_events i ON (i.workspace_id,i.connection_id,i.normalized_event->>'chat_id')=
          (c.workspace_id,c.connection_id,c.provider_chat_id) WHERE i.status='PENDING' AND i.{RELEVANT}) AS pending,
        EXISTS(SELECT 1 FROM scope c JOIN platform.inbox_events i ON (i.workspace_id,i.connection_id,i.normalized_event->>'chat_id')=
          (c.workspace_id,c.connection_id,c.provider_chat_id) WHERE i.status='FAILED' AND i.{RELEVANT}) AS failed,
        EXISTS(SELECT 1 FROM scope c JOIN platform.inbox_events i ON (i.workspace_id,i.connection_id,i.normalized_event->>'chat_id')=
          (c.workspace_id,c.connection_id,c.provider_chat_id) WHERE i.status<>'PENDING' AND i.{RELEVANT} AND {UNSEQUENCED}) AS unsequenced),
      failed_probe AS MATERIALIZED (SELECT i.id FROM scope c JOIN platform.inbox_events i
        ON (i.workspace_id,i.connection_id,i.normalized_event->>'chat_id')=(c.workspace_id,c.connection_id,c.provider_chat_id)
        WHERE i.status='FAILED' AND i.{RELEVANT} ORDER BY i.id LIMIT 1025),
      unsequenced_probe AS MATERIALIZED (SELECT i.id FROM scope c JOIN platform.inbox_events i
        ON (i.workspace_id,i.connection_id,i.normalized_event->>'chat_id')=(c.workspace_id,c.connection_id,c.provider_chat_id)
        WHERE i.status<>'PENDING' AND i.{RELEVANT} AND {UNSEQUENCED} ORDER BY i.id LIMIT 1025),
      gap_probe AS MATERIALIZED (SELECT id FROM (SELECT id FROM failed_probe UNION SELECT id FROM unsequenced_probe) q ORDER BY id LIMIT 1025),
      gap AS MATERIALIZED (SELECT count(*) AS size,CASE WHEN count(*)>1024 THEN NULL ELSE sha256(convert_to(E'asm:m3:human_context_gaps:v1\n'||
        coalesce(jsonb_agg(jsonb_build_array(i.id,coalesce(i.human_context_source_receipt_id,s.receipt_id),i.normalized_event->>'kind',i.status,i.result_code,
          i.turn_ingress_seq::text,i.human_context_observation_id) ORDER BY i.id),'[]'::jsonb)::text,'UTF8')) END AS digest
        FROM gap_probe g CROSS JOIN scope c JOIN platform.inbox_events i ON (i.workspace_id,i.id)=(c.workspace_id,g.id)
        LEFT JOIN platform.telegram_provenance s ON (s.workspace_id,s.inbox_id)=(i.workspace_id,i.id)),
      input AS MATERIALIZED (SELECT encode(platform.human_context_hash(E'asm:m3:human_context_input:v1\n',ARRAY[
        c.workspace_id::text,c.id::text,c.client_id::text,c.connection_id::text,c.provider_chat_id,cp.seq::text,fl.pending::text,
        encode(g.digest,'hex'),(g.size>1024)::text]),'hex') AS hash FROM scope c CROSS JOIN checkpoint cp CROSS JOIN flags fl CROSS JOIN gap g),
      observations AS MATERIALIZED (SELECT
        EXISTS(SELECT 1 FROM platform.human_context_observations o CROSS JOIN scope c
          WHERE (o.workspace_id,o.conversation_id)=(c.workspace_id,c.id) AND o.epoch>coalesce((SELECT n FROM last_activation),0)
          AND o.classification<>'CANONICAL_MUTATION') AS noncanonical,
        EXISTS(SELECT 1 FROM platform.human_context_observations o JOIN platform.telegram_provenance s ON (s.workspace_id,s.receipt_id)=(o.workspace_id,o.first_source_receipt_id)
          CROSS JOIN scope c WHERE (o.workspace_id,o.conversation_id)=(c.workspace_id,c.id)
          AND o.epoch>coalesce((SELECT n FROM last_activation),0) AND s.projection->'content'->>'kind' IN ('PHOTO','UNSUPPORTED')) AS unavailable),
      state AS MATERIALIZED (SELECT c.*,r.id AS rid,r.disposition,r.observation_epoch AS rn,r.expected_generation AS rg,
        r.accepted_context_version AS rv,r.policy_epoch AS rp,r.reviewed_ingress_seq AS rseq,r.reviewed_gap_digest,
        a.id AS resume_id,a.accepted_generation AS ag,a.activation_fence_seq AS af,a.human_context_revision_id AS ar,
        a.human_context_policy_epoch AS ap,coalesce(c.human_observation_epoch,0) AS n,cp.seq,fl.*,g.size,g.digest,i.hash,
        (SELECT count(*) FROM tail)>16 AS truncated,
        CASE WHEN r.id IS NULL THEN 'UNCONFIRMED' WHEN r.disposition='UNRESOLVED' THEN 'UNRESOLVED'
          WHEN r.disposition='OWNER_TEXT' THEN 'OWNER_TEXT' WHEN (SELECT count(*) FROM tail)>16 THEN 'CANONICAL_TRUNCATED' ELSE 'CANONICAL_COMPLETE' END AS coverage,
        g.size>1024 OR (g.size>0 AND NOT coalesce(r.disposition='OWNER_TEXT' AND r.reviewed_gap_digest=g.digest,false)) AS unreviewed
        FROM scope c LEFT JOIN revision r ON true LEFT JOIN activation a ON true CROSS JOIN checkpoint cp CROSS JOIN flags fl CROSS JOIN gap g CROSS JOIN input i),
      blockers AS MATERIALIZED (SELECT coalesce(jsonb_agg(reason ORDER BY ordinal),'[]'::jsonb) AS value FROM state s CROSS JOIN LATERAL (VALUES
        (1,'POLICY_INACTIVE',s.policy='OFF_UNUSED'),(2,'POLICY_PAUSED',s.policy='PAUSED'),
        (3,'CONTEXT_CONFIRMATION_REQUIRED',s.policy<>'OFF_UNUSED' AND s.rid IS NULL),
        (4,'CONTEXT_CHANGED',s.policy<>'OFF_UNUSED' AND s.rid IS NOT NULL AND ((s.control_mode='HUMAN' AND
          (s.rg,s.rv,s.rp,s.rseq) IS DISTINCT FROM (s.control_generation,s.version,s.p,s.seq)) OR (s.control_mode='AI' AND
          (s.rg::numeric+1,s.ag,s.af,s.ar,s.rp,s.ap) IS DISTINCT FROM (s.control_generation::numeric,s.control_generation,s.activation_fence_seq,s.rid,s.p,s.p)))),
        (5,'CONTEXT_UNRESOLVED',s.policy<>'OFF_UNUSED' AND s.disposition='UNRESOLVED'),
        (6,'NEW_OBSERVATION',s.policy<>'OFF_UNUSED' AND s.rid IS NOT NULL AND s.rn<>s.n),
        (7,'CONTEXT_INPUT_UNRESOLVED',s.policy<>'OFF_UNUSED' AND s.unreviewed),
        (8,'CONTEXT_COVERAGE_REQUIRED',s.policy<>'OFF_UNUSED' AND s.coverage='CANONICAL_TRUNCATED'),
        (9,'CONTEXT_INPUT_PENDING',s.policy<>'OFF_UNUSED' AND s.pending)) q(ordinal,reason,applies) WHERE applies),
      work AS MATERIALIZED (SELECT j.id,j.context_block_reason,j.status,t.id AS turn_id FROM state s
        JOIN app.conversation_turns t ON (t.workspace_id,t.conversation_id,t.control_generation)=(s.workspace_id,s.id,s.control_generation)
        JOIN platform.messaging_jobs j ON (j.workspace_id,j.turn_id)=(t.workspace_id,t.id)
        WHERE j.context_block_reason IS NOT NULL AND j.step IN ('TEST_CONSUME','GUARDED_TEXT','ESCALATE_OWNER')
        UNION ALL SELECT j.id,j.context_block_reason,j.status,r.turn_id FROM state s JOIN platform.turn_guard_receipts r
          ON (r.workspace_id,r.conversation_id,r.client_id,r.input_control_generation)=(s.workspace_id,s.id,s.client_id,s.control_generation)
          JOIN platform.messaging_jobs j ON (j.workspace_id,j.id)=(r.workspace_id,r.send_job_id) WHERE j.context_block_reason IS NOT NULL),
      selected_work AS MATERIALIZED (SELECT w.* FROM work w JOIN platform.messaging_jobs j ON j.id=w.id
        ORDER BY (w.context_block_reason<>'CONTEXT_INPUT_PENDING' OR w.status='DEAD') DESC,coalesce(j.completed_at,j.available_at) DESC,j.id DESC LIMIT 1)
      SELECT jsonb_build_object('workspace_id',s.workspace_id,'conversation_id',s.id,'client_id',s.client_id,
        'observed_at',to_char(p_clock AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),'control_mode',s.control_mode,
        'control_generation',s.control_generation::text,'context_version',s.version::text,'policy',s.policy,'policy_epoch',s.p::text,
        'observation_epoch',s.n::text,'ingress_checkpoint',s.seq::text,'input_state_hash',s.hash,
        'input_gap_limit_exceeded',s.size>1024,'has_unsequenced_context_input',s.unsequenced,
        'current_revision',(SELECT platform.human_context_revision_json(r) FROM revision r),
        'review_status',CASE b.value->>0 WHEN 'POLICY_INACTIVE' THEN 'POLICY_INACTIVE' WHEN 'POLICY_PAUSED' THEN 'POLICY_PAUSED'
          WHEN 'CONTEXT_CONFIRMATION_REQUIRED' THEN 'BOOTSTRAP_REQUIRED' WHEN 'CONTEXT_CHANGED' THEN 'CONFIRMATION_REQUIRED'
          WHEN 'CONTEXT_UNRESOLVED' THEN 'UNRESOLVED' WHEN 'NEW_OBSERVATION' THEN 'NEW_OBSERVATION'
          WHEN 'CONTEXT_INPUT_UNRESOLVED' THEN 'INPUT_UNRESOLVED' WHEN 'CONTEXT_COVERAGE_REQUIRED' THEN 'COVERAGE_REQUIRED'
          WHEN 'CONTEXT_INPUT_PENDING' THEN 'INPUT_PENDING' ELSE 'CONFIRMED' END,
        'context_blockers',b.value,'resume_blockers',CASE WHEN s.policy='OFF_UNUSED' THEN '[]'::jsonb ELSE
          (SELECT coalesce(jsonb_agg(v ORDER BY n),'[]'::jsonb) FROM (
            SELECT value AS v,ordinality*2 AS n FROM jsonb_array_elements(b.value) WITH ORDINALITY
            UNION ALL SELECT to_jsonb('HUMAN_REQUIRED'::text),5 WHERE s.control_mode='AI') q) END,
        'history_truncated',s.truncated,'coverage_status',s.coverage,'pending_context_input',s.pending,
        'has_failed_context_input',s.failed,'unreviewed_failed_context_input',s.failed AND s.unreviewed,
        'automation_work',coalesce((SELECT jsonb_build_object('state',CASE WHEN status='DEAD' OR context_block_reason<>'CONTEXT_INPUT_PENDING' THEN 'OPERATOR_REQUIRED' ELSE 'WAITING_CONTEXT' END,
          'reason',context_block_reason,'job_id',id,'turn_id',turn_id,'observed_at',to_char(p_clock AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"')) FROM selected_work),
          jsonb_build_object('state','IDLE','reason',NULL,'job_id',NULL,'turn_id',NULL,'observed_at',to_char(p_clock AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'))),
        'manual_delivery',jsonb_build_object('has_dispatching',EXISTS(SELECT 1 FROM app.outbox_events bx JOIN app.messages m ON (m.workspace_id,m.id)=(bx.workspace_id,bx.message_id)
          WHERE (m.workspace_id,m.conversation_id)=(s.workspace_id,s.id) AND bx.kind='SEND_MANUAL_TEXT' AND bx.status='DISPATCHING'),
          'has_unknown',EXISTS(SELECT 1 FROM app.outbox_events bx JOIN app.messages m ON (m.workspace_id,m.id)=(bx.workspace_id,bx.message_id)
          WHERE (m.workspace_id,m.conversation_id)=(s.workspace_id,s.id) AND bx.kind='SEND_MANUAL_TEXT' AND bx.status='UNKNOWN')),
        '_gap_digest',encode(s.digest,'hex'),'_gap_count',s.size,'_noncanonical',o.noncanonical,'_unavailable',o.unavailable,
        '_recent_messages',coalesce(recent.items,'[]'::jsonb),'_resume_receipt_id',s.resume_id)
      FROM state s CROSS JOIN blockers b CROSS JOIN observations o CROSS JOIN recent $$""")
    _define(r"""CREATE FUNCTION platform.human_context_turn_projection(ws uuid,p_turn uuid,p_clock timestamptz) RETURNS jsonb
      LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      WITH scope AS MATERIALIZED (SELECT t.*,c.version AS context_version,c.client_id,c.business_id,
        cc.human_context_policy AS policy,platform.human_context_projection(ws,c.id,p_clock) AS context
        FROM app.conversation_turns t JOIN app.conversations c ON (c.workspace_id,c.id)=(t.workspace_id,t.conversation_id)
        JOIN app.channel_connections cc ON (cc.workspace_id,cc.id)=(c.workspace_id,c.connection_id)
        WHERE t.workspace_id=ws AND t.id=p_turn AND t.state='READY'),
      members AS MATERIALIZED (SELECT jsonb_agg(jsonb_build_object('message_id',m.id,'message_version',m.version,'content_type',m.content_type,
        'membership_form',tm.membership_form,'initial_suppression_id',tm.initial_suppression_id,
        'current',platform.human_context_effective(m,mt.current_material,f.status),'ingress_at',tm.turn_ingress_at,'ingress_seq',tm.turn_ingress_seq,
        'file',CASE WHEN f.id IS NULL THEN NULL ELSE jsonb_build_object('file_id',f.id,'version',f.version,'status',f.status,'error_code',f.error_code,'wait_expired',f.status='PENDING') END)
        ORDER BY tm.turn_ingress_at,tm.turn_ingress_seq,tm.message_id) AS value
        FROM app.conversation_turn_messages tm JOIN app.messages m ON (m.workspace_id,m.id)=(tm.workspace_id,tm.message_id)
        LEFT JOIN platform.message_material_targets mt ON (mt.workspace_id,mt.message_id)=(m.workspace_id,m.id)
        LEFT JOIN app.file_objects f ON (f.workspace_id,f.id)=(tm.workspace_id,tm.file_id) WHERE tm.workspace_id=ws AND tm.turn_id=p_turn),
      body AS (SELECT jsonb_build_object('schema_version',CASE WHEN s.policy='OFF_UNUSED' THEN 2 ELSE 3 END,
        'workspace_id',ws,'connection_id',s.connection_id,'turn_id',s.id,'turn_revision',s.revision,'context_version',s.context_version,
        'control_generation',s.control_generation,'readiness',CASE WHEN s.policy<>'OFF_UNUSED' AND s.context->'current_revision'->>'source_media'='UNAVAILABLE' THEN 'PARTIAL' ELSE s.readiness END,'members',m.value)
        || CASE WHEN s.policy='OFF_UNUSED' THEN '{}'::jsonb ELSE jsonb_build_object(
          'human_context',s.context->'current_revision','context_policy_epoch',s.context->>'policy_epoch',
          'human_observation_epoch',s.context->>'observation_epoch','resume_receipt_id',s.context->'_resume_receipt_id',
          'recent_messages',s.context->'_recent_messages','history_truncated',s.context->'history_truncated',
          'coverage_status',s.context->>'coverage_status','context_coverage','OWNER_ASSERTED_TEXT_ONLY',
          'context_limitations',CASE WHEN s.context->'current_revision'->>'source_media'='UNAVAILABLE'
            THEN '["PROVIDER_HISTORY_UNVERIFIED","NATIVE_MEDIA_UNAVAILABLE"]'::jsonb ELSE '["PROVIDER_HISTORY_UNVERIFIED"]'::jsonb END) END AS v
        FROM scope s CROSS JOIN members m WHERE m.value IS NOT NULL)
      SELECT v||jsonb_build_object('snapshot_digest',encode(sha256(convert_to(v::text,'UTF8')),'hex')) FROM body $$""")
    _define(r"""CREATE FUNCTION platform.human_context_reason(projection jsonb,resume boolean) RETURNS text
      LANGUAGE sql IMMUTABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      SELECT CASE coalesce((CASE WHEN resume THEN projection->'resume_blockers' ELSE projection->'context_blockers' END)->>0,'CURRENT')
        WHEN 'POLICY_INACTIVE' THEN 'CURRENT' WHEN 'POLICY_PAUSED' THEN 'CONTEXT_POLICY_PAUSED'
        WHEN 'CONTEXT_CHANGED' THEN 'CONTEXT_CONFIRMATION_REQUIRED' ELSE
        coalesce((CASE WHEN resume THEN projection->'resume_blockers' ELSE projection->'context_blockers' END)->>0,'CURRENT') END $$""")


def _observation() -> None:
    _define(r"""CREATE FUNCTION platform.human_context_observation_digest(ws uuid,c uuid,client uuid,conn uuid,p jsonb) RETURNS bytea
      LANGUAGE sql IMMUTABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      SELECT platform.human_context_hash(E'asm:m3:human_observation:v1\n',ARRAY[ws::text,c::text,client::text,conn::text,
        p->>'discriminator',p->>'chat_id',CASE WHEN p->>'discriminator'='DELETE' THEN
          (SELECT jsonb_agg(v ORDER BY v::bigint)::text FROM (SELECT DISTINCT value AS v FROM jsonb_array_elements_text(p->'legacy_v1'->'deleted_message_ids')) a)
          ELSE p->>'message_id' END,p->'origin'->>'sender_id',p->'origin'->>'sender_is_bot',
        p->'origin'->>'sender_business_bot_id',p->'origin'->>'offline',p->>'sent_at',p->>'edited_at',(p->'content')::text]) $$""")
    _define(r"""CREATE FUNCTION platform.human_context_preview(p jsonb) RETURNS jsonb
      LANGUAGE sql IMMUTABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      SELECT CASE WHEN p->>'discriminator'='DELETE' THEN jsonb_build_object('kind','DELETE','target_count',
        (SELECT count(DISTINCT v) FROM jsonb_array_elements_text(p->'legacy_v1'->'deleted_message_ids') a(v)))
        WHEN p->'content'->>'kind'='TEXT' AND char_length(p->'content'->>'text') BETWEEN 1 AND 4096 AND octet_length(p->'content'->>'text')<=16384
          THEN jsonb_build_object('kind','TEXT','text',p->'content'->>'text')
        WHEN p->'content'->>'kind'='PHOTO' AND (p->'content'->>'caption' IS NULL OR
          (char_length(p->'content'->>'caption')<=4096 AND octet_length(p->'content'->>'caption')<=16384))
          THEN jsonb_build_object('kind','PHOTO','caption',p->'content'->>'caption','image_availability','NATIVE_UNAVAILABLE')
        ELSE jsonb_build_object('kind','UNSUPPORTED','reason',CASE WHEN p->'content'->>'kind'='UNSUPPORTED' THEN 'UNSUPPORTED_CONTENT'
          ELSE 'UNAVAILABLE_PROJECTION' END) END $$""")
    _define(r"""CREATE FUNCTION platform.human_context_observe(source platform.telegram_update_receipts,p jsonb) RETURNS uuid
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE c app.conversations%ROWTYPE; connection app.channel_connections%ROWTYPE;
        mark platform.human_context_observations%ROWTYPE; digest bytea; classification text; identifiers text[];
      BEGIN
        IF source.codec IS DISTINCT FROM 2 OR source.workspace_id IS NULL OR p->>'discriminator' NOT IN ('NEW','EDIT','DELETE') THEN RETURN NULL; END IF;
        SELECT * INTO STRICT connection FROM app.channel_connections WHERE (workspace_id,id)=(source.workspace_id,source.connection_id);
        IF connection.human_context_policy='OFF_UNUSED' THEN RETURN NULL; END IF;
        IF p->>'discriminator'='NEW' THEN
          IF p->>'chat_type'<>'PRIVATE' OR p->'origin'->>'sender_business_bot_id' IS NOT NULL
            OR p->'origin'->>'sender_is_bot'='TRUE' OR p->'origin'->>'offline'='TRUE'
            OR EXISTS(SELECT 1 FROM app.messages m JOIN app.outbox_events b ON (b.workspace_id,b.message_id)=(m.workspace_id,m.id)
              WHERE (m.workspace_id,m.connection_id,m.provider_chat_id)=
                (source.workspace_id,source.connection_id,p->>'chat_id') AND b.provider_message_id=p->>'message_id' AND m.direction='OUTBOUND' AND b.status='SENT'
              AND p->'content'->>'kind'='TEXT' AND p->'content'->>'text'=m.text)
            OR (p->>'unsupported_reason'='NONE' AND p->'origin'->>'sender_id'=p->>'chat_id') THEN RETURN NULL; END IF;
        END IF;
        SELECT * INTO c FROM app.conversations WHERE workspace_id=source.workspace_id AND connection_id=source.connection_id
          AND provider_chat_id=p->>'chat_id' FOR NO KEY UPDATE;
        IF NOT FOUND THEN RETURN NULL; END IF;
        digest:=platform.human_context_observation_digest(c.workspace_id,c.id,c.client_id,c.connection_id,p);
        SELECT * INTO mark FROM platform.human_context_observations WHERE workspace_id=c.workspace_id AND conversation_id=c.id AND semantic_digest=digest;
        IF FOUND THEN RETURN mark.id; END IF;
        IF coalesce(c.human_observation_epoch,0)=9223372036854775807 THEN RAISE EXCEPTION 'VERSION_EXHAUSTED' USING ERRCODE='P2001'; END IF;
        IF p->>'discriminator'='NEW' THEN
          classification:=CASE WHEN p->'origin'->>'sender_id'=(SELECT owner_user_id FROM platform.telegram_connection_state
            WHERE workspace_id=c.workspace_id AND connection_id=c.connection_id) AND p->>'unsupported_reason' IN ('NONE','AMBIGUOUS_SENDER')
            THEN 'NATIVE_CANDIDATE' ELSE 'AMBIGUOUS_NONCLIENT' END;
        ELSE
          IF p->>'discriminator'='EDIT' THEN identifiers:=ARRAY[p->>'message_id']; ELSE
            SELECT array_agg(DISTINCT v) INTO identifiers FROM jsonb_array_elements_text(p->'legacy_v1'->'deleted_message_ids') a(v); END IF;
          classification:=CASE WHEN NOT EXISTS(SELECT 1 FROM unnest(identifiers) a(v) WHERE
            (SELECT count(*) FROM app.messages m LEFT JOIN app.outbox_events b ON (b.workspace_id,b.message_id)=(m.workspace_id,m.id)
              WHERE (m.workspace_id,m.conversation_id,m.connection_id,m.provider_chat_id)=(c.workspace_id,c.id,c.connection_id,c.provider_chat_id)
                AND ((m.direction='INBOUND' AND m.provider_message_id=v) OR (m.direction='OUTBOUND' AND b.status='SENT' AND b.provider_message_id=v))
                AND platform.material_identity(c.workspace_id,m.id,p) IS TRUE)<>1) THEN 'CANONICAL_MUTATION' ELSE 'UNBOUND_MUTATION' END;
        END IF;
        INSERT INTO platform.human_context_observations(workspace_id,conversation_id,client_id,connection_id,provider_chat_id,epoch,
          policy_epoch,control_generation,first_source_receipt_id,classification,semantic_digest,accepted_at)
          VALUES(c.workspace_id,c.id,c.client_id,c.connection_id,c.provider_chat_id,coalesce(c.human_observation_epoch,0)+1,
            connection.human_context_policy_epoch,c.control_generation,source.id,classification,digest,source.received_at) RETURNING * INTO mark;
        UPDATE app.conversations SET human_observation_epoch=mark.epoch WHERE workspace_id=c.workspace_id AND id=c.id;
        RETURN mark.id;
      END $$""")
    _replace(
        "telegram_ingest(3)",
        (
            "ELSIF e->>'sender_id'=s.owner_user_id THEN outcome:='IGNORED_NATIVE_OWNER_MESSAGE';",
            """ELSIF EXISTS(SELECT 1 FROM app.channel_connections cc WHERE (cc.workspace_id,cc.id)=(route.workspace_id,route.connection_id) AND cc.human_context_policy<>'OFF_UNUSED')
              AND EXISTS(SELECT 1 FROM app.messages m JOIN app.outbox_events b ON (b.workspace_id,b.message_id)=(m.workspace_id,m.id)
                WHERE (m.workspace_id,m.connection_id,m.provider_chat_id)=(route.workspace_id,route.connection_id,p->>'chat_id') AND b.provider_message_id=p->>'message_id'
                AND m.direction='OUTBOUND' AND b.status='SENT' AND p->'content'->>'kind'='TEXT' AND p->'content'->>'text'=m.text) THEN outcome:='IGNORED_ECHO';
            ELSIF EXISTS(SELECT 1 FROM app.channel_connections cc WHERE (cc.workspace_id,cc.id)=(route.workspace_id,route.connection_id) AND cc.human_context_policy<>'OFF_UNUSED')
              AND (p->'origin'->>'sender_is_bot'='TRUE' OR p->'origin'->>'offline'='TRUE') THEN outcome:='IGNORED_UNSUPPORTED';
            ELSIF e->>'sender_id'=s.owner_user_id THEN outcome:='IGNORED_NATIVE_OWNER_MESSAGE';""",
        ),
        ("outcome text; inbox uuid;", "outcome text; inbox uuid; observation uuid; used boolean;"),
        (
            "INSERT INTO platform.telegram_provenance(receipt_id,bot_identity,update_id,workspace_id,connection_id,inbox_id,projection,material_enabled)",
            "observation:=platform.human_context_observe(r,p);\n        used:=coalesce((SELECT human_context_policy<>'OFF_UNUSED' FROM app.channel_connections WHERE (workspace_id,id)=(r.workspace_id,r.connection_id)),false);\n        INSERT INTO platform.telegram_provenance(receipt_id,bot_identity,update_id,workspace_id,connection_id,inbox_id,projection,material_enabled,human_context_observation_id)",
        ),
        (
            "VALUES(r.id,p_bot,r.update_id,r.workspace_id,r.connection_id,r.inbox_id,p,enabled);",
            "VALUES(r.id,p_bot,r.update_id,r.workspace_id,r.connection_id,r.inbox_id,p,enabled,observation);\n        IF used AND r.inbox_id IS NOT NULL THEN UPDATE platform.inbox_events SET human_context_source_receipt_id=r.id,human_context_observation_id=observation WHERE (workspace_id,id)=(r.workspace_id,r.inbox_id); END IF;",
        ),
    )


def _owner_commands() -> None:
    _define(r"""CREATE FUNCTION platform.human_context_read(p_conversation uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE ws uuid; projection jsonb;
      BEGIN
        PERFORM platform.turn_require_isolation(); ws:=app.current_messaging_owner_workspace_id();
        IF ws IS NULL OR platform.messaging_lock_owner(ws,nullif(current_setting('asm.actor_id',true),'')::uuid) IS NOT TRUE THEN
          RAISE EXCEPTION 'ACCESS_DENIED' USING ERRCODE='P2401'; END IF;
        SELECT platform.human_context_projection(ws,p_conversation,clock_timestamp()) INTO projection;
        IF projection IS NULL THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P2401'; END IF;
        RETURN projection-ARRAY['_gap_digest','_gap_count','_noncanonical','_unavailable','_recent_messages','_resume_receipt_id'];
      END $$""")
    _define(r"""CREATE FUNCTION platform.human_context_observations(p_conversation uuid,p_limit integer,p_cursor jsonb) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE ws uuid; result jsonb; moment timestamptz;
      BEGIN
        PERFORM platform.turn_require_isolation(); ws:=app.current_messaging_owner_workspace_id();
        IF ws IS NULL OR platform.messaging_lock_owner(ws,nullif(current_setting('asm.actor_id',true),'')::uuid) IS NOT TRUE THEN
          RAISE EXCEPTION 'ACCESS_DENIED' USING ERRCODE='P2401'; END IF;
        IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 100 THEN RAISE EXCEPTION 'INVALID_REQUEST' USING ERRCODE='P2401'; END IF;
        IF p_cursor IS NOT NULL THEN
          IF platform.material_object(p_cursor,ARRAY['v','ws','C','Client','P','through_N','after_N']) IS NOT TRUE
            OR p_cursor->'v' IS DISTINCT FROM '1'::jsonb OR p_cursor->>'v'<>'1'
            OR NOT platform.human_context_uuid(p_cursor->'ws') OR NOT platform.human_context_uuid(p_cursor->'C')
            OR NOT platform.human_context_uuid(p_cursor->'Client') OR NOT platform.human_context_decimal(p_cursor->'P',false)
            OR NOT platform.human_context_decimal(p_cursor->'through_N',false) OR NOT platform.human_context_decimal(p_cursor->'after_N',false)
            THEN RAISE EXCEPTION 'INVALID_REQUEST' USING ERRCODE='P2401'; END IF;
          IF p_cursor->>'ws'<>ws::text THEN RAISE EXCEPTION 'ACCESS_DENIED' USING ERRCODE='P2401'; END IF;
        END IF;
        moment:=clock_timestamp();
        -- Cursor relation, epochs, source and page are evaluated in this ONE command snapshot.
        WITH relation AS MATERIALIZED (SELECT c.id,c.client_id,coalesce(c.human_observation_epoch,0) AS n,cc.human_context_policy_epoch AS p
          FROM app.conversations c JOIN app.channel_connections cc ON (cc.workspace_id,cc.id)=(c.workspace_id,c.connection_id)
          WHERE c.workspace_id=ws AND c.id=p_conversation),
        bounds AS MATERIALIZED (SELECT r.*,CASE WHEN p_cursor IS NULL THEN r.n ELSE (p_cursor->>'through_N')::bigint END AS through_n,
          CASE WHEN p_cursor IS NULL THEN 0 ELSE (p_cursor->>'after_N')::bigint END AS after_n FROM relation r),
        page AS MATERIALIZED (SELECT o.*,s.projection FROM bounds b JOIN platform.human_context_observations o
          ON o.workspace_id=ws AND o.conversation_id=b.id JOIN platform.telegram_provenance s ON (s.workspace_id,s.receipt_id)=(o.workspace_id,o.first_source_receipt_id)
          WHERE o.epoch>b.after_n AND o.epoch<=b.through_n ORDER BY o.epoch LIMIT p_limit+1),
        emitted AS MATERIALIZED (SELECT * FROM page ORDER BY epoch LIMIT p_limit)
        SELECT jsonb_build_object('_error',CASE WHEN b.id IS NULL THEN 'NOT_FOUND'
          WHEN p_cursor IS NOT NULL AND (p_cursor->>'C',p_cursor->>'Client') IS DISTINCT FROM (b.id::text,b.client_id::text) THEN 'NOT_FOUND'
          WHEN p_cursor IS NOT NULL AND p_cursor->>'P'<>b.p::text THEN 'CONTEXT_CURSOR_STALE'
          WHEN NOT (0<=b.after_n AND b.after_n<=b.through_n AND b.through_n<=b.n)
            OR (b.after_n>0 AND NOT EXISTS(SELECT 1 FROM platform.human_context_observations WHERE workspace_id=ws AND conversation_id=b.id AND epoch=b.after_n))
            OR (b.through_n>0 AND NOT EXISTS(SELECT 1 FROM platform.human_context_observations WHERE workspace_id=ws AND conversation_id=b.id AND epoch=b.through_n)) THEN 'INVALID_REQUEST' END,
          'items',(SELECT coalesce(jsonb_agg(jsonb_build_object('observation_id',id,'epoch',epoch::text,'classification',classification,
            'observed_at',to_char(accepted_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
            'source_kind',projection->>'discriminator','preview',platform.human_context_preview(projection),'coverage','PROVIDER_OBSERVATION_ONLY') ORDER BY epoch),'[]'::jsonb) FROM emitted),
          'next_cursor',CASE WHEN (SELECT count(*) FROM page)>p_limit THEN
            translate(replace(encode(convert_to(replace(json_build_object('v',1,'ws',ws,'C',b.id,'Client',b.client_id,'P',b.p::text,
              'through_N',b.through_n::text,'after_N',(SELECT max(epoch)::text FROM emitted))::text,' ',''),'UTF8'),'base64'),E'\n',''),'+/=','-_') END,
          'through_epoch',b.through_n::text,'current_epoch',b.n::text,'observed_at',to_char(moment AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'))
          INTO result FROM (SELECT 1) a LEFT JOIN bounds b ON true;
        IF result->>'_error' IS NOT NULL THEN RAISE EXCEPTION '%',result->>'_error' USING ERRCODE='P2401'; END IF;
        RETURN result-'_error';
      END $$""")
    _define(r"""CREATE FUNCTION platform.human_context_reconcile_result(r platform.human_context_reconciliations) RETURNS jsonb
      LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      SELECT jsonb_build_object('workspace_id',r.workspace_id,'conversation_id',r.conversation_id,'client_id',r.client_id,
        'receipt_id',r.id,'revision_id',r.id,'revision_no',r.revision_no::text,'previous_revision_id',r.previous_revision_id,
        'audit_event_id',r.audit_event_id,'control_generation',r.expected_generation::text,'previous_context_version',r.expected_context_version::text,
        'accepted_context_version',r.accepted_context_version::text,'policy_epoch',r.policy_epoch::text,'observation_epoch',r.observation_epoch::text,
        'reviewed_ingress_checkpoint',r.reviewed_ingress_seq::text,'reviewed_input_state_hash',r.reviewed_input_state_hash,
        'disposition',r.disposition,'source_media',r.source_media,'coverage','OWNER_ASSERTED_TEXT_ONLY',
        'accepted_at',to_char(r.accepted_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"')) $$""")
    _define(r"""CREATE FUNCTION platform.human_context_reconcile(p_conversation uuid,p_key text,p_body jsonb) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE ws uuid; actor uuid; corr uuid; fingerprint bytea; c app.conversations%ROWTYPE;
        r platform.human_context_reconciliations%ROWTYPE; prior platform.human_context_reconciliations%ROWTYPE;
        projection jsonb; k text; keys text[]:=ARRAY['expected_client_id','expected_control_generation','expected_context_version',
          'expected_policy_epoch','expected_observation_epoch','expected_ingress_checkpoint','expected_input_state_hash','expected_revision_id',
          'disposition','text','source_media','attestation'];
      BEGIN
        PERFORM platform.turn_require_isolation(); ws:=app.current_messaging_owner_workspace_id();
        actor:=nullif(current_setting('asm.actor_id',true),'')::uuid; corr:=nullif(current_setting('asm.correlation_id',true),'')::uuid;
        IF ws IS NULL OR corr IS NULL OR platform.messaging_lock_owner(ws,actor) IS NOT TRUE THEN RAISE EXCEPTION 'ACCESS_DENIED' USING ERRCODE='P2401'; END IF;
        IF p_conversation IS NULL OR p_key IS NULL OR p_key !~ '^[A-Za-z0-9._:-]{1,128}$'
          OR platform.material_object(p_body,keys) IS NOT TRUE THEN RAISE EXCEPTION 'INVALID_REQUEST' USING ERRCODE='P2401'; END IF;
        IF NOT platform.human_context_uuid(p_body->'expected_client_id') OR NOT
          (p_body->'expected_revision_id'='null'::jsonb OR platform.human_context_uuid(p_body->'expected_revision_id')) THEN
          RAISE EXCEPTION 'INVALID_REQUEST' USING ERRCODE='P2401'; END IF;
        FOREACH k IN ARRAY ARRAY['expected_control_generation','expected_context_version','expected_policy_epoch','expected_observation_epoch','expected_ingress_checkpoint'] LOOP
          IF platform.human_context_decimal(p_body->k,k IN ('expected_control_generation','expected_context_version')) IS NOT TRUE THEN
            RAISE EXCEPTION 'INVALID_REQUEST' USING ERRCODE='P2401'; END IF;
        END LOOP;
        IF jsonb_typeof(p_body->'expected_input_state_hash')<>'string' OR p_body->>'expected_input_state_hash' !~ '^[0-9a-f]{64}$'
          OR p_body->>'disposition' NOT IN ('OWNER_TEXT','CANONICAL_SUFFICIENT','UNRESOLVED')
          OR p_body->>'source_media' NOT IN ('NONE','UNAVAILABLE') OR p_body->>'attestation'<>'REVIEWED_AVAILABLE_CONTEXT'
          OR jsonb_typeof(p_body->'disposition')<>'string' OR jsonb_typeof(p_body->'source_media')<>'string'
          OR jsonb_typeof(p_body->'attestation')<>'string'
          OR NOT ((p_body->>'disposition'='CANONICAL_SUFFICIENT' AND p_body->'text'='null'::jsonb AND p_body->>'source_media'='NONE')
            OR (p_body->>'disposition'='OWNER_TEXT' AND jsonb_typeof(p_body->'text')='string' AND platform.human_context_text_valid(p_body->>'text'))
            OR (p_body->>'disposition'='UNRESOLVED' AND (p_body->'text'='null'::jsonb OR (jsonb_typeof(p_body->'text')='string' AND platform.human_context_text_valid(p_body->>'text'))))) THEN
          RAISE EXCEPTION 'INVALID_REQUEST' USING ERRCODE='P2401'; END IF;
        PERFORM pg_advisory_xact_lock(hashtextextended(ws::text||':HUMAN_CONTEXT_RECONCILE_V1:'||p_key,2013));
        SELECT * INTO c FROM app.conversations WHERE workspace_id=ws AND id=p_conversation AND client_id=(p_body->>'expected_client_id')::uuid;
        IF NOT FOUND OR (p_body->>'expected_revision_id' IS NOT NULL AND NOT EXISTS(SELECT 1 FROM platform.human_context_reconciliations
          WHERE workspace_id=ws AND conversation_id=c.id AND client_id=c.client_id AND id=(p_body->>'expected_revision_id')::uuid)) THEN
          RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P2401'; END IF;
        fingerprint:=platform.human_context_hash(E'asm:m3:human_context_reconcile:v1\n',ARRAY[ws::text,actor::text,c.id::text,
          p_body->>'expected_client_id',p_body->>'expected_control_generation',p_body->>'expected_context_version',p_body->>'expected_policy_epoch',
          p_body->>'expected_observation_epoch',p_body->>'expected_ingress_checkpoint',p_body->>'expected_input_state_hash',p_body->>'expected_revision_id',
          p_body->>'disposition',p_body->>'text',p_body->>'source_media',p_body->>'attestation']);
        SELECT * INTO prior FROM platform.human_context_reconciliations WHERE workspace_id=ws AND namespace='HUMAN_CONTEXT_RECONCILE_V1' AND idempotency_key=p_key;
        IF FOUND THEN
          IF prior.request_fingerprint<>fingerprint THEN RAISE EXCEPTION 'IDEMPOTENCY_KEY_CONFLICT' USING ERRCODE='P2401'; END IF;
          RETURN jsonb_build_object('outcome','REPLAY','result',prior.result);
        END IF;
        PERFORM 1 FROM app.businesses WHERE workspace_id=ws AND id=c.business_id FOR SHARE;
        PERFORM 1 FROM app.channel_connections WHERE workspace_id=ws AND id=c.connection_id FOR SHARE;
        SELECT * INTO STRICT c FROM app.conversations WHERE workspace_id=ws AND id=p_conversation FOR NO KEY UPDATE;
        IF platform.messaging_lock_owner(ws,actor) IS NOT TRUE THEN RAISE EXCEPTION 'ACCESS_DENIED' USING ERRCODE='P2401'; END IF;
        SELECT platform.human_context_projection(ws,c.id,clock_timestamp()) INTO projection;
        IF (c.client_id::text,c.control_generation::text,c.version::text,projection->>'policy_epoch',projection->>'observation_epoch',
          projection->>'ingress_checkpoint',projection->>'input_state_hash',c.human_context_revision_id::text) IS DISTINCT FROM
          (p_body->>'expected_client_id',p_body->>'expected_control_generation',p_body->>'expected_context_version',p_body->>'expected_policy_epoch',
           p_body->>'expected_observation_epoch',p_body->>'expected_ingress_checkpoint',p_body->>'expected_input_state_hash',p_body->>'expected_revision_id') THEN
          RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P2401'; END IF;
        IF projection->>'policy'='OFF_UNUSED' THEN RAISE EXCEPTION 'CONTEXT_POLICY_INACTIVE' USING ERRCODE='P2401'; END IF;
        IF c.control_mode<>'HUMAN' THEN RAISE EXCEPTION 'HUMAN_REQUIRED' USING ERRCODE='P2401'; END IF;
        IF (projection->>'pending_context_input')::boolean THEN RAISE EXCEPTION 'CONTEXT_INPUT_PENDING' USING ERRCODE='P2401'; END IF;
        IF p_body->>'disposition'<>'UNRESOLVED' AND ((projection->>'input_gap_limit_exceeded')::boolean OR
          (p_body->>'disposition'='CANONICAL_SUFFICIENT' AND ((projection->>'_gap_count')::integer>0 OR (projection->>'_noncanonical')::boolean))) THEN
          RAISE EXCEPTION 'CONTEXT_INPUT_UNRESOLVED' USING ERRCODE='P2401'; END IF;
        IF p_body->>'disposition'='CANONICAL_SUFFICIENT' AND (projection->>'history_truncated')::boolean THEN
          RAISE EXCEPTION 'CONTEXT_COVERAGE_REQUIRED' USING ERRCODE='P2401'; END IF;
        IF (projection->>'_unavailable')::boolean AND p_body->>'source_media'='NONE' THEN RAISE EXCEPTION 'INVALID_REQUEST' USING ERRCODE='P2401'; END IF;
        IF c.version=9223372036854775807 OR coalesce((projection->'current_revision'->>'revision_no')::bigint,0)=9223372036854775807 THEN
          RAISE EXCEPTION 'VERSION_EXHAUSTED' USING ERRCODE='P2401'; END IF;
        r.workspace_id:=ws; r.id:=uuidv7(); r.conversation_id:=c.id; r.client_id:=c.client_id;
        r.connection_id:=c.connection_id; r.provider_chat_id:=c.provider_chat_id; r.actor_user_account_id:=actor;
        r.namespace:='HUMAN_CONTEXT_RECONCILE_V1'; r.idempotency_key:=p_key; r.request_fingerprint:=fingerprint; r.correlation_id:=corr;
        r.previous_revision_id:=c.human_context_revision_id; r.revision_no:=coalesce((projection->'current_revision'->>'revision_no')::bigint,0)+1;
        r.expected_generation:=c.control_generation; r.expected_context_version:=c.version; r.accepted_context_version:=c.version+1;
        r.policy_epoch:=(projection->>'policy_epoch')::bigint; r.observation_epoch:=(projection->>'observation_epoch')::bigint;
        r.reviewed_ingress_seq:=(projection->>'ingress_checkpoint')::bigint; r.reviewed_input_state_hash:=projection->>'input_state_hash';
        r.reviewed_gap_digest:=decode(projection->>'_gap_digest','hex'); r.reviewed_gap_overflow:=(projection->>'input_gap_limit_exceeded')::boolean;
        r.disposition:=p_body->>'disposition'; r.context_text:=p_body->>'text'; r.source_media:=p_body->>'source_media';
        r.attestation:=p_body->>'attestation'; r.event_type:='HUMAN_CONTEXT_RECONCILED'; r.accepted_at:=clock_timestamp();
        INSERT INTO app.audit_events(workspace_id,actor_kind,actor_user_account_id,correlation_id,event_type,object_type,object_id,object_version,payload)
          VALUES(ws,'USER_ACCOUNT',actor,corr,r.event_type,'CONVERSATION',c.id,r.accepted_context_version,
            jsonb_build_object('revision_id',r.id,'previous_revision_id',r.previous_revision_id,'disposition',r.disposition,'source_media',r.source_media,
              'control_generation',r.expected_generation::text,'previous_context_version',r.expected_context_version::text,'accepted_context_version',r.accepted_context_version::text,
              'policy_epoch',r.policy_epoch::text,'observation_epoch',r.observation_epoch::text,'reviewed_ingress_checkpoint',r.reviewed_ingress_seq::text)) RETURNING audit_event_id INTO r.audit_event_id;
        r.result:=platform.human_context_reconcile_result(r);
        INSERT INTO platform.human_context_reconciliations SELECT r.*;
        UPDATE app.conversations SET human_context_revision_id=r.id,human_observation_epoch=r.observation_epoch,version=r.accepted_context_version
          WHERE workspace_id=ws AND id=c.id;
        RETURN jsonb_build_object('outcome','ACCEPTED','result',r.result);
      END $$""")


def _snapshot_validation() -> None:
    _define(r"""CREATE FUNCTION platform.human_context_current_valid(c jsonb) RETURNS boolean
      LANGUAGE sql IMMUTABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      SELECT (platform.material_object(c,ARRAY['schema_version','state','content_type','text','image_availability','changed'])
        AND jsonb_typeof(c->'schema_version')='number' AND c->>'schema_version'='1' AND jsonb_typeof(c->'changed')='boolean'
        AND ((c->>'state' IN ('DELETED','ORDER_UNCERTAIN','UNSUPPORTED_CONTENT') AND c->'content_type'='null'::jsonb
          AND c->'text'='null'::jsonb AND c->>'image_availability'='HIDDEN' AND c->'changed'='true'::jsonb)
          OR (c->>'state'='VISIBLE' AND ((c->>'content_type'='TEXT' AND jsonb_typeof(c->'text')='string'
            AND char_length(c->>'text') BETWEEN 1 AND 4096 AND octet_length(c->>'text')<=16384 AND c->>'image_availability'='NOT_APPLICABLE')
            OR (c->>'content_type'='PHOTO' AND (c->'text'='null'::jsonb OR (jsonb_typeof(c->'text')='string' AND char_length(c->>'text')<=4096 AND octet_length(c->>'text')<=16384))
              AND c->>'image_availability' IN ('ORIGINAL_PENDING','ORIGINAL_READY','ORIGINAL_FAILED','ORIGINAL_NOT_FETCHED','MEDIA_REPLACED_UNAVAILABLE')
              AND (c->>'image_availability' NOT IN ('ORIGINAL_NOT_FETCHED','MEDIA_REPLACED_UNAVAILABLE') OR c->'changed'='true'::jsonb)))))) IS TRUE $$""")
    _define(r"""CREATE FUNCTION platform.human_context_snapshot_valid(s jsonb,shape text) RETURNS boolean
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
            IF (((value->>'status' IN ('SENT','FAILED','UNKNOWN'))<>(value->'completed_at'<>'null'::jsonb))
              OR (value->'completed_at'<>'null'::jsonb AND (jsonb_typeof(value->'completed_at')<>'string'
                OR value->>'completed_at' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}' OR NOT isfinite((value->>'completed_at')::timestamptz)))
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
      END $$""")
    _define(r"""CREATE FUNCTION platform.human_context_admission(ws uuid,p_conversation uuid,saved jsonb) RETURNS text
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE p jsonb; reason text; paired boolean;
      BEGIN
        SELECT platform.human_context_projection(ws,p_conversation,clock_timestamp()),
          coalesce(cc.provider<>'TELEGRAM' OR st.material_enabled,false)
          INTO p,paired FROM app.conversations c JOIN app.channel_connections cc ON (cc.workspace_id,cc.id)=(c.workspace_id,c.connection_id)
          LEFT JOIN platform.telegram_connection_state st ON (st.workspace_id,st.connection_id)=(cc.workspace_id,cc.id)
          WHERE c.workspace_id=ws AND c.id=p_conversation;
        IF p IS NULL THEN RETURN 'STALE'; END IF;
        IF p->>'policy'='OFF_UNUSED' THEN RETURN 'CURRENT'; END IF;
        IF NOT paired THEN RETURN 'CONTEXT_CONFIRMATION_REQUIRED'; END IF;
        reason:=platform.human_context_reason(p,false);
        IF reason NOT IN ('CURRENT','CONTEXT_INPUT_PENDING') THEN RETURN reason; END IF;
        IF saved IS NOT NULL THEN
          IF jsonb_typeof(saved->'schema_version')<>'number' OR saved->>'schema_version'<>'3' THEN RETURN 'CONTEXT_CONFIRMATION_REQUIRED'; END IF;
          IF platform.human_context_snapshot_valid(saved,CASE WHEN saved ? 'consumer' THEN 'GUARDED' ELSE 'BASE' END) IS NOT TRUE THEN
            RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
          IF (saved->'human_context',saved->>'context_policy_epoch',saved->>'human_observation_epoch',saved->>'resume_receipt_id') IS DISTINCT FROM
            (p->'current_revision',p->>'policy_epoch',p->>'observation_epoch',p->>'_resume_receipt_id') THEN RETURN 'CONTEXT_CONFIRMATION_REQUIRED'; END IF;
        END IF;
        RETURN reason;
      END $$""")


def _work() -> None:
    reasons = ",".join("'" + v + "'" for v in PERMANENT_REASONS)
    _define(f"""CREATE FUNCTION platform.human_context_work_valid(j platform.messaging_jobs) RETURNS boolean
      LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      SELECT ((j.context_block_reason IS NULL AND j.context_wait_claim_token IS NULL AND j.context_wait_result IS NULL) OR
        (j.kind IN ('PROCESS_TURN','SEND_GUARDED_TEXT') AND (j.kind<>'PROCESS_TURN' OR j.step IN ('TEST_CONSUME','GUARDED_TEXT','ESCALATE_OWNER'))
          AND j.context_block_reason IS NOT NULL AND ((j.context_wait_claim_token IS NULL AND j.context_wait_result IS NULL AND
            ((j.context_block_reason='CONTEXT_INPUT_PENDING' AND j.status IN ('READY','RUNNING') AND j.error_code='CONTEXT_INPUT_PENDING') OR
             (j.context_block_reason='CONTEXT_WAIT_EXHAUSTED' AND j.status='DEAD' AND j.error_code='RETRY_EXHAUSTED' AND (j.kind<>'PROCESS_TURN' OR j.turn_outcome='FAILED'))))
          OR (j.context_wait_claim_token IS NOT NULL AND j.context_wait_result IS NOT NULL
            AND platform.material_object(j.context_wait_result,ARRAY['code','job_id','turn_id','turn_revision','outbox_id','status','reason','available_at','recorded_at'])
            AND j.context_wait_result->>'job_id'=j.id::text AND j.context_wait_result->>'status'=j.status
            AND j.context_wait_result->>'reason'=j.context_block_reason AND platform.human_context_uuid(j.context_wait_result->'turn_id')
            AND jsonb_typeof(j.context_wait_result->'turn_revision')='number' AND j.context_wait_result->>'turn_revision' ~ '^[1-9][0-9]{{0,18}}$'
            AND ((j.kind='PROCESS_TURN' AND j.context_wait_result->>'turn_id'=j.turn_id::text
              AND j.context_wait_result->>'turn_revision'=j.turn_revision::text AND j.context_wait_result->'outbox_id'='null'::jsonb)
              OR (j.kind='SEND_GUARDED_TEXT' AND j.context_wait_result->>'outbox_id'=j.outbox_id::text))
            AND jsonb_typeof(j.context_wait_result->'recorded_at')='string'
            AND ((j.context_wait_result->>'code'='CONTEXT_WAIT' AND j.status='READY' AND j.context_block_reason='CONTEXT_INPUT_PENDING'
              AND j.error_code='CONTEXT_INPUT_PENDING' AND j.turn_outcome IS NULL AND jsonb_typeof(j.context_wait_result->'available_at')='string')
              OR (j.context_wait_result->>'code'='CONTEXT_WAIT_EXHAUSTED' AND j.status='DEAD' AND j.context_block_reason='CONTEXT_WAIT_EXHAUSTED'
                AND j.error_code='RETRY_EXHAUSTED' AND j.context_wait_result->'available_at'='null'::jsonb AND (j.kind<>'PROCESS_TURN' OR j.turn_outcome='FAILED'))
              OR (j.context_wait_result->>'code'='CONTEXT_HOLD' AND j.status='DEAD' AND j.context_block_reason IN ({reasons})
                AND j.error_code='NOT_ALLOWED' AND j.context_wait_result->'available_at'='null'::jsonb AND (j.kind<>'PROCESS_TURN' OR j.turn_outcome='FAILED'))))))) IS TRUE $$""")
    _define(r"""CREATE FUNCTION platform.human_context_work_replay(p_job uuid,p_claim uuid) RETURNS jsonb
      LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      SELECT CASE WHEN j.context_wait_claim_token=p_claim AND p_claim IS NOT NULL AND j.context_wait_result IS NOT NULL
        AND platform.human_context_work_valid(j) THEN j.context_wait_result ELSE NULL END
        FROM platform.messaging_jobs j WHERE j.id=p_job $$""")
    _define(f"""CREATE FUNCTION platform.human_context_wait(p_job uuid,p_claim uuid,p_reason text) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE j platform.messaging_jobs%ROWTYPE; r platform.turn_guard_receipts%ROWTYPE; result jsonb;
        moment timestamptz; due timestamptz; retry boolean; code text; reason text; tid uuid; revision bigint; saved jsonb;
      BEGIN
        IF p_claim IS NOT NULL THEN
          SELECT platform.human_context_work_replay(p_job,p_claim) INTO saved; IF saved IS NOT NULL THEN RETURN saved; END IF;
          j:=platform.messaging_guard(p_job,p_claim);
        ELSE SELECT * INTO STRICT j FROM platform.messaging_jobs WHERE id=p_job FOR UPDATE;
          IF j.context_block_reason IS DISTINCT FROM 'CONTEXT_INPUT_PENDING' OR j.status NOT IN ('READY','RUNNING') THEN
            RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
        END IF;
        IF p_reason IS NULL OR p_reason NOT IN ('CONTEXT_INPUT_PENDING',{reasons}) OR j.kind NOT IN ('PROCESS_TURN','SEND_GUARDED_TEXT')
          OR (j.kind='PROCESS_TURN' AND j.step NOT IN ('TEST_CONSUME','GUARDED_TEXT','ESCALATE_OWNER')) THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        tid:=j.turn_id; revision:=j.turn_revision;
        IF j.kind='SEND_GUARDED_TEXT' THEN
          SELECT * INTO STRICT r FROM platform.turn_guard_receipts WHERE workspace_id=j.workspace_id AND send_job_id=j.id AND outbox_id=j.outbox_id AND outcome='ACCEPTED';
          tid:=r.turn_id; revision:=r.turn_revision;
          IF NOT EXISTS(SELECT 1 FROM app.outbox_events WHERE workspace_id=j.workspace_id AND id=j.outbox_id AND status='PENDING') THEN
            RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
        END IF;
        moment:=clock_timestamp(); due:=moment+make_interval(secs=>random()*least(60.0,power(2.0,greatest(j.attempt_count-1,0))));
        retry:=p_reason='CONTEXT_INPUT_PENDING' AND j.attempt_count<5 AND moment<j.first_started_at+interval '15 minutes' AND due<j.first_started_at+interval '15 minutes';
        code:=CASE WHEN retry THEN 'CONTEXT_WAIT' WHEN p_reason='CONTEXT_INPUT_PENDING' THEN 'CONTEXT_WAIT_EXHAUSTED' ELSE 'CONTEXT_HOLD' END;
        reason:=CASE WHEN code='CONTEXT_WAIT_EXHAUSTED' THEN code ELSE p_reason END;
        result:=jsonb_build_object('code',code,'job_id',j.id,'turn_id',tid,'turn_revision',revision,'outbox_id',j.outbox_id,
          'status',CASE WHEN retry THEN 'READY' ELSE 'DEAD' END,'reason',reason,
          'available_at',CASE WHEN retry THEN to_char(due AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"') END,
          'recorded_at',to_char(moment AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'));
        IF NOT retry AND j.kind='SEND_GUARDED_TEXT' THEN
          UPDATE app.outbox_events SET status='FAILED',error_code=CASE WHEN code='CONTEXT_WAIT_EXHAUSTED' THEN 'RETRY_EXHAUSTED' ELSE 'NOT_ALLOWED' END,
            completed_at=moment,version=version+1 WHERE workspace_id=j.workspace_id AND id=j.outbox_id;
        END IF;
        UPDATE platform.messaging_jobs SET status=CASE WHEN retry THEN 'READY' ELSE 'DEAD' END,
          context_block_reason=reason,context_wait_claim_token=p_claim,context_wait_result=CASE WHEN p_claim IS NOT NULL THEN result END,
          error_code=CASE WHEN retry THEN 'CONTEXT_INPUT_PENDING' WHEN code='CONTEXT_WAIT_EXHAUSTED' THEN 'RETRY_EXHAUSTED' ELSE 'NOT_ALLOWED' END,
          guard_rejection=CASE WHEN kind='SEND_GUARDED_TEXT' AND code='CONTEXT_HOLD' THEN 'NOT_ALLOWED' END,
          turn_outcome=CASE WHEN kind='PROCESS_TURN' AND NOT retry THEN 'FAILED' END,
          claim_token=NULL,lease_until=NULL,worker_id=NULL,available_at=CASE WHEN retry THEN due ELSE available_at END,
          completed_at=CASE WHEN NOT retry THEN moment END,version=version+1 WHERE id=j.id;
        RETURN result;
      END $$""")
    op.execute("""ALTER TABLE platform.messaging_jobs DROP CONSTRAINT messaging_jobs_error_code_check,
      ADD CONSTRAINT messaging_jobs_error_code_check CHECK(error_code IS NULL OR error_code IN
        ('NOT_ALLOWED','RETRY_EXHAUSTED','DEPENDENCY_TIMEOUT','DEPENDENCY_UNAVAILABLE','UNKNOWN_EXTERNAL_RESULT','INVALID_INPUT','MESSAGE_ID_CONFLICT','CONVERSATION_IDENTITY_CONFLICT','CONTEXT_INPUT_PENDING')),
      ADD CONSTRAINT native_context_work_check CHECK(platform.human_context_work_valid(messaging_jobs))""")


def _control() -> None:
    _replace(
        "conversation_control_execute(6)",
        (
            "allowed boolean; target text;",
            "allowed boolean; projection jsonb; native_reason text; target text;",
        ),
        (
            "target:=CASE p_operation WHEN 'TAKEOVER' THEN 'HUMAN' ELSE 'AI' END;",
            """IF p_operation='RESUME' THEN
          SELECT platform.human_context_projection(ws,conv.id,clock_timestamp()) INTO projection;
          native_reason:=platform.human_context_reason(projection,true);
          IF native_reason<>'CURRENT' THEN RAISE EXCEPTION '%',native_reason USING ERRCODE='P2401'; END IF;
        END IF;
        target:=CASE p_operation WHEN 'TAKEOVER' THEN 'HUMAN' ELSE 'AI' END;""",
        ),
        (
            "accepted_at,result,guard_profile)",
            "accepted_at,result,guard_profile,human_context_revision_id,human_context_policy_epoch,human_observation_epoch)",
        ),
        (
            "THEN 'CONTROLLED_GUARDS_V1' END);",
            """THEN 'CONTROLLED_GUARDS_V1' END,
            CASE WHEN p_operation='RESUME' AND projection->>'policy'<>'OFF_UNUSED' THEN conv.human_context_revision_id END,
            CASE WHEN p_operation='RESUME' AND projection->>'policy'<>'OFF_UNUSED' THEN (projection->>'policy_epoch')::bigint END,
            CASE WHEN p_operation='RESUME' AND projection->>'policy'<>'OFF_UNUSED' THEN (projection->>'observation_epoch')::bigint END);""",
        ),
    )


def _admissions() -> None:
    _define(r"""CREATE FUNCTION platform.human_context_test_prelock(j platform.messaging_jobs) RETURNS void
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE c app.conversations%ROWTYPE; r platform.conversation_control_receipts%ROWTYPE;
      BEGIN
        SELECT c0.* INTO STRICT c FROM app.conversations c0 JOIN app.conversation_turns t ON (t.workspace_id,t.conversation_id)=(c0.workspace_id,c0.id)
          WHERE t.workspace_id=j.workspace_id AND t.id=j.turn_id;
        IF (SELECT human_context_policy FROM app.channel_connections WHERE workspace_id=c.workspace_id AND id=c.connection_id)='OFF_UNUSED' THEN RETURN; END IF;
        SELECT * INTO r FROM platform.conversation_control_receipts WHERE workspace_id=c.workspace_id AND conversation_id=c.id AND accepted_generation=c.control_generation AND operation='RESUME';
        IF r.id IS NOT NULL THEN PERFORM platform.messaging_lock_owner(j.workspace_id,r.actor_user_account_id); END IF;
        PERFORM 1 FROM app.businesses WHERE workspace_id=c.workspace_id AND id=c.business_id FOR SHARE;
        PERFORM 1 FROM app.channel_connections WHERE workspace_id=c.workspace_id AND id=c.connection_id FOR SHARE;
        PERFORM platform.messaging_lock_billing_workspace(j.workspace_id);
      END $$""")
    _define(r"""CREATE FUNCTION platform.human_context_test_guard(j platform.messaging_jobs,saved jsonb) RETURNS text
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE c app.conversations%ROWTYPE; t app.conversation_turns%ROWTYPE; r platform.conversation_control_receipts%ROWTYPE; allowed boolean;
      BEGIN
        SELECT * INTO STRICT t FROM app.conversation_turns WHERE workspace_id=j.workspace_id AND id=j.turn_id;
        SELECT * INTO STRICT c FROM app.conversations WHERE workspace_id=j.workspace_id AND id=t.conversation_id;
        IF (SELECT human_context_policy FROM app.channel_connections WHERE workspace_id=c.workspace_id AND id=c.connection_id)='OFF_UNUSED' THEN RETURN 'CURRENT'; END IF;
        IF t.revision<>j.turn_revision OR t.state<>'READY' OR platform.material_turn_usable(j.workspace_id,t.id) IS NOT TRUE
          OR platform.conversation_turn_activation_matches(j.workspace_id,t.id) IS NOT TRUE
          OR (saved IS NOT NULL AND ((saved->>'context_version')::bigint<>c.version OR (saved->>'control_generation')::bigint<>c.control_generation)) THEN RETURN 'STALE'; END IF;
        SELECT * INTO r FROM platform.conversation_control_receipts WHERE workspace_id=j.workspace_id AND conversation_id=c.id AND accepted_generation=t.control_generation AND operation='RESUME';
        IF r.id IS NULL OR r.human_context_revision_id IS NULL OR platform.messaging_lock_owner(j.workspace_id,r.actor_user_account_id) IS NOT TRUE
          OR NOT EXISTS(SELECT 1 FROM app.businesses WHERE workspace_id=j.workspace_id AND id=c.business_id AND status='ACTIVE')
          OR NOT EXISTS(SELECT 1 FROM app.channel_connections WHERE workspace_id=j.workspace_id AND id=j.connection_id AND business_id=c.business_id AND status='ACTIVE') THEN RETURN 'NOT_ALLOWED'; END IF;
        BEGIN allowed:=platform.messaging_manual_send_allowed(j.workspace_id);
          EXCEPTION WHEN SQLSTATE 'P2301' THEN RAISE EXCEPTION 'DEPENDENCY_UNAVAILABLE' USING ERRCODE='P2001'; END;
        IF allowed IS NOT TRUE THEN RETURN 'NOT_ALLOWED'; END IF;
        RETURN platform.human_context_admission(j.workspace_id,c.id,saved);
      END $$""")
    _define(r"""CREATE FUNCTION platform.human_context_snapshot_check(s jsonb,shape text) RETURNS text
      LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      BEGIN
        IF NOT s ? 'schema_version' OR s->>'schema_version'='2' THEN RETURN 'CURRENT'; END IF;
        IF octet_length(convert_to((s-'snapshot_digest')::text,'UTF8'))>2097152 THEN RETURN 'CONTEXT_TOO_LARGE'; END IF;
        IF platform.human_context_snapshot_valid(s,shape) IS NOT TRUE THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        RETURN 'CURRENT';
      END $$""")
    _define(
        ORIGINAL["guard_require_current(4)"]
        .replace("platform.guard_require_current(", "platform.human_context_basic_current(", 1)
        .replace(
            "RETURN 'CURRENT';",
            "IF r.human_context_revision_id IS NULL AND EXISTS(SELECT 1 FROM app.channel_connections WHERE workspace_id=ws AND id=c.connection_id AND human_context_policy<>'OFF_UNUSED') THEN RETURN 'NOT_ALLOWED'; END IF; RETURN 'CURRENT';",
        )
    )
    _replace(
        "guard_require_current(4)",
        ("RETURN 'CURRENT';", "RETURN platform.human_context_admission(ws,c.id,NULL);"),
    )
    _define(r"""CREATE OR REPLACE FUNCTION platform.turn_snapshot(ws uuid,p_turn uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE result jsonb;
      BEGIN
        SELECT platform.human_context_turn_projection(ws,p_turn,clock_timestamp()) INTO result;
        IF result IS NULL THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        RETURN result;
      END $$""")
    context_branch = """IF outcome IN ('CONTEXT_INPUT_PENDING','CONTEXT_POLICY_PAUSED','CONTEXT_CONFIRMATION_REQUIRED','CONTEXT_UNRESOLVED',
          'NEW_OBSERVATION','CONTEXT_INPUT_UNRESOLVED','CONTEXT_COVERAGE_REQUIRED','CONTEXT_TOO_LARGE') THEN
          RETURN platform.human_context_wait(j.id,p_claim,outcome); END IF;"""
    cleanup = "context_block_reason=NULL,context_wait_claim_token=NULL,context_wait_result=NULL,"
    _replace(
        "guard_turn_prepare(2)",
        ("platform.guard_require_current(", "platform.human_context_basic_current("),
        (
            "IF outcome<>'CURRENT' THEN",
            "IF outcome='CURRENT' THEN outcome:=platform.human_context_admission(j.workspace_id,conv.id,j.turn_input); END IF;\n        "
            + context_branch
            + "\n        IF outcome<>'CURRENT' THEN",
        ),
        (
            "status='SUCCEEDED',turn_outcome=outcome,error_code=NULL,",
            "status='SUCCEEDED',turn_outcome=outcome,error_code=NULL," + cleanup,
        ),
        (
            "UPDATE platform.messaging_jobs SET turn_input=input WHERE id=j.id;",
            """outcome:=platform.human_context_snapshot_check(input,'GUARDED');
          """
            + context_branch
            + "\n          UPDATE platform.messaging_jobs SET turn_input=input,context_block_reason=NULL,context_wait_claim_token=NULL,context_wait_result=NULL,error_code=NULL WHERE id=j.id;",
        ),
    )
    _replace(
        "guard_turn_accept(4)",
        ("platform.guard_require_current(", "platform.human_context_basic_current("),
        (
            "IF outcome='CURRENT' THEN",
            """IF outcome='CURRENT' THEN outcome:=platform.human_context_admission(j.workspace_id,conv.id,input); END IF;
        """
            + context_branch
            + "\n        IF outcome='CURRENT' THEN",
        ),
        (
            "status='SUCCEEDED',turn_outcome=outcome,error_code=NULL,",
            "status='SUCCEEDED',turn_outcome=outcome,error_code=NULL," + cleanup,
        ),
    )
    _replace(
        "guard_send_begin(2)",
        ("platform.guard_require_current(", "platform.human_context_basic_current("),
        (
            "IF outcome<>'CURRENT' THEN",
            """IF outcome='CURRENT' THEN outcome:=platform.human_context_admission(j.workspace_id,conv.id,
          (SELECT turn_input FROM platform.messaging_jobs WHERE workspace_id=j.workspace_id AND id=r.job_id)); END IF;
        """
            + context_branch
            + "\n        IF outcome<>'CURRENT' THEN",
        ),
        (
            "status='DEAD',error_code='NOT_ALLOWED',guard_rejection=outcome,",
            "status='DEAD',error_code='NOT_ALLOWED',guard_rejection=outcome," + cleanup,
        ),
        (
            "attempt:=gen_random_uuid();",
            """UPDATE platform.messaging_jobs SET context_block_reason=NULL,context_wait_claim_token=NULL,context_wait_result=NULL,error_code=NULL WHERE id=j.id;
        attempt:=gen_random_uuid();""",
        ),
    )
    test_gate = (
        """outcome:=platform.human_context_test_guard(j,j.turn_input);
          """
        + context_branch
        + """
          IF outcome<>'CURRENT' THEN
            UPDATE platform.messaging_jobs SET status='SUCCEEDED',turn_outcome=outcome,error_code=NULL,
              context_block_reason=NULL,context_wait_claim_token=NULL,context_wait_result=NULL,
              claim_token=NULL,lease_until=NULL,worker_id=NULL,completed_at=clock_timestamp(),version=version+1 WHERE id=j.id;
            RETURN jsonb_build_object('code',outcome,'job_id',j.id,'turn_id',j.turn_id,'turn_revision',j.turn_revision);
          END IF;"""
    )
    _replace(
        "turn_execute(2)",
        (
            "PERFORM platform.turn_preflight(j,false,false);",
            "IF j.step='TEST_CONSUME' THEN PERFORM platform.human_context_test_prelock(j); END IF;\n        PERFORM platform.turn_preflight(j,false,false);",
        ),
        (
            "input:=coalesce(j.turn_input,platform.turn_snapshot(j.workspace_id,j.turn_id));",
            test_gate
            + "\n          input:=coalesce(j.turn_input,platform.turn_snapshot(j.workspace_id,j.turn_id));",
        ),
        (
            "IF j.turn_input IS NULL THEN UPDATE platform.messaging_jobs SET turn_input=input WHERE id=j.id; END IF;",
            """outcome:=platform.human_context_snapshot_check(input,'BASE');
          """
            + context_branch
            + """
          IF j.turn_input IS NULL THEN UPDATE platform.messaging_jobs SET turn_input=input,context_block_reason=NULL,
            context_wait_claim_token=NULL,context_wait_result=NULL,error_code=NULL WHERE id=j.id; END IF;""",
        ),
    )
    _replace(
        "turn_consumer_finalize(3)",
        ("accepted timestamptz;", "accepted timestamptz; outcome text;"),
        (
            "PERFORM platform.turn_preflight(j,false,false);",
            "PERFORM platform.human_context_test_prelock(j);\n        PERFORM platform.turn_preflight(j,false,false);",
        ),
        (
            "IF p_result IS DISTINCT FROM expected THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;",
            "IF p_result IS DISTINCT FROM expected THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;\n        "
            + test_gate,
        ),
        ("j.turn_input->>'schema_version'='2'", "j.turn_input->>'schema_version' IN ('2','3')"),
        (
            "status='SUCCEEDED',turn_outcome=code,error_code=NULL,",
            "status='SUCCEEDED',turn_outcome=code,error_code=NULL," + cleanup,
        ),
    )
    _replace(
        "escalation_request_for_turn(2)",
        (
            "owner_live IS NOT TRUE OR NOT (",
            "owner_live IS NOT TRUE OR (r.human_context_revision_id IS NULL AND EXISTS(SELECT 1 FROM app.channel_connections WHERE workspace_id=ws AND id=c.connection_id AND human_context_policy<>'OFF_UNUSED')) OR NOT (",
        ),
        (
            "PERFORM platform.messaging_guard(p_job,p_claim);\n        IF outcome IS NOT NULL THEN",
            """PERFORM platform.messaging_guard(p_job,p_claim);
        IF outcome IS NULL THEN
          IF EXISTS(SELECT 1 FROM app.channel_connections WHERE workspace_id=ws AND id=c.connection_id AND human_context_policy<>'OFF_UNUSED') AND platform.material_turn_usable(ws,t.id) IS NOT TRUE THEN outcome:='STALE'; ELSE
            outcome:=nullif(platform.human_context_admission(ws,c.id,NULL),'CURRENT'); END IF;
        END IF;
        """
            + context_branch
            + "\n        IF outcome IS NOT NULL THEN",
        ),
        (
            "status='SUCCEEDED',turn_outcome=outcome,error_code=NULL,",
            "status='SUCCEEDED',turn_outcome=outcome,error_code=NULL," + cleanup,
        ),
        (
            "-- Increment first;",
            """outcome:=platform.human_context_snapshot_check(e.request_snapshot,'ESCALATION');
        """
            + context_branch
            + "\n        -- Increment first;",
        ),
        (
            "status='SUCCEEDED',turn_outcome='ESCALATED',error_code=NULL,",
            "status='SUCCEEDED',turn_outcome='ESCALATED',error_code=NULL," + cleanup,
        ),
    )
    _replace(
        "escalation_immutable(0)",
        (
            "IF (j.status,j.claim_token,t.revision,t.state,c.version",
            """IF e.request_snapshot->>'schema_version'='3' AND platform.human_context_snapshot_valid(e.request_snapshot,'ESCALATION') IS NOT TRUE THEN
          RAISE EXCEPTION 'invalid native escalation snapshot' USING ERRCODE='23514',SCHEMA='app',TABLE='escalations',CONSTRAINT='escalations_immutable_check'; END IF;
        IF (j.status,j.claim_token,t.revision,t.state,c.version""",
        ),
    )
    _replace(
        "turn_supersede(1)",
        (
            "status='SUCCEEDED',turn_outcome='SUPERSEDED',error_code=NULL,",
            "status='SUCCEEDED',turn_outcome='SUPERSEDED',error_code=NULL," + cleanup,
        ),
    )
    _replace(
        "messaging_claim(4)",
        (
            "UPDATE platform.messaging_jobs SET status='RUNNING',",
            "UPDATE platform.messaging_jobs SET context_wait_claim_token=NULL,context_wait_result=NULL,status='RUNNING',",
        ),
    )
    _replace(
        "messaging_reschedule(5)",
        (
            "final_error:=CASE WHEN (p_retry AND NOT retry)",
            """IF j.context_block_reason='CONTEXT_INPUT_PENDING' AND (p_error='RETRY_EXHAUSTED' OR (p_retry AND p_error='DEPENDENCY_TIMEOUT' AND current_setting('asm.actor_kind',true) IS DISTINCT FROM 'worker_job')) THEN
          RETURN platform.human_context_wait(j.id,CASE WHEN current_setting('asm.actor_kind',true)='worker_job' THEN j.claim_token END,'CONTEXT_INPUT_PENDING'); END IF;
        final_error:=CASE WHEN (p_retry AND NOT retry)""",
        ),
        (
            "UPDATE platform.messaging_jobs SET status=CASE WHEN retry THEN 'READY' ELSE 'DEAD' END,",
            "UPDATE platform.messaging_jobs SET context_block_reason=NULL,context_wait_claim_token=NULL,context_wait_result=NULL,status=CASE WHEN retry THEN 'READY' ELSE 'DEAD' END,",
        ),
    )


def _escalations_and_reads() -> None:
    _define(r"""CREATE FUNCTION platform.human_context_escalation_hold(ws uuid,p_escalation uuid,p_clock timestamptz) RETURNS jsonb
      LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      WITH state AS MATERIALIZED (SELECT e.status,platform.escalation_validity(ws,e.id,p_clock) AS validity,
        platform.human_context_projection(ws,e.conversation_id,p_clock) AS p FROM app.escalations e WHERE e.workspace_id=ws AND e.id=p_escalation)
      SELECT CASE WHEN status<>'PENDING' OR validity<>'CURRENT' OR p->>'policy'='OFF_UNUSED' OR platform.human_context_reason(p,false)='CURRENT'
        THEN NULL ELSE jsonb_build_object('reason',platform.human_context_reason(p,false),'policy',p->>'policy',
          'policy_epoch',p->>'policy_epoch','observation_epoch',p->>'observation_epoch','coverage_status',p->>'coverage_status') END FROM state $$""")
    _replace(
        "escalation_command(9)",
        ("validity text; moment", "native_hold jsonb; validity text; moment"),
        (
            "SELECT * INTO STRICT c FROM app.conversations WHERE workspace_id=ws AND id=p_conversation FOR NO KEY UPDATE;",
            """IF p_operation='RESOLVE' THEN
          PERFORM 1 FROM app.channel_connections cc JOIN app.conversations c0 ON (c0.workspace_id,c0.connection_id)=(cc.workspace_id,cc.id)
            WHERE c0.workspace_id=ws AND c0.id=p_conversation AND c0.client_id=p_client FOR SHARE OF cc;
        END IF;
        SELECT * INTO STRICT c FROM app.conversations WHERE workspace_id=ws AND id=p_conversation FOR NO KEY UPDATE;""",
        ),
        (
            "accepted:=CASE p_operation WHEN 'RESOLVE'",
            """IF p_operation='RESOLVE' THEN
          SELECT platform.human_context_escalation_hold(ws,e.id,moment) INTO native_hold;
          IF native_hold IS NOT NULL THEN RAISE EXCEPTION 'STALE_STATE' USING ERRCODE='P2501'; END IF;
        END IF;
        accepted:=CASE p_operation WHEN 'RESOLVE'""",
        ),
    )
    for name in ("escalation_read(1)", "escalation_list(4)"):
        _replace(
            name,
            (
                "'can_resolve',e.status='PENDING' AND v.validity='CURRENT' AND e.assignee_user_account_id=actor,",
                "'context_hold',h.hold,'can_resolve',e.status='PENDING' AND v.validity='CURRENT' AND e.assignee_user_account_id=actor AND h.hold IS NULL,",
            ),
            (
                "AS validity) v",
                "AS validity) v CROSS JOIN LATERAL (SELECT platform.human_context_escalation_hold(e.workspace_id,e.id,clock.moment) AS hold) h",
            ),
        )
    _replace(
        "messaging_read_messages(4)",
        (
            "platform.message_effective(ws,m.id) AS current",
            "platform.human_context_effective(m,mt.current_material,f.status) AS current",
        ),
        (
            "LEFT JOIN app.outbox_events b ON b.workspace_id=m.workspace_id AND b.message_id=m.id",
            "LEFT JOIN app.outbox_events b ON b.workspace_id=m.workspace_id AND b.message_id=m.id\n            LEFT JOIN platform.message_material_targets mt ON (mt.workspace_id,mt.message_id)=(m.workspace_id,m.id)",
        ),
    )


def _integrity() -> None:
    _define(r"""CREATE FUNCTION platform.human_context_integrity() RETURNS trigger
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE r platform.human_context_reconciliations%ROWTYPE; o platform.human_context_observations%ROWTYPE;
        s platform.telegram_provenance%ROWTYPE; c app.conversations%ROWTYPE; a app.audit_events%ROWTYPE;
        receipt platform.human_context_policy_receipts%ROWTYPE; gr platform.turn_guard_receipts%ROWTYPE;
      BEGIN
        IF TG_TABLE_NAME='human_context_observations' THEN
          SELECT * INTO c FROM app.conversations WHERE workspace_id=NEW.workspace_id AND id=NEW.conversation_id;
          IF c.id IS NULL OR (NEW.client_id,NEW.connection_id,NEW.provider_chat_id,NEW.control_generation,NEW.epoch) IS DISTINCT FROM
            (c.client_id,c.connection_id,c.provider_chat_id,c.control_generation,coalesce(c.human_observation_epoch,0)+1)
            OR NEW.policy_epoch IS DISTINCT FROM (SELECT human_context_policy_epoch FROM app.channel_connections WHERE workspace_id=c.workspace_id AND id=c.connection_id)
            OR NOT EXISTS(SELECT 1 FROM platform.telegram_update_receipts source WHERE source.workspace_id=c.workspace_id AND source.id=NEW.first_source_receipt_id
              AND source.connection_id=c.connection_id AND source.codec=2 AND source.received_at=NEW.accepted_at) THEN
            RAISE EXCEPTION 'invalid native observation identity' USING ERRCODE='23514'; END IF;
          RETURN NEW;
        ELSIF TG_TABLE_NAME='human_context_reconciliations' THEN
          SELECT * INTO c FROM app.conversations WHERE workspace_id=NEW.workspace_id AND id=NEW.conversation_id;
          IF c.id IS NULL OR c.control_mode<>'HUMAN' OR (NEW.client_id,NEW.connection_id,NEW.provider_chat_id,NEW.expected_generation,
              NEW.expected_context_version,NEW.observation_epoch,NEW.previous_revision_id) IS DISTINCT FROM
            (c.client_id,c.connection_id,c.provider_chat_id,c.control_generation,c.version,coalesce(c.human_observation_epoch,0),c.human_context_revision_id)
            OR NEW.policy_epoch IS DISTINCT FROM (SELECT human_context_policy_epoch FROM app.channel_connections WHERE workspace_id=c.workspace_id AND id=c.connection_id)
            OR NOT EXISTS(SELECT 1 FROM platform.workspace_memberships WHERE workspace_id=c.workspace_id AND user_account_id=NEW.actor_user_account_id AND role='OWNER' AND status='ACTIVE') THEN
            RAISE EXCEPTION 'invalid native reconciliation identity' USING ERRCODE='23514'; END IF;
          RETURN NEW;
        ELSIF TG_TABLE_NAME='conversations' THEN
          IF TG_OP='UPDATE' AND NEW.human_context_revision_id IS DISTINCT FROM OLD.human_context_revision_id THEN
            SELECT * INTO r FROM platform.human_context_reconciliations WHERE workspace_id=NEW.workspace_id AND id=NEW.human_context_revision_id;
            IF r.id IS NULL OR (r.conversation_id,r.client_id,r.previous_revision_id,r.expected_generation,r.expected_context_version,r.accepted_context_version,r.observation_epoch) IS DISTINCT FROM
              (NEW.id,NEW.client_id,OLD.human_context_revision_id,OLD.control_generation,OLD.version,NEW.version,coalesce(OLD.human_observation_epoch,0))
              OR NEW.human_observation_epoch IS DISTINCT FROM r.observation_epoch OR NEW.version::numeric<>OLD.version::numeric+1
              OR (NEW.control_generation,NEW.control_mode,NEW.activation_fence_seq) IS DISTINCT FROM (OLD.control_generation,OLD.control_mode,OLD.activation_fence_seq) THEN
              RAISE EXCEPTION 'invalid native revision atom' USING ERRCODE='23514'; END IF;
          ELSIF TG_OP='UPDATE' AND NEW.human_observation_epoch IS DISTINCT FROM OLD.human_observation_epoch THEN
            IF NEW.human_observation_epoch IS NULL OR NEW.human_observation_epoch::numeric<>coalesce(OLD.human_observation_epoch,0)::numeric+1
              OR (NEW.version,NEW.control_generation,NEW.control_mode,NEW.activation_fence_seq,NEW.human_context_revision_id) IS DISTINCT FROM
                (OLD.version,OLD.control_generation,OLD.control_mode,OLD.activation_fence_seq,OLD.human_context_revision_id)
              OR NOT EXISTS(SELECT 1 FROM platform.human_context_observations WHERE workspace_id=NEW.workspace_id AND conversation_id=NEW.id AND client_id=NEW.client_id AND epoch=NEW.human_observation_epoch) THEN
              RAISE EXCEPTION 'invalid native observation atom' USING ERRCODE='23514'; END IF;
          END IF;
          RETURN NEW;
        ELSIF TG_TABLE_NAME='conversation_control_receipts' THEN
          IF NEW.operation='TAKEOVER' THEN
            IF NEW.human_context_revision_id IS NOT NULL OR NEW.human_context_policy_epoch IS NOT NULL OR NEW.human_observation_epoch IS NOT NULL THEN RAISE EXCEPTION 'takeover native link' USING ERRCODE='23514'; END IF;
          ELSE
            SELECT c0.* INTO STRICT c FROM app.conversations c0 WHERE c0.workspace_id=NEW.workspace_id AND c0.id=NEW.conversation_id;
            IF (SELECT human_context_policy FROM app.channel_connections WHERE workspace_id=c.workspace_id AND id=c.connection_id)='OFF_UNUSED' THEN
              IF NEW.human_context_revision_id IS NOT NULL OR NEW.human_context_policy_epoch IS NOT NULL OR NEW.human_observation_epoch IS NOT NULL THEN RAISE EXCEPTION 'unused native link' USING ERRCODE='23514'; END IF;
            ELSIF NEW.human_context_revision_id IS NULL OR NEW.human_context_policy_epoch IS NULL OR NEW.human_observation_epoch IS NULL
              OR NEW.human_context_revision_id IS DISTINCT FROM c.human_context_revision_id
              OR NEW.human_observation_epoch IS DISTINCT FROM coalesce(c.human_observation_epoch,0)
              OR NEW.human_context_policy_epoch IS DISTINCT FROM (SELECT human_context_policy_epoch FROM app.channel_connections WHERE workspace_id=c.workspace_id AND id=c.connection_id)
              OR NOT EXISTS(SELECT 1 FROM platform.human_context_reconciliations rr WHERE rr.workspace_id=c.workspace_id AND rr.id=c.human_context_revision_id AND rr.disposition IN ('OWNER_TEXT','CANONICAL_SUFFICIENT')) THEN
              RAISE EXCEPTION 'used native link required' USING ERRCODE='23514'; END IF;
          END IF;
          RETURN NEW;
        ELSIF TG_TABLE_NAME='messaging_jobs' THEN
          IF NEW.context_block_reason IS NOT NULL AND NEW.kind='SEND_GUARDED_TEXT' THEN
            SELECT * INTO gr FROM platform.turn_guard_receipts WHERE workspace_id=NEW.workspace_id AND send_job_id=NEW.id AND outbox_id=NEW.outbox_id AND outcome='ACCEPTED';
            IF gr.job_id IS NULL OR (NEW.context_wait_result IS NOT NULL AND
              (NEW.context_wait_result->>'turn_id',NEW.context_wait_result->>'turn_revision') IS DISTINCT FROM (gr.turn_id::text,gr.turn_revision::text)) THEN
              RAISE EXCEPTION 'invalid native send work identity' USING ERRCODE='23514'; END IF;
          END IF;
          IF TG_OP='UPDATE' AND OLD.context_wait_claim_token IS NOT NULL AND NEW.context_wait_claim_token=OLD.context_wait_claim_token
            AND NEW.context_wait_result IS DISTINCT FROM OLD.context_wait_result THEN RAISE EXCEPTION 'immutable native scheduling result' USING ERRCODE='23514'; END IF;
          IF NEW.context_wait_result IS NOT NULL THEN
            IF to_char((NEW.context_wait_result->>'recorded_at')::timestamptz AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"') IS DISTINCT FROM NEW.context_wait_result->>'recorded_at'
              OR (NEW.status='READY' AND to_char(NEW.available_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"') IS DISTINCT FROM NEW.context_wait_result->>'available_at') THEN
              RAISE EXCEPTION 'invalid native scheduling time' USING ERRCODE='23514'; END IF;
          END IF;
          RETURN NEW;
        ELSIF TG_TABLE_NAME='inbox_events' THEN
          IF TG_OP='UPDATE' AND OLD.human_context_source_receipt_id IS NOT NULL AND
            (NEW.human_context_source_receipt_id,NEW.human_context_observation_id) IS DISTINCT FROM (OLD.human_context_source_receipt_id,OLD.human_context_observation_id) THEN
            RAISE EXCEPTION 'immutable source link' USING ERRCODE='23514'; END IF;
          RETURN NEW;
        END IF;
        RAISE EXCEPTION 'invalid native trigger' USING ERRCODE='23514';
      END $$""")
    _define(r"""CREATE FUNCTION platform.human_context_consistent() RETURNS trigger
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE r platform.human_context_reconciliations%ROWTYPE; o platform.human_context_observations%ROWTYPE;
        s platform.telegram_provenance%ROWTYPE; i platform.inbox_events%ROWTYPE; c app.conversations%ROWTYPE; a app.audit_events%ROWTYPE;
        receipt platform.human_context_policy_receipts%ROWTYPE; prior platform.human_context_reconciliations%ROWTYPE;
      BEGIN
        IF TG_TABLE_NAME='audit_events' THEN
          IF NEW.event_type='HUMAN_CONTEXT_RECONCILED' AND NOT EXISTS(SELECT 1 FROM platform.human_context_reconciliations
            WHERE workspace_id=NEW.workspace_id AND id=NEW.native_revision_id AND audit_event_id=NEW.audit_event_id
              AND conversation_id=NEW.object_id AND actor_user_account_id=NEW.actor_user_account_id AND accepted_context_version=NEW.object_version) THEN
            RAISE EXCEPTION 'missing native reconciliation audit atom' USING ERRCODE='23514';
          ELSIF NEW.event_type='HUMAN_CONTEXT_POLICY_COMMANDED' AND NOT EXISTS(SELECT 1 FROM platform.human_context_policy_receipts
            WHERE workspace_id=NEW.workspace_id AND id=NEW.native_policy_receipt_id AND audit_event_id=NEW.audit_event_id
              AND connection_id=NEW.object_id AND accepted_policy_epoch=NEW.object_version) THEN
            RAISE EXCEPTION 'missing native policy audit atom' USING ERRCODE='23514'; END IF;
          RETURN NULL;
        ELSIF TG_TABLE_NAME='human_context_reconciliations' THEN
          SELECT * INTO r FROM platform.human_context_reconciliations WHERE workspace_id=NEW.workspace_id AND id=NEW.id;
          IF NOT FOUND THEN RETURN NULL; END IF;
          SELECT * INTO STRICT a FROM app.audit_events WHERE workspace_id=r.workspace_id AND audit_event_id=r.audit_event_id;
          IF r.result IS DISTINCT FROM platform.human_context_reconcile_result(r)
            OR a.payload IS DISTINCT FROM jsonb_build_object('revision_id',r.id,'previous_revision_id',r.previous_revision_id,
              'disposition',r.disposition,'source_media',r.source_media,'control_generation',r.expected_generation::text,
              'previous_context_version',r.expected_context_version::text,'accepted_context_version',r.accepted_context_version::text,
              'policy_epoch',r.policy_epoch::text,'observation_epoch',r.observation_epoch::text,'reviewed_ingress_checkpoint',r.reviewed_ingress_seq::text)
            OR a.correlation_id<>r.correlation_id THEN RAISE EXCEPTION 'invalid native reconciliation evidence' USING ERRCODE='23514'; END IF;
          IF r.previous_revision_id IS NULL THEN IF r.revision_no<>1 THEN RAISE EXCEPTION 'native revision number' USING ERRCODE='23514'; END IF;
          ELSE SELECT * INTO STRICT prior FROM platform.human_context_reconciliations WHERE workspace_id=r.workspace_id AND id=r.previous_revision_id;
            IF r.revision_no::numeric<>prior.revision_no::numeric+1 THEN RAISE EXCEPTION 'native revision number' USING ERRCODE='23514'; END IF;
          END IF;
          SELECT * INTO STRICT c FROM app.conversations WHERE workspace_id=r.workspace_id AND id=r.conversation_id;
          IF c.version<r.accepted_context_version OR c.human_context_revision_id IS NULL OR c.human_observation_epoch<r.observation_epoch
            OR (c.human_context_revision_id<>r.id AND NOT EXISTS(SELECT 1 FROM platform.human_context_reconciliations child WHERE child.workspace_id=r.workspace_id AND child.conversation_id=r.conversation_id AND child.previous_revision_id=r.id)) THEN
            RAISE EXCEPTION 'uncommitted native pointer atom' USING ERRCODE='23514'; END IF;
        ELSIF TG_TABLE_NAME IN ('telegram_provenance','human_context_observations') THEN
          IF TG_TABLE_NAME='telegram_provenance' THEN
            SELECT * INTO s FROM platform.telegram_provenance WHERE receipt_id=NEW.receipt_id;
          ELSE SELECT * INTO s FROM platform.telegram_provenance WHERE workspace_id=NEW.workspace_id AND receipt_id=NEW.first_source_receipt_id; END IF;
          IF s.receipt_id IS NULL THEN RETURN NULL; END IF;
          IF s.human_context_observation_id IS NOT NULL THEN
            SELECT * INTO STRICT o FROM platform.human_context_observations WHERE workspace_id=s.workspace_id AND id=s.human_context_observation_id;
            IF o.connection_id IS DISTINCT FROM s.connection_id OR o.provider_chat_id IS DISTINCT FROM s.projection->>'chat_id'
              OR o.semantic_digest IS DISTINCT FROM platform.human_context_observation_digest(o.workspace_id,o.conversation_id,o.client_id,o.connection_id,s.projection)
              OR s.projection->>'discriminator' NOT IN ('NEW','EDIT','DELETE') OR s.codec<>2 THEN
              RAISE EXCEPTION 'invalid native source observation' USING ERRCODE='23514'; END IF;
            IF TG_TABLE_NAME='human_context_observations' THEN IF o.id<>NEW.id THEN RAISE EXCEPTION 'invalid first native source' USING ERRCODE='23514'; END IF; END IF;
          ELSIF TG_TABLE_NAME='human_context_observations' THEN RAISE EXCEPTION 'missing first native source' USING ERRCODE='23514'; END IF;
          IF s.inbox_id IS NOT NULL THEN
            SELECT * INTO STRICT i FROM platform.inbox_events WHERE workspace_id=s.workspace_id AND id=s.inbox_id;
            IF (i.human_context_source_receipt_id IS NOT NULL OR i.human_context_observation_id IS NOT NULL) AND
              (i.human_context_source_receipt_id,i.human_context_observation_id) IS DISTINCT FROM (s.receipt_id,s.human_context_observation_id) THEN
              RAISE EXCEPTION 'invalid queued native source' USING ERRCODE='23514'; END IF;
          END IF;
        ELSIF TG_TABLE_NAME='inbox_events' THEN
          SELECT * INTO i FROM platform.inbox_events WHERE workspace_id=NEW.workspace_id AND id=NEW.id;
          IF i.human_context_source_receipt_id IS NOT NULL THEN
            SELECT * INTO s FROM platform.telegram_provenance WHERE workspace_id=i.workspace_id AND receipt_id=i.human_context_source_receipt_id;
            IF (s.inbox_id,s.connection_id,s.human_context_observation_id) IS DISTINCT FROM (i.id,i.connection_id,i.human_context_observation_id) THEN
              RAISE EXCEPTION 'invalid native inbox binding' USING ERRCODE='23514'; END IF;
          END IF;
        ELSIF TG_TABLE_NAME='human_context_policy_receipts' THEN
          SELECT * INTO receipt FROM platform.human_context_policy_receipts WHERE workspace_id=NEW.workspace_id AND id=NEW.id;
          IF NOT FOUND THEN RETURN NULL; END IF;
          SELECT * INTO STRICT a FROM app.audit_events WHERE workspace_id=receipt.workspace_id AND audit_event_id=receipt.audit_event_id;
          IF receipt.result IS DISTINCT FROM platform.human_context_policy_result(receipt)
            OR a.payload IS DISTINCT FROM jsonb_build_object('receipt_id',receipt.id,'operation',receipt.operation,'change',receipt.change,
              'previous_policy',receipt.expected_policy,'accepted_policy',receipt.accepted_policy,'previous_policy_epoch',receipt.expected_policy_epoch::text,
              'accepted_policy_epoch',receipt.accepted_policy_epoch::text) THEN RAISE EXCEPTION 'invalid native policy evidence' USING ERRCODE='23514'; END IF;
        END IF;
        RETURN NULL;
      END $$""")
    for table, events in (
        ("app.conversations", "UPDATE"),
        ("platform.human_context_observations", "INSERT"),
        ("platform.human_context_reconciliations", "INSERT"),
        ("platform.conversation_control_receipts", "INSERT"),
        ("platform.messaging_jobs", "INSERT OR UPDATE"),
        ("platform.inbox_events", "UPDATE"),
    ):
        op.execute(
            f"CREATE TRIGGER native_integrity BEFORE {events} ON {table} FOR EACH ROW EXECUTE FUNCTION platform.human_context_integrity()"
        )
    for table in (
        *TABLES,
        "platform.telegram_provenance",
        "platform.inbox_events",
        "app.audit_events",
    ):
        op.execute(
            f"CREATE CONSTRAINT TRIGGER native_consistent AFTER INSERT OR UPDATE ON {table} DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.human_context_consistent()"
        )


def _work_replays() -> None:
    # One token-only lookup before admission; accepted result replays stay first.
    lookup = FUNCTIONS["platform.human_context_work_replay(uuid,uuid)"].replace(
        "platform.human_context_work_replay(", "platform.human_context_work_lookup(", 1
    )
    _define(lookup)
    _define(r"""CREATE FUNCTION platform.human_context_stale() RETURNS jsonb
      LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      BEGIN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END $$""")
    _define(r"""CREATE OR REPLACE FUNCTION platform.human_context_work_replay(p_job uuid,p_claim uuid) RETURNS jsonb
      LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      SELECT coalesce(platform.human_context_work_lookup(p_job,p_claim),platform.human_context_stale()) $$""")
    sql = FUNCTIONS["platform.human_context_wait(uuid,uuid,text)"].replace(
        "SELECT platform.human_context_work_replay(", "SELECT platform.human_context_work_lookup("
    )
    _define(sql.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1))
    names = (
        "guard_turn_prepare(2)",
        "guard_turn_accept(4)",
        "guard_send_begin(2)",
        "turn_execute(2)",
        "turn_consumer_finalize(3)",
        "escalation_request_for_turn(2)",
    )
    for name in names:
        signature = next(
            k for k in FUNCTIONS if k.startswith("platform." + name.split("(")[0] + "(")
        )
        sql = FUNCTIONS[signature]
        sql = sql.replace(
            "DECLARE j platform.messaging_jobs%ROWTYPE;",
            "DECLARE native_saved jsonb; j platform.messaging_jobs%ROWTYPE;",
            1,
        )
        replay = "SELECT platform.human_context_work_lookup(p_job,p_claim) INTO native_saved; IF native_saved IS NOT NULL THEN RETURN native_saved; END IF;\n        "
        if name in ("guard_turn_accept(4)", "turn_consumer_finalize(3)"):
            anchor = (
                "BEGIN\n          PERFORM platform.messaging_admit"
                if name == "turn_consumer_finalize(3)"
                else "BEGIN PERFORM platform.messaging_admit"
            )
            assert anchor in sql, name
            sql = sql.replace(anchor, replay + anchor, 1)
        elif name == "escalation_request_for_turn(2)":
            anchor = "j:=platform.messaging_guard(p_job,p_claim);"
            replay = (
                "BEGIN RETURN platform.escalation_request_replay(p_job,p_claim); EXCEPTION WHEN SQLSTATE 'P2001' THEN IF SQLERRM<>'STALE_CLAIM' THEN RAISE; END IF; END;\n        "
                + replay
            )
            sql = sql.replace(anchor, replay + anchor, 1)
        else:
            sql = sql.replace(
                "j:=platform.messaging_guard(p_job,p_claim);",
                replay + "j:=platform.messaging_guard(p_job,p_claim);",
                1,
            )
        _define(sql.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1))


def _policy() -> None:
    _define(r"""CREATE FUNCTION platform.human_context_policy_result(r platform.human_context_policy_receipts) RETURNS jsonb
      LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      SELECT jsonb_build_object('receipt_id',r.id,'workspace_id',r.workspace_id,'connection_id',r.connection_id,
        'operation',r.operation,'change',r.change,'previous_policy',r.expected_policy,'accepted_policy',r.accepted_policy,
        'previous_policy_epoch',r.expected_policy_epoch::text,'accepted_policy_epoch',r.accepted_policy_epoch::text,
        'actor_kind','LOCAL_PROVISIONER','actor_db_role',r.actor_db_role,'audit_event_id',r.audit_event_id,
        'accepted_at',to_char(r.accepted_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"')) $$""")
    _define(r"""CREATE FUNCTION platform.human_context_policy_command(ws uuid,p_connection uuid,p_operation text,p_key text,
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
      END $$""")
    _define(r"""CREATE FUNCTION platform.human_context_policy_guard() RETURNS trigger
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      BEGIN
        IF TG_TABLE_NAME='telegram_connection_state' THEN
          IF OLD.material_enabled AND NOT NEW.material_enabled AND EXISTS(SELECT 1 FROM app.channel_connections
            WHERE workspace_id=NEW.workspace_id AND id=NEW.connection_id AND human_context_policy='ON') THEN
            RAISE EXCEPTION 'native policy must pause before material disable' USING ERRCODE='23514'; END IF;
        ELSIF (NEW.human_context_policy,NEW.human_context_policy_epoch) IS DISTINCT FROM (OLD.human_context_policy,OLD.human_context_policy_epoch) THEN
          IF ((OLD.human_context_policy IN ('OFF_UNUSED','PAUSED') AND NEW.human_context_policy='ON' AND NEW.human_context_policy_epoch::numeric=OLD.human_context_policy_epoch::numeric+1)
            OR (OLD.human_context_policy='ON' AND NEW.human_context_policy='PAUSED' AND NEW.human_context_policy_epoch=OLD.human_context_policy_epoch)) IS NOT TRUE
            OR NOT EXISTS(SELECT 1 FROM platform.human_context_policy_receipts WHERE workspace_id=NEW.workspace_id AND connection_id=NEW.id
              AND expected_policy=OLD.human_context_policy AND expected_policy_epoch=OLD.human_context_policy_epoch
              AND accepted_policy=NEW.human_context_policy AND accepted_policy_epoch=NEW.human_context_policy_epoch) THEN
            RAISE EXCEPTION 'invalid native policy transition' USING ERRCODE='23514'; END IF;
        END IF;
        RETURN NEW;
      END $$""")
    op.execute(
        "CREATE TRIGGER native_policy_guard BEFORE UPDATE ON app.channel_connections FOR EACH ROW EXECUTE FUNCTION platform.human_context_policy_guard()"
    )
    op.execute(
        "CREATE TRIGGER native_policy_guard BEFORE UPDATE ON platform.telegram_connection_state FOR EACH ROW EXECUTE FUNCTION platform.human_context_policy_guard()"
    )


BASELINE_FUNCTION_PROFILES = {
    "platform.resolve_workspace_membership(uuid,uuid)": (
        "8ce9bdd67c17bc83442bea3a5e7a15337a51074e0ea6408855b10542e39ceb39",
        "sql",
        True,
        "v",
    ),
    "app.current_workspace_id()": (
        "f6c6760e5de3ce4885b0c27daf1ab82867438c4c1ec19d95cb084bb4e799475d",
        "plpgsql",
        True,
        "s",
    ),
    "platform.auth_password_lookup(text)": (
        "a972cb3994842757f18045afae2ac0f00d90020d482a62043376ecd3ee5b22e3",
        "sql",
        True,
        "s",
    ),
    "platform.auth_lock_session(text,boolean)": (
        "55ca74ab7475f964865b6d3a6b73778f7139add6a1531781b14362fef0f30428",
        "plpgsql",
        True,
        "v",
    ),
    "platform.auth_bootstrap(text,integer)": (
        "6eb28b55313391c9d0eb07ca055ff8754e49b83cfeef132d9ba413077545c5dd",
        "plpgsql",
        True,
        "v",
    ),
    "platform.auth_session(text)": (
        "5e1e2ceaad4b2b1452a02d4d04f7f5d53ebf40e5067b7223baf5a2edc65253f4",
        "plpgsql",
        True,
        "v",
    ),
    "platform.auth_memberships(text)": (
        "0e684da56252678c7bc27b962a49c4213c3de9865a63b43e552221b36ab9b7fb",
        "plpgsql",
        True,
        "v",
    ),
    "platform.auth_login(text,uuid,bigint,bigint,text,integer)": (
        "3f975835d787dd8531c415783aa7492facafcbd5d9def911703780bb1bfc83c1",
        "plpgsql",
        True,
        "v",
    ),
    "platform.auth_rotate(text,text)": (
        "7978763cff421212ae6e184771aa26468cf6be997f29ac386c256dfc0b0640b4",
        "plpgsql",
        True,
        "v",
    ),
    "platform.auth_logout(text)": (
        "67f05d0d9e47e103cd71365e8f9e574bdd6bcff42dbe156d9f6a68c1b04149e2",
        "plpgsql",
        True,
        "v",
    ),
    "platform.guard_plan_revision()": (
        "9ae94c6c1e0a8b05eeeac31db412d4cd5c8f4157bdae437664c82f5f0fc2c33b",
        "plpgsql",
        False,
        "v",
    ),
    "platform.guard_entitlement()": (
        "bed228f9542f5a6f85f28e17f47ab11f3524ab52fb648f4452c9dca4485efe06",
        "plpgsql",
        False,
        "v",
    ),
    "platform.initialize_local_billing(uuid,text,integer,text,text,text,timestamptz,timestamptz,text)": (
        "20b0e1ea5d37d8710b485232cff1441ea7c6998d431233877d2ab1814f620e83",
        "plpgsql",
        True,
        "v",
    ),
    "platform.update_billing_contact(bigint,text,text)": (
        "80d0ce6854e33601584fe350ee4b586796d0066b6288bf9a26aeec80aa23f3ed",
        "plpgsql",
        True,
        "v",
    ),
    "platform.messaging_valid_id(text,integer,integer)": (
        "9e1cf327f38fa1437a5a755e3c68d531c0209b585722755c865b395f616419f5",
        "sql",
        False,
        "i",
    ),
    "platform.messaging_validate_event(jsonb)": (
        "1f7a2405bde9171aa196355bfae185cbc4084aeffbbdfda20d4f8828fdb95791",
        "plpgsql",
        False,
        "v",
    ),
    "platform.messaging_fingerprint(jsonb,boolean)": (
        "d64c3b2ea0f53e0861315883b7420e5aee652b28dffa093bce0d3fff2986a342",
        "plpgsql",
        False,
        "i",
    ),
    "platform.messaging_immutable()": (
        "3971e82a86a3826eeaf7b9e24458fbb1adc64cce0e8f2cb43a46384348519934",
        "plpgsql",
        False,
        "v",
    ),
    "app.current_messaging_owner_workspace_id()": (
        "8ffbd40db1c507c7384981d683bf671cc1914b088d61aa543c8a2a2d44debee6",
        "plpgsql",
        True,
        "s",
    ),
    "platform.messaging_lock_owner(uuid,uuid)": (
        "11168bbd30eec24cfdb0ad9de67c70f767c0bf62480c7579638e58ecfb42bce1",
        "plpgsql",
        True,
        "v",
    ),
    "platform.messaging_job_json(platform.messaging_jobs)": (
        "7ccc5395def311a662f2b4845b33ce5e85af7c94d5920ddb03b97bcb2d37a5f3",
        "sql",
        False,
        "s",
    ),
    "platform.messaging_guard(uuid,uuid)": (
        "0a57433b9b39446547a2f2accfeb9516238ae8c9210f67773e30f749a756adb5",
        "plpgsql",
        True,
        "v",
    ),
    "platform.messaging_reschedule(uuid,text,boolean)": (
        "6409aa21554ccaa346587c2f4da07bc6941e27c4736db9bd518f26e4c7947438",
        "sql",
        True,
        "v",
    ),
    "platform.messaging_ingest(text,text,jsonb,uuid)": (
        "2833a40d4ec37a014eab30fcbe2893a590d50c909b71eebc754e1c575ecb9f32",
        "plpgsql",
        True,
        "v",
    ),
    "platform.messaging_admit(uuid,uuid)": (
        "27d0551d90b2f854b54a8b9fff35ff92bff9b131de4653000015026460fefc31",
        "plpgsql",
        True,
        "v",
    ),
    "platform.messaging_process_inbox(uuid,uuid)": (
        "5a63a698c440120cebeaf4c6ebf8133f04abf41f610ef2ad3c3e34312b4ef2e3",
        "plpgsql",
        True,
        "v",
    ),
    "platform.messaging_retry(uuid,uuid,text,boolean)": (
        "03db5c8fe85305fbdf72b93cbb3706b361c83bb719106ea8fcd7637c5abb1f45",
        "plpgsql",
        True,
        "v",
    ),
    "platform.messaging_request_text(uuid,text,text)": (
        "13dc01a5b25f4b2d5da4835fa8aabf14f33f98573532e730929006688be7059c",
        "plpgsql",
        True,
        "v",
    ),
    "platform.messaging_begin_send(uuid,uuid)": (
        "ced9aced8fef1976bae75cedc268ed5a25b651c01fb276502bcc77badc8453e1",
        "plpgsql",
        True,
        "v",
    ),
    "platform.messaging_finish_send(uuid,uuid,uuid,text,text,text)": (
        "4c6db15c26212a1a943e58eaf3f6355988380106a2be7ed04832ab6c8c673a0b",
        "sql",
        True,
        "v",
    ),
    "platform.messaging_read_conversations(integer)": (
        "aaeb0c33dd9e7501e92c3bcb599e38073bfeef8c3f3b7352cd22ef4a4b60e040",
        "plpgsql",
        True,
        "v",
    ),
    "platform.messaging_read_messages(uuid,integer)": (
        "fcfa6f29a181d0e97ce52ae98ec0d008859e6568ad118e89234a5ed5b932a460",
        "plpgsql",
        True,
        "v",
    ),
    "platform.messaging_read_delivery(uuid)": (
        "f3cdd1d7de19b740961b0f4a6aece317b4fdd4ef1dafcfc9ce25ab6908bc29ed",
        "plpgsql",
        True,
        "v",
    ),
    "platform.messaging_read_inbox(uuid)": (
        "7666d3eb0bc87de36bb75b4a7a8f9ab4e31f329f5fcd2fbaccc275d819b6d171",
        "plpgsql",
        True,
        "v",
    ),
    "platform.files_immutable()": (
        "da3e6c650e8c2ed10ad61169127e0808370857c1d458e05b49c37b7db78c4bc2",
        "plpgsql",
        False,
        "v",
    ),
    "platform.files_manifest_valid(jsonb)": (
        "3a4dbfe98efa8df5455d6ac60aeec88250d7ea110408aed5a323557b480eaf67",
        "plpgsql",
        False,
        "i",
    ),
    "platform.files_upload_json(platform.file_object_uploads)": (
        "56d0788594b3d549f87cac1980dd152d902cebb3ba9cd758066fa281c1449c40",
        "sql",
        False,
        "s",
    ),
    "platform.files_plan(uuid,uuid,uuid)": (
        "ec5f05ae04a2d4bc0ee91f99a6db768801c78890761f255a86001e8f413ead22",
        "plpgsql",
        True,
        "v",
    ),
    "platform.files_begin_fetch(uuid,uuid)": (
        "b613633a1c13e033a051e593182d275502a7b1ed9e586a8351e494ca7f394347",
        "plpgsql",
        True,
        "v",
    ),
    "platform.files_prepare_upload(uuid,uuid,jsonb)": (
        "da20120cf752fc9a0be9b31d19efdd081949391b3ff3b12b72f68e3254192a9f",
        "plpgsql",
        True,
        "v",
    ),
    "platform.files_finish_fetch(uuid,uuid,uuid)": (
        "185f336920b32f3f5c21f300ee76f456610e65164b2a39eca7539948e4c00932",
        "plpgsql",
        True,
        "v",
    ),
    "platform.files_claim_cleanup(integer)": (
        "5961679941084084fb083ec755861f9db3ecb0792f57e24fe338eb6df42bf143",
        "plpgsql",
        True,
        "v",
    ),
    "platform.files_finish_cleanup(uuid,uuid,text)": (
        "f25b769900d682dbf58e53f68dad2952162604bcde386343115f86b504aba39d",
        "plpgsql",
        True,
        "v",
    ),
    "platform.files_read_manifest(uuid,uuid,uuid)": (
        "586d58424a80d3eca338f74863d5b2ce4b0b4d97ad62d7aa72862d0374f4bfd7",
        "plpgsql",
        True,
        "v",
    ),
    "platform.telegram_numeric_id(text)": (
        "1519829aa6e3dfc1ac03180377c72929d7a7a3dcedd1b037ae7d3ea4872413cf",
        "sql",
        False,
        "i",
    ),
    "platform.telegram_validate_projection(text,jsonb)": (
        "0d088863a241460dcc16b7ea45072bb7ac03303bfba9f4d2e13e0b91b5e4500b",
        "plpgsql",
        False,
        "v",
    ),
    "platform.telegram_fingerprint(text,jsonb)": (
        "449929a9e41d6e4f38d30341fcb7c7a488d55f06169dbaca2c18df461effdc06",
        "plpgsql",
        False,
        "i",
    ),
    "platform.telegram_validate_observation(jsonb)": (
        "5aefbca98cb203f4bfc5e65101fbb6432c492858ac55fdae0b48fec520855ffc",
        "plpgsql",
        False,
        "v",
    ),
    "platform.messaging_lock_billing_workspace(uuid)": (
        "8797320c11ace5b9c44b37ed511293f0f61af6c0ba1b58abcd5cd60b5ec27204",
        "plpgsql",
        True,
        "v",
    ),
    "platform.messaging_lock_billing()": (
        "69f212c164437a4b39942e87f32c53df5cb4fb8e5f2bf9da2e1952e98be180eb",
        "plpgsql",
        True,
        "v",
    ),
    "platform.messaging_manual_send_allowed(uuid)": (
        "4ce13d4ca64dbc09aada275a295d76a01a08ac809768a2448fb1e1f074cd4bd6",
        "plpgsql",
        True,
        "v",
    ),
    "platform.initialize_local_messaging_billing(uuid,text,timestamptz,timestamptz)": (
        "2863259a15ff3178525d044704c26dbc57c35e4322f5412bed6dd13989098f7d",
        "plpgsql",
        True,
        "v",
    ),
    "platform.telegram_probe_json(platform.telegram_connection_state)": (
        "bce40873beb21b5aa8c5b850468f9f5fce85a865a60567066129998f75e0c273",
        "sql",
        False,
        "s",
    ),
    "platform.initialize_telegram_connection(uuid,uuid,text,text,text,jsonb)": (
        "bfae87784d2145810f9ed12f1dfab4416d8041c9d2044c1397204bbe0f8275bf",
        "plpgsql",
        True,
        "v",
    ),
    "platform.telegram_save_observation(uuid,uuid,bigint,bigint,jsonb)": (
        "97d4fe38521a276d4aac005feddf587a6c296e5e58ca909167cbcbb123be4816",
        "plpgsql",
        True,
        "v",
    ),
    "platform.telegram_can_send(uuid,uuid,uuid,boolean)": (
        "b273ad02ca6825bdf6b037173c3be840a615d551283c3e922357bee3f7f16811",
        "plpgsql",
        True,
        "v",
    ),
    "platform.telegram_ingest(text,jsonb,uuid)": (
        "2b3f3b8ea257c382552771fb61793fe265d878c2730d1044520a28f513bb7f63",
        "plpgsql",
        True,
        "v",
    ),
    "platform.messaging_prepare_text(uuid,text,text)": (
        "39c14deb5337876f28970605ea399f9106f5e768e9f8f8c54b2e3746d570bca9",
        "plpgsql",
        True,
        "v",
    ),
    "platform.telegram_owner_observe(uuid,bigint,bigint,jsonb)": (
        "8ecd18d13fe815311aa9b076b3313efb98bbc3276962c44932516c5692666380",
        "plpgsql",
        True,
        "v",
    ),
    "platform.telegram_worker_probe(uuid,uuid)": (
        "deb02e9c206d3b87338685c20d197e983365ee828c8b0955c4bed2935e9fa0a8",
        "plpgsql",
        True,
        "v",
    ),
    "platform.telegram_begin_send(uuid,uuid,bigint,bigint,jsonb)": (
        "c8f15c23837fa40b86451574ee3e04cc4292dd91b2929a891424e0d8acec556d",
        "plpgsql",
        True,
        "v",
    ),
    "platform.messaging_reschedule(uuid,text,boolean,integer)": (
        "21e8b16de21a18ff5646eeb28f7eceb801da8ab5bfc7d8e1799e6a91b9a2d074",
        "sql",
        True,
        "v",
    ),
    "platform.messaging_finish_send(uuid,uuid,uuid,text,text,text,integer)": (
        "5453db772462122e0d6afbd0ba1bbab2a74171e75deb35ac5e9beec60e1ac592",
        "plpgsql",
        True,
        "v",
    ),
    "platform.messaging_read_connections(integer,timestamptz,uuid)": (
        "242c6123fd6c57c44eb8c9ff658fe437700144b9e6525fff6c2ccf24c892511b",
        "plpgsql",
        True,
        "v",
    ),
    "platform.messaging_read_conversations(integer,timestamptz,uuid)": (
        "81949cfd2357e8886003e7c5618fed4a7ce2b4d4474c2764c377783e97ed9658",
        "plpgsql",
        True,
        "v",
    ),
    "platform.messaging_read_messages(uuid,integer,timestamptz,uuid)": (
        "9e57b5793933fedc3398804efe690e73ccdcc58f0ff2efb78c7e89132db33272",
        "plpgsql",
        True,
        "v",
    ),
    "platform.turn_require_isolation()": (
        "ba0e99b67e71fc6d6fa6886967282f9c5bcf7b0046e5812d34dfdfc5df8dd5d3",
        "plpgsql",
        False,
        "v",
    ),
    "platform.turn_ingress()": (
        "d8e6040eae9ce55f0e6d8f2b1338d4ea2e3b6b8a7d25f2e7da8963032e6488f0",
        "plpgsql",
        True,
        "v",
    ),
    "platform.turn_immutable()": (
        "bfc42050fa3442c8eed763a861d16ae7fc6ea3f5f3646a193e54fe22704a7df9",
        "plpgsql",
        False,
        "v",
    ),
    "platform.turn_member_check()": (
        "8cbbd5b8ccd97858edc24ba68fd904e5b4af3068b355e506d7d5cc03af5b6293",
        "plpgsql",
        True,
        "v",
    ),
    "platform.turn_members_consistent()": (
        "3acccfede293794fcc84890da99535a2730217fd1f11eb37c7ed153e2c675405",
        "plpgsql",
        True,
        "v",
    ),
    "platform.turn_enqueue(uuid,uuid,uuid)": (
        "383110c7c42c8979410560f3d0d98b784844f5da16a0a1d7f8d04fb71bd26e5f",
        "plpgsql",
        True,
        "v",
    ),
    "platform.turn_seal(uuid,uuid,timestamptz,uuid,boolean)": (
        "bc83afb9ce59538928edfe86cdc74c7ab1951640244570d05177aa3bcd08676f",
        "plpgsql",
        True,
        "v",
    ),
    "platform.turn_group_message(uuid,uuid,uuid)": (
        "89687e327f17d1a00751192fda5a56e7aeac8297b539fe95b1317d01de8d78f7",
        "plpgsql",
        True,
        "v",
    ),
    "platform.turn_material()": (
        "be30caa9fdb5cf0c3ca22e41559232e6cbe8d6246c62e9c343db539ec4303f3d",
        "plpgsql",
        True,
        "v",
    ),
    "platform.turn_preflight(platform.messaging_jobs,boolean,boolean)": (
        "e837030dab29947ad6f4cd6aa1e1dbffc420fac56fed7cd09c769619e90b467f",
        "plpgsql",
        True,
        "v",
    ),
    "platform.turn_supersede(platform.messaging_jobs)": (
        "9f11aa0ea390402734ac650a3779ec2908e8e9840279277e4c7e7e992b878475",
        "plpgsql",
        True,
        "v",
    ),
    "platform.messaging_reschedule(uuid,text,boolean,integer,boolean)": (
        "3cb1f50eafe5134359149e48d12979be27b94e1a9b7cc734a50d49b7cb32bcd3",
        "plpgsql",
        True,
        "v",
    ),
    "platform.messaging_claim(text,timestamptz,timestamptz,uuid)": (
        "3fc524b9e491f8a65e2af081caa26286032e5c7f37878962fa26654a1abd213a",
        "plpgsql",
        True,
        "v",
    ),
    "platform.messaging_recover_expired(timestamptz,timestamptz,uuid)": (
        "f7d1c35c7ead9192c4d1dbd375b027d87f40c9a9db0769fead8daa677a202448",
        "plpgsql",
        True,
        "v",
    ),
    "platform.turn_snapshot(uuid,uuid)": (
        "0e8c8ba6b4f98e4a0ed9bf63c7bd683568a751ef6c2f3c218e76b1ece7426dcd",
        "plpgsql",
        True,
        "v",
    ),
    "platform.turn_execute(uuid,uuid)": (
        "550360b423589def4e0d0038d50594ae48c6526d72d9680e6de378c9c5d15d3c",
        "plpgsql",
        True,
        "v",
    ),
    "platform.turn_consumer_replay(uuid,uuid)": (
        "4469b30f0df26f6bfb02777b2c5c8da184abc5b3bcae8dcdf45c871d9bbb7e6c",
        "plpgsql",
        True,
        "s",
    ),
    "platform.turn_consumer_finalize(uuid,uuid,jsonb)": (
        "05f45613f1f9295795d160cfc7015e990ddb4f20dd1f0994b97b034830d24648",
        "plpgsql",
        True,
        "v",
    ),
    "platform.conversation_control_fingerprint(uuid,uuid,uuid,uuid,text,bigint,bigint)": (
        "60cd026890baa0f09e98c3742ab8da80d5a44fd243fa16d983ea42dcabd2459a",
        "sql",
        False,
        "i",
    ),
    "platform.conversation_control_locked(uuid,uuid,text,text,bigint,bigint)": (
        "0609192f801e87cb185525047a79af365e868c19f6974ce0d35c4a33388d96d0",
        "plpgsql",
        True,
        "v",
    ),
    "platform.conversation_control_prepare(uuid,uuid,text,text,bigint,bigint)": (
        "3d9ce63a7e8b9787adfe7ae96e77a42d6e1af57835f57351fb8846d7e3e07c35",
        "plpgsql",
        True,
        "v",
    ),
    "platform.conversation_control_execute(uuid,uuid,text,text,bigint,bigint)": (
        "d14a6a06696e98c7779870cad324a8f18ddce723525bdb7da8de3c2098e82379",
        "plpgsql",
        True,
        "v",
    ),
    "platform.conversation_control_read(uuid)": (
        "e30448916cece6ee18500c1ef5e9399b1c50dd8a2fad7f95c3cded2cf512f9b8",
        "plpgsql",
        True,
        "v",
    ),
    "platform.conversation_manual_prelock(uuid,text,text)": (
        "0cf8c71a6028ddd08508f9132991d891b6cada8e50c2c5b831b9bc4be2d3c65f",
        "plpgsql",
        True,
        "v",
    ),
    "platform.conversation_manual_takeover(uuid,uuid)": (
        "88a05e4aa03904af8f8ec54e8544dbe867b1f7f22404becef415b76cdf3e3d29",
        "plpgsql",
        True,
        "v",
    ),
    "platform.conversation_turn_activation_matches(uuid,uuid)": (
        "ed3f021b97d11656125233eac69944bfb4a3cf09abe761d63c8cc14d531e90a5",
        "sql",
        True,
        "v",
    ),
    "platform.guard_text_fingerprint(jsonb,text)": (
        "d22ae019b3f8391ee43bb7e5f8889364694e8c59924f1712cc8533074da76bc2",
        "sql",
        False,
        "i",
    ),
    "platform.guard_require_current(uuid,uuid,uuid,bigint)": (
        "cf8bb99813a87fff550059710b3fd6e4917e17d8e5b4cbe0b8b8783ed0a40e2f",
        "plpgsql",
        True,
        "v",
    ),
    "platform.guard_turn_prepare(uuid,uuid)": (
        "00b9043ffa3f223f7632dc162854c3631602405d37afada22da5c6adc091a3df",
        "plpgsql",
        True,
        "v",
    ),
    "platform.guard_turn_replay(uuid,uuid,text,text)": (
        "e919531e4ea823def1545555aa00c91d9ac1b8b0ce9e67d8f2c698bfcb875889",
        "plpgsql",
        True,
        "s",
    ),
    "platform.guard_turn_accept(uuid,uuid,text,text)": (
        "446eeb8ac6973daf4aa6ddd95d92d6759eadd07514951c93d7979ce67a624edd",
        "plpgsql",
        True,
        "v",
    ),
    "platform.guard_send_begin(uuid,uuid)": (
        "7d7aed4b011f082e7926be5b19ab1065fd937728e3096841f4823a37de590c22",
        "plpgsql",
        True,
        "v",
    ),
    "platform.escalation_now()": (
        "31ebb037ed35337329fa522d1b51d159d7ed91eccc95e3694b2338abbcea74b1",
        "sql",
        False,
        "v",
    ),
    "platform.escalation_command_fingerprint(uuid,uuid,uuid,uuid,uuid,text,bigint,bigint,bigint,text)": (
        "83bc68632b05e2b1cc74ecb8ac81c595034dccb634182b93fa5335633ebd5c0c",
        "sql",
        False,
        "i",
    ),
    "platform.escalation_immutable()": (
        "a3802e3fddcbcdedfe6286b1c0a66693566761451099068ccb0e3ffae2555ef3",
        "plpgsql",
        True,
        "v",
    ),
    "platform.escalation_context_changed()": (
        "e9653e9625316e84df64a98386a5b4b8addd534032076eb236433f655b65b67f",
        "plpgsql",
        True,
        "v",
    ),
    "platform.escalation_validity(uuid,uuid,timestamptz)": (
        "2185d597e6ae580e5c48d4c03bda56f44865d7d2ef89a94b4815741c8ead7b1e",
        "sql",
        True,
        "s",
    ),
    "platform.escalation_request_replay(uuid,uuid)": (
        "1e10c8742b9e58fee2780d55d44af2bfb097b0114afae0b2647a201f0416f989",
        "plpgsql",
        True,
        "s",
    ),
    "platform.escalation_request_for_turn(uuid,uuid)": (
        "da8b66d0e0e2a0ce787ea2e7c720ebb790b20366f221137648938827a418bac8",
        "plpgsql",
        True,
        "v",
    ),
    "platform.escalation_timer_execute(uuid,uuid)": (
        "0bbd68c40bcae571fde899c57a51f1628fea26238e662ff015ed428ca8dfd7b3",
        "plpgsql",
        True,
        "v",
    ),
    "platform.escalation_read(uuid)": (
        "bd97929c0beb02bd87fd39cdd45d2a42f02311847ee0788d54f8233231aa0e92",
        "plpgsql",
        True,
        "v",
    ),
    "platform.escalation_list(integer,text,timestamptz,uuid)": (
        "d744f557e3621c5394b3730052a67f3f600f9f263603511621f1c091ca25d484",
        "plpgsql",
        True,
        "v",
    ),
    "platform.escalation_command(uuid,uuid,uuid,text,text,bigint,bigint,bigint,text)": (
        "25aeb0596f6edfa2bbb51c96e485193edf33e9f2941b0b3aab2f30f8b8834c1e",
        "plpgsql",
        True,
        "v",
    ),
    "platform.material_object(jsonb,text[])": (
        "aa02c1b4b7f6ad7ac3687dccee0f680b231876af0bc78d5d149b4cc6d08d40bf",
        "sql",
        False,
        "i",
    ),
    "platform.material_content_valid(jsonb)": (
        "c89faf57741e2b8d179b4201aac7979e891984e867ecb27bfc455a66c0104da4",
        "plpgsql",
        False,
        "i",
    ),
    "platform.material_semantic(jsonb)": (
        "f1ec36fd862ecf60cd69b1f1d1e41b7c09cfab38a689f6127d0969541985bb92",
        "sql",
        False,
        "i",
    ),
    "platform.material_state_valid(jsonb)": (
        "a2344f16e36d45187529757a8bd2c9fad1f0b2c6c6887ab81b631279a65f10c1",
        "sql",
        False,
        "i",
    ),
    "platform.telegram_validate_v2(text,jsonb)": (
        "7304efba94d26f93ba4d7a69030878056eb611f855ee4620a3ea6cdf61f79003",
        "plpgsql",
        False,
        "v",
    ),
    "platform.telegram_fingerprint_v2(text,jsonb)": (
        "4499d0bd8bc0ad010d856d3e20b21847a9cfedfaeced5c14ace118443c2a940f",
        "plpgsql",
        False,
        "i",
    ),
    "platform.material_result_valid(jsonb)": (
        "6070c0641ab897095effdd4f841e0e34e8cc1b788d33dd64c5ef6d4cf2f6e9b6",
        "plpgsql",
        False,
        "v",
    ),
    "platform.telegram_receipt_json(platform.telegram_update_receipts,text)": (
        "d6c81a402d8c8b53aab72685cff893e34100973ed8c7a2aefa2ab3e9a6ef5800",
        "sql",
        True,
        "s",
    ),
    "platform.telegram_replay_v1(text,jsonb)": (
        "a3598d76df2c0bf876945fa306e0410e3249c2018ff62b21e4da2968beaacf32",
        "plpgsql",
        True,
        "v",
    ),
    "platform.material_integrity()": (
        "292dd9cbb24f1d2289b6e6b628160a8755841ecc4fbc4ab2a26a3c5c54cab7f7",
        "plpgsql",
        True,
        "v",
    ),
    "platform.material_target_check()": (
        "0c41bd7a4b3399c47a7cae6707e9bb28d98ed248e687b26ec58c094a9c6dd7b1",
        "plpgsql",
        True,
        "v",
    ),
    "platform.material_no_file()": (
        "5b01911a52d5fc64edbf23895a31d8316d34221fc4c399524f4932f4496ef892",
        "plpgsql",
        True,
        "v",
    ),
    "platform.message_effective(uuid,uuid)": (
        "7354f194d5c35a121421f41aad9740686de71519aea9879e762c111353777e82",
        "plpgsql",
        True,
        "v",
    ),
    "platform.material_turn_usable(uuid,uuid)": (
        "9f2f31ab578bb9d66f1bd8ed9d57f6dd9ae5a06b9427c1138d85f8121452c893",
        "sql",
        True,
        "v",
    ),
    "platform.material_identity(uuid,uuid,jsonb)": (
        "d4bb3911e0b35af35585df2307496147b4c02ab6ac6b4869fe53a3445eb9dca3",
        "plpgsql",
        True,
        "s",
    ),
    "platform.material_fold(uuid,uuid,uuid)": (
        "74d5202cf7fe15ae866dbd81eb88e635564a189db0195a9c0311c15fe76cecf8",
        "plpgsql",
        True,
        "v",
    ),
    "platform.material_apply_context(uuid,uuid,uuid,boolean)": (
        "22636529fed5a35055d99e9a42f52615626150300ad08d62918bbbfc9bce3069",
        "plpgsql",
        True,
        "v",
    ),
    "platform.material_apply(uuid,uuid,uuid,jsonb)": (
        "529e701178043d44c7e5cbee6c4651fae3e6a3a6be36412764ac1e8b60ac7c39",
        "plpgsql",
        True,
        "v",
    ),
    "platform.material_bump_turns(uuid,uuid[],uuid)": (
        "0019faf314594758579f035373f6e5d14d37a4cb9d3b75b4bb9c0a0116e09020",
        "plpgsql",
        True,
        "v",
    ),
    "platform.material_bind(uuid,uuid,boolean,uuid)": (
        "8afd09d2d0576c14480ce5a5414aa5d924082a007888932aec43dec185a19408",
        "plpgsql",
        True,
        "v",
    ),
    "platform.material_suppression_check()": (
        "6d19f17d542008095defb943095c9f9c894aa7441123806b24df110903cbaa52",
        "plpgsql",
        True,
        "v",
    ),
    "platform.material_processing_replay(uuid,uuid)": (
        "5d04cfdae703e4786f4d61975d484ec2c1686fcbec620c98e33dab7eafe94a96",
        "sql",
        True,
        "s",
    ),
    "platform.material_process(platform.messaging_jobs)": (
        "351d28449ee12317a4f046b8f70998b0e51206954146e45e91a6491995cdcd09",
        "plpgsql",
        True,
        "v",
    ),
}

BASELINE_COLUMNS = {
    "app.audit_events": (
        "workspace_id",
        "audit_event_id",
        "occurred_at",
        "actor_kind",
        "actor_user_account_id",
        "correlation_id",
        "event_type",
        "object_type",
        "object_id",
        "object_version",
        "payload",
        "billing_account_object_id",
        "message_object_id",
        "conversation_object_id",
        "conversation_control_generation",
        "escalation_object_id",
        "escalation_operation",
        "material_target_id",
        "material_source_receipt_id",
    ),
    "app.business_members": (
        "workspace_id",
        "id",
        "business_id",
        "user_account_id",
        "name",
        "role",
        "status",
        "version",
        "created_at",
    ),
    "app.businesses": ("workspace_id", "id", "name", "status", "version", "created_at"),
    "app.channel_connections": (
        "workspace_id",
        "id",
        "business_id",
        "provider",
        "bot_identity",
        "external_connection_id",
        "status",
        "version",
        "created_at",
    ),
    "app.client_identities": (
        "workspace_id",
        "id",
        "client_id",
        "provider",
        "external_user_id",
        "created_at",
    ),
    "app.clients": ("workspace_id", "id", "version", "created_at"),
    "app.conversation_turn_messages": (
        "workspace_id",
        "message_id",
        "turn_id",
        "conversation_id",
        "connection_id",
        "direction",
        "content_type",
        "origin_inbox_id",
        "turn_ingress_at",
        "turn_ingress_seq",
        "file_id",
        "membership_form",
        "initial_suppression_id",
        "suppression_disposition",
    ),
    "app.conversation_turns": (
        "workspace_id",
        "id",
        "conversation_id",
        "connection_id",
        "provider_chat_id",
        "revision",
        "control_generation",
        "state",
        "policy_version",
        "debounce_ms",
        "group_ms",
        "media_ms",
        "max_members",
        "member_count",
        "media_group_id",
        "first_ingress_at",
        "last_ingress_at",
        "hard_at",
        "quiet_at",
        "media_deadline_at",
        "seal_time",
        "closed_at",
        "ready_at",
        "readiness",
        "error_code",
        "created_at",
        "ingress_control_mode",
        "activation_fence_seq",
        "material_invalidated",
    ),
    "app.conversations": (
        "workspace_id",
        "id",
        "connection_id",
        "business_id",
        "client_id",
        "identity_id",
        "provider_chat_id",
        "version",
        "created_at",
        "last_client_inbound_at",
        "control_mode",
        "control_generation",
        "activation_fence_seq",
    ),
    "app.file_objects": (
        "workspace_id",
        "id",
        "message_id",
        "connection_id",
        "conversation_id",
        "required_direction",
        "required_content_type",
        "status",
        "winner_intent_id",
        "winner_state",
        "storage_key",
        "mime_type",
        "size_bytes",
        "sha256",
        "width",
        "height",
        "error_code",
        "version",
        "created_at",
        "completed_at",
    ),
    "app.locations": (
        "workspace_id",
        "id",
        "business_id",
        "name",
        "status",
        "version",
        "created_at",
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
        "version",
        "created_at",
    ),
    "app.outbox_events": (
        "workspace_id",
        "id",
        "connection_id",
        "message_id",
        "kind",
        "required_direction",
        "status",
        "attempt_id",
        "provider_message_id",
        "error_code",
        "completed_at",
        "version",
        "created_at",
    ),
    "platform.alembic_version": ("version_num",),
    "platform.auth_credentials": (
        "user_account_id",
        "login",
        "password_hash",
        "version",
        "created_at",
    ),
    "platform.auth_sessions": (
        "token_hash",
        "user_account_id",
        "credential_version",
        "account_version",
        "created_at",
        "expires_at",
        "revoked_at",
    ),
    "platform.billing_contact_command_receipts": (
        "workspace_id",
        "receipt_id",
        "billing_account_id",
        "operation",
        "idempotency_key",
        "request_fingerprint",
        "expected_version",
        "status",
        "result_version",
        "result_outcome",
        "created_at",
        "completed_at",
    ),
    "platform.channel_routes": (
        "workspace_id",
        "id",
        "connection_id",
        "provider",
        "bot_identity",
        "route_key",
        "created_at",
    ),
    "platform.file_object_uploads": (
        "workspace_id",
        "id",
        "file_id",
        "job_id",
        "claim_token",
        "storage_key",
        "mime_type",
        "size_bytes",
        "sha256",
        "width",
        "height",
        "status",
        "cleanup_claim_token",
        "cleanup_lease_until",
        "cleanup_attempts",
        "next_check_at",
        "last_checked_at",
        "cleanup_outcome",
        "version",
        "created_at",
    ),
    "platform.inbox_events": (
        "workspace_id",
        "id",
        "connection_id",
        "provider",
        "bot_identity",
        "external_connection_id",
        "required_direction",
        "event_id",
        "normalized_event",
        "event_fingerprint",
        "correlation_id",
        "received_at",
        "status",
        "result_code",
        "message_id",
        "completed_at",
        "version",
        "turn_ingress_at",
        "turn_ingress_seq",
        "turn_control_generation",
        "turn_control_mode",
        "turn_activation_fence_seq",
        "material_result",
        "material_claim_token",
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
    "platform.messaging_jobs": (
        "workspace_id",
        "id",
        "connection_id",
        "kind",
        "inbox_id",
        "outbox_id",
        "correlation_id",
        "status",
        "available_at",
        "claim_token",
        "lease_until",
        "worker_id",
        "attempt_count",
        "first_started_at",
        "error_code",
        "completed_at",
        "last_attempt_id",
        "last_claim_token",
        "last_outcome",
        "last_provider_message_id",
        "last_error_code",
        "version",
        "created_at",
        "file_id",
        "last_retry_after_seconds",
        "last_retry_due",
        "telegram_probe_claim",
        "telegram_probe_generation",
        "telegram_probe_version",
        "turn_id",
        "turn_revision",
        "step",
        "turn_outcome",
        "turn_input",
        "guard_rejection",
        "escalation_id",
        "escalation_outcome",
    ),
    "platform.plan_entitlements": (
        "plan_revision_id",
        "capability_key",
        "value_kind",
        "enabled",
        "limit_value",
        "criticality",
        "created_at",
    ),
    "platform.saas_plan_revisions": (
        "plan_revision_id",
        "plan_id",
        "revision",
        "publication_state",
        "published_at",
        "created_at",
    ),
    "platform.saas_plans": ("plan_id", "code", "display_name", "status", "created_at"),
    "platform.telegram_connection_state": (
        "workspace_id",
        "connection_id",
        "provider",
        "bot_identity",
        "external_connection_id",
        "owner_user_id",
        "generation",
        "observation_version",
        "observed_generation",
        "observed_at",
        "observation_xid",
        "is_enabled",
        "can_reply",
        "error_code",
        "material_enabled",
    ),
    "platform.telegram_update_receipts": (
        "id",
        "bot_identity",
        "update_id",
        "fingerprint",
        "kind",
        "result_code",
        "workspace_id",
        "connection_id",
        "inbox_id",
        "received_at",
        "codec",
    ),
    "platform.turn_consumer_receipts": (
        "workspace_id",
        "job_id",
        "connection_id",
        "kind",
        "turn_id",
        "turn_revision",
        "step",
        "consumer",
        "winning_claim_token",
        "input_context_version",
        "input_control_generation",
        "snapshot_digest",
        "result",
        "accepted_at",
    ),
    "platform.user_accounts": ("id", "status", "version", "created_at"),
    "platform.workspace_billing_accounts": (
        "workspace_id",
        "billing_account_id",
        "contact_display_name",
        "version",
        "created_at",
        "updated_at",
    ),
    "platform.workspace_memberships": (
        "workspace_id",
        "user_account_id",
        "role",
        "status",
        "version",
        "created_at",
    ),
    "platform.workspace_service_modes": (
        "workspace_id",
        "service_mode_id",
        "mode",
        "reason_code",
        "effective_from",
        "effective_until",
        "version",
        "created_at",
        "updated_at",
    ),
    "platform.workspace_subscriptions": (
        "workspace_id",
        "subscription_id",
        "plan_revision_id",
        "required_publication_state",
        "status",
        "funding_mode",
        "effective_from",
        "effective_until",
        "version",
        "created_at",
        "updated_at",
    ),
    "platform.workspaces": ("id", "status", "version", "created_at"),
    "platform.conversation_control_receipts": (
        "workspace_id",
        "id",
        "operation_namespace",
        "operation",
        "idempotency_key",
        "conversation_id",
        "client_id",
        "actor_user_account_id",
        "correlation_id",
        "expected_generation",
        "expected_context_version",
        "previous_mode",
        "accepted_mode",
        "previous_generation",
        "accepted_generation",
        "context_version",
        "activation_fence_seq",
        "request_fingerprint",
        "audit_event_id",
        "audit_event_type",
        "accepted_at",
        "result",
        "guard_profile",
    ),
    "platform.turn_guard_receipts": (
        "workspace_id",
        "job_id",
        "winning_claim_token",
        "connection_id",
        "conversation_id",
        "client_id",
        "turn_id",
        "turn_revision",
        "resume_receipt_id",
        "input_control_generation",
        "activation_fence_seq",
        "input_context_version",
        "snapshot_digest",
        "consumer",
        "request_fingerprint",
        "result_text",
        "outcome",
        "accepted_at",
        "intent_context_version",
        "message_id",
        "outbox_id",
        "send_job_id",
        "namespace",
        "kind",
        "step",
        "direction",
        "content_type",
        "send_kind",
    ),
    "app.escalations": (
        "workspace_id",
        "id",
        "namespace",
        "conversation_id",
        "client_id",
        "connection_id",
        "turn_id",
        "source_job_id",
        "source_job_kind",
        "source_job_step",
        "source_claim_token",
        "turn_revision",
        "resume_receipt_id",
        "control_generation",
        "activation_fence_seq",
        "input_context_version",
        "waiting_context_version",
        "request_snapshot",
        "context_fingerprint",
        "request_fingerprint",
        "creation_result",
        "reason",
        "assignee_user_account_id",
        "question",
        "policy",
        "created_at",
        "due_at",
        "second_reminder_at",
        "expires_at",
        "first_reminded_at",
        "second_reminded_at",
        "version",
        "status",
        "closure_reason",
        "completed_at",
        "answer_text",
        "decided_by_user_account_id",
    ),
    "platform.escalation_command_receipts": (
        "workspace_id",
        "id",
        "namespace",
        "idempotency_key",
        "escalation_id",
        "conversation_id",
        "client_id",
        "actor_user_account_id",
        "correlation_id",
        "operation",
        "expected_version",
        "expected_control_generation",
        "expected_context_version",
        "accepted_version",
        "accepted_status",
        "accepted_context_version",
        "request_fingerprint",
        "audit_event_id",
        "audit_event_type",
        "accepted_at",
        "result",
    ),
    "platform.telegram_provenance": (
        "receipt_id",
        "codec",
        "bot_identity",
        "update_id",
        "workspace_id",
        "connection_id",
        "inbox_id",
        "projection",
        "material_enabled",
    ),
    "platform.message_material_targets": (
        "workspace_id",
        "id",
        "connection_id",
        "provider_chat_id",
        "provider_message_id",
        "message_id",
        "conversation_id",
        "client_id",
        "direction",
        "outbox_id",
        "inbound_provider_id",
        "required_sent",
        "quarantined",
        "original_grouping_closed",
        "origin_identity",
        "deleted",
        "undated_seen",
        "max_edit_at",
        "candidate",
        "dated_conflict",
        "delete_receipt",
        "undated_receipt",
        "candidate_receipt",
        "conflict_receipt",
        "current_material",
    ),
    "platform.message_material_effects": (
        "workspace_id",
        "id",
        "target_id",
        "message_id",
        "source_receipt_id",
        "audit_event_id",
        "event_type",
        "previous_version",
        "accepted_version",
        "reason",
        "accepted_at",
    ),
    "platform.message_initial_suppressions": (
        "workspace_id",
        "id",
        "message_id",
        "target_id",
        "origin_inbox_id",
        "effect_id",
        "source_receipt_id",
        "previous_version",
        "accepted_version",
        "initial_material",
        "fold_witnesses",
        "membership_disposition",
    ),
}

COLUMN_DELTA = {
    "app.channel_connections": ("human_context_policy", "human_context_policy_epoch"),
    "app.conversations": ("human_observation_epoch", "human_context_revision_id"),
    "platform.telegram_provenance": ("human_context_observation_id",),
    "platform.inbox_events": ("human_context_source_receipt_id", "human_context_observation_id"),
    "platform.conversation_control_receipts": (
        "human_context_revision_id",
        "human_context_policy_epoch",
        "human_observation_epoch",
    ),
    "platform.messaging_jobs": (
        "context_block_reason",
        "context_wait_claim_token",
        "context_wait_result",
    ),
    "app.audit_events": (
        "native_revision_id",
        "native_policy_receipt_id",
        "native_connection_id",
        "native_conversation_id",
    ),
    "platform.human_context_observations": tuple(
        "workspace_id id conversation_id client_id connection_id provider_chat_id epoch policy_epoch control_generation first_source_receipt_id classification semantic_digest accepted_at".split()
    ),
    "platform.human_context_reconciliations": tuple(
        "workspace_id id conversation_id client_id connection_id provider_chat_id actor_user_account_id namespace idempotency_key request_fingerprint correlation_id previous_revision_id revision_no expected_generation expected_context_version accepted_context_version policy_epoch observation_epoch reviewed_ingress_seq reviewed_input_state_hash reviewed_gap_digest reviewed_gap_overflow disposition context_text source_media attestation audit_event_id event_type accepted_at result".split()
    ),
    "platform.human_context_policy_receipts": tuple(
        "workspace_id id connection_id business_id provider bot_identity external_connection_id owner_user_id actor_db_role namespace idempotency_key request_fingerprint operation expected_policy expected_policy_epoch accepted_policy accepted_policy_epoch change source_profile audit_event_id event_type accepted_at result".split()
    ),
}
NATIVE_COLUMNS = {**BASELINE_COLUMNS}
for _table, _columns in COLUMN_DELTA.items():
    NATIVE_COLUMNS[_table] = NATIVE_COLUMNS.get(_table, ()) + _columns
assert len(NATIVE_COLUMNS) == 45


# Ordered, data-independent DDL catalog of the owned fresh 0013 PG18 lane.
# Function bodies have their separate source manifest below. Excluding that
# array avoids a self-hash cycle in this profile capability's own definition.
NATIVE_CATALOG_SHA256 = "57e03fe369be4bd03116ce380e37a9b447a2bc1a72e3bbf2a70c7ac08d69e370"


def _schema_profile() -> None:
    # This is a DB-only schema fingerprint. The trusted host must additionally
    # verify its clean C0-approved source tree and all paired process profiles.
    # A synthetic test supplies its actual Git identity, never an application
    # readiness attestation. No runtime grants or foundation gate are widened.
    expected = {**BASELINE_FUNCTION_PROFILES}
    for signature, sql in FUNCTIONS.items():
        body = re.search(r"AS \$\$(.*)\$\$", sql, re.S)[1]
        prefix = sql[: sql.index("AS $$")]
        expected[signature] = (
            hashlib.sha256(body.encode()).hexdigest(),
            re.search(r"LANGUAGE (\w+)", prefix, re.I)[1].lower(),
            bool(re.search(r"SECURITY DEFINER", prefix, re.I)),
            "s"
            if re.search(r"\bSTABLE\b", prefix)
            else "i"
            if re.search(r"\bIMMUTABLE\b", prefix)
            else "v",
        )
    rows = ",".join(
        "('"
        + signature
        + "','"
        + v[0]
        + "','"
        + v[1]
        + "',"
        + str(v[2]).lower()
        + ",'"
        + v[3]
        + "',"
        + str(
            signature in BASELINE_RUNTIME_FUNCTIONS
            if signature in BASELINE_FUNCTION_PROFILES
            else signature in PUBLIC_FUNCTIONS
        ).lower()
        + ")"
        for signature, v in sorted(expected.items())
    )
    columns = ",".join(
        "('" + table + "',ARRAY[" + ",".join("'" + col + "'" for col in cols) + "]::text[])"
        for table, cols in sorted(NATIVE_COLUMNS.items())
    )
    count = len(expected) + 1
    _define(f"""CREATE FUNCTION platform.human_context_schema_profile() RETURNS jsonb
      LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      WITH expected(signature,body_hash,language,security_definer,volatility,runtime_execute) AS (VALUES {rows}),
      columns_expected(table_name,column_names) AS (VALUES {columns}),
      functions AS MATERIALIZED (SELECT p.*,n.nspname||'.'||p.proname AS name,l.lanname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        JOIN pg_language l ON l.oid=p.prolang WHERE n.nspname IN ('app','platform') AND p.prokind='f'),
      tables AS MATERIALIZED (SELECT r.oid,n.nspname||'.'||r.relname AS name,r.relowner,r.relrowsecurity,r.relforcerowsecurity,r.relacl,
        array_agg(a.attname::text ORDER BY a.attnum) AS columns FROM pg_class r JOIN pg_namespace n ON n.oid=r.relnamespace
        JOIN pg_attribute a ON a.attrelid=r.oid AND a.attnum>0 AND NOT a.attisdropped WHERE n.nspname IN ('app','platform') AND r.relkind='r'
        GROUP BY r.oid,n.nspname,r.relname,r.relowner,r.relrowsecurity,r.relforcerowsecurity,r.relacl),
      validity AS MATERIALIZED (SELECT
        (SELECT count(*) FROM functions)={count} AND (SELECT count(DISTINCT to_regprocedure(signature)) FROM expected)={len(expected)}
        AND NOT EXISTS(SELECT 1 FROM expected e LEFT JOIN functions f ON f.oid=to_regprocedure(e.signature)
          WHERE f.oid IS NULL OR encode(sha256(convert_to(f.prosrc,'UTF8')),'hex')<>e.body_hash OR f.lanname<>e.language
            OR f.prosecdef<>e.security_definer OR f.provolatile::text<>e.volatility OR f.proowner<>'asm_migrator'::regrole
            OR has_function_privilege('asm_runtime',f.oid,'EXECUTE')<>e.runtime_execute
            OR f.proconfig IS DISTINCT FROM ARRAY['search_path=pg_catalog, pg_temp']
            OR EXISTS(SELECT 1 FROM aclexplode(f.proacl) a WHERE a.grantee=0 AND a.privilege_type='EXECUTE'))
        AND EXISTS(SELECT 1 FROM functions f WHERE f.oid='platform.human_context_schema_profile()'::regprocedure
          AND f.proowner='asm_migrator'::regrole AND f.lanname='sql' AND f.prosecdef AND f.provolatile='s'
          AND f.proconfig=ARRAY['search_path=pg_catalog, pg_temp'] AND NOT has_function_privilege('asm_runtime',f.oid,'EXECUTE')
          AND NOT EXISTS(SELECT 1 FROM aclexplode(f.proacl) a WHERE a.grantee=0 AND a.privilege_type='EXECUTE'))
        AND EXISTS(SELECT 1 FROM pg_roles WHERE rolname='asm_runtime' AND rolcanlogin AND NOT rolsuper AND NOT rolbypassrls
          AND NOT rolinherit AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolreplication)
        AND NOT EXISTS(SELECT 1 FROM pg_auth_members WHERE member='asm_runtime'::regrole)
        AND (SELECT count(*) FROM tables)=45 AND NOT EXISTS(SELECT 1 FROM columns_expected e LEFT JOIN tables t ON t.name=e.table_name
          WHERE t.oid IS NULL OR t.columns IS DISTINCT FROM e.column_names)
        AND NOT EXISTS(SELECT 1 FROM tables WHERE name IN ('platform.human_context_observations','platform.human_context_reconciliations','platform.human_context_policy_receipts')
          AND (relowner<>'asm_migrator'::regrole OR NOT relrowsecurity OR NOT relforcerowsecurity OR has_table_privilege('asm_runtime',oid,'SELECT,INSERT,UPDATE,DELETE')))
        AND (SELECT version_num FROM platform.alembic_version)='0013' AS valid),
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
      SELECT jsonb_build_object('schema_revision','0013','valid',coalesce(v.valid,false)
        AND encode(sha256(convert_to((c.value-'functions')::text,'UTF8')),'hex')='{NATIVE_CATALOG_SHA256}',
        'profile_sha256',encode(sha256(convert_to(E'asm:m3:native_schema:v1\\n'||c.value::text,'UTF8')),'hex')) FROM validity v CROSS JOIN catalog c $$""")


def upgrade() -> None:
    FUNCTIONS.clear()
    # Scalar primitives do not reference successor composite types.
    _primitives()
    _schema()
    _projection()
    _observation()
    _owner_commands()
    _snapshot_validation()
    _work()
    _control()
    _admissions()
    _escalations_and_reads()
    _policy()
    _integrity()
    _work_replays()
    _schema_profile()
    for signature in FUNCTIONS:
        op.execute(f"ALTER FUNCTION {signature} OWNER TO asm_migrator")
        # Replacement capabilities retain exact predecessor grants below.
        if (
            signature.split("(")[0].split(".")[1]
            + "("
            + str(
                len(signature.split("(", 1)[1][:-1].split(","))
                if signature.split("(", 1)[1][:-1]
                else 0
            )
            + ")"
            not in ORIGINAL
        ):
            op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC,asm_runtime")
    for signature in PUBLIC_FUNCTIONS:
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO asm_runtime")


def downgrade() -> None:
    op.execute("""LOCK TABLE app.channel_connections,app.conversations,app.audit_events,platform.telegram_provenance,
      platform.conversation_control_receipts,platform.inbox_events,platform.messaging_jobs,app.escalations,
      platform.human_context_observations,platform.human_context_reconciliations,platform.human_context_policy_receipts IN ACCESS EXCLUSIVE MODE""")
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM app.channel_connections WHERE human_context_policy_epoch>0 OR human_context_policy<>'OFF_UNUSED')
        OR EXISTS(SELECT 1 FROM app.conversations WHERE human_observation_epoch IS NOT NULL OR human_context_revision_id IS NOT NULL)
        OR EXISTS(SELECT 1 FROM platform.human_context_observations) OR EXISTS(SELECT 1 FROM platform.human_context_reconciliations)
        OR EXISTS(SELECT 1 FROM platform.human_context_policy_receipts)
        OR EXISTS(SELECT 1 FROM platform.telegram_provenance WHERE human_context_observation_id IS NOT NULL)
        OR EXISTS(SELECT 1 FROM platform.inbox_events WHERE human_context_source_receipt_id IS NOT NULL OR human_context_observation_id IS NOT NULL)
        OR EXISTS(SELECT 1 FROM platform.conversation_control_receipts WHERE human_context_revision_id IS NOT NULL OR human_context_policy_epoch IS NOT NULL OR human_observation_epoch IS NOT NULL)
        OR EXISTS(SELECT 1 FROM platform.messaging_jobs WHERE context_block_reason IS NOT NULL OR context_wait_claim_token IS NOT NULL OR context_wait_result IS NOT NULL OR turn_input->>'schema_version'='3')
        OR EXISTS(SELECT 1 FROM app.escalations WHERE request_snapshot->>'schema_version'='3')
        OR EXISTS(SELECT 1 FROM app.audit_events WHERE event_type IN ('HUMAN_CONTEXT_RECONCILED','HUMAN_CONTEXT_POLICY_COMMANDED')) THEN
        RAISE EXCEPTION 'Native context usage prevents downgrade' USING ERRCODE='55000'; END IF;
      END $$""")
    # No DDL, profile changes or history removal occurs before the used check.
    for sql in ORIGINAL.values():
        op.execute(sql)
    for table in (
        "app.conversations",
        "platform.human_context_observations",
        "platform.human_context_reconciliations",
        "platform.conversation_control_receipts",
        "platform.messaging_jobs",
        "platform.inbox_events",
    ):
        op.execute(f"DROP TRIGGER native_integrity ON {table}")
    for table in ("app.channel_connections", "platform.telegram_connection_state"):
        op.execute(f"DROP TRIGGER native_policy_guard ON {table}")
    for table in (
        *TABLES,
        "platform.telegram_provenance",
        "platform.inbox_events",
        "app.audit_events",
    ):
        op.execute(f"DROP TRIGGER native_consistent ON {table}")
    op.execute("""ALTER TABLE platform.messaging_jobs DROP CONSTRAINT native_context_work_check,
      DROP CONSTRAINT messaging_jobs_error_code_check,ADD CONSTRAINT messaging_jobs_error_code_check CHECK(error_code IS NULL OR error_code IN
        ('NOT_ALLOWED','RETRY_EXHAUSTED','DEPENDENCY_TIMEOUT','DEPENDENCY_UNAVAILABLE','UNKNOWN_EXTERNAL_RESULT','INVALID_INPUT','MESSAGE_ID_CONFLICT','CONVERSATION_IDENTITY_CONFLICT'));
      ALTER TABLE app.conversations DROP CONSTRAINT native_conversation_revision_fkey;
      ALTER TABLE platform.conversation_control_receipts DROP CONSTRAINT native_control_revision_fkey;
      ALTER TABLE platform.telegram_provenance DROP CONSTRAINT native_source_observation_fkey;
      ALTER TABLE platform.inbox_events DROP CONSTRAINT native_inbox_source_fkey,DROP CONSTRAINT native_inbox_observation_fkey""")
    typed = (
        "platform.human_context_revision_json(platform.human_context_reconciliations)",
        "platform.human_context_reconcile_result(platform.human_context_reconciliations)",
        "platform.human_context_policy_result(platform.human_context_policy_receipts)",
    )
    for signature in typed:
        op.execute(f"DROP FUNCTION {signature}")
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE {table}")
    op.execute(
        "ALTER TABLE app.audit_events DROP CONSTRAINT audit_events_discriminator_payload_check"
    )
    op.execute(
        f"ALTER TABLE app.audit_events ADD CONSTRAINT audit_events_discriminator_payload_check CHECK({OLD_AUDIT_CHECK})"
    )
    op.execute("""ALTER TABLE app.audit_events DROP CONSTRAINT native_audit_revision_key,DROP CONSTRAINT native_audit_policy_key,
      DROP CONSTRAINT native_audit_conversation_fkey,DROP CONSTRAINT native_audit_connection_fkey;
      ALTER TABLE app.conversations DROP CONSTRAINT native_conversation_identity_key;
      ALTER TABLE app.channel_connections DROP CONSTRAINT native_connection_binding_key""")
    for name in (
        "native_source_observation_idx",
        "native_job_work_idx",
        "native_inbox_checkpoint_idx",
        "native_inbox_pending_idx",
        "native_inbox_failed_idx",
        "native_inbox_unsequenced_idx",
    ):
        op.execute(
            f"DROP INDEX platform.{name}"
            if name.startswith(("native_source", "native_job", "native_inbox"))
            else f"DROP INDEX app.{name}"
        )
    for table, columns in COLUMN_DELTA.items():
        if table in TABLES:
            continue
        for column in reversed(columns):
            op.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
    for signature in reversed(NEW_FUNCTIONS):
        if signature not in typed:
            op.execute(f"DROP FUNCTION {signature}")


NEW_FUNCTIONS = (
    "platform.human_context_hash(text,text[])",
    "platform.human_context_text_valid(text)",
    "platform.human_context_decimal(jsonb,boolean)",
    "platform.human_context_uuid(jsonb)",
    "platform.human_context_revision_json(platform.human_context_reconciliations)",
    "platform.human_context_effective(app.messages,jsonb,text)",
    "platform.human_context_projection(uuid,uuid,timestamptz)",
    "platform.human_context_turn_projection(uuid,uuid,timestamptz)",
    "platform.human_context_reason(jsonb,boolean)",
    "platform.human_context_observation_digest(uuid,uuid,uuid,uuid,jsonb)",
    "platform.human_context_preview(jsonb)",
    "platform.human_context_observe(platform.telegram_update_receipts,jsonb)",
    "platform.human_context_read(uuid)",
    "platform.human_context_observations(uuid,integer,jsonb)",
    "platform.human_context_reconcile_result(platform.human_context_reconciliations)",
    "platform.human_context_reconcile(uuid,text,jsonb)",
    "platform.human_context_current_valid(jsonb)",
    "platform.human_context_snapshot_valid(jsonb,text)",
    "platform.human_context_admission(uuid,uuid,jsonb)",
    "platform.human_context_work_valid(platform.messaging_jobs)",
    "platform.human_context_work_replay(uuid,uuid)",
    "platform.human_context_wait(uuid,uuid,text)",
    "platform.human_context_test_prelock(platform.messaging_jobs)",
    "platform.human_context_test_guard(platform.messaging_jobs,jsonb)",
    "platform.human_context_snapshot_check(jsonb,text)",
    "platform.human_context_basic_current(uuid,uuid,uuid,bigint)",
    "platform.human_context_escalation_hold(uuid,uuid,timestamptz)",
    "platform.human_context_policy_result(platform.human_context_policy_receipts)",
    "platform.human_context_policy_command(uuid,uuid,text,text,text,bigint,jsonb,jsonb)",
    "platform.human_context_policy_guard()",
    "platform.human_context_integrity()",
    "platform.human_context_consistent()",
    "platform.human_context_work_lookup(uuid,uuid)",
    "platform.human_context_stale()",
    "platform.human_context_schema_profile()",
)

BASELINE_RUNTIME_FUNCTIONS = (
    "app.current_messaging_owner_workspace_id()",
    "app.current_workspace_id()",
    "platform.auth_bootstrap(text,integer)",
    "platform.auth_login(text,uuid,bigint,bigint,text,integer)",
    "platform.auth_logout(text)",
    "platform.auth_memberships(text)",
    "platform.auth_password_lookup(text)",
    "platform.auth_rotate(text,text)",
    "platform.auth_session(text)",
    "platform.conversation_control_execute(uuid,uuid,text,text,bigint,bigint)",
    "platform.conversation_control_prepare(uuid,uuid,text,text,bigint,bigint)",
    "platform.conversation_control_read(uuid)",
    "platform.conversation_manual_prelock(uuid,text,text)",
    "platform.escalation_command(uuid,uuid,uuid,text,text,bigint,bigint,bigint,text)",
    "platform.escalation_list(integer,text,timestamptz,uuid)",
    "platform.escalation_read(uuid)",
    "platform.escalation_request_for_turn(uuid,uuid)",
    "platform.escalation_request_replay(uuid,uuid)",
    "platform.escalation_timer_execute(uuid,uuid)",
    "platform.files_begin_fetch(uuid,uuid)",
    "platform.files_claim_cleanup(integer)",
    "platform.files_finish_cleanup(uuid,uuid,text)",
    "platform.files_finish_fetch(uuid,uuid,uuid)",
    "platform.files_prepare_upload(uuid,uuid,jsonb)",
    "platform.files_read_manifest(uuid,uuid,uuid)",
    "platform.guard_send_begin(uuid,uuid)",
    "platform.guard_turn_accept(uuid,uuid,text,text)",
    "platform.guard_turn_prepare(uuid,uuid)",
    "platform.guard_turn_replay(uuid,uuid,text,text)",
    "platform.material_processing_replay(uuid,uuid)",
    "platform.messaging_admit(uuid,uuid)",
    "platform.messaging_begin_send(uuid,uuid)",
    "platform.messaging_claim(text,timestamptz,timestamptz,uuid)",
    "platform.messaging_finish_send(uuid,uuid,uuid,text,text,text)",
    "platform.messaging_finish_send(uuid,uuid,uuid,text,text,text,integer)",
    "platform.messaging_ingest(text,text,jsonb,uuid)",
    "platform.messaging_lock_billing()",
    "platform.messaging_prepare_text(uuid,text,text)",
    "platform.messaging_process_inbox(uuid,uuid)",
    "platform.messaging_read_connections(integer,timestamptz,uuid)",
    "platform.messaging_read_conversations(integer)",
    "platform.messaging_read_conversations(integer,timestamptz,uuid)",
    "platform.messaging_read_delivery(uuid)",
    "platform.messaging_read_inbox(uuid)",
    "platform.messaging_read_messages(uuid,integer)",
    "platform.messaging_read_messages(uuid,integer,timestamptz,uuid)",
    "platform.messaging_recover_expired(timestamptz,timestamptz,uuid)",
    "platform.messaging_request_text(uuid,text,text)",
    "platform.messaging_retry(uuid,uuid,text,boolean)",
    "platform.resolve_workspace_membership(uuid,uuid)",
    "platform.telegram_begin_send(uuid,uuid,bigint,bigint,jsonb)",
    "platform.telegram_ingest(text,jsonb,uuid)",
    "platform.telegram_owner_observe(uuid,bigint,bigint,jsonb)",
    "platform.telegram_replay_v1(text,jsonb)",
    "platform.telegram_worker_probe(uuid,uuid)",
    "platform.turn_consumer_finalize(uuid,uuid,jsonb)",
    "platform.turn_consumer_replay(uuid,uuid)",
    "platform.turn_execute(uuid,uuid)",
    "platform.update_billing_contact(bigint,text,text)",
)
