# M5 — настройки бизнеса, знания, Vision и портфолио

Дата: 2026-11-12. Ведущий: C0. Статус исполнения — только в
[TASK_REGISTER](../TASK_REGISTER.md). Решение по объёму:
[IMPL-005](../decisions/IMPL-005-m5-pilot-knowledge.md) — ACCEPTED / LOCKED C0.

## CURRENT — M5.2A → C4 / IN_PROGRESS / 2026-11-14

Единственная активная задача: **C4-M5.2A-CAPABILITY-PROBE-R1**.
Ведущий C4. C6 участвует только при конкретной необходимости операторского
маршрута, последовательно в том же срезе/PR. M5.1A и M5.1B завершены;
M5.2B и последующие срезы не выданы. Правка Vision prompt включена; сейчас C4
устраняет C0-M5.2A-06 — конфликт принятой C0 docs-ревизии с source guard.
Capability остаётся UNVERIFIED. Само поручение не создаёт нового
paid/VM допуска и не включает Vision в клиентских разговорах.

- Repository: `Elefesys/ai-service-manager`; integration target: `main`.
- Accepted implementation base: `6942150e9a4ab96222f49702b2e9977178b04e74`.
- Base tree: `12e4481c8a54d219e5bae7acb94b5484cf0b166c`.
- Ветка: `c4/m5-2a-capability-probe-r1`; начать с подготовленного C0 docs-only
  commit поверх этого base, сохранить его в ancestry. Его полный SHA/tree взять
  из закреплённой ссылки C0 на это поручение, не из старого M5.1B задания.
- PR #47 слит владельцем; tree равен reviewed candidate
  `525092b701068465e73db6a912b837808b2ab284`.
  [C0 review PASS](https://github.com/Elefesys/ai-service-manager/pull/47#pullrequestreview-5887861003).
  [Post-merge CI43389871150](https://github.com/Elefesys/ai-service-manager/actions/runs/43389871150),
  push/main, attempt1: **12/12 SUCCESS**. M5.1B — **INTEGRATED / VERIFIED в
  synthetic LOCAL/TEST**. Новый v3 provider contract проверен через MockTransport;
  качество реального v3 ответа и Vision/embeddings этим не подтверждены.
- Migration head: **0019**. Applied0001–0019 immutable; новая миграция не нужна
  и не назначена. Состояние M4/live ограничений не меняется.

### Результат и зависимости

Проверить, какой конкретный маршрут сможет разбирать изображение и создавать
совместимые текстовые embeddings для будущего поиска. Это короткая проверка
до реализации M5.2B/C; её пропуск оставил бы неизвестными формат, размерность,
доступность и стоимость внешнего API. Сначала C4 возвращает готовый probe и
конкретную процедуру допуска. Сам capability PASS возможен только по отдельно
разрешённым реальным synthetic вызовам. Fake подтверждает контракт, не качество.

Прочитать CURRENT/AGENTS, IMPL-005 целиком, применимые границы IMPL-004;
Spec §7.10/7.12/7.22, ADR-049/050/051 и ADR-259/260/261. Истина/изоляция из
IMPL-005 сохраняются. Старую историю M4 целиком перечитывать и повторять её
probes не требуется. При конфликте указать точный пункт, последствие и меньший
вариант; не отменять решение молча и не расширять scope ради удобства probe.

### Ограниченная реализация

1. По актуальным первичным документам текущего Polza маршрута выбрать один
   Vision и один text-embedding профиль; model IDs из подтверждённого catalog,
   не display names. Указать источники/дату, endpoint/provider selection,
   доступность на обычном тарифе, schema, image transport/preprocessing,
   размерность/metric/версию embeddings, правила тарификации и допустимый
   synthetic data scope. Не предполагать RU processing по месту оплаты.
   Неизвестный capability/тариф отметить OPEN; не утверждать real-client approval.
   Не повторять обзор рынка и не добавлять автоматический fallback/route UI.
2. Один автономный bounded probe, default/plan/offline без credentials и HTTP.
   Без запуска application/Telegram/VM и без фиктивных messages/conversations.
   Переиспользовать подходящие bounded primitives, не старые approvals/holds.
   `polza.bounded_http` сейчас допускает только chat/catalog/history: embedding
   endpoint нельзя протащить произвольным URL или ослаблением старой allowlist.
   При необходимости добавить узкий helper для подтверждённого endpoint,
   сохранив поведение существующих callers и RuntimeRoute. Не строить общий gateway.
3. Маленький воспроизводимый synthetic набор: обычная, неоднозначная и
   неподходящая картинка; неизвестный масштаб, запрет выдумывать сантиметры,
   время, цену и допустимость заказа; image prompt injection не меняет policy.
   Fixtures локальные, без персональных данных и внешней генерации изображений.
   Один русскоязычный query с релевантным и нерелевантным текстом проверяет
   совместимую размерность, конечные значения и простое ранжирование. Fake или
   случайные векторы не доказывают semantic retrieval; такой набор не доказывает
   общее качество поиска или анализа реальных татуировок.
4. Фиксировать preprocessing/bytes/pixels/MIME, payload/response byte limits,
   token/item limits, connect/overall deadlines, конечное число HTTP requests.
   Реальные bytes, строгий разбор схемы/размерности/индексов; неизвестное не
   заменять догадкой. Не принимать model-supplied URLs, redirects, ambient proxy,
   public S3 или произвольные пути; никаких secrets/raw payload в errors/receipt.
5. До любого авторизованного API обращения — конкретные model/profile IDs,
   источник тарифов, точный список запросов (включая catalog/accounting reads),
   резерв каждого вызова, верхняя сумма в рублях и конечный deadline всей сессии.
   Число запросов определить по фактическому batching API для одного прохода
   набора выше; без повторных серий. Отдельно объяснить границу расхода при
   неизвестной стоимости/timeout. Неизвестный исход сохраняется UNKNOWN, его
   резерв не освобождать и вызов автоматически не повторять. Рестарт не должен
   незаметно повторить тот же запуск. Достаточен малый локальный durable receipt,
   без DB-таблиц и универсального ledger/runner. Штатное завершение само закрывает
   процесс/сессию; вернуть точную команду остановки для выбранного окружения.
6. Старые 150 рублей, ключ и M4 text-only допуск не являются текущим балансом
   или разрешением. Владелец отдельно разрешил C6 продолжение synthetic paid
   tests; основание и границы приведены ниже. Текущая работа C4 — offline/code/CI,
   без ключа, provider HTTP и действий на ВМ. Ключ передаётся только локально,
   не через PR/чат. Новый source/plan сам по себе не расширяет имеющийся допуск.

### Принятая правка C0-M5.2A-05 и текущий blocker C0-M5.2A-06

C0 принимает техническое уточнение общего prompt из готового кандидата C6.
Польза: модель должна сначала оценить видимость рисунка и сохранить неизвестное,
если перекрытие мешает распознать мотив. Нельзя объявлять видимые фрагменты
завершённой ABSTRACT-композицией. Это соответствует IMPL-005 «Фото, портфолио
и длительность»; прежние решения/критерии не отменяются.

- Точный reviewed PR parent: `3472faf1041b7e42c21b89ce01599efebca6a0dd`,
  tree `22e8c07a1f8125295b534a0f1ce45c946a97d67f`.
- Готовый C6 commit: `cb6c95de5c3fc6194c4f216018e4914cbf457ece`,
  tree `93fcbe5d64dd5fa9595b44380043997924778ce6`; единственный parent — выше.
  [Два изменённых файла](https://github.com/Elefesys/ai-service-manager/compare/3472faf1041b7e42c21b89ce01599efebca6a0dd...cb6c95de5c3fc6194c4f216018e4914cbf457ece).
- Пакет05 `5681ee85d31f4d8e1440dc47277893148fc7968c`, tree
  `01a1df345556a8e22cfbe083170152bba443b281` опубликован C4 exact fast-forward.
  Probe91/91, lint/type и сравнение payloads PASS; full CI остановлен guard ниже.
  Это точный repair parent06. C0 добавляет только это обновление handoff;
  его полный prepared SHA закрепляется в review PR48. C4 продолжает ту же
  ветку/задачу, сохраняя ancestry и уже принятую правку prompt.
- Accepted main и immutable assignment
  `64e80b214b3404728de73030acab4cd1fdc28a4e` остаются прежними.
  C0-M5.2A-01/02/03/04 CLOSED; [CI43546043614](https://github.com/Elefesys/ai-service-manager/actions/runs/43546043614)
  для parent3472faf — 12/12 SUCCESS, не повторять.

C0 независимо прочитал diff и визуально проверил исходные три PNG. У ambiguous
чёрные линии прерываются непрозрачным прямоугольником. Ожидаемое
AMBIGUOUS/UNKNOWN сохранено; общая инструкция не получает case ID, expected,
координаты или индивидуальную подсказку ответа. Новый regression воспроизводит
наблюдённый ORDINARY/ABSTRACT как FAILED после подтверждения стоимости, а не
объявляет качество исправленным. Девять прямых local checks C6 — ограниченное
evidence, не frozen pytest/full CI и не live-quality PASS.

### Принятый результат C6 и оставшаяся проверка

[Возврат C6](https://github.com/Elefesys/ai-service-manager/pull/48#issuecomment-6872471841)
по closed plan `6dfde87e3b2f776fecbce1b5ade566aa1e8595092c32f9f0569f9754dac8459f`:
5 HTTP / 2 model POST; ordinary PASS (FLOWER), ambiguous FAIL
(ORDINARY/ABSTRACT), unsuitable и embeddings NOT RUN.
Оба Vision маршрута подтверждены HISTORY_DETAIL как OpenAI/openai/gpt-4o-mini,
attemptsCount=1. Confirmed cost 0.12166148 RUB, текущий hold0; overall
FAILED/SYNTHETIC_QUALITY_FAILED, real_route UNVERIFIED, closed=true.
В этом проходе HTTP403 отсутствует; доступ заработал после изменения owner key
allowlist. Это не доказывает единственную причину всех прежних отказов.

Evidence — транскрипция вывода владельца, не прямое чтение ВМ C0/C4; hash
последнего receipt-файла не наблюдался. Старые UNKNOWN/holds **11.67 RUB**
сохраняются отдельно. Текущий hold0 не освобождает их; прежние receipts,
guards, modes и stop state не удалять/переписывать.

### C0-M5.2A-06 — согласовать source guard с принятой C0 docs-ревизией

[CI43563778264](https://github.com/Elefesys/ai-service-manager/actions/runs/43563778264)
на5681ee85: runtime job132353027249 остановлен до SQL cases с
`CAPABILITY_C0_DOCS_IMMUTABLE`. C0 подтвердил checkout tested merge
`1a5decffd6350a5385696ce1a9c64b734d06b246` и отказ по job log.
Это конфликт интеграционного пакета C0 с test infrastructure, не SQL/LLM failure:
старый guard сравнивает четыре C0 docs с assignment64e80b21, тогда как C0
явно изменил CURRENT в5681ee85. Отмена CURRENT либо игнорирование отказа
не приняты. Полный CI этого кандидата не PASS; неизменённый rerun не нужен.

**C0 явно принимает меньший вариант:** отдельная точная approved docs revision
для текущего M5.2A route. Исходный assignment остаётся immutable историческим
основанием; его tree/ancestry проверки сохраняются. Гарантия отсутствия
неразрешённого doc drift сохраняется, меняется только принятая точка сравнения.

- Approved C0 docs revision: `5681ee85d31f4d8e1440dc47277893148fc7968c`.
- Approved revision tree: `01a1df345556a8e22cfbe083170152bba443b281`.
- TASK_REGISTER: mode100644, blob `b2b7c06a265d897d2054b7c5c4efa0b721687bb5`,
  SHA256 `5d4047eb3bb0905ba3e172305c360d3bf0c1e46654b7b47110b6401fec102402`.
  Остальные три C0 docs равны исходному assignment.
- В capability admission проверить точный tree approved revision и её ancestry
  до HEAD, затем отсутствие diff всех четырёх C0 docs между этой revision и HEAD.
  Не брать revision из HEAD, PR body, переменной окружения или последнего commit.
  Не исключать TASK_REGISTER из protected paths и не разрешать произвольную
  docs-ветку. Не подменять исходный assignment64e80b21 новой revision.
- Для нового guard текущая M5.2A линия обязана иметь approved revision в ancestry.
  Это явно принятое уточнение admission; других исторических M4/M5 routes,
  accepted main, event admission и source export/binding оно не меняет.

**C4 write-set только для этой доработки:**

- `scripts/m4_runtime_db.py` — отдельные pins и bounded docs admission выше;
- `tests/test_m4_runtime_db_runner.py` — реальные Git fixtures/regressions;
- `docs/tasks/M5_HANDOFF.md` — это C0 поручение и короткий фактический возврат.

`docs/TASK_REGISTER.md`, остальные protected docs и уже принятые probe/test
blobs не менять: так source pins не создают новый цикл. Protected set, общий
write-set,160 runtime cases/8 cleanups/SQL900s, attemptsCount/deadline repairs,
все app/tenant/delivery/UNKNOWN guards прежние. Dependencies/workflows/migrations
и source-admission соседних этапов не трогать. Никаких provider/VM действий.

Сначала frozen targeted checks:

1. Реальный Git base → immutable assignment → явно изменённый C0 CURRENT →
   implementation → PR test merge/main push. Одобренная revision с новыми bytes
   проходит; старый guard воспроизводимо отвергает её. Mock git-output вместо
   созданных commit не является этой проверкой.
2. Неверный tree approved revision, её отсутствие в ancestry (включая unrelated
   commit с таким же tree), последующее изменение каждого из четырёх protected
   docs и mode/type drift отвергаются до resources/credentials.
   Прежние assignment/base/branch/path negative tests сохраняются.
3. Все M5 capability source-admission/export/binding cases, затем полный
   `tests/test_m4_runtime_db_runner.py`; lint/format и git diff --check.
   Подтвердить неизменность160 cases/8 cleanups/900s существующими тестами,
   не повторять локально полный M4 SQL workload.
4. До push на настоящем candidate checkout проверить pinned revision tree,
   оба ancestry и пустой protected-doc diff; не ограничиваться synthetic fixture.
   Затем один штатный full CI финального исправленного code/docs кандидата.
   Сам acceptance expected не ослаблять; SQL/инфраструктурные причины разделять.

Возврат: final head/tree/tested SHA, изменение admission и точные commands/results,
CI URL/status. Detailed evidence — в PR/CI. Новый provider plan пока не нужен.
C0 закрывает06 после проверки кода/CI;05 semantic live outcome остаётся UNVERIFIED.

### Следующий последовательный шаг C6

Только после C0 code/CI приёмки C6 обновляет source/module/payload pins и готовит
один новый bounded operator plan из фактически принятого SHA. Старые closed plans
не воспроизводить. Новые payload hashes обязательны; один полный synthetic проход
с прежним fail-fast — максимум8HTTP/4POST, резерв11.75RUB, session210s/key15s,
connect5s. Catalog4MiB; Vision32768/history65536/embedding262144 bytes.
Неподтверждённый embedding provider остаётся UNKNOWN/hold0.08; selector не evidence.

[Владелец разрешил C6 продолжение paid tests после изменения allowlist](https://github.com/Elefesys/ai-service-manager/pull/48#issuecomment-6872201066);
C6 подтверждает наличие допуска в текущем возврате. Не требовать повторного
разрешения на уже охваченные действия. При подготовке нового конкретного плана
C6 связывает его с фактическими границами этого допуска; source/expiry сами по себе
не разрешение, закрытый прежний one-Start не переиспользуется. Расширение модели,
данных, лимита расходов или VM scope требует отдельного решения владельца.
C4/C0 не выполняют provider/VM действий в этой доработке.

Vision profile `polza_openai_gpt4omini_png_low_v1`; embedding profile
`polza_openai_text_embedding3small_1536_cosine_v1`; только synthetic data,
selector openai, no fallback. Максимум 3 изображения256×256 и batch3 текстов;
scale UNKNOWN, size/time/price/order approval null. Usage/cost/provider/schema
checks и безопасный вывод failure сохраняются. Все старые receipts и11.67RUB
UNKNOWN/holds сохраняются; никаких support contacts и переключения моделей.

Только C0 принимает итог M5.2A по фактическим результатам; успешные mock/CI
не подтверждают качество модели. M5.2B не выдан. PR остаётся Draft;
merge — отдельное разрешение владельца.

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

M5.1A и M5.1B интегрированы; текущие paths и source admission задаёт только
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

Сейчас достаточно передать C4 закреплённую ссылку на CURRENT этой выдачи.
PR #45/#46/#47 уже интегрированы. Для offline подготовки M5.2A нового допуска
владельца не требуется; C4 сначала завершает проверяемый code/procedure пакет.
Запрос на платные вызовы — только с готовыми маршрутом, точными запросами,
верхней суммой и процедурой остановки. Реальные материалы мастера не нужны.

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
