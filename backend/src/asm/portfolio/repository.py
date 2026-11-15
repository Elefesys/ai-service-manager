"""Closed owner capabilities and separate opaque-ticket accounting transactions."""

import json
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection

from asm.files.models import ImageManifest
from asm.messaging.database import physical_transaction
from asm.portfolio.errors import PortfolioCode, PortfolioError, database_error
from asm.portfolio.models import (
    CommandResponse,
    ConversationProjection,
    EmbeddingReservation,
    Operation,
    PortfolioProjectionState,
    PrivatePreview,
    PrivateVersion,
    VisionReservation,
)
from asm.tenancy import TenantUnitOfWork


def decoded[M: BaseModel](model: type[M], value: Any) -> M:
    return model.model_validate_json(json.dumps(value, ensure_ascii=False, allow_nan=False))


async def private_call(connection: AsyncConnection, sql: str, params: dict[str, object]) -> Any:
    try:
        await physical_transaction(connection)
        return (await connection.execute(text(sql), params)).scalar_one()
    except DBAPIError as error:
        raise database_error(error) from None


class PortfolioRepository:
    def __init__(self, unit: TenantUnitOfWork):
        self.unit = unit

    def scope(self, workspace: UUID | str, business: UUID | str, expected: UUID) -> None:
        if str(workspace) != str(self.unit.context.workspace_id) or str(business) != str(expected):
            raise PortfolioError(PortfolioCode.UNAVAILABLE)

    async def state(self, business: UUID) -> PortfolioProjectionState:
        raw = await self.unit._portfolio_execute(
            "SELECT platform.portfolio_owner_read(:business)", {"business": business}
        )
        value = decoded(PortfolioProjectionState, raw)
        self.scope(value.workspace_id, value.business_id, business)
        return value

    async def conversation(self, business: UUID, conversation: UUID) -> ConversationProjection:
        value = decoded(
            ConversationProjection,
            await self.unit._portfolio_execute(
                "SELECT platform.portfolio_conversation_read(:business,:conversation)",
                {"business": business, "conversation": conversation},
            ),
        )
        self.scope(value.workspace_id, value.business_id, business)
        if value.conversation_id != str(conversation):
            raise PortfolioError(PortfolioCode.UNAVAILABLE)
        return value

    async def command(
        self, business: UUID, operation: Operation, key: str, body: dict[str, Any]
    ) -> CommandResponse:
        value = decoded(
            CommandResponse,
            await self.unit._portfolio_execute(
                "SELECT platform.portfolio_owner_command(:business,:operation,:key,CAST(:body AS jsonb))",
                {
                    "business": business,
                    "operation": operation,
                    "key": key,
                    "body": json.dumps(body, ensure_ascii=False, allow_nan=False),
                },
            ),
        )
        self.scope(value.result.workspace_id, value.result.business_id, business)
        if value.result.operation != operation:
            raise PortfolioError(PortfolioCode.UNAVAILABLE)
        return value

    async def upload_begin(
        self, business: UUID, asset: UUID, version: UUID, upload: UUID
    ) -> PrivateVersion:
        value = decoded(
            PrivateVersion,
            await self.unit._portfolio_execute(
                "SELECT platform.portfolio_upload_begin(:business,:asset,:version,:upload)",
                dict(business=business, asset=asset, version=version, upload=upload),
            ),
        )
        self.version_scope(value, business, asset, version, upload)
        return value

    def version_scope(
        self, value: PrivateVersion, business: UUID, asset: UUID, version: UUID, upload: UUID
    ) -> None:
        self.scope(value.workspace_id, value.business_id, business)
        if (value.asset_id, value.version_id, value.upload_id) != (asset, version, upload):
            raise PortfolioError(PortfolioCode.UNAVAILABLE)

    async def upload_prepare(
        self,
        business: UUID,
        asset: UUID,
        version: UUID,
        upload: UUID,
        ticket: UUID,
        manifest: ImageManifest,
    ) -> PrivateVersion:
        value = decoded(
            PrivateVersion,
            await self.unit._portfolio_execute(
                "SELECT platform.portfolio_upload_prepare(:business,:asset,:version,:upload,:ticket,CAST(:manifest AS jsonb))",
                dict(
                    business=business,
                    asset=asset,
                    version=version,
                    upload=upload,
                    ticket=ticket,
                    manifest=manifest.model_dump_json(),
                ),
            ),
        )
        self.version_scope(value, business, asset, version, upload)
        if (
            value.ticket != ticket
            or value.manifest.decoded() != manifest
            or value.storage_key is None
        ):
            raise PortfolioError(PortfolioCode.UNAVAILABLE)
        return value

    async def recover(
        self, business: UUID, asset: UUID, version: UUID, upload: UUID
    ) -> PrivateVersion:
        value = decoded(
            PrivateVersion,
            await self.unit._portfolio_execute(
                "SELECT platform.portfolio_upload_recover(:business,:asset,:version,:upload)",
                dict(business=business, asset=asset, version=version, upload=upload),
            ),
        )
        self.version_scope(value, business, asset, version, upload)
        if value.operation != "HEAD_GET_ONLY" or value.storage_key is None:
            raise PortfolioError(PortfolioCode.UNAVAILABLE)
        return value

    async def preview(self, business: UUID, asset: UUID, version: UUID) -> PrivatePreview:
        value = decoded(
            PrivatePreview,
            await self.unit._portfolio_execute(
                "SELECT platform.portfolio_preview(:business,:asset,:version)",
                dict(business=business, asset=asset, version=version),
            ),
        )
        self.scope(value.workspace_id, value.business_id, business)
        if (value.asset_id, value.version_id) != (asset, version):
            raise PortfolioError(PortfolioCode.UNAVAILABLE)
        return value

    async def purge(self, business: UUID, asset: UUID, version: UUID) -> PrivateVersion:
        value = decoded(
            PrivateVersion,
            await self.unit._portfolio_execute(
                "SELECT platform.portfolio_purge_begin(:business,:asset,:version)",
                dict(business=business, asset=asset, version=version),
            ),
        )
        self.scope(value.workspace_id, value.business_id, business)
        if (value.asset_id, value.version_id) != (
            asset,
            version,
        ) or value.operation != "OWNER_ACCEPTED_DELETE":
            raise PortfolioError(PortfolioCode.UNAVAILABLE)
        return value

    async def session(self, business: UUID, conversation: UUID | None) -> UUID:
        # Server-owned finite synthetic profile. There is deliberately no HTTP
        # route or request field that can invoke/choose this admission.
        raw = await self.unit._portfolio_execute(
            "SELECT platform.portfolio_session_admit(:business,:conversation,CAST(:body AS jsonb))",
            dict(
                business=business,
                conversation=conversation,
                body=json.dumps(
                    {
                        "profile_id": "SYNTHETIC_VISION_PORTFOLIO_V1",
                        "execution": "CONTROLLED",
                        "eligibility": "EVAL_ONLY",
                        "max_calls": 4,
                        "max_cost": "10",
                        "duration_seconds": 120,
                    }
                ),
            ),
        )
        self.scope(raw["workspace_id"], raw["business_id"], business)
        if raw["conversation_id"] != (str(conversation) if conversation else None):
            raise PortfolioError(PortfolioCode.UNAVAILABLE)
        return UUID(raw["session_id"])

    async def vision_reserve(
        self,
        business: UUID,
        session: UUID | None,
        *,
        asset: UUID | None = None,
        version: UUID | None = None,
        conversation: UUID | None = None,
    ) -> VisionReservation:
        if conversation is not None:
            raw = await self.unit._portfolio_execute(
                "SELECT platform.vision_client_reserve(:business,:conversation,:session)",
                dict(business=business, conversation=conversation, session=session),
            )
        else:
            raw = await self.unit._portfolio_execute(
                "SELECT platform.vision_owner_reserve(:business,:asset,:version,:session)",
                dict(business=business, asset=asset, version=version, session=session),
            )
        value = decoded(VisionReservation, raw)
        if value.status == "RESERVED":
            self.scope(value.workspace_id or "", value.business_id or "", business)
            if (value.source_kind == "CLIENT_REFERENCE") != (conversation is not None):
                raise PortfolioError(PortfolioCode.UNAVAILABLE)
            if conversation is not None and (
                value.media_pin is None or value.media_pin.conversation_id != conversation
            ):
                raise PortfolioError(PortfolioCode.UNAVAILABLE)
            if conversation is None and (value.asset_id, value.asset_version_id) != (
                asset,
                version,
            ):
                raise PortfolioError(PortfolioCode.UNAVAILABLE)
        return value

    async def vision_authorize(self, business: UUID, analysis: UUID, ticket: UUID) -> None:
        await self.unit._portfolio_execute(
            "SELECT platform.vision_authorize(:business,:analysis,:ticket)",
            dict(business=business, analysis=analysis, ticket=ticket),
        )

    async def vision_apply(self, business: UUID, analysis: UUID, ticket: UUID) -> Any:
        return await self.unit._portfolio_execute(
            "SELECT platform.vision_apply(:business,:analysis,:ticket)",
            dict(business=business, analysis=analysis, ticket=ticket),
        )

    async def build_reserve(
        self, business: UUID, build: UUID, session: UUID
    ) -> EmbeddingReservation:
        return decoded(
            EmbeddingReservation,
            await self.unit._portfolio_execute(
                "SELECT platform.portfolio_build_reserve(:business,:build,:session)",
                dict(business=business, build=build, session=session),
            ),
        )

    async def build_apply(
        self, business: UUID, call: UUID, ticket: UUID, vectors: list[list[float]]
    ) -> Any:
        return await self.unit._portfolio_execute(
            "SELECT platform.portfolio_build_apply(:business,:call,:ticket,CAST(:vectors AS jsonb))",
            dict(
                business=business,
                call=call,
                ticket=ticket,
                vectors=json.dumps(vectors, allow_nan=False),
            ),
        )

    async def lookup_reserve(
        self, business: UUID, analysis: UUID, session: UUID | None
    ) -> EmbeddingReservation:
        return decoded(
            EmbeddingReservation,
            await self.unit._portfolio_execute(
                "SELECT platform.portfolio_owner_lookup_reserve(:business,:analysis,:session)",
                dict(business=business, analysis=analysis, session=session),
            ),
        )

    async def lookup_apply(
        self, business: UUID, call: UUID, ticket: UUID, vectors: list[list[float]]
    ) -> Any:
        return await self.unit._portfolio_execute(
            "SELECT platform.portfolio_owner_lookup_apply(:business,:call,:ticket,CAST(:vectors AS jsonb))",
            dict(
                business=business,
                call=call,
                ticket=ticket,
                vectors=json.dumps(vectors, allow_nan=False),
            ),
        )
