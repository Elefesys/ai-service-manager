# Console CONTROL — C5-M3.2-CONSOLE-CONTROL

Срез использует принятые три CONTROL routes и schema0010. Источники:
M3_HANDOFF§0, M3_CONTRACT§§8/12.2–12.5/13, generated OpenAPI и actual
conversations/http_models. Финальные SHA, CI и решение C0 — в единственном
receipt Draft PR. Этот документ не переводит M3 или UI в VERIFIED.

## Поведение

Карточка управления находится в истории выбранного диалога. OWNER определяется
membership.role. Выбор/refresh/session recovery выполняют только GET; режим
показывается после проверки Workspace/conversation/Client текущего контекста.
AI означает разрешение будущей автоматики, без обещания подключённой LLM/ответа.
Обе явные команды доступны из обоих режимов: принятый сервер допускает новое
намерение с generation+1 даже при сохранении того же режима.

Control intent хранится только в памяти: actor, Workspace, conversation, Client,
operation, frozen expected tuple/body и key. Render slot позволяет держать
ConversationControl смонтированным при смене selection/auth, а shared ref
блокирует синхронное пересечение нового manual/control submit. Новая сессия
не запускает POST; пользователь явно повторяет прежнее намерение. Другой
контекст видит только общее уведомление, без переноса операции или её данных.

200 ACCEPTED/REPLAY подтверждает операцию. Следующий отдельный GET определяет
режим; ошибка GET допускает только повтор чтения. Старый Resume replay не
подменяет более новый HUMAN. Valid manual202 инициирует fresh control GET;
CONTROL POST при этом не нужен. История также обновляется после control acceptance.

STALE_STATE первого запроса завершает отклонённое намерение, перечитывает режим
и требует нового явного действия. Network/abort/timeout/5xx/invalid response
сохраняют неоднозначность. Даже последующий отказ не доказывает rollback прежней
попытки; можно явно завершить локальное ожидание с предупреждением, что это
не отмена на сервере. Conflict ключа останавливает replay. Hard reload не пишет.

DISPATCHING и UNKNOWN показаны независимо, с нейтральной семантикой отправки.
Takeover не зависит от billing/канала/старого UNKNOWN. Resume проверяет сервер.
Нет recall/resend для уже начатого/неопределённого send. Private images и прежний
manual recovery используют сохранённые M2 пути. Нет polling, storage intent,
Escalation, native-owner switch, M4, новых зависимостей или runtime endpoints.

## Проверки и соответствие

| Критерий | Tests / assertions |
|---|---|
| UI-C01 | conversation-control-api.test: strict DTO/error/identity, bigint strings, exact GET/POST; ConversationControl.test: read-only mount/refresh/role |
| UI-C02 | conversation-control.spec `@narrow CONTROL HUMAN…`: keyboard Resume, Takeover, manual HUMAN, generation/context deltas и PG receipt/Audit/Message/Outbox/Job counters |
| UI-C03 | `two actual tabs…`: STALE без auto retry, fresh explicit takeover, delayed real main GET после перехода в AI alternate; component deferred GET/POST и away/back |
| UI-C04 | `committed control response loss…`: real route.fetch/commit→abort, тот же route/body/key после login/CSRF recovery, REPLAY без новых counters; `valid200 plus failed GET…`: один UI POST, только read recovery |
| UI-C05 | component matrix actor/Workspace/conversation/Client/session и late success/401/403; actual revoke/foreign Workspace journey и общий owner boundary |
| UI-C06 | component flags DISPATCHING+UNKNOWN; actual controlled UNKNOWN→Takeover→replacement worker, один CALL/EFFECT; старый Resume receipt→current HUMAN в actual recovery journey |
| UI-C07 | Весь прежний frontend/browser suite; MessagingPanel integration блокирует пересечение manual/control; основной journey также narrow/keyboard и без overflow |

Actual DISPATCHING дополнительно остаётся в принятом
`test_control_read_reports_dispatching_and_unknown_without_recalling_intents`
(tests/test_m3_1_control_api_postgres.py). Новый in-flight harness не добавлен.

Восемь новых именованных `ctrl_*` presets используют прежний canonical runtime
seed. Inventory дополнен Client IDs из canonical relation. `control-stats`
добавляет только SELECT counts control receipts/Audit; старый `stats` неизменен.
Прежние finite downgrade/disable/restrict разрешены лишь дополнительным
соответствующим presets. Canonical control/Message/Audit rows не создаются
provisioner-ом. Старые unit assertions сохранены и дополнены проверкой read-only
SQL/counter bindings. Worker, Compose и штатные runners неизменны.

Команды:

```sh
npm --prefix frontend run typecheck
npm --prefix frontend test
npm --prefix frontend run build
uv run ruff check scripts/m2_4_browser_fixture.py tests/test_m2_4_browser_fixture.py
uv run ruff format --check scripts/m2_4_browser_fixture.py tests/test_m2_4_browser_fixture.py
uv run pytest -q tests/test_m2_4_browser_fixture.py
git diff --check
sh scripts/test_browser.sh
sh scripts/ci.sh
```

Local component/parser/fixture checks не являются PostgreSQL evidence. При
отсутствии Docker actual suites исполняются штатным disposable GitHub PR CI,
с сохранёнными9 jobs/clean gates и budgets; результаты привязываются к final head
в receipt. CONTROLLED evidence не означает live Telegram. VM/рабочие DB-S3,
deploy, внешние отправки и merge не входят в этот срез.
