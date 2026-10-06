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

    if state.get("version") == 2:
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
        state.get("version") == (1 if legacy else 2) and state.get("image") == IMAGE,
        "EGRESS_STATE_VERSION",
    )
    if legacy:
        require(state["source_sha"] == LEGACY_SHA, "EGRESS_LEGACY_SOURCE")
    require(state["uid"] == os.getuid() and state["gid"] == os.getgid(), "EGRESS_STATE_OWNER")
    source_check(accepted_sha if legacy else state["source_sha"])
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
            source_image_check(container["Image"])
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

    if state.get("version") == 2:
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
    if actual_state.get("version") == 2:
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
        ),
    )
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--profile")
    parser.add_argument("--telegram-env")
    parser.add_argument("--project", default="asm-telegram-test")
    parser.add_argument("--accepted-sha")
    parser.add_argument("--from-sha")
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
                if args.action == "recover":
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
                        before = strict_json(private_bytes(directory / "deployment-before.json"))
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
