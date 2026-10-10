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

Предлагается **сохранить один существующий продуктовый gate** для нового Resume:
реальный EntitlementService `evaluate_product(..., messaging.manual_send)` и
DB `messaging_manual_send_allowed`. Это консервативное условие доступности уже
подключённого messaging-продукта, **не выдача права AI-send по manual permission**.
CONTROL не добавляет catalog/entitlement/TEST interval и не меняет пять keys GET
billing. Будущие GUARDS/M4 обязаны отдельно определить и проверять автоматическую
capability; один Resume/его receipt её не заменяют. Такое повторное использование
gate — явное предложение C1/C0 (§12.12), не неявное расширение frozen R4.

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
4. После **всех потенциальных ожиданий** новый coherently locked DB-time billing
   snapshot → EntitlementService (Resume), затем DB policy validation с тем же
   precedence. Structural/availability/product denial имеет приоритет перед CAS;
   затем expected_generation и expected_context_version, затем overflow.
5. Один atomic transition, receipt и Audit. Reply только после commit. Никакой
   сети, нового job/Outbox или независимого commit внутри control command.

Resume service вызывает narrow prepare capability для locks/replay, затем реальный
EntitlementService, затем execute в **том же** unit. Execute повторяет canonical
receipt/authority/CAS/DB-time policy; caller `allow=true` не принимает. SQL capability
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
context, accepted_at, exact result и typed Audit binding. Accepted_at — DB clock
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
повтор temporal product/channel checks → HUMAN/gen+1/fence=NULL → новый Message
→ прежний context trigger+1 → Outbox/Audit/receipt/Job → commit`.

Предлагаемый `conversation_manual_prelock(uuid,text,text)` — узкая owner-only capability
**только для final public phase**. Она берёт отсутствующие authority/Business/
connection/state/billing locks в указанном порядке и последний Conversation lock,
не пишет mode и не выдаёт send permission. Args — conversation, exact text, key; она сначала повторяет canonical
`messaging_prepare_text`, поэтому сама не получает Conversation до M2 namespace
lock. В public service вызывается после prepare/replay (и Telegram observation)
до последнего `product_gate`; billing snapshot тогда
проверяет время уже после ожидания Conversation. Ранее взятые locks повторно не
добавляют обратных edges. Первой prepare перед HTTP Conversation lock не нужен.
Сама final SQL команда также prelock-ит Conversation перед mutation и повторяет
Telegram window/product checks после этого ожидания. Старый внутренний CONTROLLED
kernel сохраняет свой LOCAL/TEST product scope из M2; public path его не использует
для обхода EntitlementService.

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
accepted_generation=expected_generation+1, context=expected_context,
previous_generation=expected_generation, hash32bytes, конечное время, строгий
result равен immutable columns. Generated operation event_type связывает Audit.

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
receipt→Audit FK. Supporting Audit UNIQUE
`(workspace_id,audit_event_id,conversation_object_id,conversation_control_generation,event_type)`;
receipt FK включает тот же conversation/accepted generation/generated event type.
Зафиксированы нужный объект, переход и единственный Audit, не произвольный UUID.

Старые billing/Message discriminators, payload/actor/mandatory FK и Audit pagination
остаются exact. Общий Audit GET читает новые события: необходимы два строгих backend
DTO variants/generated OpenAPI и два frontend parser/type/label variants
«Управление передано владельцу» / «Автоматика разрешена владельцем» с mixed-page
regression. Это только совместимость существующего Audit screen; CONTROL UI не
выдана. Нельзя фильтровать новые события из общего Audit или fallback-ить в billing label.

Предлагаемый exact SQL ABI (new functions в platform, search_path=pg_catalog,pg_temp):

| Signature | Authority / использование |
|---|---|
| `conversation_control_read(uuid) RETURNS jsonb` | EXECUTE runtime; live owner/read, один state snapshot |
| `conversation_control_prepare(uuid,uuid,text,text,bigint,bigint) RETURNS jsonb` | EXECUTE runtime; args conversation, expected_client, operation, key, expected_generation, expected_context; REPLAY либо NEW и все locks, без mutation |
| `conversation_control_execute(uuid,uuid,text,text,bigint,bigint) RETURNS jsonb` | EXECUTE runtime; тот же canonical admission/locks, saved replay или atomic transition; DB повторяет product/CAS |
| `conversation_manual_prelock(uuid,text,text) RETURNS void` | EXECUTE runtime; final owner public manual phase, только locks, не mode mutation/allow flag |
| `conversation_control_fingerprint(uuid,uuid,uuid,uuid,text,bigint,bigint) RETURNS bytea` | Private; ws/actor/conversation/client/op/expected counters, DB codec |
| `conversation_control_locked(uuid,uuid,text,text,bigint,bigint) RETURNS jsonb` | Private; единая authority/key/Business/connection/billing/Conversation lock+replay процедура prepare/execute, не две расходящиеся implementations |
| `conversation_manual_takeover(uuid,uuid) RETURNS void` | Private; ws/conversation, canonical M2 new intent only; HUMAN/gen+1/clear fence, без context bump |
| `conversation_turn_activation_matches(uuid,uuid) RETURNS boolean` | Private; ws/Turn, predicate§12.6 для SQL/tests; не public action capability |

Все mutating/capture functions VOLATILE/READ COMMITTED; общий guard
`turn_require_isolation`, task/XID и owner/worker mutual exclusion сохраняются.
Новые SECURITY DEFINER functions принадлежат asm_migrator; REVOKE PUBLIC, grant
только четыре перечисленные owner capabilities. Private helpers/sequence/
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
монотонную generation. Maintenance сохраняет single-candidate subtransaction,
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

Новый explicit selector C: `--control-schema-upgrade T C`, entrypoint
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
не подменяют настоящий commit/lost-result сценарий.

Inventories статически заданы по фазе: exact names0007 из§10,0008=34,0009=35.
Cross0008→0009 сравнивает **фиксированный T column inventory всех34 таблиц**,
включая весь M2 и Turn/member/job/consumer receipt, не динамическое пересечение
из actual схемы. Alembic8→9 и новые NULL fields/empty control receipt проверяются
отдельно. Default same-schema C fingerprint включает все35 таблиц и все их columns.
Same-count substituted/missing/extra names — отказ. Только clean reverse cycle
требует снова полного34-table fingerprint; новые данные ради него не удаляются.

Цена proposal ограничена одним дополнительным schema phase только в двух existing
state jobs: прежние H proof и T proof не повторяются внутри C phase; T image, уже
полученный для retained phase, повторно не строится при подтверждённых bytes.
Существующие budgets **не растут**: nine jobs, state25min, historical held180s,
prepare/build600s, отдельные command/cleanup bounds; transport5/10/20s, lease30s,
DB2/5s, retries5/15min остаются. Coordinator ограничивает совокупную подготовку
schema images прежними600s, включая reuse verification; nested build не начинает
дополнительные600s. Это design bounded work, **не измеренный PASS по wall time**.
C6 должен подтвердить исполнимость в implementation CI; если retained proof + новый
phase не помещаются, вернуть C0 фактический timing/failure и конкретный scope diff.
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

Current write path — **только этот append**. Ниже finished proposal для C0; после
C1/C2 review C0 отдельно выдаёт exact список. Нельзя считать таблицу разрешением
работать сейчас. Paths сгруппированы только там, где причина одна; glob-allowlist нет.

| Exact future paths | Необходимая дельта / symbols |
|---|---|
| `migrations/versions/0009_conversation_control.py` | Одна новая revision, fields/receipt/Audit/RLS/SQL capabilities§12.6–7 и safe downgrade; copied exact0008 definitions для restore |
| `backend/src/asm/conversations/control.py` | Новый используемый `ControlPermission`, `ControlError`, `OwnerControlService`, fingerprint/prepare/execute/read orchestration; import existing EntitlementService |
| `backend/src/asm/conversations/http_models.py` | Четыре strict DTO§12.2, PositiveVersion и закрытые control error variants |
| `backend/src/asm/conversations/http.py` | `install_control`, три routes, existing AuthBoundary/cookie/CSRF и explicit errors |
| `backend/src/asm/foundation.py` | `create_app` installs routes; `DATABASE_SCHEMA_REVISION=0009`; exact mismatch guard для API/worker/scheduler |
| `backend/src/asm/tenancy/database.py` | Четыре typed owner methods по SQL ABI§12.7, task/XID guard и узкий mapping новых control SQLSTATE; никаких worker/fake-owner extensions |
| `backend/src/asm/messaging/http_service.py` | `OwnerMessagingService.send` вызывает final manual prelock до последнего product_gate; refresh и оба replay probes сохраняются |
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
| `tests/test_m2_2_migrations.py` | Только при необходимости current-head restoration fixture; старый0005→0006/7 cycle и assertions не заменяются новым phase |
| `tests/test_foundation.py`; `backend/src/asm/telegram/provisioning.py`; `tests/test_m2_3_setup.py` | Exact0009 readiness/binding guard; fresh-only provisioning, billing catalog/interval и owner/bot binding policy без изменения |
| `scripts/test_telegram_egress_migration.sh` | C coordinator: frozenH + сохранённый frozenT schema phase + mandatory newC phase в обоих state shards; separate archives/reports/cleanup |
| `scripts/test_telegram_egress.sh` | Explicit CONTROL schema selector; default exactC/0009 и35-table expectation, без ослабления старых gates |
| `scripts/prepare_telegram_egress.py` | Только добавить exact0009 inventory к schema validation; historical `migration_source`/saved-plan gate остаётся0007-only, pins/source/recovery guards неизменны |
| `tests/test_telegram_egress_migration.py` | `run_control_schema_phase`/strict observed9 recovery, phase/source mismatch tests, old historical/saved-plan refusal и reports до teardown |
| `tests/test_telegram_egress_postgres.py` | Exact35 inventory, child-first cleanup, strict current E05; сохраняются6 wire+6 lifecycle, no-resend и DB/S3/HTTP assertions |
| `docs/runbooks/M2_TELEGRAM_LOCAL_TEST.md` | Только ссылка на отдельные frozen0007/TURNS0008/CONTROL0009 LOCAL gates; historical evidence/pins/owner instructions не менять |
| `docs/tasks/M3_CONTRACT.md` | Только согласованные implementation уточнения§12; неизменный TURNS prefix, без SHA-only commits |

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
| `control_product_and_channel_matrix` | Suspended/expired/missing/false/invalid state; stopped adapter/closed window/disabled connection; Takeover/read не вызывают HTTP/billing, Resume policy строго по§12.3; DB clock проходит expiry во время подтверждённого lock wait | A07/границаproduct |
| `control_commit_loss_and_overflow` | Fault до update/между Audit и receipt/на commit; committed ACK loss→same result, rollback→нет всех writes; gen/context BIGINT/sequence exhaustion без wrap, replay всё ещё доступен | A07/A11 |
| `manual_atomic_control_and_replay` | Actual M2 request path: HUMAN/AI, новый/replay/pre0009 receipt; fault после takeover/Message/Audit/Outbox/Job и deferred FK; gen+1/context+1 только новый commit, exact old bytes | A07/contextA03/M2 |
| `manual_refresh_interleaving` | Observe network barrier вне обеих business units; concurrent Resume, rights observation CAS/revoke/expiry/product failure; final accepted order определяет HUMAN, denied/replay не меняют control | A07/M2 |
| `ingress_resume_serialization` ×CONTROLLED/TELEGRAM | Удержать producer после connection+Conversation locks до nextval/commit; наблюдать pg_locks/blocked PID, Resume ждёт. В обратном порядке ingress получает gen/fence после Resume; lower uncommitted ingress commit и rollback | Fence/A11 |
| `unknown_conversation_and_duplicate_first` ×обаproducers | До создания Conversation несколько Inbox; PROCESS blocked connection; Resume404 до существования; позже Resume, post-Resume duplicate обрабатывается первым; earliest/legacy/conflicting origin не получает новую authority | Fence/A11 |
| `generation_group_boundary_and_late_media` | old HUMAN/AI/NULL Turn + new generation input, old out-of-order input, photo READY/FAILED после Resume; no cross-generation membership/deadline reset, immutable captured tuple | A01/A02/fenceA03 |
| `test_consumer_stale_after_control` | Pure consumer snapshot → Takeover/Resume → finalize: same revision STALE, superseded revision SUPERSEDED; old committed OBSERVED/token replay byte-identical, no external call/new backlog job | control-частьA03; не полныйA05 |
| `control_lock_graph_and_maintenance` | Реальные ingest/process/file/manual/owner/consumer/expired job races, PREPARED uploads, open outer savepoint; blockedA не лишает B progress; прежние age boundary/100+ cursor/2s/5s tests сохраняются | A02/A11/reliability |
| `control_capability_and_audit` | Runtime direct SELECT/DML/sequence/private helper rejected; forged GUC/task/XID/actor/ws/key; FK same-client/generation/Audit substitution; mixed old/new Audit API/frontend и exact decimal>2^53 | A07/A11 |
| `control_migration_preservation` | populatedT/M2 seed + clean0008→9→8 definitions/grants; old pending Inbox/Turn/consumer/manual/UNKNOWN/private image, each new-data downgrade blocker; no backfill/jobs/receipt rewrite | A11 |
| `control_schema_commit_loss_normal_docker29` | Два actual state shards§12.8: separate exit86 after commit, fresh reader, incompatible runtime rejected, exact source/image forward/restart, pending/UNKNOWN/privateS3 and original receipts retained | A11/source-schema |
| Existing direct wire/real relay/browser | Same production transport: accepted wire effect + lost response → restart UNKNOWN, count1; HTTP без business transaction;6+6, auth/private signed GET/Secure cookies/browser regression неизменны | Сохранность M2/TURNS, не новый live evidence |

Fixtures используют настоящий command/worker path, deterministic barriers и
наблюдаемые DB locks, не вероятностный sleep/retry. Fault injection остаётся в
TEST, не runtime toggle. Любую адаптацию старого теста объяснять отдельно: новый
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

Один законченный proposal передаётся C1 (API/Audit/product), C2 (DB/locks/receipt/
migration) и C0; C6 адресно проверяет source/schema design при необходимости.
Согласованию подлежат конкретные предложения, не незаполненные алгоритмы:

- **CONTROL-POLICY-01 / OPEN до C1/C0:** принять выбранный existing
  `messaging.manual_send` gate для нового Resume только как CONTROL availability,
  независимость Takeover от billing/channel и отсутствие reply-window/refresh
  gate у Resume. Альтернатива — отдельный product key потребует своего catalog/
  provisioning scope; его здесь не вводим и не разрешаем default-allow.
- **CONTROL-DB-01 / OPEN до C2/C0:** принять захват origin tuple до sequence,
  legacy generation1/NULL provenance без backfill, lock graph и отдельный immutable
  receipt/Audit FK. Необходимость иного lock/ABI/column вернуть явной дельтой этого
  proposal; production DDL до решения не создаётся.
- **CONTROL-COMPAT-01 / OPEN до C0/C6:** принять два отдельных retainedT/newC
  schema phases в существующих state jobs и shared image preparation bound;
  исполнимость wall time подтверждается только actual implementation runner.
- **CONTROL-AUDIT-01 / OPEN до C1/C0:** принять два strict typed Audit variants
  и ровно parser/label frontend delta как обязательную совместимость общего API,
  сохранив единственный MESSAGE_SEND_REQUESTED для atomic manual takeover.

Это design acceptance points, не reopened TURNS findings и не новые задания
пользователю. Native account/provenance остаётся отдельно NOT VERIFIED; никакого
аккаунта, token, TEST продления или VM действия сейчас не требуется. После этих
reviews C0 принимает или корректирует§12 и выдаёт implementation **в этом PR** с
exact paths/0009. До этого запрещены runtime/DDL/tests/OpenAPI/frontend/infra edits.
Следующие C8/приёмка/merge/main CI не подменяются авторским review или документом.
