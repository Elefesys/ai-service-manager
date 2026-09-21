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
from PIL import Image, _webp


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


def webp_container(*chunks):
    payload = b"WEBP" + b"".join(
        kind + struct.pack("<I", len(data)) + data + b"\0" * (len(data) & 1)
        for kind, data in chunks
    )
    return b"RIFF" + struct.pack("<I", len(payload)) + payload


def webp_dimension_header(width, height, *, kind=b"VP8L", canvas=None, flags=0):
    if kind == b"VP8L":
        # Valid one-pixel lossless stream with only its dimensions changed.
        payload = bytes.fromhex("2f00000000071011fd0f4444ff03")
        payload = (
            payload[:1] + ((width - 1) | ((height - 1) << 14)).to_bytes(4, "little") + payload[5:]
        )
    else:
        # Displayed key frame, uncompressed VP8 header. Compressed data is never
        # reached in oversized-header cases, so no large fixture is necessary.
        payload = b"\x10\0\0\x9d\x01\x2a" + struct.pack("<HH", width, height)
    chunks = [(kind, payload)]
    if canvas is not None:
        extended = (
            bytes([flags, 0, 0, 0])
            + (canvas[0] - 1).to_bytes(3, "little")
            + (canvas[1] - 1).to_bytes(3, "little")
        )
        chunks.insert(0, (b"VP8X", extended))
    return webp_container(*chunks)


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


@pytest.mark.parametrize("kind", [b"VP8 ", b"VP8L"])
@pytest.mark.parametrize("extended", [False, True])
@pytest.mark.parametrize("size", [(8193, 1), (1, 8193), (5000, 4001), (8192, 8192)])
def test_webp_oversize_is_rejected_before_native_canvas(kind, extended, size, monkeypatch):
    def forbidden_constructor(*args, **kwargs):
        raise AssertionError("Oversized WebP reached native canvas allocation")

    content = webp_dimension_header(*size, kind=kind, canvas=size if extended else None)
    monkeypatch.setattr(_webp, "WebPAnimDecoder", forbidden_constructor)
    with pytest.raises(MessagingError, match="INVALID_INPUT"):
        decode_image(content)


@pytest.mark.parametrize("kind", [b"VP8 ", b"VP8L"])
@pytest.mark.parametrize(
    "canvas,size", [((1, 1), (8192, 8192)), ((8192, 8192), (1, 1)), ((7, 5), (1, 1))]
)
def test_webp_canvas_and_bitstream_cannot_disagree(kind, canvas, size, monkeypatch):
    def forbidden_constructor(*args, **kwargs):
        raise AssertionError("Contradictory WebP dimensions reached native decoder")

    monkeypatch.setattr(_webp, "WebPAnimDecoder", forbidden_constructor)
    with pytest.raises(MessagingError, match="INVALID_INPUT"):
        decode_image(webp_dimension_header(*size, kind=kind, canvas=canvas))


def invalid_webp_headers():
    valid = webp_dimension_header(1, 1)
    lossless = valid[20:]
    extended = b"\0" * 10
    lossy = webp_dimension_header(1, 1, kind=b"VP8 ")[20:]
    return {
        "riff_size_underflow": valid[:4] + struct.pack("<I", len(valid) - 10) + valid[8:],
        "riff_size_overflow": valid[:4] + struct.pack("<I", len(valid)) + valid[8:],
        "chunk_size_overflow": valid[:16] + b"\xff" * 4 + valid[20:],
        "partial_chunk_header": webp_container((b"VP8L", lossless))[:4]
        + struct.pack("<I", len(valid) - 4)
        + valid[8:]
        + b"JUNK",
        "missing_padding": webp_container((b"VP8L", lossless), (b"JUNK", b"x"))[:-1],
        "nonzero_padding": webp_container((b"VP8L", lossless), (b"JUNK", b"x"))[:-1] + b"x",
        "short_lossless_header": webp_container((b"VP8L", lossless[:4])),
        "lossless_signature": webp_container((b"VP8L", b"x" + lossless[1:])),
        "lossless_version": webp_container((b"VP8L", lossless[:4] + b"\xe0" + lossless[5:])),
        "short_lossy_header": webp_container((b"VP8 ", lossy[:9])),
        "lossy_not_keyframe": webp_container((b"VP8 ", b"\x11" + lossy[1:])),
        "lossy_version": webp_container((b"VP8 ", b"\x18" + lossy[1:])),
        "lossy_not_displayed": webp_container((b"VP8 ", b"\0" + lossy[1:])),
        "lossy_sync_code": webp_container((b"VP8 ", lossy[:3] + b"bad" + lossy[6:])),
        "zero_lossy_width": webp_container((b"VP8 ", lossy[:6] + b"\0\0" + lossy[8:])),
        "duplicate_bitstream": webp_container((b"VP8L", lossless), (b"VP8L", lossless)),
        "mixed_bitstreams": webp_container((b"VP8 ", lossy), (b"VP8L", lossless)),
        "late_extended_header": webp_container((b"VP8L", lossless), (b"VP8X", extended)),
        "duplicate_extended_header": webp_container(
            (b"VP8X", extended), (b"VP8X", extended), (b"VP8L", lossless)
        ),
        "missing_bitstream": webp_container((b"VP8X", extended)),
        "short_extended_header": webp_container((b"VP8X", extended[:-1]), (b"VP8L", lossless)),
        "extended_reserved_flags": webp_container(
            (b"VP8X", b"\x80" + extended[1:]), (b"VP8L", lossless)
        ),
        "extended_reserved_bytes": webp_container(
            (b"VP8X", extended[:1] + b"x" + extended[2:]), (b"VP8L", lossless)
        ),
        "animation_flag_without_frames": webp_dimension_header(1, 1, canvas=(1, 1), flags=2),
        "animation_control_without_flag": webp_container(
            (b"VP8X", extended), (b"ANIM", b"\0" * 6), (b"VP8L", lossless)
        ),
        "animation_frame_without_flag": webp_container(
            (b"VP8X", extended), (b"ANMF", b"\0" * 16), (b"VP8L", lossless)
        ),
        "alpha_without_canvas": webp_container((b"VP8 ", lossy), (b"ALPH", b"\0x")),
        "alpha_after_bitstream": webp_container(
            (b"VP8X", extended), (b"VP8 ", lossy), (b"ALPH", b"\0x")
        ),
        "duplicate_alpha": webp_container(
            (b"VP8X", extended), (b"ALPH", b"\0x"), (b"ALPH", b"\0x"), (b"VP8 ", lossy)
        ),
        "alpha_with_lossless": webp_container(
            (b"VP8X", extended), (b"ALPH", b"\0x"), (b"VP8L", lossless)
        ),
        "invalid_alpha_compression": webp_container(
            (b"VP8X", extended), (b"ALPH", b"\x02x"), (b"VP8 ", lossy)
        ),
        "invalid_raw_alpha_size": webp_container(
            (b"VP8X", extended), (b"ALPH", b"\0xx"), (b"VP8 ", lossy)
        ),
    }


@pytest.mark.parametrize(
    "content", list(invalid_webp_headers().values()), ids=list(invalid_webp_headers())
)
def test_webp_malformed_structure_is_rejected_before_native_canvas(content, monkeypatch):
    def forbidden_constructor(*args, **kwargs):
        raise AssertionError("Malformed WebP headers reached native canvas allocation")

    monkeypatch.setattr(_webp, "WebPAnimDecoder", forbidden_constructor)
    with pytest.raises(MessagingError, match="INVALID_INPUT"):
        decode_image(content)


def test_real_animated_webp_is_rejected_before_native_canvas(monkeypatch):
    content = image_bytes("WEBP", animated=True)

    def forbidden_constructor(*args, **kwargs):
        raise AssertionError("Animated WebP reached native canvas allocation")

    monkeypatch.setattr(_webp, "WebPAnimDecoder", forbidden_constructor)
    with pytest.raises(MessagingError, match="INVALID_INPUT"):
        decode_image(content)


@pytest.mark.parametrize("lossless", [False, True])
@pytest.mark.parametrize("alpha", [False, True])
@pytest.mark.parametrize("metadata", [False, True])
def test_webp_lossy_lossless_extended_originals_reach_real_decoder(
    lossless, alpha, metadata, monkeypatch
):
    output = BytesIO()
    options = {"lossless": lossless}
    if metadata:
        exif = Image.Exif()
        exif[274] = 6
        options.update(exif=exif, icc_profile=b"controlled-profile", xmp=b"<xmp/>")
    with Image.new(
        "RGBA" if alpha else "RGB", (7, 5), (12, 92, 113, 72) if alpha else (12, 92, 113)
    ) as original:
        original.save(output, format="WEBP", **options)
    content = output.getvalue()
    native_calls = []
    real_constructor = _webp.WebPAnimDecoder

    def observed_constructor(data):
        native_calls.append(True)
        return real_constructor(data)

    monkeypatch.setattr(_webp, "WebPAnimDecoder", observed_constructor)
    manifest = decode_image(content)
    assert manifest.mime_type == "image/webp"
    assert manifest.sha256 == hashlib.sha256(content).hexdigest()
    assert manifest.size_bytes == len(content)
    assert (manifest.width, manifest.height) == (7, 5)
    assert native_calls == [True, True]
    expected_first_chunk = (
        b"VP8X" if metadata or (alpha and not lossless) else b"VP8L" if lossless else b"VP8 "
    )
    assert content[12:16] == expected_first_chunk


@pytest.mark.parametrize("kind", [b"VP8 ", b"VP8L"])
def test_bounded_webp_headers_do_not_replace_full_pixel_validation(kind):
    # Keep complete dimensions but remove the entropy-coded pixel data. Merely
    # changing dimensions of a uniform lossless stream can still be valid.
    payload = webp_dimension_header(7, 5, kind=kind)[20:]
    content = webp_container((kind, payload[:5] if kind == b"VP8L" else payload[:10]))
    with pytest.raises(MessagingError, match="INVALID_INPUT"):
        decode_image(content)


@pytest.mark.parametrize("size", [(8192, 1), (1, 8192), (4000, 5000)])
def test_webp_exact_side_and_pixel_boundaries_can_decode(size):
    content = webp_dimension_header(*size)
    manifest = decode_image(content)
    assert (manifest.width, manifest.height) == size
    assert manifest.sha256 == hashlib.sha256(content).hexdigest()


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
