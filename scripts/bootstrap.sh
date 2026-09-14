#!/bin/sh
set -eu
# Explicit M0 initialization or reviewed dependency upgrade, never ordinary CI.
# It changes lockfiles and formats source. Review the resulting Git diff.
sh scripts/pin_images.sh
set -a
. ./infra/images.lock.env
set +a
docker build -f infra/Dockerfile.backend --target toolchain \
  --build-arg PYTHON_IMAGE="$PYTHON_IMAGE" --build-arg UV_IMAGE="$UV_IMAGE" \
  -t asm-toolchain:bootstrap .
docker run --rm --user "$(id -u):$(id -g)" \
  -e UV_CACHE_DIR=/tmp/uv -e HOME=/tmp \
  -v "$PWD:/app" -w /app asm-toolchain:bootstrap uv lock
docker run --rm --user "$(id -u):$(id -g)" \
  -e npm_config_cache=/tmp/npm-cache -e HOME=/tmp \
  -v "$PWD/frontend:/app" -w /app "$NODE_IMAGE" \
  npm install --package-lock-only --ignore-scripts --no-audit --no-fund
docker build -f infra/Dockerfile.backend --target development \
  --build-arg PYTHON_IMAGE="$PYTHON_IMAGE" --build-arg UV_IMAGE="$UV_IMAGE" \
  -t asm-checks:bootstrap .
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e RUFF_CACHE_DIR=/tmp/ruff \
  -v "$PWD:/app" -w /app asm-checks:bootstrap sh -eu -c '
    ruff check --fix backend tests scripts migrations
    ruff format backend tests scripts migrations
    python scripts/export_contracts.py
  '
echo 'Locks, digests and initial schema generated. Review and commit; then run sh scripts/ci.sh.'
