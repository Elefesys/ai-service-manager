# M4.2 — GPT quality R2 готов к source review C0

**Кандидат C4 — REVIEW; нового live допуска пока нет.** Отдельный режим
`--gpt-quality-r2` готов для оставшихся18 scenarios после проверки C0.
Новый `gpt_eval_history_v2` принимает строго положительный целый attemptsCount,
отдельно от client POST. Default adapter и прежние CLI modes сохраняются.

## Принятый результат

`m4-polza-gpt-quality-history-r1.jsonl`:1633 bytes/4 events,
SHA256 `bf09d2dba67de7fbbd1f9a88cde309ee0a135fc1df52ab0554f591beeb1fba24`.
2 history GET/0 model POST; exact generation gen_2227417601602097153.
List/detail: completed, OpenAI, usage694 input/118 output/812 total,
**reported cost0.00743079 RUB**, attemptsCount2. Это не второй POST нашего
runner и не доказательство маршрута каждой внутренней попытки.

Исходный GPT v2 report SHA256 `b0d1cb8249b321792355a2b4d29e1a79ba6eae30847a5deee6fbafa36159017f`
сохраняется:7 manual PASS/2 READ, case7 technical STOP,17 NOT_RUN.
Передача владельцу19, images20/21 и повтор price22 ещё не проверены.

Shared150 без изменения: **confirmed0.23889134 RUB/40 known client POST**,
**4 unknown/held7.585505548 RUB**, всего44 client POST,
remaining **142.175603112 RUB**. Reported amount неизвестного ранее call
сохранён отдельно; old hold0.465109963 не освобождён. Это ledger capacity,
не account balance. Новых history запросов ради settlement не требуется.

## Windows: доступная сейчас offline проверка

В PowerShell из корня checkout кандидата `c4/m4-2-gpt-quality-r2`, в прежнем
локальном environment с уже установленными frozen dependencies:

```powershell
$ErrorActionPreference = 'Stop'
uv run --frozen --offline python -m asm.ai.probe --plan --gpt-quality-r2
if ($LASTEXITCODE -ne 0) { throw 'OFFLINE_PLAN_FAILED' }
```

План не читает key и не делает HTTP. Существующий key/environment сохранить;
ключ не печатать и не переносить в команду. Ожидаются:

- `GPT_QUALITY_R2`, только `openai/gpt-6-luna`, selector `openai/flex`,
  provider-default; tools/tool_choice не объявлены, поскольку новых READ0.
- Original repeats7–24:18 scenarios/≤18 POST,2 images,≤36 history GET/1 catalog;
  retained7/READ2 отдельно. Prompt v2 и обе schema revisions v1 неизменны,
  images используют прежний `synthetic_shapes_v1/EVAL_ONLY`.
- 60s/case,1800s stage;32768/512 tokens,24576/32768 bytes/call;
  total token reservation599040; catalog4MiB/20s, history65536 bytes/15s на POST.
- Ceiling10 RUB в прежнем150; fixed prior40 known/4 unknown/44 client POST,
  confirmed0.23889134/held7.585505548. Maximum62 shared client POST.
  Fresh catalog должен подтвердить reserve **всех18 calls до первого POST**;
  offline `priced_reservation_rub=null` не является разрешением или ценой.

Профиль проверяет raw stepsCount в list/detail: missing/null → NOT_APPLICABLE,
строгий int1 → ONE_REPORTED. bool/float/string/0/negative/>1 — STOP. Любой
nonnull serverTools/parent запрещён; остальные identity/metering/limit checks
сохраняются. Закрытые `history_profile.provider_attempts/detail_steps/list_steps`
содержат только проверенные metadata; null означает, что проверка не достигнута.
Число попыток не умножает ledger charge/reservation, не доказывает стоимость или
маршрут каждой попытки. Flex variant остаётся NOT_OBSERVED.

После source review C0 опубликует один executable paid block с exact source SHA,
соответствующим ref `C0-M4.2-GPT-QUALITY-R2:<source40>:<suffix>` и explicit amount≤10.
Сейчас такого допуска/paid block нет. Нового подтверждения общего150 не требуется.
Будущий output — exclusive `reports/m4-polza-gpt-quality-r2.jsonl`; existing output
останавливает запуск до key/HTTP. No retry/fallback/polling/arbitrary resume.
Reservation flush предшествует HTTP; новый unknown сохраняет полный резерв.
Metadata receipt R1 не освобождает старый GPT hold0.465109963.

18 technical completions означают только HUMAN_REVIEW_REQUIRED/manual PENDING.
Любой technical failure останавливает этап; finals/flags сохраняются. C0 оценит
качество по R1+R2, включая no_send_claim19/unknown_price22, отдельно от технического
статуса. Не считать18 новых finals доказательством25 новых successful cases.

Старые paid/history команды использованы. Все отчёты сохранить; не удалять и
не переименовывать их для повторного запуска. Нового live допуска сейчас нет.
Локально916 targeted PASS, Ruff/format4/mypy71 и9 offline CLI variants;
старые8 plans побайтово совпали с base. Это CONTROLLED evidence: настоящих Polza
POST/catalog/history GET0, owner key reads0. Windows/live/full CI NOT_RUN.

[Точный scope и проверки C4](../tasks/M4_HANDOFF.md) ·
[Решение C0](../decisions/IMPL-004-m4-pilot-ai.md).
PR39 Draft/headcd60, CI41009211185 RED и C0-M4-CI-OBSERVATION-01 открыты.
Gemini/DeepSeek compatibility DEFERRED; runtime/Telegram/merge не включаются.
