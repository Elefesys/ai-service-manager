"""Validate the rendered browser Compose model without printing its secrets."""

import json
import sys
from pathlib import Path
from typing import NoReturn, cast
from urllib.parse import urlsplit


class ModelError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def reject(code: str) -> NoReturn:
    raise ModelError(code)


def mapping(value: object, code: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        reject(code)
    return cast(dict[str, object], value)


def environment(service: dict[str, object]) -> dict[str, object]:
    return mapping(service.get("environment"), "BROWSER_COMPOSE_ENVIRONMENT_INVALID")


def runtime_identity(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        url = urlsplit(value)
        return (
            url.scheme == "postgresql+psycopg"
            and url.username == "asm_runtime"
            and bool(url.password)
            and url.hostname == "postgres"
            and url.port == 5432
            and url.path == "/asm_test"
            and not url.query
            and not url.fragment
        )
    except ValueError:
        return False


def single_tmpfs(service: dict[str, object], target: str, code: str) -> None:
    volumes = service.get("volumes", [])
    tmpfs = service.get("tmpfs", [])
    if not isinstance(volumes, list) or not isinstance(tmpfs, list):
        reject(code)
    if not all(isinstance(item, dict) for item in volumes) or not all(
        isinstance(item, str) for item in tmpfs
    ):
        reject(code)
    mounts = [item for item in volumes if item.get("target") == target]
    service_mounts = [item for item in tmpfs if item.split(":", 1)[0] == target]
    if len(mounts) != 1 or mounts[0].get("type") != "tmpfs" or service_mounts:
        reject(code)


def validate_storage(services: dict[str, object], api: dict[str, object]) -> None:
    storage = mapping(services.get("storage"), "BROWSER_COMPOSE_STORAGE_INVALID")
    initializer = mapping(services.get("storage-init"), "BROWSER_COMPOSE_STORAGE_INVALID")
    runner = mapping(services.get("browser-runtime"), "BROWSER_COMPOSE_RUNNER_INVALID")
    storage_env, initializer_env = environment(storage), environment(initializer)
    runtime = environment(runner)
    if storage_env.get("MINIO_API_CORS_ALLOW_ORIGIN") != "http://127.0.0.1:8080":
        reject("BROWSER_COMPOSE_STORAGE_CORS_INVALID")
    single_tmpfs(storage, "/data", "BROWSER_COMPOSE_STORAGE_MOUNT_INVALID")
    ports = storage.get("ports")
    if not (
        isinstance(ports, list)
        and len(ports) == 1
        and isinstance(ports[0], dict)
        and ports[0].get("host_ip") == "127.0.0.1"
        and str(ports[0].get("published")) == "9000"
        and ports[0].get("target") == 9000
        and ports[0].get("protocol") == "tcp"
        and storage_env.get("MINIO_BROWSER") == "off"
    ):
        reject("BROWSER_COMPOSE_STORAGE_PORT_INVALID")

    expected_runtime_keys = {
        "ASM_ENVIRONMENT",
        "ASM_DATABASE_URL",
        "ASM_STORAGE_ENVIRONMENT",
        "ASM_STORAGE_ENDPOINT",
        "ASM_STORAGE_BUCKET",
        "ASM_STORAGE_ACCESS_KEY",
        "ASM_STORAGE_SECRET_KEY",
    }
    if set(runtime) != expected_runtime_keys or runtime.get("ASM_ENVIRONMENT") != "TEST":
        reject("BROWSER_COMPOSE_RUNNER_ENVIRONMENT_INVALID")
    if not runtime_identity(runtime.get("ASM_DATABASE_URL")) or runtime.get(
        "ASM_DATABASE_URL"
    ) != api.get("ASM_DATABASE_URL"):
        reject("BROWSER_COMPOSE_RUNNER_IDENTITY_INVALID")
    if (
        runner.get("profiles") != ["browser"]
        or runner.get("command") != ["python", "scripts/m2_4_browser_worker.py"]
        or runner.get("read_only") is not True
        or runner.get("tmpfs") != ["/tmp"]
        or runner.get("cap_drop") != ["ALL"]
        or runner.get("security_opt") != ["no-new-privileges:true"]
        or runner.get("privileged", False) is not False
        or runner.get("network_mode") is not None
        or runner.get("volumes", []) != []
        or runner.get("ports", []) != []
    ):
        reject("BROWSER_COMPOSE_RUNNER_BOUNDARY_INVALID")
    for actor in (api, runtime):
        if (
            actor.get("ASM_STORAGE_ENVIRONMENT") != "TEST"
            or actor.get("ASM_STORAGE_BUCKET") != "asm-private-test"
        ):
            reject("BROWSER_COMPOSE_STORAGE_ENVIRONMENT_INVALID")
    if (
        api.get("ASM_STORAGE_ENDPOINT") != "http://127.0.0.1:9000"
        or runtime.get("ASM_STORAGE_ENDPOINT") != "http://storage:9000"
        or initializer_env.get("STORAGE_HOST") != "storage"
        or initializer_env.get("STORAGE_BUCKET") != "asm-private-test"
    ):
        reject("BROWSER_COMPOSE_STORAGE_ORIGIN_INVALID")
    for suffix, root_name in (("ACCESS_KEY", "USER"), ("SECRET_KEY", "PASSWORD")):
        value = runtime.get(f"ASM_STORAGE_{suffix}")
        root_value = storage_env.get(f"MINIO_ROOT_{root_name}")
        if (
            not isinstance(value, str)
            or not value
            or not isinstance(root_value, str)
            or not root_value
            or value == root_value
            or value != api.get(f"ASM_STORAGE_{suffix}")
            or value != initializer_env.get(f"STORAGE_{suffix}")
            or root_value != initializer_env.get(f"STORAGE_ROOT_{root_name}")
        ):
            reject("BROWSER_COMPOSE_STORAGE_CREDENTIALS_INVALID")
    build = mapping(runner.get("build"), "BROWSER_COMPOSE_RUNNER_BUILD_INVALID")
    context = build.get("context")
    if (
        not isinstance(context, str)
        or not Path(context).is_absolute()
        or build.get("dockerfile") != "infra/Dockerfile.backend"
        or build.get("target") != "development"
    ):
        reject("BROWSER_COMPOSE_RUNNER_BUILD_INVALID")
    source = str(Path(context) / "infra/storage/bootstrap.sh")
    if initializer.get("entrypoint") != ["sh", "/bootstrap.sh"]:
        reject("BROWSER_COMPOSE_STORAGE_BOOTSTRAP_INVALID")
    volumes = initializer.get("volumes")
    if not (
        isinstance(volumes, list)
        and len(volumes) == 1
        and isinstance(volumes[0], dict)
        and volumes[0].get("type") == "bind"
        and volumes[0].get("source") == source
        and volumes[0].get("target") == "/bootstrap.sh"
        and volumes[0].get("read_only") is True
    ):
        reject("BROWSER_COMPOSE_STORAGE_BOOTSTRAP_INVALID")


def validate(model: object) -> None:
    root = mapping(model, "BROWSER_COMPOSE_MODEL_INVALID")
    if root.get("name") != "ai-service-manager-browser":
        reject("BROWSER_COMPOSE_PROJECT_INVALID")
    services = mapping(root.get("services"), "BROWSER_COMPOSE_SERVICES_INVALID")
    required = {
        name: mapping(services.get(name), "BROWSER_COMPOSE_SERVICE_INVALID")
        for name in ("postgres", "api", "migrate", "browser-provision")
    }

    postgres = required["postgres"]
    volumes = postgres.get("volumes", [])
    if not isinstance(volumes, list) or not all(isinstance(item, dict) for item in volumes):
        reject("BROWSER_COMPOSE_MOUNTS_INVALID")
    mounts = [cast(dict[str, object], item) for item in volumes]
    data = [item for item in mounts if item.get("target") == "/var/lib/postgresql"]
    service_tmpfs = postgres.get("tmpfs", [])
    if not isinstance(service_tmpfs, list) or not all(
        isinstance(item, str) for item in service_tmpfs
    ):
        reject("BROWSER_COMPOSE_MOUNTS_INVALID")
    service_data = [
        item for item in service_tmpfs if item.split(":", 1)[0] == "/var/lib/postgresql"
    ]
    if len(data) + len(service_data) != 1 or service_data or data[0].get("type") != "tmpfs":
        reject("BROWSER_COMPOSE_DATA_MOUNT_INVALID")

    bootstrap = [
        item
        for item in mounts
        if item.get("target") == "/docker-entrypoint-initdb.d/10-bootstrap.sh"
    ]
    if not (
        len(bootstrap) == 1
        and bootstrap[0].get("type") == "bind"
        and bootstrap[0].get("read_only") is True
    ):
        reject("BROWSER_COMPOSE_BOOTSTRAP_MOUNT_INVALID")

    if environment(postgres).get("POSTGRES_DB") != "asm_test":
        reject("BROWSER_COMPOSE_DATABASE_INVALID")
    api = environment(required["api"])
    database_url = api.get("ASM_DATABASE_URL")
    if api.get("ASM_ENVIRONMENT") != "TEST" or not isinstance(database_url, str):
        reject("BROWSER_COMPOSE_API_ENVIRONMENT_INVALID")
    if "asm_runtime:" not in database_url or not database_url.endswith("/asm_test"):
        reject("BROWSER_COMPOSE_API_IDENTITY_INVALID")
    if not runtime_identity(database_url):
        reject("BROWSER_COMPOSE_API_IDENTITY_INVALID")
    if (
        api.get("ASM_TELEGRAM_ENABLED") != "false"
        or any(
            api.get(key) != ""
            for key in (
                "TG_BOT_TOKEN",
                "TG_WEBHOOK_SECRET",
                "ASM_TELEGRAM_EXPECTED_BOT_ID",
                "ASM_TELEGRAM_WEBHOOK_URL",
            )
        )
        or "ASM_ADMIN_DATABASE_URL" in api
        or "ASM_MIGRATION_DATABASE_URL" in api
    ):
        reject("BROWSER_COMPOSE_API_SECRETS_INVALID")
    for name in ("migrate", "browser-provision"):
        migration_url = environment(required[name]).get("ASM_MIGRATION_DATABASE_URL")
        if (
            not isinstance(migration_url, str)
            or "asm_migrator:" not in migration_url
            or not migration_url.endswith("/asm_test")
        ):
            reject("BROWSER_COMPOSE_MIGRATION_IDENTITY_INVALID")
    if environment(required["browser-provision"]).get("ASM_ENVIRONMENT") != "TEST":
        reject("BROWSER_COMPOSE_PROVISION_ENVIRONMENT_INVALID")
    validate_storage(services, api)


def main() -> int:
    try:
        if len(sys.argv) != 2:
            reject("BROWSER_COMPOSE_INPUT_INVALID")
        validate(json.loads(Path(sys.argv[1]).read_text()))
        print("BROWSER_COMPOSE_MODEL_CHECK: PASS")
        return 0
    except ModelError as error:
        print(error.code, file=sys.stderr)
        return 1
    except Exception:
        print("BROWSER_COMPOSE_VALIDATION_UNEXPECTED", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
