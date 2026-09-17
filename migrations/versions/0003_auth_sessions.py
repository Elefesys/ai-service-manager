"""M1.2 auth-only tables and narrow runtime functions; pre-DDL contract required."""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

RUNTIME_FUNCTIONS = (
    "auth_password_lookup(text)",
    "auth_bootstrap(text, integer)",
    "auth_session(text)",
    "auth_memberships(text)",
    "auth_login(text, uuid, bigint, bigint, text, integer)",
    "auth_rotate(text, text)",
    "auth_logout(text)",
)


def upgrade() -> None:
    op.execute("""
        CREATE TABLE platform.auth_credentials (
            user_account_id uuid PRIMARY KEY
                REFERENCES platform.user_accounts(id) ON DELETE RESTRICT,
            login text NOT NULL UNIQUE CHECK (login ~ '^[a-z0-9][a-z0-9._-]{2,63}$'),
            password_hash text NOT NULL CHECK (
                length(password_hash) BETWEEN 50 AND 512 AND
                password_hash LIKE '$argon2id$v=19$%'),
            version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
            created_at timestamptz NOT NULL DEFAULT clock_timestamp()
        )
    """)
    op.execute("""
        CREATE TABLE platform.auth_sessions (
            token_hash text PRIMARY KEY CHECK (token_hash ~ '^[0-9a-f]{64}$'),
            user_account_id uuid REFERENCES platform.user_accounts(id) ON DELETE RESTRICT,
            credential_version bigint CHECK (credential_version > 0),
            account_version bigint CHECK (account_version > 0),
            created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            expires_at timestamptz NOT NULL,
            revoked_at timestamptz,
            CHECK (expires_at > created_at),
            CHECK ((user_account_id IS NULL AND credential_version IS NULL AND account_version IS NULL)
                OR (user_account_id IS NOT NULL AND credential_version IS NOT NULL AND account_version IS NOT NULL))
        )
    """)
    op.execute("CREATE INDEX auth_sessions_account_idx ON platform.auth_sessions(user_account_id)")
    op.execute("CREATE INDEX auth_sessions_expiry_idx ON platform.auth_sessions(expires_at)")
    op.execute("""
        REVOKE ALL ON platform.auth_credentials, platform.auth_sessions FROM PUBLIC, asm_runtime
    """)
    op.execute("""
        CREATE FUNCTION platform.auth_password_lookup(p_login text)
        RETURNS TABLE(user_account_id uuid, password_hash text, credential_version bigint, account_version bigint)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp
        AS $$
            SELECT c.user_account_id, c.password_hash, c.version, a.version
            FROM platform.auth_credentials c JOIN platform.user_accounts a ON a.id=c.user_account_id
            WHERE c.login=p_login AND a.status='ACTIVE'
        $$
    """)
    # Internal helper, NOT executable by runtime. All authenticated paths lock in
    # account -> credential -> session order. Recheck the row after waiting.
    op.execute("""
        CREATE FUNCTION platform.auth_lock_session(p_hash text, p_exclusive boolean)
        RETURNS platform.auth_sessions
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, pg_temp
        AS $$
        DECLARE
            candidate platform.auth_sessions%ROWTYPE;
            locked platform.auth_sessions%ROWTYPE;
            account_row platform.user_accounts%ROWTYPE;
            credential_revision bigint;
        BEGIN
            SELECT * INTO candidate FROM platform.auth_sessions WHERE token_hash=p_hash;
            IF NOT FOUND THEN RETURN NULL; END IF;
            IF candidate.user_account_id IS NOT NULL THEN
                SELECT * INTO account_row FROM platform.user_accounts
                    WHERE id=candidate.user_account_id FOR SHARE;
                IF NOT FOUND OR account_row.status <> 'ACTIVE' THEN RETURN NULL; END IF;
                SELECT version INTO credential_revision FROM platform.auth_credentials
                    WHERE user_account_id=candidate.user_account_id FOR SHARE;
                IF NOT FOUND THEN RETURN NULL; END IF;
            END IF;
            IF p_exclusive THEN
                SELECT * INTO locked FROM platform.auth_sessions WHERE token_hash=p_hash FOR UPDATE;
            ELSE
                SELECT * INTO locked FROM platform.auth_sessions WHERE token_hash=p_hash FOR SHARE;
            END IF;
            IF NOT FOUND OR locked.revoked_at IS NOT NULL OR locked.expires_at <= clock_timestamp()
                OR locked.user_account_id IS DISTINCT FROM candidate.user_account_id THEN
                RETURN NULL;
            END IF;
            IF locked.user_account_id IS NOT NULL AND
               (locked.account_version IS DISTINCT FROM account_row.version OR
                locked.credential_version IS DISTINCT FROM credential_revision) THEN
                RETURN NULL;
            END IF;
            RETURN locked;
        END
        $$
    """)
    op.execute("""
        CREATE FUNCTION platform.auth_bootstrap(p_hash text, p_ttl integer)
        RETURNS timestamptz
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, pg_temp
        AS $$
        DECLARE issued timestamptz := clock_timestamp();
        BEGIN
            IF p_ttl IS NULL OR p_ttl NOT BETWEEN 1 AND 900 THEN
                RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Invalid auth configuration';
            END IF;
            INSERT INTO platform.auth_sessions(token_hash, created_at, expires_at)
                VALUES (p_hash, issued, issued + make_interval(secs => p_ttl));
            RETURN issued + make_interval(secs => p_ttl);
        END
        $$
    """)
    op.execute("""
        CREATE FUNCTION platform.auth_session(p_hash text)
        RETURNS TABLE(user_account_id uuid, expires_at timestamptz)
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, pg_temp
        AS $$
        DECLARE locked platform.auth_sessions%ROWTYPE;
        BEGIN
            locked := platform.auth_lock_session(p_hash, false);
            IF locked.token_hash IS NOT NULL THEN
                RETURN QUERY SELECT locked.user_account_id, locked.expires_at;
            END IF;
        END
        $$
    """)
    op.execute("""
        CREATE FUNCTION platform.auth_memberships(p_hash text)
        RETURNS TABLE(workspace_id uuid, role text)
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, pg_temp
        AS $$
        DECLARE locked platform.auth_sessions%ROWTYPE;
        BEGIN
            locked := platform.auth_lock_session(p_hash, false);
            IF locked.user_account_id IS NULL THEN RETURN; END IF;
            RETURN QUERY
                SELECT wm.workspace_id, wm.role
                FROM platform.workspace_memberships wm
                JOIN platform.workspaces w ON w.id=wm.workspace_id
                WHERE wm.user_account_id=locked.user_account_id
                  AND wm.status='ACTIVE' AND w.status='ACTIVE'
                ORDER BY wm.workspace_id FOR SHARE OF wm, w;
        END
        $$
    """)
    op.execute("""
        CREATE FUNCTION platform.auth_login(
            p_previous text, p_account uuid, p_account_version bigint,
            p_credential_version bigint, p_new text, p_ttl integer)
        RETURNS timestamptz
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, pg_temp
        AS $$
        DECLARE
            actual_account_version bigint;
            actual_credential_version bigint;
            previous platform.auth_sessions%ROWTYPE;
            issued timestamptz;
        BEGIN
            IF p_ttl IS NULL OR p_ttl NOT BETWEEN 1 AND 86400 THEN
                RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Invalid auth configuration';
            END IF;
            SELECT version INTO actual_account_version FROM platform.user_accounts
                WHERE id=p_account AND status='ACTIVE' FOR SHARE;
            IF NOT FOUND OR actual_account_version IS DISTINCT FROM p_account_version THEN RETURN NULL; END IF;
            SELECT version INTO actual_credential_version FROM platform.auth_credentials
                WHERE user_account_id=p_account FOR SHARE;
            IF NOT FOUND OR actual_credential_version IS DISTINCT FROM p_credential_version THEN RETURN NULL; END IF;
            previous := platform.auth_lock_session(p_previous, true);
            IF previous.token_hash IS NULL OR previous.user_account_id IS NOT NULL THEN RETURN NULL; END IF;
            issued := clock_timestamp();
            UPDATE platform.auth_sessions SET revoked_at=issued WHERE token_hash=p_previous;
            INSERT INTO platform.auth_sessions(
                token_hash, user_account_id, credential_version, account_version, created_at, expires_at)
                VALUES (p_new, p_account, p_credential_version, p_account_version,
                    issued, issued + make_interval(secs => p_ttl));
            RETURN issued + make_interval(secs => p_ttl);
        END
        $$
    """)
    op.execute("""
        CREATE FUNCTION platform.auth_rotate(p_previous text, p_new text)
        RETURNS timestamptz
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, pg_temp
        AS $$
        DECLARE previous platform.auth_sessions%ROWTYPE; issued timestamptz;
        BEGIN
            previous := platform.auth_lock_session(p_previous, true);
            IF previous.user_account_id IS NULL THEN RETURN NULL; END IF;
            issued := clock_timestamp();
            IF previous.expires_at <= issued THEN RETURN NULL; END IF;
            UPDATE platform.auth_sessions SET revoked_at=issued WHERE token_hash=p_previous;
            INSERT INTO platform.auth_sessions(
                token_hash, user_account_id, credential_version, account_version, created_at, expires_at)
                VALUES (p_new, previous.user_account_id, previous.credential_version,
                    previous.account_version, issued, previous.expires_at);
            RETURN previous.expires_at;
        END
        $$
    """)
    op.execute("""
        CREATE FUNCTION platform.auth_logout(p_hash text)
        RETURNS boolean
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, pg_temp
        AS $$
        DECLARE previous platform.auth_sessions%ROWTYPE;
        BEGIN
            previous := platform.auth_lock_session(p_hash, true);
            IF previous.user_account_id IS NULL THEN RETURN false; END IF;
            UPDATE platform.auth_sessions SET revoked_at=clock_timestamp() WHERE token_hash=p_hash;
            RETURN true;
        END
        $$
    """)
    for function in (*RUNTIME_FUNCTIONS, "auth_lock_session(text, boolean)"):
        op.execute(f"REVOKE ALL ON FUNCTION platform.{function} FROM PUBLIC, asm_runtime")
    for function in RUNTIME_FUNCTIONS:
        op.execute(f"GRANT EXECUTE ON FUNCTION platform.{function} TO asm_runtime")


def downgrade() -> None:
    # Destructive only on disposable TEST databases; not a production rollback.
    for function in reversed(RUNTIME_FUNCTIONS):
        op.execute(f"DROP FUNCTION platform.{function}")
    op.execute("DROP FUNCTION platform.auth_lock_session(text, boolean)")
    op.execute("DROP TABLE platform.auth_sessions")
    op.execute("DROP TABLE platform.auth_credentials")
