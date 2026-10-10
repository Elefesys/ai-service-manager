#!/bin/sh
# Candidate coordinator. Execute the accepted H lane from unchanged tracked bytes.
set -eu
test "$#" -eq 1
python3 - "$1" <<'PY'
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from scripts import prepare_telegram_egress as e

H = '754f1c883e5a94a7fc9e729af2605424f949ba33'
H_TREE = 'b4fdef89583f6bab1c9c96cadb1fbe0c1e5d641f'
os.umask(0o077)
assert os.getuid() != 0 and Path.cwd() == e.ROOT, 'MIGRATION_DISPOSABLE_CHECKOUT_REQUIRED'
assert os.environ.get('GITHUB_ACTIONS') == 'true', 'MIGRATION_DISPOSABLE_RUNNER_REQUIRED'
fault = sys.argv[1]
assert fault in {'intent', 'image', 'state'}, 'MIGRATION_KNOWN_SHARD_REQUIRED'
source = e.command(['git', 'rev-parse', 'HEAD']).decode().strip()
e.source_check(source)
assert not (e.ROOT / '.env').exists(), 'MIGRATION_FRESH_RUNNER_REQUIRED'
assert not e.command(['docker', 'ps', '-aq']).strip(), 'MIGRATION_EMPTY_DISPOSABLE_DAEMON_REQUIRED'
assert not e.command(['docker', 'volume', 'ls', '-q']).strip(), 'MIGRATION_EMPTY_DISPOSABLE_VOLUMES_REQUIRED'
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
    subprocess.run(['sh', 'scripts/test_telegram_egress.sh', '--schema-upgrade', H, source],
                   stdin=subprocess.DEVNULL, check=True)
assert not e.command(['git', 'status', '--porcelain', '--untracked-files=all']).strip()
print('TELEGRAM_EGRESS_MIGRATION_DISPOSABLE_PASS', flush=True)
PY
