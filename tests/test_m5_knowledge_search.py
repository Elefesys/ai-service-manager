"""Owner DTO limits and finite orchestration through the actual controlled client."""

import asyncio
import hashlib
import json
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from asm.billing.validation import timestamp
from asm.knowledge import service as service_module
from asm.knowledge.embeddings import MODEL, PROFILE, EmbeddingClient
from asm.knowledge.errors import KnowledgeCode, KnowledgeError, database_error
from asm.knowledge.models import ConfirmSource, CreateBuild, SaveSource
from asm.knowledge.service import KnowledgeService
from asm.knowledge.validation import normalize_source, plan_source
from asm.tenancy import MembershipRole
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

WS, BUSINESS, BUILD, RELEASE, SOURCE, REVISION = (UUID(int=n) for n in range(1, 7))
HASH = "a" * 64


def source_body(**changes):
    return {
        "schema_version": 1,
        "source_id": None,
        "expected_source_version": "0",
        "title": "Synthetic preparation",
        "format": "MARKDOWN",
        "text": "Synthetic preparation text.",
        "source_label": "Synthetic owner handbook",
        **changes,
    }


def test_canonical_preview_is_complete_utf8_safe_and_never_truncates():
    assert normalize_source(" \te\u0301\r\ntext\r\n ") == "é\ntext"
    preview = plan_source("🙂" * 512)
    assert preview["issues"] == [] and len(preview["chunks"]) == 4
    assert "".join(chunk["text"] for chunk in preview["chunks"]) == "🙂" * 512
    for number, chunk in enumerate(preview["chunks"]):
        assert chunk["ordinal"] == number and len(chunk["text"].encode()) == 512
        assert chunk["sha256"] == hashlib.sha256(chunk["text"].encode()).hexdigest()
    # The byte source bound alone does not imply <=4 whole-scalar chunks.
    assert len(("€" * 682).encode()) == 2046
    assert plan_source("€" * 682) == {"chunks": [], "issues": ["CHUNK_LIMIT"]}
    assert plan_source("я" * 1025) == {"chunks": [], "issues": ["SOURCE_TOO_LARGE"]}


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": True},
        {"expected_source_version": "01"},
        {"text": "я" * 1025},
        {"text": "\ud800"},
        {"text": "bad\0text"},
        {"claim_key": "claim\n"},
        {"client_id": str(SOURCE)},
        {
            "effective_from": "2026-11-15T00:00:00.000000Z",
            "effective_until": "2026-11-14T00:00:00.000000Z",
        },
    ],
)
def test_closed_source_shape_and_input_limits(changes):
    with pytest.raises(ValidationError):
        SaveSource.model_validate(source_body(**changes))


def test_confirm_uses_only_path_source_and_exact_revision_hash():
    body = {
        "schema_version": 1,
        "expected_source_version": "1",
        "revision_id": str(REVISION),
        "canonical_sha256": HASH,
    }
    assert ConfirmSource.model_validate(body).revision_id == str(REVISION)
    with pytest.raises(ValidationError):
        ConfirmSource.model_validate(body | {"source_id": str(SOURCE)})
    assert SaveSource.model_validate(source_body()).claim_key is None
    with pytest.raises(ValidationError):
        CreateBuild(schema_version=1, expected_sources_hash=HASH, revision_ids=[str(REVISION)] * 2)


def test_embedding_composition_rejects_arbitrary_clients_and_subclasses():
    class OtherClient(EmbeddingClient):
        pass

    for client in (object(), OtherClient()):
        with pytest.raises(ValueError, match="^CONTROLLED_EMBEDDING_CLIENT_REQUIRED$"):
            KnowledgeService(object(), client)


class Bytes(httpx.AsyncByteStream):
    def __init__(self, value):
        self.value = value

    async def __aiter__(self):
        yield self.value


class Harness:
    def __init__(self, monkeypatch, *, chunks=9, enabled=True):
        self.events = []
        self.owner_active = self.completion_active = False
        self.owner = True
        self.posts = self.completed = self.applied = self.reserved = 0
        self.behavior = None
        self.normalized_state = "SUCCESS"
        self.reserve_replay = self.reserve_lost_ack = False
        self.completion_lost_ack = False
        self.receipts = {}
        self.payloads = []
        self.build = {
            "build_id": str(BUILD),
            "build_version": "1",
            "state": "PLANNED",
            "profile_id": PROFILE,
            "manifest_hash": HASH,
            "revision_ids": [str(REVISION)],
            "chunk_count": chunks,
            "calls_reserved": 0,
            "calls_completed": 0,
            "error_code": None,
        }
        self.projection = {
            "schema_version": 1,
            "workspace_id": str(WS),
            "business_id": str(BUSINESS),
            "sources_hash": HASH,
            "activation_version": "1",
            "release_id": str(RELEASE),
            "active_build_id": None,
            "profile_id": PROFILE,
            "sources": [],
            "builds": [self.build],
            "rollback_targets": [],
        }
        self.context = SimpleNamespace(workspace_id=WS)
        self.store = self
        self.service = KnowledgeService(
            self, EmbeddingClient(httpx.MockTransport(self.http)) if enabled else None
        )
        monkeypatch.setattr(service_module, "complete_embedding", self.complete)

    @asynccontextmanager
    async def workspace(self, token, workspace):
        assert token == "session" and workspace == WS and not self.completion_active
        assert not self.owner_active
        self.owner_active = True
        try:
            yield self
        finally:
            self.owner_active = False

    async def billing_membership_role(self):
        return MembershipRole.OWNER if self.owner else MembershipRole.ADMIN

    @asynccontextmanager
    async def transaction(self):
        assert not self.owner_active and not self.completion_active
        self.completion_active = True
        try:
            yield self
        finally:
            self.completion_active = False

    async def knowledge_owner_read(self, business):
        assert self.owner_active and business == BUSINESS
        return deepcopy(self.projection)

    async def knowledge_owner_command(self, business, operation, key, body):
        assert self.owner_active and business == BUSINESS
        self.payloads.append(body)
        if key in self.receipts:
            return deepcopy(self.receipts[key]) | {"outcome": "REPLAY"}
        receipt = {
            "schema_version": 1,
            "outcome": "ACCEPTED",
            "result": {
                "workspace_id": str(WS),
                "business_id": str(BUSINESS),
                "receipt_id": str(UUID(int=100 + len(self.receipts))),
                "operation": operation,
                "source_id": None,
                "source_version": None,
                "revision_id": None,
                "build_id": str(BUILD),
                "build_version": self.build["build_version"],
                "release_id": str(RELEASE),
                "activation_version": "1",
                "recorded_at": timestamp(datetime.now(UTC)),
                "request_hash": HASH,
            },
        }
        self.receipts[key] = deepcopy(receipt)
        self.events.append("create-commit")
        return receipt

    async def knowledge_build_reserve(self, business, build, batch):
        assert self.owner_active and business == BUSINESS and build == BUILD
        assert batch == self.reserved
        self.events.append(f"reserve:{batch}")
        self.reserved += 1
        self.build["state"] = "BUILDING"
        if self.reserve_lost_ack:
            raise SQLAlchemyError("private reservation ACK lost")
        count = min(8, self.build["chunk_count"] - batch * 8)
        wire = json.dumps(
            {
                "model": MODEL,
                "input": ["Synthetic text."] * count,
                "encoding_format": "float",
                "dimensions": 1536,
                "provider": {
                    "only": ["openai"],
                    "allow_fallbacks": False,
                    "require_parameters": True,
                },
            }
        )
        return {
            "status": "REPLAY" if self.reserve_replay else "RESERVED",
            "call_id": str(UUID(int=200 + batch)),
            "ticket": None if self.reserve_replay else str(UUID(int=300 + batch)),
            "wire": None if self.reserve_replay else wire,
            "wire_sha256": hashlib.sha256(wire.encode()).hexdigest(),
            "profile_id": PROFILE,
            "deadline": timestamp(datetime.now(UTC) + timedelta(seconds=10)),
            "reserved_cost": "0.08",
            "currency": "RUB",
        }

    async def http(self, request):
        assert not self.owner_active and not self.completion_active
        self.posts += 1
        self.events.append("http")
        if self.behavior is not None:
            self.behavior()
        inputs = json.loads(request.content)["input"]
        raw = json.dumps(
            {
                "model": MODEL,
                "provider": "OpenAI",
                "data": [
                    {"index": i, "embedding": [1.0] + [0.0] * 1535} for i in range(len(inputs))
                ],
                "usage": {
                    "prompt_tokens": len(inputs),
                    "total_tokens": len(inputs),
                    "cost": "0.000001",
                },
            }
        ).encode()
        return httpx.Response(200, headers={"content-type": "application/json"}, stream=Bytes(raw))

    async def complete(self, connection, call, ticket, outcome):
        assert connection is self and self.completion_active and not self.owner_active
        assert call == UUID(int=199 + self.reserved) and ticket == UUID(int=299 + self.reserved)
        self.completed += 1
        self.events.append("complete:" + outcome["kind"])
        self.last_outcome = outcome
        if self.completion_lost_ack:
            raise SQLAlchemyError("private completion ACK lost")
        state = self.normalized_state if outcome["kind"] == "SUCCESS" else outcome["kind"]
        if state != "SUCCESS":
            self.build["state"] = state
            self.build["error_code"] = (
                "EMBEDDING_UNKNOWN" if state == "UNKNOWN" else "EMBEDDING_ERROR"
            )
        return {"state": state}

    async def knowledge_build_apply(self, business, call, ticket, vectors):
        assert self.owner_active and business == BUSINESS and self.completed == self.reserved
        assert len(vectors) == min(8, self.build["chunk_count"] - self.applied * 8)
        self.applied += 1
        self.events.append("apply")
        self.build.update(
            state="READY" if self.applied == (self.build["chunk_count"] + 7) // 8 else "BUILDING",
            build_version=str(1 + self.applied * 2),
            calls_reserved=self.reserved,
            calls_completed=self.completed,
        )
        return {
            "applied": True,
            "build_id": str(BUILD),
            "build_version": self.build["build_version"],
            "state": self.build["state"],
            "reason_code": None,
        }

    async def create(self, key="build"):
        return await self.service.command(
            "session",
            WS,
            BUSINESS,
            "KNOWLEDGE_BUILD_CREATE",
            key,
            CreateBuild(schema_version=1, expected_sources_hash=HASH, revision_ids=[str(REVISION)]),
        )


async def test_build_is_sequential_outside_transactions_and_receipt_replay_never_reexecutes(
    monkeypatch,
):
    h = Harness(monkeypatch)
    receipt = await h.create()
    assert h.events == [
        "create-commit",
        "reserve:0",
        "http",
        "complete:SUCCESS",
        "apply",
        "reserve:1",
        "http",
        "complete:SUCCESS",
        "apply",
    ]
    assert h.posts == h.reserved == h.completed == h.applied == 2
    assert receipt.result.build_version == "1"  # Immutable creation ACK.
    state = await h.service.state("session", WS, BUSINESS)
    assert state.builds[0].state == "READY" and state.builds[0].build_version == "5"
    assert state.embedding_mode == "CONTROLLED" and state.release_id == str(RELEASE)
    assert (await h.create()).outcome == "REPLAY"
    assert (await h.create("new-key-same-manifest")).outcome == "ACCEPTED"
    assert h.posts == h.reserved == 2


async def test_default_disabled_records_one_error_without_http_and_preserves_active(monkeypatch):
    h = Harness(monkeypatch, enabled=False)
    await h.create()
    assert h.posts == h.applied == 0 and h.completed == h.reserved == 1
    assert h.last_outcome["error_code"] == "DISABLED"
    state = await h.service.state("session", WS, BUSINESS)
    assert state.embedding_mode == "DISABLED" and state.builds[0].state == "ERROR"
    assert (state.release_id, state.activation_version) == (str(RELEASE), "1")
    await h.create("another-key")
    assert h.posts == 0 and h.reserved == 1


async def test_owner_loss_during_http_still_accounts_before_fresh_apply_denial(monkeypatch):
    h = Harness(monkeypatch, chunks=1)
    h.behavior = lambda: setattr(h, "owner", False)
    with pytest.raises(KnowledgeError) as error:
        await h.create()
    assert error.value.code == KnowledgeCode.ACCESS_DENIED
    assert h.posts == h.completed == 1 and h.applied == 0
    assert h.events[-1] == "complete:SUCCESS"


async def test_sql_normalized_error_blocks_successful_wire_vectors(monkeypatch):
    h = Harness(monkeypatch, chunks=1)
    h.normalized_state = "ERROR"
    await h.create()
    assert h.last_outcome["kind"] == "SUCCESS" and h.completed == h.posts == 1
    assert h.applied == 0 and h.build["state"] == "ERROR"


async def test_uncertain_transport_is_durable_unknown_and_same_manifest_never_resends(monkeypatch):
    h = Harness(monkeypatch, chunks=1)

    def failed():
        raise httpx.ReadError("private provider payload")

    h.behavior = failed
    await h.create()
    assert h.last_outcome["kind"] == "UNKNOWN" and h.applied == 0
    await h.create()
    await h.create("new-key")
    assert h.posts == h.completed == h.reserved == 1


async def test_cancelled_wire_records_bounded_unknown_and_reraises(monkeypatch):
    h = Harness(monkeypatch, chunks=1)

    def cancelled():
        raise asyncio.CancelledError

    h.behavior = cancelled
    with pytest.raises(asyncio.CancelledError):
        await h.create()
    assert h.posts == h.completed == 1 and h.applied == 0
    assert h.last_outcome["kind"] == "UNKNOWN" and h.last_outcome["error_code"] == "CANCELLED"


async def test_lost_completion_ack_stops_without_apply_or_another_http_attempt(monkeypatch):
    h = Harness(monkeypatch, chunks=1)
    h.completion_lost_ack = True
    with pytest.raises(KnowledgeError) as error:
        await h.create()
    assert error.value.code == KnowledgeCode.UNAVAILABLE
    await h.create()
    await h.create("new-key")
    assert h.posts == h.reserved == h.completed == 1 and h.applied == 0


@pytest.mark.parametrize("lost_ack", [False, True])
async def test_replayed_or_lost_reservation_does_not_enter_http(monkeypatch, lost_ack):
    h = Harness(monkeypatch, chunks=1)
    h.reserve_lost_ack, h.reserve_replay = lost_ack, not lost_ack
    if lost_ack:
        with pytest.raises(KnowledgeError) as error:
            await h.create()
        assert error.value.code == KnowledgeCode.UNAVAILABLE
    else:
        await h.create()
    await h.create()  # Canonical creation replay does not retry the reservation.
    assert h.posts == h.completed == h.applied == 0 and h.reserved == 1


async def test_route_source_is_injected_server_side_and_foreign_projection_fails_closed(
    monkeypatch,
):
    h = Harness(monkeypatch)
    await h.service.command(
        "session",
        WS,
        BUSINESS,
        "KNOWLEDGE_CONFIRM",
        "confirm",
        ConfirmSource(
            schema_version=1,
            expected_source_version="1",
            revision_id=str(REVISION),
            canonical_sha256=HASH,
        ),
        source=SOURCE,
    )
    assert h.payloads[-1]["source_id"] == str(SOURCE)
    h.projection["business_id"] = str(SOURCE)
    with pytest.raises(KnowledgeError) as error:
        await h.service.state("session", WS, BUSINESS)
    assert error.value.code == KnowledgeCode.UNAVAILABLE


def test_sql_errors_use_only_known_primary_codes_and_never_exception_text():
    class PrivateError(Exception):
        sqlstate = "P2801"
        diag = SimpleNamespace(message_primary="STALE_STATE")

        def __str__(self):
            raise AssertionError("Raw SQL/credentials must never be formatted")

    error = DBAPIError("SELECT secret", {"payload": "private"}, PrivateError())
    assert database_error(error).code == KnowledgeCode.STALE_STATE
    error.orig.diag = SimpleNamespace(message_primary="private SQL password=sentinel")
    assert str(database_error(error)) == "UNAVAILABLE"
