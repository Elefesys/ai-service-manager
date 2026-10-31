# M4.2 — GPT synthetic проверка завершена

**Ничего повторно запускать не нужно.** GPT synthetic проверка принята C0:
25 manual PASS,2 READ и2 synthetic images; GPT/v2 выбран для первого runtime.
PR39/40 слиты. [Main CI41178689536](https://github.com/Elefesys/ai-service-manager/actions/runs/41178689536)
прошёл11/11, ошибка CI закрыта. [Текущая задача C2 R2](../tasks/M4_HANDOFF.md) —
исправить подготовку PostgreSQL-проверки доступа к контексту и сохранения
AI-запуска/результата. R1 остановился до тестов; его отчёт сохранён.

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

Accepted main586240e88c825aa67593af5d72e0bdbb251ed3bb:860 PostgreSQL,
54 browser и остальные CI gates PASS. C2 продолжает PG authority/durable state
задачу на synthetic данных: исправляет JSON DEFAULT0014 и получение source
tree внутри test container, затем выполняет один новый bounded run.
Все55 hosted tests R1 пока NOT_RUN. Эта задача нужна, чтобы после перезапуска использовать
сохранённый ответ и запрещать работу при HUMAN/stale/revoked состоянии.
После её проверки подключим application worker и защищённую отправку.
На ПК/ВМ ничего запускать не нужно; ключ Polza не нужен, reports сохранить.

Owner ref `C0-M4.2-GPT-QUALITY-R2:7e48510311ab77c41f84b11becb2734ddb430690:OWNER_REMAINING18_R2_10RUB`
использован. [Прежняя команда](https://github.com/Elefesys/ai-service-manager/blob/5241eba3e38bd488cea052f894efb9b43b1f7d32/docs/runbooks/M4_POLZA_PROBE.md)
остаётся историей выполненного запуска. Paid HOLD, нового бюджета нет.

Это synthetic EVAL_ONLY: OpenAI family подтверждена в receipt, flex variant
не наблюдался. Реальные данные, Telegram runtime и backend route ещё требуют
соответствующей приёмки. Gemini/DeepSeek DEFERRED; сравнение75 не завершено.
PR40/main проверены; source CI не является включением живого AI runtime.
Новая схема0014 проверяется отдельно; application/schema переход, durable
Outbox/send и разрешённый TEST smoke ещё впереди. Deploy/paid запусков нет.
