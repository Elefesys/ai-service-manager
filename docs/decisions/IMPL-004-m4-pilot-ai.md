# IMPL-004 — минимальный AI runtime для M4

Дата: 2026-10-28. Владелец решения: C0.
**Статус: ACCEPTED C0 / scope REVISED.** Принято C0 2026-10-28 в
[PR #37](https://github.com/Elefesys/ai-service-manager/pull/37), затем слито владельцем.
Решение ограничивает исполнение M4; приёмка и интеграция документа не означают
live API PASS или готовность пилота.
Текущий план: [M4_HANDOFF](../tasks/M4_HANDOFF.md).
Сравнение рынка: [исследование](../research/M4_AI_PROVIDER_REVIEW_2026-10-28.md).

## Проблема и необходимый результат

После M3 есть принятые conversation/context/control/admission механизмы, но нет
настоящего AI runtime. Пилоту нужен один агент, который читает доступный текущий
контекст, уточняет неизвестное, готовит ответ и при необходимости передаёт
разговор владельцу. Не нужен отдельный продукт управления сотнями моделей.

Baseline v0.28 полезен как исходник, но перенос всех registry/routing/agent
абстракций до первого реального диалога создаёт лишнюю работу. Кроме того,
защищённый consumer M3 сейчас CONTROLLED, а не готовая Telegram-интеграция LLM:
в guards.py указан CONTROLLED_GUARDS_V1, consume_guarded возвращает тестовый
текст, begin_guarded_send в messaging/database.py отклоняет permit не CONTROLLED.
Соответствующий SQL-контракт закреплён применёнными миграциями 0010/0013.
Просто заменить текст ответа или отключить проверку provider недостаточно.

## Решение для пилота

| Область | M4 | Отложено |
|---|---|---|
| Провайдер | PolzaAI — первый API-кандидат; одна прошедшая проверку модель в runtime. GPTunnel — альтернатива при конкретном провале/неподходящих условиях Polza | Одновременная интеграция каталога агрегаторов |
| Ветви | Узкий provider-neutral контракт сохраняет различие RU_AGGREGATOR / DIRECT_PROVIDER; конфигурация изолирована от business logic | Реальный direct adapter и live переключение между двумя ветвями до доступного разрешённого аккаунта/конкретной потребности |
| Профили/версии | Небольшая типизированная конфигурация, versioned prompt/schema в Git, разрешённые endpoint/model/upstream и лимиты; каждый run закрепляет использованную ревизию | DB/UI registry, hot routing по Workspace, dynamic marketplace, общая release-management платформа |
| Агент | Один ConversationAgent, один обычный model call, дополнительный после read tool при необходимости | Multi-agent, обязательные classifier/extractor/summary вызовы на каждый Turn |
| Tools | Один-два узких read-only инструмента над уже реализованными данными; авторизация на сервере | SQL/HTTP/browser/code execution от модели, изменения услуг/цен/записи/платежей |
| Структурированный результат | Минимум reply / handoff / no_reply и при необходимости небольшие extracted facts с происхождением; schema validation | Полная ServiceRequest/Quote/Order модель и фиктивные записи будущих этапов |
| Контекст | Существующий TurnSnapshotV2/V3, owner-confirmed context, material/native ограничения и актуальная авторизация | Новый сборщик полной Telegram-истории, автоматическое summary при каждом сообщении |
| Durable state | Минимальные AIRun/call metadata, выбранный результат, связь с существующим Job/Turn/Outbox; PG-транзакции только на короткие локальные операции | Новая очередь/broker/event bus/microservice, отдельный trace warehouse |
| Отправка | Узкий настоящий AI consumer + Telegram admission через сохранённые гарантии M3, additive migration при необходимости | Обход через manual-owner send, отключение guards, новый messaging engine |
| Vision/RAG | Несколько synthetic image probes выбранного API, чтобы рано узнать ограничения | Клиентский Vision runtime/портфолио/KB/embeddings — M5; генерация изображений позже |
| Интерфейс | Существующая переписка, HUMAN/Resume/Action Center; небольшой индикатор/ошибка только если оператору иначе не понять состояние | AI admin console, routing UI, новый dashboard |
| Эксплуатация | Конечные limits, разрешённый secret и approved route, одна операторская процедура enable/disable, метрики вызова | Production rollout и перестройка VM/PC-маршрута в этой задаче |

Вторая ветвь не удалена из продуктового направления. Её рабочая реализация и
проверка явно перенесены; конфигурационный контракт не выдаётся за работающий
direct adapter. Если необходим direct уже для данного пилота, C0 открывает
отдельную ограниченную задачу после подтверждения доступности и маршрута.

## Правила runtime, которые нельзя заменить prompt-инструкцией

1. Снимок контекста строится сервером из разрешённого Workspace/Client/conversation.
   Модель не выбирает tenant, чужой Client, произвольный ID/URL или SQL.
   Поступивший текст, tool arguments/results и изображения — недоверенные данные.
   Owner context содержит подтверждённые факты, но не право менять system policy.
2. Перед внешним model call, исполнением read tool, принятием результата и
   финальной отправкой проверяется применимая текущая authority/generation/policy.
   Изменение context/control/native observation делает старый результат
   непригодным. Не обещать отзыв уже ушедшего HTTP-запроса или сообщения после
   принятой в M3 точки начала внешнего эффекта.
3. Сохраняются HUMAN takeover, отдельный Resume, observation barrier и owner
   reconciliation. MEDIA_REPLACED_UNAVAILABLE не превращается в старое актуальное
   фото; отсутствие покрытия истории видно модели и оператору. Не заявлять Vision
   по одному наличию caption или URL.
4. Model output не устанавливает цену, длительность, booking или оплату.
   В M4 нет опубликованного каталога/ценовых правил M5/M6: неизвестное явно
   уточняется/передаётся владельцу, а не дополняется вымышленными услугами.
   Derived facts — не авторитетное business state и не новая универсальная CRM.
5. Runtime валидирует предложенный handoff и использует существующий escalation
   path; модель не получает mutation tool. Ответ отправляет доверенный runtime
   после admission, а не сама модель. Read-only tools не запрещают эти необходимые
   системные действия, запись trace или Outbox.
6. Реализовать одну устойчивую связь turn/run/result/send intent. После фиксации
   результата повторный job не генерирует другой текст для уже принятого intent.
   Потеря ответа после возможного Telegram send остаётся UNKNOWN/no-resend.
   LLM timeout/неизвестное списание отдельно от неопределённой доставки Telegram.
7. Внешний HTTP не держит DB transaction/lock. Медленная LLM не занимает единственный
   обработчик ручных ответов/inbound: использовать ограниченную конкуренцию или
   выделенный AI worker на существующих durable Jobs, без нового брокера.
8. Число вызовов, выходные токены, контекст, wall-clock deadline и расход ограничены.
   Стартовый ориентир: обычный путь 1 call, при tools 2, общий потолок 3 model calls
   на run, включая repair/retry, до 4 read tool executions. Точные значения
   утверждает C0 по пробе, не поднимает бесконечно ради PASS. SDK retries не
   должны незаметно обходить общий бюджет. Exhaustion имеет один terminal outcome.
9. Строгий local schema/DTO check обязателен даже при provider structured output.
   Invalid/refusal/truncated/oversized response не приводит к сырой отправке.
   Минимальный trace: run/turn/config revisions, provider/model/upstream,
   outcome/errors, timings, usage/currency/confirmed cost либо UNKNOWN.
   Не хранить chain-of-thought, секреты и лишние копии переписки в логах.

## Маршрут и выбор модели

Исследование даёт рекомендацию **Polza-first**, не контрактную сертификацию.
Начальные EVAL_ONLY кандидаты: openai/gpt-6-luna, google/gemini-3.8-flash
и deepseek/deepseek-v4.1-flash-1017.

**Поправка C0 от2026-10-29 по явному выбору владельца:** добавлен третий
кандидат DeepSeek. Сохраняется одинаковый finite набор25 scenarios/27 model calls
на модель; итого75 scenarios/81 calls, общий предложенный потолок100 RUB.
Это заменяет двухмодельную выборку50/54 и её ceiling80; paid admission требует
актуального расчёта, route proof и финального допуска владельца.
[Публичная карточка Polza](https://polza.ai/models/deepseek/deepseek-v4.1-flash-1017)
подтверждает ID, не заменяя account tariff/capability evidence. Никаких новых
adapter branches, runtime fallback, registry или Vision runtime эта поправка не включает.
Выбирается самая дешёвая из прошедших предметную проверку; нельзя заключить,
что первая лучше отвечает по одному ценнику.

До paid probe владелец задаёт отдельный ограниченный ключ и бюджет. Каталог
аккаунта подтверждает точные upstream IDs, capabilities, цену и валюту.
Для Polza: не разрешать unofficial providers, закрепить разрешённого поставщика,
запретить незаданный fallback. При невозможности соблюсти маршрут — явный отказ,
не переход на «самый дешёвый доступный». Изменение провайдера допускается вручную
для новых runs после проверки; старый run не продолжается на другом маршруте.

Для реальной клиентской переписки нужна проверка условий gateway/upstream и
допустимых данных. Рублёвая оплата и российский домен этого не доказывают.
Пока это не закрыто, проба использует только synthetic TEST. Никакая новая
compliance-платформа не требуется: короткая запись фактов/ограничений достаточна.

**Уточнение C0 от2026-10-29 после catalog preflight (M4.2-PROBE-CATALOG-R1):**
адаптер может применять эквивалентную wire-обёртку `{result: ...}` с root object
для conversation_result_v1, поскольку canonical root anyOf не соответствует
документированному OpenAI Structured Outputs subset. Union, ограничения и
$defs/$ref сохраняются; после проверки envelope результат проходит прежнюю
local DTO validation. Canonical schema/prompt/contracts/gateway не меняются,
wire revision отражается отдельно. Это устраняет известное несовпадение формы,
но не доказывает live schema+tools compatibility. Иные ослабления не разрешены.
Публичный catalog snapshot подтверждает опубликованные metadata, но не
валидность ключа, его whitelist или индивидуальный account tariff.
Следующая ограниченная выдача C4 исправляет token-cap alias и применимые fees
по контракту; дублирующееся provider name без однозначного selector остаётся
BLOCKED. Три модели,75 scenarios/81 calls и предложенный общий потолок100 RUB
сохранены; live admission/расходы требуют прежнего отдельного допуска владельца.

**Поправка C0 от2026-10-29 — общий ceiling150 RUB:** после явной готовности
владельца увеличить бюджет C0 меняет предложенный программный потолок со100
на150 RUB для всех трёх моделей вместе. Это не150 на модель и не live approval.
Сохраняются75 scenarios/81 model calls/6 READ и все per-call limits.
Меньший explicit approved amount продолжает ограничивать ledger; неизвестные
route/billing facts, превышение150 и отсутствие допуска по конкретному plan
не разрешают paid HTTP. Условный минимум107.138276775 RUB из catalog snapshot
не является прогнозом списания или доказанным actual priced plan.

**Решение C0 от2026-10-29 — реальные Polza observations / EVAL_ONLY:** владелец
успешно выполнил отдельный synthetic GPT READ roundtrip: 2 POST,1 READ,валидный
final с текущим адресом; stage cost0.00895610 RUB, общий prior spend0.01269785 RUB.
Это не штатный Gateway/runtime acceptance; полное сравнение ещё NOT RUN.

Два предположения пробника пересмотрены на основании этого опыта. Отсутствующее
body `provider` допускается проверять через ограниченную официальную history API
по generation ID и согласованным model/usage/cost/finish. Request pin, body field,
observed history family и непроверенный variant записываются отдельно. History
OpenAI не доказывает flex. Present wrong provider не подменяется данными history;
неизвестная/противоречивая identity останавливает этап до следующего POST.
Это достаточный уровень наблюдения для synthetic EVAL_ONLY, не новое разрешение runtime.

Изменение только числовых ставок не требует повторного ручного review всего
каталога: при прежней reviewed model/unique official route, modalities и non-price
provider configuration пробник пересчитывает свежий резерв перед paid calls.
Fee schema/currency, input/output/reasoning/image assumptions и approved amount
продолжают ограничивать запуск. Старый snapshot и свежие цены сохраняются раздельно;
нет подмены hash/даты review или обещания фактической стоимости по публичному тарифу.
Полная проба использует остаток общего150 с учётом prior0.01269785, без нового150.
Конкретный write-set, limits history и checks — в CURRENT M4_HANDOFF.

**Решение C0 от2026-10-29 — исполняемый synthetic experiment:** предварительная
сертификация всех hosted route/token/image/billing properties не является
условием конечной пробы, предназначенной для их измерения. C0 разрешает отдельный
явный EVAL_ONLY experimental admission в существующем CLI с тремя фиксированными
official route selectors, fresh catalog, conditional budget и прежними hard limits.
Нельзя маскировать assumptions под существующий verified RouteReview, обновлять
дату старого review или считать conditional reserve гарантированным списанием.
Review-mode guards сохраняются; experiment не может быть APPROVED/runtime.

Для GPT сохраняется известная history family OpenAI. Для Gemini/DeepSeek, где
prior mapping неизвестен, family устанавливается как observation первого exact
generation ID с совпадающими list/detail/model/usage/cost/finish/attempts и должна
оставаться неизменной в рамках model eval. Requested selector остаётся config,
body label и observed history family — отдельными facts, variant — NOT_OBSERVED.
Нет auto-selection, fallback, retry, клиентских данных или runtime promotion.

Native tools continuation — часть необходимой совместимости: bounded opaque
Gemini thought_signature допускается transiently сохранить и вернуть только
соответствующему call_id в том же run/route; в logs/files/DTO её нет. Для DeepSeek
этот experiment явно использует non-thinking профиль при заявленной catalog
поддержке none/disable; raw reasoning не сохраняется/не передаётся через neutral
contracts. Все bytes и actual usage/cost проверяются прежними ограничениями.
Полный отчёт75 cases требует последующего ручного review C0. Общий150 включает
prior0.01269785. Точный scope/профили/негативные проверки — EXECUTABLE-EVAL-R1 в handoff.

**Решение C0 от2026-10-30 — synthetic quality flags и один reviewed prefix:**
полный owner R1 receipt b727cc1ca65c5ef189cc2bddba619136a354c6414b7159e0bde4d521f52f8b48
сверен:14 confirmed model calls/2 READ/12 finals, cost0.08303952 RUB.
Все12 finals вручную соответствуют synthetic fixtures. В injection regex500
пометил корректный отказ как FORBIDDEN_CLAIM. Запретить любое упоминание слова
не эквивалентно запрету утверждать неизвестный факт; удалять keyword или объявлять
всё с отрицанием безопасным также неверно.

В отдельном SYNTHETIC_EXPERIMENT required/forbidden patterns, expected semantic
outcome и image-fact checks сохраняются как quality flags для human review;
они не останавливают сбор оставшегося ограниченного сравнения. Ни отсутствие
flags, ни завершение всех calls не означает quality PASS/автоматический выбор.
Schema/protocol/route/history/metering/limits/deadlines и mandatory READ failures
остаются STOP. Reviewed/runtime admission не ослабляется. Raw finals/flags и
разные evaluator revisions сохраняются; новый платный semantic grader не нужен.

C0 разрешает подготовить одну bounded continuation по exact неизменённому receipt,
без replay уже оплаченных12 cases. Новые63 cases/67 POST/4 READ, original identities,
aggregate75/81/6; вместе с helper3 максимум84 POST. Старый helper cost0.01269785 +
R1 cost0.08303952 =shared prior0.09573737; новый stage≤149.90426263 в общем150.
Все confirmed calls считаются независимо от quality; unknown сохраняет резерв.
Imported prefix получает отдельный scoped C0 manual assessment, не переписанный
автоматический PASS. Новый stage имеет свой1800s deadline, прежние per-call caps
и fresh catalog/conditional plan; старый in-flight run не возобновляется.
Общий resume framework, arbitrary receipt adoption и автоматический повтор не входят.
Это решение о реализации; новый paid запуск — после C0 review конкретного candidate.
Точная выдача/негативные проверки/receipt format — QUALITY-CONTINUATION-R1 в handoff.

**Решение C0 от2026-10-30 — отдельный допуск standalone R2 при красном M3 gate:**
source cd60e5e16d8bcada53597d660a15f4d82640e956 прошёл source review,443 targeted,
2640 ordinary+155 subtests и actual R1 loader/control continuation. CI41009211185
остаётся FAILURE:10/11 jobs SUCCESS,803 PG PASS/1 FAIL. Единственный PG failure —
1.5s observer timeout в M3 controlled-activation-subscription; причина задержки
не установлена, assertions после освобождения lock не достигнуты. Secondary
completeness отказал; незавершённые foundation gates не считаются PASS.

C0 разрешает **один LOCAL synthetic CLI R2 / EVAL_ONLY** в ранее согласованном150
с новым остатком149.90426263, exact R1 hash,63 scenarios/≤67 POST/4 READ и прежними
per-call guards. Основание узкого допуска: изменены только probe/tests/docs;
M3/DB code неизменен, standalone probe не импортирует/не вызывает эти modules.
C0 independently выполнил real R1 +controlled67 POST при запрещённых импортах
sqlalchemy/psycopg/asm.foundation/auth/messaging/tenancy, real network и secret
file reads — PASS. Платных запросов эта проверка не выполняла.

Это явное исключение **только для существующего bounded EVAL CLI**, а не зелёный
CI, runtime admission, интеграция M3 или разрешение merge. Задача
C0-M4-CI-OBSERVATION-01 должна быть разобрана до merge/runtime, с сохранением
проверки настоящего lock wait и всех временных/продуктовых assertions. Полный
прогон ради случайного PASS не повторялся, тесты не ослаблялись. Подтверждение
новых Polza outputs/charges и выбор модели остаются после полного R2 review.

**Решение C0 от2026-10-30 — R2 Gemini STOP и узкая диагностика:**
разовый R2 допуск использован. Полная текстовая копия33 events проверена:
GPT25 scenarios/27 confirmed POST/2 READ, Gemini1 attempted POST/0 READ/0 final,
DeepSeek NOT_RUN. Summary/встроенный R1/новые flags воспроизведены offline.
GPT no_send_claim19 — реальный неверный outcome reply вместо handoff;
unknown_price22 содержит неподтверждённое обобщение. Whole-model quality PASS
и runtime selection не выдаются по одному technical completion.

Gemini остановлен локально на SIGNATURE_INVALID. Код проверяет signature до
сохранения response ID/metering и объединяет несколько причин в одном detail.
Actual wire shape неизвестен, поэтому нельзя объявить причиной missing field,
слишком большую подпись либо несовместимость модели. C4 получает только
M4.2-GEMINI-DIAGNOSTIC-R1: bounded safe diagnostics/metering на отказе, GET-only
history сверка и отдельный пока не разрешённый к live запуску one-POST план.
Новый общий resume, replay GPT, prompt/fixtures/profile changes не входят.
Runtime DTO/guards не меняются, подпись не логируется и не заменяется заглушкой.
Совместимость исправляется только по доказательству фактического wire format.

Shared confirmed0.17509189 RUB/30 calls +1 unknown Gemini, reserve3.464879664;
консервативный остаток общего150 —146.360028446. Unknown не превращается в0
или точное списание по одной оценке. Потерянный ID ограничивает history correlation:
совпадение model/time — candidate, не автоматическое погашение резерва.
Hash присланного текста R2 не считается hash оригинального Windows JSONL.
Оба отчёта сохраняются; новая paid операция только после review exact source
и конкретных caps C0 в уже согласованном бюджете, без повторного запроса150.
CI41009211185 и C0-M4-CI-OBSERVATION-01 остаются RED/OPEN перед merge/runtime;
эта диагностика их не закрывает и не даёт нового full-CI PASS.

**Решение C0 от2026-10-30 — один Gemini diagnostic после history UNKNOWN:**
owner GET-only receipt source68093c7 вернул HISTORY_PROVIDER_UNKNOWN после1 GET,
0 POST. В actual report нет значения/типа provider или конкретной выбранной row;
ни название с пробелами, ни отсутствие поля не объявляются установленной причиной.
Старый Gemini charge/response shape UNKNOWN, резерв3.464879664 сохраняется.

C0 разрешает один explicit diagnostic на source **68093c769f24ea63eca5185179c3eab5fafd1229**
по ref ONE_POST_R1_5RUB:1 catalog GET/≤1 Gemini POST/≤2 history GET/0 READ/follow-up,
120s overall, прежние per-call caps, stage conditional reserve≤5 RUB в общем150.
Основание: source review520 targeted PASS и controlled exact-arguments valid/
signature-failure/history-mismatch CLI, без реальной сети/key/DB/M3 действий.
Неизвестный старый charge не требует нового150 и не блокирует это измерение,
поскольку весь его reserve удерживается сверх confirmed0.17509189; новый reserve
проверяется до POST. Это отдельное наблюдение, не автоматический retry или R3.

Допуск узко расширяет текущий standalone EVAL_ONLY шаг; общий CI всё ещё RED,
full CI нового source NOT RUN, C0-M4-CI-OBSERVATION-01 остаётся до merge/runtime.
Provider validator не ослабляется, unknown route не сертифицируется; signed tool
continuation/READ не выполняются. После одного отчёта следующий paid шаг HOLD
до C0 review. Новый code/helper/общий resume в этом решении не создаётся.

**Решение C0 от2026-10-30 — diagnostic выполнен, следующий кандидат DeepSeek:**
четыре owner events source68093c7 подтверждают1 Gemini POST/1 catalog/1 history,
0 READ/follow-up. В tool call отсутствует extra_content (SIGNATURE_EXTRA_MISSING).
Gemini tool continuation на текущем adapter/route BLOCKED; другой carrier и
причина generic history-list failure не доказаны. Проверку signature/route не
отключать, dummy не вставлять, thinking/маршрут не менять. ONE_POST_R1_5RUB consumed.

Generation gen_2227371816211582977 имеет validated body354/172 tokens,
reasoning156 внутри output, reported0.05269262 RUB. History не сверена, поэтому
это не CONFIRMED charge. Shared known остаётся0.17509189/30 POST; два unknown
Gemini удерживают6.929759328, remaining142.895148782 в прежнем150. Original R2
unknown не сопоставляется с новым ID. Резервы не равны расходу/балансу аккаунта.

Для продвижения исходного сравнения C4 получает M4.2-DEEPSEEK-EVAL-R1: offline
подготовка одного finite DeepSeek-only25 cases/≤27 POST/≤2 READ, прежние fixtures,
prompt/schema/non-thinking profile и wafer/us. GPT не повторяется; Gemini пока
BLOCKED, не объявляется quality FAIL по protocol issue. Полное сравнение остаётся
незавершённым. Снятие Gemini blocker требует точного Polza protocol evidence,
а не ещё одного идентичного paid diagnostic. Новый общий resume не строится.

Новый runner обязан учитывать reviewed C0 prior32 POST/оба unknown reserve;
это явный accounting snapshot, не raw R2 hash и не импорт старых finals. Новый
stage budget≤142.895148782, fresh whole-stage reservation до POST, обе старые
неопределённости удерживаются. Existing model/runtime guards и acceptance остаются;
допустима только fixed safe детализация history STOP без новых HTTP. Source review
и готовая команда C0 нужны до live, бюджет150 заново не запрашивается. GPT quality
findings, RED CI41009211185 и C0-M4-CI-OBSERVATION-01 не закрываются этим шагом.

**Решение C0 от2026-10-30 — source DeepSeek принят, один OWNER stage:**
source **5f5ece5426d675559c15fe1b74561dc6dddd456a**, tree **a5709d7a304cdb87970f2a1dc7783b77eabaee13**,
sole parent2da7334e101f5de60771e869166a3ac86f38588e принят без code fixes.
Независимые616 targeted PASS, Ruff/format4/mypy71,6 offline plans;127 controlled
пар подтверждают неизменность history acceptance/error/GET counts. Exact CLI
source/ref/amount проверены для полного прохода, history STOP и budget rejection.
Реальные HTTP/owner key reads=0; Windows/live/full CI этого source NOT_RUN.

C0 разрешает **один** DeepSeek-only25 scenarios/≤27 POST/≤2 synthetic READ по
ref `C0-M4.2-DEEPSEEK-EVAL-R1:5f5ece5426d675559c15fe1b74561dc6dddd456a:OWNER_25_CASES_R1`.
Explicit stage ceiling142.895148782 — остаток прежнего150 после prior confirmed
0.17509189 и held6.929759328 за2 unknown Gemini; это не новый150 и не ожидаемый
расход этапа. Fresh reserve всех27 calls≤ceiling до POST; fixed wafer/us,
non-thinking/fixtures/prompt/schema и прежние caps сохраняются. Unknown и оба
old reserves не освобождаются автоматически. GPT/Gemini POST0; no replay.

Это scoped standalone EVAL_ONLY продолжение прежнего допуска, без application/
M3/DB/Telegram действий. PR39 Draft/headcd60 и RED CI41009211185 не становятся
accepted от этой проверки; C0-M4-CI-OBSERVATION-01 и полный CI нового source
нужны до merge/runtime. Полный новый report → C0 для manual quality review,
selected_model=null/runtime=false. После одного запуска новый paid шаг HOLD.

**Решение C0 от2026-10-30 — DeepSeek eval-r1 consumed, отдельный tool compatibility profile:**
Владелец передал полный7993-byte/5-event report source5f5ece5426d675559c15fe1b74561dc6dddd456a,
SHA256 b2e716a962a8966aaff61f8eb8cec57419ea4d2b7c1375caf8b6578ec08ebfcc.
1 POST/2 history GET/0 READ, schema-valid handoff «С»/«С», READ_ROUND_TRIP.
Только этот final получает manual QUALITY_FAIL; остальные24 scenarios NOT_RUN.
Usage575/31, reasoning0, finish_reason stop; history family Wafer, variant NOT_OBSERVED,
cost0.00423361 CONFIRMED. Shared confirmed0.17932550/31 known POST,2 Gemini unknown/
held6.929759328, всего33 attempts, remaining142.890915172 из прежнего150.
Старые unknown не погашены; исходный25-case допуск использован и не повторяется.

[Wafer Structured outputs](https://docs.wafer.ai/serverless/chat-completions#structured-outputs)
документирует JSON reply при auto+response_format и tool call при required/named,
когда response_format игнорируется. Наш исходный payload использует первую
комбинацию; наблюдение согласуется с этим ограничением, не доказывает внутренний
Polza path. [Combined capability flag](https://docs.wafer.ai/serverless/models#capability-flags)
не сертифицирует нужную auto-tools семантику. Причина однобуквенного final UNKNOWN;
местный parser не обрезает длинный текст в controlled проверке.

C4 получает M4.2-DEEPSEEK-TOOL-COMPAT-R1: offline подготовить отдельный opt-in
named read_current → history/validated synthetic READ → strict final с none.
Это **новый явно помеченный экспериментальный protocol profile**, не изменение
исходного auto eval и не обход его неуспеха. Успех такого профиля подтверждает
только управляемый roundtrip; автоматический выбор инструмента,25-case quality,
одинаковость сравнения моделей и runtime admission из него не следуют.

≤2 POST/1 READ/4 history GET/1 catalog, same32768/512 tokens и24576/32768 bytes,
model roundtrip60s/overall120s; подготовительный ceiling1 RUB из текущего остатка.
Новый prior33 attempts с обоими held, fresh reservation обоих calls до POST,
exclusive report, zero retry/fallback и новый exact-source C0 ref после review.
Сейчас paid POST0. Нельзя менять canonical prompt/schema/fixtures/contracts/Gateway,
ослаблять identity/metering/READ guards или вводить общий resume/framework.
Short-text/regex гипотеза не даёт допуска к изменению wire schema по догадке.

C0 воспроизвёл summary и4 CONTROLLED случая; real HTTP/owner key reads0.
Code не менялся; неизменённые616 targeted/full CI не повторялись. GPT quality
findings, Gemini blocker, Draft PR39/headcd60, RED CI41009211185 и
C0-M4-CI-OBSERVATION-01 сохраняются. Другие исполнители HOLD, следующий C4;
владелец не запускает старые команды. Новый бюджет150 не запрашивается.

## Что пересмотрено относительно baseline

Только scope исполнения M4 из Spec §7.2/7.6/7.7/7.16/7.21/7.22,
Roadmap M4 и Implementation Plan M4.1–M4.3:
- registry/release сущности сжаты до необходимой конфигурации и закреплённых версий;
- одновременно готовые RU и direct ветви перестают быть обязательным gate M4;
- устаревший shortlist заменён кандидатами для текущей проверки;
- явно добавлена необходимая реальная AI→Telegram граница вместо предположения,
  что controlled M3 уже является готовой live-интеграцией.

Сохраняются tenant/client isolation, RBAC/RLS, фактологические ограничения,
owner control, M3 native policy, authoritative PostgreSQL, durable recovery и
no-resend. Применённые миграции 0001–0013 и импортированный baseline не
переписываются. Этот документ — явная текущая поправка, а не изменение истории.
Ссылки OPEN-074/075 не закрываются результатами desk research.

## Принятие и пересмотр

C0 принял этот текст одним review перед кодом; решение и текущая выдача
зафиксированы в едином task register. Если конкретная гарантия baseline
требует более сложной реализации, сначала показать воспроизводимый риск и
минимальное решение; не реализовывать абстракцию только из-за её названия.
Изменённые границы должны быть видны пользователю. У уже согласованной задачи
не запрашивать повторное разрешение на каждую обратимую операцию.

До actual provider proof и финального M4 acceptance статусы задач остаются
TODO/IN_PROGRESS/REVIEW по фактам, а не «готово по архитектуре».
