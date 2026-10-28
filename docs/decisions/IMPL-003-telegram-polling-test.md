# IMPL-003 — opt-in Telegram polling for the recovered TEST deployment

Date: 2026-10-26. Decision: REVISED / user approved in the recovery session.
Implementation task: C6-M3-TELEGRAM-POLLING-01, REVIEW (CI/live acceptance pending).
Base: 5c074beb4a47521b8c11a820f580673ec1c2cce2.
Branch: c6/telegram-polling-recovery.

Telegram repeatedly reports a fresh webhook connection timeout at the correct
Selectel address. Accepted ingress events, image processing and manual replies
succeed, but new events remain at Telegram. Packet observations do not establish
the exact network fault. The existing outbound Telegram-only VPN route works.

For this separate LOCAL/TEST deployment, add one persistent receiver using
official getUpdates through that route. It posts the authentic provider update
to the existing private API webhook boundary with the existing secret. The API
continues to own authentication, routing, durable ingress and deduplication.
There are no new schema, billing, conversation-policy or frontend changes.

The receiver needs the bot/webhook credentials but no database or storage
credentials. One fixed internal API origin; fixed official Telegram origin;
verified TLS, no redirects or ambient proxy settings. Reuse the accepted client
transport and socket cleanup; only long-poll read/total and payload budgets differ.
Request one update at a time with a positive 20-second wait. Confirm an update
with the next offset only after a complete local HTTP 200 / {ok:true} response.
Never confirm on timeout, cancellation, rejection or malformed response.
No offset is persisted: restarts, uncertain reads and long suspensions start
from the earliest unconfirmed event and rely on durable ingress replay handling.
Unsupported/rejected events remain unconfirmed and are visible as a blocked state.

Opt-in deployment is a separate Compose project using the current immutable
backend/operator image, a read-only receiver file and the three already-created
networks. Existing application containers and egress state are not recreated.
Start the receiver waiting for webhook removal; verify bot identity and local API
readiness before deleting only the expected webhook with drop_pending_updates=false.
The receiver never mutates webhook configuration. Rollback stops the receiver
before restoring the exact expected webhook, preserving unconfirmed events.
Do not run old activation/capture commands while polling is selected.

Acceptance: no early ACK; lost local response/restart replay is deduplicated;
provider failure and rate limiting preserve events; unknown/conflicting receiver
state fails closed; bounded and secret-free I/O/status; startup before mode switch;
one local receiver; rollback ordering; live Client text/photo and one manual reply.
Local/mock tests are not live VM or PostgreSQL evidence. Full M3 is not closed.

Validation candidate: 30 focused unit/model tests pass, including replay after a
lost local/provider response, restart, stale offset, startup waiting, conflict
backoff, private deployment drift, interruption after webhook deletion and rollback
ordering. Ruff check/format pass. The previously accepted activation fixture also
produces receipts accepted by this controller. Two added PostgreSQL tests exercise
the canonical HTTP handler, a real transaction failure before/after commit, replay
and one resulting message; these require the project's integration environment.

Operator entry point: `python3 scripts/telegram_polling_recovery.py enable` on
the accepted asmoperator host, with the receiver as its sibling. The distributed
single-file copy embeds that receiver verbatim. `status` reports current receiver
and provider mode; `rollback` stops the receiver before restoring the webhook.
No credentials are entered or included in the distributed file. Existing local
activation/preparation helpers and private receipts must match their accepted pins.
The new receiver restarts unless explicitly stopped. This does not attest that
all pre-existing application services will survive a VM reboot. Keep the VM on
through live text/photo/manual-reply acceptance; do not run old connection capture
or activation helpers while polling is selected.

Sources: https://core.telegram.org/bots/api#getupdates and
https://core.telegram.org/bots/api#deletewebhook (checked 2026-10-26).
