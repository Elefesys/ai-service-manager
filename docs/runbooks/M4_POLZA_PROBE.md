# M4.2 — готовый DeepSeek tool roundtrip

**C0 принял код и разрешил один запуск: максимум2 model POST,1 synthetic READ
и1 RUB внутри прежнего бюджета150.** Source **5885df1b0ba04378e8af6f2089d2fc86be6c22e3**,
tree **6ca70ba7f6d431accaa0478e1d515cc69ebae7b9**; [приёмка C0](../tasks/M4_HANDOFF.md).
Это отдельный named READ → strict final профиль. Предыдущий25-case auto eval
не повторяется, старые отчёты и резервы Gemini сохраняются.

## Готовая Windows команда — один DeepSeek tool roundtrip

Выполни блок **один раз** в PowerShell. Он использует существующий checkout,
окружение и `.env.m4-probe`; переустановка и замена ключа не нужны.

```powershell
& {
    $ErrorActionPreference = "Stop"
    $Candidate = "5885df1b0ba04378e8af6f2089d2fc86be6c22e3"
    $CandidateTree = "6ca70ba7f6d431accaa0478e1d515cc69ebae7b9"
    $DecisionRef = "C0-M4.2-DEEPSEEK-TOOL-COMPAT-R1:5885df1b0ba04378e8af6f2089d2fc86be6c22e3:OWNER_ROUNDTRIP_R1_1RUB"
    $StageRub = "1"
    $Repo = Join-Path $env:LOCALAPPDATA "ASM-M4-Probe-4f86e7f"
    Set-Location -LiteralPath $Repo
    $Report = "reports\m4-polza-deepseek-tool-compat-r1.jsonl"
    if (Test-Path -LiteralPath $Report) { throw "Preserve existing report; do not replay" }
    $Dirty = git status --porcelain --untracked-files=normal
    if ($LASTEXITCODE -ne 0 -or $Dirty) { throw "Clean checkout required; return STOP to C0" }
    git fetch origin $Candidate
    if ($LASTEXITCODE -ne 0) { throw "Source fetch failed" }
    git checkout --detach $Candidate
    if ($LASTEXITCODE -ne 0) { throw "Source checkout failed" }
    $Actual = git rev-parse HEAD
    if ($LASTEXITCODE -ne 0 -or $Actual -cne $Candidate) { throw "Accepted source mismatch" }
    $ActualTree = git rev-parse 'HEAD^{tree}'
    if ($LASTEXITCODE -ne 0 -or $ActualTree -cne $CandidateTree) { throw "Accepted tree mismatch" }
    $Dirty = git status --porcelain --untracked-files=normal
    if ($LASTEXITCODE -ne 0 -or $Dirty) { throw "Clean accepted source required" }
    if (-not (Test-Path -LiteralPath '.\.venv\Scripts\python.exe' -PathType Leaf)) { throw "Existing environment required" }
    if (-not (Test-Path -LiteralPath '.\.env.m4-probe' -PathType Leaf)) { throw "Existing private key file required" }
    New-Item -ItemType Directory -Path 'reports' -Force | Out-Null
    .\.venv\Scripts\python.exe -m asm.ai.probe --plan --deepseek-tool-compat
    if ($LASTEXITCODE -ne 0) { throw "Offline plan failed" }
    .\.venv\Scripts\python.exe -m asm.ai.probe --live --deepseek-tool-compat `
        --secret-file .\.env.m4-probe --report $Report `
        --approved-rub $StageRub --approval-ref $DecisionRef `
        --source-sha $Candidate --source-environment LOCAL_DESKTOP
    $ProbeExit = $LASTEXITCODE
    if (-not (Test-Path -LiteralPath $Report)) { throw "No receipt written; return STOP to C0 without retry" }
    Write-Host "DeepSeek compatibility receipt: $Report"
    if ($ProbeExit -ne 0) { Write-Host "STOP/REVIEW_REQUIRED: preserve receipt; do not retry" }
    Get-FileHash -LiteralPath $Report -Algorithm SHA256
    Write-Host "Return the complete JSONL to C0; no retry or runtime approval"
    Get-Content -LiteralPath $Report -Encoding UTF8
}
```

После offline plan промежуточных строк может не быть. Общий лимит stage120s,
roundtrip60s; не запускать второй экземпляр. В конце блок печатает весь JSONL
и hash. Вернуть файл целиком даже при exit2/STOP. Старые reports не менять.

Offline `PLAN_ONLY / PAID_NOT_AUTHORIZED` описывает только план. Допуск одного
live шага задан exact source/ref/1 RUB в этом блоке. Сам план не запускает API.
PROTOCOL_OBSERVED / HUMAN_REVIEW_REQUIRED ещё требует ручной оценки ответа.
QUALITY_FLAGGED / HUMAN_REVIEW_REQUIRED и FAILED_OR_INCOMPLETE не разрешают
retry. После одного отчёта следующий paid шаг HOLD до C0 review.

## Результат владельца

Source **5f5ece5426d675559c15fe1b74561dc6dddd456a**, исходный
`reports/m4-polza-deepseek-eval-r1.jsonl` принят целиком:7993 bytes/5 events,
SHA256 `b2e716a962a8966aaff61f8eb8cec57419ea4d2b7c1375caf8b6578ec08ebfcc`.
Approval OWNER_25_CASES_R1 использован; это не разрешение на retry.

- Первый `tool_current`:1 model POST,2 history GET,0 synthetic READ и0 follow-up.
  До него выполнен1 catalog GET.
- Вместо tool call пришёл schema-valid final
  `{"kind":"handoff","text":"С","reason":"С"}`. Ошибка `READ_ROUND_TRIP`
  правильно остановила stage. Ручная оценка этого ответа — QUALITY_FAIL.
- Usage575/31, reported reasoning0; finish_reason=stop, а не length. History
  подтвердили family `Wafer` и расход **0.00423361 RUB**. Generation
  `gen_2227387791288176641`; вариант `us` не наблюдён, только запрошен.
- Из25 сценариев попытка была только у первого; успешно завершённых0.
  Остальные24, включая изображения, NOT_RUN. Нельзя делать вывод о качестве
  всей модели или считать n1 достоверным сравнением скорости/цены.

## Почему не было вызова инструмента

В [официальной документации Wafer](https://docs.wafer.ai/serverless/chat-completions#structured-outputs)
указано: при `tools` + `response_format` и `tool_choice:auto` сервер формирует
JSON-ответ; для tool call нужен `required` или named function. Во втором случае
response_format игнорируется. Наша исходная проба отправляет первую комбинацию.
Наблюдение согласуется с документированным ограничением; внутреннюю обработку
Polza этот report не показывает. Отсутствие READ не доказывает, что DeepSeek
вообще не умеет вызывать функции.

Отдельная причина текста «С» пока UNKNOWN. Наш parser не обрезает строки:
в controlled проверке длинный handoff проходит неизменным. Одну букву допускает
прежний DTO; валидный JSON не означает полезный ответ. Не менять schema/prompt
или отключать проверки ради этого результата.

## Общий бюджет после этой попытки

| Показатель | Значение |
|---|---:|
| Общий бюджет | 150 RUB |
| Подтверждённый расход / known POST | **0.17932550 RUB /31** |
| Unknown POST | 2 Gemini |
| Их удержанные резервы | **6.929759328 RUB** |
| Всего model attempts | 33 |
| Confirmed + held | 7.109084828 RUB |
| Остаток с резервами | **142.890915172 RUB** |

Новый DeepSeek charge подтверждён, новых unknown нет. Его whole-stage reserve
5.147178939 и call reserve0.190636257 RUB — лимиты резервирования, не списания.
Это расчёт общего ledger, не проверка счёта Polza. Оба старых Gemini unknown
остаются; диагностический body amount0.05269262 не погашает их.

## Подготовленный режим

Только прежний `tool_current`, repeat0. Первый request содержит один
`read_current` и named `tool_choice:{type:"function",function:{name:"read_current"}}`.
Response format в этой фазе явно помечен `IGNORED_BY_DOCUMENTED_TOOL_MODE`.
После проверок tool name/typed args, identity/usage/cost по history выполняется
один synthetic READ. Второй request сохраняет tool declaration и историю
assistant/tool, задаёт `tool_choice:"none"` и прежний strict
`conversation_result_envelope_v1`. Local DTO и factual quality flags прежние.

В fresh selected `wafer/us` нужны `supported` для
[`tool_choice_function` и `tool_choice_none`](https://polza.ai/docs/gaidy/models),
а также прежние tools/strict schema/non-thinking/rates/fees/caps. Missing,
unknown, ignored или rejected — STOP до POST. `supported_parameters:tool_choice`
сам по себе недостаточен. `reasoning:{effort:"none",enabled:false}` обеих фаз
не меняется. Декларации каталога не доказывают фактический маршрут или тариф аккаунта.

| Ограничение | Значение |
|---|---|
| HTTP / READ | 1 catalog GET / ≤2 model POST / ≤4 history GET / ≤1 synthetic READ |
| Route | Только DeepSeek, selector `wafer/us`; observed family отдельно, variant NOT_OBSERVED |
| Tokens / bytes на call | Input/output32768/512; wire bytes24576/32768 |
| Время | Общие60s на весь model roundtrip;120s на stage |
| Catalog / history | 4MiB/20s;65536 bytes на history GET,15s verification на POST |
| Stage reserve | ≤1 RUB; резерв обоих calls должен поместиться до первого POST |
| Shared ledger | Prior33 attempts; максимум35; оба старых Gemini holds сохраняются |

Никаких retry/fallback/history polling. Ошибка первой фазы исключает READ и
второй POST. Reservations монотонны и flush до HTTP; отсутствие результата
после reservation остаётся UNKNOWN. Summary сохраняется при обрабатываемом STOP;
после аварийного завершения процесса последняя reservation также не разрешает replay.

`PROTOCOL_OBSERVED / HUMAN_REVIEW_REQUIRED` означает только две проверенные
фазы. Ручная оценка факта остаётся PENDING, даже без regex flags. Ответ «С»
сохраняется целиком и даёт `QUALITY_FLAGGED / HUMAN_REVIEW_REQUIRED`, exit2.
Прочие STOP — `FAILED_OR_INCOMPLETE`, exit2. Ни один статус не завершает25-case
comparison, не подтверждает auto-tools, не выбирает модель и не допускает runtime.
Старый DeepSeek mode имеет прежний prior: его consumed команду не запускать.
Бюджет150 заново подтверждать не нужно.

## Offline plan

Из корня checkout с установленными locked dependencies:

```powershell
uv run --frozen --no-sync python -m asm.ai.probe --plan --deepseek-tool-compat
```

Ожидается `DEEPSEEK_TOOL_COMPAT_R1 / PLAN_ONLY / PAID_NOT_AUTHORIZED`, один
`tool_current`,2 calls/1 READ/4 history, ceiling1, prior0.17932550+6.929759328,
remaining142.890915172. Fresh reservation пока null; selected_model=null,
runtime_authorized=false. Это не preflight и не проверка владельческого ключа.

## CONTROLLED receipt нового режима

Только MockTransport, synthetic catalog/ответы; sockets и owner .env reads
запрещены audit guard. Фактических Polza API HTTP0, paid POST0. Два наблюдённых
wire requests: named read_current → none;2 POST/1 READ/4 history+1 catalog.
Fake rates8/45/0 RUB дают reserve0.285184000 на call и0.570368000 на stage.
Подставной charge0.001+0.001, новый confirmed0.002; shared confirmed0.18132550,
held6.929759328, remaining142.888915172. Это тест арифметики, не новый расход.
Тестовый final: `{"kind":"reply","text":"Улица Модельная, 12","reason":null}`;
manual PENDING, variant NOT_OBSERVED, selected_model=null/runtime=false.

Отказы проверены отдельно на обеих фазах. Late STOP сохраняет known первого
call0.001 и UNKNOWN второго: new held0.285184000, shared held7.214943328.
Неверные tool name/args, лишний tool, early final, late schema, «С», family
drift, history identity/usage/cost, non-thinking, limits, отмена, таймаут,
reservation без case и попытка изменить второй wire на auto проверены.
Прежний адаптер по-прежнему отправляет auto/auto. Точные checks — в receipt C4.

## Проверки и сохранённые ограничения

Для source5885df1 C0: **711 targeted tests PASS11.25s**, Ruff/format4/mypy71,
7 offline CLI plans (первые6 равны base), AST прежних definitions и4 controlled
exact-command исхода PASS. Code fixes не потребовались. Реальные sockets и
owner .env reads запрещены; Windows/hosted mode и полный CI source5885df1
NOT_RUN. Переустановка не нужна: dependencies/lock не менялись.

Исторический review owner eval-r1: C0 пересчитал summary, caps, reservations
и quality flags по5 events.
4 CONTROLLED проверки PASS: whole-stage STOP по такому final; длинный текст
без обрезания; отказ правильного адреса без READ; положительный2-call roundtrip.
MockTransport, sockets и owner .env reads запрещены. Source не менялся,
прежние616 targeted checks и полный CI не повторялись. Это не новый hosted PASS.

GPT25 finals/27 POST/2 READ сохраняются: no_send_claim19 QUALITY_FAIL,
unknown_price22 QUALITY_NOTE. Gemini BLOCKED,2 failed POST/0 final. Исходное
75-case comparison не завершено; модель не выбрана, runtime_authorized=false.
PR39 Draft/headcd60, CI41009211185 RED; root cause M3 observer timeout UNKNOWN,
C0-M4-CI-OBSERVATION-01 и full CI интеграционного кандидата нужны до merge/runtime.
Main/VM/DB/Telegram этим отчётом не меняются.

## Использованные инструкции — только история

- [DeepSeek eval-r1](https://github.com/Elefesys/ai-service-manager/blob/1dfc6ec3a22d1be38a4a3269af847775bfc6db10/docs/runbooks/M4_POLZA_PROBE.md): consumed, не повторять.
- [Gemini diagnostic-r1](https://github.com/Elefesys/ai-service-manager/blob/2a1848f7089efda50913e24a58fcf21cafe167fc/docs/runbooks/M4_POLZA_PROBE.md): consumed, SIGNATURE_EXTRA_MISSING, charge UNKNOWN.
- [History-r1](https://github.com/Elefesys/ai-service-manager/blob/c94d2ff7923c930a8e3d1983b9a05f07414eb967/docs/runbooks/M4_POLZA_PROBE.md): UNKNOWN/HISTORY_PROVIDER_UNKNOWN,0 POST.
- [R2](https://github.com/Elefesys/ai-service-manager/blob/6e37623c804695c08cbb83d3fba8ee03ec9c4e1f/docs/runbooks/M4_POLZA_PROBE.md): stopped, не replay/resume approval.

Все исходные файлы сохранить. Ключ, raw response/reasoning или signature
передавать C0/C4 не нужно.
