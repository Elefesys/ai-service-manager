import json
from dataclasses import FrozenInstanceError
from pathlib import Path
from uuid import uuid4

import pytest
from asm.tenancy import (
    AuthenticatedAccount,
    ErrorCode,
    MembershipRole,
    Permission,
    TenancyError,
    WorkspaceContext,
    current_workspace_context,
)
from asm.tenancy.contract import contract_snapshot
from asm.tenancy.types import permissions_for


def test_tenancy_contract_snapshot():
    expected = json.loads(Path("contracts/tenancy.v1.json").read_text())
    assert contract_snapshot() == expected
    assert expected["schema_revision"] == "0002"
    assert expected["down_revision"] == "0001"
    assert len(expected["columns"]) == 6


def test_actor_and_context_are_immutable_server_values():
    actor = AuthenticatedAccount(uuid4())
    context = WorkspaceContext(uuid4(), actor, frozenset({Permission.READ}), uuid4())
    with pytest.raises(FrozenInstanceError):
        actor.user_account_id = uuid4()
    with pytest.raises(FrozenInstanceError):
        context.workspace_id = uuid4()
    with pytest.raises(TypeError):
        AuthenticatedAccount(uuid4(), kind="ai")
    with pytest.raises(TypeError):
        AuthenticatedAccount(uuid4(), permissions=["OWNER"])
    with pytest.raises(TenancyError, match="CONTEXT_INVALID"):
        AuthenticatedAccount("not-an-authenticated-id")


def test_permissions_are_explicit_not_owner_wildcards():
    assert permissions_for(MembershipRole.PROVIDER) == {Permission.READ}
    for role in (MembershipRole.OWNER, MembershipRole.ADMIN):
        assert permissions_for(role) == {Permission.READ, Permission.WRITE}
    with pytest.raises(TenancyError, match="ACCESS_DENIED"):
        permissions_for("AI")
    for code in ErrorCode:
        assert str(TenancyError(code)) == code.value


def test_no_ambient_workspace_context():
    with pytest.raises(TenancyError, match="CONTEXT_REQUIRED"):
        current_workspace_context()
