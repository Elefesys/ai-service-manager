"""Opt-in HTTPS owner API smoke; send requires one independently approved test dialog."""

import argparse
import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from asm.messaging.models import command_key, manual_text


class SmokeError(RuntimeError):
    pass


class PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        raise SmokeError("TELEGRAM_SMOKE_ARGUMENTS_INVALID")


def origin(value):
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or value != "https://" + parsed.netloc
        or parsed.port == 0
    ):
        raise SmokeError("TELEGRAM_SMOKE_HTTPS_REQUIRED")
    return value


@dataclass(frozen=True)
class SmokeSettings:
    console_origin: str
    storage_origin: str
    workspace_id: UUID
    business_id: UUID
    connection_id: UUID
    login: str = field(repr=False)
    password: str = field(repr=False)
    marker: str = field(repr=False)
    conversation_id: UUID | None = None
    client_id: UUID | None = None
    reply_text: str | None = field(default=None, repr=False)
    idempotency_key: str | None = field(default=None, repr=False)

    @classmethod
    def from_environment(cls, environment, send):
        if environment.get("ASM_ENVIRONMENT") not in {"LOCAL", "TEST"}:
            raise SmokeError("TELEGRAM_SMOKE_ENVIRONMENT_INVALID")
        conversation = environment.get("ASM_TELEGRAM_SMOKE_CONVERSATION_ID")
        client = environment.get("ASM_TELEGRAM_SMOKE_CLIENT_ID")
        reply = environment.get("ASM_TELEGRAM_SMOKE_REPLY")
        key = environment.get("ASM_TELEGRAM_SMOKE_KEY")
        if send and (
            not conversation
            or not client
            or not reply
            or not key
            or environment.get("ASM_TELEGRAM_SMOKE_APPROVAL") != "approved-test-dialog"
        ):
            raise SmokeError("TELEGRAM_SMOKE_APPROVED_DIALOG_REQUIRED")
        if reply:
            manual_text(reply)
        if key:
            command_key(key)
        return cls(
            console_origin=origin(environment["ASM_TELEGRAM_SMOKE_ORIGIN"]),
            storage_origin=origin(environment["ASM_STORAGE_ENDPOINT"]),
            workspace_id=UUID(environment["ASM_TELEGRAM_WORKSPACE_ID"]),
            business_id=UUID(environment["ASM_TELEGRAM_BUSINESS_ID"]),
            connection_id=UUID(environment["ASM_TELEGRAM_SMOKE_CONNECTION_ID"]),
            login=environment["ASM_TELEGRAM_SMOKE_LOGIN"],
            password=environment["ASM_TELEGRAM_SMOKE_PASSWORD"],
            marker=manual_text(environment["ASM_TELEGRAM_SMOKE_MARKER"]),
            conversation_id=UUID(conversation) if conversation else None,
            client_id=UUID(client) if client else None,
            reply_text=reply,
            idempotency_key=key,
        )


async def request_json(client, method, path, expected=200, **kwargs):
    async with client.stream(method, path, **kwargs) as response:
        if response.status_code != expected:
            raise SmokeError("TELEGRAM_SMOKE_HTTP_REJECTED")
        content = bytearray()
        async for chunk in response.aiter_bytes():
            content.extend(chunk)
            if len(content) > 524288:
                raise SmokeError("TELEGRAM_SMOKE_RESPONSE_TOO_LARGE")
        result = json.loads(content)
        if not isinstance(result, dict):
            raise SmokeError("TELEGRAM_SMOKE_RESPONSE_INVALID")
        return result


async def collection(client, path):
    items = []
    cursor = None
    # A fresh test Workspace should have one dialog; fail boundedly on larger datasets.
    for _ in range(4):
        params = {"limit": "25"}
        if cursor:
            params["cursor"] = cursor
        page = await request_json(client, "GET", path, params=params)
        if not isinstance(page.get("items"), list) or len(page["items"]) > 25:
            raise SmokeError("TELEGRAM_SMOKE_RESPONSE_INVALID")
        items.extend(page["items"])
        cursor = page.get("next_cursor")
        if cursor is None:
            return items
        if not isinstance(cursor, str) or len(cursor) > 1024:
            raise SmokeError("TELEGRAM_SMOKE_RESPONSE_INVALID")
    raise SmokeError("TELEGRAM_SMOKE_DATASET_TOO_LARGE")


def require_secure_cookie(client):
    cookies = [cookie for cookie in client.cookies.jar if cookie.name == "__Host-asm_session"]
    if (
        len(cookies) != 1
        or not cookies[0].secure
        or cookies[0].path != "/"
        or cookies[0].domain_specified
        or not cookies[0].has_nonstandard_attr("HttpOnly")
    ):
        raise SmokeError("TELEGRAM_SMOKE_SECURE_COOKIE_REQUIRED")


async def private_image(client, signed_url, storage_origin, manifest):
    parsed = urlsplit(signed_url)
    if (
        parsed.scheme + "://" + parsed.netloc != storage_origin
        or parsed.username is not None
        or parsed.password is not None
        or not parsed.path.startswith("/")
        or parsed.fragment
    ):
        raise SmokeError("TELEGRAM_SMOKE_SIGNED_ORIGIN_MISMATCH")
    size = int(manifest["size_bytes"])
    if not 1 <= size <= 10 * 1024 * 1024:
        raise SmokeError("TELEGRAM_SMOKE_IMAGE_INVALID")
    async with client.stream("GET", signed_url) as response:
        if (
            response.status_code != 200
            or response.headers.get("content-type", "").split(";", 1)[0] != manifest["mime_type"]
        ):
            raise SmokeError("TELEGRAM_SMOKE_PRIVATE_GET_FAILED")
        actual = 0
        async for chunk in response.aiter_bytes():
            actual += len(chunk)
            if actual > size:
                raise SmokeError("TELEGRAM_SMOKE_IMAGE_INVALID")
        if actual != size:
            raise SmokeError("TELEGRAM_SMOKE_IMAGE_INVALID")


async def smoke(settings, client, image_client, *, send=False):
    bootstrap = await request_json(
        client, "POST", "/api/v1/auth/bootstrap", json={}, headers={"X-CSRF-Bootstrap": "1"}
    )
    require_secure_cookie(client)
    login = await request_json(
        client,
        "POST",
        "/api/v1/auth/login",
        json={"login": settings.login, "password": settings.password},
        headers={"X-CSRF-Token": bootstrap["csrf_token"]},
    )
    require_secure_cookie(client)
    mutation_headers = {"X-CSRF-Token": login["csrf_token"]}
    prefix = f"/api/v1/workspaces/{settings.workspace_id}"
    connections = await collection(client, prefix + "/channel-connections")
    selected = [row for row in connections if row["connection_id"] == str(settings.connection_id)]
    if (
        len(selected) != 1
        or selected[0]["business_id"] != str(settings.business_id)
        or selected[0]["provider"] != "TELEGRAM"
    ):
        raise SmokeError("TELEGRAM_SMOKE_CONNECTION_MISMATCH")
    conversations = await collection(client, prefix + "/conversations")
    candidates = [
        row
        for row in conversations
        if row["connection_id"] == str(settings.connection_id)
        and row["business_id"] == str(settings.business_id)
    ]
    if settings.conversation_id is None:
        if send:
            raise SmokeError("TELEGRAM_SMOKE_APPROVED_DIALOG_REQUIRED")
        return {
            "status": "TELEGRAM_SMOKE_APPROVAL_NEEDED",
            "candidates": [
                {"conversation_id": row["conversation_id"], "client_id": row["client_id"]}
                for row in candidates
            ],
        }
    approved = [
        row
        for row in candidates
        if row["conversation_id"] == str(settings.conversation_id)
        and row["client_id"] == str(settings.client_id)
    ]
    if len(approved) != 1:
        raise SmokeError("TELEGRAM_SMOKE_APPROVED_DIALOG_MISMATCH")
    history = prefix + f"/conversations/{settings.conversation_id}/messages"
    messages = await collection(client, history)
    inbound = [row for row in messages if row["direction"] == "INBOUND"]
    text_seen = any(
        row["content_type"] == "TEXT" and row["text"] == settings.marker for row in inbound
    )
    photos = [
        row
        for row in inbound
        if row["content_type"] == "IMAGE_REFERENCE"
        and row["text"] == settings.marker
        and row["file"] is not None
        and row["file"]["status"] == "READY"
    ]
    if not text_seen or len(photos) != 1:
        raise SmokeError("TELEGRAM_SMOKE_APPROVED_TEXT_PHOTO_REQUIRED")
    photo = photos[0]
    grant = await request_json(
        client,
        "POST",
        history + f"/{photo['message_id']}/files/{photo['file']['file_id']}/read-grant",
        json={},
        headers=mutation_headers,
    )
    await private_image(
        image_client, grant["url"], settings.storage_origin, photo["file"]["manifest"]
    )
    if not send:
        return {"status": "TELEGRAM_SMOKE_READ_READY", "connection_state": selected[0]["state"]}
    if not settings.reply_text or not settings.idempotency_key:
        raise SmokeError("TELEGRAM_SMOKE_APPROVED_DIALOG_REQUIRED")
    accepted = await request_json(
        client,
        "POST",
        history,
        expected=202,
        json={"text": settings.reply_text},
        headers={**mutation_headers, "Idempotency-Key": settings.idempotency_key},
    )
    # Exactly one intention POST per invocation. Rerun only with the original saved key/text.
    for _ in range(15):
        messages = await collection(client, history)
        outgoing = [row for row in messages if row["message_id"] == accepted["message_id"]]
        if outgoing and outgoing[0]["delivery"]["status"] in {"SENT", "FAILED", "UNKNOWN"}:
            return {
                "status": "TELEGRAM_SMOKE_" + outgoing[0]["delivery"]["status"],
                "message_id": accepted["message_id"],
                "outcome": accepted["outcome"],
            }
        await asyncio.sleep(1)
    return {"status": "TELEGRAM_SMOKE_PENDING", "message_id": accepted["message_id"]}


async def run(environment, send):
    settings = SmokeSettings.from_environment(environment, send)
    options = {
        "trust_env": False,
        "follow_redirects": False,
        "timeout": httpx.Timeout(5, connect=2, pool=2),
        "limits": httpx.Limits(max_connections=2, max_keepalive_connections=2),
    }
    async with (
        asyncio.timeout(90),
        httpx.AsyncClient(
            base_url=settings.console_origin,
            headers={"Origin": settings.console_origin},
            **options,
        ) as client,
        httpx.AsyncClient(**options) as image_client,
    ):
        return await smoke(settings, client, image_client, send=send)


def main():
    for name in ("httpx", "httpcore"):
        logger = logging.getLogger(name)
        logger.disabled = True
        logger.propagate = False
        logger.handlers = [logging.NullHandler()]
    try:
        parser = PrivateParser(description=__doc__)
        parser.add_argument("--live", action="store_true")
        parser.add_argument("--send-approved-reply", action="store_true")
        args = parser.parse_args()
        if not args.live:
            raise SmokeError("TELEGRAM_SMOKE_EXPLICIT_LIVE_REQUIRED")
        result = asyncio.run(run(os.environ, args.send_approved_reply))
        print(json.dumps(result, sort_keys=True))
        return (
            0
            if result["status"]
            in {
                "TELEGRAM_SMOKE_APPROVAL_NEEDED",
                "TELEGRAM_SMOKE_READ_READY",
                "TELEGRAM_SMOKE_SENT",
            }
            else 1
        )
    except SmokeError as error:
        print(str(error), file=sys.stderr)
        return 1
    except Exception:
        print("TELEGRAM_SMOKE_FAILED", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
