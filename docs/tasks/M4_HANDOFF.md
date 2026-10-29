# M4 — подключение ИИ к текущему контексту

Дата подготовки: 2026-10-28. Ведущий: C0; основной исполнитель: C4.
**План принят C0 и интегрирован в PR #37. Реализация — по CURRENT реестра.**
Единственный статус исполнения — [TASK_REGISTER](../TASK_REGISTER.md).
Решение по scope: [IMPL-004](../decisions/IMPL-004-m4-pilot-ai.md).
Выбор API: [исследование 24 сервисов](../research/M4_AI_PROVIDER_REVIEW_2026-10-28.md).

## Текущая выдача — M4.2-PROBE-THIRD-CANDIDATE-R1 / C4 / 2026-10-29

**Результат и польза:** включить выбранный владельцем
`deepseek/deepseek-v4.1-flash-1017` в то же ограниченное сравнение с
`openai/gpt-6-luna` и `google/gemini-3.8-flash`. Это позволит проверить качество
и стоимость третьего кандидата до выбора одной runtime-модели. Добавление модели
в whitelist ключа само по себе не меняет двухмодельный CLI. Рынок заново не исследовать.

### База, состояние и порядок передачи

- Repository: **Elefesys/ai-service-manager**.
- Accepted actual main: **51d7d73752128715c6d98157445167c0cc0d894d**,
  tree **411636a3614529077f6d0d230c62d11f69da600f**; M4.1 принят, PR38 merged.
- Reviewed preparation / repair base: **9024b8e062c712e1e69124db7d7eea5ee2de9491**,
  tree **73d1e313732b55dc5719550ca06f641be203f410**, existing Draft [PR39](https://github.com/Elefesys/ai-service-manager/pull/39).
  [CI40822050930](https://github.com/Elefesys/ai-service-manager/actions/runs/40822050930):
  exact head, attempt1, **11/11 SUCCESS**; подготовка принята C0 для preflight,
  не live M4.2 и не независимый C8. Повторять CI старого кандидата не нужно.
- Рабочая ветка **c4/m4-2-probe-third-r1**, отдельный checkout, от C0 docs seed
  с sole parent repair base выше. Полный стартовый SHA дан в передаче C0.
  Сохранить всю ancestry; main и ветку существующего PR39 сейчас не двигать.
- Зависимости: AGENTS, CURRENT, IMPL-004 с поправкой ниже; Spec §7.2/7.6/7.7/7.16/7.21,
  ADR-023/024/026/180/259/260/261/267. Общие Gateway/DTO/prompt/schema и M3 не меняются.
- Владелец сообщил: баланс пополнен на100 RUB, отдельный ключ создан, третья модель
  добавлена в его whitelist. Секрет C0/C4 не передавался; параметры ключа и actual
  account catalog ещё не проверены. Платный запуск не выполнен и пока не допущен.
  Предыдущую двухмодельную preflight-команду пока не запускать: после R1 получаем
  одним GET каталог для всех трёх. Размещение ключа остаётся private, Windows ACL
  проверяется до записи значения; в чат/Git/CI/argv ключ не передавать.

### Точный write-set C4

- `backend/src/asm/ai/polza.py` — фиксированный список трёх кандидатов;
- `backend/src/asm/ai/probe.py` — plan/preflight/admission/summary для трёх,
  полная сумма резервов и согласованные конечные пределы;
- `tests/test_m4_polza.py`, `tests/test_m4_probe.py` — соответствующие проверки;
- `docs/runbooks/M4_POLZA_PROBE.md` — согласованные числа, три RouteReview,
  точные команды и сохранённая private secret процедура;
- `docs/TASK_REGISTER.md` — только строка M4.2-PROBE в CURRENT;
- `docs/tasks/M4_HANDOFF.md` — короткий receipt под этой выдачей.

Fixtures `tests/fixtures/m4_probe_cases.json`, settings.py, manifests/locks,
Gateway/contracts/fake/prompt/schema, CI/Docker, UI, DB/migrations и M3 wiring
не менять. При конкретной несовместимости вернуть C0 факт/источник и минимальную
необходимую дельту; не подменять модель/route и не ослаблять strict validation.

### Согласованная дельта и критерии завершения

1. Порядок моделей ровно: `openai/gpt-6-luna`,
   `google/gemini-3.8-flash`, `deepseek/deepseek-v4.1-flash-1017`.
   Это явный finite allowlist, не registry, auto-selection или fallback.
   Каталог, три RouteReview, их freshness/fingerprints и returned route проверяются
   для каждого кандидата. Неполный/дублированный/иной набор не допускает генерации.
2. Сохраняется полный одинаковый набор: 20 text cases, три critical repeats,
   две PNG fixtures на модель. Итого **75 scenarios**, максимум **81 model HTTP**
   (27 на модель, включая два tools round trips), **6 fixture READ**.
   C0 явно меняет старый потолок80 на81 из-за третьего кандидата; запасных
   retry/repair calls нет. Не убирать кейс или проверку для сохранения старого числа.
3. Все расчёты/admission/CLI/summary должны согласоваться с тремя моделями:
   общий token reservation ceiling **2695680**, input/output **32768/512** на call,
   wire **24576/32768 bytes**, **60s** на сценарий, **1800s** на весь live run.
   Денежный потолок **100 RUB суммарно** сохраняется. До HTTP проверить полный
   резерв всех81 calls по actual account tariff, не распределять100 на каждую модель.
   Дефицит бюджета или неизвестная тарификация => STOP/возврат C0.
4. Требования official upstream, no fallback/unofficial, native schema+READ,
   включая root anyOf, token/image/billing proof сохраняются и для DeepSeek.
   Публичная карточка подтверждает существование ID, но не capability выбранного
   account route. Нет live pass по fake fixtures, отзывам или низкому ценнику.
   При первом quality/contract/accounting отказе остановить расходы и честно
   показать непройденные случаи; отсутствующие/UNKNOWN данные не считать нулём.
5. Полный controlled HTTP run через настоящий Gateway должен дать75 проверяемых
   synthetic finals,81 POST, один admission catalog GET,6 READ и по25 completed
   для каждой модели; selected_model остаётся null до C0 review реальных finals.
   Проверить, что третий кандидат входит в reservation/cost/N и fingerprint checks.
   Отрицательные проверки: неверный/неполный третий review до генераций,
   бюджет>100 либо недостаточный полный резерв до HTTP, попытка82 доHTTP,
   UNKNOWN usage/cost/timeout без возврата резерва и скрытого повтора.
6. Сначала targeted четыре существующих M4 suites, Ruff/format/mypy, `--plan`
   без сети/secret, diff check. Return: полный head/tree, diff, команды/результаты,
   dry-run plan и оставшиеся account blockers; **REVIEW / PAID PROBE NOT RUN**.
   После source review C0 переносит согласованный candidate FF в существующий
   PR39 и использует один штатный full CI этого изменённого кандидата.
   Новый PR, force-push, rerun старого CI или merge не нужны; merge у владельца.

После R1: C0 выдаёт Windows-команду private key/preflight на принятом candidate,
сверяет actual catalog, показывает рассчитанный резерв и получает финальный
допуск владельца на платную пробу. ВМ/Telegram/БД/runtime остаются вне этого шага.
C1/C2/C3/C5/C6/C8 и M4.3 HOLD; одна матрица A01–A08 ниже без изменений.

### Receipt C4 — THIRD-CANDIDATE-R1 / 2026-10-29

**REVIEW / PAID PROBE NOT RUN; C4 HOLD для C0.** От seed
`0563d6d3916a4557ab0526f61d437d4746e7fb28` в `c4/m4-2-probe-third-r1`
подготовлены ровно три кандидата:75 scenarios/81 calls/6 READ,
2695680 tokens и общий потолок100 RUB; fixtures/контракты не менялись.
201 targeted tests, Ruff/format, mypy71, offline plan и diff check PASS.
Controlled HTTP через CLI/Gateway:75 finals,81 POST,1 GET,6 READ,N=25 на модель;
third-review/fingerprint, общий бюджет,82-я попытка и UNKNOWN/timeout negatives PASS.
План/команды и private key процедура — в [runbook](../runbooks/M4_POLZA_PROBE.md).
Actual account catalog, official routes/native schema+tools/image/token/billing
proof и owner paid admission остаются непроверенными; selected_model=null.
Full CI нового кандидата не запускался: C0 review → FF в существующий PR39 → CI.
PR39/main не сдвинуты; новый PR/merge/paid calls/VM activation не выполнялись.

### Исторический receipt C4 — двухмодельная подготовка / 2026-10-29

**REVIEW / PAID PROBE NOT RUN; C4 HOLD для C0.** В разрешённом write-set
подготовлены Polza adapter, private settings, finite CLI, synthetic cases и
[runbook](../runbooks/M4_POLZA_PROBE.md) с точными plan/preflight/live командами.
177 targeted tests, Ruff/format и mypy71 PASS; локальный Docker NOT RUN
(executable отсутствует). Один штатный full CI и full head/tree — в Draft PR.
План: 25 scenarios на модель (20 text +3 repeats +2 images), ≤54 model HTTP,
≤4 synthetic READ, ≤1800s; предложение ≤100 RUB, фактический тариф пока UNKNOWN.
Ключ/платные вызовы/runtime не включены. Account catalog, official route mapping,
точная native schema+tools, token/image и billing bounds требуют подтверждения;
неизвестность закрывает paid admission. Принятые Gateway/DTO/prompt/schema не менялись.

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
локальный secret path и подтверждает сумму. Предлагаемый суммарный предел100 ₽; не пополнять/не тратить автоматически. В Git/CI ключ не попадает.

Одна воспроизводимая команда пробника:
- получает/фиксирует актуальные ID, official upstream, pricing/currency и capability
  metadata аккаунта; unofficial providers выключены, route закреплён;
- проверяет openai/gpt-6-luna, google/gemini-3.8-flash и добавленный владельцем
  deepseek/deepseek-v4.1-flash-1017 на одинаковых русских cases:
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

C4 выполняет единственную M4.2-PROBE-THIRD-CANDIDATE-R1 от точной repair base
и C0 seed выше: три кандидата,75 scenarios/81 calls,100 RUB общий потолок.
Возврат REVIEW / PAID PROBE NOT RUN; C0 принимает delta/CI, затем account preflight
и конкретный бюджет. Ключ уже создан владельцем; не запрашивать его в чат и не
делать paid calls/VM activation до допуска.
C1/C2/C3/C5/C6/C8 HOLD; M4.3 ждёт реальной проверки внешней зависимости.
