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
| M1.1 | Tenant schema/context/RLS | VERIFIED M0 | C2 | REVIEW | PR #3; C8 CHANGES_REQUESTED: C8-M1.1-01 (P2), AUTOCOMMIT/context mismatch | Исправление C2 в той же ветке, все 8 C8 tests, полный CI и повторная проверка; merge запрещён до приёмки C0 |
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

## M1.1 — C0 disposition of independent C8 review / 2026-09-15

Status: **REVIEW**; review outcome: **CHANGES_REQUESTED**. Это результат review, не новый статус задач и не отмена M0 VERIFIED. M1.1 не INTEGRATED/VERIFIED. M1.2/M1.3 не запускаются.

C0 сверил отчёт C8 с PR #3/#4 и скачанным новым CI artifact. Проверенный C2 head: `84d94b2187787c654928ac11b7e4d411970b2b0c`; исходный base/main: `7eaa9aa63b3f27215f6eb970fb9eb857fd291f62`. PR #3 открыт и не слит. C8 test-only head: `4fe5f115ffbac696e58620aa6ce006642fe6e787`; PR #4 закрыт без merge, ветка `c8/m1-1-review` сохранена. Этот раздел добавлен C0 только в task register на ветке PR #3: он не исправляет код и не является интеграцией в main. C2 продолжает от resulting head этого coordination commit, сохраняя исходный base задачи.

**C8-M1.1-01, P2:** публичный TenantDatabase принимает PostgreSQL engine в DBAPI AUTOCOMMIT и выдаёт Python WorkspaceContext без общей реальной DB-транзакции. `connection.begin()` и `in_transaction()` недостаточны. Диагностический SELECT после выдачи unit вернул workspace/xid/context_xid = NULL. Нарушен существующий M1_1_CONTRACT.md §§Context and transaction ownership / Errors and consumer API; текущие locations: database.py:60–68, 200–216, 231–249. Это НЕ подтверждённая cross-tenant утечка/обход RLS; штатный RuntimeDatabase не включает AUTOCOMMIT. Архитектурный пересмотр и новая миграция не требуются.

Evidence C8: run `34987895881`, job `104444620955`, FAILURE; artifact `10403814298`, SHA-256 `2b4afb189a0724a8346e4941d006613e8020c808145ba3b6569a46ca0ce0afd7`; tested virtual merge `9cce66cd64caa6d8e0d45b87c454331ccbe5030c`. C0 проверил ZIP SHA, tested-commit, пустой worktree-status, лог assertion и сохранность всех 72 исходных файлов C2. Добавлен только tests/test_c8_tenancy_review.py. Все 11 архитектурных оригиналов и их эталоны совпали. Новый PostgreSQL run самим C0 не выполнялся.

C8 CI: 24 non-integration PASS; 55 integration PASS и 1 FAIL (AUTOCOMMIT); frontend 3 PASS. Из 8 новых C8 cases 7 PASS, 1 FAIL; все исходные 48 PostgreSQL tests прошли. Последующие верхнеуровневые downgrade/re-upgrade, OpenAPI, backend wheel, HTTP smoke и отдельный clean-source gate в этом запуске не выполнены после FAIL. Старый green C2 run `34978858961` остаётся свидетельством 75 исходных tests, но не закрывает новый finding. Первичная ошибка C8 Ruff I001 в run `34987294887` исправлена test-only commit и не является дефектом C2.

**Ограниченное задание C2:** отклонять фактический AUTOCOMMIT на выданном соединении до публикации unit/context стабильным CONTEXT_INVALID либо TRANSACTION_STATE; не менять режим незаметно. В нормальном режиме до yield подтвердить совпадение Workspace и непустого XID/fence. Не полагаться только на engine options, begin/in_transaction или get_isolation_level. Сохранить pool/task/cancellation cleanup, реальные rollback и membership locks. Не менять DDL, роли/grants/RLS, зависимости или канон.

Разрешённый scope доработки: backend/src/asm/tenancy/database.py; tests/test_c8_tenancy_review.py (все 8 C8 cases без ослабления); tests/test_tenancy*.py для targeted проверки отказа до входа в body и очистки; уточнение docs/tasks/M1_1_CONTRACT.md без ослабления обещанной гарантии. types.py/contract.py/tenancy.v1.json — только при доказанной необходимости, с явным diff; существующих error codes достаточно. Общие CI entrypoints, 0001/0002, bootstrap, frontend, lockfiles, fixtures semantics не меняются. Реестр остаётся собственностью C0.

Test-only перенос: взять tests/test_c8_tenancy_review.py из `4fe5f115ffbac696e58620aa6ce006642fe6e787` либо объединённый patch SHA-256 `9548078f85486abf603e2068b376536df413dca5539341d71e61a5772aa7d4ea`. C0 восстановил этот же patch из CI bytes и проверил git apply --check/совпадение результата. При cherry-pick нужны оба C8 commits: `080f1a4d67aaf6d456278eafadd7400e9f96524d`, затем `4fe5f115ffbac696e58620aa6ce006642fe6e787`; второй отдельно — лишь сортировка импортов. PR #4 не сливать.

Acceptance для нового head: сохранить все 75 исходных tests и 8 C8 cases (ожидаемо 83 без дополнительных cases), без skip/xfail/удаления assertion; выполнить полный scripts/ci.sh, включая ранее не достигнутые gates. При отказе AUTOCOMMIT тело UOW не должно исполняться, ambient context не публикуется; нормальный путь сохраняет Workspace/XID, COMMIT/ROLLBACK, pool reuse и concurrency. Вернуть C0 новый полный head, точный CI checkout/tree/run/evidence, diff и ограничения. Затем targeted re-review C8; интеграцию и main CI выполняет только C0.
