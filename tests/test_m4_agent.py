"""Real Gateway + FakeAdapter, controlled authority only; no PG/RLS/runtime claims."""

import asyncio
import copy
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from importlib.resources import files
from uuid import UUID

import pytest
from asm.ai import agent as module
from asm.ai.agent import AuthorityDecision, ContextRead, ConversationAgent
from asm.ai.context import ContextBuilder, ContextLimits
from asm.ai.contracts import AdapterResponse, GatewayConfig, ToolCall
from asm.ai.fake import FakeAdapter
from test_m4_context import fixture
from test_m4_gateway import config as gateway_config


def config(**limits):
    c = gateway_config(**({"model_calls": 2, "read_executions": 1} | limits))
    return GatewayConfig.model_validate(c.model_dump() | {"prompt_revision": "conversation_v2"})


class ControlledAuthority:
    """Only a test double. State/permission checks are not a PostgreSQL adapter."""

    def __init__(self, binding, raw, *, allowed):
        self.state = binding
        self.raw = copy.deepcopy(raw)
        self.allowed = allowed
        self.checks = []
        self.reads = []
        self.at_check = None
        self.at_read = None

    async def authorize(self, binding, boundary):
        self.checks.append(boundary)
        if self.at_check:
            result = self.at_check(binding, boundary)
            if result is not None:
                return result
        return AuthorityDecision(
            status="DENIED"
            if not self.allowed
            else "STALE"
            if self.state != binding
            else "ALLOWED",
            binding=self.state,
        )

    async def read_current(self, binding):
        self.reads.append(binding)
        if not self.allowed or self.state != binding:
            raise RuntimeError("CONTROLLED_READ_DENIED")
        if self.at_read:
            return self.at_read(binding)
        return ContextRead(binding=self.state, snapshot=copy.deepcopy(self.raw))


def setup(script=("reply",), name="v3_owner", **limits):
    raw, binding = fixture(name)
    cfg = config(**limits)
    adapter = FakeAdapter(cfg.route, script)
    authority = ControlledAuthority(binding, raw, allowed=True)
    return ConversationAgent(cfg, adapter, authority), adapter, authority, raw, binding


async def run(agent, raw, binding, **changes):
    return await agent.run(
        binding,
        raw,
        **(
            {"run_id": "controlled_context", "deadline": datetime.now(UTC) + timedelta(seconds=30)}
            | changes
        ),
    )


@pytest.mark.parametrize(
    "name",
    ["v2", "v2_guarded", "v3_owner", "v3_guarded_image", "v3_canonical", "v3_unicode_adversarial"],
)
@pytest.mark.parametrize("kind", ["reply", "handoff", "no_reply"])
async def test_single_call_candidate_preserves_scope_without_executing_business_effects(name, kind):
    agent, adapter, authority, raw, binding = setup((kind,), name)
    result = await run(agent, raw, binding)
    assert result.status == "CANDIDATE" and result.candidate.kind == kind
    assert not result.runtime_authorized and result.reads_executed == 0 and not authority.reads
    assert authority.checks == ["MODEL", "CANDIDATE"] and len(adapter.requests) == 1
    request = adapter.requests[0]
    assert request.prompt == files("asm.ai").joinpath("prompts/conversation_v2.txt").read_text(
        "utf-8"
    )
    assert request.config.prompt_revision == "conversation_v2" and request.config == agent.config
    assert all(m.role in ("context", "user") for m in request.request.messages)
    assert result.budget.calls_used == 1 and result.budget.cost_reserved == Decimal("0.10")
    assert result.calls[0].kind == "FINAL" and not hasattr(result.calls[0], "result")
    wire = request.input_json()
    for secret in (
        str(binding.workspace_id),
        str(binding.client_id),
        str(binding.conversation_id),
        binding.snapshot_digest,
    ):
        assert secret not in wire
    closed = await run(agent, raw, binding)
    assert closed.status == "STOP" and closed.reason == "CLOSED" and closed.candidate is None
    assert len(adapter.requests) == 1 and authority.checks == ["MODEL", "CANDIDATE"]


async def test_read_followup_uses_one_gateway_one_deadline_and_total_budget(monkeypatch):
    made = []
    original = module.ModelGateway

    def gateway(*args):
        value = original(*args)
        made.append(value)
        return value

    monkeypatch.setattr(module, "ModelGateway", gateway)
    agent, adapter, authority, raw, binding = setup(("tools", "handoff"), "v3_guarded_image")
    result = await run(agent, raw, binding)
    assert result.status == "CANDIDATE" and result.candidate.kind == "handoff"
    assert (
        len(made) == 1
        and len(adapter.requests) == 2
        and len(authority.reads) == result.reads_executed == 1
    )
    assert authority.checks == ["MODEL", "READ", "FOLLOWUP", "CANDIDATE"]
    first, second = adapter.requests
    assert first.request == second.request and first.config == second.config
    assert 0 < second.remaining_seconds <= first.remaining_seconds <= 30
    assert [r.budget.calls_used for r in adapter.requests] == [1, 2]
    assert result.budget.reads_reserved == 1 and result.budget.cost_reserved == Decimal("0.20")
    exchange = second.exchanges[0]
    assert exchange.calls[0].call_id == exchange.results[0].call_id == "read-1"
    tool = json.loads(exchange.results[0].result_json)
    assert tool == json.loads(ContextBuilder().build(raw, binding).view.model_dump_json())
    assert tool["owner_confirmed_text"] == raw["human_context"]["text"]
    assert tool["current"][0]["image_read"] is False
    for private in (
        str(binding.client_id),
        str(binding.business_id),
        binding.snapshot_digest,
        "CONTROLLED_GUARDS_V1",
        "actor_user_account_id",
        "file_id",
    ):
        assert private not in second.input_json()


def changed(binding, field):
    v = getattr(binding, field)
    return binding.model_copy(
        update={
            field: UUID(int=999)
            if isinstance(v, UUID)
            else v + 1
            if type(v) is int
            else "f" * 64
            if isinstance(v, str)
            else v.model_copy(update={"observation_epoch": v.observation_epoch + 1})
        }
    )


@pytest.mark.parametrize("boundary", ["MODEL", "READ", "FOLLOWUP", "CANDIDATE"])
@pytest.mark.parametrize(
    "field",
    [
        "permission",
        "workspace_id",
        "client_id",
        "conversation_id",
        "business_id",
        "control_generation",
        "context_version",
        "turn_revision",
        "activation_fence_seq",
        "resume_receipt_id",
        "native",
        "snapshot_digest",
    ],
)
async def test_revocation_scope_and_generation_changes_stop_at_every_effect_boundary(
    boundary, field
):
    agent, adapter, authority, raw, binding = setup(("tools", "reply"))

    def revoke(_binding, at):
        if at == boundary:
            if field == "permission":
                authority.allowed = False
            else:
                authority.state = changed(binding, field)

    authority.at_check = revoke
    result = await run(agent, raw, binding)
    assert result.status == "STOP" and result.candidate is None
    assert result.reason == ("AUTHORITY_DENIED" if field == "permission" else "AUTHORITY_STALE")
    assert len(adapter.requests) == {"MODEL": 0, "READ": 1, "FOLLOWUP": 1, "CANDIDATE": 2}[boundary]
    assert (
        len(authority.reads)
        == result.reads_executed
        == (1 if boundary in ("FOLLOWUP", "CANDIDATE") else 0)
    )
    assert authority.checks[-1] == boundary
    # Rejected FINAL text cannot leak back as an alternate candidate in trace metadata.
    assert "Уточните" not in result.model_dump_json()


@pytest.mark.parametrize("name", ["v2", "v3_owner", "v3_guarded_image"])
@pytest.mark.parametrize("field", ["workspace_id", "client_id", "conversation_id", "business_id"])
async def test_self_consistent_foreign_binding_still_requires_independent_permission(name, field):
    agent, adapter, authority, raw, binding = setup(name=name)
    foreign = changed(binding, field)
    # For unguarded client/conversation IDs there is no raw field to compare;
    # the server authority must reject, even though the builder can project it.
    result = await run(agent, raw, foreign)
    assert result.status == "STOP" and result.candidate is None
    assert not adapter.requests and not authority.reads


@pytest.mark.parametrize("phase", ["model", "read", "followup"])
async def test_changes_during_await_are_checked_again_before_next_effect(phase):
    agent, adapter, authority, raw, binding = setup(("tools", "reply"))
    original = adapter.complete

    async def complete(request):
        result = await original(request)
        if (
            phase == "model"
            and len(adapter.requests) == 1
            or phase == "followup"
            and len(adapter.requests) == 2
        ):
            authority.state = changed(binding, "resume_receipt_id")
        return result

    adapter.complete = complete
    if phase == "read":

        def read(_):
            authority.allowed = False
            return ContextRead(binding=binding, snapshot=copy.deepcopy(raw))

        authority.at_read = read
    result = await run(agent, raw, binding)
    assert result.status == "STOP" and result.candidate is None
    assert len(adapter.requests) == (2 if phase == "followup" else 1)
    assert len(authority.reads) == (0 if phase == "model" else 1)


@pytest.mark.parametrize("bad", ["binding", "material", "invalid", "unavailable"])
async def test_read_cannot_return_foreign_or_changed_context_for_followup(bad):
    agent, adapter, authority, raw, binding = setup(("tools", "reply"), "v2")

    def read(_):
        data = copy.deepcopy(raw)
        if bad == "unavailable":
            raise RuntimeError("PRIVATE_ERROR")
        if bad == "material":
            data["members"][0]["current"]["text"] = "FOREIGN_OR_CHANGED_TEXT"
        if bad == "invalid":
            data["private_storage_url"] = "PRIVATE_ERROR"
        return ContextRead(
            binding=changed(binding, "client_id") if bad == "binding" else binding, snapshot=data
        )

    authority.at_read = read
    result = await run(agent, raw, binding)
    assert result.status == "STOP" and result.candidate is None
    assert len(adapter.requests) == 1 and len(authority.reads) == 1
    assert "FOLLOWUP" not in authority.checks and "CANDIDATE" not in authority.checks
    assert (
        "PRIVATE_ERROR" not in result.model_dump_json()
        and "FOREIGN_OR_CHANGED_TEXT" not in result.model_dump_json()
    )


@pytest.mark.parametrize(
    "bad", ["none", "bool", "allowed_without_binding", "exception", "lying_allowed"]
)
async def test_authority_has_no_default_allow_or_uuid_only_shortcut(bad):
    agent, adapter, authority, raw, binding = setup()
    if bad == "none":
        agent.authority = None
    else:

        def check(_binding, _boundary):
            if bad == "exception":
                raise RuntimeError("PRIVATE_AUTHORITY_DETAIL")
            if bad == "bool":
                return True
            if bad == "allowed_without_binding":
                return {"status": "ALLOWED"}
            return AuthorityDecision(status="ALLOWED", binding=changed(binding, "client_id"))

        authority.at_check = check
    result = await run(agent, raw, binding)
    assert result.status == "STOP" and result.candidate is None
    assert not adapter.requests and not authority.reads
    assert "PRIVATE_AUTHORITY_DETAIL" not in result.model_dump_json()


@pytest.mark.parametrize(
    "arguments",
    [
        "{}",
        '{"query":"other"}',
        '{"query":"current","client_id":"foreign"}',
        '{"query":"current","url":"https://example.invalid"}',
        '{"query":"current","sql":"DROP TABLE"}',
        '{"query":"current","query":"current"}',
    ],
)
async def test_invalid_tool_arguments_never_execute_read(arguments):
    call = AdapterResponse(
        kind="TOOLS",
        tool_calls=(ToolCall(call_id="read-1", name="read_context", arguments_json=arguments),),
    )
    agent, adapter, authority, raw, binding = setup((call, "reply"))
    result = await run(agent, raw, binding)
    assert result.reason == "TOOL_CONTRACT" and result.candidate is None
    assert len(adapter.requests) == 1 and not authority.reads and authority.checks == ["MODEL"]


@pytest.mark.parametrize(
    "bad", ["mutation_tool", "multiple_reads", "second_read", "result_correlation"]
)
async def test_no_mutation_extra_read_or_uncorrelated_followup(monkeypatch, bad):
    if bad == "mutation_tool":
        script = (
            AdapterResponse(
                kind="TOOLS",
                tool_calls=(ToolCall(call_id="send-1", name="send_message", arguments_json="{}"),),
            ),
        )
    elif bad == "multiple_reads":
        script = (
            AdapterResponse(
                kind="TOOLS",
                tool_calls=tuple(
                    ToolCall(
                        call_id=f"read-{i}",
                        name="read_context",
                        arguments_json='{"query":"current"}',
                    )
                    for i in range(2)
                ),
            ),
        )
    else:
        script = ("tools", "tools" if bad == "second_read" else "reply")
    if bad == "result_correlation":
        original = module.ToolResult

        def corrupt(**kwargs):
            return original(**(kwargs | {"call_id": "different"}))

        monkeypatch.setattr(module, "ToolResult", corrupt)
    agent, adapter, authority, raw, binding = setup(script)
    result = await run(agent, raw, binding)
    assert result.status == "STOP" and result.candidate is None
    assert result.reason == (
        "TOOL_CORRELATION"
        if bad == "result_correlation"
        else "TOOL_CONTRACT"
        if bad == "mutation_tool"
        else "BUDGET"
    )
    assert len(adapter.requests) == (2 if bad == "second_read" else 1)
    assert (
        len(authority.reads)
        == result.reads_executed
        == (1 if bad in ("second_read", "result_correlation") else 0)
    )
    assert "CANDIDATE" not in authority.checks


@pytest.mark.parametrize(
    "script,reason",
    [
        ("refusal", "REFUSAL"),
        ("invalid", "INVALID_OUTPUT"),
        ("truncated", "TRUNCATED"),
        ("oversize", "OUTPUT_SIZE"),
        ("429", "RATE_LIMIT"),
        ("5xx", "UNAVAILABLE"),
    ],
)
async def test_model_failures_have_no_candidate_no_retry_and_no_read(script, reason):
    agent, adapter, authority, raw, binding = setup((script, "reply"))
    result = await run(agent, raw, binding)
    assert result.status == "STOP" and result.reason == reason and result.candidate is None
    assert len(adapter.requests) == 1 and not authority.reads and authority.checks == ["MODEL"]
    assert result.budget.calls_used == 1 and result.budget.cost_reserved == Decimal("0.10")


@pytest.mark.parametrize(
    "limits",
    [
        {"model_calls": 0},
        {"total_tokens": 0},
        {"cost_budget": Decimal("0.05")},
        {"input_bytes": 32},
        {"input_tokens": 1},
    ],
)
async def test_exhaustion_before_first_model_has_no_external_attempt(limits):
    agent, adapter, authority, raw, binding = setup(**limits)
    result = await run(agent, raw, binding)
    assert result.status == "STOP" and result.candidate is None
    assert not adapter.requests and not authority.reads and result.budget.calls_used == 0


@pytest.mark.parametrize(
    "limits", [{"model_calls": 1}, {"read_executions": 0}, {"cost_budget": Decimal("0.10")}]
)
async def test_no_read_when_followup_cannot_be_admitted(limits):
    agent, adapter, authority, raw, binding = setup(("tools", "reply"), **limits)
    result = await run(agent, raw, binding)
    assert result.reason == "BUDGET" and result.candidate is None
    assert len(adapter.requests) == 1 and not authority.reads


async def test_unknown_cost_is_not_zero_or_a_budget_refund():
    agent, adapter, authority, raw, binding = setup(("unknown_cost",))
    result = await run(agent, raw, binding)
    assert result.status == "CANDIDATE" and result.calls[0].cost.status == "UNKNOWN"
    assert result.calls[0].cost.amount is None and result.budget.cost_reserved == Decimal("0.10")


@pytest.mark.parametrize(
    "where", ["MODEL", "READ", "FOLLOWUP", "CANDIDATE", "read_port", "model_call"]
)
async def test_one_deadline_covers_authority_read_model_and_candidate(where):
    agent, adapter, authority, raw, binding = setup(("tools", "reply"), duration_seconds=0.1)
    original = authority.authorize

    async def authorize(bound, at):
        if at == where:
            await asyncio.Event().wait()
        return await original(bound, at)

    authority.authorize = authorize
    if where == "read_port":

        async def hang(_):
            authority.reads.append(binding)
            await asyncio.Event().wait()

        authority.read_current = hang
    if where == "model_call":
        adapter.script = ("timeout",)
    result = await asyncio.wait_for(run(agent, raw, binding), 1)
    assert result.reason in ("DEADLINE", "TIMEOUT") and result.candidate is None
    assert (
        len(adapter.requests)
        == {"MODEL": 0, "READ": 1, "FOLLOWUP": 1, "CANDIDATE": 2, "read_port": 1, "model_call": 1}[
            where
        ]
    )
    assert len(authority.reads) == (1 if where in ("FOLLOWUP", "CANDIDATE", "read_port") else 0)


async def test_cancel_and_concurrent_repeat_cannot_restart_gateway():
    agent, adapter, authority, raw, binding = setup(("timeout",))
    task = asyncio.create_task(run(agent, raw, binding))
    for _ in range(100):
        if adapter.requests:
            break
        await asyncio.sleep(0)
    assert len(adapter.requests) == 1
    again = await run(agent, raw, binding)
    assert again.reason == "CLOSED" and again.candidate is None
    task.cancel()
    stopped = await task
    assert stopped.reason == "CANCELLED" and stopped.candidate is None
    assert stopped.budget.calls_used == 1 and stopped.budget.cost_reserved == Decimal("0.10")
    assert len(adapter.requests) == 1 and not authority.reads


async def test_essential_context_overflow_stops_before_authority_model_or_read():
    agent, adapter, authority, raw, binding = setup()
    agent.builder = ContextBuilder(ContextLimits(max_bytes=512))
    result = await run(agent, raw, binding)
    assert result.reason == "CONTEXT_TOO_LARGE" and result.candidate is None
    assert not adapter.requests and not authority.reads and not authority.checks


@pytest.mark.parametrize("invalid", ["prompt", "calls", "reads", "runtime"])
def test_agent_requires_reviewed_scope_and_cannot_widen_gateway_limits(invalid):
    cfg = config(
        **(
            {"model_calls": 3}
            if invalid == "calls"
            else {"read_executions": 2}
            if invalid == "reads"
            else {}
        )
    )
    adapter = FakeAdapter(cfg.route)
    if invalid == "prompt":
        cfg = cfg.model_copy(update={"prompt_revision": "conversation_v1"})
    if invalid == "runtime":
        cfg = cfg.model_copy(
            update={"route": cfg.route.model_copy(update={"eligibility": "APPROVED"})}
        )
    with pytest.raises(ValueError):
        ConversationAgent(cfg, adapter, None)
    assert not adapter.requests
