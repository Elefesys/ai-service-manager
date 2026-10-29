"""Private probe credentials, separate from application/Telegram settings."""

import os
import stat
from pathlib import Path

from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProbeSettings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="forbid", frozen=True, hide_input_in_errors=True, env_prefix="M4_PROBE_"
    )
    api_key: SecretStr = Field(repr=False, min_length=16, max_length=512)


def load_secret(path: Path) -> ProbeSettings:
    """No ambient env override, symlinks, group-readable files, or raw validation errors.

    Windows ACL inspection is an operator prerequisite documented in the runbook.
    The dedicated file must contain exactly M4_PROBE_API_KEY=<value>.
    """
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 1024:
            raise ValueError
        if os.name == "posix" and (
            info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise ValueError
        value = os.read(descriptor, 1025).decode("utf-8").strip()
        prefix = "M4_PROBE_API_KEY="
        if not value.startswith(prefix):
            raise ValueError
        key = value.removeprefix(prefix)
        if not key or any(c.isspace() or not c.isprintable() for c in key):
            raise ValueError
        # Construct with an explicit value; environment cannot replace this secret.
        return ProbeSettings(api_key=SecretStr(key))
    except (OSError, UnicodeError, ValueError, ValidationError):
        raise ValueError("PRIVATE_SECRET_FILE_INVALID") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
