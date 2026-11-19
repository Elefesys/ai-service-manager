# M5 — настройки бизнеса, знания, Vision и портфолио

Статус исполнения — в [TASK_REGISTER](../TASK_REGISTER.md).
Решение по объёму — [IMPL-005](../decisions/IMPL-005-m5-pilot-knowledge.md),
ACCEPTED / LOCKED C0.

## CURRENT — C1-M5.3B-V7-FIX-R1 / IN_PROGRESS / 2026-11-18

**C0 → C1. Восстановить штатный диалог v7 с опубликованными знаниями, фото портфолио и продолжающимся intake.** Клиент получает один разрешённый пример работы и сохраняет прогресс по своему запросу. Мастер может подтвердить поле и решить уже открытый вопрос в Action Center.

**Решение C0 по общей приёмке M5 — CHANGES_REQUESTED.** Приняты все четыре замечания C8. Результаты M5.1A–M5.3A действуют в ранее проверенных границах synthetic LOCAL/TEST. PR #53 и push/main прошли по 12/12 с первой попытки. В тех прогонах отсутствовал единый v7-сценарий с непустым поисковым индексом и отправкой фото. Матрица C8 по принятому main сохранена в §4, проект передачи M6 — в §7. [Возврат C8 с исходниками и воспроизведением](https://github.com/Elefesys/ai-service-manager/blob/4cb6318f008d3ca952eb077268887e2d39714972/docs/tasks/M5_HANDOFF.md#L14). [Приёмка PR #53 и post-merge evidence](https://github.com/Elefesys/ai-service-manager/blob/3ba774da3bf61b57062098ea5e0470b1402eb70d/docs/tasks/M5_HANDOFF.md#L14).

**Основание и ведущий**

- Репозиторий · `Elefesys/ai-service-manager`. Integration target · `main`. Единственный ведущий · C1. C2 консультирует по миграции, C4 по v7, C5 при необходимости по существующим browser tests. C1 собирает один кандидат. C8 получает его на повторную приёмку после возврата C1. C6 HOLD.
- Полный application base · `c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba`. Tree · `11c987fb12e4f88d27da3737911c468d520269b8`. Начни с подготовленной ветки `c1/m5-3b-v7-fixes-r1`. Её стартовый commit с этим поручением имеет единственного родителя — указанный main. Для source admission закрепи SHA и tree стартового commit из Git до первой правки. Ветка C8 хранит независимое заключение и остаётся отдельной.
- Прочитай CURRENT в `docs/TASK_REGISTER.md`, IMPL-004/005, Specification §§5.5–5.10 и 11.11, ADR-023–026, 030–034, 065–068 и 265–267 в применимой части. Структурированные правила, источники и решения владельца определяют допустимые действия. M6, цена, длительность, Quote, запись и платежи остаются за границей поручения.

### Что исправить

| Finding | Изменение и наблюдаемый результат |
|---|---|
| **C8-M5-01 · P1** · непустой индекс | В `portfolio_query_reserve` провести v7 через тот же подходящий допуск `SYNTHETIC_INTAKE_V1`, что и PREPARE. Проверить текущий scope, владельца, профиль, expiry и бюджет под блокировкой. Активные knowledge и portfolio используют один shared QUERY. Проверить непустой и пустой индекс, replay и отказы чужому, просроченному или неверному профилю. Сохранить назначение и ограничения путей v5/v6. |
| **C8-M5-02 · P1** · стабильный READ | Сравнивать проекции одной версии. На v7 закрепить целиком показанный контекст, включая intake и допущенные фото. На неизменных данных один READ даёт одну attestation и один follow-up. COMMIT принимает только показанный и засвидетельствованный выбор по `item_id/revision_id/asset_version_id/source_sha256`. Реальная смена контекста или разрешения останавливает старый результат. Оставить проверку digest и прежний контракт v6. |
| **C8-M5-03 · P2** · сохранение фактов | Согласовать Python reducer и SQL projection/apply. При повторной публикации или rollback прежний run теряет право продолжения. В новой проекции по каждому полю проверить тот же запрос, service, совместимый template/поле и актуальную версию доступного источника или анализа. Сохранить подтверждение и исходную привязку для действительного факта. При `AMBIGUOUS` уточнить тему, сохранив прогресс прежнего запроса. У равного значения из нового сообщения сохранить статус мастера и открытый конфликт. Проверить явную коррекцию, подтверждённую смену запроса и исключение устаревших полей после изменения или удаления источника. |
| **C8-M5-04 · P2** · действующий вопрос мастеру | При `CONFIRM/CORRECT` для того же запроса атомарно обновить summary и привязку только у карточки, актуальной непосредственно до команды. Сохранить одного адресата, один PENDING, CAS и идемпотентность. Проверить порядок `COVER_UP → PENDING → подтверждение поля → повторное чтение того же ID → RESOLVE`. Старая версия команды отклоняется, replay успешной команды не добавляет эффектов. Изменение темы, источника, владельца или условий управления по-прежнему закрывает старый допуск. |

**K12 · граница истории.** На каждом MODEL, READ и FOLLOWUP проверить фактически сериализованный клиентский контекст v7. У `OFF_UNUSED` нет допуска к прежней переписке. При разрешённой native history действуют snapshot, reconcile, observation, лимиты объёма и правила пропусков M4. Это относится и к `intake.sources`, и к вложенным `Fact.source.quote`. Проверить уникальными синтетическими метками текущего сообщения, старого сообщения той же истории и другого клиента. Допущенные структурированные значения могут оставаться известными без передачи прежних цитат. Проверить источники новых кандидатов по текущему допустимому входу. Полная owner-проекция имеет собственный авторизованный путь. Исправить обнаруженный разрыв в пределах v7. C8 зафиксировал пробел в проверке состава контекста. Межобъектная изоляция K05 прошла в исследованном scope.

**K11 · интерфейс.** Дополнить существующий сценарий configuration в Chromium одним действием над некорректным draft. Владелец видит ошибку валидации, публикация не происходит, активная конфигурация сохраняется. В существующем browser case для intake проверить порядок действий мастера из C8-M5-04.

### Как принять исправление

1. Для исходного поведения использовать воспроизведения и артефакты C8. Где вывод сделан только по исходникам, проверить конкретную последовательность на actual PostgreSQL, в частности непустой QUERY и подтверждение после открытия вопроса. На кандидате запустить регрессию для каждого из четырёх замечаний, включая стабильный READ v7 с рабочим v6 рядом. В отчёте указать, какие результаты дал PostgreSQL, какие получены с FakeAdapter и какие взяты из CI.
2. Провести один положительный синтетический кейс через обычный v7 worker с actual PostgreSQL, активными непустыми KB и MY_WORK, актуальным анализом входного изображения и ограниченной сессией. Проверить **один QUERY → MODEL → один READ и attestation → FOLLOWUP → COMMIT → private GET → SEND**. Оригинальные байты и хеш опубликованной версии проверить с изолированным S3/MinIO. Telegram и AI/embedding используют контролируемый транспорт. На выходе одно фото с подписью, одна запись каждого вида intent/message/Outbox и один наблюдаемый вызов отправки. Дополнительного текстового ответа нет. Выбрать допустимую для фото реплику и не обходить штатное уточнение intake. Показать scoped source refs и число резервирований/эффектов.
3. На подходящей границе проверить изменения публикации или отзыв MY_WORK, правку/удаление источника, потерю Telegram rights, HUMAN/Resume с OWNER reconciliation и новым observation, а также потерянный ACK и restart. Перед COMMIT, private GET и транспортом должны действовать соответствующие текущие права и версии. Старая работа прекращается, новый разрешённый ход берёт свежий контекст. После неопределённого исхода — UNKNOWN и ноль повторных отправок. Указывать, до какой границы дошёл каждый отрицательный кейс и сколько было внешних эффектов.
4. Проверить факты и открытую карточку на actual PG по строкам 03–04. Для 03 отдельно показать идемпотентный/равный ввод, неоднозначность, совместимую повторную публикацию и несовместимое изменение. Изменить прежнее ожидание `facts=[]` только там, где проверены действительность источника и сохранение статуса. Для 04 проверить также конкурентную или устаревшую команду и изменившийся источник.
5. C0 выделяет **только 0024**, родитель **0023**. Добавить точечную миграцию поверх неизменных 0001–0023. Проверить fresh → 0024, заполненную 0023 → 0024, повторный upgrade и безопасный downgrade с восстановлением 0023 либо отказом до изменений при небезопасном состоянии. Сохраняются факты с provenance, PENDING, UNKNOWN, запрет повтора и прежние receipts. Исторический профиль 0023 и его digest остаются проверяемыми. Новый профиль сверить с фактическим каталогом, включая функции, столбцы, grants и поведение при drift. Переключить только проверки текущей версии, включая readiness для native context и text-only sessions. Использовать существующие таблицы и полномочия.
6. Для `scripts/m4_runtime_db.py` провести новый кандидат через обычные PR и post-merge source gates. Проверить точные base/tree, branch, SHA/tree/parent пятидокументной выдачи, конечный список путей ниже и четыре защищённых C0-файла. Для push/main проверяются реальные родители и совпадение дерева принятого кандидата. У старых маршрутов сохраняются собственные branch/base/профили и отрицательные проверки. Лимиты, timeouts и workflows остаются прежними.
7. Оформить один Draft PR в main с исправленным исходным деревом. В описании указать full head/tree и tested merge SHA, фактические команды и результаты по каждому finding и K03/04/06/09/10/11/12, ссылку на целевой PG/S3/browser evidence, штатный CI и ограничения. Включить новые сценарии в штатные собираемые тесты. Полный CI нужен один раз на изменённом финальном кандидате. При инфраструктурном сбое указать конкретную job/причину. После возврата C1 C8 повторно проверит findings и обновит матрицу. Решение C0, отдельное разрешение владельца на merge и post-merge CI предшествуют завершению M5.

### Разрешённые файлы

Список конечный. Запись `{a,b}` перечисляет ровно два имени, подстановочных символов нет. Трогать только файлы, необходимые для результата.

**Код v7 и intake**

```text
backend/src/asm/ai/{agent,context,contracts,database,intake,portfolio,portfolio_delivery,runtime,runtime_contracts}.py
backend/src/asm/intake/{models,projection,repository,service,templates,validation}.py
migrations/versions/0024_intake_v7_repair.py
```

**Регрессионные проверки и синтетические fixtures**

```text
tests/{m5_intake_fixtures,m5_knowledge_search_fixtures,m5_portfolio_fixtures,m5_portfolio_delivery_fixtures}.py
tests/{test_m5_intake,test_m5_intake_runtime,test_m5_intake_postgres,test_m5_intake_api_postgres,test_m5_portfolio_delivery,test_m5_portfolio_delivery_postgres}.py
tests/{test_m5_intake_v7_repair_migrations,test_m5_intake_v7_integration_postgres}.py
scripts/m5_intake_fixture.py
frontend/e2e/{configuration,intake-duration}.spec.ts
```

**Только действующий профиль 0024, его dispatch и допуск исходников в существующих проверках**

```text
backend/src/asm/{foundation,telegram/provisioning}.py
scripts/{m2_4_browser_fixture,m4_runtime_db,native_context_db_catalog,prepare_telegram_egress}.py
scripts/test_telegram_egress.sh
tests/{generic_pg_schema,test_foundation,test_m2_3_db_postgres,test_m2_3_schema_postgres,test_m2_3_setup,test_m2_4_browser_fixture}.py
tests/{test_m3_1_guards_migrations,test_m3_1_native_context_postgres,test_m3_1_native_context_runtime_postgres,test_m3_2_escalations_migrations}.py
tests/{test_m4_delivery,test_m4_delivery_postgres,test_m4_polza_runtime_postgres,test_m4_reply_rights,test_m4_runtime_db_runner,test_m4_runtime_migrations,test_m4_schema_postgres}.py
tests/{test_m5_configuration_postgres,test_m5_intake_migrations,test_m5_knowledge_runtime_postgres,test_native_context_db_runner,test_telegram_egress,test_telegram_egress_postgres,test_tenancy_postgres}.py
```

`docs/tasks/M5_HANDOFF.md` разрешён только для краткого возврата C1 под CURRENT до финального CI. Логи и результаты финального CI разместить в PR. В стартовой выдаче C0 также изменены `AGENTS.md`, `README.md`, `docs/TASK_REGISTER.md`, `docs/decisions/IMPL-005-m5-pilot-knowledge.md`. Эти четыре файла принадлежат C0. Другой необходимый путь требует конкретного diff и решения C0. Сохранить checkpoint в рабочей ветке, если потребуется передача незавершённой работы.

Режим — synthetic LOCAL/TEST, default OFF/FAKE/EVAL_ONLY. Прежние UNKNOWN/NOT_PROVEN, holds 11.75 RUB, подтверждённые 0.50229415 RUB, receiver ACK/fence, полный live HUMAN/Resume и ограничение `MEDIA_REPLACED_UNAVAILABLE` остаются записанными в §7. Новых paid/model/VM/live Telegram или реальных клиентских данных это поручение не допускает. Следующее действие владельца — передать C1 ссылку на этот CURRENT.

**Возврат C1.** Кандидат включает исправления C8-M5-01–04, миграцию 0024 и синтетические проверки K11/K12. Идентичность кандидата и результаты проверок собраны в Draft PR ветки задания для повторной проверки C8.

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

C8 завершил общий review принятого main и вернул CHANGES_REQUESTED. Для нового
исправленного кандидата нужны целевые проверки, штатный полный CI и повторный
review C8. Затем C0 принимает решение, владелец отдельно разрешает merge и C0
проверяет фактический push/main CI. После общей приёмки C0 обновляет реестр
и передачу M6 с release/intake/source contracts и ограничениями.

Отдельно перечислить, какие реальные Vision/embedding/Telegram проверки выполнены,
какие требуют владельца. LOCAL/TEST VERIFIED не равен готовности реального бизнеса.
При непроверенном реальном Vision route честный статус соответствующего среза —
REVIEW/BLOCKED по точной причине, а не автоматическое VERIFIED всего функционала.

## 4. Одна приёмочная матрица

Все ссылки на source в матрице закреплены на application SHA
`c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba`. Матрица фиксирует вердикты для этого main до исправления C1.
Проверка **Core**, **Runtime**, **Browser** и **Native** описана в [возврате C8](https://github.com/Elefesys/ai-service-manager/blob/4cb6318f008d3ca952eb077268887e2d39714972/docs/tasks/M5_HANDOFF.md#L14). Это артефакты push/main `44018352191`, attempt 1. Core call outcomes
сверены по `ci.log` и выборочно по nodeid/digest в `cases.jsonl`.
Один сквозной v7 результат **не подтверждён**. Ниже связаны самостоятельные
кейсы actual API/PG/browser и controlled transports.

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

M5.1A–M5.3A интегрированы. Объём исправления и конечный список путей задаёт
CURRENT выше. На принятом main действует 0023. Для этого исправления выделена 0024.

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

Сейчас владелец передаёт C1 закреплённую ссылку на CURRENT этого поручения.
PR #45–#53 интегрированы. Следующий PR содержит ограниченное исправление v7
и требует обычной проверки изменённого кандидата.

Позже — только конкретное действие по готовому результату:
1. Если понадобится дополнительный real synthetic smoke — отдельные route,
   точные запросы, предел расходов и процедура остановки перед допуском владельца.
   Принятый M5.2A probe заново не запускать.
2. VM/Telegram smoke — отдельный допуск и проверка относящихся к нему receiver
   ограничений; прежние команды не переиспользовать вслепую.
3. Перед реальным бизнесом — подтверждение правил, прав на материалы и data route.
4. Merge нового PR — отдельное действие владельца после C0 review/CI.

## 7. Передача M6

Использовать после решения C0 по §4. Ниже фактические контракты application
`c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba`, на которых можно проектировать следующий срез.

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
