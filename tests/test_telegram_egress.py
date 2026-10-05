"""E01/E02/E05 config and operator guards; real boundary is a mandatory Docker lane."""

import copy
import json
import os
from pathlib import Path
from uuid import UUID

import pytest

from scripts import prepare_telegram_egress as egress


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
    private = tmp_path / "telegram.env"
    raw = (
        b"TG_BOT_TOKEN='synthetic-do-not-print'\nASM_TELEGRAM_ENABLED=true\nKEEP_DATE=2030-01-01\n"
    )
    egress.write_private(private, raw)
    state = {"project": "fixture", "telegram_env": str(private)}
    before = {
        n: {
            "id": n,
            "image": "unchanged",
            "environment_sha256": "unchanged-environment",
            "process_sha256": "unchanged-process",
            "mounts": ["persistent"],
            "networks": {"fixture_default": {}},
        }
        for n in ("api", "worker", "postgres", "storage")
    }
    calls, snapshots = [], []
    monkeypatch.setattr(
        egress, "compose_prefix", lambda s, d, overlay=True: ["overlay" if overlay else "plain"]
    )

    def capture(args, **kwargs):
        assert b"ASM_TELEGRAM_ENABLED=false\n" in private.read_bytes()
        calls.append(args)
        return b""

    def snap(s, d, disabled=True):
        snapshots.append(disabled)
        return copy.deepcopy(before)

    monkeypatch.setattr(egress, "command", capture)
    monkeypatch.setattr(egress, "snapshot", snap)
    egress.rollback(state, tmp_path)
    assert snapshots == [False, True, True]
    assert [c[0] for c in calls] == ["overlay", "plain", "overlay"]
    assert calls[-1][-2:] == ["stop", "telegram-egress"]
    assert not any(v in {"down", "-v", "reset", "drop"} for c in calls for v in c)
    assert private.read_bytes() == raw.replace(
        b"ASM_TELEGRAM_ENABLED=true", b"ASM_TELEGRAM_ENABLED=false"
    )
    assert json.loads((tmp_path / "rollback.json").read_bytes())["telegram_disabled"] is True


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
