"""LOCAL/TEST owner Escalations; exact unused-schema reversal to accepted 0010.

Applied migrations stay immutable. Fixed ORIGINAL definitions/checks below are
source snapshots from 0010, never captured from a mutable runtime database.
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

ORIGINAL = {
    "platform.turn_enqueue(uuid,uuid,uuid)": r"""CREATE OR REPLACE FUNCTION platform.turn_enqueue(ws uuid,p_turn uuid,corr uuid) RETURNS void
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
            VALUES(ws,t.connection_id,'PROCESS_TURN',t.id,t.revision,'GUARDED_TEXT',corr)
            ON CONFLICT(workspace_id,turn_id,turn_revision,step) DO NOTHING;
        END IF;
      END $$""",
    "platform.guard_require_current(uuid,uuid,uuid,bigint)": r"""CREATE OR REPLACE FUNCTION platform.guard_require_current(ws uuid,p_turn uuid,p_resume uuid,p_context bigint) RETURNS text
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
      END $$""",
    "platform.messaging_job_json(platform.messaging_jobs)": r"""CREATE OR REPLACE FUNCTION platform.messaging_job_json(j platform.messaging_jobs) RETURNS jsonb
      LANGUAGE sql STABLE SET search_path=pg_catalog,pg_temp AS $$ SELECT jsonb_build_object(
      'job_id',j.id,'kind',j.kind,'workspace_id',j.workspace_id,'connection_id',j.connection_id,
      'inbox_id',j.inbox_id,'outbox_id',j.outbox_id,'file_id',j.file_id,'claim_token',j.claim_token,'lease_until',j.lease_until,
      'correlation_id',j.correlation_id,'attempt_count',j.attempt_count) ||
          CASE WHEN j.kind='PROCESS_TURN' THEN jsonb_build_object('turn_id',j.turn_id,'turn_revision',j.turn_revision,'step',j.step) ELSE '{}'::jsonb END $$""",
    "platform.turn_preflight(platform.messaging_jobs,boolean,boolean)": r"""CREATE OR REPLACE FUNCTION platform.turn_preflight(j platform.messaging_jobs,p_nowait boolean,p_terminal boolean) RETURNS void
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
        ELSIF j.kind IN ('SEND_MANUAL_TEXT','SEND_GUARDED_TEXT') THEN
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
    "platform.turn_supersede(platform.messaging_jobs)": r"""CREATE OR REPLACE FUNCTION platform.turn_supersede(j platform.messaging_jobs) RETURNS boolean
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$ BEGIN
        IF j.kind='PROCESS_TURN' AND EXISTS(SELECT 1 FROM app.conversation_turns
          WHERE workspace_id=j.workspace_id AND id=j.turn_id AND revision<>j.turn_revision) THEN
          UPDATE platform.messaging_jobs SET status='SUCCEEDED',turn_outcome='SUPERSEDED',error_code=NULL,
            attempt_count=greatest(1,attempt_count),first_started_at=coalesce(first_started_at,clock_timestamp()),
            claim_token=NULL,lease_until=NULL,worker_id=NULL,completed_at=clock_timestamp(),version=version+1 WHERE id=j.id;
          RETURN true;
        END IF; RETURN false;
      END $$""",
    "platform.messaging_claim(text,timestamptz,timestamptz,uuid)": r"""CREATE OR REPLACE FUNCTION platform.messaging_claim(p_worker text,p_until timestamptz,p_at timestamptz,p_id uuid) RETURNS jsonb
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
        ELSIF j.kind IN ('SEND_MANUAL_TEXT','SEND_GUARDED_TEXT') THEN
          delivery:=CASE WHEN retry THEN 'PENDING' ELSE 'FAILED' END;
          UPDATE app.outbox_events SET status=delivery,error_code=final_error,completed_at=CASE WHEN retry THEN NULL ELSE clock_timestamp() END,version=version+1 WHERE workspace_id=j.workspace_id AND id=j.outbox_id;
        ELSIF j.kind='PROCESS_TURN' AND j.step<>'GUARDED_TEXT' AND NOT retry THEN
          UPDATE app.conversation_turns SET state='FAILED',error_code=final_error,revision=revision+1 WHERE workspace_id=j.workspace_id AND id=j.turn_id;
        END IF;
        UPDATE platform.messaging_jobs SET status=CASE WHEN retry THEN 'READY' ELSE 'DEAD' END,
          claim_token=NULL,lease_until=NULL,worker_id=NULL,error_code=final_error,available_at=due,
          turn_outcome=CASE WHEN kind='PROCESS_TURN' AND NOT retry THEN 'FAILED' END,
          completed_at=CASE WHEN retry THEN NULL ELSE clock_timestamp() END,version=version+1 WHERE id=j.id;
        RETURN jsonb_build_object('code',CASE WHEN retry THEN 'RETRY_SCHEDULED' ELSE final_error END,'status',coalesce(delivery,CASE WHEN retry THEN 'READY' ELSE 'DEAD' END),'job_id',j.id,'outbox_id',j.outbox_id);
      END $$""",
}

OLD_CHECKS = {
    "messaging_jobs_kind_check": "kind IN ('PROCESS_INBOX','SEND_MANUAL_TEXT','SEND_GUARDED_TEXT','FETCH_IMAGE','PROCESS_TURN')",
    "messaging_jobs_check": "(kind='PROCESS_INBOX' AND inbox_id IS NOT NULL AND outbox_id IS NULL AND file_id IS NULL AND turn_id IS NULL) OR\n        (kind IN ('SEND_MANUAL_TEXT','SEND_GUARDED_TEXT') AND outbox_id IS NOT NULL AND inbox_id IS NULL AND file_id IS NULL AND turn_id IS NULL) OR\n        (kind='FETCH_IMAGE' AND file_id IS NOT NULL AND inbox_id IS NULL AND outbox_id IS NULL AND turn_id IS NULL) OR\n        (kind='PROCESS_TURN' AND turn_id IS NOT NULL AND inbox_id IS NULL AND outbox_id IS NULL AND file_id IS NULL)",
    "messaging_jobs_turn_check": "(kind<>'PROCESS_TURN' AND turn_revision IS NULL AND step IS NULL AND turn_outcome IS NULL) OR\n        (kind='PROCESS_TURN' AND turn_revision IS NOT NULL AND turn_revision>0 AND step IS NOT NULL\n          AND step IN ('GROUP','MEDIA','TEST_CONSUME','GUARDED_TEXT') AND (turn_outcome IS NULL OR turn_outcome IN ('GROUPED','WAITING_MEDIA','OBSERVED','STALE','SUPERSEDED','FAILED','ACCEPTED','NOT_ALLOWED','ALREADY_ACCEPTED')))",
    "messaging_jobs_turn_input_check": "turn_input IS NULL OR (kind='PROCESS_TURN' AND step IN ('TEST_CONSUME','GUARDED_TEXT') AND jsonb_typeof(turn_input)='object')",
}

OLD_AUDIT_CHECK = r"""
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
          ELSE false END) IS TRUE)"""

OLD_JOB_IDENTITY = """CREATE TRIGGER turn_job_identity BEFORE UPDATE ON platform.messaging_jobs FOR EACH ROW
      EXECUTE FUNCTION platform.messaging_immutable('workspace_id','id','connection_id','kind','inbox_id','outbox_id','file_id','turn_id','turn_revision','step','correlation_id')"""

PUBLIC_FUNCTIONS = (
    "platform.escalation_request_for_turn(uuid,uuid)",
    "platform.escalation_request_replay(uuid,uuid)",
    "platform.escalation_timer_execute(uuid,uuid)",
    "platform.escalation_read(uuid)",
    "platform.escalation_list(integer,text,timestamptz,uuid)",
    "platform.escalation_command(uuid,uuid,uuid,text,text,bigint,bigint,bigint,text)",
)
PRIVATE_FUNCTIONS = (
    "platform.escalation_command_fingerprint(uuid,uuid,uuid,uuid,uuid,text,bigint,bigint,bigint,text)",
    "platform.escalation_now()",
    "platform.escalation_validity(uuid,uuid,timestamptz)",
    "platform.escalation_context_changed()",
    "platform.escalation_immutable()",
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
QUESTION = "CONTROLLED ESCALATION TEST: требуется решение владельца."
MARKER_SQL = """EXISTS(SELECT 1 FROM app.conversation_turn_messages tm JOIN app.messages m
          ON (m.workspace_id,m.id)=(tm.workspace_id,tm.message_id)
          WHERE tm.workspace_id=ws AND tm.turn_id=p_turn AND m.direction='INBOUND'
            AND m.content_type='TEXT' AND m.text='CONTROLLED ESCALATION TEST')"""


def _replace(signature: str, *changes: tuple[str, str]) -> None:
    body = ORIGINAL[signature]
    for before, after in changes:
        assert body.count(before) == 1, (signature, before)
        body = body.replace(before, after)
    op.execute(body)


def _schema() -> None:
    op.execute("""LOCK TABLE platform.messaging_jobs,app.conversations,app.conversation_turns,
      platform.conversation_control_receipts,platform.turn_guard_receipts,app.audit_events
      IN ACCESS EXCLUSIVE MODE""")
    op.execute("""ALTER TABLE platform.messaging_jobs
      ADD COLUMN escalation_id uuid, ADD COLUMN escalation_outcome text""")
    for name, old in OLD_CHECKS.items():
        new = old
        if name == "messaging_jobs_kind_check":
            new = old.replace("'PROCESS_TURN')", "'PROCESS_TURN','ESCALATION_TIMER')")
        elif name == "messaging_jobs_check":
            new = (
                "("
                + old
                + " OR (kind='ESCALATION_TIMER' AND escalation_id IS NOT NULL AND inbox_id IS NULL AND outbox_id IS NULL AND file_id IS NULL AND turn_id IS NULL))"
            )
        elif name == "messaging_jobs_turn_check":
            new = (
                old.replace(
                    "kind<>'PROCESS_TURN'", "kind NOT IN ('PROCESS_TURN','ESCALATION_TIMER')"
                )
                .replace("'GUARDED_TEXT')", "'GUARDED_TEXT','ESCALATE_OWNER')")
                .replace(
                    "'ALREADY_ACCEPTED')",
                    "'ALREADY_ACCEPTED','ESCALATED','ALREADY_ESCALATED','WAITING_EXISTS')",
                )
            )
            new += " OR (kind='ESCALATION_TIMER' AND turn_revision IS NULL AND turn_outcome IS NULL AND step IS NOT NULL AND step IN ('REMIND_1','REMIND_2','EXPIRE'))"
        # Escalation creation has its own immutable snapshot, not a mutable turn_input.
        op.execute(
            f"ALTER TABLE platform.messaging_jobs DROP CONSTRAINT {name}, ADD CONSTRAINT {name} CHECK({new})"
        )
    op.execute("""ALTER TABLE platform.messaging_jobs ADD CONSTRAINT messaging_jobs_escalation_check CHECK(
      (kind<>'ESCALATION_TIMER' AND escalation_id IS NULL AND escalation_outcome IS NULL) OR
      (kind='ESCALATION_TIMER' AND escalation_id IS NOT NULL AND
        ((status IN ('READY','RUNNING') AND escalation_outcome IS NULL AND
           (error_code IS NULL OR error_code IN ('DEPENDENCY_TIMEOUT','DEPENDENCY_UNAVAILABLE'))) OR
         (status='SUCCEEDED' AND escalation_outcome IS NOT NULL AND escalation_outcome IN ('REMINDED','EXPIRED','CANCELLED','NOOP_TERMINAL') AND error_code IS NULL) OR
         (status='DEAD' AND escalation_outcome IS NULL AND error_code IS NOT NULL AND error_code IN ('INVALID_INPUT','RETRY_EXHAUSTED')))))""")
    op.execute("DROP TRIGGER turn_job_identity ON platform.messaging_jobs")
    op.execute(OLD_JOB_IDENTITY.replace("'correlation_id')", "'correlation_id','escalation_id')"))
    op.execute("""CREATE FUNCTION platform.escalation_now() RETURNS timestamptz
      LANGUAGE sql VOLATILE SET search_path=pg_catalog,pg_temp AS $$ SELECT clock_timestamp() $$""")
    op.execute(r"""CREATE FUNCTION platform.escalation_command_fingerprint(
      ws uuid,actor uuid,escalation uuid,conversation uuid,client uuid,operation text,
      version bigint,generation bigint,context bigint,answer text) RETURNS bytea
      LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $$
        SELECT sha256(convert_to(E'asm:m3:escalation_decision:v1\n'||ws::text||E'\n'||actor::text||E'\n'||
          escalation::text||E'\n'||conversation::text||E'\n'||client::text||E'\n'||operation||E'\n'||
          version::text||E'\n'||generation::text||E'\n'||context::text||E'\n'||
          CASE WHEN answer IS NULL THEN '-1:' ELSE octet_length(answer)::text||':'||answer END,'UTF8'))
      $$""")
    op.execute(f"""CREATE TABLE app.escalations(
      workspace_id uuid NOT NULL, id uuid NOT NULL DEFAULT uuidv7(),
      namespace text NOT NULL DEFAULT 'ESCALATION_REQUEST_V1' CHECK(namespace='ESCALATION_REQUEST_V1'),
      conversation_id uuid NOT NULL, client_id uuid NOT NULL, connection_id uuid NOT NULL, turn_id uuid NOT NULL,
      source_job_id uuid NOT NULL, source_job_kind text NOT NULL DEFAULT 'PROCESS_TURN' CHECK(source_job_kind='PROCESS_TURN'),
      source_job_step text NOT NULL DEFAULT 'ESCALATE_OWNER' CHECK(source_job_step='ESCALATE_OWNER'),
      source_claim_token uuid NOT NULL, turn_revision bigint NOT NULL CHECK(turn_revision>0),
      resume_receipt_id uuid NOT NULL, control_generation bigint NOT NULL CHECK(control_generation>0),
      activation_fence_seq bigint NOT NULL CHECK(activation_fence_seq>0),
      input_context_version bigint NOT NULL CHECK(input_context_version BETWEEN 1 AND 9223372036854775805),
      waiting_context_version bigint NOT NULL CHECK(waiting_context_version::numeric=input_context_version::numeric+1),
      request_snapshot jsonb NOT NULL CHECK(jsonb_typeof(request_snapshot)='object'),
      context_fingerprint bytea NOT NULL CHECK(octet_length(context_fingerprint)=32),
      request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32),
      creation_result jsonb NOT NULL CHECK(jsonb_typeof(creation_result)='object'),
      reason text NOT NULL DEFAULT 'OWNER_DECISION_REQUIRED' CHECK(reason='OWNER_DECISION_REQUIRED'),
      assignee_user_account_id uuid NOT NULL,
      question text NOT NULL DEFAULT '{QUESTION}' CHECK(question='{QUESTION}'),
      policy text NOT NULL DEFAULT 'LOCAL_TEST_OWNER_WAIT_V1' CHECK(policy='LOCAL_TEST_OWNER_WAIT_V1'),
      created_at timestamptz NOT NULL CHECK(isfinite(created_at)),
      due_at timestamptz NOT NULL CHECK(isfinite(due_at)),
      second_reminder_at timestamptz NOT NULL CHECK(isfinite(second_reminder_at)),
      expires_at timestamptz NOT NULL CHECK(isfinite(expires_at)),
      first_reminded_at timestamptz CHECK(isfinite(first_reminded_at)),
      second_reminded_at timestamptz CHECK(isfinite(second_reminded_at)),
      version bigint NOT NULL DEFAULT 1, status text NOT NULL DEFAULT 'PENDING',
      closure_reason text, completed_at timestamptz CHECK(isfinite(completed_at)),
      answer_text text, decided_by_user_account_id uuid,
      PRIMARY KEY(workspace_id,id), UNIQUE(workspace_id,turn_id,namespace), UNIQUE(source_job_id),
      UNIQUE(workspace_id,id,connection_id), UNIQUE(workspace_id,id,conversation_id,client_id),
      UNIQUE(workspace_id,id,version,status,decided_by_user_account_id),
      FOREIGN KEY(workspace_id,source_job_id,connection_id,source_job_kind,turn_id,turn_revision,source_job_step)
        REFERENCES platform.messaging_jobs(workspace_id,id,connection_id,kind,turn_id,turn_revision,step) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,turn_id,connection_id,conversation_id)
        REFERENCES app.conversation_turns(workspace_id,id,connection_id,conversation_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,conversation_id,client_id) REFERENCES app.conversations(workspace_id,id,client_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,resume_receipt_id,conversation_id,client_id,control_generation)
        REFERENCES platform.conversation_control_receipts(workspace_id,id,conversation_id,client_id,accepted_generation) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,assignee_user_account_id) REFERENCES platform.workspace_memberships(workspace_id,user_account_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,decided_by_user_account_id) REFERENCES platform.workspace_memberships(workspace_id,user_account_id) ON DELETE RESTRICT,
      CONSTRAINT escalations_schedule_check CHECK(due_at=created_at+interval '2 minutes' AND second_reminder_at=created_at+interval '5 minutes' AND expires_at=created_at+interval '10 minutes'),
      CONSTRAINT escalations_reminders_check CHECK(
        (first_reminded_at IS NULL OR (first_reminded_at>=due_at AND first_reminded_at<expires_at)) AND
        (second_reminded_at IS NULL OR (second_reminded_at>=second_reminder_at AND second_reminded_at<expires_at))),
      CONSTRAINT escalations_lifecycle_check CHECK((
        (status='PENDING' AND version=1 AND closure_reason IS NULL AND completed_at IS NULL AND answer_text IS NULL AND decided_by_user_account_id IS NULL) OR
        (status='RESOLVED' AND version=2 AND closure_reason IS NULL AND completed_at IS NOT NULL AND answer_text IS NOT NULL
          AND char_length(answer_text) BETWEEN 1 AND 512 AND octet_length(answer_text)<=2048 AND btrim(answer_text,{WHITESPACE})<>''
          AND decided_by_user_account_id IS NOT NULL AND decided_by_user_account_id=assignee_user_account_id) OR
        (status='CANCELLED' AND version=2 AND answer_text IS NULL AND completed_at IS NOT NULL AND closure_reason IS NOT NULL
          AND ((closure_reason='OWNER_CANCELLED' AND decided_by_user_account_id IS NOT NULL) OR
               (closure_reason IN ('CONTROL_CHANGED','CONTEXT_CHANGED','ASSIGNEE_REVOKED') AND decided_by_user_account_id IS NULL))) OR
        (status='EXPIRED' AND version=2 AND answer_text IS NULL AND completed_at IS NOT NULL AND closure_reason IS NOT NULL
          AND closure_reason='DEADLINE_ELAPSED' AND decided_by_user_account_id IS NULL)) IS TRUE),
      CHECK(completed_at IS NULL OR completed_at>=created_at))""")
    op.execute(
        "CREATE UNIQUE INDEX escalation_one_pending ON app.escalations(workspace_id,conversation_id) WHERE status='PENDING'"
    )
    op.execute(
        "CREATE INDEX escalation_status_page ON app.escalations(workspace_id,status,created_at,id)"
    )
    op.execute("CREATE INDEX escalation_all_page ON app.escalations(workspace_id,created_at,id)")
    op.execute("""ALTER TABLE platform.messaging_jobs
      ADD CONSTRAINT messaging_escalation_fkey FOREIGN KEY(workspace_id,escalation_id,connection_id)
        REFERENCES app.escalations(workspace_id,id,connection_id) ON DELETE RESTRICT,
      ADD CONSTRAINT messaging_escalation_step_key UNIQUE(workspace_id,escalation_id,step)""")
    op.execute("""ALTER TABLE app.audit_events
      ADD COLUMN escalation_object_id uuid GENERATED ALWAYS AS (CASE WHEN object_type='ESCALATION' THEN object_id END) STORED,
      ADD COLUMN escalation_operation text GENERATED ALWAYS AS (CASE WHEN event_type='ESCALATION_DECIDED' THEN payload->>'operation' END) STORED,
      ADD CONSTRAINT audit_events_escalation_fkey FOREIGN KEY(workspace_id,escalation_object_id)
        REFERENCES app.escalations(workspace_id,id) ON DELETE RESTRICT,
      ADD CONSTRAINT audit_events_escalation_ref_key UNIQUE(workspace_id,audit_event_id,escalation_object_id,
        object_version,actor_user_account_id,escalation_operation,event_type),
      DROP CONSTRAINT audit_events_discriminator_payload_check""")
    op.execute(f"""ALTER TABLE app.audit_events ADD CONSTRAINT audit_events_discriminator_payload_check CHECK(
      {OLD_AUDIT_CHECK} OR ((event_type='ESCALATION_DECIDED' AND actor_kind='USER_ACCOUNT'
        AND actor_user_account_id IS NOT NULL AND object_type='ESCALATION' AND object_version=2
        AND escalation_object_id IS NOT NULL AND escalation_operation IS NOT NULL AND
        payload IN ('{{"operation":"RESOLVE","status":"RESOLVED"}}'::jsonb,'{{"operation":"CANCEL","status":"CANCELLED"}}'::jsonb)) IS TRUE))""")
    op.execute("""CREATE TABLE platform.escalation_command_receipts(
      workspace_id uuid NOT NULL, id uuid NOT NULL DEFAULT uuidv7(),
      namespace text NOT NULL DEFAULT 'ESCALATION_DECISION_V1' CHECK(namespace='ESCALATION_DECISION_V1'),
      idempotency_key text NOT NULL CHECK(idempotency_key ~ '^[A-Za-z0-9._:-]{1,128}$'),
      escalation_id uuid NOT NULL, conversation_id uuid NOT NULL, client_id uuid NOT NULL,
      actor_user_account_id uuid NOT NULL, correlation_id uuid NOT NULL,
      operation text NOT NULL, expected_version bigint NOT NULL CHECK(expected_version=1),
      expected_control_generation bigint NOT NULL CHECK(expected_control_generation>0),
      expected_context_version bigint NOT NULL CHECK(expected_context_version>0 AND expected_context_version<9223372036854775807),
      accepted_version bigint NOT NULL CHECK(accepted_version=2), accepted_status text NOT NULL,
      accepted_context_version bigint NOT NULL CHECK(accepted_context_version::numeric=expected_context_version::numeric+1),
      request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32),
      audit_event_id uuid NOT NULL, audit_event_type text NOT NULL DEFAULT 'ESCALATION_DECIDED' CHECK(audit_event_type='ESCALATION_DECIDED'),
      accepted_at timestamptz NOT NULL CHECK(isfinite(accepted_at)), result jsonb NOT NULL,
      PRIMARY KEY(workspace_id,id), UNIQUE(workspace_id,namespace,idempotency_key),
      UNIQUE(workspace_id,escalation_id), UNIQUE(workspace_id,audit_event_id),
      FOREIGN KEY(workspace_id,escalation_id,conversation_id,client_id) REFERENCES app.escalations(workspace_id,id,conversation_id,client_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,escalation_id,accepted_version,accepted_status,actor_user_account_id)
        REFERENCES app.escalations(workspace_id,id,version,status,decided_by_user_account_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,actor_user_account_id) REFERENCES platform.workspace_memberships(workspace_id,user_account_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,audit_event_id,escalation_id,accepted_version,actor_user_account_id,operation,audit_event_type)
        REFERENCES app.audit_events(workspace_id,audit_event_id,escalation_object_id,object_version,actor_user_account_id,escalation_operation,event_type) ON DELETE RESTRICT,
      CHECK((operation='RESOLVE' AND accepted_status='RESOLVED') OR (operation='CANCEL' AND accepted_status='CANCELLED')),
      CHECK(result=jsonb_build_object('workspace_id',workspace_id,'escalation_id',escalation_id,'conversation_id',conversation_id,'client_id',client_id,
        'receipt_id',id,'audit_event_id',audit_event_id,'operation',operation,'accepted_status',accepted_status,
        'previous_version',expected_version::text,'accepted_version',accepted_version::text,'accepted_context_version',accepted_context_version::text,
        'control_generation',expected_control_generation::text,'accepted_at',to_char(accepted_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'))))""")
    for table in ("app.escalations", "platform.escalation_command_receipts"):
        op.execute(f"ALTER TABLE {table} OWNER TO asm_migrator")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY escalation_migrator ON {table} TO asm_migrator USING(true) WITH CHECK(true)"
        )
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC,asm_runtime")
    op.execute(
        "CREATE TRIGGER escalation_receipt_immutable BEFORE UPDATE ON platform.escalation_command_receipts FOR EACH ROW EXECUTE FUNCTION platform.turn_immutable()"
    )


# Pure SQL source fragments reused by capabilities, not extra SQL functions.
CREATION_RESULT = """jsonb_build_object('code','ESCALATED','workspace_id',e.workspace_id,'source_job_id',e.source_job_id,
        'escalation_id',e.id,'conversation_id',e.conversation_id,'client_id',e.client_id,'turn_id',e.turn_id,
        'resume_receipt_id',e.resume_receipt_id,'turn_revision',e.turn_revision,'input_context_version',e.input_context_version,
        'waiting_context_version',e.waiting_context_version,'control_generation',e.control_generation,
        'context_fingerprint',encode(e.context_fingerprint,'hex'),'request_fingerprint',encode(e.request_fingerprint,'hex'),
        'initial_version',1,'initial_status','PENDING','created_at',e.created_at,'due_at',e.due_at,
        'second_reminder_at',e.second_reminder_at,'expires_at',e.expires_at)"""
SNAPSHOT = """(platform.turn_snapshot(j.workspace_id,t.id)-'snapshot_digest'-'code'-'job_id') ||
        jsonb_build_object('conversation_id',c.id,'client_id',c.client_id,'business_id',c.business_id,
          'resume_receipt_id',r.id,'activation_fence_seq',t.activation_fence_seq,
          'source_job_id',j.id,'source_job_kind',j.kind,'source_job_step',j.step,'source_claim_token',j.claim_token)"""
REQUEST_HASH = r"""sha256(convert_to(E'asm:m3:escalation_request:v1\n'||jsonb_build_object(
        'snapshot',e.request_snapshot,'reason',e.reason,'assignee_user_account_id',e.assignee_user_account_id,
        'question',e.question,'policy',e.policy)::text,'UTF8'))"""


def _triggers() -> None:
    op.execute(f"""CREATE FUNCTION platform.escalation_immutable() RETURNS trigger
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
        expected:=({SNAPSHOT}) || jsonb_build_object('context_version',e.input_context_version);
        IF (j.status,j.claim_token,t.revision,t.state,c.version,c.control_generation,c.control_mode,
              r.operation,r.actor_user_account_id,r.activation_fence_seq,r.guard_profile) IS DISTINCT FROM
             ('RUNNING'::text,e.source_claim_token,e.turn_revision,'READY'::text,e.waiting_context_version,e.control_generation,'AI'::text,
              'RESUME'::text,e.assignee_user_account_id,e.activation_fence_seq,'CONTROLLED_GUARDS_V1'::text) OR
            e.request_snapshot IS DISTINCT FROM expected OR
            e.context_fingerprint IS DISTINCT FROM sha256(convert_to(e.request_snapshot::text,'UTF8')) OR
            e.request_fingerprint IS DISTINCT FROM {REQUEST_HASH} OR
            e.creation_result IS DISTINCT FROM {CREATION_RESULT} OR
            e.status<>'PENDING' OR e.version<>1 OR e.first_reminded_at IS NOT NULL OR e.second_reminded_at IS NOT NULL THEN
          RAISE EXCEPTION 'invalid escalation origin' USING ERRCODE='23514',SCHEMA='app',TABLE='escalations',CONSTRAINT='escalations_immutable_check';
        END IF;
        RETURN NEW;
      END $$""")
    op.execute(
        "CREATE TRIGGER escalation_immutable BEFORE INSERT OR UPDATE ON app.escalations FOR EACH ROW EXECUTE FUNCTION platform.escalation_immutable()"
    )
    op.execute("""CREATE FUNCTION platform.escalation_context_changed() RETURNS trigger
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$ BEGIN
        IF (NEW.version,NEW.control_generation) IS NOT DISTINCT FROM (OLD.version,OLD.control_generation) THEN RETURN NEW; END IF;
        -- Parent Conversation is already locked. This trigger locks no Job,
        -- authority, Turn, or other parent; no extra context increment.
        PERFORM 1 FROM app.escalations WHERE workspace_id=NEW.workspace_id AND conversation_id=NEW.id AND status='PENDING' FOR NO KEY UPDATE;
        UPDATE app.escalations SET status='CANCELLED',version=2,
          closure_reason=CASE WHEN NEW.control_generation<>OLD.control_generation THEN 'CONTROL_CHANGED' ELSE 'CONTEXT_CHANGED' END,
          completed_at=platform.escalation_now()
          WHERE workspace_id=NEW.workspace_id AND conversation_id=NEW.id AND status='PENDING';
        RETURN NEW;
      END $$""")
    op.execute(
        "CREATE TRIGGER escalation_context_changed AFTER UPDATE OF version,control_generation ON app.conversations FOR EACH ROW EXECUTE FUNCTION platform.escalation_context_changed()"
    )
    op.execute("""CREATE FUNCTION platform.escalation_validity(ws uuid,p_escalation uuid,p_now timestamptz) RETURNS text
      LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
        SELECT CASE WHEN e.status<>'PENDING' THEN 'TERMINAL'
          WHEN c.control_generation<>e.control_generation OR c.control_mode<>'AI' OR c.activation_fence_seq IS DISTINCT FROM e.activation_fence_seq THEN 'CONTROL_CHANGED'
          WHEN c.version<>e.waiting_context_version OR t.revision<>e.turn_revision THEN 'CONTEXT_CHANGED'
          WHEN NOT EXISTS(SELECT 1 FROM platform.workspaces w JOIN platform.workspace_memberships m ON m.workspace_id=w.id
            JOIN platform.user_accounts u ON u.id=m.user_account_id WHERE w.id=ws AND m.user_account_id=e.assignee_user_account_id
              AND w.status='ACTIVE' AND u.status='ACTIVE' AND m.status='ACTIVE' AND m.role='OWNER') THEN 'ASSIGNEE_REVOKED'
          WHEN p_now>=e.expires_at THEN 'EXPIRED' ELSE 'CURRENT' END
        FROM app.escalations e JOIN app.conversations c ON (c.workspace_id,c.id)=(e.workspace_id,e.conversation_id)
          JOIN app.conversation_turns t ON (t.workspace_id,t.id)=(e.workspace_id,e.turn_id)
        WHERE e.workspace_id=ws AND e.id=p_escalation
      $$""")


def _producer() -> None:
    op.execute("""CREATE FUNCTION platform.escalation_request_replay(p_job uuid,p_claim uuid) RETURNS jsonb
      LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE result jsonb;
      BEGIN
        SELECT e.creation_result INTO result FROM app.escalations e JOIN platform.messaging_jobs j
          ON (j.workspace_id,j.id,j.connection_id,j.kind,j.turn_id,j.turn_revision,j.step)=
            (e.workspace_id,e.source_job_id,e.connection_id,e.source_job_kind,e.turn_id,e.turn_revision,e.source_job_step)
          WHERE j.id=p_job AND e.source_claim_token=p_claim AND j.status='SUCCEEDED' AND j.turn_outcome='ESCALATED';
        IF NOT FOUND THEN RAISE EXCEPTION 'STALE_CLAIM' USING ERRCODE='P2001'; END IF;
        RETURN result;
      END $$""")
    op.execute(f"""CREATE FUNCTION platform.escalation_request_for_turn(p_job uuid,p_claim uuid) RETURNS jsonb
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
            owner_live IS NOT TRUE OR NOT ({MARKER_SQL}) OR
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
        e.request_snapshot:={SNAPSHOT}; e.context_fingerprint:=sha256(convert_to(e.request_snapshot::text,'UTF8'));
        e.reason:='OWNER_DECISION_REQUIRED'; e.assignee_user_account_id:=r.actor_user_account_id;
        e.question:='{QUESTION}'; e.policy:='LOCAL_TEST_OWNER_WAIT_V1'; e.request_fingerprint:={REQUEST_HASH};
        e.created_at:=moment; e.due_at:=moment+interval '2 minutes'; e.second_reminder_at:=moment+interval '5 minutes'; e.expires_at:=moment+interval '10 minutes';
        e.version:=1; e.status:='PENDING'; e.creation_result:={CREATION_RESULT};
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
      END $$""")


TIMER_DECLARATIONS = """timer_e app.escalations%ROWTYPE; timer_moment timestamptz; timer_due timestamptz;
        timer_validity text; timer_outcome text; timer_error text; timer_recorded timestamptz;
        fault_schema text; fault_table text; fault_constraint text;"""
TIMER_PREFLIGHT = """ELSIF j.kind='ESCALATION_TIMER' THEN
          SELECT conversation_id,assignee_user_account_id INTO STRICT conv,timer_actor FROM app.escalations
            WHERE workspace_id=j.workspace_id AND id=j.escalation_id;
          EXECUTE 'SELECT id FROM platform.workspaces WHERE id=$1 FOR SHARE'||lock_suffix USING j.workspace_id;
          EXECUTE 'SELECT id FROM platform.user_accounts WHERE id=$1 FOR SHARE'||lock_suffix USING timer_actor;
          EXECUTE 'SELECT user_account_id FROM platform.workspace_memberships WHERE workspace_id=$1 AND user_account_id=$2 FOR SHARE'||lock_suffix USING j.workspace_id,timer_actor;
          EXECUTE 'SELECT id FROM app.conversations WHERE workspace_id=$1 AND id=$2 FOR NO KEY UPDATE'||lock_suffix USING j.workspace_id,conv;
          EXECUTE 'SELECT id FROM app.escalations WHERE workspace_id=$1 AND id=$2 FOR NO KEY UPDATE'||lock_suffix USING j.workspace_id,j.escalation_id;
          RETURN;
        ELSE
          SELECT conversation_id,id INTO STRICT conv,tid FROM app.conversation_turns"""


def _timer_work(*, execute: bool) -> str:
    """Caller holds own Job and canonical preflight locks outside inner savepoint."""
    reminder = (
        """ELSIF j.step IN ('REMIND_1','REMIND_2') THEN
            timer_outcome:='REMINDED';
            IF j.step='REMIND_1' THEN
              UPDATE app.escalations SET first_reminded_at=coalesce(first_reminded_at,timer_moment)
                WHERE workspace_id=j.workspace_id AND id=timer_e.id RETURNING first_reminded_at INTO timer_recorded;
            ELSE
              UPDATE app.escalations SET second_reminded_at=coalesce(second_reminded_at,timer_moment)
                WHERE workspace_id=j.workspace_id AND id=timer_e.id RETURNING second_reminded_at INTO timer_recorded;
            END IF;"""
        if execute
        else ""
    )
    return f"""
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
          {reminder}
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
    """


def _timers() -> None:
    op.execute(f"""CREATE FUNCTION platform.escalation_timer_execute(p_job uuid,p_claim uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE j platform.messaging_jobs%ROWTYPE; {TIMER_DECLARATIONS}
      BEGIN
        j:=platform.messaging_guard(p_job,p_claim);
        IF j.kind<>'ESCALATION_TIMER' THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        PERFORM platform.turn_preflight(j,false,false);
        PERFORM platform.messaging_guard(p_job,p_claim);
        {_timer_work(execute=True)}
        IF timer_outcome IS NULL AND timer_error IS NULL THEN RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001'; END IF;
        RETURN jsonb_build_object('job_id',j.id,'escalation_id',timer_e.id,'step',j.step,
          'status',CASE WHEN timer_error IS NULL THEN 'SUCCEEDED' ELSE 'DEAD' END,'error_code',timer_error,
          'outcome',timer_outcome,'recorded_at',timer_recorded);
      END $$""")


# Both reads use the same projection expression in one statement snapshot with
# one MATERIALIZED clock capture. No per-item capability calls or writes.
def _stamp(expr: str) -> str:
    return f"to_char({expr} AT TIME ZONE 'UTC','YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"')"


VIEW = f"""jsonb_build_object(
      'workspace_id',e.workspace_id,'escalation_id',e.id,'conversation_id',e.conversation_id,'client_id',e.client_id,
      'turn_id',e.turn_id,'assignee_user_account_id',e.assignee_user_account_id,
      'reason',e.reason,'question',e.question,'policy',e.policy,'version',e.version::text,'status',e.status,
      'bound_context',jsonb_build_object('turn_revision',e.turn_revision::text,'control_generation',e.control_generation::text,
        'context_version',e.waiting_context_version::text,'fingerprint',encode(e.context_fingerprint,'hex')),
      'current_context',jsonb_build_object('control_mode',c.control_mode,'control_generation',c.control_generation::text,'context_version',c.version::text),
      'validity',v.validity,'waiting',CASE WHEN e.status='PENDING' AND v.validity='CURRENT' THEN 'WAITING_FOR_HUMAN' END,
      'created_at',{_stamp("e.created_at")},'due_at',{_stamp("e.due_at")},'second_reminder_at',{_stamp("e.second_reminder_at")},
      'expires_at',{_stamp("e.expires_at")},'observed_at',{_stamp("clock.moment")},
      'reminders',jsonb_build_array(
        jsonb_build_object('ordinal',1,'due_at',{_stamp("e.due_at")},'recorded_at',{_stamp("e.first_reminded_at")}),
        jsonb_build_object('ordinal',2,'due_at',{_stamp("e.second_reminder_at")},'recorded_at',{_stamp("e.second_reminded_at")})),
      'maintenance',CASE WHEN EXISTS(SELECT 1 FROM platform.messaging_jobs j WHERE j.workspace_id=e.workspace_id AND j.escalation_id=e.id AND j.status='DEAD') THEN 'FAILED'
        WHEN (SELECT count(*) FROM platform.messaging_jobs j WHERE j.workspace_id=e.workspace_id AND j.escalation_id=e.id AND j.status='SUCCEEDED')=3 THEN 'COMPLETE' ELSE 'SCHEDULED' END,
      'resolution',CASE WHEN e.status='RESOLVED' THEN jsonb_build_object('answer_text',e.answer_text,'actor_user_account_id',e.decided_by_user_account_id,'completed_at',{_stamp("e.completed_at")}) END,
      'closure',CASE WHEN e.status IN ('CANCELLED','EXPIRED') THEN jsonb_build_object('reason',e.closure_reason,'actor_user_account_id',e.decided_by_user_account_id,'completed_at',{_stamp("e.completed_at")}) END,
      'can_resolve',e.status='PENDING' AND v.validity='CURRENT' AND e.assignee_user_account_id=actor,
      'can_cancel',e.status='PENDING' AND v.validity IN ('CURRENT','ASSIGNEE_REVOKED') AND clock.moment<e.expires_at)"""
VIEW_FROM = """FROM app.escalations e JOIN app.conversations c ON (c.workspace_id,c.id)=(e.workspace_id,e.conversation_id)
      CROSS JOIN clock CROSS JOIN LATERAL (SELECT platform.escalation_validity(e.workspace_id,e.id,clock.moment) AS validity) v"""
OWNER = """PERFORM platform.turn_require_isolation(); ws:=app.current_messaging_owner_workspace_id();
        actor:=nullif(current_setting('asm.actor_id',true),'')::uuid;
        IF ws IS NULL OR platform.messaging_lock_owner(ws,actor) IS NOT TRUE THEN RAISE EXCEPTION 'ACCESS_DENIED' USING ERRCODE='P2501'; END IF;"""


def _reads() -> None:
    op.execute(f"""CREATE FUNCTION platform.escalation_read(p_escalation uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE ws uuid; actor uuid; result jsonb;
      BEGIN
        {OWNER}
        WITH clock AS MATERIALIZED (SELECT platform.escalation_now() AS moment)
          SELECT {VIEW} INTO result {VIEW_FROM} WHERE e.workspace_id=ws AND e.id=p_escalation;
        IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='P2501'; END IF;
        RETURN result;
      END $$""")
    op.execute(f"""CREATE FUNCTION platform.escalation_list(p_count integer,p_status text,p_at timestamptz,p_id uuid) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE ws uuid; actor uuid; result jsonb;
      BEGIN
        {OWNER}
        IF p_count IS NULL OR p_count NOT BETWEEN 1 AND 101 OR p_status IS NULL OR p_status NOT IN ('PENDING','RESOLVED','CANCELLED','EXPIRED','ALL') OR
          ((p_at IS NULL)<>(p_id IS NULL)) OR (p_at IS NOT NULL AND (NOT isfinite(p_at) OR NOT EXISTS(
            SELECT 1 FROM app.escalations WHERE workspace_id=ws AND id=p_id AND created_at=p_at))) THEN
          RAISE EXCEPTION 'INVALID_REQUEST' USING ERRCODE='P2501'; END IF;
        WITH clock AS MATERIALIZED (SELECT platform.escalation_now() AS moment), items AS (
          SELECT {VIEW} AS value,e.created_at,e.id {VIEW_FROM}
          WHERE e.workspace_id=ws AND (p_status='ALL' OR e.status=p_status) AND (p_at IS NULL OR (e.created_at,e.id)<(p_at,p_id))
          ORDER BY e.created_at DESC,e.id DESC LIMIT p_count)
          SELECT jsonb_build_object(
            'items',(SELECT coalesce(jsonb_agg(value ORDER BY created_at DESC,id DESC),'[]'::jsonb) FROM items),
            'observed_at',{_stamp("clock.moment")}) INTO result FROM clock;
        RETURN result;
      END $$""")


def _command() -> None:
    op.execute(f"""CREATE FUNCTION platform.escalation_command(p_escalation uuid,p_conversation uuid,p_client uuid,p_operation text,p_key text,
      p_version bigint,p_generation bigint,p_context bigint,p_answer text) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      DECLARE ws uuid; actor uuid; corr uuid; c app.conversations%ROWTYPE; e app.escalations%ROWTYPE;
        saved platform.escalation_command_receipts%ROWTYPE; fingerprint bytea; result jsonb;
        validity text; moment timestamptz; receipt uuid; audit uuid; accepted text;
      BEGIN
        {OWNER}
        corr:=nullif(current_setting('asm.correlation_id',true),'')::uuid;
        IF p_escalation IS NULL OR p_conversation IS NULL OR p_client IS NULL OR p_key IS NULL OR p_key !~ '^[A-Za-z0-9._:-]{{1,128}}$' OR
          p_operation IS NULL OR p_operation NOT IN ('RESOLVE','CANCEL') OR p_version IS NULL OR p_version<=0 OR
          p_generation IS NULL OR p_generation<=0 OR p_context IS NULL OR p_context<=0 OR
          (p_operation='CANCEL' AND p_answer IS NOT NULL) OR
          (p_operation='RESOLVE' AND (p_answer IS NULL OR char_length(p_answer) NOT BETWEEN 1 AND 512 OR octet_length(p_answer)>2048 OR btrim(p_answer,{WHITESPACE})='')) THEN
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
          'accepted_version','2','accepted_context_version',(c.version+1)::text,'control_generation',c.control_generation::text,'accepted_at',{_stamp("moment")});
        INSERT INTO platform.escalation_command_receipts(workspace_id,id,idempotency_key,escalation_id,conversation_id,client_id,
          actor_user_account_id,correlation_id,operation,expected_version,expected_control_generation,expected_context_version,
          accepted_version,accepted_status,accepted_context_version,request_fingerprint,audit_event_id,accepted_at,result)
          VALUES(ws,receipt,p_key,e.id,e.conversation_id,e.client_id,actor,corr,p_operation,p_version,p_generation,p_context,
            2,accepted,c.version+1,fingerprint,audit,moment,result);
        UPDATE app.conversations SET version=version+1 WHERE workspace_id=ws AND id=c.id;
        RETURN jsonb_build_object('code','ACCEPTED','result',result,'request_fingerprint',encode(fingerprint,'hex'));
      END $$""")


def _extend() -> None:
    _replace(
        "platform.turn_enqueue(uuid,uuid,uuid)",
        (
            "VALUES(ws,t.connection_id,'PROCESS_TURN',t.id,t.revision,'GUARDED_TEXT',corr)",
            f"VALUES(ws,t.connection_id,'PROCESS_TURN',t.id,t.revision,CASE WHEN {MARKER_SQL} THEN 'ESCALATE_OWNER' ELSE 'GUARDED_TEXT' END,corr)",
        ),
    )
    _replace(
        "platform.guard_require_current(uuid,uuid,uuid,bigint)",
        (
            "        RETURN 'CURRENT';",
            f"""        IF {MARKER_SQL} OR EXISTS(SELECT 1 FROM app.escalations WHERE workspace_id=ws AND
          (turn_id=p_turn OR (conversation_id=c.id AND status='PENDING'))) THEN RETURN 'NOT_ALLOWED'; END IF;
        RETURN 'CURRENT';""",
        ),
    )
    _replace(
        "platform.messaging_job_json(platform.messaging_jobs)",
        (
            "ELSE '{}'::jsonb END $$",
            "WHEN j.kind='ESCALATION_TIMER' THEN jsonb_build_object('escalation_id',j.escalation_id,'step',j.step) ELSE '{}'::jsonb END $$",
        ),
    )
    _replace(
        "platform.turn_preflight(platform.messaging_jobs,boolean,boolean)",
        (
            "conv uuid; tid uuid; disposition text;",
            "conv uuid; tid uuid; timer_actor uuid; disposition text;",
        ),
        (
            "ELSE\n          SELECT conversation_id,id INTO STRICT conv,tid FROM app.conversation_turns",
            TIMER_PREFLIGHT,
        ),
    )
    _replace(
        "platform.turn_supersede(platform.messaging_jobs)",
        (
            "AS $$ BEGIN",
            f"AS $$ DECLARE {TIMER_DECLARATIONS} BEGIN\n        IF j.kind='ESCALATION_TIMER' THEN {_timer_work(execute=False)} RETURN timer_outcome IS NOT NULL OR timer_error IS NOT NULL; END IF;",
        ),
        (
            "IF j.kind='PROCESS_TURN' AND EXISTS",
            "IF j.kind='PROCESS_TURN' AND j.step<>'ESCALATE_OWNER' AND EXISTS",
        ),
    )
    _replace(
        "platform.messaging_claim(text,timestamptz,timestamptz,uuid)",
        (
            "IF exhausted OR j.kind='PROCESS_TURN' THEN",
            "IF exhausted OR j.kind IN ('PROCESS_TURN','ESCALATION_TIMER') THEN",
        ),
        (
            "          IF platform.turn_supersede(j) THEN",
            """          -- Re-evaluate age after preflight waits; timer due/relevance in
          -- turn_supersede precedes every attempt/first-start/exhaustion write.
          exhausted:=j.attempt_count>=5 OR (j.first_started_at IS NOT NULL AND j.first_started_at+interval '15 minutes'<=clock_timestamp());
          IF platform.turn_supersede(j) THEN""",
        ),
    )
    _replace(
        "platform.messaging_reschedule(uuid,text,boolean,integer,boolean)",
        (
            "j.step<>'GUARDED_TEXT'",
            "j.step NOT IN ('GUARDED_TEXT','ESCALATE_OWNER')",
        ),
        (
            "IF platform.turn_supersede(j) THEN RETURN jsonb_build_object('code','SUPERSEDED','status','SUCCEEDED','job_id',j.id,'outbox_id',NULL); END IF;",
            """IF platform.turn_supersede(j) THEN
          IF j.kind='ESCALATION_TIMER' THEN
            SELECT status,error_code INTO delivery,final_error FROM platform.messaging_jobs WHERE id=j.id;
            RETURN jsonb_build_object('code',coalesce(final_error,'SUPERSEDED'),'status',delivery,'job_id',j.id,'outbox_id',NULL);
          END IF;
          RETURN jsonb_build_object('code','SUPERSEDED','status','SUCCEEDED','job_id',j.id,'outbox_id',NULL);
        END IF;""",
        ),
        (
            "        final_error:=CASE WHEN p_retry AND NOT retry THEN 'RETRY_EXHAUSTED' ELSE p_error END;",
            """        IF j.kind='ESCALATION_TIMER' THEN
          retry:=p_retry AND j.attempt_count<5 AND clock_timestamp()<j.first_started_at+interval '15 minutes'
            AND (p_delay IS NULL OR due<j.first_started_at+interval '15 minutes');
        END IF;
        final_error:=CASE WHEN (p_retry AND NOT retry) OR (j.kind='ESCALATION_TIMER' AND NOT retry AND p_error<>'INVALID_INPUT') THEN 'RETRY_EXHAUSTED' ELSE p_error END;""",
        ),
    )


def upgrade() -> None:
    _schema()
    _triggers()
    _producer()
    _timers()
    _reads()
    _command()
    _extend()
    for signature in (*PUBLIC_FUNCTIONS, *PRIVATE_FUNCTIONS):
        op.execute(f"ALTER FUNCTION {signature} OWNER TO asm_migrator")
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC,asm_runtime")
    for signature in PUBLIC_FUNCTIONS:
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO asm_runtime")


def downgrade() -> None:
    # Refusal precedes all DDL. Existing GUARDS/CONTROL history is not usage of E.
    op.execute("""LOCK TABLE app.escalations,platform.escalation_command_receipts,
      platform.messaging_jobs,app.audit_events,app.conversations IN ACCESS EXCLUSIVE MODE""")
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM app.escalations) OR EXISTS(SELECT 1 FROM platform.escalation_command_receipts) OR
        EXISTS(SELECT 1 FROM platform.messaging_jobs WHERE kind='ESCALATION_TIMER' OR step='ESCALATE_OWNER' OR
          escalation_id IS NOT NULL OR escalation_outcome IS NOT NULL OR turn_outcome IN ('ESCALATED','ALREADY_ESCALATED','WAITING_EXISTS')) OR
        EXISTS(SELECT 1 FROM app.audit_events WHERE event_type='ESCALATION_DECIDED' OR object_type='ESCALATION') THEN
        RAISE EXCEPTION 'Escalation history prevents downgrade' USING ERRCODE='55000'; END IF;
      END $$""")
    op.execute("DROP TRIGGER escalation_context_changed ON app.conversations")
    op.execute("DROP TRIGGER escalation_immutable ON app.escalations")
    # PL/pgSQL bodies have no catalog dependencies on the composite variable types.
    # Drop new entrypoints before their tables/functions, without CASCADE.
    for signature in (*PUBLIC_FUNCTIONS, *PRIVATE_FUNCTIONS):
        op.execute(f"DROP FUNCTION {signature}")
    for body in ORIGINAL.values():
        op.execute(body)
    op.execute("DROP TABLE platform.escalation_command_receipts")
    op.execute(f"""ALTER TABLE app.audit_events DROP CONSTRAINT audit_events_discriminator_payload_check,
      DROP CONSTRAINT audit_events_escalation_ref_key,DROP CONSTRAINT audit_events_escalation_fkey,
      DROP COLUMN escalation_operation,DROP COLUMN escalation_object_id,
      ADD CONSTRAINT audit_events_discriminator_payload_check CHECK({OLD_AUDIT_CHECK})""")
    op.execute("""ALTER TABLE platform.messaging_jobs DROP CONSTRAINT messaging_escalation_fkey,
      DROP CONSTRAINT messaging_escalation_step_key,DROP CONSTRAINT messaging_jobs_escalation_check""")
    op.execute("DROP TRIGGER turn_job_identity ON platform.messaging_jobs")
    op.execute(OLD_JOB_IDENTITY)
    for name, old in OLD_CHECKS.items():
        op.execute(
            f"ALTER TABLE platform.messaging_jobs DROP CONSTRAINT {name}, ADD CONSTRAINT {name} CHECK({old})"
        )
    op.execute(
        "ALTER TABLE platform.messaging_jobs DROP COLUMN escalation_id,DROP COLUMN escalation_outcome"
    )
    op.execute("DROP TABLE app.escalations")
