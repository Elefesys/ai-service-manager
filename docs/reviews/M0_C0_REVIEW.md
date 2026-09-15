# M0 — C0 integration review

Date: 2026-09-15. Scope: PR #1, `c0/m0-foundation`, engineering foundation only.
Initial main: `c74db484b483fccaef7b4124b418a91979cb4be6`.
Reviewer: C0, acting on the user's explicit request to complete import, checks, review and integration. This is a C0 second-pass review, not an independently executed C8 review and not production security certification. No separate agent was launched. Architecture Freeze v1.0 remains pending; no accepted domain ADR is replaced.

## Source integrity

The original eleven attachments were verified against the pre-existing `SOURCE_MANIFEST.json`. During text transfer, mismatches in several staged files were detected, including changed wording and omitted lines. They were not accepted as architectural revisions. A deterministic restoration used staged-input SHA-256 checks plus line edits calculated from the local original bytes. Every final document was validated before writing. The combined baseline was assembled from its original header and the ten exact original files, then validated against its own original SHA-256.

Import run: `34968001558`; imported commit: `395b760175871a3d6cde10b8e01e1f9364e3bd57`.
Artifact: `m0-source-import-34968001558`, ID `10395434061`, SHA-256 `fd89f2dc453e0848341b55e93565779393e772ec682a607836af267407726751`.
C0 downloaded its source archive and independently compared all eleven resulting files byte-for-byte to the mounted original attachments: PASS. The original manifest hashes were not changed. Temporary split sources, restoration data and assembly script were removed before handoff. Historical pre-implementation and OPEN wording is preserved; implementation status is tracked separately.

Correction at acceptance: the full import SHA was mistyped in the first version of this review. It is corrected above to the value in the import artifact's `imported-commit.txt`; source documents, manifest hashes and Git history are unchanged.

## Findings and remediation

| ID | Finding | Disposition |
|---|---|---|
| M0-R1 | Canonical files absent from repository; incomplete handoff | Fixed by exact import and remote-source byte comparison above |
| M0-R2 | CI recorded dirty worktree status but did not fail on it | Fixed: explicit tracked/untracked drift gate; reports and build outputs remain ignored |
| M0-R3 | Initial lock generation/import workflows retained repository write authority after their one-time purpose | Fixed: both write workflows retired; permanent CI uses contents: read and does not persist checkout credentials |
| M0-R4 | Import rejection/preflight behavior lacked executable negative tests | Fixed: five tests for exact/idempotent copy, missing source, source drift, conflicting target and in-place drift verification |
| M0-R5 | M1 handoff could miss M0-only schema/readiness assertions | Clarified: C2 updates expected schema revision and exact allowed table set without deleting existing protection tests; applied migration 0001 is immutable |

The new import tests passed locally (5/5). Full locked-environment evidence is taken only from the final PR/main CI, not from this local test count. An early local assertion expecting different error wording was corrected to the actual importer contract; rejection itself already worked.

## Reviewed engineering boundaries

- Backend: typed LOCAL/TEST configuration; safe liveness/readiness; actual database role/schema/extension probes; bounded DB timeout; redacted failure response; dispose on shutdown. No unauthenticated business mutation endpoints or production activation.
- Database/bootstrap: separate privileged bootstrap, migration and non-owner runtime identities; restricted schema/database privileges; no runtime SUPERUSER/BYPASSRLS/DDL or membership in migration role. Test database is separate and disposable. Only infrastructure schemas/extensions/migration metadata are introduced.
- Migrations: explicit migration identity, short transaction and advisory migration lock; repeatable fresh/repeated upgrade and disposable-test downgrade/re-upgrade. Migration 0001 is not modified by this closure. Default function privilege hardening is conservatively retained on downgrade; this is not a production reverse-migration runbook.
- Real PostgreSQL tests: allow/deny reads, cross-workspace write rejection, transaction rollback, same-connection context reset, runtime DDL/role denial, vector operation/UUIDv7 and worker/scheduler shutdown. These are M0 capability probes, not a complete M1 tenant implementation.
- Worker/Scheduler: shutdown-safe shells, no fake memory queue presented as durable Jobs. Durable Inbox/Outbox/Jobs remains M2.1.
- Frontend: separate console/Ops shells, typecheck and three tests; no privileged data. Route names are not security controls; session/auth/CSRF enforcement remains M1.2.
- Fixtures: four synthetic businesses and independent price/duration/payment modes, no production publication or workspace-specific algorithm fork. Later scenario descriptions are not counted as executed business engines.
- Build/CI: committed Python/npm lockfiles and five base-image digests; locked installs; immutable pinned action revisions; wheel/static-asset repeat comparisons; genuine Docker/Linux/amd64 PostgreSQL execution. A PR run tests its virtual merge ref; final main commit must also pass.
- Local operation: loopback API/frontend exposure, no published PostgreSQL port; random ignored `.env`; no provider/customer secrets needed. CI stops the same Compose project, documented so users do not run it concurrently with an interactive stack they need to preserve.

## Residual scope and limitations

M0 has no auth/session/complete tenant suite, live AI/Telegram/payment/fiscalization, Object Storage, production backup/restore drill, complete vulnerability/container/dependency audit or production telemetry exporter. These are milestone/release obligations, not green M0 claims. External model/provider statements in the imported baseline are historical candidate assumptions, not newly verified integrations.

No bit-identical OCI metadata guarantee across builders/CPU architectures; the measured reproducibility scope is locked inputs and wheel/static asset bytes. Existing dependency deprecation and action-runtime warnings do not mean tests failed, but remain toolchain maintenance items for C6 before production. No user-PC run was performed. Private repository protection settings are not changed as part of M0 integration.

Independent C8 review remains available as a separate quality workstream and should cover the substantive tenant/auth capabilities as they arrive. This C0 review does not impersonate that work or waive production readiness gates.

## Integration decision

The reviewed M0 scope may be integrated only after the current PR head passes canonical-source validation, complete software/build/PostgreSQL checks and the clean-worktree gate. C0 must pin expected_head_sha when merging; any concurrent code change requires renewed review. After merge, confirm main CI and then record actual accepted SHA/evidence in `docs/TASK_REGISTER.md` and the C2 handoff.

M1.1 implementation is not performed by this PR. It starts on `c2/m1-1-tenant-foundation` from the exact accepted base assigned by C0. M1.2/M1.3 wait for the integrated M1.1 contract.

## Integration outcome confirmed on 2026-09-15

PR #1 is closed and merged (2026-09-15T12:43:21Z). Its actual merge commit is `1d7bb4fa0567bdd263d7910492ecf217696642de`, integrating reviewed head `8639812ce71f5cce8f2b2ed051ff01fea67d5157`. C0 read the main ref and PR metadata directly; no duplicate merge was performed.

The matching push/main run `34970531911` completed successfully. Job `104385439116` passed canonical-source validation, full verification and the clean-source gate. Artifact `10396772645` has ZIP SHA-256 `e1702634f918fb92c1a361ee5ac49a762ed58dc6b125ee85c75dd35efd2f1755`; its tested-commit is the same merge SHA and worktree-status is empty. The source archive's eleven original documents were rechecked byte-for-byte and by the original SHA-256 against project attachments: PASS.

Measured result: 20 unit/fixture/import tests + 7 real PostgreSQL integration tests + 3 frontend tests = 30 passed, plus static checks, migrations, Docker/local smoke, OpenAPI and wheel/static-asset reproducibility checks. Earlier 25-test counts describe earlier commits, not this final result.

C0 accepts M0 as engineering foundation. The single task register records VERIFIED. Documentation-only reconciliation of the register, stack integration status and handoff does not add M1 functionality or revise canonical architecture. The final C2 start message pins a verified main commit including these acceptance documents; independent C8/production/Architecture Freeze claims remain excluded.

## Technical references consulted for review

- PostgreSQL 18 row security: https://www.postgresql.org/docs/18/ddl-rowsecurity.html
- GitHub Actions token permissions: https://docs.github.com/en/actions/how-tos/security-for-github-actions/security-guides/automatic-token-authentication

The code/CI evidence, not the existence of these references, establishes what was executed.
