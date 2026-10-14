# C5-M3.2-CONSOLE-ESCALATIONS — owner-wait UI

C0 assignment: https://github.com/Elefesys/ai-service-manager/pull/31#issuecomment-6172495208
Base `ab06bc135f45c88203e434eacefd107412a8eb15`, tree
`3c97459793bd200dfe9720b37ea0895b4189a8bb`, schema0011.
This is the remaining owner-wait UI of M3-A10; M3 remains IN_PROGRESS.
Task status belongs to TASK_REGISTER. Final source/CI evidence belongs to the single
canonical C5 receipt in the new Draft PR, not a post-CI SHA-only commit here.

## UI rules

- The panel is mounted beside Billing/Messaging for the lifetime of Console.
  OWNER membership gates it; Business selection, billing TEST keys and channel
  availability do not. Every operation still requires the server's current authority.
- Four existing routes only. List uses limit10, stored-status filter and an opaque
  cursor. Refresh/filter/Workspace reset pagination. Each page keeps its own required
  observed_at; detail has its own projection. No frozen multi-page snapshot claim.
- Stored lifecycle, current validity/wait and reminder maintenance are distinct.
  PENDING+EXPIRED says the deadline elapsed. FAILED maintenance does not close a
  request or invent an action prohibition. Recorded reminders are internal records,
  never a delivery/read receipt. Browser time does not decide expiry.
- Resolve needs can_resolve and the current assignee; cancel uses can_cancel.
  Capture one detail's canonical IDs and exact decimal expected counters. Preserve
  answer scalars/UTF-8 and whitespace without trimming/normalizing. Cancel has no
  answer field. Resolution/closure nullable shapes are strict and displayed separately.
- Resolve/cancel save internal decisions: no manual send, Resume, composer copy or
  revival of a Turn. Fresh detail/list follow acceptance. An already displayed
  conversation with matching Workspace/Conversation/Client is explicitly marked
  as requiring history/control refresh; the receipt never substitutes current mode.
- A synchronous ref freezes actor/Workspace/Escalation/Conversation/Client/operation/
  body/key. Unknown network/5xx/invalid responses retain it in memory. Recovery
  permits an explicit retry only for the same actor/context with the same key/body.
  A later definitive rejection preserves previous ambiguity and stops retries.
  Valid200 is final acceptance: subsequent GET failure can only retry reads.
- Changing session/actor/Workspace/request immediately hides old detail/draft.
  Generation and selection guards reject late success and auth errors. Another
  context gets only a neutral outstanding-intent notice. Discard warns before acting
  that a possible committed operation is not cancelled. Reload never sends anything.
- Shared OWNER denial clears Billing/Audit/Messaging/images and this panel. Existing
  manual/CONTROL intents survive their established recovery flow. No new state bus,
  storage, endpoint, dependency, clock/scheduler mechanism or polling.

## Assertions and evidence boundary

| Criterion | New tests / assertions | Evidence type |
|---|---|---|
| UI-E01 | escalation-api tests: required page clock even empty, item/page clock equality, exact keys/enums/nullables/UTC6/UUID/int64, receipt binding and exact request text/body/key; panel paging/refresh/status and deferred page/detail | Local API/component execution; synthetic DTOs |
| UI-E02 | messaging.spec Escalation runtime queue journey: real Resume→marker→Inbox/Turn/worker creation, internal resolve+cancel, exact answer, terminal/current read, one receipt/Audit each, unchanged outbound/control counters; keyboard and @narrow | Actual browser/HTTP/PostgreSQL only when final-source browser job passes |
| UI-E03 | panel/parser PENDING+EXPIRED, revoked assignee/cancel, FAILED maintenance and recorded reminder; retained server cases listed below | Synthetic UI + separately identified accepted actual PG cases |
| UI-E04 | real route.fetch→abort after committed200, login and actual rotate/CSRF rejection, same-key/body REPLAY and one receipt/Audit; separate accepted200+GET abort with only read recovery | Actual browser/HTTP/PG counters; no fabricated success JSON |
| UI-E05 | actual two-tab Takeover material invalidation before stale resolve; no retry/answer; deferred component page/detail/POST results after identity/selection/session boundaries | Actual browser/HTTP plus deterministic component races |
| UI-E06 | real OWNER downgrade, foreign Workspace denial, peer OWNER cancel revoked assignee; disabled connection+suspended service mode still allow queue/actions; component shared boundary/session/CSRF | Actual finite TEST presets + component integration; baseline backend isolation unchanged |
| UI-E07 | all old frontend/browser assertions retained; existing private image/manual/CONTROL/UNKNOWN journeys; new keyboard/narrow and reload/no-storage assertions | Full frontend and final-source browser suites |

Retained actual PG cases in `tests/test_m3_2_escalations_postgres.py`:
`test_other_live_owner_cancel_revoked_assignee_and_no_product_channel_gate`,
`test_expiry_before_equal_after_with_no_scheduler`,
`test_not_due_does_not_spend_attempt_then_slots_once_and_equal_expiry`,
`test_allowlisted_invariant_rolls_back_domain_but_commits_dead_and_failed_maintenance`.
The accepted API suite's `test_page_db_clock_empty_nonempty_keyset_and_read_only`
proves stored PENDING/EXPIRED projection with no read writes. PR31 actual main CI
38584344077 passed all79 Escalation PG cases (61+9+9); these are not new UI execution.
New final-source CI must retain them, not rerun a new timer/fault framework for UI.

## Disposable harness

Six finite names: esc_happy/esc_narrow/esc_recovery/esc_read/esc_stale/esc_revoked.
Each seeds two ordinary inbound conversations, no image or Escalation rows. All
previous fixtures and the final happy PENDING image remain. Happy/narrow are
separate identities because the first journey deliberately disables its channel
and suspends service. Added membership permits one existing peer to cancel a
revoked assignee's request; no impersonation or credential transfer.

Runtime actions escalate-main/escalate-alternate accept no arbitrary payload/SQL/
Workspace. Browser first issues normal owner Resume. The accepted CONTROLLED marker
then flows through normal ingress and bounded worker claims. Canonical replay of
the consumed creation claim confirms creation. Existing runtime TEST/asm_runtime/
private storage guards and CALL/EFFECT ledger remain. The timer schedule is real;
no timestamp/Job-row rewriting. Read-only escalation-stats returns counts, no answer,
credential, signed URL or request body. Decisions assert CALL/EFFECT0 and no new
Message/manual receipt/Outbox/send Job/control receipt/Audit. Original worker journeys
and PENDING observation execute before these additions.

## Commands and limits (pre-publication source)

- `python scripts/import_architecture.py docs/architecture`: original11 checksums
  PASS, no canonical diff. Generated OpenAPI inspected; unchanged.
- `uv sync --frozen --offline`: existing lock installed in isolated Python3.13 venv;
  no manifest/lock change.
- `npm --prefix frontend run typecheck`: PASS.
- `npm --prefix frontend test`:294 PASS at the implementation checkpoint, including
  all prior194;99 new API/panel cases and1 additional shared denial variant.
- `.venv/bin/pytest -q tests/test_m2_4_browser_fixture.py`:61 PASS (prior43 retained).
- `.venv/bin/ruff check` and `ruff format --check` on the three allowed harness paths:
  PASS. `git diff --check`:PASS.
- `npm --prefix frontend run build`: PASS,38 modules.
- Local Docker is absent: `sh scripts/ci.sh` and `sh scripts/test_browser.sh`
  **NOT RUN locally**. Real HTTP/PostgreSQL/MinIO journeys require the штатный
  final-source PR CI; local fixture/component tests do not replace that evidence.

Old auth App tests add a panel mock to preserve exact request ordering; new App
boundary integration extends the existing MessagingPanel test and retains every
old assertion. The old browser journey bodies are unchanged; added imports and the
alternate canonical Client inventory type only support new journeys. Fixture
limits/guards/assertions are retained and extended, without sleeps in browser,
retries, skips, timeout increases or CI changes.

CONTROLLED evidence is not live Telegram or a production SLA. Canonical sources,
backend/API/DDL/OpenAPI, auth contracts, applied0001–0011, other consumers,
ConversationControl, dependencies/Compose/workflows/CI budgets are unchanged.
Next: canonical REVIEW/BLOCKED receipt, HOLD, C0 intake and independent scoped C8.

## Seed ordering correction after first runtime attempt

Initial source e54f1ab/tree86dc436 CI38609159739/attempt1 browser116007742763
stopped during seed, before journeys, with sanitized M2_4_BROWSER_WORKER_FAILED;
clean was SKIPPED. That log does not identify the underlying exception.
A deterministic interleaving regression then reproduced the old seed's exact
`Exclusive browser seed queue required` failure: a due TEST_CONSUME claim can
precede the next expected Inbox. This is confirmed unit evidence of a harness
ordering defect; it does not retroactively prove the old CI exception.

The seed now executes only bounded GROUP/MEDIA/TEST_CONSUME work between claims,
retaining the exact expected Inbox job ID and FETCH-kind assertions. SEND,
GUARDED_TEXT, ESCALATE_OWNER, timers, unrelated Inbox/FETCH still fail closed.
Six negative cases retain that boundary; the positive regression leaves the last
FETCH unclaimed. No general drain or timestamp/Job rewrite is introduced, and
runtime/storage guards,120s envelope and counters remain unchanged. The returned
sanitized seed_turns count makes real interleaving observable in the next CI.
Focused harness:61 PASS (original43 preserved); regression failed before the fix.
All runtime claims still require final-source CI. No green SHA is rerun for statistics.
