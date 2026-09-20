# Versioned contracts

M0 exports the infrastructure API to `openapi.json` using `scripts/export_contracts.py`. Bootstrap generates the initial snapshot; ordinary CI rejects schema drift. No speculative domain commands, events or provider adapters are defined here. Regeneration is reviewed, never silently performed by ordinary CI.

## M1.3 billing API consumer notes

The generated `openapi.json` is the API DTO/schema source. It adds exactly three
owner routes to the seven preserved M1.2 routes: `GET /api/v1/workspaces/{workspace_id}/billing`
(`billing:read`), `PATCH /api/v1/workspaces/{workspace_id}/billing-account`
(`billing:manage`), and `GET /api/v1/workspaces/{workspace_id}/audit-events`
(`audit:read`). These permissions are separate from the unchanged tenancy/auth
contracts. Session and live OWNER membership are checked on every request/replay.
Service mode and entitlements do not gate contact administration, auth or existing
Business reads. No provider calls or new migration are introduced.

Use the existing HttpOnly cookie and configured Origin. PATCH needs the current
memory-only CSRF token and exactly one `Idempotency-Key` (ASCII `[A-Za-z0-9._:-]{1,128}`);
`If-Match` is forbidden. The exact body is `{expected_version,contact_display_name}`.
Versions and integer limits are decimal **strings**, including a valid limit `"0"`;
do not round through JavaScript Number. Names trim only U+0020 and retain Unicode
composition/case. UUIDs are lowercase canonical; timestamps retain all six UTC
fractional digits. CORS adds PATCH and Idempotency-Key to the existing allowlists.

PATCH returns immutable command metadata, never the current contact. A normalized
no-op keeps the version and writes no contact Audit; stale is checked before no-op.
Replay of the same key/body returns the original receipt even after later changes.
`409 STALE_STATE` means refresh GET and resolve the stale edit. `409 IDEMPOTENCY_KEY_CONFLICT`
means the key was already used for a different normalized request; do not silently
overwrite the intention. `404 NOT_FOUND` is an authorized missing billing account.

On a lost response/network failure/ambiguous 5xx, the tenant transaction may already
be committed. Keep the original intention, body (including expected_version), and
key. Recover current-session/bootstrap/login and CSRF using the accepted M1.2 flow;
confirm the current account/Workspace is still the intended actor/context. Retry the
**same** key/body only for that same pending intention and current authorization,
then GET current billing state. Do not turn ambiguity into a new key/new write or
blindly replay after the user changes identity, Workspace or intention. A 401/403
does not authorize receipt observation and does not prove the earlier operation
rolled back. Replay is not a substitute for GET, and no exactly-once HTTP delivery
is promised.

Errors retain the exact `{error:{code}}` shape. Only structural billing GET uses
`{error:{code:"BILLING_STATE_UNAVAILABLE",state_reason}}`; both it and the separate
code-only `UNAVAILABLE` can return 503. `state_reason` is never a nullable extension
of the common/auth error. Invalid strict input or cursor is safe `422 INVALID_REQUEST`.

Audit accepts only `limit` (1..100, default 25) and a single opaque cursor, ordered
by `(occurred_at DESC,audit_event_id DESC)`. Use `next_cursor` unchanged until null;
it is scoped to the authorized Workspace and does not freeze concurrent history.
It is not a credential. Audit contains only event metadata and the accepted payload
`{}` or `{changed_fields:["contact_display_name"]}`, never contact values or keys.

These are consumer notes for the implemented R4 contract, not authorization to
start C5. C0 API review/integration and separate main CI remain prerequisites.
