"""M1.1 six-table tenant foundation; see the pre-DDL C1 contract."""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE platform.user_accounts (
            id uuid PRIMARY KEY DEFAULT pg_catalog.uuidv7(),
            status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'DISABLED')),
            version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("""
        CREATE TABLE platform.workspaces (
            id uuid PRIMARY KEY DEFAULT pg_catalog.uuidv7(),
            status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'ARCHIVED')),
            version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("""
        CREATE TABLE platform.workspace_memberships (
            workspace_id uuid NOT NULL REFERENCES platform.workspaces(id) ON DELETE RESTRICT,
            user_account_id uuid NOT NULL REFERENCES platform.user_accounts(id) ON DELETE RESTRICT,
            role text NOT NULL CHECK (role IN ('OWNER', 'ADMIN', 'PROVIDER')),
            status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'REVOKED')),
            version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (workspace_id, user_account_id)
        )
    """)
    op.execute("""
        CREATE INDEX workspace_memberships_account_idx
        ON platform.workspace_memberships (user_account_id, workspace_id)
    """)
    op.execute("""
        CREATE TABLE app.businesses (
            workspace_id uuid NOT NULL REFERENCES platform.workspaces(id) ON DELETE RESTRICT,
            id uuid NOT NULL DEFAULT pg_catalog.uuidv7(),
            name text NOT NULL CHECK (name = btrim(name) AND length(name) BETWEEN 1 AND 200),
            status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'ARCHIVED')),
            version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (workspace_id, id)
        )
    """)
    op.execute("""
        CREATE TABLE app.business_members (
            workspace_id uuid NOT NULL REFERENCES platform.workspaces(id) ON DELETE RESTRICT,
            id uuid NOT NULL DEFAULT pg_catalog.uuidv7(),
            business_id uuid NOT NULL,
            user_account_id uuid,
            name text NOT NULL CHECK (name = btrim(name) AND length(name) BETWEEN 1 AND 200),
            role text NOT NULL CHECK (role IN ('OWNER', 'ADMIN', 'PROVIDER')),
            status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'ARCHIVED')),
            version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (workspace_id, id),
            FOREIGN KEY (workspace_id, business_id)
                REFERENCES app.businesses(workspace_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (workspace_id, user_account_id)
                REFERENCES platform.workspace_memberships(workspace_id, user_account_id)
                ON DELETE RESTRICT,
            UNIQUE (workspace_id, business_id, user_account_id)
        )
    """)
    op.execute("""
        CREATE INDEX business_members_account_idx
        ON app.business_members (workspace_id, user_account_id)
    """)
    op.execute("""
        CREATE TABLE app.locations (
            workspace_id uuid NOT NULL REFERENCES platform.workspaces(id) ON DELETE RESTRICT,
            id uuid NOT NULL DEFAULT pg_catalog.uuidv7(),
            business_id uuid NOT NULL,
            name text NOT NULL CHECK (name = btrim(name) AND length(name) BETWEEN 1 AND 200),
            status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'ARCHIVED')),
            version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (workspace_id, id),
            FOREIGN KEY (workspace_id, business_id)
                REFERENCES app.businesses(workspace_id, id) ON DELETE RESTRICT
        )
    """)
    op.execute("CREATE INDEX locations_business_idx ON app.locations (workspace_id, business_id)")
    # No runtime grants on platform identity tables, even before RLS context exists.
    op.execute("""
        CREATE FUNCTION platform.resolve_workspace_membership(actor_id uuid, target_workspace_id uuid)
        RETURNS text LANGUAGE sql VOLATILE SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            SELECT wm.role
            FROM platform.workspace_memberships AS wm
            JOIN platform.user_accounts AS ua ON ua.id = wm.user_account_id
            JOIN platform.workspaces AS w ON w.id = wm.workspace_id
            WHERE wm.user_account_id = actor_id AND wm.workspace_id = target_workspace_id
              AND wm.status = 'ACTIVE' AND ua.status = 'ACTIVE' AND w.status = 'ACTIVE'
            FOR SHARE OF wm, ua, w
        $$
    """)
    op.execute("""
        CREATE FUNCTION app.current_workspace_id()
        RETURNS uuid LANGUAGE plpgsql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
        DECLARE
            workspace uuid;
            actor uuid;
            correlation uuid;
            current_xid text;
        BEGIN
            current_xid := pg_current_xact_id_if_assigned()::text;
            IF current_xid IS NULL OR
               current_setting('asm.context_xid', true) IS DISTINCT FROM current_xid THEN
                RETURN NULL;
            END IF;
            workspace := NULLIF(current_setting('asm.workspace_id', true), '')::uuid;
            actor := NULLIF(current_setting('asm.actor_id', true), '')::uuid;
            correlation := NULLIF(current_setting('asm.correlation_id', true), '')::uuid;
            IF workspace IS NULL OR actor IS NULL OR correlation IS NULL OR
               current_setting('asm.actor_kind', true) IS DISTINCT FROM 'user_account' THEN
                RETURN NULL;
            END IF;
            IF EXISTS (
                SELECT 1 FROM platform.workspace_memberships AS wm
                JOIN platform.user_accounts AS ua ON ua.id = wm.user_account_id
                JOIN platform.workspaces AS w ON w.id = wm.workspace_id
                WHERE wm.workspace_id = workspace AND wm.user_account_id = actor
                  AND wm.status = 'ACTIVE' AND ua.status = 'ACTIVE' AND w.status = 'ACTIVE'
            ) THEN
                RETURN workspace;
            END IF;
            RETURN NULL;
        EXCEPTION WHEN invalid_text_representation THEN
            RETURN NULL;
        END
        $$
    """)
    for function in (
        "platform.resolve_workspace_membership(uuid, uuid)",
        "app.current_workspace_id()",
    ):
        # Explicit revocation also covers PostgreSQL's global default PUBLIC execute.
        op.execute(f"REVOKE ALL ON FUNCTION {function} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {function} TO asm_runtime")
    for table in ("businesses", "business_members", "locations"):
        op.execute(f"ALTER TABLE app.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE app.{table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY workspace_isolation ON app.{table} TO asm_runtime
            USING (workspace_id = (SELECT app.current_workspace_id()))
            WITH CHECK (workspace_id = (SELECT app.current_workspace_id()))
        """)
        op.execute(f"""
            CREATE POLICY migration_access ON app.{table} TO asm_migrator
            USING (true) WITH CHECK (true)
        """)
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON app.{table} TO asm_runtime")


def downgrade() -> None:
    # Destructive disposable-TEST reversal, not a production rollback procedure.
    for table in ("locations", "business_members", "businesses"):
        op.execute(f"DROP TABLE app.{table}")
    op.execute("DROP FUNCTION app.current_workspace_id()")
    op.execute("DROP FUNCTION platform.resolve_workspace_membership(uuid, uuid)")
    for table in ("workspace_memberships", "workspaces", "user_accounts"):
        op.execute(f"DROP TABLE platform.{table}")
