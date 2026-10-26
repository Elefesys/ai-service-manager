"""Real canonical HTTP/PG ingress; provider queue is a controlled model, not Telegram."""

import httpx
import pytest
from asm.messaging.database import MessagingDatabase
from asm.telegram.database import TelegramIngress
from asm.telegram.webhook import install_webhook
from fastapi import FastAPI
from sqlalchemy.exc import SQLAlchemyError
from test_m2_1_postgres import messaging as messaging
from test_m2_1_postgres import query
from test_m2_3_transport import BOT, SECRET, config, update
from test_m2_3_wire_postgres import telegram_case as telegram_case
from test_tenancy_postgres import A
from test_tenancy_postgres import db as db
from test_tenancy_postgres import seeded as seeded

from scripts.telegram_polling_receiver import LocalIngress, PollingError, Receiver

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("stage", ["telegram_ingest_before_commit", "telegram_ingest_after_commit"])
async def test_polling_confirmation_requires_real_commit_and_replay_has_one_effect(
    telegram_case, stage
):
    h, fail = telegram_case, True

    async def barrier(name):
        if fail and name == stage:
            raise SQLAlchemyError("SYNTHETIC_ACK_LOSS")

    app = FastAPI()
    ingress = TelegramIngress(MessagingDatabase(h.runtime.engine, barrier=barrier), str(BOT))
    install_webhook(app, config(), ingress)
    raw, offsets = update(), []

    class Queue:
        waiting = True

        async def poll(self, offset):
            offsets.append(offset)
            if offset is not None:
                # Provider acknowledgement is allowed only after a committed
                # receipt is visible from another PostgreSQL transaction.
                assert offset == raw["update_id"] + 1
                rows = await query(
                    h,
                    "SELECT id FROM platform.telegram_update_receipts WHERE workspace_id=:ws",
                    ws=A,
                )
                assert len(rows) == 1
                self.waiting = False
            return [raw] if self.waiting else []

    queue = Queue()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as client:
        local = LocalIngress(client, SECRET)
        receiver = Receiver(queue, local, lambda _: None)
        with pytest.raises(PollingError, match="LOCAL_INGRESS_REJECTED"):
            await receiver.step()
        assert queue.waiting and offsets == [None]
        for table in (
            "platform.telegram_update_receipts",
            "platform.inbox_events",
            "platform.messaging_jobs",
        ):
            rows = await query(h, f"SELECT id FROM {table} WHERE workspace_id=:ws", ws=A)
            assert len(rows) == int(stage.endswith("after_commit"))
        fail = False
        receiver = Receiver(queue, local, lambda _: None)
        await receiver.step()
        # A process restart after the local commit replays the same update.
        receiver = Receiver(queue, local, lambda _: None)
        await receiver.step()
        await receiver.step()
        assert offsets == [None, None, None, raw["update_id"] + 1]
        assert not queue.waiting
    for table in (
        "platform.telegram_update_receipts",
        "platform.inbox_events",
        "platform.messaging_jobs",
    ):
        assert len(await query(h, f"SELECT id FROM {table} WHERE workspace_id=:ws", ws=A)) == 1
    assert await h.worker.run_once()
    assert (
        len(
            await query(
                h, "SELECT id FROM app.messages WHERE connection_id=:id", id=h.telegram_connection
            )
        )
        == 1
    )
