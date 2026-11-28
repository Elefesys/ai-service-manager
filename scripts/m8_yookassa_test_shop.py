"""One operator-run, card-only 500 RUB TEST smoke through the YooKassa adapter."""

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
from uuid import UUID, uuid4

from asm.client_payments.yookassa import (
    CheckoutRequest,
    YooKassa,
    read_private_file,
    read_test_shops,
)


def write_private(path: Path, data: dict, *, new: bool) -> None:
    if not path.is_absolute():
        raise ValueError("The state file needs an absolute path")
    destination = path if new else path.with_name(f".{path.name}.{uuid4().hex}")
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    if not new:
        os.replace(destination, path)


async def run(args) -> int:
    shop = next(
        (
            shop
            for shop in read_test_shops(args.config_file)
            if shop.business_id == args.business_id
        ),
        None,
    )
    if shop is None:
        return 2
    provider = YooKassa(environment="TEST")
    try:
        if not await provider.verify_shop(shop):
            print("TEST_SHOP_UNVERIFIED")
            return 2
        if args.command == "create":
            attempt, key = uuid4(), uuid4()
            body = json.dumps(
                {
                    "amount": {"value": "500.00", "currency": "RUB"},
                    "capture": True,
                    "confirmation": {"type": "redirect", "return_url": shop.return_url},
                    "payment_method_data": {"type": "bank_card"},
                    "metadata": {"asm_attempt_id": str(attempt)},
                    "description": "Предоплата за визит",
                },
                ensure_ascii=False,
            )
            digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
            state = {
                "workspace_id": str(shop.workspace_id),
                "business_id": str(shop.business_id),
                "shop_id": shop.shop_id,
                "test": True,
                "attempt": str(attempt),
                "key": str(key),
                "body": body,
                "sha256": digest,
            }
            write_private(args.state_file, state, new=True)
            payment = await provider.payment(
                shop, CheckoutRequest(attempt, key, body, digest, 50_000)
            )
            if payment is None:
                print("TEST_CREATE_UNKNOWN")
                return 1
            write_private(
                args.state_file,
                state | {"payment_id": payment.id, "confirmation_url": payment.link},
                new=False,
            )
            print(f"TEST_CREATE_{payment.status.upper()} ***{payment.id[-6:]} 500.00 RUB")
            return int(payment.status != "pending" or payment.link is None)
        state = json.loads(read_private_file(args.state_file, 16_384))
        if (state["workspace_id"], state["business_id"], state["shop_id"], state["test"]) != (
            str(shop.workspace_id),
            str(shop.business_id),
            shop.shop_id,
            True,
        ) or not isinstance(state.get("payment_id"), str):
            return 2
        request = CheckoutRequest(
            UUID(state["attempt"]), UUID(state["key"]), state["body"], state["sha256"], 50_000
        )
        payment = await provider.payment(shop, request, state["payment_id"])
        if payment is None:
            print("TEST_PAYMENT_UNVERIFIED")
            return 1
        print(f"TEST_GET_{payment.status.upper()} ***{payment.id[-6:]} 500.00 RUB")
        return int(payment.status != "succeeded")
    finally:
        await provider.aclose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("create", "get"))
    parser.add_argument("--config-file", type=Path, required=True)
    parser.add_argument("--business-id", type=UUID, required=True)
    parser.add_argument("--state-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = asyncio.run(run(args))
        if result == 2:
            print("TEST_SHOP_INPUT_REFUSED")
        return result
    except (OSError, ValueError, TypeError, KeyError):
        print("TEST_SHOP_INPUT_REFUSED")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
