from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ASM_", extra="ignore", hide_input_in_errors=True)
    # Implementation defaults for LOCAL/TEST only, not production security policy.
    auth_origins: tuple[str, ...] = (
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    )
    auth_session_ttl_seconds: int = Field(default=28800, ge=1, le=86400)
    auth_prelogin_ttl_seconds: int = Field(default=600, ge=1, le=900)
    auth_rate_window_seconds: int = Field(default=60, ge=1, le=3600)
    auth_peer_limit: int = Field(default=30, ge=1, le=1000)
    auth_login_limit: int = Field(default=10, ge=1, le=1000)
    auth_global_limit: int = Field(default=120, ge=1, le=10000)
    auth_hash_concurrency: int = Field(default=2, ge=1, le=4)

    @field_validator("auth_origins")
    @classmethod
    def explicit_origins(cls, origins: tuple[str, ...]) -> tuple[str, ...]:
        if not origins or len(origins) > 8 or len(set(origins)) != len(origins):
            raise ValueError("An explicit bounded origin allowlist is required")
        schemes = set()
        for origin in origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in ("https", "http")
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
                or "*" in origin
                or origin != f"{parsed.scheme}://{parsed.netloc}"
                or parsed.netloc != parsed.netloc.lower()
            ):
                raise ValueError("Invalid trusted origin")
            # Parsing the port must also succeed; do not accept malformed authority.
            _ = parsed.port
            if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
                raise ValueError("HTTP auth is restricted to LOCAL/TEST loopback origins")
            schemes.add(parsed.scheme)
        if len(schemes) != 1:
            raise ValueError("Do not mix TLS and plaintext auth origins")
        return origins

    @property
    def auth_secure(self) -> bool:
        return all(origin.startswith("https://") for origin in self.auth_origins)

    @property
    def auth_cookie_name(self) -> str:
        return "__Host-asm_session" if self.auth_secure else "asm_session_local"

    @property
    def auth_hosts(self) -> frozenset[str]:
        # The accepted Compose nginx proxy sends its fixed upstream Host api:8000.
        # This does not extend browser trusted origins or trust forwarded headers.
        return frozenset(
            {"api", *(urlsplit(origin).hostname or "" for origin in self.auth_origins)}
        )
