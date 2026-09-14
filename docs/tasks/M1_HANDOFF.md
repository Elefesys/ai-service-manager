# Первые задачи M1 — выдача после приёмки M0

Статус: TODO, не разрешение начинать параллельную реализацию сейчас.
Repository: Elefesys/ai-service-manager. Integration branch: main.
Base SHA: C0 заполняет полным SHA принятого M0; исходный c74db484b483fccaef7b4124b418a91979cb4be6 содержит только README и не подходит как готовая база M1.
Источники: v0.28 / 09_IMPLEMENTATION_PLAN.md §§5–6; правила AGENTS.md. Перед стартом проверить фактический Git HEAD, оригиналы архитектуры и зелёные M0 gates.

## M1.1 — Tenant schema, DB-роли, context/RLS и cross-tenant tests

Ведущий C2; C1 согласует auth/domain contract, C8 проверяет изоляцию. Зависимость: VERIFIED M0. Ветка: c2/m1-1-tenant-foundation от принятого SHA.

Область: минимально нужные platform UserAccount/Workspace/Membership и app Business/BusinessMember structures с согласованными C1 связями; backend DB/context module; новая Alembic migration и isolation tests. Идентичности provisioning/migration/runtime развивают M0, не заменяя runtime суперпользователем. Полную будущую схему не создавать. Точный DDL/authorization relationship contract фиксируется перед кодом, не считается уже принятым этим заданием.

Нужны: NOT NULL workspace_id на tenant data, tenant-safe FK, RLS USING/WITH CHECK, серверный WorkspaceContext и transaction-local context без утечки через pool. Транзакции требуют доверенный actor/context; нет API «выбери любую Workspace». Platform lookup для login/routing ограничен контрактом, а не общим bypass.

Приёмка на real PostgreSQL и runtime identity: A не читает/не меняет B; отсутствие/неверный context fail closed; UPDATE/INSERT/FK обходы запрещены; commit/rollback/reuse/concurrent connections не смешивают context; runtime не владеет tenant tables, не может DDL/SET ROLE migrator/BYPASSRLS. Migration fresh upgrade/replay проходит. Временный M0 probe не считается этой реализацией. Возврат: migration chain, typed context contract, SQL/тесты, полный SHA/evidence.

## M1.2 — Auth/session/membership/application authorization + login UI

Ведущие C1+C5; C2/C8 участвуют. Зависимость: согласованный и интегрированный контракт M1.1. Ветки c1/m1-2-auth и c5/m1-2-login только по согласованному API SHA.

Область: backend auth/application services, API schemas, frontend login/logout/session UI, auth tests; migration additions только через очередь C2/C0. Не добавлять Telegram, AI, цены, календарь и платежи.

Нужны secure server-managed sessions, проверка credentials готовыми криптографическими примитивами, expiry/logout/revocation, HttpOnly/SameSite cookies, Secure в TLS-окружениях, CSRF для изменяющих запросов и валидация membership/permissions при каждой операции. Не хранить долгоживущие bearer secrets в localStorage. Уточнить минимальную библиотеку/session representation как реализационное решение перед кодом. Platform Ops — отдельный authorization context; до реализации запрещён доступ к privileged data. Mandatory production MFA остаётся release gate, не считается выполненным login формой.

Приёмка: владелец входит и выходит; anonymous/expired/revoked session не работает; подмена Workspace/membership/object ID и CSRF отклоняются; удаление membership не оставляет доступ; auth errors не раскрывают secrets; API+UI+real DB integration проходят. Результат включает контракты и тесты, не только страницы.

## M1.3 — Local Plan/Subscription/Entitlements + Audit

Ведущий C1; C2 согласует DDL, C5 минимальную видимость, C8 тестирует. Зависимость: M1.1; авторизованная UI/API демонстрация использует M1.2. Ветка c1/m1-3-pilot-entitlements.

Область: минимальные versioned SaaSPlanRevision/PlanEntitlement, Workspace Subscription/service mode, EntitlementService и business Audit с tenant-safe связями. Без внешнего SaaS payment provider, Invoice/checkout integrations и клиентских PaymentTransaction. Не реализовывать M15 заранее.

Поддержать явно TRIALING либо ACTIVE + COMPED, нормальную проверку capabilities вместо `if plan == ...`; entitlements не расширяют security permissions. Runtime не вызывает billing provider. Значимые действия аудируются с реальным actor, Workspace/resource/reason/correlation без secrets/PII. Audit != technical log != Outbox. Атомарность audit/domain mutation проверяется там, где описывается одно действие; не строить Outbox kernel до M2.1.

Приёмка: normal/limited capabilities, отсутствие hidden pilot bypass, изоляция Workspace, audit actor/denied access semantics и rollback атомарности; отсутствие сетевой paid-billing зависимости; versioned migration и реальные integration tests. Все реальные тарифы и платёжные реквизиты остаются вне задачи.

## Обязательный handoff каждой задачи

ID, исходный и конечный полный SHA, scope изменённых файлов, применимые ADR, изменения контрактов/миграций, команды и фактические результаты, ограничения, новые OPEN-вопросы, следующий шаг. До C0 review/integration не заявлять INTEGRATED/VERIFIED и не выдавать зависимым чатам непроверенную ветку как main.
