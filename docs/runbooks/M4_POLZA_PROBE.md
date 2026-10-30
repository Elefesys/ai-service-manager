# M4.2 — DeepSeek остановлен, следующая подготовка у C4

**Сейчас ничего не запускать.** Один разрешённый DeepSeek eval-r1 выполнен и
остановлен на первом сценарии. Не повторять команду, в том числе с другим
именем report. Сохранить все reports и передать C4 [актуальный handoff](../tasks/M4_HANDOFF.md).

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

## Что готовит C4

Отдельный конечный compatibility profile: named `read_current` → проверка
tool call/истории → один synthetic READ → final с `tool_choice:none` и прежней
строгой схемой. Максимум2 POST/1 READ/4 history GET/1 catalog; подготовительный
ceiling1 RUB внутри прежнего150, новый prior из таблицы выше. Exact limits,
write-set и критерии — в handoff. Ключ владельца и реальные вызовы C4 не нужны.

Этот профиль проверяет управляемый tool roundtrip; он не подменяет исходное
auto-tools сравнение. При успешном source review C0 опубликует новую команду.
Сейчас **нет нового live допуска**. Не запускать отдельно сохранённый старый
DeepSeek mode: у него уже устаревший prior. Бюджет150 заново подтверждать не нужно.

## Проверки и сохранённые ограничения

C0 пересчитал все summary fields, caps, reservations и quality flags по5 events.
4 CONTROLLED проверки PASS: whole-stage STOP по такому final; длинный текст
без обрезания; отказ правильного адреса без READ; положительный2-call roundtrip.
MockTransport, sockets и owner .env reads запрещены. Source не менялся,
прежние616 targeted checks и полный CI не повторялись. Это не новый hosted PASS.

GPT25 finals/27 POST/2 READ сохраняются: no_send_claim19 QUALITY_FAIL,
unknown_price22 QUALITY_NOTE. Gemini BLOCKED,2 failed POST/0 final. Исходное
75-case comparison не завершено; модель не выбрана, runtime_authorized=false.
PR39 Draft/headcd60, CI41009211185 RED; root cause M3 observer timeout UNKNOWN,
C0-M4-CI-OBSERVATION-01 и full CI нового source нужны до merge/runtime.
Main/VM/DB/Telegram этим отчётом не меняются.

## Использованные инструкции — только история

- [DeepSeek eval-r1](https://github.com/Elefesys/ai-service-manager/blob/1dfc6ec3a22d1be38a4a3269af847775bfc6db10/docs/runbooks/M4_POLZA_PROBE.md): consumed, не повторять.
- [Gemini diagnostic-r1](https://github.com/Elefesys/ai-service-manager/blob/2a1848f7089efda50913e24a58fcf21cafe167fc/docs/runbooks/M4_POLZA_PROBE.md): consumed, SIGNATURE_EXTRA_MISSING, charge UNKNOWN.
- [History-r1](https://github.com/Elefesys/ai-service-manager/blob/c94d2ff7923c930a8e3d1983b9a05f07414eb967/docs/runbooks/M4_POLZA_PROBE.md): UNKNOWN/HISTORY_PROVIDER_UNKNOWN,0 POST.
- [R2](https://github.com/Elefesys/ai-service-manager/blob/6e37623c804695c08cbb83d3fba8ee03ec9c4e1f/docs/runbooks/M4_POLZA_PROBE.md): stopped, не replay/resume approval.

Все исходные файлы сохранить. Ключ, raw response/reasoning или signature
передавать C0/C4 не нужно.
