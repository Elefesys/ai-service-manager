"""Mandatory isolated Docker29 reproduction; synthetic DNS, no Telegram requests."""

import ipaddress
import json
import os
import platform
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECT = "asm-docker29-mapping"


def run(args):
    result = subprocess.run(args, capture_output=True, timeout=120)
    if result.returncode:
        # This fixture has no private inputs/credentials. Preserve bounded Docker
        # startup errors rather than losing the cause of a failed isolated probe.
        print("DOCKER29_PROBE_COMMAND_FAILED=" + str(result.returncode), flush=True)
        print(result.stderr.decode(errors="replace")[-4096:], flush=True)
        result.check_returncode()
    return result.stdout


def main():
    assert os.environ.get("GITHUB_ACTIONS") == "true", "ISOLATED_RUNNER_REQUIRED"
    version = json.loads(run(["docker", "version", "--format", "{{json .}} "]))
    assert version["Server"]["Version"] == "29.8.2"
    assert version["Server"]["GitCommit"] == "8af9fe3"
    compose_version = run(["docker", "compose", "version", "--short"]).decode().strip()
    assert compose_version.lstrip("v") == "5.5.1"
    assert not run(
        ["docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=" + PROJECT]
    ).strip()
    assert not run(
        ["docker", "network", "ls", "-q", "--filter", "label=com.docker.compose.project=" + PROJECT]
    ).strip()
    networks = run(["docker", "network", "ls", "-q"]).decode().split()
    occupied = [
        ipaddress.ip_network(v["Subnet"])
        for n in json.loads(run(["docker", "network", "inspect", *networks]))
        for v in (n["IPAM"]["Config"] or [])
        if v.get("Subnet")
    ]
    subnet = next(
        s
        for s in ipaddress.ip_network("10.204.0.0/16").subnets(new_prefix=28)
        if all(s.version != v.version or not s.overlaps(v) for v in occupied)
    )
    relay, dns = str(subnet[2]), str(subnet[3])
    dynamic = list(subnet.subnets(prefixlen_diff=1))[1]
    os.umask(0o077)
    with tempfile.TemporaryDirectory(prefix="asm-docker29-probe-") as tmp:
        directory = Path(tmp)
        # A documentation-only AAAA makes the old flags=0 failure deterministic.
        # No query or request can reach public DNS/Telegram from this internal network.
        dns_code = """import socket,struct
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.bind(('0.0.0.0',53))
while True:
 data,peer=s.recvfrom(512); offset=12
 while data[offset]: offset+=data[offset]+1
 end=offset+5; kind=struct.unpack('!H',data[offset+1:offset+3])[0]
 address=socket.inet_pton(socket.AF_INET6,'2001:db8::91') if kind==28 else socket.inet_aton('203.0.113.91')
 answer=b'\\xc0\\x0c'+struct.pack('!HHIH',kind,1,5,len(address))+address
 s.sendto(data[:2]+struct.pack('!HHHHH',0x8180,1,1,0,0)+data[12:end]+answer,peer)
"""
        (directory / "dns.py").write_text(dns_code)
        (directory / "dns.py").chmod(0o644)
        hosts = ["api.telegram.org=" + relay, "api.telegram.org=::ffff:" + relay]
        services = {
            name: {
                "image": "asm-backend:local",
                "entrypoint": ["python", "-c", "import time; time.sleep(180)"],
                "extra_hosts": hosts,
                "dns": [dns],
                "networks": ["probe"],
            }
            for name in ("api", "worker", "telegram-operator")
        }
        services["dns"] = {
            "image": "asm-backend:local",
            "entrypoint": ["python", "/run/dns.py"],
            "read_only": True,
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges:true"],
            "sysctls": {"net.ipv4.ip_unprivileged_port_start": "0"},
            "volumes": [str(directory / "dns.py") + ":/run/dns.py:ro"],
            "networks": {"probe": {"ipv4_address": dns}},
        }
        model = {
            "services": services,
            "networks": {
                "probe": {
                    "internal": True,
                    "enable_ipv6": False,
                    "ipam": {
                        "config": [
                            {
                                "subnet": str(subnet),
                                # Keep fixed DNS .3 outside dynamic allocation even when
                                # Compose starts callers before the DNS service.
                                "ip_range": str(dynamic),
                            }
                        ]
                    },
                }
            },
        }
        path = directory / "compose.json"
        path.write_text(json.dumps(model))
        prefix = ["docker", "compose", "--project-name", PROJECT, "-f", str(path)]
        probe = """import socket,ipaddress,json,platform,pathlib
rows={}
for family in (socket.AF_UNSPEC,socket.AF_INET,socket.AF_INET6):
 rows[str(int(family))]=[str(ipaddress.ip_address(r[4][0])) for r in socket.getaddrinfo('api.telegram.org',443,family,socket.SOCK_STREAM,0,0)]
hosts=[line.split()[0] for line in pathlib.Path('/etc/hosts').read_text().splitlines() if 'api.telegram.org' in line.split()[1:]]
print(json.dumps({'hosts':hosts,'resolver':rows,'python':platform.python_version(),'libc':platform.libc_ver()}))
"""
        try:
            run([*prefix, "up", "-d", "--wait"])
            resolved = json.loads(run([*prefix, "config", "--format", "json"]))
            results = {}
            for name in ("api", "worker", "telegram-operator"):
                identity = run([*prefix, "ps", "-q", name]).decode().strip()
                info = json.loads(run(["docker", "inspect", identity]))[0]
                allocated = info["NetworkSettings"]["Networks"][PROJECT + "_probe"]["IPAddress"]
                assert ipaddress.ip_address(allocated) in dynamic and allocated not in {relay, dns}
                row = json.loads(run(["docker", "exec", identity, "python", "-c", probe]))
                assert sorted(resolved["services"][name]["extra_hosts"]) == sorted(hosts)
                assert sorted(info["HostConfig"]["ExtraHosts"]) == sorted(
                    v.replace("=", ":", 1) for v in hosts
                )
                assert row["hosts"] == [relay, relay]
                assert all(
                    row["resolver"][f] and set(row["resolver"][f]) == {relay} for f in ("0", "2")
                )
                assert row["resolver"]["10"] and set(row["resolver"]["10"]) == {"2001:db8::91"}
                results[name] = {
                    **row,
                    "model": resolved["services"][name]["extra_hosts"],
                    "host_config": info["HostConfig"]["ExtraHosts"],
                    "old_strict_mapping_rejected": True,
                    "caller_private_ip": allocated,
                }
            reports = ROOT / "reports"
            reports.mkdir(exist_ok=True)
            (reports / "docker29-mapping.json").write_text(
                json.dumps(
                    {
                        "source_sha": run(["git", "rev-parse", "HEAD"]).decode().strip(),
                        "docker": version,
                        "compose": compose_version,
                        "kernel": platform.release(),
                        "old_mapping": results,
                    },
                    indent=2,
                )
                + "\n"
            )
            print("DOCKER29_OLD_MAPPING_FAILURE_REPRODUCED_ALL_CALLERS")
        finally:
            run([*prefix, "down", "--remove-orphans", "--timeout", "2"])


if __name__ == "__main__":
    main()
