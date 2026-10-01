#!/bin/sh
set -eu
# Explicit initialization only. Existing accepted pins are never refreshed here.
mkdir -p infra
touch infra/images.lock.env
cp infra/images.lock.env infra/images.lock.env.tmp
pin() {
  if grep -q "^$1=" infra/images.lock.env; then return; fi
  docker pull "$2"
  digest=$(docker image inspect --format '{{index .RepoDigests 0}}' "$2")
  case "$digest" in *@sha256:*) ;; *) echo 'Missing image digest' >&2; exit 1;; esac
  printf '%s=%s\n' "$1" "$digest" >> infra/images.lock.env.tmp
}
pin PYTHON_IMAGE python:3.13-slim-bookworm
pin UV_IMAGE ghcr.io/astral-sh/uv:0.10.0
pin DB_IMAGE pgvector/pgvector:0.8.6-pg18-bookworm
pin NODE_IMAGE node:24-bookworm-slim
pin WEB_IMAGE nginxinc/nginx-unprivileged:stable-alpine
pin STORAGE_IMAGE ghcr.io/elefesys/asm-minio@sha256:c6c3b418f4b7bbea2f07c4095fc6e59d38ed538a33486f19bb9450a63a6a2efa
pin STORAGE_ADMIN_IMAGE ghcr.io/elefesys/asm-mc@sha256:4da81d17279b9fcdaeee8967c0de4f5d9c7fd589f8022b66e2766b9ac4fe5ce4
mv infra/images.lock.env.tmp infra/images.lock.env
