# M2 — инкрементальный контракт; первая редакция M2.1-KERNEL

Дата: 2026-09-21. Владелец: C0; предметное согласование: C2 (DB/tenancy),
C3 (events/delivery). Статус: **CONTRACT ACCEPTED C0; C2/C3 CONTRACT PASS**.
Это контракт реализации, не evidence выполненного M2. Текущий статус и поручение:
[TASK_REGISTER](../TASK_REGISTER.md), [M2_HANDOFF](M2_HANDOFF.md).

Принятый implementation base: `8e5f125d424c0ce613ed9e0c787392f11a49aeae`,
actual merge PR #17; [push/main CI 35522542861](https://github.com/Elefesys/ai-service-manager/actions/runs/35522542861)
SUCCESS. Первая задача: **M2.1-KERNEL**, ветка `c3/m2-1-messaging-kernel`.
Эта редакция задаёт только ядро M2.1; следующие части дополняют этот же файл.

Основание: AGENTS, IMPL-001, Spec §§2–4, 15.4–6, 17.4–5, 18, 19, 24.6;
ADR-019–021, 121–128, 138–140; Implementation Plan M2.1–M2.4.
R4/D-01…D-13, M1 user-account admission, frozen auth/tenancy contracts сохраняются.

## 1. Результат и разрешённая граница

Один проверяемый путь: verified synthetic event → durable Inbox/work → правильные
Client/Conversation/Message → внутренняя ручная text-команда OWNER → атомарные
Message/receipt/Audit/Outbox/Job → controlled adapter → сохранённый результат.
Повтор, конкурентная обработка и crash проверяются на реальном PostgreSQL.

Внешний adapter в M2.1 — только `CONTROLLED` в LOCAL/TEST, без реального network
send и без Telegram credentials. Он используется для исполнения и fault injection,
а не как подтверждение Telegram integration. Worker/Scheduler должны исполнять
durable работу через реальные entrypoints; очередь в памяти не допускается.
Изображение пока является нормализованной provider reference, без binary bytes,
FileObject, скачивания или выдачи URL. Эти части принадлежат M2.2.

Настоящий webhook, подтверждение Telegram connection, product entitlement policy,
публичные owner messaging routes и HTTP DTO/cursor — M2.3; интерфейс переписки —
M2.4. AI, Turns/control generation, takeover/resume, услуги/цены, запись, платежи,
универсальный event bus, Redis/broker и полный Ops не включены.

## 2. Идентичность и данные

Workspace — единственная tenant boundary. Локальные entity IDs — UUID с DB
`uuidv7()` default; FK/внешний workspace не получают случайного default.
Provider IDs хранятся отдельно, как ограниченные точные строки, и не являются
авторизацией. Нельзя использовать один Telegram message_id как глобальный key.
Абсолютное время — finite timestamptz; lease/available_at/expiry используют DB time.
Изменяемое canonical состояние имеет положительную bigint version и guarded
переходы. SQL имена constraints/индексов выбирает C2 и отражает в inventory tests.

Связь provider/bot/connection с Workspace задаёт серверная route mapping.
Смена Workspace/Business/внешней identity существующей connection или route не
переносит старую переписку: старые связи immutable, новая binding — новая identity.
Нормализованное содержимое является untrusted data, не инструкциями или principal.

NormalizedEventV1 имеет фиксированные поля: provider, bot_identity, event_id, kind,
external_connection_id, chat_id, message_id, sender_id, occurred_at, text,
image_file_id, media_group_id. Provider в исполняемом срезе — `CONTROLLED`.
IDs — 1…256 Unicode code points/не более 1024 UTF-8 bytes, без NUL/control chars;
image_file_id — не более 1024 code points/4096 bytes. Только перечисленные поля,
общий encoded payload не более 64 KiB, Unicode scalar values; пустые IDs не NULL.
Для CLIENT_MESSAGE обязательны connection/chat/message/sender/occurred_at и
непустой text либо image_file_id; text при image — optional caption. Text/caption
не более 4096 code points/16384 UTF-8 bytes. Image ref не является URL или bytes.
Для ignored kinds отсутствующие необязательные поля — NULL, не вымышленные IDs.

| Kind | Результат первой редакции |
|---|---|
| `CLIENT_MESSAGE` | TEXT либо IMAGE_REFERENCE Message; корректные Client/Identity/Conversation |
| `NATIVE_OWNER_MESSAGE` | Inbox IGNORED с `IGNORED_NATIVE_OWNER_MESSAGE` |
| `MESSAGE_EDITED` | Inbox IGNORED с `IGNORED_MESSAGE_EDITED` |
| `MESSAGE_DELETED` | Inbox IGNORED с `IGNORED_MESSAGE_DELETED` |
| `UNSUPPORTED` | Inbox IGNORED с `IGNORED_UNSUPPORTED` |

Ignored events durable и видимы в результате обработки; не создают client Message
или send. Это явная ограниченная обработка M2.1; настоящие Telegram semantics,
включая echo/edit/delete, принимаются отдельно в M2.3.

Inbox UNIQUE `(provider,bot_identity,event_id)`. Message UNIQUE
`(workspace_id,connection_id,provider_chat_id,provider_message_id)` для non-null
provider ID. Conversation UNIQUE `(workspace_id,connection_id,provider_chat_id)`;
её Client/Identity не меняются из-за очередного sender в том же chat.
ClientIdentity UNIQUE `(workspace_id,provider,external_user_id)`.

Event fingerprint — DB-authoritative SHA-256 от UTF-8 prefix
`asm:m2:normalized_event:v1\n`, затем полей в порядке NormalizedEventV1 выше.
Каждое поле кодируется как `-1:\n` для NULL либо `<UTF-8 byte length>:<exact bytes>\n`.
occurred_at — UTC `YYYY-MM-DDTHH:MM:SS.ffffffZ`. В prefix/полях `\n` — один LF.
Received time, correlation, Workspace, attempts не входят. Python использует тот
же codec; не принимать caller hash как авторитетный. Same event key/hash возвращает
прежний Inbox receipt, другой hash — `EVENT_ID_CONFLICT`, без overwrite.
При новом event ID и прежнем Message ID сравнить immutable message projection:
те же provider/bot/kind/connection/chat/message/sender/time/text/image/media-group
поля, без event_id. Совпадение — duplicate canonical Message, расхождение —
terminal `MESSAGE_ID_CONFLICT`. Смена Client у существующей Conversation —
terminal `CONVERSATION_IDENTITY_CONFLICT`, не rebind.

### Минимальный physical inventory

| Table | Ключи и обязательные связи |
|---|---|
| `app.channel_connections` | PK `(workspace_id,id)`; Business FK; UNIQUE `(provider,bot_identity,external_connection_id)`; ACTIVE/INACTIVE; immutable binding |
| `platform.channel_routes` | UNIQUE `(provider,bot_identity,route_key)`; composite FK с Workspace/connection/provider/bot/external_connection identity; route_key=external_connection_id |
| `app.clients` | PK `(workspace_id,id)` |
| `app.client_identities` | UNIQUE `(workspace_id,provider,external_user_id)`; tenant-safe Client FK |
| `app.conversations` | Connection/chat uniqueness; Client/Identity/Business/connection refs не противоречат друг другу |
| `app.messages` | Conversation/connection/chat composite FK; provider Message uniqueness; direction INBOUND/OUTBOUND; TEXT/IMAGE_REFERENCE; outbound только TEXT |
| `platform.inbox_events` | Event uniqueness; immutable normalized data/hash/route refs, received time, processing state/result |
| `app.outbox_events` | Один `SEND_MANUAL_TEXT` на outbound Message; tenant-safe Message/connection; delivery state, current attempt UUID, result/error timestamps |
| `platform.messaging_jobs` | Kind `PROCESS_INBOX` или `SEND_MANUAL_TEXT`; ровно один соответствующий Inbox/Outbox FK; claim/lease/attempt count/first_started_at/available_at/error |
| `platform.messaging_command_receipts` | Command uniqueness; typed Message/Outbox/Audit refs; original actor/correlation и immutable accepted result |

Каждый tenant reference проверяется composite FK с workspace_id; где требуется,
FK включает connection/conversation/chat, чтобы набор по отдельности существующих
IDs не образовывал ложную связь. Command receipt дополнительно подтверждает, что
его Audit относится к тому же Message. Один processing Job на Inbox и один send
Job на Outbox обеспечиваются UNIQUE, не только application lookup.
ON DELETE RESTRICT для canonical refs; физическое удаление истории не реализуется.
CHECKs исключают неизвестные kind/state, null-required поля и несовместимые
state/result/lease combinations. Claims и attempt IDs генерируются DB независимо
от entity UUIDv7 (claim — случайный UUIDv4 capability, не логируется).
Индексы — unique/FK access paths, due/expired jobs и bounded chronological message
reads; будущие отраслевые/AI/search индексы не добавляются.

## 3. Доверие, транзакции и доступ

M1 `TenantDatabase.transaction()` и `app.current_workspace_id()` допускают только
`AuthenticatedAccount`/`user_account` с актуальной membership. Их семантика не
расширяется до worker. Не создавать фиктивный Owner или service membership.

Выбранный worker path — узкие typed DB capabilities с job/claim/entity refs.
Worker не получает прямой SELECT/DML на старые или новые tenant tables. Каждая
операция восстанавливает Workspace/connection из canonical job и проверяет claim;
произвольный workspace, conversation или object из payload не даёт прав. Python
worker context task-owned/transaction-bound; AUTOCOMMIT, чужой asyncio Task,
повторное использование завершённого unit и потеря physical transaction отклоняются.
XID binding проверяется на той же connection, а не только SQLAlchemy logical begin.
`admit_job(job_id,claim_token)` проверяет сохранённый RUNNING job и live lease,
устанавливает transaction-local `actor_kind=worker_job`, очищает human actor,
связывает job/token/XID и canonical Workspace/connection/correlation. Каждая
последующая mutation проверяет их заново; перемена/expiry claim отзывает authority.
Owner и worker units не вкладываются и не наследуют контекст друг друга.

Новый owner read helper `app.current_messaging_owner_workspace_id()` использует
сохранённый M1 user context и дополнительно требует live OWNER. Он применяется
только к новым messaging read policies. ADMIN/PROVIDER не получают private history
из-за наличия `tenancy:read`/`tenancy:write`.

Сохраняются login roles `asm_runtime`/`asm_migrator`, NOSUPERUSER/NOBYPASSRLS и
отсутствие ownership/DDL у runtime. Typed SECURITY DEFINER functions принадлежат
asm_migrator; фиксируют `search_path=pg_catalog,pg_temp`, полностью квалифицируют
объекты, REVOKE PUBLIC, получают только перечисленные EXECUTE grants. Новые
Workspace-owned таблицы имеют ENABLE/FORCE RLS и явные migrator policies. Routes,
job control, receipts и attempt internals не становятся общим runtime SELECT API.
Это ограничение операций внутри доверенного server runtime, не новое разделение
API и worker по DB login и не защита от полностью скомпрометированного приложения.

Вход в ingestion принимает только серверный verified-adapter результат. В M2.1
его создаёт controlled adapter, регистрация test connections/routes доступна только
LOCAL/TEST provisioning через migrator, без runtime route reassignment. При неизвестном
route — bounded reject без tenant данных. Настоящая provider verification пока не
реализована. DB недоступна/commit не подтверждён — успешное принятие не возвращается.
trusted_source определяет provider и bot_identity; одноимённые поля event обязаны
точно совпасть, иначе reject до route lookup. Verified source A не разрешает bot B.

Все SQL transactions короткие. Adapter call выполняется после commit и возврата
connection в pool; нельзя держать открытый user/worker unit через network call.
Установить единый lock order для совпадающих writers и проверить реальные races;
не заменять атомарность последовательностью независимых commits.

## 4. Ручная команда и Audit

Внутренняя операция: `SEND_MANUAL_TEXT`. Permission: отдельная `messaging:send`,
только live OWNER, независимо от `tenancy:write`. Read — `messaging:read`, также OWNER.
Она добавляется в messaging policy, не меняет frozen `tenancy.v1` permission set.
Команда принимает conversation_id, exact text и idempotency key внутри настоящего
M1 owner unit. Workspace, actor и correlation_id получает из этого unit.

Idempotency namespace: UNIQUE `(workspace_id, operation, idempotency_key)`;
key соответствует `^[A-Za-z0-9._:-]{1,128}$`. Actor входит в fingerprint, не в UNIQUE.
DB авторитетно рассчитывает SHA-256 от UTF-8 следующих bytes:

```text
asm:m2:send_manual_text:v1\n
<canonical lowercase workspace UUID>\n
<canonical lowercase actor UUID>\n
<canonical lowercase conversation UUID>\n
<exact text>
```

Здесь `\n` означает один LF, пустых строк и trailing LF после text не добавляется.
Text не trim/NFC-normalize; JSON serialization не входит в fingerprint. Проверить
совпадение Python/DB bytes и hashes на значимых Unicode/пробелах/newline/quotes.
Manual text — 1…4096 code points/не более 16384 UTF-8 bytes; отклоняются NUL,
невалидный Unicode и полностью пробельное содержимое. Provider-specific text
limits уточняются до реального adapter, а не выдаются за проверенные здесь.

Текущая OWNER авторизация выполняется до receipt lookup. Same key/fingerprint
возвращает прежние receipt/message/accepted-at metadata; конфликт fingerprint
даёт `IDEMPOTENCY_KEY_CONFLICT`. Ошибка/rollback не оставляет частичный receipt.
Replay не создаёт новый Audit/Outbox/Job и не означает повтор внешнего send.
Новая команда append-only; отсутствие expected conversation version не разрешает
перезаписывать сообщение. Два новых key означают два самостоятельных намерения.

Для нового намерения проверить active Workspace/Business/connection. В одной
транзакции создаются canonical outbound Message, receipt, Outbox, send Job и ровно
один `MESSAGE_SEND_REQUESTED` Audit. Receipt хранит tenant-safe message/audit refs
и исходные completion metadata принятия команды; delivery state читается отдельно.

Повторная проверка перед durable send start использует исходного actor из receipt,
active account/OWNER membership/Workspace/Business/connection. Revocation до этой
границы запрещает новый send. После commit start attempt может уже выполняться;
отзыв не обещает отмену возможного I/O. Запись результата/recovery не требует всё ещё
активного Owner или connection: фактическое evidence нельзя потерять из-за отзыва.
Уже durably accepted inbound также восстанавливается после disconnect.

Новые commercial entitlements в M2.1 не вводятся. TEST keys M1.3 не становятся
messaging capabilities. Внешняя отправка/owner HTTP API не включаются до отдельного
принятия M2.3 permissions, service-mode/entitlement и connection-capability policy.

### Обязательная совместимость общего Audit

Выбран один additive вариант в существующем `app.audit_events`:
`event_type=MESSAGE_SEND_REQUESTED`, `actor_kind=USER_ACCOUNT`, non-null actor,
`object_type=MESSAGE`, object_id=message_id, object_version=1,
exact payload `{"content_type":"TEXT"}`. Текст, chat ID, key, credentials и provider
payload в Audit не копируются. Связь с Message — composite FK с Workspace;
прежние billing события продолжают иметь обязательный FK на billing account.
Типы объектов и payload проверяются строго, generic JSON fallback не добавляется.

Миграция 0005 добавляет generated nullable `billing_account_object_id` и
`message_object_id`: каждый равен object_id только при соответствующем object_type.
Старый unconditional billing FK заменяется FK `(workspace_id,billing_account_object_id)`
и `(workspace_id,message_object_id)`; точный discriminator CHECK гарантирует
необходимый ненулевой target. Для старых двух variants сохраняются прежние actor,
payload, object_type и обязательная billing relation. Для MESSAGE_SEND_REQUESTED
действует отдельная строгая ветка и UNIQUE на Workspace/outgoing Message/event.
Это сохраняет прежнюю wire форму billing событий и является
явным additive расширением R4 для нового домена, а не переписыванием миграции 0004.
При downgrade 0005 удалить только messaging Audit rows до удаления новых targets,
восстановить прежний FK/CHECK и сохранить все billing данные/receipts. Downgrade —
деструктивная проверка disposable TEST, не обещание production rollback без потерь.

Причина сопутствующей дельты: текущий GET audit-events читает все события; backend
AuditItem и frontend `billing-api.ts` допускают только два billing-варианта, а
`BillingPanel.tsx` подписывает прочие события как изменение контакта. Поэтому в
этой же задаче добавить один строгий DTO/parser/type variant, generated OpenAPI и
подпись «Ручной ответ поставлен в очередь». Старые variants/cursor/permissions/
contact recovery сохраняются. Не скрывать новые события SQL-фильтром, не заводить
второй Audit store. Это совместимость существующего Audit, не интерфейс переписки.

## 5. Jobs, транзакции и внешний эффект

| Entity | Состояния |
|---|---|
| Inbox | `PENDING`, `PROCESSED`, `IGNORED`, `FAILED` |
| Job | `READY`, `RUNNING`, `SUCCEEDED`, `DEAD` |
| Outbox | `PENDING`, `DISPATCHING`, `SENT`, `FAILED`, `UNKNOWN` |

Operation, Outbox kind и send Job kind имеют один literal `SEND_MANUAL_TEXT`.
Второй Job kind — `PROCESS_INBOX`; aliases SEND_TEXT/LEASED не вводятся.
Outbox `SENT` означает подтверждённое adapter acceptance, не доставку/прочтение.
Терминальные ошибки/UNKNOWN имеют bounded code и timestamp, доступны через owner
kernel read result; traceback/provider body/text/key/claim token не логируются.

Ingestion transaction: resolve verified route → validate/dedupe → Inbox + READY Job
→ commit → возврат accepted receipt. Processing transaction: trusted claim →
Client/Identity/Conversation/Message или explicit ignored/conflict result → Inbox
terminal state + Job SUCCEEDED/DEAD → commit. При transient DB failure transaction
откатывается и job может быть безопасно повторён. Не создавать пустой Outbox без
consumer: processing inbound в M2.1 не требует отдельного внешнего действия.

Claim использует короткую транзакцию и row locks/SKIP LOCKED, выбирает due READY job,
выдаёт новый случайный claim_token, записывает RUNNING/lease_until и count. Один
worker первоначально исполняет одну job за раз. Это не обещание strict FIFO или
provider ordering при нескольких workers. Lease по DB clock — 30 s; adapter
deadline — 10 s; максимум 5 claims, retry age — 15 min с first_started_at, не с
enqueue time. Full jitter: равномерно от 0 до min(60 s, 1 s × 2^(attempt−1)).
Явные TEST overrides допустимы с deadline < lease; runtime не принимает их из event.

Безопасный transient failure: RUNNING → READY с новым available_at; permanent или
исчерпанные count/age → DEAD (durable DLQ state). Для Inbox это FAILED; для ещё не
допущенного send — Outbox FAILED. При lease expiry PROCESS_INBOX либо send с
Outbox PENDING можно reclaim/retry с теми же bounds, без потерянной работы.

`begin_send` проверяет/блокирует job, Outbox и применимые authority rows, коммитит
новый attempt UUID + Outbox DISPATCHING **до adapter call** и возвращает SendPermit
с адресатом/text из сохранённого Message. До подтверждённого commit permit нельзя
использовать. Отказ новых прав/connection — terminal FAILED/NOT_ALLOWED, без call.

После commit start:

- SUCCESS с provider message reference → SENT, Job SUCCEEDED, result сохранён атомарно.
- Только definite NOT_SENT/retryable → PENDING + READY/backoff; definite permanent
  NOT_SENT → FAILED + DEAD. Unknown transport exception не является NOT_SENT.
- Timeout, неразобранная ошибка, crash либо expiry оставшегося DISPATCHING → UNKNOWN
  + DEAD, без повторного permit/send. Crash после start commit
  даже до фактического adapter call консервативно UNKNOWN.
- Повтор finalize точно того же уже сохранённого attempt/outcome — ALREADY_FINALIZED
  без mutation. Смена/expiry claim или поздний SUCCESS после UNKNOWN — STALE_CLAIM;
  canonical UNKNOWN не переписывается. Новый reconciliation/retry UI не строится.

При потере ACK finalize commit сначала перечитать canonical attempt/result:
уже сохранённый SENT или definite NOT_SENT не понижать до UNKNOWN и не повторять
I/O. Пока DB недоступна, нового send нет; если durable состояние осталось
DISPATCHING, применяется консервативный UNKNOWN recovery выше.

Finalize — отдельная narrow capability по job_id/claim_token/attempt_id/outcome:
сначала допускается только read-only распознавание **точно** сохранённого результата
и исходного claim; это не требует нового RUNNING admission. Любая новая mutation
проходит live admission/XID/lease guards. Приватные поля job сохраняют последнюю
связку attempt/original claim/typed outcome для сравнения; claim token не входит
в owner Outbox read DTO/SELECT grants. Старый результат после смены current attempt
можно вернуть как STALE_CLAIM; общий журнал всех будущих provider attempts не нужен.

Recovery не блокируется последующим revoke/disconnect. Зависший старый процесс
может ещё выполнить свою ранее допущенную попытку; другой worker её не дублирует.
Локальный fencing защищает DB result, но не отменяет уже возможный внешний эффект.
Принятые сообщения/receipt metadata не откатываются из-за проблемы доставки.

Scheduler выполняет bounded recover_expired, worker делает claim/process/send;
оба entrypoints используют PostgreSQL и корректный shutdown. SIGTERM прекращает
новый claim; до start lease можно отпустить/дождаться expiry; после start cancellation
не переводит send в READY. Если нельзя записать UNKNOWN, durable DISPATCHING
остаётся для следующего recovery. Ни scheduler, ни adapter не имеют скрытого retry.

### Kernel boundary

```text
ingest_event(trusted_source, normalized_event, correlation_id) -> InboxReceipt
request_manual_text(owner_unit, conversation_id, exact_text, key) -> SendReceipt
claim_job(worker_id) -> JobClaim | None
admit_job(job_id, claim_token) -> WorkerUnitOfWork
process_inbox(worker_unit) -> InboxProcessingResult
begin_send(worker_unit) -> SendPermit | TerminalRejection
finish_send(job_id, claim_token, attempt_id, typed_outcome) -> FinalizeResult
recover_expired(bounded_limit) -> RecoveryResult
```

Внешний application wrapper request_manual_text может открывать существующий M1
unit из настоящего AuthenticatedAccount; receipt возвращается только после commit.
SendReceipt сохраняет Workspace/receipt/Message/Outbox/Audit IDs и accepted_at.
JobClaim содержит canonical job/kind/Workspace/connection/entity refs, token/lease.
Поля caller claim не являются authority: admission читает их из DB заново.
Begin/finish — разные transactions, между ними adapter без DB unit. Finish wrapper
восстанавливает worker admission только для новой mutation; exact terminal replay
использует узкий read-only path описанный выше, без fake live WorkerUnitOfWork.
Read-only owner repository даёт bounded conversation/message/delivery reads для
проверки ядра; wire pagination/HTTP routes пока не вводятся. Не принимать SQL,
произвольный status, replacement recipient или arbitrary entity payload.

Ожидаемые bounded результаты: INVALID_INPUT, ACCESS_DENIED/NOT_FOUND,
EVENT_ID_CONFLICT, MESSAGE_ID_CONFLICT, CONVERSATION_IDENTITY_CONFLICT,
IDEMPOTENCY_KEY_CONFLICT, STALE_CLAIM, NOT_ALLOWED, RETRY_EXHAUSTED,
DEPENDENCY_TIMEOUT/UNAVAILABLE, UNKNOWN_EXTERNAL_RESULT. Общий M1 SQLSTATE mapping
не переопределяется; новые messaging errors отображаются локально по точному коду.

Controlled adapter считает **каждый** вызов, не дедуплицирует их по attempt ID и
не выполняет внутренних повторов. Поддерживает SUCCESS, definite NOT_SENT transient/
permanent, UNKNOWN/timeout и barriers до вызова/после эффекта/перед finalize. Crash
test использует сохраняемый вне перезапуска worker счётчик controlled effects;
сброс process memory не должен скрыть второй вызов. Это fault instrumentation,
не новая authoritative in-memory queue.

## 6. Граница проверки

Матрица M2-A01…A12 остаётся единственной в M2_HANDOFF. M2.1 проверяет применимые
части A01–A06/A08/A12 на реальном PostgreSQL и controlled adapter. Fake webhook
verification, private binary access, реальные Telegram rights/window, owner HTTP
messaging/API и browser conversation journey не считаются выполненными.

Нужны реальные runtime-role negative tests по Workspace/connection/job/claim,
duplicate/concurrent events и commands, rollback атомарных transitions и Audit,
crash до/после commit и возможного эффекта, lease reclaim/stale finalize, bounded
retry/exhaustion и отсутствие открытой DB transaction во время adapter call.
Дополнить mixed Audit API/парсер/component tests с обоими старыми вариантами,
новым событием, pagination и отвергаемыми неправильными payload/refs.

Первоначальная принятая редакция не содержала execution evidence M2.1. Текущее
evidence находится в активном M2_HANDOFF и PR #18. C0 принимает реализацию после
фактических tests/CI и независимого scoped C8 review новых
worker/routing/isolation/side-effect рисков. Прежние C8 PASS M1 сюда не переносятся.

## 7. Источники проверенных механизмов

PostgreSQL 18: [queue row locking](https://www.postgresql.org/docs/18/sql-select.html),
[SECURITY DEFINER privileges/search_path](https://www.postgresql.org/docs/18/sql-createfunction.html),
[RLS/FORCE RLS](https://www.postgresql.org/docs/18/ddl-rowsecurity.html).
Документация сверена 2026-09-21; она не заменяет runtime-role execution tests.

## 8. Реализационные имена текущего kernel (C3/C2, 2026-09-21)

Migration `0005` сохраняет revision chain `0004 → 0005`. Typed capabilities
`platform.messaging_ingest`, `messaging_claim`, `messaging_admit`,
`messaging_process_inbox`, `messaging_request_text`, `messaging_begin_send`,
`messaging_finish_send`, `messaging_retry`, `messaging_recover_expired` возвращают
bounded JSON результата; arbitrary SQL/status/recipient inputs не принимаются.
Owner reads — `messaging_read_conversations/messages/delivery/inbox` и отдельный
`app.current_messaging_owner_workspace_id`. PRIVATE helpers не имеют runtime
EXECUTE. Ошибки нового домена — SQLSTATE `P2001` + exact bounded code; mapping M1
не меняется. Owner DTO не содержит attempt/claim internals.

Lock order: job → Inbox/Outbox → authority/connection; Owner command берёт
workspace/account/membership → idempotency lock → Business/connection и создаёт
новые Message/receipt/Audit/Outbox/Job. Inbound writers сериализуются по connection,
затем по Workspace/provider/sender identity. Эти advisory locks сериализуют
конкуренцию, но не являются authorization. Новая claim инвалидирует recognition
результата старой claim; до неё exact finalized replay работает без live lease.

`finish_send` сначала читает canonical attempt/outcome; при совпадении возвращает
ALREADY_FINALIZED без смены состояния. Для новой mutation она внутри восстанавливает
worker admission. После потери finalize commit ACK wrapper делает один повтор
этого же typed DB вызова; adapter повторно не вызывается, сохранённый SENT или
NOT_SENT не заменяется UNKNOWN. Недоступная DB оставляет DISPATCHING для recovery.
Все вызовы adapter находятся после выхода из DB connection/unit.

Controlled adapter считает каждый вызов и каждый simulated effect, без dedupe;
TEST ledger из коротких fsync records находится вне процесса worker и не хранит
text/recipient/claim. Fault tests прекращают отдельный процесс через os._exit на
границах commit/start/effect/finalize и используют тот же ledger после restart.
Это fault instrumentation LOCAL/TEST, не гарантия distributed exactly-once и
не подтверждение Telegram. Runtime lease 30s, deadline 10s, retry bounds/backoff
соответствуют §5; test time manipulation доступна только migrator.

DB ingestion требует уже canonical `YYYY-MM-DDTHH:MM:SS.ffffffZ` для occurred_at:
точная shape, существующий UTC calendar timestamp и roundtrip equality. Слова
`now`/`tomorrow`, свободные PostgreSQL timestamp literals и неканонические offsets
через raw SQL отвергаются; Python нормализует допустимый timezone-aware datetime
перед вызовом. Поэтому один normalized event не меняет fingerprint со временем
и не получает иной hash через обход Python validator.
