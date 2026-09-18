#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
root="$(pwd)"
. ./infra/images.lock.env
export DB_IMAGE NODE_IMAGE WEB_IMAGE UV_IMAGE PYTHON_IMAGE
umask 077
tmp="$(mktemp -d)"
cleanup() { docker compose --env-file "$tmp/.env" -f compose.yaml -f compose.browser.yaml down -v --remove-orphans >/dev/null 2>&1 || true; rm -rf "$tmp"; }
trap cleanup EXIT INT TERM
(cd "$tmp" && python3 "$root/scripts/init_local.py" >/dev/null)
. "$tmp/.env"
export PG_ADMIN_PASSWORD PG_MIGRATION_PASSWORD PG_RUNTIME_PASSWORD
password_file="$tmp/password"
python3 -c 'import secrets,sys; sys.stdout.write(secrets.token_urlsafe(32))' > "$password_file"
docker compose --env-file "$tmp/.env" -f compose.yaml -f compose.browser.yaml up -d --build postgres migrate api frontend
docker compose --env-file "$tmp/.env" -f compose.yaml -f compose.browser.yaml --profile browser run --rm -T -v "$password_file:/run/browser-password:ro" browser-provision python scripts/provision_browser_test.py --password-file /run/browser-password > "$tmp/fixture.json"
ASM_BROWSER_LOGIN=browser.owner ASM_BROWSER_PASSWORD_FILE="$password_file" npm --prefix frontend run test:e2e
