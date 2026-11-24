"""Synthetic accepted M6 work and scoped owner requests for M7.1A."""

from dataclasses import dataclass
from urllib.parse import urlencode

import pytest_asyncio
from asm.messaging.worker import Worker
from asm.scheduling.commands import TrustedSchedulingClient
from asm.scheduling.service import SelectedSession
from sqlalchemy import text
from test_m6_owner_decisions_postgres import FIXED_DURATION, contract
from test_m6_pricing_postgres import draft_for_size, formula_price, price, publish, sign_in
from test_m6_quote_acceptance_postgres import controlled_reply, process, read, ready_two_works
from test_m6_quote_delivery_postgres import DeliveryWire, run_quote
from test_m6_service_assessments_api_postgres import request_assessment
from test_m6_service_requests_api_postgres import route

ZONE = "Asia/Novosibirsk"
WEEK = [{"weekday": weekday, "start_minute": 600, "end_minute": 720} for weekday in range(7)]
POLICY = {
    "action": "policy",
    "step_minutes": 15,
    "buffer_before_minutes": 10,
    "buffer_after_minutes": 5,
    "minimum_notice_minutes": 30,
    "horizon_days": 14,
    "offer_ttl_minutes": 10,
    "hold_ttl_minutes": 15,
}


@pytest_asyncio.fixture
async def scheduling_pg(approval_pg):
    try:
        yield approval_pg
    finally:
        async with approval_pg.migrator.begin() as connection:
            await connection.execute(
                text(
                    "TRUNCATE platform.scheduling_command_receipts,app.reservation_holds,"
                    "app.resource_allocations,app.availability_options,app.availability_offers,"
                    "app.scheduling_policy_activations,app.scheduling_policy_revisions,"
                    "app.availability_rules,app.availability_overrides,app.scheduling_resources"
                )
            )


@dataclass(frozen=True)
class Work:
    url: str
    agreement: dict

    @property
    def material(self):
        return self.agreement["quote"]["material"]

    @property
    def selection(self):
        return SelectedSession(
            **{
                field: self.material[field]
                for field in (
                    "workspace_id",
                    "business_id",
                    "conversation_id",
                    "client_id",
                    "request_id",
                )
            },
            quote_id=self.agreement["quote"]["quote_id"],
            order_id=self.agreement["order_id"],
            session_id=self.agreement["session_id"],
        )

    @property
    def identity(self):
        return TrustedSchedulingClient.model_validate(
            self.selection.model_dump(include=set(TrustedSchedulingClient.model_fields))
        )

    def preview_url(self, *, day=None, **overrides):
        refs = {
            "client_id": self.material["client_id"],
            "quote_id": self.agreement["quote"]["quote_id"],
            "order_id": self.agreement["order_id"],
        }
        refs.update(overrides)
        session = refs.pop("session_id", self.agreement["session_id"])
        workspace = refs.pop("workspace_id", self.material["workspace_id"])
        business = refs.pop("business_id", self.material["business_id"])
        if day is not None:
            refs["date"] = day
        endpoint = self.url.replace(
            f"/workspaces/{self.material['workspace_id']}/businesses/{self.material['business_id']}/",
            f"/workspaces/{workspace}/businesses/{business}/",
        )
        return f"{endpoint}/sessions/{session}/availability?{urlencode(refs)}"

    def proof(self):
        return {
            "request_id": self.material["request_id"],
            "quote_id": self.agreement["quote"]["quote_id"],
            "order_id": self.agreement["order_id"],
            "session_id": self.agreement["session_id"],
            "duration_reference_id": self.material["duration_reference_id"],
        }


async def accept_pair(harness, auth, prepared=None):
    token, left_url, left_quote, right_url, right_quote = (
        prepared if prepared is not None else await ready_two_works(harness, auth)
    )
    for quote in (right_quote, left_quote):
        receipt = await controlled_reply(harness, f"Принимаю {quote['code']}")
        assert (await process(harness, receipt)).quote_reply.outcome == "ACCEPTED"
    left = Work(left_url, (await read(harness, auth, left_url))["agreement"])
    right = Work(right_url, (await read(harness, auth, right_url))["agreement"])
    return token, left, right


async def accept_two_clients(harness, auth):
    await publish(harness, contract(formula_price(), FIXED_DURATION))
    token = await sign_in(auth)
    works = []
    for size in ("20 mm", "21 mm"):
        conversation, _, _, _, request = await draft_for_size(harness, auth, token, size)
        url = f"{route(conversation)}/{request}"
        await price(auth, url + "/pricing", token)
        await request_assessment(auth, url + "/assessment", token)
        quote = (await read(harness, auth, url))["quote"]
        await run_quote(harness, Worker(harness.kernel, DeliveryWire(harness)), quote)
        receipt = await controlled_reply(harness, f"Принимаю {quote['code']}")
        assert (await process(harness, receipt)).quote_reply.outcome == "ACCEPTED"
        works.append(Work(url, (await read(harness, auth, url))["agreement"]))
    a, b = works
    assert a.identity.client_id != b.identity.client_id
    assert a.identity.conversation_id != b.identity.conversation_id
    assert a.identity.business_id == b.identity.business_id
    return token, a, b


async def remove_historical_duration(connection, workspace_id, quote_id):
    """Emulate an accepted Quote from before duration was captured."""
    await connection.execute(text("ALTER TABLE app.quotes DISABLE TRIGGER quote_immutable"))
    result = await connection.execute(
        text("""
        UPDATE app.quotes SET material=material-'occupied_minutes'-'duration_reference_id'
        WHERE (workspace_id,id)=(:ws,CAST(:id AS uuid))
        """),
        {"ws": workspace_id, "id": quote_id},
    )
    await connection.execute(text("ALTER TABLE app.quotes ENABLE TRIGGER quote_immutable"))
    assert result.rowcount == 1
