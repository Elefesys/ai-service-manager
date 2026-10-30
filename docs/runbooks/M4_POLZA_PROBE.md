# M4.2 — один запрос Gemini для диагностики подписи

**C0 принял один OWNER diagnostic: ≤1 Gemini POST, резерв этапа≤5 RUB в прежнем150.**
Это отдельное измерение формы protocol metadata. GPT/DeepSeek не вызываются,
READ/follow-up не выполняются; R1/R2 и history report сохраняются без изменений.
Exact source **68093c769f24ea63eca5185179c3eab5fafd1229**, tree
**585f034acedec906d6859a25176ef430f808d578**. Code не менялся после приёмки:
520 targeted pytest/Ruff/format4/mypy71 PASS. [Решение C0](../tasks/M4_HANDOFF.md).

Owner history-r1 завершился UNKNOWN/HISTORY_PROVIDER_UNKNOWN после1 GET,
0 model POST/0 catalog/0 READ. Поле provider в выбранной строке списка не прошло
существующий validator. Report не сохраняет его значение/тип или конкретную строку:
нельзя заключить, что виновата Gemini, пробел в названии либо отсутствие поля.
Charge старого запроса и форма его signature остаются UNKNOWN; GET не повторяем.

Shared confirmed **0.17509189 RUB/30 calls**, old unknown **1 POST**, удержанный
резерв **3.464879664 RUB**, остаток общего150 с ним **146.360028446 RUB**.
Новый этап получает только **5 RUB** из этого остатка. Fresh catalog пересчитает
условный резерв именно одного запроса; если он больше5, модель не вызывается.
Резерв не равен списанию/гарантированной цене. Old unknown не погашается, новый
charge/резерв записывается отдельно; максимум32 model POST вместе с прошлыми31.

## Готовая Windows команда — один Gemini diagnostic

На прежнем ПК выполнить весь блок в обычном PowerShell. Ничего заменять не надо:
используются уже установленный source, `.venv` и `.env.m4-probe`. Checkout не
переключается: другой SHA или dirty source останавливают команду до API.
В конце вернуть C0 **все JSONL-строки** нового report, даже при TECHNICAL_FAILURE.
Повтор, другое имя отчёта и удаление файла ради нового запуска не разрешены.

```powershell
& {
    $ErrorActionPreference = "Stop"
    $Candidate = "68093c769f24ea63eca5185179c3eab5fafd1229"
    $DecisionRef = "C0-M4.2-GEMINI-DIAGNOSTIC-R1:68093c769f24ea63eca5185179c3eab5fafd1229:ONE_POST_R1_5RUB"
    $Repo = Join-Path $env:LOCALAPPDATA "ASM-M4-Probe-4f86e7f"
    Set-Location -LiteralPath $Repo
    $Report = "reports\m4-polza-gemini-diagnostic-r1.jsonl"
    if (Test-Path -LiteralPath $Report) { throw "Preserve existing diagnostic report; do not replay" }
    $Actual = git rev-parse HEAD
    if ($LASTEXITCODE -ne 0 -or $Actual -cne $Candidate) { throw "Expected the reviewed source already used for history; stop and return to C0" }
    $Dirty = git status --porcelain
    if ($LASTEXITCODE -ne 0 -or $Dirty) { throw "Clean checkout required" }
    if (-not (Test-Path .\.venv\Scripts\python.exe)) { throw "Existing environment required" }
    if (-not (Test-Path .\.env.m4-probe)) { throw "Existing private key file required" }
    .\.venv\Scripts\python.exe -m asm.ai.probe --plan --gemini-diagnostic
    if ($LASTEXITCODE -ne 0) { throw "Offline diagnostic plan failed" }
    .\.venv\Scripts\python.exe -m asm.ai.probe --live --gemini-diagnostic `
        --secret-file .\.env.m4-probe --report $Report `
        --approved-rub 5 --approval-ref $DecisionRef `
        --source-sha $Candidate --source-environment LOCAL_DESKTOP
    $DiagnosticExit = $LASTEXITCODE
    if (-not (Test-Path -LiteralPath $Report)) { throw "No diagnostic receipt written; return STOP to C0 without retry" }
    Write-Host "Diagnostic receipt: $Report"
    if ($DiagnosticExit -ne 0) { Write-Host "STOP/TECHNICAL_FAILURE: preserve receipt for C0; do not retry" }
    Write-Host "Return the complete receipt; no READ, follow-up or runtime approval"
    Get-Content -LiteralPath $Report -Encoding UTF8
}
```

Перед POST будет1 catalog GET; после него≤2 bounded exact-ID history GET.
Overall120s, model call≤60s с history; tokens32768/512, wire bytes24576/32768.
Три прежних отчёта не открываются/не перезаписываются. Имя нового файла фиксировано,
создание exclusive. И при valid signature результат только TOOLS_OBSERVED /
ROUNDTRIP_NOT_RUN; это не успешный READ roundtrip и не выбор модели для runtime.
Если verification history снова откажет, signature diagnostics и доступные body
metadata всё равно нужны C0; неизвестный новый charge сохраняет свой резерв.

`--plan` по-прежнему печатает PLAN_ONLY / PAID_NOT_AUTHORIZED: сам план не является
допуском. Единственный live допуск — exact source/ref и explicit5 в блоке выше.
После этого запуска новые paid действия HOLD до разбора отчёта C0.

PR39 Draft/headcd60 не меняется. CI41009211185 RED по прежнему M3 observer;
full CI source68093c7 NOT RUN, C0-M4-CI-OBSERVATION-01 остаётся до merge/runtime.
C0 принимает только этот отдельно проверенный standalone diagnostic CLI;
DB/M3/Telegram/runtime/merge разрешения из него не следуют.

## Безопасные metadata при signature failure

`signature_diagnostic` содержит только фиксированный code/shape category,
наличие ожидаемого поля, тип и длину UTF-8, ограниченную значением8193 вместе с
признаком превышения прежнего8192-byte cap. `null` означает, что признак не
установлен для закрытой ожидаемой формы. Произвольные ключи/значения, signature,
её hash, raw response, reasoning, account/key metadata не записываются.

| Ситуация | Diagnostic code |
|---|---|
| Нет extra_content | SIGNATURE_EXTRA_MISSING |
| Неправильный путь: нет google | SIGNATURE_GOOGLE_MISSING |
| Дополнительные ключи extra_content | SIGNATURE_EXTRA_KEYS |
| null / иной тип значения | SIGNATURE_NULL / SIGNATURE_TYPE |
| Пустая строка | SIGNATURE_EMPTY |
| Непечатные/control символы | SIGNATURE_CONTROL |
| Более8192 UTF-8 bytes | SIGNATURE_OVERSIZE |
| Неправильные контейнеры/нет поля/лишние Google keys | SIGNATURE_EXTRA_TYPE / SIGNATURE_GOOGLE_TYPE / SIGNATURE_FIELD_MISSING / SIGNATURE_GOOGLE_KEYS |
| Encoding / correlation / reflection | SIGNATURE_ENCODING / SIGNATURE_CORRELATION_FAILED / SIGNATURE_IN_RESPONSE |

Подтверждённая форма получает SIGNATURE_VALID, но это не quality/roundtrip PASS.
Сохраняются прежние correlation, reflection/redaction, byte/token/cost guards
и очистка transient state. Ни один отказ не разрешает READ, follow-up или следующий case.

Доступные generation/model/provider и `body_metering` помечены
`RESPONSE_BODY / FIELD_VALIDATED_ONLY`. `reported_cost_rub` из body не погашает
резерв. Invalid/unavailable поля остаются UNKNOWN/null. Если в новом ответе есть
валидный exact generation ID и согласованные bounded usage/cost, допустимы прежние
два history GET до возврата ошибки. Только успешный `HISTORY_LIST_DETAIL` даёт
confirmed usage/cost в failed call и общий учёт. Основной signature code сохраняется;
отказ history записывается отдельно как `failure_history_error`, charge остаётся UNKNOWN.
Это касается новых наблюдений; утраченный ID старого R2 не восстанавливается по догадке.

## R2 history: только чтение, без автоматического погашения резерва

`--history-r2` делает один существующий bounded list запрос: первая страница,
не более5 последних chat generations, createdAt descending. Anchor обязан быть
в этой странице; pagination/retry и поиск по account/key не выполняются. Если он
уже вытеснен более поздними генерациями, результат UNKNOWN; CLI не расширяет поиск.

Anchor `gen_2227337132904026113`: GPT,521/114 tokens,0.00631386 RUB,finish stop.
Единственный Gemini candidate должен быть после anchor, не раньше его завершения,
и внутри исходного окна `2026-10-30T06:41:00.956181Z` —
`2026-10-30T07:11:00.956181Z` (правая граница исключена). Сначала проверяется list,
затем detail кандидата и anchor: ID/model/time/status/usage/cost/provider/finish,
sync, одна попытка, отсутствие server tools/cancellation. Model берётся из list;
если detail содержит model, он также обязан совпасть. Нет кандидата/несколько/
нет anchor/невалидные или расходящиеся данные — UNKNOWN.

Фактически успешная ветка использует3 GET; hard ceiling4,≤65536 bytes/GET,
≤15s каждый, общий deadline60s. **0 catalog GET,0 model POST,0 READ.**
Только official history list/detail; `/log`, `/children`, raw wire не запрашиваются.
Ответ содержит allowlisted metadata. History не раскрывает форму signature:
`signature_shape=NOT_AVAILABLE_FROM_HISTORY`.

Даже единственный согласованный результат — `CANDIDATE_REQUIRES_C0`,
`candidate_is_exact_response_correlation=false`. Его история показывает свой
cost, но `r2_charge_status=UNKNOWN`, `r2_charge_rub=null`,
`automatic_reserve_release=false`: старые3.464879664 удерживаются. C0 решает,
достаточна ли связь для отдельной сверки; автоматического перехода к POST нет.
Исходные R1/R2 не открываются и не меняются. SHA текстовой копии R2 не используется
как hash оригинального файла и не является новым continuation checkpoint.

**Историческая GET-only процедура уже выполнена.** Получены две строки
source/history_reconciliation со статусом UNKNOWN и HISTORY_PROVIDER_UNKNOWN,
history_gets1. Исходный report сохранён, новый GET/retry не предлагается.
[Команда использованного history-r1](https://github.com/Elefesys/ai-service-manager/blob/c94d2ff7923c930a8e3d1983b9a05f07414eb967/docs/runbooks/M4_POLZA_PROBE.md)
остаётся историческим источником; её допуск использован.

## Ограничения принятого однократного diagnostic

Offline команда `python -m asm.ai.probe --plan --gemini-diagnostic` не читает
ключ и не выполняет HTTP. По умолчанию `--gemini-diagnostic` также печатает план.
Цель — безопасная форма/причина отказа metadata и metering одного нового ответа;
это не продолжение R2 и не исправление unknown compatibility.

| Параметр | Ограничение |
|---|---|
| Модель / case | Только google/gemini-3.8-flash / tool_current0; google-ai-studio/flex, прежний provider default |
| Запросы | ≤1 POST,1 fresh catalog GET,≤2 exact-ID history GET; GPT/DeepSeek POST0 |
| READ / follow-up | 0 /0; TOOLS без final не означает READ roundtrip PASS |
| Tokens / wire bytes | Прежние32768/512 и24576/32768 на call |
| Deadline | Общий120s; per-call60s с history, прежние≤15s на exact-ID verification |
| Prior | Confirmed0.17509189 +old unknown reserve3.464879664; вместе31 прошлый POST |
| Новый stage | Explicit approval5 RUB из остатка146.360028446; один fresh reserve≤5 до POST |
| После ответа | Новый confirmed cost либо удержанный unknown reserve отдельно; старый unknown автоматически не снимается |

Gateway сохраняет обычную проверку tool contract/correlation. Его внутренние
лимиты tool scenario оставлены прежними; диагностическая функция вызывает
Gateway ровно один раз, резервирует только один POST, не создаёт ToolResult и
не исполняет READ/follow-up. Даже валидный результат помечен ROUNDTRIP_NOT_RUN.
Сигнатура остаётся transient и очищается перед записью результата.

Цена до fresh catalog — null; старый Gemini reserve не становится новым тарифом.
C0 выдал ровно один admission в блоке выше; это не общий допуск повторять режим.
CLI ожидает approval ref формы
`C0-M4.2-GEMINI-DIAGNOSTIC-R1:<exact source SHA>:<decision>` и explicit amount;
старый R2 ref и budget, не учитывающий unknown reserve, отклоняются до key/HTTP.
Готовая команда выше содержит новый exact ref и amount5; автоматического перехода
из history режима по-прежнему нет.

UNKNOWN остаются actual R2 wire representation, причина конкретного старого
SIGNATURE_INVALID и связь model/time candidate с утраченным response ID.
Для будущего общего продолжения требуется исходный R2 JSONL или отдельно
принятое C0 правило идентификации. Prompt/fixtures/profiles и GPT results не меняются.

Предыдущая [точная R2 процедура](https://github.com/Elefesys/ai-service-manager/blob/6e37623c804695c08cbb83d3fba8ee03ec9c4e1f/docs/runbooks/M4_POLZA_PROBE.md)
сохранена как история уже выполненного запуска. Её команда не является новым
допуском. Ниже — справочные ограничения sourcecd60, не новая операторская команда.

## Профили и уровни evidence

| Модель | Фиксированный request selector | Reasoning / continuation | History family до пробы |
|---|---|---|---|
| `openai/gpt-6-luna` | `openai/flex` | Прежний provider default, без reasoning override | `OpenAI`, prior owner observation; mismatch STOP |
| `google/gemini-3.8-flash` | `google-ai-studio/flex` | Provider default; opaque Google signature для соответствующего tool call | UNKNOWN; первый согласованный list/detail — `OBSERVED_DURING_THIS_EVAL` |
| `deepseek/deepseek-v4.1-flash-1017` | `wafer/us` | Явно `reasoning: {effort: "none", enabled: false}` | UNKNOWN; первый согласованный list/detail — `OBSERVED_DURING_THIS_EVAL` |

Это выбор C0, не поиск наиболее дешёвого провайдера. Перед первым model POST один
fresh catalog GET проверяет **все три** unique exact official selectors,
`is_unofficial=false`, declared `tools/json_schema_strict/input_image`, параметры
`tools/tool_choice/response_format` и поддерживаемый output cap alias, context/output
limits и text/image modalities. Для DeepSeek дополнительно нужны declared reasoning
parameters, toggle supported, mandatory=false и `none` в обоих списках efforts.
В прежнем snapshot thinking default был включён; полагаться на него нельзя.
Missing/duplicate/rejected/unknown или неподдержанный профиль останавливают этап
до первого POST. Выбора другой route/model, fallback или retry нет.

`SYNTHETIC_EXPERIMENT / EVAL_ONLY` и `CONDITIONAL_ESTIMATE` отделены от обычного
`RouteReview` / `REVIEWED_BOUND`. Каталог — declaration, controlled HTTP — проверка
кода, history — наблюдение конкретной генерации; ни одно из них не является
сертификацией hosted API или runtime admission. Эксперимент не создаёт evidence
строк или `output_cap_includes_reasoning=true` за оператора.

В plan явно записываются допущения: выбранный cap512 охватывает весь output,
включая reasoning; serialized wire bytes+4096 достаточно для tokenizer и двух
synthetic images; объявленные strict schema/tools совместимы; public rates
приближают account tariff. Эти допущения проверяются actual usage/cost guards,
но public catalog не гарантирует итоговый счёт. Отсутствующее reasoning usage
DeepSeek помечается `NOT_REPORTED`; наличие raw reasoning или ненулевых reasoning
токенов останавливает probe до READ/final. Raw reasoning не сохраняется.

## Расход, маршрут и протокол

До POST записываются fresh catalog hash/date, фиксированный selector, declared
capabilities, cap alias, reasoning profile, assumptions, все известные rates,
резерв каждого нового call и всех67, prior/approved amounts. `catalog_experiment` не
подменяет дату старого review. Данные прежнего каталога и прежний резерв
не используются для нового live admission. Все три новые резерва должны поместиться
в stage approval и остаток149.90426263 общего150.

В input-rate консервативно суммируются prompt, image, cache read/write и **весь**
`input_audio_cache_per_million`; в output-rate — completion и internal reasoning;
per-request fees также суммируются. `audio_per_million` и `web_search_per_thousand`
исключены только благодаря конечному проверяемому wire: text/inline PNG/local
function tools, без audio, server tools, plugins или произвольного extra content.
Unknown/new/nonnumeric/null fee и неизвестная валюта — STOP. Эти же fresh rates
используются в wire `max_price`, Gateway reservation и monotone ledger.

Каждый experimental response требует history list/detail даже при наличии body
provider. Проверяются generation ID, exact model (документированный slug в list),
usage, cost, completed status, finish, attemptsCount=1, sync и одинаковая family.
Допускаются ровно `apiType=completions` (реальные receipts владельца) и
`chat_completions` (документация); missing/other type — STOP.
Первое наблюдение Gemini/DeepSeek не угадывается заранее и закрепляется на всю
оценку этой модели, включая следующие cases/images. Смена/invalid family — STOP.

`provider_only`/`Route.upstream` — **REQUEST_SELECTOR_NOT_OBSERVATION** только
в experiment. `observed_body_provider` сохраняется отдельно; `history_family`
описывает конкретное наблюдение. `route_variant=NOT_OBSERVED`: даже `OpenAI` не
доказывает flex. History identity/metering проверяются до локального READ и final.
Raw history, account/key поля, headers и chain-of-thought в отчёт не попадают.

Gemini continuation хранит максимум одну opaque signature ≤8192 UTF-8 bytes
только в transient adapter state. Она привязана к run ID/deadline/route и полному
validated tool call, возвращается ровно в
`tool_calls[].extra_content.google.thought_signature`. Произвольный extra_content
не копируется. Missing/malformed/oversized/correlation errors — STOP; подпись
учитывается в прежнем wire/token admission, отсутствует в neutral DTO/JSONL/errors,
очищается при завершении/ошибке/case boundary и не переносится в другой run.
Утечка сохранённой подписи в последующий response также вызывает STOP.

Источники protocol behavior:
[Google thought signatures](https://ai.google.dev/gemini-api/docs/generate-content/thought-signatures#signatures-for-openai-compatibility),
[Polza reasoning control](https://github.com/polza-ai/docs/blob/main/osobennosti/reasoning-tokens.mdx),
[Polza history](https://github.com/polza-ai/docs/blob/main/api-reference/history/generations.mdx),
[Polza routing](https://github.com/polza-ai/docs/blob/main/gaidy/provider-selection.mdx).
Google documentation объясняет нужную wire форму, но не является live proof Polza.

| Ограничение | Значение |
|---|---|
| R2 cases / model POST / READ | 63 /≤67 новых /≤4; R1+R2=75/81/6, helper3+probe81≤84 POST |
| Полный исходный набор на модель | 20 text (включая2 READ roundtrip),3 critical repeats,2 PNG; R2 skips12 GPT |
| Input / output tokens | 32768 /512 на call |
| Wire input / output bytes | 24576 /32768 на call |
| Case / run deadline | 60 /1800 секунд; catalog/history внутри общего бюджета |
| History | R2≤134 GET +R1=28 →probe≤162;65536 bytes/GET;≤15s на обе проверки |
| Catalog | 1 GET перед первым POST;4MiB,20s |
| Synthetic fixtures normalized SHA256 | `7abd25f1e1f08e51eacc3a68975e6099c942d33fad37376366dfdef6c7e025b2` |
| Стоимость | prior0.09573737 +R2≤149.90426263 ≤общего150 RUB |

Каждый call резервируется/flush до возможного POST. Неизвестный charge сохраняет
резерв. Deadline/transport/protocol/usage/cost failure останавливает весь
этап, без retry/repair/fallback. Quality flags остаются для human review. Canonical conversation schema не меняется:
wire root envelope `{result: ...}` сохраняет union/$defs/$ref; затем остаётся
прежняя local DTO validation. PNG probe остаётся отдельным EVAL_ONLY путём.

## Обычный reviewed path

Без `--synthetic-experiment` поведение по умолчанию прежнее. Offline plan не
читает secret/HTTP, `--live` требует три реальные `RouteReview` и explicit budget.
Experiment нельзя смешать с `--review` или `--preflight`; его профиль не проходит
валидацию RouteReview. Mandatory evidence/output-cap assertions не ослаблены.
Present body provider mismatch reviewed route по-прежнему STOP; история не
подменяет несовпадение. Missing provider допустим только при reviewed history
mapping и прежних exact history checks. Price-only reprice сохраняет original
review/hash/date; non-price configuration и fee schema/currency drift — STOP.

### Открытые поля для C0 перед полным сравнением

Исторические незаполненные contract поля относятся к **reviewed** admission:
route/body/history mapping, output cap including reasoning, tokenizer/image bound,
fee applicability, schema+tools compatibility. C0 явно разрешил измерить их через
описанный отдельный finite experiment; они больше не требуют от владельца
сочинять подтверждения для его запуска. После75 C0 оценивает каждый final,
quality, наблюдённые families/профили и расходы. Даже полный controlled PASS или
успешный эксперимент не открывает runtime и не выбирает модель автоматически.

## Проверки candidate

Из корня checkout в существующем frozen CPython3.13 окружении:

```sh
.venv/bin/pytest -q tests/test_m4_probe.py tests/test_m4_polza.py tests/test_m4_gateway.py tests/test_m4_gateway_failures.py
.venv/bin/ruff check backend/src/asm/ai/probe.py backend/src/asm/ai/polza.py tests/test_m4_probe.py tests/test_m4_polza.py
.venv/bin/ruff format --check backend/src/asm/ai/probe.py backend/src/asm/ai/polza.py tests/test_m4_probe.py tests/test_m4_polza.py
.venv/bin/mypy
.venv/bin/python -m asm.ai.probe --plan
.venv/bin/python -m asm.ai.probe --plan --synthetic-experiment
.venv/bin/python -m asm.ai.probe --plan --history-r2
.venv/bin/python -m asm.ai.probe --plan --gemini-diagnostic
git diff --check
```

C4 использует CONTROLLED fixtures, без owner rows в Git. Проверены все8 прежних
signature negatives с отдельными codes, дополнительные shape/reflection/metering
ошибки и исходный valid roundtrip. GET-only candidate/no-match/ambiguous/mismatch/
unknown, response/time/GET caps, exclusive reports и отсутствие POST проверяются
отдельно от one-POST diagnostic:0 READ/follow-up, fresh reserve, old unknown held,
old approval rejected, primary signature failure сохранён при history failure.
Original full comparison75/81/6 и R1 continuation63/67/4 остаются regression gates.
Фактический результат — в текущем receipt M4_HANDOFF. Settings/gateway/contracts/
prompt/schema/canonical fixtures/profiles/locks/CI не менялись.

Owner files, owner key и реальные Polza HTTP не использовались. C0 review exact
candidate → GET-only сверка на ПК; отдельное решение по one-POST плану возможно
после review, без автоматического paid запуска. CI41009211185 остаётся RED,
C0-M4-CI-OBSERVATION-01 — OPEN до merge/runtime. Полный CI C4 не повторяет;
PR39/main/VM/runtime/merge не меняет. Windows/hosted compatibility PASS не заявлен.
