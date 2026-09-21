import pytest
from asm.foundation import Health, Settings, create_app
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError


class StubDatabase:
    def __init__(self, failed=False):
        self.failed = failed
        self.closed = False

    async def check(self):
        if self.failed:
            raise RuntimeError("sensitive-connection-details")

    async def close(self):
        self.closed = True


def settings():
    return Settings(
        environment="TEST",
        database_url=SecretStr("postgresql+psycopg://asm_runtime:test@localhost/asm_test"),
    )


def test_health_lifecycle_and_metadata():
    db = StubDatabase()
    with TestClient(create_app(settings(), db)) as client:
        assert client.get("/health/live").json() == {"status": "ok", "component": "api"}
        response = client.get("/health/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "component": "database"}
        assert client.get("/api/v1/system").json()["business_features_enabled"] is False
        assert client.get("/api/v1/workspaces").status_code == 404
    assert db.closed


def test_readiness_fails_closed_and_liveness_is_independent():
    with TestClient(create_app(settings(), StubDatabase(True))) as client:
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert "sensitive" not in response.text
        assert response.json()["status"] == "unavailable"
        assert client.get("/health/live").status_code == 200


@pytest.mark.parametrize(
    "url", ["sqlite:///test.db", "postgresql+psycopg://asm_admin:x@localhost/asm_test", "not-a-url"]
)
def test_rejects_wrong_database_identity_or_driver(url):
    with pytest.raises(ValidationError):
        Settings(environment="TEST", database_url=SecretStr(url))


@pytest.mark.parametrize("environment", ["PRODUCTION", "STAGING"])
def test_shell_refuses_non_local_environments(environment):
    with pytest.raises(ValidationError):
        Settings(environment=environment, database_url=settings().database_url)


def test_schemas_are_strict():
    with pytest.raises(ValidationError):
        Health(status="ok", component="api", workspace_id="invented")


def test_settings_hide_connection_secret():
    assert "test@" not in repr(settings())


def test_runtime_database_head_is_independent_from_frozen_tenancy_contract():
    from asm.foundation import DATABASE_SCHEMA_REVISION
    from asm.tenancy import SCHEMA_REVISION

    assert SCHEMA_REVISION == "0003"
    # M2.1 adds its assigned migration; the frozen tenancy.v1 head above stays 0003.
    assert DATABASE_SCHEMA_REVISION == "0005"
