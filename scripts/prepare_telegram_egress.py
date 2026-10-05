"""Prepare and guard one private, opt-in synthetic TEST Telegram route.

No profile evaluation, app patch, automatic Telegram setup or external HTTP probe.
Errors are deliberately bounded codes: provider configuration is never printed.
"""

import argparse
import hashlib
import ipaddress
import json
import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path
from uuid import UUID

IMAGE = (
    "ghcr.io/xtls/xray-core@sha256:9a17fb7fcda36f80d041fc1f12f1d661d3f7c502572b2a6f2e4432534789a20b"
)
SOURCE = {
    "backend/src/asm/telegram/client.py": "53800d23c718910dd338cadee6ba595510c95ff9",
    "backend/src/asm/telegram/config.py": "31cba499681270d708cdb55e7c8e44202c07b4b7",
}
CALLERS = ("api", "worker", "telegram-operator")
ROOT = Path(__file__).resolve().parents[1]
SAFE_PATH = re.compile(r"/[A-Za-z0-9_./-]+")


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


def minimal_config(profile, relay_ip):
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
    return {
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
    result = subprocess.run(args, capture_output=True, timeout=timeout, env=environment)
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
    return {
        "ASM_TELEGRAM_EGRESS_SUBNET": str(subnet),
        "ASM_TELEGRAM_EGRESS_GATEWAY": str(subnet[1]),
        "ASM_TELEGRAM_EGRESS_IP": str(subnet[2]),
        "ASM_TELEGRAM_EGRESS_NETWORK": state["project"] + "_telegram-egress",
        "ASM_TELEGRAM_EGRESS_CONFIG": str(directory / "config.json"),
        "ASM_TELEGRAM_EGRESS_UID": str(state["uid"]),
        "ASM_TELEGRAM_EGRESS_GID": str(state["gid"]),
    }


def route_env(values):
    require(
        all(re.fullmatch(r"[A-Za-z0-9_./:-]+", v) for v in values.values()),
        "EGRESS_UNSAFE_ENV_VALUE",
    )
    return "".join(f"{k}={v}\n" for k, v in sorted(values.items())).encode()


def prepare(args):
    source_check(args.accepted_sha)
    profile = checked_path(args.profile)
    raw = private_bytes(profile)
    directory = Path(args.state_dir).absolute()
    require(not directory.is_relative_to(ROOT), "EGRESS_PRIVATE_STATE_OUTSIDE_CHECKOUT")
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
    config = encoded(minimal_config(strict_json(raw), str(ipaddress.ip_network(subnet)[2])))
    state = {
        "version": 1,
        "source_sha": args.accepted_sha,
        "project": args.project,
        "subnet": subnet,
        "uid": os.getuid(),
        "gid": os.getgid(),
        "profile": str(profile),
        "profile_sha256": sha(raw),
        "telegram_env": str(telegram_env),
        "config_sha256": sha(config),
        "image": IMAGE,
    }
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
    write_private(directory / "route.env", route_env(route_values(state, directory)))
    write_private(directory / "state.json", encoded(state))


def verify(directory):
    directory = checked_path(directory, directory=True)
    state = strict_json(private_bytes(directory / "state.json"))
    require(state.get("version") == 1 and state.get("image") == IMAGE, "EGRESS_STATE_VERSION")
    require(state["uid"] == os.getuid() and state["gid"] == os.getgid(), "EGRESS_STATE_OWNER")
    source_check(state["source_sha"])
    raw = private_bytes(state["profile"])
    require(sha(raw) == state["profile_sha256"], "EGRESS_PROFILE_CHANGED")
    values = route_values(state, directory)
    config = private_bytes(directory / "config.json")
    require(
        config == encoded(minimal_config(strict_json(raw), values["ASM_TELEGRAM_EGRESS_IP"]))
        and sha(config) == state["config_sha256"],
        "EGRESS_CONFIG_CHANGED",
    )
    require(private_bytes(directory / "route.env") == route_env(values), "EGRESS_MAPPING_CHANGED")
    checked_path(state["telegram_env"])
    require(
        image_check(directory / "config.json", state["uid"], state["gid"]) == state["image_id"],
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
    return state


def compose_prefix(state, directory, *, overlay=True):
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
        "--env-file",
        state["telegram_env"],
        "--env-file",
        str(ROOT / "infra/telegram-egress/image.lock.env"),
        "--env-file",
        str(directory / "route.env"),
        "-f",
        str(ROOT / "compose.yaml"),
    ]
    if overlay:
        args += [
            "-f",
            str(ROOT / "infra/telegram-egress/compose.yaml"),
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
                    "api.telegram.org=::ffff:" + values["ASM_TELEGRAM_EGRESS_IP"],
                ]
            )
            expected["networks"] = {"default": {"gw_priority": 1}, "telegram-egress": None}
            require(actual == expected, "EGRESS_CALLER_MODEL_DRIFT")
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
    require(
        relay["networks"]
        == {"telegram-egress": {"ipv4_address": values["ASM_TELEGRAM_EGRESS_IP"]}},
        "EGRESS_RELAY_NETWORK",
    )


def checked_model(state, directory):
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
    checked_model(state, directory)
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
        result[name] = {
            "id": container["Id"],
            "image": container["Image"],
            "mounts": [
                {k: m.get(k) for k in ("Type", "Name", "Source", "Destination", "RW")}
                for m in container["Mounts"]
            ],
            "networks": {
                k: {v: n.get(v) for v in ("IPAddress", "Gateway")}
                for k, n in container["NetworkSettings"]["Networks"].items()
            },
        }
    require(
        {"api", "worker", "postgres", "storage"} <= set(result), "EGRESS_RUNNING_STACK_REQUIRED"
    )
    return result


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
    probe = (
        "import socket,ipaddress; expected=ipaddress.ip_address("
        + repr(values["ASM_TELEGRAM_EGRESS_IP"])
        + "); "
    )
    probe += "rows=[socket.getaddrinfo('api.telegram.org',443,f,socket.SOCK_STREAM) for f in (socket.AF_UNSPEC,socket.AF_INET,socket.AF_INET6)]; "
    probe += "assert all(rows); ips=[ipaddress.ip_address(x[4][0]) for row in rows for x in row]; "
    probe += "assert all((getattr(x,'ipv4_mapped',None) or x)==expected for x in ips)"
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


def compare_deployment(before, after, state):
    for name, previous in before.items():
        if name in {"api", "worker", "telegram-egress"}:
            continue
        require(after.get(name) == previous, "EGRESS_UNRELATED_CONTAINER_CHANGED")
    default = state["project"] + "_default"
    for name in ("api", "worker"):
        require(
            before[name]["image"] == after[name]["image"]
            and before[name]["mounts"] == after[name]["mounts"],
            "EGRESS_CALLER_IMAGE_OR_VOLUME_CHANGED",
        )
        require(
            after[name]["networks"][default]["Gateway"]
            == before[name]["networks"][default]["Gateway"],
            "EGRESS_DEFAULT_GATEWAY_CHANGED",
        )
    relay = after["telegram-egress"]
    require(
        relay["image"] == state["image_id"]
        and relay["networks"][state["project"] + "_telegram-egress"]["IPAddress"]
        == str(ipaddress.ip_network(state["subnet"])[2]),
        "EGRESS_RUNNING_RELAY_IDENTITY",
    )


def deploy(state, directory):
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


def rollback(state, directory):
    # Explicit operator action only; disable first while the fixed route still exists.
    path = checked_path(state["telegram_env"])
    raw = path.read_bytes()
    require(len(raw) <= 65536, "EGRESS_ENV_LIMIT")
    lines = raw.splitlines(keepends=True)
    matches = [i for i, line in enumerate(lines) if line.startswith(b"ASM_TELEGRAM_ENABLED=")]
    require(len(matches) == 1, "EGRESS_ENV_ENABLED_FIELD")
    lines[matches[0]] = b"ASM_TELEGRAM_ENABLED=false\n"
    write_private(path, b"".join(lines), private_parent=False)
    env = clean_environment()
    before = snapshot(state, directory, disabled=False)
    command(
        [
            *compose_prefix(state, directory),
            "up",
            "-d",
            "--no-deps",
            "--pull",
            "never",
            "--force-recreate",
            "api",
            "worker",
        ],
        timeout=120,
        environment=env,
    )
    snapshot(state, directory)  # disabled callers, with mapping still installed
    command(
        [
            *compose_prefix(state, directory, overlay=False),
            "up",
            "-d",
            "--no-deps",
            "--pull",
            "never",
            "--force-recreate",
            "api",
            "worker",
        ],
        timeout=120,
        environment=env,
    )
    command([*compose_prefix(state, directory), "stop", "telegram-egress"], environment=env)
    after = snapshot(state, directory)
    for name, previous in before.items():
        if name in {"api", "worker", "telegram-egress"}:
            if name in {"api", "worker"}:
                require(
                    after[name]["image"] == previous["image"]
                    and after[name]["mounts"] == previous["mounts"],
                    "EGRESS_ROLLBACK_CALLER_DRIFT",
                )
            continue
        require(after.get(name) == previous, "EGRESS_ROLLBACK_UNRELATED_DRIFT")
    require(
        all(
            state["project"] + "_telegram-egress" not in after[n]["networks"]
            for n in ("api", "worker")
        ),
        "EGRESS_ROLLBACK_MAPPING_RETAINED",
    )
    write_private(
        directory / "rollback.json",
        encoded({"before": before, "after": after, "telegram_disabled": True}),
    )


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=("prepare", "verify", "snapshot", "deploy", "preflight", "compose", "rollback"),
    )
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--profile")
    parser.add_argument("--telegram-env")
    parser.add_argument("--project", default="asm-telegram-test")
    parser.add_argument("--accepted-sha")
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
            directory = Path(args.state_dir).absolute()
            if args.action == "rollback":
                state = strict_json(private_bytes(directory / "state.json"))
                source_check(state["source_sha"])
                require(
                    state["image"] == IMAGE and state["uid"] == os.getuid(), "EGRESS_ROLLBACK_STATE"
                )
            else:
                state = verify(directory)
            model = checked_model(state, directory)
            if args.action == "snapshot":
                require(
                    all(
                        model["services"][n]["environment"]["ASM_TELEGRAM_ENABLED"] == "false"
                        for n in ("api", "worker")
                    ),
                    "EGRESS_PERSISTED_TELEGRAM_MUST_BE_DISABLED",
                )
                write_private(
                    directory / "deployment-before.json", encoded(snapshot(state, directory))
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
                        [*compose_prefix(state, directory), *extra], env=clean_environment()
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
