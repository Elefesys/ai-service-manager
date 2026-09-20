"""Fixed statements executed only by guarded methods on the tenant connection."""

SNAPSHOT = """
WITH evaluation AS (SELECT CURRENT_TIMESTAMP AS evaluated_at)
SELECT evaluated_at,
  COALESCE((SELECT jsonb_agg(to_jsonb(a))
    FROM platform.workspace_billing_accounts a WHERE a.workspace_id=:workspace), '[]'::jsonb)
    AS accounts,
  COALESCE((SELECT jsonb_agg(to_jsonb(m) || jsonb_build_object(
    'is_active', m.effective_from <= evaluated_at AND
       (m.effective_until IS NULL OR evaluated_at < m.effective_until)))
    FROM platform.workspace_service_modes m WHERE m.workspace_id=:workspace), '[]'::jsonb)
    AS modes,
  COALESCE((SELECT jsonb_agg(to_jsonb(s) || jsonb_build_object(
    'is_current', s.effective_from <= evaluated_at AND evaluated_at < s.effective_until,
    'revision_state', (SELECT to_jsonb(r) || jsonb_build_object(
      'plan', (SELECT to_jsonb(p) FROM platform.saas_plans p WHERE p.plan_id=r.plan_id),
      'entitlements', COALESCE((SELECT jsonb_agg(to_jsonb(e))
        FROM platform.plan_entitlements e WHERE e.plan_revision_id=r.plan_revision_id), '[]'::jsonb))
      FROM platform.saas_plan_revisions r WHERE r.plan_revision_id=s.plan_revision_id)))
    FROM platform.workspace_subscriptions s WHERE s.workspace_id=:workspace), '[]'::jsonb)
    AS history
FROM evaluation
"""

CONTACT = "SELECT * FROM platform.update_billing_contact(:version,:name,:key)"

AUDIT_ANCHOR = """
SELECT EXISTS(SELECT 1 FROM app.audit_events
WHERE workspace_id=:workspace AND occurred_at=:at AND audit_event_id=:id)
"""

AUDIT_PAGE = """
SELECT audit_event_id,occurred_at,event_type,actor_kind,actor_user_account_id,
       correlation_id,object_type,object_id,object_version,payload
FROM app.audit_events
WHERE workspace_id=:workspace
  AND (CAST(:at AS timestamptz) IS NULL OR
       (occurred_at,audit_event_id) < (CAST(:at AS timestamptz),CAST(:id AS uuid)))
ORDER BY occurred_at DESC,audit_event_id DESC
LIMIT :count
"""
