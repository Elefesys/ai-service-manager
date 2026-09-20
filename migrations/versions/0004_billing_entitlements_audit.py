"""M1.3 billing, entitlement catalog, tenant audit, and DB commands."""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Fail atomically before the first M1.3 object is created. Extension installation
    # is deliberately an administrator/bootstrap responsibility.
    op.execute("""
    DO $check$
    DECLARE ok boolean;
    BEGIN
      SELECT e.extversion='1.8' AND n.nspname='extensions' AND EXISTS (
        SELECT 1 FROM pg_catalog.pg_opclass oc
        JOIN pg_catalog.pg_namespace ns ON ns.oid=oc.opcnamespace
        JOIN pg_catalog.pg_am am ON am.oid=oc.opcmethod
        JOIN pg_catalog.pg_opfamily f ON f.oid=oc.opcfamily
        JOIN pg_catalog.pg_amop a ON a.amopfamily=f.oid
        JOIN pg_catalog.pg_operator o ON o.oid=a.amopopr
        WHERE ns.nspname='extensions' AND oc.opcname='gist_uuid_ops'
          AND am.amname='gist' AND a.amopstrategy=3 AND o.oprname='='
          AND o.oprleft='uuid'::pg_catalog.regtype AND o.oprright='uuid'::pg_catalog.regtype)
      INTO ok FROM pg_catalog.pg_extension e
      JOIN pg_catalog.pg_namespace n ON n.oid=e.extnamespace WHERE e.extname='btree_gist';
      IF ok IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'M1.3 requires btree_gist 1.8 in schema extensions with gist_uuid_ops equality strategy';
      END IF;
    END $check$;
    """)
    op.execute("""CREATE TABLE platform.saas_plans (
      plan_id uuid DEFAULT pg_catalog.uuidv7() CONSTRAINT saas_plans_pkey PRIMARY KEY,
      code text NOT NULL CONSTRAINT saas_plans_code_key UNIQUE,
      display_name text NOT NULL, status text NOT NULL,
      created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
      CONSTRAINT saas_plans_code_check CHECK (code ~ '^[a-z][a-z0-9_-]{0,63}$'),
      CONSTRAINT saas_plans_display_name_check CHECK (char_length(display_name) BETWEEN 1 AND 200),
      CONSTRAINT saas_plans_status_check CHECK (status IN ('ACTIVE','ARCHIVED')),
      CONSTRAINT saas_plans_created_at_finite_check CHECK (isfinite(created_at)))""")
    op.execute("""CREATE TABLE platform.saas_plan_revisions (
      plan_revision_id uuid DEFAULT pg_catalog.uuidv7() CONSTRAINT saas_plan_revisions_pkey PRIMARY KEY,
      plan_id uuid NOT NULL, revision integer NOT NULL, publication_state text NOT NULL,
      published_at timestamptz, created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
      CONSTRAINT saas_plan_revisions_plan_revision_key UNIQUE(plan_id,revision),
      CONSTRAINT saas_plan_revisions_id_state_key UNIQUE(plan_revision_id,publication_state),
      CONSTRAINT saas_plan_revisions_plan_fkey FOREIGN KEY(plan_id) REFERENCES platform.saas_plans(plan_id) ON DELETE RESTRICT,
      CONSTRAINT revision_positive_check CHECK (revision>0),
      CONSTRAINT publication_check CHECK ((publication_state='DRAFT' AND published_at IS NULL) OR (publication_state='SEALED' AND published_at IS NOT NULL AND isfinite(published_at))),
      CONSTRAINT created_at_finite_check CHECK (isfinite(created_at)))""")
    op.execute("""CREATE TABLE platform.plan_entitlements (
      plan_revision_id uuid NOT NULL, capability_key text NOT NULL, value_kind text NOT NULL,
      enabled boolean, limit_value bigint, criticality text NOT NULL,
      created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
      CONSTRAINT plan_entitlements_pkey PRIMARY KEY(plan_revision_id,capability_key),
      CONSTRAINT plan_entitlements_revision_fkey FOREIGN KEY(plan_revision_id) REFERENCES platform.saas_plan_revisions(plan_revision_id) ON DELETE RESTRICT,
      CONSTRAINT capability_key_check CHECK (capability_key ~ '^[a-z][a-z0-9_.:-]{0,127}$'),
      CONSTRAINT value_check CHECK ((value_kind='BOOLEAN' AND enabled IS NOT NULL AND limit_value IS NULL) OR (value_kind='INTEGER' AND enabled IS NULL AND limit_value IS NOT NULL AND limit_value>=0)),
      CONSTRAINT criticality_check CHECK (criticality IN ('ESSENTIAL','STANDARD','EXPENSIVE_OPTIONAL')),
      CONSTRAINT created_at_finite_check CHECK (isfinite(created_at)))""")
    op.execute("""CREATE TABLE platform.workspace_billing_accounts (
      workspace_id uuid NOT NULL CONSTRAINT workspace_billing_accounts_pkey PRIMARY KEY,
      billing_account_id uuid NOT NULL DEFAULT pg_catalog.uuidv7(), contact_display_name text NOT NULL,
      version bigint NOT NULL DEFAULT 1, created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
      CONSTRAINT workspace_billing_accounts_workspace_id_key UNIQUE(workspace_id,billing_account_id),
      CONSTRAINT workspace_billing_accounts_workspace_fkey FOREIGN KEY(workspace_id) REFERENCES platform.workspaces(id) ON DELETE RESTRICT,
      CONSTRAINT version_positive_check CHECK(version>0),
      CONSTRAINT created_at_finite_check CHECK(isfinite(created_at)), CONSTRAINT updated_at_finite_check CHECK(isfinite(updated_at)),
      CONSTRAINT timestamp_order_check CHECK(updated_at>=created_at),
      CONSTRAINT contact_check CHECK(contact_display_name=btrim(contact_display_name,' ') AND char_length(contact_display_name) BETWEEN 1 AND 200 AND octet_length(contact_display_name)<=800 AND contact_display_name !~ '[\\x00-\\x1F\\x7F]'))""")
    op.execute("""CREATE TABLE platform.workspace_subscriptions (
      workspace_id uuid NOT NULL, subscription_id uuid NOT NULL DEFAULT pg_catalog.uuidv7(),
      plan_revision_id uuid NOT NULL, required_publication_state text NOT NULL,
      status text NOT NULL, funding_mode text NOT NULL, effective_from timestamptz NOT NULL,
      effective_until timestamptz NOT NULL, version bigint NOT NULL DEFAULT 1,
      created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
      CONSTRAINT workspace_subscriptions_pkey PRIMARY KEY(workspace_id,subscription_id),
      CONSTRAINT workspace_subscriptions_workspace_fkey FOREIGN KEY(workspace_id) REFERENCES platform.workspaces(id) ON DELETE RESTRICT,
      CONSTRAINT workspace_subscriptions_revision_state_fkey FOREIGN KEY(plan_revision_id,required_publication_state) REFERENCES platform.saas_plan_revisions(plan_revision_id,publication_state) ON DELETE RESTRICT,
      CONSTRAINT required_state_check CHECK(required_publication_state='SEALED'),
      CONSTRAINT status_funding_check CHECK((status='TRIALING' AND funding_mode='TRIAL') OR (status='ACTIVE' AND funding_mode='COMPED')),
      CONSTRAINT interval_check CHECK(isfinite(effective_from) AND isfinite(effective_until) AND effective_from<effective_until),
      CONSTRAINT version_positive_check CHECK(version>0), CONSTRAINT created_at_finite_check CHECK(isfinite(created_at)),
      CONSTRAINT updated_at_finite_check CHECK(isfinite(updated_at)), CONSTRAINT timestamp_order_check CHECK(updated_at>=created_at),
      CONSTRAINT workspace_subscriptions_no_overlap_excl EXCLUDE USING gist (workspace_id WITH =, tstzrange(effective_from,effective_until,'[)') WITH &&) NOT DEFERRABLE)""")
    op.execute(
        "CREATE INDEX workspace_subscriptions_current_idx ON platform.workspace_subscriptions(workspace_id,effective_from DESC,effective_until DESC,subscription_id DESC)"
    )
    op.execute("""CREATE TABLE platform.workspace_service_modes (
      workspace_id uuid NOT NULL CONSTRAINT workspace_service_modes_pkey PRIMARY KEY,
      service_mode_id uuid NOT NULL DEFAULT pg_catalog.uuidv7(), mode text NOT NULL, reason_code text NOT NULL,
      effective_from timestamptz NOT NULL, effective_until timestamptz, version bigint NOT NULL DEFAULT 1,
      created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
      CONSTRAINT workspace_service_modes_workspace_id_key UNIQUE(workspace_id,service_mode_id),
      CONSTRAINT workspace_service_modes_workspace_fkey FOREIGN KEY(workspace_id) REFERENCES platform.workspaces(id) ON DELETE RESTRICT,
      CONSTRAINT mode_reason_check CHECK((mode,reason_code) IN (('NORMAL','PROVISIONED_LOCAL'),('GRACE','TEST_GRACE'),('LIMITED','TEST_LIMITED'),('SUSPENDED','TEST_SUSPENDED'))),
      CONSTRAINT interval_check CHECK(isfinite(effective_from) AND (effective_until IS NULL OR (isfinite(effective_until) AND effective_from<effective_until))),
      CONSTRAINT version_positive_check CHECK(version>0), CONSTRAINT created_at_finite_check CHECK(isfinite(created_at)),
      CONSTRAINT updated_at_finite_check CHECK(isfinite(updated_at)), CONSTRAINT timestamp_order_check CHECK(updated_at>=created_at))""")
    op.execute("""CREATE TABLE app.audit_events (
      workspace_id uuid NOT NULL, audit_event_id uuid NOT NULL DEFAULT pg_catalog.uuidv7(),
      occurred_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP, actor_kind text NOT NULL,
      actor_user_account_id uuid, correlation_id uuid NOT NULL, event_type text NOT NULL,
      object_type text NOT NULL, object_id uuid NOT NULL, object_version bigint NOT NULL, payload jsonb NOT NULL,
      CONSTRAINT audit_events_pkey PRIMARY KEY(workspace_id,audit_event_id),
      CONSTRAINT audit_events_workspace_fkey FOREIGN KEY(workspace_id) REFERENCES platform.workspaces(id) ON DELETE RESTRICT,
      CONSTRAINT audit_events_actor_fkey FOREIGN KEY(workspace_id,actor_user_account_id) REFERENCES platform.workspace_memberships(workspace_id,user_account_id) ON DELETE RESTRICT,
      CONSTRAINT audit_events_object_fkey FOREIGN KEY(workspace_id,object_id) REFERENCES platform.workspace_billing_accounts(workspace_id,billing_account_id) ON DELETE RESTRICT,
      CONSTRAINT audit_events_occurred_at_finite_check CHECK(isfinite(occurred_at)),
      CONSTRAINT audit_events_object_version_positive_check CHECK(object_version>0),
      CONSTRAINT audit_events_discriminator_payload_check CHECK ((event_type='WORKSPACE_BILLING_PROVISIONED' AND actor_kind='LOCAL_PROVISIONER' AND actor_user_account_id IS NULL AND object_type='WORKSPACE_BILLING_ACCOUNT' AND payload='{}'::jsonb) OR (event_type='BILLING_ACCOUNT_CONTACT_UPDATED' AND actor_kind='USER_ACCOUNT' AND actor_user_account_id IS NOT NULL AND object_type='WORKSPACE_BILLING_ACCOUNT' AND payload='{"changed_fields":["contact_display_name"]}'::jsonb)),
      CONSTRAINT audit_events_payload_size_check CHECK(octet_length(payload::text)<=4096))""")
    op.execute(
        "CREATE INDEX audit_events_page_idx ON app.audit_events(workspace_id ASC,occurred_at DESC,audit_event_id DESC)"
    )
    op.execute("""CREATE TABLE platform.billing_contact_command_receipts (
      workspace_id uuid NOT NULL, receipt_id uuid NOT NULL DEFAULT pg_catalog.uuidv7(), billing_account_id uuid NOT NULL,
      operation text NOT NULL, idempotency_key text NOT NULL, request_fingerprint bytea NOT NULL,
      expected_version bigint NOT NULL, status text NOT NULL, result_version bigint, result_outcome text,
      created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP, completed_at timestamptz,
      CONSTRAINT billing_contact_command_receipts_pkey PRIMARY KEY(workspace_id,receipt_id),
      CONSTRAINT billing_contact_command_receipts_key UNIQUE(workspace_id,operation,idempotency_key),
      CONSTRAINT billing_contact_command_receipts_workspace_fkey FOREIGN KEY(workspace_id) REFERENCES platform.workspaces(id) ON DELETE RESTRICT,
      CONSTRAINT billing_contact_command_receipts_account_fkey FOREIGN KEY(workspace_id,billing_account_id) REFERENCES platform.workspace_billing_accounts(workspace_id,billing_account_id) ON DELETE RESTRICT,
      CONSTRAINT operation_check CHECK(operation='UPDATE_BILLING_CONTACT'), CONSTRAINT key_check CHECK(idempotency_key ~ '^[A-Za-z0-9._:-]{1,128}$'),
      CONSTRAINT fingerprint_check CHECK(octet_length(request_fingerprint)=32), CONSTRAINT expected_version_positive_check CHECK(expected_version>0),
      CONSTRAINT created_at_finite_check CHECK(isfinite(created_at)),
      CONSTRAINT status_result_check CHECK((status='IN_PROGRESS' AND result_version IS NULL AND result_outcome IS NULL AND completed_at IS NULL) OR (status='SUCCEEDED' AND result_version IS NOT NULL AND result_version>0 AND result_outcome IS NOT NULL AND result_outcome IN ('UPDATED','NOOP') AND completed_at IS NOT NULL AND isfinite(completed_at))))""")
    _create_catalog_guards()
    _create_initializer()
    _create_contact_command()
    _rls_and_grants()


def _create_catalog_guards() -> None:
    op.execute("""CREATE FUNCTION platform.guard_plan_revision() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$ BEGIN
      IF TG_OP='DELETE' AND OLD.publication_state='SEALED' THEN RAISE EXCEPTION 'sealed revision is immutable' USING ERRCODE='55000'; END IF;
      IF TG_OP='UPDATE' AND (OLD.publication_state='SEALED' OR NEW.plan_revision_id<>OLD.plan_revision_id OR NEW.plan_id<>OLD.plan_id OR NEW.revision<>OLD.revision OR NEW.created_at<>OLD.created_at OR NOT (OLD.publication_state='DRAFT' AND NEW.publication_state='SEALED')) THEN RAISE EXCEPTION 'invalid revision transition' USING ERRCODE='55000'; END IF;
      RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END; END $$""")
    op.execute(
        "CREATE TRIGGER saas_plan_revisions_guard BEFORE UPDATE OR DELETE ON platform.saas_plan_revisions FOR EACH ROW EXECUTE FUNCTION platform.guard_plan_revision()"
    )
    op.execute("""CREATE FUNCTION platform.guard_entitlement() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$ DECLARE state text; BEGIN
      IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'entitlements are immutable' USING ERRCODE='55000'; END IF;
      PERFORM pg_catalog.pg_advisory_xact_lock(1295070019,1);
      SELECT publication_state INTO state FROM platform.saas_plan_revisions WHERE plan_revision_id=NEW.plan_revision_id FOR UPDATE;
      IF state IS DISTINCT FROM 'DRAFT' THEN RAISE EXCEPTION 'revision is not draft' USING ERRCODE='55000'; END IF; RETURN NEW; END $$""")
    op.execute(
        "CREATE TRIGGER plan_entitlements_guard BEFORE INSERT OR UPDATE OR DELETE ON platform.plan_entitlements FOR EACH ROW EXECUTE FUNCTION platform.guard_entitlement()"
    )


def _create_initializer() -> None:
    op.execute(r"""CREATE FUNCTION platform.initialize_local_billing(p_workspace_id uuid,p_catalog_code text,p_catalog_revision integer,p_contact_display_name text,p_subscription_status text,p_funding_mode text,p_effective_from timestamptz,p_effective_until timestamptz,p_service_mode text) RETURNS text
    LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    DECLARE p_id uuid; r_id uuid; account platform.workspace_billing_accounts%ROWTYPE; sub_count int; mode_count int; audit_count int; manifest text; result text;
    BEGIN
      PERFORM pg_catalog.pg_advisory_xact_lock(1295070019,1);
      IF p_catalog_code IS DISTINCT FROM 'test' OR p_catalog_revision IS DISTINCT FROM 1 THEN RAISE EXCEPTION 'CONFLICT_CATALOG_MISMATCH' USING ERRCODE='P1301'; END IF;
      IF p_workspace_id IS NULL THEN RAISE EXCEPTION 'CONFLICT_PARTIAL_STATE' USING ERRCODE='P1301'; END IF;
      IF p_contact_display_name IS NULL OR char_length(btrim(p_contact_display_name,' ')) NOT BETWEEN 1 AND 200 OR octet_length(btrim(p_contact_display_name,' '))>800 OR p_contact_display_name ~ '[\x00-\x1F\x7F]' OR p_subscription_status IS DISTINCT FROM 'ACTIVE' OR p_funding_mode IS DISTINCT FROM 'COMPED' OR p_service_mode IS DISTINCT FROM 'NORMAL' OR p_effective_from IS NULL OR p_effective_until IS NULL OR NOT isfinite(p_effective_from) OR NOT isfinite(p_effective_until) OR p_effective_from>=p_effective_until THEN RAISE EXCEPTION 'CONFLICT_INPUT_MISMATCH' USING ERRCODE='P1301'; END IF;
      SELECT plan_id INTO p_id FROM platform.saas_plans WHERE code='test';
      IF NOT FOUND THEN INSERT INTO platform.saas_plans(code,display_name,status) VALUES('test','M1.3 TEST plan','ACTIVE') RETURNING plan_id INTO p_id; END IF;
      SELECT plan_revision_id INTO r_id FROM platform.saas_plan_revisions WHERE plan_id=p_id AND revision=1 FOR UPDATE;
      IF NOT FOUND THEN
        INSERT INTO platform.saas_plan_revisions(plan_id,revision,publication_state) VALUES(p_id,1,'DRAFT') RETURNING plan_revision_id INTO r_id;
        INSERT INTO platform.plan_entitlements(plan_revision_id,capability_key,value_kind,enabled,limit_value,criticality) VALUES
          (r_id,'test.m1_3.essential_true','BOOLEAN',true,NULL,'ESSENTIAL'),(r_id,'test.m1_3.standard_true','BOOLEAN',true,NULL,'STANDARD'),
          (r_id,'test.m1_3.standard_false','BOOLEAN',false,NULL,'STANDARD'),(r_id,'test.m1_3.expensive_positive','INTEGER',NULL,3,'EXPENSIVE_OPTIONAL'),
          (r_id,'test.m1_3.expensive_zero','INTEGER',NULL,0,'EXPENSIVE_OPTIONAL');
        SELECT string_agg(capability_key||chr(9)||value_kind||chr(9)||CASE WHEN value_kind='BOOLEAN' THEN enabled::text ELSE limit_value::text END||chr(9)||criticality||chr(10),'' ORDER BY convert_to(capability_key,'UTF8')) INTO manifest FROM platform.plan_entitlements WHERE plan_revision_id=r_id;
        IF encode(pg_catalog.sha256(convert_to(manifest,'UTF8')),'hex')<>'2aed3e0812691c4546997692e664660c7e328783422ae824c8279bd2cef963cc' THEN RAISE EXCEPTION 'synthetic manifest mismatch'; END IF;
        UPDATE platform.saas_plan_revisions SET publication_state='SEALED',published_at=clock_timestamp() WHERE plan_revision_id=r_id;
      ELSE
        SELECT string_agg(capability_key||chr(9)||value_kind||chr(9)||CASE WHEN value_kind='BOOLEAN' THEN enabled::text ELSE limit_value::text END||chr(9)||criticality||chr(10),'' ORDER BY convert_to(capability_key,'UTF8')) INTO manifest FROM platform.plan_entitlements WHERE plan_revision_id=r_id;
        IF (SELECT publication_state FROM platform.saas_plan_revisions WHERE plan_revision_id=r_id)<>'SEALED' OR (SELECT count(*) FROM platform.plan_entitlements WHERE plan_revision_id=r_id)<>5 OR encode(pg_catalog.sha256(convert_to(manifest,'UTF8')),'hex')<>'2aed3e0812691c4546997692e664660c7e328783422ae824c8279bd2cef963cc' THEN RAISE EXCEPTION 'CONFLICT_CATALOG_MISMATCH' USING ERRCODE='P1301'; END IF;
      END IF;
      PERFORM 1 FROM platform.workspaces WHERE id=p_workspace_id FOR UPDATE; IF NOT FOUND THEN RAISE EXCEPTION 'CONFLICT_PARTIAL_STATE' USING ERRCODE='P1301'; END IF;
      SELECT * INTO account FROM platform.workspace_billing_accounts WHERE workspace_id=p_workspace_id FOR UPDATE;
      SELECT count(*) INTO sub_count FROM platform.workspace_subscriptions WHERE workspace_id=p_workspace_id;
      SELECT count(*) INTO mode_count FROM platform.workspace_service_modes WHERE workspace_id=p_workspace_id;
      SELECT count(*) INTO audit_count FROM app.audit_events WHERE workspace_id=p_workspace_id AND event_type='WORKSPACE_BILLING_PROVISIONED';
      IF account.workspace_id IS NOT NULL OR sub_count+mode_count+audit_count>0 THEN
        IF account.workspace_id IS NULL OR sub_count<>1 OR mode_count<>1 OR audit_count<>1 THEN RAISE EXCEPTION 'CONFLICT_PARTIAL_STATE' USING ERRCODE='P1301'; END IF;
        IF account.contact_display_name<>btrim(p_contact_display_name,' ') OR account.version<>1 OR NOT EXISTS(SELECT 1 FROM platform.workspace_subscriptions s WHERE s.workspace_id=p_workspace_id AND s.plan_revision_id=r_id AND s.status=p_subscription_status AND s.funding_mode=p_funding_mode AND s.effective_from=p_effective_from AND s.effective_until=p_effective_until AND s.version=1) OR NOT EXISTS(SELECT 1 FROM platform.workspace_service_modes m WHERE m.workspace_id=p_workspace_id AND m.mode=p_service_mode AND m.reason_code='PROVISIONED_LOCAL' AND m.effective_from=p_effective_from AND m.effective_until=p_effective_until AND m.version=1) THEN RAISE EXCEPTION 'CONFLICT_STATE_DRIFT' USING ERRCODE='P1301'; END IF;
        IF NOT EXISTS(SELECT 1 FROM app.audit_events e WHERE e.workspace_id=p_workspace_id AND e.event_type='WORKSPACE_BILLING_PROVISIONED' AND e.object_id=account.billing_account_id AND e.object_version=1) THEN RAISE EXCEPTION 'CONFLICT_STATE_DRIFT' USING ERRCODE='P1301'; END IF;
        RETURN 'NOOP';
      END IF;
      INSERT INTO platform.workspace_billing_accounts(workspace_id,contact_display_name) VALUES(p_workspace_id,btrim(p_contact_display_name,' ')) RETURNING * INTO account;
      INSERT INTO platform.workspace_subscriptions(workspace_id,plan_revision_id,required_publication_state,status,funding_mode,effective_from,effective_until) VALUES(p_workspace_id,r_id,'SEALED',p_subscription_status,p_funding_mode,p_effective_from,p_effective_until);
      INSERT INTO platform.workspace_service_modes(workspace_id,mode,reason_code,effective_from,effective_until) VALUES(p_workspace_id,p_service_mode,'PROVISIONED_LOCAL',p_effective_from,p_effective_until);
      INSERT INTO app.audit_events(workspace_id,actor_kind,correlation_id,event_type,object_type,object_id,object_version,payload) VALUES(p_workspace_id,'LOCAL_PROVISIONER',pg_catalog.uuidv7(),'WORKSPACE_BILLING_PROVISIONED','WORKSPACE_BILLING_ACCOUNT',account.billing_account_id,account.version,'{}');
      RETURN 'INITIALIZED';
    EXCEPTION WHEN SQLSTATE 'P1301' THEN
      -- This exception block rolls back any catalog writes before returning a
      -- bounded conflict. Other SQL errors (including Audit failure) propagate.
      GET STACKED DIAGNOSTICS result = MESSAGE_TEXT;
      IF result NOT IN ('CONFLICT_PARTIAL_STATE','CONFLICT_INPUT_MISMATCH','CONFLICT_CATALOG_MISMATCH','CONFLICT_STATE_DRIFT') THEN RAISE; END IF;
      RETURN result;
    END $$""")


def _create_contact_command() -> None:
    op.execute(r"""CREATE FUNCTION platform.update_billing_contact(expected_version bigint,contact_display_name text,idempotency_key text)
    RETURNS TABLE(workspace_id uuid,billing_account_id uuid,receipt_id uuid,result_version bigint,result_outcome text,completed_at timestamptz)
    LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    DECLARE ws uuid; actor uuid; corr uuid; normalized text; fp bytea; acc platform.workspace_billing_accounts%ROWTYPE; rec platform.billing_contact_command_receipts%ROWTYPE; done timestamptz;
    BEGIN
      IF pg_current_xact_id_if_assigned() IS NULL OR current_setting('asm.context_xid',true) IS DISTINCT FROM pg_current_xact_id_if_assigned()::text THEN RAISE EXCEPTION 'invalid workspace context' USING ERRCODE='42501'; END IF;
      BEGIN ws:=NULLIF(current_setting('asm.workspace_id',true),'')::uuid; actor:=NULLIF(current_setting('asm.actor_id',true),'')::uuid; corr:=NULLIF(current_setting('asm.correlation_id',true),'')::uuid; EXCEPTION WHEN invalid_text_representation THEN RAISE EXCEPTION 'invalid workspace context' USING ERRCODE='42501'; END;
      IF ws IS NULL OR actor IS NULL OR corr IS NULL OR current_setting('asm.actor_kind',true) IS DISTINCT FROM 'user_account' OR NOT EXISTS(SELECT 1 FROM platform.workspace_memberships m JOIN platform.user_accounts u ON u.id=m.user_account_id JOIN platform.workspaces w ON w.id=m.workspace_id WHERE m.workspace_id=ws AND m.user_account_id=actor AND m.role='OWNER' AND m.status='ACTIVE' AND u.status='ACTIVE' AND w.status='ACTIVE') THEN RAISE EXCEPTION 'access denied' USING ERRCODE='42501'; END IF;
      normalized:=btrim(contact_display_name,' ');
      IF expected_version IS NULL OR expected_version<=0 OR idempotency_key IS NULL OR idempotency_key !~ '^[A-Za-z0-9._:-]{1,128}$' OR normalized IS NULL OR char_length(normalized) NOT BETWEEN 1 AND 200 OR octet_length(normalized)>800 OR normalized ~ '[\x00-\x1F\x7F]' THEN RAISE EXCEPTION 'invalid request' USING ERRCODE='22023'; END IF;
      fp:=pg_catalog.sha256(convert_to('{"contact_display_name":"'||replace(replace(normalized,'\','\\'),'"','\"')||'","expected_version":"'||expected_version::text||'","operation":"UPDATE_BILLING_CONTACT","workspace_id":"'||ws::text||'"}','UTF8'));
      SELECT * INTO acc FROM platform.workspace_billing_accounts a WHERE a.workspace_id=ws; IF NOT FOUND THEN RAISE EXCEPTION 'billing account not found' USING ERRCODE='P0002'; END IF;
      INSERT INTO platform.billing_contact_command_receipts(workspace_id,billing_account_id,operation,idempotency_key,request_fingerprint,expected_version,status) VALUES(ws,acc.billing_account_id,'UPDATE_BILLING_CONTACT',idempotency_key,fp,expected_version,'IN_PROGRESS') ON CONFLICT ON CONSTRAINT billing_contact_command_receipts_key DO NOTHING RETURNING * INTO rec;
      IF NOT FOUND THEN
        SELECT * INTO rec FROM platform.billing_contact_command_receipts r WHERE r.workspace_id=ws AND r.operation='UPDATE_BILLING_CONTACT' AND r.idempotency_key=update_billing_contact.idempotency_key FOR UPDATE;
        IF NOT FOUND THEN RAISE EXCEPTION 'receipt serialization failed' USING ERRCODE='40001'; END IF;
        IF rec.request_fingerprint<>fp THEN RAISE EXCEPTION 'idempotency key conflict' USING ERRCODE='23505'; END IF;
        RETURN QUERY SELECT rec.workspace_id,rec.billing_account_id,rec.receipt_id,rec.result_version,rec.result_outcome,rec.completed_at; RETURN;
      END IF;
      -- Receipt FK checks hold KEY SHARE on this same account. NO KEY UPDATE
      -- serializes the non-key mutation without a two-claim lock-upgrade deadlock.
      SELECT * INTO acc FROM platform.workspace_billing_accounts a WHERE a.workspace_id=ws FOR NO KEY UPDATE;
      IF acc.version<>expected_version THEN RAISE EXCEPTION 'stale state' USING ERRCODE='40001'; END IF;
      done:=clock_timestamp();
      IF acc.contact_display_name=normalized THEN result_outcome:='NOOP'; result_version:=acc.version;
      ELSE UPDATE platform.workspace_billing_accounts a SET contact_display_name=normalized,version=a.version+1,updated_at=done WHERE a.workspace_id=ws RETURNING a.version INTO result_version; result_outcome:='UPDATED';
        INSERT INTO app.audit_events(workspace_id,actor_kind,actor_user_account_id,correlation_id,event_type,object_type,object_id,object_version,payload) VALUES(ws,'USER_ACCOUNT',actor,corr,'BILLING_ACCOUNT_CONTACT_UPDATED','WORKSPACE_BILLING_ACCOUNT',acc.billing_account_id,result_version,'{"changed_fields":["contact_display_name"]}');
      END IF;
      UPDATE platform.billing_contact_command_receipts r SET status='SUCCEEDED',result_version=update_billing_contact.result_version,result_outcome=update_billing_contact.result_outcome,completed_at=done WHERE r.workspace_id=ws AND r.receipt_id=rec.receipt_id RETURNING r.workspace_id,r.billing_account_id,r.receipt_id,r.result_version,r.result_outcome,r.completed_at INTO workspace_id,billing_account_id,receipt_id,result_version,result_outcome,completed_at;
      RETURN NEXT;
    END $$""")


def _rls_and_grants() -> None:
    tables = (
        ("platform", "workspace_billing_accounts", True),
        ("platform", "workspace_subscriptions", True),
        ("platform", "workspace_service_modes", True),
        ("app", "audit_events", True),
        ("platform", "billing_contact_command_receipts", False),
    )
    for schema, table, runtime_select in tables:
        op.execute(f"ALTER TABLE {schema}.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {schema}.{table} FORCE ROW LEVEL SECURITY")
        if runtime_select:
            op.execute(
                f"CREATE POLICY {table}_runtime_select ON {schema}.{table} FOR SELECT TO asm_runtime USING (workspace_id = app.current_workspace_id())"
            )
        op.execute(
            f"CREATE POLICY {table}_migrator_all ON {schema}.{table} FOR ALL TO asm_migrator USING (true) WITH CHECK (true)"
        )
    all_tables = (
        "platform.saas_plans",
        "platform.saas_plan_revisions",
        "platform.plan_entitlements",
        "platform.workspace_billing_accounts",
        "platform.workspace_subscriptions",
        "platform.workspace_service_modes",
        "app.audit_events",
        "platform.billing_contact_command_receipts",
    )
    op.execute("REVOKE ALL ON " + ",".join(all_tables) + " FROM PUBLIC, asm_runtime")
    op.execute("GRANT SELECT ON " + ",".join(all_tables[:-1]) + " TO asm_runtime")
    for fn in (
        "platform.guard_plan_revision()",
        "platform.guard_entitlement()",
        "platform.initialize_local_billing(uuid,text,integer,text,text,text,timestamptz,timestamptz,text)",
        "platform.update_billing_contact(bigint,text,text)",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC, asm_runtime")
    op.execute(
        "GRANT EXECUTE ON FUNCTION platform.update_billing_contact(bigint,text,text) TO asm_runtime"
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION platform.update_billing_contact(bigint,text,text)")
    op.execute(
        "DROP FUNCTION platform.initialize_local_billing(uuid,text,integer,text,text,text,timestamptz,timestamptz,text)"
    )
    op.execute("DROP TABLE platform.billing_contact_command_receipts")
    op.execute("DROP TABLE app.audit_events")
    op.execute("DROP TABLE platform.workspace_service_modes")
    op.execute("DROP TABLE platform.workspace_subscriptions")
    op.execute("DROP TABLE platform.workspace_billing_accounts")
    op.execute("DROP TABLE platform.plan_entitlements")
    op.execute("DROP FUNCTION platform.guard_entitlement()")
    op.execute("DROP TABLE platform.saas_plan_revisions")
    op.execute("DROP FUNCTION platform.guard_plan_revision()")
    op.execute("DROP TABLE platform.saas_plans")
