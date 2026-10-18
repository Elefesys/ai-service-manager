# M3 — управление разговором и участие владельца

Дата подготовки: 2026-10-09. Ответственный за выдачу и приёмку: C0.
Статусы задач — только [TASK_REGISTER](../TASK_REGISTER.md).
План принят C0 и слит в PR25; runtime/DDL M3 допускаются отдельными выдачами C0.
Он детализирует M3.1/M3.2 из исходного плана, не добавляет новый milestone.

## 0. Текущая выдача C0 — независимая проверка NATIVE-CONTEXT DB-R1 / 2026-10-18 UTC

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
