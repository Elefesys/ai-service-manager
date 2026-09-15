# M1.1 — C0 acceptance after C8 targeted re-review

## Decision and authority

C0 accepts M1.1 tenant foundation and closes finding C8-M1.1-01. The single task register records VERIFIED after actual merge and successful push/main CI. This is not acceptance of all M1, authentication/session, Client-level authorization, Architecture Freeze v1.0 or production readiness. No canonical ADR is revised.

The user supplied C8's report dated 2026-09-16, PASS on exact head `fa98e714d78485f8d07108294263c89d90a6e7f0`, no new blockers. Original attachment SHA-256: `4fcdd7ff1a44d0979cfea7d7967409a96737962ba3fbbbaa73c34a50268dbd57`. C8 independently reviewed the implementation/tests and existing C2 CI; it explicitly did NOT execute a new PostgreSQL run in the re-review. Its earlier failing regression was independently executed and retained byte-identically in the fixed implementation. C0 does not relabel existing evidence as a second C8 execution.

## Exact integration evidence

Repository: Elefesys/ai-service-manager; PR #3.
Original accepted M0/base: `7eaa9aa63b3f27215f6eb970fb9eb857fd291f62`.
Reviewed C2 head: `fa98e714d78485f8d07108294263c89d90a6e7f0`.
Actual implementation merge: `b480d864a246cb0573b40fa5211f66625a71de91`.
Matching source tree: `66b87d3797bff856df449c878347766e147c5c01`.

C0 re-read the unchanged base/head, accepted closure in PR review `5214994803`, reconciled stale PR body and used expected_head_sha for the merge. No force-push, auto-merge, repeated blind merge or C2 rewrite was used.

New push/main CI: https://github.com/Elefesys/ai-service-manager/actions/runs/35015308300
Job `104537130545`: every step SUCCESS.
Artifact `10415043854`, name `m0-verification-35015308300`.
ZIP SHA-256: `b0b23c7b795f7084201a804a9285ad7634106627c9f5366c284d0b2f77287cc0`.
Tested-commit equals the actual merge above; worktree-status is empty. C0 downloaded and checked ZIP/hash, recomputed all 74-file Git tree paths/modes and matched all 11 canonical architecture originals byte-for-byte to original attachments and manifest hashes. The integrated tree equals the reviewed implementation tree.

24 non-integration + 62 PostgreSQL + 3 frontend = **89 passed**, not a sum across CI runs. All lint/format/mypy/types, migration cycles, readiness, OpenAPI, wheel/assets comparison, Docker/HTTP/proxy smoke and clean-source gates passed. Full execution occurred on GitHub Linux/amd64 Docker runner; C0's local evidence processing is not another local PostgreSQL test.

## Resolved finding

C8-M1.1-01 was a P2 context/transaction-contract defect under DBAPI AUTOCOMMIT, not a demonstrated RLS bypass or data leak. Current code checks actual psycopg autocommit before lookup/setters/context publication and rejects it with CONTEXT_INVALID. A same-connection pre-yield check requires matching Workspace, nonempty XID/fence, non-autocommit and INTRANS; mismatch rejects before publication with TRANSACTION_STATE. No implicit mode switch or hidden commit was introduced.

All eight C8 cases are unchanged (test-file SHA-256 `114f67314af6997aa11064cc786bea0da196f87abf6698b2ae38c281857d0737`); six new cases cover three AUTOCOMMIT paths, real rollback and two binding corruptions. Original C8 run `34987895881` failed on the old code. Fixed C2 run `34994578775` passed all 89 cases; the new main run independently executes the integrated snapshot. Earlier failures remain historical.

## Accepted scope and handoff

Only six tables and migration 0002 -> 0001, tenant-safe relations/RLS, bounded trusted context/UOW, permissions and CAS. No future database, login, billing or provider integration. Migrations, roles, guards, canonical sources and locks were not altered during acceptance. The documentation-only follow-up updates the existing register/handoff and adds this receipt; C0 verifies its diff and final main before assigning C1 an exact starting SHA.

M1.2 is C1 backend/auth contract, then C5 login UI, with C0/C8 review and C2/C0 migration review. M1.3 remains unissued in the sequential queue. Schema/API/library choices absent from canonical files remain explicit implementation decisions, not retroactive LOCKED architecture. Destructive downgrade tests are restricted to disposable TEST, never a production rollback recommendation.
