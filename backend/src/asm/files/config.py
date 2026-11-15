"""Operator-owned LOCAL/TEST S3 configuration, independent of DB readiness."""

from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class StorageSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ASM_STORAGE_", extra="ignore", hide_input_in_errors=True, frozen=True
    )
    environment: Literal["LOCAL", "TEST"]
    endpoint: str = Field(repr=False)
    presign_endpoint: str | None = Field(default=None, repr=False)
    bucket: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")
    access_key: SecretStr
    secret_key: SecretStr
    region: str = "us-east-1"

    @field_validator("endpoint", "presign_endpoint")
    @classmethod
    def endpoint_is_operator_origin(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            parsed = urlsplit(value)
            valid = (
                parsed.scheme in {"http", "https"}
                and parsed.hostname
                and parsed.port != 0
                and parsed.username is None
                and parsed.password is None
                and not parsed.query
                and not parsed.fragment
                and parsed.path in {"", "/"}
            )
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("STORAGE_ENDPOINT_INVALID")
        return value.rstrip("/")

    @field_validator("access_key", "secret_key")
    @classmethod
    def explicit_credentials(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 16:
            raise ValueError("STORAGE_CREDENTIAL_INVALID")
        return value
