# IMPL-001 — M0 implementation stack

Date: 2026-09-15
Decision status: LOCKED under the user's explicit C0/M0 delegation; no stack choice is revised by acceptance.
Integration status: accepted in main with M0, PR #1 merge commit 1d7bb4fa0567bdd263d7910492ecf217696642de; push/main CI 34970531911 SUCCESS. See docs/TASK_REGISTER.md for acceptance evidence. Architecture Freeze v1.0 remains pending.
Basis: uploaded baseline v0.28 and 09_IMPLEMENTATION_PLAN.md; initial main c74db484b483fccaef7b4124b418a91979cb4be6 contained only README.md.

## Decision

- Modular monolith in Python 3.13: FastAPI, Pydantic v2, SQLAlchemy 2.0 async Core/session-capable engine and psycopg 3. One backend image, API/Worker/Scheduler entrypoints.
- SQL-first reviewed Alembic migrations. Separate bootstrap admin, migration and runtime identities. Runtime is neither SUPERUSER nor BYPASSRLS nor schema/table owner.
- PostgreSQL 18 with pgvector 0.8.6. Only infrastructure schemas/extensions/migration metadata at M0. No business tables, real tenant/auth implementation, durable job queue, AI adapters or payment code yet.
- React 19 + TypeScript + Vite 7, static Business Console / Platform Ops shells. They contain no privileged data; authorization is an M1 obligation, not a route-name security boundary.
- uv 0.10.0 and uv.lock for Python; npm and package-lock.json for frontend. Resolve initial locks on a network-capable development runner, then normal builds use frozen/ci installs. Do not call an unlocked build reproducible.
- pytest + pytest-asyncio + HTTPX; Ruff and mypy; Vitest + React Testing Library. Real PostgreSQL migration/transaction/RLS/pgvector capability probes; temporary test objects are not the future business schema.
- Docker Compose for LOCAL and integration CI; GitHub Actions. Pin resolved base-image digests in infra/images.lock.env. No production deployment or paid services.
- PostgreSQL durable Jobs remain the LOCKED architecture choice (ADR-139). M0 provides only shutdown-safe process shells; Inbox/Outbox/Jobs lease/reclaim begins at M2.1, not a fake in-memory queue.

## Rationale and trade-offs

Python offers explicit integer/Decimal arithmetic, typed validation and the AI integration ecosystem without putting LLM decisions into domain authority. SQLAlchemy/psycopg expose PostgreSQL transactions and native SQL; reviewed Alembic SQL keeps RLS, composite FKs and future exclusion constraints visible. React/Vite matches the static responsive console requirement without an additional server-side rendering runtime. This uses two languages; OpenAPI/JSON Schema will be the boundary, never separately hand-maintained business truth. SQLAlchemy is not a tenant-security boundary. Short transactions, server-created context and real runtime-role tests remain necessary.

Django and a TypeScript-only backend are viable alternatives, not architecture violations; neither is selected here. Django's admin-first conventions are unnecessary for the exception-first domain-command console. A single-language backend would reduce tooling, but needs especially careful bigint monetary serialization. Redis/Celery/BullMQ, Kafka, Kubernetes, dedicated vector DB and speculative provider adapters are not introduced.

## Authority and unresolved items

No existing ADR is superseded. Applicable: ADR-002–006, 008–011, 033, 047–048, 107–109, 116, 125–127, 132, 135–146, 159–161, 191–212, 216. OPEN-067 is answered by this implementation decision; the original source snapshot must not be silently edited. Exact resolved patches/digests and measured results are recorded separately. Production PostgreSQL SKU/extension availability, actual provider accounts, security hardening, backup/restore and business configuration remain OPEN at their assigned milestones.

The original canonical documents were absent from the initial Git tree and are now imported byte-for-byte in docs/architecture. Source integrity is checked against the original SOURCE_MANIFEST.json; historical architecture status text is preserved. This file does not replace Architecture Spec or ADR-001–274.

## Verification references (checked 2026-09-15)

- https://fastapi.tiangolo.com/features/
- https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- https://www.psycopg.org/psycopg3/docs/api/connections.html
- https://www.postgresql.org/docs/18/ddl-rowsecurity.html
- https://github.com/pgvector/pgvector
- https://alembic.sqlalchemy.org/en/latest/cookbook.html
- https://docs.astral.sh/uv/concepts/projects/sync/
- https://docs.npmjs.com/cli/v11/commands/npm-ci
- https://vite.dev/guide/

Documentation compatibility is not execution evidence. M0 acceptance is backed by the actual main CI and artifact recorded in the task register; it does not certify production readiness.
