"""Finite operator admission for the existing worker; plan never opens a socket."""

import argparse
import asyncio
import json
from pathlib import Path
from uuid import UUID

from asm.ai.runtime_settings import load_key, load_settings, private_bytes
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine


def plan(config):
    return {
        "mode": "EVAL_ONLY",
        "live_authorized": False,
        "session_id": str(config.session_id),
        "expires_at": config.expires_at.isoformat(),
        "max_model_posts": config.max_calls,
        "max_session_rub": str(config.max_rub),
        "max_reads_per_run": 1,
        "max_posts_per_run": 2,
        "deadline_seconds": 120,
        "max_history_gets_per_post": 2,
        "catalog_gets": 0,
        "review_sha256": config.review_sha256,
        "requested_provider": "openai/flex",
        "observed_variant": "NOT_ESTABLISHED",
        "secret_required_only_for_enable_and_worker": True,
        "disable": "Stops new model/send admission; cannot recall an admitted HTTP request.",
    }


async def mutate(path, payload, enable):
    url = make_url(private_bytes(path, 4096).decode().strip())
    if (
        url.drivername != "postgresql+psycopg"
        or url.username != "asm_migrator"
        or url.database != "asm_test"
    ):
        raise ValueError("RUNTIME_DATABASE_INVALID")
    engine = create_async_engine(url, hide_parameters=True, connect_args={"connect_timeout": 5})
    try:
        async with asyncio.timeout(15), engine.begin() as connection:
            await connection.execute(text("SET LOCAL statement_timeout='10s'"))
            return (
                await connection.execute(
                    text("SELECT platform.ai_provider_session(CAST(:p AS jsonb),:enable)"),
                    {"p": json.dumps(payload), "enable": enable},
                )
            ).scalar_one()
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("plan", "enable", "disable"))
    parser.add_argument("--config", type=Path)
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--database-file", type=Path)
    parser.add_argument("--session", type=UUID)
    args = parser.parse_args()
    try:
        if args.operation == "disable":
            if args.session is None or args.database_file is None or args.config or args.key_file:
                raise ValueError
            result = asyncio.run(
                mutate(args.database_file, {"session_id": str(args.session)}, False)
            )
        else:
            if args.config is None or args.session is not None:
                raise ValueError
            config = load_settings(args.config)
            if args.operation == "plan":
                if args.key_file or args.database_file:
                    raise ValueError
                result = plan(config)
            else:
                if args.key_file is None or args.database_file is None:
                    raise ValueError
                config.current()
                load_key(args.key_file)
                result = asyncio.run(mutate(args.database_file, config.admission(), True))
        print(json.dumps(result, sort_keys=True))
    except Exception:
        print('{"code":"RUNTIME_OPERATION_REFUSED"}')
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
