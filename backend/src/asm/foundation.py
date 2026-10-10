import argparse
import asyncio
import json
import signal
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Literal, Protocol

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from opentelemetry import trace
from pydantic import BaseModel, ConfigDict, SecretStr, field_validator
from pydantic_settings import SettingsConfigDict
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError, SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine

from asm import __version__
from asm.auth.config import AuthSettings
from asm.auth.http import install_auth
from asm.auth.service import AuthService
from asm.auth.store import AuthStore
from asm.billing.http import install_billing
from asm.tenancy import TenantDatabase

if TYPE_CHECKING:
    from asm.files.storage import ObjectStorage
    from asm.telegram.client import TelegramClient

tracer = trace.get_tracer("ai-service-manager.foundation")

# Runtime readiness tracks the exact accepted Alembic head independently from the
# frozen historical revision embedded in the tenancy.v1 semantic contract.
DATABASE_SCHEMA_REVISION = "0008"


class Settings(AuthSettings):
    model_config = SettingsConfigDict(env_prefix="ASM_", extra="ignore", hide_input_in_errors=True)
    # This synthetic authentication slice is not deployable outside LOCAL/TEST.
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
        self.tenancy = TenantDatabase(self.engine)

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
                if (
                    version != DATABASE_SCHEMA_REVISION
                    or extension != "0.8.6"
                    or int(server) // 10000 != 18
                ):
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


def create_app(
    settings: Settings | None = None,
    database: Database | None = None,
    *,
    telegram: "TelegramClient | None" = None,
    object_storage: "ObjectStorage | None" = None,
) -> FastAPI:
    from asm.files.config import StorageSettings
    from asm.files.storage import S3ObjectStorage
    from asm.messaging.database import MessagingDatabase
    from asm.messaging.http import install_messaging
    from asm.telegram.adapter import TelegramRefresher
    from asm.telegram.client import TelegramClient
    from asm.telegram.config import TelegramSettings
    from asm.telegram.database import TelegramIngress
    from asm.telegram.webhook import install_webhook

    config = settings if settings is not None else Settings()
    db = database if database is not None else RuntimeDatabase(config)

    auth_store = AuthStore(config.database_url.get_secret_value())
    auth = AuthService(auth_store, db.tenancy if isinstance(db, RuntimeDatabase) else None, config)

    telegram_settings = TelegramSettings(ASM_ENVIRONMENT=config.environment)
    telegram_client = telegram or (
        TelegramClient(telegram_settings) if telegram_settings.enabled else None
    )
    storage = object_storage
    if isinstance(db, RuntimeDatabase) and storage is None:
        storage_settings = StorageSettings()
        if storage_settings.environment != config.environment:
            raise RuntimeError("Storage environment mismatch")
        storage = S3ObjectStorage(storage_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if telegram_client is not None:
                await telegram_client.aclose()
            if isinstance(storage, S3ObjectStorage):
                await storage.close()
            await auth_store.close()
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

    app.state.auth_service = auth
    install_auth(app, auth, config)
    install_billing(app, auth, config)
    install_messaging(
        app,
        auth,
        config,
        environment=config.environment,
        storage=storage,
        telegram=TelegramRefresher(telegram_client) if telegram_client is not None else None,
    )
    install_webhook(
        app,
        telegram_settings,
        TelegramIngress(MessagingDatabase(db.engine), telegram_settings.bot_id)
        if telegram_settings.enabled and isinstance(db, RuntimeDatabase)
        else None,
    )
    return app


async def serve(role: Literal["worker", "scheduler"]) -> None:
    from asm.files.config import StorageSettings
    from asm.files.database import FileDatabase
    from asm.files.provider import ChannelImageProvider, ControlledImageProvider
    from asm.files.storage import S3ObjectStorage
    from asm.files.transfer import CleanupSweep, FetchTransfer
    from asm.messaging.adapter import ControlledAdapter
    from asm.messaging.database import MessagingDatabase
    from asm.messaging.worker import run
    from asm.telegram.client import TelegramClient
    from asm.telegram.config import TelegramSettings

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    settings = Settings()
    db = RuntimeDatabase(settings)
    storage = None
    files = None
    telegram = None
    try:
        telegram_settings = TelegramSettings(ASM_ENVIRONMENT=settings.environment)
        telegram = TelegramClient(telegram_settings) if telegram_settings.enabled else None
        await db.check()
        kernel = MessagingDatabase(db.engine)
        storage_settings = StorageSettings()
        if storage_settings.environment != settings.environment:
            raise RuntimeError("Storage environment mismatch")
        storage = S3ObjectStorage(storage_settings)
        file_db = FileDatabase(kernel)
        files = FetchTransfer(
            file_db,
            kernel,
            ChannelImageProvider(
                ControlledImageProvider(environment=settings.environment), telegram
            ),
            storage,
        )
        print(
            json.dumps(
                {"component": role, "event": "started", "mode": "controlled", "jobs_enabled": True}
            ),
            flush=True,
        )
        await run(
            role,
            kernel,
            ControlledAdapter(environment=settings.environment),
            stop,
            files=files,
            cleanup=CleanupSweep(file_db, storage),
            telegram=telegram,
        )
    finally:
        if telegram is not None:
            await telegram.aclose()
        if files is not None:
            await files.close()
        if storage is not None:
            await storage.close()
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
