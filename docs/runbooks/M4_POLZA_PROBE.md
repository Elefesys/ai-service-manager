# M4.2 — готовая проверка GPT с conversation_v2

**Код C4 принят. Разрешён один запуск: 25 сценариев, максимум27 запросов к модели,
2 synthetic READ и15 RUB из прежнего общего бюджета150.** Это проверка качества
новых инструкций; результат потребует ручной оценки.

Source **ace29ce7d77564f8fecea84d4b7e734e6c8fbe56**, tree **8a716c528a917c8a77a853c226699ba4a47ccc2b**;
[приёмка C0](../tasks/M4_HANDOFF.md), [решение](../decisions/IMPL-004-m4-pilot-ai.md).
Ключ и установленное окружение используются прежние. Переустановка не нужна.

## Готовая Windows команда — один GPT quality запуск

Выполни блок **один раз** в PowerShell. Он проверяет исходники, новую версию
инструкций и отсутствие отчёта, показывает offline plan, затем запускает тест.

```powershell
& {
    $ErrorActionPreference = "Stop"
    $Candidate = "ace29ce7d77564f8fecea84d4b7e734e6c8fbe56"
    $CandidateTree = "8a716c528a917c8a77a853c226699ba4a47ccc2b"
    $PromptHash = "b420be44a7e4210de1151e5b0604b0fa9a08c19b1bfbedb8147f2a9b38455956"
    $DecisionRef = "C0-M4.2-GPT-QUALITY-R1:ace29ce7d77564f8fecea84d4b7e734e6c8fbe56:OWNER_25_CASES_R1_15RUB"
    $StageRub = "15"
    $Repo = Join-Path $env:LOCALAPPDATA "ASM-M4-Probe-4f86e7f"
    Set-Location -LiteralPath $Repo
    $Report = "reports\m4-polza-gpt-quality-r1.jsonl"
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
    $ActualPromptHash = (Get-FileHash -LiteralPath '.\backend\src\asm\ai\prompts\conversation_v2.txt' -Algorithm SHA256).Hash
    if ($ActualPromptHash -ine $PromptHash) { throw "Accepted prompt mismatch" }
    if (-not (Test-Path -LiteralPath '.\.venv\Scripts\python.exe' -PathType Leaf)) { throw "Existing environment required" }
    if (-not (Test-Path -LiteralPath '.\.env.m4-probe' -PathType Leaf)) { throw "Existing private key file required" }
    New-Item -ItemType Directory -Path 'reports' -Force | Out-Null
    .\.venv\Scripts\python.exe -m asm.ai.probe --plan --gpt-quality-r1
    if ($LASTEXITCODE -ne 0) { throw "Offline plan failed" }
    .\.venv\Scripts\python.exe -m asm.ai.probe --live --gpt-quality-r1 `
        --secret-file .\.env.m4-probe --report $Report `
        --approved-rub $StageRub --approval-ref $DecisionRef `
        --source-sha $Candidate --source-environment LOCAL_DESKTOP
    $ProbeExit = $LASTEXITCODE
    if (-not (Test-Path -LiteralPath $Report)) { throw "No receipt written; return STOP to C0 without retry" }
    Write-Host "GPT quality receipt: $Report"
    if ($ProbeExit -ne 0) { Write-Host "STOP: preserve receipt; do not retry" }
    Get-FileHash -LiteralPath $Report -Algorithm SHA256
    Write-Host "Return the complete JSONL to C0; no retry or runtime approval"
    Get-Content -LiteralPath $Report -Encoding UTF8
}
```

После плана консоль может некоторое время не печатать строки. Общий лимит —
**30 минут**, на один сценарий вместе с READ/follow-up/history —60 секунд.
Не запускай второй экземпляр. В конце блок печатает hash и полный JSONL.
Верни файл целиком даже при STOP; отчёты предыдущих запусков сохраняются.

Offline `PLAN_ONLY / PAID_NOT_AUTHORIZED` описывает план и не обращается к API.
Единственный live допуск задан exact source/ref/15 в блоке выше. Fresh catalog
должен подтвердить прежний route/capabilities/rates/fees; если резерв всех27 calls
больше15 RUB, выполнение остановится до model POST.15 — потолок, не ожидаемая цена.

## Что проверяем

Только openai/gpt-6-luna, request selector openai/flex, provider-default и прежний
auto-tools. Те же25 сценариев,3 critical repeats и2 изображения. Новая
conversation_v2 требует proposed handoff при просьбе связаться с владельцем
и запрещает придумывать правила бизнеса; известные факты/уточнения разрешены.
Прежние v1 ответы и их оценки сохраняются, schema и fixtures не менялись.

Text/tool config/system message/report используют v2/hash выше. Изображения
сохраняют synthetic_shapes_v1/EVAL_ONLY. Максимумы:27 model POST/2 READ/54 history
GET/1 catalog GET,32768/512 tokens и24576/32768 bytes на call. No retry/fallback/
polling/resume. Запрошенный flex не подтверждает вариант маршрута; identity,
family, usage и cost проверяются по истории прежними правилами.

**HUMAN_REVIEW_REQUIRED** означает завершённые технические сценарии; даже
exit0 и отсутствие flags не являются quality PASS. C0 проверит каждый final.
При technical error будет FAILED_OR_INCOMPLETE/exit2; полный report нужен и в
этом случае. После одного отчёта новый платный шаг HOLD до C0 review.
selected_model=null/runtime_authorized=false во всех исходах.

## Бюджет перед запуском

| Показатель | Значение |
|---|---:|
| Общий бюджет | 150 RUB |
| Подтверждённый расход / known POST | **0.17932550 RUB /31** |
| Unknown POST | **3**: 2 Gemini +1 DeepSeek |
| Held по этим запросам | **7.120395585 RUB** |
| Всего прежних model attempts | **34** |
| Confirmed + held | **7.299721085 RUB** |
| Остаток с резервами | **142.700278915 RUB** |
| Потолок нового этапа | **15 RUB /27 POST** |

Все3 old holds остаются; новые confirmed/unknown учитываются отдельно. Максимум
61 shared attempts. Это ledger capacity, не баланс аккаунта; резерв не равен
списанию. При потере ответа reservation остаётся UNKNOWN, повтор не разрешён.
Не удалять/не переименовывать файл, чтобы обойти existing-report guard.

## Проверено C0

799 targeted tests PASS13.15s; Ruff/format7, mypy71,8 actual offline plans,
первые7 равны parent; wheel с byte-exact v1/v2. Exact CLI source/ref/15 проверен
через MockTransport: полный25-case путь, сохранённый quality finding, late
history STOP и превышение whole-stage reserve. Все3 old holds и exclusivity
сохраняются. Реальные Polza HTTP/owner key reads0; actual Windows/hosted v2
quality/full CI нового source NOT_RUN. [Полный receipt C4](https://github.com/Elefesys/ai-service-manager/blob/ace29ce7d77564f8fecea84d4b7e734e6c8fbe56/docs/tasks/M4_HANDOFF.md).

PR39 остаётся Draft/headcd60; RED CI41009211185 и C0-M4-CI-OBSERVATION-01 не закрыты.
Full CI интеграционного кандидата нужен до merge/runtime. Main/VM/DB/Telegram/
merge не менялись. Gemini/DeepSeek compatibility DEFERRED, исходное75-case
comparison не завершено. Текущая проба не включает AI runtime или Telegram bridge.
