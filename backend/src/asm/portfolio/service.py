"""Finite owner operations: authority commits before I/O, accounting before apply."""

import asyncio
import base64
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from starlette.requests import ClientDisconnect

from asm.ai.vision import VisionClient, VisionPreprocessor
from asm.ai.vision import unavailable as vision_unavailable
from asm.auth.models import AuthError
from asm.auth.service import AuthService
from asm.files.models import ImageManifest, OwnerDeletePermit, OwnerUploadPermit
from asm.files.validation import ImageValidator, read_image
from asm.knowledge.embeddings import EmbeddingClient, EmbeddingFailure, unavailable, validate_wire
from asm.knowledge.repository import complete_embedding
from asm.messaging.errors import Code, MessagingError
from asm.portfolio.errors import PortfolioCode, PortfolioError
from asm.portfolio.models import (
    AnalysisResponse,
    CommandRequest,
    CommandResponse,
    ConfirmItem,
    ConversationState,
    CreateBuild,
    DeleteAsset,
    EmbeddingReservation,
    FinishUpload,
    InitUpload,
    Operation,
    OwnerState,
    PublishPortfolio,
    PurgeResponse,
    RevokeItem,
    RollbackPortfolio,
    SaveItem,
    UploadResponse,
    VisionReservation,
)
from asm.portfolio.repository import PortfolioRepository, decoded, private_call
from asm.portfolio.storage import PortfolioStorage
from asm.tenancy import MembershipRole


def remaining(deadline: datetime | None, maximum: float) -> float:
    if deadline is None or deadline.tzinfo is None:
        raise PortfolioError(PortfolioCode.UNAVAILABLE)
    seconds = min(maximum, (deadline - datetime.now(UTC)).total_seconds())
    if seconds <= 0:
        raise PortfolioError(PortfolioCode.UPLOAD_NOT_ALLOWED)
    return seconds


class PortfolioService:
    def __init__(
        self,
        auth: AuthService,
        storage: PortfolioStorage | None = None,
        *,
        vision: VisionClient | None = None,
        embeddings: EmbeddingClient | None = None,
        environment: str = "TEST",
    ):
        if vision is not None and type(vision) is not VisionClient:
            raise ValueError("CONTROLLED_VISION_CLIENT_REQUIRED")
        if embeddings is not None and type(embeddings) is not EmbeddingClient:
            raise ValueError("CONTROLLED_EMBEDDING_CLIENT_REQUIRED")
        self.auth, self.storage = auth, storage
        self.vision = vision if vision is not None else VisionClient()
        self.embeddings = embeddings if embeddings is not None else EmbeddingClient()
        if (
            environment not in {"LOCAL", "TEST"}
            or environment != "TEST"
            and (self.vision.enabled or self.embeddings.enabled)
        ):
            raise ValueError("CONTROLLED_TEST_PROFILE_REQUIRED")
        self.environment = environment
        self.validator, self.preprocessor = ImageValidator(), VisionPreprocessor()

    async def close(self) -> None:
        await self.validator.close()
        await self.preprocessor.close()

    @asynccontextmanager
    async def _owner(self, token: str, workspace: UUID) -> AsyncIterator[PortfolioRepository]:
        try:
            async with self.auth.workspace(token, workspace) as unit:
                if await unit.billing_membership_role() is not MembershipRole.OWNER:
                    raise PortfolioError(PortfolioCode.ACCESS_DENIED)
                yield PortfolioRepository(unit)
        except (SQLAlchemyError, ValidationError, TimeoutError):
            raise PortfolioError(PortfolioCode.UNAVAILABLE) from None

    def _modes(self) -> dict[str, str]:
        return {
            "vision_mode": "CONTROLLED" if self.vision.enabled else "DISABLED",
            "embedding_mode": "CONTROLLED" if self.embeddings.enabled else "DISABLED",
        }

    async def state(self, token: str, workspace: UUID, business: UUID) -> OwnerState:
        async with self._owner(token, workspace) as repository:
            value = await repository.state(business)
        return decoded(OwnerState, value.model_dump(mode="json") | self._modes())

    async def conversation(
        self, token: str, workspace: UUID, business: UUID, conversation: UUID
    ) -> ConversationState:
        async with self._owner(token, workspace) as repository:
            value = await repository.conversation(business, conversation)
        return decoded(ConversationState, value.model_dump(mode="json") | self._modes())

    async def command(
        self,
        token: str,
        workspace: UUID,
        business: UUID,
        operation: Operation,
        key: str,
        body: CommandRequest,
        *,
        asset: UUID | None = None,
        version: UUID | None = None,
        upload: UUID | None = None,
        item: UUID | None = None,
    ) -> CommandResponse:
        expected = {
            "PORTFOLIO_UPLOAD_CREATE": InitUpload,
            "PORTFOLIO_UPLOAD_FINALIZE": FinishUpload,
            "PORTFOLIO_UPLOAD_ABANDON": FinishUpload,
            "PORTFOLIO_SAVE": SaveItem,
            "PORTFOLIO_CONFIRM": ConfirmItem,
            "PORTFOLIO_REVOKE": RevokeItem,
            "PORTFOLIO_DELETE": DeleteAsset,
            "PORTFOLIO_BUILD_CREATE": CreateBuild,
            "PORTFOLIO_PUBLISH": PublishPortfolio,
            "PORTFOLIO_ROLLBACK": RollbackPortfolio,
        }
        if type(body) is not expected[operation]:
            raise PortfolioError(PortfolioCode.INVALID_INPUT)
        payload = body.model_dump(mode="json")
        if operation in {"PORTFOLIO_UPLOAD_FINALIZE", "PORTFOLIO_UPLOAD_ABANDON"}:
            if asset is None or version is None or upload is None:
                raise PortfolioError(PortfolioCode.INVALID_INPUT)
            payload |= {
                "asset_id": str(asset),
                "version_id": str(version),
                "upload_id": str(upload),
            }
        elif operation == "PORTFOLIO_DELETE":
            if asset is None:
                raise PortfolioError(PortfolioCode.INVALID_INPUT)
            payload["asset_id"] = str(asset)
        elif operation in {"PORTFOLIO_CONFIRM", "PORTFOLIO_REVOKE"}:
            if item is None:
                raise PortfolioError(PortfolioCode.INVALID_INPUT)
            payload["item_id"] = str(item)
        purge_versions: tuple[UUID, ...] = ()
        async with self._owner(token, workspace) as repository:
            if operation == "PORTFOLIO_DELETE":
                before = await repository.state(business)
                current = next((a for a in before.assets if a.asset_id == str(asset)), None)
                if current is not None and current.accepted_version_id is not None:
                    purge_versions = (UUID(current.accepted_version_id),)
            value = await repository.command(business, operation, key, payload)
        if (
            operation == "PORTFOLIO_BUILD_CREATE"
            and value.outcome == "ACCEPTED"
            and self.embeddings.enabled
        ):
            if value.result.build_id is None:
                raise PortfolioError(PortfolioCode.UNAVAILABLE)
            await self._build(token, workspace, business, UUID(value.result.build_id))
        if (
            operation == "PORTFOLIO_DELETE"
            and value.outcome == "ACCEPTED"
            and asset is not None
            and self.storage is not None
        ):
            for target in purge_versions:
                # Logical deletion is already committed. A failed physical purge
                # stays visible for a separate fresh OWNER action after reload.
                try:
                    await self.purge(token, workspace, business, asset, target)
                except (PortfolioError, AuthError, SQLAlchemyError, TimeoutError):
                    pass
        return value

    async def _upload_complete(
        self, upload: UUID, ticket: UUID, outcome: dict[str, Any]
    ) -> UploadResponse:
        async with self.auth.store.transaction() as connection:
            raw = await private_call(
                connection,
                "SELECT platform.portfolio_upload_complete(:upload,:ticket,CAST(:body AS jsonb))",
                {
                    "upload": upload,
                    "ticket": ticket,
                    "body": json.dumps(outcome, allow_nan=False),
                },
            )
        value = decoded(UploadResponse, {"schema_version": 1, **raw})
        if value.upload_id != str(upload):
            raise PortfolioError(PortfolioCode.UNAVAILABLE)
        return value

    async def _best_upload(self, upload: UUID, ticket: UUID, outcome: dict[str, Any]) -> None:
        try:
            async with asyncio.timeout(1):
                await self._upload_complete(upload, ticket, outcome)
        except (Exception, asyncio.CancelledError):
            pass

    async def upload(
        self,
        token: str,
        workspace: UUID,
        business: UUID,
        asset: UUID,
        version: UUID,
        upload: UUID,
        stream: AsyncIterator[bytes],
        mime: str,
        declared_length: int | None,
    ) -> UploadResponse:
        # This committed guard precedes the first request.stream iteration.
        async with self._owner(token, workspace) as repository:
            intent = await repository.upload_begin(business, asset, version, upload)
        sent = False
        try:
            async with asyncio.timeout(remaining(intent.operation_deadline, 45)):
                if (
                    mime != intent.manifest.mime_type
                    or declared_length is not None
                    and declared_length != intent.manifest.size_bytes
                ):
                    raise PortfolioError(PortfolioCode.MANIFEST_MISMATCH)
                if self.storage is None:
                    raise PortfolioError(PortfolioCode.DEPENDENCY_UNAVAILABLE)

                async def chunks() -> AsyncIterator[bytes]:
                    size = 0
                    async for chunk in stream:
                        if not chunk:
                            continue  # Starlette's final empty sentinel, not image content.
                        size += len(chunk)
                        if size > intent.manifest.size_bytes:
                            raise PortfolioError(PortfolioCode.MANIFEST_MISMATCH)
                        yield chunk

                content = await read_image(chunks())
                manifest = await self.validator.validate(content)
                async with self._owner(token, workspace) as repository:
                    value = await repository.upload_prepare(
                        business, asset, version, upload, intent.ticket, manifest
                    )
                if value.storage_key is None or value.operation_deadline is None:
                    raise PortfolioError(PortfolioCode.UNAVAILABLE)
                permit = OwnerUploadPermit(
                    workspace_id=value.workspace_id,
                    business_id=value.business_id,
                    asset_id=value.asset_id,
                    version_id=value.version_id,
                    upload_id=value.upload_id,
                    ticket=value.ticket,
                    storage_key=value.storage_key,
                    manifest=manifest,
                    operation_deadline=value.operation_deadline,
                )
                sent = True
                await self.storage.put_owner(permit, content)
        except asyncio.CancelledError:
            await self._best_upload(
                upload,
                intent.ticket,
                {
                    "kind": "UNKNOWN" if sent else "ERROR",
                    "manifest": None,
                    "error_code": "CANCELLED",
                },
            )
            raise
        except ClientDisconnect:
            await self._best_upload(
                upload,
                intent.ticket,
                {"kind": "ERROR", "manifest": None, "error_code": "DISCONNECT"},
            )
            raise PortfolioError(PortfolioCode.DEPENDENCY_UNAVAILABLE) from None
        except (
            TimeoutError,
            MessagingError,
            PortfolioError,
            AuthError,
            SQLAlchemyError,
            ValidationError,
        ) as error:
            code = (
                "DEPENDENCY_TIMEOUT"
                if isinstance(error, TimeoutError)
                or isinstance(error, MessagingError)
                and error.code == Code.DEPENDENCY_TIMEOUT
                else "DEPENDENCY_UNAVAILABLE"
            )
            if isinstance(error, PortfolioError) and error.code == PortfolioCode.MANIFEST_MISMATCH:
                code = "MANIFEST_MISMATCH"
            if isinstance(error, MessagingError) and error.code == Code.INVALID_INPUT:
                code = "INVALID_IMAGE"
            await self._best_upload(
                upload,
                intent.ticket,
                {"kind": "UNKNOWN" if sent else "ERROR", "manifest": None, "error_code": code},
            )
            if isinstance(error, (AuthError, PortfolioError)):
                raise
            raise PortfolioError(
                PortfolioCode.INVALID_IMAGE
                if code == "INVALID_IMAGE"
                else PortfolioCode.DEPENDENCY_TIMEOUT
                if code == "DEPENDENCY_TIMEOUT"
                else PortfolioCode.DEPENDENCY_UNAVAILABLE
            ) from None
        outcome = {
            "kind": "STORED",
            "manifest": manifest.model_dump(mode="json"),
            "error_code": None,
        }
        try:
            return await self._upload_complete(upload, intent.ticket, outcome)
        except asyncio.CancelledError:
            await self._best_upload(upload, intent.ticket, outcome)
            raise

    async def _checked_bytes(
        self, key: str, manifest: ImageManifest, *, head: bool = False
    ) -> bytes:
        if self.storage is None:
            raise PortfolioError(PortfolioCode.DEPENDENCY_UNAVAILABLE)
        if head:
            info = await self.storage.head(key)
            checksum = base64.b64encode(bytes.fromhex(manifest.sha256)).decode("ascii")
            if (info.size_bytes, info.mime_type) != (
                manifest.size_bytes,
                manifest.mime_type,
            ) or info.checksum_sha256 not in (None, checksum):
                raise PortfolioError(PortfolioCode.MANIFEST_MISMATCH)
        content = await self.storage.get(key)
        actual = await self.validator.validate(content)
        if actual != manifest:
            raise PortfolioError(PortfolioCode.MANIFEST_MISMATCH)
        return content

    async def recover(
        self, token: str, workspace: UUID, business: UUID, asset: UUID, version: UUID, upload: UUID
    ) -> UploadResponse:
        async with self._owner(token, workspace) as repository:
            intent = await repository.recover(business, asset, version, upload)
        try:
            async with asyncio.timeout(remaining(intent.recovery_deadline, 15)):
                manifest = intent.manifest.decoded()
                if intent.storage_key is None:
                    raise PortfolioError(PortfolioCode.UNAVAILABLE)
                await self._checked_bytes(intent.storage_key, manifest, head=True)
        except asyncio.CancelledError:
            await self._best_upload(
                upload,
                intent.ticket,
                {"kind": "UNKNOWN", "manifest": None, "error_code": "CANCELLED"},
            )
            raise
        except (TimeoutError, MessagingError, PortfolioError, ValidationError):
            # This recovery never writes or retries an uncertain original PUT.
            return await self._upload_complete(
                upload,
                intent.ticket,
                {"kind": "UNKNOWN", "manifest": None, "error_code": "DEPENDENCY_UNAVAILABLE"},
            )
        return await self._upload_complete(
            upload,
            intent.ticket,
            {"kind": "STORED", "manifest": manifest.model_dump(mode="json"), "error_code": None},
        )

    async def preview(
        self, token: str, workspace: UUID, business: UUID, asset: UUID, version: UUID
    ) -> tuple[bytes, str]:
        async with self._owner(token, workspace) as repository:
            permit = await repository.preview(business, asset, version)
        try:
            async with asyncio.timeout(15):
                content = await self._checked_bytes(permit.storage_key, permit.manifest)
        except (TimeoutError, MessagingError, ValidationError):
            raise PortfolioError(PortfolioCode.DEPENDENCY_UNAVAILABLE) from None
        async with self._owner(token, workspace) as repository:
            current = await repository.preview(business, asset, version)
        if current != permit:
            raise PortfolioError(PortfolioCode.SOURCE_STALE)
        return content, permit.manifest.mime_type

    async def purge(
        self, token: str, workspace: UUID, business: UUID, asset: UUID, version: UUID
    ) -> PurgeResponse:
        async with self._owner(token, workspace) as repository:
            raw = await repository.purge(business, asset, version)
        if self.storage is None or raw.storage_key is None or raw.purge_deadline is None:
            raise PortfolioError(PortfolioCode.DEPENDENCY_UNAVAILABLE)
        permit = OwnerDeletePermit(
            workspace_id=raw.workspace_id,
            business_id=raw.business_id,
            asset_id=raw.asset_id,
            version_id=raw.version_id,
            upload_id=raw.upload_id,
            ticket=raw.ticket,
            storage_key=raw.storage_key,
            operation="OWNER_ACCEPTED_DELETE",
            purge_deadline=raw.purge_deadline,
        )
        error = None
        cancelled = False
        try:
            async with asyncio.timeout(remaining(raw.purge_deadline, 15)):
                await self.storage.delete_owner(permit)
        except asyncio.CancelledError:
            error = "DEPENDENCY_TIMEOUT"
            cancelled = True
        except TimeoutError:
            error = "DEPENDENCY_TIMEOUT"
        except MessagingError as exc:
            error = (
                "DEPENDENCY_TIMEOUT"
                if exc.code == Code.DEPENDENCY_TIMEOUT
                else "DEPENDENCY_UNAVAILABLE"
            )
        async with self.auth.store.transaction() as connection:
            result = await private_call(
                connection,
                "SELECT platform.portfolio_purge_complete(:version,:ticket,:error)",
                dict(version=version, ticket=raw.ticket, error=error),
            )
        if cancelled:
            raise asyncio.CancelledError
        return decoded(PurgeResponse, {"schema_version": 1, **result})

    async def _vision_complete(
        self, analysis: UUID, ticket: UUID, outcome: dict[str, Any]
    ) -> dict[str, Any]:
        async with self.auth.store.transaction() as connection:
            raw = await private_call(
                connection,
                "SELECT platform.vision_complete(:analysis,:ticket,CAST(:body AS jsonb))",
                dict(
                    analysis=analysis,
                    ticket=ticket,
                    body=json.dumps(outcome, allow_nan=False, ensure_ascii=False),
                ),
            )
        if type(raw) is not dict or raw.get("analysis_id") != str(analysis):
            raise PortfolioError(PortfolioCode.UNAVAILABLE)
        return cast(dict[str, Any], raw)

    async def _best_vision(self, reservation: VisionReservation, outcome: dict[str, Any]) -> None:
        if reservation.ticket is None:
            return
        try:
            async with asyncio.timeout(1):
                await self._vision_complete(reservation.analysis_id, reservation.ticket, outcome)
        except (Exception, asyncio.CancelledError):
            pass

    async def _reserve_vision(
        self,
        token: str,
        workspace: UUID,
        business: UUID,
        *,
        asset: UUID | None,
        version: UUID | None,
        conversation: UUID | None,
    ) -> tuple[VisionReservation, UUID | None]:
        # Probe only stable source identity first. A replay does not manufacture
        # empty budget sessions; a missing admission fails before any INSERT.
        try:
            async with self._owner(token, workspace) as repository:
                prior = await repository.vision_reserve(
                    business, None, asset=asset, version=version, conversation=conversation
                )
            return prior, None
        except PortfolioError as error:
            if error.code != PortfolioCode.SESSION_NOT_ALLOWED:
                raise
        async with self._owner(token, workspace) as repository:
            session = await repository.session(business, conversation)
            reservation = await repository.vision_reserve(
                business, session, asset=asset, version=version, conversation=conversation
            )
        return reservation, session

    async def analysis(
        self,
        token: str,
        workspace: UUID,
        business: UUID,
        *,
        asset: UUID | None = None,
        version: UUID | None = None,
        conversation: UUID | None = None,
    ) -> AnalysisResponse:
        if not self.vision.enabled:
            async with self._owner(token, workspace) as repository:
                if conversation is not None:
                    await repository.conversation(business, conversation)
                elif asset is not None and version is not None:
                    await repository.preview(business, asset, version)
                else:
                    raise PortfolioError(PortfolioCode.INVALID_INPUT)
            return AnalysisResponse(
                schema_version=1, outcome="DISABLED", analysis_id=None, state=None, applied=False
            )
        reservation, session = await self._reserve_vision(
            token, workspace, business, asset=asset, version=version, conversation=conversation
        )
        if reservation.status == "REPLAY":
            applied = False
            if conversation is not None:
                current = await self.conversation(token, workspace, business, conversation)
                applied = current.vision_analysis is not None and current.vision_analysis.applied
                if applied and self.embeddings.enabled:
                    await self._lookup(
                        token, workspace, business, conversation, reservation.analysis_id, None
                    )
            else:
                current_owner = await self.state(token, workspace, business)
                applied = any(
                    a.analysis is not None
                    and a.analysis.analysis_id == str(reservation.analysis_id)
                    and a.analysis.applied
                    for a in current_owner.assets
                )
            return AnalysisResponse(
                schema_version=1,
                outcome="REPLAY",
                analysis_id=str(reservation.analysis_id),
                state=reservation.state,
                applied=applied,
            )
        if (
            reservation.ticket is None
            or reservation.storage_key is None
            or reservation.manifest is None
        ):
            raise PortfolioError(PortfolioCode.UNAVAILABLE)
        sent = False
        try:
            async with asyncio.timeout(remaining(reservation.deadline, 30)):
                if self.storage is None:
                    raise PortfolioError(PortfolioCode.DEPENDENCY_UNAVAILABLE)
                original = await self.storage.get(reservation.storage_key)
                image = await self.preprocessor.prepare(original, reservation.manifest)
                async with self._owner(token, workspace) as repository:
                    await repository.vision_authorize(
                        business, reservation.analysis_id, reservation.ticket
                    )
                sent = True
                outcome = await self.vision.complete(image, deadline=reservation.deadline)
        except asyncio.CancelledError:
            await self._best_vision(reservation, vision_unavailable("CANCELLED", unknown=sent))
            raise
        except (TimeoutError, MessagingError, PortfolioError, AuthError, ValueError) as error:
            code = (
                "TIMEOUT"
                if isinstance(error, TimeoutError)
                else "SOURCE_STALE"
                if isinstance(error, (AuthError, PortfolioError))
                else "INVALID_IMAGE"
            )
            outcome = vision_unavailable(code, unknown=sent)
            await self._vision_complete(reservation.analysis_id, reservation.ticket, outcome)
            if isinstance(error, (PortfolioError, AuthError)):
                raise
            return AnalysisResponse(
                schema_version=1,
                outcome="UNAVAILABLE",
                analysis_id=str(reservation.analysis_id),
                state="UNKNOWN" if sent else "ERROR",
                applied=False,
            )
        try:
            completed = await self._vision_complete(
                reservation.analysis_id, reservation.ticket, outcome
            )
        except asyncio.CancelledError:
            await self._best_vision(reservation, outcome)
            raise
        applied = False
        if outcome["kind"] == "SUCCESS" and completed["state"] == "SUCCESS":
            async with self._owner(token, workspace) as repository:
                result = await repository.vision_apply(
                    business, reservation.analysis_id, reservation.ticket
                )
            applied = result.get("applied") is True
            if applied and conversation is not None and self.embeddings.enabled:
                await self._lookup(
                    token, workspace, business, conversation, reservation.analysis_id, session
                )
        return AnalysisResponse(
            schema_version=1,
            outcome="COMPLETE",
            analysis_id=str(reservation.analysis_id),
            state=completed["state"],
            applied=applied,
        )

    async def _embedding(self, reservation: EmbeddingReservation) -> dict[str, Any] | None:
        if reservation.status == "REPLAY":
            return None
        if (
            reservation.call_id is None
            or reservation.ticket is None
            or reservation.wire is None
            or reservation.deadline is None
            or reservation.wire_sha256 is None
        ):
            raise PortfolioError(PortfolioCode.UNAVAILABLE)
        call, ticket = reservation.call_id, reservation.ticket

        async def complete(outcome: dict[str, Any]) -> dict[str, Any]:
            async with self.auth.store.transaction() as connection:
                return await complete_embedding(connection, call, ticket, outcome)

        try:
            try:
                validate_wire(reservation.wire)
                outcome = await self.embeddings.complete(
                    reservation.wire,
                    deadline=reservation.deadline,
                    wire_sha256=reservation.wire_sha256,
                )
            except EmbeddingFailure as error:
                outcome = unavailable(error.code)
            recorded = await complete(outcome)
        except asyncio.CancelledError:
            try:
                async with asyncio.timeout(1):
                    await complete(unavailable("CANCELLED", unknown=True))
            except (Exception, asyncio.CancelledError):
                pass
            raise
        if outcome["kind"] != "SUCCESS" or recorded["state"] != "SUCCESS":
            return None
        return outcome

    async def _build(self, token: str, workspace: UUID, business: UUID, build: UUID) -> None:
        async with self._owner(token, workspace) as repository:
            state = await repository.state(business)
            current = next((b for b in state.builds if b.build_id == str(build)), None)
            if current is None or current.state != "PLANNED" or current.input_count == 0:
                return
            session = await repository.session(business, None)
            reservation = await repository.build_reserve(business, build, session)
        outcome = await self._embedding(reservation)
        if outcome is not None:
            assert reservation.call_id is not None and reservation.ticket is not None
            async with self._owner(token, workspace) as repository:
                await repository.build_apply(
                    business, reservation.call_id, reservation.ticket, outcome["vectors"]
                )

    async def _lookup(
        self,
        token: str,
        workspace: UUID,
        business: UUID,
        conversation: UUID,
        analysis: UUID,
        session: UUID | None,
    ) -> None:
        try:
            async with self._owner(token, workspace) as repository:
                reservation = await repository.lookup_reserve(business, analysis, session)
        except PortfolioError as error:
            if error.code != PortfolioCode.SESSION_NOT_ALLOWED:
                raise
            async with self._owner(token, workspace) as repository:
                session = await repository.session(business, conversation)
                reservation = await repository.lookup_reserve(business, analysis, session)
        outcome = await self._embedding(reservation)
        if outcome is not None:
            assert reservation.call_id is not None and reservation.ticket is not None
            async with self._owner(token, workspace) as repository:
                await repository.lookup_apply(
                    business, reservation.call_id, reservation.ticket, outcome["vectors"]
                )

    async def matches(
        self, token: str, workspace: UUID, business: UUID, conversation: UUID
    ) -> ConversationState:
        current = await self.conversation(token, workspace, business, conversation)
        if not self.embeddings.enabled:
            return current
        if current.vision_analysis is None or not current.vision_analysis.applied:
            raise PortfolioError(PortfolioCode.ANALYSIS_UNAVAILABLE)
        await self._lookup(
            token,
            workspace,
            business,
            conversation,
            UUID(current.vision_analysis.analysis_id),
            None,
        )
        return await self.conversation(token, workspace, business, conversation)
