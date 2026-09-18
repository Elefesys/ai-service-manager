"""Validate the rendered browser Compose model without printing its secrets."""

import json
import sys
from pathlib import Path
from typing import NoReturn, cast


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
    for name in ("migrate", "browser-provision"):
        migration_url = environment(required[name]).get("ASM_MIGRATION_DATABASE_URL")
        if (
            not isinstance(migration_url, str)
            or "asm_migrator:" not in migration_url
            or not migration_url.endswith("/asm_test")
        ):
            reject("BROWSER_COMPOSE_MIGRATION_IDENTITY_INVALID")


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
