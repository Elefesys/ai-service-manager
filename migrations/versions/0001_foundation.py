"""M0 infrastructure privileges only; no business tables."""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("GRANT USAGE ON SCHEMA app, platform TO asm_runtime")
    op.execute("GRANT SELECT ON platform.alembic_version TO asm_runtime")
    op.execute("ALTER DEFAULT PRIVILEGES FOR ROLE asm_migrator IN SCHEMA app, platform REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC")


def downgrade() -> None:
    # Disposable M0 test only, never an automatic production rollback.
    op.execute("REVOKE SELECT ON platform.alembic_version FROM asm_runtime")
    op.execute("REVOKE USAGE ON SCHEMA app, platform FROM asm_runtime")
