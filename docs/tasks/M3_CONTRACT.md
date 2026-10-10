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
