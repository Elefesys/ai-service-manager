# M3 — управление разговором и участие владельца

Дата подготовки: 2026-10-09. Ответственный за выдачу и приёмку: C0.
Статусы задач — только [TASK_REGISTER](../TASK_REGISTER.md).
План принят C0 и слит в PR25; runtime/DDL M3 допускаются отдельными выдачами C0.
Он детализирует M3.1/M3.2 из исходного плана, не добавляет новый milestone.

## CURRENT — M3 INTEGRATED / VERIFIED в LOCAL/TEST; PR36 merged / 2026-10-28

**Решение C0:** M3 закрыт в принятом LOCAL/TEST scope. Основание — прежняя
[C8 acceptance A01–A12](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6314784363),
проверенный merge PR36 и новый main CI, C6 host/policy receipt, подтверждённый
пользователем конечный owner smoke и явные границы live-покрытия ниже.
Это не production/pilot readiness и не проверка настоящей модели.

| Binding / evidence | Принятое значение |
|---|---|
| PR36 / actual main | MERGED; **d2f25673f6d2698d3c3dae2d7b2d709e134358f4** |
| Main tree | **141d0a6b2b2be0efe1fcb1c3f851796e9f4cb427**, побайтовое Git-tree equality с проверенным PR36 head **5d828a1ece2840b57fb2fd7d890d3e3fd47da388** |
| Merge parents | **5c074beb4a47521b8c11a820f580673ec1c2cce2**, **5d828a1ece2840b57fb2fd7d890d3e3fd47da388** |
| Post-merge CI | [40681691046, push/main, attempt 1](https://github.com/Elefesys/ai-service-manager/actions/runs/40681691046) — **11/11 SUCCESS** на exact main |
| Foundation | Job122802288218: **804 PG PASS**, **2197 ordinary + 155 subtests PASS**; complete evidence/source gates PASS |
| Browser | Job122793727493: **54 browser/API/PG scenarios**, **398 frontend tests / 14 files PASS** |
| Native / compatibility | Native runner/carrier/fresh0013 catalog/owned cleanup PASS; durable, Docker29 и все6 migration shards PASS |
| Source / artifacts | Exact main найден в checkout logs всех11 jobs;10 ordinary source-clean gates + native cleanup/source gate PASS. Все10 uploads доступны; artifact IDs/digests совпали с логами. Payload архивов заново не аудировался. |

Actual main и PR36 candidate имеют одно дерево; повторять неизменённые тесты либо
весь owner smoke после одного факта merge не требуется. Новый CI не запускался C0:
проверен штатный push/main run. VM этим merge не обновлялась и отдельно C0 не
инспектировалась; operational evidence относится к принятому component profile.

C6-M3-TEST-POLICY-ENABLE-R2, оператор revision4: LIVE PASS на существующей
LOCAL / asm_local и том же private binding; MATERIAL false→true / COMMITTED,
native OFF_UNUSED/P0→ON/P1, receipt ACCEPTED, current ON/P1. Source/images/schema/
binding/identity и оба TEST окна PASS на момент проверки; приложение/транспорт/
исходные private files UNCHANGED, временный контейнер удалён, SSH_EXIT=0.
PC_SESSION_INACTIVE — снимок C6 до позднейшего owner smoke, не текущий статус.
Повторная активация не нужна. Все C1/C2/C3/C5/C6/C8 HOLD.

### M3-OWNER-SMOKE-R1

**Принятый результат — LIVE PASS по сообщениям пользователя:**

| Шаг | Фактически подтверждено |
|---|---|
| Takeover / reload | «Управление у мастера» сохраняется после обновления страницы; подтверждено ранее. |
| Native text | Свежий текст из Telegram-аккаунта мастера появился в «Наблюдениях провайдера»; HUMAN сохранился. |
| Native edit | Новая запись «Наблюдалось изменение в канале» содержит изменённый текст; HUMAN сохранился. |
| Native delete | После удаления того же тестового сообщения для обеих сторон появилось наблюдение удаления; пользователь подтвердил предложенные условия шага. |
| Canonical inbound delete | Новое сообщение тестового клиента сначала появилось в обычной истории; после удаления для обеих сторон и reload показано «Сообщение удалено», HUMAN сохранён. |
| Owner reconciliation | Полный текст контекста сохранён и виден после reload; сохранение оставило управление у мастера. |
| Separate Resume | Пользователь отдельно нажал «Разрешить автоматику» и подтвердил все три условия: режим пережил reload, контекст сохранился, повторных отправок прежних сообщений не наблюдалось. |
| Photo replacement / P-A03-09 | После отдельного шага с предварительным Takeover пользователь заменил вложение фото в том же Telegram-сообщении и подтвердил «Фото заменено, новое изображение недоступно». PASS принятой обработки замены без загрузки нового вложения; полноценная загрузка replacement этим не заявлена. |

Ранее user-observed text/photo/manual Console reply сохраняют приёмку.
Этот finite smoke не доказывает полноту/порядок внешней истории, все гонки,
exactly-once Telegram или использование контекста настоящей LLM. Stale/duplicate/
restart/UNKNOWN guarantees опираются на принятые автоматические тесты;
использование подтверждённого контекста настоящей LLM проверяется в M4. Старые terminal IGNORED
не переигрывались. Private evidence/IDs/content в Git не публикуются.

**Ограничение фото сохранено:** система учитывает замену, закрывает старое фото
как актуальный input, но не скачивает/не открывает/не анализирует новое вложение.
MEDIA_REPLACED_UNAVAILABLE и текстовая пометка — выбранный no-refetch scope M3.
Это корректное поведение ограниченной реализации, не полноценная поддержка
замены изображения для будущей Vision. Нужность загрузки replacement для пилота
оценивается отдельно; этой приёмкой новая реализация не назначается.

**Явный C0 disposition для живого scope A08/P-A03-09/P-05:** наблюдённые native
text/edit/delete, canonical deletion, photo replacement, reconciliation и отдельный
Resume вместе с ранее принятыми CI/PG/browser и C6 host/policy receipt достаточны
для bounded LOCAL/TEST owner smoke. Дополнительный общий collector не требуется
для подтверждения этих пользовательских результатов. Новые роли/схемы/renewal
не нужны: действующие окна подтверждены C6 в своём временном срезе.

Own-bot echo markers/native photo/offline/other-bot/unsupported/delayed варианты
остаются NOT OBSERVED в живом account scope. C0 принимает это как явный предел
данной LOCAL/TEST приёмки, а не LIVE PASS этих вариантов или доказательство
полноты/causality Telegram. Их принятые synthetic/PG guards сохраняются; отдельная
оценка по фактическому использованию в пилоте остаётся. Искусственная задержка,
смена подключения и расширение текущего smoke не назначаются.

### Итог по матрице M3

| Условия | Disposition C0 |
|---|---|
| A01/A02/A04/A05/A06/A07/A09/A10/A11 | Принятые C8 LOCAL/TEST witnesses сохраняются; весь соответствующий текущий main CI PASS. Проверки конкуренции/изоляции/restart/UNKNOWN не подменяются молчанием LLM. |
| A03/A08 / P-A03-09 | Synthetic/PG/browser evidence + описанный finite user-observed text/edit/delete/photo-replacement/reconciliation smoke приняты. Ненаблюдённые account variants и no-refetch граница явно сохранены, не названы live-verified. |
| A12 | Actual main/tree/CI PASS, C6 deployed-host/policy receipt принят, owner smoke PASS, передача в M4 подготовлена. **M3 INTEGRATED / VERIFIED LOCAL/TEST.** |

### Передача в M4 — подготовлена, реализация не начата

Пользовательский результат следующего этапа — AI читает актуальный подтверждённый
контекст и отвечает тестовому клиенту через уже защищённый путь M3. Начальный
срез по Implementation Plan§7 — M4.1 typed Gateway/profile/routing/run contracts
и fake adapters; ведущий C4, отдельная выдача с точным write-set ещё не выдана.
M4 не считается начатым этой приёмкой. Accepted runtime base —
**d2f25673f6d2698d3c3dae2d7b2d709e134358f4**, schema0013; coordination descendant
содержит тот же product source и только актуальные REGISTER/HANDOFF сверх него.

Унаследовать `backend/src/asm/conversations/turns.py` (`parse_snapshot`,
TurnSnapshotV2/V3), `guards.py` (`parse_guarded_snapshot`) и
`native_context.py` (owner context). Обязательны current context/control generation,
existing admission и tenant/Client authorization; model output не авторитетен
для цены/времени/записи. Canonical PostgreSQL state остаётся источником истины.
Saved owner context и Resume — отдельные операции; UNAVAILABLE/PARTIAL/UNKNOWN
не превращаются в доступное изображение, полный контекст либо повторную отправку.

Границы по Spec§7/ADR023–026/180/259–261/267 и Roadmap§8:
query-only AI, выбранные aggregator/direct adapters используют общий контракт;
конкретные API/model IDs/стоимость проверяются при реализации. Начальный путь —
synthetic/fake contracts; live API-доступ и допустимый маршрут решаются в M4.2.
Mutation tools, новая бизнесовая архитектура, перенос среды, production activation
и платные/provider calls этой записью не назначаются.
PC/Happ/SSH остаётся принятым маршрутом разработки; автономность — к пилоту.
Загрузка нового вложения после замены фото не реализована и не включена скрыто в M4.

### C6-M3-TEST-POLICY-ENABLE-R2

**Исполнение завершено:** LIVE PASS, оператор revision 4, результат принят выше.
Ниже сохранён точный scope разрешённой операции; повторное включение не требуется.

**Результат:** включить уже реализованную обработку edit/delete и затем штатный
native context, чтобы продолжить M3 owner smoke без LLM. C0 разрешает подготовку
и выполнение описанной операции сейчас; дополнительное согласование того же
scope после подготовки блока не требуется. При отсутствии доступа C6 предоставляет
владельцу один проверенный блок для существующего SSH-операторского сеанса.

**Точная область:** новая принятая C6 TEST VM и один ранее утверждённый
Telegram binding из его приватного activation intent. Repository Elefesys/ai-service-manager;
accepted main baseline **5c074beb4a47521b8c11a820f580673ec1c2cce2** / tree
**cb47cccdb02ba414c79c65e4fecf81f3fe83cd8b**; PR36 polling candidate
**5d828a1ece2840b57fb2fd7d890d3e3fd47da388** / tree
**141d0a6b2b2be0efe1fcb1c3f851796e9f4cb427**, schema0013.
Фактический source/component profile и images — те же, что приняты в R1 private
intent; эта операция не переключает runtime между main и PR36.
Coordination parent этой выдачи **2015950ddb87e134c35dc81230569324b7ed75ff**,
branch c0/m3-native-context-postmerge. Tracked implementation write-set пуст:
короткий операторский блок и новые private intent/result находятся вне принятого
checkout. Старые receipts/inputs не редактируются. PR36 и отдельный PC helper сохраняются.

**Явное решение C0:** запрет прямого UPDATE в R1 п.2 пересмотрен только для
одной операции ниже. Имеющаяся роль asm_migrator владеет нужной таблицей и имеет
принятую RLS policy; identity trigger и native guard не запрещают false→true.
Поэтому новый API, SQL capability, GRANT или миграция ради этой TEST-активации
не нужны. Это не общее разрешение менять DB state; native policy/Audit/receipt
по-прежнему изменяет исключительно штатный policy command. Spec5.12/5.12.1,
ADR026/180 и остальные гарантии не пересматриваются.

1. До записи сохранить отдельный private intent: точные принятые environment/DB,
   source/schema/binding, ожидаемые MATERIAL=false и native OFF_UNUSED/P0.
   Переиспользовать доказательства R1, проверив их текущую актуальность; полный
   аудит/CI не повторять. Проверить source/images и installed0013 существующим
   механизмом; подключиться реальным LOGIN asm_migrator, session_user=current_user,
   READ COMMITTED, только существующая принятая LOCAL / asm_local
   (ASM_ENVIRONMENT=LOCAL, current_database()='asm_local'), тот же binding из
   приватного activation intent. Перенос или смена среды не требуются.
   Не SET ROLE из admin.
2. Одна короткая транзакция с существующими bounded statement/lock/connect limits.
   Порядок: Workspace SHARE → Business SHARE → ChannelConnection UPDATE →
   TelegramState UPDATE → штатные billing locks через
   platform.messaging_manual_send_allowed(ws). Повторить binding/route/status,
   native policy/epoch и все условия после lock waits. Требуются ACTIVE
   Workspace/Business/connection, точные утверждённые bot/external/Owner,
   оба прежних TEST окна действительны по свежим часам БД и manual-send gate=true.
   Cached Telegram state не выдавать за новый live provider probe.
3. Если MATERIAL уже true — только чтение и ALREADY_ENABLED, без UPDATE и
   приписывания перехода текущей попытке. Для самой записи обязательны
   native OFF_UNUSED/P0 и MATERIAL=false. Единственный DML:
   UPDATE platform.telegram_connection_state SET material_enabled=true
   с параметризованными exact workspace_id+connection_id и material_enabled=false.
   RETURNING обязан дать ровно одну строку; сравнить её с заблокированной исходной
   строкой: единственная семантическая дельта — material_enabled. Native policy/epoch
   и остальные поля остаются прежними. Любое несовпадение/ошибка/timeout до commit —
   rollback, без retry loop. Не отключать RLS/constraints/triggers.
4. Private результат COMMITTED сохранять только после подтверждённого commit.
   Потеря ACK — UNKNOWN, затем отдельное чтение с проверкой того же intent/target;
   material=true подтверждает текущее состояние, а не атомарность private файла
   с БД или авторство перехода. Не повторять UPDATE для восстановления отчёта.
5. После MATERIAL=true выполнить штатные native check/commit/current с точным
   approved component profile и фактической проверкой drain старых несовместимых
   writers. OFF_UNUSED/P0→ON/P1 — существующий replayable policy command.
   Если уже ON, достаточно current; при потерянном native ACK — exact saved
   key/body replay и отдельный current. Сохранить стандартные source/schema/
   authority/product gates и тайм-ауты. Сохранение контекста и Resume остаются
   отдельными действиями владельца, не частью операторского блока.
6. Если native шаг не прошёл после MATERIAL commit, вернуть MATERIAL=true /
   actual native state и конкретную ошибку. Не откатывать MATERIAL автоматически:
   могли появиться новые receipts/effects. После native ON возможное восстановление
   использует PAUSED и отдельное решение, не OFF_UNUSED/удаление evidence.

Рабочий transport, webhook/getUpdates mode, Happ/SSH/PC helper, история/очереди,
контроль разговоров и UNKNOWN не изменяются этой операцией. Нет новых прав,
schema/DDL, billing renewal/initializer, replay старых IGNORED, provider calls,
отправок, merge или общего framework. Если фактические условия требуют выхода
за эту область, остановиться с одним точным blocker; не расширять задачу.

**Возврат C6:** MATERIAL before→after и COMMITTED/ALREADY_ENABLED/UNKNOWN;
native before→after/current и receipt outcome; schema/binding/source match;
актуальность обоих окон; сохранность приложения/транспорта/старых private files.
Наружу только sanitized статусы, не credentials/IDs/private bodies/хэши.
C6 HOLD после результата; whole M3 не закрывать.

PC_SESSION INACTIVE не мешает этой локальной DB-настройке и не означает поломку
маршрута. Перед последующим owner smoke пользователь запускает уже проверенную
PC-сессию прежним способом. Затем свежие native text/edit/delete → обновление Console →
owner context save сохраняет HUMAN → отдельный Resume. События, ранее принятые
как terminal IGNORED, не восстанавливаются этой активацией.

---

## History — продолжение native context: исправления вместо отдельного цикла отчётов / 2026-10-21

Пользователь подтвердил прежний вариант OWNER reconciliation + observation barrier.
Цель: после общения мастера вне Console следующий AI-контекст содержит подтверждённые
договорённости; известный несверенный сигнал останавливает новые AI actions.
Для пилота это полезно при ответах мастера из Telegram; сама возможность отвечать
через Console не требует этого расширения. Упрощённый вариант не принят.
Новые правила пилота, предварительного объяснения функций и пересмотра архитектуры
записаны в AGENTS.md. Пользователь разрешил продолжить реализацию и необходимые проверки.

Последний исполненный кандидат остаётся faceef49dc719d1b3c2b7945116794f6737d7b32;
RUN6: 9 SUCCESS / 2 FAILURE, generic 714 PASS / 88 FAIL, все802 исхода известны.
CI-06/07/11/12 OPEN; PR35 OPEN Draft/BLOCKED; M3 IN_PROGRESS. Main/stock не меняются.
Эта координация не является новым исполненным кандидатом и не закрывает findings.

C6 [6308193288](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6308193288)
и его неизменённый отчёт0973cd2bb5376060bb7ebcdd4bf73a3ae5eabf8a приняты как вход
для исправления CI-12. C0 прочитал выводы/исходные ограничения и проверил однофайловый
коммит; новое независимое воспроизведение четырёх архивов здесь не заявляется.
Нового опубликованного возврата C2 по RECONCILE-R1 на момент выдачи нет.
Готовые материалы этой задачи использовать внутри исправления; отдельный промежуточный
отчёт и новая очередь согласования для них больше не требуются.

Ниже полностью заменены старые report-only выдачи. Их исторические запреты не
блокируют явно разрешённые здесь изменения и LOCAL/TEST проверки. Это не разрешение
новой функции, production/VM/provider действий, платных вызовов или merge.

### Общая исходная точка и проверка

- Repository: Elefesys/ai-service-manager. Отдельные checkout/ветки C2 и C6 от
  **точного C0 coordination commit/tree из новой выдачи в PR34**. Его sole parent:
  0973cd2bb5376060bb7ebcdd4bf73a3ae5eabf8a, tree f94639ee44c5a12ef11857c1e6fc62e081a91b72.
  Runtime bytes равны RUN6; отличаются только правила/координация и отчёт C6.
- Читать AGENTS, этот CURRENT, реестр, применимый контракт§16 и уже принятые отчёты.
  Источники/артефакты привязать к SHA; не начинать повторный аудит всех оригиналов
  и архивов, если их целостность уже подтверждена и не возник новый конкретный риск.
- Допускаются изолированные LOCAL/TEST PostgreSQL/Docker и необходимые targeted units.
  Использовать штатные pinned зависимости, собственные ресурсы и cleanup. До запуска
  фиксировать source/schema/role и цель; сохранить setup/call/teardown, primary error,
  полный перечень исходов и длительности. Не печатать secrets/DSN/private payload.
- Минимальную диагностику выполнять в рамках исправления там, где нужен недостающий
  факт. Не вводить общий observer framework или отдельную серию report/prototype задач.
- Возврат: commit/patch, короткая таблица «группа → причина → изменение → проверка»,
  команды/фактические исходы, остаточные риски и ссылки на полные артефакты. Новый
  многостраничный tracked diagnostic report не требуется. После возврата HOLD для интеграции.
- Полный CI запускает C0 на объединённом проверенном SHA после целевых результатов
  обеих задач. Старые consumed approvals не переиспользовать; текущее поручение
  пользователя разрешает необходимые проверки исправлений, но не слепые rerun.
  Чистый focused subset не заменяет generic802/native112 и оставшиеся обязательные gates.

### C2-M3.1-NATIVE-CONTEXT-GENERIC-PG-REPAIR-R1 — все группы generic, CI-11

Ветка c2/m3-1-native-context-generic-pg-repair-r1. C0 назначает C2 единственным
исполнителем этого согласованного test-fixture среза, включая перечисленные ранее
C1/C3 test paths; параллельных авторов этих файлов не назначать.

Вход: RUN6 core artifact12285065331, native12281891391; точные SHA/digests и все88
диагностик — в историческом RUN6 ниже. Старый GENERIC_PG_DIAG§5–8 содержит карту
девяти групп, write-set и недостающие discriminating controls. RUN6 устранил UNKNOWN
исходы, но не доказывает поведение после исправленного входа или origin12 negative PASS.

Разрешённый write-set — только следующие11 существующих test files и один helper
при доказанной необходимости; все production/DDL/API/workflow/lock paths read-only:

| Файл в tests/ | Изменение и проверяемый результат |
|---|---|
| test_m2_3_db_postgres.py | F3: ingress выбирает корректный codec2 для0012/0013; old writers/replay сохранены. Все56 доходят до целевого поведения;12 negative cases имеют valid-input positive control и intended error/injection origin. |
| test_m1_3_c0_acceptance.py | F1: явное замыкание FK для transactional TRUNCATE;5 conflict cases и восстановление строк/catalog после rollback. Не CASCADE. |
| test_m1_3_postgres.py | F2: точные четыре native Audit columns/generated expressions; прежние defaults/keys/grants остаются. |
| test_postgres.py | F8: точный current inventory45 tables, остальные capability/role checks сохранены. |
| test_m2_3_schema_postgres.py | Current0013 postcondition после старого0007 refusal; исторический0006→0007 цикл сохранён. |
| test_m3_1_migrations.py | F4: actual refusal before DDL и полный неизменённый current snapshot; old H/I proofs сохранены. |
| test_m3_1_guards_migrations.py | F5: current отказ проверяется на current полном состоянии; strict historical G helpers не ослаблять. |
| test_m3_2_escalations_migrations.py | F5/F6: разделить current refusal/security и точную historical E phase; RLS/ACL/clock assertions выполняются. |
| test_m3_1_provenance_migrations.py | F7: явные0012/P и0013/current phases, source-paired readiness, exact downgrade/restore и usage refusals. |
| test_telegram_egress_postgres.py | F9: все8 cases, current45/167 и historical42/132; семь реальных downgrade witnesses должны быть достигнуты. |
| test_m2_3_api_postgres.py | CI-11: установить причину чужого PROCESS_TURN claim в image setup; точечно исправить fixture ownership/order при подтверждении, сохранить5 route authorization checks. |
| generic_pg_schema.py (только если нужен) | Небольшой используемый helper: current snapshot, explicit historical phase и paired readiness. Не общий schema runner. |

Сначала сопоставить все88 actual failures с группами и добавить недостающие факты
в целевых RED→GREEN проверках; не проводить ещё один общий RED ради уже записанных
ошибок. F3 —55 P2001 +1 caught-message assertion, а не56 одинаковых исключений.
Native OFF/current0013 — обычная среда generic. Исторические фазы имеют точный source,
роль/schema и finally-восстановление current состояния; использованный native context
не очищать ради downgrade. Не переносить generic целиком на0012, не ослаблять equality,
tenant/authority/refusal guards, не skip/xfail/удалять IDs и не менять applied migrations.

Проверить все88,12 negative controls, CI-11 с воспроизводимым конкурирующим Job,
и затронутые historical/current restore paths. Затем один полный generic802 на final
candidate, с учётом всех исходов и прежних47 UNKNOWN→PASS. Точный сбор907=802+105
сохранить; новые осмысленные случаи учитывать отдельно. Native112 и полный CI —
интеграционная проверка C0. Если вскроется production-дефект, вернуть его точную
причину/минимальный patch proposal; не скрывать изменением fixture или теста.

### C6-M3.1-NATIVE-CONTEXT-STATE-REPAIR-R1 — CI-12

Ветка c6/m3-1-native-context-state-repair-r1. Цель — конкретное исправление выполнения
state-проверки с подтверждённым результатом; повышение объёма диагностики само по себе
задачу не закрывает. Уже подтверждён расход S+720 и распределённое замедление;
не доказывать это заново. Причина host/Docker и длительность helper probe неизвестны.

Write-set: tests/test_telegram_egress_migration.py, scripts/test_telegram_egress_migration.sh,
scripts/prepare_telegram_egress.py и tests/test_telegram_egress.py — только текущая
обвязка state lane и проверки её изменения. Другие файлы, production/backend/DDL,
frozen source bytes, workflow/pins и общий performance refactor не входят.

Установить конкретную устранимую причину в разрешённой обвязке; использовать
существующий timing path, при необходимости добавить только недостающий замер
оригинальной операции. Не отдельный общий recorder. Разрешены один полный owned
state RED для недостающего факта и проверка final patch в normal/Docker29 lanes;
частные units/controlled regression — по проверяемому риску. Не повторять полный
запуск неизменённого кандидата ради PASS и не подменять original command/result.

Исправление сохраняет source/schema pairing,20 pairings, retained negative tests,
исторические данные/отказы, owner cleanup и точный учёт elapsed. Текущие600/720/1200,
cleanup90 и job25min не увеличивать автоматически. Если исправление внутри этих
границ невозможно или требует нового общего механизма, вернуть **один конкретный
вариант пересмотра**: какой пункт чрезмерен, минимальный diff/новое правило, сохранённые
доказательства и последствия для пилота. C0 примет/отклонит этот вариант как явное
решение; не начинать следующий diagnostic round. Архитектура пересматриваема, но
подмена старого source или объявление непроверенных обязательств PASS недопустимы.

### Следующая точка решения C0

Эта итерация должна дать исправления известных групп либо конкретный технический
предел. Если возвращается только предложение нового большого инструмента/серии
диагностик без ограниченного исправления, остановить выдачу новых циклов и оценить
DEFERRED всей функции по решению пользователя. Одна случайная ошибка CI сама по
себе не доказывает невозможность native context. Согласованный критерий завершения:
целевые гарантии, полный CI кандидата и итоговая приёмка; число отчётов не критерий.

---

## History — RUN6 reviewed; CI-10 confirmed; CI-06/07/11/12 OPEN / 2026-10-20 UTC

[RUN6 / 39457359784](https://github.com/Elefesys/ai-service-manager/actions/runs/39457359784), attempt1, completed
2026-10-20T17:17:04Z: **9SUCCESS, 2FAILURE**. The diagnostic purpose is met:
every actual failed generic phase has a persisted bounded diagnostic. This is
recorder confirmation, not a successful generic or full CI gate.

The [user-confirmed one-use approval6295749140](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6295749140) is
**CONSUMED ONCE**. Exactly one expected-head, force=false FF moved execution
from efc1c8af12dfe8b0c4098c2bf6b6d085e1b35f0b to the candidate below, triggering
its first automatic pull_request/synchronize run. No second run, retry, rerun,
dispatch, cancel or source mutation occurred. PR35 stays OPEN Draft/BLOCKED;
PR34 remains the merged/closed historical coordination hub. User owns merge.

**CI-10 CLOSED with actual RUN6 recorder evidence. CI-06/07/11 remain OPEN.
New CI-12/P2 OPEN: Docker29 state material preparation budget exhaustion.**
C2 and C6 receive only the two disjoint SOURCE + SAVED EVIDENCE report scopes
below. All implementation/repair/runtime scopes remain HOLD. M3 IN_PROGRESS.

### Executed source and evidence binding

| Binding | Exact value |
|---|---|
| PR35 head / execution c0/m3-1-native-context-ci-r1 | faceef49dc719d1b3c2b7945116794f6737d7b32 |
| Candidate tree | 341112cfd977f25441d9f617a2db8580a87dbc42 |
| Candidate sole parent / accepted C6 | ad89819de5778df32146dff245937e9a205e8265 |
| Actual tested merge | 6e12ce98f0436c8c33b8b75c62b52ce911eb0068 |
| Ordered merge parents | [e205e22051bc06295758b504d84699652b176c15,faceef49dc719d1b3c2b7945116794f6737d7b32] |
| Actual merge tree | 341112cfd977f25441d9f617a2db8580a87dbc42, identical to candidate |
| Event / action / run / attempt | pull_request / synchronize / 39457359784 / 1 |
| Event payload SHA256 | 7ba31e8ac7f63335039c434778b56af739b00ac5ab35acbd987c929a48caeeb4 |
| Frozen main / schema | e205e22051bc06295758b504d84699652b176c15 / 0012 |
| Frozen stock | af7482dede085bc033e3fee34f9a2425124351ee |

The event's advisory mergef747ca7570a39c4867e145263c4234b8e9504ee8 is stale.
Actual checkout/identity/ordered parents/tree and source archives establish the
tested merge above. All294 current source bytes/modes reconstruct the exact
candidate tree in all10 downloaded archives; API digests and sizes match.
Nine ordinary explicit clean-source gates and native's structured receipt PASS.
The failed Docker29 state lane's explicit clean gate is SKIPPED after the failure;
its always-run source capture succeeds, with empty worktree status and exact
archive independently verified. That skipped gate is not relabelled PASS.
All11 original attachments and canonical architecture copies still match the
frozen SOURCE_MANIFEST. Prior unavailable-file limitation is resolved.

This subsequent C0 coordination commit changes only HANDOFF/register, with sole
parent the tested candidate. Its exact commit/tree are published in the C0
disposition and bind the next report tasks. It is not the tested PR35 source.
Only preparation c0/m3-1-native-context-ci-r6 advances after terminal completion;
it has no PR or applicable push workflow. Execution/main/stock/old refs freeze.

### Actual foundation outcomes and recorder confirmation

Ordinary units: **2144 passed, 907 deselected, 5 warnings, 130 subtests passed in 421.95s (0:07:01)**. All old IDs/assertions and the23 accepted recorder
regressions remain;907 integration cases are deselected by the ordinary unit
command. Native's separate complete runner386+130subtests also passes.

Generic802: **802 terminal / 802 started; 714PASSED, 88FAILED**;
2406 phase records; 88 saved failure records;
0 missing diagnostics,0 evidence issues,0 remaining UNKNOWN.
Completion receipt: `{"complete":true,"completed":802,"evidence_failed":false,"expected":802,"pytest_exit":1}`.
Ordered generic LF-list SHA256
bde64cc7fbfd35daa02e8141adcaec0723427ed6c2cfeef4b5e15402e8b1d283.
Partition907=generic802+native105 remains exact/disjoint; native has7 additional
source cases. No case is skipped, xfailed, filtered out or silently retried.

Each recorded failure matches an actual failed case phase, index, node-ID hash
and ordered sequence. Closed fields, source-only Python/PLpgSQL locations,
exception/SQLSTATE/constraint allowlists, frame/chain bounds, ASCII/final-LF and
4096-byte journal limits were independently checked. Bounded detail may omit
facts; the diagnostic flags and UNKNOWN values are retained, not inferred away.
No raw exception messages, arbitrary SQL/payloads/locals/DSNs are added to this
disposition. Actual original pytest exit1 and failed execution gates are retained.
issues.jsonl is0bytes; primary1/cleanup0, clean source PASS. RUN5's empty failure
journal/89EVIDENCE_WRITE_FAILED remains historical; it is not relabelled.

| Journal | Phase | Seconds | Exit |
|---|---|---:|---:|
| host | init | 0.030243 | 0 |
| host | config | 0.423105 | 0 |
| host | build | 35.724414 | 0 |
| host | checks | 1917.978009 | 1 |
| host | cleanup | 0.365775 | 0 |
| backend | ruff | 0.068358 | 0 |
| backend | format | 0.124224 | 0 |
| backend | mypy | 11.451830 | 0 |
| backend | unit | 423.883937 | 0 |
| backend | upgrade | 2.274796 | 0 |
| backend | repeat-upgrade | 1.642415 | 0 |
| backend | generic | 1461.724828 | 1 |

Core host elapsed1955.317317877s within2700s. Durable and core have
separate actual runners/projects; core starts only after the entire durable
job passes. No incomplete/unentered phase is counted PASS.
Full tail: downgrade=NOT_RUN, reupgrade=NOT_RUN, contracts=NOT_RUN, wheel-one=NOT_RUN, wheel-two=NOT_RUN, wheel-compare=NOT_RUN, wheel-hash=NOT_RUN, storage-version=NOT_RUN, storage-admin-version=NOT_RUN, services=NOT_RUN, http=NOT_RUN, images=NOT_RUN.

### Generic failure origins: actual bounded records and remaining limits

All88 historical F1–F9 cases still FAIL; all47 previously UNKNOWN cases PASS
(U1=1,U2=38,U3=2,U4=6). All802 setup and teardown phases PASS; calls714PASS/
88FAIL. No new failed ID appears. All88 diagnostics have false chain/detail/
frame/context truncation flags. UNKNOWN metadata is retained as UNKNOWN;
an allowlisted record does not promise every original database diagnostic field.

| Family | Actual failed calls | Recorded origin / source location |
|---|---:|---|
| F1 | 5 | SQLSTATE0A000; test_m1_3_c0_acceptance.py:151 at the preparatory TRUNCATE. Exception labels/schema/table/constraint are UNKNOWN in the bounded record. Exact FK edge and restored full-state proof remain distinct requirements. |
| F2 | 1 | AssertionError at test_m1_3_postgres.py:399, the exact physical-column comparison. This is before later default/generated/grant checks; their result is not inferred. |
| F3 | 56 | 55 ProgrammingError chains reach telegram_validate_v2:8 / telegram_ingest:16 with SQLSTATEP2001 through ingress:194/sql:94. The remaining test_unknown_binding_cross_bot_and_owner_do_not_write fails with AssertionError at test_m2_3_db_postgres.py:405 while comparing the caught error message; it is not the same propagated exception record. |
| F4 | 3 | AssertionError at test_m3_1_migrations.py assert_head:440, called at611 after the direct refusal block. The recorded failure is the current-marker postcondition, not a newly recorded55000 exception. |
| F5 | 6 | AssertionError in test_m3_2_escalations_migrations.py assert_schema:67, through G assert_refusal:124 (4) or E assert_refusal:123 (2). |
| F6 | 1 | The same strict E assert_schema:67 from the exact-profile test at197; later clock/RLS/ACL checks are not proven by this failure. |
| F7 | 7 | Six AssertionError records at strict P assert_schema:73; one RuntimeError from current foundation.check:207, called by the populated0011→0012 cycle at243. Historical positive P readiness is a separate source/schema proof. |
| F8 | 1 | AssertionError at test_postgres.py:108, the exact table inventory comparison; no permissive subset replacement is authorized. |
| F9 | 8 | One strict P assert_schema:73 through material_catalog_profile:1648; seven canonical_fingerprint:801 revision assertions through material_used_refusal:1788. The seven stop before their intended guarded-downgrade witness. |

The only terminal outcome change from RUN5 is CI-11's PROVIDER case:
FAILED→PASSED. Its relevant source is unchanged; **CI-11 remains OPEN**.
RUN5's observed non-null PROCESS_TURN claim during image preparation, before
role mutation/five HTTP authorization assertions, is not repaired or explained
by a later PASS. No product authorization defect or queue/timing cause is proven.

All12 potentially vacuous negative cases retain observed PASS. They still lack
the valid-codec2 positive control and intended rejection/injected-write origin
proof required by the accepted diagnostic report. Ordinary capture also does not
automatically establish every section8 per-phase role/schema/profile, historical
teardown or corrected-input target behavior. C2 must reconcile these remaining
facts before any precise diagnostic/implementation request. No blanket stale-
test classification or generic ten-path/helper repair scope is issued here.

Actual core evidence: cases.jsonl4010rows/873320bytes,
SHA256a698d9a81f8854c1b8a93f3c85fc5bde6fe643248de60eb57210331b10678b8b;
failures.jsonl88records/83941bytes,
SHA25643e07805fe9006945f2de2d32b718264abff6df56883de6d5bec259b6b969b99;
issues.jsonl empty. The generic pytest summary is88failed/714passed in1418.10s;
the enclosing recorded generic phase is1461.724827822s. These different clocks
are not interchangeable. Original exit1 remains the execution failure.

### C0-NC-CI-12/P2 — Docker29 state material preparation exhausted

Job118747603162 / artifact12281649128 fails in frozen P source
e205e22051bc06295758b504d84699652b176c15. At
tests/test_telegram_egress_migration.py:6173, migration_image invokes its
read-only source-byte image probe; scripts/prepare_telegram_egress.py:379–385
clamps each command to the original remaining preparation budget. The last
probe has only0.14476916000012352s and raises TimeoutExpired at stage
image_probe_e205e220_development. P records CONTROL_COMMAND_TIMEOUT;
the candidate wrapper at4218 records MATERIAL_SCHEMA_PHASE_FAILED, exit1.

The original S clock is retained: S+600 retained deadline, S+720 material
preparation deadline with fixed120 extension, S+1200 outer supervisor and
cleanup90. P is issued after709.139693531s, observes709.367695088s charged/
10.632304912s remaining, and never records preparation completion. Its report
has -0.225124641s remaining; coordinator ends after720.507575965s.
This is preparation exhaustion, not expiry of the outer1200s or job25min cap.

| Saved lane | P admission remaining | Preparation complete | Final state |
|---|---:|---|---|
| RUN5 Docker29 | 215.664890098s | yes,207.211756745s left | PASS,20pairings |
| RUN5 normal | 38.206831992s | yes,27.087023418s left | PASS,20pairings |
| RUN6 normal | 36.450824822s | yes,25.589878444s left | PASS,20pairings |
| RUN6 Docker29 | 10.632304912s | no | FAILURE,0pairings |

RUN6 Docker29 C/G/E complete in121.278719755/124.941592976/142.385548998s;
normal C/G/E take116.067823507/118.581811274/137.081499755s. Differences also
exist in T and the expected negative probes. Saved timings establish depleted
shared preparation time; they do not establish a Docker29-specific defect or
the cause of all preceding cost differences. Current migration coordinator,
preparer and ci.yml bytes are unchanged from RUN5; frozen P is unchanged.

Retained C/G/E, expected full-retained timeout/export negatives and historical
volume cleanup PASS. P owned cleanup PASS0.160180745s and outer owned cleanup
PASS0.500766830s; no owned/unconfirmed leftovers. P schema/readiness/recovery/
cutover checks and later retained-C cleanup negatives are **NOT_RUN**. The
explicit clean-source step is SKIPPED after failure; its always-run source
capture succeeds with empty status and exact source archive, independently
verified by C0. Earlier deliberately injected command errors are expected
negative controls, not this unexpected primary failure.

CI-12 stays OPEN. C6 receives only a source/saved-evidence budget reconciliation
report; no cap increase, subtraction/reset of charged work, retry, runtime/code
repair or change to historical source/schema proofs is authorized.

### Other actual jobs

- Native112=7source+105PG, all336 phases and105 guarded resets PASS;
 167functions/45tables/635columns with exact source/OID/body/ACL/roles;
 PostgreSQL18.6/vector0.8.6/btree_gist1.8. All4 event admissions, clean source
 and owned cleanup PASS. Carrier464.050440651s; full receipt567.320395947s
 within1080s. Runner386+130subtests PASS59.95s. Profile
 c045a59f86201a244ed0d43fbe22aa8cd72fddd346d770706c6ab3b92ee9a411;
 verifier527fce5681d5345369cd88b555a302df6d305ef8566cf12a666198eb64a6f4ac.
- Browser398 Vitest/14files and54 Playwright cases PASS; actual source and
 clean-source gate verified through the completed job's decoded log.
- Full normal durable6lifecycles/12top assertions PASS; all host phases,
 primary0/cleanup0, empty irrelevant sinks,1091.519690282s within1500s.
 Docker29 compatibility29.8.2 also passes all6lifecycles/12assertions,
 current0013 image proofs and corrected dual-family routing.
- All4 image/intent shards PASS; source pairing/recovery/rollback and historical
 owned-volume cleanup verified. Normal state PASS with20exact P pairings,
 coordinator1138.917544084s within1200s, all retained cleanup/negative controls.
 Docker29 state FAILURE is separately accounted above; its unentered P tail
 and later C cleanup negatives are NOT_RUN. Every retained historical archive
 reconstructs its exact H/P/T/C/G/E source tree; historical volumes4removed.

| Job | ID | Result |
|---|---:|---|
| docker29-compatibility | 118747602864 | SUCCESS |
| foundation-durable | 118747602880 | SUCCESS |
| connect5-migration (docker29, intent) | 118747602905 | SUCCESS |
| browser | 118747603057 | SUCCESS |
| connect5-migration (normal, image) | 118747603077 | SUCCESS |
| connect5-migration (docker29, image) | 118747603111 | SUCCESS |
| connect5-migration (docker29, state) | 118747603162 | FAILURE |
| native-context-db / native-context-db | 118747603171 | SUCCESS |
| connect5-migration (normal, intent) | 118747603219 | SUCCESS |
| connect5-migration (normal, state) | 118747603489 | SUCCESS |
| foundation | 118756864463 | FAILURE |

| Artifact | ID | Bytes | SHA256 |
|---|---:|---:|---|
| m0-verification-39457359784 | 12285065331 | 2991559 | afef276d10f8e82a43f554d608f051bb5ea8da297e0efca4488f57feded66a0d |
| foundation-durable-39457359784-1 | 12282945577 | 2754147 | 29ae43c9c3ccfd7b28bde71dcdee3376a3cf654ba634397963532ba4983bbc09 |
| connect5-migration-normal-state-39457359784 | 12282461749 | 20180438 | 7599b8eac911f38b1c5b2f54d082e14da3056ea094da898d07bed5182741eb69 |
| connect5-migration-normal-intent-39457359784 | 12281945232 | 5268925 | 5b719600963dcbfe8d307a79edbd28343f2da44e915384ed5cc734c6e99d2079 |
| native-context-db-6e12ce98f0436c8c33b8b75c62b52ce911eb0068-39457359784-1 | 12281891391 | 3446050 | c0caa09a6d200ed6d5a4562f32b3217772995dd625cbde72e4df945d4fab30d9 |
| connect5-migration-docker29-state-39457359784 | 12281649128 | 20132359 | c4d339963a2fd44c24c187cbfacb0d3ad6f4409aa251196ddc3985d04a912205 |
| docker29-compatibility-39457359784 | 12281638392 | 2719599 | b4b250b323a38034645ce28f5134adc886d55ba39fb09d022854ecbb63da594d |
| connect5-migration-normal-image-39457359784 | 12280983277 | 5268943 | 27e1fbdc06ba85c6dedc9db04606294104dedabbfd74151b388deacf44c9ab81 |
| connect5-migration-docker29-image-39457359784 | 12280873270 | 5269871 | 96ecf407e0bdfec5cb61bb2af1ae1dce902782a0e1496d415760763fca582ba6 |
| connect5-migration-docker29-intent-39457359784 | 12280618914 | 5269818 | ca79bb13a9a2f7e6f46573847b60ab81df3a0eb235defb8c3f70111fcecc8cea |

GitHub artifacts contain the exact journals/source archives/receipts under the
unchanged7day retention. C0 downloaded/verified all10. C0 evidence root:
/workspace/scratch/241587c3ddae/c0-native-context-ci-run6-evidence.
Other chats retrieve the identified GitHub artifacts and immutable source;
local C0 paths are provenance, not a shared-filesystem assumption.
Read-only audit commands from the workspace root:
```sh
python c0-native-context-ci-run6-evidence/scripts/verify_archives.py
python c0-native-context-ci-run6-evidence/scripts/verify_native.py
python c0-native-context-ci-run6-evidence/scripts/verify_browser.py
python c0-native-context-ci-run6-evidence/scripts/verify_migrations.py
python c0-native-context-ci-run6-evidence/scripts/verify_secondary.py
python c0-native-context-ci-run6-evidence/scripts/verify_state_budget.py
python c0-native-context-ci-run6-evidence/scripts/verify_foundation.py
python c0-native-context-ci-run6-evidence/scripts/summarize_generic.py
python c0-native-context-ci-run6-evidence/scripts/compare_generic_runs.py
python c0-native-context-ci-run6-evidence/scripts/verify_final.py
```
These parse source/saved evidence; no further PostgreSQL/Docker/Actions execution.

| C0 evidence | SHA256 |
|---|---|
| preflight-source.json | b4be76093a0104bf3c47042986a1076790e602eb46f464ac6b5eda2146bdc50a |
| native-verification.json | 96183a092f6f3a898bb36931a5aff714a6374a7d8c02d52800daddf6e9e4bac1 |
| browser-verification.json | 26eef6d657b511278f462dd79702235c6307b4d56e85cade4beda905fbe5c3e0 |
| migration-image-intent-verification.json | 3dff573c064937c7de81f28b7d8d29a9121b0d7782b6fa54926f883f2049f387 |
| secondary-verification.json | 7bffe48d7f612e3a924ac965f339098d09c185e17934523cb6df96c961101e3d |
| state-budget-failure-proof.json | 83f9cf9448b1267341d8a81618dcfccacb80fb0654ff6257521d0f2a2d88bacf |
| foundation-verification.json | 3fc6b1c0a4192603df00176dab62f13b5119732bc1eb4833c7b8f440839f98a7 |
| generic-diagnostic-summary.json | 6c442975aa049cb4251f9394a35e759cedaef3a8cfda44e79672a540969efae7 |
| generic802-outcomes.json | 63598b07c83f727a93b4ba132254d3b63cc694ca1b970da7d4fd8cb99467bc2c |
| generic-failures-mapped.json | f052cf471ee70f62853be648ef1b2e89a336365b594b4feda8fdc55ea68c6a3d |
| generic-run-comparison.json | bcfdf258ffaefbbb7228cdb5cb5fb3d759da7abaf3c3781dfe4f5d548f207025 |
| final-verification.json | ff076b389960bdc14ce29c9d66b1cb38f9aa6332f58e02fd97c1aebed5322782 |
| evidence-manifest.json | d3669c6bfc315e3c0b665d95d4942720064e945f50eb0a838cbf2f3526de2148 |

### Exact next report assignments — C2 and C6, no implementation grant

These are disjoint report-only scopes. Each executor uses its own branch and
checkout, with the full post-run C0 commit/tree in the disposition as sole base.
That coordination has sole parent faceef49dc719d1b3c2b7945116794f6737d7b32;
its code is the tested candidate, while its updated docs are not a second CI run.
Both tasks return one REVIEW comment in PR34 with exact commit/tree/sole parent,
source and evidence hashes, read-only commands/results, limitations and proposed
next scope, then HOLD. Neither executor starts the other task or other agents.

#### C2 — saved generic evidence reconciliation

Task C2-M3.1-NATIVE-CONTEXT-GENERIC-PG-RECONCILE-R1; owner C2.
Source and saved-data reconciliation before any repair grant.
Repository Elefesys/ai-service-manager. Independent branch/checkout from the exact
post-run C0 coordination commit, sole parent the tested RUN6 candidate. Full
commit/tree are published with the C0 disposition; that exact binding is required
before starting. RUN6 run/attempt/merge and artifact IDs/digests are fixed in the
verified evidence table above. No moving ref or locally invented SHA is a base.

Branch c2/m3-1-native-context-generic-pg-reconcile-r1.
Sole allowed tracked write: docs/tasks/M3_NATIVE_CONTEXT_GENERIC_PG_RECONCILE.md.
One report commit; no existing accepted report, register or HANDOFF edits.
Dependency: C0 accepts complete actual RUN6 diagnostic capture. The C6 budget
report uses a separate branch/path and is not a substitute for generic evidence.

Read AGENTS, IMPL-001, original11 + SOURCE_MANIFEST, applicable architecture/
ADRs/MVP/Roadmap/implementation plan, M3_CONTRACT section16 including DB16.11–16.18
and MATERIAL15.2–15.9/15.18, native source/schema and OFF_UNUSED obligations, current HANDOFF and
TASK_REGISTER, accepted M3_NATIVE_CONTEXT_GENERIC_PG_DIAG.md and the budget report.
Original architecture and accepted reports remain unchanged.

Required reconciliation:

- Fetch immutable Git source and actual RUN6 artifacts independently; verify
  metadata/digests/bytes/modes, tested merge/ordered parents/tree, event, attempt,
  exact generic/native inventories and source/schema boundaries. Local C0 paths
  are provenance, not a shared-environment assumption.
- Account for all802 outcomes and setup/call/teardown sequences, recording every
  failed phase, missing/limited detail, retained primary exit, sink status and
  cleanup. Compare with RUN5's713PASS/89FAIL and the original F1–F9/47UNKNOWN IDs.
- For each observed failure, bind sanitized exception chain, SQLSTATE, named
  source constraint and Python/PLpgSQL locations to exact source. Separate
  OBSERVED, SOURCE, HYPOTHESIS and OPEN_RISK; bounded/truncated frames do not
  establish a missing first statement, state, transaction or role.
- Preserve CI-11's pre-authorization image-preparation identity. A later PASS
  alone does not repair its earlier PROCESS_TURN claim or establish a queue
  root cause. Keep actual role/check reachability distinct from the test name.
- Reconcile each report §8 discriminating fact and the12 potentially vacuous
  negative cases. Mark valid-V2/intended-origin/schema-role-profile/historical-
  teardown evidence as absent where ordinary capture does not supply it.
- Propose the smallest remaining diagnostic and repair scopes with exact files,
  tests/IDs/parameters, expected origin, positive controls and full-suite gates.
  Preserve all historical source/schema proofs and current0013/OFF behavior;
  no generic-on-frozen-P substitution or relaxed equality/security assertion.

No backend/DDL/applied-migration/generic helper/test/CI/clock/cap changes in this
saved-data task. No PG/Docker/service/Actions execution, execution ref movement,
new PR, merge, settings, accounts, VM/provider/live action. RUN6 grants no retry.
Return the bounded report and exact evidence/source proof, then HOLD for C0.

Actual input binding: RUN6 39457359784/attempt1, core artifact12285065331
SHA256afef276d10f8e82a43f554d608f051bb5ea8da297e0efca4488f57feded66a0d;
native artifact12281891391 SHA256c0caa09a6d200ed6d5a4562f32b3217772995dd625cbde72e4df945d4fab30d9.
Actual generic714PASS/88FAIL,2406phases,88bounded records,0sink issues;
all88historical FAIL,47priorUNKNOWN PASS,12negative PASS with intended origin
unproven; CI-11 PROVIDER now PASS with unchanged source. Include F3's55P2001
chains separately from its caught-message AssertionError at405; do not count
all56 as the same recorded exception. All code/DDL/fixture repairs stay HOLD.

#### C6 — saved state-budget reconciliation

Task C6-M3.1-NATIVE-CONTEXT-STATE-BUDGET-DIAG-R1; C0-NC-CI-12/P2.
SOURCE + SAVED ACTUAL EVIDENCE report only. Repository Elefesys/ai-service-manager.
Independent branch c6/m3-1-native-context-state-budget-diag-r1 and checkout from
the exact post-run C0 coordination commit/tree published in the disposition.
Sole allowed tracked write: docs/tasks/M3_NATIVE_CONTEXT_STATE_BUDGET_DIAG.md.
No existing accepted report, task register, HANDOFF, implementation or test edit.

Dependencies: terminal RUN6 review; frozen candidate/actual merge/ordered parents
and all source bytes verified. Read AGENTS, current HANDOFF/register, IMPL-001,
original11 + manifest, applicable architecture/ADR/MVP/Roadmap/implementation
plan, M3_CONTRACT source/schema/cleanup obligations, prior foundation budget
report and C0 state-failure receipts. Neither a green normal state lane nor
RUN5 Docker29 PASS replaces failed RUN6 Docker29 evidence.

Independently retrieve GitHub run39457359784/attempt1 and the exact Docker29 and
normal state artifacts; retain IDs, metadata, digests, source archives, reports,
safe log locations and failure identity. Do not assume the C0 local filesystem
is shared. Verify candidate faceef49dc719d1b3c2b7945116794f6737d7b32,
actual merge6e12ce98f0436c8c33b8b75c62b52ce911eb0068,
tree341112cfd977f25441d9f617a2db8580a87dbc42 and frozen source pairings.
RUN5 comparison run39435478971/attempt1 is historical evidence only.

Required report:

1. Reconstruct the single original monotonic S clock, retained600,
   material-preparation720, fixed120 extension, unchanged +480 supervisor1200,
   cleanup90 and state-job25min. Distinguish preparation admission/commands from
   later material execution and export; supervisor allowance is not extra
   preparation time. Check handoff issuance/consumption, charged work and source
   provenance; no clock reset, subtraction or silent reuse of external resources.
2. Account separately for retained T shell, expected timeout/export negatives,
   C/G/E phases, handoffs, image/archive preparation and cleanup. Compare saved
   normal/Docker29 RUN5/RUN6 durations and actual available timing granularity.
   State which intervals, command costs and host factors are not observed.
3. Bind the observed TimeoutExpired to frozen P image probe at
   tests/test_telegram_egress_migration.py:6173 and its command budget, then the
   candidate MATERIAL_SCHEMA_PHASE_FAILED wrapper. P observed10.632304912s
   remaining, final probe0.144769160s, coordinator720.507575965s. Mark completed
   C/G/E and owned cleanup PASS, P schema/readiness/cutover tail and later C
   cleanup negatives NOT_RUN. Earlier deliberately injected errors are expected
   negative tests, not the unexpected root failure.
4. Explain what the unchanged source and saved evidence establish, and what
   remains HYPOTHESIS/OPEN_RISK. Do not infer a Docker29 defect or a sufficient
   rerun from one passing comparator. No root-cause claim based only on the
   last timed-out command; account for the budget already consumed before it.
5. Propose the smallest possible source-only/local-unit investigation or repair
   boundary for C0 review. If existing evidence is insufficient, specify exactly
   which measurement would distinguish alternatives and why. Preserve frozen
   T/C/G/E/P bytes/assertions, full historical proofs, strict current0013 source
   admission, real commands, original caps and ownership/cleanup. Do not
   preauthorize an optimization, omit mandatory work, widen guards, increase
   caps, grant retries or modify source/schema pairing.

Return one report commit with exact parent/tree/branch, allowed-path diff,
reproducible read-only parsing commands, artifact/source hashes, safe evidence
mapping, limitations and proposed next scope; then HOLD for C0 acceptance.
No pytest/runtime simulation of source, PG/Docker/service/container inspection
or execution, Actions/ref movement/new PR/merge/settings/VM/provider/account/
deployment/live action. Reports may be parsed locally; source may be read and
hashed. No claim of implementation completion or all11 SUCCESS.

Actual input binding: RUN6 Docker29 state artifact12281649128
SHA256c4d339963a2fd44c24c187cbfacb0d3ad6f4409aa251196ddc3985d04a912205;
normal state artifact12282461749
SHA2567599b8eac911f38b1c5b2f54d082e14da3056ea094da898d07bed5182741eb69.
Account explicitly for the skipped clean-source gate versus successful always-
run saved clean/source capture. RUN5 state comparator IDs are12273167228
(Docker29) and12272818378(normal); retrieve and verify their exact metadata,
source, archive digests and clocks independently. No prior PASS repairs RUN6.

### Continuing limits

CI-06 requires complete current0013/OFF generic802 with historical obligations.
CI-07 requires all11 actualSUCCESS at one exact source, both foundation lanes,
full tail, native112/336/105 and catalog/security/cleanup. CI-08/09 prior closures
retain ordinary cleanup/unit confirmation; local-only fault probes remain local.
All prior closures and D1/D2/D3 remain; enforcement UNVERIFIED, IMPL-05 DEFERRED.
Caps remain durable25/foundation45, native20/payload1080, state/browser/compat25,
S600/P720/fixed120/+480/supervisor1200/cleanup90. No additional run/resource
budget follows from this disposition. A08/P01/P05/renewal/collector/account/A12/
M4 and deployment/live work remain separate. User owns merge.

---

## History — CI-10 CLOSED LOCAL; C6 accepted; diagnostic RUN6 prepared / 2026-10-20 UTC

C0 accepts [C6 FAILURE-EVIDENCE-R1 return6294851327](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6294851327)
against [assignment6294026073](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6294026073):
**INTEGRATED / VERIFIED SOURCE + ISOLATED LOCAL UNIT only; COMPLETE/HOLD.**
**C0-NC-CI-10/P2 CLOSED LOCAL.** The actual RUN5 diagnostic loss is historical;
the corrected recorder has no new PostgreSQL/Actions evidence yet. CI-06/07/11
remain OPEN; PR35 remains OPEN Draft/BLOCKED. No generic repair is accepted.

### Exact accepted source and independent review

| Binding | Exact value |
|---|---|
| C6 branch | c6/m3-1-native-context-failure-evidence-r1 |
| Accepted commit | ad89819de5778df32146dff245937e9a205e8265 |
| Accepted tree | c3e3eee324fe6c1f0fb2856be5dbddbe5aa6f4ab |
| Sole parent / assigned base | 49363b1eed1950446fd242fd9ef7ad32ee5eee58 |
| Base tree / sole parent | d59bd2d5ad0d3f4b7925b5568017f9b3a1f69d56 / efc1c8af12dfe8b0c4098c2bf6b6d085e1b35f0b |
| Frozen PR35 execution ref c0/m3-1-native-context-ci-r1 | efc1c8af12dfe8b0c4098c2bf6b6d085e1b35f0b |
| Frozen main / schema | e205e22051bc06295758b504d84699652b176c15 / 0012 |
| Frozen stock | af7482dede085bc033e3fee34f9a2425124351ee |

Exactly two existing 100644 paths change from the assigned base, +273/-3:
scripts/native_context_db_catalog.py +18/-1 and
tests/test_native_context_db_runner.py +255/-2. Independent GitHub tree/commit
readback and local Git objects match all294 bytes/modes; other292 leaves and all
modes are exact. The runner changes only foundation_failure; other67 top-level
definitions and globals are unchanged. Only old fixture foundation_git changes
in the tests; all other88 old definitions, old assertions and parameter decorators
remain exact. The added fixture and four tests expand to23 additional case IDs.

foundation_failure now validates the nonempty list of exact index/revision/sql
records, then extracts the unchanged constraint-name regex from each row's sql.
The producer schema is unchanged. Missing data raises KeyError; malformed or
alternate record shapes refuse with a fixed message. There is no string-list
fallback or substitution of UNKNOWN to hide the producer/consumer defect.
Actual source-defined constraint names survive; a foreign name remains UNKNOWN.

Source review retains exception/descriptor guards, no exception str/repr or raw
SQL/messages/locals/DSNs/payloads, the four-node/eight-frame bounds, PL/pgSQL
whitelist/bounds, ASCII/final-LF/4096-byte records and BaseException propagation.
GenericJournal, FoundationEvidence, generic_integration, foundation_check,
owner admission/cleanup, selectors, clocks/caps, original nonzero exit and strict
failure gates are byte-exact. No production/schema/workflow/CI-input changes.

### C0 independent RED, GREEN, complete units and source pairing

Before altered regression fixtures, the exact pristine base's source_catalog
produced717 index/revision/sql records, equal to RUN5's saved expected catalog
SHA256 e701a2ffe539da25e2624f9ff5c4ec87b4fc06ec8502a518979d63c1aa150bd5.
Its foundation_failure on a safe constructed AssertionError raises exactly
TypeError: sequence item 0: expected str instance, dict found. The corrected
formatter consumes the same catalog and returns sanitized bounded evidence.
This pure probe executes no database, Docker or pytest.

The new23 regression cases were independently run in a separate base worktree
with only the returned test file overlaid; all runtime source stayed pristine.
RED: **20 failed, 3 passed, 363 deselected, 1 warning in 17.32s**; exit1.
GREEN at accepted commit: **23 passed, 363 deselected, 1 warning in 10.18s**; exit0.

Independent complete final checks at the clean accepted source:

| Check | Actual C0 result |
|---|---|
| Complete runner | 386 passed, 2 warnings, 130 subtests passed in 118.01s (0:01:58) |
| Complete ordinary non-integration suite | 2144 passed, 907 deselected, 5 warnings, 130 subtests passed in 340.30s (0:05:40) |
| Ruff / format / compileall / git diff --check | PASS |
| Pure profile -> model -> native_host_source pairing | all4 components;167functions/45tables/635columns PASS |

Own frozen/offline uv.lock virtual environment: Python3.13.12, uv0.10.0, all58
installed distributions match the lock; editable project and imported asm,
provisioning and runner/preparer paths resolve to the independent checkout.
Full execution uses the stock pinned plugins; no extra probe/inventory/clock
plugin, timing adjustment or selection override. Caches/temp/bytecode stay outside
the checkout. All363 old runner and2121 old ordinary IDs/parameters/order plus
130subtests remain;23 additions only. No failed/error/skipped final JUnit case.

C0 independently checked all182 C6 evidence-manifest entries and the294-leaf
source tar, both complete C6 JUnit/command/log sets and the10 saved constructed
journal cases. C6 complete results were386+130/123.92s and2144+130/424.90s.
Its disclosed unpublished first candidate's nested pytest module-cache failure
is retained as development history; final source restores that cache entry via
monkeypatch, and all old/new nested cases pass together in both full C0 suites.

C0 also parsed its own10 constructed journal cases. Successful recording of
failed setup/call/teardown persists one bounded diagnostic per failed phase,
exact case index/hash and ordered sequence, complete=true/evidence_failed=false,
with original nonzero7 retained. The actual nested pytest path gives four cases,
19case records/11phases/3diagnostics,1PASS+3FAIL and original exit1. Six actual
write/fsync fault variants retain evidence_failed=true and failed strict gates;
fsync failure remains failure even when bytes reached the file. A recorded test
failure still fails the execution gate. These are constructed LOCAL units only.

Independent collection preserves generic802 and native112=7source+105PG,
disjointly covering all907 PG IDs; all four carrier modules remain. Ordered
LF-list hashes: generic bde64cc7fbfd35daa02e8141adcaec0723427ed6c2cfeef4b5e15402e8b1d283,
native 7b3ae663595966409f0291fe9836753bf303a37b76c529c36df7dd0957a2cf0d.
No PG fixture executed. Verifier body remains
527fce5681d5345369cd88b555a302df6d305ef8566cf12a666198eb64a6f4ac.
Unchanged inputs retain ci.yml cdb6e92b90c3070ea22812e0edd8df5767bbbea7a67c8304a54d2282ef23c691,
native-context-db.yml ff43d2470b56d26cf9c616cad5bc570e31634a19d97bdec4f28e73a205e049fd,
check_backend.sh 1473e64b8ed0819b046b764f281072583271acd5f7b0929b3f8aa959c5d69330.

### Evidence identity and exact preparation

C0 review root: /workspace/scratch/241587c3ddae/c0-native-failure-evidence-review.
The source/base/regression-red checkouts and evidence/scripts/metadata are
separate. Actual commands are saved with argv/cwd/environment/exit in evidence;
PY=evidence/python-env/bin/python, E=evidence, run from source:
```sh
"$PY" -m pytest -q tests/test_native_context_db_runner.py -k real_catalog --basetemp="$E/green-tmp" --junitxml="$E/regression-green.xml"
"$PY" -m pytest -q --durations=20 tests/test_native_context_db_runner.py --basetemp="$E/runner-tmp" --junitxml="$E/runner.xml"
"$PY" -m pytest -q --durations=20 -m 'not integration' --basetemp="$E/ordinary-tmp" --junitxml="$E/ordinary.xml"
"$PY" -m ruff check scripts/native_context_db_catalog.py tests/test_native_context_db_runner.py
"$PY" -m ruff format --check scripts/native_context_db_catalog.py tests/test_native_context_db_runner.py
"$PY" -m compileall -q scripts/native_context_db_catalog.py tests/test_native_context_db_runner.py
git diff --check HEAD^ HEAD
```
Variables above denote absolute paths recorded by scripts/local_run.py.
verify_source.py, probe_producer.py, verify_environment.py, pairing.py and
verify_results.py supply independent source, saved evidence, RED/GREEN, inventory,
JUnit, actual constructed journals and environment checks. Collection uses
--collect-only and the saved inventory plugin; full execution does not.

| C0 evidence | SHA256 |
|---|---|
| source-and-c6-evidence-proof.json | 2f987c6eb170e2d37c09c90e90398984b34a264b4819a0c53851db6bb71c9bf8 |
| environment-proof.json | 239255b74722ad0fd541c4d46df9942e44d1520eb15efa2facd4492a44b5fc4d |
| producer-red.json | 50649e283f7ee1a02f49beac89af0f9f54a7610bcbdd7641a41a46171d3e3918 |
| producer-green.json | d3ded0d2c172a9e62a5d2f3422141e61471da33ce34f6efc6705070769137cb1 |
| regression-red.xml | d79041ee3eea31f847b9e0b7dd0438fd82cbea57719da0fff4480b77a7dffdfc |
| regression-green.xml | 304ac253c2d752c9b1e5be8fd8a90103dae30bc04b039debebb4024951dcc3d8 |
| runner.xml | 8042f9c9e24e66a3519c8dcef821760adbb0e3918b0aefa7d2da5fc5a6c8ffa0 |
| ordinary.xml | 5130ecf2466a3441c70b1431ddf346de0c0f0f06258d00d5160906e51703796f |
| inventory-proof.json | 0615c5d2411b74b51c192f3db5d3d8ee106faaa56eac72777a89e66f69d18db9 |
| results-proof.json | 6cf8a927d9cd5478d85ad0e0c190a0ca7884e7b9c9d3fe66f470258fb24f3516 |
| pairing-proof.json | 982ad9ca874bcf509ce7e6a71f4a2504ca1739f16a3e0c3fbdc3314f37910fe8 |
| c0-evidence-manifest.json | 0ef49eb82075f577d1ea580c5dbe86beb2fe5d37ae3c503e0288c91a36f53ac7 |

C0 manifest covers114 files: review scripts, retrieved metadata,
receipts/logs/XML/proofs and50 constructed journal files. It excludes environments,
caches, temporary worktrees and later preparation/publication receipts.
C6 manifest182files SHA256544750db2b1f4e85101b4303efe302209367e7c20f40b2c15d96bd2c9be39377.
All11 available original attachments and canonical copies match SOURCE_MANIFEST.
The full contract, accepted diagnostic reports and original architecture remain
unchanged; current implementation coordination is recorded here and in the register.

This C0 preparation has sole parent accepted C6 and changes only HANDOFF/register;
other292 leaves are exact. New preparation branch c0/m3-1-native-context-ci-r6
has no PR or applicable push workflow. Its exact commit/tree and source-pairing
readback are published in the C0 acceptance/proposal. No existing remote ref moves
in preparation. PR35/execution, main, stock and prior preparation refs stay frozen.

### Concrete next proposal — C0-M3.1-NATIVE-CONTEXT-CI-RUN6

**PROPOSED/PREPARED, NOT AUTHORIZED, NOT RUN.** RUN5 one-use approval6292650855
is CONSUMED ONCE. C6's task and this review cover SOURCE + LOCAL units only.
A separate explicit approval of the exact prepared source is required by the
current one-use execution procedure before moving the execution ref.

Purpose: obtain actual complete sanitized failure diagnostics for the unchanged
generic802 and verify the corrected recorder in ordinary CI. RUN5 remains
10SUCCESS/1FAILURE,713PASS/89FAIL,0UNKNOWN,2406phases,0detailed failures and
89EVIDENCE_WRITE_FAILED markers; full post-generic tail NOT_RUN. This source
does not fix those89 cases or CI-11; a green complete gate is not promised.

Proposed action after explicit approval: one expected-head, force=false FF of
c0/m3-1-native-context-ci-r1 from efc1c8af12dfe8b0c4098c2bf6b6d085e1b35f0b to
the exact prepared C0 commit/tree in the proposal, enabling only its first
automatic pull_request/synchronize run,attempt1. Fresh preflight must verify
candidate/sole parent/tree, unchanged main/schema/stock and PR35 Draft/old head,
FF ancestry, no previous candidate run and no active run in the concurrency group;
otherwise stop. Record actual merge SHA, ordered[main,candidate] parents, equal
tree, event/run/attempt/job/artifact identities and all outcomes. Freeze source
during execution. No manual dispatch/rerun/retry/cancel, second ref move, new PR,
main/stock/settings/merge/deploy/VM/account/provider/live action.

All11 jobs and entrypoints remain exact: whole normal durable25min then dependent
foundation45min on fresh resources, complete ordinary units/generic802/full tail;
native112 and other9 jobs unchanged. Maximum serial allocation25+45min excluding
queueing, unchanged native20min/payload1080s, state/browser/compat25min,
S600/P720/fixed120/+480/supervisor1200/cleanup90. No subset/fail-fast/retry,
clock reset, changed resource ownership or native reset in generic execution.

C0 checks each actual failed phase against a persisted bounded record and exact
case identity/sequence, complete outcomes, original pytest result, honest
evidence_failed, primary/cleanup receipts, archive hashes and clean source.
Actual recorder confirmation does not require or imply green generic tests.
CI-06 still requires complete current0013/OFF generic802 with historical
assertions. CI-07 still requires all11 actualSUCCESS, both foundation lanes,
full native112/336/105/catalog167/45/635, full tail and owned cleanup. A failed
durable prerequisite/skipped foundation is failure; missing phases are NOT_RUN.

After evidence exists, C0/C2 reconcile observed failure origins with F1-F9 and
CI-11 before exact repair assignments. The12 potentially vacuous negatives retain
observed PASS until intended-origin controls exist. Ordinary capture alone may
not satisfy every report section8 valid-V2/schema-role-profile/historical-teardown
fact. No blanket stale-test classification or ten-test-path/helper repair grant.
C6 and C1/C2/C3/C5/C8/all implementation scopes HOLD. CI-08/09 closures and
D1/D2/D3/caps retained; enforcement UNVERIFIED, IMPL-05 DEFERRED, M3 IN_PROGRESS.
User owns merge. Later M3/M4/live/account scopes remain separate.

---

## History — RUN5 FAILURE;802 outcomes; CI-10/11 OPEN / 2026-10-20 UTC

[RUN5 / 39435478971](https://github.com/Elefesys/ai-service-manager/actions/runs/39435478971), attempt1, completed
2026-10-20T14:50:37Z: **10SUCCESS, 1FAILURE**. The one-use
[user-confirmed approval6292650855](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6292650855) is **CONSUMED ONCE**.
Exactly one expected-head/force=false FF was performed from the previous
cf9d037dbf605ec01bc81306a546cac54a3f7f91 to the accepted candidate below,
causing its first automatic pull_request/synchronize run. No rerun, retry,
dispatch, cancel or source mutation occurred during execution.

CI-06/07 remain OPEN; PR35 remains OPEN Draft/BLOCKED; M3 IN_PROGRESS.
C6's clock task is COMPLETE. The sole next assignment below is C6 CI-10
SOURCE + ISOLATED LOCAL UNIT correction. C1/C2/C3/C5/C8 and every other
implementation/repair scope remain HOLD. User owns merge.

### Exact executed source and immutable evidence

| Binding | Exact value |
|---|---|
| PR35 head / frozen execution c0/m3-1-native-context-ci-r1 | efc1c8af12dfe8b0c4098c2bf6b6d085e1b35f0b |
| Candidate tree / sole parent | 27bf2b804d6e3cf32cb548fd61ac349209b2b0c1 / 1a3295a43434142a0642f473bf5b12b6f0197b2a |
| Actual tested PR merge | f747ca7570a39c4867e145263c4234b8e9504ee8 |
| Exact ordered merge parents | [e205e22051bc06295758b504d84699652b176c15,efc1c8af12dfe8b0c4098c2bf6b6d085e1b35f0b] |
| Actual merge tree | 27bf2b804d6e3cf32cb548fd61ac349209b2b0c1; identical to candidate |
| Event / action / run / attempt | pull_request / synchronize / 39435478971 / 1 |
| Event payload SHA256 | c549e80a0c6465806f4aa978c48fae78e484fcea4be81fcd86639a50cdf44dff |
| Frozen main / schema | e205e22051bc06295758b504d84699652b176c15 / 0012 |
| Frozen stock | af7482dede085bc033e3fee34f9a2425124351ee |

The webhook's advisory merge9e9e4d617cbbcbab84d8dfbec7698c1a9defb5ef is
explicitly stale; actual checkout/header/ordered parents/tree and all retained
source artifacts establish the tested merge above. All294 current source bytes
and modes reconstruct the exact candidate tree. All10 archive sizes and SHA256
digests match GitHub metadata. Browser has decoded job logs instead of an artifact.

This post-run C0 coordination commit changes only HANDOFF/register and has sole
parent the tested candidate. Its exact final commit/tree are in the C0 disposition
comment; it is not the tested PR35 source. Only the existing preparation ref
c0/m3-1-native-context-ci-r5 advances after terminal completion. It has no PR or
applicable push workflow. Execution/main/stock/old refs remain frozen.

### Foundation: actual result and completeness

Ordinary unit result: **2121 passed, 907 deselected, 4 warnings, 130 subtests passed in 397.72s (0:06:37)**.
The accepted CI-09 unit-clock correction now has actual ordinary CI evidence in
addition to the independent local2121+130 result. Operational clocks, guards,
original assertions and the907 integration deselection remain unchanged.

Generic802: **802 terminal / 802 started; 713PASSED, 89FAILED**.
Actual phase records=2406; sanitized failure records=0
with89 missing failure records and89 EVIDENCE_WRITE_FAILED issues;
remaining UNKNOWN=0. Completion receipt:
`{"complete":true,"completed":802,"evidence_failed":true,"expected":802,"pytest_exit":1}`.
All802 ordered IDs retain LF-list SHA256
bde64cc7fbfd35daa02e8141adcaec0723427ed6c2cfeef4b5e15402e8b1d283.
Partition907=generic802+native105 remains disjoint and complete. Complete
case capture is not complete failure diagnostics or a successful generic gate.

| Journal | Phase | Seconds | Actual exit |
|---|---|---:|---:|
| host | init | 0.029699 | 0 |
| host | config | 0.627995 | 0 |
| host | build | 36.120817 | 0 |
| host | checks | 1870.126560 | 1 |
| host | cleanup | 0.365404 | 0 |
| backend | ruff | 0.069376 | 0 |
| backend | format | 0.105476 | 0 |
| backend | mypy | 10.876300 | 0 |
| backend | unit | 399.380483 | 0 |
| backend | upgrade | 2.143586 | 0 |
| backend | repeat-upgrade | 1.566182 | 0 |
| backend | generic | 1438.637643 | 1 |

Execution receipt={"cleanup_exit":0,"primary_exit":1};
issues.jsonl=7498bytes; clean-source PASS. Executed host/backend
journals are independently checked for sequence, identity, order, finite times
and case identity. Failure frames are unavailable from the empty failure journal.
No missing or unentered phase is counted PASS.
Core and durable have separate actual runners/projects; the core starts only
after the entire durable job succeeds. No prior private evidence or DB resources
are adopted. Core host elapsed1908.009015644s within2700s.

Full tail disposition: downgrade=NOT_RUN, reupgrade=NOT_RUN, contracts=NOT_RUN, wheel-one=NOT_RUN, wheel-two=NOT_RUN, wheel-compare=NOT_RUN, wheel-hash=NOT_RUN, storage-version=NOT_RUN, storage-admin-version=NOT_RUN, services=NOT_RUN, http=NOT_RUN, images=NOT_RUN.

### Generic observations and two new findings

All802 start/setup/call/teardown/end sequences are present in order:4010 records,
2406 phases,802 setup PASS,802 teardown PASS,713 call PASS and89 call FAIL.
No skip/xfail/INCOMPLETE/UNKNOWN. The ordinary pytest summary independently agrees:
89 failed,713 passed,2121 deselected,2 warnings,1398.04s. The whole generic phase,
including partition collection/reporting, took1438.637642695s.

Every old88 failed ID fails again. Their prior taxonomy membership is
F1=5,F2=1,F3=56,F4=3,F5=6,F6=1,F7=7,F8=1,F9=8. This is an ID mapping,
not newly established exception origins. All47 formerly UNKNOWN cases now PASS
individually: U1=1,U2=38,U3=2,U4=6. All12 potentially vacuous negative cases
also have ordinary PASS; their intended rejection/injected-write origin remains
unproven by that outcome alone. The accepted generic report's section8 and its
ten-test-path/helper proposal remain scoped proposals, not implementation grants.

**C0-NC-CI-10/P2 OPEN — actual failure diagnostics are lost.**
failures.jsonl is0bytes despite89 failed call phases. issues.jsonl has89
EVIDENCE_WRITE_FAILED records/7498bytes. generic-result.json correctly reports
complete=true/completed802/pytest_exit1/**evidence_failed=true**. The full
case/phase journal and ordinary ci.log remain. The completeness step correctly
fails; complete802 outcomes and successful cleanup do not hide this defect.
No exception-chain/SQLSTATE/constraint evidence is claimed from the empty journal.

C0 independently reproduces the defect with the exact unmodified
source_catalog -> foundation_failure path and a safe constructed AssertionError,
without PostgreSQL, Docker, pytest or another CI execution. source_catalog emits
717 nonfunction_ddl dictionaries with index/revision/sql. foundation_failure at
scripts/native_context_db_catalog.py:2416 joins those dictionaries as strings,
raising TypeError: `sequence item 0: expected str instance, dict found` before
emitting a diagnostic. The computed actual catalog equals the saved native
catalog. Script SHA256
f20cce5917afe5a9b8a7813a96c9a8e6e1f51ea18c2cf06153c7083324cee87e;
catalog file SHA256
e701a2ffe539da25e2624f9ff5c4ec87b4fc06ec8502a518979d63c1aa150bd5.
The foundation_git fixture at tests/test_native_context_db_runner.py:84 instead
supplies a list of SQL strings and replaces source_catalog, leaving this actual
shape mismatch uncovered. This establishes a formatter defect, not a filesystem
or database write-permission failure. Current generic outcomes remain89FAIL.

**C0-NC-CI-11/P2 OPEN — a newly observed generic case fails before its target.**
tests/test_m2_3_api_postgres.py::test_all_five_routes_require_current_session_and_live_owner[PROVIDER]
passed in RUN3 and fails in RUN5. The ordinary saved traceback locates
tests/test_m2_3_api_postgres.py:336 -> ready at tests/test_m2_2_db_postgres.py:60
-> image at line36. claim_job("file-process") returns a non-null
TurnJobClaim(kind=PROCESS_TURN) whose job_id differs from receipt.job_id.
The image helper's assertion fails during preparation, before role mutation
and the five HTTP authorization assertions. The other four variants pass.

The helper assumes the next globally claimable job is its new image inbox job.
The exact queue/timing/fixture cause and repair are not established by this
single traceback. No production authorization defect is inferred. Do not skip
or weaken the check, add retries/sleeps, force job order, or edit this helper in
the C6 scope. C1/C2/C3 review and any bounded reproduction are later assignments.
ci.log SHA256 b40dbd63f89d31515f46658bc88545e10d441cacba10f67ad313866fbf0786e0;
traceback lines3297-3334. Public summary excludes UUIDs, payloads and locals.

The immediate correction is CI-10's source/local recorder fix. C2 saved-log
reconciliation and generic repairs remain HOLD until C0's exact next issuance.
CI-06/07 and CI-10/11 remain OPEN; RUN5 approval is consumed.

### Retained successful jobs

- Native actual112=7source+105PG, all336 phases PASS,105 guarded resets,
  runner363+130subtests PASS. Exact installed source/OID/body/ACL/roles/catalog
  167functions/45tables/635columns; PostgreSQL18.6/vector0.8.6/btree_gist1.8.
  Four event admissions, source cleanliness and owned cleanup PASS.
  Carrier590.066694848s; complete receipt721.45059466362s within1080s.
  Profile c045a59f86201a244ed0d43fbe22aa8cd72fddd346d770706c6ab3b92ee9a411;
  verifier527fce5681d5345369cd88b555a302df6d305ef8566cf12a666198eb64a6f4ac.
- Browser398 Vitest cases/14files and54 Playwright cases PASS; actual checkout
  and clean-source gate verified in its decoded log and job metadata.
- Whole normal durable:6 lifecycles/12 final assertions PASS; all host phases,
  primary0/cleanup0, empty irrelevant generic/backend sinks,1035.834582333s.
  Docker29 compatibility29.8.2 likewise passes all6 lifecycles/12 final
  assertions, current0013 image proofs and corrected dual-family routing.
- All6 migration shards PASS. Current source and every retained historical
  H/P/T/C/G/E archive reconstruct their exact Git trees. Retry/rollback/source
  pairing and owned cleanup pass. Each state lane retains20 exact P pairings;
  normal coordinator1150.424446428s and Docker29 coordinator819.827167412s,
  both within1200s. Per-phase cleanup PASS, no owned/unconfirmed leftovers,
  negative cleanup controls PASS and4 historical owned volumes removed per lane.

| Job | ID | Result |
|---|---:|---|
| docker29-compatibility | 118671230183 | SUCCESS |
| native-context-db / native-context-db | 118671230600 | SUCCESS |
| connect5-migration (normal, image) | 118671230637 | SUCCESS |
| foundation-durable | 118671230714 | SUCCESS |
| browser | 118671230717 | SUCCESS |
| connect5-migration (docker29, image) | 118671230797 | SUCCESS |
| connect5-migration (docker29, intent) | 118671230854 | SUCCESS |
| connect5-migration (docker29, state) | 118671230917 | SUCCESS |
| connect5-migration (normal, intent) | 118671230970 | SUCCESS |
| connect5-migration (normal, state) | 118671230983 | SUCCESS |
| foundation | 118680201529 | FAILURE |

| Artifact | ID | Bytes | SHA256 |
|---|---:|---:|---|
| m0-verification-39435478971 | 12275172758 | 2968589 | 2cae090f1c706d7f58821b3e0094c0c730d752c11c83e0405f95940cfc961d0f |
| connect5-migration-docker29-image-39435478971 | 12273330038 | 5252804 | 579b5dba8b8cdea12974bd8f11665677383e86fae5eda5bcaa6a5dadbf5d3b2e |
| connect5-migration-docker29-state-39435478971 | 12273167228 | 20164221 | 1c8fe8b6eac3300b677949dc23f204ce0da86af9c8cfc461232fc10284769f79 |
| foundation-durable-39435478971-1 | 12273087354 | 2737200 | 913190858e72f9826a5a06b76d9bd70dcecbc5d09604adf7f600b75afa040746 |
| connect5-migration-normal-state-39435478971 | 12272818378 | 20163387 | 0f0396803baa3eb209781cac1f36abff56b9e382dc1951ce33b145ccdde3f8e2 |
| native-context-db-f747ca7570a39c4867e145263c4234b8e9504ee8-39435478971-1 | 12272721612 | 3427887 | 73e865c4f416a79505d845a4f64ccdca301a74651a47a0497a32e4483f8bc802 |
| connect5-migration-normal-intent-39435478971 | 12272680305 | 5251818 | b7972f04d353d21d752259fcc0441652b88f71a36b8b268cbddf489ac4921de9 |
| connect5-migration-normal-image-39435478971 | 12272395399 | 5251891 | e3c118d411534c506955d26b490879198f8cf3371173ae8da07c00c1cd392e31 |
| connect5-migration-docker29-intent-39435478971 | 12272190286 | 5252732 | a2f788dc32640428d2d7022daed2f05438c50ad9b346c69b7d61e81641d7bc05 |
| docker29-compatibility-39435478971 | 12271717659 | 2702584 | 15f18672a6b8b8268c8b89f224c0f053bc4205915ddc3f1a850073c59c080ec3 |

GitHub artifacts retain the exact journals, source archives and receipts;
the workflow's existing retention is7days. C0 independently downloaded and
verified all10. Local evidence root is
/workspace/scratch/241587c3ddae/c0-native-context-ci-run5-evidence;
another chat must retrieve the GitHub artifacts, not assume a shared checkout.
Read-only audit commands from the workspace root:
```sh
python c0-native-context-ci-run5-evidence/scripts/verify_archives.py
python c0-native-context-ci-run5-evidence/scripts/verify_native.py
python c0-native-context-ci-run5-evidence/scripts/verify_foundation.py
python c0-native-context-ci-run5-evidence/scripts/verify_secondary.py
python c0-native-context-ci-run5-evidence/scripts/summarize_generic.py
python c0-native-context-ci-run5-evidence/scripts/probe_failure_formatter.py
python c0-native-context-ci-run5-evidence/scripts/verify_final.py
```
These parse saved evidence/source or invoke the pure formatter with a constructed
exception; they do not execute PostgreSQL, Docker or another Actions run.
Image/intent evidence and browser logs were also checked
independently. Exact metadata, byte digests and proof files are retained.

| C0 evidence | SHA256 |
|---|---|
| original-attachments-proof.json | 3664802388bcdae7d399dd2b8525de63e358488ec51f69e5244d23dcc78ada37 |
| native-verification.json | c8f99251f82f60cc1026587a6a144f89bf4b50d7f3245c596f90aa3b4155c330 |
| browser-verification.json | 966635bcc6cf9d5c53a736c7f14d8b18b907dd0112e8a75e95f11b9f5bf0a163 |
| secondary-verification.json | 7d99cbd0ac9ad6714b5773b5ad11f0c368a90794f13a9cf85030627738b70683 |
| foundation-verification.json | 3ffcf501ec462d0f515f4aa06e15ea438ac78941d6e0c730fca3df94e84210e3 |
| generic-diagnostic-summary.json | 6999d739946ab2357f6db741a7040e4a15b60189a556a8bcf64bc3bfc6c14073 |
| generic802-outcomes.json | bb11e31712fcdb6a7cd84bde50264a5b030eeb117fa2d7ee3aceef7853350506 |
| generic-failures-mapped.json | 37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570 |
| failure-formatter-source-probe.json | 475537716635cf1e584b312c7af361b91bf7cc7ba2e3f9969d21f164e40608d1 |
| new-generic-failure-source-review.json | 4191f735494dc2181c238744ab7ce6349ebf11f7aec5dc43e60fe6fb874035f3 |
| final-verification.json | cbade9cbb70b214894ff93a1c62adddee8bddee65832c4784db356244b36b912 |
| evidence-manifest.json | 3fb66fb76cf3c0bd0153dc0531140f906b71f92fb3e5c54f36421d14b248e167 |

### Original files: prior limitation resolved

All11 original documents are now available to C0. All17 supplied copies,
including duplicates, match frozen SOURCE_MANIFEST and candidate
docs/architecture byte-for-byte. No upload or replacement is still needed.
The earlier five-available/six-unavailable statement describes the prior turn.
Git retains original baseline source documents under docs/architecture; current
implementation decisions, task contracts, HANDOFF and status live in
docs/decisions, docs/tasks and docs/TASK_REGISTER.md. No baseline file was
overwritten. Last architecture import395b760175871a3d6cde10b8e01e1f9364e3bd57
is the accepted2026-09-15 byte-identical import.

### Exact next assignment — C6-M3.1-NATIVE-CONTEXT-FAILURE-EVIDENCE-R1

**TODO/ASSIGNED: SOURCE + ISOLATED LOCAL UNIT CHECKS only.** Owner C6;
correct only C0-NC-CI-10/P2, return then HOLD. Repository
Elefesys/ai-service-manager. Create separate branch
c6/m3-1-native-context-failure-evidence-r1 from the exact final C0 post-run
commit/tree in the assignment comment. Sole parent of that base is tested
efc1c8af12dfe8b0c4098c2bf6b6d085e1b35f0b; only HANDOFF/register differ.
Use an independent checkout; do not assume a shared disk, environment or cache.

Permitted tracked writes, exactly two paths:

- scripts/native_context_db_catalog.py: foundation_failure's consumption of
  actual source_catalog nonfunction_ddl records; only a directly necessary
  private pure helper may also change. Preserve the producer's established schema.
- tests/test_native_context_db_runner.py: model the real catalog record shape
  and add regression coverage of the actual producer/formatter/journal path.

All other files are read-only: applied migrations/backend/DDL, generic tests
and helpers, architecture/manifest/contracts, prior reports, HANDOFF/register,
workflows/Compose/scripts/CI inputs, pins/locks. The accepted
tests/test_telegram_egress_migration.py clock fix stays exact. CI-11 is outside
this correction. No PostgreSQL/Docker/service/Actions execution, execution-ref
movement, new PR, merge, settings, VM/account/provider/live action is granted.

Read AGENTS, applicable architecture/MVP/Roadmap/implementation plan/ADRs,
native contract/current HANDOFF and accepted diagnostic reports. Retrieve and
verify the RUN5 artifact metadata/digests/source bindings above; C0 local paths
are provenance only. Actual expected-source-catalog.json is in native
artifact12272721612; generic journals/ci.log are in artifact12275172758.

Required correction and proof:

1. Reproduce RED using actual unmodified source_catalog output, not a handwritten
   string list or mock replacing that producer. Capture the deterministic
   TypeError at the pristine base. A safe constructed exception suffices.
2. Consume the real index/revision/sql records and extract only intended
   source-defined constraint names. Do not accept arbitrary alternate shapes
   merely to retain a bad test double, change the producer schema, drop
   constraint evidence or substitute UNKNOWN to hide this defect. Preserve
   honest failure on malformed/missing data.
3. Prove GREEN through formatter and GenericJournal/report with real producer
   data and failed setup/call/teardown examples: exact identity/sequence, one
   persisted bounded failure record per failed phase, original pytest nonzero
   result, complete case/phase records, and evidence_failed=false only when
   recording succeeds. Regression fails against pristine base. Retain actual
   sink-failure tests requiring evidence_failed=true and a failed gate.
4. Preserve privacy/robustness: no exception str/repr, arbitrary SQL/messages/
   locals/DSNs/credentials/payloads, hostile descriptor execution or new
   diagnostic authority. Retain source/catalog whitelists, UNKNOWN for genuinely
   unavailable fields, chain/frame bounds, ASCII/final LF/4096-byte record cap,
   BaseException propagation, private ownership/admission, admitted owned
   cleanup after diagnostic failure, original primary status and strict
   foundation-check. Do not weaken any gate to make the report green.
5. Use a separately verified frozen uv.lock Python3.13/uv environment; report
   actual versions/import paths. Run complete runner units and complete ordinary
   non-integration units. Preserve all363 old runner cases,2121 old ordinary
   cases and130 subtests; inventory additions. Preserve all old IDs/parameters/
   assertions and hostile/fault/cleanup tests. Verify generic802/native112 and
   907 disjoint PG coverage by collection only; all four carrier modules stay.
6. Ruff/format, relevant syntax/diff checks and pure current source pairing for
   all4 components/167functions/45tables/635columns must pass. Unchanged workflow
   inputs keep their existing hashes. No clock/cap, selection, retry, skip/xfail,
   payload, native reset or CI-boundary change is permitted. Constructed probes
   do not supply database/runtime acceptance.

Return full commit/tree/sole parent, exact two-path diff and all other source
bytes/modes proof, RED/GREEN commands/results, full unit/inventory evidence,
privacy/fault/cleanup results, environment/source identity, evidence manifest
hashes, limits and next step. Do not self-promote to INTEGRATED/VERIFIED.
C0 independently reviews source/local evidence before any later diagnostic or
ordinary CI proposal. RUN5 consumed approval grants no retry. C1/C2/C3/C5/C8
and all other scopes remain HOLD; broad IMPL-05 optimization remains DEFERRED.

### Continuing limits

CI-06 requires all current0013/OFF generic802 with every historical obligation.
CI-07 requires all11 SUCCESS at one exact source, both entire foundation lanes,
full tail, native112/336/105 and167/45/635 catalog/security/cleanup evidence.
Ordinary cleanup success reinforces CI-08 CLOSED LOCAL; the journal-loss probe
remains explicitly local. CI-09 local closure is retained with ordinary unit
confirmation. No previous failed/cancelled run is relabelled.
All prior closures and D1/D2/D3 remain; enforcement UNVERIFIED, IMPL-05 DEFERRED.
Caps remain durable25/foundation45, native20/payload1080, state/browser/compat25,
S600/P720/fixed120/+480/supervisor1200/cleanup90. No extra run or resource budget
arises from this disposition. A08/P01/P05/renewal/collector/account/A12/M4 remain
separate later scopes. No merge, settings, VM, deployment or live account action.

---

## History — CI-09 accepted CLOSED LOCAL; diagnostic RUN5 prepared / 2026-10-20 UTC

C0 accepts [C6 UNIT-CLOCK-R1 return6291541015](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6291541015)
as **INTEGRATED / VERIFIED SOURCE + ISOLATED LOCAL UNIT CHECKS only**.
**C0-NC-CI-09/P2 CLOSED LOCAL.** C6 COMPLETE/HOLD; all other implementation
roles HOLD. CI-06/07 remain OPEN, PR35 Draft/BLOCKED, M3 IN_PROGRESS.
The test clock correction has independent complete unit evidence; current CI
runtime acceptance and generic recovery remain outstanding.

### Exact accepted source and C0 preparation

| Binding | Exact value |
|---|---|
| Accepted C6 commit | 1a3295a43434142a0642f473bf5b12b6f0197b2a |
| Accepted tree | 0b86b377f1fae3812cfb2d6f40c8742abdfaab98 |
| Sole parent / assigned C0 base | 86c62f6876b093fc9e0d9306630981e569223810 |
| Base tree / its sole parent | 9c0afcf07603c25b628b7c2373a8deb33962a122 / cf9d037dbf605ec01bc81306a546cac54a3f7f91 |
| C6 branch | c6/m3-1-native-context-unit-clock-r1 |
| Prepared C0 branch | c0/m3-1-native-context-ci-r5; exact final commit/tree in C0 acceptance/proposal comment |
| Prepared C0 commit sole parent | Accepted C6 1a3295a43434142a0642f473bf5b12b6f0197b2a |
| Frozen PR35 / execution branch | cf9d037dbf605ec01bc81306a546cac54a3f7f91 / c0/m3-1-native-context-ci-r1 |
| Frozen main / schema | e205e22051bc06295758b504d84699652b176c15 / 0012 |
| Frozen stock | af7482dede085bc033e3fee34f9a2425124351ee |

C6 changes exactly tests/test_telegram_egress_migration.py, mode100644,
+147/-13,550077bytes, SHA256
34b91631501c84b211916f4179506196764fc97693578725b2559b399e9b7517.
C0 independently verified all294 remote/local leaves and modes, exact sole
parent/tree and clean source;293 other leaves remain byte-exact to the assigned
base. This C0 preparation changes only HANDOFF/register on top of accepted C6,
retains all earlier history, and preserves the other292 leaves/modes. Its exact
final tree, source pairing and remote readback are checked before publication.
The new preparation branch has no PR and no applicable push workflow; PR35's
execution ref is not advanced by this review.

### Correction review and independent evidence

The non-autouse, function-scoped unit_budget_clock fixture replaces only the
test module's time binding with a separate namespace for its explicit callers.
It supplies synthetic now10000.0, restores the binding on exit, and asserts
shared stdlib/pytest/e.time monotonic identity. Eight assigned existing test
definitions change;171 other existing definitions, all module imports/globals/
dispatch, original parameter decorators and every original assert are retained.
The three operational consumers, controllers, private helpers, deadlines/caps
and production/CI files are byte-exact. Operational imports still use real time.

Original now-30, expired now-601/issued now-2/charged599/deadline now-1,
G/E now-430 and exact absolute600 arithmetic remain. The fractional regression
at905.198142485 remains, with the old shared-time monkeypatch replaced by the
local fixture. EXHAUSTED matching is not relaxed. Existing negative cases now
require their own VERSION/PHASE_SOURCE/CANDIDATE_OWNER/CLOCK/TOTAL/CHARGED/FORMAT
origins; expired rejection requires EXHAUSTED and preserves the handoff bytes.
Private-mode, hardlink, consume-once, original charged/deadline and reporting
assertions remain. No waits/prewarm/retries, skips/xfails, selector or ID changes.

C0 repeated the same four original nodes on its own pristine base and corrected
checkout with a separate external module-local clock probe. Shared time is never
patched. At0 the old source fails4/4; at490.452973924 it fails only the original
exhaustion node with exactly started_at=-110.54702607600001 and CLOCK instead of
EXHAUSTED; at10000 the old four all pass. Corrected source passes4/4 at both0
and490.452973924. RED pytest exits1 are expected reproduction, not green runs.
C0 also checked C6's actual per-epoch XML: eight epochs
0/10/100/430/490.452973924/601/602/10000 have old failures4/4/3/3/1/1/0/0,
corrected32/32 PASS. C6 final focused58PASS/604deselected is retained; its disclosed
initial50PASS/8FAIL was a new wrapper-directory mode0755 setup error, corrected
to0700 without weakening the real private guard.

**C0 independently executed the complete ordinary unit selector at exact C6
1a3295a:2121 PASS +130 subtests PASS,907 integration deselected,4 warnings,
368.71s,exit0.** No failures/errors/skips/xfails. Runner363 is included.
Separate clean checkout, own frozen/offline uv.lock environment, Python3.13.12,
uv0.10.0; all58 installed distributions match the lock and editable/source imports
point to this checkout. No clock probe/plugin is used by the complete suite.
The907 deselection is the original non-integration selector, not a removed gate.
Both C0 and C6 complete JUnit case inventories are checked against independent
before/after collections: all2103 old IDs remain in order plus18 explicit
additions; every original parameter and all907 deselected IDs/markers remain.
C6 independently reports2121+130/385.07s on this same commit; C0 verified its XML,
commands/logs, all144 evidence-manifest entries and complete294-file source tar.

The18 additions cover8 host epochs,9 CONTROL/GUARDS/ESCALATION x
valid/invalid-clock/exact-deadline cases, and1 fixture-restoration case.
They reuse the original positive/private/hardlink/consume-once bodies and prove
unchanged600/charged accounting with synthetic5s delay, exact refusal origins
and byte-preserved rejected handoffs. Full IDs are in the accepted C6 return and
C0 results-proof.json. Ruff check, Ruff format check and git diff --check pass.

Generic802 collection SHA256 remains
bde64cc7fbfd35daa02e8141adcaec0723427ed6c2cfeef4b5e15402e8b1d283;
native112=7source+105PG in carrier MODULES order remains
7b3ae663595966409f0291fe9836753bf303a37b76c529c36df7dd0957a2cf0d.
Hash method: UTF-8 node IDs joined by LF with a final LF. This is collection,
not current PostgreSQL execution. Pure constructed native_host_profile -> model
validation -> native_host_source pairing verifies api/console/scheduler/worker,
167functions/45tables/635columns and verifier
527fce5681d5345369cd88b555a302df6d305ef8566cf12a666198eb64a6f4ac.
This is source pairing, not operator approval or installed database evidence.

C0 evidence root: /workspace/scratch/241587c3ddae/c0-native-unit-clock-review.
Source=source, evidence=evidence, scripts=scripts under that root. Python is
evidence/python-env/bin/python; commands execute from source through local_run.py
with caches/bytecode/temp outside source and saved exact argv/cwd/exits:
```sh
python scripts/verify_source.py
python scripts/verify_clock.py
"$PY" -m pytest -q --durations=20 -m 'not integration' --basetemp="$E/unit-tmp" --junitxml="$E/unit.xml"
"$PY" -m pytest -q --collect-only -m 'not integration' -p c0_inventory_plugin --c0-inventory="$E/inventory.json"
"$PY" -m ruff check tests/test_telegram_egress_migration.py
"$PY" -m ruff format --check tests/test_telegram_egress_migration.py
"$PY" "$SCRIPTS/pairing.py"
python scripts/verify_results.py
git diff --check HEAD^ HEAD
```
Baseline collection uses the same collect command in the separate exact86c62f68
worktree and writes baseline-inventory.json. verify_source/verify_clock/results
run from the review root with explicit absolute paths; the above variables denote
the absolute evidence Python/E/scripts paths. No actual Docker/PG/Actions run.

### Evidence identity and available canonical sources

| C0 evidence | SHA256 |
|---|---|
| source-verification.json | 01111296c498222ab246a279ebe2a2fab5ce9265a03238b7b84b8757779da4b3 |
| environment-proof.json | 327562da83a0b4478f7c9fa575dda24049d37a2cb4df9a3dce1c0c2eadae46e7 |
| c0-clock-proof.json | fc37cd295c2c20b6fb4fb9dbfa7bc1398ac9952df6b5d730deda48f5744c768a |
| unit.xml | 87e60e53c764f13919c58c6e739b33dd24d2793da09b4295a0dc995c15726cdb |
| unit.log | 58c73306fce49f9a3fafab364672a4dcf2d61fc36bb5d0ba32b9b017c1f6fdc2 |
| results-proof.json | cc4971cf1e37add5052b71a6a434c68c69f2f4c5cd5820f25b03ee41bb48fb4f |
| pairing-proof.json | a82a01d0e93cccce61edb55914e8ba79d417dd7abc0c25b95ed19af99236205f |
| c0-evidence-manifest.json | 5e4f4118e3898815322d5de346c397a0529c5c8200e736d111612d689fb15279 |

C6 evidence-manifest SHA256 c49d3502e237f646d3ff3770473b1abcd333f1a4ad4db7c53a0b61c75691640c;
final-source.tar10168320bytes SHA256423af3d14678bbd5463d8f0cced1d52c42158f62986ef50b616f4d9462e58fd5.

Only five original attachments were available to C0 this turn: implementation
plan, production runbooks, open questions, ADR and baseline. Their original
bytes match SOURCE_MANIFEST and Git. The six attachments ARCHITECTURE_SPEC,
DEVELOPMENT_ROADMAP, PROJECT_OVERVIEW, CHANGELOG, MVP_SPEC and GLOSSARY failed to
load this turn; C0 does not claim to have verified those six attachment files.
All11 previously accepted repository copies still match the frozen manifest.
Full contract and both accepted diagnostic reports, migrations/schema/history,
backend/CI/locks/Compose and every protected leaf remain exact.

### Concrete next proposal — C0-M3.1-NATIVE-CONTEXT-CI-RUN5

**PROPOSED/PREPARED, NOT AUTHORIZED, NOT RUN.** RUN4 one-use approval6290230660
is CONSUMED. Assignment6290903192 and this C6 return cover source/isolated LOCAL
unit work only. This acceptance does not move an execution ref or grant a retry.

After separate explicit approval, proposed action is exactly one expected-head,
force=false fast-forward of c0/m3-1-native-context-ci-r1 from
cf9d037dbf605ec01bc81306a546cac54a3f7f91 to the exact prepared C0 RUN5 commit/tree
published in the acceptance/proposal. PR35 remains Draft. This allows only the
first automatic pull_request/synchronize run,attempt1. Immediately beforehand,
recheck exact candidate/parent/tree, unchanged main e205e220, PR35 old head and
no active run which the workflow concurrency group would cancel; otherwise STOP.
Record actual merge SHA, exactly ordered parents [main,candidate], equal tree,
event/run/attempt/job/artifact identities and all complete evidence. No source
mutation during execution; no manual dispatch/rerun/retry/cancel, second ref move,
new PR, main/stock/settings change, merge, deployment or external/live action.

Purpose: pass the corrected unit prerequisite and obtain the unmodified full
generic802's failure/phase evidence and terminal outcomes for47 UNKNOWN cases.
The88 earlier generic failures are unfixed; a green complete gate is not promised.
Use all existing entrypoints/assertions/inventories, with no diagnostic selector
or source patch. Existing11 jobs remain: whole normal durable25min, then dependent
foundation45min on fresh resources with complete units/generic802/full tail;
other9 jobs unchanged. At most25+45min serial allocation excluding queue time,
not increased individual caps. Native20min/payload1080s; state/browser/compat25min;
S600/P720/fixed120/+480/supervisor1200/cleanup90 all unchanged. Actions disposable
LOCAL/TEST only. Product/VM/account/provider/Telegram/S3/LLM work is not included.

CI-06 requires complete current0013/OFF generic802 with historical assertions;
CI-07 requires all11 actual SUCCESS at one exact source, both complete foundation
lanes, full native112/336/105/catalog167/45/635, full tail, clean/owned cleanup and
persisted evidence. A failed durable prerequisite/skipped foundation is failure.
C0/C2 must review failure origins/SQLSTATE/constraints and phase data against
the nine-family taxonomy before issuing repair scopes. An ordinary capture may
still not supply every C2 report section8 valid-V2/intended-origin/schema-role-
profile/historical-teardown fact. The12 potentially vacuous negatives retain
their observed result until intended-origin controls exist; no blanket stale-test
classification and no C2 generic ten-path/helper repair assignment.

RUN4 remains10SUCCESS/1FAILURE, generic802/full tail NOT_RUN; RUN3 remains latest
generic evidence755terminal=667PASS+88FAIL,47UNKNOWN. CI-08 CLOSED LOCAL with
ordinary RUN4 actual cleanup additionally PASS; journal-loss probe remains local.
CI-09's local closure does not relabel RUN4. All prior closures/D1/D2/D3 retained,
enforcement UNVERIFIED, IMPL-05 DEFERRED. A08/P01/P05/renewal/collector/account/A12/
M4 remain later scopes. User owns merge; all implementation roles HOLD.

---

## History — RUN4 FAILED before generic PG; CI-09 unit clock OPEN / 2026-10-20 UTC

**C0-M3.1-NATIVE-CONTEXT-CI-RUN4 completed: 10 SUCCESS / 1 FAILURE.**
[Run39418189410 / attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/39418189410)
ran from11:53:24 to12:19:24 UTC. [One-use user approval6290230660](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6290230660)
is CONSUMED. C0 made exactly one expected-head/force=false fast-forward of the
existing PR35 execution ref; no rerun, dispatch, retry, cancel or in-run source
patch occurred. PR35 remains Draft/BLOCKED. User owns merge; M3 IN_PROGRESS.

### Exact source and event

| Binding | Exact value |
|---|---|
| PR35 head / execution branch | cf9d037dbf605ec01bc81306a546cac54a3f7f91 / c0/m3-1-native-context-ci-r1 |
| Candidate / actual tested tree | 9dc0f1e70a1b6a29ce9667ebae662a58ad07e11b |
| Actual tested merge | 9e9e4d617cbbcbab84d8dfbec7698c1a9defb5ef |
| Exactly ordered merge parents | e205e22051bc06295758b504d84699652b176c15, cf9d037dbf605ec01bc81306a546cac54a3f7f91 |
| Candidate ordered parents | cbbfce1fb492b164220d5d9d064037216e28e0e1, 2280b694915bf7a50cbeb3e9eb12603dd7c52c68 |
| Event / action / ref | pull_request / synchronize / refs/pull/35/merge |
| Event payload SHA256 | 44bf7344478a58fec5285a8df8a33813b3873d60ab9d181a0a182ba511227cb2 |
| Frozen main / stock | e205e22051bc06295758b504d84699652b176c15 / af7482dede085bc033e3fee34f9a2425124351ee |

C0 re-read actual Git headers, job/run/artifact metadata and PR/ref state.
All10 artifact ZIP digests/sizes match GitHub; every current source archive
reconstructs exactly the294-leaf candidate tree, including executable modes.
Every supplied tested-commit/status receipt matches the actual merge/clean tree;
native has its own full source/clean receipts. The webhook advisory merge
b6cf7fb... was correctly recorded STALE; actual checkout/ordered parents are
authoritative. No main/stock/settings change. This post-run C0 documentation
commit changes HANDOFF/register only on c0/m3-1-native-context-ci-r4 and is not
the tested PR35 candidate or authorization to move that execution ref.

### Actual jobs

| Job / ID | Actual result | Job seconds |
|---|---|---:|
| docker29-compatibility / 118612251410 | SUCCESS | 1015 |
| browser / 118612251722 | SUCCESS | 608 |
| connect5-migration (normal, intent) / 118612251844 | SUCCESS | 251 |
| foundation-durable / 118612251857 | SUCCESS | 1072 |
| connect5-migration (normal, image) / 118612251878 | SUCCESS | 275 |
| connect5-migration (docker29, state) / 118612251889 | SUCCESS | 1150 |
| native-context-db / native-context-db / 118612251908 | SUCCESS | 740 |
| connect5-migration (docker29, image) / 118612251922 | SUCCESS | 247 |
| connect5-migration (normal, state) / 118612252002 | SUCCESS | 1182 |
| connect5-migration (docker29, intent) / 118612252129 | SUCCESS | 249 |
| foundation / 118619511159 | FAILURE | 480 |

### Foundation failure and retained evidence

Foundation-durable completed its complete six-lifecycle normal lane and12 final
assertions at current0013. Its host journal has all10 start/end records for
init/config/build/normal-durable/cleanup; primary0/cleanup0, no signal or evidence
issue. Durable command1028.020648823s; whole journal1064.455827302s, within25min.
Its294-entry manifest, image proofs for api/worker/scheduler/fixture and all3 CI
input hashes match the actual source. Foundation starts only after this job
succeeds and uses a distinct fresh project/directory.

Foundation host journal is complete for the **executed prefix**:
init/config/build SUCCESS; checks exit1; cleanup exit0. Backend journal:
ruff/format/mypy SUCCESS; unit exit1. All10 host and8 backend records have exact
sequence, finite monotonic elapsed values, valid bounded ASCII lines and no
signal. execution.json is **primary_exit=1, cleanup_exit=0**; issues.jsonl is empty.
Actual owned Docker containers/network are removed in the job log. Host cleanup
takes0.366832348s; full host prefix474.105105136s. This is ordinary failure-path
cleanup evidence; it does not repeat the local post-admission journal-loss probe.

**Unit: 2102 PASSED, 1 FAILED, 130 subtests PASSED, 907 integration DESELECTED,
406.85s.** The907 deselection is the intended non-integration unit selector, not
a removal from the complete gate. Sole failed node:
`tests/test_telegram_egress_migration.py::test_control_budget_exhaustion_and_file_guards`.
No integration upgrade/repeat-upgrade/generic phase was entered.
All generic cases/failures/partition/result sinks remain empty: **generic802
NOT_RUN, zero new terminal outcomes**. Downgrade/reupgrade/contracts/wheels and
host service/HTTP/image tail are NOT_RUN. Clean-source and source/artifact upload
steps succeeded; the full execution/evidence gate correctly FAILED. Empty
unentered generic files are not lost/truncated reports or a successful generic run.

RUN3 remains the latest ordinary generic evidence:755 terminal =667PASS+88FAIL,
47UNKNOWN. RUN4 does not recover those47 outcomes or diagnose the88 failures.
CI-06 and CI-07 stay OPEN. The nine-family C2 taxonomy and its section8 missing
valid-V2/target-origin/schema-role/profile/historical-teardown facts remain;
no generic repair scope is issued.

### CI-09/P2 (C0-NC-CI-09) — unit fixture assumes a sufficiently old monotonic epoch

The exact source at lines9938–9953 constructs an expired handoff using
`now=time.monotonic(); started_at=now-601; issued_at=now-2; charged_seconds=599;
deadline=now-1`, then requires an EXHAUSTED error. The saved failure reports
**started_at=-110.54702607600001** and **CONTROL_BUDGET_CLOCK** at the positive
finite-clock guard (line2480), before the intended exhaustion check (line2488).
Thus the fixture's sampled now was about490.452973924s. Splitting onto a fresh
runner exposes this pre-existing dependence on host monotonic time. A unit
fixture defect is established; no production deadline/clock defect is inferred.

C0 independently AST-loaded the exact unchanged consumers and private-file
helpers, using real owned temporary files and a constructed module-local clock.
At490.452973924 the same negative start and CLOCK rejection reproduce; at602
and10000 the exact expired fixture reaches CONTROL_BUDGET_EXHAUSTED.
Boundary601 gives start0 and CLOCK. Additional constructed source probes show
the related valid control fixture's now-30 fails at10, and valid G/E fixtures'
now-430 fail at100/430 but reach acceptance at490/10000. These are separately
labelled local source probes, not extra CI runs or observed RUN4 failures.
The G/E cases passed in RUN4; no observed result is relabelled.
Source file SHA256:5efe2979b2a20fe8daabc795aad984bdbb5bf760b1f242621c7e532f961365fd.
C0 probe JSON SHA256:afda6373ab7bd8dd918efd66e6f80ede8edcb3ef0903fa6b9f9b084afc61f175.

### Successful retained gates

- Native actual112 cases =7source+105PG; all336 setup/call/teardown PASS,
  105 guarded resets, no missing/skip/xfail. Runner363+130subtests PASS.
  Installed source/OID/body/ACL/roles/catalog equals167functions/45tables/635columns,
  PostgreSQL18.6/vector0.8.6/btree_gist1.8; runtime/migrator privilege constraints
  hold. Full profile c045a59f86201a244ed0d43fbe22aa8cd72fddd346d770706c6ab3b92ee9a411,
  verifier527fce5681d5345369cd88b555a302df6d305ef8566cf12a666198eb64a6f4ac.
  Four event admissions, clean-source and owned cleanup PASS. Carrier603.718728051s,
  job receipt732.035454988s; full ordered generic802 inventory still equals RUN3
  and partition907=802+105 remains disjoint. Collection is not generic execution.
- Browser398 Vitest cases/14files and54 Playwright cases PASS, clean-source PASS.
- Docker29 compatibility: engine29.8.2; all six durable lifecycles/current0013
  image proofs,12 final assertions, corrected dual-stack mapping and old strict
  mapping rejection PASS.
- All six migration shards PASS. H/P source archives reconstruct exact frozen
  Git trees; completed retry/rollback/receipt assertions and owned cleanup pass.
  Both state lanes additionally preserve T/C/G/E/frozen-main-P source archives
  and actual matching historical schema phases. C0 reconstructed every retained
  archive tree against Git;20 P source/schema pairings per state lane pass,
  actual phase cleanup PASS/no owned remaining, negative cleanup controls PASS.
  State coordinator elapsed925.921076027s Docker29 and954.838881408s normal,
  within unchanged1200s supervisor; S600/P720/fixed120/+480/cleanup90 unchanged.
  Historical state success is not evidence for unentered current generic802.

### C0 evidence receipts

| Artifact ID / name suffix | ZIP bytes | SHA256 |
|---|---:|---|
| 12264135080 / m0-verification | 2672604 | 0df4ac2103f8e2027804087f7c192e119e551c460a29de9559981c2c0ccadcda |
| 12263612535 / docker29-compatibility | 2689057 | a9a08e87e6eb513a330db037c49052d58717d54420e22725b896bca8d2a06ce1 |
| 12263578143 / foundation-durable-1 | 2723824 | a7928445846ce296fb9baf3658f2793001574fc27095ead56dfae9bd5ae7f894 |
| 12263365909 / connect5-migration-normal-image | 5238458 | 0c174b223c0283d3fe0366b469c55a3fa673fcf684ba1cff7ad1333bf8eb1356 |
| 12263345882 / connect5-migration-docker29-intent | 5239327 | ec16e3568ef8e493fa795b42bf45fe282268f5925a09457b52ac47f6601e86c8 |
| 12263024125 / connect5-migration-docker29-state | 20151042 | 2acbe89b4f433a9170d17d4f5ce054d2b93c930d06f6f9a529514d811953c59a |
| 12262741458 / connect5-migration-normal-intent | 5238380 | 73261d2524e23ea787f13bfab8eb8638b194bf7398522cea28c68613e4b28cfb |
| 12262518614 / connect5-migration-normal-state | 20150076 | ace2d812e6acbe5cae11965467600d9790ff743bd614d594377e91e08505bebe |
| 12262367812 / native-context-db-1 | 3413917 | 835e2bb913d17d68a6537b1859b3d425d508b9617fadacd4ccc850d77e8e998f |
| 12262164266 / connect5-migration-docker29-image | 5239380 | c60e0f7b2054a25736f466e8526fd8b251bd2dd54d80c1b18eb3a1b665b299c3 |

Foundation ci.log SHA256:
`1e6dd27f871d364f7f44936f5a5860f3d83ac79fe89f323bfd77676086609cd0` (61149bytes).
Decoded saved foundation job log (one final LF added) SHA256:
`84127e325ce59cf45ed218a37b39037725ea340b892ae7d91a1685fe799afe7d`.
Native independent saved-data receipt SHA256:
`1f0a75dc7c980860ed7c2f05f84415feef2569f091c514e0d6487a20a53f8a05`.
Secondary artifact/source/phase receipt SHA256:
`bff399e5dfdd23cdd99866c07702a4008261ac739e551adc5e5a4a93a226cd61`.
These are checked actual RUN4 artifacts plus explicitly separated constructed
local probes; no additional runtime, provider, DB or account execution.

### C6-M3.1-NATIVE-CONTEXT-UNIT-CLOCK-R1 — sole new assignment

Owner C6. Dependency CI-09/RUN4 evidence above. Repository
Elefesys/ai-service-manager; branch `c6/m3-1-native-context-unit-clock-r1`.
Start in a separate clean checkout from the **exact C0 documentation commit/tree
published in the accompanying C0 task comment**; its sole parent is the frozen
PR35 candidatecf9d037dbf605ec01bc81306a546cac54a3f7f91 and its other292 leaves match.
Read AGENTS, current HANDOFF/register, canonical Spec/ADR/MVP/Roadmap/Plan,
M3_CONTRACT§16–16.20 and both accepted diagnostic reports. Verify all originals,
exact source pairing and branch/base before editing; no shared-disk assumption.

**Allowed tracked write-set: only `tests/test_telegram_egress_migration.py`, only
the unit clock-fixture/helper and immediately related unit tests.**
Relevant boundaries: control_budget_file; test_control_remaining_budget_is_absolute_private_and_consumed_once;
test_control_budget_wrong_phase_source_clock_or_owner_refuses;
test_control_budget_exhaustion_and_file_guards; control_budget_file callers
test_control_rejected_handoff_report_never_claims_unvalidated_budget and
test_control_initial_failure_retains_source_budget_and_primary and
test_control_prepare_failure_keeps_consumed_budget_before_any_runtime;
test_guards_budget_is_known_c_g_pair_and_same_absolute600;
test_escalation_budget_is_known_c_g_pair_and_same_absolute600.
Preserve the existing905.198142485 fractional-arithmetic control in the initial
failure test. Existing helper callers may receive a narrow scoped fixture dependency. Add only
focused unit regression cases needed to prove low-epoch independence and intended
guard origins. Do not refactor unrelated tests or change existing parameter IDs.

Make synthetic unit timestamps internally consistent and independent of host
uptime. Keep the real consume_control_budget/consume_guards_budget/
consume_escalation_budget definitions, source/schema controllers, subprocess
supervision and every real monotonic/wall deadline byte-for-byte unchanged.
No autouse/global shared-time monkeypatch; no time.sleep/prewarm/old durable
prelude to wait for uptime; no retries, skip/xfail/filter/selector change or
weaker expected-error match. Preserve expired vs invalid-clock, private-mode,
single-link, consume-once, exact600/charged/deadline arithmetic and all negatives'
intended origins. Positive controls must reach the accepted path; expired cases
must reach EXHAUSTED before consumption and retain the handoff.

Validation is **source + isolated LOCAL unit checks only**, no Docker/PG/Actions:
reproduce the old exact failure at a constructed490.452973924 (and low/boundary
epochs), then the same original node/parameters GREEN with narrow unit-fixture
changes. Include explicit invalid-clock and valid-budget controls, private-mode/
hardlink/consume-once cases, low-epoch control/G/E constructed data, and check
the fake clock does not leak into other tests or operational consumers.
Run the entire non-integration suite from locked Python3.13/uv.lock with
(2103 existing cases + explicitly inventoried additions), all130subtests, no
missing old IDs/skips/xfails/errors; runner363 remains included. Run relevant
lint/format and clean/diff checks. Preserve complete generic802/native112
inventories, all assertions, original11/contract/accepted reports, migrations,
backend, workflow/scripts/Compose/pins/hash bindings and historical source bytes.

Return exact commit/tree/parent, changed function/fixture boundaries, RED/GREEN
commands/results and hashes, preserved old inventories, actual additional IDs,
scope proof that all operational definitions/constants are unchanged, and
limitations. Then C6 HOLD for C0 review. C1/C2/C3/C5/C8 and all other work HOLD.
No PR35/stock/main/ref/settings/PR creation/merge/deploy/live/VM/provider/account
action or workflow dispatch/rerun is granted. A later full ordinary diagnostic
CI needs separately reviewed exact source and one-use C0 approval; RUN4 approval
cannot be reused. C2's ten-test-path+helper generic repair stays unassigned.

CI-08 remains CLOSED LOCAL with ordinary actual cleanup now additionally observed;
its post-admission loss control is still explicitly local. CI-09 OPEN, CI-06/07
OPEN, whole native integration BLOCKED. Prior closures/D1/D2/D3 retained.
Administrative branch enforcement UNVERIFIED; IMPL-05 DEFERRED.
A08/P01/P05/renewal/collector/account/A12/M4 remain later.

---


## History — C6 foundation CI-R4 accepted; CI-08 CLOSED LOCAL; diagnostic RUN4 proposed / 2026-10-20 UTC

C0 accepts [C6 CI-08 return6289282472](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6289282472)
and its parent foundation CI-R4 implementation as **INTEGRATED / VERIFIED
SOURCE + ISOLATED LOCAL CHECKS only**. **CI-08/P2 (C0-NC-CI-08) CLOSED LOCAL**:
the exact previous failure is independently reproduced GREEN with actual shell/
runner and inert commands. Real Docker cleanup/runtime behavior remains a later
gate. C6 is COMPLETE/HOLD; C1/C2/C3/C5/C8 and all other implementation tasks HOLD.
CI-06 and CI-07 remain OPEN; whole native integration/PR35 BLOCKED; M3 IN_PROGRESS.

| Binding | Exact value |
|---|---|
| Accepted correction | cbbfce1fb492b164220d5d9d064037216e28e0e1 |
| Correction tree / sole parent | c7bdbb4793c4128492acd1e308fc2c120b29f392 / b02a421bee23f53affb03b310cb8078393b68592 |
| Initial implementation / tree | b02a421bee23f53affb03b310cb8078393b68592 / fd373b323e819b1c3c95dfae466d08c9cd4c6b01 |
| Initial implementation parent | 427bcd4259c35e3c775a40afadf9a97fab9507ec |
| C0 integration ordered parents | accepted C6 cbbfce1 above; prior C0 coordination2280b694915bf7a50cbeb3e9eb12603dd7c52c68 |
| Prepared integration ref | c0/m3-1-native-context-ci-r4; exact final commit/tree in C0 PR34 acceptance/proposal |
| Frozen PR35 / execution branch | 59c9fce52bdaae54f50cdb847a378d47f75c642b / c0/m3-1-native-context-ci-r1 |
| Frozen main / stock | e205e22051bc06295758b504d84699652b176c15 / af7482dede085bc033e3fee34f9a2425124351ee |

### Independent correction evidence

C0 checked the exact three-path +445/-15 correction and all294 remote bytes/modes;
other291 leaves match the parent. Initial259 runner cases were preserved in338;
all338 prior identities and every preexisting test definition/assertion remain
unchanged in363. Only foundation_step/foundation_cli existing runner definitions
change; the other64 existing definitions and existing globals/caps remain exact.
The full generic selection/partition/native/event/source guards remain unchanged.
Workflow/check_backend and all3 CI input hash bindings are byte-exact to b02a421.
Original11 attachments/manifest/repo, full contract and both accepted reports are
unchanged. All58 C6 evidence-manifest entries were independently hash-checked.

C0's independent full runner execution: **363 PASS +130 subtests PASS,106.35s**,
Python3.13.12/all58 installed distributions match uv.lock, source imports from a
separate C0 checkout. Bytecode caches remain outside the checkout. Two existing
pytest configuration/deprecation warnings; no skips/xfails/failures. Ruff check,
format, compileall, shell syntax and diff-check exit0. Constructed clean source
pairing passes all4 roles and167functions/45tables/635columns; no installed DB,
runtime approval or actual catalog claim follows from that source proof.

| Independent actual shell/runner probe | Checks | Actual down | Final exit | execution.json |
|---|---:|---:|---:|---|
| Prior b02a421, delete cases.jsonl during checks | 1 | 0 | 17 | empty; historical RED |
| Corrected cbbfce1 control | 1 | 1 | 17 | primary17/cleanup0 |
| Corrected cbbfce1, same deletion | 1 | 1 | 17 | primary17/cleanup0/evidence_failed=true |

Both corrected commands target exactly their own admitted checks project. The
full suite additionally exercises journal replacement, mode/symlink/binding/
directory faults, success-with-evidence-failure, primary17, direct shell-PID
TERM/INT, invalid initial ownership, absent inherited descriptor, fixed command
scope and90s timeout. Initial admission remains fail closed. After admission,
parent shell memory carries the pinned cleanup authority through FD4; later
diagnostic files cannot grant new authority. Available original sinks retain
their inode/UID/mode checks; missing or foreign files are never recreated.

| C0 evidence | SHA256 |
|---|---|
| Independent JUnit | f8e0686e9d72fdc720b6f198ad87c0167f68e81f5e96369a7416091e39fb53ae |
| Independent unit log | 59524a160f1d34c021b0be6a788ea0258a2318175908f9549176b9bb4fd19072 |
| Independent cleanup control/fault JSON | 101478aec7fb79eb55a7cedb4f5157cb25d686a875c2874b8a6e5a3628e0e102 |
| Independent cleanup probe summary log | 87ed04f20977c9a5755b1cc575f81569d70711787aadf6c2c37ae79b8f6a1a2a |

Integration preserves every accepted C6 file verbatim and changes only C0
HANDOFF/register relative to cbbfce1; prior coordination history is retained.
Final294 leaves,292 protected leaves, exact tree/ordered parents, clean checkout
and constructed source pairing must be verified before the C0 ref advances.

### Concrete next proposal — one unmodified full-inventory diagnostic CI

**C0-M3.1-NATIVE-CONTEXT-CI-RUN4 is PROPOSED/PREPARED, NOT AUTHORIZED and NOT RUN.**
The previous RUN3 one-use approval6267864984 is consumed. Current C6 assignment
6288734136 authorized source/local checks only. No PR35/execution ref movement
or actual PG/Docker/Actions execution is authorized by this acceptance document.

Proposed action after separate explicit approval: one expected-head/force=false
fast-forward of the existing Draft PR35 execution branch from59c9fce to the exact
prepared C0 candidate, causing only its first automatic pull_request/synchronize
run/attempt1. Verify main remains e205e220 and no active PR35 run would be
cancelled; otherwise stop. Record the actual merge SHA, exactly ordered parents
[main,candidate], equal candidate tree, event/run/attempt/jobs/artifact identities.
No manual dispatch/rerun/retry/cancel, second source mutation, new PR, main/stock
movement, repository settings, merge, deployed host or account action is proposed.

Purpose: obtain actual immediate failure/phase evidence for the unmodified
generic802 and terminal outcomes for the47 previously UNKNOWN cases, while
exercising the accepted evidence/job boundary. Use the existing complete entrypoints;
do not build a new diagnostic selector or hide cases to produce a green result.
The88 previous failures have not been fixed; this is a diagnostic run, not a
claim that the full gate will pass. No source patch occurs during execution.

This proposes the already accepted11 expanded jobs: whole normal durable25min,
then dependent foundation45min with fresh resources/full units/generic802/full
tail; other9 jobs unchanged. Serial job allocation is at most25+45min excluding
queue time, not an increased individual cap or a guaranteed completion estimate.
Native20min/payload1080s, state/browser/compat25min, originalS600/P720/fixed120/
+480/supervisor1200/cleanup90 and all individual limits remain unchanged.
Disposable Actions LOCAL/TEST only, no production/account/VM/provider/S3/Telegram/
LLM/deployment. No PostgreSQL/Docker/Actions execution occurred during preparation.

C0/C2 must review the actual failure location/SQLSTATE/constraint and phase records
against the accepted nine-family taxonomy before finalizing owner repair scopes.
This initial unmodified full-inventory capture does not automatically supply every
C2 report section8 fact: valid-V2 controls, intended failure origins, per-case
schema/role/profile and historical phase teardown may still require separately
scoped probes. All12 potentially vacuous negative cases retain their observed
status until intended-origin controls exist. No blanket stale-test classification.

CI-06 cannot close without complete current0013/OFF generic802 with retained
historical phases/assertions. CI-07 cannot close on partial journals or skipped
tail: all11 actual SUCCESS at one exact source, each foundation independently,
full native112/336/105/catalog167/45/635, full tail, clean/cleanup/evidence gates
remain required. A failed durable prerequisite plus skipped foundation is failure.
Administrative branch enforcement remains UNVERIFIED (prior403/rulesets[]);
no protection settings changed. IMPL-05 remains DEFERRED.

Both accepted source diagnostic reports and RUN3 historical9 SUCCESS/foundation
CANCELLED remain. Generic755 terminal outcomes=667PASS+88FAIL,47UNKNOWN is still
the latest actual ordinary PG evidence. Prior native/runtime/UI/CI closures,
D1/D2/D3 and all clocks retained. C2 ten-test-path+helper repair remains unassigned.
A08/P01/P05/renewal/collector/account/A12/M4 later. User owns merge.

---


## History — C6 CI-R4 initial review and CI-08 correction / 2026-10-20 UTC

C0 reviewed [C6 return6288482681](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6288482681).
[C0 disposition and exact correction6288734136](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6288734136):
**CHANGES REQUESTED, one reproduced cleanup defect CI-08/P2 (C0-NC-CI-08).**
Returned implementation remains REVIEW, not INTEGRATED or runtime VERIFIED.
**C6-M3.1-NATIVE-CONTEXT-FOUNDATION-CI-R4 is IN_PROGRESS for this correction only.**
C2/C1/C3/C5/C8 and all other tasks HOLD. CI-06/07 remain OPEN; whole native
integration and Draft PR35 BLOCKED; M3 IN_PROGRESS.

| Source binding | Exact value |
|---|---|
| Reviewed C6 commit | b02a421bee23f53affb03b310cb8078393b68592 |
| Tree / sole parent | fd373b323e819b1c3c95dfae466d08c9cd4c6b01 / 427bcd4259c35e3c775a40afadf9a97fab9507ec |
| C6 correction branch | c6/m3-1-native-context-foundation-ci-r4; exact start b02a421 above |
| C0 coordination branch | c0/m3-1-native-context-ci-r4; this update changes only HANDOFF/register from427bcd42 and does not integrate the five C6 files |
| Frozen PR35 / main / stock | 59c9fce52bdaae54f50cdb847a378d47f75c642b / e205e22051bc06295758b504d84699652b176c15 / af7482dede085bc033e3fee34f9a2425124351ee |

### Independent source/local verification

C0 reconstructed a separate clean checkout, checked all294 remote bytes/modes,
the exact five-path +2262/-32 scope and all289 protected leaves. Original11,
full M3_CONTRACT, both accepted diagnostic reports and C0 documents are unchanged
by C6. All24 entries in C6's evidence manifest hash correctly. Exact CI hashes
and constructed native_host_source pairing pass for all4 components and the
167function/45table/635column catalog. This is source verification, not a new
installed PostgreSQL catalog or runtime approval.

C0 independently ran the runner suite using frozen Python3.13.12, all58 installed
distributions matching uv.lock and imports from C0's own checkout: **338 PASS,
130 subtests PASS,131.66s**, all259 baseline cases retained. Two pytest
configuration/deprecation warnings; no failures. Ruff check/format, compileall,
shell syntax and git diff-check exit0. The additional focused C0 process probe
uses only temporary Git repositories and inert command stubs; no real Docker,
PostgreSQL, build, browser, service, Actions or live endpoint was executed.

| C0 evidence | SHA256 |
|---|---|
| Independent JUnit | 6064ab7874155e08175ef63fabb30d4b8b3016821796992ed567bd0f8b3c27aa |
| Runner log | 44c9c0f253f3a7467e8e86a2e6bcdacf17ce26baf8b8b07aa3618546c2efb704 |
| Cleanup control/fault JSON | 58f1dbf88ecc654adb49ef4710541aecb1f9396e71613834ac9158fc23af7789 |
| Cleanup probe summary log | d1d381bc1d4ce001ccc4332e568696f8a30d3555019ac33cb950ece62759a1fb |

### CI-08/P2 — post-admission diagnostic loss blocks owned cleanup

foundation_step constructs foundation_store before its reporting-error handler
and child command. FoundationEvidence opens/pins every evidence file. The ci.sh
EXIT trap routes cleanup through that same step. If cases.jsonl disappears after
valid admission and checks starts, the cleanup wrapper refuses before invoking
docker compose down. This violates preserved bounded owned cleanup; reporting
failure must fail acceptance without disabling cleanup of already-owned resources.

C0's actual unchanged ci.sh --foundation-core/runner with inert commands:

| Probe | checks | cleanup wrapper | compose-down stub | Exit | execution.json |
|---|---:|---:|---:|---:|---|
| Control: checks returns17 | 1 | 1 | 1 | 17 | primary17/cleanup0 |
| Same checks removes only cases.jsonl, returns17 | 1 | 1 | 0 | 17 | empty |

Reproduction and exact insertion into the existing foundation_commands fixture
are in C0 comment6288734136. Counting only the wrapper would miss the defect.
The existing append-error test supplies an already constructed store and does
not cover this constructor failure. The primary17 is preserved correctly.
This finding is a local source/process result, not evidence of a real resource leak.

### Sole active correction and acceptance boundary

C6 continues its own returned candidate b02a421 in a separate clean checkout;
only scripts/ci.sh, scripts/native_context_db_catalog.py and
tests/test_native_context_db_runner.py may change. The workflow/check_backend
and their current bindings remain byte-exact. Other291 leaves, original sources,
reports/contracts/production/fixtures/locks/C0 documents are frozen. Use the
exact comment6288734136 for scope; do not merge coordination changes into the
three-file correction or start dependent implementation from this unaccepted code.

Preserve initial source/evidence/foreign-UID/path/inode/symlink/digest refusal
before resources. Establish cleanup authority before resources and keep it
independent of later diagnostic journal health: loss/replacement/reopen failure
must still attempt exactly the trusted already-owned cleanup, bounded90s. Do not
derive authority from an untrusted replacement binding, adopt resources, broaden
the cleanup target or add retries/prune/bypasses. Preserve primary failure and
cancellation; otherwise-successful work with missing evidence must fail.

Required regression: control and post-admission journal loss/replacement invoke
the same owned down once, primary17/cancellation remain, success plus evidence
failure stays nonzero, and foreign evidence still refuses before resource work.
Retain338 cases/130subtests and all original assertions; add only focused inert
regressions. Allowed work is frozen local source/static/runner/stub checks only.
Return exact corrected commit/tree/sole parentb02a421, three-path subset/protected
leaf proof, clean source pairing, actual commands/counts/hashes and RED-to-GREEN
proof on PR34, then HOLD. C0 integrates only after corrected source acceptance.

The accepted policy remains11 required expanded jobs: whole normal durable25min
then dependent foundation45min, fresh resources, full generic802 and full tail;
other9 unchanged. No-argument ci.sh remains the complete gate. This design is in
the unaccepted C6 candidate; frozen PR35 still has10 jobs. All existing caps and
native20min/payload1080s/S600/P720/fixed120/+480/supervisor1200/cleanup90 remain.
All11 actual SUCCESS at the exact later source, each foundation job independently,
full clean/cleanup/evidence gates are still required; dependent SKIPPED is not PASS.
Administrative protection remains unverified (prior GET403/rulesets[]); no settings
changed. IMPL-05 remains DEFERRED.

Both earlier diagnostic reports remain accepted SOURCE+SAVED-DATA only. RUN3
39256948310/attempt1 retains9 SUCCESS/foundation CANCELLED at45min; generic802
has755 terminal outcomes=667PASS+88FAIL and47UNKNOWN, no recovered original error
chains. Nine families remain source hypotheses. After corrected source acceptance,
separately authorize C2 section8 bounded actual LOCAL/TEST diagnosis, then scoped
owner fixes and full generic802/native112/336/105/catalog/full-tail/all11 gates.
C2's ten-test-path+helper proposal remains unassigned. No hidden0012 substitution.

PR35/main/stock refs unchanged. No dispatch/rerun/cancel/new PR/merge/deployment
or real Docker/PG/services/build/browser/VM/provider/Telegram/S3/LLM is authorized
by this review/correction. Prior one-use approvals remain consumed; D1/D2/D3 and
earlier closures retained. A08/P01/P05/renewal/collector/account/A12/M4 later.
User owns merge.

---


## History — diagnostic acceptance and initial C6 CI-R4 assignment / 2026-10-20 UTC

C0 accepts [C2 diagnostic return6269738186](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6269738186)
and [C6 budget/evidence return6269543868](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6269543868)
as **INTEGRATED / VERIFIED SOURCE+SAVED-DATA only**. Their diagnostic tasks are
complete; C2 is HOLD. **C6-M3.1-NATIVE-CONTEXT-FOUNDATION-CI-R4 is the sole ACTIVE
task, source implementation/local isolated verification only.** C1/C3/C5/C8 and
all other implementation tasks remain HOLD. CI-06/P2 and CI-07/P2 remain OPEN;
whole native integration/PR35 stays BLOCKED and M3 IN_PROGRESS.

### Accepted report/source evidence

| Return | Exact source / sole parent / scope |
|---|---|
| C2 | aca4f9e5ad8bb8888f580dfa8102e065b2950de7; tree bca69e7c1341f31869d22dc7eac3702c24cf95c1; parent 9ec5508e13a60962a4b2fded1d8a582cd1e6346b; only docs/tasks/M3_NATIVE_CONTEXT_GENERIC_PG_DIAG.md, +789/-0 |
| C6 | e1f5cc77659bc73f82a473bd1543cf8f2200b99d; tree 7ca0266aa5fd45dc95715fd0b3ea004a7d5e103e; same parent; only docs/tasks/M3_NATIVE_CONTEXT_FOUNDATION_BUDGET_DIAG.md, +499/-0 |

C0 reconstructed both exact report trees and commits, proved every preexisting292
leaf unchanged, verified both report SHA256 values and all11 canonical attachments
against SOURCE_MANIFEST/repository. Full M3_CONTRACT remains byte-exact
fe2eb4ef2469ccb14b7147017c3c81066cde1b8a6ad60acbf73922a15e3ace5f.
C0 downloaded and hash-checked RUN3 foundation12191528180 and native12188761326;
both source archives independently rebuild candidate tree
c5941d30aba59fe68f07b86f96c1cd8ae9c55c9a from292 bytes/modes. Actual foundation
job log hash8791be4f230d35a6a2ebba3d1d767af7ef1ac7c98a1138effee381428af4f79a
matches C6. Both log representations match all ordered755 outcomes and full802
inventory. All88 failed IDs/definition lines/family assignments and all47 UNKNOWN
IDs were independently checked; first FAIL13:26:51.337Z, last terminal13:48:49.259Z.

Nine source-supported families account for88 FAIL as5+1+56+3+6+1+7+1+8.
These remain hypotheses about actual first exceptions, not recovered traces or
proof that all failures are stale tests. C0 independently reconstructed the
TRUNCATE FK closure22→31 (nine missing relations), confirmed fresh ingress only
converts codec2 on0012, and checked current0013 readiness versus historical0012
positive assumptions. Three write-fault and nine malformed-input PASSED cases
may fail before their intended target; retain their observed statuses and require
positive/control/error-origin proof in later validation. All47 tenancy/security/
transaction outcomes remain UNKNOWN; no speculative test_tenancy_* edits.

Pure current source_catalog equals the saved native expected catalog. Its saved
function/OID/catalog/profile comparison passes167functions/45tables/635columns,
profile c045a59f86201a244ed0d43fbe22aa8cd72fddd346d770706c6ab3b92ee9a411.
Saved112 native cases/336 phases/105 resets were rechecked. This is reanalysis of
RUN3, not new PostgreSQL or runtime evidence. C0 ran no product tests, fixtures,
Docker, browser, service, Actions, VM, Telegram, S3, LLM or deployment.

### C0 decision: narrow execution-boundary change, explicitly accepted

The whole normal durable visible envelope is1005.260s; it precedes an incomplete
backend prefix1659.763s with47 generic outcomes and the complete post-PG tail
still unknown. C0 accepts C6's whole-lane separation, **10→11 expanded required
jobs**, as a bounded CI-07 repair. This revises only the current orchestration
count/boundary; historical nine/ten-job receipts remain historical. It does not
reopen IMPL-05 or general CI optimization, reduce coverage, reset a clock or
increase an existing per-job/inner cap. No claim of a complete45min fit is made.

| Required job | Responsibility / accepted policy |
|---|---|
| New foundation-durable,25min | Fresh source/resources; entire normal durable gate, all wire checks and six complete lifecycles, owned cleanup, source/evidence/archive |
| Existing foundation,45min | needs: [foundation-durable]; fresh source/resources; complete units, exact generic802, migration/base→head/contracts/two wheels/storage/service/HTTP tail, cleanup/source/evidence/archive |
| Other existing9 jobs | Unchanged browser, Docker29 compatibility, all6 normal/Docker29 image/intent/state matrix jobs and unconditional same-commit native reusable job |

Foundation must not start resources after failed/cancelled durable. A skipped
dependent foundation is not acceptance. C0's later candidate/main acceptance
requires **all11 actual SUCCESS at one exact tested source**, including each of
foundation-durable and foundation independently, clean-source gates and owned
cleanup. Repository rulesets GET returned[]; main branch-protection read returned
403 Resource not accessible by integration. Administrative enforcement therefore
is UNVERIFIED, not absent or configured. No repository protection setting is
changed by this decision; it does not block source implementation or waive the
manual all11 gate/user-owned merge. Verify administrative enforcement separately
at premerge if needed; never claim it follows from workflow YAML or needs.

No-argument scripts/ci.sh remains the full combined gate for storage-images.yml
and bootstrap callers. Only closed --normal-durable and --foundation-core routes
are added; no environment bypass, arbitrary selectors, resume offsets, resource
sharing/adoption, caching, sharding, retries or lifecycle splitting. Native20min/
payload1080s, state/browser/compat25min, foundation45min, original S/600/P720/
fixed120/+480/supervisorS+1200/cleanup90 and every individual cap remain exact.
The new serial25+45 allocation is explicit; request clocks never cross the job
boundary because the whole durable lane moves intact.

### Sole next task and later sequence

C6-M3.1-NATIVE-CONTEXT-FOUNDATION-CI-R4; branch
c6/m3-1-native-context-foundation-ci-r4. Exact base/tree are this combined C0
preparation, published in the canonical task comment on PR34 before work starts.
Preparation contains both report blobs unchanged and updates only HANDOFF/register;
all290 other original leaves remain exact,294 total. C0 integration ref is
c0/m3-1-native-context-ci-r4. C6 may modify only these five existing paths:

1. .github/workflows/ci.yml
2. scripts/ci.sh
3. scripts/check_backend.sh
4. scripts/native_context_db_catalog.py
5. tests/test_native_context_db_runner.py

Implement the accepted complete routing and immediate bounded sanitized generic
phase/failure evidence from C6 report sections4–7. Retain exact collection/order,
three complete native exclusions, partition proof, original pytest exit and
cancellation. Persist existing inventories before fixtures, then start and actual
setup/call/teardown records; missing terminal phases stay INCOMPLETE. Evidence
must survive container removal while runner/always steps remain available, with
private host-owned validated files, flush/fsync and no arbitrary exception text,
SQL/DSN/parameters/locals/env/stdout/payload dumps in the new structured record.
Preserve primary failure when reporting/cleanup fails; successful execution with
missing required evidence fails a separate completeness gate. Source/cleanup and
archive success never convert failure/cancellation into PASS.

Update the exact changed CI_INPUT_SHA256 entries atomically with their inputs;
native-context-db.yml and its hash remain exact. Preserve all existing guard
negatives/event identity/parent checks and259 existing runner tests/130 subtests;
add only meaningful routing/signal/status/evidence/redaction/hostile-path tests.
No Dockerfile/Compose/lock/image/product/SQL/migration/test fixture changes.
Full C6 scope/validation is the canonical PR34 task, which does not authorize an
actual DB/CI run. Local frozen-environment static/isolated unit tests and stubbed
shell routing/cancellation checks are allowed; no real Docker/PG/service/build/
browser/Actions/VM/provider execution. Return REVIEW, then HOLD.

After C0 accepts C6's exact implementation, separately authorize bounded actual
LOCAL/TEST diagnostic execution to obtain C2 section8 facts at unchanged test
source. C2's ten-test-path+one-helper proposal is **not yet an implementation
assignment**. Then issue small owner-specific fixes and validate target-origin
negatives, full current0013/OFF coverage and strict paired historical phases.
Preserve every existing802 generic ID; no historical-only generic substitution,
no relaxing readiness/profile/grants, no deleting usage to downgrade and no
production/migration change without a distinct finding and C0 scope.

PR35/execution remains59c9fce52bdaae54f50cdb847a378d47f75c642b; main remains
e205e22051bc06295758b504d84699652b176c15/schema0012; stock remains
af7482dede085bc033e3fee34f9a2425124351ee. RUN3 approval6267864984 consumed once.
No rerun/dispatch/retry/cancel/new PR/merge/deployment is authorized in this step.
D1/D2/D3/prior closures retained; account/A08/P01/P05/renewal/collector/A12/M4
remain later. User owns merge.

---


## History — RUN3 diagnostic issuance / 2026-10-19 UTC

[C0 final RUN3 disposition6268965488](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6268965488).
**RUN3 completed9 SUCCESS/foundation CANCELLED; PR35 Draft/BLOCKED.
CI-03/04/05 CLOSED LOCAL/TEST. CI-06 generic PG and CI-07 foundation budget OPEN.
C2 generic-PG and C6 foundation diagnostic tasks ACTIVE/source-only.
C1/C3/C5/C8 and prior implementation tasks HOLD. M3 IN_PROGRESS.**

Frozen PR35 candidate59c9fce52bdaae54f50cdb847a378d47f75c642b,
treec5941d30aba59fe68f07b86f96c1cd8ae9c55c9a. Actual RUN3 tested merge
b6cf7fb41297c18ad72da0e22f9694083f76737a,ordered parents
[e205e22051bc06295758b504d84699652b176c15,59c9fce52bdaae54f50cdb847a378d47f75c642b].
Run39256948310/attempt1;approval6267864984 CONSUMED ONCE. No next run
authorized. Main e205e220/schema0012 and stockaf7482d unchanged.

C0 verified all10 actual checkout logs,9 ZIP hashes/sizes,9 current source
archives/all292 bytes+modes and2 frozen-P archives/all275 bytes+modes.
All9 successful clean-source gates PASS. Foundation clean step SKIPPED,
although its archived worktree status is empty and source bytes/modes exact.

Native118074514069 SUCCESS: actual stale advisory89aef741 from original event,
actual HEAD/GITHUB_SHA=b6cf7fb and parents [main,candidate] exact. All4
entrypoint diagnostics PASS,payload digest
8d834a1867f756f010f7b475282cddd78b2dbd427e565abc25656cbb3f79a99d.
This confirms RUN3 admission; missing RUN2 webhook is still not reconstructed.
Full112/112,336 phases,105 reset proofs,259runner+130subtests,full catalog
167/45/635/roles/ACL/body verifier and owned cleanup/source clean PASS.
Carrier596.031864702s,receipt652.391312361s,within unchanged caps.
C6 CI-R3 INTEGRATED/VERIFIED LOCAL/TEST for its bounded corrections.

Foundation real development image:1999unit PASS+130subtests,907deselected,
215.35s;real Git fixtures/strict25-route auth inventory pass. Ruff160/mypy64
PASS. CI-04 actual git prerequisite and CI-05 inventory correction verified.
Browser398frontend/14files+54Playwright45desktop+9narrow PASS; all4 image/
intent shards PASS. Both current durable lanes full6 lifecycles/45-table
before=after/UNKNOWN/wire1/Console/source images PASS. Both complete state
lanes retainedH/T/C/G/E/frozenP0012/T2/lateC3/owned cleanup PASS;P preparation
668.224612098s normal and703.116810121s Docker29 under unchanged720.
CI-01/02 closures retained.

Foundation118074513375 runs13:03:39→13:48:55Z;main step cancelled13:48:51Z
at the45min boundary. Build/durable ends near13:21:05Z;checks13:21:11Z;
units finish13:24:59Z;partition13:25:31Z;generic802 selected13:25:39Z.
First FAIL13:26:51Z. Actual ordered prefix755=667PASS+88FAIL across14modules;
47 remain without terminal outcome. No completed generic summary/JUnit/
tracebacks survived. Migration/base→head/contracts/wheels/service/HTTP
tail NOT REACHED. This is not a passing suite stopped only after completion.

| Finding/task | Disposition |
|---|---|
| CI-03/04/05 | CLOSED / VERIFIED LOCAL/TEST bounded corrections |
| CI-06/P2 | OPEN: generic802 current compatibility;88 observed FAIL,47 UNKNOWN |
| CI-07/P2 | OPEN: foundation45min budget and lost interruption diagnostics |
| C2-M3.1-NATIVE-CONTEXT-GENERIC-PG-DIAG-R1 | ACTIVE source-only report/proposal; no code fix |
| C6-M3.1-NATIVE-CONTEXT-FOUNDATION-DIAG-R1 | ACTIVE source-only report/proposal; no workflow fix |
| Whole native integration/PR35/M3 | BLOCKED pending full gates; no merge |

Source observations:check_backend upgrades0013;old ingress helper converts
codec2 only for0012;old exact42-table/Audit/TRUNCATE inventories and strict
0012 historical profile/reverse helpers need careful successor pairing.
These are source evidence/hypotheses,not missing actual exception traces.
Do not attribute all88 to one cause or alter production authority to satisfy
stale fixtures. All802 current/historical coverage must remain.

Foundation artifact12191528180/SHA256
e651e1120877459883c1e282b45036f95da748b8cbac6947dabd95ec58c37cf2;
native12188761326/SHA256
ffcff8403820e12694d1027ce31cad907deb6cae6aeedd11a4e578f0c9142961.
Full failed-module counts/actual88 IDs recoverable from ci.log; exact802
ordered inventory is in native partition-generic-pg.json. The47 are UNKNOWN.

New preparation changes only HANDOFF/register,sole parent59c9fce;290
protected leaves exact. Exact preparation SHA/tree in task comments.
New branches c0/m3-1-native-context-ci-r4,
c2/m3-1-native-context-generic-pg-diag-r1 and
c6/m3-1-native-context-foundation-diag-r1 start from this same base.
PR35/execution and prior C0-CI-R3 stay59c9fce;accepted owner refs stay fixed.

Only two new diagnostic reports may be produced. C0 independently accepts
proposed write sets and issues future bounded implementation/runtime scopes.
No new PG/Docker/browser/Actions,cap increase,blanket0012 rerouting,
skips/retries,source gate weakening or new PR. All clocks/caps/D1/D2/D3
unchanged;IMPL-05 broad optimization DEFERRED;account/A08/P01/P05/
renewal/collector/A12/M4 later. User owns merge.

### 0.1. C2 generic PostgreSQL diagnostic

C2-M3.1-NATIVE-CONTEXT-GENERIC-PG-DIAG-R1 — explain all generic PG failure families and propose a bounded successor-compatible repair; source-only.

Branch c2/m3-1-native-context-generic-pg-diag-r1.
Only new report docs/tasks/M3_NATIVE_CONTEXT_GENERIC_PG_DIAG.md may be added.

Observed: foundation118074513375 selected exact generic802 after current head0013; logs retain exact ordered first755 results=667PASS+88FAIL,47 without terminal outcome. Earliest FAIL13:26:51Z, far before13:48:51Z cancellation. Fourteen failing modules and counts are in C0 disposition6268965488. Foundation artifact12191528180/SHA256e651e1120877459883c1e282b45036f95da748b8cbac6947dabd95ec58c37cf2 contains ci.log/source.tar.gz; native artifact12188761326/SHA256ffcff8403820e12694d1027ce31cad907deb6cae6aeedd11a4e578f0c9142961 contains full ordered partition/catalog/source evidence. No generic traceback/JUnit/terminal summary survived; do not invent one.

Required diagnostic:
1. Independently validate source/artifact bindings and extract all88 failed nodeids,47 without terminal outcome and full802 inventory; preserve all IDs and mark the47 UNKNOWN, not PASS/unexecuted assumptions.
2. Map every failed nodeid to its shared fixture/helper, actual intended schema phase and relevant current SQL/ABI/assertion. Separate evidence-supported source incompatibilities, plausible hypotheses and unresolved production-risk cases. Include exact path/function/line references and proposed owner for each group; no blanket claim that all88 are stale tests.
3. Inspect known source seams: ingress() only converts raw projections to codec2 when revision==0012; old exact table/column/grant/generated Audit inventories versus current0013; transactional TRUNCATE lists versus new foreign-key references; older migration/reverse/refusal functions operating on an upgraded database; TestEgressMaterialCompatibility exact0012 profile and all retained material/turn/control/security assertions. Trace transitive imports across all14 reported modules and remaining47, not only the first failure.
4. Define the smallest coherent repair boundaries. Current generic tests must actually cover accepted0013 behavior with native gate OFF where appropriate; historical0012 and predecessor assertions remain pinned to their exact intended source/schema and retain every refusal/data/tenant/security assertion. Do not propose running all802 solely on frozen P to hide current regressions. Distinguish a necessary fixture adaptation from a production behavior change requiring separate contract review.
5. Produce an exact proposed file/function write-set with C2/C3/C1/C6 ownership, dependencies and validation plan: focused RED→GREEN cases per failure family, complete generic802, full native112/336/105 and167/45/635 profile retained, no missing historical coverage. State which unresolved assumptions require a separately authorized bounded PostgreSQL diagnostic before implementation. Source-only reasoning cannot close CI-06.
6. Include the full observed88 IDs and47 UNKNOWN IDs (or exact reproducible extraction with hashes), a coverage mapping that preserves all802 and a concise recommended next sequence. C6 separately owns timing/evidence-retention proposal; no CI edits here.

Repository Elefesys/ai-service-manager. Exact shared docs preparation SHA/tree is provided in the canonical C0 task comment; sole parent is frozen PR35 candidate59c9fce52bdaae54f50cdb847a378d47f75c642b/treec5941d30aba59fe68f07b86f96c1cd8ae9c55c9a. Actual completed RUN3 merge b6cf7fb41297c18ad72da0e22f9694083f76737a with ordered parents [e205e22051bc06295758b504d84699652b176c15,59c9fce52bdaae54f50cdb847a378d47f75c642b]; run39256948310/attempt1. Main/schema0012 and stockaf7482dede085bc033e3fee34f9a2425124351ee frozen. Read AGENTS/current HANDOFF/register, canonical Spec/ADR/MVP/Plan M3 and M3_CONTRACT§16–16.20 plus C0 final disposition6268965488. Separate clean checkout; no shared disk/cache assumption. C1/C3/C5/C8 and completed implementation tasks HOLD.

This is source-only diagnostic/proposal work, not authorization to alter implementation or execution gates. Do not change production/API/SQL/migrations/contracts/tests/workflows/scripts/Compose/pins/locks/original11/HANDOFF/register or any existing tracked bytes/modes. No PG/Docker/build/run/browser/Actions/service/provider/VM/deployment/account/Telegram/S3/LLM/renewal, no other agents/chats, new PR, dispatch/rerun/retry/cancel/merge or main/PR35/stock/old refs movement. Only own isolated task ref may move with expected-base lease after the report is verified. No resets/extensions/charging subtraction, weakening assertions, skips/xfails/filters, historical-only substitution for current generic evidence or broad IMPL-05 optimization. Report limitations truthfully; original exception details are absent.

Read-only GitHub metadata/log/artifact retrieval and local source/AST/data analysis are allowed. Local compile/unit probes only where necessary for a concrete source inference, explicitly labelled constructed rather than actual DB evidence; collect-only may use frozen Python3.13/uv.lock with fixture setup prohibited. Do not create redundant tests for the diagnostic document. Verify every existing292 leaves byte/mode-exact, original11=manifest=repo, exact new-file diff/parent/tree and final clean source pairing all4/167functions/45tables/635columns. Return one REVIEW comment on PR34 with full commit/tree/sole parent, report path, precise commands/exits/evidence hashes/limitations, then HOLD. C0 accepts the proposal and separately issues bounded implementation/runtime scopes; no execution permission is created by a report.

### 0.2. C6 foundation budget diagnostic

C6-M3.1-NATIVE-CONTEXT-FOUNDATION-DIAG-R1 — account for foundation time and propose interruption-safe evidence plus a narrow execution-boundary repair; source-only.

Branch c6/m3-1-native-context-foundation-diag-r1.
Only new report docs/tasks/M3_NATIVE_CONTEXT_FOUNDATION_BUDGET_DIAG.md may be added.

Observed RUN3 foundation118074513375 job13:03:39→13:48:55Z;45min workflow cap, main step cancelled13:48:51Z. Build/frontend then full normal durable6 lifecycles finish near13:21:05Z; checks start13:21:11Z,1999units+130subtests finish13:24:59Z(215.35s),full partition907=802+105 complete13:25:31Z,generic802 selected13:25:39Z. By interruption755terminal outcomes=667PASS+88FAIL;47UNKNOWN. First FAIL13:26:51Z. Migration/contracts/wheels/service/HTTP tail NOT REACHED; clean gate SKIPPED. Native and other8 jobs SUCCESS. C2 separately owns the88-failure source taxonomy, not C6.

Required diagnostic/proposal:
1. Reconstruct measured phase timing from actual job log and artifact12191528180 digest e651e1120877459883c1e282b45036f95da748b8cbac6947dabd95ec58c37cf2, source scripts and step metadata. Clearly separate observed durations from unknown remaining47/tail cost and any estimates. Compare relevant prior accepted/failing evidence only at exact sources; no invented full-run duration or benchmark.
2. Explain why failure tracebacks/structured progress are lost: generic pytest emits detail at terminal summary, docker compose run --rm and temporary partition storage, cancelled main pipe. Propose a minimal safe way to retain per-case outcomes/durations and bounded sanitized failure details as they occur, preserve original exit/cancellation/cleanup semantics and archive them via always steps. Do not dump locals, full environment, credentials, DSNs or arbitrary SQL/event payloads. No fail-fast/filter/skipping can replace the complete gate.
3. Propose the smallest execution-boundary change needed for complete foundation work within existing per-job caps. Consider isolating the entire normal durable lifecycle gate from the long unit/generic/migration/reproducibility/service gate, with exact dependency/required-job/source/owned-resource/cleanup/evidence bindings. This is a proposal only; do not implement a job split, remove duplicate coverage or increase45. Explain why the proposed path preserves all existing normal and Docker29 scenarios, current generic802/native112 and full tail. If another minimal option is better, compare it using actual evidence.
4. List exact proposed paths/functions and transitive guards: ci.yml and same-commit reusable identity/input hashes, native CI_INPUT_SHA256/negative source tests if affected, development image workflow copies, existing entrypoint callers, reports locations and clean-source checks. Any changed required-job count/branch-protection dependency is explicit and requires C0 acceptance; current10-job contract is not silently rewritten.
5. Retain native20min/payload1080s, foundation45, state/browser25, all originalS/600/P720/fixed120/supervisorS+1200/cleanup90 and individual caps. Do not reset clocks or share/adopt resources between jobs. No broad optimization/caching/parallel test execution, image/pin/lock work or retries; IMPL-05 stays DEFERRED.
6. Provide a concrete minimal proposal, validation commands/gates and rollback impact; identify actual diagnostic/CI execution still needed. Timing repair cannot claim to fix the88 PostgreSQL failures or close CI-07 without complete later runtime evidence.

Repository Elefesys/ai-service-manager. Exact shared docs preparation SHA/tree is provided in the canonical C0 task comment; sole parent is frozen PR35 candidate59c9fce52bdaae54f50cdb847a378d47f75c642b/treec5941d30aba59fe68f07b86f96c1cd8ae9c55c9a. Actual completed RUN3 merge b6cf7fb41297c18ad72da0e22f9694083f76737a with ordered parents [e205e22051bc06295758b504d84699652b176c15,59c9fce52bdaae54f50cdb847a378d47f75c642b]; run39256948310/attempt1. Main/schema0012 and stockaf7482dede085bc033e3fee34f9a2425124351ee frozen. Read AGENTS/current HANDOFF/register, canonical Spec/ADR/MVP/Plan M3 and M3_CONTRACT§16–16.20 plus C0 final disposition6268965488. Separate clean checkout; no shared disk/cache assumption. C1/C3/C5/C8 and completed implementation tasks HOLD.

This is source-only diagnostic/proposal work, not authorization to alter implementation or execution gates. Do not change production/API/SQL/migrations/contracts/tests/workflows/scripts/Compose/pins/locks/original11/HANDOFF/register or any existing tracked bytes/modes. No PG/Docker/build/run/browser/Actions/service/provider/VM/deployment/account/Telegram/S3/LLM/renewal, no other agents/chats, new PR, dispatch/rerun/retry/cancel/merge or main/PR35/stock/old refs movement. Only own isolated task ref may move with expected-base lease after the report is verified. No resets/extensions/charging subtraction, weakening assertions, skips/xfails/filters, historical-only substitution for current generic evidence or broad IMPL-05 optimization. Report limitations truthfully; original exception details are absent.

Read-only GitHub metadata/log/artifact retrieval and local source/AST/data analysis are allowed. Local compile/unit probes only where necessary for a concrete source inference, explicitly labelled constructed rather than actual DB evidence; collect-only may use frozen Python3.13/uv.lock with fixture setup prohibited. Do not create redundant tests for the diagnostic document. Verify every existing292 leaves byte/mode-exact, original11=manifest=repo, exact new-file diff/parent/tree and final clean source pairing all4/167functions/45tables/635columns. Return one REVIEW comment on PR34 with full commit/tree/sole parent, report path, precise commands/exits/evidence hashes/limitations, then HOLD. C0 accepts the proposal and separately issues bounded implementation/runtime scopes; no execution permission is created by a report.

## История — 0. Текущий шаг C0 — C6 CI-R3/C1 CI-R1 приняты; ordinary CI RUN3 / 2026-10-19 UTC

[C0 review6267813855](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6267813855)
accepts [C6 return6267631802](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6267631802)
and [C1 return6267256061](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6267256061).
**Both corrections INTEGRATED source; C1 bounded inventory VERIFIED LOCAL/TEST.
C0 prepares ordinary PR35 CI RUN3. C1/C2/C3/C5/C6/C8 HOLD. M3 IN_PROGRESS.**

| Binding | Exact value |
|---|---|
| Common preparation / parent of both returns | a85d7aaa03d0a28b06c02197072c4c22ed413820 |
| C6 CI-R3 / tree | 88e9919298dfd6ffd4fd5ac7083371e79ff8b90c / b7c682dd43a305b7dc5be957d77712327d9a04c0 |
| C1 CI-R1 / tree | f7bff2d61f5d49e2d0a7fd9a11883f9a192bb3b8 / 485a17e7aa727891528e8eb0fd2b43348840a969 |
| Combined implementation | 972e838c9f132ee1f4da0c66ec50bed5db179c22 |
| Combined tree | 044c4b775d93cb008acca01b4b0a8064c58caf52 |
| Ordered combined parents | C6 88e9919298dfd6ffd4fd5ac7083371e79ff8b90c, C1 f7bff2d61f5d49e2d0a7fd9a11883f9a192bb3b8 |
| Existing Draft PR35 execution branch | c0/m3-1-native-context-ci-r1 |
| Old PR35 head / future FF lease | 45253120875ba8107035c1eb27427cdc6f30364e |
| Frozen main / MATERIAL P | e205e22051bc06295758b504d84699652b176c15 / schema0012 |
| Frozen stock execution ref | af7482dede085bc033e3fee34f9a2425124351ee |

This preparation changes only HANDOFF/register as a sole child of the combined
implementation. Exact prepared SHA/tree and leased execution binding follow in
the canonical C0 RUN3 comment. C0 preparation ref c0/m3-1-native-context-ci-r3;
owner C6/C1 refs remain at the accepted returns. The existing PR35 is retained.

C0 independently verified all292 remote bytes/modes for each owner return and
combined source; clean exact commits/trees/parents, original11=manifest=repo,
full unchanged M3_CONTRACT. C6 exactly3 paths,+736/-87,289 protected leaves;
C1 exactly1 path,+7/-0,291 protected leaves; combined4 paths,+743/-87,288
protected leaves. All combined changed blobs equal their accepted owner bytes.
C6 evidence manifest60 entries/source archive and C1 published5 evidence hashes
match. All134 old runner IDs and130 subtests retained;125 additional cases.

CI-03 correction keeps actual HEAD==GITHUB_SHA/full clean bytes/modes/tree,
raw commit-header exact2 ordered parents=original event base/head, same repo
name/numeric ID/nonfork/open unmerged PR-to-main/ref/action/run/attempt.
Optional missing/null/current/well-formed stale merge_commit_sha is advisory;
malformed values refuse. No REST refresh/substitution/retry/head-only trust.
PASS/refusal diagnostics contain bounded validated operands, payload digest
and closed predicate reason; no arbitrary malformed values/event/secret dumps.
Refused secondary entrypoints never adopt/read retained lease; diagnostic
write failure retains primary refusal or fails before resource authority.
Constructed stale-advisory RED/GREEN does not recover the missing RUN2 webhook.

CI-04 correction adds only3 development-stage Dockerfile lines for minimal
real git install and apt-list cleanup. Runtime/shared toolchain/pins/locks
and every pre-existing development line exact. Shell syntax PASS; image
installation/runtime proof still requires actual RUN3, not source checking.

CI-05 correction adds exactly3 explicit accepted native owner-route literals
to existing exact sorted equality,25 routes total. Removing only assignment/
concatenation restores whole old AST. Auth7/schema0003/down0002/all existing
auth assertions/offline DB refusal/full generated OpenAPI byte equality exact.

Independent C0 combined verification: Python3.13.12/58 exact locked packages,
runner259 +9 real-Git host fixtures +24 auth =292 PASS,130 subtests PASS/8.15s,
0skip/xfail/failure/error. Ruff/check-format/compile3 paths and read-only
export_contracts --check PASS. Pure clean published source pairing all4
api/worker/scheduler/console and167 functions/45 tables/635 columns PASS.
Production collect-only907=802+105,112=7source+105PG; complete ordered IDs and
fixture guards equal unchanged base; no fixture execution. Ordered SHA256:
allPG8a39f48de61c848c697b394e45d24eba42c86990ea35146bd5d4205e64e04031;
genericbde64cc7fbfd35daa02e8141adcaec0723427ed6c2cfeef4b5e15402e8b1d283;
native7b3ae663595966409f0291fe9836753bf303a37b76c529c36df7dd0957a2cf0d.

| Task / finding / gate | Current disposition |
|---|---|
| C6-M3.1-NATIVE-CONTEXT-CI-R3 | INTEGRATED source; actual CI validation pending |
| C1-M3.1-NATIVE-CONTEXT-CI-R1 | INTEGRATED / VERIFIED LOCAL/TEST bounded inventory |
| C0-NC-CI-03/P2 | Source correction accepted; actual event/runtime closure PENDING RUN3 |
| C0-NC-CI-04/P2 | Source correction accepted; development-image closure PENDING RUN3 |
| C0-NC-CI-05/P2 | CLOSED LOCAL/TEST for strict route inventory; whole foundation pending |
| C0-NC-CI-01/02 | CLOSED in RUN2; retained exact historical proof |
| C0-M3.1-NATIVE-CONTEXT-CI-RUN2 | Historical FAILED8SUCCESS/2FAILURE; approval6266348523 consumed |
| C0-M3.1-NATIVE-CONTEXT-CI-RUN3 | PREPARED; separate exact one-use C0 execution comment follows |
| Full ordinary CI / whole native integration | PENDING; PR35 Draft, no merge |

RUN3 must use one leased FF of existing PR35 execution head and automatic
pull_request/synchronize attempt1. Actual GitHub merge ordered parents must
equal [frozen main,prepared candidate], tree equal candidate. No reuse of
RUN1/RUN2 approvals, manual dispatch/rerun/retry/cancel or source movement
during execution. No user merge or deployment is included.

Required all10 ordinary jobs/clean-source gates on one actual merge: complete
current durable6 lifecycles/45 tables in both lanes; full retained H/T/C/G/E
plus unchanged frozen P0012 MATERIAL replay and T2+lateC3 negatives in both
state lanes; full unfiltered foundation units/generic802PG/migration/contracts/
wheels/service/HTTP smoke; native259runner+130subtests/full112carrier/336phases/
105reset/catalog167/45/635/owned cleanup; frontend and54 real Playwright
45desktop+9narrow plus all4 image/intent shards. Counts describe complete
inventories, not caps or permission to filter mandatory work.

All clocks unchanged: native20min/payload1080s,foundation45/browser25/state25;
originalS/retained600/P720/fixed120/supervisorS+1200/cleanup90. Actual disposable
Actions LOCAL/TEST fixtures only. No shared lab/VM/account/Telegram/provider/
S3/LLM/renewal/deployment. D1/D2/D3 and prior closures retained; IMPL-05/broad
optimization DEFERRED; account/A08/P01/P05/renewal/collector/A12/M4 later.
Whole M3 IN_PROGRESS; user owns merge.


## История — 0. Текущий шаг C0 — RUN2 FAILED; C6/C1 точечные CI-исправления / 2026-10-19 UTC

[C0 final RUN2 disposition6266843739](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6266843739).
**PR35 Draft/BLOCKED; RUN2 completed8 SUCCESS/2 FAILURE.
C6 CI-R3 and C1 CI-R1 ACTIVE/source-only; C2/C3/C5/C8 HOLD. M3 IN_PROGRESS.**

Frozen PR35 candidate45253120875ba8107035c1eb27427cdc6f30364e,
treec250ae01ad5b41f387f1a624dd6a93f51716e4a5; actual tested merge
89aef741a79cf1285d7321666dfa9e0d22ec3a0e, ordered parents
[e205e22051bc06295758b504d84699652b176c15,45253120875ba8107035c1eb27427cdc6f30364e].
Run39246355268/attempt1 automatic synchronize; all10 checkout logs exact.
Approval6266348523 CONSUMED ONCE. No retry/rerun/dispatch/cancel/merge.

| Task / finding / gate | Current disposition |
|---|---|
| C6-M3.1-NATIVE-CONTEXT-CI-R2 | INTEGRATED and VERIFIED LOCAL/TEST for its bounded pairing corrections |
| C0-NC-CI-01/P2 | CLOSED: current0013 durable route; all6 lifecycles in foundation+Docker29 |
| C0-NC-CI-02/P2 | CLOSED: complete frozen P0012 MATERIAL replay in both state lanes |
| C0-M3.1-NATIVE-CONTEXT-CI-RUN2 | FAILED8SUCCESS/2FAILURE; full integration BLOCKED |
| C0-NC-CI-03/P2 | OPEN: native PR admission refuses before resources; actual webhook operands missing |
| C0-NC-CI-04/P2 | OPEN: development/checks image has no git |
| C0-NC-CI-05/P2 | OPEN: exact auth owner-route test omits3 accepted native endpoints |
| C6-M3.1-NATIVE-CONTEXT-CI-R3 | IN_PROGRESS/source-only;3 files; CI-03/04 |
| C1-M3.1-NATIVE-CONTEXT-CI-R1 | IN_PROGRESS/source-only;1 file; CI-05 |
| Current native112/336/105/catalog | NOT RUN in RUN2; prior RUN1 proof retained on its own merge |
| Generic802 PG/contracts/reproducibility/service smoke | NOT REACHED after failing full units |

C0 verified all9 ZIP digests,8 current archives/all292 bytes+modes and2 frozen-P
archives/all275 bytes+modes. Both actual MATERIAL reports pass the new reader:
correct current coordinator versus exact P, images/diagnostics/ACK-loss/recovery/
callers/owners/cleanup/clock. Full H/T/C/G/E/P and T2+lateC3 complete.
Preparation normal712.921579s(7.078421s remaining),Docker29697.971276s
(22.028724s remaining),within unchanged720;cleanup PASS. Both durable lanes
complete all6 lifecycles/full45-table before=after hashes,UNKNOWN/wire1/Console,
4 source image proofs each. Browser398 frontend/14files+54 Playwright45desktop+
9narrow and all4 image/intent shards PASS. Eight successful clean-source steps PASS.

Foundation full units:1858passed/7failed/9errors,907deselected,130subtests PASS.
Six SourceGuards failures+nine host Git fixture setup errors are FileNotFoundError
for git in development image. One other failure is tests/test_auth_contract.py:62:
actual25 owner routes versus22 expected; exact missing3 human-context routes.
C0 reproduced that RED offline; full generated OpenAPI already equals snapshot.
Frozen auth.v1 remains7 endpoints/schema0003. Foundation clean step was skipped;
its archived worktree status is empty and all source bytes/modes verified.

Native fails event_identity before commands/resources; cleanup entrypoint repeats
the refusal. Receipt REFUSED/NOT_RUN,carrier+catalog null,cleanup NOT_ATTEMPTED.
Actual Git merge parents/tree are correct. Source-only9-case matrix reproduces
the refusal by changing only an optional merge_commit_sha snapshot to the previous
merge; exact failed webhook operand is UNKNOWN because diagnostics omitted it.
Preserve actual event base/head/parents/ref/repository/HEAD authority; add safe
per-predicate evidence. Never substitute a later REST response for the event.

This preparation changes only HANDOFF/register,sole parent45253120;290 other
leaves exact. Exact prepared SHA/tree in canonical task comments. New isolated
C0 c0/m3-1-native-context-ci-r3, C6 c6/m3-1-native-context-ci-r3 and
C1 c1/m3-1-native-context-ci-r1 all start from that exact preparation.
PR35/c0-CI-R1 and c0-CI-R2 stay45253120;C6-CI-R2 stays62a85024.
No source implementation fix or next runtime execution is included in preparation.
C0 independently reviews both disjoint returns before combining and issuing a
fresh exact next CI binding. User owns merge; keep one existing Draft PR.

Main e205e220/schema0012,stockaf7482d and previous closures/D1/D2/D3/all caps
unchanged. No broad optimization/IMPL-05; account/A08/P01/P05/renewal/collector/
A12/M4 later. Exact task scopes follow; no other chats or agents activated.

### 0.1. C6-M3.1-NATIVE-CONTEXT-CI-R3

C6-M3.1-NATIVE-CONTEXT-CI-R3 — ordinary PR event admission, bounded failure evidence and development git; source-only.

Repository Elefesys/ai-service-manager. Start from the full C0 docs-preparation SHA/tree in the canonical task comment, sole parent frozen RUN2 candidate45253120875ba8107035c1eb27427cdc6f30364e/treec250ae01ad5b41f387f1a624dd6a93f51716e4a5. Separate clean checkout/branch c6/m3-1-native-context-ci-r3; no shared checkout/cache assumptions. Read AGENTS, current HANDOFF/register, canonical Spec/ADR/MVP/Plan M3 and M3_CONTRACT§16–16.20. C1 separately owns the one-file CI-R1 route-inventory correction; C2/C3/C5/C8 HOLD. C6 only this bounded task.

Observed basis: RUN2/39246355268 attempt1, native job118039117478. Actual checkout and same-commit workflow use merge89aef741a79cf1285d7321666dfa9e0d22ec3a0e; raw Git parents are exactly [e205e22051bc06295758b504d84699652b176c15,45253120875ba8107035c1eb27427cdc6f30364e], treec250ae01ad5b41f387f1a624dd6a93f51716e4a5. event_identity refuses the combined “PR checkout is not the exact base/head merge” predicate before commands/resources. Cleanup entrypoint repeats the refusal. Actual receipt: admission REFUSED, stock_db NOT_RUN, carrier/catalog null, owned_cleanup NOT_ATTEMPTED_EVENT_REFUSED;5.123185s. Artifact12183930672/1981bytes/SHA2562b9d9e85ff73bc42482ddde1af1d337f0496142d83dc48b185fb2e462d3f592b.

Evidence limit: the lane retained neither the actual event identity operands nor the exact failed subcondition. C0 independently reproduced the same refusal with correct actual HEAD/tree/ordered parents and only the previous non-null advisory merge_commit_sha substituted. Fresh/None values pass; all wrong/reversed/missing/extra actual parents refuse. This is synthetic predicate isolation, not the recovered RUN2 webhook. Do not claim its exact field value as observed. A post-event REST PR read is not the original event.

Additional confirmed basis: foundation job118039116598 reached full unfiltered units and reported6 SourceGuards failures plus9 real Git fixture setup errors because the development image has no git executable. Final RUN2 is8 SUCCESS/2 FAILURE; both prior CI-R2 routing defects CLOSED. Final C0 disposition6266843739 is authoritative; original webhook limitation above remains.

Only these3 existing files may change:
- scripts/native_context_db_catalog.py
- tests/test_native_context_db_runner.py
- infra/Dockerfile.backend — development-stage git availability only

Required behavior:
1. Preserve admission authority: actual GITHUB_SHA==checked-out HEAD, clean all tracked bytes/modes/tree, actual Git commit headers even at fetch-depth1, exactly two ordered parents matching the actual event's base/head, same repository name+numeric ID/non-fork, open unmerged PR-to-main/ref/number/base/head/action identity, genuine Actions run/attempt. Wrong actual parents, stale event base/head, wrong source/ref/repository, malformed/duplicate payload, forks and unsupported events must refuse before any command/resource/cleanup adoption. Stock/main push routes and source leases remain exact.
2. Correct only the documented PR snapshot compatibility issue. GitHub documents GITHUB_SHA as the PR merge-branch commit and mergeability/test-merge metadata as asynchronously computed. The additional optional pull_request.merge_commit_sha snapshot must not override independently proven actual event source/HEAD/ordered-parent identity. Handle a missing/null or well-formed stale advisory value without rejecting an otherwise exact current merge; preserve it truthfully as advisory diagnostic data, never as tested source. Invalid types/formats must remain explicit and tested. Never substitute fresh REST values into the original event, retry/poll GitHub, relabel a PR as stock, trust head_sha alone, remove actual parent checks or allow a stale base/head event.
3. Split admission diagnostics so a failure identifies the actual predicate. Retain a small structured allowlist of safe source/run/attempt/ref/PR/validated SHA and parent operands, payload digest and closed failure reason on success and refusal, including secondary cleanup entrypoint. Do not dump the full event, PR text, environment, tokens, credentials, arbitrary malformed values or URLs. Diagnostic write errors must not hide the original refusal or authorize resources. Retain zero resource work after refusal; avoid presenting NOT_ATTEMPTED cleanup as PASS.
4. Provide the real git executable in the development/checks stage used by the unchanged full unit command. Use a minimal development-only install under the existing pinned base/toolchain; no package upgrade, image/pin/lock change or git addition to runtime/shared toolchain stages. Preserve the exact runtime stage and existing development COPY/CMD/workflow inputs. Do not copy a host binary or replace real Git fixtures with mocks/skips; no claim of image execution from a source-only check.
5. Preserve all ownership/nonces/leases/retained-state refusal/isolated child credentials/105 reset guards, complete112 carrier and336 phase accounting, catalog167/45/635, full generic/native partition, source archive fidelity, primary/secondary error handling, owned-only cleanup and all unchanged caps. No DB, production, schema, workflow, launcher, partition, budget or other compatibility-harness change; Dockerfile changes are confined to the development git prerequisite above.

Bounded verification:
- Frozen Python3.13/uv.lock development environment; compile/Ruff/check-format the2 changed Python paths; inspect Dockerfile stage boundaries and prove runtime/shared toolchain, pins/locks and every unrelated line remain exact.
- Full existing tests/test_native_context_db_runner.py unit suite, all prior134 cases/130 subtests retained except explicitly justified replacement of the advisory-only rejection fixture; no weaker actual-source admission assertion. Add meaningful regression cases for opened/reopened/synchronize with current/null/stale advisory, actual parent/base/head/env/source drift, malformed optional value, failed operands/diagnostic redaction/diagnostic write failure and secondary entrypoints. Check before any resource command, not just return codes.
- Source-only RED on unchanged base for the stale advisory/current exact merge case, then GREEN. Label constructed fixtures accurately; do not invent raw RUN2 payload. If evidence reveals a different cause or a necessary wider scope, return a precise blocker before expanding.
- Execute the full existing native runner unit module and all9 parametrizations of the existing real-Git host source fixture in tests/test_telegram_egress.py; git must be a real executable. Existing actual image failures establish the missing prerequisite; Docker build/run is NOT authorized here and is deferred to the next separately bound CI. Do not add redundant tests that merely match an install line.
- Collect-only production partition907=802+105,112=7source+105PG; retain all ordered IDs/fixture guards with no fixture execution. Pure source pairing on final published source for all4 components/167functions/45tables/635columns.
- Exact3-path diff,289 protected leaves byte/mode-exact to preparation, including all CI-R2 fixes, workflows/check_backend/launcher/Compose/locks/production/API/Console/migrations/contracts/original11. Publish exact command/exits/counts/source/evidence hashes.

Return only isolated task branch and one REVIEW comment in PR34, full commit/tree/sole parent, diff and evidence/limitations; then HOLD. No actual PG/Docker/browser/Actions or services, new PR, PR35 head/main/stock/old C0 or C6 ref movement, rerun/dispatch/retry/cancel/merge/VM/deploy/account/provider/Telegram/S3/LLM/renewal, other agents/chats or broadened optimization. PR35 remains frozen at45253120; C0 independently reviews C6 and C1's disjoint returns before a separately bound future run. User owns merge.

Primary platform references:
https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request
https://docs.github.com/en/rest/pulls/pulls#get-a-pull-request

### 0.2. C1-M3.1-NATIVE-CONTEXT-CI-R1

C1-M3.1-NATIVE-CONTEXT-CI-R1 — update the exact auth-consumer owner-route inventory for accepted native context; source-only.

Repository Elefesys/ai-service-manager. Separate clean checkout/branch c1/m3-1-native-context-ci-r1 from the exact C0 preparation SHA/tree in the canonical task comment; sole parent frozen PR35 RUN2 candidate45253120875ba8107035c1eb27427cdc6f30364e/treec250ae01ad5b41f387f1a624dd6a93f51716e4a5. Read AGENTS/current HANDOFF/register, canonical Spec/ADR/MVP/Plan M3, M3_CONTRACT§16–16.20 and C0 disposition6266843739. C6 separately owns CI-R3; C2/C3/C5/C8 HOLD. No shared checkout/cache assumption.

Observed C0-NC-CI-05/P2: RUN2/39246355268 foundation118039116598 fails tests/test_auth_contract.py:62 because the explicit expected owner-route list omits three already accepted native routes. C0 independently reproduced the exact failure offline; actual inventory25 versus expected22, exactly3 additions and no test-only extras. Full generated OpenAPI is byte-for-byte equal to contracts/openapi.json. This is a test inventory correction, not API/contract/schema implementation.

Only tests/test_auth_contract.py may change. Add an explicit native-context route list containing exactly:
- GET /api/v1/workspaces/{workspace_id}/conversations/{conversation_id}/human-context
- GET /api/v1/workspaces/{workspace_id}/conversations/{conversation_id}/human-context/observations
- POST /api/v1/workspaces/{workspace_id}/conversations/{conversation_id}/human-context/reconcile

Include it in the existing exact sorted inventory comparison. Preserve every previous auth/billing/messaging/control/escalation route and all frozen auth.v1 assertions:7 endpoints,schema0003/down0002,LOCAL/TEST,error codes/session/password policy/production and Ops disabled. Keep complete byte-for-byte generated OpenAPI equality and OfflineDatabase's refusal of DB access. No filtering out native paths, subset/superset comparison, runtime-derived expected list, skip/xfail, broad snapshots regeneration or relaxed assertions.

Verification: frozen Python3.13/uv.lock environment; reproduce the original single test RED before change, then run the full tests/test_auth_contract.py and tests/test_auth_unit.py modules GREEN. Compile/Ruff/check-format the changed file; run the existing read-only contract export --check and verify contracts/auth.v1.json/contracts/openapi.json plus every other tracked file unchanged. No new redundant tests required; the retained exact inventory/snapshot assertion is the regression gate. Preserve canonical sources/original11 and pure source pairing all4 components/167functions/45tables/635columns on the final published source. Exact1-file diff,291 other leaves byte/mode-exact to preparation. Publish precise commands/exits/counts/hashes/limitations.

No production/API/frontend/migration/contract/Docker/workflow/lock/runner or other test changes. If any accepted route or generated snapshot actually differs from the above evidence, stop with a precise blocker before expanding. Unit/contract checks use existing offline seams only; no DB/service/Docker/browser/Actions/network provider/API calls.

Publish only isolated task branch and one REVIEW return in PR34 with full commit/tree/sole parent,1-file diff,evidence/source hashes and remaining limitations; then HOLD. No new PR, PR35/main/stock/old source-ref move, rerun/dispatch/retry/cancel/merge/VM/deploy/Telegram/account/S3/LLM/renewal, other agents/chats or broad cleanup. C0 reviews both disjoint C1/C6 returns before integration and a separately bound next CI; user owns merge. Whole M3 IN_PROGRESS; previous closures/all caps and later scopes retained.

## История — 0. Текущий шаг C0 — CI-R2 source принят; ordinary CI RUN2 / 2026-10-19 UTC

[C6 return6266094297](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6266094297)
accepted by [C0 review6266253490](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6266253490).
**C6 CI-R2 INTEGRATED source; C0 prepares ordinary CI RUN2.
C1/C2/C3/C5/C6/C8 HOLD. M3 IN_PROGRESS.**

Accepted source62a85024fbebe53b8e0b5b86dc876dcbf538154f,
treea8572e8fe2ee7646f85922f7f186e298632e6018,
sole parentdac24364ca2daea082a05d6e92d4809e2ab9725c.
Exactly4 allowed test/launcher paths,+977/-74;288 protected leaves exact.
Both CI findings are corrected in source; their actual runtime closure awaits RUN2.

C0 verified all292 remote bytes/modes, original11/manifest/contract,
54 evidence-manifest entries/12 published hashes and exact source archive.
Independent two-module units798/798 PASS/62.59s; all745 previous IDs retained,
53 additions,0skip/xfail/failure/error. Python3.13.12/58 locked distributions;
Ruff/check-format/compile/launcher shell+heredoc PASS. All4 current durable
calls now use separate exact0013/45-table fingerprints; held-state functions
differ only in those4 call targets. Historical canonical_fingerprint is exact.
Coordinator differs only in MATERIAL dispatch; accepted P runs from exact
commit/tree/parents/275-byte+mode-checked checkout. Frozen phase/budget/recovery/
ownership/cleanup/workspace bodies retained. Same clock S/caps/error discipline.

C0 additionally validated the new report reader against authentic accepted P
main run38960113060/artifact12072813317. ZIP/source archives275 files and P
identity verified; current source-derived image proofs accepted the real report.
This is offline historical-evidence checking, not new runtime execution.
Generated P header imports real0012 without revision override; expected image
source inventories78runtime/168development. Current pure source pairing all4
components/167 functions/45 tables/635 columns PASS. Production collect-only
907=802+105,112=7source+105PG/105 guarded consumers; every ordered ID equals
C6 and actual RUN1 inventories. Three files byte-equal C6; no fixture executed.

| Task / finding / gate | Current disposition |
|---|---|
| C6-M3.1-NATIVE-CONTEXT-CI-R2 | INTEGRATED source |
| C0-NC-CI-01/P2 | Fixed in source; actual durable closure PENDING RUN2 |
| C0-NC-CI-02/P2 | Fixed in source; actual complete state closure PENDING RUN2 |
| C0-M3.1-NATIVE-CONTEXT-CI-RUN1 | Historical FAILURE6SUCCESS/4FAILURE; approval consumed |
| C0-M3.1-NATIVE-CONTEXT-CI-RUN2 | PREPARED; separate exact one-use execution comment follows |
| Actual corrected full CI | NOT RUN at preparation; acceptance PENDING |
| Prior native/browser slices and other closures | Retained on their exact tested sources |

Preparation is a docs-only child of62a85024; exact SHA/tree in C0 execution
comment. Only HANDOFF/register change;290 other leaves exact. C0 prepares on
c0/m3-1-native-context-ci-r2; C6 return branch stays62a85024.
PR35 currently uses c0/m3-1-native-context-ci-r1 atd5e0fe586179dfc22084c80562abec0796e88cbe.
Moving that PR head requires the new exact execution binding and triggers
one pull_request/synchronize run. Keep one existing Draft PR; no new PR.
Main e205e22051bc06295758b504d84699652b176c15/schema0012 and stock execution
af7482dede085bc033e3fee34f9a2425124351ee stay unchanged.
User owns merge; D1/D2/D3/all caps/previous closures retained.
IMPL-05 DEFERRED; account/A08/P01/P05/renewal/collector/A12/M4 later.

### 0.1. C0-M3.1-NATIVE-CONTEXT-CI-RUN2 — corrected ordinary PR gate

After exact source review and this docs-only preparation, C0 publishes one
new approval binding full candidate SHA/tree/sole parent62a85024, expected old
PR35 headd5e0fe58, and frozen main e205e220. Then one leased fast-forward of
c0/m3-1-native-context-ci-r1 to that prepared source admits a single automatic
pull_request/synchronize run, attempt1. No rerun of39235044613, workflow dispatch,
second mutation during execution, new PR, main/stock-ref move, cancellation,
merge or deployment. Old approval6264718588 stays CONSUMED and is not reused.

Record the actual new GitHub merge SHA and ordered parents[main,new candidate],
require merge tree equal candidate, then bind every actual job/archive to that
source. Metadata head_sha alone does not establish the tested merge.

Required acceptance:
- All10 ordinary jobs and retained clean-source gates succeed. No skipped,
  absent, cancelled, continued-on-error or filtered mandatory work.
- Foundation/Docker29: all six current durable lifecycles complete on exact
  current0013/45-table fingerprints; UNKNOWN/receipts/Console/wire/identity and
  teardown assertions retained. All original direct-wire assertions execute.
- Both state lanes: current coordinator truthfully reports itself; complete
  E0011→frozen P0012 executes unchanged from exact e205e220/tree85206b9c.
  Full42 tables/132 functions/readers/cycles/ACK-loss/recovery/used-refusal/
  cutover/restart, prior H/T/C/G/E and all T2+lateC3 negatives complete.
  Inspect actual P archives/images/reports/diagnostics/owners/cleanup and clock.
- Foundation must reach its formerly blocked full unfiltered unit suite,
  exact generic802 PG inventory, full migration before/after lifecycle,
  contract export, deterministic wheel comparison and service/HTTP smoke.
- Native must independently pass current112/336 phases/105 guarded resets,
 134 runner+130subtests, complete167/45/635 catalog/ACL/verifier, actual PR
  merge admission/owned cleanup/source clean. Historical P is not native proof.
- Full frontend and54 Playwright45desktop+9narrow execute again; four image/
  intent shards remain required. Counts describe complete current inventories,
  never permission to drop cases.
- Preserve whole native20min/payload1080s, foundation45/browser25/state25,
  original S+600/P+720/fixed120/supervisorS+1200/cleanup90 and all other caps.
  Measure actual new replay/checkout/export cost; no budget extension/reset,
  elapsed subtraction, retry or broad optimization.
- All resources limited to the existing disposable Actions LOCAL/TEST jobs.
  No VM/deployed host/account/Telegram/provider/S3/LLM/renewal work.

C0 inspects actual results before closing CI-01/02 or accepting whole integration.
A new failure remains evidence and leads to a bounded disposition; no automatic
retry or unrelated reopening. At preparation there is no new runtime execution.

## История — 0. Текущий шаг C0 — ordinary CI FAILED; C6 CI-R2 / 2026-10-19 UTC

[C0 failure disposition6265446311](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6265446311).
**PR35 Draft/BLOCKED; run39235044613/attempt1 completed:6 SUCCESS,4 FAILURE.
C6 CI-R2 ACTIVE/source-only; C1/C2/C3/C5/C8 HOLD. M3 IN_PROGRESS.**

Frozen PR35 head d5e0fe586179dfc22084c80562abec0796e88cbe, tested merge
bb8a30324e9e4f40bb64784dd5774d899e4fcebb, tree2f7123c22b4685173c9c5faa8f5dcdc99f7b3231,
ordered parents[e205e22051bc06295758b504d84699652b176c15,d5e0fe586179dfc22084c80562abec0796e88cbe].
All10 checkout logs bind to this merge. Approval6264718588 CONSUMED ONCE.

| Task / finding / gate | Current disposition |
|---|---|
| C6-M3.1-NATIVE-CONTEXT-CI-R1 | INTEGRATED source |
| C0-M3.1-NATIVE-CONTEXT-CI-RUN1 | FAILED; full integration BLOCKED |
| C0-NC-CI-01/P2 | OPEN: current durable0013 invokes historical0012 fingerprint |
| C0-NC-CI-02/P2 | OPEN: MATERIAL0011→0012 uses current0013 candidate as P |
| C6-M3.1-NATIVE-CONTEXT-CI-R2 | IN_PROGRESS/source-only; exact4-path task below |
| Actual PR native/browser slices | VERIFIED LOCAL/TEST on tested mergebb8a3032 |
| Foundation generic802 PG/contracts/reproducibility/smoke | NOT VERIFIED; stopped before compose run checks |
| Historical closures/main/M3 | Retained / unchanged / IN_PROGRESS |

Failed: foundation118001968950 and docker29-compatibility118001968862 at
durable_fresh, tests/test_telegram_egress_postgres.py:949→801,0013!=0012.
Both state jobs normal118001969077/docker29118001968958 stop at
MATERIAL probe_bb8a3032_False; generated header asserts current runtime is0012.
C0 source-only reproductions confirm both mismatches. Actual state logs suppress
inner stderr; no later unexecuted stage is claimed PASS. Both failure reports
retain owned cleanup PASS and complete diagnostics. Preparation705.048s(normal)/
521.814s(Docker29) stayed below720; observed failure is schema probing.

C0 checked5 ZIP digests,7 current-source archives/all292 bytes+modes, native
manifest and archived clean status in4 failed jobs. Native actual112=7source+56DB+
12API+37runtime,336 phases,105 guarded resets,134 runner+130subtests PASS.
Rechecked installed167 typed functions/OIDs/bodies/ACL,45 tables/635 columns,
profilec045a59f86201a244ed0d43fbe22aa8cd72fddd346d770706c6ab3b92ee9a411,
owned cleanup/final clean PASS. Carrier588.778s/whole648.299s under20min.
Browser actual398 frontend/14 files and54 Playwright=45desktop+9narrow PASS;
clean-source SUCCESS. Four image/intent jobs SUCCESS. Whole CI remains FAILED.

This C0 preparation is a docs-only child of frozen d5e0fe58, on new isolated
c0/m3-1-native-context-ci-r2 and c6/m3-1-native-context-ci-r2 branches.
Exact SHA/tree in canonical C6 task comment; only HANDOFF/register differ,
290 other leaves remain exact. Do not move PR35 head for status-only docs:
that would trigger a new run. Source correction and next execution are separate.
Main e205e22051bc06295758b504d84699652b176c15/schema0012 and stock ref
af7482dede085bc033e3fee34f9a2425124351ee remain unchanged; user owns merge.
D1/D2/D3/caps/previous closures retained; IMPL-05 DEFERRED. Account/A08/P01/P05/
renewal/collector/A12/M4 remain later gates.

### 0.1. Exact C6 CI-R2 correction task

C6-M3.1-NATIVE-CONTEXT-CI-R2 — repair two observed compatibility-harness source/schema pairings; source-only.

Repository Elefesys/ai-service-manager. Start only from the full C0 preparation SHA/tree in the canonical task comment, in a separate clean checkout of c6/m3-1-native-context-ci-r2. Its sole parent is frozen PR35 candidate d5e0fe586179dfc22084c80562abec0796e88cbe; preparation changes HANDOFF/register only. Do not assume shared disk/cache. Read AGENTS, current HANDOFF/register, canonical Spec/ADR/MVP/Plan M3 and M3_CONTRACT§16–16.20; original11/manifest/contract and existing acceptance remain authoritative. C1/C2/C3/C5/C8 HOLD.

Observed basis: C0 disposition6265446311 and run39235044613/attempt1. C0-NC-CI-01/P2 breaks foundation+Docker29 compatibility at durable_fresh: actual0013 versus retained canonical_fingerprint default0012. C0-NC-CI-02/P2 breaks both state lanes: the current0013 candidate image is passed to the0012 MATERIAL readiness header. Native112/336/105 and browser54/frontend398 actually PASS on mergebb8a30324e9e4f40bb64784dd5774d899e4fcebb; whole CI FAILED. Fix only these source/schema routing errors; do not alter product behavior.

Only these4 existing files may change:
- tests/test_telegram_egress_postgres.py
- tests/test_telegram_egress_migration.py
- tests/test_telegram_egress.py
- scripts/test_telegram_egress_migration.sh

Required correction A — current durable0013:
1. Preserve canonical_fingerprint default0012, its closed0009–0012 schema set and historical MATERIAL/42-table callers/assertions. Do not widen it to0013, derive a permissive expected revision from the live DB, or change production RuntimeDatabase/schema readiness.
2. Introduce a separate exact current0013 fingerprint path for durable_local and durable_snapshot. Cover every current empty/seeded/before/after/cleanup use, not just the first failing call. Validate exact revision0013 and the complete45-table inventory; preserve all row hashes/counts, UNKNOWN receipts, Console sessions, wire counter, actual caller database identity, read-only snapshots, held-state lifetime and owned fixture teardown. Missing/extra native tables and schema mismatch must fail before accepting any fingerprint.
3. Keep historical asm_test/frozen executors and schema0012 fingerprints unchanged. No downgrade of current callers, partial table filtering, skips or removal of durable phases.

Required correction B — retained MATERIAL0011→0012:
1. Add exact frozen P=e205e22051bc06295758b504d84699652b176c15 /tree85206b9c66ac151f3847aa39f46fb75663a18b91. This is the accepted PR34 main0012, ordered parents[933ddd284ff5b77fb1aa88a4270ab0032bc499c9,f78ff5c1d9996760d6d5e78d15a2c7a8148bab5f]. Verify commit/tree/ancestry, clean checkout and source/image bindings. E stays933ddd284ff5b77fb1aa88a4270ab0032bc499c9/treed0759acb9f83ec3f3e10d9c5d1325c937c343ee7.
2. Run the accepted complete E→P MATERIAL phase from P's exact tracked checkout/helper/controller/runtime/development bytes, analogously to retained E. Invoke only its material phase, not its whole coordinator. Do not transplant0012 foundation into current source, monkeypatch the frozen executor, build modified archives or accept a current0013 image as P.
3. Current outer coordinator/source archive/ledger must retain the actual current SHA. Frozen MATERIAL reports, source-P archive, diagnostics, images, recovery selections and readiness pairings identify P truthfully. Update the current launcher admission checks to validate both current coordinator and frozen P execution instead of equating them. Export complete retained reports on success/failure, require a clean frozen checkout before removal, and retain primary/secondary failure discipline.
4. Preserve every historical phase/assertion and full ordering: H/T/C/G/E, MATERIAL42 tables/132 functions, current-at-P V1 readers and fresh V2/OFF receipt, unchanged row/catalog proofs, two upgrade/reverse cycles, committed-result-loss86 recovery by observed revision, used55000 refusal before DDL, P cutover/restart, complete T negatives2 and late-C negatives3, owned cleanup and foreign-state invariance. Current0013 remains the dedicated native gate and current durable route; historical P replay cannot claim current native readiness.
5. Preserve original clock S and exact budgets: retained preparation S+600, terminal P S+720/fixed120, supervisor+480/S+1200, cleanup90, state25min and all existing transport caps. Charge added checkout/archive/image/export/cleanup work to the original applicable budget. Use only correctly source-validated existing image reuse; no budget reset, subtraction, extension, extra retry or broad caching/optimization. If the complete pairing cannot fit the existing contract, report a precise blocker.

Bounded verification:
- Python3.13/frozen uv.lock development dependencies; compile/Ruff/check-format the changed Python and sh -n the changed launcher.
- Full unit selections of tests/test_telegram_egress.py and tests/test_telegram_egress_migration.py, with all existing cases and failure assertions retained. Include new meaningful negatives for mismatched0012/0013 tables/revision, the full current durable call route, wrong P source/tree/ancestry/image/report/cleanup identity, current coordinator versus P identity, unconsumed/expired/tampered handoff, original-clock budget accounting and primary-error/report-copy/cleanup propagation. Use existing source/unit seams; no DB/Docker work.
- Reproduce each source-only failure on unmodified base, then demonstrate corrected routing without overriding foundation revision. Keep exact historical helper/phase bodies unchanged where they remain retained; explicitly account for unit fixture expectations that now model a frozen P executor. Tests must fail if current0013 is again fed to a0012 executor or native tables are silently omitted.
- Verify full existing generic-unit invocation remains unchanged; no marker/collection/ignore/workflow edits. Collect-only current generic/native partition (907=802+105;112 carrier=7source+105PG) with production guard, no fixture execution. Counts describe current complete inventories, never a cap permitting missing tests.
- Exact4-path diff;288 protected leaves equal preparation, including workflows/runner/check_backend/Dockerfile/Compose/image pins/locks/production SQL/API/Console/contracts/original11. Pure source pairing all4 components/167 functions/45 tables/635 columns on the final published source. Attach exact commands/exits/counts and evidence/source hashes.

No changes to production code, migrations0001–0013, frozen source refs, source helpers outside the4 paths, docs, contracts, workflows, runner partition, dependencies or budgets. Do not add source-only output that pretends to be live PG/browser proof. If a necessary correction needs another file or weakens any retained assertion, return a precise blocker before expanding.

Execution boundary: publish only the isolated task branch and one REVIEW return in PR34 with full commit/tree/parent, allowlist diff, evidence hashes and limitations, then HOLD. Actual PG/Docker/browser/Actions/deploy are NOT RUN by this task. No inspection/start/reuse/cleanup of services, no new PR, no change to open PR35 branch c0/m3-1-native-context-ci-r1, main, stock execution ref or old C6 CI-R1 ref; no dispatch/rerun/retry/cancel/merge/VM/account/provider/Telegram/S3/LLM/policy/renewal actions and no other chats/agents. C0 independently reviews the return and then binds a separate next CI execution to the corrected exact source. User owns merge.

## История — 0. Текущий шаг C0 — CI-R1 source принят; первый ordinary PR/CI / 2026-10-19 UTC

[C6 return6264502649](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6264502649)
accepted by [C0 review6264669308](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6264669308).
**C6 CI-R1 INTEGRATED source; C0 prepares first ordinary PR/CI gate.
C1/C2/C3/C5/C6/C8 HOLD. M3 IN_PROGRESS.**

Accepted CI implementation1fa070b99ae559923b29b361e51feb3e2fa2ba06, tree
aeee18671729617209da3ff23fec0337e7b95660, sole parent1b6571fa2251b8cba052382bb04ac5f8479d5a62.
Six allowed paths,+968/-29;286 other leaves exact. New mandatory reusable
native job retains all9 ordinary jobs, caps, pins and actual merge/main source.
Generic PG routes only the3 complete native modules away from shared Compose;
development COPY adds only2 actual workflow inputs. No product scope change.

C0 verified all292 remote bytes/modes, original11/manifest/contract, all11 C6
evidence hashes and292-file source archive. Independent development projection:
9 COPY inputs/182 exact files;134 runner cases+130 subtests PASS, Python3.13.12,
58 frozen versions. Production collect-only preflight:907=802 generic+105 native
PG, disjoint/full union/order;112 carrier=7source+56DB+12API+37runtime,105 actual
guarded consumers, historic105 prefix exact. All3 inventory hashes match C6.
Existing51 tests/assertions and ownership/catalog/reset/carrier AST retained;
83 additions. YAML/20 shell blocks/pins/caps/changed-Python Ruff/format PASS.
Pure source pairing4 components/167functions/45tables/635columns PASS.

| Task / gate | Current disposition |
|---|---|
| C6-M3.1-NATIVE-CONTEXT-CI-R1 | INTEGRATED source; source/unit blocker resolved |
| C0-M3.1-NATIVE-CONTEXT-CI-RUN1 | PREPARED; exact one-use PR/CI approval follows |
| Actual ordinary CI/browser/PG on current candidate | NOT RUN; no runtime acceptance yet |
| Accepted stock112 on af7482d; C8-NC-HOST-01 | Retained VERIFIED LOCAL/TEST / CLOSED |
| M3/account/A08/P01/P05/renewal/collector/A12 | IN_PROGRESS / later gates OPEN; M4 out |

C0 preparation is a docs-only child of1fa070b; exact SHA/tree/PR binding in the
canonical C0 execution comment. Only HANDOFF/register change;290 other leaves
remain exact to accepted source. C0 branch c0/m3-1-native-context-ci-r1;
C6 return branch stays1fa070b. Main e205e22051bc06295758b504d84699652b176c15/schema0012
and stock execution refaf7482dede085bc033e3fee34f9a2425124351ee unchanged.
Approval6262637585 CONSUMED; old stock evidence is not current ordinary CI proof.
Full integration requires real10-job execution, including native and browser.
User owns merge. D1/D2/D3/caps/previous closures retained; IMPL-05 DEFERRED.

### 0.1. C0-M3.1-NATIVE-CONTEXT-CI-RUN1 — first ordinary PR gate

C0 first publishes an exact one-use execution comment with full candidate
SHA/tree/sole parent and current main SHA. Only then open one same-repository
draft PR from c0/m3-1-native-context-ci-r1 to main. This admits one automatic
pull_request/opened run, attempt1. No main/stock-execution-ref move, dispatch,
rerun/retry, concurrent source mutation or merge. C6 source-only task is complete.

The candidate includes the previously reviewed native SQL/API/runtime/host/Console
slice and this CI wiring. CI-R1's own implementation remains the exact6-path delta;
opening the integration PR introduces no new product requirement. Confirm actual
GitHub merge SHA, ordered parents[current main,candidate], and tree equal candidate.
Every job must verify this same merged source, including the reusable native job.

Required actual evidence:
- All9 existing jobs plus1 mandatory native job complete successfully, none
  absent/skipped/continued on error; every retained clean-source gate passes.
- Foundation: full unfiltered unit suite, dynamic exact generic802 PG inventory,
  complete before/after migrations, contracts, deterministic wheels and service
  smoke. All existing commands remain; no permission to bypass/reset a gate.
- Native: real same-repository-pr-merge admission and payload/source identity;
  complete current112/336 phases,105 guarded resets,134 runner+130 subtests,
  fresh typed catalog167/45/635, roles/ACL/verifier, owned logs/cleanup and final
  clean source. Counts are current expected inventories, not a truncation rule.
- Real browser full54=45desktop+9narrow inventory and full frontend suite; both
  complete migration-state lanes, Docker29 compatibility, image/intent shards.
- Verify actual source archives/manifests, run/attempt/job identities, exits and
  artifacts. Preserve failures as observed evidence; do not claim mocks or
  collection as PG/browser execution.
- Keep whole native20min/payload1080s, foundation45/browser25/state25 and every
  existing budget. Resource lifecycle only on disposable owned Actions runners;
  no VM, live Telegram/provider/account/S3/LLM calls, deployment or renewal.

C0 inspects results and issues a bounded disposition. A failing/missing gate blocks
runtime acceptance and user merge; no automatic retry, budget increase, broad CI
optimization or reopening of unrelated accepted findings. A08/renewal/collector/
account/A12 and deployment remain separately scoped after this integration gate.

## История — 0. HOST-R2 принят, paired stock112 PASS; CI integration / 2026-10-19 UTC

[C0 acceptance6262637585](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6262637585);
[C0 stock acceptance6262882269](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6262882269).
**C6 CI-R1 ACTIVE/source-only; C1/C2/C3/C5/C8 HOLD. M3 IN_PROGRESS.**
Текущая работа — подключение уже написанных проверок к обычному CI.
Product scope не меняется; broad CI optimization/IMPL-05 остаётся DEFERRED.

| Task / finding | Current disposition |
|---|---|
| C8-NC-HOST-01/P2 | CLOSED LOCAL/TEST; exact existing command-key contract restored |
| C6 HOST-R2 | INTEGRATED source; C0 independent278/278 unit PASS |
| Native DB/API/runtime/operator carrier | VERIFIED LOCAL/TEST on af7482d;112/112 actual PASS |
| C8 independent source review | COMPLETE/HOLD; only actionable finding closed |
| C6-M3.1-NATIVE-CONTEXT-CI-R1 | IN_PROGRESS/source-only; same task, six-path scope including development workflow input |
| Unified browser/full ordinary CI/deployed host | NOT VERIFIED; next exact C0 execution after CI-R1 review |
| Account/A08/P01/P05/renewal/collector/A12 | Later gates OPEN; M4 out |

Accepted implementation af7482dede085bc033e3fee34f9a2425124351ee, tree
212f753f0cfc21ea53fab103349bb8e4d36971c6, sole parent0d3d089727fe6652b80c2695ab4d394044460a08.
C0 checked all 292 remote bytes/modes, two-path+154/-3,290 protected leaves,
old setup-test prefix, original11/manifest/full contract unchanged. Actual C0
Python 3.13.12 setup+egress278 PASS/8.44s,128 ASCII/66 valid/0 mismatch, pure source
pairing: 4 components/167functions/45tables/635columns. All 10 C6 evidence hashes
and 19 old-pattern RED failures/33passes checked. Unchanged C8/frontend evidence
remains tied to2b1d3cac; it is not fresh af7482d frontend/browser execution.

Actual [run39220536676/attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/39220536676),
job117954530143, exact af7482d/tree above:112/112=7source +56DB+12API+37runtime,
all 336 phases PASS,105 guarded reset proofs;51 runner tests+130subtests PASS.
Independent installed 167 typed functions/45tables/635columns, roles/ACL/private
verifier, full source archive and owned cleanup/final clean source all PASS.
Native carrier 687.740s; whole receipt
720.597s within unchanged20 min.
Profile c045a59f86201a244ed0d43fbe22aa8cd72fddd346d770706c6ab3b92ee9a411 retained.
Approval6262637585 CONSUMED ONCE; execution ref now af7482d. No rerun/ref permission.

Integration wiring blocker confirmed from source and collection, not a full-CI
failure claim: check_backend.sh selects907 PG cases=802 ordinary+105 owned-native;
Compose checks has neither native reset opt-in nor owned-host administrator URL.
The native workflow currently triggers only on the special C0 stock ref. CI-R1
must route these 105 complete cases through a mandatory owned native job and
retain all 802 ordinary cases and all 9 existing jobs. No reset bypass or skips.

[C6 blocker6263355900](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6263355900)
accepted by [C0 scope disposition6263490094](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6263490094).
C6 returned unchanged75182546af178c5749d46fc6bb0c67befc665f0c/tree
7eec2f17159ede4f252c78fa23cb6b7c5b9a070d: CI implementation not yet written.
Development checks image lacks workflow source read by two retained unit tests.
C0 independently rebuilt8 COPY inputs/180 exact files: both tests FAIL with
FileNotFoundError; adding only two actual workflow files/182 files gives2 PASS.
C0 checked9 C6 evidence hashes; C6 baseline51 cases+130 subtests PASS retained.
This is source/unit projection evidence, not Docker or ordinary full-CI execution.
Same CI-R1 scope extends to6 paths: only one development-stage COPY is added to
infra/Dockerfile.backend; runtime/toolchain/pins/locks/Compose stay frozen.
The final complete runner suite must also pass against final development inputs.

Continuation C0 preparation is docs-only with sole parent
75182546af178c5749d46fc6bb0c67befc665f0c; exact SHA/tree in the canonical task
comment. Only HANDOFF/register differ;290 other leaves equal accepted af7482d.
Branches c0/m3-1-native-context-ci-r1 and c6/m3-1-native-context-ci-r1.
Main e205e22051bc06295758b504d84699652b176c15/schema0012 and closed/merged PR34
remain unchanged. Prior stock105/5d98651 and approvals retained as history only.
Contract9/Q01/MATERIAL11, all prior closures/D1/D2/D3/caps retained. User owns merge.

### 0.1. Exact C6 CI integration task

C6-M3.1-NATIVE-CONTEXT-CI-R1 — connect the accepted native carrier to ordinary integration CI; source-only.

Why this task exists: scripts/check_backend.sh currently executes unfiltered
pytest -m integration, which collects the 105 native PG cases. Their real shared
reset_disposable requires ASM_NATIVE_TEST_ALLOW_RESET=1, a private administrator
URL to postgres and the same 127.0.0.1 owned cluster as runtime/migrator. The
ordinary compose checks service has neither reset variable and uses postgres-test,
not the dedicated owned host lane. The separate native workflow currently runs
only on c0/m3-1-native-context-db-stock-r1. Consequently the native carrier must
be wired as a separate mandatory job before ordinary full CI can be accepted.
Independent C0 collection on af7482d confirms 907 selected integration cases:
802 retained generic PG cases plus105 native PG cases, no fixture execution.
This is source-confirmed integration wiring, not an executed full-CI failure,
new product functionality, or the deferred broad CI optimization/IMPL-05.

Repository Elefesys/ai-service-manager. Separate task branch
c6/m3-1-native-context-ci-r1 from the exact preparation SHA/tree in this comment.
C0 preparation changes only docs/tasks/M3_HANDOFF.md and docs/TASK_REGISTER.md;
all 290 other leaves equal accepted af7482dede085bc033e3fee34f9a2425124351ee.
Read current HANDOFF/register, AGENTS, canonical Spec/ADR/MVP/Plan M3,
M3_CONTRACT §16–16.20 and this C0 acceptance. No shared checkout or cache assumption.
C1/C2/C3/C5/C8 HOLD; C6 is active only for this bounded task.

Only these 6 existing files may change (same CI-R1; C0 disposition6263490094):

- .github/workflows/ci.yml
- .github/workflows/native-context-db.yml
- scripts/check_backend.sh
- scripts/native_context_db_catalog.py
- tests/test_native_context_db_runner.py
- infra/Dockerfile.backend — development-stage COPY below only

The sixth path is limited to adding this exact input before development CMD:

```dockerfile
COPY .github/workflows/ci.yml .github/workflows/native-context-db.yml ./.github/workflows/
```

No other Dockerfile line/stage/pin/toolchain change. Preserve unfiltered generic
unit selection and actual workflow-source assertions; no synthetic file inputs.

Required behavior:
1. Ordinary pull_request-to-main and push-to-main verification must contain a
   dedicated native job using the existing owned stock runner, pinned actions,
   DB image, frozen Python 3.13/uv0.10.0 and complete current MODULES. Prefer
   reusing the existing workflow rather than duplicating resource lifecycle.
   Preserve the existing explicit C0 stock-push route and its source guard.
   No workflow_dispatch, pull_request_target, secrets/write permissions,
   arbitrary checkout input, arbitrary ref/event/resource adoption or lab fallback.
2. Admission must distinguish existing stock push, actual same-repository
   pull_request-to-main merge checkout, and actual main push. Bind HEAD/tree,
   actual event/ref/run/attempt and source archive consistently; validate event
   payload/target and reject malformed/mismatched/unapproved routes before any
   Docker/resource action. A reusable caller event retains its real identity;
   never label a PR as stock push. Event metadata remains test-source identity,
   not C0 deployment approval or drain/deployed-process attestation.
3. The generic integration command must not execute the 3 destructive native PG
   modules against the shared Compose DB. Route the complete modules to the
   native job; do not grant its reset opt-in/admin credentials to generic checks.
   All other generic unit/integration tests, complete lifecycle before/after PG,
   contract export, reproducibility and service smoke remain unchanged. Preserve
   every native test/assertion and all 112 current carrier IDs/order. No skips,
   xfail, -k filtering, partial cases, selection based only on a stale total,
   continue-on-error, failure masking, broad ignores or replacement of real tests.
   A source/collection guard must prove the partition has no lost PG cases and
   only the exact 3 native modules leave the generic integration selection.
4. Reuse all ownership/nonce/container/volume/server/login guards, isolated
   child-only credentials,105 guarded resets, full catalog/ACL comparison,
   complete phase evidence, sanitization, owned-only cleanup and clean-source
   checks. No source/schema readiness override. Real browser remains the normal
   full job;54=45desktop+9narrow is the current expected inventory, not execution.
5. Preserve all 9 existing CI jobs and their checks/budgets/commands; the native
   gate is additional. Whole native job stays20 min including prep/cleanup/upload,
   payload1080s reserve; foundation45/browser25/state25 and every prior transport
   and migration budget remain exact. No CI optimization/retry/cache redesign.
   Publish useful exact source/inventory/phase/result/catalog/cleanup artifacts
   on success or failure. Overall integration cannot be accepted if this job
   is skipped, absent, failed, or uses a different source from the other jobs.

Bounded local verification only:
- Python 3.13 and frozen uv.lock/dev; compile/Ruff/check-format changed Python,
  mypy backend/src only if a production typing dependency changes.
- Complete tests/test_native_context_db_runner.py, preserving prior 51 cases/
 130 subtests and explicitly count additions. New meaningful negatives cover
  event/repository/ref/base/merge-source mismatches before resource creation,
  actual identity in evidence, exact test partition/lost module, payload and
  cleanup failure propagation. Mock seams are local unit evidence only.
- YAML parse, pinned actions/permissions/caps and shell syntax for both workflows
  and check_backend.sh; verify reusable event semantics from workflow source.
- Independently project the final development COPY inputs using actual committed
  bytes/modes, including both workflows, and run the complete final runner unit
  module there: retained51 cases/130 subtests plus additions. No fake inputs or
  skips; demonstrate the source tests read the copied files and runtime/toolchain
  Dockerfile lines remain exact. File/unit proof is not Docker/full-CI evidence.
- Collection-only full native MODULES112/105 shared guarded consumers, retained
  old105 ordered prefix; collect the generic integration partition and prove
  disjoint PG execution sets and complete union (current907=802+105).
  Account for the7 source tests in the dedicated112 separately from PG105;
  no fixed count that silently permits dropped/new tests. No fixture execution.
- Exact allowlist diff, frozen original11/contract/SQL/API/frontend/locks/compose/
  images and protected leaves, clean final checkout; pure source pairing all 4
  components: 167functions/45tables/635columns on the published final source.

Do not edit product code, test fixtures/migrations/DDL, public contracts, locks,
base image pins, Compose, other tests/docs or shared runtime settings. The sole
Dockerfile exception is the exact development COPY above. If these6 paths
cannot preserve the complete gate, return a precise blocker before expanding.
No PG/Docker/services/resource inspection/start/reuse/cleanup, browser/provider/
account/VM/S3/LLM/policy CLI, Actions/dispatch/rerun/execution-ref/new PR/full CI/
main/merge/deploy/live/renewal or other chats/agents. Source-only permission does
not authorize execution of the newly admitted routes. C0 will inspect the source
and issue the exact first ordinary CI/PR execution separately; user owns merge.

Publish only the task branch and one REVIEW return to PR34 with exact commit/
tree/parent,6-path allowlist diff, source/inventory/guard proof, full actual commands/exits/
counts and explicit actual PG/browser/Actions NOT RUN. Then C6 HOLD. No task
comment/PR-body/C0-doc/other-ref changes. Existing findings stay closed unless
new contrary evidence is actually demonstrated.

## История — 0. Текущий шаг C0 — C8 review принято; точечное исправление C6 HOST-R2 / 2026-10-19 UTC

[C8 return6260761693](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6260761693);
[C0 disposition6260873892](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6260873892).
**C6 HOST-R2 ACTIVE/source-only; C1/C2/C3/C5/C8 HOLD.**
C8 independent review COMPLETE, outcome CHANGES REQUESTED: один подтверждённый P2.
C5 CONSOLE-R1/R2 и C6 HOST-R1 остаются INTEGRATED source; whole host/Console runtime
NOT VERIFIED. M3 IN_PROGRESS. Исправляется соответствие уже принятому command-key
contract, без новой функции или расширения M3.

### 0.1. Disposition and evidence

| Task / finding | Current disposition |
|---|---|
| C8-M3.1-NATIVE-CONTEXT-HOST-CONSOLE-R1 | Review COMPLETE; CHANGES REQUESTED, one confirmed P2; C8 HOLD |
| C8-NC-HOST-01/P2 | OPEN; NativePolicyRequest uses narrower billing key grammar; owner C6 |
| C6-M3.1-NATIVE-CONTEXT-HOST-R2 | IN_PROGRESS/source-only; exact two-path correction below |
| C5 CONSOLE-R1/R2; C6 HOST-R1 | Prior INTEGRATED source retained |
| C0-NC-UI-01/02 | CLOSED LOCAL/TEST retained |
| Prior native DB/carrier/runtime findings | Prior acceptance6254556203 and closures retained |
| Actual unified host/PG/browser/full integration/account | NOT VERIFIED; separate C0 gates after correction |

Exact reviewed combined source2b1d3cac2c453e1d35242c2c682442625aeefdd9/tree
663277ba89db5aaa743cfd653227dab502fb0593, ordered parents C5
208dd68959d9ee15e4ba9a746cac38d0f1806935 then C6
9bd76b30069617ceadf5e35de046505255600cca. C0 freshly checked all292 remote/local
bytes/modes, exact parents/tree and clean status; C8 made no tracked source change.

C8 found NativePolicyRequest.key:CapabilityKey, whose billing grammar requires
lowercase first letter and forbids uppercase anywhere. M3_CONTRACT§16.7.1 and
frozen0013 policy RPC/receipt CHECK use existing ASCII[A-Za-z0-9._:-]{1,128},
matching asm.messaging.models.command_key. Valid uppercase/digit/punctuation
requests are rejected before source/DB checks. Saved-key replay likewise fails
DTO validation before receipt lookup; this recovery impact is a source trace,
not an actual PG replay execution. Changing the key is not recovery.

C0 actual pure probe on exact2b1d3cac with Python3.13.12/verified local imports:
same9 vectors reproduce4 mismatches;128 single-ASCII vectors give66 allowed by
contract/codec versus26 by host DTO,40 manifestations of the same defect.
No SQL/CLI/service call. Probe SHA256
dbf890293c791f864a6541f9df6762fb6a54ee21a764c6224dc8c1b064402291.
This is RED discrepancy confirmation, not a corrected-source PASS.

C0 checked all8 C8 published evidence hashes and report contents. C8 actual:
345/345 Python=36foundation+82setup+144egress+83browser-fixture,0fail/error/skip;
359/359 frontend/10files; typecheck/build PASS; full list54=45desktop+9narrow;
compile/Ruff/format13 PASS; mypy64 PASS; native112 and host20 collection only.
All105 PG consumers use the current guarded fixture; old105 ID order hash
9881ab5a77aca51a7d6c66737c352055cd4f037acf156e55f265cedeabb24b1a retained.
C8 pure real clean source pairing: api/worker/scheduler/console,167functions/
45tables/635columns, private verifier body527fce5681d5345369cd88b555a302df6d305ef8566cf12a666198eb64a6f4ac.
These are verified C8 report artifacts, not new C0 suite executions. Independent
review has no additional actionable finding in the other reviewed risks.
Actual installed catalog/readiness/operator/browser/rollout was NOT RUN.

C8 evidence SHA256: units.xml7e38015a6a92972847a57ffc88a7c0c6b7bd28a2cf8525e743375a8c0fb4dc01;
Vitest9d15efa4b8da8e57bfcd3222038dffc299bb0349edfd09668837cf4ccf860be8;
native collectionf5ddb680c895ab5e0a1c9379b60cd38ca246041b9fc2e759ddd2d88441da89fa.
Complete inventory/commands and limits in the exact C8 return/C0 disposition.

New preparation is docs-only, sole parent2b1d3cac; only HANDOFF/register differ,
290 other leaves unchanged/292 total. Full new SHA/tree is in the canonical C0
task comment; branches c0/m3-1-native-context-host-r2 and c6/m3-1-native-context-host-r2.
No implementation fix has been applied by this preparation. Original11=canon=
SOURCE_MANIFEST; full contract SHA256fe2eb4ef2469ccb14b7147017c3c81066cde1b8a6ad60acbf73922a15e3ace5f;
all SQL/API/frontend/locks/CI/runner unchanged. Native profile remains
c045a59f86201a244ed0d43fbe22aa8cd72fddd346d770706c6ab3b92ee9a411.

### 0.2. Exact C6 correction task

**C6-M3.1-NATIVE-CONTEXT-HOST-R2 — correct C8-NC-HOST-01/P2; source-only.**

Repository Elefesys/ai-service-manager. Branch c6/m3-1-native-context-host-r2.
Start from the exact C0 preparation SHA/tree in the canonical task comment.
Its sole parent is reviewed combined source2b1d3cac2c453e1d35242c2c682442625aeefdd9,
tree663277ba89db5aaa743cfd653227dab502fb0593. The preparation changes only
HANDOFF/register; all290 implementation/other leaves remain exact. C0 branch:
c0/m3-1-native-context-host-r2. Separate clean checkout; do not start from the
old standalone C6 branch or a moving sibling. No shared-disk/dependency assumption.

Read current HANDOFF/REGISTER, AGENTS, IMPL-001, original11/SOURCE_MANIFEST and
applicable Spec/ADR/MVP/Plan M3; M3_CONTRACT§16.7.1 and retained§16–16.20.
Read C8 return6260761693 and C0 disposition6260873892; retain acceptance6260443971,
C5 return6260302288, C6 return6255240519 and stock acceptance6254556203.
C8 review COMPLETE/HOLD; C1/C2/C3/C5/C8 HOLD. C5/C6 R1 source integration retained;
whole host/Console runtime remains NOT VERIFIED. No new product requirement.

**Only two existing paths may change:**
- backend/src/asm/telegram/provisioning.py — NativePolicyRequest.key validation
  and the necessary import/local validator only.
- tests/test_m2_3_setup.py — focused command-key regressions and a local helper
  only if required. Retain every existing case/assertion and old behavior.

C8-NC-HOST-01/P2: the billing CapabilityKey currently requires a lowercase first
letter and excludes uppercase anywhere. Accepted command grammar is exact
ASCII [A-Za-z0-9._:-]{1,128}, already implemented by asm.messaging.models.command_key
and frozen0013 policy RPC/receipt CHECK. C0 independently reproduced all4 reported
valid-key rejections and confirmed the existing source/recovery requirement.

Use strict existing command-key validation for this DTO (reuse the existing
codec with bounded validation-error translation as needed), exact fullmatch.
Keep repr=False, hide_input_in_errors, strict/frozen/extra-forbid model behavior,
and the same key bytes through JSON cloning/commit/current/replay. No trim,
case conversion, Unicode normalization, generated prefix, alternate key or retry.
Do not edit/widen shared billing CapabilityKey or the shared messaging codec.
All surrounding source/catalog/binding/role/drain/CAS/fingerprint/receipt/current
checks and time bounds remain intact. No SQL or new DTO/API contract.

Regression evidence must cover valid lowercase, uppercase/mixed case,
digit-leading canonical UUID, each allowed punctuation at the first position,
one-character boundary and128-character uppercase key. Preserve the value
exactly after Python/JSON validation and the immutable clone used by host paths.
Exercise key preservation through an existing unit host-RPC/recovery seam with
a formerly rejected valid key; do not add a fake successful PG claim.
Reject empty,129 characters, embedded/leading/trailing whitespace including
terminal newline, non-ASCII, forbidden ASCII and non-string/coercible inputs.
Check private key canaries remain absent from repr/bounded errors. Existing
saved-receipt replay/current-failure/CAS/redaction tests must remain meaningful.
Keep the pre-fix reproducer as RED evidence; new tests must fail on the reviewed
parent for the actual grammar mismatch and pass on the correction.

**Required bounded local verification on the final published source:**
1. Python3.13 and frozen uv.lock/dev, uv0.10.0. Existing isolated environment or
   isolated frozen restore is allowed; no dependency re-resolution/lock edits,
   global installs or different Python minor. Record versions and actual import
   paths from this checkout. External caches/logs/pycache/pytest basetemp only.
2. Compile, Ruff and check-format for the two changed Python files; mypy backend/src.
3. Complete tests/test_m2_3_setup.py and tests/test_telegram_egress.py:
   baseline226=82+144 plus explicitly counted new vectors;0fail/error/skip.
   Include the new key tests in these complete modules. No need to rerun unchanged
   frontend/foundation/browser-fixture/601 migration unit suites solely for counts.
4. Collection only: current native_context_db_catalog.MODULES112=7+56+12+37,
   same105 guarded PG fixture consumers and exact old105 ID order retained;
   tests/test_telegram_egress_postgres.py20 with --collect-only -q
   -o 'python_classes=Test* TelegramEgress*'. No PG/service fixture execution.
5. On a clean final checkout, pure native_host_profile(final_commit,final_tree)
   then native_host_source(NativeHostApproval) must pair all4 source components
   and unchanged native167functions/45tables/635columns. Do not print the private
   approval/request. This proves source pairing only, not drain/deployed processes.
6. Verify exact diff/allowed paths, all290 other leaves/modes, original11 and
   full frozen contract/SQL/API/frontend/locks/CI/runner. No weakening, skips,
   retries, sleeps, enlarged budgets or assertions removed.

If a required runtime cannot be restored, report exact NOT RUN rather than use
an old commit PASS, syntax-only substitute or alternate Python minor.
Unchanged C8 checks remain retained evidence at2b1d3cac, not fresh R2 execution.

**Not authorized in this task:** any other source/tests/docs/contract/OpenAPI/
migration/lock/workflow edits; policy CLI check/commit/current (even check reaches
DB); PG/Docker/service/lab/resource inspection/start/reuse/cleanup; real browser/
API/provider/account/VM/S3/LLM; Actions/execution-ref/dispatch/rerun/full CI/new PR/
main/merge/deploy/live/renewal/other chats/agents. Do not move prior C0/C8 refs.
No0014 or applied migration edits. Preserve Contract9/Q01/MATERIAL11/D1/D2/D3,
S600/P720/fixed120/+480/S+1200/cleanup90/state25/browser25/foundation45/stock20m/
request3s60s10s and prior worker caps. No new acceptance rule or feature.

Publish only the task branch through GitHub, then return one REVIEW comment to
PR34 with exact commit/tree/parent, two-path diff, retained leaves/contract proof,
pre-fix RED/new regression results, full commands/exits/counts/import paths and
explicit actual PG/browser/host rollout NOT RUN. Do not update C0 docs, PR body,
other task comments or remote refs. Then C6 HOLD. C0 owns review, closure and the
next separately authorized actual paired gate; user owns merge.

### 0.3. Remaining boundaries

Prior stock105 run39160997284/attempt1 remains VERIFIED LOCAL/TEST only for
5d98651d2c34314724a12283d1741e73594e16b8/treea1989f20284c201bfd58bafe12c174544f1eb3c1.
Approval6254432619 CONSUMED ONCE; execution branch stays5d98651, no new run/ref
permission. Main e205e22051bc06295758b504d84699652b176c15/schema0012; PR34 closed/merged.
C0 reviews the correction before issuing the next exact actual paired gate.
Account/A08/P01/P05/renewal/collector/A12 remain later gates; M4 out, broad
CI optimization DEFERRED. User owns merge.

## История — 0. Текущий шаг C0 — C5+C6 source integration; независимое C8 review / 2026-10-19 UTC

[C0 acceptance6260443971](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6260443971).
**C8 ACTIVE/read-only source review; C1/C2/C3/C5/C6 HOLD.**
C5 CONSOLE-R1/R2 и C6 HOST-R1 INTEGRATED source на общем C0 checkpoint.
Whole host/Console runtime NOT VERIFIED; M3 IN_PROGRESS. Это предусмотренная
независимая проверка уже реализованной функции, без нового product scope.

### 0.1. Принятые исправления и объединённые исходники

| Item | Current disposition |
|---|---|
| C0-NC-UI-01/P2 | CLOSED LOCAL/TEST: Response/APIResponse type pairing; browser emitted JS unchanged |
| C0-NC-UI-02/P2 | CLOSED LOCAL/TEST: two submits reach connected form; one frozen intent/request; complete replacement/current-read assertions PASS |
| C5 CONSOLE-R1/R2 | INTEGRATED source; required frontend checks independently PASS |
| C6 HOST-R1 | INTEGRATED source; reviewed host/readiness/operator code and checked C6 unit evidence; actual paired gate pending |
| C8 independent source review | IN_PROGRESS; exact assignment below |
| Actual unified host/PG/browser/full integration/account | NOT VERIFIED / separate C0 gates |

C5 final208dd68959d9ee15e4ba9a746cac38d0f1806935/tree
b436c1bcb11e0e22c4ca0553dd8527dfc26a0b88, sole parentc5605521b8b730a3bd1c20b6160e4fb4afe8d204.
R2 changes exactly2 test paths,+31/−5; all290 other leaves retained.
C0 independently checked all292 remote/local bytes/modes. The browser change is
type-only: emitted JS SHA256ce4b903701565f1070bfd99e07bd374e9fb00c4360beba6d91fa6c3343bc20d1
matches before/after with TypeScript5.9.3. The amended callback retains/strengthens
both confirmations, full CAS, one immutable intent/request, no CONTROL/send,
pending state and fresh current read after receipt. Historical R1 RED retained.

C0 actual checks on exact C5 final: Node24.19.0/npm11.9.0 locked167 packages,
typecheck PASS; complete10 Vitest files359/359 PASS in6.24s,0fail/skip;
build PASS40modules/1.08s; full Playwright list54=45desktop+9narrow PASS.
List-only inputs are inert private synthetic files, not browser/PG evidence.
C0 logs SHA256: typecheckb24fec26336d05929eedd0e048a02eb5099df83b5021c72ba8f3180c98015940;
Vitestca46ddf257d9c4ab2ab96afd3de80ad2fadf3a01e7f28effdfe61f90f05a0b24;
builddd1207206d752c7851c04aff9cacfeac983e54abb1284b55f990eaba918592f9;
listf4c9bf73b970fceb83efcbd0d0f2da54815e1cd59c6b3ae17c4907b3d509d979.

C0 combined commit has ordered parents C5 final208dd68959d9ee15e4ba9a746cac38d0f1806935
then C6 HOST-R1 9bd76b30069617ceadf5e35de046505255600cca
(tree8124ef7664434a2e999502daff4b1f5d856bab0f). All24 C5 and12 C6 implementation/
test/runbook path blobs are exact returns; no additional implementation edit.
Only C0 HANDOFF/register are changed by consolidation. Relative to common
prepared8d1ba99:38paths including2 coordination docs;292 leaves,254 old leaves exact.
Original11=canon=SOURCE_MANIFEST; full contract SHA256
fe2eb4ef2469ccb14b7147017c3c81066cde1b8a6ad60acbf73922a15e3ace5f;
SQL/API/OpenAPI/dependencies/locks/CI/runner frozen. Full final SHA/tree in canonical
C0 acceptance/task binding; branches c0/m3-1-native-context-host-console-r2 and
c8/m3-1-native-context-host-console-r1. No moving sibling base.

C6 report digests previously independently checked:863unit=36foundation+82setup+
144egress+601migration,0fail/error/skip;112nativecollection/20hostcollection.
These are C6 report evidence, not a fresh combined-source execution.
All prior105 ordered IDs/hash9881ab5a77aca51a7d6c66737c352055cd4f037acf156e55f265cedeabb24b1a
retained;7 host cases added. Native profilec045a59f86201a244ed0d43fbe22aa8cd72fddd346d770706c6ab3b92ee9a411,
167typedfunctions/45tables/635columns unchanged. Runtime private verifier body
527fce5681d5345369cd88b555a302df6d305ef8566cf12a666198eb64a6f4ac remains pinned.
Actual new readiness/operator integration is not inferred from old stock PASS.

### 0.2. C8 exact independent task

**C8-M3.1-NATIVE-CONTEXT-HOST-CONSOLE-R1 — independent source/security/recovery review; read-only.**

Repository Elefesys/ai-service-manager. Branch c8/m3-1-native-context-host-console-r1.
Start only from the exact C0 combined SHA/tree in the canonical task binding.
Ordered parents: C5 208dd68959d9ee15e4ba9a746cac38d0f1806935 then
C6 9bd76b30069617ceadf5e35de046505255600cca. C0 branch:
c0/m3-1-native-context-host-console-r2. Separate clean checkout; no moving sibling
base or assumption of shared files/dependencies. C5/C6 are INTEGRATED source,
not whole runtime VERIFIED. C1/C2/C3/C5/C6 HOLD.

Read current HANDOFF/REGISTER, AGENTS, IMPL-001; supplied original11 and exact
SOURCE_MANIFEST; applicable Spec5.8–5.14/5.12.1/18.5–18.9, ADR002–007/024–026/
180/266/267, MVP GJ-G/J and variants, Roadmap/Plan M3. M3_CONTRACT§16–16.20 and
retained MATERIAL§15; current C0 acceptance6260443971, review6260097657,
C5 return6260302288, C6 return6255240519 and stock acceptance6254556203.

**Read scope:** all code/contracts needed to assess the combined changed risk.
Primary implementation delta is the exact36 paths in the C5/C6 returns:
C6 foundation/provisioning/operator helpers/runbook/readiness+host tests;
C5 HumanContextPanel/API and tests, ConversationControl/Messaging, Escalations/
Audit consumers and tests/styles, browser control spec and three fixture files.
Only two additional paths are C0 HANDOFF/register. All original SQL/API/OpenAPI,
dependencies/locks, CI/runner and the prior accepted DB/runtime slice are frozen.

**Write scope:** no tracked repository source, tests, contracts, docs, locks,
workflow, branch ref or PR metadata edits. External scratch notes/probes/reports
and caches only; final checkout must remain exact/clean. Report findings with
specific path/function, violated existing requirement, reproducer/finite trace,
impact, severity and proposed owner. Do not silently fix the implementation,
create a new acceptance rule or reopen prior findings without a concrete new defect.

1. Verify provenance and pairing. Compare exact ordered parents, all292 source
bytes/modes and the36 returned implementation paths; C0 changed only two docs.
Original11=canon=manifest and frozen contract/API/SQL/locks remain exact.
Verify actual imports from this checkout, not an old editable install/pyc.
Exercise pure source functions native_host_profile(approved_commit,approved_tree)
and native_host_source(NativeHostApproval): real clean unified Git source,
all api/worker/scheduler/console components,167 functions/45 tables/635 columns.
This source proof does not approve deployed binaries, drain or policy activation.
No full private approval object/request/credential output.

2. Runtime/host review: exact0013 readiness before API admission and Worker/
Scheduler work, actual safe runtime role,3s bound, pinned catalog verifier body/
metadata/ACL before executing its catalog-only SELECT. Runtime must not receive
EXECUTE on the private migrator capability. Independently inspect how full source/
installed function OIDs/definitions/columns/ACL/roles are checked; no trust in a
self-reported digest alone. Keep historical0012 material132functions/42tables
and historical0007 switch separate. Both named readiness test exceptions retain
explicit old0012 refusal, and all other old native definitions/assertions remain.

3. Operator review: closed LOCAL/TEST DTO, actual session_user=current_user
asm_migrator/READ COMMITTED/database, approved clean source/components and real
scoped binding/catalog checks; explicit drain attestation is not process discovery.
Only the accepted capability mutates policy/receipt/Audit; CAS/full fingerprint,
no-op, PAUSE/reenable and bounded work must retain contract semantics. Validated
receipt escapes only after commit; failed separate current read preserves it.
Old source-tree replay requires stored request evidence; a fresh old-tree command
must fail. Saved ENABLE receipt must not overwrite current PAUSED. Read-only retry
must not create a new key/POST. Private file/lock/symlink/ownership/diagnostic
handling; no Telegram HTTP, billing initialization, implicit activation or renewal.

4. Console review against accepted Python/OpenAPI: exact closed unions/fields/
timestamps/UUID/decimal/Unicode/preview/cursor/scope checks; complete serialized
UTF-8 body <=4096, full CAS and receipt binding. Separate saved full context,
replacement and provider observations; explicit replacement+attestation and
separate Resume. OFF_UNUSED/ON/PAUSED and conservative coverage/hold/UNKNOWN
display must preserve manual work/product authorization. Memory-only intent is
actor/ws/C/Client bound; two-tab stale CAS, lost ACK/session/CSRF, old receipt vs
new current R, valid200+failed GET, revoke and late cross-scope responses must not
grant authority, expose old context or automatically POST. Audit/context_hold/
control-error pairing remains strict; no owner policy toggle, fake completeness
or M4/native image authority. Check C0-NC-UI-01/02 closure without weakening tests.

5. Browser carrier review is source-only: finite native_happy/native_narrow
fixtures use the real SQL capability, not successful authority DML/fake receipts;
existing pending-image fixture stays genuinely pending and last;127 seed events
remain below128. All54 browser cases/assertions retained, real network/drop/delay
seams are distinguished from mocked successful business results. Native cases
require the later clean-source paired stack; no host rollout claim from fixture
source_tree/drain fields. Review compatibility with existing full-suite collection.

**Local checks permitted/required for this source review:**
- Isolated Node24/npm environment from exact package-lock (npm ci --ignore-scripts
  --no-audit --no-fund allowed if absent). No upgrades/new library/global install/
  browser download. Typecheck; complete10 files below; external frontend build;
  full Playwright list54=45desktop+9narrow. Use only inert external private
  list-input files described in the preceding C5 R2 task, never account credentials.
- Existing or isolated restored Python3.13 environment from frozen uv.lock/dev
  dependencies using the locked uv toolchain; no dependency re-resolution/lock
  edits or global installs. Record exact interpreter/distributions/import paths.
  Compile and Ruff/check-format for the13 changed Python paths; mypy backend/src.
- Complete four directly affected Python unit modules:
  tests/test_foundation.py, tests/test_m2_3_setup.py,
  tests/test_telegram_egress.py, tests/test_m2_4_browser_fixture.py.
  Current expected collection345=36+82+144+83. Do not rerun the unchanged601-case
  migration unit module just for counts; its same-source C6 evidence is retained.
- Full native four-module collection only:7source+56DB+12API+37runtime=112.
  Use current native_context_db_catalog.MODULES and independently verify all105
  PG-fixture consumers use the guarded current shared native fixture/reset;
  all prior105 IDs/order retained (7 new host cases appended).
  Host PG collection20 using the same full class collector as C6:
  python -m pytest tests/test_telegram_egress_postgres.py --collect-only -q
  -o 'python_classes=Test* TelegramEgress*'.
  No test selection may execute an actual PG/service fixture.
- Source catalog/profile and frozen-input checks are local only, no DB connection.
  Keep caches/builds/logs/basetemp outside checkout. If a required runtime cannot
  be restored, report the exact unavailable check; do not substitute syntax-only
  probes, another Python major/minor, mock PG or a PASS from another commit.

Exact frontend test scope:
npm run test -- src/HumanContextPanel.test.tsx src/human-context-api.test.ts
src/ConversationControl.test.tsx src/conversation-control-api.test.ts
src/MessagingPanel.test.tsx src/messaging-api.test.ts
src/EscalationsPanel.test.tsx src/escalation-api.test.ts
src/BillingPanel.test.tsx src/billing-api.test.ts

**Not authorized:** policy CLI check/commit/current (even check reaches DB),
PG/Docker/service/lab/resource inspection/start/reuse/cleanup, real browser/API/
provider/account/VM/S3/LLM calls, Actions/execution-ref/dispatch/rerun/full CI/new PR/
main/merge/deploy/live/renewal, other chats/agents. No skip/retry/sleep/budget changes.
Preserve S600/P720/fixed120/+480/S+1200/cleanup90/state25/browser25/foundation45/
stock20m/request3s60s10s and all prior Contract9/Q01/MATERIAL11/D1/D2/D3 constraints.

Return one independent REVIEW comment on PR34 then C8 HOLD: exact inspected
SHA/tree/parents, source/evidence comparisons, actual commands/exits/counts,
risk-by-risk disposition, actionable findings (or no findings) and explicit
NOT RUN actual PG/browser/host rollout. A source-only PASS does not close those
gates or the whole M3. C0 owns disposition and the next exact actual gate;
user owns merge. No new product scope.


### 0.3. Remaining execution boundaries

Accepted stock105 source5d98651d2c34314724a12283d1741e73594e16b8/tree
a1989f20284c201bfd58bafe12c174544f1eb3c1/run39160997284/attempt1 remains
INTEGRATED/VERIFIED LOCAL/TEST for that DB/API/runtime slice only:
all315 phases/51runner+130subtests/98guardedresets/catalog/cleanup/clean PASS.
C0-NC-CARRIER-01/02 and C3-NC-RUNTIME-01 CLOSED LOCAL/TEST retained.
Approval6254432619 CONSUMED ONCE; execution ref still5d98651; no new run/ref permission.
Main e205e22051bc06295758b504d84699652b176c15/schema0012 and PR34 closed/merged.
C0 reviews C8 then authorizes the next exact actual paired gate separately.
C8/full integration/account/A08/P01/P05/renewal/collector/A12 remain their own
gates; whole M3 IN_PROGRESS, M4 out, broad CI optimization DEFERRED.

## История — 0. Текущая выдача C0 — два исправления frontend-проверок C5 / 2026-10-19 UTC

[C0 review6260097657](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6260097657).
**C5 CONSOLE-R2 ACTIVE/source-only; C6/C1/C2/C3/C8 HOLD.**
Новых требований к функции нет: исправляются две ошибки тестового кода в рамках
уже выданной Console-R1. M3 IN_PROGRESS. Host/Console whole integration NOT VERIFIED.

### 0.1. Disposition and exact evidence

| Return / finding | C0 disposition |
|---|---|
| C6 HOST-R1 6255240519 | Source review complete; no new source finding; REVIEW/HOLD pending C5 and paired actual gates |
| C5 CONSOLE-R1 6255159597 | REVIEW; required frontend gates FAIL; two narrow corrections assigned |
| C0-NC-UI-01/P2 | OPEN: Response passed to helper accepting only APIResponse, two TS2345 errors |
| C0-NC-UI-02/P2 | OPEN: duplicate-submit test queries already removed form button |
| Old native stock/carrier/runtime findings | Prior acceptance6254556203 and CLOSED LOCAL/TEST retained |

C6 exact9bd76b30069617ceadf5e35de046505255600cca/tree8124ef7664434a2e999502daff4b1f5d856bab0f;
C5 exacte9a5dcbf16fd9d3d7824a2c3d3b3628074d3cc79/tree723869324be6f5627a3d1348d32a55c36e7a2dae.
Both sole-parent8d1ba99c820b42c590408d98043e6963743f77a0.
C0 checked all288/292 actual remote/local blobs/modes, disjoint12/24 changes,
276/268 retained old leaves; original11 and full contract exact. Source-only
combined review indexd460c942752983b127c16309e6486916110e6a68 was not published or
accepted as integration; its complete frontend equals C5 source.

C0 restored exact Node24.19.0/npm11.9.0 frozen dependencies (npm ci --ignore-scripts,
167 packages, no package/lock edit). Actual checks: typecheck FAIL2;
complete10 impacted Vitest files358PASS/1FAIL/359 in6.36s; build PASS40 modules/0.99s;
full Playwright list PASS54=45desktop+9narrow/4files. Initial list lacked private
import inputs and failed; corrected list used inert synthetic files only, no
browser/HTTP/PG execution. C5's earlier syntax/vector probes remain supplemental.

C6 final evidence files independently checked: log SHA256
ac369c6d482d5bb0c1916aba73be0f388afe6aeb1fc2322a5c375b9fcd434208,
XML b4d8dda1e35a823fa1fa09106783aac11eb4abea24fad3e306ede67438c04d50;
863 cases=36foundation+82setup+144egress+601migration,0fail/error/skip.
Native collection112=7source+56DB+12API+37runtime and host collection20 match
reported digests; all105 old IDs/order retained, SHA256
9881ab5a77aca51a7d6c66737c352055cd4f037acf156e55f265cedeabb24b1a.
C0 Python recheck did not start because retained3.13 interpreter targets were
unavailable; NOT RUN. Report-file verification is not a fresh C0 execution.

C6's pinned runtime catalog SELECT, API startup/readiness, explicit trusted policy
operator and all new host carriers still need actual paired verification. No
runtime EXECUTE grant, SQL mutation outside accepted capability, implicit policy
activation or automatic replay/current-state conflation is accepted. Old0012
negative/readiness evidence remains alongside the new0013 positive source cases.
Historical material0001–0012 profile132functions/42tables remains bounded separately;
current native167functions/45tables/635columns/full profile
c045a59f86201a244ed0d43fbe22aa8cd72fddd346d770706c6ab3b92ee9a411 is unchanged.

The R2 preparation is docs-only on C5 e9a5dcb; only HANDOFF/register differ,
290 other leaves exact/292 total. It does not contain C6 changes and is not whole
Console integration acceptance. Full new SHA/tree supplied in the canonical task.
C0 branch c0/m3-1-native-context-console-r2; C5 branch below. Separate clean checkout.

### 0.2. C5 exact correction

**C5-M3.1-NATIVE-CONTEXT-CONSOLE-R2 — fix two frontend test blockers; source-only.**

Repository Elefesys/ai-service-manager. Branch c5/m3-1-native-context-console-r2.
Start only at the exact new C0 preparation SHA/tree in the canonical task binding.
Its sole parent is C5 e9a5dcbf16fd9d3d7824a2c3d3b3628074d3cc79, tree
723869324be6f5627a3d1348d32a55c36e7a2dae. Preparation changes only HANDOFF/register;
the remaining290 leaves are exact C5 R1. This is a reviewed repair base, not
INTEGRATED/VERIFIED whole-Console acceptance. C6 is not incorporated in this base;
do not merge/follow the C6 branch. C0 will consolidate both returns after R2.

Read current HANDOFF/REGISTER, AGENTS, IMPL-001, supplied original11 and their
SOURCE_MANIFEST; applicable Spec5.8–5.14/18.5–18.9, ADR002–007/024–026/180/266/267,
MVP GJ-G/J, Plan/Roadmap M3, M3_CONTRACT§16–16.20. Accepted backend/Python/OpenAPI,
all product behavior, SQL, prior constraints and R1 assertions remain frozen.

**Only two existing paths may change:**
- frontend/e2e/conversation-control.spec.ts — the shared JSON response helper/
  necessary response type import, solely to fix both TS2345 call sites.
- frontend/src/HumanContextPanel.test.tsx — the failing full-replacement/
  duplicate-submit test and a local helper only if needed for that probe.

C0-NC-UI-01/P2: lines152/187 pass Playwright Response from page.waitForResponse
to json(APIResponse). Give the helper its actual supported response union/minimal
JSON interface or use the existing typed safe response path. Preserve
safeDiagnostic, strict receipt parsing, scope/body checks and all54 browser cases.
No any/unknown-as cast, @ts-ignore, tsconfig change or suppressed diagnostic.

C0-NC-UI-02/P2: in test "prefills current text separately, requires both
confirmations and saves one frozen replacement without Resume/send", the second
save() queries a form button already removed by the first pending submission.
Repair the probe against the actual pending state. It must meaningfully prove
that a second attempt cannot create another request or replace the frozen intent,
and then exercise the deferred receipt/current-read completion. Keep explicit
two confirmations, old/current text separation, full replacement, exact frozen
body, one request, no Resume/send, old-text removal, accepted callback once and
cleared intent. Do not merely drop the second-action assertion, click a detached
node with no possible React handler, weaken assertions or change product code
just to preserve a button for the test. No skip/delete/retry/sleep/timeout increase.

**Exact local verification is required.** Node24 with the existing package.json
and package-lock.json; restoring an absent dependency environment with
npm ci --ignore-scripts --no-audit --no-fund is explicitly allowed. Use an
isolated checkout/private cache or external node_modules; verify lock/source
bytes before and after. No manifest/lock edit, package upgrade, new library,
global installation, browser download or service. C0 used Node24.19.0/npm11.9.0,
167 locked packages; lock SHA256
bc4c95ef78ada2e6c2e1eee49974f6d13e865cb62409265c577d06baaa8809ad.

Run and report actual exit codes/results on the final frozen source:
1. npm run typecheck.
2. npm run test -- src/HumanContextPanel.test.tsx src/human-context-api.test.ts
   src/ConversationControl.test.tsx src/conversation-control-api.test.ts
   src/MessagingPanel.test.tsx src/messaging-api.test.ts
   src/EscalationsPanel.test.tsx src/escalation-api.test.ts
   src/BillingPanel.test.tsx src/billing-api.test.ts
3. npm run build -- --outDir <external-evidence-build-directory>.
4. npm run test:e2e -- --list, full existing config; expect all54 cases retained,
   45 desktop+9 narrow. Collection needs ASM_BROWSER_LOGIN,
   ASM_BROWSER_PASSWORD_FILE, ASM_BROWSER_FIXTURE_FILE, ASM_BROWSER_ENV_FILE,
   ASM_BROWSER_MESSAGING_FILE and ASM_BROWSER_COUNTER_DIR. For list-only, private
   files outside checkout may contain an unused synthetic login/password,
   {"billing_fixtures":{},"messaging_fixtures":{}}, empty inventory{}, empty env
   and an empty counter directory. Never use account credentials or start a stack.
   This import/collection input is not fabricated browser/PG execution evidence.

Keep failed R1 facts: typecheck2 errors, Vitest358PASS/1FAIL/359; build/list PASS.
Do not rerun unrelated Python/PG suites for counts; no Python source is assigned.
Preserve all old test cases/assertions; changes to the named failing probe must
be explained, not hidden in a claim of exact AST identity.

Return REVIEW then C5 HOLD: exact commit/tree/sole parent/branch and two changed
paths, retained source/lock/contract hashes, actual commands/results and concise
mapping of each correction to its finding. Normal FF from the prepared head with
expected SHA/force=false; no amend/rebase/force. C0 alone closes findings after review.

No product UI/API/SQL, host/operator, contracts/C0 docs, dependencies, CI/runner/
budget changes; no PG/Docker/services/browser/API/provider/account/VM/Actions/
execution-ref/full CI/new PR/main/merge/live/deploy/renewal or other agents.
If a change outside the two files becomes necessary, return the exact reason to C0.
C6/C1/C2/C3/C8 HOLD. Prior stock105 and closures retained; M3 IN_PROGRESS.
Next after correction: C0 consolidation, independent C8 and exact actual paired gates.
User owns merge.

### 0.3. Retained gates

Accepted actual stock source5d98651d2c34314724a12283d1741e73594e16b8/tree
a1989f20284c201bfd58bafe12c174544f1eb3c1, run39160997284/attempt1:
105/105/all315 phases PASS,51runner+130subtests,98 guarded resets, complete
independent catalog/cleanup/clean-source. Approval6254432619 CONSUMED ONCE;
execution branch remains5d98651. No further run/ref permission.
C0-NC-CARRIER-01/02 and C3-NC-RUNTIME-01 CLOSED LOCAL/TEST on that source.
Main e205e22051bc06295758b504d84699652b176c15/schema0012 and PR34 closed/merged unchanged.
Contract9/Q01/MATERIAL11/D1/D2/D3 and all existing caps retained; M4 out.
C8/actual host+Console/full CI/account/A08/P01/P05/renewal/collector/A12 remain
separate gates. No service or live authorization follows from this correction.

## История — 0. Текущая выдача C0 — stock105 PASS; C6 host/operator и C5 Console / 2026-10-18 UTC

[C0 actual acceptance6254556203](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6254556203).
**C6 и C5 ACTIVE по двум source-only задачам ниже; C1/C2/C3/C8 HOLD.**
Это уже предусмотренные контрактом§16.7/16.9 части выбранной функции.
Новых требований к продукту нет. Native DB/API/runtime slice INTEGRATED/VERIFIED
LOCAL/TEST; whole host/Console application integration not yet accepted; M3 IN_PROGRESS.

### 0.1. Actual accepted checkpoint

Run39160997284/attempt1/job117774086948 SUCCESS, all13 steps SUCCESS:
source **5d98651d2c34314724a12283d1741e73594e16b8**,
tree **a1989f20284c201bfd58bafe12c174544f1eb3c1**,
ordered parents C2 d694e24638ae133fe9412b3f7cde73acb0089be3 then
C3 e4ac5afa12174317b39097de042f131f5820cb74.
**105/105 PASS =7 source+56 DB+12 API+30 runtime**;315 phase reports PASS,
0skip/xfail/deselection. Runner51+130subtests PASS/5.130s.
Native549.027s,receipt579.043s within20m. Approval6254432619 CONSUMED ONCE;
execution ref stays5d98651, no further ref/run permission.

C0-NC-CARRIER-01/02 and C3-NC-RUNTIME-01 CLOSED LOCAL/TEST.
Actual full Audit observer/10 terminal boundary cases+ACK-loss recovery now PASS.
Actual five-status UTC6 history in both timezones/all shapes, strict parsers/
digests/storage/Outbox invariance and unchanged old cases PASS.
Historical39154853068 FAIL92/105 retained; no result erased.

Artifact12149291601,38 files/3034275 bytes,expires2026-10-25;
ZIP SHA25606553fcec3c0b6408c9061bcf4305b03721c0fad80ee5823a389523c0879f6a8.
C0 independently checked all288 archived source bytes/modes, source tar
c891811cff4ed9144eff07604cf94887f3342a221741f22a1650f56b065606b3 and manifest
c2053a6ac06da85c914d218ee063d8b32cf8f0e0172c8be8238a92ac41448ac0.
Exact105 ordered node IDs/hash9881ab5a77aca51a7d6c66737c352055cd4f037acf156e55f265cedeabb24b1a,
98 guarded resets/current shared fixture, actual LOGIN roles/owned resources,
complete catalog, cleanup and final clean tree independently verified.
Actual PG18.6/vector0.8.6/btree_gist1.8/Python3.13.16/uv0.10.0/Docker28.0.4;
57 frozen external distributions, all catalog/carrier/process exits0.

Independent full profile **c045a59f86201a244ed0d43fbe22aa8cd72fddd346d770706c6ab3b92ee9a411**:
167 typed functions/unique OIDs including verifier,45 tables/635 columns/ACL exact.
Nonfunction57e03fe369be4bd03116ce380e37a9b447a2bc1a72e3bbf2a70c7ac08d69e370;
verifier527fce5681d5345369cd88b555a302df6d305ef8566cf12a666198eb64a6f4ac.
This tested source still deliberately refuses0013 at foundation readiness.
C6 must pair that boundary and retain explicit incompatible-reader evidence;
C5 adds the existing specified owner flow. Neither task may activate the feature.

This preparation is docs-only, sole parent5d98651; only HANDOFF/register differ,
286 other leaves exact/288 total. Exact new SHA/tree and branches are supplied
by canonical C0 task bindings. Do not start from a moving sibling branch.
C0 preparation branch c0/m3-1-native-context-host-console-r1.

### 0.2. C6 exact source task

**C6-M3.1-NATIVE-CONTEXT-HOST-R1 — paired schema/readiness and LOCAL/TEST policy operator; source-only.**

Repository Elefesys/ai-service-manager. Branch c6/m3-1-native-context-host-r1.
Start only from the exact C0 preparation SHA/tree in this task's binding; its sole
parent is the accepted stock source5d98651d2c34314724a12283d1741e73594e16b8.
Separate clean checkout; exact commit/tree/original11=canon=SOURCE_MANIFEST.
Read current HANDOFF/REGISTER/AGENTS/IMPL-001, applicable Spec5.8–5.14/18.5–18.9,
ADR002–007/024–026/180/266/267, MVP GJ-G/J, Roadmap/Plan M3 and accepted
M3_CONTRACT§16–16.20, especially§16.7/16.7.1/16.9/16.15.
This is the already planned host/operator completion of native context, not a
new feature or authorization to activate it. C5 has disjoint Console work.

**Exact write set, existing paths only:**
- backend/src/asm/foundation.py
- backend/src/asm/telegram/provisioning.py
- scripts/provision_telegram_test.py
- scripts/prepare_telegram_egress.py
- scripts/test_telegram_egress.sh
- scripts/test_telegram_egress_migration.sh
- tests/test_foundation.py
- tests/test_m2_3_setup.py
- tests/test_telegram_egress.py
- tests/test_telegram_egress_migration.py
- tests/test_telegram_egress_postgres.py
- tests/test_m3_1_native_context_postgres.py — only readiness subpart of
  test_fresh_catalog_exact_security_and_foundation_fail_closed; other bytes frozen.
- tests/test_m3_1_native_context_runtime_postgres.py — only
  test_python_foundation0012_still_refuses_actual_native0013 and append focused
  actual PG host/policy-wrapper cases; all other current definitions frozen.
- docs/runbooks/M2_TELEGRAM_LOCAL_TEST.md

C0 explicitly includes the actual operator CLI and paired foundation/setup/native
readiness tests found in source. No other path without a concrete C0 finding.
Do not edit C0 docs, contract, SQL/migrations0001–0013, native backend/API/parsers,
OpenAPI, C5 frontend/browser fixtures, CI/stock runner/deps/locks/compose/images.
No0014 and no used0013 in-place reapplication.

1. Pair current application/provisioning readiness with exact schema0013, preserving
the frozen tenancy.v1 revision0003 and role/PG18/vector0.8.6 fail-closed checks.
API/Worker/Scheduler must use the same accepted schema boundary before admission.
Keep historical0012 MATERIAL profile/reader/recovery semantics exact and introduce
a distinct0013 native profile (167 typed functions/unique OIDs,45 tables/635 ordered
columns, exact bodies/security/ACL). Do not wildcard revisions or widen a legacy
profile. Current material_source_profile scans all migration files and refuses0013:
bound the retained0012 source inventory explicitly, preserving its132 functions/
42 tables/all assertions, then validate the separate native successor. The historical
source/image-switch helper remains0007-only; do not turn it into a generic DDL switch.

2. Implement commit_native_context_policy through the already accepted capability
platform.human_context_policy_command(uuid,uuid,text,text,text,bigint,jsonb,jsonb)
only. Strict closed ENABLE/PAUSE request, key/CAS/binding/source profile and result
per§16.7.1; exact actual session_user=asm_migrator, LOCAL/TEST DB and READ COMMITTED.
No runtime/owner HTTP toggle, direct policy/receipt/Audit DML, auto-enable, billing
initialization/renewal, provider discovery/probe/setWebhook or external HTTP in the
native-policy path. Existing explicit Telegram setup behavior stays separate.
Use bounded redacted diagnostics; no secret/key/hash/provider/raw-body logging.

Before a policy mutation, host must verify clean C0-approved source/tree, exact
installed0013 catalog and matching approved API/Worker/Scheduler/Console profile.
Drained old processes is explicit operator attestation, never inferred DB knowledge.
Missing/unpaired C5 profile refuses; this task cannot claim Console readiness from
the starting tree. Do not accept a caller trusted=true assertion in place of actual
source/catalog/binding checks. Wire an explicit operator invocation in the existing
CLI/host surfaces as needed; none may run automatically on start/migration/health.
After exact old-key replay, read current policy separately; historical accepted ON
must not overwrite/enable a currently PAUSED policy. Preserve previous accepted
receipt when current-read fails; retry read, not manufacture a fresh command.

3. Add narrow unit/PG evidence carriers for the host boundary: exact0013 readiness
positive and mismatched0012/unsafe role failures, absent/mixed source or Console
profile refusal before mutation, no external calls, strict policy DTO/rollback/
commit-before-result, ENABLE/no-op/PAUSE/CAS/conflict, committed ENABLE→later PAUSE→
old replay with current PAUSED, retained no-op counters/Audit/receipt semantics.
Use real SQL capabilities for successful authority. Negative DML seams must be
explicit; no fabricated accepted receipt/permission/current state.

**Explicit readiness-test exception:** the two existing native PG tests currently
prove deliberate0012 refusal. Pair new0013 positive with explicit retained0012
reader refusal; do not simply delete the negative or relabel an old PASS. Preserve
their catalog/security assertions and all existing105 node IDs. The original C2/
C3 byte-prefix freeze is relaxed ONLY inside those two named readiness definitions
for this assigned change; every other current test/fixture/assertion stays exact.
New focused cases may be appended; existing source/runtime cases cannot be removed,
skipped, xfailed or reduced. Keep distinct historical profiles/pins/evidence.

4. Update the runbook with concrete prepare/check/drain/upgrade/pair/operator/
current-read/PAUSED recovery order, bounds and separate account authorization.
No command is execution permission. Existing S600/P720/fixed120/+480/S+1200,
cleanup90,state25,browser25,foundation45,stock20m and request3s/60s/10s unchanged.
No CI optimization or new product requirement.

**Allowed local verification:** current clean checkout imports and existing frozen
Python3.13; compile/Ruff/format/mypy changed Python; complete relevant unit modules
(test_foundation,test_m2_3_setup,test_telegram_egress,test_telegram_egress_migration);
full four-module native collect-only and relevant host-PG collect-only, no service.
Report exact commands/results/added node IDs and untouched old assertions/profiles.
Do not rerun unrelated unchanged suites just for counts. If runtime evidence needs
another path/profile change, report precise dependency to C0, do not expand silently.

**NOT authorized:** PG/Docker/services/lab startup/reuse/cleanup, Actions/execution
ref/dispatch/rerun/full CI, new PR/main/VM/provider/S3/LLM/live/deploy/renewal or
other chat/agent launches. Source task does not execute operator policy commands.
Return REVIEW→C6 HOLD with exact commit/tree/parent, actual local evidence and
PG/operator/host rollout NOT RUN; source-only is not VERIFIED. Normal FF with
expected prepared head/force=false, no amend/rebase/force. C0 integrates C5/C6,
reviews readiness exceptions and separately authorizes required real gates.
User owns merge.

### 0.3. C5 exact source task

**C5-M3.1-NATIVE-CONTEXT-CONSOLE-R1 — owner context review and explicit Resume; source-only.**

Repository Elefesys/ai-service-manager. Branch c5/m3-1-native-context-console-r1.
Start only from the exact C0 preparation SHA/tree in this binding; its sole parent
is accepted stock source5d98651d2c34314724a12283d1741e73594e16b8. Separate clean
checkout; exact HEAD/tree and supplied original11=canon=SOURCE_MANIFEST. Read
current HANDOFF/REGISTER/AGENTS/IMPL-001; applicable Spec5.8–5.14/18.5–18.9,
ADR002–007/024–026/180/266/267, MVP GJ-G/J and Plan/Roadmap M3; M3_CONTRACT§16–16.20.
The accepted current Python models/OpenAPI at this exact source define wire truth.
C6 has disjoint host/schema/operator work; do not follow its moving branch.

**New paths allowed:**
- frontend/src/HumanContextPanel.tsx
- frontend/src/HumanContextPanel.test.tsx
- frontend/src/human-context-api.ts
- frontend/src/human-context-api.test.ts

**Existing paths allowed, only paired native-context integration:**
- frontend/src/ConversationControl.tsx
- frontend/src/conversation-control-api.ts
- frontend/src/ConversationControl.test.tsx
- frontend/src/conversation-control-api.test.ts
- frontend/src/MessagingPanel.tsx
- frontend/src/MessagingPanel.test.tsx
- frontend/src/App.test.tsx
- frontend/src/style.css — only necessary panel styles; no global redesign.
- frontend/src/escalation-api.ts
- frontend/src/escalation-api.test.ts
- frontend/src/escalation-fixtures.test-helper.ts
- frontend/src/EscalationsPanel.tsx
- frontend/src/EscalationsPanel.test.tsx
- frontend/src/billing-api.ts
- frontend/src/billing-api.test.ts
- frontend/src/BillingPanel.tsx
- frontend/src/BillingPanel.test.tsx
- frontend/e2e/conversation-control.spec.ts
- scripts/m2_4_browser_fixture.py
- scripts/m2_4_browser_worker.py
- tests/test_m2_4_browser_fixture.py

The last three are only for the existing synthetic browser carrier through real
accepted capabilities; no forged reconciliation/Resume/send receipt or successful
authority DML. C0 explicitly includes affected MessagingPanel/App tests and scoped
styles. No backend/API/OpenAPI/SQL, host/operator, contract/C0 docs, manifests/locks,
CI/runner, new dependency or unrelated UI change. If another path is necessary,
return the exact integration reason to C0 first.

1. Implement strict parsers for the three accepted human-context routes:
GET state, GET observations(limit/cursor), POST reconcile. Closed object keys/
unions/cross-field invariants exactly pair Python/OpenAPI; canonical UUID/decimal
strings, UTC6 timestamps, nullable keys, scalar Unicode/no NUL/surrogates and exact
TEXT/PHOTO/UNSUPPORTED/DELETE preview rules. Preserve ordered blockers and current/
through epochs/cursor bounds and scope. Reject malformed/unknown responses closed;
no coercion, trimming/normalization, silent truncation or generic JSON fallback.
Do not request backend fields/endpoints absent from the accepted source.

POST keeps exact actor/ws/C/Client/key/body and full CAS, including P/N/checkpoint/
input hash/current revision. Measure the entire serialized UTF-8 JSON body <=4096
bytes including envelope/escaping, not text length alone. Expose usable size/error
feedback without hashes/counters/internal protocol in the product flow. Three
dispositions OWNER_TEXT/CANONICAL_SUFFICIENT/UNRESOLVED, explicit attestation and
source_media NONE/UNAVAILABLE; render the applicable choices/limitations honestly.

2. Owner UI shows current saved full context separately from editable replacement
and provider observations. Prefill current text but require explicit replacement/
withdrawal confirmation; omitted old facts are not merged back. Save action
«Сохранить сверенный контекст» is separate from «Разрешить автоматику».
Save does not Resume/Takeover/send; resumed AI state does not claim an AI answer.
Explain Takeover before native discussion, unavailable photo/content, text-only
owner assertion and the inability to prove completeness/causality from N0/no updates.
Native observation is a signal, not a proven owner agreement. No synthetic Message,
Outbox, File/FETCH/vision or M4 behavior.

Render policy OFF_UNUSED/ON/PAUSED, review/coverage/resume blockers and
automation_work IDLE/WAITING_CONTEXT/OPERATOR_REQUIRED in understandable language.
IDLE is not proof that an old request was answered; terminal hold is not a retry/
restart/new-send button. PAUSED blocks new Resume but permits allowed review/save/
Takeover/manual work. Preserve existing manual DISPATCHING/UNKNOWN visibility and
all product/billing authorization. Context confirmation never grants send permission.

3. Memory-only request recovery bound to actor/ws/C/Client. Lost commit/network ACK:
same key/body after session/CSRF recovery; no silent new intent/rebase/repost.
Valid200 or saved replay + failed current GET retries only GET. Current GET, not
historical acceptance, determines displayed R/mode/allowed actions. R1 replay after
R2 leaves current R2. Two-tab stale CAS refreshes and requires a fresh explicit
choice; late response from old scope cannot repopulate the new view. Revocation
clears protected view. Cursor-stale refreshes first page; pagination/reading is not
attestation. No local/session storage of private context or automatic background POST.

4. Pair existing control error parser/UI with all accepted native409 codes while
retaining exact BILLING_STATE_UNAVAILABLE/state_reason503. Pair Escalation strict
reader with nullable context_hold and reason/P/N/coverage; hold cannot claim current
can_resolve=true or rewrite status/validity/cancel/replay semantics. Pair both Audit
variants HUMAN_CONTEXT_RECONCILED and HUMAN_CONTEXT_POLICY_COMMANDED, exact actor/
payload/object-version invariants and safe readable labels; no owner policy toggle.
Retain old closed variants and response/error strictness.

5. Focused Vitest/API/component tests cover body4096/4097 including Unicode/escaping,
all dispositions/preview unions, stale/foreign/malformed projection/cursor, both
policy states/hold/unknown visibility, old replay/new current, valid200+GET failure,
session/CSRF/Owner revoke and cross-scope late responses, full replacement and
separate explicit Resume. Preserve existing assertions/cases, add only meaningful
new risks. Extend existing browser control spec and synthetic fixtures for actual
Takeover→reconcile→Resume, replacement/stale tabs/replay/hold, through real API/
capabilities. Real browser/PG execution is a later paired C0 gate; mocks are not it.

**Local verification allowed:** existing frozen Node24/npm dependency environment,
typecheck, complete impacted Vitest files and frontend build with generated output
outside the checkout or cleaned before return; no package/lock changes. Current
frozen Python3.13 imports/compile/Ruff/mypy and complete browser-fixture unit module
if changed; full Playwright collection/list only (not service/browser execution).
Report exact commands/results and which scenarios are mocks versus future actual
carrier assertions. Do not rerun unrelated suites simply to increase counts.

**NOT authorized:** PG/Docker/service/lab startup/reuse/cleanup, real browser/API/
provider/account/VM calls, Actions/execution ref/dispatch/rerun/full CI/new PR/main/
deploy/renewal, other chats/agents. No source-only evidence promoted to E2E VERIFIED.
All caps and Contract9/Q01/MATERIAL11/D1/D2/D3 constraints retained.
Return REVIEW→C5 HOLD: exact source commit/tree/sole parent/branch, changed files/
wire mappings, actual local results, retained cases and PG/browser NOT RUN.
Normal FF with expected prepared head/force=false, no amend/rebase/force. C0 reviews
combined C5+C6 source and then assigns independent C8/real integration gates.
User owns merge.

### 0.4. Retained integration boundary

C0 reviews exact C5/C6 returns, consolidates their disjoint write sets and assigns
independent C8/required actual integration gates. Current stock PASS covers the
accepted DB/API/runtime source; it cannot be transferred automatically to new
host/Console code. No executor starts services/PG/browser/Actions or accesses VM/
provider/account under these source-only tasks. No new product scope or blanket
test rewrites. Main e205e22051bc06295758b504d84699652b176c15/schema0012 and PR34
closed/merged unchanged; execution remains accepted5d98651. No0014/applied edits.
Contract9/Q01/MATERIAL11 and prior closures/D1/D2/D3/budgets retained.
Account/A08/P01/P05/TEST renewal/collector/A12 later; M4 out/IMPL-05 deferred.
User owns merge.

## История — 0. Текущий шаг C0 — полный stock после двух исправлений тестов / 2026-10-18 UTC

[C0 source acceptance6254398312](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6254398312).
**C2 DB-R4 и C3 PG-R3 INTEGRATED source; C1/C2/C3/C5/C6/C8 HOLD.**
Это исправления двух test carriers; новых product requirements нет.
Native application/runtime NOT VERIFIED; M3 IN_PROGRESS.

### 0.1. Exact accepted source and C0 checks

| Source | Commit / tree |
|---|---|
| C2 DB-R4 | d694e24638ae133fe9412b3f7cde73acb0089be3 / eb5d76dbd05d2390775887409ccd6743237f49cd |
| C3 PG-R3 | e4ac5afa12174317b39097de042f131f5820cb74 / b80ea2d7b3fac2ade38b47edb5e9475db86a95ef |
| Shared sole parent | a2678ce605e2dcc1c4789d0e1285cf5ec616c336 / 551404ae860d335951b0073b2367f92aa847cb84 |
| Previous actual stock source | 2fc3f1491321456e280c01852c7747e0ffdf9139 / 127e40091cf40cf8602c89eaf72833bae84d6044 |

This C0 consolidation has ordered parents C2 then C3 above. Against shared start,
only their two disjoint PG files (+43/−3) and these two C0 docs change;
all other284 blobs/modes remain exact,288 total. Exact final SHA/tree/archive
are bound by the separate canonical C0 execution approval, not this document.

C2 modifies only native_manual_delivery_history and its UTC6 timezone test.
Real ordinary post-Resume Turn obtains BASE/GUARDED; a distinct real marker Turn
then obtains ESCALATE_OWNER. Correct Job routes and distinct Turns are asserted.
Actual owner-created SENT/FAILED/UNKNOWN/PENDING/DISPATCHING history, both
UTC and Asia/Novosibirsk, strict untouched parsers/digests/full history,
saved input/whole Outbox invariance and zero adapter calls remain.
C3 changes only runtime_effects Audit order key id→audit_event_id; SELECT *
full-row Audit comparison and all other helper/test bytes are preserved.
No production workaround, fabricated receipt/Job, reduced assertions or new cases.

C0 independently verified all288 remote source bytes/modes for each return,
287 unchanged leaves each, exact parent/tree and intended combined source.
Old121779-byte C2 prefix SHA256987ce8de6655236b6872f483b1cf3084640f8fb804232c98a905d573a329d12d
and12965-byte C3 prefix SHA25630fc57c7a69521130faedc48da7d8d90766d7e9deb940a691fc4ce03da746a1f
are unchanged; only the three assigned AST definitions differ and all prior
assertions remain. Full contract769072 bytes/SHA256fe2eb4ef2469ccb14b7147017c3c81066cde1b8a6ad60acbf73922a15e3ace5f
and original11=canon=manifest verified. No migration/backend/runner/workflow change.

Actual local combined compile/Ruff/format2/whitespace PASS; Python3.13.14,
current checkout imports and57 frozen external distributions verified.
Complete four-module collection105 in3.65s =7 source+56 DB+12 API+30 runtime,
shared actual FixtureDefs/reset guards and all98 PG consumers verified.
Ordered LF node-list SHA2569881ab5a77aca51a7d6c66737c352055cd4f037acf156e55f265cedeabb24b1a unchanged.
Fresh source catalog equals accepted source exactly:167 functions/45 tables/
635 columns; all10 observer table/key pairs exist. These are source checks,
not actual PG PASS; no local PG/services or unchanged full suite run for counts.

### 0.2. Required single corrected execution

C0 next publishes a separate exact one-use approval for one normal FF,
force=false, of c0/m3-1-native-context-db-stock-r1 from exact
2fc3f1491321456e280c01852c7747e0ffdf9139 to this final reviewed C0 source.
Previous approval6253600648 is consumed and supplies no retry permission.
Existing push-only workflow/stock digest/extensions/roles/dependencies and
20-minute whole-job cap are unchanged. No source amendment during execution.

Run all105 native cases/all phases with0skip/xfail/deselection and full51 runner
tests+130subtests. Independently verify the exact archive/manifest, owned image/
container/volume/URL, actual LOGIN roles/98 guarded resets, fresh0013 catalog
(all167 typed functions/unique OIDs including verifier,45 tables/635 columns/
nonfunction/security/ACL), foundation0013 refusal, owned cleanup and clean tree.
Expected unchanged SQL full profile c045a59f86201a244ed0d43fbe22aa8cd72fddd346d770706c6ab3b92ee9a411
must be independently measured again, not accepted from a declared digest.
Nonfunction57e03fe369be4bd03116ce380e37a9b447a2bc1a72e3bbf2a70c7ac08d69e370;
verifier527fce5681d5345369cd88b555a302df6d305ef8566cf12a666198eb64a6f4ac.

C0-NC-CARRIER-01/P2 and02/P2 stay OPEN/source-addressed until actual corrected
full evidence; C3-NC-RUNTIME-01/P2 stays OPEN for complete five-status UTC6
projection/BASE/GUARDED/unsigned escalation interoperability.
Historical39154853068 FAIL92/105 remains; earlier C6 runner/catalog/cleanup
acceptance is retained but does not prove the13 formerly blocked scenarios.
On failure retain evidence and issue a narrow finding; no retry/selected rerun,
cap extension, dispatch, used0013 reuse or unproven lab repair/cleanup.

### 0.3. Retained gates

No full CI/new PR/main/VM/provider/S3/LLM/live/deploy/renewal in this execution.
Main e205e22051bc06295758b504d84699652b176c15/schema0012; PR34 closed/merged.
No0014/applied0001–12 edit. Host/schema/operator, C5, C8/full integration,
account/renewal/collector/A08/P01/P05/A12 remain later separate gates.
C1-NC-DB-01/02/C0-NC-RUNNER-01 and Contract9/Q01/MATERIAL11 prior closures,
D1/D2/D3 and every prior budget remain. M4 out, IMPL-05 deferred; user owns merge.

## История — 0. Текущая выдача C0 — исправления двух test carriers после stock FAIL / 2026-10-18 UTC

**C2/C3 ACTIVE только по двум source-only исправлениям ниже; C1/C5/C6/C8 HOLD.**
[C0 actual disposition6253741115](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6253741115).
Это исправление тестов уже выбранной функции; новых product requirements нет.
Native application/runtime NOT VERIFIED; M3 IN_PROGRESS.

### 0.1. Проверенный actual result и границы принятия

Run39154853068/attempt1, job117755853170, source
**2fc3f1491321456e280c01852c7747e0ffdf9139**,
tree **127e40091cf40cf8602c89eaf72833bae84d6044**: **FAIL92/105**.
All105 called,105 setup+105 teardown PASS;315 phase reports,0skip/xfail/deselection.
Per-module source7/7, DB54/56, API12/12, runtime19/30.
Runner51+130subtests PASS; native542.983s/receipt573.957s within unchanged20m.
Approval6253600648 consumed once; execution ref stays2fc3f14, no retry permission.

Artifact12146143735 (39 files,3238146 bytes, expires2026-10-25), ZIP SHA256
0dddf0eae3fd9837ca56c1e745cba4c89f99c4917b2c4ebbe2f0d927918e2a05.
C0 independently checked all288 source bytes/modes, exact archive
ccf625cec399d7c404475f019cb86bbcc2f3a3054eb58eff327fa46b5b9de391
and manifest8de5124772a6f3627d11a6fae160a0f8621645de709619af43994e54a092dad3.
Actual PG18.6/vector0.8.6/btree_gist1.8/Python3.13.16/uv0.10.0;
actual LOGIN roles,98 guarded resets, shared fixture/source/resource guards,
foundation0013 refusal, independent catalog, owned cleanup and final clean tree PASS.

Independent corrected full profile now VERIFIED for exact source:
**c045a59f86201a244ed0d43fbe22aa8cd72fddd346d770706c6ab3b92ee9a411**.
All167 typed functions/unique OIDs incl verifier,45 tables/635 columns/ACL exact.
Nonfunction57e03fe369be4bd03116ce380e37a9b447a2bc1a72e3bbf2a70c7ac08d69e370;
verifier body527fce5681d5345369cd88b555a302df6d305ef8566cf12a666198eb64a6f4ac.
C6 runner-R3 INTEGRATED/VERIFIED scoped runner/catalog/cleanup; C6 HOLD.
Whole carrier FAIL is retained, not promoted to application verification.

### 0.2. Two test findings; original runtime gate stays open

| Finding | Actual cause / owner |
|---|---|
| C0-NC-CARRIER-01/P2 OPEN | C3 runtime_effects orders Audit by nonexistent id; actual audit_event_id. SQLSTATE42703 blocks10 terminal cases+1 ACK-loss case before target assertions |
| C0-NC-CARRIER-02/P2 OPEN | C2 manual history uses escalation marker, then requests GUARDED_TEXT; deliberate scheduler chooses ESCALATE_OWNER. Both timezone cases blocked |
| C3-NC-RUNTIME-01/P2 OPEN | UTC6 source addressed and strict C3 wrapper/vector pairs now PASS; complete five-status multi-shape carrier still blocked, so full closure withheld |

Actual positives also include all12 API and all16 original runtime cases,
server JSONB vectors and both Unicode/native/material/private File cases.
No new production bug is established by the13 fixture failures. Fix the test
setup/observer, retain all assertions; do not alter production to satisfy tests.

This docs-only preparation is a sole-parent descendant of2fc3f14; only
HANDOFF/register change,286 other blobs/modes exact. Canonical task bindings
supply full new SHA/tree. C0 source branch
c0/m3-1-native-context-stock-followup-r1; both task branches start there.

### 0.3. C2 exact correction task

**C2-M3.1-NATIVE-CONTEXT-DB-R4 — исправить только UTC6 test fixture; source-only.**

Repository Elefesys/ai-service-manager; branch **c2/m3-1-native-context-db-r4**.
Start from the exact new C0 docs-only preparation SHA/tree in this task's binding;
its sole parent is **2fc3f1491321456e280c01852c7747e0ffdf9139**.
Separate clean checkout; verify HEAD/tree and original11 against supplied
project_sources/SOURCE_MANIFEST. Read current HANDOFF/REGISTER, AGENTS/IMPL-001,
applicable Spec/ADR/MVP/Roadmap/Plan and contract§16–16.20. No other chat/agent.

**Only write path: tests/test_m3_1_native_context_postgres.py.**
Only these two existing definitions may change:
- native_manual_delivery_history;
- test_completed_manual_delivery_history_utc6_before_v3_digest.

Finding C0-NC-CARRIER-02/P2: both timezone cases failed in run39154853068 at
work_for(...,"GUARDED_TEXT"), no matching Job. The helper's exact escalation marker
selects ESCALATE_OWNER, deliberately excluding GUARDED_TEXT. This is a fixture
mistake; do not change scheduler/backend/SQL/contract or insert a Job by hand.

Prepare a legitimate ordinary post-Resume Turn for BASE and GUARDED. After their
saved snapshots and strict unchanged parser/digest/storage checks, admit a distinct
real marker message through the existing capabilities, seal its new Turn and use
its actual ESCALATE_OWNER Job. Assert the new Turn is distinct and expected Jobs
exist on their respective Turns. Keep the same actual owner-created five-status
manual history: SENT/FAILED/UNKNOWN/PENDING/DISPATCHING; both UTC and
Asia/Novosibirsk; projection+BASE+GUARDED+closed unsigned ESCALATION complete
expected history, null/UTC6/status/error/version, no normalization/re-signing
produced bodies, stored-input and whole Outbox invariance, zero adapter calls.
Follow the now actual-PASS separate ordinary→marker sequence in the C3 Unicode
File scenario as a reference, without editing its file. No generic fixture rewrite.

Keep the entire **121779-byte** old prefix SHA256
**987ce8de6655236b6872f483b1cf3084640f8fb804232c98a905d573a329d12d** byte-exact,
all52 original DB PG cases, new validator-vector pair and all other definitions/
imports/assertions. In particular native_worker_at_timezone is frozen.
Starting file134337 bytes, SHA256
77e908893e23ee3489fd38075a210eec715d00cbcece6aba189b81074ac4a031.
All existing56 DB node IDs and complete105 four-module node IDs remain unchanged.
No deleting/skipping/xfail/param reduction or weakening assertions to get green.

Local verification only: existing frozen Python3.13 environment, explicit current
checkout PYTHONPATH and actual import check; source compile, Ruff/format this
one file, exact two-definition AST/prefix/diff audit; complete four-module
collect-only, no subset, still105 IDs (7+56+12+30). Ordered LF node-list SHA256
9881ab5a77aca51a7d6c66737c352055cd4f037acf156e55f265cedeabb24b1a.
Source-check routing against the accepted scheduler; collection is not PG PASS.
No unchanged full suite rerun just for counts.

All other287 blobs/modes frozen: migrations0013 and applied0001–0012, source tests,
C3 runtime/API PG, backend/foundation0012/strict parsers, contract769072 bytes/
SHA256fe2eb4ef2469ccb14b7147017c3c81066cde1b8a6ad60acbf73922a15e3ace5f,
runner/workflows/deps/locks/operator/frontend/C0 docs. No0014.

**No PG/Docker/service/lab startup, cleanup or reuse; no Actions/ref movement/
dispatch/rerun/full CI/new PR/main/VM/provider/S3/LLM/live/deploy/renewal.**
The execution branch stays2fc3f14 and approval6253600648 is consumed. No used0013
reapplication; later full corrected stock run needs separate C0 approval.
If another change is needed, return the exact finding; do not expand this scope.

Return REVIEW→C2 HOLD: exact commit/tree/sole parent/branch, one-path diff and
two changed AST definitions, preserved prefix/other cases, legitimate route/
Turn/Job mapping and retained assertions, actual local commands/results and
PG NOT RUN. Finding remains OPEN until corrected full execution accepted.
Normal FF with expected prepared head, force=false; no amend/rebase/force.
C3 has a disjoint one-helper correction. C0 consolidates both returns; user owns merge.

### 0.4. C3 exact correction task

**C3-M3.1-NATIVE-CONTEXT-RUNTIME-PG-R3 — исправить имя ключа Audit в test helper; source-only.**

Repository Elefesys/ai-service-manager; branch
**c3/m3-1-native-context-runtime-pg-r3**. Start from the exact new C0 docs-only
preparation SHA/tree in this task's binding, sole parent
**2fc3f1491321456e280c01852c7747e0ffdf9139**.
Separate clean checkout, exact HEAD/tree. Read current HANDOFF/REGISTER,
AGENTS/IMPL-001, relevant originals/manifest and contract§16–16.20.
Verify supplied project_sources byte-exact. No other chat/agent.

**Only write path: tests/test_m3_1_native_context_runtime_postgres.py.**
**Only allowed change: runtime_effects() table-order map entry for app.audit_events,
from id to the actual audit_event_id.** The complete full-row Audit comparison
must remain. All other mapping entries, SQL loop/helper behavior and test bodies
are frozen; do not remove Audit rows from runtime_effects.

Finding C0-NC-CARRIER-01/P2:10 terminal matrix cases plus1 committed ACK-loss case
failed before their intended actions because SELECT * FROM app.audit_events
ORDER BY id raises42703. Exact source and installed catalog use composite
(workspace_id,audit_event_id); no id column. This is a test observer defect.
Verify every other listed table/order key against the accepted source catalog,
so the helper reaches its assertions; report any distinct mismatch before edits.

Starting file48090 bytes /SHA256
7e57727b6f7ee7c9f590a860a3ba108946579e97ed7da4a09f69305681df9417.
Retain entire **12965-byte** original prefix SHA256
**30fc57c7a69521130faedc48da7d8d90766d7e9deb940a691fc4ce03da746a1f** and all32
original AST nodes. Apart from runtime_effects AST, every existing definition,
fixture/import/helper/decorator/assertion is exact. All30 runtime cases and all105
combined node IDs unchanged; no skip/xfail/subset/parameter/assertion reduction.
No production/schema/backend behavior changes or fabricated evidence.

Use existing frozen Python3.13; verify current import paths with explicit
PYTHONPATH. Source compile, Ruff/format one file, exact one-helper AST/one-line
diff/prefix audit and static all-table/key schema check; complete four-module
collect-only still105=7+56+12+30. Ordered LF node-list SHA256
9881ab5a77aca51a7d6c66737c352055cd4f037acf156e55f265cedeabb24b1a.
No PG PASS claim from source/collection. Do not rerun unchanged suites for counts.

Other287 blobs/modes frozen, including C2 DB/source/API tests, migrations,
backend/foundation readiness0012/strict parsers, full contract769072 bytes/
SHA256fe2eb4ef2469ccb14b7147017c3c81066cde1b8a6ad60acbf73922a15e3ace5f,
runner/workflow/deps/locks/operator/frontend and C0 docs.
**No PG/Docker/service/lab/cleanup, Actions/ref move/dispatch/rerun/full CI/
new PR/main/VM/provider/S3/LLM/live/deploy/renewal.** Approval6253600648 consumed;
execution stays2fc3f14. C0 later reviews both corrected sources and separately
authorizes one full corrected stock run; no used0013 reapplication.

Return REVIEW→C3 HOLD with exact commit/tree/sole parent/branch/clean source,
one-line mapping change, all other AST/prefix/node IDs exact, source schema key
cross-check and actual local results, PG NOT RUN. Finding stays OPEN until actual
corrected full run. Normal FF/expected head, no amend/rebase/force.
C2 has disjoint UTC6 fixture correction; do not follow or edit its branch.
User owns merge.

### 0.5. Retained gates

C0 reviews both returns and consolidates once before a separate exact full-stock
approval. Existing105 cases and51 runner tests remain; no new product scope,
selective retry, cap extension, source patch during a run or hidden PG execution.
Main e205e22051bc06295758b504d84699652b176c15/schema0012 and PR34 closed/merged
unchanged. No0014/applied migration edits/used0013 reapplication.
Host/schema readiness/operator/C5/C8/account/renewal/collector/A08/P01/P05/A12
remain later gates; M4 out, IMPL-05/CI optimization deferred.
Contract9/Q01/MATERIAL11, D1/D2/D3 and all prior budgets preserved. User owns merge.


## История — 0. Текущий шаг C0 — общий stock-прогон native DB/API/runtime / 2026-10-18 UTC

**C3 PG-R2 и C6 runner-R3 приняты по исходному коду и интегрированы в этот checkpoint.**
[C0 source acceptance6253565474](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6253565474).
C1/C2/C3/C5/C6/C8 HOLD; следующий шаг выполняет C0: отдельное точное разрешение
одного прогона существующего stock workflow. Этот документ сам по себе не
разрешает перемещение execution ref, повторный запуск или новые изменения.

### 0.1. Что принято и что пока не проверено

| Source | Exact accepted commit / tree |
|---|---|
| C3 runtime PG additions | 33146375886f99f6eeff7db4ab92f0e162e6520e /43156c62b869d674de5a201d2a3a2dee32d4e025 |
| C6 complete runner | 397389b77f331ef78c5cafe37feffe42959e136f /4748746ffc95fc1f6b932ac4c8a5bee4d9c54a24 |
| Shared sole parent | 64e6a13f52904507368f88f981947d5d41250c08 /7c9948c3205475d2d1f0211bc0e59062b77fe3f3 |
| Retained C2 UTC6 correction | 15a8ea7a12f01644250315e26d3d6c5cc487b59e |

This C0 merge has ordered parents C3 then C6 above; only their3 disjoint source
paths plus HANDOFF/register differ from64e6. The full created commit/tree is
bound by the canonical C0 approval. No source invention, conflict correction,
production/SQL/API/contract or workflow change is included in this consolidation.

C3 adds14 PG cases for the three already assigned gaps: five remaining terminal
boundaries × HOLD/exhaustion; committed guarded send-begin ACK loss with work
replay miss and real UNKNOWN recovery; PostgreSQL JSONB bytes/hash and real
saved Unicode/native/material/private File inputs. Original12965-byte runtime
prefix SHA25630fc57c7a69521130faedc48da7d8d90766d7e9deb940a691fc4ce03da746a1f
and all32 original AST nodes are unchanged. No successful authority/receipt/
UNKNOWN DML; negative Job budget/lease seams are explicit.

C6 includes all four complete modules and every setup/call/teardown, rejects
omissions/skips/xfail/deselection/duplicate reports, and proves the same guarded
native reset for all PG fixture consumers. No fixed test-count ceiling.
Existing40 runner tests/78 subtests retained;11 tests/52 subtests added.

C0 actual local combined-source evidence: **58 PASS +130 subtests /7.62s**
(51 runner+7 source), Ruff/format3 and compile/whitespace PASS.
**105 collected only /5.77s =7 source+56 DB PG+12 API PG+30 runtime PG**.
All previous91 retained. Real collected FixtureDefs for all98 PG consumers
resolve to the shared fixture/reset. Ordered LF node-list SHA256
9881ab5a77aca51a7d6c66737c352055cd4f037acf156e55f265cedeabb24b1a.
Python3.13.14/current imports/57 frozen external distributions and all original11
attachments=canon=manifest verified. No local PG/service started.

**Actual corrected PG/stock/interop NOT RUN at this preparation.**
**C3-NC-RUNTIME-01/P2 OPEN / addressed in source. Native runtime NOT VERIFIED.**
No new confirmed production finding in this source review.

### 0.2. One intended actual gate; execution requires the separate exact approval

C0 will bind exactly this final source SHA/tree and one normal force=false FF of
c0/m3-1-native-context-db-stock-r1 from
**bde0c48af74f23cd6430fc669ea4635e21aa68c6**. Previous approval6251780231 is consumed.
Existing push-only workflow, exact stock image/extensions/roles/dependencies and
20-minute whole-job cap are frozen. Run the full final105 carrier, full51 runner
tests, independently rebuilt fresh0013 catalog and owned cleanup/clean-source.
No selected subset, retry/rerun/dispatch/cap increase or amendment during the run.

Independent catalog must compare all167 typed functions/OIDs including verifier,
45 tables/columns/security/ACL/nonfunction data. Corrected source body hashes:
projection8d38da64c526acb61365aa06eb293d117e1d8af93b598b5a507da3a23bc17b51;
validator21492e85adeaf186bce6bbfdde7b89c8e70762c56f8ec28c6da54b3a5327f49c;
verifier527fce5681d5345369cd88b555a302df6d305ef8566cf12a666198eb64a6f4ac.
Nonfunction57e03fe369be4bd03116ce380e37a9b447a2bc1a72e3bbf2a70c7ac08d69e370
is unchanged; new installed full profile remains unknown until measured.
No reuse/reapplication of a used0013 DB or unproven C2 lab resources.

Main e205e22051bc06295758b504d84699652b176c15/schema0012 and PR34 closed/merged
remain unchanged. Foundation must still refuse0013; host/schema pairing, C5/C8,
A08/P01/P05/account/renewal/collector/A12 are separate later gates.
Contract9/Q01 and MATERIAL11 closures, D1/D2/D3 and all existing caps retained.
M3 IN_PROGRESS; M4 out; IMPL-05/CI optimization DEFERRED. User owns merge.

### 0.3. Scope visibility

These returns implement verification already assigned after C1 review; they add
no new product behavior. Native owner reconciliation remains the earlier chosen
mechanism for resuming from current human context. Any later material expansion
or new owner action must be explained explicitly, with its reason and effect;
test/run numbers are evidence, not additional product goals.


## История — 0. Текущая выдача C0 — native PG carriers и runner R3 / 2026-10-18 UTC

**C3 и C6 ACTIVE только по новым source-only задачам; C1/C2/C5/C8 HOLD.**
[C0 disposition6253081736](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6253081736) принимает
[C1 scoped review](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6252871772) и
[C2 DB-R3 source correction](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6252983496).
C3 runtime R1 и C2 DB-R3 включены в консолидированный C0 source checkpoint.
**Это source integration, не native application/runtime VERIFIED.**
**C3-NC-RUNTIME-01/P2 OPEN / addressed in source** до actual corrected PG/interop.
Новых подтверждённых product findings по C1 review нет.

### 0.1. Принятые exact sources и проверка C0

| Binding / evidence | Exact value |
|---|---|
| C1 read-only review target | **225879990011f2e41f4c38e46308ffdd976a7393**, tree **57009c4990345768badb912c1c3ff0818edb4650** |
| C1 separate instructions | **73eaeed87cb8c9caf7a6256ba8c246f25e059621**, tree **4a02292219cb9219a56772a7a7c7be0ece7e0039** |
| Accepted C2 delivery / tree | **15a8ea7a12f01644250315e26d3d6c5cc487b59e** / **3fc15bdb8c9d475c94c94e5e12cce2b059fedfc6** |
| C2 sole parent | **73eaeed87cb8c9caf7a6256ba8c246f25e059621** |
| C2 source delta | 4 existing paths,+564/−5;288 blobs,284 other bytes/modes unchanged |
| C0 source identity | Independently fetched4 blobs; all288 bytes/modes, exact commit/tree/archive, clean/diff --check PASS |
| Source tar SHA256 | **cad5d1705b2754abc7ddfa59fdeafc712653609bd9fd228b679746d28452bb32** |
| Actual C0 local checks | **47 PASS +78 subtests /4.35s** =7 native source/codec +40 runner; Ruff/format3 files PASS |
| Actual C0 collection | **91 collected only /4.73s** =7 source +56 DB PG +12 API PG +16 runtime PG |
| Full frozen contract | **769072 bytes**, SHA256 **fe2eb4ef2469ccb14b7147017c3c81066cde1b8a6ad60acbf73922a15e3ace5f** |

C0 verified intended asm.foundation import path, Python3.13.14 and57 installed
external distributions against frozen uv.lock. Original11=repository=manifest=
attached originals exact. C0 did not rerun unchanged222 local suite after prior
C0 PASS on2258799; C2 reports222 PASS on its corrected tree. C1 independently reports
38 targeted unit/ASGI cases and10 source-derived literal vectors; those are not PG.
No source/local/mock/collection count is actual PostgreSQL or application acceptance.

C2 changed only0013, two native source/DB tests and contract append§16.19–16.20.
Old756397-byte contract prefix/SHA256e7f3796fcff8640ffca203266ecf7b5988f7ab1bd24850b12e923122abf5d281
preserved; append12675 bytes. Original121779-byte native PG module prefix exact;
all52 old PG nodes retained. Four original source-test ASTs exact; only authorized
R1/R2 freeze carrier adapted and paired with exact R2 freeze. All28 C3 PG cases,
backend, foundation, API/OpenAPI, frontend, runner/workflow/locks unchanged.

### 0.2. UTC6 correction and remaining actual gate

Producer human_context_projection now serializes nested delivery.completed_at in
UTC6 before ordinary V3 digest; NULL remains null. Nested snapshot validator checks
exact lexical shape before cast, finite/calendar round-trip and preserved closed
status/error/null/type relations. Python Timestamp/V3, member ingress_at, other
timestamps, old snapshots/receipts and ORIGINAL restoration bodies unchanged.

Independent expansion:955 commands,167 functions/45 tables;0013=198 op batches/
53 final definitions;35 additions/18 replacements. Exactly3 changed bodies:
- projection **8d38da64c526acb61365aa06eb293d117e1d8af93b598b5a507da3a23bc17b51**;
- nested validator **21492e85adeaf186bce6bbfdde7b89c8e70762c56f8ec28c6da54b3a5327f49c**;
- generated verifier **527fce5681d5345369cd88b555a302df6d305ef8566cf12a666198eb64a6f4ac**.
All164 other function bodies, signatures/metadata/ACL, nonfunction DDL/columns,
all19 ORIGINAL and applied0001–0012 exact. Nonfunction expected catalog
**57e03fe369be4bd03116ce380e37a9b447a2bc1a72e3bbf2a70c7ac08d69e370** retained.
New installed full profile is unknown until actual source→installed comparison.
Old stock full profilec8a335b8… must not be reused as corrected expected result.

C3-NC-RUNTIME-01 remains OPEN. C2's new SENT/FAILED/UNKNOWN/incomplete/timezone/
calendar carriers and the unchanged strict C3 completed-delivery wrapper case
are collected, **NOT RUN** on corrected SQL. C2 lab ownership checks stopped before
asm_test/bootstrap/roles/reset/migrations/pytest. Two lab startup attempts are
disclosed, normal cleanup not attested; C0 does not transfer a cleanup/stock PASS.
New tasks do not authorize repairing, starting, reusing or cleaning unproven lab
resources. No used0013 DB in-place reapplication; future execution fresh owned DB.

### 0.3. Why these two disjoint source tasks precede execution

Existing runner selects only the two native DB modules. A run now would omit
all28 C3 API/runtime cases. C6 must include all four complete modules and retain
the same guarded reset/source/ownership/role/catalog/cleanup/TEST/budget boundary.

C1 explicitly identified three actual-evidence gaps, without a new product defect:
remaining five boundary HOLD/exhaustion cases, committed guarded send-begin
ACK loss with scheduling replay miss, and SQL→Python JSONB/digest edge vectors
and native material/File shapes. C3 adds focused PG carriers for those gaps,
keeping every existing case intact. Production logic does not change.

Current91 is a starting inventory, not a fixed total. New C3 cases must appear in
the final four-module collection and execution automatically. No lowering counts,
selection, xfail/skip or reclassification of collection as PASS.

### 0.4. Repository, branches and starts

Repository **Elefesys/ai-service-manager**. New C0 preparation is a sole-parent
descendant of **15a8ea7a12f01644250315e26d3d6c5cc487b59e**, changing ONLY
docs/tasks/M3_HANDOFF.md and docs/TASK_REGISTER.md;286 other blobs/modes unchanged.
Canonical tasks provide the full created preparation commit/tree.

| Branch | Purpose / start |
|---|---|
| c0/m3-1-native-context-pg-prep-r1 | New current C0 instruction/source checkpoint |
| c3/m3-1-native-context-runtime-pg-r2 | Same new prepared SHA/tree; append-only runtime PG tests |
| c6/m3-1-native-context-db-stock-runner-r3 | Same new prepared SHA/tree; only runner + runner tests |
| c2/m3-1-native-context-db-r3 | Returned15a8ea7a; C2 HOLD |
| c1/m3-1-native-context-runtime-review-r1 | Reviewed2258799; C1 HOLD |

Each executor uses a separate clean checkout and exact base, normal FF/expected head,
no amend/rebase/force. No assumptions about another chat's disk/environment/memory.
C3 and C6 do not follow or edit each other's branches; C0 later consolidates.
Main **e205e22051bc06295758b504d84699652b176c15/schema0012** and execution
**bde0c48af74f23cd6430fc669ea4635e21aa68c6** remain unchanged; PR34 closed/merged.

Read current HANDOFF§0/TASK_REGISTER, AGENTS/IMPL-001, original11/SOURCE_MANIFEST,
applicable original Spec5.8–5.14/5.12.1/18.5–18.9/24.7, ADR002–007/024–026/180/266/267,
MVP GJ-G/J+variants, Roadmap/Plan M3.1/M3.2, accepted full contract§16 through§16.20
and MATERIAL boundaries. Historical proposed/status headings do not override
subsequent exact C0 acceptance. Source tasks below grant no actual PG/Actions run.

### 0.5. C3 test-only task

**C3-M3.1-NATIVE-CONTEXT-RUNTIME-PG-R2 — test-only evidence gaps, no runtime correction.**

Repository Elefesys/ai-service-manager. Branch **c3/m3-1-native-context-runtime-pg-r2** starts at the exact C0 docs-only preparation SHA/tree in the canonical task, sole parent **15a8ea7a12f01644250315e26d3d6c5cc487b59e**. Separate clean checkout, verify full HEAD/tree; normal FF/expected head, no amend/rebase/force. C1 reviewed2258799; the prepared source also contains C0-reviewed C2 UTC6 correction. Do not revert it or follow moving C6 head.

**One existing write path only:** tests/test_m3_1_native_context_runtime_postgres.py.
**Append-only:** preserve the entire12965-byte prefix SHA256 **30fc57c7a69521130faedc48da7d8d90766d7e9deb940a691fc4ce03da746a1f**, all16 existing runtime node IDs/AST/assertions/fixtures. Add new helpers/tests below it; local imports inside appended helpers/tests are allowed. Existing12 API cases,63 native source/DB cases, backend, SQL, contract, foundation, runner/workflow and all other files are frozen. No new files or refactoring of retained tests.

These are three concrete evidence gaps identified by C1; no additional confirmed product finding is asserted. The goal is executable actual-PG coverage on the existing guarded native fixture, for later consolidated stock execution:

1. **Terminal scheduling at every boundary.** Existing prepare tests cover HOLD and exhausted. Add the remaining five boundaries (accept, send-begin, escalation, test_prepare, test_finalize) × both variants. Use actual Python wrapper/Worker and SQL, with reachable capability-built saved inputs/receipts where required. Assert persisted terminal Job/result and token identity, no fresh lease/admission on historical replay, no adapter/send/new Job/intent/revision, unchanged attempts/first_started budget except the stated terminal transition, OPERATOR_REQUIRED then existing Takeover projection/DEAD non-revival. Respect saved acceptance/consumer/creation receipt precedence: select a state that actually reaches the intended boundary; never change production precedence to satisfy a test. Negative exhaustion injection may reuse the existing explicit test pattern, not fabricate successful authority/receipts.

2. **Committed guarded send-begin ACK loss with work-replay miss.** Drive actual begin to durable DISPATCHING/permit commit, inject loss after commit before the caller receives the permit, and execute the real Worker exception/replay path. Prove one begin, no returned permit/no adapter call/no blind second begin, work scheduling replay miss rather than a synthetic WAIT receipt, and persisted same Outbox/attempt. Exercise existing expiry/recovery capability to reach conservative UNKNOWN, with no resend/recreated intent and retained history. Any clock/expiry/transport seam must be explicit and bounded; never directly DML a successful permit/receipt or UNKNOWN outcome. Keep the original six WAIT-hit ACK-loss cases unchanged; this new case covers the distinct no-receipt path.

3. **Actual PostgreSQL JSONB → strict Python bytes/digest compatibility.** Add a finite table of independent closed-domain vectors comparing actual PostgreSQL jsonb::text UTF8 bytes/hash with native_jsonb: UTF8 key-length/order ties, Cyrillic, combining/astral Unicode, U+2028/2029, quote/backslash/control escaping, signed bigint endpoints, nested arrays/objects/null/bool. No float/Decimal/domain widening. Compare server bytes/hash directly; do not generate the expected result with the same Python implementation. Add capability-built BASE/GUARDED V3 snapshots with full Unicode OWNER_TEXT/current material/private File variants using existing permitted fixture/capabilities, then parse unchanged and compare persisted body/digest. Escalation request snapshot has its accepted closed unsigned shape: validate/compare its canonical body without inventing a digest field. Vector-only SELECTs must be labelled separately from capability-built saved evidence and must never fabricate stored production receipts. Reuse existing retained File/material scenario setup; no S3/provider I/O.

Use a few bounded fixtures/vector loops rather than one DB reset per literal vector. Reuse the unchanged native fixture/reset and actual asm_runtime/migrator behavior; do not introduce a second destructive entry point, bypass readiness, or use owner/superuser as application runtime. Preserve all caps, fixed waits,5 claims/15min/30s/backoff≤60, strict V1/V2/V3 parsers, UNKNOWN semantics and CONTROLLED-only scope. No artificial waits or unbounded polling.

**Verification now is source-only:** locked Python3.13/frozen existing dependencies, verify actual imported module path with explicit checkout PYTHONPATH; Ruff/format for the changed module; compile without checkout caches; collect the complete four modules (migrations, native DB, API PG, runtime PG) with no -k/-m/deselection/skips/xfail. Record node IDs and per-module counts, preserve all previous91 and report additions. Read/check that assertions reach real wrappers/SQL; use targeted source/unit checks only if needed for a concrete risk. Collection is NOT RUN, never PG PASS.

**Do not start PG, Docker, services, lab builds or cleanup controllers in this task.** The disclosed C2 lab ownership blocker is not a request to repair/bypass it or reuse a used0013 DB. Do not mutate execution ref, dispatch/rerun/cancel Actions, run full CI, create PR, change main/VM/shared DB/provider/S3/LLM/live send/deploy/renewal or launch other chats/agents. C6 separately extends the stock runner; C0 will consolidate/review both returns and separately authorize actual execution.

Return **REVIEW → C3 HOLD** with exact full commit/tree/parent, one-path append-only diff, old prefix/AST hashes and clean checkout, each gap→new node/assertion/real-vs-seam mapping, exact local commands/results/full collection delta, remaining NOT RUN. Any concrete production defect is a finding for C0 with minimal reproduction/owner/scope; do not fix it within this test-only task. C3-NC-RUNTIME-01 stays OPEN until actual corrected PG/interop acceptance. User owns merge.

### 0.6. C6 runner task

**C6-M3.1-NATIVE-CONTEXT-DB-STOCK-RUNNER-R3 — four-module carrier, source-only preparation.**

Repository Elefesys/ai-service-manager. Branch **c6/m3-1-native-context-db-stock-runner-r3** starts at the exact C0 docs-only preparation SHA/tree in the canonical task, sole parent **15a8ea7a12f01644250315e26d3d6c5cc487b59e**. Separate clean checkout, full HEAD/tree verification; normal FF/expected head, no amend/rebase/force. C3 separately appends runtime PG cases; do not follow or edit that branch.

**Exactly two existing write paths:**
1. scripts/native_context_db_catalog.py.
2. tests/test_native_context_db_runner.py.

Current runner MODULES selects only native migration/source and native DB tests. It would omit the12 API and16 runtime cases. Extend the closed required module set to exactly these four complete files:
- tests/test_m3_1_native_context_migrations.py;
- tests/test_m3_1_native_context_postgres.py;
- tests/test_m3_1_native_context_api_postgres.py;
- tests/test_m3_1_native_context_runtime_postgres.py.

Current approved source collects91 =7 source+56 DB PG+12 API PG+16 runtime PG. This is a starting inventory, **not a fixed total or ceiling**: later C3 append-only cases must be included automatically on the final consolidated source. No selected node subset, -k/-m filtering, deselection, skip/xfail, exclusion by marker or two-module fallback. Require every collected node's setup/call/teardown result and whole-run failure propagation; keep complete node-ID/per-module evidence, fail if any required module is absent. A PASS must contain all final collected nodes, not merely the starting91.

Preserve the existing single reset entry point in test_m3_1_native_context_postgres and prove that API/runtime imported native fixtures still resolve to that same guarded function. All resets must retain fresh source identity/clean checkout, owned Docker container+volume+image/labels/port/PID/start/system identifier, child URL/role/ownership guards and explicit reset opt-in before destructive action. If minimal guard wiring changes are necessary to support imported fixtures, they must strengthen or preserve the same boundary; no test-file monkeypatch that changes assertions or SQL, no new reset route. Keep restoration on exceptions. Include meaningful source-level/runner-unit coverage for four-module omissions and guard wiring, not only a self-asserted MODULES count.

Retain actual child ASM_ENVIRONMENT=TEST and real Settings construction tests (C0-NC-RUNNER-01 closed), current explicit PYTHONPATH/clean environment, actual LOGIN asm_runtime and asm_migrator with no inheritance/ownership, source archive/manifest, final clean checks, redaction, owned cleanup/failure receipts and current independent fresh catalog. Independent comparison must still cover all167 exact typed definitions/unique OIDs including generated verifier,45 tables/columns/nonfunction/security/ACL. Source expansion must read the approved corrected SQL, not hardcode old profile/body hashes or trust only installed self-report.

Approved R3 source body hashes:
projection **8d38da64c526acb61365aa06eb293d117e1d8af93b598b5a507da3a23bc17b51**;
nested validator **21492e85adeaf186bce6bbfdde7b89c8e70762c56f8ec28c6da54b3a5327f49c**;
verifier **527fce5681d5345369cd88b555a302df6d305ef8566cf12a666198eb64a6f4ac**.
Nonfunction **57e03fe369be4bd03116ce380e37a9b447a2bc1a72e3bbf2a70c7ac08d69e370** unchanged. New installed full digest remains unknown until an authorized actual run. No unrelated catalog/parser/guard rewrite is allowed.

Retain all40 existing runner tests and78 substantive subtests. Narrow adaptations to existing two-module collection fixtures/messages are allowed only to express the four-module requirement while keeping all prior failure assertions; add negative cases for omitting either API/runtime (even if remaining tests pass), partial/deselected/skipped/xfail/duplicate/failing setup or teardown, and future added cases being included. Verify guarded reset calls for all PG consumers and failure cleanup without starting any real service. Do not weaken source/event/ref/ownership matching, fixed budgets or cleanup gates to make mocks green.

**Frozen outside these two paths:** scripts/test_native_context_db.sh, .github/workflows/native-context-db.yml and all other workflows, exact stock pgvector image digest/extensions, Python/uv/deps/locks, bootstrap/roles, application/foundation/backend, all migrations/contract, all91 current source/DB/API/runtime cases and C0 docs. The workflow's single execution branch and20-minute whole-job cap remain unchanged; no schedule/dispatch/new lane, timeout/retry increase, install workaround or readiness0013 change.

Run locked Python3.13/frozen existing environment, verify intended module paths; full runner unit suite plus applicable source/catalog checks, Ruff/format only changed files, whitespace/clean-source and complete four-module collect-only to prove inclusion. Report exact commands/counts and all retained assertions. These local tests/mocks/collection are not PG/stock acceptance.

**No actual execution in this task:** do not start Docker/PG/lab/services, inspect/reuse/clean C2's unproven lab resources, change execution ref, dispatch/rerun/cancel Actions, run full CI, create PR or touch main/VM/shared DB/provider/S3/LLM/live/deploy/renewal. Previous one-use stock approval is consumed. C0 must first review this return and C3 PG additions, consolidate one immutable source, then issue a separate exact execution approval. No other chats/agents.

Return **REVIEW → C6 HOLD** with exact commit/tree/parent/two-path diff/clean checkout, retained40+78 assertion mapping and new negatives, full collection/per-module/guard evidence, actual local results and NOT RUN stock status. New failures outside this narrow runner change go to C0 as findings, not scope expansion. User owns merge.

### 0.7. Later gate and retained limits

C0 accepts both exact returns, checks disjoint diffs and existing cases, combines
one immutable source and reviews full collection/runner safeguards before a
separate exact stock execution approval. Until then execution ref is frozen.
Eventual actual run must cover full final native+API+runtime collection, corrected
UTC6 interoperability, added C3 cases, independent167/45 catalog including verifier,
actual LOGIN roles/reset proofs, owned cleanup and clean source. Report new installed
profile from actual PG serialization; retain all failing evidence and no rerun waiver.

[Historical stock acceptance](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6251867599) remains scoped
to bde0c48 and run39141370282/attempt1 SUCCESS57/57 (5 source+52 PG),40 runner+78 subtests.
C1-NC-DB-01/02 and C0-NC-RUNNER-01 CLOSED. First39136349844 remains FAIL56/57.
Old one-use approval consumed; no stock evidence transfers to the corrected/new code.

C6 coherent host/source/schema/operator pairing is a later task, distinct from runner
work. Foundation0012 refusal remains; C5 TS/UI, C8/full integration CI and user merge
remain later gates. Whole native application/runtime NOT VERIFIED; M3 IN_PROGRESS.
Contract9 CLOSED/Q01 RESOLVED and MATERIAL11 INTEGRATED/VERIFIED LOCAL/TEST retained.
D1 provider completeness/causality unverified; D2 conservative holds; D3
TEXT_ONLY/UNAVAILABLE/PARTIAL retained. A08/P01/P05/renewal/collector/account/A12 OPEN;
M4 out, IMPL-05 DEFERRED. All source/state/browser/foundation/request/worker caps
unchanged. No0014/applied migration edits, main/new PR/full CI/VM/shared DB/provider/
S3/LLM/live send/deploy/renewal/other chat-agent launch. Earlier sections are history.

<a id="0-текущая-выдача-c0--c1-review-и-c2-utc6-r3--2026-10-18-utc"></a>

## История — C1 review и C2 UTC6 R3 / 2026-10-18 UTC

**C1 и C2 ACTIVE по отдельным canonical tasks PR34; C3/C5/C6/C8 HOLD.**
[C0 disposition](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6252562993)
по [C3 return](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6252466443):
source/scope ACCEPTED FOR REVIEW, задача C3 в REVIEW. Приложение native
не INTEGRATED/VERIFIED; фактический PostgreSQL для новых API/runtime ещё NOT RUN.
Открыт один **C3-NC-RUNTIME-01/P2**: completed delivery в canonical recent history
выдаёт raw PostgreSQL timestamptz, который не соответствует строгому UTC6 DTO.

### 0.1. Проверенный source checkpoint C3

| Binding | Exact value / evidence |
|---|---|
| Source / tree | **225879990011f2e41f4c38e46308ffdd976a7393** / **57009c4990345768badb912c1c3ff0818edb4650** |
| Sole parent / tree | **ad1e28fc69179398a9dc6ca31ee91c32cdf512d3** / **9019dc8a469652122447828379b5477fdd6b6a78** |
| Source delta | 22 paths, 16 existing + 6 authorized NEW, +6162/−1092; 288 blobs, 266 old blobs/modes unchanged |
| C0 source verification | All 288 bytes/modes, exact Git tree/commit/archive, clean checkout and diff --check PASS |
| Source tar SHA256 | **6c53901982fe6836534efe603f0608754afc8048eb3b3c9c00a2bec36bd71af2** |
| C0 local checks | 222 PASS / 10.62s, no skip/xfail; Mypy 64, Ruff/format 69, current-source OpenAPI --check PASS |
| New PG carriers | 28 collected only / 7.60s: 12 API + 16 runtime. Actual PG NOT RUN; C3 environment BLOCKED |
| Frozen contract | 756397 bytes; SHA256 **e7f3796fcff8640ffca203266ecf7b5988f7ab1bd24850b12e923122abf5d281** |

C0 OpenAPI first imported an old editable package from a reused environment.
Explicit current-checkout PYTHONPATH and verified asm.foundation.__file__ gave PASS;
this is a corrected verification-environment issue, not a C3 product finding.
Python 3.13.14 and 57 installed external distributions matched frozen uv.lock.
Original 11 files matched SOURCE_MANIFEST and attached originals exactly.
Foundation delta is only two native route wiring lines: removing them restores the
parent bytes; DATABASE_SCHEMA_REVISION=0012, Settings and readiness/serve unchanged.
Existing native 57, all SQL, runner/workflow/operator/frontend/dependencies frozen.
Retained test changes add only replay seam/context_hold fixture; no assertion removal.

### 0.2. C0 disposition and one open interoperability finding

C3-NC-RUNTIME-01/P2 is confirmed by source/strict codec evidence, not a new PG run.
In current 0013 line 1265, platform.human_context_projection(uuid,uuid,timestamptz)
inserts raw b.completed_at into recent.delivery. PostgreSQL REL_18_6 JSON encoding
uses XSD dates with a signed offset, including +00:00, and variable fractions.
Accepted DeliveryResponse/Timestamp requires YYYY-MM-DDTHH:MM:SS.ffffffZ.
The paired human_context_snapshot_valid(jsonb,text) nested delivery check at
1736–1738 accepts broader finite ISO spellings. Producer and validator form one P2.

Reachable state: completed manual delivery in canonical recent tail → full R and
Resume → new Client Turn → strict V3 parser rejection before consume/send.
OWNER_TEXT does not remove canonical recent history. C0 ran the re-signed V3
unit regression: raw offset rejected, UTC6 accepted, UNKNOWN preserved.
The existing actual-wrapper test_python_native_v3_completed_delivery_history_is_contract_utc6
is collected, strict and unmodified; actual execution remains pending.

C0 authorizes only the unmerged 0013←0012 correction below. No 0014, no edits to
applied 0001–0012 or ORIGINAL restoration bodies, including the similar raw
completed_at expression around original line 708. No mutation of saved snapshots
or receipts and no in-place reapplication to any previously used 0013 database.
Fresh owned disposable LOCAL/TEST DB is required for new actual evidence.

Approved pre-correction SQL expansion: 167 functions / 45 tables / 955 commands;
0013 has 198 op batches / 53 final definitions, 35 additions / 18 replacements.
Only two semantic bodies and their generated verifier consequence may change:
- human_context_projection body SHA256 **2ad43cb844a4676fe4d9bc0e5fe8d0d30736e5f306aa7ce5bbab12a32528e4c1**;
- human_context_snapshot_valid body SHA256 **56ae7479219928bdc1e2bc091efc29a6a6b4011e91509395cb973f5a4dc0f006**;
- generated human_context_schema_profile body SHA256 **d485135ecccf986a2b16e71dd451f95508847bb455f8fbf987cf5092ec5de8a6**.
Nonfunction catalog SHA256 **57e03fe369be4bd03116ce380e37a9b447a2bc1a72e3bbf2a70c7ac08d69e370**
and all other bodies/signatures/DDL/ACL/roles/RLS stay exact. Historical full profile
c8a335b808f11b0c6f3d784731ddc95bf1023e6f1881aff5448659388f927a7a
must not be reused as the expected new profile after correction.

### 0.3. Repository, branches and exact starts

Repository **Elefesys/ai-service-manager**. C0 docs-only preparation is a
sole-parent descendant of **225879990011f2e41f4c38e46308ffdd976a7393**, changing
ONLY docs/tasks/M3_HANDOFF.md and docs/TASK_REGISTER.md; all 286 other blobs/modes
remain exact. Canonical task comments supply its full commit and tree after creation.

| Branch | Purpose / start |
|---|---|
| c0/m3-1-native-context-runtime-followup-r1 | Current instructions; new C0 docs-only preparation |
| c2/m3-1-native-context-db-r3 | C2 correction; exactly the same new preparation SHA/tree |
| c1/m3-1-native-context-runtime-review-r1 | C1 immutable code target **225879990011f2e41f4c38e46308ffdd976a7393**, tree **57009c4990345768badb912c1c3ff0818edb4650** |
| c3/m3-1-native-context-runtime-r1 | Returned source **225879990011f2e41f4c38e46308ffdd976a7393**; C3 HOLD |

C1 reads this current instruction snapshot separately from its code target.
C2 does not modify C1 target; C1 does not follow moving C2 head. Separate clean
checkouts, normal FF with expected head; no amend/rebase/force or assumption of
shared disk/memory. Main remains e205e22051bc06295758b504d84699652b176c15/schema0012.
Execution c0/m3-1-native-context-db-stock-r1 remains
bde0c48af74f23cd6430fc669ea4635e21aa68c6. PR34 remains closed/merged.
New branches do not authorize Actions or movement of the execution ref.

Before work read AGENTS, IMPL-001, current HANDOFF§0/TASK_REGISTER, original 11
and SOURCE_MANIFEST, applicable Spec/ADR/MVP/Roadmap/Implementation Plan and
full accepted M3_CONTRACT§16 including §16.11–16.18; preserve MATERIAL boundaries.
Historical PROPOSED/status headings do not override subsequent exact C0 acceptance.
C2 and C1 scopes below are disjoint; C0 does not launch other chats or agents.

### 0.4. C2 correction scope

C3-NC-RUNTIME-01/P2 OPEN. Review target225879990011f2e41f4c38e46308ffdd976a7393/tree57009c4990345768badb912c1c3ff0818edb4650 contains C3 consumers but frozen DB-R2 SQL. C0 source/scope intake is accepted as this correction base; full runtime is not accepted. Work from the exact C0 docs preparation SHA in the canonical task, separate checkout, normal FF/expected head, no amend/rebase/force. Branch **c2/m3-1-native-context-db-r3**.

Exactly FOUR existing write paths:
1. migrations/versions/0013_native_context.py.
2. tests/test_m3_1_native_context_migrations.py.
3. tests/test_m3_1_native_context_postgres.py.
4. docs/tasks/M3_CONTRACT.md — append-only §16.19+ correction/evidence, preserve entire756397-byte prefix SHA256e7f3796fcff8640ffca203266ecf7b5988f7ab1bd24850b12e923122abf5d281.

C0 explicitly authorizes correction of **unmerged0013←0012**, no0014. Main applied0001–0012, ORIGINAL restoration bodies (including similar raw delivery JSON around original line708), signatures/DDL/ACL/roles/locks/caps frozen. Do not globally replace completed_at; edit the actual new native projection only. Existing used0013 DB is not an upgrade target: no deleting usage/reapplying changed source in place. Fresh owned disposable DB only.

In **platform.human_context_projection(uuid,uuid,timestamptz)**, recent.delivery.completed_at must use the existing `to_char(... AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"')` convention, preserve JSON null for incomplete delivery. Normalize the producer representation before normal V3 digest computation; no Python post-read normalization/re-sign, no mutation of historical snapshot/receipt bytes.

In **platform.human_context_snapshot_valid(jsonb,text)**, align ONLY nested recent.delivery.completed_at with the accepted strict UTC6/finite/calendar contract, retaining closed null/status/error/type semantics and existing fail-closed exception handling. Offset/variable-width fractional/noncanonical/invalid-calendar spellings must be rejected even when the entire candidate body is correctly re-signed; valid exactUTC6 accepted. Retained member ingress_at/private V1/V2 timestamp codecs and other semantic validation are outside this correction. Do not widen shared Python Timestamp or permissively cast before comparison.

These TWO semantic function bodies plus deterministic generated **human_context_schema_profile()** consequences are the entire allowed SQL change. Preserve all other expanded commands/bodies, including already corrected Resume projection priority/mapping; compare exact function-body delta to approved DB-R2. Counts stay167 functions/45tables/955 replayed commands (0013:198 op batches/53final definitions),35 additions/18 replacements; no new catalog objects. Nonfunction catalog SHA256 **57e03fe369be4bd03116ce380e37a9b447a2bc1a72e3bbf2a70c7ac08d69e370** unchanged. Recompute generated full-profile/body hashes; independently verify source/installed definitions when PG is actually run. Old full profilec8a335b8… and verifierd485135e… are historical, not a new expected PASS.

Regression requirements:
- Preserve original57 native cases and all their substantive assertions/setup/teardown/reset guards. Append focused cases; no test selection/xfail/skips or removal of checks. Update source-freeze carrier narrowly to allow the two named semantic bodies+generated verifier while proving all other accepted R2 SQL byte-exact; retain original R1/R2 corrections, applied-source and ORIGINAL checks.
- Actual capability-built manual delivery → recent tail → R/Resume/new Turn → native V3 should preserve SENT/FAILED/UNKNOWN status/error/version while emitting exactUTC6 for completed_at; null remains null for PENDING/DISPATCHING. Do not fabricate successful state/permit/receipt by direct DML. Test seams may produce controlled transport outcomes; label them accurately.
- Cover UTC and non-UTC session TimeZone, zero and fractional microseconds, calendar validity, null/status pairing and otherwise-valid re-signed nested completed_at negatives in relevant BASE/GUARDED/ESCALATION validators. Strict Python DeliveryResponse/V3 must consume the produced canonical data unchanged.
- Existing C3 case **tests/test_m3_1_native_context_runtime_postgres.py::test_python_native_v3_completed_delivery_history_is_contract_utc6** must remain unmodified and pass with the corrected DB when executed. Whole C3 API/runtime files are frozen (28 current collected cases), no parser/test weakening to hide the mismatch.
- Do not change current SQL/source/browser/worker budgets. No new completion locks, side effects, send outcomes, generation/version behavior or scope expansion.

Use locked Python3.13/frozen dependencies, targeted unit/source checks, Ruff/format/typing as relevant, exact diff/clean-source. Verify the intended checkout's actual imported module path if using an external editable environment; current C0 OpenAPI check required explicit PYTHONPATH.

Actual PG only with your owned disposable LOCAL/TEST asm_test, actual asm_runtime+asm_migrator LOGIN, existing source/role/ownership/reset guards and explicit owned opt-in. If available, capture RED on exact pre-correction source and GREEN after correction, full current native carrier plus complete28 API/runtime cases, not just failing node. Report exact source/tree/versions/counts/times/SQLSTATE and any lab startup patch; lab is not stock parity. If unavailable, honest NOT RUN/BLOCKED with executable carriers; no install/probe loop or invented PG PASS. Unexpected failures outside this narrow correction are exact findings for C0, not permission to alter C3 consumers.

No stock execution-ref mutation/Actions/dispatch/rerun/cancel/full CI/new PR/main/VM/shared DB/provider/S3/LLM/live send/deploy/renewal or other agent/chat launch. No backend/foundation/OpenAPI/frontend/runner/workflow/bootstrap/images/deps/locks/operator/C0 docs writes. Existing57 native assertions, C3 code/tests and original11 remain frozen except explicit four-path delta.

Return **REVIEW → C2 HOLD**: exact commit/tree/parent/four-path diff/clean checkout; P2 producer+validator→regression node mapping; exact changed expanded function bodies and generated profiles, all unaffected SQL/DDL/ORIGINAL/applied hashes preserved; actual commands/results and PG limitations. C3-NC-RUNTIME-01 stays OPEN until C0 source review plus actual corrected PG/interop evidence. C0 consolidates with C1 read-only review before issuing stock/runtime or host/operator work.


### 0.5. C1 independent review scope

**Exact code target225879990011f2e41f4c38e46308ffdd976a7393, tree57009c4990345768badb912c1c3ff0818edb4650**, sole parentad1e28fc69179398a9dc6ca31ee91c32cdf512d3. Review branch **c1/m3-1-native-context-runtime-review-r1** is created at this exact target. C0 current instructions live in the separately named docs-only preparation SHA/branch; read that HANDOFF§0/REGISTER first. Do not substitute a moving C2/head for this review target. Separate checkout, clean tracked/untracked source.

Read AGENTS/IMPL-001, original11/SOURCE_MANIFEST/attached originals, applicable Spec5.8–5.14/5.12.1/18.5–18.9/24.7, ADR002–007/024–026/180/266/267, MVP GJ-G/J+variants, Roadmap/Plan M3.1/M3.2, accepted full contract§16 including§16.11–16.18 and MATERIAL retained boundaries. Current full contract756397 bytes SHA256e7f3796fcff8640ffca203266ecf7b5988f7ab1bd24850b12e923122abf5d281. Contract9/Q01 and MATERIAL11 closures are not reopened without a concrete source-backed contradiction.

**No repository write paths.** Inspect all22 C3 changed paths and relevant unchanged SQL/runtime/auth/Audit/query/test consumers. Source diff22 paths,+6162/−1092;288 blobs/266unchanged. Foundation only native route import/install, schema0012 readiness unchanged. This task permits local read-only source probes/targeted unit checks for a concrete finding; no PG/reset/Docker/services/Actions/full CI/new PR/ref changes. Return review in PR34; do not implement corrections or modify C0 docs. No other chats/agents.

Known OPEN **C3-NC-RUNTIME-01/P2**: raw SQL recent.delivery.completed_at versus strict UTC6; C2 is separately assigned producer+paired nested validator correction. Verify its relevance and scope, do not duplicate it under a new ID or treat it as permission to relax Python/parser/digest. C0 needs independent assessment of the rest of the C3 delivery, with any additional confirmed findings assigned finite reproduction/impact/fix boundary. Current target remains old SQL until separately reviewed C2 return.

Review priorities:
1. Three routes: trusted live OWNER/session/UOW/C/Client/R relations; revoke/cross-ws/same-ws-other-Client; raw4096/header16384/body3s/request10s; exact query/key/If-Match/cookie/CSRF/duplicate-safe JSON order; PAUSED HUMAN save/no send entitlement; outer commit before200 and historical replay before fresh policy/CAS.
2. Opaque cursor original bytes≤1024, exact unpadded Base64URL/UTF8/key order/duplicate/type rejection; strict native object before SQL, relation/P/epoch authority in SQL; same snapshot/fixed through_N and response validation; no widening billing codec or leakage.
3. Exact V1/V2/V3 dispatch and retained bytes/counts; strict full typed R/history/current/File/delivery/coverage/order/limits; independent PostgreSQL-jsonb serialization/digest compatibility across representative Unicode/escaping/integer vectors, 2,097,152/64/16, no OWNER_TEXT truncation or parser fallback. Check actual consume_guarded allowlist, TEST counts and Escalation V3 behavior.
4. Six wrapper boundaries and Worker: saved accepted/creation/consumer replay first, then token-only scheduling replay in a short physical transaction without admission/new lease/owner impersonation; valid tuple identity, commit/ACK-loss/rollback/unknown result. Check old-schema optional-capability lookup is only retained compatibility, never readiness or used-policy bypass. No new permit from replay, no retry send-begin on miss, DISPATCHING/UNKNOWN preserved;5claims/15min/30s/backoff≤60/same Job/intent/revision, stop after WAIT/HOLD/exhausted and0adapter calls.
5. Resume exact old body/fingerprint/receipt/product/CAS/overflow precedence and closed P2401 mappings; known C1 DB priority/mapping fixes retained; raw NEW_OBSERVATION only in read/worker where specified.
6. Escalation read/list required nullable context_hold/can_resolve, same query/waiting V, terminal/timer/CANCEL/old replay and Takeover-once; no new connection edge in completion/SENT/File, CONTROLLED-only producer unchanged.
7. Typed Python Audit union actor/object/version/payload/redaction; generic unchanged billing service/query paths truly consume it. Generated OpenAPI against current create_app and exact public closed schemas/errors/nullables. TS/UI unchanged is an explicit later gate, not accidental acceptance.
8. Tests: identify real scenario/assertion gaps or failures in28 executable PG cases and focused local222 suite; verify meaningful six-boundary late-token/ACK/commit/no-adapter assertions. Do not call collection/mocks actual PG/HTTP-with-DB evidence. Existing57 stock carrier does not prove new wrappers.

C0 independently reproduced222 local PASS and28 collection, Mypy64/Ruff+format69/current-source OpenAPI PASS. C3 actual PG NOT RUN/environment BLOCKED; C0 also has no new PG/stock result for2258799. Historical bde0c48 run39141370282 SUCCESS57/57 remains checkpoint-specific. Unit/source review cannot close new runtime gate or P2 merely from test count.

Return **PASS for scoped source review** or **CHANGES_REQUESTED**, with exact target/tree/readbacks, finding IDs/severity/path+line, finite input/state→actual→expected/impact, minimal correction owner/paths and executable regression guidance. Separate confirmed facts, inference and NOT RUN; account for known P2 and retained closures. No new confirmed finding is not application/PG acceptance. Provide concrete C3/C2/C6/C5 handoff, then **C1 HOLD**. C0 integrates/authorizes later execution; user owns merge.


### 0.6. Retained acceptance, later gates and limits

[C0 stock acceptance6251867599](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6251867599)
remains scoped to bde0c48af74f23cd6430fc669ea4635e21aa68c6:
[run39141370282/attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/39141370282)
SUCCESS, 57/57 native (5 source + 52 PG), 40 runner tests + 78 subtests;
actual foundation0013 refusal, independent 167/45 catalog, roles, reset guards,
owned cleanup and clean source PASS. C1-NC-DB-01/02 and C0-NC-RUNNER-01 stay CLOSED.
Historical run39136349844 stays FAIL56/57. Prior one-use approval is consumed;
there is no current permission for another run or execution-ref movement.

C0 consolidates exact C1 and C2 returns and any additional findings first.
Then a separate assignment must cover complete native + all new API/runtime cases
on the corrected source and independent changed catalog, with actual stock evidence.
C6 coherent host/source/schema/operator pairing, C5 TS/UI and C8/full integration CI
remain later gates; user owns merge. Foundation0012 refusal is retained until C6's
explicit coherent pairing; no current application readiness or rollout claim.

M3 IN_PROGRESS; native application/runtime NOT VERIFIED. Contract 9 findings CLOSED /
Q01 RESOLVED and MATERIAL 11 INTEGRATED/VERIFIED LOCAL/TEST remain scoped and retained.
D1 provider completeness/causality unverified; D2 conservative holds;
D3 TEXT_ONLY/UNAVAILABLE/PARTIAL limitations retained. A08/P01/P05/renewal/collector/
account/A12 OPEN; M4 outside scope; IMPL-05 DEFERRED.
All fixed source/browser/state/foundation/worker and SQL/request caps unchanged.
No full CI/new PR/main/VM/shared DB/provider/S3/LLM/live send/deploy/renewal or
other agent/chat launch. Earlier sections are historical, not active assignments.

<a id="0-текущая-выдача-c0--native-runtime-r1-после-stock-db-pass--2026-10-18-utc"></a>

## История — native runtime R1 после stock DB PASS / 2026-10-18 UTC

**C3 ACTIVE по exact canonical task PR34; C1/C2/C5/C6/C8 HOLD.**
[C0 actual disposition](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6251867599): C0-NC-RUNNER-01/P2 CLOSED;
C1-NC-DB-01/02 CLOSED. DB/runner checkpoint VERIFIED LOCAL/TEST.
Native application/runtime NOT VERIFIED; M3 IN_PROGRESS.

### 0.1. Принятый checkpoint и evidence

C6 R2 **bde0c48af74f23cd6430fc669ea4635e21aa68c6**,
tree **f2be86c21f754e7997aa4a04ee07d0952fefe940**, sole parent
**e7c2730bd61f0fd9f023a226700c9a81f4b12beb**. Только2 source paths,+64/−1:
runner explicit child TEST + real Settings regressions;280 other blobs/modes unchanged.
C0 verified all282 bytes/modes, exact tree/archive; all38 prior test ASTs retained.
Local45 tests+78subtests/Ruff/format/whitespace PASS; local evidence не PG.

[Approval](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6251780231) consumed once by normal FF execution ref
bbc3d42a5cd13736928a6a57f02e299a9c92a0a4→bde0c48….
[Run39141370282/attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/39141370282):
**SUCCESS,57/57 native PASS** (5 source+52 actual PG),0skip/xfail/deselection;
runner40 tests+78subtests PASS/2.50s. JUnit40 testcase elements;118 includes subtests.
Job117716323052 all13 steps SUCCESS; payload329.164s,receipt358.535s within20m.
Actual unchanged foundation Settings constructs TEST and RuntimeDatabase.check()
rejects0013 in test_fresh_catalog_exact_security_and_foundation_fail_closed PASS.
C0-NC-RUNNER-01 CLOSED; complete stock DB carrier gap closed. All5 C2 corrected
Resume PG cases PASS again. Historical run39136349844 remains FAIL56/57,
foundation refusal then NOT REACHED; no rerun/reclassification.

Unchanged pinned stock PG18.6/vector0.8.6/btree_gist1.8; Python3.13.16/uv0.10.0/
frozen deps/Docker28.0.4. Actual asm_runtime+asm_migrator LOGIN,0memberships/
runtime ownership;52 revalidated pre-reset proofs, owned cleanup/clean source PASS.
Independent167 typed functions/unique OIDs incl executable verifier and45tables/
ordered catalog PASS. Full profile
**c8a335b808f11b0c6f3d784731ddc95bf1023e6f1881aff5448659388f927a7a**;
nonfunction **57e03fe369be4bd03116ce380e37a9b447a2bc1a72e3bbf2a70c7ac08d69e370**;
verifier body **d485135ecccf986a2b16e71dd451f95508847bb455f8fbf987cf5092ec5de8a6**.

[Artifact12142480040](https://github.com/Elefesys/ai-service-manager/actions/runs/39141370282/artifacts/12142480040):
2932595 bytes/37 files,expires2026-10-25,ZIP SHA256
**a1177528f52e11d26e769a4d1da865944415018277d0ce6e2ad898a76d7e1406**.
C0 independently verified all archived source bytes/modes/manifest, full source
expansion/installed bodies/OIDs/ACL/catalog, all test phases/JUnit/roles/cleanup.
Source tar SHA256 **c1031b8dcd64372047dafce60c069b60f0e89e2d825cd9b3132e6f72daa4bbb2**;
manifest **315a8f29df3a9ec3b12a6f949ae9f43f6d36224d88c8fcfc3c60c8e8284bc6ba**.
Green DB scope не доказывает paired API/worker/host/Console readiness.

### 0.2. Repository / branch / exact start

Repository Elefesys/ai-service-manager. C0 docs-only preparation is a sole-parent
descendant of **bde0c48af74f23cd6430fc669ea4635e21aa68c6** and changes ONLY
docs/tasks/M3_HANDOFF.md and docs/TASK_REGISTER.md;280 code blobs/modes unchanged.
Full prepared start SHA/tree supplied by canonical C0 task in PR34. Branches:
- coordination c0/m3-1-native-context-runtime-prep-r1;
- task **c3/m3-1-native-context-runtime-r1**, identical prepared start.

Separate checkout, verify exact full HEAD/tree; normal FF with expected head,
no amend/rebase/force. Do not assume other chats' disk/environment/memory.
Main remains **e205e22051bc06295758b504d84699652b176c15/schema0012**.
Execution c0/m3-1-native-context-db-stock-r1 and C6 R2 delivery stay bde0c48…;
old C0 candidate bbc3d42…/C2/C6 deliveries remain frozen; PR34 closed/merged.
No execution permission is conveyed by the new task branch.

### 0.3. C3 implementation scope

**C3-M3.1-NATIVE-CONTEXT-RUNTIME-R1 — реализация Python/API/V3/worker/Audit на принятом DB checkpoint.**

Сначала прочитать AGENTS, актуальные HANDOFF§0/TASK_REGISTER/IMPL-001; original11 и SOURCE_MANIFEST; Spec5.8–5.14/5.12.1/18.5–18.9/24.7, ADR002–007/024–026/180/266/267, MVP GJ-G/J+variants, Roadmap M3/M4, Implementation Plan M3.1/M3.2; accepted M3_CONTRACT§16 целиком, включая DB§16.11–16.18 и MATERIAL§15.2–15.9/§15.18. Заголовок PROPOSED/исторические статусы в frozen contract не отменяют последующую приёмку C0. Норма — принятый exact contract и actual0013; C1 consumer handoff6249871164 уточняет реальные paths, а не разрешает расширить protocol.

**Разрешённый результат:** coherent source checkpoint всех Python consumers, трёх native routes, retained Resume errors, Escalation projections и Python Audit/OpenAPI. Это ещё не merge/deploy/runtime readiness acceptance. C6 затем отдельной выдачей pair-ит exact host/source/schema/operator profiles; C5 после accepted API pair-ит TS/UI. Не делать частичный V3 через legacy parser и не объявлять готовность всего приложения.

**Write allowlist — существующие31 пути:**
```text
backend/src/asm/conversations/control.py
backend/src/asm/conversations/http.py
backend/src/asm/conversations/http_models.py
backend/src/asm/conversations/turns.py
backend/src/asm/conversations/guards.py
backend/src/asm/conversations/material.py
backend/src/asm/conversations/escalations.py
backend/src/asm/conversations/escalation_http.py
backend/src/asm/conversations/escalation_http_models.py
backend/src/asm/tenancy/database.py
backend/src/asm/messaging/database.py
backend/src/asm/messaging/worker.py
backend/src/asm/messaging/results.py
backend/src/asm/messaging/errors.py
backend/src/asm/telegram/database.py
backend/src/asm/billing/models.py
backend/src/asm/billing/service.py
backend/src/asm/billing/queries.py
backend/src/asm/billing/validation.py
backend/src/asm/foundation.py
contracts/openapi.json
tests/test_m3_1_control_postgres.py
tests/test_m3_1_control_api_postgres.py
tests/test_m3_1_guards_postgres.py
tests/test_m3_1_turns_postgres.py
tests/test_m3_2_escalations_postgres.py
tests/test_m3_2_escalations_api_postgres.py
tests/test_m3_1_turns.py
tests/test_m3_1_guards.py
tests/test_m3_2_escalations.py
tests/test_m3_1_provenance_postgres.py
```

**NEW6 путей (создавать только реально используемые):**
```text
backend/src/asm/conversations/native_context.py
backend/src/asm/conversations/native_context_http.py
backend/src/asm/conversations/native_context_http_models.py
tests/test_m3_1_native_context.py
tests/test_m3_1_native_context_api_postgres.py
tests/test_m3_1_native_context_runtime_postgres.py
```

Новый runtime PG carrier отделён от уже принятого DB carrier. `tests/test_m3_1_native_context_postgres.py` и `test_m3_1_native_context_migrations.py` полностью frozen: все57, включая actual foundation0013 refusal. Не переименовывать прежний файл как новый и не ослаблять fixtures/assertions. Existing allowlisted tests менять лишь для точного нового DTO/consumer contract и добавленных regressions, сохраняя retained assertions/scenarios; не массово обновлять expectations ради зелёного результата.

**Обязательные implementation boundaries:**

1. `GET /human-context`, `GET /human-context/observations`, `POST /human-context/reconcile` под существующим workspace/conversation prefix. Live OWNER/session/relation/UOW, cookie/CSRF, exact query/key/If-Match/body порядок, strict shared primitives/closed unions/nullable keys по§16.4. Реальные raw-body4096 bytes, headers16384/body3s/request10s остаются; новый route не наследует messages65536. Reconcile не требует manual-send entitlement, не делает Resume/Takeover/send; PAUSED HUMAN save допустим. Все writes через назначенные capabilities, commit до200. Missing/wrong same-ws Client/R relation не раскрывается. Full body/key/actor historical replay first после live authority, без current-state optimism.

2. Canonical observation cursor≤1024 encoded ASCII bytes: exact unpadded Base64URL, strict UTF-8 JSON с duplicate-key rejection и exact ordered keys `v,ws,C,Client,P,through_N,after_N`; re-encode byte-equal, v строго int1. Передавать SQL decoded closed object; ws/C/Client/P/through/after relations и snapshot bounds остаются DB authority. Новый typed codec не должен расширить существующие billing cursor contracts. Unknown/duplicate/empty query422; P mismatch409 CONTEXT_CURSOR_STALE; scope403/404 как§16.4. Никаких provider IDs/raw JSON/private pointers в page/Audit.

3. Exact snapshot dispatch: absent schema_version→retained V1; integer2→V2; integer3→V3; bool/float/unknown/null/extra rejected. Pair `parse_snapshot`, `parse_guarded_snapshot`, exact `consume_guarded` type allowlist, TEST `consume`/finalize counts и Escalation validator. Полные typed R+recent history, current/material/File/WINNER semantics, exact body/digest/2,097,152-byte bound/64 members/16 history и strict ordering/IDs. OWNER_TEXT целиком, без trim/NFC/truncation. V1/V2 saved bytes/results/counts не менять; V3 READY/PENDING counts по current image availability. Существующие V2 normalizer/hash не редактировать.

4. Все три closed ContextWorkResult variants, permanent reasons и CONTEXT_INPUT_PENDING. Шесть boundaries: guard prepare/accept/send-begin, Escalation producer, TEST prepare/finalize. Persist/commit scheduling до return/continuation; zero adapter calls при WAIT/HOLD/exhausted. Existing accepted/creation/consumer replay first; затем token-only `human_context_work_replay` на trusted short physical transaction **без messaging_admit, новой lease/owner impersonation**; оба misses — только retained bounded fresh path. Send-begin ACK loss остаётся DISPATCHING/UNKNOWN recovery, не новый внешний вызов. No internal polling/retry loop/new Job/intent/revision;5claims/15min/30s/backoff≤60, same identity и failure-preserving commit semantics. Late/losing token после clear/maintenance не resurrect work.

5. Resume сохраняет exact three-field body/fingerprint/receipt и прежние product/CAS/overflow/replay priorities. Closed P2401 mapping отражает corrected SQL: applicable PAUSED→HUMAN_REQUIRED→remaining context; CONTEXT_CHANGED/NEW_OBSERVATION в public Resume→CONTEXT_CONFIRMATION_REQUIRED. Raw read arrays и worker NEW_OBSERVATION не переименовывать. Никакого force/optional R/legacy bypass при used policy.

6. Escalation nullable `context_hold` в каждом read/list item и `can_resolve` с hold; read same snapshot/waiting V. Retain validity/FINAL/EXPIRED/timer/CANCEL/replay/Takeover-once/RESOLVE precedence; context не становится новым lifecycle и не меняет CONTROLLED-only producer gate. Completion/SENT/File не получает connection lock. Current automation_work projection типизирована, DEAD не оживляется и не обещает queued continuation.

7. Python Audit closed variants HUMAN_CONTEXT_RECONCILED и HUMAN_CONTEXT_POLICY_COMMANDED: actual typed actor/object_version/payload, модели+service+queries; protected text/digest/provider IDs не попадают в public Audit. Согласовать exact Python/OpenAPI ошибки/nullable/variants; TS/UI получает отдельную следующую выдачу, checkpoint unpaired до неё.

**Shared entrypoint authorization узкая:** `foundation.py` только import/install native routes в existing create_app. `DATABASE_SCHEMA_REVISION="0012"`, Settings/AuthSettings, RuntimeDatabase.check/serve/readiness/timeouts остаются byte/behavior-identical; не monkeypatch и не disable в production path. Это намеренно сохраняет0013 readiness refusal до C6 coherent host/schema pairing. API/worker PG tests могут использовать реальные модульные installers/DB wrappers и owned native fixture, но не называют это startup/readiness/full-stack PASS. Frozen old carrier проверяет отказ и после этой работы.

**Verification:** exact diff/scope/whitespace; locked Python3.13/frozen deps; Ruff/format и relevant strict typing; focused meaningful new unit/API/PG regressions плюс затронутые retained consumers. Проверить regenerated OpenAPI against real create_app, не ручная подмена snapshot. Сохранить authority negative cases (revoke/cross-ws/same-ws-other-Client), duplicate/unknown JSON/raw-byte caps/cursor bytes, whole-field hash vectors, stale G/V/P/N/input/R, replay after newer state, commit-failure rollback/no optimistic result, strict re-signed V3 negatives, real wrapper WAIT commit+lost ACK+single continuation+0adapter, old V1/V2/UNKNOWN/File и Escalation paths. Все6 scheduling boundaries — mapping к executable wrapper assertions. Counts не заменяют semantics.

PG только свой disposable LOCAL/TEST asm_test с actual asm_runtime/asm_migrator LOGIN, nonowner/NOBYPASSRLS, unchanged source/role/reset guards и explicit owned reset opt-in. Указать реальную среду/патчи/версии; labPG не stock parity. Если требуемая среда недоступна, оставить executable carrier и честный NOT RUN/BLOCKED, без install/probe loops, skip/xfail/fixture bypass/ложного PASS. Полный принятый DB57 runner разрешён C0 отдельно; **не двигать execution ref и не запускать Actions**. Никакого full CI/new PR/main/VM/provider/S3/LLM/send/deploy/renewal; fake платные состояния/receipt/permit запрещены. Instrumented adapters в tests — только наблюдаемый test seam, не live evidence.

**Frozen:** миграции0001–0013, tenancy security contract/SQL profiles, native57/stock runner/workflow/bootstrap/images/compose/deps/locks/CI/operator/frontend, original11/full M3 contract756397 bytes SHA256e7f3796fcff8640ffca203266ecf7b5988f7ab1bd24850b12e923122abf5d281. No0014. C0 docs вне write scope. При конкретной несовместимости outside allowlist — exact evidence/path/minimal request в return, без самостоятельного расширения. Существующие S600/P720/fixed120/+480/S+1200/cleanup90/state25/browser25/foundation45 и3s/60s/10s unchanged; M4out, IMPL-05DEFERRED.

**Return REVIEW → C3 HOLD:** full commit/tree/parent(s), exact path diff/clean source, requirement→implementation→node-ID table (особенно6 worker boundaries/replay/commit и3 routes), actual commands/counts/time/limitations, generated OpenAPI comparison, retained V1/V2 и proof, что foundation schema0012 по-прежнему отвергает DB0013, real PG vs mock/collection clearly separate, new OPEN findings and concrete C1/C6/C5 handoff. C0 принимает; затем scoped C1 security/API review, C6 host/operator и C5 UI; C8/full integration CI/user merge позже. Не запускать другие чаты/агентов. D1/D2/D3 сохраняют принятые пределы; A08/P01/P05/account/renewal/collector/A12 OPEN, M3 IN_PROGRESS.

### 0.4. Retained acceptance boundary

All9 contract findings/Q01 and MATERIAL11 closures retained. Native application
remains NOT VERIFIED; current checkpoint is not merge-ready/deployable.
C0 accepts returned exact source before issuing C1 review/C6 host/operator/C5 UI.
Only coherent reviewed composition receives later C8/full integration CI; user merges.
No automatic stock rerun or full CI. Previous assignments below are history.

<a id="0-текущая-выдача-c0--stock-runner-r2-после-одного-fail--2026-10-18-utc"></a>

## История — stock runner R2 после одного FAIL / 2026-10-18 UTC

**C6 ACTIVE: исправить только явный TEST environment дочернего runner.**
C1/C2/C3/C5/C8 HOLD. Оба C1 DB P2 CLOSED; один C0-NC-RUNNER-01/P2 OPEN.
[Source approval](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6251106119),
[actual run disposition](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6251192609).
Native runtime NOT VERIFIED; M3 IN_PROGRESS. Следующая выдача не запускает Actions.

### 0.1. Принятый source и actual stock evidence

C2 DB-R2 **861bdf4f77f907768b073eab1daa24cce59f9d3a**,
treefcbdb5c8e1acb889860ed46f6b7c2bb7e14275ae; C6 runner R1
**4ccbb40a69b74dca0bef730d82ac425309ee7554**,
tree18f0150f89b4d9ac82a9cae02ccad45fcec175be.
C0 exact disjoint composition **bbc3d42a5cd13736928a6a57f02e299a9c92a0a4**,
tree**f34ac327244a323697a602ea5fdab752f213fdb3**; parents C2 then C6.
Все282 blobs/modes проверены; исходники обоих returns не редактировались.

[Run39136349844/attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/39136349844),
job117701524374: **FAIL**. Native57 collected,56PASS/1FAIL,0skip/xfail/deselection;
52 PG setups/reset proofs, все setup/teardown PASS. Все5 новых C2 PG cases PASS.
Runner38 tests+76 subtests PASS. JUnit suite tests114 включает subtests;
это38 testcase elements, не114 независимых тестов. Carrier232.906s;
receipt whole-job elapsed260.532s в20m cap. Повтора не было.

Stock unchanged pinned PG18.6/vector0.8.6/btree_gist1.8; Python3.13.16/uv0.10.0/
frozen lock/Docker28.0.4. Real asm_runtime/asm_migrator LOGIN, zero memberships/
runtime ownership; independent installed167 unique OIDs/full typed functions incl
executable verifier,45 tables/full catalog PASS. Owned cleanup и clean source PASS.
Actual full profile **c8a335b808f11b0c6f3d784731ddc95bf1023e6f1881aff5448659388f927a7a**,
nonfunction **57e03fe369be4bd03116ce380e37a9b447a2bc1a72e3bbf2a70c7ac08d69e370**,
verifier body **d485135ecccf986a2b16e71dd451f95508847bb455f8fbf987cf5092ec5de8a6**.

Artifact12140326093,2935013 bytes, ZIP SHA256
**d043652088e71f026198022f80c3f53b0068e8510f9364481efd21a2263519d6**,
[38-file archive](https://github.com/Elefesys/ai-service-manager/actions/runs/39136349844/artifacts/12140326093),
retention2026-10-25. C0 verified all282 archived source bytes/modes, expected-source
manifest vs own approved-source expansion, installed definitions/catalog and cleanup.
Source archive SHA256 **e2e7ae6b9566ec6d3795b8f2f3a7546adf61bbef34a88c550608c20b295f51d3**;
manifest **906c10fe269148d730332e7ddcd0458731c5e6ed850be67f2028fd50d16e0fff**.
Evidence is checkpoint-specific; installed DB/profile PASS is not application/host readiness.

C1-NC-DB-01 CLOSED: source fixed priority +3 real PG cases incl retained OFF_UNUSED/
HUMAN/authority/CAS/no-write semantics. C1-NC-DB-02 CLOSED: resume-only mapping +
N-only Resume/no writes and worker permanent HOLD/replay cases. C2 HOLD.
The complete native carrier is still not PASS because its foundation check was not reached.

### 0.2. C0-NC-RUNNER-01/P2 — exact failure

Only failed node:
tests/test_m3_1_native_context_postgres.py::test_fresh_catalog_exact_security_and_foundation_fail_closed.
At line502 RuntimeDatabase(Settings()) raises ValidationError: environment missing.
Catalog/ACL/RLS assertions before it passed; RuntimeDatabase.check() and its expected
schema0013 rejection were NOT REACHED. No SQLSTATE; no new confirmed SQL finding.

scripts/native_context_db_catalog.py::child_environment builds an explicit allowlist
without ASM_ENVIRONMENT; child() then adds only owned reset opt-in/three URLs.
The unchanged Settings requires LOCAL/TEST. C0 reproduced without DB I/O:
exact current child + synthetic valid runtime URL → missing environment;
explicit ASM_ENVIRONMENT=TEST → Settings validates TEST.
Do not fix this by weakening Settings, changing foundation schema gate or test assertion.

### 0.3. C6-M3.1-NATIVE-CONTEXT-DB-STOCK-RUNNER-R2

Repository Elefesys/ai-service-manager. C0 preparation has sole parent
**bbc3d42a5cd13736928a6a57f02e299a9c92a0a4** and changes only HANDOFF/REGISTER.
Full start SHA/tree is in canonical C0 task PR34. C0 creates:
- coordination branch c0/m3-1-native-context-db-stock-followup-r1;
- task branch **c6/m3-1-native-context-db-stock-runner-r2**, same exact start.
Separate checkout; normal FF/expected-head, no rebase/amend/force.
Current execution/candidate branches remain frozen at bbc3d42… until a later C0 decision.
Old C2/C6 delivery refs remain frozen. Do not assume another chat's disk/environment.

Exactly TWO existing write paths:
1. scripts/native_context_db_catalog.py.
2. tests/test_native_context_db_runner.py.

Explicitly pin **ASM_ENVIRONMENT=TEST** in the isolated child configuration.
Do not copy the parent's arbitrary ASM/application/provider configuration.
Preserve no parent reset opt-in/URLs and grant owned URLs only after source/resource
guards. TEST is a local fixture setting, not a production or account permission.

Add a meaningful regression using the real unchanged foundation Settings construction
under the produced child environment and a clearly synthetic valid runtime URL, with
no engine connection or DB I/O. Cover parent environment absent and hostile/non-TEST;
child must remain TEST. Retain all38 existing guard cases/subcases and secret/reset/
foreign-source/resource negatives; do not replace real Settings with a permissive mock.
Use available locked Python3.13/frozen deps. If unavailable, return exact limitation;
do not skip/xfail/mask the new test or claim PG proof from configuration validation.

Do not edit native tests/0013/contract/foundation/AuthSettings/.github workflows/
bootstrap/images/deps/locks/ci.yml/ci.sh/tenancy/backend/frontend/operator files.
Keep total57 native carriers, including intended foundation fail-closed assertion,
unchanged. No 0014, applied0001–0012/original11 and accepted contract prefix changes.
Current full contract756397 bytes/SHA256
e7f3796fcff8640ffca203266ecf7b5988f7ab1bd24850b12e923122abf5d281 is frozen.

Source checks: targeted runner unit suite and new actual Settings negative/positive
configuration test, Ruff check/format, whitespace, exact two-path scope, clean checkout.
PG/Actions execution is not part of this correction task. No install/probe loop for
known missing stock Docker; source correction is sufficient for REVIEW return.
Do not create/update execution branch, dispatch/rerun/cancel, run full CI/new PR,
access VM/shared DB/provider/S3/LLM/sends/renewal/deploy or launch another chat/agent.

Return exact commit/tree/parent/two-path diff; root-cause/fix/node-ID mapping, actual
commands/results/limitations, unchanged reset/ownership guards and all source freezes.
Return **REVIEW → C6 HOLD**; addressed runner finding remains OPEN until C0 acceptance.

### 0.4. Next gate and retained boundaries

C0 rereviews R2, binds one corrected candidate SHA/tree, then separately authorizes
one fresh full57-native+runner stock job on that corrected source. Keep20m whole-job
cap; no selective -k/retries/skip/no-tests PASS, no cap reset or source amendment
during a run. Previous run stays FAIL; no automatic retry and no false aggregate PASS.
Full carrier including actual foundation0013 refusal must pass before this gap closes.

Main e205e22051bc06295758b504d84699652b176c15/schema0012 remains unchanged.
C3 backend/API/V3/worker/Audit, C6 paired host/operator, C5 UI, C1/C8 integration reviews
remain HOLD until the current stock gap is resolved and exact next scopes are issued.
All9 contract findings/Q01 and MATERIAL11 closures retained. D1 provider completeness/
D2 conservative holds/D3 text-only limits, A08/P01/P05/renewal/collector/account/A12 OPEN;
M3 IN_PROGRESS, M4 out, IMPL-05 DEFERRED. Existing budgets/caps unchanged.

<a id="0-текущая-выдача-c0--native-context-db-r2-и-stock-runner--2026-10-18-utc"></a>

## История — NATIVE-CONTEXT DB-R2 и stock runner / 2026-10-18 UTC

**DB-R1 CHANGES_REQUESTED: два P2 OPEN. C2 получает correction, C6 — подготовку
штатного standalone DB runner. Execution пока HOLD; C1/C3/C5/C8 HOLD.**
[C0 disposition](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6250016242),
[C1 findings](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6249871164),
[C6 source PASS / PG NOT RUN](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6249901315).
Это две disjoint source задачи от общего preparation, не принятие DB/runtime.

### 0.1. Общий start и очередь

C0 preparation имеет sole parent **6a244ceed01388d85ecdd47fd373c6547fd34654**,
treeb97e1c8964cc493b81976ddb349dba3ec03266c4. Он меняет только HANDOFF/REGISTER.
Полные start SHA/tree публикуются в canonical C0 tasks PR34; обе новые ветки C0
создаёт на одном exact start:
- C2: **c2/m3-1-native-context-db-r2**.
- C6: **c6/m3-1-native-context-db-stock-runner-r1**.
Coordination branch: c0/m3-1-native-context-db-followup-r1.
Отдельные checkouts; normal FF/expected-head check на своей ветке. Старые C2 DB-R1
и C0 review branches frozen. Shared disk/память других чатов не предполагаются.

Runtime source в start совпадает с reviewed
**0268331e5b57f87e7f51f3973610cb83477662e8 /3f2f8416f6d286cca7e826b1272f450c0e5a0907**;
поверх него только C0 coordination docs. Runtime main
e205e22051bc06295758b504d84699652b176c15/schema0012 unchanged.
**0013←0012** остаётся unmerged/unreleased successor;0001–0012 frozen.
Коррекция0013 до integration не создаёт0014 и не обновляет существующую used DB
подменой исходника: любые execution proofs используют новую собственную test DB.

Full delivery contract **745994 UTF-8 bytes**, SHA256
**4c0187790c2e00a64a343173663072e4e51765a2aa922bc480681473dcef8886** frozen как prefix.
Accepted R2 prefix714947/SHA256d032a4b699767f58f60288fbe17808b69bf98627d8c11acb8df2c9a439ae8346
и original11/applied12 неизменны. Author R1 appendix остаётся историей, не current PASS.

### 0.2. C2-M3.1-NATIVE-CONTEXT-DB-R2 — четыре write paths

1. migrations/versions/0013_native_context.py — только две semantic corrections
   и неизбежная source-derived profile body delta.
2. tests/test_m3_1_native_context_migrations.py — узкие source/semantic regression
   assertions; существующие predecessor/security/freeze assertions сохранить.
3. tests/test_m3_1_native_context_postgres.py — реальные PG regression carriers,
   existing51 baseline и scoped primitives сохранить; no fake state/skip.
4. docs/tasks/M3_CONTRACT.md — append§16.17+ после полного745994-byte prefix:
   correction trace, changed bodies, tests/actual limits, future stock handoff.

Никаких tenancy/backend/API/OpenAPI/UI/host/foundation/infra/scripts/workflows/
deps/locks/AGENTS/HANDOFF/REGISTER/originals/applied revisions edits.
Нельзя расширить Resume enum или изменить R2 semantics под ошибочный SQL.

**C1-NC-DB-01/P2 OPEN:** used-policy resume_blockers должен сохранять fixed
semantic order: applicable POLICY_PAUSED → HUMAN_REQUIRED(if AI) → остальные
context reasons в contract order. Current ordinality уже filtered array не даёт
semantic rank. context_blockers/review_status не менять. OFF_UNUSED остаётся[],
HUMAN не получает HUMAN_REQUIRED. Fresh Resume использует тот же первый blocker
после retained authority/product/availability/CAS/G-overflow priorities.

Regression carriers должны включать:
- legacy OFF_UNUSED Resume→AI→ENABLE ON/P1/R=NULL, settled input: read
  [HUMAN_REQUIRED,CONTEXT_CONFIRMATION_REQUIRED]; fresh Resume→HUMAN_REQUIRED;
- used ON+AI+stale R: HUMAN_REQUIRED раньше CONTEXT_CHANGED;
- simultaneous PAUSED+AI+stale R+pending: read
  [POLICY_PAUSED,HUMAN_REQUIRED,CONTEXT_CHANGED,CONTEXT_INPUT_PENDING]
  при этих единственных применимых predicates; command→CONTEXT_POLICY_PAUSED;
- retained OFF_UNUSED[] и HUMAN без HUMAN_REQUIRED, product/CAS priority без изменения.
Достигать state реальными existing commands/ingress, не direct fixture UPDATE
N/P/G/R или disable constraints.

**C1-NC-DB-02/P2 OPEN:** human_context_reason(...,resume=true) mapping
NEW_OBSERVATION→CONTEXT_CONFIRMATION_REQUIRED. resume=false сохраняет
NEW_OBSERVATION для worker permanent hold/E context_hold. CONTEXT_CHANGED и
другие прежние mappings не менять. Carrier: TELEGRAM HUMAN/ON/current R N0,
native OWNER NEW→N1 без V/G/checkpoint/pending delta, fresh current-CAS Resume
даёт P2401/CONTEXT_CONFIRMATION_REQUIRED и0 writes. Проверить raw blocker и
non-resume reason; actual worker после legal Resume→N-only observation остаётся
permanent HOLD/NEW_OBSERVATION, без нового permit/adapter call.
CONTROLLED-only Escalation producer gate не расширять ради fake E2E.

Три таблицы/45 tables/167 functions/35 additions/18 replacements/grants/DDL и
nonfunction catalog hash57e03fe369be4bd03116ce380e37a9b447a2bc1a72e3bbf2a70c7ac08d69e370
сохраняются. Меняются semantic bodies и generated verifier body/full profile hash.
R1 full profile11e26c… и profile body225049… исторические, не expected corrected values.
Не hardcode новое значение по предположению/старому report; actual installed hash
получит следующий stock run. No changes to BASELINE original bodies/applied hashes.

Разрешены focused source/Ruff/format/Python3.13 checks при доступности locked env,
source-only probes с честной маркировкой при отсутствии. PG execution только на
доступном неизменённом stock PG18 own disposable; не воспроизводить patched-root
build, не тратить работу на повтор known unavailable setup. Если PG нет — закончить
code + regression carriers и вернуть **PG NOT RUN**, это ожидаемая dependency на
C6 standalone runner. No Actions/full CI/new PR/whole stack/HTTP/browser/VM/live.
Return: REVIEW correction, exact SHA/tree/parent/4-path diff, mapping каждого P2,
actual commands/results/limits и full prefix hashes. **Addressed≠CLOSED; затем C2 HOLD.**

### 0.3. C6-M3.1-NATIVE-CONTEXT-DB-STOCK-RUNNER-R1 — четыре NEW paths

1. .github/workflows/native-context-db.yml — один focused hosted job, default CI untouched.
2. scripts/test_native_context_db.sh — owned DB/bootstrap/reset guard/frozen env/
   exact source/run/evidence/cleanup orchestration.
3. scripts/native_context_db_catalog.py — independent source-derived functions/
   installed roles/full catalog comparator, включая verifier executable body.
4. tests/test_native_context_db_runner.py — адресные unit regressions для отказа
   при чужом resource/source mismatch и повреждённом/missing/extra catalog.
   Эти guard tests не являются PostgreSQL evidence.

Нет edits C2 files/contract/foundation/ci.yml/ci.sh/Compose/images/deps/lockfiles/
host provisioning/AGENTS/HANDOFF/REGISTER. C6 может читать reusable existing scripts,
но не менять их для этой lane. Код verifier должен работать с actual C2 corrected
candidate после C0 integration, без baked-in0268331 или R1 full profile hash.

**Подготовка source сейчас; Actions execution не выдано.**
Workflow trigger ровно push branch **c0/m3-1-native-context-db-stock-r1**,
без wildcard/main/pull_request/workflow_dispatch/schedule. Эту branch C6 не создаёт/
не обновляет. Normal FF своей preparation branch не запускает workflow.
Один job ubuntu-24.04, timeout-minutes20 на весь job, contents:read,
persist-credentials:false; pinned action commits, no repository/org secrets.
Checkout actual event SHA с .git; никаких dirty/staged подмен. C0 отдельно фиксирует
approved combined SHA/tree перед event и сверяет checkout evidence после run;
саморавенство runner HEAD/event не выдаётся за C0 approval.

Runtime: exact DB_IMAGE из infra/images.lock.env
pgvector/pgvector@sha256:2ba9ca5f2e7daa0f0e7723cba1ee9167bab54efd3640516a44ac1a928dd67e7a,
неизменённый infra/postgres/bootstrap.sh, actual PG18/vector0.8.6/btree_gist1.8,
distinct asm_runtime(nonowner/NOINHERIT/NOBYPASSRLS/etc)/asm_migrator LOGIN.
Python3.13/frozen uv.lock; existing locked images/tool versions не повышать.
Если нужны setup actions — официальные exact commit pins, actual versions/logs;
никаких arbitrary dependency updates. Git нужен carrier source_tree_identity.

Только один own DB container/fresh volume/loopback ephemeral port, unique labels/
IDs; не весь Compose stack. До reset permission проверить ownership labels,
container ID/image digest/PID/server identity/volume/mount/host-port и real login
roles. Secrets temporary0600, не печатать inspect.Env/URLs/passwords/.env в logs.
Нет чужих mounts/Docker prune/global cleanup. ASM_NATIVE_TEST_ALLOW_RESET=1 и три
URLs передаются только isolated child carrier после проверки ownership; переменные
не экспортировать в shared/full-CI lane. Resettable asm_test именно новая own DB.

Focused payload на clean combined source: прежние два native modules целиком,
включая будущие C2 regressions, и отдельные runner guard unit tests.
Нет pytest -k/masking/no-collection-pass, skip/xfail/retry/увеличения caps.
Сохранить collected node IDs, actual pass/fail/skip/count/JUnit/duration/SQLSTATE;
51 — R1 historical baseline, corrected total обязан включать новые cases.
Реальный failure вернуть как failure, не менять тесты/source для green.

До и после payload HEAD/tree/clean-source check (tracked+untracked); logs/artifacts/
venv/cache вне checkout. Identity actual event SHA/tree и git archive/source hash
в evidence. Temporary index tests не должен менять trusted checkout. Сохранить
failure diagnostics без секретов; artifact upload always где runner ещё доступен.
Cleanup только still-matching owned IDs/labels/volume; отказ foreign cleanup
проверяется unit tests. Job timeout не повод reset budget или скрыть failure.

После carrier reset cycles создать/выбрать fresh own0013 checkpoint и независимо
сверить167 source signatures→unique installed OIDs, exact bodies/args/returns/
language/volatility/secdef/owner/proconfig/ACL + zero runtime memberships.
Expected строить из trusted full0001–0013 expansion; не из installed body и не
только declared BASELINE dict. Include profile function body. Reject extra/missing/
modified functions, runtime grant/owner/role drift; при unsupported parser syntax
fail closed, без silent omission. Number OIDs process-local, comparison через
full signatures, не constant numeric OID values.

Full nonfunction catalog:45 tables/ordered columns/types/defaults/generated/
constraints/validation/indices/RLS/policies/triggers/enabled/relations/schema ACL/
immutable sequences/extensions. Independent PG query с pinned search_path/order/
jsonb::text/UTF-8, без вызова checked verifier для построения expected snapshot;
compare trusted nonfunction hash и independent full digest к declared result только
после source-body validation. Raw catalog/manifests/query/hash normalization сохранять.
C6 R1 embedded probes/query — исходный материал для review, не заранее trusted runner.

Минимальные meaningful unit negatives: source mismatch до DB reset; foreign labels/
IDs/mount/host mismatch не разрешают destructive action/cleanup; missing/extra/
body-changed verifier и role/ACL mismatch не PASS. Mocked Docker/catalog inputs —
unit evidence, не stock PG. Code/static tests можно выполнять locally; actual stock
run в этой source-preparation задаче **NOT RUN**, no fake PASS.

Return: REVIEW runner source, exact SHA/tree/parent/4-path diff, workflow trigger/
permission/cap inspection, actual local checks/limitations, usage/evidence schema/
cleanup trace и готовность к C0 composition с corrected C2 source. Затем **C6 HOLD**.

### 0.4. C0 gate и сохранённые ограничения

После обоих source returns C0 intake/rereview findings, объединяет disjoint deltas
в один candidate, проверяет clean exact code/tree и workflow, фиксирует source
approval и только затем запускает один адресный stock job через reserved branch.
Исправление двух P2 и author source checks сами по себе не закрывают PG gap.
Full CI/C8/user merge сохраняются для позже coherent backend/API/worker/Audit-V3/
C6 source-schema/operator/C5 Console. Foundation0012 пока reject0013.

Не запускать чужие задачи/чаты/агенты. No main/old refs/amend/rebase/force/new PR/
dispatch/rerun/cancel/VM/Telegram/working DB/S3/LLM/sends/deploy/renewal.
Все9 contract findings CLOSED/Q01 RESOLVED и MATERIAL/all11 остаются принятыми.
Native/P-01/A08/P-05/renewal/collector/account/A12 OPEN; M3 IN_PROGRESS.
Existing S/600/P720/fixed120/+480/S+1200/cleanup90/state25/browser25/foundation45/
3s/60s/10s и worker5claims/15min/30s/backoff60 unchanged.
Новый standalone job20min не пересматривает эти limits; IMPL-05 DEFERRED, M4 вне scope.

<a id="0-текущая-выдача-c0--независимая-проверка-native-context-db-r1--2026-10-18-utc"></a>

## История — независимая проверка NATIVE-CONTEXT DB-R1 / 2026-10-18 UTC

**C2 DB-R1: REVIEW/HOLD. C0 source intake PASS по identity/scope; DB/runtime ещё
не VERIFIED. C1 и C6 получают две ограниченные проверки, код заморожен.**
[C0 disposition](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6249640362),
[C2 return](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6248340477),
[исходная выдача](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6247002446).
Ни один review не разрешает C3/C5/runtime/host integration до решения C0.

### 0.1. Два источника с разными назначениями

**Единственный review/test target:0268331e5b57f87e7f51f3973610cb83477662e8**,
tree **3f2f8416f6d286cca7e826b1272f450c0e5a0907**, sole parent
9cebc175959eba565dcd7b979a91d04423fa94fa/tree8ab4f9a690798f010013d907b6eee0f29fd43eab.
Ветка c2/m3-1-native-context-db заморожена на этом delivery.
C0 preparation с sole parent0268331 меняет только данный handoff и TASK_REGISTER;
он хранит инструкции, **не заменяет exact review/test target**. Полные SHA/tree
этого preparation — в canonical C0 tasks PR34; ветка c0/m3-1-native-context-db-review-r1.
Не тестировать автоматически более новый branch tip вместо указанного target.

Runtime main e205e22051bc06295758b504d84699652b176c15,
tree85206b9c66ac151f3847aa39f46fb75663a18b91/schema0012.
Reservation0013/down0012 сохранена; applied0001–0012 frozen.
Contract/design R2 accepted0cdd66c/all9 CLOSED/Q01 RESOLVED не означает SQL PASS.
MATERIAL/all11 INTEGRATED/VERIFIED LOCAL/TEST остаётся принятым.

Проверенный delivery delta от preparation9cebc17:5 paths,+7624/−0,3 new,
278 blobs total/273 unchanged. Native migration+4302,source tests+188,PG tests+2685,
tenancy+84,contract appendix+365. Full R2 prefix714947/SHA256
d032a4b699767f58f60288fbe17808b69bf98627d8c11acb8df2c9a439ae8346 frozen;
full delivery contract745994 bytes/blob84166e925b3aa3eef39882baaaf4ff20132802df.
Все11 originals exact attachments/manifest. C0 source-only4 assertions/AST/frozen
predecessor expansion не являются Python3.13/pytest/PG run.

### 0.2. Общие границы двух проверок

- AGENTS, актуальные architecture Spec/ADR/MVP/Roadmap/Implementation Plan и
  IMPL-001 остаются authority. Spec5.8/5.12/5.12.1/24.7, ADR002–006/026/267,
  contract§16 целиком, C0 acceptance и C2 appendix§16.11–16.16 обязательны.
  Original sources не менять; локальный диск/окружение другого чата не предполагаются.
- Отдельные isolated checkouts на exact0268331. C1 local branch
  c1/m3-1-native-context-db-review-r1; C6 local branch
  c6/m3-1-native-context-db-repro-r1. Remote ветки/коммиты/PR не создавать.
- **Write allowlist tracked files: EMPTY.** Scratch probes/logs вне checkout
  допустимы; не исправлять implementation/tests/docs/manifests/source profiles для green.
  Любое обнаруженное противоречие — finding с exact path/line/trace и минимальным
  предложением C0. C2 остаётся автором возможного исправления после новой выдачи.
- Read scope: все5 delivery paths, effective0001–0012 chain, callers/tenant and worker
  factories, existing runtime/tenancy/regression tests, pinned infra и текущие readers.
  Считать динамические SQL replacements по фактически развёрнутым строкам.
- No Actions dispatch/rerun/cancel/new PR/full CI, whole application stack/HTTP/browser,
  account/VM/shared DB/S3/Telegram/LLM/provider API/real sends/expenses/deploy/renewal.
  No force/amend/rebase/main/C2/C3/old PR34 branch mutation. Чужие процессы не трогать.
- Перед return сверить source HEAD/tree/clean status и fresh main/C2 ref.
  Если source/main/reservation изменились — сообщить C0, не переносить PASS на другой SHA.
  Один canonical receipt PR34 на задачу; после return соответствующий reviewer HOLD.

### 0.3. C1-M3.1-NATIVE-CONTEXT-DB-REVIEW-R1 — read-only SQL/contract review

C1 проверяет реализацию независимо от авторского PASS. В этой выдаче не нужны
повтор full/PG suites или запуск приложения; источник результата — inspection и
ограниченные source-only probes, явно отмеченные как таковые.

1. Closed SQL wire/schema/error priority по accepted§16: exact OWNER/body/cursor/
   reply shapes; reject unknown/NULL/type variants; V3 final-body digest/2MiB/64/16/
   decimal/UUID/UTC/coverage. Ordinary Client growth после Resume, own OUTBOUND
   eviction, OWNER_TEXT full replacement; retained V1/V2/UNKNOWN bytes/semantics.
2. Authority: actual live OWNER/trusted transaction, same-ws wrong Client/actor/
   R/source/Audit negatives, SECURITY DEFINER/search_path/PUBLIC/runtime grants,
   private3 FORCE RLS tables, token-only replay без permit, policy actual session_user.
   Проверить command gates отдельно от table constraints и tests privileged fixtures.
3. Stable one-snapshot classifier после waits, actual direct/transitive callees,
   RLS/expressions и own-write separation. Pending→FAILED Job/Inbox-only race;
   source→mark для каждого fresh-key duplicate, no-C/old NULL/IGNORED, distinct
   gaps≤1024/probe1025, index predicates/bounded access без скрытого full-history scan.
4. R/Audit/pointer atom, FK/RI/implicit locks/no mutable-counter FK; Resume
   historical R/P/N; RESOLVE Connection-before-C/E и retained priority; completion/
   SENT/File без нового Connection edge, changed SENT one target/one C+2.
5. Все6 WAIT boundaries и все early exits: immediate CHECK на каждом UPDATE,
   commit-before-outcome contract, current/latest-token replay, reclaim/recover/
   supersede/maintenance/5claims/15min/30s/backoff60/exhaustion/visible work.
   Same Job/intent/Turn; no permit/attempt/adapter call при pending/permanent hold.
6. Policy ENABLE/PAUSE/no-op/CAS/hash/expired entitlement/lost ACK, schema/profile
   trust boundary; exact unused reverse и used55000 before DDL. Полнота executable
   cases: отличать source assertions/composed proof от actual PG/E2E.
7. Paired C3 ABI: назвать точные существующие Python/HTTP/worker/Audit consumers,
   которым нужны V3/closed errors/strict cursor/commit handling. Это handoff proposal,
   не разрешение менять backend и не finding само по себе о намеренно unpaired0012.

Return: PASS либо CHANGES_REQUESTED с stable finding ID/severity/path/line/trace,
ожидаемым/фактическим поведением, scope/limits и minimal correction. Не закрывать
native runtime/A08/M3 и не подменять independent review доверием к51 author tests.

### 0.4. C6-M3.1-NATIVE-CONTEXT-DB-REPRO-R1 — stock DB/catalog evidence

Конкретный gap: C2 actual51 run выполнен на PG18.1 с тремя изменёнными startup root
checks. Он не доказывает stock pinned parity. C6 сначала проверяет доступность
штатного собственного disposable setup; не тратит повторный цикл на patched-root
build. Baseline DB_IMAGE из exact infra/images.lock.env:
pgvector/pgvector@sha256:2ba9ca5f2e7daa0f0e7723cba1ee9167bab54efd3640516a44ac1a928dd67e7a.
Python3.13 + frozen uv.lock; extensions vector0.8.6/btree_gist1.8.
Нельзя заменять digest/tag/dependencies, root-checks/permissions/role identity.

Разрешён запуск только собственного DB container/LOCAL-TEST DB и focused Python
tests, без всего Compose stack. Исходники checkout остаются untouched. Временные
loopback bindings/bootstrap env/secret values/volumes/processes создаёт и убирает
только C6; cleanup только собственных ресурсов. Credentials не публиковать.

Fixture destructive по своему назначению: reset_disposable DROP DATABASE asm_test.
**Перед запуском установить, что host/port/server/process/volume принадлежат этой
проверке**, и только тогда ASM_NATIVE_TEST_ALLOW_RESET=1 и loopback admin URL к postgres.
Это не разрешение reset существующей asm_test/asm_local другого задания. Реальные
distinct LOGIN asm_runtime(nonowner/NOINHERIT/NOBYPASSRLS) и asm_migrator обязательны;
не SET ROLE вместо session_user, не disable RLS/constraints, не fake paid state.

Выполнить один focused итоговый run на exact clean0268331/tree3f2f…:
python -m pytest -q tests/test_m3_1_native_context_migrations.py tests/test_m3_1_native_context_postgres.py
Ожидаемый carrier —51 cases из C2 return; фиксировать actual collected/pass/fail/skip.
No skip/xfail/retry/timeout/cap expansion для green. Не запускать полный foundation.
Не менять тесты ради green; конкретный failure возвращать C0 со stage/SQLSTATE/trace.

Независимо проверить:
- fresh/populated/repeat0012→0013,45 tables/167 functions; actual pinned engine/
  extension versions; unused exact reverse и used55000 before DDL без удаления evidence;
- из trusted source chain построить expected function inventory/bodies/owners/
  volatility/search_path/ACL; сверить все167 installed definitions, включая body
  human_context_schema_profile(). Недостаточно SELECT profile.valid=true или
  саморавенства двух значений, полученных от проверяемого DB function;
- точный nonfunction catalog (columns/generated/constraints/indices/triggers/RLS/
  policies/sequences/schema ACL/extensions) и role membership/no inherited bypass;
  заявленные hashes сверять с independently computed values и описать serialization;
- security/replay/lock/coverage cases выполняются реальными actors и транзакциями.
  Current foundation0012 должна по-прежнему отвергать0013: это expected checkpoint
  limit; не повышать version, не skip и не fabricate source/drain/ready attestation.

C2 reference hashes: full profile
11e26ca71164fed6b7ed5ccd29fccc432f9a4e9f78747d4ae51e377cc5365c94,
nonfunction catalog57e03fe369be4bd03116ce380e37a9b447a2bc1a72e3bbf2a70c7ac08d69e370.
Совпадение hash не заменяет независимую body/source проверку.

Если штатная среда недоступна: закончить доступный source/catalog-definition review,
вернуть **BLOCKED / PG NOT RUN**, actual capability error и конкретный minimal
reproduction plan/proposed diff для C0. Не копировать PASS C2, не patch PostgreSQL,
не подключаться к VM/shared DB и не запускать самовольно Actions/full CI.
Stock reproduction остаётся OPEN до реального выполнения; это не SQL failure.

Return: exact HEAD/tree/clean status, engine/image/deps/extensions/role identities
без секретов, команды/actual durations/results, independent manifest comparison,
raw log hashes/available evidence links, ограничения и setup cleanup. Затем C6 HOLD.
Это DB-only proof; C6 source/schema/host/readiness/operator implementation отдельная
будущая выдача после решения C0, не scope этого review.

### 0.5. Следующее решение и сохранённые границы

После C1/C6 returns C0 consolidates findings: при необходимости C2 correction,
иначе отдельные paired C3 backend/API/worker/Audit-V3 и C6 compatibility scopes,
затем C5 Console → C8/integration/CI → renewal/collector/account/A12.
C8 independent whole candidate review и штатные gates/user merge сохраняются.
Никакого implied deploy или ENABLE policy на рабочем окружении.

P-01/A08/P-05/renewal/collector/account/A12 OPEN, whole M3 IN_PROGRESS;9 contract
findings CLOSED/Q01 RESOLVED — только contract. D1/D2/D3 provider limits не сняты.
Budgets S/600/P720/fixed120/+480/S+1200/cleanup90/state25/browser25/foundation45/
3s/60s/10s и worker caps unchanged; IMPL-05 DEFERRED, M4 вне scope.

<a id="0-текущая-выдача-c0--c2-m31-native-context-db-r1--2026-10-18-utc"></a>

## История — C2-M3.1-NATIVE-CONTEXT-DB-R1 выдача / 2026-10-18 UTC

**NATIVE-CONTEXT R2 принят в contract/design scope. C2 получает реализацию DB protocol,
первый ограниченный checkpoint; остальные авторы HOLD.**
[C0 acceptance](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6246954666),
[C1 R2 PASS](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6246639567),
[C2 R2 PASS](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6246768008).
Все9 contract findings CLOSED, Q01 RESOLVED; aliases coverage — один finding.
Это не runtime/PG/account PASS. M3 IN_PROGRESS; P-01/A08, renewal/collector/account/A12 OPEN.

### 0.1. Принятый источник, очередь и следующий checkpoint

Accepted contract: **0cdd66cc135c8797224e8dc0e87bc3280ad446c1**,
tree **11335a808d4468c78af17501849c52202b811ff7**; sole parent
315c42e2ef03ace056279fe019efef5100665c7c. Runtime main остаётся
**e205e22051bc06295758b504d84699652b176c15**, tree85206b9c66ac151f3847aa39f46fb75663a18b91,
schema0012. MATERIAL INTEGRATED/VERIFIED LOCAL/TEST/all11 CLOSED сохраняется.

Старт — **exact C0 preparation commit**, sole parent которого равен accepted R2.
Он меняет только этот handoff и docs/TASK_REGISTER.md; полный SHA/tree публикуются
в canonical C0 task PR34. C0 создаёт отдельную ветку **c2/m3-1-native-context-db**
на этом commit. C2 продолжает её в отдельном checkout обычными fast-forward commits;
не начинать от main/старого R1 и не менять C3 contract branch.
Shared disk/память другого чата не предполагаются.

**C0 назначил revision0013/down_revision0012**,
path migrations/versions/0013_native_context.py. Applied0001–0012 frozen.
Reservation0013 принадлежит этому native slice; renewal не получает competing head.
При изменении accepted main/schema или конфликте reservation сообщить C0 до публикации,
без rebase/force/переименования применённых revisions.

M3_CONTRACT R2 целиком frozen: **714947 UTF-8 bytes**,
SHA256 **d032a4b699767f58f60288fbe17808b69bf98627d8c11acb8df2c9a439ae8346**,
blob ef2df1e6ba8369fc2d3321e4b6c44ee98a0e42a7.
Through§15.18 по-прежнему603955 bytes/SHA2569643365fa8b534d6cf37a181c7c03ed76bd16b9d559016794b377b9a1eb1064b.
PROPOSED/OPEN/unassigned в exact§16 — история фазы review; текущая выдача заменяет
эти статусы/резервацию, technical decisions R2 не меняются. Evidence append после
R2 разрешён только вместе с содержательным DB кодом, не вместо него.

Порядок зависимостей: C2 DB checkpoint → C0 source/DB intake → отдельные C3 backend/API/
worker/paired Audit-V3 consumers и C6 exact source/schema compatibility scopes →
C5 Console → C8/CI/integration → отдельные renewal/collector/account/A12.
Это порядок подготовки, не разрешение начать следующие роли.
DB checkpoint отдельно **не merge-ready и не deployable**: current foundation
ожидает0012, current Python/TS readers не V3. Readiness на0013 должна fail closed
до coherent paired source. Не поднимать readiness version/ослаблять profile для
обхода этой зависимости. C0 откроет новый PR после source intake и готовности
согласованного состава; gates перед merge сохраняются, merge за пользователем.

### 0.2. Точная write allowlist — пять paths

| Path | Разрешённая цель |
|---|---|
| migrations/versions/0013_native_context.py (NEW) | Вся DDL/SQL delta R2:3 private tables, supporting existing columns/keys/indexes, RLS/ACL/typed Audit, complete DB commands/readers/guards/recovery, exact predecessor restore |
| tests/test_m3_1_native_context_migrations.py (NEW) | Real PG migration/catalog/RLS/FK/unused reverse/used refusal-before-DDL и exact source inventory; SQL/pure contract checks при необходимости |
| tests/test_m3_1_native_context_postgres.py (NEW) | Focused actual runtime-role capabilities/transactions/read races/coverage/replay/WAIT/policy/rollback tests; synthetic disposable LOCAL/TEST only |
| tests/test_tenancy_postgres.py (EXISTING) | Только точная0013 native inventory/typed Audit/privilege/constraint delta; сохранить прежние assertions и historical profiles, no wildcard/skip |
| docs/tasks/M3_CONTRACT.md (EXISTING) | Append§16.11+ после всего frozen R2: exact implemented SQL signatures/columns/source linkage/indices/result schemas, evidence/limitations и handoff; не менять принятую семантику |

Это permission, не требование менять каждый path. C0 owns HANDOFF/TASK_REGISTER/AGENTS.
Backend modules/HTTP/OpenAPI/TS/frontend/host provisioning/foundation/readiness scripts/
CI/workflows/Compose/images/dependencies/lockfiles/original11/manifest и applied migrations
не выданы. Новый path — concrete proposed diff/reason C0 до применения.
Не исправлять unrelated suite failures молчаливым расширением scope.

### 0.3. Реализуемый результат и обязательные границы

Полный DB protocol§16 в0013, без пустых future stubs. Три private tables и Job marker
должны обслуживаться реальными SQL capabilities/tests; private policy command
не заменяется direct test UPDATE policy. Initial OFF_UNUSED/P0 сохраняет old paths,
все new capabilities fail closed при неподходящей authority/source/schema/policy.

1. Exact stable ws+C+Client/connection/chat/source/actor/Audit identities,
   immutable observation/reconciliation/policy receipt, source→mark linkage для
   **каждого** fresh-key duplicate. First source witness alone недостаточен.
   Supporting association columns/keys/indexes допускаются в0013; новых generic
   frameworks/tables сверх трёх не выдаётся. NOT NULL/closed IS TRUE variants,
   no partial-NULL bypass, no FK к current counters/claim token.
2. FORCE RLS/private ACL/nonowner runtime; PUBLIC revoke; exact regprocedure/OID/
   owner/search_path/volatility/full-body/callee inventory. Live OWNER commands,
   separate token-only work replay и real session_user=asm_migrator policy command
   имеют разные authority. Private stable projections/hash/effective formatters
   не доступны произвольным runtime SELECT/EXECUTE.
3. R/Audit/pointer атомарны: C/actor→Audit→R→один C pointer/N/V UPDATE.
   Resume выбирает R и пишет historical links в одной transaction с existing G/F;
   replay не восстанавливает pointer/mode. OFF_UNUSED fresh legacy NULL relation
   и retained receipts сохраняются; new used-policy nullable bypass запрещён.
4. Exact STABLE C/Turn one-SELECT projection, без VOLATILE descendants/expressions/
   policies. После authority/connection/C/Turn waits — отдельный SQL command;
   post-write read — следующий command. Frozen message_effective и own-write
   invariant helpers сохраняются; no DML-CTE snapshot shortcut.
5. Same-chat pending/failed/unsequenced classifier, protected input hash/CAS,
   ordered distinct gap digest≤1024/probe1025. Pending→FAILED Job/Inbox-only race
   видит одно из состояний. Indexed source linkage/union/pending/checkpoint,
   без full tenant/history scan и без foreign Job/Inbox locks.
   No-C MATERIAL queue/defer/fold/initial suppression сохраняется; NULL не no gap,
   old IGNORED не backfill. Successful captured Client/duplicate не новый gap.
6. Coverage guard на R/Resume/prepare/accept/begin/Escalation/TEST: latest17 из
   всех canonical Messages, OWNER_TEXT отдельно полностью, current+saved input.
   Normal Client после Resume не сравнивается навечно с R.accepted V/checkpoint.
   Own accepted outbound eviction отказывает до permit,0 adapter call.
   V3 final-body digest/bounds/exact schema type/SQL validators/counts, V1/V2
   bytes/results unchanged. Python/TS парные consumers — последующая выдача.
7. Dedicated CONTEXT_WAIT не проходит generic terminal rejection/reschedule
   path. Same Job/intent/Turn revision,5 claims/15min/30s/backoff≤60 и due<deadline;
   commit-before-outcome, saved wait replay никогда не permit. Marker CHECK
   корректен на каждом UPDATE; next claim/reclaim/maintenance/early turn_supersede/
   stale/product/terminal exits не оставляют ложный WAITING_CONTEXT.
   Exhaustion/permanent hold видимы, no revival/new key/revision/budget reset.
8. Full lock graph включая implicit RI/own-XID: connection before C для fresh
   RESOLVE и admissions; completion/SENT/File не получает connection dependency.
   Retained FINAL/EXPIRED/replay/cancel/timers/assignee/CAS/overflow priority.
   В нормальном Takeover→R recovery первый G change может уже cancel E; R не
   закрывает terminal повторно. Context_hold read/list uses waiting V.
9. Replayable policy ENABLE/PAUSE/no-op, trusted session_user, source/schema/
   binding/CAS/key/hash/typed Audit и caps. Lost enable ACK→newer pause→old replay
   оставляет PAUSED/P. No-op different keys допустимы без counter bump.
   Fresh ENABLE использует existing post-wait billing locks/clock; PAUSE не
   зависит от expired send entitlement. SQL command tests разрешены только
   в disposable synthetic DB с фактическим migration actor/profile; fabricated
   application readiness/profile PASS запрещён. Host operator runner ещё не выдан.
10. Exact upgrade0012→0013, repeat/current-head no-op и populated preservation;
    unused reverse exact0012 inventory/bodies/ACL/data. Used refusal55000 до
    любого DDL по all native used markers, включая receipts/Jobs/V3; old0012
    transport history сама по себе не native usage. Counter/FK/Audit/commit failure
    whole rollback; changed-SENT single target/one C+2, no-op+1,UNKNOWN/private
    File/WINNER сохранились. Old assertions/caps не ослаблять.

Прочитать current AGENTS/IMPL-001, Spec/ADR/MVP/M3–M4 sources и весь accepted§16,
оба PASS и C0 acceptance; для effective SQL реальная0009→0010→0011→0012 replacement
chain обязательна. LLМ не authority для critical state; D1/D2/D3 limits не меняются.
Если concrete implementation выявит contradiction — exact trace/diff C0, не
молчаливое новое semantic решение.

### 0.4. Проверка и возврат

Разрешены focused unit/source checks, Python3.13/Ruff/format и реальные PG18 checks
этого DB slice в **собственных disposable asm_local/asm_test**. Existing pinned
локальный test setup/locked dependencies допустимы без изменения manifests;
нет платных внешних API/production данных. Shared/live/VM DB-S3 запрещены.
При недоступном PG вернуть законченный source/patch и явный NOT RUN; не выдавать
manual trace/mock за PG PASS и не расширять scope для green.

Достаточное evidence: fresh/populated/repeat upgrade; unused reverse/used refusal
before DDL; exact45-table successor при трёх additions и exact functions inventory,
tenant/same-ws wrong Client/R/source/Audit/NULL negatives; FORCE RLS/private ACL;
0/1/1024/1025 distinct gaps/overlap/dedup/bounded lookup на большой unrelated history;
two-connection post-wait snapshot/resolve/admission; full R/policy/WAIT ACK replay/
reclaim/supersede/exhaustion; actual coverage/own OUTBOUND; rollback/overflow и
V1/V2/V3 SQL digest/types/counts. Не прогонять broad suites ради количества;
применимые retained regression cases можно выполнить адресно, не изменяя gates.

Не запускать Actions dispatch/rerun/cancel/new PR/full CI, HTTP/Playwright/весь Docker
application stack, host operator/VM/Telegram API/account/sends/deploy/renewal.
Материализация synthetic fixtures не разрешает fabricated receipts/paid state.
DB fixtures используют легитимные existing auth/provisioning primitives и реальные
capabilities; targeted fault injection не disable/skip constraints.

Публикация только normal FF c2/m3-1-native-context-db с expected-head check;
один focused delivery commit предпочтителен, законченные checkpoints допустимы.
No main/C3 branch/old PR34 branch/amend/rebase/force/new PR. C0 intake перед PR.
Return в PR34: full SHA/tree/parent, exact diff/allowlist, capability+index+RLS catalog,
closure assertions→actual commands/results, failure limits, API/C3/C6 interface
handoff и следующий minimal scope. **REVIEW / DB checkpoint, не INTEGRATED/VERIFIED
native runtime**, затем C2 HOLD. C0 выдаёт зависимую работу отдельно.

Budgets S/600/P720/fixed120/+480/S+1200/cleanup90/state25/browser25/foundation45/
3s/60s/10s и worker caps unchanged. IMPL-05 DEFERRED; M4 вне scope.

<a id="0-текущий-статус--native-context-r2-review--2026-10-18-utc"></a>

## История — NATIVE-CONTEXT R2 REVIEW / 2026-10-18 UTC

[C0 R2 assignment](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6245868587),
[C0 consolidated decisions](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6245858507),
[C1 CHANGES_REQUESTED](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6245768491),
[C2 CHANGES_REQUESTED](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6245810317).
**C3-M3.1-NATIVE-CONTEXT-CONTRACT-R2: REVIEW / docs proposal → HOLD после return.**
C1/C2 review COMPLETE/CHANGES_REQUESTED accepted→HOLD; C5/C6/C8 HOLD.
Все9 distinct findings + C2-NC-Q01 остаются OPEN до C0 rereview, addressed in proposal;
full alias mapping и finite traces — [contract§16.10](M3_CONTRACT.md#1610-review-mapping-принятые-choices-и-предел-evidence)
и [единый реестр](../TASK_REGISTER.md). Ни одного runtime finding не объявлено CLOSED.

Exact correction base/sole parent `315c42e2ef03ace056279fe019efef5100665c7c`, tree
`348519b752e05aae7d410f4a97ac7685ac77e8e0` — reviewed proposal, не integrated runtime.
Один normal fast-forward commit на `c3/m3-1-native-context-contract-r1`, отдельный
checkout; ровно M3_CONTRACT proposed§16, M3_HANDOFF, TASK_REGISTER. Prefix through§15.18
603955 bytes/SHA256 `9643365fa8b534d6cf37a181c7c03ed76bd16b9d559016794b377b9a1eb1064b` frozen.
Applied0001–0012 frozen; revision/predecessor/reservation не назначены.

| Concrete R2 correction | Owner handoff / bound |
|---|---|
| Coverage | CANONICAL_SUFFICIENT только при full canonical tail≤16 на Resume и каждом fresh admission; eviction→CONTEXT_COVERAGE_REQUIRED. Full OWNER_TEXT включается независимо в каждый V3; replacement/withdrawal explicit, old replay не возвращает pointer |
| Read/classification | Один post-wait STABLE SELECT/direct projection, без nested VOLATILE message_effective; old helper own-write behavior сохранён. Pending/failed/NULL/checkpoint/input-state hash coherent. Unsequenced/pre-C terminal evidence acknowledged через bounded gap digest/OWNER_TEXT |
| Temporary pending | Same durable Job CONTEXT_WAIT→READY в прежних5claims/15min/30s/backoff; без terminal result receipt/нового intent. Exhaustion/permanent hold→видимый OPERATOR_REQUIRED; DISPATCHING/UNKNOWN completion unchanged |
| Policy/wire | Closed OFF_UNUSED/P0/ON/PAUSED/P+1 matrix, ordered errors, HUMAN_REQUIRED, fresh legacy NULL-link Resume. Total serialized body4096, exact validators/cursor/preview/no-store и paired Python/OpenAPI/TS |
| Escalation | Fresh resolve connection SHARE до C; typed context_hold read/list/can_resolve=false. Validity/timer/cancel/FINAL/EXPIRED/winning replay прежние; later R V+1 cancel once |
| Policy command | Concrete asm_migrator session_user LOCAL/TEST capability; minimal third private receipt carrier, key/hash/CAS/Audit/no-op/overflow. Lost enable ACK→newer pause→old replay не включает policy |
| Evidence/handoff | NC01–20 обновлены с finite orders; exact future messaging worker/results/errors, V3 validators и Escalation API/models/TS/panel/tests включены в§16.9. Это proposed future paths, не разрешение writes сейчас |

C0 D1/D2/D3 выбраны с пределами: owner-confirmed доступный handoff, conservative
hold, native TEXT_ONLY/UNAVAILABLE/PARTIAL. Unseen/unreported native facts/provider
completeness/causal takeover не доказаны; A08 не сокращён. D4: targeted C1 API/wire/
UI и C2 snapshot/locks/FK/recovery/policy receipt/1024-gap-bound rereview, затем C0
отдельно назначает schema/runtime scopes. Никакого M4 summary/retrieval.

Original11 repository=manifest=supplied originals проверены заново; frozen prefix,
three-path diff и links проверены;69 future paths=57 existing+12 proposed new.
Actual `git diff --check` для R2 **EXIT0**; full commit/tree/parent/stats в canonical
return. R1 exec outage/NOT RUN
и actual C0 R1 EOF EXIT2 сохранены как история ниже, не переписаны в прежний PASS.
Только source inspection и finite manual traces; product tests/PG/browser/build/
services/install/Actions/VM/Telegram API/working DB/S3/sends/operator command/
renewal/deploy/expenses NOT RUN by scope. No new PR/main/old PR34 branch changes.

MATERIAL **INTEGRATED/VERIFIED LOCAL/TEST**, all11 CLOSED; accepted runtime main
`e205e22051bc06295758b504d84699652b176c15`, tree `85206b9c66ac151f3847aa39f46fb75663a18b91`;
prior push/main CI38960113060 attempt1 9jobs+9clean SUCCESS unchanged. Gate OFF,
merge≠VM deployment. Whole M3 IN_PROGRESS; P-01/latest-human-context/A08,
P-05 renewal/collector, P-A03-09 account и M3-ACCEPTANCE/A12 OPEN.
Budgets S/600/P720/fixed120/+480/S+1200/cleanup90/state25/browser25/foundation45/
3s/60s/10s unchanged; IMPL-05 DEFERRED. Next: C0 intake → C1/C2 rereview.

<a id="0-текущий-статус--material-принят-native-context-proposal--2026-10-17-utc"></a>

## История — NATIVE-CONTEXT R1 proposal / 2026-10-17 UTC

[C0 postmerge acceptance](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6228792048)
принимает MATERIAL **INTEGRATED/VERIFIED LOCAL/TEST**, все11 findings CLOSED.
PR34 merged; exact accepted main `e205e22051bc06295758b504d84699652b176c15`,
tree `85206b9c66ac151f3847aa39f46fb75663a18b91`.
[CI38960113060 attempt1 push/main](https://github.com/Elefesys/ai-service-manager/actions/runs/38960113060):
9 jobs и9 clean SUCCESS. [C8 independent PASS](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6223489359)
проверил candidate/tested-merge с тем же tree. Старые R5 OPEN3/Draft/NOT RUN ниже —
история source checkpoint; не current integration status. Merge не deployment,
MATERIAL gate OFF; whole M3 IN_PROGRESS.

**C3-M3.1-NATIVE-CONTEXT-CONTRACT-R1 — REVIEW / docs proposal; return затем HOLD.**
[C0 task](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6228802023),
[contract§16](M3_CONTRACT.md#16-native-context--proposed).
Отдельная `c3/m3-1-native-context-contract-r1`, sole parent accepted main выше;
один docs commit. Full head/tree/numstat и verification limitation в canonical
return, без отдельного self-SHA commit. Только M3_CONTRACT append§16, этот handoff
и TASK_REGISTER. Prefix through§15.18 exact603955 bytes/SHA256
`9643365fa8b534d6cf37a181c7c03ed76bd16b9d559016794b377b9a1eb1064b`.
Applied0001–0012 frozen; successor revision/predecessor/reservation не назначены.

Proposal: **live OWNER reconciliation + conservative observation barrier**.
Сначала save immutable R/Audit/V+1 в HUMAN, затем existing explicit Resume атомарно
выбирает свежую R и сохраняет relation с новым G/F. V2 native observations —
сигналы сверки, не human transcript/Client inbound/delivery evidence.
Новый сигнал N+1 закрывает admission в AI без guessed automatic takeover.
Mandatory confirmation каждого Resume покрывает исходный no-update контрпример,
если Owner передал договорённость; attestation не доказывает Telegram completeness.
No native text resend через Console; no File/WINNER для unfetched native PHOTO.

| Concrete proposal / owner next step | Binding |
|---|---|
| API/receipt | New GET human-context, GET observations, POST human-context/reconcile; strict CAS G/V/P/N/current-R/ingress checkpoint + namespace/hash/exact replay. Existing Resume three-field success contract/hash retained, new server guard and immutable R relation |
| Data/context | Two needed private tables observations/reconciliations, C pointer+N, connection policy+P, control receipt nullable relation. V3 selected R+current bounded canonical tail; TEXT_ONLY/media unavailable/PARTIAL, UNRESOLVED blocks |
| Serialization | Shared C barrier, no foreign Job/Inbox/Outbox/File locks after C; pending/unreviewed failed input guard. Lost ACK replays saved result, newer HUMAN/current R not overwritten; in-flight/UNKNOWN retained |
| Compatibility | V1/V2 receipts/hash/snapshots unchanged; old native IGNORED never replayed/backfilled. Existing AI bootstrap hold; HUMAN/new C explicit reconciliation; PAUSED/reenable P+1, used downgrade refusal before DDL |
| Evidence | NC01–NC20 finite manual traces map PG/API/browser assertions separately from bounded account observation. No runtime PASS; account cannot prove causality/completeness |
| C0 D1 | Approve limited owner-confirmed available-context guarantee or require another proof source/explicit scope decision; no silent reduction A08/LOCKED |
| C0 D2/D3 | Approve conservative AI hold including delayed/ambiguous/material observations; approve TEXT_ONLY/UNAVAILABLE boundary or issue native media scope |
| C0 D4 → owner reviews | C1 exact API/error/Audit/security; C2 FK/RLS/lock/V3/checkpoint/rollout contract. C0 then assigns revision and exact write sets from§16.9 |
| Implementation sequence after separate authorization | C2 schema/security contract → C3 backend/V3/guards + C1 paired contracts → C5 owner UI/recovery → C6 exact successor compatibility/readiness → C8 changed-risk review → C0 integration/CI; account/renewal/A12 separately |

Source-backed reads covered AGENTS/IMPL-001/original11/manifest/supplied originals,
applicable Spec/ADRs/MVP/Plan, control/normalizer/ingress/worker/context/material/
Escalation/private-image/UI paths and existing PG/browser boundaries, plus C0/C8
current receipts. All11 originals matched manifest/attachments before environment
failure; final tree must preserve them unchanged.

Local checkout/exec-server became unavailable after authoring. Final candidate
prepared from exact GitHub base blobs; prefix/whole-tree allowlist/read-back/hash/
whitespace/link checks are recorded in canonical return. **Local git diff --check
for final candidate NOT RUN**; separate whitespace/conflict check is not presented
as that command. Product tests/PG/Docker/Playwright/build/services/install/CI actions
NOT RUN by docs scope. No new PR/main/old PR34 branch update, force, runtime or live action.

C3 HOLD after return; C1/C2/C5/C6/C8 HOLD until separate C0 assignments.
P-01/latest-human-context/A08 remains OPEN; P-05 renewal/collector, P-A03-09 account,
M3-ACCEPTANCE/A12 OPEN. Native proposal/implementation not INTEGRATED/VERIFIED.
Budgets S/600/P720/fixed120/+480/S+1200/cleanup90/state25/browser25/foundation45,
individual3s/60s/10s unchanged; IMPL-05 DEFERRED. No M4/renewal/probe in this diff.

<a id="0-c2-m31-material-sent-lock-r5--source-return--2026-10-16-utc"></a>

## История — C2-M3.1-MATERIAL-SENT-LOCK-R5 — source return / 2026-10-16 UTC

[C0 task](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6220709356),
[C0 R4 disposition](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6220674632),
[contract§15.18](M3_CONTRACT.md#1518-c2-m31-material-sent-lock-r5--single-targetcontext-updates-and-typed-tenancy-identity--2026-10-16-utc).
Separate c2/m3-1-material-sent-lock-r5; base/sole parent
36240388fa580e563699c4dec3fd989cc2dd09f6/tree cb5c38e78a145184d8792f53702e102275fbb785.
One focused descendant, full identity/numstat/commands in canonical receipt;
REVIEW on return then C2 HOLD. Main/frozen E933ddd…/0011 and OPEN/Draft PR34
c6/m3-1-material-compat at36240388 stay unchanged.

Actual R4: CI38926368179/merge d3c39fa…,8 SUCCESS/1 FAILURE;
clean8 SUCCESS/1 SKIPPED.1444 units PASS;797 PG PASS/2 FAIL. Original SENT
diagnostic760 bytes: MessagingError→OperationalError→LockNotAvailable/55P03,
material_apply:17→material_bind:40→turn_material:21. Blocking constraint/resource
UNKNOWN, not an observed deadlock. Dedicated tenancy count23 PASS; pretty composite
signature equality fails and later profile tail NOT RUN. Browser308/44 and both
complete state lanes/clean PASS; historical browser cause UNKNOWN. Foundation
post-PG downgrade/re-upgrade/contracts/wheel/storage/startup/HTTP tail NOT RUN.

Pinned PostgreSQL18 source shows current-XID old tuple before equal-key shortcut;
heap UPDATE creates a current-xmin version and RI lookup takes FOR KEY SHARE.
The repeated target UPDATE explains a source path consistent with the actual frame;
the exact FK remains inferred. A second repeated Conversation update would retain
the same connection dependency. Source now combines canonical bind+final current
into one target UPDATE, and changed SENT delivery1+material1 into one C+2 UPDATE.
Shared context/invalidation stays one body; its ordinary/default behavior is C+1.
SENT no-op/unmatched/quarantine uses original delivery+1, UNKNOWN unchanged.
Two private signatures gain previous jsonb / delivery boolean(default false),
with all132/23/2runtime/21private/7invoker/16SECDEF identities/profiles preserved.
Tenancy expected fully qualified regprocedure signatures resolve to exact unique
OIDs; the same OIDs select all privilege/owner/search_path profiles.

Original single finish_send/arguments/3s/held connection FOR UPDATE/diagnostic exact;
only post-success readbacks and retention of its existing historical-result read.
Neighbor no-op SENT proves binding/zero effects; Message=max and C=max−1 overflow
arms require22003 from shared context and exact41 data+actual metadata rollback.
These PG cases are NOT RUN locally. Cached online-DDL test1 PASS/69 deselected/0.84s;
Ruff check/format3 files, compile/diff/AST source audits PASS on3.12.14, not packaged
3.13 (absent).131 expanded statements/42 tables/132 functions;127 other function
profiles and53 other test definitions exact. No installs/services/runtime runs.
Six paths only, all inside eight allowed. Contract592048-byte prefix through§15.17,
SHA256 ad5697568bcd71639c06fbf827c97481c9e1149879a538518599866a72fb3604,
applied0001–0011/ORIGINAL17/OLD_CHECK4/original11/product/frozen/runtime/frontend exact.

C0 closed8: C1-R2-02 (C1-R3-01 alias), C2-MAT-02, C1-R3-03,
C0-R3-01/02/04/05, C5-R3-01. OPEN3: C1-MAT-01/P1 (C1-R3-02 alias),
C0-R3-03/P2, C2-MAT-01/P1. This source closes none; earlier scoped closures and
all regression boundaries remain. C1/C3/C5/C6/C8 HOLD. C0 source intake before
same PR normal automatic CI: full9+clean9/full foundation tail/dedicated ACL/SENT
and both complete state lanes again, remaining owners then independent C8.
MATERIAL/M3 IN_PROGRESS, gate OFF, Draft/BLOCKED, not INTEGRATED/VERIFIED.
Normal P prep719.560822218s/rem0.439177782s and foundation43:11 do not authorize
optimization. S/600/P720/fixed120/+480/S+1200/cleanup90/state25/browser25/foundation45
and3s/60s/10s unchanged; no reset/subtraction/retry/budget increase/Actions/PR advance/
new PR/merge/live/VM/working DB/S3/sends/deploy/native/A08/renewal/collector/M4.
IMPL-05/broad optimization DEFERRED. Earlier returns below remain historical.

## История — C2-M3.1-MATERIAL-CURRENT-PROFILE-R4 — source return / 2026-10-16 UTC

[C0 task](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6218233521),
[C0 actual disposition](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6218176738),
[contract§15.17](M3_CONTRACT.md#1517-c2-m31-material-current-profile-r4--test-boundaries-and-same-call-sent-diagnostics--2026-10-16-utc).
Branch c2/m3-1-material-current-profile-r4; base/sole parent89f9e157ddfc328ba4564fc003b047f517352cdf,
tree9be95d45e6a70bf76adf146c1035e571d52205af. One focused descendant, full identity/
numstat/commands in canonical receipt; REVIEW on return then C2 HOLD. Main/E933ddd…/0011
and OPEN/Draft PR34 c6/m3-1-material-compat at89f9e15 unchanged.

Thirteen reached PG failures receive narrow test corrections: three wire_dates
call sites (two PG plus state), existing V2 adapter in six held-transaction TELEGRAM
arms and normal ingest_update at lifecycle refresh, exact current key/23 signature
profiles, actual-stage legacy seed and same-instant UTC caller. R3 rollback adds
actual migration metadata to its41 data fingerprints. Existing assertions/receipts/
barriers/strict DTOs and V1/current/frozen boundaries remain; no product/DDL correction.
SENT gets only same-call diagnostics: one finish_send, original3s and held connection
FOR UPDATE, closed metadata/cycle-safe≤4-node chain/≤4KiB/no payload, primary preserved
through diagnostic/cleanup failures. Cause UNKNOWN until actual metadata exists.

Local: cached Ruff0.16.7 check/format9 files PASS; compile/diff/AST/prefix/source
audits PASS.235 other function bodies/decorators byte-exact. Six new pure tests
6 PASS/64 deselected in0.86s on Python3.12.14 with cached packages, not packaged3.13.
Initial six import failures lacked psycopg/libpq; helpers now reside in the allowed
pure test module, so the tests no longer import PG harness. Pure DTO/V2/fingerprint/
UTC probes PASS. No installs/new services/runtimes or full PG/state/browser run.
Full contract prefix582717 bytes/SHA2566f68bd44… and original11/frozen/runtime/product/
migrations/frontend remain unchanged; all twelve paths are inside C0's closed list.

Actual baseline38909147338/merge d0fd7e5:5 SUCCESS/4 FAILURE; clean5 SUCCESS/4 SKIPPED;
1438 units PASS, PG785 PASS/14 FAIL, browser43 PASS/1 FAIL, both state fresh failures.
Saved-V1 reader returned before the later DTO failure, not fresh PASS. Historical R3
“all42” wording is corrected:41 data tables before this complementary metadata read.
C0 CLOSED C0-DIAG-02 (C1-R2-01 alias), C1-MAT-02, C2-MAT-03; earlier scoped
C5-MATERIAL-01/C0-DIAG-01 closures remain. Eleven OPEN findings and aliases are
recorded in§15.17/register; source checks close none. C5 independent one-file task
ACTIVE from89, no branch absorbed; C1/C3/C6/C8 HOLD.

C0 intake/combination before normal automatic CI; full9+clean9/product PG/strict
fresh+ACL/SENT/EXPIRED/ingress/catalog/populated reverse/R3 raw42/both complete P-state/
used recovery/cutover/restart/retained full120/export/all3 late-C+owned cleanup and
remaining C1/C2/applicable C5 acceptance, then C8 required. Gate OFF; MATERIAL/M3
IN_PROGRESS, PR Draft/BLOCKED, not INTEGRATED/VERIFIED. S/600/P720/+480/S+1200/
cleanup90/state25/browser25/foundation45 unchanged. No PR advancement/new PR/merge/
Actions operations/live/VM/working DB/S3/sends/deploy/native/A08/renewal/collector/M4;
IMPL-05/broad optimization DEFERRED. Earlier returns below remain historical.

## История — C6-M3.1-MATERIAL-HARNESS-R5 — source return / 2026-10-16 UTC

[C0 task](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6211450459),
[current C0 disposition](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6211420811),
[contract§15.16](M3_CONTRACT.md#1516-c6-m31-material-harness-r5--packaged-inputs-and-saved-v1-reader--2026-10-16-utc).
Branch c6/m3-1-material-harness-r5; exact base/sole parent
d7cea5a2e9da7b384aeaf11dd41df3e1e4abcbff/tree a471c98e16343cf9d17d4d184df88ed491184544.
One focused descendant, full identity/numstat/commands/manifest in canonical receipt.
PR34 OPEN/Draft c6/m3-1-material-compat stays on d7; main/E933ddd…/0011 unchanged.

Explicit frozen_h_source dependency supplies verified packaged pins before e.ROOT
substitution; all11 preparation cases/real entrypoint/assertions retained. Fresh
saved-V1 helper reads the complete non-NULL Job inventory with real id/kind/step,
dispatches only ordinary TEST_CONSUME or CONTROLLED_GUARDS_V1/GUARDED_TEXT, adds
code/job_id in memory and preserves raw JSON/all fields/digest. Closed rejection,
nonempty/count/unique identity checks; no persisted envelope/schema_version,
Escalation turn_input form, DB updates or product decoder changes.

Baseline exact168 COPY inputs: preparation[pass] **1 expected FAIL in0.95s**,0
subprocesses; old actual reader block reproduces raw/envelope mismatch on synthetic
ordinary/guarded inputs. Corrected same restricted layout: **110 PASS in2.87s**
(78 affected fixture cases including all11,32 new actual-helper regressions), then
**91 PASS/510 deselected in10.05s**.15 overlap,186 distinct cases;0 skips/xfails.
No.git/usable Git/current pins; env-i/cached locked deps, parent audit forbids network,
all subprocesses for110 and Git for91. Real python-S/runpy units remain unchanged;
synthetic external H/Git/docker boundaries are unit evidence only.

Exact six paths; Ruff/format/compile/source audits PASS. Full306538-byte runtime
prefix, shell7d1e08e…, frozen-H JSON/validation, originals/product/migrations/C3,
observer/ACK/privacy and budgets preserved. Entire§15.15 prefix576446 bytes/
SHA25676ed7dd2… unchanged; append§15.16 only. Historical sections below are retained.

C0 disposition closes C5-MATERIAL-01/C0-DIAG-01 on actual d7/merge58542ff. Seven OPEN:
C2-MAT-01/02/03,C1-MAT-01/02,C0-DIAG-02 (alias C1-R2-01),C1-R2-02. CI38868575912:
6 SUCCESS/3 FAILURE,clean6 SUCCESS/3 SKIPPED; two state failures reached fresh reader.
Prep623.690022374s/688.934643093s is PASS720 only. Full product PG/both complete
P-state/used55000/recovery/cutover/restart/retained/full120/export/all3 late-C/9+clean9
still required. C0 intake → C0 PR advance/automatic CI → C1/C2/applicable C5/later C8.
C6 HOLD after return; C3/C1/C2/C5/C8 HOLD. MATERIAL/M3 IN_PROGRESS,not INTEGRATED/
VERIFIED; gate OFF. No PR-head/new PR/merge/Actions/Docker/PG/browser/live operations.
All S/600/P720/+480/S+1200/cleanup90/state25/browser25/foundation45 bounds remain.
Native/A08/renewal/collector/M4 unissued; IMPL-05/broad optimization DEFERRED.

## История — C6-M3.1-MATERIAL-CI-DIAG-R4 — unit image packaging / 2026-10-16 UTC

[C0 task](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6210115890),
[R3 intake/C0-DIAG-02](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6210103047),
[§15.15](M3_CONTRACT.md#1515-c6-m31-material-ci-diag-r4--diagnostic-unit-image-inputs--2026-10-16-utc).
Branch c6/m3-1-material-ci-diag-r4, exact base/future sole parent
9cb1467c1705827a4e782421754850f5dee762ce, tree e0c1e5231cddfd25e44071990031371aaa16c482;
base parent a9f58a1…. One source descendant, final identity/numstat in receipt.
R3 loader source/unit correction is accepted and byte-preserved. Main/E933ddd…/0011
and PR34 OPEN/Draft c6/m3-1-material-compat/d810dde… unchanged.

Only post-pytest fixtures/tests change. Pinned JSON input carries exact four H files
from actual frozen Git objects:231153 decoded bytes, fixed paths/lengths/blob hashes,
bounded zlib/base64. COPY tests already packages it. No Git/history at test runtime.
The host unit copies current/H bytes, uses finite synthetic external Git-command IO
and retains real binding functions/runpy/observer/ACK behavior. Unexpected commands
fail; synthetic identities are explicitly unit-only. Real state Git validation stays.

Exact9cb source-only baseline: **2 setup ERROR in1.35s**, git show/clone exit128.
Corrected development COPY layout:168 files matching per-file manifest, no .git or
uncopied infra/images.lock.env; empty inherited environment, restricted sh/python3
PATH, Git lookup None and audit rejection. **91 PASS/510 deselected in10.00s**, JUnit
91/0 errors/0 failures/0 skipped; no xfails. All15 host and60 earlier invocation cases
included, real child python -S/no pytest. Synthetic docker executables only;0 actual
Git subprocess attempts. Revised loader control with exact a9 shell/module still
gives6 FAIL/9 PASS on pytest attempts. No broader suite/services/CI executed.

Ruff/format/compile/diff/source/fixture/COPY audits PASS. Full runtime prefix306538
bytes/SHA2563b1b9e4d… and entire shell7d1e08e… exact;168 other definitions and all
host assertions/cases preserved. Full§15.14 prefix569463 bytes/SHA256bd6f9cb9…
unchanged; only§15.15 appended. Earlier receipts/history remain tied to their source.
All product/C3/PG/migrations/frozen sources/observer protocol/P/budgets unchanged.

**Eight findings OPEN:** C2-MAT-01/02/03, C1-MAT-01/02, C5-MATERIAL-01,
C0-DIAG-01/02; DIAG-01 source-fixed, actual state acceptance pending. This proves
packaging/units, not actual Docker/PG/browser/Actions acceptance. Historical CI and
H cause UNKNOWN/partial Docker29 prep remain unchanged. C0 reviews packaging before
PR advancement; actual9+clean9/both full state-P/retained-late-C/0012-PG/PHOTO-browser
and C1/C2/C5/later C8 remain required. C6 HOLD after return; C3/C1/C2/C5/C8 HOLD.
MATERIAL/M3 IN_PROGRESS; PR34 Draft/BLOCKED, not INTEGRATED/VERIFIED; gate OFF.
No PR-head update/new PR/merge/dispatch/rerun/cancel/live operation; unissued work
and IMPL-05/broad optimization deferral unchanged.

## История — C6-M3.1-MATERIAL-CI-DIAG-R3 — stdlib H host correction / 2026-10-16 UTC

[C0 task](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6209721060),
[C0-DIAG-01/P1](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6209702274),
[§15.14](M3_CONTRACT.md#1514-c6-m31-material-ci-diag-r3--stdlib-h-host-boundary--2026-10-16-utc).
Branch `c6/m3-1-material-ci-diag-r3`, exact correction base/sole parent
a9f58a1364b98b5331b83fa17893363abb7d5dae, tree4c938731b25a4b0424f8e86d33bcf779f6f1fe8b.
R2 was returned CHANGES REQUIRED, not accepted for PR advancement. Its historical
60/196-unit results below remain tied to that a9 source and do not prove this host
boundary. Final R3 head/tree/numstat are in one canonical receipt; REVIEW then HOLD.
Main/E933ddd…/0011 and OPEN/Draft PR34 c6/m3-1-material-compat/d810dde… unchanged.

The actual outer state loader now uses an early stdlib-only dispatch before
pytest collection. The unchanged observer runs while runpy's module is available
for inspect; a request/result container transfers its result/summary or original
exception object. Started execution cannot fall back into a second H. Setup/load
failure stays finite INVALID, original H result/exception primary; image/intent,
H cleanup/diagnostic gates, observer protocol/launcher/P and budgets unchanged.

Actual new regression against separate clean a9: **6 FAIL/9 PASS in6.10s**,
pytest attempted and state diagnostics INVALID. Corrected affected selection:
**91 PASS/510 deselected in14.80s**, including15 real-loader `python -S` cases and
the existing60 invocation cases. Only external H execution doubled; no loader or
definitions namespace substitution, dependency, Docker/PG/browser/CI execution.
Synthetic COMPLETE report/ACK proves host transfer only, not actual H builds.
Ruff/format/shell/embedded/generated compilation/diff/source audit PASS;168 existing
definitions byte-exact, only related seam double adjusted with assertions intact.
All274 baseline tracked blobs verified. Full§15.13 prefix563611 bytes/SHA256
2aee65737913ebfede51103ae02e8758405ce3f934d7a7abf040cda4fd9b109a preserved;
only§15.14 appended. Five-path scope; all product/C3/PG/migrations/frozen sources,
private protocol/source guards and original S/600/720/+480/S+1200/90 unchanged.

**Seven findings OPEN:** C2-MAT-01/02/03, C1-MAT-01/02, C5-MATERIAL-01, C0-DIAG-01.
Historical CI38850821014 stays4 SUCCESS/5 FAILURE, clean4 SUCCESS/5 SKIPPED;
H cause UNKNOWN; Docker29 prep499.951432356s remains partial. C0 reviews source
before advancing the same Draft PR34; both complete state/P lanes, all9+clean9,
retained/late-C negatives, actual0012/PG/PHOTO/browser and C1/C2/C5/later C8 remain.
C6 HOLD after return; C3/C1/C2/C5/C8 HOLD. MATERIAL/M3 IN_PROGRESS, PR34 Draft/
BLOCKED, implementation not INTEGRATED/VERIFIED; gate OFF. No PR-head update,
new PR/merge/dispatch/rerun/cancel/live operation; unissued work and IMPL-05 deferral
remain as assigned.

## История — C6-M3.1-MATERIAL-CI-DIAG-R2 — original-invocation diagnostics / 2026-10-16 UTC

[C0 task](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6208852583),
[accepted C3 intake](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6208831490),
[C6 diagnosis](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6208328996),
[§15.13 source/evidence](M3_CONTRACT.md#1513-c6-m31-material-ci-diag-r2--bounded-original-invocation-diagnostics--2026-10-16-utc).
Separate branch `c6/m3-1-material-ci-diag-r2`, accepted base
`f0c111ac0b74695cc12444ccdf077314d06d2a9b`, tree
`ca3f638b206b232a7a6cd8f1920e31580991b58b` (parent d810dde…).
C3's seven-space correction and both real-string regression nodes are read-only.
Main/frozen E933ddd…/0011 and existing PR34 branch/head d810dde… stay fixed.
Two focused source commits; final immediate parent711934148b3921047501ff3e3c3b6e6ff34c74a4.
Final head/tree/combined numstat are in the canonical receipt; source REVIEW then HOLD.

Only H's current state invocation boundary and current P ordinary migration
observation changed. Private startup ZIP preserves original H stdin execution,
helper/build objects and pass-through interpreter behavior; evidence is instrumented
immutable H. P scopes tracing to original e.command inside ordinary migrate/run,
with unchanged args/environment/30s bound; expected post-commit86 arms stay outside.
No duplicate/retry/probe/alternate migration, source rewrite or product fix.

Reports bind separate observer/executor source/tree/blob/code identities. Closed
schema, at most16 records/64KiB, at most16KiB classification per captured stream,
finite categories and explicit UNKNOWN/TRUNCATED; no raw outputs/SQL/argv/env/URL/
credentials. Private0700/0600 paths, identity/source checks, per-session HMAC and
H's independent64-byte completion ACK reject missing/tampered/failed evidence.
P distinguishes recognized client parameter errors from PostgreSQL failures;
SQLSTATE is exported only when explicitly safely recognized. Diagnostic failures
are secondary to executor failure; success with invalid diagnostics fails a distinct
diagnostic gate after required cleanup. Original traces/source pairing/owned checks
remain. All overhead consumes original clocks, without changing S/600/720/480/90.

**Local source evidence:**60 new invocation cases PASS; focused combined196 PASS /
390 deselected, includes those60. Actual isolated interpreter/frozen-function and
outer/P boundary seams use synthetic doubles only. Ruff/format/shell/embedded code,
five-path/frozen-source/flow audit PASS.134 existing definitions are byte-exact;
removing only diagnostics yields original P/outer ASTs. Full contract through§15.12
is preserved:551663 bytes/SHA2560be54876…; only§15.13 appended. Original11, all product/
PG tests, migrations/inventory/Inbox pair/five NULL Job fields and workflows/locks
are unchanged. No dependency installation, service, PG/Docker/browser/Actions run.

**Current actual evidence remains BLOCKED.** Historical38850821014/attempt1 tested
merge51fca8…/tree fb06ad7…:4 SUCCESS/5 FAILURE; clean4 SUCCESS/5 SKIPPED. H cause UNKNOWN;
its lost exit/target/stderr are not reconstructed by this change. Docker29 prep
499.951432356s is partial, not full P/state/late-C-negative acceptance. C3's accepted
source correction is not observed historical CI stderr. All six findings remain
OPEN: C2-MAT-01/03, C1-MAT-01/02, C5-MATERIAL-01, C2-MAT-02.

Next: C0 combined-source intake → advance the same Draft PR34 once → normal automatic
CI on exact descendant → actual9/9+clean9/9, both full state/P/retained negatives/
3 late C cleanup, product PG/current-T→T2/PHOTO/browser → C1/C2/C5, later C8.
No PR-head update/new PR/merge/dispatch/rerun in this task. C6 HOLD after receipt;
C3/C1/C2/C5/C8 HOLD. MATERIAL/M3 IN_PROGRESS, not INTEGRATED/VERIFIED; PR34 Draft/
BLOCKED, gate OFF. Native/A08/renewal/collector/live/VM/working DB/S3/sends/deploy/
M4 unissued; broad CI optimization/IMPL-05 DEFERRED.

## История — C3-M3.1-MATERIAL-R2 — online SQL source correction / 2026-10-16 UTC

[C0 R2 assignment](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6208530769),
[C0 disposition](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6208519238),
[source/evidence§15.12](M3_CONTRACT.md#1512-c3-m31-material-r2--online-sql-parameter-correction--2026-10-16-utc).
Branch `c3/m3-1-material-r2` starts from exact base/sole parent
`d810dde939f727085af15f7614eeddd36f4909b8`, tree
`fb06ad7bf5cf4d821e880328888c9bbf25eea3b7`, base parent R1
`e7f554772ad4dd697d38c88f4f6423b3d3895499`. Main/frozen E933ddd…/0011 stays fixed;
the existing Draft PR34 C6 branch remains at d810dde. Final C3 identity/numstat and
commands are in one canonical PR34 receipt. Source REVIEW on return, then C3 HOLD.

Only six0012 JSON literal spaces and one forged-basis setup space remove unintended
SQLAlchemy null binds; decoded JSON and intended suppression rejection are unchanged.
Two focused tests exercise actual online Alembic/TextClause/psycopg parameter
construction and the PG case's real CREATE setup, without DB calls or SQL rewriting.
Against unchanged base inputs both fail with required-null InvalidRequestError;
corrected inputs both pass. Independent expansion: base bad indices2/3/48/58,
candidate all131 empty-parameter constructions PASS. Scoped units67 PASS/98 deselected;
Ruff/format3 and diff/source audits PASS in the reused locked offline environment.
No install/services/PG/Docker/browser/CI execution; client preflight is not actual PG.

**Current evidence: PR34 Draft/BLOCKED; MATERIAL/M3 IN_PROGRESS.** Final historical
CI38850821014/attempt1, tested merge51fca8…/tree fb06ad7…: **4 SUCCESS/5 FAILURE;
clean4 SUCCESS/5 SKIPPED**. Migration/startup failures did not retain traceback/
DDL/SQLSTATE; MAT-03 is reproduced source evidence, not an observed CI exception.
Normal state separately failed an H build before T/P; actual target/exit/stderr and
root cause remain UNKNOWN. Docker29 preparation499.951432356s is PARTIAL, not a full
P/state-lane PASS. C1/C5 source rereviews requested no additional product correction.

All six findings stay OPEN: C2-MAT-01/P1, C1-MAT-01/P1, C1-MAT-02/P2,
C5-MATERIAL-01/P2, C2-MAT-02/P2, C2-MAT-03/P1. Source correction does not close them.
Required later: actual0012 lifecycle/raw42/catalog/security/recovery/replay, current
T→T2 maintenance/File/Resume refusals, paired PHOTO/browser, both full state lanes
including3 late C negatives and9/9+clean9/9 on exact tested SHA/tree.

Preserved: contract prefix through§15.11 (546352 bytes/SHA25679f920fd…); original11,
applied0001–0011/ORIGINAL17/OLD_CHECK4;10 columns/6 old tables,4 new/42 total,
132 signatures; immutable Inbox winning pair/five NULL delivery fields; C6 sources,
frozen H/T/C/G/E, original S/retained600/P720, supervision/cleanup/individual bounds.

Next: C0 source intake → separate C6 diagnostics-only issuance on accepted C3 SHA
→ combined source intake → same PR34 automatic CI → C1/C2/C5 disposition → later C8.
No intermediate PR-head update/new PR/merge/dispatch/rerun. C1/C2/C5/C6/C8 HOLD;
C3 HOLD after receipt. No implementation INTEGRATED/VERIFIED. Gate OFF; native/A08/
renewal/collector/live/VM/working DB/S3/sends/deploy/M4 unissued; IMPL-05 DEFERRED.

## История — C6-M3.1-MATERIAL-COMPAT-R2 — terminal720 source checkpoint / 2026-10-16 UTC

[C0 accepted source/budget decision](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6207691746)
and [five-path assignment](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6207709114).
Separate branch/checkout `c6/m3-1-material-compat-r2`, exact accepted base
`e7f554772ad4dd697d38c88f4f6423b3d3895499`, tree
`0242e71790e0fe441ebc55a6311c80f5681b218f`, sole parent
`ef7b52d2d862e3d3e656ba56ccac8781e1d0a374`. Main/frozen E933ddd…/0011 and
the existing PR34 branch/head ef7b52… are preserved. Final source identity is in
the single canonical PR34 C6 receipt; no self-SHA/status-only commit.

**MATERIAL/M3 IN_PROGRESS; PR34 Draft/BLOCKED; all five findings OPEN.**
C6 source is REVIEW on return, then C6 HOLD; no implementation VERIFIED claim.
C3 R1 source was accepted by C0; its product PG/browser evidence is still required.

Current coordinator retains the original S and retained S+600, full T positive,
real120 timeout/export negatives, C/G/E, all archives/images/byte probes and late
three C cleanup negatives. Only P preparation receives explicit S+720. This is the
accepted120-second increase, not a600 optimization or a new clock at P. Version2
private single-use request binds exact E/candidate/phase/uid/P owner, both absolute
deadlines and saved successful E report/hash/owner/observed completion. P charges
actual observation−S and full preparation-end−S, including G image verification;
expiry/tamper/incomplete E refuse before runtime. Original frozen600 consumers,
ownership/checkpoint/supervisor/cleanup functions remain byte-exact.

[§15.11](M3_CONTRACT.md#1511-c0--terminal-material-preparation720-exception--2026-10-16-utc)
appends the accepted exception without altering the existing contract prefix.
P supervision remains remaining+480, nominal absolute bound S+1200; cleanup90,
individual command bounds, state25/browser25/foundation45,9 jobs/clean9 unchanged.
Measured old P handoff603.658495599/679.481488282s would leave116.341504401/
40.518511718s under720 **before unmeasured P preparation**.720 is not proved
sufficient/minimal; further failure returns BLOCKED to C0 without rerun/increase.

Scoped units in the reused frozen/offline environment: **625 passed**; protocol
nodes cover after600 admission, exact clock/private/source/owner/report refusal,
full preparation/end720 and failure/owned cleanup, actual coordinator entrypoints
and executed shell evidence gates. Static/immutability commands/results and exact
head/tree/parents/five-path numstat are in the canonical receipt. No local actual
PG/Docker/image builds/browser/CI execution or new dependencies/services.

Accepted R1 companions are read-only: private Inbox token,10 columns on6 existing
tables/42 total/132 signatures, P_COLUMNS/no-backfill, raw42 used55000 before DDL,
unused reverse/ORIGINAL17/OLD_CHECK4. C6 changes no DDL/backend/frontend/other tests.

Next C0 route: exact combined-source intake → move descendant into **the same**
Draft PR34 → one normal automatic CI → C1/C2/C5 re-review; C8 after actual gates.
Require9/9+clean9/9 on exact tested SHA/tree, both state lanes complete P preparation
<720 from S and all retained negatives/cleanup within25min, actual0012
catalog/migrations/recovery/refusal/security/races and paired PHOTO/browser proof.
C2-MAT-02 remains OPEN until those lanes pass. No dispatch/rerun/new PR or update
of the old PR34 head in this task. Gate OFF; C3/C1/C2/C5/C8 HOLD. No live/VM/working
DB/S3/sends/deploy/native/renewal/collector/M4 or broad CI optimization/IMPL-05.

## История — C3-M3.1-MATERIAL-R1 correction source / 2026-10-16 UTC

[C0 R1](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6201238585).
Base `ef7b52d2d862e3d3e656ba56ccac8781e1d0a374`, tree
`e4317cc6478b2c40669d96242c3adb89079ab46c`; separate branch
`c3/m3-1-material-r1`. Only0012←0011; no new PR or push to the PR34 C6 branch.

Three CASE grammar fixes and the accepted private Inbox winning token correct
C2-MAT-01/C1-MAT-01 at source level. Result/token are a closed immutable pair;
Job delivery fields remain NULL. Inventory is10 columns on6 old tables,4 new/42
all tables,132 surviving signatures. Current C6 inventory/no-backfill/used-result
companions updated; orchestration and budget untouched. Original17/CHECK4 and
applied0001–0011 retained exactly.

Known T→fresh T2 now has current-version checks after real maintenance, late File
and Resume, with Telegram and two CONTROLLED producer arms. R3-T4 requires exact
rejection plus same-claim positive neighbor. Four actual paired PHOTO journeys are
written: real TEST bytes→FetchTransfer/private S3, caption eligibility, loaded-image
invalidation and old-file grant refusal, unmodified real delayed grant response.
No new product/frontend/public API capability.

Evidence/precise node map: [§15.10.4](M3_CONTRACT.md#15104-c3-m31-material-r1-correction--2026-10-16-utc).
Ruff/format9, targeted79 unit, complete browser-harness68 unit, typecheck and32
MessagingPanel component tests PASS;121 PG tests collected only. Actual PG/Docker/
S3/browser/migrations/races NOT RUN locally. Findings remain OPEN pending C0 and
actual evidence; C2-MAT-02 budget remains C6's separate OPEN blocker.

One canonical PR34 receipt binds final head/tree/parents/numstat. C3 HOLD after
return; C0 accepts source then assigns C6 descendant for the same Draft PR34 and
its normal automatic CI. No dispatch/rerun, activation, live/VM/sends/deploy/M4.

## История — C3-M3.1-MATERIAL source checkpoint / 2026-10-15 UTC

[Исходная выдача](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6195028336),
[продолжение source-first](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6195754984).
**MATERIAL/M3 IN_PROGRESS; C3 HOLD после canonical return. A03 NOT VERIFIED.**
Design PR33 интегрирован, C2-PROV-04 CLOSED на уровне design по
[C2 R3](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6193806982)/[C0](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6193890730).

| Binding | Значение |
|---|---|
| Checkout/branch | Отдельный `c3/m3-1-material`; новый PR не открыт |
| Base/first source commit parent | `933ddd284ff5b77fb1aa88a4270ab0032bc499c9` |
| Base tree/schema | `d0759acb9f83ec3f3e10d9c5d1325c937c343ee7` /0011 |
| Assigned successor |0012←0011, `migrations/versions/0012_message_provenance.py` |
| Scope | Закрытый allowlist57; applied0001–0011/original11/manifest и prefix345960 immutable; C6 reserved6 untouched |
| Final head/tree/parent/paths/numstat | Один source receipt в PR33; без self-SHA/status-only commit |

Source реализует closed V2+saved V1 replay, default-OFF material ingress, bounded
fold, stable target/effect/Audit/suppression, original-before-File/grouping, terminal
winning replay, shared Turn/control/guard/Escalation context, no-refetch/current-only
API/OpenAPI/TS/UI and billing Audit companion. Historical source and current state
разделены. Browser fixture имеет finite material preset/actions, без подмены provider
или arbitrary current DML. PG cases включают реальные worker barriers, physical
process exit/restart, negative constraints/FORCE RLS, миграции и all42 fingerprints.

Полный source inventory/table columns/constraints/triggers132 signatures/grants,
17 immutable downgrade body hashes,4 fixed CHECK hashes, owned used blockers,
source/schema pairing и P-A03/R3 test node mapping — [M3_CONTRACT§15.10](M3_CONTRACT.md#1510-material-implementation-source-checkpoint--2026-10-15-utc).
**Это DDL/source inventory, actual PostgreSQL catalog NOT RUN.**

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


Следующая последовательность: C0 проверяет exact source checkpoint; C6 получает
отдельную выдачу от принятого head и последовательно меняет только reserved6 egress
paths для0012, сохраняя H/T/C/G/E projections. Затем C0 назначает общий candidate и
один Draft implementation PR; все9 automatic jobs/clean-source checks и actual
backend PG/migration/paired browser обязательны. Сверяются final PR head, tested
merge SHA/tree и выполнение новых node IDs, а не только badge. Failures исправляются
в том же scope; известный timeout возвращается C0 с exact log. C6 пока HOLD.
Native/latest-state/P-A03-09/renewal/collector/live/VM/deploy не активированы.
Gate default OFF; пользовательские credentials/VM-команды/сообщения не нужны.

## История выдачи C0 — C3-M3.1-PROVENANCE-CONTRACT-R3

[Поручение C0 R3](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6191877569).
**C3 R3 — REVIEW при передаче diff, затем HOLD.** M3 IN_PROGRESS;
C1/C2/C5/C6/C8 HOLD до отдельной выдачи. Ниже сохранена история; её прежние active
формулировки не новые поручения. Единственный обязательный finding — C2-PROV-04/P2,
OPEN до адресного C2 re-review и приёмки C0, не самостоятельно закрыт C3.

| Binding / evidence | Значение |
|---|---|
| Repository / PR / branch→target | Elefesys/ai-service-manager / тот же Draft [PR33](https://github.com/Elefesys/ai-service-manager/pull/33) / `c3/m3-1-provenance`→main |
| R3 start / sole parent | `165dd09b0138c66216a8a7d8240af95663165769` |
| Start tree | `f619c5ebad814141d0db0f9cbafccc6cd2089200` |
| Accepted main/base / schema | `bae25093bafb9534af68de5c586763667b896e70` /0011; applied0001–0011 immutable; successor/revision/order не назначены |
| C3 R2 / C0 intake | [R2 receipt](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6190608696) / [C0 intake](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6191327158), сохранены |
| C1 R2 | [PASS](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6191616132): C1-PROV-01…05 CLOSED на уровне revised design |
| C2 R2 | [CHANGES_REQUESTED](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6191712300): C2-PROV-01…03 CLOSED на уровне revised design; C2-PROV-04/P2 OPEN |
| Existing R2 CI | [38724672096/attempt2](https://github.com/Elefesys/ai-service-manager/actions/runs/38724672096), aggregate9/9+clean9/9 SUCCESS по C0; только R2 evidence, не R3/future implementation PASS |

Отдельный чистый checkout exact start; remote main/branch/tree сверены. Один
содержательный commit поверх R2 в том же PR, без reset/rebase/force-push. Final
head/parent/tree/numstat и actual automatic CI — в одном новом canonical R3 receipt,
без self-SHA/status-only commit; старые authored receipts не редактируются.

Ровно3 paths: `docs/tasks/M3_CONTRACT.md` (точечно§15.4/7/9, статус§15.1), этот handoff,
`docs/TASK_REGISTER.md`. Accepted prefix345960 bytes/SHA256
`b53b3f9caa4af82c095cd2e4d1ac22a0bef435a5d657dacde3278498d2808302`,
original11/manifest и historical tails сохранены. AGENTS/Spec/применимые ADR,
MVP/Roadmap/Implementation Plan и actual0008 CHECK/FKs/final0009 grouping/capture,
shared seal/snapshot bodies сверены; accepted0011 не переоткрывается.

| R3 / C2-PROV-04 | Предлагаемая норма |
|---|---|
| R3-01 →§15.7 | Одна closed INITIAL_FOLD_SUPPRESSED member форма: original IMAGE_REFERENCE/INBOUND, file=NULL только с same-Message immutable initial evidence/effect/origin; legacy PHOTO по-прежнему требует FileObject |
| R3-02 →§15.4/7 | Общие grouping/member validator/seal/V2 snapshot/readiness различают historical identity и usable current. TEXT без media wait; replacement PHOTO PARTIAL; hidden original без membership/FETCH, restore ORIGINAL_NOT_FETCHED не создаёт Turn |
| R3-03 →§15.4/7 | Один original atom; Audit→effect→evidence→member, commit integrity. Original connection→C и sorted target/Message/Turn order, identity-only FKs; stable-target SENT без reverse connection/foreign Job; FORCE RLS/private capabilities сохранены |
| R3-04 →§15.9 R3-T1–T5 | Ручные traces/future PG assertions: m2/context+2/один effect+Audit, fresh revision1/member_count1 либо один collecting increment; forged evidence refusal/zero partial atom; replay/hidden restore/seal/V1 |

API/current DTO, V2 codec/ordering/TargetResult, no-refetch/native/renewal policy и
future path allowlist не расширены. P-01/native/A08/latest-state OPEN/NOT VERIFIED;
P-04/P-05 OPEN. TEST interval истёк, VM UNKNOWN/live BLOCKED_TEST_INTERVAL.
Static scope/prefix/original11/manifest/history/link/diff checks и ручные traces
достаточны; это не executed PG tests. Product suites/Docker/Actions dispatch/rerun
не запускаются ради docs; automatic CI не отключается и не переносится с R2.

Следующий шаг C0: exact-head intake, затем адресный **C2 re-review только
C2-PROV-04 и затронутых shared bodies/locks**. Полный C1 review не нужен при сохранённом
API/current DTO. Runtime/migrations/renewal/probe/VM/live/DB/S3/sends/deploy не выданы;
PR Draft, merge пользователем после приёмки. M4/CI optimization/IMPL-05 не открываются.


## История выдачи C0 — C3-M3.1-PROVENANCE-CONTRACT-R2

[R2 C0](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6189981613)
и [disposition C0](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6189999448).
**C3 R2 — REVIEW при передаче этого diff; затем C3 HOLD.** C1/C2 read-only reviews
завершены CHANGES_REQUESTED; C1/C2/C5/C6/C8 HOLD до адресной повторной выдачи C0.
Ниже сохранены прежние snapshots; их старые статусы не новые поручения. M3 IN_PROGRESS.

| Binding / evidence | Точное значение |
|---|---|
| Repository / PR / branch→target | Elefesys/ai-service-manager / тот же Draft [PR33](https://github.com/Elefesys/ai-service-manager/pull/33) / `c3/m3-1-provenance`→main |
| R2 start / sole parent нового commit | `f5e71ff47f000ee55a5509cae4ec22487ca8b6c2` |
| Start tree | `9b91c33724e4f847c8febfbeb24bcf42188e4713` |
| Accepted main/base | `bae25093bafb9534af68de5c586763667b896e70` |
| Accepted schema |0011; applied0001–0011 immutable; successor/order не назначены |
| Initial design receipt | [C3](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6188075575), сохранён |
| Initial C0 intake / old-head CI | [C0](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6188855331); [38707131575/attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/38707131575)9/9 SUCCESS+clean9/9 по C0, только initial head evidence |
| C1 / C2 completed reviews | [C1](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6189743405) / [C2](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6189782680), CHANGES_REQUESTED к§15; accepted CONTROL/GUARDS/Escalation не переоткрыты |

Отдельный чистый checkout R2 от exact start; remote main/branch/parent/tree сверены.
Продолжение PR33 одним содержательным commit поверх start, без reset/rebase/force-push
и нового PR. Final head/tree/numstat и actual automatic CI только в новом R2 receipt,
без self-SHA/status-only commit. При ref drift — конкретная дельта C0, не перезапись.

Разрешены ровно `docs/tasks/M3_CONTRACT.md`, этот `docs/tasks/M3_HANDOFF.md` и
`docs/TASK_REGISTER.md`. §15 редактируется **по месту**, не конкурирующий§16.
Принятые первые345960 bytes остаются с SHA256
`b53b3f9caa4af82c095cd2e4d1ac22a0bef435a5d657dacde3278498d2808302`.
Original11/manifest/history неизменны. Future allowlist§15.7 не write permission.
AGENTS/IMPL-001/canon из первой выдачи, особо Spec4.8–4.10/5.12.1,
ADR026/180/267 и MVP GJ-G/J сверены с exact source0004–0011/normalizer/results/DTO.

| R2 / finding | Где и что исправлено |
|---|---|
| R2-01 / C1-PROV-02 |§15.3: closed variants/NULL/common equality, один per-target union/unique-ID ordering |
| R2-02 / C2-PROV-01 |§15.3–4: any valid undated edit→sticky uncertainty, без identical NOOP; known/deferred traces и точные increments, history не выравнивается |
| R2-03 / C2-PROV-02 |§15.6–7: separate codec2 queued EDIT/DELETE и MATERIAL_PROCESSED/NULL Inbox Message, retained V1; full telegram_fingerprint |
| R2-04 / C1-PROV-03 |§15.4/9: new-key terminal Escalation errors точные, old winning replay сохранён |
| R2-05 / C1-PROV-04 |§15.3–4/9: chosen no-refetch, closed current DTO/examples, grant/late response/refresh/TTL |
| R2-06 / C1-PROV-01 |§15.5/8/9: Console-only canonical reply; native-only HUMAN до reconciliation, latest-state case OPEN |
| R2-07 / C1-PROV-05 + C2-PROV-03 |§15.7–8: оба TEST окна; append subscription+CAS single mode row, immutable before/after, replay исходного T0; schemas последовательно |
| R2-08 / C2-P01/P03/P04/P06 |§15.4/6/7/9: exact composite identity, historical effect/Audit versions, stable-target SENT FK/locks, shared apply/readiness/effective view |

P-02 направление material/per-target/deferred/sticky suppression выбрано C0;
исправленная ordering-норма ждёт review. P-03 C0 выбрал no-refetch ограниченного slice:
«фото заменено, новое изображение недоступно», PARTIAL; full replacement/refetch не
поддержан. Current DTO/UI/grant ещё NOT VERIFIED. Это не приёмка A03/M3.

P-01 OPEN: кандидат native не human transcript. Поддержанный resumable human-reply
путь — canonical Console reply. После native-only разговора оставить HUMAN до
принятого reconciliation; не повторять доставленный native текст через Console.
Actual0011 полноту native history не проверяет и новой блокировки Resume не содержит.
Takeover→native «согласовали другой вариант»→Resume→client «да» остаётся незакрытым
latest-state case; native/A08 не списываются и NOT VERIFIED.

P-04/P-05 OPEN: последовательность revisions/implementation отдельно. Для будущего
renewal выбран append ACTIVE/COMPED + CAS expected NORMAL/PROVISIONED_LOCAL mode
с immutable before/after receipt/Audit, без runtime DML/смены old subscriptions.
Оба окна должны действовать; TEST2026-10-09T00:00Z истёк, VM UNKNOWN,
live BLOCKED_TEST_INTERVAL. Collector-only не зависит от A03 activation, но требует
согласованную actual schema; finite probe после native оставляет HUMAN.

Проверки R2: static scope/prefix/original11/manifest/history/link consistency,
ручные traces и git diff --check. Product suites/Docker/Actions dispatch/rerun не
запускаются. Automatic PR CI не отключается, old green не переносится на R2.
Foundation45/browser25/state25, prepare600/cleanup90,9 jobs/clean guards прежние.
Один новый canonical R2 receipt; старые C3/C1/C2 reviews не редактируются.
Возврат REVIEW→C3 HOLD→C0 exact-head intake→адресный повторный review.
Runtime/SQL/API/OpenAPI/frontend/tests/CI/dependencies, migration/renewal/probe/VM/
live/DB/S3/sends/deploy не выданы. PR Draft; merge пользователем после приёмки.
M3-ACCEPTANCE отдельно; M4/CI optimization/IMPL-05 остаются DEFERRED/не открыты.


## История выдачи C0 — C3-M3.1-PROVENANCE-CONTRACT (initial delivery PR33)

Единственная активная выдача: [C0,2026-10-15](https://github.com/Elefesys/ai-service-manager/pull/32#issuecomment-6185468957).
**C3 — IN_PROGRESS**, только design и план account probe. C1/C2/C5/C6/C8 HOLD до
адресного поручения C0. Ниже сохранена история завершённых выдач; её старые статусы
не разрешают новую работу. Весь M3 IN_PROGRESS, M4 не открыт.

| Exact start | Значение |
|---|---|
| Repository / branch → target | Elefesys/ai-service-manager / `c3/m3-1-provenance` → main |
| Accepted base / tree | `bae25093bafb9534af68de5c586763667b896e70` / `ad857f156e6ff7ebb23a18c4b127256e774dd7bd` |
| Ordered parents | `ab06bc135f45c88203e434eacefd107412a8eb15` + `ad161ce0e04f6271890458cbec56681199846df8` |
| Accepted schema |0011;0001–0011 immutable; следующая revision не назначена |
| PR32 | [INTEGRATED / VERIFIED LOCAL/TEST по C0](https://github.com/Elefesys/ai-service-manager/pull/32#issuecomment-6184721998) |
| Base main CI | [38684447412/attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/38684447412),9/9 SUCCESS+clean9/9;1153 unit/680 PG/79 Escalation PG/294 frontend/39 browser |

Создан отдельный чистый checkout. Remote main/new branch, parent order/tree сверены
до правок и совпали с exact base. Без reset/rebase/force-push/продолжения PR31/PR32.
Новый Draft PR после содержательного contract diff; final source/CI только в PR receipt.
При чужой дельте branch/main — остановка с конкретным diff, не перезапись.

Разрешены **ровно три paths**, один содержательный commit:

- `docs/tasks/M3_CONTRACT.md`: append нового§15; прежние345960 bytes неизменны,
  SHA256 `b53b3f9caa4af82c095cd2e4d1ac22a0bef435a5d657dacde3278498d2808302`,
  blob `e19f8c8aa82c43ec88e8873f16675d13929934e5`;
- этот `docs/tasks/M3_HANDOFF.md`: один активный блок, предыдущий C5 блок — история;
- `docs/TASK_REGISTER.md`: PR32 accepted evidence, C3 IN_PROGRESS/остальные HOLD,
  остаток A03/A08/acceptance и DEFERRED.

Источники: AGENTS/IMPL-001; original11/manifest; Spec4.6–4.10/5.10–5.14/18.5–18.8/24.7;
ADR019–026/121–128/267/272; MVP GJ-G/J; Roadmap/Plan M3.1/M3.2;
M2_CONTRACT2/10, M3_CONTRACT6/9/12.6/12.9 и принятые CONTROL/GUARDS/Escalation;
нижние§4.4/5/6. Actual normalization/webhook/SQL/Message/Turn/control/guards/escalation
и tests прочитаны. Официальные Telegram sources заново проверены2026-10-15;
DOCUMENTED/CURRENT SOURCE/OBSERVED ACCOUNT/PROPOSED разделены в§15.1.

| Поручение | Результат proposal |
|---|---|
| P01 |§15.1–2: field/provenance table; V1 теряет offline/edit_date, Telegram ignored receipt не хранит projection |
| P02 |§15.3–4: typed edit/delete, scoped targets/deferred/order/batch/no-op, exact increments, Turn/file/Escalation/guard/locks/Audit |
| P03 |§15.5: native identity не доказывает post-Resume causality; finite table, explicit Console/manual alternative для решения C0 |
| P04 |§15.6–7: V1 replay before V2 parse, shared namespace, cutover/restart/refusal, schema/security и exact proposed paths без revision |
| P05 |§15.8: finite post-auth collector, supported TEST renewal gap, controlled actions/redaction/stop; только план |
| P06 |§15.9: отдельные A03/A08 assertions, actual OPEN P-01–05 и будущая адресная выдача |

Два policy решения не замаскированы под существующую реализацию: per-target material
increments/invalidated Turn не запускает автоматический ответ; replaced photo помечено
MEDIA_REPLACED_UNAVAILABLE без refetch в минимальном варианте. C0 принимает эти
границы или выдаёт конкретное расширение. Native automatic takeover NOT VERIFIED;
Console Takeover/manual atomic takeover остаются принятыми. Unknown delivery не
подтверждается echo, auto-Resume/старый Turn revival запрещены.

Static design verification: exact three-path scope, prefix/original11/manifest/link
consistency и `git diff --check`. Product tests/Docker/свои Actions dispatch/rerun
не нужны и не выполняются. Автоматический PR CI не отключается; actual final-head
status/run/attempt указываются в receipt, прежний main PASS не переносится.
Foundation45/browser25/state25, prepare600/cleanup90,9 jobs/clean guards прежние.

Один canonical C3 receipt нового Draft PR: exact base/head/parent/tree,3 paths/numstat,
prefix/original11, P01–P06 map, evidence levels, commands/results/actual CI, OPEN и
next scope. Возврат REVIEW либо конкретный BLOCKED, затем HOLD. C0 назначает C1/C2,
и при необходимости C6; merge пользователем после приёмки. Старые C5/C8 receipts
не меняются. Никаких runtime/SQL/API/frontend/test/fixture/script/CI/dependency правок,
VM/live/ACK/sends/deploy/рабочих DB/S3. Новый path — minimal proposal C0 до применения.
TEST interval2026-10-09T00:00Z истёк; renewal не выполнялся. M3-ACCEPTANCE/M4/LLM/
production/CI optimization/IMPL-05 вне scope, прежний канон/manifest immutable.


## История выдачи C0 — C5-M3.2-CONSOLE-ESCALATIONS (завершено в PR32)

Историческая выдача: [C0,2026-10-14](https://github.com/Elefesys/ai-service-manager/pull/31#issuecomment-6172495208).
C5 — единственный автор; остальные C1/C2/C3/C6/C8 HOLD. Нижние блоки — история,
их старые OPEN/proposal/status headers не переоткрывают принятый backend/API.

| Exact start | Значение |
|---|---|
| Repository / branch / integration target | Elefesys/ai-service-manager / `c5/m3-2-console-escalations` / main |
| Accepted base / tree | `ab06bc135f45c88203e434eacefd107412a8eb15` / `3c97459793bd200dfe9720b37ea0895b4189a8bb` |
| Base ordered parents / schema | `c502d5fd258aef15bb5549e1529df8d038a4fb9b` + `09d92a141ae5b2f000b9de27e562c1d7a3fd791f` /0011 |
| PR31 integration | [C0 INTEGRATED/VERIFIED LOCAL/TEST](https://github.com/Elefesys/ai-service-manager/pull/31#issuecomment-6170928749) |
| Actual main CI |38584344077/attempt1,9/9 SUCCESS+clean9/9;1133 unit/680 PG/79 Escalation/194 frontend/33 browser |
| Finding disposition | C8-M3-ESC-01 CLOSED; C6-ESC-COMPAT-01 CLOSED |

Отдельный чистый checkout создан от base после remote/ancestry проверки.
Новый Draft PR после содержательного UI diff. Не продолжать старые branches/PR,
не reset/rebase/force-push/merge. При изменении main/занятой ветке сообщить C0.

Источники: AGENTS/IMPL-001; Spec5.10–5.14/18.5–18.8/Console;
ADR024/025/026/267/272; MVP GJ-G/J; Roadmap M3/Implementation Plan M3.2;
M3_CONTRACT8/12/13/14.3–5/14.9/14.16–17 и generated OpenAPI/actual escalation modules.
Original11 checksums подтверждены; canonical sources/contract не меняются.

Результат: компактная OWNER queue по Workspace без выбора Business/channel;
stored status/validity/wait/maintenance раздельно, per-page observed_at,
opaque cursor, detail canonical Escalation→Conversation→Client, internal answer
и cancel по свежим flags с повторной серверной проверкой. Ответ exact Unicode,
не send/Resume/исполняемая инструкция. Frozen actor/context/body/key только в памяти;
после ambiguity/session/CSRF только явный same-intent retry; conflict останавливает
повтор, valid200 допускает далее только GET. Late responses не меняют новый scope.
Общая protected owner boundary, прежние auth/Billing/Audit/messaging/CONTROL/private
image/UNKNOWN сохранены. Другой context не получает прежний answer/identity.

Exact allowlist (максимум17 paths):
- `frontend/src/EscalationsPanel.tsx`, `frontend/src/EscalationsPanel.test.tsx`;
- `frontend/src/escalation-api.ts`, `frontend/src/escalation-api.test.ts`, `frontend/src/escalation-fixtures.test-helper.ts`;
- additive `frontend/src/App.tsx`, `frontend/src/App.test.tsx`;
- только canonical decision notice/wiring в `frontend/src/MessagingPanel.tsx`, соответствующий `frontend/src/MessagingPanel.test.tsx`;
- `frontend/src/style.css`, `frontend/e2e/messaging.spec.ts`;
- finite `scripts/m2_4_browser_fixture.py`, `scripts/m2_4_browser_worker.py`, `tests/test_m2_4_browser_fixture.py`;
- `docs/tasks/M3_CONSOLE_ESCALATIONS.md`, этот handoff, `docs/TASK_REGISTER.md`.

Backend/migrations/applied0001–0011/DDL/grants/auth/tenancy/R4/OpenAPI/M3_CONTRACT,
старые consumers/ConversationControl, dependencies/locks/Compose/Docker/workflows,
CI scripts/budgets неизменны;0012 не назначена. Foundation45/browser25/state25,
prepare600/cleanup90 и9 jobs/clean guards сохраняются. Другой path — blocker и
minimal proposal C0 до применения. VM/live/deploy/рабочие DB-S3/внешние отправки не выданы.

UI-E01–07 и достаточные assertions изложены в выдаче и
[M3_CONSOLE_ESCALATIONS](M3_CONSOLE_ESCALATIONS.md). Новые runtime journeys только
после старой seeded PENDING image границы в messaging.spec; migrator не создаёт
Escalation/receipt/Audit/Message/Outbox/Jobs. Normal Resume→marker→Inbox/Turn/Worker,
asm_runtime TEST/storage guard, finite presets/read-only counters, CALL/EFFECT0
для решений; никакого clock/scheduler fault framework ради UI. Synthetic UI-E03
отделён от retained actual PG evidence, не объявляется новым server execution.

Локально typecheck/frontend/build, Ruff/fixture unit/diff. Без local Docker actual
runtime NOT RUN locally. Final-source PR CI обязан выполнить штатные ci.sh и
test_browser.sh,9/9 SUCCESS+clean9/9 и retained suites. Не повторять зелёный SHA.
Canonical C5 receipt в новом Draft PR: exact base/final head/parent/tree/paths/numstat,
UI-E01–07→tests/results, commands/limitations, run/attempt/9jobs/clean/actual checkout/
merge parents/tree. Docs вместе с implementation, без post-CI status commits.
Возврат REVIEW/BLOCKED и HOLD; C0 intake→scoped C8→C0 decision→merge пользователем→
actual main CI. Весь M3 IN_PROGRESS; native/edit-delete provenance/M3 acceptance впереди.

## История выдачи C0 — C6-M3-FOUNDATION-TIME-BUDGET

Дата:2026-10-14 UTC. [Поручение C0](https://github.com/Elefesys/ai-service-manager/pull/31#issuecomment-6168070726).
C3 HOLD; C8 HOLD. Приёмка PAGE-R1 BLOCKED незавершённым CI; M3 IN_PROGRESS.
C6 выполняет только эту выдачу в отдельном checkout, последовательно в том же
Draft PR31/`c3/m3-2-escalation`, без reset/rebase/force-push.

| Source / gate | Exact value |
|---|---|
| Exact base | `0dd8a3490cfccf7fb613c169f3bd5116373827fd` |
| Sole parent / base tree | `c413a6f80b30fbdd12717af3f12642a5b5f785f4` / `c21d936d22b85fe849296f06650f800ff459b6b1` |
| Accepted main / frozen G | `c502d5fd258aef15bb5549e1529df8d038a4fb9b`,0010 |
| Base tested merge | `f5409011ccf81223b6bc1f1286766c866779da85`; ordered parents main+base, tree=base tree |
| Base workflow blob | `8a1c480320c0518075edd4ecf2a74177acdde3a0` |
| Previous CI |38549789284/attempt2:8 SUCCESS/1 CANCELLED, clean8/1 SKIPPED; foundation40m19s |

AGENTS, IMPL-001, canonical architecture/ADR/roadmap/plan и действующие contract
boundaries прочитаны; remote/base и чистота exact checkout сверены до изменения.
Разрешены максимум4 paths: `.github/workflows/ci.yml` — только foundation40→45;
`M3_CONTRACT.md` — append§14.17 после неизменного prefix; этот handoff — один
активный C6 block с сохранением истории; `docs/TASK_REGISTER.md` — текущая задача
и фактический BLOCKED предыдущего CI. Все четыре входят в один содержательный commit.

Текущий override foundation45 заменяет только прежний лимит40; prepare600s,
cleanup90s/state25m/browser25m и остальные limits прежние. Остальные workflow
bytes,9 jobs/matrix/steps/conditions/clean checks, pins/locks/controllers/dependency,
product/SQL/DTO/OpenAPI/tests/applied migrations не меняются. Новые tests, builds
и полные local suites не нужны; проверить exact diff и `git diff --check`.

После одного содержательного commit — один новый штатный PR CI на final source,
9 SUCCESS+clean9 SUCCESS без SKIPPED. Нужны actual foundation completion,
`HTTP and frontend reverse-proxy smoke passed`, unit/PG/Escalation/frontend/browser
counts и обе normal/Docker29 state lanes. Старые8 зелёных jobs не переносятся.
В отдельном canonical C6 receipt: head/parent/tree, paths/numstat/workflow line,
run/attempt/jobs/clean/duration/counts/smoke, actual checkout/virtual merge/ordered
parents/tree и существующие source artifacts. C3/C8 receipts не переписывать.
При cancelled/failed — точные step/time/log, BLOCKED и HOLD; не повторять цикл,
не повышать45 и не менять gates. После receipt C6 HOLD; C0 назначит только
C8-M3-ESC-01 и затронутые ESC-C02/07. Finding пока OPEN, C6-ESC-COMPAT-01 CLOSED.
C5 owner-wait/native/provenance/M3 acceptance впереди; IMPL-05 fix и CI optimization
DEFERRED. VM/live Telegram/рабочие DB-S3/deploy/merge не выполнять.

<details>
<summary>История PAGE-R1 и прежних выдач; текущая выдача C6 приведена выше</summary>

## История выдачи C0 — C3-M3.2-ESCALATION-PAGE-R1

Дата:2026-10-14 UTC. [Поручение C0](https://github.com/Elefesys/ai-service-manager/pull/31#issuecomment-6164474811)
по [C8-M3-ESC-01/P2 OPEN](https://github.com/Elefesys/ai-service-manager/pull/31#issuecomment-6164119233).
HOLD C3 снят только для page wire correction; C8 после review остаётся HOLD.
Тот же Draft PR31/`c3/m3-2-escalation`, отдельный checkout, последовательный
commit без reset/rebase/force-push. Remote и чистота проверены до изменения.

| Source | Exact value |
|---|---|
| Base | `c413a6f80b30fbdd12717af3f12642a5b5f785f4` |
| Base tree / sole parent | `1a87601835bd9646e40f62e399f0b71304e28abc` / `9d65a69c47d26ceacdb5f3093d14720c5d40e779` |
| Accepted main / frozen G | `c502d5fd258aef15bb5549e1529df8d038a4fb9b`,0010 |
| Reviewed base CI |38525189666/attempt1,9/9+clean9/9;1122 unit/679 PG,78 Escalation,194 frontend/33 browser |
| Base tested merge | `1b4dcd13a482a2efe0cc148499078711c468928d`, parents main+base, tree=base |

Разрешены ровно9 paths:
- `backend/src/asm/conversations/escalation_http_models.py`: required page Timestamp/consistency.
- `backend/src/asm/conversations/escalations.py`: strict list envelope и один DB clock.
- `migrations/versions/0011_escalations.py`: только тело escalation_list внутри _reads().
- `contracts/openapi.json`: штатная regeneration page schema.
- `tests/test_m3_2_escalations.py`: targeted DTO/schema/service regression.
- `tests/test_m3_2_escalations_api_postgres.py`: actual raw HTTP/PG empty/nonempty/pagination.
- `docs/tasks/M3_CONTRACT.md`: append§14.16 после прежнего339842-byte prefix.
- `docs/tasks/M3_HANDOFF.md`: этот активный блок, история ниже сохранена.
- `docs/TASK_REGISTER.md`: текущая correction/finding и факты.

Результат: ровно items,next_cursor,required observed_at; один MATERIALIZED DB clock
передаётся через empty/nonempty envelope, все item clocks совпадают. Сохранить
guards, UNAVAILABLE, lookahead/≤100/status anchor, read-only GET и business lifecycle.
0011/down0010 ещё candidate; остальные тела/DDL/signatures/profiles,0001–0010,
controller/dependency/pins/locks/workflows/Compose/frontend immutable в этом R1.

Сначала regression:24 PASS/7 FAIL до code fix; затем31 focused PASS/9 integration
 deselected, static/contracts/original11 checks PASS. Local Docker отсутствует,
local PG NOT RUN; один новый raw HTTP/PG case collected, прежние78 сохранены.
Не переносить base GREEN. Final-source CI9+clean9, обе G→E/state lanes и migration
reverse обязательны; бюджеты prepare600/cleanup90/state25/foundation40/browser25
сохранить. Полные local suites/CI optimization и новый C6 review не назначены.

Возврат через [canonical C3 receipt](https://github.com/Elefesys/ai-service-manager/pull/31#issuecomment-6152762197):
final head/parent/tree, delta отc413/numstat, DB clock trace, commands/results,
actual HTTP/PG/CI run/attempt/jobs/clean/checkout/parents/tree. Docs идут вместе
с substantive fix, без status/SHA-only commit. После CI — REVIEW и HOLD;
finding OPEN до C0/C8, весь M3 IN_PROGRESS. C0 назначает только повтор C8-M3-ESC-01
и затронутых ESC-C02/07; остальные independent PASS сохранены. C6-ESC-COMPAT-01
CLOSED. C5 owner-wait/native/provenance/acceptance впереди; IMPL-05 fix и CI
optimization DEFERRED. VM/live Telegram/рабочие DB-S3/deploy/merge запрещены.

<details>
<summary>История implementation выдачи до PAGE-R1; прежние checkpoints и результаты</summary>

## История выдачи C0 — C3-M3.2-ESCALATION-IMPLEMENTATION

Дата: 2026-10-13 UTC. Основание — [конкретная выдача C0](https://github.com/Elefesys/ai-service-manager/pull/31#issuecomment-6151237330).
Продолжение от checkpoint разрешено [решением C0](https://github.com/Elefesys/ai-service-manager/pull/31#issuecomment-6161454304)
после [адресного C6 review](https://github.com/Elefesys/ai-service-manager/pull/31#issuecomment-6161347908).
Она заменяет прежний contract-only HOLD ниже. Продолжать тот же Draft PR31,
ветку `c3/m3-2-escalation` в отдельном checkout. Реализация разрешена;
единственный статус исполнения — в [TASK_REGISTER](../TASK_REGISTER.md).

| Source / gate | Принятый факт |
|---|---|
| Accepted main / frozen G / schema | `c502d5fd258aef15bb5549e1529df8d038a4fb9b` / `0010` |
| Implementation start | `65454012c0e5a2c9643bf1401d86773a5a4df29a` |
| Start tree | `de09e1bf435d15929059f4e7691bd1fa17c0f2a4` |
| Start CI | [38430231534/attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/38430231534), SUCCESS9/9 + clean9/9 |
| Actual tested start merge | `2650c69c48c0e882317e6ca6a68cda18f26918ed`, parents main+start, tree=start |
| Accepted R2 contract | 331348 bytes, blob `3d2f88ddedf0ab9944db3181040abe16a7034e81`; append evidence after§14.11 |
| Assigned migration | `migrations/versions/0011_escalations.py`, revision0011/down0010; applied0001–0010 immutable |

C0 принял R2; три design findings CLOSED. Legacy-overload finding NOT CONFIRMED.
Оба diagnostic patches (C3 refresh и C6 observer) приняты и сохраняются.
Исторические причины CI failures UNKNOWN; отдельное расследование прекращено.
На принятом start текущих CI blockers нет. Эти результаты не проверяют E runtime.

### 0.1. Результат и принятые границы

Работающий LOCAL/TEST backend/API по M3_CONTRACT§14, без нового milestone:
trusted CONTROLLED Inbox→Turn→PROCESS_TURN/ESCALATE_OWNER создаёт отдельный
запрос; live OWNER читает очередь/detail, resolve сохраняет внутренний ответ,
cancel закрывает ожидание; reminders2/5min и expiry10min durable и recoverable.
Это M3-A09 и основание будущего owner-wait UI, без UI реализации здесь.

Exact marker `CONTROLLED ESCALATION TEST` допускается только при fresh live
Resume OWNER и принятом CONTROLLED_GUARDS_V1. Lifetime exclusion GUARDS/Escalation
на Turn, historical replay, canonical Workspace/Client/Conversation и точные
fingerprints обязательны. Не создавать запрос migrator-ом вместо runtime,
не вводить public create API/произвольного actor. Answer1..512 scalars/2048bytes
сохраняется точно, без send/Approval/Resume и оживления старого Turn.

PENDINGv1→RESOLVED/CANCELLED/EXPIREDv2; assignee immutable; resolve только ему,
cancel любому current OWNER. Material context/control invalidation атомарна
и не добавляет лишний counter bump. Local read/decision независимы от billing/
channel availability. Ровно четыре routes§14.5, existing cookie/Origin/CSRF,
strict DTO/error/cursor, exact key/body, current authority и saved receipt.

Две таблицы,36→38;11 function profiles, FORCE RLS/capability-only runtime.
Owner UPDATE→Audit→receipt→context в одной transaction. Ациклические identity,
terminal/relation/membership и seven-column receipt→Audit FKs. Cleanup строго
receipt→Esc Audit→timer Jobs→request→old parents, без CASCADE/disable/nulling.
Timer post-lock trusted time и due-before-attempt; exact allowlisted23514
внутри rollback, затем committable DEAD/INVALID_INPUT/NULL; остальные ошибки
и failed commit не объявляют сохранённый успех. До expiry DEAD не стирает
ожидание, после expiry actions запрещены даже без scheduler.

### 0.2. Канон и точный scope

AGENTS, IMPL-001; оригиналы Spec§§1.7/5.10–5.14/14.11/16/18.5–18.8/24.7;
ADR023–026/121–128/139/197–198/267; MVP GJ-G/GJ-J; Roadmap M3;
Implementation Plan M3.1/M3.2; OPEN082/083/085. Принятые §§8/9/12/13/14
M3_CONTRACT и actual dependencies обязательны; canon/snapshots не менять.

Разрешены ровно40 implementation paths из **M3_CONTRACT§14.10** с указанными
там причинами и дополнительно этот handoff + `docs/TASK_REGISTER.md` для
переноса принятой выдачи/фактов. C0 добавил `tests/test_auth_contract.py` только
для exact approved four-route inventory diff; полный endpoint equality, семь
frozen auth routes и остальные assertions сохраняются. Максимум43 paths,
не требование изменить каждый.
`tests/test_m2_1_postgres.py`, `tests/test_m3_1_control_api_postgres.py`,
manifest/dependencies/locks/workflows/Compose/images не выданы.
Дополнительный path — конкретный diff/причина C0 **до применения**.

Пять условных paths: `scripts/prepare_telegram_egress.py`,
`scripts/test_telegram_egress.sh`, `scripts/test_telegram_egress_migration.sh`,
`tests/test_telegram_egress.py`, `tests/test_telegram_egress_migration.py` —
активированы C0 ровно для corrected replacement C6:41783 UTF-8 bytes,
SHA256 `2c63dc567c151c8c6be0be342f98f19eb947b6f355ad43a202bd76367140b0f8`.
Исходный proposal41097bytes/hash`78762113ce37a2709f366a8a95d4284525f9def366be579241f4c756bcf4540e`
отклонён: G report export мог заменить primary failure. Corrected finally
сохраняет исходное исключение, записывает export failure как secondary; без
прежнего failure export остаётся primary, private evidence retained.
Иная содержательная controller/budget/source-identity дельта требует конкретного
proposed diff C0 до применения. Новые pins не включаются. H/T/C/G identities
сохранить; G=`c502…`/0010 отдельно от E/0011. Нужна genuine G→E phase в двух
existing state lanes, exact38 E inventory и полное canonical residual timer
set после drain; kind/count waiver, сдвиг часов/available_at или удаление future
Jobs в asm_local запрещены. Serial private clock только disposable asm_test,
committed replacement и exact restore. Prepare600/cleanup90, state25min,
foundation40/browser25, exact Docker29 и все9 jobs неизменны.

### 0.3. Текущий implementation checkpoint и gates

Продолжение последовательно от `373aeaf42debba80266c976f95658124455045d5`,
parent`65454012c0e5a2c9643bf1401d86773a5a4df29a`,
tree`65ee8f983693ffd973f822c0d28cb952ef64999b`: remote head и clean source
совпали. Применены exact corrected controller replacement выше и approved
route diff1268bytes/SHA256`501b68c29f740cf57490b2129b5633db694ecde8e70e23c023773390bd060a3e`;
hashes, все base blobs/dependency и `git apply --check` проверены до изменения.
C6 controller review завершён; scope blocker закрыт решением C0, C3 продолжает
реализацию без нового общего C1/C2/C6 review. C0 проверяет фактическую интеграцию
C6-ESC-COMPAT-01 по следующему source diff; C3 не объявляет acceptance за C0.

Actual final-source PG/S3/G→E/CI9+clean9 ещё должны дать фактический результат.
Docker локально отсутствует; local collection/unit не считаются PG/daemon proof.
Нужны обе state lanes: genuine G baseline/old36/private S3/UNKNOWN, source/schema
readiness, drain API/worker/scheduler, repeat/unused reverse/used refusal до DDL,
fresh-reader ACK-loss identity/restart и полный canonical3 residual queue.
0010 helper branch не объявляется выполненным fallback restart; неизвестное
состояние STOP. Exact commands/results/checkout/archives/head/parents/tree и
timings/primary/secondary/cleanup — один обновляемый
[C3 receipt](https://github.com/Elefesys/ai-service-manager/pull/31#issuecomment-6152762197).
Старый CI38448949685/attempt1:5 SUCCESS/4 FAILURE, clean5/4 SKIPPED; он не
проверял эти patches и повторно не запускается. Никакого будущего GREEN заранее.

Сверка implementation matrix§14.9 дополнительно дала21 адресный PG case,
всего78 вместо57: write rollback, late-file lifetime/material, typed terminal
links и committable poison cleanup в claim/recovery. Это только два уже выданных
test paths; reviewed controller и его migration-controller dependency прежние.
Локально1122 non-integration PASS/0 FAIL; PG collection не runtime proof.
Причины/точные assertions — M3_CONTRACT§14.14 и canonical receipt. Все final-source
CI/clean gates остаются обязательными после содержательного test commit.
Actual первый run нового controller:650 PG PASS/8 FAIL (семь idle-queue assumptions
в новых fixtures, один старый function inventory). Минимальные fixes: normal
TEST_CONSUME worker drain до timer assertions и exact11 profiles в уже выданном
tenancy test. Production/DDL/controller bytes неизменны; причины сохранены§14.14.

Второй actual run38521506363:675 PG PASS/4 FAIL, jobs8 SUCCESS/1 FAILURE,
clean8/1 SKIPPED. Исправлены только новые test queries: Guard receipt имеет
`job_id`, а typed FK target проверяется catalog OID независимо от display/search_path.
Late-file lifetime и FK23503 уже сработали; детали§14.15. Все78 cases сохраняются,
production/controller/dependency прежние; новый source требует полного CI заново.

<details>
<summary>История checkpoint373aeaf: scope HOLD до решения C0, не активный blocker</summary>

Подготовлены domain/migration/API/Audit и focused tests. Runtime/PG/S3/browser/
Docker29 proofs **NOT RUN** локально: Docker и PostgreSQL отсутствуют. C3 не
выдаёт отдельные задачи ролям; конкретный proposed G→E patch возвращается C0
для адресного C6. Общий C1/C2 review не повторяется.

Локальный полный non-integration: **1113 PASS/1 FAIL**. Единственный failure —
`tests/test_auth_contract.py::test_auth_machine_contract_and_generated_c5_api_have_no_drift`:
closed total route inventory ещё не содержит четыре принятых Escalation routes.
Этот path не выдан; C3 сохранил assertion и подготовил отдельный proposed diff
C0, оставив семь frozen auth routes и остальные checks прежними. Это текущий
конкретный scope blocker; результат не называется зелёным.

Focused backend91 PASS, frontend Audit30 PASS; Ruff/mypy и generated OpenAPI
проверяются на candidate. Actual assertions/matrix§14.9, commands/results и
неприменённые patches — в одном обновляемом C3 PR31 receipt; SHA-only commits
не создавать. После C0/C6 review нужен final implementation CI9/9+clean9/9 с
actual checkout/archive/merge parents/tree. Start CI не переносится на E и
повторно ради статистики не запускается. C0 выдаёт scoped C8 после готового
candidate; C5 owner-wait — после принятого backend/API SHA и своего gate.

</details>

M3 остаётся IN_PROGRESS. M3/native/provenance, production OPEN082/083/085,
IMPL-05 OPEN/fix DEFERRED и CI optimization DEFERRED сохранены. M4/LLM/RAG,
Approval/M6, Notification Engine/M9, client follow-ups, production сроки вне
среза. VM/live Telegram/рабочие DB-S3/deploy/merge не выполнять.


</details>

<details>
<summary>Завершённая выдача ESCALATION-CONTRACT; принята C0, не активное поручение</summary>

## 0. Текущая выдача C0 — C3-M3.2-ESCALATION-CONTRACT

Дата: 2026-10-13 UTC. **CONTROL UI интегрирован и проверен; следующий срез —
Escalation backend/API в рамках прежнего M3.2.** C3 сначала дополняет единый
контракт минимальным §14. После адресного согласования схема/API реализуются
в этой же ветке и PR отдельным разрешением C0. Это не новый milestone.

### 0.1. Принятая база и точный старт

| Поле | Значение |
|---|---|
| Repository | `Elefesys/ai-service-manager` |
| Accepted main / schema | `c502d5fd258aef15bb5549e1529df8d038a4fb9b` / `0010` |
| Accepted tree | `9ed2c0cd679d1577b93998c5a429c90e4b810588` |
| Branch | `c3/m3-2-escalation`, отдельный checkout |
| C0 preparation/start | Sole parent = accepted main; полный SHA/tree в GitHub выдаче C0 |
| C0 preparation files | Только `docs/TASK_REGISTER.md` и этот handoff |
| Единственный write path C3 сейчас | `docs/tasks/M3_CONTRACT.md`, только новый §14 в конце |

[C0 post-merge PR30](https://github.com/Elefesys/ai-service-manager/pull/30#issuecomment-6142120541):
CONTROL UI **INTEGRATED / VERIFIED LOCAL/TEST**.
[Main CI38374030362](https://github.com/Elefesys/ai-service-manager/actions/runs/38374030362),
attempt1: **9/9 SUCCESS + clean9/9; 1089 unit/597 PG/192 frontend/33 browser**.
Tree actual merge точно совпадает с принятым candidate.

C3 продолжает подготовленную C0 ветку от указанного в выдаче start. Не использовать
слитые TURNS/CONTROL/GUARDS или отложенную CI ветку. Baseline M3_CONTRACT:
**238882 bytes**, blob `1763a5379926e4ae3e47483faf91b006e5bc4f30`.
Этот полный prefix должен остаться побайтно прежним. Два preparation docs C3
не редактирует. Новая migration сейчас не назначена; applied0001–0010 immutable.

### 0.2. Что должен получить владелец

Отдельный запрос участия владельца с понятной причиной, ответственным, сохранённым
контекстом и исходом. Владелец позже увидит его в очереди Console и даст решение;
повторный запрос не размножает ожидания, устаревший ответ не применяется к другому
состоянию. Сроки и внутренние напоминания переживают restart.

Здесь проектируется **минимальный backend/API** для M3-A09 и будущей owner-wait
части M3-A10. Сейчас нет UI реализации, нового AI/LLM, ApprovalRequest или
полного Notification Engine. CONTROL UI уже работает и его API не переоткрывается.

### 0.3. Источники и неизменные решения

Сначала AGENTS, IMPL-001, Spec §§1.7/5.10–5.14/14.11/16/18.5–18.8/24.7;
ADR-023–026/121–128/139/197–198/267; MVP GJ-G/GJ-J, Roadmap M3,
Implementation Plan M3.1/M3.2 и OPEN-082/083/085. Затем M3_CONTRACT §§8/9/12/13,
этот handoff §§4.5/5 и actual conversations/control/guards/turns,
messaging Jobs/worker/scheduler, tenancy/auth, Audit, migrations0008–0010,
OpenAPI и owner read/command patterns. Canon/original snapshots не редактировать.

Принято:
- Escalation — отдельный lifecycle ожидания, не Conversation.control_mode.
  Resolve/cancel/expiry не снимают HUMAN и не выполняют неявный Resume.
- Relevant context/generation и current authority проверяются в короткой
  serialized/CAS транзакции; прежний receipt не выдаётся за current state.
  Новая несовместимая информация/withdrawal отменяет устаревшее ожидание;
  поздний owner answer не применяется к другой версии/Client.
- Workspace и canonical Client/Conversation/Turn binding обязательны.
  LLM не назначает авторитетные business facts/actor и не выполняет решение.
- Durable Jobs используют PostgreSQL. Internal reminders ограничены,
  дедуплицированы и видимы через будущий Console API; клиентских follow-ups,
  внешних owner notifications и нового notification framework в этом срезе нет.
- OPEN-082 о реальных сроках/quiet hours/контактах мастера остаётся OPEN.
  Для LOCAL/TEST допустима явно ограниченная synthetic policy, без обещаний
  клиенту или выдуманных production сроков. OPEN-083 safe default сохранён.
- Принятый M3_CONTRACT§13.5/actual0010: `manual_delivery` flags считают
  **только SEND_MANUAL_TEXT**. Все OUTBOUND kinds/statuses видны в истории.
  Неточная фраза прежней выдачи C0 исправлена ниже согласно PR30 receipt.

### 0.4. Содержание одного минимального §14

C3 предлагает один конкретный рекомендуемый вариант, отмечая ещё не принятые
реализационные решения как **PROPOSED/OPEN**, а не выдумывая LOCKED-ответы.

1. **Исполняемое происхождение запроса.** Какой существующий callable producer/
   service/worker создаёт Escalation и как его authority/relevance доказываются.
   В M3 ещё нет Agent M4: отделить реальный reusable domain path от конечного
   synthetic LOCAL/TEST trigger. Не предлагать unused service, публичный
   произвольный worker principal или создание canonical rows migrator-ом
   вместо тестирования runtime. Существующий GUARDS TEST consumer не менять
   молча; необходимую совместимую дельту назвать явно.
2. **Модель и state transitions.** Минимальные reason/assignee/context fingerprint,
   request/version/dedupe identity, статусы и create/resolve/cancel/expire.
   Определить meaning owner answer и сохранённого outcome: ответ сам не является
   отправкой клиенту, Approval денежного действия или переключением в AI.
   Описать effect на waiting projection, context/control counters и будущую
   работу; не возрождать stale Turn/output. Назвать фактическую cancellation
   boundary для текущих material events, не реализуя native/edit/delete раньше
   отдельного provenance gate.
3. **Сроки и Jobs.** Сохраняемые due/expiry и bounded reminder policy, deterministic
   test clock, reclaim/restart/dedupe и terminal cleanup. Resolve против expiry,
   cancel против reminder и stale claim должны иметь однозначный исход;
   проверять trusted time/relevance при выполнении команды, даже если scheduler
   ещё не обработал срок. Не busy-loop и не sleeps как гарантия correctness.
4. **Owner API для следующего C5.** Минимальные list/detail/actions, если нужны:
   точные routes/DTO/errors/permission, expected version/Client/context,
   cookie/Origin/CSRF, exact key/body replay, conflict/stale, bounded pagination.
   Разделить receipt и current projection. Обосновать read/resolve/cancel при
   недоступном канале/billing; не перенести send permission на локальный owner
   decision автоматически. Не ломать действующие CONTROL/manual/auth routes.
5. **DB/transaction design.** Только необходимые таблицы/constraints/FK/RLS,
   owner/runtime capabilities, Audit и receipt binding. Объяснить минимальную
   новую durable state и возможность reuse Jobs без generic ledger. Указать
   общий lock order с CONTROL/manual/GUARDS, атомарность, replay после ACK loss,
   concurrent duplicate/resolve/stale/expiry и независимость conversations.
   Схема/число таблиц/SQL signatures остаются proposal для C2; не писать DDL.
6. **Совместимость и компактная реализация.** Proposed переход от0010 к новой
   revision, clean/repeat/populated/refusal/rollback и exact source/schema gates.
   Сохранить прежние receipts/data/UNKNOWN и9 CI jobs/budgets/pins.
   Дать конкретный будущий allowlist с причиной для каждого path, без разрешения
   менять их сейчас. Если объём действительно велик, предложить минимальное
   деление внутри того же M3.2 по работающему результату.
7. **Достаточные проверки.** Таблица contract→service/API/actual PG/worker
   assertions для M3-A09: создание/dedupe, resolve/cancel/expire/late answer,
   context/control/owner changes, same-key ACK loss, две конкурирующие команды,
   restart/reminder once, tenant/Client isolation и compatibility. Отдельно
   предусмотреть future C5 owner-wait UI; mocks не называть PG evidence.
   Не повторять неизменные M2/CONTROL suites и не вводить новую security program.

Если канон не отвечает на прикладной выбор, сформулировать конкретный OPEN-вопрос,
влияние и рекомендуемый MVP ответ C0. Не закрывать OPEN-082/083/085 целиком
для удобства реализации и не изменять принятую архитектуру по умолчанию.

### 0.5. Проверки, возврат и следующий gate

Сейчас проверяются source binding, один разрешённый implementation path,
побайтное сохранение всего старого M3_CONTRACT и preparation docs,
`git diff --check`, внутреннее соответствие §14 actual source/канону.
Продуктовые PG/browser/Docker suites заново для одного proposal локально не нужны.
После содержательного дополнения открыть **один Draft PR в main**; штатный CI
сохранить, не запускать отдельный PR/CI на одной подготовке и не rerun зелёный
SHA ради статистики. Документационный CI не доказывает будущую Escalation.

Один C3 receipt в этом PR: head/parent/tree/base/start, path/numstat/prefix proof,
основные предложения и конкретные OPEN решения, future implementation allowlist,
фактические проверки/CI run/status, ограничения и следующий шаг.
Статус результата REVIEW либо конкретный BLOCKED; затем HOLD exact head.

C0 проведёт intake; C1 проверит новый API/owner semantics, C2 — минимальную схему,
транзакции и migration proposal. Их review ограничен §14 и используемыми зависимостями.
C6 подключается только при конкретной дельте существующего migration/CI controller,
без отдельного общего аудита. После принятых решений C0 назначит revision/exact paths
и выдаст реализацию **в том же PR**. C5 ждёт принятого backend/API SHA; C8 —
готового implementation candidate. Сейчас поручение получает только C3.

Не менять backend/API/DDL/frontend/workflows/runners/deps/canon/реестр.
VM/live Telegram/рабочие DB-S3/deploy/merge и M4 вне выдачи.
M3-A08 native/provenance и весь M3 остаются NOT VERIFIED/IN_PROGRESS по своему scope.
IMPL-05 OPEN/fix DEFERRED и CI optimization DEFERRED до завершения M3 сохранены.

</details>

<details>
<summary>Завершённая выдача CONSOLE-CONTROL; не активное поручение</summary>

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
   manual_delivery.has_dispatching/has_unknown. По принятому M3_CONTRACT§13.5
   actual0010 read фильтрует kind=SEND_MANUAL_TEXT; статусы всех OUTBOUND видны
   в истории. Формулировка C0 уточнена при post-merge приёмке PR30.
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

</details>

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

</details>
