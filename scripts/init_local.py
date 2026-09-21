"""Create LOCAL-only random credentials. Does not print or replace existing secrets."""

import os
import secrets
from pathlib import Path

path = Path(".env")
keys = (
    "PG_ADMIN_PASSWORD",
    "PG_MIGRATION_PASSWORD",
    "PG_RUNTIME_PASSWORD",
    "STORAGE_ROOT_USER",
    "STORAGE_ROOT_PASSWORD",
    "STORAGE_ACCESS_KEY",
    "STORAGE_SECRET_KEY",
)
# Append missing LOCAL settings only. Existing bytes and values are preserved.
flags = os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW
fd = os.open(path, flags, 0o600)
with os.fdopen(fd, "r+") as output:
    content = output.read()
    existing = {line.split("=", 1)[0].strip() for line in content.splitlines() if "=" in line}
    missing = [key for key in keys if key not in existing]
    if missing and content and not content.endswith("\n"):
        output.write("\n")
    for key in missing:
        output.write(f"{key}={secrets.token_hex(24)}\n")
print("LOCAL settings ready; existing credentials preserved; no secrets printed")
