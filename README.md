# AI Service Manager

M0 engineering foundation. Architecture v0.28; stack decision: `docs/decisions/IMPL-001-stack.md`.
Current task and acceptance state: `docs/TASK_REGISTER.md`. C0 review: `docs/reviews/M0_C0_REVIEW.md`.
All eleven canonical architecture documents are in `docs/architecture/`, byte-identical to the approved project attachments. Their historical pre-implementation/Freeze-pending wording is preserved; current implementation status belongs in the task register, not in a rewritten historical snapshot.

## Scope

API/Worker/Scheduler shells, Business Console/Platform Ops shells, PostgreSQL 18 + pgvector 0.8.6, separate database identities, infrastructure-only migration, locked builds, real PostgreSQL tests, synthetic fixtures A–D and CI. There are no production customer data, business tables, auth implementation, real AI/payment integrations or durable job queue yet. Durable Inbox/Outbox/Jobs belongs to M2.1. The RLS capability probe is not the M1 tenant-security implementation.

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
The Ops shell contains no privileged data and is not an authorization boundary. Auth and permissions begin at M1. `ASM_ENVIRONMENT` permits only LOCAL/TEST; this is not a production deployment configuration.

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
```

`ci.sh` builds locked images, uses a separate ephemeral `asm_test` database, runs Python/TypeScript/real-PostgreSQL tests, migration cycles, contract drift checks, wheel/static-asset byte comparisons and local-stack HTTP smoke. It stops this Compose project on completion; do not run concurrently with an interactive stack that must stay running.

GitHub CI additionally rejects dirty tracked/untracked source and records the actual tested SHA, source archive and logs. A PR run tests its merge ref; the post-merge main run proves the final integration commit. CI has read-only repository permission. Completed one-time bootstrap/import write workflows were removed.

Reproducibility means locked dependencies/image inputs and matching wheel/static asset bytes on the tested Linux/amd64 toolchain. Bit-identical OCI metadata across builders/CPU architectures is not claimed. No user-machine run, live provider test, comprehensive vulnerability audit or production readiness is inferred from CI success.

## Architecture and work distribution

Read `AGENTS.md`, canonical `docs/architecture/01_ARCHITECTURE_SPEC.md`, applicable ADRs and `09_IMPLEMENTATION_PLAN.md` before changing code. Verify all source hashes with the command above. Do not change manifest hashes to hide an accidental source modification; approved future architecture revisions require explicit review and a new documented source baseline.

C0 owns the single task register and integration. C2 starts M1.1 only from the accepted full commit assigned by C0; `docs/tasks/M1_HANDOFF.md` defines the bounded scope and tests. The initial README-only commit is not a valid M1 base. Do not prebuild future business schemas or assume separate chats share a checkout.
