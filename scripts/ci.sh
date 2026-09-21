#!/bin/sh
set -eu
python3 scripts/init_local.py
compose() { docker compose --env-file infra/images.lock.env --env-file .env --profile test "$@"; }
cleanup() { compose down --remove-orphans; }
trap cleanup EXIT
compose config --quiet
# Verify the new LOCAL/TEST service release manifests while its pins are introduced.
docker buildx imagetools inspect quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z
docker buildx imagetools inspect quay.io/minio/mc:RELEASE.2025-02-15T10-36-16Z
compose build --pull api checks frontend
compose run --rm checks
compose run --rm --no-deps --entrypoint minio storage --version
compose run --rm --no-deps --entrypoint mc storage-init --version
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
