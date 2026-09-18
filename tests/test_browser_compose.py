import copy
import subprocess
import sys

import pytest

from scripts.check_browser_compose import ModelError, validate


@pytest.fixture
def model():
    return {
        "name": "ai-service-manager-browser",
        "volumes": {"unused": {"name": "safe-unused-declaration"}},
        "services": {
            "postgres": {
                "environment": {"POSTGRES_DB": "asm_test"},
                "volumes": [
                    {"type": "tmpfs", "target": "/var/lib/postgresql"},
                    {
                        "type": "bind",
                        "source": "/source/bootstrap.sh",
                        "target": "/docker-entrypoint-initdb.d/10-bootstrap.sh",
                        "read_only": True,
                    },
                ],
            },
            "api": {
                "environment": {
                    "ASM_ENVIRONMENT": "TEST",
                    "ASM_DATABASE_URL": "postgresql+psycopg://asm_runtime:canary@postgres:5432/asm_test",
                }
            },
            "migrate": {
                "environment": {
                    "ASM_MIGRATION_DATABASE_URL": "postgresql+psycopg://asm_migrator:canary@postgres:5432/asm_test"
                }
            },
            "browser-provision": {
                "environment": {
                    "ASM_MIGRATION_DATABASE_URL": "postgresql+psycopg://asm_migrator:canary@postgres:5432/asm_test"
                }
            },
        },
    }


def invalid(model, mutate, code):
    candidate = copy.deepcopy(model)
    mutate(candidate)
    with pytest.raises(ModelError, match=f"^{code}$"):
        validate(candidate)


def test_accepts_explicit_tmpfs_and_ignores_unused_top_level_volume(model):
    validate(model)


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (
            lambda value: value["services"]["postgres"].update(
                volumes=value["services"]["postgres"]["volumes"][1:]
            ),
            "BROWSER_COMPOSE_DATA_MOUNT_INVALID",
        ),
        (
            lambda value: value["services"]["postgres"]["volumes"].append(
                {"type": "tmpfs", "target": "/var/lib/postgresql"}
            ),
            "BROWSER_COMPOSE_DATA_MOUNT_INVALID",
        ),
        (
            lambda value: value["services"]["postgres"]["volumes"][0].update(type="volume"),
            "BROWSER_COMPOSE_DATA_MOUNT_INVALID",
        ),
        (
            lambda value: value["services"]["postgres"].update(tmpfs=["/var/lib/postgresql"]),
            "BROWSER_COMPOSE_DATA_MOUNT_INVALID",
        ),
        (
            lambda value: value["services"]["postgres"].update(
                volumes=value["services"]["postgres"]["volumes"][:1]
            ),
            "BROWSER_COMPOSE_BOOTSTRAP_MOUNT_INVALID",
        ),
        (
            lambda value: value["services"]["postgres"]["volumes"][1].update(read_only=False),
            "BROWSER_COMPOSE_BOOTSTRAP_MOUNT_INVALID",
        ),
        (lambda value: value.update(name="wrong"), "BROWSER_COMPOSE_PROJECT_INVALID"),
        (
            lambda value: value["services"]["api"]["environment"].update(ASM_ENVIRONMENT="LOCAL"),
            "BROWSER_COMPOSE_API_ENVIRONMENT_INVALID",
        ),
        (
            lambda value: value["services"]["api"]["environment"].update(
                ASM_DATABASE_URL="postgresql+psycopg://asm_runtime:canary@postgres/asm_local"
            ),
            "BROWSER_COMPOSE_API_IDENTITY_INVALID",
        ),
        (
            lambda value: value["services"]["migrate"]["environment"].update(
                ASM_MIGRATION_DATABASE_URL="postgresql+psycopg://asm_runtime:canary@postgres/asm_test"
            ),
            "BROWSER_COMPOSE_MIGRATION_IDENTITY_INVALID",
        ),
    ],
)
def test_rejects_invalid_models(model, mutate, code):
    invalid(model, mutate, code)


@pytest.mark.parametrize("payload", ["not-json", "[]", '{"services": []}'])
def test_cli_rejects_malformed_input_without_secret(tmp_path, payload):
    path = tmp_path / "model.json"
    path.write_text(payload + " canary-secret" if payload == "not-json" else payload)
    result = subprocess.run(
        [sys.executable, "scripts/check_browser_compose.py", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "canary-secret" not in result.stdout + result.stderr
    assert "BROWSER_COMPOSE_" in result.stderr
