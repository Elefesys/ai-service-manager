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
counter_dir="$tmp/m2-counters"
python3 -c 'import secrets,sys; sys.stdout.write(secrets.token_urlsafe(32))' > "$password_file"
mkdir "$counter_dir"
python3 - "$counter_dir" "$tmp/.env" "$password_file" <<'PY'
import os
import stat
import sys

directory = os.stat(sys.argv[1], follow_symlinks=False)
assert stat.S_ISDIR(directory.st_mode)
assert directory.st_uid == os.getuid() and directory.st_gid == os.getgid()
assert stat.S_IMODE(directory.st_mode) == 0o700
for path in sys.argv[2:]:
    value = os.stat(path, follow_symlinks=False)
    assert stat.S_ISREG(value.st_mode)
    assert value.st_uid == os.getuid() and value.st_gid == os.getgid()
    assert stat.S_IMODE(value.st_mode) == 0o600
PY
compose_model="$tmp/compose.json"
docker compose --env-file "$tmp/.env" -f compose.yaml -f compose.browser.yaml --profile browser config -q
docker compose --env-file "$tmp/.env" -f compose.yaml -f compose.browser.yaml --profile browser config --format json > "$compose_model"
python3 scripts/check_browser_compose.py "$compose_model"
docker compose --env-file "$tmp/.env" -f compose.yaml -f compose.browser.yaml --profile browser up -d --build postgres migrate storage storage-init api frontend
docker compose --env-file "$tmp/.env" -f compose.yaml -f compose.browser.yaml --profile browser build browser-provision browser-runtime
docker compose --env-file "$tmp/.env" -f compose.yaml -f compose.browser.yaml --profile browser run --no-deps --rm -T --user "$(id -u):$(id -g)" -v "$password_file:/run/browser-password:ro" browser-provision python scripts/provision_browser_test.py --password-file /run/browser-password > "$tmp/fixture.json"
docker compose --env-file "$tmp/.env" -f compose.yaml -f compose.browser.yaml --profile browser run --no-deps --rm -T --user "$(id -u):$(id -g)" -v "$counter_dir:/run/m2-browser-counters:rw" browser-runtime python scripts/m2_4_browser_worker.py --action seed
docker compose --env-file "$tmp/.env" -f compose.yaml -f compose.browser.yaml --profile browser run --no-deps --rm -T --user "$(id -u):$(id -g)" browser-provision python scripts/m2_4_browser_fixture.py --action inventory > "$tmp/messaging.json"
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
ASM_BROWSER_FIXTURE_FILE="$tmp/fixture.json" ASM_BROWSER_MESSAGING_FILE="$tmp/messaging.json" ASM_BROWSER_COUNTER_DIR="$counter_dir" ASM_BROWSER_ENV_FILE="$tmp/.env" ASM_BROWSER_LOGIN=browser.owner ASM_BROWSER_PASSWORD_FILE="$password_file" npm --prefix frontend run test:e2e
