# M5 — настройки бизнеса, знания, Vision и портфолио

Дата: 2026-11-12. Ведущий: C0. Статус исполнения — только в
[TASK_REGISTER](../TASK_REGISTER.md). Решение по объёму:
[IMPL-005](../decisions/IMPL-005-m5-pilot-knowledge.md) — ACCEPTED / LOCKED C0.

## CURRENT — M5.1B → C4 / IN_PROGRESS — CI repair / 2026-11-13

Единственная активная задача: **C4-M5.1B-PUBLISHED-KNOWLEDGE-R1**.
Ведущий C4; C1/C3 согласуют backend/runtime/delivery, C2 — SQL/миграцию и
сериализацию; затем C5 добавляет UI. Это участие в одном срезе/PR, не несколько
параллельных выдач. Общие файлы редактировать последовательно; C4 собирает возврат.
M5.1A завершён; M5.2A и последующие срезы не выданы.

[Решение C0 по repair PR #47](https://github.com/Elefesys/ai-service-manager/pull/47#issuecomment-6844936121)
принято к исполнению. Repair start
`a8067f1ad0cd5baffcd28379109009fb9ba7173f`, tree
`7c8a442465cb00711eebf09714765ce987a7723b`; implementation base и C0 docs
`3b2a28a192753103017dab5452288cde61226d95` сохраняются. Это продолжение M5.1B,
не новая выдача и не приёмка.

- Repository: `Elefesys/ai-service-manager`; integration target: `main`.
- Accepted implementation base: `6c27be8487f3f8792cf01ed2a0fcdde130ea7a52`.
- Base tree: `1aa2959f1ba28438304ef758947ba241f6d0b729`.
- Ветка: `c4/m5-1b-published-knowledge-r1`; начать с подготовленного C0 docs-only
  commit поверх этого base и сохранить его. Не начинать от старого planning SHA.
- PR #46 интегрирован: parents main49d3e259 + reviewed headd4626334; tree равен
  проверенному кандидату. [C0 review PASS](https://github.com/Elefesys/ai-service-manager/pull/46#pullrequestreview-5876870257).
  [Post-merge CI43245856346](https://github.com/Elefesys/ai-service-manager/actions/runs/43245856346),
  push/main, attempt1: **12/12 SUCCESS**, все jobs completed, failed steps нет.
  M5.1A — **INTEGRATED / VERIFIED в LOCAL/TEST**. Новый прогон C0 не запускал.
- Принятый API/bundle/rollback контракт M5.1A:
  [handoff d4626334](https://github.com/Elefesys/ai-service-manager/blob/d4626334613a91a6ff5e75c57b2edcc05181f69f/docs/tasks/M5_HANDOFF.md).
  Его длинный исходный write-set и старые ошибки CI не являются текущим заданием.

### Пользовательский результат

Владелец через небольшой раздел Console редактирует услуги, правила и FAQ,
видит различие draft/active, deterministic preview и ошибки, публикует изменения.
Текстовый AI runtime получает только опубликованные сведения этого Business.
После новой публикации/rollback следующий ответ использует новую activation;
устаревший ещё не допущенный к отправке ответ блокируется.

Это первый полезный сценарий знаний из принятого §3 / IMPL-005. Без него M5.1A
остаётся API подготовки данных, которыми AI ещё не пользуется. Откладывать его
ради embeddings/Vision не нужно. Цена/время/предоплата здесь только известные
настройки либо явное неизвестное; индивидуальный расчёт и обязательства — не M5.

### Контракт перед реализацией

Прочитать AGENTS, этот CURRENT, IMPL-005 и применимые IMPL-004; Spec §10.14–17,
ADR-030/031/032/072/075/076/262–267. Сначала C4 с участниками кратко фиксирует
здесь выбранные DTO/версии, точки SQL-проверки, порядок locks и UI состояния.
Затем реализует этот контракт. Новый конфликт с принятым решением вернуть C0
с точным пунктом, меньшим рабочим вариантом и последствиями; не отменять молча.

1. Использовать существующий `configuration` bundle v1 и active projection.
   Доверенный Workspace/Business/Client получается из admitted job/run, не из
   model arguments. Начать с небольшой service card, structured rules/style и
   bounded FAQ selection; deterministic structured/keyword selection достаточно.
   Не создавать KnowledgeBuild/index tables или embedding profile заранее.
   Неопубликованный draft, чужой Business и частные данные другого Client не
   попадают в projection; общие опубликованные FAQ доступны клиентам своего Business.
2. Ввести явную новую версию knowledge-aware context/read DTO и bundled prompt
   `conversation_v3.txt`. Старые Context/Read DTO, prompts v1/v2 и сохранённые runs
   сохраняют исходную семантику. Result schema v1 можно сохранить, если её shape
   не меняется; при изменении shape нужна отдельная v2, без ослабления v1.
   Привязка source/release/activation и provenance вычисляется сервером, не LLM.
   Контракт не обязан добавлять новый read tool: компактный bundle можно включить
   сервером в ContextPack, сохранив максимум2 model calls/1 READ и прежние бюджеты.
3. Закрепить immutable release + монотонную activation version и версию projection
   в durable run и выбранном результате/delivery binding. Отсутствие публикации
   также явное состояние: первый publish инвалидирует ранее подготовленный
   контекст «знаний нет». Draft edit не инвалидирует неизменившийся active.
   Rollback к прежнему release не возвращает старую activation (защита от ABA).
4. Проверять актуальность на MODEL/READ/FOLLOWUP/CANDIDATE/COMMIT/SEND, включая
   call reservation, текущий rights-refresh COMMIT и окончательный send admission.
   Publish/rollback и admission используют согласованную точку сериализации в
   БД. Если публикация выиграла, старый run не делает новый вызов/отправку и не
   переключается молча на новый набор внутри уже начатого run. Уже допущенный
   внешний эффект не объявлять отозванным. HTTP не держит DB transaction/locks;
   нет fan-out update всех conversations, event bus или нового worker engine.
5. Старые сохранённые runs/receipts не переписывать и не backfill'ить выдуманными
   publication pins. Явно определить legacy replay/read и безопасный отказ там,
   где старый run не удовлетворяет новому admission; повтор не регенерирует ответ.
   HUMAN/Resume, OWNER reconciliation, observation barrier, Telegram rights/TTL,
   claim/generation/currentness и UNKNOWN/no-resend сохраняются одновременно.
6. FAQ/owner text остаются данными, не system policy. Structured rules выше FAQ;
   пустой/противоречивый источник, неизвестная цена/длительность — уточнение или
   существующий handoff, без выдуманных значений. Источник/revision/authority
   ограничены по размеру и видны в trace и owner preview/active view; внутренние
   UUID, storage keys и скрытые поля не печатаются клиенту. Не вводить новый trace UI.
7. C5 после согласования backend делает формы услуг/правил/FAQ/стиля, читаемые
   draft/active, ERROR/WARNING, preview, publish и допустимый rollback. Использовать
   шесть принятых owner API; нельзя заставлять владельца редактировать SQL/JSON.
   Независимые policy fields и nullable unknown не теряются при сохранении формы.
   Нужны версия/конфликт, запрет publish при ERROR, объяснение ROLLBACK_NOT_ALLOWED,
   восстановление неопределённого результата команды тем же key/body и защита от
   позднего ответа после смены Workspace/Business/logout. UI не заменяет live OWNER.
   Preview локальный/deterministic, без model call, расхода и отправки клиенту.
8. AI по умолчанию OFF; FAKE/EVAL_ONLY остаётся ограниченным режимом проверки.
   Существующий provider bridge сохраняется; для новой версии проверяется только
   локальная wire/contract совместимость. Старый paid approval не переносится на
   новый prompt/source. Не включать provider, не менять маршрут/стоимость/лимиты.

### Контракт C4/C1/C2/C3/C5 перед реализацией — 2026-11-13

Base выдачи **3b2a28a192753103017dab5452288cde61226d95**, tree
**0d93ec5242def3e31b6a650b1c0b24d2766cf343**, sole parent accepted
**6c27be8487f3f8792cf01ed2a0fcdde130ea7a52**. Head миграций подтверждён:0018.

- Новый private `KnowledgePin`: business/release (null при отсутствии публикации),
  монотонная activation version и `business_knowledge_v1`. Run сохраняет pin и
  immutable active projection из configuration bundle v1; delivery сохраняет тот
  же pin. Client/scope берутся из admitted job. Draft не участвует в projection.
- Новый context/read `conversation_context_v2`, отдельный `KnowledgeGatewayConfig`
  и prompt `conversation_v3`;
  result schema остаётся v1. Прежние context/read/prompt/run/receipt не меняют
  семантику. Active service cards и structured rules сохраняются целиком;
  bounded keyword selection FAQ показывает source/authority/revision и усечение.
  Owner/FAQ text — data; structured rules приоритетны. Unknown остаётся null.
- 0019 добавляет nullable bindings без backfill. На current schema новые runs
  требуют v3; legacy receipt/replay/accounting доступны, новые эффекты старого
  NULL-pinned run отклоняются. Replay не регенерирует ответ. Explicit unpublished
  pin инвалидируется первым publish; rollback увеличивает activation.
- Сериализация: job/run → owner authority → Business FOR SHARE → существующий
  CONFIGURATION_V1 advisory transaction lock → connection/billing/conversation/
  turn/client. Publish/rollback используют owner → Business → тот же advisory
  lock → state. Publisher не ждёт job/run/conversation. Pin проверяется на
  MODEL/READ/FOLLOWUP/CANDIDATE/RESERVE/COMMIT, rights-refresh COMMIT и SEND.
  COMPLETE/replay не требуют свежести публикации. HTTP вне транзакции;
  выигравший SEND admission остаётся допущенным при последующем publish.
- Console использует шесть owner API: формы service/rules/FAQ/style, draft/active,
  ERROR/WARNING, deterministic preview, CAS publish и rollback. Unknown сохраняется;
  неопределённая команда повторяется с тем же key/body, смена scope/logout
  отменяет владение поздним ответом. Preview не вызывает модель или transport.
- Default OFF,2 calls/1 READ и прежние limits. Для provider v3 нужен новый явный
  synthetic knowledge profile/prompt; прежний v2 approval не переносится.
  Здесь проверяется только локальный wire с MockTransport, без paid/live допуска.

### Миграция и разрешённые paths

C0 резервирует только `0019_published_knowledge.py`, revision `0019`, predecessor
`0018`. C2 перед SQL подтверждает единственный актуальный head0018 и согласует
минимальные durable bindings/constraints/locks. При дрейфе head вернуть вопрос C0;
applied `0001–0018` побайтово неизменны. Нет будущих бизнесовых таблиц. Использовать
существующие run/delivery/configuration boundaries; необходимость отдельной таблицы
должна следовать из конкретной операции и быть объяснена в контракте, не из терминов
baseline. Не переписывать миграцию0018 ради нового publication/admission lock.

Основной write-set (создавать/менять только реально нужное):

```text
backend/src/asm/ai/context.py
backend/src/asm/ai/knowledge.py
backend/src/asm/ai/agent.py
backend/src/asm/ai/contracts.py
backend/src/asm/ai/runtime_contracts.py
backend/src/asm/ai/database.py
backend/src/asm/ai/runtime.py
backend/src/asm/ai/runtime_settings.py
backend/src/asm/ai/provider_runtime.py
backend/src/asm/ai/settings.py
backend/src/asm/ai/gateway.py
backend/src/asm/ai/fake.py
backend/src/asm/ai/prompts/conversation_v3.txt
backend/src/asm/ai/schemas/conversation_result_v2.json
backend/src/asm/configuration/models.py
backend/src/asm/configuration/repository.py
backend/src/asm/configuration/service.py
backend/src/asm/configuration/validation.py
backend/src/asm/tenancy/database.py
backend/src/asm/messaging/database.py
backend/src/asm/messaging/results.py
backend/src/asm/messaging/errors.py
backend/src/asm/messaging/worker.py
backend/src/asm/foundation.py
migrations/versions/0019_published_knowledge.py
contracts/openapi.json
frontend/src/ConfigurationPanel.tsx
frontend/src/ConfigurationPanel.test.tsx
frontend/src/configuration-api.ts
frontend/src/configuration-api.test.ts
frontend/src/configuration-fixtures.test-helper.ts
frontend/src/App.tsx
frontend/src/App.test.tsx
frontend/src/style.css
frontend/e2e/configuration.spec.ts
frontend/e2e/messaging.spec.ts
tests/test_m5_knowledge.py
tests/test_m5_knowledge_migrations.py
tests/test_m5_knowledge_postgres.py
tests/test_m5_knowledge_runtime.py
tests/test_m5_knowledge_runtime_postgres.py
tests/m5_knowledge_fixtures.py
tests/m5_configuration_fixtures.py
tests/test_m5_configuration.py
tests/test_m5_configuration_migrations.py
tests/test_m5_configuration_postgres.py
tests/test_m5_configuration_api_postgres.py
tests/test_m4_context.py
tests/test_m4_agent.py
tests/test_m4_gateway.py
tests/test_m4_runtime_database.py
tests/test_m4_runtime_postgres.py
tests/test_m4_polza_runtime.py
tests/test_m4_polza_runtime_migrations.py
scripts/m2_4_browser_worker.py
scripts/test_browser.sh
docs/tasks/M5_HANDOFF.md
```

`contracts/openapi.json` — только штатная генерация при реальном изменении schema;
новые owner endpoints не требуются. `test_browser.sh`/browser worker — только
finite synthetic сценарий знания/UI, без произвольного test HTTP endpoint и без
ослабления runtime-only роли. Исходящий transport остаётся текстовым.

Ниже отдельное допустимое подмножество только для current-schema/profile перехода
на0019 и проверок действительно затронутой runtime границы. Это не поручение
менять всё и не разрешение переписать прежние отрицательные проверки:

```text
backend/src/asm/telegram/provisioning.py
scripts/native_context_db_catalog.py
scripts/m4_runtime_db.py
scripts/m2_4_browser_fixture.py
scripts/prepare_telegram_egress.py
scripts/test_telegram_egress.sh
tests/generic_pg_schema.py
tests/test_foundation.py
tests/test_auth_contract.py
tests/test_postgres.py
tests/test_tenancy_postgres.py
tests/test_native_context_db_runner.py
tests/test_m4_runtime_db_runner.py
tests/test_m4_delivery.py
tests/test_m4_reply_rights.py
tests/test_m4_runtime_migrations.py
tests/test_m4_schema_postgres.py
tests/test_m4_polza_runtime_postgres.py
tests/test_m4_delivery_postgres.py
tests/test_m4_reply_rights_postgres.py
tests/test_m2_3_setup.py
tests/test_m2_3_db_postgres.py
tests/test_m2_3_schema_postgres.py
tests/test_m2_4_browser_fixture.py
tests/test_browser_compose.py
tests/test_m3_1_guards_migrations.py
tests/test_m3_1_native_context_postgres.py
tests/test_m3_1_native_context_runtime_postgres.py
tests/test_m3_2_escalations_migrations.py
tests/test_telegram_egress.py
tests/test_telegram_egress_postgres.py
```

Exact counts/hashes/ACL выводить из реальной DDL и независимого installed catalog.
Исторические0013–0018 profiles/checkers сохранить; equality inventory не превращать
в subset. Auth routes не меняются; разрешение test_auth_contract не означает снятие
его полной проверки. Указать использованное compatibility подмножество с причинами.

В `scripts/m4_runtime_db.py` и его тестах разрешён только новый bounded admission
этой ветки/base/tree и перечисленного write-set, включая пять C0 документов:
`AGENTS.md`, `README.md`, `docs/TASK_REGISTER.md`,
`docs/decisions/IMPL-005-m5-pilot-knowledge.md`, `docs/tasks/M5_HANDOFF.md`.
Согласовать outer/export/inner и последующий push/main, сохранить прежние source
routes, same-repository/event/parents/tree/clean-source guards. До implementation
PR проверить позитивный маршрут и отказы на чужие branch/base/tree/path.

Не менять dependencies/locks, workflows, frozen auth/tenancy contracts, исходные
архитектурные файлы, старые prompt/schema/migration files и receipts M4. Другие
paths или реально нужный новый API согласуются с C0 по конкретной причине,
без нового разрешения владельца на рутинные исправления. C4/C5 не меняют CURRENT
реестра; согласованный контракт и один краткий возврат — в M5_HANDOFF/PR.
Разовое исключение C0 для этого совместного code/docs repair push: C4 обновляет
единственный CURRENT реестра на IN_PROGRESS / CI repair; далее CURRENT ведёт C0.
Новый exact path `frontend/e2e/messaging.spec.ts` разрешён только для вызова/
закрытой диагностики finite helper; его функциональные assertions сохраняются.

### Критерии готовности и возврат

1. Actual owner API/PG + реальный browser: создать/изменить synthetic FAQ и
   structured rule → preview → publish → active. Draft не влияет на AI; publish
   меняет видимые runtime факты. Новый вопрос проходит настоящий runtime/DB путь
   с fake model и controlled text transport; assertions проверяют model input,
   выбранный источник/release и единственный effect, а не только заранее заданный reply.
2. Actual PG под runtime role: первая публикация, новая версия и rollback
   инвалидируют старый run на перечисленных границах. Конкурентные publish и
   send admission проверяются в обоих порядках с наблюдаемым call/effect counter;
   stale путь не выполняет запрещённый вызов. Draft-only edit не даёт ложный stale.
3. Два Workspace/Business и два Client внутри одного Workspace: общий FAQ своего
   Business разрешён, чужие знания/личная история — нет. Подмена DTO/tool args,
   HUMAN, revoke, native observation, rights refresh и UNKNOWN/no-resend сохраняют
   отказ. Replay/restart не делает новый model call/вторую отправку. Старые runs
   остаются читаемы/безопасно отклоняются согласно явно зафиксированной версии.
4. Knowledge injection, конфликт structured rule/FAQ, отсутствие/неизвестность,
   лимит размера и provenance: нет draft/private data leak, исполнения инструкций
   из FAQ, ложной цены/времени/доступности. Fake/contract evidence не объявляется
   проверкой смыслового качества реальной LLM.
5. UI: OWNER/revoked-owner, session/CSRF, version conflict, uncertain mutation
   с тем же key, переключение Business/logout без поздней утечки; preview делает
   ноль model/Telegram calls. Минимум достаточных actual browser journeys,
   остальные гонки проверять адресно на API/PG, не дублировать всё во всех слоях.
6. Чистый upgrade и populated0018→0019, повторный upgrade, штатный migration cycle;
   прежние данные/права и pinned historical checkers сохранены. Current app отвергает
   старую схему; installed catalog соответствует new current profile. Нельзя
   разрушать новые durable данные ради обратного прохода тестовой миграции.
7. Сначала адресные проверки по изменениям; затем один штатный полный CI final
   кандидата. Новые actual-PG cases входят в существующие lanes с полным evidence,
   не новый workflow и не отдельный повтор старого M4. Зафиксировать достигнутые
   cases и source SHA; при ошибке отделить реализацию от инфраструктуры, без
   unchanged reruns и изменения expected ради PASS.

Вернуть один PR в main: final head/tree, короткий контракт C4/C1/C2/C3/C5,
миграция и версии DTO/prompt, используемые paths, воспроизводимый пользовательский
сценарий, целевые проверки и CI URL, оставшиеся ограничения. После зелёного CI
не делать отдельный status-only push. Приёмку/интеграцию и следующий CURRENT ведёт C0.
Если реализация перестаёт укладываться в связный небольшой срез, вернуть конкретную
границу C0 до расширения; новый workflow engine или сетка будущих задач не нужны.

Только synthetic LOCAL/TEST. Vision/embeddings/sendPhoto/intake/DurationCase,
VM/paid/live/реальные данные и merge не разрешены этой выдачей. Receiver ACK/fence
и полный live HUMAN/Resume остаются OPEN_OPERATIONAL, UNKNOWN/holds сохраняются.
Никаких фиктивных Telegram messages/conversations для бизнесовой конфигурации.



## C4 receipt — C4-M5.1B-PUBLISHED-KNOWLEDGE-R1 / REVIEW / 2026-11-13

Реализован контракт выше на **c4/m5-1b-published-knowledge-r1** поверх сохранённого
C0 docs commit **3b2a28a192753103017dab5452288cde61226d95**. Accepted base/tree
**6c27be8487f3f8792cf01ed2a0fcdde130ea7a52 /1aa2959f1ba28438304ef758947ba241f6d0b729**.
Final head/tree и CI URL возвращаются в PR; текущий реестр C4 не меняет.

В model input попадают active service cards/structured rules и до4 целых FAQ с
source/authority/revision; keyword ranking детерминирован, общий context≤8192
UTF-8 bytes. Owner/current/structured facts не режутся; overflow → STOP.
Draft, publisher/release UUID, storage и private Client context исключены.
Новые `KnowledgeGatewayConfig`, `PreparedKnowledgeRun`, context/read v2 и prompt v3
явно отделены от прежних DTO; result schema v1 и старые prompt/schema неизменны.
Durable pin включает business/release/null-unpublished, activation и projection
revision. MODEL/READ/FOLLOWUP/CANDIDATE/RESERVE/COMMIT/rights refresh/SEND проверяют
тот же pin. SQL reader использует настоящий admitted job/claim, не owner GUC.
Publish/rollback и admission используют общий business lock; HTTP вне транзакции.
Legacy SQL/Python replay/COMPLETE сохранены, backfill и regeneration отсутствуют.

0019←0018 добавляет bindings/FK/immutability в существующие run/delivery boundaries,
без новых таблиц. Populated downgrade отказывается до потери новых данных.
Installed PG18/source: **207 functions /52 tables /736 columns**, точные bodies,
ACL/RLS/constraints и прежние0013–0018 profiles. Full pin
`e2bfd685188e1b67430de02c03eb3cef3af8f13de74e13d641032085b3b23c36`, body
`93c1c8615c17619929194606686ebd21b7f99afa7698cfd425bb6b65035137f5`, nonfunction
`1583e77dbe74107fe93cbadd6c43ff20d1521e9f62b4a6b22e89447f5569743c` независимо сверены C3.

Console: формы service/rules/FAQ/style, draft/active/source, ERROR/WARNING,
read-only preview, CAS publish/rollback, тот же key/body при uncertain result,
защита смены Business/session/logout. Rollback UI предлагает до8 публикаций,
наблюдавшихся в памяти страницы; сервер окончательно проверяет допустимость.
Нового history API/trace UI нет. Provider settings v3 требуют явную новую пару
prompt/data profile; DB admission остаётся закрытым15-key, prompt внутри config.
V3 provider composition разрешает только MockTransport; live отклоняется до key load.

Фактическая локальная проверка, frozen uv/Python3.13.5 и npm ci:

- `PYTHONPATH=backend/src pytest -q -m 'not integration' --tb=short`:
  **3753 PASS +161 subtests /246.37s**. Последняя правка serializer отдельно:
  **155 targeted PASS /1.87s**; неизменённые negative fixtures сохранены.
- Actual owned PostgreSQL **18.6** из закреплённого OCI image, vector0.8.6 /
  btree_gist1.8, asm_test, runtime NOSUPERUSER/NOBYPASSRLS: **106 unique cases
  достигли PASS** — knowledge SQL17, runtime11, configuration PG25/API12,
  provider PG41. После исправлений повторялись затронутые группы: races4 +
  downgrade1 (**5 PASS /22.09s**), legacy Python replay (**1 PASS /12.44s**).
  Runtime11:44.71s; configuration25:13.59s; API12:9.57s; provider41:129.51s.
  Реальные PG locks в обоих порядках, first publish/rollback ABA, scopes,
  HUMAN/revoke/native/input/rights и UNKNOWN/no-resend проверены.
- Локальный temporary harness проверял настоящий base/tree/write-set и заменял
  только CI-file reader test fixture на **LOCAL_SOURCE_CHECK_NOT_CI**. Product
  SQL/roles/readiness/admission не обходились; GitHub CI evidence не имитировался.
- `ruff check backend/src tests scripts`, `ruff format --check backend/src tests scripts`:
  **PASS /209 files**; `mypy backend/src`: **87 files PASS**.
- `npm --prefix frontend run typecheck`, `npm --prefix frontend test`,
  `npm --prefix frontend run build`: **PASS /427 tests**. Три новых browser
  journeys добавлены, включая publish→отличающийся draft→реальный runtime/fake
  model→один controlled effect→DB replay. До PR actual browser ещё NOT_RUN.

Дельта57 paths строго внутри разрешения. Compatibility subset — current0019
readiness/provisioning/egress/catalog/source admission и соответствующие tests;
исторические M4 delivery/rights остаются явными0018/v2 carriers с возвратом0019.
Один новый finite browser preset требует двух text events; удалены два избыточных
pagination history events: остаются26 messages (>page25), seed127<128, прежние
сценарии/отрицательные проверки сохранены. OpenAPI/API shape, deps/locks/workflows,
0001–0018, старые prompts/schemas/receipts и архитектурные источники неизменны.

Real provider HTTP/owner key reads/Telegram/VM/paid/live **0**. Это synthetic
LOCAL/TEST plumbing/guards, не semantic quality реальной LLM и не M5 целиком.
AI default OFF,2 calls/1 READ, старые UNKNOWN/holds и operational gates сохранены.
Первый [CI43361745800](https://github.com/Elefesys/ai-service-manager/actions/runs/43361745800)
на head59c4b87e/treee8ee6904 выявил неверный application full pin: локальная
БД имела locale C, штатный Docker — en_US.utf8. Fresh artifact14009055081
независимо подтвердил all source bodies/security/nonfunction PASS, declared
valid=true и full e2bfd685; отличие только в порядке5 пар function rows.
Исправлен один application pin под canonical Docker; body/nonfunction/SQL и
строгие проверки прежние. Локальный reset с en_US.utf8 воспроизвёл exact e2bfd685
и valid=true; targeted profile pytest завершился exit0. Затем workspace стал
unavailable: повтор API/Ruff/mypy repair не завершён, нового PASS им не приписываем.
Первый native-context lane также RED; подробности в artifact14009171371,
локальная распаковка заблокирована недоступностью environment. Точная причина
этого отдельного отказа не устанавливалась. Последующий
[CI43363880768](https://github.com/Elefesys/ai-service-manager/actions/runs/43363880768)
на a8067f1, attempt1: **10/12 SUCCESS**; catalog/readiness, native-context,
foundation/durable и все connect5 lanes PASS. Pin repair завершён, повторять его
не требуется. Browser56 PASS/2 FAIL и runtime aggregate600s FAIL разобраны C0.

### Ограниченный CI repair — решение C0 принято / 2026-11-13

Решение и разовое делегирование CURRENT — в комментарии C0, связанном выше.
Исходные browser/runtime ZIP повторно скачаны, SHA256 и CRC совпали с C0.
Отдельный чистый worktree a8067f1/tree7c8a442 сохранён для RED reproducer.

**Причины и исправление browser.** Новый helper принимал TEST_CONSUME старого
HUMAN main Turn после UI Resume. Read-only PG подтвердил другую generation;
старый Turn не имеет подходящего Resume receipt, поэтому SQL правильно выдал
NOT_ALLOWED до model call. Оставшийся новый question GROUP затем обработал
обычный happy drain: knowledge GUARDED_TEXT дошёл до чужого FixtureAdapter и
его guard остановил helper до foreign CALL/EFFECT. Это подтверждённый каскад,
не предположение о случайности. После устранения ранней ошибки обнаружен
отдельный текущий TEST_CONSUME: передача его в AI повторяла уже выполненный
GUARDED_TEXT enqueue и давала IDEMPOTENCY_KEY_CONFLICT.

Два knowledge seed события теперь первыми проходят обычный Worker без AI до
двух разных canonical OBSERVED replay receipts при нулевых CALL/EFFECT. Затем
создаются material и остальные fixtures; два события не дублируются, исходные
127 events в `seed_events()` и happy PENDING сохранены. В knowledge loop TEST_CONSUME идёт только
через обычного effect-free observer; GUARDED_TEXT → AI_GENERATE → SEND_AI_TEXT
сохраняют настоящий runtime/DB/Gateway/Worker. Нет catch-NOT_ALLOWED/fallback,
timestamp/status DML или новых grants. Cutoff — available_at cursor, не scope
filter; неожиданные claims по-прежнему отклоняются. Canonical question Inbox
message_id дополнительно сверяется с PREPARE snapshot до FakeAdapter.

**Carrier.** C0 разрешил один aggregate SQL/test budget900s только в runtime
после exact M5.1B admission, включая последующий main-push. Остальные routes и
targeted —600; per-command cap600, build/cleanup bounds и workflow25min прежние.
Один выбранный budget управляет остатком/timeout/stop/summary/final gate.
Все **160 cases =35+22+9+41+25+17+11** остаются в прежних семи модулях.

**Целевые результаты.** Carrier209 и browser-fixture135 unit PASS
(совместно344/61.43s); browser-compose49/0.34s, Ruff/format и frontend
typecheck/build PASS. Исходные
fixture92 tests/expectations сохранены побайтово. Проверены полный виртуальный
проход160 cases/699s, отказ сверх900, прежние600, cleanup failure и missing phase/
case no-PASS; observer до GUARDED_TEXT и после AI даёт один model request/effect.
16 Node checks реальных TS formatter functions PASS: raw stdout/stderr,
exception text/SQL/payload/credentials не печатаются; только closed stage/class/
code, exit/timeout и bounded counters. Прежний ARGS error marker сохранён.

Actual LOCAL PG18.6 из pinned OCI/en_US.utf8, API и pinned Chromium140:
оригинальный knowledge UI test и следующий happy text/control/manual subset
получили RED→GREEN. Knowledge: один actual FakeAdapter request, один canonical
controlled text effect, draft отсутствует, DB replay не вызывает model/send.
После исправления knowledge jobs завершены; happy делает только свой эффект.
Это host helper transport и108 text events, **не Docker/MinIO evidence**:
MinIO в executor остановлен запретом netlink. Исходные image assertions не
изменены; полный58-case browser и actual160 PG в пределах900s остаются OPEN
до штатного CI исправленного кандидата. Его URL и final SHA/tree — в PR #47.
AI default OFF, live/paid/VM0; merge и review — C0. После зелёного CI отдельный
status-only push не нужен.

## 1. Проверяемый результат всего этапа

Владелец может завести услуги и подтверждённые знания, проверить изменения и
опубликовать их. Клиент задаёт вопрос и присылает доступное фото. AI отвечает
по опубликованным сведениям, последовательно уточняет недостающее, подбирает
подходящую настоящую работу и готовит мастеру описание запроса с источниками.
Сложный/неподдерживаемый случай поступает в существующий Action Center.

M5 не считает индивидуальную цену, не определяет подтверждённое время сеанса,
не выставляет предложение/депозит, не бронирует и не принимает оплату. Результат
intake — предварительная информация с происхождением, не M6 ServiceRequest,
Assessment или одобренный заказ. LLM не получает mutation tools.

Первый полезный результат появляется уже после M5.1B: изменённый владельцем FAQ
доходит до ответа тестового AI, draft не виден, старое правило после публикации
не используется. Не ждать окончания всех функций M5 ради этого сценария.

## 2. Объём пилота и границы

Входят:

- компактные Service/Intake/Rule/Communication settings, draft → validation →
  owner preview/publish, immutable active release, rollback;
- curated FAQ/источники и поиск с происхождением; один text embedding profile,
  PostgreSQL exact search, ограниченная загрузка в context/read tools;
- анализ текущих private images, owner upload/review настоящих работ,
  подбор Portfolio и одна разрешённая работа в ответе клиенту;
- DurationCase как подтверждённые примеры для мастера;
- synthetic TattooPack: NEW_TATTOO, COVER_UP и OTHER_COMPLEX с owner handoff;
- минимальный интерфейс для повседневного просмотра, подтверждения и публикации.

Не входят: universal workflow builder/engine, массовый импорт чатов/PDF/сайтов,
OnboardingAgent, автоматическое обучение, генерация эскизов, отдельная vector DB,
новый provider marketplace, scheduling/pricing/payment engines, новый канал,
отдельный ops dashboard, автономный облачный маршрут и production rollout.
Это явно принятые уточнения IMPL-005; исходный baseline сохраняется в истории.

Concierge import допустим через небольшой проверяемый CLI/API и тот же domain
service. Владелец не должен править SQL/JSON вручную для review/publish/отзыва.
Нельзя называть internal-only portfolio готовым клиентским показом изображения.

## 3. Очередь реализации

Порядок по умолчанию последовательный; одна активная выдача с одним ведущим.
Каждый кодовый срез — отдельный небольшой PR, конкретный продуктовый результат
и ограниченная проверка. C0 может разделить большой срез по реально найденной
границе, но не создавать новую сетку задач заранее.

| Порядок / ID | Ведущий; участие | Зависимости | Результат |
|---|---|---|---|
| M5.0 — приёмка плана | C0 | Этот пакет и CI кандидата | IMPL-005 принят; после разрешённой интеграции фиксируются base и единственная выдача M5.1A; application runtime не меняется |
| M5.1A — конфигурация и публикация | C1; C2 | M5.0 | В БД можно безопасно подготовить, проверить и опубликовать небольшой набор услуг/правил/FAQ |
| M5.1B — ответ по опубликованным знаниям | C4; C1/C3, C2 для БД, затем C5 | M5.1A | Опубликованный FAQ читается M4 runtime; owner видит preview и публикует через простой UI |
| M5.2A — ограниченная проверка modalities | C4; C6 только при необходимости | M5.1B; допуск нужен только для paid probe | Выбран конкретный пригодный Vision/embedding route либо описан точный блокер |
| M5.2B — знания и семантический поиск | C4; C1/C2 | M5.1B, embedding контракт M5.2A | Источники/ревизии/index build; keyword + exact vector retrieval с источниками |
| M5.2C — Vision и private portfolio | C4; C1/C2/C5, C6 для storage | M5.2A/B | Фото анализируется, подтверждённые работы загружаются, релевантные примеры видны мастеру |
| M5.2D — показать одну работу клиенту | C3; C4/C5/C8 | M5.2C | Одно разрешённое фото с caption проходит штатные delivery guards и UNKNOWN recovery |
| M5.3A — intake и DurationCase | C1; C4/C5 | M5.2C; клиентский показ использует M5.2D | Предварительное описание заказа, похожие кейсы и owner handoff без выдуманных условий |
| M5.3B — сборка и приёмка | C0/C8; исполнители по findings | Все предыдущие | Сквозные сценарии на одном кандидате; честная граница LOCAL/TEST и live; передача M6 |

Связь со старым планом 09: M5.1A/B уточняют M5.1; M5.2A–D разбивают прежнюю
чрезмерно крупную M5.2; M5.3A/B закрывают M5.3. UI появляется внутри срезов,
а не откладывается целиком на последний день. Роли в таблице — ответственность,
не распоряжение запускать несколько чатов над общими файлами одновременно.

### M5.1A — маленькая опубликованная конфигурация

**Польза:** правила мастера впервые становятся проверяемыми данными приложения.

Сначала C1/C2 фиксируют здесь короткий контракт: объекты и связь с Business,
минимальные поля, команды/ошибки, owner permissions, активная версия и инвалидация.
После этого реализуют bounded domain module, PostgreSQL/RLS и owner API:

- service name/description/active, intake template, понятные ограничения услуги;
- независимый выбор price/duration/deposit modes; неизвестное явно обозначено;
  M5 не исполняет формулу и не создаёт обязательства M6–M8;
- несколько вручную подтверждённых FAQ с источником, стиль общения без prompt editor;
- edit draft с expected version; validate ERROR/WARNING; inspect/preview;
  publish и rollback с idempotency, owner audit и atomic active pointer;
- release содержит только готовые материалы; не смешивает части двух публикаций.

Стартовать с двух маленьких synthetic конфигураций, без данных реального мастера.
Отсутствие цены/времени допустимо для консультации с owner handoff; невалидный
режим/ссылка/противоречивое структурированное правило блокируют publish.
Нет полного Rule DSL, семантического «детектора любых противоречий» и workflow graph.

**Приёмка:** actual PostgreSQL: draft невидим клиентскому чтению, publish атомарен,
повтор не создаёт второй release, конкурентный edit получает конфликт, revoked
owner не публикует, Workspace A не получает B, rollback не возвращает старую
activation version. UI и model calls пока не требуются для DB/API acceptance.

### M5.1B — первый полезный ответ и минимальный UI

**Польза:** AI знает ответы конкретного бизнеса, владелец понимает, что опубликовано.

- Дополнить ContextBuilder/authority/read boundary небольшой service card и
  bounded FAQ projection. Для малого набора начать с structured/keyword selection;
  не ждать embeddings, но и не выдавать этот срез за весь готовый RAG.
- Привязать run и результат к release/build/activation; применять инвалидацию
  IMPL-005 на MODEL/READ/FOLLOWUP/CANDIDATE/COMMIT/SEND, сохраняя все M3/M4 guards.
- Явно версионировать изменённые prompt/schema/DTO; старые сохранённые runs не
  переписывать. `read_context` и text-only DTO нельзя ослабить без новой версии.
- C5 последовательно добавляет простой раздел услуг/FAQ: draft/active, ошибки,
  preview, publish/rollback. Live preview не должен скрыто тратить API бюджет:
  deterministic preview показывает выбранные факты, paid generation — отдельный
  явно обозначенный opt-in. Preview не отправляется клиенту.
- Пустой источник, конфликт или неизвестная политика → уточнение/handoff.
  Источник сохраняется в trace/owner view; внутренние UUID не сыплются в текст клиенту.

**Приёмка:** actual API/PG + fake runtime + реальный browser:
владелец меняет правило, публикует, новый ответ использует его; draft не утёк;
publication перед MODEL/FOLLOWUP блокирует новый вызов со старым контекстом,
между read и send блокирует старый ответ; HUMAN/revocation работают.
Fake E2E не называется live LLM/Telegram проверкой.

### M5.2A — проверить Vision и embeddings до большой реализации

**Польза:** заранее узнать, какой реальный маршрут обслужит изображения и поиск.

Не повторять рынок агрегаторов и все M4 probes. Сначала проверить применимость
текущего Polza маршрута по актуальным capabilities и условиям; подтвердить schema,
image transport/preprocessing, embedding dimension/model, finite costs/deadlines.
Выбрать один Vision и один text embedding профиль; это могут быть разные модели
в принятой ветви. Не строить routing UI или автоматический fallback.

Подготовить короткий synthetic набор: обычная/неоднозначная/неподходящая картинка,
проверка запрета вывода масштаба, один релевантный/нерелевантный текстовый поиск;
негативные transport/schema cases выполнять локально. До paid вызова дать владельцу
конкретный маршрут, число запросов, ограничение суммы и процедуру выключения.
Старый M4 бюджет/ключ/допуск не считать новым разрешением. Реальные клиентские
изображения не использовать. Результат хранится коротким receipt в PR.

Отсутствие live допуска блокирует только real-route acceptance: работа с fake,
данными и контрактами продолжается. Нельзя имитировать embedding случайным
вектором и объявлять качество поиска доказанным. M5.2A закрывается с подтверждённым
capability result; при недоступности route C0 явно меняет задачу, а не ставит PASS.

### M5.2B — знания с источниками и управляемый поиск

**Польза:** отвечать по материалам мастера, даже если вопрос сформулирован иначе.

- Bounded текст/Markdown/структурированный concierge input; без URL crawler,
  PDF/OCR/import archives. Source → подтверждённые sections/items → chunks/index.
- Author/source/version/service/category/effective state; critical rule хранится
  структурированно или ссылается на него, не становится истиной из похожего FAQ.
- Подготовка нового KnowledgeBuild отдельно от active; error/unknown не меняет
  опубликованный набор. Publish включает готовый совместимый build.
- Один embedding profile, exact pgvector + metadata/full-text ranking. Размерность
  и профиль query/index совпадают; смена профиля требует rebuild, не смешения векторов.
- Минимальные READ results: разрешённые источники, фрагменты, причина релевантности,
  empty/conflict. Приватная история клиента не индексируется как общая Knowledge.
- Revocation/delete исключают source и derived chunks/cache из новых reads;
  хранить необходимую безопасную provenance, не бесконечные копии удалённого текста.

**Приёмка:** actual PG retrieval под runtime role, query/index mismatch;
общие опубликованные знания Business доступны его клиентам, личные данные другого
Client и недоступные Business/Workspace изолированы; draft/revoked/expired source,
failed build с сохранением active, injection content и корректный empty result.
Качество оценивается по источникам/полезности ответа, не побуквенно по реплике модели.

### M5.2C — фото и собственные работы

**Польза:** понять присланный референс и показать мастеру подходящие работы.

- Добавить явную image capability, новый разрешённый synthetic data profile и
  bounded Vision operation. Caption не выдаётся за просмотр пикселей.
- Reuse private storage/validation; owner asset upload/review — отдельный узкий
  permit, без фиктивного inbound Telegram message. Никаких public buckets.
- Vision result связан с точной доступной file/content version и профилем:
  subject/style/наблюдаемые детали/неопределённость. Чужой файл, удаление/замена,
  неподдерживаемый формат и лимит дают честный unavailable, не старую картинку.
- Portfolio item: MY_WORK / CLIENT_REFERENCE / INSPIRATION, подтверждение автора,
  разрешение клиентского показа, описание/атрибуты/service и активная версия.
  Vision suggestions подтверждает владелец перед публикацией.
- Поиск client reference → наблюдаемые признаки/описание → text embedding +
  filters → небольшой набор реальных релевантных PortfolioItem. Similarity не
  доказывает eligibility/цену/время; разрешён пустой результат.
- Owner UI: загрузить, посмотреть анализ/источник, исправить, подтвердить/отозвать.
  Analysis/build повторы не делают бесконтрольные paid calls; outcome хранится.

**Приёмка:** actual private S3 + PG/owner API, version invalidation и isolation,
несанкционированный тип/размер/URL, read auth перед выдачей, unknown cost/timeout,
restart, IMAGE unavailable; контроль, что reference не стал MY_WORK. Для смыслового
Vision PASS нужен отдельный разрешённый real API receipt, не только fake assertions.

### M5.2D — одна работа в ответе клиенту

**Польза:** клиент видит реальный пример, а не только сообщение «я нашёл похожее».

В текущем коде нет `sendPhoto`; не предполагать его готовым. C3 проектирует
небольшой typed portfolio selection + server-validated send intent. Модель
предлагает только выданный в текущем read PortfolioItem, не storage key/URL.
Проверить Telegram business capability для выбранного действия; сохранить права,
лимиты caption/media, текущую конфигурацию и разрешение показа перед send.

Один ответ — одно фото с caption либо обычный text reply; без отдельного text +
photo двойного эффекта, albums и новой очереди. Повтор и restart используют receipt;
возможный effect с потерянным ответом остаётся UNKNOWN/no-resend. Владелец видит
состояние в текущем Inbox. Отзыв работы до send блокирует отправку; уже начатая
отправка не объявляется отозванной. Новый content type должен проходить старые
control/rights/native/claim gates, а не обходить их через ручной send.

**Приёмка:** actual PG + controlled wire counter, stop/restart/UNKNOWN,
takeover/config change/withdrawal и cross-client isolation. Synthetic picture в
TEST явно обозначена тестовой, не «реальной работой мастера». Live Telegram smoke
только после отдельного допуска и закрытия относящегося к нему receiver ограничения.
Если C0/владелец отложит этот срез, фиксируется конкретный неполный UX M5.

### M5.3A — описание запроса мастеру и примеры длительности

**Польза:** мастер получает собранную информацию и примеры вместо чтения всей переписки.

- Tattoo template: идея, расположение, примерный размер со слов клиента, стиль,
  доступные референсы. Спрашивать последовательно только недостающее, принимать
  исправление клиентом; нет обязательной длинной анкеты для любого сообщения.
- Предварительная intake projection: значение + source message/file version +
  observed/client-stated/owner-confirmed/unknown. Вывести из текущих разрешённых
  данных и хранить/пересобирать с provenance; это не второе authoritative CRM ядро.
  Не создавать преждевременно M6 ServiceRequest/Assessment/Order таблицы.
- Ограниченные deterministic transitions template: уточнить, получить owner
  решение, завершить сбор. COVER_UP/OTHER_COMPLEX и отсутствие правила → existing
  escalation; в Action Center компактный summary со ссылками и открытым вопросом.
  Выполнение owner request не обещается до принятого результата runtime.
- DurationCase: разрешённая работа/описание, реальные размеры при наличии,
  исполнитель, working/occupied time, подготовка/перерывы, сессии и объяснение.
  Unknown не заполняется AI. Найти похожие случаи и показать мастеру различия;
  не выводить часы из размера картинки и не назначать клиенту длительность.
- Небольшая owner форма/concierge import и просмотр примеров; без fine-tuning,
  duration predictor, automatic rule publication и медицинских интервалов.

**Приёмка:** два разных бизнеса одним кодом; исправленный/удалённый источник
обновляет projection; known facts не спрашиваются заново; сложный запрос получает
одну актуальную escalation; подтверждённое время прошлого кейса не становится
обещанием новому клиенту. HUMAN и последующий Resume не теряют границы M3.

### M5.3B — завершение этапа

C8 проверяет весь интегрируемый scope по матрице ниже, уделяя внимание source
authority, private media и конкуренции publish/send. Авторские тесты остаются
обязанностью исполнителя. Targeted review одного fix не выдаётся за review всего M5.

Один финальный candidate → штатный полный CI → C0 acceptance → отдельный merge
допуск → фактический push/main CI. Не менять существующие gates ради зелёного
результата. Если CI сам запускается для docs PR, учитывать его один раз, без
ручного rerun неизменённых исходников. После приёмки — одна запись в реестре,
обновление CURRENT и передача M6 с release/intake/source contracts и ограничениями.

Отдельно перечислить, какие реальные Vision/embedding/Telegram проверки выполнены,
какие требуют владельца. LOCAL/TEST VERIFIED не равен готовности реального бизнеса.
При непроверенном реальном Vision route честный статус соответствующего среза —
REVIEW/BLOCKED по точной причине, а не автоматическое VERIFIED всего функционала.

## 4. Одна приёмочная матрица

| ID | Сценарий / обязательный результат | Доказательство |
|---|---|---|
| K01 | Draft изолирован; publish/rollback атомарны; edit/publish replay и конфликт корректны | PG + owner API |
| K02 | Один вопрос даёт разные подтверждённые ответы у разных бизнесов; нет if workspace_id | Runtime + fixtures |
| K03 | Missing/conflicting knowledge → уточнение/handoff; trace содержит реальные sources | Runtime/eval |
| K04 | Publish/revoke во время run не выпускает старый ещё не отправленный ответ; UNKNOWN не повторяется | PG race + wire/restart |
| K05 | Общие опубликованные знания/разрешённое портфолио Business доступны его клиентам; личные данные другого Client и недоступные Business/Workspace изолированы в search/context/media | PG runtime-role + API |
| K06 | Compatible embedding build; failed rebuild не ломает active; semantic relevance и empty result | PG + разрешённый real embedding receipt |
| K07 | Vision читает реальные доступные pixels; не угадывает scale/time/price; injection не управляет tools | Media tests + real synthetic Vision probe |
| K08 | MY_WORK подтверждён; reference не становится портфолио; withdrawn asset не показывается | PG/S3 + UI |
| K09 | Один разрешённый portfolio photo reply, guards/UNKNOWN/restart/no-resend; состояние видно | Controlled wire + browser; live отдельно |
| K10 | Intake исправляем/прослеживаем; COVER_UP handoff; case duration не обещается клиенту | Runtime/eval + browser |
| K11 | Владелец review/publish/revoke без SQL; draft ошибки понятны | Real browser |
| K12 | HUMAN/Resume/currentness и старые source gates сохранены; all features одного accepted candidate | Штатный CI + scoped C8/C0 |

Исполнитель связывает соответствующие строки с конкретными assertions и результатом
в PR; не создаёт ещё несколько независимых matrices/реестров. Число тестов не gate.
Fixtures: два изолированных Workspace и минимум два Client внутри одного; варианты
A fixed/fixed/fixed deposit, B configured formula/rule/percent, C owner/owner/NONE,
D mixed/full payment. В M5 проверяются настройки и честные ограничения, не работа
ещё отсутствующего pricing/payment engine. Не нужен полный декартов перебор.

## 5. Правила выдачи и инженерные ограничения

В каждом задании C0 указывает ID, продуктовый результат, полный base SHA, branch,
одного ведущего, exact write-set, dependency, критерии и что оставлено за границей.
Не выдавать весь этот документ C1/C4 как одно задание «реализовать M5».

Первая **M5.1A**: базовый домен `backend/src/asm/configuration/` (новый), узкое
подключение owner API/auth, новая назначенная C0/C2 migration, относящиеся DTO,
tests/fixtures. Это предлагаемая область, не wildcard разрешение всего backend.
Перед кодом C0 фиксирует точные существующие entrypoint/permission/test paths
и ограниченный CI source admission для назначенной ветки/write-set: допуск PR #45
не разрешает будущие изменения приложения или миграций.
`0018` может быть назначена только если head всё ещё `0017`; будущие номера не
резервировать цепочкой. C5 получает следующий принятый API SHA последовательно.

Не менять applied0001–0017, роли/гранты всех старых модулей, исторические schema
checks, native context или `.github/workflows` ради удобства новой функции.
Если additive migration требует current catalog/profile compatibility, перечислить
конкретные затронутые guards/fixtures и доказать изменение. Проблема тестового
harness/locale отделяется от production SQL. Не подгонять expected к неверному
поведению и не разносить огромную test refactor работу по продуктовым задачам.

Сначала targeted unit/actualPG по риску, затем один штатный full CI кандидата.
Повтор запуска — только новое исправление/конкретная причина. Не добавлять новые
универсальные test runners, classifiers, trace registries, очереди или fallback
ради гипотетических будущих случаев. При тупике остановить расширение задачи,
указать cause/evidence/наименьший fix либо предложить явный DEFERRED.

Возврат исполнителя: PR, head, изменённые операции/миграция, относящиеся K-строки,
команды и реальные результаты, ограничения, один следующий шаг. Исторические
артефакты не перепечатывать в CURRENT. Один актуальный статус и краткая выдача;
логи/большие подробности остаются в PR/CI. Никаких auto-merge/VM/paid действий по
факту назначения задачи разработки.

## 6. Действия владельца

Сейчас требуется только отдельное разрешение владельца на merge PR #45, когда
C0 подтвердит готовность и зелёный CI кандидата. Прайс, архив чатов и портфолио
реального мастера не нужны. C0 выдаёт первый срез только после интеграции.

Позже, по конкретной готовой процедуре:

1. Отдельно разрешить ограниченный synthetic Vision/embedding probe и сумму;
   при необходимости внести ключ локально, не в чат/Git. Не покупать новый сервис
   до результата capability preflight.
2. При необходимости выполнить owner VM/Telegram smoke после текущей диагностики
   receiver; старые инструкции не переиспользуются вслепую. Это не блокирует coding.
3. До реального бизнеса подтвердить правила, права на материалы и допустимый
   маршрут обработки данных. Synthetic fixtures не становятся его настройками.
4. Слияние PR — после C0 review/CI и конкретного допуска, как в предыдущих этапах.

## 7. Передача M6

M6 получает принятые service/intake/rule/release identifiers, source provenance,
private Portfolio/DurationCase access и предварительные факты разговора.
Он создаёт ServiceRequest/Assessment, утверждение цены/времени, QuoteAcceptance,
Order/Session и owner decision, не заменяя их результатом Vision или похожим кейсом.
Все OPEN live ограничения переносятся отдельным коротким списком.
