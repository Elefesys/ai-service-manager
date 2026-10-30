# M4.2 — Gemini diagnostic получен; подготовка отдельного DeepSeek этапа

**Сейчас владельцу ничего запускать не нужно.** ONE_POST_R1_5RUB использован;
`reports/m4-polza-gemini-diagnostic-r1.jsonl` принят C0. Следующая единственная
выдача — C4: подготовить DeepSeek-only25-case stage без платных вызовов.
[Точный handoff и ограничения](../tasks/M4_HANDOFF.md),
[CURRENT](../TASK_REGISTER.md), [решение C0](../decisions/IMPL-004-m4-pilot-ai.md).

## Что установил последний запуск

Source68093c769f24ea63eca5185179c3eab5fafd1229,1 catalog GET/1 Gemini POST/
1 history GET/0 READ/0 follow-up; TECHNICAL_FAILURE. Primary
`SIGNATURE_EXTRA_MISSING` означает отсутствие `extra_content` в tool call.
Ответ завершился `tool_calls`, но принятого READ roundtrip нет. Размер signature
не измерен; receipt не сообщает о других возможных местах её передачи.

Generation `gen_2227371816211582977`, model google/gemini-3.8-flash:
354 входных/172 выходных токена,156 reasoning уже входят в172. Body сообщает
**0.05269262 RUB**, уровень **FIELD_VALIDATED_ONLY**. Сверка истории отказала
после первого GET с `HISTORY_VERIFICATION_FAILED`, до запроса detail. Точная
причина неизвестна; это не установленная ошибка provider label или стоимости.
Provider в body отсутствует, history family неизвестна. Flex только запрошен.

Поле `new_confirmed_cost_rub=0` означает отсутствие подтверждённого списания,
а не бесплатный запрос. План внутри receipt сохраняет PLAN_ONLY, но конкретный
POST был допущен exact C0 ref/5 RUB. Нового допуска из этого плана не следует.

| Общий учёт | Значение |
|---|---:|
| Принятый бюджет | 150 RUB |
| Подтверждённый расход / POST | 0.17509189 RUB /30 |
| Unknown POST | 2 Gemini |
| Удержанные резервы обоих unknown | 6.929759328 RUB |
| Confirmed + held | 7.104851218 RUB |
| Остаток с учётом резервов | **142.895148782 RUB** |

Это расчёт лимита, не проверка остатка счёта Polza. Оба old unknown остаются
отдельно; body amount не погашает ни один из них. Не удалять/переименовывать
отчёты ради повторного запуска. R1/R2/history/diagnostic сохранить без изменений.
Ключ, raw reasoning/response или signature C0 не нужны.

## Следующий этап для C4, ещё не команда владельцу

Подготовить один конечный режим только для `deepseek/deepseek-v4.1-flash-1017`
через `wafer/us`, прежний `reasoning: {effort: "none", enabled: false}`.
Прежние fixtures/prompt/schema/quality flags и порядок25 cases сохраняются.
GPT уже собран; Gemini BLOCKED до доказанного protocol решения. Нет fallback,
повтора GPT/Gemini или общего R3/resume. Только after-review exact-source ref
и explicit stage ceiling смогут открыть live шаг в прежнем150.

| Граница нового этапа | Требование к реализации |
|---|---|
| Cases / POST / READ | 25 /≤27 /≤2;20 text,3 critical repeats,2 synthetic PNG |
| Другие модели | GPT POST0, Gemini POST0 |
| Catalog | 1 fresh GET,4MiB/20s; проверяется только выбранный DeepSeek entry |
| History | ≤54 GET,65536 bytes/GET, прежний15s verification budget на call |
| Tokens / wire bytes | 32768/512 и24576/32768 на call; total token reservation≤898560 |
| Case / whole stage | 60 /1800s; catalog/history внутри общего deadline |
| Prior | confirmed0.17509189, known30, unknown2, held6.929759328, всего32 POST |
| Новое stage approval | Explicit amount≤142.895148782; fresh reserve всех27 calls≤amount до первого POST |
| Совокупный call ceiling | 59 с прежними32 |
| Report | Новый exclusive reports/m4-polza-deepseek-eval-r1.jsonl; старые файлы не трогать |
| Итог | Все finals/flags и отдельный new-stage accounting; selected_model=null/runtime_authorized=false |

До POST обязательны прежние SyntheticRoute guards: unique official selector,
declared tools/strict schema/image, поддерживаемый output cap, non-thinking
toggle/effort, все rates/fees. Неизвестная цена/возможность — STOP до POST.
Каталог не доказывает hosted behavior. Actual history identity/provider/usage/
cost проверяются до READ и принятия final. Смена family/route, raw reasoning или
ненулевые reasoning tokens DeepSeek остаются техническими STOP, не обходятся.

Новые diagnostic stage/reason/type на history отказе должны уточнять только
существующие ветки проверки без ослабления условий, дополнительных GET/POST,
raw labels/response/key/account/reasoning. Unknown charge удерживает новый резерв
сверх обоих старых; cancellation/crash после reservation не разрешают replay.
Quality flags сами по себе не превращают завершённый ответ в technical STOP
или quality PASS; ручная оценка всех finals остаётся необходимой.

Будущий plan offline и без ключа; режимы/старые approval refs конфликтуют до
key/HTTP. Готовый Windows live блок появится после source review C0. Сейчас
нет новой команды, нового расхода или необходимости переустанавливать среду.

## Исторические команды и результаты

- [Использованный Gemini diagnostic ONE_POST_R1_5RUB](https://github.com/Elefesys/ai-service-manager/blob/2a1848f7089efda50913e24a58fcf21cafe167fc/docs/runbooks/M4_POLZA_PROBE.md): завершён, не повторять.
- [Использованный GET-only history-r1](https://github.com/Elefesys/ai-service-manager/blob/c94d2ff7923c930a8e3d1983b9a05f07414eb967/docs/runbooks/M4_POLZA_PROBE.md): UNKNOWN/HISTORY_PROVIDER_UNKNOWN,0 POST; не повторять.
- [R2](https://github.com/Elefesys/ai-service-manager/blob/6e37623c804695c08cbb83d3fba8ee03ec9c4e1f/docs/runbooks/M4_POLZA_PROBE.md): остановлен, не replay/resume approval.

Source68093c7 сохраняет старые CLI priors для воспроизводимости; они не учитывают
последний диагностический POST и не годятся как лимит нового этапа. GPT25 finals /
27 POST/2 READ сохранены: no_send_claim19 QUALITY_FAIL, unknown_price22 QUALITY_NOTE.
Gemini2 attempts/0 final, DeepSeek NOT_RUN. Full comparison75 cases не завершена.

## Протокол и проверка C0

[Google protocol](https://ai.google.dev/gemini-api/docs/generate-content/thought-signatures#signatures-for-openai-compatibility)
задаёт `tool_calls[].extra_content.google.thought_signature`. В проверенных
2026-10-30 [Polza tools](https://polza.ai/docs/gaidy/tool-calling),
[reasoning](https://polza.ai/docs/osobennosti/reasoning-tokens) и
[chat API](https://polza.ai/docs/api-reference/chat/completions) не найден
альтернативный signature carrier; это не вывод о всех возможностях сервиса.
Текущий report доказывает только отсутствие ожидаемого блока. Gemini остаётся
BLOCKED, не quality FAIL. Не убирать validator, не вставлять dummy signature,
не копировать весь raw message/reasoning и не менять thinking наугад.

[Polza history contract](https://polza.ai/docs/api-reference/history/generations)
описывает metadata отдельно от model response. C0 воспроизвёл8 CONTROLLED
вариантов exact source: positive history подтверждает расход, сохраняя signature
ERROR;7 разных list failures дают тот же generic error после1 GET. Поэтому
конкретная причина реального history отказа остаётся UNKNOWN. Реальная сеть,
owner key, READ/follow-up в проверках C0 не использованы. Арифметика receipt PASS.

Code source68093c7 ранее прошёл520 targeted tests/Ruff/format4/mypy71; текущая
правка только4 docs, полный suite/CI не повторялся. PR39 Draft/headcd60,
CI41009211185 RED; C0-M4-CI-OBSERVATION-01 остаётся до merge/runtime. Полный CI
source68093c7 NOT_RUN. Пилот, Telegram и live DB этим receipt не запускаются.
