# AI Service Manager — единый task register

Ответственный: C0. Архитектура v0.28; implementation decision IMPL-001.
Исходный main: `c74db484b483fccaef7b4124b418a91979cb4be6`.
Рабочая ветка всех задач M0 ниже: `c0/m0-foundation`. Точный текущий SHA читается из Git; принятого M0 commit на main пока нет.
Состояния: TODO → IN_PROGRESS → REVIEW → INTEGRATED → VERIFIED. BLOCKED всегда содержит причину. REVIEW означает результат на рабочей ветке, не приёмку main.

| ID | Цель | Зависимости | Ведущий | Статус | Файлы / проверка | Следующий шаг / блокер |
|---|---|---|---|---|---|---|
| M0.ACCESS | Проверить repository, main и запись | — | C0 | VERIFIED | GitHub read, новая ветка, реальные commits | Доступ подтверждён; main не менялся |
| M0.BASELINE | Сверить Spec/ADR/baseline/plan | ACCESS | C0 | REVIEW | 10 SHA-256 совпали с baseline; перечень ADR в IMPL-001 | Завершить SOURCE |
| M0.SOURCE | Побайтовый импорт оригиналов архитектуры в Git | BASELINE | C0 | BLOCKED | docs/architecture/SOURCE_MANIFEST.json; scripts/import_architecture.py | Оригиналы прочитаны из project attachments и есть в локальном пакете, но ещё не все размещены в Git. Не заменять пересказом |
| M0.STACK | Выбрать и записать стек | BASELINE | C0/C1/C2/C6 | REVIEW | docs/decisions/IMPL-001-stack.md; manifests | Проверить LOCK/CI, принять вместе с M0 |
| M0.BACKEND | API/Worker/Scheduler shell | STACK | C1/C0 | REVIEW | backend/src/asm; unit health/schema/env tests | Locked-env type/lint/DB/shutdown evidence |
| M0.FRONTEND | Business Console/Ops shells | STACK | C5/C0 | REVIEW | frontend; 3 Vitest cases, typecheck, build | Реальный frontend build/test evidence |
| M0.DB | PG18/pgvector/roles/migrations без domain tables | STACK | C2/C0 | REVIEW | infra/postgres, migrations; временные probes в asm_test | Real PG migration/RLS/rollback/pool test evidence |
| M0.LOCAL | Docker/local запуск и smoke | BACKEND/FRONTEND/DB/LOCK | C6/C0 | REVIEW | compose.yaml, infra/Dockerfile.*, scripts/ci.sh | Чистый запуск и shutdown; локальных Docker/PG в C0-сессии нет |
| M0.TEST | Существенные real PostgreSQL tests | DB | C8/C0 | REVIEW | tests/test_postgres.py; 7 cases с worker/scheduler parametrization | Выполнить на Docker runner; mock не закрывает задачу |
| M0.LOCK | Lockfiles, image digests, воспроизводимые артефакты | STACK | C6/C0 | IN_PROGRESS | scripts/bootstrap.sh, scripts/pin_images.sh; uv.lock/package-lock/images.lock после выполнения | Первичное разрешение на network-capable runner; затем frozen builds |
| M0.CI | Сборка/миграции/tests/schema/repro/smoke в CI | LOCAL/LOCK | C6/C8/C0 | IN_PROGRESS | .github/workflows; scripts/check_backend.sh и ci.sh | Нужны фактические логи и SHA, наличие YAML не равно PASS |
| M0.FIXTURES | Synthetic configurations A–D | STACK | C0/C8 | REVIEW | tests/fixtures; strict validator, env guards | Локальные fixture tests PASS; подтвердить в locked CI |
| M0.HANDOFF | Правила чатов, реестр, M1.1–M1.3 | BASELINE/STACK | C0 | REVIEW | AGENTS.md; docs/tasks/M1_HANDOFF.md | Привязать к принятому M0 SHA после интеграции |
| M0.ACCEPT | Приёмка M0 | Все обязательные M0 проверки | C0/C8 | BLOCKED | Один согласованный commit + независимые gates | Не закрывать до real PG, build/repro/CI и source handoff |
| M1.1 | Tenant schema/context/RLS | VERIFIED M0 | C2 | TODO | docs/tasks/M1_HANDOFF.md | Не выдавать до принятого base SHA |
| M1.2 | Auth/session/membership/login UI | Интегрированный контракт M1.1 | C1+C5 | TODO | docs/tasks/M1_HANDOFF.md | Не выдавать раньше зависимости |
| M1.3 | Local Plan/Subscription/Entitlements/Audit | M1.1 | C1 | TODO | docs/tasks/M1_HANDOFF.md | Без paid provider и клиентских платежей |

## Evidence до первого remote CI

В локальной C0-сессии на предустановленном, не locked окружении: 15 unit/fixture tests PASS; Python compileall PASS; OpenAPI export/check PASS; shell syntax checks PASS. Найденная ошибка длины synthetic UUID исправлена до публикации fixtures.

Не выполнены локально: PostgreSQL integration, Docker build/smoke, npm/frontend tests, Ruff, mypy, locked dependency installation и wheel rebuild. Docker/psql отсутствуют; пакетные реестры недоступны из этой сессии. Remote CI evidence записывается отдельно с run/commit; его успех нельзя предполагать.

## Ограничения и открытые вопросы

Architecture Freeze v1.0 pending. Production hosting SKU, release monitoring/restore, реальные AI/payment/fiscal providers и параметры мастера остаются в исходном OPEN register и не блокируют synthetic разработку. M0 не включает auth, durable Jobs, бизнесовые таблицы, real AI/payment calls и production deployment. Code/DB probes не являются production tenant/security certification.
