# M3 — контракт ConversationTurn и границ управления

Дата: 2026-10-10. **Кандидат M3.1-CONTRACT для review; не разрешение на код.**
Поручение C0: [PR #25, post-merge assignment](https://github.com/Elefesys/ai-service-manager/pull/25#issue-5781534926).
Accepted base: `754f1c883e5a94a7fc9e729af2605424f949ba33`;
ветка первого среза: `c3/m3-1-turns`. Единственная дельта фазы CONTRACT — этот файл.
Согласование C2 (DB/locks/migration), C1 (commands/API) и приёмка C0 — **PENDING**.
Собственная проверка C3 их не заменяет. Статусы задач ведёт C0 в
[TASK_REGISTER](../TASK_REGISTER.md), очередь и критерии — в [M3_HANDOFF](M3_HANDOFF.md).
Актуальное post-merge поручение PR25 имеет приоритет над до-выдачным текстом плана.

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
DB trigger, без прямого UPDATE/sequence privileges у runtime. Для порядка используется
logged sequence `platform.turn_ingress_seq`, CACHE 1, NO CYCLE; gaps допустимы.
Sequence задаёт порядок выделения, **не порядок commit**; Resume требует дополнительной
сериализации §8, одного сравнения sequence недостаточно.

Если несколько Inbox ссылаются на один Message namespace, происхождение берётся
из исходного входа, а не из job, первым создавшего Message: среди fresh Inbox
используется минимальный сохранённый ingress sequence, а legacy имеет приоритет.
Наличие pre-cutover CLIENT_MESSAGE Inbox в этом namespace сохраняет legacy eligibility,
даже если он ещё PENDING, а более новый duplicate обработан первым. Это консервативное
правило действует и при конфликте payload; оно не меняет победителя/ошибку M2.
Для этой проверки нужен tenant/connection/chat/message index по Inbox projection.
Новые duplicates не обновляют ingress/deadlines, а сохранённые IGNORED не перечитываются.

Legacy Message остаётся контекстом, но не создаёт membership, Turn или consumer job.
Для fresh Message membership, material context increment и постановка Turn job
происходят в той же транзакции, что Inbox/Message/file plan и завершение PROCESS_INBOX.
Rollback не оставляет частичного Turn. В HUMAN fresh grouping разрешён;
готовность Turn сама по себе никогда не разрешает ответ клиенту.

## 3. Конечная политика группировки v1

Числа ниже — предложение C3 для принятия C2/C1/C0, не ранее принятое требование канона.
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
| `platform.turn_consumer_receipts` | UNIQUE `(workspace_id,turn_id,turn_revision,consumer)`; consumer только `TURN_TEST_V1`; input context version/control generation, snapshot digest, итог OBSERVED/STALE и время; immutable результат без Outbox/Audit/manual receipt |

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
существующий backoff cap 60 с), lock timeout 2 с и statement timeout 5 с.
Нельзя сбрасывать attempt_count или выпускать новую revision ради повторения ошибки.
Scheduler/recovery работают через действующие entrypoints; отмена/падение до commit
откатывают изменения, после commit recovery читает canonical result.
Terminal Turn failure возникает только для ещё актуальной revision; устаревший job
не переводит более новый Turn в FAILED. Ошибки видимы в DB/typed worker result.

Порядок locks для проверки C2:

| Путь | Порядок и ограничения |
|---|---|
| PROCESS_INBOX | Существующие job → Inbox → connection/identity; существующий file plan; затем conversation → Turn/membership и только новые jobs |
| File outcome | Существующие job → FileObject → upload intent; затем conversation → затронутый Turn; это короткий DB hook после material terminal change |
| PROCESS_TURN | Собственный job/claim → conversation → Turn; read-only snapshots FileObject без row lock; не захватывает connection/file/outbox/другие jobs |
| Manual intent / delivery context hook | После существующих authority/domain locks и канонического Message/Outbox изменения — conversation; не меняет control и не перебирает Turn jobs |

Из существующего 0007 inbound hook `last_client_inbound_at` переносится в ту же
конечную conversation-секцию после file plan, сохраняя его формулу и Telegram scope;
provider-only increment заменяется единым §6. Иначе возникает порядок conversation →
существующий FileObject, обратный file completion. Новый Turn worker не расширяет
connection serialization. Новые job FK ссылаются на Turn и не добавляют обратное
ожидание connection lock. Claim/lease повторно проверяются после ожидания locks.
Не делать bulk cancellation jobs под conversation lock; fencing заменяет такой обход.

TEST consumer фиксирует snapshot из канонических refs/versions под claim/conversation,
делает только чистое детерминированное вычисление вне transaction, затем повторно
проверяет claim, Turn revision, context version и generation при сохранении результата.
Ровно один receipt OBSERVED либо STALE на `(Turn,revision,TURN_TEST_V1)` фиксируется
атомарно с terminal job. STALE не запускает автоматическую регенерацию по всему backlog.
При потере ACK читается receipt; повтор чистого вычисления после crash допустим,
два committed результата — нет. Receipt/digest не являются разрешением на action.
Два workers, forged refs/token и истёкший lease не обходят guard; fake Owner не создаётся.

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
down_revision `0007`; C2 подтверждает до DDL. При другом actual head — новое решение,
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
под тем же lock. Тогда вход, принятый до Resume, остаётся по старую сторону fence,
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

## 10. Исполняемые compatibility pins: решение C0 нужно до кода

Следующие места прочитаны на accepted base. Они не изменены этим документом.
Первые три группы **вне** первоначального TURNS allowlist, но блокируют точный upgrade
или штатную регрессию; просится содержательное расширение, а не ослабление guards.

| Точный path / причина | Предлагаемая ограниченная дельта после согласования |
|---|---|
| `backend/src/asm/foundation.py`; `tests/test_foundation.py` | Runtime `DATABASE_SCHEMA_REVISION` и его assertion 0007 → 0008; frozen `tenancy.v1`/SCHEMA_REVISION 0003 не менять; mismatch по-прежнему отказ |
| `backend/src/asm/telegram/provisioning.py`; `tests/test_m2_3_setup.py` | `commit_binding` сейчас принимает ровно 0007; проверить ровно принятый runtime head 0008, поправить fake revision и сохранить wrong-head rejection; binding/product policy без изменений |
| `tests/test_m2_1_postgres.py` | Общий TABLES/cleanup используется M2 descendants; добавить scoped child-first deletion новых FK rows, без CASCADE/disable constraints и без ослабления старых assertions |
| `scripts/prepare_telegram_egress.py`; `tests/test_telegram_egress_migration.py`; `tests/test_telegram_egress_postgres.py` | `migration_database` дважды требует ровно 31 app/platform table; новый набор здесь = 34. Нужен отдельный C0/C6-reviewed revision-qualified exact inventory для 0007 и 0008, проверка неизвестной/missing/extra таблицы и сохранение historical 31-table receipts. Не blind 31→34, не пересчёт старых fingerprints и не обход source/image/recovery guards |

Последняя группа — отдельное необходимое решение C0 по executable LOCAL/TEST harness,
а не поручение C6 и не разрешение обновить VM. Если unit rejection coverage потребует
`tests/test_telegram_egress.py`, добавить именно эти cases отдельным scope решением.
Client/config/source pins, relay profiles и lifecycle logic менять для TURNS не требуется.

Уже разрешённые inventory/cycle files: `tests/test_postgres.py`,
`tests/test_m2_1_schema_postgres.py`, `tests/test_m2_2_migrations.py`,
`tests/test_m2_3_schema_postgres.py`. Последний содержит literal 0007; historical
cycles должны явно выбирать прежнюю revision и не удалять M3 rows ради downgrade.
Новый migration suite проверяет populated downgrade refusal отдельно от чистого cycle.
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

Полный A03 admission, A04–A10 и A12 первым срезом не закрываются. После принятого
CONTRACT/C2 — код TURNS, штатные CI/browser/clean-source gates и независимый scoped C8;
C0 связывает результаты с exact implementation SHA. Mock или этот документ не являются
actual PostgreSQL/S3/Telegram evidence. Full CI принятого base не доказывает реализацию M3.

До перехода к коду нужны: C2 по schema/locks/cutover/0008; C1 по material versions,
manual/control boundary и неизменности API; C0 по числам policy, compatibility scope
§10 и общему контракту. После них C0 отдельно выдаёт TURNS. M3 не объявляется VERIFIED.
VM, binding, ACK, Telegram activation/sends и immutable receipts этой работой не меняются.
