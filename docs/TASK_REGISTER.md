# AI Service Manager — единый task register

Ответственный: C0. Архитектура v0.28; implementation decision IMPL-001.
Исходный main: `c74db484b483fccaef7b4124b418a91979cb4be6`.
Рабочая ветка M0: `c0/m0-foundation`. Draft PR: https://github.com/Elefesys/ai-service-manager/pull/1.
Текущий SHA читается из Git; принятого M0 commit на main пока нет. Код M0 подготовлен текущей C0-сессией; роли ниже обозначают ответственность областей, не работу отдельно запущенных агентов. Независимый C8 review пока не проводился.

Состояния: TODO → IN_PROGRESS → REVIEW → INTEGRATED → VERIFIED. BLOCKED всегда содержит причину. REVIEW + PASS означает проверенную рабочую ветку, не приёмку main.

| ID | Цель | Зависимости | Ведущий | Статус | Проверка / результат | Следующий шаг |
|---|---|---|---|---|---|---|
| M0.ACCESS | Repository, main и запись | — | C0 | VERIFIED | GitHub read, новая ветка и реальные commits | Доступ подтверждён; main не менялся |
| M0.BASELINE | Spec/ADR/baseline/plan | ACCESS | C0 | REVIEW | 10 SHA-256 совпали с baseline; перечень ADR в IMPL-001 | Завершить SOURCE |
| M0.SOURCE | Точный импорт оригиналов в Git | BASELINE | C0 | BLOCKED | Manifest/importer есть; 11 оригиналов прочитаны и проверены во вложениях проекта | Импортировать из AI_Service_Manager_Architecture_Import_v0.28.zip командой scripts/import_architecture.py и закоммитить. Не заменять пересказом |
| M0.STACK | Выбор и фиксация стека | BASELINE | C0/C1/C2/C6 | REVIEW | IMPL-001; manifests, locks и real CI PASS | Принять вместе с M0 |
| M0.BACKEND | API/Worker/Scheduler shell | STACK | C1/C0 | REVIEW | Lint, strict mypy, health/schema/env tests и real shutdown PASS | C0/C8 review |
| M0.FRONTEND | Business Console/Ops shells | STACK | C5/C0 | REVIEW | TypeScript, 3 Vitest tests, Docker build, повторная сборка PASS | C0/C8 review |
| M0.DB | PG18/vector/roles/migrations | STACK | C2/C0 | REVIEW | Bootstrap и migration upgrade/replay/downgrade/re-upgrade PASS | C2/C8 review; без domain tables |
| M0.LOCAL | Docker/local и smoke | BACKEND/FRONTEND/DB/LOCK | C6/C0 | REVIEW | Чистый Docker runner поднял стек; HTTP/proxy smoke и shutdown PASS | Пользовательский workstation smoke отдельно не проводился |
| M0.TEST | Существенные real PG tests | DB | C8/C0 | REVIEW | 7 real PostgreSQL tests PASS, не SQLite/mock | C8 review M0 probes; полная tenant authorization — M1 |
| M0.LOCK | Locks/digests/reproducibility | STACK | C6/C0 | REVIEW | uv.lock, package-lock.json, 5 image digests; 2 wheel/asset builds совпали | Дальше менять только явно и с review |
| M0.CI | Полный проверочный pipeline | LOCAL/LOCK | C6/C8/C0 | REVIEW | Run 34889375796 SUCCESS; head c89b839c56d14c184650423a18ec35d1fc22de41 | Проверять актуальный PR head перед merge |
| M0.FIXTURES | Synthetic A–D | STACK | C0/C8 | REVIEW | Matrix, UUID, strict money, env guards PASS в locked CI | Не переносить тестовые цены в production defaults |
| M0.HANDOFF | Правила, реестр, M1.1–M1.3 | BASELINE/STACK | C0 | REVIEW | AGENTS.md и docs/tasks/M1_HANDOFF.md опубликованы | После SOURCE/review/merge назначить принятый base SHA |
| M0.ACCEPT | Интеграционная приёмка M0 | Обязательные M0 результаты | C0/C8 | BLOCKED | Инженерные gates PASS, Draft PR не слит | SOURCE + review + green current-head CI + интеграция |
| M1.1 | Tenant schema/context/RLS | VERIFIED M0 | C2 | TODO | Критерии в M1_HANDOFF.md | Не выдавать до принятого base SHA |
| M1.2 | Auth/session/membership/login UI | Интегрированный контракт M1.1 | C1+C5 | TODO | Критерии в M1_HANDOFF.md | Не выдавать раньше зависимости |
| M1.3 | Local Plan/Subscription/Entitlements/Audit | M1.1 | C1 | TODO | Критерии в M1_HANDOFF.md | Без paid provider и клиентских платежей |

## Фактическое CI evidence

Успешный PR run: https://github.com/Elefesys/ai-service-manager/actions/runs/34889375796.
Head: `c89b839c56d14c184650423a18ec35d1fc22de41`.
Проверенный GitHub PR merge-ref: `94bccf8a6545c1920c14bd5d81d8d61d0cd83225`.
Artifact: `m0-verification-34889375796`, ID `10366535686`; содержит ci.log, tested-commit.txt и пустой worktree-status.txt. CI не изменил source или lockfiles.

- Backend: 15 unit/fixture tests PASS; 7 real PostgreSQL integration tests PASS.
- Frontend: TypeScript PASS, 3 Vitest tests PASS; два набора static assets совпали побайтово.
- Ruff lint/format PASS; strict mypy + pydantic.mypy PASS.
- PostgreSQL runtime identity/RLS/no-context/cross-Workspace/rollback/reused-pool-context/vector/UUIDv7 и SIGTERM worker/scheduler PASS.
- Alembic upgrade, repeated upgrade, downgrade и re-upgrade PASS.
- OpenAPI drift check PASS; два backend wheel совпали побайтово.
- Docker backend/check/frontend images built; LOCAL compose ready; direct API, reverse proxy и Ops HTML smoke PASS.

Первый bootstrap 34889055896 сформировал locks в `76fd251d2b323986306731505ce59773886e5ca7`, но verification остановился на mypy: BaseSettings требовал аргументы, хотя значения читаются из environment. Исправление `c89b839` включает официальный Pydantic mypy plugin без отключения strict checks. После этого обычный read-only PR CI успешно прошёл весь путь. Первую неуспешную попытку не переписываем как успешную.

До remote CI локально на предустановленном, не locked окружении прошли те же 15 unit/fixture tests, compileall, OpenAPI и shell syntax. Локальная C0-сессия не содержит Docker/psql; полноценное выполнение подтверждено именно GitHub runner, а не заявлено как локальный запуск у пользователя.

## Открытые ограничения

Полный импорт канонических исходников в Git и независимый review остаются открыты. Architecture Freeze v1.0 pending; production readiness не утверждается. App имеет только LOCAL/TEST guard; auth, durable Jobs, бизнесовые таблицы и real AI/payment calls отсутствуют намеренно.

Неблокирующие warnings CI: Starlette/HTTPX и AnyIO deprecated interfaces; обязательные Docker ARG без default дают build-lint warnings; закреплённые actions target Node20, runner исполняет их на Node24 без unsafe override. Их обновление требует отдельного reviewed tooling change; warnings не были заглушены.

Reproducibility evidence относится к зафиксированным Linux/amd64 inputs и wheel/static asset bytes. Bit-identical OCI metadata между разными builders/CPU, полноценный vulnerability audit, production hosting SKU/extension availability, restore/monitoring и реальные provider accounts остаются отдельными gates. M0 capability probe не является полной M1 tenant-security реализацией.
