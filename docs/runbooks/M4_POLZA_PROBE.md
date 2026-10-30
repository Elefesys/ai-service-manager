# M4.2 — GPT synthetic проверка завершена

**Ничего повторно запускать не нужно.** C0 принял18 новых ответов; вместе
с7 сохранёнными из R1 получено **25 manual PASS**,2 READ и2 synthetic images.
GPT/v2 выбран кандидатом для разработки первого runtime. C4 context/read/agent
принят локально. C2 R3 принят: 258 PASS на PostgreSQL, cleanup PASS.
Полный [PR39 CI](https://github.com/Elefesys/ai-service-manager/actions/runs/41099431123)
принят C0: **11/11 SUCCESS**. Следующий шаг — merge PR39 владельцем.

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

C0 проверил R3: все 258 сценариев прошли, включая удержание блокировки после
таймаута и ошибки/отмену observer SQL. Исправление принято.
C0 принял общий PR39 head1b7a6987: full CI41099431123/attempt1,11/11 SUCCESS.
Владелец сливает [PR39](https://github.com/Elefesys/ai-service-manager/pull/39)
после снятия Draft C0. Затем C0 проверяет actual main/CI и выдаёт задачу
подключения durable/runtime/Telegram. Передавать новую задачу C2 или запускать
что-либо на ПК/ВМ сейчас не нужно. Ключ Polza не нужен, reports сохранить.
[Подробная приёмка CI](../tasks/M4_HANDOFF.md) опубликована отдельно от tested head.

Owner ref `C0-M4.2-GPT-QUALITY-R2:7e48510311ab77c41f84b11becb2734ddb430690:OWNER_REMAINING18_R2_10RUB`
использован. [Прежняя команда](https://github.com/Elefesys/ai-service-manager/blob/5241eba3e38bd488cea052f894efb9b43b1f7d32/docs/runbooks/M4_POLZA_PROBE.md)
остаётся историей выполненного запуска. Paid HOLD, нового бюджета нет.

Это synthetic EVAL_ONLY: OpenAI family подтверждена в receipt, flex variant
не наблюдался. Реальные данные, Telegram runtime и backend route ещё требуют
соответствующей приёмки. Gemini/DeepSeek DEFERRED; сравнение75 не завершено.
PR39 готов к merge по принятому CI; запись итога не меняет tested head.
Старый CI41009211185 RED сохранён как история; его причина UNKNOWN.
Никакого enable/deploy эта приёмка не выполняет.
