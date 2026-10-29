# M4.2 — synthetic Polza probe

Статус C0 OBSERVATION-R1: **GPT helper READ_ROUNDTRIP_OK / full75 NOT RUN**.
Владелец уже выделил общий150 RUB и выполнил один одиночный POST и успешный
двухшаговый synthetic READ test. Подтверждённый расход **0.01269785 RUB**;
арифметический остаток общего бюджета **149.98730215 RUB**, не новый150.
Ниже — процедура исправленного основного CLI, candidate **REVIEW** для C0.
Команда полного сравнения подготовлена, но три фактических route reviews ещё
не собраны; конкретные открытые поля перечислены ниже. Повтор успешного helper не нужен.
Body provider оказался отсутствующим, history family — OpenAI; выбранный
openai/flex остаётся request pin. Price-only catalog drift требует fresh repricing.
Точный receipt и текущая выдача — [M4_HANDOFF](../tasks/M4_HANDOFF.md).
Никаких клиентских данных, Telegram, БД, S3 или runtime activation.
Accepted deployment остаётся LOCAL / asm_local.

C0 подготовил общий ceiling150 RUB после сообщения владельца о готовности
увеличить бюджет. Это потолок на все три модели вместе, не автоматическое
разрешение потратить150. Меньший explicit approved amount сохраняет силу.
Баланс Polza и лимит dedicated key проверяются отдельно; пополнение баланса
само по себе не меняет лимит ключа и не подтверждает совместимость маршрута.

## Offline — можно сейчас

Из корня checkout, Python 3.13 и существующий frozen lock:

```sh
uv sync --frozen
.venv/bin/python -m asm.ai.probe --plan
.venv/bin/pytest -q tests/test_m4_polza.py tests/test_m4_probe.py tests/test_m4_gateway.py tests/test_m4_gateway_failures.py
.venv/bin/ruff check backend/src/asm/ai/polza.py backend/src/asm/ai/settings.py backend/src/asm/ai/probe.py tests/test_m4_polza.py tests/test_m4_probe.py
.venv/bin/ruff format --check backend/src/asm/ai/polza.py backend/src/asm/ai/settings.py backend/src/asm/ai/probe.py tests/test_m4_polza.py tests/test_m4_probe.py
.venv/bin/mypy
git diff --check
```

Windows x64: после review C0 заменить `C0_ACCEPTED_FULL_SHA` полным SHA принятого
кандидата и выполнить из корня чистого checkout в обычном PowerShell. Нужны Git,
существующее frozen окружение CPython3.13. Новый ввод ключа и повторная установка
зависимостей не нужны: lock/manifests этого candidate не менялись.

```powershell
& {
    $ErrorActionPreference = "Stop"
    $Candidate = "C0_ACCEPTED_FULL_SHA"
    if ($Candidate -cnotmatch '^[0-9a-f]{40}$') { throw "Exact accepted SHA required" }
    $Dirty = git status --porcelain
    if ($LASTEXITCODE -ne 0 -or $Dirty) { throw "Clean checkout required" }
    git fetch origin $Candidate
    if ($LASTEXITCODE -ne 0) { throw "Candidate fetch failed" }
    git switch --detach $Candidate
    if ($LASTEXITCODE -ne 0) { throw "Candidate checkout failed" }
    $Actual = git rev-parse HEAD
    if ($LASTEXITCODE -ne 0 -or $Actual -cne $Candidate) { throw "Source SHA mismatch" }
    if (-not (Test-Path .\.venv\Scripts\python.exe)) { throw "Existing probe environment not found" }
    .\.venv\Scripts\python.exe -m asm.ai.probe --plan
    if ($LASTEXITCODE -ne 0) { throw "Offline plan failed" }
}
```

В исходном head4f86e7f для cffi2.0.0 и argon2-cffi-bindings25.1.0 lock содержал
только Linux wheels: Windows пыталась собирать C extension и требовала MSVC.
M4.2-PROBE-WINDOWS-LOCK-R1 добавляет ровно два Windows x64 wheel URL/SHA-256 из
[cffi PyPI](https://pypi.org/project/cffi/2.0.0/#files) и
[argon2 bindings PyPI](https://pypi.org/project/argon2-cffi-bindings/25.1.0/#files).
Версии и dependency graph сохранены. Не обходить frozen lock через upgrade,
удаление зависимостей или установку компиляторов. Первичная frozen установка уже
подтверждена владельцем; при новом checkout её команда из прежней выдачи —
`uv sync --frozen --python 3.13 --no-build-package cffi --no-build-package argon2-cffi-bindings`.
Обновление SHA выше запускает только offline plan.

Без flags выполняется тот же offline plan. Он не читает secret и не создаёт HTTP
client. Fixtures фиксируют ожидания до вызовов: 20 русских text cases, включая два
READ round trips, плюс три critical repeats и две заранее созданные PNG фигуры
128×128 на каждого кандидата. PNG bytes и SHA-256 находятся в JSON fixture.
Image calls — только отдельная EVAL_ONLY проверка, не расширение text Gateway.

| Предел | Значение для трёх кандидатов суммарно |
|---|---|
| Модели | ровно в этом порядке: `openai/gpt-6-luna`, `google/gemini-3.8-flash`, `deepseek/deepseek-v4.1-flash-1017` |
| Сценарии | 25 на модель, 75 всего |
| Model HTTP | 27 на модель, максимум и жёсткий потолок 81; retry/repair calls отсутствуют |
| Catalog HTTP | один GET на preflight; один повторный GET на live admission |
| History HTTP | максимум 2 GET на model POST / 162 на весь этап; по 65536 bytes, суммарно до15s на проверку одного ответа внутри case/run deadlines |
| READ | максимум 6, только локальные fixture facts |
| Вход / выход | 32768 / 512 tokens на call |
| Общий token reservation | максимум 2695680 tokens |
| Wire input / response | 24576 / 32768 bytes на call |
| Сценарий / весь live запуск | 60 / 1800 секунд, включая каталог |
| Бюджет | общий150 RUB; prior0.01269785, новый этап не выше149.98730215 RUB и меньшего explicit approved amount |
| Общие model POST | prior3 + не более81 новых = максимум84 |

Plan без account review печатает `priced_reservation_rub: null`, UNKNOWN.
Публичный ценник из исследования не заменяет актуальный account tariff.
Добавление DeepSeek согласовано C0 в M4.2-PROBE-THIRD-CANDIDATE-R1; это finite
allowlist, не auto-selection или fallback. Набор fixtures не сокращён.

## Существующий отдельный ключ

Владелец уже подтвердил dedicated key limit150/reset never и owner-only Windows
ACL. Для этой выдачи использовать имеющийся `.env.m4-probe`; повторно создавать
или вводить ключ не требуется. Следующая памятка относится к первичному созданию.

В консоли Polza создать отдельный ключ для M4, выключить unofficial providers;
поставить расходный лимит не выше согласованного бюджета, если доступен. Не
переиспользовать Telegram key и не менять `.env`, `.env.telegram` или activation
intent. Секрет не передавать в чат, argv, shell history, Git, CI или report.

Linux: оператор создаёт **новый** `.env.m4-probe`, owned by current UID, mode0600,
без symlink. Эта команда запрашивает значение без echo, не содержит его в history
и не перезаписывает существующий файл:

```sh
.venv/bin/python - <<'PY'
import getpass, os
value = getpass.getpass('Dedicated Polza key (hidden): ')
if not value or any(c.isspace() or not c.isprintable() for c in value):
    raise SystemExit('Invalid key format')
fd = os.open('.env.m4-probe', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w', encoding='utf-8') as out:
    out.write('M4_PROBE_API_KEY=' + value + '\n')
PY
git check-ignore .env.m4-probe
```

Формат — одна строка `M4_PROBE_API_KEY=<value>`, без кавычек. Значение загружается
в SecretStr; ambient env не заменяет содержимое файла. Ошибки чтения не содержат
самого значения. На Windows **до записи значения** создать пустой новый файл,
отключить наследование ACL, оставить доступ только оператору (и обязательным
системным principals по политике хоста); проверить `icacls .env.m4-probe`.
Ввести строку через локальный редактор без sync/backups. Пробник не проверяет
Windows ACL автоматически: до подтверждения ACL запуск закрыт. Python там —
`.venv\Scripts\python.exe`; ключ также запрещён в PowerShell command line/history.

## Catalog preflight и отдельный review аккаунта/маршрутов

После отдельного допуска на ключ/preflight; `C0-APPROVAL-ID` заменить ссылкой/ID
реального решения, не выдумывать. Команда делает один GET, без генераций:

```sh
.venv/bin/python -m asm.ai.probe --preflight --approval-ref C0-APPROVAL-ID --report .env.m4-probe.catalog.json
```

Один GET получает **публичный** каталог сразу для всех трёх кандидатов. Даже с
Authorization header успешный GET не доказывает валидность ключа, whitelist,
индивидуальный тариф или доступность генерации. В новом отчёте это явно
`source: PUBLIC_CATALOG`, `account_authorization: NOT_CHECKED`,
`account_tariff: NOT_ESTABLISHED_BY_CATALOG`. Прежний двухмодельный preflight не
использовать. Из отчёта reviewer создаёт `.env.m4-probe.review.json`:
JSON-массив из **трёх**
RouteReview в порядке моделей выше. Для каждого копируются `catalog_entry`,
`catalog_sha256` и `checked_at`; добавляются поля ниже. Это trusted configuration,
не вывод модели. Пустое поле/неизвестный факт означает BLOCKED; заполнять текстом
«supported» ради обхода допуска нельзя. Review действителен 24 часа от исходного
`checked_at`; live один раз получает публичный каталог и проверяет прежнюю unique
official route, model/modalities, всю non-price provider configuration и fee schema.
Числовые цены могут измениться; порядок пересчёта ниже. Не обновлять время review:
после 24 часов нужен новый разрешённый GET и review. Это не снимает отдельную
проверку key restrictions и индивидуального тарифа.
Неполный, дублированный, переставленный либо другой набор reviews отклоняется.
Для DeepSeek нужны те же route/schema/tools/image/token/billing evidence;
наличие ID в whitelist ключа или публичной карточке не подтверждает capability.

| Поле | Что должен подтвердить reviewer |
|---|---|
| `model` | точный разрешённый ID, без замены |
| `provider_name` | точное **единственное** имя из `providers`, для `provider.only`; duplicate name блокируется |
| `response_provider` | документированное соответствующее значение response `provider`; это `Route.upstream` |
| `history` | необязательный объект `provider` + `evidence` для разрешённой C0 проверки отсутствующего body provider; точный family label и источник его соответствия маршруту, без обещания variant |
| `route_evidence` | источник/дата/вывод для name→response ID, official upstream, key restrictions |
| `schema_tools_evidence` | native strict **точная** conversation_result_envelope_v1 с неизменённым conversation_result_v1 внутри, strict READ tools и совместное использование |
| `token_bound_evidence` | основание указанной ниже границы для этого tokenizer/wire protocol |
| `billing_bound_evidence` | актуальные ставки/единицы, применимые fees, отсутствие неизвестного начисления сверх резерва |
| `image_bound_evidence` | поддержка PNG input и token/billing bound для данных двух изображений |
| `output_cap_parameter` | ровно `max_tokens` либо `max_completion_tokens`, явно поддерживаемый выбранным provider |
| `output_cap_includes_reasoning` | только `true`, если подтверждён общий предел всей платной генерации |
| `output_cap_evidence` | источник/дата/вывод: выбранный параметр ограничивает completion **вместе** с paid reasoning; числовой catalog limit сам по себе этого не доказывает |
| `inactive_fee_evidence` | объект `имя fee: evidence` только для присутствующих в pricing `audio_per_million`, `input_audio_cache_per_million`, `web_search_per_thousand`; отдельное подтверждение единиц и неприменимости каждого fee к этому payload |

Каждое evidence — короткий текст (20–2000 символов) со ссылкой и проверенным
выводом. Это обязательный review, не автоматическая сертификация текстового поля.
Не копировать строки `OFFLINE FIXTURE ONLY` из тестов: они не являются evidence.
Если нет источника, вернуть C0 точный неизвестный факт. Нет catalog auto-selection.

Выбранный provider должен явно сообщать `is_unofficial: false`, supported для
`tools`, `json_schema_strict`, `input_image`, необходимые supported_parameters и
числовые token limits. `top_provider` не заменяет выбранную запись. Дублированные
имена не объединяются и первая запись не выбирается. Другой уникальный official
route возможен только по ручному review; response provider ID не угадывается.

`verified_at: null` — только заявление каталога, timestamp — сообщённая каталогом
проверка. Ни то ни другое не является нашим live evidence совместимости целого
payload; plan сохраняет эти различия в `reviewed_routes` вместе с review hash.

Разрешённая C0 wire-обёртка — root object с единственным required полем `result`
и `additionalProperties: false`. Внутри неизменённый canonical union; `$defs`
перенесены на root без изменения `$ref`. Адаптер проверяет envelope и передаёт
его `result` прежнему DTO validator Gateway. Отчёт различает canonical
`schema_revision: conversation_result_v1` и wire
`wire_schema_revision: conversation_result_envelope_v1`; prompt не изменён.
Offline tests покрывают reply/handoff/no_reply, READ и images. Пользовательский
GPT helper уже подтвердил native strict schema + READ→final для одного text case;
он не является live acceptance штатного Gateway, images или остальных моделей.

## Наблюдение route через history

Если поле body `provider` присутствует, оно обязано точно совпасть с reviewed
`response_provider`; null/неверное значение/неправильный тип — STOP, history не
подменяет этот ответ. Если поля нет, необходим `history` review и response ID
формата `gen_` + 1–64 цифры. Произвольные URL, поиск по похожим usage/стоимости,
substitution requested provider и polling не используются.

По [официальному list/detail контракту](https://github.com/polza-ai/docs/blob/main/api-reference/history/generations.mdx)
адаптер выполняет один GET последних5 chat generations, затем один detail GET
строго по ID этого ответа. List model должен совпасть с полным model ID либо его
документированной slug-частью после `/`; сравнение family регистрозависимое.
ID должен быть единственным, оба статуса completed, family и usage/cost совпадают;
detail также обязан подтвердить finishReason, attemptsCount=1, sync chat_completions
и отсутствие отмены/server-tool steps. Неизвестные данные — STOP до READ/следующего
POST. Total/reasoning counters, если присутствуют, также сверяются. Нет retry,
redirect, pagination или `/log`. Время двух GET вместе ограничено15s и оставшимся
временем исходного вызова; image EVAL использует тот же путь.

В case report отдельно записываются `requested_provider`, `observed_body_provider`,
`provider_field_state`, `history_family`, `route_evidence_source` (`BODY` либо
`HISTORY_LIST_DETAIL`), `generation_id`, `history_gets`, `route_variant: NOT_OBSERVED`.
Ожидаемый Route.upstream не выдаётся за observed endpoint. В принятом GPT receipt
family — `OpenAI`, variant flex остаётся только request pin. Raw history, account/key
поля и chain-of-thought не сохраняются. Недоступность/задержка history завершает
этот этап с UNKNOWN/no automatic retry; reserved amount не возвращается.

Официальные источники, сверенные при подготовке 2026-10-29:

- [GET Models reference](https://polza.ai/docs/api-reference/models/list): `include_providers=true&include_capabilities=true`; статусы возможностей могут быть unknown.
- [Models guide](https://polza.ai/docs/gaidy/models): RUB, явно именованные per-million и per-request поля. Reference также показывает альтернативные per-token поля: код не угадывает единицы.
- [Provider selection](https://polza.ai/docs/gaidy/provider-selection): only/fallback и различие request name / returned provider.
- [Unofficial providers](https://polza.ai/docs/gaidy/unofficial-providers): restriction ключа и `is_unofficial`.
- [Chat](https://polza.ai/docs/gaidy/chat-completions), [tools](https://polza.ai/docs/gaidy/tool-calling), [schema](https://polza.ai/docs/gaidy/structured-output), [usage](https://polza.ai/docs/osobennosti/usage): wire mapping, finish reasons, `cost_rub` / `cost` в RUB.
- [Reasoning](https://polza.ai/docs/osobennosti/reasoning-tokens): paid output и provider defaults; наличие alias не доказывает общий cap для любого route.
- [Web search](https://polza.ai/docs/gaidy/web-search): способы активации и условный search fee.
- [OpenAI schema subset](https://developers.openai.com/api/docs/guides/structured-outputs): root object, nested anyOf и `$defs`/`$ref`; это не доказательство совместимости всех Polza routes.

## Тарификация и token bound

Локальная оценка: **число UTF-8 bytes полного serialized body + 4096 tokens**.
Включены messages, READ definitions, native schema, tool exchanges и protocol
поля. Это не точный tokenizer и не универсальное доказательство для любой
модели. Допуск требует подтверждения, что tokenizer не выдаёт больше одного
token на byte и скрытое framing/schema преобразование (для PNG также image tokens)
укладывается в запас 4096. Если такой границы для маршрута нет — paid STOP;
увеличивать лимит или называть эвристику гарантией нельзя. После каждого ответа
usage сравнивается с границей; неизвестный usage не даёт PASS.

После единственного admission catalog GET, **до первого model POST**, пересчитывается
полный резерв27 calls для каждой из трёх моделей — сумма всех81 calls. Он должен
помещаться в149.98730215 RUB и explicit `--approved-rub`; prior уже потрачен.
Бюджет не выделяется заново каждой модели. Цена call:
`(32768 * input_rate + 512 * output_rate) / 1000000 + request_rate` с округлением
вверх до 1e-9 RUB. Input складывает prompt/image/cache-read/cache-write ставки;
output складывает completion/reasoning; request складывает per_request и
request_per_thousand/1000. Это намеренно консервативно, без cache discounts.
Reviewer подтверждает, что отсутствующие optional fees неприменимы/включены и
**выбранный** cap включает всю платную reasoning-генерацию. Отправляется только
один alias; supported_parameters и числовой `max_completion_tokens >= 512`
проверяются независимо. Отдельно заявленные reasoning tokens должны быть
подмножеством usage completion_tokens, иначе STOP без повторного вызова.
Неизвестные
валюта, единицы, tiers, fee objects или дополнительные ставки останавливают план.

Три известных условных audio/search fees требуют `inactive_fee_evidence` даже
при нулевой ставке. До HTTP проверяется конечная форма text/PNG/function payload:
audio/modalities, plugins, web_search_options, built-in search tools, лишние поля
и второй token-cap alias запрещены. Unexpected audio/server-tool usage — STOP.
Это не разрешение игнорировать неизвестные fees, даже null/zero; cache ставки
остаются слагаемыми. Для `input_audio_cache_per_million` в сверенных официальных
источниках пока не найден достаточный контракт единиц/применимости: фактический
review этого fee остаётся UNKNOWN, его название не является доказательством.

Price-only drift допускается без переписывания ручного review: прежние source
snapshot/hash/checked_at остаются в файле и `reviewed_routes`. Для исполнения
создаются отдельные views со свежими ценами и прежним временем review; истечение
24h всё ещё останавливает запуск. Состав fees/currency, null↔number, route,
capabilities, reasoning settings, parameters и прочая non-price configuration
меняться не могут. Изменения других, не выбранных providers не влияют на route.

`catalog_repricing` сохраняет old/new entry fingerprints, source review hash/date,
non-price provider hash, old/new pricing, фактические additive rates и новый
резерв. `plan.pricing_catalogs`, `max_price`, Gateway и ledger используют одни
fresh prices. Overbudget останавливается до POST; валидный расчёт сохраняется в
receipt даже при STOP. Публичные цены по-прежнему не доказывают account tariff.

<a id="snapshot-2026-10-29-оставшиеся-блокеры"></a>

### Исторический snapshot CATALOG-R1

Разобраны все 58 записей исходного snapshot с
`checked_at=2026-10-29T10:43:36.518349+00:00`, SHA256
`ac671d10d528ff8c8458f9fad5dd853651c74b29a7763c20e740e2539ae5d02f`.
Проверки групп независимы: ранняя ошибка больше не считается полным диагнозом.
У GPT два `openai`, у DeepSeek два `deepseek`; max_tokens-only — 4/7/42 записей
соответственно. Все 7 Gemini требуют reasoning и содержат три условных fees;
ещё 7 GPT содержат search fee. Strict rejected у 5 DeepSeek entries: оба
`deepseek`, `baseten`, `alibaba`, `novita/fp8`; `baseten` и `mistral/fp8` также
не имеют `response_format`. У одной direct DeepSeek записи нет input_image.
У 7/7/42 записей соответственно image/tools заявлены без verified_at.

Ни одного trusted review для реального запуска в этой выдаче не создано.
Отдельный расчёт Decimal по публичным ставкам и прежней консервативной формуле
показывает **условный арифметический минимум**, если позже подтвердятся все
route/cap/billing evidence и исключения fees. Среди уникальных official записей
с нужными declared capabilities/parameters и numeric limits:

| Модель / арифметический минимум route | Резерв одного call, RUB | Все 27 calls, RUB |
|---|---:|---:|
| GPT / `openai/flex` | 0.464071642 | 12.529934334 |
| Gemini / `google-ai-studio/flex` (равен `google-vertex/global/flex`) | 3.313802006 | 89.472654162 |
| DeepSeek / `wafer/us` | 0.190210677 | 5.135688279 |
| **Итого 81 call** | | **107.138276775** |

Это историческая условная арифметика, **не текущий plan OBSERVATION-R1**. Уже в
R2 GPT цены изменились; reserve0.930219926 относился только к двум calls helper.
Без фактических reviews `--plan` остаётся null/UNKNOWN. Актуальные81 calls будут
пересчитаны по свежему admission GET; старый107.138276775 не переносится в ledger.

### Открытые поля для C0 перед полным сравнением

Сверены официальные источники2026-10-29; реальные RouteReview не создавались.
Нужен один проверенный набор трёх routes, без выдуманных строк evidence.

| Поле / кандидат | Источник и уже установленный факт | Недостающий факт |
|---|---|---|
| `provider_name`, `response_provider`, `history.provider/evidence` / Gemini, DeepSeek | [Polza routing](https://github.com/polza-ai/docs/blob/main/gaidy/provider-selection.mdx), [history](https://github.com/polza-ai/docs/blob/main/api-reference/history/generations.mdx); unique selector и family — разные поля | Выбранный unique official route и проверенное соответствие body/history family; GPT OpenAI не переносится на эти модели |
| `output_cap_evidence` / Gemini, DeepSeek | [Gemini thinking](https://ai.google.dev/gemini-api/docs/generate-content/thinking) включает thoughts в native max_output_tokens; [DeepSeek API](https://api-docs.deepseek.com/api/create-chat-completion/) описывает native max_tokens | Подтвердить mapping одного Polza alias и aggregate usage для **выбранного** route; direct API contract не удостоверяет любой hosted variant |
| `schema_tools_evidence` / Gemini, DeepSeek | Polza catalog даёт declarations; [DeepSeek thinking/tools](https://api-docs.deepseek.com/guides/thinking_mode/) требует reasoning_content в последующих tool turns в thinking mode | Подтвердить штатный text/function wire без скрытого обязательного continuation payload на конкретном route. Вывод: direct DeepSeek thinking docs недостаточны для нашего пути, который не возвращает reasoning; это риск контракта, не наблюдённый HTTP400 |
| `inactive_fee_evidence` / Gemini и routes с search fee | Polza [models](https://github.com/polza-ai/docs/blob/main/gaidy/models.mdx)/[search](https://github.com/polza-ai/docs/blob/main/gaidy/web-search.mdx) и существующий snapshot | Единицы/неприменимость каждого исключения, особенно input_audio_cache_per_million; неизвестный контракт не заменяется именем поля |
| `token_bound_evidence`, `image_bound_evidence` / все3 | [DeepSeek Vision](https://api-docs.deepseek.com/guides/vision/) описывает PNG и1024 tokens/image для своего deepseek-flash; GPT receipt покрывает только text/READ | Применимость к точному Polza model/provider и двум128×128 PNG, общий bound serialized bytes+4096; direct model и каталог не доказывают bound всех upstream |

Actual compatibility/quality оставшихся75 cases устанавливает сама проба; её
предварительный live PASS не требуется. До неё нужны проверяемые route/billing/
token assumptions из таблицы и review C0 конкретного candidate/plan. Уже выделенные
150 RUB и известный prior не требуют повторного согласования той же суммы.

| Код STOP | Действие reviewer |
|---|---|
| `AMBIGUOUS_PROVIDER_NAME` | Не выбирать первую запись; нужен иной уникальный route или отдельное решение C0 |
| `OUTPUT_CAP_REVIEW_REQUIRED` / `OUTPUT_CAP_PARAMETER_UNSUPPORTED` | Подтвердить один поддерживаемый alias и полный paid-output bound |
| `CONDITIONAL_FEE_REVIEW_REQUIRED` / `FEE_EXCLUSION_REVIEW_REQUIRED` | Проверить каждый fee; не копировать synthetic evidence из тестов |
| `JSON_SCHEMA_STRICT_REJECTED` / `IMAGE_CAPABILITY_UNKNOWN` | Этот выбранный route не допускается без необходимых capabilities |
| `TARIFF_UNKNOWN` / `PLAN_EXCEEDS_CEILING` | Устранить неизвестный контракт либо вернуть C0 бюджетный blocker; не повышать лимит |
| `REVIEW_EXPIRED` / `PROVIDER_CONFIGURATION_CHANGED` / `TARIFF_SCHEMA_CHANGED` | Нужен новый review изменившегося контракта; одна смена числовых цен сама по себе не требует review |
| `GENERATION_ID_INVALID` / `HISTORY_VERIFICATION_FAILED` / `HISTORY_METERING_UNKNOWN` | Сохранить receipt, сверить конкретное наблюдение; не выполнять следующий POST |
| `APPROVAL_LIMIT` / `APPROVED_BUDGET_TOO_SMALL` | Проверить остаток149.98730215 и меньший approved amount по свежему полному резерву |

Локальный резерв не гарантирует фактическое списание провайдером. UNKNOWN,
429/5xx, timeout и отмена не возвращают резерв. Каждая попытка записывает и flush
резерв **до** HTTP; файл открывается исключительно как новый. Это не durable
billing subsystem и не защита от ручного второго запуска под другим именем.
Повтор после сбоя/новый файл требует C0 reconciliation и нового остаточного допуска.

## Финальный допуск и live

Сначала повторный offline расчёт с reviewed facts:

```sh
.venv/bin/python -m asm.ai.probe --plan --review .env.m4-probe.review.json
```

C0 проверяет candidate и фактические reviews, показывает plan/fingerprints и
источник запуска. При reserve + prior >150 RUB либо reserve > approved — STOP;
бюджет/выборка не меняются автоматически. Следующая команда подготовлена для
Windows с имеющимся ключом; **сейчас HOLD до review C0 и закрытия таблицы выше**.
Заменить два placeholders фактическими SHA/ссылкой решения C0; фиктивный approval
не подставлять. Общий бюджет уже выделен, повторный запрос150 не нужен.

```powershell
& {
    $ErrorActionPreference = "Stop"
    $Candidate = "C0_ACCEPTED_FULL_SHA"
    $Approval = "C0_REVIEW_REF"
    if ($Candidate -cnotmatch '^[0-9a-f]{40}$' -or $Approval -eq "C0_REVIEW_REF") {
        throw "Exact reviewed candidate and C0 decision required"
    }
    $Actual = git rev-parse HEAD
    if ($LASTEXITCODE -ne 0 -or $Actual -cne $Candidate) { throw "Source SHA mismatch" }
    $Dirty = git status --porcelain
    if ($LASTEXITCODE -ne 0 -or $Dirty) { throw "Clean checkout required" }
    if (-not (Test-Path .\.env.m4-probe) -or -not (Test-Path .\.env.m4-probe.review.json)) {
        throw "Existing private secret and actual three-route review required"
    }
    $Report = ".env.m4-probe.observation-r1.report.jsonl"
    if (Test-Path $Report) { throw "Receipt already exists; preserve it and reconcile, do not retry" }
    .\.venv\Scripts\python.exe -m asm.ai.probe --live --secret-file .env.m4-probe --review .env.m4-probe.review.json --approval-ref $Approval --approved-rub 149.98730215 --source-sha $Candidate --source-environment LOCAL_DESKTOP --report $Report
    if ($LASTEXITCODE -ne 0) { throw "Probe STOP; retain receipt, no automatic retry" }
}
```

При меньшем согласованном бюджете заменить149.98730215 на него. Команда не содержит
secret. В source-environment честно указать LOCAL_DESKTOP либо LOCAL_BACKEND;
сам flag не доказывает размещение. Не менять VM/Happ/SSH/egress для этого шага.
Доступность с ПК не доказывает backend route; runtime-ready требует отдельного
вызова из фактической backend среды по допуску C0/C6. Не использовать TG relay.

Выход2 — STOP/FAIL, выход0 — отчёт создан; даже полный automated PASS требует
review всех final outputs. Первый провал quality/route/schema/tools/usage/cost
останавливает расходы; repair/retry/fallback отсутствуют. Остальные cases явно
остаются непройденными, failure не усредняется.

JSONL содержит source SHA/environment/approval, plan и reservations, case/model,
source prior/total/stage budget, old/new pricing, expected route и отдельно observed
body/history каждого ответа, revisions, outcomes,
usage/CONFIRMED либо UNKNOWN cost, READ count и проверяемый synthetic final.
Raw HTTP, headers, key, provider reasoning и chain-of-thought не сохраняются.
Latency — whole-scenario elapsed, p50/p95 nearest-rank и N; не время компиляции.
Стоимость completed scenarios и их средняя сравниваются только после ручного
прохождения всех expectations. Regex checks — предварительный фильтр, не доказательство
истинности prose; C0 проверяет выдуманные факты, семантику отрицаний и handoff.
При полном прохождении ожидаются75 finals,81 POST,6 READ и N=25 на каждую модель.
Для модели без completed scenarios стоимость остаётся null/UNKNOWN, не нулём.
На малой выборке не делать production вывод. До такого review selected_model=null;
затем C0 фиксирует одного прошедшего кандидата с минимальной стоимостью или blocker.

Остановка: Ctrl-C, не повторять автоматически; сохранить receipt, сверить возможное
списание по отдельному допуску. По окончании отозвать dedicated key через консоль
и удалить только `.env.m4-probe`, когда оператору больше не нужен. Runtime не включён.
