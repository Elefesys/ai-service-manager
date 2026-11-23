"""Finish the admitted agent operation with the same domain calculation and renderer as Console."""

from collections.abc import Awaitable, Callable

from pydantic import ValidationError

from asm.billing.validation import CanonicalUUID
from asm.configuration.models import ConfigurationModel
from asm.service_requests.assessment import AssessmentInputs, evaluate
from asm.service_requests.errors import ServiceRequestCode, ServiceRequestError
from asm.service_requests.quotes import QuoteInput, render_quote


class AgentServiceResult(ConfigurationModel):
    request_id: CanonicalUUID
    approval_id: CanonicalUUID | None
    quote_id: CanonicalUUID | None


async def finish_service_intents(
    command: Callable[[str, dict[str, object]], Awaitable[object]],
) -> dict[str, object]:
    try:
        inputs = AssessmentInputs.model_validate(await command("PLAN", {}))
        assessment = evaluate(inputs)
        raw_quote = await command(
            "ASSESS",
            {
                "expected_revision": inputs.request_revision,
                "authority_sha256": inputs.authority_sha256,
                **assessment.model_dump(mode="json"),
            },
        )
        payload: dict[str, object] = {}
        if raw_quote is not None:
            quote = QuoteInput.model_validate(raw_quote)
            payload = {**quote.model_dump(mode="json"), "text": render_quote(quote)}
        receipt = AgentServiceResult.model_validate(await command("FINISH", payload))
    except ValidationError:
        raise ServiceRequestError(ServiceRequestCode.UNAVAILABLE) from None
    return receipt.model_dump(mode="json")
