"""One mixed Audit store through the existing authenticated HTTP endpoint."""

import pytest
from asm.billing.models import AuditPage
from test_auth_postgres import auth as auth
from test_auth_postgres import headers, login
from test_m1_3_api_postgres import initialize
from test_m2_1_postgres import command, conversation, query
from test_m2_1_postgres import messaging as messaging
from test_tenancy_postgres import A
from test_tenancy_postgres import db as db
from test_tenancy_postgres import seeded as seeded

pytestmark = pytest.mark.integration


async def test_mixed_billing_message_audit_http_cursor_and_strict_payload(auth, messaging):
    h = messaging
    async with h.migrator.begin() as c:
        await initialize(c, A)
    try:
        response = await login(auth)
        assert response.status_code == 200
        csrf = response.json()["csrf_token"]
        patched = await auth.client.patch(
            f"/api/v1/workspaces/{A}/billing-account",
            json={"expected_version": "1", "contact_display_name": "After"},
            headers={**headers(auth.client, csrf), "Idempotency-Key": "billing-key"},
        )
        assert patched.status_code == 200
        receipt = await command(
            h, await conversation(h), value="private message must stay out of Audit"
        )
        first = await auth.client.get(f"/api/v1/workspaces/{A}/audit-events?limit=2")
        assert first.status_code == 200
        page = AuditPage.model_validate(first.json())
        assert [item.event_type for item in page.items] == [
            "MESSAGE_SEND_REQUESTED",
            "BILLING_ACCOUNT_CONTACT_UPDATED",
        ]
        assert page.items[0].object_id == str(receipt.message_id)
        assert page.items[0].payload.model_dump() == {"content_type": "TEXT"}
        assert "private message" not in first.text and "claim_token" not in first.text
        assert page.next_cursor is not None
        second = await auth.client.get(
            f"/api/v1/workspaces/{A}/audit-events?limit=2&cursor={page.next_cursor}"
        )
        assert second.status_code == 200
        assert [item.event_type for item in AuditPage.model_validate(second.json()).items] == [
            "WORKSPACE_BILLING_PROVISIONED"
        ]
        assert second.json()["next_cursor"] is None
        # The same command preserves both its receipt and the existing Audit cursor.
        replay = await command(
            h,
            (await query(h, "SELECT id FROM app.conversations"))[0]["id"],
            value="private message must stay out of Audit",
        )
        assert replay.audit_event_id == receipt.audit_event_id
        assert (
            await auth.client.get(f"/api/v1/workspaces/{A}/audit-events?limit=2")
        ).json() == first.json()
    finally:
        for table in (
            "platform.billing_contact_command_receipts",
            "app.audit_events",
            "platform.workspace_service_modes",
            "platform.workspace_subscriptions",
            "platform.workspace_billing_accounts",
        ):
            suffix = (
                " AND event_type<>'MESSAGE_SEND_REQUESTED'" if table == "app.audit_events" else ""
            )
            await query(
                h,
                f"DELETE FROM {table} WHERE workspace_id=:ws" + suffix + " RETURNING workspace_id",
                ws=A,
            )
