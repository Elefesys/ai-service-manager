# M4.2 — GPT synthetic проверка завершена

**Ничего повторно запускать не нужно.** GPT synthetic проверка принята C0:
25 manual PASS,2 READ и2 synthetic images; GPT/v2 выбран для первого runtime.
PR39/40 слиты. [Main CI41178689536](https://github.com/Elefesys/ai-service-manager/actions/runs/41178689536)
прошёл11/11, ошибка CI закрыта. C2 R4 принят C0:104 PASS, включая35 actual PG.
[C0 принял R11](../tasks/M4_HANDOFF.md): полный CI12/12 SUCCESS,
3529 unit и1031/1031 actual PostgreSQL PASS. Foundation blocker закрыт.
Владелец может слить **только PR42**, способом Create a merge commit,
при source3f68b262/main586240e8. PR41 не сливать. После merge — проверка main у C0.

## Принятый отчёт

`reports/m4-polza-gpt-quality-r2.jsonl`:42789 bytes,39 events,
SHA256 **f89ad00e49ab730f12a62f413142dd16ee7864bf4a026f9308662aa984750f35**.
Source **7e48510311ab77c41f84b11becb2734ddb430690**, tree **23dad7ed0cf0e9974285db3881a1093e670fe443**.
18 client model POST,36 history GET,1 catalog GET,0 READ; новых unknown0.
HUMAN_REVIEW_REQUIRED в файле означает, что runner оставил оценку человеку.
C0 отдельно проверил все18 finals и признал6 regex flags ложными срабатываниями
по смыслу: отрицания цены/отмены и корректные уточнения без ожидаемого слова.
no_send_claim теперь handoff; unknown_price не добавляет вымышленное правило.
Подробные per-case основания — в [приёмке GPT](https://github.com/Elefesys/ai-service-manager/blob/ed29ce8c104c5f1631ddb6af483588b7df5ff2a0/docs/tasks/M4_HANDOFF.md); исходный JSONL не меняется.

| Учёт | RUB |
|---|---:|
| Этот запуск, confirmed | 0.13616096 |
| Все запуски, confirmed | 0.37505230 |
| Сохранённые резервы4 unknown | 7.585505548 |
| Остаток из150 с резервами | 142.039442152 |

Всего62 client model POST:58 known/4 unknown. Старые holds не освобождены,
reported0.00743079 из отдельного history receipt остаётся UNSETTLED.
Остаток — внутренний ledger, не проверенный баланс Polza.
R2 p50 11.163s /p95 16.393s, N18, включая history; маленькая выборка, не SLA.

## Дальше

Synthetic runtime принят C0: ответ проходит через durable result и защищённый
Outbox; права/currentness, ручной ответ во время AI wait, отмена, restart/replay
и UNKNOWN/no-regeneration проверены. R11 восстановил совместимость foundation
без изменения product code, миграций и защитных ограничений.

Следующий шаг — merge PR42 и штатный push/main CI12/12; C0 проверяет результат
перед отметками INTEGRATED/VERIFIED. Проверенное дерево PR42 не менять.
Реальный AI→Telegram сценарий будет отдельной задачей; synthetic PASS не
включает автоматически live provider/transport. AI остаётся выключен по умолчанию.
На ПК/ВМ ничего запускать не нужно; ключ Polza не нужен, reports сохранить.

Owner ref `C0-M4.2-GPT-QUALITY-R2:7e48510311ab77c41f84b11becb2734ddb430690:OWNER_REMAINING18_R2_10RUB`
использован. [Прежняя команда](https://github.com/Elefesys/ai-service-manager/blob/5241eba3e38bd488cea052f894efb9b43b1f7d32/docs/runbooks/M4_POLZA_PROBE.md)
остаётся историей выполненного запуска. Paid HOLD, нового бюджета нет.

Это synthetic EVAL_ONLY: OpenAI family подтверждена в receipt, flex variant
не наблюдался. Реальные данные, Telegram runtime и backend route ещё требуют
соответствующей приёмки. Gemini/DeepSeek DEFERRED; сравнение75 не завершено.
PR40/main проверены; source CI не является включением живого AI runtime.
0014 отдельно не сливается; согласованный application/Outbox successor0015
назначен C3. Разрешённый живой TEST smoke — отдельный последующий шаг.
Deploy/paid запусков нет.
