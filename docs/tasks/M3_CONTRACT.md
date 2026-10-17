# M3 — контракт ConversationTurn и границ управления

Дата: 2026-10-10. **CONTRACT-R2 для scoped review; контракт не принят, код не разрешён.**
Поручение C0: [CONTRACT-R2](https://github.com/Elefesys/ai-service-manager/pull/26#issuecomment-6093798400),
[активный M3_HANDOFF §0](M3_HANDOFF.md).
Accepted base: `754f1c883e5a94a7fc9e729af2605424f949ba33`;
continuation C0: `b99e119757d52ee8bd00a51093f63bada5f95823`;
ветка: `c3/m3-1-turns`. Единственный write path C3 — этот файл.
На первом candidate `5706350eaf01d72b4398f14f20c77649a4f0d6e2` C0 принял
[C1 PASS](https://github.com/Elefesys/ai-service-manager/pull/26#issuecomment-6093584212)
и [C2 CHANGES_REQUESTED](https://github.com/Elefesys/ai-service-manager/pull/26#issuecomment-6093660636)
в их scope. Findings **C2-M3-CONTRACT-01–04/P2 OPEN** до verdict C0;
scoped C2/C1 delta review R2 и общая приёмка C0 — PENDING.
[Pairing-решение C6 принято C0](https://github.com/Elefesys/ai-service-manager/pull/26#issuecomment-6094458702)
для включения в R2 (§10); зависимость публикации снята. Это не приёмка полного
контракта. C1 PASS первого candidate на этот R2 автоматически не переносится.
Собственная проверка C3 не заменяет согласования. Статусы задач ведёт C0 в
[TASK_REGISTER](../TASK_REGISTER.md), очередь и критерии — в [M3_HANDOFF](M3_HANDOFF.md).

## 1. Основание и предел первого среза

Источники: [Spec](../architecture/01_ARCHITECTURE_SPEC.md) §§4.10, 5.1–5.14,
14.11, 18.5–18.8, 24.7; [ADR](../architecture/02_ARCHITECTURE_DECISIONS.md)
022–026, 121–128, 180, 197–198, 267, 272;
[MVP](../architecture/06_MVP_SPEC.md) GJ-G и Audit;
[Roadmap](../architecture/07_DEVELOPMENT_ROADMAP.md) M3;
[Implementation Plan](../architecture/09_IMPLEMENTATION_PLAN.md) M3.1/M3.2;
[OPEN-082/083/085](../architecture/04_OPEN_QUESTIONS.md).
Применённые [M2_CONTRACT](M2_CONTRACT.md) §§2–5/9–10 и миграции 0005–0007
сохраняют authority, namespace, fingerprint, receipt, media и delivery semantics.
Канонические оригиналы v0.28 и manifest не меняются.

После отдельного допуска C0 TURNS объединяет уже принятые клиентские text/photo
в durable Turn, ограниченно ждёт существующие FileObject и передаёт snapshot
внутреннему детерминированному TEST consumer **без внешнего эффекта**.
Это не AI, не action admission и не вызов OWNER_MANUAL/SEND_MANUAL_TEXT.
CONTROL, GUARDS, ESCALATION и CONSOLE следуют отдельно. M4/Gateway/AIRun,
новые business entities, outbound media и Notification Engine здесь не проектируются.

## 2. Вход, eligibility и время

Единица входа — канонический INBOUND Message из успешного PROCESS_INBOX
для CLIENT_MESSAGE. Photo с caption остаётся одним Message. Scope сообщения
остаётся `(workspace_id, connection_id, provider_chat_id, provider_message_id)`;
event dedupe остаётся `(provider, bot_identity, event_id)`.
Ни новый event ID для прежнего Message, ни duplicate projection не дают второе
membership. Конфликт fingerprint/identity сохраняет исходный M2 error и не создаёт Turn.

Для новых Inbox после cutover БД записывает неизменяемые `turn_ingress_at`
(`clock_timestamp()` при INSERT) и `turn_ingress_seq` (положительный BIGINT).
Нельзя брать их из provider `occurred_at`, HTTP body, worker clock или даты
создания Message. Существующий `received_at` и старые fingerprints не переписываются.
Пара NULL/NULL означает legacy; неполная пара запрещена. Присвоение и защита пары —
BEFORE INSERT trigger, без прямого UPDATE/sequence privileges у runtime. Для порядка используется
logged sequence `platform.turn_ingress_seq`, CACHE 1, NO CYCLE; gaps допустимы.
Sequence задаёт порядок выделения, **не порядок commit**; Resume требует дополнительной
сериализации §8, одного сравнения sequence недостаточно.

**Origin barrier действует уже в TURNS для обоих producers.** После trusted route lookup
`messaging_ingest` (CONTROLLED) и fresh CLIENT_MESSAGE ветка `telegram_ingest`
берут каноническую `app.channel_connections` по `(workspace_id,connection_id)`
`FOR SHARE` **до INSERT и до обоих ingress fields**. Lock живёт до commit/rollback
Inbox/job/receipt. Trigger сначала получает тот же SHARE lock, проверяет canonical ref
и лишь затем вычисляет clock/sequence; поэтому timing BEFORE INSERT не оставляет
окно перед implicit FK check. Обычный FK KEY SHARE после вставки этот barrier не заменяет.
Exact Telegram receipt replay возвращается прежним ранним путём без нового INSERT/mark;
CONTROLLED duplicate/conflict сохраняет исходные правила. Нормализация и hashes не меняются.

PROCESS_INBOX сохраняет порядок job → свой Inbox → connection `FOR UPDATE`;
свой Inbox берёт `FOR NO KEY UPDATE`, поскольку меняет только non-key status/result refs.
После получения UPDATE все более ранние writers с SHARE либо committed, либо rolled back;
новый writer ещё не может выделить mark. **Следующим отдельным SELECT** выбираются
origin/legacy и canonical Message под тем же connection lock до membership commit.
Эти entrypoints — VOLATILE, UOW — READ COMMITTED; иной isolation отвергается как
TRANSACTION_STATE, а не использует старый snapshot. Нельзя слить lock и origin lookup
в один CTE/statement со snapshot до ожидания или отметить function STABLE.
Чтение остальных Inbox — MVCC без explicit row locks: их workers уже могут держать
свой Inbox и ожидать connection. Membership FK на origin Inbox получает лишь KEY SHARE,
совместимый с NO KEY UPDATE; поэтому **все** status writers Inbox, включая reschedule/
recovery, используют NO KEY UPDATE, не прежний FOR UPDATE. Иначе implicit FK на origin
снова создал бы цикл connection → чужой Inbox → connection. Origin FK использует
неизменный `(workspace_id,id,connection_id)`, не ещё NULL `Inbox.message_id`;
совпадение Message namespace проверяется по immutable normalized projection.

Если несколько Inbox ссылаются на один Message namespace, происхождение берётся
из исходного входа, а не из job, первым создавшего Message: среди fresh Inbox
используется минимальный сохранённый ingress sequence, а legacy имеет приоритет.
Наличие pre-cutover CLIENT_MESSAGE Inbox в этом namespace сохраняет legacy eligibility,
даже если он ещё PENDING, а более новый duplicate обработан первым. Это консервативное
правило действует и при конфликте payload; оно не меняет победителя/ошибку M2.
Для этой проверки нужен tenant/connection/chat/message index по Inbox projection.
Для fresh origin выбирается минимальный committed sequence после barrier среди
CLIENT_MESSAGE этого namespace. Это выбор ingress metadata, а не замена canonical
payload: winner/duplicate/conflict M2 остаются прежними. Legacy-приоритет выше
сохраняется для любого pre-cutover CLIENT_MESSAGE namespace, включая конфликтный.
При I1 с меньшим ещё не committed sequence и committed I2 worker I2 ждёт SHARE I1:
commit I1 фиксирует origin I1, rollback I1 оставляет I2. После выбора origin неизменяем;
он не зависит от того, какой из PROCESS_INBOX jobs первым получил UPDATE.
Новые duplicates не обновляют ingress/deadlines, а сохранённые IGNORED не перечитываются.

Legacy Message остаётся контекстом, но не создаёт membership, Turn или consumer job.
Для fresh Message membership, material context increment и постановка Turn job
происходят в той же транзакции, что Inbox/Message/file plan и завершение PROCESS_INBOX.
Rollback не оставляет частичного Turn. В HUMAN fresh grouping разрешён;
готовность Turn сама по себе никогда не разрешает ответ клиенту.

## 3. Конечная политика группировки v1

Числа v1 ниже выбраны C0 в текущем поручении для LOCAL/TEST; это не изменение канона.
Параметры сохраняются в каждом Turn; retry/restart и изменение следующей политики
не меняют сроки существующего Turn. В TURNS нет нового env, публичного config API
или настройки Telegram. DB entrypoint использует одну фиксированную policy v1.

| Параметр | v1 | Допустимые границы будущей внутренней policy |
|---|---:|---|
| Debounce `D` | 2 с | 100–5000 мс |
| Максимальное окно группировки `G` | 10 с | `D ≤ G ≤ 30000 мс` |
| Ожидание media после логического закрытия `M` | 15 с | 0–30000 мс |
| Максимум members `N` | 32 | 1–64 |

Все значения — конечные целые миллисекунды/количество; неверные значения отвергаются,
а не clamp. Для первого ingress `t0`: `hard_at = t0 + G`,
`quiet_at = min(last_ingress_at + D, hard_at)`. Изначальный верхний
`media_deadline_at = hard_at + M` сохраняется сразу. При закрытии он один раз
сокращается до `min(seal_time + M, hard_at + M)`. `seal_time` — логическая граница
группы, а `closed_at` — фактическое DB время её обработки. Просроченный worker
не начинает новое ожидание от `closed_at`; абсолютный предел v1 — `t0 + 25 с`.

Под коротким conversation lock новый Message добавляется в единственный COLLECTING
Turn, если ingress не меньше `t0`, строго меньше текущего `quiet_at/hard_at`,
media group совместима и есть место. Затем last/quiet пересчитываются, hard не движется.
При равенстве границе старый Turn закрывается. При достижении N он закрывается сразу.
Закрытие из-за таймера имеет `seal_time = min(quiet_at, hard_at)`; из-за лимита
или несовместимого следующего входа — не позднее ingress этого входа и прежней границы.

Media group имеет scope `(workspace, connection, provider_chat_id, media_group_id)`.
Один Turn содержит не более одного непустого album key; text/одиночная photo без key
могут войти в тот же Turn в пределах окна. Другой непустой album key закрывает прежний
Turn и начинает следующий. Нельзя склеивать по одному media_group_id между чатами,
Business, Client или Workspace. Нет ожидания «всех частей альбома»: их число неизвестно.

После seal membership неизменяем. Поздняя часть альбома получает отдельный Turn
с исходным album key, без переноса прежних Messages и без продления старого ожидания.
Out-of-order ingress, который старше начала текущего COLLECTING Turn, получает
отдельный сразу sealed Turn; существующее окно не сдвигается назад. Если job впервые
материализовал уже просроченный вход, применяются исходные deadlines; он не открывает
новое окно от времени обработки. Это осознанное ограничение: задержка обработки
может разделить связанные сообщения, но не создать бесконечное ожидание.
Порядок snapshot стабилен: `(turn_ingress_at, turn_ingress_seq, message_id)`;
provider timestamp остаётся evidence и не управляет дедлайном.

## 4. Минимальные данные и readiness

Предлагаются три используемые таблицы, без отдельной универсальной ConversationState:

| Объект | Ключи и содержимое |
|---|---|
| `app.conversation_turns` | PK `(workspace_id,id)`; typed conversation/connection ref; `revision>0`; captured control generation; COLLECTING / WAITING_MEDIA / READY / FAILED; policy, ingress bounds и deadlines; album key; seal/ready timestamps; COMPLETE/PARTIAL readiness либо terminal error |
| `app.conversation_turn_messages` | PK `(workspace_id,message_id)` обеспечивает одно membership навсегда; Turn, Conversation, Connection и INBOUND Message связаны составными FK; origin Inbox и его ingress; ссылки на канонические Message/FileObject, без копий blob или URL |
| `platform.turn_consumer_receipts` | UNIQUE `(workspace_id,turn_id,turn_revision,consumer)` и `(workspace_id,job_id)`; consumer только `TURN_TEST_V1`; private canonical TEST_CONSUME job/winning claim binding (§5.4); input context version/control generation, snapshot digest, точный immutable результат OBSERVED/STALE и время; без Outbox/Audit/manual receipt |

Turn принадлежит той же Conversation/Connection, что каждый member; origin Inbox
принадлежит тому же tenant/connection и каноническому Message. FK и guarded insert
совместно проверяют это, включая Client/Business через существующую Conversation.
Нужные supporting UNIQUE keys добавляются только для этих FK. RLS/FORCE RLS,
RESTRICT и точные runtime privileges распространяются на новые объекты;
не вводятся свободные DML grants или каскадное удаление истории.
Partial UNIQUE допускает не более одного COLLECTING Turn на conversation.

Существующий `app.conversations.version` становится единым context counter (§6).
В той же строке минимальные control fields: `control_mode=HUMAN`,
`control_generation=1`, generation положительная и монотонная. TURNS не предоставляет
пути смены режима/поколения. Они уже используются в TEST snapshot, но не дают authority.
Вместо неиспользуемых business state columns стадия обработки здесь определяется
Turn: сбор, ожидание media, готовый snapshot или ошибка. READY не означает «ИИ отвечает»
и не подменяет будущие WAITING_FOR_CLIENT/HUMAN/EXTERNAL_SERVICE.

| Событие | Переход / результат |
|---|---|
| Новое допустимое membership | COLLECTING, revision +1; первый member создаёт revision 1; новый GROUP job на quiet/hard |
| Seal, все files терминальны или text-only | READY; COMPLETE, если все требуемые files READY; иначе PARTIAL с FAILED refs |
| Seal, есть PENDING | WAITING_MEDIA, job на сохранённый media deadline |
| Все ожидаемые files стали READY/FAILED до deadline | READY с COMPLETE/PARTIAL, ожидание завершается раньше |
| Deadline, ещё есть PENDING | READY/PARTIAL; snapshot помечает их `WAIT_EXPIRED`, сохраняя file/message refs; сами FileObject остаются PENDING |
| Поздний READY/FAILED после READY/PARTIAL | Тот же sealed Turn, revision +1 и новый актуальный TEST snapshot; membership/deadlines не открываются заново |
| Исчерпание job retry текущей revision | Turn FAILED с typed error; members/refs сохраняются; не становится успешным и не возобновляется скрыто |

Revision меняется один раз на material изменение membership/readiness projection
или переход состояния; несколько изменений одной атомарной операции дают один increment.
Повтор оценки, claim/reclaim, чтение и duplicate не меняют revision. Seal → READY
в одной операции — один переход; WAITING_MEDIA → READY — следующий.
После FAILED поздний file outcome обновляет context/evidence, но не оживляет consumer.
Новая клиентская реплика может создать новый Turn. Изменение READY/FAILED FileObject
сверх существующего M2 terminal lifecycle этим контрактом не разрешается.

В snapshot у каждого image сохраняются FileObject ID/version/status/error и связь
с Message. Отсутствующий/чужой FileObject не считается text-only success: это явный
integrity error. HTTP, download, S3 validation, cleanup и read grants остаются M2;
Turn worker не читает image bytes и не выпускает signed URL.

## 5. Jobs, транзакции и TEST consumer

### 5.1. Durable work и неизменные пределы

Расширяется существующий `platform.messaging_jobs` одним kind PROCESS_TURN:
typed `turn_id`, ожидаемая revision и step GROUP / MEDIA / TEST_CONSUME.
UNIQUE `(workspace_id,turn_id,turn_revision,step)` запрещает повторную постановку.
Inbox/Outbox/File refs для этого kind NULL; для прежних kinds Turn refs NULL.
Turn FK проверяет тот же workspace/connection. Claims прежних kinds сохраняют shape;
новые поля выдаются только соответствующему typed claim, не произвольному job payload.

GROUP/MEDIA выполняют короткую DB-оценку. Изменение revision атомарно ставит работу
для новой revision, не обновляя/блокируя чужой RUNNING job. Устаревший job заканчивается
typed SUPERSEDED (SUCCEEDED без domain effect). Ожидание — `available_at`, не sleep
в transaction и не расходование retry. Завершение GROUP с pending media ставит MEDIA;
file transition может поставить следующую revision раньше при полной terminal readiness.
Старый MEDIA job после этого безопасно становится SUPERSEDED.

Сохраняются claim token, DB lease 30 с, bounded retry (не более 5 попыток / 15 мин,
существующий jitter/backoff cap 60 с), lock timeout 2 с и statement timeout 5 с.
Прежний Telegram `retry_after` 1–86400 с допустим только для proven NOT_SENT_RETRYABLE;
due за пределами 15 мин означает exhaustion, а не увеличение retry horizon.
Нельзя сбрасывать attempt_count или выпускать новую revision ради повторения ошибки.
Scheduler/worker сохраняют действующие entrypoints. Меняется private DB scan protocol
ниже; это не новый брокер и не ослабление admission. Отмена/падение до commit откатывают
всю операцию данного job; после commit читается canonical result.

### 5.2. Claim/exhaustion и recovery: один кандидат на транзакцию

В 0008 `messaging_claim` и `messaging_recover_expired` становятся single-candidate
SQL operations; прежний цикл с terminalization до 100/1000 jobs в одной transaction
не сохраняется ни в overload, ни в helper. Private SQL scan arguments/result получают
cursor и typed step envelope; `MessagingDatabase.claim_job(worker_id) -> JobClaim|None`
и `recover_expired(limit) -> int`, прежние JobClaim fields и внешние API сохраняются.
Bounded iteration выполняется в messaging/database.py через отдельные `_transaction()`.

1. Pass фиксирует DB `scan_until`; порядок claim — `(available_at,id)`, recovery —
   `(lease_until,id)`. Каждый SQL step выбирает не более одного canonical job после
   cursor, до scan_until и текущего DB time, `FOR UPDATE SKIP LOCKED LIMIT 1`.
   Status/due/lease/refs заново проверяются под lock; caller cursor — только hint
   порядка, не authority/Workspace/доказательство expiry.
2. Candidate lock и весь preflight находятся внутри PL/pgSQL exception block.
   Перед terminalization все существующие rows из цепочки §5.3 захватываются
   в заданном порядке **NOWAIT**, включая conversation/Turn и FK targets, если
   соответствующий lock ещё не удерживается. На занятый row block откатывается;
   освобождаются job и все domain locks, возвращается BUSY с позицией scan.
   Нет частичного job/domain/context изменения, нового attempt, сдвига available_at
   или продления lease. Исключение перехватывается только вокруг NOWAIT preflight;
   ошибка исполнения/constraint/commit не маскируется под BUSY.
3. При готовом candidate claim либо сохраняет RUNNING/live token обычным путём,
   либо атомарно терминализирует exhausted/SUPERSEDED. Recovery либо сохраняет
   UNKNOWN для DISPATCHING send, либо делает bounded reschedule/exhaustion, либо
   SUPERSEDED для неактуального PROCESS_TURN. Job/domain/context/следующая Turn job
   коммитятся вместе, без HTTP. Результат step: CLAIMED / TERMINALIZED / RECOVERED /
   BUSY / END; CLAIMED несёт прежний typed JobClaim.
4. Python завершает эту transaction **до** следующего candidate. BUSY/terminal result
   продвигают cursor, CLAIMED возвращает claim, recovery суммирует только committed
   transitions. На один вызов — не более 100 различных candidates; recovery дополнительно
   ограничен переданным limit 1–100. Один candidate не выбирается повторно в этом pass.
   Достигнув bound, worker/scheduler сохраняет cursor/scan_until между итерациями;
   после END следующий pass начинается с начала с новым DB scan_until. Новые due jobs
   до cursor обслуживаются следующим pass. Cursor — process-local fairness hint,
   не durable очередь; restart теряет только позицию, а jobs/outcomes остаются в БД.
5. Неограниченный tight loop и retry SQL при BUSY запрещены; используется прежний
   idle poll 0.25 с. При blocked exhausted A и доступной следующей B claim пропускает A
   и выдаёт B уже в этом вызове. При префиксе более 100 blocked jobs следующий вызов
   продолжает страницу, а не начинает снова с A. Когда lock A отпущен, новый pass
   терминализирует A по прежним пределам; работа не потеряна и attempts не обнулены.

Два recovery batches никогда не держат locks разных conversations одновременно:
одна candidate transaction полностью завершена перед другой. Внутри неё нельзя
добрать вторую conversation, даже «для batch optimization». Новые Turn jobs создаются
только под lock своей conversation; существующие чужие jobs не обновляются.
Неожиданный SQL/commit failure возвращает ошибку и не считается processed/idle success;
если последующая retry/cleanup тоже упала, первичная ошибка сохраняется как cause
с bounded diagnostics, без payload/token. Ни timeout, ни BUSY не означают NOT_SENT.

### 5.3. Полный lock/terminal protocol

Все идентичности берутся из canonical job/domain rows, не из claim DTO caller.
Для обычного execute/finalize одной job допускается прежнее bounded ожидание locks;
maintenance из §5.2 использует те же modes/order с NOWAIT. Job/Outbox/FileObject/
upload intent — `FOR UPDATE`; Inbox, conversation и Turn — `FOR NO KEY UPDATE` для сериализации
без изменения их identity keys. Это конфликтует с другой material mutation, но
совместимо с FK `KEY SHARE`. Claim/token/lease/XID проверяются после locks до записи;
maintenance вместо live claim проверяет canonical READY+exhausted либо RUNNING+expired.

| Все затронутые entrypoints | Порядок, material effect и terminal rule |
|---|---|
| PROCESS_INBOX | job UPDATE → свой Inbox NO KEY UPDATE → connection UPDATE → identity advisory/создание → file plan → conversation → Turn/member/new jobs. Origin читается по §2; context +1 только за новый Message |
| `messaging_claim` exhaustion, оба `messaging_reschedule` overloads, `messaging_retry`, `messaging_recover_expired` для PROCESS_INBOX | job → свой Inbox; его FAILED и job DEAD атомарны, нового Message/context нет; не брать connection/conversation без существующего material outcome |
| Те же maintenance/retry/reschedule paths для FETCH_IMAGE; `files_prepare_upload` / `files_finish_fetch` | job → FileObject → затронутые upload intents в порядке id → conversation → member Turn. Failure path меняется с прежнего intents-before-file на file-before-intents; сначала prelock всего набора, затем ABANDONED/FAILED/READY. prepare и retry без terminal file — context 0; первый file terminal — +1 |
| `messaging_begin_send`, `telegram_begin_send`, включая rejection/reschedule | job → Outbox → существующие OWNER/workspace/user/membership → Business → connection SHARE → Telegram observation/billing locks, где применимы → conversation при terminal rejection. NOT_ALLOWED/terminal dependency refusal создают FAILED/context +1; допустимый DISPATCHING context 0. Live rights/product/window проверки сохраняются |
| Оба `messaging_finish_send` overloads, send `messaging_retry`/reschedule, claim exhaustion send, recovery DISPATCHING→UNKNOWN | job → Outbox → conversation; первым распознаётся допустимый M2 saved replay. SENT/FAILED/UNKNOWN +1 только при первом terminal transition. Retry PENDING и ALREADY_FINALIZED = 0. Recovery не вызывает adapter и не возвращает DISPATCHING в PENDING |
| PROCESS_TURN execute/finalize, claim exhaustion, оба reschedule/retry paths и expired recovery | job → conversation → Turn. Проверка revision **до** решения retry/FAILED: mismatch = SUPERSEDED, без изменения Turn/context/нового receipt. Только актуальная revision может исчерпать retry и стать FAILED; terminal job не обрабатывается повторно |
| Новый manual intent | Прежние authority/product/receipt locks → новый Message → conversation context +1; оставшиеся receipt/Audit/Outbox/Job в той же transaction. Replay/rejection = 0; control пока не меняется |

Общий четырёхаргументный reschedule helper содержит единственную retry/terminal
реализацию, трёхаргументный только делегирует с NULL delay; callers не повторяют
context hook. File/delivery material hooks выполняются при фактическом первом
status transition (OLD PENDING → READY/FAILED для file; OLD PENDING/DISPATCHING →
terminal для Outbox), включая наследуемую ветку recover_expired из 0005.
Повторная запись того же terminal состояния и rollback дают 0; отдельный trigger
или helper не добавляет второй increment поверх исходного transition.
File reschedule не трогает WINNER/terminal FileObject, cleanup ABANDONED intent
не захватывает FileObject/conversation и остаётся нематериальным.
Для prepare/retry без terminal file последняя conversation/Turn часть цепочки
не выполняется; уже удерживаемые locks не захватываются заново в обратном порядке.

SUPERSEDED хранится как typed Turn-job outcome при SUCCEEDED, без подмены send outcome.
Если obsolete READY job ещё не имела попыток, её первая фактическая DB-оценка оформляет
одну попытку в той же transaction; старый CHECK terminal/attempt_count>0 сохраняется.
Это не reset/дополнительный retry и не выдача lease старому worker. Для TEST_CONSUME
revision mismatch до snapshot/при recovery = SUPERSEDED без receipt; при valid live
finalize с той же Turn revision, но изменённым context/generation — STALE receipt §5.4.

Из 0007 `last_client_inbound_at` переносится после file plan в конечную conversation
секцию, сохраняя формулу и Telegram scope; provider-only increment заменяется §6.
Не брать conversation до ожидания существующего FileObject. Turn worker не берёт
connection/file/outbox row locks и не расширяет короткий ingest connection barrier.

Implicit locks входят в этот порядок: INSERT Message получает KEY SHARE на conversation,
Inbox — на connection, file/job/member/receipt — на своих typed FK targets. FK к
connection после conversation не добавляется; job PROCESS_TURN ссылается на Turn.
При maintenance нужные существующие FK targets предварительно lock NOWAIT, даже
если последующий INSERT/UPDATE запросил бы lock автоматически. Новые строки принадлежат
той же transaction; ON CONFLICT новых Turn jobs ограничен её conversation и не обновляет
existing job. Deferred file winner FK не переносит незахваченный конфликт в commit:
job/file/intent уже удерживаются. Нельзя менять immutable key ради получения слабого lock.
После conversation запрещён захват другого job или file; после file — обратное
ожидание job. До реализации C2 сверяет все эти edges, включая FK/trigger effects.

### 5.4. Private TEST receipt и ACK-loss replay

Третья таблица хранит immutable `job_id`, `winning_claim_token`, workspace/connection,
Turn/revision, фиксированные kind PROCESS_TURN и step TEST_CONSUME, consumer version,
input versions/digest и полный canonical typed result OBSERVED/STALE (включая время).
В jobs нужен supporting UNIQUE `(workspace_id,id,connection_id,kind,turn_id,turn_revision,step)`;
receipt ссылается составным FK на этот exact immutable tuple и имеет UNIQUE по job
и по `(workspace,Turn,revision,consumer)`. `winning_claim_token` копируется из
canonical RUNNING job после live guard, не принимается как свободное поле результата.
FK на текущий job.claim_token не применяется: terminal job по-прежнему очищает его.
Прямые SELECT/DML receipt, SET winning claim и UPDATE job refs для runtime запрещены.

Consumer читает snapshot refs/versions под job/conversation/Turn, делает только чистое
детерминированное вычисление вне transaction, затем finalize повторяет live claim/XID,
revision/context/generation checks. Canonical receipt + SUCCEEDED/очистка claim коммитятся
атомарно. Current revision с изменённым context/generation даёт STALE, без регенерации
по backlog; revision mismatch завершается SUPERSEDED по §5.3. Повтор чистого вычисления
после crash допустим, два committed результата одного job/revision — нет.

Для потерянного ACK предусмотрена **отдельная read-only capability**
`turn_consumer_replay(job_id, claim_token)`, вызываемая в собственной transaction
без user/worker UOW. Узкая SECURITY DEFINER function с фиксированным search_path
и EXECUTE только у runtime проверяет canonical terminal SUCCEEDED job, его kind/step,
полный FK tuple и точное совпадение token с private receipt.winning_claim_token.
Workspace/Turn/revision caller не передаёт; они выводятся только из этих связанных rows.
Читается один committed snapshot без row locks/изменения GUC authority, результата,
версий, jobs, Audit или lease. Общего runtime SELECT и обхода RLS по caller Workspace нет.

При совпадении возвращается **сохранённый результат**, даже после lease expiry или
поздней смены context; replay не выдаёт новую authority и не «обновляет» OBSERVED.
Unknown/NULL/чужой/проигравший token, другой job/kind, отсутствие terminal receipt —
STALE_CLAIM без данных. Finalize может сначала распознать этот exact terminal replay;
иначе запись требует обычного fresh admit+guard в текущем physical transaction/XID.
Если commit не состоялся, read-only miss ничего не повторяет: ещё live claim может
завершиться через обычный finalize, expired claim — только через recovery/reclaim.
Если A expired, B reclaimed и committed, поздний A не читает и не меняет результат B.
Fake Owner, expired capability для новой mutation и общий reader по одному Turn ID
запрещены. Receipt/digest никогда не являются разрешением на внешний action.

Механика snapshot/locks опирается на PostgreSQL 18:
[VOLATILE snapshots](https://www.postgresql.org/docs/18/xfunc-volatility.html),
[row locks и rollback savepoint](https://www.postgresql.org/docs/18/explicit-locking.html),
[exception blocks](https://www.postgresql.org/docs/18/plpgsql-control-structures.html#PLPGSQL-ERROR-TRAPPING).
Это основания выбранного протокола, а не evidence выполненных concurrency tests.

## 6. Общий context version

`context_version` в новом внутреннем DTO — имя существующего `Conversation.version`,
не второй независимый счётчик. Existing значения не сбрасываются/не пересчитываются
при upgrade; новая conversation стартует с 1 и получает increment за первый Message.
0007 сейчас инкрементирует только новый TELEGRAM inbound; CONTROLLED не эквивалентен.
0008 должна заменить это поведение одной общей таблицей, не оставить двойной increment.

| Material event | Conversation.version | Message.version / примечание |
|---|---:|---|
| Новый канонический CLIENT_MESSAGE, text/photo+caption, CONTROLLED или Telegram | +1 | Новый Message version 1; legacy materialization также меняет context, но не eligibility |
| Новый успешно принятый Console manual intent | +1 | Новый OUTBOUND Message version 1; атомарно с существующими receipt/Audit/Outbox/Job, без takeover в TURNS |
| FileObject PENDING → READY либо FAILED | +1 | Message неизменен; FileObject.version меняется по M2; относится и к исторической фотографии |
| Первый terminal delivery outcome SENT / FAILED / UNKNOWN | +1 | Message неизменен; delivery evidence входит в context; retry/DISPATCHING не terminal |
| Duplicate/replay/conflict/rejected command | 0 | Исходный результат/ошибка M2; никакого нового Audit/Turn |
| Read, pagination, file grant, rights refresh/observation, lease, retry, cleanup, seal/consumer receipt | 0 | Служебное событие не становится material context; у Turn своя revision |
| Edit/delete/native/echo/unsupported в текущем TURNS | 0 | Сохраняются M2 IGNORED outcomes; нет новой интерпретации старого receipt |
| Будущее принятое material edit/delete | +1 ровно один раз | Semantic Message.version +1; исходный ingest fingerprint не переписывается; новый provenance/codec принимается до кода |
| Будущее Takeover/Resume без нового сообщения | 0 | Меняется отдельная control_generation; само изменение режима не новый Message |
| Будущее доказанное native owner сообщение | +1 за новый semantic Message | HUMAN/generation только по отдельно принятой provenance policy §9; echo не второе сообщение |

Один исходный material event даёт один increment, хотя он может затронуть Turn,
FileObject, job и receipt. Сохранённый terminal outcome при повторном finalize не
инкрементируется. Context update откатывается вместе с породившей его операцией.
Более высокий version не означает право действовать: mode/generation/permissions
проверяются отдельно. Переполнение любого счётчика — отказ, не wrap/reset.

## 7. Cutover, совместимость и rollback

Новая миграция зарезервирована C0: `0008_conversation_turns.py`, revision `0008`,
down_revision `0007`; C2 подтвердил этот резерв, но не выдал DDL acceptance.
При другом actual head — новое решение,
не переименование/редактирование 0001–0007. Upgrade ничего не отправляет.

Cutover требует остановки приёма новых работ и drain старых transactions/workers.
В migration transaction Inbox получает lock, конфликтующий с INSERT/UPDATE;
добавляются NULL ingress columns **без backfill**, затем insert/immutability triggers.
После commit только новые вставки получают trusted mark. Старый PENDING PROCESS_INBOX,
ещё без Message/Conversation, навсегда остаётся legacy. Не использовать volatile
DEFAULT при добавлении columns, который пометит все прежние rows как fresh.
Migration не создаёт Turns/jobs из истории и не повторяет IGNORED/native receipts.
Pending manual send, UNKNOWN, exact receipt replay, FileObject/upload attempts и
их дедупликационные ключи сохраняются; старые значения context не обнуляются.

Mixed 0007/0008 workers **не поддерживаются**: старый worker не понимает PROCESS_TURN
и не должен claim его. Порядок: drain → upgrade → совместимый runtime с exact schema
readiness → возобновление. Существующие незавершённые M2 jobs забирает новый worker;
изменение кода не возвращает DISPATCHING/UNKNOWN в безопасный resend.
Deployment/VM-команды этим документом не выдаются.

Downgrade разрешён только после drain и до появления M3 data: нет Turn/member/consumer
rows, PROCESS_TURN jobs или Inbox с новым ingress mark. Иначе explicit отказ до
любого destructive DDL; не удалять данные для прохождения cycle. Чистый 0007→0008→0007
восстанавливает прежние functions/permissions/schema, сохраняя M2 rows и версии.
После реального cutover нужен forward fix либо отдельно принятый restore-план C0/C2/C6,
а не запуск старого image поверх новой схемы.
Это ограниченный LOCAL/TEST порядок, не отмена production Expand/Migrate/Contract
из Spec §§18.14/25.7 и ADR-217. Historical connect5 source switch 0007→0007 сохраняется
отдельно; его cross-source fingerprint и image rollback нельзя переносить на schema
upgrade 0007→0008. Exact source/image/schema pairing остаётся gate §10.

## 8. Обязательная граница CONTROL/GUARDS, без их реализации в TURNS

**Принятое решение C0:** existing/new conversations — HUMAN. Только явный Resume
разрешает допустимую автоматику; таймер, закрытие Turn, доставка manual reply или
resolve Escalation не включают AI. В M3 режим AI не обещает наличие исполнителя M4.

Control generation монотонна и отделена от Conversation.version, Turn.revision,
Message.version и Telegram connection generation/observation_version. В CONTROL
новый принятый Takeover/Resume и новый принятый manual intent фиксируют новое поколение
в одной conversation serialization/CAS границе. Console manual intent атомарно
устанавливает HUMAN даже если ранее HUMAN; его context increment остаётся один.
Replay key/body возвращает сохранённый результат, без нового поколения/версии/Audit;
отказ authority/product policy/stale precondition не забирает разговор.
Delivery FAILED/UNKNOWN после принятия intent не возвращает AI.

Будущие owner-команды сохраняют live OWNER, cookie/Origin/CSRF, точные key/body,
DB-authoritative fingerprint, receipt replay и явные conflict/stale errors.
Маршруты/DTO/Audit variants CONTROL согласуются с C1 отдельно; текущие пять M2 API,
generated OpenAPI, billing/catalog и response snapshots TURNS не меняет.
Изменение материальности Conversation.version в §6 явно подлежит review C1.

Resume атомарно сохраняет новый generation и ingress fence, не ставит работу по
предыдущим Turns/PENDING Inbox. Для уже известной conversation новый accepted ingress
и Resume должны сериализоваться на её строке **до выделения sequence**: известные
connection/authority locks берутся раньше conversation; sequence fence выделяется
под тем же lock. Это дополняет producer connection SHARE barrier §2; не откладывает
его до CONTROL и не разрешает connection lock после conversation. Тогда вход,
принятый до Resume, остаётся по старую сторону fence,
в том числе если Message ещё не существует. При создании conversation после ingress
HUMAN остаётся default; её последующий Resume также исключает уже принятые входы.
Legacy NULL исключён всегда. Это обязательная доработка CONTROL до открытия Resume,
не утверждение, что sequence TURNS уже даёт commit-order barrier.
Группы после CONTROL не пересекают activation generation; generation/fence допустимого
входа наследуются Turn/job. Поздняя media readiness не заменяет их текущим поколением.
Resume не оживляет старый output, а новая допустимая работа строит свежий snapshot
после fence. Старый HUMAN Turn остаётся контекстом без нового action admission.

GUARDS допускает action только при текущих context/generation/mode, live authority,
product policy, channel rights/window, валидных refs и claim. Линеаризация с Takeover —
в одной короткой DB/CAS transaction. Для send durable dispatch/attempt commit отделяет
не начатую работу от in-flight **до HTTP**. Если Takeover победил раньше — stale/suppressed
без эффекта; если dispatch commit раньше — запрос может уже начаться и не отзывается
DB toggle. UNKNOWN не называется CANCELLED. Фактический результат начатого send
сохраняется и после смены поколения, ACK loss требует canonical read, возможный
эффект исключает blind resend. HUMAN не останавливает inbound/manual/reconciliation.

## 9. Native provenance и отдельная Escalation

В TURNS native owner/edit/delete/echo остаются M2 ignored. Для CONTROL необходимо
отдельно принять origin projection и account evidence: настоящий owner, наш bot echo,
другой bot/offline/unsupported и запоздалый update не взаимозаменяемы.
`sender_business_bot`/`is_from_offline` сами по себе не доказывают наблюдаемость native
reply на конкретном подключении. Текущий live gate — **NOT VERIFIED**.
Не присваивать native owner Client identity, не менять сохранённый V1 fingerprint
и не переисполнять исторический IGNORED ради новой классификации.

Будущее достоверное новое native intervention может забрать управление один раз;
echo — никогда. Для delayed/pre-Resume events требуется доказуемая provenance/order
policy: время доставки webhook не доказывает новое вмешательство после Resume.
При неоднозначности нельзя автоматически разрешать AI или утверждать native takeover
проверенным. Точный fallback/ограничение C0 принимает до этого кода по account evidence.
Явный Console Takeover обязателен независимо от native поддержки.

Escalation — отдельный lifecycle запроса решения владельца, не режим Conversation.
Resolve/cancel/expiry не снимают HUMAN. Будущие due/expiry/reminder сохраняются и
повторно проверяют текущий context/generation; late answer не применяется к иному
состоянию. Здесь нет escalation DDL/API, ApprovalRequest или Notification Engine.
OPEN-082/083 о сроках/исключениях остаются OPEN; в HUMAN client follow-ups запрещены,
для transactional notices сохраняется консервативный owner-review default.

## 10. Exact source/schema pairing и будущий compatibility scope

**Finding04 OPEN; pairing design C6 принят C0 для включения в R2.** Здесь включено
[предложение C6](https://github.com/Elefesys/ai-service-manager/pull/26#issuecomment-6093950520)
по [его поручению](https://github.com/Elefesys/ai-service-manager/pull/26#issuecomment-6093798239).
[Решение C0](https://github.com/Elefesys/ai-service-manager/pull/26#issuecomment-6094458702)
принимает matrix, assertions и будущий compatibility scope, разрешая один финальный
docs-only R2. CONTRACT acceptance и выдача TURNS остаются отдельными gates.
Выбран полностью frozen historical source switch H/0007 с прежними P/O,
candidate same-schema regression I/0008 и отдельный disposable LOCAL upgrade
H/0007→I/0008. Один inventory31/34 pairing не решает.

### 10.1. Неизменяемые sources и actual image proof

| Pin | Полный source SHA | Tree / роль |
|---|---|---|
| P | `0b7e24ee425ebb429bf87dfe382cbd3fab883028` | `14a4033b849c736235653a5a85ec9e5112bfe727`; прежний operational helper/recovery и runtime0007 |
| O | `80e51c43e31541940f1ccf18b8281adf1a061748` | `88ed308b4c56114aa977dcf91204964d9b7348e5`; только explicit historical operator0007; manifest128 `b88bc4ceadff581a170fdb81543b631eef6e8624d57504a049a5ac2645105195` |
| H | `754f1c883e5a94a7fc9e729af2605424f949ba33` | `b4fdef89583f6bab1c9c96cadb1fbe0c1e5d641f`; frozen accepted historical target/harness/fixture0007 и baseline нового upgrade |
| I | Будущий exact implementation SHA, пока отсутствует; не текущий docs SHA | Реально проверяемые source/tree, линейный head0008 и exact readiness0008; pin принимается после отдельной выдачи и реализации TURNS |

`R_X`/`D_X` ниже — будущие фактически измеренные immutable runtime/development image IDs
из `git archive X`, проверенные по полному copied-source inventory, SHA/tree и image kind.
Ни одного actual image ID этот контракт не утверждает. Tag/label без проверки bytes
недостаточен. Existing Dockerfile/build/image/dependency/relay/client/config pins не меняются.
H выбран только для новых disposable historical runs; прежние owner `to_sha`, pins,
hashes и receipt DAG не заменяются H. Reports различают PR head и actual tested checkout
SHA (в том числе virtual merge с parents), не подменяют source одним совпадением tree.

### 10.2. Phase → code/image → schema/fixture → допустимый переход

| Phase | Controller и callers | Schema / fixture | Переход и обязательные assertions |
|---|---|---|---|
| Historical preparation/recovery | Неизменённый harness/helper H; operational P; API/worker/scheduler R_P; operator D_P либо explicit D_O | LOCAL0007; held fixture D_H; отдельный TEST0007 также D_H | Прежний recovery-v2/preparation; exact LOCAL identity/readiness, .intent/DAG/private bytes, old operator provenance, UNKNOWN/wire1 и private S3 |
| Historical forward/resume/preflight | H; API/worker R_H, operator D_H; scheduler R_P | Только0007, тот же D_H | P→H только source/images; intent/image/state interruption/resume; полное равенство31-table fingerprint, done/result/schema2 audit обоих направлений; unrelated IDs/config/mounts сохраняются |
| Historical rollback/retry | H возвращает R_P и исходный D_P/D_O; old-source preflight P | Только0007, D_H | Прежний image/state rollback без DDL; readiness0007, IDs/state/DAG/hashes и completed retry без recreate/нового send |
| Candidate default transport/lifecycle | Изменяемые shell/helper/tests I; API/worker/scheduler R_I, operator/checks D_I | LOCAL0008 для E05 и отдельный TEST0008 для шести wire cases | Candidate prepare/deploy/recover/preflight/route rollback на той же0008; прежние6 wire+6 lifecycle assertions, full34-table before/after, HTTPS/disabled TG/identity/UNKNOWN/no-resend |
| Upgrade baseline / negative pairing | Candidate controller I; runtime R_H, operator D_H; I test image лишь явный migration-role SQL controller | Новый disposable LOCAL0007; seed через H/0007 | Seed legacy PENDING без Message, manual pending/UNKNOWN/receipts, files/grants, ignored и versions. I runtime/0007 даёт ожидаемый readiness отказ ДО seed/claim |
| Drain / schema upgrade | API/worker/**scheduler** H остановлены; старые fixture pools/transactions закрыты. Migrator I под asm_migrator | Тот же LOCAL PG/DB/volume: 0007→0008 | При потере ACK сначала определить actual revision: подтверждённая0007 после rollback допускает H/0007; committed0008 требует I/0008 и forward recovery. M2 column projection сохранена, legacy NULL, HUMAN/gen1, нет history Turns/jobs/ignored replay |
| Cutover / restart | API/worker/**scheduler** R_I; operator/fixture D_I | Только LOCAL0008 | Exact readiness, legacy без Turn/consumer и fresh Turn, receipt/claim fencing, UNKNOWN/no-resend. Restart/forward recovery I/0008; будущий forward-fix source отдельно принимает C0 |
| Clean downgrade case | Отдельный пустой M3 case; I drained; migrator I | 0008→0007 только без M3 rows/marks/jobs | H runtime стартует только после exact0007. Полный31-table fingerprint до/после cycle, M2 versions/functions/permissions, без удаления M3 ради совпадения |
| Populated refusal | I drained; migrator I; после отказа только I/0008 | LOCAL0008 с каждым blocker по отдельности | STOP до destructive DDL; schema/data/functions/grants неизменны. Старые R_H/R_P и historical source-switch rollback недопустимы |

Текущий `alembic upgrade head` в egress TEST DB не обновляет held LOCAL DB.
Запрещены I runtime/consumer fixture0008 + LOCAL0007; P/H/O runtime0007 + schema0008;
P→I historical switch без DDL; отключение readiness D_I ради seed0007; upgrade только
asm_test вместо asm_local; оставленный scheduler P/H при API/worker I; arbitrary operator
или подмена D_O→D_P. I migrator на0007 допустим только для явной schema операции,
не для runtime claim/seed. Это LOCAL/TEST harness, не VM updater или rollout.

### 10.3. Обязательный coverage изменяемого candidate

1. Candidate `scripts/test_telegram_egress_migration.sh` проверяет собственный exact I
   и clean source, создаёт detached H и вызывает **его неизменённый** migration shell
   с тем же intent/image/state shard. Все шесть historical normal/Docker29 shards
   остаются. Нельзя собрать H+patched helper или перенести I runtime в H.
   До historical cleanup координатор отдельно сохраняет reports/source archive,
   source/image proofs и clean-source результаты этой фазы.
2. В существующих двух `boundary=state` shards после полного historical cleanup
   выполняется обязательная отдельная candidate schema phase: новый project/private
   state/LOCAL DB, явный schema-upgrade selector основного shell. Historical volumes,
   state и receipts не используются как новый baseline; image reuse требует byte proof.
3. Основной shell оставляет default I/0008 E01–E05 и передаёт schema-specific entrypoint
   `tests/test_telegram_egress_migration.py` точные H/I и actual R_H/D_H/R_I/D_I.
   I images собираются test orchestration из tracked archive I и frozen build inputs;
   historical-only `migration_build_images()` для I не используется. Seed/проверки —
   в `tests/test_m3_1_migrations.py`: на0007 только migration-role SQL control и H runtime,
   без вызова generic I `durable_local()` против0007.
4. Старый seed controller завершается до cutover, оставляя seeded M2 rows; pools/
   transactions закрываются, все effect-producing processes, включая scheduler,
   drained. Отдельная same-schema E05 I/0008 fixture стабилизирует Turn/jobs настоящими
   bounded worker transitions до durable-before, без claim-фильтров, mocks или
   отключения новых jobs ради прежнего SEND/UNKNOWN assertion.
5. Helper I разрешает historical `migration-*`/`migrate` только для пары0007→0007.
   Общий source/schema guard выполняется при initial preparation **и** saved resume/
   preflight/rollback (включая `migration_saved → migration_source(plan.to_sha)`)
   до build/recreate/journal publication. Target/runtime0008, unknown/mismatched
   revision, same-count wrong/missing/extra names и substituted fixture/operator
   отвергаются. Direct CLI и saved-plan negative tests выполняют именно helper I;
   STOP сохраняет private bytes,
   data/container IDs и не публикует migration intent. Exact source guard не обходится
   переписыванием H checkout.
6. Candidate tests сохраняют receipt DAG15, historical128 provenance, cross-direction
   schema2 audit, result/done, tamper/inter-effect/completed-retry assertions. Frozen
   historical PASS относится H; runtime coverage I дают его E01–E05 и schema phase.
   Reports отдельно фиксируют I coordinator/tested source, H executor/fixture/target,
   P/O, actual image IDs/tree/bytes, LOCAL/TEST identities и revision до/после. Старое
   `source_sha=H` не переписывается в I; source/clean checks и archive сохраняются
   для I и detached H/P. Новая schema phase обязательна, не informational/skip.

Workflows, compose, Dockerfile/locks/pins и budgets не меняются; все девять jobs
и gates сохраняются. Если выбранный путь не помещается в существующие пределы
или требует новых paths, требуется отдельное решение C0 по evidence,
а не увеличение timeout/retry. Этот design не объясняет первичный docs-only CI failure.

### 10.4. Exact inventories и cross-schema сравнение

Expected revision задаётся фазой и source pin, затем сверяется actual
`platform.alembic_version`, readiness и **полный набор qualified table names**.
Ни autodetect произвольного head, ни допуск любых31/34 таблиц не разрешён.
Набор0007, статически сверенный C6 с applied migrations:

```text
app.audit_events, app.business_members, app.businesses,
app.channel_connections, app.client_identities, app.clients,
app.conversations, app.file_objects, app.locations, app.messages,
app.outbox_events,
platform.alembic_version, platform.auth_credentials, platform.auth_sessions,
platform.billing_contact_command_receipts, platform.channel_routes,
platform.file_object_uploads, platform.inbox_events,
platform.messaging_command_receipts, platform.messaging_jobs,
platform.plan_entitlements, platform.saas_plan_revisions, platform.saas_plans,
platform.telegram_connection_state, platform.telegram_update_receipts,
platform.user_accounts, platform.workspace_billing_accounts,
platform.workspace_memberships, platform.workspace_service_modes,
platform.workspace_subscriptions, platform.workspaces
```

0008 добавляет только `app.conversation_turns`, `app.conversation_turn_messages`,
`platform.turn_consumer_receipts`; actual DDL inventory ещё проверяет C2. Historical0007
JSON/hash format, receipts и hashes сохраняются; actual revision/name validation
не добавляет поля в старый receipt. Same-schema0008 использует отдельный full34-table
fingerprint. Unknown/missing/extra и same-count substituted names отвергаются.

При0007→0008 полный fingerprint **должен измениться** из-за revision, новых tables/columns.
Schema case сравнивает заранее зафиксированную по H0007 **точную column projection**
всех прежних M2 rows, counts/IDs/versions/statuses/receipt fingerprints и private-object
hashes; Alembic7→8 и новые fields проверяются отдельно, включая legacy NULL/HUMAN/gen1.
Projection не подстраивается под неизвестные actual columns. Только после чистого
обратного cycle снова требуется полный0007 fingerprint; marked/M3 rows не удаляются.

### 10.5. Точные будущие paths, до отдельной выдачи C0

Ни один из этих файлов сейчас не изменён. Необходимость pins/cleanup подтверждена
профильными C1/C2; предложенный C6 исчерпывающий compatibility-набор принят
[C0](https://github.com/Elefesys/ai-service-manager/pull/26#issuecomment-6094458702)
для последующей выдачи TURNS, **не как текущая write permission**:

| Path | Только необходимая дельта |
|---|---|
| `backend/src/asm/foundation.py`; `tests/test_foundation.py` | Runtime exact0008 и mismatch rejection; frozen tenancy.v1 revision0003 остаётся прежней |
| `backend/src/asm/telegram/provisioning.py`; `tests/test_m2_3_setup.py` | Binding exact0008 и отказ wrong head до initializer; billing/product/binding policy неизменна |
| `tests/test_m2_1_postgres.py` | Общий scoped child-first cleanup новых receipt/job/member/Turn FK, без CASCADE/disable constraints |
| `scripts/test_telegram_egress_migration.sh` | Frozen-H dispatch, обязательная schema phase в state shards, раздельные source reports/clean checks |
| `scripts/test_telegram_egress.sh` | Explicit schema selector/source-image pairing; default I/0008; не подменять LOCAL upgrade TEST migration |
| `scripts/prepare_telegram_egress.py` | Historical-only source/schema guard и exact revision/name-set validation с сохранением old JSON/receipts/provenance/recovery |
| `tests/test_telegram_egress_migration.py` | Candidate pairing rejection, сохранённые regressions, bounded schema orchestration/report assertions |
| `tests/test_telegram_egress_postgres.py` | Exact inventory, стабилизация I fixture и child-first cleanup на0008; frozen H fixture не редактируется |
| `tests/test_m3_1_migrations.py` | Уже предусмотренный новый suite: schema seed/verification entrypoint, upgrade, clean cycle и populated refusal |
| `docs/runbooks/M2_TELEGRAM_LOCAL_TEST.md` | Короткая граница historical0007 и ссылка на M3/schema lane; закрытая история/receipts/pins сохраняются |

`tests/test_telegram_egress.py` выбранному варианту не требуется: отрицательные cases
помещаются в migration tests. Workflow/compose/egress overlays/Dockerfile/locks,
TelegramClient/config/transport и canonical architecture не запрашиваются.

Предусмотренные планом будущие inventory/cycle files: `tests/test_postgres.py`,
`tests/test_m2_1_schema_postgres.py`, `tests/test_m2_2_migrations.py`,
`tests/test_m2_3_schema_postgres.py`. Последний содержит literal 0007; historical
cycles должны явно выбирать прежнюю revision и не удалять M3 rows ради downgrade.
Новый migration suite проверяет populated downgrade refusal отдельно от чистого cycle.
Private scan ABI §5.2 также проверяется в inventories/worker admission; historical
fixtures на 0005/0006/0007 используют соответствующие той revision SQL capabilities,
а не новый 0008 scan client на старой схеме. Такую адаптацию старого fixture нужно
объяснять точным schema/source boundary, сохранив исходные domain assertions.
`scripts/provision_local_auth.py`, `scripts/m1_3_browser_fixture.py`,
`scripts/m2_4_browser_worker.py` уже используют общий DATABASE_SCHEMA_REVISION;
отдельной правки для номера не требуют, их exact checks сохраняются.

Остальной TURNS allowlist остаётся из PR25: новый используемый
`backend/src/asm/conversations/{__init__,turns}.py`, ограниченные
`backend/src/asm/messaging/{database,worker,results,models,errors}.py`, новая 0008
и три `tests/test_m3_1_{turns,turns_postgres,migrations}.py`.
DDL SQL hooks в 0008 сохраняют прежний API/codec; если реализация требует иных paths,
сначала конкретный diff C0. Текущий CONTRACT не разрешает менять ни один из них.

## 11. Проверяемые обязательства будущего TURNS

Это план assertions, **не результаты выполненных тестов**. Проверки идут через
реальные runtime DB/worker paths с PostgreSQL; media — через действующий private
S3 pipeline там, где утверждается его integration. Детерминированный clock/барьеры
тестов не становятся runtime-аргументом для backdating ingress/deadline.

| Критерий | Обязательные assertions |
|---|---|
| M3-A01 | 2 с debounce / 10 с cap, точное равенство границе, 32 members; text+photo+caption, совпадающий/другой album key; event/message duplicates и conflicts; late/out-of-order не меняют sealed membership/deadline и не дублируют Message |
| M3-A02 | Restart до/после membership, seal, media result и receipt commit; сроки не пересчитываются; READY/FAILED/WAIT_EXPIRED сохраняют refs; late terminal меняет ровно нужную revision; два workers дают один committed receipt; stale claim/reclaim и exhaustion видимы |
| M3-A02, изоляция | Barrier на conversation A не блокирует Turn worker B, включая другую conversation того же connection; чужие ws/client/conversation/message/file/Turn/job/token отвергаются FK/RLS/guard; file completion и Inbox/Turn конкурируют без lock inversion; во время ожидания/HTTP нет business transaction |
| M3-A03, только часть | CONTROLLED и Telegram имеют одинаковые material increments §6; duplicate/read/refresh/retry/receipt replay = 0; rollback = 0; старый input даёт STALE consumer; Message.version не имитирует FileObject/Turn version |
| M3-A11 | На 0007 принять PENDING Inbox без Message/Conversation, upgrade, обработать: context есть, Turn/consumer нет; post-cutover duplicate, обработанный первым, не обходит fence; fresh вход формирует Turn; IGNORED и fingerprints byte-identical |
| M3-A11, M2 regression | Clean upgrade и 0007→0008, пустой downgrade cycle и populated refusal; exact inventories/permissions/readiness; manual new/replay/conflict/revocation, pending send/UNKNOWN/no-resend, private file references и grants сохраняются |

Дополнительные адресные assertions R2; findings остаются OPEN, результаты ещё не получены:

| Finding / разделы | Проверка будущей реализации |
|---|---|
| 01 / §2, §8 | Для ОБОИХ producers I1 удерживает SHARE после меньшего mark до INSERT/FK/commit, I2 committed, worker I2 ждёт connection UPDATE. Commit I1 → сохранён origin I1; rollback I1 → origin I2; late duplicate не меняет deadlines/membership. Проверить fresh/fresh, legacy/fresh и conflicting projection. REPEATABLE READ отвергается; origin SELECT использует snapshot после lock |
| 02 / §5.2–5.3, §6 | При blocked conversation A с exhausted FETCH_IMAGE или SEND job последующая PROCESS_TURN B получает claim, в том числе на том же connection. A не меняет attempts/due/domain/context; после unlock A терминализируется ровно один раз. Более 100 blocked candidates не возвращают scan бесконечно в начало; concurrent recovery batches освобождают все locks перед следующим candidate |
| 02 / все terminal branches | SUPERSEDED до ошибки/исчерпания проверяется в claim, обоих reschedule overloads, retry, expired recovery и Turn execute/finalize; новый Turn не становится FAILED из-за старой revision. File success/failure, send begin rejection, обе finish overloads, retry/exhaustion и DISPATCHING recovery дают по одному material increment; ALREADY_FINALIZED/rollback = 0. Fault между domain/context/job writes откатывает весь candidate; последующая ошибка не скрывает первичную |
| 03 / §4, §5.4 | Receipt+SUCCEEDED committed, ACK потерян: exact job/winning token возвращает тот же result после expiry без новых rows/version/Audit. Forged/NULL/чужой token и job/kind/Turn mismatch отказаны; прямой runtime SELECT/DML отказан. A expired → B reclaimed+committed → поздний A rejected, B replay успешен. Не committed finalize не создаёт права terminal replay |
| 04 / §7, §10 | По принятому C0 pairing design отдельно доказать historical P/0007→H/0007 и обратный source/image переход с operator P/O, candidate I/0008 и новый H/0007→I/0008 upgrade; actual caller/fixture/API/worker/scheduler schemas в LOCAL и asm_test, rejected mixed pairs и coverage candidate helper; exact inventory names, сохранность historical receipts и populated downgrade refusal. Design принят для R2; scoped review и execution evidence ещё не получены |

Полный A03 admission, A04–A10 и A12 первым срезом не закрываются. После принятого
CONTRACT/C2 — код TURNS, штатные CI/browser/clean-source gates и независимый scoped C8;
C0 связывает результаты с exact implementation SHA. Mock или этот документ не являются
actual PostgreSQL/S3/Telegram evidence. Full CI принятого base не доказывает реализацию M3.

Pairing design §10 принят C0; findings01–04 остаются OPEN до scoped review/verdict.
До кода нужны scoped C2 по schema/locks/cutover, C1 по затронутой
versions/commands/API/caller delta и общая приёмка C0;
policy D2/G10/M15/N32 уже выбрана C0, но не заменяет эти gates. После них C0 отдельно
выдаёт TURNS. Findings C3 самостоятельно не закрывает; M3 не объявляется VERIFIED.
VM, binding, ACK, Telegram activation/sends и immutable receipts этой работой не меняются.


## 12. CONTROL — owner commands, activation fence и границы native intervention

### 12.1. Статус дополнения и действительные основания

**C3-M3.1-CONTROL-CONTRACT, proposal для C1/C2 и приёмки C0; реализации CONTROL нет.**
Поручение: [PR27](https://github.com/Elefesys/ai-service-manager/pull/27),
[активный M3_HANDOFF §0](M3_HANDOFF.md). Accepted main/T:
`ea1ae98ce9e5e26d5d0d14f3e6d278ecb9efbbad`, tree
`11ad506a859db155973f965bcdd0cebc7bc0d5ed`; continuation C0:
`8c6b13542bf661bb9b5a4994c5d0576407779372`. Его единственный parent — T.
Ветка `c3/m3-1-control`, этот же Draft PR сохраняется для будущей реализации.

R1 по [выдаче C0](https://github.com/Elefesys/ai-service-manager/pull/27#issuecomment-6100251718)
исправляет только§12 reviewed candidate `cf043901186f7f5178332e64a056d336cce0dc0f`.
Учтены [C1](https://github.com/Elefesys/ai-service-manager/pull/27#issuecomment-6100160198),
[C2](https://github.com/Elefesys/ai-service-manager/pull/27#issuecomment-6100147266) и
[C6](https://github.com/Elefesys/ai-service-manager/pull/27#issuecomment-6100099472).
Три P2 остаются OPEN до re-review/verdict C0; авторские исправления — FIXED FOR REVIEW.
Принятые C0 policy choice, Audit API design и C6 compatibility design отражены§12.12;
это не принятие всего CONTROL и не evidence его реализации.

Вступление и §§1–11 сохранены побайтно как принятый TURNS prefix, blob
`5e87375852331523491a47926b9c5bd49946c157`; их исторические PENDING/OPEN и «будущий I»
не являются текущими статусами. По реестру C0 TURNS принят на main в LOCAL/TEST,
пять implementation findings и четыре CONTRACT findings CLOSED. Здесь не меняются
их verdict/evidence. M3 остаётся IN_PROGRESS; новые проверки ниже ещё не исполнялись.

Прочитаны originals Spec §§4.10,5.1–5.14,14.11,18.5–18.8,18.14,24.7,25.7;
ADR022–026/121–128/180/197–198/217/267/272; MVP GJ-G/GJ-J; Roadmap M3;
Implementation Plan M3.1/M3.2; M2_CONTRACT §§2–5/9–10. Все11 originals сверены
с SOURCE_MANIFEST и предоставленными файлами. Runtime основания — actual0008,
`messaging_request_text`, `messaging_prepare_text`, `telegram_owner_observe`,
`OwnerMessagingService.send`, `turn_ingress`, `turn_group_message`, TEST consumer,
общий Audit и действующие schema runners. Раздел12 — additive design, не DDL permission.

CONTROL сохраняет owner intent, mode/generation и происхождение нового ingress.
Новых AI-команд, внешнего automated send или AI executor нет. Полное action/send
admission, проверка authority непосредственно перед эффектом и доказательство
Takeover→Resume против старого effect-producing worker относятся к GUARDS.
`AI` сейчас означает явное намерение владельца разрешить последующую автоматику,
а не запущенную модель, доступность Telegram или разрешение обойти product policy.

### 12.2. Три additive owner routes и строгий wire contract

Префикс прежний: `/api/v1/workspaces/{workspace_id}`. Пять M2 routes, их DTO,
status codes, отсутствие If-Match у manual send и правила pagination неизменны.
Новые routes не принимают query; дополнительный receipt/retry/reset endpoint не нужен.

| Method/path | Точный запрос | Ответ после commit |
|---|---|---|
| GET `/conversations/{conversation_id}/control` | Без body/query; действующая session и live OWNER/messaging:read | 200 `ControlStateResponse` |
| POST `/conversations/{conversation_id}/takeover` | `ControlCommandRequest`, один Idempotency-Key; cookie/Origin/CSRF | 200 `ControlCommandResponse`, ACCEPTED либо REPLAY |
| POST `/conversations/{conversation_id}/resume` | Тот же DTO/header; операция определяется route | 200 `ControlCommandResponse`, ACCEPTED либо REPLAY |

Отдельная domain permission `conversations:control` — только live OWNER; она
определяется в conversations policy, не в frozen `tenancy.v1`. ADMIN/PROVIDER,
worker context и caller Workspace не дают её. Не создаётся новый user/worker principal.
GET использует прежний owner read policy, не «доступ к любому Client по одному UUID».

Все DTO frozen/strict/additionalProperties=false; отсутствующий nullable field —
ошибка, как и duplicate JSON key, boolean/number вместо decimal string, NaN,
лишний header Idempotency-Key или If-Match у POST. Коды ошибок не включают SQL,
text, provider IDs, fingerprint, claim или private fence sequence. UUID — canonical
lowercase; время — UTC с6fractions. `PositiveVersion` — canonical decimal string
`[1-9][0-9]{0,18}` с проверкой значения ≤9223372036854775807, без leading zero/sign/
exponent/whitespace. Клиент сравнивает такие значения как strings/BigInt, не Number.

| DTO | Ровно эти поля и значения |
|---|---|
| `ControlCommandRequest` | `expected_client_id: UUID`, `expected_control_generation: PositiveVersion`, `expected_context_version: PositiveVersion`; не принимает target mode, actor, workspace, fence или reason |
| `ControlStateResponse` | `workspace_id`, `conversation_id`, `client_id`: UUID; `control_mode: HUMAN\|AI`; `control_generation`, `context_version`: PositiveVersion; `observed_at`: timestamp; `manual_delivery`: ровно `{has_dispatching: boolean, has_unknown: boolean}` |
| `ControlAcceptedResult` | `workspace_id`, `conversation_id`, `client_id`, `receipt_id`, `audit_event_id`: UUID; `operation: TAKEOVER\|RESUME`; `previous_mode`, `accepted_mode: HUMAN\|AI`; `previous_generation`, `accepted_generation`, `context_version`: PositiveVersion; `accepted_at`: timestamp |
| `ControlCommandResponse` | `outcome: ACCEPTED\|REPLAY`, `result: ControlAcceptedResult` |

GET выполняет один canonical SQL snapshot: принадлежность Conversation Workspace,
её Client/Connection, versions/mode и EXISTS по связанным Message/Outbox. Flags
показывают текущие DISPATCHING/UNKNOWN, включая прежние manual intents; список
сообщений и их PENDING/SENT/FAILED остаётся в M2 history. Никаких Outbox/job IDs,
provider fields или полного unbounded history в новом ответе. `observed_at` — время
этого DB чтения, не provider freshness. GET не refresh-ит канал и ничего не пишет.

`result` всегда описывает **сохранённую принятую операцию**, не актуальное состояние.
При replay старого Resume он может иметь accepted_mode=AI, хотя сейчас HUMAN/gen7.
Свежий state получают отдельным GET; response не смешивает receipt со случайным
поздним snapshot. Порядок HTTP completion двух вкладок не задаёт порядок команд;
UI позже сверяет conversation/client и generation и перечитывает state.

Новые routes проходят существующий AuthBoundary: Host/Origin, cookie, CSRF, actual
body cap4096bytes, read3s, media type/encoding, rate limits, CORS, no-store.
64KiB exception остаётся только у M2 POST messages; auth middleware не расширяется.
GET проверяет Origin при наличии, POST требует ровно configured Origin. Сначала
transport/security validation и строгий синтаксис, затем авторитетная DB admission.

| Ошибка | HTTP / строгий envelope `{"error":...}` |
|---|---|
| Session/Origin/CSRF/role | Прежние401/403 security codes; revoked OWNER никогда не получает receipt |
| Новый key: нет Conversation в Workspace либо expected_client_id не её canonical Client | 404 NOT_FOUND, без disclosure другой связи; existing key сначала проверяет fingerprint |
| Тот же namespace/key, иной fingerprint | 409 IDEMPOTENCY_KEY_CONFLICT |
| Новая команда с несовпадением любого expected counter | 409 STALE_STATE; без текущих versions в ошибке, нужен GET |
| Новый Resume запрещён structural availability/product policy | 409 NOT_ALLOWED; не DELIVERED/ACCEPTED |
| Generation исчерпана | 409 CONTROL_VERSION_EXHAUSTED; exact receipt replay всё ещё возможен |
| Body/key/UUID/query/decimal | 422 INVALID_REQUEST; прежние413/415/429 для boundary |
| Структурно недоступен billing snapshot | 503 BILLING_STATE_UNAVAILABLE + закрытый `state_reason` из R4 |
| DB/lock/неподтверждённый commit либо sequence exhaustion | 503 UNAVAILABLE; без утверждения «команда не принята» |
| Неожиданная ошибка | Прежний bounded500; не переводить произвольный exception в STALE/REPLAY |

### 12.3. Authority, product и порядок решений

**C0 согласовал один существующий продуктовый gate** для нового Resume:
реальный EntitlementService `evaluate_product(..., messaging.manual_send)` и
DB `messaging_manual_send_allowed`. Это консервативное условие доступности уже
подключённого messaging-продукта, **не выдача права AI-send по manual permission**.
CONTROL не добавляет catalog/entitlement/TEST interval и не меняет пять keys GET
billing. Будущие GUARDS/M4 обязаны отдельно определить и проверять автоматическую
capability; один Resume/его receipt её не заменяют. Policy choice принят C0;
temporal evaluation исправлена ниже и ещё требует C1 re-review (§12.12).
Frozen R4 read semantics этим решением не расширяются.

| Проверка | GET control | Новый Takeover | Новый Resume | Новый public manual intent |
|---|---|---|---|---|
| Active session/user/Workspace и live OWNER | Да | Да | Да | Да |
| Canonical tenant/conversation/client relation | Да | Да, expected_client_id | Да, expected_client_id | Прежняя relation по route; нового client/CAS body нет |
| Active Business | Не требуется для истории | Не требуется для безопасной остановки | Требуется | Прежний обязательный gate |
| ACTIVE canonical connection | Не требуется | Не требуется | Требуется | Требуется |
| Observed enabled/can_reply, окно24h, новый refresh | Нет | Нет | **Нет** | Для TELEGRAM — прежний fresh probe/CAS и DB window; CONTROLLED без HTTP |
| billing inactive/expired, SUSPENDED, key missing/false | Read разрешён | Остановка разрешена | Отказ; NORMAL/GRACE/LIMITED + valid true ESSENTIAL key допускают | Прежний отказ |
| Structural billing error/неработающий Telegram | Read не зависит | Остановка не зависит | Billing error503; Telegram outage сам по себе не блокирует | Прежние bounded observation/product отказы |
| Expected generation/context | Нет | Оба обязательны | Оба обязательны | Не добавляются в M2 request |
| Exact receipt replay после новых ограничений | Не применяется | После live OWNER/relations, до перечисленных новых gates | То же | Прежний M2 replay-first |

Takeover — локальная операция прекращения автоматики: зависимость от подписки,
can_reply или успешного внешнего HTTP оставила бы владельца без безопасной остановки.
Resume действует только на **будущий** ingress. Закрытое сегодня окно или stale
observation не должны требовать фиктивного send: новый client Message может открыть
окно позднее. Resume не refresh-ит права, не обещает ответа и не изменяет cached
Telegram state. INACTIVE connection/Business не активируются этой командой.
Реальный send по-прежнему обязан проходить все channel/product gates в своей фазе.

Авторитетный порядок POST внутри одного короткого auth.workspace:

1. Active M1 session admission и live OWNER; server-derived ws/actor/correlation,
   physical XID/task guards. Синтаксис проверен; Workspace берётся из unit,
   не из body. По чужому Workspace даже receipt lookup не выполняется.
2. Transaction advisory lock namespace CONTROL/key; fingerprint из DB; receipt
   lookup. Mismatch — conflict без entity data (включая изменённый expected_client).
   Exact match проверяет сохранённую canonical tenant/conversation/client relation
   и возвращает immutable result. Ни новый product/availability gate, ни stale
   expected state не отменяют законный replay.
3. Только для нового key: canonical Conversation/expected Client либо404,
   затем Business SHARE → connection SHARE; для Resume billing
   locks в прежнем порядке, затем Conversation NO KEY UPDATE. Takeover billing
   rows не берёт. Повторно проверить immutable relation под этим lock.
4. После final prepare и **всех потенциальных ожиданий** authority/connection/
   billing/Conversation locks — отдельный `POST_LOCK_PRODUCT_SNAPSHOT` → прежний
   EntitlementService (Resume), затем SQL повтор policy с тем же precedence:
   structural error → availability/product denial → expected_generation и
   expected_context_version → overflow. Старый `billing_snapshot()` здесь не годится.
5. Один atomic transition, receipt и Audit. Reply только после commit. Никакой
   сети, нового job/Outbox или независимого commit внутри control command.

Новая fixed query `POST_LOCK_PRODUCT_SNAPSHOT` в `billing/queries.py` выполняется
**одним statement** на том же guarded tenant connection. Однострочный MATERIALIZED
CTE однократно захватывает DB clock после locks; все flags и полный snapshot
вычисляются из этого единственного `evaluated_at` в одном statement snapshot:

```sql
WITH evaluation AS MATERIALIZED (
  SELECT pg_catalog.clock_timestamp() AS evaluated_at
)
SELECT evaluated_at,
  COALESCE((SELECT jsonb_agg(to_jsonb(a))
    FROM platform.workspace_billing_accounts a WHERE a.workspace_id=:workspace), '[]'::jsonb)
    AS accounts,
  COALESCE((SELECT jsonb_agg(to_jsonb(m) || jsonb_build_object(
    'is_active', m.effective_from <= evaluated_at AND
       (m.effective_until IS NULL OR evaluated_at < m.effective_until)))
    FROM platform.workspace_service_modes m WHERE m.workspace_id=:workspace), '[]'::jsonb)
    AS modes,
  COALESCE((SELECT jsonb_agg(to_jsonb(s) || jsonb_build_object(
    'is_current', s.effective_from <= evaluated_at AND evaluated_at < s.effective_until,
    'revision_state', (SELECT to_jsonb(r) || jsonb_build_object(
      'plan', (SELECT to_jsonb(p) FROM platform.saas_plans p WHERE p.plan_id=r.plan_id),
      'entitlements', COALESCE((SELECT jsonb_agg(to_jsonb(e))
        FROM platform.plan_entitlements e WHERE e.plan_revision_id=r.plan_revision_id), '[]'::jsonb))
      FROM platform.saas_plan_revisions r WHERE r.plan_revision_id=s.plan_revision_id)))
    FROM platform.workspace_subscriptions s WHERE s.workspace_id=:workspace), '[]'::jsonb)
    AS history
FROM evaluation
```

В проекции сохраняются **все** account/mode/history rows и pinned revisions,
catalog/entitlements, включая inactive/future history для structural validation;
нельзя фильтром спрятать invalid/overlapping state. Не допускаются application clock,
замена только evaluated_at при старых flags, несколько независимых SELECT или
повторные clock captures. Frozen public R4 GET, existing `SNAPSHOT` с
`CURRENT_TIMESTAMP`, `billing_snapshot()` и EntitlementService **не меняются**.

Отдельный `TenantUnitOfWork.post_lock_product_snapshot() -> RowMapping` выполняет
эту fixed query с server-derived Workspace. Он сохраняет task/active-unit/physical-XID
guards, live owner admission и owner/worker mutual exclusion, не принимает ws или
`allow=true`. Это guarded read method, **не новая SQL capability**; новых tables,
grants или product keys нет. SQL locks уже взяты, projection не добавляет обратных
lock edges. Один и тот же полный snapshot подаётся неизменному
`EntitlementService.evaluate_product(..., messaging.manual_send)` в новом Resume
и final public manual обоих providers (§12.5).

Resume service вызывает narrow prepare capability для locks/replay, затем этот
method и реальный EntitlementService, затем execute в **том же** unit. Prepare для
NEW собирает и удерживает locks; availability/product/CAS verdict следует после
post-lock evaluation, иначе scheduled activation во время ожидания теряется.
Exact replay выходит до projection/новых gates. Execute повторяет canonical
receipt/authority/DB-time policy, затем CAS; caller `allow=true` не принимает. SQL capability
не позволяет обходить policy вызовом без Python. Unknown commit восстанавливается
тем же actor/ws/conversation/body/key после восстановления auth/CSRF; новый key не
recovery. Owner revocation и команда сериализуются на прежних authority rows:
победивший revoke запрещает, победивший admitted commit сохраняется. DB read/replay
не выдаёт capability от имени старого actor после revoke.

### 12.4. Receipt, fingerprint и полная таблица переходов

Новый узкий `platform.conversation_control_receipts` нужен потому, что M2
`messaging_command_receipts` CHECK требует operation=SEND_MANUAL_TEXT и non-null
Message/Outbox/Audit composite refs. Ослаблять этот discriminator ради control
нельзя. Новый receipt не является универсальным workflow/action ledger.

Namespace: UNIQUE `(workspace_id, operation_namespace, idempotency_key)`, namespace
ровно `CONVERSATION_CONTROL_V1` для ОБЕИХ команд. Поэтому Takeover→Resume с тем же
key — conflict, не две операции. Key — прежний ASCII pattern1…128; actor не входит
в UNIQUE, но входит в fingerprint. Новый owner с чужим сохранённым key не читает
результат первого actor. M2 SEND namespace остаётся независимым. Advisory key —
`hashtextextended(ws::text || ':CONVERSATION_CONTROL_V1:' || key, 2009)`; оба operation используют его одинаково.
Hash collision даёт только лишнее bounded ожидание, authority/dedupe задаются rows/UNIQUE.

DB-authoritative SHA-256 от UTF-8, без JSON serialization, trim или нормализации:

```text
asm:m3:conversation_control:v1\n
<lowercase workspace UUID>\n
<lowercase actor UUID>\n
<lowercase conversation UUID>\n
<lowercase expected_client UUID>\n
<TAKEOVER or RESUME>\n
<canonical expected_control_generation>\n
<canonical expected_context_version>
```

`\n` — один LF; после последнего decimal нет LF. Key, correlation, receipt ID,
время и текущие counters не входят. Python/DB используют одинаковые vectors.
Сохраняются original actor/correlation, request fields/hash, before/after mode/gen,
context, accepted_at, exact result и typed Audit binding. Receipt column
`actor_user_account_id` — saved actor; `context_version` — saved accepted context,
равный `expected_context_version`; `expected_generation` хранит request
`expected_control_generation`. `audit_event_type` генерируется из operation:
TAKEOVER→CONVERSATION_TAKEN_OVER, RESUME→CONVERSATION_RESUMED.
Exact receipt key `(workspace_id,audit_event_id,conversation_id,accepted_generation,
audit_event_type,actor_user_account_id,context_version)` ссылается на Audit
`(workspace_id,audit_event_id,conversation_object_id,conversation_control_generation,
event_type,actor_user_account_id,object_version)` (§12.7). Membership FK сам по себе
равенство actors не доказывает. Все семь CONTROL components обязательны/non-null.
Accepted_at — DB clock
после lock/CAS, не CURRENT_TIMESTAMP до ожидания. Denied/stale/conflicting command
не сохраняет success receipt, Audit, generation/fence или частичный transition.

| Исходный режим | Новое намерение при совпавшем CAS и пройденных gates | Generation | Context | Fence / работа |
|---|---|---:|---:|---|
| HUMAN | Takeover → HUMAN | +1 | +0 | active fence=NULL; jobs не ставятся |
| AI | Takeover → HUMAN | +1 | +0 | active fence=NULL; jobs не ставятся |
| HUMAN | Resume → AI | +1 | +0 | новый fence из DB sequence под Conversation lock |
| AI | Resume → AI | +1 | +0 | новый generation **и новый fence**, прежний output не оживает |
| HUMAN или AI | Новый admitted manual TEXT → HUMAN | +1 | +1 | fence=NULL; прежние Message/receipt/Audit/Outbox/Job атомарны |
| Любой | Exact replay любого возраста, в том числе pre0009 manual | +0 | +0 | Сохранённый result; нет takeover, fence, Audit или повторного send |
| Любой | Same key / changed body или actor | +0 | +0 | Conflict, прежний receipt неизменен |
| Любой | Новый stale expected generation либо context | +0 | +0 | STALE_STATE; отклонённый key не становится success receipt |
| Любой | Security/availability/product/overflow отказ | +0 | +0 | Нет control/domain writes; observation M2 может отдельно законно сохраниться |
| Любой | Rollback / crash до commit | +0 | +0 | Весь transition/receipt/Audit отсутствует; sequence gap допустим |
| Уже изменён | Commit состоялся, ACK/процесс потерян | +0 при recovery | +0 | Exact replay результата, не повтор mutation; ambiguous503 не доказывает rollback |

Две вкладки с одним expected tuple/разными keys: под Conversation lock ровно одна
новая команда выигрывает; вторая получает STALE_STATE даже при одинаковом желаемом
режиме. Concurrent same key/body: один ACCEPTED, остальные REPLAY; changed body
не overwrites. После STALE новый осознанный intent требует свежего GET и нового key;
не делать auto-loop, который превратит устаревшее намерение в новую команду.
Takeover/Resume не меняют Conversation.version и не bump Turn.revision; stale
TEST consumer выявляет generation отдельно от context. Счётчики не wrap/reset.

### 12.5. Новый manual intent: takeover внутри M2 commit

Прежний `OwnerMessagingService.send` сохраняет две auth units для TELEGRAM:
prepare/replay → release → readonly refresh≤5s → новая auth unit и prepare/replay
→ fenced observation → product gate → `request_manual_text`. CONTROLLED public
остаётся одной unit без Telegram. Не использовать nested UOW или fake Owner.

Для нового intent final chain становится:
`authority → M2 key lock → Business SHARE → connection SHARE → Telegram state
(если применим) → billing locks (public path) → Conversation NO KEY UPDATE →
POST_LOCK_PRODUCT_SNAPSHOT/EntitlementService → повтор SQL temporal product/channel
checks в прежнем provider scope → HUMAN/gen+1/fence=NULL → новый Message
→ прежний context trigger+1 → Outbox/Audit/receipt/Job → commit`.

Предлагаемый `conversation_manual_prelock(uuid,text,text)` — узкая owner-only capability
**только для final public phase**. Она берёт отсутствующие authority/Business/
connection/state/billing locks в указанном порядке и последний Conversation lock,
не пишет mode и не выдаёт send permission. Args — conversation, exact text, key; она сначала повторяет canonical
`messaging_prepare_text`, поэтому сама не получает Conversation до M2 namespace
lock. В public service вызывается после prepare/replay (и Telegram observation)
до последнего `product_gate`; тот использует **новый** guarded
`post_lock_product_snapshot()`, не прежний `billing_snapshot()` с transaction-start
time. Это обязательно для public CONTROLLED **и** TELEGRAM: single DB clock и все
interval flags захватываются только после final prelock (§12.3). До него final NEW
path не решает temporal product gate по старому snapshot; replay exits сохранены.
Ранее взятые locks повторно не
добавляют обратных edges. Первой prepare перед HTTP Conversation lock не нужен.
Сама final SQL команда также prelock-ит Conversation перед mutation и повторяет
Telegram window/product checks после этого ожидания. В actual0007
`messaging_request_text` эти SQL product checks есть **только в TELEGRAM branch**;
public CONTROLLED должен проходить новый post-lock Python gate. Старый внутренний
CONTROLLED kernel сохраняет свой LOCAL/TEST product scope из M2: дополнительный
SQL product gate ему не вводится. Public path его не использует для обхода
EntitlementService. Frozen R4 GET projection не участвует в новом final admission.

В0009 заменяется **только тело** `messaging_request_text(uuid,text,text)`:
после его прежнего exact receipt-first и всех new-intent gates private
`conversation_manual_takeover(ws,conversation)` обновляет HUMAN/gen+1/fence=NULL.
Существующий `turn_manual_material` после INSERT Message остаётся единственным
источником context+1; второй increment в helper запрещён. До INSERT проверяются
overflow generation и будущего context; у manual — прежний409 NOT_ALLOWED, без
расширения M2 error/response DTO. SQL rollback любого следующего INSERT, Audit FK,
job или deferred constraint откатывает и takeover. Отдельного control receipt или
второго Audit для manual нет: его immutable MESSAGE_SEND_REQUESTED по-прежнему
доказывает один принятый intent. Новые standalone команды имеют свои Audit (§12.7).

Прежние bytes fingerprint, key/body, accepted_at, SendReceipt и202 unchanged;
receipt, принятый до0009, не дополняется новым takeover при replay. Новый manual
не получает скрытого expected-state параметра: если refresh начат раньше Resume,
но intent законно принят после него, последний admission устанавливает HUMAN.
Это не STALE_STATE bypass — M2 manual append никогда не имел control CAS. Отказ
observation CAS, revocation, expired product/window и replay ничего не захватывают.

PENDING send другого intent продолжает обычный manual admission; DISPATCHING уже
может иметь wire effect; UNKNOWN сохраняется. Takeover не отзывает эти manual sends.
Последующие SENT/FAILED/UNKNOWN/recovery меняют context по прежней таблице, но не
mode/generation. FAILED/UNKNOWN не возвращают AI. Изменение режима не обещает recall,
не маркирует UNKNOWN как CANCELLED и не разрешает resend новым key.

### 12.6. Ingress capture и Resume fence для ОБОИХ producers

Используется existing logged `platform.turn_ingress_seq`, CACHE1/NO CYCLE;
ни новой sequence, ни provider timestamp/update_id watermark. Resume резервирует
один `nextval` **под тем же Conversation NO KEY UPDATE**, что и accepted ingress.
Он сохраняется в `app.conversations.activation_fence_seq`; каждое новое Resume
выдаёт новый fence. Takeover/manual очищают active fence, но сохранённые receipt/
Inbox/Turn provenance не переписываются. Sequence allocation сама по себе не commit
order; общий lock ниже — обязательная часть алгоритма.

0009 добавляет nullable fields без DEFAULT/backfill:

| Место | Поля / инвариант |
|---|---|
| Conversation | `activation_fence_seq bigint NULL`; HUMAN→NULL; AI→positive non-null и generation≥2 |
| Inbox | `turn_control_generation bigint NULL`, `turn_control_mode text NULL`, `turn_activation_fence_seq bigint NULL`; либо всеNULL (pre-CONTROL/ignored), либо fresh CLIENT_MESSAGE с trusted turn mark, positive generation и HUMAN/AI; HUMAN fenceNULL, AI fence>0 и ingress_seq>fence |
| Turn | `ingress_control_mode text NULL`, `activation_fence_seq bigint NULL`; прежний positive `control_generation` неизменяем; NULL/NULL — pre-CONTROL, HUMAN/NULL или AI/positive — captured provenance |

Новые поля не входят в NormalizedEventV1/Telegram projection/fingerprint.
BEFORE INSERT `turn_ingress` отвергает caller-filled metadata, как прежние marks;
immutability trigger защищает полный новый tuple. Точное поведение:

1. CONTROLLED `messaging_ingest` сохраняет validate/route/connection SHARE/dedupe;
   Telegram `telegram_ingest` сохраняет update-key advisory/receipt-first/verified
   route и explicit ignored/lifecycle ветки. Только fresh CLIENT_MESSAGE идёт
   к INSERT. Оба entrypoints и trigger остаются VOLATILE/READ COMMITTED.
2. Trigger получает canonical connection SHARE **до** Conversation и marks.
   Отдельным последующим SELECT по `(ws,connection,provider_chat_id)` на свежем
   snapshot выбирает Conversation `FOR NO KEY UPDATE`. Если строка найдена,
   captures её current generation/mode/fence, затем присваивает clock/nextval;
   обе блокировки удерживаются до commit Inbox+Job(+Telegram receipt).
3. Если Conversation ещё нет, ничего не создавать в ingress: trusted capture
   HUMAN/gen1/fenceNULL — default будущей новой Conversation. Connection SHARE
   не позволяет PROCESS_INBOX с connection UPDATE одновременно её создать.
   После ожидания SHARE выполняется именно новый SELECT, а не старый snapshot.
   Создание Client/Identity/Conversation остаётся только в PROCESS_INBOX.
4. Resume держит authority/Business/connection SHARE, затем ту же Conversation
   NO KEY UPDATE; final CAS и product, gen+1, `nextval` fence и receipt/Audit
   коммитятся вместе. Не делает snapshot существующего MAX(seq), не перечисляет
   Inbox/Turns и не ставит jobs по backlog. Unknown Conversation —404, не создание.
5. PROCESS_INBOX сохраняет job→свой Inbox NO KEY UPDATE→connection UPDATE→
   identity/file plan→Conversation→Turn. Origin lookup — отдельный SELECT после
   connection barrier по§2: legacy-null ingress приоритетен, затем минимальный
   committed ingress_seq **namespace Message**, включая conflicting inputs.
   Captured control tuple берётся из этого origin, не из job или current Conversation.

Если нижний ingress I1 ещё не committed, I2/Resume не могут его «перепрыгнуть»
по Conversation lock; PROCESS_INBOX также ждёт connection SHARE holders. Commit I1
оставляет старый captured generation, rollback I1 — только gap. Для нескольких
новых Inbox до создания Conversation их captures HUMAN/gen1 остаются такими и
после материализации другим worker и последующего Resume. Duplicate-first после
Resume наследует самый ранний origin; same-event replay не получает новые marks,
а проигравший `ON CONFLICT` INSERT не меняет canonical tuple. Fingerprint conflict
не становится способом reactivation; retained legacy origin всегда исключён.

**Предикат activation eligibility**, ещё не action admission GUARDS:
Turn captured mode=AI, его fence non-null, generation и fence равны current
Conversation AI generation/fence; все member origins nonlegacy, с тем же exact
captured tuple и ingress_seq>fence. Один false/NULL запрещает eligible. Future action
также потребует current context/claim/authority/product/channel checks, здесь их
успешность не утверждается. Не выдавать этот predicate как публичный allow_send.

Pre0008 NULL ingress остаётся без membership/Turn. Pre0009 Inbox с существующим
turn mark, но NULL control tuple, сохраняет grouping TURNS **без authority**:
новый materialized Turn имеет исторический generation1 и NULL provenance, а не
поколение текущей Conversation. Это допустимо ровно потому, что0008 разрешала
только HUMAN/gen1 и upgrade проверяет этот инвариант; произвольный legacy generation
не угадывается. Уже существующие Turns и TEST receipts остаются побайтно прежними
по всем старым columns. Нет заполнения NULL из нынешнего режима задним числом.

Группа не пересекает captured `(generation, mode, fence)`; NULL provenance также
отделена от нового HUMAN capture. `turn_group_message` берёт origin tuple:
совместимый COLLECTING Turn агрегируется по прежним D2/G10/M15/N32. Более новое
поколение закрывает старую collecting группу по прежним min(ingress,quiet,hard)
правилам и начинает следующую; clock/out-of-order case обрабатывается как late.
Старый generation/NULL-origin, пришедший после новой группы, получает отдельный
сразу sealed singleton, **не закрывая и не изменяя** новое окно. При generation1
pre-CONTROL NULL считается старше fresh HUMAN/gen1. Никакое закрытие не продлевает
media deadline. `turn_member_check` проверяет совпадение capture Turn/origin,
в дополнение к прежним tenant/Message/File/origin FK и namespace checks.

GROUP/MEDIA и поздний File READY/FAILED продолжают readiness/context по TURNS;
generation/provenance Turn не обновляется, не запускается новый backlog pass.
Job наследует capture через immutable Turn FK + revision, без caller payload и
нового job kind. PROCESS_TURN публичный Python ABI, `TURN_TEST_V1`, snapshot/digest
и immutable receipt format **не меняются**. TEST consumer остаётся effect-free и
может OBSERVED в HUMAN того же поколения; это не automation eligibility. При
generation/context mismatch его обычный finalize сохраняет STALE; revision mismatch
до/при execute/recovery — SUPERSEDED. Старый saved OBSERVED при replay не понижается.
CONTROL не переписывает чужие RUNNING jobs, не делает eager batch cancellation.

### 12.7. Минимальная0009, Audit, capabilities и полный lock graph

Резерв C0: `migrations/versions/0009_conversation_control.py`, revision0009,
down_revision0008. **Создать миграцию можно только после отдельной выдачи.**
Applied0001–0008, включая R1 NOWAIT/final-age correction, immutable.

Добавляется одна таблица `platform.conversation_control_receipts`; qualified
inventory0009 = exact34 таблицы0008 + она, итого35, не допуск любого количества35.
PK `(workspace_id,id)` с uuidv7; namespace/key UNIQUE; UNIQUE
`(workspace_id,conversation_id,accepted_generation)` и `(workspace_id,audit_event_id)`.
Поля request/result описаны§12.4; additionally saved `activation_fence_seq` private
(Resume positive, Takeover NULL). CHECK: target соответствует operation,
accepted_generation=expected_generation+1, context_version=expected_context_version,
previous_generation=expected_generation, hash32bytes, конечное время, строгий
result равен immutable columns. Saved/expected context — positive bigint;
generated `audit_event_type` по operation связывает Audit (§12.4).

Supporting UNIQUE `(workspace_id,id,client_id)` у Conversation позволяет receipt
FK `(workspace_id,conversation_id,client_id)` без same-Workspace/different-Client
перестановки. Actor FK на existing workspace membership; все refs RESTRICT.
Нет FK к mutable current generation: исторический receipt переживает новые команды.
Новая таблица ENABLE/FORCE RLS, migrator-only policy; PUBLIC/asm_runtime не получают
SELECT/DML. Читать/писать можно лишь через typed owner capabilities, не по receipt UUID.
Историческая membership строка не удаляется ради revoke и не теряет свои receipt refs.

Audit additive: два variants `CONVERSATION_TAKEN_OVER` и `CONVERSATION_RESUMED`:
USER_ACCOUNT/non-null actor, object_type=CONVERSATION, object_id=canonical Conversation,
object_version=**сохранённый context version**, не смешанный generation counter.
Payload ровно `{previous_mode, control_mode, previous_generation, control_generation}`;
mode enums, generations — canonical decimal strings, new=old+1; target HUMAN/AI
определяется event_type. Нет body/key/chat/provider/claim или public fence.
Generated nullable `conversation_object_id` обеспечивает typed tenant FK; generated
nullable `conversation_control_generation` из строгого payload нужен для exact
receipt→Audit FK. Минимальный supporting Audit UNIQUE и точная связь:

```sql
-- app.audit_events: supporting UNIQUE
UNIQUE (workspace_id, audit_event_id, conversation_object_id,
        conversation_control_generation, event_type, actor_user_account_id,
        object_version)

-- platform.conversation_control_receipts
CONSTRAINT conversation_control_receipts_audit_fk
FOREIGN KEY (workspace_id, audit_event_id, conversation_id, accepted_generation,
             audit_event_type, actor_user_account_id, context_version)
REFERENCES app.audit_events
  (workspace_id, audit_event_id, conversation_object_id,
   conversation_control_generation, event_type, actor_user_account_id,
   object_version) ON DELETE RESTRICT
```

Все receipt components — NOT NULL; CONTROL Audit discriminator CHECK явно требует
non-null `conversation_object_id`, `conversation_control_generation`,
`actor_user_account_id` и positive `object_version`.
Так исключён MATCH SIMPLE NULL bypass. Зафиксированы **тот же saved actor и context**,
объект, accepted generation/event и единственный Audit; result/transition CHECKs
и typed Client/Conversation refs сохраняются. Это не FK к mutable текущей generation
и не новый generic consistency helper. Nullable generated поля прежних billing/
Message branches сохраняют прежний смысл; их constraints не ослабляются.

Старые billing/Message discriminators, payload/actor/mandatory FK и Audit pagination
остаются exact. Общий Audit GET читает новые события: необходимы два строгих backend
DTO variants/generated OpenAPI и два frontend parser/type/label variants
«Управление передано владельцу» / «Автоматика разрешена владельцем» с mixed-page
regression. Это только совместимость существующего Audit screen; CONTROL UI не
выдана. Нельзя фильтровать новые события из общего Audit или fallback-ить в billing label.

Предлагаемый exact SQL ABI: **ровно восемь** new functions в platform. Для каждой
строки без исключений owner=`asm_migrator`, exact `search_path=pg_catalog,pg_temp`
(catalog proconfig `["search_path=pg_catalog, pg_temp"]`), PUBLIC EXECUTE запрещён.

| Signature | SECURITY profile | asm_runtime EXECUTE | Authority / использование |
|---|---|---|---|
| `conversation_control_read(uuid) RETURNS jsonb` | DEFINER | Да | Live owner/read, один state snapshot |
| `conversation_control_prepare(uuid,uuid,text,text,bigint,bigint) RETURNS jsonb` | DEFINER | Да | Args conversation, expected_client, operation, key, expected_generation, expected_context; REPLAY либо NEW и все locks, без mutation |
| `conversation_control_execute(uuid,uuid,text,text,bigint,bigint) RETURNS jsonb` | DEFINER | Да | Тот же canonical admission/locks, saved replay или atomic transition; DB повторяет product/CAS |
| `conversation_manual_prelock(uuid,text,text) RETURNS void` | DEFINER | Да | Final owner public manual phase, только locks, не mode mutation/allow flag |
| `conversation_control_fingerprint(uuid,uuid,uuid,uuid,text,bigint,bigint) RETURNS bytea` | INVOKER | Нет | Private pure DB codec без table access; ws/actor/conversation/client/op/expected counters |
| `conversation_control_locked(uuid,uuid,text,text,bigint,bigint) RETURNS jsonb` | DEFINER | Нет | Private единая authority/key/Business/connection/billing/Conversation lock+replay процедура prepare/execute, не две расходящиеся implementations |
| `conversation_manual_takeover(uuid,uuid) RETURNS void` | DEFINER | Нет | Private ws/conversation, canonical M2 new intent only; HUMAN/gen+1/clear fence, без context bump |
| `conversation_turn_activation_matches(uuid,uuid) RETURNS boolean` | DEFINER | Нет | Private ws/Turn, predicate§12.6 для SQL/tests; не public action capability |

Все mutating/capture functions VOLATILE/READ COMMITTED; общий guard
`turn_require_isolation`, task/XID и owner/worker mutual exclusion сохраняются.
REVOKE PUBLIC для всех восьми, grant только четыре owner capabilities.
Отдельный guarded fixed-query `post_lock_product_snapshot()` (§12.3) **не девятая
SQL function** и не расширение worker context. Private helpers/sequence/
receipt internals недоступны runtime; frozen tenancy permissions не расширяются.
Prepare не превращает prior transaction в token authority: execute обязан сам
проверить canonical state, даже если prepare вообще не вызывался. Идемпотентность
обеспечивают UNIQUE и advisory namespace, не флаг caller.

Existing signatures неизменны.0009 заменяет тела `turn_ingress`,
`turn_group_message`, `turn_member_check`, `messaging_request_text`; усиливает
immutability для новых fields, разрешает mode AI с coherent fence CHECK.
`messaging_ingest`/`telegram_ingest` продолжают production trigger path обоих
producers; их body менять не требуется. `turn_snapshot/turn_execute/turn_consumer_*`,
claim/recovery/reschedule, files, send begin/finish сохраняют принятый ABI/semantics.
Ни UPDATE всех old jobs, ни private capability с произвольным Workspace authority.

| Writer / implicit edge | Обязательный порядок и отсутствие обратного ожидания |
|---|---|
| Standalone owner command | M1 session/shared admission → Workspace/user/membership SHARE → CONTROL namespace advisory → Business SHARE → connection SHARE → billing SHARE для Resume → Conversation NO KEY UPDATE → новые Audit/receipt |
| Manual public final phase | Те же authority → M2 key advisory → Business/connection → Telegram state UPDATE для observation/prelock → billing → Conversation → новые Message/Outbox/Audit/receipt/Job; old receipt replay выходит раньше |
| CONTROLLED fresh ingress | route read → connection SHARE → Conversation NO KEY UPDATE если есть → nextval/Inbox/new Job; absent Conversation под connection barrier |
| TELEGRAM fresh ingress | update-key advisory → receipt/route/state read → connection SHARE → Conversation NO KEY UPDATE → nextval/Inbox/new Job/receipt; early duplicate/lifecycle/ignored paths без control capture |
| PROCESS_INBOX | job UPDATE → свой Inbox NO KEY UPDATE → connection UPDATE → identity advisory → existing/new file plan → Conversation → Turn/member/new jobs; origin MVCC, чужие Inbox не lock-ить |
| File completion/retry/exhaustion | job → FileObject → PREPARED intents поid → Conversation → member Turn; hooks не меняют generation/fence; deferred WINNER FK targets уже prelocked |
| Send admission | job → Outbox → original actor authority → Business → connection SHARE → Telegram state/billing → Conversation только terminal material hook; owner не ждёт existing job/Outbox после Conversation |
| Send finish/recovery | job → Outbox → Conversation; existing saved terminal replay first, context once, без control mutation |
| GROUP/MEDIA/TEST | job → Conversation → Turn; не получает connection/file/Outbox locks и не lock-ит чужой job |
| Telegram lifecycle / billing writer | Существующие state или billing/authority locks, без Conversation→connection/billing edge; control не добавляет lifecycle takeover |
| FK/trigger | Message→Conversation KEY SHARE совместим с NO KEY UPDATE; receipt/Audit→Conversation и membership targets уже held; origin Inbox KEY SHARE совместим с NO KEY UPDATE; Turn new jobs FK targets held. New own rows не равны захвату чужого existing job |

Billing order точный existing: account → service mode → subscriptions поsubscription_id
→ revisions поid → plans поid → entitlements по(revision,key), SHARE. После последнего
Conversation lock нельзя впервые получать connection/authority/state/billing/file/
existing-job locks. Повторные проверки уже held rows не оправдывают новый обратный
edge. Control commands не берут Turn locks: старые результаты устаревают через
монотонную generation. Новый post-lock snapshot выполняется после последнего
Conversation lock, без дополнительных locks и без прежнего CURRENT_TIMESTAMP;
SQL execute повторяет policy по DB clock до CAS. Maintenance сохраняет single-candidate subtransaction,
NOWAIT до **окончательного** retry-age решения, узкий P3001 catch и rollback BUSY;
новый control writer не добавляет туда blocking FK. Constraints и deferred checks
проверяются отдельными concurrency tests до C2 implementation acceptance.


### 12.8. Upgrade/downgrade и source/schema0008→0009

Сначала exact Alembic head0008, роли и schema inventory. Cutover LOCAL/TEST:
закрыть ingress/API, остановить новый claim/dispatch и drain API/worker/**scheduler**,
закрыть auth/fixture pools и незавершённые transactions; upgrade отдельным migrator.
Один migration commit добавляет nullable metadata **без DEFAULT и backfill**,
receipt/Audit constraints/helpers и новые определения. Table locks исключают
concurrent writers при смене trigger. Проверить precondition0008: все Conversations HUMAN/gen1 и все Turns gen1;
неожиданный state — STOP, не reset. Не изменять existing version/rows, не создавать jobs/Turns/consumer receipts из истории.

M2 text/image bytes, IDs, fingerprints, manual receipts, accepted_at, PENDING/
DISPATCHING/UNKNOWN, grants/uploads/private objects и все старые columns TURNS
сохраняются. Existing Turn control_generation и ConsumerReceipt/digest остаются
прежними; новые fieldsNULL означают отсутствие новой activation authority.
Старые PENDING Inbox и поздняя media не получают futureAI authority при drain/restart.
Новый runtime обрабатывает имеющиеся M2/TURNS jobs без пересоздания и reset attempts.

0009 downgrade — **CONTROL-clean**, не требование пустого TURNS:
до любого destructive DDL/restore проверить отсутствие control receipts/Audit,
non-null CONTROL metadata Inbox/Turn и любых Conversations с AI, gen≠1 или fence.
Любой blocker — SQLSTATE55000, все rows/functions/grants/schema остаются прежними.
Можно сохранить populated0008 Turns/members/TEST receipts и M2 history, если новой
CONTROL истории нет. Не чистить новые captures/commands ради успеха cycle.
После разрешённого0009→0008 восстановить exact0008 definitions/triggers/CHECKs/
permissions, сохранив все0008 rows и counters. Нельзя вслед за этим автоматически
downgrade0008→0007: у TURNS свой independent refusal. После CONTROL данных — forward
fix либо отдельно принятый restore, не запуск T runtime поверх0009.

Мixed0008/0009 runtime не поддерживается в этой LOCAL/TEST процедуре. Это bounded
schema compatibility gate, не production rollout и не отмена Expand/Migrate/Contract
Spec18.14/25.7/ADR217. VM updater, owner ACK или разрешение эксплуатации не проектируются.

Обозначения§10 P/O/H0007 **не меняются**. Новый predecessor **T** — только принятый
`ea1ae98ce9e5e26d5d0d14f3e6d278ecb9efbbad`/0008; новый **C (I_CONTROL)** — будущий exact CONTROL
implementation checkout/0009, не настоящий docs-only SHA. I из исторического§10
относился к TURNS; в новых reports не переименовывать его в CONTROL.

| Phase | Source/image/fixture | Exact schema и обязательный outcome |
|---|---|---|
| Historical intent/image/state × normal/Docker29 | Frozen H shell/helper/fixtures; P/O runtime/operator ровно по§10 |0007→0007, прежние six shards,31-table fingerprints/receipt DAG/operator proof/180s/UNKNOWN-wire1 |
| Retained TURNS schema, оба state shards | Из detached **T** без patch: `sh scripts/test_telegram_egress.sh --schema-upgrade H T`; H baseline, R_T/D_T target | Отдельные fresh LOCAL0007→0008, прежний actual committed0008/exit86/fresh observer, H/8 refusal, T/8 forward/restart, clean cycle/populated refusal. Это всё ещё **0007→0008** proof |
| CONTROL default transport/lifecycle | C shell/helper/API/worker/scheduler/operator/TEST fixture | LOCAL0009 + отдельный TEST0009; прежние6 wire+6 lifecycle, строгий E05, full35-table fingerprint/UNKNOWN-wire1/HTTP-outside-transaction |
| Новый CONTROL baseline/negative pairing, оба state shards | C coordinator; baseline R_T/D_T, C image только для migration-role controller | **Другая fresh LOCAL DB/volume**,0008 seeded through T. C/8 readiness rejected до runtime admission; нельзя использовать generic C fixture на8 |
| Drain и clean cycle | Все T callers/pools drained; D_C migrator |0008→0009→0008 без CONTROL data, с populated TURNS/M2; exact34-table fingerprint, definitions/grants восстановлены; T starts лишь на observed8 |
| Настоящая post-commit result loss | Separate D_C migrator commits0009, затем marker + exit86 до normal success exit | Caller получает failure; новый observer process/connection читает revision/role/DB identity. Expected loss отличается от любого произвольного exception |
| Recovery choice | Никакого старта по одному return code или «upgrade уже вызывали» | Observed9→только exactC/9; observed8 после подтверждённого rollback/clean cycle→только T/8; unknown/unreadable/несколько heads→STOP. T/9 и C/8 запрещены |
| Forward/restart и populated refusal | Только R_C/D_C, exact pinned source/tree/manifest; все API/worker/scheduler | Preserved M2+TURNS projection, private S3 hash, pending manual/UNKNOWN/receipt replay; fresh control/fence scenarios; новые IDs при restart; refusal до DDL по каждому blocker |

Новый explicit selector C: `--control-schema-upgrade T C <private-budget-request>`, entrypoint
`run_control_schema_phase` в candidate migration harness. Он не расширяет старый
`schema_recovery_source` до «8 или9»: отдельный CONTROL guard требует конкретную9
и exactC. Existing `--schema-upgrade H T` исполняется только frozenT shell; C не
исполняет старый H→C branch с body, жёстко ожидающим0008. Неподходящий selector/
source/schema останавливается до build/start. `migration_source` и saved-plan
historical guards по-прежнему допускают только0007→0007, включая initial/resume/
preflight/rollback; наличие нового inventory9 не расширяет этот operational helper.

Coordinator sequence в обоих state shards: frozenH historical → сохранить archive/
reports → полный existing disposable cleanup → frozenT schema-only → сохранить
verbatim reports/source/image evidence отдельно `turns-schema` → cleanup → новый
C control-schema. Каждый этап начинает с проверенного empty disposable daemon/
volume inventory и собственного project/private state. Никакого общего mutable DB,
перезаписи baseline или удаления чужих containers/volumes; существующие dedicated
runner guards и scoped cleanup сохраняются, prune не используется. intent/image
shards остаются только historical; browser/foundation/default lanes не сокращаются.

Runtime/development images строятся из `git archive` exact source с existing locked
build inputs. H/T image reuse разрешён только после actual copied-blob/tree/kind
проверки immutable image, не tag. На C API/worker/scheduler используется exact R_C;
ни schedulerT при API C, ни миграция только asm_test вместо held asm_local не допускаются.
Reports сохраняются **до teardown даже при failure**: original source/checkout SHA,
head и tested virtual merge/parents/tree, role/DB/volume identity, fresh observed
revision, fail exit/marker, source/image IDs/manifest, before/retained projections,
recovery/restarted caller IDs, private S3 bytes/hash, exact receipt/fingerprint state.
Unknown/unreadable negative probes отдельно маркируются как unit или actual PG,
не подменяют настоящий commit/lost-result сценарий. Outer failure retention начинается
до source/archive/build/reuse/probe, а не лишь внутри runtime try: ранний отказ также
оставляет source/phase, exit/reason и elapsed ledger. T reports копируются до удаления
detached checkout; cleanup относится только к owned processes/projects/volumes.

Inventories статически заданы по фазе: exact names0007 из§10,0008=34,0009=35.
**Фиксированный T column inventory содержит все34 qualified tables** и все старые
columns, включая весь M2 и Turn/member/job/consumer receipt. При forward0008→0009
данные сравниваются по33 data tables; `platform.alembic_version` проверяется отдельно
как exact8→9, как и новые NULL fields/empty control receipt. Никакого dynamic
intersection из actual схемы. Default same-schema C fingerprint включает все35
таблиц и все их columns.
Same-count substituted/missing/extra names — отказ. Только clean reverse cycle
требует снова полного34-table fingerprint + exact restored definitions/grants;
новые данные ради него не удаляются.

Цена proposal ограничена одним дополнительным schema phase только в двух existing
state jobs: прежние H proof и T proof не повторяются внутри C phase; T image, уже
полученный для retained phase, повторно не строится при подтверждённых bytes.
Существующие budgets **не растут**: nine jobs, state25min с setup/upload/cleanup,
foundation35min, historical held180s, совокупный prepare/build600s. Прежние command
bounds сохраняются: build480s, controller/start120s, migration/probe30s, drain60s,
teardown90s, normal command40s; transport5/10/20s, lease30s, DB2/5s, retries5/15min.

Actual helper `migration_budget` — **process-local**; detached T не наследует его
deadline. Принят консервативный protocol C6 без patch T: C coordinator ведёт один
monotonic ledger600s и вычитает **весь supervised retained-T shell interval**,
включая его prepare/runtime/cleanup, а также все уже выполненные schema-image
archive/preparation/build/reuse verification intervals. Пересекающиеся интервалы
не считаются дважды, ни один ранее выполненный подготовительный этап не теряется.
T запускается под watchdog с оставшимся временем этого ledger; после него C получает
**только остаток**. Нулевой/отрицательный остаток — STOP с report, не fresh600.

Для передачи между процессами C coordinator создаёт в своём private temp directory
одноразовый budget request (0600, exact T/C/phase, charged seconds и absolute
monotonic deadline остатка на этом runner). Новый CONTROL selector принимает его
как обязательный internal budget operand в дополнение к T/C и передаёт в
`schema_request` нового `run_control_schema_phase`. Это test-only channel в уже
предложенных coordinator/shell/harness paths, не env/product parameter и не изменение
frozen T selector. Child проверяет owner/формат/source/phase и допустимый остаток,
вычитает время handoff по тому же monotonic clock, затем вызывает существующий
`migration_budget(remaining)` только вокруг C prepare/build/reuse. Нельзя создавать
новые600s, nested/reset budget или менять helper global implementation. Суммарный
ledger и фактическое окончание preparation проверяются и сохраняются coordinator;
отдельный общий state deadline продолжает действовать после preparation.

Supervisor обязан bounded завершить child **и его process group** при deadline/
failure, дождаться их остановки, сохранить reports и выполнить owned cleanup в
прежних bounds. Detached worktree и чужие ресурсы не служат обходом cleanup. Failure
retention охватывает в том числе source/build/probe до runtime try; outer finally
копирует T reports до удаления checkout. Stage timings и charged ledger публикуются
для retainedT/newC/cleanup. Это design bounded work, **не измеренный PASS по wall time**.
C6 design PASS принят; исполнимость actual implementation CI ещё не доказана.
Если retained proof + новый phase не помещаются, вернуть C0 фактический timing/
failure и конкретный scope diff.
Нельзя убрать phase, повысить timeout, пересобрать patchedT или заменить PG mocks.

### 12.9. Native/edit/delete: явная невыданная часть A08

**Native-owner observability NOT VERIFIED.** Нет принятого account evidence;
прежний TEST interval истёк. Настоящего Telegram probe/продления TEST в этой задаче
нет. Для ближайшего CONTROL C0 выбрал обязательные Console Takeover и atomic manual
takeover; automatic native takeover и material edit/delete **не реализуются**.

| Наблюдение | Текущий durable outcome / почему недостаточно для нового control |
|---|---|
| `from.id` совпадает с independently approved Owner | Прежний IGNORED_NATIVE_OWNER_MESSAGE; не доказано, что нужные native replies стабильно наблюдаемы на этом account/connection |
| `sender_business_bot` присутствует, включая нашего bot | Прежний IGNORED_ECHO; не второе клиентское сообщение, не подтверждение UNKNOWN и не takeover |
| Другой bot / bot sender / неподдержанный sender | Прежний echo/UNSUPPORTED mapping по M2 codec; не приписывать его Owner или Client |
| `is_from_offline`, автоматические/offline-сообщения | Поле само по себе не authority и не новый discriminator0009; действует прежняя supported/ignored классификация, control не меняется |
| Unsupported/document/service/nonbusiness | Explicit existing ignored outcome; нет silent client identity или новой Message |
| Поздний native update, потенциально до Resume | Receipt/доставка сейчас не доказывает новое вмешательство после fence; не откатывать новый Resume автоматически |
| Edit/delete | Прежние IGNORED_MESSAGE_EDITED/DELETED; не менять semantic Message/version, file или новый control |

Отдельный будущий gate C0: разрешённый finite TEST interval и exact runtime/binding;
сравнение Client text/photo, native Owner reply, own echo, other-bot/offline,
edit/delete и delayed/redelivered events на одном подтверждённом connection;
редактированное evidence полей sender/chat/connection/IDs/time и того, что фактически
доставлено webhook, без token/содержимого диалога. Нужны negatives отсутствия native
updates и доказуемая causal/order policy против pre-Resume delayed update.
Нельзя принимать очередность update_id или provider date за гарантированный epoch.
По evidence C0 принимает typed provenance/codec с C1/C2/C3 до автоматического path.

Новый codec должен иметь явную version/receipt migration compatibility; V1 hashes
не переписываются, исторические IGNORED не reprocess-ятся, outgoing Owner не получает
Client identity. Если provenance/order остаются неоднозначными, остаётся явное
Console управление и честное ограничение native, не условный VERIFIED. Материальные
edit/delete, native semantic Message/context+1 требуют следующего отдельного scope.

### 12.10. Предлагаемый exact implementation scope, ещё не write permission

Current write path — **только§12 в этом M3_CONTRACT.md**; R1 исправляет proposal,
не immutable prefix. Ниже finished proposal для C0; после
C1/C2 review C0 отдельно выдаёт exact список. Нельзя считать таблицу разрешением
работать сейчас. Paths сгруппированы только там, где причина одна; glob-allowlist нет.

| Exact future paths | Необходимая дельта / symbols |
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

Относительно cf043901 future allowlist дополнен **ровно двумя existing paths**:
`backend/src/asm/billing/queries.py` и `tests/test_tenancy_postgres.py`. Сейчас они
не меняются. В inventory запрещены subset/count-only/prefix exclusions, skip или
ослабление grants: восемь profiles проверяются наряду со всем прежним exact набором.

Новые SQLSTATE предлагаются локально: P2401 с exact перечисленными control codes;
не менять общую M1 exception policy. `_messaging_execute` сохраняет прежний P2001/
P2301 mapping; добавляет узкую передачу control domain errors для новых methods.
P3001 maintenance BUSY не переносится в owner API. Existing `messaging:read/send`,
manual fingerprint/SEND response, worker scan ABI, TurnSnapshot/ConsumerReceiptV1,
normalization, Audit cursor и billing contact CAS не расширяются произвольно.

Новые frontend Audit paths — необходимая совместимость общего backend Audit,
требующая явного C0 scope, а не начало C5 CONTROL UI. `scripts/export_contracts.py`
уже экспортирует create_app и не требует изменения. Auth middleware/settings,
`conversations/turns.py`, messaging worker/database/commands/models, TelegramClient,
codec/webhook, transport/config/relay, dependencies/locks, Compose/workflows/images,
TASK_REGISTER/M3_HANDOFF/AGENTS/canon не запрашиваются. Иная фактическая потребность
в реализации возвращается C0 с конкретным diff до изменения.

### 12.11. Матрица будущего execution evidence

Все строки — **PLANNED, NOT EXECUTED для CONTROL**. Future commands:
`pytest -q tests/test_m3_1_control.py`; реальные PostgreSQL/API/migration suites
`tests/test_m3_1_control_postgres.py`, `tests/test_m3_1_control_api_postgres.py`,
`tests/test_m3_1_control_migrations.py` через existing integration runner;
`sh scripts/ci.sh`, `sh scripts/test_browser.sh` и all9 clean-source gates на exact
implementation source. Названия cases ниже — proposed test IDs, не существующие PASS.

| Proposed test/scenario | Barrier / durable assertion | Критерий |
|---|---|---|
| `control_transition_matrix` | HUMAN/AI × Takeover/Resume/new-key same mode; +1gen/+0context; exact Audit+receipt, no jobs/fence except Resume | A07, control-частьA03 |
| `control_two_tabs_and_replay` | Два actual HTTP clients/DB transactions после одного GET; same/different keys, body/actor changes, stale gen либо context; один commit, сохранённый результат против свежего state | A07 |
| `control_authority_and_scope` | Реальные cookie/Origin/CSRF revoke/role/session races до authority lock и во время ожидания; другой Workspace и same-Workspace mismatch Client/Conversation; никаких partial writes/receipt disclosure | A07/изоляция |
| `control_product_and_channel_matrix` | Suspended/expired/missing/false/invalid state; stopped adapter/closed window/disabled connection; Takeover/read не вызывают HTTP/billing, Resume policy и structural→availability/product→CAS precedence строго по§12.3 | A07/границаproduct |
| `post_lock_product_boundaries` ×Resume/public manual CONTROLLED/TELEGRAM | Подтверждённый Conversation NO KEY UPDATE wait без material mutation: subscription и service-mode expiry **и scheduled activation**, обе стороны half-open boundaries; один post-lock clock/полный snapshot, re-auth/policy, denied/replay без control/context/Audit writes | C1-M3-CONTROL-01/A07 |
| `frozen_r4_snapshot_compatibility` | Existing SNAPSHOT/billing_snapshot и public GET сохраняют transaction-start evaluated_at и согласованные прежние flags/history/errors/пять TEST keys; новый gate не меняет R4 | C1-M3-CONTROL-01/R4 |
| `control_commit_loss_and_overflow` | Fault до update/между Audit и receipt/на commit; committed ACK loss→same result, rollback→нет всех writes; gen/context BIGINT/sequence exhaustion без wrap, replay всё ещё доступен | A07/A11 |
| `manual_atomic_control_and_replay` | Actual M2 request path: HUMAN/AI, новый/replay/pre0009 receipt; fault после takeover/Message/Audit/Outbox/Job и deferred FK; gen+1/context+1 только новый commit, exact old bytes | A07/contextA03/M2 |
| `manual_refresh_interleaving` | Observe network barrier вне обеих business units; concurrent Resume, rights observation CAS/revoke/expiry/product failure; final accepted order определяет HUMAN, denied/replay не меняют control | A07/M2 |
| `ingress_resume_serialization` ×CONTROLLED/TELEGRAM | Удержать producer после connection+Conversation locks до nextval/commit; наблюдать pg_locks/blocked PID, Resume ждёт. В обратном порядке ingress получает gen/fence после Resume; lower uncommitted ingress commit и rollback | Fence/A11 |
| `unknown_conversation_and_duplicate_first` ×обаproducers | До создания Conversation несколько Inbox; PROCESS blocked connection; Resume404 до существования; позже Resume, post-Resume duplicate обрабатывается первым; earliest/legacy/conflicting origin не получает новую authority | Fence/A11 |
| `generation_group_boundary_and_late_media` | old HUMAN/AI/NULL Turn + new generation input, old out-of-order input, photo READY/FAILED после Resume; no cross-generation membership/deadline reset, immutable captured tuple | A01/A02/fenceA03 |
| `test_consumer_stale_after_control` | Pure consumer snapshot → Takeover/Resume → finalize: same revision STALE, superseded revision SUPERSEDED; old committed OBSERVED/token replay byte-identical, no external call/new backlog job | control-частьA03; не полныйA05 |
| `control_lock_graph_and_maintenance` | Реальные ingest/process/file/manual/owner/consumer/expired job races, PREPARED uploads, open outer savepoint; blockedA не лишает B progress; прежние age boundary/100+ cursor/2s/5s tests сохраняются | A02/A11/reliability |
| `control_capability_and_audit` | Runtime direct SELECT/DML/sequence/private helper rejected; forged GUC/task/XID/actor/ws/key; FK same-client/generation/Audit substitution; mixed old/new Audit API/frontend и exact decimal>2^53 | A07/A11 |
| `control_receipt_audit_actor_fk` | Raw PG: одинаковые ws/Audit/Conversation/gen/event/context, **другой валидный member actor** в receipt; прочие constraints удовлетворены, отказ23503 именно conversation_control_receipts_audit_fk, без partial transition | C2-M3-CONTROL-01/A07 |
| `control_receipt_audit_context_fk` | Отдельный raw PG case: тот же actor и остальные keys, **иной locally valid saved context** receipt относительно Audit.object_version; coherent request/result, отказ23503 того же FK, rollback всех writes | C2-M3-CONTROL-01/A07 |
| Existing exact function inventory | Весь pg_proc app/platform = прежние profiles + ровно8§12.7; каждый owner/search_path/PUBLIC/security/runtime EXECUTE проверен, private вызов runtime отвергнут | C1-M3-CONTROL-02/security |
| `control_migration_preservation` | populatedT/M2 seed + clean0008→9→8 definitions/grants; old pending Inbox/Turn/consumer/manual/UNKNOWN/private image, each new-data downgrade blocker; no backfill/jobs/receipt rewrite | A11 |
| `control_schema_commit_loss_normal_docker29` | Два actual state shards§12.8: separate exit86 after commit, fresh reader, incompatible runtime rejected, exact source/image forward/restart, pending/UNKNOWN/privateS3 and original receipts retained | A11/source-schema |
| `control_schema_budget_and_failure_retention` | Реальные stage timings: весь frozenT shell + все schema prepare/verify ≤600s, C только remaining; invalid/exhausted handoff отказ, bounded process-group stop/owned cleanup и reports при source/build/probe failure до runtime try; T reports до worktree removal, state≤25min/foundation≤35min/all9 gates | CONTROL-COMPAT-01 implementation condition |
| Existing direct wire/real relay/browser | Same production transport: accepted wire effect + lost response → restart UNKNOWN, count1; HTTP без business transaction;6+6, auth/private signed GET/Secure cookies/browser regression неизменны | Сохранность M2/TURNS, не новый live evidence |

Fixtures используют настоящий command/worker path, deterministic barriers и
наблюдаемые DB locks, не вероятностный sleep/retry. Fault injection остаётся в
TEST, не runtime toggle. Temporal cases удерживают только Conversation NO KEY UPDATE
в независимом blocker transaction; он **не меняет** context/generation/billing.
Подтвердить ожидающий PID/pg_locks до границы и освобождение после неё; ожидание
укладывается в прежние DB2/5s, без backdating или увеличения timeout. Для expiry
начало command transaction ещё активно, post-lock clock уже за effective_until;
для activation начало раньше effective_from, post-lock clock уже внутри interval.
Проверить также before/at границы: начало включительно, конец исключительно.
Subscription и service mode параметризуются независимо; прочие product/channel
условия valid. Для TELEGRAM refresh закончен до final wait и HTTP вне transaction;
CONTROLLED идёт через public HTTP service, не internal kernel. Отдельные replay и
revocation/policy cases подтверждают прежний порядок, отказ и отсутствие writes;
replay не обращается к новой snapshot projection.

Два FK negatives выполняются отдельно с привилегированной TEST fixture после
проверки всех локальных CHECKs и прочих refs: оба actor состоят в нужном Workspace,
оба context положительны; в context case receipt expected/result/context согласованы
между собой, отличается только Audit.object_version. Иначе unrelated constraint
не докажет finding. Проверять SQLSTATE23503 **и имя** нового FK, сохранность исходного
control state и отсутствие частичного receipt/Audit/transition после rollback,
включая fault/deferred failure позже valid insert. Production positive atomic
command и exact replay обязаны оставаться valid. Это план actual PG, не выполненный
exploit или новое runtime evidence.

Любую адаптацию старого теста объяснять отдельно: новый
manual законно меняет generation; новый head/inventory9 не меняет смысл historical
8/7 tests; teardown идёт по новым FK; expected semantic outcomes и time limits не
ослабляются. Не добавлять skip/xfail, фильтрацию очереди, backdating deadlines,
fake success SQL, mocks вместо PG/S3/wire или rerun-to-green.

CONTROL покрывает A07 и перечисленные context/fence/A11 части. Полные A04–A06
(automated admission/stale effect-producing worker/реальный in-flight после control),
native частьA08, EscalationA09, ConsoleA10 и итоговыйA12 остаются отдельными gates.
Сохранённый M2 UNKNOWN wire test не объявляется новым GUARDS PASS. Новый contract
или зелёный docs CI не доказывают ни один будущий CONTROL runtime case.

### 12.12. Решения для согласования и возврат

Один finished R1 передаётся C0 для точечного re-review C1/C2 на exact head. Ниже
отражена [выдача C0 R1](https://github.com/Elefesys/ai-service-manager/pull/27#issuecomment-6100251718),
а не отдельный реестр статусов. Три finding **OPEN до verdict C0**; авторский статус
исправлений — FIXED FOR REVIEW:

| Finding / P2 | Исправление R1 и будущая проверка |
|---|---|
| C1-M3-CONTROL-01 | §§12.3/12.5/12.7/12.10/12.11: отдельный single-statement POST_LOCK_PRODUCT_SNAPSHOT с MATERIALIZED clock_timestamp, guarded method и final Resume/public manual callers; expiry **и activation** на подтверждённом lock wait, unchanged R4 GET |
| C1-M3-CONTROL-02 | §§12.7/12.10/12.11: добавлен exact inventory path, восемь однозначных security profiles, полный pg_proc query и exact equality со всеми прежними profiles |
| C2-M3-CONTROL-01 | §§12.4/12.7/12.11: seven-column Audit UNIQUE/receipt FK связывает saved actor/context; два самостоятельных raw constraint negatives с valid прочими constraints, positive atomic/replay и rollback |

Решения C0 по design acceptance points:

- **CONTROL-POLICY-01 / OPEN** до clock-path re-review. Сам выбор existing
  `messaging.manual_send` как консервативного availability gate Resume **согласован**;
  Takeover/read не зависят от billing/channel, Resume требует active Business/
  connection, но не can_reply/window/refresh. Это не AI-send permission.
- **CONTROL-DB-01 / OPEN** до receipt-binding re-review. Сохраняются origin до
  sequence, legacy generation1/NULL без backfill, lock graph и immutable result;
  R1 усиливает только selected Audit key без generic consistency helper.
- **CONTROL-AUDIT-01 / ACCEPTED, CLOSED в C1 API/DTO/UI compatibility design scope**:
  два typed variants/parser/label и единственный MESSAGE_SEND_REQUESTED для manual.
  Этот PASS **не закрывает** независимый DB finding C2.
- **CONTROL-COMPAT-01 / ACCEPTED, CLOSED в C6 design scope на cf043901**. Matrix
  frozen P/O/H0007 → detached T0008 retained7→8 → futureC0009 new8→9 сохранена.
  §§12.8/12.11 конкретизируют принятый conservative whole-T/remaining600 protocol,
  full34 inventory/33 forward data tables, bounded cleanup/failure reports.
  Actual timings prepare≤600s/state≤25min/foundation≤35min и all9 gates ещё
  **PLANNED**. Нынешний docs head не является C/9; runtime укладываемость не PASS.

C0 сверяет эти уточнения; substantive source/phase/guard/budget delta требует
адресного C6 review до реализации. R1 сохраняет семантику принятого compatibility
design; helper budget implementation, pins/workflows/timeouts сейчас не меняются.
В receipt R1 обязательны exact head/parent/tree, diff от cf043901, whole-file hashes
и immutable77343-byte prefix proof, actual document checks и **новый** automatic
CI run/attempt/event head/tested merge/parents/tree/status. Старый CI38067015295
проверяет cf043901, не эту R1. Docs CI не доказывает будущие CONTROL/0009 cases.

Это не reopened TURNS/M2 findings и не новые задания пользователю. Native
account/provenance остаётся отдельно NOT VERIFIED; GUARDS/UI отдельно. Никакого
аккаунта, token, TEST продления или VM действия сейчас не требуется. После
re-reviews C0 принимает или корректирует§12 и выдаёт implementation **в этом PR**
с exact paths/резервом0009→0008. До этого запрещены runtime/DDL/tests/OpenAPI/
frontend/infra edits. Следующие C8/приёмка/merge/main CI не подменяются авторским
review или документом.

## 13. M3.1-GUARDS — предложение минимальной границы исполнения

Дата: 2026-10-12. **CONTRACT PROPOSAL / REVIEW, не разрешение реализации.**
Основание — [выдача C0](https://github.com/Elefesys/ai-service-manager/pull/27#issuecomment-6119082701)
и активный [M3_HANDOFF §0](M3_HANDOFF.md). Accepted implementation:
`c6a55b6b17d1c1ab286ce97dfa4bd27197141fe5`, schema0009. Preparation parent этой
работы: `67326f7e2e0865e1b84f5e4fc7c67d5044e48ba7`. §§1–12 сохранены byte-for-byte;
исторические OPEN там не заменяют текущий [реестр](../TASK_REGISTER.md).
Сейчас изменяется только этот файл; revision следующей миграции не назначена.
R1 по [решению C0](https://github.com/Elefesys/ai-service-manager/pull/28#issuecomment-6121132463)
продолжает head `d4f9bdec7ec801e61165e142b16e98f6d2322e0b`: разрешена адресная
правка существующего §13. C1/C2 reviews приняты, две TEST policy LOCKED;
общий contract и implementation ещё не приняты, findings остаются OPEN (§13.10).

Прочитаны actual0005/0006/0007/0008/0009, `OwnerControlService`, `Worker`,
`MessagingDatabase`/`WorkerUnitOfWork`, `TurnSnapshot`/`consume`, manual commands,
results/policy и соответствующие tests. Канонические основания: Spec
§§5.1–5.14,18.5–18.8,18.14,25.7; ADR024–026/121–128/180/197–198/217/267;
MVP GJ-G/GJ-J; Roadmap M3; Implementation Plan M3.1; IMPL-001.
Оригиналы из SOURCE_MANIFEST сверены с предоставленными файлами. Это дополнение
не переопределяет M4, AI tools, модель Escalation или product billing.

### 13.1. Один исполняемый срез и явно предлагаемые изменения

Срез проверяет цепочку fresh controlled ingress → READY Turn → guarded consumer
→ атомарный text intent → отдельный send Job → existing controlled adapter.
Вместо LLM — детерминированный `CONTROLLED_GUARDS_V1`, результат которого ровно
`CONTROLLED GUARDS TEST` (без завершающего LF). Он работает через штатные
`Worker.execute/run_once/run`, PostgreSQL claim и Outbox, а не через отдельно
вызываемую тестом функцию admission. `TURN_TEST_V1` остаётся effects-free.

Для этого среза C0 зафиксировал следующие ограниченные policy относительно
принятого CONTROL (GUARDS-POLICY-01/02, §13.10):

1. **Новый Resume в LOCAL/TEST для CONTROLLED** сохраняет внутренний профиль
   `CONTROLLED_GUARDS_V1` в своём receipt. Старые receipts получают NULL, без
   backfill. Replay Resume возвращает прежний результат и профиль не добавляет.
   Telegram Resume по-прежнему не включает автоматический consumer. Сам Resume
   не создаёт Jobs; только последующий fresh ingress может привести к новому шагу.
   Это явное расширение внутренней семантики CONTROL, принятое C0 только для
   LOCAL/TEST + CONTROLLED среза.
2. Допуск этого TEST-профиля требует **live OWNER, принявшего соответствующий
   Resume**, active Workspace/Business/Connection и текущей product availability
   по existing `messaging.manual_send`. Последняя — лишь availability check;
   permission на автоматический эффект задаёт отдельный доверенный GUARDS path.
   Это не предоставление manual capability LLM и не entitlement для production AI.
   Отзыв выбранного OWNER до допуска блокирует работу; наличие другого OWNER
   автоматически её не перепоручает. Для нового допуска нужен новый Resume.
3. **Не более одного принятого automated text intent на Turn**, независимо от
   последующих revision. Новый material context может подавить ещё не начатую
   отправку, но не создаёт автоматически замену уже принятого intent. Следующий
   fresh Turn имеет свой ключ. C0 принял one-per-Turn для deterministic TEST
   consumer; общая production AI/M4 replacement policy этим не определяется.

Исполнение этих policy требует принятия всего §13 и отдельной выдачи implementation.
Профиль ограничен одновременно
server environment LOCAL/TEST, разрешённой LOCAL/TEST БД и canonical provider
CONTROLLED; Python и SQL проверяют это независимо. Пользовательский JSON, GUC,
job payload, произвольный connection UUID и флаг `origin` профиль не назначают.
Секреты, внешние AI/Telegram sends и новый endpoint для активации не нужны.

### 13.2. Происхождение, идентичность и доказательство актуальности

| Поле / источник | Правило |
|---|---|
| `OWNER_MANUAL` | Только существующий owner command и `SEND_MANUAL_TEXT`; прежние live session/OWNER, fingerprint, receipt и `MESSAGE_SEND_REQUESTED` неизменны |
| `AUTOMATED` | Только новый `PROCESS_TURN/GUARDED_TEXT` и создаваемый им `SEND_GUARDED_TEXT`; тип определяется SQL command path и сохранённым Job/Outbox, не входным flag |
| Workspace/Connection | `messaging_admit(job_id, claim_token)` читает canonical Job; переданные в Python claim остальные refs не авторитетны |
| Conversation/Client/Business/chat | Читаются через canonical Turn → Conversation → Connection; exact relation во Workspace обязательна, same-workspace чужой Client также отвергается |
| Turn revision / input context | Existing `conversation_turns.revision` и `conversations.version`; отдельно сохранены в DB input, сравниваются на result admission |
| Generation/fence | Existing captured Turn/Inbox tuple и current Conversation tuple; private `conversation_turn_activation_matches` плюс exact сохранённый Resume receipt с этим поколением и TEST-профилем |
| Claim | Existing Job/token/lease, task/XID/physical transaction guards; claim проверяется снова после lock waits, а не только при входе в UoW |
| Origin members | Все existing Turn members имеют earliest committed Inbox origin с AI, exact generation/fence и ingress sequence строго больше fence |
| Intent context | Новое поле receipt: версия Conversation **после** собственного outbound Message insert; используется для dispatch, а не версия до этого insert |

Legacy NULL, HUMAN-captured Turn, pre-fence ingress, дубликат с более ранним origin
и Turn прежнего поколения не получают authority от текущего AI. Дополнительный
NULL-профиль старого Resume исключает автоматизацию уже имеющегося AI backlog
при upgrade. Новый Resume меняет generation/fence штатным образом; поэтому и
старый AI backlog не становится разрешённым после нового Resume. Scan/backfill,
reprocess IGNORED, восстановление полномочий из old OBSERVED receipt отсутствуют.

DB сохраняет отдельный `GuardedTurnSnapshot` в existing `messaging_jobs.turn_input`:
existing TurnSnapshot + canonical conversation/client/business refs,
`activation_fence_seq`, `resume_receipt_id`, consumer literal. Это отдельный private
DTO; форма TurnSnapshot, TURN_TEST_V1 и старых consumer receipts не меняется.
Digest вычисляет DB по своему canonical input. Чужой snapshot digest, подмена
client/turn/revision и результат от другого claim не могут создать intent.

Intent namespace — `GUARDED_TEXT_V1`, ключ `(workspace_id, turn_id)`; случайный
Message/Outbox UUID не является idempotency key. Winning revision сохраняется.
DB-authoritative request fingerprint:
`sha256(UTF8('asm:m3:guarded_text:v1\n' || canonical_input::text || '\n' || exact_text))`,
где `canonical_input` — сохранённый DB jsonb, а не заново сериализованный Python
payload. Text — ровно полученные Unicode bytes после UTF-8 encoding, без trim,
нормализации или подстановки; существующие M2 пределы 4096 chars/16384 bytes,
non-empty TEXT. Claim token не входит в business fingerprint, но отдельно
связывает winning receipt и terminal replay. Другой body для того же сохранённого
результата даёт `IDEMPOTENCY_KEY_CONFLICT`, а не второе Message.

### 13.3. Scheduling и реальные callable границы

`turn_enqueue` сохраняет GROUP/MEDIA/TEST_CONSUME без изменения их назначения.
Когда Turn READY, добавляет ровно один `PROCESS_TURN/GUARDED_TEXT` на revision
только при matching activation и новом controlled Resume profile. Existing
`UNIQUE(workspace_id,turn_id,turn_revision,step)` обеспечивает дедупликацию.
Поздний file terminal может создать шаг новой revision; если intent этого Turn
уже принят, шаг заканчивается `ALREADY_ACCEPTED` со ссылкой на него без consumer,
нового receipt/Message/Outbox/send Job. Нет переоткрытия старого intent.
Производитель только планирует по activation/profile; это не окончательный
permission check. `turn_enqueue` не получает authority/billing locks из material
hook: эта цепочка принадлежит последующему guarded admission.

Предлагаемый private Python ABI в `MessagingDatabase`:

| Метод | Результат и commit boundary |
|---|---|
| `prepare_guarded_turn(claim)` | Отдельная короткая transaction; canonical input либо terminal progress; снимок выдаётся после commit |
| `accept_guarded_text(claim, snapshot_digest, text)` | Reconciliation saved result, затем новая admitted transaction; возвращает committed `GuardReceipt`, никогда SendPermit |
| `replay_guarded_text(job_id, winning_token, snapshot_digest, text)` | Только чтение canonical committed receipt/terminal result; не обновляет lease, generation или authority |
| `begin_guarded_send(claim)` | Самостоятельный final admission; `SendPermit` появляется только после durable DISPATCHING commit |

`Worker.execute` маршрутизирует новый Turn step к `prepare_guarded_turn`, затем
вычисляет constant text вне UoW и вызывает `accept_guarded_text`. Send Job проходит
`begin_guarded_send`, затем existing bounded adapter call и existing finalize.
Ни LLM, ни HTTP, ни ожидание controlled transport не держат business transaction.
Никакой worker не конструирует `AuthenticatedAccount`/TenantContext за OWNER:
saved Resume actor проверяется private DB authority helper, worker admission
остаётся отдельным от user-only context. `messaging.policy.Permission.SEND`
по-прежнему owner permission, не новый automated enum с тем же смыслом.

Подключение будущего trusted caller требует отдельной выдачи C0: конкретный
серверный producer/consumer version, product permission и разрешённый provider,
принятые C1/C2 contracts и интеграционные tests того же admission/dispatch path.
Нельзя подключить его параметром environment, свободным callback из HTTP,
подменой consumer literal или расширением provider enum только в DTO. AIRun,
ModelGateway, prompts, M6–M9 commands и generic action registry здесь отсутствуют.

### 13.4. Transactions, locks и проверки после ожиданий

Все новые mutating capabilities: READ COMMITTED, existing transaction/task/XID
guards, lock_timeout2s/statement_timeout5s; lease30s и retry horizon не меняются.
Основная сериализация — `Conversation FOR NO KEY UPDATE`, та же, что у CONTROL,
manual acceptance, ingress capture и material hooks. Одна conversation на unit.

| Callable | Порядок locks после canonical worker admission |
|---|---|
| prepare / accept guarded result | Собственный Job UPDATE → Workspace/User/Membership SHARE выбранного Resume actor → Business SHARE → Connection SHARE → billing rows в existing порядке → Conversation NO KEY UPDATE → свой Turn NO KEY UPDATE |
| begin guarded send | Собственный Job UPDATE → свой Outbox UPDATE → та же authority/Business/Connection/billing цепочка → Conversation NO KEY UPDATE → свой Turn NO KEY UPDATE |
| finish/recover guarded send | Existing Job → Outbox → Conversation; после DISPATCHING не получает owner/product/control authority повторно |
| claim/exhaustion/recovery scan | Existing single candidate transaction и NOWAIT/savepoint preflight; новый send kind использует send branch, не Turn branch |

Resume receipt immutable: его refs можно предварительно прочитать, но relation,
profile и live authority подтверждаются под указанными locks. Receipt FK к
Membership и Conversation добавляет KEY SHARE; новые Message/Outbox/Job FK также
берут KEY SHARE на своих parents. Conversation NO KEY UPDATE совместим с этим
FK mode. Принимающая transaction не блокирует существующие send Jobs/Outboxes
после Conversation; создаёт только собственные новые rows. CONTROL не захватывает
existing Jobs/Outbox. Старый порядок Inbox/file → connection/conversation/Turn
сохраняется; GUARDS не захватывает existing Inbox/file после Conversation.
Billing: account → mode → subscriptions/revisions/plans/entitlements, как0007/0009.
Новый accepted receipt ссылается на уже locked Turn/Conversation и immutable
Resume; implicit edges включаются в C2 review, а не прячутся за advisory lock.

**После последнего ожидания**, непосредственно перед изменением, новая DB clock
и canonical rows подтверждают одновременно:

- live Job/token/kind/step/lease, exact refs; Turn READY и exact revision;
- live выбранный OWNER/Workspace, active Business/Connection, TEST/CONTROLLED
  profile; current AI + exact generation/fence + все origin members;
- current context равен input context (accept) либо intent context (begin send);
- product availability посредством existing DB-authoritative billing check,
  включая activation/expiry interval по post-wait clock; Python decision сама
  по себе не authority. Structural billing error — existing bounded UNAVAILABLE,
  действительный отказ — NOT_ALLOWED, без нового эффекта.

Locks защищают state от конкурентного изменения до commit; clock-dependent
условия повторяются после waits даже при ранее успешном prepare. Boundary
подписки: `from <= db_now < until`; equality на expiry отказывает. Revocation,
product/channel change, начавшийся после полученных SHARE locks, сериализуется
после commit допуска. Нельзя объявлять его уже победившим отзывом.

В этом срезе channel gate допускает только CONTROLLED, для которого нет Telegram
rights/window. `TELEGRAM` отказывает **до** probe/dispatch, даже при AI и valid
claim. Existing manual Telegram path сохраняет generation + observation-version
CAS, rights refresh вне transaction, post-wait права и строгий
`db_now < last_client_inbound_at + 24h`. Будущий automated Telegram caller обязан
встроить этот probe/CAS/window в **тот же final guarded admission**; отдельное
успешное чтение прав либо Resume не заменяет такую проверку. Сейчас эта будущая
ветвь не реализуется и не объявляется проверенной.

На accept saved exact result replay проверяется прежде live claim; для новой
работы обязательна live claim. Authority может отказать раньше при получении
своих locks. После получения цепочки locks superseded revision имеет приоритет
над stale context/control/origin, затем проверяются product и остальные gates.
Неверный/истёкший/reclaimed token отвергается без изменения текущей работы;
terminal winning replay проверяется отдельно до требования live lease.
Если concurrent finalizer commit завершился во время admission wait, выполняется
existing canonical re-read с теми же winning token/digest/text, без нового permit.
STALE/SUPERSEDED/NOT_ALLOWED допускают только собственный terminal Job и receipt
результата; **нет domain mutation**, нового Message/Outbox/Audit или follow-up Job.
ALREADY_ACCEPTED завершает только текущий шаг и возвращает прежнюю идентичность.
Replay не создаёт ни одной row и не делает старый результат исполнимым заново.
Prepare без ещё сохранённого input может завершить только свой Job с progress,
без result receipt; потеря его ACK сама по себе не разрешает computation/send
повторно. Committed terminal Job даёт STALE_CLAIM; после rollback возможен только
existing bounded retry/reclaim с повторным live admission.
Exhaustion нового GUARDS step завершает только этот Job, не переводит уже READY
Turn в FAILED. Старые GROUP/MEDIA/TEST_CONSUME exhaustion rules сохраняются.

Acceptance одной transaction создаёт immutable result receipt + OUTBOUND TEXT
Message + PENDING Outbox `SEND_GUARDED_TEXT` + один send Job, затем terminalizes
consumer Job. Ошибка любого write, включая последний consumer Job terminal
UPDATE, или commit откатывает всё. Existing
`turn_manual_material` на деле обрабатывает **любой** OUTBOUND Message: его
однократный context+1 сохраняется и для automated Message. После insert читается
и сохраняется `intent_context_version=input_context_version+1`; generation не
меняется, `conversation_manual_takeover` из manual command здесь не вызывается.
Другие новые material facts после этого invalidate pending dispatch.

### 13.5. Dispatch, in-flight и восстановление

Guarded result acceptance не разрешает adapter call. Final `begin_guarded_send`
повторяет §13.4 и атомарно сохраняет existing `attempt_id`, DISPATCHING и winning
claim до выдачи permit. **Durable commit DISPATCHING — linearization point**:

| Порядок | Обязательный результат |
|---|---|
| Takeover/manual acceptance победил до result admission | STALE, без intent и вызова adapter |
| Intent принят, Takeover/new context победил до dispatch | Outbox FAILED с existing `NOT_ALLOWED`, Job DEAD; private причина STALE/SUPERSEDED/NOT_ALLOWED; новый attempt/CALL не начинается. До первого begin CALL=0; при повторном begin счётчик прежних calls не увеличивается |
| DISPATCHING commit победил, затем Takeover, в том числе до фактического I/O | Permit может быть использован один раз исходным worker; mode switch не доказывает отмену. Финальный outcome принимается независимо от нового поколения |
| Успех / definite non-retryable failure | Existing Outbox SENT/FAILED и Job SUCCEEDED/DEAD; terminal material hook context+1 ровно один раз |
| Proven NOT_SENT, retryable | Existing PENDING/READY, прежние backoff/5 claims/15min; **каждый** новый begin снова проверяет GUARDS, поэтому Takeover пресекает retry |
| Возможный effect, timeout/cancellation/response loss | UNKNOWN/DEAD; не CANCELLED, не READY, без второго вызова |
| Dispatch commit потерял ACK | Нет полученного permit — worker не делает I/O. При состоявшемся commit/start_after_commit — recovery UNKNOWN/CALL=0; DISPATCHING не выдаёт новый permit. Если canonical read доказал rollback/PENDING, разрешён только обычный retry/reclaim с новым guarded admission |
| Finalize commit потерял ACK | Canonical exact attempt/claim/outcome replay до live lease checks; сохранённый SENT не понижается в UNKNOWN |

Отдельного automated retry engine нет. `messaging_finish_send`, reschedule,
recovery и terminal preflight расширяются ровно на новый typed send kind.
При отказе повторного begin после proven NOT_SENT прежний `attempt_id` может
оставаться: запрещён новый attempt/transport, а не наличие уже сохранённого ID.
Сохраняются last_attempt/last_claim/last_outcome, late SUCCESS после уже записанного
UNKNOWN отвергается, restart не исполняет DISPATCHING повторно. При stale pending
intent private rejection фиксируется в одном новом nullable Job поле
`guard_rejection` (STALE/SUPERSEDED/NOT_ALLOWED); existing публичные error/status
enums не расширяются. Outbox FAILED сам является terminal material fact и потому
даёт existing context+1; это не применение stale consumer result.

Для будущего Console достаточно origin, Turn/revision, accepted generation,
input/intent context, intent/attempt IDs и truthful delivery status из сохранённых
rows. Не обещать отмену in-flight после Takeover. Public DTO/history/delivery fields
не меняются; новая UI-функция или CONTROL screen/buttons здесь не появляются.
Существующие `manual_delivery.has_dispatching/has_unknown` должны фильтровать
`kind='SEND_MANUAL_TEXT'`: сейчас SQL считает все Outbox, что было эквивалентно
manual-only схеме. Это необходимая compatibility correction при втором kind;
нельзя молча показать automated pending как ручную отправку.
Existing history SQL возвращает OUTBOUND любого Outbox kind; MessageResponse
не содержит origin, а `MessagingPanel` сейчас подписывает все такие rows как
«Ручной ответ». В будущей implementation эта единственная подпись заменяется
на нейтральную **«Исходящее»** для любого OUTBOUND. Manual и automated rows не
скрываются, их PENDING/DISPATCHING/SENT/FAILED/UNKNOWN остаются честными;
existing manual composer и receipt recovery сохраняются. Это узкая compatibility
правка двух frontend paths (§13.9), не новый origin DTO/API/OpenAPI или экран.

### 13.6. Минимальная schema и security profiles — proposal C2

Нужна **одна новая migration после0009**, номер/filename назначают C0/C2 до кода.
Рекомендация C2 — `0010_conversation_guards.py`, revision0010/down_revision0009;
это **не резерв номера и не разрешение DDL**. C0 назначит их вместе с implementation.
Причина: текущие Outbox/Jobs CHECK и command receipts разрешают только manual
send; записать automated intent в них как manual означало бы выдумать owner
команду и `MESSAGE_SEND_REQUESTED`. Applied0001–0009 не редактируются.

| Объект | Точная необходимая дельта / назначение |
|---|---|
| `platform.conversation_control_receipts` | Nullable immutable `guard_profile`, только NULL или `CONTROLLED_GUARDS_V1` и только RESUME/AI; заполняется при новом CONTROLLED Resume (§13.1). Composite UNIQUE для FK нового receipt на `(workspace_id,id,conversation_id,client_id,accepted_generation)`; прежние fingerprint/result/Audit constraints неизменны |
| `platform.messaging_jobs` | Новый kind `SEND_GUARDED_TEXT` с тем же outbox-only shape, что manual; новый Turn step `GUARDED_TEXT`; turn_input разрешён только двум consumer steps. Turn outcomes дополнены ACCEPTED/NOT_ALLOWED/ALREADY_ACCEPTED. `guard_rejection` nullable, closed enum и только для terminal rejected guarded send. Existing lease/retry/attempt поля используются без новых часов/счётчиков |
| `app.outbox_events` | CHECK kind дополнен `SEND_GUARDED_TEXT`; shape, Message FK, unique message, immutable identity, states/attempt/error constraints сохранены |
| `platform.turn_guard_receipts` | Единственная новая private table: fields ниже; immutable результат и единственная accepted action identity, без AIRun/action registry |

Новая table хранит `workspace_id`, `job_id`, `winning_claim_token`,
`connection_id`, `conversation_id`, `client_id`, `turn_id`, `turn_revision`,
`resume_receipt_id`, `input_control_generation`, `activation_fence_seq`,
`input_context_version`, `snapshot_digest`, consumer literal,
`request_fingerprint`, `result_text`, `outcome`, `accepted_at`, nullable
`intent_context_version/message_id/outbox_id/send_job_id`. Outcome —
ACCEPTED/STALE/SUPERSEDED/NOT_ALLOWED; last four refs/version non-NULL ровно для
ACCEPTED, для остальных outcomes все четыре NULL; intent context = input context+1
с проверкой bigint overflow. Result text нужен для exact replay
и DB fingerprint, не является второй mutable копией Message.

PK `(workspace_id,job_id)`; partial UNIQUE `(workspace_id,turn_id)` WHERE
outcome=ACCEPTED. UNIQUE `(workspace_id,outbox_id)` в receipt вместе с existing
one-Outbox-per-Message/one-send-Job-per-Outbox обеспечивает уникальность accepted
Message/Outbox/send Job; отдельные дубли этих UNIQUE и новый action UUID не нужны.
Captured revision связывается с immutable consumer Job. FK не ссылаются на
mutable current Turn revision либо Conversation context/generation как замену
admission; актуальность проверяется по §13.4.

Точная relation chain (`ws` = `workspace_id`, constants — non-NULL literals):

| Связь | Columns / supporting parent key |
|---|---|
| Receipt → consumer Job | `(ws,job_id,connection_id,PROCESS_TURN,turn_id,turn_revision,GUARDED_TEXT)` → existing `messaging_jobs_turn_receipt_key` |
| Receipt → Turn | `(ws,turn_id,connection_id,conversation_id)` → existing four-column Turn UNIQUE |
| Receipt → Conversation/Client | `(ws,conversation_id,client_id)` → existing `conversations_control_client_key` |
| Receipt → Resume | `(ws,resume_receipt_id,conversation_id,client_id,input_control_generation)` → proposed five-column Resume UNIQUE выше; operation/profile/fence подтверждает trusted insert/current helper |
| Receipt → Message | `(ws,message_id,connection_id,conversation_id,OUTBOUND,TEXT)` → existing `messages_file_source_key` из0006 |
| Receipt → Outbox | `(ws,outbox_id,message_id)` → existing Outbox UNIQUE; connection связан через typed Message/Outbox FK |
| Receipt → send Job | `(ws,send_job_id,outbox_id,SEND_GUARDED_TEXT)` → **новый** supporting Job UNIQUE `(workspace_id,id,outbox_id,kind)` |
| Send Job → Outbox kind | `(ws,outbox_id,connection_id,kind)` → **новый** supporting Outbox UNIQUE `(workspace_id,id,connection_id,kind)`; typed FK требует совпадающий manual/guarded kind, независимых CHECK двух rows недостаточно |

Existing parent keys переиспользуются, не дублируются. Common refs NOT NULL;
нужные constants — GENERATED либо checked non-NULL literals, nullable CHECK —
явные IS NULL/IS NOT NULL/IS TRUE. Insert capability дополнительно сравнивает
DB input, fence/profile и exact Message text. Все receipt fields immutable;
для full-row UPDATE protection используется existing `turn_immutable()`, без
нового trigger helper. RLS/constraints не заменяются наличием workspace UUID.

Runtime не имеет прямых SELECT/DML новой table; owner asm_migrator, ENABLE/FORCE
RLS и только migrator policy. Proposed inventory: 36 таблиц вместо35, exact set
старых35 + `platform.turn_guard_receipts`, не проверка одним count.
Origin Message хранится через его единственный typed Outbox и guard receipt:
`SEND_MANUAL_TEXT` → OWNER_MANUAL, `SEND_GUARDED_TEXT` → AUTOMATED. Новое поле
Message origin и backfill всей истории для этого доказательства не нужны.

| Новый SQL профиль (schema `platform`) | SECURITY / EXECUTE |
|---|---|
| `guard_turn_prepare(uuid,uuid)` | DEFINER, asm_migrator; asm_runtime EXECUTE, внутри mandatory worker admission |
| `guard_turn_accept(uuid,uuid,text,text)` | DEFINER, asm_migrator; asm_runtime EXECUTE; digest/text, без произвольных entity refs |
| `guard_turn_replay(uuid,uuid,text,text)` | DEFINER, asm_migrator; asm_runtime EXECUTE; single-statement exact terminal read |
| `guard_send_begin(uuid,uuid)` | DEFINER, asm_migrator; asm_runtime EXECUTE; новый kind only |
| `guard_require_current(uuid,uuid,uuid,bigint)` | DEFINER, asm_migrator; private, no runtime EXECUTE; canonical workspace/Turn/Resume/expected context, checks only under caller locks |
| `guard_text_fingerprint(jsonb,text)` | INVOKER, IMMUTABLE STRICT; private, no runtime EXECUTE; codec§13.2 |

У всех шести `search_path=pg_catalog,pg_temp`, PUBLIC EXECUTE revoked; no GUC
как authority, no dynamic user SQL. Existing function signatures/security modes
сохраняются. Изменяются определения только перечисленных caller families:
CONTROL execute (profile)/read (manual filter), `turn_enqueue`, exact claim/admit
parsing, `messaging_retry`, send finish/reschedule, relevant legacy и scan
entrypoints `messaging_claim`/`messaging_recover_expired`, `turn_preflight`/exhaustion.
В claim/retry/finish/reschedule/recover/preflight новый `SEND_GUARDED_TEXT` явно
входит в send branch, а не PROCESS_TURN fallback; GUARDS exhaustion завершает
только Job (§13.4).

**Отдельный обязательный replacement тела existing
`platform.turn_execute(uuid,uuid)` в новой migration:** сразу после canonical
Job guard разрешены только GROUP/MEDIA/TEST_CONSUME. Для GUARDED_TEXT — existing
`INVALID_INPUT` (SQLSTATE P2001) **до** preflight/supersede/seal/terminal mutation,
в том числе после Takeover. Одного нового Worker router недостаточно: legacy SQL
capability остаётся runtime-executable. Signature, SECURITY/grants, старые
outcomes и TEST_CONSUME codec/result сохраняются; applied0008 не редактируется.
Это замена existing body, не седьмая новая функция.

Exact pg_proc inventory tests сравнивают все прежние profiles плюс эти шесть;
новый helper или grant вне этого списка требует C2/C0 согласования.

Strict private DTOs: `GuardedTurnSnapshot`, `GuardTextResult` (consumer/digest/text),
`GuardReceipt` (outcome/refs/versions/fingerprint), `GuardProgress`
(SUPERSEDED/STALE/NOT_ALLOWED/ALREADY_ACCEPTED). Existing JobClaim kind и
TurnJobClaim step расширяются; старые формы parse identically. SendPermit и
FinalizeResult reuse, новые public DTO/status/error/Audit variants отсутствуют.
`MESSAGE_SEND_REQUESTED` остаётся manual USER_ACCOUNT event. В данном controlled
proof automated acceptance наблюдаема через private receipt/Job, без фиктивного
Audit от OWNER. Production automated Audit policy — часть отдельного допуска
будущего caller, не молчаливое разрешение отсутствия Audit для M4.

### 13.7. Upgrade, refusal и точная совместимость

Предлагаемый cutover — existing drained LOCAL/TEST source/schema discipline.
Миграция сохраняет все35 существующих таблиц/rows, receipts, pending manual,
UNKNOWN, files и TURNS/CONTROL metadata; старым Resume добавляется только NULL
profile. Не меняет mode/generation/context/sequence, не создаёт Jobs, не запускает
retained Inbox/ignored событий. Повторный upgrade head штатно no-op. Exact schema
revision readiness для API/worker/scheduler и TEST provisioning обновляется
одновременно; source0009 на новой схеме и новый source на0009 отказывают.

Downgrade в0009 разрешён только **до использования новой семантики**. Первая
проверка под migration locks отказывает до DDL при любом non-NULL guard profile,
новом kind/step, guard receipt или guard_rejection, включая terminal rows.
На неиспользованной схеме новая table пуста, добавленные поля NULL: удаляется
только дельта, восстанавливаются точные0009 function/check definitions; full
snapshot существующих35 tables до/после совпадает. Не вызывается downgrade0009,
не очищаются receipts/история и не превращаются automated rows в manual.
Forward recovery — обычный выбор подтверждённой schema, не обход refusal.

Compatibility proposal: frozen H/0007 → frozen T/0008 → frozen
**C=`c6a55b6b17d1c1ab286ce97dfa4bd27197141fe5`/0009** → future reviewed G/new revision.
Existing historical proofs остаются на своих source/schema pairs. В двух existing
state shards добавить один C→G upgrade/readiness/preservation/recovery phase;
не умножать fault families. Existing coordinator, source/image attestations,
fresh DB observation, STOP/refusal и cleanup используются как есть. Нужна
адресная C6 оценка этого конкретного source/schema phase, не переработка helper.
Historical0007 saved-plan/migration_source guard не расширяется на latest head.

Whole retained phases и новые prepare обязаны вместиться в прежний aggregate600s,
cleanup90s, state25min/foundation35min и exact Docker29 lane. Это **не измерено**
на contract head. Если дополнительный frozen C checkout/image/phase не помещается,
C3 возвращает timing evidence и узкий diff C0/C6 до изменения harness; бюджеты,
gates, source pins и assertions не ослабляются. IMPL-05 OPEN/DEFERRED сохраняется,
GUARDS не чинит journal publication/collection и не вводит новый fault framework.

### 13.8. Компактная матрица будущих доказательств

Все новые runtime строки ниже — **PLANNED**, не PASS текущего документа. Для
конкуренции использовать existing actual PG lock observation/barriers, canonical
worker methods и counted controlled adapter. Считать каждый CALL/EFFECT, без
transport dedupe. Моки не заменяют PostgreSQL, process restart или wire evidence.

| Сценарий / критерий | Actual caller / граница | Обязательный observable / tests |
|---|---|---|
| Fresh Resume + fresh controlled text, M3-A03/A04 | OwnerControlService → ingress → штатный worker/новый step → send Job | Один receipt/Message/Outbox/send Job, CALL=1/EFFECT=1; normal queue, не прямой insert send fixture; новый guards PG test |
| GUARDED_TEXT через legacy Turn capability, A03/A04 | Genuine normal-produced guarded Job/current claim через `MessagingDatabase.process_turn` и `platform.turn_execute`; повторный вариант после Takeover | INVALID_INPUT до mutation: Turn/Jobs/receipts unchanged, никакого GROUPED/seal/enqueue. Тот же claim через новый штатный guarded path даёт intended result (current AI → ACCEPTED; после Takeover → STALE); один узкий actual-PG routing case |
| Takeover до accept и отдельно до begin, A04 | Два PG connections, подтверждённый Conversation wait; owner API выигрывает commit | STALE без intent либо существующий pending→FAILED; CALL=0, нет новых Audit/Jobs; новый parametrized guards PG test |
| AI→HUMAN→AI, legacy/HUMAN/старый AI backlog, A05/A11 | Old snapshot/claim после нового Resume + свежий producer | Старые отказы, fresh origin проходит; profileNULL не запускается; reuse capture tests CONTROL + новый guards/migration test |
| Новый inbound/file terminal/manual, revised Turn, A03 | Pause consumer/dispatch, existing material callers | STALE или SUPERSEDED; own Message +1 не делает intent stale; чужой Client/Turn/ref отвергается; новый guards PG test |
| OWNER revoke, product expiry/activation, inactive channel, A04/A05 | Guard boundary после **наблюдённого** lock wait | Post-wait решение, expiry equality deny, CALL=0 при отказе; existing billing boundary fixtures, новый guards PG test |
| Expired/reclaimed claim и два worker, A05 | Normal claim/reclaim → prepare/accept/begin | Старый token без mutation, новый token допускается только при current state; concurrency same intent = один accepted result; exact terminal replay без lease/новых rows |
| Rollback и lost acceptance ACK, A03/A11 | Failure на receipt/Message/Outbox/send Job INSERT, последнем consumer Job terminal UPDATE и commit, затем fresh reader | Всё либо ничего; canonical acceptance replay; changed text conflict; собственный context+1 ровно один раз; новый guards PG test |
| Dispatch commit до Takeover и commit→I/O окно, A06 | Реальный begin, barrier перед adapter, Takeover, release | SENT/FAILED/UNKNOWN по факту, без повторного authority veto finalize; future UI refs сохраняют старое generation; новый guards PG test |
| Lost dispatch ACK / start_after_commit, A06 | Existing process test boundary после durable start, до permit/I/O; fresh reader и recovery | UNKNOWN/CALL=0, новый permit не выдаётся; guarded-kind reuse existing M2 case, отдельно от after-effect case |
| Possible effect + response loss + process restart, A06 | Existing counted controlled transport и отдельный worker process, затем scheduler/recovery | UNKNOWN, CALL=1/EFFECT=1 после restart/Takeover/Resume; новый guarded-kind вариант existing process test, не MockTransport |
| Safe NOT_SENT, exhaustion и lost finalize ACK, A06 | Existing send finish/retry/recover через новый kind | Прежние bounds; Takeover блокирует новый begin без нового attempt/CALL, старый attempt_id допустим; saved SENT не становится UNKNOWN; узкое расширение M2 kernel regression |
| HUMAN manual/inbound/file reconciliation и existing history, A04/A11 | Existing owner API/worker с mixed manual/automated Outbox; существующий `MessagingPanel` | Прежние receipts/fingerprints/Audit/UNKNOWN; manual flags считают только manual. Узкий frontend test показывает все mixed outbound rows/statuses с «Исходящее», без ложной подписи «Ручной ответ», сохраняет manual composer/receipt recovery; новые CONTROL read assertions сохранены |
| C/0009↔G, clean/repeat/populated/refusal, A11 | Actual migration role + exact source readiness/35-table projection | Old rows/receipts unchanged, NULL profile/no Jobs; used schema refuses before DDL; exact36 inventory/SQL grants; новая migration suite |

Существующее evidence, которое сохраняется, но не переименовывается в GUARDS:

- `tests/test_m3_1_control_postgres.py`: ingress/Resume capture, stale effects-free
  consumer, winning receipt replay, lock progress и client isolation;
  `tests/test_m3_1_control_api_postgres.py`: live OWNER и post-lock product,
  `test_control_read_reports_dispatching_and_unknown_without_recalling_intents`.
- `tests/test_m3_1_turns_postgres.py`: grouping, media/context revisions,
  superseded-before-exhaustion, single-candidate NOWAIT/fair scan и consumer ACK.
- `tests/test_m2_1_postgres.py`: `test_actual_process_crash_restart_durable_effect_ledger`,
  `test_lost_finalize_ack_reads_canonical_success_and_replays_exact_outcome`,
  cancellation/NOT_SENT/recovery и finish after owner revoke. Добавленный guarded
  case должен пройти normal producer/worker admission, а не скопировать raw Outbox.
  В existing process family отдельно сохраняются `start_after_commit` →
  UNKNOWN/CALL=0 и `after_effect`/response loss → UNKNOWN/CALL=1/EFFECT=1;
  это разные обязательные границы, не новая fault family/harness.
- `tests/test_m2_3_wire_postgres.py::test_real_http_accept_lost_response_process_restart_never_second_wire_call`
  остаётся отдельным actual Telegram-compatible wire/PG UNKNOWN proof. Он не
  доказывает automated Telegram admission, который здесь запрещён.

M3-A03 покрывается для уже material inbound/manual/file/delivery/control facts.
Native-owner, material edit/delete/provenance пока не реализованы: их частьA03/A08
NOT VERIFIED. ConsoleA10, EscalationA09/M3.2 и итоговыйA12 — отдельные выдачи;
нейтральная existing-history подпись не является реализацией Console CONTROL UI.

### 13.9. Один будущий план и предложенный allowlist

Ниже **запрос write scope перед implementation**, не текущее разрешение. C1/C2
reviews приняты; далее C0 проверяет точную R1 и закрытие двух findings, без
повторного полного C1/C2 review. Затем конкретный C6 source/schema compatibility
review при прежних budgets → C0 назначает revision/точные paths → один
новый migration + integrated worker path → компактные tests и retained regression
→ штатные gates на final integration SHA → независимый C8 → решение C0.

| Предлагаемые paths | Единственная причина изменения |
|---|---|
| `migrations/versions/<назначенная_revision>_conversation_guards.py` | §13.6, predecessor0009; placeholders заменить только после резерва C0/C2 |
| `backend/src/asm/conversations/guards.py` (новый) | Strict private DTOs и deterministic consumer; не общий tool framework |
| `backend/src/asm/messaging/database.py`, `backend/src/asm/messaging/worker.py`, `backend/src/asm/messaging/results.py` | Четыре typed methods, canonical step/kind parsing, normal consumer/send routing; existing attempt/finalize reuse |
| `backend/src/asm/foundation.py`, `backend/src/asm/telegram/provisioning.py` | Только exact новой schema revision readiness/provisioning; CONTROLLED wiring если требуется existing constructor, без route/env/provider changes |
| `tests/test_m3_1_guards.py`, `tests/test_m3_1_guards_postgres.py`, `tests/test_m3_1_guards_migrations.py` (новые) | Private DTO/codec; §13.8 actual command/worker/PG cases; C/0009 cycle/refusal, source/schema readiness |
| `tests/test_m2_1_postgres.py`, `tests/test_m3_1_control_postgres.py` | Только fixture cleanup в FK порядке, нормальный drain нового step, reuse process/ACK/recovery cases; исходные manual assertions сохранены |
| `tests/test_m3_1_control_api_postgres.py` | Дополнительный mixed-kind manual_delivery negative, прежняя public shape/Audit |
| `frontend/src/MessagingPanel.tsx`, `frontend/src/MessagingPanel.test.tsx` | Только OUTBOUND label «Исходящее» и узкая existing-history regression: без «Ручной ответ», mixed rows/statuses/manual composer/receipt recovery сохранены; без нового origin DTO или CONTROL UI |
| `tests/test_foundation.py`, `tests/test_m2_3_setup.py`, `tests/test_tenancy_postgres.py`, `tests/test_m2_3_schema_postgres.py` | Exact latest revision/table/function inventories и downgrade-refusal head assertions; historical0007/0008/0009 expectations остаются revision-qualified |
| `tests/test_m3_1_migrations.py`, `tests/test_m3_1_control_migrations.py` | Только latest-head fixture/cycle plumbing; frozen T/C definitions/data projections не заменяются сравнением intersection |
| `tests/test_postgres.py` | Exact inventory: старые35 + новая guard receipt table |
| `tests/test_m1_3_c0_acceptance.py` | Explicit TRUNCATE child guard receipt вместе с CONTROL receipt, даже при пустом child; без CASCADE и изменения старых assertions |
| `tests/test_telegram_egress_postgres.py` | Latest G/schema pairing; frozen C сохраняет exact0009 projection/inventory, без intersection |
| `scripts/prepare_telegram_egress.py`, `scripts/test_telegram_egress.sh`, `scripts/test_telegram_egress_migration.sh`, `tests/test_telegram_egress.py`, `tests/test_telegram_egress_migration.py` | Только необходимая exact inventory и frozen C→G phase/source pairing§13.7 после адресного C6/C0 согласования; не lifecycle/pin/recovery redesign |
| `docs/tasks/M3_CONTRACT.md`, `docs/runbooks/M2_TELEGRAM_LOCAL_TEST.md` | Принятое дополнение/evidence и точная LOCAL/TEST source/schema инструкция после кода; register/handoff остаются у C0 |

Дополнение R1 к proposed allowlist — ровно эти пять paths: два frontend label/test
и три inventory/fixture/schema tests. Сейчас ни один из них не является write scope;
`tests/test_m1_3_postgres.py` и Audit columns не добавляются заодно.
Другие runtime modules, owner API/tenancy API, HTTP/OpenAPI snapshots, frontend
за пределами двух названных label/test paths, dependencies/locks,
Compose/workflows, applied migrations, imported canon не
планируются к изменению. Если inventory/fixture требует дополнительный path,
предъявить конкретный diff и причину C0 до записи; не расширять список молча.
Каждую адаптацию старого теста объяснить новой typed kind/schema, сохранив прежний
смысл assertion; skip/xfail, подмена actual среды и обновление ожиданий «до зелёного»
не допускаются. Номер теста/количество строк не являются критерием приёмки.

### 13.10. Конкретные вопросы review и статус доказательств

По [C0 R1 decision](https://github.com/Elefesys/ai-service-manager/pull/28#issuecomment-6121132463),
принявшему [C1 review](https://github.com/Elefesys/ai-service-manager/pull/28#issuecomment-6120487284)
и [C2 review](https://github.com/Elefesys/ai-service-manager/pull/28#issuecomment-6120992738):

| Решение | Предлагаемый выбор / оставшийся вопрос |
|---|---|
| GUARDS-POLICY-01 — LOCKED C0 | Только LOCAL/TEST + CONTROLLED: новый Resume profile и live автор Resume; existing manual_send только availability, отдельный trusted automated path. Production AI/M4 permission не выдаётся |
| GUARDS-POLICY-02 — LOCKED C0 | Только deterministic TEST consumer: один accepted intent на Turn, stale pending без automatic replacement; поздний media revision не создаёт второй ответ. Допустим пропуск TEST ответа при новой информации; это не общая production AI policy |
| C1-M3-GUARDS-01 / P3 — OPEN до verdict C0 | R1 §§13.5/13.8/13.9: existing OUTBOUND label «Исходящее», public shape/statuses/manual flow сохранены, два точных future frontend paths; фактическая implementation ещё не выдана |
| C2-M3-GUARDS-01 / P2 — OPEN до verdict C0 | R1 §§13.6/13.8: existing turn_execute body allowlist до preflight/mutation, genuine guarded claim negative и intended new path; шесть новых profiles, applied0008 неизменна |
| GUARDS-DB-01 — OPEN до R1 acceptance | C2 поддержал одну receipt table; §13.6 уточняет exact typed FK chain/parent-key reuse и новый Job→Outbox kind FK. Номер миграции остаётся рекомендацией C2 до назначения C0 |
| GUARDS-COMPAT-01 — OPEN | После сведённого R1 C0 выдаёт конкретный C6 source/schema review: frozen C/0009 → G phase/exact inventories при прежних budgets. Укладываемость пока не измерена; общий audit/harness redesign не выдан |

Это исправления документационного proposal по static source traces, а не finding
исполненного GUARDS runtime или принятого CONTROL. Общий contract не объявляется
принятым; runtime строки §13.8 остаются PLANNED. Закрытие findings выполняет C0.

Контракт сознательно не обещает exactly-once внешнего эффекта: durable intent,
canonical result и UNKNOWN/no-resend сохраняют прежнюю честную границу M2.
Чтение текущего AI flag или successful effects-free receipt не заменяет admission.
IMPL-01/02/03/04 CLOSED; IMPL-05 OPEN/DEFERRED без новых изменений. Native account
gate NOT VERIFIED; M3 остаётся IN_PROGRESS. VM/Telegram/live/deploy/merge не выданы.

На contract head выполняются только source/ancestry, single-path/prefix, diff и
ссылочные/consistency проверки. Runtime/PG/S3/relay/Docker/новые fault experiments
не запрашиваются для документа. Автоматический PR CI сохраняется; его status,
tested merge/parents/tree указываются в единственном PR receipt и **не являются
GUARDS execution evidence**. После receipt C3 удерживает head до решения C0;
самостоятельно задачи C1/C2/C6 не выдаёт и implementation не начинает.

### 13.11. Implementation GUARDS — C3, 2026-10-12

Выдача C0 implementation6123042372 сняла прежний HOLD после R1/C6 acceptance.
Продолжение — `c3/m3-1-guards`, Draft PR28, sole start parent
`4caf1d64ce6073cc8064b088f9a0a9cdf245ad20`; frozen C/main —
`c6a55b6b17d1c1ab286ce97dfa4bd27197141fe5`. Принятые226090bytes выше сохранены
как неизменный prefix. Это описание реализации и подготовленных проверок;
actual final-source CI и verdict привязываются только в едином
[C3 receipt6119496506](https://github.com/Elefesys/ai-service-manager/pull/28#issuecomment-6119496506).
До завершения runtime gates задача IN_PROGRESS, не VERIFIED.

`0010_conversation_guards.py` (0010→0009) добавляет одну private FORCE RLS
receipt table, nullable profile/rejection, typed kind/step и relation constraints.
Шесть новых SQL profiles соответствуют §13.6; public EXECUTE только у четырёх
runtime capabilities, private check/fingerprint runtime не вызываются.
Existing SQL replacements используют зафиксированные0009 bodies; unused
reverse восстанавливает их без правки applied0001–0009. Runtime/readiness и
TEST provisioning требуют exact0010. Legacy Resume replay не пишет profile.

`conversations/guards.py` содержит закрытые внутренние DTO и effects-free
`consume_guarded`, возвращающий exact `CONTROLLED GUARDS TEST`.
`messaging/database.py` добавляет четыре typed worker entrypoints; никакого
owner context для consumer/send не создаётся. `worker.py` маршрутизирует
GUARDED_TEXT и SEND_GUARDED_TEXT отдельно от effects-free TEST_CONSUME/manual
admission; не вызывает Telegram probe для automated path. BEGIN/COMMIT и
adapter I/O разделены. Result acceptance, DB fingerprint, canonical replay,
post-wait checks и durable dispatch принадлежат PostgreSQL. Existing controlled
adapter считает каждый CALL/EFFECT; transport дедупликации не добавлено.

Матрица §13.8 реализована следующими проверками (короткие имена ниже — suffix
`test_` в `tests/test_m3_1_guards_postgres.py`, если path не указан):

| Строка §13.8 | Исполнимые проверки / ожидаемые assertions |
|---|---|
| 1 fresh positive | `fresh_owner_resume_normal_ingress_worker_atomic_intent_and_final_send`: owner API → fresh Inbox → normal queue/worker, один accepted intent, own context+1, SENT/CALL1/EFFECT1, нет manual receipt/Audit, pool checkedout0 на adapter |
| 2 legacy routing | `legacy_capability_rejects_genuine_guarded_claim_before_any_mutation`: current/Takeover, INVALID_INPUT и full facts unchanged; intended path ACCEPTED/STALE |
| 3 Takeover wait | `takeover_wins_observed_conversation_wait`: actual PG blockers, accept STALE без intent, begin FAILED/STALE без attempt/CALL |
| 4 generation/backlog | `new_material_or_generation_rejects_old_snapshot[resume]`, `telegram_resume_and_fresh_ingress_never_plan_or_probe_automated_send`, migration legacy NULL/replay/no-backfill; retained CONTROL capture tests |
| 5 new material/relations | `new_material_or_generation_rejects_old_snapshot`, `late_same_turn_file_revision_cannot_replace_accepted_intent`, `private_receipts_and_same_workspace_relation_forgery_are_rejected`: inbound/manual/file hooks, late revision ALREADY_ACCEPTED, exact same-kind FK23503 |
| 6 live authority/time | `post_wait_live_authority_and_db_clock`: owner revoke, expiry, activation, inactive channel; observed locks и DB clock, обе accept/begin boundaries |
| 7 claims/concurrency | `claim_expiry_reclaim_and_guarded_exhaustion_leave_ready_turn`, `canonical_refs_bad_digest_token_and_concurrent_exact_replay`: old token rejects, canonical refs, два accept возвращают один immutable receipt, changed text conflict |
| 8 atomicity/accept ACK | `acceptance_rolls_back_every_write_and_final_update` шесть boundaries + `acceptance_and_finalize_ack_loss_read_canonical_success`; full facts rollback, DB-authoritative fingerprint и canonical receipt |
| 9 durable begin | `dispatch_linearizes_before_effect_and_takeover_does_not_veto_finalize`: Takeover до/после adapter effect после committed begin; factual SENT, CALL1/EFFECT1 |
| 10 start ACK/process | `guarded_process_death_unknown_no_resend_after_restart_and_resume[start_after_commit-0]`: existing M2 child exit42, durable start, UNKNOWN/CALL0/EFFECT0 после recovery |
| 11 possible effect/process | тот же existing process family `[after_effect-1]`: UNKNOWN/CALL1/EFFECT1 после restart/Takeover/Resume; второй call отсутствует |
| 12 retry/finalize | `proven_not_sent_rechecks_guard_and_exhausts_without_turn_failure`, lost finalize ACK: каждый новый begin rechecks, старый attempt допустим, пять claims max, READY Turn не FAILED, canonical SENT сохранён |
| 13 retained/manual/history | `tests/test_m3_1_control_api_postgres.py` mixed read + `frontend/src/MessagingPanel.test.tsx` mixed10rows/all5statuses; только manual flags считают manual, composer/recovery и public shape прежние |
| 14 schema/source | `tests/test_m3_1_guards_migrations.py`: fixed C35/G36, populated repeat/reverse definitions/data, legacy NULL, used refusal, fresh actual-schema observer/lost commit ACK; tenancy exact SQL profiles и existing schema inventory tests |

C6 plan воплощён в существующих двух state lanes: H wrapper один раз;
H→T direct frozen T; T→C direct selector из byte-identical frozen C checkout;
C→G selector из G. C runtime/development images переиспользуются только после
attestation. G controller расположен в разрешённом guards migration test.
Сохраняются retained T full/negative и C six-daemon proofs; C tail negatives
исполняются в C checkout и сохраняются в `reports/retained-control/`.

Один coordinator600 начинается после H до T preparation. Whole T/negatives,
whole C including capture/cleanup/report, pre-G и G image preparation используют
исходный absolute deadline. Retained C supervisor получает remaining600 без
terminal+480; terminal G сохраняет прежний runtime bound. Cleanup90, state25min,
foundation35min, exact Docker29, all9/source9 unchanged. G reports:
`reports/guards-schema-phase.json`, `reports/control-schema-ledger.json`;
retained C report сохраняет C source, не объявляется G evidence.
Actual укладываемость проверяется runner; новый лимит не введён.

Адаптации старых проверок ограничены принятым поведением: latest readiness/setup
0009→0010 (0009 теперь negative); latest inventory35→36 с отдельными frozen T/C
sets; cleanup удаляет новый child receipt до родителей; retained CONTROL tests
явно исполняют0009 cycle; mixed history отделяет manual status flags. Static
coordinator assertion теперь требует явные T/C/G executors и C negative tail.
OpenAPI, auth/owner DTO, manual fingerprints/Audit, source pins и guards не менялись.

Локально: Ruff/format/mypy, generated OpenAPI consistency и frontend typecheck
PASS; frontend114 PASS; полный non-integration1082 PASS/0 FAIL (110.40s).
Docker отсутствует: local actual PG/S3/browser/Docker29 NOT RUN. Эти локальные
результаты не доказывают runtime строки таблицы; actual результаты и точный
head/tree/merge/ordered parents/run/jobs/artifact digests публикуются в receipt.
Секреты/live Telegram/VM/рабочие DB/S3 не использовались. C0 intake и независимый
C8 ещё обязательны; scope exclusions §§13.8–13.10 сохранены.

Первый implementation run38248730093 / head77155722c34a671af011caa90407f64c3f9a4a9e:
8 jobs PASS, foundation остановлен на3 старых unit queue cases до PG suite.
Причина — eager database-name lookup в общем constructor при TEST environment;
старые doubles намеренно описывают только прежний driver/role contract.
Проверка имени БД перенесена в `_require_guards`, то есть применяется ко всем
четырём новым entrypoints до transaction, вместе с server-environment gate.
DB-side current_database/provider/authority checks сохранены; старые tests/fixtures
не изменены. Адресный TEST-environment rerun:25 PASS. Это содержательная правка
admission boundary; полный новый source CI требуется после неё.

В первом actual normal/exact Docker29 C→G phase обе проверки PASS: guarded
CALL1/EFFECT1, C35 projection/private-S3 unchanged, unused reverse/used refusal,
post-commit exit86 → independent actual0010 observer → G callers/restart.
Prepare charge normal419.586215s / Docker29427.785057s < исходных600;
whole retained C113.157986s /113.469536s включён, G prepare8.112129s /8.133850s.
Retained T/C/daemon negatives и clean8 сохранены. Это evidence первого tree,
не переносится автоматически на исправленный final head; новые IDs в receipt.

Второй run38251039019 / heada8eff5f161c1bb5ad7b99216a7333ead35d02f17:
constructor regression закрыта;8 jobs PASS, foundation1081 unit PASS/1 FAIL
до597 PG cases. Retained early-failure unit сравнивал float subtraction с600:
`1475.198142485 - 875.198142485 == 600.0000000000001`, хотя сохранённое
`deadline == started_at + 600` точно TRUE. Исправлены два одинаковых unit
assertions на эту исходную exact identity, без tolerance/расширения bounds;
существующий early-refusal seam фиксирует наблюдённый fractional clock для
детерминированного воспроизведения. Runtime/harness clocks, deadlines, cleanup,
source guards и actual Docker cases не менялись. Адресный budget/early-failure
suite38 PASS. Новая полная source проверка обязательна, ручного rerun-to-green нет.
Вторые G phases actual PASS: charge369.394445s normal /368.402980s Docker29;
whole retained C93.381538s /92.315675s включён; данные/identities/retained proofs
подтверждены чтением artifacts11748991093/11748866348. Это evidence второго tree.

Третий run38253408056 / head756714f78327f80118d962d4b9311e74165fa906:
unit1082 PASS (185.25s); actual PG591 PASS/6 FAIL (847.68s), затем foundation
CANCELLED на прежнем35min. Остальные8 jobs/clean8 PASS. Разобраны ошибки именно
новых scenarios: fresh manual API принимает202, а не200; owner Takeover нельзя
исполнять из migrator через runtime-only raw_context; file/crash setup не может
предполагать отсутствие retained effects-free Jobs. Исправление сохраняет все
outcome/counter/assertions и production: Takeover prepare/execute берёт lock
через настоящую runtime capability; file case проходит обычный Inbox/claim и
проверяет отдельный context increment после finish_fetch; existing M2 crash
child выполняет обычный worker loop до прежнего barrier/exit42, не меняя очередь.
Старые M2 helpers/CHILD и runtime/DDL/budgets не менялись. Это содержательный
test-setup fix; новый CI обязателен, лимит foundation35 не расширен.
Третьи G phases PASS: charge421.186321s normal /419.969723s Docker29; whole C
112.615779s /111.796138s включён. Artifacts11749449642/11749900999 проверены;
этот частичный PASS не объявляется завершённой GUARDS приёмкой.

## 14. M3.2 — минимальный Escalation backend/API: proposal для C0/C1/C2

### 14.1. Статус, источники и один рекомендуемый результат

**R2 / REVIEW, 2026-10-13; только контракт, не разрешение implementation.** Основание —
[выдача C0](https://github.com/Elefesys/ai-service-manager/pull/30#issuecomment-6142964762)
и активный M3_HANDOFF§0 на `a20423248b54c46720e361d7e79c47ee278f00de`, уточнённые
[ограниченной R2 C0](https://github.com/Elefesys/ai-service-manager/pull/31#issuecomment-6145970644)
после C1/C2 review. R2 разрешает редактировать только собственный ещё не принятый §14.
Accepted main — `c502d5fd258aef15bb5549e1529df8d038a4fb9b`, schema0010;
main CI38374030362/attempt1 SUCCESS относится к прежнему продукту. Весь prefix
этого документа до §14 — прежние238882 bytes/blob
`1763a5379926e4ae3e47483faf91b006e5bc4f30`, без правок исторических решений/evidence.
Прикладная LOCAL/TEST policy принята C0 в R2 (§14.11); DB mechanics остаются REVIEW,
runtime proofs PLANNED/NOT RUN. Принятие policy не означает приёмку всего контракта.

Прочитаны AGENTS/IMPL-001; оригиналы Spec §§1.7/5.10–5.14/14.11/16/18.5–18.8/24.7,
ADR-023–026/121–128/139/197–198/267, MVP GJ-G/GJ-J, Roadmap M3,
Implementation Plan M3.1/M3.2, OPEN-082/083/085; §§8/9/12/13 этого контракта.
Оригиналы из `project_sources` сверены с SOURCE_MANIFEST и imported canon.
Actual source traces: conversations/control/guards/turns, owner HTTP/strict DTOs,
messaging/database/worker/results, tenancy UOW/auth boundary, Audit API/parser,
applied0008–0010, exact readiness и существующий source/schema controller.

Результат будущего backend-среза: штатный CONTROLLED Turn может вместо TEST text
создать один durable запрос решения своему владельцу. Owner API читает очередь
и контекст, принимает короткий внутренний ответ либо отмену. Два внутренних
напоминания и expiry исполняются существующими PostgreSQL Jobs после restart.
Это отдельный lifecycle; Conversation.control_mode не становится «ESCALATED».
Создание, ответ, отмена, expiry и reminder не выполняют Resume и не отправляют
Message клиенту. В HUMAN режим остаётся HUMAN; в AI нет нового разрешения
автоматики помимо уже принятого явного Resume и текущих GUARDS.

Не входят: Agent/LLM M4, ApprovalRequest/M6, денежные действия, новые transports,
клиентские follow-ups, внешние owner notifications, Notification Engine/M9,
новые Telegram/native/edit/delete producers, Console owner-wait UI. OPEN-082
остаётся OPEN: TEST сроки ниже не являются SLA, quiet-hours/contact policy или
обещанием клиенту. OPEN-083 safe default и OPEN-085/native NOT VERIFIED сохранены.
CONTROL routes, manual composer/receipt recovery, manual-only `manual_delivery`
и вся OUTBOUND история остаются совместимыми.

### 14.2. Исполняемый producer без M4 и точная дельта GUARDS

Предлагается новый Turn step **`ESCALATE_OWNER`** внутри существующего
`PROCESS_TURN`, а не публичный create endpoint или самостоятельный worker principal.
Реальный путь: trusted CONTROLLED ingest → Inbox commit → обычный PROCESS_INBOX →
Turn/group/media → `turn_enqueue` → обычный claim/admit → `Worker.run_once` →
`EscalationService.request_for_turn(claim)` → короткая DB capability
`platform.escalation_request_for_turn(job_id,claim_token)` → durable request/Jobs.
Worker вызывает сервис в штатном маршруте; отдельный тестовый вызов SQL не заменяет
этот путь. Никаких canonical Escalation rows через migrator fixture.

**Конечный synthetic trigger:** в READY Turn есть хотя бы один canonical inbound
TEXT member с точным текстом `CONTROLLED ESCALATION TEST`. Без trim/case-fold,
regex intent detection, LLM или произвольного JSON reason. Другие members этого
же Turn включаются в snapshot; сам marker остаётся обычным входящим Message.
Trusted source/нормализация, provider=CONTROLLED, server environment LOCAL/TEST,
DB name `asm_local`/`asm_test` и private `CONTROLLED_GUARDS_V1` Resume profile —
независимые обязательные gates. Строка в Telegram, legacy/HUMAN/pre-fence входе
не создаёт запрос и не наделяет отправителя полномочиями.

`turn_enqueue` сохраняет прежние GROUP/MEDIA/TEST_CONSUME jobs. В **новой** migration
меняется только выбор дополнительного action step для допустимого READY Turn:
marker → ESCALATE_OWNER; остальные Turns → прежний GUARDED_TEXT. Это явная
совместимая дельта §13.3: literal `CONTROLLED GUARDS TEST`, его consumer, DTO,
fingerprint и accepted receipts не меняются. Marker не добавляется в старый
GUARDS text result. Exact marker повторно проверяется DB при admission.

Для старых уже поставленных GUARDED_TEXT jobs выбор не переписывается миграцией.
Guard prepare/accept дополнительно отказывают для marker Turn и для Turn,
по которому уже принят Escalation; существующий accepted guard intent никогда
не переклассифицируется: winning receipt replay остаётся до новых marker/pending
checks. Escalation create симметрично отказывает при accepted
guard receipt по любому revision того же Turn. Проверки и INSERT сериализуются
на Conversation. На один Turn возможен **либо** accepted guarded intent, **либо**
accepted Escalation, никогда оба. Новый marker job появляется только через
обычный fresh enqueue, не через migration/backlog sweep.

Creator принимает только job/token. Workspace, Client, Conversation, Business,
Turn/revision, connection, origin members, Resume receipt/actor/generation/fence
читаются из сохранённых связанных строк. Ни assignee, ни deadline, ни причина,
ни «текущая версия» не поступают как authority из worker payload/GUC.
Reuse `messaging_admit`/`messaging_guard`, physical transaction/task ownership,
canonical claim token/lease; owner и worker contexts по-прежнему разделены.
Live автор именно этого Resume становится ответственным. Проверяются существующие
origin/fence условия §13.2, READY/current revision, live OWNER, active Workspace/
Business/CONTROLLED connection и прежняя availability `messaging.manual_send`
через SQL authoritative gate. Это допуск synthetic producer, не permission
локальной owner-команды и не разрешение production AI.

Доменный метод строит request из canonical Turn snapshot под locks, атомарно
принимает его и завершает собственный consumer Job. Здесь нет inference/network
между snapshot и acceptance, поэтому второй prepare/compute/finalize цикл не нужен.
Snapshot включает существующие member Message/File versions и новые binding поля,
но не содержит выдуманных business facts. Future M4 caller сможет использовать
доменную модель только после отдельного authority/producer контракта; текущая
capability не принимает любой чужой kind/step или произвольные reason/answer.

`platform.turn_execute` сохраняет allowlist GROUP/MEDIA/TEST_CONSUME и отвергает
ESCALATE_OWNER до preflight/seal/mutation; guard prepare/accept допускают только
GUARDED_TEXT. Новый `EscalationTimerClaim` также нельзя провести через эти legacy
capabilities, send begin или process_inbox. Отказ старого token не чинится новым
user context. Python gate размещается у нового callable, не в общем constructor.

### 14.3. Identity, immutable request и lifecycle

Одна новая domain row `app.escalations` представляет запрос, его immutable origin
и дальнейший исход. Минимальные поля сгруппированы ниже; это модель, **не DDL**.

| Группа | Предлагаемые поля и смысл |
|---|---|
| Identity | `workspace_id,id`, namespace=`ESCALATION_REQUEST_V1`, canonical `conversation_id,client_id,connection_id,turn_id`; один accepted request на `(workspace_id,turn_id,namespace)` независимо от revision |
| Origin | `source_job_id,source_job_kind=PROCESS_TURN,source_job_step=ESCALATE_OWNER,source_claim_token,turn_revision,resume_receipt_id,control_generation,activation_fence_seq,input_context_version`, canonical `request_snapshot`, `context_fingerprint`, `request_fingerprint`, `created_at`, immutable `creation_result` |
| Request | `reason=OWNER_DECISION_REQUIRED`, `assignee_user_account_id`=live Resume actor, `question=CONTROLLED ESCALATION TEST: требуется решение владельца.`, `policy=LOCAL_TEST_OWNER_WAIT_V1`; не caller-controlled строки |
| Relevance | `waiting_context_version=input_context_version+1`; captured generation/Turn revision, immutable snapshot digest. Текущие версии читаются отдельно, не FK на mutable version |
| Lifecycle | `version`=1 при PENDING, =2 при единственном terminal переходе; `status=PENDING/RESOLVED/CANCELLED/EXPIRED`; nullable `closure_reason,completed_at,answer_text,decided_by_user_account_id` с closed shape. Audit reference хранится только в owner receipt (§14.6), в request обратной ссылки нет |
| Schedule | Сохранённые `due_at,second_reminder_at,expires_at`; nullable `first_reminded_at,second_reminded_at`. Reminder не меняет lifecycle version; count выводится из двух slots, нового notification ledger нет |

`context_fingerprint` — lowercase hex SHA-256 от UTF-8 DB canonical
`request_snapshot::text` (jsonb): existing Turn snapshot без внешнего `code/job_id`
envelope и без старого `snapshot_digest`, плюс canonical conversation/client/business,
Resume/fence и source job identity. Snapshot фиксируется один раз; bytes/codec
не зависят от порядка ключей HTTP. `request_fingerprint` — SHA-256 UTF-8 строки
`asm:m3:escalation_request:v1\n` + DB jsonb text объекта с полями `snapshot`,
`reason`, `assignee_user_account_id`, `question`, `policy`. Due timestamps получаются
из одного trusted acceptance moment, не входят в dedupe identity и не пересчитываются
на replay. DB вычисляет оба fingerprints; worker не может прислать свой hash как истину.

Partial UNIQUE `(workspace_id,conversation_id)` WHERE status=PENDING ограничивает
одновременное ожидание одним. При уже имеющемся request этого Turn возвращается
`ALREADY_ESCALATED` с его ID, включая terminal: не открывать его заново и не двигать
сроки. При другом PENDING request — `WAITING_EXISTS`, без нового request/reminders.
При guard intent того же Turn — `ALREADY_ACCEPTED`, без Escalation. Rejected producer
завершает только свой Job с typed outcome STALE/SUPERSEDED/NOT_ALLOWED либо указанным
dedupe outcome; не FAILED Turn и не «успешное решение». Existing receipt не становится
current authorization. Нормальный runtime не удаляет terminal requests/receipts.

| Переход | Результат и counters |
|---|---|
| Create после полного admission | PENDING/version1; Conversation.context +1 ровно один раз; control_mode/generation/fence +0; три timer Jobs и consumer SUCCEEDED атомарно; Message/Outbox/send/Audit от fake OWNER отсутствуют |
| Owner resolve | Только актуальный PENDING до expiry; RESOLVED/version2, exact внутренний `answer_text`, actor/time, owner receipt/Audit; context +1, control +0 |
| Owner cancel | Актуальный PENDING до expiry; CANCELLED/version2/OWNER_CANCELLED, actor/time, receipt/Audit; context +1, control +0; answer NULL |
| Material invalidation | PENDING → CANCELLED/version2/CONTEXT_CHANGED либо CONTROL_CHANGED в том же commit, что material fact; дополнительного context/generation increment нет |
| Assignee потерял OWNER/активность | При timer execution PENDING → CANCELLED/version2/ASSIGNEE_REVOKED; context +1, control +0. Уже до timer current projection не разрешает resolve/reminder; другой live OWNER может явно cancel |
| Trusted time `now >= expires_at` | PENDING → EXPIRED/version2/DEADLINE_ELAPSED при timer; context +1, control +0; answer/owner actor/Audit NULL. Ни retry, ни задержанный scheduler не продлевают срок |
| Reminder slot | Только current PENDING и due ≤ now < expiry; записывается свой ранее пустой slot, Job SUCCEEDED; lifecycle/context/control +0 |
| Повтор/отказ/terminal timer | Canonical replay или NOOP_TERMINAL; ноль новых domain rows/versions/Audit/reminders/effects |

В MVP answer — **записанная внутренняя заметка-решение владельца** по запросу,
а не текст, уже отправленный клиенту, executable instruction, Approval или
изменение booking/payment. Сохраняется exact text длиной1..512 Unicode scalars,
UTF-8 ≤2048 bytes, без NUL/surrogates и не whitespace-only; никакого trim/NFC.
Ни resolve, ни cancel/expiry не ставят PROCESS_TURN, SEND или «продолжить старый ответ».
Старый source Turn исчерпал свою единственную Escalation identity навсегда;
late-file revision не создаёт второй запрос/guarded intent. Новая работа может
прийти только от нового допустимого ingress/Turn по обычным текущим gates.

**Waiting projection** — WAITING_FOR_HUMAN только для PENDING с совпадающими
bound context/generation/Turn revision, live assignee и now < expiry. Иначе NULL;
RESOLVED не означает автоматически READY_TO_RESPOND или AI. Текущий MVP не вводит
полную state machine WAITING_FOR_CLIENT/PAYMENT/EXTERNAL_SERVICE из Spec5.14.
Existing Conversation/control DTO не расширяется: будущий C5 получает owner-wait
через новый Escalation API и связывает по canonical conversation/client.

### 14.4. Material boundary, время и durable reminders

Предлагается private AFTER UPDATE trigger на **изменение** Conversation.version
или control_generation. Под уже удерживаемым Conversation NO KEY UPDATE он
отменяет несовместимый PENDING request, меняя только Escalation row. При одновременном
изменении обоих counters причина CONTROL_CHANGED имеет приоритет. Trigger не берёт
Job/Outbox/connection/Turn locks и не увеличивает Conversation повторно.
Create сначала увеличивает context, затем вставляет новую PENDING row; terminal
команда/таймер сначала закрывает row, затем увеличивает context. Это предотвращает
самоотмену и рекурсивные increments без bypass GUC или временного disable trigger.

Фактическая material boundary сохраняет уже принятую семантику: новый PROCESSED
inbound Message в PROCESS_INBOX commit; новый manual/guarded outbound intent;
FileObject PENDING→READY/FAILED; delivery PENDING/DISPATCHING→SENT/FAILED/UNKNOWN;
новый accepted Takeover/Resume/manual generation. Durable Inbox ACK до обработки
ещё не является новым Message/context fact. Duplicate/replay/IGNORED, seal сам
по себе и reminder не отменяют ожидание. Новое сообщение об отказе клиента пока
обычный новый material inbound: старый запрос отменяется независимо от NLP.
Отдельный распознаватель withdrawal и native/edit/delete provenance не добавляются.

GUARDS prepare/accept/begin дополнительно проверяют отсутствие сохранённого PENDING
Escalation в Conversation, под тем же serialization lock. Это консервативный gate:
даже уже overdue PENDING блокирует новый automated admission до terminal cleanup,
а не исчезает в момент чтения часов. Late snapshot после закрытия отклоняется по
новому context; accepted guard receipt своего Turn остаётся неизменным.
Уже committed DISPATCHING не отзывается созданием/отменой ожидания: finish сохраняет
фактический SENT/FAILED/UNKNOWN, без blind resend. Его terminal material commit
может отменить ещё PENDING Escalation. Manual send и Takeover не блокируются wait.

**Один finite TEST policy:** acceptance=t; due_at=t+2min, second_reminder_at=t+5min,
expires_at=t+10min; ровно два внутренних slots, без quiet hours, env knobs и
production defaults. При create вставляются три существующих durable Job rows
нового kind `ESCALATION_TIMER`, steps REMIND_1/REMIND_2/EXPIRE, available_at равен
сохранённому сроку; UNIQUE `(workspace_id,escalation_id,step)`. Пять attempts,
прежний bounded jitter/backoff ≤60s, retry window15min и lease30s сохраняются.
Ошибки не создают дополнительные reminder Jobs и не сдвигают domain expiry.

Обычный worker исполняет timer в короткой transaction, scheduler продолжает
существующий claim/reclaim/recovery; нового poller/cron/notification transport нет.
После locks заново проверяются claim/lease и trusted time. Приоритет: terminal
row → NOOP; несовместимый generation/context/Turn → CANCELLED; неактивный assignee
→ CANCELLED; now ≥ expiry → EXPIRED; иначе только due reminder slot. EXPIRE раньше
своего deadline не допускается к claim; forged/неподходящий step/token отклоняется.
При восстановлении после обоих reminder due, но до expiry каждый slot записывается
не более одного раза; порядок между1/2 не обещается. После expiry missed reminders
не «догоняются». Это durable запись для Console, не обещание, что человек её увидел.

Slot update + own Job SUCCEEDED — один commit. Crash до commit оставляет slot пустым;
после commit повторный worker не создаёт второй reminder. Cancel/resolve выиграли
Conversation lock → timer завершится NOOP; reminder выиграл раньше → сохранённый
slot остаётся историческим, subsequent cancel его не стирает. Старый token после
reclaim не может записать slot или закрыть request. Terminal rows immutable;
оставшиеся максимум три jobs лениво завершаются NOOP при due/claim/recovery.
Owner/material paths не блокируют их под Conversation lock ради eager cancellation.

Exhaustion нового consumer завершает только consumer Job, не Turn: новая ветка
`messaging_reschedule` исключает оба steps GUARDED_TEXT/ESCALATE_OWNER из FAILED
Turn mutation. Timer не использует PROCESS_TURN fallback. В timer maintenance
claim/recovery/exhaustion после canonical preflight сначала проверяют terminal,
relevance/assignee/expiry. Успешный terminal cleanup или уже terminal request даёт
SUCCEEDED с EXPIRED/CANCELLED/NOOP_TERMINAL, даже если retry budget исчерпан: работа
по закрытию/проверке уже выполнена. Если request ещё current PENDING до expiry,
exhaustion завершает только own Job DEAD/RETRY_EXHAUSTED, без reminder/domain write.
Неисчерпанный expired-lease Job в этом случае штатно возвращается READY с прежним
DEPENDENCY_TIMEOUT/backoff; reminder исполняет только новый admitted claim.
Recovery не вызывает `escalation_timer_execute` с просроченным lease и не создаёт
новый token/worker context ради обхода admission.

**Committable invariant failure:** own Job UPDATE и все canonical preflight locks
из §14.7 получены **до** внутреннего PL/pgSQL EXCEPTION block/subtransaction.
Внутри него только attempted slot/terminal request update и соответствующий
Conversation context increment. Для перехватываемого permanent failure rollback
этого внутреннего блока возвращает request/slots/counters к прежним значениям;
наружные locks сохраняются, и снаружи блока пишется DEAD только в own Job. Общий
SQL fragment допустим в исходнике новой migration, новый SQL profile не добавляется.

Перехват ограничен **SQLSTATE23514** и точными stacked diagnostics
`SCHEMA_NAME=app`, `TABLE_NAME=escalations`, `CONSTRAINT_NAME` из трёх имён:
`escalations_lifecycle_check`, `escalations_reminders_check`,
`escalations_immutable_check`. Первые два — named CHECK новой row shape; последнее
— diagnostic constraint name нового immutable trigger, который выставляет все
три diagnostic fields явно. Это ошибки собственной записи timer после canonical
preflight (worker admission либо maintenance authority), не классификация входного
owner body. Mapping в существующий Job error code —
**INVALID_INPUT**, `escalation_outcome=NULL`; текст исключения не парсится.
Несовпавший/пустой diagnostic, другой CHECK/FK/unique error или любой иной SQLSTATE
пробрасывается без такой terminal записи; `WHEN OTHERS → DEAD` запрещён.

| Timer result после успешного commit | status / error_code / escalation_outcome | Domain |
|---|---|---|
| Успешный slot/cleanup/terminal observation | SUCCEEDED / NULL / REMINDED либо EXPIRED либо CANCELLED либо NOOP_TERMINAL | Только реально записанный slot/переход; NOOP не меняет row |
| Permanent invariant failure из точного набора выше | DEAD / INVALID_INPUT / NULL | Cleanup subtransaction откатан; request/slots/context/control неизменны |
| Обычный exhaustion, cleanup не требовался | DEAD / RETRY_EXHAUSTED / NULL | Current PENDING сохраняется; slot не записывается |
| Обычный retry/recovery без terminal результата | READY / DEPENDENCY_TIMEOUT либо DEPENDENCY_UNAVAILABLE / NULL | Прежние attempt/window/backoff; без domain write |

Во всех terminal shapes claim_token/lease_until/worker_id=NULL, completed_at finite,
Job.version +1; attempt_count/first_started_at соответствуют existing Job CHECK.
Terminalization READY без прежнего attempt использует существующий pattern
`greatest(1,attempt_count)`/`coalesce(first_started_at,clock_timestamp())` только
после due/preflight, не расходует второй attempt и не расширяет retry budget.
Job completion и успешный domain write — всё ещё один внешний commit. Ошибка
самой записи DEAD/commit не перехватывается как доказательство durable результата;
при потерянном ACK canonical Job читается свежей transaction, без speculative success.
STALE_CLAIM/P2001, NOWAIT55P03→P3001 BUSY, cancellation/statement timeout57014,
unavailable DB/connection и failed commit не превращаются в durable DEAD. BUSY
откатывает **весь** scan candidate, включая Job lock (§14.7). При недоступной DB
никакой durable transition не обещается; retained Job остаётся для recovery.
DEAD Jobs больше не выбираются ни READY claim, ни RUNNING recovery; re-enqueue нет.

**Truthful projection:** DEAD timer означает FAILED maintenance, но не lifecycle
transition. До expiry raw PENDING с current relevance/live assignee сохраняет
validity=CURRENT/waiting=WAITING_FOR_HUMAN и обычные owner actions. При now≥expiry
waiting=NULL/actions=false независимо от scheduler/DEAD; validity=EXPIRED, если
не выиграла более ранняя причина CONTROL_CHANGED/CONTEXT_CHANGED/ASSIGNEE_REVOKED.
Сохранённый status остаётся PENDING до реально committed terminal transition.

**Часы:** новая private `platform.escalation_now()` — VOLATILE, runtime/HTTP/GUC не
могут её задавать; обычное тело возвращает DB clock_timestamp. Deadline сравнивается
после последнего lock wait. Для deterministic actual-PG тестов только serial fixture
в disposable asm_test проверяет database name и роль asm_migrator; замена тела
helper фиксированным UTC clock **committed**, видна другим test connections.
VOLATILE/search_path/ACL/owner/security сохраняются. Fixture восстанавливает точные
definition/owner/security/grants в finally отдельной исправной transaction и сверяет
catalog даже после assertion/DB error. Если тест завершает child process, cleanup
clock принадлежит живому parent; потеря parent уничтожает disposable DB, не оставляет
подменённую shared DB. В asm_local state lane этот seam не применяется.
Это явный test seam времени, не создание domain rows и не доказательство elapsed
wall time. Lease/retry/control/billing часы не подменяются. Tests идут через обычные
ingress/claim/API/capabilities; точные before/equal/after проверяются без sleep-based
correctness. Отдельный restart case оставляет настоящий clock и реальные processes.

GET и owner command всегда проверяют relevance/time, даже если timer ещё не
запускался. GET не пишет expiry; он явно различает stored status и current validity.
Rejected late command не фиксирует accepted receipt/Audit и не применяет ответ;
expiry позже записывает timer. Clock equality принадлежит expiry. Чтобы terminal
context +1 не переполнился, create требует input_context ≤ bigint_max−2: pending
резервирует один increment. Любой внешний material increment уже атомарно отменяет
pending без второго increment. Прочие existing overflow guards сохраняются.

### 14.5. Четыре owner routes и строгий consumer contract

Ровно четыре additive routes относительно `/api/v1/workspaces/{workspace_id}`:

| Method / path | Результат |
|---|---|
| GET `/escalations` | 200 `EscalationPage`: `items` (≤100 `EscalationView`), `next_cursor` string/null, один `observed_at` всей страницы |
| GET `/escalations/{escalation_id}` | 200 `EscalationView` с текущей projection; без query parameters |
| POST `/escalations/{escalation_id}/resolve` | 200 `EscalationCommandResponse`, только после commit; exact внутренний answer |
| POST `/escalations/{escalation_id}/cancel` | 200 тот же discriminated response; без answer/свободного reason |

Нет HTTP create/reassign/reopen/send/mark-read endpoint. Предлагаемые domain
permissions `escalations:read` и `escalations:decide` находятся в новом module;
оба только live Workspace OWNER. Они не расширяют tenancy.v1 и не используют
permission `messaging.manual_send`. **Resolve — только текущему live OWNER,
равному immutable assignee; cancel — любому live OWNER этого Workspace.**
Другой OWNER видит запрос и может закрыть его после ухода ответственного, но
не подменяет чужой ответ и не выполняет скрытую reassignment. Выбор требует C1/C0.

Read/resolve/cancel не вызывают Telegram, EntitlementService или billing refresh
и доступны при неактивном канале/Business либо недоступном billing, если auth,
Workspace и owner membership действуют. Это локальное решение, не outbound effect.
Создание нового synthetic request по-прежнему имеет отдельный producer gate§14.2.
Неактивный User/Workspace, отозванные session/OWNER не обходятся доступностью
исторического receipt. Ops/system admin не превращается в business OWNER.

Cookie/Origin/CSRF, allowed Host, rate limit, no-store, header limit16KiB,
Content-Type application/json, identity encoding, body read3s и общий body cap4096
сохраняются в existing AuthBoundary. Все POST требуют ровно один Origin и
CSRF token, ровно один `Idempotency-Key` по `[A-Za-z0-9._:-]{1,128}`; If-Match
не принимается. Новый 512-scalar answer помещается в обычный cap при компактном
UTF-8 JSON; чрезмерно escaped JSON всё равно ограничен4096 wire bytes и получает413.
Ни отдельной cookie, ни более широкого body limit/auth middleware exception не нужно.

Все DTO — extra=forbid, без coercion: canonical lowercase UUID, positive decimal
strings ≤int64 для versions/generation, UTC timestamps с6 fractional digits/Z,
closed enums и проверяемые nullable shapes. Duplicate JSON keys, NaN, lone
surrogate, NUL, пустой/whitespace-only answer, неизвестные поля/queries, повторные
параметры/headers и неправильные JSON types отклоняются. JSON whitespace/order
не значимы; значения answer/key/IDs/counters после строгого parse сохраняются
точно, без trim/normalization. Генерируемый OpenAPI отражает именно эти shapes.

Общий POST body: `expected_conversation_id`, `expected_client_id`,
`expected_escalation_version`, `expected_control_generation`, `expected_context_version`.
Resolve дополнительно требует `answer_text` с пределами§14.3. Cancel **не содержит**
answer, null answer также extra field. Все expected values обязательны; server
не подставляет текущий Client/версии из соседнего UI state и не принимает body
workspace/assignee/reason/deadline. Canonical Escalation→Conversation→Client
проверяется до команды; чужой Workspace/Client/Conversation/несуществующий ID →404.

`EscalationView` содержит ровно следующие поля/группы:

| Поля | Wire shape / смысл |
|---|---|
| `workspace_id,escalation_id,conversation_id,client_id,turn_id,assignee_user_account_id` | Canonical UUIDs; origin linkage, не credential |
| `reason,question,policy,version,status` | Literals§14.3; version decimal1/2; status — **сохранённый** lifecycle |
| `bound_context` | `turn_revision,control_generation,context_version` (context = waiting_context_version), decimal strings, `fingerprint`64 lowercase hex |
| `current_context` | `control_mode` HUMAN/AI, `control_generation,context_version`; прочитаны сейчас, отдельно от origin |
| `validity` | CURRENT / CONTROL_CHANGED / CONTEXT_CHANGED / ASSIGNEE_REVOKED / EXPIRED / TERMINAL; для stored terminal всегда TERMINAL; для PENDING порядок checks§14.4 |
| `waiting` | Literal WAITING_FOR_HUMAN ровно при PENDING+CURRENT, иначе null |
| `created_at,due_at,second_reminder_at,expires_at,observed_at` | UTC timestamps; due/expiry сохранены, observed_at — текущий read, не saved acceptance |
| `reminders` | Ровно2 элемента `{ordinal:1\|2,due_at,recorded_at:Timestamp\|null}` в ordinal order; никакой отметки «прочитано»/external delivery |
| `maintenance` | SCHEDULED / COMPLETE / FAILED: FAILED при любом DEAD timer (ровно INVALID_INPUT/RETRY_EXHAUSTED, outcome=NULL по §14.4), COMPLETE когда все3 timer jobs SUCCEEDED, иначе SCHEDULED. FAILED имеет приоритет даже при terminal request; сам по себе не меняет status/validity/waiting/actions |
| `resolution` | Только RESOLVED: `{answer_text,actor_user_account_id,completed_at}`, иначе null |
| `closure` | Только CANCELLED/EXPIRED: `{reason,actor_user_account_id:UUID\|null,completed_at}`; reason OWNER_CANCELLED / CONTROL_CHANGED / CONTEXT_CHANGED / ASSIGNEE_REVOKED / DEADLINE_ELAPSED; actor non-null только OWNER_CANCELLED |
| `can_resolve,can_cancel` | Текущие подсказки для этого session actor, не capabilities; resolve = CURRENT+assignee; cancel = PENDING, matching context/generation/Turn и now<expiry даже при revoked assignee; при POST всё перепроверяется |

Read — одна связная DB projection/statement snapshot с live owner admission и одним
observed_at, без изменения terminal rows и без network. Для PENDING/EXPIRED validity
UI должен показать «срок истёк», waiting=null, actions=false, даже если stored status
ещё PENDING. После terminal commit status становится EXPIRED. Receipt не используется
для обновления `current_context` или для вывода «запрос всё ещё ожидает».

List query: только `limit` (default25,1..100), `status` (default PENDING;
PENDING/RESOLVED/CANCELLED/EXPIRED/ALL) и `cursor`. Status фильтрует **stored** status,
поэтому отстающий timer не скрывает проблему из очереди. Stable descending
`(created_at,id)` keyset, fetch limit+1; status/validity могут меняться между pages,
frozen-history guarantee нет. Cursor — existing bounded base64url JSON ≤1024chars:
`v:1,endpoint:ESCALATIONS,workspace_id,direction:DESC,status,created_at,id`.
Decode строгий, scope/filter совпадают с query; anchor реально существует в том же
Workspace с точным tuple, но его нынешний status не обязан оставаться прежним.
Cursor не выдаёт authority. Forged/malformed/wrong endpoint/workspace/filter/anchor
→422 INVALID_REQUEST; offset, произвольные sort/search/include не вводятся.

Response command: `{outcome:ACCEPTED|REPLAY,result:EscalationAcceptedResult}`,
как у существующего CONTROL envelope.
Saved result содержит `workspace_id,escalation_id,conversation_id,client_id`,
`receipt_id,audit_event_id`, `operation:RESOLVE|CANCEL`, `accepted_status`,
`previous_version,accepted_version,accepted_context_version,control_generation`,
`accepted_at`. Все значения неизменны после commit; accepted_version=2 и
accepted_context_version=expected_context_version+1. Result не содержит новой
Message/Outbox, текущих clocks или editable answer copy. Owner читает exact
сохранённый answer в detail, если нужна reconciliation своего решения.

| HTTP / error envelope `{"error":{"code":...}}` | Условие |
|---|---|
| 401 SESSION_REQUIRED;403 ACCESS_DENIED | Прежняя session/live OWNER граница; resolve чужого assignee также403 |
| 403 ORIGIN_DENIED/CSRF_REJECTED;413 BODY_TOO_LARGE;415 UNSUPPORTED_MEDIA_TYPE;429 RATE_LIMITED | Прежние auth errors/Retry-After, без нового обхода |
| 404 NOT_FOUND | Canonical tenant/Client/Conversation/Escalation relation не совпала |
| 422 INVALID_REQUEST | DTO/query/key/header/cursor/body validation |
| 409 IDEMPOTENCY_KEY_CONFLICT | Существующий workspace namespace/key имеет другой exact fingerprint/actor/operation |
| 409 STALE_STATE | После locks не совпали expected lifecycle/context/control или request уже material-incompatible |
| 409 ESCALATION_EXPIRED | Stored EXPIRED либо current PENDING уже достиг expires_at |
| 409 ESCALATION_FINAL | Новый key для stored RESOLVED/CANCELLED; terminal не переоткрывается |
| 409 VERSION_EXHAUSTED | Невозможен допустимый bounded increment; ни half-commit, ни wraparound |
| 503 UNAVAILABLE | DB/lock/invariant/service failure; не расширять definitely-unsent или считать command rejected после неизвестного commit |
| 500 INTERNAL_ERROR | Прежний sanitized unexpected-error envelope; никаких SQL/body/token details |

Порядок после session/live owner, validation, key lock и relation proof: exact saved
receipt replay; затем current locks/state, terminal-state result, material relevance,
trusted expiry, resolve assignee policy, expected CAS, mutation. Cancel не зависит
от live assignee, но time/CAS обязательны. На любой reject отсутствуют новый receipt,
Audit, answer и изменение counters. После неизвестного ACK клиент повторяет
**тот же key/body**; после conflict/stale/expiry сначала fresh detail, никаких
автоматических новой key/новых expected versions. Старый receipt доступен на replay
только после новой live OWNER проверки, даже если с тех пор контекст уже другой.

### 14.6. Минимальная DB, receipts, Audit и capability profiles

Предложены **две** новые таблицы: `app.escalations` и
`platform.escalation_command_receipts`. Expected inventory новой schema — exact
старые36 qualified names плюс эти2, то есть38, а не проверка только count.
Первая уже является durable creation receipt через immutable origin/creation_result;
третья worker receipt table, generic action/event/notification ledger не нужны.
Owner command receipt необходим: manual/control receipts имеют другие typed shapes,
namespace, fingerprints и не могут представлять ответ по Escalation.

В `platform.messaging_jobs` добавляются nullable `escalation_id` и закрытый
`escalation_outcome`; новый kind ESCALATION_TIMER с единственным escalation reference
и steps REMIND_1/REMIND_2/EXPIRE. У timer inbox/outbox/file/turn refs NULL; connection
связан typed FK с request. Turn step ESCALATE_OWNER остаётся в старом Turn shape,
без timer reference. Расширяются точные CHECK/claim DTO/JSON/profiles/ветки lifecycle,
но не размеры lease/retry/deadlines. Existing `turn_outcome` получает только
ESCALATED/ALREADY_ESCALATED/WAITING_EXISTS сверх уже принятых outcomes;
Новый `escalation_outcome` non-null **только** при timer SUCCEEDED: REMINDED/EXPIRED/
CANCELLED/NOOP_TERMINAL. Для DEAD он NULL; точные пары DEAD/INVALID_INPUT и
DEAD/RETRY_EXHAUSTED, а также READY/RUNNING NULL shape заданы в §14.4.
У всех не-timer Jobs оба escalation поля NULL. Исторические forms
parse identically; send kind/Outbox/attempt поля и semantics не меняются.

| Relation / constraint | Минимальная DB гарантия |
|---|---|
| Escalation → source Job | `(ws,source_job_id,connection_id,source_job_kind,turn_id,turn_revision,source_job_step)` → `platform.messaging_jobs(ws,id,connection_id,kind,turn_id,turn_revision,step)`, existing `messaging_jobs_turn_receipt_key`; все поля NOT NULL, checked PROCESS_TURN/ESCALATE_OWNER literals |
| Escalation → Turn / Conversation | `(ws,turn_id,connection_id,conversation_id)` → existing `app.conversation_turns(ws,id,connection_id,conversation_id)`; `(ws,conversation_id,client_id)` → `app.conversations(ws,id,client_id)`, existing `conversations_control_client_key`; cross-Client link невозможен |
| Escalation → Resume | `(ws,resume_receipt_id,conversation_id,client_id,control_generation)` → `platform.conversation_control_receipts(ws,id,conversation_id,client_id,accepted_generation)`, existing0010 `control_guard_reference_key`. Capability и immutable-origin trigger сверяют RESUME operation, actor именно этого receipt, fence/profile; все refs NOT NULL |
| Assignee / decider / receipt actor | Request `(ws,assignee_user_account_id)` и `(ws,decided_by_user_account_id)`, receipt `(ws,actor_user_account_id)` → existing `platform.workspace_memberships(ws,user_account_id)`. Assignee и receipt actor NOT NULL; decider non-null только у owner terminal. Global user FK не заменяет этот tenant binding; live OWNER проверяется отдельно |
| Timer → Escalation | Новый supporting UNIQUE Escalation `(ws,id,connection_id)`; Job `(ws,escalation_id,connection_id)` → этот key, UNIQUE Job `(ws,escalation_id,step)`; escalation_id immutable в Job identity. Нельзя подставить connection другого Workspace/Business |
| Request uniqueness | Unique ws/Turn/namespace и source_job_id; partial unique ws/Conversation PENDING; terminal usage остаётся dedupe usage |
| Bounded list access | Два keyset indexes: `(workspace_id,status,created_at,id)` для status filter и `(workspace_id,created_at,id)` для ALL; existing Job due/lease indexes переиспользуются |
| Owner receipt → request relation | Receipt `(ws,escalation_id,conversation_id,client_id)` → новый Escalation UNIQUE `(ws,id,conversation_id,client_id)`; NOT NULL. Receipt UNIQUE `(ws,namespace,idempotency_key)`, `(ws,escalation_id)` и `(ws,audit_event_id)` |
| Owner receipt → terminal decision | Receipt `(ws,escalation_id,accepted_version,accepted_status,actor_user_account_id)` → новый Escalation UNIQUE `(ws,id,version,status,decided_by_user_account_id)`; все local поля NOT NULL. Это binding к frozen terminal row, не к текущим Conversation/Turn counters |
| Audit → Escalation | Audit `(ws,escalation_object_id)` → existing Escalation PK `(ws,id)`. Только immutable identity, без actor/version/operation в этом FK; у request нет поля или FK на Audit |
| Owner receipt → Audit | Точный binding из семи local/referenced columns и supporting UNIQUE ниже; receipt не может ссылаться на другой request/actor/version/operation/variant |
| Lifecycle shape | PENDING version1, terminal version2; resolution/closure/actor/answer/time строго по статусу; source/schedule/fingerprints immutable; due1<due2<expiry, finite timestamps; reminder slot write-once, terminal row полностью immutable |

В таблице `ws` означает ровно `workspace_id`. Все tenant FKs ON DELETE RESTRICT,
NOT DEFERRABLE; existing parent keys reused. Новые supporting keys
нужны только для указанных typed relations. CHECK с nullable полями явно использует
IS NULL/IS NOT NULL/IS TRUE. Lifecycle `version` — версия решения, не count SQL UPDATE:
reminder не инвалидирует owner CAS. Hash хранится32bytes; hex только в DTO. Request
snapshot/result нельзя менять вместе с hash, даже если computed hashes совпали.

Обе таблицы принадлежат asm_migrator, ENABLE/FORCE RLS, migrator policy; runtime
без прямых SELECT/INSERT/UPDATE/DELETE. Owner reads только через tenant/live-owner
capabilities; worker только через canonical Job/claim. Пользовательский principal
не расширяется worker grants, тестовый произвольный SET ROLE/GUC не является admission.
Штатные migration/service roles сохраняются, PUBLIC EXECUTE закрыт.

Owner namespace **`ESCALATION_DECISION_V1`** общий для resolve/cancel, UNIQUE
`(workspace_id,namespace,idempotency_key)`, actor входит в fingerprint, не в unique
scope. DB authoritative codec: UTF-8 LF-joined fixed fields в порядке
`asm:m3:escalation_decision:v1`, ws, actor, escalation, conversation, client,
operation, expected_escalation_version, expected_control_generation,
expected_context_version; затем LF и length-prefixed answer:
`<UTF8 byte length>:<exact answer>` для RESOLVE, `-1:` для CANCEL, без завершающего LF.
UUID/decimal/operation canonical; fixed fields не содержат LF. Key — lookup identity,
не часть hash. Domain/body/key/actor mismatch → conflict; replay возвращает сохранённый
result, без нового clock/version/Audit. Correlation id сохраняется как evidence,
новый retry correlation не меняет identity.

**Один новый Audit variant, policy принята C0:** `ESCALATION_DECIDED`, object_type=ESCALATION,
object_id=request id, object_version="2", actor_kind=USER_ACCOUNT, actor ID non-null;
payload ровно `{operation:RESOLVE|CANCEL,status:RESOLVED|CANCELLED}`, согласованные пары.
Answer, message content и snapshot в Audit не копируются. Два nullable generated
STORED targets: `escalation_object_id` = object_id только при object_type=ESCALATION;
`escalation_operation` = payload->>'operation' только при event_type=ESCALATION_DECIDED,
иначе NULL. Strict Audit CHECK требует весь согласованный variant, object_version=2,
оба generated targets NOT NULL для него и ровно пары RESOLVE/RESOLVED либо
CANCEL/CANCELLED. Прежние discriminator branches остаются прежними.

Точные новые связи (local и referenced порядок одинаков, **семь** полей):

| Constraint | Exact columns |
|---|---|
| Supporting UNIQUE `app.audit_events` | `(workspace_id,audit_event_id,escalation_object_id,object_version,actor_user_account_id,escalation_operation,event_type)` |
| Local FK `platform.escalation_command_receipts` | `(workspace_id,audit_event_id,escalation_id,accepted_version,actor_user_account_id,operation,audit_event_type)` |
| Referenced FK `app.audit_events` | `(workspace_id,audit_event_id,escalation_object_id,object_version,actor_user_account_id,escalation_operation,event_type)` |

Все local FK поля NOT NULL; receipt CHECK фиксирует audit_event_type=ESCALATION_DECIDED,
accepted_version=2 и `(operation,accepted_status)` ровно RESOLVE/RESOLVED или
CANCEL/CANCELLED. Saved result CHECK связывает ровно поля wire result§14.5 с receipt
columns; actor связан FK и fingerprint, нового actor field в result нет.
Answer/fingerprint точные по §14.3/6. Separate
receipt→request relation и terminal FK выше сохраняются одновременно. Один Audit
event ID принадлежит одному owner receipt; API/replay возвращает его из receipt.

Atomic write order: **terminal request UPDATE → Audit INSERT → owner receipt INSERT
→ Conversation context+1**. До Audit INSERT request уже terminal, поэтому все
немедленные FK выполнимы. Сам Audit зависит только от request identity; request
не зависит от Audit. После terminal request полностью immutable, повторный UPDATE
ради audit_event_id не нужен. Все четыре записи имеют один commit/rollback.
Creation, material cancellation, expiry/reminder не выдаются за owner Audit:
их evidence — canonical source/timer Job и immutable request/closure/slots. Это
ограниченная LOCAL/TEST policy, не заранее принятое отсутствие system Audit в M4/M9.

Strict backend union/generated OpenAPI и существующий Audit parser/label должны
быть расширены одновременно, иначе mixed page сломает уже работающую Console.
Это единственная принятая frontend дельта backend-среза: label «Решение по запросу
владельцу сохранено» и strict variant test. Нового owner-wait UI здесь нет; другие
Audit variants/payloads/labels/billing GET semantics неизменны.

Предлагаемые **11 новых SQL profiles** (схема platform; точные signatures под C2 review):

| Signature | Security / назначение |
|---|---|
| `escalation_request_for_turn(uuid,uuid)` | DEFINER; runtime EXECUTE, canonical producer admission, atomic create; terminal accepted replay до новой claim admission |
| `escalation_request_replay(uuid,uuid)` | DEFINER; runtime EXECUTE, single-statement immutable creation result по source job + winning token, включая уже закрытый request |
| `escalation_timer_execute(uuid,uuid)` | DEFINER; runtime EXECUTE, только admitted timer kind/step, current-time transition |
| `escalation_read(uuid)` | DEFINER; runtime EXECUTE, live owner/tenant detail |
| `escalation_list(integer,text,timestamptz,uuid)` | DEFINER; runtime EXECUTE, bounded count/status/anchor, live owner projection |
| `escalation_command(uuid,uuid,uuid,text,text,bigint,bigint,bigint,text)` | DEFINER; runtime EXECUTE, escalation/conversation/client/operation/key/expected version/generation/context/answer; полный owner transaction, без caller time |
| `escalation_command_fingerprint(uuid,uuid,uuid,uuid,uuid,text,bigint,bigint,bigint,text)` | Private INVOKER IMMUTABLE; codec выше, CANCEL answer=NULL допустим, поэтому не STRICT |
| `escalation_now()` | Private INVOKER VOLATILE, trusted DB clock и явный test seam§14.4 |
| `escalation_validity(uuid,uuid,timestamptz)` | Private DEFINER STABLE, только canonical read checks; при mutations caller предварительно держит нужные locks, при GET statement snapshot |
| `escalation_context_changed()` | Private DEFINER trigger, material invalidation без parent/Job lock inversion |
| `escalation_immutable()` | Private DEFINER trigger, immutable origin/schedule/creation result, allowed slot/lifecycle transitions и full terminal freeze; no arbitrary DML capability |

У всех owner asm_migrator и `search_path=pg_catalog,pg_temp`, PUBLIC EXECUTE revoked;
private пять profiles также без asm_runtime EXECUTE. Request hash считается внутри
creation capability, отдельный hash helper не нужен. Existing function bodies
заменяются только в новой migration: enqueue, guard prepare/accept/current gate,
Job JSON/guard/admit, claim/preflight/supersede/retry/reschedule/recovery. Legacy
turn_execute allowlist сохраняется; требуется actual negative на новый step.
SQL signatures/прежние grants не расширяются произвольным JSON dispatcher.
Действующие scanner signatures — `messaging_claim(text,timestamptz,timestamptz,uuid)`
и `messaging_recover_expired(timestamptz,timestamptz,uuid)`. Старые `(text)`/`(integer)`
удалены upgrade0008; snapshots ORIGINAL и их восстановление внутри downgrade не
являются final0010 capabilities. R2 не создаёт их, не добавляет grants/filters или
tests с вызовом несуществующих функций; существующий `to_regprocedure` NULL assertion
в `test_m3_1_migrations.py` сохраняется. Source anchors:0008:776–779,1033–1052;
0010:637–654; test:610–633. Это source tracing, не новый actual DB run.

**Scoped ordinary fixture cleanup:** owner receipts → только Escalation Audit events
→ timer Jobs → Escalation requests → прежние source/CONTROL parents. Весь новый prefix
выполняется в already-allowlisted `test_m3_1_control_postgres.py::control` / новых
Escalation fixtures **до** их existing cleanup и delegated Telegram/M2 teardown.
Source/CONTROL rows ещё существуют при удалении request. Runtime историю не удаляет;
обычная уборка test tenant следует только после доказанного migration refusal,
не делает used schema «unused» ради downgrade. CASCADE, disable constraints/triggers
и обнуление immutable fields запрещены. Для M1 explicit TRUNCATE учитывает полную
FK closure, включая Audit/timer/source parents, с прежними assertions.

### 14.7. Общий lock graph, atomicity и потеря ACK

Все новые mutations — READ COMMITTED, существующие statement5s/lock2s limits;
никакого HTTP/S3/LLM внутри transaction. Generation/context/revision/role/time
читаются заново после последнего ожидаемого lock. Immutable refs можно читать
до locks только для определения цепочки, но не для authority decision.

| Caller | Порядок относительно существующих CONTROL/manual/GUARDS |
|---|---|
| Owner resolve/cancel | Existing session + Workspace/User/Membership SHARE → command namespace/key advisory → canonical relation proof/replay → Conversation NO KEY UPDATE → Escalation NO KEY UPDATE → terminal UPDATE → Audit INSERT → receipt INSERT → context+1. Terminal UPDATE может усилить own Escalation lock из-за terminal supporting key; parent/Job locks после него не добавляются. Business/connection/billing locks не нужны |
| Create ESCALATE_OWNER | Own Job UPDATE → Resume actor Workspace/User/Membership SHARE → Business SHARE → connection SHARE → существующая billing chain§12.7 → Conversation NO KEY UPDATE → existing pending Escalation, если есть, NO KEY UPDATE → own Turn NO KEY UPDATE → insert request/new timer rows/own Job completion |
| Timer execute | Own Job UPDATE → assigned Workspace/User/Membership SHARE (existing rows даже при denial) → Conversation NO KEY UPDATE → Escalation NO KEY UPDATE; нет connection/billing/network зависимости. Turn revision читается под Conversation serialization без отдельного Turn lock |
| CONTROL / manual | Прежние parent/key/connection/Telegram/billing locks§12.7 → Conversation NO KEY UPDATE → новый trigger берёт только pending Escalation. CONTROL по-прежнему не блокирует Turn/старые Jobs; manual context +1 и generation +1 неизменны |
| PROCESS_INBOX / file / send finalize | Прежние own Job/Inbox/connection либо FileObject/intents либо Outbox → Conversation → pending Escalation через material trigger → прежний Turn lock, где он был. Trigger не возвращается к предыдущим locks |
| GUARDS accept/begin | Прежние Job/(Outbox)/authority/business/connection/billing → Conversation → read-only pending-Escalation check → own Turn. Никакого Escalation→Job/Outbox или Turn→Conversation пути |
| Claim/recovery/exhaustion | Existing bounded single-candidate SAVEPOINT/NOWAIT scan: own Job → assigned Workspace/User/Membership SHARE/NOWAIT → Conversation NO KEY UPDATE/NOWAIT → Escalation NO KEY UPDATE/NOWAIT. Затем trusted moment/due/relevance и лишь затем inner cleanup subtransaction§14.4. BUSY откатывает весь candidate, включая Job/authority locks, и двигает scan |

Conversation — общий serial barrier всех child transitions. Ни один caller не
блокирует existing Escalation до Conversation, ни одна domain mutation не берёт
existing Job после Conversation. INSERT трёх **новых** timer Jobs и обновление
уже заблокированного own Job разрешены. FK KEY SHARE совместим с NO KEY UPDATE;
FOR UPDATE на Conversation «на всякий случай» не вводится. Across Conversations
нет global escalation mutex; workspace/key lock связывает только совпадающий key.

Предварительный список кандидатов claim использует старый indexed available_at
и bounded cutoff. Действующий four-argument claim проверяет timer due через
escalation_now **до attempt_count, first_started_at и exhaustion/cleanup mutations**;
ещё не due → BUSY/полный candidate rollback. Due взят из immutable request schedule
по canonical step; момент получен после всех authority/Conversation/Escalation locks.
Three-argument recovery и reschedule/exhaustion соблюдают тот же preflight/due/order;
STABLE validity читает уже locked state и не берёт новые authority locks. Общие
lease/retry clocks прежние, expired lease не становится admitted execution.
Это сохраняет correctness и при test clock. В deterministic PG cases clock anchor
выбирается в прошлом так, чтобы все synthetic milestones были до wall-clock cutoff;
runtime index/lease clock и очередь не подменяются тестовым selector. Фиксированный
clock переставляется между before/equal/after steps, а реальные lock barriers
доказывают, что command перечитывает время после ожидания. Source helper после теста
восстановлен; такой test не выдаётся за реальный десятиминутный elapsed run.

Atomic create включает context increment, request/creation_result/fingerprints,
все3 timers и consumer terminal. Failure на любой записи/commit оставляет всё
прежним. После неизвестного create ACK сначала `escalation_request_replay` с теми
же job/winning token: она требует terminal source Job с правильным outcome и
typed request binding, возвращает **immutable creation_result**, даже если request
уже RESOLVED. Отсутствие receipt не считается успехом: новый attempt только через
штатный claim/reclaim и полную relevance, не прямое повторное INSERT. Old token
не становится действующим из-за dedupe. Lifetime token/lease не требуются только
для чтения доказанного ранее committed результата.

Private strict `EscalationCreationResult`: `code=ESCALATED`, workspace/source_job/
escalation/conversation/client/turn/resume UUIDs, source Turn revision, input context,
waiting context, control generation, context/request fingerprints, initial_version=1,
initial_status=PENDING, created/due/second_reminder/expiry timestamps. Это saved
acceptance, не `EscalationView`; claim token не возвращается в owner API. Private
progress хранит typed outcome и canonical source job/Turn/request ID (последний
nullable только при отказе без request); timer result — own job/request/step/status/
error_code/outcome и реально записанный slot/terminal timestamp либо NULL. DEAD не
выдумывает domain timestamp/outcome; shapes точно по §14.4. Все parsing branches
extra=forbid, не raw dict.

Owner resolve/cancel сначала UPDATE terminal/answer, затем INSERT typed Audit,
затем INSERT receipt, последним context+1 — одним commit, немедленные FK§14.6.
Same-key/same-body concurrent calls получают
один accepted result/replay; same-key/different-body конфликтуют. Два разных keys
с одной expected version: первый accepted, второй FINAL/STALE, только один Audit
и одна смена context. Исключение перед commit откатывает все четыре части.
After-commit ACK loss → exact replay, не новое действие. Этим API не создаётся
внешний эффект, поэтому нет новой отправочной семантики UNKNOWN; сохранённые
M2/GUARDS UNKNOWN/attempts/no-resend не меняются.

Resolve/expiry: при now==expiry любой ещё не принятый resolve отклоняется, даже
если timer job не claimed. Если resolve получил lock и проверил time<expiry первым,
он может commit уже после wall deadline: это принятый до срока linearization point,
timer затем NOOP. Если timer первым зафиксировал EXPIRED, resolve получает409.
Material/owner revoke против команды/таймера проверяются через наблюдённые PG waits,
не тест «повезло с порядком coroutine». Role revoke after accepted commit не стирает
Audit/answer; последующий replay всё равно требует текущий OWNER.

### 14.8. Migration и exact source/schema compatibility от0010

Нужна одна новая migration **E**. Рекомендация C2 **`0011_escalations.py`,
revision0011/down_revision0010** принята C0 в R2 как кандидат. Окончательное
назначение revision/filename и write permission будут в отдельной выдаче кода
после приёмки R2; сейчас DDL не создаётся и номер самостоятельно не резервируется.
Applied0001–0010 immutable. Только новая migration добавляет две tables, typed
keys/checks/trigger/Audit delta и перечисленные capability replacements. Новых
enum extensions общего назначения, dependences/locks или seed бизнес-данных нет.

Upgrade под drained API/worker/**scheduler** сохраняет все36 таблиц старого
column projection: rows/IDs/versions/control modes/fences, command/consumer/guard
receipts и exact fingerprints/results, PENDING/UNKNOWN/outbound attempts, files/
private objects/grants. Новые nullable Job fields NULL; escalation tables пусты.
Ни backfill requests, ни marker reprocess, ни jobs для history не создаются.
Повторный upgrade E — no-op. Code readiness/provisioning принимает ровно E:
old0010 source/E и E source/0010 дают отказ, до runtime claim/seed.

Downgrade E→0010 разрешён лишь на неиспользованной новой семантике. Первое действие
под migration locks — refusal при любой Escalation/decision receipt, новом timer
kind/ESCALATE_OWNER step/outcome/reference или новом Audit variant, включая terminal
rows. Никакого удаления истории ради downgrade. При отсутствии usage удаляется
только новая дельта и восстанавливаются **точные**0010 function/check/grant/trigger
definitions; full36-table projection совпадает, existing GUARDS/CONTROL usage сама
по себе не запрещает этот обратный шаг. Downgrade0010 не вызывается заодно.
После usage требуется forward recovery/fix; не старый image поверх E.

Compatibility source **G** = accepted main
`c502d5fd258aef15bb5549e1529df8d038a4fb9b` / schema0010; будущий reviewed **E** source
будет pinned отдельно. Текущие historical H/0007, T/0008, C/0009 и G/0010 proofs
нельзя переименовать в новый source. В existing normal/exact Docker29 state lanes
понадобится одна отдельная G→E phase: seed genuine G runtime/0010, drain, migrate,
fresh actual-revision observer при ACK loss, E readiness/restart/request/API,
unused reverse и used refusal. Сравнение36 projection, exact38 names, private S3
preservation и retained UNKNOWN/no-resend; не новый fault matrix/CI job.

В E phase terminal request сохраняет будущие timer Jobs до их due/lazy NOOP.
После остановки API/worker/scheduler fresh drain observer может допустить **только**
ожидаемый retained набор по canonical workspace/request/job IDs из committed
creation result/DB relation, kind=ESCALATION_TIMER, steps REMIND_1/REMIND_2/EXPIRE.
Для каждого remaining Job проверяются точные connection/request refs, saved
available_at/due, status=READY, отсутствие claim/lease/worker; request terminal.
Сравнивается полный набор remaining READY/RUNNING, а не count или общий kind filter:
другой/extra Job, RUNNING timer или неканонический ref остаётся blocker. IDs таймеров
читаются из DB после genuine creation; owner DTO ради controller не расширяется.
Прежние drain/claim/recovery guards для всех остальных Jobs и остановка трёх
процессов сохраняются. Нельзя удалять future Jobs, сдвигать due/часы или исполнять
их досрочно ради пустой очереди. E readiness, persisted timer identities/schedule
и restart проверяются отдельно от frozen G/0010 proof на **G source**. No-effect
restart в asm_local не выдаётся за пройденный десятиминутный timer lifecycle;
before/equal/after runtime proofs остаются в serial disposable asm_test§14.4.

Это **конкретная причина будущего адресного C6/C0 review** controller paths§14.10:
latest candidate уже не0010, а retained G phase должна остаться на G source/0010.
Default candidate egress fixture получает exact E/38 отдельно от frozen G/36;
старые source/image/pin/recovery guards остаются строгими, arbitrary-head или
intersection-of-tables не допускается. Новые SOURCE pins только если конкретный
source delta этого требует и C0 согласует exact diff; никакого второго допустимого
hash/normalization/guard bypass. Сейчас controller и pin values не меняются.

Остаются9 existing jobs, clean-source gates/artifacts, exact Docker29, prepare600s,
cleanup90s, state25min, foundation40min, browser25min. Прежняя historical строка
§13.7 о foundation35min не переписывается: текущая принятая workflow уже40min.
Укладываемость G→E **не измерена**; при нехватке бюджета предъявить timings и
конкретный узкий diff C0, не увеличивать лимит и не отключать retained phase.
CI optimization DEFERRED до завершения M3; IMPL-05 OPEN/fix DEFERRED. Никаких VM,
live Telegram, working DB/S3 или rollout действий этот migration proposal не выдаёт.

### 14.9. Компактная матрица будущих actual proofs

Все runtime rows ниже **PLANNED / NOT RUN**, не PASS контрактного head.
Один bounded набор новых tests использует реальные owner services/API, PostgreSQL,
обычный claim/worker/scheduler и счётчики adapter. Unit clock/DTO tests не заменяют
actual PG; mocks не доказывают locks/recovery. Новый внешней-effect harness не нужен:
Escalation не имеет outbound transport. Retained M2 wire/PG/S3/relay/no-resend и
CONTROL suites запускаются штатно без дублирования всех их сценариев.

| Contract / критерий | Actual boundary | Минимальные assertions |
|---|---|---|
| §14.2 create, M3-A09 | Fresh OWNER Resume → trusted CONTROLLED marker Inbox/Turn → normal worker, ни одной inserted fixture Escalation | Один PENDING request, exact origin/assignee/hash/context+1,3 unique timers, consumer terminal; CALL/EFFECT=0, Message history содержит только inbound; non-marker по-прежнему GUARDS CALL1/EFFECT1 |
| §14.2 authority/routing, A03/A04/A09 | Genuine new claims через legacy/новые capabilities; spoofed refs/token/context, TELEGRAM/PROD/legacy/HUMAN/pre-fence variants | Wrong kind/step/tenant/Client/Turn/Resume/ref/claim отказ до mutation; current admission только normal path; DB+Python gates независимы; no fake Owner |
| §14.2/3 dedupe, A09 | Concurrent inbox duplicate + request workers/reclaimed token + повторное enqueue/late-file revision | Один accepted request или один guard intent на Turn; no second request после terminal,3 timer identities всего; changed canonical binding не маскируется dedupe; old GUARDED_TEXT marker job не создаёт второй effect |
| §14.3/7 rollback/ACK, A07/A09 | Fail each request/timer/Audit/receipt/terminal write и commit; fresh runtime reader после lost ACK | All-or-nothing; creation canonical result прежний даже после resolve; exact owner replay без новой версии/Audit; другой answer/key namespace конфликт; нет speculative success |
| §14.3/5 resolve/cancel, A09 | Real authenticated HTTP → service → runtime capability, billing/connection unavailable | Exact internal answer сохранён; no Message/Outbox/Resume; context+1/lifecycle1→2; другой OWNER resolve403, cancel200; channel/billing не запрашивались; live caller revoke403 без accepted rows |
| §14.4 material, A03/A04/A05/A09 | Real PROCESS_INBOX, manual acceptance, file finalization, delivery terminal, Takeover/Resume | Pending cancellation в том же commit, одна прежняя counter delta; duplicate/replay/IGNORED/reminder без cancellation; no stale/new-client answer; HUMAN остаётся HUMAN, manual доступен |
| §14.4/7 timer boundaries, A09 | Deterministic private clock before/equal/after + реальные PG wait barriers | now==expiry deny даже при остановленном scheduler; lock loser перечитывает часы/роль/context; no reminder после expiry/material/cancel; нет недоказанного sleep-order |
| §14.4 restart/reclaim, A09 | Отдельный worker process завершается до/после slot commit, свежие worker/scheduler; реальные PG Jobs | До commit slot пустой, после commit ровно1; stale token без writes; два slots максимум; future timer после terminal NOOP; retained due/expiry не сдвинулись; dead/exhaustion видимы |
| §14.4/6/7 failure branch, A09 | Один bounded actual-PG case через normal timer execution и recovery/exhaustion; targeted stricter CHECK того же имени в disposable asm_test, восстановленный в finally | Реальная23514 с точными diagnostics → committed DEAD/INVALID_INPUT/NULL; прежние request/slots/context/control. До expiry current wait сохраняется с FAILED maintenance, при expiry waiting=NULL/actions=false с прежним reason priority; обычный exhaustion отдельно DEAD/RETRY_EXHAUSTED/NULL; successful cleanup SUCCEEDED с фактическим outcome. Fresh scanner больше не выбирает DEAD Job; ошибка вне allowlist/BUSY/отмена/failed commit не считаются durable DEAD. Clock replacement committed/VOLATILE, exact restore/catalog check у живого parent |
| §14.7 concurrency/fairness, A09 | Две owner команды разных keys; resolve vs expiry; cancel vs reminder; blocked Conv плюс здоровая | Один terminal outcome/Audit; counter consistency; request другого Conversation продвигается; NOWAIT rollback не удерживает candidate Job; complete lock graph не содержит обратного edge |
| §14.5 API/isolation, A07/A09 | Real cookie/Origin/CSRF/OWNER, strict JSON/OpenAPI, page cursor и same-tenant wrong Client | No cross-tenant/relation leak; errors точны; duplicate/extra/wrong type reject; same-key timeout replay; status/validity/receipt различены; bounded pagination и смена status anchor не ломают следующую страницу |
| §14.6 security/Audit, A09/A11 | Runtime/migrator grants + actual pg_proc/FK negatives; existing mixed Audit API/parser | Exact38 tables/11 new profiles, RLS FORCE/no raw DML; typed actor/object/version/operation/FK reject подстановок; старые5 variants + ESCALATION_DECIDED читаются вместе; старые labels/values прежние |
| §14.3/6/7 owner binding/cleanup, A09/A11 | Один адресный actual-PG owner transition → Audit → receipt; отрицательные FK probes и ordinary fixture teardown | Полный terminal/relation/Audit binding; wrong request/version/status/actor/operation/event ID/type и чужой membership отвергнуты, SQLSTATE и имя FK/CHECK зафиксированы. Rollback оставляет прежний snapshot. Receipt→Esc Audit→timer Jobs→request→old parents удаляются без CASCADE/disable/nulling; used-refusal proof выполнен до уборки |
| §14.7 actual scan, A09 | Four-argument claim/three-argument recovery, private clock before/equal/after и PG lock barriers | Not-due не меняет attempt_count/first_started_at; assignee locks до Conversation, trusted moment после locks; BUSY полностью освобождает candidate. Existing NULL assertions для удалённых overloads сохранены, новых вызовов legacy нет |
| §14.8 migration, A11 | Actual E migration role + genuine G/0010/E source readiness; clean/repeat/populated/refusal/ACK/restart | Old36 projection/fingerprints/private S3/UNKNOWN сохранены; no history jobs; unused reverse точный; каждый used blocker отказывает до DDL; mismatched source/schema STOP. E residual timers только по exact canonical ID/kind/step set§14.8, без форсирования due; frozen G proof остаётся на G source |
| Final implementation gates, A12 | `sh scripts/ci.sh`, `sh scripts/test_browser.sh`, все9 jobs/clean gates, archives и actual tested SHA/parents | Не заменять продуктовые проверки unit mocks; final reviewed integration SHA CI и независимый scoped C8 обязательны до приёмки C0; C3 сам VERIFIED не объявляет |

Future C5 owner-wait часть A10 получает только после принятого backend/API SHA:
очередь с причиной/ответственным/сроком, detail текущего Client/context, internal
answer/cancel, revoked/stale/expired states, same-key ACK recovery и видимые reminders.
UI не называется готовым из-за new Audit label и не переносит answer в manual composer
автоматически. Native/provenance часть A03/A08 остаётся NOT VERIFIED.

### 14.10. Предлагаемый exact implementation allowlist — пока без write permission

Один working vertical slice в этой же ветке/PR: после contract acceptance C0
назначает revision/paths → domain/schema/normal workers + owner API/compatibility
→ actual tests/CI/C8 → C0 intake. Отдельного DDL-only результата с неиспользуемым
сервисом не предлагается. Следующая UI часть A10 остаётся прежней отдельной выдачей
C5 в M3.2, не новым milestone. Таблица — максимум **40 paths** будущего scope,
не требование менять каждый path и не разрешение писать сейчас. Единственное
расширение списка в R2 — `tests/test_m1_3_postgres.py` по C1-M3-ESC-01/C0.

| Exact path(s) | Единственная причина будущей дельты |
|---|---|
| `migrations/versions/0011_escalations.py` | Кандидат E, revision0011/down0010, принят C0 как рекомендация§14.8; окончательное назначение/write permission ещё не выданы |
| `backend/src/asm/conversations/escalations.py` (новый) | Domain lifecycle DTOs/services/permissions; real request_for_turn и local owner decision, не generic workflow engine |
| `backend/src/asm/conversations/escalation_http.py`, `backend/src/asm/conversations/escalation_http_models.py` (новые) | Четыре routes/strict wire/cursors/errors, receipt vs current projection |
| `backend/src/asm/messaging/database.py`, `backend/src/asm/messaging/worker.py`, `backend/src/asm/messaging/results.py` | Typed request/replay/timer entrypoints, нормальные new step/kind claims/routing; прежние send/recovery bounds сохранены |
| `backend/src/asm/tenancy/database.py` | Только owner UOW wrappers для escalation read/list/command; прежний user-only context не расширять |
| `backend/src/asm/foundation.py` | Install new routes и exact E readiness; без нового env/config/runtime role |
| `backend/src/asm/telegram/provisioning.py` | Только exact E schema gate, не новый provisioning или live setup |
| `backend/src/asm/billing/models.py`, `contracts/openapi.json` | Один strict ESCALATION_DECIDED Audit variant + generated новый API; старые billing/CONTROL/manual DTOs неизменны |
| `frontend/src/billing-api.ts`, `frontend/src/billing-api.test.ts`, `frontend/src/BillingPanel.tsx`, `frontend/src/BillingPanel.test.tsx` | Только mixed Audit parser/type/label/compatibility tests; никакого Escalation UI/новых consumers |
| `tests/test_m3_2_escalations.py` (новый) | Domain/DTO/codec/errors/permission/public schema, clock cleanup и negative scopes |
| `tests/test_m3_2_escalations_postgres.py` (новый) | Normal producer/worker/Jobs/locks/rollback/restart/time/fencing/exhaustion matrix§14.9 |
| `tests/test_m3_2_escalations_api_postgres.py` (новый) | Actual owner API/session/CAS/idempotency/cursors/isolation/mixed Audit |
| `tests/test_m3_2_escalations_migrations.py` (новый) | E/G clean/repeat/populated/refusal, exact definitions/projection, source readiness |
| `tests/test_foundation.py`, `tests/test_m2_3_setup.py`, `tests/test_postgres.py`, `tests/test_tenancy_postgres.py`, `tests/test_m2_3_schema_postgres.py` | Только latest E revision/exact38 names/profiles; frozen historical inventories не переписываются |
| `tests/test_m1_3_postgres.py` | Только актуальная exact physical projection/default assertions и typed keys `app.audit_events` для новых generated Escalation targets из §14.6; прежние M1/M2/CONTROL columns/defaults/FKs/grants и все остальные assertions сохранить. Не заменять full comparison count/subset/skip. |
| `tests/test_m3_1_guards_postgres.py`, `tests/test_m3_1_control_postgres.py` | Узкие pending-wait/marker mutual-exclusion/material compatibility assertions; в `control` wrapper весь новый receipt→Esc Audit→timer→request cleanup prefix§14.6 до old CONTROL/Telegram/M2 teardown; old accepted behavior прежнее |
| `tests/test_m3_1_migrations.py`, `tests/test_m3_1_control_migrations.py`, `tests/test_m3_1_guards_migrations.py` | Только latest-head fixture/cycle restoration plumbing; exact frozen T/C/G contracts и predecessor data projections сохранены |
| `tests/test_m1_3_c0_acceptance.py` | Explicit полная FK closure в existing TRUNCATE, включая новые receipt/Audit/timer/request связи и прежние source parents; без CASCADE/ослабления M1 assertions |
| `tests/test_telegram_egress_postgres.py` | Latest E source/schema inventory/default fixture и retained frozen G semantics, без повторения wire suite |
| `scripts/prepare_telegram_egress.py`, `scripts/test_telegram_egress.sh`, `scripts/test_telegram_egress_migration.sh`, `tests/test_telegram_egress.py`, `tests/test_telegram_egress_migration.py` | Только exact G→E phase/inventory/source pairing§14.8 после адресного C6/C0 diff review; без оптимизации/lifecycle/recovery guard redesign |
| `docs/tasks/M3_CONTRACT.md`, `docs/runbooks/M2_TELEGRAM_LOCAL_TEST.md` | Принятое дополнение/evidence и локальная E/G readiness/recovery инструкция; SHA/CI в одном PR receipt |

Все остальные paths — отдельный конкретный diff C0 **до записи**. В частности,
AGENTS/canon/TASK_REGISTER/M3_HANDOFF, applied migrations, dependencies/locks,
Compose/images/workflows/runners, auth.v1/tenancy.v1, CONTROL UI/API и Telegram
client/transport не входят. `tests/test_m2_1_postgres.py` не добавляется: выбран
cleanup prefix в разрешённом wrapper. Если он невыполним, сначала dependency/diff C0.
Текущий R2 task разрешает редактирование **только §14** с побайтным сохранением prefix.
Изменённые старые fixtures/assertions объясняются конкретным FK/new-kind/head
поведением, не желанием получить зелёный CI. Skip/xfail/понижение actual checks,
подмена источника/schema/часов в неуказанных tests и widening guards запрещены.

### 14.11. Принятые policy, DB mechanics на review и возврат C0

Основание статусов — [C0 R2/disposition C1/C2](https://github.com/Elefesys/ai-service-manager/pull/31#issuecomment-6145970644).
LOCKED ниже относится только к выбранной LOCAL/TEST policy; весь implementation
ещё не выдан. Production OPEN-082/083/085 остаются OPEN.

| Решение / статус | Принятый ответ или оставшаяся проверка |
|---|---|
| ESC-PRODUCER-01 — LOCKED C0, LOCAL/TEST | Exact finite CONTROLLED marker в normal Turn → ESCALATE_OWNER; lifetime exclusion GUARDS/Escalation по Turn; historical winning replay сохранён |
| ESC-OWNER-01 — LOCKED C0, LOCAL/TEST | Immutable assignee=live Resume OWNER, resolve только ему, cancel любому live Workspace OWNER; reassign/reopen вне среза |
| ESC-OUTCOME-01 — LOCKED C0, LOCAL/TEST | Exact answer1..512scalars/2048bytes — внутреннее решение без send/Approval/Resume; counters/relevance§14.3; старый Turn не оживает |
| ESC-API-01 — LOCKED C0, LOCAL/TEST | Четыре routes§14.5, прежние cookie/Origin/CSRF/live OWNER/error/CAS/replay; local read/decide без billing/channel gate |
| ESC-TIME-01 — policy LOCKED C0; mechanics REVIEW | Reminders2/5min, expiry10min. Post-lock time/DEAD projection/serial private seam§14.4/7 требуют actual proofs; production SLA/quiet hours не приняты |
| ESC-AUDIT-01 — policy LOCKED C0; FK mechanics REVIEW | Один owner ESCALATION_DECIDED +4 narrow frontend compatibility paths; system evidence Job/request только для controlled среза; точный ациклический binding§14.6 |
| ESC-DB-01 — REVIEW C0 | Две tables/38 total,11 profiles, existing Job/Turn/Resume keys, tenant membership и terminal/Audit receipt FKs; committable timer failure§14.4. Кандидат0011/down0010 принят как рекомендация, окончательное назначение/write permission после R2 |
| ESC-COMPAT-01 — REVIEW, C6 только на конкретный implementation diff | Frozen G/0010 отдельно от G→E; canonical residual timers§14.8; budget fit PLANNED/NOT RUN, guards/budgets/CI9 прежние |

| Finding C0 | R2 response / verdict boundary |
|---|---|
| C1-M3-ESC-01/P3 ACCEPTED, OPEN | §14.10 exact `test_m1_3_postgres.py`,40 future paths; cleanup в existing wrapper, не добавлен M2 test path |
| C2-M3-ESC-01/P2 ACCEPTED, OPEN | §14.3/6/7: нет domain Audit backpointer; exact terminal/relation/Audit/membership FKs; выполнимый write/cleanup order; адресный proof§14.9 |
| C2-M3-ESC-02/P2 ACCEPTED, OPEN | §14.4/5/6/7: nested cleanup rollback и exact23514/diagnostics→INVALID_INPUT, outcome=NULL; truthful projection/due/locks; bounded proof§14.9 |
| C2-M3-ESC-03/P2 NOT CONFIRMED | Upgrade0008 удаляет старые overloads; ORIGINAL/downgrade не final source. Никакого recreate/filter/grant/call; NULL assertions сохранены§14.6. «100 final signatures» из collector без DROP/downgrade tracing не принято как inventory evidence |

Три принятых finding остаются OPEN до verdict C0; C3 их сам не закрывает.
Текущий результат — **REVIEW / HOLD после публикации**, не полная приёмка Escalation
контракта и не runtime VERIFIED. Проверки этого документа: exact source ancestry,
byte prefix, один C3 path, сохранение двух C0 prep docs, diff whitespace, сверка
канона и actual dependency traces/путей. Полные local product suites для одного
proposal не запускаются. Штатный автоматический PR CI сохраняется; его status,
head/tested merge/parents/tree фиксируются в одном PR receipt, не объявляются
Escalation execution evidence. Зелёный SHA ради статистики не rerun.

C0 проверяет эти три R2 исправления → выдаёт revision/exact implementation scope
в том же PR. C1/C2 HOLD, повторный общий audit не требуется; только конкретная SQL
неоднозначность может потребовать адресной проверки. C6 — на конкретный controller
diff при implementation. C3 не выдаёт другим ролям задачи, не пишет код/DDL и не делает VM/live/
deploy/merge. M3 остаётся IN_PROGRESS, IMPL-05 OPEN/fix DEFERRED и CI optimization
DEFERRED. C5 owner-wait и независимый C8 implementation review следуют после своих
gate; их отсутствие не скрывается документационным PASS.


### 14.12. C0 implementation activation и C3 compatibility checkpoint / 2026-10-13

[Выдача C0](https://github.com/Elefesys/ai-service-manager/pull/31#issuecomment-6151237330)
принимает R2 и закрывает три design findings; legacy-overload claim NOT CONFIRMED.
Исторические формулировки§14.11 сохранены выше. Назначена migration0011/down0010,
разрешены40 paths§14.10 плюс handoff/register только для принятых фактов.
Accepted main/frozen G=c502d5fd258aef15bb5549e1529df8d038a4fb9b/0010;
implementation start65454012c0e5a2c9643bf1401d86773a5a4df29a,
tree de09e1bf435d15929059f4e7691bd1fa17c0f2a4. Start CI38430231534/attempt1
SUCCESS9/9+clean9/9 проверил merge2650c69c48c0e882317e6ca6a68cda18f26918ed,
parents main+start/tree=start. Это не runtime evidence новой Escalation.

Подготовленная implementation следует§14: две таблицы/11 profiles, нормальный
CONTROLLED producer, три durable timers, committable allowlisted failure,
четыре owner routes, strict saved receipt/current projection и additive Audit.
Applied0001–0010 и полный принятый prefix331348bytes/blob
3d2f88ddedf0ab9944db3181040abe16a7034e81 сохранены побайтно.

Actual-PG tests подготовлены для creation/commit loss, concurrent owner replay,
FK/RLS/rollback, lock waits/fairness, expiry boundaries, timer crash/reclaim/
exhaustion и schema cycles. Не выполнены локально без Docker/PG/S3 и не являются
пока proof§14.9. Focused backend91 и Audit frontend30 PASS; полный local
non-integration1113 PASS/1 FAIL на старом closed total route inventory.
`tests/test_auth_contract.py` вне allowlist: exact additive four-route diff
только предложен C0, frozen auth contract/assertions не изменены.

Пять controller paths§14.8/10 пока не включены в tracked candidate. Отдельный
proposed patch сохраняет frozen H/T/C/G, добавляет genuine G→E/38 inventory и
canonical residual3timer set. C0 организует адресный C6 по diff; budgets/pins/
CI jobs и прежние diagnostic evidence не меняются. Новых production source pins
не требуется: TelegramClient/config bytes не затронуты. Полный CI нового E,
actual state lanes, scoped C8 и приёмка C0 остаются gates. Статус исполнения
IN_PROGRESS; текущий checkpoint BLOCKED/HOLD на указанных согласованиях,
не INTEGRATED/VERIFIED. Один canonical PR31 receipt содержит SHA/tree/parents,
commands/results/proposed patches; SHA-only commits не создаются.

### 14.13. C0/C6 exact compatibility activation

[C0 continuation](https://github.com/Elefesys/ai-service-manager/pull/31#issuecomment-6161454304)
после [C6 review](https://github.com/Elefesys/ai-service-manager/pull/31#issuecomment-6161347908)
принимает corrected five-path replacement:41783bytes,
SHA256 `2c63dc567c151c8c6be0be342f98f19eb947b6f355ad43a202bd76367140b0f8`.
Он применён вместо исходного proposal78762113… от чистого373aeaf checkpoint.
G report-export failure больше не заменяет прежний shell/timeout primary:
secondary записан безопасно, private evidence retained; без прежнего failure
export становится primary. C0 принимает фактический source diff отдельно.
Route inventory diff1268bytes/hash`501b68c29f740cf57490b2129b5633db694ecde8e70e23c023773390bd060a3e`
также принят и применён; scope43 с `tests/test_auth_contract.py`, без изменения
семи auth routes/полного endpoint equality. История§14.12 сохранена.

H/T/C/G identities, Telegram production pins, applied0001–0010, prepare600/
cleanup90 и все прежние CI lanes/budgets неизменны. Source/unit review не
является actual G→E/57 PG proof. Final source9/9 CI+clean9, matrix§14.9,
timings/cleanup/archives и scoped C8 остаются обязательными gates.
Commands/results/полные SHA — один canonical PR receipt, не будущий GREEN.

### 14.14. Адресное дополнение implementation matrix

При сопоставлении§14.9 с первоначальными57 PG cases добавлен21 случай в уже
выданных `test_m3_2_escalations_postgres.py` и
`test_m3_2_escalations_api_postgres.py`: реальные CHECK failures на каждой
creation/owner write boundary; Resume и поздние file/delivery material changes;
same-Turn late-file revision до/после owner resolution с lifetime identity;
отрицательные typed terminal/Audit substitutions; allowlisted cleanup failure
через actual claim/exhaustion и recovery после реального истечения lease.
Прежний receipt-write rollback case расширен параметрами без изменения503,
full snapshot equality и retry assertions. В material-case прежние ожидания
manual/inbound/Takeover сохранены; Resume проверяет прежний generation-only bump.

78 PG cases собраны локально; collection не является execution evidence.
Controlled fault constraints и private asm_test clock восстанавливаются в finally;
LOCAL time/due, production source и reviewed five-path controller patch не меняются.
`tests/test_m3_2_escalations_migrations.py` остаётся exact reviewed dependency.
Actual результаты обоих последовательных source/CI записываются только в receipt;
для окончательного test source обязательны новые9/9 CI и clean9/9.

Первый actual runner source76ce3d6/merge8117637 выполнил650 PG PASS/8 FAIL:
семь assertions об отсутствии следующей работы получили легальный оставшийся
PROCESS_TURN/TEST_CONSUME; восьмой — старый exact tenancy function inventory.
Новая `created` fixture завершает ordinary TEST_CONSUME через normal claim/worker
до timer assertions, с bounded loop и отказом при любом другом kind/step:
нет удаления/сдвига Job или ослабления not-due/no-DEAD-retry assertions.
`tests/test_tenancy_postgres.py` получает ровно11 принятых profiles; полное equality,
M1/M2/CONTROL/GUARDS grants, owner/search_path/PUBLIC checks сохранены.
Обе G→E state lanes на этом source прошли; они не подменяют8 failures и не
переносятся как final-source GREEN. Полный rerun после содержательных fixes обязателен.

### 14.15. Actual test-query corrections после второго runner

Run38521506363 на treef55d4a9:675 PG PASS/4 FAIL; прежние восемь failures
исправлены. Все четыре новые ошибки локализованы в test queries, production
и reviewed controller не меняются. Оба late-file cases уже прошли same-Turn
revision/lifetime/timer/replay assertions, затем SELECT несуществующего `id`
из `platform.turn_guard_receipts` упал с42703; используется фактический `job_id`.
Оба typed request/status probes получили ожидаемый23503 с правильной relation,
но `pg_get_constraintdef` опустил `app` из-за search_path. Проверка REFERENCES
теперь сравнивает actual `confrelid` с schema-qualified regclass OIDs, сохраняя
SQLSTATE, diagnostic table/name, FK prefix и rollback/original-row assertions.
Это correction новых tests, не изменение принятого FK-контракта/DDL. Число cases78
и отсутствие skip/xfail прежние. Full final-source CI/clean9 и C8 ещё требуются;
второй красный run и его фактические G→E successes сохраняются в canonical receipt.


### 14.16. C8-M3-ESC-01 — page observed_at correction (R1)

[C0 PAGE-R1](https://github.com/Elefesys/ai-service-manager/pull/31#issuecomment-6164474811)
разрешает узкую correction от reviewed `c413a6f80b30fbdd12717af3f12642a5b5f785f4`.
[C8 review](https://github.com/Elefesys/ai-service-manager/pull/31#issuecomment-6164119233)
нашёл несоответствие уже принятому§14.5: page DTO/OpenAPI/service теряли общий
observed_at, особенно для empty list. Это не новое product/business решение.
Весь прежний339842-byte prefix,§14.1–14.15 и LOCKED boundaries сохранены.

Единственная SQL delta — outer JSONB result новой `platform.escalation_list`
в `_reads()` ещё не интегрированной0011/down0010: `{items,observed_at}`.
Прежний MATERIALIZED `clock` захватывает `platform.escalation_now()` один раз;
VIEW использует `clock.moment`, outer SELECT FROM clock возвращает тот же
canonical UTC moment даже при пустом items subquery. Owner/scope/status/cursor/
count guards, descending tuple order, signature/ACL/profiles и все остальные
0011 bodies/DDL не меняются. Applied0001–0010 прежние;0012 не создаётся.

Service строго проверяет closed envelope, Timestamp, row DTO/authority/filter,
limit+1 bound и clock equality всех rows, включая lookahead; invalid result →
существующий UNAVAILABLE, без empty fallback/Python clock/first-item clock.
Публичный closed EscalationPage имеет ровно items,next_cursor,observed_at;
observed_at required/non-null, Timestamp и согласован со всеми items. Pagination
по-прежнему выдаёт≤100 и cursor последнего возвращённого item. Generated OpenAPI
содержит только эту schema delta, routes и остальные schemas прежние.

Regression-first: до code fix focused unit module дал24 PASS/7 FAIL (missing
field, canonical clock rejection, generated page schema, envelope service).
После fix:31 PASS/9 integration deselected по двум разрешённым modules.
Ruff check/format, mypy60 modules, generated contract --check,11 original hashes
и diff checks проходят. Local Docker отсутствует: local HTTP/PG NOT RUN.
Новый actual-PG case собран, но collection не объявляется runtime proof.

В новом HTTP/PG case используется retained normal fixture/serial asm_test clock
с exact restore: точный empty JSON; три normal ingress/Resume/worker requests,
включая tied created_at; общий page/item moment, limit2/lookahead/descending tuple
и cursor последнего output row; следующая страница и новая empty page получают
свои DB moments. Raw HTTP fields/values проверяются независимо от DTO. Повторный
GET после expiry сохраняет raw PENDING, показывает EXPIRED validity и не пишет
expiry/context/control/Jobs/Audit/receipt/Message/Outbox: full facts equality и
adapter.calls=0. Все прежние78 PG cases/assertions сохранены; всего79, API9.

Новому source требуются штатные CI9/9+clean9/9, включая обе existing G→E/state
lanes и retained migration/reverse gates. Reviewed base CI38525189666 GREEN
не переносится. Prepare600/cleanup90/state25/foundation40/browser25, controller,
pins/dependencies/workflows/Compose и frontend прежние. Не запускать повторные
full local suites ради статистики. Final source/actual results — в едином
[C3 receipt](https://github.com/Elefesys/ai-service-manager/pull/31#issuecomment-6152762197),
без status/SHA-only commit после CI. Finding OPEN до C0/scoped C8; M3 IN_PROGRESS.


### 14.17. C0 — foundation time budget 40→45 минут

[C0 C6-M3-FOUNDATION-TIME-BUDGET](https://github.com/Elefesys/ai-service-manager/pull/31#issuecomment-6168070726)
разрешает от exact base `0dd8a3490cfccf7fb613c169f3bd5116373827fd` только
job-level `foundation.timeout-minutes: 40→45` и три coordination docs в одном
содержательном commit. Весь прежний prefix через§14.16 сохранён побайтно.
Это текущий override прежнего foundation40; исторические записи не отменяются.

PAGE-R1 CI38549789284/attempt2 BLOCKED:8 SUCCESS/1 CANCELLED, clean8/1 SKIPPED;
foundation40m19s, основной step40m13s. HTTP/reverse-proxy smoke не завершён.
Логи обеих попыток:1133 non-integration и680 PG PASS,79 Escalation
(61 domain+9 API+9 migration); это не полный GREEN и не доказательство нового source.
Пять дополнительных минут предназначены для обязательных завершающих smoke,
cleanup и clean; фиксированная длительность не обещана.

Все9 jobs, matrix/steps/conditions/clean checks, concurrency/permissions/pins,
locks/scripts/controllers/dependency и product/SQL/DTO/OpenAPI/tests прежние.
Prepare600s/cleanup90s/state25m/browser25m и остальные limits не меняются.
CI optimization/IMPL-05 fix DEFERRED. Один новый штатный PR CI на final source:
9/9 SUCCESS+clean9/9 без SKIPPED, actual foundation completion и строка
`HTTP and frontend reverse-proxy smoke passed`; source records/archives обязательны.
При failed/cancelled — конкретный BLOCKED и HOLD, без rerun/нового повышения45.
Final evidence — отдельный canonical C6 receipt, без status/SHA-only commit.
C3/C8 HOLD; C8-M3-ESC-01/P2 OPEN до scoped recheck и решения C0; M3 IN_PROGRESS.

## 15. Native provenance и material edit/delete — proposal

### 15.1. Статус, источники и границы доказательства

**Design§15 принят и интегрирован; MATERIAL implementation IN_PROGRESS / A03 NOT VERIFIED.**
[C2 R3 PASS](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6193806982),
[C0 design acceptance](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6193890730),
[C0 integration](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6194957626).
C1-PROV-01…05/C2-PROV-01…04 CLOSED **на уровне design**; это не runtime acceptance.
PR33 design head `642160d2181b9fb5d062e449a0ff603467c40e51` слит.
Implementation выдан [C0](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6195028336), порядок source checkpoint→C6→
actual candidate CI уточнён [продолжением](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6195754984).
Exact base `933ddd284ff5b77fb1aa88a4270ab0032bc499c9`, tree `d0759acb9f83ec3f3e10d9c5d1325c937c343ee7`,
schema0011; назначен successor0012/down_revision0011.0001–0011 immutable.
Branch `c3/m3-1-material`; source return и execution gaps —§15.10.
MATERIAL/M3 IN_PROGRESS, C3 HOLD после source receipt; новый PR не открыт.
Предыдущие345960 bytes этого документа, blob `e19f8c8aa82c43ec88e8873f16675d13929934e5`,
SHA256 `b53b3f9caa4af82c095cd2e4d1ac22a0bef435a5d657dacde3278498d2808302`
сохраняются точно. Native/probe/renewal/VM/live/merge/activation не выданы.

Прочитаны AGENTS/IMPL-001, original11/SOURCE_MANIFEST, Spec4.6–4.10/5.10–5.14/
18.5–18.8/24.7 (в R2 особо4.8–4.10/5.12.1), ADR019–026/121–128/180/267/272, MVP GJ-G/J, Roadmap M3,
Implementation Plan M3.1/M3.2, M2_CONTRACT§2/10, настоящий документ§6/9/12–14,
M3_HANDOFF§4.4/5/6. Принятые CONTROL/GUARDS/Escalation и Console PASS не пересматриваются.

| Уровень | Что действительно известно |
|---|---|
| DOCUMENTED | Официальные источники ниже повторно прочитаны2026-10-15; описание полей/transport, не evidence аккаунта |
| CURRENT SOURCE | Ниже указан фактический код на exact base; чтение кода/tests не новый execution PASS |
| OBSERVED ACCOUNT | В этой выдаче **NOT RUN**. Прежняя M2-приёмка text/photo/manual не доказывает native/echo/edit/delete provenance; текущий account/runtime не инспектировался |
| ACCEPTED DESIGN / SOURCE CHECKPOINT |§15 принят C0; material0012 source и доступные local checks —§15.10. Actual PG/catalog/browser NOT RUN, native/renewal вне реализации |

Официальные ссылки: [Update](https://core.telegram.org/bots/api#update),
[Message](https://core.telegram.org/bots/api#message),
[BusinessConnection](https://core.telegram.org/bots/api#businessconnection),
[BusinessMessagesDeleted](https://core.telegram.org/bots/api#businessmessagesdeleted),
[getting updates](https://core.telegram.org/bots/api#getting-updates),
[setWebhook](https://core.telegram.org/bots/api#setwebhook),
[WebhookInfo](https://core.telegram.org/bots/api#webhookinfo),
[connected business bots](https://core.telegram.org/api/bots/connected-business-bots).
Bot API описывает отдельные business/new/edit/delete updates. `from`,
`business_connection_id`, `sender_business_bot`, `edit_date`, `is_from_offline`
у Message optional; последнее помечает, в частности, implicit/scheduled отправку.
BusinessConnection связывает connection с создавшим её user. Delete содержит connection,
chat и массив message IDs, но не actor/date удаления. Webhook допускает повторы
и нарушенный порядок; update_id не бесконечный sequence. Эти факты не дают общего
causal clock с нашей Console. Отсутствие native update за finite interval означает
NOT OBSERVED, не доказательство невозможности. MTProto-поля из второй документации
не переносятся в Bot API DTO и не разрешают userbot.

### 15.2. P01 — provenance и фактическая потеря информации

Trusted binding `B` — server-configured bot после independently checked getMe,
immutable route `(TELEGRAM,bot,external_connection_id)` → Workspace/connection/Business,
`platform.telegram_connection_state.owner_user_id`, подтверждённый оператором независимо
от очередного webhook. `BusinessConnection.user.id` должен совпасть с этим Owner;
сообщение не создаёт binding. `C` — найденная по той же connection/chat Conversation,
её immutable Client/ClientIdentity. Наличие Workspace без C не даёт права на другого Client.
Native `from=Owner` не означает `ClientIdentity.external_user_id=Owner`;
получатель определяется C, не переименованием sender. Связь Telegram Owner с локальным
UserAccount тоже не выводится из одинакового имени/username.

Текущий путь: `telegram/webhook.py::WebhookBoundary` проверяет secret до parsing;
`strict_json` ограничивает тело/Unicode/duplicate keys; `normalize_update` строит11-field
projection; `TelegramIngress.ingest` вызывает SQL и возвращает ACK после commit.
SQL `telegram_ingest` создан в0007 и заменён/обёрнут в0008 для isolation/connection
barrier;0009 добавляет ingress capture через trigger.0009–0011 не добавили origin-поля
в Telegram codec. SQL fingerprint вычисляется в БД, не принимается от caller.

| Вход / поле и ограничение | CURRENT SOURCE: projection → durable результат | PROPOSED authoritative outcome / достаточное основание |
|---|---|---|
| Client text | private chat, `from.id=chat.id`, nonbot; `date/message_id/business_connection_id`, text нужны adapter, хотя общая provider-схема шире | После B и исключения approved Owner: QUEUED → canonical INBOUND Message/C; существующая identity проверяется, не rebind |
| Client photo/caption | Сохраняет один file_id по max `(width*height,width,height,file_id)`, caption и media_group_id; размеры массива/file_unique_id не сохраняются | Тот же Client predicate и B/C; один исходный FileObject. URL в caption не file source; фото ≠ image-as-document |
| Native Owner reply | Обычно `from.id=approved Owner`, chat — клиент. Normalizer может дать event.kind=UNSUPPORTED из-за sender≠chat; SQL всё равно проверяет Owner раньше unsupported | Сейчас IGNORED_NATIVE_OWNER_MESSAGE. Предлагается OWNER_CANDIDATE_ONLY: B+C+Owner equality — identity evidence, но не post-Resume/human causality; никакого Client Message/takeover |
| Own-bot echo | `sender_business_bot.id=bot` сохраняется; необязательность поля не доказывает, что всякий echo его содержит | Сейчас любой nonnull sender_business_bot → IGNORED_ECHO. V2 различает OWN_BOT, но только для exclusion/diagnostics; не SENT confirmation, не native authority |
| Другой business bot / обычный bot | sender_business_bot другого ID тоже IGNORED_ECHO; `from.is_bot` используется для UNSUPPORTED, но отдельным полем V1 не хранится | V2 OTHER_BOT/BOT_SENDER исключены из takeover и Client input; отсутствие такого update в probe — NOT OBSERVED |
| Offline/automatic | `is_from_offline` вообще не читается. Owner-shaped input → native ignored; client-shaped input может пройти как CLIENT_MESSAGE; старый fingerprint одинаков с/без этого поля | V2 true → AUTOMATIC, без takeover. Absent — отдельное MISSING, не доказательство ручного ввода. Для Client это attribution, не новая Owner authority |
| Unsupported/service/nonbusiness | Known unsupported reason обычно сворачивается в event.kind; не сохраняются raw extras/reason. Nonbusiness → receipt без tenant refs | Explicit ignored, без вымышленного Client/C. Новые типы провайдера не становятся поддержанными из-за наличия text/photo |
| Edit | Normalizer сохраняет исходную `date`, text/selected photo, IDs; edited kind устанавливается даже после unsupported predicate. `edit_date` потерян. SQL возвращает IGNORED_MESSAGE_EDITED до owner/echo branch | Только V2 typed edit + exact existing target/B/C → material policy§15.3. Это изменение содержимого, не доказательство личности редактора/takeover |
| Delete | projection содержит connection/chat/ordered IDs; не выдумывает message_id/date/from. SQL → IGNORED_MESSAGE_DELETED | V2 deletion авторитетна для scoped known target, без attribution удалившему человеку; unknown target не создаёт Client/Message |
| Delayed/duplicate | update key `(bot,update_id)`; same V1 hash возвращает receipt до route/disconnect checks; другой hash409. Новый update_id с прежним Message ID дедуплицируется позже по immutable projection | Один canonical эффект. Доставка после Resume не означает отправку после Resume. Message conflict не превращается в edit; legacy ignored не replay-ится как новая работа |

Для первых двух строк V1 normalized event сохраняется в Inbox. Worker
`messaging_process_inbox` (0008 с последующими replacements) сериализует connection,
проверяет Message/Conversation identity, создаёт Client только для нового CLIENT_MESSAGE,
планирует file и группирует Turn.§6 определяет context increment.
**Telegram ignored не равен ignored Inbox:** в текущем SQL native/echo/edit/delete
завершаются в `platform.telegram_update_receipts`, с NULL Inbox/Job. Там сохраняются
hash/kind/result/refs/received_at, **не projection и не raw update**. Поэтому даже
поле, участвовавшее в hash ignored projection, нельзя прочитать обратно из receipt.
CONTROLLED ignored, напротив, может пройти через прежний Inbox/PROCESS job.
Durable IGNORED доказывает commit выбранной V1 ветки и дедупликацию; не совершение
domain action, не наблюдение отброшенного поля, не полноту доставки Telegram.

Опорные source/tests: `backend/src/asm/telegram/{normalization,webhook,database}.py`,
`backend/src/asm/messaging/{models,database,worker}.py`, migrations0005–0011;
`tests/test_m2_3_transport.py::test_projection_exact_unicode_opaque_photo_order_and_delete_chat`,
`test_unsupported_sender_or_document_cannot_be_client_input`,
`tests/test_m2_3_db_postgres.py::test_terminal_ignored_receipts_and_lifecycle_never_create_work`,
`test_receipt_concurrent_dedupe_and_exact_conflict_precede_disconnection`,
`tests/test_m2_3_wire_postgres.py::test_real_tcp_webhook_never_acknowledges_before_durable_commit`.
Native fixture в существующем DB test использует owner-shaped sender/chat; это не
account observation настоящего исходящего Owner→Client сообщения.

### 15.3. P02 — закрытый material payload и bounded ordering

Предлагается отдельный `TelegramProjectionV2`, **не изменение NormalizedEventV1**.
Envelope содержит `codec=TELEGRAM_PROVENANCE_V2`, exact `legacy_v1` (все11 полей
Telegram projection), discriminator NEW/EDIT/DELETE/LIFECYCLE/UNSUPPORTED и закрытые
дополнения ниже. B/Workspace/Client/C/receive time/generation устанавливает сервер.
Body256KiB, typed projection64KiB, прежние Unicode/string bounds; неизвестные extras
отбрасываются. Известное поле неверного типа, explicit NULL вместо допустимого значения,
bool вместо integer, несколько известных update branches — INVALID_INPUT, не MISSING.
Исключение совместимости для уже сохранённого V1 key описано только в§15.6.

**Единая discriminator matrix.** R=обязательно, N=только NULL, O=типизированное
optional значение или NULL. Common aliases ниже не вторая независимая projection:
их значения должны точно совпадать с указанными `legacy_v1` полями.
Неприменимые legacy поля строго NULL: deleted_chat_id/IDs только DELETE;
owner_user_id/is_enabled/can_reply/lifecycle_date только LIFECYCLE; event и
sender_business_bot_id только NEW/EDIT. Required NULL поля присутствуют, не пропущены.

| Discriminator / provider branch | legacy kind / event | connection | message target / origin / content | deleted IDs / lifecycle | edited_at |
|---|---|---|---|---|---|
| NEW / business_message, включая unsupported sender/content | BUSINESS_MESSAGE / R event; kind CLIENT_MESSAGE либо UNSUPPORTED по exact V1 rules | R=external_connection_id=event.external_connection_id | R chat_id/message_id/sent_at=event.chat_id/message_id/occurred_at; R chat_type/origin/content | IDs N; owner/is_enabled/can_reply/lifecycle_date N | O из edit_date; не превращает NEW в EDIT |
| EDIT / edited_business_message | EDITED_BUSINESS_MESSAGE / R event.kind=MESSAGE_EDITED | R, те же equalities | R target/chat_type/origin/content; поддержка content определяется заново, а не по V1 kind | IDs N; lifecycle fields N | O из edit_date; отсутствие имеет ordering-смысл ниже |
| DELETE / deleted_business_messages | DELETED_BUSINESS_MESSAGES / N event | R=external_connection_id | R chat_id=deleted_chat_id; message_id/sent_at/chat_type/origin/content N | R deleted_message_ids,1…100; lifecycle fields N | N |
| LIFECYCLE / business_connection | BUSINESS_CONNECTION / N event | R=external_connection_id | Все message/target/origin/content fields N | IDs N; R owner_user_id/is_enabled/can_reply/lifecycle_date из legacy | N |
| UNSUPPORTED / нет известной business branch (NONBUSINESS) | UNSUPPORTED / N event | N | Все message/target/origin/content fields N | IDs/lifecycle N | N |

Для всех variants update_id R=legacy.update_id, bot — configured positive canonical
decimal bigint. Для message variants IDs положительные decimal bigint; sent_at/edited_at
UTC6 из provider integer seconds, не receive time. chat_type=PRIVATE либо UNSUPPORTED:
private либо другой допустимо типизированный chat.type; отсутствующий type даёт
UNSUPPORTED, неверно типизированный присутствующий type invalid. Для DELETE chat.type
не становится новым полем authority: legacy принимает только chat.id в своём positive
ID domain; автора/время удаления не синтезировать.

`origin` у NEW/EDIT имеет ровно sender_id (O=event.sender_id), sender_is_bot
TRUE/FALSE/MISSING, sender_business_bot_id (O=legacy.sender_business_bot_id), offline
TRUE/MISSING. Отсутствующий from даёт NULL/MISSING; присутствующий from требует valid
id и boolean is_bot. is_from_offline отсутствует→MISSING, присутствует→только true
(документированный True-only marker); false/NULL/другой тип invalid для fresh V2.
В остальных variants origin целиком NULL и legacy.sender_business_bot_id=NULL.

`unsupported_reason` всегда R: NONE/NONPRIVATE/BOT_SENDER/SENDER_CHAT/GUEST/
UNSUPPORTED_MEDIA/EMPTY_CONTENT/AMBIGUOUS_SENDER/NONBUSINESS. Для NEW/EDIT выбирается
первая подходящая причина в указанном порядке после NONE (NONE только если причин нет);
AMBIGUOUS_SENDER включает отсутствующий from либо sender≠chat. Для NONBUSINESS только
NONBUSINESS; DELETE/LIFECYCLE только NONE. Это причина legacy inbound eligibility,
**не доказательство автора edit и не автоматическое отрицание supported content**:
например, Owner→Client может иметь TEXT и AMBIGUOUS_SENDER, но не стать Client input.

`content` — закрытый union TEXT `{text}` (непустой exact Unicode), PHOTO
`{caption:null|string,selected_file_id,selected_unique_id:null|string}` либо UNSUPPORTED
`{reason:UNSUPPORTED_MEDIA|EMPTY_CONTENT}`. Для PHOTO выбор max(width*height,width,height,
file_id) прежний; при tie того же selected tuple разные file_unique_id дают invalid,
не first-array-wins. Caption NULL≠пустая строка. Text/photo не пересекаются; malformed
известное content поле invalid, не UNSUPPORTED. Unsupported media/пустое содержимое
не превращаются в text/photo из-за случайного text поля. Для supported variants
text/caption=legacy.event.text, selected_file_id=legacy.event.image_file_id; TEXT
требует legacy image=NULL. У unsupported сохраняется exact legacy event целиком,
но его text/file не становится usable content. Media group=legacy.event.media_group_id;
он не меняет historical Turn membership. selected_unique_id optional только PHOTO,
с bounds opaque image ID1024 codepoints/4096 bytes; не byte identity/file authority.
Connection/media-group bounds256/1024 bytes прежние. Неперечисленные поля typed DTO
запрещены. SQL/Python проверяют discriminator, все NULL/equalities и полный legacy
Telegram fingerprint, не принимают caller-computed hash.

**Canonical target:** `(Workspace,connection,provider_chat_id,provider_message_id)`.
INBOUND связывается с Message и его сохранённым provider ID; OUTBOUND — только через
valid SENT Outbox.provider_message_id и тот же Message/C. UNKNOWN/PENDING/echo/text/
близкое время не alias. Более одного lookup match — IDENTITY_CONFLICT, без first wins.
B, Business, C/Client/ClientIdentity проверяются exact composite relations. Для INBOUND
edit sender равен canonical ClientIdentity и sent_at=original provider date. Для
OUTBOUND нужен approved Owner либо sender_business_bot_id=configured bot
при exact saved SENT Outbox; другой bot не принимается как этот origin; отсутствующий original
provider timestamp не сравнивают с local intent time. Это проверка identity исходного
Message, не того, кто нажал Edit. DELETE не требует отсутствующего sender/time.
Cross-connection/chat/client/bot mismatch не имеет effects и не rebind-ит target.

Original Message body/ingest hash immutable. На provider target хранится только
bounded folded state: sticky deleted; undated_seen; max_edit_at; один content candidate
при этом максимуме либо dated_conflict; bounded source-receipt witnesses: максимум три refs (один undated и candidate
либо пара equal-date conflict); delete оставляет один собственный witness. Два distinct
contents с одинаковым max date дают conflict, хранить их общий журнал не требуется.
Равные semantic candidates могут отличаться selected_unique_id/техническим watermark;
это не material change. Source witness нужен для eventual effect, а не для утверждения
provider order. Canonical binding write-once; unknown target не создаёт Client/C/
Message/Turn/File или отдельную работу ожидания.

**Выбранное R2 правило:** любой valid undated edit (edit_date отсутствует либо меньше
его sent_at) ставит sticky undated_seen, **включая identical content**. Прежнего
undated-NOOP исключения больше нет. Цена: даже повторение того же текста с новым
update key без даты один раз скрывает пригодный current input и invalidates Turn.
Это консервативное ограничение до отдельно принятого reconciliation, не полный media
или event journal. Exact saved receipt replay ничего не меняет.

| Приоритет / вход после receipt и identity checks | Bounded transition | Current semantic результат у known Message |
|---|---|---|
| Уже deleted; любой EDIT/DELETE | Ничего; delete доминирует, его ordering fields очищены | ALREADY_DELETED;0 |
| Первый DELETE | deleted=true; candidate/max_edit_at=NULL, undated_seen/dated_conflict=false | DELETED; один APPLIED |
| Undated EDIT при не deleted | undated_seen=true; dated watermark/candidate не подменяются undated body | ORDER_UNCERTAIN; APPLIED только при первом изменении usable state; иначе ALREADY_UNCERTAIN |
| Dated EDIT ниже max_edit_at | Ничего | STALE_EDIT;0 |
| Dated EDIT выше max_edit_at (либо первый dated) | Сохранить date/candidate, dated_conflict=false; undated_seen не снимать | Если undated_seen — ORDER_UNCERTAIN и0; иначе VISIBLE supported content либо UNSUPPORTED_CONTENT, APPLIED при semantic change, иначе NOOP_CONTENT |
| Dated EDIT равен max_edit_at, тот же content, conflict=false | Только допустимый технический witness; не новая семантика | NOOP_CONTENT, либо ALREADY_UNCERTAIN при undated_seen;0 |
| Dated EDIT равен max_edit_at, distinct content | dated_conflict=true, usable candidate=NULL | ORDER_UNCERTAIN; APPLIED при входе в hidden state, иначе ALREADY_UNCERTAIN;0 |
| Уже dated_conflict, ещё EDIT с той же date | Conflict сохраняется независимо от совпадения с одним из кандидатов | ALREADY_UNCERTAIN;0 |
| Unknown target | Тот же bounded fold без semantic materialization | Всегда DEFERRED_TARGET;0 domain increments/effects/Audit |
| Поздний original / exact valid SENT binding | Recheck identity/B/C после waits, затем сравнить final folded state с canonical original до reads/grouping | Не более одного впервые применённого final fact; no-op fold0; old deferred result не переписывается |

Final current state выбирается: DELETED → ORDER_UNCERTAIN (undated_seen либо
dated_conflict) → UNSUPPORTED_CONTENT → VISIBLE. При uncertainty/unsupported нет
usable text/image; strictly newer date снимает только dated_conflict, никогда
undated_seen. Delete не resurrect-ится. Exact Unicode без trim/NFC; photo semantic
key — exact selected file_id+caption, не file_unique_id и не догадка о bytes.
Если deferred sender/date identity не совпала с authoritative original, candidate
не применяется: IDENTITY_CONFLICT binding resolution без material effect; disputed
target остаётся unbound/quarantined, trusted original не получает чужого содержания.
Конфликт не является основанием менять Client или исторический processing result.

**Один private per-target result union.** EDIT даёт одну запись; DELETE — ровно K
записей на unique IDs,1≤K≤100, в возрастающем numeric provider-ID order. Поле
`target_ordinal`=1…K связывает результат с canonical sorted unique input; исходный
ordered array, включая duplicate IDs, остаётся в fingerprint. Даже mixed known/
unknown/conflict batch имеет одну terminal запись на unique ID; duplicate ID не
второй effect. TargetResult имеет ровно ordinal/code/target_id/message_id/effect_id/
audit_event_id/previous_version/accepted_version; ordinal — integer1…100 (не bool),
refs — canonical UUID strings либо explicit NULL, versions — canonical positive decimal
strings в диапазоне bigint либо explicit NULL. Все поля обязательны; unknown keys invalid.

| code (закрытый union) | target_id / message_id | effect_id / audit_event_id | previous_version / accepted_version |
|---|---|---|---|
| APPLIED | Оба non-NULL, verified canonical binding | Оба non-NULL, один actual effect и его Audit | Оба non-NULL; accepted=previous+1 |
| NOOP_CONTENT / STALE_EDIT / ALREADY_DELETED / ALREADY_UNCERTAIN | Оба non-NULL | Оба NULL | Оба равны observed semantic version |
| DEFERRED_TARGET | target_id non-NULL, message_id NULL | Оба NULL | Оба NULL |
| IDENTITY_CONFLICT | Оба NULL; не раскрывать/не выбирать спорный Message | Оба NULL | Оба NULL |

Нет отдельного кода DEFERRED, UNORDERED_EDIT или batch APPLIED вне этого union:
ORDER_UNCERTAIN — state/reason actual APPLIED, а MATERIAL_PROCESSED — **другой уровень**
terminal Inbox§15.6. INGEST receipt immutable; terminal Inbox result immutable после
completion; eventual material effect отдельный. Поздняя binding не переписывает
DEFERRED_TARGET в старом result. Outcome refs/provider IDs не выходят в owner API;
HTTP webhook ACK не становится per-target result API.

**Photo policy C0 P-03 выбрана для ограниченного slice:** no-refetch. Замена file_id,
даже консервативно тех же bytes, применяет новую current reference с
MEDIA_REPLACED_UNAVAILABLE. Новое изображение не открывается/не анализируется и не
будет «позже автоматически загружено» этим slice; старое не выдается за новое.
Caption-only с тем же original ref сохраняет пригодный original image. TEXT→PHOTO
также unavailable; PHOTO→TEXT убирает image из current. Unsupported content скрывает
старое. Полноценный refetch потребует отдельного C0 scope (media-source/revision FK,
отказ от UNIQUE(ws,message), WINNER/late PUT/grants); приёмка всего M3 остаётся впереди.

### 15.4. P02 — increments, traces, Turn, atomicity и current read

C0 сохранил policy per-target increments/deferred folding/sticky invalidation;
ordering-норма R2 согласована C1/C2 на уровне revised design. Единица material effect — один
canonical Message. N actual changed targets одного DELETE дают context+N и revision+1
на каждый affected Turn **за batch**, не за ID; прежний принятый prefix§6 не изменён.

| Commit / logical effect | Message.version | Conversation.version | Turn.revision | control_generation/fence |
|---|---:|---:|---:|---|
| Known semantic text/caption/photo/state change | +1 target | +1 | +1 у связанного Turn |0 / прежний |
| Batch N actual changed targets | +1 каждому | +N в одной C | +1 каждому affected Turn за batch |0 / прежний |
| Original после deferred: final fact отличается от original | starts1, затем+1 | +1 original и+1 folded fact | До membership дополнительного bump нет; hidden target без membership |0 / capture original, не edit |
| Original после deferred: final fact identical | starts1 | +1 original, fold0 | Обычная grouping только original |0 / capture original |
| Unknown до binding, stale/no-op/conflict/replay |0|0|0|0 / прежний |
| Первый hidden uncertainty / повтор уже hidden uncertainty |+1 /0|+1 /0|+1 /0|0 / прежний |
| Newer ordered снимает dated uncertainty |+1|+1|+1|0 / прежний |
| Original File PENDING→READY/FAILED после edit/delete |0|+1 по§6|+1 только если file still effective, иначе0|0 / прежний |
| Watermark/witness, свой Audit/effect/receipt, echo/owner candidate |0|0|0|0 / прежний |
| Console Takeover/Resume без сообщения |0|0|0|Прежняя§12; новый fence только Resume |

**Ручные traces known target (R2-02).** Initial: original TEXT A/date0, m.version=1,
C.version=V, один existing Turn.revision=R, invalidated=false; нет других событий.
E10=B/E20=C означают dated edits at10/20; U(A/B) — undated; X — delete. S=(ΔMessage,
Δcontext,ΔTurn,material Audits/effects); в этих одиночных commits каждый actual change
даёт S=(1,1,1,1), no-op0. I=ORDER_UNCERTAIN, watermark у DELETED=NULL.

| Trace (по commits; числа — actual changes каждого шага) | Final usable state / watermark | Total S | Sticky Turn invalidated |
|---|---|---|---|
| U(A)→D10(B):1,0 | I /10; undated_seen=true |(1,1,1,1)|true|
| D10(B)→U(A):1,1 | I /10; undated_seen=true |(2,2,2,2)|true|
| U(B)→D10(B):1,0 | I /10; undated_seen=true |(1,1,1,1)|true|
| D10(B)→U(B):1,1 | I /10; undated_seen=true |(2,2,2,2)|true|
| E10(B)→E20(C):1,1 | VISIBLE C /20 |(2,2,2,2)|true|
| E20(C)→E10(B):1,0 STALE | VISIBLE C /20 |(1,1,1,1)|true|
| E10(B)→E20(A):1,1 | VISIBLE A /20 |(2,2,2,2)|true|
| E20(A)→E10(B):0 NOOP,0 STALE | VISIBLE A /20 |(0,0,0,0)|false|
| E10(B)→F10(C):1,1; либо F10(C)→E10(B):1,1 | I /10; dated_conflict=true |(2,2,2,2)|true|
| E10(B)→F10(C)→E20(A):1,1,1; обратный порядок первых двух тот же | VISIBLE A /20; dated_conflict=false |(3,3,3,3)|true|
| E20(A)→E10(B)→F10(C):0,0,0; перестановка последних двух та же | VISIBLE A /20 |(0,0,0,0)|false|
| E10(B)→same receipt replay→fresh same-date B:1,0,0 | VISIBLE B /10 |(1,1,1,1)|true|
| U(A)→fresh U(A)→D10(B):1,0,0 | I /10; undated_seen=true |(1,1,1,1)|true|
| E10(B)→X→E20(C)→fresh X:1,1,0,0 | DELETED /NULL |(2,2,2,2)|true|
| X→E10(B)→E20(C)→fresh X:1,0,0,0 | DELETED /NULL |(1,1,1,1)|true|

**Те же traces deferred до original.** Пока canonical target отсутствует, каждый
unique input получает DEFERRED_TARGET, domain S=0 (same receipt — его replay).
Затем обычный original A materializes **один** final fact до любых current reads.
Ни один промежуточный deferred candidate не публиковался. Таблица учитывает отдельно
original context+1; current Conversation может уже существовать. Для точного Turn
примера нет collecting Turn, original eligible в текущем epoch, maintenance ещё не
срабатывала: visible original создаёт fresh Turn revision1/member_count1, а hidden
не создаёт Turn. Mutation-related ΔTurn всегда0; invalidated old Turn не возникает.

| Все mutations до original A, в указанном либо обратном порядке | Final state / watermark | Final m.version / ΔC включая original | Material Audit/effect / Turn |
|---|---|---|---|
| U(A),D10(B); отдельно U(B),D10(B), оба порядка | I /10 |2 /+2|1 / отсутствует|
| E10(B),E20(C), оба порядка | VISIBLE C /20 |2 /+2|1 / fresh revision1, invalidated=false|
| E10(B),E20(A), оба порядка | VISIBLE A /20 |1 /+1|0 / fresh revision1, invalidated=false|
| E10(B),F10(C), оба порядка | I /10 |2 /+2|1 / отсутствует|
| E10(B),F10(C),E20(A), любая перестановка | VISIBLE A /20 |1 /+1|0 / fresh revision1, invalidated=false|
| E10(B),same receipt replay,fresh same-date B | VISIBLE B /10 |2 /+2|1 / fresh revision1, invalidated=false|
| U(A),fresh U(A),D10(B), любая перестановка | I /10 |2 /+2|1 / отсутствует|
| E10(B),X,E20(C),fresh X, любая перестановка | DELETED /NULL |2 /+2|1 / отсутствует; FETCH нет|

Batch trace: input IDs `[b,a,b,u]`, known visible a/b в одном existing Turn, unknown u.
Fingerprint хранит этот массив. Sorted unique results a=APPLIED,b=APPLIED,u=DEFERRED_TARGET;
m(a/b)+1, C+2, Turn+1, два Audit/effect, u0. Exact replay всё0. Поздний original u
получает m2, C+1 original+1 tombstone, один material Audit/effect, без Turn/FETCH;
old u result остаётся DEFERRED_TARGET. Если a уже deleted, batch изменяет только b:
C+1/Turn+1/Audit1. Overflow любого counter — полный rollback.

**Граница эквивалентности.** Для одинакового finite набора valid identity-consistent
updates и original гарантированы final semantic content/reference (либо hidden), max
dated watermark, delete/uncertainty flags по§15.3. Delete канонически очищает watermark.
Это не равенство Message/context/Turn counters, changed flag, effects/Audit, source
witness IDs или уже выставленного sticky Turn invalidation. Фактическое наличие/готовность
original FileObject тоже зависит от уже выполненного FETCH/suppression, не выравнивается
задним числом; current availability сообщает это отдельно. Published A→B→A не
отменяется задним числом; E20(A)→stale E10(B) не выдумывает два effects. Same receipt
replay возвращает **свой сохранённый** outcome/version, не новый current result.
Deferred source для одного final fact — first stored delete witness, иначе first
undated witness, иначе witness equal-date conflict, иначе max-date candidate receipt;
приоритет тот же, не provider chronological claim. Effect UNIQUE(source receipt,
canonical Message); original binding/final SENT создаёт effect только если этого
accepted fact ещё нет. Старые receipts/results immutable.

Turn membership/origin/captured generation/fence/deadlines не меняются. Edit не
переносит member, delete не уменьшает historical member_count, sealed не reopen.
У affected existing Turn sticky material_invalidated=true: общий readiness/enqueue/
admission body, включая turn_material, GUARDS accept/begin и Escalation producer,
после waits проверяет его под Conversation barrier. Ни revision, ни Resume, ни late
file не возвращают автоматизацию этого Turn. GROUP/MEDIA могут закончить maintenance;
следующий новый Client Message начинает другой Turn. Один edit не CLIENT_MESSAGE.
Hidden deferred original не group-ится; visible folded original использует только
свою original ingress eligibility, никогда дату/sequence edit.

**R3-02 — общие bodies для новой suppression membership.** Исключение§15.7
дополняет будущий member CHECK/validator, не меняет original Message/FK type:
PHOTO остаётся IMAGE_REFERENCE даже при effective TEXT. `turn_group_message` при
первом materialization выбирает форму INITIAL_FOLD_SUPPRESSED только по verified
immutable evidence; `turn_member_check` и `turn_members_consistent` проверяют её
same-Message/origin relation, exact count и прежние capture/deadlines. У fresh eligible
singleton revision1/member_count1; добавление к existing collecting Turn даёт
member_count+1/revision+1 ровно за grouping. Fold до membership не даёт отдельного
revision bump или invalidation этого Turn. Последующий seal сохраняет свои прежние
переходы/revision rules, не считается вторым grouping.

`turn_seal`, GROUP/MEDIA, V2 `turn_snapshot`/typed decoder и общий readiness body
оценивают **каждый member** через effective helper, включая file=NULL suppression:
effective TEXT B — usable TEXT/NOT_APPLICABLE, без media wait за original PHOTO;
effective replacement PHOTO — PARTIAL/MEDIA_REPLACED_UNAVAILABLE, без вымышленного
PENDING/FETCH. Пустой inner JOIN к file_objects не доказывает COMPLETE. WAITING_MEDIA
возможен лишь из-за реального PENDING **effective** original FileObject другого
либо обычного member, в пределах прежнего media deadline. Недоступная replacement
сама не создаёт ожидания; её caption можно использовать по согласованной current
норме. Hidden/no-usable-input и sticky invalidation продолжают блокировать consumer.

Private V2 snapshot разносит historical Message/member identity (original
content_type, origin/capture, реальный file либо NULL, проверенная member form/evidence
ref) и current usable material той же effective projection§15.4; digest покрывает
обе части и принятые semantic versions. Decoder не выводит current type/readiness из
original content_type или наличия file. Это private snapshot contract, **не новые
поля MessageResponse/current/API**. Saved V1 snapshot/digest/receipt и V1 decoder
не переписываются и новой member формой задним числом не дополняются.

Initially hidden PHOTO получает suppression evidence, но **не member/Turn/FETCH**.
Strictly newer dated edit после dated conflict может восстановить original ref:
current ORIGINAL_NOT_FETCHED/PARTIAL, без автоматической новой membership/Turn/FETCH.
При deletion/sticky undated restore по-прежнему запрещён. Evidence хранит initial
disposition независимо от mutable current, поэтому duplicate original, replay и
maintenance не переигрывают grouping и не откладывают original FETCH на потом;
ineligible original также не получает новую eligibility при повторе. Уже созданный
member остаётся immutable при следующих edits; старые generations/fence/deadlines,
sticky invalidation, FileObject/WINNER и V1 results сохраняются.

Current readiness: COMPLETE лишь при доступных используемых inputs; иначе PARTIAL
с typed reason MEDIA_REPLACED_UNAVAILABLE / ORDER_UNCERTAIN / DELETED /
UNSUPPORTED_CONTENT / ORIGINAL_NOT_FETCHED (retained media pending/failed reasons прежние).
Полностью hidden/deleted input set — NO_USABLE_INPUT, не consumer-ready. Saved V1
snapshot/readiness/digest immutable и читается прежним decoder; новый V2 snapshot,
API current view и files_read_manifest используют **одну effective projection**.
Original FileObject/WINNER/storage неизменны. Late FETCH завершает исходную работу,
сохраняет context+1 по§6, не возвращает substituted/hidden image в current.

**Accepted0011 Escalation precedence (R2-04).** Material context trigger отменяет
PENDING→CANCELLED/CONTEXT_CHANGED в том же commit, без второго context bump. Exact
winning command receipt replay возвращает прежний результат. При новом key stored
CANCELLED/RESOLVED→409 ESCALATION_FINAL; stored EXPIRED→409 ESCALATION_EXPIRED.
STALE_STATE возможен только для ещё PENDING там, где accepted порядок доходит до
validity/expected guards mismatch; существующие authority/expiry/access precedence
не меняются. Семантически неактуальный late ответ не обязательно error STALE_STATE.
Material раньше GUARDS admission —0 новых side effects; committed DISPATCHING раньше
material — прежние SENT/FAILED/UNKNOWN, без recall/resend/echo confirmation. Pending
manual intent остаётся принятой ручной операцией; новые manual/control команды
сохраняют прежние guards. Material не auto-Resume и не новый native takeover.

**Lock/atom proposal; actual PG proof ещё нет.** Webhook: update-key advisory →
connection SHARE → existing Conversation NO KEY UPDATE для capture → own receipt/
sidecar/Inbox/Job, commit до ACK. Worker: own Job UPDATE → own Inbox NO KEY UPDATE →
connection UPDATE → existing identity barrier (original) → Conversation NO KEY UPDATE
→ sorted targets → sorted Messages → sorted Turns → context/PENDING Escalation.
Provider lookup перечитать после Conversation wait; unknown chat без C держит
connection UPDATE и target, original creation использует тот же barrier. Existing
child→Conversation reverse path не вводится. Mutation не берёт File/FETCH Job/Outbox
после Conversation. File path сохраняет Job→File/upload intents→Conversation→Turn.
Claim/reclaim — прежний single-candidate NOWAIT/savepoint с rollback всех candidate
locks; не ждать target, удерживая другой Conversation. Clock/claim после waits.

Выбран stable-target вариант C2 для SENT: own Job→own Outbox UPDATE→Conversation→
**уже существующий deferred target**→sorted Message/Turn. При отсутствии deferred
candidate finalizer не создаёт target. Provider/connection key target неизменен;
меняются только write-once canonical refs и current state. Valid-SENT FK проверяет
свой Outbox либо уже terminal SENT row; exact terminal replay не возвращается к C.
Effect/Audit ссылаются на stable target/Message/immutable source receipt, **без прямого
connection FK и без FK на чужой Job**. Поэтому после C нет нового implicit KEY SHARE
на connection против worker connection UPDATE→C; target connection FK проверен при
его раннем создании и не переоценивается сменой неизменяемого key. Нет lock чужого
Inbox/Job; historical deferred source Job уже terminal. Supporting keys/FKs§15.7
обязаны сохранить этот mapping, alternative требует отдельного адресного review.
NO KEY UPDATE на C/Inbox совместим с identity-only FK KEY SHARE; это необходимая
статическая граница, не объявление PASS concurrency или отсутствия всех deadlocks.

R3-03: new suppression evidence/member relations§15.7 замыкаются на immutable
Message/target/origin/receipt/effect identity, не на mutable Message.version/current
watermark. Evidence создаётся только original INBOUND path после уже взятого
connection→Conversation barrier; sorted target→Message→Turn order сохраняется.
В stable-target actual-SENT path нет такой membership/evidence вставки, прямого
нового connection FK или foreign Job edge; общие helpers не должны добавлять их
неявно. Origin/source читаются по immutable identity, без повторного lock чужого
Job/Inbox; identity-only FK KEY SHARE совместим с принятым Inbox NO KEY UPDATE.
Это обязательство future FK/capability review, не actual concurrency PASS.

Atom и порядок immediate FK: current state/versions/Turn invalidation/context+
Escalation cancellation → INSERT typed MESSAGE_MATERIAL_CHANGED Audit → INSERT effect
→ own Inbox/Job terminal, один commit. Audit actor_kind=CHANNEL_EVENT,
actor_user_account_id=NULL; strict bounded reason CONTENT_CHANGED/DELETED/
ORDER_UNCERTAIN/ORDER_RESTORED/UNSUPPORTED_CONTENT, old/new accepted version и canonical
refs/source receipt, без текста/provider IDs. Не USER_ACCOUNT Owner. На actual changed
target один Audit/effect, для unknown/no-op0. Effect ссылается на тот же Audit/accepted
version, без FK к mutable Message.version/watermark и без обратного Audit→effect FK.
Crash before commit откатывает atom; lost ACK не удваивает его. HTTP/S3 вне transaction.

Для R3 initial suppression выбран один порядок внутри этого atom: insert original
Message/context+1 под original claim → bind/recheck deferred target и применить
один final fact (m1→2/context+1) → strict material Audit → effect → immutable
suppression evidence → grouping/member, только если evidence требует membership →
own Inbox/Job terminal → commit. Immediate evidence→effect→Audit refs уже существуют
до member INSERT. Deferred integrity check к commit проверяет disposition↔membership
и отсутствие original File/FETCH; он не откладывает authority/identity checks до
после grouping. Нарушение любой relation/overflow откатывает **весь** atom. Existing
material flow для already-known Message сохраняет порядок выше; suppression evidence
не дополнительный material effect/Audit/context bump.

**Versioned nested owner DTO (R2-05).** В paired MessageResponse добавляется обязательный
`current` ровно с полями `schema_version:1`, `state`, `content_type`, `text`,
`image_availability`, `changed`. schema_version — integer1 (не bool), changed — boolean;
все поля обязательны, unknown keys запрещены. Message.version остаётся
semantic version. changed=(Message.version>1): хотя бы один published material change,
не тест current≠original; A→B→A сохраняет true. File completion сам changed не меняет.
Original content_type/text/file/delivery остаются историческими полями; их нельзя
смешивать с current. Direction↔delivery relation прежняя. TEXT требует historical
file=NULL; PHOTO хранит фактический original FileObject, если он был создан. Узкое
новое исключение MessageResponse.relations: для PHOTO materialized сразу hidden,
заменённой либо TEXT после deferred fold historical file=NULL допустим при changed=true,
если original FETCH не создавался. Не создавать фиктивный PENDING ради старого DTO
CHECK; это paired API/TS change, не ослабление legacy/unchanged PHOTO relation.
Provider IDs/receipt internals не выдаются.

| current.state | current.content_type | current.text | current.image_availability | changed |
|---|---|---|---|---|
| VISIBLE, effective TEXT | TEXT | nonempty string,4096 codepoints/16384 bytes | NOT_APPLICABLE | m.version>1 |
| VISIBLE, effective PHOTO с тем же original ref и существующим FileObject | PHOTO | caption NULL либо string, включая пустую | ORIGINAL_PENDING / ORIGINAL_READY / ORIGINAL_FAILED по original File status | m.version>1 |
| VISIBLE, effective PHOTO с original ref, но original file не создавался из-за deferred suppression | PHOTO | caption NULL либо string | ORIGINAL_NOT_FETCHED | true |
| VISIBLE, effective PHOTO с другим ref либо original TEXT | PHOTO | caption NULL либо string | MEDIA_REPLACED_UNAVAILABLE | true |
| DELETED / ORDER_UNCERTAIN / UNSUPPORTED_CONTENT | NULL | NULL | HIDDEN | true |

Это полные enums/NULL combinations; остальные формы invalid. ORIGINAL_NOT_FETCHED
возможен, например, когда original поступил при dated conflict без FETCH, а поздний
ordered edit снял conflict. Label «исходное фото не было загружено», PARTIAL reason
ORIGINAL_NOT_FETCHED; этот slice также не запускает отложенную загрузку такого ref.
File refs берутся только из historical original, если он существует, current PHOTO
**и exact same original ref** и READY.
Current DTO не создаёт FileObject и не изображает replacement как PENDING. Hidden
states не выдают спорный text/image как usable input. Caption можно использовать у
unavailable PHOTO, но изображение отсутствует и readiness PARTIAL с указанной причиной.

| Normative example | historical fields | current (schema_version=1) |
|---|---|---|
| Unchanged PHOTO, original READY, caption NULL, m1 | IMAGE_REFERENCE/text=NULL/file READY | VISIBLE,PHOTO,NULL,ORIGINAL_READY,changed=false |
| TEXT A→PHOTO caption B, m2 | TEXT/text=A/file=NULL | VISIBLE,PHOTO,B,MEDIA_REPLACED_UNAVAILABLE,true |
| PHOTO caption A→TEXT B, m2 | IMAGE_REFERENCE/text=A/file READY | VISIBLE,TEXT,B,NOT_APPLICABLE,true |
| Любой original→DELETED, m2 | original body/file/delivery сохранены | DELETED,NULL,NULL,HIDDEN,true |
| Любой original→ORDER_UNCERTAIN, m2 | original body/file/delivery сохранены | ORDER_UNCERTAIN,NULL,NULL,HIDDEN,true |
| PHOTO same-ref caption A→B, m2 | original caption A/file READY | VISIBLE,PHOTO,B,ORIGINAL_READY,true |

UI label для MEDIA_REPLACED_UNAVAILABLE: **«фото заменено, новое изображение недоступно»**.
Replacement/type change/delete/uncertainty запрещают новый current grant на старое
изображение; late FETCH не меняет semantic state/ref и не возвращает его. Только
новый valid material transition, разрешённый ordering table, может вновь дать
VISIBLE PHOTO с exact original ref; прежний grant response этим не становится
актуальным. Sticky undated uncertainty и deletion такой transition запрещают.
Backend grant predicate, current read и context используют одну effective eligibility;
готовый historical file сам по себе недостаточен.

MessageResponse→generated OpenAPI→TS/parser/panel меняются совместно до activation;
unknown optional field не совместим с нынешним strict parser. При refresh UI сверяет
Message semantic version/current availability, очищает открытое stale image и pending
grant request; late response принимается только для всё ещё выбранных scope/message/
version и eligible current image (request token фиксирует version). Не обещается
atomic revocation URL при последующей mutation: уже выданный signed URL живёт по TTL,
а stale display до refresh не является realtime invalidation. Новых endpoints в R2 нет.

### 15.5. P03 — native intervention, causality и Resume

Строгий automatic native takeover **не доказуем на текущем Bot API контракте**:
есть две неразличимые для сервера истории — Owner отправил до Resume, update задержан;
Owner отправил после Resume, update пришёл сразу. Native сообщение не содержит нашего
control_generation/fence или ack Console Resume. Provider second-resolution time и
server clock не имеют документированной общей causal границы; update_id упорядочивает
provider updates, но Resume вообще не provider update. Локальный ingress capture
доказывает admission после fence, а не момент человеческого действия. Даже успешный
account probe не устраняет эту неразличимость и не доказывает полноту origin markers.

| Проверки в порядке приоритета | Однозначное действие |
|---|---|
| Auth/route/B/Client relation отсутствует или конфликтует | Existing reject/unsupported;0 takeover, не создать C по Owner sender |
| Same update либо тот же known native Message identity уже terminal | Replay/duplicate,0 новых Message/context/generation/Audit |
| sender_business_bot=own, или exact known outbound identity | OWN_ECHO_EXCLUDED;0 takeover; UNKNOWN остаётся UNKNOWN |
| Другой business bot / sender_is_bot true / offline true / unsupported sender_chat | BOT_OR_AUTOMATIC_EXCLUDED;0 takeover |
| `from=approved Owner`, private chat=C, origin markers absent | Выделить OWNER_CANDIDATE_ONLY и продолжить fence checks ниже;0 domain Message/context/control. Presence/absence sender_business_bot не положительная authority |
| Candidate ingress до текущего Resume fence/captured старый generation | PRE_RESUME_EXCLUDED;0 takeover даже если обработан после Resume |
| Candidate ingress после fence, provider date «новее», но нет отдельного causal proof | ORDER_UNPROVEN;0 takeover. Это включает невиденный раньше pre-Resume delayed update |
| Identity+human origin+post-Resume causal proof+first durable native effect | Был бы sufficient set: под C lock native Message/context+1 и generation+1/HUMAN/fenceNULL один раз. **На текущем API эта ветка недостижима; token/proof не изобретается и не принимается от caller** |
| Явный live OWNER Console Takeover или новый разрешённый manual intent | Existing accepted command/key/CAS/auth boundary§12; takeover по воле Owner, не по догадке о native событии |

OWNER_CANDIDATE_ONLY/PRE_RESUME_EXCLUDED/ORDER_UNPROVEN/OWN_ECHO_EXCLUDED —
диагностические classes этой таблицы, не новые TelegramReceipt result codes. Native
candidate остаётся transport IGNORED_NATIVE_OWNER_MESSAGE, echo — IGNORED_ECHO;
новая domain branch не включена. Fence refinements не меняют этот terminal receipt.

**Решение C0 P-01 для R2:** поддержанный resumable human-reply путь использует
canonical Console reply (обычный manual intent с честным delivery outcome). Candidate-only
native не создаёт human transcript. После native-only разговора операционный план
оставляет HUMAN до отдельно принятого canonical-context reconciliation. Это **не
реализованная блокировка Resume**: actual0011 проверяет authority/product/CAS, но
полноту native transcript не проверяет. Не отправлять уже доставленный native текст
повторно через Console ради наполнения истории.

Контрпример latest-state: Takeover → native «согласовали другой вариант» → Resume →
client «да». Новые generation/context counters могут быть свежими, но canonical
history не содержит согласованного варианта; новый Client Message не восстанавливает
пропущенный human ответ. Этот сценарий **не закрыт**. Для native→Resume отдельно нужен
согласованный источник canonical human context: context-only native ingestion либо
подтверждённое reconciliation, без false Client identity, фиктивного Outbox SENT и
automatic takeover по arrival. Endpoint/protocol этой capability в R2 не проектируется.

Гарантия «takeover по arrival после Resume» по-прежнему не принимается вместо causal
proof. Account observation не доказывает causality/полноту delivery. Native/latest-state
и A08 остаются обязательствами M3 и OPEN/NOT VERIFIED; уменьшение scope не скрывается
под Console PASS. LOCKED ADR026/180/267, Spec5.12.1 и MVP GJ-G/J не переписываются.
Ни native candidate, ни edit/delete не делают auto-Resume, не оживляют старый Turn,
не подтверждают UNKNOWN и не становятся Client sender identity.

### 15.6. P04 — closed V2 receipt/Inbox, codec и cutover

Один namespace `(configured bot,update_id)` для V1/V2. Receipt codec marker NULL=V1,
2=V2; old columns/hash/result/timestamps immutable. V2 имеет ровно одну immutable
bounded typed sidecar с verified same receipt/codec/bot/update/ws/connection/Inbox
binding§15.7. Raw update не сохраняется. Наличие EventKind.MESSAGE_EDITED/DELETED
без sidecar не authority новой branch; legacy CONTROLLED/Telegram V1 остаётся прежним.

**CURRENT SOURCE0005/0007, сохранённый до0011:** Telegram receipt QUEUED допускает
только kind=BUSINESS_MESSAGE и non-NULL Inbox. Inbox PROCESSED требует code
PROCESSED/DUPLICATE и non-NULL message_id; FK required_direction=INBOUND. IGNORED
имеет старый closed union. Python TelegramReceipt/InboxProcessingResult также closed.
Поэтому OUTBOUND/batch/deferred нельзя записать в старую форму и просто удалить CHECK.

| Предлагаемая ветка | Ingest receipt + sidecar | Inbox / terminal processing | Job |
|---|---|---|---|
| codec NULL V1 | Exact старые predicates; sidecar отсутствует | Exact старые normalized event/hash/status/code/INBOUND FK и decoder | Прежние outcomes |
| codec2 NEW eligible Client | kind=BUSINESS_MESSAGE,result=QUEUED, same non-NULL Inbox + verified sidecar | Прежний inbound process shape, exact V1 event/hash; новые origin exclusions проверены до queue | PROCESS_INBOX как прежде |
| codec2 EDIT/DELETE, captured A03=ON | kind=EDITED_BUSINESS_MESSAGE/DELETED_BUSINESS_MESSAGES,result=QUEUED, same non-NULL Inbox + verified typed mutation sidecar | PENDING до processing; затем status=PROCESSED,result_code=MATERIAL_PROCESSED,message_id=NULL,completed_at non-NULL; bounded per-target result§15.3 | SUCCEEDED,error_code=NULL, в том числе durable DEFERRED_TARGET/IDENTITY_CONFLICT |
| codec2 EDIT/DELETE, captured A03=OFF | Прежний IGNORED_MESSAGE_EDITED/DELETED, Inbox/Job=NULL; sidecar с gate OFF | Нет mutation worker; ON позднее не переигрывает | Нет |
| codec2 NEW excluded / LIFECYCLE | Прежний appropriate native/echo/unsupported либо LIFECYCLE_INVALIDATED, Inbox/Job=NULL; typed sidecar | Прежняя classification/lifecycle authority, не material branch | Нет |
| codec2 NONBUSINESS | IGNORED_UNSUPPORTED; workspace/connection/Inbox/Job=NULL; closed nonbusiness sidecar | Нет tenant/domain work | Нет |

Routed receipt всегда all-or-none ws/connection; unknown business binding сохраняет
прежний503/no ACK, не masquerade NONBUSINESS. EDIT Inbox.normalized_event точно
legacy.event. DELETE использует deterministic transport stub NormalizedEventV1:
provider=TELEGRAM, configured bot, event_id=update_id, kind=MESSAGE_DELETED,
external_connection_id и chat_id из delete, message_id/sender_id/occurred_at/text/
image_file_id/media_group_id=NULL. Это envelope для PROCESS_INBOX; legacy_v1.event
**остаётся NULL**, исходный ordered ID array только sidecar. Stub/event hash не
подменяет fingerprint полного Telegram update.

Новая terminal mutation ветка допускается исключительно для verified codec2 EDIT/
DELETE binding. Старый INBOUND FK остаётся; OUTBOUND и batch refs только target/effects.
Inbox получает private `material_result` (ровно bounded array TargetResult,≤100 rows,
≤64KiB), NULL в old branches/PENDING, write-once при MATERIAL_PROCESSED. Для invalid
claim/structural failure существующий failure/retry protocol; не маскировать сбой
под MATERIAL_PROCESSED. Successful durable defer — terminal transport success, не
promise eventual domain success. Terminal replay возвращает сохранённый результат;
поздний effect не переписывает этот array/receipt. SQL return и Python closed decoder
расширяются совместно отдельной MutationInboxProcessingResult:
`{code:MATERIAL_PROCESSED,status:PROCESSED,inbox_id:UUID,message_id:NULL}`.
Internal per-target details остаются private; HTTP ACK прежний.

V2 fingerprint: prefix `asm:m3:telegram_provenance:v2\n`, затем length-prefixed UTF-8
parts (NULL=`-1:\n`, длина в bytes), фиксированный порядок:
configured bot,update_id,hex(H1),
discriminator,chat_type,sender_is_bot,offline,unsupported_reason,edited_at,content_kind,
selected_unique_id,content_unsupported_reason. Последнее равно content.reason только
для UNSUPPORTED content, иначе NULL; nested origin fields для non-message variants NULL.
H1 — **full telegram_fingerprint exact legacy_v1**: SQL platform.telegram_fingerprint /
Python update_fingerprint с prefix
`asm:m2:telegram_update:v1\n`, **не только NormalizedEvent fingerprint**. Он включает
lifecycle/delete/echo fields и ordered delete IDs. Все остальные V2 common/content
values совпадают с exact legacy, поэтому уже покрыты им; V2 adds покрыты списком выше.
Enums uppercase, timestamps UTC6, NULL/MISSING/FALSE различаются; selected_unique_id
не semantic photo key, но relevant typed projection field. Shared Python/SQL vectors
проверяют полный closed shape, legacy equality и каждый fingerprint field.

| Доставка/upgrade | Обязательное поведение |
|---|---|
| Existing V1 key, V1 projection совпала | Старый receipt/result **до V2 interpretation**, независимо от новых dropped extras/gate/route; no sidecar/new marks |
| Existing V1 key, relevant V1 differs | EVENT_ID_CONFLICT409; no V2 fork/overwrite |
| Existing V2 key | Full V2 parse/hash; exact replay, иной relevant V2 field→409 даже при равном V1 subset |
| Absent key после cutover | Только V2 writer: receipt+verified sidecar+Inbox/Job либо terminal ignored атомарно |
| V1 pending | Старый decoder/process/hash/eligibility; старый edited/deleted без sidecar остаётся ignored |
| V1 completed/ignored/missed ACK | Только read/replay; no backfill origin/date, no reclassification/reprocessing |
| A03 OFF / restart / compatible rollback source | Fresh receipt всё равно V2, captured OFF terminal ignored; fresh V1 writer после cutover запрещён |
| Lost commit response |503 до доказанного commit; redelivery namespace replay, не новая операция |

Сначала auth+strict JSON+legacy normalization и narrow saved-V1 receipt probe.
Found V1 hash/result/conflict возвращается до interpretation новых V2 полей. Probe
miss **не ACK**: V2 parse → final namespace lookup под тем же update-key advisory,
включая concurrent V1/V2 result/conflict recheck. Existing V2 требует полный codec.
Malformed strict JSON/known legacy field invalid по прежним правилам; новые dropped
extras не ломают saved V1 replay. Probe не раскрывает tenant/receipt публично.

Cutover по exact approved binding/source/schema: guarded stop старых writers/workers,
normal webhook retries, upgrade/readiness, совместимый source. Никакого getUpdates,
drop_pending_updates или отключения connection. До отдельного material cutover
collector-only0011 остаётся V1. После cutover codec2 обязателен для fresh keys при
любом OFF/restart; default OFF относятся к A03/collector, не разрешают downgrade
writer до V1. Native domain activation в этом slice отсутствует, не скрытый bool.
Давний update без receipt — новый key, не доказательство свежего Owner действия;
update_id high-water не отбрасывает события. Used rollback только совместимым source.

### 15.7. P04 — минимальные DB/security связи и future allowlist

Нужны receipt codec/immutable typed sidecar; closed mutation Inbox terminal/result;
current target с nullable canonical binding и bounded fold; immutable actual effects;
effective-view helper; Turn invalidation flag; узкие ingress/process/read/grant/
admission capabilities. Original Message body/NormalizedEventV1/hash, Outbox delivery
и applied0001–0011 не переписываются. Это необходимые DDL conditions C2-P01/P03/P04/P06,
не исполняемая migration и не actual constraint/PG acceptance.

| Объект | Минимальные exact constraints / mapping |
|---|---|
| V2 sidecar | Один immutable row на receipt. Same receipt ID+codec2+configured bot+update+ws/connection; supporting receipt UNIQUE с этими immutable fields. NULL tenant refs допускаются только closed NONBUSINESS shape, не обход через nullable composite FK. V1 sidecar отсутствует |
| Queued binding | Same sidecar/receipt/Inbox/event: supporting Inbox UNIQUE `(workspace_id,id,connection_id,bot_identity,event_id)`; просто `(ws,id,connection)` недостаточно. Source kind/stub/event и hashes проверены§15.3/6. Receipt/sidecar/Inbox existence и equality проверены к commit (при цикле — deferred integrity constraint), не только Python promise |
| Provider target | Stable target UUID + UNIQUE/PK `(ws,connection,chat,provider_message_id)`, все четыре NOT NULL; partial UNIQUE `(ws,message_id) WHERE message_id IS NOT NULL`. Nullable Message UNIQUE не заменяет provider key. Canonical refs all-or-none, NULL лишь unbound deferred/tombstone/quarantined; binding write-once, provider/connection key immutable |
| Canonical C/Message | Reuse Conversation `(ws,id,connection,chat)` и `(ws,id,client)`; supporting Message `(ws,id,connection,conversation,chat,direction)` для exact FK. Business/Client совпадают с C/connection, workspace-only FK недостаточно |
| INBOUND target | Direction-specific required INBOUND; provider ID дополнительно равен saved Message.provider_message_id через supporting identity key/conditional FK; outbound ref NULL |
| OUTBOUND target | Required OUTBOUND и exact Outbox `(ws,id,message_id,connection,status,provider_message_id)` с required status=SENT; этот Outbox относится к тому же Message/C/chat. PENDING/DISPATCHING/UNKNOWN/FAILED/echo никогда не valid binding; inbound-only provider key NULL в этой ветке |
| Actual effect | Message non-NULL, UNIQUE `(source_update_receipt,canonical_message)`; tenant-safe refs на stable target, immutable Message identity, source receipt и тот же Audit. new_version=old_version+1, bounded reason. Historical accepted versions не FK к mutable Message.version или current watermark |
| Audit | Strict CHANNEL_EVENT/NULL user variant; supporting Audit key связывает ws/Audit ID/тот же Message/event type/accepted version. Audit ссылается на stable canonical identity/source receipt, effect→Audit; обратного Audit→effect FK нет |

**R3-01 — закрытая initial-fold suppression membership (C2-PROV-04).** Retained0008
CHECK требует FileObject для IMAGE_REFERENCE; заменить member type на current TEXT
нельзя из-за composite Message FK. В **будущем successor**, не в applied0008/0009,
выбрана одна новая форма с `membership_form='INITIAL_FOLD_SUPPRESSED'` и обязательным
`initial_suppression_id`. Для прежней формы оба новых поля NULL; прежние rows/V1 не
переписываются. Никакого общего PHOTO/file=NULL разрешения нет.

| Member form | Required / NULL и неизменные relations |
|---|---|
| Retained, membership_form=NULL | initial_suppression_id=NULL; прежний CHECK: TEXT/file=NULL либо IMAGE_REFERENCE/file NOT NULL с настоящим same-Message FileObject FK. PENDING/FAILED — существующие FileObject, не suppression |
| INITIAL_FOLD_SUPPRESSED | original content_type=IMAGE_REFERENCE, direction=INBOUND, file_id=NULL; initial_suppression_id NOT NULL и tenant-safe compound FK на evidence того же Message/target/origin с disposition=ELIGIBLE_VISIBLE. Все прежние Turn/Message/origin refs, ingress и capture relations сохраняются |

Marker/evidence/file combination вне этих двух строк — refusal. New member сохраняет
original `app.messages.content_type`/identity и original origin Inbox; mutable current
TEXT/PHOTO не подставляется в FK. OUTBOUND/SENT не допускается в обеих member формах.

Immutable основание сохраняется в proposed private
`platform.message_initial_suppressions`: PK `(workspace_id,id)`, UNIQUE
`(workspace_id,message_id)`. Это **не** mutable target flag и не копия всего event log.
Required refs: same-tenant canonical Message, stable bound target, original origin
Inbox, initial material effect и его source receipt; они все NOT NULL. Supporting
composite keys/constraint validator связывают evidence→target/Message с одной
INBOUND IMAGE_REFERENCE identity, теми же C/connection/chat/provider message и через
C — тем же Client/Business. Evidence→effect проверяет тот же target/Message/source
receipt и immutable accepted old_version=1/new_version=2; effect→Audit — прежняя
relation. Origin Inbox действительно CLIENT_MESSAGE того же original provider key,
original photo ref/body/sender/date; не Inbox edit и не произвольный более новый
duplicate. Выбор origin прежний: earliest `(turn_ingress_seq NULLS FIRST,id)` после
connection barrier. Его immutable ingress/captured generation/mode/fence сохраняются
через exact origin relation; legacy NULL captures не заменяются текущими значениями.
Membership допустима лишь при прежней original grouping eligibility, которая сама
по себе **не** выдаёт AI admission.

Evidence хранит frozen `initial_material` (closed semantic state/content по§15.3),
bounded fold summary/witness refs на immutable verified V2 sidecars (не более трёх,
delete — один) и `membership_disposition`. Material snapshot доказывает на момент
first bind ровно одно из: VISIBLE TEXT; VISIBLE PHOTO с ref, отличным от original;
DELETED/ORDER_UNCERTAIN/UNSUPPORTED_CONTENT. Same original PHOTO, в том числе лишь
изменённый caption, не suppression exception. Witness equality/identity и выбранный
effect source проверяются по§15.3–4, quarantine/identity conflict не основание.
Later target/watermark/current может измениться; frozen initial evidence и accepted
versions остаются валидными без historical FK к mutable Message.version/watermark.
Все поля evidence immutable; runtime UPDATE/DELETE запрещены, refs ON DELETE RESTRICT.

`membership_disposition` закрыт: HIDDEN при initial hidden state; иначе
INELIGIBLE_ORIGIN при отсутствии original grouping eligibility; иначе
ELIGIBLE_VISIBLE. По этому порядку NULL ingress допустим лишь в no-member ветке;
ELIGIBLE_VISIBLE требует настоящий original ingress и прежние exact capture checks.
К commit ELIGIBLE_VISIBLE требует ровно один matching new member; HIDDEN и
INELIGIBLE_ORIGIN требуют отсутствия membership. Deferred integrity constraint
проверяет обе стороны, включая попытку позднего member INSERT; evidence не содержит
обратного Turn/Job FK. Это сохраняет отсутствие membership после hidden→dated restore.

Право создать evidence имеет только private initial-original materialization body
с server-verified own PROCESS_INBOX claim/task/physical-XID context: именно он в этой
transaction впервые INSERT-нул данный Message, связал validated deferred fact и
принял effect1→2 **до** file creation/grouping. Проверяется отсутствие original
FileObject и связанного FETCH_IMAGE; наличие файла любого статуса, ранее созданного
member или merely missing file у старого Message — refusal. Runtime не может
выпустить capability для уже существующего Message, передать arbitrary suppression
boolean или вставить/изменить evidence direct DML. INSERT evidence и member находятся
в одном original atom§15.4, не в последующем «repair» commit.

Отсутствие FETCH доказывается не только снимком отсутствующих rows: каждый future
original File/FETCH creation path обязан отказать для Message с таким immutable
evidence. Existing File/FETCH/WINNER не удаляются/не маскируются ради exception.
Повторный original/grouping, replay и maintenance читают initial disposition и не
создают пропущенную работу позже. Guard проверяет immutable relation под уже принятым
original connection→Conversation порядком; File completion path не получает
обратного File→connection lock. Missing/wrong-tenant/wrong-Message/forged evidence
или mismatch frozen proof даёт integrity refusal и zero partial atom, не fallback
на NULL-photo либо создание фиктивного PENDING.

Evidence INSERT-before-member позволяет immediate member→evidence→effect→Audit FKs;
deferred check нужен только для commit-completeness/disposition/no-File инвариантов.
Новые evidence/member keys ссылаются на immutable Message/target/origin/receipt/effect
identities, без прямого connection или чужого Job FK. INBOUND-only private capability,
FORCE RLS и запрет direct runtime SELECT/DML распространяются на evidence. Принятый
stable-target SENT mapping ниже остаётся без новых reverse edges. Это constraints/
capability proposal, не SQL implementation, revision или новый migration grant.

Unknown создаёт только bounded target и terminal transport outcome,0 Client/C/Message/
Turn/File/material effect/Audit. Тот же входной PROCESS_INBOX заканчивается; новых
wait/polling/automation jobs нет. Duplicate IDs сворачиваются только для lock/effect/
result cardinality, не для receipt hash. Bound/unbound mismatch не rebind-ит target.

В stable-target SENT варианте§15.4 effect/Audit **не имеют прямого connection или
чужого Job FK**. Их ws/binding integrity замыкается через immutable source receipt и
stable target/Message composite identities. Смена canonical NULL→Message на target
не меняет его connection key; target создан заранее под connection barrier. Finalizer
не создаёт новый target и не проверяет повторно owner/product authority после
DISPATCHING. Source receipt immutable, source Inbox не блокируется заново, parent
Message/C keys не зависят от semantic version. SQL inventory/review обязан проверить
все implicit FK edges; другая physical mapping не считается согласованной этой таблицей.

Новые workspace-owned rows, включая private platform sidecars/effects, FORCE RLS;
runtime non-owner/non-BYPASSRLS, без direct SELECT/DML к закрытым данным. Public narrow
capabilities восстанавливают refs из verified receipt/own claim и прежнего task/
physical-XID context. Helpers private, PUBLIC revoked, search_path pinned
pg_catalog,pg_temp. Strict Audit union расширяется новым вариантом без ослабления
billing/manual/control/escalation variants. Общий apply/readiness/enqueue/admission
body обязателен: mutation-only wrapper не закрывает late file/control/worker races.
API/current snapshots/files_read_manifest используют общий effective projection.

**Последовательность схем.** B=`bae25093...`/0011 — frozen historical baseline, не
обещание двух независимых successors. C0/C2 отдельно назначают первый accepted
predecessor/source/revision и порядок renewal/material. Если renewal идёт первым,
material наследует exact accepted renewal schema; если material первой — renewal
наследует её. Соседняя migration не «перенумеровывается» и old migration не правится.
Каждый source P принимает только свой exact schema; mismatch source/schema отказывает
readiness. Collector-only не требует A03 activation, но поддерживает **actual выбранную
schema** и оба действующих TEST окна. Current VM UNKNOWN/live BLOCKED_TEST_INTERVAL.

Upgrade от назначенного exact predecessor сохраняет old-column exports/hashes,
UNKNOWN/private objects, receipts и прежние capability semantics; не создаёт history
Message/Turn/job, не backfill-ит origin/date. Unused downgrade возвращает именно
predecessor definitions/grants/inventory. Used blockers проверяются **до любого DDL**
для объектов, введённых откатываемой revision: V2 receipt/sidecar/material-result/
target/effect/initial-suppression evidence/new member form/invalidated Turn для material;
renewal receipt/Audit/новый interval и
mode transition для renewal. Уже принятый renewal predecessor не объявляется новым
material used state. Последующие revisions сначала откатываются по их собственным
правилам. Used recovery — совместимый P source/gates OFF либо forward fix, не B поверх
P и не удаление evidence. Старые compatibility lanes остаются frozen; exact successor
profile/inventory/allowlist implementation определяет отдельная выдача C0/C2/C6.

Следующая таблица — **proposed maximum allowlist material**, не write permission.
`migrations/versions/m3_message_provenance.py` — только proposed filename; revision и
predecessor назначаются отдельно по порядку выше. Разделение C3/C1/C2/C5/C6 за C0;
R2 не запускает других исполнителей и не разрешает писать эти paths.

| Exact future path(s) | Единственная причина |
|---|---|
| `migrations/versions/m3_message_provenance.py` (new) | Additive successor, tables/FKs/RLS/Audit/functions, no changes0001–0011 |
| `backend/src/asm/telegram/normalization.py`, `backend/src/asm/telegram/database.py`, `backend/src/asm/telegram/webhook.py` | V1 replay seam, V2 typed codec/receipt binding; прежняя auth/limits/ACK |
| `backend/src/asm/conversations/material.py` (new) | Закрытые typed delta/effect/current-view DTOs; не generic event engine |
| `backend/src/asm/messaging/database.py`, `backend/src/asm/messaging/results.py`, `backend/src/asm/messaging/worker.py` | V2 PROCESS_INBOX branch/typed outcomes, unchanged claims/recovery horizons |
| `backend/src/asm/conversations/turns.py`, `backend/src/asm/conversations/guards.py`, `backend/src/asm/conversations/escalations.py` | Versioned current material snapshot, suppression invalidated Turn; retained V1 decoders |
| `backend/src/asm/messaging/http_models.py`, `backend/src/asm/messaging/http_service.py`, `contracts/openapi.json` | Current material view в существующей history, generated paired contract; никаких edit/delete endpoints |
| `backend/src/asm/billing/models.py` | Только strict MESSAGE_MATERIAL_CHANGED Audit variant |
| `backend/src/asm/foundation.py`, `backend/src/asm/telegram/provisioning.py` | Только exact successor readiness/schema check, не live setup/TEST renewal |
| `frontend/src/messaging-api.ts`, `frontend/src/messaging-api.test.ts`, `frontend/src/messaging-fixtures.test-helper.ts`, `frontend/src/MessagingPanel.tsx`, `frontend/src/MessagingPanel.test.tsx` | Paired strict parser и current edit/deleted/unavailable presentation; прежняя manual recovery |
| `frontend/src/billing-api.ts`, `frontend/src/billing-api.test.ts`, `frontend/src/BillingPanel.tsx`, `frontend/src/BillingPanel.test.tsx` | Новый bounded Audit label/parser, сохранить mixed history |
| `tests/test_m3_1_provenance.py`, `tests/test_m3_1_provenance_postgres.py`, `tests/test_m3_1_provenance_migrations.py` (new) | P06 assertions/V1–V2 vectors, actual concurrency/upgrade/refusal |
| `tests/test_m3_1_control_postgres.py`, `tests/test_m3_1_control_api_postgres.py`, `tests/test_m3_1_guards_postgres.py`, `tests/test_m3_2_escalations_postgres.py`, `tests/test_m3_2_escalations_api_postgres.py` | Только mutation→guard rejection/Resume/UNKNOWN/terminal-first late answer cases и explicit child cleanup |
| `tests/test_m2_3_transport.py`, `tests/test_m2_3_db_postgres.py`, `tests/test_m2_3_wire_postgres.py`, `tests/test_m2_3_api_postgres.py`, `tests/test_m2_3_schema_postgres.py` | Retained V1 + new authenticated V2 path, isolation/grant/current view |
| `tests/test_foundation.py`, `tests/test_postgres.py`, `tests/test_tenancy_postgres.py`, `tests/test_m2_3_setup.py`, `tests/test_m1_3_postgres.py`, `tests/test_m1_3_c0_acceptance.py` | Только exact new head/inventory/explicit FK cleanup; прежние assertions неизменны |
| `tests/test_m3_1_migrations.py`, `tests/test_m3_1_control_migrations.py`, `tests/test_m3_1_guards_migrations.py`, `tests/test_m3_2_escalations_migrations.py` | Latest fixture restore/child cleanup; frozen predecessor projections сохранены |
| `scripts/prepare_telegram_egress.py`, `scripts/test_telegram_egress.sh`, `scripts/test_telegram_egress_migration.sh`, `tests/test_telegram_egress.py`, `tests/test_telegram_egress_migration.py`, `tests/test_telegram_egress_postgres.py` | Только согласованный C6 source/schema/inventory extension; без CI optimization/новых budgets |
| `frontend/e2e/messaging.spec.ts`, `scripts/m2_4_browser_fixture.py`, `scripts/m2_4_browser_worker.py`, `tests/test_m2_4_browser_fixture.py` | Один paired current-view journey через normal worker, existing TEST guards/PENDING-image boundary |
| `docs/tasks/M3_CONTRACT.md`, `docs/tasks/M3_HANDOFF.md`, `docs/TASK_REGISTER.md`, `docs/runbooks/M2_TELEGRAM_LOCAL_TEST.md` | Принятый scope/операторский порядок/evidence с содержательным diff |

Не включены transport client, dependencies, locks, Compose/images/workflows, SQL originals,
auth/CONTROL API, FileObject replacement engine. Для отдельного full photo replacement
конкретный дополнительный allowlist сначала утверждает C0; эта таблица его не
разрешает. Security/grant изменения выполняются в новой migration, не правкой old SQL.

### 15.8. P05 — короткий account probe для будущей выдачи C0/C6

**План исполним после трёх отдельных gates; сейчас NOT RUN.** Gate1 — C0 принимает
конкретный observation scope с Console-only control и HUMAN после native, а также
collector diff; это не требует объявить P-01/A08 закрытыми. Gate2 — поддержанный
renewal и **оба** действующих TEST окна; Gate3 — C6 подтверждает exact runtime/image/
schema/binding и отдельный guarded deployment/recovery. Collector не зависит от A03
activation. На0011 он допустим лишь при уже поддержанном действующем interval; сейчас
такого evidence нет. После renewal migration collector/readiness должны поддерживать
именно принятую actual schema. Runtime material/probe permissions различны; Git merge
не обновляет VM. Baseline0011 исторический, VM state UNKNOWN.

1. C6 получает текущее accepted source SHA/image digests/schema и сверяет actual VM
   read-only с ними; нельзя считать VM уже на0011. Collector target — принятый source
   и отдельно review-нутый collector commit с тем же exact schema gate. Если renewal
   требует migration, сначала отдельный source/schema rollout C0. Проверить TEST/asm_test, runtime role,
   normal webhook auth, configured bot, existing connection/Workspace/Business и
   independently approved Owner; Client/C известны либо создаются обычным client inbound.
   Readonly getMe/getBusinessConnection/getWebhookInfo только по отдельной live выдаче,
   один bounded запрос каждого, без retry loop; webhook URL/allowed business types и
   expected binding совпадают. Несовпадение/timeout/чужой chat → STOP до отправок.
2. Старый TEST interval завершён **2026-10-09T00:00Z**. Actual0007 fresh initializer
   создаёт и subscription, и NORMAL/PROVISIONED_LOCAL service mode с одинаковыми
   from/until. Actual product gate проверяет **оба** окна по DB clock после billing
   waits. workspace_service_modes имеет PK(workspace_id): одну current row, не history
   intervals. Только append subscription оставляет mode истёкшим; INSERT второй mode
   невозможен. provisioning.commit_binding требует0011/fresh initializer, provision
   затем setWebhook; повтор setup с новыми датами запрещён, renewal в этом path нет.

   **Выбор C0 для отдельной operator-only LOCAL/TEST command:** append новый
   ACTIVE/COMPED subscription + узкий CAS той же current NORMAL/PROVISIONED_LOCAL
   mode row, version+1, в **тот же** `[T0,T0+60min)`; один atomic commit с immutable
   key/request hash/result и новым strict Audit variant. Не строить mode-history модель.
   Expected mode ID/version/state/reason/old from/until, approved Workspace/Business/
   connection/bot/Owner, billing account, sealed test_messaging revision1/manifest и
   old subscription state проверяются целиком; SUSPENDED/GRACE/LIMITED/unexpected state
   не обходятся. Старые subscription intervals/catalog/binding/прежние receipts/Audit
   неизменны. У single current mode row старые from/until **законно заменяются этим CAS**,
   их точный before snapshot сохраняется immutable; фраза «old intervals неизменны»
   относится к subscription history, а не запрету этого выбранного mode transition.

   Конечный protocol новой операции: operator authority/actual LOCAL или TEST DB →
   typed key/payload и workspace/key serialization → saved receipt replay/conflict →
   согласованные billing locks и full expected-state/CAS recheck → DB clock T0 после
   waits → no-overlap/old-window-expired check → append subscription + mode CAS +
   immutable receipt/Audit одним commit. Request hash покрывает stable request:
   operation TEST_RENEW_60_V1, binding/catalog/expected old mode snapshot и fixed60min;
   новый clock/T0 **не** input hash. Exact replay по тому же key/payload возвращает
   сохранённые subscription/mode IDs, before/after, даты, versions и Audit ID, даже
   позже expiry; не append-ит, не CAS-ит, не пересчитывает T0 и не продлевает окно.
   Другой payload с тем же key — conflict. Replay receipt не означает, что product
   сейчас enabled: обычный manual/Resume заново проходит actual product gate.

   Proposed strict Audit: TEST_MESSAGING_INTERVAL_RENEWED, actor_kind=LOCAL_PROVISIONER,
   actor_user_account_id=NULL, object_type=WORKSPACE_SERVICE_MODE, object_id=той же
   mode.service_mode_id, object_version=accepted mode.version. Payload/receipt содержат
   exact typed before/after mode ID/mode/reason/from/until/version, новый subscription
   ID/plan revision/ACTIVE/COMPED/from/until и immutable approved binding evidence refs;
   не произвольный JSON и не повтор WORKSPACE_BILLING_PROVISIONED. Receipt/Audit FK
   используют immutable identity/accepted values, не mutable current mode.version.
   При ошибке append/CAS/Audit весь commit откатывается; exclusion no-overlap сохранён.
   Runtime direct DML не выдаётся; command/capability/строгие audit readers требуют
   отдельной C0/C2 implementation выдачи и inventory review.

   Future assertions: exact/mismatch replay, two concurrent requests/expected-version
   loss, atomic rollback, no overlap, refusal unexpected/SUSPENDED, DB clock после
   wait и реальный messaging_manual_send_allowed/Resume/manual product gate на обеих
   границах `from<=now<until`. Проверить independently expired subscription и mode:
   одной новой row недостаточно. Observation стартует≤T0+30min; collector≤15min и
   обязательно внутри обоих окон. Пока command/окна не приняты —
   **BLOCKED_TEST_INTERVAL**, Console sends/Resume/live probe не выполняются.
3. Current V1 не сохраняет нужные поля. Предложить C6 minimal diagnostic collector:
   после normal auth+strict JSON, до normalize_update извлечь только whitelist ниже;
   после ingest добавить sanitized receipt outcome/commit observation. Тело/headers
   не сохранять, отдельный маршрут не создавать. Collector default OFF, exact bot/
   connection/chat allowlist, TTL15min, максимум50 events/256KiB, private mode0600,
   stop на лимите/ошибке. Он не меняет ACK/domain decisions; capture loss помечает
   evidence INCOMPLETE, не PASS. Вне allowlist не сохранять даже metadata.
4. Включить capture на `Tstart` с абсолютным `Tstop=min(Tstart+15min,TEST_until)`.
   Owner сначала нажимает Console Takeover, подтверждает HUMAN; нет synthetic AI
   consumer в live conversation. Client отправляет один новый короткий TEST text и
   одну безопасную photo с caption. Дождаться visible canonical rows максимум60s на
   шаг; отсутствие → записать NOT OBSERVED/STOP, не посылать бесконечные повторы.
5. **Console-only control observation сначала:** Owner делает один новый TEST manual
   send из Console с одним сохранённым key. Его semantic Message/Outbox/delivery уже
   canonical; это отдельный тестовый ответ, не повтор native текста. Зафиксировать
   factual outcome независимо от echo; ambiguity→STOP sends, UNKNOWN сохранить, новый
   key не использовать. На полностью Console-only history explicit Resume возможен
   по accepted guards, но **в этом probe Resume не шаг завершения**.

   **Native observation затем:** один обычный native TEST reply в этом chat; отдельно
   owner/echo markers и отсутствие canonical human text. Далее Client меняет TEST
   text/caption, при доступном UI один раз заменяет TEST photo, удаляет эти два TEST
   сообщения для обеих сторон. Owner может один раз отредактировать native TEST reply;
   принятую project history не удалять. После первого native действия оставить HUMAN
   до отдельно принятого reconciliation; Console send не используется для заполнения
   пропуска. Каждый шаг≤60s, action ordinal/time/ожидаемый class; нет заранее PASS.
6. Other-bot/offline/scheduled проверить только если уже реально доступно на account
   без смены подключения/режима/подписок; максимум по одному действию. Иначе отдельные
   строки NOT OBSERVED/NOT AVAILABLE IN THIS PROBE. Не заменять connected bot ради
   примера. При необходимости пользователь делает scheduled TEST send в оставшемся
   окне; это проверяет marker, не доказательство полного списка implicit actions.
7. После действий оставить capture до Tstop, без изменения webhook/getUpdates mode,
   queue/inbox/jobs, paused chats или connection. Live delay/redelivery не инсценировать.
   Из duplicate доставки сделать observation, если она действительно случилась;
   synthetic delayed-before/after-Resume cases тестируются отдельно в LOCAL/PG.
   После native HUMAN — обязательная операционная граница плана, до separately
   accepted reconciliation. Actual0011 ещё позволяет Resume по старым guards и не
   проверяет полноту native transcript; не выдавать эту рекомендацию за runtime block.
   Takeover→native «согласовали другой вариант»→Resume→client «да» остаётся OPEN case,
   даже со свежими counters. Account observation не закрывает causal/latest-state proof.
8. Collector сам выключается на Tstop. C6 сверяет finite counts/drop status/normal
   receipt results, сохраняет sanitized evidence и digest, удаляет только временный
   приватный capture/key по принятому плану. Не удаляет DB receipts, Messages или S3.
   Матрица по каждому действию: action observed / webhook observed / fields present /
   current receipt / canonical effect / NOT OBSERVED reason. Выводы A03 и A08 раздельны.

Whitelist evidence: probe pseudonym; action/arrival/commit ordinal; update equality token
и относительный provider-order rank; configured bot/connection/chat/sender/message
устойчивые псевдонимы; target-ID equality для edits/delete; sender_is_bot, наличие
sender_business_bot и его relation own/other/none; offline TRUE/MISSING; event type,
text/photo/caption presence (не содержание); date/edit_date offsets в секундах от T0;
private-chat predicate; equals_approved_owner/client/configured_bot; canonical binding
match; sanitized result/duplicate flag и local control generation/fence relation.
Не сохранять text/caption, content hashes, username/names, реальные IDs, file_id,
file_unique_id, URLs, token/secret, IP, header/body/exception dumps. Для отношений
использовать HMAC с приватным случайным ключом одного probe (domain разделён по виду
identity), не обычный hash угадываемых numeric IDs. Provider-order rank сохраняет
относительный порядок без публикации чисел; пропуски/MISSING остаются явными.
Одинаковые User IDs используют общий user namespace, чтобы Owner/Client/bot comparison
не потерялся. Отдельно arrival order и provider-time order, их совпадение не causality.

Proposed collector-only exact paths: `backend/src/asm/telegram/provenance_probe.py`
(new: whitelist/redaction/finite buffer), `backend/src/asm/telegram/webhook.py`
(post-auth/pre-normalize hook), `backend/src/asm/telegram/config.py` (OFF/TTL/allowlist),
`tests/test_telegram_provenance_probe.py` (new: auth-before-capture/redaction/bounds),
`docs/runbooks/M2_TELEGRAM_LOCAL_TEST.md` (finite operation). Никакого raw logging.
Отдельный renewal proposal: `migrations/versions/m3_test_messaging_interval.py` (new,
revision не назначена), `scripts/renew_telegram_test_interval.py` (new),
`tests/test_telegram_test_interval.py` (new), `docs/runbooks/M2_TELEGRAM_LOCAL_TEST.md`.
C0/C2 назначают exact accepted predecessor/revision/order и implementation allowlist
до этой **отдельной** задачи; обе migrations не наследуют0011 параллельно. Proposed
companion allowlist — те же exact foundation/provisioning/readiness,
profile/fixture/cleanup, migration-cycle и шесть C6 compatibility paths из§15.7,
плюс `docs/tasks/M3_HANDOFF.md` и `docs/TASK_REGISTER.md`; их единственная дельта —
renewal revision/receipts и exact inventory. Для нового strict renewal Audit также
нужны `backend/src/asm/billing/models.py`, `frontend/src/billing-api.ts`,
`frontend/src/billing-api.test.ts`, `frontend/src/BillingPanel.tsx`,
`frontend/src/BillingPanel.test.tsx` и generated `contracts/openapi.json`, если union
включён в schema: только typed variant/label и mixed-history proof; accepted readers
нельзя сломать новой неизвестной записью. Это уточнение proposal, не новая выдача.
Ни этот перечень, ни четыре новых пути
не являются permission на deploy; не требуется расширять permissions runtime.

Ровно что понадобится пользователю позже: выбрать с C0 finite время, подтвердить
prepared Owner/Client account pair без публикации IDs/секретов, выполнить Takeover,
два client сообщения, один Console TEST send, затем native reply, edits/delete только
TEST messages и оставить HUMAN до reconciliation;
опциональный scheduled пример лишь при доступности. Доступ/секреты C6 использует
существующим защищённым способом. Сейчас никаких действий/паролей от пользователя
не требуется и отправки не инициируются.

### 15.9. P06 — конечная приёмка, OPEN и следующий scope

Это **обязательные assertions**; исполняемые material cases и статус NOT RUN перечислены в§15.10. Только затронутый risk;
прежние TURNS/CONTROL/GUARDS/Escalation suites остаются regression gates.

| ID / часть | Минимальный future assertion и слой |
|---|---|
| P-A03-01 normalizer/codec | Exact V1 vectors; closed NEW/EDIT/DELETE/LIFECYCLE/UNSUPPORTED(NONBUSINESS) NULL matrix, malformed-known rejection; SQL/Python full telegram_fingerprint+V2 fields, в том числе content reason; wrong common equality отказ; DELETE no invented origin/time |
| P-A03-02 actual PG identity/FK | Exact sidecar/receipt/codec/bot/update/ws/connection/Inbox binding; supporting composite keys/NULL bypass negatives; same provider ID across tenants/connections/chats не alias; write-once canonical binding; conditional INBOUND/exact valid-SENT OUTBOUND, UNKNOWN unmatched; immutable effect/Audit accepted version допускают следующий edit без historical FK break |
| P-A03-03 PG order/material | Все known/deferred traces§15.4, особенно U(A)/D(B) и U(B)/D(B) в обоих порядках; E10/E20 возврат к A; equal-date conflict/newer/replay/delete. Точные per-step counters/effects/Audit/sticky Turn, final safety convergence отдельно от history; mixed duplicate batch cardinality/order и context+N/Turn+1 |
| P-A03-04 workers/terminal/races | Closed codec2 queued EDIT/DELETE и MATERIAL_PROCESSED/message_id=NULL/Job SUCCEEDED/error=NULL, включая deferred/conflict; old V1 shapes/FK не ослаблены. Claim/restart/rollback/ACK loss, immutable processing results/eventual effects. Barriers original/material/SENT/implicit FK/connection/Conversation, sorted target/Message/Turn, no reverse foreign Job edge; NOWAIT/reclaim/post-wait expiry |
| P-A03-05 Turn/file/shared body | Общий apply/readiness/enqueue/admission и effective projection; original capture/deadlines/membership неизменны; invalidated Turn не revive, new Client→new Turn. Caption-only same ref сохраняет image; replacement/type change/delete/uncertainty и late FETCH не выдают stale image/grant, WINNER/history сохранены |
| P-A03-06 action/API races | Material до GUARDS accept/begin→0 new effects; после DISPATCHING retained SENT/FAILED/UNKNOWN. PENDING Escalation cancels once, без второго context bump; new key к stored CANCELLED/RESOLVED→409 ESCALATION_FINAL, EXPIRED→409 ESCALATION_EXPIRED; STALE_STATE только по accepted PENDING precedence; exact winning receipt replay неизменен |
| P-A03-07 API/UI/security | Полная current DTO matrix/examples/changed, historical file отдельно; backend/grant/context одно eligibility; paired OpenAPI/TS parser/panel/mixed Audit, auth/CSRF/RLS/same-Workspace wrong Client negatives. Refresh снимает stale image и игнорирует late grant по captured semantic version; TTL/realtime ограничения честные |
| P-A03-08 migration/compat | Fresh/populated/repeat upgrade от exact назначенного predecessor, retained0011/V1 history hashes/pending/completed/ignored/UNKNOWN/files. V1 replay до V2 parse и final locked recheck; OFF/restart не создаёт fresh V1. Owned used blockers до DDL, unused exact reverse, source/schema mismatch; последовательный renewal/material order |
| P-A03-09 account edit/delete | Отдельная выдача: target relations/action→actual receipt/effect. Collector-only0011 ожидает прежний IGNORED, не material PASS. Live material proof только после отдельно принятой A03 activation |
| P-A08-01 synthetic provenance/latest state | Approved Owner+B+C, bot/echo/offline/unsupported;0 false Client/takeover, no UNKNOWN confirmation/old IGNORED replay. Takeover→native «согласовали другой вариант»→Resume→client «да» остаётся missing-human-context counterexample; Console-only canonical reply проверяется отдельно, не closure native |
| P-A08-02 actual PG ordering | Ingress/Resume barrier, candidate before/after Resume при одинаковых provider fields, replay0; local fence не causal proof. Console control сохраняет accepted guards; candidate-only не создаёт transcript и не блокирует actual0011 Resume новой фиктивной проверкой |
| P-A08-03 account/renewal gate | Exact actual source/schema/binding; оба TEST окна. Future renewal CAS mode+append subscription+strict Audit/receipt atom, replay сохранённых дат, conflict/rollback/no-overlap/SUSPENDED rejection, clock после wait и реальный product gate на from/until. Finite authenticated collector, Console control до native, после native HUMAN; observation ≠causal/latest-state proof |

**C2-PROV-04 CLOSED на уровне design:** адресные R3 traces / обязательные PG assertions.
Исполняемые cases —§15.10; actual PG **NOT RUN**. Во всех positive traces B/C/identity verified;
P — ещё неизвестный original PHOTO F/caption A. Deferred commits имеют0 domain
increments/effects/Audit/File/Turn. Затем normal original worker впервые materializes
P; ΔC ниже включает original+1, material Audit/effect считается отдельно от transport.
Для fresh singleton origin eligible, нет collecting Turn и немедленного seal;
для existing Turn origin попадает в прежнее collecting окно без boundary/seal.

| ID / trace | Обязательный результат / future assertion |
|---|---|
| R3-T1: deferred E20(TEXT B) → original PHOTO F | m2/ΔC+2/один material effect+Audit,0 File/FETCH. Immutable Message/member IMAGE_REFERENCE; INITIAL_FOLD_SUPPRESSED/file=NULL с same-Message evidence ELIGIBLE_VISIBLE; current TEXT B. Fresh revision1/member_count1; existing R/n→R+1/n+1, fold не второй bump. Seal/snapshot используют TEXT, без ложного media wait; при отсутствии иных blockers COMPLETE |
| R3-T2: deferred E20(PHOTO G/caption B), G≠F → original F | Те же m2/ΔC+2/один effect+Audit,0 File/FETCH и exact grouping increments. New member IMAGE_REFERENCE/file=NULL; current PHOTO/PARTIAL/MEDIA_REPLACED_UNAVAILABLE. Seal/snapshot сохраняют unavailable reason, empty file JOIN не COMPLETE и не PENDING/WAITING_MEDIA ради replacement |
| R3-T3: deferred E10(PHOTO G), F10(PHOTO H), G≠H → original F → E20(PHOTO F) | Initial dated conflict: m2/ΔC+2/один effect+Audit, evidence HIDDEN,0 member/Turn/File/FETCH. Strictly newer restore: m3/ещё C+1/ещё один effect+Audit; current ORIGINAL_NOT_FETCHED/PARTIAL,0 нового member/Turn/File/FETCH. Evidence HIDDEN остаётся immutable, historical FK не зависит от m3/current watermark |
| R3-T4: legacy/unchanged PHOTO+NULL; invalid suppression | Retained member form PHOTO/file=NULL отказывает. Missing/wrong-tenant/wrong-Message/forged evidence, origin/effect mismatch, попытка exception при реальном PENDING/FAILED File или для старого missing File — refusal, zero partial atom: нет новых Message/context/member/Turn/effect/Audit/evidence/Job deltas этого atom. Подмена member type на TEXT также refusal |
| R3-T5: duplicate original / exact replay / maintenance после T1–T3 | Не добавляют material effect/Audit/context/grouping bump/File/FETCH. Existing membership не дублируется; initial HIDDEN/INELIGIBLE_ORIGIN не получает member, даже после restore. Законные GROUP/MEDIA переходы имеющегося Turn сохраняют прежние revision/deadline rules. Saved V1 snapshot/digest/receipt/decoder и File WINNER неизменны |

Граница execution evidence: принятый GUARDS producer исполняется только на CONTROLLED,
автоматической Telegram отправки сейчас нет. Поэтому P-A03-06 состоит из двух честных
proofs: TELEGRAM V2→обычный worker→material state/context/Escalation invalidation и
CONTROLLED guarded worker→тот же private material-apply helper→stale admission.
Второй proof использует disposable LOCAL/TEST fixture с finite typed delta, не подменяет
provider/route/Client в сохранённых rows и не называется live Telegram E2E. Test-only
trusted wrapper создаётся/удаляется migrator в fixture, не grant-ится обычному runtime
и не остаётся в production schema; C2 проверяет вызов того же apply body/lock order.
Public/production mutation helper не принимает произвольный caller Workspace/claim.
Если C0 требует positive automated Telegram admission, это отдельный scope по§13.4,
а не ослабление текущего CONTROLLED-only guard ради теста.

| Decision / статус | Что выбрано C0 / что остаётся |
|---|---|
| P-01 **OPEN** | Candidate-only + явный control не восстанавливают native human transcript. Resumable путь — canonical Console reply; native-only HUMAN до отдельно принятого context ingestion/reconciliation. No automatic takeover по arrival; native/latest-state/A08 NOT VERIFIED |
| P-02 policy/design **ACCEPTED** | Per-target increments, deferred folding, sticky suppression invalidated Turn сохранены. C2-PROV-04 CLOSED по C2 R3/C0; material source§15.10, implementation NOT VERIFIED |
| P-03 no-refetch policy/design **ACCEPTED** | Явное MEDIA_REPLACED_UNAVAILABLE/label/PARTIAL и потеря открытия/анализа replacement сохранены. Full replacement не поддержан этим slice. Current DTO/internal membership/seal/snapshot реализованы в source§15.10; DTO/grant/UI actual PG/browser NOT RUN, A03/M3 не принят |
| P-04 **IN_PROGRESS** для material; renewal OPEN | C0 назначил material0012←0011, exact base/allowlist57 и отдельные6 C6 paths. Source inventory§15.10; actual migration/catalog/compat NOT RUN. Renewal остаётся отдельной последовательной выдачей |
| P-05 **OPEN** | Выбран future append subscription + CAS NORMAL/PROVISIONED_LOCAL mode + immutable before/after/Audit. Команда/схема/collector/deploy/live не выданы и NOT VERIFIED. Старый TEST истёк, оба новых окна не подтверждены, VM UNKNOWN/live BLOCKED_TEST_INTERVAL |

| R2 пункт / findings | Исправленный proposal |
|---|---|
| R2-01 / C1-PROV-02 |§15.3: discriminator/nullability/common equality, один TargetResult union/cardinality/order, immutable receipt/result/effect раздельны |
| R2-02 / C2-PROV-01 |§15.3–4: undated-NOOP исключение удалено; bounded transition table и known/deferred traces, final safety отдельно от history |
| R2-03 / C2-PROV-02 |§15.6–7: retained0005/0007 limits, closed codec2 queued mutation/MATERIAL_PROCESSED/NULL Message, full Telegram V1 hash и post-cutover writer |
| R2-04 / C1-PROV-03 |§15.4/P-A03-06: точный terminal-first Escalation error и historical receipt replay |
| R2-05 / C1-PROV-04 |§15.3–4/P-A03-05/07: chosen no-refetch/current DTO matrix/examples/grant/refresh/TTL |
| R2-06 / C1-PROV-01 |§15.5/8/9: canonical Console-only path, native missing-context counterexample/HUMAN boundary; P-01 остаётся OPEN |
| R2-07 / C1-PROV-05 + C2-PROV-03 |§15.7–8/P-A08-03: оба TEST окна, CAS single mode row, immutable before/after, stable replay dates, последовательные schemas |
| R2-08 / C2-P01/P03/P04/P06 |§15.4/6/7/9: composite binding/FKs, stable-target SENT closure, same apply/readiness/read body; actual PG proof не заявлен |

C1-P01–07/C2-P01–07 review dispositions сохранены в исходных комментариях. По C1/C2
R2 reviews§15.1 C1-PROV-01…05/C2-PROV-01…03 CLOSED **на уровне revised design**;
повтор этих sections не требуется. C2-PROV-04/P2 CLOSED по C2 R3/C0 на уровне design;
следующий mapping сохранён, execution evidence —§15.10:

| R3 / C2-PROV-04 mapping | Норма / ручной trace и будущая проверка |
|---|---|
| R3-01 |§15.7: closed INITIAL_FOLD_SUPPRESSED/member evidence, frozen initial basis/identity/disposition и commit integrity; R3-T1–T4 |
| R3-02 |§15.4: shared grouping/member validators/seal/V2 snapshot/readiness, original identity отдельно от current; R3-T1–T3/T5 |
| R3-03 |§15.4/7: original atom, immutable FK/accepted version, connection→C→sorted targets/Messages/Turns, stable-target SENT без reverse connection/foreign Job; P-A03-02/04 и R3-T4 |
| R3-04 |§15.9 R3-T1–T5: exact counters/grouping, negative constraints, hidden restore/replay/maintenance, truthful snapshot и retained V1 |

Policy choice, revised-contract acceptance, implementation evidence и account
observation — разные стадии; native P-01/latest-state остаётся OPEN.

P01→§15.1–2; P02→§15.3–4; P03→§15.5; P04→§15.6–7;
P05→§15.8; P06→§15.9. Design R3 принят/интегрирован; прежние canonical receipts
сохранены. Material source checkpoint и точные local/deferred gates —§15.10.
После C0 intake C6 получает отдельную compatibility выдачу; затем C0 назначает один
Draft implementation PR с9 штатными automatic jobs и clean-source checks. PG/browser
остаются обязательны до приёмки. Actions dispatch/rerun, новые runners/budgets,
renewal/probe/VM/live/deploy/merge/activation не выдаются этим checkpoint.
C3 HOLD после возврата; C1/C2/C5/C6/C8 HOLD до назначения C0. MATERIAL/M3 IN_PROGRESS,
A03/A08/acceptance впереди; M4/LLM/production/IMPL-05/CI optimization не открыты.

### 15.10. MATERIAL implementation source checkpoint / 2026-10-15 UTC

Выдача [C0 MATERIAL](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6195028336), продолжение
[после ограничения окружения](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6195754984). Implementation source готов к
C0 intake; **MATERIAL/M3 IN_PROGRESS, A03 NOT VERIFIED; C3 HOLD после возврата**.
Текущая correction R1 от reviewed PR34 —§15.10.4; inventory§15.10.2 обновлён для неё.
Принятый design§15.2–15.8 и assertion tables§15.9 не изменены. No-refetch policy,
native/latest-state OPEN, renewal/collector/live и право merge/activation не расширены.

| Source binding | Значение |
|---|---|
| Branch | `c3/m3-1-material`; новый PR не открывается |
| Exact base / first source commit parent | `933ddd284ff5b77fb1aa88a4270ab0032bc499c9` |
| Base tree / schema | `d0759acb9f83ec3f3e10d9c5d1325c937c343ee7` /0011 |
| Base ordered parents | `bae25093bafb9534af68de5c586763667b896e70`, `642160d2181b9fb5d062e449a0ff603467c40e51` |
| Successor | `0012_message_provenance.py`, revision0012/down_revision0011; material first, renewal не назначен |
| Final head/tree/parents and changed paths/numstat | Один canonical source checkpoint comment в [PR33](https://github.com/Elefesys/ai-service-manager/pull/33); no self-SHA/status-only commit |

Implementation включает saved-V1 lookup до strict V2 parse и final locked recheck,
full H1→H2, separate codec2 sidecar, default-OFF captured material gate, bounded
target fold, immutable results/effects/Audit/suppression proof, atomic original
fold before File/grouping, winning terminal replay, current-only shared projection,
sticky Turn invalidation, preserved SENT/WINNER and legacy snapshots. Job→Inbox→
connection→identity barrier (original only)→Conversation→sorted targets→Messages→
Turns is the source lock order; SENT binds only an existing target under its existing
Conversation barrier without a reverse connection/foreign Job FK. Actual blocking
and rollback behavior is still subject to the PG tests below.

Owner message DTO now requires closed `current` (schema_version1, state,
content_type, text, image_availability, changed); immutable historical fields remain.
Versioned V2 internal snapshots keep historical identity and add current/member
suppression evidence; saved V1 parsing stays exact. The image grant SQL shares
`message_effective` eligibility. The Console uses current, clears an old image on
refresh and drops a late grant captured at another Message version. Audit adds the
closed `MESSAGE_MATERIAL_CHANGED`/`CHANNEL_EVENT` variant. OpenAPI and both TS
consumers are changed together. No realtime/TTL guarantee or replacement fetch is added.

#### 15.10.1. Contract→source→executable cases

| Contract / proof | Implementation | Исполняемые test node IDs; PG/browser пока NOT RUN |
|---|---|---|
| P-A03-01 / §15.3/6 | `normalization.py`, `material.py`, `telegram/database.py`, 0012 validation/ingress | `tests/test_m3_1_provenance.py::test_p_a03_01_*`; `PG::test_full_codec_sql_python_parity_closed_null_matrix_and_immutable_sidecar`; `MIG::test_cutover_saved_v1_replay_precedes_new_field_parse_and_fresh_v1_refused`; `tests/test_m2_3_wire_postgres.py::test_material_authenticated_webhook_to_normal_worker_preserves_original` |
| P-A03-02 / §15.7 | Provenance, target/effect/suppression composite FKs, immutable accepted versions, exact SENT binding | `PG::test_cross_binding_fk_null_bypasses_and_historical_effect_versions`; `PG::test_identity_conflict_does_not_poison_trusted_original_and_chat_isolation`; `PG::test_same_provider_id_across_workspace_and_connection_never_aliases`; `PG::test_exact_sent_binding_only_and_deferred_finalizer_without_connection_reverse` |
| P-A03-03 / §15.3/4 | Bounded fold, private apply/context, per-target effects/Audit and per-batch Turn bump | `PG::test_known_order_per_commit_counters_and_sticky_turn[steps0…17]`; `PG::test_deferred_order_fold_has_no_domain_writes_before_original[steps0…17]`; `PG::test_mixed_delete_batch_sorted_unique_context_n_turn_once_and_late_original`; `PG::test_overflow_is_full_rollback_without_effect_or_audit` |
| P-A03-04 / §15.4/6/7 | Normal claim/admission, terminal MATERIAL_PROCESSED, winning-claim replay, ordered barriers | `PG::test_material_terminal_result_token_pair_is_closed_and_write_once`; `PG::test_material_token_requires_completed_verified_mutation`; `PG::test_material_off_edit_has_no_terminal_token_or_replay`; `PG::test_rollback_and_lost_ack_restart_exact_terminal_replay`; `PG::test_real_barrier_recheck_and_postwait_claim_expiry`; `PG::test_original_and_material_workers_serialize_unknown_chat_without_deadlock`; `PG::test_material_reclaim_nowait_skips_locked_candidate_and_old_token_cannot_apply`; SENT test above |
| P-A03-05 / §15.4/7 | Shared grouping/member/seal/snapshot/readiness, effective projection and File grant predicate | R3 nodes below; `PG::test_known_turn_fresh_input_and_current_version_refusal_after_maintenance_file_resume[telegram/controlled-guard/controlled-escalation]`; `PG::test_late_original_fetch_retains_winner_and_context_but_never_stale_image`; `tests/test_m3_1_provenance.py::test_r3_t1_v2_snapshot_keeps_photo_identity_but_consumes_current_text` |
| P-A03-06 / §15.4/9 | Same private `material_apply_context`, existing context→Escalation trigger, shared GUARDS admission | `PG::test_shared_body_guards_stale_admission_and_retained_dispatch`; `PG::test_shared_body_escalation_context_cancel_once_terminal_precedence_and_saved_replay`; `PG::test_shared_body_retains_expired_escalation_precedence`; retained CONTROL/GUARDS/Escalation suites remain candidate gates |
| P-A03-07 / §15.4/7 | Required current DTO, paired OpenAPI/TS parser/panel, CHANNEL_EVENT Audit, current-only grant | `tests/test_m3_1_provenance.py::test_p_a03_07_*`; `PG::test_api_current_closed_history_and_same_workspace_wrong_client`; `PG::test_runtime_nonowner_force_rls_and_no_raw_table_or_private_function_access`; four scoped Vitest modules; `frontend/e2e/messaging.spec.ts` TEXT journey plus three “material PHOTO … normal Worker mutation and grant refusal” journeys and “material PHOTO delayed real old grant cannot restore image after semantic refresh” |
| P-A03-08 / §15.6/7 | 0011→0012, immutable ORIGINAL/OLD_CHECK copies, first used refusal, current readiness0012 | `MIG::test_fresh_head_full42_columns_profiles_rls_and_no_unused_backfill`; `MIG::test_populated_0011_repeat_upgrade_and_exact_unused_reverse`; `MIG::test_owned_used_refusal_precedes_every_ddl_and_preserves_all42`; cutover node above; C6 source/schema compatibility still pending |
| R3-T1/T2 | First original fold before File/grouping; typed PHOTO/file=NULL only with suppression proof | `PG::test_initial_photo_suppression_visible_snapshot_and_duplicate`: fresh-turn/existing-turn × R3-T1-text/R3-T2-photo, exact m2/C+2/effect/Audit/grouping/seal/V2 assertions |
| R3-T3 | HIDDEN initial exclusion, newer restore without retroactive membership/FETCH | `PG::test_r3_t3_hidden_restore_and_t5_no_late_group_or_fetch` |
| R3-T4 | Before-insert authority and deferred completeness, typed legacy member retained | `PG::test_r3_t4_invalid_first_suppression_rolls_back_entire_original_atom`: null-form, missing-proof, text-member, wrong-tenant/message/origin/effect, forged-basis and PENDING/FAILED File negatives; exact SQLSTATE/constraint/reason + intended function context, all42-table rollback fingerprints, same-claim positive neighboring atom after dropping the corruption trigger |
| R3-T5 | Duplicate original/exact replay/maintenance; retained V1 decoder/snapshot/receipt/WINNER | R3-T1/T2/T3 nodes; `MIG::test_legacy_ineligible_photo_first_original_stays_suppressed_after_restore`; populated-cycle node; `tests/test_m3_1_provenance.py::test_r3_t5_saved_v1_decoder_does_not_adopt_new_member_form` |

`PG` = `tests/test_m3_1_provenance_postgres.py`, `MIG` =
`tests/test_m3_1_provenance_migrations.py`. Parameter suffixes are generated by pytest;
the concrete collection, not a claimed execution, is recorded below. Every integration
module uses the existing disposable `asm_test` fixtures and `integration` marker;
no skip/xfail or substitute mock PostgreSQL. The CONTROLLED proof creates/drops a
finite migrator-only TEST wrapper around the same private apply body; it does not
rewrite saved provider/route/Client rows or grant a production mutation capability.


#### 15.10.2. Source inventory for C6; not an actual catalog report

This inventory is expanded from migration Python/DDL, without a PostgreSQL connection.
The full table projection is `P_COLUMNS` in the migration test: retained exact
`E_COLUMNS` (38 tables/schema0011) plus4 tables and10 columns on6 existing tables.
No prior projected column is removed/reordered. `app.messages` and `app.outbox_events`
gain supporting unique keys only. All retained types/defaults/constraints/indexes/
triggers/policies/ACLs are defined by immutable0001–0011; the successor delta is
`_schema`, `_integrity`, `_suppression`, `_material`, `_worker`, `_shared` and explicit
owner/REVOKE/GRANT loop in0012. Source operation count131 is not SQL statement count
or successful-DDL evidence. Implicit constraint/index names must be checked by PG,
not guessed from source. Actual catalog comparison is `catalog`/`definitions` in
the tests (functions+bodies/ACL/owner, relations, columns/types/defaults, constraints,
indexes, triggers, policies, sequences), and is **NOT RUN**.

| Полная P table projection | Columns, exact source order |
|---|---|
| `app.audit_events` | `workspace_id, audit_event_id, occurred_at, actor_kind, actor_user_account_id, correlation_id, event_type, object_type, object_id, object_version, payload, billing_account_object_id, message_object_id, conversation_object_id, conversation_control_generation, escalation_object_id, escalation_operation, material_target_id, material_source_receipt_id` |
| `app.business_members` | `workspace_id, id, business_id, user_account_id, name, role, status, version, created_at` |
| `app.businesses` | `workspace_id, id, name, status, version, created_at` |
| `app.channel_connections` | `workspace_id, id, business_id, provider, bot_identity, external_connection_id, status, version, created_at` |
| `app.client_identities` | `workspace_id, id, client_id, provider, external_user_id, created_at` |
| `app.clients` | `workspace_id, id, version, created_at` |
| `app.conversation_turn_messages` | `workspace_id, message_id, turn_id, conversation_id, connection_id, direction, content_type, origin_inbox_id, turn_ingress_at, turn_ingress_seq, file_id, membership_form, initial_suppression_id, suppression_disposition` |
| `app.conversation_turns` | `workspace_id, id, conversation_id, connection_id, provider_chat_id, revision, control_generation, state, policy_version, debounce_ms, group_ms, media_ms, max_members, member_count, media_group_id, first_ingress_at, last_ingress_at, hard_at, quiet_at, media_deadline_at, seal_time, closed_at, ready_at, readiness, error_code, created_at, ingress_control_mode, activation_fence_seq, material_invalidated` |
| `app.conversations` | `workspace_id, id, connection_id, business_id, client_id, identity_id, provider_chat_id, version, created_at, last_client_inbound_at, control_mode, control_generation, activation_fence_seq` |
| `app.escalations` | `workspace_id, id, namespace, conversation_id, client_id, connection_id, turn_id, source_job_id, source_job_kind, source_job_step, source_claim_token, turn_revision, resume_receipt_id, control_generation, activation_fence_seq, input_context_version, waiting_context_version, request_snapshot, context_fingerprint, request_fingerprint, creation_result, reason, assignee_user_account_id, question, policy, created_at, due_at, second_reminder_at, expires_at, first_reminded_at, second_reminded_at, version, status, closure_reason, completed_at, answer_text, decided_by_user_account_id` |
| `app.file_objects` | `workspace_id, id, message_id, connection_id, conversation_id, required_direction, required_content_type, status, winner_intent_id, winner_state, storage_key, mime_type, size_bytes, sha256, width, height, error_code, version, created_at, completed_at` |
| `app.locations` | `workspace_id, id, business_id, name, status, version, created_at` |
| `app.messages` | `workspace_id, id, conversation_id, connection_id, provider_chat_id, provider_message_id, direction, content_type, text, image_file_id, media_group_id, occurred_at, projection_fingerprint, version, created_at` |
| `app.outbox_events` | `workspace_id, id, connection_id, message_id, kind, required_direction, status, attempt_id, provider_message_id, error_code, completed_at, version, created_at` |
| `platform.alembic_version` | `version_num` |
| `platform.auth_credentials` | `user_account_id, login, password_hash, version, created_at` |
| `platform.auth_sessions` | `token_hash, user_account_id, credential_version, account_version, created_at, expires_at, revoked_at` |
| `platform.billing_contact_command_receipts` | `workspace_id, receipt_id, billing_account_id, operation, idempotency_key, request_fingerprint, expected_version, status, result_version, result_outcome, created_at, completed_at` |
| `platform.channel_routes` | `workspace_id, id, connection_id, provider, bot_identity, route_key, created_at` |
| `platform.conversation_control_receipts` | `workspace_id, id, operation_namespace, operation, idempotency_key, conversation_id, client_id, actor_user_account_id, correlation_id, expected_generation, expected_context_version, previous_mode, accepted_mode, previous_generation, accepted_generation, context_version, activation_fence_seq, request_fingerprint, audit_event_id, audit_event_type, accepted_at, result, guard_profile` |
| `platform.escalation_command_receipts` | `workspace_id, id, namespace, idempotency_key, escalation_id, conversation_id, client_id, actor_user_account_id, correlation_id, operation, expected_version, expected_control_generation, expected_context_version, accepted_version, accepted_status, accepted_context_version, request_fingerprint, audit_event_id, audit_event_type, accepted_at, result` |
| `platform.file_object_uploads` | `workspace_id, id, file_id, job_id, claim_token, storage_key, mime_type, size_bytes, sha256, width, height, status, cleanup_claim_token, cleanup_lease_until, cleanup_attempts, next_check_at, last_checked_at, cleanup_outcome, version, created_at` |
| `platform.inbox_events` | `workspace_id, id, connection_id, provider, bot_identity, external_connection_id, required_direction, event_id, normalized_event, event_fingerprint, correlation_id, received_at, status, result_code, message_id, completed_at, version, turn_ingress_at, turn_ingress_seq, turn_control_generation, turn_control_mode, turn_activation_fence_seq, material_result, material_claim_token` |
| `platform.message_initial_suppressions` | `workspace_id, id, message_id, target_id, origin_inbox_id, effect_id, source_receipt_id, previous_version, accepted_version, initial_material, fold_witnesses, membership_disposition` |
| `platform.message_material_effects` | `workspace_id, id, target_id, message_id, source_receipt_id, audit_event_id, event_type, previous_version, accepted_version, reason, accepted_at` |
| `platform.message_material_targets` | `workspace_id, id, connection_id, provider_chat_id, provider_message_id, message_id, conversation_id, client_id, direction, outbox_id, inbound_provider_id, required_sent, quarantined, original_grouping_closed, origin_identity, deleted, undated_seen, max_edit_at, candidate, dated_conflict, delete_receipt, undated_receipt, candidate_receipt, conflict_receipt, current_material` |
| `platform.messaging_command_receipts` | `workspace_id, id, operation, idempotency_key, request_fingerprint, actor_user_account_id, correlation_id, message_id, outbox_id, audit_event_id, accepted_at` |
| `platform.messaging_jobs` | `workspace_id, id, connection_id, kind, inbox_id, outbox_id, correlation_id, status, available_at, claim_token, lease_until, worker_id, attempt_count, first_started_at, error_code, completed_at, last_attempt_id, last_claim_token, last_outcome, last_provider_message_id, last_error_code, version, created_at, file_id, last_retry_after_seconds, last_retry_due, telegram_probe_claim, telegram_probe_generation, telegram_probe_version, turn_id, turn_revision, step, turn_outcome, turn_input, guard_rejection, escalation_id, escalation_outcome` |
| `platform.plan_entitlements` | `plan_revision_id, capability_key, value_kind, enabled, limit_value, criticality, created_at` |
| `platform.saas_plan_revisions` | `plan_revision_id, plan_id, revision, publication_state, published_at, created_at` |
| `platform.saas_plans` | `plan_id, code, display_name, status, created_at` |
| `platform.telegram_connection_state` | `workspace_id, connection_id, provider, bot_identity, external_connection_id, owner_user_id, generation, observation_version, observed_generation, observed_at, observation_xid, is_enabled, can_reply, error_code, material_enabled` |
| `platform.telegram_provenance` | `receipt_id, codec, bot_identity, update_id, workspace_id, connection_id, inbox_id, projection, material_enabled` |
| `platform.telegram_update_receipts` | `id, bot_identity, update_id, fingerprint, kind, result_code, workspace_id, connection_id, inbox_id, received_at, codec` |
| `platform.turn_consumer_receipts` | `workspace_id, job_id, connection_id, kind, turn_id, turn_revision, step, consumer, winning_claim_token, input_context_version, input_control_generation, snapshot_digest, result, accepted_at` |
| `platform.turn_guard_receipts` | `workspace_id, job_id, winning_claim_token, connection_id, conversation_id, client_id, turn_id, turn_revision, resume_receipt_id, input_control_generation, activation_fence_seq, input_context_version, snapshot_digest, consumer, request_fingerprint, result_text, outcome, accepted_at, intent_context_version, message_id, outbox_id, send_job_id, namespace, kind, step, direction, content_type, send_kind` |
| `platform.user_accounts` | `id, status, version, created_at` |
| `platform.workspace_billing_accounts` | `workspace_id, billing_account_id, contact_display_name, version, created_at, updated_at` |
| `platform.workspace_memberships` | `workspace_id, user_account_id, role, status, version, created_at` |
| `platform.workspace_service_modes` | `workspace_id, service_mode_id, mode, reason_code, effective_from, effective_until, version, created_at, updated_at` |
| `platform.workspace_subscriptions` | `workspace_id, subscription_id, plan_revision_id, required_publication_state, status, funding_mode, effective_from, effective_until, version, created_at, updated_at` |
| `platform.workspaces` | `id, status, version, created_at` |

New tables are owned by `asm_migrator`, ENABLE+FORCE RLS, with one
`material_migrator TO asm_migrator USING(true) WITH CHECK(true)` policy each and
`REVOKE ALL ... FROM PUBLIC,asm_runtime`. No runtime raw table grants, runtime RLS
policy or sequence is added. Three new histories reject UPDATE through
`turn_immutable`; targets have before-write identity/witness checks and deferred
current/fold consistency. Receipt codec is immutable; deferred provenance iff/binding
checks also cover deletes. Suppression authority is before INSERT and completeness
is deferred on proof/member. `material_no_file` forbids a late File for initial
suppression. Existing immutable original Message columns/capture/deadlines remain.

| Constraint family | Exact source obligations |
|---|---|
| Provenance | receipt PK and full composite codec/bot/update/ws/connection/Inbox FK; same-Workspace Inbox/receipt unique keys; closed V2 JSON/common equality; tenantless only NONBUSINESS; codec2↔sidecar iff and queued fingerprint checked deferred |
| Target | PK(ws,id), unique(ws,connection,chat,provider ID), partial unique(ws,Message); conditional full INBOUND/exact SENT OUTBOUND FK/NULL matrix; Conversation/Client and immutable Message identity; at most3 retained fold witnesses; same ws/connection/chat/target/kind/date/semantic witnesses; sticky delete/uncertainty/quarantine/excluded grouping; no foreign Job FK |
| Effect/Audit | unique(source receipt,Message); target/message and source FK; immutable accepted_version=previous_version+1; exact Audit composite key incl event type/version/target/source; CHANNEL_EVENT/no user and closed payload/reason; no FK to mutable current Message.version |
| Suppression/member | one proof per(ws,Message), previous1/accepted2, exact effect/source/origin FK; frozen initial state/witnesses/disposition; own first-original physical transaction authority; PHOTO/INBOUND/fileNULL exception only same-Message ELIGIBLE_VISIBLE proof; HIDDEN/INELIGIBLE never gain membership |
| Inbox/receipt | retained old closed CHECK alternatives, separate codec2 queued EDIT/DELETE and MATERIAL_PROCESSED/NULL Message; complete sorted per-target result union + non-NULL private winning material_claim_token, exact source/effect/Audit binding and immutable terminal pair; legacy/NEW/PENDING pair NULL; outer CHECK IS TRUE excludes NULL bypass |

The following is the complete successor schema DDL expansion (excluding function
bodies, table security loop and locks already described); it is executable source,
not `pg_get_*` output. Retained checks appear in full so C6 can compare the exact
OR extension and immutable reverse.

```sql
ALTER TABLE platform.telegram_connection_state ADD COLUMN material_enabled boolean NOT NULL DEFAULT false;
      ALTER TABLE platform.telegram_update_receipts ADD COLUMN codec smallint CHECK(codec=2),
        ADD CONSTRAINT telegram_material_identity_key UNIQUE(id,codec,bot_identity,update_id,workspace_id,connection_id,inbox_id),
        ADD CONSTRAINT telegram_material_source_key UNIQUE(workspace_id,id),
        DROP CONSTRAINT telegram_update_receipts_check;

ALTER TABLE platform.telegram_update_receipts ADD CONSTRAINT telegram_update_receipts_check CHECK(
      (codec IS NULL AND ((workspace_id IS NULL AND connection_id IS NULL AND inbox_id IS NULL AND kind='UNSUPPORTED' AND result_code='IGNORED_UNSUPPORTED') OR
        (workspace_id IS NOT NULL AND connection_id IS NOT NULL AND
          ((result_code='QUEUED' AND kind='BUSINESS_MESSAGE' AND inbox_id IS NOT NULL) OR (result_code<>'QUEUED' AND inbox_id IS NULL))))) OR
      (codec=2 AND ((workspace_id IS NULL AND connection_id IS NULL AND inbox_id IS NULL AND kind='UNSUPPORTED' AND result_code='IGNORED_UNSUPPORTED') OR
        (workspace_id IS NOT NULL AND connection_id IS NOT NULL AND ((result_code='QUEUED' AND kind IN
          ('BUSINESS_MESSAGE','EDITED_BUSINESS_MESSAGE','DELETED_BUSINESS_MESSAGES') AND inbox_id IS NOT NULL) OR
          (result_code<>'QUEUED' AND inbox_id IS NULL))))) IS TRUE);

ALTER TABLE platform.inbox_events ADD COLUMN material_result jsonb,ADD COLUMN material_claim_token uuid,
      ADD CONSTRAINT inbox_material_identity_key UNIQUE(workspace_id,id,connection_id,bot_identity,event_id),
      DROP CONSTRAINT inbox_events_check;

ALTER TABLE platform.inbox_events ADD CONSTRAINT inbox_events_check CHECK(
      ((material_result IS NULL AND material_claim_token IS NULL AND ((status='PENDING' AND result_code IS NULL AND message_id IS NULL AND completed_at IS NULL) OR
       (status='PROCESSED' AND result_code IS NOT NULL AND result_code IN ('PROCESSED','DUPLICATE') AND message_id IS NOT NULL AND completed_at IS NOT NULL) OR
       (status='IGNORED' AND result_code IS NOT NULL AND result_code IN ('IGNORED_NATIVE_OWNER_MESSAGE','IGNORED_MESSAGE_EDITED','IGNORED_MESSAGE_DELETED','IGNORED_UNSUPPORTED') AND message_id IS NULL AND completed_at IS NOT NULL) OR
       (status='FAILED' AND result_code IS NOT NULL AND result_code IN ('MESSAGE_ID_CONFLICT','CONVERSATION_IDENTITY_CONFLICT','RETRY_EXHAUSTED','DEPENDENCY_TIMEOUT','DEPENDENCY_UNAVAILABLE','INVALID_INPUT') AND message_id IS NULL AND completed_at IS NOT NULL))) OR
      (status='PROCESSED' AND result_code='MATERIAL_PROCESSED' AND message_id IS NULL AND completed_at IS NOT NULL
        AND material_claim_token IS NOT NULL AND platform.material_result_valid(material_result) IS TRUE)) IS TRUE);

CREATE TABLE platform.telegram_provenance(
      receipt_id uuid PRIMARY KEY,codec smallint NOT NULL DEFAULT 2 CHECK(codec=2),
      bot_identity text NOT NULL,update_id text NOT NULL,workspace_id uuid,connection_id uuid,inbox_id uuid,
      projection jsonb NOT NULL,material_enabled boolean NOT NULL,
      UNIQUE(workspace_id,receipt_id),UNIQUE(workspace_id,inbox_id),
      FOREIGN KEY(receipt_id) REFERENCES platform.telegram_update_receipts(id) ON DELETE RESTRICT,
      FOREIGN KEY(receipt_id,codec,bot_identity,update_id,workspace_id,connection_id,inbox_id)
        REFERENCES platform.telegram_update_receipts(id,codec,bot_identity,update_id,workspace_id,connection_id,inbox_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,inbox_id,connection_id,bot_identity,update_id)
        REFERENCES platform.inbox_events(workspace_id,id,connection_id,bot_identity,event_id) ON DELETE RESTRICT,
      CHECK(projection=platform.telegram_validate_v2(bot_identity,projection)),
      CHECK((workspace_id IS NULL AND connection_id IS NULL AND inbox_id IS NULL AND projection->>'discriminator'='UNSUPPORTED') OR
        (workspace_id IS NOT NULL AND connection_id IS NOT NULL AND projection->>'discriminator'<>'UNSUPPORTED')))
      ;

ALTER TABLE app.messages
      ADD CONSTRAINT messages_material_identity_key UNIQUE(workspace_id,id,connection_id,conversation_id,provider_chat_id,direction),
      ADD CONSTRAINT messages_material_inbound_key UNIQUE(workspace_id,id,provider_message_id,direction);
      ALTER TABLE app.outbox_events ADD CONSTRAINT outbox_material_sent_key
        UNIQUE(workspace_id,id,message_id,connection_id,status,provider_message_id);
      ALTER TABLE app.conversation_turns ADD COLUMN material_invalidated boolean NOT NULL DEFAULT false;

CREATE TABLE platform.message_material_targets(
      workspace_id uuid NOT NULL,id uuid NOT NULL DEFAULT uuidv7(),connection_id uuid NOT NULL,
      provider_chat_id text NOT NULL CHECK(platform.telegram_numeric_id(provider_chat_id)),
      provider_message_id text NOT NULL CHECK(platform.telegram_numeric_id(provider_message_id)),
      message_id uuid,conversation_id uuid,client_id uuid,direction text,outbox_id uuid,
      inbound_provider_id text,required_sent text,
      quarantined boolean NOT NULL DEFAULT false,original_grouping_closed boolean NOT NULL DEFAULT false,origin_identity jsonb,
      deleted boolean NOT NULL DEFAULT false,undated_seen boolean NOT NULL DEFAULT false,
      max_edit_at timestamptz CHECK(isfinite(max_edit_at)),candidate jsonb,dated_conflict boolean NOT NULL DEFAULT false,
      delete_receipt uuid,undated_receipt uuid,candidate_receipt uuid,conflict_receipt uuid,
      current_material jsonb CHECK(current_material IS NULL OR platform.material_state_valid(current_material)),
      PRIMARY KEY(workspace_id,id),UNIQUE(workspace_id,connection_id,provider_chat_id,provider_message_id),
      UNIQUE(workspace_id,id,message_id),
      FOREIGN KEY(workspace_id,connection_id) REFERENCES app.channel_connections(workspace_id,id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,message_id,connection_id,conversation_id,provider_chat_id,direction)
        REFERENCES app.messages(workspace_id,id,connection_id,conversation_id,provider_chat_id,direction) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,conversation_id,client_id) REFERENCES app.conversations(workspace_id,id,client_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,message_id,inbound_provider_id,direction)
        REFERENCES app.messages(workspace_id,id,provider_message_id,direction) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,outbox_id,message_id,connection_id,required_sent,provider_message_id)
        REFERENCES app.outbox_events(workspace_id,id,message_id,connection_id,status,provider_message_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,delete_receipt) REFERENCES platform.telegram_provenance(workspace_id,receipt_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,undated_receipt) REFERENCES platform.telegram_provenance(workspace_id,receipt_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,candidate_receipt) REFERENCES platform.telegram_provenance(workspace_id,receipt_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,conflict_receipt) REFERENCES platform.telegram_provenance(workspace_id,receipt_id) ON DELETE RESTRICT,
      CHECK((message_id IS NULL AND conversation_id IS NULL AND client_id IS NULL AND direction IS NULL AND outbox_id IS NULL
        AND inbound_provider_id IS NULL AND required_sent IS NULL AND current_material IS NULL) OR
        (message_id IS NOT NULL AND conversation_id IS NOT NULL AND client_id IS NOT NULL AND direction IS NOT NULL
          AND current_material IS NOT NULL AND NOT quarantined AND
          ((direction='INBOUND' AND inbound_provider_id=provider_message_id AND inbound_provider_id IS NOT NULL AND outbox_id IS NULL AND required_sent IS NULL) OR
           (direction='OUTBOUND' AND inbound_provider_id IS NULL AND outbox_id IS NOT NULL AND required_sent='SENT' AND required_sent IS NOT NULL)))),
      CHECK((deleted AND delete_receipt IS NOT NULL AND NOT undated_seen AND NOT dated_conflict AND max_edit_at IS NULL AND candidate IS NULL
        AND undated_receipt IS NULL AND candidate_receipt IS NULL AND conflict_receipt IS NULL) OR
        (NOT deleted AND delete_receipt IS NULL AND (undated_seen=(undated_receipt IS NOT NULL)) AND
          ((max_edit_at IS NULL AND candidate IS NULL AND candidate_receipt IS NULL AND conflict_receipt IS NULL AND NOT dated_conflict) OR
           (max_edit_at IS NOT NULL AND candidate_receipt IS NOT NULL AND
             ((dated_conflict AND candidate IS NULL AND conflict_receipt IS NOT NULL) OR
              (NOT dated_conflict AND candidate IS NOT NULL AND conflict_receipt IS NULL AND platform.material_content_valid(candidate) IS TRUE)))))));

CREATE UNIQUE INDEX message_material_bound_key ON platform.message_material_targets(workspace_id,message_id) WHERE message_id IS NOT NULL;
      ALTER TABLE app.audit_events ADD COLUMN material_target_id uuid GENERATED ALWAYS AS
        (CASE WHEN event_type='MESSAGE_MATERIAL_CHANGED' THEN (payload->>'target_id')::uuid END) STORED,
      ADD COLUMN material_source_receipt_id uuid GENERATED ALWAYS AS
        (CASE WHEN event_type='MESSAGE_MATERIAL_CHANGED' THEN (payload->>'source_receipt_id')::uuid END) STORED,
      ADD CONSTRAINT audit_material_target_fkey FOREIGN KEY(workspace_id,material_target_id,object_id)
        REFERENCES platform.message_material_targets(workspace_id,id,message_id) ON DELETE RESTRICT,
      ADD CONSTRAINT audit_material_source_fkey FOREIGN KEY(workspace_id,material_source_receipt_id)
        REFERENCES platform.telegram_provenance(workspace_id,receipt_id) ON DELETE RESTRICT,
      ADD CONSTRAINT audit_material_ref_key UNIQUE(workspace_id,audit_event_id,object_id,event_type,object_version,material_target_id,material_source_receipt_id),
      DROP CONSTRAINT audit_events_discriminator_payload_check;

ALTER TABLE app.audit_events ADD CONSTRAINT audit_events_discriminator_payload_check CHECK(
      (

      (event_type='WORKSPACE_BILLING_PROVISIONED' AND
 actor_kind='LOCAL_PROVISIONER' AND actor_user_account_id IS NULL AND
 object_type='WORKSPACE_BILLING_ACCOUNT' AND payload='{}'::jsonb) OR
 (event_type='BILLING_ACCOUNT_CONTACT_UPDATED' AND actor_kind='USER_ACCOUNT' AND
 actor_user_account_id IS NOT NULL AND object_type='WORKSPACE_BILLING_ACCOUNT' AND
 payload='{"changed_fields":["contact_display_name"]}'::jsonb) OR (event_type='MESSAGE_SEND_REQUESTED' AND actor_kind='USER_ACCOUNT' AND actor_user_account_id IS NOT NULL AND object_type='MESSAGE' AND object_version=1 AND payload='{"content_type":"TEXT"}'::jsonb) OR ((
        event_type IN ('CONVERSATION_TAKEN_OVER','CONVERSATION_RESUMED') AND actor_kind='USER_ACCOUNT'
        AND actor_user_account_id IS NOT NULL AND object_type='CONVERSATION' AND object_version>0
        AND conversation_object_id IS NOT NULL AND conversation_control_generation IS NOT NULL
        AND payload=jsonb_build_object('previous_mode',payload->>'previous_mode','control_mode',payload->>'control_mode',
          'previous_generation',payload->>'previous_generation','control_generation',payload->>'control_generation')
        AND payload->>'previous_mode' IN ('HUMAN','AI')
        AND payload->>'control_mode'=CASE event_type WHEN 'CONVERSATION_TAKEN_OVER' THEN 'HUMAN' ELSE 'AI' END
        AND CASE WHEN payload->>'previous_generation' ~ '^[1-9][0-9]{0,18}$'
                   AND payload->>'control_generation' ~ '^[1-9][0-9]{0,18}$'
          THEN (payload->>'previous_generation')::numeric<9223372036854775807
            AND (payload->>'control_generation')::numeric=(payload->>'previous_generation')::numeric+1
          ELSE false END) IS TRUE) OR ((event_type='ESCALATION_DECIDED' AND actor_kind='USER_ACCOUNT'
        AND actor_user_account_id IS NOT NULL AND object_type='ESCALATION' AND object_version=2
        AND escalation_object_id IS NOT NULL AND escalation_operation IS NOT NULL AND
        payload IN ('{"operation":"RESOLVE","status":"RESOLVED"}'::jsonb,'{"operation":"CANCEL","status":"CANCELLED"}'::jsonb)) IS TRUE)) OR ((event_type='MESSAGE_MATERIAL_CHANGED' AND actor_kind='CHANNEL_EVENT'
        AND actor_user_account_id IS NULL AND object_type='MESSAGE' AND material_target_id IS NOT NULL AND material_source_receipt_id IS NOT NULL
        AND platform.material_object(payload,ARRAY['target_id','source_receipt_id','previous_version','accepted_version','reason'])
        AND payload->>'target_id'=material_target_id::text AND payload->>'source_receipt_id'=material_source_receipt_id::text
        AND jsonb_typeof(payload->'previous_version')='string' AND jsonb_typeof(payload->'accepted_version')='string'
        AND platform.telegram_numeric_id(payload->>'previous_version') AND platform.telegram_numeric_id(payload->>'accepted_version')
        AND (payload->>'previous_version')::numeric+1=object_version AND payload->>'accepted_version'=object_version::text
        AND payload->>'reason' IN ('CONTENT_CHANGED','DELETED','ORDER_UNCERTAIN','ORDER_RESTORED','UNSUPPORTED_CONTENT')) IS TRUE));

CREATE TABLE platform.message_material_effects(
      workspace_id uuid NOT NULL,id uuid NOT NULL DEFAULT uuidv7(),target_id uuid NOT NULL,message_id uuid NOT NULL,
      source_receipt_id uuid NOT NULL,audit_event_id uuid NOT NULL,
      event_type text NOT NULL DEFAULT 'MESSAGE_MATERIAL_CHANGED' CHECK(event_type='MESSAGE_MATERIAL_CHANGED'),
      previous_version bigint NOT NULL CHECK(previous_version>0),accepted_version bigint NOT NULL CHECK(accepted_version::numeric=previous_version::numeric+1),
      reason text NOT NULL CHECK(reason IN ('CONTENT_CHANGED','DELETED','ORDER_UNCERTAIN','ORDER_RESTORED','UNSUPPORTED_CONTENT')),
      accepted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      PRIMARY KEY(workspace_id,id),UNIQUE(source_receipt_id,message_id),
      UNIQUE(workspace_id,id,target_id,message_id,source_receipt_id,previous_version,accepted_version),
      FOREIGN KEY(workspace_id,target_id,message_id) REFERENCES platform.message_material_targets(workspace_id,id,message_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,source_receipt_id) REFERENCES platform.telegram_provenance(workspace_id,receipt_id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,audit_event_id,message_id,event_type,accepted_version,target_id,source_receipt_id)
        REFERENCES app.audit_events(workspace_id,audit_event_id,object_id,event_type,object_version,material_target_id,material_source_receipt_id) ON DELETE RESTRICT);

CREATE TABLE platform.message_initial_suppressions(
      workspace_id uuid NOT NULL,id uuid NOT NULL DEFAULT uuidv7(),message_id uuid NOT NULL,target_id uuid NOT NULL,
      origin_inbox_id uuid NOT NULL,effect_id uuid NOT NULL,source_receipt_id uuid NOT NULL,
      previous_version bigint NOT NULL DEFAULT 1 CHECK(previous_version=1),accepted_version bigint NOT NULL DEFAULT 2 CHECK(accepted_version=2),
      initial_material jsonb NOT NULL,fold_witnesses uuid[] NOT NULL CHECK(cardinality(fold_witnesses) BETWEEN 1 AND 3),
      membership_disposition text NOT NULL CHECK(membership_disposition IN ('HIDDEN','INELIGIBLE_ORIGIN','ELIGIBLE_VISIBLE')),
      PRIMARY KEY(workspace_id,id),UNIQUE(workspace_id,message_id),
      UNIQUE(workspace_id,id,message_id,origin_inbox_id,membership_disposition),
      FOREIGN KEY(workspace_id,message_id) REFERENCES app.messages(workspace_id,id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,origin_inbox_id) REFERENCES platform.inbox_events(workspace_id,id) ON DELETE RESTRICT,
      FOREIGN KEY(workspace_id,effect_id,target_id,message_id,source_receipt_id,previous_version,accepted_version)
        REFERENCES platform.message_material_effects(workspace_id,id,target_id,message_id,source_receipt_id,previous_version,accepted_version) ON DELETE RESTRICT);

ALTER TABLE app.conversation_turn_messages
      ADD COLUMN membership_form text,ADD COLUMN initial_suppression_id uuid,
      ADD COLUMN suppression_disposition text GENERATED ALWAYS AS
        (CASE WHEN membership_form='INITIAL_FOLD_SUPPRESSED' THEN 'ELIGIBLE_VISIBLE' END) STORED,
      ADD CONSTRAINT turn_member_suppression_fkey FOREIGN KEY(workspace_id,initial_suppression_id,message_id,origin_inbox_id,suppression_disposition)
        REFERENCES platform.message_initial_suppressions(workspace_id,id,message_id,origin_inbox_id,membership_disposition) ON DELETE RESTRICT,
      DROP CONSTRAINT conversation_turn_messages_check;

ALTER TABLE app.conversation_turn_messages ADD CONSTRAINT conversation_turn_messages_check CHECK(
      (membership_form IS NULL AND initial_suppression_id IS NULL AND ((content_type='TEXT' AND file_id IS NULL) OR (content_type='IMAGE_REFERENCE' AND file_id IS NOT NULL))) OR
      (membership_form='INITIAL_FOLD_SUPPRESSED' AND membership_form IS NOT NULL AND initial_suppression_id IS NOT NULL
        AND content_type='IMAGE_REFERENCE' AND direction='INBOUND' AND file_id IS NULL) IS TRUE);
```

Complete added trigger definitions from the source expansion:

```sql
CREATE TRIGGER material_immutable BEFORE UPDATE ON platform.telegram_provenance FOR EACH ROW EXECUTE FUNCTION platform.turn_immutable();
CREATE TRIGGER material_immutable BEFORE UPDATE ON platform.message_material_effects FOR EACH ROW EXECUTE FUNCTION platform.turn_immutable();
CREATE TRIGGER material_immutable BEFORE UPDATE ON platform.message_initial_suppressions FOR EACH ROW EXECUTE FUNCTION platform.turn_immutable();
CREATE TRIGGER material_receipt_immutable BEFORE UPDATE ON platform.telegram_update_receipts
      FOR EACH ROW EXECUTE FUNCTION platform.messaging_immutable('codec');
CREATE CONSTRAINT TRIGGER material_integrity AFTER INSERT OR UPDATE OR DELETE ON platform.telegram_update_receipts DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.material_integrity();
CREATE CONSTRAINT TRIGGER material_integrity AFTER INSERT OR UPDATE OR DELETE ON platform.telegram_provenance DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.material_integrity();
CREATE CONSTRAINT TRIGGER material_integrity AFTER INSERT OR UPDATE OR DELETE ON platform.inbox_events DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.material_integrity();
CREATE TRIGGER material_target_check BEFORE INSERT OR UPDATE ON platform.message_material_targets FOR EACH ROW EXECUTE FUNCTION platform.material_target_check();
CREATE CONSTRAINT TRIGGER material_target_consistency AFTER INSERT OR UPDATE ON platform.message_material_targets DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.material_target_check();
CREATE TRIGGER material_no_file BEFORE INSERT ON app.file_objects FOR EACH ROW EXECUTE FUNCTION platform.material_no_file();
CREATE TRIGGER material_suppression_authority BEFORE INSERT ON platform.message_initial_suppressions FOR EACH ROW EXECUTE FUNCTION platform.material_suppression_check();
CREATE CONSTRAINT TRIGGER material_suppression_completeness AFTER INSERT OR UPDATE ON platform.message_initial_suppressions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.material_suppression_check();
CREATE CONSTRAINT TRIGGER material_suppression_completeness AFTER INSERT OR UPDATE ON app.conversation_turn_messages DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.material_suppression_check();
```

The source function closure is132 surviving functions:109 retained after the
predecessor's two explicit DROP statements, plus23 new. Seventeen retained bodies
are replaced;92 retain their predecessor body. All new functions use fixed
`search_path=pg_catalog,pg_temp` and owner `asm_migrator`;16 are SECURITY DEFINER,
7 pure validators/codecs are INVOKER (as listed below); all23
explicitly REVOKE PUBLIC/runtime, then only two narrow wrappers receive runtime
EXECUTE. Replacement preserves existing owner/ACL/signature/security. The table
below lists every surviving signature from source (argument names included);
runtime ACL is derived from ordered explicit GRANT/REVOKE source, not catalog evidence.

| Function signature | Source body | Runtime EXECUTE | Security |
|---|---|---|---|
| `app.current_messaging_owner_workspace_id()` | retained0011 | YES | DEFINER |
| `app.current_workspace_id()` | retained0011 | YES | DEFINER |
| `platform.auth_bootstrap(p_hash text, p_ttl integer)` | retained0011 | YES | DEFINER |
| `platform.auth_lock_session(p_hash text, p_exclusive boolean)` | retained0011 | NO | DEFINER |
| `platform.auth_login( p_previous text, p_account uuid, p_account_version bigint, p_credential_version bigint, p_new text, p_ttl integer)` | retained0011 | YES | DEFINER |
| `platform.auth_logout(p_hash text)` | retained0011 | YES | DEFINER |
| `platform.auth_memberships(p_hash text)` | retained0011 | YES | DEFINER |
| `platform.auth_password_lookup(p_login text)` | retained0011 | YES | DEFINER |
| `platform.auth_rotate(p_previous text, p_new text)` | retained0011 | YES | DEFINER |
| `platform.auth_session(p_hash text)` | retained0011 | YES | DEFINER |
| `platform.conversation_control_execute( p_conversation uuid,p_client uuid,p_operation text,p_key text,p_generation bigint,p_context bigint)` | retained0011 | YES | DEFINER |
| `platform.conversation_control_fingerprint( ws uuid,actor uuid,conversation uuid,client uuid,operation text,generation bigint,context bigint)` | retained0011 | NO | INVOKER |
| `platform.conversation_control_locked( p_conversation uuid,p_client uuid,p_operation text,p_key text,p_generation bigint,p_context bigint)` | retained0011 | NO | DEFINER |
| `platform.conversation_control_prepare( p_conversation uuid,p_client uuid,p_operation text,p_key text,p_generation bigint,p_context bigint)` | retained0011 | YES | DEFINER |
| `platform.conversation_control_read(p_conversation uuid)` | retained0011 | YES | DEFINER |
| `platform.conversation_manual_prelock(p_conversation uuid,p_text text,p_key text)` | retained0011 | YES | DEFINER |
| `platform.conversation_manual_takeover(ws uuid,p_conversation uuid)` | retained0011 | NO | DEFINER |
| `platform.conversation_turn_activation_matches(ws uuid,p_turn uuid)` | 0012 REPLACED | NO | DEFINER |
| `platform.escalation_command(p_escalation uuid,p_conversation uuid,p_client uuid,p_operation text,p_key text, p_version bigint,p_generation bigint,p_context bigint,p_answer text)` | retained0011 | YES | DEFINER |
| `platform.escalation_command_fingerprint( ws uuid,actor uuid,escalation uuid,conversation uuid,client uuid,operation text, version bigint,generation bigint,context bigint,answer text)` | retained0011 | NO | INVOKER |
| `platform.escalation_context_changed()` | retained0011 | NO | DEFINER |
| `platform.escalation_immutable()` | retained0011 | NO | DEFINER |
| `platform.escalation_list(p_count integer,p_status text,p_at timestamptz,p_id uuid)` | retained0011 | YES | DEFINER |
| `platform.escalation_now()` | retained0011 | NO | INVOKER |
| `platform.escalation_read(p_escalation uuid)` | retained0011 | YES | DEFINER |
| `platform.escalation_request_for_turn(p_job uuid,p_claim uuid)` | retained0011 | YES | DEFINER |
| `platform.escalation_request_replay(p_job uuid,p_claim uuid)` | retained0011 | YES | DEFINER |
| `platform.escalation_timer_execute(p_job uuid,p_claim uuid)` | retained0011 | YES | DEFINER |
| `platform.escalation_validity(ws uuid,p_escalation uuid,p_now timestamptz)` | retained0011 | NO | DEFINER |
| `platform.files_begin_fetch(p_job uuid,p_claim uuid)` | retained0011 | YES | DEFINER |
| `platform.files_claim_cleanup(p_limit integer)` | retained0011 | YES | DEFINER |
| `platform.files_finish_cleanup(p_intent uuid,p_claim uuid,p_error text)` | retained0011 | YES | DEFINER |
| `platform.files_finish_fetch(p_job uuid,p_claim uuid,p_intent uuid)` | retained0011 | YES | DEFINER |
| `platform.files_immutable()` | retained0011 | NO | INVOKER |
| `platform.files_manifest_valid(m jsonb)` | retained0011 | NO | INVOKER |
| `platform.files_plan(p_workspace uuid,p_message uuid,p_correlation uuid)` | 0012 REPLACED | NO | DEFINER |
| `platform.files_prepare_upload(p_job uuid,p_claim uuid,p_manifest jsonb)` | retained0011 | YES | DEFINER |
| `platform.files_read_manifest(p_conversation uuid,p_message uuid,p_file uuid)` | 0012 REPLACED | YES | DEFINER |
| `platform.files_upload_json(u platform.file_object_uploads)` | retained0011 | NO | INVOKER |
| `platform.guard_entitlement()` | retained0011 | NO | INVOKER |
| `platform.guard_plan_revision()` | retained0011 | NO | INVOKER |
| `platform.guard_require_current(ws uuid,p_turn uuid,p_resume uuid,p_context bigint)` | 0012 REPLACED | NO | DEFINER |
| `platform.guard_send_begin(p_job uuid,p_claim uuid)` | retained0011 | YES | DEFINER |
| `platform.guard_text_fingerprint(p_input jsonb,p_text text)` | retained0011 | NO | INVOKER |
| `platform.guard_turn_accept(p_job uuid,p_claim uuid,p_digest text,p_text text)` | retained0011 | YES | DEFINER |
| `platform.guard_turn_prepare(p_job uuid,p_claim uuid)` | retained0011 | YES | DEFINER |
| `platform.guard_turn_replay(p_job uuid,p_claim uuid,p_digest text,p_text text)` | retained0011 | YES | DEFINER |
| `platform.initialize_local_billing(p_workspace_id uuid,p_catalog_code text,p_catalog_revision integer,p_contact_display_name text,p_subscription_status text,p_funding_mode text,p_effective_from timestamptz,p_effective_until timestamptz,p_service_mode text)` | retained0011 | NO | DEFINER |
| `platform.initialize_local_messaging_billing(p_workspace uuid,p_contact text,p_from timestamptz,p_until timestamptz)` | retained0011 | NO | DEFINER |
| `platform.initialize_telegram_connection(p_workspace uuid,p_business uuid,p_bot text,p_external text,p_owner text,p_observation jsonb)` | retained0011 | NO | DEFINER |
| `platform.material_apply(ws uuid,p_target uuid,corr uuid)` | 0012 NEW | NO | DEFINER |
| `platform.material_apply_context(ws uuid,p_message uuid,corr uuid)` | 0012 NEW | NO | DEFINER |
| `platform.material_bind(ws uuid,p_message uuid,initial boolean,corr uuid)` | 0012 NEW | NO | DEFINER |
| `platform.material_bump_turns(ws uuid,messages uuid[],corr uuid)` | 0012 NEW | NO | DEFINER |
| `platform.material_content_valid(c jsonb)` | 0012 NEW | NO | INVOKER |
| `platform.material_fold(ws uuid,p_target uuid,p_source uuid)` | 0012 NEW | NO | DEFINER |
| `platform.material_identity(ws uuid,p_message uuid,p jsonb)` | 0012 NEW | NO | DEFINER |
| `platform.material_integrity()` | 0012 NEW | NO | DEFINER |
| `platform.material_no_file()` | 0012 NEW | NO | DEFINER |
| `platform.material_object(p jsonb,keys text[])` | 0012 NEW | NO | INVOKER |
| `platform.material_process(j platform.messaging_jobs)` | 0012 NEW | NO | DEFINER |
| `platform.material_processing_replay(p_job uuid,p_claim uuid)` | 0012 NEW | YES | DEFINER |
| `platform.material_result_valid(a jsonb)` | 0012 NEW | NO | INVOKER |
| `platform.material_semantic(c jsonb)` | 0012 NEW | NO | INVOKER |
| `platform.material_state_valid(v jsonb)` | 0012 NEW | NO | INVOKER |
| `platform.material_suppression_check()` | 0012 NEW | NO | DEFINER |
| `platform.material_target_check()` | 0012 NEW | NO | DEFINER |
| `platform.material_turn_usable(ws uuid,p_turn uuid)` | 0012 NEW | NO | DEFINER |
| `platform.message_effective(ws uuid,p_message uuid)` | 0012 NEW | NO | DEFINER |
| `platform.messaging_admit(p_job uuid,p_claim uuid)` | retained0011 | YES | DEFINER |
| `platform.messaging_begin_send(p_job uuid,p_claim uuid)` | retained0011 | YES | DEFINER |
| `platform.messaging_claim(p_worker text,p_until timestamptz,p_at timestamptz,p_id uuid)` | retained0011 | YES | DEFINER |
| `platform.messaging_fingerprint(e jsonb,projection boolean)` | retained0011 | NO | INVOKER |
| `platform.messaging_finish_send(p_job uuid,p_claim uuid,p_attempt uuid,p_outcome text,p_provider_message text,p_error text)` | retained0011 | YES | DEFINER |
| `platform.messaging_finish_send(p_job uuid,p_claim uuid,p_attempt uuid,p_outcome text,p_provider_message text,p_error text,p_retry_after_seconds integer)` | retained0011 | YES | DEFINER |
| `platform.messaging_guard(p_job uuid,p_claim uuid)` | retained0011 | NO | DEFINER |
| `platform.messaging_immutable()` | retained0011 | NO | INVOKER |
| `platform.messaging_ingest(p_provider text,p_bot text,p_event jsonb,p_correlation uuid)` | retained0011 | YES | DEFINER |
| `platform.messaging_job_json(j platform.messaging_jobs)` | retained0011 | NO | INVOKER |
| `platform.messaging_lock_billing()` | retained0011 | YES | DEFINER |
| `platform.messaging_lock_billing_workspace(ws uuid)` | retained0011 | NO | DEFINER |
| `platform.messaging_lock_owner(ws uuid,actor uuid)` | retained0011 | NO | DEFINER |
| `platform.messaging_manual_send_allowed(ws uuid)` | retained0011 | NO | DEFINER |
| `platform.messaging_prepare_text(p_conversation uuid,p_text text,p_key text)` | retained0011 | YES | DEFINER |
| `platform.messaging_process_inbox(p_job uuid,p_claim uuid)` | 0012 REPLACED | YES | DEFINER |
| `platform.messaging_read_connections(p_limit integer,p_at timestamptz,p_id uuid)` | retained0011 | YES | DEFINER |
| `platform.messaging_read_conversations(p_limit integer)` | retained0011 | YES | DEFINER |
| `platform.messaging_read_conversations(p_limit integer,p_at timestamptz,p_id uuid)` | retained0011 | YES | DEFINER |
| `platform.messaging_read_delivery(p_message uuid)` | retained0011 | YES | DEFINER |
| `platform.messaging_read_inbox(p_inbox uuid)` | retained0011 | YES | DEFINER |
| `platform.messaging_read_messages(p_conversation uuid,p_limit integer)` | retained0011 | YES | DEFINER |
| `platform.messaging_read_messages(p_conversation uuid,p_limit integer,p_at timestamptz,p_id uuid)` | 0012 REPLACED | YES | DEFINER |
| `platform.messaging_recover_expired(p_until timestamptz,p_at timestamptz,p_id uuid)` | retained0011 | YES | DEFINER |
| `platform.messaging_request_text(p_conversation uuid,p_text text,p_key text)` | retained0011 | YES | DEFINER |
| `platform.messaging_reschedule(p_job uuid,p_error text,p_retry boolean)` | retained0011 | NO | DEFINER |
| `platform.messaging_reschedule(p_job uuid,p_error text,p_retry boolean,p_delay integer)` | retained0011 | NO | DEFINER |
| `platform.messaging_reschedule(p_job uuid,p_error text,p_retry boolean,p_delay integer,p_nowait boolean)` | retained0011 | NO | DEFINER |
| `platform.messaging_retry(p_job uuid,p_claim uuid,p_error text,p_retry boolean)` | retained0011 | YES | DEFINER |
| `platform.messaging_valid_id(value text,max_chars integer,max_bytes integer)` | retained0011 | NO | INVOKER |
| `platform.messaging_validate_event(e jsonb)` | retained0011 | NO | INVOKER |
| `platform.resolve_workspace_membership(actor_id uuid, target_workspace_id uuid)` | retained0011 | YES | DEFINER |
| `platform.telegram_begin_send(p_job uuid,p_claim uuid,p_generation bigint,p_observation_version bigint,p_observation jsonb)` | retained0011 | YES | DEFINER |
| `platform.telegram_can_send(ws uuid,conn uuid,conversation uuid,same_uow boolean)` | retained0011 | NO | DEFINER |
| `platform.telegram_fingerprint(bot text,p jsonb)` | retained0011 | NO | INVOKER |
| `platform.telegram_fingerprint_v2(bot text,p jsonb)` | 0012 NEW | NO | INVOKER |
| `platform.telegram_ingest(p_bot text,p_projection jsonb,p_correlation uuid)` | 0012 REPLACED | YES | DEFINER |
| `platform.telegram_numeric_id(value text)` | retained0011 | NO | INVOKER |
| `platform.telegram_owner_observe(p_conversation uuid,p_generation bigint,p_observation_version bigint,p_observation jsonb)` | retained0011 | YES | DEFINER |
| `platform.telegram_probe_json(s platform.telegram_connection_state)` | retained0011 | NO | INVOKER |
| `platform.telegram_receipt_json(r platform.telegram_update_receipts,code text)` | 0012 NEW | NO | DEFINER |
| `platform.telegram_replay_v1(p_bot text,p_projection jsonb)` | 0012 NEW | YES | DEFINER |
| `platform.telegram_save_observation(ws uuid,conn uuid,p_generation bigint,p_version bigint,o jsonb)` | retained0011 | NO | DEFINER |
| `platform.telegram_validate_observation(o jsonb)` | retained0011 | NO | INVOKER |
| `platform.telegram_validate_projection(bot text,p jsonb)` | retained0011 | NO | INVOKER |
| `platform.telegram_validate_v2(bot text,p jsonb)` | 0012 NEW | NO | INVOKER |
| `platform.telegram_worker_probe(p_job uuid,p_claim uuid)` | retained0011 | YES | DEFINER |
| `platform.turn_consumer_finalize(p_job uuid,p_claim uuid,p_result jsonb)` | 0012 REPLACED | YES | DEFINER |
| `platform.turn_consumer_replay(p_job uuid,p_claim uuid)` | retained0011 | YES | DEFINER |
| `platform.turn_enqueue(ws uuid,p_turn uuid,corr uuid)` | 0012 REPLACED | NO | DEFINER |
| `platform.turn_execute(p_job uuid,p_claim uuid)` | retained0011 | YES | DEFINER |
| `platform.turn_group_message(ws uuid,p_message uuid,corr uuid)` | 0012 REPLACED | NO | DEFINER |
| `platform.turn_immutable()` | 0012 REPLACED | NO | INVOKER |
| `platform.turn_ingress()` | retained0011 | NO | DEFINER |
| `platform.turn_material()` | 0012 REPLACED | NO | DEFINER |
| `platform.turn_member_check()` | 0012 REPLACED | NO | DEFINER |
| `platform.turn_members_consistent()` | 0012 REPLACED | NO | DEFINER |
| `platform.turn_preflight(j platform.messaging_jobs,p_nowait boolean,p_terminal boolean)` | retained0011 | NO | DEFINER |
| `platform.turn_require_isolation()` | retained0011 | NO | INVOKER |
| `platform.turn_seal(ws uuid,p_turn uuid,p_seal timestamptz,corr uuid,bump boolean)` | 0012 REPLACED | NO | DEFINER |
| `platform.turn_snapshot(ws uuid,p_turn uuid)` | 0012 REPLACED | NO | DEFINER |
| `platform.turn_supersede(j platform.messaging_jobs)` | 0012 REPLACED | NO | DEFINER |
| `platform.update_billing_contact(expected_version bigint,contact_display_name text,idempotency_key text)` | retained0011 | YES | DEFINER |

Changed capability profiles: ingress accepts fresh V2 only, with a separate saved-V1
replay wrapper; PROCESS_INBOX has a closed material terminal and own winning-claim
replay wrapper; owner message read returns required current; image manifest read
requires ORIGINAL_READY; Turn execute/guard prepare may return V2 snapshots while
old persisted V1 is decoded unchanged; consumer finalize uses effective current;
shared activation/enqueue/admission reject sticky invalidated/no visible input;
original/File/SENT share the context/apply path. Other public signatures and scope
authority are retained. No runtime arbitrary ws material setter is added.

Immutable downgrade source copies (SHA256 of each complete `ORIGINAL` Python string,
UTF-8, no strip; equality to final0011 source checked after only CREATE prefix normalization).
Trailing whitespace in two fixed source literals is encoded as Python `\x20`,
so the decoded predecessor bodies/CHECKs remain byte-identical and the new source
passes `git diff --check`:

| Function key | SHA256 |
|---|---|
| `telegram_ingest(3)` | `d4f721a95492512516dfa2fee8ebf8f328ac65c9397ab495e6079df93a36e150` |
| `messaging_process_inbox(2)` | `0553893a279d6e99ec9e31d5ef53bb0cb2892f163a06c75dae734e868b102d14` |
| `files_plan(3)` | `0c54939f99ea35d3c51c82b62ee95d72bba52684a9089306715fa90ba0746e9b` |
| `turn_group_message(3)` | `d243c77f84df2a6f76acfae76609ec574010842c4af378ed0281d96f9df07984` |
| `turn_member_check(0)` | `90e436d84b4b5d4e7f5f3af84305c9fd128e244a7d834f1ac0b6db337544c90d` |
| `turn_members_consistent(0)` | `24cb6bbf1f87abfa7db79ae01d74066edf54e8e479aba52a3803558708a06ca9` |
| `turn_immutable(0)` | `7c791be6b0014ef1fdb33362e6d60dc85606dc93ae03066c7ed1ff7d611f352c` |
| `turn_material(0)` | `cca96d0b3fd2e3d62057b433b2da496d49c048d6bbdd1e5fb20469068cb0279e` |
| `turn_seal(5)` | `f6b0af975822f3b3583cb7098057a268344ad7015361fa9afdc625a3c4260d7b` |
| `turn_enqueue(3)` | `5e05c02a6eb9d7d6f26b8d40ae52cc8933649dc63bd6b49d29ce8ee464526cd0` |
| `conversation_turn_activation_matches(2)` | `6490af54d1eb8f2ce910fb92756d52a7c1efeb74bcdef2711f750d417af13591` |
| `guard_require_current(4)` | `5f1d2af143058b6c31c5ee2cdf143d4820bc1ba618ae511415f4c0b4c40d6aba` |
| `turn_snapshot(2)` | `c08f501ab8531f74b179c9bf64d442a5af7f4581231f82854a468b00954937c8` |
| `turn_consumer_finalize(3)` | `b507659817f6faac9511b75b6f1f7458befbfbab331b3b124597b9c7d6e2613a` |
| `turn_supersede(1)` | `3dc2768dc757cc236a1f562aafb0e8fb87a94809d120a6c275a7cccfb90db904` |
| `files_read_manifest(3)` | `de7c4b4dee362402f324f203749fccd910ecc0a11bb2a37d64f6f5968e0354a9` |
| `messaging_read_messages(4)` | `948fc60122590b14343789ba1534d18ae5466fa1595120508ae4c0b0798cf967` |

The four fixed predecessor CHECK strings are likewise stored in0012, never captured
from a live catalog during upgrade:

| Fixed CHECK | SHA256 of UTF-8 Python string |
|---|---|
| `OLD_RECEIPT_CHECK` | `2c33d64a122148d0e62bf3c1fd34610bee6b0e7d0dfea60faf36bda981b7f6be` |
| `OLD_INBOX_CHECK` | `7eeb77ebb9bfeddf15abf0a9215ac03f1752270691caca802d2061c60b77f804` |
| `OLD_MEMBER_CHECK` | `fd1eb0e3703a811a9f881cc871d8d2838691e857372a93372b8a2cff84b5d809` |
| `OLD_AUDIT_CHECK` | `da07204e67d993452b643699ad6e35406bf231755f776226d953afcb60e0a6e1` |

Downgrade takes the explicit ownership-table ACCESS EXCLUSIVE locks, then refuses
with SQLSTATE55000 **before any DDL** if any receipt codec, sidecar, target, effect,
suppression, material Inbox result/token/code, invalidated Turn, new member form/evidence,
material Audit or enabled material gate exists. Unused reversal restores the17
fixed bodies and4 predecessor CHECKs, drops only owned0012 additions and never
CASCADE/deletes history. Actual all42 row/catalog equality is pending integration.

| Sequential source/schema lane for C6 | Closed projection / boundary |
|---|---|
| Frozen H source `754f1c883e5a94a7fc9e729af2605424f949ba33` /0007 | Existing H projection31 and frozen assertions; historical sources are not rewritten |
| Frozen T source `ea1ae98ce9e5e26d5d0d14f3e6d278ecb9efbbad` /0008 | Existing T projection34; original CONTROL phase0008→0009 retained |
| Frozen C source `c6a55b6b17d1c1ab286ce97dfa4bd27197141fe5` /0009 | Existing C projection35; GUARDS phase0009→0010 retained |
| Frozen G source `c502d5fd258aef15bb5549e1529df8d038a4fb9b` /0010 | Existing G projection36; Escalation phase0010→0011 retained |
| E/predecessor source `933ddd284ff5b77fb1aa88a4270ab0032bc499c9` /0011 | Exact `E_COLUMNS`38; used history/V1 bytes preserved; full actual catalog read required |
| P/current C3 source checkpoint /0012 | Exact `P_COLUMNS`42 above; current Runtime/provisioner readiness accepts only0012; cross-pair source/schema refusal required |
| Future renewal | No revision/source/profile assigned; never run concurrently with material preparation |

Historical first-checkpoint handoff (superseded for R1 by §15.10.4):
C6 receives exact accepted C3 head from a separate C0 issuance, works sequentially,
and owns only `scripts/prepare_telegram_egress.py`, `scripts/test_telegram_egress.sh`,
`scripts/test_telegram_egress_migration.sh`, `tests/test_telegram_egress.py`,
`tests/test_telegram_egress_migration.py`, `tests/test_telegram_egress_postgres.py`.
All six remain byte-identical in this C3 checkpoint. C6 must extend the current
source/schema0012 capability/catalog assertions while retaining all old frozen
controllers/projections, failure ownership/cleanup and9-job clean-source gates.
The old egress profile currently stops at0011; this checkpoint is intentionally
handed off before a PR, since egress runs before backend integration in foundation.

#### 15.10.3. Historical local evidence, 2026-10-15 checkpoint; deferred execution

| Проверка этого source checkpoint | Фактический результат |
|---|---|
| `uv sync --frozen`; `npm --prefix frontend ci --ignore-scripts` | Locked dependencies prepared; lockfiles unchanged |
| `uv run --frozen ruff check backend tests scripts migrations` | PASS |
| `uv run --frozen ruff format --check --diff backend tests scripts migrations` | PASS,149 files already formatted |
| `uv run --frozen mypy backend/src` | PASS,61 source files |
| `uv run --frozen pytest -q -m 'not integration' tests/test_m3_1_provenance.py tests/test_m2_3_transport.py tests/test_foundation.py tests/test_m2_3_setup.py tests/test_m2_4_browser_fixture.py tests/test_m3_1_turns.py tests/test_m3_1_guards.py tests/test_m2_3_api.py` | PASS,284 tests;2 existing Starlette/AnyIO deprecation warnings |
| `uv run --frozen python scripts/export_contracts.py --check` | PASS |
| `npm --prefix frontend run typecheck` | PASS |
| `npm --prefix frontend test -- src/messaging-api.test.ts src/MessagingPanel.test.tsx src/billing-api.test.ts src/BillingPanel.test.tsx` | PASS,93 tests/4 files |
| `npm --prefix frontend run build` | PASS,38 modules |
| `uv run --frozen pytest --collect-only -q -m integration tests/test_m3_1_provenance_postgres.py tests/test_m3_1_provenance_migrations.py tests/test_m2_3_wire_postgres.py` |103 collected; **collection only**, no PG execution |
| DDL source expansion / frozen bodies |131 `op.execute` calls;4 new tables;23 new+17 replaced functions;17 predecessor copies exact after CREATE/CREATE OR REPLACE normalization |
| `git diff --check`; allowlist/prefix/original11/applied migrations/C6 reserved checks | PASS at canonical checkpoint; exact head/tree/path numstat in PR33 receipt |

| Обязательный remaining gate | Статус и следующий executor |
|---|---|
| Actual PG identity/codec/fold/terminal/counters/R3-T1…T5/File/grant/shared body | **NOT RUN — deferred to штатный final candidate CI** |
| Fresh/populated/repeat migrations, all42 fingerprints, exact unused catalog reverse, used refusal, schema/source pairing | **NOT RUN — deferred to штатный final candidate CI**; C6 compatibility preparation first |
| Real workers/process death/rollback/ACK loss, connection/C/SENT/FK barriers, NOWAIT/reclaim/expiry/overflow | **NOT RUN — deferred to штатный final candidate CI** |
| Runtime non-owner/FORCE RLS/private ACL/auth/CSRF/wrong Workspace/Client and retained security regressions | **NOT RUN — deferred to штатный final candidate CI** |
| Paired Docker API/PostgreSQL/Console browser journey and retained39 browser regressions | **NOT RUN — deferred to штатный final candidate CI** |
| Final candidate nine automatic jobs and nine clean-source checks; exact PR head/tested merge SHA/tree | **NOT RUN**; no PR/dispatch/rerun in this source-only handoff |

Local environment has no PostgreSQL/browser services; no additional service
installation was performed after the continuation. Unit/static/build evidence is
not PostgreSQL, race, catalog, browser or account evidence. Full prior backend/browser
suites were not requested locally. Existing main/design CI does not certify this code.


#### 15.10.4. C3-M3.1-MATERIAL-R1 correction / 2026-10-16 UTC

[C0 assignment](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6201238585),
[C0 findings/disposition](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6201199649).
Separate clean checkout/branch `c3/m3-1-material-r1`, exact parent/base
`ef7b52d2d862e3d3e656ba56ccac8781e1d0a374`, tree
`e4317cc6478b2c40669d96242c3adb89079ab46c`; frozen E/main stays
`933ddd284ff5b77fb1aa88a4270ab0032bc499c9`/0011. Final head/tree/parents/numstat are in
one canonical PR34 receipt. PR34 remains Draft; C3 does not update its C6 branch.
Findings remain **OPEN pending C0 review and actual acceptance**, not CLOSED/VERIFIED.

| Finding | Substantive R1 correction / executable proof |
|---|---|
| C2-MAT-01 | Parenthesize exactly two IF CASE expressions in telegram_validate_v2 and one in material_suppression_check. Predicates unchanged. Existing MIG fresh/populated/repeat/unused reverse and positive R3 suppression nodes remain actual PG gates. |
| C1-MAT-01 | New nullable private Inbox material_claim_token uuid, no default/backfill. Closed result/token pair; verified V2 EDIT/DELETE only. Final admitted claim recheck precedes atomic Inbox pair + Job SUCCEEDED. All five retained Job delivery fields remain NULL; no fake send outcome or widening of0005. Replay joins exact Job/Inbox/provenance and stored token. New terminal-pair/pending/NEW/nonbinding/OFF negatives; populated MIG includes actual saved-V1 refusal; all saved-results positives assert NULL delivery fields. Restart/ACK-loss now asserts saved winning token, wrong Job/token refusal and historical result after a later deletion; reclaim test rejects the old token even after the new winner commits. |
| C1-MAT-02 | New known-Turn test has three arms: real Telegram ingress/Worker, CONTROLLED same private apply body for GUARDS, CONTROLLED same body with real TEXT Escalation marker. Captured T is collecting; mutation preserves its member/origin/capture/deadlines; fresh input actually arrives before old quiet_at and creates T2. Real GROUP/MEDIA, late File WINNER, owner Takeover/Resume retain invalidation. Read predicates use fresh DB context/revision/Resume under C/Turn barriers, including pre-Resume matching generation/fence; T has no new consumer/guard/Escalation/outbox authority. CONTROLLED T2 supplies a positive ordinary producer neighbor. No row-edited authority or Telegram AI producer. |
| R3-T4 discrimination | Each corruption maps to exact SQLSTATE + CHECK name or precise exception/context. Wrong identity uses P0002 from material_suppression_check lookup, not an arbitrary DB exception. Same claim/original successfully commits after only the corruption trigger is removed; all42 rollback remains checked before that positive neighbor. |
| C5-MATERIAL-01 | Four finite PHOTO originals, real FetchTransfer/private TEST S3/File/WINNER. Three paired journeys load original, apply same-ref caption (new successful grant/load), then replacement/type change/delete through ordinary Worker.execute and canonical replay read. Current/history, loaded-image removal, old-file grant404, unchanged original/File/upload digests and File/FETCH counts are asserted. Fourth journey holds route.fetch's actual200 grant response, performs semantic mutation+refresh, then releases it unmodified and observes no image/request restoration. Component loaded-image test is supplementary. Already issued URL TTL remains explicit. |

R1 storage inventory is **10 columns/6 existing tables,4 new/42 total tables,
23 new+17 replaced/132 surviving function signatures**. Only one additional column
relative to reviewed PR34. ORIGINAL17 and OLD_CHECK4 are byte-exact;0001–0011 and
normative§15.2–15.9 unchanged. Unused downgrade drops token with result; used55000
guard checks token before DDL. P_COLUMNS, no-backfill, current C6 source inventory
and existing used-result witness include token. Token has no new child/FK cleanup
edge: ordinary fixture deletion removes the owning Inbox, never clears its write-once
pair separately. C6 coordinator/shell/budget/ownership code is not changed.

| Command / local evidence | Result |
|---|---|
| `uv run --offline --frozen ruff check <changed Python paths>`; `ruff format --check <changed Python paths>` | PASS,9 changed Python files |
| `uv run --offline --frozen pytest -q -m 'not integration' tests/test_m3_1_provenance.py tests/test_m2_4_browser_fixture.py tests/test_telegram_egress.py -k 'material or provenance or seed'` |79 passed,152 deselected; includes exact frozen17/4 and current inventory checks |
| `uv run --offline --frozen pytest -q tests/test_m2_4_browser_fixture.py` |68 passed; includes retained finite actions/seed/PENDING boundary and new byte-provider/Worker/readback guards |
| `npm --prefix frontend run typecheck` | PASS, includes e2e TypeScript |
| `npm --prefix frontend test -- src/MessagingPanel.test.tsx` |32 passed; DOM/component evidence only |
| `pytest --collect-only -q -m integration tests/test_m3_1_provenance_postgres.py tests/test_m3_1_provenance_migrations.py tests/test_m2_3_wire_postgres.py` via frozen offline uv |121 collected, not executed |
| Cached pglast8.6/PostgreSQL18.6, no repository dependency | Both formerly failing expanded operations4/61 now parse; all131 top-level SQL operations parse. Four pre-existing standalone PL/pgSQL catalog/type-resolution limitations at66/67/70/77 are unchanged from exact base; not actual migration/PG execution. |
| Diff/allowlist/original11/applied0001–0011/normative sections/ORIGINAL17/OLD_CHECK4/source signatures | PASS; original attachments = repository = manifest11; source count132 |

Local PostgreSQL/Docker/paired browser/migration/catalog/concurrency/actual R3/
private-S3 acceptance **NOT RUN**. No services installed, skip/xfail, alternative
runner, workflow dispatch/rerun or new PR. Existing failed PR34 CI is historical
review evidence, not an R1 test run. C2-MAT-02 budget remains **OPEN, C6 scope**.
C0 intake → assigned C6 descendant → existing PR34 automatic CI → C1/C2/C5 review
and actual PG/browser acceptance. C3 HOLD after return. Gate OFF; native/latest-state,
renewal/collector/P-A03-09/live/VM/working DB/S3/sends/deploy/M4 remain unissued.

### 15.11. C0 — terminal MATERIAL preparation720 exception / 2026-10-16 UTC

[Explicit C0 intake/decision](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6207691746),
[C6 implementation assignment](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6207709114),
[C6 actual-budget analysis](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6207442994).
This section is the narrow accepted override of the earlier blanket600/no-new-budget
wording in §§12.8/13/14/15.7 **only for terminal MATERIAL admission/preparation**.
It does not rewrite historical results, change any other budget or open IMPL-05.
The entire existing contract through§15.10.4 is preserved byte-for-byte.

#### 15.11.1. Decision, measured cause and unchanged execution

One original monotonic start **S** remains established before T. H/predecessor
execution stays before that ledger, exactly as in the accepted harness. Retained
T/C/G/E keep **D_retained=S+600** and their original version1 requests/consumers.
Only P admission/source/archive/build/reuse/image-probe preparation receives
**D_material=S+720** from that same S. This is an explicit **120-second increase**
of the terminal cumulative limit, not an optimization that satisfies600 and not a
fresh720 allocated at P. Every preceding elapsed cost remains charged: full T
positive, genuine120-second command-timeout negative, export negative, C/G/E
preparation/runtime/supervision/report retention/owned cleanup and handoff costs.
No clock reset/shift, nested fresh allowance or subtraction of those durations.

Failed CI38793747628/attempt1, tested merge
`d6f2bd1eeceaebebb7140940f6b6d23ab98ddb26`, analysed head
`ef7b52d2d862e3d3e656ba56ccac8781e1d0a374`, produced these actual facts:

| Lane | Elapsed at P guard | Remaining600 | Remaining720 before P preparation |
|---|---:|---:|---:|
| normal |603.658495599s|−3.658495599s|116.341504401s|
| Docker29 |679.481488282s|−79.481488282s|40.518511718s|

Both E exits were0/cleanup PASS. P never started; its report was absent. Pre-C
276.016/306.369s includes the two required full T negatives, not unexplained idle
time. ZIP/source/timing bindings and the complete nonoverlapping decomposition
are in the C6 analysis. That evidence belongs to the failed source above and
does not certify C3 R1 or this C6 descendant.

720 is **not a guaranteed fit, mathematically minimal value or general new budget**.
Actual P preparation/runtime and the full state25min job remain separate gates.
Failure at the amended bound returns BLOCKED to C0 with exact evidence; there is
no authorization for another increase, automatic retry/rerun or assertion skip.
C2-MAT-02 remains OPEN pending complete final normal and Docker29 execution.

Sequence stays T positive → real timeout negative → export negative → C → G → E
→ P → all three original C cleanup negatives. Source archives/images, byte probes,
all frozen function bodies/selectors/requests, readiness/recovery/refusal cycles,
failure retention and source-clean gates remain mandatory. `SchemaOwnership`,
`RetainedCheckpoint`, supervisor/process-group termination and cleanup code do not
change. Existing P supervision remains **remaining+480**, hence the nominal
absolute terminal bound becomes **S+1200**. Shared owner cleanup90, individual
build480/controller-start120/migration-probe30/drain60/normal-command40 and late
C-negative supervisor480 remain. State25min/browser25min/foundation45min, nine
jobs/clean9, existing pins/artifacts/Compose/dependencies remain unchanged. The
supervisor bound alone does not guarantee that the complete job fits25min.

#### 15.11.2. Closed P-only protocol and evidence gates

The coordinator issues P only after successful E exit, final exact E source/clean
verification, report retention and successful owned cleanup. It reads the retained
E report, verifies phase/source/image tree, the original600 budget, completed
used-refusal/timer evidence and cleanup owner, then records the observed completion
after export/cleanup/worktree removal. The request is private0600/current uid,
single-link, one-use and bound to the new P owner's nonce.

| Version2 field | Exact semantics |
|---|---|
| `version`, `phase`, `historical`, `candidate` |2; MATERIAL_SCHEMA_0011_0012; frozen E933ddd…; actual checked-out final C6 descendant. R1 is the base, never substituted for final P. |
| `uid`, `owner_token` | Exact current uid and admitted asm-material-schema-phase owner nonce/source/phase. |
| `started_at`, `retained_deadline`, `deadline`, `extension_seconds` | Original S; exactly S+600; exactly S+720; fixed integer120. No tolerance extends admission. Stored deadline comparisons use addition from S, avoiding float-subtraction equality errors. |
| `issued_at`, `charged_seconds` | Actual issue time and exactly issued_at−S, including all retained work. |
| `escalation_completion` | Closed object: exact E source/tree, source_clean=true, exit_code=0, cleanup_state=PASS, E owner nonce, SHA256 of the retained E report, its ended-at and coordinator-observed completed-at. |

The child independently rereads/hash-checks that retained report and its original
S+600/source/phase/cleanup/image binding. Required order is E report end ≤ observed
E completion ≤ P issue ≤ child observation. Missing/incomplete/failed E, stale or
changed report, reset S, wrong phase/source/owner/extension/deadline, changed file
device/inode/content or private-file guards, reused or exhausted requests refuse
before P runtime. The request file is removed only after successful validation.

At admission the child records `observed_at`, `charged_at_observation=observed_at−S`
and the true handoff delay/remaining. Source/ancestry/daemon admission and every
archive/build/reuse/probe use only remaining D_material. The separate frozen G
development-image verification is inside this preparation. Final evidence records
`preparation_ended_at`, `charged_total_seconds=preparation_ended_at−S` **<720**, both
absolute deadlines, candidate preparation duration and image preparation duration.
Preparation failure retains the actual stop/charge and primary/secondary/owned
cleanup evidence. No P report claims PASS600.

The outer shell cross-checks the material report against the coordinator handoff,
same S, both deadlines,120 extension and supervisor bound, exact saved E report
hash/owner/completion order, P owner and admission/final-preparation arithmetic.
The original schema/recovery/42-table/cleanup checks still run. A unit/mocked
protocol check is not actual PostgreSQL/catalog/timing acceptance.

#### 15.11.3. C6 source checkpoint, tests and remaining gates

Branch `c6/m3-1-material-compat-r2` starts from accepted C3 R1
`e7f554772ad4dd697d38c88f4f6423b3d3895499`, tree
`0242e71790e0fe441ebc55a6311c80f5681b218f`, sole parent
`ef7b52d2d862e3d3e656ba56ccac8781e1d0a374`. Main/frozen E remains
`933ddd284ff5b77fb1aa88a4270ab0032bc499c9`/0011. The existing Draft PR34 head is
not changed by this source task. Final C6 head/tree/parent/numstat and verification
are bound in one canonical PR34 receipt, without a self-SHA/status-only commit.

Only five assigned existing paths change: current material coordinator/consumer/
preparation/report and protocol units in `tests/test_telegram_egress_migration.py`,
outer evidence gates in `scripts/test_telegram_egress_migration.sh`, this appended
section, current handoff and task register. R1 inventory/used witnesses in the two
other egress test files are read-only:10 columns/6 existing tables,4 new/42 total,
132 signatures, private Inbox material_claim_token, full P_COLUMNS/no-backfill,
used55000 before DDL/raw42 preservation, unused exact reverse and ORIGINAL17/
OLD_CHECK4 remain. No new DDL/product/workflow/image/dependency capability.

| Protocol requirement | Executable unit evidence in test_telegram_egress_migration.py |
|---|---|
| Valid after600/before720; fixed S/deadlines/delta; closed/private/source/owner/E/reuse failures | `test_material_budget_preserves_original_S_terminal720_private_binding_and_single_use` |
| Changed inode/content or expiry during validation; exact fractional endpoint | `test_material_handoff_changed_or_expired_during_validation_cannot_be_consumed`; `test_material_budget_fractional_deadlines_use_stored_absolute_values` |
| Missing request and early failure report; no runtime | `test_material_phase_early_failure_reports_budget_and_performs_no_runtime` |
| Full source/archive/reuse/probe/G-probe charge; end720 refusal, strict just-before720 positive boundary; primary/cleanup behavior | `test_material_entrypoint_accounts_full_preparation_and_refuses_before_runtime` |
| Actual current coordinator entry, original sequence/retained600 requests, E exit/source/report/cleanup refusal, expired P admission and late C-negative call | `test_current_coordinator_binds_completed_E_and_full_elapsed_to_terminal720` |
| Executed outer-shell report gates and tampered deadline/charge/E/owner/supervisor evidence | `test_material_shell_validates_original_S_completed_E_and_terminal720_report` |

Scoped unit command in the existing frozen offline environment:
`uv run --offline --frozen --no-sync pytest -q -m 'not integration' tests/test_telegram_egress.py tests/test_telegram_egress_migration.py`
with UV_PROJECT_ENVIRONMENT selecting the existing environment: **625 passed**.
Ruff/check/format, shell/embedded-Python compilation and exact scope/prefix/frozen
source audits are recorded with their actual results in the canonical receipt.
These local results do not certify runtime720 feasibility.

Actual PostgreSQL/Docker/image builds/paired PHOTO/browser/CI execution are
**NOT RUN in this source task**. No service/dependency installation, dispatch,
rerun, new PR or push to the old PR34 branch. Five findings remain OPEN;
MATERIAL/M3 IN_PROGRESS, implementation not INTEGRATED/VERIFIED. C6 HOLD after
canonical return; C3/C1/C2/C5/C8 HOLD until C0 assignments.

Next: C0 exact source intake → move the combined descendant into the same Draft
PR34 → one normal automatic CI → C1/C2/C5 re-review final source/actual evidence;
C8 follows required gates. Required:9/9+clean9/9 on exact tested SHA/tree, both
normal/Docker29 full P preparation<720 from original S, complete retained negatives/
owned cleanup within state25min, actual0012 migrations/catalog/42-table hashes/
recovery/refusal/security/races and paired PHOTO/browser acceptance. Gate OFF;
live/VM/working DB/S3/sends/deploy/native/renewal/collector/M4 remain unissued.

### 15.12. C3-M3.1-MATERIAL-R2 — online SQL parameter correction / 2026-10-16 UTC

[C0 assignment](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6208530769)
and [binding disposition](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6208519238).
Separate branch/checkout `c3/m3-1-material-r2`, exact base/sole parent
`d810dde939f727085af15f7614eeddd36f4909b8`, tree
`fb06ad7bf5cf4d821e880328888c9bbf25eea3b7`; base parent is accepted R1
`e7f554772ad4dd697d38c88f4f6423b3d3895499`. Main/frozen E stays
`933ddd284ff5b77fb1aa88a4270ab0032bc499c9`/0011. Final head/tree/numstat are in the
canonical PR34 receipt, not a self-SHA commit. The complete preceding contract
through§15.11 is unchanged:546352 bytes, SHA256
`79f920fdf779236e33c7b622f31a9e8ee750ea87596431378a880dbae6a65ae4`.

C2-MAT-03/P1 correction adds one space after the colon in exactly six new0012 JSON
literals (base lines578/586/1048/1049/1207/1208) and the actual PG forged-basis setup
literal (line770). All seven decoded JSON values are equal before/after. No other
migration or PG-test behavior changes: the invalid proof, precise SQLSTATE/reason/
function context, all42 rollback and same-claim positive neighbor remain intact.
No executor workaround, fake null bind, preprocessing or dependency change.

Two new nonintegration nodes in `tests/test_m3_1_provenance.py` use untouched source:
`test_material_upgrade_online_has_no_required_parameters` invokes actual upgrade
through online Alembic Operations/_exec and a TextClause execution sink;
`test_material_forged_basis_setup_online_has_no_required_parameters` invokes the
actual PG case with only preceding domain fixture work mocked, and stops after its
real CREATE reaches the sink. Both use PostgreSQL/psycopg compilation and empty
`construct_params` semantics, require an empty result, and never sanitize SQL.

| R2 local command/evidence | Result |
|---|---|
| Both new nodes against unchanged d810dde migration/PG setup |2 FAILED with the intended `InvalidRequestError: A value is required for bind parameter 'null'`; migration first fails at expanded operation2/material_semantic, setup fails before its negative assertion |
| Same two nodes after the seven spaces |2 PASSED |
| Independent expansion + psycopg empty-parameter construction | Base failures exactly indices2/3/48/58; candidate all131 operations PASS, no required parameters; not PostgreSQL execution |
| `uv run --offline --frozen --no-sync pytest -q -m 'not integration' tests/test_m3_1_provenance.py tests/test_telegram_egress.py -k 'material or p_a03 or r3'` |67 passed,98 deselected; includes the two new nodes and retained inventory/reverse/source companions |
| Ruff check / format --check on the three changed Python paths; git diff --check | PASS |
| Read-only source audit | Original11 attachments/repo/manifest, applied0001–0011, ORIGINAL17/OLD_CHECK4, six-path scope and exact immutable contract prefix PASS |

Reused cached frozen environment: Python3.13.16, SQLAlchemy2.0.52, Alembic1.20.0,
psycopg3.3.5, pytest9.1.1; UV_PROJECT_ENVIRONMENT selects the existing R1 venv and
PYTHONPATH=backend/src:tests binds this checkout. No installation/sync/services.
Inventory remains10 columns/6 old tables,4 new/42 total,132 function signatures;
Inbox immutable result/winning-token pair and five NULL Job delivery fields remain.
All C6 code and frozen H/T/C/G/E identities/bodies, original-S terminal720 with
retained600, supervisor/cleanup/individual bounds and9 jobs/clean9 are unchanged.

Historical final CI38850821014/attempt1 tested merge
`51fca8a26bb19fa511040592a8b04613ddf0eb96` (main+base, base tree):
**4 SUCCESS/5 FAILURE; clean4 SUCCESS/5 SKIPPED**. Foundation, compatibility and
browser stopped at migrate exit1; Docker29 state stopped at first upgrade0012.
No retained migrate traceback/DDL/SQLSTATE proves MAT-03 was the observed CI error.
Normal state has a **separate unknown H-build blocker** before T/P; failed target,
numeric exit and stderr were not retained. Do not infer its cause from MAT-03 or
Docker29 H success. Docker29 P preparation499.951432356s is **PARTIAL**; neither
complete state lane passed. C0/C2/C6 receipts retain those detailed observations.

All six findings remain OPEN: C2-MAT-01/P1, C1-MAT-01/P1, C1-MAT-02/P2,
C5-MATERIAL-01/P2, C2-MAT-02/P2 and C2-MAT-03/P1. This source/client PASS closes none.
Actual0012 fresh/populated/repeat/unused reverse/used55000-before-DDL/raw42/catalog/
security/recovery/replay, known T→T2/current-version refusals, paired PHOTO/browser,
both full state lanes including3 late C negatives and9/9+clean9/9 remain required.
PG/Docker/browser/image builds/Actions execution **NOT RUN in R2 by task scope**.

Next: C0 source intake → separately assigned C6 diagnostics-only work on the exact
accepted C3 descendant → combined source intake → same PR34 normal automatic CI
→ C1/C2/C5 actual/source disposition → later C8. No intermediate PR-head update,
new PR, merge, dispatch/rerun or edits to other receipts. C3 HOLD after return;
C1/C2/C5/C6/C8 HOLD until C0 issuance. PR34 Draft/BLOCKED; MATERIAL/M3 IN_PROGRESS,
implementation not INTEGRATED/VERIFIED. Gate OFF; native/A08/renewal/collector/live/
VM/working DB/S3/sends/deploy/M4 unissued; broad CI optimization/IMPL-05 DEFERRED.

### 15.13. C6-M3.1-MATERIAL-CI-DIAG-R2 — bounded original-invocation diagnostics / 2026-10-16 UTC

[C0 assignment](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6208852583),
[accepted C3 intake](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6208831490),
[C3 source receipt](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6208752834),
[historical C6 diagnosis](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6208328996).
Separate branch/checkout `c6/m3-1-material-ci-diag-r2`, exact accepted base `f0c111ac0b74695cc12444ccdf077314d06d2a9b`, tree
`ca3f638b206b232a7a6cd8f1920e31580991b58b`; its parent is d810dde939f727085af15f7614eeddd36f4909b8.
Main/frozen E remains933ddd284ff5b77fb1aa88a4270ab0032bc499c9/0011.
Existing Draft PR34 remains on `c6/m3-1-material-compat`/d810dde; no PR-head update.
The complete contract through§15.12 is preserved: **551663 bytes**, SHA256
`0be54876bec43bc88348586ccf8e7b99571be02207ed9af9773fcd06ce75f050`.
Only this section is appended. Two focused source commits retain the accepted base;
the final immediate parent is711934148b3921047501ff3e3c3b6e6ff34c74a4. Final head/tree/
combined numstat appear in the canonical receipt.

D1 observes the **same original H invocation**, only in the two existing state
shards. Image/intent still invoke their original shell directly. The current
wrapper sets up a private startup ZIP outside H; its sitecustomize entry establishes
observation and lets Python itself execute the original stdin program. No stdin
consumption/rewrite or alternate executor; argv/cwd/interpreter and original helper
objects remain intact. PYTHONPATH and sys.path are restored before original code;
temporary bytecode suppression is restored after importing H, without inserting
observer files or caches into H. Unrelated interpreter invocations pass through.

The original `e.command.__code__` is selected, with its original
`migration_build_images.__code__` caller and actual build argv checked in memory.
Only matching H docker builds are recorded; target runtime/development comes from
that invocation, never from loop order. No command/helper/subprocess rebinding,
duplicate call, probe build or retry. Evidence is labelled
**INSTRUMENTED_IMMUTABLE_H** because tracing/reporting consumes time.

| Frozen H binding | Exact identity |
|---|---|
| Executor source/tree |754f1c883e5a94a7fc9e729af2605424f949ba33 / b4fdef89583f6bab1c9c96cadb1fbe0c1e5d641f |
| H shell blob |1672fbb4fb676ad69885043e46350f53334db0fc |
| H test-module blob |99cf8d1a3f8a85b64e2785710a728964d5bd3f03 |
| H helper blob |58486046a6bb5682a336a1578705ed973e7b4fc6 |

Observer source/tree, current shell/module/helper blobs and generated observer-code
SHA256 are separate from those executor identities. Git clean-source/tree/blob
checks precede launch. The child verifies frozen file bytes, launcher identity/code
hash and the intended compiled stdin entrypoint before observing original frames.
Missing/substituted entry/source/path never yields valid diagnostic evidence.
The startup ZIP is also bounded to128KiB of code and has only sitecustomize.py.

D2 scopes observation to current P's **ordinary** migrate→run→original command calls.
The P envelope executor identifies the host command module; each row identifies
the selected E/P development image's source/tree.
Source/tree come from accepted image proofs and the closed E/P source map; direction
and revision are closed values. Original args/stdin/cwd/env, returned bytes/exception,
30-second command limit, report stage/timing and source/schema order remain unchanged.
Post-commit86 result-loss calls and their evidence are outside this observer scope.
The producer labels P evidence INSTRUMENTED_CURRENT_P. Recognized InvalidRequestError
parameter failures remain client errors with UNKNOWN SQLSTATE. PostgreSQL SQLSTATE
is serialized only when explicitly present in bounded captured output and in the
finite recognized set; no code is inferred from an exception name.

D3 uses these additive reports, under existing artifact directories:
`historical/build-observation.json` and `migration-P-observation.json`.
They explain original invocations, not new product acceptance.

| Closed schema/bound | Definition |
|---|---|
| Envelope v1 | phase/evidence; separate observer/executor bindings; accepted source→tree map; start/end monotonic times; trace-restored flag; status; bounded secondary codes; observed count/records; HMAC |
| Invocation record | fixed operation H_DOCKER_BUILD/P_ALEMBIC; exact source/tree; target or UNKNOWN; closed direction/revision/stage; start/elapsed; outcome; numeric exit or UNKNOWN; finite exception/category; stream byte counts/status; SQLSTATE/step/line or UNKNOWN |
| Stream classification | At most16KiB of each already captured stream, bounded head/tail; UNKNOWN/EMPTY/PRESENT/TRUNCATED explicit. No additional capture mode |
| Persisted report | At most64KiB, at most16 records; current P has11 ordinary migrate callsites. Limit/observer errors make evidence incomplete |
| Privacy | No raw output/argv/stdin/SQL/payload/URL/env/config/credentials/traceback/Dockerfile command text; unknown messages stay UNKNOWN |
| Files | Temporary directories0700/files0600; same UID, resolved path, dev/inode/mode/single-link and descriptor/read stability checks; exclusive NOFOLLOW creates/opens |
| Integrity/completion | Fresh private HMAC key per session, absent from exported report. Closed schema/source/clock/content validation and export hash; missing/tampered/incomplete/export-failed records cannot pass |
| H final-write acknowledgement | Separate private FD carries one64-byte final-report hash after successful observer completion. Parent reads at most65 bytes without blocking; missing/partial/mismatched ACK refuses completeness. Original stdout/stderr capture and shell exit are unchanged |
| Trace lifecycle | Original frame/code observation only; previous tracer conflict is incomplete evidence. Prior tracing state is restored, including exception/cancellation paths |

The independent H ACK prevents a visible COMPLETE file whose last fsync failed
from being accepted. In-process P additionally retains observer failure state.
Export identity is anchored to the opened descriptor before copying and checked
again afterward. Replaced copies are rejected; failure cleanup never removes a
foreign replacement. Failed exports remove their own partial target when identity
still matches. Diagnostics never claim COMPLETE solely from a parseable report or exit0.

Executor failure remains primary. Setup/import failure runs the original H shell
once without observation and records invalid diagnostics. Classifier/write/export/
private cleanup problems are separate finite secondary outcomes. Existing H reports,
source pairing, exit/traceback, source checks and owned-volume cleanup are preserved.
For successful H, the distinct H_DIAGNOSTIC_VALIDATION_FAILED gate runs after
historical owned-volume checks; successful P with invalid diagnostics gets
P_DIAGNOSTIC_VALIDATION_FAILED. P's existing finally publishes invalid diagnostic
status while preserving the original exception object when execution already failed.
The outer P success gate additionally requires the exported report hash.

Observation is charged to existing clocks: H stays before original S and inside
its existing warm-build/job limits; P uses its existing preparation/runtime limits.
No S reset/move/subtraction, new budget, timeout/cache/pin change, assertion weakening
or cleanup shortcut. Retained version1 S+600, P version2 S+720, remaining+480 /
nominal S+1200 supervision, cleanup90 and state25/browser25/foundation45 stay fixed.

**Local verification, no runtime gate claim.** Reused cached locked
`/workspace/scratch/65ac7d472387/c6-material-compat/.venv/bin/python`, with
`PYTHONPATH=backend/src:tests` selecting this checkout. No sync/install/services.

```sh
PYTHONPATH=backend/src:tests /workspace/scratch/65ac7d472387/c6-material-compat/.venv/bin/python -m pytest -q tests/test_telegram_egress_migration.py -k 'test_invocation_' --tb=short
PYTHONPATH=backend/src:tests /workspace/scratch/65ac7d472387/c6-material-compat/.venv/bin/python -m pytest -q tests/test_telegram_egress_migration.py -k 'invocation or material_budget or material_handoff or material_phase or material_entrypoint or material_shell or schema_entrypoint or control_cleanup or control_secondary or retained or ack_loss or material_recovery' --tb=short
/workspace/scratch/65ac7d472387/c6-material-compat/.venv/bin/python -m ruff check tests/test_telegram_egress_migration.py
/workspace/scratch/65ac7d472387/c6-material-compat/.venv/bin/python -m ruff format --check tests/test_telegram_egress_migration.py
sh -n scripts/test_telegram_egress_migration.sh
git diff --check f0c111ac0b74695cc12444ccdf077314d06d2a9b
```

Results: **60 new invocation cases PASS in7.65s; focused combined196 PASS /
390 deselected in13.02s** (the60 are included, not additional unique cases).
Ruff/format, shell/embedded-Python/generated-launcher compilation and diff checks
PASS. Units use real isolated Python subprocesses and the original frozen helper/
build objects with synthetic local executable/test doubles; no daemon/PG operation.
They cover both actual targets, return bytes/nonzero/partial timeout/cancellation,
client vs server/UNKNOWN classification, bounds/canaries, source/entry/owner/path/
launcher substitution, tampering/incompleteness/write/export/final-fsync/ACK failures,
state-only boundary, failure precedence, restored tracing and charged observer costs.
The existing P shell-gate unit adds only valid diagnostic fixture data and two
new status/hash negatives; all prior budget/cleanup assertions remain.

Offline source audit verifies original11 attachment/repo/manifest/frozen-main bytes,
the complete§15.12 prefix and the exact five-path scope. **134 existing top-level
function/class definitions stay byte-exact**; only current P and its existing shell
gate unit are adjusted, with additive diagnostics/tests. Removing only the approved
diagnostic statements from current P and the outer embedded program yields ASTs
identical to accepted base, including ACK86, cleanup, requests/order and original S.
All product/PG/C3 regression nodes, migration0012 and applied0001–0011/ORIGINAL17/
OLD_CHECK4, source inventories10 columns/6 old tables/4 new/42 total/132 signatures,
private Inbox winning pair/five NULL delivery fields, frozen H/T/C/G/E, workflows/
Compose/images/pins/dependencies/locks are unchanged to the accepted C3 base.

Historical CI38850821014/attempt1 tested merge51fca8…/tree fb06ad7…, **not f0c111a
or this descendant**:4 SUCCESS/5 FAILURE, clean4 SUCCESS/5 SKIPPED. H root cause
remains UNKNOWN. Docker29 preparation499.951432356s is partial; P/full state and3 late
C negatives were not completed. Accepted C3 null-bind correction is independent
source/client evidence, not recovered historical CI stderr or a common root cause.

All six findings stay OPEN: C2-MAT-01/03, C1-MAT-01/02, C5-MATERIAL-01, C2-MAT-02.
C6 source is REVIEW on return, then HOLD; C3/C1/C2/C5/C8 HOLD. No actual PG, Docker
build/state, browser, Actions dispatch/rerun/cancel or live/VM/working DB/S3/sends/
deploy execution. No PR-head update/new PR/merge. C0 reviews the combined descendant,
advances the same Draft PR34 once and observes normal automatic CI; concrete new
failures return to C0 without guessed fixes or another budget increase. Still require
all9+clean9 on exact tested SHA/tree, both complete state lanes/full retained negatives/
P/late C cleanup, actual0012 lifecycle/raw42/catalog/security/recovery/replay/current
T→T2 and paired PHOTO/browser, C1/C2/C5 disposition and later C8. PR34 Draft/BLOCKED;
MATERIAL/M3 IN_PROGRESS, not INTEGRATED/VERIFIED, gate OFF. Native/A08/renewal/
collector/M4 unissued; broad CI optimization/IMPL-05 DEFERRED.

### 15.14. C6-M3.1-MATERIAL-CI-DIAG-R3 — stdlib H host boundary / 2026-10-16 UTC

[C0 assignment](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6209721060),
[C0-DIAG-01/P1 reproduction/disposition](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6209702274),
[historical R2 return](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6209600353).
Separate branch `c6/m3-1-material-ci-diag-r3`; exact correction base/sole parent
`a9f58a1364b98b5331b83fa17893363abb7d5dae`, tree
`4c938731b25a4b0424f8e86d33bcf779f6f1fe8b` (its sole parent7119341…).
R2 is a correction base, not accepted for advancing PR34. Accepted C3 ancestor
f0c111a… and main/frozen E933ddd…/0011 remain fixed; PR34 stays OPEN/Draft on
`c6/m3-1-material-compat`/d810dde939f727085af15f7614eeddd36f4909b8.
One focused source descendant; final head/tree/numstat in the canonical receipt.
The complete old contract through§15.13 is preserved byte-for-byte: **563611 bytes**,
SHA256 `2aee65737913ebfede51103ae02e8758405ce3f934d7a7abf040cda4fd9b109a`.

The real outer state loader previously reached test-only `import pytest`. With
site packages disabled it fell back to unobserved H/DIAGNOSTIC_MODULE_LOAD_FAILED;
successful H could not pass the distinct diagnostic gate. The explicit
`__h_observer_definitions__` entrypoint now dispatches before pytest imports and
runs the unchanged observer while runpy's module remains available to ordinary
`inspect.getsource`. Only stdlib is required. A shared request/result container
transfers the original CompletedProcess/summary or the exact original exception
object. The outer boundary re-raises that exception outside its load-failure catch.
The started marker prevents a second H invocation after dispatch. Missing module
still invokes original H once with finite INVALID diagnostics; observer setup
failure retains its existing DIAGNOSTIC_SETUP_FAILED behavior. Image/intent stay
direct. SystemExit(0) completes host dispatch; it does not replace H's exit code.
Ordinary pytest collection and all existing cleanup/success gates remain intact.

**Observed regression, not a proposed expectation.** The new fixture/test nodes
were copied to an external test file and run from a separate, unchanged detached
a9 checkout. All274 tracked files were independently blob-checked against its
index. The child runs `python -S`, executes the actual outer state branch with
real runpy/full checked-in source and records any pytest import attempt. No loader
or definitions namespace is stubbed. Only external H execution is a stdlib double;
its synthetic empty completion uses the actual observer and independent ACK.
Test-only AST extraction selects the outer branch; runtime source is not rewritten.

```sh
# cwd: /workspace/scratch/65ac7d472387/c6-material-ci-diag-r3-baseline
PYTHONPATH=backend/src:tests /workspace/scratch/65ac7d472387/c6-material-compat/.venv/bin/python -m pytest -q /workspace/scratch/65ac7d472387/c6-material-ci-diag-r3-evidence/test_stdlib_host_regression.py --tb=short
# cwd: /workspace/scratch/65ac7d472387/c6-material-ci-diag-r3
PYTHONPATH=backend/src:tests /workspace/scratch/65ac7d472387/c6-material-compat/.venv/bin/python -m pytest -q tests/test_telegram_egress_migration.py -k 'invocation or material_shell or schema_entrypoint' --tb=short
```

Base: **6 FAIL/9 PASS in6.10s**, pytest attempted in normal/setup state cases;
normal H success/nonzero yielded INVALID/DIAGNOSTIC_MODULE_LOAD_FAILED, exactly
one invocation. Correction: **91 PASS/510 deselected in14.80s**, including all15
new cases and the existing60 invocation cases. New cases cover H success/nonzero/
original OSError identity, exactly-one invocation, COMPLETE result/report/hash
transfer, finite invalid setup/load, unchanged image/intent, no pytest import and
restored host environment/sys.path/tracing. No broader suite repeated.

Ruff check/format, shell syntax, module/embedded/generated-observer compilation,
diff and source audit PASS. **168 existing definitions are byte-exact**; only the
related outer-seam test's loader double changes, with its assertions preserved.
The module outside this dispatch/two new nodes/related seam and the outer program
outside this H boundary are AST-exact. Generated observer SHA256 remains
`6e254dda632211b318ed299345c73d1b5e95e2bebb32af330247402f64055458`.
Exactly five allowed paths changed. Original11, all product/PG/C3 regressions,
0001–0011/ORIGINAL17/OLD_CHECK4/0012←0011, inventories/Inbox winning pair/five NULL
Job fields, frozen H/T/C/G/E, P semantics, source/owner/path/HMAC/final-ACK/privacy
protocol,16KiB/64KiB/16 records, workflows/locks and all budgets are unchanged.

Historical R2's60/196 PASS remain evidence for a9 only; C0-DIAG-01 demonstrates
their missing stdlib-loader coverage. This correction is source/unit evidence,
not actual H/build/state/PG/PHOTO/browser acceptance or recovered historical stderr.
Historical38850821014 remains4 SUCCESS/5 FAILURE, clean4 SUCCESS/5 SKIPPED; H cause
UNKNOWN and Docker29 prep499.951432356s partial. **Seven findings OPEN:**
C2-MAT-01/02/03, C1-MAT-01/02, C5-MATERIAL-01, C0-DIAG-01.
C6 REVIEW on source return, then HOLD; C3/C1/C2/C5/C8 HOLD. No installs/services,
Docker/PG/browser/Actions execution, PR-head update/new PR/merge or live operation.
C0 reviews before any PR advancement; actual9+clean9, both full state/P lanes,
retained/late-C negatives,0012/PG/current-T→T2/paired PHOTO/browser and subsequent
C1/C2/C5/later C8 acceptance remain required. S/retained600/P720/remaining+480/
nominal S+1200/cleanup90/individual bounds/state25/browser25/foundation45 unchanged.
PR34 Draft/BLOCKED; MATERIAL/M3 IN_PROGRESS, not INTEGRATED/VERIFIED; gate OFF.
Native/A08/renewal/collector/live/VM/working DB/S3/sends/deploy/M4 unissued;
IMPL-05/broad CI optimization DEFERRED.

### 15.15. C6-M3.1-MATERIAL-CI-DIAG-R4 — diagnostic unit image inputs / 2026-10-16 UTC

[C0 task](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6210115890),
[C0-DIAG-02/P1 reproduction and R3 intake](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6210103047).
Branch `c6/m3-1-material-ci-diag-r4`; exact base/future sole parent
`9cb1467c1705827a4e782421754850f5dee762ce`, tree
`e0c1e5231cddfd25e44071990031371aaa16c482`, base parent a9f58a1….
R3's stdlib host correction is source/unit accepted and preserved. Main/frozen
E933ddd…/0011 and OPEN/Draft PR34 c6/m3-1-material-compat/d810dde… unchanged.
One focused source descendant; exact final head/tree/numstat in canonical receipt.
Entire contract through§15.14 preserved: **569463 bytes**, SHA256
`bd6f9cb9cc6ef73edacfd9634fd415f9275d2e569ecee8cd4a6d8d311e51b582`.

The ordinary units previously used git show and clone/commit/worktree even though
the existing development image copies no .git/history. Only post-pytest diagnostic
fixtures/tests change. The new `tests/fixtures/telegram_egress_h_source.json` is
83297 bytes of versioned stdlib-readable zlib/base64 input data. Four exact frozen
H files are verified against their actual Git objects during preparation; runtime
tests read only this committed data, validate fixed paths/source/tree/decoded sizes/
Git blobs, bound decompression and reject trailing/incomplete compressed data.

| Frozen H754f1c… / tree b4fdef8… input | Decoded bytes | Git blob |
|---|---:|---|
| scripts/test_telegram_egress_migration.sh |6248|1672fbb4fb676ad69885043e46350f53334db0fc|
| tests/test_telegram_egress_migration.py |84396|99cf8d1a3f8a85b64e2785710a728964d5bd3f03|
| scripts/prepare_telegram_egress.py |139789|58486046a6bb5682a336a1578705ed973e7b4fc6|
| infra/images.lock.env |720|1f14e1686acd3ffdde9986ec58352d0e03735af8|

Total **231153 decoded bytes**; no reconstruction or current-source replacement.
COPY tests already includes the fixture. invocation_units retains its original H
helper/frame/launcher assertions. stdlib_host_checkout copies actual current files
and those H bytes. Its real-loader child doubles only external H/Git-command IO;
finite Git replies identify explicitly SYNTHETIC_UNIT source/tree values derived
from actual copied blobs. Unexpected commands fail and are asserted absent.
Real schema_source_binding/diagnostic_binding, runpy, observer/launcher/classifier
and the whole loaded definitions namespace are not replaced. The child still uses
python -S, records/refuses pytest imports and checks all15 original cases. Synthetic
Git IO applies only to these units; both actual state lanes still require real Git
source/tree/blob/clean validation. No runtime protocol/acceptance rule changes.

**Observed packaging regression.** Separate unchanged9cb checkout and its complete
source-only export were blob-checked (274 files); export has no .git. With Git
available the two exact C0 nodes gave **2 setup ERROR in1.35s**, exit1: git show
and git clone each exit128. Commands, from that export:

```sh
PYTHONPATH=backend/src:tests /workspace/scratch/65ac7d472387/c6-material-compat/.venv/bin/python -m pytest -q 'tests/test_telegram_egress_migration.py::test_invocation_h_launcher_original_frozen_functions_and_stream_bounds[exit-runtime]' 'tests/test_telegram_egress_migration.py::test_invocation_outer_stdlib_host_real_loader[state-none-success]' --tb=short
```

Correction ran in a fresh **168-file development COPY layout**: pyproject.toml,
uv.lock, backend/, migrations/, alembic.ini, tests/, scripts/, contracts/ and only
infra/postgres/ensure_m1_3_prerequisites.sh. Per-file byte/SHA256 manifest matches
those inputs; no .git, uncopied docs/infra/image pins, parent checkout or history.
Empty inherited environment; PATH contains only sh/python3 symlinks, Git lookup
returns None, and the parent audit hook rejects any Git subprocess. PYTHONPATH is
backend/src:tests; dependencies are the unchanged cached locked venv. Exact run,
cwd c6-material-ci-diag-r4-evidence/copied-layout under the shared scratch root:

```sh
/usr/bin/env -i PATH=/workspace/scratch/65ac7d472387/c6-material-ci-diag-r4-evidence/restricted-bin PYTHONPATH=backend/src:tests PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 LANG=C.UTF-8 /workspace/scratch/65ac7d472387/c6-material-compat/.venv/bin/python /workspace/scratch/65ac7d472387/c6-material-ci-diag-r4-evidence/guarded_pytest.py -q tests/test_telegram_egress_migration.py -k 'invocation or material_shell or schema_entrypoint' --tb=short --junitxml=/workspace/scratch/65ac7d472387/c6-material-ci-diag-r4-evidence/copied-layout-results.xml
```

**91 PASS/510 deselected in10.00s**, JUnit91 tests/0 failure/0 error/0 skipped;
no xfail/skip/filter changes. Includes all60 earlier invocation and15 stdlib-host
cases: success/nonzero/original exception identity, one H invocation, setup/load
INVALID, COMPLETE result/hash/ACK transfer, direct image/intent, privacy/bounds and
restored environment/path/tracing. Actual Git subprocess attempts:0. Executables
named docker are the existing synthetic fixture executables, not Docker/daemon.
Supplemental loader control uses exact a9 shell/module bytes with the revised
external unit nodes, still without Git: **6 FAIL/9 PASS in2.62s**, all six on the
pytest import attempt. R3's missing-pytest regression remains effective.

Ruff/format, compilation, diff/source/fixture/COPY audits PASS. All **306538 bytes**
before test-only pytest import remain exact, SHA256
`3b1b9e4d617d89da8268ba66d37e3097d188c1ca7504f8c161d170137062d6c9`.
Entire shell blob7d1e08e…/SHA256145a8300… unchanged.168 other existing definitions,
all original host assertions/cases, Original11, C3/product/PG, migrations/ORIGINAL17/
OLD_CHECK4/0012←0011, Inbox/Job/inventory invariants, frozen H/T/C/G/E, generated
observer6e254dda…, limits/HMAC/ACK/privacy/export/current P and all budgets remain
unchanged. Exactly five allowed paths; no Dockerfile/workflow/dependency expansion.

Packaging/unit evidence only; no install/service/Docker/build/PG/browser/Actions/
live operation or new historical H cause. Historical38850821014 stays4 SUCCESS/
5 FAILURE, clean4 SUCCESS/5 SKIPPED; H cause UNKNOWN, Docker29 prep499.951432356s
partial. **Eight findings OPEN:** C2-MAT-01/02/03, C1-MAT-01/02, C5-MATERIAL-01,
C0-DIAG-01/02. DIAG-01 source-fixed; actual state acceptance remains pending.
C6 REVIEW then HOLD; C3/C1/C2/C5/C8 HOLD. C0 packaging intake before any update of
the same Draft PR34; actual9+clean9/both full state-P/retained-late-C/0012-PG/
current-T→T2/paired PHOTO-browser, C1/C2/C5 and later C8 still required. No PR-head
update/new PR/merge/dispatch/rerun/cancel. S/600/P720/+480/S+1200/cleanup90 and
individual/state25/browser25/foundation45 unchanged. MATERIAL/M3 IN_PROGRESS,
not INTEGRATED/VERIFIED; PR34 Draft/BLOCKED; gate OFF. Unissued native/A08/renewal/
collector/live/VM/working DB/S3/sends/deploy/M4 and deferred IMPL-05 unchanged.

### 15.16. C6-M3.1-MATERIAL-HARNESS-R5 — packaged inputs and saved V1 reader / 2026-10-16 UTC

[C0 task](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6211450459),
[C0 disposition](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6211420811).
Separate branch `c6/m3-1-material-harness-r5`, exact base/sole parent
`d7cea5a2e9da7b384aeaf11dd41df3e1e4abcbff`, base tree
`a471c98e16343cf9d17d4d184df88ed491184544`. One focused descendant; final head/tree/
numstat in canonical PR34 receipt. PR34 remains OPEN/Draft on that base, main/frozen
E `933ddd284ff5b77fb1aa88a4270ab0032bc499c9`/0011 unchanged. Entire contract through
§15.15 preserved: **576446 bytes**, SHA256
`76ed7dd2fe91834ad7884d07c0f95e76889875232981fcc29ab58d48e3b8a75e`.

**Observed baseline.** CI38868575912/attempt1 tested merge
`58542ff01cfbcd95f5247a901168e7525f5ef9f0` with matching tree:6 SUCCESS/3 FAILURE,
clean6 SUCCESS/3 SKIPPED. Foundation116867029172 failed all11 preparation units
at uncopied `/app/infra/images.lock.env` before preparation logic;1395 passed/799
deselected. Both state reports fail at material_controller_fresh: ValidationError,
material_schema_controller:1995→parse_snapshot:84, SQLSTATE NULL. C6 re-read these
three job logs and both state reports, verified ZIP hashes/tested merge/all275
source-P archive blobs. Actual missing field locations/payload were not exported.
Separate clean d7 baseline and exact168-file COPY layout reproduced `[pass]`:
**1 expected FAIL in0.95s**, same missing input,0 subprocess attempts. Executing the
unchanged controller reader block on synthetic source-shaped ordinary/guarded raw
inputs reproduces missing code/job_id; ordinary reader also rejects six guarded
fields. Each matching reader accepts only the nonpersistent response envelope.

**Narrow correction.** material_budget_fixture explicitly depends on the unchanged
frozen_h_source fixture, reading its verified720-byte image pins before e.ROOT is
substituted. The preparation unit writes those bytes into its disposable input.
All11 cases/real entrypoint/assertions remain unchanged; no current infra/Git lookup.
Pins equal current and frozen H blob1f14e1686acd3ffdde9986ec58352d0e03735af8.

The fresh controller now calls material_saved_v1_snapshots. Its sole SELECT reads
id/kind/step/turn_input for **every non-NULL input**, with no consumer/step filtering.
Nonempty inventory and unique actual UUID Job identities are required. Closed
PROCESS_TURN/TEST_CONSUME selects parse_snapshot; PROCESS_TURN/GUARDED_TEXT with
CONTROLLED_GUARDS_V1 selects parse_guarded_snapshot. Only code=SNAPSHOT/actual Job id
are added in memory. Stored JSON, all fields and snapshot_digest are preserved and
checked; no schema_version or persisted code/job_id is accepted. Unknown/wrong
kind/step/consumer, extra fields or malformed inputs fail. No digest recomputation,
row update, permissive fallback or stale worker execution. Escalation keeps its own
immutable snapshot; ESCALATE_OWNER is not a third turn_input form. Other controller,
catalog/fingerprint/recovery/refusal/ownership/pairing assertions remain byte-exact.

**Executed source/unit verification**, cached locked Python3.13.16 dependencies:

| Exact selection in the development COPY layout | Result |
|---|---|
| All seven material_budget_fixture consumers, explicitly including the entire11-case preparation function |78 PASS|
| Three new test functions calling the actual controller helper: mixed ordinary/guarded inventory, Job binding/raw decoder refusal,28 invalid-last-row cases, empty/duplicate identity |32 PASS|
| Combined preceding two selections; all subprocess/network attempts denied by parent audit |**110 PASS in2.87s**,0 subprocess/network attempts|
| Existing invocation/host-loader/material-shell/schema-entrypoint selector |**91 PASS/510 deselected in10.05s**|

Both runs use the same exact168 copied files, no.git/history/current infra pins,
env-i, PATH containing only sh/python3 and Git lookup None. Per-file SHA256 manifest
`9082ccc0f52debb7cd5cd94d95c37f0842d91429798c248e0a19afbe3daa2c51` is in the receipt.
JUnit:0 failure/error/skip; no xfails or marker/collection exclusions.15 material-shell
cases overlap:201 executions,**186 distinct cases**, not201 independent cases.
The91 run retains real python-S/runpy and finite external H/Git units,37 synthetic
docker/38 Python/2 sh parent launches;0 real Git or network attempts. Audit restrictions
apply to the parent; this is not an OS sandbox or real image/DB execution. Full
commands/environment, baseline probe and manifest are in the canonical receipt.

Ruff/format/compilation/diff/scope/source audits PASS. Pre-pytest runtime prefix
306538 bytes/SHA2563b1b9e4d617d89da8268ba66d37e3097d188c1ca7504f8c161d170137062d6c9,
whole shell blob7d1e08edcfc11d12c5e7067586ec0cd795e664c5, frozen-H JSON/decoder,
original11, product/strict parsers/C3/applied migrations/0012←0011/ORIGINAL17/OLD_CHECK4,
Inbox winning pair/five NULL Job fields/current-T→T2/PHOTO, frozen H/T/C/G/E,
observer/ACK/privacy/bounds/workflows/pins/dependencies remain unchanged.

C0 closed **C5-MATERIAL-01 and C0-DIAG-01** on scoped actual d7/merge58542ff evidence.
**Seven distinct findings OPEN:** C2-MAT-01/02/03, C1-MAT-01/02, C0-DIAG-02
(C1-R2-01 is its packaging counterexample), C1-R2-02. Units close none. Latest actual
P preparation623.690022374s/688.934643093s is scoped PASS720, not PASS600/full-state.
Original S/retained600/P720/remaining+480/nominal S+1200/cleanup90/individual bounds/
state25/browser25/foundation45 unchanged; no retry/reset/subtraction/budget increase.
Full product PG and both complete P/state lifecycles, used55000/used recovery/cutover/
restart, retained positives/full120-timeout/export/all3 late-C negatives and9+clean9
remain mandatory. C0 intake before C0 alone advances the same Draft PR for normal
automatic CI; C1/C2 acceptance, applicable C5 bridge, later independent C8 follow.
No new Docker/PG/browser/Actions/services/install/live/PR-head/new PR/merge operation.
C6 HOLD after return; C3/C1/C2/C5/C8 HOLD. MATERIAL/M3 IN_PROGRESS, not INTEGRATED/
VERIFIED; gate OFF. Native/A08/renewal/collector/M4 unissued; IMPL-05/broad optimization
DEFERRED; VM/working DB/S3/sends/deploy remain unissued.

### 15.17. C2-M3.1-MATERIAL-CURRENT-PROFILE-R4 — test boundaries and same-call SENT diagnostics / 2026-10-16 UTC

[C0 assignment](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6218233521),
[C0 R3 disposition](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6218176738),
[C2 R3 return](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6217695756),
[C1 R3 return](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6217641903).
This is the separately issued source task, not a reopening of the completed reviews.
Branch `c2/m3-1-material-current-profile-r4`; exact base/sole parent
`89f9e157ddfc328ba4564fc003b047f517352cdf`, base tree
`9be95d45e6a70bf76adf146c1035e571d52205af`. One focused descendant;
final head/tree/numstat and commands belong in the canonical PR34 receipt.
Main/base/frozen E `933ddd284ff5b77fb1aa88a4270ab0032bc499c9`/0011 and
PR34 OPEN/Draft `c6/m3-1-material-compat` at89f9e15 remain unchanged.
The entire preceding582717-byte contract through§15.16 is byte-exact,
SHA256 `6f68bd4443ec384b0cceee98cc9af8276d15846962ca162207ac9fc06db76cfe`.

**Actual baseline, not execution of this source.** CI38909147338/attempt1 tested
merge `d0fd7e5da7c29b1e065e72a7bfcc11519bdd39d6`:5 SUCCESS/4 FAILURE,
clean5 SUCCESS/4 SKIPPED. Foundation117000270183:1438 packaged units PASS;
PG785 PASS/14 FAIL. Browser43 PASS/1 FAIL. Both state117000270974/117000270455
stop at material_controller_fresh/MessageResponse:2037 after the saved-V1 reader.
The two foundation DTO failures export occurred_at/created_at pattern errors;
the state reports export only ValidationError/frame/sqlstate=NULL. The analogous
field cause in state remains a source-supported inference. Saved reader progress
does not accept fresh/catalog or later P lifecycle. Empty archived worktree-status
does not replace four skipped workflow clean-source gates.

C0 CLOSED C0-DIAG-02 (packaging alias C1-R2-01), C1-MAT-02 and C2-MAT-03 on this
actual run; C5-MATERIAL-01/C0-DIAG-01 retain scoped closure. Historical statements
in earlier sections that call the R3 helper's coverage “all42” are corrected here:
it covered41 data tables, intentionally omitting platform.alembic_version.
All10 intended negative/same-claim-positive R3 cases passed; seven independent
canonical used-refusal cases covered42 but do not supply that R3 assertion.

| Source correction | Preserved boundary / remaining execution |
|---|---|
| Three raw SQL→MessageResponse sites | Existing wire_dates precedes the unchanged strict DTO in provenance PG, fresh controller and current0012 compatibility case. No key dropping, permissive timestamp/parser, storage changes or R5 saved-V1 reader edits; full page/current/history/tenant/provider/wrong-Client/later catalog gates remain |
| Six held TELEGRAM race arms | Existing v2_fixture wraps only the two direct current-profile producers. Each telegram_ingest remains on its original held connection/transaction; commit/rollback/barrier/Resume and earliest-origin assertions remain. Second arrival keeps its identity/text/date relationships. Shared V1 projection and CONTROLLED neighbors unchanged |
| Lifecycle refresh companion | Same callback point uses normal ingest_update with the original raw lifecycle update;503 UNAVAILABLE/no-new-intention/UNVERIFIED assertions unchanged |
| Current projection/capabilities | Closed exact message key set gains current. Catalog expects23 exact signatures:2 runtime replay wrappers/21 private,7 invoker/16 SECURITY DEFINER; owner/search_path/PUBLIC/runtime and predecessor/negative privilege assertions remain. No wildcard, grant or product SQL change |
| Populated0011 seed | Every enumerated Turn follows actual COLLECTING→GROUP, WAITING_MEDIA→due MEDIA, READY→TEST_CONSUME; current-revision claim helper and final READY assertion remain strict. File WINNER may already seal/bump a Turn. No forced Job/status/revision, skipped Turn, manufactured snapshot or removed WINNER; frozen V1 receipt/digest, pending/ignored/lifecycle/UNKNOWN and repeat exact reverse/hash loop retained |
| UTC caller | expires_at.astimezone(UTC) supplies the identical instant to unchanged serial_clock; production deadlines and all EXPIRED assertions unchanged |
| R3 rollback42 | Existing41 data fingerprints plus actual ordered version_num rows before/after the rejected transaction; assert41 data entries/one metadata row. Shared legacy fingerprint semantics untouched. Exact SQLSTATE/constraint/reason/context, zero partial atom and same original/same claim positive after only trigger removal remain |
| SENT | Diagnostic-only instrumentation of the existing single finish_send inside original3s timeout and held channel_connection FOR UPDATE. No second SQL/finalizer/probe, release/retry, mapper patch or product/DDL correction. Stable-target lock order/implicit FK closure and atomic SENT+deferred apply remain requirements |

**Diagnostic contract.** Test-only formatter and scope live in the existing pure
`tests/test_m3_1_provenance.py`; the named PG case imports the scope. This keeps
the six new pure tests independent of PG harness imports. The report is one
ASCII JSON line, including LF≤4096 bytes: static stage/action, closed outcome,
at most4 distinct exception nodes through orig/cause/context, closed exception
class and schema/table/constraint identifiers, five-character uppercase SQLSTATE,
and at most3 allowlisted platform function/numeric-line pairs per node.
Absent/untrusted/oversized values are UNKNOWN; traversal is cycle-safe and
chain_limited records a truncated chain. Context input is bounded to16KiB and
only parsed into the closed function/line fields. No raw context, SQL, parameters,
message/detail, arbitrary str/repr, payload/text/IDs/claims/tokens/connection strings
are emitted. Formatter failure yields static UNKNOWN metadata; sink failure does
not replace the primary. The original exception identity/traceback survives both
failing and suppressing lock cleanup. Success/setup failures do not emit a fabricated
finalizer diagnostic. Existing actual primary SQLSTATE/constraint/lock edge remains
**UNKNOWN**; synthetic unit SQLSTATE values are not SENT execution evidence.

**Local source/pure evidence.** Available Python3.12.14/Pydantic2.13.5, cached
Ruff0.16.7; required Python3.13 interpreter is absent (retained venv links are broken).
Ruff check/format for all9 changed Python modules, compile/diff and exact AST/source
scope audits PASS. Existing235 function bodies/decorators in those modules stay
byte-exact; existing pure codec/migration/model tests and R5 reader untouched.
Six new tests execute with cached pytest packages:6 PASS/64 deselected in0.86s,
no skips/xfails, on3.12 rather than the packaged3.13 image. The first local attempt
imported the PG harness and failed6 times on unavailable psycopg/libpq before the
formatter; placing the helper in the permitted pure module removed that dependency.
No install or environment bootstrapping followed. Exact-source pure probes also
reproduce the two raw timestamp failures and validate strict wire_dates output/
unchanged input, V2 normalizer+fingerprint equality and second-arrival relationships,
and same-instant UTC normalization. These are not full1438-unit/PG/state acceptance.
All14 prior PG failures and both state sites were reviewed:13 have the bounded test
corrections above; SENT receives diagnostics only. No broader suite or service run.

The closed12-path scope contains only the nine named test modules and these three
task documents. Backend/product/models/decoders/Worker/error mapper, every migration
including0012 and applied0001–0011, ORIGINAL17/OLD_CHECK4, original11, V1/hash/codec,
private Inbox winning pair/five NULL Job delivery fields, terminal/token/T→T2,
scripts/runtime/shell/frozen-H fixture, infra/workflows/Compose/Dockerfiles/pins/locks/
dependencies and frontend remain byte-exact.

**Eleven distinct OPEN findings per C0; this source closes none:**
C1-MAT-01/P1 (C1-R3-02 alias), C1-R2-02/P2 (C1-R3-01 alias),
C2-MAT-01/P1, C2-MAT-02/P2, C1-R3-03/P2, C0-R3-01/P2,
C0-R3-02/P2, C0-R3-03/P2, C0-R3-04/P2, C0-R3-05/P2 and C5-R3-01/P2.
C5 separately ACTIVE only on frontend/e2e/messaging.spec.ts from89; no C5 source
absorbed here. C1/C3/C6/C8 HOLD. C2 source REVIEW on return, then HOLD.
C0 combines accepted independent returns before one normal automatic CI advance.
Required actual gates:9+clean9, full product PG/strict fresh DTO+tenant/wrong-Client,
SENT lock/atomicity, EXPIRED precedence, both ingress race suites, exact catalog/
ACL/populated reverse/R3 raw42, both complete state-P/used/recovery/cutover/restart,
retained positives/full120-timeout/export/all3 late-C negatives and owned cleanup,
remaining C1/C2/applicable C5 acceptance then independent C8.

MATERIAL/M3 IN_PROGRESS; PR34 Draft/BLOCKED; not INTEGRATED/VERIFIED; gate OFF.
Original S/retained600/P720/remaining+480/nominal S+1200/cleanup90/state25/browser25/
foundation45 and individual limits unchanged. No clock reset/charges subtraction/
retry/budget increase, new PR/PR-head advance/merge/dispatch/rerun/cancel, installs/
new services/Docker/PG/browser runtime or live operation. VM/working DB/S3/sends/
deploy/native/A08/P-A03-09/renewal/collector/M4 unissued; IMPL-05/broad optimization
DEFERRED.

### 15.18. C2-M3.1-MATERIAL-SENT-LOCK-R5 — single target/context updates and typed tenancy identity / 2026-10-16 UTC

[C0 task](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6220709356),
[C0 R4 actual disposition](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6220674632),
[C2 R4 return](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6220498853).
Separate branch `c2/m3-1-material-sent-lock-r5`; exact base/sole parent
`36240388fa580e563699c4dec3fd989cc2dd09f6`, tree
`cb5c38e78a145184d8792f53702e102275fbb785`; ordered base parents
`cb0e49af1a7ff263593373b41b116ef7d26c11c6`,
`ef86965c4b4d747be5823034f81b1e187781f7b8`.
One focused descendant; full head/tree/numstat/commands in the canonical receipt.
Main/frozen E `933ddd284ff5b77fb1aa88a4270ab0032bc499c9`/0011 and
PR34 OPEN/Draft `c6/m3-1-material-compat` at36240388 remain unchanged.
The entire preceding592048-byte contract through§15.17 stays byte-exact,
SHA256 `ad5697568bcd71639c06fbf827c97481c9e1149879a538518599866a72fb3604`.

**Observed baseline; no new PostgreSQL execution.** CI38926368179/attempt1 tested
merge `d3c39fa8977d86aa25f6ab9cc713a0c7f55d2f22`:8 SUCCESS/1 FAILURE,
clean8 SUCCESS/1 SKIPPED. Foundation117058825254:1444 units PASS;
797 PG PASS/2 FAIL. The original one-call SENT diagnostic is760 ASCII bytes/LF,
chain_limited=false: MessagingError→OperationalError→LockNotAvailable/55P03;
frames material_apply:17→material_bind:40→turn_material:21. Schema/table/constraint
remain UNKNOWN. SENT failed at test line1018; UNKNOWN passed; subsequent SENT
readback NOT RUN. No particular FK/resource/lock_timeout/deadlock was observed.
The other failure is exact23 tenancy signature equality: composite type rendering
omitted platform qualifiers, with the dedicated profile tail NOT RUN.

**Source-supported RI cause and full closure.** Read the authoritative PostgreSQL18
source at pinned `92d47d544bf64274b6a7aa8775f7b35bcf71f339`:
[RI update gate1490–1495 and lookup426](https://github.com/postgres/postgres/blob/92d47d544bf64274b6a7aa8775f7b35bcf71f339/src/backend/utils/adt/ri_triggers.c#L1417-L1500),
[heap UPDATE new xmin3874](https://github.com/postgres/postgres/blob/92d47d544bf64274b6a7aa8775f7b35bcf71f339/src/backend/access/heap/heapam.c#L3868-L3878),
[slot raw-xmin check798–800](https://github.com/postgres/postgres/blob/92d47d544bf64274b6a7aa8775f7b35bcf71f339/src/backend/executor/execTuples.c#L785-L801).
The FK update gate checks all/some NULL keys first, then current-transaction old
tuple, then equal keys. The first UPDATE of the committed existing target sees
an old xmin from another transaction: its unchanged non-NULL connection key can
skip RI; new canonical keys still receive their normal checks. That UPDATE makes
a new physical tuple with current xmin. The second current_material UPDATE sees
that version as its old tuple: current-XID requires RI even for unchanged keys.
The RI lookup uses FOR KEY SHARE, conflicting with the separately held connection
FOR UPDATE. Thus the actual frame agrees with a concrete source path through the
target's connection FK; that FK identity remains an inference, not exported fact.

The same analysis also finds a second dependency after that first failure:
turn_material's delivery C+1 followed by material_apply_context's material C+1
updates the same Conversation twice. Its FK `(ws,connection,business)` can likewise
recheck connection on the second current-XID tuple. A target-only correction would
leave this source path. Both physical repetitions are removed for changed SENT.

| Site / old path | Corrected source / preserved result |
|---|---|
| material_bind: canonical refs + original current; apply then updates current again | One target UPDATE stores validated canonical refs and the final folded current together. Provider/connection key and all identity/witness checks are unchanged. Original semantic current is carried privately for comparison/reason; no intermediate current is published |
| material_apply: always writes changed current | Private p_previous=NULL retains ordinary apply unchanged; non-NULL binding path verifies stored current equals the recomputed fold, then uses the same Message/context/Audit/effect body without another target UPDATE. No-op still binds but returns NULL without counters/effect/Audit |
| SENT trigger C+1 before binding, then shared C+1 | Under the same acquired C barrier, bind runs before the delivery UPDATE. A changed OUTBOUND first binding invokes shared context with delivery=true, performing Message+1 and one physical C+2 UPDATE, then the trigger returns. NULL/no-op/unmatched/quarantined bind falls through to the original delivery C+1; UNKNOWN retains its original path |
| Shared material_apply_context | Only its C increment expression gains delivery2/ordinary1, with default false preserving all existing three-argument callers. Conversation/Message/Turn locks, Message+1, material_bump_turns, Escalation/shared invalidation body stay exact; per-fact context arithmetic remains delivery1+material1, invalidation once |
| Tenancy catalog query/profile lookup | Catalog p.oid is compared to the closed23 fully qualified expected signatures resolved through regprocedure→OID, with duplicate OID refusal and exact set/count equality. Profiles look up by the same OID; no pretty-type-name/search_path comparison |

Two necessary **private signature replacements**, not overload additions:
`platform.material_apply(uuid,uuid,uuid)` →
`platform.material_apply(uuid,uuid,uuid,jsonb)`;
`platform.material_apply_context(uuid,uuid,uuid)` →
`platform.material_apply_context(uuid,uuid,uuid,boolean)` (last argument DEFAULT false).
Bind passes original semantic current; material_process passes NULL. Apply passes
delivery=true only for non-NULL previous material and OUTBOUND, i.e. changed first
SENT binding. Known bound outbound mutations pass NULL and retain context+1.
The material_process fallback that detects a missed changed original/SENT binding
still raises and rolls back. The two existing direct context callers retain default
false. PRIVATE_FUNCTIONS and exactly these two tenancy profile entries are updated;
old three-type apply signature is absent. Public wrappers/grants and private execute
denials remain:23 additions/132 functions,2 runtime/21 private,7 invoker/16 SECDEF,
same owner/search_path/PUBLIC/runtime profiles. No new capability or physical schema.

The local shared-context change is a direct implementation dependency of the
same RI gate: omitting it would preserve a reverse connection edge after C.
Its body is byte-exact apart from the documented C increment/comment; no alternate
invalidation path is introduced. Required order remains own Job→own Outbox→C→
existing target→Message/Turn, with no new target/connection or foreign Job/Inbox lock
after C. Changed refs check the own Message, held C and exact own valid-SENT Outbox;
unchanged source FKs skip on the committed target's first UPDATE, nullable FKs retain
MATCH SIMPLE behavior. Audit/effect point only to stable own target/Message/source;
all RI, trigger, RLS and deferred consistency checks remain enabled and unchanged.

One physical transaction still contains SENT, canonical binding/effective current,
Message+1/C+2, shared Turn/context/Escalation, exactly one typed Audit/effect and Job
completion. Any failure rolls back the complete atom. Existing all-or-none NULL,
tenant/Client identity, write-once refs, quarantine/mismatch/UNKNOWN no-bind, sticky
delete/uncertainty, effective grouping/readiness/late File, immutable private Inbox
winning pair/results and five NULL mutation Job delivery fields remain. There is
no deferred second apply/Job/ACK, mapper change, retry, prelock or constraint bypass.

**Targeted regressions; awaiting actual CI.** The original SENT/UNKNOWN decorators,
single finish_send/arguments/3s, separate connection FOR UPDATE and same-call bounded
diagnostic scope are exact. Its first existing saved-result read is retained as
historical for final full equality; no extra pre-finalizer SQL/probe/send. Added
post-success readbacks assert exact Outbox outcome, full target binding/current,
original Message text/current/version, C version, one source-linked typed Audit/effect
and immutable DEFERRED_TARGET result. A neighboring equal-original SENT case keeps
the same held blocker/3s and proves binding with Message1/C4/zero material effects;
it exercises the trigger's NULL-result delivery fallback. Two overflow arms target
Message=max and C=max−1: SQLSTATE22003 must originate in material_apply_context,
with all41 data fingerprints plus actual ordered migration metadata unchanged,
zero partial SENT/binding/current/context/effect/Audit/Job changes and historical
result preserved. They add no positive retry or new provider send. R3 literal42,
terminal/token/known-T/UTC/current/seed and six diagnostic tests remain exact.

**Local evidence only.** Python3.12.14/Pydantic2.13.5 and cached Ruff0.16.7;
required packaged3.13 interpreter is absent. Cached targeted existing online Alembic
empty-parameter test:1 PASS/69 deselected in0.84s, compiling all131 expanded DDL
operations without a DB. Ruff check/format3 changed Python files, compile/diff and
AST/source audits PASS. Read-only AST-lifted existing source parser/inventories
confirm42 tables,131 upgrade statements,132 functions,23 additions/2 runtime/21
private/7 invoker/16 SECDEF and the exact typed tenancy map.127 complete surviving
function profiles and all non-function DDL/column mappings are exact except the
two typed identities in existing owner/REVOKE statements.53 other test definitions
including decorators are byte-exact. These checks do not execute PostgreSQL, the
new PG regressions, dedicated catalog/ACL tail or full product/state acceptance.

Six changed paths inside the closed eight-path list:0012, named provenance PG and
tenancy tests, and three task documents. The pure provenance and migration tests
remain byte-exact. Applied0001–0011, ORIGINAL17/OLD_CHECK4, original11 and all other
tracked blobs/modes are preserved: product/models/DTO/Worker/mapper, scripts/runtime/
shell/frozen-H, workflows/Compose/pins/locks/dependencies and frontend. Revision
0012←0011 and physical schema mapping are unchanged; no0013/new file/runner.

**C0 actual statuses, not closures by this source.** Eight R4 closures remain:
C1-R2-02 (C1-R3-01 alias), C2-MAT-02, C1-R3-03, C0-R3-01/02/04/05,
C5-R3-01. Three remain OPEN: **C1-MAT-01/P1** (C1-R3-02 alias),
**C0-R3-03/P2**, **C2-MAT-01/P1**. Earlier scoped closures and their regression
matrix remain. Baseline browser308 Vitest/44 Playwright and clean PASS, both complete
state lanes PASS; historical browser timeout cause UNKNOWN. Foundation downgrade/
re-upgrade/contracts/wheel and subsequent storage/startup/HTTP smoke tail NOT RUN
after PG exit1, clean SKIPPED. Other jobs' green evidence does not replace that tail.

C0 source intake precedes one normal automatic CI on the same PR; full9+clean9,
all foundation tail, exact dedicated tenancy/ACL/SENT atomicity and both complete
state lanes are mandatory again after this correction. Source is REVIEW on return,
then C2 HOLD; C1/C3/C5/C6/C8 HOLD. Remaining owner acceptance then independent C8.
MATERIAL/M3 IN_PROGRESS, gate OFF, PR Draft/BLOCKED, not INTEGRATED/VERIFIED.
Normal P prep719.560822218s left0.439177782s; foundation43:11 stopped before its tail.
No optimization allowance follows. Original S/retained600/P720/fixed120/+480/S+1200/
cleanup90/state25/browser25/foundation45 and individual3s/60s/10s remain unchanged.
No clock reset/subtraction/retry/budget increase, installs/bootstrap/new services/
Docker/PG/browser runtime/Actions operations/PR-head move/new PR/merge. Live/VM/
working DB/S3/sends/deploy/native/A08/P-A03-09/renewal/collector/M4 unissued;
IMPL-05/broad optimization DEFERRED.

## 16. NATIVE-CONTEXT — PROPOSED

### 16.1. Выдача, accepted baseline и статус

**C3-M3.1-NATIVE-CONTEXT-CONTRACT-R1, 2026-10-17 UTC: REVIEW / proposal; затем C3 HOLD.**
[C0 task](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6228802023).
Ветка `c3/m3-1-native-context-contract-r1`; exact base/sole parent
`e205e22051bc06295758b504d84699652b176c15`, base tree
`85206b9c66ac151f3847aa39f46fb75663a18b91`. Один docs commit; full identity/numstat
в canonical return, без self-SHA/status-only commit. Только три task documents.
Existing prefix through§15.18 — exact603955 bytes, SHA256
`9643365fa8b534d6cf37a181c7c03ed76bd16b9d559016794b377b9a1eb1064b`.

[C0 postmerge](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6228792048)
принял MATERIAL **INTEGRATED/VERIFIED LOCAL/TEST**, все11 findings CLOSED.
PR34 merged; accepted main/tree выше. [CI38960113060 attempt1 push/main](https://github.com/Elefesys/ai-service-manager/actions/runs/38960113060)
имеет9 jobs и9 clean SUCCESS; [C8 independent PASS](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6223489359)
относится к candidate/tested-merge с тем же tree. Старые OPEN3/Draft/NOT RUN в§15.18
исторические, не current disposition. Acceptance не означает VM deployment.

**Весь§16 — PROPOSED; ничего не supersede-ит до отдельной приёмки C0.**
Endpoint/DDL/guard/reader ниже ещё не реализованы. Applied0001–0012 frozen;
следующая revision/predecessor/reservation не назначены. M3 IN_PROGRESS;
P-01/latest-human-context/A08, P-05 renewal/collector, P-A03-09 account и
M3-ACCEPTANCE/A12 OPEN. MATERIAL gate OFF по C0. Runtime tests/services/install/
CI actions/account/API/VM/S3/sends/deploy этим return не выполнялись.

### 16.2. Выбранный механизм и доказуемые пределы

Рекомендуется **явный live OWNER reconciliation + observation review barrier**.
Владелец сверяет canonical Console history и известную ему внешнюю переписку,
сохраняет ограниченный текст актуальных договорённостей либо явно подтверждает
достаточность canonical history. Immutable revision связывается с actor/CAS/
observed epoch. Затем существующий explicit Resume атомарно выбирает эту revision
и связывает с новым generation/fence. Save context сам не включает AI.
Уже доставленный native текст не отправляется через Console повторно.

| Вариант | Реальная гарантия | Выбор |
|---|---|---|
| Context-only native ingestion прямо в human transcript | Сохраняет только пришедшее в webhook | Не доказывает human origin, causal order или отсутствие пропусков; не решает no-update контрпример |
| Только обязательный OWNER reconciliation | Authenticated OWNER утверждает context, в том числе без native update | Минимальный canonical источник; сервер проверяет identity/commit/CAS, но не истинность/полноту утверждения |
| **Reconciliation + conservative observation barrier** | Предыдущее плюс запрет новых AI actions при известном несверенном сигнале | **Рекомендуется**; V2 sidecar остаётся observation, не вторым Message/transport engine |

Три authority различны: trusted route/V2 receipt доказывает получение projection;
`sender_id=approved owner` без bot/offline markers остаётся OWNER_CANDIDATE_ONLY;
Workspace OWNER через live authenticated command подтверждает **свой текст**.
Actor берётся из session/membership, provider sender/time — только из sidecar.
Console actor не объявляется Telegram sender и не обязан совпадать с Telegram owner.
Caller `is_human`, отсутствие marker, provider date/update_id/arrival/fence не proof.

Гарантия после реализации: **каждый новый Resume при включённой policy требует
свежего explicit confirmed context текущего HUMAN generation; известные
несверенные observations и pending context input запрещают Resume/admission;
fresh snapshot содержит выбранную R и current canonical данные**.
Известный новый сигнал в AI закрывает дальнейший admission, но не меняет
control_mode/G. UI показывает AI + «нужна сверка, новые действия остановлены»;
Owner выполняет Takeover → reconciliation → Resume. Это availability tradeoff,
не реализованный automatic native takeover.

**D1, неустранимый остаток.** H1: после подтверждения/Resume native сообщения нет.
H2: оно есть, но update отсутствует. DB/input сервера одинаковы; нельзя разрешить
H1 и гарантированно остановить H2. Delayed pre-Resume и immediate post-Resume
с одинаковыми полями также неразличимы (§15.5). Mandatory confirmation устраняет
молчаливый Resume исходного контрпримера, **если Owner передал договорённость**;
не доказывает полноту истории, истинность attestation или unseen post-Resume
intervention. UI требует Takeover до внешней переписки; это операционная граница,
не серверное обнаружение невидимого действия.

Spec5.12/5.12.1, ADR026/180/267 (HUMAN suppression, explicit Resume/latest context,
serialized admission) сохраняются. Если C0 требует безусловно полного Telegram
history/causal native takeover, proposal недостаточен: нужен другой проверяемый
источник origin/history/causal acknowledgement либо отдельное изменение scope.
C3 LOCKED не меняет и A08 Console PASS не закрывает.

Адресная proposed delta к§15.5 после принятия: owner-confirmed context становится
resumable путём; нынешняя операционная HUMAN boundary дополняется server guard;
добавляется conservative review hold без mode/G toggle. Не меняются causality
limit, origin exclusions, terminal IGNORED replay, Client identity, UNKNOWN,
transport hashes и MATERIAL. Никаких новых внешних provider фактов.

### 16.3. Минимальная модель, provenance и media

Обозначения: V=Conversation.version; G=control_generation; F=activation_fence_seq;
N=human_observation_epoch; P=human_context_policy_epoch; R=current revision.
N — локальный счётчик сигналов сверки, P — поколение включения policy connection.
Это не provider watermark, control generation или доказательство полноты.
Counters checked bigint без wrap/reset; bootstrap NULL N читается как0.

| Proposed объект | Identity и необходимые данные |
|---|---|
| `app.channel_connections` additions | `human_context_policy` OFF_UNUSED/ON/PAUSED; `human_context_policy_epoch` initial0. Первый ON и reenable дают P+1; P не сбрасывается. Trusted provisioning authority, не owner toggle/GUC |
| `app.conversations` additions | Nullable `human_observation_epoch`, `human_context_revision_id`. Existing rows NULL без history backfill; pointer/N только под C barrier |
| New `platform.human_context_observations` | Immutable UUID, ws/C/Client/connection, epoch N>0, captured P/G, first V2 source receipt, class, semantic digest, accepted_at. UNIQUE(ws,C,N), UNIQUE(ws,C,digest). Typed preview читается из exact private sidecar; raw update не копируется |
| New `platform.human_context_reconciliations` | Immutable revision UUID/no, ws/C/Client/actor, namespace/key/hash, previous R, expected G/V/P/N, accepted V=V+1, disposition/text/source_media/attestation, private reviewed_ingress_seq, Audit/time, exact result. Revision одновременно command receipt; отдельная receipt table не нужна |
| Existing `conversation_control_receipts` additions | Nullable R ID/P/N, all NULL у retained rows/TAKEOVER, all non-NULL у new policy RESUME. Same-ws/C/Client/R relation. Existing V1 fingerprint/result/timestamps/guard_profile/fence неизменны |

Compound FK связывает **тот же Client и C**, ws/connection/chat; Workspace alone
недостаточно. Observation source: codec2, exact bot/update/ws/connection/chat
из verified provenance. Previous/current R относится к той же C/Client.
Resume relation проверяет R.expected G=previous G, R.accepted V=receipt.context V,
R.P/N=saved P/N и confirmed disposition. Historical accepted counters не FK к
mutable V/G/N/P. Supporting identity keys/closed new nullable variant сохраняют
старые CHECK; old receipt rows не backfill-ятся.

Обе новые tables ENABLE/FORCE RLS; runtime non-owner/non-BYPASSRLS, no direct
SELECT/DML; PUBLIC revoked; narrow capabilities с pinned `pg_catalog,pg_temp`.
Нет native Message table, общего event framework или пустых future tables.

Observation digest отдельный от frozen V1/V2 hashes: prefix
`asm:m3:human_observation:v1\n`, length-prefixed UTF-8 parts (NULL=`-1:\n`),
ws,C,Client,connection,discriminator,chat,message ID (DELETE: canonical sorted unique
ID array), exact origin markers/sender,sent_at,edited_at,typed content. Нет update_id,
arrival/P/G/N/mode. JSON arrays/content — closed deterministic field order,
exact Unicode; SQL/Python vectors обязательны. Same semantic event/new update_id
создаёт новый transport receipt, но не второй mark/N. Distinct content/origin/date
— новый сигнал, не overwrite/human chronological claim. DELETE batch один mark;
existing MATERIAL effects per-target. Old V1/V2 key replay возвращается **до**
новой branch, включая native IGNORED при gate OFF.

Current projection = R pointer + effective canonical Messages + review status.
R — отдельный OWNER_CONFIRMED_CONTEXT, не OUTBOUND Message и не model summary.
UI отдельно показывает actor/time/coverage, candidates и настоящую переписку.
Save context не создаёт Message/Client/identity/Inbox/Turn/member/File/FETCH/WINNER/
Outbox/SEND Job; не меняет last_client_inbound_at и не является delivery evidence.

| Material | Canonical treatment / предел |
|---|---|
| Native TEXT | Candidate preview; canonical только exact owner text после подтверждения, с actor/time команды, не provider sender/time |
| Native PHOTO/caption | Caption preview; image_availability=NATIVE_UNAVAILABLE. Нет getFile/FETCH/S3/URL/File/WINNER. Owner может описать достаточный смысл текстом, но это не vision evidence |
| Unsupported/ambiguous | Typed reason, нет usable media. OWNER_TEXT с достаточными фактами либо UNRESOLVED; непредставимый существенный материал запрещает Resume |
| Native EDIT/DELETE | Новый mark/hold, old R immutable. New owner revision заменяет current text или отзывает его через UNRESOLVED; candidate не редактирует слова actor автоматически |
| Canonical edit/delete | Existing0012 effective current, versions, sticky Turn invalidation/private-file guards. Mark не заменяет MATERIAL и не создаёт второго semantic V increment |
| Correction/withdrawal R | Только HUMAN; если AI — сначала explicit Takeover. New revision/previous pointer/CAS, old receipts/Audit остаются; полного удаления evidence нет |

Canonical private image доступен только existing live owner→same C/Message/File→
effective ORIGINAL_READY→WINNER path. Observation/R не дают grant. Provider file IDs,
raw JSON, storage keys, signed URLs и secrets не выходят в observation DTO/Audit/
diagnostics; text/caption только в защищённых command/read/snapshot.

### 16.4. Current reader и proposed API

Fresh policy input получает closed private **TurnSnapshotV3**: retained V2
members/current плюс `human_context` (R ID/no, actor/time, disposition/text,
accepted V, confirmed G/P/N, source_media, coverage=OWNER_ASSERTED_TEXT_ONLY),
`context_policy_epoch`, `human_observation_epoch`, linked Resume ID для guard,
`recent_messages` и `history_truncated`. Recent tail — до16 canonical Messages,
ordered(created_at,id), read17 для флага truncation; ID/version/direction/current/
delivery/file refs через same0012 effective helper. Manual/automation origin
берётся из existing receipt/Outbox.kind linkage; ambiguous legacy помечен
LEGACY_UNATTRIBUTED, не human по одной OUTBOUND direction. IDs позволяют downstream
не удвоить current members. Reader не выдаёт tail за полную историю; более ранние
релевантные договорённости Owner явно включает в R. Это bounded M3 context input,
не реализация M4 ContextBuilder.

Snapshot под C/Turn фиксирует одну V, R/N/P и current canonical projection; digest
покрывает весь saved JSON. New V3 bound —2,097,152 UTF-8 bytes canonical SQL JSON,
до existing64 members и16 history rows, каждый текст с прежними bounds. При
превышении — typed internal CONTEXT_TOO_LARGE и NOT_ALLOWED до consumer/action;
текст молча не обрезается. Это новый payload bound, не увеличение существующих
request/CI/time caps. SQL/Python vectors и C1 review нужны до реализации.
V1/V2 saved snapshots/results/digests не переписываются и читаются прежними parsers.

V3 `human_context` использует exact non-NULL current_revision shape ниже, без
UNRESOLVED. `recent_messages` entry ровно `{message_id,version,direction,origin,
created_at,current,delivery,file}`: IDs canonical UUID, version positive decimal,
UTC6 time, current=existing MessageCurrent; delivery=existing nullable delivery DTO;
file=NULL либо `{file_id,version,status}` с реальным FileObject, без grant/URL.
Origin closed CLIENT_INBOUND/OWNER_MANUAL/CONTROLLED_AUTOMATION/LEGACY_UNATTRIBUTED,
по canonical ingest/manual/guard receipt links. Для чтения usable content берётся
только current, historical refs не оживляют hidden/replaced image.
Дополнительные V3 поля `context_coverage=OWNER_ASSERTED_TEXT_ONLY` и ordered unique
`context_limitations`: всегда PROVIDER_HISTORY_UNVERIFIED, плюс
NATIVE_MEDIA_UNAVAILABLE при R.source_media=UNAVAILABLE. Эта причина объясняет
PARTIAL отдельно от existing member-media readiness; no untyped reason string.

`context_coverage` всегда OWNER_ASSERTED_TEXT_ONLY, никогда TELEGRAM_COMPLETE.
`source_media=UNAVAILABLE` даёт PARTIAL/NATIVE_MEDIA_UNAVAILABLE; caption/owner
description не делают фото доступным. PROVIDER_HISTORY_UNVERIFIED сохраняется
даже при N=0. Existing COMPLETE относится только к доступности выбранных inputs,
не полноте истории. UNRESOLVED не usable context. Owner text — domain evidence
со своим происхождением, не override hard policies/permissions (Spec5.8–5.14).
Snapshot не содержит storage key/signed URL и не запускает media/LLM I/O.

New prefix: `/api/v1/workspaces/{workspace_id}/conversations/{conversation_id}`.
Existing `GET /control`, `POST /takeover`, `POST /resume` success DTO остаются
strict прежними. Resume body сохраняет три existing expected fields: current R
выбирается через V/G под DB lock, а не optional caller pointer/override.

| Route | Closed shape / outcome |
|---|---|
| New `GET /human-context` | No query, live OWNER. `workspace_id,conversation_id,client_id,observed_at,control_mode,control_generation,context_version,policy,policy_epoch,observation_epoch,ingress_checkpoint,current_revision,review_status,resume_blockers,pending_context_input,has_failed_context_input,unreviewed_failed_context_input,manual_delivery`. No writes |
| New `GET /human-context/observations` | limit1…100 default20, optional strict opaque cursor `{v:1,ws,C,Client,P,through_N,after_N}`. `items,next_cursor,through_epoch,current_epoch,observed_at`; ascending N, fixed through_N, no completeness promise |
| New `POST /human-context/reconcile` | Strict body ниже, one Idempotency-Key, only HUMAN. R/Audit/V+1; G/mode/F unchanged. Exact ACCEPTED/REPLAY result; save не выполняет Resume |
| Existing `POST /resume` | Existing body/client/G/V; после existing live gates/CAS новый guard§16.5. Atomic R selection→receipt relation→AI/G+1/Fnew, V0. V1 fingerprint/result сохранены; new error parser меняется парно |

`ingress_checkpoint` — maximum committed same-connection/chat Inbox.turn_ingress_seq
под C (0 если нет); это дополнительный **локальный read checkpoint**, не causal
native proof. Нужен потому, что queued/failed ingress ещё может не увеличить V.
Pending predicate и checkpoint читаются indexed EXISTS/ORDER LIMIT1, no full tenant
scan. Новые NULL capture после cutover запрещены; retained NULL rows принадлежат
старой истории. Reconcile CAS включает этот checkpoint; R сохраняет его как
reviewed_ingress_seq. Saved R может подтвердить known FAILED gap только через
OWNER_TEXT, не CANONICAL_SUFFICIENT. После Resume новый failed/unmaterialized Inbox
с seq>R.checkpoint закрывает admission до новой сверки; retained NULL gaps
обрабатываются при bootstrap, не объявляются отсутствующими. Fresh receipt replay
не меняет checkpoint. Входные bytes не считаются человеческим native контекстом.

Reconcile exact body (all fields required; unknown keys invalid):

```json
{
  "expected_client_id": "<canonical UUID>",
  "expected_control_generation": "<positive decimal bigint>",
  "expected_context_version": "<positive decimal bigint>",
  "expected_policy_epoch": "<positive decimal bigint>",
  "expected_observation_epoch": "<nonnegative decimal bigint>",
  "expected_ingress_checkpoint": "<nonnegative decimal bigint>",
  "expected_revision_id": null,
  "disposition": "OWNER_TEXT",
  "text": "Согласовали другой вариант; прежний вариант больше не актуален.",
  "source_media": "NONE",
  "attestation": "REVIEWED_AVAILABLE_CONTEXT"
}
```

R ID nullable/current; disposition CANONICAL_SUFFICIENT(text=NULL,source_media=NONE),
OWNER_TEXT(nonempty exact Unicode≤4096 codepoints/16384 UTF-8 bytes), UNRESOLVED
(NULL либо bounded text). source_media NONE/UNAVAILABLE; attestation literal выше.
Attestation означает утверждение Owner о доступном ему контексте/существенных
договорённостях, не proof чтения каждой страницы или полной внешней истории.

Новое noncanonical observation после последнего selected Resume требует OWNER_TEXT
с содержанием/объяснением нерелевантности либо UNRESOLVED, не CANONICAL_SUFFICIENT.
При native PHOTO/unsupported в этом интервале NONE запрещён: description сохраняет
UNAVAILABLE. Wholly canonical processed mutation может быть подтверждена
CANONICAL_SUFFICIENT. Для no-update Owner сам сообщает о существенном media gap.
Непереданный факт невозможно выявить schema validation. Последующий R — полный
replacement текущего owner context: UI prefill/показывает предыдущий текст и явно
предупреждает об отзыве/замене, не очищает договорённости автоматически.

`current_revision` NULL либо exact `{revision_id,revision_no,previous_revision_id,
actor_user_account_id,accepted_at,disposition,text,source_media,coverage,
confirmed_generation,accepted_context_version,policy_epoch,observation_epoch,
reviewed_ingress_checkpoint}`. Review status BOOTSTRAP_REQUIRED /
CONFIRMATION_REQUIRED / CONFIRMED / UNRESOLVED / NEW_OBSERVATION / POLICY_PAUSED.
Resume blockers — closed ordered applicable list POLICY_INACTIVE, HUMAN_REQUIRED,
CONTEXT_INPUT_PENDING, CONTEXT_INPUT_UNRESOLVED, CONTEXT_CONFIRMATION_REQUIRED,
CONTEXT_UNRESOLVED, CONTEXT_CHANGED, NEW_OBSERVATION. Product denial остаётся
existing CONTROL gate. CONFIRMED в AI — accepted linked Resume, не право его повторить.
Manual delivery flags прежние has_dispatching/has_unknown с manual scope.

Observation item exact `{observation_id,epoch,classification,observed_at,source_kind,
preview,coverage}`. Class NATIVE_CANDIDATE/AMBIGUOUS_NONCLIENT/CANONICAL_MUTATION/
UNBOUND_MUTATION; kind NEW/EDIT/DELETE. Preview TEXT(text), PHOTO(caption,
image_availability=NATIVE_UNAVAILABLE), UNSUPPORTED(reason), DELETE(target_count);
coverage=PROVIDER_OBSERVATION_ONLY. No provider IDs/URLs. Cursor связан ws/C/Client;
current_epoch>through_epoch требует fresh read, а не молчаливый «все просмотрены».

Command result exact `{workspace_id,conversation_id,client_id,receipt_id,revision_id,
revision_no,previous_revision_id,audit_event_id,control_generation,
previous_context_version,accepted_context_version,policy_epoch,observation_epoch,
reviewed_ingress_checkpoint,disposition,source_media,coverage,accepted_at}`.
receipt_id=revision_id; V'=V+1, G unchanged. Text только в protected current read.
Wrapper `{outcome:ACCEPTED|REPLAY,result}`; replay — saved result, не current pointer.

Namespace HUMAN_CONTEXT_RECONCILE_V1, UNIQUE(ws,namespace,key); existing key ASCII
`[A-Za-z0-9._:-]{1,128}`. DB SHA256 prefix `asm:m3:human_context_reconcile:v1\n`;
length-prefixed UTF-8 parts: ws,actor,C,expected Client,G,V,P,N,ingress checkpoint,
previous R,disposition,text,source_media,attestation. NULL=`-1:\n`;
nonnull=`byte_length:value\n`, canonical decimals, exact Unicode без trim/NFC.
Python/SQL vectors проверяют каждый field/NULL/empty. Caller hash не authority.

Command order: strict headers/body → cookie/Origin/CSRF/live OWNER → key lock и
saved exact replay/conflict → scope/live locks → post-wait policy/authority →
CAS/semantic guards → writes → outer commit →200. Replay требует current OWNER и
same relation, но предшествует новым product/policy/CAS guards; revoke→403.
Same key changed body/actor→409 IDEMPOTENCY_KEY_CONFLICT; different key stale
G/V/P/N/checkpoint/R→409 STALE_STATE; new reconcile in AI→409 HUMAN_REQUIRED.
Reconcile доступен как Takeover без manual_send entitlement, включая PAUSED:
save/withdraw context не покупка/отправка. Resume сохраняет existing active
Business/connection/post-lock entitlement, structural failure/product/CAS precedence,
затем новые guards. Missing/stale R→409 CONTEXT_CONFIRMATION_REQUIRED;
UNRESOLVED→409 CONTEXT_UNRESOLVED; pending→409 CONTEXT_INPUT_PENDING;
unreviewed failed gap→409 CONTEXT_INPUT_UNRESOLVED; PAUSED→409 CONTEXT_POLICY_PAUSED.
Counters overflow fully rollback; new VERSION_EXHAUSTED, existing control G retains
CONTROL_VERSION_EXHAUSTED. Остальные 401/403/404/413/415/422/429/500/503/no-store —
existing conventions; request body/caps не расширяются.

Audit: HUMAN_CONTEXT_RECONCILED, USER_ACCOUNT/live actor, object_type CONVERSATION,
object_id C, object_version accepted V; payload ровно `{revision_id,
previous_revision_id,disposition,source_media,control_generation,
previous_context_version,accepted_context_version,policy_epoch,observation_epoch,
reviewed_ingress_checkpoint}`. Без текста/hash/key/provider IDs. Typed composite
R→Audit включает ws/C/actor/accepted V/event/revision identity, без circular
Audit→R FK. Resume сохраняет один existing Audit; selected R хранится в receipt
relation. Observation не USER_ACCOUNT Audit/CONVERSATION_TAKEN_OVER.

UI: candidate/current/history отдельно; объяснение причины hold; «Сохранить
сверенный контекст», затем отдельное explicit «Разрешить автоматику». Fresh GET
определяет mode/R; receipt не optimistic current. Network/commit loss удерживает
exact actor/ws/C/Client/key/body в памяти страницы; session/CSRF recovery и тот же
POST. Valid200+failed GET повторяет только GET. New body/version — fresh intent
после разрешения прежней неопределённости. Нет переноса в другой Workspace;
revoke очищает protected views; late response предыдущего C отвергается.

### 16.5. Closed transitions и Resume boundary

Scope: known exact C/Client, policy ON (observations также в PAUSED).
OFF_UNUSED сохраняет legacy behavior только до cutover; PAUSED запрещает
new Resume/automation. Priority: auth/route/key replay → discriminator →
NEW origin exclusions → candidate; EDIT/DELETE не приписываются человеку по from.
`mark` означает first semantic observation+N+1, **V/G/F unchanged**.
R acceptance даёт V+1, Resume G+1/Fnew. N проверяется отдельно в каждом admission;
не искусственный context bump за candidate.

| Event / before | Durable after | Resume/admission |
|---|---|---|
| No trusted route / mismatched C/Client / unknown chat | Existing reject/ignored;0 C/Client/mark из owner sender | Future C default HUMAN/needs bootstrap; history восполняет Owner |
| Existing V1/V2 update key | Exact saved receipt/conflict,0 counters | Old ignored never reprocessed |
| Fresh key, same observation digest | New transport receipt/sidecar; existing mark/N | Duplicate не инвалидирует подтверждение |
| NEW own sender_business_bot или exact known outbound echo | Existing exclusion/IGNORED_ECHO;0 mark | No human/SENT/takeover; UNKNOWN unchanged |
| NEW explicit other bot/sender_is_bot TRUE/offline TRUE | Automated exclusion;0 mark | Не human proof, no mode change; контекст других bots не обещан |
| NEW owner candidate/ambiguous nonclient known private chat, markers absent | mark, old native/unsupported receipt,0 Message | HUMAN требует R; AI остаётся AI с review hold |
| NEW unsupported/native sender_chat/ambiguous known chat | mark AMBIGUOUS_NONCLIENT + unavailable reason | OWNER_TEXT/UNRESOLVED; no false COMPLETE |
| Fresh EDIT/DELETE known chat | One mark: all targets canonical→CANONICAL_MUTATION, иначе UNBOUND_MUTATION; MATERIAL queue/fold отдельно | Hold включает Client edit. Не проверять sender как human author; pending must settle |
| Mutation worker applies later | Existing Message/V per-target/sticky Turn effects; no second mark | Hold автоматически не снимается; saved MATERIAL result immutable |
| New eligible Client ingress | Existing Inbox/Job/C capture, no human mark | Pending blocks reconcile/Resume/admission; after success V+1, future post-F Turn только по valid activation |
| Unseen native before Resume, no update | No DB mark | Mandatory confirmation даже N=0; Owner вводит факт |
| Unseen native after Resume, no update | No DB change | Обнаружение не гарантировано, D1; отсутствие updates не completeness |
| First delayed pre-Resume candidate arrives after Resume | Same mark as indistinguishable post-Resume event | Hold,0 G/F change; никакого causal guess |
| New reconcile in AI |409 HUMAN_REQUIRED,0 writes | Сначала Takeover; save не скрытый control transition |
| New reconcile in HUMAN, live auth/CAS G/V/P/N/checkpoint/R, pending=0 | Rnew+Audit/V+1, same G/F/N | Confirmed только CANONICAL_SUFFICIENT/OWNER_TEXT; UNRESOLVED blocks |
| Replay R после newer R/Takeover/Resume | Exact saved result,0 changes | Не переносить fulfilled R поверх current state |
| New Resume HUMAN, confirmed R with exact G/V/P/N/checkpoint, no pending/unreviewed gap | Existing receipt/Audit+R relation, G+1/Fnew,V0 | Только future eligible ingress; selection/activation one atom |
| New Resume missing/stale R, UNRESOLVED, pending/gap or paused |409 explicit reason,0 writes | No override/force/legacy bypass; new Resume in AI тоже требует HUMAN/fresh R |
| Fulfilled Resume replay, current уже HUMAN/другая R | Exact old result/relation,0 counters | Не снимает hold, не выдаёт новый G/F |
| Takeover/new accepted manual intent | Existing HUMAN/G+1/F=NULL; manual V+1 | Prior R readable but stale для нового G. Exact replay0 |
| Canonical Message/file/delivery changes between R and Resume | Existing V changes; R.accepted V stale | Fresh confirmation, включая Console-only |
| Canonical change after Resume without human observation | Existing V/sticky guards/current reader | Old snapshot stale; fresh eligible work reads current. EDIT/DELETE имеет дополнительный mark выше |
| DISPATCHING precedes mark/Takeover | Existing finish/recovery outcome | No recall/blind resend; only not-admitted work blocked |
| PAUSED/reenable P+1/old codec worker | Saved replay only, no fresh permission | New HUMAN/R/Resume; restart/gate cannot bypass used barrier |

`resume_ready` = live existing authority/product/CAS + mode HUMAN +
R confirmed + R.expected G=G + R.accepted V=V + R.P=P + R.N=N +
R.reviewed ingress=current checkpoint + pending=0 + no unreviewed failed gap.
CAS body выбирает exact current R через V; every new revision changes V.
Repeat Resume new key in AI не использует already-consumed R.

`automation_ready` после Resume = policy ON, current linked Resume/R,
mode AI/G=R.G+1=receipt.accepted G, F=receipt.F, current R pointer тот же,
P/N equal saved, no pending/unreviewed failed input, valid claim/Turn revision/
material usability/captured V и existing live authority/product gates.
Обычный Client input после Resume ожидаемо увеличивает V: action сравнивает
current V со своим snapshot/intent, **не** навечно с R.accepted V.
Takeover/reconciliation/new Resume не оживляют old HUMAN/invalidated Turns.

Pending — indexed EXISTS same connection/chat Inbox PENDING для eligible original
или queued EDIT/DELETE, включая legacy; no foreign row lock после C.
Failed gap виден Owner. R при OWNER_TEXT подтверждает известные на его checkpoint
failed originals; mutation failure связывается также с captured observation N.
Unreviewed failure после Resume: original seq>R.checkpoint или mutation mark>N;
retained NULL originals/mutations без mark — bootstrap history, не новые capture.
Новый eligible CLIENT_MESSAGE не может получить NULL ingress mark после cutover;
EDIT/DELETE сохраняют собственную retained shape и не становятся original ingress.
Old pending всегда должен settle до R; поэтому поздний terminal failure не может
обойти guard «pending исчез». Никакого automatic retry/backfill или fabricated
Client Message. Failure without content остаётся known limitation owner attestation.

### 16.6. Atomicity, lock order, workers и recovery

READ COMMITTED/physical-XID discipline, checks после waits. Нет HTTP/S3/LLM в txn.
Lease/UI read/caller GUC/old receipt не authority. GET context — one consistent
statement/snapshot, не смесь нескольких read moments; mutations recheck under C.

| Path | Order / atom |
|---|---|
| Fresh observation | Update-key advisory → connection SHARE → known C NO KEY UPDATE → dedupe/new source receipt+sidecar+mark/N and optional own Inbox/Job. Source exists before FK validation; commit before ACK |
| Reconcile/Resume | Existing live owner/workspace/user/membership → namespace/key advisory → Business SHARE → connection SHARE → billing only Resume → C NO KEY UPDATE. Recheck/CAS, immutable reads, own Audit/R/pointer. No Job/Inbox/Outbox/File/target lock after C |
| Original/material worker | Own Job UPDATE → own Inbox NO KEY UPDATE → connection UPDATE → identity(original) → C → sorted targets → Messages → Turns; existing0012 atom. Mark captured at ingress, no duplication |
| Send admission | Own Job → own Outbox → existing authority/Business/connection/billing → C→Turn; R/N/P/V/G/F recheck, DISPATCHING commit before external request |
| SENT/UNKNOWN/file completion | Retained Job→Outbox→C→existing target→Message/Turn or Job→File/upload→C→Turn. Human-context helper adds no connection/foreign-source lock |
| New V3 prepare/finalize/test consumer/Escalation producer | Own Job → required authority/Business/connection SHARE **before C** → C→Turn; common current guard. Existing acquired order не разворачивать |
| Enable/pause | Connection UPDATE conflicts with fresh admission/reconcile/Resume connection SHARE; no mass C lock/reset. P change invalidates old confirmations; in-flight outcome remains |

One physical C UPDATE for R pointer/bootstrap N/V+1; one for Resume G/F.
R/Audit insert precedes pointer UPDATE; deferred consistency verifies complete
atom at commit. Existing context hook cancels PENDING Escalation/CONTEXT_CHANGED
without second V bump; existing EXPIRED/FINAL/replay precedence stays.
R не resolve/send answer. N-only mark не вызывает material V hook: fresh
Escalation creation checks barrier→NOT_ALLOWED, fresh resolve→STALE_STATE;
cancel/exact winning replay сохраняются. Later R V+1 cancels PENDING normally.

FK/trigger review C2 обязателен: R→C/Client/actor/Audit, C→R — stable identity;
observation→immutable same-source provenance, no foreign worker Job lock.
No FK to mutable version/epoch. KEY SHARE from new FK must match preheld compatible
identity; no new connection edge inside SENT/file helpers. §15.18 lesson:
second UPDATE same row can recheck unchanged FK due to current-XID tuple;
review expanded SQL/trigger chain, not just Python order. Preserve changed-SENT
single target update/single C+2, no-op delivery+1, UNKNOWN and private contracts.
No disabled constraints, authority deferred until commit, added foreign prelocks,
lock-timeout increases or weakening old concurrency assertions.

Race outcomes: mark first→reconcile stale N; R first→later mark invalidates
readiness; Resume first→later mark closes next admission without G guess;
dispatch first→mark cannot recall already admitted request. Pending accepted
before Resume blocks; later eligible Client keeps normal fence capture.
Any insert/FK/counter/commit failure rolls back entire atom. Same-key advisory
gives one winner; changed key old CAS loses. Commit response loss replays exact
saved result, not regenerated timestamps/current state. Later HUMAN/R2 stays
current when old R1/Resume receipt replays.

Retained V1/V2 snapshot/receipt winning-token reads remain, but policy ON new
automation requires V3 and linked R/N/P. Old pending unstarted work follows
STALE/SUPERSEDED/NOT_ALLOWED terminal paths, no rewritten input/digest/new intent.
Old worker source rejected by readiness/drain; DB gates still deny old capability
calls. Shared guards cover prepare, accept, send-begin, Escalation create/resolve,
recovery decision for **new** action; not veto of already-started send finalize.
N/P hold does not require clearing/revising sticky material-invalidated Turn.
Resumption needs new G/F, so old generations never regain eligibility.
Effect-free TEST consumer stays effect-free; Telegram guarded automation remains
prohibited by existing LOCAL/TEST CONTROLLED policy. No live AI activation.

### 16.7. Rollout/compatibility proposal

1. C0 accepts decisions/reviews then assigns exact predecessor/revision. If renewal
   lands first, native inherits its accepted schema; otherwise reverse. Applied
   0001–0012 unchanged; no preallocated next number or renaming older files.
2. Drain old writers/workers/readers, upgrade and compatible source with exact
   schema readiness; no mixed old claim. Preserve old-column exports, V1/V2
   hashes/snapshots/receipts, UNKNOWN/private File/WINNER/history. Upgrade creates
   no historical native mark/Message/Turn/send job.
3. Initial OFF_UNUSED/P0, C fields NULL are not completeness. Enable requires paired
   current MATERIAL reader/gate on Telegram plus new backend/UI/worker readiness.
   Отключение требуемого MATERIAL consumer при used native policy требует PAUSED;
   readiness/admission отказывают mismatched native ON/material OFF.
   ON/P1 does not backfill history. Existing HUMAN requires first R; existing AI
   without linked R immediately fails admission and shows BOOTSTRAP_REQUIRED:
   Takeover→R→Resume. New C remains HUMAN.
4. First R covers current canonical history + owner-entered external facts.
   N0 means no fresh captured signals only. Old IGNORED keys replay without new
   effect even if V2 sidecar has text. Old event without receipt is fresh observation,
   not causal fresh-human proof; no high-water update_id/date drop. Old pending
   Inbox processes normally, no retroactive post-F eligibility.
5. Restart retains P/N/R. After ON, OFF_UNUSED cannot return: PAUSED blocks new
   Resume/AI, retains observations/read/Takeover/manual/save/replay. Reenable P+1
   requires HUMAN/new R/new Resume. Save while PAUSED is evidence, not confirmation
   for a future P. Policy change trusted provisioning/operator path, no owner
   HTTP toggle; C2/C6 define scoped receipt/Audit using existing provisioning style.
6. P>0 is monotonic used marker. Used downgrade refuses before any DDL if activated
   or if marks/R/Resume links/V3 snapshots exist. No deleting evidence to downgrade.
   Unused reverse restores exact assigned predecessor definitions/ACL/inventory.
   Used recovery compatible source PAUSED/forward fix, never old0012 over used schema.

Minimal schema delta additionally needs bounded same-chat Inbox checkpoint/pending/
failed indexes (not full tenant scans), supporting composite identity/Audit keys,
private helpers and exact capability grants. New tables have immediate purpose.
Gate disable/restart does not reclassify transport history or grant action permission.
Future collector reads bounded markers, never replays IGNORED or infers completeness
from zero. TEST renewal remains separate authenticated provisioning with actual
valid interval/source/schema binding; this task does not renew or access accounts.

### 16.8. Конечные manual traces и будущие assertions

Это **ручной design analysis, не выполненные tests/PASS**. H/A=mode, T=fresh Turn,
r=confirmed R; default ON/P1/no pending. Save R:V+1; Resume:G+1/Fnew; mark:N+1.
Каждая строка требует конкретного assertion через actual PG/API/worker/browser
path; количество tests не target. Old invariants/caps не ослаблять.

| ID / before | Action → after | Достаточное LOCAL/TEST evidence и account предел |
|---|---|---|
| NC01 H,G7,V20,N0; native «согласовали другой вариант», update нет | Resume409; OWNER_TEXT→r1/V21; Resume→A/G8/Fnew; Client «да»→V22/Tnew | PG/API V3 содержит r1 text, linked G8/N0 и current history;0 native Message/Outbox/File/send. Browser explicit review. Account absence update не completeness |
| NC02 H после Console SENT,G7,V20,N0 | CANONICAL_SUFFICIENT→V21; Resume→G8; future Client→T | Snapshot tail содержит real manual ID/current text/SENT,0 resend. Browser two steps. Положительный Console путь не закрывает A08 |
| NC03 A/r1; pre-Resume delayed и post-Resume immediate с одинаковым V2 | Обе истории first arrival→N1/hold, same A/G/F | Two PG arms identical outcome,0 false takeover/SENT; account timing не устраняет неразличимость |
| NC04 fresh native затем duplicates | First N1; same key replay N1; new update_id/same semantic digest N1; changed content N2 | Normal normalizer/ingest, exact receipt/hash conflict409,0 V/G/Message; no observation reprocessing |
| NC05 A/r1, manual DISPATCHING/UNKNOWN | NEW own echo/other bot/offline TRUE excluded; absent markers candidate→hold | PG closed origin matrix; UNKNOWN unchanged/no adapter call. Account records particular markers only, не универсальность |
| NC06 H, native PHOTO/caption/unsupported | NONE/CANONICAL shortcut refused; OWNER_TEXT+UNAVAILABLE→PARTIAL; UNRESOLVED→Resume409 | API/UI media label,0 File/FETCH/WINNER/grant/send, no false native COMPLETE; D3 media scope |
| NC07 A/r1, unseen post-Resume native без update | DB unchanged; future Client может пройти current guard | Нельзя требовать PG «обнаружил невидимое». Explicit D1 limit/UI Takeover-before-native, account observation не доказательство |
| NC08 A/r1, native EDIT/DELETE | Mark/hold; old R immutable; Takeover→H; replacement/withdraw R→V+1 | PG/API new selected text or UNRESOLVED, old receipt equality, no manufactured Message delete. No-update limit NC07 |
| NC09 H/r1,V21, queued canonical edit/delete | Pending/mark blocks Resume; MATERIAL applies; fresh R/Resume не оживляет invalidated T | Existing provenance→guard bridge; current caption/replaced/deleted/private image correct, original per-target increments retained |
| NC10 две вкладки H/G7/V20 | Different keys same CAS: one R/V21, other409. Same key: ACCEPTED/REPLAY one result; changed body/actor/P/N/checkpoint conflict | API two connections/observed lock, one Audit, browser reload/no silent intent retarget |
| NC11 saved R/Resume, revoke while authority waits | Committed revoke denies new+replay403; foreign ws/wrong same-ws Client/R/cursor denied | RLS/compound FK/private grants/HTTP;0 leak/write; browser clears shared views |
| NC12 reconcile vs mark | Mark first→stale N; R first→V+1 then N+1 makes R not ready; rollback ingress→no mark/N | Actual two-connection barrier, commit/rollback; no timing guess/new sleep/budget |
| NC13 Resume vs Client/Edit/native ingress | Ingress first→N/checkpoint/pending guard; Resume first→G/F then mark hold or normal post-F Client capture | Both commit orders, capture immutable; date/update_id not causal proof |
| NC14 captured worker vs mark/Takeover | Hold first→no action; DISPATCHING first→later finalize allowed | Real GUARDS prepare/accept/begin, effect ledger, no Telegram live send |
| NC15 R response lost/crash/deferred failure | Before commit0; after commit replay one R/V/Audit; later R2 stays current on replayR1 | API/process boundary, exact result/timestamp, whole-atom rollback; browser valid200+GET failure read-only |
| NC16 Resume response lost then Takeover | Replay old AI receipt; fresh GET still HUMAN/new G; fulfilled R cannot activate newer G | Existing browser recovery journey extended with R binding; no double G/V/F/Audit |
| NC17 old V2 worker or invalidated Turn, enable/restart | Old terminal replay readable; fresh action refused; new post-F input V3 | Upgrade/worker tests, exact V1/V2 hashes/snapshots/files/UNKNOWN; readiness rejects mixed source |
| NC18 DISPATCHING crash/UNKNOWN/late echo/R/Resume | UNKNOWN stays, no return PENDING; permitted late finalize retains protocol | Existing persistent send ledger/token equality; no blind resend, missing ACK not SENT |
| NC19 existing H/A NULL state, enable/pause/reenable | AI bootstrap hold; H needs R; PAUSED blocks; P+1 fresh H/R/Resume; used downgrade refused before DDL | Finite migration/DB/UI test, exact old exports; no VM actions |
| NC20 pending/failed input and >16 history | Pending blocks; failed gap requires OWNER_TEXT; new failed seq/mark beyond R blocks; truncated=true | PG/API checkpoint CAS/failed-gap guards, no fake complete/backfill; owner attestation remains limited |

Additional assertions within these risks: all counter overflows roll whole atom
back; FK/trigger/late commit failure; stale scope response; Escalation N/P barrier;
post-wait product deny plus exact old replay; V3 byte-bound refusal without action.
No broad suite repetition solely for counts.

Account A08/P-A03-09 requires separate C0 assignment: bounded approved test dialog,
current valid TEST interval/source/schema/route/account binding and observations
TEXT/PHOTO/echo/offline/unsupported/edit/delete/missing update. Redacted metadata,
no raw/private content. NOT OBSERVED≠NOT POSSIBLE/COMPLETE; one account/timing
cannot prove universal provenance/completeness/causality. Renewal/collector/live
probe not part of this diff or of claimed LOCAL/TEST implementation evidence.

### 16.9. Sources и конкретная передача

Read: AGENTS/IMPL-001, original11/manifest and supplied originals (all11 exact);
applicable Spec5.8–5.14/5.12.1/18.5–18.9, ADR002–007/024–026/180/267,
MVP GJ-G/J+variants, Roadmap M3/M4, Implementation Plan M3.1/M3.2.
Retained M3 turns/context/control/guards/Escalation and MATERIAL§15.2–15.9/§15.18,
handoff decisions/assertions/register, latest C0/C8 receipts. Historical prefix
status is not reasserted as current.

| Actual source на accepted base | Design consequence |
|---|---|
| `backend/src/asm/telegram/{normalization,database}.py`;0012 ingress | V1 replay before V2; native ignored+sidecar without Inbox/Job. New mark belongs fresh routed branch, not reprocessing old ignored |
| `conversations/{control,http,http_models}.py`;0009/0010 CONTROL | Three-field Resume/live OWNER/product/CAS, no native guard. Separate accepted R V required before existing exact control receipt |
| `conversations/{turns,guards,material,escalations}.py`;0012 shared/current helpers | V2 snapshot members/current, no native handoff. Explicit V3/R+bounded history needed; sticky guards retained |
| `messaging/{database,worker,http_models,http_service}.py` | Winning-token replay, permit only after commit, UNKNOWN; same effective history reader. R/observation not transport outcome |
| `files/{service,database}.py`;0012 files_read_manifest | Canonical ownership/current ORIGINAL_READY/WINNER, no native file authority |
| `frontend/src/{ConversationControl.tsx,conversation-control-api.ts,MessagingPanel.tsx,messaging-api.ts}` | Strict parser/memory intent/receipt≠current, valid200 recovery read-only |
| Control/guards/provenance PG/API tests; `frontend/e2e/conversation-control.spec.ts` | Actual two-tab/revoke/ingress-wait/stale/UNKNOWN/old Resume replay boundaries to extend narrowly |

Следующие **proposed write sets**, не разрешение на код сейчас. New migration
filename не присваивает revision/reservation; C0 выдаёт exact predecessor/paths.
No framework, Telegram client method, M4 implementation or empty tables.

| Slice / dependency / owner review | Minimal exact paths |
|---|---|
| C0 decisions → C3 contract R2 only if comments | `docs/tasks/M3_CONTRACT.md`, `docs/tasks/M3_HANDOFF.md`, `docs/TASK_REGISTER.md`; ближайший scope до runtime authorization |
| C2 schema/security design with C3 after D1–D4 | Proposed new `migrations/versions/m3_native_context.py`, `tests/test_m3_1_native_context_migrations.py`; existing `tests/test_tenancy_postgres.py`. Two tables/additions/FKs/RLS/Audit, shared locks/capabilities, unused reverse/used refusal; no applied edits |
| C3 backend + C1 API/security review after schema contract | New `backend/src/asm/conversations/native_context.py`, `backend/src/asm/conversations/native_context_http.py`, `backend/src/asm/conversations/native_context_http_models.py`; existing `backend/src/asm/conversations/control.py`, `backend/src/asm/conversations/http.py`, `backend/src/asm/conversations/http_models.py`, `backend/src/asm/conversations/turns.py`, `backend/src/asm/conversations/guards.py`, `backend/src/asm/conversations/escalations.py`; `backend/src/asm/tenancy/database.py`, `backend/src/asm/messaging/database.py`, `backend/src/asm/telegram/database.py`, `backend/src/asm/billing/models.py`, `backend/src/asm/foundation.py`, `contracts/openapi.json`. Route wiring is actually foundation.py; V2 normalizer/hash need no change |
| Focused C3/C1 assertions | New `tests/test_m3_1_native_context.py`, `tests/test_m3_1_native_context_postgres.py`, `tests/test_m3_1_native_context_api_postgres.py`. Existing `tests/test_m3_1_control_postgres.py`, `tests/test_m3_1_control_api_postgres.py`, `tests/test_m3_1_guards_postgres.py`, `tests/test_m3_1_turns_postgres.py`, `tests/test_m3_2_escalations_postgres.py`, `tests/test_m3_2_escalations_api_postgres.py`; NC risks via actual capabilities |
| C5 paired UI after accepted API, C1 errors review | New `frontend/src/HumanContextPanel.tsx`, `frontend/src/HumanContextPanel.test.tsx`, `frontend/src/human-context-api.ts`, `frontend/src/human-context-api.test.ts`. Existing `frontend/src/ConversationControl.tsx`, `frontend/src/conversation-control-api.ts`, `frontend/src/ConversationControl.test.tsx`, `frontend/src/conversation-control-api.test.ts`, `frontend/src/MessagingPanel.tsx`, `frontend/src/billing-api.ts`, `frontend/src/billing-api.test.ts`, `frontend/src/BillingPanel.tsx`, `frontend/src/BillingPanel.test.tsx`, `frontend/e2e/conversation-control.spec.ts` |
| C6 with C2, after accepted runtime tree | `backend/src/asm/foundation.py`, `backend/src/asm/telegram/provisioning.py`, `scripts/prepare_telegram_egress.py`, `scripts/test_telegram_egress.sh`, `scripts/test_telegram_egress_migration.sh`, `tests/test_telegram_egress.py`, `tests/test_telegram_egress_migration.py`, `tests/test_telegram_egress_postgres.py`, `docs/runbooks/M2_TELEGRAM_LOCAL_TEST.md`; exact successor profiles/readiness/policy lifecycle, no live/renewal/optimization |
| C3/C5 actual browser fixture only if needed | `scripts/m2_4_browser_fixture.py`, `scripts/m2_4_browser_worker.py`, `tests/test_m2_4_browser_fixture.py`; same capabilities, no forged receipt/send |
| C8 → C0 | Independent review completed changed-risk tree/evidence; C0 integration/actual CI, then separate account/renewal/A12 assignments. No agents launched by this docs task |

Все paths в future write sets — exact; actual assignment C0 определяет разрешения.
Current tests/profile restorers
requiring exact successor head are added only after specific dependency inspection,
not via wildcard. No modification of original11, frozen migration/functions or
old lane assertions. Budgets S/600/P720/fixed120/+480/S+1200/cleanup90/state25/browser25/
foundation45 and3s/60s/10s unchanged; IMPL-05/broad optimization DEFERRED.

### 16.10. C0 decisions и verification disposition

| ID | Recommended decision / unresolved acceptance |
|---|---|
| D1 assurance/scope | Accept owner-confirmed available context with explicit unseen/native completeness limit. If unconditional provider-complete/causal guarantee is required, reject this implementation scope and choose another evidence channel/explicit LOCKED decision. No silent A08/M3 reduction |
| D2 availability | Conservative N/P hold without automatic HUMAN, including ambiguous/delayed/fresh EDIT/DELETE; mandatory R for every new HUMAN→Resume. UI exposes AI plus blocked reason; no date heuristic |
| D3 media | TEXT_ONLY description with UNAVAILABLE/PARTIAL, UNRESOLVED blocks Resume. If A08 requires actual native image bytes, separate File/source/grant scope before closure |
| D4 concrete implementation | C1/C2 approve exact command/error/Audit/FK/lock graph, V3 bound/checkpoints/failed-gap rules; C0 assigns predecessor/revision and owner allowlists. Current table is proposal, no runtime authorization |

Source/manifest/accepted head/tree inspection выполнены на exact checkout до сбоя
локальной среды. После authoring среда потеряла exec-server/filesystem connection;
повторное восстановление не состоялось. Финальные документы подготовлены от exact
GitHub base blobs с append-only prefix, read-back/hash/changed-path/whitespace/link
проверками, перечисленными в canonical return. **Local git diff --check для final
candidate NOT RUN** из-за environment failure; whitespace/conflict-marker check
выполнен отдельно и не выдаётся за запуск git. Product runtime/PG/browser/build/
services/install/CI actions NOT RUN by scope. Это reviewable proposal с явным
ограничением verification, не native runtime PASS.

Next minimal scope: C0 decision record + точечные C1 API/security и C2 schema/
serialization reviews; C3 R2 только по конкретным замечаниям. Ни migration/runtime
branch/PR, ни TEST interval/probe/deploy пока не выданы. C3 return REVIEW, затем
HOLD; C1/C2/C5/C6/C8 HOLD до собственных назначений. P-01/A08/M3 остаются OPEN.

