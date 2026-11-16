# M5 — настройки бизнеса, знания, Vision и портфолио

Статус исполнения — в [TASK_REGISTER](../TASK_REGISTER.md).
Решение по объёму — [IMPL-005](../decisions/IMPL-005-m5-pilot-knowledge.md),
ACCEPTED / LOCKED C0.

## CURRENT — C3-M5.2D-PORTFOLIO-PHOTO-R1 / IN_PROGRESS / 2026-11-16

**Единственная активная задача — M5.2D, ведущий C3.**
C2 помогает с SQL/миграцией, C4 — с typed model selection, C5 — с Inbox,
последовательно в одной ветке. C6 HOLD; M5.3 пока не выдаётся.

### Результат для пользователя

Клиент получает одну опубликованную и разрешённую владельцем работу бизнеса
с короткой подписью. Мастер видит это исходящее фото и достоверное состояние
доставки в текущем Inbox. Фото проходит тот же контроль разговора и доставки,
что текст. Это следующий согласованный срез M5; отправка альбомов, ручной
media composer, генерация изображений и intake сюда не входят.

### Принятая основа и завершение M5.2C

- Repository: `Elefesys/ai-service-manager`.
- Ветка: `c3/m5-2d-portfolio-photo-r1`; один небольшой Draft PR в `main`
  после готовности реализации и source admission.
- **Exact accepted application base: `8d98593bc739666176968c5d76b9c01a2a711686`.**
  Tree: `a14ed9b69e3529ac060bc015b9a24dcea515ef9b`.
  PR #51 слит; parents `84ad8e4c954005801f115aa8e6c0c6f7edef40db` +
  `47457668510b5103206491463e6bd65869c988b7`. Tree совпадает с кандидатом.
- C0 сохранил поверх base только 5 assignment docs. Exact assignment SHA/tree
  взять из закреплённой ссылки и Git; сохранить этот commit в ancestry.
  PR #50/#51 и их старые ветки не продолжать.
- **M5.2C и CI fix — INTEGRATED / VERIFIED в synthetic LOCAL/TEST.**
  [Post-merge CI43818223732](https://github.com/Elefesys/ai-service-manager/actions/runs/43818223732):
  push/main, attempt 1, **12/12 SUCCESS**, без повторов.
  C0 сверил exact main/tree/parents и source archive/binding всех 438 Git
  blobs/bytes/modes/SHA256. 4499 unit + 161 subtests PASS; 1016/1016 generic PG
  со всеми start/setup/call/teardown/end PASS, без skip/xfail; все 14 backend
  phases и primary/cleanup 0. Runtime 160/160, 8/8 cleanup PASS,
  main source admission PASS, SQL 725.406s из прежних 900s.
  Foundation целиком 37m36s; build 34.015s, unit phase 492.632s,
  generic phase 1656.097s. Эти значения не смешивать со временем компиляции.
- Foundation artifact14206445469 ZIP SHA256
  `666340ffa3218cdf007e025daa8211a852eaafdd853f0e445528303cd7927132`;
  runtime artifact14204180560 ZIP SHA256
  `9bc2e4e23dfb4f131f7388f58786e78bfb5f1188bd25cbd08bc703d25e2b92bd`.
  Source archives совпадают; runtime manifest проверен; остальные 10 jobs
  SUCCESS по Actions API. Новый прогон C0 не запускал.
- [Приёмка реализации M5.2C](https://github.com/Elefesys/ai-service-manager/blob/c132213302daeeaa4f9309d6352841fe99d6da8e/docs/tasks/M5_HANDOFF.md#L803)
  и [приёмка CI fix](https://github.com/Elefesys/ai-service-manager/blob/e027855477bbe8a2428d7c95ce45bc216fa24e5c/docs/tasks/M5_HANDOFF.md#L142)
  сохраняются. Старый CI43800096544 остаётся CANCELLED; он не переписан в PASS.
  Functional capability M5.2A остаётся ASSISTED_SYNTHETIC; M5.2C не дал нового
  допуска real-client/provider/Telegram.

### Сначала сверить зависимости, затем реализовать

Прочитать AGENTS, CURRENT реестра, IMPL-005 и применимые IMPL-004,
Architecture Spec §3 tenant/client isolation, §4.1–4.6, §5.12.1,
§6.14–6.15, §18 delivery/idempotency; ADR-019/020/028/128/173/174/252.
Исходные архитектурные файлы не переписывать.

Проверенные ограничения actual base:

- `TelegramHTTPClient.send` отправляет только JSON `sendMessage`;
  готового `sendPhoto` нет. Успех имеет строгую проверку connection/chat/message,
  неоднозначный результат даёт UNKNOWN.
- `ConversationResult`/`conversation_result_v1` и prompts v1–v5 — text-only.
  v5 содержит `PortfolioRefs` с item/revision/asset-version/source hash,
  а `read_context` заверяет точный уже поставленный bounded context.
  Ни такой ref, ни сохранённый RuntimeReceipt не является send permit.
- SQL currentness/receipt helpers в 0021 явно ветвятся по conversation_v5
  (в частности portfolio_runtime_current/ai_runtime_receipt). Новая v6 обязана
  проходить те же проверки; ветка «для других revisions true» не является
  допустимым обходом. Расширять функции через 0022, не изменяя applied 0021.
- Worker исполняет существующие SEND_MANUAL_TEXT/SEND_GUARDED_TEXT/SEND_AI_TEXT,
  использует PostgreSQL claim, fresh Telegram rights и durable DISPATCHING.
  Owner portfolio имеет отдельные assets/versions; это не inbound FileObject.
- Owner message DTO и frontend сейчас знают TEXT/IMAGE_REFERENCE.
  Нельзя сделать вид, что показываемое входящее фото уже является исходящим.
- Head схемы **0021**. C0 резервирует только
  `migrations/versions/0022_portfolio_delivery.py`, `down_revision="0021"`.
  C3/C2 до SQL проверяют фактический слот и фиксируют короткий контракт данных,
  команд/ошибок и точки сериализации здесь. При совпадающем слоте и выполнении
  границ ниже дополнительный круг разрешения C0 не нужен.

### Принятое C0 техническое ограничение M5.2D

1. **Новая явная версия результата и runtime.**
   Использовать `conversation_v6` + `conversation_result_v2` и отдельный
   закрытый config/result DTO. v1–v5, schema v1, прежние сохранённые runs,
   provider sessions и их парсинг/повтор не переосмысливать.
   В v2 допускается ровно одна proposed portfolio-photo selection с caption
   либо прежнее text/handoff/no_reply поведение. Схему и discriminators
   C3/C4 фиксируют до SQL; неизвестные поля/версии отклоняются.
   Новое исходящее photo в history не должно ломать следующий text turn;
   старые snapshots/receipts сохраняют свои закрытые формы.
   Не добавлять model mutation tool и не расширять бюджет 2 calls / 1 READ.
   Фото выбирается только после успешного fresh READ именно показанного
   контекста: item/revision/asset-version/hash должны совпасть с фактически
   показанным подмножеством current PortfolioRefs, включая context reduction.
   Новый v6 context сообщает media eligibility либо только sendable subset;
   отсутствие пригодного JPEG/PNG не превращается в выдуманную успешную отправку.
   При изменении read shape вводится новая явная revision, старый read_v4 сохранён.
   Модель не выбирает workspace/client/chat, storage key, URL или Telegram file_id.

2. **Авторитетное намерение и единичный эффект.**
   Сервер повторно проверяет опубликованный MY_WORK, owner confirmation,
   show_permission, активные release/build/activation и точную private asset
   version/hash. CLIENT_REFERENCE, INSPIRATION, draft/revoked/deleted,
   чужой Business/Workspace и личный файл другого Client не допускаются.
   Общая разрешённая работа Business может быть показана его разным клиентам;
   персональные reference/history других клиентов — нет.
   Persisted photo intent закрепляет source, версии, caption и fingerprint;
   создаёт настоящее исходящее Message/Outbox через существующий durable kernel.
   Не создавать фиктивные inbound messages/conversations для чтения портфолио.
   Одна выбранная реакция — один photo+caption send или один text send.
   Нет отдельного следом sendMessage, альбомов, новой очереди, sender-сервиса
   или автоматической подмены изображения другой версией.

3. **Private bytes и последний допуск к отправке.**
   Отдельный узкий DB-issued media-read permit привязан к trusted job/run,
   conversation и точной asset version. Переиспользовать private S3 и validator.
   Читать и проверять bounded bytes/hash до durable dispatch admission;
   после I/O снова проверить актуальность и выдать окончательный send permit.
   Проверка publish/revoke/delete, HUMAN/Resume, control generation, native
   OWNER reconciliation/observation barrier, material/current context,
   claim/fence, owner authority и billing проходит в существующей согласованной
   точке сериализации. Нет DB transaction/lock через S3 или Telegram HTTP.
   Отзыв до этой точки блокирует отправку; уже DISPATCHING/in-flight эффект
   нельзя обещать отменить задним числом (Spec §5.12.1).
   Путь не выдаёт модели/клиенту public/presigned S3 URL. Preview мастеру
   обслуживается существующим авторизованным owner read либо узким дополнением.

4. **Ограниченный Telegram transport.**
   В этом срезе — только проверенный **JPEG/PNG**, без перекодирования.
   Использовать исходные байты закреплённой версии и multipart `sendPhoto`;
   URL/file_id input, WebP, анимации, albums и генерация закрыты.
   Telegram-совместимый поднабор: не более **10,000,000 bytes**,
   width+height ≤10000, max(width/height,height/width) ≤20,
   плюс все более строгие текущие decoder/pixel/side ограничения.
   Caption — plain text, непустой, до 1024 символов; без parse_mode/entities,
   скрытого обрезания текста и дополнительных кнопок/paid broadcast.
   Неподдерживаемый исходник честно даёт unavailable до dispatch, а не
   изменение оригинала или неожиданный fallback-send.
   Официальные зависимости проверены C0 2026-11-16:
   [sendPhoto](https://core.telegram.org/bots/api#sendphoto),
   [BusinessBotRights](https://core.telegram.org/bots/api#businessbotrights).
   Для нашего private business route обязательны trusted chat_id и
   business_connection_id, актуальные is_enabled/can_reply и окно ответа.
   Сохранить TLS/redirect/proxy/response-size/deadline guards и retries=0.
   SUCCESS требует корректный Telegram Message с нужными connection/chat/id
   и photo shape; 200/malformed, wrong destination, response loss, timeout
   после возможной передачи или cancel не становятся SENT.
   Старые M4 text-only real-provider sessions не дают photo authority.

5. **Повтор, восстановление и видимость владельцу.**
   Повтор intent/finish после lost DB ACK использует существующий receipt,
   не повторяет model call или внешний effect. После возможного send effect
   UNKNOWN сохраняется и после restart/reclaim; автоматический resend,
   text fallback и кнопка «повторить UNKNOWN» запрещены.
   Только доказанно NOT_SENT может использовать существующую bounded retry
   policy с новыми guards; 429/transport классификацию проверить отдельно.
   Собственный Telegram echo не создаёт вторую доставку, фиктивный client
   input/OWNER observation или ложный takeover.
   Минимально расширить Inbox: исходящее фото/его источник, caption,
   текущий delivery status и честное unavailable/UNKNOWN.
   Никаких новых вкладок, ручного photo composer или обхода guards из Console.
   `MessagingPanel.tsx` и соответствующий DTO parser **явно разрешены** ниже.
   Смена workspace/conversation/session и отзыв доступа очищают старый preview;
   не смешивать inbound image reference и portfolio version.

6. **Только synthetic LOCAL/TEST.**
   Новая ветвь runtime — FAKE/EVAL_ONLY, default OFF; существующие Vision/
   embedding defaults DISABLED не менять. Telegram wire tests — exact
   MockTransport в TEST, effect/crash tests — ControlledAdapter с настоящим
   счётчиком вызовов/эффектов без внутренней дедупликации.
   Actual PostgreSQL и private S3 обязательны; изображение явно synthetic,
   в TEST owner подтверждает его как тестовую MY_WORK fixture.
   Никаких настоящих Telegram/model calls, VM, ключей или клиентских данных.
   Старые provider receipts/UNKNOWN/holds, receiver ACK/fence и live
   HUMAN/Resume ограничения сохраняются. Live smoke — отдельная будущая выдача.

### Разрешённый write-set

Это верхняя граница scope, не требование менять каждый перечисленный файл.
Новые узкие модули указаны отдельно; соседние продуктовые области закрыты.

- AI: `backend/src/asm/ai/{contracts,gateway,agent,context,portfolio,runtime,runtime_contracts,database,fake,settings}.py`;
  новые `backend/src/asm/ai/portfolio_delivery.py`,
  `backend/src/asm/ai/prompts/conversation_v6.txt`,
  `backend/src/asm/ai/schemas/conversation_result_v2.json`.
  `backend/src/asm/ai/{runtime_settings,provider_runtime}.py` — только явное сохранение отказа старых real sessions
  и необходимая строгая регистрация новой synthetic ветви; real Polza/probe/
  capability/Vision/embedding transport и старые prompts/schemas не менять.
- Messaging: `backend/src/asm/messaging/{models,results,database,worker,adapter,policy,http_models,http_service,http,errors}.py`;
  Telegram: `backend/src/asm/telegram/{client,adapter,normalization,database}.py`.
  `backend/src/asm/telegram/provisioning.py` — только current schema readiness.
  `backend/src/asm/conversations/{turns,material,guards,http_models}.py` —
  только versioned projection настоящего исходящего photo и совместимость
  нового history с сохранёнными snapshots; control/native rules не ослаблять.
  Manual text и исторический guarded text сохраняют прежние гарантии.
- Private media: новый `backend/src/asm/portfolio/delivery.py`;
  `backend/src/asm/portfolio/{models,repository,storage,service,http,errors}.py`,
  `backend/src/asm/files/{models,storage}.py` — только typed delivery/read
  permit и reuse private bytes/owner preview, без нового upload/import engine.
  Существующий `files/validation.py` не ослаблять; Telegram subset проверять
  отдельно в новом delivery module.
- `backend/src/asm/foundation.py` — wiring нового пути и exact 0022 profile;
  `backend/src/asm/billing/models.py` — только typed messaging audit/payload
  при необходимости, не деньги/правила/новые billing operations.
  Одна новая migration `migrations/versions/0022_portfolio_delivery.py`;
  applied 0001–0021 immutable. `contracts/openapi.json` — штатная регенерация
  только изменённого owner DTO/API.
- UI: `frontend/src/{MessagingPanel.tsx,MessagingPanel.test.tsx,messaging-api.ts,messaging-api.test.ts,messaging-fixtures.test-helper.ts,portfolio-api.ts,portfolio-api.test.ts,portfolio-fixtures.test-helper.ts,style.css}`;
  `frontend/e2e/{messaging.spec.ts,portfolio.spec.ts}`.
  При необходимости отдельного сценария —
  `frontend/e2e/portfolio-delivery.spec.ts`.
  PortfolioPanel/App и остальная owner Console — без перепроектирования.
- Новые tests:
  `tests/test_m5_portfolio_delivery.py`,
  `tests/test_m5_portfolio_delivery_transport.py`,
  `tests/test_m5_portfolio_delivery_postgres.py`,
  `tests/test_m5_portfolio_delivery_migrations.py`,
  `tests/m5_portfolio_delivery_fixtures.py`.
  Существующие targeted tests:
  `tests/{test_m4_gateway,test_m4_gateway_failures,test_m4_agent,test_m4_runtime_database,test_m5_portfolio_runtime,test_m5_portfolio_context,test_m5_portfolio_auth_boundary}.py`
  и `tests/m5_portfolio_fixtures.py` — совместимость v1–v5/старых guards.
- Узкая current 0022/readiness/fixture совместимость, без пересмотра старых
  сценариев/expected/исторических SQL profiles:
  `tests/{generic_pg_schema,m5_knowledge_search_fixtures,test_foundation,test_m2_3_db_postgres,test_m2_3_schema_postgres,test_m2_3_setup,test_m2_4_browser_fixture,test_m3_1_guards_migrations,test_m3_1_native_context_postgres,test_m3_1_native_context_runtime_postgres,test_m3_2_escalations_migrations,test_m4_delivery,test_m4_delivery_postgres,test_m4_polza_runtime_postgres,test_m4_reply_rights,test_m4_runtime_migrations,test_m4_schema_postgres,test_m5_configuration_postgres,test_m5_knowledge_runtime_postgres,test_m5_portfolio_migrations,test_telegram_egress,test_telegram_egress_migration,test_telegram_egress_postgres,test_tenancy_postgres}.py`;
  `tests/fixtures/businesses.v1.json`;
  `scripts/{m2_4_browser_fixture,prepare_telegram_egress}.py`,
  `scripts/test_telegram_egress.sh`.
- CI source/schema admission:
  `scripts/{m4_runtime_db,native_context_db_catalog}.py`,
  `tests/{test_m4_runtime_db_runner,test_native_context_db_runner}.py`.
  Только новая exact task branch/base/assignment route и current 0022 profile.
  Существующий foundation route пинит base 84ad8e4/assignment eb64476 и новую
  задачу автоматически не допускает. Новый branch/main selector, producer/
  validator proof и конечный write-set согласовать; old routes не расширять.
  Все 4 C0 assignment docs (AGENTS, README, TASK_REGISTER, IMPL-005) immutable
  после assignment. `docs/tasks/M5_HANDOFF.md` — короткий контракт и возврат C3.
- Все workflow YAML, `scripts/check_backend.sh`, `scripts/test_browser.sh`,
  Compose/images/locks/dependencies, исходная архитектура, operator scripts,
  M4/M5.2A live probes и прочие paths закрыты.
  CI limits foundation 60/browser 900/runtime SQL 900 и прежние 600 сохраняются.
  Новый необходимый path или конфликт вернуть C0 с точным меньшим diff;
  не открывать общий scope автоматически.

### Критерии готовности и порядок

1. До SQL — короткий C3/C2/C4 контракт: v2 result, exact selected reference,
   immutable intent, permit/dispatch boundary, error/state mapping,
   source-read/owner-preview authority и 0022 profile. Проверить migration slot.
   Принятые выше решения реализуются без нового общего архитектурного этапа.
2. Сначала целевые проверки по риску:
   - actual PG/S3: publish permitted work → v6 fresh READ → выбор одного
     допустимого ref → один photo intent → один counted effect → owner Inbox;
     выбранные bytes/hash/caption совпадают с намерением;
   - photo/text взаимоисключение; ref вне урезанного контекста, чужие IDs,
     source injection/URL/file_id, неправильные origin/permission/version/hash,
     нет подходящей работы, MIME/bytes/dimensions/ratio/caption boundaries;
   - revoke/delete/replacement/publish/rollback, HUMAN/Resume, stale claim,
     observation/material changes и rights/window loss на всех применимых
     существующих границах, в том числе после чтения bytes до final admission;
   - потеря ACK до/после commit, send effect/response loss, cancel, restart,
     reclaim, malformed success, explicit NOT_SENT/429 и UNKNOWN/no-resend;
     receipt/echo не создаёт дубликат или ложное управление разговором;
   - actual 0022 clean +0021→0022, repeat upgrade, runtime RLS/noDDL,
     исторические0021/0020/... profiles отдельно, used downgrade fail-closed
     с сохранением rows/receipts/in-flight state. Current expected выводится
     из проверенного source/catalog, а не заменяется фактическим ради PASS;
   - реальный browser desktop+narrow: авторизованный исходящий photo preview,
     caption/status/unavailable/UNKNOWN, смена scope, истёкшая session и
     committed response recovery; существующие text/inbound/UI journeys PASS.
     Подменённый HTTP route не считается проверкой PG/S3/owner boundary.
3. До PR проверить настоящий clean Git PR/main source admission; synthetic
   LOCAL event metadata явно отделить от Actions evidence. Новый 0022/current
   profile и old closed fixtures пройти до полного CI, чтобы ранний отказ
   не скрывал downstream checks. Новые PG cases включить в штатный generic
   набор; прежние runtime/native inventories не сокращать и не подменять.
4. Затем один push полного кандидата, один Draft PR и штатный full CI.
   Требуются все 12 jobs SUCCESS на одном source, полное evidence и cleanup 0.
   Повтор unchanged полного CI, skip/xfail или рост timeout ради PASS запрещён.
   При сбоях разобрать все известные группы и отличить код от infrastructure.
5. Возврат C3: PR/head/tree, exact tested SHA/CI/artifacts; один описанный
   работающий сценарий, contract/migration delta, targeted/CI evidence,
   ограничения и следующий шаг. Длинные журналы — в CI/PR.
   C0 review → отдельное owner merge → post-merge CI; только затем M5.3A.


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

M5.1A/B и M5.2A/B интегрированы; текущие paths и source admission задаёт только
CURRENT выше. Допуски предыдущих PR не разрешают автоматически будущие изменения
приложения. Current migration0020; слот0021←0020 выделен только M5.2C с проверкой
C2 до SQL. Новые номера не резервировать цепочкой.

Не менять applied0001–0020, роли/гранты всех старых модулей, исторические schema
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

Сейчас достаточно передать C4 закреплённую ссылку на CURRENT M5.2C.
PR #45–#49 уже интегрированы. Разработка LOCAL/TEST идёт без нового paid/VM
допуска и без реальных материалов мастера. Новый PR открывает C4 после
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
