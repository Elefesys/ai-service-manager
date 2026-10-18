"""Operator-only LOCAL/TEST binding; no external I/O inside the migrator unit."""

import asyncio
import hashlib
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any, Literal, Protocol, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

from asm.billing.validation import CanonicalUUID, CapabilityKey, LimitDecimal, Timestamp
from asm.foundation import DATABASE_SCHEMA_REVISION, NATIVE_CONTEXT_PROFILE_SHA256
from asm.messaging.models import identifier


class ProvisioningError(RuntimeError):
    """Only bounded diagnostics cross the operator CLI boundary."""


def numeric_id(value: str) -> str:
    if re.fullmatch(r"[1-9][0-9]{0,18}", value) is None or int(value) > 2**63 - 1:
        raise ProvisioningError("TELEGRAM_SETUP_ID_INVALID")
    return value


def migrator_target(environment: str, database_url: str) -> URL:
    try:
        url = make_url(database_url)
        if (
            environment not in {"LOCAL", "TEST"}
            or url.database != {"LOCAL": "asm_local", "TEST": "asm_test"}[environment]
            or url.drivername != "postgresql+psycopg"
            or url.username != "asm_migrator"
            or not url.host
        ):
            raise ValueError
        return url
    except Exception:
        raise ProvisioningError("TELEGRAM_SETUP_TARGET_INVALID") from None


@dataclass(frozen=True)
class ProvisionRequest:
    environment: str
    workspace_id: UUID
    business_id: UUID
    expected_owner_id: str
    contact_display_name: str = field(repr=False)
    effective_from: datetime
    effective_until: datetime
    external_connection_id: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if (
            self.environment not in {"LOCAL", "TEST"}
            or type(self.workspace_id) is not UUID
            or type(self.business_id) is not UUID
            or not self.contact_display_name.strip()
            or len(self.contact_display_name) > 200
            or "\0" in self.contact_display_name
            or self.effective_from.tzinfo is None
            or self.effective_until.tzinfo is None
            or self.effective_from >= self.effective_until
        ):
            raise ProvisioningError("TELEGRAM_SETUP_REQUEST_INVALID")
        numeric_id(self.expected_owner_id)
        if self.external_connection_id is not None:
            identifier(self.external_connection_id)


class ConnectionObservation(Protocol):
    @property
    def external_connection_id(self) -> str: ...

    @property
    def owner_user_id(self) -> str: ...

    @property
    def is_enabled(self) -> bool: ...

    @property
    def can_reply(self) -> bool: ...

    def observation(self, bot_id: str) -> dict[str, object]: ...


class SetupClient(Protocol):
    async def get_me(self) -> str: ...

    async def get_webhook_info(self) -> dict[str, object]: ...

    async def get_updates(self) -> list[dict[str, object]]: ...

    async def get_business_connection(self, external_id: str) -> ConnectionObservation: ...

    async def set_webhook(self) -> None: ...


@dataclass(frozen=True)
class CommittedBinding:
    connection_id: UUID
    billing_outcome: str
    binding_outcome: str


async def commit_binding(
    request: ProvisionRequest, database_url: str, bot_id: str, observation: dict[str, object]
) -> CommittedBinding:
    """The two reviewed typed SQL capabilities commit or roll back together."""
    url = migrator_target(request.environment, database_url)
    engine = create_async_engine(url, hide_parameters=True, connect_args={"connect_timeout": 3})
    try:
        async with asyncio.timeout(10), engine.begin() as connection:
            if (
                await connection.execute(text("SELECT current_user"))
            ).scalar_one() != "asm_migrator":
                raise ProvisioningError("TELEGRAM_SETUP_TARGET_INVALID")
            if (
                await connection.execute(text("SELECT version_num FROM platform.alembic_version"))
            ).scalar_one() != DATABASE_SCHEMA_REVISION:
                raise ProvisioningError("TELEGRAM_SETUP_SCHEMA_INVALID")
            billing = (
                await connection.execute(
                    text(
                        "SELECT platform.initialize_local_messaging_billing("
                        ":workspace,:contact,:effective_from,:effective_until)"
                    ),
                    {
                        "workspace": request.workspace_id,
                        "contact": request.contact_display_name,
                        "effective_from": request.effective_from,
                        "effective_until": request.effective_until,
                    },
                )
            ).scalar_one()
            binding = (
                await connection.execute(
                    text(
                        "SELECT platform.initialize_telegram_connection("
                        ":workspace,:business,:bot,:external,:owner,CAST(:observation AS jsonb))"
                    ),
                    {
                        "workspace": request.workspace_id,
                        "business": request.business_id,
                        "bot": bot_id,
                        "external": observation["external_connection_id"],
                        "owner": request.expected_owner_id,
                        "observation": json.dumps(observation),
                    },
                )
            ).scalar_one()
            if (
                billing not in {"CREATED", "NOOP"}
                or not isinstance(binding, dict)
                or binding.get("code") not in {"CREATED", "NOOP"}
            ):
                raise ProvisioningError("TELEGRAM_SETUP_COMMIT_INVALID")
            result = CommittedBinding(
                UUID(str(binding["connection_id"])), billing, str(binding["code"])
            )
        return result  # setWebhook may run only after this context has committed.
    finally:
        await engine.dispose()


def discover_connection(updates: list[dict[str, object]], expected_owner_id: str) -> str:
    """Only independently approved Owner lifecycle updates may suggest a candidate."""
    candidates: set[str] = set()
    if len(updates) > 100:
        raise ProvisioningError("TELEGRAM_SETUP_DISCOVERY_INVALID")
    for update in updates:
        value = update.get("business_connection")
        if not isinstance(value, dict):
            continue
        owner = value.get("user")
        if not isinstance(owner, dict) or type(owner.get("id")) is not int:
            continue
        if str(owner["id"]) != expected_owner_id:
            continue
        candidate = value.get("id")
        if isinstance(candidate, str):
            candidates.add(identifier(candidate))
    if len(candidates) != 1:
        raise ProvisioningError("TELEGRAM_SETUP_DISCOVERY_UNRESOLVED")
    return candidates.pop()


async def inspect_connection(
    client: SetupClient,
    request: ProvisionRequest,
    expected_bot_id: str,
    webhook_url: str,
) -> tuple[str, ConnectionObservation]:
    """Read-only discovery; getUpdates occurs once and only without an installed webhook."""
    numeric_id(expected_bot_id)
    async with asyncio.timeout(20):
        webhook = await client.get_webhook_info()
        installed_url = webhook.get("url")
        if not isinstance(installed_url, str) or installed_url not in {"", webhook_url}:
            raise ProvisioningError("TELEGRAM_SETUP_FOREIGN_WEBHOOK")
        bot_id = await client.get_me()
        if bot_id != expected_bot_id:
            raise ProvisioningError("TELEGRAM_SETUP_BOT_MISMATCH")
        external = request.external_connection_id
        if external is None:
            if installed_url:
                raise ProvisioningError("TELEGRAM_SETUP_CONNECTION_REQUIRED")
            external = discover_connection(await client.get_updates(), request.expected_owner_id)
        observed = await client.get_business_connection(external)
        if (
            observed.external_connection_id != external
            or observed.owner_user_id != request.expected_owner_id
            or type(observed.is_enabled) is not bool
            or type(observed.can_reply) is not bool
        ):
            raise ProvisioningError("TELEGRAM_SETUP_OWNER_MISMATCH")
        return bot_id, observed


async def provision(
    client: SetupClient,
    request: ProvisionRequest,
    database_url: str,
    expected_bot_id: str,
    webhook_url: str,
    *,
    commit: Callable[
        [ProvisionRequest, str, str, dict[str, object]], Awaitable[CommittedBinding]
    ] = commit_binding,
) -> dict[str, object]:
    """Discovery never acknowledges updates; retry repairs setWebhook after commit."""
    migrator_target(request.environment, database_url)
    async with asyncio.timeout(40):
        bot_id, observed = await inspect_connection(client, request, expected_bot_id, webhook_url)
        saved = await commit(request, database_url, bot_id, observed.observation(bot_id))
        try:
            await client.set_webhook()
        except Exception:
            raise ProvisioningError("TELEGRAM_SETUP_COMMITTED_WEBHOOK_UNCONFIRMED") from None
        return {
            "status": "TELEGRAM_SETUP_READY",
            "workspace_id": str(request.workspace_id),
            "business_id": str(request.business_id),
            "connection_id": str(saved.connection_id),
            "billing_outcome": saved.billing_outcome,
            "binding_outcome": saved.binding_outcome,
            "is_enabled": observed.is_enabled,
            "can_reply": observed.can_reply,
        }


# These are source capabilities, not a claim to have observed running binaries.
# C0 approves the complete immutable checkout and each computed component digest;
# the operator separately attests that old processes have actually been drained.
NATIVE_COMPONENTS = {
    "api": (
        "backend/src/asm/foundation.py",
        "backend/src/asm/conversations/native_context.py",
        "backend/src/asm/conversations/native_context_http.py",
        "contracts/openapi.json",
    ),
    "worker": (
        "backend/src/asm/foundation.py",
        "backend/src/asm/messaging/database.py",
        "backend/src/asm/messaging/worker.py",
        "backend/src/asm/conversations/guards.py",
        "backend/src/asm/conversations/turns.py",
    ),
    "scheduler": (
        "backend/src/asm/foundation.py",
        "backend/src/asm/messaging/database.py",
        "backend/src/asm/messaging/worker.py",
    ),
    "console": (
        "frontend/src/HumanContextPanel.tsx",
        "frontend/src/human-context-api.ts",
        "frontend/src/ConversationControl.tsx",
        "frontend/src/conversation-control-api.ts",
        "frontend/src/EscalationsPanel.tsx",
        "frontend/src/escalation-api.ts",
        "frontend/src/billing-api.ts",
        "contracts/openapi.json",
    ),
}


class NativeOperatorModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)


class NativePolicyBinding(NativeOperatorModel):
    business_id: CanonicalUUID
    provider: Literal["CONTROLLED", "TELEGRAM"]
    bot_identity: str = Field(repr=False)
    external_connection_id: str = Field(repr=False)
    owner_user_id: str | None = Field(repr=False)

    @model_validator(mode="after")
    def closed_binding(self) -> Self:
        identifier(self.external_connection_id)
        identifier(self.bot_identity)
        if len(self.bot_identity) > 128 or len(self.bot_identity.encode()) > 512:
            raise ValueError("Invalid binding")
        if self.provider == "TELEGRAM":
            numeric_id(self.bot_identity)
            if self.owner_user_id is None:
                raise ValueError("Missing owner")
            numeric_id(self.owner_user_id)
        elif self.owner_user_id is not None:
            raise ValueError("Unexpected owner")
        return self


class NativeSourceProfile(NativeOperatorModel):
    source_tree: str = Field(pattern=r"^[0-9a-f]{40}$", repr=False)
    schema_revision: Literal["0013"]
    profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)
    drain_confirmed: Literal[True]

    @field_validator("drain_confirmed", mode="before")
    @classmethod
    def explicit_drain(cls, value: object) -> object:
        if value is not True:
            raise ValueError("Explicit drain attestation required")
        return value

    @field_validator("profile_sha256")
    @classmethod
    def accepted_profile(cls, value: str) -> str:
        if value != NATIVE_CONTEXT_PROFILE_SHA256:
            raise ValueError("Unpaired native profile")
        return value


class NativeHostApproval(NativeOperatorModel):
    commit: str = Field(pattern=r"^[0-9a-f]{40}$", repr=False)
    tree: str = Field(pattern=r"^[0-9a-f]{40}$", repr=False)
    components: dict[str, str] = Field(repr=False)

    @field_validator("components")
    @classmethod
    def exact_components(cls, value: dict[str, str]) -> dict[str, str]:
        if set(value) != set(NATIVE_COMPONENTS) or any(
            re.fullmatch(r"[0-9a-f]{64}", digest) is None for digest in value.values()
        ):
            raise ValueError("All four approved component profiles required")
        return value


class NativePolicyRequest(NativeOperatorModel):
    environment: Literal["LOCAL", "TEST"]
    workspace_id: CanonicalUUID
    connection_id: CanonicalUUID
    operation: Literal["ENABLE", "PAUSE"]
    key: CapabilityKey = Field(repr=False)
    expected_policy: Literal["OFF_UNUSED", "ON", "PAUSED"]
    expected_policy_epoch: LimitDecimal
    expected_binding: NativePolicyBinding = Field(repr=False)
    source_profile: NativeSourceProfile = Field(repr=False)

    @model_validator(mode="after")
    def coherent_cas(self) -> Self:
        if (self.expected_policy == "OFF_UNUSED") != (self.expected_policy_epoch == "0"):
            raise ValueError("Invalid policy CAS")
        return self


class NativePolicyResult(NativeOperatorModel):
    receipt_id: CanonicalUUID
    workspace_id: CanonicalUUID
    connection_id: CanonicalUUID
    operation: Literal["ENABLE", "PAUSE"]
    change: Literal["ENABLED", "PAUSED", "UNCHANGED"]
    previous_policy: Literal["OFF_UNUSED", "ON", "PAUSED"]
    accepted_policy: Literal["ON", "PAUSED"]
    previous_policy_epoch: LimitDecimal
    accepted_policy_epoch: LimitDecimal
    actor_kind: Literal["LOCAL_PROVISIONER"]
    actor_db_role: Literal["asm_migrator"]
    audit_event_id: CanonicalUUID
    accepted_at: Timestamp

    @model_validator(mode="after")
    def exact_transition(self) -> Self:
        old, new = int(self.previous_policy_epoch), int(self.accepted_policy_epoch)
        if (self.previous_policy == "OFF_UNUSED") != (old == 0) or new == 0:
            raise ValueError("Invalid policy result")
        expected = (
            ("ON", "UNCHANGED", old)
            if self.operation == "ENABLE" and self.previous_policy == "ON"
            else ("ON", "ENABLED", old + 1)
            if self.operation == "ENABLE"
            else ("PAUSED", "PAUSED", old)
            if self.previous_policy == "ON"
            else ("PAUSED", "UNCHANGED", old)
            if self.previous_policy == "PAUSED"
            else None
        )
        if (self.accepted_policy, self.change, new) != expected:
            raise ValueError("Invalid policy transition")
        return self


class NativePolicyReceipt(NativeOperatorModel):
    outcome: Literal["ACCEPTED", "REPLAY"]
    result: NativePolicyResult


class NativePolicyCurrent(NativeOperatorModel):
    policy: Literal["OFF_UNUSED", "ON", "PAUSED"]
    policy_epoch: LimitDecimal

    @model_validator(mode="after")
    def coherent_epoch(self) -> Self:
        if (self.policy == "OFF_UNUSED") != (self.policy_epoch == "0"):
            raise ValueError("Invalid current policy")
        return self


@dataclass(frozen=True)
class CommittedNativePolicy:
    receipt: NativePolicyReceipt
    current: NativePolicyCurrent | None


def native_host_source(approval: NativeHostApproval) -> tuple[ModuleType, dict[str, Any]]:
    """Actual clean approved Git bytes, then four source-derived component proofs.

    This host-only path intentionally refuses the runtime image (no Git/Console).
    An approval is a C0/operator input, not a trusted=true bypass or automatic
    approval of whatever happens to be checked out.
    """
    root = Path(__file__).resolve().parents[4]
    path = root / "scripts/native_context_db_catalog.py"
    # Check the runner bytes with Git before executing the source verifier.
    import subprocess

    def git(*args: str) -> bytes:
        return subprocess.check_output(
            ["git", "-C", str(root), *args], stderr=subprocess.DEVNULL, timeout=3
        )

    try:
        runner_bytes = path.read_bytes()
        if (
            git("rev-parse", "HEAD").decode().strip() != approval.commit
            or git("rev-parse", "HEAD^{tree}").decode().strip() != approval.tree
            or git("status", "--porcelain=v1", "--untracked-files=all")
            or git("show", "HEAD:scripts/native_context_db_catalog.py") != runner_bytes
        ):
            raise ValueError
        # Execute the exact verified bytes, never an ignored/stale .pyc cache.
        runner = ModuleType("asm_native_operator_catalog")
        runner.__file__ = str(path)
        exec(compile(runner_bytes, str(path), "exec"), vars(runner))
        tree, manifest = runner.require_source(root, approval.commit)
        if tree != approval.tree:
            raise ValueError
        entries = {entry["path"]: entry for entry in manifest}
        for role, paths in NATIVE_COMPONENTS.items():
            if any(name not in entries for name in paths):
                raise ValueError
            material = {
                "role": role,
                "source_tree": tree,
                "schema_revision": "0013",
                "profile_sha256": NATIVE_CONTEXT_PROFILE_SHA256,
                "files": {name: entries[name] for name in paths},
            }
            digest = hashlib.sha256(
                json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            if digest != approval.components[role]:
                raise ValueError
        expected = runner.source_catalog(root)
        if (
            len(expected["functions"]) != 167
            or len(expected["columns"]) != 45
            or sum(map(len, expected["columns"].values())) != 635
        ):
            raise ValueError
        return runner, expected
    except Exception:
        raise ProvisioningError("POLICY_PREREQUISITE_FAILED") from None


async def native_catalog_profile(
    connection: AsyncConnection, runner: ModuleType, expected: dict[str, Any]
) -> str:
    """Independent installed comparison, including the generated verifier body."""
    try:
        for sql in (
            "SET LOCAL search_path=pg_catalog,pg_temp",
            "SET LOCAL timezone='UTC'",
            "SET LOCAL extra_float_digits=3",
            "SET LOCAL statement_timeout='3s'",
            "SET LOCAL lock_timeout='2s'",
        ):
            await connection.execute(text(sql))
        if (
            int((await connection.execute(text("SHOW server_version_num"))).scalar_one()) // 10000
            != 18
        ):
            raise ValueError
        if (
            await connection.execute(text("SELECT version_num FROM platform.alembic_version"))
        ).scalar_one() != "0013":
            raise ValueError
        extra = (
            await connection.execute(
                text(
                    "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname IN ('app','platform') AND (c.relkind NOT IN ('r','i','S') OR c.relpersistence<>'p')"
                )
            )
        ).all()
        if extra:
            raise ValueError
        full, nonfunction = (await connection.execute(text(runner.CATALOG_SQL))).one()
        functions = (await connection.execute(text(runner.FUNCTION_SQL))).mappings().all()
        resolved_rows = (
            (
                await connection.execute(
                    text(
                        "SELECT signature,to_regprocedure(signature)::oid::bigint AS oid "
                        "FROM unnest(CAST(:signatures AS text[])) AS source(signature) ORDER BY signature"
                    ),
                    {"signatures": sorted(expected["functions"])},
                )
            )
            .mappings()
            .all()
        )
        runner.compare_functions(
            expected["functions"], functions, {r["signature"]: r["oid"] for r in resolved_rows}
        )
        digest = runner.compare_snapshot(expected["columns"], full, nonfunction)
        if digest != NATIVE_CONTEXT_PROFILE_SHA256:
            raise ValueError
        roles = (await connection.execute(text(runner.ROLE_SQL))).mappings().all()
        memberships = (
            await connection.execute(
                text(
                    "SELECT roleid,member FROM pg_auth_members WHERE roleid IN "
                    "('asm_runtime'::regrole,'asm_migrator'::regrole) OR member IN "
                    "('asm_runtime'::regrole,'asm_migrator'::regrole)"
                )
            )
        ).all()
        owned = (
            await connection.execute(
                text(
                    "SELECT (SELECT count(*) FROM pg_database WHERE datdba='asm_runtime'::regrole) + "
                    "(SELECT count(*) FROM pg_namespace WHERE nspowner='asm_runtime'::regrole) + "
                    "(SELECT count(*) FROM pg_class WHERE relowner='asm_runtime'::regrole) + "
                    "(SELECT count(*) FROM pg_proc WHERE proowner='asm_runtime'::regrole)"
                )
            )
        ).scalar_one()
        runner.compare_roles(roles, memberships, owned)
        declared = (
            await connection.execute(text("SELECT platform.human_context_schema_profile()"))
        ).scalar_one()
        if (
            declared != {"schema_revision": "0013", "valid": True, "profile_sha256": digest}
            or type(declared["valid"]) is not bool
        ):
            raise ValueError
        return str(digest)
    except Exception:
        raise ProvisioningError("POLICY_PREREQUISITE_FAILED") from None


async def native_policy_identity(connection: AsyncConnection, environment: str) -> None:
    identity = (
        await connection.execute(
            text(
                "SELECT session_user,current_user,current_database(),current_setting('transaction_isolation')"
            )
        )
    ).one()
    if tuple(identity) != (
        "asm_migrator",
        "asm_migrator",
        {"LOCAL": "asm_local", "TEST": "asm_test"}[environment],
        "read committed",
    ):
        raise ProvisioningError("ACCESS_DENIED")


async def native_policy_current(
    connection: AsyncConnection, request: NativePolicyRequest
) -> NativePolicyCurrent:
    row = (
        (
            await connection.execute(
                text(
                    "SELECT c.business_id::text,c.provider,c.bot_identity,c.external_connection_id,"
                    "CASE WHEN c.provider='TELEGRAM' THEN s.owner_user_id END AS owner_user_id,"
                    "c.human_context_policy AS policy,c.human_context_policy_epoch::text AS policy_epoch "
                    "FROM app.channel_connections c LEFT JOIN platform.telegram_connection_state s "
                    "ON (s.workspace_id,s.connection_id)=(c.workspace_id,c.id) "
                    "WHERE c.workspace_id=:ws AND c.id=:connection "
                    "AND (c.provider<>'TELEGRAM' OR (s.bot_identity,s.external_connection_id,s.owner_user_id)="
                    "(c.bot_identity,c.external_connection_id,:owner)) "
                    "AND EXISTS(SELECT 1 FROM platform.channel_routes r "
                    "WHERE (r.workspace_id,r.connection_id,r.provider,r.bot_identity,r.route_key)="
                    "(c.workspace_id,c.id,c.provider,c.bot_identity,c.external_connection_id))"
                ),
                {
                    "ws": UUID(request.workspace_id),
                    "connection": UUID(request.connection_id),
                    "owner": request.expected_binding.owner_user_id,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise ProvisioningError("NOT_FOUND")
    if {
        key: row[key] for key in NativePolicyBinding.model_fields
    } != request.expected_binding.model_dump():
        raise ProvisioningError("NOT_FOUND")
    return NativePolicyCurrent.model_validate(
        {"policy": row["policy"], "policy_epoch": row["policy_epoch"]}
    )


async def native_policy_request_source(
    connection: AsyncConnection, request: NativePolicyRequest, approval: NativeHostApproval
) -> None:
    if request.source_profile.source_tree == approval.tree:
        return
    # Current processes/source are checked against the current C0 approval.
    # A saved request keeps its original tree for fingerprint-exact replay;
    # an old tree can never authorize a fresh command.
    prior = (
        (
            await connection.execute(
                text(
                    "SELECT connection_id::text,source_profile FROM platform.human_context_policy_receipts "
                    "WHERE workspace_id=:ws AND namespace='HUMAN_CONTEXT_POLICY_V1' AND idempotency_key=:key"
                ),
                {"ws": UUID(request.workspace_id), "key": request.key},
            )
        )
        .mappings()
        .one_or_none()
    )
    if prior is None:
        raise ProvisioningError("POLICY_PREREQUISITE_FAILED")
    if (
        prior["connection_id"] != request.connection_id
        or prior["source_profile"] != request.source_profile.model_dump()
    ):
        raise ProvisioningError("IDEMPOTENCY_KEY_CONFLICT")
    # The capability still verifies the full actor/body/binding fingerprint and
    # live relation after its waits, before returning the immutable old result.


async def read_native_context_policy(
    request: NativePolicyRequest, database_url: str, approval: NativeHostApproval
) -> NativePolicyCurrent:
    try:
        request = NativePolicyRequest.model_validate_json(request.model_dump_json())
    except Exception:
        raise ProvisioningError("INVALID_INPUT") from None
    try:
        approval = NativeHostApproval.model_validate_json(approval.model_dump_json())
    except Exception:
        raise ProvisioningError("POLICY_PREREQUISITE_FAILED") from None
    try:
        url = migrator_target(request.environment, database_url)
    except ProvisioningError:
        raise ProvisioningError("ACCESS_DENIED") from None
    engine = None
    try:
        async with asyncio.timeout(3):
            runner, expected = await asyncio.to_thread(native_host_source, approval)
            engine = create_async_engine(
                url,
                hide_parameters=True,
                isolation_level="READ COMMITTED",
                connect_args={"connect_timeout": 3},
                poolclass=NullPool,
            )
            async with engine.begin() as connection:
                await connection.execute(text("SET TRANSACTION READ ONLY"))
                await native_policy_identity(connection, request.environment)
                await native_catalog_profile(connection, runner, expected)
                return await native_policy_current(connection, request)
    finally:
        if engine is not None:
            await engine.dispose()


async def commit_native_context_policy(
    request: NativePolicyRequest, database_url: str, approval: NativeHostApproval
) -> CommittedNativePolicy:
    """Explicit operator command only; never setup, readiness, renewal or HTTP."""
    # Snapshot nested caller-owned mappings before the first await.
    try:
        request = NativePolicyRequest.model_validate_json(request.model_dump_json())
    except Exception:
        raise ProvisioningError("INVALID_INPUT") from None
    try:
        approval = NativeHostApproval.model_validate_json(approval.model_dump_json())
    except Exception:
        raise ProvisioningError("POLICY_PREREQUISITE_FAILED") from None
    try:
        url = migrator_target(request.environment, database_url)
    except ProvisioningError:
        raise ProvisioningError("ACCESS_DENIED") from None
    engine = None
    receipt = None
    try:
        async with asyncio.timeout(10):
            runner, expected = await asyncio.to_thread(native_host_source, approval)
            engine = create_async_engine(
                url,
                hide_parameters=True,
                isolation_level="READ COMMITTED",
                connect_args={"connect_timeout": 3},
                poolclass=NullPool,
            )
            async with engine.begin() as connection:
                await native_policy_identity(connection, request.environment)
                await native_catalog_profile(connection, runner, expected)
                await native_policy_current(
                    connection, request
                )  # actual scoped binding, no CAS/replay gate
                await native_policy_request_source(connection, request, approval)
                # A cancelled/slow source check is read-only and cannot reach RPC.
                await asyncio.to_thread(native_host_source, approval)
                raw = (
                    await connection.execute(
                        text(
                            "SELECT platform.human_context_policy_command(:ws,:connection,:operation,:key,"
                            ":policy,:epoch,CAST(:binding AS jsonb),CAST(:profile AS jsonb))"
                        ),
                        {
                            "ws": UUID(request.workspace_id),
                            "connection": UUID(request.connection_id),
                            "operation": request.operation,
                            "key": request.key,
                            "policy": request.expected_policy,
                            "epoch": int(request.expected_policy_epoch),
                            "binding": request.expected_binding.model_dump_json(),
                            "profile": request.source_profile.model_dump_json(),
                        },
                    )
                ).scalar_one()
                validated = NativePolicyReceipt.model_validate(raw)
                result = validated.result
                if (
                    result.workspace_id,
                    result.connection_id,
                    result.operation,
                    result.previous_policy,
                    result.previous_policy_epoch,
                ) != (
                    request.workspace_id,
                    request.connection_id,
                    request.operation,
                    request.expected_policy,
                    request.expected_policy_epoch,
                ):
                    raise ProvisioningError("INVALID_INPUT")
            receipt = validated  # commit must complete before any accepted result escapes
            current = await read_native_context_policy(request, database_url, approval)
            return CommittedNativePolicy(receipt, current)
    except Exception as error:
        if receipt is not None:
            return CommittedNativePolicy(
                receipt, None
            )  # retry current GET/read only, never a new command
        allowed = {
            "ACCESS_DENIED",
            "NOT_FOUND",
            "INVALID_INPUT",
            "IDEMPOTENCY_KEY_CONFLICT",
            "STALE_STATE",
            "POLICY_PREREQUISITE_FAILED",
            "CONTEXT_POLICY_INACTIVE",
            "POLICY_VERSION_EXHAUSTED",
        }
        if isinstance(error, ProvisioningError) and str(error) in allowed:
            raise
        if isinstance(error, SQLAlchemyError):
            code = getattr(
                getattr(getattr(error, "orig", None), "diag", None), "message_primary", ""
            )
            if code in allowed:
                raise ProvisioningError(code) from None
        raise ProvisioningError("UNAVAILABLE") from None
    finally:
        try:
            if engine is not None:
                await engine.dispose()
        except Exception:
            if receipt is None:
                raise ProvisioningError("UNAVAILABLE") from None
