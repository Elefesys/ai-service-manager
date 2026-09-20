"""R4 wire primitives. No credential, contact or fingerprint logging."""

import base64
import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import AfterValidator, Field, StringConstraints

MAX_BIGINT = 9223372036854775807
UUID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
TIMESTAMP_PATTERN = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$"
KEY_PATTERN = r"^[A-Za-z0-9._:-]{1,128}$"


def _decimal_pattern(zero: bool) -> str:
    # Encode the bigint upper bound in JSON Schema as well as runtime validation.
    maximum = str(MAX_BIGINT)
    alternatives = (["0"] if zero else []) + [r"[1-9][0-9]{0,17}"]
    for index, digit in enumerate(maximum):
        low, high = (1 if index == 0 else 0), int(digit) - 1
        if low <= high:
            alternatives.append(maximum[:index] + f"[{low}-{high}]" + f"[0-9]{{{18 - index}}}")
    return "^(?:" + "|".join([*alternatives, maximum]) + ")$"


def _uuid(value: str) -> str:
    if str(UUID(value)) != value:
        raise ValueError("Invalid UUID")
    return value


def _timestamp(value: str) -> str:
    datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    return value


CanonicalUUID = Annotated[
    str,
    StringConstraints(strict=True, pattern=UUID_PATTERN),
    AfterValidator(_uuid),
    Field(json_schema_extra={"format": "uuid"}),
]
Timestamp = Annotated[
    str,
    StringConstraints(strict=True, pattern=TIMESTAMP_PATTERN),
    AfterValidator(_timestamp),
    Field(json_schema_extra={"format": "date-time"}),
]
PositiveDecimal = Annotated[
    str,
    StringConstraints(strict=True, pattern=_decimal_pattern(False), max_length=19),
    Field(description="Canonical decimal string, 1..9223372036854775807."),
]
LimitDecimal = Annotated[
    str,
    StringConstraints(strict=True, pattern=_decimal_pattern(True), max_length=19),
    Field(description="Canonical decimal string, 0..9223372036854775807."),
]
CapabilityKey = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^[a-z][a-z0-9_.:-]{0,127}$"),
]


def timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("Timezone required")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def normalize_name(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid contact")
    value = value.strip(" ")
    if not 1 <= len(value) <= 200 or any(
        ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in value
    ):
        raise ValueError("Invalid contact")
    if len(value.encode("utf-8", "strict")) > 800:
        raise ValueError("Invalid contact")
    return value


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate field")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise ValueError("Invalid JSON constant")


def strict_json(raw: bytes) -> dict[str, Any]:
    value = json.loads(
        raw.decode("utf-8", "strict"), object_pairs_hook=_pairs, parse_constant=_constant
    )
    if not isinstance(value, dict):
        raise ValueError("Object required")
    return value


def canonical_json(value: dict[str, Any], *, sort: bool = False) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=sort, separators=(",", ":"), allow_nan=False
    ).encode("utf-8", "strict")


def contact_fingerprint(workspace_id: UUID, version: str, name: str) -> bytes:
    return hashlib.sha256(
        canonical_json(
            {
                "contact_display_name": name,
                "expected_version": version,
                "operation": "UPDATE_BILLING_CONTACT",
                "workspace_id": str(workspace_id),
            },
            sort=True,
        )
    ).digest()


def encode_cursor(value: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(canonical_json(value)).rstrip(b"=").decode("ascii")


def decode_cursor(value: str) -> dict[str, Any]:
    if not 1 <= len(value) <= 1024 or re.fullmatch(r"[A-Za-z0-9_-]+", value) is None:
        raise ValueError("Invalid cursor")
    raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    result = strict_json(raw)
    if encode_cursor(result) != value:
        raise ValueError("Noncanonical cursor")
    return result
