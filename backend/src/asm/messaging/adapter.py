"""Controlled adapter: every invocation/effect counts, with no hidden dedupe/retry."""

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from asm.messaging.errors import Code, MessagingError
from asm.messaging.models import OutcomeKind, SendOutcome, identifier
from asm.messaging.results import SendPermit

_VERIFIED = object()
Barrier = Callable[[str], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class TrustedSource:
    provider: str
    bot_identity: str
    _proof: object = field(repr=False)

    def validate(self) -> None:
        if self._proof is not _VERIFIED or self.provider != "CONTROLLED":
            raise MessagingError(Code.ACCESS_DENIED)
        identifier(self.bot_identity)


class ControlledAdapter:
    def __init__(
        self,
        *,
        environment: str,
        ledger: Path | None = None,
        outcome: OutcomeKind = OutcomeKind.SUCCESS,
        barrier: Barrier | None = None,
    ) -> None:
        if environment not in {"LOCAL", "TEST"} or type(outcome) is not OutcomeKind:
            raise MessagingError(Code.NOT_ALLOWED)
        self.ledger = ledger
        self.outcome = outcome
        self.barrier = barrier
        self.calls = 0
        self.effects = 0

    def source(self, bot_identity: str) -> TrustedSource:
        return TrustedSource("CONTROLLED", identifier(bot_identity), _VERIFIED)

    async def checkpoint(self, name: str) -> None:
        if self.barrier is not None:
            await self.barrier(name)

    def _record(self, kind: str) -> None:
        # File is TEST instrumentation, not a queue. It survives worker process
        # replacement; no payload/recipient/text/claim is written. Each O_APPEND
        # record is one short syscall followed by fsync before the next barrier.
        if self.ledger is not None:
            fd = os.open(self.ledger, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                raw = (json.dumps({"event": kind}) + "\n").encode("ascii")
                if os.write(fd, raw) != len(raw):
                    raise OSError("Controlled ledger write failed")
                os.fsync(fd)
            finally:
                os.close(fd)

    async def send(self, permit: SendPermit) -> SendOutcome:
        self.calls += 1
        self._record("CALL")
        await self.checkpoint("before_effect")
        if self.outcome in {OutcomeKind.SUCCESS, OutcomeKind.UNKNOWN}:
            self.effects += 1
            self._record("EFFECT")
            await self.checkpoint("after_effect")
        if self.outcome == OutcomeKind.SUCCESS:
            return SendOutcome(self.outcome, "controlled-" + str(uuid4()))
        if self.outcome == OutcomeKind.UNKNOWN:
            # No internal retry. Worker deadline/cancellation is also observable.
            await asyncio.sleep(0)
            return SendOutcome(self.outcome, error_code=Code.UNKNOWN_EXTERNAL_RESULT)
        return SendOutcome(
            self.outcome,
            error_code=(
                Code.DEPENDENCY_UNAVAILABLE
                if self.outcome == OutcomeKind.NOT_SENT_RETRYABLE
                else Code.NOT_ALLOWED
            ),
        )
