"""Offline application contract and failure behavior; not PostgreSQL evidence."""

import asyncio
import hashlib
import importlib.util
import itertools
import json
import sqlite3
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from asm.ai.fake import FakeAdapter
from asm.ai.runtime import SyntheticRuntime
from asm.foundation import create_worker
from asm.messaging.errors import Code, MessagingError
from asm.messaging.results import AIJobClaim, AISendPermit
from asm.telegram.client import TelegramClient
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from test_m2_3_transport import config as telegram_config
from test_m2_3_transport import permit
from test_m4_agent import config
from test_m4_runtime_migrations import compile_statements

from scripts import native_context_db_catalog as catalog


def claim():
    return AIJobClaim.model_validate(
        dict(
            inbox_id=None,
            outbox_id=None,
            correlation_id=uuid4(),
            attempt_count=1,
            lease_until=datetime.now(UTC) + timedelta(seconds=30),
            job_id=uuid4(),
            claim_token=uuid4(),
            workspace_id=uuid4(),
            connection_id=uuid4(),
            kind="PROCESS_TURN",
            turn_id=uuid4(),
            turn_revision=2,
            step="AI_GENERATE",
        )
    )


@pytest.mark.parametrize("environment", ["LIVE", "PRODUCTION", "test", ""])
def test_composition_refuses_non_synthetic_environment(environment):
    with pytest.raises(MessagingError):
        SyntheticRuntime(
            SimpleNamespace(),
            config(),
            lambda: FakeAdapter(config().route),
            environment=environment,
        )


@pytest.mark.parametrize(
    "kwargs", [{"ai_config": config()}, {"model": lambda: None}, {"ai_telegram": object()}]
)
def test_composition_requires_complete_explicit_configuration(kwargs):
    with pytest.raises(MessagingError):
        create_worker(SimpleNamespace(), object(), environment="TEST", **kwargs)


async def test_default_off_and_separate_claim_lane():
    kernel = SimpleNamespace(claim_job=AsyncMock(return_value=None))
    worker = create_worker(kernel, object(), environment="TEST")
    assert worker.ai is None
    with pytest.raises(MessagingError):
        await worker.execute(claim())
    with pytest.raises(MessagingError):
        await worker.run_once(ai_only=True)
    kernel.claim_job.assert_not_awaited()
    ai = create_worker(
        kernel,
        object(),
        environment="TEST",
        ai_config=config(),
        model=lambda: FakeAdapter(config().route),
    )
    assert await ai.run_once(ai_only=True) is False
    assert kernel.claim_job.await_args.kwargs == {"ai": True}


async def test_real_http_client_cannot_be_composed_or_send_ai_permit():
    client = TelegramClient(telegram_config())
    try:
        with pytest.raises(MessagingError):
            SyntheticRuntime(
                SimpleNamespace(), config(), lambda: None, environment="TEST", telegram=client
            )
        client._request = AsyncMock(side_effect=AssertionError("network must not be entered"))
        value = AISendPermit.model_validate(permit().model_dump() | {"ai_delivery": True})
        result = await client.send(value)
        assert result.error_code == Code.NOT_ALLOWED
        client._request.assert_not_awaited()
    finally:
        await client.aclose()


async def test_only_exact_injected_mock_transport_is_ai_eligible():
    client = TelegramClient(
        telegram_config(), transport=httpx.MockTransport(lambda r: httpx.Response(500))
    )
    try:
        assert (
            SyntheticRuntime(
                SimpleNamespace(), config(), lambda: None, environment="TEST", telegram=client
            ).telegram
            is client
        )
        with pytest.raises(ValidationError):
            AISendPermit.model_validate(permit().model_dump() | {"ai_delivery": False})
    finally:
        await client.aclose()


@pytest.mark.parametrize("fault", ["factory", "adapter", "timeout", "lost_ack", "cancel"])
async def test_execution_failure_terminalizes_without_second_model_invocation(fault):
    fake = FakeAdapter(config().route)

    def factory():
        if fault == "factory":
            raise RuntimeError("synthetic factory failure")
        return fake

    runtime = SyntheticRuntime(SimpleNamespace(), config(), factory, environment="TEST")
    runtime.stop = AsyncMock()
    errors = {
        "adapter": RuntimeError(),
        "timeout": TimeoutError(),
        "lost_ack": SQLAlchemyError(),
        "cancel": asyncio.CancelledError(),
    }
    runtime.database.execute = AsyncMock(side_effect=errors.get(fault))
    runtime.database.replay = AsyncMock(side_effect=MessagingError(Code.STALE_CLAIM))
    c = claim()
    if fault == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await runtime.execute(c)
    else:
        await runtime.execute(c)
    runtime.stop.assert_awaited_once_with(c)
    assert runtime.database.execute.await_count == (0 if fault == "factory" else 1)
    assert fake.requests == []


@pytest.mark.parametrize("boundary", ["unknown_metering", "pre_call_timeout", "in_call_timeout"])
async def test_real_runtime_gateway_metering_and_expiration_controls(
    boundary, monkeypatch, request
):
    """Real runtime/agent/Gateway/DurableAdapter; only PostgreSQL methods replaced."""
    import asm.ai.runtime as runtime_module
    from test_m4_runtime_database import prepared

    cfg = config(duration_seconds=0.05 if boundary == "pre_call_timeout" else 30)
    run = prepared().model_copy(update={"config": cfg})
    entered = asyncio.Event()
    cancelled = asyncio.Event()
    reservations, completions, timeouts, stages = [], [], [], []
    loop = asyncio.get_running_loop()
    started = loop.time()
    error_info = {"type": "NONE_OBSERVED", "code": "NONE_OBSERVED"}

    def stage(name):
        assert len(stages) < 10
        stages.append({"stage": name, "seconds": round(loop.time() - started, 6)})

    def diagnostics():
        return {
            "boundary": boundary,
            "error": error_info,
            "entry_count": int(entered.is_set()),
            "reservation_count": len(reservations),
            "completion_count": len(completions),
            "cancellation_observed": cancelled.is_set(),
            "timeout_expired": bool(timeouts and timeouts[0].expired()),
            "stages": stages,
        }

    @asynccontextmanager
    async def observed_timeout(seconds):
        # Keep a real, finite asyncio timeout, isolated to this runtime module.
        timeout = asyncio.timeout(seconds)
        timeouts.append(timeout)
        try:
            async with timeout:
                yield
        except BaseException as error:
            error_info.update(
                type=type(error).__name__[:80],
                code=error.code.value
                if isinstance(error, MessagingError)
                else "TIMEOUT"
                if isinstance(error, TimeoutError)
                else "CANCELLED"
                if isinstance(error, asyncio.CancelledError)
                else "OPERATION_FAILED",
            )
            raise

    monkeypatch.setattr(
        runtime_module,
        "asyncio",
        SimpleNamespace(timeout=observed_timeout, CancelledError=asyncio.CancelledError),
    )

    class Observable(FakeAdapter):
        async def complete(self, request):
            assert len(reservations) == 1, diagnostics()
            entered.set()
            stage("adapter_entered")
            if boundary == "in_call_timeout":
                assert len(timeouts) == 1 and not timeouts[0].expired(), diagnostics()
                # Expire only after real DurableAdapter reservation and model entry.
                timeouts[0].reschedule(loop.time())
                stage("deadline_armed")
            try:
                return await super().complete(request)
            except asyncio.CancelledError:
                cancelled.set()
                stage("adapter_cancelled")
                raise

    fake = Observable(cfg.route, ("unknown_cost" if boundary == "unknown_metering" else "timeout",))
    runtime = SyntheticRuntime(SimpleNamespace(), cfg, lambda: fake, environment="TEST")
    runtime.database.replay = AsyncMock(side_effect=MessagingError(Code.STALE_CLAIM))

    async def prepare(*args, **kwargs):
        stage("prepare")
        if boundary == "pre_call_timeout":
            await asyncio.Event().wait()
        return run

    async def reserve(*args):
        assert not entered.is_set()
        reservations.append(args[-1])
        stage("reserved")
        return 1

    async def complete(*args):
        completions.append(args[-1])
        stage("completed")

    async def stop(*args):
        stage("stop")

    runtime.database.prepare = prepare
    runtime.database.reserve = reserve
    runtime.database.complete = complete
    runtime.database._command = AsyncMock()
    runtime.database.commit = AsyncMock(return_value=object())
    runtime.database.messaging.ai_reply_probe = AsyncMock(return_value=None)
    runtime.stop = AsyncMock(side_effect=stop)
    c = claim()
    before = set(asyncio.all_tasks())
    task = asyncio.create_task(runtime.execute(c))
    try:
        await asyncio.wait_for(task, 2)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        stage("finished")
        request.node.user_properties.append(("runtime_control", json.dumps(diagnostics())))
        assert task.done() and set(asyncio.all_tasks()) == before, diagnostics()
    assert len(timeouts) == 1, diagnostics()
    if boundary == "unknown_metering":
        candidate = runtime.database.commit.await_args.args[-1]
        assert candidate.kind == "reply"
        assert len(fake.requests) == len(reservations) == len(completions) == 1
        assert reservations[0].cost_reserved == cfg.limits.call_cost_reservation > 0
        assert completions[0].kind == "OUTPUT"
        assert completions[0].cost.status == "UNKNOWN" and completions[0].cost.amount is None
        assert (
            completions[0].usage.input_tokens is None and completions[0].usage.output_tokens is None
        )
        runtime.stop.assert_not_awaited()
        assert not timeouts[0].expired() and not cancelled.is_set(), diagnostics()
        # The R5 test's no-result oracle contradicts this valid OUTPUT contract.
        assert candidate is not None
    else:
        runtime.database.commit.assert_not_awaited()
        runtime.stop.assert_awaited_once_with(c)
        assert entered.is_set() is (boundary == "in_call_timeout"), diagnostics()
        assert timeouts[0].expired(), diagnostics()
        assert len(fake.requests) == len(reservations) == (1 if entered.is_set() else 0), (
            diagnostics()
        )
        if entered.is_set():
            assert cancelled.is_set(), diagnostics()
            assert fake.requests[0].budget == reservations[0]
            assert reservations[0].calls_used == 1
            assert reservations[0].cost_reserved == cfg.limits.call_cost_reservation > 0
            assert len(completions) == 1 and completions[0].kind == "UNKNOWN"
            assert completions[0].error == "CANCELLED"
            assert completions[0].cost.status == "UNKNOWN" and completions[0].cost.amount is None
            assert completions[0].usage.input_tokens is completions[0].usage.output_tokens is None
        else:
            assert not cancelled.is_set(), diagnostics()
            assert completions == []


@pytest.mark.parametrize("entry", ["direct", "parent", "deadline"])
@pytest.mark.parametrize("cleanup", ["ok", "error", "delay", "repeat_cancel", "completion_delay"])
async def test_real_agent_cancellation_unwinds_worker_and_bounds_bookkeeping(entry, cleanup):
    from asm.messaging.worker import run
    from test_m4_runtime_database import prepared

    entered, stopping = asyncio.Event(), asyncio.Event()
    cfg = config(duration_seconds=0.05 if entry == "deadline" else 30)
    run_data = prepared().model_copy(update={"config": cfg})
    calls, finished = [], []

    class Waiting(FakeAdapter):
        async def complete(self, request):
            calls.append(request)
            entered.set()
            await asyncio.Event().wait()

    c = claim()
    available = True
    ordinary = asyncio.Event()

    async def claimed(*args, ai=False):
        nonlocal available
        if not ai:
            ordinary.set()
            return None
        if available:
            available = False
            return c
        return None

    kernel = SimpleNamespace(claim_job=claimed)
    runtime = SyntheticRuntime(kernel, cfg, lambda: Waiting(cfg.route), environment="TEST")
    runtime.database.replay = AsyncMock(side_effect=MessagingError(Code.STALE_CLAIM))
    runtime.database.prepare = AsyncMock(return_value=run_data)
    runtime.database.reserve = AsyncMock(return_value=1)

    async def complete(*args):
        assert args[-1].kind == "UNKNOWN" and args[-1].error == "CANCELLED"
        if cleanup == "completion_delay":
            try:
                await asyncio.Event().wait()
            finally:
                finished.append("completion_cancelled")

    async def command(claim, operation, **payload):
        if operation == "STOP":
            stopping.set()
            try:
                if cleanup == "error":
                    raise SQLAlchemyError()
                if cleanup in {"delay", "repeat_cancel"}:
                    await asyncio.Event().wait()
            finally:
                finished.append("stop_finished")

    runtime.database.complete = complete
    runtime.database._command = command
    stop = asyncio.Event()
    before = set(asyncio.all_tasks())
    task = asyncio.create_task(
        run("worker", kernel, object(), stop, ai=runtime)
        if entry == "parent"
        else runtime.execute(c)
    )
    try:
        await asyncio.wait_for(entered.wait(), 1)
        if entry == "parent":
            await asyncio.wait_for(ordinary.wait(), 1)
        started = asyncio.get_running_loop().time()
        if entry != "deadline":
            task.cancel()
        if cleanup == "repeat_cancel":
            await asyncio.wait_for(stopping.wait(), 2)
            task.cancel()
        done, pending = await asyncio.wait({task}, timeout=3.5)
        assert done == {task} and not pending
        assert asyncio.get_running_loop().time() - started < 3.5
        if entry == "deadline" and cleanup != "repeat_cancel":
            assert task.result() is None
        else:
            assert task.cancelled()
        assert not stop.is_set() and len(calls) == 1
        assert "stop_finished" in finished
        if cleanup == "completion_delay":
            assert "completion_cancelled" in finished
        assert set(asyncio.all_tasks()) == before
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("direction", ["upgrade", "downgrade"])
def test_successor_ddl_compiles_and_predecessor_bytes_are_immutable(direction):
    spec = importlib.util.spec_from_file_location(
        "delivery15", Path("migrations/versions/0015_ai_delivery.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert (module.revision, module.down_revision) == ("0015", "0014")
    statements = []
    module.op = SimpleNamespace(execute=lambda sql: statements.append(sql))
    getattr(module, direction)()
    compile_statements(statements)
    assert (
        hashlib.sha256(Path("migrations/versions/0014_ai_runtime.py").read_bytes()).hexdigest()
        == "74db20d70ded7ec9bd3fc7baa78af9cbe81136e84651f6525f610615a3907c39"
    )
    assert not any("CASCADE" in sql or "DELETE FROM" in sql for sql in statements)


def test_probe_check_upgrade_downgrade_uses_exact_old_and_causal_new_predicate():
    """Execute emitted portable CHECK expression offline; actual PG is a separate gate."""
    spec = importlib.util.spec_from_file_location(
        "delivery15_probe", Path("migrations/versions/0015_ai_delivery.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    name = "messaging_jobs_telegram_probe_check"
    _, _, old, new = next(row for row in module.CHECKS if row[1] == name)
    assert old in Path("migrations/versions/0007_telegram_api.py").read_text()
    assert new == old.replace(
        "kind='SEND_MANUAL_TEXT'", "kind IN ('SEND_MANUAL_TEXT','SEND_AI_TEXT')"
    )
    for forward in (True, False, True):
        statements = []
        module.op = SimpleNamespace(execute=statements.append)
        module._constraints(forward)
        compile_statements(statements)
        statement = next(sql for sql in statements if f"ADD CONSTRAINT {name}" in sql)
        expression = statement.split(f"ADD CONSTRAINT {name} CHECK(", 1)[1][:-1]
        assert expression == (new if forward else old)
        with sqlite3.connect(":memory:") as db:
            db.execute(
                "CREATE TABLE jobs(kind TEXT NOT NULL,telegram_probe_claim TEXT,"
                "telegram_probe_generation INTEGER,telegram_probe_version INTEGER,"
                f"CONSTRAINT {name} CHECK({expression}))"
            )
            for kind in ("SEND_MANUAL_TEXT", "SEND_AI_TEXT", "SEND_GUARDED_TEXT", "PROCESS_TURN"):
                for present in itertools.product((False, True), repeat=3):
                    fields = ("synthetic", 1, 1)
                    values = (
                        kind,
                        *(v if has else None for v, has in zip(fields, present, strict=True)),
                    )
                    allowed = (
                        not any(present)
                        or all(present)
                        and (kind == "SEND_MANUAL_TEXT" or forward and kind == "SEND_AI_TEXT")
                    )
                    if allowed:
                        db.execute("INSERT INTO jobs VALUES(?,?,?,?)", values)
                    else:
                        with pytest.raises(sqlite3.IntegrityError, match=name):
                            db.execute("INSERT INTO jobs VALUES(?,?,?,?)", values)


def test_current_and_historical_catalogs_are_distinct_and_closed():
    from asm.foundation import NATIVE_PROFILE_BODY_SHA256

    old = catalog.source_catalog(catalog.ROOT, "0013")
    middle = catalog.source_catalog(catalog.ROOT, "0014")
    current = catalog.source_catalog(catalog.ROOT, "0017")
    assert (len(old["functions"]), len(middle["functions"]), len(current["functions"])) == (
        167,
        175,
        194,
    )
    assert (len(old["columns"]), len(middle["columns"]), len(current["columns"])) == (45, 47, 49)
    body = current["functions"]["platform.ai_reply_rights_schema_profile()"]["body"]
    assert hashlib.sha256(body.encode()).hexdigest() == NATIVE_PROFILE_BODY_SHA256
    assert catalog.compare_embedded_profile(current) == {
        "other_functions": 193,
        "tables": 49,
        "result": "PASS",
    }
    assert (
        current["functions"]["platform.human_context_schema_profile()"]
        == old["functions"]["platform.human_context_schema_profile()"]
    )


@pytest.mark.parametrize("damage", [None, "source", "tree", "event", "attempt", "branch", "extra"])
def test_new_carrier_requires_exact_actual_tested_source(tmp_path, monkeypatch, damage):
    import json

    from scripts import m4_runtime_db as carrier

    value = dict(
        base=carrier.BASE,
        base_tree=carrier.BASE_TREE,
        source="1" * 40,
        tree="2" * 40,
        paths=["migrations/versions/0015_ai_delivery.py"],
        run_id="123",
        attempt=1,
        event="pull_request",
        branch=carrier.BRANCH,
        pins={"DB_IMAGE": carrier.DB_IMAGE},
        uv_lock_sha256="3" * 64,
    )
    for name, item in {
        "SOURCE_SHA": value["source"],
        "SOURCE_TREE": value["tree"],
        "RUN_ID": "123",
        "RUN_ATTEMPT": "1",
    }.items():
        monkeypatch.setenv("ASM_M4_" + name, item)
    if damage:
        value[damage] = {
            "source": "4" * 40,
            "tree": "5" * 40,
            "event": "workflow_dispatch",
            "attempt": 2,
            "branch": "c2/m4-3-pg-runtime-run-r4",
            "extra": True,
        }[damage]
    path = tmp_path / "source.json"
    path.write_text(json.dumps(value))
    if damage:
        with pytest.raises(RuntimeError, match="SOURCE_IDENTITY"):
            carrier.source_tree_from_evidence(path)
    else:
        assert carrier.source_tree_from_evidence(path) == "2" * 40


@pytest.mark.parametrize("damage", ["missing", "overlap", "foreign", "deselected"])
def test_three_pg_execution_lanes_reject_incomplete_m4_inventory(damage):
    from test_native_context_db_runner import partition_fixture

    a, n, g, m = partition_fixture()
    assert catalog.validate_partition(a, n, g, m)["disjoint_pg_sets_and_complete_union"]
    if damage == "missing":
        m["nodeids"].pop()
    elif damage == "overlap":
        g["nodeids"].append(m["nodeids"][0])
        g["integration_nodeids"].append(m["nodeids"][0])
    elif damage == "foreign":
        m["nodeids"].append("tests/foreign.py::test_escape")
    else:
        m["deselected"].append(m["nodeids"][0])
    with pytest.raises(catalog.Refusal):
        catalog.validate_partition(a, n, g, m)
