#!/bin/sh
set -eu
case "$#" in
  0) mode=all ;;
  1) case "$1" in
       --normal-durable) mode=normal-durable ;;
       --foundation-core) mode=foundation-core ;;
       *) echo 'INVALID_FOUNDATION_ROUTE' >&2; exit 2 ;;
     esac ;;
  *) echo 'INVALID_FOUNDATION_ROUTE' >&2; exit 2 ;;
esac

# Admission and private files precede init, Docker resources and test fixtures.
ASM_FOUNDATION_EVIDENCE=$(python3 scripts/native_context_db_catalog.py foundation-prepare "$mode")
ASM_FOUNDATION_OWNER_UID=$(id -u)
ASM_FOUNDATION_BINDING_SHA256=$(sha256sum "$ASM_FOUNDATION_EVIDENCE/binding.json" | cut -d ' ' -f 1)
export ASM_FOUNDATION_EVIDENCE ASM_FOUNDATION_OWNER_UID ASM_FOUNDATION_BINDING_SHA256
if [ "$mode" != all ]; then
    COMPOSE_PROJECT_NAME="asm-foundation-$mode-${ASM_FOUNDATION_EVIDENCE##*-}"
    export COMPOSE_PROJECT_NAME
fi
phase_child=
phase() {
    label=$1; shift
    if [ "$label" = cleanup ]; then
        set -- --owned-cleanup-fd=4 -- "$@"
    else
        set -- -- "$@"
    fi
    python3 scripts/native_context_db_catalog.py foundation-step host "$label" "$@" <&3 3<&- &
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
compose_phase() { label=$1; shift; phase "$label" docker compose --env-file infra/images.lock.env --env-file .env --profile test "$@"; }
phase init python3 scripts/init_local.py
compose_phase config config --quiet
if [ "$mode" != all ]; then
    # Split jobs never adopt the previous job's project/volumes/private state.
    containers=$(docker ps -aq --filter "label=com.docker.compose.project=$COMPOSE_PROJECT_NAME")
    volumes=$(docker volume ls -q --filter "label=com.docker.compose.project=$COMPOSE_PROJECT_NAME")
    networks=$(docker network ls -q --filter "label=com.docker.compose.project=$COMPOSE_PROJECT_NAME")
    test -z "$containers$volumes$networks"
fi
# Fully admit source, evidence and ownership once more before resource work.
# Keep cleanup authority in this parent shell, never recover it from later files.
owned_cleanup=$(python3 scripts/native_context_db_catalog.py foundation-ownership)
readonly owned_cleanup
cleanup() {
    primary=$?
    trap - EXIT INT TERM
    set +e
    compose_phase cleanup down --remove-orphans 4<<OWNED_CLEANUP
$owned_cleanup
OWNED_CLEANUP
    cleanup_status=$?
    python3 scripts/native_context_db_catalog.py foundation-finish "$primary" "$cleanup_status" --owned-cleanup-fd=4 4<<OWNED_CLEANUP
$owned_cleanup
OWNED_CLEANUP
    reporting_status=$?
    result=$primary
    if [ "$result" -eq 0 ]; then result=$cleanup_status; fi
    if [ "$result" -eq 0 ]; then result=$reporting_status; fi
    if [ "$result" -eq 0 ]; then
        # Separate completeness gate; never replace an original nonzero/cancel.
        python3 scripts/native_context_db_catalog.py foundation-check
        result=$?
    fi
    exit "$result"
}
trap cleanup EXIT
trap 'signal_phase INT 130' INT
trap 'signal_phase TERM 143' TERM
compose_phase build build --pull api checks frontend
if [ "$mode" != foundation-core ]; then
    phase normal-durable sh scripts/test_telegram_egress.sh
fi
if [ "$mode" != normal-durable ]; then
    compose_phase checks run --rm \
        --volume "$ASM_FOUNDATION_EVIDENCE:/asm-evidence:rw" \
        -e ASM_FOUNDATION_EVIDENCE=/asm-evidence \
        -e "ASM_FOUNDATION_OWNER_UID=$ASM_FOUNDATION_OWNER_UID" \
        -e "ASM_FOUNDATION_BINDING_SHA256=$ASM_FOUNDATION_BINDING_SHA256" checks
    compose_phase storage-version run --rm --no-deps --entrypoint minio storage --version
    compose_phase storage-admin-version run --rm --no-deps --entrypoint mc storage-init --version
    compose_phase services up -d --wait api worker scheduler frontend
    phase http python3 - <<'SMOKE'
import json
import urllib.request
for port in (8000, 8080):
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/health/ready', timeout=5) as response:
        assert json.load(response) == {'status': 'ok', 'component': 'database'}
with urllib.request.urlopen('http://127.0.0.1:8080/ops/', timeout=5) as response:
    assert 'AI Service Manager' in response.read().decode()
print('HTTP and frontend reverse-proxy smoke passed')
SMOKE
    compose_phase images images
fi
