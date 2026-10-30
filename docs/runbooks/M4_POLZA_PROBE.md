# M4.2 — DeepSeek report принят; следующий шаг у C4

**Команду DeepSeek tool roundtrip больше не запускать.** Владелец вернул полный
отчёт; допуск OWNER_ROUNDTRIP_R1_1RUB использован. Сейчас новых команд с ключом
или платных запусков нет. Следующий шаг — [задача C4 M4.2-GPT-QUALITY-R1](../tasks/M4_HANDOFF.md)
по [решению C0](../decisions/IMPL-004-m4-pilot-ai.md).

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

C4 готовит conversation_v2 и отдельную полную GPT-only проверку по тем же fixtures.
Подготовительные границы:≤27 POST/2 READ/54 history GET/1 catalog, ceiling15 RUB
из прежнего150, prior34/max61 attempts. Все old holds сохраняются. Старый v1
prompt, result schema и flags не переписываются; новые finals требуют ручной
оценки даже при полном техническом проходе.

**Это задача на подготовку, не live допуск.** После source review C0 опубликует
одну готовую Windows команду с новым exact SHA/ref/report. Сейчас владельцу
достаточно передать [CURRENT handoff](../tasks/M4_HANDOFF.md) в C4. Повторно
подтверждать общий150 или передавать ключ не нужно.

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
