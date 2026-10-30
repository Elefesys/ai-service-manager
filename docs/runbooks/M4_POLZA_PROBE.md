# M4.2 — GPT quality v2: кандидат для source review C0

**Команду DeepSeek tool roundtrip больше не запускать.** Владелец вернул полный
отчёт; допуск OWNER_ROUNDTRIP_R1_1RUB использован. Сейчас новых команд с ключом
или платных запусков нет. C4 подготовил отдельный `--gpt-quality-r1` и
conversation_v2 по [решению C0](../decisions/IMPL-004-m4-pilot-ai.md).
[Задача и receipt](../tasks/M4_HANDOFF.md); статус REVIEW — в [CURRENT](../TASK_REGISTER.md).

## Что произошло

`reports/m4-polza-deepseek-tool-compat-r1.jsonl`:7094 bytes/5 JSONL events,
SHA256 `1b7addea429f9e53f1e5d0086d1cdf1f648c138747013efe25c4c2ff037cd1b3`.
Source **5885df1b0ba04378e8af6f2089d2fc86be6c22e3**.

Сделаны1 catalog GET и1 model POST. В ответе DeepSeek указан tool_calls, но
адаптер отклонил форму ответа: ADAPTER_ERROR / INVALID_PROVIDER_RESPONSE.
История не читалась, synthetic READ и второй POST не выполнялись; final=null.
Generation `gen_2227402879917887489`, reported reasoning_tokens0. Конкретное
отказавшее поле не сохранено; несколько разных ошибок имеют такой же итог.
Нельзя объявлять причиной content/id/arguments или делать вывод обо всей модели.

Usage и стоимость нового запроса UNKNOWN, история не подтвердила provider family.
Запрошенный wafer/us не равен наблюдению этого маршрута. Пустые quality_flags
при отсутствии final не означают успешную проверку качества.

## Общий учёт после попытки

| Показатель | Значение |
|---|---:|
| Общий бюджет | 150 RUB |
| Подтверждённый расход / known POST | **0.17932550 RUB /31** |
| Unknown POST | **3**: 2 Gemini +1 DeepSeek |
| Gemini held | **6.929759328 RUB** |
| Новый DeepSeek held | **0.190636257 RUB** |
| Всего held | **7.120395585 RUB** |
| Всего model attempts | **34** |
| Confirmed + held | **7.299721085 RUB** |
| Остаток с резервами | **142.700278915 RUB** |

Это ledger, не проверка баланса аккаунта. Резерв не равен списанию, confirmed0
нового stage не означает бесплатный запрос. Все3 неизвестных расхода удержаны.
Неиспользованный второй call не является новым unknown. Ключ, окружение и
старые файлы отчётов сохраняются; переустановка не нужна.

## Дальше — GPT quality revision

Для первого пилота продолжаем с GPT как кандидатом: v1 дал25 finals/27 POST/2 READ,
включая2 картинки. Остались неверный reply вместо handoff на просьбу написать
владельцу и неподтверждённое правило о зависимости цены от вида ремонта.
Gemini/DeepSeek compatibility отложена, причины их остановок сохранены.
Полное сравнение75 scenarios не завершено; модель для runtime пока не выбрана.

C4 подготовил conversation_v2 и отдельную полную GPT-only проверку по тем же
fixtures. Explicit owner contact требует proposed handoff, без утверждений об
отправке или уведомлении; неизвестные business facts/rules нельзя дополнять
типичными предположениями. Известные факты используются, обычные уточнения
разрешены. Prompt не содержит case IDs, тестовых ответов/адресов, обязательных
regex слов или mutation tools.

Prompt v2 SHA256:
`b420be44a7e4210de1151e5b0604b0fa9a08c19b1bfbedb8147f2a9b38455956`.
v1 сохранён побайтово, SHA256
`1ba9d9638b601d5890c6f1acc038d670cd5a8360105816ad7fea5298d458cee0`.
Gateway допускает только v1/v2 и выбирает один из двух фиксированных bundled
файлов. Result DTO/schema и strict conversation_result_envelope_v1 не меняются.
Старые modes продолжают v1; новая версия не переоценивает их saved finals.

| Граница нового режима | Значение |
|---|---|
| Route / profile | Только openai/gpt-6-luna, selector openai/flex, provider-default; прежний auto-tools |
| Schedule | Все прежние25 scenarios в прежнем порядке,3 critical repeats,2 READ,2 images |
| Prompt / image | Text/tool conversation_v2; images synthetic_shapes_v1/EVAL_ONLY, отдельные revisions в plan/report |
| Максимумы HTTP | 27 POST /54 history GET /1 catalog GET; Gemini/DeepSeek POST0 |
| Tokens / bytes на call | Input/output32768/512;24576/32768 wire bytes |
| Время | 60s на case вместе с READ roundtrip;1800s на весь stage |
| Catalog / history | 4MiB/20s;65536 bytes на GET и15s verification на POST |
| Stage ceiling | 15 RUB из прежнего150; fresh reservation всех27 calls до первого POST |
| Prior / shared | 34 attempts,31 known/3 unknown; максимум61 attempts, все old holds сохраняются |

Canonical fixture SHA256
`7abd25f1e1f08e51eacc3a68975e6099c942d33fad37376366dfdef6c7e025b2`
не менялся. Fresh route/capabilities/rates/fees проверяются прежним adapter;
missing/unknown/несовместимое значение или превышение whole-stage reserve —
STOP до POST. Запрошенный flex не означает observed variant; history family,
identity, usage/cost проверяются отдельно. Parser acceptance не расширен.

Новый `reports/m4-polza-gpt-quality-r1.jsonl` создаётся exclusively до чтения
ключа. Reservations flush до HTTP, без retry/fallback/polling/imports/resume.
Обрабатываемый STOP сохраняет terminal summary; потерянный результат после
reservation остаётся UNKNOWN. Не удалять/не переименовывать report ради повтора.

После25 технически завершённых scenarios статус `HUMAN_REVIEW_REQUIRED`, exit0;
это не автоматический quality PASS. Quality flags и каждый final сохраняются,
manual assessment остаётся PENDING даже без flags. Technical error останавливает
stage, `FAILED_OR_INCOMPLETE`, exit2. selected_model=null/runtime_authorized=false.
Старые no_send_claim19 QUALITY_FAIL и unknown_price22 QUALITY_NOTE сохраняются;
будущий live receipt и ручная оценка покажут, улучшилось ли качество v2.

**Это задача на подготовку, не live допуск.** После source review C0 опубликует
одну готовую Windows команду с новым exact SHA/ref/report. Общий150 повторно
не согласовывается, ключ не передаётся C0/C4.

## Windows: только offline plan

Существующие Python/uv/dependencies и локальный `.env.m4-probe` сохранить.
План не читает ключ, не создаёт report и не делает catalog/history/model HTTP.
Из корня checkout принятого для review кандидата, с уже установленными locked
dependencies, можно выполнить:

```powershell
$ErrorActionPreference = 'Stop'
uv run --frozen --offline python -m asm.ai.probe --plan --gpt-quality-r1
if ($LASTEXITCODE -ne 0) { throw 'OFFLINE_PLAN_FAILED' }
```

Ожидается `GPT_QUALITY_R1`, `PLAN_ONLY / PAID_NOT_AUTHORIZED`, v2/hash выше;
priced_reservation_rub=null до fresh catalog,25 scenarios/27 calls/2 reads/2 images,
ceiling15, prior0.17932550 + held7.120395585, remaining142.700278915.
Семь прежних offline-plan invocations сохранили исходный JSON. Это проверка
плана/совместимости кода, не новый допуск для consumed modes.

**Executable live блока здесь нет.** После review C0 должен закрепить полный
candidate SHA/tree и отдельный ref
`C0-M4.2-GPT-QUALITY-R1:<exact-source>:<C0_SUFFIX>`, ceiling15 и новый report.
Будущая Windows команда проверит clean exact source/tree и отсутствие report,
использует прежний локальный key-файл и запустит один stage. CLI связывает
source/ref, но не удостоверяет полномочия автора строки approval; использовать
только опубликованную C0 команду. Старые refs/команды не подходят.

При будущем любом исходе сохранить полный JSONL и передать C0 с SHA256.
Не публиковать owner report, ключ, raw responses/reasoning или account metadata в Git.

## CONTROLLED evidence C4

799 targeted tests PASS (711 прежних +88 новых); Ruff/format7 и mypy71 PASS.
8 actual offline CLI invocations PASS, первые7 совпали с base. Wheel собран,
обе bundled prompt версии совпали побайтово с исходниками. Точные команды —
в [receipt C4](../tasks/M4_HANDOFF.md). Full CI/Windows live не запускались.

Полный MockTransport путь наблюдает v2 system wire/config/plan/report,
прежний auto READ roundtrip, обе картинки и history. CONTROLLED catalog rates
8/45/0 дают reserve0.285184000 на call,7.699968000 на27 calls. Подставные
charges27×0.001 =0.027 RUB; shared known58/confirmed0.20632550, unknown3,
held7.120395585,61 attempts, remaining142.673278915. Это арифметическая
проверка, не расход владельца и не подтверждённый тариф аккаунта.

Проверены early/follow-up и поздние STOP (image и последний case), unknown
revision, fresh catalog/whole-stage ceiling, exact source/ref/budget,
exclusivity до key, отсутствующий case после reservation, отмена/таймаут,
identity/family/usage/cost. First charge0.001 при неподтверждённом follow-up
сохраняется; new unknown held0.285184000 добавляется к old7.120395585.
CONTROLLED ответы с теми же quality проблемами остаются в отчёте: OUTCOME
для reply вместо handoff, а неподтверждённое ценовое правило может не дать
regex flag и всё равно требует manual review. Tests не доказывают исправление
сохранённых v1 findings или hosted GPT quality.

Audit guard запрещал реальные sockets и чтение owner .env; pytest использует
только synthetic secrets. В этой выдаче Polza API POST/catalog/history GET0,
owner key reads0; исходные owner reports не импортировались.

## Проверка C0 и сохранённые ограничения

C0 воспроизвёл hash/source/ref/plan/caps/reservation и все поля summary на exact
source.8 CONTROLLED checks:7 разных shapes дают generic отказ и0 READ/follow-up;
positive даёт2 POST/1 READ. MockTransport, запрет sockets/owner .env reads;
real HTTP/key reads0. C0 не запускал Windows и не менял код;711 targeted/full CI
повторно не запускались. Это отдельные controlled проверки, не новая hosted проба.

PR39 Draft/headcd60, CI41009211185 RED и C0-M4-CI-OBSERVATION-01 не закрыты;
full CI интеграционного кандидата нужен до merge/runtime. Telegram bridge и
runtime ещё не готовы, main/VM/DB/Telegram/merge не менялись.

## Использованные инструкции — история, без права повтора

- [Tool compatibility source review и использованная Windows команда](https://github.com/Elefesys/ai-service-manager/blob/dc16ed86fe9b030c317873d3d4b0f5dc3a583c43/docs/runbooks/M4_POLZA_PROBE.md)
- [Исходный DeepSeek auto eval и отдельная compatibility задача](https://github.com/Elefesys/ai-service-manager/blob/7e0870d8492d36a00ffac894e44b787c5af8ca47/docs/tasks/M4_HANDOFF.md)
- Все owner reports сохраняются отдельно; их raw contents не публикуются в Git.
