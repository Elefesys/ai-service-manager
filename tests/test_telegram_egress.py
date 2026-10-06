"""E01/E02/E05 config and operator guards; real boundary is a mandatory Docker lane."""

import argparse
import base64
import copy
import hashlib
import json
import os
import subprocess
import sys
import zlib
from pathlib import Path
from uuid import UUID

import pytest

from scripts import prepare_telegram_egress as egress


def test_split_private_inputs_preserve_https_runtime_and_strict_drift(tmp_path, monkeypatch):
    root = tmp_path / "checkout"
    root.mkdir(mode=0o700)
    monkeypatch.setattr(egress, "ROOT", root)
    credentials = b"PG_RUNTIME_PASSWORD=synthetic-db\nSTORAGE_SECRET_KEY=synthetic-storage\n"
    operational = {
        "ASM_AUTH_ORIGINS": '["https://console.fixture.invalid"]',
        "ASM_STORAGE_ENDPOINT": "https://files.fixture.invalid",
    }
    staged = dict(
        operational,
        TG_BOT_TOKEN="staged-token",
        TG_WEBHOOK_SECRET="staged-secret",
        ASM_TELEGRAM_EXPECTED_BOT_ID="9911",
        ASM_TELEGRAM_WEBHOOK_URL="https://console.fixture.invalid/webhooks/telegram",
    )
    staged_bytes = "".join(f"{k}='{v}'\n" for k, v in staged.items()).encode()
    egress.write_private(root / ".env", credentials)
    egress.write_private(tmp_path / "telegram.env", staged_bytes)
    egress.write_private(tmp_path / "profile.json", egress.encoded(profile()))
    defaults = dict(
        operational,
        ASM_AUTH_ORIGINS='["http://localhost:8000"]',
        ASM_STORAGE_ENDPOINT="http://storage:9000",
    )
    active = dict(
        operational,
        ASM_TELEGRAM_ENABLED="false",
        TG_BOT_TOKEN="",
        TG_WEBHOOK_SECRET="",
        ASM_TELEGRAM_EXPECTED_BOT_ID="",
        ASM_TELEGRAM_WEBHOOK_URL="",
        ASM_DATABASE_URL="synthetic-db-url",
        ASM_STORAGE_ACCESS_KEY="synthetic-access",
        ASM_STORAGE_SECRET_KEY="synthetic-storage",
    )
    containers = [
        {
            "Id": name,
            "Image": "image",
            "Config": {
                "Labels": {"com.docker.compose.service": name},
                "Env": [k + "=" + v for k, v in active.items()],
            },
            "Mounts": [],
            "NetworkSettings": {"Networks": {}},
        }
        for name in ("api", "worker", "postgres", "storage")
    ]
    state_dir = tmp_path / "state"
    monkeypatch.setattr(egress, "source_check", lambda *_: None)
    monkeypatch.setattr(egress, "source_image_check", lambda *_: None)
    monkeypatch.setattr(egress, "image_check", lambda *_: "image")
    monkeypatch.setattr(egress, "database_identity", lambda *_: {"database": "same"})

    def command(args, **_):
        if args[:2] == ["docker", "inspect"]:
            return egress.encoded(containers)
        if args[-2:] == ["ps", "-q"]:
            return b"api worker postgres storage"
        if "config" in args:
            # External Compose boundary: the two accepted files resolve staged
            # values; no model is derived from the inspected running containers.
            assert str(tmp_path / "telegram.env") in args
            return egress.encoded(
                {"services": {n: {"environment": staged} for n in ("api", "worker")}}
            )
        return b"[]"

    monkeypatch.setattr(egress, "command", command)
    egress.prepare(
        argparse.Namespace(
            accepted_sha="a" * 40,
            project="fixture",
            profile=str(tmp_path / "profile.json"),
            telegram_env=str(tmp_path / "telegram.env"),
            state_dir=str(state_dir),
        )
    )
    state = json.loads((state_dir / "state.json").read_bytes())

    def model(s, directory):
        values = dict(active, **defaults)
        args = egress.compose_prefix(s, directory)
        overlay = directory / "runtime.json"
        if str(overlay) in args:
            payload = json.loads(egress.private_bytes(overlay))
            assert set(payload) == {"services"} and set(payload["services"]) == {"api", "worker"}
            for service in payload["services"].values():
                assert set(service) == {"environment"} and service["environment"] == operational
            values.update(payload["services"]["api"]["environment"])
        return {"services": {n: {"environment": values} for n in ("api", "worker")}}

    monkeypatch.setattr(egress, "checked_model", model)
    egress.snapshot(state, state_dir)  # Reviewed implementation fails here, before any up.
    assert (root / ".env").read_bytes() == credentials
    assert (tmp_path / "telegram.env").read_bytes() == staged_bytes
    egress.verify_runtime(state, state_dir)
    original_runtime = (state_dir / "runtime.json").read_bytes()
    staged["TG_BOT_TOKEN"] = "another-staged-token"
    egress.verify_runtime(state, state_dir)  # Still operator-only, never copied into runtime.
    for field in operational:
        previous = staged[field]
        staged[field] = "changed-config-input"
        with pytest.raises(egress.EgressError, match="EGRESS_RUNTIME_INPUTS_CHANGED"):
            egress.verify_runtime(state, state_dir)
        staged[field] = previous
    egress.write_private(state_dir / "runtime.json", original_runtime + b" ")
    with pytest.raises(egress.EgressError, match="EGRESS_RUNTIME_INPUTS_CHANGED"):
        egress.verify_runtime(state, state_dir)
    egress.write_private(state_dir / "runtime.json", original_runtime)
    for field in (
        *operational,
        "TG_BOT_TOKEN",
        "TG_WEBHOOK_SECRET",
        "ASM_TELEGRAM_EXPECTED_BOT_ID",
        "ASM_TELEGRAM_WEBHOOK_URL",
        "ASM_DATABASE_URL",
        "ASM_STORAGE_ACCESS_KEY",
        "ASM_STORAGE_SECRET_KEY",
    ):
        containers[0]["Config"]["Env"] = [
            k + "=" + ("drift" if k == field else v) for k, v in active.items()
        ]
        with pytest.raises(egress.EgressError, match="EGRESS_RUNNING_ENVIRONMENT_DRIFT"):
            egress.snapshot(state, state_dir)


@pytest.mark.parametrize("alias", [False, True])
def test_prepare_rejects_canonical_checkout_state_before_any_effect(tmp_path, monkeypatch, alias):
    checkout, outside = tmp_path / "checkout", tmp_path / "outside"
    checkout.mkdir(mode=0o700)
    outside.mkdir(mode=0o700)
    monkeypatch.setattr(egress, "ROOT", checkout)
    egress.write_private(outside / "profile.json", egress.encoded(profile()))
    egress.write_private(outside / "telegram.env", b"ASM_TELEGRAM_ENABLED=false\n")
    target = checkout / "private-state"
    requested = outside / ".." / "checkout" / "private-state" if alias else target
    calls = []
    monkeypatch.setattr(egress, "source_check", lambda *_: calls.append("source"))
    monkeypatch.setattr(egress, "command", lambda *_: calls.append("command") or b"[]")
    monkeypatch.setattr(egress, "image_check", lambda *_: calls.append("image") or "image")
    with pytest.raises(egress.EgressError, match="EGRESS_PRIVATE_STATE_OUTSIDE_CHECKOUT"):
        egress.prepare(
            argparse.Namespace(
                accepted_sha="a" * 40,
                profile=str(outside / "profile.json"),
                telegram_env=str(outside / "telegram.env"),
                state_dir=str(requested),
                project="fixture",
            )
        )
    assert not target.exists() and not list(checkout.iterdir())
    assert calls == []


def test_prepare_canonical_outside_path_and_symlink_alias_guard(tmp_path, monkeypatch):
    checkout, outside = tmp_path / "checkout", tmp_path / "outside"
    checkout.mkdir(mode=0o700)
    outside.mkdir(mode=0o700)
    monkeypatch.setattr(egress, "ROOT", checkout)
    monkeypatch.setattr(egress, "source_check", lambda *_: None)
    calls = []
    monkeypatch.setattr(egress, "command", lambda *_: b"[]")
    monkeypatch.setattr(egress, "runtime_overlay", lambda *_: b'{"services":{}}\n')
    monkeypatch.setattr(egress, "image_check", lambda *_: calls.append("image") or "image")
    egress.write_private(outside / "profile.json", egress.encoded(profile()))
    egress.write_private(outside / "telegram.env", b"ASM_TELEGRAM_ENABLED=false\n")
    alias = tmp_path / "alias"
    alias.symlink_to(outside, target_is_directory=True)
    args = argparse.Namespace(
        accepted_sha="a" * 40,
        profile=str(outside / "profile.json"),
        telegram_env=str(outside / "telegram.env"),
        project="fixture",
    )
    # A later '..' must not normalize away the traversed symlink.
    args.state_dir = str(alias / ".." / "new-state")
    with pytest.raises(egress.EgressError, match="EGRESS_SYMLINK"):
        egress.prepare(args)
    assert not (tmp_path / "new-state").exists() and calls == []
    args.state_dir = str(outside / ".." / "outside" / "new-state")
    egress.prepare(args)
    target = outside / "new-state"
    assert egress.checked_path(target, directory=True) == target
    state = json.loads(egress.private_bytes(target / "state.json"))
    assert state["profile"] == str(outside / "profile.json")
    assert str(target / "config.json").encode() in egress.private_bytes(target / "route.env")
    assert b".." not in egress.private_bytes(target / "route.env")
    assert calls == ["image"] and not list(checkout.iterdir())


def test_staged_inputs_do_not_enter_disabled_runtime_model_or_relax_drift(monkeypatch):
    state = {"project": "fixture", "telegram_env": "/private/staged.env"}
    fields = {
        "TG_BOT_TOKEN": "",
        "TG_WEBHOOK_SECRET": "",
        "ASM_TELEGRAM_EXPECTED_BOT_ID": "",
        "ASM_TELEGRAM_WEBHOOK_URL": "",
        "ASM_DATABASE_URL": "unchanged-db",
        "ASM_STORAGE_BUCKET": "unchanged-bucket",
    }
    values = dict(fields, ASM_TELEGRAM_ENABLED="false")
    containers = [
        {
            "Id": n,
            "Image": "image",
            "Config": {
                "Labels": {"com.docker.compose.service": n},
                "Env": [k + "=" + v for k, v in values.items()],
            },
            "Mounts": [],
            "NetworkSettings": {"Networks": {}},
        }
        for n in ("api", "worker", "postgres", "storage")
    ]

    def model(s, d):
        expected = dict(values)
        if s["telegram_env"] in egress.compose_prefix(s, d):
            expected.update(
                TG_BOT_TOKEN="staged-token",
                TG_WEBHOOK_SECRET="staged-secret",
                ASM_TELEGRAM_EXPECTED_BOT_ID="9911",
                ASM_TELEGRAM_WEBHOOK_URL="https://synthetic.invalid/webhook",
            )
        return {"services": {n: {"environment": expected} for n in ("api", "worker")}}

    monkeypatch.setattr(egress, "checked_model", model)
    monkeypatch.setattr(egress, "source_image_check", lambda *_: None)
    monkeypatch.setattr(
        egress,
        "command",
        lambda args, **_: (
            egress.encoded(containers)
            if args[:2] == ["docker", "inspect"]
            else b"api worker postgres storage"
        ),
    )
    # The identity probe is independent of this exact environment regression.
    monkeypatch.setattr(egress, "database_identity", lambda *_: {"database": "same"}, raising=False)
    egress.snapshot(state, Path("/private/state"))
    assert state["telegram_env"] in egress.compose_prefix(
        state, Path("/private/state"), operator_inputs=True
    )
    for key in fields:
        containers[0]["Config"]["Env"] = [
            k + "=" + ("drift" if k == key else v) for k, v in values.items()
        ]
        with pytest.raises(egress.EgressError, match="EGRESS_RUNNING_ENVIRONMENT_DRIFT"):
            egress.snapshot(state, Path("/private/state"))
    containers[0]["Config"]["Env"] = [k + "=" + v for k, v in values.items()]
    monkeypatch.setattr(egress, "database_identity", lambda container: {"database": container})
    with pytest.raises(egress.EgressError, match="EGRESS_CALLER_DATABASE_MISMATCH"):
        egress.snapshot(state, Path("/private/state"))


def profile():
    return {
        "dns": {"servers": ["untrusted-desktop.invalid"]},
        "inbounds": [{"protocol": "socks", "listen": "0.0.0.0", "port": 1080}],
        "routing": {"rules": [{"outboundTag": "direct"}]},
        "outbounds": [
            {
                "tag": "desktop-selected",
                "protocol": "vless",
                "settings": {
                    "vnext": [
                        {
                            "address": "192.0.2.10",
                            "port": 443,
                            "users": [
                                {
                                    "id": str(UUID(int=100)),
                                    "encryption": "none",
                                    "flow": "xtls-rprx-vision",
                                }
                            ],
                        }
                    ]
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "serverName": "fixture.invalid",
                        "fingerprint": "chrome",
                        "password": "A" * 43,
                        "shortId": "0123456789abcdef",
                        "spiderX": "/selected",
                    },
                },
            },
            {"tag": "direct", "protocol": "freedom"},
        ],
    }


def test_profile_extracts_only_fixed_tcp_origin_preserving_selected_connection():
    original = profile()
    config = egress.minimal_config(original, "10.203.0.2")
    assert original == profile()
    assert set(config) == {"log", "inbounds", "outbounds", "routing"}
    assert config["inbounds"] == [
        {
            "tag": "telegram-only",
            "listen": "10.203.0.2",
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
    ]
    deny, selected = config["outbounds"]
    assert deny["protocol"] == "blackhole" and selected["protocol"] == "vless"
    assert selected["settings"] == original["outbounds"][0]["settings"]
    assert selected["streamSettings"] == original["outbounds"][0]["streamSettings"]
    serialized = json.dumps(config)
    assert all(
        word not in serialized
        for word in ("freedom", "socks", "untrusted-desktop", "TG_BOT_TOKEN", "sniffed")
    )
    assert config["routing"]["domainStrategy"] == "AsIs"
    assert config["routing"]["rules"][0]["domain"] == ["full:api.telegram.org"]
    assert config["routing"]["rules"][-1]["outboundTag"] == "deny"
    assert config["log"]["error"] == config["log"]["access"] == "none"


@pytest.mark.parametrize(
    "field,value",
    [
        ("mux", None),
        ("mux", {"enabled": True}),
        ("settings", None),
        ("settings", {"vnext": []}),
        ("settings", {"vnext": [None]}),
        ("streamSettings", None),
        ("streamSettings", {"network": "tcp", "security": "tls"}),
        ("proxySettings", {"tag": "direct"}),
        ("sendThrough", "0.0.0.0"),
    ],
)
def test_profile_rejects_ambiguous_or_broader_outbounds(field, value):
    raw = profile()
    raw["outbounds"][0][field] = value
    with pytest.raises(egress.EgressError):
        egress.minimal_config(raw, "10.203.0.2")


@pytest.mark.parametrize(
    "field,value",
    [
        ("allowInsecure", True),
        ("show", True),
        ("serverName", "https://wrong.invalid"),
        ("shortId", "not-hex"),
        ("password", "too-short"),
        ("publicKey", "B" * 43),
    ],
)
def test_profile_preserves_tls_reality_validation_and_one_key(field, value):
    raw = profile()
    raw["outbounds"][0]["streamSettings"]["realitySettings"][field] = value
    with pytest.raises(egress.EgressError):
        egress.minimal_config(raw, "10.203.0.2")


def test_profile_refuses_multiple_selected_connections_and_nonprivate_mapping():
    raw = profile()
    raw["outbounds"].append(copy.deepcopy(raw["outbounds"][0]))
    with pytest.raises(egress.EgressError):
        egress.minimal_config(raw, "10.203.0.2")
    for address in ("127.0.0.1", "0.0.0.0", "8.8.8.8", "169.254.1.1"):
        with pytest.raises(egress.EgressError):
            egress.minimal_config(profile(), address)


@pytest.mark.parametrize(
    "raw", [b'{"outbounds":[],"outbounds":[]}', b'{"x":NaN}', b"[" * 2000, b"x" * 65537]
)
def test_strict_bounded_json(raw):
    with pytest.raises(egress.EgressError):
        egress.strict_json(raw)


def test_private_file_owner_modes_and_both_symlink_boundaries(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    secret = tmp_path / "profile.json"
    secret.write_bytes(b'{"synthetic":true}')
    secret.chmod(0o600)
    assert egress.private_bytes(secret) == b'{"synthetic":true}'
    secret.chmod(0o644)
    with pytest.raises(egress.EgressError):
        egress.private_bytes(secret)
    secret.chmod(0o600)
    alias = tmp_path / "alias.json"
    alias.symlink_to(secret)
    with pytest.raises(egress.EgressError):
        egress.private_bytes(alias)
    linked = tmp_path / "linked"
    linked.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(egress.EgressError):
        egress.private_bytes(linked / "profile.json")
    tmp_path.chmod(0o755)
    with pytest.raises(egress.EgressError):
        egress.private_bytes(secret)
    tmp_path.chmod(0o700)
    uid = os.getuid()
    monkeypatch.setattr(egress.os, "getuid", lambda: uid + 1)
    with pytest.raises(egress.EgressError):
        egress.private_bytes(secret)


def test_ipam_avoids_host_and_docker_routes_and_never_changes_existing_mapping():
    networks = [{"Name": "existing", "IPAM": {"Config": [{"Subnet": "10.203.0.0/24"}]}}]
    assert (
        egress.select_subnet(networks, [{"dst": "default"}, {"dst": "10.203.1.0/24"}])
        == "10.203.2.0/28"
    )
    assert egress.select_subnet([], [{"dst": "10.0.0.0/8"}]) == "172.29.0.0/28"
    with pytest.raises(egress.EgressError):
        egress.select_subnet(networks, [], "10.203.0.0/28")
    own = {
        "Name": "fixture_telegram-egress",
        "Labels": {"asm.scope": "synthetic-telegram-test"},
        "IPAM": {"Config": [{"Subnet": "10.203.0.0/28", "IPRange": "10.203.0.8/29"}]},
    }
    assert (
        egress.select_subnet([own], [{"dst": "10.203.0.0/28"}], "10.203.0.0/28", own["Name"])
        == "10.203.0.0/28"
    )
    own["IPAM"]["Config"][0]["IPRange"] = "10.203.0.0/28"
    with pytest.raises(egress.EgressError, match="DYNAMIC_RANGE_CHANGED"):
        egress.select_subnet([own], [], "10.203.0.0/28", own["Name"])
    own["Labels"] = {}
    with pytest.raises(egress.EgressError):
        egress.select_subnet([own], [], "10.203.0.0/28", own["Name"])


def test_canonical_source_rejects_added_byte_without_normalization(tmp_path, monkeypatch):
    repository = Path(__file__).resolve().parents[1]
    for path in egress.SOURCE:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((repository / path).read_bytes())
    lock = tmp_path / "infra/telegram-egress/image.lock.env"
    lock.parent.mkdir(parents=True)
    lock.write_text("TELEGRAM_EGRESS_IMAGE=" + egress.IMAGE + "\n")
    monkeypatch.setattr(egress, "ROOT", tmp_path)
    monkeypatch.setattr(egress, "command", lambda args: b"a" * 40 if "rev-parse" in args else b"")
    egress.source_check("a" * 40)
    target = tmp_path / next(iter(egress.SOURCE))
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(egress.EgressError, match="APP_SOURCE_CHANGED"):
        egress.source_check("a" * 40)


def previous_or_modified_client(variant, current):
    if variant == "extra_byte":
        return current + b"\n"
    if variant == "crlf":
        assert b"\r" not in current
        return current.replace(b"\n", b"\r\n")
    previous = zlib.decompress(base64.b64decode(_R1_CLIENT))
    expected = "abe2cfc61297397ffc313d287364741403ccf5bf"
    if variant == "base_connect2":
        assert previous.count(b"httpx.Timeout(connect=5,") == 1
        previous = previous.replace(b"httpx.Timeout(connect=5,", b"httpx.Timeout(connect=2,")
        expected = "53800d23c718910dd338cadee6ba595510c95ff9"
    else:
        assert variant == "failed_candidate"
    assert (
        hashlib.sha1(b"blob " + str(len(previous)).encode() + b"\0" + previous).hexdigest()
        == expected
    )
    return previous


@pytest.mark.parametrize("variant", ["base_connect2", "failed_candidate", "extra_byte", "crlf"])
def test_final_source_pin_accepts_exact_bytes_rejects_old_or_modified_client(
    tmp_path, monkeypatch, variant
):
    repository = Path(__file__).resolve().parents[1]
    for path in egress.SOURCE:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((repository / path).read_bytes())
    lock = tmp_path / "infra/telegram-egress/image.lock.env"
    lock.parent.mkdir(parents=True)
    lock.write_text("TELEGRAM_EGRESS_IMAGE=" + egress.IMAGE + "\n")
    monkeypatch.setattr(egress, "ROOT", tmp_path)
    monkeypatch.setattr(egress, "command", lambda args: b"a" * 40 if "rev-parse" in args else b"")
    egress.source_check("a" * 40)
    target = tmp_path / "backend/src/asm/telegram/client.py"
    exact = target.read_bytes()
    target.write_bytes(previous_or_modified_client(variant, exact))
    with pytest.raises(egress.EgressError, match="EGRESS_APP_SOURCE_CHANGED"):
        egress.source_check("a" * 40)
    target.write_bytes(exact)
    egress.source_check("a" * 40)
    lock.write_text("TELEGRAM_EGRESS_IMAGE=fixture.invalid/foreign@sha256:" + "0" * 64 + "\n")
    with pytest.raises(egress.EgressError, match="EGRESS_IMAGE_PIN_CHANGED"):
        egress.source_check("a" * 40)


@pytest.mark.parametrize("variant", ["base_connect2", "failed_candidate", "extra_byte", "crlf"])
def test_cached_image_probe_rejects_incompatible_client_bytes(tmp_path, monkeypatch, variant):
    # Execute the helper's actual generated Python/hash probe against real files.
    # Only Docker execution/path is substituted: this is unit evidence, NOT an
    # actual cached image, Docker29 or relay execution receipt.
    repository = Path(__file__).resolve().parents[1]
    for path in egress.SOURCE:
        target = tmp_path / path.removeprefix("backend/src/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((repository / path).read_bytes())
    calls = []
    image = "sha256:" + "a" * 64

    def execute_probe(args):
        assert args[:-1] == [
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
        ]
        calls.append(args)
        assert args[-1].count("/app/backend/src") == 1
        probe = args[-1].replace("/app/backend/src", str(tmp_path))
        result = subprocess.run([sys.executable, "-c", probe], capture_output=True, timeout=5)
        egress.require(result.returncode == 0, "EGRESS_COMMAND_FAILED")
        return result.stdout

    monkeypatch.setattr(egress, "command", execute_probe)
    egress.source_image_check(image)
    target = tmp_path / "asm/telegram/client.py"
    target.write_bytes(previous_or_modified_client(variant, target.read_bytes()))
    with pytest.raises(egress.EgressError, match="EGRESS_COMMAND_FAILED"):
        egress.source_image_check(image)
    assert len(calls) == 2


@pytest.mark.parametrize(
    "args",
    [
        ["up", "-d", "scheduler"],
        ["up", "--env-file=foreign", "api"],
        ["-fforeign", "up"],
        ["down", "-v"],
        ["run", "-e", "ASM_TELEGRAM_ENABLED=true", "telegram-operator"],
        ["exec", "api", "printenv"],
        ["up", "--build", "api"],
    ],
)
def test_operator_wrapper_refuses_unissued_overrides_and_destructive_commands(args):
    assert not egress.permitted_compose(args)


def test_rollback_disables_first_retains_other_private_bytes_and_never_resets(
    tmp_path, monkeypatch
):
    tmp_path.chmod(0o700)
    args, directory, actual, _ = partial_state(tmp_path, monkeypatch)
    state = json.loads((directory / "state.json").read_bytes())
    private = Path(state["telegram_env"])
    staged = b"TG_BOT_TOKEN='staged-do-not-print'\nASM_TELEGRAM_ENABLED=false\n"
    egress.write_private(private, staged)
    runtime = egress.ROOT / ".env"
    raw = (
        b"TG_BOT_TOKEN='synthetic-do-not-print'\nASM_TELEGRAM_ENABLED=true\nKEEP_DATE=2030-01-01\n"
    )
    egress.write_private(runtime, raw)
    calls, snapshots = [], []
    before = copy.deepcopy(actual)
    monkeypatch.setattr(
        egress, "compose_prefix", lambda s, d, overlay=True: ["overlay" if overlay else "plain"]
    )

    def capture(args, **kwargs):
        assert b"ASM_TELEGRAM_ENABLED=false\n" in runtime.read_bytes()
        assert private.read_bytes() == staged
        calls.append(args)
        if "stop" in args:
            actual.pop("telegram-egress")
        return b""

    def snap(s, d, disabled=True):
        snapshots.append(disabled)
        return copy.deepcopy(actual)

    monkeypatch.setattr(egress, "command", capture)
    monkeypatch.setattr(egress, "snapshot", snap)
    egress.rollback(state, directory)
    assert snapshots == [False, True, True, True]
    assert [c[0] for c in calls] == ["overlay", "plain", "overlay"]
    assert calls[-1][-2:] == ["stop", "telegram-egress"]
    assert not any(v in {"down", "-v", "reset", "drop"} for c in calls for v in c)
    assert runtime.read_bytes() == raw.replace(
        b"ASM_TELEGRAM_ENABLED=true", b"ASM_TELEGRAM_ENABLED=false"
    )
    receipt = json.loads((directory / "rollback.json").read_bytes())
    assert receipt["telegram_disabled"] is True and receipt["before"] == before
    assert (directory / "rollback-intent/runtime-before.env").read_bytes() == raw
    assert (directory / "rollback-intent/runtime-disabled.env").read_bytes() == runtime.read_bytes()
    calls.clear()
    egress.rollback(state, directory)
    assert not calls, "COMPLETED_ROLLBACK_MUST_NOT_RECREATE"


def test_docker_mount_order_is_not_drift_but_every_mount_field_remains_guarded(monkeypatch):
    state = {"project": "fixture", "image_id": "relay-image", "subnet": "10.203.0.0/28"}
    containers = []
    for name in ("api", "worker", "postgres", "storage", "telegram-egress"):
        containers.append(
            {
                "Id": name,
                "Image": "relay-image" if name == "telegram-egress" else "image",
                "Config": {
                    "Labels": {"com.docker.compose.service": name},
                    "Env": ["ASM_TELEGRAM_ENABLED=false"],
                },
                "Mounts": [],
                "NetworkSettings": {
                    "Networks": {
                        "fixture_default": {"Gateway": "172.18.0.1"},
                        "fixture_telegram-egress": {"IPAddress": "10.203.0.2"},
                    }
                },
            }
        )
    mounts = [
        dict(
            Type="volume", Name="fixture_pgdata", Source="/vol/data", Destination="/data", RW=True
        ),
        dict(
            Type="bind",
            Name=None,
            Source="/source/bootstrap.sh",
            Destination="/bootstrap.sh",
            RW=False,
        ),
    ]
    containers[2]["Mounts"] = copy.deepcopy(mounts)
    monkeypatch.setattr(
        egress,
        "checked_model",
        lambda *_: {"services": {name: {"environment": {}} for name in ("api", "worker")}},
    )
    monkeypatch.setattr(egress, "compose_prefix", lambda *_: ["compose"])
    monkeypatch.setattr(egress, "source_image_check", lambda *_: None)
    monkeypatch.setattr(egress, "database_identity", lambda *_: {"database": "same"})

    def inspect(args, **_):
        if args == ["compose", "ps", "-q"]:
            return b"api worker postgres storage telegram-egress"
        assert args[:2] == ["docker", "inspect"]
        return egress.encoded(containers)

    monkeypatch.setattr(egress, "command", inspect)
    before = egress.snapshot(state, Path("/unused"))
    containers[2]["Mounts"].reverse()
    after = egress.snapshot(state, Path("/unused"))
    assert before == after
    egress.compare_deployment(before, after, state)
    after["api"]["database_identity"] = {"database": "different"}
    with pytest.raises(egress.EgressError, match="EGRESS_CALLER_DATABASE_CHANGED"):
        egress.compare_deployment(before, after, state)
    for field, changed in {
        "Type": "bind",
        "Name": "other",
        "Source": "/other",
        "Destination": "/other",
        "RW": False,
    }.items():
        containers[2]["Mounts"] = copy.deepcopy(mounts)
        containers[2]["Mounts"][0][field] = changed
        with pytest.raises(egress.EgressError, match="EGRESS_UNRELATED_CONTAINER_CHANGED"):
            egress.compare_deployment(before, egress.snapshot(state, Path("/unused")), state)


def test_cli_never_prints_provider_exception_or_secret(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(egress.os, "getuid", lambda: 1000)
    monkeypatch.setattr(
        "sys.argv",
        [
            "prepare",
            "prepare",
            "--state-dir",
            str(tmp_path),
            "--profile",
            "/private/profile",
            "--telegram-env",
            "/private/env",
            "--accepted-sha",
            "a" * 40,
        ],
    )

    def fail(_):
        raise AttributeError("SYNTHETIC_PROVIDER_SECRET_DO_NOT_PRINT")

    monkeypatch.setattr(egress, "prepare", fail)
    with pytest.raises(SystemExit) as error:
        egress.main()
    assert error.value.code == 1
    assert capsys.readouterr().out == "EGRESS_INVALID_INPUT_OR_COMMAND\n"


def test_native_ipv6_inbound_keeps_exact_fixed_upstream_and_selected_connection():
    old = egress.minimal_config(profile(), "10.203.0.2")
    new = egress.minimal_config(profile(), "10.203.0.2", "fd42:6173:6d00::2")
    assert new["outbounds"] == old["outbounds"] and new["log"] == old["log"]
    assert new["inbounds"][0] == old["inbounds"][0]
    second = dict(old["inbounds"][0], tag="telegram-only-v6", listen="fd42:6173:6d00::2")
    assert new["inbounds"][1:] == [second]
    expected = copy.deepcopy(old["routing"])
    expected["rules"][0]["inboundTag"].append("telegram-only-v6")
    assert new["routing"] == expected
    for address in ("::1", "::ffff:10.203.0.2", "fe80::2", "2001:db8::2"):
        with pytest.raises(egress.EgressError, match="EGRESS_PRIVATE_IPV6"):
            egress.minimal_config(profile(), "10.203.0.2", address)


def test_ipv6_ipam_collision_identity_and_static_reservation():
    subnet = "fd42:6173:6d00::/64"
    assert egress.select_subnet6([], []) == subnet
    assert egress.select_subnet6([], [{"dst": subnet}]) == "fd42:6173:6d00:1::/64"
    own = {
        "Name": "fixture_telegram-egress-v6",
        "Internal": True,
        "EnableIPv6": True,
        "EnableIPv4": False,
        "Labels": {"asm.scope": "synthetic-telegram-test"},
        "IPAM": {
            "Config": [
                {
                    "Subnet": subnet,
                    "Gateway": "fd42:6173:6d00::1",
                    "IPRange": "fd42:6173:6d00:0:8000::/65",
                }
            ]
        },
    }
    assert (
        egress.select_subnet6(
            [own], [{"dst": subnet}, {"dst": "fd42:6173:6d00::1"}], subnet, own["Name"]
        )
        == subnet
    )
    for key, value in (("Internal", False), ("EnableIPv6", False), ("EnableIPv4", True)):
        changed = dict(own, **{key: value})
        with pytest.raises(egress.EgressError, match="EGRESS_IPV6_NETWORK_COLLISION"):
            egress.select_subnet6([changed], [], subnet, own["Name"])
    changed = copy.deepcopy(own)
    changed["IPAM"]["Config"][0]["IPRange"] = subnet
    with pytest.raises(egress.EgressError, match="EGRESS_IPV6_DYNAMIC_RANGE_CHANGED"):
        egress.select_subnet6([changed], [], subnet, own["Name"])
    with pytest.raises(egress.EgressError, match="EGRESS_NO_NONOVERLAPPING_IPV6_SUBNET"):
        egress.select_subnet6([], [{"dst": "fd00::/8"}], subnet)


@pytest.mark.parametrize("bad", [None, "mapped", "foreign", "empty"])
def test_all_three_callers_keep_strict_flags_zero_for_every_address(monkeypatch, bad):
    import socket

    state = {
        "version": 2,
        "subnet": "10.203.0.0/28",
        "subnet6": "fd42:6173:6d00::/64",
        "project": "fixture",
        "uid": 1000,
        "gid": 1000,
    }
    calls, families = [], []

    def resolve(host, port, family, kind, proto, flags):
        assert host == "api.telegram.org" and port == 443 and proto == flags == 0
        families.append(family)
        rows = [
            (socket.AF_INET, kind, 6, "", ("10.203.0.2", 443)),
            (socket.AF_INET6, kind, 6, "", ("fd42:6173:6d00::2", 443, 0, 0)),
        ]
        if family == socket.AF_INET6 and bad:
            if bad == "empty":
                return []
            rows[1] = (
                socket.AF_INET6,
                kind,
                6,
                "",
                ("::ffff:10.203.0.2" if bad == "mapped" else "2001:db8::91", 443, 0, 0),
            )
        return rows if family == socket.AF_UNSPEC else [r for r in rows if r[0] == family]

    def execute(args, **_):
        calls.append(args)
        if args[-1].startswith("import socket,ipaddress;"):
            exec(args[-1], {})
        return b""

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    monkeypatch.setattr(egress, "command", execute)
    if bad:
        with pytest.raises(AssertionError):
            egress.caller_probe(state, Path("/private"))
    else:
        egress.caller_probe(state, Path("/private"))
        assert families == [socket.AF_UNSPEC, socket.AF_INET, socket.AF_INET6] * 3
        assert len(calls) == 4 and "telegram-operator" in calls[2]


def test_immutable_bundle_atomic_publish_and_private_operation_lock(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    target = tmp_path / "generation"
    rename = egress.os.rename
    monkeypatch.setattr(egress.os, "rename", lambda *_: (_ for _ in ()).throw(OSError("crash")))
    with pytest.raises(OSError):
        egress.atomic_bundle(target, {"state.json": b"{}\n"})
    assert not target.exists()
    monkeypatch.setattr(egress.os, "rename", rename)
    egress.atomic_bundle(target, {"state.json": b"{}\n"})
    egress.atomic_bundle(target, {"state.json": b"{}\n"})
    with pytest.raises(egress.EgressError, match="EGRESS_BUNDLE_CHANGED"):
        egress.atomic_bundle(target, {"state.json": b"changed"})
    with egress.operation_lock(tmp_path):
        with pytest.raises(egress.EgressError, match="EGRESS_OPERATION_BUSY"):
            with egress.operation_lock(tmp_path):
                raise AssertionError("concurrent mutation accepted")


def partial_state(tmp_path, monkeypatch):
    root, directory = tmp_path / "checkout", tmp_path / "state"
    root.mkdir(mode=0o700)
    directory.mkdir(mode=0o700)
    monkeypatch.setattr(egress, "ROOT", root)
    egress.write_private(root / ".env", b"PG_RUNTIME_PASSWORD=synthetic\n")
    egress.write_private(tmp_path / "telegram.env", b"TG_BOT_TOKEN=staged\n")
    raw = egress.encoded(profile())
    egress.write_private(tmp_path / "profile.json", raw)
    runtime = egress.encoded(
        {
            "services": {
                n: {
                    "environment": {
                        "ASM_AUTH_ORIGINS": '["https://console.test"]',
                        "ASM_STORAGE_ENDPOINT": "https://files.test",
                    }
                }
                for n in ("api", "worker")
            }
        }
    )
    old = {
        "version": 1,
        "source_sha": egress.LEGACY_SHA,
        "project": "fixture",
        "subnet": "10.203.0.0/28",
        "uid": os.getuid(),
        "gid": os.getgid(),
        "profile": str(tmp_path / "profile.json"),
        "profile_sha256": egress.sha(raw),
        "telegram_env": str(tmp_path / "telegram.env"),
        "image": egress.IMAGE,
        "image_id": "relay-image",
        "runtime_sha256": egress.sha(runtime),
    }
    config = egress.encoded(egress.minimal_config(profile(), "10.203.0.2"))
    old["config_sha256"] = egress.sha(config)
    before = {
        n: {
            "id": n + "-original",
            "image": "app-image",
            "mounts": [],
            "environment_sha256": "env",
            "process_sha256": "process",
            "database_identity": {"database": "same"},
            "networks": {"fixture_default": {"IPAddress": "172.18.0.2", "Gateway": "172.18.0.1"}},
        }
        for n in ("api", "worker", "postgres", "storage")
    }
    for name, data in {
        "state.json": egress.encoded(old),
        "config.json": config,
        "runtime.json": runtime,
        "route.env": egress.route_env(egress.route_values(old, directory)),
        "deployment-before.json": egress.encoded(before),
    }.items():
        egress.write_private(directory / name, data)
    actual = copy.deepcopy(before)
    for n in ("api", "worker"):
        actual[n]["id"] = n + "-partial"
    actual["telegram-egress"] = {
        "id": "relay-partial",
        "image": "relay-image",
        "networks": {"fixture_telegram-egress": {"IPAddress": "10.203.0.2"}},
    }
    ups = []
    owned_relay = copy.deepcopy(actual["telegram-egress"])

    def command(args, **_):
        if args[:3] == ["docker", "image", "inspect"]:
            return egress.encoded([{"Id": "app-image"}])
        if "up" in args:
            ups.append(args)
            if args[-1] == "telegram-egress":
                actual["telegram-egress"] = copy.deepcopy(owned_relay)
                actual["telegram-egress"]["networks"]["fixture_telegram-egress-v6"] = {
                    "GlobalIPv6Address": "fd42:6173:6d00::2"
                }
            else:
                for n in ("api", "worker"):
                    actual[n]["id"] = n + "-recreated-" + str(len(ups))
        if "stop" in args:
            actual.pop("telegram-egress", None)
        return b"[]"

    def relay(states, directory, *, missing=False):
        if "telegram-egress" in actual:
            egress.require(
                actual["telegram-egress"]["image"] == "relay-image",
                "EGRESS_RELAY_TRANSITION_IDENTITY",
            )
            return {
                "status": "running",
                "id": "relay-partial",
                "image": "relay-image",
                "config_sha256": states[-1]["config_sha256"],
            }
        return {
            "status": "stopped",
            "id": "relay-partial",
            "image": "relay-image",
            "config_sha256": states[-1]["config_sha256"],
        }

    def source(expected):
        egress.require(expected == "a" * 40, "EGRESS_CHECKOUT_MISMATCH")

    monkeypatch.setattr(egress, "source_check", source)
    monkeypatch.setattr(egress, "source_image_check", lambda *_: None)
    monkeypatch.setattr(egress, "image_check", lambda *_: "relay-image")
    monkeypatch.setattr(egress, "runtime_overlay", lambda *_: runtime)
    monkeypatch.setattr(egress, "command", command)
    monkeypatch.setattr(egress, "snapshot", lambda *_, **__: copy.deepcopy(actual))
    monkeypatch.setattr(egress, "transition_relay", relay)
    monkeypatch.setattr(egress, "caller_probe", lambda *_: None)
    monkeypatch.setattr(
        egress,
        "checked_model",
        lambda *_: {
            "services": {
                n: {"image": "app-image", "environment": {"ASM_TELEGRAM_ENABLED": "false"}}
                for n in egress.CALLERS
            }
        },
    )
    args = argparse.Namespace(
        state_dir=str(directory), from_sha=egress.LEGACY_SHA, accepted_sha="a" * 40
    )
    return args, directory, actual, ups


@pytest.mark.parametrize(
    "phase", ["audit", "generation", "manifest", "relay", "callers", "probe", "after"]
)
def test_partial_recovery_interruptions_resume_without_rebaseline_or_false_success(
    tmp_path, monkeypatch, phase
):
    args, directory, _, ups = partial_state(tmp_path, monkeypatch)
    original = {
        name: (directory / name).read_bytes()
        for name in (
            "state.json",
            "config.json",
            "route.env",
            "runtime.json",
            "deployment-before.json",
        )
    }
    write, bundle, command = egress.write_private, egress.atomic_bundle, egress.command
    tripped = False

    def crash():
        nonlocal tripped
        if not tripped:
            tripped = True
            raise OSError("synthetic interruption")

    def publish(path, files):
        bundle(path, files)
        if (phase, path.name) in {("audit", "recovery-v1"), ("generation", "recovery-v2")}:
            crash()

    def save(path, data, **kwargs):
        write(path, data, **kwargs)
        if path == directory / (
            "state.json"
            if phase == "manifest"
            else "deployment-after.json"
            if phase == "after"
            else "unused"
        ):
            crash()

    def execute(command_args, **kwargs):
        value = command(command_args, **kwargs)
        if "up" in command_args and (
            (phase == "relay" and command_args[-1] == "telegram-egress")
            or (phase == "callers" and command_args[-1] == "worker")
        ):
            crash()
        return value

    monkeypatch.setattr(egress, "atomic_bundle", publish)
    monkeypatch.setattr(egress, "write_private", save)
    monkeypatch.setattr(egress, "command", execute)
    monkeypatch.setattr(egress, "caller_probe", lambda *_: crash() if phase == "probe" else None)
    with pytest.raises(OSError, match="synthetic interruption"):
        egress.recover(args)
    assert tripped and not (directory / "recovery.json").exists()
    assert (directory / "deployment-after.json").exists() == (phase == "after")
    egress.recover(args)
    for name, raw in original.items():
        assert (directory / "recovery-v1" / name).read_bytes() == raw
        if name != "state.json":
            assert (directory / name).read_bytes() == raw
    state = json.loads((directory / "state.json").read_bytes())
    assert state["version"] == 2 and state["source_sha"] == args.accepted_sha
    assert state["legacy_state_sha256"] == egress.sha(original["state.json"])
    receipt = json.loads((directory / "recovery.json").read_bytes())
    assert receipt["original_before_sha256"] == egress.sha(original["deployment-before.json"])
    previous_ups = len(ups)
    egress.recover(args)  # Completed response retry has no recreate or changed receipt.
    assert len(ups) == previous_ups
    with pytest.raises(egress.EgressError, match="EGRESS_BASELINE_EXISTS_USE_RECOVERY"):
        egress.deploy(state, directory)


@pytest.mark.parametrize(
    "drift", ["unknown_source", "before", "staged", "database", "image", "gateway"]
)
def test_partial_recovery_drift_stops_before_runtime_mutation(tmp_path, monkeypatch, drift):
    args, directory, actual, ups = partial_state(tmp_path, monkeypatch)
    original = (directory / "deployment-before.json").read_bytes()
    if drift in {"before", "staged"}:
        egress.recovery_archive(directory, args.accepted_sha)
        path = (
            directory / "deployment-before.json" if drift == "before" else tmp_path / "telegram.env"
        )
        egress.write_private(path, path.read_bytes() + b"\n")
    elif drift == "unknown_source":
        state = json.loads((directory / "state.json").read_bytes())
        state["source_sha"] = "b" * 40
        egress.write_private(directory / "state.json", egress.encoded(state))
    elif drift == "database":
        actual["api"]["database_identity"] = {"database": "other"}
    elif drift == "image":
        actual["worker"]["image"] = "other-image"
    else:
        actual["api"]["networks"]["fixture_default"]["Gateway"] = "172.18.0.99"
    with pytest.raises(egress.EgressError):
        egress.recover(args)
    assert not ups and not (directory / "deployment-after.json").exists()
    assert json.loads((directory / "state.json").read_bytes())["version"] == 1
    assert (directory / "deployment-before.json").read_bytes() == original + (
        b"\n" if drift == "before" else b""
    )


@pytest.mark.parametrize("phase", ["env", "callers", "remove", "stop", "receipt"])
def test_legacy_rollback_exact_disable_delta_resumes_each_interruption(
    tmp_path, monkeypatch, phase
):
    args, directory, actual, ups = partial_state(tmp_path, monkeypatch)
    old, _, _ = egress.attest_partial_recovery(args, rolling_back=True)
    original_before = (directory / "deployment-before.json").read_bytes()
    original_env = (egress.ROOT / ".env").read_bytes()
    staged = Path(old["telegram_env"]).read_bytes()
    audit = {p.name: p.read_bytes() for p in (directory / "recovery-v1").iterdir()}
    save, execute = egress.write_private, egress.command
    tripped = False

    def crash():
        nonlocal tripped
        if not tripped:
            tripped = True
            raise OSError("interrupted rollback")

    def write(path, raw, **kwargs):
        if phase == "receipt" and path == directory / "rollback.json":
            crash()
        save(path, raw, **kwargs)
        if phase == "env" and path == egress.ROOT / ".env":
            crash()

    def command(argv, **kwargs):
        result = execute(argv, **kwargs)
        if (
            phase == "callers"
            and "up" in argv
            and len(ups) == 1
            or phase == "remove"
            and "up" in argv
            and len(ups) == 2
            or phase == "stop"
            and "stop" in argv
        ):
            crash()
        return result

    monkeypatch.setattr(egress, "write_private", write)
    monkeypatch.setattr(egress, "command", command)
    with pytest.raises(OSError, match="interrupted rollback"):
        egress.rollback(old, directory)
    assert tripped and not (directory / "rollback.json").exists()
    resumed, _, _ = egress.attest_partial_recovery(args, rolling_back=True)
    egress.rollback(resumed, directory)
    assert (egress.ROOT / ".env").read_bytes() == original_env + b"ASM_TELEGRAM_ENABLED=false\n"
    assert Path(old["telegram_env"]).read_bytes() == staged
    assert (directory / "deployment-before.json").read_bytes() == original_before
    assert {p.name: p.read_bytes() for p in (directory / "recovery-v1").iterdir()} == audit
    receipt = (directory / "rollback.json").read_bytes()
    previous = copy.deepcopy(actual)
    previous_ups = len(ups)
    resumed, _, _ = egress.attest_partial_recovery(args, rolling_back=True)
    egress.rollback(resumed, directory)
    assert len(ups) == previous_ups and actual == previous
    assert (directory / "rollback.json").read_bytes() == receipt
    with pytest.raises(egress.EgressError, match="EGRESS_RECOVERY_ALREADY_ROLLED_BACK"):
        egress.recover(args)


@pytest.mark.parametrize(
    "drift",
    [
        "runtime",
        "staged",
        "profile",
        "baseline",
        "intent",
        "database",
        "image",
        "gateway",
        "unrelated",
    ],
)
def test_legacy_rollback_retry_keeps_all_other_drift_guards(tmp_path, monkeypatch, drift):
    args, directory, actual, ups = partial_state(tmp_path, monkeypatch)
    old, _, _ = egress.attest_partial_recovery(args, rolling_back=True)
    execute = egress.command
    monkeypatch.setattr(
        egress,
        "command",
        lambda argv, **kw: (
            (_ for _ in ()).throw(OSError("interrupted")) if "up" in argv else execute(argv, **kw)
        ),
    )
    with pytest.raises(OSError):
        egress.rollback(old, directory)
    monkeypatch.setattr(egress, "command", execute)
    paths = {
        "runtime": egress.ROOT / ".env",
        "staged": Path(old["telegram_env"]),
        "profile": Path(old["profile"]),
        "baseline": directory / "deployment-before.json",
        "intent": directory / "rollback-intent/runtime-disabled.env",
    }
    if drift in paths:
        path = paths[drift]
        egress.write_private(path, path.read_bytes() + b"\n")
    elif drift == "database":
        actual["api"]["database_identity"] = {"database": "foreign"}
    elif drift == "image":
        actual["worker"]["image"] = "foreign"
    elif drift == "gateway":
        actual["api"]["networks"]["fixture_default"]["Gateway"] = "172.18.0.99"
    else:
        actual["storage"]["id"] = "foreign"
    previous = len(ups)
    with pytest.raises(egress.EgressError):
        resumed, _, _ = egress.attest_partial_recovery(args, rolling_back=True)
        egress.rollback(resumed, directory)
    assert len(ups) == previous and not (directory / "rollback.json").exists()


@pytest.mark.parametrize("relay_status", ["stopped", "missing"])
def test_recovery_resumes_relay_recreate_gap_only_with_exact_intent(
    tmp_path, monkeypatch, relay_status
):
    args, directory, actual, ups = partial_state(tmp_path, monkeypatch)
    original = (directory / "deployment-before.json").read_bytes()
    execute, relay = egress.command, egress.transition_relay
    tripped = False

    def command(argv, **kwargs):
        nonlocal tripped
        if "up" in argv and argv[-1] == "telegram-egress" and not tripped:
            actual.pop("telegram-egress")
            tripped = True
            raise OSError("recreate gap")
        return execute(argv, **kwargs)

    def inspect(states, path, *, missing=False):
        if tripped and "telegram-egress" not in actual and relay_status == "missing":
            egress.require(missing, "EGRESS_RELAY_MISSING_WITHOUT_INTENT")
            return {"status": "missing"}
        return relay(states, path, missing=missing)

    monkeypatch.setattr(egress, "command", command)
    monkeypatch.setattr(egress, "transition_relay", inspect)
    with pytest.raises(OSError, match="recreate gap"):
        egress.recover(args)
    assert not (directory / "deployment-after.json").exists()
    intent = directory / "recovery-recreate.json"
    raw = intent.read_bytes()
    egress.write_private(intent, raw + b"\n")
    with pytest.raises(egress.EgressError, match="EGRESS_RECOVERY_RECREATE_CHANGED"):
        egress.recover(args)
    assert not ups
    egress.write_private(intent, raw)
    egress.recover(args)
    assert (directory / "deployment-before.json").read_bytes() == original
    assert (directory / "recovery-v1/deployment-before.json").read_bytes() == original
    assert (directory / "recovery.json").exists()


@pytest.mark.parametrize(
    "drift",
    [
        None,
        "stopped",
        "missing",
        "foreign_image",
        "foreign_tag",
        "foreign_config",
        "config_bytes",
        "entrypoint",
        "project",
        "privileged",
        "network",
        "address",
        "duplicate",
        "status",
    ],
)
def test_transition_relay_attests_stopped_container_and_rejects_foreign_identity(
    tmp_path, monkeypatch, drift
):
    args, directory, _, _ = partial_state(tmp_path, monkeypatch)
    state = json.loads((directory / "state.json").read_bytes())
    # Real guard: partial_state substitutes only orchestration's Docker boundary.
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "relay_guard", Path(__file__).resolve().parents[1] / "scripts/prepare_telegram_egress.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    info = {
        "Id": "owned",
        "Image": state["image_id"],
        "Config": {
            "Image": egress.IMAGE,
            "User": f"{state['uid']}:{state['gid']}",
            "Cmd": ["run", "-config", "/run/telegram-egress/config.json"],
            "Entrypoint": ["xray"],
            "Labels": {
                "com.docker.compose.project": "fixture",
                "com.docker.compose.service": "telegram-egress",
                "com.docker.compose.oneoff": "False",
            },
        },
        "HostConfig": {
            "ReadonlyRootfs": True,
            "Privileged": False,
            "PortBindings": {},
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges:true"],
            "NetworkMode": "fixture_telegram-egress",
            "LogConfig": {"Type": "none"},
        },
        "Mounts": [
            {
                "Type": "bind",
                "RW": False,
                "Source": str(directory / "config.json"),
                "Destination": "/run/telegram-egress/config.json",
            }
        ],
        "NetworkSettings": {
            "Networks": {"fixture_telegram-egress": {"IPAMConfig": {"IPv4Address": "10.203.0.2"}}}
        },
        "State": {"Status": "exited" if drift == "stopped" else "running", "Dead": False},
    }
    if drift == "foreign_image":
        info["Image"] = "foreign"
    elif drift == "foreign_tag":
        info["Config"]["Image"] = "foreign:latest"
    elif drift == "foreign_config":
        info["Mounts"][0]["Source"] = str(directory / "foreign.json")
    elif drift == "config_bytes":
        (directory / "config.json").write_bytes(b"{}")
    elif drift == "entrypoint":
        info["Config"]["Entrypoint"] = ["sh"]
    elif drift == "project":
        info["Config"]["Labels"]["com.docker.compose.project"] = "foreign"
    elif drift == "privileged":
        info["HostConfig"]["Privileged"] = True
    elif drift == "network":
        info["NetworkSettings"]["Networks"]["foreign"] = {}
    elif drift == "address":
        info["NetworkSettings"]["Networks"]["fixture_telegram-egress"]["IPAMConfig"][
            "IPv4Address"
        ] = "10.203.0.3"
    elif drift == "status":
        info["State"]["Status"] = "dead"

    def command(argv, **_):
        if argv[:3] == ["docker", "ps", "-aq"]:
            return (
                b"" if drift == "missing" else b"owned\nother" if drift == "duplicate" else b"owned"
            )
        if argv[:3] == ["docker", "image", "inspect"]:
            return egress.encoded([{"Config": {"Entrypoint": ["xray"]}}])
        return egress.encoded([info])

    monkeypatch.setattr(module, "command", command)
    if drift in {None, "stopped"}:
        assert module.transition_relay([state], directory)["status"] == (
            "stopped" if drift else "running"
        )
    else:
        with pytest.raises(module.EgressError):
            module.transition_relay([state], directory)
        if drift == "missing":
            assert module.transition_relay([state], directory, missing=True) == {
                "status": "missing"
            }


# Exact failed-candidate client fixture: c009c8540146d0a16d44fccf662d6e4d50fc53b1,
# blob abe2cfc61297397ffc313d287364741403ccf5bf. Compressed only to keep this
# historical source fixture bounded; decode/hash validation precedes every use.
# No Git/network access is available inside the ordinary checks image.
_R1_CLIENT = (
    b"eNrlG11z2zbyXb8CYR+ObGnaTpPeVVd1znGU1lNH8dhyP87j4cAkZLGhSB1B2VFy/u+3C4AkQIKy7Lh5OWfGloDFYrHf2EUc"
    b"x3mVr7KYxSSfzZIooSl5lZfk4OSIRGnCsvKfJMtJwcoiYdyHD3FSsKiEj3lBIpqmrNjJbzNcXyTXSRY4jjMYJItlXpSE8nUW"
    b"JXn1Nc2vAeK6+lqwwazIFyTKAUtUJnnGA3oVETV9gIuPSlbQMi8kZExLGqWUc8YrqHpIQpTrJexQo8jWcnhVpGlyFSxpwVk1"
    b"CWN8mSZlTe28LJcfBnIB5YtglqSMB4s8Zmm93RtWRvMTVixgXQ24YJxTPFnAiiIvauBDWOqTt9XsGCdtq8wt3q3KKF+wX5Is"
    b"9skZy2I14JMkBnkks4RZsRSMr9KyRoMr24SWLGXXBV0EUZ7NkppNUzV8xsoSMHHLgiwvFjRNPlIUU7UOsGRScCEQlcagFNlq"
    b"wYokChOgPb/6E2bDG5qugHgOGgTf/uR5NhgMhMjqjQVn3PGHiC0RmzccEPiJ2YyEYZIlZRi6nKUzH3aM2VDx9WsfIXCapetw"
    b"lXFgzpBc5XlKRuQNTTnzyM6PZJJnTOLDH75assL1ghovYgwEiV4DBHsFOAGI8I850dkUoDpjcMR/1arpAj8/smw0LQQj0rzk"
    b"4rOn2PBqxZMM5HhY81MSzD6A9mc0DTVGJ/EQWSnm0e6KcMXhlz6c8JBl9CplsWSHGIxoFhZsma61MSCQyWU1v/MrwHYjpKxY"
    b"fpWXFXbBzxikeAFfKvleNswFL7EqMvKpHsAfRyJAzS3XzlDh800Y+0kBWnDcPttCYTCjWmkMthY0bKqgm5EWaM28CrIeaJ8D"
    b"FTlEnQFI1Lxm/g5UAjkMGrgEU+VhWdCMox2F4Be521LWr2o3vFyBUZdzBjtHwGGSZOLb+elxQF4nHOklV2yWFwwNEiSzitCK"
    b"CVUO3Ff4kixKVzHOsA8JFyDRPElj4ZZZwQPyZgXyY3K0YGDm2RyMGdw44eAKQdHBf8KfQCCEDUlGFwzpcR3hOx2fiA8R0AKf"
    b"vy5Xy5S5yusHx2KbYEEzin/lrq9BmzyvUaFkJpGORkThJNU+1ZDAXo0GvKRFyW+Tcu4qKgKdjMDRseOP3BdstqLrmpWSNBcR"
    b"ehbgIJZsjmEV2q0NZFnkS3oNBlU5HxsQh63YDUtrnhyeHk2PDg+OyTdk39wZGZGX1cI5zWKItNw8ioaZxvHPEqbGPVmlaTXm"
    b"eR2feyiUw+JpDW/na99kcBh2wkUD83XzsdbuoYyrgQjnryhn02qG/FfoOzDMtJSS8TKU2YRwOzY4i2tXHKvoDCofaLCsoAlk"
    b"AGbcwXASTN5Nw4Pj43e/jV83gpBEEKV4fLi7S5dJExTz4trRt6/PDC5Y0CLIBk3VTqRPDdsS12i/SYo8W6DRPYPtp+OzqdMV"
    b"/sNOgxRuQ4jIklDXqwzJ1ZZ1tNTtUCXXBzyaMzDbZ4p7TgcOGKNA5zkvhY0jQUDaJ2f/+d+DPfi3j8ac5pBoIgx+GQ73nbsN"
    b"uJa0nG+Y/s+KFesN87OCXiPbN4BgOEFqNxLB+W1exAaI9wABHk1+PTg+eh0eTU7OpybPa6XUpKLnN/boYuYwlaIBluqjCRDW"
    b"u7Q3ELMoUJjTLFu6E1MZahpG9afWSXQMP0+nJ7Vv6GqVuoKM9vyuD0wgy+UjietYfHEX9IOWLvDRC5/g0HvGlpDH3jBz0usi"
    b"hTgK7AVDHAl3bgK04G8gTM7WMr8bbI1kBvee/Dasr1Q2mCc/WpksWL4qFcap/OaqFaOXPllCdjh6jjc9GuP3W8gA2OhlC80c"
    b"ZiEejT45BxFm7TvjDLIe0CPIe5w627trFnlNjhmCX1HJ5YKV81wmlyKhxyuXJYeH6U6WaWqIrrTGxDeQnOwi2l1IPB10WPiF"
    b"wH2LEUeMeS14w0CCMn/PMswRQpl+yeuM217k7DqtEXm09vnFjVhyoWDgi3jZircmS5Z0neYUvnWybsGuq1UMlA3JDIDwGvKy"
    b"iY0i97pIIP3T1sJ9+FLL18tibbokSR0mUxa3ri7zgdIgV25usZzGRUB2Bmq0cJ2TdxC/fDWD4pen9HyC98GROqYHe4B4wQFk"
    b"HYPr+k4QZQUbKHVEObkOKHMJCrjDKpX0NZX0IPG8xYxIBKbmXtJB/1j3jD9XebwGcVytS0aLgq5dz85NkURH81X2HqNefRoK"
    b"FleEuJq7YjbkyUc2+u7ly2+/8+yU4o7inpTFcolnBQOeQSLvIrRHfiQCox3h5xxfWWh9HsjRyxUX1yKjDuDKIwpqfElMg4yJ"
    b"agBxpaNSV2NBg0+MMeXDqtETcB5qyNsy93s9PhlPXo8nh3+E55ODXw+Ojg9eHY8t5QV5ayeiPIJ5U4dYtbFBZjXWqm48hKrp"
    b"0dvxO+B0/85yKwyhAsNnHXzDNmYta8tdTG3RkHc9Io3zLF27D/KEwt2BZ9OKPELf/FoBwRTpLRiV8j+V45X4a9RGoixR4J3z"
    b"+d4egVtUo83Cx+TvHQ8zaFQIMe3I8pujG3KLP6ZVXFQrLge92bR9z+71Egko10vmmgu0aoQnViatvFY/14UOfoknlzzoLFCs"
    b"wTT9xd6eT17s7eOvb/HXiyYz9z7n4vVQjW2rEsbrBRN61E0gOmFPCgJzXa1i6ZoqozTTAcxvsbjx6c4zHR+kEoChqX+6EquU"
    b"RBI7XufmZADwUOQi1a1M6BUEB8T6bNTKSVRJ7jOvg5pOAsIvaukonlt2Nc/z92GSzfJGUBuri0pKvYL5TaI8AoxSQv2WJS6a"
    b"PMlAmbOIKVnJVKl927LDSrFBKuN4IqZ1VlX2WMMuITYDP8PVEuuuYGerrFR2Ka+9ncuRXH1hX3lJfiB7D7a2nsj9FREwRHYT"
    b"GN89Pz0WJr4s8htIkgrgDL3O4AqeRJzQQt7UpfYw8D15XU3rFIMFj4b1WfAbJK/2Mw3vOfKdTZEkCG90KE14edGb9G5WI7Oc"
    b"C+jPJXbHTEc/dWzPETc1OMH+nuWG6qikGeZtsxQvgiyujgJQF9akzLlSnQLtiuf494AqmfbBwe2zhK23BY9Bp2zw3LLg0hwy"
    b"boO9lqnZTW0bKNG2cWAeW4H9iFxvA9Bs7QpkcL5FjQr1QqTdOKqCNeJ4KktqojxgtamrRYQq36nbHHq7pa83ZA1kTYPQ1ZCZ"
    b"rkl26kRnq9W9s1z57jUR3VS6pKIXtums7NBoJHYLeibRndgpKb7oaxxdYtDU+fl0sbJ7yi5H7qPO711hdrE2AGrdqw1QTeNq"
    b"A1CazFi0jlIWovdpQ3pfNDOQ/UfW7T12zcNX/c8tm5NdY5kp/H9lgtUI3ow4fZ6g12yB2gbM7Gsi/TUrnk7R9e20rrDkTUcr"
    b"jA2wjsMs2mHrD9t6xGY/6P4ucQ98uyXcA2Y0gntg9A5wH3V671d8CZrHBa1I2FZ73iTETR5jdmYekrfwOhe+P2+R6Zmp/1Vu"
    b"DnOWg6pCqKiM9i6VQJbC6f9t+iPWt2r3mC9aoOIiX4ZmCoyglv5AX06ltEW7TT4urenoaRYr37wUb4uG2jsjobTagyWjNSvB"
    b"g/o+Ibuax+OfTg/eim6+AtA9wXaOWXkVbWNXe0Il3NzZeDINT8anbw8m8MknjamO+l1hJ2BsWVayGUwWv+3Vq09b67r0YopR"
    b"2zyKadzXnJbGajXQA14C8gYWv3UB77pDsiMw2t/zNydvDymuWQKatVpjYlClNa9bm8aDW9bWt3Sct61Tdo7htrfK08DYMFh7"
    b"5c2BJIoeqXvIrI2Ct2JG1mq04tm0epSGU6lDL5JmJd6oJDnOskhuMGHs5u493ZTNhnp2fng4PjvzNVZv8dhg2xLp55RJH1Uq"
    b"rRaZlSNt25jxqEhES8BaQ7K3vPqqr3eP4vmjnaPVml88/95OxZJCkME7p8kBMQzhtOCOvV0F0ZZiI02ur0wbHHNIZ7AMZT3T"
    b"GSzhVBlP9niNLkaLcqELYo9K7EJi++SHkdoaPvzjO+Dzhh5Zl8G9sPhj5f7peHr6h+g5bVzblkxP32ojDo19mJjlWcxH4qz9"
    b"y7wvqlkPuE+ACGWe3X0HPHgsuY0odHKbdP5B12F8BjTYkoLzyS+Td79NulxSE+H49+n4dHJwDCSenR93c7McEsYwWYDnbGVo"
    b"2pt12SvTH9ZfiB7s5ZfK1UTaabJsYzlty17NdpUrLFK9SVLRvnHwGYiREgnWhWr4blP9CZ+YSWdWx22xDMed7WKWuVBE+Gcj"
    b"KyW2V2atjgTuawkgWqEUIWSZ9PkLG0zBgtkqTRcUNMUtnIuDnX/TnY97O9+Hwe7O5TeOTyQG8JJWh6rKrZyJt3PyCR8+uxBv"
    b"cYPAuRMlV20a0QXycaGz286Wnuih3INeszzf2+4ly09j8yGL5D3KSj4OePwbFu2VBOrC876oY2NFr+/u8qgXtI+WH8jLVnHd"
    b"iEkYZDdEo8F2EeULPOb5ipwydBnVY3l8LPH73zj4Tjwm/memjGAlIsJH3BRfv89S+BjLtzVP+j7oiR//rLGQK1E9Joyq/+nS"
    b"JbwJsBJEwWhhW4q/gbnf2YsY+le8oLEFlad+QnPPHj1vaFpxmkZpzllfmU8PXMLxKHBv8D9zbxDi"
)
