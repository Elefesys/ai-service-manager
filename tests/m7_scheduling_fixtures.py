"""Synthetic M6 agreements and scoped owner requests for scheduling proof."""

from dataclasses import dataclass
from urllib.parse import urlencode

import pytest_asyncio
from asm.messaging.worker import Worker
from asm.scheduling.commands import TrustedSchedulingClient
from asm.scheduling.service import SelectedSession
from sqlalchemy import text
from test_m5_intake_postgres import application, next_turn, summary
from test_m6_owner_decisions_postgres import FIXED_DURATION, contract
from test_m6_pricing_postgres import draft_for_size, formula_price, price, publish, sign_in
from test_m6_quote_acceptance_postgres import controlled_reply, process, read
from test_m6_quote_delivery_postgres import DeliveryWire, run_quote
from test_m6_service_assessments_api_postgres import create_draft, request_assessment
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
                    "TRUNCATE platform.scheduling_chat_codes,platform.scheduling_turn_actions,"
                    "platform.scheduling_command_receipts,app.appointments,app.reservation_holds,"
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

    def booking_url(self, **overrides):
        return self.preview_url(**overrides).replace("/availability?", "/booking?")

    def proof(self):
        return {
            "request_id": self.material["request_id"],
            "quote_id": self.agreement["quote"]["quote_id"],
            "order_id": self.agreement["order_id"],
            "session_id": self.agreement["session_id"],
            "duration_reference_id": self.material["duration_reference_id"],
        }


def booking_contract(mode):
    terms = {
        "NONE": (None, None),
        "FIXED_DEPOSIT": (50_000, None),
        "PERCENT_DEPOSIT": (None, 20),
        "FULL_PREPAYMENT": (None, None),
    }
    amount, percent = terms[mode]
    published = contract(formula_price(), FIXED_DURATION)
    published["services"][0]["deposit"] = {"mode": mode, "amount_minor": amount, "percent": percent}
    return published


async def prepare_quote(harness, auth, token, url):
    await price(auth, url + "/pricing", token)
    await request_assessment(auth, url + "/assessment", token)
    quote = (await read(harness, auth, url))["quote"]
    await run_quote(harness, Worker(harness.kernel, DeliveryWire(harness)), quote)
    return quote


async def accept_quote(harness, auth, url, quote):
    receipt = await controlled_reply(harness, f"Принимаю {quote['code']}")
    assert (await process(harness, receipt)).quote_reply.outcome == "ACCEPTED"
    return Work(url, (await read(harness, auth, url))["agreement"])


async def draft_work_pair(harness, auth, first_mode, *, titles=None):
    await publish(harness, booking_contract(first_mode))
    token = await sign_in(auth)
    if titles is None:
        conversation, intake, model, _, request = await draft_for_size(
            harness, auth, token, "20 mm"
        )
    else:
        facts = dict(
            idea=titles[0], placement="forearm", approximate_size="20 mm", style="linework"
        )
        conversation, intake, model, _, _ = await application(
            harness, facts, message_text=" ".join(facts.values())
        )
        request = await create_draft(
            auth, conversation, token, await summary(harness, conversation)
        )
    left_url = f"{route(conversation)}/{request}"
    left_quote = await prepare_quote(harness, auth, token, left_url)
    model.values = {
        "idea": "swallow" if titles is None else titles[1],
        "placement": "shoulder",
        "approximate_size": "21 mm",
        "style": "linework",
    }
    model.switch = True
    await next_turn(harness, intake, "Separate " + " ".join(model.values.values()))
    other = await create_draft(auth, conversation, token, await summary(harness, conversation))
    return token, left_url, left_quote, f"{route(conversation)}/{other}"


async def prepare_pair(harness, auth):
    token, left_url, left_quote, right_url = await draft_work_pair(harness, auth, "FIXED_DEPOSIT")
    return (
        token,
        left_url,
        left_quote,
        right_url,
        await prepare_quote(harness, auth, token, right_url),
    )


async def accept_pair(harness, auth, prepared=None):
    token, left_url, left_quote, right_url, right_quote = prepared or await prepare_pair(
        harness, auth
    )
    right = await accept_quote(harness, auth, right_url, right_quote)
    left = await accept_quote(harness, auth, left_url, left_quote)
    return token, left, right


async def accept_pair_with_modes(harness, auth, first_mode, second_mode, *, titles=None):
    token, left_url, left_quote, right_url = await draft_work_pair(
        harness, auth, first_mode, titles=titles
    )
    left = await accept_quote(harness, auth, left_url, left_quote)
    if second_mode != first_mode:
        await publish(harness, booking_contract(second_mode))
    right_quote = await prepare_quote(harness, auth, token, right_url)
    right = await accept_quote(harness, auth, right_url, right_quote)
    return token, left, right


async def accept_work(harness, auth, token, size):
    conversation, _, _, _, request = await draft_for_size(harness, auth, token, size)
    url = f"{route(conversation)}/{request}"
    quote = await prepare_quote(harness, auth, token, url)
    return await accept_quote(harness, auth, url, quote)


async def accept_two_clients(harness, auth, *, first_mode="FIXED_DEPOSIT", second_mode=None):
    await publish(harness, booking_contract(first_mode))
    token = await sign_in(auth)
    a = await accept_work(harness, auth, token, "20 mm")
    if second_mode is not None:
        await publish(harness, booking_contract(second_mode))
    b = await accept_work(harness, auth, token, "21 mm")
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
