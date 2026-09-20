"""Three owner endpoints sharing the accepted auth/CSRF/admission boundary."""

import re
from typing import Any
from uuid import UUID

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from asm.auth.config import AuthSettings
from asm.auth.http import mutation_token, required_cookie
from asm.auth.service import AuthService
from asm.billing.errors import BillingError, BillingUnavailable
from asm.billing.models import (
    AuditCursor,
    AuditPage,
    BillingResponse,
    BillingStateError,
    CommonError,
    ContactPatch,
    ContactResult,
)
from asm.billing.permissions import BillingPermission, require
from asm.billing.repository import BillingRepository
from asm.billing.validation import KEY_PATTERN, CanonicalUUID, decode_cursor, strict_json


def no_query(request: Request) -> None:
    if request.query_params:
        raise BillingError("INVALID_REQUEST", 422)


def audit_query(request: Request) -> tuple[int, AuditCursor | None]:
    values: dict[str, str] = {}
    try:
        for name, value in request.query_params.multi_items():
            if name not in ("limit", "cursor") or name in values:
                raise ValueError("Invalid query")
            values[name] = value
        raw_limit = values.get("limit", "25")
        if not raw_limit.isascii() or not raw_limit.isdigit():
            raise ValueError("Invalid limit")
        limit = int(raw_limit)
        if not 1 <= limit <= 100:
            raise ValueError("Invalid limit")
        cursor = (
            AuditCursor.model_validate(decode_cursor(values["cursor"]))
            if "cursor" in values
            else None
        )
        return limit, cursor
    except (ValueError, TypeError, RecursionError, ValidationError):
        raise BillingError("INVALID_REQUEST", 422) from None


def install_billing(app: FastAPI, auth: AuthService, settings: AuthSettings) -> None:
    errors: dict[int | str, dict[str, Any]] = {
        status: {"model": CommonError} for status in (401, 403, 413, 415, 422, 429, 500, 503)
    }
    router = APIRouter(prefix="/api/v1/workspaces", responses=errors, tags=["billing"])

    @app.exception_handler(BillingError)
    async def billing_error(request: Request, error: BillingError) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": error.code}},
            status_code=error.status,
            headers={"Cache-Control": "no-store"},
        )

    @app.exception_handler(BillingUnavailable)
    async def state_error(request: Request, error: BillingUnavailable) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": "BILLING_STATE_UNAVAILABLE", "state_reason": error.reason}},
            status_code=503,
            headers={"Cache-Control": "no-store"},
        )

    @router.get(
        "/{workspace_id}/billing",
        response_model=BillingResponse,
        responses={503: {"model": CommonError | BillingStateError}},
        description="OWNER billing:read. No query parameters. One DB-time snapshot of local state.",
    )
    async def billing(request: Request, workspace_id: CanonicalUUID) -> BillingResponse:
        no_query(request)
        async with auth.workspace(required_cookie(request, settings), UUID(workspace_id)) as unit:
            result = await BillingRepository(unit).billing()
        return result

    @router.patch(
        "/{workspace_id}/billing-account",
        response_model=ContactResult,
        responses={404: {"model": CommonError}, 409: {"model": CommonError}},
        description="OWNER billing:manage. Exactly one Idempotency-Key; If-Match and query parameters forbidden. Replay returns original metadata; GET obtains current contact.",
        openapi_extra={
            "parameters": [
                {
                    "in": "header",
                    "name": "Idempotency-Key",
                    "required": True,
                    "schema": {
                        "type": "string",
                        "pattern": KEY_PATTERN,
                        "minLength": 1,
                        "maxLength": 128,
                    },
                }
            ],
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": ContactPatch.model_json_schema()}},
            },
        },
    )
    async def contact(request: Request, workspace_id: CanonicalUUID) -> ContactResult:
        no_query(request)
        keys = request.headers.getlist("idempotency-key")
        if (
            len(keys) != 1
            or re.fullmatch(KEY_PATTERN, keys[0]) is None
            or "if-match" in request.headers
        ):
            raise BillingError("INVALID_REQUEST", 422)
        token = mutation_token(request, settings)
        async with auth.workspace(token, UUID(workspace_id)) as unit:
            await require(unit, BillingPermission.MANAGE)
            try:
                body = ContactPatch.model_validate(strict_json(await request.body()))
            except (ValueError, TypeError, RecursionError, ValidationError):
                raise BillingError("INVALID_REQUEST", 422) from None
            result = await BillingRepository(unit).change_contact(body, keys[0])
        # Tenant commit and outer admission release precede response serialization.
        return result

    @router.get(
        "/{workspace_id}/audit-events",
        response_model=AuditPage,
        description="OWNER audit:read. Tenant-scoped descending tuple pagination; cursor is not a credential or a frozen-history guarantee.",
        openapi_extra={
            "parameters": [
                {
                    "in": "query",
                    "name": "limit",
                    "required": False,
                    "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 25},
                },
                {
                    "in": "query",
                    "name": "cursor",
                    "required": False,
                    "schema": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 1024,
                        "pattern": "^[A-Za-z0-9_-]+$",
                    },
                },
            ]
        },
    )
    async def audit(request: Request, workspace_id: CanonicalUUID) -> AuditPage:
        async with auth.workspace(required_cookie(request, settings), UUID(workspace_id)) as unit:
            await require(unit, BillingPermission.AUDIT)
            limit, cursor = audit_query(request)
            result = await BillingRepository(unit).audit(limit, cursor)
        return result

    app.include_router(router)
