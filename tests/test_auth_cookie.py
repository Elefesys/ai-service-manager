"""C0-M1.2-03: HTTP UTC normalization preserves the DB-supplied expiry instant."""

from datetime import UTC, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from http.cookies import SimpleCookie
from zoneinfo import ZoneInfo

import pytest
from asm.auth import http as auth_http
from asm.auth.config import AuthSettings
from fastapi import Response

NOW = datetime(2035, 7, 1, 11, 34, 56, 987654, tzinfo=UTC)
EXPIRY = NOW + timedelta(hours=1)


class FixedClock(datetime):
    @classmethod
    def now(cls, tz=None):
        assert tz is UTC
        return NOW


@pytest.mark.parametrize(
    "zone",
    [
        pytest.param(UTC, id="datetime-UTC"),
        pytest.param(ZoneInfo("UTC"), id="zoneinfo-UTC"),
        pytest.param(ZoneInfo("Etc/UTC"), id="zoneinfo-Etc-UTC"),
        pytest.param(ZoneInfo("Europe/Moscow"), id="non-UTC-positive"),
        pytest.param(ZoneInfo("America/New_York"), id="non-UTC-negative"),
        pytest.param(timezone(timedelta(hours=5, minutes=30)), id="non-UTC-half-hour"),
    ],
)
@pytest.mark.parametrize("secure", [False, True], ids=["local-http", "tls"])
def test_cookie_expiry_normalizes_timezone_without_extending_ttl(monkeypatch, zone, secure):
    # Freeze only this HTTP helper's clock; do not replace the incoming aware date.
    monkeypatch.setattr(auth_http, "datetime", FixedClock)
    settings = AuthSettings(
        auth_origins=("https://console.example.test",) if secure else ("http://localhost:8000",)
    )
    expires = EXPIRY.astimezone(zone)
    before = expires.isoformat()
    response = Response()
    # This literal has no backing server session and is not a usable credential.
    auth_http.set_cookie(response, "noncredential-unit-probe", expires, settings)
    cookies = SimpleCookie()
    cookies.load(response.headers["set-cookie"])
    assert len(cookies) == 1
    cookie = cookies[settings.auth_cookie_name]
    http_expiry = parsedate_to_datetime(cookie["expires"])
    assert http_expiry.tzinfo is UTC
    # HTTP dates have whole-second precision; compare against the original instant.
    assert http_expiry.timestamp() == int(EXPIRY.timestamp())
    assert http_expiry.timestamp() <= expires.timestamp()
    assert cookie["expires"].endswith(" GMT")
    assert int(cookie["max-age"]) == 3600
    assert cookie["httponly"] is True
    assert bool(cookie["secure"]) is secure
    assert cookie["samesite"] == "lax"
    assert cookie["path"] == "/"
    assert cookie["domain"] == ""
    assert expires.isoformat() == before
