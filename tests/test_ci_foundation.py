"""Execute the CI shell routes with isolated command doubles, never real Docker."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class FoundationRoutingTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "scripts").mkdir()
        (self.root / "bin").mkdir()
        for name in ("ci.sh", "check_foundation_gate.sh"):
            shutil.copyfile(ROOT / "scripts" / name, self.root / "scripts" / name)
        (self.root / "scripts/test_telegram_egress.sh").write_text(
            'printf \'["egress"]\\n\' >> "$CI_TEST_TRACE"\nexit "$CI_TEST_EGRESS_STATUS"\n'
        )
        self.trace = self.root / "trace.jsonl"
        self.trace.touch()
        tool = """import json,os,sys
from pathlib import Path
name=Path(sys.argv[0]).name
args=sys.argv[1:]
with Path(os.environ["CI_TEST_TRACE"]).open("a") as trace:
    trace.write(json.dumps([name,*args])+"\\n")
if name=="python3":
    if args==["scripts/init_local.py"]:
        Path(".env").touch()
    elif args==["-"]:
        sys.stdin.read()
elif name=="git":
    print(os.environ["CI_TEST_SHA"])
elif name=="docker":
    failure=os.environ.get("CI_TEST_FAILURE")
    if failure=="backend" and args[-3:]==["run","--rm","checks"]:
        sys.exit(17)
    if failure=="cleanup" and "down" in args:
        sys.exit(17)
"""
        for name in ("python3", "docker", "git"):
            executable = self.root / "bin" / name
            executable.write_text(f"#!{sys.executable}\n" + tool)
            executable.chmod(0o700)
        self.env = {
            **os.environ,
            "PATH": str(self.root / "bin") + os.pathsep + os.environ["PATH"],
            "CI_TEST_TRACE": str(self.trace),
            "CI_TEST_EGRESS_STATUS": "0",
            "CI_TEST_SHA": "a" * 40,
        }

    def run_ci(self, args=(), **env):
        self.trace.write_text("")
        result = subprocess.run(
            ["sh", "scripts/ci.sh", *args],
            cwd=self.root,
            env={**self.env, **env},
            capture_output=True,
            text=True,
            timeout=10,
        )
        calls = [json.loads(line) for line in self.trace.read_text().splitlines()]
        return result, calls

    def assert_core_gates(self, calls):
        docker = [call[1:] for call in calls if call[0] == "docker"]
        for args in docker:
            self.assertEqual(
                args[:7],
                [
                    "compose",
                    "--env-file",
                    "infra/images.lock.env",
                    "--env-file",
                    ".env",
                    "--profile",
                    "test",
                ],
            )
        operations = [args[7:] for args in docker]
        self.assertEqual(
            operations,
            [
                ["config", "--quiet"],
                ["build", "--pull", "api", "checks", "frontend"],
                ["run", "--rm", "checks"],
                ["run", "--rm", "--no-deps", "--entrypoint", "minio", "storage", "--version"],
                ["run", "--rm", "--no-deps", "--entrypoint", "mc", "storage-init", "--version"],
                ["up", "-d", "--wait", "api", "worker", "scheduler", "frontend"],
                ["images"],
                ["down", "--remove-orphans"],
            ],
        )
        self.assertEqual(calls[0], ["python3", "scripts/init_local.py"])
        self.assertIn(["python3", "-"], calls)

    def test_default_preserves_full_sequence(self):
        result, calls = self.run_ci()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_core_gates(calls)
        self.assertEqual(calls.count(["egress"]), 1)
        backend = next(i for i, call in enumerate(calls) if call[-1:] == ["checks"])
        self.assertLess(calls.index(["egress"]), backend)

    def test_explicit_core_keeps_all_other_gates(self):
        result, calls = self.run_ci(("--foundation-core",))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_core_gates(calls)
        self.assertNotIn(["egress"], calls)

    def test_unknown_args_refuse_before_init_or_docker(self):
        for args in (("--unknown",), ("",), ("--foundation-core", "extra"), ("extra", "extra")):
            with self.subTest(args=args):
                result, calls = self.run_ci(args)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(calls, [])
                self.assertFalse((self.root / ".env").exists())

    def test_failed_required_gate_propagates_and_cleans(self):
        cases = [
            ((), {"CI_TEST_FAILURE": "backend"}),
            (("--foundation-core",), {"CI_TEST_FAILURE": "backend"}),
            ((), {"CI_TEST_EGRESS_STATUS": "17"}),
        ]
        for args, env in cases:
            with self.subTest(args=args, env=env):
                result, calls = self.run_ci(args, **env)
                self.assertEqual(result.returncode, 17)
                self.assertEqual(calls[-1][-2:], ["down", "--remove-orphans"])
                self.assertNotIn(["python3", "-"], calls)

    def test_cleanup_failure_is_not_success(self):
        for args in ((), ("--foundation-core",)):
            with self.subTest(args=args):
                result, _ = self.run_ci(args, CI_TEST_FAILURE="cleanup")
                self.assertNotEqual(result.returncode, 0)

    def test_aggregate_requires_exactly_two_success_results(self):
        cases = [("success", "success")]
        for status in ("failure", "cancelled", "skipped", "", "unknown"):
            cases.extend([(status, "success"), ("success", status)])
        cases.extend([(), ("success",), ("success", "success", "extra")])
        for args in cases:
            with self.subTest(args=args):
                result = subprocess.run(
                    ["sh", "scripts/check_foundation_gate.sh", *args],
                    cwd=self.root,
                    env=self.env,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                self.assertEqual(result.returncode == 0, args == ("success", "success"))


if __name__ == "__main__":
    unittest.main()
