import contextlib
import copy
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from scripts import prepare_telegram_egress as private
from scripts import telegram_polling_recovery as recovery

TG_FIELDS = (
    "ASM_TELEGRAM_ENABLED",
    "TG_BOT_TOKEN",
    "TG_WEBHOOK_SECRET",
    "ASM_TELEGRAM_EXPECTED_BOT_ID",
    "ASM_TELEGRAM_WEBHOOK_URL",
)
SECRET = "SYNTHETIC_PRIVATE_SENTINEL"
IMAGE = "sha256:" + "1" * 64


def context(root):
    return SimpleNamespace(
        directory=root / "polling",
        activation_sha="a" * 64,
        intent={"operator_image": IMAGE},
        act=SimpleNamespace(TG_FIELDS=TG_FIELDS),
        helper=private,
        prefix=["docker", "compose", "-p", recovery.PROJECT],
        values=dict(
            zip(
                TG_FIELDS,
                (
                    "true",
                    "123:" + SECRET,
                    SECRET,
                    "123",
                    "https://example.invalid/webhooks/telegram",
                ),
            )
        ),
        operator={"extra_hosts": ["api.telegram.org=10.2.0.2", "api.telegram.org=fd00::2"]},
        base={
            "networks": {
                name: {"name": "existing-" + name}
                for name in ("default", "telegram-egress", "telegram-egress-v6")
            }
        },
    )


def inspected(c):
    model = recovery.desired_model(c, c.receiver_sha)
    service = model["services"]["receiver"]
    return {
        "Id": "owned-receiver",
        "Image": IMAGE,
        "State": {"Running": True},
        "Config": {
            "Labels": {**service["labels"], "com.docker.compose.service": "receiver"},
            "Env": [key + "=" + value for key, value in service["environment"].items()],
            "Entrypoint": service["entrypoint"],
            "Cmd": [],
        },
        "Mounts": [
            {
                "Type": "bind",
                "Source": str(c.directory / "receiver.py"),
                "Destination": recovery.RECEIVER_TARGET,
                "RW": False,
            }
        ],
        "HostConfig": {
            "ReadonlyRootfs": True,
            "Privileged": False,
            "PortBindings": {},
            "CapDrop": ["ALL"],
            "RestartPolicy": {"Name": "unless-stopped"},
        },
        "NetworkSettings": {
            "Networks": {value["name"]: {} for value in model["networks"].values()}
        },
    }


class PrivateDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.c = context(Path(self.temp.name))

    def resolved(self, c, args, **kwargs):
        self.assertEqual(args[-3:], ["config", "--format", "json"])
        return (c.directory / "compose.json").read_bytes().replace(b"$$", b"$")

    def prepare(self):
        with mock.patch.object(recovery, "command", self.resolved):
            return recovery.prepare(self.c, write=True)

    def test_uses_existing_image_networks_only_and_no_privileged_credentials(self):
        self.c.values.update(
            ASM_DATABASE_URL="runtime",
            ASM_MIGRATION_DATABASE_URL="migrator",
            STORAGE_SECRET_KEY="storage",
        )
        model = self.prepare()
        service = model["services"]["receiver"]
        self.assertEqual(set(model["services"]), {"receiver"})
        self.assertEqual(set(service["environment"]), {*TG_FIELDS, "ASM_ENVIRONMENT"})
        self.assertTrue(all(value["external"] for value in model["networks"].values()))
        self.assertEqual(service["image"], IMAGE)
        self.assertNotIn("ports", service)
        self.assertEqual(service["restart"], "unless-stopped")
        self.assertEqual(service["networks"]["default"], {"gw_priority": 1})
        self.assertEqual(self.c.directory.stat().st_mode & 0o777, 0o700)
        self.assertTrue(
            all(path.stat().st_mode & 0o777 == 0o600 for path in self.c.directory.iterdir())
        )

    def test_rerun_preserves_files_and_refuses_input_drift(self):
        self.prepare()
        original = {path.name: path.read_bytes() for path in self.c.directory.iterdir()}
        self.prepare()
        self.assertEqual(
            {path.name: path.read_bytes() for path in self.c.directory.iterdir()}, original
        )
        self.c.values["TG_WEBHOOK_SECRET"] = "changed"
        with self.assertRaisesRegex(RuntimeError, "POLLING_PRIVATE_FILE_CHANGED"):
            self.prepare()
        self.assertEqual(
            {path.name: path.read_bytes() for path in self.c.directory.iterdir()}, original
        )

    def test_unknown_file_or_symlink_is_not_adopted(self):
        self.prepare()
        unknown = self.c.directory / "unowned"
        unknown.touch()
        with self.assertRaisesRegex(RuntimeError, "POLLING_DIRECTORY_NOT_OWNED"):
            self.prepare()
        unknown.unlink()
        receiver = self.c.directory / "receiver.py"
        receiver.unlink()
        receiver.symlink_to(Path(self.temp.name) / "elsewhere")
        with self.assertRaisesRegex(private.EgressError, "EGRESS_SYMLINK"):
            self.prepare()

    def test_foreign_extra_or_privileged_receiver_is_refused(self):
        self.prepare()
        good = inspected(self.c)

        def commands(c, args, **kwargs):
            return b"owned-receiver" if args[1] == "ps" else json.dumps([row]).encode()

        with mock.patch.object(recovery, "command", commands):
            row = copy.deepcopy(good)
            self.assertEqual(recovery.container(self.c)["Id"], "owned-receiver")
            for case in ("identity", "env", "image", "mount", "network", "privileged"):
                with self.subTest(case=case):
                    row = copy.deepcopy(good)
                    if case == "identity":
                        row["Config"]["Labels"]["asm.polling.activation"] = "foreign"
                    if case == "env":
                        row["Config"]["Env"].append("ASM_MIGRATION_DATABASE_URL=forbidden")
                    if case == "image":
                        row["Image"] = "unreviewed"
                    if case == "mount":
                        row["Mounts"][0]["RW"] = True
                    if case == "network":
                        row["NetworkSettings"]["Networks"]["unowned"] = {}
                    if case == "privileged":
                        row["HostConfig"]["Privileged"] = True
                    with self.assertRaises(RuntimeError):
                        recovery.container(self.c)
        with mock.patch.object(recovery, "command", return_value=b"first second"):
            with self.assertRaisesRegex(RuntimeError, "MULTIPLE_RECEIVERS"):
                recovery.container(self.c)

    def test_bundled_source_is_exact_and_inner_operator_is_valid_python(self):
        expected = recovery.receiver_bytes()
        with mock.patch.object(recovery, "BUNDLED_RECEIVER", expected.decode()):
            self.assertEqual(recovery.receiver_bytes(), expected)
        compile(recovery.OPERATOR_CODE, "operator", "exec")


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.c = SimpleNamespace(prefix=["compose", "polling"])
        self.current, self.webhook, self.calls = None, "EXPECTED", []
        self.fail_wait, self.fail_remove_after, self.fail_stop = False, False, False
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        for name, function in {
            "app_runtime": lambda c: self.calls.append("app-check"),
            "prepare": lambda c, **kw: self.calls.append("prepare"),
            "check_inputs": lambda c: self.calls.append("input-check"),
            "container": lambda c: self.current,
            "command": self.command,
            "operator": self.operator,
            "wait_state": self.wait,
            "save_mode": lambda c, mode, result: self.calls.append("saved-" + mode),
        }.items():
            stack.enter_context(mock.patch.object(recovery, name, function))
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))

    def command(self, c, args, **kwargs):
        if "up" in args:
            self.calls.append("start")
            self.current = {"Id": "owned", "State": {"Running": True}}
        elif args[:2] == ["docker", "start"]:
            self.calls.append("restart")
            self.current["State"]["Running"] = True
        elif args[:2] == ["docker", "stop"]:
            self.calls.append("stop")
            if self.fail_stop:
                raise RuntimeError("STOP_FAILED")
            self.current["State"]["Running"] = False
        else:
            raise AssertionError(args)
        return b""

    def operator(self, c, action):
        self.calls.append(action)
        if action == "remove":
            self.assertTrue(self.current["State"]["Running"])
            self.webhook = "NONE"
            if self.fail_remove_after:
                raise RuntimeError("RESPONSE_LOST")
        if action == "restore":
            self.assertFalse(self.current and self.current["State"]["Running"])
            self.webhook = "EXPECTED"
        return {"ok": True, "webhook": self.webhook, "pending_updates": 6}

    def wait(self, c, states, seconds):
        self.calls.append("ready" if "WAITING_WEBHOOK_REMOVAL" in states else "poll-observed")
        if self.fail_wait:
            raise RuntimeError("RECEIVER_NOT_READY")
        return {"successful_polls": 1, "state": "RUNNING"}

    def test_receiver_is_ready_before_switch_and_rerun_does_not_restart_app_or_receiver(self):
        recovery.enable(self.c)
        self.assertLess(self.calls.index("start"), self.calls.index("ready"))
        self.assertLess(self.calls.index("ready"), self.calls.index("remove"))
        self.assertLess(self.calls.index("poll-observed"), self.calls.index("saved-POLLING"))
        recovery.enable(self.c)
        self.assertEqual(self.calls.count("start"), 1)
        self.assertNotIn("stop", self.calls)
        self.assertEqual(self.webhook, "NONE")

    def test_not_ready_leaves_webhook_and_queue_untouched(self):
        self.fail_wait = True
        with self.assertRaisesRegex(RuntimeError, "RECEIVER_NOT_READY"):
            recovery.enable(self.c)
        self.assertEqual(self.webhook, "EXPECTED")
        self.assertNotIn("remove", self.calls)
        self.assertNotIn("saved-POLLING", self.calls)

    def test_disconnect_after_delete_leaves_running_receiver_and_enable_can_resume(self):
        self.fail_remove_after = True
        with self.assertRaisesRegex(RuntimeError, "RESPONSE_LOST"):
            recovery.enable(self.c)
        self.assertTrue(self.current["State"]["Running"])
        self.assertEqual(self.webhook, "NONE")
        self.fail_remove_after = False
        recovery.enable(self.c)
        self.assertEqual(self.calls.count("start"), 1)
        self.assertEqual(self.calls[-1], "saved-POLLING")

    def test_rollback_stops_receiver_before_restoring_webhook_and_reenable_reuses_it(self):
        recovery.enable(self.c)
        recovery.rollback(self.c)
        self.assertLess(self.calls.index("stop"), self.calls.index("restore"))
        self.assertEqual(self.webhook, "EXPECTED")
        recovery.enable(self.c)
        self.assertEqual(self.calls.count("start"), 1)
        self.assertEqual(self.calls.count("restart"), 1)

    def test_failed_stop_never_restores_competing_webhook(self):
        recovery.enable(self.c)
        self.fail_stop = True
        with self.assertRaisesRegex(RuntimeError, "STOP_FAILED"):
            recovery.rollback(self.c)
        self.assertNotIn("restore", self.calls)
        self.assertEqual(self.webhook, "NONE")


class ProviderOperatorTests(unittest.TestCase):
    def operator(self, action, initial="EXPECTED", owner="123", expected_owner="123"):
        calls, status = (
            [],
            {"url": "https://expected.invalid" if initial == "EXPECTED" else initial},
        )

        class Client:
            def __init__(self, settings):
                self.settings = settings

            async def get_webhook_info(self):
                return {"url": status["url"], "pending_update_count": 6}

            async def get_me(self):
                calls.append("identity")

            async def get_business_connection(self, external):
                return SimpleNamespace(owner_user_id=owner, is_enabled=True, can_reply=True)

            async def _readonly(self, method, payload):
                calls.append((method, payload))
                status["url"] = ""
                return True

            async def set_webhook(self):
                calls.append("restore")
                status["url"] = "https://expected.invalid"

            async def aclose(self):
                pass

        class TelegramError(Exception):
            pass

        output = io.StringIO()
        modules = {
            "asm.telegram.client": SimpleNamespace(
                TelegramClient=Client, TelegramError=TelegramError
            ),
            "asm.telegram.config": SimpleNamespace(
                TelegramSettings=lambda: SimpleNamespace(webhook_url="https://expected.invalid")
            ),
        }
        with (
            mock.patch.dict("sys.modules", modules),
            mock.patch.object(recovery.sys, "argv", ["operator", action]),
            mock.patch.dict(
                os.environ,
                {
                    "ASM_TELEGRAM_CONNECTION_ID": "private",
                    "ASM_TELEGRAM_EXPECTED_OWNER_ID": expected_owner,
                },
            ),
            contextlib.redirect_stdout(output),
        ):
            exec(compile(recovery.OPERATOR_CODE, "operator", "exec"), {})
        return json.loads(output.getvalue()), calls

    def test_delete_explicitly_preserves_queue_and_does_not_poll_or_send(self):
        result, calls = self.operator("remove")
        self.assertEqual(result, {"ok": True, "webhook": "NONE", "pending_updates": 6})
        self.assertEqual(calls, [("deleteWebhook", {"drop_pending_updates": False})])
        result, calls = self.operator("remove", initial="")
        self.assertTrue(result["ok"])
        self.assertEqual(calls, [])

    def test_foreign_webhook_and_wrong_owner_never_mutate_provider(self):
        result, calls = self.operator("remove", initial="https://foreign.invalid")
        self.assertEqual(result, {"ok": False, "code": "FOREIGN_WEBHOOK"})
        self.assertEqual(calls, [])
        result, calls = self.operator("preflight", owner="999")
        self.assertEqual(result, {"ok": False, "code": "CONNECTION_NOT_READY"})
        self.assertEqual(calls, ["identity"])


if __name__ == "__main__":
    unittest.main()
