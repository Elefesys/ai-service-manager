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
                return Result("0007")
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
