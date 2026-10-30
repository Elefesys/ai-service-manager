# M4.2 — история GPT проверена; следующий шаг C4

**Сейчас владельцу запускать команды не нужно.** Metadata read завершён:
Polza вернула attemptsCount2, а наш verifier требовал1. Подготовлена
[задача C4](../tasks/M4_HANDOFF.md) на исправление semantics и оставшиеся18
scenarios. Передай C4 immutable ссылку на HANDOFF этой версии.

## Принятый результат

`m4-polza-gpt-quality-history-r1.jsonl`:1633 bytes/4 events,
SHA256 `bf09d2dba67de7fbbd1f9a88cde309ee0a135fc1df52ab0554f591beeb1fba24`.
2 history GET/0 model POST; exact generation gen_2227417601602097153.
List/detail: completed, OpenAI, usage694 input/118 output/812 total,
**reported cost0.00743079 RUB**, attemptsCount2. Это не второй POST нашего
runner и не доказательство маршрута каждой внутренней попытки.

Исходный GPT v2 report SHA256 `b0d1cb8249b321792355a2b4d29e1a79ba6eae30847a5deee6fbafa36159017f`
сохраняется:7 manual PASS/2 READ, case7 technical STOP,17 NOT_RUN.
Передача владельцу19, images20/21 и повтор price22 ещё не проверены.

Shared150 без изменения: **confirmed0.23889134 RUB/40 known client POST**,
**4 unknown/held7.585505548 RUB**, всего44 client POST,
remaining **142.175603112 RUB**. Reported amount неизвестного ранее call
сохранён отдельно; old hold0.465109963 не освобождён. Это ledger capacity,
не account balance. Новых history запросов ради settlement не требуется.

## Что будет после C4

Готовится отдельный fixed stage18 scenarios (repeats7–24),≤18 model POST,
0 READ,2 images,36 history GET/1 catalog; ceiling10 RUB из прежнего150.
Первые7 scenarios и обе READ проверки не повторяются. Source/plan пройдут C0
review, затем здесь появится готовая Windows команда с существующим environment
и ключом. Общий бюджет заново подтверждать не нужно.

Старые paid/history команды использованы. Все отчёты сохранить; не удалять и
не переименовывать их для повторного запуска. Нового live допуска сейчас нет.
Код provider/prompt/guards пока не исправлен; эта версия меняет только4 docs.

[Точный scope и проверки C4](../tasks/M4_HANDOFF.md) ·
[Решение C0](../decisions/IMPL-004-m4-pilot-ai.md).
PR39 Draft/headcd60, CI41009211185 RED и C0-M4-CI-OBSERVATION-01 открыты.
Gemini/DeepSeek compatibility DEFERRED; runtime/Telegram/merge не включаются.
