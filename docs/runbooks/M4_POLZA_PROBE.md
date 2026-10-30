# M4.2 — прочитать метаданные остановившегося GPT запроса

**Платный тест уже выполнен и остановлен. Сейчас — только чтение истории:
максимум2 GET, без новых генераций, catalog запросов и READ.**

7 полученных ответов проверены C0: PASS. На восьмом сценарии verifier отказал
из-за attemptsCount: пришло целое число, отличное от1, но само значение не
сохранено. Получим его вместе с cost/usage существующей generation
`gen_2227417601602097153`. [Разбор C0](../tasks/M4_HANDOFF.md),
[решение](../decisions/IMPL-004-m4-pilot-ai.md).

## Готовая Windows команда — один metadata read

Выполни весь блок **один раз** в PowerShell. Он использует прежние source,
окружение и ключ, проверяет hash исходного отчёта и создаёт отдельный JSONL.
Ничего переустанавливать, обновлять или передавать ключ не нужно.

```powershell
& {
    $ErrorActionPreference = "Stop"
    $Candidate = "ace29ce7d77564f8fecea84d4b7e734e6c8fbe56"
    $CandidateTree = "8a716c528a917c8a77a853c226699ba4a47ccc2b"
    $Repo = Join-Path $env:LOCALAPPDATA "ASM-M4-Probe-4f86e7f"
    Set-Location -LiteralPath $Repo
    $Actual = git rev-parse HEAD
    if ($LASTEXITCODE -ne 0 -or $Actual -cne $Candidate) { throw "Existing accepted source required; return STOP to C0" }
    $ActualTree = git rev-parse 'HEAD^{tree}'
    if ($LASTEXITCODE -ne 0 -or $ActualTree -cne $CandidateTree) { throw "Accepted tree mismatch" }
    $Dirty = git status --porcelain --untracked-files=normal
    if ($LASTEXITCODE -ne 0 -or $Dirty) { throw "Clean accepted source required" }
    if (-not (Test-Path -LiteralPath '.\.venv\Scripts\python.exe' -PathType Leaf)) { throw "Existing environment required" }
    if (-not (Test-Path -LiteralPath '.\.env.m4-probe' -PathType Leaf)) { throw "Existing private key file required" }
    $Report = "reports\m4-polza-gpt-quality-history-r1.jsonl"
    if (Test-Path -LiteralPath $Report) { throw "Preserve existing history receipt; do not repeat" }
    $ReadOnlyScript = @'
import asyncio
import hashlib
import json
from decimal import Decimal
from pathlib import Path

from asm.ai.contracts import Cost, strict_json
from asm.ai.polza import HISTORY, HISTORY_LIST, bounded_http
from asm.ai.settings import load_secret

TARGET = "gen_2227417601602097153"
SOURCE = "ace29ce7d77564f8fecea84d4b7e734e6c8fbe56"
DIGEST = "b0d1cb8249b321792355a2b4d29e1a79ba6eae30847a5deee6fbafa36159017f"
INPUT = Path("reports/m4-polza-gpt-quality-r1.jsonl")
OUTPUT = Path("reports/m4-polza-gpt-quality-history-r1.jsonl")


def integer(value):
    return value if type(value) is int and abs(value) <= 10000000 else None


def label(value, allowed):
    return value if type(value) is str and value in allowed else None


def money(value):
    try:
        if type(value) not in (str, int, float):
            return None
        cost = Cost(status="CONFIRMED", amount=Decimal(str(value)), currency="RUB")
        return str(cost.amount)
    except (ValueError, TypeError, ArithmeticError):
        return None


def project(row, detail=False):
    usage = row.get("usage")
    usage = usage if type(usage) is dict else {}
    result = {
        "id": TARGET,
        "model": label(row.get("model"), ("openai/gpt-6-luna", "gpt-6-luna")),
        "provider": label(
            row.get("finalEndpointSlug" if detail else "provider"), ("OpenAI",)
        ),
        "status": label(row.get("status"), ("completed", "failed", "pending")),
        "request_type": label(
            row.get("requestType"), ("chat", "image", "video", "audio")
        ),
        "reported_cost_rub": money(row.get("clientCost" if detail else "cost")),
        "usage": {
            k: integer(usage.get(k))
            for k in ("prompt_tokens", "completion_tokens", "total_tokens")
        },
    }
    if detail:
        result.update(
            attempts_count=integer(row.get("attemptsCount")),
            attempts_count_type={
                int: "INT",
                str: "STRING",
                float: "FLOAT",
                bool: "BOOL",
                type(None): "NULL",
                list: "ARRAY",
                dict: "OBJECT",
            }.get(type(row.get("attemptsCount")), "OTHER")
            if "attemptsCount" in row
            else "MISSING",
            api_type=label(
                row.get("apiType"),
                ("completions", "chat_completions", "responses", "media"),
            ),
            response_mode=label(row.get("responseMode"), ("sync", "stream", "async")),
            finish_reason=label(
                row.get("finishReason"),
                ("stop", "length", "tool_calls", "content_filter"),
            ),
            is_cancelled=row.get("isCancelled")
            if type(row.get("isCancelled")) is bool
            else None,
            steps_count=integer(row.get("stepsCount")),
            has_parent=bool(row.get("parentGenerationId")),
            has_server_tools=bool(row.get("serverTools")),
        )
    return result


def main():
    try:
        output = OUTPUT.open("x", encoding="utf-8")
    except OSError:
        print("STOP / REPORT_EXISTS_OR_CANNOT_CREATE / NO_HTTP")
        return 2
    with output:
        gets = 0

        def emit(row):
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
            output.flush()

        emit(
            {
                "event": "source",
                "mode": "GPT_QUALITY_HISTORY_R1",
                "source_sha": SOURCE,
                "input_sha256": DIGEST,
                "input_validation": "PENDING",
                "generation_id": TARGET,
                "max_history_gets": 2,
                "bytes_per_get": 65536,
                "seconds_per_get": 15,
                "overall_seconds": 45,
                "model_posts": 0,
                "catalog_gets": 0,
                "reads": 0,
                "cost_status": "UNSETTLED",
                "automatic_reserve_release": False,
                "runtime_authorized": False,
            }
        )
        try:
            with INPUT.open("rb") as source_file:
                raw = source_file.read(65537)
            if len(raw) > 65536 or hashlib.sha256(raw).hexdigest() != DIGEST:
                raise ValueError
            settings = load_secret(Path(".env.m4-probe"))

            async def inspect():
                nonlocal gets

                async def get(url):
                    nonlocal gets
                    gets += 1
                    emit(
                        {
                            "event": "history_get",
                            "index": gets,
                            "target": "LIST_FIRST_5"
                            if gets == 1
                            else "EXACT_ID_DETAIL",
                            "model_posts": 0,
                        }
                    )
                    body = await bounded_http(
                        settings.api_key, url, body=None, seconds=15, maximum=65536
                    )
                    data = strict_json(body.decode("utf-8"))
                    if settings.api_key.get_secret_value() in json.dumps(
                        data, ensure_ascii=False
                    ):
                        raise ValueError
                    return data

                async with asyncio.timeout(45):
                    listing = await get(HISTORY_LIST)
                    items = listing.get("items") if type(listing) is dict else None
                    if (
                        type(items) is not list
                        or len(items) > 5
                        or any(type(item) is not dict for item in items)
                    ):
                        raise ValueError
                    matches = [item for item in items if item.get("id") == TARGET]
                    if len(matches) != 1:
                        raise ValueError
                    detail = await get(HISTORY + "/" + TARGET)
                    if type(detail) is not dict or detail.get("id") != TARGET:
                        raise ValueError
                    return {
                        "generation": project(matches[0]),
                        "detail": project(detail, True),
                    }

            metadata = asyncio.run(inspect())
            emit(
                {
                    "event": "metadata",
                    "status": "OBSERVED / C0_REVIEW_REQUIRED",
                    "input_validation": "SHA256_MATCH",
                    "history_gets": gets,
                    **metadata,
                    "model_posts": 0,
                    "cost_status": "UNSETTLED",
                    "automatic_reserve_release": False,
                    "runtime_authorized": False,
                }
            )
        # Provider/credential exception text must never reach the operator report.
        except (Exception, KeyboardInterrupt, asyncio.CancelledError):  # noqa: BLE001
            emit(
                {
                    "event": "stop",
                    "status": "STOP / UNKNOWN",
                    "history_gets": gets,
                    "model_posts": 0,
                    "cost_status": "UNSETTLED",
                    "automatic_reserve_release": False,
                    "runtime_authorized": False,
                }
            )
            print("REPORT_WRITTEN / STOP / NO_PAID_TRANSITION")
            return 2
    print("REPORT_WRITTEN / METADATA_ONLY / NO_PAID_TRANSITION")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@
    $ReadOnlyScript | .\.venv\Scripts\python.exe -
    $ReadExit = $LASTEXITCODE
    if (-not (Test-Path -LiteralPath $Report)) { throw "No receipt; return STOP to C0 without retry" }
    Write-Host "History receipt: $Report"
    if ($ReadExit -ne 0) { Write-Host "STOP: preserve receipt; do not retry" }
    Get-FileHash -LiteralPath $Report -Algorithm SHA256
    Get-Content -LiteralPath $Report -Encoding UTF8
}
```

Верни **полный `reports/m4-polza-gpt-quality-history-r1.jsonl`**, даже при STOP.
Ожидаемое успешное окончание: `METADATA_ONLY / NO_PAID_TRANSITION` — метаданные
получены, но расход и причина ещё требуют C0 review. Общий лимит45 секунд.
Не удалять/переименовывать отчёт ради повторного запуска; paid тест не повторять.

## Границы и текущий учёт

Source **ace29ce7d77564f8fecea84d4b7e734e6c8fbe56**, tree **8a716c528a917c8a77a853c226699ba4a47ccc2b**;
исходный report21904 bytes/21 events, SHA256 `b0d1cb8249b321792355a2b4d29e1a79ba6eae30847a5deee6fbafa36159017f`.
Команда читает только first5 history и detail точного ID; missing/duplicate ID,
невалидный HTTP/JSON или превышение bounds → STOP. Без pagination/polling/retry.
Каждый GET≤65536 bytes/15s. В report только выбранные metadata; raw request,
response, reasoning, account/key labels и /log не сохраняются. Сам исходный
report неизменен. Cost из history обозначен reported/UNSETTLED; автоматического
освобождения резервов, settlement или перехода к новой генерации нет.

| Показатель после GPT v2 | Значение |
|---|---:|
| Новые model POST / confirmed | 10 /0.05956584 RUB за9 known calls |
| Новый unknown / held | 1 /0.465109963 RUB |
| Shared confirmed / known POST | 0.23889134 RUB /40 |
| Shared unknown / held | 4 /7.585505548 RUB |
| Всего model attempts | 44 |
| Остаток общего150 с резервами | 142.175603112 RUB |

Это ledger capacity, не проверенный баланс Polza; reserve не списание, unknown
не charge0. Старые holds сохранены. Из25 scenarios только7 завершены, восьмой
technical STOP,17 NOT_RUN. Передача владельцу19, images20/21 и price22 ещё не
проверены; quality/runtime не приняты, C4 HOLD до metadata.

C0 проверил исходный report/accounting и4 controlled counter cases; точный
Python блок выше прошёл15 checks с MockTransport/audit запретом real network
и owner secret reads. Windows PowerShell самостоятельно C0 не запускался;
реальная metadata retrieval ещё NOT_RUN. Backend/guards не менялись.
PR39 Draft/headcd60, RED CI41009211185 и C0-M4-CI-OBSERVATION-01 остаются.
Main/VM/DB/Telegram/merge без изменений; full integration CI нужен до runtime.
