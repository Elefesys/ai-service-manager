# IMPL-004 — минимальный AI runtime для M4

Дата: 2026-10-28. Владелец решения: C0.
**Статус: ACCEPTED C0 / scope REVISED.** Принято C0 2026-10-28 в
[PR #37](https://github.com/Elefesys/ai-service-manager/pull/37), затем слито владельцем.
Решение ограничивает исполнение M4; приёмка и интеграция документа не означают
live API PASS или готовность пилота.
Текущий план: [M4_HANDOFF](../tasks/M4_HANDOFF.md).
Сравнение рынка: [исследование](../research/M4_AI_PROVIDER_REVIEW_2026-10-28.md).
Последнее решение ниже: C2 R4 принят; C0 integration/full CI, main ещё BLOCKED.
Прежние exact-source owner допуски использованы; нового paid запуска нет.

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

**Решение C0 от2026-10-30 — source tool compatibility принят, один OWNER roundtrip:**
Source **5885df1b0ba04378e8af6f2089d2fc86be6c22e3**, tree **6ca70ba7f6d431accaa0478e1d515cc69ebae7b9**,
sole parent7e0870d8492d36a00ffac894e44b787c5af8ca47 принят без исправлений;
7-file write-set соблюдён. C0:711 targeted PASS11.25s, Ruff/format4/mypy71,
7 offline plans, прежние6 совпали с base. Все прежние polza definitions и
constants неизменны, probe меняет только opt-in Ledger/main; protected
contracts/prompt/schema/fixtures/gateway и зависимости не менялись.

Разрешён **один** standalone owner run по
`C0-M4.2-DEEPSEEK-TOOL-COMPAT-R1:5885df1b0ba04378e8af6f2089d2fc86be6c22e3:OWNER_ROUNDTRIP_R1_1RUB`.
Ceiling **1 RUB** из прежнего150, fresh reservation обоих calls≤1 до POST.
Один tool_current: named read_current → verified history/typed synthetic READ
→ none + strict final, ≤2 POST/1 READ/4 history GET/1 catalog, прежние
32768/512 tokens и24576/32768 bytes, roundtrip60s/stage120s. GPT/Gemini POST0.
Prior0.17932550/31 known +2 unknown held6.929759328,33 attempts, remaining
142.890915172; всего≤35 attempts, old holds не освобождаются. Отдельный
exclusive report, flush до HTTP, no retry/fallback/resume.

Exact CLI source/ref/amount проверены CONTROLLED positive, short-final,
late-history и budget-preflight исходами. Sockets/owner .env reads запрещены,
real HTTP0; Windows/hosted compatibility ещё NOT_RUN. Это не runtime approval.
PROTOCOL_OBSERVED требует manual review; quality flags и «С» не PASS.
После одного receipt paid HOLD до C0. Исходный auto eval failure, GPT quality
findings и Gemini blocker не переписываются; model selection=null/runtime=false.

Продолжается ранее принятый scoped EVAL_ONLY допуск. PR39 Draft/headcd60,
CI41009211185 RED и C0-M4-CI-OBSERVATION-01 сохраняются; full CI source5885df1
NOT_RUN и нужен до merge/runtime. Другие исполнители HOLD, следующий — владелец
по готовой команде. Main/VM/DB/Telegram/merge не меняются; бюджет150 заново не
запрашивается.

**Решение C0 от2026-10-30 — tool receipt reviewed; один GPT quality candidate:**
DeepSeek named profile source5885df1b0ba04378e8af6f2089d2fc86be6c22e3 выполнил
1 model POST/1 catalog GET/0 history/0 READ/0 follow-up. Полный7094-byte report
SHA2561b7addea429f9e53f1e5d0086d1cdf1f648c138747013efe25c4c2ff037cd1b3:
finish_reason=tool_calls, generation gen_2227402879917887489, но decode вернул
INVALID_PROVIDER_RESPONSE. Точная форма отказавшего call UNKNOWN;7 разных
CONTROLLED форм дают те же признаки, positive control проходит. Это не
доказательство неработоспособности tools у всей модели и не quality PASS/FAIL
несуществующего final. Одноразовый допуск consumed, repeat не разрешён.

Новый POST остаётся UNKNOWN с reserve0.190636257. Shared confirmed0.17932550/31,
unknown3 (2 Gemini +1 DeepSeek), held7.120395585, всего34 attempts, remaining
142.700278915 из прежнего150. Все held сохраняются; reported/unknown не считаются
списанием0. C0 проверил exact accounting/plan и8 controlled cases, не менял код
и не повторял неизменённый полный CI/711 targeted suite. Real HTTP/key reads0.

Цель M4 — один работающий provider. Дальнейшая Gemini/DeepSeek compatibility
DEFERRED для первого пилота до конкретного protocol evidence/потребности;
задачи BLOCKED и прежние результаты сохранены. Новые paid diagnostics и raw
capture не назначаются. Исходное75-case сравнение не завершено, selection=null.

C4 получает **M4.2-GPT-QUALITY-R1**: versioned conversation_v2 для explicit owner
contact → proposed handoff и запрета неподтверждённых business rules. Это
исправляет кандидат по сохранённым no_send_claim19 QUALITY_FAIL и unknown_price22
QUALITY_NOTE, а не переоценивает v1. Пустые flags/regex matching не заменяют
ручную оценку. v1, result schema, canonical fixtures и прежние modes неизменны.
По ADR-048 C0 явно разрешает узкий shared contract/Gateway scope: только закрытый
Literal v1/v2 и выбор одного из двух фиксированных bundled prompt files.
Никаких arbitrary prompt/path, нового registry или ослабления authorisation,
typed tools, result validation, route/history/usage/cost/limit guards.

Подготовить fixed GPT/openai/flex25-case mode с прежним auto-tools/provider profile,
≤27 POST/2 READ/54 history/1 catalog,60s/case и1800s/stage, прежние token/byte bounds.
Ceiling15 RUB из согласованного150; fresh reserve всех27 calls до POST, prior34/
max61 shared attempts и все3 old holds. Новый report exclusive, без imports/resume,
retry/fallback или автоматического model/runtime selection. Images сохраняют
synthetic_shapes_v1; text/tool config/wire/report pin v2. Сейчас live POST/GET0;
source review и exact-source C0 допуск требуются перед owner запуском, новый
бюджет не запрашивается. Write-set/verification в CURRENT M4_HANDOFF.

PR39 Draft/headcd60, CI41009211185 RED и C0-M4-CI-OBSERVATION-01 сохраняются;
интеграционный full CI нужен до merge/runtime. Main/VM/DB/Telegram не меняются.
Это подготовка нового EVAL_ONLY кандидата, а не готовый AI runtime.

**Решение C0 от2026-10-30 — GPT quality source принят, один OWNER stage:**
Source **ace29ce7d77564f8fecea84d4b7e734e6c8fbe56**, tree **8a716c528a917c8a77a853c226699ba4a47ccc2b**,
sole parent07e18c70b02a3739fbe640d28c41ec0341f8452d принят без code fixes.
11 разрешённых файлов; contract delta только Literal v1/v2, Gateway только
фиксированный prompt selection; polza.py/v1/schema/fixtures/прочие методы и
старые constants сохранены. conversation_v2 SHA256b420be44a7e4210de1151e5b0604b0fa9a08c19b1bfbedb8147f2a9b38455956.
Versioned policy уточняет proposed handoff при explicit owner contact и запрет
неподтверждённых business rules, сохраняя известные факты/обычные уточнения.

Независимо C0:799 targeted PASS13.15s, Ruff/format7, mypy71;8 actual offline plans,
первые7 JSON равны exact parent; wheel с byte-exact v1/v2. Exact source/ref/15 RUB
CONTROLLED CLI: полный25-case путь и retained quality finding, late history
mismatch, whole-stage budget STOP. Все3 old holds и exclusive report сохранены.
Audit guard запрещал sockets и owner .env reads; real HTTP/key reads0.
Actual Windows/hosted v2 quality/full CI этого source NOT_RUN.

C0 разрешает **один** GPT-only25-case stage по
`C0-M4.2-GPT-QUALITY-R1:ace29ce7d77564f8fecea84d4b7e734e6c8fbe56:OWNER_25_CASES_R1_15RUB`.
Ceiling15 RUB внутри прежнего150, fresh reserve всех27 calls до POST;
GPT/openai/flex/provider-default/auto,≤27 POST/2 READ/54 history/1 catalog,
60s/case/1800s stage,32768/512 tokens и24576/32768 bytes. Text/tool v2, images
synthetic_shapes_v1; прежние fixture identities/repeats/result schemas.
Prior31 known/3 unknown/34 attempts, confirmed0.17932550/held7.120395585,
remaining142.700278915; максимум61 attempts. Все old holds сохраняются,
новый known/unknown отдельно. Report exclusive, no retry/fallback/resume.

После одного report следующий paid шаг HOLD до C0 review. Technical completion
даёт HUMAN_REVIEW_REQUIRED, manual PENDING; selected_model=null/runtime=false.
Сохранённые GPT quality findings и Gemini/DeepSeek blockers не закрыты source
tests; comparison75 не завершено. Compatibility дополнительных моделей DEFERRED.
Повторного запроса бюджета150, reinstall или передачи ключа не требуется.

Это bounded standalone EVAL_ONLY в прежнем scoped исключении, с разрешённой
закрытой Gateway prompt delta и подтверждённой неизменностью v1. PR39 остаётся
Draft/headcd60, CI41009211185 RED и root cause UNKNOWN. C0-M4-CI-OBSERVATION-01
и полный CI интеграционного кандидата нужны до merge/runtime. Main/VM/DB/
Telegram не меняются; другие исполнители HOLD, следующий — владелец.

**Решение C0 от2026-10-30 — GPT v2 stage consumed; только exact metadata read:**
Owner report sourceace29ce7d77564f8fecea84d4b7e734e6c8fbe56,21904 bytes/21 events,
SHA256b0d1cb8249b321792355a2b4d29e1a79ba6eae30847a5deee6fbafa36159017f:10 POST/2 READ,
7 finals manual PASS, eighth scenario unknown_duration технически остановлен,
17 NOT_RUN. Полные quality25 и прежние findings no_send_claim19/unknown_price22
не закрыты. Price clarification case5 допустим, regex false positive сохранён.

Generation gen_2227417601602097153: HISTORY_VERIFICATION_FAILED / DETAIL / ATTEMPTS / INT.
Код требует integer==1; фактическое число integer!=1 не сохранено. Документация
[Polza history](https://polza.ai/docs/api-reference/history/generations) не задаёт
invariant1; [allow_fallbacks](https://polza.ai/docs/gaidy/provider-selection)
описывает другие providers, не количество внутренних attempts. Причина/стоимость
внутренних попыток UNKNOWN. Не менять guards и не запускать paid probe по догадке.

Новые confirmed0.05956584/9 known, unknown1/held0.465109963; shared
confirmed0.23889134/40 known,4 unknown (2 Gemini/1 DeepSeek/1 GPT),
held7.585505548,44 model attempts, confirmed+held7.824396888,
remaining142.175603112 из прежнего150. Все old holds остаются; это не account
balance, unknown charge не0. Исходный report и v1 evidence не изменяются.

C0-M4.2-GPT-QUALITY-HISTORY-R1 разрешает owner один metadata-only read:
≤2 history GET,0 model POST/catalog/READ; first5 должен содержать exact ID,
затем exact-ID detail.65536 bytes/15s каждый,45s overall; no pagination/retry/
polling, missing/ambiguous ID→STOP. Existing ace29 source/venv/private key;
input SHA до key/HTTP, новый exclusive report. Только выбранные типизированные
metadata, без /log, raw prompts/responses/reasoning/account/key labels.
Никакого automatic settlement/reserve release/paid/runtime transition.
Это сбор недостающего факта внутри прежней задачи, нового бюджета не нужно.

C0 exact receipt accounting/plan/flags PASS,4 controlled counter checks и15
checks точной операторской команды PASS; real HTTP/key reads0 под audit guard.
Backend без изменений,799 source tests/full CI повторно не запускались.
C4 и другие HOLD до metadata review; paid допуск OWNER_25_CASES_R1_15RUB consumed.
Gemini/DeepSeek DEFERRED, PR39 Draft/headcd60 и CI41009211185 RED сохраняются.
C0-M4-CI-OBSERVATION-01/full integration CI нужны до merge/runtime.
Main/VM/DB/Telegram/merge без изменений, selection=null/runtime=false.

**Решение C0 от2026-10-30 — history count2 принят; M4.2-GPT-QUALITY-R2:**
Metadata receipt1633 bytes/4 events, SHA256bf09d2dba67de7fbbd1f9a88cde309ee0a135fc1df52ab0554f591beeb1fba24,
exact input/ID gen_2227417601602097153:2 GET/0 POST, completed/OpenAI,
attemptsCount2, usage694/118/812 и reported cost0.00743079 совпали list/detail.
Original GPT v2 failed на integer==1. Счётчик provider attempts не число client
POST, причина/внутренние маршруты не наблюдались. Detail model/steps в проекции
null не доказывают raw null или отсутствие. Final не восстановлен.

По [официальному history contract](https://polza.ai/docs/api-reference/history/generations)
attemptsCount — количество попыток, stepsCount относится к server-tool requests;
[allow_fallbacks](https://polza.ai/docs/gaidy/provider-selection) ограничивает
другие providers, не обещает одну внутреннюю попытку. C0 явно пересматривает
invariant только в новом opt-in GPT EVAL_ONLY profile: positive int attempts
(без bool/coercion) сохраняется как metadata, не вызывает extra POST/READ.
Без serverTools/parent raw steps missing/null = NOT_APPLICABLE, int1 допустим;
все иные типы/0/negative/>1 отвергать. Default прежний profile/старые modes и
RouteReview/runtime не меняются. Model/identity/family/finish/cancel/usage/cost/
limits/reflection guards сохраняются; flex variant и routes отдельных attempts
не объявлять доказанными. Это исправление смысла metadata, не снятие quality gate.

Confirmed/held snapshot консервативно прежний:0.23889134/40 known,4 unknown,
held7.585505548,44 client POST, remaining142.175603112 из150. Reported0.00743079
не является автоматическим settlement: original body metering/final отсутствуют,
проекция не полный protocol verification. Hold0.465109963 остаётся; новых
запросов ради его освобождения не назначаем. Все source reports неизменны.

C4 готовит fixed **--gpt-quality-r2** для remaining repeats7–24:18 scenarios,
18 POST/0 READ/2 images/36 history/1 catalog. Retained7 manual PASS/2 READ
с exact R1/history hashes — C0-reviewed prior, без report import/arbitrary resume
или повторного исполнения первых7. Prompt conversation_v2/hash и fixtures/schema
не меняются. Reuse helpers; manual PENDING даже после полного R2, technical STOP
сохраняет finals/flags/accounting. Ни25 новых PASS, ни model selection/runtime
не выводятся из18 результатов. Full quality review C0 объединит R1+R2.

Подготовительный ceiling10 RUB из прежнего150, fresh18-call reservation до
POST, max62 shared client POST и все4 holds;60s/case/1800s stage, прежние
32768/512 token и24576/32768 byte bounds,599040 total token reservation.
Exclusive новый r2 report, source/ref/amount gates, no retry/fallback/polling.
Сейчас real HTTP0; source review и exact-source C0 допуск перед owner запуском.
Write-set7 paths/проверки в HANDOFF; общий бюджет повторно не запрашивается.

C0 receipt/ledger/schedule и7 controlled existing-verifier checks PASS,
audit real sockets/owner key reads запрещал. C4 должен проверить весь известный
набор полей после успешного attempts gate, включая strict raw steps type,
late STOP/оба images/no_send_claim и unchanged defaults; не обходить guards.
Backend этой docs-only выдачей не меняется,799/full CI не повторялись.
PR39 Draft/headcd60, CI41009211185 RED/C0-M4-CI-OBSERVATION-01 сохраняются;
full integration CI нужен до merge/runtime. Gemini/DeepSeek DEFERRED.
Main/VM/DB/Telegram/merge без изменений; следующий C4, owner paid/history HOLD.

**Решение C0 от2026-10-30 — GPT R2 source принят; один remaining18 owner stage:**
Source **7e48510311ab77c41f84b11becb2734ddb430690**, tree **23dad7ed0cf0e9974285db3881a1093e670fe443**,
sole parente07edeede77e4426e362531b2b6cde6ca6bc436d.7 разрешённых paths,
код принят без fixes. Новый opt-in gpt_eval_history_v2 только exact synthetic
GPT; provider attempts strict positive int отдельно от client POST. List/detail
raw steps missing/null NOT_APPLICABLE, strict int1 ONE_REPORTED; nonnull server
context запрещён. Identity/model/family/usage/cost/finish/cancel/limit/reflection
guards сохранены. Default strict_v1/старые modes и RouteReview/runtime прежние.
Prompts/Gateway/contracts/schema/fixtures/settings/deps/CI/DB/M3 не менялись.

C0 независимо:916 targeted PASS15.06s, Ruff/format4, mypy71;9 actual offline
CLI variants,8 старых stdout byte-exact e07. Exact source/ref/10 CONTROLLED:
complete18/retained quality flag/late DETAIL-STEPS-BOOL/whole-stage budget STOP;
all4 holds и exclusivity до key/HTTP сохранены. Real HTTP/owner key reads0 под
audit guard. Windows/hosted R2/full CI нового source NOT_RUN, код не исправлялся.

Разрешён один EVAL_ONLY stage по ref
`C0-M4.2-GPT-QUALITY-R2:7e48510311ab77c41f84b11becb2734ddb430690:OWNER_REMAINING18_R2_10RUB`.
Ceiling10 RUB из прежнего150, не новый бюджет. Fixed repeats7–24:18 scenarios,
≤18 model POST/0 READ/2 images/36 history/1 catalog; fresh18-call reservation
до POST,case60s/stage1800s,32768/512 tokens,24576/32768 bytes,599040 total tokens.
GPT/openai/flex/provider-default; v2/hash и canonical fixture прежние.
Retained7 manual PASS/READ2 из R1 не повторять/не импортировать/не переоценивать.

Prior confirmed0.23889134/40 known,4 unknown/held7.585505548,44 client POST,
remaining142.175603112, max62 shared. Все4 holds остаются, reported0.00743079
не settlement и не освобождает GPT hold0.465109963. Это ledger capacity, не
баланс Polza; catalog reserve CONDITIONAL_ESTIMATE и flex variant NOT_OBSERVED.
Новый exclusive reports/m4-polza-gpt-quality-r2.jsonl, source/ref/amount и input
report hashes в ready command; existing output до key/HTTP. No retry/fallback/
polling/arbitrary resume. После одного receipt paid HOLD до C0 review.

18 technical completions →HUMAN_REVIEW_REQUIRED/manual PENDING; не quality PASS25.
V1 no_send_claim19/unknown_price22 findings не закрыты unit tests; C0 оценит
полные R1+R2 finals. selection=null/runtime=false. Key/environment прежние,
reinstall и повторное подтверждение150 не нужны. Следующий исполнитель owner.

Scoped standalone EVAL_ONLY не закрывает CI debt. PR39 Draft/headcd60,
CI41009211185 RED/root cause UNKNOWN и C0-M4-CI-OBSERVATION-01 сохраняются;
full CI интеграционного кандидата нужен до merge/runtime. Gemini/DeepSeek
DEFERRED, comparison75 не завершено. Main/VM/DB/Telegram/merge без изменений.

**Решение C0 от2026-10-30: GPT quality R2 принят; переход к
M4.3-CONTEXT-R1.** Owner report SHA256 **f89ad00e49ab730f12a62f413142dd16ee7864bf4a026f9308662aa984750f35**,
42789 bytes/39 events, source **7e48510311ab77c41f84b11becb2734ddb430690**, tree **23dad7ed0cf0e9974285db3881a1093e670fe443**.
Exact ref/plan/schedule/DTO/flags/reservations и все summary fields проверены
локально; original files неизменны, новых C0 HTTP/key reads0.
По receipt18 POST/36 history/1 catalog/0 READ/0 new unknown; manual PASS18.
Вместе с retained R1 PASS7/2 READ —25 schedule positions,27 confirmed POST,
2 synthetic images. Это составной результат двух source/profile revisions,
не25 новых вызовов и не воспроизведение прежнего unknown final.
Все6 R2 flags (7/11/15/18/22/24) — semantic PASS при сохранённых regex findings.
V1 no_send_claim19 исправлен structured handoff; price22 теперь уточнение без
неподтверждённого business rule. Качество принято для этой маленькой synthetic
выборки; R2 N18/p50 11.163s/p95 16.393s включая history, не SLA.

C0 **выбирает GPT/openai/flex, conversation_v2** как единственный кандидат
первого runtime. Рекомендация «дешевейшая из прошедших» не превращается в
заявление о проведённом трёхмодельном сравнении: только GPT завершил набор,
Gemini/DeepSeek compatibility DEFERRED. Prompt SHA256 **b420be44a7e4210de1151e5b0604b0fa9a08c19b1bfbedb8147f2a9b38455956**,
canonical result/envelope/fixtures и image revision неизменны. Выбор ручной,
source-pinned; runtime route остаётся EVAL_ONLY. Raw report selected_model=null/
manual PENDING не переписывается. OpenAI family наблюдалась, flex variant нет.
gpt_eval_history_v2 остаётся только synthetic; production RouteReview и metering
не наследуют допуск автоматически. Data permission/backend reachability,
durable consumer и отправка требуют следующих runtime gates.

Новый confirmed0.13616096 RUB/18 known. Shared150: **confirmed0.37505230/58
known,4 unknown/held7.585505548,62 client POST**, committed7.960557848,
remaining142.039442152. Старые4 holds сохранены, metadata reported0.00743079
UNSETTLED. Capacity не account balance; новые retry/probe/settlement не назначены.
Ref OWNER_REMAINING18_R2_10RUB consumed; все owner paid stages завершены.

Следующий scope — уже запланированный **M4.3-CONTEXT-R1/C4**: bounded projection
существующих M3 snapshots, один текущий-context READ, bounded ConversationAgent
через ModelGateway на fixtures. Минимальная mandatory authority/read boundary
проверяется controlled tests, без default-allow; actual PG authority и durable
AIRun/Telegram — M4.3-RUNTIME. Нельзя считать UUID/DTO или fixture PASS доказанной
PG авторизацией. Точный7-file scope/критерии/base — в CURRENT HANDOFF.
Это не runtime enable, не новая очередь/registry/CRM и не клиентский Vision.

PR39 Draft/headcd60, CI41009211185 RED/root cause UNKNOWN,
C0-M4-CI-OBSERVATION-01/full integration CI остаются до merge/runtime.
Полный M4/A01–A08 ещё не принят. В этом C0 шаге только4 coordination docs и
PR body; C4 следующий, остальные HOLD. Main/VM/DB/Telegram/merge неизменны.

**Решение C0 от2026-10-30: M4.3-CONTEXT-R1 принят в SOURCE +
LOCAL UNIT scope; следующий C2-M4-CI-OBSERVATION-R1.** C4 source
d07619234570b28dbc0917aebfc288fe38e63aa8, tree f900178c5f3053049500fff6bd876d7e244da948,
sole parent ed29ce8c104c5f1631ddb6af483588b7df5ff2a0; exact7 paths.
ContextBuilder над original stored V2/V3 JSON ограничивает model-visible поля,
сохраняет current/owner факты, явно передаёт history/media ограничения.
ConversationAgent — один Gateway/deadline/budget, максимум2 calls/1 READ,
mandatory authority/read port на MODEL/READ/FOLLOWUP/CANDIDATE, без default-allow.
Только candidate/STOP; production authority и durable guarantees не следуют
из equality binding или DTO. Real PG adapter и атомарное принятие результата/
send intent остаются M4.3-RUNTIME; CONTROLLED guards не обходятся.

C0 независимо выполнил1283 targeted tests PASS21.67s, Ruff/format4, mypy73,
5 controlled ContextBuilder/Agent→Gateway→PolzaAdapter checks. Последние
покрыли READ/follow-up, authority revoke, stale native fence, foreign tool args,
invalid read digest, wire privacy/correlation и budget retention. Real HTTP0/
owner key reads0; это не hosted context quality, PG isolation или full CI.

До runtime продолжения C2 исправляет открытый C0-M4-CI-OBSERVATION-01:
CI41009211185 foundation803PASS/1FAIL, observer wait_blocked1.5s timeout,
root cause UNKNOWN. Scope — два existing test modules и два receipt docs;
реальная disposable PostgreSQL18 разрешена для targeted evidence. Production
семантика/DDL/CI не меняются, assertions/time bounds не ослабляются. Нужны
доказанная причина, минимальный repair, вся12-case matrix и отрицательные
контроли, shared-helper consumers при изменении. Если нужен production change,
C2 возвращает точную причину/paths C0. Общая CI optimization остаётся DEFERRED.
Exact base/write-set/критерии — в CURRENT HANDOFF; C2 следующий, остальные HOLD.

После C2 review C0 готовит integration candidate/full CI, затем runtime task.
PR39 Draft/headcd60 и main51d7 прежние; новая приёмка не integration/enable.
GPT/v2 selection, все old holds и shared ledger0.37505230 confirmed +
7.585505548 held / remaining142.039442152 RUB сохранены. Новых paid probes нет.
Route/data/backend/durable/Telegram gates и полный M4/A01–A08 остаются открыты.

**Решение C0 от2026-10-30: C2 audit принят; C6-M4-PG-EXECUTOR-R1
устраняет блокер среды.** Return560d445b169fe5487c002989af5857bc3c0d6c25/tree
3250876da5a759d462ac138c468bb2ccd43a721c меняет2 docs, code прежний. C0 проверил
C2 ZIP/hash/manifest, повторно получил original CI artifact12957949439,
воспроизвёл read-only audit byte-exact и сверил saved evidence/log excerpts.
803 PASS/1 FAIL и phase timings остаются историческими. C2 repair BLOCKED,
root cause UNKNOWN, новые PG tests NOT_RUN. Local UID0-only/no capabilities
и отсутствие PG/Docker подтверждены также C0; sandbox обходы не нужны.

C6 получает точную6-path задачу: один temporary branch-only workflow и маленький
diagnostic script, при необходимости hooks в двух test modules, два receipt
docs. Подготовить и один раз запустить original12-case matrix на disposable
GitHub runner/stock Docker с existing pinned PG18/asm_test/schema/roles.
Finite20min job, отдельные setup/test/cleanup results, expected waiter PID и
observer/request/DB-edge timings; assertions/time bounds/product state прежние.
Один explicit expected-base fast-forward execution branch разрешён этой выдачей.
Main/PR39/старые CI jobs не перемещаются/не повторяются; никаких VM/owner secrets.
Точный source/base/branch/write-set и критерии — CURRENT HANDOFF.

Это необходимый executor для прежнего repair, не общая CI optimization или
новая runtime capability. Диагностический PASS12 не закрывает прежний timeout;
после receipt C0 возвращает C2 необходимые repair/negative-control проверки,
затем готовит integration/full CI. C4/GPT приёмки, все unknown holds и бюджет
сохранены; runtime/data/route/durable/Telegram gates остаются открыты.
В этом C0 шаге code/Actions/PG/paid calls0; C6 следующий, остальные HOLD.

**Предыдущее решение C0 от2026-10-30: C6 PG observation принят;
C2-M4-CI-OBSERVATION-R2 назначен.** Source a4ca08f9a6f8ed3642e4f82f156389588e6e05f6,
receipt38f6a53fa91d3d6933b64610d47997fa230c7038. Actual run41082835484/attempt1:
12 PASS на fresh PG18.6/asm_test, expected waiter PID12/12, cleanup PASS.
C0 независимо сверил GitHub metadata/log/digest, source/AST/manifests, byte-exact
analyze output;9 controlled preflight/static checks PASS. Aggregate matrix.json
был перезаписан outer command, но raw cases/collect/JUnit/events достаточны:
R1 принят как observation с этим ограничением, исходные bytes сохранены.

Исторический timeout не воспроизведён, cause UNKNOWN. C0 контролируемо подтвердил
конкретный test-oracle дефект: foreign waiter/nonempty rows позволяют success
для неподходящего либо уже completed target. Поэтому следующая задача — строгая
привязка wait к actual target PID/task на всех9 call sites, negative controls
и устранение filename collision. Не выдавать эти дефекты за причину старого timeout.
222 existing cases четырёх consumer modules собраны C0 collect-only; PG222 не заявлен.

C2 явно разрешены8 paths из HANDOFF, включая четыре test modules и узкие изменения
уже подготовленного executor/workflow. Один новый branch-only job≤25min,
test phase≤600s для222+ новых cases; business limits1.5s/1.1s/clock/state и
production semantics прежние. Это новый repaired-source validation, не rerun
старого job. R1 refs/receipt/artifact frozen, no owner VM/credentials/paid calls.
После return C0 review/integration/full CI; historical cause остаётся UNKNOWN
в истории, integration gate закрывается отдельным решением по актуальному
evidence. Бесконечное воспроизведение единичного timeout не становится целью.

C4/GPT scoped acceptance и unknown holds/shared150 сохранены. Runtime route/
data/backend/durable/Telegram gates остаются открыты. В этом C0 шаге только
coordination docs/PR body и offline review; новых Actions/PG/model runs нет.
C2 следующий, C6 и остальные HOLD; PR39/main без изменений.

**Предыдущее решение C0 от 2026-10-30: R2 evidence VERIFIED; узкий R3.**
Source44cbaa0e09e066b35894a11e7004ea651b1a54a2 / receipt862c037bb8e5307a9991b9938567e2a910a20777
проверены C0. Один hosted run41090382696: 253 PASS / 1 FAIL, original222 и
matrix12 PASS, cleanup PASS. Recorder command/summary collision исправлен;
complete=true/result=FAIL отражают фактический результат, не успешный repair.
Независимые C0 metadata/artifact/AST и 25 controlled checks подтверждены.

Новый foreign-control не завершил held-lock/effect assertions: после expected
timeout повторный SQL на invalidated blocker вызывает PendingRollbackError.
C0 controlled probe подтвердил SQL без active target identity и cancellation
observer await; точный hosted момент инвалидации не traced. Это test lifecycle
defect, не доказанная причина historical timeout и не production defect.

C2-M4-CI-OBSERVATION-R3 ограничен helper/negative-control lifecycle и необходимой
execution identity существующего runner/workflow; exact 5 paths в HANDOFF.
Не выполнять observer SQL без active query, сохранить task/PID/result guards,
не скрывать observer failure и не освобождать blocker ради PASS. Отдельное
существующее TEST-role observer connection допустимо только для изоляции
timeout/cancel controls, без новых grants/framework. Existing 254 cases,
1.5s/1.1s/DB bounds и business effects сохраняются.
После local checks разрешён один fresh hosted validation четырёх modules
<=600s tests / <=25min job. R1/R2 frozen; новых paid/VM/production действий нет.

R2 repair в целом остаётся BLOCKED до R3; historical cause UNKNOWN.
После review — integration/full CI и runtime, без бесконечного replay старого
timeout. GPT/C4 acceptance и shared150 ledger не изменены. PR39/main прежние.

**Предыдущее решение C0 от 2026-10-31: C2 R3 VERIFIED, integration/full CI.**
Source db46d06c3ee12b34f6a0630415454a56a128c9d9, receipt
ea10472de268ceb9d656a0d5ddc11f093b653cd3 принят SOURCE + TARGETED PG.
Run41096329059/attempt1:258 PASS, cleanup PASS. Foreign held-lock/effects и
два actual observer error/cancel controls прошли; original222/R2 254, 509
assertions и прежние timeouts сохранены. C0 сверил metadata/source/artifacts,
повторил offline27/static/collection/controlled checks. Нового repair не нужно.

C0 разрешает FF существующей PR39 branch с old cd60e5e на cumulative candidate
после docs acceptance и один штатный full CI, без изменения CI core/лимитов.
Accepted GPT/v2 adapter/probe, C4 context/agent и C2 test-helper source входят
в общий кандидат. R1/R2/R3 execution refs сохраняются. Полный PASS ещё NOT_RUN
на момент этой записи; scoped R3 PASS не означает integration/main acceptance.
Приёмка актуального CI позволит закрыть observation gate, сохранив historical
timeout cause UNKNOWN. Merge остаётся владельцу после C0 readiness.

Модельные расходы/holds не меняются. Настоящие PG authority, durable AIRun и
AI->Outbox->Telegram ещё не реализованы; full source CI не является runtime
или data/route approval. VM/Telegram/live/paid запусков эта выдача не разрешает.

**Предыдущее решение C0 от 2026-10-31: PR39 merged; main verification BLOCKED.**
Actual main997d2bf83b5402068ba1f62b23d5947fcfaf7d32 имеет тот же tree13f5ab44,
что accepted PR candidate1b7a6987. PR CI41099431123:11/11 SUCCESS сохранён;
main CI41108194917/attempt1:10 SUCCESS/1 FAILURE. Foundation839 PG PASS/1 FAIL
resume-activation-subscription, timeout1.5s при active query=None. Место ожидания
target до cleanup UNKNOWN; source drift при merge отсутствует. Generic evidence
complete=true/840, primary_exit1/cleanup_exit0; secondary gate refusal ожидаем.

C0 вновь открывает observation gate и выдаёт C2-M4-CI-OBSERVATION-R4:
минимальный test synchronization repair с доказанным before/after, либо точный
BLOCKED; допустима bounded readiness до измеряемой фазы при сохранении смысла
policy snapshots,1.1s edge и1.5s actual lock observation. Нельзя просто поднять
таймаут или объявить очередной PASS причиной. R3 fixes/guards/assertions сохраняются.
Failure-stage facts должны собираться до cancellation, без секретов/SQL parameters.
Write-set6 и единственный targeted run после local proof заданы в HANDOFF;
production/DDL/core CI не меняются. Runtime и actual main acceptance ждут repair.
Новый paid/VM/Telegram запуск не разрешён; ledger и data/route gates прежние.

**Актуальное решение C0 от 2026-10-31: R4 SOURCE + TARGETED PG VERIFIED.**
Source249b36112adb72fb763207893eb50ab31c06eff7/receipt55a65c2 принят C0.
One run41124252930/attempt1:278 PASS/834 phases, cleanup/source PASS. Readiness5s
отделяет подготовку HTTP/auth от прежнего edge1.1s/observer1.5s/release<2s.
Original12 + delayed-auth12 доказывают opposite frozen/post-lock policy,
реальный exact task/PID/query wait и прежние effects/replay. C0 offline35 PASS,
source/collection/artifact/controlled before-after PASS; historical trigger UNKNOWN.

C0 готовит отдельный child receipt на c0/m4-ci-repair-integration-r1, новый
Draft PR к main и один full CI. R4 execution ref frozen, C2/остальные HOLD.
Main997d2bf8/run41108194917 остаётся FAILED; не переигрывать неизменённый run.
Целевой PASS не закрывает main gate; Ready после full CI, merge владельцу,
далее проверка actual main. Production/DDL/core CI/ledger не меняются.
Новых VM/Telegram/paid/runtime действий нет; real durable AI bridge ещё TODO.

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
