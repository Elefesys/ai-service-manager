# M2 — единый инкрементальный контракт

Дата: 2026-09-21. Владелец: C0; предметное согласование: C2 (DB/tenancy),
C3 (events/media/delivery). **C0 ACCEPTED; C2/C3 CONTRACT PASS** для M2.1 и
добавления M2.2 §9. Это согласование контракта, не C8 review реализации M2.2.
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
