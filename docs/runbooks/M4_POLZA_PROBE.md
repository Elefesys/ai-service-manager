# M4.2 — quality flags и одно продолжение synthetic experiment

**QUALITY-CONTINUATION-R1: candidate REVIEW; новый paid R2 NOT RUN.**
Выдача C0 — [M4_HANDOFF](../tasks/M4_HANDOFF.md), решение —
[IMPL-004](../decisions/IMPL-004-m4-pilot-ai.md). Source R1
**b1ff8f1463e12ff65a64d692b7fc7718aa8d05fc** принят C0:399 targeted PASS и
[CI40915999616](https://github.com/Elefesys/ai-service-manager/actions/runs/40915999616)
SUCCESS11/11. Это прежний source; CI нового candidate выполняет C0 после review.

C0 проверил полный owner R1:12 GPT finals/14 confirmed POST/2 READ/28 history GET,
manual12 semantic PASS в их synthetic scope. Regex500 нашёл упоминание внутри
отказа подтверждать цену; исходный `FORBIDDEN_CLAIM` остаётся в историческом отчёте.
Gemini/DeepSeek в R1 — NOT_RUN. Не повторять R1 и не редактировать его JSONL.

| Подтверждённый расход | RUB | Model POST / READ |
|---|---:|---|
| Старые helpers | 0.01269785 | 3 /1, отдельно от probe |
| Сохранённый R1 | 0.08303952 | 14 /2 |
| Shared prior | **0.09573737** | **17 /3** |
| Остаток общего150 для нового этапа | **149.90426263** | ≤67 новых POST /4 READ |

Reservation R1 **6.511539482 RUB** не равен списанию. Все14 calls подтверждены,
unknown0, поэтому остаток рассчитан по expense, без повторного прибавления R1.
Balance/key limit заново не запрашивался. Для R2 используется прежний key/env,
без новой установки, ручного подсчёта или сочинения RouteReview.

## Один принятый префикс

`--continue-from` принимает только полный неизменённый
`reports/m4-polza-executable-eval-r1.jsonl`, SHA256
`b727cc1ca65c5ef189cc2bddba619136a354c6414b7159e0bde4d521f52f8b48` (owner34940 bytes).
CLI читает ограниченный файл один раз, проверяет полный byte hash **до ключа/HTTP**,
затем source/approval/fixture/plan, exact ordered12 cases,14 monotone reservations,
unique generations, all confirmed RUB costs, READ/final completeness и terminal
summary. Legacy summary воспроизводится неизменённым алгоритмом sourceb1ff8f1.
Altered/missing/duplicate/out-of-order/pending/unknown receipt — STOP. Нет public
hash override, arbitrary prefix, цепочки resumptions или принятия одного tail case.

Новый exclusive R2 report содержит `imported_receipt.original_events`: все30
исходных событий, включая reservations/finals/flags и прежний summary. Они не
пересчитываются и не стираются. Source SHA/receipt hash/legacy evaluator revision
сохраняются как provenance;12 scoped `manual_assessments` C0 записаны отдельно
по `(model, repeat, case)` и привязаны к этому hash/source. Они не относятся к
любым новым ответам или совпадениям текста. Новые cases имеют evaluator revision
`synthetic_quality_flags_v2`, новый source — в собственном `source` event.

| Новый этап | Original repeats | Cases | POST ceiling | READ ceiling |
|---|---|---:|---:|---:|
| GPT | 12–24 | 13 | 13 | 0 |
| Gemini | 0–24 | 25 | 27 | 2 |
| DeepSeek | 0–24 | 25 | 27 | 2 |
| R2 всего | без перенумерации | **63** | **67** | **4** |
| Aggregate R1+R2 | полный исходный набор | **75** | **81** | **6** |

GPT начинается с `owner_injection`12; после images20/21 остаются critical repeats
`unknown_price`22, `unknown_booking`23, `injection`24. Ни одного нового POST за
импортированные12 cases. Вместе с3 helper POST максимум84. R2 — отдельный stage
с новым deadline1800s, не продолжение старого in-flight запроса. Gemini transient
state и DeepSeek explicit none не меняются.

## Quality и технические STOP

Только в `SYNTHETIC_EXPERIMENT` required/forbidden regex, semantic expected outcome
и valid image-fact mismatch записываются в `quality_flags`. Для regex сохраняются
`code/pattern/match/span`, для outcome/image — expected/observed; case/final и
revision остаются в отчёте. Отрицание, цитата, настоящее утверждение и смешанный
ответ с тем же keyword остаются flagged. Никаких exemptions по «не могу», удаления
500/777/999 из fixtures, parser отрицания или LLM grader нет.

Quality flags не останавливают конечный сбор и не дают автоматического PASS.
Даже без flags assessment — `HUMAN_REVIEW_REQUIRED`, manual assessment — PENDING.
Transport/deadline/route/history/schema/usage/cost/call/byte/token errors,
невалидный/отсутствующий final и неполный обязательный READ roundtrip остаются
в `failures` и останавливают следующий POST. Обычный reviewed path по-прежнему
останавливается также на quality failures. Ни один путь не выбирает модель
или не включает runtime.

Summary отдельно показывает helper, imported R1, new stage, aggregate probe и
shared total. **Все confirmed calls** входят в сумму независимо от flags или
отклонения case; `completed_cost_rub` — лишь стоимость завершённых cases,
для расходов использовать `confirmed_cost_rub` и `known_call_count`.
Unknown calls и pending reservations имеют отдельные counts/резерв; неизвестный
расход — `null`, не0. Unstarted model — `NOT_RUN`, не оплаченная ошибка.
Per-model reservation fields относятся к новому stage (`NEW_STAGE_ONLY`),
импортированные confirmed charges уже погашают старые reservations.

## Одна Windows команда после принятия C0

Из обычного PowerShell на прежнем ПК заменить только `C0_ACCEPTED_FULL_SHA` и
`C0_ACCEPTED_DECISION_REF`. C0 сначала проверяет source/план и replay реального
R1 без HTTP/секрета, затем один full CI нового candidate и выдаёт запуск.
Команда использует существующий `ASM-M4-Probe-4f86e7f`, `.venv` и `.env.m4-probe`;
owner-only ACL ключа уже проверен. Файлы не переименовывать ради нового запуска.

```powershell
& {
    $ErrorActionPreference = "Stop"
    $Candidate = "C0_ACCEPTED_FULL_SHA"
    $DecisionRef = "C0_ACCEPTED_DECISION_REF"
    if ($Candidate -cnotmatch '^[0-9a-f]{40}$') { throw "Exact accepted SHA required" }
    if ([string]::IsNullOrWhiteSpace($DecisionRef) -or $DecisionRef -eq "C0_ACCEPTED_DECISION_REF") {
        throw "Exact C0 decision reference required"
    }
    $Repo = Join-Path $env:LOCALAPPDATA "ASM-M4-Probe-4f86e7f"
    Set-Location -LiteralPath $Repo
    $PriorReport = "reports\m4-polza-executable-eval-r1.jsonl"
    $Report = "reports\m4-polza-executable-eval-r2.jsonl"
    if (Test-Path -LiteralPath $Report) { throw "R2 report already exists; preserve it and do not replay" }
    if (-not (Test-Path -LiteralPath $PriorReport -PathType Leaf)) { throw "Original complete R1 report required" }
    $PriorHash = (Get-FileHash -LiteralPath $PriorReport -Algorithm SHA256).Hash
    if ($PriorHash -ine "b727cc1ca65c5ef189cc2bddba619136a354c6414b7159e0bde4d521f52f8b48") {
        throw "R1 receipt hash mismatch; do not edit the receipt"
    }
    $Dirty = git status --porcelain
    if ($LASTEXITCODE -ne 0 -or $Dirty) { throw "Clean checkout required" }
    git fetch origin $Candidate
    if ($LASTEXITCODE -ne 0) { throw "Candidate fetch failed" }
    git switch --detach $Candidate
    if ($LASTEXITCODE -ne 0) { throw "Candidate checkout failed" }
    $Actual = git rev-parse HEAD
    if ($LASTEXITCODE -ne 0 -or $Actual -cne $Candidate) { throw "Source SHA mismatch" }
    if (-not (Test-Path .\.venv\Scripts\python.exe)) { throw "Existing probe environment not found" }
    if (-not (Test-Path .\.env.m4-probe)) { throw "Existing private probe secret not found" }
    .\.venv\Scripts\python.exe -m asm.ai.probe --plan --synthetic-experiment --continue-from $PriorReport
    if ($LASTEXITCODE -ne 0) { throw "Offline prefix validation/plan failed" }
    Write-Host "Report: $Report"
    .\.venv\Scripts\python.exe -m asm.ai.probe --live --synthetic-experiment --continue-from $PriorReport `
        --secret-file .\.env.m4-probe --report $Report `
        --approved-rub 149.90426263 --approval-ref $DecisionRef `
        --source-sha $Candidate --source-environment LOCAL_DESKTOP
    if ($LASTEXITCODE -ne 0) { throw "Probe stopped; preserve both reports for C0; do not replay" }
    Write-Host "Report written; C0 must review all outputs, flags, routes and expenses"
}
```

`--plan --continue-from` читает только receipt/fixtures, не ключ и не HTTP.
До fresh catalog цена `null`. Live делает один catalog GET всех3 fixed routes,
пересчитывает **13/27/27** POST по новым ставкам, записывает conditional plan и
проверяет меньший explicit approval/остаток149.90426263 до первого нового POST.
Старые104.745359386 при R1 rates — историческая арифметика, не новый тариф.
Report создаётся exclusive (`x`). При STOP не повторять команду, не удалять отчёт
и не выбирать другое имя ради replay; дальнейшее решение остаётся у C0.

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
.venv/bin/ruff check backend/src/asm/ai/probe.py tests/test_m4_probe.py
.venv/bin/ruff format --check backend/src/asm/ai/probe.py tests/test_m4_probe.py
.venv/bin/mypy
.venv/bin/python -m asm.ai.probe --plan
.venv/bin/python -m asm.ai.probe --plan --synthetic-experiment
git diff --check
```

C4 использует CONTROLLED fixtures, без owner rows в Git. Полный controlled CLI
проверяет continuation63/67/4/134 history+1 catalog и aggregate75/81/6, fresh rates,
exact original order и отсутствие replay. Исходный full path75/81/6 тоже сохранён.
Проверяются отрицание/цитата/утверждение/смешанный ответ, required/outcome/image flags,
все hard STOP, invalid prefix/hash/budget, unknown pending charges и NOT_RUN.
Фактические результаты candidate — в receipt M4_HANDOFF. Adapter/settings/gateway/
contracts/prompt/schema/fixtures/model profiles/lock/CI остаются прежними.

C0 проверяет реальный34940-byte receipt своим экземпляром:
`--plan --synthetic-experiment --continue-from reports/m4-polza-executable-eval-r1.jsonl`.
Этот replay не загружает ключ и не делает HTTP. C4 не выдаёт controlled PASS за
replay owner-файла, Windows/Polza live или приёмку модели. После review — один full
CI нового source и owner запуск; PR39/main/VM/runtime/merge C4 не меняет.
