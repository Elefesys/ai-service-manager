#!/bin/sh
set -eu
phase_child=
run_phase() {
    label=$1; shift
    python scripts/native_context_db_catalog.py foundation-step backend "$label" -- "$@" <&3 3<&- &
    phase_child=$!
    if wait "$phase_child"; then phase_status=0; else phase_status=$?; fi
    phase_child=
    return "$phase_status"
} 3<&0
signal_phase() {
    if [ -n "$phase_child" ]; then
        kill -"$1" "$phase_child" 2>/dev/null || :
        wait "$phase_child" || :
    fi
    exit "$2"
}
trap 'signal_phase INT 130' INT
trap 'signal_phase TERM 143' TERM
run_phase ruff ruff check backend tests scripts migrations
run_phase format ruff format --check --diff backend tests scripts migrations
run_phase mypy mypy backend/src
run_phase unit pytest -q --durations=20 -m 'not integration'
run_phase upgrade alembic upgrade head
run_phase repeat-upgrade alembic upgrade head
run_phase generic python scripts/native_context_db_catalog.py generic-integration
run_phase downgrade alembic downgrade base
run_phase reupgrade alembic upgrade head
run_phase contracts python scripts/export_contracts.py --check
export SOURCE_DATE_EPOCH=315532800
run_phase wheel-one python -m build --wheel --no-isolation --outdir /tmp/wheel-one
run_phase wheel-two python -m build --wheel --no-isolation --outdir /tmp/wheel-two
run_phase wheel-compare cmp /tmp/wheel-one/*.whl /tmp/wheel-two/*.whl
run_phase wheel-hash sha256sum /tmp/wheel-one/*.whl
