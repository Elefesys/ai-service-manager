# M4.2 — GPT synthetic проверка завершена

**Ничего повторно запускать не нужно.** GPT synthetic проверка принята C0:
25 manual PASS,2 READ и2 synthetic images; GPT/v2 выбран для первого runtime.
PR39/40 слиты. [Main CI41178689536](https://github.com/Elefesys/ai-service-manager/actions/runs/41178689536)
прошёл11/11, ошибка CI закрыта. C2 R4 принят C0:104 PASS, включая35 actual PG.
[PR42 слит и проверен C0](../tasks/M4_HANDOFF.md): accepted main3cb3764c,
post-merge CI41971790237 **12/12 SUCCESS**,3529unit и1031actualPG PASS.
Synthetic runtime INTEGRATED/VERIFIED (LOCAL/TEST). PR41 также отмечен merged:
его коммиты вошли в PR42; отдельного merge PR41 в main нет.
На ПК/ВМ ничего запускать не нужно. Полный M4/live запуск ещё впереди.

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

Слияние и штатный push/main CI завершены. Следующий предусмотренный результат —
реальный Polza/GPT-v2 → runtime → guarded Telegram путь с явной процедурой
enable/disable. Текущий worker намеренно принимает только FakeAdapter/FAKE;
старые API probes отдельно от application не включают live transport.

Выдана [C3-M4.3-POLZA-RUNTIME-R1](../tasks/M4_HANDOFF.md): C3 готовит
provider bridge в одной новой ветке/PR. Сначала закрытые HTTP-транспорты и
actual PostgreSQL, затем full CI; остальные роли HOLD. Он вернёт source/CI
и короткий новый M4_RUNTIME_PILOT runbook с plan/enable/disable.
AI выключен по умолчанию, нового paid/live/deploy допуска нет.
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
