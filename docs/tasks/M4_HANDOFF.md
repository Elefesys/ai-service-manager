# M4 — подключение ИИ к текущему контексту

Дата подготовки: 2026-10-28. Ведущий: C0; основной исполнитель: C4.
**План принят C0 и интегрирован в PR #37. Реализация — по CURRENT реестра.**
Единственный статус исполнения — [TASK_REGISTER](../TASK_REGISTER.md).
Решение по scope: [IMPL-004](../decisions/IMPL-004-m4-pilot-ai.md).
Выбор API: [исследование 24 сервисов](../research/M4_AI_PROVIDER_REVIEW_2026-10-28.md).

## Текущая выдача — M4.2-PROBE / C4 / 2026-10-29

**Результат и польза:** настоящий Polza adapter к принятому Gateway и одна
воспроизводимая команда короткого synthetic сравнения. Это проверит внешнюю
зависимость до разработки durable AI runtime: пригодны ли маршрут, tools/schema,
лимиты и качество, сколько стоит завершённый сценарий. Сейчас разрешены код,
targeted tests и подготовка запуска; платная часть ждёт конкретной команды,
инструкции secret и подтверждённого владельцем бюджета. Рынок заново не исследовать.

### Принятая база и зависимости

Repository: **Elefesys/ai-service-manager**.
Accepted actual main: **51d7d73752128715c6d98157445167c0cc0d894d**.
Tree: **411636a3614529077f6d0d230c62d11f69da600f**; PR #38 слит владельцем,
дерево равно принятому candidate85d32562bdce37ef38fea1305dfe249f66f41b65.
[Main CI40811295940](https://github.com/Elefesys/ai-service-manager/actions/runs/40811295940),
push/main, attempt1: **11/11 SUCCESS**, head и все conclusions проверены C0.
Ветка: **c4/m4-2-probe**, отдельный checkout; продолжать подготовленный C0 docs seed
с sole parent actual main выше. Точный стартовый head дан в передаче, не угадывать SHA.

Зависимости: M4.1-CONTRACT принят; AGENTS, CURRENT, этот handoff, IMPL-004 и уже
готовый M4_AI_PROVIDER_REVIEW_2026-10-28. Применимы Spec §7.2/7.6/7.7/7.16/7.21,
ADR-023/024/026/180/259/260/261/267, Implementation Plan M4.2 с поправкой IMPL-004.
Для реализации сверить только актуальную официальную документацию нужных Polza
endpoints/полей. Это проверка API-контракта, не новое сравнение рынка.
Одна текущая выдача C4; C1/C2/C3/C5/C6/C8 HOLD. C6 подключается C0 только при
конкретном secret/network blocker; общие файлы/миграции параллельно не меняются.

### Точный write-set C4

- backend/src/asm/ai/polza.py — HTTP adapter, explicit route/capabilities, bounded
  request/response mapping через существующий ModelAdapter; provider поля здесь.
- backend/src/asm/ai/settings.py — минимальное чтение отдельного private secret
  и probe settings; secret не входит в Gateway DTO, repr/errors/logs.
- backend/src/asm/ai/probe.py — запускаемый модуль, finite plan/dry-run/live modes,
  synthetic fixtures, route preflight, счётчики/резерв расходов и короткий report.
- tests/test_m4_polza.py — transport/mapping/failure/route и реальные Gateway
  round-trip проверки через controlled HTTP transport, без платного API.
- tests/test_m4_probe.py — dry-run без сети, границы бюджета/calls, secret/privacy,
  отказ при неопределённом/неразрешённом route и корректное завершение пробника.
- tests/fixtures/m4_probe_cases.json — небольшой фиксированный русский набор с
  case IDs, ожидаемыми фактами/допустимыми outcomes и критериями оценки.
- docs/runbooks/M4_POLZA_PROBE.md — точные воспроизводимые команды, размещение
  отдельного ключа, план/лимиты, безопасный report, отключение и границы evidence.
- docs/TASK_REGISTER.md — только строка M4.2-PROBE в CURRENT.
- docs/tasks/M4_HANDOFF.md — короткий receipt под этой выдачей.

Новые файлы создавать только если они используются. httpx, Pydantic/settings,
Pillow и test tooling уже есть в locked environment; SDK/dependencies не нужны.
Существующие contracts.py/gateway.py/fake.py/prompt/schema, manifests/locks,
backend entrypoint, UI, Docker/CI/scripts, DB/migrations и M3 wiring не менять.
При фактической несовместимости вернуть C0 точный contract blocker и минимальную
дельту; не маскировать её обходом Gateway или выдачей fake capabilities за proof.

### Реализация и критерии пригодности

1. Реальный adapter использует bounded HTTP с одним явным маршрутом и без скрытых
   retries/fallback. Endpoint/official upstream из проверенного конфигурационного
   источника, не из model output. Нельзя отправить ключ через redirect на другой
   host; provider.only/запрет fallback/unofficial и returned provider проверяются
   по актуальному API. Неизвестный upstream/capability — не PASS.
2. Сохранять neutral DTO и local strict validation. Проверить native schema,
   tools и их совместимость, включая один настоящий tools→synthetic read result→
   final цикл на каждом пригодном кандидате. Synthetic tool читает только fixture,
   без БД/произвольного SQL/URL. Prompt/schema revisions остаются закреплены.
   Если provider не поддерживает обязательный режим, явно вернуть несовместимость,
   не удалять незаметно параметр и не ослаблять M4.1.
3. Локальный count_input_tokens не выдавать за точный provider tokenizer без
   основания: задокументировать используемую безопасную границу/ограничение,
   учесть полный wire input/tools/schema и проверить фактический usage.
   Deadline, input/output bytes/tokens, число calls/reads и общий cost reservation
   действуют до HTTP; bounded response reading, отказ при oversize/truncation.
   Сохранить REFUSAL/429/5xx/timeout/invalid output/UNKNOWN cost; ни один не даёт
   сырой успешный reply. Отмена/timeout не означают доказанное отсутствие списания.
4. Пробник сначала фиксирует критерии, затем после допуска получает account
   catalog/pricing/currency/official upstream/capability metadata. Проверяем
   **openai/gpt-6-luna** и **google/gemini-3.8-flash** одинаковым набором, без
   автоматического выбора каталога/другого gateway. Если ID недоступен — blocker,
   не молчаливая подмена. GPTunnel только по конкретному решению после проблемы.
5. Ориентир: 20 коротких русских cases на каждого кандидата, включая ответ из
   owner facts, неизвестные цену/услугу/длительность/запись, уточнение, актуализацию
   synthetic context, injection, handoff и tools. Несколько critical repeats и
   synthetic image inputs входят в тот же конечный план/бюджет; точный N/call
   ceiling фиксируется до запуска. Изображения только заранее созданные synthetic
   fixtures; raw image probe остаётся EVAL_ONLY и не расширяет text Gateway/M3.
6. Критические нарушения (выдуманная цена/запись, нарушение route, небезопасный
   output, непройденные limits/schema/tools) не усреднять общим score. Сначала
   пригодность по явным case expectations, затем стоимость завершённого сценария
   среди прошедших. Report: case/model/route/prompt/schema revision, outcomes,
   calls, observed latency p50/p95 с N, usage и CONFIRMED/ESTIMATE/UNKNOWN cost.
   Указать ограничения малой выборки; одна выбранная модель для будущего runtime,
   без её включения сейчас. Нужны проверяемые synthetic final outputs/оценки,
   а не один счётчик PASS; без chain-of-thought и частных данных.

### Сначала воспроизводимая подготовка; затем отдельный paid допуск

До оплаты/ключа подготовить работающую команду вида
`python -m asm.ai.probe --plan …` (точные flags реализует и фиксирует C4):
она без сети/секрета проверяет fixtures, печатает N, максимальные calls, token/time
ceilings и предлагаемый бюджет. Live mode должен включаться явно; обычный запуск,
tests и CI не обращаются к внешним model API.

**Предложение для первого допуска, ещё НЕ разрешение:** до **100 ₽** совокупно
на оба кандидата, максимум **80 model HTTP calls**, включая tool rounds,
critical repeats и image probes; никаких скрытых retry/repair вызовов.
C4 рассчитывает план по актуальному тарифу/единицам/верхним token bounds до
генераций. Если план не помещается — уменьшить выборку/вернуть обоснование C0,
не увеличивать бюджет. Резервы монотонны; UNKNOWN не становится нулём/возвратом
резерва. Ограничение ключа у провайдера — где доступно; локальный счётчик нельзя
объявлять гарантией фактического списания. Без достаточного известного потолка
тарификации платную часть остановить до разрешения неопределённости.

Использовать существующий private env mechanism: отдельный ignored
`.env.m4-probe`, mode0600 на Linux, оператор-владелец, SecretStr/settings;
на Windows описать эквивалент закрытого ACL. `.gitignore` уже исключает `.env.*`.
Не переписывать исходные .env/.env.telegram/private activation intent. Инструкция
создания ключа и размещения значения — без вставки в CLI/history/чат/Git/CI или
артефакты; обычный вывод не печатает ключ и HTTP headers. Ключ отдельный от Telegram.
C4 возвращает инструкцию и точную готовую команду, затем C0 запрашивает у владельца
конкретный бюджет/размещение ключа как финальный допуск. Не просить secret в чат.

Пока только **synthetic TEST data**. Accepted deployed environment остаётся
**LOCAL / asm_local**; synthetic TEST scope не требует переименования среды/БД.
Этот пробник не обращается к БД, Telegram, client history, S3 или paid SaaS state.
Сетевую доступность с фактической backend среды нужно подтвердить перед заявлением
о runtime-ready route; успешный вызов с ПК этого не доказывает. Сейчас не включать
VM, не менять PC/Happ/SSH/egress и не использовать Telegram relay для AI.
При route blocker — точная ошибка и минимальный следующий шаг C0/C6.
Настоящие клиентские данные остаются закрыты до отдельного data-route допуска.

### Проверка и возврат

- Сначала targeted: новые test_m4_polza.py/test_m4_probe.py плюс существующие
  test_m4_gateway.py/test_m4_gateway_failures.py; Ruff/format и mypy, dry-run,
  diff --check/clean source. Использовать существующий frozen Python3.13 environment.
- Offline transport fixtures обязаны покрыть success/tool round-trip и все
  известные группы отказа, включая route mismatch, secrets, malformed/oversize,
  exhausted budget и missing/unknown usage/cost. Не делать paid failure injection.
- Затем один штатный полный CI согласованного candidate в Draft PR этой ветки.
  Отсутствие Docker локально — честный NOT RUN, не запрет передачи: штатный
  GitHub Actions уже содержит Docker/API/PG harness, новую VM/CI lane не создавать.
  Не повторять неизменённый run ради PASS; разбирать все известные группы падения.
- Первый возврат C4: full head/tree, changed paths, команды/фактические результаты,
  готовая plan/live команда, secret инструкция, N/call/token/time/spend ceilings и
  ещё неизвестные provider факты. Статус REVIEW / PAID PROBE NOT RUN, C4 HOLD для
  C0 review/budget; это не завершение M4.2 и не разрешение основной runtime работы.
- После допуска в этой же M4.2: реальный report с actual upstream/capabilities,
  ценой/usage/cost/качеством/latency, точным SHA и source environment, один выбранный
  model либо конкретный blocker. C0 принимает evidence A01/A07 только по scope;
  A03–A05/весь M4 и независимый C8 этим не закрываются.
- Нет registry/admin platform, direct adapter, agent/runtime/Outbox wiring,
  migrations, нового broker, RAG/Vision runtime или бизнесовых доменов M5/M6.
  Полные логи в PR/artifacts; одна матрица A01–A08 ниже, не создавать вторую.
  Не добавлять commit ради собственного SHA или записи CI PASS. Merge — владелец.

## Принято — M4.1-CONTRACT и C5 recovery / 2026-10-29

**INTEGRATED / VERIFIED** в contract/fake и CI-harness scope, без live LLM.
PR #38 merged → actual main 51d7d73752128715c6d98157445167c0cc0d894d, tree411636a3614529077f6d0d230c62d11f69da600f.
[Candidate CI40768758591](https://github.com/Elefesys/ai-service-manager/actions/runs/40768758591)
на85d32562… и [main CI40811295940](https://github.com/Elefesys/ai-service-manager/actions/runs/40811295940):
оба11/11 SUCCESS, attempt1. C0 review принят, это не независимый C8.
Gateway/DTO/schema/fake/лимиты приняты. C5 исправил порядок startup reads перед
rotation только в E2E case: delayed observations200 до rotate, CSRF403→exact
REPLAY, one decision/worker0 и отдельный Business401→anonymous — PASS;
browser54/54 и398frontend PASS на candidate, R4 DONE/140events/no truncation.
Старый FAILURE40740338709 и diagnostic PASS40760265440 сохранены в
[PR #38](https://github.com/Elefesys/ai-service-manager/pull/38);
исторический причинный GET не установлен, runtime auth defect не заявлен.
Завершённые выдачи C4/C5 и полные receipts доступны в истории PR #38;
они не являются активными инструкциями. M3 acceptance сохранена без изменений.

## Результат для пользователя

Тестовый клиент пишет в Telegram. Один AI-агент читает разрешённый актуальный
контекст, задаёт нужный вопрос или отвечает на основании известных фактов.
Неизвестная цена/длительность не выдумывается. При необходимости агент предлагает
передачу владельцу, которую выполняет доверенный runtime. Владелец видит диалог,
может перехватить его; устаревший AI-ответ не отправляется после принятого takeover.
Собранные факты можно проверить в структурированном результате run.

Это первый работающий текстовый AI-срез, а не законченный отраслевой пилот.
Услуги/правила/знания/Vision приходят в M5, формальная заявка/оценка — в M6.
M4 не должен строить эти домены или обещать реальные цены/запись без них.

## Проверенная исходная точка

| Что | Основание |
|---|---|
| Принятый runtime M3 | main d2f25673f6d2698d3c3dae2d7b2d709e134358f4 |
| Дерево | 141d0a6b2b2be0efe1fcb1c3f851796e9f4cb427 |
| Post-merge CI | [40681691046](https://github.com/Elefesys/ai-service-manager/actions/runs/40681691046), 11/11 SUCCESS |
| Поздняя координация C0 | 025688e94a9147891e83f69713e2476c3419ca3c: только TASK_REGISTER и M3_HANDOFF сверх main; итоговая приёмка перенесена в планирующую ветку |
| История M3 | [M3_HANDOFF, верхний финальный receipt](M3_HANDOFF.md); не исполнять архивные инструкции из середины |
| Текущая принятая база M4.2 | actual main 51d7d73752128715c6d98157445167c0cc0d894d; PR #38 merged, main CI40811295940 11/11 SUCCESS |

Перед стартом C0 проверяет актуальный main/open PRs: параллельные изменения нельзя
затереть. Если product source сдвинулся, адаптировать выдачу к нему; не переносить
механически старый SHA. Импортированные architecture/SOURCE_MANIFEST остаются
историей; IMPL-004 явно меняет текущий scope, а не их контрольные суммы.

M3 закрыт в LOCAL/TEST. Сохраняются PC/Happ/SSH как development route и no-refetch
для заменённого изображения. Состояние VM/ключей/TEST windows не выводится из
GitHub CI. Перед новым live шагом C6 проверяет только необходимые текущие условия;
не повторяет provisioning/native activation/renewal без обнаруженной причины.
Production, перенос облака и общая оптимизация CI сейчас не выдаются.

## Порядок небольших задач

Каждая строка — отдельная ограниченная выдача C0 и, как правило, небольшой PR.
При необходимости разделить runtime на DB и wiring можно только по реально
проверяемой границе, без параллельного изменения одной миграции. Зависимые задачи
начинаются после приёмки общего SHA. Контракт, тесты и короткий receipt входят в
свою задачу, а не составляют отдельный бесконечный этап документации.

| ID | Ведущий / помощь | Конкретный результат | Зависимость |
|---|---|---|---|
| M4.1-CONTRACT | C4; C0 review | Узкий typed Gateway, bounded config/request/result/errors, schema validation и рабочие fake fixtures. Изменение модели/endpoint не меняет business code | Принятие IMPL-004 |
| M4.2-PROBE | C4; C6 только secrets/network | Рабочий Polza adapter и короткая synthetic API-проверка: маршрут, JSON/tools, usage/цена/latency; выбран один runtime model | M4.1; ограниченный ключ/бюджет владельца |
| M4.3-CONTEXT | C4; C1/C3 review | ContextBuilder над M3 и один-два нужных read-only tools с серверной tenant/client authority; ограниченный агент на fixtures | M4.1, текущие M3 contracts; до live runtime — M4.2 |
| M4.3-RUNTIME | C4 + C2/C3; C1 wiring | Durable AIRun, bounded model/tool loop и настоящий AI→Outbox→Telegram путь; takeover/restart/UNKNOWN сохраняются | M4.2 + M4.3-CONTEXT |
| M4.3-QUALITY | C8 scoped review; авторы исправляют | Проверенные failure/concurrency границы и короткий предметный eval; при необходимости минимальная понятность статуса в существующей Console | Тесты пишутся в каждой задаче; итог на runtime candidate |
| M4-ACCEPTANCE | C0; C6/operator; C8 по дельте | Штатные CI, ограниченный живой synthetic диалог, main verification и короткая передача в M5 | Принятый кандидат, ключ/допустимый маршрут/действующая TEST среда |

Соответствие старому плану: CONTRACT = M4.1; PROBE = M4.2;
CONTEXT/RUNTIME/QUALITY = детализация M4.3. Новых продуктовых milestones нет.

### M4.1-CONTRACT — сначала минимальный интерфейс

Реализовать реально используемые DTO и вызов через adapter contract: messages,
явно разрешённые read tools/schema, модель/маршрут, deadline/token limits,
typed result/refusal/error/usage. Provider-specific поля локализованы в adapter.
Prompt и schema — versioned files, небольшой config — typed config, а не registry
с CRUD/UI/DB. Прописать совместимость полей для выбранных кандидатов: неподдерживаемые
tools/schema/limits дают понятный отказ, а не тихую потерю параметра.

Fake adapter нужен для обычного ответа, tool round-trip, invalid/truncated JSON,
refusal, 429/5xx/timeout и неизвестной стоимости. Это реализация контракта для CI,
не доказательство настоящего API и не фиктивный direct provider.

Предлагаемый первый write-set: новый backend/src/asm/ai/ с минимально нужными
файлами и относящиеся к ним tests/test_m4_*.py. C0 перечисляет точные файлы до выдачи.
Existing manifests/locks/config wiring — только если реально нужно и отдельно
включено в write-set. В этой задаче нет migrations, live activation, нового UI
или изменения M3 guards.

### M4.2-PROBE — проверить внешнюю зависимость рано

Polza — выбранный первый кандидат по desk research, ещё EVAL_ONLY.
Не создавать аккаунты всех агрегаторов. GPTunnel либо другая альтернатива
проверяется только при конкретном препятствии/непригодном результате Polza.

До платного вызова владелец предоставляет выделенный secret через штатный
локальный secret path и подтверждает сумму. Предлагаемый первоначальный предел
100–300 ₽; не пополнять/не тратить автоматически. В Git/CI ключ не попадает.

Одна воспроизводимая команда пробника:
- получает/фиксирует актуальные ID, official upstream, pricing/currency и capability
  metadata аккаунта; unofficial providers выключены, route закреплён;
- проверяет openai/gpt-6-luna и google/gemini-3.8-flash на одинаковых русских cases:
  краткий ответ/уточнение, неизвестная цена, owner facts, изменение контекста,
  недоверенные инструкции, handoff, JSON и реальный tools→result→ответ;
- проверяет несколько synthetic image inputs для ранней проверки M5 capability.
  Это не Vision runtime и не обработка реальных фото клиента;
- записывает request/call counts, correctness, observed latency и usage/списание
  без частного содержимого. Небольшая выборка 20–30 cases — ориентир, не SLA;
  критические/нестабильные случаи повторить, указать N для p50/p95;
- фиксирует выбранные route/model/prompt/schema revisions, ограничения, бюджет
  фактических вызовов, правила отключения и отсутствие неразрешённого fallback.

Сначала критерии пригодности, затем сравнение стоимости прошедших моделей.
Не объявлять качество доказанным по одиночному «привет». Provider capabilities
«unknown» не означают PASS; игнорирование max_tokens/strict schema недопустимо
маскировать «совместимостью OpenAI». При необходимости выберите другую модель
либо явный bounded local validation режим с соответствующим evidence.

Проверять доступность Polza с нужного backend environment, не только с ПК.
Работающий Telegram relay не означает разрешение отправлять через него AI traffic.
Менять egress/VM можно только отдельной малой выдачей при подтверждённом блокере.
До допуска реальной переписки использовать synthetic content.

### M4.3-CONTEXT — правильные факты до хорошей формулировки

Переиспользовать parse_snapshot/TurnSnapshotV2/V3 из conversations/turns.py,
parse_guarded_snapshot из guards.py, owner context из native_context.py,
material состояния и уже принятые observation/control tokens.
Строить bounded context с источниками/пределами; не добавлять raw Telegram fetch
или лог всего Workspace. Отсечение истории не должно незаметно удалять важные
owner facts или скрывать неполноту; при нехватке безопасного контекста — уточнение
или handoff, без обязательной дополнительной summary-модели.

Инструменты читают только уже реализованные данные этого разговора/бизнеса.
Один полезный current-context/history read tool достаточен; второй — лишь при
доказанной необходимости. Не придумывать ServiceCatalog/Quote repositories,
пустые будущие таблицы или универсальный SQL-инструмент ради tools demo.
Workspace/Client/conversation связывает сервер, каждое чтение авторизуется заново.
Не выдавать другим клиентам owner-only заметки, billing, секреты или служебные поля.

Schema результата минимальна: выбранное reply/handoff/no_reply, текст если нужен,
причина и небольшие extracted facts при необходимости. Schema валидность не
доказывает истинность ответа. Derived facts привязаны к источнику/текущему run;
не записываются как утверждённая цена, длительность или готовая ServiceRequest.
Владелец продолжает работать в существующем разговоре/Action Center.

### M4.3-RUNTIME — подключить действующий AI, сохранив M3

**Обязательный обнаруженный разрыв:** M3 consumer CONTROLLED_GUARDS_V1 и
consume_guarded тестовые; begin_guarded_send принимает только CONTROLLED provider.
0010/0013 закрепляют эту границу в SQL. Нельзя открыть Telegram снятием одного
if, подменой provider или использованием owner manual-send от имени AI.

C4/C2/C3 сначала согласуют короткую дельту: настоящий AI consumer/job, durable run
и result, авторитетная admission/generation проверка и создание ровно одного
канонического send intent. C2 назначает следующий свободный migration revision
по фактическому main; применённые 0001–0013 не правятся. Не фиксировать число
новых таблиц заранее: нужны только данные для реального recovery/trace.
Existing controlled tests остаются честно controlled и проверяются отдельно.

В runtime обязательны:
- lease/restart/replay на существующих durable Jobs; bounded loop, одна терминальная
  запись результата или понятный отказ. Persist before publishing send intent;
- проверка актуальной authority/context/native policy перед моделью/tools,
  сохранением результата и отправкой; takeover/new input/native event/Resume ABA
  не должны оживить старый run;
- свежие Telegram permission/delivery gates как у принятого живого пути,
  обязательные deadlines и отсутствие скрытого SDK send retry;
- короткие DB-транзакции; LLM HTTP снаружи. Ручные ответы/inbound не ждут окончания
  единственного занятого LLM worker;
- state-changing effects только у доверенного runtime. Handoff проходит существующий
  escalation command; read tools остаются read-only. Не строить новое уведомление;
- UNKNOWN после возможного send сохраняется после restart и не переотправляется.
  Повтор не создаёт второй Outbox intent/альтернативный уже принятый текст;
- finite tokens/time/call/spend limits, typed provider errors и trace без secrets,
  chain-of-thought и лишней копии переписки. Missing cost != 0;
- AI default disabled до отдельного TEST enable; при отключении остаются
  ручная переписка и текущий durable state. Rollback не удаляет receipts/migrations.

Начальный ориентир ограничений из IMPL-004 уточняется по пробе. Не нужен новый
Redis/broker, отдельный SaaS billing, custom provider-health framework или
автоматическое переключение на другой data route.

### M4.3-QUALITY — проверять поведение, не наращивать счётчик тестов

Автор проверяет свой срез сразу. C8 независимо смотрит конкретную изменённую
границу; review автора нельзя назвать независимым C8.
Использовать существующие PostgreSQL/worker/browser harnesses, маленький набор
JSON fixtures/eval script. Новая общая eval-платформа не требуется.

Обязательная матрица результата (одно место, здесь):

| ID | Что должно быть доказано | Нужное evidence |
|---|---|---|
| A01 | Выбранный реальный route умеет нужные tools/schema/limits; usage и цена понятны, неразрешённого fallback нет | Synthetic paid probe + adapter contract/failure tests; условия маршрута отдельно от технической пробы |
| A02 | AI использует текущие owner/canonical facts, явно учитывает недоступное/заменённое фото и неполноту; не выдумывает услуги/цену/запись | Context fixtures + реальные model cases |
| A03 | Tenant/client isolation, read permissions и revoked authority проверяются сервером; prompt injection не открывает чужие данные или mutation | Реальные PG/API negatives + agent/tool boundary tests |
| A04 | HUMAN/takeover, new input, edit/delete/native barrier и separate Resume не допускают stale send | PG/worker concurrency, границы actual AI consumer; существующие M3 guarantees сохранены |
| A05 | Duplicate jobs/restart после model result и неоднозначный Telegram send не дают второго intent/повторной отправки | Durable PG + controlled wire: возможный send → потеря ACK → restart → persistent wire count остаётся 1 |
| A06 | 429/5xx/timeout/refusal/invalid output/oversize/exhausted budget заканчиваются ограниченно; ручной путь не блокируется | Adapter/job failure tests + проверка параллельного manual/inbound пути |
| A07 | Реальный короткий русский сценарий проходит: уточнение → ответ из фактов или handoff, структурированный результат правдоподобен | Версионированный небольшой eval; модель/route/prompt/schema/N/cost/latency указаны |
| A08 | Оператор понимает enable/disable и ограничения; принятый код работает в LOCAL/TEST, actual main CI соответствует интеграции | Ограниченный synthetic live smoke + CI/операторский receipt, без production claims |

Производные новые race matrices вводить только для конкретного незакрытого риска.
CI без внешних платных API, deterministic fixtures не выдавать за real model proof.
Сначала targeted tests, затем штатный full candidate CI. Не менять критерии,
grants или общий timeout ради зелёного результата и не гонять неизменный CI лотереей.
При нескольких падениях перечислить все группы и исправлять первопричины.

### M4-ACCEPTANCE — закончить этап, не расширяя его

C0 принимает C8 findings по фактическому scope и один конечный candidate.
C6 готовит короткий preflight/deploy/disable для существующей TEST среды и ключа:
актуальный source/schema/environment/binding/сроки policy, только нужный route.
Старые VM команды не повторять без проверки; merge сам VM не обновляет.

Владелец подтверждает ограниченный сценарий: новое synthetic обращение →
AI уточняет/отвечает → HUMAN takeover → owner context → отдельный Resume →
ответ с актуальными фактами, без повтора старого. Не загружать реальные фото/данные
до разрешённого scope. C0 заранее выдаёт точные ожидаемые наблюдения, а не длинный
ручной чек-лист всех автоматических race tests.

Merge по действующей процедуре владельца, затем читать штатный CI actual main.
Не добавлять новый документационный коммит только для записи собственного SHA.
Короткий итог/ссылка на evidence в PR + единое обновление register/handoff достаточны.
M4 VERIFIED только после A01–A08 в заявленных границах; отсутствие полного data
допуска явно оставляет real-client rollout закрытым, но не подменяет synthetic TEST.
Передача M5: проверенная модель/route, ограничения image capability, текущий SHA,
контракт read tools и список действительно отложенных работ.

## Как C0 ведёт этап без повторения путаницы M1/M3

1. Первым сообщением — фактическая база, что уже принято и один ближайший результат.
   План/IMPL-004 и M4.1 приняты; текущая выдача M4.2-PROBE выше. Не открывать все чаты разом.
2. Перед каждой задачей показать понятную пользу для пилота, необходимость сейчас
   либо возможность отложить. Выдать ID/base SHA/точные paths/dependencies/criteria.
   C2 контролирует миграции; общие файлы не редактируются параллельно.
3. Сохранять один активный блок выдачи, короткий registry summary и ссылки на
   результаты. Завершённые verbose логи — в PR/artifacts, не новые сотни страниц
   инструкций с несколькими взаимоисключающими CURRENT.
4. Scope creep/тупик: назвать проблемный invariant, полученное evidence, ограниченное
   исправление и более простой вариант. Пересмотреть ошибочное решение через ADR,
   но не скрыто ослабить RLS, takeover, no-resend или утверждённый native context.
5. Продолжать уже разрешённые read-only/reversible работы самостоятельно.
   Пользователь нужен для credentials/budget, разрешённого live scope, фактического
   owner smoke и merge по текущей процедуре, не для пересылки технических догадок.

## Непосредственное следующее действие

C4 выполняет единственную M4.2-PROBE от принятого actual main: adapter, offline
checks и воспроизводимая команда с secret инструкцией/лимитами. Первый возврат —
REVIEW / PAID PROBE NOT RUN; C0 принимает подготовку, затем владелец подтверждает
бюджет. До этого не запрашивать ключ в чат, не делать paid calls/VM activation.
C1/C2/C3/C5/C6/C8 HOLD; M4.3 ждёт реальной проверки внешней зависимости.
