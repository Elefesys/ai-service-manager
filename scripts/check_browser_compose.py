"""Validate the rendered browser Compose model without printing its secrets."""

import json
import sys
from pathlib import Path


class ModelError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ModelError(message)


def environment(service: dict[str, object]) -> dict[str, str]:
    value = service.get("environment")
    require(isinstance(value, dict), "service environment must be a mapping")
    return value  # type: ignore[return-value]


def main() -> int:
    try:
        model = json.loads(Path(sys.argv[1]).read_text())
        require(model.get("name") == "ai-service-manager-browser", "unexpected project name")
        services = model.get("services")
        require(isinstance(services, dict), "services are missing")
        postgres = services["postgres"]
        mounts = postgres.get("volumes", [])
        data = [item for item in mounts if item.get("target") == "/var/lib/postgresql"]
        require(len(data) == 1 and data[0].get("type") == "tmpfs", "database must use one tmpfs")
        bootstrap = [
            item
            for item in mounts
            if item.get("target") == "/docker-entrypoint-initdb.d/10-bootstrap.sh"
        ]
        require(
            len(bootstrap) == 1
            and bootstrap[0].get("type") == "bind"
            and bootstrap[0].get("read_only") is True,
            "read-only bootstrap bind is required",
        )
        require(environment(postgres).get("POSTGRES_DB") == "asm_test", "TEST database required")
        api = environment(services["api"])
        require(api.get("ASM_ENVIRONMENT") == "TEST", "API must run in TEST")
        require("asm_runtime:" in api.get("ASM_DATABASE_URL", ""), "runtime identity required")
        require(api.get("ASM_DATABASE_URL", "").endswith("/asm_test"), "API must use asm_test")
        for name in ("migrate", "browser-provision"):
            migration = environment(services[name]).get("ASM_MIGRATION_DATABASE_URL", "")
            require("asm_migrator:" in migration, f"{name} must use migration identity")
            require(migration.endswith("/asm_test"), f"{name} must use asm_test")
        print("BROWSER_COMPOSE_MODEL_CHECK: PASS")
        return 0
    except Exception:
        print(
            "Browser Compose model validation failed; rendered configuration is private.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
