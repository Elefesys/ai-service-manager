"""Generic PG fixtures: exact current state and bounded historical schema phases.

Historical validators remain closed. Nothing here resets native usage or changes
the application readiness gate. Four-process/image proofs remain separate gates.
"""

import asyncio
import hashlib
import json
import runpy
from contextlib import asynccontextmanager
from functools import cache
from pathlib import Path

import pytest
from asm.foundation import tracer
from sqlalchemy import text

# Also used when the egress file is executed directly, without pytest's root
# pythonpath (the retained historical controller entrypoints stay unchanged).
_catalog = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "scripts/native_context_db_catalog.py")
)


@cache
def current_source():
    return _catalog["source_catalog"](Path(__file__).resolve().parents[1])


async def assert_current_schema(c):
    assert (await c.execute(text("SELECT current_user"))).scalar_one() == "asm_migrator"
    assert (
        await c.execute(text("SELECT version_num FROM platform.alembic_version"))
    ).scalar_one() == "0013"
    original_path = (await c.execute(text("SHOW search_path"))).scalar_one()
    await c.execute(text("SET LOCAL search_path=pg_catalog,pg_temp"))
    expected = current_source()
    functions = [dict(row) for row in (await c.execute(text(_catalog["FUNCTION_SQL"]))).mappings()]
    resolved = dict(
        (
            await c.execute(
                text(
                    "SELECT sig,to_regprocedure(sig)::bigint FROM jsonb_array_elements_text(CAST(:s AS jsonb)) AS t(sig)"
                ),
                {"s": json.dumps(list(expected["functions"]))},
            )
        ).all()
    )
    full, nonfunction = (await c.execute(text(_catalog["CATALOG_SQL"]))).one()
    profile = (await c.execute(text("SELECT platform.human_context_schema_profile()"))).scalar_one()
    await c.execute(text("SELECT set_config('search_path',:path,true)"), {"path": original_path})
    _catalog["compare_catalog"](expected, functions, resolved, full, nonfunction, lambda: profile)
    return full


async def current_snapshot(c):
    """All 45 complete row multisets plus the independently checked full catalog."""
    catalog = await assert_current_schema(c)
    rows = {}
    for table in sorted(current_source()["columns"]):
        values = (await c.execute(text(f"SELECT to_jsonb(t) FROM {table} AS t"))).scalars()
        canonical = sorted(json.dumps(v, sort_keys=True, separators=(",", ":")) for v in values)
        rows[table] = (len(canonical), hashlib.sha256("\n".join(canonical).encode()).hexdigest())
    assert len(rows) == 45
    return rows, catalog


@asynccontextmanager
async def historical_schema(h, revision):
    """Use actual migration guards; always restore 0013 before outer fixture cleanup."""
    from test_m2_1_schema_postgres import _migrate

    assert revision in {"0011", "0012"}
    async with h.migrator.connect() as c:
        before = await assert_current_schema(c)
    await h.runtime.engine.dispose()
    try:
        await _migrate("downgrade", revision)
        with pytest.raises(RuntimeError, match="schema"):
            await h.runtime.check()
        yield
    finally:
        await _migrate("upgrade", "0013")
        await h.runtime.engine.dispose()
        await h.runtime.check()
        with pytest.raises(RuntimeError, match="schema"):
            await check(h.runtime)
        async with h.migrator.connect() as c:
            assert await assert_current_schema(c) == before


async def paired_p_readiness(h):
    """The frozen P checker accepts P; the current application must reject P."""
    from test_telegram_egress_postgres import material_catalog_profile

    async with h.migrator.connect() as c:
        proof = await material_catalog_profile(c)
        assert (proof["tables"], proof["functions"]) == (42, 132)
    with pytest.raises(RuntimeError, match="schema"):
        await h.runtime.check()
    await check(h.runtime)


# Exact RuntimeDatabase.check extracted from frozen P/e205e22051bc06295758b504d84699652b176c15,
# backend/src/asm/foundation.py Git blob a973374267f808151bebf78da6fffbe2ff750c64.
# Its module constant is fixed independently of the current application module.
DATABASE_SCHEMA_REVISION = "0012"


async def check(self) -> None:
    with tracer.start_as_current_span("database.readiness"):
        async with asyncio.timeout(3), self.engine.connect() as connection:
            role = (
                (
                    await connection.execute(
                        text(
                            "\n                    SELECT rolname, rolsuper, rolbypassrls,\n                        has_schema_privilege(current_user, 'app', 'CREATE') AS app_ddl,\n                        has_schema_privilege(current_user, 'platform', 'CREATE') AS platform_ddl\n                    FROM pg_roles WHERE rolname = current_user\n                "
                        )
                    )
                )
                .mappings()
                .one()
            )
            if role["rolname"] != "asm_runtime" or any(
                role[key] for key in ("rolsuper", "rolbypassrls", "app_ddl", "platform_ddl")
            ):
                raise RuntimeError("Unsafe runtime database role")
            version = (
                await connection.execute(text("SELECT version_num FROM platform.alembic_version"))
            ).scalar_one()
            extension = (
                await connection.execute(
                    text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
                )
            ).scalar_one()
            server = (await connection.execute(text("SHOW server_version_num"))).scalar_one()
            if (
                version != DATABASE_SCHEMA_REVISION
                or extension != "0.8.6"
                or int(server) // 10000 != 18
            ):
                raise RuntimeError("Database capability/schema mismatch")
