# M1 — принятый tenant foundation и следующие задания

Ответственный за интеграцию: C0. Единственный task register: `docs/TASK_REGISTER.md`. Канон: `docs/architecture/01_ARCHITECTURE_SPEC.md`, действующие ADR, MVP/Roadmap и `09_IMPLEMENTATION_PLAN.md`; стек: IMPL-001; правила: AGENTS.md.

## Текущий handoff C0 — M1.2 принята, M1.3 pre-DDL / 2026-09-18

Полная M1.2 INTEGRATED / VERIFIED на actual main `28c289ce6f77e33676cfa416585cc0e20c0be4e3`, tree `0df4c1b9a2e6922f742ebe459e46dd93d2c2959f`, PR #8 MERGED. Новый push/main run `35368244266`: foundation + browser + clean-source SUCCESS, 246 tests. Полная приёмка и границы evidence: `docs/reviews/M1_2_C0_ACCEPTANCE.md`; статусы — только `docs/TASK_REGISTER.md`.

Следующий исполнитель C1 начинает новую M1.3 от этого SHA, не продолжает слитые C5/C8 задачи. В текущем первом этапе разрешены точный механический post-merge перенос документов C0 и **один pre-DDL contract** `docs/tasks/M1_3_CONTRACT.md`. В нём нужны concrete minimal schema, RLS/grants/permission matrix, EntitlementService и service-mode truth table, Audit transaction boundary, API/UI proposal и тест-план. Все незафиксированные решения явно PROPOSED/OPEN, не принятый канон.

До C0/C2 review нельзя писать/применять новые migrations, менять runtime, frontend, JSON contracts/locks/CI/Compose или самостоятельно назначать revision. Backend+UI M1.2 не переоткрываются; C5/M2/production не запускаются. Исторические pre-merge и implementation сообщения ниже сохраняются как история, а не текущий запрет выданного contract scope.

## M1.1 — принято

PR #3, reviewed head `fa98e714d78485f8d07108294263c89d90a6e7f0`, actual merge `b480d864a246cb0573b40fa5211f66625a71de91`. Push/main CI `35015308300` SUCCESS, 89 tests. C8-M1.1-01 закрыто после targeted PASS; отсутствие нового DB run в повторном C8 review не скрывается. Отдельный main run выполнен при интеграции C0. Полная приёмка/evidence: task register и `docs/reviews/M1_1_C0_ACCEPTANCE.md`.

Шесть таблиц, typed context, scoped platform lookup, tenant-safe keys/FK, RLS и migration `0002 -> 0001`. Контракт: `docs/tasks/M1_1_CONTRACT.md`, `contracts/tenancy.v1.json`. AUTOCOMMIT отвергается до публикации; same-connection Workspace/XID/fence/INTRANS проверяются до yield. Все 8 C8 regressions и 6 дополнительных guard cases сохранены. AuthenticatedAccount не является аутентификацией по UUID. Ранее записанное в контракте pending C8 acceptance закрывается более поздним решением C0 в реестре; сам reviewed contract не переписывается ради этого.

Полный M1 ещё не завершён. Auth/login M1.2, entitlements/Audit M1.3, Architecture Freeze и production readiness не закрываются M1.1. Канонические ADR не пересматриваются.

## M1.2 — Auth/session/membership/application authorization и login UI

Ведущие по плану C1 + C5. Исполнение последовательно: C1 backend и consumer contract → C0/C8 review и интеграция → C5 login UI по принятому API. Это две части одной M1.2, не новые milestones. Backend-only не закрывает всю M1.2. Backend и UI приняты C0 после отдельных actual main CI; полная M1.2 VERIFIED. Текущее задание M1.3 ограничено pre-DDL контрактом выше. История до интеграции сохраняется ниже.

### История handoff — C0: UI pre-merge, 2026-09-18

C0 принял targeted C8 PASS на `7821aae54834de7107244090f76a1c7f327af897`, tree `0bcbf5bf0dd9ca937a56af5ef723697cbcfd8ef4`. UI-01/02/04/05 CLOSED по цепочке решений C0; ранее принятый backend не переоткрывается. **Полная M1.2 — REVIEW**, а не уже INTEGRATED/VERIFIED. Текущее действие — точная документальная синхронизация и условная интеграция существующего PR #8 (`codex/-ui-business-console` → `main`). Новую UI/backend реализацию не начинать. Исторические задания C5/C1 ниже сохраняются как критерии и история, не повторная выдача работы.

Actual main/base остаётся `aa7e792555c19d798eafa0cae17d29b73ca12376`. UI candidate run `35358909227` SUCCESS: 105 Python + 105 PostgreSQL + 30 frontend + 6 browser = 246 cases, clean-source в обоих jobs. Это PR test-merge `fcab2583010bb6cece456d8daaba239217bc78ef`, не actual integration. C8 лично выполнил 3 targeted + 1 full frontend на Node 24.8.0/npm 11.6.0, но не запускал новый PostgreSQL/Playwright. Точные evidence/границы и dispositions: `docs/reviews/M1_2_UI_C0_PREMERGE.md` и единственный `docs/TASK_REGISTER.md`.

Разрешены только четыре точных docs postimages: TASK_REGISTER, этот M1_HANDOFF, integration metadata IMPL-002 и новый UI pre-merge receipt. Старый неисполненный UI-04 register transfer отдельно не применять. Код, тесты, контракты, зависимости, миграции и CI не меняются. После их scope-check, нового SUCCESS foundation/browser на опубликованном docs head и неизменного base main C0 разрешает пользователю обычный merge commit PR #8; Codex сам не сливает и не включает auto-merge. Не обходить branch protections; unexpected tree/base требует C0. Дополнительный C8 для точной docs-only delta не нужен.

После слияния нужен отдельный actual main run обоих jobs. Только после проверки actual merge SHA/tree и main CI C0 объявляет полную M1.2 INTEGRATED/VERIFIED и выдаёт дальнейший base. M1.3 — TODO / не выдана; migration 0004 не резервировать; изменения в future capabilities/production не включать. Ни caller Workspace ID, ни UI membership state не заменяют backend authorization. Authenticated cross-Workspace browser и cookie-loss fault-B не заявляются как покрытые; accepted fault-A/RTL границы сохранены.

### История: C5 — выдано от принятого backend / C0 2026-09-18

Принятый API base: `aa7e792555c19d798eafa0cae17d29b73ca12376`, tree `77ddd22af30ef07afa89f61e96e1066ba4be8692`. PR #7 MERGED; отдельный push/main run `35321610083` SUCCESS, 199 tests. Post-merge приёмка: `docs/reviews/M1_2_BACKEND_C0_ACCEPTANCE.md`, текущее решение в едином реестре. Ниже pre-merge сведения сохранены как история и больше не являются запретом C5.

Выдан scope той же M1.2: responsive login/logout/session-expired/recovery Business Console, выбор только доступных Workspace, защищённое отображение Business и browser journey через неизменённый Application API. Ops surface остаётся без privileged/tenant content. Сначала минимальный UI/API/error/recovery contract в docs/tasks/M1_2_UI_CONTRACT.md, затем реализация. Настоящие synthetic данные получаются через backend, не из фиктивных frontend auth flags. CSRF — только page memory; cookie — только HttpOnly/browser; client IDs/roles не являются разрешением.

Разрешены frontend source/tests/config и минимальные devDependencies с lock; docs/tasks/M1_2_UI_CONTRACT.md, docs/tasks/M1_2_UI_RUNBOOK.md, README. Для реального browser gate C0 разрешает test-only frontend/e2e + Playwright config, scripts/test_browser.sh, scripts/provision_browser_test.py, compose.browser.yaml и один дополнительный browser job в .github/workflows/ci.yml, не ослабляющий существующий foundation job. Secrets/state/screenshots/trace hygiene обязательны; backend runtime/DDL/auth contract, существующие 196 backend tests, locks backend и image digests не меняются. Frontend три прежних проверки сохраняют смысл. Нужен браузер через same-origin proxy и real PostgreSQL, а не только ASGITransport/jsdom; browser secrets не коммитятся/не выгружаются. Допустима минимальная .gitignore/.dockerignore адаптация для локальных тестовых выходов.

Стартовая ветка выбирается из принятого main SHA; c5/m1-2-login — желательное имя, автоматическая Codex ветка допустима. Один новый UI PR в main, не продолжение закрытого #7, без merge/auto-merge. C5 не переписывает эталонные канонические документы, не внедряет новые backend endpoints и не резервирует migration 0004. Необходимые изменения за границей задания — новый вопрос C0, не молчаливое расширение.

C8-M1.2-02: ambiguous response требует current-session/bootstrap recovery с сохранением намерения logout, без слепого mutation replay и ложного success. Клиент не продлевает expiry и не заменяет серверную membership-проверку. Нужны component tests и Playwright/Chromium E2E (desktop + narrow viewport), обычный full pipeline и отдельный browser gate на одном опубликованном snapshot. Production/identity MFA/Client capabilities/M1.3 остаются вне задачи.

### История разрешения перед интеграцией / C0 2026-09-18

Рабочая реализация находится в PR **#7**, ветка **codex/-m1.2-r2**, head `194ea3cfa3f0aa9b8f271590a26ca3857ade3e54`, tree `799f271cbfc1c8815136828da35f9a32ef58b16e`. Старый PR #6 и c1/m1-2-auth не используются для продолжения реализации. C0 принял targeted C8 PASS, закрытие C8-M1.2-01/C0-M1.2-04 и контрактную обработку C8-M1.2-02. Полный CI `35248449942` подтвердил 199 tests и все gates. Границы evidence — в task register и `docs/reviews/M1_2_BACKEND_C0_PREMERGE.md`.

Backend одобрен для интеграции, но ещё не интегрирован в main на момент этой записи. C5 не запускается до отдельной проверки actual merge и push/main CI и передачи точного принятого API SHA от C0. PR test-merge `c99d9cc7e781fd9acf20ae7276761336e38b99d1` не является этим SHA. Полная M1.2 остаётся REVIEW, не VERIFIED.

Следующий C5 scope после явной выдачи: login/logout/session-expired UI, состояние загрузки и ошибок, минимальное защищённое чтение Business и общий browser journey через существующий API. Источники API: `contracts/openapi.json`, `contracts/auth.v1.json`, `docs/tasks/M1_2_AUTH_CONTRACT.md`. Cookies остаются HttpOnly; CSRF хранится только в текущем состоянии страницы; membership DTO не заменяет серверную авторизацию.

C8-M1.2-02 остаётся обязательством UI: потеря HTTP-ответа не означает rollback. Не обещать exactly-once доставку Set-Cookie, не повторять login/rotate/logout вслепую и не показывать ложный успешный logout. Восстановление current-session/bootstrap и очистка displayed identity на 401 выполняются по уже описанному auth contract. DDL, backend security semantics, Platform Ops grants/MFA, реальные провайдеры и M1.3 не входят в следующий UI-срез.

Разделы реализации C1 ниже сохраняют выданные критерии и историю, а не поручают заново писать готовый backend. Новых API/TTL или архитектурных решений в этой записи нет.

### Snapshot

Точный полный base C0 указывает в сопровождающем стартовом сообщении после проверки итогового main с документами приёмки. Это может быть documentation-only descendant принятого implementation merge; moving main или старый M0 не заменяют его. Исходная ветка C1: `c1/m1-2-auth`; актуальная реализация продолжена через Codex в `codex/-m1.2-r2` / PR #7. Будущая C5: `c5/m1-2-login` от отдельно выданного API SHA. Existing branches не перезаписывать; общий checkout не предполагать.

### Источники

Spec §§1.1, 2, 16.1/16.7/16.9, 17.3/17.4/17.12/17.13, 18.5, 22.2; ADR-002–006, 107, 109, 116–117, 119–120, 125–126, 160–161, 194–195, 206, 216; Roadmap §5; Implementation Plan §§5–6/9. Читать принятый M1.1 contract и guard tests. Same-Workspace Client authorization — future capability gate, не доказанный наличием login.

### Контракт до DDL/API

Запиши `docs/tasks/M1_2_AUTH_CONTRACT.md` и ограниченный machine-readable contract: login identifier/нормализация, поддерживаемые password/session libraries, storage/lookup/grants, session lifecycle/rotation/revocation, cookie/CSRF protocol, errors, transaction boundary и API для C5. Обычные реализационные решения выбери и обоснуй в `docs/decisions/IMPL-002-auth.md`; конфликт с LOCKED вынеси C0. Не выдавай новые поля/TTL за ранее принятые факты. Production TTL/abuse thresholds — конфигурация, TEST значения явно маркируются.

### Backend scope C1

Рабочий вход synthetic владельца по проверяемым credentials, серверная сессия PostgreSQL и непрозрачный случайный cookie token. Signed client-side session payload, JWT/localStorage и память процесса не заменяют canonical server session. Используй поддерживаемый password hashing (Argon2id — рекомендуемый кандидат), CSPRNG и готовые crypto primitives. В DB хранить безопасный verifier session token, не повторно используемую bearer-копию. Plaintext passwords, cookies, hashes и tokens не входят в Git/логи/CI artifacts.

Current-session, серверный logout/revocation, expiry, fixation-resistant rotation; старый token после logout/revocation не работает. AuthenticatedAccount создаёт только проверенный auth adapter, не десериализация UUID/actor/role/permissions из запроса. Workspace selector — лишь кандидат, далее активные account/workspace/membership и M1.1 UOW. Role downgrade, membership revoke и account disable должны влиять на следующие защищённые операции без cached Owner fallback. Опиши и проверь гонку revocation с уже допущенной короткой операцией; не обещай отменить уже committed действие.

Минимальный защищённый read Business через M1.1 нужен для API+DB проверки. Не добавляй остальные business mutations ради демонстрации. Не обходи task-owned UOW/AUTOCOMMIT guard и не удерживай длинную DB-транзакцию при дорогом password hash или внешнем HTTP. При проверке credentials вне транзакции перепроверь auth state/version перед созданием session/допуском операции.

Pre-context lookup/auth writes — только узкие контрактные пути. Не выдавай runtime общие CRUD на existing platform identity tables, migration credentials, BYPASSRLS/ownership/DDL или generic SECURITY DEFINER SQL. Конкретные функции/grants перечисли для review C2/C0. Нужен воспроизводимый LOCAL/TEST provisioning synthetic login без публичной регистрации, hardcoded рабочего пароля, CLI secret arguments или печати secrets. Setup вправе использовать отдельную provisioning identity; API/worker — runtime only.

Browser contract: HttpOnly, explicit SameSite, Secure при TLS; local HTTP exception только LOCAL/TEST. CSRF для изменяющих запросов, включая login/logout, не один SameSite. Явные trusted origins/CORS, отсутствие доверия arbitrary forwarded host; запрет state-changing GET. Ограничить входной размер, дорогие login attempts и account enumeration; минимальный исполнимый throttling с честной границей restart/replica, без Redis dependency. Errors/telemetry без passwords/cookies/hash/token/DB URL.

Business session не даёт Platform Ops rights. Статическая Ops shell допустима, привилегированные данные/команды без отдельного authorization plane/MFA — нет. Health/technical shell не раскрывают tenant data. SupportAccessGrant и production Ops здесь не реализуются.

### Scope файлов и очередь миграций

C0 резервирует `migrations/versions/0003_auth_sessions.py`, revision `0003`, down_revision `0002`. 0001/0002 не менять. Только необходимые credentials/sessions/защитное состояние, без будущих domain tables. C2/C0 сохраняют владение общей очередью; DDL/grants явно перечислить.

Разрешены `backend/src/asm/auth/`, `tests/test_auth*.py`, auth contract/IMPL-002 выше, `contracts/auth.v1.json` и generated OpenAPI; `foundation.py` только settings/router/wiring/readiness. Для 0003 разрешена точечная schema-revision/metadata адаптация tenancy types/contract/snapshot и tests: без изменения guard/RLS/permissions semantics и без удаления отрицательных assertions. Все 89 прежних cases сохраняют смысл; новые увеличивают число.

Минимальные `pyproject.toml`/`uv.lock` изменения разрешены только для выбранной auth library, без массового upgrade. Допустим `scripts/provision_local_auth.py`; startup/Compose env wiring — только необходимое с явным diff. Общие CI scripts — лишь подключение новых checks и обоснованная адаптация smoke к законным 401/403 без снятия защиты. Frontend, bootstrap/роли/image digests вне scope без C0. Реестр обновляет только C0.

### Backend acceptance

Real PostgreSQL + runtime identity: правильные/неправильные credentials, unknown/disabled account, session persistence между двумя app instances, forged/expired/revoked tokens, logout/rotation/fixation. API+DB: anonymous/expired/revoked отказ, чужие Workspace/Business IDs, revoke/role downgrade и отсутствие повышения прав через BusinessMember.role. CSRF отсутствует/неверен/из другой session, login/logout CSRF, hostile origin, cookie flags, rate/size limits, redacted errors/logs и platform-grant restrictions. Конкурентные session/rotation/revocation paths проверяются по явно принятому контракту, а не случайному timing.

Выполнить `python3 scripts/import_architecture.py docs/architecture` и полный `sh scripts/ci.sh`: все прежние 89 tests + новые, fresh/M1.1 upgrade/replay/disposable reversal/re-upgrade, readiness, contract drift, build/reproducibility/smoke/clean-source. Mock не заменяет session persistence/RLS/locks. Destructive downgrade — только disposable TEST, не production rollback.

### Handoff

C1 возвращает PR без merge, полный base/head и pre-DDL contract commit, DDL/grants/dependency diff, точные команды/результаты, CI/tested SHA/tree и ограничения. Для C5: endpoints, schemas/errors, cookie credentials mode, CSRF bootstrap/rotation, logout/expiry UX и synthetic provisioning. C0/C8 проверяют backend, C0 затем выдаёт C5 API SHA. C5 реализует login/logout/session-expired UI и общий API+UI journey. Только после этого M1.2 может быть VERIFIED; M1.3 не запускать самостоятельно.

### Не входит

M1.3 Audit/Plan/Subscription/Entitlements; Telegram/AI/Client/Conversation/File/Inbox/Outbox/Jobs; цены/расписание/платежи. Email/SMS/OAuth/SSO/password-reset provider, публичная регистрация, invite/team-management UI и production activation не требуются для этого среза. Login не равен готовой commercial identity platform. Реальные данные мастера/API accounts/расходы не нужны.

### Дополнительные рекомендации, не замена канона

C0 сверил первичные источники. Конкретная library/patch выбирается C1 до кода; FastAPI пример используется для password hashing, не как разрешение заменить серверные sessions JWT.
- https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/

## M1.3 — local entitlements и Audit

Ведущий C1, DDL C2/C0, последующий UI C5, проверки C8. Зависимость M1.1 удовлетворена; M1.2 принята. **Выдан только этап pre-DDL contract** от `28c289ce6f77e33676cfa416585cc0e20c0be4e3`. Миграционный номер и executable scope выдаёт C0 после review; параллельных DDL writers нет.

Scope сохраняется: WorkspaceBillingAccount, immutable SaaSPlanRevision/PlanEntitlements, Subscription TRIALING либо ACTIVE+COMPED, WorkspaceServiceMode и EntitlementService без `if plan == ...`, hidden bypass или paid provider. Entitlements не заменяют security permissions. Audit с реальным actor/correlation и атомарностью одной domain mutation; Audit != Outbox != technical log. Реальные тарифы/billing secrets/client payments вне задачи.

Первый результат — `docs/tasks/M1_3_CONTRACT.md`: точное предложение table/schema/keys/grants/RLS и permission matrix; границы immutable/local state; policy time/interval decisions; предложение безопасной демонстрационной операции и её атомарного Audit; тест-план для real PostgreSQL и негативных границ, без реализации будущих domain tables. Отсутствующие решения отметить OPEN с вариантами и рекомендацией. Это contract proposal, не подтверждённая реализация, DDL approval или PASS M1.3. Новый Draft PR в main, без merge/auto-merge.
