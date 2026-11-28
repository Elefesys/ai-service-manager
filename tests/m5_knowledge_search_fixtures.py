"""Synthetic v4 fixtures: actual current-schema capabilities and text-free receipts."""

import asyncio
import hashlib
import json
import os
import subprocess
import tempfile
import unicodedata
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest_asyncio
from asm.ai.agent import SearchAuthorityDecision, SearchContextRead
from asm.ai.context import ContextBuilder
from asm.ai.contracts import SearchGatewayConfig
from asm.ai.database import decoded
from asm.ai.fake import FakeAdapter
from asm.ai.knowledge import SearchProjection
from asm.ai.runtime_contracts import PreparedSearchRun
from asm.foundation import create_worker
from asm.knowledge.embeddings import MODEL, EmbeddingClient
from asm.knowledge.repository import complete_embedding
from asm.messaging.adapter import ControlledAdapter
from asm.messaging.database import MessagingDatabase
from asm.tenancy import AuthenticatedAccount
from m5_configuration_fixtures import configuration_bundle
from m5_knowledge_fixtures import knowledge_run
from sqlalchemy import text
from test_m2_1_postgres import CA, provision
from test_m2_3_db_postgres import BOT, EXTERNAL, OWNER, observed
from test_m3_1_native_context_postgres import policy
from test_m4_agent import config
from test_tenancy_postgres import BA, UA, UB, A, B
from test_tenancy_postgres import db as db
from test_tenancy_postgres import seeded as seeded


def normalized(value):
    return unicodedata.normalize("NFC", value.replace("\r\n", "\n")).strip(" \t\r\n\f\v")


def test_tree():
    # Generic CI receives a validated source manifest bind, not a Git checkout.
    if os.environ.get("ASM_FOUNDATION_EVIDENCE"):
        from scripts.native_context_db_catalog import foundation_store

        store = foundation_store()
        tree = store.binding["identity"]["tree"]
        assert type(tree) is str and len(tree) == 40 and all(c in "0123456789abcdef" for c in tree)
        return tree
    assert os.environ.get("GITHUB_ACTIONS") != "true"

    # Actual working source for the disposable TEST policy carrier; never a
    # substitute for the C0/CI admission artifact used by the historical lane.
    with tempfile.TemporaryDirectory() as directory:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(directory) / "index"))
        for args in (["read-tree", "HEAD"], ["add", "--all", "--", "."]):
            subprocess.run(["git", *args], env=env, check=True, capture_output=True)
        return subprocess.check_output(["git", "write-tree"], env=env, text=True).strip()


def search_run(*, status="RESULTS", text_value="Confirmed preparation source.", published=True):
    old = knowledge_run(published=published)
    raw = old.model_dump(mode="json")
    raw["config"]["prompt_revision"] = "conversation_v4"
    pin = {
        "projection_revision": "business_knowledge_search_v1",
        "business_id": str(old.binding.business_id),
        "release_id": raw["knowledge_pin"]["release_id"],
        "activation_version": raw["knowledge_pin"]["activation_version"],
        "build_id": str(uuid4()) if published else None,
        "profile_id": "polza_openai_text_embedding3small_1536_cosine_v1",
        "preprocessing": "nfc_crlf_ascii_trim_v1",
        "visible_revisions_sha256": "f" * 64,
        "next_transition_at": None,
    }
    base = ContextBuilder().build(old.snapshot, old.binding)
    query = "\n".join(
        m.text for m in base.view.current if m.state == "VISIBLE" and m.text is not None
    )
    projection = {
        "revision": "business_knowledge_search_result_v1",
        "profile_id": pin["profile_id"],
        "query_sha256": hashlib.sha256(normalized(query).encode()).hexdigest(),
        "status": status,
        "reason_code": None
        if status == "RESULTS"
        else "OWNER_LABEL_CONFLICT"
        if status == "CONFLICT"
        else "NO_ACTIVE_BUILD",
        "fragments": [],
        "conflicts": [],
    }
    if status == "RESULTS":
        projection["fragments"] = [
            {
                "source_id": str(uuid4()),
                "revision_id": str(uuid4()),
                "chunk_id": str(uuid4()),
                "ordinal": 0,
                "text": text_value,
                "sha256": hashlib.sha256(text_value.encode()).hexdigest(),
                "title": "Preparation",
                "source_label": "Owner source",
                "author_label": None,
                "service_id": None,
                "category": None,
                "claim_key": None,
                "authority": "OWNER_CONFIRMED_EXPLANATION",
                "rank": 1,
                "score": 0.6,
            }
        ]
    elif status == "CONFLICT":
        projection["conflicts"] = [
            {"claim_key": "preparation", "revision_ids": [str(uuid4()), str(uuid4())]}
        ]
    view = decoded(SearchProjection, projection)
    raw.update(search_pin=pin, search_refs=view.refs().model_dump(mode="json"))
    return decoded(PreparedSearchRun, raw), view


class ControlledSearchAuthority:
    def __init__(self, run, projection, *, allowed):
        self.run, self.projection, self.allowed = run, projection, allowed
        self.stale = False
        self.boundaries, self.reads = [], []

    async def authorize(self, binding, knowledge_pin, search_pin, boundary):
        self.boundaries.append(boundary)
        return SearchAuthorityDecision(
            status="STALE" if self.stale else "ALLOWED" if self.allowed else "DENIED",
            binding=binding,
            knowledge_pin=knowledge_pin,
            search_pin=search_pin,
        )

    async def read_current(self, binding, knowledge_pin, search_pin):
        self.reads.append(binding)
        return SearchContextRead(
            binding=binding,
            knowledge_pin=knowledge_pin,
            active_projection=self.run.active_projection,
            snapshot=self.run.snapshot,
            search_pin=search_pin,
            search_refs=self.projection.refs(),
            search_projection=self.projection,
        )


class WireBytes(httpx.AsyncByteStream):
    def __init__(self, data):
        self.data = data

    async def __aiter__(self):
        yield self.data


def wire_response(value):
    raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
    return httpx.Response(200, headers={"Content-Type": "application/json"}, stream=WireBytes(raw))


def vector(axis=0):
    return [1.0 if i == axis else 0.0 for i in range(1536)]


class ControlledEmbeddings:
    def __init__(self, *, choose=None, hook=None, failure=False):
        self.requests = []
        self.choose = choose or (lambda value: vector())
        self.hook, self.failure = hook, failure
        self.client = EmbeddingClient(httpx.MockTransport(self.handle))

    async def handle(self, request):
        self.requests.append(request)
        body = json.loads(request.content)
        if self.hook is not None:
            await self.hook(request, body)
        if self.failure:
            raise httpx.ReadTimeout("Controlled unknown embedding response")
        return wire_response(
            {
                "id": "gen_123",
                "model": MODEL,
                "provider": "OpenAI",
                "object": "list",
                "data": [
                    {"object": "embedding", "index": i, "embedding": self.choose(value)}
                    for i, value in enumerate(body["input"])
                ],
                "usage": {"prompt_tokens": 1, "total_tokens": 1, "cost": "0.000001"},
            }
        )


@asynccontextmanager
async def owner_unit(h, *, workspace=A, actor=UA):
    async with h.runtime.tenancy.transaction(
        AuthenticatedAccount(actor), workspace, uuid4()
    ) as unit:
        yield unit


async def knowledge_command(h, op, payload, *, business=BA, workspace=A, actor=UA, key=None):
    async with owner_unit(h, workspace=workspace, actor=actor) as u:
        return (
            await u._execute(
                "SELECT platform.knowledge_owner_command(:b,:op,:k,CAST(:p AS jsonb))",
                {"b": business, "op": op, "k": key or str(uuid4()), "p": json.dumps(payload)},
            )
        ).scalar_one()


async def knowledge_state(h, *, business=BA, workspace=A, actor=UA):
    async with owner_unit(h, workspace=workspace, actor=actor) as u:
        return (
            await u._execute("SELECT platform.knowledge_owner_read(:b)", {"b": business})
        ).scalar_one()


async def publication(
    h, sources, embeddings=None, *, business=BA, workspace=A, actor=UA, bundle=None
):
    embeddings = embeddings or ControlledEmbeddings()
    scope = dict(business=business, workspace=workspace, actor=actor)
    revisions = []
    async with owner_unit(h, workspace=workspace, actor=actor) as u:
        draft = await u.configuration_owner_read(business)
        await u.configuration_command(
            business,
            "EDIT",
            str(uuid4()),
            {
                "expected_draft_version": draft["draft_version"],
                "bundle": bundle if bundle is not None else configuration_bundle(),
            },
        )
    for item in sources:
        payload = {
            "schema_version": 1,
            "source_id": None,
            "expected_source_version": "0",
            "title": "Owner knowledge",
            "format": "TEXT",
            "text": item if isinstance(item, str) else item["text"],
            "source_label": "Controlled owner source",
            "author_label": None,
            "service_id": None,
            "category": None,
            "claim_key": None,
            "effective_from": None,
            "effective_until": None,
        }
        if isinstance(item, dict):
            payload.update(item)
        await knowledge_command(h, "KNOWLEDGE_SAVE", payload, **scope)
        state = await knowledge_state(h, **scope)
        source = next(
            s
            for s in state["sources"]
            if not s["head"]["confirmed"]
            and s["head"]["canonical_text"] == normalized(payload["text"])
        )
        await knowledge_command(
            h,
            "KNOWLEDGE_CONFIRM",
            {
                "schema_version": 1,
                "source_id": source["source_id"],
                "expected_source_version": source["source_version"],
                "revision_id": source["head"]["revision_id"],
                "canonical_sha256": source["head"]["canonical_sha256"],
            },
            **scope,
        )
        revisions.append(source["head"]["revision_id"])
    state = await knowledge_state(h, **scope)
    created = await knowledge_command(
        h,
        "KNOWLEDGE_BUILD_CREATE",
        {
            "schema_version": 1,
            "expected_sources_hash": state["sources_hash"],
            "revision_ids": revisions,
        },
        **scope,
    )
    build = UUID(created["result"]["build_id"])
    state = await knowledge_state(h, **scope)
    current = next(b for b in state["builds"] if b["build_id"] == str(build))
    for batch in range((current["chunk_count"] + 7) // 8):
        async with owner_unit(h, workspace=workspace, actor=actor) as u:
            r = (
                await u._execute(
                    "SELECT platform.knowledge_build_reserve(:b,:build,:batch)",
                    {"b": business, "build": build, "batch": batch},
                )
            ).scalar_one()
        assert r["status"] == "RESERVED"
        outcome = await embeddings.client.complete(
            r["wire"], deadline=datetime.fromisoformat(r["deadline"]), wire_sha256=r["wire_sha256"]
        )
        async with h.kernel._transaction() as c:
            recorded = await complete_embedding(c, UUID(r["call_id"]), UUID(r["ticket"]), outcome)
        assert recorded["state"] == "SUCCESS", recorded
        async with owner_unit(h, workspace=workspace, actor=actor) as u:
            applied = (
                await u._execute(
                    "SELECT platform.knowledge_build_apply(:b,:call,:ticket,CAST(:v AS jsonb))",
                    {
                        "b": business,
                        "call": UUID(r["call_id"]),
                        "ticket": UUID(r["ticket"]),
                        "v": json.dumps(outcome["vectors"]),
                    },
                )
            ).scalar_one()
        assert applied["applied"]
    state = await knowledge_state(h, **scope)
    current = next(b for b in state["builds"] if b["build_id"] == str(build))
    assert current["state"] == "READY"
    async with owner_unit(h, workspace=workspace, actor=actor) as u:
        draft = await u.configuration_owner_read(business)
    receipt = await knowledge_command(
        h,
        "KNOWLEDGE_PUBLISH",
        {
            "schema_version": 1,
            "expected_draft_version": draft["draft_version"],
            "expected_activation_version": state["activation_version"],
            "build_id": str(build),
            "expected_build_version": current["build_version"],
        },
        **scope,
    )
    return receipt, await knowledge_state(h, **scope), embeddings


# One atomic statement removes only this fixture's children. RESTRICT witness
# cycles (native revision/conversation/source) are checked after the same SQL
# statement; every trigger, RLS policy and FK stays enabled.
async def cleanup_search(h):
    tables = (
        "platform.ai_deliveries",
        "platform.knowledge_embedding_calls",
        "platform.ai_provider_calls",
        "platform.ai_runs",
        "platform.knowledge_release_builds",
        "platform.knowledge_build_chunks",
        "platform.knowledge_chunks",
        "platform.knowledge_revisions",
        "platform.knowledge_builds",
        "platform.knowledge_sources",
        "platform.business_configuration_receipts",
        "platform.business_configuration_state",
        "platform.business_configuration_releases",
        "platform.turn_guard_receipts",
        "platform.turn_consumer_receipts",
        "platform.escalation_command_receipts",
        "platform.messaging_command_receipts",
        "platform.conversation_control_receipts",
        "platform.human_context_reconciliations",
        "platform.human_context_policy_receipts",
        "platform.file_object_uploads",
        "platform.message_initial_suppressions",
        "platform.message_material_effects",
        "app.audit_events",
        "app.escalations",
        "platform.messaging_jobs",
        "app.conversation_turn_messages",
        "platform.message_material_targets",
        "platform.telegram_provenance",
        "platform.telegram_update_receipts",
        "platform.inbox_events",
        "app.conversation_turns",
        "app.file_objects",
        "app.outbox_events",
        "app.messages",
        "platform.human_context_observations",
        "app.conversations",
        "app.client_identities",
        "app.clients",
        "platform.channel_routes",
        "platform.telegram_connection_state",
        "app.channel_connections",
        "platform.billing_contact_command_receipts",
        "platform.workspace_service_modes",
        "platform.workspace_subscriptions",
        "platform.workspace_billing_accounts",
    )
    sql = (
        "WITH "
        + ",".join(
            f"d{n} AS (DELETE FROM {table} WHERE workspace_id IN(:a,:b) RETURNING 1)"
            for n, table in enumerate(tables)
        )
        + " SELECT "
        + "+".join(f"(SELECT count(*) FROM d{n})" for n in range(len(tables)))
    )
    async with h.migrator.begin() as c:
        await c.execute(text(sql), {"a": A, "b": B})


@pytest_asyncio.fixture
async def search_pg(seeded, tmp_path):
    runtime, migrator = seeded
    h = SimpleNamespace(
        runtime=runtime,
        migrator=migrator,
        kernel=MessagingDatabase(runtime.engine, environment="TEST"),
        adapter=ControlledAdapter(environment="TEST", ledger=tmp_path / "search-effects.jsonl"),
        source_tree=test_tree(),
        schema_revision="0038",
    )
    try:
        async with migrator.begin() as c:
            await c.execute(
                text(
                    "UPDATE platform.workspace_memberships SET role='OWNER' WHERE workspace_id=:w AND user_account_id=:u"
                ),
                {"w": B, "u": UB},
            )
            for ws in (A, B):
                start = datetime.now(UTC) - timedelta(days=1)
                await c.execute(
                    text(
                        "SELECT platform.initialize_local_messaging_billing(:ws,'Knowledge TEST',:s,:e)"
                    ),
                    {"ws": ws, "s": start, "e": start + timedelta(days=30)},
                )
        await provision(migrator)
        async with migrator.begin() as c:
            result = (
                await c.execute(
                    text(
                        "SELECT platform.initialize_telegram_connection(:ws,:b,:bot,:external,:owner,CAST(:o AS jsonb))"
                    ),
                    {
                        "ws": A,
                        "b": BA,
                        "bot": BOT,
                        "external": EXTERNAL,
                        "owner": OWNER,
                        "o": json.dumps(observed()),
                    },
                )
            ).scalar_one()
            h.telegram_connection = UUID(result["connection_id"])
            await c.execute(
                text(
                    "UPDATE platform.telegram_connection_state SET material_enabled=true WHERE workspace_id=:ws AND connection_id=:id"
                ),
                {"ws": A, "id": h.telegram_connection},
            )
        await policy(h, CA)
        await policy(h, h.telegram_connection)
        yield h
    finally:
        await cleanup_search(h)


class FragmentAnswer(FakeAdapter):
    def __init__(self, route, script=("reply",), *, wait=False):
        super().__init__(route, script)
        self.started, self.release = asyncio.Event(), asyncio.Event()
        self.wait = wait
        self.views = []

    async def complete(self, request):
        response = await super().complete(request)
        value = next(
            json.loads(m.text)
            for m in request.request.messages
            if m.role == "context" and json.loads(m.text).get("revision") == "business_knowledge_v2"
        )
        self.views.append(value)
        self.started.set()
        if self.wait:
            await self.release.wait()
        if response.kind == "TOOLS":
            return response
        fragments = value["search"]["fragments"]
        answer = fragments[0]["text"] if fragments else "Ask owner for missing source."
        return response.model_copy(
            update={"output_json": json.dumps({"kind": "reply", "text": answer, "reason": None})}
        )


def application(h, embeddings, *, script=("reply",), wait=False, adapter=None, telegram=None):
    cfg = SearchGatewayConfig.model_validate(
        config(duration_seconds=120).model_dump() | {"prompt_revision": "conversation_v4"}
    )
    fake = FragmentAnswer(cfg.route, script, wait=wait)
    worker = create_worker(
        h.kernel,
        adapter or h.adapter,
        environment="TEST",
        ai_config=cfg,
        model=lambda: fake,
        ai_telegram=telegram,
        ai_embeddings=embeddings.client,
    )
    return worker, fake
