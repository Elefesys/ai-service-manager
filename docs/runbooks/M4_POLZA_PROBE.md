# M4.2 — finite synthetic Polza experiment

**CURRENT: R1 выполнен частично; повтор/continuation HOLD.**
Получен terminal tail: GPT12 scenarios/14 reserved calls, затем ложный
FORBIDDEN_CLAIM в injection — matcher нашёл500 в корректном отказе подтверждать
цену. Gemini/DeepSeek ещё не запускались. Полный исходный JSONL нужен C0 для
сверки расходов/outputs и подготовки продолжения; не удалять/не переименовывать
отчёт для повторного запуска. Подробности — [текущий handoff](../tasks/M4_HANDOFF.md).

Ниже сохранён исторический одноразовый допуск R1. Он уже использован и не
разрешает заново выполнять приведённую команду. Source/CI остаются прежними.


**Историческая приёмка R1: C0 source review PASS; CI11/11 SUCCESS; paid75 PARTIAL.**
Source **b1ff8f1463e12ff65a64d692b7fc7718aa8d05fc**, tree
**75227361cac6f619d51d19acfc3e0c8e413fa530**; full CI
[40915999616](https://github.com/Elefesys/ai-service-manager/actions/runs/40915999616),
attempt1. C0 independently:399 targeted PASS, Ruff/format5, mypy71, offline plans,
scope/diff PASS. Решение **C0-M4.2-EXECUTABLE-EVAL-ACCEPT-R1** и полный receipt —
[M4_HANDOFF](../tasks/M4_HANDOFF.md). Experimental admission —
[IMPL-004](../decisions/IMPL-004-m4-pilot-ai.md).

Команда использует существующие `.venv` и `.env.m4-probe` владельца.
Ключ повторно вводить, передавать в чат или переустанавливать зависимости не нужно.
C0 допускает один новый finite synthetic experiment на этом source;
самостоятельный повтор после STOP не входит в решение.

Общий согласованный бюджет **150 RUB** уже включает **0.01269785 RUB / 3 POST**
предыдущих GPT observations. Новый этап ограничен **149.98730215 RUB**, меньшая
явно заданная сумма сохраняет силу. Полный результат требует ручного review C0;
`selected_model=null`, `runtime_authorized=false`. Клиентские данные, Telegram,
БД, VM, runtime и merge в этот experiment не входят.

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

## Архив команды R1 — повторно не запускать

В обычном PowerShell на прежнем ПК выполнить блок целиком. Он использует
существующий каталог ASM-M4-Probe-4f86e7f, проверяет точный source и
сохранённый отчёт до любых Polza-запросов. `.env.m4-probe` остаётся локальным
с уже проверенным owner-only ACL. Если каталог или prerequisite отличается —
STOP без переустановки/удаления. Терминал может молчать до30 минут; progress
пишется в JSONL, новый запуск в это время не выполнять.

```powershell
& {
    $ErrorActionPreference = "Stop"
    $Candidate = "b1ff8f1463e12ff65a64d692b7fc7718aa8d05fc"
    $DecisionRef = "C0-M4.2-EXECUTABLE-EVAL-ACCEPT-R1:b1ff8f1463e12ff65a64d692b7fc7718aa8d05fc:CI40915999616"
    $Repo = Join-Path $env:LOCALAPPDATA "ASM-M4-Probe-4f86e7f"
    Set-Location -LiteralPath $Repo
    $Report = "reports\m4-polza-executable-eval-r1.jsonl"
    if (Test-Path -LiteralPath $Report) { throw "Report already exists; do not repeat the probe" }
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
    .\.venv\Scripts\python.exe -m asm.ai.probe --plan --synthetic-experiment
    if ($LASTEXITCODE -ne 0) { throw "Offline plan failed" }
    New-Item -ItemType Directory -Force -Path reports | Out-Null
    Write-Host "Report: $Report"
    .\.venv\Scripts\python.exe -m asm.ai.probe --live --synthetic-experiment `
        --secret-file .\.env.m4-probe --report $Report `
        --approved-rub 149.98730215 --approval-ref $DecisionRef `
        --source-sha $Candidate --source-environment LOCAL_DESKTOP
    $ProbeExit = $LASTEXITCODE
    if (Test-Path -LiteralPath $Report) { Get-Content -LiteralPath $Report -Encoding UTF8 -Tail 3 }
    if ($ProbeExit -ne 0) { throw "Probe stopped; preserve report and return it to C0; do not replay" }
    Write-Host "Complete. Return the JSONL report to C0: $Report"
}
```

Offline `--plan --synthetic-experiment` не читает secret и не делает HTTP; до fresh
catalog цена в нём `null`. В `--live` выполняется **один** catalog GET, затем все
проверки и запись свежего conditional plan, и только потом model POST.
Отдельного preflight или review JSON для этой команды нет. Report создаётся
exclusive (`x`); прерванный запуск нельзя возобновить или перезаписать тем же report.
Фиксированное имя отчёта и exclusive open предотвращают случайный повтор этой команды;
переименование/удаление отчёта не разрешает повторные расходы.
При STOP сохранить JSONL и передать C0 для решения; unknown attempt не равен нулю.

## Расход, маршрут и протокол

До POST записываются fresh catalog hash/date, фиксированный selector, declared
capabilities, cap alias, reasoning profile, assumptions, все известные rates,
резерв каждого call и всех81, prior/approved amounts. `catalog_experiment` не
подменяет дату старого review. Данные прежнего каталога/старый резерв107.138276775
не используются для live admission. Все три новые резерва должны поместиться
в stage approval и остаток общего150.

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

| Неизменённый предел | Значение |
|---|---|
| Cases / model POST / READ | 75 / ≤81 новых / ≤6; prior3 +81 =≤84 POST |
| Сценарии на модель | 20 text (включая2 READ roundtrip),3 critical repeats,2 PNG |
| Input / output tokens | 32768 /512 на call |
| Wire input / output bytes | 24576 /32768 на call |
| Case / run deadline | 60 /1800 секунд; catalog/history внутри общего бюджета |
| History | ≤2 GET/POST,≤162/этап;65536 bytes/GET;≤15s на обе проверки |
| Catalog | 1 GET перед первым POST;4MiB,20s |
| Synthetic fixtures normalized SHA256 | `7abd25f1e1f08e51eacc3a68975e6099c942d33fad37376366dfdef6c7e025b2` |
| Стоимость | prior0.01269785 +stage≤149.98730215 ≤общего150 RUB |

Каждый call резервируется/flush до возможного POST. Неизвестный charge сохраняет
резерв. Deadline/transport/protocol/quality/usage/cost failure останавливает весь
этап, без retry/repair/fallback. Canonical conversation schema не меняется:
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

В существующем CPython3.13 frozen окружении из корня checkout:

```sh
.venv/bin/pytest -q tests/test_m4_polza.py tests/test_m4_probe.py tests/test_m4_gateway.py tests/test_m4_gateway_failures.py
.venv/bin/ruff check backend/src/asm/ai/polza.py backend/src/asm/ai/settings.py backend/src/asm/ai/probe.py tests/test_m4_polza.py tests/test_m4_probe.py
.venv/bin/ruff format --check backend/src/asm/ai/polza.py backend/src/asm/ai/settings.py backend/src/asm/ai/probe.py tests/test_m4_polza.py tests/test_m4_probe.py
.venv/bin/mypy
.venv/bin/python -m asm.ai.probe --plan
.venv/bin/python -m asm.ai.probe --plan --synthetic-experiment
git diff --check
```

C4 candidate: **399 targeted PASS**, Ruff/format5 PASS, strict mypy71 PASS,
default/оба offline plans и diff check PASS. Controlled полный CLI:75 finals,
81 POST,6 READ,1 catalog +162 history GET; обе формы body provider. Mock требует
разные signatures для Gemini roundtrips и explicit none на каждом DeepSeek POST.
Проверены metadata/correlation/byte bounds, cross-run/case cleanup, changed family,
unknown fee/capability, overbudget и actual usage/cost STOP.

Локальная проверка **исторического** public snapshot10:43:36Z сохранила его дату:
все3 fixed profiles проходят catalog admission, резерв81 равен111.008526759 RUB
(включая audio cache). Это проверка совместимости формы snapshot с кодом,
не новый fresh plan, не live/account proof и не обещание фактического списания.
Windows PowerShell команда подготовлена для существующего окружения владельца;
controlled CLI проверен на CPython3.13.16 Linux, Windows/Polza live не запускались.

C0 проверил exact candidate b1ff8f1:399 targeted PASS, Ruff/format5 и mypy71,
offline plans/scope PASS. Full CI40915999616 attempt1 — **11/11 SUCCESS**:
2596 ordinary+155 subtests,804 PostgreSQL,54 browser,398 frontend tests.
Tested merge fffe3720cb2f36b69c12d225bb0725915b3c7102 tree точно равен
source tree75227361cac6f619d51d19acfc3e0c8e413fa530. Native/cleanup/durable/
Docker29/6 migration shards PASS; CI не перезапускался. Старый78dabd8 CI40902629746
также завершился SUCCESS11/11, но не использован вместо новой проверки.
Приёмка не меняет source/PR head/main и не является runtime admission.
