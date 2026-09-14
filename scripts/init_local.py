"""Create LOCAL-only random credentials. Does not print or replace existing secrets."""
import os
import secrets
from pathlib import Path

path = Path(".env")
if path.exists():
    print("Existing .env kept unchanged")
else:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w") as output:
        for key in ("PG_ADMIN_PASSWORD", "PG_MIGRATION_PASSWORD", "PG_RUNTIME_PASSWORD"):
            output.write(f"{key}={secrets.token_hex(24)}\n")
    print("Created .env with random LOCAL credentials; do not commit it")
