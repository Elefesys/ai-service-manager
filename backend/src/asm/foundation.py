import argparse
import asyncio
import json
import signal
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal, Protocol

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from opentelemetry import trace
from pydantic import BaseModel, ConfigDict, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError, SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine

from asm import __version__

SCHEMA_REVISION = "0001"
tracer = trace.get_tracer("ai-service-manager.foundation")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ASM_", extra="ignore", hide_input_in_errors=True)
    # The unauthenticated M0 shell is not deployable outside LOCAL/TEST.
    environment: Literal["LOCAL", "TEST"]
    database_url: SecretStr

    @field_validator("database_url")
    @classmethod
    def require_postgres(cls, value: SecretStr) -> SecretStr:
        try:
            url = make_url(value.get_secret_value())
        except ArgumentError:
            raise ValueError("Invalid database URL") from None
        if url.drivername != "postgresql+psycopg" or not url.host or not url.database:
            raise ValueError("An explicit postgresql+psycopg connection is required")
        if url.username != "asm_runtime":
            raise ValueError("API/Worker/Scheduler must use the runtime identity")
        return value


class Database(Protocol):
    async def check(self) -> None: ...
    async def close(self) -> None: ...


class RuntimeDatabase:
    def __init__(self, settings: Settings, pool_size: int = 5) -> None:
        self.engine = create_async_engine(
            settings.database_url.get_secret_value(),
            pool_size=pool_size,
            max_overflow=0,
            pool_timeout=3,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 3},
            hide_parameters=True,
        )

    async def check(self) -> None:
        with tracer.start_as_current_span("database.readiness"):
            async with asyncio.timeout(3), self.engine.connect() as connection:
                role = (
                    (
                        await connection.execute(
                            text("""
                    SELECT rolname, rolsuper, rolbypassrls,
                        has_schema_privilege(current_user, 'app', 'CREATE') AS app_ddl,
                        has_schema_privilege(current_user, 'platform', 'CREATE') AS platform_ddl
                    FROM pg_roles WHERE rolname = current_user
                """)
                        )
                    )
                    .mappings()
                    .one()
                )
                if role["rolname"] != "asm_runtime" or any(
                    role[key] for key in ("rolsuper", "rolbypassrls", "app_ddl", "platform_ddl")
                ):
                    raise RuntimeError("Unsafe runtime database role")
                version = (
                    await connection.execute(
                        text("SELECT version_num FROM platform.alembic_version")
                    )
                ).scalar_one()
                extension = (
                    await connection.execute(
                        text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
                    )
                ).scalar_one()
                server = (await connection.execute(text("SHOW server_version_num"))).scalar_one()
                if version != SCHEMA_REVISION or extension != "0.8.6" or int(server) // 10000 != 18:
                    raise RuntimeError("Database capability/schema mismatch")

    async def close(self) -> None:
        await self.engine.dispose()


class Health(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    status: Literal["ok", "unavailable"]
    component: Literal["api", "database"]


class SystemInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    application: Literal["ai-service-manager"] = "ai-service-manager"
    version: str = __version__
    milestone: Literal["M0"] = "M0"
    business_features_enabled: Literal[False] = False


def create_app(settings: Settings | None = None, database: Database | None = None) -> FastAPI:
    config = settings if settings is not None else Settings()
    db = database if database is not None else RuntimeDatabase(config)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await db.close()

    app = FastAPI(title="AI Service Manager", version=__version__, lifespan=lifespan)

    @app.get("/health/live", response_model=Health)
    async def live() -> Health:
        return Health(status="ok", component="api")

    @app.get("/health/ready", response_model=Health, responses={503: {"model": Health}})
    async def ready() -> Health | JSONResponse:
        try:
            await db.check()
        except (SQLAlchemyError, TimeoutError, RuntimeError):
            return JSONResponse(
                status_code=503, content={"status": "unavailable", "component": "database"}
            )
        return Health(status="ok", component="database")

    @app.get("/api/v1/system", response_model=SystemInfo)
    async def system() -> SystemInfo:
        return SystemInfo()

    return app


async def serve(role: Literal["worker", "scheduler"]) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    db = RuntimeDatabase(Settings())
    try:
        await db.check()
        print(
            json.dumps(
                {"component": role, "event": "started", "mode": "shell", "jobs_enabled": False}
            ),
            flush=True,
        )
        # M2.1 adds durable claiming/leases; M0 does not simulate a queue.
        await stop.wait()
    finally:
        await db.close()
        print(json.dumps({"component": role, "event": "stopped"}), flush=True)
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(sig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("role", choices=["worker", "scheduler"])
    args = parser.parse_args()
    asyncio.run(serve(args.role))


if __name__ == "__main__":
    main()
