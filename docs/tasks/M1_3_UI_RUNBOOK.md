# M1.3 C5 — owner UI and browser verification

Implementation follows the accepted R4 and generated `contracts/openapi.json`;
no API/schema/DDL/auth contract changes. This runbook records implementation and
execution, not C0 acceptance. M1.3 remains IN_PROGRESS; PR #15 stays Draft.

## Owner Console

After the existing LOCAL/TEST login, select a Workspace with OWNER membership.
The panel reads subscription, independently active service mode and decisions
from the server. Decimal versions/limits (including zero) and microsecond UTC
strings remain exact. Structural503, inactive subscription, unavailable reads and
live403 have distinct displays. Contact administration remains available in
restricted/inactive states. Ops contains no billing/Audit surface.

The contact form uses the last confirmed GET version. A submit freezes the actor,
Workspace, exact body, expected_version and crypto-generated key in page memory.
Repeated submit and edits are blocked until the intention is resolved. An
ambiguous response displays an unknown result. Use **Проверить сессию для повтора**
(or login after401), then **Повторить исходное сохранение**. A successful current
session and owner GET are required before this explicit bounded retry. It reuses
the original body/version/key, then reads current state; a second ambiguous result
requires another explicit recovery. No background mutation loop exists.

Actor/Workspace changes detach the intention and hide its contents. They never
replay it in another context. The user can explicitly finish it without retry,
with the unknown-result notice. Reload loses in-memory intention and performs
reads only. CSRF/password/body/key never enter persistent browser storage or URLs.
A confirmed PATCH followed by read failure retries GET only. STALE_STATE preserves
the draft separately and requires explicit saving with the newly read version;
key conflict stops the intention until an explicit user decision.

Audit uses limit10 and an unchanged opaque cursor, stops at null and resets on
refresh or Workspace change. The renderer exposes only bounded event metadata,
without contact values, keys or fingerprints. All reads, writes and pages check
context generation and actor/Workspace ownership for both success and failure.

## Reproducible checks

```sh
npm --prefix frontend ci --ignore-scripts --no-audit --no-fund
npm --prefix frontend run typecheck
npm --prefix frontend test
npm --prefix frontend run build
python3 scripts/import_architecture.py docs/architecture
sh scripts/ci.sh
sh scripts/test_browser.sh
```

The last two commands require Docker and the existing pinned images. The existing
GitHub workflow executes both on the published PR snapshot and checks a clean
source tree. The browser gate additionally requires the existing locked
Playwright Chromium installation, as configured by that workflow. No dependency,
image, workflow or backend default changes are needed.

The browser runner provisions separate named synthetic fixtures for happy/stale/
recovery/isolation/foreign/inactive/restricted/mode_inactive journeys. They use
`initialize_local_billing` with explicit TEST intervals 2000–2100, with narrowly
scoped interval/mode updates for the three state fixtures. Only the isolation
fixture permits the finite `downgrade` action; `stats` returns version and counts,
never contact/key/credentials. Helpers reject non-TEST, non-asm_test and unexpected
identity before writes. The existing tmpfs, rendered Compose validation,
unprivileged API, private0600 files and cleanup remain in place. The browser TEST
overlay alone uses the C0-authorized rate capacity300/1000/100.

## Evidence boundary and handoff

The 30 accepted frontend tests retain every assertion; the existing auth suite
isolates the new owner component, while the new Console integration test covers
401/bootstrap/login/focus with the real component. All six accepted browser
journeys remain unchanged. Added tests cover strict DTO/errors/Unicode, zero/max
bigint, state distinctions, permissions, paging, stale conflict, read failure after
PATCH200, bounded recovery, context switches and late success/error ownership.

New real journeys: owner UPDATE/NOOP and Audit pagination (desktop + narrow/keyboard),
second-session stale conflict, lost delivery after actual route.fetch200/commit,
authenticated foreign denial/live downgrade, three real inactive/restricted
states, and credentialed cross-origin PATCH/disallowed-header preflight. The
lost-response scenario compares exact body/key in memory and checks one version
increment, one receipt and one contact Audit through the TEST provisioning role.
All application calls continue through asm_runtime. Component mocks are not
claimed as PostgreSQL/browser evidence.

Final published SHA/tree, actual tested merge SHA/parents/tree and CI results are
reported in PR #15 and the C5 return to C0; no self-referential SHA-only commit is
required. UI/M1.3 acceptance, merge and separate actual main verification remain C0.
