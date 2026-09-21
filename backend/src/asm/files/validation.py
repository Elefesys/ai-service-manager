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

# These are process-wide immutable decoder settings in this service. WebP needs
# a header preflight too: Pillow's Image.open creates native canvas buffers.
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


def _checked_size(width: int, height: int) -> tuple[int, int]:
    if not 0 < width <= MAX_SIDE or not 0 < height <= MAX_SIDE or width * height > MAX_PIXELS:
        raise MessagingError(Code.INVALID_INPUT)
    return width, height


def _webp_bitstream_size(kind: bytes, data: memoryview) -> tuple[int, int]:
    if kind == b"VP8L":
        # Lossless signature, 14-bit width/height minus one, alpha hint, version.
        if len(data) < 5 or data[0] != 0x2F:
            raise MessagingError(Code.INVALID_INPUT)
        header = int.from_bytes(data[1:5], "little")
        if header >> 29:
            raise MessagingError(Code.INVALID_INPUT)
        return _checked_size((header & 0x3FFF) + 1, ((header >> 14) & 0x3FFF) + 1)
    # A WebP lossy frame is a displayed VP8 key frame (RFC 6386 section 9.1).
    if (
        len(data) < 10
        or data[0] & 1
        or (data[0] >> 1) & 7 > 3
        or not data[0] & 0x10
        or bytes(data[3:6]) != b"\x9d\x01\x2a"
    ):
        raise MessagingError(Code.INVALID_INPUT)
    return _checked_size(
        int.from_bytes(data[6:8], "little") & 0x3FFF,
        int.from_bytes(data[8:10], "little") & 0x3FFF,
    )


def _preflight_webp(content: bytes) -> tuple[int, int] | None:
    """Bound native canvas allocation, without replacing the full decoder.

    RIFF/VP8X/VP8L layout: developers.google.com/speed/webp/docs/riff_container
    and webp_lossless_bitstream_specification. Scan chunk boundaries in-place;
    only the native decoder validates the compressed pixel stream afterwards.
    """
    if content[:4] != b"RIFF":
        return None
    if (
        len(content) < 20
        or content[8:12] != b"WEBP"
        or int.from_bytes(content[4:8], "little") != len(content) - 8
        or content[12:16] not in (b"VP8 ", b"VP8L", b"VP8X")
    ):
        raise MessagingError(Code.INVALID_INPUT)
    data = memoryview(content)
    offset = 12
    canvas = None
    bitstream = None
    alpha = False
    while offset < len(content):
        if len(content) - offset < 8:
            raise MessagingError(Code.INVALID_INPUT)
        kind = content[offset : offset + 4]
        size = int.from_bytes(data[offset + 4 : offset + 8], "little")
        start = offset + 8
        end = start + size
        padded_end = end + (size & 1)
        if padded_end > len(content) or (size & 1 and data[end] != 0):
            raise MessagingError(Code.INVALID_INPUT)
        payload = data[start:end]
        if kind == b"VP8X":
            # First and unique; reject animation and reserved header bits.
            if offset != 12 or size != 10 or payload[0] & 0xC3 or bytes(payload[1:4]) != b"\0\0\0":
                raise MessagingError(Code.INVALID_INPUT)
            canvas = _checked_size(
                int.from_bytes(payload[4:7], "little") + 1,
                int.from_bytes(payload[7:10], "little") + 1,
            )
        elif kind in (b"ANIM", b"ANMF"):
            raise MessagingError(Code.INVALID_INPUT)
        elif kind in (b"VP8 ", b"VP8L"):
            if bitstream is not None or (alpha and kind != b"VP8 "):
                raise MessagingError(Code.INVALID_INPUT)
            bitstream = _webp_bitstream_size(kind, payload)
            if canvas is not None and canvas != bitstream:
                raise MessagingError(Code.INVALID_INPUT)
        elif kind == b"ALPH":
            # Alpha inherits the checked VP8X dimensions; it has no own canvas.
            if canvas is None or bitstream is not None or alpha or not size:
                raise MessagingError(Code.INVALID_INPUT)
            if payload[0] & 0xC0 or payload[0] & 3 > 1:
                raise MessagingError(Code.INVALID_INPUT)
            if payload[0] & 3 == 0 and size != 1 + canvas[0] * canvas[1]:
                raise MessagingError(Code.INVALID_INPUT)
            alpha = True
        # Metadata and unknown chunks cannot supply an alternate canvas. Their
        # payloads remain untouched, bounded by the original-byte limit.
        offset = padded_end
    if bitstream is None:
        raise MessagingError(Code.INVALID_INPUT)
    return bitstream


def decode_image(content: bytes) -> ImageManifest:
    """Verify the container and reopen for full pixel decode, never re-encode."""
    if type(content) is not bytes or not 0 < len(content) <= MAX_BYTES:
        raise MessagingError(Code.INVALID_INPUT)
    webp_size = _preflight_webp(content)
    try:
        with Image.open(BytesIO(content), formats=list(MIME_TYPES)) as image:
            width, height = image.size
            image_format = image.format
            _checked_size(width, height)
            if (
                image_format is None
                or image_format not in MIME_TYPES
                or (webp_size is not None and (image_format != "WEBP" or image.size != webp_size))
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
