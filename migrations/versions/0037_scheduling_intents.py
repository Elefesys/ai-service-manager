"""Commit conversational scheduling effects with the guarded reply and its option codes."""

import hashlib
import re

from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None

THIS_PROFILE = "platform.scheduling_intent_schema_profile()"
TURN_ACTIONS = "platform.scheduling_turn_actions"
CHAT_CODES = "platform.scheduling_chat_codes"
COMMAND = "platform.scheduling_intent_command(uuid,uuid,uuid,text,jsonb)"
OWNER_OFFER = "platform.scheduling_owner_offer(jsonb,text,date,text,jsonb)"
SCOPED_OFFER = "platform.scheduling_scoped_offer(uuid,jsonb,text,date,text,jsonb)"
CLIENT_COMMAND = "platform.scheduling_client_command(jsonb,uuid,uuid,text,uuid,text,boolean,jsonb)"
SCOPED_CLIENT = (
    "platform.scheduling_scoped_client(uuid,jsonb,uuid,uuid,text,uuid,text,boolean,jsonb)"
)
DELIVERY_CURRENT = (
    "platform.ai_delivery_current(platform.messaging_jobs,platform.ai_deliveries,platform.ai_runs)"
)
PIN_CHECK = "CHECK(service_request_pin IS NULL OR config->>'prompt_revision'='conversation_v8' AND service_request_pin ~ '^[0-9a-f]{64}$')"

TABLES = {
    TURN_ACTIONS: """CREATE TABLE platform.scheduling_turn_actions (
      workspace_id uuid NOT NULL,
      business_id uuid NOT NULL,
      conversation_id uuid NOT NULL,
      client_id uuid NOT NULL,
      run_id uuid NOT NULL,
      source_message_id uuid NOT NULL,
      source_version text NOT NULL CHECK(source_version ~ '^[0-9a-f]{64}$'),
      transaction_id xid8 NOT NULL,
      intent text NOT NULL CHECK(intent IN ('list_availability','select_availability')),
      phase text NOT NULL CHECK(phase IN ('OPEN','LIST_STATE','SELECT_STATE','NEEDS_ALTERNATIVES','READY','DONE')),
      selection jsonb,
      local_date date,
      timezone text,
      period text CHECK(period IN ('ANY','MORNING','AFTERNOON','EVENING')),
      option_id uuid,
      result jsonb,
      outbox_id uuid,
      PRIMARY KEY(workspace_id,run_id),
      UNIQUE (workspace_id,business_id,conversation_id,client_id,run_id),
      CHECK(outbox_id IS NULL OR phase='DONE')
    )""",
    CHAT_CODES: """CREATE TABLE platform.scheduling_chat_codes (
      workspace_id uuid NOT NULL,
      business_id uuid NOT NULL,
      conversation_id uuid NOT NULL,
      client_id uuid NOT NULL,
      code text NOT NULL CHECK(code ~ '^S-[A-Z0-9]{6}$'),
      run_id uuid NOT NULL,
      option_id uuid NOT NULL,
      PRIMARY KEY(workspace_id,business_id,conversation_id,client_id,code),
      UNIQUE(workspace_id,business_id,option_id),
      FOREIGN KEY(workspace_id,business_id,conversation_id,client_id,run_id)
        REFERENCES platform.scheduling_turn_actions(workspace_id,business_id,conversation_id,client_id,run_id)
    )""",
}

FUNCTIONS = {
    "platform.scheduling_agreed_works(platform.ai_runs)": r"""CREATE FUNCTION platform.scheduling_agreed_works(
      r platform.ai_runs
    ) RETURNS TABLE(request_id uuid, title text, service_name text, selection jsonb)
    LANGUAGE sql STABLE SET search_path=pg_catalog,pg_temp AS $$
      SELECT q.request_id,coalesce(f.idea,q.material->>'service_name'),q.material->>'service_name',
        jsonb_build_object('workspace_id',d.workspace_id,'business_id',d.business_id,
          'conversation_id',d.conversation_id,'client_id',d.client_id,'request_id',d.id,
          'quote_id',q.id,'order_id',o.id,'session_id',s.id)
      FROM app.service_requests d
      JOIN app.quote_acceptances a ON (a.workspace_id,a.request_id)=(d.workspace_id,d.id)
      JOIN app.quotes q ON (q.workspace_id,q.business_id,q.conversation_id,q.client_id,q.request_id,q.id)
        =(d.workspace_id,d.business_id,d.conversation_id,d.client_id,d.id,a.quote_id)
      JOIN app.service_orders o ON (o.workspace_id,o.request_id,o.acceptance_id)=(a.workspace_id,a.request_id,a.id)
      JOIN app.service_sessions s ON (s.workspace_id,s.order_id)=(o.workspace_id,o.id)
      CROSS JOIN LATERAL (
        SELECT max(nullif(btrim(fact->>'value'),'')) AS idea
        FROM jsonb_array_elements(d.facts) AS facts(fact) WHERE fact->>'field'='idea'
      ) f
      WHERE (d.workspace_id,d.business_id,d.conversation_id,d.client_id)
        =(r.workspace_id,r.business_id,r.conversation_id,r.client_id)
        AND s.status='PLANNED' AND s.scheduled_at IS NULL
    $$""",
    "platform.scheduling_register_chat_list(platform.scheduling_turn_actions,jsonb)": r"""CREATE FUNCTION platform.scheduling_register_chat_list(
      a platform.scheduling_turn_actions, p_offer jsonb
    ) RETURNS jsonb LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
    DECLARE slot jsonb; option_id uuid; suffix text; inserted text; salt integer; bytes bytea; byte_index integer;
      alphabet constant text:='23456789ABCDEFGHJKLMNPQRSTUVWXYZ'; items jsonb:='[]'::jsonb;
    BEGIN
      FOR slot IN SELECT value FROM jsonb_array_elements(p_offer->'options') LOOP
        option_id:=(slot->>'option_id')::uuid;
        FOR salt IN 0..31 LOOP
          bytes:=sha256(convert_to(option_id::text||':'||salt::text,'UTF8'));
          suffix:='S-';
          FOR byte_index IN 0..5 LOOP
            suffix:=suffix||substr(alphabet,1+(get_byte(bytes,byte_index)%length(alphabet)),1);
          END LOOP;
          INSERT INTO platform.scheduling_chat_codes(workspace_id,business_id,conversation_id,client_id,run_id,option_id,code)
            VALUES(a.workspace_id,a.business_id,a.conversation_id,a.client_id,a.run_id,option_id,suffix)
            ON CONFLICT(workspace_id,business_id,conversation_id,client_id,code) DO NOTHING RETURNING code INTO inserted;
          EXIT WHEN inserted IS NOT NULL;
        END LOOP;
        IF inserted IS NULL THEN RAISE EXCEPTION 'AI_INCOMPLETE' USING ERRCODE='P2001'; END IF;
        items:=items||jsonb_build_array(slot||jsonb_build_object('code',suffix));
      END LOOP;
      RETURN jsonb_set(p_offer,'{options}',items);
    END $$""",
    "platform.scheduling_intent_must_finish()": r"""CREATE FUNCTION platform.scheduling_intent_must_finish()
    RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    DECLARE saved platform.scheduling_turn_actions%ROWTYPE;
    BEGIN
      SELECT * INTO STRICT saved FROM platform.scheduling_turn_actions a
        WHERE (a.workspace_id,a.run_id)=(NEW.workspace_id,NEW.run_id);
      -- Check the reply together with the fact, after the existing selector
      -- has written its delivery. The established workflow owns those rows.
      IF saved.phase<>'DONE' OR NOT EXISTS(
        SELECT 1 FROM platform.ai_runs r
        JOIN platform.ai_deliveries d ON (d.workspace_id,d.run_id)=(r.workspace_id,r.id)
        JOIN app.messages source ON (source.workspace_id,source.conversation_id,source.connection_id)
          =(r.workspace_id,r.conversation_id,r.connection_id)
        WHERE (r.workspace_id,r.business_id,r.conversation_id,r.client_id,r.id)
          =(saved.workspace_id,saved.business_id,saved.conversation_id,saved.client_id,saved.run_id)
          AND source.id=saved.source_message_id AND source.direction='INBOUND'
          AND d.outbox_id IS NOT DISTINCT FROM saved.outbox_id
      ) OR (saved.option_id IS NOT NULL AND NOT EXISTS(
        SELECT 1 FROM app.availability_options o JOIN app.availability_offers f
          ON (f.workspace_id,f.business_id,f.id)=(o.workspace_id,o.business_id,o.offer_id)
        WHERE (o.workspace_id,o.business_id,o.id)=(saved.workspace_id,saved.business_id,saved.option_id)
          AND (f.conversation_id,f.client_id,f.session_id)=(saved.conversation_id,saved.client_id,(saved.selection->>'session_id')::uuid)
      )) OR EXISTS(
        SELECT 1 FROM platform.scheduling_chat_codes x
        LEFT JOIN app.availability_options o ON (o.workspace_id,o.business_id,o.id)=(x.workspace_id,x.business_id,x.option_id)
        LEFT JOIN app.availability_offers f ON (f.workspace_id,f.business_id,f.id)=(o.workspace_id,o.business_id,o.offer_id)
        WHERE (x.workspace_id,x.run_id)=(saved.workspace_id,saved.run_id)
          AND (saved.outbox_id IS NULL OR (f.conversation_id,f.client_id,f.session_id,f.id::text) IS DISTINCT FROM
            (saved.conversation_id,saved.client_id,(saved.selection->>'session_id')::uuid,
             saved.result->'offer'->>'offer_id'))
      ) THEN RAISE EXCEPTION 'AI_INCOMPLETE' USING ERRCODE='P2001'; END IF;
      RETURN NULL;
    END $$""",
    COMMAND: r"""CREATE FUNCTION platform.scheduling_intent_command(
      p_job uuid,p_claim uuid,p_run uuid,p_stage text,p jsonb
    ) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    DECLARE r platform.ai_runs%ROWTYPE; a platform.scheduling_turn_actions%ROWTYPE;
      m app.messages%ROWTYPE; source jsonb; effective jsonb; work record; chosen_code text;
      chosen_id uuid; origin app.availability_offers%ROWTYPE; reply jsonb; response jsonb;
      state jsonb; outcome text; key text; seen jsonb;
    BEGIN
      r:=platform.ai_reply_rights_current(p_job,p_claim,p_run);
      IF current_database()<>'asm_test' OR r.config->>'prompt_revision' IS DISTINCT FROM 'conversation_v9'
        OR r.config->>'schema_revision' IS DISTINCT FROM 'conversation_result_v5'
        OR current_setting('asm.actor_kind',true) IS DISTINCT FROM 'worker_job'
        OR current_setting('asm.workspace_id',true) IS DISTINCT FROM r.workspace_id::text
        OR current_setting('asm.context_xid',true) IS DISTINCT FROM pg_current_xact_id()::text
        OR platform.ai_knowledge_current(r) IS NOT TRUE
        OR platform.knowledge_runtime_current(r) IS NOT TRUE THEN
        RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001';
      END IF;
      PERFORM 1 FROM app.channel_connections c WHERE (c.workspace_id,c.business_id,c.id)
        =(r.workspace_id,r.business_id,r.connection_id) AND c.status='ACTIVE' AND c.provider='CONTROLLED' FOR SHARE;
      IF NOT FOUND THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;
      IF platform.messaging_manual_send_allowed(r.workspace_id) IS NOT TRUE
        THEN RAISE EXCEPTION 'NOT_ALLOWED' USING ERRCODE='P2001'; END IF;

      IF p_stage='OPEN' THEN
        source:=p->'source';
        IF NOT (CASE p->>'name'
            WHEN 'list_availability' THEN platform.material_object(p,ARRAY['name','source','period'])
              AND (p->'period'='null'::jsonb OR p->>'period' IN ('ANY','MORNING','AFTERNOON','EVENING'))
            WHEN 'select_availability' THEN platform.material_object(p,ARRAY['name','source'])
            ELSE false END)
          OR platform.material_object(source,ARRAY['message_id','source_version']) IS NOT TRUE
          OR platform.human_context_uuid(source->'message_id') IS NOT TRUE
          OR platform.intake_source_current(r.workspace_id,r.business_id,r.conversation_id,r.client_id,source) IS NOT TRUE
          OR NOT (r.snapshot->'members') @> jsonb_build_array(jsonb_build_object('message_id',source->'message_id'))
        THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
        SELECT * INTO STRICT m FROM app.messages WHERE (workspace_id,id)=(r.workspace_id,(source->>'message_id')::uuid)
          AND (conversation_id,connection_id,direction)=(r.conversation_id,r.connection_id,'INBOUND') FOR SHARE;
        effective:=platform.message_effective(r.workspace_id,m.id);
        IF effective->>'content_type' IS DISTINCT FROM 'TEXT' OR effective->>'text' IS NULL
          OR effective->>'changed' IS DISTINCT FROM 'false'
          THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
        INSERT INTO platform.scheduling_turn_actions(workspace_id,business_id,conversation_id,client_id,run_id,
          source_message_id,source_version,transaction_id,intent,phase)
        VALUES(r.workspace_id,r.business_id,r.conversation_id,r.client_id,r.id,m.id,source->>'source_version',
          pg_current_xact_id(),p->>'name','OPEN') RETURNING * INTO a;
        IF EXISTS(SELECT 1 FROM platform.scheduling_turn_actions past
          WHERE (past.workspace_id,past.business_id,past.conversation_id,past.client_id,past.source_message_id,past.source_version)
            =(a.workspace_id,a.business_id,a.conversation_id,a.client_id,a.source_message_id,a.source_version)
            AND past.phase='DONE') THEN
          UPDATE platform.scheduling_turn_actions SET phase='READY',result='{"outcome":"REPEAT"}'
            WHERE (workspace_id,run_id)=(r.workspace_id,r.id);
          RETURN '{"kind":"REPEAT"}'::jsonb;
        END IF;
        IF a.intent='list_availability' THEN
          SELECT sr.timezone INTO a.timezone FROM app.scheduling_resources sr
            WHERE (sr.workspace_id,sr.business_id)=(r.workspace_id,r.business_id);
          UPDATE platform.scheduling_turn_actions SET timezone=a.timezone
            WHERE (workspace_id,run_id)=(r.workspace_id,r.id);
          RETURN jsonb_build_object('kind','LIST','text',effective->>'text','occurred_at',m.occurred_at,
            'timezone',a.timezone,'works',(
              SELECT coalesce(jsonb_agg(to_jsonb(w)-'selection' ORDER BY w.request_id),'[]'::jsonb)
              FROM platform.scheduling_agreed_works(r) w
            ));
        END IF;
        -- Accept one unedited, unambiguous client choice. The model supplies neither
        -- the code nor an ID. A second message in this Turn may qualify the first.
        chosen_code:=upper(substring(btrim(effective->>'text') COLLATE pg_catalog.pg_c_utf8
          FROM '(?i)^выбираю[[:space:]]+(S-[0-9A-Z]{6})[.!]?$'));
        IF chosen_code IS NULL OR jsonb_array_length(r.snapshot->'members')<>1 THEN
          RETURN '{"kind":"NEEDS_CODE"}'::jsonb;
        END IF;
        SELECT x.option_id,list.period INTO chosen_id,a.period
        FROM platform.scheduling_chat_codes x
        JOIN platform.scheduling_turn_actions list ON (list.workspace_id,list.run_id)=(x.workspace_id,x.run_id)
        JOIN app.outbox_events box ON (box.workspace_id,box.id)=(list.workspace_id,list.outbox_id)
        JOIN platform.ai_runs origin_run ON (origin_run.workspace_id,origin_run.id)=(list.workspace_id,list.run_id)
        WHERE (x.workspace_id,x.business_id,x.conversation_id,x.client_id,x.code)
          =(r.workspace_id,r.business_id,r.conversation_id,r.client_id,chosen_code)
          AND list.phase='DONE' AND box.status='SENT' AND box.kind='SEND_AI_TEXT'
          AND origin_run.connection_id=r.connection_id
          AND platform.intake_source_current(list.workspace_id,list.business_id,list.conversation_id,list.client_id,
            jsonb_build_object('message_id',list.source_message_id,'source_version',list.source_version));
        IF NOT FOUND THEN RETURN '{"kind":"UNKNOWN_CODE"}'::jsonb; END IF;
        SELECT o.* INTO STRICT origin FROM app.availability_offers o
        JOIN app.availability_options opt ON (opt.workspace_id,opt.business_id,opt.offer_id)=(o.workspace_id,o.business_id,o.id)
        WHERE (opt.workspace_id,opt.business_id,opt.id)=(r.workspace_id,r.business_id,chosen_id)
          AND (o.client_id,o.conversation_id)=(r.client_id,r.conversation_id)
          AND o.replacement_appointment_id IS NULL;
        SELECT * INTO STRICT work FROM platform.scheduling_agreed_works(r) w
          WHERE (w.request_id,(w.selection->>'session_id')::uuid)=(origin.request_id,origin.session_id);
        UPDATE platform.scheduling_turn_actions SET phase='SELECT_STATE',selection=work.selection,
          local_date=origin.local_date,timezone=origin.timezone,period=a.period,option_id=chosen_id
          WHERE (workspace_id,run_id)=(r.workspace_id,r.id);
        state:=platform.scheduling_scoped_client(r.workspace_id,work.selection,r.client_id,r.conversation_id,
          'state',chosen_id,NULL,NULL,NULL);
        RETURN jsonb_build_object('kind','SELECT','work',to_jsonb(work)-'selection','state',state,'period',a.period);
      END IF;

      SELECT * INTO a FROM platform.scheduling_turn_actions
        WHERE (workspace_id,run_id)=(r.workspace_id,r.id) FOR UPDATE;
      IF a.run_id IS NULL OR a.transaction_id<>pg_current_xact_id() OR a.phase='DONE'
        THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
      key:='m7-chat:'||a.option_id::text;

      IF p_stage='LIST_STATE' AND a.phase='OPEN' AND a.intent='list_availability'
        AND platform.material_object(p,ARRAY['request_id','day','period'])
        AND p->>'period' IN ('ANY','MORNING','AFTERNOON','EVENING') THEN
        SELECT * INTO STRICT work FROM platform.scheduling_agreed_works(r) w WHERE w.request_id=(p->>'request_id')::uuid;
        state:=platform.scheduling_scoped_offer(r.workspace_id,work.selection,'state',(p->>'day')::date,NULL,NULL);
        IF state->>'timezone' IS DISTINCT FROM a.timezone THEN RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001'; END IF;
        UPDATE platform.scheduling_turn_actions SET phase='LIST_STATE',selection=work.selection,
          local_date=(p->>'day')::date,period=p->>'period' WHERE (workspace_id,run_id)=(r.workspace_id,r.id);
        RETURN jsonb_build_object('schedule',state,'terms',to_jsonb(platform.scheduling_agreement(r.workspace_id,work.selection))->'material');

      ELSIF p_stage='ISSUE' AND a.phase='LIST_STATE' AND platform.material_object(p,ARRAY['windows']) THEN
        response:=platform.scheduling_scoped_offer(r.workspace_id,a.selection,'issue',a.local_date,
          'm7-chat:'||a.source_message_id::text||':'||a.source_version,p->'windows');
        response:=platform.scheduling_register_chat_list(a,response);
        UPDATE platform.scheduling_turn_actions SET phase='READY',result=jsonb_build_object('outcome','LIST','offer',response)
          WHERE (workspace_id,run_id)=(r.workspace_id,r.id);
        RETURN response;

      ELSIF p_stage='SELECT' AND a.phase='SELECT_STATE' AND platform.material_object(p,ARRAY['eligible'])
        AND jsonb_typeof(p->'eligible')='boolean' THEN
        response:=platform.scheduling_scoped_client(r.workspace_id,a.selection,r.client_id,r.conversation_id,
          'select',a.option_id,key,(p->>'eligible')::boolean,NULL);
        outcome:=response->>'outcome';
        IF EXISTS(SELECT 1 FROM platform.scheduling_turn_actions past
          WHERE (past.workspace_id,past.business_id,past.conversation_id,past.client_id,past.option_id,past.phase)
            =(a.workspace_id,a.business_id,a.conversation_id,a.client_id,a.option_id,'DONE')
            AND (past.result->>'outcome'=outcome
              OR past.result->>'outcome' IN ('CONFIRMED','ALREADY_CONFIRMED') AND outcome IN ('CONFIRMED','ALREADY_CONFIRMED'))
        ) THEN
          UPDATE platform.scheduling_turn_actions SET phase='READY',result=jsonb_build_object('outcome','REPEAT','original',response)
            WHERE (workspace_id,run_id)=(r.workspace_id,r.id);
          RETURN '{"kind":"REPEAT"}'::jsonb;
        END IF;
        IF outcome='OPTION_UNAVAILABLE' THEN
          IF response ? 'alternatives' THEN
            -- Another path already issued the same reply. Do not assign its options new codes.
            UPDATE platform.scheduling_turn_actions SET phase='READY',result=jsonb_build_object('outcome','REPEAT','original',response)
              WHERE (workspace_id,run_id)=(r.workspace_id,r.id);
            RETURN '{"kind":"REPEAT"}'::jsonb;
          END IF;
          UPDATE platform.scheduling_turn_actions SET phase='NEEDS_ALTERNATIVES' WHERE (workspace_id,run_id)=(r.workspace_id,r.id);
          SELECT coalesce(jsonb_agg(sibling.visit_start ORDER BY sibling.visit_start),'[]'::jsonb) INTO seen
          FROM app.availability_options picked JOIN app.availability_options sibling
            ON (sibling.workspace_id,sibling.business_id,sibling.offer_id)=(picked.workspace_id,picked.business_id,picked.offer_id)
          WHERE (picked.workspace_id,picked.business_id,picked.id)=(a.workspace_id,a.business_id,a.option_id);
          state:=platform.scheduling_scoped_client(r.workspace_id,a.selection,r.client_id,r.conversation_id,
            'state',a.option_id,NULL,NULL,NULL);
          RETURN jsonb_build_object('kind','NEEDS_ALTERNATIVES','schedule',state->'schedule','seen',seen);
        END IF;
        UPDATE platform.scheduling_turn_actions SET phase='READY',result=response WHERE (workspace_id,run_id)=(r.workspace_id,r.id);
        RETURN jsonb_build_object('kind','RESULT','result',response);

      ELSIF p_stage='ALTERNATIVES' AND a.phase='NEEDS_ALTERNATIVES' AND platform.material_object(p,ARRAY['windows']) THEN
        response:=platform.scheduling_scoped_client(r.workspace_id,a.selection,r.client_id,r.conversation_id,
          'alternatives',a.option_id,key,NULL,p->'windows');
        response:=platform.scheduling_register_chat_list(a,response);
        UPDATE platform.scheduling_turn_actions SET phase='READY',
          result=jsonb_build_object('outcome','OPTION_UNAVAILABLE','offer',response)
          WHERE (workspace_id,run_id)=(r.workspace_id,r.id);
        RETURN response;

      ELSIF p_stage='FINISH' AND a.phase IN ('OPEN','LIST_STATE','SELECT_STATE','READY') AND platform.material_object(p,ARRAY['text'])
        AND (p->'text'='null'::jsonb) IS NOT DISTINCT FROM coalesce(a.result->>'outcome'='REPEAT',false) THEN
        reply:=jsonb_build_object('kind',CASE WHEN p->>'text' IS NULL THEN 'no_reply' ELSE 'reply' END,
          'text',p->'text','reason',CASE WHEN p->>'text' IS NULL THEN 'Выбор уже обработан.' END,
          'intake',jsonb_build_object('service_id',NULL,'category','FAQ_ONLY','switch_request',false,'facts','[]'::jsonb));
        response:=platform.ai_delivery_command(p_job,p_claim,'COMMIT',jsonb_build_object('run_id',r.id,'result',reply));
        UPDATE platform.scheduling_turn_actions SET phase='DONE',result=coalesce(a.result,'{"outcome":"CLARIFICATION"}'::jsonb),
          outbox_id=(SELECT d.outbox_id FROM platform.ai_deliveries d WHERE (d.workspace_id,d.run_id)=(r.workspace_id,r.id))
          WHERE (workspace_id,run_id)=(r.workspace_id,r.id);
        RETURN response;
      END IF;
      RAISE EXCEPTION 'INVALID_INPUT' USING ERRCODE='P2001';
    EXCEPTION WHEN SQLSTATE 'P3101' OR no_data_found OR invalid_text_representation THEN
      RAISE EXCEPTION 'AI_STALE' USING ERRCODE='P2001';
    END $$""",
}


def extend_prompt_versions(sql: str) -> str:
    return (
        sql.replace(",'conversation_v8')", ",'conversation_v8','conversation_v9')")
        .replace("='conversation_v8'", " IN ('conversation_v8','conversation_v9')")
        .replace(
            "IS DISTINCT FROM 'conversation_v8'", "NOT IN ('conversation_v8','conversation_v9')"
        )
    )


def conversation_functions(intents, portfolio):
    functions = {}
    for signature, original in intents.V8_FUNCTIONS.items():
        if "'conversation_v8'" not in original:
            continue
        if signature == "platform.ai_runtime_config_valid":
            original_pair = "p->>'prompt_revision'='conversation_v8' AND p->>'schema_revision'='conversation_result_v4'"
            sql = original.replace(
                original_pair,
                "("
                + original_pair
                + ") OR ("
                + original_pair.replace("v8", "v9").replace("v4", "v5")
                + ")",
            )
            assert sql != original
        else:
            sql = extend_prompt_versions(original).replace(
                "CASE WHEN r.config->>'prompt_revision' IN ('conversation_v8','conversation_v9') THEN 'conversation_result_v4'",
                "CASE WHEN r.config->>'prompt_revision'='conversation_v9' THEN 'conversation_result_v5'"
                " WHEN r.config->>'prompt_revision'='conversation_v8' THEN 'conversation_result_v4'",
            )
        functions[signature] = sql
    for name in ("service_request_agent_begin", "service_request_agent_continue"):
        signature = next(
            key for key in intents.AGENT_DOMAIN_FUNCTIONS if key.startswith(f"platform.{name}(")
        )
        functions[signature] = extend_prompt_versions(
            intents.AGENT_DOMAIN_FUNCTIONS[signature]
            .strip()
            .replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
        )
    current = portfolio.REPLACEMENTS[DELIVERY_CURRENT]
    start = current.index("        IF r.knowledge_pin IS NULL")
    stop = current.index("        PERFORM 1 FROM app.channel_connections", start)
    # Closing the last channel can make the publication lookup raise AI_STALE.
    # An admitted v9 Outbox must become terminal through the standard send path.
    functions[DELIVERY_CURRENT] = (
        current[:start]
        + "        BEGIN\n"
        + "  "
        + current[start:stop]
        + """        EXCEPTION WHEN SQLSTATE 'P2001' THEN
          IF r.config->>'prompt_revision'='conversation_v9' AND SQLERRM='AI_STALE' THEN RETURN false; END IF;
          RAISE;
        END;
"""
        + current[stop:]
    )
    return functions


def scoped_functions(reschedule, appointments, holds, availability):
    before = reschedule.prior_definitions(appointments, holds, availability)
    client = reschedule.replacements_sql(appointments, before)[CLIENT_COMMAND]
    offer = holds.FUNCTIONS[OWNER_OFFER]
    original = {
        OWNER_OFFER: offer.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1),
        CLIENT_COMMAND: client,
    }
    internal = {}
    for sql, old, new in (
        (offer, "scheduling_owner_offer", "scheduling_scoped_offer"),
        (client, "scheduling_client_command", "scheduling_scoped_client"),
    ):
        internal[new] = (
            sql.removeprefix("CREATE OR REPLACE ")
            .removeprefix("CREATE ")
            .replace(f"platform.{old}(\n", f"platform.{new}(\n      ws uuid,", 1)
            .replace(" SECURITY DEFINER ", " ", 1)
            .replace(
                "      ws uuid:=platform.scheduling_owner_scope(business,'schedule');\n", "", 1
            )
        )
        internal[new] = "CREATE " + internal[new]
    wrappers = {
        OWNER_OFFER: """CREATE OR REPLACE FUNCTION platform.scheduling_owner_offer(
      p_selection jsonb,p_action text,p_day date,p_key text,p_options jsonb
    ) RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      SELECT platform.scheduling_scoped_offer(platform.scheduling_owner_scope((p_selection->>'business_id')::uuid,'schedule'),
        p_selection,p_action,p_day,p_key,p_options)
    $$""",
        CLIENT_COMMAND: """CREATE OR REPLACE FUNCTION platform.scheduling_client_command(
      p_selection jsonb,p_client uuid,p_conversation uuid,p_action text,p_target uuid,p_key text,
      p_eligible boolean,p_options jsonb
    ) RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
      SELECT platform.scheduling_scoped_client(platform.scheduling_owner_scope((p_selection->>'business_id')::uuid,'schedule'),
        p_selection,p_client,p_conversation,p_action,p_target,p_key,p_eligible,p_options)
    $$""",
    }
    return original, wrappers | {
        SCOPED_CLIENT: internal["scheduling_scoped_client"],
        SCOPED_OFFER: internal["scheduling_scoped_offer"],
    }


def dependencies():
    scripts = op.get_context().script
    if scripts is None:
        from pathlib import Path

        from alembic.script import ScriptDirectory

        scripts = ScriptDirectory(str(Path(__file__).resolve().parents[1]))
    return tuple(
        scripts.get_revision(item).module
        for item in ("0036", "0035", "0034", "0033", "0032", "0031", "0021")
    )


def _constraints(intents, current: bool):
    definitions = intents.V8_CONSTRAINTS | {("platform.ai_runs", "ai_runs_check6"): PIN_CHECK}
    if current:
        definitions = {key: extend_prompt_versions(sql) for key, sql in definitions.items()}
    intents._set_constraints(definitions)


def profile_sql(owner_day, reschedule, holds, availability, replacements, callers):
    previous = owner_day.profile_sql(
        reschedule,
        holds,
        availability,
        holds.callers_sql(availability, owner_day.THIS_PROFILE, "'0036'"),
    )
    changes = (
        replacements
        | dict(zip(holds.PROFILE_CALLERS, callers, strict=True))
        | {owner_day.THIS_PROFILE: previous}
    )
    additions = []
    profile = previous.replace(owner_day.THIS_PROFILE, THIS_PROFILE)
    for sql in changes.values():
        header, body, _ = sql.split("$$")
        # The catalog parser supplies the signatures for functions stored by name in 0031.
        name, args = re.search(r"FUNCTION ([\w.]+)\((.*?)\)\s*RETURNS", header, re.S).groups()
        signature = (
            name
            + "("
            + ",".join(arg.strip().split()[-1] for arg in args.split(",") if arg.strip())
            + ")"
        )
        profile = re.sub(r"\('" + re.escape(signature) + r"',[^\n]+\),\n", "", profile)
        language = "plpgsql" if "LANGUAGE plpgsql" in header else "sql"
        volatility = "s" if " STABLE " in header else "i" if " IMMUTABLE " in header else "v"
        definer = str("SECURITY DEFINER" in header).lower()
        execute = str(signature in {COMMAND, OWNER_OFFER, CLIENT_COMMAND}).lower()
        if signature not in FUNCTIONS and signature not in {
            SCOPED_CLIENT,
            SCOPED_OFFER,
            owner_day.THIS_PROFILE,
        }:
            packed = re.search(r"\('" + re.escape(signature) + r"',[^\n]+\)", previous)
            if packed:
                execute = packed.group().rsplit(",", 1)[-1].rstrip(")")
        digest = hashlib.sha256(body.encode()).hexdigest()
        additions.append(
            f"('{signature}','{digest}','{language}',{definer},'{volatility}',{execute})"
        )
    columns = []
    for table, sql in TABLES.items():
        names = re.findall(r"^\s+([a-z_]+)\s+(?:uuid|text|jsonb|xid8|date)\b", sql, re.M)
        columns.append(f"('{table}',ARRAY[{','.join(repr(name) for name in names)}]::text[])")
    growth = len(FUNCTIONS) + 3
    return (
        profile.replace(" AS (VALUES ", " AS (VALUES " + ",\n".join(additions) + ",\n", 1)
        .replace(
            "columns_expected(table_name,column_names) AS (VALUES ",
            "columns_expected(table_name,column_names) AS (VALUES " + ",\n".join(columns) + ",\n",
        )
        .replace("FROM functions)=442", f"FROM functions)={442 + growth}")
        .replace("FROM expected)=441", f"FROM expected)={441 + growth}")
        .replace("FROM tables)=97", "FROM tables)=99")
        .replace("FROM columns_expected)=97", "FROM columns_expected)=99")
        .replace("'0036'", "'0037'")
        .replace(
            "fbb12c3304ea5d08d1b27b3cf5360839f040eac534ebb58cc0115d9a57521c72",
            "08cd4c23b2f4977686ce29ace57f5811d88dcbd69470243185e6e0b7d7c2b239",
        )
    )


def upgrade():
    owner_day, reschedule, appointments, holds, availability, intents, portfolio = dependencies()
    conversation = conversation_functions(intents, portfolio)
    for sql in conversation.values():
        op.execute(sql)
    _constraints(intents, True)
    for table, sql in TABLES.items():
        op.execute(sql)
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY scheduling_migrator ON {table} TO asm_migrator USING(true) WITH CHECK(true)"
        )
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC,asm_runtime")
    op.execute("""CREATE INDEX scheduling_turn_source_idx ON platform.scheduling_turn_actions
      (workspace_id,business_id,conversation_id,client_id,source_message_id,source_version) WHERE phase='DONE'""")
    op.execute("""CREATE INDEX scheduling_turn_option_idx ON platform.scheduling_turn_actions
      (workspace_id,business_id,conversation_id,client_id,option_id) WHERE phase='DONE' AND option_id IS NOT NULL""")
    _, scoped = scoped_functions(reschedule, appointments, holds, availability)
    for signature in (SCOPED_OFFER, SCOPED_CLIENT, OWNER_OFFER, CLIENT_COMMAND):
        op.execute(scoped[signature])
        if signature in {SCOPED_OFFER, SCOPED_CLIENT}:
            op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC,asm_runtime")
    for signature, sql in FUNCTIONS.items():
        op.execute(sql)
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC,asm_runtime")
    op.execute(f"GRANT EXECUTE ON FUNCTION {COMMAND} TO asm_runtime")
    op.execute("""CREATE CONSTRAINT TRIGGER scheduling_intent_must_finish
      AFTER INSERT ON platform.scheduling_turn_actions DEFERRABLE INITIALLY DEFERRED
      FOR EACH ROW EXECUTE FUNCTION platform.scheduling_intent_must_finish()""")
    callers = holds.callers_sql(availability, THIS_PROFILE, "'0037'")
    for sql in callers:
        op.execute(sql)
    op.execute(
        profile_sql(
            owner_day, reschedule, holds, availability, conversation | scoped | FUNCTIONS, callers
        )
    )
    op.execute(f"REVOKE ALL ON FUNCTION {THIS_PROFILE} FROM PUBLIC,asm_runtime")


def downgrade():
    owner_day, reschedule, appointments, holds, availability, intents, portfolio = dependencies()
    op.execute(
        "LOCK TABLE platform.ai_runs,platform.scheduling_turn_actions IN ACCESS EXCLUSIVE MODE"
    )
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM platform.ai_runs WHERE config->>'prompt_revision'='conversation_v9')
        OR EXISTS(SELECT 1 FROM platform.scheduling_turn_actions)
      THEN RAISE EXCEPTION 'SCHEDULING_INTENT_DURABLE_DATA' USING ERRCODE='55000'; END IF;
    END $$""")
    for sql in holds.callers_sql(availability, owner_day.THIS_PROFILE, "'0036'"):
        op.execute(sql)
    op.execute(f"DROP FUNCTION {THIS_PROFILE}")
    op.execute("DROP TRIGGER scheduling_intent_must_finish ON platform.scheduling_turn_actions")
    for signature in (*reversed(FUNCTIONS),):
        op.execute(f"DROP FUNCTION {signature}")
    for table in (CHAT_CODES, TURN_ACTIONS):
        op.execute(f"DROP TABLE {table}")
    originals, _ = scoped_functions(reschedule, appointments, holds, availability)
    for sql in originals.values():
        op.execute(sql)
    for signature in (SCOPED_OFFER, SCOPED_CLIENT):
        op.execute(f"DROP FUNCTION {signature}")
    for signature in conversation_functions(intents, portfolio):
        sql = (intents.V8_FUNCTIONS | intents.AGENT_DOMAIN_FUNCTIONS | portfolio.REPLACEMENTS)[
            signature
        ]
        op.execute(sql.strip().replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1))
    _constraints(intents, False)
