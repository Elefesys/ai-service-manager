# Первые задания после принятия M0

Задачи M1 остаются TODO до передачи C0 точного принятого base commit. Канонические исходники v0.28 находятся в `docs/architecture/`; стек — `docs/decisions/IMPL-001-stack.md`; правила — `AGENTS.md`; единственный реестр — `docs/TASK_REGISTER.md`.

C0 выдаёт полный SHA принятого M0 после интеграции и успешного main CI. Старый `c74db484b483fccaef7b4124b418a91979cb4be6` содержит только README и не является M1 base. Не выбирать moving main вместо переданного SHA и не предполагать общую файловую систему чатов.

## M1.1 — Tenant schema, roles, WorkspaceContext/RLS

Ведущий: C2 — PostgreSQL и надёжность данных. Координация контрактов/миграций: C0; auth consumer: C1; независимые последующие проверки: C8.
Зависимость: принятый M0. Новая ветка от переданного SHA: `c2/m1-1-tenant-foundation`.

### Основание

`01_ARCHITECTURE_SPEC.md` §§1.1, 2, 3, 17.3–17.4, 18.5, 18.14, 22.2, 24.5, 24.19; ADR-002–006, 008, 010–011, 116–117, 125–126, 132, 160–161, 194–195, 206, 216, 266. Дополнительно `06_MVP_SPEC.md`, `07_DEVELOPMENT_ROADMAP.md` §§4–5/19 и `09_IMPLEMENTATION_PLAN.md` §§5–6/9. Оригинальные статусы и отложенные горизонты не переписывать.

### Ограниченный результат

Минимальные platform UserAccount/Workspace/WorkspaceMembership и app Business/BusinessMember/Location, требуемые tenant foundation M1. UserAccount здесь — identity/schema foundation, не реализация login/password/session. BusinessMember может существовать без UserAccount. Workspace и Business различаются; отдельный tenant_id, schema-per-tenant и database-per-tenant запрещены.

Зафиксировать реализуемый schema/context contract для C1 до зависимой работы: ключи/FK, минимальные statuses/permissions, trusted actor/context shape, разрешённый путь platform lookup, transaction ownership и error semantics. Обычные поля принятого контракта — implementation detail; новый domain decision или конфликт с LOCKED ADR вынести C0, не считать молча принятым.

Серверный WorkspaceContext содержит workspace_id, actor, permissions и correlation/request ID. Установка PostgreSQL context только transaction-local в короткой транзакции. Не вводить endpoint, который доверяет произвольному client/model workspace_id или выдаёт Owner permissions. RLS не заменяет application authorization; login/session/membership-management остаются M1.2.

Для tenant tables: workspace_id NOT NULL, RLS USING + WITH CHECK, tenant-safe composite FK/unique constraints. Platform lookup должен быть минимальным и не превращаться в универсальный обход доступа. Сохранить отдельные bootstrap/migration/runtime identities; runtime без SUPERUSER/BYPASSRLS/ownership/DDL/SET ROLE в migration identity. Никаких production данных/секретов.

### Разрешённая область файлов

- Новый модуль `backend/src/asm/tenancy/` и связанные tenant tests, например `tests/test_tenancy*.py`.
- Новая миграция `migrations/versions/0002_tenant_foundation.py`: C0 резервирует revision `0002`, down_revision `0001`, единственный следующий migration head. Не менять уже применённую `0001_foundation.py`.
- `infra/postgres/bootstrap.sh` — только необходимые изменения ролей/прав с явным описанием и тестами; не ослаблять ограничения runtime.
- `contracts/tenancy.v1.json` и `docs/tasks/M1_1_CONTRACT.md` для фактически реализованного контракта, без будущего универсального DSL.
- `backend/src/asm/foundation.py` — только wiring нового DB/context модуля и проверяемое обновление ожидаемой schema revision/readiness.
- `tests/test_postgres.py` — адаптировать M0-only assertion о единственной alembic_version к минимальному M1.1 набору таблиц; не удалить проверки прав/изоляции/pgvector/migration behavior.
- Fixtures можно расширять только synthetic tenant identity/relations. Не менять их price/duration/payment semantics и не создавать пока client/message/payment tables.

Frontend, AI/channel/payment adapters, lockfiles/toolchain и общие CI entrypoints вне обычного scope этой задачи. Необходимое расширение явно согласовать с C0. Task register централизованно обновляет C0 по handoff результата; не создавать второй независимый реестр.

### Проверки приёмки

Настоящий PostgreSQL 18 + pgvector под реальной runtime-ролью. Workspace A не читает/изменяет B; без context и с некорректным context доступ fail-closed. Покрыть INSERT/UPDATE/DELETE, попытку перенести строку в другой Workspace, forged IDs и cross-workspace FK. Дополнительно подтвердить положительный доступ A→A/B→B.

Проверить отсутствие tenant-context leakage после COMMIT/ROLLBACK и повторного использования того же соединения; конкурентные async contexts; несовпадающие Workspace/Business relations. SQL connections должны подтверждаться не только mock-объектами. Runtime не может отключить защиту через ownership/DDL/привилегированную роль.

Проверить свежую БД, upgrade из принятого M0, повторный upgrade, согласованный downgrade/re-upgrade в disposable TEST, полный M0 regression, strict typing/lint и contract drift. Изменение schema revision не должно оставлять readiness навсегда 503. Same-Workspace Client authorization остаётся обязательством следующих клиентских capabilities; отсутствие Client tables здесь не даёт права объявить этот будущий gate пройденным.

### Не входит

Login UI/session/CSRF/password storage (M1.2), Audit/Plan/Subscription/Entitlements implementation (M1.3), durable Inbox/Outbox/Jobs и Client/Conversation/File (M2), services/quotes/orders/scheduling/payment schemas следующих milestones. Не строить всю будущую БД заранее.

### Возврат C0

PR в main без самостоятельного merge, полный head SHA и base SHA; список файлов/миграций и контрактных изменений; команды, CI run и фактические результаты; ограничения/OPEN вопросы; явный REVIEW, не INTEGRATED. После C0 приёмки зависимые задачи получают новый общий SHA.

## M1.2 — Auth/session/membership/application authorization и login UI

Ведущие: C1 + C5. Зависимость: интегрированный schema/context contract M1.1. Отдельная задача и ветка от нового C0 base, не параллельное изменение миграций M1.1.

Результат: поддерживаемая библиотека auth/session, серверные sessions, expiry/rotation/revocation/logout, membership/permission enforcement; login UI и разделение Workspace/Ops contexts. Защита CSRF, HttpOnly/SameSite и Secure cookies при TLS; не хранить долгоживущие bearer credentials в localStorage. Не вводить собственную криптографию. Platform Ops MFA обязателен до production.

Приёмка: вход владельца synthetic Workspace, logout/revocation/expiry, отрицательные auth/permission tests, запрет forged Workspace/Business доступа, отсутствие secret/session leakage; UI работает через application API. Нет Telegram/AI/customer payments.

## M1.3 — Local Plan/Subscription/Entitlements и Audit

Ведущий: C1; C2 координирует последующую миграцию. Зависимость: M1.1; защищённый UI использует M1.2.

Минимальные локальные WorkspaceBillingAccount, SaaSPlanRevision/PlanEntitlements, Subscription (TRIALING или ACTIVE+COMPED), WorkspaceServiceMode и EntitlementService. Entitlement не является security permission. Бизнес-код проверяет capability, не имя плана. Runtime не вызывает paid billing provider (это M15) и не создаёт client payments (M8).

Audit фиксирует фактическое важное действие/actor/correlation без секретов и избыточных данных. AuditEvent не подменяет Outbox/технические логи. Приёмка: изоляция Workspace, нормальная работа TRIALING/COMPED без скрытого обхода, allow/deny entitlements, неизменность истории и воспроизводимые миграции/тесты. Публичные owner operations должны быть авторизованы.
