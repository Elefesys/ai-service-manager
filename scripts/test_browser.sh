#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
root="$(pwd)"
. ./infra/images.lock.env
export DB_IMAGE NODE_IMAGE WEB_IMAGE UV_IMAGE PYTHON_IMAGE STORAGE_IMAGE STORAGE_ADMIN_IMAGE
umask 077
tmp="$(mktemp -d)"
mkdir -m 700 "$tmp/private" "$tmp/evidence"
step() {
  label="$1"
  budget="$2"
  shift 2
  python3 - "$tmp" "$label" "$budget" "$@" <<'PY_STEP'
import sys
from pathlib import Path
from scripts.m4_runtime_db import phase
try:
    phase(Path(sys.argv[1]), sys.argv[2], sys.argv[4:], int(sys.argv[3]),
          separate_stdout=sys.argv[2] in {"provision", "fixture-inventory"})
except Exception:
    raise SystemExit(1) from None
PY_STEP
}
cleanup() {
  status=$?
  trap - EXIT INT TERM
  python3 - "$tmp" <<'PY_DIAG' || true
import sys
from pathlib import Path
from scripts.m4_runtime_db import stack_diagnostics
root = Path(sys.argv[1])
stack_diagnostics(root, ['docker', 'compose', '--env-file', str(root / 'private/test.env'), '-f', 'compose.yaml', '-f', 'compose.browser.yaml'])
PY_DIAG
  cleanup_status=0
  step cleanup 60 docker compose --env-file "$tmp/private/test.env" -f compose.yaml -f compose.browser.yaml down -v --remove-orphans --timeout 10 || cleanup_status=$?
  mkdir -p reports/browser-lifecycle
  cp -R "$tmp/evidence/." reports/browser-lifecycle/ || cleanup_status=1
  rm -rf "$tmp"
  if [ "$status" -ne 0 ]; then exit "$status"; fi
  exit "$cleanup_status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
(cd "$tmp/private" && python3 "$root/scripts/init_local.py" >/dev/null)
mv "$tmp/private/.env" "$tmp/private/test.env"
. "$tmp/private/test.env"
export PG_ADMIN_PASSWORD PG_MIGRATION_PASSWORD PG_RUNTIME_PASSWORD
password_file="$tmp/private/browser-password"
counter_dir="$tmp/m2-counters"
python3 -c 'import secrets,sys; sys.stdout.write(secrets.token_urlsafe(32))' > "$password_file"
python3 - "$tmp/private/test.env" "$password_file" <<'PY_SECRET'
from pathlib import Path
import sys
with Path(sys.argv[1]).open('a') as stream:
    stream.write('ASM_TEST_PASSWORD=' + Path(sys.argv[2]).read_text() + '\n')
PY_SECRET
mkdir "$counter_dir"
python3 - "$counter_dir" "$tmp/private/test.env" "$password_file" <<'PY'
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
docker compose --env-file "$tmp/private/test.env" -f compose.yaml -f compose.browser.yaml --profile browser config -q
docker compose --env-file "$tmp/private/test.env" -f compose.yaml -f compose.browser.yaml --profile browser config --format json > "$compose_model"
python3 scripts/check_browser_compose.py "$compose_model"
step application-build 600 docker compose --env-file "$tmp/private/test.env" -f compose.yaml -f compose.browser.yaml --profile browser build migrate storage storage-init api frontend
step startup 180 docker compose --env-file "$tmp/private/test.env" -f compose.yaml -f compose.browser.yaml --profile browser up -d --no-build postgres migrate storage storage-init api frontend
step fixture-build 420 docker compose --env-file "$tmp/private/test.env" -f compose.yaml -f compose.browser.yaml --profile browser build browser-provision browser-runtime
step provision 90 docker compose --env-file "$tmp/private/test.env" -f compose.yaml -f compose.browser.yaml --profile browser run --no-deps --rm -T --user "$(id -u):$(id -g)" -v "$password_file:/run/browser-password:ro" browser-provision python scripts/provision_browser_test.py --password-file /run/browser-password
cp "$tmp/private/provision.stdout" "$tmp/fixture.json"
step worker-seed 90 docker compose --env-file "$tmp/private/test.env" -f compose.yaml -f compose.browser.yaml --profile browser run --no-deps --rm -T --user "$(id -u):$(id -g)" -v "$counter_dir:/run/m2-browser-counters:rw" browser-runtime python scripts/m2_4_browser_worker.py --action seed
step fixture-inventory 90 docker compose --env-file "$tmp/private/test.env" -f compose.yaml -f compose.browser.yaml --profile browser run --no-deps --rm -T --user "$(id -u):$(id -g)" browser-provision python scripts/m2_4_browser_fixture.py --action inventory
cp "$tmp/private/fixture-inventory.stdout" "$tmp/messaging.json"
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
ASM_BROWSER_FIXTURE_FILE="$tmp/fixture.json" ASM_BROWSER_MESSAGING_FILE="$tmp/messaging.json" ASM_BROWSER_COUNTER_DIR="$counter_dir" ASM_BROWSER_ENV_FILE="$tmp/private/test.env" ASM_BROWSER_LOGIN=browser.owner ASM_BROWSER_PASSWORD_FILE="$password_file" step browser-tests 600 npm --prefix frontend run test:e2e
