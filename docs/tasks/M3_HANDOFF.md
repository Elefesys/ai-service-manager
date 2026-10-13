# M3 — управление разговором и участие владельца

Дата подготовки: 2026-10-09. Ответственный за выдачу и приёмку: C0.
Статусы задач — только [TASK_REGISTER](../TASK_REGISTER.md).
План принят C0 и слит в PR25; runtime/DDL M3 допускаются отдельными выдачами C0.
Он детализирует M3.1/M3.2 из исходного плана, не добавляет новый milestone.

## 0. Текущая выдача C0 — C5-M3.2-CONSOLE-CONTROL, реализация

Дата: 2026-10-13 UTC. **Пользователь поручил продолжить реализацию M3.**
C5 реализует первый ограниченный UI-срез M3.2 на уже принятом CONTROL API.
Отдельный предварительный contract-only PR не нужен: wire/domain contract
сохранён, ниже зафиксированы правила его использования в интерфейсе.

### 0.1. Результат и последовательность M3

В выбранном диалоге Console владелец видит текущий режим, может явно забрать
управление или разрешить будущую автоматику, видит начатую/неопределённую отправку
и сохраняет работающий ручной ответ. Это делает принятый backend доступным из UI.

C0 уточняет порядок небольших срезов в рамках прежнего M3.2:
**CONSOLE-CONTROL сейчас → ESCALATION backend/API → CONSOLE ожидания/Escalation
→ оставшиеся native/provenance gates и M3-ACCEPTANCE.**
Escalation пока не имеет принятого DDL/API; её ожидание не блокирует UI существующих
трёх CONTROL routes. M3-A10 закрывается здесь только в части control/in-flight,
не в части причины/очереди ожидания владельца. Native-owner/edit-delete остаются
NOT VERIFIED; конкретный account evidence будет отдельной выдачей C0.
Новый milestone не создаётся. C3/C1/C2/C6/C8 сейчас не получают параллельной
implementation задачи; один автор и один новый implementation PR.

### 0.2. Точный старт и принятые основания

| Поле | Значение |
|---|---|
| Repository | `Elefesys/ai-service-manager` |
| Accepted main / schema | `4b63d9ad59fee3631b4314211aaae40884488c98` / `0010` |
| Accepted main tree | `0db9939107435dec730c8963af5e686fa0f818ce` |
| Ветка C5 | `c5/m3-2-console-control`, отдельный checkout |
| Старт implementation | C0 preparation commit на этой ветке, sole parent = accepted main; полный SHA/tree в C0 выдаче |
| C0 preparation scope | Только `docs/TASK_REGISTER.md` и `docs/tasks/M3_HANDOFF.md` |
| Принятый contract | `docs/tasks/M3_CONTRACT.md`, 238882 bytes, blob `1763a5379926e4ae3e47483faf91b006e5bc4f30`, неизменен |

GUARDS закрыт: [C0 post-merge receipt](https://github.com/Elefesys/ai-service-manager/pull/28#issuecomment-6137086496).
[Main CI38338767227](https://github.com/Elefesys/ai-service-manager/actions/runs/38338767227)
9/9 SUCCESS + clean9/9: 1082 unit, 597 PostgreSQL, 114 frontend, 27 browser.
Это baseline, не evidence ещё не написанного UI.

Сверить start/parent/tree, читать AGENTS, IMPL-001, Spec §§5.10–5.14/18.5/Console,
ADR-024/025/026/267, MVP GJ-G/GJ-J, Roadmap M3 и Implementation Plan M3.1/M3.2.
Непосредственные источники: M3_CONTRACT §§8/12.2–12.5/13, actual
`conversations/http.py`, `http_models.py`, `control.py`,
`0010_conversation_guards.py:conversation_control_read`,
generated OpenAPI и текущие MessagingPanel/API/browser fixtures.
Исторические proposal/OPEN строки contract не отменяют принятие CONTROL/GUARDS.

C0 подготовит ветку; C5 продолжает её, не создаёт её повторно и не использует
слитые M2/GUARDS или экспериментальную CI ветку. Новый Draft PR в main открыть
после содержательного UI diff. Coordination-only commit не требует отдельного
PR/CI/review. Reset/rebase/force/main merge не выдаются.

### 0.3. Exact write allowlist — 14 paths

| Path | Допустимое изменение |
|---|---|
| `frontend/src/ConversationControl.tsx` | Новый компактный control UI; при необходимости держать pending intent выше в MessagingPanel |
| `frontend/src/ConversationControl.test.tsx` | Значимые unit/component проверки состояний и конкурирующих ответов |
| `frontend/src/conversation-control-api.ts` | Строгий потребитель трёх принятых routes |
| `frontend/src/conversation-control-api.test.ts` | DTO/error/identity/decimal-string и exact request checks |
| `frontend/src/MessagingPanel.tsx` | Встраивание UI, согласованное обновление после control/manual; существующий manual recovery сохранить |
| `frontend/src/MessagingPanel.test.tsx` | Интеграция UI и необходимые mocks новых GET, прежние assertions сохранить |
| `frontend/src/messaging-fixtures.test-helper.ts` | Только связанные synthetic fixture values/helpers |
| `frontend/src/App.test.tsx` | Только необходимые adapters/mocks и regression общей session/owner boundary |
| `frontend/src/style.css` | Узкие стили control UI, keyboard/narrow layout |
| `frontend/e2e/conversation-control.spec.ts` | Новые journeys через настоящий owner API/PostgreSQL |
| `frontend/e2e/messaging.spec.ts` | Только необходимая адаптация существующего journey к добавленному UI, без ослабления |
| `scripts/m2_4_browser_fixture.py` | Конечные CONTROLLED TEST presets и read-only control/receipt/Audit counters; сохранить прежний provisioning scope |
| `tests/test_m2_4_browser_fixture.py` | Проверки добавленных finite presets/read-only counters и прежних границ |
| `docs/tasks/M3_CONSOLE_CONTROL.md` | Краткие UI правила, команды, соответствие scenarios→tests и ограничения; финальные SHA/CI — в receipt |

Это максимум, не требование изменить все файлы. Full PR может содержать эти
14 paths плюс два C0 preparation docs; C5 два preparation docs не редактирует.
Другой path или реальный дефект backend contract — конкретный minimal diff/факт C0
до расширения. Не добавлять «на будущее» routes/components/абстракции.

Backend, migrations/0010, schema/readiness, auth/tenancy/billing/M2 contracts,
M3_CONTRACT, canon, manifests/lockfiles, App auth implementation, текущий
messaging-api и browser worker, Compose/Docker/workflows/штатные scripts неизменны.
**Новая migration не назначается.** У прежнего CI 9 jobs; foundation40/browser25,
остальные budgets/pins сохранены. [Оптимизация CI DEFERRED до завершения M3](https://github.com/Elefesys/ai-service-manager/pull/29#issuecomment-6139376486);
из PR29 ничего не переносить, включая clock fixtures.

### 0.4. Поведение интерфейса по принятому контракту

1. **Текущее состояние — отдельный GET control.** При выборе диалога показывать
   загрузку/недоступность/состояние именно выбранного actor/Workspace/conversation/
   Client. Сверять response IDs. HUMAN — управление у мастера; AI — владелец
   разрешил автоматику. Режим AI не означает наличие работающей LLM или обещание
   отправки. В пользовательском UI не нужны SHA, generation/fence, Docker и
   названия fixture consumers. Достаточны понятный режим, действия и предупреждения.
   Refresh — чтение, mount/focus/выбор/автовосстановление session ничего не пишут.

2. **Только явное действие владельца.** «Забрать управление» вызывает takeover;
   «Разрешить автоматику» — resume. Запрос формируется из последнего пригодного
   control GET: exact expected_client_id/control_generation/context_version,
   новый Idempotency-Key на новое намерение, cookie + CSRF по действующей схеме.
   Нет If-Match, query, actor/mode в body. POST отвечает **200**, а не M2 manual202.
   Takeover не блокировать по billing/Telegram availability или наличию старого
   UNKNOWN: сервер разрешает локальную остановку независимо от них.
   Resume не обходится frontend-проверкой billing; authoritative denial приходит
   с сервера. Новый Resume работает только для будущих входящих сообщений.

3. **Receipt не равен текущему режиму.** ACCEPTED/REPLAY подтверждают сохранённую
   операцию. После них выполнять свежий GET; при его ошибке показывать подтверждение
   операции отдельно от недоступного current state и повторять только чтение.
   Старый replay Resume не должен рисовать AI поверх более нового HUMAN.
   Успешный manual intent тоже требует свежего control GET, поскольку сервер
   атомарно ставит HUMAN; не повторять control POST как часть manual send.

4. **Pending intent и потеря ответа.** В памяти страницы сохранить immutable
   actor/Workspace/conversation/Client/operation/body/key. Пока результат
   неоднозначен, не создавать новый key и не подменять expected tuple свежими
   values для повтора. После восстановления session повтор возможен лишь
   явным действием того же actor в том же контексте, тем же route/body/key.
   Network/timeout/abort/5xx/невалидный ответ не доказывают rollback.
   Idempotency conflict останавливает повтор. STALE_STATE требует свежего GET
   и нового осознанного действия, без автоматического retry-loop.
   Можно завершить локальное ожидание без повтора, явно указав, что это не отмена
   возможной серверной операции. Не сохранять intent в local/session storage.

5. **Смена контекста и обычные гонки UI.** Late GET/POST из другого диалога,
   Workspace, actor или прежней session не меняет текущую карточку. При 401/403
   использовать существующие recovery/deny callbacks; отозванный OWNER не
   продолжает работу из cached session. Нельзя переносить pending intent другому
   пользователю. В выбранном диалоге не отправлять перекрывающиеся новые
   manual/control намерения; сохранить явное восстановление прежнего manual
   намерения. Старый UNKNOWN доставки — не pending HTTP намерение.
   Все параметры версий остаются decimal strings/BigInt, не Number.

6. **Начатая и неизвестная отправка.** Показать оба признака
   manual_delivery.has_dispatching/has_unknown с нейтральной семантикой отправки:
   actual0010 read охватывает связанные Outbox, не только ручные сообщения.
   Takeover останавливает дальнейшую автоматику, но не отзывает уже начатый
   внешний запрос; UNKNOWN не становится CANCELLED и не даёт кнопку повторного
   send. История сообщений остаётся источником отдельных delivery outcomes.
   Это предупреждение о конкретном состоянии, не общий security disclaimer.

7. **Совместимость и доступность.** Ручной текст, private images, pagination,
   статусы доставки, billing/Auth и доступ OWNER сохраняются. Loading/error/empty
   состояния не показывают старое «успешное» состояние как текущее.
   Keyboard и узкий экран работают; использовать существующий визуальный стиль.
   Никаких LLM, Escalation заглушек, обещанного срока ответа или переключателя
   автоматического native takeover в этом срезе.

API parser сохраняет точные DTO/nullable/enum/error envelopes из accepted
http_models/OpenAPI: canonical UUID/time, positive decimal <=9223372036854775807,
previous_generation+1=accepted_generation, operation/accepted_mode и identity
исходного запроса. Результат с неверной identity не принимается как успех.
Не расширять текущие auth/M2 parsers ради новых CONTROL codes.

### 0.5. Достаточные проверки

| ID | Проверяемый результат | Достаточное evidence |
|---|---|---|
| UI-C01 | Выбор/refresh read-only; правильные IDs/mode, роли и большие version strings | API/component tests |
| UI-C02 | HUMAN→Resume→AI→Takeover→HUMAN, затем manual остаётся HUMAN; receipt/Audit по одной принятой операции | Actual browser→HTTP→PG, read-only counters; основной journey также @narrow |
| UI-C03 | Две вкладки/stale tuple: второй intent отклонён, нет auto retry; старый response не меняет новый контекст | Actual two-page/API journey + deferred-response component tests |
| UI-C04 | Реальный commit с потерянным HTTP ответом: тот же key/body возвращает REPLAY, counters не растут повторно; ошибка GET после успеха повторяет только GET | Browser route.fetch с последующим abort/задержкой + actual PG, без fabricated success JSON |
| UI-C05 | Session/CSRF recovery, revoke, смена actor/Workspace/conversation не переадресуют намерение | Component tests; один адресный actual browser context/revoke scenario |
| UI-C06 | DISPATCHING/UNKNOWN видны, control не обещает recall/resend; старый replay не подменяет current state | Component/parser для обоих flags + actual UNKNOWN через существующий CONTROLLED worker; отдельный новый in-flight harness не нужен |
| UI-C07 | Прежние manual/private image/billing/auth journeys сохранены; клавиатура и narrow без горизонтального overflow | Весь existing frontend/browser suite плюс UI-C02 |

Не нужно дублировать все backend concurrency/RLS/migration тесты: они приняты и
остаются в штатном CI. Новые tests проверяют риски добавленного UI. Для DISPATCHING
сослаться также на существующий actual backend test; не создавать новый runtime
fault framework. В browser допускается задержать/оборвать настоящий response,
но не подменять им отсутствующее server execution.

Использовать существующие disposable browser TEST fixtures: finite synthetic
identities/bindings, owner HTTP commands, runtime ingest/Worker и private storage.
Новые control counters — read-only; не INSERT/UPDATE canonical control receipts,
Audit/Conversation/Message/Outbox/Jobs от migrator ради зелёного теста.
При необходимости добавить несколько именованных presets, а не произвольный
SQL/fixture endpoint. Existing worker умеет unknown/success и seed из PRESETS;
новый worker/daemon не требуется. Прежние assertions и quiet/no-secret diagnostics
сохранить, не включать dumps session/CSRF/password/signed URLs.

Локально: `npm --prefix frontend run typecheck`, `npm --prefix frontend test`,
`npm --prefix frontend run build`, применимые Ruff/unit checks finite fixture,
`git diff --check`. Actual browser: `sh scripts/test_browser.sh`;
полный foundation: `sh scripts/ci.sh`. Если локального Docker нет, честно
использовать actual disposable CI и отдельно указать, что локально не исполнялось.

Нужен финальный штатный PR CI **9/9 SUCCESS + clean-source9/9** на final source.
Сохранить все прежние 1082 unit/597 PG/114 frontend/27 browser cases; новые counts
указать по факту, без квоты тестов. Не исключать suites, не повышать timeout,
не менять workflows или повторять зелёный SHA ради статистики.
Не нужен полный historical ZIP/image audit для UI-only изменений.

### 0.6. Возврат и приёмка

Один канонический C5 receipt в новом Draft PR, обновлять его и проверять чтением.
Вернуть final head/parent/tree, exact C0 start/base, full PR scope и собственный
implementation diff, summary поведения, таблицу UI-C01–07→actual tests/results,
команды, CI run/attempt/9 jobs/clean gates/tested merge и несколько замечаний по UX.
Небольшие screenshots только synthetic UI без private URLs/credentials можно
приложить при необходимости; отдельная презентация не нужна.

Статус результата — REVIEW либо BLOCKED с конкретным фактом. После готового
candidate удерживать head. Далее C0 intake → короткое независимое C8 review
нового UI/receipt recovery → решение C0 → merge пользователем → actual main CI.
C1/C2/C6 повторный review неизменного backend/schema/harness заранее не выдаётся.
Если обнаружено противоречие accepted API, вернуть его C0, а не менять контракт
или расширять задачу скрыто.

C5-M3.2-CONSOLE-CONTROL и весь M3 сейчас IN_PROGRESS; работа ещё не выполнена.
GUARDS INTEGRATED/VERIFIED LOCAL/TEST, IMPL-05 OPEN/fix DEFERRED сохранены.
VM/live Telegram/рабочие DB-S3/deploy/merge вне этой выдачи. После принятия этого
среза C0 выдаст C3 ограниченный ESCALATION backend/API; M4 пока не начинается.

<details>
<summary>Завершённые TURNS/CONTROL/GUARDS поручения; не активная выдача</summary>

## 0. Текущая выдача C0 — C3-M3.1-GUARDS, реализация

Дата: 2026-10-12 UTC. **GUARDS contract принят; C3 разрешена implementation
в том же Draft PR28.** Это следующий срез M3.1, не новый milestone.
C3 — единственный implementation автор; C0 владеет реестром/handoff,
migration queue и приёмкой. M3.1-GUARDS и весь M3 остаются IN_PROGRESS.

### 0.1. Принятый design и точный старт

[C0 R1 acceptance](https://github.com/Elefesys/ai-service-manager/pull/28#issuecomment-6121868191)
на `9645c99d49c0a27ea9f4fd95de676771df0a135d` закрывает
C1-M3-GUARDS-01/P3 и C2-M3-GUARDS-01/P2 **в contract scope**.
[C6 design PASS](https://github.com/Elefesys/ai-service-manager/pull/28#issuecomment-6122758140)
проверен C0: новых findings нет. GUARDS-POLICY-01/02, GUARDS-DB-01 и теперь
GUARDS-COMPAT-01 **LOCKED в design scope**. C6 source/budget plan конкретизирован
в §0.5 ниже. Actual runtime/timing доказательства остаются частью этой реализации.

| Привязка | Значение |
|---|---|
| Repository / PR | `Elefesys/ai-service-manager` / [PR28](https://github.com/Elefesys/ai-service-manager/pull/28) |
| Branch / checkout | `c3/m3-1-guards`, отдельный checkout; продолжить ту же ветку |
| Принятый contract head | `9645c99d49c0a27ea9f4fd95de676771df0a135d` |
| Contract head tree | `c29c13a6a67c0d8349ddb5f73f0d5a1ffe10febd` |
| Parent принятого R1 | `d4f9bdec7ec801e61165e142b16e98f6d2322e0b` |
| Accepted main / frozen C | `c6a55b6b17d1c1ab286ce97dfa4bd27197141fe5` / schema0009 |

Начать от **C0 continuation commit**, который содержит эту выдачу, имеет sole
parent = принятый R1 и меняет только `docs/TASK_REGISTER.md` и этот handoff.
Его полный SHA/tree опубликован в поручении C0. Сверить parent, два changed paths
и неизменный contract blob; не терять preparation и не возвращаться к старой
CONTROL ветке. Reset/rebase/force/new PR/main mutation не входят в выдачу.

[R1 CI38229073360 attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/38229073360)
SUCCESS9/9 + clean9/9: tested merge
`750e4432e1e9e3636b9e810530ff253e0726fe47`, parents accepted main + R1,
tree=R1;1056 non-integration/555 PG/113 frontend/27 browser PASS.
Это retained0009 на docs head. Preparation CI и implementation CI привязываются
к своим SHA; ни один docs PASS не доказывает GUARDS execution.

### 0.2. Источники, разрешение и граница среза

Прочитать AGENTS, единый реестр, весь M3_CONTRACT (особенно §§6/8/12/13),
M2 send/recovery contract, R1/C2/C6 receipts и actual0005–0009 definitions,
CONTROL service, consumer/TurnSnapshot, messaging database/worker/results/commands/
policy, Outbox/recovery/material hooks и relevant tests. Канон — originals по
SOURCE_MANIFEST: Spec§§5.1–5.14/18.5–18.8/18.14/25.7,
ADR024–026/121–128/180/197–198/217/267, MVP GJ-G/GJ-J, Roadmap M3,
Implementation Plan M3.1 и IMPL-001.

Цель: fresh CONTROLLED ingress → обычный PostgreSQL-backed worker →
guarded deterministic text result → атомарный Message/receipt/Outbox/send Job →
отдельный final dispatch admission → existing counted controlled adapter.
Takeover/new context пресекают устаревшую работу; уже допущенный send сохраняет
честный outcome. `TURN_TEST_V1` остаётся effects-free. Это LOCAL/TEST срез
admission/control/idempotency, без ModelGateway/AIRun/LLM/нового tool framework.

C0 **назначает и разрешает одну** новую migration:
`migrations/versions/0010_conversation_guards.py`,
**revision0010, down_revision0009**. Резерв принадлежит этому срезу/C3; другого
DDL writer нет. Applied0001–0009 immutable. Это разрешение реализации и проверок,
не приёмка её результата; production coexistence/cutover этой выдачей не заявлены.

Принятый M3_CONTRACT226090bytes/blob
`3a16de4c4336e70af53143e08b8858fc2452d7a9`/SHA256
`8b3df3bf404857fe182323a1238bbac4862c860d7c5c5c7e9f1f3ae2abda6cab`
сохранить целиком как byte-prefix. C3 может **append §13.11 implementation evidence**
с mapping коду/сценариям/source/CI и C6 plan; новый отдельный technical contract
не нужен. Исторические OPEN/proposal/невыданный0010 в §§13.1–13.10/старых receipts
заменены этой активной выдачей; согласованная technical semantics сохраняется.

### 0.3. Exact write allowlist —31 paths

26 existing +5 new; новые: migration, guards module и3 GUARDS test files.
Список — максимальный разрешённый scope, не требование менять каждый файл:

```text
migrations/versions/0010_conversation_guards.py
backend/src/asm/conversations/guards.py
backend/src/asm/messaging/database.py
backend/src/asm/messaging/worker.py
backend/src/asm/messaging/results.py
backend/src/asm/foundation.py
backend/src/asm/telegram/provisioning.py
tests/test_m3_1_guards.py
tests/test_m3_1_guards_postgres.py
tests/test_m3_1_guards_migrations.py
tests/test_m2_1_postgres.py
tests/test_m3_1_control_postgres.py
tests/test_m3_1_control_api_postgres.py
frontend/src/MessagingPanel.tsx
frontend/src/MessagingPanel.test.tsx
tests/test_foundation.py
tests/test_m2_3_setup.py
tests/test_tenancy_postgres.py
tests/test_m2_3_schema_postgres.py
tests/test_m3_1_migrations.py
tests/test_m3_1_control_migrations.py
tests/test_postgres.py
tests/test_m1_3_c0_acceptance.py
tests/test_telegram_egress_postgres.py
scripts/prepare_telegram_egress.py
scripts/test_telegram_egress.sh
scripts/test_telegram_egress_migration.sh
tests/test_telegram_egress.py
tests/test_telegram_egress_migration.py
docs/tasks/M3_CONTRACT.md
docs/runbooks/M2_TELEGRAM_LOCAL_TEST.md
```

Назначение каждого path — принятое §13.9 с R1 five-path additions.
`foundation.py`/`provisioning.py` — exact0010 readiness/TEST provisioning и только
необходимое существующему constructor CONTROLLED wiring. Frontend — только
нейтральная OUTBOUND подпись «Исходящее» и existing-history regression; manual
composer, history rows/delivery statuses/receipt recovery сохраняются.
Fixture/inventory изменения — только вследствие0010/typed kind/receipt FK;
старые assertions и revision-qualified T/C cycles сохраняются.

Нужен другой path или изменение принятой semantics — сначала конкретный diff
и причина C0 до записи. AGENTS/register/handoff, imported canon, applied migrations,
owner/tenancy HTTP API, DTO/OpenAPI snapshots, dependencies/lockfiles, Compose/
workflows/pins не входят в allowlist. `tests/test_m1_3_postgres.py` не требуется:
GUARDS не добавляет Audit columns. Разрешённые scripts/helper меняются только
для exact inventories/source pairing/new phase по §0.5, без общего redesign.

### 0.4. Обязательная runtime/DB граница

Реализовать §13 целиком в принятом scope. В частности:

1. Новый LOCAL/TEST + CONTROLLED Resume сохраняет private
   `CONTROLLED_GUARDS_V1`; legacy profile NULL, replay без добавления профиля.
   Сам Resume Jobs не создаёт; старый HUMAN/AI/pre-fence backlog не получает
   authority. Live автор именно этого Resume, Workspace/Business/Connection
   и product availability проверяются при result admission и final send.
   `messaging.manual_send` — availability, не owner permission для worker.
   Automated TELEGRAM отказывает до probe/I/O; будущий caller требует отдельной
   выдачи. Server/DB/provider gates не задаются пользовательским flag/GUC/payload.

2. Trusted typed origin, canonical refs, generation/fence/revision/context и
   claim/XID/lease по §13.2–4. Существующий worker admission, короткие transactions,
   Job→authority/Business/Connection/billing→Conversation NO KEY UPDATE→Turn,
   для send own Job→own Outbox прежде этой цепочки. Post-wait DB clock повторяет
   live/expiry/activation checks, equality expiry deny. Enqueue не берёт
   authority/billing locks из material hook; external computation/I/O вне UoW.

3. `prepare_guarded_turn`/`accept_guarded_text`/`replay_guarded_text`/
   `begin_guarded_send` через normal Worker. Не более одного accepted intent на
   Turn. Input=context до собственного Message; receipt intent context=input+1
   после material trigger. Чужой новый material fact инвалидирует pending send.
   Result receipt+Message+Outbox+send Job+consumer terminal UPDATE атомарны.
   Canonical winning replay прежде live lease и повторное чтение после wait,
   changed text conflict, без повторной computation/action/permit.

4. `turn_execute(uuid,uuid)` — replacement тела в0010:
   GROUP/MEDIA/TEST_CONSUME only после canonical guard; GUARDED_TEXT INVALID_INPUT
   **до** preflight/supersede/seal/terminal mutation. Старые ABI/grants/codec
   сохраняются. Typed send branches в claim/retry/finalize/recovery/preflight;
   GUARDS exhaustion terminalizes Job, не FAILED READY Turn.

5. DISPATCHING commit до permit/I/O — linearization. До него stale send подавляется;
   после него Takeover/новая generation/Owner revoke не отменяют factual finalize.
   Proven NOT_SENT может иметь старый attempt_id; каждый новый begin повторяет
   admission. Возможный effect → UNKNOWN/no-resend; lost start ACK → нет нового
   permit, committed start/recovery UNKNOWN/CALL=0. Lost finalize ACK читает
   canonical saved outcome и не понижает SENT. Прежние retry/lease/bounds сохраняются.

6. Одна `platform.turn_guard_receipts`, nullable immutable Resume.guard_profile/
   Job.guard_rejection, typed kind/step; exact36 = старые35 + эта table.
   Captured revision FK к immutable consumer Job; current context/generation не
   превращаются в FK. Явный send Job→Outbox same-kind FK, все восемь relation
   chains §13.6, reuse parent keys/turn_immutable и accepted identity uniqueness.
   Runtime без direct table SELECT/DML, existing role/RLS/context правила.
   Ровно6 новых SQL profiles §13.6; existing signatures/grants сохранены.
   Никаких выдуманных manual command/owner session/Audit от автоматического send.

7. Existing inbound/manual/file/delivery reconciliation работают в HUMAN.
   `manual_delivery` фильтрует SEND_MANUAL_TEXT; history OUTBOUND имеет
   нейтральную подпись, без скрытия automated rows. Public shape, manual
   fingerprints/receipts/Audit/UNKNOWN, auth/tenant/client isolation сохраняются.

### 0.5. Принятый C6 source/schema и budget plan

Это обязательная конкретизация §13.7 по
[C6 PASS](https://github.com/Elefesys/ai-service-manager/pull/28#issuecomment-6122758140).
G — будущий implementation candidate/его проверенный merge с равным tree,
**не** текущий docs/preparation SHA.

| Phase | Исполнитель / исходники | Schema и граница |
|---|---|---|
| Retained predecessor→H | P=`0b7e24ee425ebb429bf87dfe382cbd3fab883028`, H=`754f1c883e5a94a7fc9e729af2605424f949ba33`; unchanged H wrapper | Сохранённые0006→0007 intent/image/state proofs |
| Retained H→T | T=`ea1ae98ce9e5e26d5d0d14f3e6d278ecb9efbbad`; unchanged T checkout, `test_telegram_egress.sh --schema-upgrade H T` | Полный0007→0008, прежние full-T timeout/export cases |
| Retained T→C | C=`c6a55b6b17d1c1ab286ce97dfa4bd27197141fe5`; **C checkout**, direct `test_telegram_egress.sh --control-schema-upgrade T C budget_C` | Прежний0008→0009 child byte-identical, fixed T/C columns/recovery |
| Новый C→G | G coordinator + explicit known C/G schema selector; отдельная owned LOCAL DB/volume |0009→0010 readiness/preservation/reverse/refusal/recovery; actual G callers/restart |

В existing normal/Docker29 state lanes H/T/C выполняются по одному разу,
добавляется один G phase; новых matrix jobs/fault families нет.
**Не вызывать полный frozen C migration wrapper state внутри G**: он повторит
H/T chain и создаст другой coordinator600. Развести G coordinator source,
frozen C executor и G phase candidate; G-root `source_check(C)` не заменяет
реальный C checkout. Known phase/source pairs закрыты, не произвольная revision.

Прежние6 daemon negatives исполняются через direct
`__control_cleanup_negatives__` **в C checkout**, candidate=C, с C report,
сохранённым до удаления checkout. Их можно оставить в tail после нового G phase;
C report не переименовывается в G. Retained failure останавливает продвижение.
Полный T/negative/C evidence сохраняется отдельно до teardown/removal.

Сохранить exact H/T/C runtime/development image/source identities и archives;
C images из retained C phase переиспользуются после attestation, без лишней
пересборки. G migration/observer — G development image/asm_migrator.
Перед cutover старые API/worker/scheduler drained; старт/restart каждого caller
только на confirmed source/schema, actual image/CID сверяются.
Historical0007 saved-plan/`migration_source()` guard не расширяется на G.

**Один исходный prepare deadline t0+600** начинается после H, до любой T/C/G
source preparation. H сохраняет прежние held180/state25min bounds.
В этот600 входят whole T + full-T negatives, **весь retained C shell**
(prepare/runtime/capture/cleanup/report handoff), pre-G интервалы и G prepare.
C время не прибавляется повторно отдельным C prepare. C получает прежний
one-use0600 T/C/CONTROL budget, G — отдельный C/G/G budget с тем же started/deadline,
phase/source/owner/clock binding и накопленной charge; remaining=deadline-now.

Нынешний terminal C watchdog `remaining+480` **не переносится на retained C**:
внешний G supervisor ограничивает весь retained C remaining600 и завершает
owned process group при timeout, затем ждёт cleanup. Для terminal G остаются
нынешние отдельные runtime/command/state limits. Нового fresh600 и продления90
при re-entry нет: один persisted cleanup90/owner с тем же child/parent deadline.
State25min/foundation35min/exact Docker29/all9 gates не менять.

C6 измерил прежний0009 chain: whole T+negatives+C416.452s normal/341.616s Docker29;
арифметический остаток183.548/258.384s **не гарантия G и не новый лимит**.
Реальные C checkout/image work и G prepare/runtime стоимость показать на final G.
Если не помещается — вернуть C0 actual timing/узкий gap diff, не повышать
лимиты и не удалять прежние assertions; не пытаться rerun-to-green.

Migration checks:
- exact0007/0008/0009 inventories и T_COLUMNS/C_COLUMNS остаются frozen;
  G full36 inventory/columns содержит новые nullable fields/receipt.
- forward preservation — **fixed C projection** старых34 data tables плюс отдельно
  `alembic_version`0009→0010; это old35 inventory, не dynamic intersection.
  До запуска G workers проверить old rows/private-S3 bytes/pending manual/UNKNOWN/
  TURNS/CONTROL, NULL profile/rejection, empty guard receipt, отсутствие backfill/
  enqueue/reset. Дальнейшие worker effects отделены от DDL preservation.
- fresh/repeat upgrade; на0009 C readiness PASS/G refusal, на0010 наоборот;
  API/worker/scheduler/TEST provisioning требуют exact0010.
- no-use downgrade **только0010** восстанавливает exact0009 full35 data/
  definitions/grants/constraints/indexes/triggers/RLS и C readiness.
  Used-profile/kind/step/receipt/rejection (включая terminal) отказывает до DDL;
  snapshot used G не меняется. Не очищать usage ради успешного rollback.
- один новый existing commit/lost-result marker/exit86 case C→G с fresh
  independent migration-role observer: actual revision и DB/volume/asm_local/
  PID/birth/boot identity выбирают source. Confirmed0009→C, confirmed0010→G,
  unreadable/unknown/mismatch→STOP. Exit code сам source не выбирает.
  Старый control recovery остаётся T/0009-qualified; новая ветвь явно C/0010.
  Controller уместен в разрешённом guards migration test, нового framework нет.

Все7 compat paths уже в31-path allowlist. Latest canonical_fingerprint и
candidate-egress-source expected_revision обновляются на G **revision-qualified**;
frozen C bytes/expectations не переписываются. `infra/postgres/ensure_m1_3_prerequisites.sh`,
`scripts/check_backend.sh`, Compose/pins/workflows не нуждаются в адаптации.

### 0.6. Проверки и фактические доказательства

Покрыть 14 строк §13.8 компактными actual PostgreSQL/worker/process cases,
переиспользуя existing barriers/lock observation/counting/recovery. Fresh positive
обязательно проходит Resume → normal ingress/queue → guarded consumer → send,
а не raw Outbox fixture. Отдельно показать legacy-route rejection до mutation,
post-wait отказ, accept atomicity/replay и две различные process границы:
lost dispatch ACK до permit (CALL=0) и possible effect/response loss (CALL=1/EFFECT=1).
Это функциональная корректность и восстановление существующего пути.

Сохранить прежние unit/PG/frontend/browser/HTTP/wire/manual/CONTROL assertions.
Нейтральную history подпись проверить одним содержательным mixed-history
regression; новые UI flows не нужны. Для fixture/inventory adaptations указать
причину по0010/новому kind/FK, без skip/xfail/ослабления assertion.

Использовать штатные команды проекта: адресные GUARDS unit/PG/migration suites,
`sh scripts/ci.sh`, `sh scripts/test_browser.sh`, Ruff/mypy, frontend typecheck/tests,
generated OpenAPI consistency и whitespace/source checks. Final-source gates —
прежние9 jobs + clean-source9/9, normal/exact Docker29 и retained T/C/G evidence.
Если локальный Docker отсутствует, честно обозначить NOT RUN и получить actual
PG/S3/browser/Docker evidence на disposable GitHub runners штатным PR CI.
Моки и success docs head не подменяют эту проверку.

Receipt/runbook связывают full final head, parent/tree, accepted main,
tested merge с ordered parents main+head и tree=head, run/attempt/jobs,
clean checkouts, actual commands/counts и ограничения. Для нового G предъявить
оба state report/source/image bindings, C→G/reverse/refusal/recovery assertions,
actual timings/600 ledger/cleanup и сохранённые T/C markers.
Указать artifact IDs/digests и точные report paths для адресной проверки;
повторять полный исторический ZIP/archive audit без конкретной причины не нужно.
Не запускать повторные CI только ради цвета; при реальном исправлении новое
evidence привязывается к новому SHA.

### 0.7. Возврат C0 и границы выдачи

C3 продолжает тот же Draft PR28, делает содержательные commits и push в
`c3/m3-1-guards`; head удерживает после возврата на REVIEW. Обновляет один
[единый receipt](https://github.com/Elefesys/ai-service-manager/pull/28#issuecomment-6119496506),
проверяет публикацию чтением и возвращает его ссылку. Нужны: changed paths/diff,
migration/profile/contract mapping, каждый §13.8 case → actual test/assertion,
команды/evidence выше, ограничения и OPEN/gap. Если реализация или actual gates
не завершены, статус остаётся IN_PROGRESS с конкретным остатком, не READY/VERIFIED.

Затем C0 intake → адресные C1 product / C2 DB / C6 source-budget implementation
reviews по final candidate → C8 independent acceptance по выдаче C0 → решение
C0 → merge пользователем → проверка main. Повторный полный design review без
semantic delta не нужен. C3 не закрывает findings от имени C0 и не выдаёт задачи
другим чатам. При дополнительном path/semantic/budget gap вернуть конкретный
diff/evidence и дождаться решения только по этому расширению.

IMPL-01/02/03/04 CLOSED. **IMPL-05 OPEN, fix DEFERRED; неблокирующий P3 только
LOCAL/TEST по C0**, исходный C6 P2/CHANGES_REQUESTED сохранён как history.
Штатный STOP run остаётся неуспешным; automatic resume/reuse restored failed
journal не поддержан, новый run получает новый workspace. Нового факта влияния
на обычный path нет; этот fix и новый FS/chaos/security/fault framework не выдаются.

Native-owner/edit-delete provenance, production automated Telegram, ModelGateway/
LLM/M4, Escalation и Console CONTROL UI — отдельный scope. Базовые auth/tenant/
Client/data/idempotency protections сохраняются. VM/SSH, live Telegram,
working DB/S3, credentials/secrets, ACK/binding/renewal, deploy и merge не разрешены.
Допустимы только предусмотренные disposable LOCAL/TEST/CI проверки.

<details>
<summary>История GUARDS-CONTRACT до выдачи implementation; активная выдача выше</summary>

## 0. Текущая выдача C0 — C3-M3.1-GUARDS-CONTRACT

Дата: 2026-10-12 UTC. **CONTROL закрыт; следующий срез — GUARDS. Сейчас только
контрактное дополнение, реализация будет выдана после review.**
Это начальная фаза M3.1-GUARDS в существующем плане, не новый milestone.
C3 — единственный автор; C0 владеет реестром, этим handoff и приёмкой.

### 0.1. Принятая база, ветка и файлы

[PR27](https://github.com/Elefesys/ai-service-manager/pull/27) слит пользователем.
Accepted main **`c6a55b6b17d1c1ab286ce97dfa4bd27197141fe5`**, tree
`d7f0dbd35a637877b57d721cbb6a39c6ef59eae4`, schema0009.
Parents: `ea1ae98ce9e5e26d5d0d14f3e6d278ecb9efbbad` +
`634ea9b3b1af91124abd1b60873cc6fa723b5361`; дерево равно принятому candidate.
[Main CI38209943421](https://github.com/Elefesys/ai-service-manager/actions/runs/38209943421)
9/9 SUCCESS + clean9/9; 1056 non-integration/555 PG/113 frontend/27 browser.
[Приёмка C0](https://github.com/Elefesys/ai-service-manager/pull/27#issuecomment-6118563610):
M3.1-CONTROL INTEGRATED/VERIFIED LOCAL/TEST, весь M3 IN_PROGRESS.

Ветка **`c3/m3-1-guards`**, отдельный checkout. Начать от **C0 preparation head**,
единственный parent которого равен accepted main. Он меняет только
`docs/TASK_REGISTER.md` и `docs/tasks/M3_HANDOFF.md`; exact continuation SHA/tree
даны в поручении C0. Проверить parent и два paths; не потерять подготовку, не
продолжать старую CONTROL ветку, не reset/rebase/force. Main не менять.

**Единственный разрешённый C3 write path: `docs/tasks/M3_CONTRACT.md`.**
Append новый §13 GUARDS, сохраняя целиком принятый prefix:
170371 bytes, blob `aa3729960a43cf09d729a3514671d44c0b9685a4`,
SHA256 `12cfeb72a4c101c557a710522d0e553dbada06d2ade307649187086e85b6a3df`.
Существующие §§1–12 остаются исторически точными. Изменение принятой семантики
явно назвать proposal с причиной/последствиями для решения C0 до реализации.
Новые отдельные технические contracts не создавать.

Runtime, DDL, tests, frontend/OpenAPI, shared helper, workflows/Compose/pins,
AGENTS/реестр/handoff и imported canon сейчас не входят в C3 write scope.
Applied0001–0009 immutable; номер следующей миграции ещё не назначен.

### 0.2. Зачем нужен этот срез

CONTROL уже сохраняет HUMAN/AI, generation и Resume fence; worker сейчас обрабатывает
PROCESS_TURN через effects-free TEST consumer, а send path — SEND_MANUAL_TEXT.
Нужна одна рабочая граница, к которой последующий AI runtime сможет подключить
автоматический результат: устаревшая работа не меняет состояние и не отправляет
сообщение после Takeover. Уже допущенная отправка сохраняет честный исход.
Приём сообщений, ручной ответ и reconciliation продолжают работать в HUMAN.

Основания: AGENTS, текущий реестр, весь M3_CONTRACT (особенно §§6/8/12),
M2_CONTRACT send/recovery; Spec §§5.1–5.14/18.5–18.8,
ADR024–026/121–128/180/197–198/267; MVP GJ-G/GJ-J; Roadmap M3 и
Implementation Plan M3.1. При предлагаемой schema дельте дополнительно ADR217,
Spec§18.14/25.7. Прочитать actual0009 и унаследованные определения0005/0007/0008,
CONTROL orchestration, messaging worker/database/commands/results/policy,
TurnSnapshot/consumer, Outbox/attempt/recovery и relevant existing tests.
Выводы о внешнем API не нужны для этой фазы; native account gate остаётся отдельным.

### 0.3. Содержание минимального §13

1. **Доверенный источник и актуальность.** Развести OWNER_MANUAL и automated origin;
   происхождение задаёт доверенный command path, не клиентский flag. Указать
   необходимый набор Workspace/Client/Conversation/Turn refs, context/revision,
   control generation/fence и live claim/lease. Показать, какие существующие поля
   используются, какие действительно нужны дополнительно; legacy NULL/backlog и
   старый HUMAN Turn не получают новую authority после Resume.

2. **Конкретная transaction boundary.** Дать callable/SQL-orchestration outline и
   lock order, включая имеющиеся FK/trigger edges. Admission и Takeover используют
   одну сериализованную conversation границу. Live authority, product availability,
   channel rights/window и свежесть проверяются в нужном месте после ожиданий;
   lease сам по себе не разрешает эффект. External HTTP/LLM вне DB transaction.
   Отдельно описать отказ/STALE/SUPERSEDED и replay без новых mutation/Audit/jobs.
   Это требование к исполнению, не proposal универсального policy engine.

3. **Send и in-flight.** Указать durable linearization point до I/O, идентичность
   intent/attempt и совместимость с существующей send/recovery моделью. Takeover
   до admission подавляет новую автоматическую отправку; после dispatch commit
   запрос может уже начаться, в том числе в промежутке commit→I/O. Фактические
   SUCCEEDED/FAILED/UNKNOWN сохраняются после смены generation. UNKNOWN не
   переименовывать в CANCELLED и не отправлять повторно вслепую. Lost ACK ведёт
   к canonical read/reconciliation, не к новому вызову transport. Для UI определить
   только данные, нужные будущему потребителю; сам UI здесь не строится.

4. **Реальная точка использования без M4.** Описать минимальный интегрируемый
   worker/Outbox path и LOCAL/TEST сценарий с детерминированным результатом на
   существующем controlled transport. Нужна проверка реальной DB/worker границы,
   а не свободная функция, которую вызывает только тест. Схема/сервисы AIRun,
   ModelGateway, prompts, бизнес-команды M6–M9 и живой AI provider здесь не нужны.
   Production/Telegram automation этим design не включается; согласовать точное
   условие подключения будущего trusted caller без публичного обходного route.

5. **Совместимость и минимальная schema/API дельта.** Сохранить существующие manual
   fingerprints/receipts/UNKNOWN, CONTROL replay, TURNS и старые API/Audit snapshots.
   Перечислить необходимые DTO/status/SQL profiles и будущие paths. Если нужна
   миграция — обосновать каждое поле/constraint/таблицу, predecessor0009, no backfill,
   upgrade/downgrade/refusal и source/schema pairing. Это proposal: C0/C2 назначают
   revision и write scope перед кодом. Если schema не нужна, показать, как existing
   model покрывает требования. Не добавлять unused tables/adapters.

6. **Проверяемые сценарии M3-A03/A04–A06/A11.** Дать компактную таблицу scenario →
   actual caller/граница → observable result → существующий или необходимый test:
   Takeover до admission; AI→HUMAN→AI со старым worker; новый material context/
   superseded Turn; истёкший/reclaimed claim; dispatch до Takeover и результат
   после него; возможный effect/response loss/restart без resend; обычные manual/
   inbound/reconciliation в HUMAN. Проверки — обычные concurrency/recovery и
   existing controlled wire, без расширения программы filesystem/chaos faults.
   Отделить новые GUARDS proofs от уже принятых M2 UNKNOWN и CONTROL TEST outcomes.

7. **Один план реализации.** Предложить точный минимальный allowlist будущей
   implementation, используемые public/private methods, предполагаемые migration
   изменения, existing suite reuse и несколько обязательных regressions. Сложность
   каждого нового механизма объяснить конкретным сценарием. Нереализованные native/
   edit/delete/Console/Escalation/M4 границы обозначить явно; не расширять VERIFIED.

### 0.4. Соразмерность и сохранённые ограничения

Приоритет владельца — работающий MVP с базовой защитой и возможностью расширения.
Auth/tenant isolation, целостность данных, idempotency и право человека остановить
новую автоматику обязательны. Новые security/chaos программы, новый framework
надёжного журналирования и общая платформа будущих tools не являются результатом
этой задачи. Предпочитать имеющиеся DB/Jobs/Outbox механизмы и короткий ясный flow.

IMPL-01/02/03/04 CLOSED. IMPL-05 остаётся OPEN, исправление DEFERRED по
[решению C0](https://github.com/Elefesys/ai-service-manager/pull/27#issuecomment-6118079467);
не исправлять его заодно и не переоткрывать без нового practical evidence.
Native-owner observability NOT VERIFIED; automatic native takeover, material
edit/delete/provenance и reprocess ignored events не выданы. HUMAN default,
explicit Resume, no backlog automation и сохранение manual/inbound действуют.

Новые длительные прогоны, provider probes, Docker/PG/fault experiments для написания
контракта не нужны. Существующие CI gates/лимиты не отключать и не повышать.
VM/SSH/live Telegram/рабочие DB-S3/secrets/ACK/activation/renewal/deploy/merge,
новые платные сервисы/аккаунты не входят в выдачу.

### 0.5. Возврат, PR и review

Содержательный contract commit/обычный push в подготовленную ветку разрешены.
После завершения дополнения открыть **один новый Draft PR в main**; он продолжится
для реализации после её отдельной выдачи. Не открывать PR только для C0 preparation:
это исключает лишний предварительный CI на одной документационной подготовке.
Автоматический CI после открытия Draft PR работает штатно; вручную не rerun-to-green.
Docs CI не является execution GUARDS.

Вернуть один receipt: full base/parent/head/tree и PR; diff ровно одного C3 path;
byte-prefix/hash proof; краткие выбранные решения и действительно OPEN trade-offs;
точный будущий allowlist/миграция proposal; таблица сценариев и существующие
tests; выполненные source/diff/link checks и фактический CI status, без ложного
runtime PASS. При отсутствии нужной среды это явно указать, новый scope не
расширять молча. После сдачи удерживать head.

Далее C0 intake → адресные C1 (product/admission/manual) и C2 (DB/locks/recovery)
reviews → решение C0 → implementation в том же PR. C6 нужен только при конкретной
необходимой source/schema/harness дельте; C8 — после готовой реализации.
C3 сам не выдаёт поручения другим чатам и не начинает code до решения C0.

</details>

<details>
<summary>История завершённой CONTROL implementation выдачи</summary>

## 0. Текущая выдача C0 — C3-M3.1-CONTROL, реализация

Дата решения: 2026-10-10 UTC. **CONTROL-CONTRACT R1 принят; C3 выдана реализация
в существующем Draft [PR27](https://github.com/Elefesys/ai-service-manager/pull/27),
ветка `c3/m3-1-control`.** Это следующий срез M3.1, не новый milestone.
C3 — единственный автор implementation; C0 владеет handoff/реестром и приёмкой.
Предыдущая contract-only выдача ниже завершена и больше не ограничивает эту фазу.

### 0.1. Принятые основания и точный старт

- Accepted main/T: **`ea1ae98ce9e5e26d5d0d14f3e6d278ecb9efbbad`**, tree
  `11ad506a859db155973f965bcdd0cebc7bc0d5ed`, схема0008. TURNS принят в LOCAL/TEST
  A01/A02/context-частьA03/A11; [post-merge receipt C0](https://github.com/Elefesys/ai-service-manager/pull/26#issuecomment-6099303953).
- Принятый CONTROL contract R1: **`ffc0a66e2916f300e9f2f779084322a6a9b5447d`**,
  sole parent `cf043901186f7f5178332e64a056d336cce0dc0f`, tree
  `8cfc7edd0778c0d1ec053c70a24596f32281c0ad`.
- `M3_CONTRACT.md`:170371bytes, blob `aa3729960a43cf09d729a3514671d44c0b9685a4`,
  SHA256 `12cfeb72a4c101c557a710522d0e553dbada06d2ade307649187086e85b6a3df`.
  Неизменный TURNS prefix77343bytes/§§1–11: blob
  `5e87375852331523491a47926b9c5bd49946c157`, SHA256
  `8e610bf369d8c82ac629754a9a6077230e04b8190a13db61c263d0804fb5b0dd`.
- [C1 R1 PASS](https://github.com/Elefesys/ai-service-manager/pull/27#issuecomment-6101167262)
  и [C2 R1 PASS](https://github.com/Elefesys/ai-service-manager/pull/27#issuecomment-6101177021)
  относятся к exact R1; остаточных/new blockers нет. C0 принимает оба verdict
  после [собственного R1 intake](https://github.com/Elefesys/ai-service-manager/pull/27#issuecomment-6100794824).
- [C6 design PASS](https://github.com/Elefesys/ai-service-manager/pull/27#issuecomment-6100099472)
  на cf043901 сохраняется: R1 конкретизирует согласованный whole-T/remaining600
  protocol. Новый C6 PASS на R1 или actual timing evidence не утверждается.
- [R1 CI38073531311 attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/38073531311)
  завершён2026-10-10T18:22:38Z:9/9 jobs и9/9 clean-source gates SUCCESS.
  Tested merge `13f67b02f9ec67353f308f4f82f6002d06df734c`, ordered parents T+R1,
  tree=R1; foundation/browser logs:937 unit/462 integration/111 frontend/27 browser PASS.
  Это retained runtime/document evidence, не execution CONTROL/0009.

C0 закрывает **C1-M3-CONTROL-01, C1-M3-CONTROL-02, C2-M3-CONTROL-01 / P2**
в contract-review scope. **CONTROL-POLICY-01 и CONTROL-DB-01 приняты/закрыты
в design scope**; CONTROL-AUDIT-01 и CONTROL-COMPAT-01 сохраняют ранее принятые
границы. Implementation assertions каждого finding обязательны и не считаются PASS.
Статусы proposal/OPEN/ещё-не-write-permission в §§12.1/12.7/12.10/12.12 — снимок
предыдущей фазы: это решение C0 и текущая выдача их сменяют, не меняя technical design.

**Старт C3 — exact C0 preparation commit, единственный parent которого равен R1.**
Он меняет только `docs/TASK_REGISTER.md` и `docs/tasks/M3_HANDOFF.md`;
полный continuation SHA/tree опубликован в текущем поручении C0 в PR27 и его metadata.
Контракт/runtime/все остальные blobs и modes при подготовке сохранены.
Перед работой сверить этот full SHA, parent, два paths и contract blob; продолжить
ту же ветку в отдельном checkout без reset/rebase/force и без нового PR.
Main не менять. Не начинать от старого cf043901 или от T с потерей R1/подготовки.

Сначала прочитать AGENTS, реестр, весь M3_CONTRACT, M2_CONTRACT §§2–5/9–10,
реальные0008/runtime и применимый canon: Spec §§4.10,5.1–5.14,14.11,18.5–18.8,
18.14,24.7,25.7; ADR022–026/121–128/180/197–198/217/267/272;
MVP GJ-G/GJ-J, Roadmap M3, Implementation Plan M3.1/M3.2 и IMPL-001.
Originals/manifest и LOCKED решения неизменны; не восстанавливать их по пересказу.

### 0.2. Результат и обязательные инварианты

Реализовать принятый [M3_CONTRACT §12](M3_CONTRACT.md) целиком в выданной границе:
owner read/Takeover/Resume API, durable control receipt/Audit, atomic manual takeover,
ingress generation/fence и minimal0009 с безопасными LOCAL/TEST compatibility gates.
Новые SQL/DTO/modules должны использоваться реальным command path, без future stubs.

1. Три additive routes и strict DTO/error/decimal-string contracts§12.2:
   live OWNER, существующие cookie/Origin/CSRF/auth bounds, server-derived tenant,
   canonical same-Workspace Client/Conversation, общий CONTROL idempotency namespace.
   Saved command result отделён от свежего GET state; reauth/relation перед replay,
   replay перед новой policy/CAS. Новые Takeover/Resume дают gen+1/context+0,
   включая same-mode/new-key; replay/denial/rollback не дают mutation/Audit/jobs.
2. Новый Resume после ВСЕХ authority/connection/billing/Conversation waits:
   fixed `POST_LOCK_PRODUCT_SNAPSHOT` с одним MATERIALIZED DB clock и полной
   прежней SELECT projection → unchanged EntitlementService → canonical SQL policy
   repeat → CAS. Prepare не отклоняет scheduled activation раньше post-lock gate.
   Guarded method сохраняет task/active-unit/physical-XID/live-owner/worker exclusion;
   это не девятая SQL function. Frozen SNAPSHOT/billing_snapshot/R4 GET неизменны.
3. Public manual CONTROLLED и final TELEGRAM получают тот же post-lock snapshot
   после narrow prelock. HTTP остаётся между auth units; прежние replay probes,
   observation/SQL provider scope и five M2 routes сохраняются. Только новый admitted
   intent атомарно даёт HUMAN/gen+1/fenceNULL + прежние Message/Outbox/Job/receipt/Audit;
   context+1 только прежним material trigger. Pre0009 replay побайтно сохранён.
   Никакого второго CONTROL Audit/receipt для manual или AI restore при FAILED/UNKNOWN.
4. Оба ingress producers: connection barrier → Conversation NO KEY UPDATE → capture
   и nextval до commit. Origin берётся из earliest committed Message namespace,
   не из current state/job; absent Conversation остаётся HUMAN/gen1 до PROCESS.
   Legacy NULL не получает authority/backfill. Generation/mode/fence разделяют группы;
   late old origin не закрывает новое окно. Delayed media не обновляет capture.
   TEST consumer остаётся effects-free: stale generation/context и superseded revision
   различаются, старый committed OBSERVED replay неизменен. Backlog jobs не создаются.
5. Receipt→Audit: точный seven-column `conversation_control_receipts_audit_fk`§12.7,
   включая saved actor/context; все CONTROL components non-null, generated event,
   Audit object_version=context, supporting UNIQUE/typed tenant/client refs/RESTRICT.
   Не связывать receipt с mutable current generation и не ослаблять старые variants.
   Ровно8 ABI/security profiles:4 owner runtime capabilities;4 private, из которых
   pure fingerprint INVOKER; остальные DEFINER, asm_migrator, exact search_path,
   PUBLIC EXECUTE denied. Exact pg_proc inventory расширяется без исключений/skip.
6. Полный lock graph§12.7, включая implicit FK/triggers, сохраняется: после
   Conversation не появляется первого захвата authority/connection/state/billing/
   file/existing-job. Принятые NOWAIT/final-age/P3001/2s/5s и worker scan ABI неизменны.
   Mixed Audit backend/OpenAPI/frontend поддерживает ровно два новых typed variants;
   frontend delta — parser/type/label совместимость, без CONTROL screen/buttons.

### 0.3. Точная write allowlist

C0 разрешает **ровно36 repository paths =28 existing +8 новых** из принятого§12.10,
только в указанной цели. Таблица ниже — действующая write permission этой фазы.
Новый scope/path/изменение принятой семантики возвращается C0 с конкретным diff
и причиной до расширения; чтение исходников/references разрешено.

| Разрешённые exact paths | Необходимая дельта / symbols |
|---|---|
| `migrations/versions/0009_conversation_control.py` | Одна новая revision, fields/receipt/Audit/RLS/SQL capabilities§12.6–7 и safe downgrade; copied exact0008 definitions для restore |
| `backend/src/asm/conversations/control.py` | Новый используемый `ControlPermission`, `ControlError`, `OwnerControlService`, fingerprint/prepare/execute/read orchestration; Resume после prepare/replay/locks получает отдельный post-lock snapshot и вызывает unchanged EntitlementService |
| `backend/src/asm/conversations/http_models.py` | Четыре strict DTO§12.2, PositiveVersion и закрытые control error variants |
| `backend/src/asm/conversations/http.py` | `install_control`, три routes, existing AuthBoundary/cookie/CSRF и explicit errors |
| `backend/src/asm/foundation.py` | `create_app` installs routes; `DATABASE_SCHEMA_REVISION=0009`; exact mismatch guard для API/worker/scheduler |
| `backend/src/asm/tenancy/database.py` | Четыре typed owner methods по SQL ABI§12.7 плюс отдельный guarded fixed-query `post_lock_product_snapshot() -> RowMapping`§12.3, task/XID/owner/worker guards и узкий mapping новых control SQLSTATE; existing billing_snapshot неизменен |
| `backend/src/asm/billing/queries.py` | Только отдельный `POST_LOCK_PRODUCT_SNAPSHOT`§12.3: одна MATERIALIZED clock capture и полный coherent snapshot; frozen SNAPSHOT/R4 GET не менять |
| `backend/src/asm/messaging/http_service.py` | `OwnerMessagingService.send` вызывает final manual prelock, затем product_gate использует новый post-lock snapshot для public CONTROLLED/TELEGRAM; unchanged EntitlementService, refresh и оба replay probes сохраняются |
| `backend/src/asm/billing/models.py` | Два strict Audit variants и discriminator union; старые models/R4 semantics неизменны |
| `contracts/openapi.json` | Только generated export: новые routes/DTO/errors/Audit; five M2 routes и frozen tenancy snapshot сохранены |
| `frontend/src/billing-api.ts`; `frontend/src/BillingPanel.tsx` | Только два Audit parser/type/label variants; никаких control buttons, polling, messaging UI или маршрутов |
| `frontend/src/billing-api.test.ts`; `frontend/src/BillingPanel.test.tsx` | Mixed Audit parsing/render, unknown/extra/wrong-type rejection, прежняя pagination |
| `tests/test_m3_1_control.py` | Новый unit suite: strict bodies/decimal/hash/error union/route contract, без замены DB evidence |
| `tests/test_m3_1_control_postgres.py` | Новый actual DB suite: transitions/receipts/fence/provenance/locks/rollback/recovery, обе ingress capabilities |
| `tests/test_m3_1_control_api_postgres.py` | Новый HTTP→Auth→real PG suite: sessions/CSRF/OWNER/two tabs/product/mixed Audit/manual compatibility |
| `tests/test_m3_1_control_migrations.py` | Новый exact T0008/C0009 cycle/refusal suite и disposable migration-role controller; source/phase-specific seeding |
| `tests/test_m3_1_turns_postgres.py`; `tests/test_m3_1_migrations.py` | Сохранить TURNS assertions; явно отделить historical0008 fixture/teardown от current0009 и адаптировать только generation ожидания нового manual; frozenT archive не редактируется |
| `tests/test_m2_1_postgres.py` | Existing shared fixture cleanup: child-first control receipts/Audit перед Conversations, без CASCADE/constraints disable |
| `tests/test_postgres.py`; `tests/test_m2_1_schema_postgres.py`; `tests/test_m2_3_schema_postgres.py` | Exact current table/grant/function inventories/проверка отказа на current head; прежние historical targets/scan ABI сохраняются |
| `tests/test_tenancy_postgres.py` | Только `test_runtime_roles_policies_functions_and_platform_surface`: добавить ровно8 profiles§12.7 к exact legacy/M1/M2/M3 union; весь pg_proc query app/platform, exact-set equality, owner/search_path/PUBLIC/runtime EXECUTE и все прежние profiles сохранить |
| `tests/test_m2_2_migrations.py` | Только при необходимости current-head restoration fixture; старый0005→0006/7 cycle и assertions не заменяются новым phase |
| `tests/test_foundation.py`; `backend/src/asm/telegram/provisioning.py`; `tests/test_m2_3_setup.py` | Exact0009 readiness/binding guard; fresh-only provisioning, billing catalog/interval и owner/bot binding policy без изменения |
| `scripts/test_telegram_egress_migration.sh` | C coordinator: frozenH + сохранённый frozenT schema phase + mandatory newC phase в обоих state shards; separate archives/reports/cleanup, единый ledger600 и supervised child termination§12.8 |
| `scripts/test_telegram_egress.sh` | Explicit CONTROL schema selector с private remaining-budget request§12.8; default exactC/0009 и35-table expectation, без ослабления старых gates |
| `scripts/prepare_telegram_egress.py` | Только добавить exact0009 inventory к schema validation; historical `migration_source`/saved-plan gate остаётся0007-only, pins/source/recovery guards неизменны |
| `tests/test_telegram_egress_migration.py` | `run_control_schema_phase`/strict observed9 recovery, remaining-budget admission, phase/source mismatch tests, old historical/saved-plan refusal и reports при раннем failure/до teardown |
| `tests/test_telegram_egress_postgres.py` | Exact35 inventory, child-first cleanup, strict current E05; сохраняются6 wire+6 lifecycle, no-resend и DB/S3/HTTP assertions |
| `docs/runbooks/M2_TELEGRAM_LOCAL_TEST.md` | Только ссылка на отдельные frozen0007/TURNS0008/CONTROL0009 LOCAL gates; historical evidence/pins/owner instructions не менять |
| `docs/tasks/M3_CONTRACT.md` | Только согласованные implementation уточнения§12; неизменный TURNS prefix, без SHA-only commits |

`tests/test_m2_2_migrations.py` меняется только при фактической необходимости
current-head restoration; прежний historical cycle сохраняется. Остальные старые
test adaptations также должны иметь конкретную причину: new manual generation,
exact current head/inventory или child-first cleanup, без ослабления assertions.
`docs/tasks/M3_CONTRACT.md` — только согласованные implementation уточнения§12
вместе с содержательным кодом; весь TURNS prefix неизменен. Переписывать документ
ради SHA/status не требуется. Generated OpenAPI получать штатным export.

Applied0001–0008, canon/manifest, TASK_REGISTER/M3_HANDOFF/AGENTS (владелец C0),
tenancy.v1, auth middleware/settings, EntitlementService, conversations/turns.py,
messaging worker/commands/models/codec/webhook, transport/config/relay,
dependencies/lockfiles, Compose/workflows/images/pins — вне write scope.
Нет параллельного authoring C1/C2/C5/C6/C8. Они получают отдельный review готового
candidate; новый путь/функция не добавляется как молчаливая «починка теста».

### 0.4. Миграция, source/schema и неизменные budgets

**Теперь разрешена одна новая миграция** `0009_conversation_control.py`,
revision=`0009`, down_revision=`0008`. Очередь назначена C0 по принятому C2 design.
Все DDL/body replacements/restore definitions для этой дельты — только в0009.
Одна новая receipt table: exact34→35 inventory, nullable metadata без DEFAULT/
backfill. Upgrade проверяет0008 HUMAN/gen1 и Turn gen1, сохраняет старые rows,
receipts/counters/UNKNOWN/private files; unexpected state означает отказ, не reset.

Cutover только в disposable LOCAL/TEST: drain API/worker/scheduler/ingress,
закрытие pools/transactions, отдельный migrator. CONTROL-clean0009→0008 допускает
populated TURNS/M2; каждый новый receipt/Audit/capture/AI/gen≠1/fence blocker
даёт55000 до destructive DDL. Восстановить exact0008 definitions/grants и полный
fingerprint; отказ0008→0007 остаётся независимым. Новые данные ради downgrade не удалять.
Это не production rollout; Expand/Migrate/Contract ADR217 сохраняется.

Матрица§12.8 обязательна без переименования исторических доказательств:

| Phase | Source/schema и результат |
|---|---|
| Historical6 shards normal/Docker29 | Frozen P/O/H0007, прежние31-table receipts/operator/UNKNOWN-wire1 proof |
| Retained TURNS, оба state shards | Detached immutable T: `--schema-upgrade H T`, отдельный0007→0008 committed/exit86/fresh observer/recovery proof |
| CONTROL default | Future exact implementation C/0009, отдельные LOCAL/TEST,35 tables, прежние6 wire+6 lifecycle/строгийE05 |
| New CONTROL, оба state shards | Другая fresh DB/volume, baseline T/0008; C migration-role controller, clean populated8→9→8 cycle, отдельный committed0009/exit86/fresh observer, exactC/9 forward/restart |

**T всегда ea1ae98c; C — будущий implementation checkout, не R1/этот docs commit.**
T/9 и C/8 rejected; unknown/unreadable/multiple heads→STOP. API/worker/scheduler
на recovery используют один exact runtime image/source. Historical saved-plan и
`migration_source` остаются0007-only; selector C
`--control-schema-upgrade T C <private-budget-request>` не расширяет старый guard.
Fixed T inventory содержит все34 qualified tables/старые columns; forward сравнивает
33 data tables, Alembic8→9 и новыеNULL/empty receipt отдельно; clean reverse — полный34
fingerprint+definitions/grants, same-schema C — полный35. Не dynamic intersection.

Один monotonic prepare ledger600s учитывает весь supervised retained-T shell
(prepare/runtime/cleanup) и все schema archive/build/reuse-verification интервалы,
без double count/потерянной ранней подготовки. Process-local `migration_budget`
не наследуется: T watchdog получает remaining, C получает только оставшееся через
private one-time0600 request с exactT/C/phase/charged seconds/absolute deadline.
Child проверяет owner/format/source/phase и elapsed handoff; no reset/nested/fresh600,
без patch frozenT или изменения global helper. Bounded stop всей process group,
wait, owned cleanup и reports при source/build/probe failure ДО runtime try;
T reports копируются до удаления checkout. Archive/image reuse — только verified bytes.

Штатные9 jobs/clean-source gates, state25min включая setup/upload/cleanup,
foundation35min, prepare600s, historical held180s не меняются. Bounds:
build480/controller120/migration-probe30/drain60/teardown90/normal40s;
transport5/10/20s,lease30s,DB2/5s,retries5/15min. Actual stage timings/ledger —
обязательное evidence будущего C6 implementation review. Если не помещается,
вернуть C0 первичный failure/timing и конкретный scope diff; не удалять proof,
не повышать timeout, не подменять actual PG mocks и не делать rerun-to-green.

### 0.5. Проверки и evidence готового candidate

Разрешены необходимые unit/actual PostgreSQL/HTTP→Auth→PG/private-S3/worker/
Docker проверки в disposable LOCAL/TEST через штатный harness и CI обычного push.
**Все22 scenario rows§12.11 обязательны; на момент этой выдачи CONTROL NOT EXECUTED.**
Результаты старого docs CI не заменяют новые проверки на implementation SHA.

Особо сохранить доказательства исправленных findings:

- Subscription и service-mode expiry И scheduled activation независимо для Resume,
  public CONTROLLED/manual TELEGRAM: actual Conversation-only NO KEY UPDATE blocker
  без mutation, наблюдаемые waiting PID/pg_locks до границы и release после неё,
  half-open boundaries в DB2/5s. Один полный post-lock snapshot; reauth/denial/replay
  без control/context/Audit writes, replay без новой projection, R4 unchanged.
- Полный app/platform pg_proc exact-set legacy/M1/M2/M3 union + ровно8 profiles;
  per-function owner/search_path/PUBLIC/runtime EXECUTE и private rejection.
- Два независимых raw PG negatives: иной действительный member actor и иной
  locally coherent positive saved context. Все прочие CHECKs/refs valid; каждый
  даёт23503 именно `conversation_control_receipts_audit_fk`. Positive command/replay,
  fault между writes и поздний deferred failure откатывают все partial writes.

Остальные§12.11 cases также исполняются: transitions/two tabs/security/product/
overflow/ACK loss; atomic manual/replay/refresh races; оба producers и absent/
duplicate-first/lower uncommitted origin; grouping/late media/stale TEST consumer;
FK/maintenance/savepoint/B-progress; migrations/refusal/preservation; оба actual
state shards с0009 commit-loss/recovery; budget/failure retention и M2 regressions.
Существующие TURNS tests не урезать. Deterministic barriers/DB observations вместо
вероятностного sleep; не backdate rows/deadlines и не вводить runtime test toggle.

Штатные entrypoints: `pytest -q tests/test_m3_1_control.py`; три новых actual PG/API/
migration suites через existing integration runner; `sh scripts/ci.sh`,
`sh scripts/test_browser.sh` и существующий полный9-job CI. Конкретные commands,
их environment/source и действительный результат обязательны в receipt. Тесты
должны проверять поведение/инварианты, не копию собственной реализации.

### 0.6. Возврат C0 и следующие границы

Один законченный candidate в этом же PR. Логические implementation commits
допустимы; status-only commits/новые PR на подпункты не нужны. Перед push сверить
branch/main, не перетирать чужие изменения. По завершении держать exact head
для review до сведённого решения C0.

Вернуть **один PR comment**:

1. Full head/parent/tree, acceptedT и C0 continuation; changed paths/diff относительно
   continuation,36-path scope proof, неизменные0001–0008/canon/pins/TURNS prefix.
2. Реализованные routes/DTO/SQL ABI/profiles/0009/Audit и причины каждой адаптации
   старых fixtures; все substantive contract уточнения/оставшиеся OPEN вопросы.
3. Матрица22 rows → exact case/command/SHA/result: раздельно unit, actual PG/API,
   private S3/wire, frozenH, retainedT и newC evidence. Неисполненное так и пометить.
4. Current CI run/attempt/jobs/clean-source, tested checkout/ordered parents/tree,
   source/image manifests/IDs; phase-separated reports, committed9 marker/exit86,
   fresh observer/DB identities, preserved receipts/files, recovery/restarted IDs.
5. Actual stage timings/charged600 ledger/state+foundation budgets, early failure
   retention/process-group cleanup и пределы результата. Сохранять первичную ошибку;
   исправления в scope доводить до finished candidate, нехватку среды не выдавать за PASS.

После candidate C0 выдаёт implementation reviews: C1(API/product/Audit),
C2(DB/receipt/locks/migration), C6(source/schema/budget/recovery), затем независимый
C8 по новому риску. Contract PASS не заменяет их. Только после приёмки C0 —
разрешение пользователю merge и отдельная сверка actual main/CI.

CONTROL покрывает A07 и согласованные context/fence/A11 части. Полные GUARDS
A04–A06/action-send admission/in-flight, native частьA08, EscalationA09, ConsoleA10,
общийA12 и M4 не выданы. Native-owner **NOT VERIFIED**; automatic native takeover,
material edit/delete/codec/provenance остаются отдельным gate. Старые ignored events
не reprocess-ить. AI mode не означает работающую модель или public allow_send.

VM/SSH/live Telegram/рабочие DB-S3/owner binding/ACK/TEST продление/deploy/merge
не входят в эту задачу. Новых аккаунтов/tokens/данных или действий пользователя
для LOCAL/TEST implementation не требуется. M3 остаётся IN_PROGRESS.


</details>

<details>
<summary>История CONTROL-CONTRACT до R1; завершено, текущая implementation выдача — §0 выше</summary>

## История выдачи C0 — C3-M3.1-CONTROL-CONTRACT (завершено)

Дата: 2026-10-10. Это следующий срез M3.1 после принятого TURNS,
а не новый milestone. Один новый Draft PR на ветке `c3/m3-1-control`;
C3 — единственный автор следующей дельты, C0 владеет этим handoff и реестром.

### CONTRACT.1. Принятый TURNS и точный старт

[PR26](https://github.com/Elefesys/ai-service-manager/pull/26) слит пользователем
2026-10-10T15:12:11Z. **M3.1-TURNS — INTEGRATED / VERIFIED в LOCAL/TEST scope**
A01/A02/context-часть A03/A11; весь M3 остаётся IN_PROGRESS.

- Accepted main/base: **`ea1ae98ce9e5e26d5d0d14f3e6d278ecb9efbbad`**.
- Tree: `11ad506a859db155973f965bcdd0cebc7bc0d5ed`.
- Ordered parents: `754f1c883e5a94a7fc9e729af2605424f949ba33` +
  `cd277b195396e76d914364903f42e1e52f21e1ff`.
- Дерево совпало с reviewed head и tested merge
  `9694adf33e6fa0d5342083ac7fd26f9e25c1e6f5`.
- [Push/main CI38062653562 attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/38062653562):
  **9/9 jobs и9/9 clean-source gates SUCCESS**, завершён15:34:05Z.
  Foundation114243888408:937 unit/462 integration,111 frontend PASS;
  browser114243888385:27 PASS. Checkout logs показывают actual main.
- [C0 acceptance](https://github.com/Elefesys/ai-service-manager/pull/26#issuecomment-6098927722),
  [C8 PASS](https://github.com/Elefesys/ai-service-manager/pull/26#issuecomment-6098859899),
  [C2 PASS](https://github.com/Elefesys/ai-service-manager/pull/26#issuecomment-6098377195),
  [C6 PASS](https://github.com/Elefesys/ai-service-manager/pull/26#issuecomment-6098346591).
  C1 PASS6097008758 относится к b301; неизменные callers/API + SQL delta
  проверены в последующих C2/C8 scopes, нового C1 PASS на другом SHA не заявляем.

C0 проверил merge/parents/tree,9 main jobs/gates и foundation/browser logs.
Собственного нового PG/Docker/live запуска при post-merge приёмке нет.
Actual runtime evidence — штатные PR/main runners. Прежние пять implementation
findings CLOSED; CONTRACT findings01–04 CLOSED; приёмка не расширена до CONTROL.

C0 создаёт **один содержательный preparation commit** от accepted main:
меняются только `docs/TASK_REGISTER.md` и `docs/tasks/M3_HANDOFF.md`.
Его full continuation SHA/tree и новый PR публикуются в PR metadata.
C3 начинает от этого exact continuation в отдельном checkout,
проверив parent=accepted main, эти два paths и неизменность runtime/contract.
Не писать в закрытый PR26/старую ветку; main не менять, без reset/rebase/force.

### CONTRACT.2. Почему контракт CONTROL до кода

Текущий [M3_CONTRACT §§8–9](M3_CONTRACT.md) принимает семантические границы,
но прямо требует отдельно согласовать owner routes/DTO/Audit с C1,
Resume ingress serialization/fencing с C2 и provenance native intervention.
TURNS не фиксировал конкретные CONTROL request/response/error/receipt schemas
и0009 source/schema cutover. Нельзя вывести их из старого общего PASS.

**Текущая задача: C3-M3.1-CONTROL-CONTRACT (часть M3.1-CONTROL).**
Подготовить один законченный, пригодный для реализации раздел
`## 12. CONTROL — owner commands, activation fence и границы native intervention`
в **том же** `docs/tasks/M3_CONTRACT.md`; не заводить второй технический контракт.

Accepted TURNS blob `5e87375852331523491a47926b9c5bd49946c157` —
точный неизменный prefix: существующий текст §§1–11, включая вступление,
не переписывать. Дополнение явно относится к следующему срезу;
исторические0007/0008/H/I формулировки остаются TURNS evidence.
Нужное изменение ранее принятой семантики вернуть C0 как отдельное противоречие
с последствиями, а не скрывать редактурой старых разделов.

### CONTRACT.3. Обязательные решения и содержание раздела12

Сначала прочитать AGENTS, текущий реестр, весь M3_CONTRACT и применимый canon:
Spec §§4.10,5.1–5.14,14.11,18.5–18.8,18.14,24.7,25.7;
ADR022–026,121–128,180,197–198,217,267,272; MVP GJ-G/GJ-J;
Roadmap M3; Implementation Plan M3.1/M3.2; M2_CONTRACT §§2–5/9–10.
Originals/manifest не менять. Читать реальный0008/runtime, не только планы.

1. **Owner command/API contract.** Предложить точные read/Takeover/Resume
   routes и строгие request/response/error DTO, expected-state/CAS fields,
   idempotency namespace/body/fingerprint, immutable receipt и Audit variants.
   Перечислить порядок live OWNER/auth/session/Origin/CSRF, tenant/client,
   product policy, expected-state и replay/conflict checks.
   Отдельная матрица read/Takeover/Resume/manual: нужны ли channel rights,
   open reply window или refresh, что происходит при unavailable channel,
   suspended/expired product/role revocation и почему. Не копировать send
   gate механически в Takeover и не вводить обход действующей product policy.
   Спорные различия вернуть C0/C1 до кода. Permissions не добавлять в frozen
   tenancy.v1 молча. Числовые версии сохранить точными на JSON/JS границе.
2. **Control transitions.** HUMAN default existing/new; AI только после
   явно принятого Resume. Новая принятая Takeover/Resume, включая повтор
   желаемого режима с новым key, фиксирует новое control_generation согласно§8;
   exact replay —0 generation/context/Audit. Новая команда на устаревшем
   expected state — явный отказ; same key/different body — conflict.
   Для replay определить сохранённый command result отдельно от свежего state,
   чтобы старый receipt не выглядел текущим режимом.
   Таблица HUMAN/AI × команды × stale/replay/conflict/denied/rollback/crash,
   две вкладки и параллельные команды; overflow — отказ, не reset/wrap.
   Takeover/Resume без semantic Message дают context+0; generation отдельно.
3. **Атомарный Console manual takeover.** Только новый успешно admitted
   M2 manual intent устанавливает HUMAN и generation+1 в той же transaction,
   что прежние Message/Outbox/Job/receipt/Audit; context по-прежнему+1.
   Receipt/fingerprint M2 и пять существующих API не ломать.
   Replay сохранённого intent, включая pre0009, не повторяет takeover/Audit;
   rejected/stale/product/authority failure ничего не захватывает.
   Уже PENDING/DISPATCHING/UNKNOWN и дальнейший terminal reconciliation
   не объявляются отменёнными и не возвращают AI после FAILED/UNKNOWN.
   Доказать lock order с существующими двухфазными prepare/refresh/request_text;
   сеть остаётся вне business transaction.
4. **Resume fence до eligibility.** Дать точный DB алгоритм, columns/refs,
   generation/fence capture и predicates для ОБОИХ producers.
   Existing connection/authority locks до conversation; conversation
   serialization до выдачи ingress sequence и Resume fence, без обратного edge.
   Sequence allocation не считать commit order. Ingress до Resume, ещё без
   materialized Message, old HUMAN Turn, legacy NULL и delayed media readiness
   не получают новую authority. Случаи ещё не созданной conversation,
   duplicate-first/rollback, uncommitted lower ingress и simultaneous Resume
   разобрать отдельно. Группа не пересекает activation generation.
   Определить работу старых durable jobs/TEST receipt и поздних результатов;
   не проставлять им текущий generation задним числом, не ставить backlog jobs.
5. **Минимальная0009/DB contract.** После проверки актуального Alembic head
   C0 резервирует `0009_conversation_control.py`, revision0009,
   down_revision0008; это резерв для design/C2, **не разрешение DDL сейчас**.
   Перечислить только реально нужные columns/tables/indexes/FK/private helpers,
   signatures/privileges/RLS/Audit deltas и полный lock graph, включая triggers,
   deferred FK, manual hooks, ingress и background writers.
   Сопоставить reuse/новый immutable command receipt с точными M2 constraints;
   не создавать универсальный future ledger/workflow/AI entity.
   Applied0001–0008 неизменны. Описать clean и populated upgrade/downgrade:
   сохранённые HUMAN/gen/context/Turn/consumer/M2 rows, отказ до destructive DDL,
   отсутствие backfill/action authority и при каких новых данных downgrade
   уже нельзя безопасно выполнить.
6. **Source/schema pairing0008→0009.** Новый раздел дополняет TURNS §10:
   frozen historical P/O/H0007 остаются своими source/images/receipts;
   принятый TURNS source `ea1ae98ce9e5e26d5d0d14f3e6d278ecb9efbbad`/0008 —
   отдельный predecessor, будущий CONTROL candidate/0009 — отдельный I.
   Указать exact readiness guards/fixtures/default lanes и план реального
   0008→0009 сценария в обоих normal/Docker29 state shards, сохранив прежний
   0007→0008 proof и его meaning. Fresh containers/volumes/role/schema,
   drain API/worker/scheduler/pools, committed upgrade lost result,
   observed revision до recovery choice, clean cycle/populated refusal,
   exact qualified inventories/M2+TURNS projections/source/image evidence.
   Не переписывать historical source на newest/main, не менять workflow,
   Compose/pins/limits и не объявлять LOCAL cutover production rollout.
   Обосновать bounded cost в существующих budgets; конкретную несовместимость
   вернуть C0/C6, без импровизированного упрощения gates.
7. **Native/edit/delete provenance.** Live observability native-owner
   остаётся **NOT VERIFIED**, account evidence не получено, прежний TEST
   interval истёк. Решение C0 для ближайшей разработки: обязательны явный
   Console Takeover и atomic manual takeover; автоматический native takeover
   не реализуется/не заявляется подтверждённым до отдельного provenance/account
   решения C0. Это конкретная невыданная часть A08, не закрытие всего M3.
   Разделить owner/own echo/other bot/offline/unsupported/pre-Resume delayed
   updates и описать, какое evidence позволит безопасно включить native path.
   Не присваивать outgoing owner Client identity, не менять V1 fingerprints
   и не переисполнять исторические IGNORED. Material edit/delete также требуют
   отдельного принятого codec/provenance: документировать границу и необходимый
   следующий gate, без скрытого включения в текущий write scope.
8. **Граница GUARDS и будущего UI.** CONTROL сохраняет mode/generation/fence
   и owner command authority; не утверждать полный automated action/send
   admission, takeover→resume stale-worker proof или recall in-flight.
   Они относятся к следующему GUARDS. Для текущего TEST consumer описать
   инвалидацию/STALE/SUPERSEDED без внешних sends, не создавать AI executor.
   Read DTO может честно отражать existing DISPATCHING/UNKNOWN, не выдавая
   UNKNOWN за CANCELLED. C5 начинает от принятого API позже; новая Console UI,
   Escalation, M4/AI/gateway/payments/booking не входят.
9. **Implementation proposal и evidence matrix.** Дать exact future path
   allowlist с причиной каждой строки, public ABI/data migration delta,
   current symbols и proposed symbols. Указать, какие gates являются
   CONTROL (в частности A07 и relevant context/fence parts), какие остаются
   GUARDS/A04–A06 и native A08, а не расширять VERIFIED.
   Для каждого критического перехода — настоящий command/DB/worker test,
   deterministic barrier/crash boundary, expected durable outcome/replay,
   двухвкладочный CAS/role-revoke/CSRF/tenant/other-client negatives,
   HTTP-outside-transaction, no-backlog и preserved M2/TURNS regression.
   Пока это **план checks**, не executed PASS.

### CONTRACT.4. Точный write scope текущей фазы

| Path | Разрешённая дельта |
|---|---|
| `docs/tasks/M3_CONTRACT.md` | Только append раздела12 и его подразделов после неизменного принятого prefix |

В этой фазе runtime/SQL/tests/contracts snapshots/generated OpenAPI,
frontend/infra/workflows/Compose/pins/lockfiles/runbooks и applied migrations
не менять. TASK_REGISTER/M3_HANDOFF/AGENTS/canon — C0-owned.
C3 не создаёт0009, новые tables/functions/DTO/routes или placeholder modules.
Нет параллельного authoring C1/C2/C6/C8; они получают адресные review поручения
после готового proposal. Не отправлять другим чатам недоговорённые куски вместо
одного законченного contract candidate.

### CONTRACT.5. Проверка и возврат

Сверить main/base/parent, неизменный original contract prefix/blob, один changed
path относительно continuation, diff whitespace, links/symbol references и
согласованность таблиц переходов/lock order/permissions/source/schema matrix.
Прочитанное existing CI не выдавать за исполнение будущего CONTROL.
Новые runtime tests для Markdown не писать; штатный автоматический PR CI/gates
не менять и не rerun-to-green. Его source/run/result указать честно.

Один finished candidate в этом же Draft PR. Вернуть C0 один comment:
- exact head/parent/tree и diff от continuation; hash/prefix proof;
- решения раздела12 по пунктам выше и remaining конкретные вопросы,
  proposed0009/ABI/paths/guard changes с причинами;
- команды/фактические результаты, ссылки на current CI/gates и предел evidence;
- explicit native NOT VERIFIED и границу CONTROL/GUARDS;
- готовность для C1 API/Audit/policy и C2 DB/locks/receipt/migration reviews;
  C6 адресно проверит новый source/schema compatibility design при необходимости.

После этих согласований C0 принимает CONTROL contract и выдаёт **implementation
в том же PR/ветке** с точными разрешёнными paths и0009. До этого runtime
не начинается. После реализации — профильные reviews, независимый C8,
приёмка/пользовательский merge/actual main CI. Никаких новых PR на абзац.

VM/SSH/live Telegram/рабочие DB-S3/owner binding/ACK/TEST продление/deploy/merge
не выполнять. Новых данных, аккаунтов, tokens, прайса или действий пользователя
для текущей документационной задачи не требуется.

</details>

<details>
<summary>История выдачи TURNS; закрыто actual merge/main CI, текущая задача находится выше</summary>

## История выдачи C0 — C3-M3.1-TURNS (завершено)

Дата выдачи и приёмки CONTRACT: 2026-10-10.
Repository: `Elefesys/ai-service-manager`. Продолжать существующие
Draft [PR26](https://github.com/Elefesys/ai-service-manager/pull/26) и ветку
`c3/m3-1-turns` в отдельном checkout C3; integration target — main.
Это одна implementation-задача, а не начало CONTROL/GUARDS или всего M3.

### 0.1. Принятый контракт, основания и точный старт

**C0 принимает CONTRACT-R2** на
`4f9d32e9d67308da8062dc12aeb4839e06c850cb`,
tree `25c4bf9f4039141f4ce8c03c1edfb18196deb790`,
blob `5e87375852331523491a47926b9c5bd49946c157`.
Единственный parent R2: `b99e119757d52ee8bd00a51093f63bada5f95823`.
Accepted main/implementation base остаётся
`754f1c883e5a94a7fc9e729af2605424f949ba33`; main ещё не содержит M3.

Основания: [final C3 receipt](https://github.com/Elefesys/ai-service-manager/pull/26#issuecomment-6094572773),
[C1 scoped PASS](https://github.com/Elefesys/ai-service-manager/pull/26#issuecomment-6094967481),
[C2 CONTRACT/DB PASS](https://github.com/Elefesys/ai-service-manager/pull/26#issuecomment-6095018013).
Оба review относятся exact R2; остаточных findings не заявлено.
[CI38030244030 attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/38030244030)
—9/9 SUCCESS и9/9 clean-source gates. Прочитанный C0 foundation checkout:
`5403d868ffbcefa9489d83bcc8d674da394b2984`, parents accepted main + R2,
tree равен R2. C0 ранее сверил own-path/parent/tree/blob, unchanged §§6/9,
единственное дополнение barrier §8 и exact31 inventory.

**C2-M3-CONTRACT-01–04/P2 CLOSED в contract-review scope.**
Их assertions полностью сохраняются как implementation gates; текущий0007
не объявляется реализующим новые механизмы. M3 runtime/DDL ещё не VERIFIED.
Принятый [pairing design C0/C6](https://github.com/Elefesys/ai-service-manager/pull/26#issuecomment-6094458702)
входит в R2. Выбраны D2с/G10с/M15с/N32, cap25с, HUMAN/gen1.

Этот содержательный C0 handoff добавляется одним commit поверх R2, меняя только
TASK_REGISTER и M3_HANDOFF. Полный **continuation SHA и tree опубликованы в PR26
в текущем C0-поручении**; C3 сначала fast-forward к этому exact SHA и сверяет
его parent=R2, два разрешённых C0 paths и неизменный contract blob. Не начинать
от случайного branch tip, не reset/rebase/force, не создавать второй PR.
Номер собственного SHA не вписывается дополнительным status-only commit.
Вступление M3_CONTRACT отражает момент передачи R2: перечисленные там pending
review/code gates заменены этим verdict и явной выдачей TURNS; reviewed bytes
контракта сохраняются для exact evidence.

Прочитать AGENTS, текущий TASK_REGISTER, весь [M3_CONTRACT](M3_CONTRACT.md),
оба final review, M2_CONTRACT §§2–5/9–10, действующие SQL0005–0007,
messaging/files/Telegram/worker и egress paths по §10. Канон — Spec §§4.10,
5.1–5.14,14.11,18.5–18.8,18.14,24.7,25.7; ADR022–026,121–128,180,197–198,
217,267,272; MVP GJ-G/GJ-J, Roadmap M3, Implementation Plan M3.1/M3.2.
Не воспроизводить закрытые M2 operator-поручения.

### 0.2. Результат и единственный исполнитель

**C3 реализует M3.1-TURNS**, включая Python, новую0008 и только перечисленную
совместимость. C2 проверит DDL/RLS/locks/upgrade готового candidate; C1 — затронутые
callers/versions/API; C6/C8 получают отдельные scoped задания C0 по готовому diff.
Параллельного authoring C2/C6 в этих файлах сейчас не выдано.

Ожидаемый результат: fresh CONTROLLED/Telegram text/photo группируются в durable
Turn, deadlines/readiness/revision переживают restart, stale работа безопасна;
внутренний детерминированный TEST consumer сохраняет один canonical result
через реальный DB/worker path и не производит внешнего эффекта.
Existing/new conversations HUMAN/gen1; takeover/resume/control API в этом срезе нет.

Реализовать принятые §§2–7/10/11, в частности:

1. Trusted nullable Inbox ingress pair без backfill, immutable origin/membership
   и SHARE-before-mark barrier ОБОИХ producers с post-barrier READ COMMITTED/
   VOLATILE origin selection. Legacy/conflicting namespace priority не меняет
   M2 winner/error/fingerprint. Все Inbox status writers используют допустимый
   NO KEY UPDATE, включая inherited reschedule/recovery.
2. Три таблицы Turn/member/private consumer receipt с canonical composite refs,
   FORCE RLS/RESTRICT/narrow privileges, partial single-COLLECTING UNIQUE.
   Existing Conversation.version — единый context counter; control_generation,
   Turn.revision, Message/File/connection versions не смешивать.
3. PROCESS_TURN GROUP/MEDIA/TEST_CONSUME, durable available_at/deadlines,
   revision fencing, COMPLETE/PARTIAL/WAIT_EXPIRED и поздний file outcome.
   TEST snapshot использует private file refs/statuses, не bytes/signed URLs.
4. Single-candidate claim/recovery transactions по §5.2: SKIP LOCKED + полный
   NOWAIT preflight/savepoint rollback, bounded cursor/scan_until, continuation
   после100 candidates, освобождение всех locks на BUSY, первичная ошибка как cause.
   Public claim_job/recover_expired и прежние kind/result contracts сохраняются.
   Полный graph §5.3 охватывает implicit/deferred FK, оба reschedule overloads,
   retry/exhaustion, begin/finish rejection, file failure/success и recovery UNKNOWN.
   Supporting UNIQUE не включает mutable identity fields, усиливающие row locks.
5. Один material increment за каждый факт из §6 во ВСЕХ writers; replay/rollback0.
   SUPERSEDED проверяется до retry/FAILED во всех Turn terminal paths.
   Private immutable receipt привязан к typed canonical job и winning claim;
   отдельный узкий read-only terminal replay после lost ACK не ослабляет
   live claim/XID mutation admission. Saved replay читает один committed snapshot.
6. Schema/source разделение из §10 реализуется вместе с0008: candidate не может
   пройти за счёт одного frozen historical H. Минимальная runbook дельта объясняет
   границу synthetic historical0007 и LOCAL schema phase, не выдаёт VM updater.

### 0.3. Точная write allowlist и ограничения

C0 разрешает **ровно следующие26 repository paths**, только для целей ниже.
Чтение references разрешено. Новые пути, контрактные изменения или невместимость
выбранного механизма возвращаются C0 с конкретным diff/причиной до расширения.

| Разрешённые exact paths | Ограниченный scope |
|---|---|
| `backend/src/asm/conversations/__init__.py`; `backend/src/asm/conversations/turns.py` | Используемый Turn/TEST consumer domain; без будущих пустых модулей |
| `backend/src/asm/messaging/database.py`; `backend/src/asm/messaging/worker.py`; `backend/src/asm/messaging/results.py`; `backend/src/asm/messaging/models.py`; `backend/src/asm/messaging/errors.py` | PROCESS_TURN, private scan/replay и typed worker integration; прежние public shapes/authority сохраняются |
| `migrations/versions/0008_conversation_turns.py` | Единственная новая revision0008, predecessor0007; все новые SQL/constraints/grants и replacements прежних functions здесь |
| `tests/test_m3_1_turns.py`; `tests/test_m3_1_turns_postgres.py`; `tests/test_m3_1_migrations.py` | Новые адресные behavior/concurrency/migration tests; последний также schema-phase seed/verification entrypoint |
| `backend/src/asm/foundation.py`; `tests/test_foundation.py` | Только exact runtime0008/mismatch, сохранив tenancy.v1 revision0003 и прочие capability checks |
| `backend/src/asm/telegram/provisioning.py`; `tests/test_m2_3_setup.py` | Exact binding head0008/wrong-head отказ до обоих initializer, без смены product/billing/binding policy |
| `tests/test_m2_1_postgres.py` | Scoped child-first cleanup receipt/jobs/member/Turn refs, без CASCADE/disable constraints |
| `tests/test_postgres.py`; `tests/test_m2_1_schema_postgres.py`; `tests/test_m2_2_migrations.py`; `tests/test_m2_3_schema_postgres.py` | Exact inventories/cycles/permissions и revision-appropriate historical scan fixtures; исходные assertions сохраняются |
| `scripts/test_telegram_egress_migration.sh` | Frozen-H dispatch, обязательная schema phase в двух state shards, отдельные reports/source/clean proofs |
| `scripts/test_telegram_egress.sh` | Explicit schema selector/source-image pairing, default candidate0008 и отдельный LOCAL upgrade |
| `scripts/prepare_telegram_egress.py` | Historical-only0007 guard initial/saved paths; exact revision/name sets; прежние receipts/provenance/recovery сохранены |
| `tests/test_telegram_egress_migration.py` | Candidate helper negative/regressions, bounded schema orchestration/report assertions |
| `tests/test_telegram_egress_postgres.py` | Exact inventory/current fixture stabilization/child-first cleanup; H fixture frozen |
| `docs/runbooks/M2_TELEGRAM_LOCAL_TEST.md` | Только historical/schema boundary и ссылка на принятый M3 contract; старые receipts/pins/history не переписывать |

Migrations0001–0007, reviewed M3_CONTRACT, canonical architecture/manifest,
TASK_REGISTER/M3_HANDOFF (владение C0), .github/workflows, compose/egress overlays,
Dockerfile/locks, TelegramClient/config/transport, frontend/OpenAPI и публичные
owner routes/DTO вне write scope. Shared revision scripts не менять отдельно.
Новые env/API/brokers, backfill истории, CONTROL/GUARDS/ESCALATION/CONSOLE, AI/M4,
native/edit/delete reinterpretation, платные вызовы и production rollout не входят.

### 0.4. Миграция и source/schema gates

C0 подтверждает назначенный C2 резерв: filename0008_conversation_turns.py,
revision0008/down_revision0007, одна линейная цепочка. При другом actual head
сначала вернуть расхождение C0; applied migrations не редактировать.
DDL выполняется migration identity; runtime не получает DDL/BYPASSRLS/owner.
Upgrade на чистой и принятой0007 сохраняет M2 данные/versions/receipts/UNKNOWN/files;
legacy ingress NULL, без исторических Turns/consumer jobs/IGNORED replay.

Закреплённые pins из §10:
P=`0b7e24ee425ebb429bf87dfe382cbd3fab883028`;
O=`80e51c43e31541940f1ccf18b8281adf1a061748`;
H=`754f1c883e5a94a7fc9e729af2605424f949ba33`.
I — будущий actual implementation/tested source, не текущий docs continuation.
В reports различать PR head, tested checkout/parents/tree и image source SHA/ID;
совпадение tree не заменяет source/image byte proof.

- Historical H harness/fixtures неизменны: P0007→H0007 и прежний rollback,
  explicit operator P/O, все6 normal/Docker29 intent/image/state shards.
  До cleanup сохранить отдельные historical reports/source archive/proofs.
- Default candidate E01–E05 исполняет изменённый I на paired0008; schema phase
  обязательна в обоих state shards, с отдельными project/state/LOCAL DB.
  Тестовый controller/migrator I на0007 не означает runtime/consumer I на0007.
- До cutover drain API/worker/**scheduler**, закрыть old fixture pools/transactions.
  После commit/lost ACK сначала actual revision;0008 обслуживает только I/0008.
  Старый runtime разрешён только после доказанного чистого downgrade до0007.
- Expected revision/name set фиксирован фазой/source: exact31/exact34.
  Historical JSON/hash/receipt формат неизменен; same-schema полные fingerprints,
  cross-schema fixed-H M2 column projection и отдельная проверка metadata/defaults.
  Populated refusal каждого blocker происходит до destructive DDL, без удаления
  M3/marked rows ради чистого cycle; schema/data/functions/grants сохраняются.
- Candidate helper initial и saved resume/preflight/rollback отвергают несовместимое
  pairing до build/recreate/journal; STOP не меняет private bytes/data/container IDs.
  I coverage обязателен, H PASS его не подменяет. Historical0005/0006/0007 fixtures
  используют capabilities именно своей revision, без permissive readiness fallback.

LOCAL/TEST drain не меняет production EXPAND→compatible code→migrate→CONTRACT.
Достаточность существующих budgets доказывается actual исполнением; нельзя
исправлять failure ростом timeout/retry, skip или ослаблением assertions/gates.

### 0.5. Проверки, критерии и evidence

Разрешены необходимые локальные unit/реальные PostgreSQL/private-S3/worker проверки
в disposable LOCAL/TEST, Docker штатного test harness и штатный CI от обычного push.
Не использовать рабочие DB/S3/VM или живой Telegram. Не менять сами workflows/
Compose/budgets. Тесты нужны на поведение/инварианты, а не на совпадение реализации
с собственной копией алгоритма. HTTP/wait/consumer compute вне business transaction.

Обязательны все адресные assertions принятого Contract §11 и final C1/C2 reviews:

| Gate этого среза | Минимальное реальное доказательство |
|---|---|
| A01 / grouping | D/G/M/N и точные границы; text/photo/caption/album; duplicate/conflict/late/out-of-order; sealed membership/deadlines неизменны |
| A02 / readiness/restart | Restart до/после membership/seal/file/receipt commit; COMPLETE/PARTIAL/WAIT_EXPIRED/late terminal; два workers/один committed receipt |
| Finding01 implementation | Оба producers: меньший uncommitted I1, committed I2, commit/rollback I1; fresh/legacy/conflicting namespace; origin immutable; non-READ-COMMITTED rejection и FK/worker deadlock negatives |
| Finding02 implementation | Exhausted FETCH/SEND A с blocked conversation пропускается ради B, включая same connection; >100 prefix/continuation/unlock/restart; concurrent recovery; BUSY release ВСЕХ locks без effects; SUPERSEDED в каждом terminal path, первичная ошибка сохранена |
| Finding03 implementation | Receipt+SUCCEEDED/lost ACK/expiry exact replay; forged/NULL/foreign/mismatched/losing token/direct SELECT-DML rejection; A expired→B committed→late A rejected; uncommitted miss и concurrent snapshot/terminal race |
| A03, только context часть | Все writers §6 дают ровно1, replay/read/refresh/retry/rollback0; Telegram/CONTROLLED эквивалентны; stale context/generation → STALE, другая Turn revision → SUPERSEDED; без action authority |
| A11 / isolation/migration | Clean head и0007 upgrade; legacy PENDING без Message + duplicate-first; fresh Turn; composite FK/RLS/client-scope/capability negatives; чистый cycle и populated refusal; pending manual/UNKNOWN/files/receipts/versions сохранены |
| Finding04 implementation | Historical6 shards отдельно от candidate I coverage; LOCAL upgrade в2 state shards; API/worker/scheduler/fixture exact pairing и rejected mixed pairs; actual image/source proofs, exact names/projections/receipt guards |
| M2 regression / штатный CI | Manual new/replay/conflict/revocation и пять API unchanged; private files/grants, send/UNKNOWN/no-resend; прежние wire/lifecycle/historical assertions, все9 jobs/clean-source gates |

Не заявлять полный A03 admission, A04–A10/A12 или M3 VERIFIED: это последующие
срезы. Закрытие contract findings не отменяет ни одного implementation assertion.
DB гонки — детерминированные barriers/наблюдаемые условия, без sleep/retry как
исправления. Test clock не становится runtime backdating API.
При failure сохранить первичную команду/ошибку и причину; не делать серию reruns
ради зелёного результата. Исправления в выданном scope доводить до законченного
candidate и штатных gates; недостаток окружения/новый scope честно вернуть C0
с exact evidence, не выдавая mock/неисполненный сценарий за PASS.

### 0.6. Возврат и следующий gate

Один законченный implementation candidate в том же Draft PR; логические code
commits допустимы, status-only commits/PR на каждый подпункт не нужны.
Перед публикацией сверить main/base/branch и сохранность C0 continuation;
не перетирать конкурентные changes и не force-push.

Вернуть в одном PR comment:
- full implementation head/parent/tree, accepted base и C0 continuation;
  полный changed-path список и diff к continuation, соответствие26-path allowlist;
- migration revision/predecessor, exact schema/permissions/ABI deltas,
  неизменность принятого contract blob и P/O/H pins;
- таблицу assertions выше → exact command/scenario/result/SHA, отдельно unit,
  actual PostgreSQL/private S3/worker, historical H и candidate I/schema evidence;
- final CI run/attempt/jobs/clean-source и tested checkout/parents/tree;
  actual image IDs/source manifests и отдельные reports для H/P и I;
- ограничения/OPEN issues, причины изменений тестовых fixtures, достаточность
  budgets, отсутствие VM/live/deploy/merge. Никаких выдуманных результатов.

После готового candidate C0 выполняет intake и выдаёт scoped implementation review
C2, затронутому C1, при необходимости C6, затем независимый C8 по concurrency/
isolation/recovery/upgrade. Только после evidence C0 принимает TURNS и разрешает
пользователю merge; actual main/CI проверяется отдельно. CONTROL выдается от
принятого интегрированного TURNS SHA. Сейчас merge и VM/Telegram действий нет.

</details>

<details>
<summary>История CONTRACT-R2 и read-only C6; завершено, текущая выдача — §0 выше</summary>

## История C0 — завершённая выдача CONTRACT-R2

Дата выдачи: 2026-10-10. Repository: `Elefesys/ai-service-manager`.
Accepted main/base: `754f1c883e5a94a7fc9e729af2605424f949ba33`;
[его push/main CI37965195898](https://github.com/Elefesys/ai-service-manager/actions/runs/37965195898) — 9/9 SUCCESS.
Один действующий Draft PR: [#26](https://github.com/Elefesys/ai-service-manager/pull/26),
ветка `c3/m3-1-turns`. Reviewed candidate: `5706350eaf01d72b4398f14f20c77649a4f0d6e2`.
Полный текущий continuation SHA после передачи C0 публикуется в PR metadata;
он не подменяет accepted main. Не reset/rebase, не force-push, не новый PR.

### R2.1. Решение C0 по первому candidate

[C1 review — PASS](https://github.com/Elefesys/ai-service-manager/pull/26#issuecomment-6093584212) принят в scope versions/commands/API.
[C2 review — CHANGES_REQUESTED](https://github.com/Elefesys/ai-service-manager/pull/26#issuecomment-6093660636) принят: findings01–04/P2 остаются OPEN до scoped delta review.
C0 сверил соответствующие SQL/worker/fixture/source-switch paths; это обоснованные
пробелы проектируемого контракта, а не подтверждённые execution defects M3 или M2.
Никакой M3 runtime/DDL этим решением не разрешается; PR26 остаётся Draft.

Сохраняются HUMAN-by-default, takeover только при новом принятом manual intent,
раздельные context/control/Turn/connection versions и честный in-flight/UNKNOWN.
C0 выбирает предложенную policy v1 для первого LOCAL/TEST среза: D=2с, G=10с,
M=15с после logical seal при абсолютном cap25с, N=32. Это реализационные параметры;
они не отменяют требование исправить concurrency/recovery и принять весь контракт.
Три таблицы остаются минимальной основой. C2 подтвердил revision0008, predecessor0007;
применённые0001–0007 immutable. Frozen tenancy.v1 revision0003 не меняется.

### R2.2. C3-M3.1-CONTRACT-R2 — один документ, четыре finding

Цель: подготовить один согласованный candidate с конкретными исполнимыми механизмами.
C3 продолжает свой отдельный checkout/ветку от опубликованного C0 continuation SHA.
**Единственный разрешённый C3 write path: `docs/tasks/M3_CONTRACT.md`.**
Реестр/handoff изменены C0 в этой содержательной передаче и остаются за C0.
Runtime/DDL/tests, canonical architecture, workflows и VM не входят.
Прочитать AGENTS, актуальный верхний TASK_REGISTER, этот §0, весь контракт,
оба review и cited current SQL/Python paths; старые M2 поручения не повторять.

1. **Finding01 — origin barrier уже в TURNS.** Описать barrier в ОБОИХ ingest paths
   до выдачи ingress time/sequence, lifetime lock до commit и выбор origin после
   стабилизации writers. Допустимый исходный вариант: canonical connection FOR SHARE
   до ingress mark; PROCESS_INBOX сохраняет FOR UPDATE до origin/membership.
   Сверить implicit FK locks, trigger timing и SQL snapshots; иной вариант требует
   явного доказательства того же инварианта. Future conversation/Resume fence
   добавляется поверх принятого порядка в CONTROL, а не заменяет барьер TURNS.
   Fingerprint, exact duplicate/conflict/legacy policy сохраняются. Новый scenario:
   fresh I1 с меньшим не committed sequence, fresh I2/worker, поздний commit I1;
   origin/deadlines не зависят от случайного materializing job и потом неизменны.
2. **Finding02 — полный claim/recovery protocol.** Дать выбранный ограниченный
   алгоритм для messaging_claim/exhaustion, обоих reschedule overloads/retry,
   begin/finish_send rejection, files success/failure и recover_expired/UNKNOWN.
   Указать lock modes/order, implicit FK locks, transaction boundaries, skip bound
   и освобождение locks при пропуске domain-blocked candidate. Объяснить, как B
   продвигается при exhausted A без потери terminalization A, увеличения timeout
   или retry и без бесконечного выбора того же кандидата. Для batch запретить блокирующий
   захват новых conversations в противоположном порядке. Job/domain/context
   outcome атомарны; актуальность Turn revision проверяется и в exhaustion/recovery.
   Сохранить первичную ошибку. Assertions: B-progress за заблокированной exhausted A,
   concurrent recovery batches, SUPERSEDED в каждом terminal entrypoint и ровно
   один context increment в FAILED/UNKNOWN/file terminal, replay/rollback=0.
3. **Finding03 — ACK-loss capability.** В той же третьей private receipt table
   определить immutable связь с canonical TEST_CONSUME job и winning claim плюс
   нужные supporting key/FK. Описать отдельный узкий read-only terminal replay:
   exact saved result может читаться после lease expiry без новой mutation;
   чужой/неизвестный/проигравший token отвергается. Никакого runtime общего SELECT,
   caller-Workspace bypass или ослабления live claim/XID admission для записи.
   Assertions: committed result + lost ACK, valid terminal replay, forged token,
   expired A → reclaimed B committed → late A rejected.
4. **Finding04 — source/schema pairing.** После заключения C6 из §0.3 и решения C0
   заменить недостаточное обещание «только inventory31→34» точной таблицей пар:
   caller/test image, app/operator/worker source, schema, allowable switch/rollback,
   обслуживаемые assertions и exact affected paths. Historical source migration
   0007→0007 сохраняется как отдельная гарантия; новый LOCAL/TEST upgrade0007→0008
   не переиспользует требование неизменного cross-schema fingerprint или обещание
   старого image rollback после populated cutover. Runtime0008 на schema0007
   запрещён. До выбора решения §10 остаётся явным OPEN gate, не разрешением к коду.

C3 может готовить01–03, пока C6 анализирует04; предварительные отдельные commits
на каждый finding не нужны. Финальный R2 вернуть после включения принятого pairing
решения, одним содержательным candidate. Если решение C6 ещё не принято — назвать
зависимость и не объявлять04 CLOSED/CONTRACT accepted. Чужие выводы не выдавать за
собственные согласования; полный C1 PASS старого SHA не переносить автоматически.

Ожидаемый возврат: PR/head/parent и diff к reviewed candidate, единственный собственный
changed path, таблица01–04 → разделы/механизм/assertions, список exact compatibility
paths с причиной, фактические static checks и состояние штатного CI без выдуманных
PG/live результатов. Все четыре finding остаются OPEN до review. Новых tests/suites
ради редакции не создавать; штатные gates не менять и не перезапускать без причины.

### R2.3. C6-M3-SCHEMA-SOURCE-PAIRING — ограниченное read-only согласование

Это dependency CONTRACT/finding04, не deployment и не переоткрытие M2.
Exact code для анализа: `5706350eaf01d72b4398f14f20c77649a4f0d6e2`
(его runtime равен accepted main). Отдельный detached checkout при локальной работе.
**Разрешённых write paths нет.** Результат — review/предложение в PR26 для C0/C3.
Не запускать suites/Actions/Docker, VM/SSH/Telegram/probes, не менять source pins,
receipts, runtime, schema, CI или ветки. C6 пока не реализует compatibility fix.

C0 задаёт границу решения: historical connect5 source-migration на0007 сохраняет
свои assertions/receipts; upgrade0007→0008 получает отдельный LOCAL/TEST проверяемый
путь с drain/exact readiness/forward-fix и populated downgrade refusal. Конкретные
точные source pins и минимальную реализацию этого разделения предлагает C6;
C0 утверждает их до code allowlist. Подмена coverage текущего candidate запуском
только замороженного M2 source недопустима: назвать, какие assertions проверят
сам изменяемый candidate helper/harness и отказ несовместимого pairing.

Обязательные исходники: scripts/test_telegram_egress_migration.sh,
scripts/test_telegram_egress.sh, scripts/prepare_telegram_egress.py,
tests/test_telegram_egress_migration.py, tests/test_telegram_egress_postgres.py,
backend/src/asm/foundation.py, применимые workflow/compose/fixture paths и runbook.
Прочитать finding04 и Contract §§7/10/11, M2_CONTRACT; references разрешено читать,
но наличие path в списке не даёт write permission.

Вернуть один минимальный вариант с таблицей phase → code/image → schema → fixture
→ valid forward/recovery/rollback → assertions. В частности проверить candidate
held LOCAL fixture против predecessor0007, asm_test отдельно от LOCAL DB,
readiness в forward/rollback, source manifests/clean-source gates, сохранение
historical fingerprints и текущие migration invariants. Указать полные существующие
source SHA; будущий implementation SHA не выдумывать, его проверка отдельный gate.
Назвать точную необходимую allowlist, включая оба shell paths, если они меняются,
и отвергаемые mixed pairs. Production rollout/новый VM updater сюда не включать.

После C6 предложения C0 принимает scope, C3 завершает04 в R2; C2 проверяет DB и
schema/source delta, C1 — только затронутую versions/API/commands delta. Затем C0
принимает контракт и отдельно выдаёт TURNS на исходном accepted main с текущим
reviewed continuation. Независимый C8 реализации остаётся последующим gate.

</details>

</details>

## 1. Исходная точка и результат для владельца

M2 INTEGRATED / VERIFIED в принятом LOCAL/TEST scope:
[PR #24](https://github.com/Elefesys/ai-service-manager/pull/24),
main `ca64f98b0c8d12d4de922ed0ed7d34e48822ac00`,
tree `5aa2b7764797919758a1d89a01c34fb94788540e`,
[push/main CI 37863489865](https://github.com/Elefesys/ai-service-manager/actions/runs/37863489865)
— 9/9 SUCCESS и все clean-source gates PASS.
[Итоговый receipt C0](https://github.com/Elefesys/ai-service-manager/pull/24#issuecomment-6066209663)
подтверждает owner-operated text/photo → Console → ручной ответ → одна копия у Client.
Не переоткрывать прежние findings/owner процедуры по историческим блокам M2.

**Результат M3:** система объединяет связанные сообщения клиента в Turn, хранит
текущее состояние разговора и право на автоматическое действие. Владелец видит
режим, может взять разговор и явно вернуть его автоматике. Устаревшая работа
подавляется; запрос участия владельца имеет причину, ответственного и завершение.
Уже начатая отправка и неопределённый результат отображаются честно.

Настоящие LLM/Gateway/AIRun и query-only Agent — M4. M3 проверяет рабочие сервисы,
DB-команды и dispatch boundary с детерминированным TEST consumer результата.
Это не заглушки вместо проверок и не публичный endpoint для отправки от имени AI.
Console не должна сообщать «ИИ отвечает», пока исполнитель M4 не подключён.
Режим AI означает разрешение на допустимую автоматику, а не наличие модели.

## 2. Источники и обнаруженные точки расширения

Канон: [Spec](../architecture/01_ARCHITECTURE_SPEC.md) §§4.10, 5.1–5.14,
14.11, 18.5–18.8, 24.7; [ADR](../architecture/02_ARCHITECTURE_DECISIONS.md)
022–026, 121–128, 180, 197–198;
[Roadmap M3](../architecture/07_DEVELOPMENT_ROADMAP.md);
[Implementation Plan M3.1/M3.2](../architecture/09_IMPLEMENTATION_PLAN.md);
[OPEN-082/083/085](../architecture/04_OPEN_QUESTIONS.md).
Сначала прочитать AGENTS.md. Канонический snapshot v0.28 и manifest не редактировать
в рамках планирования. Новое противоречие канону требует явного решения.

На исходном main:
- `app.conversations` и его `version` уже существуют; отдельные Turn/control
  generation/owner wait ещё предстоит реализовать.
- `backend/src/asm/messaging/worker.py` выполняет PROCESS_INBOX/FETCH_IMAGE/
  SEND_MANUAL_TEXT. Есть durable start attempt, claim token и UNKNOWN recovery.
  Новый automated origin нельзя выдать за прежний manual OWNER.
- [M2_CONTRACT](M2_CONTRACT.md) §§2/10 определяет native-owner/edit/delete как
  durable ignored events; M3 должен явно расширить эту семантику.
- `backend/src/asm/telegram/normalization.py` и SQL ingestion совместно
  определяют происхождение события. Изменение проекции требует совместимости
  dedupe/fingerprint и уже сохранённых Inbox, а не только нового Python enum.
- Existing Console, owner session/permissions, private image path, product policy,
  idempotent manual send и transport UNKNOWN сохраняются как рабочая основа.

M3 не требует ServiceRequest/Quote/Order/ApprovalRequest будущих этапов, модели
оценки тату, платежей, AI-провайдера, Redis или нового брокера. RequestRouter в этом
этапе ограничен реально используемым контекстом conversation/awaiting response;
будущие business references описываются как расширение, без пустых таблиц/сервисов.

## 3. Очередь небольших задач

| ID | Ведущий / участие | Ограниченный результат | Зависимость |
|---|---|---|---|
| M3.1-CONTRACT | C0; C3/C2, C1 для API | Один `M3_CONTRACT.md`: минимальная модель, переходы, admission boundary, upgrade/compatibility и применимые критерии. Не подробное проектирование M4–M9 | Принятый M2; review этого плана |
| M3.1-TURNS | C3 + C2 | TurnAggregator/ConversationTurn и минимальное State: bounded grouping, media readiness, durable deadline/restart, контекст/версии; реальные PostgreSQL tests | Принятый контракт |
| M3.1-CONTROL | C3; C1/C2 | Takeover/Resume, monotonic generation, типизированные owner-команды/API/Audit; Console manual send и надёжно распознанное native intervention | Принятый TURNS |
| M3.1-GUARDS | C3 + C2; C1 | Рабочая граница допуска автоматического результата/команды/отправки; stale/fencing/restart и in-flight semantics через существующий worker/Outbox | Принятый CONTROL |
| M3.2-ESCALATION | C3; C1/C2 | Отдельный запрос участия владельца: reason/assignee/context fingerprint, дедупликация, due/expiry/resolve/cancel, минимальные внутренние напоминания и API | Принятые control/guards |
| M3.2-CONSOLE | C5; C3/C1 | Режим и действия владельца, очередь ожидания/карточка причины, ответ, stale/in-flight/UNKNOWN; browser journeys по принятому API | Принятый API предыдущих частей |
| M3-ACCEPTANCE | C0 + C8; C6 только deployment | Сводная проверка матрицы, целевая проверка Telegram/Console, приёмка actual main; подготовка точного handoff M4 | Интегрированные части |

По умолчанию один implementation PR за раз, от фактически принятого main.
Контракт можно согласовать в начале PR первого среза; отдельный PR на каждый
редакционный абзац не нужен. API потребитель C5 начинает от принятого API SHA.
При чрезмерной дельте C0 делит текущий срез по проверяемому результату, сохраняя
родительские IDs M3.1/M3.2; не создаёт новые независимые milestones.

Названия/число таблиц, маршрутов, jobs и численные debounce/deadline не фиксируются
этим планом. C0/C2 выбирают минимум под сценарии до соответствующего кода.
Текущая принятая на main миграция0010 — GUARDS после PR28.
CONSOLE-CONTROL использует принятый API без DDL. Следующая schema дельта для
Escalation требует отдельного решения C0/C2; новая revision сейчас не назначена.
Applied0001–0010 не переписываются.

## 4. Контракт до кода: существенные решения

### 4.1. Turn и актуальность

Определить bounded debounce и максимальное ожидание, группировку быстрых text/photo
и media groups, порядок late/out-of-order событий, membership одного сообщения
в Turn, правила закрытия/revision и возобновления после restart.
Одна conversation обрабатывается последовательно; независимая conversation
не блокируется глобальным lock. Внешний HTTP/LLM не выполняется в DB-транзакции.

FileObject pending/ready/error не создаёт дубликат Message/Turn и не теряется
из-за закрытия debounce. Условие готовности Turn с изображением и ограниченное
ожидание файла определяются явно; Vision не входит в M3.
Новый inbound, material edit/delete, ответ владельца и иные изменения контекста
имеют таблицу влияния на актуальность. Не реализовывать редактор сообщений ради
минимальной обработки edit/delete, необходимой для stale guards.

Развести существующие Conversation/Message versions и control generation.
Задание/результат фиксирует доверенные Workspace/conversation/turn references,
релевантную версию контекста и generation. Определить точные события инвалидации,
а не увеличивать все счётчики при любом чтении или фоновой записи.

### 4.2. Control и право на действие

AI/HUMAN — отдельная ось от WAITING_FOR_CLIENT/WAITING_FOR_HUMAN/
WAITING_FOR_EXTERNAL_SERVICE/READY_TO_RESPOND. Не создавать фиктивный платёжный
workflow ради перечисления WAITING_FOR_PAYMENT.

Takeover и допуск нового automated action проходят общую сериализованную DB/CAS
границу. Проверяются текущие authority, permissions/product policy, generation,
context и channel capabilities. Lease сам по себе не является разрешением.
Происхождение OWNER_MANUAL/automation определяется доверенной командой, не
переданным клиентом `is_ai=false`. Ручная переписка и приём сообщений работают
в HUMAN. Запись фактического результата начатой отправки допускается после
смены control, чтобы не потерять evidence.

Повтор owner-команды с тем же key/body возвращает прежний результат; конфликт
payload и stale expected state обрабатываются явно. Replay не создаёт новый
Audit/переход/поколение. Для двух вкладок предусмотреть конкурентный takeover/
resume. Resume не возрождает старые outputs: будущая обработка использует свежий
контекст и новое поколение. Автоматического возврата из HUMAN по таймеру нет.

Предлагаемая безопасная начальная настройка M3 — HUMAN для existing/new
conversations до явного действия владельца; C0 подтверждает default в контракте.
Выбор режима сам не включает отсутствующий AI executor и не обходит product policy.

### 4.3. Отправка, уже получившая допуск

Зафиксировать linearization point dispatch до реализации тестов.
Если takeover победил до admission, ожидающий automated output не отправляется.
Если durable dispatch уже начался, физический запрос может быть в полёте,
включая интервал между commit допуска и I/O: DB toggle не доказывает отмену.
Показывать эту границу владельцу, сохранять результат; UNKNOWN не выдавать за
CANCELLED/FAILED и не возвращать в очередь слепым resend.

STALE/CANCELLED для не начатой работы должно иметь явное представление и
совместимость API/DB; это не повод менять исход уже начатой M2 send attempt.
Проверить гонки до admission, после него, после возможного provider effect и
после takeover → resume со старым worker. Уже совершённый эффект не откатывать.
Инварианты generation проверять настоящими DB/worker paths, не assertion
о том, что одна mock-функция была вызвана.

### 4.4. Вмешательство через Telegram и Console

C0 принимает точную семантику Console manual reply: предлагаемый вариант —
новое ручное намерение атомарно забирает управление/инвалидирует ожидающую
автоматическую работу; replay не создаёт нового перехода.
У существующих M2 manual intentions сохранить fingerprint/receipt/recovery semantics.
Чтение истории, открытие фотографии и refresh сами takeover не вызывают.

Проверить источник native-owner update, actor identity и признак bot-origin.
Нельзя принимать любой исходящий update за вмешательство человека: ответ нашего
adapter может наблюдаться как echo. Не присваивать native owner событию Client
identity. Дубликаты и запоздавшие события после Resume имеют явную семантику.

Официальная [Bot API документация](https://core.telegram.org/bots/api#message),
проверенная 2026-10-09, описывает `sender_business_bot` у исходящих сообщений
connected business account и `is_from_offline` для некоторых автоматических
сообщений. Эти поля помогают проектировать классификацию, но не доказывают
фактическую доставку нужных updates конкретному подключению.
Ранний ограниченный account probe проверяет native reply против bot echo.
Если автоматическое распознавание недоступно, C0 фиксирует конкретное ограничение
и решение по scope; нельзя объявить автоматический native takeover проверенным.
Явная кнопка Console остаётся обязательной независимо от native pause Telegram.

### 4.5. Escalation и ожидание владельца

Escalation не обязана переключать весь разговор в HUMAN.
Минимум: conversation/turn/context, reason, responsible owner, pending status,
due/expiry policy, dedupe key и явные resolve/cancel/expire переходы.
Новая несовместимая информация клиента или устаревший context отменяют прежнее
решение; поздний ответ не применяется к другому состоянию.
Resolve не должен неявно отменять установленный владельцем HUMAN.

Реализовать ограниченный lifecycle ожидания на существующих durable jobs:
сохранённые сроки, restart-safe expiry и дедуплицированные внутренние reminders,
видимые в Console. TEST сроки задаются fixtures/config; реальные часы ответа
мастера и исключения остаются OPEN-082/083. Не обещать клиенту срок ответа.
Полный Notification Engine, внешние owner notification transports и клиентские
follow-ups — M9; ApprovalRequest для денежных/заказных решений — M6.
В HUMAN не запускать новые AI sends/mutations/client follow-ups.
Для будущих transactional notices сохранить консервативный owner-review default;
не реализовывать сейчас отсутствующие платежные/booking процессы.

### 4.6. Upgrade и обратная совместимость

Миграции воспроизводимы с текущей схемы и на чистом окружении; расширяются точные
inventories/Audit variants/permissions там, где это нужно M3.
Не ослаблять RLS, type constraints или права worker ради новых операций.
Новые consumer/event versions читают сохранённые M2 Inbox/Jobs/receipts корректно.
Изменение normalization fingerprint требует отдельного compatibility теста.

Определить начальный watermark/backfill для существующих диалогов: исторические
сообщения доступны как контекст, но deployment не запускает ответы на весь backlog
и не переисполняет ранее IGNORED native-owner/edit/delete events.
Pending manual sends/UNKNOWN/receipts/private media сохраняют своё значение.
Добавление новой проекции не переписывает историческое доказательство отправки.

## 5. Матрица результата M3

Матрица принята C0; scope текущего среза указан в §0. Для каждой применимой строки указывать
конкретные assertions/scenario и SHA/run; количество тестов не является целью.
Если нужен дополнительный критерий, сначала объяснить риск/канонический источник.

| ID | Проверяемое поведение | Evidence |
|---|---|---|
| M3-A01 | Быстрые text/photo и media group объединяются по принятой политике; duplicates/late events не размножают Turn; ожидание ограничено | Controlled clock + реальные PostgreSQL/worker сценарии |
| M3-A02 | Restart сохраняет сроки/состав/готовность; pending/failed image не теряется; разные conversations обрабатываются независимо | Recovery, two-worker и private file integration |
| M3-A03 | Новый material context, edit/delete или owner action устаревает прежний результат по принятой таблице | Актуальные и stale payload через рабочий admission path |
| M3-A04 | Takeover раньше admission запрещает automated action; manual reply/inbound в HUMAN работают | Реальная конкуренция DB/worker и owner API |
| M3-A05 | AI → HUMAN → AI не возвращает полномочия старому worker; stale lease/generation не допускается | Реальные конкурентные/restart tests |
| M3-A06 | Начатый send сохраняет честный outcome; possible effect + response loss не приводит к повтору после takeover/restart | Existing controlled wire/worker, persistent send count и UNKNOWN |
| M3-A07 | Control commands идемпотентны; две вкладки/stale state/revoke/Workspace A→B безопасны; Audit ровно по принятой операции | API/auth/CSRF/RLS/DB tests и typed contract checks |
| M3-A08 | Native owner, bot echo, offline/unsupported и delayed events классифицированы без ложного переключения/дубликатов | Нормализованные fixtures + ограниченное наблюдение на разрешённом test account |
| M3-A09 | Escalation отдельна от takeover; duplicate/resolve/cancel/expiry/late answer и restart-safe reminders корректны | Service/API/PG со временем под контролем теста |
| M3-A10 | Owner видит mode/reason/wait/in-flight; takeover/resume и ответ работают, старая вкладка/другой Workspace не меняются поздним response | Browser journeys через настоящий backend/DB, минимум desktop/narrow |
| M3-A11 | Upgrade сохраняет M2 history/receipts/UNKNOWN/files и не запускает историческую автоматизацию; прежний manual scenario работает | Migration compatibility + regression по затронутому M2 пути |
| M3-A12 | Финальный интегрированный код проходит штатный CI; подготовлен рабочий interface для M4 и честный TEST/live receipt | Scoped C8, actual main CI, применимый owner smoke и handoff M4 |

DB гонки проверять детерминированными барьерами/наблюдаемыми условиями; не
подменять исправление увеличением sleep/retry. При failure сохранять первичную
ошибку и отделять дефект наблюдения от нарушения инварианта.
C8 выполняет независимое review законченного среза по новому риску
(control/admission, origin/isolation, recovery/upgrade); C0 self-review так не называет.
Повторный review закрытого неизменного кода без конкретного основания не нужен.

## 6. Окружение и действия пользователя

Начало M3 не требует новых аккаунтов, AI ключей, прайса, портфолио или правил
конкретного мастера. Основные проверки проходят LOCAL/TEST с контролируемым
источником результата; настоящая модель появится в M4.
Повторная настройка Telegram/VPN/DNS/TLS не является стартовым заданием M3.

Существующий TEST/COMPED interval завершился **2026-10-09T00:00Z**.
Это не отменяет принятую M2, но запрещает считать старый интервал действующим
для новых sends/проверок permissions. Перед account probe или финальным smoke
C0 готовит конкретный поддерживаемый путь нового TEST interval/fixture с
сохранением binding/history; не меняет даты старых immutable receipts и не
обходит product policy ручной правкой SQL. Если нужен новый scoped provisioning
механизм, это отдельная обоснованная задача, а не скрытая часть UI/turns.

Git merge не обновляет VM автоматически. На существующей VM уже были законные
live messages и активированный webhook. Старые migration fingerprints и команды
из исторических receipt не означают текущего снимка и не запускаются заново.
C6 нужен только для действительно необходимого guarded update/rollback под
принятую миграцию M3; доступ/текущий runtime проверяется, не предполагается.
Публичные сообщения — только в согласованном тестовом диалоге; synthetic AI
consumer не подключается к живому клиенту без отдельного явного тестового шага.

Владелец позже выполняет короткий целевой сценарий: несколько связанных
сообщений/photo, takeover из Console, ручной ответ, Resume; отдельно native owner
reply и наблюдение echo, если этот scope принят. Это evidence UI/channel control,
а не качества LLM или proof of no double-send во всех возможных гонках.

## 7. Порядок координации и первая выдача

Один реестр, этот handoff, один технический `M3_CONTRACT.md`; история M2 закрыта.
Каждому срезу C0 назначает цель, full accepted base SHA, ветку/PR, paths и критерии.
Существенные изменения документов совмещаются с передачей/реализацией; не плодить
status-only commits и отдельные receipts на каждый безопасный read.
Фактический текущий PR/head/CI можно фиксировать в PR metadata без самоссылочной
цепочки SHA в документах. Ошибки тестов исправляются с причиной, не скрываются.

Merge сохраняется за пользователем после конкретной приёмки C0 и green checks.
После merge C0 сверяет actual main/CI и от него выдаёт зависимую работу.
Унаследованные обязательные CI gates не отключаются этим планом; соразмерность
новых проверок определяет конкретный риск. Никакого deployment от одного факта merge.

**Порядок первого поручения (актуальная выдача — §0):** CONTRACT принимается до
отдельного допуска к ограниченному M3.1-TURNS. Сначала прочитать текущие messaging/
telegram modules, migration0005/0007 и M2_CONTRACT; сверить модель событий и
перечень совместимых изменений. Зафиксировать решения §§4.1/4.2/4.6 и границу
последующего CONTROL/GUARDS. Не выдавать C5, AI или изменение VM раньше зависимостей.
Если нужен отдельный чат, пользователю передаётся одно готовое текущее поручение.

M3 считается завершённой после матрицы/интеграции/применимого operator evidence.
Отсутствующий provider факт не подменяется synthetic PASS. M4 выдаётся отдельно
с точными Turn/context/control/admission контрактами и принятым main SHA.
