"""Real PostgreSQL evidence for the M1.3 DB-only contract."""

import asyncio
import hashlib
import json
import os
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def migrator():
    url = os.environ["ASM_MIGRATION_DATABASE_URL"]
    assert make_url(url).database == "asm_test"
    engine = create_async_engine(url, hide_parameters=True)
    try:
        yield engine
    finally:
        await engine.dispose()


async def test_m1_3_inventory_extension_rls_and_privileges(migrator):
    async with migrator.connect() as connection:
        extension = (
            await connection.execute(
                text(
                    "SELECT e.extversion,n.nspname FROM pg_extension e "
                    "JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname='btree_gist'"
                )
            )
        ).one()
        assert extension == ("1.8", "extensions")
        tables = (
            (
                await connection.execute(
                    text(
                        "SELECT schemaname||'.'||tablename FROM pg_tables WHERE "
                        "(schemaname,tablename) IN (( 'platform','saas_plans'),"
                        "('platform','saas_plan_revisions'),('platform','plan_entitlements'),"
                        "('platform','workspace_billing_accounts'),"
                        "('platform','workspace_subscriptions'),"
                        "('platform','workspace_service_modes'),('app','audit_events'),"
                        "('platform','billing_contact_command_receipts')) ORDER BY 1"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(tables) == 8
        rls = (
            await connection.execute(
                text(
                    "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE c.relname IN ('workspace_billing_accounts','workspace_subscriptions',"
                    "'workspace_service_modes','audit_events','billing_contact_command_receipts') "
                    "AND c.relrowsecurity AND c.relforcerowsecurity"
                )
            )
        ).scalar_one()
        assert rls == 5
        assert not (
            await connection.execute(
                text(
                    "SELECT has_database_privilege('asm_migrator',current_database(),'CREATE') "
                    "OR has_schema_privilege('asm_migrator','extensions','CREATE')"
                )
            )
        ).scalar_one()


async def test_initializer_manifest_overlap_adjacency_and_replay(migrator):
    first, second = uuid4(), uuid4()
    async with migrator.begin() as connection:
        await connection.execute(
            text("INSERT INTO platform.workspaces(id) VALUES (:a),(:b)"),
            {"a": first, "b": second},
        )
        call = text(
            "SELECT platform.initialize_local_billing(:ws,'test',1,'Example name',"
            "'ACTIVE','COMPED','2026-09-01T00:00:00Z','2026-10-01T00:00:00Z','NORMAL')"
        )
        assert (await connection.execute(call, {"ws": first})).scalar_one() == "INITIALIZED"
        assert (await connection.execute(call, {"ws": first})).scalar_one() == "NOOP"
        assert (await connection.execute(call, {"ws": second})).scalar_one() == "INITIALIZED"
        assert (
            await connection.execute(text("SELECT count(*) FROM platform.saas_plans"))
        ).scalar_one() == 1
        assert (
            await connection.execute(text("SELECT count(*) FROM platform.plan_entitlements"))
        ).scalar_one() == 5
        revision = (
            await connection.execute(
                text(
                    "SELECT plan_revision_id FROM platform.saas_plan_revisions "
                    "WHERE publication_state='SEALED'"
                )
            )
        ).scalar_one()
        # Half-open adjacency is legal.
        await connection.execute(
            text(
                "INSERT INTO platform.workspace_subscriptions(workspace_id,plan_revision_id,"
                "required_publication_state,status,funding_mode,effective_from,effective_until) "
                "VALUES(:ws,:revision,'SEALED','ACTIVE','COMPED',"
                "'2026-10-01T00:00:00Z','2026-11-01T00:00:00Z')"
            ),
            {"ws": first, "revision": revision},
        )
    with pytest.raises(DBAPIError) as caught:
        async with migrator.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO platform.workspace_subscriptions(workspace_id,plan_revision_id,"
                    "required_publication_state,status,funding_mode,effective_from,effective_until) "
                    "VALUES(:ws,:revision,'SEALED','ACTIVE','COMPED',"
                    "'2026-09-15T00:00:00Z','2026-09-20T00:00:00Z')"
                ),
                {"ws": first, "revision": revision},
            )
    assert caught.value.orig.sqlstate == "23P01"


M1_3_TABLES = {
    "platform.saas_plans",
    "platform.saas_plan_revisions",
    "platform.plan_entitlements",
    "platform.workspace_billing_accounts",
    "platform.workspace_subscriptions",
    "platform.workspace_service_modes",
    "app.audit_events",
    "platform.billing_contact_command_receipts",
}
TENANT_TABLES = {
    "platform.workspace_billing_accounts",
    "platform.workspace_subscriptions",
    "platform.workspace_service_modes",
    "app.audit_events",
    "platform.billing_contact_command_receipts",
}

# Canonical §2 column order/type/nullability. ``!`` means NOT NULL.
PHYSICAL_COLUMNS = {
    "platform.saas_plans": "plan_id:uuid! code:text! display_name:text! status:text! created_at:timestamp_with_time_zone!",
    "platform.saas_plan_revisions": "plan_revision_id:uuid! plan_id:uuid! revision:integer! publication_state:text! published_at:timestamp_with_time_zone created_at:timestamp_with_time_zone!",
    "platform.plan_entitlements": "plan_revision_id:uuid! capability_key:text! value_kind:text! enabled:boolean limit_value:bigint criticality:text! created_at:timestamp_with_time_zone!",
    "platform.workspace_billing_accounts": "workspace_id:uuid! billing_account_id:uuid! contact_display_name:text! version:bigint! created_at:timestamp_with_time_zone! updated_at:timestamp_with_time_zone!",
    "platform.workspace_subscriptions": "workspace_id:uuid! subscription_id:uuid! plan_revision_id:uuid! required_publication_state:text! status:text! funding_mode:text! effective_from:timestamp_with_time_zone! effective_until:timestamp_with_time_zone! version:bigint! created_at:timestamp_with_time_zone! updated_at:timestamp_with_time_zone!",
    "platform.workspace_service_modes": "workspace_id:uuid! service_mode_id:uuid! mode:text! reason_code:text! effective_from:timestamp_with_time_zone! effective_until:timestamp_with_time_zone version:bigint! created_at:timestamp_with_time_zone! updated_at:timestamp_with_time_zone!",
    "app.audit_events": "workspace_id:uuid! audit_event_id:uuid! occurred_at:timestamp_with_time_zone! actor_kind:text! actor_user_account_id:uuid correlation_id:uuid! event_type:text! object_type:text! object_id:uuid! object_version:bigint! payload:jsonb!",
    "platform.billing_contact_command_receipts": "workspace_id:uuid! receipt_id:uuid! billing_account_id:uuid! operation:text! idempotency_key:text! request_fingerprint:bytea! expected_version:bigint! status:text! result_version:bigint result_outcome:text created_at:timestamp_with_time_zone! completed_at:timestamp_with_time_zone",
}

EXPECTED_DEFAULTS = {
    "plan_id": "uuidv7()",
    "plan_revision_id": "uuidv7()",
    "billing_account_id": "uuidv7()",
    "subscription_id": "uuidv7()",
    "service_mode_id": "uuidv7()",
    "audit_event_id": "uuidv7()",
    "receipt_id": "uuidv7()",
    "version": "1",
    "created_at": "CURRENT_TIMESTAMP",
    "updated_at": "CURRENT_TIMESTAMP",
    "occurred_at": "CURRENT_TIMESTAMP",
}
ENTITY_DEFAULTS = {
    "platform.saas_plans.plan_id",
    "platform.saas_plan_revisions.plan_revision_id",
    "platform.workspace_billing_accounts.billing_account_id",
    "platform.workspace_subscriptions.subscription_id",
    "platform.workspace_service_modes.service_mode_id",
    "app.audit_events.audit_event_id",
    "platform.billing_contact_command_receipts.receipt_id",
}

# Canonical §2 named key/relationship constraints. Tuple is
# (kind, local columns, referenced relation or None, referenced columns).
KEY_CONSTRAINTS = {
    "platform.saas_plans": {
        "saas_plans_pkey": ("p", ("plan_id",), None, ()),
        "saas_plans_code_key": ("u", ("code",), None, ()),
    },
    "platform.saas_plan_revisions": {
        "saas_plan_revisions_pkey": ("p", ("plan_revision_id",), None, ()),
        "saas_plan_revisions_plan_revision_key": ("u", ("plan_id", "revision"), None, ()),
        "saas_plan_revisions_id_state_key": (
            "u",
            ("plan_revision_id", "publication_state"),
            None,
            (),
        ),
        "saas_plan_revisions_plan_fkey": ("f", ("plan_id",), "platform.saas_plans", ("plan_id",)),
    },
    "platform.plan_entitlements": {
        "plan_entitlements_pkey": ("p", ("plan_revision_id", "capability_key"), None, ()),
        "plan_entitlements_revision_fkey": (
            "f",
            ("plan_revision_id",),
            "platform.saas_plan_revisions",
            ("plan_revision_id",),
        ),
    },
    "platform.workspace_billing_accounts": {
        "workspace_billing_accounts_pkey": ("p", ("workspace_id",), None, ()),
        "workspace_billing_accounts_workspace_id_key": (
            "u",
            ("workspace_id", "billing_account_id"),
            None,
            (),
        ),
        "workspace_billing_accounts_workspace_fkey": (
            "f",
            ("workspace_id",),
            "platform.workspaces",
            ("id",),
        ),
    },
    "platform.workspace_subscriptions": {
        "workspace_subscriptions_pkey": ("p", ("workspace_id", "subscription_id"), None, ()),
        "workspace_subscriptions_workspace_fkey": (
            "f",
            ("workspace_id",),
            "platform.workspaces",
            ("id",),
        ),
        "workspace_subscriptions_revision_state_fkey": (
            "f",
            ("plan_revision_id", "required_publication_state"),
            "platform.saas_plan_revisions",
            ("plan_revision_id", "publication_state"),
        ),
    },
    "platform.workspace_service_modes": {
        "workspace_service_modes_pkey": ("p", ("workspace_id",), None, ()),
        "workspace_service_modes_workspace_id_key": (
            "u",
            ("workspace_id", "service_mode_id"),
            None,
            (),
        ),
        "workspace_service_modes_workspace_fkey": (
            "f",
            ("workspace_id",),
            "platform.workspaces",
            ("id",),
        ),
    },
    "app.audit_events": {
        "audit_events_pkey": ("p", ("workspace_id", "audit_event_id"), None, ()),
        "audit_events_workspace_fkey": ("f", ("workspace_id",), "platform.workspaces", ("id",)),
        "audit_events_actor_fkey": (
            "f",
            ("workspace_id", "actor_user_account_id"),
            "platform.workspace_memberships",
            ("workspace_id", "user_account_id"),
        ),
        "audit_events_object_fkey": (
            "f",
            ("workspace_id", "object_id"),
            "platform.workspace_billing_accounts",
            ("workspace_id", "billing_account_id"),
        ),
    },
    "platform.billing_contact_command_receipts": {
        "billing_contact_command_receipts_pkey": ("p", ("workspace_id", "receipt_id"), None, ()),
        "billing_contact_command_receipts_key": (
            "u",
            ("workspace_id", "operation", "idempotency_key"),
            None,
            (),
        ),
        "billing_contact_command_receipts_workspace_fkey": (
            "f",
            ("workspace_id",),
            "platform.workspaces",
            ("id",),
        ),
        "billing_contact_command_receipts_account_fkey": (
            "f",
            ("workspace_id", "billing_account_id"),
            "platform.workspace_billing_accounts",
            ("workspace_id", "billing_account_id"),
        ),
    },
}
CHECK_NAMES = {
    "platform.saas_plans": {
        "saas_plans_code_check",
        "saas_plans_display_name_check",
        "saas_plans_status_check",
        "saas_plans_created_at_finite_check",
    },
    "platform.saas_plan_revisions": {
        "revision_positive_check",
        "publication_check",
        "created_at_finite_check",
    },
    "platform.plan_entitlements": {
        "capability_key_check",
        "value_check",
        "criticality_check",
        "created_at_finite_check",
    },
    "platform.workspace_billing_accounts": {
        "version_positive_check",
        "created_at_finite_check",
        "updated_at_finite_check",
        "timestamp_order_check",
        "contact_check",
    },
    "platform.workspace_subscriptions": {
        "required_state_check",
        "status_funding_check",
        "interval_check",
        "version_positive_check",
        "created_at_finite_check",
        "updated_at_finite_check",
        "timestamp_order_check",
    },
    "platform.workspace_service_modes": {
        "mode_reason_check",
        "interval_check",
        "version_positive_check",
        "created_at_finite_check",
        "updated_at_finite_check",
        "timestamp_order_check",
    },
    "app.audit_events": {
        "audit_events_occurred_at_finite_check",
        "audit_events_object_version_positive_check",
        "audit_events_discriminator_payload_check",
        "audit_events_payload_size_check",
    },
    "platform.billing_contact_command_receipts": {
        "operation_check",
        "key_check",
        "fingerprint_check",
        "expected_version_positive_check",
        "created_at_finite_check",
        "status_result_check",
    },
}


async def test_exact_physical_schema_constraints_keys_and_grants(migrator):
    """Criteria 8-11, 15, 18-21, 26: bounded physical and privilege surface."""
    async with migrator.connect() as connection:
        tables = set(
            (
                await connection.execute(
                    text(
                        "SELECT schemaname||'.'||tablename FROM pg_tables "
                        "WHERE schemaname IN ('platform','app') AND tablename IN "
                        "('saas_plans','saas_plan_revisions','plan_entitlements',"
                        "'workspace_billing_accounts','workspace_subscriptions',"
                        "'workspace_service_modes','audit_events',"
                        "'billing_contact_command_receipts')"
                    )
                )
            ).scalars()
        )
        assert tables == M1_3_TABLES
        for table, expected in PHYSICAL_COLUMNS.items():
            schema, name = table.split(".")
            columns = (
                await connection.execute(
                    text(
                        "SELECT a.attname,replace(format_type(a.atttypid,a.atttypmod),' ','_'),"
                        "a.attnotnull,pg_get_expr(d.adbin,d.adrelid) FROM pg_attribute a "
                        "JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
                        "LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum "
                        "WHERE n.nspname=:schema AND c.relname=:table AND a.attnum>0 "
                        "AND NOT a.attisdropped ORDER BY a.attnum"
                    ),
                    {"schema": schema, "table": name},
                )
            ).all()
            assert (
                " ".join(
                    f"{col}:{kind}{'!' if required else ''}" for col, kind, required, _ in columns
                )
                == expected
            )
            for column, _, _, default in columns:
                qualified = f"{table}.{column}"
                if qualified in ENTITY_DEFAULTS:
                    assert default == "uuidv7()"
                elif column == "version":
                    assert default == "1"
                elif column in {"created_at", "updated_at", "occurred_at"}:
                    assert default == "CURRENT_TIMESTAMP"
                else:
                    assert default is None
            constraints = (
                await connection.execute(
                    text(
                        "SELECT con.conname,con.contype,"
                        "ARRAY(SELECT a.attname FROM unnest(con.conkey) WITH ORDINALITY k(attnum,n) "
                        "JOIN pg_attribute a ON a.attrelid=con.conrelid AND a.attnum=k.attnum ORDER BY k.n),"
                        "CASE WHEN con.confrelid=0 THEN NULL ELSE (SELECT rn.nspname||'.'||rc.relname FROM pg_class rc JOIN pg_namespace rn ON rn.oid=rc.relnamespace WHERE rc.oid=con.confrelid) END,"
                        "ARRAY(SELECT a.attname FROM unnest(con.confkey) WITH ORDINALITY k(attnum,n) "
                        "JOIN pg_attribute a ON a.attrelid=con.confrelid AND a.attnum=k.attnum ORDER BY k.n),"
                        "con.confdeltype,con.confupdtype,con.condeferrable,con.condeferred,"
                        "pg_get_constraintdef(con.oid,false) FROM pg_constraint con "
                        "WHERE con.conrelid=CAST(:relation AS regclass) ORDER BY con.conname"
                    ),
                    {"relation": table},
                )
            ).all()
            expected_names = set(KEY_CONSTRAINTS[table]) | CHECK_NAMES[table]
            if table == "platform.workspace_subscriptions":
                expected_names.add("workspace_subscriptions_no_overlap_excl")
            # PostgreSQL 18 exposes generated named NOT NULL constraints in
            # pg_constraint as well. Nullability is asserted from pg_attribute
            # above; here require every contract-defined named constraint without
            # treating those server-generated entries as part of the contract.
            assert expected_names <= {row[0] for row in constraints}
            by_name = {row[0]: row for row in constraints}
            for constraint, signature in KEY_CONSTRAINTS[table].items():
                kind, local, referenced, remote = signature
                row = by_name[constraint]
                assert row[1] == kind and tuple(row[2]) == local
                assert row[3] == referenced and tuple(row[4]) == remote
                assert not row[7] and not row[8]
                if kind == "f":
                    assert row[5:7] == ("r", "a")
                    assert row[9].startswith("FOREIGN KEY")
                elif kind == "p":
                    assert row[9] == f"PRIMARY KEY ({', '.join(local)})"
                else:
                    assert row[9] == f"UNIQUE ({', '.join(local)})"
            for constraint in CHECK_NAMES[table]:
                row = by_name[constraint]
                assert row[1] == "c" and row[9].startswith("CHECK (")
            if table == "platform.workspace_subscriptions":
                exclusion = by_name["workspace_subscriptions_no_overlap_excl"]
                assert exclusion[1] == "x" and not exclusion[7] and not exclusion[8]
                assert exclusion[9] == (
                    "EXCLUDE USING gist (workspace_id WITH =, "
                    "tstzrange(effective_from, effective_until, '[)'::text) WITH &&)"
                )
        tenant_flags = {
            row[0]: (row[1], row[2])
            for row in (
                await connection.execute(
                    text(
                        "SELECT n.nspname||'.'||c.relname,c.relrowsecurity,c.relforcerowsecurity "
                        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                        "WHERE n.nspname||'.'||c.relname = ANY(:tables)"
                    ),
                    {"tables": sorted(TENANT_TABLES)},
                )
            )
        }
        assert tenant_flags == {name: (True, True) for name in TENANT_TABLES}
        constraint_types = set(
            (
                await connection.execute(
                    text(
                        "SELECT contype FROM pg_constraint c JOIN pg_class r ON r.oid=c.conrelid "
                        "JOIN pg_namespace n ON n.oid=r.relnamespace "
                        "WHERE n.nspname||'.'||r.relname = ANY(:tables)"
                    ),
                    {"tables": sorted(M1_3_TABLES)},
                )
            ).scalars()
        )
        assert {"p", "u", "f", "c", "x"} <= constraint_types
        for table in sorted(M1_3_TABLES - {"platform.billing_contact_command_receipts"}):
            assert (
                await connection.execute(
                    text("SELECT has_table_privilege('asm_runtime',:table,'SELECT')"),
                    {"table": table},
                )
            ).scalar_one()
        for table in sorted(M1_3_TABLES):
            assert not (
                await connection.execute(
                    text("SELECT has_table_privilege('asm_runtime',:table,'INSERT,UPDATE,DELETE')"),
                    {"table": table},
                )
            ).scalar_one()
        assert not (
            await connection.execute(
                text(
                    "SELECT has_table_privilege('asm_runtime',"
                    "'platform.billing_contact_command_receipts','SELECT')"
                )
            )
        ).scalar_one()


async def test_sealed_manifest_immutability_and_draft_subscription_rejection(migrator):
    """Criteria 22-26: exact manifest, seal immutability, and SEALED-only FK."""
    workspace = uuid4()
    async with migrator.connect() as connection:
        transaction = await connection.begin()
        await connection.execute(
            text("INSERT INTO platform.workspaces(id) VALUES(:id)"), {"id": workspace}
        )
        result = await connection.execute(
            text(
                "SELECT platform.initialize_local_billing(:id,'test',1,'Example name',"
                "'ACTIVE','COMPED','2026-09-01T00:00:00Z','2026-10-01T00:00:00Z','NORMAL')"
            ),
            {"id": workspace},
        )
        assert result.scalar_one() == "INITIALIZED"
        rows = (
            await connection.execute(
                text(
                    "SELECT capability_key,value_kind,enabled,limit_value,criticality "
                    'FROM platform.plan_entitlements ORDER BY capability_key COLLATE "C"'
                )
            )
        ).all()
        lines = "".join(
            f"{key}\t{kind}\t{str(enabled).lower() if kind == 'BOOLEAN' else limit_value}"
            f"\t{criticality}\n"
            for key, kind, enabled, limit_value, criticality in rows
        )
        assert len(rows) == 5
        assert hashlib.sha256(lines.encode()).hexdigest() == (
            "2aed3e0812691c4546997692e664660c7e328783422ae824c8279bd2cef963cc"
        )
        revision = (
            await connection.execute(
                text("SELECT plan_revision_id FROM platform.saas_plan_revisions WHERE revision=1")
            )
        ).scalar_one()
        for statement in (
            "UPDATE platform.saas_plan_revisions SET publication_state='DRAFT' "
            "WHERE plan_revision_id=:revision",
            "DELETE FROM platform.plan_entitlements WHERE plan_revision_id=:revision",
            "INSERT INTO platform.plan_entitlements(plan_revision_id,capability_key,value_kind,"
            "enabled,criticality) VALUES(:revision,'test.extra','BOOLEAN',true,'ESSENTIAL')",
        ):
            with pytest.raises(DBAPIError):
                async with connection.begin_nested():
                    await connection.execute(text(statement), {"revision": revision})
        draft = (
            await connection.execute(
                text(
                    "INSERT INTO platform.saas_plan_revisions(plan_id,revision,publication_state) "
                    "SELECT plan_id,2,'DRAFT' FROM platform.saas_plans WHERE code='test' "
                    "RETURNING plan_revision_id"
                )
            )
        ).scalar_one()
        with pytest.raises(DBAPIError):
            async with connection.begin_nested():
                await connection.execute(
                    text(
                        "INSERT INTO platform.workspace_subscriptions(workspace_id,"
                        "plan_revision_id,required_publication_state,status,funding_mode,"
                        "effective_from,effective_until) VALUES(:ws,:revision,'SEALED',"
                        "'ACTIVE','COMPED','2027-01-01T00:00:00Z','2027-02-01T00:00:00Z')"
                    ),
                    {"ws": workspace, "revision": draft},
                )
        await transaction.rollback()


async def test_entitlement_insert_and_seal_serialize_on_catalog_and_parent_locks(migrator):
    """Criterion 24: a real concurrent writer commits before the waiting seal."""
    async with migrator.begin() as connection:
        plan = (
            await connection.execute(
                text(
                    "INSERT INTO platform.saas_plans(code,display_name,status) "
                    "VALUES(:code,'Concurrency fixture','ACTIVE') RETURNING plan_id"
                ),
                {"code": "concurrency-" + uuid4().hex[:12]},
            )
        ).scalar_one()
        revision = (
            await connection.execute(
                text(
                    "INSERT INTO platform.saas_plan_revisions"
                    "(plan_id,revision,publication_state) VALUES(:plan,1,'DRAFT') "
                    "RETURNING plan_revision_id"
                ),
                {"plan": plan},
            )
        ).scalar_one()
        await connection.execute(
            text(
                "INSERT INTO platform.plan_entitlements"
                "(plan_revision_id,capability_key,value_kind,enabled,limit_value,criticality) "
                "VALUES (:r,'test.m1_3.essential_true','BOOLEAN',true,NULL,'ESSENTIAL'),"
                "(:r,'test.m1_3.standard_false','BOOLEAN',false,NULL,'STANDARD'),"
                "(:r,'test.m1_3.expensive_positive','INTEGER',NULL,3,'EXPENSIVE_OPTIONAL'),"
                "(:r,'test.m1_3.expensive_zero','INTEGER',NULL,0,'EXPENSIVE_OPTIONAL')"
            ),
            {"r": revision},
        )

    writer = await migrator.connect()
    writer_tx = await writer.begin()
    await writer.execute(
        text(
            "INSERT INTO platform.plan_entitlements"
            "(plan_revision_id,capability_key,value_kind,enabled,criticality) "
            "VALUES(:r,'test.m1_3.standard_true','BOOLEAN',true,'STANDARD')"
        ),
        {"r": revision},
    )

    async def seal():
        async with migrator.begin() as connection:
            await connection.execute(text("SELECT pg_advisory_xact_lock(1295070019,1)"))
            await connection.execute(
                text(
                    "SELECT 1 FROM platform.saas_plan_revisions "
                    "WHERE plan_revision_id=:r FOR UPDATE"
                ),
                {"r": revision},
            )
            count, digest = (
                await connection.execute(
                    text(
                        "SELECT count(*),encode(pg_catalog.sha256(convert_to(string_agg("
                        "capability_key||chr(9)||value_kind||chr(9)||CASE WHEN "
                        "value_kind='BOOLEAN' THEN enabled::text ELSE limit_value::text END||"
                        "chr(9)||criticality||chr(10),'' ORDER BY convert_to(capability_key,'UTF8')),"
                        "'UTF8')),'hex') FROM platform.plan_entitlements "
                        "WHERE plan_revision_id=:r"
                    ),
                    {"r": revision},
                )
            ).one()
            assert count == 5
            assert digest == "2aed3e0812691c4546997692e664660c7e328783422ae824c8279bd2cef963cc"
            await connection.execute(
                text(
                    "UPDATE platform.saas_plan_revisions SET publication_state='SEALED',"
                    "published_at=clock_timestamp() WHERE plan_revision_id=:r"
                ),
                {"r": revision},
            )

    sealing = asyncio.create_task(seal())
    await asyncio.sleep(0.2)
    assert not sealing.done(), "seal must wait for writer's advisory/parent locks"
    await writer_tx.commit()
    await writer.close()
    await asyncio.wait_for(sealing, 5)
    with pytest.raises(DBAPIError):
        async with migrator.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO platform.plan_entitlements"
                    "(plan_revision_id,capability_key,value_kind,enabled,criticality) "
                    "VALUES(:r,'test.late','BOOLEAN',true,'ESSENTIAL')"
                ),
                {"r": revision},
            )
    async with migrator.begin() as connection:
        await connection.execute(
            text("ALTER TABLE platform.plan_entitlements DISABLE TRIGGER plan_entitlements_guard")
        )
        await connection.execute(
            text("DELETE FROM platform.plan_entitlements WHERE plan_revision_id=:r"),
            {"r": revision},
        )
        await connection.execute(
            text("DROP TRIGGER saas_plan_revisions_guard ON platform.saas_plan_revisions")
        )
        await connection.execute(
            text("DELETE FROM platform.saas_plan_revisions WHERE plan_revision_id=:r"),
            {"r": revision},
        )
        await connection.execute(
            text("DELETE FROM platform.saas_plans WHERE plan_id=:p"), {"p": plan}
        )
        await connection.execute(
            text(
                "CREATE TRIGGER saas_plan_revisions_guard BEFORE UPDATE OR DELETE ON "
                "platform.saas_plan_revisions FOR EACH ROW EXECUTE FUNCTION "
                "platform.guard_plan_revision()"
            )
        )
        await connection.execute(
            text("ALTER TABLE platform.plan_entitlements ENABLE TRIGGER plan_entitlements_guard")
        )


@pytest.mark.parametrize(
    ("start", "end"),
    [("-infinity", "2027-01-01T00:00:00Z"), ("2027-01-01T00:00:00Z", "infinity")],
)
async def test_finite_intervals_and_tenant_safe_composite_fk_negatives(migrator, start, end):
    """Criteria 10-11: non-finite endpoints and cross-workspace composite FKs fail."""
    first, second = uuid4(), uuid4()
    async with migrator.connect() as connection:
        transaction = await connection.begin()
        await connection.execute(
            text("INSERT INTO platform.workspaces(id) VALUES(:a),(:b)"),
            {"a": first, "b": second},
        )
        for workspace in (first, second):
            await connection.execute(
                text(
                    "SELECT platform.initialize_local_billing(:ws,'test',1,'Example name',"
                    "'ACTIVE','COMPED','2026-09-01T00:00:00Z',"
                    "'2026-10-01T00:00:00Z','NORMAL')"
                ),
                {"ws": workspace},
            )
        revision = (
            await connection.execute(
                text(
                    "SELECT r.plan_revision_id FROM platform.saas_plan_revisions r "
                    "JOIN platform.saas_plans p ON p.plan_id=r.plan_id "
                    "WHERE p.code='test' AND r.revision=1"
                )
            )
        ).scalar_one()
        with pytest.raises(DBAPIError) as interval:
            async with connection.begin_nested():
                await connection.execute(
                    text(
                        "INSERT INTO platform.workspace_subscriptions(workspace_id,"
                        "plan_revision_id,required_publication_state,status,funding_mode,"
                        "effective_from,effective_until) VALUES(:ws,:revision,'SEALED',"
                        "'ACTIVE','COMPED',:start,:end)"
                    ),
                    {"ws": first, "revision": revision, "start": start, "end": end},
                )
        assert interval.value.orig.sqlstate == "23514"
        foreign_account = (
            await connection.execute(
                text(
                    "SELECT billing_account_id FROM platform.workspace_billing_accounts "
                    "WHERE workspace_id=:ws"
                ),
                {"ws": second},
            )
        ).scalar_one()
        with pytest.raises(DBAPIError) as tenant_fk:
            async with connection.begin_nested():
                await connection.execute(
                    text(
                        "INSERT INTO app.audit_events(workspace_id,actor_kind,correlation_id,"
                        "event_type,object_type,object_id,object_version,payload) VALUES"
                        "(:ws,'LOCAL_PROVISIONER',:correlation,'WORKSPACE_BILLING_PROVISIONED',"
                        "'WORKSPACE_BILLING_ACCOUNT',:object,1,'{}')"
                    ),
                    {"ws": first, "correlation": uuid4(), "object": foreign_account},
                )
        assert tenant_fk.value.orig.sqlstate == "23503"
        await transaction.rollback()


async def test_initializer_conflicts_and_concurrent_serialization(migrator):
    """Criteria 27-30: global/workspace serialization and bounded drift conflicts."""
    workspaces = (uuid4(), uuid4())
    async with migrator.begin() as connection:
        await connection.execute(
            text("INSERT INTO platform.workspaces(id) VALUES(:a),(:b)"),
            {"a": workspaces[0], "b": workspaces[1]},
        )
    call = text(
        "SELECT platform.initialize_local_billing(:ws,'test',1,'Example name','ACTIVE',"
        "'COMPED','2026-09-01T00:00:00Z','2026-10-01T00:00:00Z','NORMAL')"
    )

    async def initialize(workspace):
        async with migrator.begin() as connection:
            return (await connection.execute(call, {"ws": workspace})).scalar_one()

    assert await asyncio.gather(*(initialize(ws) for ws in workspaces)) == [
        "INITIALIZED",
        "INITIALIZED",
    ]
    same = uuid4()
    async with migrator.begin() as connection:
        await connection.execute(
            text("INSERT INTO platform.workspaces(id) VALUES(:id)"), {"id": same}
        )
    outcomes = await asyncio.gather(initialize(same), initialize(same))
    assert sorted(outcomes) == ["INITIALIZED", "NOOP"]
    async with migrator.begin() as connection:
        await connection.execute(
            text("UPDATE platform.workspace_billing_accounts SET version=2 WHERE workspace_id=:id"),
            {"id": same},
        )
    assert await initialize(same) == "CONFLICT_STATE_DRIFT"
    partial, incompatible = uuid4(), uuid4()
    async with migrator.begin() as connection:
        await connection.execute(
            text("INSERT INTO platform.workspaces(id) VALUES(:partial),(:incompatible)"),
            {"partial": partial, "incompatible": incompatible},
        )
        await connection.execute(
            text(
                "INSERT INTO platform.workspace_billing_accounts"
                "(workspace_id,contact_display_name) VALUES(:ws,'Do not repair')"
            ),
            {"ws": partial},
        )
    assert await initialize(partial) == "CONFLICT_PARTIAL_STATE"
    async with migrator.connect() as connection:
        assert (
            await connection.execute(
                text(
                    "SELECT contact_display_name FROM platform.workspace_billing_accounts "
                    "WHERE workspace_id=:ws"
                ),
                {"ws": partial},
            )
        ).scalar_one() == "Do not repair"
        assert (
            await connection.execute(
                text(
                    "SELECT count(*) FROM platform.workspace_subscriptions WHERE workspace_id=:ws"
                ),
                {"ws": partial},
            )
        ).scalar_one() == 0

    async with migrator.begin() as connection:
        incompatible_result = (
            await connection.execute(
                text(
                    "SELECT platform.initialize_local_billing(:ws,'test',1,'Example name',"
                    "'TRIALING','TRIAL','2026-09-01T00:00:00Z',"
                    "'2026-10-01T00:00:00Z','NORMAL')"
                ),
                {"ws": incompatible},
            )
        ).scalar_one()
        assert incompatible_result == "CONFLICT_INPUT_MISMATCH"
        assert (
            await connection.execute(
                text(
                    "SELECT count(*) FROM platform.workspace_billing_accounts "
                    "WHERE workspace_id=:ws"
                ),
                {"ws": incompatible},
            )
        ).scalar_one() == 0


async def test_m1_3_runtime_cross_workspace_and_xid_fail_closed(migrator):
    """Criteria 16-17: new readable tenant tables obey Workspace/XID context."""
    runtime = create_async_engine(os.environ["ASM_DATABASE_URL"], hide_parameters=True)
    workspaces, actors = (uuid4(), uuid4()), (uuid4(), uuid4())
    tables = (
        "platform.workspace_billing_accounts",
        "platform.workspace_subscriptions",
        "platform.workspace_service_modes",
        "app.audit_events",
    )
    async with migrator.begin() as connection:
        await connection.execute(
            text("INSERT INTO platform.user_accounts(id) VALUES(:a),(:b)"),
            {"a": actors[0], "b": actors[1]},
        )
        await connection.execute(
            text("INSERT INTO platform.workspaces(id) VALUES(:a),(:b)"),
            {"a": workspaces[0], "b": workspaces[1]},
        )
        for workspace, actor in zip(workspaces, actors, strict=True):
            await connection.execute(
                text(
                    "INSERT INTO platform.workspace_memberships"
                    "(workspace_id,user_account_id,role) VALUES(:ws,:actor,'OWNER')"
                ),
                {"ws": workspace, "actor": actor},
            )
            await connection.execute(
                text(
                    "SELECT platform.initialize_local_billing(:ws,'test',1,'Example name',"
                    "'ACTIVE','COMPED','2026-09-01T00:00:00Z',"
                    "'2026-10-01T00:00:00Z','NORMAL')"
                ),
                {"ws": workspace},
            )
    try:
        for workspace, actor, foreign in zip(workspaces, actors, reversed(workspaces), strict=True):
            async with runtime.begin() as connection:
                await _set_context(connection, workspace, actor, uuid4())
                for table in tables:
                    rows = (
                        (
                            await connection.execute(
                                text(f"SELECT workspace_id FROM {table}")  # noqa: S608
                            )
                        )
                        .scalars()
                        .all()
                    )
                    assert rows and set(rows) == {workspace} and foreign not in rows
        for context_sql in (
            None,
            "SELECT set_config('asm.workspace_id','malformed',true),"
            "set_config('asm.context_xid',pg_current_xact_id()::text,true)",
            "SELECT set_config('asm.workspace_id',:ws,true),"
            "set_config('asm.actor_id',:actor,true),"
            "set_config('asm.actor_kind','user_account',true),"
            "set_config('asm.correlation_id',:correlation,true),"
            "set_config('asm.context_xid','0',true)",
        ):
            async with runtime.begin() as connection:
                if context_sql:
                    await connection.execute(
                        text(context_sql),
                        {
                            "ws": str(workspaces[0]),
                            "actor": str(actors[0]),
                            "correlation": str(uuid4()),
                        },
                    )
                for table in tables:
                    assert (
                        await connection.execute(text(f"SELECT count(*) FROM {table}"))
                    ).scalar_one() == 0
                with pytest.raises(DBAPIError) as command_denied:
                    await connection.execute(
                        text("SELECT * FROM platform.update_billing_contact(1,'Safe','xid-denied')")
                    )
            assert command_denied.value.orig.sqlstate == "42501"
    finally:
        await runtime.dispose()


def _canonical_fingerprint(workspace, version, name):
    payload = {
        "contact_display_name": name,
        "expected_version": str(version),
        "operation": "UPDATE_BILLING_CONTACT",
        "workspace_id": str(workspace),
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).digest()


PUBLISHED_FINGERPRINT_VECTORS = [
    ("Example name", "813d712466b9605186455d77032311a5e7865f48a5db0524e90b3f120a1d4b2a"),
    ("  Example name  ", "813d712466b9605186455d77032311a5e7865f48a5db0524e90b3f120a1d4b2a"),
    ("Анна", "cc4623b8517c225cc787e1eb961997592535ef07fc4184193c43862484b25bd8"),
    ('A"B\\C/D', "a90b071bf4761bda6e42a025e6c7f231b386e453238dddb58cc2db7b94e0d275"),
    ("Studio 🎨", "ffa9252a316a9d8001d20c7d2efe2e842294de6f45710df0faca802fd8a52dbd"),
    ("A\u2028B\u2029C", "fc36542d1fe82f730b56f8ad004d7aab3d6bb26208e0b740e0ac3e479f593d54"),
    ("é", "69ebd81a850211d04df9055a77ff95468dc1ff88acb568514c11f62d416f0c87"),
    ("e\u0301", "07c64318f29cbe6803800928ebf5d4b27436c63f850f1b190eb8418c79d79030"),
]


@pytest.mark.parametrize(("name", "expected"), PUBLISHED_FINGERPRINT_VECTORS)
async def test_exact_published_fingerprint_vectors_in_postgres(migrator, name, expected):
    """Criterion 43: PostgreSQL SHA-256 matches every distinct published vector."""
    workspace = UUID("01990000-0000-7000-8000-000000000001")
    normalized = name.strip(" ")
    canonical = json.dumps(
        {
            "contact_display_name": normalized,
            "expected_version": "7",
            "operation": "UPDATE_BILLING_CONTACT",
            "workspace_id": str(workspace),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    async with migrator.connect() as connection:
        digest = (
            await connection.execute(
                text("SELECT encode(pg_catalog.sha256(convert_to(:value,'UTF8')),'hex')"),
                {"value": canonical},
            )
        ).scalar_one()
    assert digest == expected
    assert _canonical_fingerprint(workspace, 7, normalized).hex() == expected


async def _set_context(connection, workspace, actor, correlation):
    await connection.execute(
        text(
            "SELECT set_config('asm.workspace_id',:ws,true),"
            "set_config('asm.actor_id',:actor,true),"
            "set_config('asm.actor_kind','user_account',true),"
            "set_config('asm.correlation_id',:correlation,true),"
            "set_config('asm.context_xid',pg_current_xact_id()::text,true)"
        ),
        {"ws": str(workspace), "actor": str(actor), "correlation": str(correlation)},
    )


async def test_billing_contact_authorization_cas_replay_audit_and_fingerprint(migrator):
    """Criteria 31-45: authorization, CAS, replay, atomic Audit, fingerprint, validation."""
    runtime_url = os.environ["ASM_DATABASE_URL"]
    runtime = create_async_engine(runtime_url, hide_parameters=True)
    workspace = UUID("01990000-0000-7000-8000-000000000001")
    owner, outsider = uuid4(), uuid4()
    async with migrator.begin() as connection:
        await connection.execute(
            text("INSERT INTO platform.user_accounts(id) VALUES(:a),(:b)"),
            {"a": owner, "b": outsider},
        )
        await connection.execute(
            text("INSERT INTO platform.workspaces(id) VALUES(:id)"), {"id": workspace}
        )
        await connection.execute(
            text(
                "INSERT INTO platform.workspace_memberships(workspace_id,user_account_id,role) VALUES(:ws,:owner,'OWNER')"
            ),
            {"ws": workspace, "owner": owner},
        )
        await connection.execute(
            text(
                "SELECT platform.initialize_local_billing(:ws,'test',1,'Old name','ACTIVE','COMPED','2026-09-01T00:00:00Z','2026-10-01T00:00:00Z','NORMAL')"
            ),
            {"ws": workspace},
        )
        await connection.execute(
            text("UPDATE platform.workspace_billing_accounts SET version=7 WHERE workspace_id=:ws"),
            {"ws": workspace},
        )
    try:
        async with runtime.begin() as connection:
            await _set_context(connection, workspace, outsider, uuid4())
            with pytest.raises(DBAPIError) as denied:
                await connection.execute(
                    text("SELECT * FROM platform.update_billing_contact(7,'Example name','denied')")
                )
        assert denied.value.orig.sqlstate == "42501"
        async with runtime.begin() as connection:
            await _set_context(connection, workspace, owner, uuid4())
            updated = (
                (
                    await connection.execute(
                        text(
                            "SELECT * FROM platform.update_billing_contact(7,'Example name','key-1')"
                        )
                    )
                )
                .mappings()
                .one()
            )
            assert updated["result_outcome"] == "UPDATED" and updated["result_version"] == 8
        async with runtime.begin() as connection:
            await _set_context(connection, workspace, owner, uuid4())
            replay = (
                (
                    await connection.execute(
                        text(
                            "SELECT * FROM platform.update_billing_contact(7,'Example name','key-1')"
                        )
                    )
                )
                .mappings()
                .one()
            )
            assert dict(replay) == dict(updated)
        async with migrator.connect() as connection:
            before = (
                await connection.execute(
                    text(
                        "SELECT (SELECT count(*) FROM app.audit_events WHERE workspace_id=:ws "
                        "AND event_type='BILLING_ACCOUNT_CONTACT_UPDATED'),"
                        "(SELECT count(*) FROM platform.billing_contact_command_receipts "
                        "WHERE workspace_id=:ws),"
                        "(SELECT version FROM platform.workspace_billing_accounts "
                        "WHERE workspace_id=:ws),"
                        "(SELECT contact_display_name FROM platform.workspace_billing_accounts "
                        "WHERE workspace_id=:ws)"
                    ),
                    {"ws": workspace},
                )
            ).one()
        async with runtime.begin() as connection:
            await _set_context(connection, workspace, owner, uuid4())
            with pytest.raises(DBAPIError) as stale:
                await connection.execute(
                    text("SELECT * FROM platform.update_billing_contact(7,'Example name','stale')")
                )
        assert stale.value.orig.sqlstate == "40001"
        async with migrator.connect() as connection:
            after = (
                await connection.execute(
                    text(
                        "SELECT (SELECT count(*) FROM app.audit_events WHERE workspace_id=:ws "
                        "AND event_type='BILLING_ACCOUNT_CONTACT_UPDATED'),"
                        "(SELECT count(*) FROM platform.billing_contact_command_receipts "
                        "WHERE workspace_id=:ws),"
                        "(SELECT version FROM platform.workspace_billing_accounts "
                        "WHERE workspace_id=:ws),"
                        "(SELECT contact_display_name FROM platform.workspace_billing_accounts "
                        "WHERE workspace_id=:ws)"
                    ),
                    {"ws": workspace},
                )
            ).one()
            assert after == before
        async with runtime.begin() as connection:
            await _set_context(connection, workspace, owner, uuid4())
            noop = (
                (
                    await connection.execute(
                        text(
                            "SELECT * FROM platform.update_billing_contact(8,"
                            "'  Example name  ','noop')"
                        )
                    )
                )
                .mappings()
                .one()
            )
            assert noop["result_outcome"] == "NOOP" and noop["result_version"] == 8
        async with migrator.connect() as connection:
            noop_receipt = (
                await connection.execute(
                    text(
                        "SELECT status,result_outcome,result_version FROM "
                        "platform.billing_contact_command_receipts WHERE workspace_id=:ws "
                        "AND idempotency_key='noop'"
                    ),
                    {"ws": workspace},
                )
            ).one()
            assert noop_receipt == ("SUCCEEDED", "NOOP", 8)
            assert (
                await connection.execute(
                    text(
                        "SELECT count(*) FROM app.audit_events WHERE workspace_id=:ws "
                        "AND event_type='BILLING_ACCOUNT_CONTACT_UPDATED'"
                    ),
                    {"ws": workspace},
                )
            ).scalar_one() == 1
        async with runtime.begin() as connection:
            await _set_context(connection, workspace, owner, uuid4())
            with pytest.raises(DBAPIError) as conflict:
                await connection.execute(
                    text("SELECT * FROM platform.update_billing_contact(8,'Different','key-1')")
                )
        assert conflict.value.orig.sqlstate == "23505"
        async with migrator.connect() as connection:
            atomic_before = (
                await connection.execute(
                    text(
                        "SELECT a.version,a.contact_display_name,"
                        "(SELECT count(*) FROM platform.billing_contact_command_receipts r "
                        "WHERE r.workspace_id=a.workspace_id),"
                        "(SELECT count(*) FROM app.audit_events e WHERE "
                        "e.workspace_id=a.workspace_id AND "
                        "e.event_type='BILLING_ACCOUNT_CONTACT_UPDATED') "
                        "FROM platform.workspace_billing_accounts a WHERE a.workspace_id=:ws"
                    ),
                    {"ws": workspace},
                )
            ).one()
        with pytest.raises(DBAPIError):
            async with runtime.begin() as connection:
                await _set_context(connection, workspace, owner, uuid4())
                changed = await connection.execute(
                    text(
                        "SELECT * FROM platform.update_billing_contact"
                        "(8,'Atomic rollback sentinel','atomic-rollback')"
                    )
                )
                assert changed.mappings().one()["result_outcome"] == "UPDATED"
                await connection.execute(text("SELECT 1/0"))
        async with migrator.connect() as connection:
            atomic_after = (
                await connection.execute(
                    text(
                        "SELECT a.version,a.contact_display_name,"
                        "(SELECT count(*) FROM platform.billing_contact_command_receipts r "
                        "WHERE r.workspace_id=a.workspace_id),"
                        "(SELECT count(*) FROM app.audit_events e WHERE "
                        "e.workspace_id=a.workspace_id AND "
                        "e.event_type='BILLING_ACCOUNT_CONTACT_UPDATED') "
                        "FROM platform.workspace_billing_accounts a WHERE a.workspace_id=:ws"
                    ),
                    {"ws": workspace},
                )
            ).one()
            assert atomic_after == atomic_before
        async with migrator.connect() as connection:
            receipt = (
                await connection.execute(
                    text(
                        "SELECT request_fingerprint FROM platform.billing_contact_command_receipts WHERE workspace_id=:ws AND idempotency_key='key-1'"
                    ),
                    {"ws": workspace},
                )
            ).scalar_one()
            assert receipt == _canonical_fingerprint(workspace, 7, "Example name")
            audit = (
                await connection.execute(
                    text(
                        "SELECT payload::text FROM app.audit_events WHERE workspace_id=:ws AND event_type='BILLING_ACCOUNT_CONTACT_UPDATED'"
                    ),
                    {"ws": workspace},
                )
            ).scalar_one()
            assert audit == '{"changed_fields": ["contact_display_name"]}'
            assert "Example name" not in audit
            receipt_text = (
                (
                    await connection.execute(
                        text(
                            "SELECT row_to_json(r)::text FROM "
                            "platform.billing_contact_command_receipts r WHERE workspace_id=:ws"
                        ),
                        {"ws": workspace},
                    )
                )
                .scalars()
                .all()
            )
            assert all("Example name" not in value for value in receipt_text)
        for bad in ("", "A\nB", "A\tB", "A\x7fB", "A" * 201, "é" * 201, "🎨" * 201):
            async with runtime.begin() as connection:
                await _set_context(connection, workspace, owner, uuid4())
                with pytest.raises(DBAPIError) as invalid:
                    await connection.execute(
                        text("SELECT * FROM platform.update_billing_contact(8,:name,:key)"),
                        {"name": bad, "key": "invalid-" + uuid4().hex},
                    )
            assert invalid.value.orig.sqlstate == "22023"
        for version, key in (
            (0, "zero"),
            (-1, "negative"),
            (8, ""),
            (8, "k" * 129),
            (8, "bad key!"),
        ):
            async with runtime.begin() as connection:
                await _set_context(connection, workspace, owner, uuid4())
                with pytest.raises(DBAPIError) as invalid:
                    await connection.execute(
                        text(
                            "SELECT * FROM platform.update_billing_contact(:version,"
                            "'Example name',:key)"
                        ),
                        {"version": version, "key": key},
                    )
            assert invalid.value.orig.sqlstate == "22023"
        # Exercise the encoder inside the actual command, not merely the reference
        # encoder above. Resetting this synthetic fixture is migrator-only test setup.
        for index, (input_name, expected_digest) in enumerate(PUBLISHED_FINGERPRINT_VECTORS):
            async with migrator.begin() as connection:
                await connection.execute(
                    text(
                        "DELETE FROM platform.billing_contact_command_receipts "
                        "WHERE workspace_id=:ws"
                    ),
                    {"ws": workspace},
                )
                await connection.execute(
                    text(
                        "DELETE FROM app.audit_events WHERE workspace_id=:ws AND "
                        "event_type='BILLING_ACCOUNT_CONTACT_UPDATED'"
                    ),
                    {"ws": workspace},
                )
                await connection.execute(
                    text(
                        "UPDATE platform.workspace_billing_accounts SET "
                        "contact_display_name='Reset fixture',version=7 WHERE workspace_id=:ws"
                    ),
                    {"ws": workspace},
                )
            async with runtime.begin() as connection:
                await _set_context(connection, workspace, owner, uuid4())
                encoded = (
                    (
                        await connection.execute(
                            text("SELECT * FROM platform.update_billing_contact(7,:name,:key)"),
                            {"name": input_name, "key": f"published-{index}"},
                        )
                    )
                    .mappings()
                    .one()
                )
                assert encoded["result_outcome"] == "UPDATED"
            async with migrator.connect() as connection:
                stored = (
                    await connection.execute(
                        text(
                            "SELECT encode(request_fingerprint,'hex') FROM "
                            "platform.billing_contact_command_receipts WHERE "
                            "workspace_id=:ws AND idempotency_key=:key"
                        ),
                        {"ws": workspace, "key": f"published-{index}"},
                    )
                ).scalar_one()
                assert stored == expected_digest
    finally:
        await runtime.dispose()


@pytest.mark.parametrize("different_fingerprint", [False, True])
async def test_concurrent_new_idempotency_key_serializes_before_account_lock(
    migrator, different_fingerprint
):
    """C8-M1.3-DB-01: a UNIQUE claim waits, then replays or conflicts boundedly."""
    runtime = create_async_engine(os.environ["ASM_DATABASE_URL"], hide_parameters=True)
    workspace, owner = uuid4(), uuid4()
    blocker = blocker_tx = winner = contender = None
    async with migrator.begin() as connection:
        await connection.execute(
            text("INSERT INTO platform.user_accounts(id) VALUES(:id)"), {"id": owner}
        )
        await connection.execute(
            text("INSERT INTO platform.workspaces(id) VALUES(:id)"), {"id": workspace}
        )
        await connection.execute(
            text(
                "INSERT INTO platform.workspace_memberships(workspace_id,user_account_id,role) VALUES(:ws,:owner,'OWNER')"
            ),
            {"ws": workspace, "owner": owner},
        )
        await connection.execute(
            text(
                "SELECT platform.initialize_local_billing(:ws,'test',1,'Before race','ACTIVE','COMPED','2026-09-01T00:00:00Z','2026-10-01T00:00:00Z','NORMAL')"
            ),
            {"ws": workspace},
        )

    async def command(name, pid_future):
        async with runtime.begin() as connection:
            # The observer has a five-second deadline for each lock phase. Keep the
            # disposable test transaction alive across both phases without changing
            # the runtime role's production defaults.
            await connection.execute(text("SET LOCAL lock_timeout = '15s'"))
            await connection.execute(text("SET LOCAL statement_timeout = '20s'"))
            pid_future.set_result(
                (await connection.execute(text("SELECT pg_backend_pid()"))).scalar_one()
            )
            await _set_context(connection, workspace, owner, uuid4())
            return (
                (
                    await connection.execute(
                        text(
                            "SELECT * FROM platform.update_billing_contact(1,:name,'concurrent-key')"
                        ),
                        {"name": name},
                    )
                )
                .mappings()
                .one()
            )

    def fail_if_command_finished(task, phase):
        if not task.done():
            return
        if task.cancelled():
            raise AssertionError(f"{phase} was cancelled before the expected lock wait")
        error = task.exception()
        if error is not None:
            sqlstate = getattr(getattr(error, "orig", None), "sqlstate", None)
            detail = f" with SQLSTATE {sqlstate}" if sqlstate is not None else ""
            raise AssertionError(f"{phase} failed before the expected lock wait{detail}") from error
        raise AssertionError(f"{phase} completed before the expected lock wait")

    async def wait_until_lock_wait(task, pid, expected_blocker_pid, phase):
        async def observe():
            while True:
                fail_if_command_finished(task, phase)
                # Ordinary PostgreSQL roles can inspect their own sessions. Observing
                # asm_runtime from asm_migrator hides the wait fields unless extra
                # monitoring privileges are granted, which the application roles must
                # not receive merely for this test.
                async with runtime.connect() as connection:
                    row = (
                        await connection.execute(
                            text(
                                "SELECT state,wait_event_type,"
                                ":expected_blocker_pid=ANY(pg_catalog.pg_blocking_pids(pid)) "
                                "AS blocked_by_expected FROM pg_catalog.pg_stat_activity "
                                "WHERE pid=:pid AND usename=current_user"
                            ),
                            {
                                "pid": pid,
                                "expected_blocker_pid": expected_blocker_pid,
                            },
                        )
                    ).one_or_none()
                if (
                    row is not None
                    and row.state == "active"
                    and row.wait_event_type == "Lock"
                    and row.blocked_by_expected
                ):
                    return
                await asyncio.sleep(0.02)

        try:
            await asyncio.wait_for(observe(), 5)
        except TimeoutError as error:
            fail_if_command_finished(task, phase)
            raise AssertionError(
                f"{phase} did not enter the expected lock wait before the observer deadline"
            ) from error

    try:
        blocker = await migrator.connect()
        blocker_tx = await blocker.begin()
        blocker_pid = (await blocker.execute(text("SELECT pg_backend_pid()"))).scalar_one()
        await blocker.execute(
            text(
                "SELECT 1 FROM platform.workspace_billing_accounts WHERE workspace_id=:ws FOR NO KEY UPDATE"
            ),
            {"ws": workspace},
        )
        loop = asyncio.get_running_loop()
        winner_pid = loop.create_future()
        contender_pid = loop.create_future()
        winner = asyncio.create_task(command("Winner value", winner_pid))
        winner_backend_pid = await asyncio.wait_for(winner_pid, 5)
        await wait_until_lock_wait(winner, winner_backend_pid, blocker_pid, "initial claimant")
        assert not winner.done(), "claimant must wait on explicit account FOR UPDATE"
        contender = asyncio.create_task(
            command("Different value" if different_fingerprint else "Winner value", contender_pid)
        )
        contender_backend_pid = await asyncio.wait_for(contender_pid, 5)
        await wait_until_lock_wait(
            contender,
            contender_backend_pid,
            winner_backend_pid,
            "contending claimant",
        )
        assert not contender.done(), "contender must wait on the uncommitted UNIQUE receipt claim"
        await blocker_tx.commit()
        blocker_tx = None
        await blocker.close()
        blocker = None
        winning_result = await asyncio.wait_for(winner, 5)
        if different_fingerprint:
            with pytest.raises(DBAPIError) as conflict:
                await asyncio.wait_for(contender, 5)
            assert conflict.value.orig.sqlstate == "23505"
        else:
            replay = await asyncio.wait_for(contender, 5)
            assert dict(replay) == dict(winning_result)
        async with migrator.connect() as connection:
            state = (
                await connection.execute(
                    text(
                        "SELECT (SELECT count(*) FROM platform.billing_contact_command_receipts WHERE workspace_id=:ws AND idempotency_key='concurrent-key'),(SELECT count(*) FROM app.audit_events WHERE workspace_id=:ws AND event_type='BILLING_ACCOUNT_CONTACT_UPDATED'),version,contact_display_name FROM platform.workspace_billing_accounts WHERE workspace_id=:ws"
                    ),
                    {"ws": workspace},
                )
            ).one()
            assert state == (1, 1, 2, "Winner value")
    finally:
        if blocker_tx is not None and blocker_tx.is_active:
            await blocker_tx.rollback()
        if blocker is not None:
            await blocker.close()
        for task in (winner, contender):
            if task is not None and not task.done():
                task.cancel()
        pending = [task for task in (winner, contender) if task is not None]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        await runtime.dispose()


@pytest.mark.parametrize(
    ("mode", "reason", "allowed"),
    [
        ("NORMAL", "PROVISIONED_LOCAL", {"ESSENTIAL", "STANDARD", "EXPENSIVE_OPTIONAL"}),
        ("GRACE", "TEST_GRACE", {"ESSENTIAL", "STANDARD"}),
        ("LIMITED", "TEST_LIMITED", {"ESSENTIAL"}),
        ("SUSPENDED", "TEST_SUSPENDED", set()),
    ],
)
async def test_coherent_entitlement_snapshot_and_service_mode_filtering(
    migrator, mode, reason, allowed
):
    """Criteria 46-48: one-statement snapshot, mode filtering, inactive intervals."""
    workspace = uuid4()
    async with migrator.connect() as connection:
        transaction = await connection.begin()
        await connection.execute(
            text("INSERT INTO platform.workspaces(id) VALUES(:id)"), {"id": workspace}
        )
        await connection.execute(
            text(
                "SELECT platform.initialize_local_billing(:ws,'test',1,'Example name',"
                "'ACTIVE','COMPED','2026-09-01T00:00:00Z','2026-10-01T00:00:00Z','NORMAL')"
            ),
            {"ws": workspace},
        )
        await connection.execute(
            text(
                "UPDATE platform.workspace_service_modes SET mode=:mode,reason_code=:reason,"
                "effective_from='2026-09-01T00:00:00Z',effective_until='2026-10-01T00:00:00Z' "
                "WHERE workspace_id=:ws"
            ),
            {"mode": mode, "reason": reason, "ws": workspace},
        )
        snapshot = (
            await connection.execute(
                text(
                    "WITH instant AS (SELECT '2026-09-15T00:00:00Z'::timestamptz AS now), "
                    "current_state AS (SELECT s.plan_revision_id,m.mode FROM instant i "
                    "JOIN platform.workspace_subscriptions s ON s.workspace_id=:ws "
                    "AND i.now>=s.effective_from AND i.now<s.effective_until "
                    "JOIN platform.workspace_service_modes m ON m.workspace_id=s.workspace_id "
                    "AND i.now>=m.effective_from AND (m.effective_until IS NULL OR i.now<m.effective_until)) "
                    "SELECT e.capability_key,e.criticality FROM current_state c "
                    "JOIN platform.plan_entitlements e ON e.plan_revision_id=c.plan_revision_id "
                    "WHERE CASE c.mode WHEN 'NORMAL' THEN true WHEN 'GRACE' THEN "
                    "e.criticality IN ('ESSENTIAL','STANDARD') WHEN 'LIMITED' THEN "
                    "e.criticality='ESSENTIAL' ELSE false END ORDER BY e.capability_key"
                ),
                {"ws": workspace},
            )
        ).all()
        assert {criticality for _, criticality in snapshot} == allowed
        inactive = (
            await connection.execute(
                text(
                    "WITH instant AS (SELECT '2027-01-01T00:00:00Z'::timestamptz AS now) "
                    "SELECT count(*) FROM instant i JOIN platform.workspace_subscriptions s "
                    "ON s.workspace_id=:ws AND i.now>=s.effective_from AND i.now<s.effective_until "
                    "JOIN platform.workspace_service_modes m ON m.workspace_id=s.workspace_id "
                    "AND i.now>=m.effective_from AND (m.effective_until IS NULL OR i.now<m.effective_until)"
                ),
                {"ws": workspace},
            )
        ).scalar_one()
        assert inactive == 0
        subscription_inactive, mode_active = (
            await connection.execute(
                text(
                    "WITH instant AS (SELECT '2026-10-15T00:00:00Z'::timestamptz AS now) "
                    "SELECT (SELECT count(*) FROM platform.workspace_subscriptions s,instant i "
                    "WHERE s.workspace_id=:ws AND i.now>=s.effective_from AND i.now<s.effective_until),"
                    "(SELECT count(*) FROM platform.workspace_service_modes m,instant i "
                    "WHERE m.workspace_id=:ws AND i.now>=m.effective_from AND "
                    "(m.effective_until IS NULL OR i.now<m.effective_until))"
                ),
                {"ws": workspace},
            )
        ).one()
        assert subscription_inactive == 0
        assert mode_active == 0  # finite initializer mode is independently expired
        await connection.execute(
            text(
                "UPDATE platform.workspace_service_modes SET effective_from='2026-08-01T00:00:00Z',"
                "effective_until=NULL WHERE workspace_id=:ws"
            ),
            {"ws": workspace},
        )
        subscription_inactive, mode_active = (
            await connection.execute(
                text(
                    "WITH instant AS (SELECT '2026-10-15T00:00:00Z'::timestamptz AS now) "
                    "SELECT (SELECT count(*) FROM platform.workspace_subscriptions s,instant i "
                    "WHERE s.workspace_id=:ws AND i.now>=s.effective_from AND i.now<s.effective_until),"
                    "(SELECT count(*) FROM platform.workspace_service_modes m,instant i "
                    "WHERE m.workspace_id=:ws AND i.now>=m.effective_from AND "
                    "(m.effective_until IS NULL OR i.now<m.effective_until))"
                ),
                {"ws": workspace},
            )
        ).one()
        assert (subscription_inactive, mode_active) == (0, 1)
        await connection.execute(
            text(
                "UPDATE platform.workspace_service_modes SET effective_from='2026-09-20T00:00:00Z',"
                "effective_until='2026-11-01T00:00:00Z' WHERE workspace_id=:ws"
            ),
            {"ws": workspace},
        )
        subscription_active, mode_future = (
            await connection.execute(
                text(
                    "WITH instant AS (SELECT '2026-09-15T00:00:00Z'::timestamptz AS now) "
                    "SELECT (SELECT count(*) FROM platform.workspace_subscriptions s,instant i "
                    "WHERE s.workspace_id=:ws AND i.now>=s.effective_from AND i.now<s.effective_until),"
                    "(SELECT count(*) FROM platform.workspace_service_modes m,instant i "
                    "WHERE m.workspace_id=:ws AND i.now>=m.effective_from AND "
                    "(m.effective_until IS NULL OR i.now<m.effective_until))"
                ),
                {"ws": workspace},
            )
        ).one()
        assert (subscription_active, mode_future) == (1, 0)
        await transaction.rollback()
