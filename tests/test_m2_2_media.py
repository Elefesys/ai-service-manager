"""Hostile original-byte validation and bounded decoder/provider behavior."""

import asyncio
import hashlib
import struct
import threading
import zlib
from datetime import UTC, datetime, timedelta
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from asm.files.models import FetchPermit
from asm.files.provider import ControlledImageProvider
from asm.files.validation import MAX_BYTES, ImageValidator, decode_image, read_image
from asm.messaging.errors import MessagingError
from asm.messaging.results import JobClaim
from asm.messaging.worker import Worker
from PIL import Image


def image_bytes(image_format="PNG", size=(7, 5), *, animated=False, orientation=False):
    output = BytesIO()
    first = Image.new("RGB", size, (12, 92, 113))
    kwargs = {}
    if animated:
        kwargs.update(
            save_all=True,
            append_images=[Image.new("RGB", size, (172, 54, 131))],
            duration=100,
            loop=0,
        )
    if orientation:
        exif = Image.Exif()
        exif[274] = 6
        kwargs["exif"] = exif
    first.save(output, format=image_format, **kwargs)
    first.close()
    return output.getvalue()


def fetch_permit(ref="image-ref", bot="bot-a"):
    return FetchPermit(
        job_id=uuid4(),
        claim_token=uuid4(),
        workspace_id=uuid4(),
        connection_id=uuid4(),
        file_id=uuid4(),
        message_id=uuid4(),
        conversation_id=uuid4(),
        provider="CONTROLLED",
        bot_identity=bot,
        external_connection_id="connection-a",
        image_file_id=ref,
    )


@pytest.mark.parametrize(
    "image_format,mime", [("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")]
)
def test_actual_format_original_hash_dimensions_and_exif_are_preserved(image_format, mime):
    content = image_bytes(image_format, orientation=True)
    manifest = decode_image(content)
    assert manifest.mime_type == mime
    assert manifest.size_bytes == len(content)
    assert manifest.sha256 == hashlib.sha256(content).hexdigest()
    assert (manifest.width, manifest.height) == (7, 5)


@pytest.mark.parametrize("image_format", ["PNG", "WEBP", "GIF"])
def test_animated_input_is_permanently_invalid(image_format):
    with pytest.raises(MessagingError, match="INVALID_INPUT"):
        decode_image(image_bytes(image_format, animated=True))


@pytest.mark.parametrize("image_format", ["JPEG", "PNG", "WEBP"])
def test_truncated_container_or_pixel_stream_is_not_ready(image_format):
    content = image_bytes(image_format)
    for truncated in (content[: len(content) // 2], content[:-8]):
        with pytest.raises(MessagingError, match="INVALID_INPUT"):
            decode_image(truncated)


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"<svg/>\n",
        b"%PDF-1.7\n",
        b"PK\x03\x04",
        b"\x89PNG\r\n\x1a\n",
        b"RIFF\x00\x00\x00\x00WEBP",
        b"\xff\xd8\xff\xd9",
    ],
)
def test_empty_malformed_unsupported_formats_are_rejected(content):
    with pytest.raises(MessagingError, match="INVALID_INPUT"):
        decode_image(content)


def png_header(width, height):
    data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)

    def chunk(kind, value):
        body = kind + value
        return struct.pack(">I", len(value)) + body + struct.pack(">I", zlib.crc32(body))

    # Complete container framing lets Image.open expose the dimensions. Tiny
    # dummy pixel data must never be decoded for a rejected header.
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", data)
        + chunk(b"IDAT", zlib.compress(b"\0" * 4))
        + chunk(b"IEND", b"")
    )


@pytest.mark.parametrize("size", [(8193, 1), (1, 8193), (5000, 4001), (1000000, 1000000)])
def test_dimensions_and_decompression_bomb_rejected_before_pixel_allocation(size, monkeypatch):
    def forbidden_load(*args, **kwargs):
        raise AssertionError("Oversized image reached pixel allocation")

    monkeypatch.setattr(Image.Image, "load", forbidden_load)
    with pytest.raises(MessagingError, match="INVALID_INPUT"):
        decode_image(png_header(*size))


@pytest.mark.parametrize("size", [(8192, 1), (1, 8192), (4000, 5000)])
def test_exact_side_and_pixel_boundaries_can_decode(size):
    manifest = decode_image(image_bytes(size=size))
    assert (manifest.width, manifest.height) == size


def test_crc_corruption_is_rejected():
    content = bytearray(image_bytes())
    content[29] ^= 0xFF  # IHDR checksum; dimensions and IDAT remain plausible.
    with pytest.raises(MessagingError, match="INVALID_INPUT"):
        decode_image(bytes(content))


async def test_provider_metadata_is_never_authority_and_url_is_an_opaque_reference():
    provider = ControlledImageProvider(environment="TEST")
    ref = "https://169.254.169.254/latest/meta-data/never-requested"
    with pytest.raises(MessagingError, match="NOT_FOUND"):
        await read_image(provider.open_image(fetch_permit(ref)))
    content = image_bytes()
    provider.register("bot-a", ref, content, content_length=1, content_type="image/jpeg")
    actual = await read_image(provider.open_image(fetch_permit(ref)))
    assert actual == content
    assert decode_image(actual).mime_type == "image/png"
    with pytest.raises(MessagingError, match="NOT_FOUND"):
        await read_image(provider.open_image(fetch_permit(ref, bot="bot-b")))


async def test_actual_stream_cap_exact_limit_overflow_and_stream_closed():
    closed = []

    async def content_stream(extra=0):
        try:
            for _ in range(MAX_BYTES // 65536):
                yield b"x" * 65536
            if extra:
                yield b"x" * extra
        finally:
            closed.append(True)

    assert len(await read_image(content_stream())) == MAX_BYTES
    with pytest.raises(MessagingError, match="INVALID_INPUT"):
        await read_image(content_stream(1))
    assert closed == [True, True]
    provider = ControlledImageProvider(environment="TEST")
    provider.register("bot-a", "image-ref", b"x" * (MAX_BYTES + 1), content_length=1)
    with pytest.raises(MessagingError, match="INVALID_INPUT"):
        await read_image(provider.open_image(fetch_permit()))


async def test_decoder_cancellation_does_not_release_native_operation_capacity(monkeypatch):
    started = threading.Event()
    release = threading.Event()
    calls = []
    expected = decode_image(image_bytes())

    def blocked_decode(content):
        calls.append(True)
        started.set()
        assert release.wait(timeout=5)
        return expected

    monkeypatch.setattr("asm.files.validation.decode_image", blocked_decode)
    validator = ImageValidator()
    task = asyncio.create_task(validator.validate(image_bytes()))
    try:
        assert await asyncio.to_thread(started.wait, 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(validator.validate(image_bytes()), timeout=0.03)
        assert len(calls) == 1
        release.set()
        assert await asyncio.wait_for(validator.validate(image_bytes()), timeout=2) == expected
        assert len(calls) == 2
    finally:
        release.set()
        await validator.close()


async def test_explicit_fetch_dispatch_never_reaches_send():
    invocations = []

    async def send(*args):
        raise AssertionError("FETCH reached SEND")

    async def fetch(claim):
        invocations.append(claim.kind)

    db = SimpleNamespace(begin_send=send)
    worker = Worker(db, SimpleNamespace(), files=SimpleNamespace(execute=fetch))
    claim = JobClaim.model_construct(
        job_id=uuid4(),
        kind="FETCH_IMAGE",
        workspace_id=uuid4(),
        connection_id=uuid4(),
        inbox_id=None,
        outbox_id=None,
        file_id=uuid4(),
        claim_token=uuid4(),
        lease_until=datetime.now(UTC) + timedelta(seconds=30),
        correlation_id=uuid4(),
        attempt_count=1,
    )
    await worker.execute(claim)
    assert invocations == ["FETCH_IMAGE"]
    with pytest.raises(MessagingError, match="INVALID_INPUT"):
        await worker.execute(claim.model_copy(update={"kind": "FORGED_KIND"}))
