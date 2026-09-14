# AI Service Manager

M0 engineering foundation on architecture baseline v0.28. **LOCAL/TEST only; no production data, authentication, business features, live AI or payments.** Main acceptance is separate from working-branch implementation.

## Stack and scope

Python 3.13 / FastAPI / Pydantic 2 / SQLAlchemy async + psycopg 3 / Alembic; PostgreSQL 18 + pgvector 0.8.6; React 19 / TypeScript / Vite 7. Docker Compose and GitHub Actions. Backend API/Worker/Scheduler share one runtime image; PostgreSQL durable Jobs begin at M2.1. See `docs/decisions/IMPL-001-stack.md`, `docs/TASK_REGISTER.md` and `AGENTS.md`.

M0 creates infrastructure schemas, least-privilege runtime/migration roles, the vector extension and Alembic metadata only. It does not pre-create future business tables. The RLS test table exists only inside isolated integration tests and is removed afterward.

## Local prerequisites

Git, Python 3, Docker Engine/Desktop with Linux containers and Docker Compose v2. Commands below use Bash (Linux/macOS/WSL2). Registry/package network access is needed for the first dependency resolution and image pull. Host PostgreSQL, Node and uv are not required for the Docker path. Do not run these commands against production credentials.

## First checkout

```sh
git clone https://github.com/Elefesys/ai-service-manager.git
cd ai-service-manager
git switch c0/m0-foundation
```

Until M0 is accepted, use the working branch; `main` may still contain only the initial README. Check `git rev-parse HEAD` and PR/CI state rather than assuming acceptance.

## Initial locks — one explicit operation

Normal builds require committed `uv.lock`, `frontend/package-lock.json`, `infra/images.lock.env` and `contracts/openapi.json`. The M0 bootstrap workflow generates and commits these to `c0/m0-foundation`, then runs the same verification script as CI. Missing lockfiles are a blocker, not permission for an unpinned production build.

If those files are absent in the checked-out commit, run once on a network-capable Docker machine:

```sh
sh scripts/bootstrap.sh
git diff
```

This explicit bootstrap resolves the chosen version families, records real container digests, creates package locks, formats initial Python source and exports the typed API snapshot. Review/commit the diff on the working branch before sharing it. Ordinary CI never resolves new versions or modifies source. Do not re-run bootstrap to work around a failing check without reviewing the dependency/source changes.

## Start

```sh
python3 scripts/init_local.py
docker compose --env-file infra/images.lock.env --env-file .env up -d --build
```

The init script creates random LOCAL-only credentials in `.env` without printing or overwriting them. They are excluded from Git and Docker build contexts. Runtime containers receive only runtime DB credentials; the migration process receives the separate migration identity. PostgreSQL is not published on a host port.

Business Console: `http://127.0.0.1:8080/`.
Platform Operations shell: `http://127.0.0.1:8080/ops/`.
API: `http://127.0.0.1:8000`.
OpenAPI UI: `/docs`; liveness: `/health/live`; readiness: `/health/ready`.

Readiness checks the actual runtime identity, schema revision, PostgreSQL major version and vector extension. It returns 503 on dependency/schema/privilege failure without disclosing connection details. Console routes are not security boundaries; no tenant or operator data is exposed before M1 authorization.

```sh
docker compose --env-file infra/images.lock.env --env-file .env ps
docker compose --env-file infra/images.lock.env --env-file .env down
```

`down` stops containers but preserves the named local database volume. Changing `.env` passwords does not automatically reconfigure an already initialized PostgreSQL volume; use the original LOCAL credentials or an explicit reviewed local reset. Do not delete volumes as a generic troubleshooting step.

## Verify

```sh
sh scripts/ci.sh
```

This builds and checks the backend/frontend, runs a separate disposable `asm_test` PostgreSQL service, verifies migrations and DB behavior, then starts the LOCAL shell for HTTP/reverse-proxy smoke. It stops this Compose project afterward; do not run it while relying on a separate interactive session in the same Compose project.

Checks include Ruff, mypy, unit/fixture tests, genuine PostgreSQL runtime-role/RLS/rollback/pool reuse/vector/UUIDv7 tests, worker/scheduler SIGTERM shutdown, upgrade/repeated upgrade/downgrade/re-upgrade, OpenAPI drift, TypeScript/Vitest, repeated wheel and frontend asset byte comparisons. The full production multi-tenant suite remains M1 onward. A source file describing a test is not evidence that it passed.

Reproducibility scope: locked dependencies, immutable base image references and compared backend wheel/frontend static asset bytes on the selected Linux builder. Bit-identical OCI image metadata across different builders/CPU architectures and a production release manifest are not claimed by this M0 check.

## Architecture sources

The initial repository contained only README. C0 read the supplied original project documents and verified the ten source hashes against baseline. `docs/architecture/SOURCE_MANIFEST.json` additionally pins the combined baseline. Full originals are included in the accompanying C0 source pack; their exact Git import is separately tracked as M0.SOURCE.

To import, point this command at a directory containing the eleven original Markdown files (or the source pack's `docs/architecture`):

```sh
python3 scripts/import_architecture.py /path/to/original-project-documents
git add docs/architecture
git diff --cached --stat
git commit -m "docs: import checksum-verified architecture baseline v0.28"
git push origin c0/m0-foundation
```

The importer validates every file before writing and refuses to replace a differing architectural version. Do not reconstruct or shorten canonical originals. Architecture Freeze v1.0 remains pending.

## Coordination

`docs/TASK_REGISTER.md` is the single execution register. `AGENTS.md` assigns C0–C8 responsibilities, shared-file/migration rules and evidence requirements. `docs/tasks/M1_HANDOFF.md` contains the first bounded M1.1–M1.3 tasks; C0 assigns the accepted base SHA before work starts. Synthetic fixtures A–D are deliberately non-production and do not encode actual practitioner prices or rules.

No user data, provider secrets, production infrastructure or paid service activation is required for M0. Provider/account verification and production security/operations remain explicit later gates.
