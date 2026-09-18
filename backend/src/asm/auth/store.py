"""Narrow platform auth calls through a separate bounded runtime-role pool."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from psycopg import AsyncConnection as PsycopgAsyncConnection
from psycopg.pq import TransactionStatus
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from asm.auth.crypto import token_verifier
from asm.auth.models import AuthCode, AuthError


@dataclass(frozen=True)
class Credentials:
    user_account_id: UUID
    password_hash: str = field(repr=False)
    credential_version: int
    account_version: int


@dataclass(frozen=True)
class Session:
    user_account_id: UUID | None
    expires_at: datetime


class AuthStore:
    def __init__(self, database_url: str) -> None:
        url = make_url(database_url)
        if url.drivername != "postgresql+psycopg" or url.username != "asm_runtime":
            raise AuthError(AuthCode.UNAVAILABLE, 503)
        self.engine = create_async_engine(
            url,
            pool_size=4,
            max_overflow=0,
            pool_timeout=2,
            pool_pre_ping=True,
            hide_parameters=True,
            connect_args={"connect_timeout": 3},
        )

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncConnection]:
        async with asyncio.timeout(4), self.engine.connect() as connection, connection.begin():
            driver = (await connection.get_raw_connection()).driver_connection
            if not isinstance(driver, PsycopgAsyncConnection) or driver.autocommit:
                raise AuthError(AuthCode.UNAVAILABLE, 503)
            if (
                await connection.execute(text("SELECT current_user"))
            ).scalar_one() != "asm_runtime":
                raise AuthError(AuthCode.UNAVAILABLE, 503)
            # Actual driver state, not SQLAlchemy's logical begin() flag.
            if driver.info.transaction_status != TransactionStatus.INTRANS:
                raise AuthError(AuthCode.UNAVAILABLE, 503)
            yield connection
            if driver.autocommit or driver.info.transaction_status != TransactionStatus.INTRANS:
                raise AuthError(AuthCode.UNAVAILABLE, 503)

    async def lookup(self, login: str) -> Credentials | None:
        async with self.transaction() as connection:
            row = (
                (
                    await connection.execute(
                        text("SELECT * FROM platform.auth_password_lookup(:login)"),
                        {"login": login},
                    )
                )
                .mappings()
                .one_or_none()
            )
            return Credentials(**row) if row is not None else None

    async def session(self, connection: AsyncConnection, token: str) -> Session | None:
        row = (
            (
                await connection.execute(
                    text("SELECT * FROM platform.auth_session(:token)"),
                    {"token": token_verifier(token)},
                )
            )
            .mappings()
            .one_or_none()
        )
        return Session(**row) if row is not None else None

    async def authenticated(self, connection: AsyncConnection, token: str) -> Session:
        session = await self.session(connection, token)
        if session is None or session.user_account_id is None:
            raise AuthError(AuthCode.SESSION_REQUIRED, 401)
        return session

    async def close(self) -> None:
        await self.engine.dispose()
