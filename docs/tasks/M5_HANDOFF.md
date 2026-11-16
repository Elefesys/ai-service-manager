# M5 — настройки бизнеса, знания, Vision и портфолио

Статус исполнения — в [TASK_REGISTER](../TASK_REGISTER.md).
Решение по объёму — [IMPL-005](../decisions/IMPL-005-m5-pilot-knowledge.md),
ACCEPTED / LOCKED C0.

## CURRENT — C1-M5.3A-INTAKE-DURATION-R1 / IN_PROGRESS / 2026-11-16

**Единственная активная задача — M5.3A, ведущий C1.** C2 помогает с БД,
C4 с extraction/runtime, C5 с UI; работа последовательно в одной ветке.
C3 — консультация только по существующим delivery/control контрактам.
C6 HOLD. M5.3B и M6 пока не выданы.

### Принятый main и завершение M5.2D

- PR #52 слит владельцем. **M5.2D — INTEGRATED / VERIFIED в synthetic LOCAL/TEST.**
- **Exact application base: `220606193208a1ef082732e4dfcdf1f2ffbea857`.**
  Tree `d15f9a75346ab881449010745cbe0216081b78cf` совпадает с принятым кандидатом
  `3cb99509796262112a563e5665d6cabb44fbfc99` и tested PR merge
  `f6e09f313ca3bf58e71460d20acaefde703568d0`.
  Actual merge parents: `8d98593bc739666176968c5d76b9c01a2a711686` +
  `3cb99509796262112a563e5665d6cabb44fbfc99`.
- [C0 review M5.2D](https://github.com/Elefesys/ai-service-manager/blob/afb7b1b6f126446c8ac7162bd7f42a8603ff624f/docs/tasks/M5_HANDOFF.md#L13)
  и [PR CI43879466102](https://github.com/Elefesys/ai-service-manager/actions/runs/43879466102)
  сохранены. Этот отдельный docs receipt не является application base.
- [Post-merge CI43894664260](https://github.com/Elefesys/ai-service-manager/actions/runs/43894664260):
  push/main, attempt 1, **12/12 SUCCESS**. C0 проверил Git identity/parents/tree,
  ZIP digest/size/CRC core и runtime, совпадение всех 449 source paths,
  Git blob bytes/executable bits и обоих SHA256 manifests с actual main.
  Core: 4680 unit + 161 subtests, 1041/1041 generic PG, все 14 backend и
  10 host phases PASS; primary/cleanup 0. Runtime: 160/160, 8/8 cleanup PASS,
  source admission PASS, полный evidence manifest проверен; SQL 624.736s/900s.
  Остальные 10 jobs SUCCESS по Actions API; их artifacts заново не аудировались.
  Неизменённый CI C0 не повторял.
- Core artifact14246322296 ZIP SHA256
  `1eeb7e908e6c91ff676d6b27b2b6d50094ca6e2ffb09d012f6492c365236ca53`;
  runtime artifact14239576641 ZIP SHA256
  `a9001fb9a6ef7419b46de707855fc04d398c9fd1d9530bf3f7f2144dae764fb7`.
  Общий source archive SHA256
  `a3e80ba2acafb3898ae90f329a65983d72927e2bf4b5e522c86b7f7b4c8848ab`.
  Старый CI43866508414 остаётся FAILURE, не переписан в PASS.
- M5.1A–M5.2C сохраняют приёмку. Functional capability M5.2A остаётся
  ASSISTED_SYNTHETIC. Реальная доставка фото/общий live VERIFIED не заявлены.

### Результат для пользователя и порядок старта

Клиент сообщает идею, место, примерный размер, стиль и доступные референсы;
AI спрашивает только недостающее и принимает исправления. Мастер видит
предварительную сводку с источниками, неизвестным/конфликтами и похожими
подтверждёнными примерами прошлых работ. Сложный случай даёт один актуальный
вопрос в существующем Action Center. Часы прошлых кейсов видит только мастер.
Это согласованный завершающий функциональный срез M5; без него нет собранного
описания запроса для передачи M6. Цена, подтверждённая длительность и запись
остаются за пределами этого задания.

- Repository: `Elefesys/ai-service-manager`.
- Branch: `c1/m5-3a-intake-duration-r1`; один небольшой Draft PR в `main`.
- Начать с docs-only assignment C0 в этой ветке: его sole parent — exact base
  выше, diff — только AGENTS, README, TASK_REGISTER, IMPL-005, M5_HANDOFF.
  Взять полный assignment SHA/tree из закреплённой ссылки/Git, сохранить
  ancestry; не продолжать старые ветки C1/C3/C4 и не переносить их scope proofs.
- Прочитать этот CURRENT, IMPL-005, Spec §§5.5–5.10, 11.11, 23.3 и
  ADR-023–026/030–034/065–068/265–267. IMPL-004 сохраняет operational границы.
- До SQL записать здесь короткий контракт: projection/source refs,
  template binding, candidate/result DTO, owner commands/errors, DurationCase
  shape/access, escalation linkage, invalidation и точные новые таблицы/FK.
  C1/C2 подтверждают слот **0023/down_revision 0022** по actual checkout.
  Это выполнение уже выданной задачи, не обязательный дополнительный approval
  после каждого решения в пределах ниже. Противоречие архитектуре или новый
  необходимый path вернуть C0 с конкретным меньшим вариантом.
- После контракта/первого связного результата разрешён один checkpoint push
  в эту же ветку до долгих проверок, без PR/ручного CI; явно UNVERIFIED.
  После готовности реализации и source admission — один Draft PR и штатный CI.

### Контракт и границы реализации

1. **Предварительная projection, не новое CRM-ядро.** Связать с проверенными
   Workspace/Business/Client/Conversation, service id, immutable active release,
   template revision и context/control generation. Поля: value либо unknown,
   статус client-stated / observed / owner-confirmed / unknown, source message
   id + material/content version и при наличии file/analysis exact version.
   Признаки Vision остаются наблюдениями; source id, provenance status и
   currentness проверяет сервер, model confidence не даёт authority.
   Неподтверждённый вывод не помечать client-stated/owner-confirmed.
   Доступная projection должна восстанавливаться из разрешённых источников;
   durable cache допустим с версией, bounded size и fail-closed invalidation.
   Не создавать ServiceRequest/Assessment/Order/WorkflowInstance/StepInstance.

2. **Один bounded template и последовательное уточнение.** Использовать
   опубликованные service/intake field identifiers, а не бизнесовые UUID или
   эвристику по произвольному label. Tattoo template v1: NEW_TATTOO;
   COVER_UP/OTHER_COMPLEX — owner handoff. Идея, расположение, приблизительный
   размер со слов клиента, стиль и референсы где доступны. Existing v1 bundle
   уже содержит максимум 6 intake fields: сначала переиспользовать его;
   owner-selected template можно применить к draft и явно publish через текущий
   UI. Не менять уже опубликованный bundle при обновлении кода/template.
   Если необходим новый metadata contract, только новая закрытая версия с
   явной совместимостью v1, без silent reinterpretation старых release.
   Known facts не спрашивать заново; optional/unavailable reference не делать
   обязательным фото. FAQ-only сообщение не запускать в длинную анкету.
   Неоднозначная услуга/смена темы/несколько запросов требуют уточнения, а не
   смешивания фактов разных запросов в одну авторитетную запись.

3. **Исправления, удаление и freshness.** Явное новое значение заменяет старое
   с provenance; неявный конфликт остаётся вопросом. Edit/delete/redaction
   message, replace/delete media, revoke analysis/material, publish/rollback,
   смена Client/Business/control и native observation инвалидируют зависимые
   данные до следующего чтения/модельного вызова/сохранения/отправки.
   Старый cache/summary не восстанавливает удалённый факт. Изображение без
   масштаба не доказывает сантиметры, возраст, здоровье или длительность.
   Owner confirmation — отдельное аутентифицированное version-checked действие
   над конкретным полем/источником; свободный ответ Action Center не становится
   автоматическим подтверждением всех полей и условий заказа.

4. **LLM предлагает, сервер применяет.** Добавить узкую synthetic ветвь
   `conversation_v7` / `conversation_result_v3` для candidate facts и одного
   результата разговора. При необходимости — новую closed context/read DTO.
   Старые prompts v1–v6, schemas v1/v2 и их parsers сохраняют прежние shapes;
   нельзя расширять их через optional arbitrary JSON/extra=allow.
   Candidate write выполняется сервером атомарно после schema/source/tenant/
   context/control/native/claim checks; у LLM нет mutation tool.
   Переходы clarify / owner handoff / preliminarily complete определяются
   template и проверенными данными; complete не означает согласованный заказ.
   Один обычный ответ — 1 model call, максимум 2 calls / 1 READ без нового loop.
   Сохранить M5 knowledge/Vision/photo branches и счётчики; фото использует
   существующий M5.2D intent/admission, без обхода или нового send effect.
   Связь с runtime/worker должна быть настоящей, не отдельной demo function.
   Default OFF, FAKE/EVAL_ONLY, finite TEST execution; старые реальные text
   sessions не получают новый contract и права на private data автоматически.

5. **Action Center — узкое расширение текущего механизма.** C0 проверил:
   `EscalationView` и frontend codec сейчас фиксируют CONTROLLED ESCALATION TEST
   / LOCAL_TEST_OWNER_WAIT_V1. Они не готовы принять произвольную intake сводку.
   Разрешена новая закрытая discriminated projection/policy рядом с legacy,
   с summary, проверяемыми source links и одним открытым вопросом; legacy
   literal contract и M3 resolve/cancel/replay сохраняются.
   COVER_UP/OTHER_COMPLEX, неподдерживаемый/рискованный случай и отсутствие
   необходимого правила не получают автоматическое согласие. Неизвестная
   цена/длительность консультации сама по себе не блокирует весь сбор данных.
   Repeated turn/retry не плодит одинаковые pending escalations; изменение
   источника делает прежний вопрос stale и оставляет не более одного актуального.
   Accepted owner command и фактический runtime result различать в UI;
   не обещать исполнение до принятого результата. Во время HUMAN не запускать
   AI и не применять его старые candidates; Resume использует текущие данные,
   OWNER reconciliation/observation barrier и прежние guards M3/M4.

6. **DurationCase — owner-only примеры.** Компактная форма создания/исправления,
   подтверждения и отзыва. В кейсе: разрешённое описание и optional точная
   ссылка на business asset/version, реальные размеры если известны,
   placement/style/detail/fill, исполнитель, actual working/occupied minutes,
   setup/stencil/break/cleanup treatment, session count/durations и пояснение.
   Unknown остаётся null/unknown, не 0 и не модельной оценкой; явные величины
   валидируются, противоречивые суммы не исправлять догадкой. Подтверждение
   имеет actor/source/version. Owner case не становится публичным Portfolio,
   Knowledge или правом доступа к файлу другого Client.
   Для изображения переиспользовать разрешённый business asset/private preview;
   не создавать фиктивные messages/conversations и не копировать чужой
   клиентский референс в общую базу. Отзыв/замена источника делает зависимый
   preview/сравнение недействительным. Description-only case допустим.
   Bounded structured/keyword поиск по подтверждённым текущим кейсам своего
   Business; показать мастеру совпадения, различия и unknown с источниками.
   Новые embeddings, AI estimator, усреднение часов, calibration/fine-tuning,
   automatic rule publication и medical intervals не нужны.
   Ни case times, ни owner-only notes не попадают в client ContextPack/read
   tool, reply/caption или клиентский поиск; только отдельная owner projection.

7. **Минимальный UI и БД.** В текущем Inbox — сводка, sources, missing/conflict,
   понятный статус и owner correction/confirmation; в Action Center — вопрос;
   рядом с настройками/портфолио — маленькая DurationCase форма/поиск.
   Разрешено wiring в App/MessagingPanel/ConfigurationPanel/EscalationsPanel,
   без нового dashboard или переделки навигации. На scope/auth/OWNER/context
   смене очищать stale данные и private previews; не показывать successful
   mutation до durable acceptance. Owner auth/CSRF/idempotency/expected version,
   forced RLS, typed tenant/client FK, private capabilities, no runtime DDL и
   exact current schema verifier обязательны. Внешний I/O вне DB transaction.
   Единственная новая migration 0023; applied 0001–0022 immutable. Used downgrade
   отказывает до изменений, unused downgrade и повторный upgrade проверяемы.

Это конкретизация принятого IMPL-005 и ADR-024/265, не отмена архитектурных
инвариантов. Цены, Quote, согласованная длительность, запись и платежи — M6–M8.
Новых paid/provider/VM/real Telegram/client-data допусков нет. Исходные
UNKNOWN/NOT_PROVEN/holds, receiver ACK/fence и полный live HUMAN/Resume
сохраняются; старые receiver/probes не запускать.

### Разрешённые paths

Списки ниже конечные; brace notation разворачивается только в названные файлы.
Это верхняя граница, не требование менять каждый файл. Новые модули не являются
разрешением общего framework/refactor. Для нового path — показать C0 точный diff.

- Новые `backend/src/asm/intake/{__init__,models,validation,projection,templates,duration_cases,repository,service,http,errors}.py`,
  `backend/src/asm/ai/intake.py`, `backend/src/asm/ai/prompts/conversation_v7.txt`,
  `backend/src/asm/ai/schemas/conversation_result_v3.json`,
  `migrations/versions/0023_intake_duration.py`.
- AI wiring/contracts: `backend/src/asm/ai/{contracts,gateway,agent,context,knowledge,portfolio,portfolio_delivery,runtime,runtime_contracts,database,fake,settings}.py`.
  `backend/src/asm/ai/{runtime_settings,provider_runtime}.py` — только отказ
  legacy real sessions/new synthetic registration; transport/routes не расширять.
- Owner/domain integration: `backend/src/asm/configuration/{models,validation,permissions,errors,repository,service,http}.py`,
  `backend/src/asm/portfolio/{models,repository,service,http,errors}.py`,
  `backend/src/asm/conversations/{escalations,escalation_http,escalation_http_models,turns,material,guards,http_models}.py`,
  `backend/src/asm/messaging/{models,results,database,worker,http_models,http_service,http,errors}.py`,
  `backend/src/asm/tenancy/database.py`, `backend/src/asm/foundation.py`.
  Только описанные projection/owner commands/guarded runtime; старые
  control/native policies, transport/send/recovery не перепроектировать.
  `backend/src/asm/billing/models.py` — при необходимости только typed audit
  payload нового события, без billing operations/денежных правил.
  `backend/src/asm/telegram/provisioning.py` — только current schema readiness.
  `contracts/openapi.json` — штатная генерация изменённых DTO/API.
- Новые UI `frontend/src/{IntakePanel.tsx,IntakePanel.test.tsx,DurationCasesPanel.tsx,DurationCasesPanel.test.tsx,intake-api.ts,intake-api.test.ts,intake-fixtures.test-helper.ts}`;
  существующие `frontend/src/{App.tsx,App.test.tsx,MessagingPanel.tsx,MessagingPanel.test.tsx,EscalationsPanel.tsx,EscalationsPanel.test.tsx,ConfigurationPanel.tsx,ConfigurationPanel.test.tsx,PortfolioPanel.tsx,PortfolioPanel.test.tsx,messaging-api.ts,messaging-api.test.ts,messaging-fixtures.test-helper.ts,escalation-api.ts,escalation-api.test.ts,escalation-fixtures.test-helper.ts,configuration-api.ts,configuration-api.test.ts,configuration-fixtures.test-helper.ts,portfolio-api.ts,portfolio-api.test.ts,portfolio-fixtures.test-helper.ts,style.css}`.
  Новая `frontend/e2e/intake-duration.spec.ts`; существующие
  `frontend/e2e/{messaging,portfolio,portfolio-delivery}.spec.ts` — совместимость.
- Новые `tests/{m5_intake_fixtures,test_m5_intake,test_m5_intake_runtime,test_m5_intake_postgres,test_m5_intake_api_postgres,test_m5_intake_migrations,test_m5_duration_cases,test_m5_duration_cases_postgres}.py`.
  Новая `scripts/m5_intake_fixture.py` — только finite LOCAL/TEST browser setup
  через domain capabilities с проверкой target, без SQL shortcut/реального клиента.
  Existing targeted `tests/{test_m4_gateway,test_m4_gateway_failures,test_m4_agent,test_m4_runtime_database,test_m5_configuration,test_m5_configuration_migrations,test_m5_configuration_api_postgres,test_m5_portfolio_runtime,test_m5_portfolio_context,test_m5_portfolio_auth_boundary,test_m5_portfolio_runtime_postgres,test_m5_portfolio_delivery,test_m5_portfolio_delivery_postgres,test_m3_2_escalations,test_m3_2_escalations_api_postgres,test_m3_2_escalations_postgres}.py`;
  `tests/{m5_configuration_fixtures,m5_portfolio_fixtures,m5_portfolio_delivery_fixtures}.py`.
- **Только current 0023/readiness/fixture совместимость**:
  `tests/{generic_pg_schema,m5_knowledge_search_fixtures,test_foundation,test_m2_3_db_postgres,test_m2_3_schema_postgres,test_m2_3_setup,test_m2_4_browser_fixture,test_m3_1_guards_migrations,test_m3_1_native_context_postgres,test_m3_1_native_context_runtime_postgres,test_m3_2_escalations_migrations,test_m4_delivery,test_m4_delivery_postgres,test_m4_polza_runtime_postgres,test_m4_reply_rights,test_m4_runtime_migrations,test_m4_schema_postgres,test_m5_configuration_postgres,test_m5_knowledge_runtime_postgres,test_m5_portfolio_migrations,test_m5_portfolio_delivery_migrations,test_telegram_egress,test_telegram_egress_migration,test_telegram_egress_postgres,test_tenancy_postgres}.py`,
  `tests/fixtures/businesses.v1.json`, `scripts/{m2_4_browser_fixture,prepare_telegram_egress}.py`,
  `scripts/test_telegram_egress.sh`.
  `tests/test_postgres.py` — добавить в exact ordered table inventory только
  реально созданные 0023 таблицы; сохранить equality/roles/RLS/no-DDL assertions.
  `tests/test_m1_3_c0_acceptance.py` — только новые FK-required table literals
  в существующем transactional TRUNCATE; сохранить no CASCADE/rollback/все
  пять initializer cases и assertions. Новые nullable поля retained legacy
  fixtures исключать только из старой closed projection с отдельной IS NULL
  проверкой; не замалчивать новые данные и не переписывать historical profiles.
- Source/schema admission: `scripts/{m4_runtime_db,native_context_db_catalog}.py`,
  `tests/{test_m4_runtime_db_runner,test_native_context_db_runner}.py`.
  Новая exact M5.3A branch/base/tree/assignment route с producer/consumer proof,
  clean PR merge и push/main acceptance; старые task routes не расширять.
  Pin actual assignment SHA/tree/sole-parent и только 5 docs в initial diff.
  AGENTS, README, TASK_REGISTER, IMPL-005 immutable после assignment;
  `docs/tasks/M5_HANDOFF.md` — только короткий контракт/возврат C1 в этом CURRENT.
  Current 0023 verifier/catalog учитывать во всех нужных entrypoints, в том
  числе native context и old text sessions; их функциональные допуски прежние.
- Все workflow YAML, CI scripts/budgets вне названного admission, Compose,
  locks/dependencies/images, original architecture, operator/live probes,
  Polza/Vision/embedding transports и остальные paths закрыты.
  Foundation 60 min, browser 900s, runtime SQL 900s и прежние 600s сохраняются.

### Критерии готовности и возврат

1. Targeted unit/schema tests и actual PostgreSQL на используемых операциях:
   два Business одним кодом; другой Workspace и другой Client того же Workspace
   не доступны; owner-only DurationCase не попадает в client model/read/output;
   source spoofing/unknown/observed не повышают authority.
2. Multi-turn сценарий: часть данных уже известна → один нужный вопрос → ответ →
   исправление → новая сводка с источником. Edit/delete/replaced file/revoke/
   publish гонки дают свежую projection либо явный stale/refusal, не старый факт.
   Смена темы не смешивает запросы. COVER_UP и missing rule дают один актуальный
   handoff; concurrent/repeated execution и owner stale command не дублируют его.
   HUMAN/OWNER observation/Resume и existing text/photo delivery guards проходят
   положительные и отрицательные проверки; UNKNOWN не приводит к resend.
3. DurationCase: owner создаёт и подтверждает описание/пример с unknown полями;
   просмотр/исправление/отзыв и поиск показывают различия. Один настоящий
   browser journey на desktop и narrow viewport: intake summary/source,
   owner confirmation, Action Center и DurationCase без ручного SQL/JSON.
   Проверить auth/scope смену и несвоевременный response UI.
4. Actual PG: 0022→0023, repeat upgrade, fresh upgrade, unused downgrade/reupgrade,
   used downgrade refusal; exact independently observed catalog/functions/
   roles/RLS/FK/security/profile. После setup fix доходить до call в положительных
   и отрицательных сценариях; не считать ранний отказ проверкой последнего guard.
   Current table inventory и все M1 initializer cases включены заранее.
5. После targeted checks — один штатный полный CI кандидата со всеми 12 jobs,
   clean source/manifest, всеми фазами и cleanup. Не repeat unchanged runs,
   не skip/xfail/замена expected ради PASS/рост timeout. При сбоях разобрать
   все известные группы, разделяя implementation и test infrastructure.
6. C1 возвращает PR/head/tree, exact tested SHA/CI, контракт/миграцию и один
   понятный рабочий сценарий, evidence и реальные ограничения. Длинные логи
   — PR/CI. Статус REVIEW до C0; merge только после отдельного решения владельца.
   После actual merge/post-merge CI C0 выдаёт M5.3B. Не начинать M6.


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

M5.1A–M5.2D интегрированы; текущие paths и source admission задаёт только
CURRENT выше. Допуски предыдущих PR не разрешают автоматически будущие изменения
приложения. Current migration0022; слот0023←0022 выделен только M5.3A с проверкой
C1/C2 до SQL. Новые номера не резервировать цепочкой.

Не менять applied0001–0022, роли/гранты всех старых модулей, исторические schema
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

Сейчас достаточно передать C1 закреплённую ссылку на CURRENT M5.3A.
PR #45–#52 уже интегрированы. Разработка LOCAL/TEST идёт без нового paid/VM
допуска и без реальных материалов мастера. Новый PR открывает C1 после
подготовки работающего сценария и source admission.

Позже — только конкретное действие по готовому результату:
1. Если понадобится дополнительный real synthetic smoke — отдельные route,
   точные запросы, предел расходов и процедура остановки перед допуском владельца.
   Принятый M5.2A probe заново не запускать.
2. VM/Telegram smoke — отдельный допуск и проверка относящихся к нему receiver
   ограничений; прежние команды не переиспользовать вслепую.
3. Перед реальным бизнесом — подтверждение правил, прав на материалы и data route.
4. Merge нового PR — отдельное действие владельца после C0 review/CI.

## 7. Передача M6

M6 получает принятые service/intake/rule/release identifiers, source provenance,
private Portfolio/DurationCase access и предварительные факты разговора.
Он создаёт ServiceRequest/Assessment, утверждение цены/времени, QuoteAcceptance,
Order/Session и owner decision, не заменяя их результатом Vision или похожим кейсом.
Все OPEN live ограничения переносятся отдельным коротким списком.
