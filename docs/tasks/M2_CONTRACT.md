# M2 — единый инкрементальный контракт

Дата: 2026-09-21. Владелец: C0; предметное согласование: C2 (DB/tenancy),
C3 (events/media/delivery), C1 (owner API/product policy M2.3). **C0 ACCEPTED;
C2/C3 CONTRACT PASS** для M2.1, M2.2 §9 и M2.3 §10; **C1 CONTRACT PASS** для
API/policy §10. Это согласование контракта, не C8 review новой реализации M2.3.
Текущие статусы и поручение: [TASK_REGISTER](../TASK_REGISTER.md),
[M2_HANDOFF](M2_HANDOFF.md).

Разделы 1–8 сохраняют принятый kernel M2.1: первоначальный base
`8e5f125d424c0ce613ed9e0c787392f11a49aeae`, PR #18. Его интегрированный main
**`d3c849d4792f7af60f43eea0f0551659ee3cee5d`**, отдельный
[push/main CI 35596593891](https://github.com/Elefesys/ai-service-manager/actions/runs/35596593891)
SUCCESS — принятый base следующего среза **M2.2-PRIVATE-IMAGES**.
В §1–8 отсутствие binary I/O описывает границу M2.1; §9 явно добавляет только
private image path. SEND deadline/UNKNOWN и ранее принятые механизмы не меняются.

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

## 9. M2.2-PRIVATE-IMAGES — принято C0/C2/C3, 2026-09-21

Основание: Spec §§3.10, 4.9, 17.5, 19.4–5; ADR-009/115/138–140;
Implementation Plan M2.2 и действующая матрица M2_HANDOFF. Ведущий C6, предметное
участие C3 (provider/media) и C2 (DB/migration). Только LOCAL/TEST. Ограничения
формата/размера/TTL ниже — явные реализационные решения C0 для этого среза,
а не восстановленные исторические требования или новый общий media-продукт.

### 9.1. Один работающий путь и сохранённая семантика

Controlled IMAGE_REFERENCE → прежний Inbox/Message → PENDING FileObject и
FETCH_IMAGE Job → проверенный private object → READY → авторизованный signed GET.
Реальны PostgreSQL, scheduler/worker и S3-compatible сервис; provider пока
CONTROLLED. Telegram download/webhook/rights, owner messaging HTTP/DTO, UI и live
smoke остаются M2.3/4. AI, upload владельцем, исходящие файлы, thumbnails/transforms,
CDN/multipart, дополнительные форматы и общая retention/deletion платформа не выданы.

Исходные Message.content_type=IMAGE_REFERENCE, image_file_id, projection hash,
IDs и dedupe M2.1 остаются immutable. Один FileObject на один inbound image Message;
новый generic Attachment слой не нужен. Message сохраняется даже при FAILED файле.
Disconnected connection не запрещает хранить уже durably принятое изображение
или читать историю актуальному OWNER; send policy остаётся прежней.

### 9.2. Схема, связь и trusted capabilities

Назначена и реализована **0006_private_images.py: revision 0006, down_revision 0005**.
Применённые 0001–0005 не редактировать. Минимальный inventory:

| Объект | Обязательная связь/состояние |
|---|---|
| `app.file_objects` | UUIDv7, Workspace, canonical Message/connection; UNIQUE по Workspace/Message; PENDING/READY/FAILED, положительная version, timestamps, bounded error; READY manifest и winner обязательны |
| `platform.file_object_uploads` | Durable intent с FileObject/FETCH Job/claim, отдельным server key, immutable validated manifest; PREPARED/WINNER/ABANDONED; cleanup token/lease/next-check/outcome |
| `platform.messaging_jobs` | Новый явный kind FETCH_IMAGE и file_id; typed composite FK и точная discriminator shape; один fetch Job на FileObject |

FK/constraints подтверждают Workspace и принадлежность FileObject именно inbound
IMAGE_REFERENCE Message и его connection, а READY winner — именно этому файлу.
Manifest: actual MIME, size_bytes, SHA-256, width/height; storage_key ведёт к winner,
бинарных данных в PostgreSQL нет. WINNER/READY pointer и ABANDONED→WINNER запрещено
переписывать. Upload intent уникален по job/claim; новая claim получает новый key.
Ключ выводится сервером из Workspace/FileObject/intent UUID, без имени файла,
provider ID, URL или секрета; он не является доказательством права доступа.

ENABLE/FORCE RLS, migrator policy и прежняя asm_runtime роль сохраняются.
Upload internals не получают общий runtime SELECT/DML; только перечисленные typed
SECURITY DEFINER capabilities с fixed search_path и canonical guards. Worker
получает source refs по Job→FileObject→Message→Connection из БД. Caller claim,
GUC, произвольный payload/key/URL не определяют Workspace/источник/winner.
Отдельная DB login role и расширение app.current_workspace_id() не требуются.
Прежние XID/task/physical transaction/pool и owner/worker mutual-exclusion guards
применяются к новым capabilities; worker не получает human billing/Business доступ.

0006 заменяет только необходимые branches messaging_process_inbox/job_json/
reschedule/recover_expired и добавляет file capabilities. Поддерживающая дельта
claim/admit/guard возможна только с сохранением проверенных инвариантов.
SEND begin/finish, owner command/receipt/Audit, UNKNOWN/no-resend не перепроектировать.
Python worker использует явный exhaustive dispatch трёх kinds: прежний implicit
«всё кроме PROCESS_INBOX = SEND» для FETCH_IMAGE недопустим.

### 9.3. Atomic planning и переход 0005 → 0006

Обработка image Inbox создаёт Message + PENDING FileObject + один FETCH Job и
фиксирует Inbox/PROCESS Job **одной транзакцией**. Точный повтор event/message
возвращает прежний результат и не создаёт новый файл/job; conflict semantics прежние.
Транзакционная ошибка любого звена откатывает весь новый набор.

Upgrade в БД добавляет ровно один PENDING FileObject/FETCH Job для каждого уже
существующего inbound IMAGE_REFERENCE Message, включая disconnected connection.
Источник — сохранённые Message/Connection, correlation — первоначальный PROCESSED
Inbox, если есть, иначе серверный migration correlation. Никакого внешнего I/O
в Alembic; Message bytes/fingerprints, Inbox result, billing и SEND evidence прежние.
Downgrade в disposable TEST удаляет только новые file jobs/metadata и восстанавливает
функции/constraints 0005. Объекты disposable TEST bucket убирает test infrastructure,
не SQL migration. Реальный rollback production этим не объявляется готовым.

### 9.4. Provider stream и hostile image validation

Небольшой provider boundary `open_image(FetchPermit)` возвращает ограниченный поток.
Permit берётся из canonical DB source; provider/bot/image_file_id остаются opaque refs.
Даже reference, похожий на URL, не разрешает HTTP по этому адресу. CONTROLLED provider
использует synthetic fixtures и fault barriers; настоящий Telegram — следующая задача.

Принятые лимиты: **JPEG, PNG, static WebP; 10 MiB = 10 485 760 bytes; максимум
20 000 000 pixels, 8192 pixels на сторону, ровно один frame**. Ограничивать фактически
прочитанные bytes независимо от Content-Length; provider MIME/filename не авторитетны.
Проверять actual format, dimensions и полное декодирование. Truncated, malformed,
animated, unsupported/SVG/GIF/PDF/archive content, bytes/pixel overflow — permanent
bounded failure, не READY. Настроить decoder против decompression bombs.

Сохранять оригинальные проверенные bytes без перекодирования/EXIF transforms,
actual MIME/size/SHA-256/dimensions. Это не заявление о malware scanning.
Первоначальная редакция §9.4 предполагала private temporary file. C0 явно принимает
более простую реализацию: ограниченный memory buffer оригинала, без записи временного
файла. Actual input по-прежнему не больше 10 MiB; возможные копии buffer и память
decoder не выдаются за общий лимит процесса 10 MiB. Один decoder slot и два S3 I/O
slots удерживаются до фактического окончания операций, включая cancellation.
Crash не оставляет временных файлов; канонические bytes хранятся только в S3.
Это реализационное упрощение в прежнем scope, не хранение клиентских файлов на ПК.

WebP требует dimension/static preflight до Image.open: pinned native decoder может
выделить canvas уже при открытии. Проверяются bounded RIFF/VP8/VP8L/VP8X headers;
затем сохраняются actual-format verification, полный decode и совпадение размеров.
Лимиты и JPEG/PNG/static WebP поддержка не сокращаются. Decoder и сетевой клиент
имеют ограниченную concurrency/resource lifetime.

### 9.5. Lease, upload intent и recovery

FETCH использует прежние max 5 claims, max age 15 min от first claim и bounded
backoff; lease **30 s**, отдельный общий fetch I/O budget **20 s**. SEND сохраняет
**10 s** deadline и прежнее UNKNOWN. SDK retries не обходят эти бюджеты; transport
connect/read deadlines заданы явно. Timeout/cancellation Python await не считается
доказательством прекращения фонового synchronous I/O: поздний PUT остаётся возможен.
Не накапливать неограниченные abandoned threads/tasks при недоступном storage.

1. Короткая DB admission возвращает canonical source. Download/validation вне DB unit.
2. Перед PUT новая короткая transaction проверяет live claim/lease и сохраняет
   intent, validated manifest и отдельный key. Permit используется только после
   подтверждённого commit; потерянный prepare ACK не разрешает внешний PUT.
3. PUT проверенных bytes вне DB transaction, с проверяемой checksum/integrity
   защитой SDK/S3. ETag или произвольная user metadata сами по себе не доказывают
   SHA-256 объекта. Реальный round-trip проверяет exact bytes/hash/manifest.
4. Подтверждённый PUT позволяет одной fenced transaction сделать intent WINNER,
   FileObject READY и Job SUCCEEDED. Только текущая canonical claim и exact intent.
5. При потере finalize ACK читать canonical result: уже READY того же intent —
   ALREADY_FINALIZED, без второго download/PUT, смены metadata или cleanup winner.
6. При неопределённом PUT/expiry старый intent становится ABANDONED; READY не
   объявляется. Следующий bounded claim может повторно скачать/upload в **новый key**.
   Stale worker не перезаписывает новый объект/pointer и не удаляет объекты сам.
   Это безопасный повтор private storage работы, не повтор отправки человеку.
7. Permanent invalid/missing либо retry exhaustion → FAILED FileObject/DEAD Job,
   незавершённые intents ABANDONED. Недоступная БД оставляет durable состояние
   для scheduler recovery, без предположения об успешном rollback/commit.

Conditional PUT If-None-Match:* допустим как дополнительная immutable-key защита
после проверки выбранного TEST сервиса; он не заменяет intent fencing и cleanup.
Все provider/S3 calls выполняются без business DB transaction/connection. Локальное
вычисление подписи без credential/network discovery — не внешний вызов.

### 9.6. Минимальная надёжная очистка сирот

Использовать существующий scheduler и узкую typed maintenance capability, без второй
generic queue и бесконечного создания periodic Jobs. ABANDONED intent сохраняется
как tombstone в течение жизни FileObject; WINNER никогда не eligible для cleanup.

Один claim выбирает до **100** due intents через SKIP LOCKED, сохраняет random token
и **30 s** lease. После commit DELETE canonical key с ограниченным deadline; guarded
finish по token/lease фиксирует outcome и next check. Выполнять столько I/O одновременно,
сколько укладывается в transport/concurrency budget; просроченную lease можно reclaim.
Успех/NotFound назначает следующий check через **1 hour**, но не удаляет tombstone.
Ошибка сохраняет bounded code и следующий retry с backoff не более 1 hour.
Это позволяет убрать поздний PUT после первого успешного DELETE. Нужны tests именно
такого порядка событий, а также отсутствие удаления нового READY winner.
Очистка eventual при доступном сервисе; outage не выдаётся за подтверждённое удаление.

### 9.7. Авторизованный read grant и private storage

Внутренний owner service работает через настоящий authenticated M1 tenant unit:
live OWNER/messaging:read, точные Workspace/Conversation/Message/FileObject и READY
winner. ADMIN/PROVIDER, revoked membership, cross-Workspace и mismatched relation
не получают URL. Внутри одного Workspace Owner вправе читать свои разные диалоги;
тест неверной пары Message/FileObject не вводит нового Client principal.
PENDING/FAILED не подписываются. Disconnect connection не закрывает историю.

Результат — signed GET и expires_at, **фиксированный TTL 60 s**. Caller не задаёт
bucket/key/TTL. Не возвращать отдельно provider reference, bot URL, credentials
или internal upload/claim; signed URL по природе содержит object locator и bearer
signature и не является «секретным key без URL». После revoke новые grants запрещены;
уже выданная bearer URL может работать до TTL — это принятая граница отзыва.
Согласовать content type с validated MIME, безопасное UUID-based filename,
private/no-store cache response. Авторизация не заменяется знанием object key.
Signing только локальный с заранее разрешёнными credentials; никакого SDK metadata
network discovery внутри authorizing transaction. Публичный route/DTO — M2.3.

Реальный LOCAL/TEST S3-compatible сервис, pinned image digest, private bucket;
anonymous GET/LIST/PUT запрещены. Конфигурационные endpoint/credentials задаёт
оператор, не event или user input. HTTP допустим только в изолированном LOCAL/TEST;
внешний deployment требует HTTPS и отдельной проверки. API/worker используют
ограниченные bucket credentials, bootstrap admin credentials не передаются runtime.
Новые LOCAL secrets генерируются без вывода; существующие .env/PG secrets сохраняются.
S3 SDK и image decoder разрешены как необходимые зависимости с narrow lock update.
Не писать собственный SigV4. Реализовать только используемые PUT/HEAD/GET/DELETE/
presignGET, без облачного provisioning, multipart, CDN или платных ресурсов.
Успех локального S3 не подтверждает Yandex/другое облако или live Telegram.

### 9.8. Проверка и предел приёмки

Единая матрица остаётся M2-A01…A12 в handoff; новых критериев milestone не добавлено.
Для A07/A08 и применимых A02/A04/A06/A12 нужны реальные PostgreSQL/S3 evidence:
atomic planning/rollback/concurrent dedupe; exact bytes/hash signed GET; anonymous
access denied/signature tamper/реальный expired URL; wrong Workspace и same-Workspace
relation; OWNER revoke/role change; forged claim/key/intent, stale lease и XID/task.
Missing/malformed/animated/oversized bytes/pixels и false/missing provider metadata;
retry/exhaustion/outages; crash после intent/PUT/READY commit и потерянный ACK;
late PUT после cleanup и после нового READY; cleanup outage/reclaim/winner safety.
Provider/S3 I/O проверяется без DB transaction; migration clean/repeated/0005-data/
downgrade-reupgrade сохраняет старые messages/billing/receipts/UNKNOWN.

Все прежние M1/M2.1 tests, штатные ci.sh/test_browser.sh, contracts/reproducibility
и оба clean-source gates сохраняются. Изменение old fixtures/inventory объясняется
новой схемой/очередью, прежние assertions не удаляются. C8 private-file/worker/recovery
review выполняется независимо после реализации; данный C2/C3 CONTRACT PASS его не заменяет.

Первичные источники, проверенные C0 2026-09-21:
[Yandex signed URLs](https://yandex.cloud/en/docs/storage/concepts/pre-signed-urls),
[Yandex PutObject/checksums/conditions](https://yandex.cloud/en/docs/storage/s3/api-ref/object/upload),
[S3 conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html),
[Pillow image/decompression limits](https://pillow.readthedocs.io/en/stable/reference/Image.html).
Это подтверждение доступных механизмов, не execution evidence выбранного сервиса.

### 9.9. Реализационные уточнения C6/C2/C3

В PR #19 реализована назначенная `0006 → 0005`, без изменения 0001–0005.
`files_plan` вызывается внутри прежнего process-inbox commit и при backfill;
original Message IDs/content/projection fingerprints не переписываются. Публичные
typed capabilities: `files_begin_fetch`, `files_prepare_upload`, `files_finish_fetch`,
`files_claim_cleanup`, `files_finish_cleanup`, `files_read_manifest`. Общего runtime
доступа к uploads нет. `files_plan` и serialization/validation/immutability helpers
не доступны runtime. Реализация меняет ровно три определения kernel: job JSON,
process inbox и reschedule; прежний recover-expired вызывает этот reschedule,
SEND begin/finish и UNKNOWN остаются прежними.

READY pointer имеет полный composite FK на WINNER key/manifest. FK `DEFERRABLE
INITIALLY DEFERRED` позволяет только явный ordered teardown связанных TEST rows в
одной транзакции; immediate triggers запрещают изменение READY/WINNER и переход
ABANDONED→WINNER. Это не отключение FK или проверок lease/claim.

Используются `boto3==1.43.98`, `pillow==12.3.0` и реальный MinIO LOCAL/TEST с
digest pins из `infra/images.lock.env`. PUT передаёт SHA-256 checksum и
`If-None-Match: *`, проверяет ответную checksum. Сетевая подпись не написана вручную.
SDK имеет один attempt, connect/read 2/5 s, await 8 s, два sync slots до фактического
окончания I/O. Decode — один отдельный slot. FETCH общий budget 20 s; cleanup
sweep берёт два intent, оставляя SQL limit 1…100. Успех cleanup не удаляет tombstone.

Runtime S3 user получает Get/Put/Delete только своего `workspaces/*` и ListBucket
только собственного private bucket, чтобы HEAD absent key возвращал 404. Anonymous
доступ и bucket admin запрещены; root credentials остаются в server/bootstrap.
Presign вычисляется локально внутри live owner unit, URL возвращается после commit;
`expires_at` вычислен из фактического SigV4 timestamp + 60 s. Новые grants после
revoke запрещены, прежний grant живёт до expiry согласно §9.7.

Настройка, recovery и операционные ограничения — в
[M2_STORAGE_LOCAL_TEST](../runbooks/M2_STORAGE_LOCAL_TEST.md). Конкретные execution
results, tests→критерии и C0/C8 receipt — в активном handoff и PR #19. Этот раздел
фиксирует контракт реализации; статус интеграции/VERIFIED определяется реестром
после actual merge и отдельного main CI, а не наличием данных уточнений.

## 10. M2.3-TELEGRAM-API — принято C0/C2/C3/C1, 2026-09-21

Этот раздел добавляет только настоящий Telegram transport и минимальный owner API.
Основание: Spec §§4, 15.4–6, 17.5, 18, 19, 24.6; ADR-019–021/121–128/138–140;
Implementation Plan M2.3, принятый handoff и матрица M2-A01…A12. Accepted base:
`a321bdd58856fb41bccb5749b4212349832e623c` (PR #19 merge); push/main CI
35611528733 SUCCESS. M2.1/2 не проектируются повторно; §§1–9 остаются историей
соответствующих срезов, явные additive TELEGRAM/API отличия определены только здесь.

### 10.1. Конечный scope и сохранённые механизмы

Один configured test bot, connected business bot/Profile Automation; Workspace
остаётся tenant boundary. Официальный webhook принимает текст или Telegram photo;
прежние Inbox/Jobs/Message/FileObject сохраняют их; пять owner routes читают историю,
дают private file grant и принимают ручной TEXT reply через прежний Outbox.
CONTROLLED остаётся для deterministic tests. Настоящий external adapter, HTTP/API
и тестовое подключение проверяются отдельно; наличие fake server не закрывает A11.

Без standalone fallback, userbot/MTProto client, owner upload, исходящего media,
edit/delete commands, retry/resend endpoint, album aggregation, notifications,
AI/Turn/takeover/resume/M3, prices/payments или дополнительной общей очереди.
Полученный native owner/echo/edit/delete имеет явный ignored outcome, а не новую
client Message. UI и полный Console→Telegram journey — M2.4 после принятого API.

### 10.2. Минимальная DB-дельта и migration queue

C0/C2 назначают **0007_telegram_api.py: revision 0007, predecessor 0006**.
0001–0006 immutable. Только следующие physical additions и необходимые typed SQL
capabilities; не создавать общий provider registry/secret table/raw-event queue.

| Объект | Дельта / обязательный инвариант |
|---|---|
| Existing provider validators/CHECKs/permits | CONTROLLED или TELEGRAM. NormalizedEventV1 поля, порядок и fingerprint codec прежние; CONTROLLED vectors побайтно прежние |
| `platform.telegram_connection_state` | Один state на canonical connection, composite Workspace/connection/bot identity FK; immutable independently approved owner Telegram ID; local invalidation generation/version, observed enabled/can_reply, DB observation time/error. Secrets здесь отсутствуют |
| `platform.telegram_update_receipts` | UNIQUE(bot_identity,update_id), DB-authoritative fingerprint bounded typed projection, kind/result/received time; optional canonical connection/Inbox FK. Terminal ignored/lifecycle receipt либо ссылка на прежний Inbox/Job; собственной очереди нет |
| `app.conversations.last_client_inbound_at` | Nullable finite timestamp, только Telegram reply-window evidence. Старые CONTROLLED строки NULL, immutable Message/time/hash не переписываются |
| Existing retry/finalize state | Optional bounded retry_after_seconds для definite NOT_SENT_RETRYABLE; canonical saved result/due, без новой delivery state machine |
| Owner typed reads | Connection list и cursor overloads conversation/message reads; projection Message/File/Outbox одним SQL snapshot, не raw dict наружу |

FORCE RLS, tenant-composite FK, закрытые grants, pinned SECURITY DEFINER search_path
и runtime non-owner/non-BYPASSRLS сохраняются. Никакого общего runtime SELECT/DML
к new platform receipts/state. Непривязанный terminal unsupported receipt не имеет
tenant authority. Caller Workspace/connection/claim/hash не является доказательством.

SQL seams: typed Telegram ingress; owner/worker canonical connection probe и fenced
observation; owner receipt/prepare helper; TELEGRAM guards request_text/begin_send;
429 finalize/reschedule; bounded owner read/cursor helpers; fresh-only TEST initializer
из §10.7. Старый begin_send path не может обойти TELEGRAM preflight. Worker permit
привязан к canonical job/claim, generation и observation version; stale claim/probe
не даёт permission. Telegram-specific atomic observation+begin проверяет текущую
claim и CAS перед DISPATCHING; прежний begin path не заменяет эту capability. DB определяет контекст, никогда не caller boolean/Workspace.

Порядок locks: owner admission → idempotency namespace → Business/connection →
Telegram state/billing; worker job → Outbox → actor authority → Business/connection
→ state/billing. Lifecycle не берёт worker locks в обратном порядке. Никакой network
I/O внутри DB/auth admission unit. File SQL capabilities, READY/WINNER FK, per-attempt
keys, fencing/late-PUT cleanup и C8-M2.2-01 guards менять не требуется.

Upgrade проверяется с точными данными 0006. Downgrade 0007→0006 при наличии TELEGRAM
domain rows **отказывает SQLSTATE 55000 до destructive изменений**; не удаляет историю.
Disposable TEST сначала явно удаляет только свой Telegram dataset в FK-порядке.
CONTROLLED/billing/receipts/FileObject/WINNER/UNKNOWN остаются неизменными. Новый
SEALED test_messaging catalog может остаться в совместимой схеме 0006. Никаких
CASCADE, правок применённых migrations или внешнего S3 I/O из Alembic.

### 10.3. Доверенная LOCAL/TEST binding и секреты

Одна operator-only процедура, не owner HTTP connect(connection_id). Она получает
заранее подтверждённые Workspace/Business и expected Telegram Owner user ID;
проверяет принадлежность Business Workspace. Bot identity — canonical decimal
getMe.id и configured expected bot ID, не username и не caller webhook поле.

1. getWebhookInfo/getMe; не менять чужой установленный webhook. Для discovery
   допустим один bounded getUpdates до установки webhook: без offset, negative
   offset, auto-pagination или drop. Это setup, не второй runtime transport.
2. Выбрать только connection с independently approved owner ID; затем
   getBusinessConnection и exact owner/bot/connection match, observed enabled/rights.
   Первый случайный connection или один переданный connection ID не авторизуют bind.
3. Одна short migrator-only transaction создаёт immutable binding/state/route;
   exact повтор NOOP, конфликт identity/Workspace — отказ без rebind/переноса истории.
4. Только после commit setWebhook: точный HTTPS URL, отдельный secret_token,
   allowed_updates=[business_connection,business_message,edited_business_message,
   deleted_business_messages], max_connections=1, drop_pending_updates=false.
   Повтор setup восстанавливает webhook после неудачи этой внешней операции,
   не удаляя и не подтверждая накопленные сообщения заранее.

TG_BOT_TOKEN и отдельный TG_WEBHOOK_SECRET вводятся оператором только в защищённый
runtime env/secret file (например, игнорируемый `.env.telegram`, mode 0600), не CLI
аргументы, GitHub repo, build context, artifact или чат. Runtime не получает migrator
credentials. В БД нет токена/secret URL; settings repr и diagnostics его не раскрывают.
Один configured bot может иметь разные immutable Workspace bindings, но клиент
не выбирает его credentials. Default LOCAL/TEST без Telegram secrets продолжает
работать с CONTROLLED; Telegram endpoint в таком режиме недоступен, не fake-enabled.

### 10.4. Webhook, общий receipt и normalization

Точный route **POST /webhooks/telegram**, без bot token и Workspace в URL.
Отдельная narrow boundary: один X-Telegram-Bot-Api-Secret-Token с constant-time
comparison до parsing; header cap 16 KiB, body **256 KiB**, полный read ≤3 s.
JSON Content-Type, identity encoding, strict Content-Length/stream cap, duplicate
JSON keys/ambiguous known fields/невалидный Unicode отвергаются. Secret error —
403; body413, media415, invalid422, transient DB503. Текст и secrets не включать
в ответы/logs. Cookie/Origin/CSRF не нужны Telegram; owner routes сохраняют все
прежние guards, wildcard exemptions для /api/v1/workspaces не добавляются.

Используемые Telegram поля строго типизированы; integer не bool/float. Только исходно
numeric IDs (bot/user/private chat/message/update) переводятся в точные canonical
decimal strings без округления; здесь принимается положительный private-chat domain.
Business connection ID, photo.file_id и media_group_id остаются bounded opaque strings;
их не преобразовывать в числа/URL/authority. Unknown дополнительные provider fields
допускаются и отбрасываются.
Одна bounded typed projection для общего receipt включает discriminator и все
значимые normalized/lifecycle/delete identifiers; immutable DB fingerprint считает
сама DB. Python codec и SQL проверяются одинаковыми vectors. Не сохранять raw update,
не выдумывать message ID для deleted array, не принимать caller-computed hash.

Known supported event: общий Telegram receipt + прежний Inbox/PROCESS Job атомарно.
Known lifecycle: receipt + generation invalidation атомарно; webhook не повышает rights.
Known ignored event: явный durable outcome, без новой client Message/send/download.
Неизвестный business connection — bounded503, без ACK/tenant writes. Неподдержанный
nonbusiness update получает terminal IGNORED receipt без tenant refs, чтобы не создать
вечный retry старых unwanted updates. При known duplicate сначала возвращается
canonical receipt независимо от последующего disconnect. Same bot/update ID с другой
relevant projection —409 EVENT_ID_CONFLICT, без overwrite.

**200 только после commit или чтения подтверждённого сохранённого duplicate.**
Lost commit ACK/DB outage →503, повтор безопасен. Состояние нельзя восстанавливать
из in-memory queue или provider ACK. Нормализация не скачивает изображения до ACK.

| Provider событие | Принятая семантика |
|---|---|
| Private business message: from.id=chat.id, sender не approved Owner и не bot | TEXT либо photo/caption → CLIENT_MESSAGE; forwarded origin/reply metadata не меняют sender |
| sender_business_bot присутствует | Durable echo-ignore; не новый inbound, не подтверждение UNKNOWN |
| from.id=approved Owner | Durable native-owner-ignore; M3 takeover не запускается |
| edited/deleted business message | Durable explicit ignored outcome; локальный Message не редактируется/удаляется |
| document, включая image-as-document, video/sticker/service/guest/неясный sender | Durable UNSUPPORTED; URL из текста/caption не скачивается |

PHOTO-only — явное ограничение adapter M2.3, не уменьшение форматов validator M2.2.
Наибольшая PhotoSize выбирается по (width*height,width,height,file_id) с стабильным
лексикографическим tie-break, независимо от порядка массива. Optional caption
сохраняется; один Message/FileObject на сообщение, media_group_id — correlation,
без album aggregation. Original bytes — выбранный Telegram file после обработки
платформой; побайтное совпадение с исходником до отправки в Telegram не обещается.

update_id не использовать как вечный high-water cutoff: поздние события допустимы,
после долгой паузы sequence может смениться. BusinessConnection.date — не revision.
Message dedupe остаётся scoped connection/chat/message, не глобальный message_id.

### 10.5. Observation, reply window и реальный SEND

Lifecycle инвалидирует local generation; duplicate receipt не инвалидирует повторно.
getBusinessConnection выполняется вне DB и сохраняется CAS по generation **и версии
наблюдения**, чтобы старый response после invalidation/нового snapshot не восстановил
rights. Наблюдение имеет DB time; для отображения AVAILABLE срок freshness **30 s**.
Это display/cache bound, не разрешение worker пропустить новый preflight: перед
каждым Telegram begin_send требуется проверка в текущей claim. Технический snapshot
не гарантирует немедленный provider revoke; Telegram остаётся конечной enforcement
boundary, и внешняя гонка после выдачи permit не скрывается.

Для нового canonical поддержанного client Message:
last_client_inbound_at=greatest(old,least(provider occurred_at,first Inbox received_at)).
DB send admission требует DB now < last_client_inbound_at+24h; equality запрещена.
Duplicate/native/echo/edit/delete/unsupported не продлевают окно, старое позднее
сообщение не сокращает его. Это conservative supported-inbound evidence, не полная
синхронизация Telegram history. Incoming persistence/FETCH не зависят от reply rights.

Worker: canonical job/claim probe → commit → readonly getBusinessConnection ≤5 s
→ short CAS + current OWNER/Business/product/window/lease check → durable DISPATCHING
commit → один sendMessage ≤10 s → прежний finish/recovery. Lease остаётся30 s.
Ошибки readonly probe до DISPATCHING безопасно retry в прежних count/age bounds.
Следующий этап не использует stale permit; caller readiness flag недостаточен.

sendMessage содержит canonical business_connection_id/chat_id и точный text. Без
parse_mode, split/trim/NFC, reply markup/paid broadcast или standalone fallback.
Success принимается только с корректными ожидаемыми business/chat refs и положительным
message_id. SENT значит Telegram принял сообщение, не доставку/прочтение клиентом.

| Фактический результат | Canonical исход |
|---|---|
| Строгий valid success | SUCCESS → SENT |
| Доказанный connect/pool failure до отправки request bytes | NOT_SENT_RETRYABLE |
| Валидный явный 400/401/403 отказ с ok=false | NOT_SENT_PERMANENT / bounded NOT_ALLOWED |
| Валидный 429 с positive integer retry_after | NOT_SENT_RETRYABLE с durable delay |
| Read/write timeout, разрыв после возможной записи, неверный success/refs, неясный 5xx | UNKNOWN_EXTERNAL_RESULT → UNKNOWN |
| Crash/cancellation после DISPATCHING, в том числе до фактического send | Прежний conservative UNKNOWN, без повторного adapter call |

Если wire-phase не доказана, ошибка не классифицируется как definitely NOT_SENT.
Никаких HTTP retries внутри client. Для valid429 без корректного retry_after —
консервативный terminal NOT_SENT_PERMANENT, не немедленный retry. Неизвестные/malformed
ответы после потенциального send — UNKNOWN. Echo может не прийти; он не reconciliation.

retry_after_seconds допустим только для NOT_SENT_RETRYABLE; due=max(old jitter due,
DB now+delay). Предельные5 claims/15 min сохраняются; due≥first_started_at+15min →
RETRY_EXHAUSTED. Delay/due входят в canonical finalized result: lost ACK replay
не переносит due снова. CONTROLLED без delay сохраняет прежние vectors/behavior.

### 10.6. Safe HTTP и media provider

Использовать существующий locked **httpx 0.28.1**: narrow promotion dev→runtime,
без package refresh/нового bot SDK. AsyncClient с TLS verify, trust_env=false,
redirects=false, retries=0, pool≤4 connections, connect≤5s, pool≤2s и read/write≤5s;
общие wall budgets выше обязательны независимо от chunk activity. Origin фиксирован
https://api.telegram.org; TEST transport/server внедряется явно в tests, event/owner
не задаёт endpoint. Никакого dependency на Telegram для прежнего DB/auth health.

C3-M2-ENV04-05: connect2→5 — **VERIFIED в code/runner scope на
14f794b650c935c47ab1e78474fda0d1df0a7277** после C0/actual CI37531243359 и
независимого C8 PASS. Owner migration выполняется отдельным этапом.
Connect входит в прежние readonly5/send10/FETCH20s, не добавляется к ним; lease30s
не меняется. Общий timeout/cancellation без доказанной wire phase не означает
definitely_unsent. Cold TLS3s подтвердил old-fail/new-pass, но stalled TLS выявил
незакрытый TCP после outer cancellation в R1; failed candidate сохранён в истории.
R2 владеет raw TCP transport до завершения TLS и при BaseException выполняет
синхронный nonblocking abort только этого transport, сохраняя исходное исключение.
Нет drain/TLS shutdown, нового deadline, await/GC или detached cleanup task;
повторная cancellation не прерывает этот участок. Освобождение socket завершает
обычный следующий callback asyncio. Shared client и чужие in-flight streams не закрываются.
Production factory и TEST AsyncHTTPTransport injection проходят один cleanup path.
Private seams locked HTTPX0.28.1/httpcore1.0.9/AnyIO4.15.1 явно описаны в client.py
и проверяются real peer EOF/closed FD при выключенном GC, включая repeat cancellation.
Findings01/02 CLOSED на R2,03 CLOSED на R3. Final CI:614 unit/393 integration,
27 browser,6 relay+6 lifecycle на normal/exact Docker29, все clean-source gates PASS.
C8 сообщил122 scoped tests/77.49s и2 независимые AutoBackend probes PASS, без findings;
его local checks отделены от прочитанного CI evidence. C0 принял отчёт на том же
head/tree. Owner VM пока остаётся на0b7e24ee/connect2: отдельная задача
M2-ENV-04-CONNECT5-MIGRATION готовит exact source/image/state переход, без запуска
на VM в этом поручении. R1/R2/R3 history — runbook§0.6.19–0.6.24.

JSON responses ≤64 KiB. getFile принимает только opaque canonical FetchPermit.image_file_id;
file_unique_id/filename/provider metadata не заменяют его. Relative file_path bounded,
без scheme/host/query/fragment, backslash, percent escapes, empty/dot/dot-dot segments;
не применять urljoin к произвольной строке. File download только фиксированного origin,
без redirects, stream через прежний read_image actual≤10MiB. Общий FETCH≤20s, прежние
20M pixels/8192-side/static/WebP-before-native guards, hash/bytes и S3 fencing сохранены.
Image Content-Length/Type не authority. Missing/invalid terminal, readonly transport
outage — bounded retry; download не является отправкой человеку.

Токен находится в Bot API request path по протоколу: отключить/редактировать его во
всех HTTPX/httpcore/exception/tracing logs до первого запроса, не логировать full URL,
response body, текст/получателя или claims. Проверить secrets redaction на failures.
Внутренний ImageProvider и простой explicit CONTROLLED/TELEGRAM dispatch достаточны;
будущий универсальный plugin registry не нужен.

### 10.7. Product policy, новый intent и replay

Ровно один продуктовый key **messaging.manual_send**, BOOLEAN/ESSENTIAL. Реальный
EntitlementService используется с прежним R4 precedence: structural→subscription
inactive→mode inactive→missing key→mode restriction→typed value. NORMAL/GRACE/LIMITED
позволяют корректный true key; SUSPENDED/missing/false/inactive запрещают новый send.
Security live OWNER отдельно и не ослабляется entitlement. Read/history/private grants,
durable inbound/FETCH не блокируются billing; данные не удаляются при ограничениях.

Внутренний API сервиса допускает этот known product key; старый GET billing по-прежнему
возвращает ровно пять TEST decisions. Старые TEST catalog/hash/SEALED revisions и
initializer не менять. Отдельный migrator-only initialize_local_messaging_billing:
fresh LOCAL/TEST Workspace без billing, фиксированный test_messaging revision1 с
одним BOOLEAN true/ESSENTIAL key, обычные ACTIVE+COMPED/NORMAL/account и provisioning
Audit. Использовать прежний global catalog lock(1295070019,1), DRAFT→SEALED и
immutable manifest. Finite explicit TEST interval; exact repeat NOOP. Existing M1,
partial/drift state — conflict+rollback, никакой silent repin/upgrade старой subscription.
Это тестовое подключение, не pricing, paid billing, plan editor или production catalog.

SQL перед новым TELEGRAM intention и перед DISPATCHING проверяет canonical billing
с DB time/SEALED revision/type/value; caller allow=true недостаточен. Python/SQL
решения совпадают; структурный сбой —503, не ложное NOT_ENTITLED. CONTROLLED internal
path сохраняет принятый M2.1 scope. OWNER actor перед send берётся из receipt, не Job JSON.

Новый **TELEGRAM** HTTP POST использует две последовательные короткие auth.workspace:
1. Live OWNER, строгий body/key, canonical conversation/binding и exact receipt probe.
   REPLAY/conflict разрешаются прежде новых route/product checks. Закрыть обе DB
   connections/auth admission до следующего network step.
2. Для нового намерения getBusinessConnection≤5s вне DB; затем новая auth.workspace,
   повтор cookie/session/liveOWNER/canonical binding и **сначала** idempotency replay/
   conflict. Конкурентно созданный exact receipt возвращается даже при stale response.
3. Только если receipt ещё нет: generation/version CAS, observed rights/window,
   locked coherent billing snapshot → EntitlementService → guarded request_manual_text
   в этом unit. DB повторяет policy guard и атомарность Message/receipt/Audit/Outbox/Job.
   Ответ после commit/release admission. CAS mismatch→503 UNAVAILABLE, known deny→409
   NOT_ALLOWED, без нового intent. Observation может быть сохранён с bounded rejection,
   но отказ не выдаётся за принятый Message; не полагаться на случайный rollback.

Public CONTROLLED POST допускается только LOCAL/TEST: одна auth.workspace, live OWNER,
receipt recognition, настоящий EntitlementService для нового intention и прежний append;
Telegram HTTP не вызывается. Это позволяет реальные API/browser tests без секретов.
Старый внутренний CONTROLLED command contract не меняется.

Это не nested UOW и не HTTP внутри business transaction. Не использовать convenience
send_manual_text/read_image wrappers, которые открывают второй UOW внутри route.
Receipt replay требует текущую session/liveOWNER и совпадение actor/workspace/text/key;
последующий plan/connection restriction не скрывает ранее принятую операцию. Replay
не отправляет заново; UNKNOWN остаётся UNKNOWN. Потеря ответа: сохранить исходные
actor/Workspace/conversation/text/key, восстановить auth/CSRF и повторить то же
намерение; новый key не является recovery. Worker отдельно перепроверяет policy.

### 10.8. Пять owner routes и wire contract

Префикс **/api/v1/workspaces/{workspace_id}**. Только live OWNER; ADMIN/PROVIDER,
revoked session/membership, cross-Workspace и неправильные relation не разрешены.

| Method/path | Permission / результат |
|---|---|
| GET /channel-connections | messaging:read; collection statuses |
| GET /conversations | messaging:read; collection conversations |
| GET /conversations/{conversation_id}/messages | messaging:read; history + current file/delivery |
| POST /conversations/{conversation_id}/messages | messaging:send; ровно {text}, ровно один Idempotency-Key, no If-Match;202 ACCEPTED/REPLAY |
| POST /conversations/{conversation_id}/messages/{message_id}/files/{file_id}/read-grant | messaging:read; ровно {}, cookie/Origin/CSRF;200 {url,expires_at}, fixed60s; idempotency не применяется |

Все public objects strict/additionalProperties=false; UUID lowercase canonical,
UTC timestamps с6fractions, bigint version/size decimal strings. Никаких bot/provider
external IDs, raw dicts, storage keys/claims/Jobs/fingerprint/Outbox internals в DTO.
Signed URL по принятому §9 содержит bearer locator/signature; отдельно key не выдаётся.

| DTO | Точные поля |
|---|---|
| Connection | connection_id,business_id,provider,state,observed_at,created_at,version |
| Conversation | conversation_id,connection_id,business_id,client_id,created_at,version,reply_window_expires_at |
| Message | message_id,conversation_id,direction,content_type,text,occurred_at,created_at,version,file,delivery |
| File | file_id,status,error_code,manifest; manifest только READY: mime_type,size_bytes,width,height |
| Delivery | status,error_code,completed_at,version; PENDING/DISPATCHING/SENT/FAILED/UNKNOWN |
| Send response | workspace_id,receipt_id,message_id,accepted_at,outcome; original metadata, outcome ACCEPTED/REPLAY |

TEXT.file=null, inbound.delivery=null; missing dates/error fields nullable по state,
все nullable поля явно присутствуют. Connection.state: AVAILABLE/DISABLED/RIGHTS_MISSING/
UNVERIFIED/UNAVAILABLE; AVAILABLE — observed enabled/can_reply, не обещание открытого
окна или разрешённого тарифа. Stale/invalidated →UNVERIFIED; last probe failure→
UNAVAILABLE; successful disabled→DISABLED; enabled без rights→RIGHTS_MISSING.
Для CONTROLLED state отражает существующее active/inactive, без выдуманного Telegram
observation; observed_at=null, reply_window_expires_at=null. Manifest width/height
bounded integers; file/error codes — закрытый bounded набор существующего домена.

Три collection GET: {items,next_cursor}, defaultlimit25, 1…100, только limit/cursor;
duplicate/extra query запрещены. Stable(created_at,id) DESC; history — creation order,
provider occurred_at показывается отдельно. Cursor≤1024 canonical unpadded base64url
JSON: v=1,endpoint,workspace_id,direction=DESC,created_at,id; messages дополнительно
conversation_id. Endpoint=CHANNEL_CONNECTIONS/CONVERSATIONS/MESSAGES. Exact anchor
проверяется в том же tenant/conversation; malformed/чужой/missing anchor→422. SQL
limit+1≤101; конец next_cursor=null. Cursor не credential и не frozen-history snapshot.
Остальные routes query не принимают. Read-grant использует текущий owner unit и
local presign, возвращается после commit; TTL/revoke semantics §9 неизменны.

Text — прежний exact1…4096 scalars/≤16384UTF8 bytes, valid Unicode, no NUL и не
whitespace-only, без trim/NFC. AuthBoundary body cap **64KiB только exact POST messages
route**; прежние routes остаются4096 bytes. Header/actual streaming/Content-Length/
3s read/Host/Origin/CSRF/session locks и bounded errors сохраняются. Новый webhook
имеет отдельный cap; он не получает глобальное исключение для Console. CORS уже
имеет GET/POST и нужные headers: расширение allow-list не нужно; positive/negative
configured-origin preflight tests обязательны. Generated OpenAPI/consumer notes
меняются только additive messaging/webhook contracts; frozen M1 snapshots сохраняются.

Errors: прежние401/403 security;404 NOT_FOUND для чужого/unknown/mismatched/not-ready
file;409 IDEMPOTENCY_KEY_CONFLICT или NOT_ALLOWED для нового запрещённого intent;
422 INVALID_REQUEST для DTO/key/query/cursor/UUID; прежние413/415/429/500 envelopes.
503 union сохраняет boundary UNAVAILABLE и BILLING_STATE_UNAVAILABLE с bounded
state_reason только для структурного billing сбоя. Provider body/SQL/секреты наружу
не возвращаются. Current delivery/recovery читается history, отдельный retry route
или optimistic SUCCESS из202 не добавляется.

### 10.9. Конечная проверка и внешняя граница

Критерии остаются M2-A01…A12. Нужны tests/assertions→строка→actual SHA/run:
verified webhook/unknown route/binding A01; receipt/Inbox commit/repeat/crash A02;
HTTP intention/replay/atomic rollback A03; claim/CAS/429/exhaustion A04; real wire
accept+response loss/process crash→UNKNOWN/no-resend A05; typed Telegram fixtures/
photo/native/echo/edit/delete/out-of-order A06; real provider stream→PG/private S3/
HTTP grant A07; все пять routes и forged claims/relations/liveOWNER/revoke A08;
rights/window/revocation/errors и честный observed status A09; migration/M1/M2.1/2
regression/contracts/gates A12. A10 и полный A11 через Console остаются M2.4.

Полный HTTP/PG путь обязателен. Для ambiguous send — локальный HTTP server реально
принимает POST и рвёт ответ, wire counter переживает restart worker; MockTransport
не заменяет этот case. Поддерживаемые event fixtures и negative parsing можно
проверять детерминированно. Внешний Telegram не включать в обычный CI и не подменять
его успехом fake adapter. Проверить отсутствие provider/S3 I/O при удержании DB,
secret redaction, future-date/window boundary, concurrent refresh/replay, drop
OWNER/billing между enqueue/dispatch, TTL/host/path signed GET и downgrade refusal.

Сохраняются штатные ci.sh/test_browser.sh, оба clean-source gates, exact inventories,
full migration cycles, generated contracts, reproducibility и smoke. Старые fixtures
адаптируются только по новой схеме/current revision с объяснением; guards не удалять.
C8 после реализации независимо проверяет новый Telegram/API trust и effect boundary;
настоящее C2/C3/C1 CONTRACT согласование его не заменяет.

Live TEST: C6 даёт один исполнимый runbook от точного SHA: safe secrets injection,
getMe/getBusinessConnection/getWebhookInfo/binding, тестовый HTTPS webhook и exact
Console origin/secure cookies, backend/worker/scheduler, private DB/S3. Signed S3 URL
должна быть доступна браузеру по HTTPS с исходными подписанными host/path: внутренний
minio hostname после подписи не заменять. Existing loopback Compose не готовый
internet deployment. Пользователь подготовил bot/Owner/Client и секреты в password
manager; подключать manager к чату не нужно. Доступ к runtime/HTTPS блокирует только
соответствующий live check. Платная инфраструктура — только после отдельного
предложения конкретной цены; в этом поручении расходы/production не разрешены.

Внешний adapter smoke: Client text+photo → корректные owner API/history/private GET
→ ручной API reply → Client получает text; отдельно observed rights/native behavior.
Это подготовка A11, не завершённый Console journey. M2.3 code/API можно принять с
явным external-check blocker, но M2 целиком нельзя завершать без реального A11.
Следующий C5 начинает только от принятого интегрированного API и отдельного main CI.

Первичные источники, проверенные C0/C3 2026-09-21:
[Telegram Bot API](https://core.telegram.org/bots/api),
[connected business bots](https://core.telegram.org/api/bots/connected-business-bots),
[HTTPX timeouts](https://www.python-httpx.org/advanced/timeouts/),
[HTTPX transports](https://www.python-httpx.org/advanced/transports/),
[HTTPX environment variables](https://www.python-httpx.org/environment_variables/).
Документация объясняет provider constraints, не доказывает доступ/права конкретного
тестового аккаунта. OPEN-052/085 остаются внешними account/release checks.

### 10.10. Реализационное отображение принятого §10

В Draft PR #20 §10 реализован через `asm.telegram`, пять owner routes в
`asm.messaging.http` и миграцию `0007_telegram_api.py` (0007→0006). Это описание
кода для review, не изменение принятого контракта и не объявление VERIFIED.
Точный final head/tree, tested merge/parents и результаты gates находятся в PR receipt.

- Единственные новые таблицы — `platform.telegram_connection_state` и
  `platform.telegram_update_receipts`; runtime не получает прямой доступ. Typed
  capabilities сохраняют receipt/Inbox/Job одним commit. Первый receipt содержит
  DB fingerprint и timestamp; повтор возвращается до новых routing/rights gates.
  Tenantless receipt допустим только для unsupported update без business route.
- `telegram_worker_probe` сохраняет claim/generation/version. Затем readonly HTTP
  выполняется без DB unit; `telegram_begin_send` сверяет claim и оба CAS значения,
  текущего OWNER, Business/connection, окно и product permission перед durable
  DISPATCHING. Старый `messaging_begin_send` не принимает TELEGRAM. Owner refresh
  отдельно проверяется через `telegram_owner_observe` и transaction xid перед
  новым намерением; replay читается раньше refresh/product gate в обеих auth units.
- Public CONTROLLED POST использует одну guarded UOW и настоящий product gate;
  внутренний CONTROLLED kernel остаётся прежним M2.1 LOCAL/TEST механизмом.
  TELEGRAM worker дополнительно проверяет product permission перед отправкой.
  Новый product key не включён в пять frozen TEST keys GET billing. Fresh-only
  initializer `initialize_local_messaging_billing` и trusted binding исполняются
  одним migrator commit; `setWebhook` вызывается после него.
- Retry delay хранится в Job вместе с canonical finalized attempt. Повтор finalize
  читает сохранённый outcome/due; не вызывает provider и не заменяет SENT на UNKNOWN.
  `retry_after` не продлевает прежние five-claim/15-minute limits. UNKNOWN terminal:
  новый idempotency key не является способом recovery.
- `ChannelImageProvider` направляет TELEGRAM photo в прежний FETCH/validation/private
  S3 pipeline. Fixed-origin getFile path проверяется до download; encoded response
  отвергается до HTTPX decompression. Grant подписывается локально внутри текущей
  owner UOW, возвращается после commit, TTL60 и relation/tenant checks прежние.
- `httpx==0.28.1` перенесён из dev в runtime без изменения package versions/hashes.
  Generated OpenAPI дополнен webhook и пятью routes/DTO; прежние paths/schemas,
  auth/tenancy/R4 snapshots и frontend сохраняются.

Исполнимый operator/live порядок, включая safe runtime injection, fresh Workspace,
независимый Owner ID, HTTPS, secure cookie и исходный HTTPS signed origin, находится
в [M2_TELEGRAM_LOCAL_TEST](../runbooks/M2_TELEGRAM_LOCAL_TEST.md). Live Telegram и
Console A11 требуют отдельного наблюдения; автоматические tests их не подменяют.

### 10.11. C8-M2.3-01 — временные проверки после получения блокировок

C0/C2 исправили выполнение принятого temporal admission: `messaging_manual_send_allowed`
снимает DB clock после получения всех billing locks. Canonical owner request и
worker повторяют окончательный `telegram_can_send` после billing gate, перед созданием
нового intention/DISPATCHING. Иначе ожидание account lock могло пересечь конец
subscription/service-mode interval или24h window при ещё действующей lease.

Прежние ранние отказы, receipt replay, structural precedence, R4 snapshot,
lock_timeout2s и lease30s сохраняются. Шесть PG barrier regressions проверяют
worker/owner × subscription/mode/window, подтверждённое ожидание через runtime
observer/pg_blocking_pids, release после DB deadline и отказ без effect/partial intent.
Независимый targeted C8 и exact implementation CI приведены в активном handoff;
final head/CI документационной приёмки — в PR receipt. Принятый scope §10 сохраняется.

### 10.12. Operational extension — M2-ENV-04 TEST egress

**Current C0 disposition2026-10-07: C8-MIG-01/P2 CLOSED на exact R2.**
Headf1c7aca724778e41671f2754bb85885507c4f14d/tree4f28480ef1458141422a14514473c05f49193fe6:
independent C8 PASS154 tests/3 original repro/50 additional probes; C0 own prior5
probes и final CI37629816347/9 jobs подтверждают cross-direction audit fix.
Новый **C0-MIG-OWNER-01/P2 OPEN** относится только совместимости сохранённого
receipt basename `.intent.json`: reviewed R2 reader отвергает legacy ACK intent.
§10.12.1 schema2 audit, source/client pins и contracts вне basename validation
сохраняются. C6 issued narrow fix/test fixture, current M2_HANDOFF/runbook§0.6.30.
Actual owner cached images/independent receipt pin пока не аттестованы.
M2 IN_PROGRESS/ENV04 REVIEW; owner execution blocked. Docs CI37640492805
attempt2 SUCCESS после одного browser rerun; original Audit paging failure
сохранён как C0-CI-AUDIT-01/P3, separate C5 TODO, не scope C6.

<details>
<summary>История — R2 source/CI PASS до targeted C8 verdict</summary>

**Current C0 disposition2026-10-07: R2 source/CI review PASS; targeted C8 pending.**
Implementationf1c7aca724778e41671f2754bb85885507c4f14d/tree4f28480ef1458141422a14514473c05f49193fe6
исправляет cross-direction audit binding. CI37629816347 all9 jobs/clean-source
SUCCESS; C0 повторил3 исходных negative repro и2 controls —5 targeted PASS.
C8-MIG-01/P2 остаётся OPEN до targeted verdict. §10.12.1 schema2 и поведение
не меняются этим coordination. C6 implementation завершён; активный этап — C8-R2.
Evidence/ограничения — current M2_HANDOFF/runbook§0.6.29. Owner applicability ещё
не аттестована; M2 IN_PROGRESS/ENV04 REVIEW, VM/ACK/activation/sends/merge не выданы.

</details>

<details>
<summary>История — C8 finding и выдача C6-R2</summary>

**Current C0/C8 disposition2026-10-07: CHANGES_REQUESTED; C8-MIG-01/P2 OPEN.**
На implementation3f65be7a60a1271247d04f23cbe0b151f82d65a1 C8 выявил и C0 воспроизвёл
непроверенный forward audit при rollback. Выдана узкая C6-R2: до effects проверить
существующий forward audit, закрепить inventory/hashes в rollback intent и проверять
на resume/retry; done требует result в обоих направлениях. Valid partial rollback
сохраняется. Это устранение нарушения прежнего audit-preservation contract, без
изменения domain/TLS/deadlines/UNKNOWN. Findings01/02/03 остаются CLOSED.
Migration REVIEW до final CI/targeted C8; VM execution не выдана. Подробности и
reproducer — current M2_HANDOFF/runbook§0.6.27; M2 IN_PROGRESS/ENV04 REVIEW.

</details>

<details>
<summary>История — C0 disposition до нового C8 finding</summary>

**Current C0 disposition2026-10-07: migration source/CI review PASS.**
Implementation3f65be7a60a1271247d04f23cbe0b151f82d65a1/tree5e4d0c741a2dcf9967c9c1502bc97ca6a78c9797
проверен на CI37607152590: все9 jobs/clean-source SUCCESS. Новых C0 blockers нет;
migration остаётся REVIEW, выдан независимый C8-M2-CONNECT5-MIGRATION. §10.12.1
не меняется; прежние connect5 findings01/02/03 CLOSED. Owner applicability/images/
receipt DAG ещё требуют отдельного read-only attestation после C8; это не live PASS.
Exact scope/evidence/ограничения — current M2_HANDOFF и runbook§0.6.26.
M2 IN_PROGRESS, ENV04 REVIEW до actual A09/A11; VM/ACK/activation/sends/merge не выданы.

</details>

<details>
<summary>История — C0 acceptance connect5 и выдача C6 migration</summary>

**Current C0 disposition2026-10-07:** accepted connect5 implementation
**14f794b650c935c47ab1e78474fda0d1df0a7277** / tree
**72b824d85091076a025998a71e564deab805b1cf**, actual final CI37531243359 all gates SUCCESS
и независимый C8-M2-CONNECT-BUDGET-R3 PASS. C0 принял code/runner scope; M2 IN_PROGRESS,
ENV04 REVIEW до actual A09/A11. C3 findings01/02/03 CLOSED.
Owner VM последним receipt остаётся на exact0b7e24ee/recovery-v2/connect2,
Telegram disabled/empty, binding committed, ACK NOT_ATTEMPTED.
Отдельное active поручение **M2-ENV-04-CONNECT5-MIGRATION** разрешает C6 подготовить
и проверить новый source/image/state transition в disposable CI. Ordinary strict
source/image/recovery guards сохраняются; old source принимается только узким
exact predecessor attestation. Original baseline/recovery receipts, binding,
fixed TEST interval и canonical data не переписываются.
VM execution, real Telegram/queue/ACK, activation/setWebhook/send и merge сейчас
не выданы. Детальный scope — current M2_HANDOFF; приёмка — runbook§0.6.24 и единый receipt.
Ниже сохранены исторические dispositions, а не дополнительные активные поручения.

</details>

**Историческая C0 disposition2026-10-06: PASS на implementation0b7e24ee425ebb429bf87dfe382cbd3fab883028;
C8-04/05 CLOSED, прежние01/02/03 CLOSED.** Independent C0 source/evidence review +17
bounded local probes; реальная execution — CI37385698548 all3 SUCCESS на merge
fdfbe35974fa548b722622132aa0edb3a30c9bf5/tree14a4033b849c736235653a5a85ec9e5112bfe727.
Нового отдельного C8 agent execution не заявлено. Полный scope/ограничения — runbook§0.6.15
и current TASK_REGISTER. Owner recovery/preflight на exact0b7e24ee PASS
2026-10-06T07:58:54.204446+00:00, SSH_EXIT0: original baseline/private inputs/images
сохранены, actual Telegram runtime disabled/empty. C0-M2-ENV04-04 CLOSED по этому receipt.
Следующий шаг — только discovery по runbook§0.6.16: временный operator-only enabled=true
и pin того же cached image ID; persisted inputs и существующий runtime не меняются.
Проверенный external ID сохраняется private до отдельного atomic setup; installed
webhook/Owner/rights проверяет существующий provisioner. M2 IN_PROGRESS, live A09/A11
ещё впереди. Ниже сохранены прежние, superseded dispositions.


CI37367018261 attempt2 после восстановления Actions реально исполнил exact Docker29:
6 transport, fresh/recovery, recover-stopped/recover-missing и legacy-disable PASS.
Следующий legacy-stop остановился до своего held-state baseline: test controller
ожидал dual-family relay, но предыдущий legacy rollback оставил stopped IPv4-only
container. Узкая коррекция harness перед каждым независимым fixture восстанавливает
только disposable seed relay из fresh model и проверяет оба private endpoints до
создания UNKNOWN/session. Original before/audit предыдущих cases и DB rows не
перезаписываются; sealed-catalog guard,180s и все assertions сохранены.
Это fixture sequencing defect, не runner incident; legacy-stop PASS и полный
final-head CI после коррекции ещё ожидаются в едином PR24 receipt.


**C6 correction REVIEW, 2026-10-06.** Для04/05 добавлены immutable rollback intent
с exact before/disabled dotenv bytes и stage receipts; audit hashes не заменяются
текущим hash после own write. Completed rollback retry проверяет original operation
before/after и не повторяет recreate. Recovery intent привязан к exact generation;
stopped relay проверяется включая image/tag/config/process/network, missing допускается
только в подтверждённом recreate/stop переходе. Остальные guards и deadlines прежние.
Новые real isolated cases и final-head результаты — runbook§0.6.14/PR24 receipt;
приёмка04/05 остаётся targeted независимому C8/C0. Ниже сохранён исходный verdict.

**Targeted C0/C8 disposition 2026-10-06: CHANGES_REQUESTED, C8-M2-ENV04-04/05,
P2 / E05.** Reviewed head94a402f3cf7c9d5ad9cd5837cd3d91d738fcf684, final CI37358453152
SUCCESS. Native strict mapping/full executed cases подтверждены; legacy rollback
retry после собственной enabled=false записи и recover retry при stopped/missing
relay внутри recreate блокируются до repair. Полное evidence — runbook§0.6.13,
bounded correction — единственный active M2_HANDOFF. Прежние01/02/03 CLOSED.

Interruption/resume — часть существующего E05, не новое расширение domain scope.
Original before/audit сохраняются byte-for-byte. Собственная разрешённая запись
disable-first должна иметь проверяемый transition и возобновляться без общего
исключения runtime_env hash. Ожидаемые stopped/missing/recreated состояния своего
relay не должны требовать successful running topology до repair; source/config/
image/input/DB/HTTPS/emptyTG/gateway/unrelated guards при этом сохраняются.
Unknown/foreign relay или state не принимаются. After/receipt/PASS только после
полного подтверждения итогового состояния; rebaseline/manual state patch запрещены.
Explicit legacy/schema2 rollback и recover требуют настоящих isolated failure/resume
cases на exact Docker29, затем final CI и targeted C8 перед owner issuance.

**Operational finding 2026-10-05 — C0-M2-ENV04-04/P2:** на owner Docker29.8.2
extra_hosts сохраняет mapped IPv6 в model/HostConfig, но Engine Unmap() записывает
в hosts второй IPv4. Actual AF_INET6/flags=0 у api/worker получает посторонний
native IPv6. Actual owner deployment/preflight ещё не принят; mapping correction
подтверждена на reviewed head, interruption/retry correction — верхний M2_HANDOFF.
VM receipt — runbook§0.6.11; targeted C8 CHANGES_REQUESTED04/05 — §0.6.13.
Прежние C8-01/02/03 CLOSED сохраняются.

Семантический контракт не ослабляется: AF_UNSPEC/AF_INET/AF_INET6 с исходными
flags=0 на всех трёх callers возвращают только адреса того же private relay,
без public/DNS fallback. Разрешён bounded private IPv6 endpoint/IPAM этого relay
в opt-in overlay, если требуется совместимость; он не меняет official TLS/Host/
SNI, fixed upstream, client/config blobs, deadlines/retries, permissions/media
или UNKNOWN. Нельзя исключить AF_INET6, подменить его AI_V4MAPPED/AI_ADDRCONFIG
или изменить global host networking/daemon ради PASS.

Existing partial deployment — отдельное проверяемое начальное состояние:
schema1/source c29aabd36f4e81ee2d4b835bd921fa2de1ae5b14, before PRESENT / after ABSENT,
relay running и disabled/emptyTG callers уже пересозданы. Guarded helper recovery
сохраняет первоначальный before byte-for-byte, сравнивает с ним actual state и
явно проверяет source/schema/generated-state transition. Reset/rebaseline и
неявное принятие старого source_sha запрещены. Новый receipt/PASS — только после
mapping/readiness/preservation; interruption не оставляет ложный commit receipt.
Fresh deploy и explicit disable-first rollback сохраняются. Targeted C8 проверяет
новую mapping/recovery boundary после real Docker29/full CI; owner VM changes —
только отдельным шагом C0. Domain/API/production/M3 scope прежний.

C6 correction реализует второй native ULA listener того же pinned Xray, тот же
fixed upstream/selected outbound. Internal IPv6-only bridge имеет непересекающийся
/64 ULA, static ::2 и отдельный dynamic /65; existing default gateway сохраняется.
Model/HostConfig/hosts и resolver flags=0 проверяются на api/worker/operator. Нет
mapped-address substitution, host sysctl/DNS patch или caller TLS/config change.

Generated schema2 проверяет оба private endpoints. Явный recover разрешён только
из schema1/source c29aabd36f4e81ee2d4b835bd921fa2de1ae5b14 и original partial before.
Private immutable recovery-v1 хранит прежние bytes и hashes inputs; recovery-v2 —
новую generation. Atomic manifest + exclusive operation lock сохраняют resumability.
Оригинальный before не переписывается, accepted after/receipt появляются лишь после
полного сравнения, mapping и readiness. Completed retry не пересоздаёт callers.
Изменение baseline/input/schema/source/image/DB/gateway даёт STOP, не новый baseline.
Rollback явный: disabled with route → remove caller route → stop relay. Оба bounded
private bridges и stopped relay сохраняются без application endpoints для audit;
owner inputs, volumes и durable receipts не удаляются. Legacy partial rollback требует
тех же explicit from/accepted SHA и guards. Recovery после recorded rollback запрещён.
Повторные synthetic E05 lifecycles сохраняют SEALED catalog первого fixture;
исходный empty-DB guard выполняется до него. Между cases проверяется полный exact
fingerprint31 таблицы после scoped cleanup, без исключения неизвестных rows/сброса
immutable catalog. Каждый held before/after относится к той же actual caller DB.

C6 real foundation evidence CI37356534441: оба lifecycles и все E05 preservation
assertions PASS; recovery157s при180s. Это не заменяет обязательный exact Docker29
final-head gate после исправления isolated DNS fixture; owner VM не менялась.
Exact-source execution receipt и команды — runbook§0.6.12/PR24; это не новый C8 verdict.

C0 разрешил отдельный opt-in overlay на принятом Xray26.9.9 digest (runbook§0.6),
без изменения §§10.1–10.11/domain/API/app. Callers ровно api/worker/telegram-operator;
official api.telegram.org сохраняет TLS/SNI и фиксируется на устойчивом private IP
для A/AAAA, включая stop/recreate. Relay opaque TCP, non-root/read-only/default deny,
один выбранный VLESS/TCP/REALITY/Vision connection, без direct/DNS target fallback,
sniffing, TLS termination, HTTP retries или TG/DB/S3 credentials. Scheduler прежний.
Timeout/retry/permission/media/private-S3/UNKNOWN semantics неизменны; relay health
не является auth/DB readiness или разрешением send. Подготовка проверяет exact Git
blobs, private files, image/config и непересекающийся IPAM; runtime остаётся disabled.
Rollback сначала выключает Telegram с mapping, затем снимает route, сохраняя durable
state/receipts/env/volumes. E01–E06 проверяются настоящими Docker/PG/S3 и controlled
TLS wire; fixture CA/peer не входят в live config. Самостоятельного live включения
нет; C0 выдаёт deployment после scoped C8/final CI. ADR239/production/M3 не изменены.

C0 final targeted disposition 2026-10-05: **C8-01 CLOSED/PASS** на implementation
d57ae07f10cd603910876068da444829b326bdab, CI37297119410 SUCCESS; прежние02/03 CLOSED.
Принятый two-field private runtime overlay сохраняет HTTPS origin/endpoint из
исходных inputs отдельно от staged TG. Independent pre-live baseline, strict drift,
actual DB/Secure session/UNKNOWN preservation проверены real runner и targeted C8.
Изложения прежнего open finding ниже — история причины, не незакрытая текущая задача.
Contract/domain scope не меняется. Этот code-acceptance receipt исторический;
current gate — runbook§0.6.11/верхний M2_HANDOFF. Source и partial VM deployment уже
подтверждены; IPv6 mapping/recovery correction, live A09/A11 и merge/main CI впереди,
M2 остаётся IN_PROGRESS.

C0 targeted disposition 2026-10-05: C8-02/03 закрыты на implementation
2536a1aa2b41792fff381c4d222906e2ff9ad23c; остаток C8-01/E05 требует сохранения
действующих non-TG runtime настроек. Принятый pre-live env состоит из `.env` с PG/S3
credentials и HTTPS origin/endpoint из `.env.telegram`; позднее тот же файл получил
staged TG inputs, не применённые к running callers. Исключение всего файла —
неполная коррекция: непреднамеренная потеря HTTPS значений не принимается.

Минимальный контракт — private runtime-модель сохраняет действующие
`ASM_AUTH_ORIGINS` и `ASM_STORAGE_ENDPOINT`, не импортирует staged TG activation
fields, не меняет исходные private input bytes и проходит полное строгое сравнение
с actual disabled callers до recreate. Разрешён узкий private overlay вне checkout
для этих двух проверенных values; без общей config framework или ручного переноса
owner. Staged inputs доступны отдельно explicit one-shot operator; их будущее
применение к runtime требует отдельного C0 live шага. Rollback сохраняет disable-first
с mapping, затем снимает route; допустим только enabled=false в runtime source,
прочие inputs/durable state остаются неизменными.

Реализация остатка01 передана C6 на REVIEW: prepare создаёт private runtime.json600
в canonical state700 вне checkout, только services.api/worker.environment с этими
двумя keys. Values разрешаются из accepted env files штатным Compose config без
source/eval; JSON экранирует повторную Compose interpolation. Hash и повторная
деривация проверяются перед resolved model. Snapshot строго сравнивает модель
с actual callers, без исключений для HTTPS/TG/DB/S3. Runtime overlay сохраняется
при снятии route, исходные private files не переписываются. Regression начинает
с независимого двухфайлового HTTPS baseline до generator. Console evidence использует
настоящий TLS/Secure cookie; E02–E04 transport и closed02/03 guards не ослаблены.
Это не targeted C8 PASS; final execution receipt и готовая процедура — runbook§0.6.9/PR24.

Actual SQL DB identity api/worker и её сохранность при recreate обязательны;
durable evidence относится к той же БД. Canonical outside-checkout boundary
проверяется до effects, requested symlink components не нормализуются в разрешённые
пути. Domain/API, TLS, timeouts, permissions и UNKNOWN/no-resend прежние. Подробный
targeted verdict — runbook§0.6.8; текущий correction REVIEW — §0.6.9/активный M2_HANDOFF.

<details>
<summary>История — первая C6 correction формулировка до targeted C8</summary>

C8 correction E01/E05: deployment читает текущий runtime `.env`, не применяет
staged `.env.telegram`; staged inputs сохранены для отдельного C0 operator шага.
Rollback выключает enabled flag именно runtime `.env` до снятия mapping, не меняя
остальные values или staged file. Snapshot проверяет actual SQL DB identity api и
worker и её сохранность при recreate; durable evidence должно относиться к этой
же БД. Private state canonical outside-checkout проверяется до effects, при этом
requested symlink components не нормализуются в разрешённые пути. Domain/API,
timeouts, TLS, permissions и UNKNOWN/no-resend остаются прежними.

</details>

#### 10.12.1. Explicit connect2 → connect5 migration (historical operator candidate REVIEW)

`M2-ENV-04-CONNECT5-MIGRATION` introduces a separate operation, not a relaxation of
`recover`. Its only predecessor is completed recovery-v2 at
`0b7e24ee425ebb429bf87dfe382cbd3fab883028` / tree
`14a4033b849c736235653a5a85ec9e5112bfe727`. The target is an exact clean descendant
of accepted base `14f794b650c935c47ab1e78474fda0d1df0a7277`, retaining client blob
`525381357de76ea1c570fd864f8df5e9781a87e2` and the frozen dependency/image pins.
The predecessor checkout remains intact; the candidate has a separate checkout,
an identical private runtime `.env`, and the same canonical outside-checkout state.
Both checkouts and their private `.env*` inventories are attested and archived.

`migration-attest` is read-only. It verifies the original v1 audit, completed v2
receipt and caller IDs/images, disabled/empty runtime, HTTPS/config/profile/routes,
actual caller DB identity and 31 canonical table fingerprints. The caller supplies
an independently pinned last operator receipt SHA256; its complete predecessor
receipt DAG must include the committed binding. A changed staged Owner ID is
accepted only through the exact C0 correction journal and byte reconstruction of
the archived original. Unexplained changes, missing receipts or foreign sources
stop before runtime mutation. Full copied Git blobs are checked offline in both
old images; cached images with different bytes are a STOP, not an automatic rebuild.

C6-M2-OWNER-RECEIPT-COMPAT admits only `[a-z0-9-]+(?:\.intent)?\.json` for
both current/root basenames and parent keys. This includes the issued
`asm-telegram-ack-old-lifecycle-owner2-0b7e24ee.intent.json` without renaming,
rewriting or dropping any retained receipt. The optional `.intent` suffix does not
permit other dotted names, traversal, separators, absolute parent keys or symlinks.
Same-parent, private owner/mode/size, independent root pin, complete DAG inventory,
exact byte hashes, source/tree/baseline/staged and binding checks are unchanged.
Legacy `prior_attempt_sha256` and `owner_correction_sha256` links remain mandatory
when present. This is receipt compatibility only; the historical NOT_ATTEMPTED ACK
does not authorize a new attempt. C0 accepted the focused C8 PASS and CLOSED
C0-MIG-OWNER-01 on exact31eb3360; implementation evidence is runbook §0.6.31 and
[C0 closure/owner chronology](https://github.com/Elefesys/ai-service-manager/pull/24#issuecomment-6060286080).

The separate C0-MIG-OWNER-02 candidate admits an explicit old **operator-only**
source choice. Omitted `--predecessor-operator-sha` still means exact0b7 on first
attestation. The only other accepted value is
`80e51c43e31541940f1ccf18b8281adf1a061748`, tree
`88ed308b4c56114aa977dcf91204964d9b7348e5`, with the exact128 copied-file manifest
`b88bc4ceadff581a170fdb81543b631eef6e8624d57504a049a5ac2645105195`.
Historical source/tree, complete inventory/blob hashes, the four known additions
and only changed common path `scripts/ci.sh`, and unchanged application, migrations,
dependencies, provisioner and build inputs are mandatory. Missing/extra/changed
bytes stop; no fallback, arbitrary SHA or expected provenance derived from images.
Operational predecessor/recovery/receipts and old API/worker stay exact0b7;
new runtime/development images stay exact target. The original receipt's verified
operator ID and original recovered caller IDs/images anchor the preparation.

New preparation version2 keeps `predecessor_operator_sha` and the existing
`image_proofs` keyed by the three caller roles. Each proof contains exact image ID,
source SHA/tree, kind and copied-blob-map SHA256. `prepared.json` also records the
target role proofs. Before build effects and each switch/preflight/resume/retry,
the stored proofs must equal the expected Git inventory and actual image probes.
Hashes bind these records into the existing intent/audit; there is no second DAG.
A repeat uses the saved choice; an explicit different choice stops. Recomputing
local hashes after changing only source/proof cannot substitute actual image bytes
or the original receipt image. Version1 preparation has only its previous exact0b7
interpretation and must pass full original-proof/image validation; absent fields
never infer historical provenance. Original state, DAG bytes and image IDs remain
unchanged. Cross-direction audit schema2 and all done/result guards stay required.

`migration-prepare` (600s overall bound) publishes an immutable private archive,
then builds distinct runtime/development images from `git archive` of the exact
target. No private inputs enter that context. Exact before/after IDs and retained
rollback tags are journaled. API and worker change to the new runtime image;
disposable operator uses the new development image. Scheduler, frontend, ingress,
PG/storage, relay, their mounts and config remain unchanged. In particular, the
original scheduler ID remains compatible with the predecessor's strict baseline.

`migrate` / `migration-resume` publish an immutable intent before any recreate,
with exact sources/trees, archive/image-plan hashes and allowed per-service deltas.
Each service has intent/result/done records. Only an issued, unfinished service
intent can admit its stopped/missing boundary; source/config/image/data drift is
never interpreted as an outage. Read-only repeatable-read fingerprints must remain
equal before PASS. The final state is v3, binding the intent hash and target SHA,
while continuing to reference the original recovery-v2 route generation.
Original deployment-before, recovery-v1, recovery.json, previous receipts and
private inputs are never replaced by a new baseline.

`migration-preflight` and a completed retry re-attest the result without recreating
containers. `migration-rollback` is explicit, independently resumable, and restores
the old image IDs and exact archived v2 state. The preserved predecessor checkout
is again the operational source; the candidate checkout remains the read-only
controller for rollback retry. Its old-source preflight must also succeed. Forward
and rollback audit remain; a subsequent forward call after rollback stops and
requires a new C0 decision. No automatic rollback, rebaseline or cleanup is implied.
R2 validates the complete existing audit in **both** directions before any rollback
effect and before reporting success: exact stage/result shapes, service order,
intent/source/state/database bindings, and done requiring its preserved result.
Completion must agree with the direction's historical service results and unchanged
unrelated baseline, not with container IDs created by a later opposite transition.
The immutable `rollback-intent.json` is schema version 2, with exactly `version`,
`stage`, `intent_sha256`, `forward_audit_sha256` (filename to SHA256 of exact bytes),
and `forward_runtime` (the validated snapshot at rollback entry). Resume and completed
retry require the same forward inventory/bytes and historical result binding.
Missing, changed or additional forward evidence is STOP; no re-pinning, reconstruction
from current runtime or upgrade of an older unbound rollback intent is permitted.
Valid partial forward histories remain rollbackable, including result/done and
state/completion publication gaps; an unpublished completion is not mandatory.
These R2 audit changes are accepted: C8-MIG-01/P2 CLOSED by C0 after targeted C8 PASS.
Each runtime invocation is bounded to 180s, including subprocesses. Telegram stays
disabled/empty; no discovery/setup/ACK/send/binding/billing operation is invoked.

New disposable normal + exact Docker29 jobs separately exercise real completed
predecessor recovery, SIGKILL at intent/image/state boundaries in both directions,
drift rejection, completed retry, old-source rollback preflight, held UNKNOWN/wire1,
Secure Console/private S3 and equal 31-table fingerprints. The held fixture remains
180s. Existing three jobs and their 6+6 cases remain mandatory. These facts require
final-head CI evidence and C0/scoped C8 review; this contract does not confer VERIFIED
or owner execution permission. Commands and owner draft: runbook §0.6.25.
For C6-M2-HISTORICAL-OPERATOR-COMPAT, only boundary=image (normal and Docker29)
builds the old operator from tracked archive80e before receipts and the held interval.
Intent/state shards retain exact0b7. Synthetic egress services run from the target
test-driver image, never injected into the old operator. The same nine jobs remain;
reports assert source/tree/manifest/image ID and saved proof preservation. The
candidate's evidence and limits are in §0.6.32; C0-MIG-OWNER-02 remains OPEN.

## 11. M2.4-CONSOLE — текущий ограниченный UI/browser-контракт

Принят C0 для последовательной выдачи C5 от integrated API/base
`ffc437f125aa6af4dcf1c61a035a0d5df517e062` (PR #20, push/main CI 35649907678 SUCCESS).
**C1 CONTRACT PASS**: предметная read-only проверка совместимости consumer semantics
с фактическим §10/API и App/BillingPanel выполнена; это не C8 review будущего UI. Разделы 1–10 и wire contract сохраняются.
Матрица M2-A01…A12 остаётся единственной в M2_HANDOFF; новых критериев milestone нет.

### 11.1. Один экран и достаточное обновление

В существующую Business Console добавить одну панель «Переписка»: connections с
observed status, список диалогов, выбранная история, входящие text/photo и ручной
текстовый ответ. Использовать пять routes §10.8 и generated OpenAPI; новые backend
routes/DTO, SQL, миграции, зависимости, поиск, read receipts, аватары/имена клиентов,
редактирование/загрузка файлов, AI/takeover/resume/Action Center не требуются.
Из доступного client_id можно показать короткую подпись диалога; не выдумывать имя.

Достаточно первоначального GET и явных «Обновить»/«Загрузить ещё»; после принятой
команды — GET истории. WebSocket, polling, realtime service и фоновая повторная
отправка не вводятся. Это обычный рабочий сценарий с ручным обновлением.
Пустые данные, ожидание, отказ и ошибка имеют понятные отдельные состояния.
На узком экране всё доступно без горизонтальной прокрутки; form/selection/image
controls доступны клавиатурой, labels/status/error читаются assistive technology.
Сохраняются login/logout/rotate/recovery, Business, Billing/Audit и отдельная Ops shell.

### 11.2. Authority и честное состояние подключения

UI visibility — актуальная membership.role === OWNER выбранного Workspace.
Frozen session.permissions не содержит messaging:*; не требовать этих строк и не
расширять auth contract. Сервер проверяет live OWNER на каждом GET/POST/replay.

Connection.state и observed_at показываются как наблюдение, а reply window отдельно.
AVAILABLE не означает разрешённый продукт, открытое окно или доставку. UNVERIFIED/
UNAVAILABLE и прежнее DISABLED/RIGHTS_MISSING не заменяют свежий server probe:
GET не вызывает Telegram refresh. Оставить явное действие «Проверить и отправить»
для нового намерения с объяснением текущего статуса; POST сам проверяет актуальные
rights/window/product, worker повторяет admission. Не открывать отправку по одному
client clock и не делать бессрочный UI deadlock по устаревшему observation.

Не вычислять messaging.manual_send по пяти TEST decisions GET billing: такого key
в этом ответе нет. Не скрывать history/images по billing restriction. NOT_ALLOWED
показывать как отказ нового запроса без выдуманной точной причины; два 503 envelopes
сохраняются. Обновление списка/истории не является provider resync.

### 11.3. Строгий consumer и изоляция чтений

Добавить отдельный typed messaging-api.ts по принятому OpenAPI/http_models.py.
Не копировать допущения billing wrapper: send возвращает именно202, read/grant200;
collection limit25, а BILLING_STATE_UNAVAILABLE возможен на POST send. Nullable fields,
закрытые enums, file/delivery state relations и exact object shapes проверяются.
UUID canonical lowercase; versions/sizes — decimal strings без округления Number;
UTC timestamps сохраняют шесть fractional digits. Не нормализовать входящие DTO.

Три collection GET используют limit=25, opaque next_cursor до null. Cursor и pending
response принадлежат endpoint/actor/Workspace, а history ещё conversation. Отмена
запроса дополняется generation/sequence checks: поздний ответ старого контекста не
должен вернуть чужой список, текст, image URL или изменить текущую отправку.
Проверять принадлежность результата до success/error/401/403 handling: поздний
ответ не разлогинивает новую сессию. При смене actor/Workspace, logout/recovery/denial
защищённые данные сразу скрыты.

Пагинация объединяет страницы по canonical ID без дублей, сохраняя серверный
(created_at,id) DESC. Для отображения от старых к новым можно развернуть полученную
последовательность; не пересортировывать по occurred_at или Date с потерей precision.
Явный refresh сбрасывает страницы/cursors и читает свежую первую страницу. При422
cursor не менять самостоятельно: показать ошибку и предложить fresh GET. Отсутствие
message на первой странице не доказывает отсутствие сохранённой команды. Новая
проекция того же Message заменяет старые file/delivery fields, не теряется из-за
keep-first dedupe; совпадение текста не является подтверждением receipt.

### 11.4. Exact intention и два разных вида неопределённости

Текст — исходный Unicode без trim/NFC/formatting/split. Проверять 1…4096 scalars,
≤16384 UTF-8 bytes, no NUL/lone surrogate/whitespace-only по принятому Python-набору.
Не использовать textarea maxLength=4096 как лимит scalars: HTML считает UTF-16 units.
Ввод/рендер — plain text с сохранением переносов; Enter остаётся переводом строки.
Не исполнять HTML/Markdown/URL.

При явном submit создать один key и заморозить actor/Workspace/conversation/exact
body {text}/key. Один pending intent в памяти страницы; double-click/Enter/refresh
не создают новую команду. POST содержит текущий CSRF и один Idempotency-Key, без
If-Match и query. Не писать текст, ключ, CSRF или private URL в browser storage/logs.

MessagingPanel живёт весь lifetime Console, включая login/recovery, как BillingPanel;
не unmount его условно по authenticated phase. Protected view скрыт без текущего
OWNER, исходное намерение хранится отдельно и никогда не переносится в другой
actor/Workspace/conversation. Abort/context switch не доказывает rollback.

- Потеря HTTP ответа, invalid success body, network/ambiguous5xx: сохранить прежние
  context/body/key. Восстановить session/CSRF существующим auth flow, проверить тот же
  actor/Workspace и выбранный conversation; затем только явный same-key/body replay.
  Нельзя автоматически заменять key, менять текст или replay после смены контекста.
- Подтверждённый202 ACCEPTED/REPLAY: сохранить immutable receipt/message metadata.
  Это только durable intention; дальнейшее recovery — GET истории, без нового POST
  при ошибке чтения. Не объявлять DELIVERED/READ. Delivery из history: PENDING — очередь,
  DISPATCHING — отправка начата, SENT — канал принял, FAILED — конечный отказ,
  UNKNOWN — результат неизвестен, автоматического повтора нет.
- UNKNOWN delivery является canonical terminal state, не неполученным HTTP receipt.
  Нет resend/retry button, автоматического копирования его текста или нового ключа
  для этой операции. Same-key receipt recovery не вызывает adapter повторно. После
  подтверждённого receipt возможен новый пустой composer для другого явного намерения;
  UNKNOWN не блокирует всю дальнейшую переписку.
- 401/403 не доказывает, что прежняя попытка не committed. Скрыть защищённые данные,
  восстановить текущую authority; CSRF_REJECTED обрабатывается через auth recovery.
  IDEMPOTENCY_KEY_CONFLICT останавливает replay. Даже поздний4xx после прежней
  неоднозначности не доказывает отсутствие первого intent. Если первая попытка
  получила достоверный отказ без предшествующей неопределённости, сохранить editable
  draft и показать отказ. Не отправлять его автоматически при восстановлении.

При смене контекста показывать только нейтральное уведомление о незавершённой
операции без текста/чужих IDs/URL. Явное «Завершить без повтора» может освободить
pending UI с предупреждением, что это не отмена серверной команды. Hard reload
утрачивает memory-only intent и выполняет только чтения; никаких writes из storage,
URL, mount/focus/refresh. Это не обещание восстановления ключа после закрытия страницы.

### 11.5. Private image в браузере

PENDING/FAILED показывать без фиктивного готового изображения. Для READY владелец
явно открывает изображение: current-session/CSRF read-grant POST с ровно{} и без
Idempotency-Key. Только полученный signed URL используется как img src без изменения
host/path/query, без Console auth headers и с referrerPolicy=no-referrer. Не принимать
javascript/data URL и URL с userinfo (username/password); HTTPS обязателен на HTTPS Console, HTTP
допустим для loopback LOCAL/TEST. Текст URL не выводить в UI/errors/artifacts.

Не сохранять bearer URL в local/session storage или persistent cache. При смене
контекста/denial скрыть изображение и удалить удерживаемый grant; поздний ответ не
может снова его открыть. После expires_at/ошибки GET предложить явную новую выдачу
через API, без бесконечного retry/re-sign loop. Уже выданный URL может действовать
до60s; скачанный image не отзывается задним числом. Не обещать немедленный global revoke.

### 11.6. Реальные browser journeys и ограниченный TEST harness

Playwright идёт через собранную Console, настоящий cookie/auth API, asm_runtime
PostgreSQL и private MinIO. CONTROLLED adapter/provider обозначаются явно; это не
внешний Telegram. Результат UI не фабрикуется route.fulfill happy-path JSON.

Fresh disposable TEST fixtures имеют отдельные identities/Workspaces и фиксированные
presets. Migrator настраивает identity/binding и fresh messaging billing через уже
принятые provisioners/DB functions. Старый M1 test plan/fixtures не перепривязывается.
Current DATABASE_SCHEMA_REVISION, asm_test, environment/role/secret guards сохраняются.

Отдельный finite browser runtime runner получает только asm_runtime и S3 credentials;
у него нет migrator/admin URL. Он использует существующие MessagingDatabase,
ControlledAdapter/ControlledImageProvider, Worker/FetchTransfer и durable Jobs:
normalized text/image → canonical ingest/process/fetch → real private S3. Для send
браузер вызывает настоящий owner POST, затем runner исполняет job с определённым
SUCCESS/UNKNOWN/permanent outcome. Не заполнять Message/File READY/receipt/Audit/
Outbox/Job напрямую ради успешного сценария. TEST-only seed/негативные state changes
и bounded read-only counters отделены от проверяемого runtime command path.

В compose.browser.yaml C0 разрешает только необходимую TEST-дельту: private storage
в tmpfs, bootstrap private asm-private-test, доступ браузера к signed origin и
browser-profile runtime runner. Достаточный LOCAL вариант: storage port
127.0.0.1:9000, API signer endpoint http://127.0.0.1:9000; runtime FETCH/worker использует
http://storage:9000. API read-grant выполняет local presign без S3 I/O; endpoint
не переписывается после подписи. Одинаковые bucket/runtime S3 credentials, разные
достижимые origins в своих процессах. Public bucket/listing, TLS bypass, production
endpoint switch и изменение базового compose.yaml не нужны.

Finite helper actions и arguments проверяются до записи; нет arbitrary SQL/host/
workspace selection, runtime test endpoints или production switches. Process
counter CALL/EFFECT в private temporary TEST file может переживать runner restart;
это instrumentation, не очередь. Cleanup удаляет именно disposable project/files.
Существующий test_browser.sh запускает все старые и новые journeys; проверка rendered
Compose сохраняет tmpfs/identity/environment guards и дополняет runner/storage guards.

Нужны фактические assertions для A10 и применимых A03/A05/A07/A08/A09/A12: text/image
и manual reply, пагинация/обновление без дублей, потеря202 после реального commit и
same-key recovery, UNKNOWN после worker/restart без второго CALL, private image/new
grant denial, чужой Workspace/отзыв OWNER/поздний ответ, policy/connection/error states,
keyboard/narrow и сохранность M1. Component/parser tests дополняют эти journeys для
strict DTO, всех состояний, Unicode, context races и expired grant; не заменяют БД/S3.

### 11.7. Внешняя граница и порядок приёмки

В existing M2_TELEGRAM_LOCAL_TEST runbook добавить конечный сценарий из Console:
на принятом SHA Client присылает уникальные text+photo → Owner обновляет правильный
Workspace/диалог, видит текст и private image → вводит один manual reply → Client
подтверждает получение. Зафиксировать дату/SHA, binding/rights и очищенное evidence;
SENT в UI/успех CONTROLLED не закрывает A11. Токены не попадают в чат/PR/CI.

Bot/Owner/Client/secrets подготовлены пользователем; host/DNS/TLS ещё не предоставлены.
Отсутствие runtime блокирует только live часть A09/A11, не C5 implementation/browser.
C5 возвращает REVIEW с exact head/tree/tested SHA/run и tests/assertions→матрица.
C0 проводит приёмку и независимый scoped C8 по новому UI trust/recovery/private-image
риску; прежний C8 M2.3 не объявляется review нового UI. Затем user merge и отдельный
push/main CI. Весь M2 VERIFIED только после всех четырёх частей и реального A11.


### 11.8. Реализация C5 → REVIEW / 2026-09-22

§§1–10 и принятые wire/schema/authority semantics не изменены. В том же Draft PR #21
реализованы messaging-api.ts и page-lifetime MessagingPanel.tsx; App/style wiring
additive. Panel не вычисляет entitlement из billing TEST decisions и не требует
messaging:* в frozen permissions. Exact actor/Workspace/conversation/body/key
хранятся отдельно от защищённого view; valid202 receipt не превращается обратно в
неоднозначный POST из-за GET failure. Context/selection/sequence ownership проверяется
до обработки поздних success/401/403. UNKNOWN не предлагает resend, composer для
нового намерения пустой. Refresh и hard reload ничего не отправляют.

Три коллекции fixed25, opaque cursor/null и ID merge с replacement новых file/delivery
проекций; exact created_at/id ordering без потери microseconds. Parser повторяет
nullable/enum/state-relation правила OpenAPI/http_models, два503 различаются. Unicode
ввод сохраняется без trim/NFC, scalar/Python-whitespace validation отдельно от UTF16.
Private current-owner grant используется как исходный img URL с anonymous CORS и
no-referrer; API/storage no-store сохранён, URL удаляется при context/denial/expiry.
Локальный display timer ограничен максимум60s; он не заменяет серверную TTL/authority.

C3 finite TEST scripts добавляют fresh messaging identities/bindings/product fixture,
bounded outbound DB counters и отдельный runtime-only runner. Существующие Worker,
ControlledAdapter/ControlledImageProvider/FetchTransfer исполнили93 normalized events
и real private MinIO path; никакого fixture-side canonical READY/receipt/Job insert.
C6 browser overlay сохраняет private tmpfs/roles/secrets guards и добавляет MinIO
loopback signer origin, internal runtime origin, exact TEST CORS и private CALL/EFFECT
instrumentation между runner restarts. Browser worker не имеет migrator/admin URL;
production test endpoints, base Compose/workflow/dependency changes отсутствуют.

Implementation CI35694903440 SUCCESS на tree de2b4b708791f3c55f815d947b00fa13e4888a64:
492 unit,390 PostgreSQL/S3,107 frontend,27 browser и оба штатных scripts/source gates.
Assertions→A01–A12 и точный source/CI receipt находятся в единственном active
M2_HANDOFF; final REVIEW docs snapshot заново проверяется полным CI, итоговые
head/parent/tree/tested SHA/jobs фиксируются в PR receipt без SHA-only commits.

Прежние fixtures/guards/assertions сохранены: App auth tests отдельно изолируют
новую panel, full Console recovery тестируется в новой suite; browser auth/billing
selectors не потребовали изменений. TEST model fixture расширен новой storage/runtime
границей, старые14 guard cases сохранены. Local compiler/format corrections не
ослабляли behavioral assertions. Первый опубликованный implementation CI зелёный.

CONTROLLED evidence не live Telegram. Runbook содержит конечный Console journey,
но runtime/DNS/TLS отсутствуют: live A09/A11 BLOCKED, внешних sends/расходов нет.
C5 возвращает REVIEW; приёмка C0 и независимый scoped C8, user merge/main CI и
реальный Client receipt ещё требуются. M2.4/M2 VERIFIED самостоятельно не объявлены.


### 11.9. C0/C8 — ограниченная коррекция и приёмка

C0 принял LOCAL/TEST code/UI после реального независимого C8 и targeted closure
**C8-M2.4-01/02/03**. Это уточняет реализацию §§11.1/11.3–11.5, не добавляет API,
архитектурных решений или функций будущего этапа; §11.8 сохраняется как C5 REVIEW history.

- History pagination и send не выполняются одновременно в одном выбранном контексте.
  Только чтение, начатое после202 с тем же confirmed intent, завершает recovery.
  Неоднозначность POST, exact body/key, GET-only recovery и UNKNOWN/no-resend неизменны.
- Актуальный OWNER denial в любой owner-панели Console распространяется на обе.
  Панели получают недоступный protected context, оставаясь mounted; grant удаляется,
  pending intent сохраняется отдельно. Восстановление authority использует прежний
  session flow; исходный command повторяется только явно. Late-response guards
  проверяются до callback. C0 разрешил только этот callback в прежнем BillingPanel.
- Browser проверки private image не используют locator failure previews, содержащие
  img.src. Visibility/naturalWidth проверяются через безопасные boolean/number probes;
  exceptions заменяются bounded code без исходного URL/cause. Private GET и header
  assertions сохранены, это не смягчение проверки изображения.

Исправленный implementation **842b9ee3300fcea06fbb1394c13a01faae21493b**, tree
**f1dd4f5c9442febd192f3a81061634117aa3d7fe**; CI35703839157:
**SUCCESS:492 unit,390 PostgreSQL/S3,111 frontend,27 browser; оба штатных scripts и clean-source gates, canonical/migrations/contracts/reproducibility/smoke PASS**. Exact tested merge, scoped review boundaries, assertions→A01–A12
и дальнейшее действие находятся в единственном активном M2_HANDOFF. Этот acceptance
update повторно проходит полный CI; собственный final SHA записывается в PR receipt.
До user merge/actual main CI M2.4-CONSOLE остаётся REVIEW. До фактического live A11
весь M2 IN_PROGRESS, live A09/A11 BLOCKED runtime/DNS/TLS; M3 не выдан.
