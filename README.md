# AI Service Manager

Modular monolith; architecture v0.28. Stack decision: `docs/decisions/IMPL-001-stack.md`.
Current tasks and acceptance: [`docs/TASK_REGISTER.md`](docs/TASK_REGISTER.md). The M4 source prerequisites for M5 are integrated and verified in LOCAL/TEST. M5.1A configuration/publication is integrated and verified in LOCAL/TEST. The accepted M5 plan and the sole active assignment, M5.1B led by C4, are in [`docs/tasks/M5_HANDOFF.md`](docs/tasks/M5_HANDOFF.md).
All eleven canonical architecture documents are in `docs/architecture/`, byte-identical to the approved project attachments. Their historical pre-implementation/Freeze-pending wording is preserved; current implementation status belongs in the task register, not in a rewritten historical snapshot.

## Scope

API/Worker/Scheduler, LOCAL/TEST owner auth and tenant isolation, billing/entitlements and Audit, durable PostgreSQL Inbox/Outbox/Jobs, Telegram text/private inbound images and manual replies, conversation control, escalation, owner-confirmed native context, the guarded M4 text AI runtime, and the M5.1A owner configuration API with validated atomic publication and rollback.

PR #44 is merged at `c9d42878ebfaf6def59d24cf7f95b1f74646eb83`; [post-merge CI43157266312](https://github.com/Elefesys/ai-service-manager/actions/runs/43157266312) passed 12/12 jobs. [M4 acceptance](docs/tasks/M4_HANDOFF.md) preserves the exact scope: code verification and an owner-confirmed assisted AI reply are not full live pilot verification. Receiver ACK/fence and the complete live HUMAN/Resume journey remain open, without blocking M5 development. The PC/Happ/SSH route and unavailable replacement-photo content remain explicit limitations.

M5 follows accepted [IMPL-005](docs/decisions/IMPL-005-m5-pilot-knowledge.md). PR #46 is merged at `6c27be8487f3f8792cf01ed2a0fcdde130ea7a52`; [post-merge CI43245856346](https://github.com/Elefesys/ai-service-manager/actions/runs/43245856346) passed 12/12 jobs and the tree matches the reviewed candidate. M5.1A provides the owner API for services, structured rules and confirmed FAQ, draft validation/preview, immutable releases, atomic publish/rollback and bounded active reads. C0 issued only M5.1B from this actual main: published knowledge in guarded AI replies and a minimal owner UI. Those two features are not implemented by M5.1A. Retrieval, Vision, portfolio display and intake remain later slices. Accepted [IMPL-004](docs/decisions/IMPL-004-m4-pilot-ai.md) boundaries remain; this handoff grants no images, embeddings, real data, paid session or VM actions.

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

Read `AGENTS.md`, the current M5 handoff and IMPL-005, the accepted M4 boundaries in IMPL-004, then applicable canonical architecture/ADRs and `09_IMPLEMENTATION_PLAN.md` before changing code. Verify all source hashes with the command above. Do not change manifest hashes to hide an accidental source modification; current architecture revisions require an explicit reviewed decision; they do not silently rewrite the imported historical source baseline.

C0 owns the single task register and integration. [`M5_HANDOFF`](docs/tasks/M5_HANDOFF.md) defines the sole active M5.1B scope; no later slice is assigned. M1–M4 handoffs retain acceptance/history and explicit live limitations. C0 assigns each task an actual accepted full main commit and bounded file/migration scope. A repository merge does not update the existing VM; historical operator commands are not current deployment instructions. Do not prebuild future milestones or assume separate chats share a checkout.
