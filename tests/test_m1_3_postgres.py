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
                text("SELECT plan_revision_id FROM platform.saas_plan_revisions WHERE revision=1")
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
