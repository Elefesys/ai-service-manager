"""Synthetic accepted M6 work and scoped owner requests for M7.1A."""

from dataclasses import dataclass
from urllib.parse import urlencode

import pytest_asyncio
from sqlalchemy import text
from test_m6_quote_acceptance_postgres import controlled_reply, process, read, ready_two_works

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
                    "TRUNCATE app.scheduling_policy_activations,app.scheduling_policy_revisions,"
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
