#!/usr/bin/env python3
"""Bounded opt-in polling deployment for the accepted fresh Selectel TEST.

Uses private receipts from the previous accepted activation. No application image
rebuild, source checkout change, DB/S3 credential in the receiver, or app restart.
Commands: enable, status, rollback. Packaging embeds the sibling receiver source.
"""

import copy
import hashlib
import importlib.util
import json
import os
import pwd
import re
import resource
import stat
import sys
import time
from pathlib import Path
from types import SimpleNamespace

BUNDLED_RECEIVER = None
ACTIVATOR = Path("/home/asmoperator/asm_fresh_telegram_activate.py")
ACTIVATOR_SHA256 = "4cc75fd3acc325865916d153b5d2e944357e69edb3852416c84cd9a0085a7549"
PROJECT = "asm-telegram-polling"
RECEIVER_TARGET = "/run/asm-polling-receiver.py"
STATES = {
    "STARTING",
    "WAITING_WEBHOOK_REMOVAL",
    "RUNNING",
    "ACK_PENDING",
    "BLOCKED",
    "RETRYING",
    "STOPPED",
}

OPERATOR_CODE = r"""
import asyncio,json,os,sys
from asm.telegram.client import TelegramClient,TelegramError
from asm.telegram.config import TelegramSettings

async def main():
    client=TelegramClient(TelegramSettings())
    try:
        async with asyncio.timeout(25):
            action=sys.argv[1]
            info=await client.get_webhook_info()
            if info['url'] not in {'',client.settings.webhook_url}:
                raise RuntimeError('FOREIGN_WEBHOOK')
            if action=='preflight':
                await client.get_me()
                connection=await client.get_business_connection(os.environ['ASM_TELEGRAM_CONNECTION_ID'])
                if connection.owner_user_id!=os.environ['ASM_TELEGRAM_EXPECTED_OWNER_ID'] or not connection.is_enabled or not connection.can_reply:
                    raise RuntimeError('CONNECTION_NOT_READY')
            elif action=='remove':
                if info['url']:
                    result=await client._readonly('deleteWebhook',{'drop_pending_updates':False})
                    if result is not True: raise RuntimeError('WEBHOOK_REMOVE_UNCONFIRMED')
                info=await client.get_webhook_info()
                if info['url']: raise RuntimeError('WEBHOOK_STILL_SET')
            elif action=='restore':
                if not info['url']: await client.set_webhook()
                info=await client.get_webhook_info()
                if info['url']!=client.settings.webhook_url: raise RuntimeError('WEBHOOK_RESTORE_UNCONFIRMED')
            elif action!='inspect':
                raise RuntimeError('INVALID_ACTION')
            return {'ok':True,'webhook':'EXPECTED' if info['url'] else 'NONE','pending_updates':info['pending_update_count']}
    except TelegramError as error:
        return {'ok':False,'code':error.code.value}
    except TimeoutError:
        return {'ok':False,'code':'OPERATOR_TIMEOUT'}
    except Exception as error:
        import re
        code=str(error)
        return {'ok':False,'code':code if re.fullmatch('[A-Z0-9_]{1,80}',code) else 'OPERATOR_FAILED'}
    finally:
        try:
            async with asyncio.timeout(3): await client.aclose()
        except Exception: pass
print(json.dumps(asyncio.run(main()),sort_keys=True))
"""


def need(condition, code):
    if not condition:
        raise RuntimeError(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def error_code(error):
    value = str(error)
    return value if re.fullmatch(r"[A-Z0-9_]{1,100}", value) else "POLLING_OPERATION_FAILED"


def load_checked(name, path, expected):
    for item in (path, *path.parents):
        need(not item.is_symlink(), "SCRIPT_SYMLINK")
    info = path.stat()
    need(
        stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and not info.st_mode & 0o022,
        "SCRIPT_PERMISSIONS",
    )
    need(digest(path.read_bytes()) == expected, "SCRIPT_CHANGED")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bootstrap():
    need(pwd.getpwuid(os.getuid()).pw_name == "asmoperator", "WRONG_USER")
    act = load_checked("asm_polling_activation", ACTIVATOR, ACTIVATOR_SHA256)
    p = load_checked("asm_polling_preparation", act.PREPARER, act.PREPARER_SHA256)
    need(
        not any(
            os.environ.get(k)
            for k in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH")
        ),
        "DOCKER_OVERRIDE_PRESENT",
    )
    for key in tuple(os.environ):
        if key.startswith(
            ("ASM_", "TG_", "PG_", "STORAGE_", "TELEGRAM_EGRESS_", "COMPOSE_")
        ) or key in {"PYTHON_IMAGE", "UV_IMAGE", "NODE_IMAGE", "WEB_IMAGE", "DB_IMAGE"}:
            del os.environ[key]
    os.environ["DOCKER_HOST"] = "unix:///var/run/docker.sock"
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    os.chdir(p.APP)
    need(
        p.git_output("rev-parse", "HEAD") == p.SOURCE_SHA
        and p.git_output("rev-parse", "HEAD^{tree}") == p.SOURCE_TREE,
        "SOURCE_CHANGED",
    )
    need(not p.git_output("status", "--porcelain", "--untracked-files=all"), "SOURCE_NOT_CLEAN")
    need(
        p.git_output("hash-object", "scripts/prepare_telegram_egress.py") == p.HELPER_BLOB,
        "EGRESS_HELPER_CHANGED",
    )
    helper = act.load_module("asm_polling_egress", p.APP / "scripts/prepare_telegram_egress.py")
    return SimpleNamespace(act=act, p=p, helper=helper)


def command(c, args, timeout=40):
    return c.helper.command(args, timeout=timeout, environment=c.helper.clean_environment())


def check_inputs(c):
    need(
        all(
            digest(c.helper.private_bytes(Path(path))) == value
            for path, value in c.intent["inputs"].items()
        ),
        "ACCEPTED_INPUTS_CHANGED",
    )
    need(not c.p.git_output("status", "--porcelain", "--untracked-files=all"), "SOURCE_NOT_CLEAN")


def context(c):
    activation = c.p.SETUP / "activation"
    raw = c.helper.private_bytes(activation / "intent.json")
    c.activation_sha = digest(raw)
    c.intent = c.helper.strict_json(raw)
    complete = c.helper.strict_json(c.helper.private_bytes(activation / "complete.json"))
    binding_raw = c.helper.private_bytes(activation / "binding.json")
    binding = c.helper.strict_json(binding_raw)
    need(
        complete.get("intent_sha256") == c.activation_sha
        and binding.get("intent_sha256") == c.activation_sha
        and complete.get("binding_sha256") == digest(binding_raw)
        and complete.get("telegram_runtime") == "ENABLED",
        "ACTIVATION_NOT_COMPLETE",
    )
    c.act.validate_binding(binding["result"], c.p)
    check_inputs(c)
    for name in ("runtime", "operator"):
        need(
            digest(c.helper.private_bytes(activation / (name + ".json")))
            == c.intent[name + "_overlay_sha256"],
            "ACTIVATION_OVERLAY_CHANGED",
        )
    c.state = c.helper.verify(c.p.EGRESS)
    c.base = c.helper.checked_model(c.state, c.p.EGRESS)
    need(digest(c.helper.encoded(c.base)) == c.intent["base_model_sha256"], "BASE_MODEL_CHANGED")
    c.operator_prefix = [
        *c.helper.compose_prefix(c.state, c.p.EGRESS, operator_inputs=True),
        "-f",
        str(activation / "operator.json"),
    ]
    model = json.loads(command(c, [*c.operator_prefix, "config", "--format", "json"]))
    c.operator = model["services"]["telegram-operator"]
    c.values = c.operator["environment"]
    need(c.operator["image"] == c.intent["operator_image"], "OPERATOR_IMAGE_CHANGED")
    c.helper.source_image_check(c.intent["operator_image"])
    before_raw = c.helper.private_bytes(activation / "before.json")
    need(digest(before_raw) == c.intent["before_sha256"], "ACTIVATION_BASELINE_CHANGED")
    c.before = c.helper.strict_json(before_raw)
    c.started = {
        name: c.helper.strict_json(c.helper.private_bytes(activation / (name + "-started.json")))
        for name in c.act.SERVICES
    }
    c.done = {
        name: c.helper.strict_json(c.helper.private_bytes(activation / (name + "-done.json")))
        for name in c.act.SERVICES
    }
    for name in c.act.SERVICES:
        need(
            c.started[name] == {"intent_sha256": c.activation_sha, "service": name}
            and c.done[name].get("intent_sha256") == c.activation_sha
            and c.done[name].get("service") == name,
            "ACTIVATION_SERVICE_RECEIPT_CHANGED",
        )
    c.directory = c.p.SETUP / "polling"
    c.prefix = [
        "docker",
        "compose",
        "--project-name",
        PROJECT,
        "--project-directory",
        str(c.directory),
        "-f",
        str(c.directory / "compose.json"),
    ]
    return c


def app_runtime(c):
    actual, modes = c.act.runtime_capture(c.helper, c.state, c.base, c.values)
    c.act.compare_runtime(c.helper, c.before, actual, modes, c.intent["images"], c.started, c.done)
    need(
        all(modes.get(name) == "enabled" and actual[name]["running"] for name in c.act.SERVICES),
        "APP_NOT_ENABLED",
    )
    return actual


def receiver_bytes():
    raw = (
        BUNDLED_RECEIVER.encode()
        if BUNDLED_RECEIVER is not None
        else Path(__file__).with_name("telegram_polling_receiver.py").read_bytes()
    )
    need(0 < len(raw) < 65536, "RECEIVER_SIZE")
    compile(raw, "telegram_polling_receiver.py", "exec")
    return raw


def desired_model(c, source_sha):
    networks = {
        key: {"external": True, "name": c.base["networks"][key]["name"]}
        for key in ("default", "telegram-egress", "telegram-egress-v6")
    }
    env = {key: c.values[key] for key in c.act.TG_FIELDS}
    env["ASM_ENVIRONMENT"] = "LOCAL"
    need(env["ASM_TELEGRAM_ENABLED"] == "true", "RECEIVER_NOT_ENABLED")
    return {
        "services": {
            "receiver": {
                "image": c.intent["operator_image"],
                "user": f"{os.getuid()}:{os.getgid()}",
                "entrypoint": ["python", RECEIVER_TARGET],
                "command": [],
                "environment": env,
                "extra_hosts": copy.deepcopy(c.operator["extra_hosts"]),
                "networks": {
                    "default": {"gw_priority": 1},
                    "telegram-egress": {},
                    "telegram-egress-v6": {},
                },
                "read_only": True,
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
                "pids_limit": 64,
                "mem_limit": "256m",
                "cpus": 0.5,
                "restart": "unless-stopped",
                "stop_grace_period": "10s",
                "logging": {"driver": "none"},
                "tmpfs": [
                    "/tmp:rw,noexec,nosuid,size=16m",
                    f"/run/asm-polling:rw,noexec,nosuid,size=1m,uid={os.getuid()},gid={os.getgid()},mode=0700",
                ],
                "labels": {
                    "asm.scope": "synthetic-telegram-test",
                    "asm.polling.activation": c.activation_sha,
                    "asm.polling.source": source_sha,
                },
                "volumes": [
                    {
                        "type": "bind",
                        "source": str(c.directory / "receiver.py"),
                        "target": RECEIVER_TARGET,
                        "read_only": True,
                        "bind": {"create_host_path": False},
                    }
                ],
                "healthcheck": {
                    "test": ["CMD", "python", RECEIVER_TARGET, "--health"],
                    "interval": "5s",
                    "timeout": "3s",
                    "retries": 3,
                    "start_period": "5s",
                },
            }
        },
        "networks": networks,
    }


def prepare(c, *, write):
    raw = receiver_bytes()
    c.receiver_sha = digest(raw)
    model = desired_model(c, c.receiver_sha)
    compose = c.helper.encoded(model).replace(b"$", b"$$")
    c.manifest = {
        "version": 1,
        "activation_sha256": c.activation_sha,
        "receiver_sha256": c.receiver_sha,
        "compose_sha256": digest(compose),
        "image": c.intent["operator_image"],
    }
    if write:
        c.directory.mkdir(mode=0o700, exist_ok=True)
    need(c.directory.exists(), "POLLING_NOT_PREPARED")
    c.helper.checked_path(c.directory, directory=True)
    need(
        set(x.name for x in c.directory.iterdir())
        <= {"receiver.py", "compose.json", "manifest.json", "mode.json"},
        "POLLING_DIRECTORY_NOT_OWNED",
    )
    for name, content in (
        ("receiver.py", raw),
        ("compose.json", compose),
        ("manifest.json", c.helper.encoded(c.manifest)),
    ):
        path = c.directory / name
        if path.exists() or path.is_symlink():
            need(c.helper.private_bytes(path) == content, "POLLING_PRIVATE_FILE_CHANGED")
        else:
            need(write, "POLLING_NOT_PREPARED")
            c.helper.write_private(path, content)
    resolved = json.loads(command(c, [*c.prefix, "config", "--format", "json"]))
    service = resolved["services"]["receiver"]
    need(
        set(resolved["services"]) == {"receiver"}
        and service["image"] == c.manifest["image"]
        and service["environment"] == model["services"]["receiver"]["environment"],
        "POLLING_MODEL_CHANGED",
    )
    need(
        all(
            resolved["networks"][key]["external"]
            and resolved["networks"][key]["name"] == value["name"]
            for key, value in model["networks"].items()
        ),
        "POLLING_NETWORK_CHANGED",
    )
    return model


def operator(c, action):
    need(action in {"preflight", "inspect", "remove", "restore"}, "OPERATOR_ACTION")
    raw = command(
        c,
        [
            *c.operator_prefix,
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
            OPERATOR_CODE,
            action,
        ],
        timeout=35,
    )
    need(len(raw) <= 4096, "OPERATOR_REPORT_SIZE")
    value = json.loads(raw)
    if value.get("ok") is not True:
        raise RuntimeError(error_code(RuntimeError(value.get("code", "OPERATOR_FAILED"))))
    need(
        value.get("webhook") in {"EXPECTED", "NONE"}
        and type(value.get("pending_updates")) is int
        and value["pending_updates"] >= 0,
        "OPERATOR_REPORT_SHAPE",
    )
    return value


def container(c):
    ids = (
        command(
            c, ["docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=" + PROJECT]
        )
        .decode()
        .split()
    )
    need(len(ids) <= 1, "MULTIPLE_RECEIVERS")
    if not ids:
        return None
    item = json.loads(command(c, ["docker", "inspect", ids[0]]))[0]
    labels = item["Config"]["Labels"]
    need(
        labels.get("com.docker.compose.service") == "receiver"
        and labels.get("asm.polling.activation") == c.activation_sha
        and labels.get("asm.polling.source") == c.receiver_sha
        and item["Image"] == c.manifest["image"],
        "RECEIVER_IDENTITY_CHANGED",
    )
    env = c.helper.migration_environment(item["Config"].get("Env"))
    desired = desired_model(c, c.receiver_sha)
    need(
        all(
            env.get(key) == value
            for key, value in desired["services"]["receiver"]["environment"].items()
        ),
        "RECEIVER_ENV_CHANGED",
    )
    need(
        not any(
            key.startswith(("PG_", "STORAGE_"))
            or key in {"ASM_DATABASE_URL", "ASM_MIGRATION_DATABASE_URL"}
            for key in env
        ),
        "RECEIVER_PRIVILEGED_CREDENTIAL",
    )
    need(
        item["Config"].get("Entrypoint") == ["python", RECEIVER_TARGET]
        and not item["Config"].get("Cmd"),
        "RECEIVER_COMMAND_CHANGED",
    )
    binds = [x for x in item["Mounts"] if x["Type"] == "bind"]
    need(
        len(binds) == 1
        and binds[0]["Source"] == str(c.directory / "receiver.py")
        and binds[0]["Destination"] == RECEIVER_TARGET
        and binds[0]["RW"] is False,
        "RECEIVER_MOUNT_CHANGED",
    )
    need(
        set(item["NetworkSettings"]["Networks"])
        == {v["name"] for v in desired["networks"].values()},
        "RECEIVER_NETWORK_CHANGED",
    )
    host = item["HostConfig"]
    need(
        host.get("ReadonlyRootfs") is True
        and not host.get("Privileged")
        and not host.get("PortBindings")
        and "ALL" in host.get("CapDrop", [])
        and host["RestartPolicy"]["Name"] == "unless-stopped",
        "RECEIVER_ISOLATION_CHANGED",
    )
    return item


def receiver_status(c):
    raw = command(
        c, [*c.prefix, "exec", "-T", "receiver", "python", RECEIVER_TARGET, "--status"], timeout=8
    )
    need(len(raw) < 4096, "RECEIVER_STATUS_SIZE")
    value = json.loads(raw)
    need(value.get("version") == 1 and value.get("state") in STATES, "RECEIVER_STATUS_SHAPE")
    need(
        value.get("code") is None or re.fullmatch(r"[A-Z0-9_]{1,80}", str(value["code"])),
        "RECEIVER_STATUS_CODE",
    )
    need(
        all(
            type(value.get(key)) is int and value[key] >= 0
            for key in ("successful_polls", "durable_deliveries", "confirmed_responses")
        ),
        "RECEIVER_STATUS_COUNTERS",
    )
    need(
        type(value.get("ack_pending")) is bool and type(value.get("updated_at")) in {float, int},
        "RECEIVER_STATUS_SHAPE",
    )
    allowed = {
        "version",
        "state",
        "code",
        "updated_at",
        "successful_polls",
        "durable_deliveries",
        "confirmed_responses",
        "ack_pending",
    }
    need(set(value) == allowed, "RECEIVER_STATUS_FIELDS")
    value["age_seconds"] = int(time.time() - value["updated_at"])
    return value


def wait_state(c, states, seconds):
    deadline = time.monotonic() + seconds
    last = None
    while time.monotonic() < deadline:
        try:
            last = receiver_status(c)
            if last["state"] in states and 0 <= last["age_seconds"] < 45:
                return last
        except Exception:
            pass
        time.sleep(1)
    if last:
        print("ASM_POLLING_RECEIVER=" + json.dumps(last, sort_keys=True), flush=True)
    raise RuntimeError("RECEIVER_NOT_READY")


def save_mode(c, mode, provider):
    c.helper.write_private(
        c.directory / "mode.json",
        c.helper.encoded(
            {
                "version": 1,
                "manifest_sha256": digest(c.helper.encoded(c.manifest)),
                "mode": mode,
                "observed_at": int(time.time()),
                "pending_updates": provider["pending_updates"],
            }
        ),
    )


def enable(c):
    app_runtime(c)
    prepare(c, write=True)
    operator(c, "preflight")
    current = container(c)
    print("ASM_POLLING_STAGE=START_RECEIVER", flush=True)
    if current is None:
        command(
            c,
            [*c.prefix, "up", "-d", "--no-deps", "--no-build", "--pull", "never", "receiver"],
            timeout=40,
        )
    elif not current["State"]["Running"]:
        command(c, ["docker", "start", current["Id"]])
    need(container(c)["State"]["Running"], "RECEIVER_NOT_RUNNING")
    wait_state(c, {"WAITING_WEBHOOK_REMOVAL", "RUNNING", "ACK_PENDING"}, 35)
    # A running, preflighted receiver exists before removing the webhook. If the
    # SSH client disconnects after this call it can continue without the wrapper.
    print("ASM_POLLING_STAGE=SWITCH_RECEIVE_MODE", flush=True)
    operator(c, "remove")
    status = wait_state(c, {"RUNNING", "ACK_PENDING"}, 55)
    need(status["successful_polls"] > 0, "POLLING_NOT_OBSERVED")
    app_runtime(c)
    check_inputs(c)
    container(c)
    provider = operator(c, "inspect")
    need(provider["webhook"] == "NONE", "WEBHOOK_STILL_SET")
    save_mode(c, "POLLING", provider)
    print("ASM_POLLING_RECEIVER=" + json.dumps(status, sort_keys=True))
    print("ASM_POLLING_TELEGRAM=" + json.dumps(provider, sort_keys=True))
    print("ASM_APP_PRESERVATION=PASS")
    print("ASM_TELEGRAM_MODE=POLLING")
    print("ASM_POLLING_ENABLE=PASS")


def rollback(c):
    prepare(c, write=False)
    current = container(c)
    if current and current["State"]["Running"]:
        command(c, ["docker", "stop", "--time", "10", current["Id"]], timeout=20)
    current = container(c)
    need(current is None or not current["State"]["Running"], "RECEIVER_STILL_RUNNING")
    provider = operator(c, "restore")
    need(provider["webhook"] == "EXPECTED", "WEBHOOK_RESTORE_UNCONFIRMED")
    check_inputs(c)
    save_mode(c, "WEBHOOK", provider)
    print("ASM_POLLING_TELEGRAM=" + json.dumps(provider, sort_keys=True))
    print("ASM_TELEGRAM_MODE=WEBHOOK")
    print("ASM_POLLING_ROLLBACK=PASS")


def status(c):
    prepare(c, write=False)
    try:
        app_runtime(c)
        print("ASM_APP_RUNTIME=PASS")
    except Exception as error:
        print("ASM_APP_RUNTIME=CHECK_FAILED CODE=" + error_code(error))
    current = container(c)
    if current and current["State"]["Running"]:
        print("ASM_POLLING_RECEIVER=" + json.dumps(receiver_status(c), sort_keys=True))
    else:
        print("ASM_POLLING_RECEIVER=STOPPED")
    print("ASM_POLLING_TELEGRAM=" + json.dumps(operator(c, "inspect"), sort_keys=True))
    print("ASM_POLLING_STATUS=COMPLETE")


def main():
    stage = "PRECHECK"
    try:
        os.umask(0o077)
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        sys.dont_write_bytecode = True
        need(
            len(sys.argv) == 2 and sys.argv[1] in {"enable", "status", "rollback"},
            "USAGE_ENABLE_STATUS_ROLLBACK",
        )
        c = bootstrap()
        with c.helper.operation_lock(c.p.EGRESS):
            stage = "VERIFY_ACCEPTED_ACTIVATION"
            context(c)
            stage = sys.argv[1].upper()
            {"enable": enable, "status": status, "rollback": rollback}[sys.argv[1]](c)
        return 0
    except KeyboardInterrupt:
        code = "CANCELLED"
    except Exception as error:
        code = error_code(error)
    print("ASM_POLLING_RECOVERY=STOP STAGE=" + stage + " CODE=" + code, file=sys.stderr)
    print("ASM_POLLING_NEXT=RUN_STATUS_OR_REPEAT_ENABLE_OR_ROLLBACK", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
