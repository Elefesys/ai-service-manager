"""Pure validation/crypto boundary checks; these do not claim database evidence."""

import asyncio
import threading
from pathlib import Path

import pytest
from asm.auth.config import AuthSettings
from asm.auth.crypto import (
    PASSWORD_HASHER,
    HashBudget,
    RateLimiter,
    check_csrf,
    csrf_value,
    new_token,
    normalize_login,
    token_verifier,
    verify_password,
)
from asm.auth.models import AuthError, LoginRequest
from pydantic import SecretStr, ValidationError

from scripts.provision_local_auth import ProvisioningError, read_password, validate_target


def test_supported_password_hash_random_salt_and_no_normalization():
    password = SecretStr(" " + new_token() + " ")
    first = PASSWORD_HASHER.hash(password.get_secret_value())
    second = PASSWORD_HASHER.hash(password.get_secret_value())
    distinct = first != second
    assert distinct
    assert PASSWORD_HASHER.type.name == "ID"
    assert verify_password(first, password.get_secret_value())
    assert not verify_password(first, password.get_secret_value().strip())
    assert not verify_password("not-a-password-hash", password.get_secret_value())


@pytest.mark.parametrize(
    "value",
    ["ab", "x" * 65, "owner@example.test", "owner/name", "оwner", "\u212aelvin", "owner\x00"],
)
def test_invalid_login_identifiers(value):
    with pytest.raises(AuthError, match="INVALID_REQUEST"):
        normalize_login(value)


def test_ascii_identifier_normalization_and_fresh_token_verifier():
    assert normalize_login("  Synthetic.Owner\t") == "synthetic.owner"
    first, second = new_token(), new_token()
    assert len(first) == 43 and len(token_verifier(first)) == 64
    changed = token_verifier(first) != token_verifier(second)
    assert changed
    check_csrf(first, csrf_value(first))
    with pytest.raises(AuthError, match="CSRF_REJECTED"):
        check_csrf(first, csrf_value(second))


@pytest.mark.parametrize(
    "origins",
    [
        (),
        ("*",),
        ("http://outside.example",),
        ("https://good.example/",),
        ("https://good.example", "http://localhost:8000"),
        ("https://user:pass@good.example",),
    ],
)
def test_rejects_untrusted_origin_configuration(origins):
    with pytest.raises(ValidationError):
        AuthSettings(auth_origins=origins)


def test_login_model_is_strict_and_redacts_password_repr():
    secret = SecretStr(new_token())
    model = LoginRequest(login="synthetic.owner", password=secret)
    hidden = secret.get_secret_value() not in repr(model)
    assert hidden
    with pytest.raises(ValidationError):
        LoginRequest(login="synthetic.owner", password=secret, role="OWNER")
    with pytest.raises(ValidationError):
        LoginRequest(login="synthetic.owner", password=SecretStr("x" * 129))


def test_rate_map_is_bounded_and_limits_survive_key_reuse():
    limiter = RateLimiter(60, capacity=2)
    limiter.consume("one", 1)
    with pytest.raises(AuthError, match="RATE_LIMITED"):
        limiter.consume("one", 1)
    limiter.consume("two", 1)
    with pytest.raises(AuthError, match="RATE_LIMITED"):
        limiter.consume("three", 1)
    assert len(limiter.buckets) == 2


async def test_cancelled_hash_does_not_release_capacity_until_real_thread_finishes():
    entered, release = threading.Event(), threading.Event()
    budget = HashBudget(1)

    def operation():
        entered.set()
        assert release.wait(3)
        return True

    task = asyncio.create_task(budget.run(operation))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pytest.raises(AuthError, match="RATE_LIMITED"):
            await budget.run(lambda: True)
    finally:
        release.set()
    async with asyncio.timeout(2):
        while budget.active:
            await asyncio.sleep(0.01)
    assert await budget.run(lambda: True)


@pytest.mark.parametrize(
    "environment,database,user",
    [
        ("PRODUCTION", "asm_local", "asm_migrator"),
        ("TEST", "asm_local", "asm_migrator"),
        ("LOCAL", "asm_test", "asm_migrator"),
        ("TEST", "asm_test", "asm_runtime"),
    ],
)
def test_provisioning_refuses_wrong_environment_database_or_identity(environment, database, user):
    with pytest.raises(ProvisioningError):
        validate_target(environment, f"postgresql+psycopg://{user}@localhost/{database}")


def test_password_file_requires_private_mode_and_rejects_symlinks(tmp_path):
    path = tmp_path / "private-input"
    secret = SecretStr(new_token())
    path.write_text(secret.get_secret_value())
    path.chmod(0o600)
    equal = read_password(path) == secret.get_secret_value()
    assert equal
    path.chmod(0o644)
    with pytest.raises(ProvisioningError):
        read_password(path)
    link = Path(tmp_path / "symlink")
    link.symlink_to(path)
    with pytest.raises(OSError):
        read_password(link)
