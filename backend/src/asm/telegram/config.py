"""Optional operator-owned configuration, never inferred from an incoming event."""

import re
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TelegramSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", frozen=True, hide_input_in_errors=True)
    environment: Literal["LOCAL", "TEST"] = Field(
        default="LOCAL", validation_alias="ASM_ENVIRONMENT"
    )
    enabled: bool = Field(default=False, validation_alias="ASM_TELEGRAM_ENABLED")
    token: SecretStr = Field(default=SecretStr(""), validation_alias="TG_BOT_TOKEN", repr=False)
    webhook_secret: SecretStr = Field(
        default=SecretStr(""), validation_alias="TG_WEBHOOK_SECRET", repr=False
    )
    bot_id: str = Field(default="", validation_alias="ASM_TELEGRAM_EXPECTED_BOT_ID")
    webhook_url: str = Field(default="", validation_alias="ASM_TELEGRAM_WEBHOOK_URL", repr=False)

    @model_validator(mode="after")
    def explicit_enabled_configuration(self) -> Self:
        if not self.enabled:
            return self
        token, secret = self.token.get_secret_value(), self.webhook_secret.get_secret_value()
        if (
            re.fullmatch(r"[1-9][0-9]{0,18}", self.bot_id) is None
            or int(self.bot_id) > 9223372036854775807
            or re.fullmatch(re.escape(self.bot_id) + r":[A-Za-z0-9_-]{16,128}", token) is None
            or re.fullmatch(r"[A-Za-z0-9_-]{16,256}", secret) is None
            or secret == token
        ):
            raise ValueError("TELEGRAM_CONFIG_INVALID")
        try:
            url = urlsplit(self.webhook_url)
            valid = (
                url.scheme == "https"
                and url.hostname
                and not url.username
                and not url.password
                and url.path == "/webhooks/telegram"
                and not url.query
                and not url.fragment
                and url.port in {None, 443, 8443}
            )
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("TELEGRAM_WEBHOOK_INVALID")
        return self
