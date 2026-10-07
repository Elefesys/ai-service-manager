"""Prepare and guard one private, opt-in synthetic TEST Telegram route.

No profile evaluation, app patch, automatic Telegram setup or external HTTP probe.
Errors are deliberately bounded codes: provider configuration is never printed.
"""

import argparse
import copy
import fcntl
import hashlib
import ipaddress
import json
import os
import re
import stat
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

IMAGE = (
    "ghcr.io/xtls/xray-core@sha256:9a17fb7fcda36f80d041fc1f12f1d661d3f7c502572b2a6f2e4432534789a20b"
)
SOURCE = {
    "backend/src/asm/telegram/client.py": "525381357de76ea1c570fd864f8df5e9781a87e2",
    "backend/src/asm/telegram/config.py": "31cba499681270d708cdb55e7c8e44202c07b4b7",
}
CALLERS = ("api", "worker", "telegram-operator")
RUNTIME_FIELDS = ("ASM_AUTH_ORIGINS", "ASM_STORAGE_ENDPOINT")
ROOT = Path(__file__).resolve().parents[1]
SAFE_PATH = re.compile(r"/[A-Za-z0-9_./-]+")

LEGACY_SHA = "c29aabd36f4e81ee2d4b835bd921fa2de1ae5b14"
LEGACY_OVERLAY_BLOB = "5a6158a648d553fe80a917f6ebca8867c20bbfe6"
MIGRATION_FROM = "0b7e24ee425ebb429bf87dfe382cbd3fab883028"
MIGRATION_FROM_TREE = "14a4033b849c736235653a5a85ec9e5112bfe727"
MIGRATION_BASE = "14f794b650c935c47ab1e78474fda0d1df0a7277"
# Scheduler never uses Telegram HTTP. Keep its original ID/image so even rollback
# remains compatible with the predecessor's strict unrelated-container baseline.
MIGRATION_SERVICES = ("api", "worker")
MIGRATION_DEADLINE = None
# Exact accepted schema1 overlay, retained only to verify/recover the known partial state.
LEGACY_OVERLAY = b'# Opt-in only. Use the private route.env produced by prepare_telegram_egress.py.\n# Preserve the existing default gateway; Telegram alone resolves to this relay.\nx-egress-hosts: &egress-hosts\n  - api.telegram.org=${ASM_TELEGRAM_EGRESS_IP:?Prepare private egress state}\n  - api.telegram.org=::ffff:${ASM_TELEGRAM_EGRESS_IP:?Prepare private egress state}\nx-egress-networks: &egress-networks\n  default:\n    gw_priority: 1\n  telegram-egress: {}\nservices:\n  api:\n    extra_hosts: *egress-hosts\n    networks: *egress-networks\n  worker:\n    extra_hosts: *egress-hosts\n    networks: *egress-networks\n  telegram-operator:\n    extra_hosts: *egress-hosts\n    networks: *egress-networks\n  telegram-egress:\n    profiles: [telegram-egress]\n    image: ${TELEGRAM_EGRESS_IMAGE:?Missing telegram-egress/image.lock.env}\n    platform: linux/amd64\n    user: "${ASM_TELEGRAM_EGRESS_UID:?}:${ASM_TELEGRAM_EGRESS_GID:?}"\n    command: [run, -config, /run/telegram-egress/config.json]\n    read_only: true\n    # Shadow the publisher\'s writable anonymous VOLUME declarations.\n    tmpfs:\n      - /usr/local/etc/xray:ro,noexec,nosuid,size=64k\n      - /var/log/xray:ro,noexec,nosuid,size=64k\n    cap_drop: [ALL]\n    security_opt: [no-new-privileges:true]\n    sysctls:\n      net.ipv4.ip_unprivileged_port_start: "0"\n    pids_limit: 64\n    mem_limit: 96m\n    cpus: 0.5\n    ulimits:\n      nofile: {soft: 512, hard: 512}\n    restart: unless-stopped\n    stop_grace_period: 10s\n    logging: {driver: none}\n    volumes:\n      - type: bind\n        source: ${ASM_TELEGRAM_EGRESS_CONFIG:?Prepare private egress state}\n        target: /run/telegram-egress/config.json\n        read_only: true\n        bind: {create_host_path: false}\n    networks:\n      telegram-egress:\n        ipv4_address: ${ASM_TELEGRAM_EGRESS_IP:?}\nnetworks:\n  telegram-egress:\n    name: ${ASM_TELEGRAM_EGRESS_NETWORK:?}\n    driver: bridge\n    enable_ipv6: false\n    labels:\n      asm.scope: synthetic-telegram-test\n    ipam:\n      config:\n        - subnet: ${ASM_TELEGRAM_EGRESS_SUBNET:?}\n          gateway: ${ASM_TELEGRAM_EGRESS_GATEWAY:?}\n          # Reserve the lower half for fixed endpoints, even while relay is stopped.\n          ip_range: ${ASM_TELEGRAM_EGRESS_DYNAMIC_RANGE:?}\n'


class EgressError(Exception):
    """Only a non-sensitive fixed diagnostic code may cross the CLI boundary."""


def require(condition, code):
    if not condition:
        raise EgressError(code)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def strict_json(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            require(key not in out, "EGRESS_DUPLICATE_JSON_KEY")
            out[key] = value
        return out

    def invalid(_):
        raise EgressError("EGRESS_NONFINITE_JSON")

    require(len(raw) <= 65536, "EGRESS_JSON_LIMIT")
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
    except (ValueError, UnicodeError, RecursionError):
        raise EgressError("EGRESS_INVALID_JSON") from None


def checked_path(path, *, directory=False):
    path = Path(path).absolute()
    require(SAFE_PATH.fullmatch(str(path)) is not None, "EGRESS_UNSAFE_PATH")
    for part in (path, *path.parents):
        require(not stat.S_ISLNK(part.lstat().st_mode), "EGRESS_SYMLINK")
    info = path.stat()
    require(info.st_uid == os.getuid(), "EGRESS_WRONG_OWNER")
    require(stat.S_IMODE(info.st_mode) == (0o700 if directory else 0o600), "EGRESS_PRIVATE_MODE")
    require(
        stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode), "EGRESS_FILE_TYPE"
    )
    return path


def private_bytes(path):
    path = checked_path(path)
    checked_path(path.parent, directory=True)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        value = os.fstat(fd)
        require(stat.S_ISREG(value.st_mode) and value.st_uid == os.getuid(), "EGRESS_FILE_CHANGED")
        require(
            stat.S_IMODE(value.st_mode) == 0o600 and value.st_size <= 65536,
            "EGRESS_PRIVATE_MODE_OR_LIMIT",
        )
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(65537)
        require(len(data) <= 65536, "EGRESS_JSON_LIMIT")
        return data
    finally:
        os.close(fd)


def write_private(path, data, *, private_parent=True):
    path = Path(path)
    if private_parent:
        checked_path(path.parent, directory=True)
    else:
        info = path.parent.lstat()
        require(
            stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and not info.st_mode & 0o022,
            "EGRESS_ENV_PARENT",
        )
    if path.exists() or path.is_symlink():
        checked_path(path)
    fd, temp = tempfile.mkstemp(prefix=".egress-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def minimal_config(profile, relay_ip, relay_ipv6=None):
    """Copy only the single selected VLESS/TCP/REALITY/Vision connection."""
    require(isinstance(profile, dict), "EGRESS_PROFILE_SHAPE")
    choices = profile.get("outbounds")
    require(isinstance(choices, list) and len(choices) <= 16, "EGRESS_PROFILE_SHAPE")
    choices = [v for v in choices if isinstance(v, dict) and v.get("protocol") == "vless"]
    require(len(choices) == 1, "EGRESS_ONE_SELECTED_CONNECTION_REQUIRED")
    outbound = choices[0]
    require(
        not (set(outbound) - {"tag", "protocol", "settings", "streamSettings", "mux"}),
        "EGRESS_OUTBOUND_FIELDS",
    )
    require(isinstance(outbound.get("mux", {}), dict), "EGRESS_MUX_SHAPE")
    require(outbound.get("mux", {}).get("enabled", False) is False, "EGRESS_MULTIPLEX_FORBIDDEN")
    settings = outbound.get("settings", {})
    require(isinstance(settings, dict) and isinstance(settings.get("vnext"), list), "EGRESS_VNEXT")
    require(set(settings) == {"vnext"} and len(settings["vnext"]) == 1, "EGRESS_VNEXT")
    server = settings["vnext"][0]
    require(isinstance(server, dict), "EGRESS_SERVER_FIELDS")
    require(set(server) == {"address", "port", "users"}, "EGRESS_SERVER_FIELDS")
    address = server["address"]
    require(
        isinstance(address, str)
        and 1 <= len(address) <= 253
        and re.fullmatch(r"[A-Za-z0-9.:-]+", address) is not None,
        "EGRESS_SERVER_ADDRESS",
    )
    try:
        ip = ipaddress.ip_address(address)
        require(
            not (ip.is_loopback or ip.is_unspecified or ip.is_multicast or ip.is_link_local),
            "EGRESS_SERVER_ADDRESS",
        )
    except ValueError:
        require(
            re.fullmatch(r"(?=.{1,253}$)[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*", address) is not None,
            "EGRESS_SERVER_ADDRESS",
        )
    require(type(server["port"]) is int and 1 <= server["port"] <= 65535, "EGRESS_SERVER_PORT")
    require(isinstance(server["users"], list) and len(server["users"]) == 1, "EGRESS_ONE_USER")
    user = server["users"][0]
    require(isinstance(user, dict), "EGRESS_USER_FIELDS")
    require(set(user) <= {"id", "encryption", "flow", "level"}, "EGRESS_USER_FIELDS")
    require(str(UUID(user["id"])) == user["id"].lower(), "EGRESS_USER_ID")
    require(
        user.get("encryption") == "none" and user.get("flow") == "xtls-rprx-vision",
        "EGRESS_VISION_REQUIRED",
    )
    stream = outbound.get("streamSettings", {})
    require(isinstance(stream, dict), "EGRESS_STREAM_FIELDS")
    require(
        set(stream) <= {"network", "security", "realitySettings", "tcpSettings", "rawSettings"},
        "EGRESS_STREAM_FIELDS",
    )
    require(
        stream.get("network") in {"tcp", "raw"} and stream.get("security") == "reality",
        "EGRESS_REALITY_TCP_REQUIRED",
    )
    for key in ("tcpSettings", "rawSettings"):
        if key in stream:
            require(
                stream[key] in ({}, {"header": {"type": "none"}}), "EGRESS_TCP_HEADER_FORBIDDEN"
            )
    reality = stream.get("realitySettings", {})
    require(isinstance(reality, dict), "EGRESS_REALITY_FIELDS")
    require(
        set(reality)
        <= {
            "serverName",
            "fingerprint",
            "publicKey",
            "password",
            "shortId",
            "spiderX",
            "show",
            "mldsa65Verify",
        },
        "EGRESS_REALITY_FIELDS",
    )
    require(reality.get("show", False) is False, "EGRESS_REALITY_DEBUG_FORBIDDEN")
    require(
        isinstance(reality.get("serverName"), str)
        and re.fullmatch(r"[A-Za-z0-9.-]{1,253}", reality["serverName"]) is not None,
        "EGRESS_REALITY_NAME",
    )
    require(
        reality.get("fingerprint")
        in {
            "chrome",
            "firefox",
            "safari",
            "ios",
            "android",
            "edge",
            "360",
            "qq",
            "random",
            "randomized",
        },
        "EGRESS_FINGERPRINT",
    )
    keys = [key for key in ("publicKey", "password") if key in reality]
    require(
        len(keys) == 1 and re.fullmatch(r"[A-Za-z0-9_-]{43}", reality[keys[0]]) is not None,
        "EGRESS_REALITY_KEY",
    )
    require(
        isinstance(reality.get("shortId"), str)
        and re.fullmatch(r"(?:[0-9a-fA-F]{2}){0,8}", reality["shortId"]) is not None,
        "EGRESS_SHORT_ID",
    )
    if "spiderX" in reality:
        require(
            isinstance(reality["spiderX"], str)
            and reality["spiderX"].startswith("/")
            and len(reality["spiderX"]) <= 256
            and not any(ord(x) < 32 for x in reality["spiderX"]),
            "EGRESS_SPIDER_PATH",
        )
    ip = ipaddress.IPv4Address(relay_ip)
    require(
        ip.is_private and not (ip.is_loopback or ip.is_unspecified or ip.is_link_local),
        "EGRESS_PRIVATE_IPV4",
    )
    selected = {
        "tag": "selected",
        "protocol": "vless",
        "settings": {
            "vnext": [
                {
                    "address": address,
                    "port": server["port"],
                    "users": [{k: user[k] for k in ("id", "encryption", "flow")}],
                }
            ]
        },
        "streamSettings": stream,
        "mux": {"enabled": False},
    }
    result = {
        "log": {"access": "none", "error": "none", "loglevel": "none", "dnsLog": False},
        "inbounds": [
            {
                "tag": "telegram-only",
                "listen": str(ip),
                "port": 443,
                "protocol": "dokodemo-door",
                "settings": {
                    "address": "api.telegram.org",
                    "port": 443,
                    "network": "tcp",
                    "followRedirect": False,
                },
                "sniffing": {"enabled": False},
            }
        ],
        "outbounds": [{"tag": "deny", "protocol": "blackhole", "settings": {}}, selected],
        "routing": {
            "domainStrategy": "AsIs",
            "rules": [
                {
                    "type": "field",
                    "inboundTag": ["telegram-only"],
                    "domain": ["full:api.telegram.org"],
                    "port": "443",
                    "network": "tcp",
                    "outboundTag": "selected",
                },
                {"type": "field", "network": "tcp,udp", "outboundTag": "deny"},
            ],
        },
    }

    if relay_ipv6 is not None:
        address6 = ipaddress.IPv6Address(relay_ipv6)
        require(address6 in ipaddress.ip_network("fd00::/8"), "EGRESS_PRIVATE_IPV6")
        inbound = copy.deepcopy(result["inbounds"][0])
        inbound.update(tag="telegram-only-v6", listen=str(address6))
        result["inbounds"].append(inbound)
        result["routing"]["rules"][0]["inboundTag"].append("telegram-only-v6")
    return result


def select_subnet(networks, routes, previous=None, own_name=None):
    occupied = []
    own = None
    for network in networks:
        blocks = network.get("IPAM", {}).get("Config") or []
        if network.get("Name") == own_name:
            require(
                network.get("Labels", {}).get("asm.scope") == "synthetic-telegram-test",
                "EGRESS_NETWORK_COLLISION",
            )
            require(
                previous is not None
                and [v["Subnet"] for v in blocks if ":" not in v["Subnet"]] == [previous],
                "EGRESS_NETWORK_CHANGED",
            )
            own = ipaddress.ip_network(previous)
            require(
                blocks[0].get("IPRange") == str(list(own.subnets(prefixlen_diff=1))[1]),
                "EGRESS_DYNAMIC_RANGE_CHANGED",
            )
            continue
        occupied.extend(ipaddress.ip_network(v["Subnet"]) for v in blocks if v.get("Subnet"))
    for route in routes:
        destination = route.get("dst", "default")
        if destination == "default":
            continue
        block = ipaddress.ip_network(destination, strict=False)
        if own and (block == own or (block.prefixlen == 32 and block.subnet_of(own))):
            continue
        occupied.append(block)
    candidates = (
        [ipaddress.ip_network(previous)]
        if previous
        else (
            block
            for pool in ("10.203.0.0/16", "172.29.0.0/16", "192.168.240.0/20")
            for block in ipaddress.ip_network(pool).subnets(new_prefix=28)
        )
    )
    for candidate in candidates:
        if all(
            candidate.version != used.version or not candidate.overlaps(used) for used in occupied
        ):
            return str(candidate)
    raise EgressError("EGRESS_NO_NONOVERLAPPING_SUBNET")


def command(args, *, timeout=40, environment=None):
    if MIGRATION_DEADLINE is not None:
        remaining = MIGRATION_DEADLINE - time.monotonic()
        require(remaining > 0, "EGRESS_MIGRATION_DEADLINE")
        timeout = min(timeout, remaining)
    result = subprocess.run(
        args, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout, env=environment
    )
    require(result.returncode == 0, "EGRESS_COMMAND_FAILED")
    return result.stdout


def source_check(expected):
    require(re.fullmatch(r"[0-9a-f]{40}", expected) is not None, "EGRESS_EXPECTED_SHA")
    require(
        command(["git", "-C", str(ROOT), "rev-parse", "HEAD"]).decode().strip() == expected,
        "EGRESS_CHECKOUT_MISMATCH",
    )
    require(
        not command(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=all"]),
        "EGRESS_DIRTY_SOURCE",
    )
    for path, expected_blob in SOURCE.items():
        data = (ROOT / path).read_bytes()
        require(
            hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            == expected_blob,
            "EGRESS_APP_SOURCE_CHANGED",
        )
    pins = (ROOT / "infra/telegram-egress/image.lock.env").read_text().splitlines()
    require(
        [v for v in pins if v and not v.startswith("#")] == ["TELEGRAM_EGRESS_IMAGE=" + IMAGE],
        "EGRESS_IMAGE_PIN_CHANGED",
    )


def image_check(config, uid, gid):
    info = json.loads(command(["docker", "image", "inspect", IMAGE]))[0]
    require(
        info["Os"] == "linux"
        and info["Architecture"] == "amd64"
        and IMAGE in info.get("RepoDigests", []),
        "EGRESS_IMAGE_IDENTITY",
    )
    options = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--user",
        f"{uid}:{gid}",
        "--pids-limit=64",
        "--memory=96m",
        "--cpus=0.5",
        "--log-driver=none",
        "--entrypoint=/usr/local/bin/xray",
    ]
    require(b"Xray 26.9.9" in command([*options, IMAGE, "version"]), "EGRESS_BINARY_VERSION")
    command(
        [
            *options,
            "--mount",
            f"type=bind,source={config},target=/run/config.json,readonly",
            IMAGE,
            "run",
            "-test",
            "-config",
            "/run/config.json",
        ]
    )
    return info["Id"]


def route_values(state, directory):
    subnet = ipaddress.ip_network(state["subnet"])
    result = {
        "ASM_TELEGRAM_EGRESS_SUBNET": str(subnet),
        "ASM_TELEGRAM_EGRESS_DYNAMIC_RANGE": str(list(subnet.subnets(prefixlen_diff=1))[1]),
        "ASM_TELEGRAM_EGRESS_GATEWAY": str(subnet[1]),
        "ASM_TELEGRAM_EGRESS_IP": str(subnet[2]),
        "ASM_TELEGRAM_EGRESS_NETWORK": state["project"] + "_telegram-egress",
        "ASM_TELEGRAM_EGRESS_CONFIG": str(generated_directory(state, directory) / "config.json"),
        "ASM_TELEGRAM_EGRESS_UID": str(state["uid"]),
        "ASM_TELEGRAM_EGRESS_GID": str(state["gid"]),
    }

    if state.get("version") in {2, 3}:
        block = ipaddress.ip_network(state["subnet6"])
        result.update(
            {
                "ASM_TELEGRAM_EGRESS_SUBNET6": str(block),
                "ASM_TELEGRAM_EGRESS_GATEWAY6": str(block[1]),
                "ASM_TELEGRAM_EGRESS_IPV6": str(block[2]),
                "ASM_TELEGRAM_EGRESS_DYNAMIC_RANGE6": str(list(block.subnets(prefixlen_diff=1))[1]),
                "ASM_TELEGRAM_EGRESS_NETWORK6": state["project"] + "_telegram-egress-v6",
            }
        )
    return result


def generated_directory(state, directory):
    generation = state.get("generation", ".")
    require(generation in {".", "recovery-v2"}, "EGRESS_GENERATION")
    return directory / generation


def route_env(values):
    require(
        all(re.fullmatch(r"[A-Za-z0-9_./:-]+", v) for v in values.values()),
        "EGRESS_UNSAFE_ENV_VALUE",
    )
    return "".join(f"{k}={v}\n" for k, v in sorted(values.items())).encode()


def state_directory(path):
    # Check the requested spelling before resolving it: resolve() alone would
    # hide a symlink component, including a symlink followed by '..'.
    requested = Path(path).absolute()
    require(SAFE_PATH.fullmatch(str(requested)) is not None, "EGRESS_UNSAFE_PATH")
    for part in (requested, *requested.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        require(not stat.S_ISLNK(info.st_mode), "EGRESS_SYMLINK")
    directory = requested.resolve()
    require(not directory.is_relative_to(ROOT.resolve()), "EGRESS_PRIVATE_STATE_OUTSIDE_CHECKOUT")
    return directory


def runtime_overlay(state):
    # Let Compose parse the accepted dotenv syntax without source/eval. Only two
    # non-Telegram values leave this in-memory model; never serialize its secrets.
    for path in (ROOT / ".env", Path(state["telegram_env"])):
        require(checked_path(path).stat().st_size <= 65536, "EGRESS_ENV_LIMIT")
    model = json.loads(
        command(
            [
                "docker",
                "compose",
                "--project-directory",
                str(ROOT),
                "--project-name",
                state["project"],
                "--env-file",
                str(ROOT / "infra/images.lock.env"),
                "--env-file",
                str(ROOT / ".env"),
                "--env-file",
                state["telegram_env"],
                "-f",
                str(ROOT / "compose.yaml"),
                "config",
                "--format",
                "json",
            ],
            environment=clean_environment(),
        )
    )
    services = {}
    for name in ("api", "worker"):
        values = {key: model["services"][name]["environment"][key] for key in RUNTIME_FIELDS}
        require(
            all(
                isinstance(v, str) and 0 < len(v) <= 4096 and not any(ord(c) < 32 for c in v)
                for v in values.values()
            ),
            "EGRESS_RUNTIME_INPUT_SHAPE",
        )
        services[name] = {"environment": values}
    require(services["api"] == services["worker"], "EGRESS_RUNTIME_INPUT_MISMATCH")
    # JSON is a Compose YAML subset; literal '$' must survive its second parse.
    return encoded({"services": services}).replace(b"$", b"$$")


def verify_runtime(state, directory):
    raw = private_bytes(generated_directory(state, directory) / "runtime.json")
    require(
        sha(raw) == state["runtime_sha256"] and raw == runtime_overlay(state),
        "EGRESS_RUNTIME_INPUTS_CHANGED",
    )


def prepare(args):
    directory = state_directory(args.state_dir)
    source_check(args.accepted_sha)
    profile = checked_path(args.profile)
    raw = private_bytes(profile)
    require(re.fullmatch(r"[a-z][a-z0-9-]{0,40}", args.project) is not None, "EGRESS_PROJECT")
    if not directory.exists():
        directory.mkdir(mode=0o700, parents=True)
    checked_path(directory, directory=True)
    telegram_env = checked_path(args.telegram_env)
    require(
        telegram_env != profile and telegram_env != directory / "config.json",
        "EGRESS_INPUT_PATH_COLLISION",
    )
    old = (
        strict_json(private_bytes(directory / "state.json"))
        if (directory / "state.json").exists()
        else None
    )
    ids = command(["docker", "network", "ls", "-q"]).decode().split()
    networks = json.loads(command(["docker", "network", "inspect", *ids])) if ids else []
    routes = json.loads(command(["ip", "-j", "-4", "route", "show", "table", "all"]))
    subnet = select_subnet(
        networks, routes, old["subnet"] if old else None, args.project + "_telegram-egress"
    )
    routes6 = json.loads(command(["ip", "-j", "-6", "route", "show", "table", "all"]))
    subnet6 = select_subnet6(
        networks, routes6, old.get("subnet6") if old else None, args.project + "_telegram-egress-v6"
    )
    config = encoded(
        minimal_config(
            strict_json(raw),
            str(ipaddress.ip_network(subnet)[2]),
            str(ipaddress.ip_network(subnet6)[2]),
        )
    )
    state = {
        "version": 2,
        "source_sha": args.accepted_sha,
        "project": args.project,
        "subnet": subnet,
        "subnet6": subnet6,
        "uid": os.getuid(),
        "gid": os.getgid(),
        "profile": str(profile),
        "profile_sha256": sha(raw),
        "telegram_env": str(telegram_env),
        "config_sha256": sha(config),
        "image": IMAGE,
    }
    runtime = runtime_overlay(state)
    state["runtime_sha256"] = sha(runtime)
    if old:
        require(all(old.get(k) == v for k, v in state.items()), "EGRESS_PREPARATION_DRIFT")
        verify(directory)
        return
    require(not any(directory.iterdir()), "EGRESS_STATE_DIRECTORY_NOT_EMPTY")
    with tempfile.TemporaryDirectory(prefix=".verify-", dir=directory) as temporary:
        temporary = Path(temporary)
        write_private(temporary / "config.json", config)
        state["image_id"] = image_check(temporary / "config.json", state["uid"], state["gid"])
    write_private(directory / "config.json", config)
    write_private(directory / "runtime.json", runtime)
    write_private(directory / "route.env", route_env(route_values(state, directory)))
    write_private(directory / "state.json", encoded(state))


def verify(directory, *, legacy=False, accepted_sha=None, saved_state=None):
    directory = checked_path(state_directory(directory), directory=True)
    state = (
        saved_state
        if saved_state is not None
        else strict_json(private_bytes(directory / "state.json"))
    )
    require(
        state.get("version") in ({1} if legacy else {2, 3}) and state.get("image") == IMAGE,
        "EGRESS_STATE_VERSION",
    )
    if legacy:
        require(state["source_sha"] == LEGACY_SHA, "EGRESS_LEGACY_SOURCE")
    require(state["uid"] == os.getuid() and state["gid"] == os.getgid(), "EGRESS_STATE_OWNER")
    source_check(accepted_sha if legacy else state["source_sha"])
    if state.get("version") == 3:
        migration_manifest(directory, state)
        bundle, _, _, _ = migration_prepared(directory)
        completed = strict_json(private_bytes(bundle / "forward-complete.json"))
        require(
            completed["state_sha256"] == sha(encoded(state))
            and completed["intent_sha256"] == state["migration_intent_sha256"]
            and not (bundle / "rollback-intent.json").exists(),
            "EGRESS_MIGRATION_COMPLETED_STATE_REQUIRED",
        )
    return verify_state_contents(state, directory, legacy=legacy)


def verify_state_contents(state, directory, *, legacy=False):
    """Configuration checks shared with the separately attested exact predecessor."""
    raw = private_bytes(state["profile"])
    require(sha(raw) == state["profile_sha256"], "EGRESS_PROFILE_CHANGED")
    values = route_values(state, directory)
    generated = generated_directory(state, directory)
    config = private_bytes(generated / "config.json")
    require(
        config
        == encoded(
            minimal_config(
                strict_json(raw),
                values["ASM_TELEGRAM_EGRESS_IP"],
                values.get("ASM_TELEGRAM_EGRESS_IPV6"),
            )
        )
        and sha(config) == state["config_sha256"],
        "EGRESS_CONFIG_CHANGED",
    )
    require(private_bytes(generated / "route.env") == route_env(values), "EGRESS_MAPPING_CHANGED")
    checked_path(state["telegram_env"])
    verify_runtime(state, directory)
    require(
        image_check(generated / "config.json", state["uid"], state["gid"]) == state["image_id"],
        "EGRESS_IMAGE_CHANGED",
    )
    ids = command(["docker", "network", "ls", "-q"]).decode().split()
    networks = json.loads(command(["docker", "network", "inspect", *ids])) if ids else []
    routes = json.loads(command(["ip", "-j", "-4", "route", "show", "table", "all"]))
    require(
        select_subnet(networks, routes, state["subnet"], values["ASM_TELEGRAM_EGRESS_NETWORK"])
        == state["subnet"],
        "EGRESS_NETWORK_CHANGED",
    )
    if not legacy:
        routes6 = json.loads(command(["ip", "-j", "-6", "route", "show", "table", "all"]))
        require(
            select_subnet6(
                networks, routes6, state["subnet6"], values["ASM_TELEGRAM_EGRESS_NETWORK6"]
            )
            == state["subnet6"],
            "EGRESS_NETWORK_CHANGED",
        )
    return state


def compose_prefix(state, directory, *, overlay=True, operator_inputs=False):
    args = [
        "docker",
        "compose",
        "--project-directory",
        str(ROOT),
        "--project-name",
        state["project"],
        "--env-file",
        str(ROOT / "infra/images.lock.env"),
        "--env-file",
        str(ROOT / ".env"),
    ]
    # The base env supplies credentials; runtime.json preserves only the two
    # accepted non-TG settings from both inputs. Staged TG stays operator-only.
    if operator_inputs:
        args += ["--env-file", state["telegram_env"]]
    args += [
        "--env-file",
        str(ROOT / "infra/telegram-egress/image.lock.env"),
        "--env-file",
        str(generated_directory(state, directory) / "route.env"),
        "-f",
        str(ROOT / "compose.yaml"),
        "-f",
        str(generated_directory(state, directory) / "runtime.json"),
    ]
    if overlay:
        args += [
            "-f",
            str(directory / "recovery-v1/compose.yaml")
            if state.get("version") == 1
            else str(ROOT / "infra/telegram-egress/compose.yaml"),
            "--profile",
            "telegram-egress",
        ]
    if state.get("version") == 3:
        migration_manifest(directory, state)
        args += ["-f", str(directory / "migration-v3/images-after.json")]
    return args + ["--profile", "telegram-operator"]


def clean_environment():
    # Compose environment files, not unrelated ambient shell overrides, are authoritative.
    return {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("ASM_", "TG_", "PG_", "STORAGE_", "TELEGRAM_EGRESS_", "COMPOSE_"))
        and k not in {"PYTHON_IMAGE", "UV_IMAGE", "NODE_IMAGE", "WEB_IMAGE", "DB_IMAGE"}
    }


def validate_model(base, model, values):
    for name, service in base["services"].items():
        actual = model["services"][name]
        if name in CALLERS:
            expected = dict(service)
            expected["extra_hosts"] = sorted(
                [
                    "api.telegram.org=" + values["ASM_TELEGRAM_EGRESS_IP"],
                    "api.telegram.org="
                    + values.get(
                        "ASM_TELEGRAM_EGRESS_IPV6", "::ffff:" + values["ASM_TELEGRAM_EGRESS_IP"]
                    ),
                ]
            )
            expected["networks"] = {"default": {"gw_priority": 1}, "telegram-egress": {}}
            if "ASM_TELEGRAM_EGRESS_IPV6" in values:
                expected["networks"]["telegram-egress-v6"] = {}
            for field in set(actual) | set(expected):
                require(
                    actual.get(field) == expected.get(field),
                    f"EGRESS_CALLER_MODEL_DRIFT_{name}_{field}",
                )
        else:
            require(actual == service, "EGRESS_UNRELATED_SERVICE_DRIFT")
    require(
        model["networks"]["default"] == base["networks"]["default"],
        "EGRESS_DEFAULT_NETWORK_CHANGED",
    )
    relay = model["services"]["telegram-egress"]
    require(
        relay["image"] == IMAGE
        and relay["user"]
        == values["ASM_TELEGRAM_EGRESS_UID"] + ":" + values["ASM_TELEGRAM_EGRESS_GID"],
        "EGRESS_RELAY_IDENTITY",
    )
    require(
        not relay.get("ports") and not relay.get("environment") and not relay.get("depends_on"),
        "EGRESS_RELAY_EXPOSURE",
    )
    require(
        relay["read_only"] is True
        and relay["cap_drop"] == ["ALL"]
        and relay["security_opt"] == ["no-new-privileges:true"],
        "EGRESS_RELAY_PRIVILEGE",
    )
    require(
        len(relay["volumes"]) == 1
        and relay["volumes"][0]["read_only"] is True
        and relay["volumes"][0]["source"] == values["ASM_TELEGRAM_EGRESS_CONFIG"],
        "EGRESS_RELAY_MOUNT",
    )
    expected_networks = {"telegram-egress": {"ipv4_address": values["ASM_TELEGRAM_EGRESS_IP"]}}
    if "ASM_TELEGRAM_EGRESS_IPV6" in values:
        expected_networks["telegram-egress-v6"] = {
            "ipv6_address": values["ASM_TELEGRAM_EGRESS_IPV6"]
        }
        network = model["networks"]["telegram-egress-v6"]
        require(
            network["internal"]
            and network["enable_ipv6"]
            and not network["enable_ipv4"]
            and network["driver"] == "bridge"
            and network["name"] == values["ASM_TELEGRAM_EGRESS_NETWORK6"]
            and network["ipam"]["config"]
            == [
                {
                    "subnet": values["ASM_TELEGRAM_EGRESS_SUBNET6"],
                    "gateway": values["ASM_TELEGRAM_EGRESS_GATEWAY6"],
                    "ip_range": values["ASM_TELEGRAM_EGRESS_DYNAMIC_RANGE6"],
                }
            ],
            "EGRESS_IPV6_MODEL_DRIFT",
        )
    require(relay["networks"] == expected_networks, "EGRESS_RELAY_NETWORK")


def checked_model(state, directory):
    verify_runtime(state, directory)
    env = clean_environment()
    base = json.loads(
        command(
            [*compose_prefix(state, directory, overlay=False), "config", "--format", "json"],
            environment=env,
        )
    )
    model = json.loads(
        command([*compose_prefix(state, directory), "config", "--format", "json"], environment=env)
    )
    validate_model(base, model, route_values(state, directory))
    return model


def snapshot(state, directory, *, disabled=True):
    model = checked_model(state, directory)
    return runtime_snapshot(state, directory, model, source_image_check, disabled=disabled)


def runtime_snapshot(state, directory, model, check_image, *, disabled=True):
    ids = (
        command([*compose_prefix(state, directory), "ps", "-q"], environment=clean_environment())
        .decode()
        .split()
    )
    containers = json.loads(command(["docker", "inspect", *ids])) if ids else []
    result = {}
    for container in containers:
        name = container["Config"]["Labels"]["com.docker.compose.service"]
        values = dict(v.split("=", 1) for v in container["Config"]["Env"] if "=" in v)
        if name in {"api", "worker"} and disabled:
            require(
                values.get("ASM_TELEGRAM_ENABLED") == "false",
                "EGRESS_RUNNING_TELEGRAM_MUST_BE_DISABLED",
            )
        if name in {"api", "worker"}:
            check_image(container["Image"])
            require(
                all(
                    values.get(k) == str(v)
                    for k, v in model["services"][name]["environment"].items()
                    if k != "ASM_TELEGRAM_ENABLED"
                ),
                "EGRESS_RUNNING_ENVIRONMENT_DRIFT",
            )
        result[name] = {
            "id": container["Id"],
            "image": container["Image"],
            # Never persist environment values; include DB/S3/TG/TLS identity
            # in the preservation check. Rollback deliberately changes enabled.
            "environment_sha256": sha(
                encoded({k: v for k, v in values.items() if k != "ASM_TELEGRAM_ENABLED"})
            ),
            "process_sha256": sha(
                encoded({k: container["Config"].get(k) for k in ("Cmd", "Entrypoint", "User")})
            ),
            # Docker constructs this array from a Go map: order is not identity.
            # Preserve every mount/field, including duplicates, in canonical order.
            "mounts": sorted(
                [
                    {k: m.get(k) for k in ("Type", "Name", "Source", "Destination", "RW")}
                    for m in container["Mounts"]
                ],
                key=encoded,
            ),
            "networks": {
                k: {
                    v: n.get(v)
                    for v in (
                        ("IPAddress", "Gateway", "GlobalIPv6Address", "IPv6Gateway")
                        if k == state["project"] + "_telegram-egress-v6"
                        else ("IPAddress", "Gateway")
                    )
                }
                for k, n in container["NetworkSettings"]["Networks"].items()
            },
        }
        if name in {"api", "worker"}:
            result[name]["database_identity"] = database_identity(container["Id"])
    require(
        {"api", "worker", "postgres", "storage"} <= set(result), "EGRESS_RUNNING_STACK_REQUIRED"
    )
    require(
        result["api"]["database_identity"] == result["worker"]["database_identity"],
        "EGRESS_CALLER_DATABASE_MISMATCH",
    )
    return result


def database_identity(container):
    # Read the actual caller environment inside each running container. No URL,
    # role credential or business rows leave the container; transaction is read-only.
    query = (
        "SELECT current_database() AS database, "
        "(SELECT oid::bigint FROM pg_database WHERE datname=current_database()) AS database_oid, "
        "inet_server_addr()::text AS server_address, inet_server_port() AS server_port, "
        "pg_postmaster_start_time()::text AS postmaster_started"
    )
    probe = (
        "import json,os; from sqlalchemy import create_engine,text; "
        "engine=create_engine(os.environ['ASM_DATABASE_URL'],hide_parameters=True,"
        "connect_args={'connect_timeout':4})\n"
        "with engine.connect() as connection:\n"
        " connection.execute(text('SET TRANSACTION READ ONLY'))\n"
        " connection.execute(text('SET LOCAL statement_timeout=4000'))\n"
        " print(json.dumps(dict(connection.execute(text(" + repr(query) + ")).mappings().one())))\n"
    )
    identity = json.loads(command(["docker", "exec", container, "python", "-c", probe]))
    require(
        set(identity)
        == {"database", "database_oid", "server_address", "server_port", "postmaster_started"}
        and identity["database"] == "asm_local"
        and isinstance(identity["database_oid"], int)
        and identity["server_address"]
        and identity["postmaster_started"],
        "EGRESS_CALLER_DATABASE_IDENTITY",
    )
    return identity


def source_image_check(image):
    expected = {p.removeprefix("backend/src/"): v for p, v in SOURCE.items()}
    probe = "import hashlib,pathlib; expected=" + repr(expected) + "; "
    probe += "values={p:(pathlib.Path('/app/backend/src')/p).read_bytes() for p in expected}; "
    probe += "assert all(hashlib.sha1(b'blob '+str(len(v)).encode()+b'\\0'+v).hexdigest()==expected[p] for p,v in values.items())"
    command(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--entrypoint=python",
            image,
            "-c",
            probe,
        ]
    )


def caller_probe(state, directory):
    values = route_values(state, directory)
    expected = [values["ASM_TELEGRAM_EGRESS_IP"], values["ASM_TELEGRAM_EGRESS_IPV6"]]
    probe = (
        "import socket,ipaddress; expected={ipaddress.ip_address(v) for v in "
        + repr(expected)
        + "}; "
    )
    probe += "rows=[socket.getaddrinfo('api.telegram.org',443,f,socket.SOCK_STREAM,0,0) for f in (socket.AF_UNSPEC,socket.AF_INET,socket.AF_INET6)]; "
    probe += "assert all(rows); assert all(ipaddress.ip_address(x[4][0]) in expected for row in rows for x in row); "
    probe += (
        "assert {ipaddress.ip_address(x[4][0]) for x in rows[1]}=={ipaddress.ip_address("
        + repr(expected[0])
        + ")}; "
    )
    probe += (
        "assert {ipaddress.ip_address(x[4][0]) for x in rows[2]}=={ipaddress.ip_address("
        + repr(expected[1])
        + ")}"
    )
    prefix = compose_prefix(state, directory)
    for name in ("api", "worker"):
        command(
            [*prefix, "exec", "-T", name, "python", "-c", probe], environment=clean_environment()
        )
    command(
        [
            *prefix,
            "run",
            "--rm",
            "--no-deps",
            "--pull",
            "never",
            "-T",
            "--entrypoint",
            "python",
            "telegram-operator",
            "-c",
            probe,
        ],
        environment=clean_environment(),
    )
    command(
        [
            *prefix,
            "exec",
            "-T",
            "api",
            "python",
            "-c",
            "import json,urllib.request; assert json.load(urllib.request.urlopen('http://localhost:8000/health/ready',timeout=4))=={'status':'ok','component':'database'}",
        ],
        environment=clean_environment(),
    )


def compare_callers(before, after, state):
    """Preservation is mandatory even while our relay is between stop and create."""
    for name, previous in before.items():
        if name in {"api", "worker", "telegram-egress"}:
            continue
        require(after.get(name) == previous, "EGRESS_UNRELATED_CONTAINER_CHANGED")
    default = state["project"] + "_default"
    for name in ("api", "worker"):
        require(
            before[name]["image"] == after[name]["image"]
            and before[name]["mounts"] == after[name]["mounts"]
            and before[name]["environment_sha256"] == after[name]["environment_sha256"]
            and before[name]["process_sha256"] == after[name]["process_sha256"],
            "EGRESS_CALLER_IMAGE_OR_VOLUME_CHANGED",
        )
        require(
            before[name]["database_identity"] == after[name]["database_identity"],
            "EGRESS_CALLER_DATABASE_CHANGED",
        )
        require(
            after[name]["networks"][default]["Gateway"]
            == before[name]["networks"][default]["Gateway"],
            "EGRESS_DEFAULT_GATEWAY_CHANGED",
        )


def compare_deployment(before, after, state):
    compare_callers(before, after, state)
    require("telegram-egress" in after, "EGRESS_RUNNING_RELAY_REQUIRED")
    relay = after["telegram-egress"]
    require(
        relay["image"] == state["image_id"]
        and relay["networks"][state["project"] + "_telegram-egress"]["IPAddress"]
        == str(ipaddress.ip_network(state["subnet"])[2]),
        "EGRESS_RUNNING_RELAY_IDENTITY",
    )

    if state.get("version") in {2, 3}:
        require(
            relay["networks"][state["project"] + "_telegram-egress-v6"]["GlobalIPv6Address"]
            == str(ipaddress.ip_network(state["subnet6"])[2]),
            "EGRESS_RUNNING_RELAY_IPV6",
        )


def transition_relay(states, directory, *, missing=False):
    """Inspect our relay including stopped containers, never infer identity from absence."""
    state = states[-1]
    ids = (
        command(
            [
                "docker",
                "ps",
                "-aq",
                "--filter",
                "label=com.docker.compose.project=" + state["project"],
                "--filter",
                "label=com.docker.compose.service=telegram-egress",
            ]
        )
        .decode()
        .split()
    )
    require(len(ids) <= 1, "EGRESS_RELAY_MULTIPLE")
    if not ids:
        require(missing, "EGRESS_RELAY_MISSING_WITHOUT_INTENT")
        return {"status": "missing"}
    info = json.loads(command(["docker", "inspect", ids[0]]))[0]
    labels = info["Config"]["Labels"]
    require(
        labels["com.docker.compose.project"] == state["project"]
        and labels["com.docker.compose.service"] == "telegram-egress"
        and labels.get("com.docker.compose.oneoff") == "False"
        and info["Image"] == state["image_id"]
        and info["Config"]["Image"] == IMAGE
        and info["Config"]["User"] == f"{state['uid']}:{state['gid']}"
        and info["Config"]["Cmd"] == ["run", "-config", "/run/telegram-egress/config.json"],
        "EGRESS_RELAY_TRANSITION_IDENTITY",
    )
    image = json.loads(command(["docker", "image", "inspect", state["image_id"]]))[0]
    require(
        info["Config"]["Entrypoint"] == image["Config"]["Entrypoint"]
        and info["Config"].get("Env") == image["Config"].get("Env")
        and info["Config"].get("WorkingDir") == image["Config"].get("WorkingDir"),
        "EGRESS_RELAY_ENTRYPOINT",
    )
    host = info["HostConfig"]
    require(
        host["ReadonlyRootfs"]
        and not host["Privileged"]
        and not host["PortBindings"]
        and host["CapDrop"] == ["ALL"]
        and host["SecurityOpt"] == ["no-new-privileges:true"]
        and host["NetworkMode"] not in {"host", "none"}
        and host["LogConfig"]["Type"] == "none",
        "EGRESS_RELAY_TRANSITION_PRIVILEGE",
    )
    binds = [m for m in info["Mounts"] if m["Type"] != "tmpfs"]
    require(
        len(binds) == 1
        and binds[0]["Type"] == "bind"
        and not binds[0]["RW"]
        and binds[0]["Destination"] == "/run/telegram-egress/config.json",
        "EGRESS_RELAY_TRANSITION_MOUNT",
    )
    matches = [
        s
        for s in states
        if str(generated_directory(s, directory) / "config.json") == binds[0]["Source"]
    ]
    require(len(matches) == 1, "EGRESS_RELAY_TRANSITION_CONFIG")
    actual_state = matches[0]
    require(
        sha(private_bytes(binds[0]["Source"])) == actual_state["config_sha256"],
        "EGRESS_RELAY_TRANSITION_CONFIG",
    )
    values = route_values(actual_state, directory)
    expected = {
        values["ASM_TELEGRAM_EGRESS_NETWORK"]: {"IPv4Address": values["ASM_TELEGRAM_EGRESS_IP"]}
    }
    if actual_state.get("version") in {2, 3}:
        expected[values["ASM_TELEGRAM_EGRESS_NETWORK6"]] = {
            "IPv6Address": values["ASM_TELEGRAM_EGRESS_IPV6"]
        }
    networks = info["NetworkSettings"]["Networks"]
    require(set(networks) == set(expected), "EGRESS_RELAY_TRANSITION_NETWORKS")
    for name, addresses in expected.items():
        require(networks[name]["IPAMConfig"] == addresses, "EGRESS_RELAY_TRANSITION_ADDRESS")
    status = info["State"]["Status"]
    require(
        status in {"running", "exited", "created"} and not info["State"].get("Dead"),
        "EGRESS_RELAY_TRANSITION_STATUS",
    )
    return {
        "status": "running" if status == "running" else "stopped",
        "id": info["Id"],
        "image": info["Image"],
        "config_sha256": actual_state["config_sha256"],
    }


def recovery_recreate_pending(state, directory):
    path = directory / "recovery-recreate.json"
    if not path.exists():
        return False
    require(state.get("generation") == "recovery-v2", "EGRESS_RECOVERY_RECREATE_STATE")
    require(
        private_bytes(path)
        == encoded(
            {
                "state_sha256": sha(encoded(state)),
                "before_sha256": state["recovery_before_sha256"],
                "legacy_state_sha256": state["legacy_state_sha256"],
            }
        ),
        "EGRESS_RECOVERY_RECREATE_CHANGED",
    )
    return not (directory / "deployment-after.json").exists()


def deploy(state, directory):
    require(
        not (directory / "deployment-before.json").exists()
        and not (directory / "deployment-after.json").exists()
        and not (directory / "recovery-v1").exists(),
        "EGRESS_BASELINE_EXISTS_USE_RECOVERY",
    )
    model = checked_model(state, directory)
    require(
        all(
            model["services"][n]["environment"]["ASM_TELEGRAM_ENABLED"] == "false" for n in CALLERS
        ),
        "EGRESS_DEPLOY_REQUIRES_DISABLED_TELEGRAM",
    )
    before = snapshot(state, directory)
    for name in ("api", "worker"):
        current = json.loads(
            command(["docker", "image", "inspect", model["services"][name]["image"]])
        )[0]
        require(current["Id"] == before[name]["image"], "EGRESS_APP_TAG_DRIFT")
    operator_image = model["services"]["telegram-operator"].get(
        "image", state["project"] + "-telegram-operator"
    )
    source_image_check(operator_image)
    write_private(directory / "deployment-before.json", encoded(before))
    prefix, env = compose_prefix(state, directory), clean_environment()
    command(
        [*prefix, "up", "-d", "--no-deps", "--pull", "never", "telegram-egress"],
        timeout=90,
        environment=env,
    )
    command(
        [
            *prefix,
            "up",
            "-d",
            "--no-deps",
            "--pull",
            "never",
            "--force-recreate",
            "--wait",
            "api",
            "worker",
        ],
        timeout=120,
        environment=env,
    )
    after = snapshot(state, directory)
    compare_deployment(before, after, state)
    caller_probe(state, directory)
    write_private(directory / "deployment-after.json", encoded(after))


def disabled_runtime(raw):
    """The sole permitted runtime-input delta; preserve every other byte."""
    require(len(raw) <= 65536, "EGRESS_ENV_LIMIT")
    lines = raw.splitlines(keepends=True)
    matches = [i for i, line in enumerate(lines) if line.startswith(b"ASM_TELEGRAM_ENABLED=")]
    require(len(matches) <= 1, "EGRESS_ENV_ENABLED_FIELD")
    if matches:
        lines[matches[0]] = b"ASM_TELEGRAM_ENABLED=false\n"
    else:
        if lines and not lines[-1].endswith(b"\n"):
            lines[-1] += b"\n"
        lines.append(b"ASM_TELEGRAM_ENABLED=false\n")
    return b"".join(lines)


def rollback_inputs(state, directory):
    """Validate the immutable intent, including both exact dotenv byte strings."""
    bundle = directory / "rollback-intent"
    checked_path(bundle, directory=True)
    require(
        {p.name for p in bundle.iterdir()}
        == {"intent.json", "runtime-before.env", "runtime-disabled.env", "before.json"},
        "EGRESS_ROLLBACK_INTENT_INVENTORY",
    )
    plan = strict_json(private_bytes(bundle / "intent.json"))
    original = private_bytes(bundle / "runtime-before.env")
    disabled = private_bytes(bundle / "runtime-disabled.env")
    require(
        set(plan) == {"state_sha256", "baseline_sha256", "inputs", "before_sha256", "relay"}
        and plan["state_sha256"] == sha(encoded(state))
        and plan["baseline_sha256"] == sha(private_bytes(directory / "deployment-before.json"))
        and plan["before_sha256"] == sha(private_bytes(bundle / "before.json"))
        and plan["inputs"]["runtime_env"] == sha(original)
        and disabled == disabled_runtime(original),
        "EGRESS_ROLLBACK_INTENT_CHANGED",
    )
    current = input_hashes(state)
    expected = dict(plan["inputs"])
    require(set(current) == set(expected), "EGRESS_ROLLBACK_INPUT_FIELDS")
    require(
        current["runtime_env"] in {sha(original), sha(disabled)}
        and all(current[k] == expected[k] for k in ("profile", "staged_env")),
        "EGRESS_ROLLBACK_INPUT_DRIFT",
    )
    return plan


def rollback_stage(directory, name, intent_hash, *, publish=False):
    path = directory / ("rollback-" + name + ".json")
    raw = encoded({"intent_sha256": intent_hash, "stage": name})
    if path.exists() or path.is_symlink():
        require(private_bytes(path) == raw, "EGRESS_ROLLBACK_STAGE_CHANGED")
        return True
    if publish:
        write_private(path, raw)
    return False


def rollback(state, directory):
    # Explicit action, with an immutable byte-exact disable-first intent before I/O.
    # No retry re-baselines either the original deployment or this operation.
    baseline = strict_json(private_bytes(directory / "deployment-before.json"))
    before = snapshot(state, directory, disabled=(directory / "rollback-disabled.json").exists())
    compare_callers(baseline, before, state)
    states = [state]
    if state.get("generation") == "recovery-v2":
        old, _, before_hash = recovery_archive(directory, state["source_sha"], rolling_back=True)
        candidate = recovery_candidate(old, directory, state["source_sha"], before_hash)
        require(state == candidate, "EGRESS_RECOVERY_MANIFEST_CHANGED")
        states.insert(0, old)
    bundle = directory / "rollback-intent"
    existed = bundle.exists()
    if existed:
        plan = rollback_inputs(state, directory)
        intent_hash = sha(private_bytes(bundle / "intent.json"))
    else:
        require(not (directory / "rollback.json").exists(), "EGRESS_ROLLBACK_INTENT_REQUIRED")
        intent_hash = None
    stopping = existed and rollback_stage(directory, "stop-intent", intent_hash)
    relay = transition_relay(
        states, directory, missing=stopping or recovery_recreate_pending(state, directory)
    )
    if not existed:
        original = checked_path(ROOT / ".env").read_bytes()
        plan = {
            "state_sha256": sha(encoded(state)),
            "baseline_sha256": sha(private_bytes(directory / "deployment-before.json")),
            "inputs": input_hashes(state),
            "before_sha256": sha(encoded(before)),
            "relay": relay,
        }
        atomic_bundle(
            bundle,
            {
                "intent.json": encoded(plan),
                "before.json": encoded(before),
                "runtime-before.env": original,
                "runtime-disabled.env": disabled_runtime(original),
            },
        )
        intent_hash = sha(private_bytes(bundle / "intent.json"))
    plan = rollback_inputs(state, directory)
    actual = before
    before = strict_json(private_bytes(bundle / "before.json"))
    compare_callers(before, actual, state)
    disabled_done = rollback_stage(directory, "disabled", intent_hash)
    remove_intent = rollback_stage(directory, "remove-intent", intent_hash)
    removed = rollback_stage(directory, "removed", intent_hash)
    require(not remove_intent or disabled_done, "EGRESS_ROLLBACK_STAGE_ORDER")
    require(not removed or remove_intent, "EGRESS_ROLLBACK_STAGE_ORDER")
    require(not stopping or removed, "EGRESS_ROLLBACK_STAGE_ORDER")
    if removed:
        require_unrouted(state, actual)
    receipt_path = directory / "rollback.json"
    if receipt_path.exists():
        require(stopping and relay["status"] != "running", "EGRESS_ROLLBACK_INCOMPLETE")
        require(
            checked_path(ROOT / ".env").read_bytes()
            == private_bytes(bundle / "runtime-disabled.env"),
            "EGRESS_ROLLBACK_NOT_DISABLED",
        )
        receipt = strict_json(private_bytes(receipt_path))
        require(
            receipt["before"] == before and receipt["after"] == snapshot(state, directory),
            "EGRESS_ROLLBACK_AFTER_DRIFT",
        )
        require(
            receipt == rollback_receipt(state, before, receipt["after"], intent_hash),
            "EGRESS_ROLLBACK_RECEIPT_CHANGED",
        )
        return
    path = checked_path(ROOT / ".env")
    disabled = private_bytes(bundle / "runtime-disabled.env")
    if path.read_bytes() != disabled:
        require(not disabled_done, "EGRESS_ROLLBACK_ENV_REVERTED")
        write_private(path, disabled, private_parent=False)
    env = clean_environment()
    if not disabled_done:
        command(
            [
                *compose_prefix(state, directory),
                "up",
                "-d",
                "--no-deps",
                "--pull",
                "never",
                "--force-recreate",
                "--wait",
                "api",
                "worker",
            ],
            timeout=120,
            environment=env,
        )
        compare_callers(before, snapshot(state, directory), state)
        rollback_stage(directory, "disabled", intent_hash, publish=True)
    rollback_stage(directory, "remove-intent", intent_hash, publish=True)
    if not removed:
        command(
            [
                *compose_prefix(state, directory, overlay=False),
                "up",
                "-d",
                "--no-deps",
                "--pull",
                "never",
                "--force-recreate",
                "--wait",
                "api",
                "worker",
            ],
            timeout=120,
            environment=env,
        )
        actual = snapshot(state, directory)
        compare_callers(before, actual, state)
        require_unrouted(state, actual)
        rollback_stage(directory, "removed", intent_hash, publish=True)
    rollback_stage(directory, "stop-intent", intent_hash, publish=True)
    relay = transition_relay(states, directory, missing=True)
    if relay["status"] != "missing":
        command([*compose_prefix(state, directory), "stop", "telegram-egress"], environment=env)
    relay = transition_relay(states, directory, missing=True)
    require(relay["status"] != "running", "EGRESS_ROLLBACK_RELAY_RUNNING")
    after = snapshot(state, directory)
    compare_callers(before, after, state)
    require_unrouted(state, after)
    rollback_inputs(state, directory)
    write_private(receipt_path, encoded(rollback_receipt(state, before, after, intent_hash)))


def require_unrouted(state, after):
    require(
        all(
            all(
                state["project"] + suffix not in after[n]["networks"]
                for suffix in ("_telegram-egress", "_telegram-egress-v6")
            )
            for n in ("api", "worker")
        ),
        "EGRESS_ROLLBACK_MAPPING_RETAINED",
    )


def rollback_receipt(state, before, after, intent_hash):
    return {
        "intent_sha256": intent_hash,
        "before": before,
        "after": after,
        "telegram_disabled": True,
        "route_networks_retained_inactive": [
            state["project"] + suffix
            for suffix in (
                ("_telegram-egress", "_telegram-egress-v6")
                if state.get("version") == 2
                else ("_telegram-egress",)
            )
        ],
    }


def permitted_compose(extra):
    return extra in [
        ["ps", "-q"],
        ["up", "-d", "--no-deps", "--pull", "never", "--force-recreate", "api", "worker"],
        [
            "run",
            "--rm",
            "--no-deps",
            "--pull",
            "never",
            "-T",
            "telegram-operator",
            "python",
            "scripts/provision_telegram_test.py",
            "--live",
            "--discover",
        ],
        [
            "run",
            "--rm",
            "--no-deps",
            "--pull",
            "never",
            "-T",
            "telegram-operator",
            "python",
            "scripts/provision_telegram_test.py",
            "--live",
        ],
    ]


def select_subnet6(networks, routes, previous=None, own_name=None):
    occupied, own = [], None
    for network in networks:
        blocks = network.get("IPAM", {}).get("Config") or []
        if network.get("Name") == own_name:
            require(
                network.get("Labels", {}).get("asm.scope") == "synthetic-telegram-test"
                and network.get("Internal") is True
                and network.get("EnableIPv6") is True
                and network.get("EnableIPv4") is False,
                "EGRESS_IPV6_NETWORK_COLLISION",
            )
            require(
                previous is not None and len(blocks) == 1 and blocks[0]["Subnet"] == previous,
                "EGRESS_IPV6_NETWORK_CHANGED",
            )
            own = ipaddress.ip_network(previous)
            require(
                blocks[0].get("Gateway") == str(own[1])
                and blocks[0].get("IPRange") == str(list(own.subnets(prefixlen_diff=1))[1]),
                "EGRESS_IPV6_DYNAMIC_RANGE_CHANGED",
            )
            continue
        occupied.extend(ipaddress.ip_network(v["Subnet"]) for v in blocks if v.get("Subnet"))
    for route in routes:
        if route.get("dst", "default") == "default":
            continue
        block = ipaddress.ip_network(route["dst"], strict=False)
        if own and (block == own or (block.prefixlen == 128 and block.subnet_of(own))):
            continue
        occupied.append(block)
    candidates = (
        [ipaddress.ip_network(previous)]
        if previous
        else ipaddress.ip_network("fd42:6173:6d00::/48").subnets(new_prefix=64)
    )
    for candidate in candidates:
        require(
            candidate.version == 6
            and candidate.prefixlen == 64
            and candidate.subnet_of(ipaddress.ip_network("fd00::/8")),
            "EGRESS_PRIVATE_IPV6_SUBNET",
        )
        if all(
            candidate.version != used.version or not candidate.overlaps(used) for used in occupied
        ):
            return str(candidate)
    raise EgressError("EGRESS_NO_NONOVERLAPPING_IPV6_SUBNET")


@contextmanager
def operation_lock(directory):
    checked_path(directory, directory=True)
    path = directory / "operation.lock"
    if path.exists() or path.is_symlink():
        checked_path(path)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        require(
            stat.S_ISREG(info.st_mode)
            and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == 0o600,
            "EGRESS_LOCK_IDENTITY",
        )
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise EgressError("EGRESS_OPERATION_BUSY") from None
        yield
    finally:
        os.close(fd)


def atomic_bundle(destination, files):
    """Publish an immutable generation at one rename; partial staging is never active."""
    checked_path(destination.parent, directory=True)
    require(all(re.fullmatch(r"[a-z0-9.-]+", name) for name in files), "EGRESS_BUNDLE_NAME")
    if destination.exists() or destination.is_symlink():
        checked_path(destination, directory=True)
        require({p.name for p in destination.iterdir()} == set(files), "EGRESS_BUNDLE_INVENTORY")
        require(
            all(private_bytes(destination / name) == raw for name, raw in files.items()),
            "EGRESS_BUNDLE_CHANGED",
        )
        return
    with tempfile.TemporaryDirectory(prefix=".generation-", dir=destination.parent) as tmp:
        temporary = Path(tmp)
        for name, raw in files.items():
            write_private(temporary / name, raw)
        os.rename(temporary, destination)
        fd = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def input_hashes(state):
    result = {}
    for name, path in {
        "runtime_env": ROOT / ".env",
        "staged_env": state["telegram_env"],
        "profile": state["profile"],
    }.items():
        raw = checked_path(path).read_bytes()
        require(len(raw) <= 65536, "EGRESS_ENV_LIMIT")
        result[name] = sha(raw)
    return result


def recovery_archive(directory, accepted_sha, *, rolling_back=False):
    """Attest only the known owner schema1; never substitute a new baseline."""
    source_check(accepted_sha)
    require(
        rolling_back
        or not ((directory / "rollback.json").exists() or (directory / "rollback-intent").exists()),
        "EGRESS_RECOVERY_ALREADY_ROLLED_BACK",
    )
    current_raw = private_bytes(directory / "state.json")
    current = strict_json(current_raw)
    audit = directory / "recovery-v1"
    if current.get("version") == 1:
        raw = current_raw
        require(not (directory / "deployment-after.json").exists(), "EGRESS_RECOVERY_NOT_PARTIAL")
    else:
        require(
            current.get("version") == 2
            and current.get("generation") == "recovery-v2"
            and current.get("source_sha") == accepted_sha,
            "EGRESS_RECOVERY_STATE",
        )
        raw = private_bytes(audit / "state.json")
        require(current.get("legacy_state_sha256") == sha(raw), "EGRESS_LEGACY_STATE_CHANGED")
    old = strict_json(raw)
    require(
        set(old)
        == {
            "version",
            "source_sha",
            "project",
            "subnet",
            "uid",
            "gid",
            "profile",
            "profile_sha256",
            "telegram_env",
            "config_sha256",
            "image",
            "runtime_sha256",
            "image_id",
        },
        "EGRESS_LEGACY_STATE_FIELDS",
    )
    require(old["version"] == 1 and old["source_sha"] == LEGACY_SHA, "EGRESS_LEGACY_SOURCE")
    verify(directory, legacy=True, accepted_sha=accepted_sha, saved_state=old)
    before_raw = private_bytes(directory / "deployment-before.json")
    before = strict_json(before_raw)
    require({"api", "worker", "postgres", "storage"} <= set(before), "EGRESS_LEGACY_BASELINE")
    require(
        hashlib.sha1(
            b"blob " + str(len(LEGACY_OVERLAY)).encode() + b"\0" + LEGACY_OVERLAY
        ).hexdigest()
        == LEGACY_OVERLAY_BLOB,
        "EGRESS_LEGACY_OVERLAY_CHANGED",
    )
    files = {
        name: private_bytes(directory / name)
        for name in ("config.json", "route.env", "runtime.json")
    }
    # The audit always keeps the pre-operation hashes. Only a byte-exact recorded
    # rollback delta can explain the different current runtime_env hash on retry.
    inputs = (
        rollback_inputs(current, directory)["inputs"]
        if rolling_back and (directory / "rollback-intent").exists()
        else input_hashes(old)
    )
    files.update(
        {
            "state.json": raw,
            "deployment-before.json": before_raw,
            "compose.yaml": LEGACY_OVERLAY,
            "inputs.json": encoded(inputs),
            "transition.json": encoded({"from_sha": LEGACY_SHA, "accepted_sha": accepted_sha}),
        }
    )
    atomic_bundle(audit, files)
    return old, before, sha(before_raw)


def recovery_candidate(old, directory, accepted_sha, before_hash):
    destination = directory / "recovery-v2"
    previous = (
        strict_json(private_bytes(destination / "state.json")) if destination.exists() else None
    )
    ids = command(["docker", "network", "ls", "-q"]).decode().split()
    networks = json.loads(command(["docker", "network", "inspect", *ids])) if ids else []
    routes = json.loads(command(["ip", "-j", "-6", "route", "show", "table", "all"]))
    subnet6 = select_subnet6(
        networks,
        routes,
        previous.get("subnet6") if previous else None,
        old["project"] + "_telegram-egress-v6",
    )
    state = dict(
        old,
        version=2,
        source_sha=accepted_sha,
        generation="recovery-v2",
        subnet6=subnet6,
        legacy_state_sha256=sha(private_bytes(directory / "recovery-v1/state.json")),
        recovery_before_sha256=before_hash,
    )
    values = route_values(state, directory)
    config = encoded(
        minimal_config(
            strict_json(private_bytes(old["profile"])),
            values["ASM_TELEGRAM_EGRESS_IP"],
            values["ASM_TELEGRAM_EGRESS_IPV6"],
        )
    )
    state["config_sha256"] = sha(config)
    require(
        image_check(directory / "recovery-v1/config.json", old["uid"], old["gid"])
        == old["image_id"],
        "EGRESS_IMAGE_CHANGED",
    )
    atomic_bundle(
        destination,
        {
            "state.json": encoded(state),
            "config.json": config,
            "runtime.json": private_bytes(directory / "runtime.json"),
            "route.env": route_env(values),
        },
    )
    require(
        image_check(destination / "config.json", state["uid"], state["gid"]) == state["image_id"],
        "EGRESS_IMAGE_CHANGED",
    )
    return state


def attest_partial_recovery(args, *, rolling_back=False, for_recover=False):
    directory = checked_path(state_directory(args.state_dir), directory=True)
    require(args.from_sha == LEGACY_SHA and args.accepted_sha, "EGRESS_RECOVERY_INPUTS")
    old, before, before_hash = recovery_archive(
        directory, args.accepted_sha, rolling_back=rolling_back
    )
    # The current model has the same frozen application environment. Its old
    # topology is used only to attest the already-recreated partial deployment.
    actual = snapshot(old, directory)
    compare_callers(before, actual, old)
    require(
        all(actual[n]["id"] != before[n]["id"] for n in ("api", "worker")),
        "EGRESS_RECOVERY_CALLERS_NOT_RECREATED",
    )
    model = checked_model(old, directory)
    require(
        all(
            model["services"][n]["environment"]["ASM_TELEGRAM_ENABLED"] == "false" for n in CALLERS
        ),
        "EGRESS_RECOVERY_REQUIRES_DISABLED_TELEGRAM",
    )
    for name in ("api", "worker"):
        info = json.loads(
            command(["docker", "image", "inspect", model["services"][name]["image"]])
        )[0]
        require(info["Id"] == actual[name]["image"], "EGRESS_APP_TAG_DRIFT")
    source_image_check(
        model["services"]["telegram-operator"].get("image", old["project"] + "-telegram-operator")
    )
    current = strict_json(private_bytes(directory / "state.json"))
    states = [old]
    missing = False
    candidate = (
        recovery_candidate(old, directory, args.accepted_sha, before_hash)
        if current.get("version") == 2 or for_recover
        else None
    )
    if current.get("version") == 2:
        require(current == candidate, "EGRESS_RECOVERY_MANIFEST_CHANGED")
        states.append(candidate)
        missing = recovery_recreate_pending(candidate, directory)
    if rolling_back and (directory / "rollback-intent").exists():
        rollback_inputs(current, directory)
        intent_hash = sha(private_bytes(directory / "rollback-intent/intent.json"))
        missing = missing or rollback_stage(directory, "stop-intent", intent_hash)
    transition_relay(states, directory, missing=missing)
    return (old, before, before_hash, candidate) if for_recover else (old, before, before_hash)


def recover(args):
    directory = checked_path(state_directory(args.state_dir), directory=True)
    old, before, before_hash, candidate = attest_partial_recovery(args, for_recover=True)
    recreate = encoded(
        {
            "state_sha256": sha(encoded(candidate)),
            "before_sha256": before_hash,
            "legacy_state_sha256": candidate["legacy_state_sha256"],
        }
    )
    recreate_path = directory / "recovery-recreate.json"
    if recreate_path.exists():
        require(private_bytes(recreate_path) == recreate, "EGRESS_RECOVERY_RECREATE_CHANGED")
    else:
        write_private(recreate_path, recreate)
    # Files were fsynced as an immutable generation. Only this single manifest
    # publication makes it active. The original root generated files remain intact.
    if strict_json(private_bytes(directory / "state.json"))["version"] == 1:
        write_private(directory / "state.json", encoded(candidate))
    require(
        private_bytes(directory / "state.json") == encoded(candidate),
        "EGRESS_RECOVERY_MANIFEST_CHANGED",
    )
    state = verify(directory)
    prefix, env = compose_prefix(state, directory), clean_environment()
    if not (directory / "deployment-after.json").exists():
        command(
            [
                *prefix,
                "up",
                "-d",
                "--no-deps",
                "--pull",
                "never",
                "--force-recreate",
                "telegram-egress",
            ],
            timeout=90,
            environment=env,
        )
        command(
            [
                *prefix,
                "up",
                "-d",
                "--no-deps",
                "--pull",
                "never",
                "--force-recreate",
                "--wait",
                "api",
                "worker",
            ],
            timeout=120,
            environment=env,
        )
    after = snapshot(state, directory)
    compare_deployment(before, after, state)
    caller_probe(state, directory)
    recovery_archive(directory, args.accepted_sha)  # Recheck baseline and inputs before success.
    after_raw = encoded(after)
    if (directory / "deployment-after.json").exists():
        require(
            private_bytes(directory / "deployment-after.json") == after_raw,
            "EGRESS_RECOVERY_AFTER_DRIFT",
        )
    else:
        write_private(directory / "deployment-after.json", after_raw)
    receipt = encoded(
        {
            "from_sha": LEGACY_SHA,
            "source_sha": args.accepted_sha,
            "original_before_sha256": before_hash,
            "after_sha256": sha(after_raw),
            "legacy_state_sha256": state["legacy_state_sha256"],
            "mapping_readiness_preservation": "PASS",
        }
    )
    if (directory / "recovery.json").exists():
        require(
            private_bytes(directory / "recovery.json") == receipt, "EGRESS_RECOVERY_RECEIPT_CHANGED"
        )
    else:
        write_private(directory / "recovery.json", receipt)


@contextmanager
def migration_budget(seconds):
    global MIGRATION_DEADLINE
    require(MIGRATION_DEADLINE is None, "EGRESS_MIGRATION_NESTED_OPERATION")
    MIGRATION_DEADLINE = time.monotonic() + seconds
    try:
        yield
        require(time.monotonic() < MIGRATION_DEADLINE, "EGRESS_MIGRATION_DEADLINE")
    finally:
        MIGRATION_DEADLINE = None


def migration_source(target):
    source_check(target)
    command(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", MIGRATION_BASE, target])
    require(
        command(["git", "-C", str(ROOT), "rev-parse", MIGRATION_FROM + "^{tree}"]).decode().strip()
        == MIGRATION_FROM_TREE,
        "EGRESS_MIGRATION_PREDECESSOR_TREE",
    )
    for name in (
        "compose.yaml",
        "infra/Dockerfile.backend",
        "infra/images.lock.env",
        "infra/telegram-egress/compose.yaml",
        "pyproject.toml",
        "uv.lock",
    ):
        require(
            command(["git", "-C", str(ROOT), "show", MIGRATION_FROM + ":" + name])
            == (ROOT / name).read_bytes(),
            "EGRESS_MIGRATION_FROZEN_SOURCE",
        )
    require(
        not os.environ.get("DOCKER_HOST") and not os.environ.get("DOCKER_CONTEXT"),
        "EGRESS_MIGRATION_AMBIENT_DOCKER",
    )
    context = json.loads(command(["docker", "context", "inspect"]))
    require(
        len(context) == 1
        and context[0]["Endpoints"]["docker"]["Host"] == "unix:///var/run/docker.sock",
        "EGRESS_MIGRATION_NONLOCAL_DOCKER",
    )
    return command(["git", "-C", str(ROOT), "rev-parse", target + "^{tree}"]).decode().strip()


def migration_bytes(path):
    path = checked_path(path)
    parent = path.parent.stat()
    require(
        parent.st_uid == os.getuid() and not parent.st_mode & 0o022,
        "EGRESS_MIGRATION_PRIVATE_PARENT",
    )
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        require(
            stat.S_ISREG(info.st_mode)
            and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == 0o600
            and info.st_size <= 65536,
            "EGRESS_MIGRATION_PRIVATE_FILE_CHANGED",
        )
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(65537)
    finally:
        os.close(fd)
    require(len(raw) <= 65536, "EGRESS_MIGRATION_FILE_LIMIT")
    return raw


def migration_receipts(path, expected, state, directory):
    """An explicitly pinned last operator receipt seals its complete predecessor DAG."""
    require(re.fullmatch(r"[0-9a-f]{64}", expected or ""), "EGRESS_MIGRATION_RECEIPT_PIN")
    path = checked_path(path)
    pending, files = [(path, expected)], {}
    while pending:
        current, digest = pending.pop()
        require(
            current.parent == path.parent and re.fullmatch(r"[a-z0-9-]+\.json", current.name),
            "EGRESS_MIGRATION_RECEIPT_PATH",
        )
        raw = migration_bytes(current)
        require(sha(raw) == digest, "EGRESS_MIGRATION_RECEIPT_CHANGED")
        if str(current) in files:
            continue
        require(len(files) < 32, "EGRESS_MIGRATION_RECEIPT_LIMIT")
        files[str(current)] = raw
        receipt = strict_json(raw)
        require(
            receipt.get("source_sha") == MIGRATION_FROM
            and receipt.get("source_tree") == MIGRATION_FROM_TREE
            and receipt.get("original_before_sha256")
            == sha(private_bytes(directory / "deployment-before.json")),
            "EGRESS_MIGRATION_RECEIPT_SOURCE",
        )
        parents = receipt.get("prior_receipts_sha256", {})
        require(isinstance(parents, dict), "EGRESS_MIGRATION_RECEIPT_PARENTS")
        for name, value in parents.items():
            require(
                re.fullmatch(r"[a-z0-9-]+\.json", name) is not None, "EGRESS_MIGRATION_RECEIPT_PATH"
            )
            pending.append((path.parent / name, value))
        if "prior_attempt_sha256" in receipt:
            pending.append(
                (
                    path.parent / "asm-telegram-discovery-0b7e24ee.json",
                    receipt["prior_attempt_sha256"],
                )
            )
        if "owner_correction_sha256" in receipt:
            pending.append(
                (
                    path.parent / "asm-telegram-owner-id-correction-0b7e24ee.json",
                    receipt["owner_correction_sha256"],
                )
            )
    last = strict_json(files[str(path)])
    require(
        last.get("preservation_pass") is True
        and last.get("status") in {"DIAGNOSTIC_COMPLETE", "BINDING_COMMITTED"}
        and last.get("staged_sha256") == sha(migration_bytes(state["telegram_env"])),
        "EGRESS_MIGRATION_LAST_RECEIPT",
    )
    require(
        any(
            strict_json(raw).get("status") == "BINDING_COMMITTED"
            and strict_json(raw).get("preservation_pass") is True
            for raw in files.values()
        ),
        "EGRESS_MIGRATION_BINDING_RECEIPT_REQUIRED",
    )
    return files, last["operator_image_id"]


def migration_inputs(state, directory, receipts):
    expected = strict_json(private_bytes(directory / "recovery-v1/inputs.json"))
    current = input_hashes(state)
    require(
        all(current[k] == expected[k] for k in ("runtime_env", "profile")),
        "EGRESS_MIGRATION_ORIGINAL_INPUT_DRIFT",
    )
    if current["staged_env"] != expected["staged_env"]:
        journals = [
            strict_json(raw)
            for name, raw in receipts.items()
            if Path(name).name == "asm-telegram-owner-id-correction-0b7e24ee.json"
        ]
        require(len(journals) == 1, "EGRESS_MIGRATION_STAGED_CHANGE_UNEXPLAINED")
        journal = journals[0]
        raw = migration_bytes(state["telegram_env"])
        key = rb"(?m)^[ \t]*(?:export[ \t]+)?ASM_TELEGRAM_EXPECTED_OWNER_ID[ \t]*="
        require(len(re.findall(key, raw)) == 1, "EGRESS_MIGRATION_OWNER_KEY_COUNT")
        match = re.search(
            key + rb"[ \t]*(?P<q>['\"]?)(?P<v>[1-9][0-9]{0,18})(?P=q)[ \t]*(?:#[^\r\n]*)?\r?$", raw
        )
        require(match is not None, "EGRESS_MIGRATION_OWNER_VALUE")
        previous, approved = journal.get("previous_owner_id"), journal.get("approved_owner_id")
        require(
            isinstance(previous, str)
            and re.fullmatch(r"[1-9][0-9]{0,18}", previous)
            and match.group("v").decode() == approved
            and previous != approved,
            "EGRESS_MIGRATION_OWNER_JOURNAL",
        )
        original = raw[: match.start("v")] + previous.encode() + raw[match.end("v") :]
        require(
            sha(original) == expected["staged_env"] == journal.get("staged_before_sha256")
            and sha(raw) == journal.get("staged_after_sha256"),
            "EGRESS_MIGRATION_OWNER_DELTA",
        )
    return current


def migration_predecessor_checkout(path):
    require(path, "EGRESS_MIGRATION_PREDECESSOR_CHECKOUT_REQUIRED")
    root = Path(path).absolute()
    require(SAFE_PATH.fullmatch(str(root)), "EGRESS_UNSAFE_PATH")
    require(all(not p.is_symlink() for p in (root, *root.parents)), "EGRESS_SYMLINK")
    info = root.stat()
    require(
        root != ROOT
        and info.st_uid == os.getuid()
        and stat.S_ISDIR(info.st_mode)
        and not info.st_mode & 0o022,
        "EGRESS_MIGRATION_SEPARATE_SOURCE_REQUIRED",
    )
    require(
        command(["git", "-C", str(root), "rev-parse", "--show-toplevel"]).decode().strip()
        == str(root)
        and command(["git", "-C", str(root), "rev-parse", "HEAD"]).decode().strip()
        == MIGRATION_FROM
        and command(["git", "-C", str(root), "rev-parse", "HEAD^{tree}"]).decode().strip()
        == MIGRATION_FROM_TREE
        and not command(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"]
        ).strip(),
        "EGRESS_MIGRATION_PREDECESSOR_SOURCE_CHANGED",
    )
    require(
        migration_bytes(root / ".env") == migration_bytes(ROOT / ".env"),
        "EGRESS_MIGRATION_RUNTIME_INPUT_COPY_CHANGED",
    )
    return root


def migration_catalog(directory, state, receipts, predecessor):
    files = dict(receipts)
    for path in directory.rglob("*"):
        relative = path.relative_to(directory)
        if relative.parts[0] == "migration-v3" or relative == Path("operation.lock"):
            continue
        if path.is_dir():
            checked_path(path, directory=True)
        else:
            files[str(path)] = migration_bytes(path)
    for root in (ROOT, predecessor):
        tracked = set(command(["git", "-C", str(root), "ls-files", "-z"]).decode().split("\0"))
        for parent in root.glob(".env*"):
            if parent.name in tracked:
                continue
            for path in [parent] if not parent.is_dir() else [parent, *parent.rglob("*")]:
                if path.is_dir():
                    checked_path(path, directory=True)
                else:
                    files[str(path)] = migration_bytes(path)
    for path in (state["telegram_env"], state["profile"]):
        files[str(path)] = migration_bytes(path)
    require(len(files) <= 100, "EGRESS_MIGRATION_CATALOG_LIMIT")
    return files


def migration_database(state, directory):
    """Read-only canonical multiset; no business command or raw rows leave the container."""
    probe = r"""
import hashlib,json,os,re
from sqlalchemy import create_engine,text
engine=create_engine(os.environ['ASM_MIGRATION_DATABASE_URL'],hide_parameters=True,connect_args={'connect_timeout':4})
with engine.connect() as c:
    c.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
    c.execute(text('SET LOCAL statement_timeout=4000'))
    identity=dict(c.execute(text("SELECT current_database() AS database, (SELECT oid::bigint FROM pg_database WHERE datname=current_database()) AS database_oid, inet_server_addr()::text AS server_address, inet_server_port() AS server_port, pg_postmaster_start_time()::text AS postmaster_started")).mappings().one())
    tables=c.execute(text("SELECT n.nspname,c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('app','platform') AND c.relkind='r' ORDER BY n.nspname,c.relname")).all()
    assert len(tables)==31
    fingerprints={}
    for ns,name in tables:
        assert re.fullmatch('[a-z_][a-z_0-9]*',ns) and re.fullmatch('[a-z_][a-z_0-9]*',name)
        rows=c.execute(text(f'SELECT to_jsonb(t) FROM "{ns}"."{name}" AS t')).scalars().all()
        values=sorted(json.dumps(row,sort_keys=True,separators=(',',':')) for row in rows)
        fingerprints[ns+'.'+name]={'count':len(rows),'sha256':hashlib.sha256('\n'.join(values).encode()).hexdigest()}
    print(json.dumps({'identity':identity,'tables':fingerprints},sort_keys=True))
engine.dispose()
"""
    result = strict_json(
        command(
            [
                *compose_prefix(state, directory),
                "run",
                "--rm",
                "--no-deps",
                "--pull",
                "never",
                "-T",
                "--entrypoint",
                "python",
                "telegram-operator",
                "-B",
                "-c",
                probe,
            ],
            environment=clean_environment(),
        )
    )
    require(len(result["tables"]) == 31, "EGRESS_MIGRATION_DATABASE_TABLES")
    return result


def migration_image(image, source, kind):
    require(re.fullmatch(r"sha256:[0-9a-f]{64}", image), "EGRESS_MIGRATION_IMAGE_ID")
    paths = ["backend", "migrations", "pyproject.toml", "uv.lock", "alembic.ini"]
    if kind == "development":
        paths += ["tests", "scripts", "contracts", "infra/postgres/ensure_m1_3_prerequisites.sh"]
    raw = command(["git", "-C", str(ROOT), "ls-tree", "-rz", source, "--", *paths])
    blobs = {}
    for row in raw.split(b"\0"):
        if row:
            meta, path = row.split(b"\t", 1)
            mode, form, digest = meta.decode().split()
            require(form == "blob" and mode in {"100644", "100755"}, "EGRESS_MIGRATION_SOURCE_TYPE")
            blobs[path.decode()] = digest
    require(len(blobs) > 50, "EGRESS_MIGRATION_SOURCE_INVENTORY")
    probe = (
        "import hashlib,pathlib; expected=" + repr(blobs) + "; root=pathlib.Path('/app'); "
        "actual={str(p.relative_to(root)) for name in "
        + repr(paths)
        + " for p in ([root/name] if (root/name).is_file() else (root/name).rglob('*')) "
        "if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}; "
        "assert actual==set(expected); "
        "data={p:(root/p).read_bytes() for p in expected}; "
        "assert all(hashlib.sha1(b'blob '+str(len(v)).encode()+b'\\0'+v).hexdigest()==expected[p] for p,v in data.items())"
    )
    command(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--entrypoint=python",
            image,
            "-B",
            "-c",
            probe,
        ]
    )
    info = json.loads(command(["docker", "image", "inspect", image]))[0]
    require(
        info["Id"] == image and info["Os"] == "linux" and info["Architecture"] == "amd64",
        "EGRESS_MIGRATION_IMAGE_IDENTITY",
    )
    return {"id": image, "source_sha": source, "kind": kind, "blobs_sha256": sha(encoded(blobs))}


def migration_runtime(state, directory):
    model = checked_model(state, directory)
    ids = (
        command(
            [
                "docker",
                "ps",
                "-aq",
                "--filter",
                "label=com.docker.compose.project=" + state["project"],
            ]
        )
        .decode()
        .split()
    )
    records = {}
    for item in json.loads(command(["docker", "inspect", *ids])) if ids else []:
        config, host = item["Config"], item["HostConfig"]
        labels = config["Labels"]
        if labels.get("com.docker.compose.oneoff") == "True":
            continue
        name = labels["com.docker.compose.service"]
        require(name not in records, "EGRESS_MIGRATION_MULTIPLE_CONTAINERS")
        env = dict(row.split("=", 1) for row in config.get("Env", []) if "=" in row)
        running = item["State"]["Running"]
        if name in {*MIGRATION_SERVICES, "scheduler"}:
            require(
                env.get("ASM_TELEGRAM_ENABLED") == "false"
                and all(
                    env.get(k) == ""
                    for k in (
                        "TG_BOT_TOKEN",
                        "TG_WEBHOOK_SECRET",
                        "ASM_TELEGRAM_EXPECTED_BOT_ID",
                        "ASM_TELEGRAM_WEBHOOK_URL",
                    )
                ),
                "EGRESS_MIGRATION_TELEGRAM_NOT_EMPTY",
            )
        if name in MIGRATION_SERVICES:
            require(
                all(
                    env.get(k) == str(v) for k, v in model["services"][name]["environment"].items()
                ),
                "EGRESS_MIGRATION_ENVIRONMENT_DRIFT",
            )
        records[name] = {
            "id": item["Id"],
            "image": item["Image"],
            "running": running,
            "config_sha256": sha(
                encoded(
                    {
                        k: config.get(k)
                        for k in (
                            "Cmd",
                            "Entrypoint",
                            "User",
                            "WorkingDir",
                            "Env",
                            "Healthcheck",
                            "ExposedPorts",
                        )
                    }
                )
            ),
            "host_sha256": sha(encoded(host)),
            "mounts": sorted(item["Mounts"], key=encoded),
            "networks": {
                k: {
                    x: v.get(x)
                    for x in (
                        "IPAddress",
                        "Gateway",
                        "GlobalIPv6Address",
                        "IPv6Gateway",
                        "IPAMConfig",
                    )
                }
                for k, v in item["NetworkSettings"]["Networks"].items()
            },
        }
        if name in {"api", "worker"} and running:
            records[name]["database_identity"] = database_identity(item["Id"])
    require(
        {"postgres", "storage", "telegram-egress"} <= records.keys(),
        "EGRESS_MIGRATION_REQUIRED_RUNTIME",
    )
    return records


def migration_compare(before, actual, images, *, pending=(), completed=False):
    require(set(actual) <= set(before), "EGRESS_MIGRATION_FOREIGN_CONTAINER")
    for name, previous in before.items():
        if name not in MIGRATION_SERVICES:
            require(actual.get(name) == previous, "EGRESS_MIGRATION_UNRELATED_DRIFT")
            continue
        if name not in actual:
            require(name in pending and not completed, "EGRESS_MIGRATION_MISSING_WITHOUT_INTENT")
            continue
        current = actual[name]
        require(current["image"] in images[name], "EGRESS_MIGRATION_APP_IMAGE_DRIFT")
        for key in ("config_sha256", "host_sha256", "mounts"):
            require(current[key] == previous[key], "EGRESS_MIGRATION_APP_CONFIG_DRIFT")
        require(
            current["running"] or name in pending and not completed,
            "EGRESS_MIGRATION_STOPPED_WITHOUT_INTENT",
        )
        if current["running"]:
            require(
                set(current["networks"]) == set(previous["networks"]),
                "EGRESS_MIGRATION_NETWORK_DRIFT",
            )
            for network, value in current["networks"].items():
                for field in ("Gateway", "IPv6Gateway", "IPAMConfig"):
                    require(
                        value[field] == previous["networks"][network][field],
                        "EGRESS_MIGRATION_NETWORK_DRIFT",
                    )
            if name in {"api", "worker"}:
                require(
                    current["database_identity"] == previous["database_identity"],
                    "EGRESS_MIGRATION_DATABASE_DRIFT",
                )


def migration_attest(args, directory):
    tree = migration_source(args.accepted_sha)
    require(args.from_sha == MIGRATION_FROM, "EGRESS_MIGRATION_FROM")
    state_raw = private_bytes(directory / "state.json")
    state = strict_json(state_raw)
    require(
        state.get("version") == 2
        and state.get("generation") == "recovery-v2"
        and state.get("source_sha") == MIGRATION_FROM
        and state.get("uid") == os.getuid()
        and state.get("gid") == os.getgid(),
        "EGRESS_MIGRATION_PREDECESSOR",
    )
    predecessor = migration_predecessor_checkout(args.predecessor_checkout)
    require(not directory.is_relative_to(predecessor), "EGRESS_PRIVATE_STATE_OUTSIDE_CHECKOUT")
    require(
        not (directory / "rollback-intent").exists() and not (directory / "rollback.json").exists(),
        "EGRESS_MIGRATION_ROLLED_BACK_PREDECESSOR",
    )
    require(
        private_bytes(directory / "recovery-v2/state.json") == state_raw,
        "EGRESS_MIGRATION_RECOVERY_STATE",
    )
    before = private_bytes(directory / "deployment-before.json")
    after = private_bytes(directory / "deployment-after.json")
    legacy_raw = private_bytes(directory / "recovery-v1/state.json")
    legacy = strict_json(legacy_raw)
    require(
        legacy.get("version") == 1
        and legacy.get("source_sha") == LEGACY_SHA
        and sha(legacy_raw) == state["legacy_state_sha256"]
        and sha(before) == state["recovery_before_sha256"]
        and private_bytes(directory / "recovery-v1/deployment-before.json") == before,
        "EGRESS_MIGRATION_ORIGINAL_BASELINE",
    )
    for name in ("config.json", "runtime.json", "route.env"):
        require(
            private_bytes(directory / name) == private_bytes(directory / "recovery-v1" / name),
            "EGRESS_MIGRATION_ORIGINAL_GENERATION",
        )
    require(
        strict_json(private_bytes(directory / "recovery-v1/transition.json"))
        == {"from_sha": LEGACY_SHA, "accepted_sha": MIGRATION_FROM},
        "EGRESS_MIGRATION_RECOVERY_TRANSITION",
    )
    receipt = strict_json(private_bytes(directory / "recovery.json"))
    require(
        receipt
        == {
            "from_sha": LEGACY_SHA,
            "source_sha": MIGRATION_FROM,
            "original_before_sha256": sha(before),
            "after_sha256": sha(after),
            "legacy_state_sha256": sha(legacy_raw),
            "mapping_readiness_preservation": "PASS",
        },
        "EGRESS_MIGRATION_RECOVERY_RECEIPT",
    )
    verify_state_contents(state, directory)
    require(
        transition_relay([state], directory)["status"] == "running",
        "EGRESS_MIGRATION_RELAY_NOT_RUNNING",
    )
    receipts, operator_image = migration_receipts(
        args.operator_receipt, args.operator_receipt_sha256, state, directory
    )
    migration_inputs(state, directory, receipts)
    runtime = migration_runtime(state, directory)
    require(set(MIGRATION_SERVICES) <= runtime.keys(), "EGRESS_MIGRATION_CALLERS_REQUIRED")
    old_after = strict_json(after)
    for name in MIGRATION_SERVICES:
        require(
            runtime[name]["running"]
            and runtime[name]["id"] == old_after[name]["id"]
            and runtime[name]["image"] == old_after[name]["image"],
            "EGRESS_MIGRATION_RECOVERED_RUNTIME_CHANGED",
        )
    old_images = {name: runtime[name]["image"] for name in MIGRATION_SERVICES}
    old_images["telegram-operator"] = operator_image
    model = checked_model(state, directory)
    observed = runtime_snapshot(
        state,
        directory,
        model,
        lambda image: require(image in old_images.values(), "EGRESS_MIGRATION_OLD_IMAGE_CHANGED"),
    )
    # Use the predecessor's original unrelated-service settings (including HTTPS),
    # not fresh .env defaults. Exclude only actually labeled disposable one-offs.
    observed = {n: v for n, v in observed.items() if n in runtime}
    require(set(observed) == set(old_after), "EGRESS_MIGRATION_PREDECESSOR_CONTAINERS_CHANGED")
    compare_deployment(old_after, observed, state)
    for name, expected in old_images.items():
        tag = model["services"][name].get("image", state["project"] + "-" + name)
        require(
            json.loads(command(["docker", "image", "inspect", tag]))[0]["Id"] == expected,
            "EGRESS_MIGRATION_OLD_TAG_DRIFT",
        )
    proofs = {}
    for name, image in old_images.items():
        kind = "development" if name == "telegram-operator" else "runtime"
        if image not in proofs:
            proofs[image] = migration_image(image, MIGRATION_FROM, kind)
    caller_probe(state, directory)
    database = migration_database(state, directory)
    require(
        all(database["identity"] == runtime[n]["database_identity"] for n in ("api", "worker")),
        "EGRESS_MIGRATION_ACTUAL_DATABASE_REQUIRED",
    )
    return (
        state,
        runtime,
        old_images,
        migration_catalog(directory, state, receipts, predecessor),
        tree,
        proofs,
        database,
    )


def migration_saved(directory):
    bundle = checked_path(directory / "migration-v3", directory=True)
    plan = strict_json(private_bytes(bundle / "preparation.json"))
    require(
        plan.get("version") == 1
        and plan.get("from_sha") == MIGRATION_FROM
        and plan.get("from_tree") == MIGRATION_FROM_TREE
        and plan.get("to_tree") == migration_source(plan["to_sha"]),
        "EGRESS_MIGRATION_PREPARATION_SOURCE",
    )
    original = strict_json(private_bytes(bundle / "state-before.json"))
    predecessor = migration_predecessor_checkout(plan["predecessor_checkout"])
    names = {
        "preparation.json",
        "prepared.json",
        "state-before.json",
        "intent.json",
        "images-before.json",
        "images-after.json",
        "forward-complete.json",
        "rollback-intent.json",
        "rollback-complete.json",
    }
    names.update(entry["archive"] for entry in plan["files"].values())
    names.update(
        f"{direction}-{name}-{stage}.json"
        for direction in ("forward", "rollback")
        for name in MIGRATION_SERVICES
        for stage in ("intent", "result", "done")
    )
    require(
        all(p.name in names and p.is_file() and not p.is_symlink() for p in bundle.iterdir()),
        "EGRESS_MIGRATION_FOREIGN_EVIDENCE",
    )
    for path, entry in plan["files"].items():
        raw = private_bytes(bundle / entry["archive"])
        require(sha(raw) == entry["sha256"], "EGRESS_MIGRATION_ARCHIVE_CHANGED")
        if path != str(directory / "state.json"):
            require(migration_bytes(path) == raw, "EGRESS_MIGRATION_PRESERVED_FILE_CHANGED")
    require(
        sha(private_bytes(bundle / "state-before.json"))
        == plan["files"][str(directory / "state.json")]["sha256"],
        "EGRESS_MIGRATION_ARCHIVED_STATE_CHANGED",
    )
    receipts, _ = migration_receipts(
        plan["operator_receipt"], plan["operator_receipt_sha256"], original, directory
    )
    require(
        set(migration_catalog(directory, original, receipts, predecessor)) == set(plan["files"]),
        "EGRESS_MIGRATION_FILE_INVENTORY_CHANGED",
    )
    migration_inputs(original, directory, receipts)
    verify_state_contents(original, directory)
    require(
        transition_relay([original], directory)["status"] == "running",
        "EGRESS_MIGRATION_RELAY_NOT_RUNNING",
    )
    return bundle, plan, original


def migration_prepare(args, directory):
    bundle = directory / "migration-v3"
    if not bundle.exists():
        state, runtime, old_images, files, tree, proofs, database = migration_attest(
            args, directory
        )
        inventory, archive = {}, {}
        for index, (path, raw) in enumerate(sorted(files.items())):
            name = f"original-{index:03d}.bin"
            inventory[path] = {"archive": name, "sha256": sha(raw)}
            archive[name] = raw
        plan = {
            "version": 1,
            "from_sha": MIGRATION_FROM,
            "from_tree": MIGRATION_FROM_TREE,
            "to_sha": args.accepted_sha,
            "to_tree": tree,
            "files": inventory,
            "before": runtime,
            "before_images": old_images,
            "image_proofs": proofs,
            "database": database,
            "predecessor_checkout": str(Path(args.predecessor_checkout).absolute()),
            "operator_receipt": str(checked_path(args.operator_receipt)),
            "operator_receipt_sha256": args.operator_receipt_sha256,
        }
        archive.update({"preparation.json": encoded(plan), "state-before.json": encoded(state)})
        atomic_bundle(bundle, archive)
    bundle, plan, state = migration_saved(directory)
    migration_arguments(args, plan)
    require(
        plan["to_sha"] == args.accepted_sha and args.from_sha == MIGRATION_FROM,
        "EGRESS_MIGRATION_PREPARATION_TARGET",
    )
    require(
        private_bytes(directory / "state.json") == private_bytes(bundle / "state-before.json"),
        "EGRESS_MIGRATION_PREPARATION_ALREADY_ACTIVE",
    )
    migration_compare(
        plan["before"],
        migration_runtime(state, directory),
        {n: {v} for n, v in plan["before_images"].items()},
        completed=True,
    )
    require(
        migration_runtime(state, directory) == plan["before"],
        "EGRESS_MIGRATION_PREPARATION_RUNTIME_CHANGED",
    )
    prepared = bundle / "prepared.json"
    if prepared.exists():
        migration_prepared(directory)
        return
    tags, images = migration_build_images(args.accepted_sha, plan["to_tree"])
    mapping = {n: images["runtime"] for n in MIGRATION_SERVICES}
    mapping["telegram-operator"] = images["development"]
    require(
        all(mapping[n] != old for n, old in plan["before_images"].items()),
        "EGRESS_MIGRATION_IMAGE_NOT_DISTINCT",
    )
    keep = {}
    for name, image in plan["before_images"].items():
        tag = "asm-connect5-rollback:" + image.removeprefix("sha256:")
        found = command(["docker", "image", "ls", "-q", "--no-trunc", tag]).decode().strip()
        require(not found or found == image, "EGRESS_MIGRATION_ROLLBACK_TAG_DRIFT")
        if not found:
            command(["docker", "tag", image, tag])
        keep[name] = tag
    migration_saved(directory)
    write_private(
        prepared,
        encoded(
            {
                "before_images": plan["before_images"],
                "after_images": mapping,
                "tags": tags,
                "rollback_tags": keep,
                "preparation_sha256": sha(encoded(plan)),
            }
        ),
    )


def migration_build_context(source, directory):
    import io
    import tarfile

    with tarfile.open(
        fileobj=io.BytesIO(command(["git", "-C", str(ROOT), "archive", source]))
    ) as tar:
        require(
            all(member.isfile() or member.isdir() for member in tar.getmembers()),
            "EGRESS_MIGRATION_BUILD_FILE_TYPE",
        )
        tar.extractall(directory, filter="data")
    # data_filter drops directory modes; private umask otherwise yields root-owned
    # 0700 COPY trees, unreadable to UID10001. Only tracked source is present here.
    for path in Path(directory).rglob("*"):
        if path.is_dir():
            path.chmod(0o755)


def migration_build_images(source, tree):
    require(migration_source(source) == tree, "EGRESS_MIGRATION_BUILD_SOURCE")
    tags, images = {}, {}
    pins = dict(
        line.split("=", 1)
        for line in (ROOT / "infra/images.lock.env").read_text().splitlines()
        if line and not line.startswith("#")
    )
    for kind in ("runtime", "development"):
        tag = "asm-connect5-" + kind + ":" + source
        exists = command(["docker", "image", "ls", "-q", "--no-trunc", tag]).decode().strip()
        if not exists:
            # git archive contains only tracked exact source, never .env/TLS/operator files.
            with tempfile.TemporaryDirectory(prefix="asm-connect5-build-") as temporary:
                migration_build_context(source, temporary)
                command(
                    [
                        "docker",
                        "build",
                        "--pull",
                        "--network=default",
                        "--target",
                        kind,
                        "--build-arg",
                        "PYTHON_IMAGE=" + pins["PYTHON_IMAGE"],
                        "--build-arg",
                        "UV_IMAGE=" + pins["UV_IMAGE"],
                        "--label",
                        "asm.connect5.source=" + source,
                        "--label",
                        "asm.connect5.tree=" + tree,
                        "--label",
                        "asm.connect5.kind=" + kind,
                        "-f",
                        temporary + "/infra/Dockerfile.backend",
                        "-t",
                        tag,
                        temporary,
                    ],
                    timeout=480,
                )
        info = json.loads(command(["docker", "image", "inspect", tag]))[0]
        labels = info["Config"].get("Labels", {}) or {}
        require(
            all(
                labels.get("asm.connect5." + k) == v
                for k, v in {"source": source, "tree": tree, "kind": kind}.items()
            ),
            "EGRESS_MIGRATION_TARGET_TAG_DRIFT",
        )
        migration_image(info["Id"], source, kind)
        tags[kind], images[kind] = tag, info["Id"]
    return tags, images


def migration_prepared(directory):
    bundle, plan, original = migration_saved(directory)
    ready = strict_json(private_bytes(bundle / "prepared.json"))
    require(
        ready["preparation_sha256"] == sha(encoded(plan))
        and ready["before_images"] == plan["before_images"]
        and set(ready["after_images"]) == {*MIGRATION_SERVICES, "telegram-operator"},
        "EGRESS_MIGRATION_IMAGE_PLAN_CHANGED",
    )
    checked = set()
    for direction, source in (("before_images", MIGRATION_FROM), ("after_images", plan["to_sha"])):
        for name, image in ready[direction].items():
            kind = "development" if name == "telegram-operator" else "runtime"
            if (image, source, kind) not in checked:
                migration_image(image, source, kind)
                checked.add((image, source, kind))
            tag = (
                ready["rollback_tags"][name]
                if direction == "before_images"
                else ready["tags"][kind]
            )
            require(
                json.loads(command(["docker", "image", "inspect", tag]))[0]["Id"] == image,
                "EGRESS_MIGRATION_IMAGE_TAG_CHANGED",
            )
    return bundle, plan, original, ready


def migration_manifest(directory, state):
    bundle = directory / "migration-v3"
    intent_raw = private_bytes(bundle / "intent.json")
    intent = strict_json(intent_raw)
    old = strict_json(private_bytes(bundle / "state-before.json"))
    plan = strict_json(private_bytes(bundle / "preparation.json"))
    ready = strict_json(private_bytes(bundle / "prepared.json"))
    expected = dict(
        old, version=3, source_sha=intent["to_sha"], migration_intent_sha256=sha(intent_raw)
    )
    require(
        state == expected
        and intent["from_sha"] == MIGRATION_FROM
        and intent["from_tree"] == MIGRATION_FROM_TREE
        and intent["to_sha"] == plan["to_sha"]
        and intent["to_tree"] == plan["to_tree"]
        and intent["preparation_sha256"] == sha(encoded(plan))
        and intent["prepared_sha256"] == sha(encoded(ready))
        and intent["before_images"] == ready["before_images"] == plan["before_images"]
        and intent["after_images"] == ready["after_images"],
        "EGRESS_MIGRATION_STATE_BINDING",
    )
    for side in ("before", "after"):
        require(
            private_bytes(bundle / ("images-" + side + ".json"))
            == encoded(
                {"services": {n: {"image": v} for n, v in intent[side + "_images"].items()}}
            ),
            "EGRESS_MIGRATION_IMAGE_OVERLAY_CHANGED",
        )
    require(
        not (bundle / "rollback-complete.json").exists(), "EGRESS_MIGRATION_ALREADY_ROLLED_BACK"
    )
    return intent


def migration_stage(bundle, name, intent, *, publish=False):
    path = bundle / (name + ".json")
    expected = encoded({"intent_sha256": sha(encoded(intent)), "stage": name})
    if path.exists() or path.is_symlink():
        require(private_bytes(path) == expected, "EGRESS_MIGRATION_STAGE_CHANGED")
        return True
    if publish:
        write_private(path, expected)
    return False


def migration_observed(bundle, intent):
    allowed, pending = {}, []
    rolling_back = migration_stage(bundle, "rollback-intent", intent)
    for name in MIGRATION_SERVICES:
        forward = migration_stage(bundle, "forward-" + name + "-intent", intent)
        reverted = migration_stage(bundle, "rollback-" + name + "-intent", intent)
        forward_done = migration_stage(bundle, "forward-" + name + "-done", intent)
        reverted_done = migration_stage(bundle, "rollback-" + name + "-done", intent)
        require(
            (not forward_done or forward)
            and (not reverted or rolling_back)
            and (not reverted_done or reverted),
            "EGRESS_MIGRATION_STAGE_ORDER",
        )
        allowed[name] = {intent["before_images"][name]}
        if forward:
            allowed[name].add(intent["after_images"][name])
        if reverted_done:
            allowed[name] = {intent["before_images"][name]}
        elif forward_done and not reverted:
            allowed[name] = {intent["after_images"][name]}
        if forward and not forward_done or reverted and not reverted_done:
            pending.append(name)
    return allowed, pending


def migration_results(bundle, intent, actual):
    for name in MIGRATION_SERVICES:
        reverse = migration_stage(bundle, "rollback-" + name + "-intent", intent)
        forward = migration_stage(bundle, "forward-" + name + "-intent", intent)
        if not forward and not reverse:
            require(
                actual.get(name) == intent["before"][name],
                "EGRESS_MIGRATION_UNJOURNALED_CALLER_CHANGE",
            )
            continue
        stage = ("rollback-" if reverse else "forward-") + name
        path = bundle / (stage + "-result.json")
        if migration_stage(bundle, stage + "-done", intent):
            require(path.is_file(), "EGRESS_MIGRATION_SERVICE_RESULT_REQUIRED")
        if path.exists() or path.is_symlink():
            require(
                strict_json(private_bytes(path))
                == {"intent_sha256": sha(encoded(intent)), "runtime": actual.get(name)},
                "EGRESS_MIGRATION_SERVICE_RESULT_CHANGED",
            )


def migration_arguments(args, plan):
    for name in ("operator_receipt", "operator_receipt_sha256", "predecessor_checkout"):
        requested = getattr(args, name, None)
        if requested is not None:
            require(requested == plan[name], "EGRESS_MIGRATION_REQUEST_CHANGED")


def migration_switch(args, directory, *, reverse=False, readonly=False):
    bundle, plan, old, ready = migration_prepared(directory)
    migration_arguments(args, plan)
    require(
        args.accepted_sha == plan["to_sha"] and args.from_sha == MIGRATION_FROM,
        "EGRESS_MIGRATION_REQUEST_CHANGED",
    )
    database = migration_database(old, directory)
    require(database == plan["database"], "EGRESS_MIGRATION_CANONICAL_DATA_DRIFT")
    intent_path = bundle / "intent.json"
    if not intent_path.exists():
        require(not reverse and not readonly, "EGRESS_MIGRATION_INTENT_REQUIRED")
        actual = migration_runtime(old, directory)
        require(
            actual == plan["before"] and private_bytes(directory / "state.json") == encoded(old),
            "EGRESS_MIGRATION_PREPARATION_RUNTIME_CHANGED",
        )
        migration_compare(
            plan["before"],
            actual,
            {n: {v} for n, v in ready["before_images"].items()},
            completed=True,
        )
        intent = {
            "version": 1,
            "from_sha": MIGRATION_FROM,
            "from_tree": MIGRATION_FROM_TREE,
            "to_sha": plan["to_sha"],
            "to_tree": plan["to_tree"],
            "preparation_sha256": sha(encoded(plan)),
            "prepared_sha256": sha(encoded(ready)),
            "before": actual,
            "before_images": ready["before_images"],
            "after_images": ready["after_images"],
        }
        for side in ("before", "after"):
            write_private(
                bundle / ("images-" + side + ".json"),
                encoded(
                    {"services": {n: {"image": v} for n, v in intent[side + "_images"].items()}}
                ),
            )
        write_private(intent_path, encoded(intent))
    intent = strict_json(private_bytes(intent_path))
    require(
        intent["preparation_sha256"] == sha(encoded(plan))
        and intent["prepared_sha256"] == sha(encoded(ready))
        and intent["before_images"] == ready["before_images"]
        and intent["after_images"] == ready["after_images"]
        and intent["to_sha"] == plan["to_sha"]
        and intent["from_sha"] == MIGRATION_FROM,
        "EGRESS_MIGRATION_INTENT_CHANGED",
    )
    new = dict(
        old, version=3, source_sha=plan["to_sha"], migration_intent_sha256=sha(encoded(intent))
    )
    migration_manifest(directory, new) if not (bundle / "rollback-complete.json").exists() else None
    current = private_bytes(directory / "state.json")
    require(current in {encoded(old), encoded(new)}, "EGRESS_MIGRATION_MANIFEST_DRIFT")
    rollback_started = migration_stage(bundle, "rollback-intent", intent)
    require(reverse or not rollback_started, "EGRESS_MIGRATION_ROLLBACK_ALREADY_STARTED")
    direction, side = ("rollback", "before") if reverse else ("forward", "after")
    completion = bundle / (direction + "-complete.json")
    actual = migration_runtime(old, directory)
    allowed, pending = migration_observed(bundle, intent)
    migration_compare(intent["before"], actual, allowed, pending=pending)
    migration_results(bundle, intent, actual)
    if completion.exists():
        receipt = strict_json(private_bytes(completion))
        require(
            receipt
            == {
                "intent_sha256": sha(encoded(intent)),
                "source_sha": intent[side == "after" and "to_sha" or "from_sha"],
                "state_sha256": sha(encoded(old if reverse else new)),
                "after": actual,
                "database_sha256": sha(encoded(database)),
                "preservation": "PASS",
            }
            and current == encoded(old if reverse else new),
            "EGRESS_MIGRATION_COMPLETED_DRIFT",
        )
        caller_probe(old if reverse else new, directory)
        return
    require(not readonly, "EGRESS_MIGRATION_NOT_COMPLETE")
    if reverse and not rollback_started:
        migration_stage(bundle, "rollback-intent", intent, publish=True)
    prefix = [*compose_prefix(old, directory), "-f", str(bundle / ("images-" + side + ".json"))]
    for name in MIGRATION_SERVICES:
        expected = intent[side + "_images"][name]
        actual = migration_runtime(old, directory)
        allowed, pending = migration_observed(bundle, intent)
        migration_compare(intent["before"], actual, allowed, pending=pending)
        migration_results(bundle, intent, actual)
        if migration_stage(bundle, direction + "-" + name + "-done", intent):
            require(
                name in actual and actual[name]["image"] == expected and actual[name]["running"],
                "EGRESS_MIGRATION_FINISHED_SERVICE_DRIFT",
            )
            continue
        migration_stage(bundle, direction + "-" + name + "-intent", intent, publish=True)
        if name not in actual or actual[name]["image"] != expected or not actual[name]["running"]:
            command(
                [
                    *prefix,
                    "up",
                    "-d",
                    "--no-deps",
                    "--pull",
                    "never",
                    "--force-recreate",
                    "--wait",
                    "--wait-timeout",
                    "35",
                    name,
                ],
                timeout=50,
                environment=clean_environment(),
            )
        actual = migration_runtime(old, directory)
        require(
            actual[name]["image"] == expected and actual[name]["running"],
            "EGRESS_MIGRATION_SWITCH_FAILED",
        )
        result = bundle / (direction + "-" + name + "-result.json")
        raw = encoded({"intent_sha256": sha(encoded(intent)), "runtime": actual[name]})
        if result.exists():
            require(private_bytes(result) == raw, "EGRESS_MIGRATION_SERVICE_RESULT_CHANGED")
        else:
            write_private(result, raw)
        migration_stage(bundle, direction + "-" + name + "-done", intent, publish=True)
    actual = migration_runtime(old, directory)
    migration_compare(
        intent["before"],
        actual,
        {n: {intent[side + "_images"][n]} for n in MIGRATION_SERVICES},
        completed=True,
    )
    caller_probe(old if reverse else new, directory)
    migration_saved(directory)
    require(
        migration_database(old if reverse else new, directory) == database,
        "EGRESS_MIGRATION_CANONICAL_DATA_DRIFT",
    )
    desired = encoded(old if reverse else new)
    if current != desired:
        write_private(directory / "state.json", desired)
    write_private(
        completion,
        encoded(
            {
                "intent_sha256": sha(encoded(intent)),
                "source_sha": intent["from_sha" if reverse else "to_sha"],
                "state_sha256": sha(desired),
                "after": actual,
                "database_sha256": sha(encoded(database)),
                "preservation": "PASS",
            }
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=(
            "prepare",
            "verify",
            "snapshot",
            "deploy",
            "preflight",
            "compose",
            "rollback",
            "recover",
            "migration-attest",
            "migration-prepare",
            "migrate",
            "migration-resume",
            "migration-preflight",
            "migration-rollback",
        ),
    )
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--profile")
    parser.add_argument("--telegram-env")
    parser.add_argument("--project", default="asm-telegram-test")
    parser.add_argument("--accepted-sha")
    parser.add_argument("--from-sha")
    parser.add_argument("--operator-receipt")
    parser.add_argument("--operator-receipt-sha256")
    parser.add_argument("--predecessor-checkout")
    args, compose_args = parser.parse_known_args()
    os.umask(0o077)
    try:
        require(os.getuid() != 0, "EGRESS_NONROOT_OPERATOR_REQUIRED")
        require(not compose_args or args.action == "compose", "EGRESS_UNEXPECTED_ARGUMENTS")
        if args.action == "prepare":
            require(
                all((args.profile, args.telegram_env, args.accepted_sha)), "EGRESS_PREPARE_INPUTS"
            )
            prepare(args)
        else:
            directory = state_directory(args.state_dir)
            with operation_lock(directory):
                if args.action.startswith("migration-") or args.action == "migrate":
                    require(
                        args.accepted_sha and args.from_sha,
                        "EGRESS_MIGRATION_EXACT_SOURCES_REQUIRED",
                    )
                    with migration_budget(600 if args.action == "migration-prepare" else 180):
                        if args.action == "migration-attest":
                            migration_attest(args, directory)
                        elif args.action == "migration-prepare":
                            migration_prepare(args, directory)
                        else:
                            if args.action == "migration-resume":
                                require(
                                    (directory / "migration-v3/intent.json").is_file(),
                                    "EGRESS_MIGRATION_INTENT_REQUIRED",
                                )
                            migration_switch(
                                args,
                                directory,
                                reverse=args.action == "migration-rollback",
                                readonly=args.action == "migration-preflight",
                            )
                elif args.action == "recover":
                    recover(args)
                else:
                    if args.action == "rollback":
                        state = strict_json(private_bytes(directory / "state.json"))
                        if state.get("version") == 1:
                            state, _, _ = attest_partial_recovery(args, rolling_back=True)
                        else:
                            state = verify(directory)
                        require(
                            state["image"] == IMAGE and state["uid"] == os.getuid(),
                            "EGRESS_ROLLBACK_STATE",
                        )
                    else:
                        state = verify(directory)
                    model = checked_model(state, directory)
                    require(
                        state.get("version") != 3
                        or args.action in {"verify", "compose", "preflight"},
                        "EGRESS_MIGRATION_EXPLICIT_OPERATION_REQUIRED",
                    )
                    if args.action == "snapshot":
                        require(
                            all(
                                model["services"][n]["environment"]["ASM_TELEGRAM_ENABLED"]
                                == "false"
                                for n in ("api", "worker")
                            ),
                            "EGRESS_PERSISTED_TELEGRAM_MUST_BE_DISABLED",
                        )
                        require(
                            not (directory / "deployment-before.json").exists(),
                            "EGRESS_BASELINE_EXISTS_USE_RECOVERY",
                        )
                        write_private(
                            directory / "deployment-before.json",
                            encoded(snapshot(state, directory)),
                        )
                    elif args.action == "rollback":
                        rollback(state, directory)
                    elif args.action == "deploy":
                        deploy(state, directory)
                    elif args.action == "preflight":
                        if state.get("version") == 3:
                            args.accepted_sha, args.from_sha = state["source_sha"], MIGRATION_FROM
                            with migration_budget(180):
                                migration_switch(args, directory, readonly=True)
                        else:
                            before = strict_json(
                                private_bytes(directory / "deployment-before.json")
                            )
                            compare_deployment(before, snapshot(state, directory), state)
                            caller_probe(state, directory)
                    elif args.action == "compose":
                        extra = compose_args
                        if extra[:1] == ["--"]:
                            extra = extra[1:]
                        require(permitted_compose(extra), "EGRESS_COMPOSE_OPERATION")
                        require(
                            subprocess.run(
                                [
                                    *compose_prefix(
                                        state, directory, operator_inputs=extra[:1] == ["run"]
                                    ),
                                    *extra,
                                ],
                                stdin=subprocess.DEVNULL,
                                env=clean_environment(),
                            ).returncode
                            == 0,
                            "EGRESS_COMPOSE_FAILED",
                        )
        print("TELEGRAM_EGRESS_" + args.action.upper() + "_PASS")
    except (
        EgressError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        subprocess.SubprocessError,
    ) as error:
        print(str(error) if isinstance(error, EgressError) else "EGRESS_INVALID_INPUT_OR_COMMAND")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
