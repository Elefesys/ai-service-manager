#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
root="$(pwd)"
. ./infra/images.lock.env
export DB_IMAGE NODE_IMAGE WEB_IMAGE UV_IMAGE PYTHON_IMAGE STORAGE_IMAGE STORAGE_ADMIN_IMAGE
umask 077
tmp="$(mktemp -d)"
cleanup() {
  status=$?
  trap - EXIT INT TERM
  docker compose --env-file "$tmp/.env" -f compose.yaml -f compose.browser.yaml down -v --remove-orphans >/dev/null 2>&1 || true
  rm -rf "$tmp"
  exit "$status"
}
trap cleanup EXIT INT TERM
(cd "$tmp" && python3 "$root/scripts/init_local.py" >/dev/null)
. "$tmp/.env"
export PG_ADMIN_PASSWORD PG_MIGRATION_PASSWORD PG_RUNTIME_PASSWORD
password_file="$tmp/password"
python3 -c 'import secrets,sys; sys.stdout.write(secrets.token_urlsafe(32))' > "$password_file"
python3 -c 'import os,stat,sys; value=os.stat(sys.argv[1], follow_symlinks=False); assert stat.S_ISREG(value.st_mode) and value.st_uid == os.getuid() and value.st_gid == os.getgid() and stat.S_IMODE(value.st_mode) == 0o600' "$password_file"
compose_model="$tmp/compose.json"
docker compose --env-file "$tmp/.env" -f compose.yaml -f compose.browser.yaml --profile browser config -q
docker compose --env-file "$tmp/.env" -f compose.yaml -f compose.browser.yaml --profile browser config --format json > "$compose_model"
python3 scripts/check_browser_compose.py "$compose_model"
docker compose --env-file "$tmp/.env" -f compose.yaml -f compose.browser.yaml --profile browser up -d --build postgres migrate api frontend
docker compose --env-file "$tmp/.env" -f compose.yaml -f compose.browser.yaml --profile browser build browser-provision
docker compose --env-file "$tmp/.env" -f compose.yaml -f compose.browser.yaml --profile browser run --no-deps --rm -T --user "$(id -u):$(id -g)" -v "$password_file:/run/browser-password:ro" browser-provision python scripts/provision_browser_test.py --password-file /run/browser-password > "$tmp/fixture.json"
python3 - <<'PY'
import json
import time
import urllib.request

for attempt in range(30):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8080/health/ready", timeout=2) as response:
            body = json.load(response)
        if response.status == 200 and body == {"status": "ok", "component": "database"}:
            break
    except Exception:
        pass
    if attempt == 29:
        raise SystemExit("Browser stack readiness failed")
    time.sleep(1)
else:
    raise SystemExit("Browser stack readiness failed")
print("BROWSER_STACK_READINESS: PASS")
PY
ASM_BROWSER_FIXTURE_FILE="$tmp/fixture.json" ASM_BROWSER_ENV_FILE="$tmp/.env" ASM_BROWSER_LOGIN=browser.owner ASM_BROWSER_PASSWORD_FILE="$password_file" npm --prefix frontend run test:e2e
