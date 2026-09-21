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

## M2.1 Audit compatibility

The existing Audit endpoint adds only `MESSAGE_SEND_REQUESTED` with object type
`MESSAGE`, version `"1"`, a live command actor reference, and exact payload
`{"content_type":"TEXT"}`. Both billing variants, permissions and cursor semantics
are unchanged. The strict backend/OpenAPI/frontend union includes this event; no
message body, provider IDs, command keys or claims are part of Audit. No messaging
HTTP routes are introduced in this LOCAL/TEST kernel.

## M2.3 owner messaging API

The generated OpenAPI adds five routes under `/api/v1/workspaces/{workspace_id}`:

| Method | Relative path | Result |
| --- | --- | --- |
| GET | `/channel-connections` | Current observed connection statuses |
| GET | `/conversations` | Conversations and reply-window expiry |
| GET | `/conversations/{conversation_id}/messages` | History with current file/delivery state |
| POST | `/conversations/{conversation_id}/messages` | `202` durable manual text intention |
| POST | `/conversations/{conversation_id}/messages/{message_id}/files/{file_id}/read-grant` | `200` private signed GET grant |

All five require the current session cookie and live OWNER membership. Both POSTs
require the configured Origin and current CSRF token. Send accepts exactly `{text}`,
one `Idempotency-Key` in the existing ASCII format, no `If-Match`, and no query.
Text is preserved exactly: 1–4096 Unicode scalars, at most 16384 UTF-8 bytes, no
NUL/surrogates/whitespace-only value. Do not trim, normalize, split or add formatting.
Only this exact POST route has a 64 KiB JSON body limit; other owner/auth routes
retain their 4 KiB limit.

The three collections return `{items,next_cursor}` and accept only one `limit`
(1–100, default 25) and one `cursor`. Ordering is `(created_at,id)` descending;
message `occurred_at` is separate provider event time. Pass `next_cursor` unchanged
until null. It is scoped to the endpoint, Workspace and, for history, conversation;
an invalid or missing anchor is `422 INVALID_REQUEST`. It does not freeze history
or grant authorization. UUIDs are lowercase canonical, timestamps have six UTC
fractional digits, and versions/file sizes are decimal strings. Nullable fields
are always present. Image content type remains `IMAGE_REFERENCE`; READY file
manifests expose only MIME type, byte size, width and height.

Connection `AVAILABLE` reports a fresh observed enabled/can-reply snapshot. It does
not promise an open 24-hour reply window, entitlement, or successful delivery.
Stale/invalidated observations are `UNVERIFIED`; a failed last probe is
`UNAVAILABLE`; confirmed disabled and missing rights are `DISABLED` and
`RIGHTS_MISSING`. CONTROLLED LOCAL/TEST connections have no Telegram observation
or reply-window timestamp. Every new Telegram send refreshes the connection outside
the database transaction; the worker performs its own preflight before dispatch.

New sends require the `messaging.manual_send` BOOLEAN/ESSENTIAL capability through
the real entitlement service. NORMAL, GRACE and LIMITED allow a valid true key;
inactive state, SUSPENDED, false or missing keys reject the new intention with
`409 NOT_ALLOWED`. Structural billing failure is `503` with the separate
`{error:{code:"BILLING_STATE_UNAVAILABLE",state_reason}}` envelope; ordinary
dependency/auth admission failure remains code-only `503 UNAVAILABLE`. Billing GET
still exposes exactly the five original TEST decisions. History, inbound processing
and private grants remain available independently of product restrictions.

Send returns only `{workspace_id,receipt_id,message_id,accepted_at,outcome}`, with
`outcome` ACCEPTED or REPLAY and the original accepted metadata. `202` confirms
commit of the intention, never delivery. Read history for PENDING, DISPATCHING,
SENT, FAILED or UNKNOWN. SENT means Telegram accepted the message, not that the
recipient received or read it. An ambiguous send becomes UNKNOWN and is not sent
again automatically. There is no retry/resend endpoint.

After a lost response or ambiguous 5xx, preserve the original actor, Workspace,
conversation, exact text and key. Recover the current session/CSRF, confirm that
identity/context still matches, and repeat that exact intention. A new key is a
new send, not recovery. Authorized exact replay is recognized before new product,
route or observation checks and does not call Telegram or send again; UNKNOWN
remains UNKNOWN. Different text/context for an existing key is
`409 IDEMPOTENCY_KEY_CONFLICT`. Revoked/downgraded authority cannot inspect a receipt.

Read-grant accepts exactly `{}` and no query, with no idempotency requirement.
Unknown, mismatched, foreign or not-ready relations return `404 NOT_FOUND`.
The response is `{url,expires_at}` with a fixed 60-second lifetime. The URL is a
bearer grant: use its original signed host/path, keep it out of logs, and do not
cache or distribute it. Revocation prevents new grants; already issued URLs may
remain usable until expiry. No separate storage key or provider identifier is
returned. Local signing uses the current owner unit; network reads occur after
the response.

These contracts prepare the API for C5. The complete Console journey and external
Telegram account/HTTPS verification remain separately evidenced M2 work.
