"""The TEST-only YooKassa API boundary. No provider payloads are logged."""

import asyncio
import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from asm.telegram.client import suppress_transport_logs

API = "https://api.yookassa.ru/v3/"
CHECKOUT_HOSTS = {"yookassa.ru", "yoomoney.ru"}
PAYMENT_ID = re.compile(r"[a-zA-Z0-9_-]{1,64}", re.ASCII)
PAYMENT_STATUS = Literal["pending", "canceled", "succeeded", "waiting_for_capture"]


def read_private_file(path: Path, limit: int) -> str:
    if not path.is_absolute():
        raise ValueError("TEST shop file requires an absolute path")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o077
            or not 1 <= info.st_size <= limit
        ):
            raise ValueError("TEST shop file must be private")
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("TEST shop file is too large")
    return raw.decode("utf-8")


def rubles(minor: int) -> str:
    units, kopecks = divmod(minor, 100)
    return f"{units}.{kopecks:02}"


def https_parts(url: str):
    if not 1 <= len(url) <= 2048 or not url.isascii() or re.search(r"[\x00-\x20\x7f\\]", url):
        raise ValueError("Invalid HTTPS URL")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
        or parsed.fragment
    ):
        raise ValueError("Invalid HTTPS origin")
    return parsed


def checkout_url(value: object) -> str | None:
    if type(value) is not str:
        return None
    try:
        parts = https_parts(value)
    except ValueError:
        return None
    if parts.hostname not in CHECKOUT_HOSTS or not value.startswith(f"https://{parts.netloc}/"):
        return None
    authority = parts.hostname + (":443" if parts.port is not None else "")
    return value if parts.netloc == authority else None


@dataclass(frozen=True, slots=True)
class TestShop:
    __test__ = False

    workspace_id: UUID
    business_id: UUID
    shop_id: str
    return_url: str
    secret: str = field(repr=False)

    def __post_init__(self) -> None:
        url = https_parts(self.return_url)
        if (
            not re.fullmatch(r"[0-9]{1,20}", self.shop_id)
            or url.path != "/payment-return"
            or url.query
            or not re.fullmatch(r"test_[a-zA-Z0-9_+=/-]{8,256}", self.secret)
        ):
            raise ValueError("Invalid YooKassa TEST shop configuration")

    @property
    def scope(self) -> tuple[UUID, UUID]:
        return self.workspace_id, self.business_id


def read_test_shops(config_file: Path) -> tuple[TestShop, ...]:
    try:
        config = json.loads(read_private_file(config_file, 16_384))
        if type(config) is not list or not 1 <= len(config) <= 32:
            raise ValueError
        shops: list[TestShop] = []
        for item in config:
            if (
                type(item) is not dict
                or set(item)
                != {
                    "workspace_id",
                    "business_id",
                    "confirmed_test_shop_id",
                    "return_url",
                    "secret_file",
                    "receipt_required",
                }
                or item["receipt_required"] is not False
            ):
                raise ValueError
            shop = TestShop(
                UUID(item["workspace_id"]),
                UUID(item["business_id"]),
                item["confirmed_test_shop_id"],
                item["return_url"],
                read_private_file(Path(item["secret_file"]), 512).strip(),
            )
            shops.append(shop)
        if len({shop.scope for shop in shops}) != len(shops) or len(
            {shop.shop_id for shop in shops}
        ) != len(shops):
            raise ValueError
    except (OSError, TypeError, ValueError, AttributeError):
        raise ValueError("Invalid YooKassa TEST shop configuration") from None
    return tuple(shops)


@dataclass(frozen=True, slots=True)
class CheckoutRequest:
    attempt_id: UUID
    idempotence_key: UUID = field(repr=False)
    body: str = field(repr=False)
    sha256: str
    amount_minor: int

    @classmethod
    def from_job(cls, data: dict) -> "CheckoutRequest":
        return cls(
            UUID(data["attempt_id"]),
            UUID(data["idempotence_key"]),
            data["request_body"],
            data["request_sha256"],
            data["amount_minor"],
        )

    def valid(self, shop: TestShop) -> bool:
        try:
            data = json.loads(self.body)
        except ValueError:
            return False
        return (
            type(self.amount_minor) is int
            and self.amount_minor >= 100
            and hashlib.sha256(self.body.encode("utf-8")).hexdigest() == self.sha256
            and data
            == {
                "amount": {"value": rubles(self.amount_minor), "currency": "RUB"},
                "capture": True,
                "confirmation": {"type": "redirect", "return_url": shop.return_url},
                "payment_method_data": {"type": "bank_card"},
                "metadata": {"asm_attempt_id": str(self.attempt_id)},
                "description": "Предоплата за визит",
            }
            and data["capture"] is True
        )


@dataclass(frozen=True, slots=True)
class ProviderPayment:
    id: str
    status: PAYMENT_STATUS
    link: str | None = field(repr=False)


class YooKassa:
    def __init__(self, *, environment: str, transport: httpx.MockTransport | None = None):
        if environment != "TEST" or (
            transport is not None and type(transport) is not httpx.MockTransport
        ):
            raise ValueError("Checkout requires TEST")
        suppress_transport_logs()
        self.http = httpx.AsyncClient(
            base_url=API,
            transport=transport,
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(5),
            headers={"Accept-Encoding": "identity"},
        )

    async def aclose(self) -> None:
        await self.http.aclose()

    async def _request(
        self,
        shop: TestShop,
        method: str,
        path: str,
        *,
        body: str | None = None,
        key: UUID | None = None,
    ) -> dict | None:
        headers = {"Idempotence-Key": str(key), "Content-Type": "application/json"} if key else {}
        try:
            async with (
                asyncio.timeout(8),
                self.http.stream(
                    method,
                    path,
                    auth=(shop.shop_id, shop.secret),
                    content=body.encode("utf-8") if body is not None else None,
                    headers=headers,
                ) as response,
            ):
                if response.status_code not in (200, 201):
                    return None
                if response.headers.get("content-encoding", "identity").lower() != "identity":
                    return None
                raw = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    raw.extend(chunk)
                    if len(raw) > 65536:
                        return None
                value = json.loads(raw)
                return value if type(value) is dict else None
        except (TimeoutError, httpx.HTTPError, ValueError):
            # A lost response, including HTTP 500, may follow a real payment creation.
            return None

    @staticmethod
    def _belongs_to_test_shop(shop: TestShop, value: dict) -> bool:
        recipient = value.get("recipient")
        return (
            value.get("test") is True
            and type(recipient) is dict
            and recipient.get("account_id") == shop.shop_id
        )

    async def verify_shop(self, shop: TestShop) -> bool:
        # An empty list verifies credentials only. TEST also requires the
        # operator's confirmed shop ID and a TEST key in the protected manifest.
        raw = await self._request(shop, "GET", "payments?limit=1")
        return (
            raw is not None
            and raw.get("type") == "list"
            and type(raw.get("items")) is list
            and all(
                type(item) is dict and self._belongs_to_test_shop(shop, item)
                for item in raw["items"]
            )
        )

    async def payment(
        self, shop: TestShop, request: CheckoutRequest, provider_id: str | None = None
    ) -> ProviderPayment | None:
        if not request.valid(shop):
            return None
        if provider_id is None:
            value = await self._request(
                shop, "POST", "payments", body=request.body, key=request.idempotence_key
            )
        elif PAYMENT_ID.fullmatch(provider_id):
            value = await self._request(shop, "GET", f"payments/{provider_id}")
        else:
            return None
        if value is None or not self._belongs_to_test_shop(shop, value):
            return None
        payment_id = value.get("id")
        status = value.get("status")
        metadata = value.get("metadata")
        if (
            type(payment_id) is not str
            or not PAYMENT_ID.fullmatch(payment_id)
            or (provider_id is not None and payment_id != provider_id)
            or value.get("amount") != {"value": rubles(request.amount_minor), "currency": "RUB"}
            or type(metadata) is not dict
            or metadata.get("asm_attempt_id") != str(request.attempt_id)
            or status not in ("pending", "canceled", "succeeded", "waiting_for_capture")
            or value.get("paid") is not (status in ("succeeded", "waiting_for_capture"))
        ):
            return None
        confirmation = value.get("confirmation")
        link = (
            checkout_url(confirmation.get("confirmation_url"))
            if status == "pending"
            and type(confirmation) is dict
            and confirmation.get("type") == "redirect"
            else None
        )
        return ProviderPayment(payment_id, status, link)
