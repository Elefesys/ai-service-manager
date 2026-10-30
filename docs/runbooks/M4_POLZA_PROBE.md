# M4.2 — R2 остановлен на первом Gemini запросе

**Повторять R1/R2 не нужно. Разовый допуск R2 использован; новый paid запуск HOLD.**
Сохранить `reports/m4-polza-executable-eval-r1.jsonl` и
`reports/m4-polza-executable-eval-r2.jsonl` без изменений. Не удалять/переименовывать
отчёт ради повторного запуска. Ключ и `.env.m4-probe` остаются на прежнем ПК.

C0 прочитал полный переданный текст R2:33 events,84220 bytes. Встроенный R1,
порядок cases/reservations, summary и quality flags проверены offline по
source `cd60e5e16d8bcada53597d660a15f4d82640e956`. Это проверка содержания копии;
byte hash оригинального Windows R2 пока не подтверждён.

| Модель | Результат |
|---|---|
| GPT | 25 scenarios завершены,27 confirmed POST/2 READ. Есть неверный reply вместо handoff в no_send_claim19 и неподтверждённое обобщение о цене в unknown_price22. Модель целиком не принята |
| Gemini | Первый tool_current0 POST остановлен: SIGNATURE_INVALID,0 READ/0 final. Стоимость/usage/actual route UNKNOWN |
| DeepSeek | NOT_RUN,0 POST |

Подтверждённый общий расход **0.17509189 RUB**, включая helpers/R1/R2.
Для неизвестного Gemini charge удерживается резерв **3.464879664 RUB**;
остаток прежнего общего150 с этим резервом **146.360028446 RUB**. Это не
текущий баланс Polza и не обещание стоимости; нового бюджета150 нет.

**Дальше C4 готовит диагностику** по [текущей выдаче](../tasks/M4_HANDOFF.md).
Сначала будет отдельная команда только чтения history:0 model POST, до4 GET.
Она соберёт доступные metadata для C0; неоднозначное совпадение по времени/модели
не считается подтверждённой связью с утраченным R2 response ID. Если история
не раскрывает форму signature, C4 подготовит отдельный ограниченный план
одного Gemini POST для последующего C0 review. Автоматического запуска нет.
На ПК сейчас не требуется новая установка, изменение ключа или paid команда.

Новая процедура остаётся в существующем CLI. Completed GPT cases не повторяются;
общий R3/resume ещё не реализован и не разрешён. Все old flags/finals/charges
сохраняются, runtime_authorized=false. Подробные результаты и ограничения —
[receipt C0](../tasks/M4_HANDOFF.md), [решение IMPL-004](../decisions/IMPL-004-m4-pilot-ai.md).

PR39 остаётся Draft/headcd60; [CI41009211185](https://github.com/Elefesys/ai-service-manager/actions/runs/41009211185)
RED:10/11 jobs SUCCESS, M3 observer timeout, незавершённые foundation gates.
C0-M4-CI-OBSERVATION-01 остаётся до merge/runtime; повтор CI ради PASS не выполнялся.

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
