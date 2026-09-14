import argparse
import json
from pathlib import Path

from pydantic import SecretStr

from asm.foundation import Settings, create_app


class OfflineDatabase:
    async def check(self):
        raise RuntimeError("Contract export does not connect to a database")

    async def close(self):
        pass


parser = argparse.ArgumentParser()
parser.add_argument("--check", action="store_true")
args = parser.parse_args()
settings = Settings(environment="TEST", database_url=SecretStr("postgresql+psycopg://asm_runtime:unused@localhost/asm_test"))
content = json.dumps(create_app(settings, OfflineDatabase()).openapi(), sort_keys=True, indent=2) + "\n"
path = Path("contracts/openapi.json")
if args.check:
    if not path.exists() or path.read_text() != content:
        raise SystemExit("OpenAPI drift: run scripts/export_contracts.py and review the diff")
else:
    path.write_text(content)
