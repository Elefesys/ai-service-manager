#!/bin/sh
# Explicit disposable lane; never reads an owner's directory, credentials or daemon.
set -eu
test "$#" -eq 1
python3 - "$1" <<'PY'
import os
import json
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

from scripts import prepare_telegram_egress as e

os.umask(0o077)
assert os.getuid() != 0 and Path.cwd() == e.ROOT, 'MIGRATION_DISPOSABLE_CHECKOUT_REQUIRED'
assert os.environ.get('GITHUB_ACTIONS') == 'true', 'MIGRATION_DISPOSABLE_RUNNER_REQUIRED'
fault = sys.argv[1]
assert fault in {'intent', 'image', 'state'}, 'MIGRATION_KNOWN_SHARD_REQUIRED'
source = e.command(['git', 'rev-parse', 'HEAD']).decode().strip()
tree = e.migration_source(source)
assert not (e.ROOT / '.env').exists(), 'MIGRATION_FRESH_RUNNER_REQUIRED'
assert not e.command(['docker', 'ps', '-aq']).strip(), 'MIGRATION_EMPTY_DISPOSABLE_DAEMON_REQUIRED'
assert not e.command(['docker', 'volume', 'ls', '-q']).strip(), 'MIGRATION_EMPTY_DISPOSABLE_VOLUMES_REQUIRED'
with tempfile.TemporaryDirectory(prefix='asm-connect5-source-') as temp:
    # Round-trip the owner draft's literal PowerShell -> SSH-command/stdin -> sh
    # protocol through a LOCAL shim. No SSH client or network connection is used.
    capture = Path(temp) / 'capture.py'
    shim = Path(temp) / 'ssh-argv-probe.py'
    expected = ['migration-resume', '--accepted-sha', source, '--from-sha', e.MIGRATION_FROM,
                '--state-dir', '/home/fixture/private-state']
    e.write_private(capture, ('import sys\nassert sys.argv[1:] == ' + repr(expected)
                             + '\nprint("MIGRATION_OWNER_ARGV_PASS")\n').encode())
    e.write_private(shim, b"import subprocess,sys\nassert sys.argv[1:] == ['-T','synthetic.invalid','sh -s -- migration-resume']\nsubprocess.run(['sh','-s','--','migration-resume'],input=sys.stdin.buffer.read(),check=True)\n")
    shell_text = 'set -eu\naction=${1:?}\n' + shlex.join(['python3', str(capture)]) + ' "$action" ' + shlex.join(expected[1:]) + '\n'
    powershell = "$ErrorActionPreference = 'Stop'\n$payload = @'\n" + shell_text + "'@\n$payload | & python3 '" + str(shim) + "' '-T' 'synthetic.invalid' 'sh -s -- migration-resume'\nif ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }\n"
    checked = subprocess.run(['pwsh', '-NoProfile', '-NonInteractive', '-Command', powershell],
                             capture_output=True, timeout=30, check=True)
    assert checked.stdout.strip() == b'MIGRATION_OWNER_ARGV_PASS'
    reports = e.ROOT / 'reports'
    reports.mkdir(exist_ok=True)
    (reports / 'migration-owner-quoting.json').write_text(json.dumps({
        'source_sha': source, 'posix_argv': 'PASS', 'powershell_literal_stdin': 'PASS',
        'ssh_single_command_argv_local_shim': 'PASS', 'network_calls': 0,
        'script_sha256': e.sha(shell_text.encode())}, indent=2) + '\n')
    print('MIGRATION_OWNER_QUOTING_PASS', flush=True)
    old = Path(temp) / 'predecessor'
    e.command(['git', 'worktree', 'add', '--detach', str(old), e.MIGRATION_FROM])
    try:
        subprocess.run(['python3', 'scripts/init_local.py'], cwd=old, check=True, timeout=30)
        e.write_private(e.ROOT / '.env', (old / '.env').read_bytes(), private_parent=False)
        e.command(['docker', 'compose', '--project-directory', str(old),
            '--env-file', str(old / 'infra/images.lock.env'), '--env-file', str(old / '.env'),
            '-f', str(old / 'compose.yaml'), 'build', '--pull', 'api'], timeout=480)
        # Warm the separately bounded build before the 180s held data fixture.
        # The production preparation subsequently attests and reuses these exact tags.
        with e.migration_budget(600):
            e.migration_build_images(source, tree)
        result = subprocess.run(['sh', 'scripts/test_telegram_egress.sh', '--migration', str(old), fault],
                                stdin=subprocess.DEVNULL, timeout=720)
        assert result.returncode == 0, 'MIGRATION_DISPOSABLE_ASSERTIONS_FAILED'
        assert not e.command(['git', '-C', str(old), 'status', '--porcelain', '--untracked-files=all']).strip()
    finally:
        e.command(['git', 'worktree', 'remove', str(old)])
assert not e.command(['git', 'status', '--porcelain', '--untracked-files=all']).strip()
print('TELEGRAM_EGRESS_MIGRATION_DISPOSABLE_PASS', flush=True)
PY
