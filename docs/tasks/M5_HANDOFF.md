# M5 — настройки бизнеса, знания, Vision и портфолио

Статус исполнения — в [TASK_REGISTER](../TASK_REGISTER.md).
Решение по объёму — [IMPL-005](../decisions/IMPL-005-m5-pilot-knowledge.md),
ACCEPTED / LOCKED C0.

## CURRENT — C8-M5.3B-ACCEPTANCE-R2 / REVIEW / 2026-11-18

**C0 → C8. Проведи независимую повторную приёмку [PR #54](https://github.com/Elefesys/ai-service-manager/pull/54) по четырём замечаниям C8 и дай итог по матрице K01–K12.** Проверяем, что клиент получает фото подтверждённой работы, сохраняет прогресс и может явно разрешить противоречие, а мастер может решить уже открытый вопрос.

**Решение C0.** Исправление C1 принято для повторного review. На предыдущем head выбор исходного значения оставлял `conflict=true`. На новом head C0 проверил тот же сценарий штатным Python reducer. В CI на actual PostgreSQL все четыре сочетания исхода и статуса поля дошли до следующего вопроса о месте татуировки. Подтверждение мастера и его исходный источник сохранены при возврате к тому же значению. Точная привязка уточнения есть в результате run. Обычный повтор оставляет конфликт открытым. [Исходный возврат C8](https://github.com/Elefesys/ai-service-manager/blob/4cb6318f008d3ca952eb077268887e2d39714972/docs/tasks/M5_HANDOFF.md#L14) · [остаток, найденный C0](https://github.com/Elefesys/ai-service-manager/blob/24f9439e78c017d4e467ceb6338545aca099471a/docs/tasks/M5_HANDOFF.md#L9) · [worker и проверки результата](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/tests/test_m5_intake_v7_integration_postgres.py#L625).

### Какой код проверять

| Объект | Git identity |
|---|---|
| Принятый application base в `main` · PR #53 | `c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba` · tree `11c987fb12e4f88d27da3737911c468d520269b8` |
| Предыдущий проверенный head PR #54 | `593c9d633b144d149be6699b8228e0d08f0a31ab` |
| **Application head для этого review** | **`9ead66496b37d78d35654c9a7b32ee66d1b30a7a`** · tree **`305dbbe737302680f658e05835f9b5ee82484309`** |
| Проверенный GitHub test merge | `e356b49ebaca589d2d221b06762c0cf3ae6b26c0` · родители в порядке main, application head · то же дерево |
| Рабочая ветка C8 | `c8/m5-3b-acceptance-r2` · стартовый commit с этим CURRENT имеет единственного родителя `9ead66496b37d78d35654c9a7b32ee66d1b30a7a` |

Последний commit C1 изменил пять разрешённых путей. Все 12 jobs завершились SUCCESS с первой попытки. C0 сверил ZIP digest и CRC для core, runtime и browser, все 483 файла и режимы source archive с Git и результаты фазы вызова в `cases.jsonl` для четырёх intake-комбинаций, фото с MinIO, UNKNOWN/restart и обеих политик history. Runtime дал 160/160, Chromium 73/73. Установленная 0024 совпала с каталогом из исходников, включая 321 функцию и 73 таблицы. [CI 44337635508](https://github.com/Elefesys/ai-service-manager/actions/runs/44337635508) · [core](https://github.com/Elefesys/ai-service-manager/actions/runs/44337635508/artifacts/14446459123) · [runtime](https://github.com/Elefesys/ai-service-manager/actions/runs/44337635508/artifacts/14442513168) · [Chromium](https://github.com/Elefesys/ai-service-manager/actions/runs/44337635508/artifacts/14442299492).

### Границы и критерии C8

Единственный ведущий — C8. C1 завершил доработку. Объект проверки — application head выше. Изучай исходники из отдельного чистого checkout этого SHA или из сверенного source archive. В ветке `c8/m5-3b-acceptance-r2` разрешён один файл — `docs/tasks/M5_HANDOFF.md` для короткого возврата под CURRENT, матрицы §4 и сверки фактических контрактов §7. Документальная выдача C8 находится вне PR #54. Остальные роли на паузе.

1. Сопоставь первоначальные C8-M5-01–04 и критерии последнего возврата C0 с кодом и наблюдаемыми результатами текущего CI. Для каждого замечания укажи CLOSED либо OPEN с причиной. Для K03/K06/K09 проверь непустой индекс, один общий QUERY в сессии v7, стабильный READ с attestation, точный выбор, оригинал MinIO и один контролируемый SEND с подписью. Сверь, где проверяются права и версия источника до COMMIT, private GET и wire. Для K04 проверь отзыв и UNKNOWN с нулём повторных отправок.
2. Для K10 проверь обычный повтор, неоднозначность и явный выбор каждого варианта, в том числе после подтверждения мастером. Нужны сохранённые поля и источники, фактически отправленный следующий вопрос и отсутствие новых эффектов при replay. Сверь повторную публикацию/rollback, EDIT/DELETE и порядок COVER_UP → открытая карточка → подтверждение поля → та же карточка → RESOLVE. Для K11 сопоставь ошибки некорректного черновика и сценарий мастера с desktop/narrow browser evidence.
3. Для K12 проверь содержимое MODEL, READ и FOLLOWUP в пределах текущего turn и разрешённой истории, включая source quotes. Сохраняются tenant/client scope, OWNER reconciliation, observation barrier, HUMAN/Resume, права Telegram и ограничения бюджета. Проверь связь actual SQL 0024 с предыдущей 0023, сохранение PENDING/UNKNOWN и допуск проверенного дерева. [Контрольные сценарии v7](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/tests/test_m5_intake_v7_integration_postgres.py) · [миграция на заполненной БД](https://github.com/Elefesys/ai-service-manager/blob/9ead66496b37d78d35654c9a7b32ee66d1b30a7a/tests/test_m5_intake_v7_repair_migrations.py).
4. Обнови все 12 строк §4 для указанного кандидата. Для ранее прошедших K01/K02/K05/K07/K08 достаточно проверить применимость прежнего evidence к изменившимся путям и дать ссылки. Сохрани границы PG, MinIO, controlled Telegram, FAKE и ранее принятого ASSISTED_SYNTHETIC. Укажи пробел отдельно, если он меняет решение. Используй завершённый CI. При конкретной нехватке доказательств допустима точечная локальная синтетическая проверка.
5. В §7 сверь контракты передачи M6 и перечисли оставшиеся live-ограничения. В возврате укажи head/tree/tested merge, решение **PASS для C0** или **CHANGES_REQUESTED**, четыре исхода по замечаниям и ссылку на обновлённую матрицу. Для открытого замечания приложи ожидаемое и наблюдаемое поведение, точный путь и границу проверки. Верни C0 одну закреплённую ссылку на результат в своей ветке. При смене application head укажи SHA, к которому относится заключение.

Проверка ограничена synthetic LOCAL/TEST. Default OFF/FAKE/EVAL_ONLY, прежние UNKNOWN/NOT_PROVEN и holds, receiver ACK/fence, полный live HUMAN/Resume и ограничения обработки реальных материалов действуют. Операторские действия и платные вызовы требуют отдельного допуска. PR #54 остаётся Draft до решения C0 по возврату C8. После независимого review вопрос о merge решается отдельно с владельцем. Общая приёмка M5 учитывает фактический push/main CI после слияния.

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

Первичный review C8 выявил четыре замечания на принятом main. C1 вернул исправленный кандидат PR #54. После полного CI и проверки C0 активна независимая повторная приёмка C8. Затем C0 решает вопрос о готовности к интеграции. Владелец отдельно разрешает merge, а C0 проверяет фактический push/main CI и обновляет статус M5 и передачу M6.

Отдельно перечислить, какие реальные Vision/embedding/Telegram проверки выполнены,
какие требуют владельца. LOCAL/TEST VERIFIED не равен готовности реального бизнеса.
При непроверенном реальном Vision route честный статус соответствующего среза —
REVIEW/BLOCKED по точной причине, а не автоматическое VERIFIED всего функционала.

## 4. Одна приёмочная матрица

До возврата C8 таблица ниже сохраняет результаты первичной проверки main `c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba`. Теперь на кандидате PR #54 выполнен единый v7 worker-сценарий. C8 пересматривает строки по CURRENT и привязывает итог к `9ead66496b37d78d35654c9a7b32ee66d1b30a7a`. Первоначальные результаты и ссылки на материалы прежнего main остаются в [отчёте C8](https://github.com/Elefesys/ai-service-manager/blob/4cb6318f008d3ca952eb077268887e2d39714972/docs/tasks/M5_HANDOFF.md#L14).

| ID | Сценарий / обязательный результат | Проверенная граница и вердикт C8 |
|---|---|---|
| K01 | Draft, explicit publish/rollback и replay | **PASS.** Core PG/owner API проверяет draft вне active, конкурентные publish 200/409, replay той же команды без новых записей, rollback с ростом activation. При ошибке валидации/записи и при отзыве исходника остаётся текущий допустимый набор. [API CAS](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m5_configuration_api_postgres.py#L148), [rollback и отзыв](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m5_configuration_postgres.py#L196), [атомарность поздней ошибки](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m5_configuration_postgres.py#L343) |
| K02 | Один вопрос, разные подтверждённые ответы двух бизнесов | **PASS в synthetic scope.** Runtime actual PG закрепляет разные bundles Tattoo/Ceramics за разными Workspace/Business и один обычный source-backed reply. Локальная проба выше подтвердила разный FAQ reply для одинакового input в общем v3 agent. Выбор по trusted Business и publication pin. Live quality за пределом. [две проекции](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m5_knowledge_postgres.py#L347), [ответ и один эффект](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m5_knowledge_runtime_postgres.py#L111), [projection](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/backend/src/asm/ai/knowledge.py#L72) |
| K03 | Missing/conflict, уточнение/handoff и source trace | **CHANGES_REQUESTED для v7.** Core PG v4 проверяет точные source/revision/chunk refs без текста в durable trace и handoff при конфликте до top-four. Core PG v7 без индекса даёт следующий недостающий вопрос. С действующим индексом v7 останавливается до этого поведения по 01. [source refs](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m5_knowledge_search_runtime_postgres.py#L245), [conflict](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m5_knowledge_search_runtime_postgres.py#L327), [v7 clarify](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m5_intake_postgres.py#L184) |
| K04 | Publish/revoke race, pending reply, UNKNOWN/restart | **PASS для проверенных v4–v6, GAP для v7 SEND.** Core PG сериализует publish/revoke, блокирует старый текст до send и хранит UNKNOWN/no-resend. Photo guard после потери authority до/после S3 GET даёт 0 wire effects. Core PG v7 проверяет edit/delete/revert видимых фактов. После ремонта 01/02 нужна v7 проверка от аттестации до send, включая race и restart. [publish/revoke](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m5_knowledge_search_runtime_postgres.py#L825), [UNKNOWN](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m5_knowledge_search_runtime_postgres.py#L579), [до/после GET](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m5_portfolio_delivery_postgres.py#L123), [material versions](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m5_intake_postgres.py#L418) |
| K05 | Общая публикация и изоляция другого Client/Business/Workspace | **PASS для межобъектной изоляции.** Runtime PG показывает двум разным Client одно опубликованное знание; чужой текст отсутствует в обоих model requests. Core PG отклоняет чужой intake source в том же и другом Workspace, два Client получают одну общую допустимую работу по отдельным intents. Owner лишается preview после S3 GET, чужой Business не добирается до GET. [client text](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m5_knowledge_runtime_postgres.py#L148), [intake guard](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m5_intake_postgres.py#L313), [photo scopes](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m5_portfolio_delivery_postgres.py#L341), [preview recheck](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m5_portfolio_api_postgres.py#L564), [private S3](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m5_portfolio_storage_postgres.py#L123) |
| K06 | Compatible embeddings, active после сбоя, relevance и empty | **CHANGES_REQUESTED для v7.** Core PG подтвердил exact vector/keyword/empty, неудачный rebuild оставил активный release. Реальный исторический probe 3×1536/cosine/relevance принят ASSISTED_SYNTHETIC. V7 QUERY с непустым build отклоняется по 01. [PG retrieval](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m5_knowledge_search_runtime_postgres.py#L287), [rebuild failure](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m5_knowledge_search_api_postgres.py#L597), [receipt PR48](https://github.com/Elefesys/ai-service-manager/pull/48#issuecomment-6876443802) |
| K07 | Приватные pixels, UNKNOWN scale и границы полномочий | **PASS для synthetic Vision capability и v5 plumbing.** Core PG/S3 передаёт decodable pixels в MockTransport и закрепляет exact file/hash/analysis. Схема отвергает бизнесовые поля и tool output. Новейшее unavailable фото не подменяется старым ready. Три исторических synthetic samples включают изображение с текстом-инструкцией. Поля `price/time/eligibility` не устанавливаются Vision. Live client route остаётся OPEN. [S3 pixels](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m5_portfolio_storage_postgres.py#L70), [guarded worker](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m5_portfolio_runtime_postgres.py#L383), [schema/tool assertions](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m5_vision_pixels.py#L192), [unavailable](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m5_portfolio_runtime_postgres.py#L670), [Vision receipt](https://github.com/Elefesys/ai-service-manager/pull/48#issuecomment-6876443802) |
| K08 | Подтверждённая MY_WORK, reference и отзыв | **PASS.** Core PG исключает INSPIRATION из подтверждаемого MY_WORK и защищает origin. Совместная публикация содержит только подтверждённые revisions с show permission. Browser с actual private S3 проверяет owner upload/review/revoke/delete, а delivery journey — исчезновение preview отозванного источника. [origin](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m5_portfolio_postgres.py#L301), [опубликованный build](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m5_portfolio_postgres.py#L415), [private owner S3](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/frontend/e2e/portfolio.spec.ts#L111), [withdrawal](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/frontend/e2e/portfolio-delivery.spec.ts#L42) |
| K09 | Одно фото, rights, restart, видимость статуса | **CHANGES_REQUESTED для v7.** Core v6 PG/S3 подтвердил оригинальные bytes и единственный Outbox/wire effect. Mock Telegram сделан через rights probe и final send probe, отказ даёт 0 sendPhoto. Потеря ACK и отмена после учтённого эффекта дают UNKNOWN без повтора. Browser отображает SENT/UNKNOWN. В v7 01 и 02 блокируют путь до этого. [один эффект](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m5_portfolio_delivery_postgres.py#L47), [actual S3](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m5_portfolio_delivery_postgres.py#L105), [dispatch recovery](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m5_portfolio_delivery_postgres.py#L232), [cancel after effect](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m5_portfolio_delivery_postgres.py#L282), [final rights](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m5_portfolio_delivery_postgres.py#L406), [delivery journey](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/frontend/e2e/portfolio-delivery.spec.ts#L42) |
| K10 | Progressive intake/correction, COVER_UP, private DurationCase | **CHANGES_REQUESTED.** Core PG v7 проверяет последовательный вопрос, коррекцию с новым message id, CAS подтверждения и закрытую owner сводку COVER_UP. Browser проверяет source link/внутреннее решение/известные и неизвестные минуты. DurationCase остаётся owner-only, compare фильтрует отозванные assets и не отдаёт часы в model context. 03/04 нарушают сохранность фактов и обработку действующего вопроса. [correction](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m5_intake_postgres.py#L244), [handoff](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m5_intake_postgres.py#L207), [private case](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m5_duration_cases_postgres.py#L22), [owner journey](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/frontend/e2e/intake-duration.spec.ts#L13) |
| K11 | Owner review/publish/revoke из Console, понятные ошибки | **PASS для операций UI, GAP для одного негативного browser case.** Chromium desktop/narrow проверил edit/preview/explicit publish и отзыв источника через реальные owner API. Невалидный draft даёт детерминированную ошибку и не меняет active в Core PG/API, UI показывает ошибки и блокирует publish в component test. Нет отдельного browser прогона невалидного draft на этом tree. [publish](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/frontend/e2e/configuration.spec.ts#L49), [ревью и отзыв](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/frontend/e2e/configuration.spec.ts#L115), [ошибка draft](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m5_configuration_api_postgres.py#L181), [component](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/frontend/src/ConfigurationPanel.test.tsx#L27) |
| K12 | HUMAN/Resume, reconciliation, observation, source gates | **CHANGES_REQUESTED / GAP v7.** Native проверил reconcile+Resume, новое observation, stale work и source admission. Runtime сверил installed 0023 с source catalog. Core v7 отклоняет candidate после TAKEOVER и stale owner confirmation. Native carrier проверяет исторический профиль 0013. В v6 контроль прав и send также подтверждены на application tree. В v7 `intake_sources` выбирает VISIBLE inbound того же Client без сверки нового model payload с admitted snapshot/history policy. `OFF_UNUSED` даёт V2 без истории в ContextBuilder, а `IntakeContextView` добавляет отдельный список. На уровне source это различие требует явной проверки и ограничения свежими авторизованными материалами. Отдельная new-branch proof для resume/observation → READ → SEND остаётся открытой. [reconcile/Resume](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m3_1_native_context_postgres.py#L583), [v7 takeover](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m5_intake_postgres.py#L368), [intake sources](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/migrations/versions/0023_intake_duration.py#L5846), [V2 history boundary](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/backend/src/asm/ai/context.py#L309), [v7 model projection](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/backend/src/asm/ai/intake.py#L60) |

Fixtures A/B прошли publish через одинаковый owner API. Режимы и неизвестные
значения проверялись как configuration, с независимыми price/duration/deposit.
`businesses.v1.json` содержит также C/D. Проведённые runtime journeys
не покрывают каждый вариант с живым провайдером, pricing и payment engine
выходят за рамки M5. [две конфигурации](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m5_configuration_api_postgres.py#L95), [независимые policies](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/test_m5_configuration.py#L13), [A–D fixtures](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/tests/fixtures/businesses.v1.json#L1).

## 5. Правила выдачи и инженерные ограничения

В каждом задании C0 указывает ID, продуктовый результат, полный base SHA, branch,
одного ведущего, exact write-set, dependency, критерии и что оставлено за границей.
Не выдавать весь этот документ C1/C4 как одно задание «реализовать M5».

M5.1A–M5.3A интегрированы. На принятом main действует 0023. В рассматриваемом PR #54 добавлена 0024 с родителем 0023. Изменения C8 ограничены отчётом в M5_HANDOFF согласно CURRENT.

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

Сейчас владелец передаёт C8 ссылку на CURRENT этого поручения. После возврата C8 решение о готовности PR #54 к интеграции принимает C0.

Позже — только конкретное действие по готовому результату:
1. Если понадобится дополнительный real synthetic smoke — отдельные route,
   точные запросы, предел расходов и процедура остановки перед допуском владельца.
   Принятый M5.2A probe заново не запускать.
2. VM/Telegram smoke — отдельный допуск и проверка относящихся к нему receiver
   ограничений; прежние команды не переиспользовать вслепую.
3. Перед реальным бизнесом — подтверждение правил, прав на материалы и data route.
4. Merge нового PR — отдельное действие владельца после C0 review/CI.

## 7. Передача M6

Раздел подготовлен C8 по main `c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba`. При повторном review C8 проверяет его применимость к PR #54 и указывает подтверждённые изменения. Передача в работу M6 требует отдельного решения C0 после приёмки M5.

- `configuration` и owner API `/configuration` возвращают `ActiveProjection`
  schema v1. `Service.id`, `Rule.id` и `Rule.service_id` принадлежат bundle
  в рамках Business и immutable `release_id`. `draft_version` нужен для
  EDIT/PUBLISH CAS. `activation_version` увеличивается при publish/rollback
  и инвалидирующих операциях. Запрос к старому release не даёт текущей authority.
  `tattoo_intake_v1` привязан к опубликованному списку field IDs и required,
  включая optional `references`. Price/duration/deposit проверяются отдельно.
  [bundle и policy IDs](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/backend/src/asm/configuration/models.py#L63), [release и CAS](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/backend/src/asm/configuration/models.py#L147), [template](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/backend/src/asm/intake/templates.py#L5).
- `knowledge` и `portfolio` имеют раздельные paths/API. Authorization связывает
  release/activation и build с Workspace/Business. Knowledge содержит
  `source_id/revision_id/chunk_id/sha256`, owner confirmation и effective window.
  Portfolio содержит `item_id/revision_id/asset_version_id/source_sha256`,
  MY_WORK и show permission. `current_image_v1` закрепляет текущие
  Client/Conversation/message/file/version/hash и optional analysis id/hash.
  Перед чтением байтов и отправкой действуют частные permits и новые проверки.
  Отзыв прекращает доступ к этому источнику. Разрешённая работа или наблюдение
  Vision не даёт решения о цене, времени или допустимости запроса.
  [knowledge source/build](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/backend/src/asm/knowledge/models.py#L119), [portfolio/media pins](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/backend/src/asm/ai/portfolio.py#L59), [private GET](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/backend/src/asm/portfolio/delivery.py#L121).
- `intake` и owner API `/intake/conversations/{conversation_id}` возвращают
  `preliminary_intake_v1` со scope, service/template/release/activation,
  control/context versions и version/fingerprint для owner `CONFIRM/CORRECT`.
  `conversation_v7` / `conversation_result_v3` предлагают candidate facts и
  один outcome через существующий worker. Статусы `client-stated`, `observed`,
  `owner-confirmed` и missing/conflict несут provenance `message_id/source_version`
  с optional analysis id/hash. Проверять source и актуальность в транзакции.
  `PRELIMINARILY_COMPLETE` означает, что известны поля шаблона на текущих
  источниках. Открытые дефекты 01–04 существенны при использовании этого пути.
  [DTO и owner CAS](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/backend/src/asm/intake/models.py#L18), [входы API](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/backend/src/asm/intake/http.py#L39), [result v3](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/backend/src/asm/ai/contracts.py#L296).
- Action Center использует `escalation_id` и `PRELIMINARY_INTAKE_OWNER_V1`
  через прежние list/read/resolve/cancel API. Summary потребляет current pin,
  команда владельца сохраняет версионированное внутреннее решение/receipt.
  Отдельные поля подтверждаются в Intake. `DurationCase` имеет
  `case_id/version/state/source_current`, optional exact asset/version и
  working/occupied minutes с unknown. CRUD/confirm/revoke/search owner-only.
  Comparison возвращает до пяти подтверждённых и действительных примеров
  по placement/style/detail/fill, с совпадениями, различиями и unknown.
  Данные остаются справочными для мастера. [escalation contract](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/backend/src/asm/conversations/escalation_http_models.py#L164), [DurationCase DTO](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/backend/src/asm/intake/models.py#L104), [сравнение](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/backend/src/asm/intake/duration_cases.py#L6).

**Минимальный следующий срез для решения C0.** После закрытия findings и
принятия M5 проверить транзакционный перенос одного актуального intake в
черновой ServiceRequest с provenance и idempotency. В M6 владелец или принятая
детерминированная policy смогут утверждать Assessment. Порядок Quote/Order,
записи и оплаты следует своим этапам. OPEN-080/081 сохраняют вопросы
о конкретных временах мастера, границах сессий и калибровке. [OPEN-080/081](https://github.com/Elefesys/ai-service-manager/blob/c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba/docs/architecture/04_OPEN_QUESTIONS.md#L441).

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
