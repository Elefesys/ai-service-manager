#!/bin/sh
set -eu
ruff check backend tests scripts migrations
ruff format --check --diff backend tests scripts migrations
mypy backend/src
pytest -q --durations=20 -m 'not integration'
alembic upgrade head
alembic upgrade head
python scripts/native_context_db_catalog.py generic-integration
alembic downgrade base
alembic upgrade head
python scripts/export_contracts.py --check
export SOURCE_DATE_EPOCH=315532800
python -m build --wheel --no-isolation --outdir /tmp/wheel-one
python -m build --wheel --no-isolation --outdir /tmp/wheel-two
cmp /tmp/wheel-one/*.whl /tmp/wheel-two/*.whl
sha256sum /tmp/wheel-one/*.whl
