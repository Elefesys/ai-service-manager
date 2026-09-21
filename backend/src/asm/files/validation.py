"""Actual-byte caps and full single-frame decode, preserving the original bytes."""

import asyncio
import hashlib
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from typing import Literal

from PIL import Image, ImageFile, UnidentifiedImageError

from asm.files.models import ImageManifest
from asm.messaging.errors import Code, MessagingError

MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 20_000_000
MAX_SIDE = 8192
MIME_TYPES: dict[str, Literal["image/jpeg", "image/png", "image/webp"]] = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}

# These are process-wide immutable decoder settings in this service. A decode
# still checks our smaller explicit pixel/side limits before allocating pixels.
Image.MAX_IMAGE_PIXELS = MAX_PIXELS
ImageFile.LOAD_TRUNCATED_IMAGES = False


async def read_image(stream: AsyncIterator[bytes]) -> bytes:
    """Keep at most 10 MiB of originals; no temporary files survive a crash."""
    content = bytearray()
    # Provider iterators own no persistent authority. Always close a stream that
    # offers aclose(), including on overflow or cancellation.
    try:
        async for chunk in stream:
            if type(chunk) is not bytes or not chunk or len(content) + len(chunk) > MAX_BYTES:
                raise MessagingError(Code.INVALID_INPUT)
            content.extend(chunk)
        if not content:
            raise MessagingError(Code.INVALID_INPUT)
        return bytes(content)
    finally:
        close = getattr(stream, "aclose", None)
        if close is not None:
            await close()


def decode_image(content: bytes) -> ImageManifest:
    """Verify the container and reopen for full pixel decode, never re-encode."""
    if type(content) is not bytes or not 0 < len(content) <= MAX_BYTES:
        raise MessagingError(Code.INVALID_INPUT)
    try:
        with Image.open(BytesIO(content), formats=list(MIME_TYPES)) as image:
            width, height = image.size
            image_format = image.format
            if (
                image_format is None
                or image_format not in MIME_TYPES
                or not 0 < width <= MAX_SIDE
                or not 0 < height <= MAX_SIDE
                or width * height > MAX_PIXELS
                or getattr(image, "n_frames", 1) != 1
                or getattr(image, "is_animated", False)
            ):
                raise MessagingError(Code.INVALID_INPUT)
            image.verify()
        with Image.open(BytesIO(content), formats=list(MIME_TYPES)) as decoded:
            decoded.load()
            if decoded.size != (width, height) or decoded.format != image_format:
                raise MessagingError(Code.INVALID_INPUT)
    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        OSError,
        ValueError,
        SyntaxError,
        EOFError,
    ):
        raise MessagingError(Code.INVALID_INPUT) from None
    return ImageManifest(
        mime_type=MIME_TYPES[image_format],
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        width=width,
        height=height,
    )


class ImageValidator:
    """One decoder at a time, including after cancellation of its async caller."""

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="image-decode")
        self._slot = asyncio.Semaphore(1)
        self._closed = False
        self._pending: set[asyncio.Future[ImageManifest]] = set()

    async def validate(self, content: bytes) -> ImageManifest:
        if self._closed:
            raise MessagingError(Code.DEPENDENCY_UNAVAILABLE)
        await self._slot.acquire()
        if self._closed:
            self._slot.release()
            raise MessagingError(Code.DEPENDENCY_UNAVAILABLE)
        future = asyncio.get_running_loop().run_in_executor(self._executor, decode_image, content)
        self._pending.add(future)

        def done(result: asyncio.Future[ImageManifest]) -> None:
            self._pending.discard(result)
            self._slot.release()
            # Retrieve a late failure when its timed-out caller no longer awaits.
            if not result.cancelled():
                result.exception()

        future.add_done_callback(done)
        # Shield keeps the slot until the actual decoder exits. A timed-out
        # caller cannot queue an unbounded number of native decoder operations.
        return await asyncio.shield(future)

    async def close(self) -> None:
        self._closed = True
        self._executor.shutdown(wait=False, cancel_futures=True)
