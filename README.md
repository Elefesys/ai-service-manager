# AI Service Manager

Modular monolith; architecture v0.28. Stack decision: `docs/decisions/IMPL-001-stack.md`.
Current tasks and acceptance: [`docs/TASK_REGISTER.md`](docs/TASK_REGISTER.md). M1 is accepted in its LOCAL/TEST scope; the next execution plan is [`docs/tasks/M2_HANDOFF.md`](docs/tasks/M2_HANDOFF.md).
All eleven canonical architecture documents are in `docs/architecture/`, byte-identical to the approved project attachments. Their historical pre-implementation/Freeze-pending wording is preserved; current implementation status belongs in the task register, not in a rewritten historical snapshot.

## Scope

API/Worker/Scheduler, LOCAL/TEST server auth and Business read, Business Console login/session recovery, LOCAL/TEST billing/entitlements and the minimal owner contact/Audit screen, the separate Platform Ops shell, PostgreSQL 18 + pgvector 0.8.6, separate database identities, locked builds and real PostgreSQL tests. There are no production customer data, public signup/reset/MFA, Business mutations, real AI/payment integrations or durable job queue yet. Durable Inbox/Outbox/Jobs belongs to M2.1.

## LOCAL start

Prerequisites: Git, Python 3, Bash and Docker with Linux containers / Compose v2. On Windows use the Bash commands in WSL2. Standard builds use committed Python/npm locks and image digests; do not rerun dependency bootstrap for an ordinary checkout.

```sh
git clone https://github.com/Elefesys/ai-service-manager.git
cd ai-service-manager
# Use the accepted main commit assigned by C0, or the explicitly assigned review branch.
python3 scripts/init_local.py
docker compose --env-file infra/images.lock.env --env-file .env up -d --build
```

Console: `http://127.0.0.1:8080/`; Ops shell: `/ops/`; API docs: `http://127.0.0.1:8000/docs`.
The Ops shell contains no privileged data and is not an authorization boundary. A Business login grants no operator access. `ASM_ENVIRONMENT` permits only LOCAL/TEST; this is not a production deployment configuration. Synthetic login provisioning and the real-browser gate are documented in [`docs/tasks/M1_2_UI_RUNBOOK.md`](docs/tasks/M1_2_UI_RUNBOOK.md).

`init_local.py` creates random local credentials, never prints them and refuses to overwrite an existing `.env`. Do not commit `.env` or change its credentials while retaining an already-initialized PostgreSQL volume without a deliberate rotation procedure. PostgreSQL is not exposed on a host port. API and frontend bind to loopback.

```sh
# Stop without deleting the local named database volume.
docker compose --env-file infra/images.lock.env --env-file .env down
```

Do not add `--volumes` unless intentional destruction of disposable local data is required.

## Verification

```sh
python3 scripts/import_architecture.py docs/architecture
sh scripts/ci.sh
sh scripts/test_browser.sh
```

`ci.sh` builds locked images, uses a separate ephemeral `asm_test` database, runs Python/TypeScript/real-PostgreSQL tests, migration cycles, contract drift checks, wheel/static-asset byte comparisons and local-stack HTTP smoke. It stops this Compose project on completion; do not run concurrently with an interactive stack that must stay running.

GitHub CI additionally rejects dirty tracked/untracked source and records the actual tested SHA, source archive and logs. A PR run tests its merge ref; the post-merge main run proves the final integration commit. CI has read-only repository permission. Completed one-time bootstrap/import write workflows were removed.

Reproducibility means locked dependencies/image inputs and matching wheel/static asset bytes on the tested Linux/amd64 toolchain. Bit-identical OCI metadata across builders/CPU architectures is not claimed. No user-machine run, live provider test, comprehensive vulnerability audit or production readiness is inferred from CI success.

## Architecture and work distribution

Read `AGENTS.md`, canonical `docs/architecture/01_ARCHITECTURE_SPEC.md`, applicable ADRs and `09_IMPLEMENTATION_PLAN.md` before changing code. Verify all source hashes with the command above. Do not change manifest hashes to hide an accidental source modification; approved future architecture revisions require explicit review and a new documented source baseline.

C0 owns the single task register and integration. [`M2_HANDOFF`](docs/tasks/M2_HANDOFF.md) defines the next sequential scope; M2 implementation is not yet accepted. [`M1_HANDOFF`](docs/tasks/M1_HANDOFF.md) is closed history. C0 assigns each task an actual accepted full main commit and bounded file/migration scope. Do not prebuild future milestones or assume separate chats share a checkout.
