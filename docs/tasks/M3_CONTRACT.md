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
