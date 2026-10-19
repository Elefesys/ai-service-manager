"""Deterministic operator-boundary checks; none contact Telegram or send a live message."""

import json
import logging
import sys
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest
from asm.telegram import provisioning as setup

from scripts import provision_telegram_test as setup_cli
from scripts import smoke_telegram_test as smoke_cli

WS = UUID("12345678-1234-4234-8234-123456789001")
BIZ = UUID("12345678-1234-4234-8234-123456789002")
CONN = UUID("12345678-1234-4234-8234-123456789003")
CONV = UUID("12345678-1234-4234-8234-123456789004")
CLIENT = UUID("12345678-1234-4234-8234-123456789005")
MSG = UUID("12345678-1234-4234-8234-123456789006")
PHOTO = UUID("12345678-1234-4234-8234-123456789007")
FILE = UUID("12345678-1234-4234-8234-123456789008")
BOT = "123456"
OWNER = "567890"
EXTERNAL = "opaque:connection-123"
URL = "postgresql+psycopg://asm_migrator:canary-password@postgres:5432/asm_local"
ORIGIN = "https://console.test.invalid"
STORAGE = "https://files.test.invalid"
WEBHOOK = ORIGIN + "/webhooks/telegram"


def request(**changes):
    return replace(
        setup.ProvisionRequest(
            "LOCAL",
            WS,
            BIZ,
            OWNER,
            "Synthetic TEST owner",
            datetime(2026, 9, 1, tzinfo=UTC),
            datetime(2026, 10, 1, tzinfo=UTC),
            EXTERNAL,
        ),
        **changes,
    )


@dataclass
class Observed:
    external_connection_id: str = EXTERNAL
    owner_user_id: str = OWNER
    is_enabled: bool = True
    can_reply: bool = True

    def observation(self, bot_id):
        return {
            "bot_identity": bot_id,
            "external_connection_id": self.external_connection_id,
            "owner_user_id": self.owner_user_id,
            "is_enabled": self.is_enabled,
            "can_reply": self.can_reply,
            "error_code": None,
        }


class Client:
    def __init__(self):
        self.events = []
        self.webhook = ""
        self.bot = BOT
        self.observed = Observed()
        self.updates = [{"business_connection": {"id": EXTERNAL, "user": {"id": int(OWNER)}}}]
        self.webhook_fails = False

    async def get_webhook_info(self):
        self.events.append("webhook_info")
        return {"url": self.webhook, "pending_update_count": 9}

    async def get_me(self):
        self.events.append("me")
        return self.bot

    async def get_updates(self):
        self.events.append("updates")
        return self.updates

    async def get_business_connection(self, external):
        self.events.append("connection")
        assert external == EXTERNAL
        return self.observed

    async def set_webhook(self):
        self.events.append("set_webhook")
        self.webhook = WEBHOOK
        if self.webhook_fails:
            raise RuntimeError("do not expose canary-token")


async def perform(client, req=None, *, fail_commit=False):
    async def commit(req, url, bot, observation):
        assert req.expected_owner_id == OWNER and url == URL and bot == BOT
        assert observation == client.observed.observation(BOT)
        client.events.append("commit")
        if fail_commit:
            raise RuntimeError("transaction rolled back")
        return setup.CommittedBinding(CONN, "CREATED", "CREATED")

    return await setup.provision(client, req or request(), URL, BOT, WEBHOOK, commit=commit)


async def test_approved_binding_commits_before_install_without_discovery_for_explicit_id():
    client = Client()
    result = await perform(client)
    assert client.events == ["webhook_info", "me", "connection", "commit", "set_webhook"]
    assert result["connection_id"] == str(CONN) and result["status"] == "TELEGRAM_SETUP_READY"
    assert "canary" not in json.dumps(result) and EXTERNAL not in json.dumps(result)


async def test_discovery_is_one_bounded_read_and_independent_owner_is_rechecked():
    client = Client()
    client.updates.insert(0, {"business_connection": {"id": "foreign", "user": {"id": 88}}})
    await perform(client, request(external_connection_id=None))
    assert client.events == ["webhook_info", "me", "updates", "connection", "commit", "set_webhook"]
    client = Client()
    client.observed.owner_user_id = "999"
    with pytest.raises(setup.ProvisioningError, match="OWNER_MISMATCH"):
        await perform(client, request(external_connection_id=None))
    assert "commit" not in client.events and "set_webhook" not in client.events


@pytest.mark.parametrize(
    "updates",
    [
        [],
        [{"business_connection": {"id": EXTERNAL, "user": {"id": True}}}],
        [{"business_connection": {"id": EXTERNAL, "user": {"id": OWNER}}}],
        [
            {"business_connection": {"id": name, "user": {"id": int(OWNER)}}}
            for name in (EXTERNAL, "another-connection")
        ],
        [{"business_message": {"business_connection_id": EXTERNAL}}],
        [{}] * 101,
    ],
)
def test_discovery_refuses_missing_ambiguous_and_untrusted_owner_evidence(updates):
    with pytest.raises(setup.ProvisioningError):
        setup.discover_connection(updates, OWNER)


@pytest.mark.parametrize("foreign", ["https://foreign.invalid/webhook", WEBHOOK + "/"])
async def test_foreign_webhook_is_never_modified(foreign):
    client = Client()
    client.webhook = foreign
    with pytest.raises(setup.ProvisioningError, match="FOREIGN_WEBHOOK"):
        await perform(client)
    assert client.events == ["webhook_info"]


async def test_wrong_bot_and_explicit_foreign_connection_cannot_authorize_binding():
    client = Client()
    client.bot = "999"
    with pytest.raises(setup.ProvisioningError, match="BOT_MISMATCH"):
        await perform(client)
    assert client.events == ["webhook_info", "me"]
    client = Client()
    client.observed.external_connection_id = "wrong"
    with pytest.raises(setup.ProvisioningError, match="OWNER_MISMATCH"):
        await perform(client)
    assert "commit" not in client.events


async def test_existing_webhook_never_switches_to_polling_and_explicit_repeat_can_repair():
    client = Client()
    client.webhook = WEBHOOK
    with pytest.raises(setup.ProvisioningError, match="CONNECTION_REQUIRED"):
        await perform(client, request(external_connection_id=None))
    assert "updates" not in client.events
    client.events.clear()
    await perform(client)
    assert "updates" not in client.events and client.events[-1] == "set_webhook"


async def test_no_webhook_after_rollback_and_lost_webhook_result_has_bounded_recovery_error():
    client = Client()
    with pytest.raises(RuntimeError, match="rolled back"):
        await perform(client, fail_commit=True)
    assert "set_webhook" not in client.events
    client = Client()
    client.webhook_fails = True
    with pytest.raises(
        setup.ProvisioningError, match="^TELEGRAM_SETUP_COMMITTED_WEBHOOK_UNCONFIRMED$"
    ):
        await perform(client)
    assert client.events[-2:] == ["commit", "set_webhook"]
    client.webhook_fails = False
    await perform(client)
    assert client.events.count("updates") == 0


async def test_disabled_rights_are_observed_honestly_and_do_not_forge_enablement():
    client = Client()
    client.observed = Observed(is_enabled=False, can_reply=False)
    result = await perform(client)
    assert result["is_enabled"] is False and result["can_reply"] is False


@pytest.mark.parametrize(
    ("environment", "url"),
    [
        ("PRODUCTION", URL),
        ("TEST", URL),
        ("LOCAL", URL.replace("asm_migrator", "asm_runtime")),
        ("LOCAL", URL.replace("asm_local", "other")),
        ("LOCAL", "malformed canary-token"),
    ],
)
def test_migrator_target_refuses_runtime_other_environment_or_database_without_secret(
    environment, url
):
    with pytest.raises(setup.ProvisioningError, match="^TELEGRAM_SETUP_TARGET_INVALID$"):
        setup.migrator_target(environment, url)


@pytest.mark.parametrize("fail_binding", [False, True])
async def test_billing_and_binding_use_one_short_reviewed_capability_transaction(
    monkeypatch, fail_binding
):
    events = []

    class Result:
        def __init__(self, value):
            self.value = value

        def scalar_one(self):
            return self.value

    class Unit:
        async def __aenter__(self):
            events.append("begin")
            return self

        async def __aexit__(self, kind, value, traceback):
            events.append("rollback" if kind else "commit")

        async def execute(self, statement, params=None):
            sql = str(statement)
            if sql == "SELECT current_user":
                return Result("asm_migrator")
            if sql == "SELECT version_num FROM platform.alembic_version":
                # Setup is paired with current0013; native policy remains a separate command.
                return Result("0013")
            assert sql.startswith("SELECT platform.initialize_")
            assert params["workspace"] == WS
            if "initialize_local_messaging_billing" in sql:
                events.append("billing")
                return Result("CREATED")
            events.append("binding")
            assert params["business"] == BIZ and params["owner"] == OWNER
            assert json.loads(params["observation"])["owner_user_id"] == OWNER
            if fail_binding:
                raise RuntimeError("conflict")
            return Result({"code": "CREATED", "connection_id": str(CONN)})

    class Engine:
        def begin(self):
            return Unit()

        async def dispose(self):
            events.append("dispose")

    def engine(url, **kwargs):
        assert url.username == "asm_migrator" and kwargs["hide_parameters"] is True
        return Engine()

    monkeypatch.setattr(setup, "create_async_engine", engine)
    if fail_binding:
        with pytest.raises(RuntimeError, match="conflict"):
            await setup.commit_binding(request(), URL, BOT, Observed().observation(BOT))
    else:
        assert (
            await setup.commit_binding(request(), URL, BOT, Observed().observation(BOT))
        ).connection_id == CONN
    assert events == [
        "begin",
        "billing",
        "binding",
        "rollback" if fail_binding else "commit",
        "dispose",
    ]


@pytest.mark.parametrize("module", [setup_cli, smoke_cli])
@pytest.mark.parametrize("arguments", [[], ["--token", "canary-token-secret"]])
def test_clis_default_to_no_network_and_never_echo_accidental_token(
    monkeypatch, capsys, module, arguments
):
    async def must_not_run(*args):
        pytest.fail("No live opt-in must cause no network")

    monkeypatch.setattr(module, "run", must_not_run)
    monkeypatch.setattr(sys, "argv", ["operator-script", *arguments])
    # The real CLI exits immediately; isolate its process-wide diagnostic settings here.
    for name in ("httpx", "httpcore", "sqlalchemy.engine"):
        logger = logging.getLogger(name)
        for attribute in ("disabled", "propagate", "handlers"):
            monkeypatch.setattr(logger, attribute, getattr(logger, attribute))
    assert module.main() == 1
    output = capsys.readouterr()
    assert "canary-token-secret" not in output.err + output.out
    assert "TELEGRAM_" in output.err


@pytest.mark.parametrize("head", ["0007", "0008", "0009", "0010", "0011", "0012", "unknown"])
async def test_binding_wrong_head_rejected_before_either_initializer(monkeypatch, head):
    from types import SimpleNamespace

    statements = []

    class Unit:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def execute(self, statement, params=None):
            sql = str(statement)
            statements.append(sql)
            assert sql in {
                "SELECT current_user",
                "SELECT version_num FROM platform.alembic_version",
            }
            value = "asm_migrator" if sql == "SELECT current_user" else head
            return SimpleNamespace(scalar_one=lambda: value)

    class Engine:
        def begin(self):
            return Unit()

        async def dispose(self):
            pass

    monkeypatch.setattr(setup, "create_async_engine", lambda *a, **k: Engine())
    with pytest.raises(setup.ProvisioningError, match="TELEGRAM_SETUP_SCHEMA_INVALID"):
        await setup.commit_binding(request(), URL, BOT, Observed().observation(BOT))
    assert statements == ["SELECT current_user", "SELECT version_num FROM platform.alembic_version"]


def smoke_settings(**changes):
    return replace(
        smoke_cli.SmokeSettings(
            ORIGIN,
            STORAGE,
            WS,
            BIZ,
            CONN,
            "test.owner",
            "canary-password",
            "approved-marker",
            CONV,
            CLIENT,
            "approved reply",
            "saved-smoke-key-1",
        ),
        **changes,
    )


class SmokeWire:
    def __init__(self):
        self.calls = []
        self.image_calls = []
        self.marker = "approved-marker"
        self.signed_url = STORAGE + "/private-bucket/object?X-Amz-Signature=canary-signature"
        self.sent = False
        self.drop_send_response = False

    def handle(self, request):
        self.calls.append(request)
        assert request.headers["origin"] == ORIGIN
        path = request.url.path
        cookie = "__Host-asm_session=canary-session; Path=/; Secure; HttpOnly; SameSite=Lax"
        if path.endswith("/auth/bootstrap") or path.endswith("/auth/login"):
            return httpx.Response(
                200, json={"csrf_token": "canary-csrf"}, headers={"Set-Cookie": cookie}
            )
        assert request.headers["cookie"] == "__Host-asm_session=canary-session"
        if path.endswith("/channel-connections"):
            rows = [
                {
                    "connection_id": str(CONN),
                    "business_id": str(BIZ),
                    "provider": "TELEGRAM",
                    "state": "AVAILABLE",
                }
            ]
        elif path.endswith("/conversations"):
            rows = [
                {
                    "conversation_id": str(CONV),
                    "client_id": str(CLIENT),
                    "connection_id": str(CONN),
                    "business_id": str(BIZ),
                }
            ]
        elif path.endswith("/read-grant"):
            assert request.headers["x-csrf-token"] == "canary-csrf"
            assert json.loads(request.content) == {}
            return httpx.Response(
                200, json={"url": self.signed_url, "expires_at": "2026-09-21T00:01:00.000000Z"}
            )
        elif request.method == "POST":
            assert path.endswith("/messages")
            assert request.headers["x-csrf-token"] == "canary-csrf"
            assert request.headers["idempotency-key"] == "saved-smoke-key-1"
            assert json.loads(request.content) == {"text": "approved reply"}
            self.sent = True
            if self.drop_send_response:
                raise httpx.ReadTimeout("canary-url must not be printed")
            return httpx.Response(202, json={"message_id": str(MSG), "outcome": "ACCEPTED"})
        else:
            rows = [
                {
                    "message_id": str(PHOTO),
                    "direction": "INBOUND",
                    "content_type": "TEXT",
                    "text": self.marker,
                    "file": None,
                },
                {
                    "message_id": str(PHOTO),
                    "direction": "INBOUND",
                    "content_type": "IMAGE_REFERENCE",
                    "text": self.marker,
                    "file": {
                        "file_id": str(FILE),
                        "status": "READY",
                        "manifest": {"size_bytes": "5", "mime_type": "image/png"},
                    },
                },
            ]
            if self.sent:
                rows.append(
                    {
                        "message_id": str(MSG),
                        "direction": "OUTBOUND",
                        "delivery": {"status": "SENT"},
                    }
                )
        return httpx.Response(200, json={"items": rows, "next_cursor": None})

    def image(self, request):
        self.image_calls.append(request)
        assert str(request.url) == self.signed_url
        assert "cookie" not in request.headers and "x-csrf-token" not in request.headers
        return httpx.Response(200, content=b"image", headers={"Content-Type": "image/png"})


async def smoke_perform(wire, settings=None, send=True):
    async with (
        httpx.AsyncClient(
            base_url=ORIGIN, headers={"Origin": ORIGIN}, transport=httpx.MockTransport(wire.handle)
        ) as client,
        httpx.AsyncClient(transport=httpx.MockTransport(wire.image)) as image,
    ):
        return await smoke_cli.smoke(settings or smoke_settings(), client, image, send=send)


async def test_smoke_auth_photo_private_get_then_one_exact_approved_intention():
    wire = SmokeWire()
    result = await smoke_perform(wire)
    assert result["status"] == "TELEGRAM_SMOKE_SENT"
    assert (
        len([r for r in wire.calls if r.method == "POST" and r.url.path.endswith("/messages")]) == 1
    )
    assert len(wire.image_calls) == 1
    assert "canary" not in json.dumps(result)


async def test_smoke_read_only_and_candidate_listing_never_send():
    wire = SmokeWire()
    result = await smoke_perform(wire, send=False)
    assert result["status"] == "TELEGRAM_SMOKE_READ_READY" and not wire.sent
    wire = SmokeWire()
    result = await smoke_perform(
        wire, smoke_settings(conversation_id=None, client_id=None), send=False
    )
    assert result["candidates"] == [{"conversation_id": str(CONV), "client_id": str(CLIENT)}]
    assert not wire.sent and not wire.image_calls


@pytest.mark.parametrize("case", ["wrong-client", "wrong-conversation", "missing-text-photo"])
async def test_smoke_refuses_unapproved_target_or_missing_independent_marker(case):
    wire = SmokeWire()
    settings = smoke_settings()
    if case == "wrong-client":
        settings = replace(settings, client_id=WS)
    elif case == "wrong-conversation":
        settings = replace(settings, conversation_id=WS)
    else:
        wire.marker = "not-the-approved-dialog"
    with pytest.raises(smoke_cli.SmokeError):
        await smoke_perform(wire, settings)
    assert not wire.sent


@pytest.mark.parametrize(
    "url",
    [
        "http://storage:9000/bucket/file?secret",
        "https://foreign.invalid/file?secret",
        "https://user@files.test.invalid/file?secret",
    ],
)
async def test_smoke_requires_browser_https_signed_host_and_path_without_rewriting(url):
    wire = SmokeWire()
    wire.signed_url = url
    with pytest.raises(smoke_cli.SmokeError, match="SIGNED_ORIGIN_MISMATCH"):
        await smoke_perform(wire)
    assert not wire.sent and not wire.image_calls


async def test_smoke_lost_owner_post_response_never_blindly_retries():
    wire = SmokeWire()
    wire.drop_send_response = True
    with pytest.raises(httpx.ReadTimeout):
        await smoke_perform(wire)
    assert (
        len([r for r in wire.calls if r.method == "POST" and r.url.path.endswith("/messages")]) == 1
    )


def test_smoke_send_requires_separate_exact_approval_before_network():
    with pytest.raises(smoke_cli.SmokeError, match="APPROVED_DIALOG_REQUIRED"):
        smoke_cli.SmokeSettings.from_environment({"ASM_ENVIRONMENT": "TEST"}, send=True)


@pytest.mark.parametrize(
    "value",
    [
        "http://localhost:8080",
        ORIGIN + "/",
        ORIGIN + "?query",
        "https://user:pass@console.test.invalid",
    ],
)
def test_live_smoke_origin_requires_exact_https_origin(value):
    with pytest.raises(smoke_cli.SmokeError):
        smoke_cli.origin(value)


def native_request(**updates):
    from asm.foundation import NATIVE_CONTEXT_PROFILE_SHA256

    value = {
        "environment": "LOCAL",
        "workspace_id": str(WS),
        "connection_id": str(CONN),
        "operation": "ENABLE",
        "key": "private-command-canary",
        "expected_policy": "OFF_UNUSED",
        "expected_policy_epoch": "0",
        "expected_binding": {
            "business_id": str(BIZ),
            "provider": "CONTROLLED",
            "bot_identity": "CONTROLLED_TEST",
            "external_connection_id": "private-binding-canary",
            "owner_user_id": None,
        },
        "source_profile": {
            "source_tree": "b" * 40,
            "schema_revision": "0013",
            "profile_sha256": NATIVE_CONTEXT_PROFILE_SHA256,
            "drain_confirmed": True,
        },
    }
    value.update(updates)
    return setup.NativePolicyRequest.model_validate(value)


def native_approval():
    return setup.NativeHostApproval(
        commit="a" * 40,
        tree="b" * 40,
        components={role: "c" * 64 for role in setup.NATIVE_COMPONENTS},
    )


def native_receipt(outcome="ACCEPTED"):
    # Synthetic unit RPC return only. Actual authority is tested by appended PG
    # carriers using the real capability, never these toy objects.
    return setup.NativePolicyReceipt.model_validate(
        {
            "outcome": outcome,
            "result": {
                "receipt_id": str(UUID(int=77)),
                "workspace_id": str(WS),
                "connection_id": str(CONN),
                "operation": "ENABLE",
                "change": "ENABLED",
                "previous_policy": "OFF_UNUSED",
                "accepted_policy": "ON",
                "previous_policy_epoch": "0",
                "accepted_policy_epoch": "1",
                "actor_kind": "LOCAL_PROVISIONER",
                "actor_db_role": "asm_migrator",
                "audit_event_id": str(UUID(int=78)),
                "accepted_at": "2026-10-18T12:00:00.000001Z",
            },
        }
    )


@pytest.mark.parametrize(
    "damage",
    [
        "extra",
        "key",
        "epoch_int",
        "epoch_bool",
        "epoch_overflow",
        "epoch_leading_zero",
        "epoch_policy",
        "operation",
        "profile",
        "drain_false",
        "drain_int",
        "owner",
        "provider",
        "binding_extra",
        "uuid",
        "null_epoch",
    ],
)
def test_native_policy_closed_request_never_coerces_private_inputs(damage):
    from pydantic import ValidationError

    value = native_request().model_dump(mode="json")
    if damage == "extra":
        value["trusted"] = True
    elif damage == "key":
        value["key"] = "private key canary"
    elif damage == "epoch_int":
        value["expected_policy_epoch"] = 0
    elif damage == "epoch_bool":
        value["expected_policy_epoch"] = False
    elif damage == "epoch_overflow":
        value["expected_policy_epoch"] = str(2**63)
    elif damage == "epoch_leading_zero":
        value["expected_policy_epoch"] = "00"
    elif damage == "epoch_policy":
        value["expected_policy"] = "ON"
    elif damage == "operation":
        value["operation"] = "DISABLE"
    elif damage == "profile":
        value["source_profile"]["profile_sha256"] = "0" * 64
    elif damage == "drain_false":
        value["source_profile"]["drain_confirmed"] = False
    elif damage == "drain_int":
        value["source_profile"]["drain_confirmed"] = 1
    elif damage == "owner":
        value["expected_binding"]["owner_user_id"] = OWNER
    elif damage == "provider":
        value["expected_binding"]["provider"] = "HTTP"
    elif damage == "binding_extra":
        value["expected_binding"]["trusted"] = True
    elif damage == "uuid":
        value["workspace_id"] = str(WS).upper()
    else:
        value["expected_policy_epoch"] = None
    if damage == "uuid":
        value["workspace_id"] = "12345678-ABCD-4234-8234-123456789001"
    with pytest.raises((ValidationError, setup.ProvisioningError)) as error:
        setup.NativePolicyRequest.model_validate(value)
    assert "private-command-canary" not in str(error.value)
    assert "private-binding-canary" not in repr(native_request())


@pytest.mark.parametrize(
    "mode",
    [
        "accepted",
        "replay_paused",
        "current_error",
        "rpc_error",
        "invalid_result",
        "commit_error",
        "STALE_STATE",
        "IDEMPOTENCY_KEY_CONFLICT",
    ],
)
async def test_native_policy_transaction_boundary_and_read_after_commit(monkeypatch, mode):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from sqlalchemy.exc import DBAPIError

    events = []
    statements = []
    source = Mock(return_value=(SimpleNamespace(), {}))
    monkeypatch.setattr(setup, "native_host_source", source)

    async def catalog(*args):
        events.append("catalog")

    async def binding(*args):
        events.append("binding")
        return setup.NativePolicyCurrent(policy="OFF_UNUSED", policy_epoch="0")

    async def current(*args):
        events.append("current_read")
        assert "commit" in events
        if mode == "current_error":
            raise RuntimeError("private current canary")
        return setup.NativePolicyCurrent(policy="PAUSED", policy_epoch="1")

    monkeypatch.setattr(setup, "native_catalog_profile", catalog)
    monkeypatch.setattr(setup, "native_policy_current", binding)
    monkeypatch.setattr(setup, "read_native_context_policy", current)

    class Unit:
        async def __aenter__(self):
            events.append("begin")
            return self

        async def __aexit__(self, kind, *args):
            events.append("rollback" if kind else "commit")
            if mode == "commit_error" and kind is None:
                raise RuntimeError("private commit canary")

        async def execute(self, statement, params=None):
            sql = str(statement)
            statements.append(sql)
            if sql.startswith("SELECT session_user"):
                return SimpleNamespace(
                    one=lambda: ("asm_migrator", "asm_migrator", "asm_local", "read committed")
                )
            assert sql.startswith("SELECT platform.human_context_policy_command(")
            assert source.call_count == 2 and events[-1] == "binding"
            events.append("capability")
            assert params["key"] == native_request().key and params["epoch"] == 0
            if mode == "rpc_error":
                raise RuntimeError("private body canary")
            if mode in {"STALE_STATE", "IDEMPOTENCY_KEY_CONFLICT"}:
                original = RuntimeError("private SQL parameters")
                original.diag = SimpleNamespace(message_primary=mode)
                raise DBAPIError(sql, params, original)
            value = native_receipt("REPLAY" if mode == "replay_paused" else "ACCEPTED").model_dump(
                mode="json"
            )
            if mode == "invalid_result":
                value["result"]["accepted_policy_epoch"] = 1
            return SimpleNamespace(scalar_one=lambda: value)

    class Engine:
        def begin(self):
            return Unit()

        async def dispose(self):
            events.append("dispose")

    def engine(*args, **kwargs):
        assert kwargs["hide_parameters"] is True
        assert kwargs["isolation_level"] == "READ COMMITTED"
        assert kwargs["connect_args"] == {"connect_timeout": 3}
        return Engine()

    monkeypatch.setattr(setup, "create_async_engine", engine)
    with monkeypatch.context() as no_network:
        no_network.setattr(httpx, "AsyncClient", lambda *a, **k: pytest.fail("No HTTP for policy"))
        if mode in {
            "rpc_error",
            "invalid_result",
            "commit_error",
            "STALE_STATE",
            "IDEMPOTENCY_KEY_CONFLICT",
        }:
            code = mode if mode in {"STALE_STATE", "IDEMPOTENCY_KEY_CONFLICT"} else "UNAVAILABLE"
            with pytest.raises(setup.ProvisioningError, match="^" + code + "$"):
                await setup.commit_native_context_policy(native_request(), URL, native_approval())
            assert "current_read" not in events
            assert events[-2] == ("commit" if mode == "commit_error" else "rollback")
        else:
            result = await setup.commit_native_context_policy(
                native_request(), URL, native_approval()
            )
            assert result.receipt.result.accepted_policy == "ON"
            if mode == "current_error":
                assert result.current is None
            else:
                assert result.current.policy == "PAUSED" and result.current.policy_epoch == "1"
            assert events.index("commit") < events.index("current_read")
    assert events[-1] == "dispose"
    assert not any(
        "initialize_" in sql or "INSERT " in sql or "UPDATE " in sql for sql in statements
    )


@pytest.mark.parametrize("damage", ["source", "tree", "missing_console", "mixed_components"])
async def test_native_policy_source_pairing_refuses_before_engine_or_mutation(monkeypatch, damage):
    from unittest.mock import Mock

    from pydantic import ValidationError

    engine = Mock(side_effect=AssertionError("No engine before paired source"))
    monkeypatch.setattr(setup, "create_async_engine", engine)
    value = native_approval().model_dump()
    if damage == "missing_console":
        del value["components"]["console"]
    if damage == "mixed_components":
        value["components"]["api"] = True
    if damage == "tree":
        value["tree"] = "c" * 40
    with pytest.raises((setup.ProvisioningError, ValidationError)):
        await setup.commit_native_context_policy(
            native_request(), URL, setup.NativeHostApproval.model_validate(value)
        )
    engine.assert_not_called()


async def test_native_cli_preserves_private_acceptance_and_retries_only_current(
    monkeypatch, tmp_path
):
    from unittest.mock import AsyncMock

    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    inputs, receipt = directory / "input.json", directory / "receipt.json"
    inputs.write_text(
        json.dumps(
            {
                "request": native_request().model_dump(mode="json"),
                "approval": native_approval().model_dump(mode="json"),
            }
        )
    )
    inputs.chmod(0o600)
    env = {
        "ASM_NATIVE_POLICY_INPUT": str(inputs),
        "ASM_NATIVE_POLICY_RECEIPT": str(receipt),
        "ASM_ENVIRONMENT": "LOCAL",
        "ASM_MIGRATION_DATABASE_URL": URL,
    }
    command = AsyncMock(return_value=setup.CommittedNativePolicy(native_receipt(), None))
    read = AsyncMock(side_effect=RuntimeError("private failed read"))
    monkeypatch.setattr(setup_cli, "commit_native_context_policy", command)
    monkeypatch.setattr(setup_cli, "read_native_context_policy", read)
    result = await setup_cli.run_native_policy(env, "commit")
    assert result["current_read"] == "RETRY_READ_ONLY" and receipt.stat().st_mode & 0o777 == 0o600
    accepted = receipt.read_bytes()
    with pytest.raises(RuntimeError):
        await setup_cli.run_native_policy(env, "current")
    assert receipt.read_bytes() == accepted
    read.side_effect = None
    read.return_value = setup.NativePolicyCurrent(policy="PAUSED", policy_epoch="1")
    result = await setup_cli.run_native_policy(env, "current")
    assert result["current_policy"] == "PAUSED" and command.await_count == 1
    saved = json.loads(receipt.read_bytes())
    assert saved["receipt"] == native_receipt().model_dump(mode="json")
    assert saved["current"] == {"policy": "PAUSED", "policy_epoch": "1"}
    assert "private-command-canary" not in json.dumps(result)
    assert "private-binding-canary" not in json.dumps(result)


@pytest.mark.parametrize(
    "args", [["--native-policy", "commit", "--live"], ["--native-policy", "check", "--discover"]]
)
def test_native_cli_never_combines_policy_with_telegram_http(monkeypatch, capsys, args):
    async def forbidden(*a):
        pytest.fail("No command or HTTP after ambiguous CLI")

    monkeypatch.setattr(setup_cli, "run_native_policy", forbidden)
    monkeypatch.setattr(setup_cli, "run", forbidden)
    monkeypatch.setattr(sys, "argv", ["operator", *args])
    for name in ("httpx", "httpcore", "sqlalchemy.engine"):
        logger = logging.getLogger(name)
        for attribute in ("disabled", "propagate", "handlers"):
            monkeypatch.setattr(logger, attribute, getattr(logger, attribute))
    assert setup_cli.main() == 1
    assert capsys.readouterr().err.strip() == "INVALID_INPUT"


@pytest.mark.parametrize(
    "case", ["current", "saved", "missing", "foreign_connection", "changed_profile"]
)
async def test_native_historical_source_tree_only_allows_stored_request_replay(case):
    from types import SimpleNamespace

    request = native_request()
    if case != "current":
        data = request.model_dump(mode="json")
        data["source_profile"]["source_tree"] = "d" * 40
        request = setup.NativePolicyRequest.model_validate(data)
    prior = {
        "connection_id": request.connection_id,
        "source_profile": request.source_profile.model_dump(),
    }
    if case == "missing":
        prior = None
    elif case == "foreign_connection":
        prior["connection_id"] = str(UUID(int=99))
    elif case == "changed_profile":
        prior["source_profile"] = dict(prior["source_profile"], source_tree="e" * 40)
    statements = []

    class Connection:
        async def execute(self, statement, params):
            statements.append(str(statement))
            assert str(statement).startswith(
                "SELECT connection_id::text,source_profile FROM platform.human_context_policy_receipts"
            )
            assert params == {"ws": WS, "key": request.key}
            return SimpleNamespace(mappings=lambda: SimpleNamespace(one_or_none=lambda: prior))

    if case in {"current", "saved"}:
        await setup.native_policy_request_source(Connection(), request, native_approval())
    else:
        code = "POLICY_PREREQUISITE_FAILED" if case == "missing" else "IDEMPOTENCY_KEY_CONFLICT"
        with pytest.raises(setup.ProvisioningError, match="^" + code + "$"):
            await setup.native_policy_request_source(Connection(), request, native_approval())
    assert len(statements) == (0 if case == "current" else 1)


@pytest.mark.parametrize(
    "key",
    [
        pytest.param("lowercase.key-09_:k", id="lowercase"),
        pytest.param("UPPERCASE", id="uppercase"),
        pytest.param("mIxEd.Case-09_:K", id="mixed_case"),
        pytest.param(str(WS), id="digit_uuid"),
        pytest.param(".Dot", id="dot_first"),
        pytest.param("_Under", id="underscore_first"),
        pytest.param(":Colon", id="colon_first"),
        pytest.param("-Dash", id="dash_first"),
        pytest.param("a", id="one_lower"),
        pytest.param("Z", id="one_upper"),
        pytest.param("0", id="one_digit"),
        pytest.param(".", id="one_dot"),
        pytest.param("_", id="one_underscore"),
        pytest.param(":", id="one_colon"),
        pytest.param("-", id="one_dash"),
        pytest.param("U" * 128, id="upper_128"),
    ],
)
def test_native_command_key_preserves_exact_python_json_and_host_clone(key):
    request = native_request(key=key)
    payload = request.model_dump(mode="json")
    from_python = setup.NativePolicyRequest.model_validate(payload)
    from_json = setup.NativePolicyRequest.model_validate_json(json.dumps(payload))
    # This is the immutable request clone used by both host paths before await.
    clone = setup.NativePolicyRequest.model_validate_json(request.model_dump_json())
    for candidate in (request, from_python, from_json, clone):
        assert candidate.key == key and candidate.key.encode("ascii") == key.encode("ascii")
        assert json.loads(candidate.model_dump_json())["key"] == key
        assert "key=" not in repr(candidate)


@pytest.mark.parametrize(
    "key",
    [
        pytest.param("", id="empty"),
        pytest.param("U" * 129, id="over_128"),
        pytest.param(" HOST_R2_PRIVATE_KEY_CANARY", id="leading_space"),
        pytest.param("HOST_R2_PRIVATE_KEY_CANARY ", id="trailing_space"),
        pytest.param("HOST_R2_PRIVATE_KEY_CANARY middle", id="embedded_space"),
        pytest.param("HOST_R2_PRIVATE_KEY_CANARY\n", id="terminal_newline"),
        pytest.param("\nHOST_R2_PRIVATE_KEY_CANARY", id="leading_newline"),
        pytest.param("HOST_R2_PRIVATE_KEY_CANARY\nmiddle", id="embedded_newline"),
        pytest.param("HOST_R2_PRIVATE_KEY_CANARY\t", id="tab"),
        pytest.param("HOST_R2_PRIVATE_KEY_CANARY\r", id="carriage_return"),
        pytest.param("HOST_R2_PRIVATE_KEY_CANARY\f", id="form_feed"),
        pytest.param("HOST_R2_PRIVATE_KEY_CANARY\v", id="vertical_tab"),
        pytest.param("HOST_R2_PRIVATE_KEY_CANARYЖ", id="non_ascii"),
        pytest.param("HOST_R2_PRIVATE_KEY_CANARY\u0301", id="combining_mark"),
        pytest.param("HOST_R2_PRIVATE_KEY_CANARY\u00a0", id="nonbreaking_space"),
        pytest.param("HOST_R2_PRIVATE_KEY_CANARY/", id="slash"),
        pytest.param("HOST_R2_PRIVATE_KEY_CANARY\\", id="backslash"),
        pytest.param("HOST_R2_PRIVATE_KEY_CANARY+", id="plus"),
        pytest.param("HOST_R2_PRIVATE_KEY_CANARY@", id="at"),
        pytest.param("HOST_R2_PRIVATE_KEY_CANARY\0", id="nul"),
        pytest.param("HOST_R2_PRIVATE_KEY_CANARY\x7f", id="del"),
        pytest.param(None, id="none"),
        pytest.param(True, id="true"),
        pytest.param(False, id="false"),
        pytest.param(123, id="integer"),
        pytest.param(1.0, id="float"),
        pytest.param(b"HOST_R2_PRIVATE_KEY_CANARY", id="bytes"),
        pytest.param(bytearray(b"HOST_R2_PRIVATE_KEY_CANARY"), id="bytearray"),
        pytest.param(WS, id="uuid_object"),
        pytest.param(["HOST_R2_PRIVATE_KEY_CANARY"], id="list"),
        pytest.param({"key": "HOST_R2_PRIVATE_KEY_CANARY"}, id="object"),
    ],
)
def test_native_command_key_rejects_noncanonical_input_with_bounded_errors(key):
    from pydantic import ValidationError

    payload = native_request().model_dump(mode="json")
    payload["key"] = key
    validators = [lambda: setup.NativePolicyRequest.model_validate(payload)]
    if not isinstance(key, (bytes, bytearray, UUID)):
        validators.append(
            lambda: setup.NativePolicyRequest.model_validate_json(json.dumps(payload))
        )
    for validate in validators:
        with pytest.raises(ValidationError) as caught:
            validate()
        assert [item["loc"] for item in caught.value.errors(include_input=False)] == [("key",)]
        assert "HOST_R2_PRIVATE_KEY_CANARY" not in str(caught.value)
        assert "HOST_R2_PRIVATE_KEY_CANARY" not in repr(caught.value)
        assert len(str(caught.value)) < 512


def test_native_command_key_private_canary_stays_hidden_and_frozen_after_clone():
    from pydantic import ValidationError

    key = "HOST_R2_PRIVATE_KEY_CANARY"
    request = native_request(key=key)
    clone = setup.NativePolicyRequest.model_validate_json(request.model_dump_json())
    for candidate in (request, clone):
        assert candidate.key == key and key not in repr(candidate)
        with pytest.raises(ValidationError) as frozen:
            candidate.key = key
        assert [item["type"] for item in frozen.value.errors(include_input=False)] == [
            "frozen_instance"
        ]
        # The host clones/validates input rather than assigning frozen fields.
        # Check bounded input errors, including a whole-request CAS error.
        payload = candidate.model_dump(mode="json")
        payload["expected_policy_epoch"] = "1"
        with pytest.raises(ValidationError) as caught:
            setup.NativePolicyRequest.model_validate(payload)
        assert key not in str(caught.value) and key not in repr(caught.value)
        assert len(str(caught.value)) < 512
        assert candidate.key == key


def native_command_key_request(monkeypatch):
    original = native_request
    key = "1_HOST_R2_Private-Key:CANARY"

    def keyed_request(**updates):
        return original(**dict(updates, key=key))

    monkeypatch.setattr(sys.modules[__name__], "native_request", keyed_request)
    return key


@pytest.mark.parametrize("mode", ["accepted", "replay_paused", "current_error"])
async def test_native_command_key_survives_existing_host_rpc_and_recovery(monkeypatch, mode):
    # Reuse every existing transaction/RPC/commit/current assertion with the
    # formerly rejected key. These remain unit doubles, never PG authority.
    native_command_key_request(monkeypatch)
    await test_native_policy_transaction_boundary_and_read_after_commit(monkeypatch, mode)


async def test_native_command_key_survives_saved_receipt_and_read_only_retry(monkeypatch, tmp_path):
    key = native_command_key_request(monkeypatch)
    await test_native_cli_preserves_private_acceptance_and_retries_only_current(
        monkeypatch, tmp_path
    )
    saved = json.loads((tmp_path / "private" / "receipt.json").read_bytes())
    assert saved["request"]["key"] == key
    assert saved["current"] == {"policy": "PAUSED", "policy_epoch": "1"}
