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
                    "ASM_TELEGRAM_ENABLED": "false",
                    "TG_BOT_TOKEN": "",
                    "TG_WEBHOOK_SECRET": "",
                    "ASM_TELEGRAM_EXPECTED_BOT_ID": "",
                    "ASM_TELEGRAM_WEBHOOK_URL": "",
                    "ASM_DATABASE_URL": "postgresql+psycopg://asm_runtime:canary@postgres:5432/asm_test",
                    "ASM_STORAGE_ENVIRONMENT": "TEST",
                    "ASM_STORAGE_BUCKET": "asm-private-test",
                    "ASM_STORAGE_ENDPOINT": "http://127.0.0.1:9000",
                    "ASM_STORAGE_ACCESS_KEY": "runtime-access",
                    "ASM_STORAGE_SECRET_KEY": "runtime-secret",
                }
            },
            "migrate": {
                "environment": {
                    "ASM_MIGRATION_DATABASE_URL": "postgresql+psycopg://asm_migrator:canary@postgres:5432/asm_test"
                }
            },
            "browser-provision": {
                "environment": {
                    "ASM_ENVIRONMENT": "TEST",
                    "ASM_MIGRATION_DATABASE_URL": "postgresql+psycopg://asm_migrator:canary@postgres:5432/asm_test",
                }
            },
            "storage": {
                "environment": {
                    "MINIO_ROOT_USER": "root-access",
                    "MINIO_ROOT_PASSWORD": "root-secret",
                    "MINIO_BROWSER": "off",
                    "MINIO_API_CORS_ALLOW_ORIGIN": "http://127.0.0.1:8080",
                },
                "volumes": [{"type": "tmpfs", "target": "/data"}],
                "ports": [
                    {"host_ip": "127.0.0.1", "published": "9000", "target": 9000, "protocol": "tcp"}
                ],
            },
            "storage-init": {
                "environment": {
                    "STORAGE_ROOT_USER": "root-access",
                    "STORAGE_ROOT_PASSWORD": "root-secret",
                    "STORAGE_ACCESS_KEY": "runtime-access",
                    "STORAGE_SECRET_KEY": "runtime-secret",
                    "STORAGE_BUCKET": "asm-private-test",
                    "STORAGE_HOST": "storage",
                },
                "entrypoint": ["sh", "/bootstrap.sh"],
                "volumes": [
                    {
                        "type": "bind",
                        "source": "/source/infra/storage/bootstrap.sh",
                        "target": "/bootstrap.sh",
                        "read_only": True,
                    }
                ],
            },
            "browser-runtime": {
                "profiles": ["browser"],
                "build": {
                    "context": "/source",
                    "dockerfile": "infra/Dockerfile.backend",
                    "target": "development",
                },
                "command": ["python", "scripts/m2_4_browser_worker.py"],
                "read_only": True,
                "tmpfs": ["/tmp"],
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
                "environment": {
                    "ASM_ENVIRONMENT": "TEST",
                    "ASM_DATABASE_URL": "postgresql+psycopg://asm_runtime:canary@postgres:5432/asm_test",
                    "ASM_STORAGE_ENVIRONMENT": "TEST",
                    "ASM_STORAGE_BUCKET": "asm-private-test",
                    "ASM_STORAGE_ENDPOINT": "http://storage:9000",
                    "ASM_STORAGE_ACCESS_KEY": "runtime-access",
                    "ASM_STORAGE_SECRET_KEY": "runtime-secret",
                },
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


@pytest.mark.parametrize("origin", [None, "*", "http://other.example"])
def test_storage_cors_is_only_browser_test_origin(model, origin):
    invalid(
        model,
        lambda value: value["services"]["storage"]["environment"].update(
            MINIO_API_CORS_ALLOW_ORIGIN=origin
        ),
        "BROWSER_COMPOSE_STORAGE_CORS_INVALID",
    )


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


@pytest.mark.parametrize(
    ("service", "name", "value", "code"),
    [
        ("api", "ASM_TELEGRAM_ENABLED", "true", "BROWSER_COMPOSE_API_SECRETS_INVALID"),
        ("api", "TG_BOT_TOKEN", "canary-secret", "BROWSER_COMPOSE_API_SECRETS_INVALID"),
        (
            "api",
            "ASM_DATABASE_URL",
            "postgresql+psycopg://asm_runtime:canary@external:5432/asm_test",
            "BROWSER_COMPOSE_API_IDENTITY_INVALID",
        ),
        (
            "browser-provision",
            "ASM_ENVIRONMENT",
            "LOCAL",
            "BROWSER_COMPOSE_PROVISION_ENVIRONMENT_INVALID",
        ),
        (
            "browser-runtime",
            "ASM_ENVIRONMENT",
            "LOCAL",
            "BROWSER_COMPOSE_RUNNER_ENVIRONMENT_INVALID",
        ),
        (
            "browser-runtime",
            "ASM_ADMIN_DATABASE_URL",
            "canary-secret",
            "BROWSER_COMPOSE_RUNNER_ENVIRONMENT_INVALID",
        ),
        (
            "browser-runtime",
            "ASM_MIGRATION_DATABASE_URL",
            "canary-secret",
            "BROWSER_COMPOSE_RUNNER_ENVIRONMENT_INVALID",
        ),
        (
            "browser-runtime",
            "TG_BOT_TOKEN",
            "canary-secret",
            "BROWSER_COMPOSE_RUNNER_ENVIRONMENT_INVALID",
        ),
        (
            "browser-runtime",
            "ASM_DATABASE_URL",
            "postgresql+psycopg://asm_migrator:canary@postgres:5432/asm_test",
            "BROWSER_COMPOSE_RUNNER_IDENTITY_INVALID",
        ),
        (
            "browser-runtime",
            "ASM_DATABASE_URL",
            "postgresql+psycopg://asm_runtime:canary@postgres:5432/asm_local",
            "BROWSER_COMPOSE_RUNNER_IDENTITY_INVALID",
        ),
        (
            "browser-runtime",
            "ASM_STORAGE_ENVIRONMENT",
            "LOCAL",
            "BROWSER_COMPOSE_STORAGE_ENVIRONMENT_INVALID",
        ),
        (
            "browser-runtime",
            "ASM_STORAGE_BUCKET",
            "asm-private-local",
            "BROWSER_COMPOSE_STORAGE_ENVIRONMENT_INVALID",
        ),
        (
            "browser-runtime",
            "ASM_STORAGE_ENDPOINT",
            "http://127.0.0.1:9000",
            "BROWSER_COMPOSE_STORAGE_ORIGIN_INVALID",
        ),
        (
            "api",
            "ASM_STORAGE_ENDPOINT",
            "http://storage:9000",
            "BROWSER_COMPOSE_STORAGE_ORIGIN_INVALID",
        ),
        (
            "storage-init",
            "STORAGE_BUCKET",
            "asm-private-local",
            "BROWSER_COMPOSE_STORAGE_ORIGIN_INVALID",
        ),
        (
            "browser-runtime",
            "ASM_STORAGE_SECRET_KEY",
            "root-secret",
            "BROWSER_COMPOSE_STORAGE_CREDENTIALS_INVALID",
        ),
        ("api", "ASM_STORAGE_ACCESS_KEY", "drift", "BROWSER_COMPOSE_STORAGE_CREDENTIALS_INVALID"),
        (
            "storage-init",
            "STORAGE_SECRET_KEY",
            "drift",
            "BROWSER_COMPOSE_STORAGE_CREDENTIALS_INVALID",
        ),
    ],
)
def test_rejects_runtime_storage_and_secret_drift(model, service, name, value, code):
    invalid(
        model, lambda item: item["services"][service]["environment"].update({name: value}), code
    )


@pytest.mark.parametrize(
    ("service", "name", "value", "code"),
    [
        (
            "storage",
            "volumes",
            [{"type": "volume", "target": "/data"}],
            "BROWSER_COMPOSE_STORAGE_MOUNT_INVALID",
        ),
        ("storage", "tmpfs", ["/data"], "BROWSER_COMPOSE_STORAGE_MOUNT_INVALID"),
        (
            "storage",
            "ports",
            [{"host_ip": "0.0.0.0", "published": "9000", "target": 9000, "protocol": "tcp"}],
            "BROWSER_COMPOSE_STORAGE_PORT_INVALID",
        ),
        (
            "storage",
            "ports",
            [{"host_ip": "127.0.0.1", "published": "9001", "target": 9001, "protocol": "tcp"}],
            "BROWSER_COMPOSE_STORAGE_PORT_INVALID",
        ),
        (
            "storage-init",
            "entrypoint",
            ["sh", "-c", "unsafe"],
            "BROWSER_COMPOSE_STORAGE_BOOTSTRAP_INVALID",
        ),
        (
            "storage-init",
            "volumes",
            [
                {
                    "type": "bind",
                    "source": "/other/bootstrap.sh",
                    "target": "/bootstrap.sh",
                    "read_only": True,
                }
            ],
            "BROWSER_COMPOSE_STORAGE_BOOTSTRAP_INVALID",
        ),
        (
            "storage-init",
            "volumes",
            [
                {
                    "type": "bind",
                    "source": "/source/infra/storage/bootstrap.sh",
                    "target": "/bootstrap.sh",
                    "read_only": False,
                }
            ],
            "BROWSER_COMPOSE_STORAGE_BOOTSTRAP_INVALID",
        ),
        ("browser-runtime", "profiles", [], "BROWSER_COMPOSE_RUNNER_BOUNDARY_INVALID"),
        ("browser-runtime", "read_only", False, "BROWSER_COMPOSE_RUNNER_BOUNDARY_INVALID"),
        ("browser-runtime", "privileged", True, "BROWSER_COMPOSE_RUNNER_BOUNDARY_INVALID"),
        ("browser-runtime", "network_mode", "host", "BROWSER_COMPOSE_RUNNER_BOUNDARY_INVALID"),
        (
            "browser-runtime",
            "volumes",
            [{"type": "bind", "source": "/", "target": "/host"}],
            "BROWSER_COMPOSE_RUNNER_BOUNDARY_INVALID",
        ),
        ("browser-runtime", "command", ["sh"], "BROWSER_COMPOSE_RUNNER_BOUNDARY_INVALID"),
        (
            "browser-runtime",
            "build",
            {"context": "/source", "dockerfile": "unapproved", "target": "development"},
            "BROWSER_COMPOSE_RUNNER_BUILD_INVALID",
        ),
    ],
)
def test_rejects_storage_exposure_and_runner_boundary_changes(model, service, name, value, code):
    invalid(model, lambda item: item["services"][service].update({name: value}), code)


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
