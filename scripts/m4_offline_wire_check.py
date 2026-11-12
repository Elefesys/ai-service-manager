"""Rebuild one stored first-call payload without HTTP, DB writes or admission.

Run in a container with --network none. Inputs stay private on the operator host.
The historical call time checks expiry without rewriting any stored timestamp.
PASS proves local request construction only, never provider acceptance or delivery.
"""

import argparse
import json
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import Any

import httpx
from asm.ai.agent import current_context_tool
from asm.ai.context import ContextBuilder
from asm.ai.contracts import CONVERSATION_RESULT, AdapterRequest, GatewayRequest, strict_json
from asm.ai.polza import GPT_HISTORY_PROFILE, PolzaAdapter, PolzaFailure, failure_labels
from asm.ai.runtime_contracts import PreparedRun
from asm.ai.runtime_settings import RuntimeSettings, load_settings, private_bytes
from pydantic import SecretStr


def inspect(settings: RuntimeSettings, run: PreparedRun, at: datetime) -> dict[str, Any]:
    """Pure local check. No call to complete(), Gateway.call(), runtime or authority."""
    stage = "CONFIG"
    try:
        if (
            at.tzinfo is None
            or run.config != settings.gateway()
            or any(
                getattr(settings, name) != getattr(run.binding, name)
                for name in ("workspace_id", "client_id", "conversation_id", "connection_id")
            )
        ):
            raise ValueError
        stage = "CONTEXT"
        context = ContextBuilder().build(run.snapshot, run.binding)
        stage = "SCHEMA"
        prompt = files("asm.ai").joinpath("prompts/conversation_v2.txt").read_text("utf-8")
        schema = files("asm.ai").joinpath("schemas/conversation_result_v1.json").read_text("utf-8")
        if strict_json(schema) != CONVERSATION_RESULT.json_schema():
            raise ValueError("WIRE_SCHEMA_UNSUPPORTED")

        def deny_http(request: httpx.Request) -> httpx.Response:
            raise AssertionError("OFFLINE_HTTP_FORBIDDEN")

        adapter = PolzaAdapter(
            settings.review,
            SecretStr("offline-placeholder-never-a-provider-key"),
            transport=httpx.MockTransport(deny_http),
            history_profile=GPT_HISTORY_PROFILE,
        )
        request = AdapterRequest(
            config=run.config,
            request=GatewayRequest(
                run_id=str(run.run_id),
                deadline=run.deadline,
                messages=context.view.messages(),
                tools=(current_context_tool(),) if run.config.limits.read_executions else (),
            ),
            prompt=prompt,
            output_schema_json=schema,
            exchanges=(),
            budget=run.budget,
            # No execution/deadline is renewed: remaining_seconds is not on the wire.
            remaining_seconds=1.0,
        )
        stage = "WIRE"
        body = adapter.wire(request)
        tokens = adapter.count_input_tokens(request)
        stage = "PAYLOAD"
        adapter.check_payload(body)
        limits = run.config.limits
        stage = "LIMITS"
        if (
            len(request.input_json().encode()) > limits.input_bytes
            or len(body) > limits.input_bytes
            or tokens > limits.input_tokens
            or limits.call_cost_reservation < settings.review.reservation()
        ):
            raise PolzaFailure("ADAPTER_ERROR", "LOCAL_REQUEST_LIMIT")
        return {
            "status": "OFFLINE_WIRE_VALID",
            "wire_bytes": len(body),
            "input_token_bound": tokens,
            "catalog_fresh_at_call": 0
            <= (at - settings.review.checked_at).total_seconds()
            <= 86400,
            "session_current_at_call": settings.starts_at <= at < settings.expires_at,
            "deadline_current_at_call": at < run.deadline,
            "provider_acceptance": "NOT_TESTED",
            "runtime_authorization": "NOT_TESTED",
            "model_posts": 0,
        }
    except Exception as error:
        return {
            "status": "OFFLINE_CHECK_FAILED",
            "stage": stage,
            **failure_labels(error),
            "model_posts": 0,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument(
        "--at", required=True, help="Original reserved_at timestamp, with UTC offset"
    )
    args = parser.parse_args()
    try:
        settings = load_settings(args.settings)
        run = PreparedRun.model_validate_json(private_bytes(args.run, 1048576))
        at = datetime.fromisoformat(args.at)
        if at.tzinfo is None:
            raise ValueError
        result = inspect(settings, run, at.astimezone(UTC))
    except Exception as error:
        result = {
            "status": "OFFLINE_CHECK_FAILED",
            "stage": "LOAD",
            **failure_labels(error),
            "model_posts": 0,
        }
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "OFFLINE_WIRE_VALID" else 1


if __name__ == "__main__":
    raise SystemExit(main())
