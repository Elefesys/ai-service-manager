# AI Service Manager — единый task register

Ответственный: C0. Дата приёмки инженерного M0: 2026-09-15.
Архитектура: v0.28; реализационный стек: `docs/decisions/IMPL-001-stack.md`.

## Принятие M0

**M0 — VERIFIED.** PR #1 фактически слит в `main` 2026-09-15T12:43:21Z.
Принятый implementation/merge commit: `1d7bb4fa0567bdd263d7910492ecf217696642de`.
Исходный main: `c74db484b483fccaef7b4124b418a91979cb4be6` (только README).
Интегрированный PR head: `8639812ce71f5cce8f2b2ed051ff01fea67d5157`.
PR: https://github.com/Elefesys/ai-service-manager/pull/1

Приёмка основана на C0 second-pass review (`docs/reviews/M0_C0_REVIEW.md`), точном импорте исходников и успешном **push/main** CI принятого merge commit, а не только на виртуальном PR merge-ref. C0 повторно прочитал PR/main через GitHub и проверил скачанный CI artifact: tested-commit совпал, worktree-status пуст, все одиннадцать документов совпали с исходными вложениями побайтово и по SHA-256.

Эта запись фиксирует уже проверенную инженерную реализацию. Последующее согласование документов приёмки не меняет код, миграции, архитектурные оригиналы или lockfiles. Полный стартовый SHA для M1.1 C0 передаёт в готовом стартовом сообщении после проверки итогового main, включающего эту запись. Это может быть documentation-only descendant указанного implementation commit; исполнитель не подменяет полученный SHA движущейся веткой main.

Review выполнен C0. Роли C1–C8 в таблице обозначают ответственность, не работу отдельно запущенных агентов. Независимый C8 review не выполнялся и не заявляется. Приёмка M0 не означает Architecture Freeze v1.0, завершение M1 tenant-security или production readiness.

Состояния задач: TODO → IN_PROGRESS → REVIEW → INTEGRATED → VERIFIED; BLOCKED требует конкретной причины. Это не архитектурные LOCKED/OPEN/DEFERRED/REVISED.

| ID | Цель | Зависимости | Ведущий | Статус | Проверка / результат | Следующий шаг |
|---|---|---|---|---|---|---|
| M0.ACCESS | Repository, main и запись | — | C0 | VERIFIED | PR #1 merged; main и commit подтверждены GitHub | Использовать назначенный полный SHA |
| M0.BASELINE | Spec/ADR/baseline/plan | ACCESS | C0 | VERIFIED | v0.28, канонические оригиналы и IMPL-001 сверены | Не менять принятые ADR молча |
| M0.SOURCE | Точный импорт оригиналов в Git | BASELINE | C0 | VERIFIED | 11/11 документов, исходные SHA-256 и побайтовое сравнение PASS | Оригиналы в docs/architecture; manifest не переписан |
| M0.STACK | Выбор и фиксация стека | BASELINE | C0/C1/C2/C6 | VERIFIED | IMPL-001 интегрирован; manifests/locks/digests и CI PASS | Сохранять стек; изменения только с review |
| M0.BACKEND | API/Worker/Scheduler shell | STACK | C1/C0 | VERIFIED | Lint, strict mypy, health/schema/env и shutdown PASS | Tenant foundation в отдельном модуле M1.1 |
| M0.FRONTEND | Business Console/Ops shells | STACK | C5/C0 | VERIFIED | TypeScript, 3 Vitest tests, build/rebuild PASS | Login/authorization в M1.2 |
| M0.DB | PG18/vector/roles/migrations | STACK | C2/C0 | VERIFIED | Real PG, runtime restrictions, migration cycles PASS | Следующая revision 0002 после 0001; будущей БД нет |
| M0.LOCAL | Docker/local и smoke | BACKEND/FRONTEND/DB/LOCK | C6/C0 | VERIFIED | Чистый GitHub Linux/amd64 Docker runner: stack/HTTP/proxy PASS | Запуск на ПК пользователя отдельно не выполнялся |
| M0.TEST | Существенные real PG tests | DB | C8/C0 | VERIFIED | 7 real PostgreSQL tests PASS, не SQLite/mock | Расширить реальную tenant suite в M1.1 |
| M0.LOCK | Locks/digests/reproducibility | STACK | C6/C0 | VERIFIED | uv.lock, package-lock.json, 5 image digests; wheel/assets byte comparisons PASS | Не запускать bootstrap при обычном checkout |
| M0.CI | Полный проверочный pipeline | LOCAL/LOCK | C6/C8/C0 | VERIFIED | Main run 34970531911 SUCCESS; точный SHA, source/drift gates PASS | CI каждой интеграции; contents: read |
| M0.FIXTURES | Synthetic A–D | STACK | C0/C8 | VERIFIED | UUID/money/modes/environment checks PASS | Только synthetic, не production defaults |
| M0.HANDOFF | Правила, реестр, M1.1–M1.3 | BASELINE/STACK | C0 | VERIFIED | AGENTS, M1_HANDOFF, ограниченный scope и зарезервированная 0002 | C0 выдаёт M1.1 с точным проверенным SHA |
| M0.ACCEPT | Интеграционная приёмка M0 | Все обязательные M0 результаты | C0 | VERIFIED | PR #1 merged + C0 review + green main CI + source integrity | Разрешён запуск M1.1; не production |
| M1.1 | Tenant schema/context/RLS | VERIFIED M0 | C2 | TODO | Готова к выдаче; docs/tasks/M1_HANDOFF.md | Ветка c2/m1-1-tenant-foundation от SHA стартового сообщения C0 |
| M1.2 | Auth/session/membership/login UI | Интегрированный контракт M1.1 | C1+C5 | TODO | Критерии в M1_HANDOFF.md | Не начинать зависимую реализацию до приёмки M1.1 |
| M1.3 | Local Plan/Subscription/Entitlements/Audit | M1.1 | C1 | TODO | Критерии в M1_HANDOFF.md; защищённый UI использует M1.2 | Без paid provider и клиентских платежей |

## Фактическое evidence принятого implementation commit

Main CI: https://github.com/Elefesys/ai-service-manager/actions/runs/34970531911
Event: `push`; branch: `main`; conclusion: `success`; attempt: 1.
Head и tested-commit: `1d7bb4fa0567bdd263d7910492ecf217696642de`.
Job: `104385439116` (`foundation`); все обязательные шаги SUCCESS.
Artifact: `m0-verification-34970531911`, ID `10396772645`.
SHA-256 ZIP: `e1702634f918fb92c1a361ee5ac49a762ed58dc6b125ee85c75dd35efd2f1755`.
Состав: architecture.log, ci.log, tested-commit.txt, пустой worktree-status.txt, source.tar.gz.

- 20 backend unit/fixture/import tests PASS; 7 real PostgreSQL integration tests PASS; 3 frontend tests PASS. Итого 30 тестов, без суммирования повторных CI запусков.
- Ruff lint/format, strict mypy и TypeScript PASS.
- PostgreSQL runtime-role restrictions, RLS allow/deny/no-context/cross-Workspace, rollback/reused-pool context, pgvector/UUIDv7 и worker/scheduler SIGTERM PASS.
- Alembic fresh/repeated upgrade, disposable TEST downgrade/re-upgrade PASS.
- OpenAPI drift, два одинаковых backend wheel и два одинаковых набора frontend assets PASS.
- Docker build, LOCAL readiness, direct API/reverse proxy/Ops HTML smoke PASS.
- Canonical-source verification и clean tracked/untracked worktree gate PASS; source/locks не изменены проверками.

## История импорта и предыдущих проверок

Import run `34968001558` создал commit `395b760175871a3d6cde10b8e01e1f9364e3bd57` с одиннадцатью оригиналами. Artifact ID `10395434061`, SHA-256 `fd89f2dc453e0848341b55e93565779393e772ec682a607836af267407726751`. Его source archive и source принятого main повторно сверены с оригиналами. Опечатка полного import SHA в первоначальном C0 review исправлена документально; эталонные файлы/manifest и Git history не изменены.

Ранее успешные PR runs `34889375796` и `34889853771` проверяли предыдущие snapshots с 25 тестами; они не подменяют main evidence выше. Первый bootstrap `34889055896` сформировал locks в `76fd251d2b323986306731505ce59773886e5ca7`, но остановился на mypy/BaseSettings. Исправление `c89b839c56d14c184650423a18ec35d1fc22de41` включило Pydantic mypy plugin без отключения strict checks. Промежуточные source-import CI failures отражали отсутствующие/несовпадающие ещё переносимые документы; итоговые оригиналы прошли проверку без изменения эталонных хэшей. Неуспешные попытки не переписываются как успешные.

## Открытые ограничения после M0

Architecture Freeze v1.0 pending. App разрешает только LOCAL/TEST. Полная tenant schema/authorization — M1; durable Inbox/Outbox/Jobs — M2.1. Нет live AI/Telegram/payment/fiscalization, Object Storage, production backup/restore, полного vulnerability/container/dependency audit и production telemetry exporter. Эти gates не закрыты инженерным M0.

Независимый C8 review не выполнялся; отдельная проверка substantive tenant/auth capabilities требуется по мере их реализации. C0 review не заменяет production security/release gates. Запуск на пользовательском компьютере не выполнен; полный запуск подтверждён GitHub Linux/amd64 runner.

Неблокирующие deprecation/toolchain warnings остаются задачей сопровождения C6. Reproducibility ограничена locked inputs и wheel/static asset bytes; bit-identical OCI metadata между builders/CPU не заявляется. Реальные данные мастера, API keys и расходы не нужны для начала M1.1.
