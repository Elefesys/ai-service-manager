# M1 — принятый tenant foundation и следующие задания

Ответственный за интеграцию: C0. Единственный task register: `docs/TASK_REGISTER.md`. Канон: `docs/architecture/01_ARCHITECTURE_SPEC.md`, действующие ADR, MVP/Roadmap и `09_IMPLEMENTATION_PLAN.md`; стек: IMPL-001; правила: AGENTS.md.

## Единственный активный handoff — C0: ручная интеграция UI PR #15 / 2026-09-20

Статус — только [TASK_REGISTER](../TASK_REGISTER.md). DB/API INTEGRATED / VERIFIED;
UI REVIEW, C0 full-PR PASS; targeted C8 PASS исправления UI-01. M1.3 IN_PROGRESS.
Поручение C5 выполнено и сохранено ниже как история; повторно его не запускать.

- Repository: `https://github.com/Elefesys/ai-service-manager.git`.
- PR: [#15](https://github.com/Elefesys/ai-service-manager/pull/15),
  `c5/m1-3-owner-ui` → `main`, Draft / open / not merged.
- Accepted base / actual API merge: `43f22b5e28a93e269eccc25bf73653e47fd01426`,
  tree `a6051034784d30e1ecb4af4c28caf4a596dafdab`;
  [push/main CI 35508232378](https://github.com/Elefesys/ai-service-manager/actions/runs/35508232378) SUCCESS.
- Сохранён coordination head `2274667f06ddd72b1a02c57fb555456e948f2c50`.
- Reviewed implementation с ограниченным fix:
  `7630032d29dc3f79f48a9089b60492b2520384c5`,
  tree `203fdd8c7da809a17866df8feb77dbfa90218139`.
  [CI 35511904393](https://github.com/Elefesys/ai-service-manager/actions/runs/35511904393)
  SUCCESS, 415 cases, оба clean-source gates PASS.
- [UI C0 receipt](../reviews/M1_3_UI_C0_ACCEPTANCE.md) содержит проверяемую матрицу,
  закрытый дефект и границы C0/C8/browser evidence. [UI runbook](M1_3_UI_RUNBOOK.md)
  описывает работу готового UI и воспроизводимые команды, не новое задание.

### Последнее действие до merge

После этого согласованного docs update C0 проверяет SUCCESS CI именно итогового
head и неизменный main/base; full head/tree, tested merge SHA/parents/tree и URL run
фиксируются в PR и ответе C0. Не создавать новый commit лишь для записи SHA этого
документа. Если head/base изменился неожиданно, проверить конкретную дельту прежде
чем разрешать merge. Нельзя переносить старый SUCCESS на непроверенный snapshot.

Пользователь открывает PR #15 и после финального подтверждения C0 выполняет
**Ready for review → Create a merge commit → Confirm merge**. Без squash/rebase,
force-push, auto-merge или обхода защит. Вернуть C0 «слито» либо URL merge commit;
техническую проверку SHA/CI пользователь не собирает самостоятельно.

### После фактического merge

C0 проверяет actual merge parents = принятый main + final PR head, tree = final
reviewed tree, отдельный workflow event `push` / branch `main` / head и tested SHA
= actual merge. Оба jobs/clean-source gates, 153 backend non-integration,
189 real PostgreSQL, 58 frontend и 15 real browser должны пройти на этом snapshot.
Затем согласованно фиксирует интеграцию UI и итоговое решение всей M1.3 с учётом
сохранённой DB/API приёмки. До этого UI не INTEGRATED/VERIFIED и M1.3 IN_PROGRESS.

Никаких новых обязательных implementation работ или архитектурных изменений не
назначено. Сохраняются R4/D-01…D-13, прежние auth/tenancy/grants, snapshot/service,
одна typed DB command, три маршрута, один owner panel и Audit limit10. Новое broad
C8 review без конкретного риска не нужно. M2/production/providers/payments/Jobs,
catalog/subscription/mode editors и полный production Ops не выдаются.

## История — выполненное поручение C0 → C5, owner UI / 2026-09-20

Ниже сохранены принятый scope и критерии; это завершённое поручение, не активная
инструкция снова начинать реализацию. Его приёмка/evidence находятся выше.


Это полное конечное поручение C5. Единственный статус исполнения находится в
[TASK_REGISTER](../TASK_REGISTER.md). DB и backend/API INTEGRATED / VERIFIED;
полная M1.3 IN_PROGRESS. Реализовать только owner UI/browser часть принятого R4.

### Repository, base и ветка

- Repository: `https://github.com/Elefesys/ai-service-manager.git`.
- Accepted implementation base: **`43f22b5e28a93e269eccc25bf73653e47fd01426`** — actual
  merge PR #14; tree `a6051034784d30e1ecb4af4c28caf4a596dafdab`.
- [Отдельный push/main CI 35508232378](https://github.com/Elefesys/ai-service-manager/actions/runs/35508232378)
  SUCCESS, 378 cases, оба clean-source gates PASS; exact tested SHA равен base.
- Task branch: **`c5/m1-3-owner-ui`**, target `main`. Продолжать единственный
  подготовленный Draft PR этой ветки; его номер и полный стартовый head C0
  передаёт в сопровождающем сообщении/PR. PR #14 закрыт после merge.
- Сохранить первый C0 coordination commit. Он меняет только TASK_REGISTER,
  этот handoff, API receipt и исторический контекст DB receipt. Не выполнять
  отдельный docs merge, не переписывать coordination history.
- Работать в отдельном checkout. Проверить refs/ancestry; при неожиданной code
  delta/base сообщить C0 точное расхождение, не force-push/rebase/merge самостоятельно.

### Источники и неизменяемая граница

Прочитать AGENTS, актуальные Spec §§15–17, применимые ADR-002/005/006/064/099…109/
126/182, MVP и Implementation Plan, [R4](M1_3_CONTRACT.md) §§4–7,
[API acceptance](../reviews/M1_3_API_C0_ACCEPTANCE.md), существующий auth/UI contract
и recovery tests M1.2. R4 SHA-256:
`0d33a26aa13fb3eda34b0a5c07a4a11dc263b1ee37ce9e3fda126f53e0c0282a`.
D-01…D-13 приняты; исторические PROPOSED/PENDING внутри R4 не открывают новый design gate.

API DTO/schema source — **`contracts/openapi.json`** на accepted base, consumer/recovery
notes — **`contracts/README.md`**. R4 нормативен. Не создавать новый конкурирующий
контракт, не вычислять billing decisions по имени плана и не подменять разрешения UI.
Auth/tenancy/DB и все 342 backend cases уже приняты; их не переписывать ради UI.

### Разрешённые файлы

- `frontend/src/`: только необходимые billing DTO/parser/API adapter, owner panel,
  локальное UI state/recovery, wiring в существующую Console, styles и component tests.
  Сохранить прежние auth request ownership/logout intent, Business read и Ops isolation.
- `frontend/e2e/`: новые M1.3 journeys и необходимые узкие helpers; прежние шесть
  journeys и safe diagnostics сохраняют assertions. `frontend/playwright.config.ts`
  — только необходимое включение нового suite/desktop+narrow, без retries/skip ради PASS.
- `scripts/provision_browser_test.py` и, если нужна отдельная узкая реализация,
  `scripts/m1_3_browser_fixture.py`: TEST-only synthetic billing setup/fixtures,
  используя принятую `platform.initialize_local_billing(...)`, существующую
  provisioning identity и disposable `asm_test`. Никаких runtime test endpoints
  или generic SQL interface. Новые fixture helpers имеют проверки environment,
  database и identity до записи; текущие protections сохраняются.
- `scripts/test_browser.sh`, `compose.browser.yaml`: только передача нужных
  private fixture files/test presets и bounded TEST wiring. Сохранить rendered
  Compose check, tmpfs, unprivileged API, 0600 secrets, cleanup и отсутствие их в artifacts.
  Если дополнительные legitimate journeys упираются в общий rate budget, C0
  разрешает только в browser TEST overlay `ASM_AUTH_PEER_LIMIT=300`,
  `ASM_AUTH_GLOBAL_LIMIT=1000`, `ASM_AUTH_LOGIN_LIMIT=100`; defaults и реальные
  backend rate-limit regressions неизменны. Это fixture capacity, не новая policy.
- `README.md` и при необходимости `docs/tasks/M1_3_UI_RUNBOOK.md` — только реальные
  команды запуска/fixtures/проверки готового UI. TASK_REGISTER и этот handoff —
  фактический ход/evidence без самостоятельной приёмки; история сохраняется.

Не выданы backend runtime, SQL/DDL/migrations 0001…0004/grants, R4, frozen auth/tenancy
contracts и generated OpenAPI; package/lock/image changes, новые dependencies,
перепроектирование CI, новые endpoints и privileged Ops. Если принятого API не
хватает из-за конкретного defect, вернуть C0 воспроизводимый blocker; не обходить
его frontend fallback или сменой DB contract.

### Конечный UI

Один минимальный owner panel внутри существующей Business Console для выбранного
Workspace, с тремя понятными частями. Новый router/design system не нужен.

1. **Подписка и entitlements.** Показать текущий contact, plan/revision и subscription
   status/funding/effective interval (или явную INACTIVE/no-current-subscription),
   mode и его независимую активность, пять серверных decisions и numeric limits,
   включая `"0"`. Activity/availability/decisions брать из API. Отдельные loading,
   empty/inactive, unavailable/error состояния; не показывать fake FREE/paid или
   empty success вместо structural503. Сохранить LOCAL/TEST маркировку.
2. **Contact edit.** Одна форма `contact_display_name`; expected_version из последнего
   подтверждённого GET. Save/Pending/Recovery/ошибка/подтверждённый результат; mutation
   pending блокирует повторный submit и изменение её замороженного body. После
   подтверждённого PATCH получать current state через GET; replay metadata не является
   текущим account. NOOP не обещает новый version/Audit; structural mode ограничения
   не блокируют разрешённую contact administration, auth или Business read.
3. **Audit.** Только два принятых event types/payload. Читаемые дата/действие/инициатор;
   безопасные metadata при необходимости. Фиксированный limit10 и «Загрузить ещё»
   по непрозрачному next_cursor; null прекращает загрузку. Refresh начинает страницу
   заново; Workspace change сбрасывает старые rows/cursor. Без фильтров/экспорта/
   универсального Audit editor и без contact values/keys/fingerprints в Audit.

Панель доступна OWNER выбранного Workspace; role из session используется только для
видимости UI. Реальная authority проверяется API на каждом запросе. ADMIN/PROVIDER,
revoked/foreign не получают данные/controls через stale UI. Backend403 прекращает
доступ и убирает защищённые данные этого контекста. Ops shell остаётся без billing/Audit.
Layout, labels, клавиатура, focus/error announcements и narrow viewport должны работать
в существующем интерфейсе; дополнительных экранов управления не требуется.

### Точный API и wire

Все пути относительно `/api/v1/workspaces/{workspace_id}`:

| Метод/path | Live permission | Использование |
|---|---|---|
| GET `/billing` | OWNER billing:read | Без query; один snapshot account/subscription/mode/availability/decisions |
| PATCH `/billing-account` | OWNER billing:manage | Только `{expected_version,contact_display_name}`; immutable receipt metadata |
| GET `/audit-events` | OWNER audit:read | Только limit1…100 и cursor, exact items/next_cursor |

PATCH response только `{workspace_id,billing_account_id,receipt_id,result_version,
outcome,completed_at}`. Один `Idempotency-Key` `[A-Za-z0-9._:-]{1,128}`; генерировать
новый через browser crypto только для нового намерения. Существующие HttpOnly
cookie/credentials include, configured Origin и memory-only CSRF обязательны;
If-Match запрещён. CORS уже реализован C1; backend allowlists не менять.

Новые bigint versions/limits — decimal strings, не JavaScript Number. Новые UUID
lowercase canonical по OpenAPI (не переносить старую v4/v7-only проверку DTO).
Timestamps имеют шесть UTC fractional digits; сохранить точную wire строку, не
восстанавливать cursor из Date с потерей microseconds. Canonical cursor передавать
неизменным. Strict DTO/tagged decisions/error unions проверять на входе adapter.
Старые auth/business DTO/parsers и их ошибки не ослаблять новым общим permissive parser.

Contact trim — только U+0020, далее1…200 Unicode scalars/<=800 UTF-8 bytes, без
C0/DEL/lone surrogates, без NFC/NFD/casefold. Не использовать обычный JS trim или
HTML maxLength200 как подмену scalar bound: они отвергнут допустимые padded/emoji
inputs. Backend остаётся authoritative; input schema API-01 уже исправлена.

Errors:401/403 по прежнему auth contract; PATCH404 NOT_FOUND;409 STALE_STATE или
IDEMPOTENCY_KEY_CONFLICT;422 INVALID_REQUEST. CommonError ровно `{error:{code}}`;
только structural GET503 — `{error:{code:"BILLING_STATE_UNAVAILABLE",state_reason}}`
с четырьмя bounded reasons. Отдельный503 UNAVAILABLE остаётся code-only. Billing503
не означает logout и не даёт показывать отсутствующий plan как действующий.
Ошибки/логи не содержат raw response diagnostics, credentials или contact/key contents.

### Recovery и ownership — обязательные критерии

- До отправки PATCH зафиксировать в памяти страницы actor, Workspace, intention,
  exact body/expected_version и key. Timeout/network/abort/malformed success/5xx
  могут означать commit. Не показывать ложный success или гарантированный rollback.
- Сохранить это намерение через auth/current-session/bootstrap/login/CSRF recovery.
  После проверки того же actor и выбранного Workspace и текущего доступа повторить
  **тот же body/key/expected_version** только для того же намерения, затем GET.
  Новый key или новый version из recovery GET не заменяет разрешение неоднозначности.
  Повторная recovery failure оставляет pending/uncertain с явным bounded retry;
  не выполнять бесконечные/слепые background mutations.
- При смене actor/Workspace/намерения не переносить старую pending mutation в новый
  контекст и не replay её автоматически. Защищённые данные скрыть, старое намерение
  отделить/завершить явным решением пользователя с честным статусом неизвестного
  результата.401/403 не доказывают rollback ранее допущенной команды.
- STALE_STATE: показать конфликт, получить current state, сохранить draft отдельно;
  только явное новое сохранение создаёт новое намерение/key от новой версии.
  IDEMPOTENCY_KEY_CONFLICT: остановиться и показать конфликт, не обходить его новым
  key автоматически. PATCH200 + GET failure — команда подтверждена, current read
  недоступен; повторять GET, не создавать новую mutation.
- Memory-only: cookies/CSRF/password/contact body/key не сохранять в localStorage,
  sessionStorage, IndexedDB, URL или logs. Reload не даёт права придумывать потерянный
  key и автоматически повторять запись; после reload только current state/read flow.
- Reads, saves, recovery и Audit pages имеют request ownership по generation +
  actor/Workspace. Поздние success **и error** старого контекста не обновляют новый
  UI. Abort не является доказательством rollback. Сохранить уже принятые auth
  sequence/logout-intent guards; focus/session recheck не должен терять pending contact
  намерение или применять устаревший billing response.

### Конечная проверка

Component/adapter tests детерминированы deferred promises/barriers; покрыть:

- exact new DTO/error unions, bigint0/max string, six-digit timestamps, padded200
  emoji/Unicode normalization boundaries; no permissive auth-parser regression;
- active/inactive/mode-disabled/missing-state UI, OWNER visibility и403, Audit
  paging/end/reset; local billing failures не блокируют auth/Business;
- change/NOOP, stale/conflict, PATCH success followed by GET failure; same-intent
  repeated ambiguous recovery; auth/CSRF refresh; actor/Workspace changes, поздние
  read/write/Audit success/error и отсутствие второго submit нового key.

Реальные Playwright journeys через Console → существующий API → PostgreSQL,
штатный asm_runtime и disposable TEST fixtures должны подтвердить:

1. Owner login, billing snapshot/limit0, contact UPDATE и NOOP, fresh GET/reload,
   Audit update без contact values, pagination/end. Happy path также @narrow/keyboard.
2. Stale edit с другой реальной HTTP-сессией/командой:409, current GET, сохранённый
   draft и явное новое намерение; не потеря update и не automatic overwrite.
3. Потеря PATCH response **после настоящего route.fetch/commit**: контролируемо
   abort только delivery, recovery auth/CSRF, проверенный same body/key replay,
   один version increment и один contact Audit, затем GET. Fake successful body
   без server call не считается этим evidence. Bounded callbacks/finally cleanup.
4. Аутентифицированный A→foreign B отказ для billing/Audit/contact и отсутствие
   чужих данных; текущая owner permission revoke/downgrade прекращает UI доступ.
   Anonymous tamper из старого M1.2 suite не заменяет authenticated проверку.
5. Реальное inactive/restricted состояние fixture отображается по API, contact
   administration/auth/Business сохраняют принятые права. Браузерный CORS positive
   PATCH из `http://127.0.0.1:8080` к API `http://127.0.0.1:8000` с credentials и
   content-type,x-csrf-token,idempotency-key; disallowed-header preflight не отправляет
   mutation. Configured origins уже приняты, новые origins не нужны.

Сценарии можно объединять по общим fixtures; не нужен декартов набор всех modes
или повтор DB/service matrix. Test-only setup может создать foreign Workspace и
изменить synthetic membership/interval; это не production API/editor. Fixture
параметры конечны и именованы, teardown не касается чужих/постоянных данных.
Вызовы route.fetch/callbacks используют существующие safeDiagnostic conventions;
secrets/body/key не выводятся даже при failed assertions. Если доказательство
ограничено mock/component сценарием, так и отметить — это не browser/DB result.

Выполнить штатные **`sh scripts/ci.sh`** и **`sh scripts/test_browser.sh`** на одном
итоговом published snapshot; GitHub Docker runner допустим при local limitation.
Сохранить 153 non-integration +189 PostgreSQL accepted base tests,30 frontend и6
прежних journeys; новые tests добавляются. Также frontend typecheck/test/build,
canonical imports, generated contract check, migrations/reproducibility/smoke и оба
clean-source gates. Не отключать tests, не подменять PostgreSQL/mock или добавлять
retry ради PASS. Node24 и существующий lock достаточны, новых dependencies не выдано.

### Возврат C0 и оставшаяся последовательность

Вернуть существующий Draft PR без merge: полный base/start/final head/tree, paths,
точные команды/results, URL последнего CI и фактически tested SHA/parents/tree,
отдельные counts старых/новых tests, список journeys с реальным evidence, recovery
semantics, ограничения и конкретные blockers. Первый coordination commit сохранён;
не создавать chain docs commits ради SHA. UI не объявлять VERIFIED самостоятельно.

C0 review → при конкретном риске targeted C8 → ручной merge после final-head CI →
проверка actual merge/main CI → итоговая приёмка всей M1.3. M2, production,
providers/payments, Jobs/Outbox, catalog/subscription/mode editors и расширение R4
не входят. Перепроектировать уже принятые части не требуется.

## История — выполненная интеграция backend/API PR #14

Следующий блок сохраняет прежнее поручение и pre-merge evidence. Его условия
actual merge/main CI выполнены; он не является текущим заданием или blocker.


Статус исполнения ведётся только в [TASK_REGISTER](../TASK_REGISTER.md).
DB принят. Полный C0 review backend/API PASS; два конкретных targeted C8 P2
исправлены и проверены. API остаётся REVIEW до ручного merge и отдельного main CI.
M1.3 IN_PROGRESS; C5 и M2 не запускать.

- Repository: `https://github.com/Elefesys/ai-service-manager.git`.
- PR: [#14](https://github.com/Elefesys/ai-service-manager/pull/14),
  `c1/m1-3-billing-api` → `main`, без squash/rebase/force-push/auto-merge.
- Accepted DB base: `2bd339ee9bb4638588e5f07b63723caaf717c619`;
  tree `5bf0a4fc429cc11b1b1b2da03147fad6ab088ad8`, push/main 35503584157 SUCCESS.
- Reviewed implementation с исправлением: `a6d44560f035a4a288ab62abbac1ad2bde3651ad`,
  tree `2a587356a9591c6a997ab245a2c0c9403930222b`;
  [CI 35507439390](https://github.com/Elefesys/ai-service-manager/actions/runs/35507439390)
  SUCCESS: 153 non-integration + 189 real PostgreSQL + 30 frontend + 6 прежних browser = 378 cases; оба clean-source gates PASS. Evidence и критерии: [API receipt](../reviews/M1_3_API_C0_ACCEPTANCE.md).
- Последующий согласованный docs commit содержит только TASK_REGISTER, этот
  handoff и API receipt. Итоговые head/CI фиксируются в PR и ответе C0, а не
  новым коммитом ради SHA предыдущего документа.

### Точное следующее действие

После проверки C0 SUCCESS итогового head пользователь открывает PR #14,
нажимает **Ready for review**, выбирает **Create a merge commit** и подтверждает
merge. Вернуть C0 «слито» или ссылку на merge commit. C0 сам проверяет фактические
parents/tree/merge SHA и отдельный `push/main` CI; PR virtual merge его не заменяет.
Не обходить неизвестные/красные gates. При неожиданной code delta/base — конкретная
проверка C0, без автоматического нового design cycle.

### После фактической интеграции API

Только C0 после main evidence выдаёт полностью готовое ограниченное C5 поручение
с точным base. Конечный scope: один минимальный owner screen, состояние
subscription/entitlements, изменение `contact_display_name` с корректным recovery,
Audit pagination, component tests и настоящие browser/API/PostgreSQL journeys M1.3.
Источники DTO — generated `contracts/openapi.json`, consumer/recovery notes —
`contracts/README.md`; нормативный R4 и D-01…D-13 сохраняются.

Сохранить intention/body/key при неоднозначном PATCH; восстановить auth/CSRF,
проверить actor/Workspace, повторять тот же key/body только для прежнего намерения,
затем GET current state. Не заменять recovery новым key; не считать replay текущим
account state. OWNER permissions отдельны от неизменной tenancy matrix.

Дополнительные backend routes, catalog/subscription/mode editors, payments,
провайдеры, generic frameworks, migrations и M2 не выданы. После C5/main CI
нужна отдельная итоговая приёмка M1.3; API PASS не завершает milestone.

## История — выполненное поручение C1 backend/API

Следующий блок сохраняет выданный scope и критерии, но не требует повторной
реализации или повторного review уже проверенных частей.


Это готовое задание C1. Выполнить backend/API часть принятого R4 последовательно, без расширения scope и перепроектирования уже принятого DB/auth. Состояния задач ведутся только в [TASK_REGISTER](../TASK_REGISTER.md). DB-срез INTEGRATED / VERIFIED; M1.3 IN_PROGRESS. C5 и M2 не запускать.

### Repository, base и продолжение

- Repository: `https://github.com/Elefesys/ai-service-manager.git`.
- Принятый implementation base: **`2bd339ee9bb4638588e5f07b63723caaf717c619`**, actual merge PR #13 в main.
- Accepted tree: `5bf0a4fc429cc11b1b1b2da03147fad6ab088ad8`.
- Отдельный main evidence: [push run 35503584157](https://github.com/Elefesys/ai-service-manager/actions/runs/35503584157), foundation + browser + clean-source SUCCESS, 288 cases.
- Task branch: **`c1/m1-3-billing-api`**, integration target `main`. Продолжать единственный подготовленный Draft PR этой ветки; PR #13 уже слит, не переоткрывать его и не создавать конкурирующий implementation PR.
- Первый C0 coordination commit на task branch меняет только TASK_REGISTER, этот handoff и DB receipt. Сохранить его при продолжении. Полный published head передан в PR/сообщении; не записывать SHA текущего docs commit следующим docs commit.
- Отдельный checkout. Перед работой подтвердить refs/ancestry; при неожиданной code delta/base передать точную дельту C0, не применять force-push/rebase/merge самостоятельно.

### Основание и разрешённые paths

Прочитать AGENTS, актуальную Spec, применимые ADR, Implementation Plan и принятый
[контракт R4](M1_3_CONTRACT.md), особенно §3–7. SHA-256 R4:
`0d33a26aa13fb3eda34b0a5c07a4a11dc263b1ee37ce9e3fda126f53e0c0282a`.
DB receipt и R4/C0 disposition фиксируют приёмку; исторические PROPOSED/PENDING
в самом контракте не означают повторный design gate. D-01…D-13 сохраняются.
Применимые области: Workspace/security boundaries, ADR-002/005/006,
ADR-064, ADR-099…109, ADR-126 и ADR-182; исходные canonical docs не редактировать.

Разрешены:

- `backend/src/asm/billing/` — repository, typed models/errors/permissions, EntitlementService и HTTP adapter; создавать только необходимые модули.
- `backend/src/asm/foundation.py` — узкий wiring новых services/router, без переноса domain logic в foundation.
- `backend/src/asm/tenancy/database.py` — только необходимые узкие guarded методы/адаптация для billing repository на текущем tenant connection; сохранять task/XID/connection/transaction guard и rollback. Не делать общий публичный raw-SQL bypass.
- `backend/src/asm/auth/http.py` — additive CORS и минимальное повторное использование существующей boundary/CSRF plumbing; auth protocol/семантику старых routes не менять. `auth/service.py` допускается лишь для необходимого узкого reuse, без изменения admission/revocation/TTL/cookie поведения.
- `scripts/export_contracts.py`, `contracts/openapi.json`, `contracts/README.md` — генерация и описание новых schemas/routes; существующие `contracts/auth.v1.json`, `contracts/tenancy.v1.json` и их семантика остаются неизменными.
- `tests/test_m1_3_*` и новые тематические billing/API tests; точные additive inventory/schema assertions в существующих contract/foundation tests, когда это нужно для трёх новых routes. Старые coverage/assertions не удалять ради зелёного CI.
- Этот активный handoff и TASK_REGISTER — фактический ход/evidence без самоприёмки; API consumer details отражать generated OpenAPI, не вторым конкурирующим контрактом.

Не выданы migrations/DDL/role grants, изменение 0001…0004, package/lock/image/CI
перепроектирование, frontend и browser UI M1.3. Если найден DB defect, вернуть
конкретный reproducer C0/C2; не переписывать уже интегрированную 0004.

### Конечный результат C1

1. **Billing repository и настоящий EntitlementService.** Один fixed SQL statement
   с одним `CURRENT_TIMESTAMP` читает на принятом RLS tenant connection account,
   subscription history/current `[)` interval, mode, pinned SEALED revision,
   catalog/entitlements. Не собирать coherent snapshot из нескольких READ COMMITTED
   SELECTs. Archived plan не отменяет pinned SEALED revision. Evaluated time — DB.
   Decision precedence §6: structural failure → subscription inactive → mode
   inactive → missing known key → mode restriction → typed value. NORMAL разрешает
   все criticalities; GRACE ESSENTIAL/STANDARD; LIMITED ESSENTIAL; SUSPENDED none.
   BOOLEAN true/false, INTEGER limit включая `"0"`, отсутствие known key и независимая
   активность mode/subscription реализованы в service. Никаких `if plan == ...`,
   fake paid state или provider calls. SQL feasibility test DB-среза не заменяет service.

2. **Ровно три маршрута R4.**

   | Method/path | Требование |
   |---|---|
   | `GET /api/v1/workspaces/{workspace_id}/billing` | OWNER `billing:read` |
   | `PATCH /api/v1/workspaces/{workspace_id}/billing-account` | OWNER `billing:manage` |
   | `GET /api/v1/workspaces/{workspace_id}/audit-events` | OWNER `audit:read` |

   Workspace из route — selector. Authority приходит из server session и live
   membership на том же tenant UOW. Billing permissions — отдельная явная typed
   policy OWNER-only; использовать принятый live membership resolver внутри UOW.
   Не выводить OWNER из `tenancy:write` (ADMIN тоже имеет его), не расширять старую
   tenancy permission matrix/AuthResponse и не доверять UI role/actor/header.
   ADMIN/PROVIDER/revoked/foreign/неаутентифицированные не получают billing/Audit.
   Entitlements не заменяют permissions и не блокируют auth/старые Business reads
   либо разрешённую contact administration при GRACE/LIMITED/SUSPENDED.

3. **DTO и errors ровно §7.** Strict objects, UUID lowercase canonical,
   timestamptz UTC с шестью дробными digits, bigint versions/limits как decimal
   strings. Positive version 1…9223372036854775807; integer limit 0 допустим.
   GET billing без query; точные account/subscription/mode/availability/decisions
   поля §7.1, five known TEST keys, unique sorted decisions max100; missing keys
   остаются NOT_ENTITLED entries. При valid history без current subscription —
   200 INACTIVE/subscription null; структурный сбой не имитировать empty success.
   Precedence reason: MISSING → INVALID → REVISION_INVALID; unreadable DB только
   DATABASE_UNAVAILABLE, без выдуманного MISSING.

   PATCH body только `{expected_version,contact_display_name}`. Response только
   `{workspace_id,billing_account_id,receipt_id,result_version,outcome,completed_at}`;
   outcome UPDATED/NOOP. Replay возвращает прежние immutable metadata, current
   contact клиент получает через GET.

   `CommonError` ровно `{error:{code}}`; `BillingStateError` ровно
   `{error:{code:"BILLING_STATE_UNAVAILABLE",state_reason}}`. State reason обязателен
   только во втором варианте: BILLING_STATE_MISSING/BILLING_STATE_INVALID/
   REVISION_INVALID/DATABASE_UNAVAILABLE. Сохранить оба разных 503:
   shared boundary `UNAVAILABLE` и structural billing GET `BILLING_STATE_UNAVAILABLE`.
   401/403 — существующие auth codes; PATCH 404 NOT_FOUND, 409 STALE_STATE либо
   IDEMPOTENCY_KEY_CONFLICT; strict input/cursor 422 INVALID_REQUEST.
   SQLSTATE переводить только в контексте конкретной billing command, сохранив
   общий tenancy mapping и poisoned-UOW rollback; не объявлять любой 40001 всей
   системы STALE_STATE. Исключения/SQL/PII/cookie/key/fingerprint в response/logs не выводить.

4. **Audit pagination.** Exact item/page §7.3; provisioning `{}` и contact
   `{changed_fields:["contact_display_name"]}` без значений контакта. Только query
   `limit` 1…100, default25, и один cursor. Order `(occurred_at DESC,audit_event_id DESC)`,
   tuple `<`, fetch limit+1; next_cursor от последнего возвращённого item лишь при
   наличии следующего; конец/empty → null. Cursor <=1024 ASCII, unpadded base64url
   compact strict UTF-8 JSON с точными `{v:1,endpoint:"AUDIT_EVENTS",workspace_id,
   direction:"DESC",occurred_at,id}`. Duplicate/extra/missing/wrong/foreign/nonexistent
   tenant anchor → safe422; anchor lookup tenant-scoped. Cursor не credential,
   не подписанный token и не обещание frozen-history.

5. **Auth/CSRF/idempotency.** Сохранить R4 §4 order: HTTP size/header/Origin/CSRF
   boundary → outer `AuthService.workspace` shared admission → distinct tenant
   UOW/XID trusted context → live OWNER permission → bounded normalization/hash →
   receipt → account CAS/Audit/finalize → tenant commit → release admission → response.
   Использовать существующую `platform.update_billing_contact(bigint,text,text)`
   как единственный write path; не выполнять direct DML и не переносить receipt/Audit
   в другую transaction. Ранее принятый FOR NO KEY UPDATE/CAS порядок не менять.
   Ровно один `Idempotency-Key` `[A-Za-z0-9._:-]{1,128}`, `If-Match` запрещён.
   Strict UTF-8/scalars, trim только U+0020, name1…200 scalars/<=800bytes, без
   C0/DEL/surrogates/NFC/NFD/casefold. Exact canonical bytes/hash §5, восемь vectors.
   Auth/permission проверяются до fingerprint/receipt и снова при replay; ключ не
   credential. Stale до no-op; no-op сохраняет version/updated_at и не добавляет Audit.
   Changed name +1/один Audit; same key+same fingerprint exact replay после later
   change; другой fingerprint конфликт; разные keys одной версии — один winner.
   Audit/finalize/outer failure откатывают mutation/receipt/Audit; не продолжать
   aborted transaction. Для C5 описать ambiguous-result recovery: тот же key/body
   только для того же намерения после auth/CSRF recovery, затем GET current state;
   не подменять неоднозначный результат новым key и не обещать слепой replay.

6. **Только additive CORS.** Добавить PATCH к `[GET,POST]`, Idempotency-Key к
   существующим Content-Type/X-CSRF-Token/X-CSRF-Bootstrap. Сохранить configured
   Origins, credentials=true, Host/Origin/CSRF/JSON controls и отсутствие wildcard.
   Положительный HTTP preflight: configured Origin + PATCH +
   content-type,x-csrf-token,idempotency-key. Отрицательные: foreign Origin,
   disallowed method/header. Реальный M1.3 browser proof — следующий C5 после API.

7. **Generated contracts и существенные tests.** Generate/review/commit
   `contracts/openapi.json` из реализованных Pydantic models/routes; exact error
   union, strict DTO/decimal/timestamps и response codes должны совпасть с runtime.
   Не добавлять nullable state_reason к старому auth error. Дрейф проверяет CI.
   Сохранить все семь M1.2 routes и их wire semantics; endpoint inventory проверяет
   точное прежнее множество плюс три разрешённых, а не произвольный superset.

### Проверка и возврат C0

Добавить реальные API + PostgreSQL tests под штатным `asm_runtime` для:

- Success GET/service decisions по четырём modes, BOOLEAN false/INTEGER zero,
  independent inactive/future intervals и missing state/DB-unreadable boundaries;
  unit tests покрывают полную precedence matrix и невозможные при обычном DDL
  contradictory snapshots с честным указанием границы evidence.
- OWNER success, ADMIN/PROVIDER deny, foreign Workspace, disabled/revoked session/
  membership, отсутствие receipt observation/write до auth; accepted revocation
  admission ordering, pooled context cleanup и XID guards сохраняются.
- HTTP PATCH→настоящая SQL command: change/no-op/stale/conflict/replay after later
  change, ambiguous response after commit и последующий same-intent replay/GET;
  same-key и different-key concurrency, rollback/Audit/finalize failure. Существенные
  SQL инварианты уже приняты; повторять их только для нового API/UOW соединения.
- Strict raw headers/body/query: duplicate/missing key, If-Match, extra
  JSON fields по strict контракту, malformed UTF-8/surrogate/C0/DEL, decimal zero/leading-zero/overflow,
  границы name; восемь fingerprint vectors через API совпадают с DB receipts.
- Cursor pagination с одинаковыми timestamps/UUID tie-break, end/empty,
  invalid/foreign/nonexistent anchors и сохранением tenant boundary.
- Runtime responses + OpenAPI, оба 503 discriminators, безопасные ошибки;
  additive CORS positive/negative preflight без регрессии прежней auth boundary.

Выполнить штатные `sh scripts/ci.sh` и `sh scripts/test_browser.sh` в поддерживаемом
Docker runner (GitHub CI допустим при sandbox limitation). Отдельно
`python scripts/export_contracts.py --check`. Ruff/mypy/unit/real PostgreSQL,
frontend regression, существующие шесть browser journeys, canonical imports,
reproducibility и clean-source остаются обязательными. Новые browser journeys UI
M1.3 сюда не выдаются. Не заменять реальную PostgreSQL/API проверку mock или
описанием; не добавлять skip/xfail ради зелёного CI. После конечного commit нужен
полный CI именно этого head; не суммировать повторные runs в число tests.

Вернуть C0 в одном сообщении: PR URL; accepted base и полный final head/tree;
что реализовано/изменённые paths; generated contract diff; команды и фактические
результаты; exact CI/tested SHA/tree; ограничения/конкретные blockers; готовые для
C5 endpoint/DTO/error/cursor/auth/CSRF/recovery сведения. PR оставить Draft/open,
без merge, без самостоятельного INTEGRATED/VERIFIED. C0 проверяет implementation;
новый review назначает по конкретным рискам/критериям, затем разрешает пользователю
интеграцию и проверяет actual main CI. C5 — только после этого, M2 не выдавать.

### C1 — реализация активного backend/API поручения / 2026-09-20

Implementation candidate находится в существующем Draft PR #14. Сохранены
подготовленный coordination commit и принятый implementation base. Фактическое
состояние — в TASK_REGISTER; приёмка API/C5/M2 самостоятельно не объявляется.

- `asm/billing/`: strict models/validation/errors, отдельная OWNER policy,
  fixed SQL repository и `EntitlementService.decide(snapshot, key)`, HTTP adapter.
  Snapshot включает DB time и interval flags одним statement; критичность берётся
  только из pinned SEALED revision. Archived plan, INTEGER zero и все precedence
  уровни покрыты; billing state не управляет auth/contact admission.
- `tenancy/database.py`: только guarded fixed billing methods на текущем connection,
  live membership resolver и локальный mapping intentional contact-command RAISEs.
  Общий tenancy SQLSTATE mapping не изменён; failed UOW остаётся poisoned.
- OpenAPI сгенерирован из работающих routes/models; consumer сведения, включая
  same-intent ambiguous-result recovery и GET current state, — `contracts/README.md`.
- `tests/test_m1_3_service.py`: 37 unit cases для полной precedence, contradictory
  snapshots (честно вне обычного DDL), восьми exact vectors и strict wire primitives.
- `tests/test_m1_3_http_contract.py`: 9 schema/CORS cases; прежний auth inventory test
  теперь требует точное множество семи старых плюс три новых routes.
- `tests/test_m1_3_api_postgres.py`: 43 real PostgreSQL/API cases для modes/intervals,
  OWNER/live revocation/foreign tenant, read failures и обоих 503, CAS/no-op/replay,
  raw inputs, восьми fingerprints в receipts, Audit keyset, rollback, admission race,
  concurrent claims и ambiguous committed result recovery. PostgreSQL fault injection
  меняет только изолированные test fixtures/statements, не runtime DDL/privileges.

Локально прошли 152 non-integration tests, Ruff/format/mypy, contract drift и
canonical import. Docker здесь отсутствует; collection PostgreSQL tests не
выдаётся за исполнение. Полный unchanged CI runner и шесть M1.2 browser journeys
обязательны на конечном опубликованном snapshot. Exact final head/tree и CI/tested
SHA/tree передаются в PR/сообщении C0 после последнего commit, без записи собственного
SHA следующим docs commit. UI M1.3 browser proof остаётся будущим C5.

## Архив handoff — не текущие задания

Весь текст ниже сохраняет историю решений и прежних выдач. При расхождении текущие действия определяет единственный активный блок выше и TASK_REGISTER; старые base/status/запреты не переисполнять.

### История — DB pre-merge M1.3 / 2026-09-20

Статусы — в [TASK_REGISTER](../TASK_REGISTER.md); DB-решение, матрица и evidence — в [M1_3_DB_C0_ACCEPTANCE](../reviews/M1_3_DB_C0_ACCEPTANCE.md). M1.3 IN_PROGRESS; M0/M1.1/M1.2 сохраняют VERIFIED.

PR #13 `codex/-m1.3-db-only-0004` → `main`, base `552e74c7b542b81ee523d1eccfa0fffe7de06a5b`. Reviewed implementation snapshot `cc172d12e3d48f47d294d862a0c73b6ea126320d`; текущая документационная синхронизация меняет только реестр, этот handoff и DB receipt. Не создавать новый commit только ради записи SHA этой синхронизации. Итоговый PR head и его SUCCESS CI фиксирует C0 в PR и сообщении пользователю.

Ближайшее действие: C0 DB review и targeted C8 завершены **PASS**, implementation CI 35502644158 **SUCCESS**; C0 проверяет полный CI итогового docs head и фиксирует точный результат в PR. После явного READY TO MERGE пользователь переводит Draft PR #13 в Ready for review при необходимости и выполняет **Create a merge commit**. Без squash/rebase/auto-merge/обхода protections. При новой code delta или изменении base C0 проверяет её до merge. C0 сам не сливает PR.

После фактического merge пользователь возвращает URL PR или merge SHA. C0 сам проверяет actual merge commit, родителей/дерево и отдельный `push` run на `main`; PR virtual merge не заменяет эту проверку. Принимается только DB-срез. Затем C0 готовит одно полностью готовое сообщение C1 от подтверждённого base; пользователь не собирает поручение из файлов и не выбирает SQL/поля/тесты.

Фиксированный следующий scope C1 по неизменному R4:

- Billing repository и настоящий EntitlementService с согласованным DB snapshot и accepted service-mode truth table.
- Только `GET /api/v1/workspaces/{workspace_id}/billing`, `PATCH /api/v1/workspaces/{workspace_id}/billing-account`, `GET /api/v1/workspaces/{workspace_id}/audit-events`.
- OWNER permissions `billing:read`, `billing:manage`, `audit:read`; exact DTO/errors/cursor/decimal/timestamps.
- Принятый M1.2 auth admission, отдельный tenant UOW, XID context, Origin/CSRF и idempotency ordering/recovery; без изменения старого auth-контракта.
- Только additive CORS: `PATCH` + `Idempotency-Key` с сохранением прежних методов/headers/configured Origin/credentials.
- Generated contracts и существенные API/PostgreSQL проверки, включая negative permissions, replay/revocation/rollback, оба 503 discriminators, cursor и CORS.

C1 ещё не выдан до main DB evidence. C5 не запускать до приёмки и интеграции C1. Следующее ограниченное поручение C5: один owner screen с subscription/entitlements, изменением `contact_display_name` и корректным recovery, просмотром Audit, component tests и реальными browser journeys M1.3. Никаких дополнительных экранов, billing providers или будущих capabilities. После обеих частей C0 проверяет milestone acceptance; до этого M1.3 не VERIFIED и M2 не выдаётся.

Принятые R4/D-01…D-13, 0001/0002/0003, tenant/auth mechanisms и предыдущие acceptance остаются в силе. SQL feasibility тест не заменяет EntitlementService; шесть существующих browser journeys — regression M1.2, не доказательство UI M1.3. Дополнительные архитектурные предложения требуют отдельного явного решения и не входят автоматически в обязательный scope.

### История — M1.2 принята, M1.3 pre-DDL / 2026-09-18

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

Ведущий доменного/backend slice C1; DDL/миграции C2 под C0; последующий UI C5; независимые проверки C8. M1.1 и M1.2 VERIFIED. M1.3 milestone остаётся `IN_PROGRESS`.

### Pre-DDL contract — INTEGRATED / VERIFIED

Canonical R4 принят C0/C2 и интегрирован:
- actual main base до DB coordination: `ce585d67168489083e9b94e4be4f5669b16a8552`;
- tree `ace73cdf8163428eb74872c35ce9e920d5e9066c`;
- contract Git blob `d1e80cb9242a4c0a88e2762bb17d46fa4d9f3320`;
- contract SHA-256 `0d33a26aa13fb3eda34b0a5c07a4a11dc263b1ee37ce9e3fda126f53e0c0282a`;
- PR #9 MERGED;
- post-merge run `35460116356` SUCCESS.

Это приёмка контракта, не M1.3 implementation.

### C2 DB prerequisite — PASS

Exact pinned image:
`pgvector/pgvector@sha256:2ba9ca5f2e7daa0f0e7723cba1ee9167bab54efd3640516a44ac1a928dd67e7a`.

GitHub-hosted probe PR #11 был одноразовым test-only evidence и закрыт без merge. Final head `fca70041c86a859fd1aa8fcb06c95d2a0a830681`; tested virtual merge `e1e327162297a556a99d8873a741f775a13aacf2`, tree `44dc6a2c85cc95045c8001812c78c47941f7998d`.

Special run `35463399932` SUCCESS доказал на exact image:
- PostgreSQL 18.6 / vector 0.8.6;
- `btree_gist` 1.8, namespace `extensions`, trusted/relocatable;
- default `extensions.gist_uuid_ops` для uuid equality;
- exact GiST exclusion behavior;
- отсутствие необходимости расширять privileges `asm_migrator`;
- idempotent repeated preflight;
- fail-before-domain-DDL.

Receipt: `docs/reviews/M1_3_BTREE_GIST_C0_ACCEPTANCE.md`.

### Migration reservation

C0 резервирует исключительно для C2 M1.3 DB slice:
- file: `migrations/versions/0004_billing_entitlements_audit.py`;
- revision: `0004`;
- down_revision: `0003`.

0001/0002/0003 не менять. Параллельных DDL writers нет. Reservation не означает, что migration уже реализирована или принята.

### C2 DB implementation scope

Источник истины — exact `docs/tasks/M1_3_CONTRACT.md`; D-01…D-13 и принятые R4 semantics менять нельзя без нового C0 decision.

Разрешён DB-only slice:
- admin/bootstrap prerequisite `btree_gist` для fresh LOCAL/TEST и explicit existing-0003 preflight/fail-closed path;
- exact 8 tables R4;
- keys/checks/composite tenant-safe FKs;
- finite half-open subscription intervals и declarative GiST exclusion;
- ENABLE + FORCE RLS для пяти Workspace-owned tables;
- XID-fenced tenant context и migrator policy по принятому contract;
- SEALED revision/entitlement immutability and lock order;
- grants/catalog read surface;
- exact SECURITY DEFINER `platform.update_billing_contact(...)` DB command;
- LOCAL/TEST synthetic catalog/provisioning DB primitives;
- real PostgreSQL tests для isolation, constraints, grants, concurrency, replay/idempotency DB semantics и migration replay.

Backend HTTP routes, application EntitlementService orchestration, CORS, OpenAPI generation и frontend **не входят** в C2 DB slice.

### Evidence / acceptance boundary

C2 обязан вернуть exact base/head/tree, migration/grant diff, real PostgreSQL commands/results, fresh + existing-0003 + replay path, disposable downgrade/re-upgrade where safe, concurrency evidence and limitations. Все существующие tests сохраняют смысл и новый полный CI должен быть green. C0/C8 проводят отдельный review до merge.

Не drop `btree_gist` на downgrade. Не выдавать `CREATE` на database/schema `extensions` роли `asm_migrator`. Не делать runtime owner/SUPERUSER/BYPASSRLS. Не расширять scope до billing provider/client payments/Jobs/production retention.

После DB integration C0 отдельно выдаёт C1 backend/API/CORS slice; C5 только после принятого API SHA.
