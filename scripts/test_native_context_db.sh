#!/usr/bin/env bash
# This lane requires a clean event checkout, host Python 3.13 and stock Docker.
# Only the isolated child receives credentials and the disposable-reset opt-in.
set -euo pipefail
umask 077
: "${NATIVE_ROOT:?Set an external runner-temporary directory}"
: "${NATIVE_PYTHON:?Use the Python 3.13 environment installed from frozen uv.lock}"
exec "$NATIVE_PYTHON" scripts/native_context_db_catalog.py run
