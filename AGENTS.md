# AI Service Manager — правила работы исполнителей

## Источники и границы

Сначала читать актуальные `docs/architecture/01_ARCHITECTURE_SPEC.md`, применимые ADR, MVP Spec, Roadmap и `09_IMPLEMENTATION_PLAN.md`. Baseline v0.28 — снимок, не отменяющий более новые явно принятые файлы. До точного импорта оригиналов в Git использовать предоставленные project sources с SHA-256 из `docs/architecture/SOURCE_MANIFEST.json`; отсутствие оригиналов явно указывать. Не восстанавливать канон по пересказу этого файла.

`docs/decisions/IMPL-001-stack.md` фиксирует реализационный стек. LOCKED / OPEN / DEFERRED / REVISED — статусы решений; TODO / IN_PROGRESS / REVIEW / INTEGRATED / VERIFIED / BLOCKED — статусы задач. Нельзя смешивать их. Изменение LOCKED-решения требует явного противоречия, последствий, предложения и принятия ADR. Architecture Freeze v1.0 не считается выполненным автоматически.

Критические факты определяются structured state и domain services, не LLM. Workspace — единственная tenant boundary. Runtime не SUPERUSER/BYPASSRLS/владелец tenant-таблиц. Tenant context только внутри транзакции из доверенного серверного контекста. Наличие workspace_id не разрешает доступ к чужому Client внутри Workspace. Внешние HTTP-вызовы не держат бизнес-транзакцию.

В M0 разрешены только shells, инфраструктурные роли/схемы/миграции и временные DB-пробы в asm_test. Нет будущих business tables, auth-заглушек с доступом к данным, fake paid states, очереди в памяти или пустых будущих adapters. PostgreSQL durable Jobs появляются в M2.1. Реальные данные, production credentials и платные вызовы не нужны и не разрешены автоматически.

## Владельцы областей

| Чат | Ответственность | Основная область после выдачи задачи |
|---|---|---|
| C0 | Координация, общие контракты, очередь миграций, приёмка | README, AGENTS, task register, integration branch, решения |
| C1 | Backend и бизнесовые команды, auth, workflow, scheduling | backend; контракты с C2/C5 |
| C2 | PostgreSQL, RLS, ограничения, транзакции, migrations, durable kernel | migrations, DB-модули; infra/postgres совместно с C6 |
| C3 | Telegram, события, разговоры, delivery, takeover | channel/conversation modules |
| C4 | AI, Gateway, RAG/Vision, typed tools integration, evals | AI-модули; без авторитетной бизнес-логики в prompt |
| C5 | Business Console и Platform Ops | frontend; backend-контракты согласуются с C1 |
| C6 | Docker/CI, облако, файлы, secrets, наблюдаемость, restore | infra, compose, workflows, scripts совместно с C0/C2 |
| C7 | Платежи, фискализация, позднее paid SaaS billing | отдельные payment/fiscal/billing domains |
| C8 | Независимая проверка качества/безопасности | tests/evals и evidence; авторы также пишут тесты |

Общие manifests, lockfiles, backend entrypoint, contract snapshots и migration heads редактируются по согласованию C0. Пока foundation помещён в один небольшой инфраструктурный модуль; это не разрешение добавлять в него все будущие domains. Не создавать каталоги/классы только ради будущей схемы.

## Выполнение и передача

Один канонический реестр: `docs/TASK_REGISTER.md`; не вести независимые дубликаты статусов по чатам. Перед стартом нужны ID, scope, зависимости, применимые ADR, repository, branch, полный base SHA, разрешённые файлы и критерии проверки. Нельзя предполагать общий диск или память между чатами.

Одна задача — отдельная ветка и checkout. Общий checkout допускает только последовательные изменения. C2/C0 назначают migration revision, predecessor и порядок интеграции. Не изменять уже применённую миграцию; не решать конфликт произвольным переименованием. C0 проверяет upgrade на чистой и предыдущей схеме.

Исполнитель возвращает commit/patch, изменённые контракты и миграции, точные команды и фактический результат, ограничения, новые OPEN-вопросы и следующий шаг. Mock/описание сценария не является PostgreSQL, live API или E2E evidence. Сборка, тесты и данные привязаны к одному проверяемому SHA.

Только C0 после проверки переводит задачу в INTEGRATED; VERIFIED требует evidence соответствующих критериев. Зависимый исполнитель начинает от принятого общего SHA, а не от непроверенного пересказа. Не force-push main, не включать production и не сливать PR с красными/неизвестными gates. Секреты не коммитить, не печатать и не включать в build context/артефакты.
