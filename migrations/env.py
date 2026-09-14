import os

from alembic import context
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool


def migrate() -> None:
    if context.is_offline_mode():
        raise RuntimeError("Migrations require real PostgreSQL")
    engine = create_engine(os.environ["ASM_MIGRATION_DATABASE_URL"], poolclass=NullPool, hide_parameters=True)
    try:
        with engine.begin() as connection:
            if connection.execute(text("SELECT current_user")).scalar_one() != "asm_migrator":
                raise RuntimeError("Use the dedicated migration identity")
            connection.execute(text("SELECT pg_advisory_xact_lock(1947060900)"))
            context.configure(connection=connection, target_metadata=None, version_table_schema="platform")
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


migrate()
