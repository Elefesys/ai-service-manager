"""Controlled opaque media references; no URL fetching or trusted provider headers."""

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Protocol

from asm.files.models import FetchPermit
from asm.messaging.adapter import Barrier
from asm.messaging.errors import Code, MessagingError
from asm.messaging.models import identifier


class ImageProvider(Protocol):
    def open_image(self, permit: FetchPermit) -> AsyncIterator[bytes]: ...


@dataclass(frozen=True, slots=True)
class ControlledImage:
    content: bytes = field(repr=False)
    # Fault fixtures may supply lies. Neither field is used as authority.
    content_length: int | None = None
    content_type: str | None = None


class ControlledImageProvider:
    """LOCAL/TEST byte fixtures keyed by exact bot/ref, never by a parsed URL."""

    def __init__(
        self,
        *,
        environment: str,
        images: Mapping[tuple[str, str], ControlledImage] | None = None,
        barrier: Barrier | None = None,
    ) -> None:
        if environment not in {"LOCAL", "TEST"}:
            raise MessagingError(Code.NOT_ALLOWED)
        self._images = dict(images or {})
        self.barrier = barrier
        self.calls = 0

    def register(
        self,
        bot_identity: str,
        image_file_id: str,
        content: bytes,
        *,
        content_length: int | None = None,
        content_type: str | None = None,
    ) -> None:
        identifier(bot_identity)
        identifier(image_file_id, image=True)
        if type(content) is not bytes:
            raise MessagingError(Code.INVALID_INPUT)
        self._images[bot_identity, image_file_id] = ControlledImage(
            content, content_length, content_type
        )

    async def _checkpoint(self, name: str) -> None:
        if self.barrier is not None:
            await self.barrier(name)

    async def open_image(self, permit: FetchPermit) -> AsyncIterator[bytes]:
        if type(permit) is not FetchPermit or permit.provider != "CONTROLLED":
            raise MessagingError(Code.ACCESS_DENIED)
        self.calls += 1
        await self._checkpoint("image_before_open")
        image = self._images.get((permit.bot_identity, permit.image_file_id))
        if image is None:
            raise MessagingError(Code.NOT_FOUND)
        for offset in range(0, len(image.content), 65536):
            await self._checkpoint("image_before_read")
            yield image.content[offset : offset + 65536]
        await self._checkpoint("image_after_read")


class ChannelImageProvider:
    """Only the two currently accepted provider paths, using DB-issued permits."""

    def __init__(self, controlled: ControlledImageProvider, telegram: ImageProvider | None) -> None:
        self.controlled, self.telegram = controlled, telegram

    async def open_image(self, permit: FetchPermit) -> AsyncIterator[bytes]:
        if permit.provider == "CONTROLLED":
            provider: ImageProvider = self.controlled
        elif permit.provider == "TELEGRAM" and self.telegram is not None:
            provider = self.telegram
        else:
            raise MessagingError(Code.DEPENDENCY_UNAVAILABLE)
        async for chunk in provider.open_image(permit):
            yield chunk
