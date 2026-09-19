# C0 — M1.3 pre-DDL contract acceptance

Дата: 2026-09-20.

## Verdict

**M1.3 PRE-DDL CONTRACT — ACCEPTED.**

Это приёмка только docs-only контракта `docs/tasks/M1_3_CONTRACT.md`. M1.3 как milestone остаётся `IN_PROGRESS`: DDL, migration, runtime/backend/frontend implementation и production enablement ещё не интегрированы и не VERIFIED.

## Exact accepted snapshot

PR #9, branch `codex/-m1.3-ddl`, exact reviewed head:

- commit: `4d371069bd094757c410f50cd7bbe9725249dd7b`;
- tree: `b1be94654bb4539f42b8e93f44c61609ccc0dc91`;
- contract Git blob: `d1e80cb9242a4c0a88e2762bb17d46fa4d9f3320`;
- contract SHA-256 UTF-8: `0d33a26aa13fb3eda34b0a5c07a4a11dc263b1ee37ce9e3fda126f53e0c0282a`.

C2 final targeted read-only re-review: **PASS**. User-provided C2 report SHA-256: `a19dc887801fa7fbe4d12dd75d8a8a8ebf49fc65d3e5abeb5d9b8bd88c55f5a0`.

`C2-M1.3-R3-01`, `C2-M1.3-R3-02`, `C2-M1.3-R3-03` закрыты C0 на уровне pre-DDL contract. Исторические `C2-M1.3-R2-08` и `C2-M1.3-R2-09` считаются содержательно разрешёнными через mapped R3 findings; их старые REMAINING-записи остаются историей. Семь ранее закрытых R2 findings не переоткрываются.

## Regression evidence

Exact canonical head прошёл PR-context run `35458868525` — SUCCESS.

GitHub CI checkout:
- virtual merge `caea72d02492142b21da69fe35e57a0857894f59`;
- tree `ec924223d89f076de01880f0c621017eba5167fa`;
- parents: current main `3e57f1dcf4567a72b8a4bddbdb512139b700e2e3` и exact contract head `4d371069bd094757c410f50cd7bbe9725249dd7b`.

Результаты:
- 105 Python non-integration;
- 105 real PostgreSQL integration;
- 30 frontend;
- 6 Playwright;
- 246 distinct regression cases;
- foundation/browser clean-source PASS.

Artifact `10589571468`, SHA-256 `e71e0b8535ef5292333053a5e26e79d82e684da9dd0d89a63293f9b4fe2a9541`. C0 проверил `tested-commit.txt`, пустой `worktree-status.txt`, reconstructed source tree и exact contract SHA-256.

Это regression evidence существующего приложения и exact docs snapshot; оно не является доказательством ещё не существующей M1.3 DDL/runtime/browser implementation.

## Current main note

Current main `3e57f1dcf4567a72b8a4bddbdb512139b700e2e3` имеет tree `721b205f2cdc8ba8405ef47d001f2e4e82e286f9`, идентичный ранее принятому main `049b212f135f09c025d2f81badc810fa7c2c9d13`. Разница — только история временного transport add/delete; file delta отсутствует. Revert/force-push не требуется и не разрешён.

## Accepted contract scope

Приняты:
- exact eight-table inventory;
- Workspace billing isolation независимо от schema placement;
- immutable `DRAFT -> SEALED` plan revision/entitlement set;
- LOCAL/TEST synthetic catalog serialization и lock order;
- finite non-overlapping Subscription intervals;
- separate Workspace service mode;
- one coherent entitlement snapshot/read policy;
- exact RLS/grant/runtime surface;
- typed `platform.update_billing_contact(...)` command with Workspace scoping;
- immutable idempotency receipt and replay/CAS semantics;
- truthful atomic Audit for provisioning/contact mutation;
- exact fingerprint bytes/vectors;
- three `/api/v1` routes, strict DTOs/cursor/error union;
- future additive CORS obligation for PATCH + Idempotency-Key;
- LOCAL/TEST initializer fresh/repeat/conflict semantics.

D-01…D-13 remain the accepted design directions for this slice. No prior LOCKED ADR is REVISED by this acceptance.

## Implementation gate

Contract acceptance does **not** automatically allocate migration `0004`.

Before any M1.3 domain DDL, C2 must perform a read-only prerequisite check against the exact pinned DB image `pgvector/pgvector@sha256:2ba9ca5f2e7daa0f0e7723cba1ee9167bab54efd3640516a44ac1a928dd67e7a` and current bootstrap/roles:

1. exact PostgreSQL/pgvector image identity;
2. `btree_gist` availability and version;
3. required UUID GiST operator class;
4. relocatability / installation into schema `extensions`;
5. idempotent admin/bootstrap preflight for existing databases already at `0003`;
6. no `CREATE` privilege grant to `asm_migrator`;
7. fail-before-domain-DDL behavior when prerequisite is missing.

External source review identifies the pinned digest as pgvector 0.8.6 on PostgreSQL 18 and PostgreSQL 18 documents UUID support in `btree_gist`; this is not a substitute for execution against the exact pinned image. Therefore successor `0004` remains unallocated until that preflight PASS.

After PR #9 is merged and actual main CI is verified, C0 issues that separate C2 prerequisite task from the actual merged main SHA. Only after PASS does C0 reserve migration `0004` / down_revision `0003` and issue the DB implementation slice. Backend/API and later UI work follow the integrated DB contract; no parallel DDL writer.

## Integration permission

This acceptance-sync itself is docs-only. After its exact published head passes the normal PR foundation/browser clean-source gates with no unexpected delta, C0 permits a normal merge commit of PR #9 into main. No squash/rebase/force-push/auto-merge or protection bypass.

After merge, an actual push/main CI run is required. Only after that run is checked may the merged main SHA be used as the implementation base.

PR #9 integrates the accepted contract, not the M1.3 implementation. M1.3 remains `IN_PROGRESS`.
