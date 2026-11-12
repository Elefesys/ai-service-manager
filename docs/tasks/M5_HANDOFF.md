# M5 — настройки бизнеса, знания, Vision и портфолио

Дата: 2026-11-12. Ведущий: C0. Статус исполнения — только в
[TASK_REGISTER](../TASK_REGISTER.md). Решение по объёму:
[IMPL-005](../decisions/IMPL-005-m5-pilot-knowledge.md) — ACCEPTED / LOCKED C0.

## CURRENT — M5.1A → C1 с участием C2 / 2026-11-12

Единственная активная выдача: **C1-M5.1A-CONFIGURATION-R1**. Ведущий — C1;
C2 согласует схему, миграцию, RLS/права и PostgreSQL evidence в том же PR.
M5.1B и все последующие срезы не выданы.

- Repository: `Elefesys/ai-service-manager`; integration target: `main`.
- Accepted implementation base: `49d3e25968507ac41037f369fce5bd7080475a8f`.
- Base tree: `699bd90777771c5d22d37029336c3e0f8909fb5c`.
- Подготовленная ветка: `c1/m5-1a-configuration-r1`; начать с её C0 docs-only
  handoff commit поверх указанного base, сохранив его. Один checkout/PR,
  последовательные изменения общих файлов; без параллельного редактирования C1/C2.
- Зависимости: PR #45 интегрирован; IMPL-005 ACCEPTED / LOCKED;
  [post-merge CI43192222535](https://github.com/Elefesys/ai-service-manager/actions/runs/43192222535)
  на момент выдачи ещё IN_PROGRESS. Дерево main совпадает с кандидатом, прошедшим
  [CI43180741615](https://github.com/Elefesys/ai-service-manager/actions/runs/43180741615).
  C0 принимает этот base по совпадающему проверенному tree; runtime job
  прошёл также на merge SHA. Это допуск к synthetic разработке, не заявление
  о завершении всего post-merge CI. Receipt M4
  `98136c33a997f0ce266dee2ad517ea23e312408e` сохранён в ancestry.

### Результат и короткий контракт

Через owner API можно подготовить небольшой набор услуг, правил и подтверждённых
FAQ, увидеть ошибки/предупреждения и preview, атомарно опубликовать его либо
активировать допустимый прежний набор. Для будущего AI чтения доступна только
ограниченная active projection с release/activation version; draft туда не попадает.
UI и использование знаний в ответе AI принадлежат M5.1B.

До SQL C1 с C2 записывают в этот CURRENT короткий согласованный контракт:
объекты/Business ownership, поля и пределы размера, API команды/ошибки,
expected-version/idempotency semantics, owner authority, release/activation и RLS.
Физическая схема и точные DTO пока OPEN; выбрать минимальное решение для этих
операций. Не создавать таблицу на каждый термин baseline и отдельный contract tome.

#### Согласованный контракт C1/C2 — M5.1A v1 / 2026-11-12

C2 проверил clean handoff `6c9023dbf29e1e8e100084aee85a12c132ba2ab3`:
единственный head `0017`, revision `0018` / predecessor `0017` подтверждены до SQL.

- Три private `platform.business_configuration_{state,releases,receipts}`:
  одна draft/active state на `(Workspace,Business)`, immutable release и immutable
  command receipt, одновременно configuration domain audit (actor, correlation,
  operation, Business/release/activation/time; без текста). Compound FK сохраняют
  тот же Workspace/Business. Generic AuditEvent/его API не расширяются.
- Bundle v1: `schema_version=1`, `communication_style=NEUTRAL|WARM|CONCISE`,
  services (до8), structured rules (до12), owner-confirmed FAQ (до12).
  Service: slug id, name≤100, description≤500, active, до6 intake fields
  `(id,label≤100,required)`; независимые price/duration/deposit policy objects.
  Price: FIXED/CONFIGURED_FORMULA/OWNER_QUOTE, nullable amount_minor/formula_note;
  duration: FIXED/CONFIGURED_RULE/OWNER_DEFINED, nullable minutes/rule_note;
  deposit: NONE/FIXED_DEPOSIT/PERCENT_DEPOSIT/FULL_PREPAYMENT, nullable amount/percent.
  Все nullable fields явные; RUB minor units — настройки, не расчёт/Quote/обязательство.
- Rule: id, nullable service_id, MIN_AGE с integer1…120 либо OWNER_HANDOFF с bool.
  FAQ: id, nullable service_id, question≤200, answer≤500, source≤120, confirmed,
  до6 rule_ids. Id — ASCII slug1…40; notes≤160. Неизвестное значение остаётся NULL.
  Неверный mode/ref, duplicate id, конфликт правил и неподтверждённый FAQ — ERROR;
  неизвестные цена/время/депозит, неисполняемые formula/rule notes — WARNING с
  owner handoff. FAQ explanatory; структурированные rules выше текста.
- Shape/Unicode/types/limits проверяются в Python и БД; publish повторяет
  deterministic SQL validation и не доверяет переданному ready flag. Normalized
  jsonb bundle≤4096 UTF-8 bytes, существующий raw HTTP body cap4096 сохраняется
  отдельно и включает весь envelope/escaping; не каждый максимальный field
  помещается одновременно. Free-form prompt/code/Client IDs/private files/PII
  не являются поддерживаемым содержимым общей бизнес-конфигурации.
- API prefix `/api/v1/workspaces/{workspace_id}/businesses/{business_id}/configuration`:
  GET/PUT `/draft`, GET `/preview` (validation + bounded owner preview),
  POST `/publish`, POST `/rollback`, GET `/active`; query и If-Match запрещены.
  Все owner API используют существующие session/CSRF/AuthService.workspace и
  отдельную live OWNER policy. В БД OWNER/auth scope проверяется до replay и
  после waits; membership/account/Business locks сериализуют отзыв прав и publish.
- Mutation требует один Idempotency-Key (existing ASCII1…128). EDIT body:
  `{expected_draft_version,bundle}`; PUBLISH:
  `{expected_draft_version,expected_activation_version}`; ROLLBACK:
  `{expected_activation_version,release_id}`. Counters — canonical bigint decimal
  strings. Первый EDIT expected0 создаёт draft1; каждый новый EDIT +1. Publish и
  rollback +1 activation, draft не меняют. Stale CAS→409 STALE_STATE;
  тот же key/actor/op/body→exact saved REPLAY без effect; другой payload→409
  IDEMPOTENCY_KEY_CONFLICT. Live revoked/non-owner не получает даже replay.
- SQL owner read/command, bounded active read и private validator — narrow
  capabilities; runtime direct table SELECT/DML запрещён, FORCE RLS/migrator owner,
  PUBLIC revoke/pinned search_path. Active projection v1 содержит только весь
  immutable ready bundle, release/activation/source draft version и provenance.
  До первого publish release/bundle NULL; draft не попадает в active read.
  Чтение общих бизнесовых знаний не требует чужих Client данных; M5.1B привяжет
  этот release/activation к существующему trusted context и send admission.
- Publish ERROR не меняет active. Rollback revalidates ready release и запрещает
  восстановление удалённых/изменённых FAQ и free text относительно current active;
  откат policy values/style с сохранёнными текстами допустим. Это консервативный
  ROLLBACK_NOT_ALLOWED, не попытка распознавать PII или вернуть удалённые данные.
  Полный release/receipt и active pointer commit атомарно; replay старой команды
  никогда не переключает pointer обратно.
- Closed errors: ACCESS_DENIED403, NOT_FOUND404, INVALID_INPUT422,
  STALE_STATE/IDEMPOTENCY_KEY_CONFLICT/VALIDATION_FAILED/VERSION_EXHAUSTED/
  ROLLBACK_NOT_ALLOWED409, UNAVAILABLE503; retained auth/CSRF/413/429 unchanged.
  SQL P2701 преобразуется только в этот allowlist, произвольный SQL текст скрыт.
- Current-schema transitions ограничены actual catalog/readiness/provisioning,
  двумя current SQL dispatchers (native policy и AI provider session), current
  runner/egress/browser fixtures и assertions текущего head. Исторические профили
  и applied0001–0017 не меняются. Точное использованное подмножество paths и
  новые измеренные profiles возвращаются с final source/evidence.

Использованное current-schema подмножество (исторические0013–0017 сохранены):

```text
backend/src/asm/telegram/provisioning.py
scripts/m2_4_browser_fixture.py
scripts/m4_runtime_db.py
scripts/native_context_db_catalog.py
scripts/prepare_telegram_egress.py
scripts/test_telegram_egress.sh
tests/generic_pg_schema.py
tests/test_foundation.py
tests/test_m2_3_db_postgres.py
tests/test_m2_3_schema_postgres.py
tests/test_m2_3_setup.py
tests/test_m2_4_browser_fixture.py
tests/test_m3_1_guards_migrations.py
tests/test_m3_1_native_context_postgres.py
tests/test_m3_1_native_context_runtime_postgres.py
tests/test_m3_2_escalations_migrations.py
tests/test_m4_delivery.py
tests/test_m4_delivery_postgres.py
tests/test_m4_polza_runtime_postgres.py
tests/test_m4_reply_rights.py
tests/test_m4_reply_rights_postgres.py
tests/test_m4_runtime_db_runner.py
tests/test_m4_runtime_migrations.py
tests/test_m4_schema_postgres.py
tests/test_native_context_db_runner.py
tests/test_telegram_egress.py
tests/test_telegram_egress_postgres.py
tests/test_tenancy_postgres.py
```

Причины: provisioning/browser и их fixtures требуют current18; egress читает
все52 таблицы новым fingerprint; catalog/readiness сверяют202 functions/732 columns;
PG fixtures восстанавливают current18 после исторических фаз, tenancy проверяет
старые и новые права. M4 runner сохраняет старые source routes и добавляет только
точную M5.1A branch/base/tree/write-set в outer/export/inner admission.

### Возврат C1/C2 — подготовленный source, ожидание точечного согласования

Реализованы шесть owner API и bundle v1, additive0018, private receipt-audit,
validation/preview/publish/rollback и bounded active projection. Draft и active
разделены; UNKNOWN/holds, native/control/delivery и AI loop не менялись.
202 functions /52 tables /732 columns измерены на owned native PG18.0,
vector0.8.6/btree_gist1.8; accepted0017 profile предварительно совпал полностью.
Это local synthetic evidence, не pinned image/full CI или live verification.

Локальные unit/source, actual API/PG и legacy tenancy checks выполнены; полные
команды, результаты, initial setup failures и один readiness timeout сохраняются
в возврате C1. Ruff/mypy, OpenAPI check и все document-root JSON refs проходят.
Финальные source identities и подробный return — в
[C1/C0 coordination](https://github.com/Elefesys/ai-service-manager/pull/45#issuecomment-6821719546).

До PR/штатного CI нужен только точечный C0 write-set допуск для
`tests/test_auth_contract.py`: явный список шести маршрутов +existing equality,
+9/-0, frozen auth.v1 и все прежние assertions без изменений. Тест воспроизведён
RED25→31; source OpenAPI уже byte-equal generated snapshot. Этот путь пока не
изменён. Scope не расширен самостоятельно; M5.1B/UI/LLM tools не выданы.



C0 резервирует только `0018_business_configuration.py`: revision `0018`,
down_revision `0017`. **C2 до SQL подтверждает**, что актуальный migration head
по-прежнему `0017`, и согласует схему/профиль. При изменении head вернуть вопрос
C0; не переименовывать применённые миграции. `0001`–`0017` побайтово сохраняются.

Реализовать согласованный объём M5.1A из §3 ниже:

- service name/description/active, простой intake template, структурированные
  ограничения; независимые price/duration/deposit policies по ADR-262/263/265;
  явное неизвестное, без расчёта цены/времени, Quote, записи или платежа;
- несколько owner-confirmed FAQ с происхождением и выбранный стиль общения;
  два маленьких synthetic набора, без реальных клиентских данных и prompt editor;
- draft edit с expected version; deterministic ERROR/WARNING validation и preview;
  неизвестная цена/длительность допускают консультацию с owner handoff, а
  невалидный режим, ссылка или конфликт структурированных правил блокируют publish;
- publish/rollback с устойчивым replay, immutable release, audit и атомарным
  переключением ready bundle; rollback увеличивает activation version и не
  восстанавливает удалённые персональные данные;
- bounded active read по доверенному Workspace/Business. Общий опубликованный
  FAQ бизнеса доступен его клиентам; приватные записи клиентов в bundle не входят.
  Зафиксировать контракт версии для M5.1B, не менять agent loop/LLM tools сейчас.

### Точки интеграции и разрешённые paths

Использовать существующие `AuthService.workspace`, session/CSRF и
`/api/v1/workspaces/...` boundary. `tenancy:write` есть и у ADMIN: для публикации
и отката нужна отдельная актуальная OWNER-проверка, включая replay. Не расширять
замороженные auth/tenancy permissions ради этого. Связь ресурса с Business и
Workspace, runtime role, транзакция и права должны проверяться в БД; никакого
внешнего HTTP под DB locks. C2 проверяет блокировку конкурентного изменения
owner authority и публикации, а не только предварительный Python role check.

Новый модуль: только перечисленные файлы (создавать лишь необходимые):

```text
backend/src/asm/configuration/__init__.py
backend/src/asm/configuration/errors.py
backend/src/asm/configuration/models.py
backend/src/asm/configuration/validation.py
backend/src/asm/configuration/permissions.py
backend/src/asm/configuration/repository.py
backend/src/asm/configuration/service.py
backend/src/asm/configuration/http.py
migrations/versions/0018_business_configuration.py
tests/test_m5_configuration.py
tests/test_m5_configuration_migrations.py
tests/test_m5_configuration_postgres.py
tests/test_m5_configuration_api_postgres.py
tests/m5_configuration_fixtures.py
```

Общие файлы: `backend/src/asm/foundation.py` — wiring и current readiness;
`backend/src/asm/tenancy/database.py` — ограниченные configuration operations;
`contracts/openapi.json` — штатно сгенерированный API snapshot;
`docs/tasks/M5_HANDOFF.md` — короткий контракт C1/C2 и итоговый возврат.

Ниже разрешён **только** необходимый переход current-schema consumers на `0018`
и его проверки. C1/C2 указывают использованное подмножество и причину в контракте;
это не поручение менять каждый файл и не разрешение переписать прошлые проверки:

```text
backend/src/asm/telegram/provisioning.py
scripts/native_context_db_catalog.py
scripts/m4_runtime_db.py
scripts/m2_4_browser_fixture.py
scripts/prepare_telegram_egress.py
scripts/test_telegram_egress.sh
tests/test_foundation.py
tests/generic_pg_schema.py
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
tests/test_m2_4_browser_fixture.py
tests/test_telegram_egress.py
tests/test_telegram_egress_postgres.py
tests/test_m2_3_db_postgres.py
tests/test_m2_3_schema_postgres.py
tests/test_m3_1_guards_migrations.py
tests/test_m3_2_escalations_migrations.py
tests/test_m3_1_native_context_postgres.py
tests/test_m3_1_native_context_runtime_postgres.py
```

Новый exact profile/hashes/counts выводятся из фактической DDL и сверяются с
установленной PostgreSQL схемой. Исторические профили/тесты прежних ревизий
сохраняются; массовая замена `0017` на `0018` недопустима. Нужные замены текущих
SQL dispatchers выполняются additive миграцией, без ослабления ACL/readiness.

В `scripts/m4_runtime_db.py` и его tests разрешён также ограниченный admission
этой конкретной ветки, полного base/tree и этого write-set, включая пять C0
стартовых документов (`AGENTS.md`, `README.md`, `docs/TASK_REGISTER.md`,
`docs/decisions/IMPL-005-m5-pilot-knowledge.md`, `docs/tasks/M5_HANDOFF.md`).
Обновить согласованно outer admission, source export и inner source verification;
сохранить same-repository/event/parent/tree/clean-source guards и корректный
последующий push/main. Старый M5 planning allowance не допускает этот код.
До открытия implementation PR проверить положительный admission и отказы на
чужой branch/base/tree/path; fixtures должны работать в штатном checks image.

Другие paths требуют конкретного согласования C0, не нового разрешения владельца
на каждую рутинную правку. C1 не редактирует CURRENT реестра или канонические ADR.
Не менять `.github/workflows`, зависимости/locks, frozen auth/tenancy contracts,
frontend, AI/messaging/delivery guards, старые migration files и M4 receipts.
Не создавать фиктивные Telegram conversations/messages для этой конфигурации.

### Критерии готовности и возврат

Сначала целевые проверки по риску, затем один штатный полный CI готового
кандидата. Новые actual-PG тесты идут в существующий generic integration lane;
не добавлять новый workflow или отдельный повтор M4. Обязательное evidence:

1. Два synthetic набора проходят edit → validate/preview → publish → active read;
   draft и неготовый набор не видны active projection; частичной публикации нет.
2. Actual API + PostgreSQL под runtime role: expected-version conflict, атомарный
   publish при конкуренции, idempotent replay без второго release/audit effect,
   конфликт повторного ключа с другим payload; прежняя active version сохранена
   при ERROR. Rollback даёт новую монотонную activation version.
3. Session/CSRF, ADMIN/non-owner/revoked owner, cross-Workspace и неверный
   Business/resource scope запрещены, включая replay. Проверены RLS/ACL и
   неизменяемость release, а не только mock репозитория или HTTP status.
4. Unknown price/duration не превращаются в нули/обещания; невалидные modes/refs
   блокируются. FAQ со ссылкой на правила не переопределяет структурированную истину.
5. Upgrade с чистой БД и с `0017`, повторный upgrade и штатный migration cycle;
   прежние данные и права сохранены, exact current profile проходит, историческая
   схема отвергается current app и проверяется своим сохранённым checker.
6. Ruff/mypy/OpenAPI и штатный полный CI одного final SHA; clean-source evidence
   и фактическое включение новых PG tests. Падения implementation и test setup
   разделять; expected не менять только ради PASS и неизменённые прогоны не повторять.

Вернуть один небольшой PR в `main`: final head/tree, краткий согласованный
контракт C1/C2, migration/изменённые API, проверяемый сценарий и команды/результат,
CI URL, оставшиеся ограничения/OPEN. Подробные логи — в PR/CI, здесь только итог.
C0 проводит review и интеграцию; авторы не объявляют задачу INTEGRATED/VERIFIED.

Только synthetic LOCAL/TEST. VM/paid/Vision/embedding/live/реальные данные не
разрешены этой выдачей. Старые receiver ACK/fence и общий live HUMAN/Resume
остаются отдельными ограничениями; UNKNOWN/holds, OWNER reconciliation и
observation barrier сохраняются. Прежний receiver вслепую не запускать.


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
| M5.1B — ответ по опубликованным знаниям | C4; C1/C3, затем C5 | M5.1A | Опубликованный FAQ читается M4 runtime; owner видит preview и публикует через простой UI |
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
