"""Synthetic publication fixtures and an explicitly controlled authority port."""

from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

from asm.ai.agent import KnowledgeAuthorityDecision, KnowledgeContextRead
from asm.ai.database import decoded
from asm.ai.runtime_contracts import PreparedKnowledgeRun
from m5_configuration_fixtures import configuration_bundle
from test_m4_runtime_database import prepared


def knowledge_run(*, bundle=None, published=True):
    old = prepared()
    release = str(uuid4()) if published else None
    activation = "1" if published else "0"
    pin = {
        "projection_revision": "business_knowledge_v1",
        "business_id": str(old.binding.business_id),
        "release_id": release,
        "activation_version": activation,
    }
    active = {
        "schema_version": 1,
        "workspace_id": str(old.binding.workspace_id),
        "business_id": str(old.binding.business_id),
        "activation_version": activation,
        "release_id": release,
        "source_draft_version": "1" if published else None,
        "published_by": str(uuid4()) if published else None,
        "published_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ") if published else None,
        "bundle": deepcopy(bundle if bundle is not None else configuration_bundle())
        if published
        else None,
        "structured_rules_authoritative": True,
    }
    raw = old.model_dump(mode="json")
    raw["config"]["prompt_revision"] = "conversation_v3"
    raw.update(knowledge_pin=pin, active_projection=active)
    return decoded(PreparedKnowledgeRun, raw)


class ControlledKnowledgeAuthority:
    """No DB/RLS claim: the test must explicitly grant or revoke this one pin."""

    def __init__(self, run, *, allowed):
        self.run = run
        self.allowed = allowed
        self.stale = False
        self.boundaries = []
        self.reads = []

    async def authorize(self, binding, knowledge_pin, boundary):
        self.boundaries.append(boundary)
        status = "ALLOWED"
        if not self.allowed:
            status = "DENIED"
        elif self.stale or binding != self.run.binding or knowledge_pin != self.run.knowledge_pin:
            status = "STALE"
        return KnowledgeAuthorityDecision.model_validate(
            {"status": status, "binding": binding, "knowledge_pin": knowledge_pin}
        )

    async def read_current(self, binding, knowledge_pin):
        self.reads.append((binding, knowledge_pin))
        return KnowledgeContextRead(
            binding=self.run.binding,
            knowledge_pin=self.run.knowledge_pin,
            active_projection=self.run.active_projection,
            snapshot=self.run.snapshot,
        )
