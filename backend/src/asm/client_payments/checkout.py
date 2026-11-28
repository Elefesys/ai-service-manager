"""Durable checkout processing through the ordinary messaging worker."""

from uuid import UUID

from asm.client_payments.yookassa import CheckoutRequest, TestShop, YooKassa
from asm.messaging.database import MessagingDatabase
from asm.messaging.results import JobClaim


class Checkout:
    def __init__(self, database: MessagingDatabase, provider: YooKassa) -> None:
        self.database = database
        self.provider = provider
        self.shops: dict[tuple[UUID, UUID], TestShop] = {}

    async def register(self, shops: tuple[TestShop, ...]) -> int:
        for shop in shops:
            if await self.provider.verify_shop(shop) and await self.database.register_checkout_shop(
                *shop.scope, shop.shop_id, shop.return_url
            ):
                self.shops[shop.scope] = shop
        return len(self.shops)

    async def prepare_link(self, claim: JobClaim, *, telegram_allowed: bool) -> bool:
        registered = {
            str(business): shop.shop_id
            for (workspace, business), shop in self.shops.items()
            if workspace == claim.workspace_id
        }
        operation = await self.database.checkout_provider_begin(
            claim, registered, telegram_allowed=telegram_allowed
        )
        if operation is None:
            return False
        if operation["action"] == "SEND":
            return True
        shop = self.shops[claim.workspace_id, UUID(operation["business_id"])]
        request = CheckoutRequest.from_job(operation)
        payment = await self.provider.payment(shop, request, operation["provider_id"])
        return await self.database.checkout_provider_finish(
            claim,
            {"id": payment.id, "status": payment.status, "link": payment.link} if payment else None,
        )
