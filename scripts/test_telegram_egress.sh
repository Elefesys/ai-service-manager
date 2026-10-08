#!/bin/sh
# Mandatory synthetic lane. No owner inputs, public Telegram calls or Docker socket mounts.
set -eu
python3 - "$@" <<'PY'
import importlib.util
import ipaddress
import json
import os
import re
import runpy
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from scripts import prepare_telegram_egress as e

os.umask(0o077)
root = Path.cwd()
assert root == e.ROOT and os.getuid() != 0, 'TEST_RUNNER_CHECKOUT_AND_NONROOT_REQUIRED'
migration = None
if sys.argv[1:]:
    assert len(sys.argv) in {4, 6} and sys.argv[1] == '--migration', 'EXPLICIT_MIGRATION_SELECTOR_REQUIRED'
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'DISPOSABLE_RUNNER_REQUIRED'
    migration = {'root': root, 'fault': sys.argv[3], 'source': subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip()}
    assert migration['fault'] in {'intent', 'image', 'state'}
    migration['operator_source'] = e.MIGRATION_FROM
    if migration['fault'] == 'image':
        assert len(sys.argv) == 6 and sys.argv[4] == e.HISTORICAL_OPERATOR
        assert re.fullmatch(r'sha256:[0-9a-f]{64}', sys.argv[5])
        migration.update(operator_source=sys.argv[4], operator_image=sys.argv[5])
    else:
        assert len(sys.argv) == 4
    root = Path(sys.argv[2]).resolve()
    assert root != migration['root'] and root.name == 'predecessor'
    spec = importlib.util.spec_from_file_location('exact_predecessor_egress', root / 'scripts/prepare_telegram_egress.py')
    e = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(e)
    os.chdir(root)
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip() == '0b7e24ee425ebb429bf87dfe382cbd3fab883028'
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
        # CI-only Docker lifecycle diagnostics; no config/inspect/stdout dumps.
        diagnostic = result.stderr.decode(errors='replace')[-4096:]
        for env_path in (root / '.env', directory / 'telegram.env'):
            if env_path.exists():
                for line in env_path.read_text().splitlines():
                    if '=' in line and not line.startswith('#'):
                        value = line.split('=', 1)[1].strip().strip('\"\'')
                        if value:
                            diagnostic = diagnostic.replace(value, '<redacted>')
        diagnostic = re.sub(r'(://)[^/\s]*@', r'\1<redacted>@', diagnostic)
        print('TEST_COMMAND_EXIT=' + str(result.returncode) + ' phase=' + phase, flush=True)
        print(diagnostic, flush=True)
        if args[:1] == ['python3'] and len(args) > 1 and Path(args[1]).name == 'prepare_telegram_egress.py':
            code = result.stdout.decode(errors='replace').strip()
            if re.fullmatch('EGRESS_[A-Za-z0-9_]{1,120}', code):
                print(code, flush=True)
        raise RuntimeError('TEST_COMMAND_FAILED:' + phase)
    return result.stdout

def compose(*args, timeout=120):
    return run([*prefix, *args], timeout)

def phase_start(name):
    global phase
    phase = name
    print('TELEGRAM_EGRESS_TEST_' + name.upper(), flush=True)

def operator(action):
    phase_start('operator_' + action)
    prepare_args = (['--accepted-sha', source, '--profile', str(directory / 'profile.json'),
                     '--telegram-env', str(directory / 'telegram.env'), '--project', project]
                    if action == 'prepare' else ['--accepted-sha', source, '--from-sha', e.LEGACY_SHA]
                    if action == 'recover' or action == 'rollback' and
                    json.loads((state_dir / 'state.json').read_text())['version'] == 1 else [])
    output = run(['python3', 'scripts/prepare_telegram_egress.py', action,
                  '--state-dir', str(state_dir), *prepare_args], 120).decode().strip()
    assert output == 'TELEGRAM_EGRESS_' + action.upper() + '_PASS'
    print(output, flush=True)

def interrupted_operator(action, fault):
    # Fault injection wraps only real command/fsync boundaries, then SIGKILLs this
    # exact helper main(). No Docker/PG substitutes or production fault switches.
    injector = r'''
import os, signal, sys
from pathlib import Path
from scripts import prepare_telegram_egress as e
fault, destination = sys.argv[1:3]
sys.argv = ["prepare_telegram_egress.py", *sys.argv[3:]]
execute, save = e.command, e.write_private
up_count = 0
def crash():
    save(Path(destination), e.encoded({"fault": fault, "real_boundary": True}))
    os.kill(os.getpid(), signal.SIGKILL)
def write(path, data, **kwargs):
    if fault == "rollback-receipt" and path.name == "rollback.json":
        crash()
    save(path, data, **kwargs)
    if fault == "rollback-env" and path == e.ROOT / ".env":
        crash()
def command(argv, **kwargs):
    global up_count
    if fault in {"relay-stopped", "relay-missing"} and "up" in argv and argv[-1] == "telegram-egress":
        prefix = argv[:argv.index("up")]
        execute([*prefix, "stop", "telegram-egress"], **kwargs)
        if fault == "relay-missing":
            execute([*prefix, "rm", "-f", "telegram-egress"], **kwargs)
        crash()
    result = execute(argv, **kwargs)
    if "up" in argv and argv[-2:] == ["api", "worker"]:
        up_count += 1
        if (fault == "rollback-callers" and up_count == 1 or fault == "rollback-remove" and up_count == 2):
            crash()
    return result
e.command, e.write_private = command, write
e.main()
'''
    marker = directory / ('interruption-' + lifecycle + '-' + fault + '.json')
    assert not marker.exists()
    result = subprocess.run(['python3', '-c', injector, fault, str(marker), action,
        '--state-dir', str(state_dir), '--accepted-sha', source, '--from-sha', e.LEGACY_SHA],
        stdin=subprocess.DEVNULL, capture_output=True, timeout=120, env=environment)
    if result.returncode != -signal.SIGKILL:
        code = result.stdout.decode(errors='replace').strip()
        if re.fullmatch('EGRESS_[A-Za-z0-9_]{1,120}', code):
            print(code, flush=True)
    assert result.returncode == -signal.SIGKILL, 'EXPECTED_HELPER_SIGKILL_' + fault
    assert json.loads(marker.read_text()) == {'fault': fault, 'real_boundary': True}
    assert not (state_dir / 'rollback.json').exists()
    print('REAL_HELPER_INTERRUPTION_' + fault.upper(), flush=True)

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
    assert info['NetworkSettings']['Networks'][values['ASM_TELEGRAM_EGRESS_NETWORK6']]['IPAMConfig']['IPv6Address'] == values['ASM_TELEGRAM_EGRESS_IPV6']
    return identity

def mapping_evidence():
    model = e.checked_model(state, state_dir)
    expected = {values['ASM_TELEGRAM_EGRESS_IP'], values['ASM_TELEGRAM_EGRESS_IPV6']}
    probe = """import json,pathlib,platform,socket
rows={str(f):[x[4][0] for x in socket.getaddrinfo('api.telegram.org',443,f,socket.SOCK_STREAM,0,0)] for f in (socket.AF_UNSPEC,socket.AF_INET,socket.AF_INET6)}
hosts=[line.split()[0] for line in pathlib.Path('/etc/hosts').read_text().splitlines() if 'api.telegram.org' in line.split()[1:]]
print(json.dumps({'hosts':hosts,'resolver_flags':0,'resolver':rows,'python':platform.python_version(),'libc':platform.libc_ver()}))
"""
    result = {}
    for name in ('api', 'worker', 'telegram-operator'):
        temporary = name == 'telegram-operator'
        identity = (run([*live, 'run', '-d', '--rm', '--no-deps', '--pull', 'never',
            '--entrypoint', 'python', name, '-c', 'import time; time.sleep(120)']).decode().strip()
            if temporary else run([*live, 'ps', '-q', name]).decode().strip())
        try:
            info = json.loads(run(['docker', 'inspect', identity]))[0]
            data = json.loads(run(['docker', 'exec', identity, 'python', '-c', probe]))
            assert set(data['hosts']) == expected and len(data['hosts']) == 2
            assert all(row and set(row) <= expected for row in data['resolver'].values())
            assert set(data['resolver']['2']) == {values['ASM_TELEGRAM_EGRESS_IP']}
            assert set(data['resolver']['10']) == {values['ASM_TELEGRAM_EGRESS_IPV6']}
            data.update(model=model['services'][name]['extra_hosts'], host_config=info['HostConfig']['ExtraHosts'])
            assert set(data['model']) == {'api.telegram.org=' + v for v in expected}
            assert set(data['host_config']) == {'api.telegram.org:' + v for v in expected}
            result[name] = data
        finally:
            if temporary:
                run(['docker', 'rm', '-f', identity])
    return result

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
        compose('exec', '-T', 'api', 'python', '-c', probe)
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

def local_database_args():
    model = e.checked_model(state, state_dir)['services']
    return ['-e', 'ASM_DATABASE_URL=' + model['api']['environment']['ASM_DATABASE_URL'],
            '-e', 'ASM_MIGRATION_DATABASE_URL=' + model['telegram-operator']['environment']['ASM_MIGRATION_DATABASE_URL'],
            '-e', 'ASM_AUTH_ORIGINS=' + model['api']['environment']['ASM_AUTH_ORIGINS'],
            '-e', 'ASM_STORAGE_ENDPOINT=' + model['api']['environment']['ASM_STORAGE_ENDPOINT'],
            '-e', 'ASM_EGRESS_LIFECYCLE=' + lifecycle]

def assert_https_callers(command_prefix):
    ids = {}
    for name in ('api', 'worker'):
        identity = run([*command_prefix, 'ps', '-q', name]).decode().strip()
        info = json.loads(run(['docker', 'inspect', identity]))[0]
        values = dict(v.split('=', 1) for v in info['Config']['Env'])
        assert values['ASM_TELEGRAM_ENABLED'] == 'false'
        assert all(values[k] == '' for k in ('TG_BOT_TOKEN', 'TG_WEBHOOK_SECRET',
            'ASM_TELEGRAM_EXPECTED_BOT_ID', 'ASM_TELEGRAM_WEBHOOK_URL'))
        assert {key: values[key] for key in operational} == operational, 'E05_HTTPS_INPUT_DRIFT'
        ids[name] = identity
    return ids

def start_checks(args, *, local=False):
    # Only bounded synthetic pytest/fixture output is inherited. Never print config/env.
    process = subprocess.Popen([*prefix, 'run', '--rm', '--no-deps', '-T',
        *(local_database_args() if local else []),
        'egress-checks', *args], stdin=subprocess.DEVNULL, env=environment)
    processes.append(process)
    return process

with tempfile.TemporaryDirectory(prefix='asm-telegram-egress-') as temporary:
    directory = Path(temporary)
    try:
        source = run(['git', 'rev-parse', 'HEAD']).decode().strip()
        e.source_check(source)
        # Attest a disposable project before E05 may seed its actual LOCAL DB.
        assert not run(['docker', 'ps', '-aq', '--filter', 'label=com.docker.compose.project=' + project]).strip()
        assert not run(['docker', 'volume', 'ls', '-q', '--filter', 'label=com.docker.compose.project=' + project]).strip()
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
        operational = {'ASM_AUTH_ORIGINS': '["https://console.egress.test:8443"]',
                       'ASM_STORAGE_ENDPOINT': 'https://files.egress.test:8443'}
        original_env = (root / '.env').read_bytes()
        assert {row.split('=', 1)[0] for row in original_env.decode().splitlines()} == {
            'PG_ADMIN_PASSWORD', 'PG_MIGRATION_PASSWORD', 'PG_RUNTIME_PASSWORD',
            'STORAGE_ROOT_USER', 'STORAGE_ROOT_PASSWORD', 'STORAGE_ACCESS_KEY', 'STORAGE_SECRET_KEY'}
        prelive_inputs = (b'ASM_TELEGRAM_ENABLED=false\n'
                          + ''.join(f"{key}='{value}'\n" for key, value in operational.items()).encode())
        e.write_private(directory / 'telegram.env', prelive_inputs)
        e.write_private(directory / 'prelive.env', prelive_inputs)
        # Reproduce the accepted pre-live recipe independently of the generator.
        # Callers first receive HTTPS values from the second env file with no TG inputs.
        historical = ['docker', 'compose', '--project-directory', str(root), '--project-name', project,
            '--env-file', str(root / 'infra/images.lock.env'), '--env-file', str(root / '.env'),
            '--env-file', str(directory / 'telegram.env'), '-f', str(root / 'compose.yaml'),
            '--profile', 'telegram-operator']
        prefix = historical
        prelive = [str(directory / 'prelive.env') if v == str(directory / 'telegram.env') else v for v in historical]
        phase_start('independent_https_baseline')
        run([*historical, 'up', '-d', '--wait', 'api', 'worker', 'scheduler'], 180)
        independent_ids = assert_https_callers(historical)
        postgres_id = run([*historical, 'ps', '-q', 'postgres']).decode().strip()
        postgres_info = json.loads(run(['docker', 'inspect', postgres_id]))[0]
        assert postgres_info['Config']['Labels']['com.docker.compose.project'] == project
        assert postgres_info['Config']['Labels']['com.docker.compose.service'] == 'postgres'
        assert re.fullmatch('[a-f0-9]{64}', postgres_id)
        assert any(m['Type'] == 'volume' and m['Name'] == project + '_pgdata' for m in postgres_info['Mounts'])
        # Stage the Telegram fields without recreating those accepted callers.
        staged_inputs = (prelive_inputs + b'TG_BOT_TOKEN=9911:synthetic-staged-not-active\n'
                         b'TG_WEBHOOK_SECRET=synthetic-staged-webhook-not-active\n'
                         b'ASM_TELEGRAM_EXPECTED_BOT_ID=9911\n'
                         b'ASM_TELEGRAM_WEBHOOK_URL=https://synthetic.invalid/webhook\n')
        if migration is not None:
            staged_inputs += b"ASM_TELEGRAM_EXPECTED_OWNER_ID='101' # synthetic predecessor\r\n"
        e.write_private(directory / 'telegram.env', staged_inputs)
        state_dir = directory / 'state'
        phase_start('private_prepare')
        assert not state_dir.exists()
        operator('prepare')
        assert independent_ids == assert_https_callers(historical)
        assert (root / '.env').read_bytes() == original_env
        assert (directory / 'telegram.env').read_bytes() == staged_inputs
        state = e.verify(state_dir)
        lifecycle = 'fresh'
        values = e.route_values(state, state_dir)
        assert values['ASM_TELEGRAM_EGRESS_IP'] == relay_ip
        live = e.compose_prefix(state, state_dir)
        base = e.compose_prefix(state, state_dir, overlay=False)
        prelive_live = [*prelive, '--env-file', str(root / 'infra/telegram-egress/image.lock.env'),
            '--env-file', str(state_dir / 'route.env'), '-f', str(root / 'infra/telegram-egress/compose.yaml'),
            '--profile', 'telegram-egress']
        assert str(state_dir / 'runtime.json') not in prelive_live
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
                    # 26.9.9 blocks private targets for VLESS by default. Only
                    # this synthetic recipient /32:443 is explicitly allowed.
                    # This TEST peer rule never enters the actual relay config.
                    'settings': {'redirect': wire_ip + ':443', 'finalRules': [
                        {'action': 'allow', 'network': 'tcp', 'port': '443',
                         'ip': [wire_ip + '/32']}]}}],
            'routing': {'domainStrategy': 'AsIs', 'rules': [{'type': 'field',
                'inboundTag': ['test-peer'], 'domain': ['full:api.telegram.org'],
                'port': '443', 'network': 'tcp', 'outboundTag': 'synthetic-recipient'},
                {'type': 'field', 'network': 'tcp,udp', 'outboundTag': 'deny'}]}}
        e.write_private(directory / 'peer.json', e.encoded(peer))
        phase_start('synthetic_peer_config')
        e.image_check(directory / 'peer.json', os.getuid(), os.getgid())
        run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
            '-addext', 'basicConstraints=critical,CA:TRUE',
            '-addext', 'keyUsage=critical,keyCertSign,cRLSign',
            '-subj', '/CN=Synthetic TEST CA', '-keyout', str(directory / 'ca.key'),
            '-out', str(directory / 'ca.pem')])
        run(['openssl', 'req', '-newkey', 'rsa:2048', '-nodes', '-subj', '/CN=api.telegram.org',
            '-keyout', str(directory / 'server.key'), '-out', str(directory / 'server.csr')])
        # CPython 3.13 defaults to VERIFY_X509_STRICT. Supply a valid bounded
        # TEST chain; do not weaken the accepted client's certificate checks.
        e.write_private(directory / 'extensions',
            b'basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\n'
            b'subjectAltName=DNS:api.telegram.org\nextendedKeyUsage=serverAuth\n'
            b'subjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\n')
        run(['openssl', 'x509', '-req', '-in', str(directory / 'server.csr'),
            '-CA', str(directory / 'ca.pem'), '-CAkey', str(directory / 'ca.key'), '-CAcreateserial',
            '-out', str(directory / 'server.pem'), '-days', '1', '-extfile', str(directory / 'extensions')])
        run(['openssl', 'verify', '-x509_strict', '-purpose', 'sslserver',
            '-verify_hostname', 'api.telegram.org', '-CAfile', str(directory / 'ca.pem'),
            str(directory / 'server.pem')])
        # Separate TEST TLS leaf for a real Secure Console cookie and HTTPS S3
        # endpoint. Existing Telegram leaf, transport and trust assertions stay intact.
        run(['openssl', 'req', '-newkey', 'rsa:2048', '-nodes', '-subj', '/CN=console.egress.test',
            '-keyout', str(directory / 'https.key'), '-out', str(directory / 'https.csr')])
        e.write_private(directory / 'https-extensions',
            b'basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\n'
            b'subjectAltName=DNS:console.egress.test,DNS:files.egress.test\nextendedKeyUsage=serverAuth\n'
            b'subjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\n')
        run(['openssl', 'x509', '-req', '-in', str(directory / 'https.csr'),
            '-CA', str(directory / 'ca.pem'), '-CAkey', str(directory / 'ca.key'), '-CAcreateserial',
            '-out', str(directory / 'https.pem'), '-days', '1', '-extfile', str(directory / 'https-extensions')])
        for hostname in ('console.egress.test', 'files.egress.test'):
            run(['openssl', 'verify', '-x509_strict', '-purpose', 'sslserver',
                '-verify_hostname', hostname, '-CAfile', str(directory / 'ca.pem'), str(directory / 'https.pem')])
        e.write_private(directory / 'https.conf', b'''
pid /tmp/nginx.pid;
error_log stderr warn;
events { worker_connections 128; }
http {
    access_log off;
    client_body_temp_path /tmp/client_temp;
    proxy_temp_path /tmp/proxy_temp;
    fastcgi_temp_path /tmp/fastcgi_temp;
    uwsgi_temp_path /tmp/uwsgi_temp;
    scgi_temp_path /tmp/scgi_temp;
    resolver 127.0.0.11 valid=1s ipv6=off;
    ssl_protocols TLSv1.3;
    ssl_certificate /run/https.pem;
    ssl_certificate_key /run/https.key;
    server {
        listen 8443 ssl;
        server_name console.egress.test;
        location / {
            set $upstream http://api:8000;
            proxy_set_header Host api:8000;
            proxy_pass $upstream;
        }
    }
    server {
        listen 8443 ssl;
        server_name files.egress.test;
        location / {
            set $upstream http://storage:9000;
            proxy_set_header Host $http_host;
            proxy_pass $upstream;
        }
    }
}
''')
        phase_start('topology')
        if migration is not None and migration['fault'] == 'image':
            run(['docker', 'tag', migration['operator_image'], project + '-telegram-operator'])
        else:
            run([*base, 'build', 'telegram-operator'], 180)
        run(['docker', 'tag', project + '-telegram-operator', 'asm-telegram-egress-checks:test'])
        if migration is not None:
            # Old app/operator images stay exact. Only synthetic test services use
            # the candidate development image containing the new held fixture.
            run(['docker', 'tag', 'asm-connect5-development:' + migration['source'], 'asm-telegram-egress-checks:test'])
        compose('config', '--quiet')
        phase_start('test_storage_bootstrap')
        compose('up', '-d', '--wait', 'postgres-test', 'storage-test')
        # This one-shot has no selected dependent here. --wait requires running
        # or healthy, so execute it to completion and preserve its exact exit code.
        compose('run', '--rm', '--no-deps', '-T', 'storage-test-init')
        phase_start('test_migration')
        compose('run', '--rm', '--no-deps', '-T', 'egress-checks', 'alembic', 'upgrade', 'head')
        phase_start('relay_containers')
        compose('up', '-d', '--no-deps', '--wait', 'api', 'worker', 'egress-wire', 'egress-peer', 'telegram-egress')
        deadline = time.monotonic() + 15
        while not (directory / 'wire-ready.json').exists():
            assert time.monotonic() < deadline, 'TLS_RECIPIENT_START'
            time.sleep(.1)
        network = json.loads(run(['docker', 'network', 'inspect', values['ASM_TELEGRAM_EGRESS_NETWORK']]))[0]
        assert network['EnableIPv6'] is False
        assert network['IPAM']['Config'][0]['Subnet'] == state['subnet']
        assert network['IPAM']['Config'][0]['IPRange'] == values['ASM_TELEGRAM_EGRESS_DYNAMIC_RANGE']
        network6 = json.loads(run(['docker', 'network', 'inspect', values['ASM_TELEGRAM_EGRESS_NETWORK6']]))[0]
        assert network6['Internal'] and network6['EnableIPv6'] and not network6['EnableIPv4']
        assert network6['IPAM']['Config'] == [{'Subnet': state['subnet6'],
            'IPRange': values['ASM_TELEGRAM_EGRESS_DYNAMIC_RANGE6'], 'Gateway': values['ASM_TELEGRAM_EGRESS_GATEWAY6']}]
        relay_info()
        e.caller_probe(state, state_dir)
        corrected_mapping = mapping_evidence()
        # Real Docker identity negatives, outside each bounded held-state fixture.
        # A stopped spoof carrying our Compose labels is never treated as an outage.
        transition_guard = e.transition_relay([state], state_dir)
        assert transition_guard['status'] == 'running'
        foreign = run(['docker', 'create', '--label', 'com.docker.compose.project=' + project,
            '--label', 'com.docker.compose.service=telegram-egress', '--label', 'com.docker.compose.oneoff=False',
            '--entrypoint', '/bin/false', e.IMAGE]).decode().strip()
        try:
            try:
                e.transition_relay([state], state_dir, missing=True)
            except e.EgressError as error:
                assert str(error) == 'EGRESS_RELAY_MULTIPLE'
            else:
                raise AssertionError('FOREIGN_RELAY_NOT_REJECTED')
        finally:
            run(['docker', 'rm', foreign])
        config_path = state_dir / 'config.json'
        config_bytes = config_path.read_bytes()
        e.write_private(config_path, config_bytes + b'\n')
        try:
            try:
                e.transition_relay([state], state_dir)
            except e.EgressError as error:
                assert str(error) == 'EGRESS_RELAY_TRANSITION_CONFIG'
            else:
                raise AssertionError('RELAY_CONFIG_DRIFT_NOT_REJECTED')
        finally:
            e.write_private(config_path, config_bytes)
        assert e.transition_relay([state], state_dir) == transition_guard
        if migration is not None:
            runpy.run_path(str(migration['root'] / 'tests/test_telegram_egress_migration.py'),
                           init_globals={'fixture': globals()}, run_name='__migration_harness__')
            raise AssertionError('MIGRATION_HARNESS_MUST_COMPLETE_EXPLICITLY')
        phase_start('postgres_wire')
        checks = start_checks(['pytest', '-q', '-o', 'python_classes=TelegramEgressPostgresChecks',
                               'tests/test_telegram_egress_postgres.py'])
        await_process(checks)
        assertions = [json.loads(row) for row in (directory / 'assertions.jsonl').read_text().splitlines()]
        assert len(assertions) == 6 and all(row['result'] == 'PASS' for row in assertions)
        lifecycle_receipts = {}
        fresh_state, fresh_dir = state, state_dir
        lifecycles = ('fresh', 'recovery', 'recover-stopped', 'recover-missing', 'legacy-disable', 'legacy-stop')
        for lifecycle_index, lifecycle in enumerate(lifecycles):
            phase_start('durable_' + lifecycle)
            state, state_dir = fresh_state, fresh_dir
            values = e.route_values(state, state_dir)
            live, base = e.compose_prefix(state, state_dir), e.compose_prefix(state, state_dir, overlay=False)
            prefix = [*live, '-f', str(root / 'infra/telegram-egress/compose.test.yaml'), '--profile', 'test']
            # Independent disposable cases; no reset/drop of the actual caller DB.
            e.write_private(root / '.env', original_env, private_parent=False)
            # A legacy rollback leaves its IPv4-only relay stopped. Restore the
            # disposable dual-family seed transport before holding the next case's
            # UNKNOWN/session, without touching any prior baseline/audit or DB rows.
            compose('up', '-d', '--no-deps', '--pull', 'never', '--force-recreate', 'telegram-egress')
            relay_info()
            for filename in ('durable-before.json', 'durable-after.json', 'durable-release.json'):
                (directory / filename).unlink(missing_ok=True)
            # E05 uses the exact base runtime database, not the six cases' asm_test.
            # Keep the relay attached while the isolated LOCAL harness creates UNKNOWN.
            # Restore the independently captured pre-staging baseline, not runtime.json.
            run([*prelive_live, 'up', '-d', '--no-deps', '--force-recreate', '--wait', 'api', 'worker'])
            assert_https_callers(prelive_live)
            compose('up', '-d', '--no-deps', '--wait', 'egress-https')
            target = e.snapshot(state, state_dir)
            assert target['postgres']['id'] == postgres_id
            identity = target['api']['database_identity']
            assert identity == target['worker']['database_identity'] and identity['database'] == 'asm_local'
            e.write_private(directory / 'durable-target.json', e.encoded({
                'project': project, 'postgres_id': postgres_id, 'database_identity': identity,
                'callers': {name: target[name]['database_identity'] for name in ('api', 'worker')}}))
            run([*base, 'stop', 'worker'])
            durable = start_checks(['python', 'tests/test_telegram_egress_postgres.py', '--durable-receipt', 'before'], local=True)
            await_process(durable, marker=directory / 'durable-before.json', timeout=90)
            # Keep actual UNKNOWN/receipt/session fixtures open while running the exact
            # operator code on real containers. No domain reset, volume deletion or rebind.
            run([*prelive, 'up', '-d', '--no-deps', '--force-recreate', '--wait', 'api', 'worker'])
            def assert_runtime_boundary():
                current = e.snapshot(state, state_dir)
                assert current['postgres']['id'] == postgres_id
                for name in ('api', 'worker'):
                    assert current[name]['database_identity'] == identity, 'E05_ACTUAL_CALLER_DATABASE_CHANGED'
                    info = json.loads(run(['docker', 'inspect', current[name]['id']]))[0]
                    actual = dict(v.split('=', 1) for v in info['Config']['Env'])
                    assert actual['ASM_TELEGRAM_ENABLED'] == 'false'
                    assert all(actual[k] == '' for k in ('TG_BOT_TOKEN', 'TG_WEBHOOK_SECRET',
                        'ASM_TELEGRAM_EXPECTED_BOT_ID', 'ASM_TELEGRAM_WEBHOOK_URL')), 'E05_STAGED_INPUT_LEAK'
                    assert {key: actual[key] for key in operational} == operational, 'E05_HTTPS_INPUT_DRIFT'
                assert (directory / 'telegram.env').read_bytes() == staged_inputs
                return current
            runtime_before = assert_runtime_boundary()
            if lifecycle == 'fresh':
                operator('deploy')
            else:
                # Materialize the exact accepted schema1 and partial deployment using
                # the frozen old overlay, independently of corrected prepare/deploy.
                compose('rm', '-f', '-s', 'telegram-egress')
                held = run(['docker', 'ps', '-q', '--filter', 'label=com.docker.compose.project=' + project,
                            '--filter', 'label=com.docker.compose.service=egress-checks']).decode().split()
                assert len(held) == 1
                run(['docker', 'network', 'disconnect', values['ASM_TELEGRAM_EGRESS_NETWORK6'], held[0]])
                run(['docker', 'network', 'rm', values['ASM_TELEGRAM_EGRESS_NETWORK6']])
                original_before = e.encoded(e.snapshot(state, state_dir))
                old = {k: v for k, v in state.items() if k != 'subnet6'}
                old.update(version=1, source_sha=e.LEGACY_SHA)
                state_dir = directory / ('partial-state-' + lifecycle)
                state_dir.mkdir(mode=0o700)
                legacy_config = e.encoded(e.minimal_config(profile, relay_ip))
                old['config_sha256'] = e.sha(legacy_config)
                for name, raw in {'config.json': legacy_config,
                        'runtime.json': (fresh_dir / 'runtime.json').read_bytes(),
                        'route.env': e.route_env(e.route_values(old, state_dir)),
                        'state.json': e.encoded(old), 'deployment-before.json': original_before}.items():
                    e.write_private(state_dir / name, raw)
                e.write_private(directory / 'legacy-compose.yaml', e.LEGACY_OVERLAY)
                legacy_prefix = [*e.compose_prefix(old, state_dir, overlay=False),
                    '-f', str(directory / 'legacy-compose.yaml'), '--profile', 'telegram-egress']
                run([*legacy_prefix, 'up', '-d', '--no-deps', '--pull', 'never', '--force-recreate', 'telegram-egress'])
                run([*legacy_prefix, 'up', '-d', '--no-deps', '--pull', 'never', '--force-recreate', '--wait', 'api', 'worker'])
                partial = e.snapshot(fresh_state, fresh_dir)
                e.compare_deployment(json.loads(original_before), partial, old)
                assert all(partial[n]['id'] != json.loads(original_before)[n]['id'] for n in ('api', 'worker'))
                assert not (state_dir / 'deployment-after.json').exists()
                before_files = {name: (state_dir / name).read_bytes() for name in
                    ('state.json', 'config.json', 'runtime.json', 'route.env', 'deployment-before.json')}
                if lifecycle.startswith('legacy-'):
                    state = old
                    if lifecycle == 'legacy-disable':
                        interrupted_operator('rollback', 'rollback-env')
                        audit = {p.name: p.read_bytes() for p in (state_dir / 'recovery-v1').iterdir()}
                        interrupted_operator('rollback', 'rollback-callers')
                    else:
                        # Initial outage, then interruption after route removal and
                        # after the real stop, before receipt. Finally the stopped
                        # owned container disappears: the durable stop intent remains.
                        run([*legacy_prefix, 'stop', 'telegram-egress'])
                        interrupted_operator('rollback', 'rollback-remove')
                        audit = {p.name: p.read_bytes() for p in (state_dir / 'recovery-v1').iterdir()}
                        interrupted_operator('rollback', 'rollback-receipt')
                        run([*legacy_prefix, 'rm', '-f', 'telegram-egress'])
                    operator('rollback')
                    assert {p.name: p.read_bytes() for p in (state_dir / 'recovery-v1').iterdir()} == audit
                    for name, raw in before_files.items():
                        assert (state_dir / name).read_bytes() == raw
                        assert (state_dir / 'recovery-v1' / name).read_bytes() == raw
                    receipt_bytes = (state_dir / 'rollback.json').read_bytes()
                    rolled_back = e.snapshot(old, state_dir)
                    operator('rollback')
                    assert e.snapshot(old, state_dir) == rolled_back
                    assert (state_dir / 'rollback.json').read_bytes() == receipt_bytes
                    assert not (state_dir / 'deployment-after.json').exists()
                    assert not (state_dir / 'recovery.json').exists()
                else:
                    command = ['python3', 'scripts/prepare_telegram_egress.py', 'recover', '--state-dir', str(state_dir),
                               '--accepted-sha', source, '--from-sha', e.LEGACY_SHA]
                    if lifecycle == 'recovery':
                        # Crash the exact CLI after atomic manifest publication, before up.
                        with (directory / 'interrupted-recovery.log').open('wb') as output:
                            recovery = subprocess.Popen(command, stdout=output, stderr=output, stdin=subprocess.DEVNULL,
                                                        env=environment, start_new_session=True)
                            processes.append(recovery)
                            deadline = time.monotonic() + 30
                            while recovery.poll() is None:
                                if json.loads((state_dir / 'state.json').read_text())['version'] == 2:
                                    os.killpg(recovery.pid, signal.SIGKILL)
                                    recovery.wait(timeout=5)
                                    break
                                assert time.monotonic() < deadline, 'RECOVERY_MANIFEST_DEADLINE'
                                time.sleep(.005)
                            assert recovery.returncode == -signal.SIGKILL, 'EXACT_RECOVERY_NOT_INTERRUPTED'
                    else:
                        interrupted_operator('recover', 'relay-stopped' if lifecycle == 'recover-stopped' else 'relay-missing')
                        assert json.loads((state_dir / 'state.json').read_text())['version'] == 2
                        identities = run([*legacy_prefix, 'ps', '-a', '-q', 'telegram-egress']).decode().split()
                        if lifecycle == 'recover-stopped':
                            assert len(identities) == 1
                            assert json.loads(run(['docker', 'inspect', identities[0]]))[0]['State']['Status'] == 'exited'
                        else:
                            assert not identities
                    assert not (state_dir / 'deployment-after.json').exists()
                    assert not (state_dir / 'recovery.json').exists()
                    interrupted = e.snapshot(fresh_state, fresh_dir)
                    assert {n: interrupted[n]['id'] for n in ('api', 'worker')} == {
                        n: partial[n]['id'] for n in ('api', 'worker')}
                    if lifecycle == 'recovery':
                        # Real retry refuses changed baseline/private input before any recreate.
                        for path in (state_dir / 'deployment-before.json', directory / 'telegram.env'):
                            original = path.read_bytes()
                            e.write_private(path, original + b'\n')
                            rejected = subprocess.run(command, capture_output=True, timeout=40, env=environment)
                            assert rejected.returncode == 1 and rejected.stdout.strip() == b'EGRESS_BUNDLE_CHANGED'
                            assert not (state_dir / 'deployment-after.json').exists()
                            e.write_private(path, original)
                    operator('recover')
                    state = e.verify(state_dir)
                    values = e.route_values(state, state_dir)
                    live, base = e.compose_prefix(state, state_dir), e.compose_prefix(state, state_dir, overlay=False)
                    prefix = [*live, '-f', str(root / 'infra/telegram-egress/compose.test.yaml'), '--profile', 'test']
                    for name, raw in before_files.items():
                        assert (state_dir / 'recovery-v1' / name).read_bytes() == raw
                        if name != 'state.json':
                            assert (state_dir / name).read_bytes() == raw
                    assert (state_dir / 'deployment-before.json').read_bytes() == original_before
                    # Explicit completed-response retry is read/verify only, no recreate.
                    recovered = e.snapshot(state, state_dir)
                    recovered_ids = {n: recovered[n]['id'] for n in ('api', 'worker')}
                    operator('recover')
                    retried = e.snapshot(state, state_dir)
                    assert recovered_ids == {n: retried[n]['id'] for n in ('api', 'worker')}

            if not lifecycle.startswith('legacy-'):
                current_mapping = mapping_evidence()
                runtime_deployed = assert_runtime_boundary()
                operator('preflight')
                assert (root / '.env').read_bytes() == original_env
                e.compare_deployment(json.loads((state_dir / 'deployment-before.json').read_text()),
                                     e.snapshot(state, state_dir), state)
                e.caller_probe(state, state_dir)
                before_env = (directory / 'telegram.env').read_bytes()
                compose('stop', '--timeout', '1', 'telegram-egress')
                e.caller_probe(state, state_dir)
                operator('rollback')
            else:
                current_mapping = {'legacy_rollback_only': True}
                runtime_deployed = partial
                before_env = staged_inputs
            runtime_rolled_back = assert_runtime_boundary()
            assert (root / '.env').read_bytes() == original_env + b'ASM_TELEGRAM_ENABLED=false\n'
            assert (directory / 'telegram.env').read_bytes() == before_env
            compose('run', '--rm', '--no-deps', '-T', *local_database_args(), 'egress-checks', 'python',
                    'tests/test_telegram_egress_postgres.py', '--durable-receipt', 'after')
            await_process(durable, timeout=30)
            assertions = [json.loads(row) for row in (directory / 'assertions.jsonl').read_text().splitlines()]
            assert len(assertions) == 7 + lifecycle_index and all(row['result'] == 'PASS' for row in assertions)
            durable_before = json.loads((directory / 'durable-before.json').read_text())
            durable_after = json.loads((directory / 'durable-after.json').read_text())
            assert durable_before['database']['identity'] == durable_after['database']['identity'] == identity
            receipt = {'source_sha': source, 'image': e.IMAGE, 'image_id': state['image_id'],
                'E01': 'source/blob/private-config/offline-pinned-binary PASS',
                'E02': 'resolved opt-in/real all-callers mapping/stop/recreate/auth/DB/S3 PASS',
                'assertions': assertions, 'relay_controls': controls,
                'C8_01': {'runtime_disabled_empty_TG': True, 'staged_inputs_unchanged': True,
                    'https_settings_preserved': True, 'independent_baseline_before_prepare': True,
                    'runtime_input_bytes_preserved_except_disable': True,
                    'operational_sha256': e.sha(e.encoded(operational))},
                'C8_02': {'actual_database_identity': identity, 'postgres_id': postgres_id,
                    'callers': {phase: {name: data[name]['database_identity'] for name in ('api', 'worker')}
                        for phase, data in [('before', runtime_before), ('deployed', runtime_deployed),
                                            ('rolled_back', runtime_rolled_back)]}},
                'mapping': current_mapping,
                'deployment_before': json.loads((state_dir / 'deployment-before.json').read_text()),
                'deployment_after': (None if lifecycle.startswith('legacy-') else json.loads((state_dir / 'deployment-after.json').read_text())),
                'rollback': json.loads((state_dir / 'rollback.json').read_text()),
                'durable_before': json.loads((directory / 'durable-before.json').read_text()),
                'durable_after': json.loads((directory / 'durable-after.json').read_text())}
            if lifecycle in ('recovery', 'recover-stopped', 'recover-missing'):
                receipt['recovery'] = json.loads((state_dir / 'recovery.json').read_text())
                receipt['recovery'].update(exact_cli_sigkill_after_manifest=lifecycle == 'recovery',
                    relay_gap=lifecycle if lifecycle != 'recovery' else None,
                    baseline_and_staged_drift_rejected=lifecycle == 'recovery', original_generated_bytes_preserved=True,
                    completed_retry_without_recreate=True, immutable_catalog_retained_between_cases=True)
            receipt['interruptions'] = [json.loads(p.read_text()) for p in sorted(directory.glob('interruption-' + lifecycle + '-*.json'))]
            if lifecycle.startswith('legacy-'):
                receipt['legacy_retry'] = {'original_before_audit_staged_preserved': True, 'completed_retry_without_recreate': True,
                    'exact_disabled_delta': True, 'absent_deployment_after': True, 'missing_after_stop': lifecycle == 'legacy-stop'}
            lifecycle_receipts[lifecycle] = receipt
        reports = root / 'reports'
        reports.mkdir(exist_ok=True)
        (reports / 'telegram-egress.json').write_text(json.dumps({'source_sha': source,
            'lifecycles': lifecycle_receipts, 'assertions': assertions, 'corrected_mapping': corrected_mapping,
            'transition_guard': {'real_stopped_foreign_relay_rejected': True, 'config_bytes_drift_rejected': True},
            'docker': json.loads(run(['docker', 'version', '--format', '{{json .}}'])),
            'compose': run(['docker', 'compose', 'version', '--short']).decode().strip()}, indent=2) + '\n')
        print('TELEGRAM_EGRESS_E01_E05_PASS', flush=True)
    except Exception as error:
        # No private config, environment, process argv or raw Docker inspect output.
        print('TELEGRAM_EGRESS_TEST_FAILURE phase=' + phase + ' type=' + type(error).__name__, flush=True)
        trace = error.__traceback__
        while trace is not None:
            # Line/function only; never locals, source statements, argv or values.
            print('TEST_FAILURE_FRAME=' + trace.tb_frame.f_code.co_name + ':' + str(trace.tb_lineno), flush=True)
            trace = trace.tb_next
        if isinstance(error, e.EgressError):
            print(str(error), flush=True)
        # Preserve only fixture stage/error classes and aggregate event counts.
        # Never include exception messages, request paths, bodies or TLS material.
        for filename in ('wire-failures.jsonl', 'wire-stages.jsonl', 'wire-calls.jsonl'):
            path = directory / filename
            if path.exists():
                rows = [json.loads(line) for line in path.read_text().splitlines()]
                counts = {}
                for row in rows:
                    fields = ('event', 'operation') if filename == 'wire-calls.jsonl' else ('stage', 'error')
                    key = '/'.join(str(row.get(field, 'none')) for field in fields)
                    assert re.fullmatch('[A-Za-z0-9_/]{1,100}', key), 'UNSAFE_TEST_DIAGNOSTIC'
                    counts[key] = counts.get(key, 0) + 1
                print(filename + ' ' + json.dumps(counts, sort_keys=True), flush=True)
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
