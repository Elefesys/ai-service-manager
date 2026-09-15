"""Bounded M1.1 snapshot; not a future schema/permission DSL."""

from dataclasses import fields

from asm.tenancy.types import (
    CONTEXT_SETTINGS,
    SCHEMA_REVISION,
    AccountStatus,
    ErrorCode,
    LifecycleStatus,
    MembershipRole,
    MembershipStatus,
    WorkspaceContext,
    permissions_for,
)


def contract_snapshot() -> dict[str, object]:
    result: dict[str, object] = {
        "name": "tenancy.v1",
        "down_revision": "0001",
        "columns": {
            "platform.user_accounts": ["id", "status", "version", "created_at"],
            "platform.workspaces": ["id", "status", "version", "created_at"],
            "platform.workspace_memberships": [
                "workspace_id",
                "user_account_id",
                "role",
                "status",
                "version",
                "created_at",
            ],
            "app.businesses": ["workspace_id", "id", "name", "status", "version", "created_at"],
            "app.business_members": [
                "workspace_id",
                "id",
                "business_id",
                "user_account_id",
                "name",
                "role",
                "status",
                "version",
                "created_at",
            ],
            "app.locations": [
                "workspace_id",
                "id",
                "business_id",
                "name",
                "status",
                "version",
                "created_at",
            ],
        },
        "primary_keys": {
            "platform.user_accounts": ["id"],
            "platform.workspaces": ["id"],
            "platform.workspace_memberships": ["workspace_id", "user_account_id"],
            "app.businesses": ["workspace_id", "id"],
            "app.business_members": ["workspace_id", "id"],
            "app.locations": ["workspace_id", "id"],
        },
        "platform_lookup": "platform.resolve_workspace_membership(uuid,uuid)",
        "foreign_keys": [
            ["platform.workspace_memberships", ["workspace_id"], "platform.workspaces", ["id"]],
            [
                "platform.workspace_memberships",
                ["user_account_id"],
                "platform.user_accounts",
                ["id"],
            ],
            ["app.businesses", ["workspace_id"], "platform.workspaces", ["id"]],
            ["app.business_members", ["workspace_id"], "platform.workspaces", ["id"]],
            [
                "app.business_members",
                ["workspace_id", "business_id"],
                "app.businesses",
                ["workspace_id", "id"],
            ],
            [
                "app.business_members",
                ["workspace_id", "user_account_id"],
                "platform.workspace_memberships",
                ["workspace_id", "user_account_id"],
            ],
            ["app.locations", ["workspace_id"], "platform.workspaces", ["id"]],
            [
                "app.locations",
                ["workspace_id", "business_id"],
                "app.businesses",
                ["workspace_id", "id"],
            ],
        ],
        "nullable_columns": {"app.business_members": ["user_account_id"]},
    }
    result.update(
        schema_revision=SCHEMA_REVISION,
        context_fields=[item.name for item in fields(WorkspaceContext)],
        actor_kinds=["user_account"],
        permissions_by_role={
            role.value: sorted(permission.value for permission in permissions_for(role))
            for role in MembershipRole
        },
        error_codes=[code.value for code in ErrorCode],
        statuses={
            "platform.user_accounts": [status.value for status in AccountStatus],
            "platform.workspaces": [status.value for status in LifecycleStatus],
            "platform.workspace_memberships": [status.value for status in MembershipStatus],
            **{
                f"app.{table}": [status.value for status in LifecycleStatus]
                for table in ("businesses", "business_members", "locations")
            },
        },
        context_settings=list(CONTEXT_SETTINGS),
    )
    return result
