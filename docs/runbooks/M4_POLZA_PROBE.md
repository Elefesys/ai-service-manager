# M4.2 — готовый запуск оставшихся18 GPT scenarios

**Код C4 принят C0. Разрешён один запуск:18 scenarios, максимум18 запросов к
модели,0 READ,2 images и10 RUB из прежнего общего бюджета150.**
Семь ранее проверенных ответов и обе READ проверки сохраняются.

Source **7e48510311ab77c41f84b11becb2734ddb430690**, tree **23dad7ed0cf0e9974285db3881a1093e670fe443**;
[приёмка и границы C0](../tasks/M4_HANDOFF.md), [решение](../decisions/IMPL-004-m4-pilot-ai.md).
Ключ и установленное окружение прежние; переустановка не нужна.

## Готовая Windows команда — выполнить один раз

Вставь весь блок в PowerShell. Он проверит hashes обоих старых отчётов,
получит точный source, покажет offline plan и запустит оставшиеся scenarios.

```powershell
& {
    $ErrorActionPreference = "Stop"
    $Candidate = "7e48510311ab77c41f84b11becb2734ddb430690"
    $CandidateTree = "23dad7ed0cf0e9974285db3881a1093e670fe443"
    $PromptHash = "b420be44a7e4210de1151e5b0604b0fa9a08c19b1bfbedb8147f2a9b38455956"
    $DecisionRef = "C0-M4.2-GPT-QUALITY-R2:7e48510311ab77c41f84b11becb2734ddb430690:OWNER_REMAINING18_R2_10RUB"
    $StageRub = "10"
    $Repo = Join-Path $env:LOCALAPPDATA "ASM-M4-Probe-4f86e7f"
    Set-Location -LiteralPath $Repo
    $Report = "reports\m4-polza-gpt-quality-r2.jsonl"
    if (Test-Path -LiteralPath $Report) { throw "Preserve existing R2 report; do not replay" }
    $PriorChecks = @(
        @{ Path = "reports\m4-polza-gpt-quality-r1.jsonl"; Sha = "b0d1cb8249b321792355a2b4d29e1a79ba6eae30847a5deee6fbafa36159017f" },
        @{ Path = "reports\m4-polza-gpt-quality-history-r1.jsonl"; Sha = "bf09d2dba67de7fbbd1f9a88cde309ee0a135fc1df52ab0554f591beeb1fba24" }
    )
    foreach ($Check in $PriorChecks) {
        if (-not (Test-Path -LiteralPath $Check.Path -PathType Leaf)) { throw "Original receipt missing; return STOP to C0" }
        $ActualHash = (Get-FileHash -LiteralPath $Check.Path -Algorithm SHA256).Hash
        if ($ActualHash -ine $Check.Sha) { throw "Original receipt hash mismatch; preserve files and return STOP to C0" }
    }
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
    .\.venv\Scripts\python.exe -m asm.ai.probe --plan --gpt-quality-r2
    if ($LASTEXITCODE -ne 0) { throw "Offline plan failed" }
    Write-Host "Starting GPT R2: 18 scenarios, ceiling 10 RUB. Preserve the report at any outcome."
    .\.venv\Scripts\python.exe -m asm.ai.probe --live --gpt-quality-r2 `
        --secret-file .\.env.m4-probe --report $Report `
        --approved-rub $StageRub --approval-ref $DecisionRef `
        --source-sha $Candidate --source-environment LOCAL_DESKTOP
    $ProbeExit = $LASTEXITCODE
    if (-not (Test-Path -LiteralPath $Report)) { throw "No receipt; return STOP to C0 without retry" }
    Write-Host "GPT R2 receipt: $Report"
    if ($ProbeExit -ne 0) { Write-Host "STOP: preserve receipt; do not retry" }
    Get-FileHash -LiteralPath $Report -Algorithm SHA256
    Write-Host "Return the complete JSONL to C0; no automatic retry or runtime approval"
    Get-Content -LiteralPath $Report -Encoding UTF8
}
```

После плана консоль может некоторое время не печатать строки. Общий лимит —
**30 минут**, на один scenario вместе с history —60 секунд. Не запускай второй
экземпляр. В конце блок печатает hash и полный новый JSONL.

Верни **полный `reports/m4-polza-gpt-quality-r2.jsonl`**, даже при STOP.
Исходные R1/history reports сохраняются без изменения. Не удалять/переименовывать
отчёты ради повторного запуска. После одного receipt следующий paid шаг HOLD.

Offline PLAN_ONLY/PAID_NOT_AUTHORIZED — обычный план без key/HTTP; exact-source
допуск задан ref и10 RUB в блоке выше. Fresh catalog должен подтвердить резерв
всех18 calls≤10 до первого POST.10 — потолок, не ожидаемая стоимость.

## Что проверяем

Original repeats7–24: unknown duration, booking, clarification, context/injection,
handoff, privacy/payment/mutation/no_send_claim, обе synthetic images и critical
repeats22–24. Только GPT/openai/flex/provider-default. Text conversation_v2,
result/envelope v1, images synthetic_shapes_v1 неизменны; новых READ0, tools не
объявляются. Full quality по R1+R2 оценивает C0 вручную.

Новый gpt_eval_history_v2 принимает strict positive-int provider attempts
отдельно от client POST. Raw list/detail steps missing/null NOT_APPLICABLE,
int1 ONE_REPORTED; неверные типы/значения и nonnull server context отклоняются.
Identity/model/family/usage/cost/limits по-прежнему проверяются. Количество
attempts не умножает запросы/списания и не подтверждает routes каждой попытки;
flex variant NOT_OBSERVED. No retry/fallback/polling/arbitrary resume.

HUMAN_REVIEW_REQUIRED/exit0 означает18 технически завершённых scenarios,
не quality PASS25. Technical failure →FAILED_OR_INCOMPLETE. Flags и finals
сохраняются для C0; selected_model=null/runtime_authorized=false.

## Бюджет перед запуском

| Показатель | Значение |
|---|---:|
| Общий бюджет | 150 RUB |
| Confirmed / known client POST | 0.23889134 RUB /40 |
| Unknown client POST / held | 4 /7.585505548 RUB |
| Всего прежних client POST | 44 |
| Остаток с резервами | 142.175603112 RUB |
| Потолок нового stage | 10 RUB /18 POST |
| Максимум shared client POST | 62 |

Все4 old holds остаются; reported0.00743079 из metadata не освобождает GPT
hold0.465109963. Новые known/unknown учитываются отдельно, unknown не charge0.
Это ledger capacity, не account balance; catalog reservation — условная оценка.
Ограничения:36 history GET/1 catalog,32768/512 tokens и24576/32768 bytes на call,
total599040 tokens; catalog4MiB/20s, history65536 bytes/15s verification на POST.

## Проверено C0

916 targeted PASS15.06s, Ruff/format4, mypy71;9 actual offline plans,8 прежних
stdout byte-exact parent. Exact source/ref/10 CLI: полный18-case путь, retained
quality finding, late steps STOP и whole-stage budget STOP; exclusivity и old
holds сохранены. Real Polza HTTP/owner key reads0. Windows shell/live R2/full CI
нового source NOT_RUN; Windows block проверен статически, Python CLI — исполнением.

PR39 Draft/headcd60, CI41009211185 RED и C0-M4-CI-OBSERVATION-01 остаются.
Full integration CI нужен до merge/runtime. Main/VM/DB/Telegram/merge не менялись.
Gemini/DeepSeek compatibility DEFERRED; исходное75-case comparison не завершено.
