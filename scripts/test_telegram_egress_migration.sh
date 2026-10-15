#!/bin/sh
# Candidate coordinator. Execute the accepted H lane from unchanged tracked bytes.
set -eu
test "$#" -eq 1
python3 - "$1" <<'PY'
import json
import os
import re
import runpy
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from scripts import prepare_telegram_egress as e

H = '754f1c883e5a94a7fc9e729af2605424f949ba33'
H_TREE = 'b4fdef89583f6bab1c9c96cadb1fbe0c1e5d641f'
# Retention begins before the first source/daemon admission. H remains outside
# the separate whole-T/remaining600 preparation budget; this records whole job stages.
started = time.monotonic()
requested = os.environ.get('GITHUB_SHA', 'NOT_PROVIDED')
if not re.fullmatch('[0-9a-f]{40}', requested):
    requested = 'NOT_PROVIDED'
admission = {'requested_source': requested, 'observed_source': 'NOT_OBSERVED',
             'phase': 'HISTORICAL_CONTROL_COORDINATOR', 'stage': 'admission',
             'budget_state': 'NOT_VALIDATED', 'cleanup': 'NOT_ADMITTED'}
report = e.ROOT / 'reports/migration-coordinator-admission.json'
def retain(primary=None):
    admission['elapsed_seconds'] = time.monotonic() - started
    try:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(admission, indent=2) + '\n')
    except BaseException:
        if primary is None:
            raise
        primary.add_note('CONTROL_OUTER_REPORT_FAILED')
        print('CONTROL_OUTER_REPORT_FAILED', flush=True)
primary = None
retain()
try:
    os.umask(0o077)
    assert os.getuid() != 0 and Path.cwd() == e.ROOT, 'MIGRATION_DISPOSABLE_CHECKOUT_REQUIRED'
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'MIGRATION_DISPOSABLE_RUNNER_REQUIRED'
    fault = sys.argv[1]
    assert fault in {'intent', 'image', 'state'}, 'MIGRATION_KNOWN_SHARD_REQUIRED'
    admission['stage'] = 'observe_source'
    source = e.command(['git', 'rev-parse', 'HEAD']).decode().strip()
    admission['observed_source'] = source
    admission['stage'] = 'source_check'
    e.source_check(source)
    assert not (e.ROOT / '.env').exists(), 'MIGRATION_FRESH_RUNNER_REQUIRED'
    assert not e.command(['docker', 'ps', '-aq']).strip(), 'MIGRATION_EMPTY_DISPOSABLE_DAEMON_REQUIRED'
    assert not e.command(['docker', 'volume', 'ls', '-q']).strip(), 'MIGRATION_EMPTY_DISPOSABLE_VOLUMES_REQUIRED'
    admission['stage'] = 'historical_archive'
    e.command(['git', 'merge-base', '--is-ancestor', H, source])
    assert e.command(['git', 'rev-parse', H + '^{tree}']).decode().strip() == H_TREE
    reports = e.ROOT / 'reports' / 'historical'
    reports.mkdir(parents=True, exist_ok=True)
    (reports / 'source-H.tar.gz').write_bytes(e.command(['git', 'archive', '--format=tar.gz', H]))
    (reports / 'source-P.tar.gz').write_bytes(e.command(['git', 'archive', '--format=tar.gz', e.MIGRATION_FROM]))
    with tempfile.TemporaryDirectory(prefix='asm-frozen-h-') as temp:
        historical = Path(temp) / 'historical'
        subprocess.run(['git', 'worktree', 'add', '--detach', str(historical), H],
                       check=True, capture_output=True, timeout=40, umask=0o022)
        try:
            result = subprocess.run(['sh', 'scripts/test_telegram_egress_migration.sh', fault],
                                    cwd=historical, stdin=subprocess.DEVNULL)
            # H publishes its image/data/receipt proof before its teardown. Preserve
            # that report verbatim; source_sha=H must never be relabelled as I.
            if (historical / 'reports').exists():
                shutil.copytree(historical / 'reports', reports, dirs_exist_ok=True)
            clean = e.command(['git', '-C', str(historical), 'status', '--porcelain', '--untracked-files=all'])
            assert not clean, 'HISTORICAL_SOURCE_CHANGED'
            (reports / 'source-pairing.json').write_text(json.dumps({
                'coordinator': source, 'historical_executor': H, 'historical_tree': H_TREE,
                'historical_clean': True, 'predecessor': e.MIGRATION_FROM,
                'exit_code': result.returncode, 'shard': fault,
            }, indent=2) + '\n')
            assert result.returncode == 0, 'FROZEN_HISTORICAL_ASSERTIONS_FAILED'
            assert not e.command(['docker', 'ps', '-aq']).strip(), 'HISTORICAL_CONTAINERS_REMAIN'
            # The daemon had no volumes/containers before this frozen lane. Remove
            # its exact remaining inventory, including anonymous image VOLUMEs that
            # have no Compose project label. No prune and no pre-existing volumes.
            volumes = e.command(['docker', 'volume', 'ls', '-q']).decode().split()
            if volumes:
                inventory = json.loads(e.command(['docker', 'volume', 'inspect', *volumes]))
                assert {v['Name'] for v in inventory} == set(volumes)
                assert all(v['Driver'] == 'local' and not v.get('Options') for v in inventory)
                (reports / 'disposable-volume-cleanup.json').write_text(json.dumps({
                    'initial_inventory': [], 'containers_after_historical': [],
                    'removed': [{'name': v['Name'], 'labels': v.get('Labels')} for v in inventory],
                }, indent=2) + '\n')
                e.command(['docker', 'volume', 'rm', *volumes])
            assert not e.command(['docker', 'volume', 'ls', '-q']).strip(), 'HISTORICAL_VOLUMES_REMAIN'
        finally:
            e.command(['git', 'worktree', 'remove', str(historical)])
    if fault == 'state':
        admission['stage'] = 'control_coordinator'
        try:
            runpy.run_path(str(e.ROOT / 'tests/test_telegram_egress_migration.py'),
                           init_globals={'control_coordinator_request': {'historical': H, 'candidate': source}},
                           run_name='__control_coordinator__')
        except SystemExit as completed:
            assert completed.code == 0, 'CONTROL_COORDINATOR_EXIT'
        full = json.loads((e.ROOT / 'reports/control-full-retained-negatives.json').read_text())
        assert full['candidate'] == source and full['result'] == 'PASS' and full['count'] == 2
        assert full['results'] == ['timeout', 'export']
        assert full['deadline'] == full['started_at'] + 600 and full['charged_seconds'] < 600
        admission['full_retained_negatives'] = full
        # The GUARDS coordinator executed __control_cleanup_negatives__ in
        # the byte-identical frozen C checkout before preserving/removing it.
        negative = json.loads((e.ROOT / 'reports/retained-control/control-cleanup-negatives.json').read_text())
        assert negative['candidate'] == 'c6a55b6b17d1c1ab286ce97dfa4bd27197141fe5'
        assert negative['result'] == 'PASS' and negative['count'] == 3
        admission['actual_cleanup_negatives'] = negative['results']
        guards = json.loads((e.ROOT / 'reports/retained-guards/guards-schema-phase.json').read_text())
        assert guards['coordinator'] == 'c502d5fd258aef15bb5549e1529df8d038a4fb9b' and guards['historical'] == negative['candidate']
        assert guards['cleanup']['state'] == 'PASS'
        assert guards['prepare_budget']['charged_total_seconds'] < 600
        admission['guards_schema'] = {'source': guards['coordinator'], 'revision': '0010', 'report': 'retained-guards/guards-schema-phase.json'}
        escalation = json.loads((e.ROOT / 'reports/retained-escalation/escalation-schema-phase.json').read_text())
        assert escalation['coordinator'] == '933ddd284ff5b77fb1aa88a4270ab0032bc499c9' and escalation['historical'] == guards['coordinator']
        assert escalation['cleanup']['state'] == 'PASS'
        assert escalation['prepare_budget']['charged_total_seconds'] < 600
        assert escalation['database']['populated_refusal'] == 'PASS'
        assert len(escalation['database']['timers']) == 3
        admission['escalation_schema'] = {'source': escalation['coordinator'], 'revision': '0011', 'report': 'retained-escalation/escalation-schema-phase.json'}
        material = json.loads((e.ROOT / 'reports/material-schema-phase.json').read_text())
        assert material['coordinator'] == source and material['historical'] == escalation['coordinator']
        assert material['cleanup']['state'] == 'PASS' and material['database']['populated_refusal'] == 'PASS'
        budget = material['prepare_budget']
        assert budget['started_at'] == escalation['prepare_budget']['started_at']
        assert budget['deadline'] == escalation['prepare_budget']['deadline'] == budget['started_at'] + 600
        assert budget['issued_at'] >= escalation['started_at'] + escalation['total_seconds']
        assert budget['charged_total_seconds'] < 600
        assert material['upgrade_ack_loss']['observed']['revision'] == '0012'
        assert material['upgrade_ack_loss']['recovery_source'] == source
        assert material['downgrade_ack_loss']['observed']['revision'] == '0011'
        assert material['downgrade_ack_loss']['recovery_source'] == escalation['coordinator']
        assert material['used_recovery']['source'] == source
        assert material['database']['refusal']['before_ddl'] and material['database']['refusal']['tables'] == 42
        admission['material_schema'] = {'source': source, 'revision': '0012', 'report': 'material-schema-phase.json'}
    assert not e.command(['git', 'status', '--porcelain', '--untracked-files=all']).strip()
    print('TELEGRAM_EGRESS_MIGRATION_DISPOSABLE_PASS', flush=True)
except BaseException as error:
    primary = error
    reason = str(error)
    if not re.fullmatch('(?:CONTROL|EGRESS|FROZEN|HISTORICAL|MIGRATION|MATERIAL)_[A-Z0-9_]{1,100}', reason):
        reason = 'CONTROL_' + type(error).__name__.upper()
    admission['failure'] = {'type': type(error).__name__, 'reason': reason, 'stage': admission['stage']}
    raise
finally:
    retain(primary)

PY
