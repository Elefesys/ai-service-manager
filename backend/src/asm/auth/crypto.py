"""Standard primitives and supported high-level password hashing; no identity claims."""

import asyncio
import hashlib
import hmac
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from time import monotonic
from typing import TypeVar

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError

from asm.auth.models import AuthCode, AuthError

PASSWORD_HASHER = PasswordHasher(
    time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16, type=Type.ID
)
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}\Z", re.ASCII)
LOGIN_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]{2,63}\Z", re.ASCII)
T = TypeVar("T")


def normalize_login(value: str) -> str:
    normalized = value.strip(" \t\r\n").lower()
    if not value.isascii() or not LOGIN_PATTERN.fullmatch(normalized):
        raise AuthError(AuthCode.INVALID_REQUEST, 422)
    return normalized


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_verifier(token: str) -> str:
    if not TOKEN_PATTERN.fullmatch(token):
        raise AuthError(AuthCode.SESSION_REQUIRED, 401)
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def csrf_value(token: str) -> str:
    token_verifier(token)
    return hmac.new(token.encode("ascii"), b"asm.csrf.v1", hashlib.sha256).hexdigest()


def check_csrf(token: str, supplied: str | None) -> None:
    if (
        supplied is None
        or len(supplied) != 64
        or not hmac.compare_digest(csrf_value(token).encode("ascii"), supplied.encode("utf-8"))
    ):
        raise AuthError(AuthCode.CSRF_REJECTED, 403)


def verify_password(encoded: str, password: str) -> bool:
    try:
        return PASSWORD_HASHER.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


class HashBudget:
    """No queue; cancelled requests do not release capacity while a thread still runs."""

    def __init__(self, maximum: int) -> None:
        self.maximum = maximum
        self.active = 0

    async def run(self, operation: Callable[[], T]) -> T:
        if self.active >= self.maximum:
            raise AuthError(AuthCode.RATE_LIMITED, 429)
        self.active += 1
        task = asyncio.create_task(asyncio.to_thread(operation))

        def finished(completed: asyncio.Task[T]) -> None:
            self.active -= 1
            if not completed.cancelled():
                # Retrieve failures even when the request was cancelled, without logging secrets.
                completed.exception()

        task.add_done_callback(finished)
        return await asyncio.shield(task)


@dataclass
class RateLimiter:
    """Bounded process-local abuse control, NOT canonical auth/session state."""

    window_seconds: int
    capacity: int = 1024
    buckets: dict[str, tuple[float, int]] = field(default_factory=dict, repr=False)

    def consume(self, key: str, limit: int) -> None:
        now = monotonic()
        self.buckets = {k: v for k, v in self.buckets.items() if now - v[0] < self.window_seconds}
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        if digest not in self.buckets and len(self.buckets) >= self.capacity:
            raise AuthError(AuthCode.RATE_LIMITED, 429)
        start, count = self.buckets.get(digest, (now, 0))
        if count >= limit:
            raise AuthError(AuthCode.RATE_LIMITED, 429)
        self.buckets[digest] = (start, count + 1)
