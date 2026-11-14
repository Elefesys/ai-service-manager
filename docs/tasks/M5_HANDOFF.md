# M5 — настройки бизнеса, знания, Vision и портфолио

Дата: 2026-11-12. Ведущий: C0. Статус исполнения — только в
[TASK_REGISTER](../TASK_REGISTER.md). Решение по объёму:
[IMPL-005](../decisions/IMPL-005-m5-pilot-knowledge.md) — ACCEPTED / LOCKED C0.

## CURRENT — M5.2B → C4 / IN_PROGRESS / 2026-11-14

Единственная активная задача **C4-M5.2B-KNOWLEDGE-SEARCH-R1**.
Ведущий C4; C1 помогает с configuration/API, C2 — со схемой, RLS и миграцией,
последовательно в рамках этой задачи. Остальные срезы M5 не выданы; C6 HOLD.

### Результат для пользователя

Владелец подготавливает небольшой подтверждённый текст, проверяет и публикует
его. При вопросе клиента приложение находит подходящие фрагменты опубликованных
знаний, включая переформулированный вопрос, и передаёт AI фрагменты с источниками.
Черновик/отозванный материал не попадает в ответ; неудачная индексация сохраняет
старую публикацию. Это следующий шаг после малого FAQ из M5.1B, необходимый
для принятого семантического поиска M5; сейчас можно разрабатывать без VM/paid.

### Repository, base, зависимости

- Repository: `Elefesys/ai-service-manager`; branch
  `c4/m5-2b-knowledge-search-r1`; integration target `main`.
- **Accepted application base: `8eeeede1b4a05537b0afb8c29992e8b681eaeb65`.**
  Tree: `df31d522ff862a0af58f1876fd8f16ddcda7bdc1`.
  PR48 merged владельцем; tree совпадает с принятым кандидатом b455e6eb.
- [Post-merge CI43600856660](https://github.com/Elefesys/ai-service-manager/actions/runs/43600856660):
  итог **12/12 SUCCESS**. Первый docker29/intent остановился на старте
  docker.service до тестов; повтор именно этой job прошёл на том же SHA.
  Остальные успешные checks сохранены с attempt1; неизменённый CI не повторять.
- Подготовленная ветка содержит один C0 docs-only assignment commit поверх
  accepted base. Его exact SHA/tree брать из закреплённой ссылки C0 и Git,
  сохранить в ancestry. Это старт выдачи, не application implementation.
- Зависимости M5.1A/B и M5.2A приняты. M5.2A code/CI — LOCAL/TEST;
  route/quality — ASSISTED_SYNTHETIC по существующим receipts PR48.
  Это не client-data/runtime activation и не новый paid допуск.
- Читать этот CURRENT, IMPL-005, Spec §6, §7.12 и ADR-030–036/051/052/075/076/148.
  Исторические M4/M5.2A handoff не перечитывать целиком.

### Ограниченный контракт и реализация

1. Начать с короткого совместного C4/C1/C2 контракта в PR/возврате: source/revision,
   подтверждение, chunks, build/profile, owner операции, runtime read, ошибки и
   численные лимиты. Зафиксировать пределы text/Markdown input, числа chunks,
   batch/query bytes/tokens, timeout и результата; текущий context budget не
   расширять. Не делать отдельный planning PR или универсальный registry.
2. Bounded text/Markdown/structured concierge input через owner domain/API.
   Source хранит автора/происхождение, ревизию, service/category, authority и
   effective dates; raw text сам не становится правилом. Без crawler/PDF/OCR,
   архивов и истории клиентов. Подтверждение владельца обязательно.
3. Canonical source/chunks отделить от embedding projection. Один профиль
   `polza_openai_text_embedding3small_1536_cosine_v1`:
   Polza / OpenAI / `openai/text-embedding-3-small`, 1536, cosine,
   EVAL_ONLY / synthetic. Не переключать branch/provider автоматически.
   Query и index должны совпадать по profile/version/dimensions/preprocessing.
4. Новый build готовить отдельно от active; активировать только полный валидный
   совместимый build вместе с release. Error/timeout/UNKNOWN не заменяет active.
   Publish/rollback/revoke используют owner authority, expected version,
   idempotency и монотонную activation. Сохранить старые v1 releases/runs и
   их receipts; не переписывать их под новый контракт.
5. В PostgreSQL выполнить scoped full-text/metadata + exact pgvector retrieval,
   deterministic bounded merge/ranking, provenance и честный empty/conflict.
   Источник Business брать из trusted conversation binding. Общие подтверждённые
   знания доступны его клиентам; чужие Business/Workspace и личные данные другого
   Client недоступны. Никакого search_everything, отдельной vector DB или ANN.
6. Включить результат в защищённый ConversationAgent/ContextBuilder/read path.
   Версионировать изменённые DTO/prompt/schema; не увеличивать agent loop/tool
   budget автоматически. Rules/service policy остаются authoritative.
   Сохранить проверки актуальности на MODEL/READ/FOLLOWUP/CANDIDATE/COMMIT/SEND,
   HUMAN/Resume, OWNER reconciliation, observation barrier, Telegram rights и
   UNKNOWN/no-resend. Revocation/delete/expiry исключают материал из новых reads
   и блокируют stale ещё не отправленный ответ; cache не обходит проверку.
7. Embedding adapter/build/query path проверять controlled transport в LOCAL/TEST.
   HTTP не держит DB transaction; finite reservations, durable outcome/receipt,
   restart и uncertain-call no-resend обязательны. Для owner build не создавать
   фиктивные Telegram conversations/messages и не включать общий job engine.
   Использовать маленькую отдельную операцию с durable outcome при необходимости.
   Отсутствующий embedding completion_tokens — NOT_APPLICABLE, raw ABSENT
   сохраняется; present допустим только integer0. Не требовать provider в body,
   если exact request history подтверждает маршрут; не выдумывать это подтверждение.
   Identity/usage/cost evidence различать; асинхронная финансовая сверка не заменяет
   functional проверки (ADR-148). Старые UNKNOWN/holds/closed plans не менять.
8. В существующем owner экране — минимальный способ посмотреть источник,
   подтвердить/опубликовать/отозвать и увидеть ошибку build. Допустим bounded
   concierge import через тот же service; ежедневный review/publish/revoke
   не требует SQL/ручного JSON. Не строить новый кабинет или dashboard.

### Миграция и write-set

Фактический head **0019**; applied0001–0019 immutable. C0 выделяет для этого
среза единственный следующий слот **0020**, predecessor **0019**.
C2 до SQL подтверждает отсутствие конкурирующей миграции и минимальный контракт;
имя файла `migrations/versions/0020_knowledge_search.py`. Не резервировать цепочку
номеров. При конфликте сначала согласовать C0/C2, не переименовывать применённое.

Разрешены только нужные для указанного сценария paths:
- Новый bounded domain `backend/src/asm/knowledge/`: `__init__.py`,
  `models.py`, `errors.py`, `validation.py`, `permissions.py`,
  `repository.py`, `service.py`, `http.py`, `embeddings.py`.
  Не создавать пустые файлы/слои ради списка.
- `backend/src/asm/configuration/{models,validation,repository,service,http}.py`;
  `backend/src/asm/ai/{knowledge,contracts,context,agent,database,fake,gateway,runtime,runtime_contracts,runtime_settings,provider_runtime,settings,polza}.py`;
  новая версия conversation prompt/result schema, сохраняя старые версии.
- `backend/src/asm/foundation.py`, `backend/src/asm/tenancy/database.py`,
  `backend/src/asm/messaging/{database,worker,results,errors}.py` —
  только подключение нового контракта/сохранение currentness; `contracts/openapi.json`.
- `migrations/versions/0020_knowledge_search.py`.
- Минимальный owner UI: `frontend/src/ConfigurationPanel.tsx`,
  `frontend/src/configuration-api.ts`, `frontend/src/style.css`, их существующие
  tests/fixtures и `frontend/e2e/configuration.spec.ts`; App wiring только при
  необходимости в `frontend/src/App.tsx`/`App.test.tsx`.
- Новые `tests/test_m5_knowledge_search*.py`, `tests/m5_knowledge_search_fixtures.py`,
  `tests/fixtures/m5_knowledge_search/`; относящиеся существующие M5 configuration/
  knowledge tests и M4 context/agent/gateway/runtime/delivery/rights regression tests.
- Current-schema compatibility, только по фактическому impact list:
  `scripts/m4_runtime_db.py`, `scripts/native_context_db_catalog.py`,
  `tests/generic_pg_schema.py`, `tests/test_postgres.py`,
  `tests/test_tenancy_postgres.py`, `tests/test_foundation.py`,
  `tests/test_auth_contract.py`, `tests/test_m4_runtime_db_runner.py`,
  `tests/test_native_context_db_runner.py`, schema/profile guards в существующих
  M2/M3/M4 test fixtures, `backend/src/asm/telegram/provisioning.py`,
  `scripts/m2_4_browser_fixture.py`, `scripts/m2_4_browser_worker.py`,
  `scripts/prepare_telegram_egress.py`, `scripts/test_telegram_egress.sh`.
  Это не разрешение менять Telegram/native поведение или исторические expected.
- `docs/tasks/M5_HANDOFF.md`: короткий контракт/возврат. AGENTS, README,
  TASK_REGISTER и IMPL-005 из C0 assignment — сохранить; статус меняет C0.

Не изменять старые миграции, исходную архитектуру, dependencies/lockfiles,
`.github/workflows`, deployment, capability probe/fixtures PR48, ценовые
планы, provider routing M4 или будущие Portfolio/DurationCase/Quote таблицы.
Любой дополнительный path/новый существенный контракт — конкретный запрос C0
с причиной; сначала выполнить независимую разрешённую часть.

### Source admission и критерии готовности

Текущий runner узнаёт только прежние M5 branches. В рамках этой выдачи разрешено
добавить **узкий M5.2B admission** для указанной ветки/base/assignment и её будущего
main merge: exact base tree, assignment ancestry, закрытый write-set и неизменность
C0 docs. Старые admission branches/отказы сохраняются. Не расширять глобальный
allowlist, не удалять проверку attempt/source и не менять runtime budget ради PASS.
До открытия Draft PR/первого CI проверить actual Git pins/ancestry/protected diff
и положительные/отрицательные admission cases. Не открывать заведомо красный
docs-only PR с ещё не поддержанной веткой.

Готовность — работающий сценарий и относящиеся K02–K06/K11/K12:
- actual PG/pgvector под runtime role: релевантный exact-vector + keyword result,
  provenance, empty/conflict, mismatch profile/dimensions/invalid vector отказ;
  draft/unconfirmed/revoked/expired не читаются; cross-tenant/business/client tests;
- source edit/build/publish/revoke/rollback races; failed build сохраняет active;
  удалить источник и производные данные без восстановления удалённого через rollback;
- owner API + browser: ввод/preview/confirm/publish/revoke без SQL; ошибка build видна;
- controlled runtime: опубликованный fragment доходит до AI reply; prompt injection
  остаётся данными; смена публикации/прав/HUMAN на границах блокирует stale эффект;
- bounded embedding wire, accounting/restart/UNKNOWN и отсутствие HTTP по умолчанию.
  Fake vectors доказывают механику, не качество модели. M5.2A real sample остаётся
  отдельным capability evidence, не выдаётся за новый end-to-end semantic benchmark.
- upgrade с чистой БД и с0019, current schema/catalog совместимость и исторические
  invariants. Сначала целевые unit/actualPG/browser по риску, затем один штатный
  полный CI итогового небольшого PR. Не повторять unchanged успешные проверки.

Вернуть PR/head, контракт/миграцию C2, фактические сценарии/команды/результаты,
ограничения и следующий шаг. C0 review → отдельное owner merge; auto-merge нет.
Новые model POST/GET, ключи, действия на ВМ и реальные клиентские данные не
разрешены этим заданием. Если для дополнительной проверки понадобится paid smoke,
сначала готовые процедура/route/точные запросы/предел расходов, затем отдельный
допуск владельца; не повторять M5.2A ради нового отчёта.

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

M5.1A, M5.1B и M5.2A интегрированы; текущие paths и source admission задаёт только
CURRENT выше. Допуски PR #45/#46/#47 не разрешают автоматически будущие изменения
приложения. Current migration0019; новые номера не резервировать цепочкой,
назначать с C2 по фактическому head при выдаче соответствующей задачи.

Не менять applied0001–0019, роли/гранты всех старых модулей, исторические schema
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

Сейчас достаточно передать C4 закреплённую ссылку на CURRENT M5.2B.
PR #45–#48 уже интегрированы. Разработка LOCAL/TEST идёт без нового paid/VM
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
