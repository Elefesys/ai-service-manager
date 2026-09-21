"""Short, task-owned transactions and explicit tenant-aware foundation queries."""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from psycopg import AsyncConnection as PsycopgAsyncConnection
from psycopg.pq import TransactionStatus
from sqlalchemy import CursorResult, RowMapping, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from asm.tenancy.types import (
    AuthenticatedAccount,
    ErrorCode,
    MembershipRole,
    Permission,
    TenancyError,
    WorkspaceContext,
    permissions_for,
    require_uuid,
)

if TYPE_CHECKING:
    from asm.files.models import ReadManifest


_active: ContextVar["TenantUnitOfWork | None"] = ContextVar("asm_tenant_unit", default=None)
_SQL_ERRORS = {
    "23503": ErrorCode.INVALID_RELATION,
    "23514": ErrorCode.INVALID_STATE,
    "23502": ErrorCode.INVALID_STATE,
    "23505": ErrorCode.CONFLICT,
    "42501": ErrorCode.ACCESS_DENIED,
    "40001": ErrorCode.RETRY_TRANSACTION,
    "40P01": ErrorCode.RETRY_TRANSACTION,
    "55P03": ErrorCode.RETRY_TRANSACTION,
}


def _redacted_error(error: DBAPIError) -> TenancyError | None:
    code = _SQL_ERRORS.get(getattr(error.orig, "sqlstate", ""))
    return TenancyError(code) if code is not None else None


def current_workspace_context() -> WorkspaceContext:
    unit = _active.get()
    if unit is None:
        raise TenancyError(ErrorCode.CONTEXT_REQUIRED)
    return unit.context


class TenantUnitOfWork:
    """Use only inside TenantDatabase.transaction; do not share across Tasks."""

    def __init__(self, connection: AsyncConnection, context: WorkspaceContext) -> None:
        self._connection = connection
        self._context = context
        self._task = asyncio.current_task()
        self._closed = False
        self._failed = False

    def _assert_active(self) -> None:
        if (
            self._closed
            or self._failed
            or self._task is not asyncio.current_task()
            or _active.get() is not self
            or not self._connection.in_transaction()
        ):
            raise TenancyError(ErrorCode.TRANSACTION_STATE)

    @property
    def context(self) -> WorkspaceContext:
        self._assert_active()
        return self._context

    def require(self, permission: Permission) -> None:
        if permission not in self.context.permissions:
            raise TenancyError(ErrorCode.ACCESS_DENIED)

    async def _execute(self, sql: str, params: dict[str, object]) -> CursorResult[Any]:
        self._assert_active()
        try:
            return await self._connection.execute(text(sql), params)
        except DBAPIError as error:
            self._failed = True
            redacted = _redacted_error(error)
            if redacted is not None:
                raise redacted from None
            raise
        except BaseException:
            self._failed = True
            raise

    async def list_businesses(self) -> tuple[RowMapping, ...]:
        self.require(Permission.READ)
        result = await self._execute(
            "SELECT * FROM app.businesses WHERE workspace_id = :workspace ORDER BY id",
            {"workspace": self.context.workspace_id},
        )
        return tuple(result.mappings().all())

    async def billing_membership_role(self) -> MembershipRole | None:
        """Resolve live authority on this same guarded connection, never from WRITE."""
        result = await self._execute(
            "SELECT platform.resolve_workspace_membership(:actor, :workspace)",
            {"actor": self.context.actor.user_account_id, "workspace": self.context.workspace_id},
        )
        role = result.scalar_one()
        return MembershipRole(role) if role is not None else None

    async def messaging_membership_role(self) -> MembershipRole | None:
        """Live messaging permission admission; frozen tenancy permissions stay unchanged."""
        return await self.billing_membership_role()

    async def _messaging_execute(self, sql: str, params: dict[str, object]) -> Any:
        from asm.messaging.database import physical_transaction, worker_active
        from asm.messaging.errors import Code, MessagingError, database_error

        self._assert_active()
        if worker_active():
            raise MessagingError(Code.TRANSACTION_STATE)
        try:
            await physical_transaction(self._connection)
            return (await self._connection.execute(text(sql), params)).scalar_one()
        except DBAPIError as error:
            self._failed = True
            from asm.billing.errors import BillingUnavailable
            from asm.billing.models import StateReason

            diagnostic = getattr(error.orig, "diag", None)
            reason = getattr(diagnostic, "message_detail", None)
            if (
                getattr(error.orig, "sqlstate", "") == "P2301"
                and getattr(diagnostic, "message_primary", None) == "BILLING_STATE_UNAVAILABLE"
                and reason in ("BILLING_STATE_MISSING", "BILLING_STATE_INVALID", "REVISION_INVALID")
            ):
                raise BillingUnavailable(cast(StateReason, reason)) from None
            bounded = database_error(error)
            if bounded is not None:
                raise bounded from None
            raise
        except BaseException:
            self._failed = True
            raise

    async def messaging_request_text(self, conversation_id: UUID, value: str, key: str) -> Any:
        return await self._messaging_execute(
            "SELECT platform.messaging_request_text(:conversation, :value, :key)",
            {"conversation": conversation_id, "value": value, "key": key},
        )

    async def messaging_prepare_text(self, conversation_id: UUID, value: str, key: str) -> Any:
        return await self._messaging_execute(
            "SELECT platform.messaging_prepare_text(:conversation, :value, :key)",
            {"conversation": conversation_id, "value": value, "key": key},
        )

    async def telegram_owner_observe(
        self,
        conversation_id: UUID,
        generation: int,
        observation_version: int,
        observation: dict[str, object],
    ) -> Any:
        return await self._messaging_execute(
            "SELECT platform.telegram_owner_observe(:conversation,:generation,:version,CAST(:observation AS jsonb))",
            {
                "conversation": conversation_id,
                "generation": generation,
                "version": observation_version,
                "observation": json.dumps(observation, ensure_ascii=False, allow_nan=False),
            },
        )

    async def messaging_lock_billing(self) -> None:
        await self._messaging_execute("SELECT platform.messaging_lock_billing()", {})

    @staticmethod
    def _messaging_page_count(count: int) -> None:
        from asm.messaging.errors import Code, MessagingError

        if type(count) is not int or not 1 <= count <= 101:
            raise MessagingError(Code.INVALID_INPUT)

    async def messaging_connections_page(
        self, count: int, at: datetime | None, anchor: UUID | None
    ) -> Any:
        self._messaging_page_count(count)
        return await self._messaging_execute(
            "SELECT platform.messaging_read_connections(:count,:at,:anchor)",
            {"count": count, "at": at, "anchor": anchor},
        )

    async def messaging_conversations_page(
        self, count: int, at: datetime | None, anchor: UUID | None
    ) -> Any:
        self._messaging_page_count(count)
        return await self._messaging_execute(
            "SELECT platform.messaging_read_conversations(:count,:at,:anchor)",
            {"count": count, "at": at, "anchor": anchor},
        )

    async def messaging_messages_page(
        self, conversation_id: UUID, count: int, at: datetime | None, anchor: UUID | None
    ) -> Any:
        self._messaging_page_count(count)
        return await self._messaging_execute(
            "SELECT platform.messaging_read_messages(:conversation,:count,:at,:anchor)",
            {"conversation": conversation_id, "count": count, "at": at, "anchor": anchor},
        )

    async def messaging_conversations(self, limit: int) -> Any:
        return await self._messaging_execute(
            "SELECT platform.messaging_read_conversations(:limit)", {"limit": limit}
        )

    async def messaging_messages(self, conversation_id: UUID, limit: int) -> Any:
        return await self._messaging_execute(
            "SELECT platform.messaging_read_messages(:conversation, :limit)",
            {"conversation": conversation_id, "limit": limit},
        )

    async def messaging_delivery(self, message_id: UUID) -> Any:
        return await self._messaging_execute(
            "SELECT platform.messaging_read_delivery(:message)", {"message": message_id}
        )

    async def messaging_inbox(self, inbox_id: UUID) -> Any:
        return await self._messaging_execute(
            "SELECT platform.messaging_read_inbox(:inbox)", {"inbox": inbox_id}
        )

    async def file_read_manifest(
        self, conversation_id: UUID, message_id: UUID, file_id: UUID
    ) -> "ReadManifest":
        from asm.files.models import ReadManifest
        from asm.messaging.database import require_uuid as require_file_uuid

        for value in (conversation_id, message_id, file_id):
            require_file_uuid(value)
        return ReadManifest.model_validate(
            await self._messaging_execute(
                "SELECT platform.files_read_manifest(:conversation,:message,:file)",
                {"conversation": conversation_id, "message": message_id, "file": file_id},
            )
        )

    async def billing_snapshot(self) -> RowMapping:
        from asm.billing.queries import SNAPSHOT

        return (
            (await self._execute(SNAPSHOT, {"workspace": self.context.workspace_id}))
            .mappings()
            .one()
        )

    async def billing_contact(self, version: int, name: str, key: str) -> RowMapping:
        from asm.billing.errors import contact_error
        from asm.billing.queries import CONTACT

        self._assert_active()
        try:
            result = await self._connection.execute(
                text(CONTACT), {"version": version, "name": name, "key": key}
            )
            return result.mappings().one()
        except DBAPIError as error:
            self._failed = True
            bounded = contact_error(error)
            if bounded is not None:
                raise bounded from None
            raise
        except BaseException:
            self._failed = True
            raise

    async def billing_audit_anchor(self, at: datetime, event_id: UUID) -> bool:
        from asm.billing.queries import AUDIT_ANCHOR

        return bool(
            (
                await self._execute(
                    AUDIT_ANCHOR, {"workspace": self.context.workspace_id, "at": at, "id": event_id}
                )
            ).scalar_one()
        )

    async def billing_audit_page(
        self, limit: int, at: datetime | None, event_id: UUID | None
    ) -> tuple[RowMapping, ...]:
        from asm.billing.queries import AUDIT_PAGE

        if type(limit) is not int or not 1 <= limit <= 100:
            raise TenancyError(ErrorCode.INVALID_STATE)
        result = await self._execute(
            AUDIT_PAGE,
            {
                "workspace": self.context.workspace_id,
                "at": at,
                "id": event_id,
                "count": limit + 1,
            },
        )
        return tuple(result.mappings().all())

    async def get_business(self, business_id: UUID) -> RowMapping:
        self.require(Permission.READ)
        require_uuid(business_id)
        row = (
            (
                await self._execute(
                    "SELECT * FROM app.businesses WHERE workspace_id = :workspace AND id = :id",
                    {"workspace": self.context.workspace_id, "id": business_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise TenancyError(ErrorCode.NOT_FOUND)
        return row

    async def get_business_member(self, business_id: UUID, member_id: UUID) -> RowMapping:
        self.require(Permission.READ)
        require_uuid(business_id)
        require_uuid(member_id)
        row = (
            (
                await self._execute(
                    "SELECT * FROM app.business_members WHERE workspace_id = :workspace "
                    "AND business_id = :business AND id = :id",
                    {
                        "workspace": self.context.workspace_id,
                        "business": business_id,
                        "id": member_id,
                    },
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise TenancyError(ErrorCode.NOT_FOUND)
        return row

    async def get_location(self, business_id: UUID, location_id: UUID) -> RowMapping:
        self.require(Permission.READ)
        require_uuid(business_id)
        require_uuid(location_id)
        row = (
            (
                await self._execute(
                    "SELECT * FROM app.locations WHERE workspace_id = :workspace "
                    "AND business_id = :business AND id = :id",
                    {
                        "workspace": self.context.workspace_id,
                        "business": business_id,
                        "id": location_id,
                    },
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise TenancyError(ErrorCode.NOT_FOUND)
        return row

    async def rename_business(
        self, business_id: UUID, name: str, expected_version: int
    ) -> RowMapping:
        self.require(Permission.WRITE)
        require_uuid(business_id)
        if (
            not isinstance(name, str)
            or not 1 <= len(name) <= 200
            or name != name.strip()
            or type(expected_version) is not int
            or expected_version < 1
        ):
            raise TenancyError(ErrorCode.INVALID_STATE)
        row = (
            (
                await self._execute(
                    "UPDATE app.businesses SET name = :name, version = version + 1 "
                    "WHERE workspace_id = :workspace AND id = :id AND version = :version RETURNING *",
                    {
                        "workspace": self.context.workspace_id,
                        "id": business_id,
                        "name": name,
                        "version": expected_version,
                    },
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            await self.get_business(business_id)
            raise TenancyError(ErrorCode.STALE_STATE)
        return row


class TenantDatabase:
    def __init__(self, engine: AsyncEngine) -> None:
        if engine.url.drivername != "postgresql+psycopg" or engine.url.username != "asm_runtime":
            raise TenancyError(ErrorCode.CONTEXT_INVALID)
        self._engine = engine

    @asynccontextmanager
    async def transaction(
        self, actor: AuthenticatedAccount, workspace_id: UUID, correlation_id: UUID
    ) -> AsyncIterator[TenantUnitOfWork]:
        from asm.messaging.database import worker_active

        if _active.get() is not None or worker_active():
            raise TenancyError(ErrorCode.TRANSACTION_STATE)
        if type(actor) is not AuthenticatedAccount:
            raise TenancyError(ErrorCode.CONTEXT_INVALID)
        require_uuid(workspace_id)
        require_uuid(correlation_id)
        try:
            async with self._engine.connect() as connection, connection.begin():
                # SQLAlchemy begin/in_transaction track a logical transaction even
                # in AUTOCOMMIT. Inspect this checkout's actual psycopg connection;
                # do not close the borrowed proxy or silently change its mode.
                driver = (await connection.get_raw_connection()).driver_connection
                if not isinstance(driver, PsycopgAsyncConnection) or driver.autocommit:
                    raise TenancyError(ErrorCode.CONTEXT_INVALID)
                identity = (await connection.execute(text("SELECT current_user"))).scalar_one()
                if identity != "asm_runtime":
                    raise TenancyError(ErrorCode.ACCESS_DENIED)
                role = (
                    await connection.execute(
                        text("SELECT platform.resolve_workspace_membership(:actor, :workspace)"),
                        {"actor": actor.user_account_id, "workspace": workspace_id},
                    )
                ).scalar_one()
                if role is None:
                    raise TenancyError(ErrorCode.ACCESS_DENIED)
                context = WorkspaceContext(
                    workspace_id, actor, permissions_for(MembershipRole(role)), correlation_id
                )
                await connection.execute(
                    text("""
                        SELECT set_config('asm.workspace_id', :workspace, true),
                               set_config('asm.actor_id', :actor, true),
                               set_config('asm.actor_kind', 'user_account', true),
                               set_config('asm.correlation_id', :correlation, true),
                               set_config('asm.context_xid', pg_current_xact_id()::text, true)
                    """),
                    {
                        "workspace": str(workspace_id),
                        "actor": str(actor.user_account_id),
                        "correlation": str(correlation_id),
                    },
                )
                binding = (
                    (
                        await connection.execute(
                            text("""
                                SELECT app.current_workspace_id() AS workspace_id,
                                       pg_current_xact_id_if_assigned()::text AS xid,
                                       NULLIF(current_setting('asm.context_xid', true), '')
                                           AS context_xid
                            """)
                        )
                    )
                    .mappings()
                    .one()
                )
                # Verify after the setter in a separate statement on the SAME
                # connection, before constructing/publishing the unit or yielding.
                if (
                    driver.autocommit
                    or driver.info.transaction_status != TransactionStatus.INTRANS
                    or binding["workspace_id"] != context.workspace_id
                    or not binding["xid"]
                    or binding["xid"] != binding["context_xid"]
                ):
                    raise TenancyError(ErrorCode.TRANSACTION_STATE)
                unit = TenantUnitOfWork(connection, context)
                token = _active.set(unit)
                try:
                    yield unit
                    unit._assert_active()
                finally:
                    unit._closed = True
                    _active.reset(token)
        except DBAPIError as error:
            redacted = _redacted_error(error)
            if redacted is not None:
                raise redacted from None
            raise
