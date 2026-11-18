# AI Service Manager

Modular monolith; architecture v0.28. Stack decision: `docs/decisions/IMPL-001-stack.md`.
Current tasks and acceptance: [`docs/TASK_REGISTER.md`](docs/TASK_REGISTER.md). The M4 source prerequisites for M5 are integrated and verified in LOCAL/TEST. M5.1A configuration/publication and M5.1B published-knowledge replies with a minimal owner UI are integrated and verified in synthetic LOCAL/TEST. The accepted M5 plan and the sole active assignment, C8’s independent review of the repaired v7 conversation, intake and portfolio photo in PR #54, are in [`docs/tasks/M5_HANDOFF.md`](docs/tasks/M5_HANDOFF.md).
All eleven canonical architecture documents are in `docs/architecture/`, byte-identical to the approved project attachments. Their historical pre-implementation/Freeze-pending wording is preserved; current implementation status belongs in the task register, not in a rewritten historical snapshot.

## Scope

API/Worker/Scheduler, LOCAL/TEST owner auth and tenant isolation, billing/entitlements and Audit, durable PostgreSQL Inbox/Outbox/Jobs, Telegram text/private inbound images and manual replies, conversation control, escalation, owner-confirmed native context, the guarded M4 text AI runtime, and the M5 owner configuration API/UI with validated atomic publication, rollback and published knowledge in guarded text replies.

PR #44 is merged at `c9d42878ebfaf6def59d24cf7f95b1f74646eb83`; [post-merge CI43157266312](https://github.com/Elefesys/ai-service-manager/actions/runs/43157266312) passed 12/12 jobs. [M4 acceptance](docs/tasks/M4_HANDOFF.md) preserves the exact scope: code verification and an owner-confirmed assisted AI reply are not full live pilot verification. Receiver ACK/fence and the complete live HUMAN/Resume journey remain open, without blocking M5 development. The PC/Happ/SSH route and unavailable replacement-photo content remain explicit limitations.

M5 follows accepted [IMPL-005](docs/decisions/IMPL-005-m5-pilot-knowledge.md). PR #46 is merged at `6c27be8487f3f8792cf01ed2a0fcdde130ea7a52`; [post-merge CI43245856346](https://github.com/Elefesys/ai-service-manager/actions/runs/43245856346) passed 12/12 jobs and the tree matches the reviewed candidate. M5.1A provides the owner API for services, structured rules and confirmed FAQ, draft validation/preview, immutable releases, atomic publish/rollback and bounded active reads. PR #47 integrates M5.1B at `6942150e9a4ab96222f49702b2e9977178b04e74`; [post-merge CI43389871150](https://github.com/Elefesys/ai-service-manager/actions/runs/43389871150) passed 12/12 jobs, with the exact reviewed tree. M5.1B adds published-knowledge context, activation-currentness guards, additive migration0019 and the minimal owner UI. The v3 provider contract is verified through MockTransport; a new real provider call is not claimed. C0 accepted M5.2A functional capability from the existing owner-reported assisted synthetic run and matching history evidence. Embedding usage allows absent completion_tokens under the accepted modality-specific rule in IMPL-005. PR #48 is merged at `8eeeede1b4a05537b0afb8c29992e8b681eaeb65`, with the reviewed tree. [Post-merge CI43600856660](https://github.com/Elefesys/ai-service-manager/actions/runs/43600856660) is successful: the Docker service setup failure in one job was retried on the same source; the other successful results were retained. M5.2A is integrated/verified within those code/CI and assisted-synthetic boundaries. PR #49 integrates M5.2B at `70804866f6838f77c12bd281febae47887559d75`, with the exact reviewed tree `a6ee68b5a6b0cd2091b4cecc89614bada4db2585`. [Post-merge CI43693059853](https://github.com/Elefesys/ai-service-manager/actions/runs/43693059853) passed 12/12 jobs on attempt1. Confirmed sources/builds and bounded keyword/exact-vector retrieval are integrated/verified in synthetic LOCAL/TEST; embeddings remain DISABLED by default and CONTROLLED uses MockTransport. PR #50 integrated M5.2C image analysis, private owner portfolio review/publication and confirmed-work matching. PR #51 fixes the foundation job budget at 60 minutes. Both are integrated and verified in synthetic LOCAL/TEST at `8d98593bc739666176968c5d76b9c01a2a711686`, with the reviewed tree `a14ed9b69e3529ac060bc015b9a24dcea515ef9b`. [Post-merge CI43818223732](https://github.com/Elefesys/ai-service-manager/actions/runs/43818223732) passed 12/12 jobs on attempt1, including the complete foundation suite and cleanup; the earlier cancelled run remains historical. Vision/embedding runtime remains DISABLED by default. PR #52 adds one authorized portfolio photo with caption through guarded delivery, visible in the owner Inbox. M5.2D is integrated and verified in synthetic LOCAL/TEST at `220606193208a1ef082732e4dfcdf1f2ffbea857`, tree `d15f9a75346ab881449010745cbe0216081b78cf`; [post-merge CI43894664260](https://github.com/Elefesys/ai-service-manager/actions/runs/43894664260) passed all 12 jobs on attempt 1. This does not authorize real photo delivery. PR #53 integrates preliminary intake, the owner Action Center summary and private DurationCase examples at `c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba`, tree `11c987fb12e4f88d27da3737911c468d520269b8`; [post-merge CI44018352191](https://github.com/Elefesys/ai-service-manager/actions/runs/44018352191) passed all 12 jobs on attempt1. M5.1A–M5.3A are integrated and verified within their tested synthetic LOCAL/TEST scope. C1 returned the v7 fixes in PR #54. C0 verified the explicit conflict-resolution regression, the controlled single-photo journey and the candidate CI. C8 now owns the independent K01–K12 review on head `9ead66496b37d78d35654c9a7b32ee66d1b30a7a`. Main has migration 0023 and the candidate has 0024. C6 remains on hold and M6 awaits M5 acceptance. Accepted [IMPL-004](docs/decisions/IMPL-004-m4-pilot-ai.md) boundaries remain; paid/provider execution, VM actions and real client data require separate authorization.

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

C0 owns the single task register and integration. [`M5_HANDOFF`](docs/tasks/M5_HANDOFF.md) defines C8’s active M5.3B review and its acceptance criteria. M6 awaits a separate assignment. M1–M4 handoffs retain acceptance/history and explicit live limitations. C0 assigns each task an actual accepted full main commit and bounded file/migration scope. A repository merge does not update the existing VM; historical operator commands are not current deployment instructions. Do not prebuild future milestones or assume separate chats share a checkout.
