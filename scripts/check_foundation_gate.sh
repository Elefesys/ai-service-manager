#!/bin/sh
set -eu
if [ "$#" -ne 2 ]; then
    printf 'Usage: sh scripts/check_foundation_gate.sh CORE_RESULT EGRESS_RESULT\n' >&2
    exit 2
fi
result() {
    case "$1" in
        success|failure|cancelled|skipped) printf '%s' "$1" ;;
        '') printf 'empty' ;;
        *) printf 'unknown' ;;
    esac
}
core_result=$(result "$1")
egress_result=$(result "$2")
printf 'FOUNDATION_CORE_RESULT=%s\nFOUNDATION_EGRESS_RESULT=%s\n' "$core_result" "$egress_result"
if [ "$core_result" != success ] || [ "$egress_result" != success ]; then
    printf 'FOUNDATION_GATE_REFUSED\n' >&2
    exit 1
fi
printf 'FOUNDATION_GATE_RESULTS_PASS\n'
