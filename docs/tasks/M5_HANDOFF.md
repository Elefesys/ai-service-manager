# M5 — настройки бизнеса, знания, Vision и портфолио

Статус исполнения — в [TASK_REGISTER](../TASK_REGISTER.md).
Решение по объёму — [IMPL-005](../decisions/IMPL-005-m5-pilot-knowledge.md),
ACCEPTED / LOCKED C0.

## CURRENT — M5.3B / C0 ACCEPTED · READY FOR OWNER MERGE / 2026-11-19

**C0 принял кандидата. Следующее действие владельца — слить [PR #54](https://github.com/Elefesys/ai-service-manager/pull/54) в `main` через `Create a merge commit`.** Независимая приёмка C8 завершена. Все пять замечаний закрыты. K01–K12 прошли в согласованных пределах synthetic LOCAL/TEST. [Заключение C8 R3](https://github.com/Elefesys/ai-service-manager/blob/06d77019ca3d4a59e3a3b25787a98bab0a37f22d/docs/tasks/M5_HANDOFF.md#L27) · [матрица K01–K12](https://github.com/Elefesys/ai-service-manager/blob/06d77019ca3d4a59e3a3b25787a98bab0a37f22d/docs/tasks/M5_HANDOFF.md#L328).

| Объект | Проверенная версия |
|---|---|
| Принятый `main` до слияния | `c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba` |
| Head PR #54 · `c1/m5-3b-v7-fixes-r1` | `7e5cbc1f5caeaafa507de0c4cfd7dee7c4ee6455` |
| Дерево кандидата и тестового слияния | `cf2710c69fdd3823ed0a8b12b89d139b509ea13f` |
| GitHub test merge | `5244a3be1caeb4ed1ebbe2ec368e9511ec876958` · родители в порядке `main`, head PR |
| CI кандидата | [44359814084](https://github.com/Elefesys/ai-service-manager/actions/runs/44359814084) · 12/12 SUCCESS с первой попытки |

В трёх конкурентных проверках PostgreSQL мастер прочитал или обработал карточку в том же диалоге, где работал бот. При конфликте двух опубликованных ответов FAQ мастер получил одну карточку с текущим вопросом и уже собранными фактами. Повтор сохранил тот же ID, число автономных отправок клиенту за этот ход — ноль. Пять случаев FAQ включают обычный ответ, пустой intake и отказы при устаревшей публикации или чужом диалоге. [Проверки PostgreSQL](https://github.com/Elefesys/ai-service-manager/actions/runs/44359814084/artifacts/14459173205).

После слияния C0 сверит фактический SHA `main`, обоих родителей и дерево с принятым кандидатом, затем проверит штатный CI события `push` на этом SHA. Успешная проверка завершит приёмку M5 в synthetic LOCAL/TEST и откроет передачу по §7. Обычный merge commit сохраняет родителей, которых проверяет допуск исходников. [Проверка родителей и дерева](https://github.com/Elefesys/ai-service-manager/blob/7e5cbc1f5caeaafa507de0c4cfd7dee7c4ee6455/scripts/m4_runtime_db.py#L1665).

### Возврат C8 — PASS для C0

**C8-M5-04 и C8-M5-05 закрыты.** Кандидат PR #54 прошёл независимую
приёмку в synthetic LOCAL/TEST. Исходные C8-M5-01–03 закрыты по R2.
[Итог K01–K12](#4-одна-приёмочная-матрица).

- Application head `7e5cbc1f5caeaafa507de0c4cfd7dee7c4ee6455`, tree
  `cf2710c69fdd3823ed0a8b12b89d139b509ea13f`. Tested merge `5244a3be1caeb4ed1ebbe2ec368e9511ec876958`
  имеет то же дерево, родители `c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba`
  и проверенный head. От R2 один коммит на пяти разрешённых путях.
  [CI 44359814084](https://github.com/Elefesys/ai-service-manager/actions/runs/44359814084) — **12/12 SUCCESS**, attempt 1. Сверены ZIP и Git-идентичность
  483 путей, blob SHA и executable modes, фазы всех 1 106 Core PG
  тестов по `ci.log` и `cases.jsonl`. Восемь целевых случаев прошли
  setup/call/teardown. [Core](https://github.com/Elefesys/ai-service-manager/actions/runs/44359814084/artifacts/14459173205) · [Runtime](https://github.com/Elefesys/ai-service-manager/actions/runs/44359814084/artifacts/14454976346) ·
  [Native](https://github.com/Elefesys/ai-service-manager/actions/runs/44359814084/artifacts/14455800526) · [Chromium](https://github.com/Elefesys/ai-service-manager/actions/runs/44359814084/artifacts/14455581582).
- **C8-M5-04 · CLOSED.** В установленной 0024 worker, `intake_owner`
  и `RESOLVE` intake-карточки берут `CONFIGURATION_V1` раньше строки
  диалога. В трёх Core PG сценариях `pg_blocking_pids` подтвердил
  независимые транзакции, а `pg_locks` — ожидание одного advisory lock.
  READ совпал с PREPARE по context version. При PENDING прежний PREPARE
  получил `NOT_ALLOWED`, CONFIRM обновил сводку, RESOLVE закрыл ту же
  карточку. ID и адресат сохранились, replay вернул receipt, вызовы
  транспорта — 0. Последовательные тесты сохранили отказ stale CAS и
  решения по удалённому источнику. Проверки обычных карточек тоже прошли.
  [Три конкурентных теста](https://github.com/Elefesys/ai-service-manager/blob/7e5cbc1f5caeaafa507de0c4cfd7dee7c4ee6455/tests/test_m5_intake_postgres.py#L318) · [SQL RESOLVE](https://github.com/Elefesys/ai-service-manager/blob/7e5cbc1f5caeaafa507de0c4cfd7dee7c4ee6455/migrations/versions/0024_intake_v7_repair.py#L465) · [SQL intake_owner](https://github.com/Elefesys/ai-service-manager/blob/7e5cbc1f5caeaafa507de0c4cfd7dee7c4ee6455/migrations/versions/0024_intake_v7_repair.py#L718) ·
  [Stale source](https://github.com/Elefesys/ai-service-manager/blob/7e5cbc1f5caeaafa507de0c4cfd7dee7c4ee6455/tests/test_m5_intake_postgres.py#L710) · [Обычные карточки](https://github.com/Elefesys/ai-service-manager/blob/7e5cbc1f5caeaafa507de0c4cfd7dee7c4ee6455/tests/test_m3_2_escalations_postgres.py#L265).
- **C8-M5-05 · CLOSED.** Два опубликованных источника вызвали
  `OWNER_LABEL_CONFLICT`. Штатный v7 worker из корректного
  `FAQ_ONLY / service_id=null` сформировал owner handoff. При начатом
  intake сохранились услуга, факты и provenance. List вернул одну
  `PENDING` карточку. Read подтвердил нужные Client/Conversation/assignee
  и вопрос текущего хода. Повтор сохранил тот же ID. Новые OUTBOUND
  Message, Outbox, photo intent и вызовы транспорта — 0. Пустой intake
  также передан мастеру, обычный FAQ дал reply. Отзыв до COMMIT и
  чужой claim отклонены. Текст из входящих сообщений хода ограничен
  300 символами. List/read проверяют права владельца и актуальность
  карточки и её intake pin. Вывод вопроса текущего хода в Console
  сверён по существующему компоненту. Браузерный CI подтверждает
  прежний сценарий intake-карточки на desktop и narrow.
  [Сценарии FAQ](https://github.com/Elefesys/ai-service-manager/blob/7e5cbc1f5caeaafa507de0c4cfd7dee7c4ee6455/tests/test_m5_intake_v7_integration_postgres.py#L272) · [Отказы COMMIT](https://github.com/Elefesys/ai-service-manager/blob/7e5cbc1f5caeaafa507de0c4cfd7dee7c4ee6455/tests/test_m5_intake_v7_integration_postgres.py#L331) · [Проверка актуальности и scope](https://github.com/Elefesys/ai-service-manager/blob/7e5cbc1f5caeaafa507de0c4cfd7dee7c4ee6455/migrations/versions/0024_intake_v7_repair.py#L699) ·
  [Console](https://github.com/Elefesys/ai-service-manager/blob/7e5cbc1f5caeaafa507de0c4cfd7dee7c4ee6455/frontend/src/EscalationsPanel.tsx#L142).
- Прежние миграции 0001–0023 сохранены. Сверены 321 функция и их права,
  73 таблицы, profile `33fbfcc9e3c09021ea7bc38de857706a8f23270d7c1dcd79d55ed20f3a5b63c0`
  и verifier body pin установленной 0024. Fresh/populated upgrade,
  повторный upgrade, downgrade пустой схемы, отказ used downgrade и
  сохранность PENDING/UNKNOWN подтверждены CI. Проверка использует
  завершённый CI и локальную сверку его артефактов и исходников.
  [Миграция на заполненной БД](https://github.com/Elefesys/ai-service-manager/blob/7e5cbc1f5caeaafa507de0c4cfd7dee7c4ee6455/tests/test_m5_intake_v7_repair_migrations.py#L154).

**Дальше.** C0 может передать владельцу PR #54 на решение о слиянии.
Принятие M5 следует за проверенным push/main CI. Область решения —
synthetic LOCAL/TEST, default OFF/FAKE/EVAL_ONLY. Live-ограничения в §7.

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

C8 закрыл 01–03 в R2, затем проверил исправления 04 и 05 на `7e5cbc1f5caeaafa507de0c4cfd7dee7c4ee6455`. C0 принял итог R3 по K01–K12. PR #54 готов к слиянию владельцем. Завершение M5 и передача M6 следуют за проверкой фактического `push/main`. [Итог C8](https://github.com/Elefesys/ai-service-manager/blob/06d77019ca3d4a59e3a3b25787a98bab0a37f22d/docs/tasks/M5_HANDOFF.md#L27) · [CI кандидата](https://github.com/Elefesys/ai-service-manager/actions/runs/44359814084).

Отдельно перечислить, какие реальные Vision/embedding/Telegram проверки выполнены,
какие требуют владельца. LOCAL/TEST VERIFIED не равен готовности реального бизнеса.
При непроверенном реальном Vision route честный статус соответствующего среза —
REVIEW/BLOCKED по точной причине, а не автоматическое VERIFIED всего функционала.

## 4. Одна приёмочная матрица

**Итог C8 R3 — PASS для C0 по K01–K12 в synthetic LOCAL/TEST.** K03 и K10
перепроверены на PR #54 head `7e5cbc1f5caeaafa507de0c4cfd7dee7c4ee6455`, tested merge
`5244a3be1caeb4ed1ebbe2ec368e9511ec876958` с тем же деревом. [CI 44359814084](https://github.com/Elefesys/ai-service-manager/actions/runs/44359814084).

Остальные строки сохраняют результаты [C8 R2, §4](https://github.com/Elefesys/ai-service-manager/blob/d2af1c5f8d51590ff354ee21db2b4648a9042d04/docs/tasks/M5_HANDOFF.md#L381) для head
`9ead66496b37d78d35654c9a7b32ee66d1b30a7a` и tested merge
`e356b49ebaca589d2d221b06762c0cf3ae6b26c0`. Дельта R3 затрагивает
согласование блокировок и привязку FAQ handoff. В новом CI подтверждены
связанные проверки. В том числе отзыв, UNKNOWN/no-resend, один QUERY и
одна отправка оригинала из MinIO, четыре явных выбора intake, границы
MODEL/READ/FOLLOWUP и новая observation после Resume. Для K12 сохранён
допуск источников на точное дерево и проверен профиль 0024. Остаток по
конкуренции, отмеченный в R2, закрыт в K10 R3. [Core](https://github.com/Elefesys/ai-service-manager/actions/runs/44359814084/artifacts/14459173205) ·
[Runtime](https://github.com/Elefesys/ai-service-manager/actions/runs/44359814084/artifacts/14454976346).

| ID | Сценарий / обязательный результат | Проверенная граница и вердикт C8 |
|---|---|---|
| K01 | Draft, explicit publish/rollback и replay | **PASS.** Core PG/owner API сохраняет изоляцию draft, CAS 200/409, точный replay и rollback с ростом activation. UI отдельно проверяет, что недопустимое изменение оставляет active прежним. [API CAS](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/tests/test_m5_configuration_api_postgres.py#L148), [rollback и отзыв](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/tests/test_m5_configuration_postgres.py#L196), [Ошибка draft](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/frontend/e2e/configuration.spec.ts#L59) |
| K02 | Одинаковый вопрос, опубликованные ответы двух бизнесов | **PASS в synthetic scope.** Две проекции принадлежности Business проходят в Runtime, обычный FAQ даёт один effect на схеме кандидата. Путь v3 и выбор по publication pin сохранились, результат одинакового input с разными FAQ из R1 применим. [Два Workspace](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/tests/test_m5_knowledge_postgres.py#L347), [Фактический reply](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/tests/test_m5_knowledge_runtime_postgres.py#L111), [Проба R1](https://github.com/Elefesys/ai-service-manager/blob/4cb6318f008d3ca952eb077268887e2d39714972/docs/tasks/M5_HANDOFF.md#L84) |
| K03 | Missing/conflict, уточнение/handoff и source trace | **PASS R3 в synthetic scope.** Ранее проверены durable refs и обычное уточнение. Два опубликованных противоречивых источника дают одну PENDING-карточку с вопросом текущего хода, действующей услугой, сохранёнными полями и их provenance при уже начатом intake. Ноль отправок и повторных карточек. Пустой intake даёт handoff, обычный FAQ — reply. Отзыв источника и чужая привязка отклонены. [Предыдущее уточнение](https://github.com/Elefesys/ai-service-manager/blob/7e5cbc1f5caeaafa507de0c4cfd7dee7c4ee6455/tests/test_m5_intake_v7_integration_postgres.py#L792) · [Worker и Action Center](https://github.com/Elefesys/ai-service-manager/blob/7e5cbc1f5caeaafa507de0c4cfd7dee7c4ee6455/tests/test_m5_intake_v7_integration_postgres.py#L272) · [Отказы COMMIT](https://github.com/Elefesys/ai-service-manager/blob/7e5cbc1f5caeaafa507de0c4cfd7dee7c4ee6455/tests/test_m5_intake_v7_integration_postgres.py#L331) |
| K04 | Publish/revoke, pending reply, UNKNOWN/restart | **PASS для проверенной доставки.** v7 revoke/publish/HUMAN и EDIT/DELETE после READ прекращают выбор до COMMIT. Отзыв до или после private GET даёт 0 отправок. При потере ACK после фиксации DISPATCHING restart оставляет UNKNOWN с 0 повторных эффектов, даже при replay исходного claim. [Смена authority](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/tests/test_m5_intake_v7_integration_postgres.py#L424), [EDIT/DELETE](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/tests/test_m5_intake_v7_integration_postgres.py#L704), [До/после GET](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/tests/test_m5_intake_v7_integration_postgres.py#L443), [UNKNOWN после restart](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/tests/test_m5_intake_v7_integration_postgres.py#L465) |
| K05 | Shared publication и изоляция другого Client/Business/Workspace | **PASS в synthetic scope.** Runtime проверил общую публикацию и разный private context двух клиентов. Core отклоняет чужой intake source в том же и другом Workspace, v7 исключает чужие метки из MODEL/READ/FOLLOWUP. Private GET проверяет Business и owner после чтения. [Два клиента](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/tests/test_m5_knowledge_runtime_postgres.py#L148), [Чужой intake source](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/tests/test_m5_intake_postgres.py#L373), [Model payload и scope](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/tests/test_m5_intake_v7_integration_postgres.py#L522), [Owner после S3 GET](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/tests/test_m5_portfolio_api_postgres.py#L564), [Чужой Business](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/tests/test_m5_portfolio_storage_postgres.py#L123) |
| K06 | Compatible embeddings, relevance, empty и плохой rebuild | **PASS в synthetic scope.** Core PG v7 с непустыми KB и MY_WORK делает один scoped QUERY, replay тот же. Пустая выдача — без резерва. Exact vector/keyword/empty и сохранение active при плохом rebuild также прошли. Real embedding capability 3×1536/cosine/relevance взята из принятого ASSISTED_SYNTHETIC. [Один QUERY](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/tests/test_m5_intake_v7_integration_postgres.py#L249), [Повтор](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/tests/test_m5_intake_v7_integration_postgres.py#L388), [EMPTY](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/migrations/versions/0024_intake_v7_repair.py#L858), [Exact vector/keyword](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/tests/test_m5_knowledge_search_runtime_postgres.py#L287), [Плохой rebuild](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/tests/test_m5_knowledge_search_api_postgres.py#L597), [Probe PR48](https://github.com/Elefesys/ai-service-manager/pull/48#issuecomment-6876443802) |
| K07 | Приватные pixels, UNKNOWN scale и границы Vision | **PASS для synthetic capability.** Текущий анализ с exact file/hash входит в v7 worker. Core тесты подтверждают decodable S3 bytes в MockTransport, schema/tool limits и отсутствие подстановки старого ready после unavailable. Три ASSISTED_SYNTHETIC samples сохраняют историческую границу. Price, time и eligibility остаются бизнесовыми решениями. [Актуальный анализ](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/tests/test_m5_intake_v7_integration_postgres.py#L232), [S3 pixels](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/tests/test_m5_portfolio_storage_postgres.py#L70), [Схема Vision](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/tests/test_m5_vision_pixels.py#L192), [Unavailable](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/tests/test_m5_portfolio_runtime_postgres.py#L670), [Probe PR48](https://github.com/Elefesys/ai-service-manager/pull/48#issuecomment-6876443802) |
| K08 | Подтверждённая MY_WORK, reference и отзыв | **PASS.** Проверены immutable origin, подтверждённая revision, show permission, совместная публикация и отзыв до отправки. В Chromium сохранены owner upload/review/delete через private S3 и отзыв preview. [Происхождение](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/tests/test_m5_portfolio_postgres.py#L301), [Build](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/tests/test_m5_portfolio_postgres.py#L415), [Выбранный MY_WORK](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/tests/test_m5_intake_v7_integration_postgres.py#L265), [Private S3](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/frontend/e2e/portfolio.spec.ts#L111), [Отозванный preview](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/frontend/e2e/portfolio-delivery.spec.ts#L42) |
| K09 | Одно разрешённое фото, rights и видимость результата | **PASS в synthetic scope.** Один actual PG v7 worker прошёл QUERY→MODEL→READ/attestation→FOLLOWUP→COMMIT→private MinIO GET→SEND. Совпали SHA оригинала и caption, по одному intent/Message/Outbox/QUERY/effect. Четыре отличающихся refs отвергнуты при проверке результата и отдельно на SQL COMMIT. Telegram MockTransport проверил оба fresh rights наблюдения и 0 sendPhoto при отказе. [MinIO и 1 effect](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/tests/test_m5_intake_v7_integration_postgres.py#L227), [COMMIT rejects](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/tests/test_m5_intake_v7_integration_postgres.py#L878), [Telegram MockTransport](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/tests/test_m5_intake_v7_integration_postgres.py#L754), [SENT/UNKNOWN в UI](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/frontend/e2e/portfolio-delivery.spec.ts#L42) |
| K10 | Progressive intake/correction, COVER_UP, private DurationCase | **PASS R3.** Подтверждены все четыре варианта явного выбора с переиспользованием исходного подтверждения, когда выбран тот же owner-confirmed факт. Три конкурентных PG теста подтвердили ожидание CONFIGURATION_V1 и последовательное завершение READ / CONFIRM / RESOLVE. При PENDING stale worker отклонён, сохранены ID, адресат, проверки CAS/источника и идемпотентность. DurationCase остаётся owner-only. [Явный выбор](https://github.com/Elefesys/ai-service-manager/blob/7e5cbc1f5caeaafa507de0c4cfd7dee7c4ee6455/tests/test_m5_intake_v7_integration_postgres.py#L792) · [Три конкурентных теста](https://github.com/Elefesys/ai-service-manager/blob/7e5cbc1f5caeaafa507de0c4cfd7dee7c4ee6455/tests/test_m5_intake_postgres.py#L318) · [Карточка и CAS](https://github.com/Elefesys/ai-service-manager/blob/7e5cbc1f5caeaafa507de0c4cfd7dee7c4ee6455/tests/test_m5_intake_postgres.py#L213) · [Private DurationCase](https://github.com/Elefesys/ai-service-manager/blob/7e5cbc1f5caeaafa507de0c4cfd7dee7c4ee6455/tests/test_m5_duration_cases_postgres.py#L22) |
| K11 | Owner review/publish/revoke в Console, понятные ошибки | **PASS.** Оба проекта Chromium прошли сохранение невалидного черновика, сообщение об ошибке, disabled Publish и неизменный active. Те же проекты проверили публикацию/отзыв источника, обновление той же карточки и разрешённое внутреннее решение мастера. [Невалидный draft](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/frontend/e2e/configuration.spec.ts#L59), [Отзыв](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/frontend/e2e/configuration.spec.ts#L125), [Та же карточка](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/frontend/e2e/intake-duration.spec.ts#L45), [Отчёт Chromium](https://github.com/Elefesys/ai-service-manager/actions/runs/44337635508/artifacts/14442299492) |
| K12 | HUMAN/Resume, reconciliation, history и source gates | **PASS для проверенных границ контекста и data gate.** Actual PG v7 проверил сериализацию MODEL/READ/FOLLOWUP для OFF_UNUSED и native, исключение старых и чужих цитат, разрешённую bounded history, TAKEOVER и новый reconciled Resume с другой revision/observation. Свежий v7 ход дошёл до COMMIT; SEND проверен в K09. 0024 прошла fresh/populated upgrade, repeat, unused downgrade и отказ used downgrade/drift. SQL profile 321 функций/73 таблицы, сохранены факты, PENDING и UNKNOWN. Проверены scope и точное tested tree. Риск конкурентной сериализации принятия решения закреплён в K10. [History/quotes](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/tests/test_m5_intake_v7_integration_postgres.py#L522), [Takeover и Resume](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/tests/test_m5_intake_v7_integration_postgres.py#L823), [Профили и заполненная БД](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/tests/test_m5_intake_v7_repair_migrations.py#L94), [Допуск исходников](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/scripts/m4_runtime_db.py#L1665), [Runtime](https://github.com/Elefesys/ai-service-manager/actions/runs/44337635508/artifacts/14442513168) |

Fixtures A/B проверены через одинаковый owner API. C/D находятся в synthetic
fixtures. Согласованные режимы и unknown подтверждены для конфигурации.
[Owner API](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/tests/test_m5_configuration_api_postgres.py#L95),
[Независимые policies](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/tests/test_m5_configuration.py#L13),
[A–D fixtures](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/tests/fixtures/businesses.v1.json#L1).

## 5. Правила выдачи и инженерные ограничения

В каждом задании C0 указывает ID, продуктовый результат, полный base SHA, branch,
одного ведущего, exact write-set, dependency, критерии и что оставлено за границей.
Не выдавать весь этот документ C1/C4 как одно задание «реализовать M5».

M5.1A–M5.3A интегрированы. На принятом main действует 0023. В рассматриваемом PR #54 добавлена 0024 с родителем 0023. Итоговое заключение C8 принято C0 по проверенному head PR #54.

Не менять applied0001–0023, роли/гранты всех старых модулей, исторические schema
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

Владелец сливает [PR #54](https://github.com/Elefesys/ai-service-manager/pull/54) через `Create a merge commit`. C0 проверяет фактический `main` и его штатный CI после слияния.

Позже — только конкретное действие по готовому результату:
1. Если понадобится дополнительный real synthetic smoke — отдельные route,
   точные запросы, предел расходов и процедура остановки перед допуском владельца.
   Принятый M5.2A probe заново не запускать.
2. VM/Telegram smoke — отдельный допуск и проверка относящихся к нему receiver
   ограничений; прежние команды не переиспользовать вслепую.
3. Перед реальным бизнесом — подтверждение правил, прав на материалы и data route.
4. Merge нового PR — отдельное действие владельца после C0 review/CI.

## 7. Передача M6

Контракты R2 сверены с дельтой PR #54 head `7e5cbc1f5caeaafa507de0c4cfd7dee7c4ee6455`.
Независимое review R3 завершено **PASS для C0**, C8-M5-04 и C8-M5-05 закрыты.
C0 принял это заключение по текущему кандидату. Передача M6 следует за слиянием
владельцем и приёмкой M5 по фактическому `push/main` CI.

- `configuration` и owner API `/configuration` возвращают `ActiveProjection`
  schema v1. `Service.id`, `Rule.id` и `Rule.service_id` принадлежат bundle
  в рамках Business и immutable `release_id`. `draft_version` нужен для
  EDIT/PUBLISH CAS. `activation_version` увеличивается при publish/rollback
  и инвалидирующих операциях. Запрос к старому release не даёт текущей authority.
  `tattoo_intake_v1` привязан к опубликованному списку field IDs и required,
  включая optional `references`. Price/duration/deposit проверяются отдельно.
  [bundle и policy IDs](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/backend/src/asm/configuration/models.py#L63), [release и CAS](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/backend/src/asm/configuration/models.py#L147), [template](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/backend/src/asm/intake/templates.py#L5).
- `knowledge` и `portfolio` имеют раздельные paths/API. Authorization связывает
  release/activation и build с Workspace/Business. Knowledge содержит
  `source_id/revision_id/chunk_id/sha256`, owner confirmation и effective window.
  Portfolio содержит `item_id/revision_id/asset_version_id/source_sha256`,
  MY_WORK и show permission. `current_image_v1` закрепляет текущие
  Client/Conversation/message/file/version/hash и optional analysis id/hash.
  Перед чтением байтов и отправкой действуют частные permits и новые проверки.
  Отзыв прекращает доступ к этому источнику. Разрешённая работа или наблюдение
  Vision не даёт решения о цене, времени или допустимости запроса.
  [knowledge source/build](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/backend/src/asm/knowledge/models.py#L119), [portfolio/media pins](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/backend/src/asm/ai/portfolio.py#L59), [private GET](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/backend/src/asm/portfolio/delivery.py#L121).
- `intake` и owner API `/intake/conversations/{conversation_id}` возвращают
  `preliminary_intake_v1` со scope, service/template/release/activation,
  control/context versions и version/fingerprint для owner `CONFIRM/CORRECT`.
  `conversation_v7` / `conversation_result_v3` предлагают candidate facts и
  один outcome через существующий worker. Статусы `client-stated`, `observed`,
  `owner-confirmed` и missing/conflict несут provenance `message_id/source_version`
  с optional analysis id/hash. Проверять source и актуальность в транзакции.
  `PRELIMINARILY_COMPLETE` означает, что известны поля шаблона на текущих
  источниках. Совместимая активация сохраняет факт после сверки service/template
  и подтверждённой версии источника. При явном выборе прежнего owner-confirmed
  значения уточнение хранится в принятом `ai_runs.result`, а источник
  подтверждённого факта сохраняется. Запреты из истории видны на MODEL/READ/FOLLOWUP,
  полная owner-проекция доступна по отдельной авторизации.
  [Currentness факта и template](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/migrations/versions/0024_intake_v7_repair.py#L795), [Привязка уточнения](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/tests/test_m5_intake_v7_integration_postgres.py#L668),
  [DTO и owner CAS](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/backend/src/asm/intake/models.py#L18), [входы API](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/backend/src/asm/intake/http.py#L39), [result v3](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/backend/src/asm/ai/contracts.py#L296).
- Action Center использует `escalation_id` и `PRELIMINARY_INTAKE_OWNER_V1`
  через прежние list/read/resolve/cancel API. Summary потребляет current pin,
  команда владельца сохраняет версионированное внутреннее решение/receipt.
  При подтверждении/коррекции поля той же актуальной карточки обновляются summary
  и conversation CAS. ID и адресат сохраняются. READ, CONFIRM и RESOLVE
  сериализуются с worker через lock конфигурации. При конфликте опубликованных
  FAQ карточка содержит текущий вопрос, действующую услугу и проверенные
  сведения с provenance. Вопрос из хода показывается при действующей
  привязке карточки. [Правила чтения Action Center](https://github.com/Elefesys/ai-service-manager/blob/7e5cbc1f5caeaafa507de0c4cfd7dee7c4ee6455/migrations/versions/0024_intake_v7_repair.py#L699).
  Отдельные поля подтверждаются в Intake. `DurationCase` имеет
  `case_id/version/state/source_current`, optional exact asset/version и
  working/occupied minutes с unknown. CRUD/confirm/revoke/search owner-only.
  Comparison возвращает до пяти подтверждённых и действительных примеров
  по placement/style/detail/fill, с совпадениями, различиями и unknown.
  Данные остаются справочными для мастера. [Обновление карточки и CAS](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/migrations/versions/0024_intake_v7_repair.py#L742),
  [escalation contract](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/backend/src/asm/conversations/escalation_http_models.py#L164), [DurationCase DTO](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/backend/src/asm/intake/models.py#L104), [сравнение](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/backend/src/asm/intake/duration_cases.py#L6).

**Минимальный следующий срез для решения C0.** После принятия M5
проверить транзакционный перенос одного актуального intake в
черновой ServiceRequest с provenance и idempotency. В M6 владелец или принятая
детерминированная policy смогут утверждать Assessment. Порядок Quote/Order,
записи и оплаты следует своим этапам. OPEN-080/081 сохраняют вопросы
о конкретных временах мастера, границах сессий и калибровке. [OPEN-080/081](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/docs/architecture/04_OPEN_QUESTIONS.md#L441).

**Открыто для live.** Receiver ACK/fence и полный live HUMAN/Resume остаются
OPEN_OPERATIONAL. `MEDIA_REPLACED_UNAVAILABLE` сохраняет недоступность
заменённых bytes. Production provider/data route, разрешение обработки
клиентских материалов и реальный client-runtime E2E не подтверждены.
IMPL-005 принимает существующие owner-reported synthetic Vision и embedding
receipts. Исходные UNKNOWN/NOT_PROVEN и учёт confirmed 0.50229415 RUB /
holds 11.75 RUB сохранены. На этом review использованы только DEFAULT_OFF /
FAKE / EVAL_ONLY, реальные provider/Telegram/VM вызовы отсутствовали.
[Решение IMPL-005](https://github.com/Elefesys/ai-service-manager/blob/3ba774da3bf61b57062098ea5e0470b1402eb70d/docs/decisions/IMPL-005-m5-pilot-knowledge.md),
[embedding history](https://github.com/Elefesys/ai-service-manager/pull/48#issuecomment-6877156327).
