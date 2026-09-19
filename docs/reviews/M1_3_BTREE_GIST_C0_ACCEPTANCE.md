# C0 — M1.3 btree_gist prerequisite acceptance

Дата: 2026-09-20.

## Verdict

**PASS. MIGRATION 0004 MAY BE RESERVED.**

Этот receipt принимает только DB prerequisite gate перед M1.3 implementation. Он не принимает migration 0004 как реализованную и не меняет статус M1.3 milestone: M1.3 остаётся `IN_PROGRESS`.

## Accepted main / contract base

До coordination записи actual main:
- commit `ce585d67168489083e9b94e4be4f5669b16a8552`;
- tree `ace73cdf8163428eb74872c35ce9e920d5e9066c`.

M1.3 pre-DDL contract уже INTEGRATED / VERIFIED:
- `docs/tasks/M1_3_CONTRACT.md`;
- Git blob `d1e80cb9242a4c0a88e2762bb17d46fa4d9f3320`;
- SHA-256 `0d33a26aa13fb3eda34b0a5c07a4a11dc263b1ee37ce9e3fda126f53e0c0282a`.

## Why remote probe was needed

Первоначальный C2 READ-ONLY preflight в Codex sandbox корректно вернул CHANGES_REQUESTED/fail-closed: exact Docker image не мог зарегистрировать layer из-за `unshare: operation not permitted`. Это было environment limitation, а не PostgreSQL/`btree_gist` incompatibility finding.

C0 разрешил одноразовый GitHub-hosted test-only workflow на отдельном Draft PR. Он не является product source и не должен попадать в main.

## Exact probe snapshot

PR #11:
- final state: CLOSED / NOT MERGED;
- base: `ce585d67168489083e9b94e4be4f5669b16a8552`;
- final head: `fca70041c86a859fd1aa8fcb06c95d2a0a830681`;
- permanent delta: только `.github/workflows/m1_3_btree_gist_preflight.yml`.

GitHub PR virtual merge/tested commit:
- `e1e327162297a556a99d8873a741f775a13aacf2`;
- tree `44dc6a2c85cc95045c8001812c78c47941f7998d`.

Первоначальный special run был SKIPPED из-за branch guard mismatch. C0 исправил только guard; DB logic probe не ослаблялась.

## Special prerequisite evidence

Run `35463399932`: SUCCESS.

Artifact:
- ID `10589963101`;
- SHA-256 `180ff8829976ff3d457ea186c4142d32a434ab71bb38afe2b6bfc1027e42ff87`;
- C0 скачал и проверил 16 evidence files.

Exact image:
- RepoDigest `pgvector/pgvector@sha256:2ba9ca5f2e7daa0f0e7723cba1ee9167bab54efd3640516a44ac1a928dd67e7a`;
- image ID `sha256:b551e63a5606bdd3127b12a8120c6df8d71c812b29a7faf944b034cb9beb644a`.

PostgreSQL:
- `PostgreSQL 18.6 (Debian 18.6-1.pgdg12+2)`;
- `server_version_num=180006`;
- vector `0.8.6`, namespace `extensions`;
- Alembic current `0003 (head)`.

`btree_gist`:
- available versions 1.2…1.8;
- default `1.8`;
- installed `1.8`;
- metadata for 1.8: superuser=true, trusted=true, relocatable=true, no fixed schema, no requires;
- installed namespace `extensions`;
- second `CREATE EXTENSION IF NOT EXISTS ... WITH SCHEMA extensions` leaves version and namespace unchanged.

UUID GiST:
- schema `extensions`;
- opclass `gist_uuid_ops`;
- family `gist_uuid_ops`;
- access method `gist`;
- default=true;
- input type `uuid`;
- equality strategy `3`, operator `uuid = uuid`.

Disposable exact exclusion proof under `SET ROLE asm_migrator`:
- exact two-column GiST exclusion table created in `app`;
- same Workspace adjacent `[)` intervals accepted;
- overlap for another Workspace accepted;
- same Workspace overlap raised expected `exclusion_violation`;
- accepted row count remained 3;
- probe table dropped.

Roles/privileges:
- `asm_admin`: superuser/createdb/createrole/replication/bypassrls true as bootstrap admin identity;
- `asm_migrator`: all false;
- `asm_runtime`: all false;
- `asm_migrator` DB CREATE=false;
- `asm_migrator` extensions USAGE=true, CREATE=false;
- `asm_runtime` extensions USAGE=true, CREATE=false;
- schema owners: `app` and `platform` = `asm_migrator`; `extensions` = `asm_admin`.
No privilege broadening was needed for migrator to create the exclusion in its owned app schema after admin extension installation.

Fail-before-domain-DDL:
- intentional impossible extension version raised `M1_3_PREREQUISITE_MISMATCH`;
- sentinel `app._m13_should_not_exist` absent=true.

Final probe git-status evidence was empty.

## Regression evidence on same snapshot

Run `35463399929`: SUCCESS.

Artifact:
- ID `10591045912`;
- SHA-256 `beddda7af582007be61160443921a6cfcf5de5b606d877ce032dd328ead1b17f`;
- tested commit `e1e327162297a556a99d8873a741f775a13aacf2`;
- worktree-status empty;
- reconstructed source tree `44dc6a2c85cc95045c8001812c78c47941f7998d`.

## C0 decision

Prerequisite gate is CLOSED / PASS.

C0 reserves:
- migration file `migrations/versions/0004_billing_entitlements_audit.py`;
- revision `0004`;
- down_revision `0003`.

Reservation is a task/implementation queue decision, not a REVISED architecture ADR. No LOCKED architecture decision is changed.

C2 owns the only DDL writer for this slice. The implementation must preserve exact accepted R4; changes to D-01…D-13 require a new explicit C0 decision.

PR #11 remains closed and unmerged. Its workflow must not be merged into main.
