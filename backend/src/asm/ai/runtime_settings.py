"""Operator-owned finite test admission. Loading a key never enables a session."""

import os
import stat
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, SecretStr, model_validator

from asm.ai.contracts import DTO, GatewayConfig, Limits, Money
from asm.ai.polza import RuntimeRoute, fingerprint


class RuntimeSettings(DTO):
    session_id: UUID
    workspace_id: UUID
    client_id: UUID
    conversation_id: UUID
    connection_id: UUID
    chat_id: str = Field(pattern=r"^[1-9][0-9]{0,18}$", repr=False)
    bot_identity: str = Field(pattern=r"^[1-9][0-9]{0,18}$")
    data_profile: Literal["SYNTHETIC_TEXT_V1"]
    starts_at: datetime
    expires_at: datetime
    max_calls: int = Field(ge=1, le=4)
    max_rub: Money
    review: RuntimeRoute
    review_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def finite_reviewed_test(self) -> Self:
        if (
            self.starts_at.tzinfo is None
            or self.expires_at.tzinfo is None
            or not 0 < (self.expires_at - self.starts_at).total_seconds() <= 900
            or not Decimal(0) < self.max_rub <= Decimal(10)
            or self.review_sha256 != fingerprint(self.review.model_dump(mode="json"))
            or self.review.reservation() * self.max_calls > self.max_rub
        ):
            raise ValueError("RUNTIME_ADMISSION_INVALID")
        self.review.route()
        return self

    def current(self) -> None:
        self.review.fresh()
        if not self.starts_at <= datetime.now(UTC) < self.expires_at:
            raise ValueError("RUNTIME_SESSION_EXPIRED")

    def gateway(self) -> GatewayConfig:
        return GatewayConfig(
            revision="polza-" + str(self.session_id) + "-" + self.review_sha256,
            route=self.review.route(),
            prompt_revision="conversation_v2",
            schema_revision="conversation_result_v1",
            limits=Limits(
                model_calls=2,
                read_executions=1,
                input_bytes=24576,
                output_bytes=32768,
                input_tokens=32768,
                output_tokens=512,
                total_tokens=66560,
                duration_seconds=120.0,
                currency="RUB",
                cost_budget=min(self.max_rub, self.review.reservation() * 2),
                call_cost_reservation=self.review.reservation(),
            ),
        )

    def admission(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"review"}) | {
            "config": self.gateway().model_dump(mode="json"),
            "review_checked_at": self.review.checked_at.isoformat(),
        }


def private_bytes(path: Path, maximum: int) -> bytes:
    """No symlink, shared-mode, non-owner or unbounded source; no path in errors."""
    descriptor = -1
    try:
        if not path.is_absolute():
            raise ValueError
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) & 0o077
            or not 0 < info.st_size <= maximum
        ):
            raise ValueError
        value = os.read(descriptor, maximum + 1)
        if len(value) > maximum:
            raise ValueError
        return value
    except (OSError, ValueError):
        raise ValueError("PRIVATE_RUNTIME_SOURCE_INVALID") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def load_settings(path: Path) -> RuntimeSettings:
    try:
        return RuntimeSettings.model_validate_json(private_bytes(path, 32768))
    except Exception:
        raise ValueError("RUNTIME_CONFIG_INVALID") from None


def load_key(path: Path) -> SecretStr:
    try:
        key = private_bytes(path, 512).decode("ascii").removesuffix("\n")
        if not 16 <= len(key) <= 256 or any(ord(c) < 33 or ord(c) > 126 for c in key):
            raise ValueError
        return SecretStr(key)
    except Exception:
        raise ValueError("RUNTIME_SECRET_INVALID") from None
