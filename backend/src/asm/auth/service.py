from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from asm.auth.config import AuthSettings
from asm.auth.crypto import (
    PASSWORD_HASHER,
    HashBudget,
    csrf_value,
    new_token,
    normalize_login,
    token_verifier,
    verify_password,
)
from asm.auth.models import (
    AuthCode,
    AuthError,
    BootstrapResponse,
    MembershipResponse,
    SessionResponse,
)
from asm.auth.store import AuthStore
from asm.tenancy import AuthenticatedAccount, MembershipRole, TenantDatabase, TenantUnitOfWork
from asm.tenancy.types import permissions_for


class AuthService:
    def __init__(
        self, store: AuthStore, tenancy: TenantDatabase | None, settings: AuthSettings
    ) -> None:
        self.store, self.tenancy, self.settings = store, tenancy, settings
        self.hash_budget = HashBudget(settings.auth_hash_concurrency)
        # Generated per instance, not a usable account or hardcoded password.
        self._dummy_hash = PASSWORD_HASHER.hash(new_token())

    async def bootstrap(self, token: str | None) -> tuple[BootstrapResponse, str | None]:
        async with self.store.transaction() as connection:
            if token is not None:
                session = await self.store.session(connection, token)
                if session is not None:
                    return BootstrapResponse(
                        csrf_token=csrf_value(token), expires_at=session.expires_at
                    ), None
            fresh = new_token()
            expires = (
                await connection.execute(
                    text("SELECT platform.auth_bootstrap(:token, :ttl)"),
                    {
                        "token": token_verifier(fresh),
                        "ttl": self.settings.auth_prelogin_ttl_seconds,
                    },
                )
            ).scalar_one()
            return BootstrapResponse(csrf_token=csrf_value(fresh), expires_at=expires), fresh

    async def _current(self, connection: AsyncConnection, token: str) -> SessionResponse:
        session = await self.store.authenticated(connection, token)
        if session.user_account_id is None:
            raise AuthError(AuthCode.SESSION_REQUIRED, 401)
        rows = (
            (
                await connection.execute(
                    text("SELECT * FROM platform.auth_memberships(:token)"),
                    {"token": token_verifier(token)},
                )
            )
            .mappings()
            .all()
        )
        return SessionResponse(
            user_account_id=session.user_account_id,
            expires_at=session.expires_at,
            csrf_token=csrf_value(token),
            memberships=[
                MembershipResponse(
                    workspace_id=row["workspace_id"],
                    role=MembershipRole(row["role"]),
                    permissions=sorted(permissions_for(MembershipRole(row["role"]))),
                )
                for row in rows
            ],
        )

    async def current(self, token: str) -> SessionResponse:
        async with self.store.transaction() as connection:
            return await self._current(connection, token)

    async def login(self, token: str, login: str, password: str) -> tuple[SessionResponse, str]:
        login = normalize_login(login)
        async with self.store.transaction() as connection:
            previous = await self.store.session(connection, token)
            if previous is None or previous.user_account_id is not None:
                raise AuthError(AuthCode.SESSION_REQUIRED, 401)
        credentials = await self.store.lookup(login)
        encoded = credentials.password_hash if credentials is not None else self._dummy_hash
        # Both DB checkouts have ended before the costly high-level hash call.
        verified = await self.hash_budget.run(lambda: verify_password(encoded, password))
        if not verified or credentials is None:
            raise AuthError(AuthCode.INVALID_CREDENTIALS, 401)
        fresh = new_token()
        async with self.store.transaction() as connection:
            expires = (
                await connection.execute(
                    text("SELECT platform.auth_login(:previous,:account,:av,:cv,:fresh,:ttl)"),
                    {
                        "previous": token_verifier(token),
                        "account": credentials.user_account_id,
                        "av": credentials.account_version,
                        "cv": credentials.credential_version,
                        "fresh": token_verifier(fresh),
                        "ttl": self.settings.auth_session_ttl_seconds,
                    },
                )
            ).scalar_one()
            if expires is None:
                raise AuthError(AuthCode.INVALID_CREDENTIALS, 401)
            return await self._current(connection, fresh), fresh

    async def rotate(self, token: str) -> tuple[SessionResponse, str]:
        fresh = new_token()
        async with self.store.transaction() as connection:
            expires = (
                await connection.execute(
                    text("SELECT platform.auth_rotate(:previous,:fresh)"),
                    {"previous": token_verifier(token), "fresh": token_verifier(fresh)},
                )
            ).scalar_one()
            if expires is None:
                raise AuthError(AuthCode.SESSION_REQUIRED, 401)
            return await self._current(connection, fresh), fresh

    async def logout(self, token: str) -> None:
        async with self.store.transaction() as connection:
            revoked = (
                await connection.execute(
                    text("SELECT platform.auth_logout(:token)"), {"token": token_verifier(token)}
                )
            ).scalar_one()
            if not revoked:
                raise AuthError(AuthCode.SESSION_REQUIRED, 401)

    @asynccontextmanager
    async def workspace(self, token: str, workspace_id: UUID) -> AsyncIterator[TenantUnitOfWork]:
        if self.tenancy is None:
            raise AuthError(AuthCode.UNAVAILABLE, 503)
        async with self.store.transaction() as connection:
            session = await self.store.authenticated(connection, token)
            if session.user_account_id is None:
                raise AuthError(AuthCode.SESSION_REQUIRED, 401)
            # The only HTTP-facing issuer: after actual cookie + DB auth validation.
            # Candidate Workspace comes from the route; actor and correlation do not.
            actor = AuthenticatedAccount(session.user_account_id)
            async with self.tenancy.transaction(actor, workspace_id, uuid4()) as unit:
                yield unit
        # The shared session lock spans the completed M1.1 UOW, never vice versa.
