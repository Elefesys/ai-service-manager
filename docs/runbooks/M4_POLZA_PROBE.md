# M4.2 — synthetic Polza probe

Статус первой передачи: **REVIEW / PAID PROBE NOT RUN**. Команды ниже не являются
разрешением потратить деньги. C0 получает отдельный допуск владельца после review
кода, плана и размещения ключа. Никаких клиентских данных, Telegram, БД, S3 или
runtime activation. Accepted deployment остаётся LOCAL / asm_local.

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

Без flags выполняется тот же offline plan. Он не читает secret и не создаёт HTTP
client. Fixtures фиксируют ожидания до вызовов: 20 русских text cases, включая два
READ round trips, плюс три critical repeats и две заранее созданные PNG фигуры
128×128 на каждого кандидата. PNG bytes и SHA-256 находятся в JSON fixture.
Image calls — только отдельная EVAL_ONLY проверка, не расширение text Gateway.

| Предел | Значение для обоих кандидатов |
|---|---|
| Модели | ровно `openai/gpt-6-luna`, `google/gemini-3.8-flash` |
| Сценарии | 25 на модель, 50 всего |
| Model HTTP | максимум 54; отдельный жёсткий потолок 80 не заполняется повторами |
| Catalog HTTP | один GET на preflight; один повторный GET на live admission |
| READ | максимум 4, только локальные fixture facts |
| Вход / выход | 32768 / 512 tokens на call |
| Общий token reservation | максимум 1797120 tokens |
| Wire input / response | 24576 / 32768 bytes на call |
| Сценарий / весь live запуск | 60 / 1800 секунд, включая каталог |
| Предложение бюджета | максимум 100 RUB; сейчас не разрешено |

Plan без account review печатает `priced_reservation_rub: null`, UNKNOWN.
Публичный ценник из исследования не заменяет актуальный account tariff.

## Отдельный ключ после допуска C0

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

## Account preflight и review маршрутов

После отдельного допуска на ключ/preflight; `C0-APPROVAL-ID` заменить ссылкой/ID
реального решения, не выдумывать. Команда делает один GET, без генераций:

```sh
.venv/bin/python -m asm.ai.probe --preflight --approval-ref C0-APPROVAL-ID --report .env.m4-probe.catalog.json
```

Из отчёта reviewer создаёт `.env.m4-probe.review.json`: JSON-массив из **двух**
RouteReview в порядке моделей выше. Для каждого копируются `catalog_entry`,
`catalog_sha256` и `checked_at`; добавляются поля ниже. Это trusted configuration,
не вывод модели. Пустое поле/неизвестный факт означает BLOCKED; заполнять текстом
«supported» ради обхода допуска нельзя. Review действителен 24 часа, live повторно
получает account catalog и сравнивает fingerprint целиком для каждой модели.

| Поле | Что должен подтвердить reviewer |
|---|---|
| `model` | точный разрешённый ID, без замены |
| `provider_name` | точное имя из `providers`, для `provider.only` |
| `response_provider` | документированное соответствующее значение response `provider`; это `Route.upstream` |
| `route_evidence` | источник/дата/вывод для name→response ID, official upstream, key restrictions |
| `schema_tools_evidence` | native strict **точная** conversation_result_v1, READ tools и совместное использование |
| `token_bound_evidence` | основание указанной ниже границы для этого tokenizer/wire protocol |
| `billing_bound_evidence` | актуальные ставки/единицы, применимые fees, отсутствие неизвестного начисления сверх резерва |
| `image_bound_evidence` | поддержка PNG input и token/billing bound для данных двух изображений |

Каждое evidence — короткий текст (20–2000 символов) со ссылкой и проверенным
выводом. Это обязательный review, не автоматическая сертификация текстового поля.
Не копировать строки `OFFLINE FIXTURE ONLY` из тестов: они не являются evidence.
Если нет источника, вернуть C0 точный неизвестный факт. Нет catalog auto-selection.

Каталог должен явно сообщать `is_unofficial: false`, `tools.status: supported`,
`json_schema_strict.status: supported`, необходимые supported_parameters и token
limits. `top_provider` не используется вместо выбранного provider. Individual
tools/schema flags сами по себе **не** доказывают совместимость. Есть потенциально
важный вопрос для live admission: принятая schema содержит root `anyOf`; адаптер
передаёт её без удаления ограничений или wrapping. Если маршрут не принимает
её, C0 получает blocker для `contracts.py` / `schemas/conversation_result_v1.json`
и решения о минимальной эквивалентной wire-схеме; C4 не меняет принятый контракт.

Официальные источники, сверенные при подготовке 2026-10-29:

- [GET Models reference](https://polza.ai/docs/api-reference/models/list): `include_providers=true&include_capabilities=true`; статусы возможностей могут быть unknown.
- [Models guide](https://polza.ai/docs/gaidy/models): RUB, явно именованные per-million и per-request поля. Reference также показывает альтернативные per-token поля: код не угадывает единицы.
- [Provider selection](https://polza.ai/docs/gaidy/provider-selection): only/fallback и различие request name / returned provider.
- [Unofficial providers](https://polza.ai/docs/gaidy/unofficial-providers): restriction ключа и `is_unofficial`.
- [Chat](https://polza.ai/docs/gaidy/chat-completions), [tools](https://polza.ai/docs/gaidy/tool-calling), [schema](https://polza.ai/docs/gaidy/structured-output), [usage](https://polza.ai/docs/osobennosti/usage): wire mapping, finish reasons, `cost_rub` / `cost` в RUB.

## Тарификация и token bound

Локальная оценка: **число UTF-8 bytes полного serialized body + 4096 tokens**.
Включены messages, READ definitions, native schema, tool exchanges и protocol
поля. Это не точный tokenizer и не универсальное доказательство для любой
модели. Допуск требует подтверждения, что tokenizer не выдаёт больше одного
token на byte и скрытое framing/schema преобразование (для PNG также image tokens)
укладывается в запас 4096. Если такой границы для маршрута нет — paid STOP;
увеличивать лимит или называть эвристику гарантией нельзя. После каждого ответа
usage сравнивается с границей; неизвестный usage не даёт PASS.

До генераций рассчитывается полный резерв 27 calls для каждой модели. Цена call:
`(32768 * input_rate + 512 * output_rate) / 1000000 + request_rate` с округлением
вверх до 1e-9 RUB. Input складывает prompt/image/cache-read/cache-write ставки;
output складывает completion/reasoning; request складывает per_request и
request_per_thousand/1000. Это намеренно консервативно, без cache discounts.
Reviewer подтверждает, что отсутствующие optional fees неприменимы/включены и
`max_completion_tokens` включает всю платную reasoning-генерацию. Неизвестные
валюта, единицы, tiers, fee objects или дополнительные ставки останавливают план.

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

C0 показывает владельцу конкретный plan/fingerprint, вычисленный резерв, лимит
ключа и источник запуска. Если резерв >100 RUB — STOP/уменьшение выборки только
новым review; программа не повышает бюджет. После owner approval до100 RUB:

```sh
.venv/bin/python -m asm.ai.probe --live --review .env.m4-probe.review.json --approval-ref C0-APPROVAL-ID --approved-rub 100 --source-sha "$(git rev-parse HEAD)" --source-environment LOCAL_DESKTOP --report .env.m4-probe.report.jsonl
```

При меньшем согласованном бюджете заменить100 на него. Команда не содержит
secret. В source-environment честно указать LOCAL_DESKTOP либо LOCAL_BACKEND;
сам flag не доказывает размещение. Не менять VM/Happ/SSH/egress для этого шага.
Доступность с ПК не доказывает backend route; runtime-ready требует отдельного
вызова из фактической backend среды по допуску C0/C6. Не использовать TG relay.

Выход2 — STOP/FAIL, выход0 — отчёт создан; даже полный automated PASS требует
review всех final outputs. Первый провал quality/route/schema/tools/usage/cost
останавливает расходы; repair/retry/fallback отсутствуют. Остальные cases явно
остаются непройденными, failure не усредняется.

JSONL содержит source SHA/environment/approval, plan и reservations, case/model,
expected route и observed model/provider каждого ответа, revisions, outcomes,
usage/CONFIRMED либо UNKNOWN cost, READ count и проверяемый synthetic final.
Raw HTTP, headers, key, provider reasoning и chain-of-thought не сохраняются.
Latency — whole-scenario elapsed, p50/p95 nearest-rank и N; не время компиляции.
Стоимость completed scenarios и их средняя сравниваются только после ручного
прохождения всех expectations. Regex checks — предварительный фильтр, не доказательство
истинности prose; C0 проверяет выдуманные факты, семантику отрицаний и handoff.
На малой выборке не делать production вывод. До такого review selected_model=null;
затем C0 фиксирует одного прошедшего кандидата с минимальной стоимостью или blocker.

Остановка: Ctrl-C, не повторять автоматически; сохранить receipt, сверить возможное
списание по отдельному допуску. По окончании отозвать dedicated key через консоль
и удалить только `.env.m4-probe`, когда оператору больше не нужен. Runtime не включён.
