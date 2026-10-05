#!/bin/sh
# Mandatory synthetic lane. No owner inputs, public Telegram calls or Docker socket mounts.
set -eu
python3 - <<'PY'
import argparse
import ipaddress
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from scripts import prepare_telegram_egress as e

os.umask(0o077)
root = Path.cwd()
assert root == e.ROOT and os.getuid() != 0, 'TEST_RUNNER_CHECKOUT_AND_NONROOT_REQUIRED'
phase = 'identity'
project = 'asm-telegram-egress-test'
processes = []
prefix = None
environment = e.clean_environment()
controls = []
last_control = None

def run(args, timeout=120):
    result = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout, env=environment)
    if result.returncode:
        raise RuntimeError('TEST_COMMAND_FAILED:' + phase)
    return result.stdout

def compose(*args, timeout=120):
    return run([*prefix, *args], timeout)

def phase_start(name):
    global phase
    phase = name
    print('TELEGRAM_EGRESS_TEST_' + name.upper(), flush=True)

def relay_info():
    identity = compose('ps', '-a', '-q', 'telegram-egress').decode().strip()
    assert re.fullmatch('[a-f0-9]{12,64}', identity), 'RELAY_CONTAINER_REQUIRED'
    info = json.loads(run(['docker', 'inspect', identity]))[0]
    assert info['Image'] == state['image_id']
    assert not info['HostConfig']['PortBindings']
    assert not info['HostConfig']['Privileged'] and info['HostConfig']['ReadonlyRootfs']
    assert info['HostConfig']['CapDrop'] == ['ALL']
    assert info['Config']['User'] == f'{os.getuid()}:{os.getgid()}'
    assert all(m['Type'] != 'volume' for m in info['Mounts']), 'NO_ANONYMOUS_WRITABLE_VOLUME'
    assert info['NetworkSettings']['Networks'][values['ASM_TELEGRAM_EGRESS_NETWORK']]['IPAMConfig']['IPv4Address'] == relay_ip
    return identity

def control():
    global last_control
    request_file = directory / 'control-request.json'
    if not request_file.exists():
        return
    request = json.loads(request_file.read_text())
    assert set(request) == {'id', 'action'}
    identity, action = request['id'], request['action']
    assert re.fullmatch('[a-f0-9]{32}', identity) and action in {'stop', 'recreate'}
    if identity == last_control:
        return
    previous = relay_info()
    if action == 'stop':
        compose('stop', '--timeout', '1', 'telegram-egress')
        current = previous
    else:
        compose('up', '-d', '--no-deps', '--pull', 'never', '--force-recreate', 'telegram-egress')
        current = relay_info()
        assert current != previous
        # Wait for the actual listener before returning, without an HTTP request.
        probe = "import socket,time; end=time.monotonic()+8\nwhile True:\n try:\n  s=socket.create_connection(('" + relay_ip + "',443),.3);s.close();break\n except OSError:\n  assert time.monotonic()<end;time.sleep(.1)"
        compose('exec', '-T', 'worker', 'python', '-c', probe)
    response = {'id': identity, 'action': action, 'relay_id': current, 'relay_ip': relay_ip}
    e.write_private(directory / 'control-response.json', e.encoded(response))
    controls.append(response)
    last_control = identity

def await_process(process, *, marker=None, timeout=240):
    deadline = time.monotonic() + timeout
    while process.poll() is None:
        control()
        if marker is not None and marker.exists():
            return
        assert time.monotonic() < deadline, 'TEST_PROCESS_DEADLINE'
        time.sleep(.05)
    assert process.returncode == 0, 'RELAY_POSTGRES_ASSERTION_FAILED'
    assert marker is None or marker.exists(), 'DURABLE_RECEIPT_MISSING'

def start_checks(args):
    # Only bounded synthetic pytest/fixture output is inherited. Never print config/env.
    process = subprocess.Popen([*prefix, 'run', '--rm', '--no-deps', '-T',
        'egress-checks', *args], stdin=subprocess.DEVNULL, env=environment)
    processes.append(process)
    return process

with tempfile.TemporaryDirectory(prefix='asm-telegram-egress-') as temporary:
    directory = Path(temporary)
    try:
        source = run(['git', 'rev-parse', 'HEAD']).decode().strip()
        e.source_check(source)
        run(['docker', 'pull', '--platform', 'linux/amd64', e.IMAGE], 180)
        ids = run(['docker', 'network', 'ls', '-q']).decode().split()
        networks = json.loads(run(['docker', 'network', 'inspect', *ids])) if ids else []
        routes = json.loads(run(['ip', '-j', '-4', 'route', 'show', 'table', 'all']))
        subnet = ipaddress.ip_network(e.select_subnet(networks, routes))
        relay_ip, peer_ip, wire_ip = map(str, (subnet[2], subnet[3], subnet[4]))
        phase_start('synthetic_keys')
        key_output = run(['docker', 'run', '--rm', '--network', 'none', '--read-only',
            '--cap-drop=ALL', '--security-opt=no-new-privileges', '--log-driver=none',
            e.IMAGE, 'x25519']).decode()
        keys = {re.sub('[^a-z]', '', k.lower()): v.strip()
                for k, v in (line.split(':', 1) for line in key_output.splitlines() if ':' in line)}
        private_key = keys['privatekey']
        # Exact 26.9.9 publisher source: "Password (PublicKey): ...".
        public_key = keys['passwordpublickey']
        assert all(re.fullmatch('[A-Za-z0-9_-]{43}', k) for k in (private_key, public_key))
        user_id, short_id = str(uuid4()), '0123456789abcdef'
        profile = {'outbounds': [{'protocol': 'vless', 'settings': {'vnext': [{
            'address': peer_ip, 'port': 8443, 'users': [{'id': user_id,
                'encryption': 'none', 'flow': 'xtls-rprx-vision'}]}]},
            'streamSettings': {'network': 'tcp', 'security': 'reality',
                'realitySettings': {'serverName': 'api.telegram.org', 'fingerprint': 'chrome',
                    'password': public_key, 'shortId': short_id}}}]}
        e.write_private(directory / 'profile.json', e.encoded(profile))
        e.write_private(directory / 'telegram.env', b'ASM_TELEGRAM_ENABLED=false\n')
        state_dir = directory / 'state'
        phase_start('private_prepare')
        e.prepare(argparse.Namespace(accepted_sha=source, profile=str(directory / 'profile.json'),
            state_dir=str(state_dir), telegram_env=str(directory / 'telegram.env'), project=project))
        state = e.verify(state_dir)
        values = e.route_values(state, state_dir)
        assert values['ASM_TELEGRAM_EGRESS_IP'] == relay_ip
        live = e.compose_prefix(state, state_dir)
        base = e.compose_prefix(state, state_dir, overlay=False)
        phase_start('resolved_model')
        e.checked_model(state, state_dir)
        environment.update(ASM_EGRESS_TEST_DIR=str(directory), ASM_EGRESS_PEER_IP=peer_ip,
                           ASM_EGRESS_WIRE_IP=wire_ip)
        prefix = [*live, '-f', str(root / 'infra/telegram-egress/compose.test.yaml'), '--profile', 'test']
        peer = {'log': {'access': 'none', 'error': 'none', 'loglevel': 'none'},
            'inbounds': [{'tag': 'test-peer', 'listen': peer_ip, 'port': 8443,
                'protocol': 'vless', 'settings': {'decryption': 'none',
                    'clients': [{'id': user_id, 'flow': 'xtls-rprx-vision'}]},
                'streamSettings': {'network': 'tcp', 'security': 'reality',
                    'realitySettings': {'show': False, 'target': wire_ip + ':8443', 'xver': 0,
                        'serverNames': ['api.telegram.org'], 'privateKey': private_key,
                        'shortIds': [short_id]}}}],
            'outbounds': [{'tag': 'deny', 'protocol': 'blackhole'},
                {'tag': 'synthetic-recipient', 'protocol': 'freedom',
                    'settings': {'redirect': wire_ip + ':443'}}],
            'routing': {'domainStrategy': 'AsIs', 'rules': [{'type': 'field',
                'inboundTag': ['test-peer'], 'domain': ['full:api.telegram.org'],
                'port': '443', 'network': 'tcp', 'outboundTag': 'synthetic-recipient'},
                {'type': 'field', 'network': 'tcp,udp', 'outboundTag': 'deny'}]}}
        e.write_private(directory / 'peer.json', e.encoded(peer))
        phase_start('synthetic_peer_config')
        e.image_check(directory / 'peer.json', os.getuid(), os.getgid())
        run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
            '-subj', '/CN=Synthetic TEST CA', '-keyout', str(directory / 'ca.key'),
            '-out', str(directory / 'ca.pem')])
        run(['openssl', 'req', '-newkey', 'rsa:2048', '-nodes', '-subj', '/CN=api.telegram.org',
            '-keyout', str(directory / 'server.key'), '-out', str(directory / 'server.csr')])
        e.write_private(directory / 'extensions', b'subjectAltName=DNS:api.telegram.org\nextendedKeyUsage=serverAuth\n')
        run(['openssl', 'x509', '-req', '-in', str(directory / 'server.csr'),
            '-CA', str(directory / 'ca.pem'), '-CAkey', str(directory / 'ca.key'), '-CAcreateserial',
            '-out', str(directory / 'server.pem'), '-days', '1', '-extfile', str(directory / 'extensions')])
        phase_start('topology')
        run([*base, 'build', 'telegram-operator'], 180)
        run(['docker', 'tag', project + '-telegram-operator', 'asm-telegram-egress-checks:test'])
        run([*base, 'up', '-d', '--wait', 'api', 'worker', 'scheduler'], 180)
        compose('config', '--quiet')
        compose('up', '-d', '--wait', 'postgres-test', 'storage-test-init')
        compose('run', '--rm', '--no-deps', '-T', 'egress-checks', 'alembic', 'upgrade', 'head')
        compose('up', '-d', '--no-deps', '--wait', 'api', 'worker', 'egress-wire', 'egress-peer', 'telegram-egress')
        deadline = time.monotonic() + 15
        while not (directory / 'wire-ready.json').exists():
            assert time.monotonic() < deadline, 'TLS_RECIPIENT_START'
            time.sleep(.1)
        network = json.loads(run(['docker', 'network', 'inspect', values['ASM_TELEGRAM_EGRESS_NETWORK']]))[0]
        assert network['EnableIPv6'] is False
        assert network['IPAM']['Config'][0]['Subnet'] == state['subnet']
        assert network['IPAM']['Config'][0]['IPRange'] == values['ASM_TELEGRAM_EGRESS_DYNAMIC_RANGE']
        relay_info()
        e.caller_probe(state, state_dir)
        phase_start('postgres_wire')
        checks = start_checks(['pytest', '-q', '-o', 'python_classes=TelegramEgressPostgresChecks',
                               'tests/test_telegram_egress_postgres.py'])
        await_process(checks)
        assertions = [json.loads(row) for row in (directory / 'assertions.jsonl').read_text().splitlines()]
        assert len(assertions) == 6 and all(row['result'] == 'PASS' for row in assertions)
        phase_start('durable_rollback')
        durable = start_checks(['python', 'tests/test_telegram_egress_postgres.py', '--durable-receipt', 'before'])
        await_process(durable, marker=directory / 'durable-before.json', timeout=90)
        # Keep actual UNKNOWN/receipt/session fixtures open while running the exact
        # operator code on real containers. No domain reset, volume deletion or rebind.
        run([*base, 'up', '-d', '--no-deps', '--force-recreate', '--wait', 'api', 'worker'])
        e.deploy(state, state_dir)
        e.compare_deployment(json.loads((state_dir / 'deployment-before.json').read_text()),
                             e.snapshot(state, state_dir), state)
        e.caller_probe(state, state_dir)
        before_env = (directory / 'telegram.env').read_bytes()
        compose('stop', '--timeout', '1', 'telegram-egress')
        e.caller_probe(state, state_dir)
        e.rollback(state, state_dir)
        assert (directory / 'telegram.env').read_bytes() == before_env
        compose('run', '--rm', '--no-deps', '-T', 'egress-checks', 'python',
                'tests/test_telegram_egress_postgres.py', '--durable-receipt', 'after')
        await_process(durable, timeout=30)
        assertions = [json.loads(row) for row in (directory / 'assertions.jsonl').read_text().splitlines()]
        assert len(assertions) == 7 and all(row['result'] == 'PASS' for row in assertions)
        receipt = {'source_sha': source, 'image': e.IMAGE, 'image_id': state['image_id'],
            'E01': 'source/blob/private-config/offline-pinned-binary PASS',
            'E02': 'resolved opt-in/real all-callers mapping/stop/recreate/auth/DB/S3 PASS',
            'assertions': assertions, 'relay_controls': controls,
            'deployment_before': json.loads((state_dir / 'deployment-before.json').read_text()),
            'deployment_after': json.loads((state_dir / 'deployment-after.json').read_text()),
            'rollback': json.loads((state_dir / 'rollback.json').read_text()),
            'durable_before': json.loads((directory / 'durable-before.json').read_text()),
            'durable_after': json.loads((directory / 'durable-after.json').read_text())}
        reports = root / 'reports'
        reports.mkdir(exist_ok=True)
        (reports / 'telegram-egress.json').write_text(json.dumps(receipt, indent=2) + '\n')
        print('TELEGRAM_EGRESS_E01_E05_PASS', flush=True)
    except Exception as error:
        # No private config, environment, process argv or raw Docker inspect output.
        print('TELEGRAM_EGRESS_TEST_FAILURE phase=' + phase + ' type=' + type(error).__name__, flush=True)
        if isinstance(error, e.EgressError):
            print(str(error), flush=True)
        raise SystemExit(1) from None
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        if prefix is not None:
            result = subprocess.run([*prefix, 'down', '--remove-orphans', '--timeout', '2'],
                                    capture_output=True, timeout=90, env=environment)
            assert result.returncode == 0, 'SYNTHETIC_TOPOLOGY_CLEANUP_FAILED'
PY
