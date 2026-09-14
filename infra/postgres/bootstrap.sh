#!/bin/sh
set -eu
# LOCAL/TEST only. Values are quoted by psql, never concatenated into SQL.
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --single-transaction \
  --set=ON_ERROR_STOP=1 --set=db_name="$POSTGRES_DB" \
  --set=migration_password="$ASM_MIGRATION_PASSWORD" \
  --set=runtime_password="$ASM_RUNTIME_PASSWORD" <<'SQL'
CREATE ROLE asm_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'migration_password';
CREATE ROLE asm_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD :'runtime_password';
REVOKE ALL ON DATABASE :"db_name" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"db_name" TO asm_migrator, asm_runtime;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
CREATE SCHEMA platform AUTHORIZATION asm_migrator;
CREATE SCHEMA app AUTHORIZATION asm_migrator;
CREATE SCHEMA extensions;
CREATE EXTENSION vector WITH SCHEMA extensions VERSION '0.8.6';
GRANT USAGE ON SCHEMA extensions TO asm_migrator, asm_runtime;
ALTER ROLE asm_runtime IN DATABASE :"db_name" SET search_path = pg_catalog, app, extensions;
ALTER ROLE asm_migrator IN DATABASE :"db_name" SET search_path = pg_catalog, platform, app, extensions;
ALTER ROLE asm_runtime IN DATABASE :"db_name" SET timezone = 'UTC';
ALTER ROLE asm_runtime IN DATABASE :"db_name" SET statement_timeout = '5s';
ALTER ROLE asm_runtime IN DATABASE :"db_name" SET lock_timeout = '2s';
ALTER ROLE asm_runtime IN DATABASE :"db_name" SET idle_in_transaction_session_timeout = '10s';
SQL
