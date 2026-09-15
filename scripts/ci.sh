#!/bin/sh
set -eu
python3 scripts/init_local.py
compose() { docker compose --env-file infra/images.lock.env --env-file .env --profile test "$@"; }
cleanup() { compose down --remove-orphans; }
trap cleanup EXIT
compose config --quiet
compose build --pull api checks frontend
compose run --rm checks
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
