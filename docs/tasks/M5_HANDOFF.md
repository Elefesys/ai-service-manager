# M5 — настройки бизнеса, знания, Vision и портфолио

Статус исполнения — в [TASK_REGISTER](../TASK_REGISTER.md).
Решение по объёму — [IMPL-005](../decisions/IMPL-005-m5-pilot-knowledge.md),
ACCEPTED / LOCKED C0.

## CURRENT — C4-M5.2C-FOUNDATION-BUDGET-R1 / IN_PROGRESS / 2026-11-16

**Единственная активная выдача — ограниченное исправление CI, ведущий C4.**
M5.2C/PR #50 слит; полная проверка после интеграции пока BLOCKED по CI budget.
C6 HOLD; M5.2D и M5.3 не выдаются до закрытия этого gate.

### Результат и основание

Штатный foundation должен завершить все тесты, миграционные проверки,
контракты, воспроизводимость сборки и owned cleanup в конечном лимите времени.
Это необходимо для достоверной post-merge приёмки уже реализованного M5.2C.
Новый продуктовый scope не вводится; деление CI на дополнительные jobs,
ускорение/переписывание тестов и изменение архитектуры не входят в задачу.

- Repository: `Elefesys/ai-service-manager`; новая ветка `c4/m5-2c-foundation-budget-r1`;
  один новый Draft PR в `main`. PR #50 уже закрыт; старую ветку не продолжать.
- **Фактический application base: `84ad8e4c954005801f115aa8e6c0c6f7edef40db`.**
  Tree: `bf8992e20260e56f8d84884fc65fa3febcafc053`.
  Merge parents: `70804866f6838f77c12bd281febae47887559d75` +
  `da2a6e62a3455241d21b25fbb7e9ef1b33f5cb02`.
  Это точный reviewed candidate tree; использование base для CI fix не означает
  закрытую post-merge верификацию.
- C0 сохраняет docs-only assignment поверх этого base в новой ветке.
  Exact assignment SHA/tree взять из закреплённой ссылки и Git, сохранить в ancestry.
- [Принятая реализация и review C0](https://github.com/Elefesys/ai-service-manager/blob/c132213302daeeaa4f9309d6352841fe99d6da8e/docs/tasks/M5_HANDOFF.md#L803).
  [Исходный контракт M5.2C](https://github.com/Elefesys/ai-service-manager/blob/2775e0d8a6f8a3858b40417bd77ea99eeaf3efce/docs/tasks/M5_HANDOFF.md).
  История прежних выдач остаётся по этим ссылкам; её длинные receipts здесь не повторяются.

### Диагноз C0 — CI 43800096544

[Push/main run](https://github.com/Elefesys/ai-service-manager/actions/runs/43800096544),
attempt 1: **11 SUCCESS / foundation CANCELLED**.
Foundation job 133083153248 начался 04:02:49Z, завершился 04:48:06Z;
в workflow установлен `jobs.foundation.timeout-minutes: 45`.
Generic PostgreSQL продолжал проходить тесты до остановки; в логе
`The operation was canceled`, затем completeness gate правильно отказал
`FOUNDATION_EVIDENCE_REFUSED`.

C0 скачал artifact 14198940375 и сверил ZIP SHA256
`175f6b05d2fce548118de4d06c013d67e2540193be61c2b768d88282e20db813`.
Source archive и binding всех 438 files/bytes/Git blobs/modes совпадают с
проверенным candidate, tracked/untracked source чист. Доказано:

- unit 4443 PASS, 161 subtests PASS; unit phase 659.72s вместо 538.30s в PR CI;
- из 1016 actual generic PG cases 966 имеют полные start/setup/call/teardown/end
  PASS, без xfail; 9 actual S3 API и 38 v5 runtime cases входят в эти 966;
- case 967 `TestEgressMaterialCompatibility::test_used_0012_refuses_before_ddl_and_preserves_all42[invalidated-turn]`
  имеет start/setup PASS, но нет завершения call/teardown; ещё 49 не начаты;
- одинаковые 966 cases заняли 1913.96s вместо 1688.81s (+13.3%).
  Рост распределён по выполнению; конкретная причина различия скорости runner
  не установлена. Ни assertion failure, ни один зависший case не доказаны;
- generic-result/execution пусты; generic end, downgrade/reupgrade/contracts,
  wheels и owned cleanup не подтверждены. Не считать их PASS по прежнему PR.
  Остальные 11 jobs прошли; повторять их отдельно не требуется.

Предыдущий [PR CI43791099844](https://github.com/Elefesys/ai-service-manager/actions/runs/43791099844)
остаётся настоящим 12/12 SUCCESS / attempt 1 на том же code tree. Новый отказ —
достижение общего job budget, не изменение expected/schema либо обнаруженное
падение application test. 45 минут недостаточно как устойчивый верхний предел
для выросшего последовательного набора.

### Принятое техническое решение C0

**ACCEPTED FOR IMPLEMENTATION: только foundation job timeout 45→60 минут.**
Это конечный предел всей TEST job с запасом к наблюдённым 40–45+ минутам,
а не разрешение продлить product/provider/SQL deadlines.
60 минут повторно не повышать без нового разбора C0.
Browser cap 900 / per-test 30 / workers 1 / retries 0, остальные job budgets,
application/generic PG test inventory,
assertions, skips/xfails, phase/cleanup/error semantics и workflow triggers
сохраняются. Не запускать повтор старого cancelled run ради случайного PASS.

### Разрешённые paths и точный объём

1. `.github/workflows/ci.yml`: ровно одна строка
   `jobs.foundation.timeout-minutes: 45 → 60`.
   Другие jobs, needs, steps, triggers, permissions, concurrency, image/action pins
   и reusable workflow calls оставить побайтово прежними.
2. `scripts/native_context_db_catalog.py`: пересчитать только текущий точный
   `CI_INPUT_SHA256[".github/workflows/ci.yml"]` по изменённому файлу.
   Остальные CI input pins, schemas, catalog/evidence/phase/cleanup/event guards
   и fingerprint алгоритмы неизменны.
3. `tests/test_native_context_db_runner.py`: синхронизировать существующее
   утверждение foundation budget с принятым 60; сохранить проверки всех остальных
   jobs и exact CI-input drift отказов. Не переписывать исторические SQL profiles.
4. `scripts/m4_runtime_db.py`: добавить только узкий source admission этой
   новой задачи/ветки и её обычного post-merge main пути.
   Base SHA/tree — выше; docs assignment SHA/tree/parent/ancestry должны проверяться.
   Diff от фактического base разрешает ровно 5 implementation paths из этого списка
   и 5 C0 assignment docs (AGENTS/README/TASK_REGISTER/IMPL-005/M5_HANDOFF).
   Первые 4 docs — immutable после assignment; только короткий возврат в handoff.
   Учесть producer/validator persisted source identity и actual PR base; старый
   M5.2C admission закреплён на 7080486 и автоматически новую ветку не допускает.
   Переиспользовать существующие проверки, не строить новый admission engine.
   Старые branches/assignments/base pins/closed refusals не переопределять;
   глобальный M5_PORTFOLIO_PATHS ради нового workflow не расширять.
5. `tests/test_m4_runtime_db_runner.py`: целевые проверки этого admission:
   actual-Git positive для exact branch/base/assignment, main descendant и
   persisted proof; wrong branch/base/tree/parent, protected-doc drift,
   neighbouring application/workflow path должны отказать до ресурсов.
   Старые negative fixtures и прошлые task boundaries сохраняются.
6. `docs/tasks/M5_HANDOFF.md`: короткий итог C4 — SHA/tree/PR/CI, фактические
   targeted results и ограничения. Логи и case journals оставить в artifacts.

Backend/frontend application, tests/*.py вне двух перечисленных runner modules,
миграции 0001–0021, зависимости/locks, compose/storage/Telegram и исходная
архитектура закрыты для изменений. Новый migration slot не нужен.
Обнаруженный настоящий application defect вернуть с точным reproducer C0;
этим CI fix его не маскировать.

### Порядок выполнения и готовность

1. Прочитать AGENTS/CURRENT/IMPL-005, проверить base и чистый отдельный checkout.
   Применить одну workflow-строку, exact hash и минимальный admission.
2. До открытия PR: затронутые runner checks, сохранение exact отрицательных
   отказов, phase/cleanup/exit-preservation проверки, Ruff/format/diff.
   Проверить YAML и сравнить workflow: только один scalar 45→60.
   В LOCAL admission использовать настоящий Git и честно обозначенную synthetic
   event metadata; не выдавать его за Actions evidence.
3. Затем один push полного кандидата и один новый Draft PR/штатный full CI.
   Нужны 12/12 SUCCESS, весь generic inventory 1016 без skips и все 14 backend
   phases, primary/owned cleanup 0, source clean, complete evidence.
   Отдельный unchanged full rerun старого source не запускать.
4. Вернуть C0 точные durations build/unit/generic/whole-job отдельно.
   При timeout 60 или ином падении разобрать весь известный набор причин и вернуть
   evidence; новый рост timeout/skip/retry без C0 не делать.
5. После C0 review требуется отдельный owner merge нового PR, затем штатный
   push/main CI. Только после зелёной приёмки исправленного main C0 закрывает
   M5.2C verification и выдаёт M5.2D ведущему C3.

Новых paid/VM/client-data допусков нет. Default Vision/embedding DISABLED,
CONTROLLED exact MockTransport/EVAL_ONLY, исходные UNKNOWN/holds, receiver
ACK/fence и полный live HUMAN/Resume сохраняются. C6/operator HOLD.

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
