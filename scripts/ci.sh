#!/bin/sh
set -eu
foundation_mode=full
if [ "$#" -ne 0 ]; then
    if [ "$#" -ne 1 ] || [ "$1" != "--foundation-core" ]; then
        printf 'Usage: sh scripts/ci.sh [--foundation-core]\n' >&2
        exit 2
    fi
    foundation_mode=core
fi
phase() { printf 'FOUNDATION_PHASE mode=%s phase=%s event=%s\n' "$foundation_mode" "$1" "$2"; }
phase setup START
python3 scripts/init_local.py
compose() { docker compose --env-file infra/images.lock.env --env-file .env --profile test "$@"; }
cleanup() {
    phase cleanup START
    compose down --remove-orphans
    phase cleanup END
}
trap cleanup EXIT
compose config --quiet
compose build --pull api checks frontend
phase setup END
if [ "$foundation_mode" = full ]; then
    phase egress START
    sh scripts/test_telegram_egress.sh
    phase egress END
fi
phase backend START
compose run --rm checks
phase backend END
phase storage_versions START
compose run --rm --no-deps --entrypoint minio storage --version
compose run --rm --no-deps --entrypoint mc storage-init --version
phase storage_versions END
phase smoke START
compose up -d --wait api worker scheduler frontend
python3 - <<'SMOKE'
import json
import urllib.request
for port in (8000, 8080):
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/health/ready', timeout=5) as response:
        assert json.load(response) == {'status': 'ok', 'component': 'database'}
with urllib.request.urlopen('http://127.0.0.1:8080/ops/', timeout=5) as response:
    assert 'AI Service Manager' in response.read().decode()
print('HTTP and frontend reverse-proxy smoke passed')
SMOKE
compose images
phase smoke END
