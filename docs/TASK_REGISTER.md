# AI Service Manager — единый task register

Ответственный: C0. Канон: v0.28; стек: `docs/decisions/IMPL-001-stack.md`. Это единственный реестр исполнения. LOCKED/OPEN/DEFERRED/REVISED относятся к архитектуре; состояния задач: TODO → IN_PROGRESS → REVIEW → INTEGRATED → VERIFIED, BLOCKED требует причины.

## Текущий статус — M2.4-CONSOLE принята C0/C8; ожидает merge / 2026-09-22

**M2.4-CONSOLE и M2.4 остаются REVIEW до пользовательского merge и отдельного
push/main CI. C0 и независимый scoped C8 приняли исправленный LOCAL/TEST code/UI.
Весь M2 IN_PROGRESS; live A09/A11 BLOCKED внешними runtime/DNS/TLS. M3 не выдан.**

Единственный PR — [#21](https://github.com/Elefesys/ai-service-manager/pull/21),
ветка **c5/m2-4-console**. Accepted base/main
**ffc437f125aa6af4dcf1c61a035a0d5df517e062** и первый coordination
**76d44a7e0559f470b3de07c97a4b61581e7e00a8** сохранены. M1 и принятые M2.1–M2.3
LOCAL/TEST receipts не отменены.

C0 проверил C5 head **1323648d4cd889bc35dcfcf9291fb918412c8d86**, его213 Git blobs/modes,
ordered merge parents/tree и оба job logs CI35695869235. Реальный независимый C8
проверил recovery/isolation, strict consumer/private images и TEST harness/evidence.
Три P2 замечания исправлены в этом же PR; targeted C8 **PASS / CLOSED**:

- **C8-M2.4-01:** pagination во время pending POST больше не поглощает fresh GET
  после202; только чтение, начатое с подтверждённым intent, завершает recovery.
- **C8-M2.4-02:** live OWNER denial из любой owner-панели скрывает обе панели и
  private grant до session recovery; frozen body/key и late-response guards сохранены.
- **C8-M2.4-03:** private image browser checks используют безопасные boolean/number
  probes; signed URL не включается в failure diagnostics, visibility/width/headers
  assertions сохранены.

Исправленный implementation head **842b9ee3300fcea06fbb1394c13a01faae21493b**, parent
**1323648d4cd889bc35dcfcf9291fb918412c8d86**, tree
**f1dd4f5c9442febd192f3a81061634117aa3d7fe**.
[Полный CI35703839157](https://github.com/Elefesys/ai-service-manager/actions/runs/35703839157):
SUCCESS:492 unit,390 PostgreSQL/S3,111 frontend,27 browser; оба штатных scripts и clean-source gates, canonical/migrations/contracts/reproducibility/smoke PASS. Tested merge **17713ebd43c69273f12ee2961fed8c1d8dd79c6b**,
parents accepted base + implementation, equal tree. Локально typecheck и111 frontend
PASS; C8 независимо выполнил11 targeted component и7 privacy failure-path probes.
PG/S3/browser execution — GitHub runner; ZIP bytes отдельно не проверены.

C0 явно разрешил дополнительный **frontend/src/BillingPanel.tsx** только для callback
общего OWNER denial. Всего24 changed paths относительно base. Backend/API, migrations
0001–0007, grants/R4/tenancy/OpenAPI/base Compose/workflows/locks/pins/canonical sources
не изменены. Прежние15 M1 browser journeys и их исходные файлы сохранены.

Этот единый acceptance update согласует register, active [M2_HANDOFF](tasks/M2_HANDOFF.md)
и [M2_CONTRACT §11.9](tasks/M2_CONTRACT.md#119-c0c8--ограниченная-коррекция-и-приёмка).
**Окончательный docs head/tree/tested SHA и его полный CI указываются в верхнем PR
receipt после исполнения.** Коммит только ради записи SHA этого документа не нужен.
Ready/merge допустимы после SUCCESS именно последнего head; C0 самостоятельно не сливает.

Осталось: пользователь делает обычный merge commit PR21; C0 проверяет actual merge/main
CI и фиксирует только code/UI LOCAL/TEST. Затем разрешённый live A09/A11 по готовому
runbook: Client text+photo → Owner Console/private image → manual reply → Client receipt.
Bot/Owner/Client и секреты готовы, ещё нужны Linux/Docker host, два DNS имени и TLS.
Секреты вводятся непосредственно в private runtime env/secret store; расходов/внешних
sends не было. CONTROLLED и SENT не доказывают live Client receipt и завершение M2.

## Задачи — актуальная таблица

| ID | Цель | Зависимости | Ведущий | Статус | Evidence / результат | Следующий шаг |
|---|---|---|---|---|---|---|
| M0.ACCESS | Repository и доступ | — | C0 | VERIFIED | PR #1/#2 merged, доступ подтверждён | Проверять refs перед каждой задачей |
| M0.BASELINE | Spec/ADR/baseline/plan | ACCESS | C0 | VERIFIED | 11 канонических оригиналов и IMPL-001 | Не менять канон молча |
| M0.SOURCE | Точный импорт | BASELINE | C0 | VERIFIED | 11/11 SHA-256 и byte comparison | CI проверяет SOURCE_MANIFEST |
| M0.STACK | Зафиксированный стек | BASELINE | C0 | VERIFIED | IMPL-001, locks/digests и CI | Только обоснованные reviewed изменения |
| M0.BACKEND | API/Worker/Scheduler shell | STACK | C0 | VERIFIED | Types/health/env/shutdown tests | Auth — M1.2 |
| M0.FRONTEND | Console/Ops shells | STACK | C0 | VERIFIED | 3 frontend tests/build/reproducibility | Login UI — C5 в M1.2 |
| M0.DB | PostgreSQL/vector/roles/migrations | STACK | C0 | VERIFIED | Real PostgreSQL и migration cycles | 0002 уже реализована в M1.1 |
| M0.LOCAL | Docker/local smoke | BACKEND/FRONTEND/DB/LOCK | C0 | VERIFIED | GitHub Linux/amd64 runner | Пользовательский ПК не проверен |
| M0.TEST | Существенные PostgreSQL tests | DB | C0 | VERIFIED | 7 первоначальных DB cases сохранены | Tenant/auth regression развивается |
| M0.LOCK | Locks/digests/build repeatability | STACK | C0 | VERIFIED | uv/npm locks, image digests, wheel/assets | Bootstrap при обычном checkout не нужен |
| M0.CI | Общий pipeline | LOCAL/LOCK | C0 | VERIFIED | Main runs 34970531911 и 34972872410 | Read-only CI, source/drift gates |
| M0.FIXTURES | Synthetic A–D | STACK | C0 | VERIFIED | UUID/money/modes/environment guards | Не production defaults |
| M0.HANDOFF | Правила, реестр и очередь | BASELINE/STACK | C0 | VERIFIED | AGENTS и M1_HANDOFF | Передача по точному SHA |
| M0.ACCEPT | Приёмка foundation | M0 gates | C0 | VERIFIED | C0 review + exact import + main CI | История M0 сохранена ниже |
| M1.1 | Tenant schema/context/RLS | VERIFIED M0 | C2; C0/C8 review | VERIFIED | PR #3 merged; C8 PASS; main run 35015308300; 89 tests PASS | Auth consumer C1; не весь M1 |
| M1.2 | Auth/session/membership/login UI | Интегрированный M1.1; принятый backend API | C1+C5; C0/C8 review | VERIFIED | PR #8 MERGED; actual main `28c289ce6f77e33676cfa416585cc0e20c0be4e3`; push/main 35368244266 SUCCESS, 246 tests; UI-01/02/04/05 CLOSED | Полная приёмка: docs/reviews/M1_2_C0_ACCEPTANCE.md; не production |
| M1.3 | Local Plan/Subscription/Entitlements/Audit | M1.1 и принятая M1.2 | C1 backend; C2 DB; C5 UI; C0/C8 review | VERIFIED | DB/API/UI приняты; PR #15 + документы PR #16 в main; push/main 35513585580 SUCCESS, 415 cases; итоговый receipt | Закрыто в R4 LOCAL/TEST scope; сохранять принятые механизмы |
| M2.1 | Normalized channel events и durable Inbox/Outbox/Jobs | VERIFIED M1; принятый контракт M2.1 | C3+C2; C0/C8 review | VERIFIED | PR #18 MERGED; actual main d3c849d4792f7af60f43eea0f0551659ee3cee5d; push/main 35596593891 SUCCESS; C8 PASS | Сохранять принятый kernel при additive Telegram extension |
| M2.1-KERNEL | Controlled event → Message → owner command → durable send/recovery | M2_CONTRACT §§1–8 | C3; C2 DB/migration | VERIFIED | 0005→0004; post-merge C0 acceptance; 259 PostgreSQL и 15 прежних browser PASS | Сохранять SEND UNKNOWN/worker/RLS/Audit при расширениях |
| M2.2 | Private ObjectStorage/FileObject и авторизация изображений | Принятый actual main M2.1 | C6+C3; C2 DB/migration; C0/C8 review | VERIFIED | PR #19 MERGED; actual main a321bdd58856fb41bccb5749b4212349832e623c; push/main 35611528733 SUCCESS; C8 PASS | Принято controlled LOCAL/TEST; настоящий provider/API — M2.3 |
| M2.2-PRIVATE-IMAGES | Image reference → private file → owner signed GET | M2_CONTRACT §9 | C6; C3 media/fix; C2 migration | VERIFIED | 0006→0005; 305 PostgreSQL/S3; privacy/recovery/late-PUT/WebP guards; C8-M2.2-01 CLOSED; post-merge receipt | Сохранить private grant/fencing/cleanup; не объявлять весь M2 готовым |
| M2.3 | Telegram adapter, test connection, capabilities, UNKNOWN и owner API | VERIFIED M2.1/M2.2 | C3; C1/C2/C6; C0/C8 | INTEGRATED | PR #20 merged, main ffc437f125aa6af4dcf1c61a035a0d5df517e062; push/main 35649907678 SUCCESS; code/API VERIFIED LOCAL/TEST | Actual Telegram A09/A11 BLOCKED runtime/DNS/TLS; UI C5 M2.4 |
| M2.3-TELEGRAM-API | Official Telegram → durable kernel/private images → five owner API routes | M2_CONTRACT §10 | C3; C2/C1/C6; C0/C8 | VERIFIED | Accepted main ffc437f125aa6af4dcf1c61a035a0d5df517e062; code/API LOCAL/TEST, C8-M2.3-01 CLOSED; actual main CI SUCCESS | Сохранять API/0007/time guards/UNKNOWN; live evidence отдельно |
| M2.4 | Console Inbox, manual reply и E2E | Интегрированный API M2.3 + main CI | C5; C3/C6; C0/C8 | REVIEW | PR21 code/UI принято C0; независимый C8 PASS, C8-M2.4-01/02/03 CLOSED; implementation CI35703839157 и final receipt в PR | User merge → actual main CI; live A09/A11 отдельно |
| M2.4-CONSOLE | Owner panel + private image + exact manual intention/recovery + browser | Base ffc437f125aa6af4dcf1c61a035a0d5df517e062; M2_CONTRACT §§10–11 | C5; C3/C6 TEST harness; C0 fix; C8 review | REVIEW | Исправленный head842b9ee3300fcea06fbb1394c13a01faae21493b; C0/C8 acceptance,111 frontend,27 browser в CI receipt; backend/0001–0007 сохранены | SUCCESS final head → пользовательский merge; VERIFIED code/UI только после main CI |

Таблица M0 перечисляет фактического исполнителя C0, а не подразумевает отдельно запущенных C1–C8. Review M0 был C0 self/second-pass; M1.1 имеет отдельные отчёты C8. Назначения областей остаются в AGENTS/Implementation Plan.

## История — прежние решения и evidence

Всё ниже — записи прежних snapshots. Их статусы и команды не переопределяют
текущий блок, таблицу выше и M2_HANDOFF. Не выполнять старые поручения повторно.

## История — передача C5 M2.4-CONSOLE REVIEW в Draft PR #21 / 2026-09-22

**M1.1–M1.3 и принятый M2.1–M2.3 code/API сохраняют VERIFIED LOCAL/TEST receipts.
M2.4-CONSOLE и M2.4 REVIEW; весь M2 IN_PROGRESS. Live A09/A11 BLOCKED внешними
runtime/DNS/TLS. M3 не выдан. C5 не объявляет UI или M2 VERIFIED.**

Accepted main/base **ffc437f125aa6af4dcf1c61a035a0d5df517e062**, tree
**0ed75735d6c9d9b7d35fac13dbfb6cc3b6ede814**: PR #20 merged; отдельный
[push/main CI35649907678](https://github.com/Elefesys/ai-service-manager/actions/runs/35649907678)
SUCCESS, C8-M2.3-01 CLOSED. Его parents, scoped acceptance и полная прежняя история
сохранены ниже. M2.4 продолжает тот же [Draft/open/not merged PR #21](https://github.com/Elefesys/ai-service-manager/pull/21),
ветка **c5/m2-4-console**. Coordination **76d44a7e0559f470b3de07c97a4b61581e7e00a8**
сохранён как первый commit после base; tree **f416c7f8a3230d7b4bb5b8edfa9ec53cc6ff8139**.

C5 реализовал одну Console messaging panel/strict consumer; C3 — finite TEST
provisioning/runtime Worker/FetchTransfer/counters, C6 — private MinIO Compose/guards
и existing live runbook. Shared edits интегрированы последовательно. OWNER role,
exact frozen intention,202/GET-only recovery, UNKNOWN/no-resend, private grants,
late-response isolation и прежние M1 mechanisms покрыты component и real browser
API/PostgreSQL/S3 journeys. Backend/API/0001–0007/grants/OpenAPI/base Compose/workflows/
dependencies/canonical sources не менялись; новых endpoints нет.

Implementation **cd2cce43acf2556d49e865e198a717acdc67dc96**, parent coordination,
tree **de2b4b708791f3c55f815d947b00fa13e4888a64**;
[CI35694903440, attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/35694903440)
SUCCESS: **492 unit,390 PostgreSQL/S3,107 frontend,27 browser**, оба штатных scripts,
source gates, migrations/contracts/reproducibility/smoke PASS. Оба jobs реально
checkout **05344240fffd5d67340db1db292fd3fb00fb3f29**, parents accepted base +
implementation, equal tree. Это implementation evidence; final docs update имеет
собственный head/tree/tested SHA и повторный полный CI в итоговом PR receipt.
SHA-only documentary chain не создаётся. Локального Docker нет; real evidence —
GitHub runner. ZIP byte verification не заявляется.

Единственный active return — [M2_HANDOFF](tasks/M2_HANDOFF.md), mapping assertions
к прежним A01–A12 и причины test/fixture changes там же; consumer semantics сохранены
в [M2_CONTRACT §11](tasks/M2_CONTRACT.md#11-m24-console--текущий-ограниченный-uibrowser-контракт).
C1 ранее выполнил CONTRACT PASS. C0 и независимый scoped C8 теперь проверяют новый UI;
соавторская проверка C3/C6 не заменяет C8. Затем user merge и отдельный actual main CI.

Конкретных implementation blockers вне scope нет. Bot/accounts/secrets готовы,
но host/DNS/TLS отсутствуют: только live A09/A11 BLOCKED. CONTROLLED не Telegram,
SENT не Client receipt. Runbook дополнен сценарием Client text+photo→Owner Console→
manual reply→Client receipt; внешние sends/расходы не выполнялись. Весь M2 остаётся
IN_PROGRESS до полной приёмки и фактического live A11.

## История — M2.3 integrated и первоначальная выдача M2.4 / 2026-09-21

**M1.1–M1.3, M2.1/M2.2 VERIFIED LOCAL/TEST. M2.3 code/API INTEGRATED / VERIFIED
в LOCAL/TEST. Живое подключение A09/A11 BLOCKED: внешнее runtime/DNS/TLS.
M2.4 IN_PROGRESS — подготовлена одна задача C5, UI ещё не реализован.
Весь M2 IN_PROGRESS; M3 и последующие этапы не выданы.**

[PR #20](https://github.com/Elefesys/ai-service-manager/pull/20) фактически merged.
Accepted main/base **`ffc437f125aa6af4dcf1c61a035a0d5df517e062`**, tree
**`0ed75735d6c9d9b7d35fac13dbfb6cc3b6ede814`**. Merge parents: прежний base
`a321bdd58856fb41bccb5749b4212349832e623c` + принятый PR head
`2aece2df399a722ba6d978977527c3b92eb0adf6`; tree совпадает с final PR tree.
[Отдельный push/main CI 35649907678](https://github.com/Elefesys/ai-service-manager/actions/runs/35649907678)
**SUCCESS**:421 unit,390 real PostgreSQL/S3,60 frontend,15 прежних browser, оба
scripts/clean-source gates PASS. Оба checkout logs проверены на actual merge SHA.
C8-M2.3-01 CLOSED: независимые DB/API targeted PASS; transport scoped PASS.
Подробности review и assertions сохранены в историческом receipt M2.3.

Единственное текущее поручение — [M2_HANDOFF](tasks/M2_HANDOFF.md), ID
**M2.4-CONSOLE**, ведущий C5; C3 TEST worker/provider harness, C6 TEST Compose/runbook,
C1 consumer compatibility. Ветка **c5/m2-4-console** → main, один подготовленный
Draft PR от exact base выше; номер/start head/tree/CI находятся в PR receipt и
сообщении C0. Первый coordination commit сохранить; отдельный docs merge не нужен.
Принятый consumer scope — [M2_CONTRACT §11](tasks/M2_CONTRACT.md#11-m24-console--текущий-ограниченный-uibrowser-контракт).

Нужны одна панель переписки, private image, manual text/exact recovery, состояния
connection/delivery и реальные API/PG/S3 browser journeys. Ручное обновление достаточно.
Backend wire/schema, применённые0001–0007, frozen M1/R4 и kernel не перепроектируются;
необходимые browser-only scripts/Compose/guards заранее включены в разрешённые paths.
C1 read-only consumer CONTRACT PASS выполнен; backend-дельта не требуется.
Это выдача задачи, не evidence выполненного UI и не независимый C8 нового среза.

Bot/accounts/secrets пользователя готовы; внешний host/DNS/TLS пока отсутствует.
Это блокирует только live A09/A11. M2 завершается после четырёх принятых частей,
успешного actual main CI и реального Client text+photo→Console→manual reply→Client.
C5 возвращает REVIEW; C0/C8 приёмка, пользовательский merge и отдельный main CI впереди.


## История — приёмка M2.3 до merge, snapshot 2026-09-21

### Прежний статус — M2.3 code/API принят C0/C8 до merge / 2026-09-21

**M1.1–M1.3, M2.1 и M2.2 VERIFIED в принятых LOCAL/TEST границах.
M2.3 REVIEW: code/API прошёл C0 и независимый scoped C8 после ограниченного
исправления C8-M2.3-01. Merge и отдельный actual main CI ещё требуются.
Live Telegram BLOCKED: внешнее runtime/DNS/TLS. M2.4 TODO; весь M2 IN_PROGRESS.**

Единственные текущие инструкции — [M2_HANDOFF](tasks/M2_HANDOFF.md); технические
решения — [M2_CONTRACT §10](tasks/M2_CONTRACT.md#10-m23-telegram-api--принято-c0c2c3c1-2026-09-21).
Принятый base/main **`a321bdd58856fb41bccb5749b4212349832e623c`**; ветка
**`c3/m2-3-telegram-api`**, тот же [PR #20](https://github.com/Elefesys/ai-service-manager/pull/20).
Coordination **`5347e3de498752be2834573eadfb39d59dc51bcb`** сохранён.

C0 сверил все52 paths с разрешённым scope,204 source blobs/modes, канон и CI.
Сохранены 0001–0006, M1/R4/tenancy/auth wire contracts, прежние OpenAPI paths/schemas,
private validation/fencing/cleanup, frontend, workflows и source gates. Httpx0.28.1
перенесён в runtime без обновления package versions/hashes. Реализованы только
принятый Telegram business adapter, пять owner routes,0007 и TEST setup/runbook.

Первоначальный implementation head439eb3228a681dd1558ab98ebe232d4a266d9874 и
[CI35632000530](https://github.com/Elefesys/ai-service-manager/actions/runs/35632000530)
SUCCESS не покрывали истечение temporal permission во время billing lock wait.
Независимые C8 DB/API нашли один P2 blocker **C8-M2.3-01**; transport/webhook/media/setup
получил scoped PASS. C2 исправил только0007 и добавил6 PostgreSQL barrier cases.

Исправление **`0ffd9e2146fe5fda1db22152b6feaa1737fc9151`**, tree
`90079c2c8874b6456b1710aef2538467513f018a`, прошло
[CI35647402496](https://github.com/Elefesys/ai-service-manager/actions/runs/35647402496)
**SUCCESS**:421 unit,390 real PostgreSQL/S3,60 frontend,15 прежних browser;
оба scripts/source gates и штатные проверки PASS. **Targeted C8-M2.3-01 PASS,
blocker CLOSED** после source review и runner evidence. Ранние отказы, replay,
structural precedence, R4 snapshot, lock_timeout2s и lease30s сохранены.
Подробные assertions и границы review — в активном handoff.

Это единое обновление документов приёмки. Его собственные final head/tree/tested SHA
и итоговый CI находятся в PR receipt; дополнительный SHA-only commit не нужен.
C0 снимает Draft только после SUCCESS обоих checks именно final head. Пользователь
выполняет обычный merge commit; затем C0 проверяет actual merge/main CI и выдаёт
одну задачу C5 M2.4 от принятой версии. До этого C5 не стартует.

Принят **code/API LOCAL/TEST**, а не проверка пользовательского Telegram подключения.
Live getMe/getBusinessConnection/getWebhookInfo, права Owner/Client, HTTPS/private
signed GET и получение ответа Client ещё не подтверждены. Подготовленные bot/accounts/
secrets остаются у пользователя; внешних отправок и платной инфраструктуры не было.
Весь M2 требует реального Client text+photo→Console→manual reply→Client A11.


## История — первоначальная передача M2.3 от C3 в REVIEW / 2026-09-21

**M1.1–M1.3, M2.1 и M2.2 VERIFIED в принятых LOCAL/TEST границах.
M2.3 REVIEW: реализация Telegram/owner API передана в Draft PR #20; приёмка C0
и независимый scoped C8 ещё впереди. M2.4 TODO; весь M2 IN_PROGRESS.** Единственные текущие инструкции —
[M2_HANDOFF](tasks/M2_HANDOFF.md), единый технический контракт —
[M2_CONTRACT §10](tasks/M2_CONTRACT.md#10-m23-telegram-api--принято-c0c2c3c1-2026-09-21).
M1/R4 и закрытые kernel/storage срезы не переоткрывать.

[PR #19](https://github.com/Elefesys/ai-service-manager/pull/19) MERGED пользователем.
C0 подтвердил actual merge/main **`a321bdd58856fb41bccb5749b4212349832e623c`**,
parents `d3c849d4792f7af60f43eea0f0551659ee3cee5d` + принятый final head
`1e460ea58c7d9ceb48152cdd49a651b66ad625b7`; tree
**`8221b88b481378d49a185e29e95e3d20ea119c0c`** совпадает с accepted final tree.
[Отдельный push/main CI 35611528733](https://github.com/Elefesys/ai-service-manager/actions/runs/35611528733)
**SUCCESS** на actual merge: 288 unit, **305 real PostgreSQL/S3**, 60 frontend,
15 прежних M1 browser; оба scripts/clean-source gates, canonical import, migrations,
contracts/reproducibility/smoke PASS. Checkout SHA в обоих jobs совпадает с merge.
Artifact digest указан по GitHub metadata; побайтная проверка ZIP не заявляется.
Независимый scoped C8 и targeted closure **C8-M2.2-01 PASS** относятся к тому же коду.
Приняты только private images и внутренний owner grant, применимые A07/A08 и
A02/A04/A06/A12; настоящий Telegram/API/UI и полный A11 ещё не приняты.

Текущее единственное поручение — **M2.3-TELEGRAM-API**, ведущий **C3**,
C2 — DB/0007, C1 — API/product policy, C6 — ограниченная TEST setup/runbook помощь.
Accepted implementation base — actual main выше. Ветка
**`c3/m2-3-telegram-api`** → main; тот же [Draft PR #20](https://github.com/Elefesys/ai-service-manager/pull/20).
Первый coordination commit `5347e3de498752be2834573eadfb39d59dc51bcb` сохранён.
Final head/tree, tested virtual merge/parents, CI/gates и изменённые paths публикуются
в PR receipt без цепочки документальных коммитов только ради SHA.

C0 прочитал код и канон; C2/C3 и C1 реально выполнили read-only CONTRACT review §10.
Согласованы: verified operator binding, durable Telegram receipt/Inbox/ACK, opaque
и numeric IDs, явные ignored outcomes, photo-only, observed rights generation/version
CAS, 24h conservative window, 429 delay и UNKNOWN/no-resend. Пять owner routes,
строгие DTO/cursor/auth/idempotency, отдельный messaging.manual_send BOOLEAN/ESSENTIAL
через настоящий EntitlementService; старые TEST catalog/keys/GET billing сохранены.
Новый test_messaging plan используется только явно для fresh LOCAL/TEST Workspace,
без перепривязки прежних subscriptions. **0007_telegram_api.py, 0007→0006** назначена
C0/C2 и реализована; применённые 0001–0006 не изменены. Это не C8 review реализации.

Реализация включает durable verified webhook, trusted binding/CAS, Telegram TEXT/photo,
private S3, ровно пять owner routes и fresh-only product provisioning. Фактическая
матрица tests/assertions находится в активном handoff; точные runs — в PR receipt.
Следующий gate — C0 + независимый scoped C8 по новым Telegram/API risks →
ручной merge пользователя → actual main CI. C5 не стартует
до принятого интегрированного API. Нет новых AI/M3/цен/платежей или платной infra.
Подготовленные пользователем bot/Owner/Client/secrets учтены; runtime injection,
HTTPS/browser-reachable private S3, binding/rights и живой Telegram ещё требуют
проверки. External access блокирует только соответствующий live check; весь M2
не VERIFIED до настоящего Console A11.


## История — M2.2 pre-merge приёмка C0 / 2026-09-21

**M1.1–M1.3 и M2.1 VERIFIED в принятых LOCAL/TEST границах. M2.2 REVIEW;
не INTEGRATED/VERIFIED. M2.3/M2.4 TODO; весь M2 IN_PROGRESS.** Единственные
активные инструкции — [M2_HANDOFF](tasks/M2_HANDOFF.md), технические решения —
[M2_CONTRACT](tasks/M2_CONTRACT.md). M1/R4 и закрытое ядро M2.1 не переоткрываются.

Принятый actual main/base — **`d3c849d4792f7af60f43eea0f0551659ee3cee5d`**,
merge PR #18; tree `f12aa90a3c3fb7fdfda84290315a3fd820816b4b`.
[Push/main CI 35596593891](https://github.com/Elefesys/ai-service-manager/actions/runs/35596593891)
SUCCESS: 192 non-integration, 259 PostgreSQL, 60 frontend, 15 прежних M1 browser;
оба clean-source gates и штатные проверки PASS. Это принятый M2.1 controlled kernel.

Продолжен [PR #19](https://github.com/Elefesys/ai-service-manager/pull/19), ветка
**`c6/m2-2-private-images`**; coordination commit
`c4ad360e482f47a30e6f0756a13e6ce1cf68def4` сохранён. C0 проверил все 37 changed paths,
принятый §9 и сохранность старых механизмов на исходном implementation head
`5d72557a1058906e0040d5f410968f769986f2e8`.
[CI 35605713463](https://github.com/Elefesys/ai-service-manager/actions/runs/35605713463)
SUCCESS: 220 unit, 303 PostgreSQL/S3, 60 frontend, 15 прежних browser; оба scripts,
clean-source gates, migrations/contracts/reproducibility/smoke PASS. Git blobs/tree
и tested virtual merge проверены. ZIP download дал 403: побайтная проверка ZIP
не заявлена. Это исходное evidence, не проверка последующего WebP fix.

Независимый C8 нашёл единственный blocker **C8-M2.2-01 (P2)**: pinned WebP decoder
выделял native canvas внутри Image.open, до проверки размеров. C3 внёс ограниченный
preflight RIFF/VP8/VP8L/VP8X и regression tests в три существующих файла. Прежние
форматы, лимиты, original bytes и полный decode сохранены. Локально Python 3.13.15 /
Pillow 12.3.0: 288 non-integration, Ruff/format/strict mypy PASS. Два новых PostgreSQL
cases должны пройти в обязательном итоговом CI; local unit run их не заменяет.
**Независимый targeted C8-M2.2-01 PASS: blocker закрыт по reviewed source.**
C0 code/scope review PASS; готовность к merge требует итогового полного CI.
Точные assertions и границы review — в активном handoff.

C0 явно принял упрощение §9.4: bounded RAM buffer оригинала вместо temporary disk
file. 10 MiB — лимит input, не всей памяти decoder. Канонические bytes остаются
в private S3; это не уменьшает обязательность WebP preflight. Миграция 0006→0005,
прежние 0001–0005, auth/tenancy/R4, OpenAPI/frontend и старые dependencies/image pins
сохранены. Новых возможностей за пределами private-images scope нет.

Этот согласованный fix/receipt update не записывает свой будущий SHA. Единственный
final receipt в PR #19 содержит точные final head/tree/tested SHA, результат
обязательных checks именно этого head и C8. C0 снимает Draft только после их PASS;
пользователь выполняет обычный merge commit, C0 затем проверяет actual merge и
отдельный push/main CI. Только после этого M2.2 может стать INTEGRATED/VERIFIED
и выдаётся M2.3 от принятого main. Telegram/API/UI и A11 этим срезом не закрываются.


## История — передача M2.2 от C6/C2/C3 до C0 review / 2026-09-21

**M1.1–M1.3 и M2.1 VERIFIED в принятых LOCAL/TEST границах.
M2.2 REVIEW: реализация C6/C2/C3 и execution evidence переданы; C0/C8 ещё не приняли.
M2.3/M2.4 TODO; весь M2 IN_PROGRESS.** Один активный
[M2_HANDOFF](tasks/M2_HANDOFF.md), один инкрементальный
[M2_CONTRACT](tasks/M2_CONTRACT.md). M1_HANDOFF закрыт; M1/R4 не переоткрывать.

[PR #18](https://github.com/Elefesys/ai-service-manager/pull/18) MERGED пользователем.
C0 проверил actual merge/main **`d3c849d4792f7af60f43eea0f0551659ee3cee5d`**,
parents accepted base + `e9d5b748f19bb7d9d67b014947de3fb29ffc481f`,
tree **`f12aa90a3c3fb7fdfda84290315a3fd820816b4b`** = accepted final PR tree.
[Отдельный push/main CI 35596593891](https://github.com/Elefesys/ai-service-manager/actions/runs/35596593891)
**SUCCESS** на actual merge: 192 non-integration, 259 real PostgreSQL, 60 frontend,
15 прежних M1 browser journeys; migration/contracts/reproducibility/smoke и оба
clean-source gates PASS. Artifact digest/source tree/recorded SHA/status проверены.
C0 post-merge receipt в PR #18 и активном handoff; независимый scoped
**C8-M2.1-KERNEL PASS** уже выполнен и относится только к reviewed kernel рискам.
M2.1 **INTEGRATED / VERIFIED** — controlled LOCAL/TEST, не Telegram/storage/API/UI.

Реализовано единственное поручение **M2.2-PRIVATE-IMAGES**, ведущий **C6**, участие
C3 (provider/media/worker) и C2 (миграция/DB). Base — actual main выше; ветка
**`c6/m2-2-private-images`**, [Draft PR #19](https://github.com/Elefesys/ai-service-manager/pull/19).
Первый coordination commit `c4ad360e482f47a30e6f0756a13e6ce1cf68def4` сохранён.
Принятый §9 реализован: atomic FileObject/FETCH и backfill, validated original bytes
в private S3, 60 s live OWNER signed GET, fenced per-attempt keys и durable cleanup.
Миграция **0006_private_images.py, 0006 → 0005**; применённые 0001–0005 неизменны.

[Implementation CI 35604791065](https://github.com/Elefesys/ai-service-manager/actions/runs/35604791065)
**SUCCESS**: 220 backend non-integration, **303 real PostgreSQL/S3**, 60 frontend,
15 прежних M1 browser cases; оба штатных scripts/clean-source gates, migration cycles,
contracts, reproducibility и smoke PASS. Новые 28 unit + 44 PostgreSQL/S3 cases
покрывают A07/A08 и применимые A02/A04/A06/A12; конкретные tests/assertions и объяснения
исправленных двух новых test defects — в активном handoff. Runbook добавлен;
SDK/decoder и два новых storage images pinned, прежние package lock blocks/image
pins сохранены. Final head/tree/tested SHA/CI/artifact — в PR receipt после проверки
итогового documentation/narrow-lock commit, без SHA-only цепочки.

M2.2 **REVIEW**, не INTEGRATED/VERIFIED. Следующий gate — C0 и независимый scoped
C8 review новых private-files/recovery рисков → ручной merge пользователем → actual
main CI. PR остаётся Draft. До этих gates M2.3 не выдавать. Telegram/owner messaging
API — M2.3, UI — M2.4; полное M2 требует A11. Tokens в password manager, binding/
rights, runtime secrets, HTTPS и live smoke ещё не проверены; M2.2 их не использует.


## История — M2.1 pre-merge приёмка C0 / 2026-09-21

**M1.1–M1.3 VERIFIED в принятых LOCAL/TEST границах. M2.1 REVIEW:
C0 PASS, независимый scoped C8 PASS; M2.2–M2.4 TODO.**
Единственный активный handoff — [M2_HANDOFF](tasks/M2_HANDOFF.md), единый
технический контракт — [M2_CONTRACT](tasks/M2_CONTRACT.md). M1_HANDOFF закрыт;
R4/D-01…D-13 и ранее принятые механизмы M1 не переоткрываются.

[PR #18](https://github.com/Elefesys/ai-service-manager/pull/18), ветка
`c3/m2-1-messaging-kernel`, продолжен без переписывания coordination commit
`587531e71380a9a83549cba25c1b5c71c01d223c`. Принятый actual main/base остаётся
**`8e5f125d424c0ce613ed9e0c787392f11a49aeae`**;
[push/main CI 35522542861](https://github.com/Elefesys/ai-service-manager/actions/runs/35522542861)
SUCCESS относится к принятому плану PR #17, не к ещё не слитому kernel.
Миграция `0005 → 0004`; `0001`–`0004` неизменны.

C0 проверил исходный head `2c7ada9b8b9b13956a56bd13e0a4f9f5b4cb33ae` и девять
failures run 35593328892. Четыре запрошенные совместимые правки **согласованы и
применены** в `e772c2a92bb38cb0af869ef77ed36b2df9fcaf59`:
точный current revision в двух provisioning scripts, закрытый inventory десяти
messaging tables/реальные controlled Jobs и одна добавленная receipt table в
существующем TRUNCATE. Assertions, FK, rollback, роли и shutdown guards сохранены.
Это исправление совместимости принятого M2.1; новый функциональный scope не выдан.

[CI 35594839363](https://github.com/Elefesys/ai-service-manager/actions/runs/35594839363)
**SUCCESS** на этом implementation head: 192 non-integration, 259 PostgreSQL,
60 frontend и 15 browser cases PASS; оба штатных scripts и clean-source gates PASS.
C0 сверил head/tested merge/tree, digest и 162 файла архива. Полные migration cycles,
contracts, reproducibility и HTTP smoke пройдены. C8 независимо проверил новые
routing/RLS/worker/atomicity/side-effect риски и четыре совместимые правки;
**C8-M2.1-KERNEL PASS** относится только к этой проверенной области LOCAL/TEST.
Подробные assertions, receipt и границы — в активном handoff.

Этот согласованный update меняет только register/handoff. Финальные head/tree,
tested SHA и CI именно итогового документационного head C0 фиксирует в PR receipt
после исполнения; отдельный коммит ради SHA предыдущего документа не создаётся.
Ready for review и пользовательский merge допустимы только при SUCCESS этого head.
Следующий шаг: пользователь делает обычный merge commit PR #18; C0 проверяет
actual merge и отдельный push/main CI, затем принимает только M2.1 и выдаёт M2.2.
До этого M2.1 не INTEGRATED/VERIFIED; весь M2 не завершён.

Telegram подготовлен со слов пользователя: bot/Business mode и тестовые Owner/Client
accounts, секреты в менеджере паролей. Binding/rights, runtime injection, HTTPS
webhook и живой M2-A11 ещё не проверены; это не блокирует приёмку kernel.
Реальные Telegram/storage, messaging API/UI и M3 этим PR не реализованы.

## История — C3 handoff до согласования C0 / 2026-09-21

**M1.1–M1.3 VERIFIED в принятых LOCAL/TEST границах. M2.1 BLOCKED;
M2.2–M2.4 TODO.** Kernel реализован в Draft PR #18; полные regression gates
требуют узкой scope exception C0, приёмка ещё не выполнена.
Единственный активный handoff — [M2_HANDOFF](tasks/M2_HANDOFF.md), единственный
инкрементальный технический контракт — [M2_CONTRACT](tasks/M2_CONTRACT.md).
M1_HANDOFF закрыт; R4/D-01…D-13 и инварианты M1 не переоткрываются.

[PR #17](https://github.com/Elefesys/ai-service-manager/pull/17) MERGED пользователем.
Принятый actual main/base: **`8e5f125d424c0ce613ed9e0c787392f11a49aeae`**;
tree `3e2a2519c949461856c9f3c5ca1d1ec33a180953` совпадает с reviewed PR tree.
[Отдельный push/main CI 35522542861](https://github.com/Elefesys/ai-service-manager/actions/runs/35522542861)
SUCCESS; actual head/tested SHA, оба jobs/clean-source gates и artifact проверены C0.
Это приёмка интеграции плана, не реализации M2; post-merge receipt записан в PR #17.

Текущее единственное implementation поручение — **M2.1-KERNEL**, ведущий C3 с C2,
ветка `c3/m2-1-messaging-kernel`, подготовленный Draft PR → main.
Продолжить первый coordination commit с контрактом/поручением; номер PR и точный
стартовый head/CI фиксируются в PR metadata и сообщении C0 без SHA-only commits.
Миграция этой задачи: `0005`, predecessor `0004`; `0001`–`0004` неизменны.
C0/C2/C3 согласовали routing/IDs, typed worker admission, Inbox/Outbox/Jobs,
atomicity/UNKNOWN и ограниченную Audit compatibility. C2 подготовил migration/DB
capabilities, C3 — Python kernel/worker/Audit compatibility и tests.
Первый runner [35592297034](https://github.com/Elefesys/ai-service-manager/actions/runs/35592297034):
192 non-integration PASS, 241 PostgreSQL PASS / 10 FAIL, 61 frontend PASS; browser
setup FAIL, оба clean-source gates skipped. Один новый test-context defect исправлен;
9 старых failures требуют scope exception. Итоговый повторный run и exact SHA/tree
в PR receipt; independent C8 ещё не выполнен.

Единственное содержательное дополнение существующих consumers — strict
MESSAGE_SEND_REQUESTED в общем Audit: typed FK/DTO/generated OpenAPI и frontend
parser/label. Оно сохраняет прежние billing events и предотвращает их consumer
failure после новой send-команды. UI переписки/owner messaging API этим не выданы.

Подготовка Telegram со слов пользователя: test bot и Business/Secretary Mode,
Owner/Client accounts готовы; TG_BOT_TOKEN/TG_WEBHOOK_SECRET сохранены в менеджере
паролей. Секреты не получены. Binding/rights, runtime secret injection, HTTPS webhook
и живой сценарий ещё не проверены; M2.1 от этих внешних проверок не зависит.

Scope blocker: два provisioning scripts требуют `0004`; `test_postgres.py`
не допускает новый table inventory/реальные Jobs; `test_m1_3_c0_acceptance.py`
не включает новую receipt→Audit FK в TRUNCATE. Четыре точные совместимые дельты
предложены в активном M2_HANDOFF, но не применены без C0. Guards/CI не ослаблены.

Следующий шаг: C0 разрешает четыре совместимые дельты; C3 завершает оба штатных
scripts/clean-source gates. Затем C0 выполняет приёмку и scoped C8 review новых рисков. M2.2 выдаётся после merge
ядра и отдельного main CI. M2 VERIFIED только после всех четырёх частей и M2-A11.

## Историческая исходная запись подготовки PR #17 / 2026-09-20

Следующий snapshot сохранён как история подготовки; его TODO/запрос review
заменены текущим решением выше. Актуальная таблица находится выше.

**M1.1, M1.2, M1.3 — VERIFIED в принятых границах LOCAL/TEST.**
Сохранено итоговое решение C0: обязательные DB/API/UI работы M1.3 завершены,
production readiness не объявляется. Исторические IN_PROGRESS/BLOCKED и
поручения повторного merge ниже не являются текущими задачами.

[PR #16](https://github.com/Elefesys/ai-service-manager/pull/16) с документами
финальной приёмки уже MERGED. Проверенная исходная точка этого плана:
`38bbb975c189ed445dc4b825ca189f3a80de9814`;
[push/main CI 35513585580](https://github.com/Elefesys/ai-service-manager/actions/runs/35513585580)
SUCCESS, foundation/browser и оба clean-source gate PASS.
415 cases и границы приёмки зафиксированы C0.
Подробности: [итоговый receipt M1.3](reviews/M1_3_UI_C0_ACCEPTANCE.md),
[DB receipt](reviews/M1_3_DB_C0_ACCEPTANCE.md),
[API receipt](reviews/M1_3_API_C0_ACCEPTANCE.md). R4/D-01…D-13 не переоткрываются.

**M2.1–M2.4 — TODO.** По запросу пользователя подготовлен последовательный план,
не реализация и не новая приёмка C0. Единственная точка передачи:
[M2_HANDOFF](tasks/M2_HANDOFF.md). C0 рассматривает этот план, проверяет
актуальный main и выдаёт одну первую задачу M2.1 с конкретным scope/base.
[M1_HANDOFF](tasks/M1_HANDOFF.md) закрыт; активных заданий M1 в нём нет.

Документационный PR не разрешает merge других PR и не подтверждает Telegram,
storage или production. После его интеграции достаточно post-merge проверки
C0 и ссылки на evidence в PR; отдельный SHA-only docs commit не требуется.


## История — UI pre-merge review / 2026-09-20


**DB и backend/API M1.3 — INTEGRATED / VERIFIED. UI-срез — REVIEW: C0 PASS,
targeted C8 PASS для UI-01. M1.3 milestone — IN_PROGRESS. M2 не выдан.**
UI готов к обычному merge commit после SUCCESS именно итогового опубликованного
head. PR #15 пока Draft / open / not merged; интеграция и отдельный main CI впереди.

Принятый base/main `43f22b5e28a93e269eccc25bf73653e47fd01426` и первый coordination
commit `2274667f06ddd72b1a02c57fb555456e948f2c50` сохранены. C0 проверил весь PR,
исходный C5 head `398dc723fed339f8a3e660a114fb231e924c8e31`, CI 35510912219 SUCCESS
(411 cases), ZIP digest/tested SHA/tree/clean-source и 11 canonical originals.

Один конкретный P2 **C8-M1.3-UI-01 CLOSED**: STALE_STATE после auth recovery терял
исходный draft; retry GET после ошибки мог заменить его серверным contact.
Ограниченный fix `7630032d29dc3f79f48a9089b60492b2520384c5`, tree
`203fdd8c7da809a17866df8feb77dbfa90218139`, меняет только BillingPanel и четыре
новых regression cases. Три исходных воспроизведения RED; после fix все четыре
новых cases и 20 focused tests PASS. Независимый targeted C8 PASS относится только
к этой дельте, не ко всей M1.3. Backend/DB/R4/contracts/locks/CI неизменны.
[Полный CI исправления 35511904393](https://github.com/Elefesys/ai-service-manager/actions/runs/35511904393)
SUCCESS: 153 non-integration + 189 PostgreSQL + 58 frontend + 15 browser = 415 cases;
оба clean-source gates PASS. Матрица и пределы evidence —
[UI C0 receipt](reviews/M1_3_UI_C0_ACCEPTANCE.md).

Этот согласованный docs update обновляет реестр, верхний активный handoff,
UI receipt и историческую формулировку API receipt. Итоговые SHA/tree/tested SHA
и CI публикуются в PR и ответе C0 после проверки; следующего SHA-only docs commit нет.

Конечный остаток M1.3:

1. После green final-head CI пользователь в PR #15 выбирает **Ready for review →
   Create a merge commit → Confirm merge**, без squash/rebase/обхода checks.
2. C0 проверяет actual merge commit, его parents/tree и отдельный `push/main` CI.
3. C0 фиксирует общую приёмку M1.3 на этом фактическом evidence. До этого milestone
   IN_PROGRESS. Новых implementation задач при неизменном проверенном snapshot нет.

Упрощения уже приняты и реализованы: существующая Console, один owner panel,
одна contact форма, Audit limit10/Load more, memory-only recovery. R4/D-01…D-13
не отменены. Новые editors, provider billing, Jobs, production и M2 не выданы.
Текущие инструкции — этот блок, актуальная таблица и верхний M1_HANDOFF;
следующие разделы сохраняют историю, а не конкурирующие поручения.

## История — исполнение C5 до C0 review / 2026-09-20


Owner UI/browser implementation подготовлена поверх стартового coordination
`2274667f06ddd72b1a02c57fb555456e948f2c50` и accepted implementation base
`43f22b5e28a93e269eccc25bf73653e47fd01426`. Первый coordination commit сохранён;
ветка `c5/m1-3-owner-ui`, target main, PR Draft / без merge.

Добавлены owner panel, строгий R4 adapter, memory-only frozen contact intention,
ограниченный явный auth/CSRF recovery, Audit limit10 и component/browser journeys.
Команды, поведение, TEST-only fixtures и границы evidence описаны в
[M1_3_UI_RUNBOOK](tasks/M1_3_UI_RUNBOOK.md). Backend/DDL/grants/contracts/dependencies
и прежние browser assertions неизменны. Локально typecheck/build и54frontend
(30прежних +24новых) PASS; Docker отсутствует. Обязательные штатные Docker/realPG/
browser gates выполняются опубликованным GitHub snapshot, не заменяются mocks.
Их final SHA/tree/run evidence возвращается в PR и C0 без SHA-only docs chain.

Это запись исполнения, не приёмка. **UI не VERIFIED; M1.3 IN_PROGRESS.** После
зелёного final-head CI требуются C0 review, ручной merge и отдельный actual main CI.

## История — API принят и выдан owner UI C5 / 2026-09-20

**DB и backend/API M1.3 — INTEGRATED / VERIFIED. M1.3 milestone — IN_PROGRESS.**
Полная M1.2 сохраняет VERIFIED. C0 выдаёт только конечный UI/browser-срез C5;
реализация и приёмка UI M1.3 ещё не выполнены. M2 не выдан.

[PR #14](https://github.com/Elefesys/ai-service-manager/pull/14) MERGED обычным merge
commit **`43f22b5e28a93e269eccc25bf73653e47fd01426`**. Parents:
`2bd339ee9bb4638588e5f07b63723caaf717c619` + `817e9b472dab896d4afeca5eaf2d4f5313b9a686`.
Tree `a6051034784d30e1ecb4af4c28caf4a596dafdab` совпадает с принятым final PR tree.
Отдельный [push/main CI 35508232378](https://github.com/Elefesys/ai-service-manager/actions/runs/35508232378)
SUCCESS: 153 non-integration + 189 PostgreSQL + 30 frontend + 6 прежних M1.2 browser
= 378 cases; foundation/browser и оба clean-source gates PASS. C0 проверил exact
actual tested SHA, ZIP digest, clean worktree, reconstructed tree и 11 canonical originals.

Полный C0 API review, 18-критериальная матрица, ограниченные исправления API-01/02
и targeted C8 PASS сохраняются в [API receipt](reviews/M1_3_API_C0_ACCEPTANCE.md).
Принятый DB receipt/DB-A01…32 и R4/D-01…D-13 не переоткрываются.
Это приёмка только backend/API, не всего milestone и не production.

Единственное готовое поручение C5 — верхний [M1_HANDOFF](tasks/M1_HANDOFF.md).
Repository `Elefesys/ai-service-manager`, accepted implementation base
`43f22b5e28a93e269eccc25bf73653e47fd01426`, task branch **`c5/m1-3-owner-ui`** → `main`.
Продолжать подготовленный Draft PR этой ветки; не продолжать закрытый PR #14.
Первый C0 coordination commit фиксирует только post-merge API receipt, реестр,
активный handoff и историческую границу DB receipt. Сохранить его. Полные published
head/PR/CI переданы в сообщении и PR, без следующего SHA-only docs commit.

Конечный остаток M1.3:

1. C5: один минимальный owner screen; subscription/entitlements; contact edit с
   recovery того же intention/body/key; Audit; component tests и реальные browser
   journeys через принятый API и PostgreSQL. Перепроектирование auth/DB/API не выдано.
2. C0 review UI и его evidence; targeted C8 только по конкретным рискам/незакрытым
   критериям; ручной merge UI PR после green final-head CI, затем отдельный main CI.
3. Итоговое решение C0 по всей M1.3. До этого milestone IN_PROGRESS и M2 не выдан.

Упрощения: существующая Console и auth recovery, один owner panel, одна contact
форма и фиксированный Audit page size10 с «Загрузить ещё»; без editors каталога,
подписки/mode, универсального Audit UI, новых routes/dependencies, providers и Jobs.
Это реализация принятой границы, не новая архитектура и не отмена R4.
Текущие инструкции — этот блок, актуальная таблица и верхний handoff; всё ниже — история.

## История — API pre-merge review


**DB-срез INTEGRATED / VERIFIED. Backend/API-срез REVIEW: C0 PASS, targeted C8
PASS; готов к обычному merge commit после SUCCESS итогового опубликованного head.
API ещё не интегрирован. M1.3 milestone IN_PROGRESS; C5 и M2 не выданы.**

Продолжается [PR #14](https://github.com/Elefesys/ai-service-manager/pull/14),
`c1/m1-3-billing-api` → `main`. Принятый base остаётся actual merge PR #13
`2bd339ee9bb4638588e5f07b63723caaf717c619`, tree
`5bf0a4fc429cc11b1b1b2da03147fad6ab088ad8`, отдельный
[push/main CI 35503584157](https://github.com/Elefesys/ai-service-manager/actions/runs/35503584157)
SUCCESS. Первый coordination commit `4c167e2ea1e2cb3e9721a7cefe5da72372eca0ad` сохранён.

C0 проверил весь C1 diff и исходный head `26ca3db6f5dd6c6e784583e02d3026edfa321954`
с CI 35506227688 SUCCESS (377 cases). Два конкретных P2 targeted C8 закрыты
ограниченным исправлением `a6d44560f035a4a288ab62abbac1ad2bde3651ad`, tree
`2a587356a9591c6a997ab245a2c0c9403930222b`: входная OpenAPI-схема после U+0020 trim;
согласованные deadlines и завершение фоновых HTTP tasks в concurrency tests.
Runtime normalization, auth/DB semantics, migrations/grants, R4, frozen contracts,
frontend, dependencies и CI неизменны. [CI исправления 35507439390](https://github.com/Elefesys/ai-service-manager/actions/runs/35507439390)
SUCCESS: 153 non-integration + 189 real PostgreSQL + 30 frontend + 6 прежних browser = 378 cases; оба clean-source gates PASS. Полная матрица, проверенные snapshots и пределы evidence —
[API C0 receipt](reviews/M1_3_API_C0_ACCEPTANCE.md); DB receipt сохраняет прежнюю приёмку.

Единственный активный handoff — верхний блок [M1_HANDOFF](tasks/M1_HANDOFF.md).
Этот согласованный docs update фиксирует решение; SHA и CI его итогового head
публикуются в PR и ответе C0, без следующего SHA-only docs commit.
До ручного merge C0 проверяет SUCCESS именно итогового head и неизменный base.

Конечный остаток M1.3:

1. Пользователь переводит PR #14 из Draft через Ready for review и выполняет
   **Create a merge commit**; C0 затем проверяет actual merge commit/tree и отдельный
   `push/main` CI. Только после этого API становится INTEGRATED / VERIFIED.
2. C0 выдаёт C5 одно готовое задание от подтверждённого API base: один минимальный
   owner screen, subscription/entitlements, contact edit с сохранением intention/body/key
   и auth/CSRF recovery, Audit; component tests и реальные M1.3 browser journeys.
3. После review/интеграции C5 и общего main CI C0 принимает всю M1.3. M2 до этого не выдавать.

Сохраняются R4 и D-01…D-13. Упрощения уже соответствуют принятой границе: существующий
auth/UOW, одна DB command, три routes и один owner screen. Дополнительные editors,
generic billing/Audit framework, payments/providers, Jobs и production не требуются.
Нового архитектурного решения нет. История ниже не является текущим поручением.

## История — выдача C1 и implementation candidate


**DB-срез M1.3 — INTEGRATED / VERIFIED. M1.3 milestone — IN_PROGRESS.** M0/M1.1/полная M1.2 сохраняют VERIFIED. Backend/API C1 реализован в продолжаемом Draft PR #14 и передаётся на CI/C0 review; приёмка и интеграция API не выполнены. C5 и M2 не выданы.

PR #13 MERGED обычным merge commit `2bd339ee9bb4638588e5f07b63723caaf717c619`; parents `552e74c7b542b81ee523d1eccfa0fffe7de06a5b` и `0df55aa577b49b6bc863c2f8b76d1851eea01457`; tree `5bf0a4fc429cc11b1b1b2da03147fad6ab088ad8` совпадает с принятым PR snapshot. Отдельный [push/main CI 35503584157](https://github.com/Elefesys/ai-service-manager/actions/runs/35503584157) SUCCESS: foundation/browser и оба clean-source gates, 106 non-integration + 146 PostgreSQL + 30 frontend + 6 прежних M1.2 browser = 288 cases. C0 проверил actual tested SHA, ZIP digest, clean worktree, reconstructed tree и 11/11 canonical originals.

Receipt с полной матрицей и post-merge evidence: [M1_3_DB_C0_ACCEPTANCE](reviews/M1_3_DB_C0_ACCEPTANCE.md). Историческая 1–48 не найдена; новая DB-A01…32 явно не является восстановленным оригиналом. Принятый R4 SHA-256 `0d33a26aa13fb3eda34b0a5c07a4a11dc263b1ee37ce9e3fda126f53e0c0282a` неизменен; старые PROPOSED/PENDING внутри snapshot не переоткрывают принятие контракта.

**Следующее поручение C1:** единственный активный блок [M1_HANDOFF](tasks/M1_HANDOFF.md). Repository `Elefesys/ai-service-manager`; accepted implementation base — actual main `2bd339ee9bb4638588e5f07b63723caaf717c619`; task branch `c1/m1-3-billing-api`, target `main`. Первый C0 docs commit только фиксирует post-merge DB acceptance и выдачу C1; это не новый implementation base и не повод создавать отдельный docs merge gate. C1 продолжает подготовленную ветку/её единственный Draft PR. Полный SHA опубликованного coordination head фиксируется в PR и передаваемом сообщении, не новым SHA-only commit.

Разрешённый C1 scope: billing repository и настоящий EntitlementService, ровно три R4 routes, отдельные OWNER billing/audit permissions, exact DTO/errors/cursor, существующие auth admission/tenant UOW/CSRF/idempotency, additive CORS, generated OpenAPI и существенные API/PostgreSQL tests. 0001…0004 не редактировать, новый revision не выдавался. Устаревшие pre-DDL/DB-only запреты ниже — история; текущая выдача относится только к C1 backend/API.

Конечный остаток M1.3:

1. C1 implementation → C0 review (targeted C8 по конкретным рискам/обязательным критериям) → ручная интеграция и отдельный main CI → приёмка API.
2. Только затем C0 выдаёт C5: один минимальный owner screen, subscription/entitlements, contact edit/recovery, Audit, component tests и настоящие M1.3 browser journeys.
3. После review/интеграции C5 и общей проверки C0 — решение по milestone M1.3. До этого не объявлять M1.3 завершённой и не выдавать M2.

Переиспользовать принятый auth/UOW и DB command; R4 не сокращается. Новые provider payments, catalog/subscription/mode editors, Jobs/Outbox, общий billing framework, production и дополнительные endpoints не входят. Новые архитектурные предложения отделяются от исправлений и не считаются принятыми автоматически.

Текущие инструкции — только этот блок, актуальная таблица задач и верхний M1_HANDOFF. Датированные записи ниже сохранены как история.

### C1 implementation candidate / 2026-09-20

Продолжен [Draft PR #14](https://github.com/Elefesys/ai-service-manager/pull/14),
с сохранением coordination commit `4c167e2ea1e2cb3e9721a7cefe5da72372eca0ad`
над принятым base `2bd339ee9bb4638588e5f07b63723caaf717c619`.
Реализованы один DB-time SQL snapshot/EntitlementService, отдельные live OWNER
permissions, три точных R4 routes, guarded tenant adapters, единственная contact
SQL command, строгие DTO/errors/cursor и additive CORS. OpenAPI сгенерирован;
семь прежних routes и все прежние OpenAPI schemas сохранены семантически точно.
R4, migrations/grants, frozen auth/tenancy contracts, frontend, dependencies и CI
не менялись. Consumer/recovery сведения находятся в `contracts/README.md` рядом
с generated OpenAPI; нового нормативного контракта нет.

Локальный Python 3.13.15 / `uv sync --frozen --offline --python 3.13`: Ruff,
format, strict mypy, 152 non-integration tests, generated OpenAPI check и 11/11
canonical checksums PASS. Добавлены 43 real API/PostgreSQL cases; их collection
не является исполнением. `sh scripts/ci.sh` и `sh scripts/test_browser.sh` здесь
завершились `docker: not found`; полное исполнение — в неизменённом GitHub runner.
Конечные head/tree, CI URL, фактически tested SHA/tree и результаты публикуются
C1 в этом PR и едином возврате C0 после последнего commit, без SHA-only docs chain.
Эта запись не заменяет CI evidence и не объявляет API INTEGRATED/VERIFIED.

## История — DB pre-merge решение

### История — DB pre-merge приёмка M1.3 / 2026-09-20

M0/M1.1 и полная M1.2 сохраняют **VERIFIED**. M1.3 остаётся **IN_PROGRESS**. DB-срез PR #13 находится в **REVIEW**: C0 DB review PASS, targeted C8 PASS; до ручного merge обязателен SUCCESS итогового head. Actual merge и отдельный push/main CI ещё не выполнены. Backend/API и UI M1.3 не приняты и не выданы.

- PR: https://github.com/Elefesys/ai-service-manager/pull/13, ветка `codex/-m1.3-db-only-0004`.
- Проверенный base main: `552e74c7b542b81ee523d1eccfa0fffe7de06a5b`.
- Implementation snapshot: `cc172d12e3d48f47d294d862a0c73b6ea126320d`, tree `f32ec3b726d5c008476530625b56ce32c31fe1e3`; execution/review evidence — в едином [DB receipt](reviews/M1_3_DB_C0_ACCEPTANCE.md).
- Accepted R4 неизменен: `docs/tasks/M1_3_CONTRACT.md`, SHA-256 `0d33a26aa13fb3eda34b0a5c07a4a11dc263b1ee37ce9e3fda126f53e0c0282a`. Старые PROPOSED/PENDING в самом историческом contract snapshot закрыты последующей приёмкой контракта, не являются текущим поручением перепроектировать его.
- Историческая матрица 1–48 не найдена. Новая C0 DB-матрица в receipt явно отделена от оригинала и не вводит новых требований.
- C8-M1.3-DB-01 имеет прежний targeted PASS. Новые C0-M1.3-DB-02…05 воспроизведены на PostgreSQL и исправлены в существующем PR; targeted C8 **PASS** на `fa83d612… → cc172d12…`, implementation CI [35502644158](https://github.com/Elefesys/ai-service-manager/actions/runs/35502644158) **SUCCESS** (288 cases, в том числе 146 PostgreSQL). Оставшихся DB implementation blockers не выявлено; результат final-head gate фиксируется в PR и ответе C0.

Единственный активный handoff — верхний блок [M1_HANDOFF](tasks/M1_HANDOFF.md). Текущие инструкции находятся только здесь, в актуальной таблице задач и в верхнем handoff; остальные датированные решения ниже — история, а не параллельные задания.

Конечный остаток M1.3:

1. Final-head CI и обычный merge commit PR #13 пользователем; C0 затем проверяет actual merge SHA и отдельный `push/main` CI. Только после этого DB-срез становится INTEGRATED / VERIFIED.
2. C1 от подтверждённого main: billing repository + настоящий EntitlementService; три R4 routes; permissions/DTO/errors/cursor; сохранение auth/CSRF/idempotency; additive CORS; generated contracts и существенные API/PostgreSQL tests. Затем review и интеграция C1 с main CI.
3. C5 только от принятого API: один owner screen, subscription/entitlements, contact edit/recovery, Audit, component tests и реальные browser journeys M1.3. Затем review, интеграция и итоговая приёмка milestone C0.

M2 и production не выданы. Упрощения: использовать принятую инфраструктуру auth/tenant UOW и один экран; не добавлять общий billing framework, новые routes, редакторы каталога/подписки/mode, provider payments или универсальный Audit UI. Это реализация уже принятой границы, не отмена R4 и не новые архитектурные решения. Повторный review требуется только при конкретном риске/изменении или незакрытом обязательном критерии.

## История решений до DB-приёмки

Все последующие датированные выдачи/запреты сохраняются как история. Актуальная таблица задач отдельно обозначена ниже.

### История — M1.3 DB prerequisite PASS; migration 0004 RESERVED / 2026-09-20

M0/M1.1 и полная M1.2 сохраняют VERIFIED. M1.3 pre-DDL contract интегрирован в actual main `ce585d67168489083e9b94e4be4f5669b16a8552`, tree `ace73cdf8163428eb74872c35ce9e920d5e9066c`; PR #9 MERGED, push/main run `35460116356` SUCCESS. Canonical `docs/tasks/M1_3_CONTRACT.md` SHA-256 остаётся `0d33a26aa13fb3eda34b0a5c07a4a11dc263b1ee37ce9e3fda126f53e0c0282a`. M1.3 milestone остаётся **IN_PROGRESS**.

C2 prerequisite в исходном Codex sandbox вернул fail-closed CHANGES_REQUESTED только из-за container restriction `unshare: operation not permitted`; несовместимость PostgreSQL/`btree_gist` не была установлена. C0 разрешил одноразовый test-only GitHub-hosted probe в Draft PR #11 без права merge. Первоначальный workflow был SKIPPED из-за branch-name guard; C0 исправил только guard в probe branch.

**DB prerequisite — PASS.** Exact test-only PR #11 base: main `ce585d67168489083e9b94e4be4f5669b16a8552`; final probe head `fca70041c86a859fd1aa8fcb06c95d2a0a830681`; GitHub PR virtual merge/tested commit `e1e327162297a556a99d8873a741f775a13aacf2`, tree `44dc6a2c85cc95045c8001812c78c47941f7998d`. Permanent PR delta — только `.github/workflows/m1_3_btree_gist_preflight.yml`. PR #11 CLOSED / NOT MERGED; probe workflow не входит в main.

Special preflight run `35463399932` SUCCESS. Artifact `10589963101`, SHA-256 `180ff8829976ff3d457ea186c4142d32a434ab71bb38afe2b6bfc1027e42ff87`. C0 проверил artifact и live evidence:
- exact RepoDigest `pgvector/pgvector@sha256:2ba9ca5f2e7daa0f0e7723cba1ee9167bab54efd3640516a44ac1a928dd67e7a`;
- PostgreSQL `18.6`, `server_version_num=180006`; vector `0.8.6` в schema `extensions`;
- `btree_gist` default/installed `1.8`, trusted=true, relocatable=true, installed namespace `extensions`;
- default UUID GiST opclass `extensions.gist_uuid_ops`, family `gist_uuid_ops`, equality strategy 3 / `uuid = uuid`;
- exact exclusion probe: adjacent half-open intervals same Workspace accepted; overlap another Workspace accepted; overlap same Workspace rejected;
- `asm_migrator`: no SUPERUSER/BYPASSRLS/CREATEDB/CREATEROLE, no DB CREATE, `USAGE extensions=true`, `CREATE extensions=false`; no privilege broadening needed;
- repeated admin preflight leaves version/namespace unchanged;
- intentional prerequisite mismatch aborts before sentinel domain DDL; sentinel absent;
- final probe worktree clean.

Обычный regression run на том же PR snapshot `35463399929` SUCCESS; artifact `10591045912`, SHA-256 `beddda7af582007be61160443921a6cfcf5de5b606d877ce032dd328ead1b17f`; tested commit `e1e327162297a556a99d8873a741f775a13aacf2`, empty worktree, reconstructed tree `44dc6a2c85cc95045c8001812c78c47941f7998d`.

**C0 резервирует migration successor:** file `migrations/versions/0004_billing_entitlements_audit.py`, revision `0004`, down_revision `0003`. Reservation принадлежит M1.3 DB slice C2; параллельных DDL writers нет. 0001/0002/0003 не изменять. Reservation не означает implementation PASS/REVIEW/INTEGRATED.

Первый разрешённый implementation slice после интеграции этой coordination записи — C2 DB-only по exact accepted R4: admin/bootstrap prerequisite для `btree_gist`, migration 0004, exact eight-table schema/RLS/grants/functions/constraints и real PostgreSQL acceptance. Backend/API/CORS/frontend остаются отдельными последующими slices C1/C5 и сейчас не выдаются.

Receipt: `docs/reviews/M1_3_BTREE_GIST_C0_ACCEPTANCE.md`.

## Предыдущее решение C0 — R2 (история)

**M0 — VERIFIED. M1.1 — VERIFIED. Полная M1.2 — INTEGRATED / VERIFIED.** Actual main `28c289ce6f77e33676cfa416585cc0e20c0be4e3`, tree `0df4c1b9a2e6922f742ebe459e46dd93d2c2959f`; PR #8 MERGED, push/main CI 35368244266 SUCCESS: foundation + browser + оба clean-source gates, 246 cases. Backend и UI приняты; UI-01/02/04/05 CLOSED в границах reviewed snapshots. **M1.3 — IN_PROGRESS: C2 verdict CHANGES_REQUESTED; C1 выдана только редакция R2 pre-DDL контракта по решениям C0.** Runtime/DDL M1.3 ещё не разрешены до C0/C2 review контракта. Полный M1/M2/production не приняты.

Принятый implementation merge M1.1: `b480d864a246cb0573b40fa5211f66625a71de91`.
Проверенный C2 head: `fa98e714d78485f8d07108294263c89d90a6e7f0`.
Исходный base задачи/M0: `7eaa9aa63b3f27215f6eb970fb9eb857fd291f62`.
Implementation tree: `66b87d3797bff856df449c878347766e147c5c01` (74 файла).

Следующий разрешённый scope: **M1.3 — C1, единая contract-correction R2 местных Plan/Subscription/Entitlements и Audit**, продолжение PR #9 от reviewed proposal `f4fb513de79c2a9b93c746db17b3395d5233dfdf`. Исходный accepted task base остаётся `28c289ce6f77e33676cfa416585cc0e20c0be4e3`. Зависимости M1.1/M1.2 удовлетворены; DDL/runtime ещё не выданы. Решения для R2: `docs/reviews/M1_3_C0_C2_DISPOSITION.md`; после исправления необходимы C0/C2 review и отдельная выдача implementation/revision. Канон и предыдущие ADR не отменены; billing provider, client payments и future Jobs не входят в этап.

Выданный C0 исходный base M1.3: `28c289ce6f77e33676cfa416585cc0e20c0be4e3`, actual accepted main. Moving main, PR test-merge и локальный SHA исполнителя не заменяют его. Последующий механический docs commit сохраняет этот base и фиксируется отдельно; не создавать бесконечную цепочку коммитов ради записи собственного SHA.

### M1.3 — C0: C2 CHANGES_REQUESTED; единая редакция R2 / 2026-09-19

C2 проверил published proposal `f4fb513de79c2a9b93c746db17b3395d5233dfdf`, tree `529e8bcb5de4be04fb0a56f4737327052b22d131`, contract SHA-256 `cab7c014eb0c264377f2a160825cdb984195ee4fcf165965bc3deb7838558c2b`. История и ровно четыре исходных docs paths подтверждены. **CHANGES_REQUESTED** относится к proposal, не к M1.3 runtime: его ещё нет. G-01…G-07 и OPEN-01…07 требуют согласованной R2 и повторного C0/C2 review; автоматически закрытыми не считаются.

Решения C0 D-01…D-13 для R2 изложены в `docs/reviews/M1_3_C0_C2_DISPOSITION.md`. Выбран exact восьмитабличный inventory (SaaS billing в platform, Audit в app; Workspace isolation независимо от schema), sealed entitlement set, декларативный non-overlap с отдельно подготовленным btree_gist, immutable narrow command receipt, один typed contact-command/Audit write path, один источник criticality/DB snapshot и один body expected_version. Контакт ограничен display name. Это направления редакции и будущие proof obligations, не уже LOCKED архитектурный ADR/разрешение DDL. Runtime, grants, migration successor и generated contracts не выданы. Production retention и доступность production infrastructure остаются OPEN.

C1 разово разрешён точный механический перенос этого решения в реестр и C0 receipt, затем изменение только `docs/tasks/M1_3_CONTRACT.md`. Не переисполнять старые transfers M1.2, не менять acceptance M1.2, не cherry-pick-ить maintenance patch в контракт. Статус R2: PROPOSED / AWAITING C0-C2 REVIEW. C2 исходный report и C0 решения различаются; отклонения от рекомендаций явно описаны в receipt. Старый seven-table proposal сохраняется в Git history, но не остаётся конкурирующим нормативным вариантом в R2.

### M1.2 maintenance — C0-M1.2-E2E-01 / 2026-09-19

Исторический docs-only run PR #9 `35373643918`: foundation SUCCESS (240), browser 5 PASS/1 FAIL на desktop keyboard, browser clean-source SKIPPED. Этот результат не стирается и не становится зелёным от чужого PR.

C0 принял исправление **на snapshot** PR #10 `f05abe2f64bfe81f2db57b450440133306410a60`, tree `721b205f2cdc8ba8405ef47d001f2e4e82e286f9`: только 6 вставленных строк `frontend/e2e/auth.spec.ts`, остальные 108 файлов/modes сохранены. Run `35421203125`, attempt 1: foundation `105839129341` и browser `105839129444` SUCCESS, оба clean-source PASS; 105 Python + 105 PostgreSQL + 30 frontend + 6 Playwright = 246 cases. ZIP SHA-256 `63b701bd1eae3fc11fef7b354b644c30ab1d59f8c78057570f78abc9d8f6a385`. CI checkout `489160ca5e7ae43ae292139eef4df7c5ef621192` — virtual merge, не actual main. C0 проверил архив/tree/originals, не выполнял новый локальный Playwright/PostgreSQL run.

**Maintenance — REVIEW: исправление принято C0, интеграция ещё не подтверждена.** Разрешён обычный пользовательский merge exact PR #10 при прежнем base `28c289ce…`, зелёных gates и соблюдении protections; отдельный C8 для шестистрочного test-only изменения не требуется. Actual merge/main SHA и post-merge CI не назначаются заранее и здесь не утверждаются. После интеграции нужен собственный actual main run. PR #9 остаётся Draft/NOT MERGED; новый CI его актуального head/base проверяется отдельно. Приёмка M1.2 на `28c289ce…` сохраняется; не обещается отсутствие любых flakes. Два reported moderate npm audit findings не исследованы до конкретных advisory и не являются основанием менять зависимости в текущей test/docs задаче.

### M1.2 — C0: actual main принят; M1.3 pre-DDL выдан / 2026-09-18

C0 принял **полную M1.2 INTEGRATED / VERIFIED** после фактического слияния PR #8 в `28c289ce6f77e33676cfa416585cc0e20c0be4e3` и отдельного push/main run `35368244266`. Foundation `105675787590` и browser `105675787266` SUCCESS: 105 Python + 105 PostgreSQL + 30 frontend + 6 Playwright = 246 cases; оба clean-source gates SUCCESS. Receipt: `docs/reviews/M1_2_C0_ACCEPTANCE.md`.

ZIP `10557427976`, SHA-256 `d71f362404280dea321c3bc1a9cc21edb5cae10469d17886c013eea29e008ef9`: проверены actual tested SHA, empty worktree, 109-file tree/modes `0df4c1b9a2e6922f742ebe459e46dd93d2c2959f`, 11 оригиналов и точные четыре docs postimages. Остальной source совпадает с C8-reviewed UI tree. Предшествующий documentation head `11bb299379833f470c62f98dd343fb769bb86c87` имеет SUCCESS run `35367688000`; его green не подменяет новый main run.

C8 UI-01/02/04/05 и прежние C0/backend dispositions остаются CLOSED. Accepted browser/RTL limitations и история flaky run сохранены в receipt. C0 не заявляет собственный новый локальный DB/Vitest/Playwright run, live production/платежи или Architecture Freeze.

**M1.3 IN_PROGRESS, первый этап — C1 pre-DDL contract.** Scope: Workspace billing boundary, local WorkspaceBillingAccount, versioned SaaSPlanRevision/PlanEntitlements, Subscription TRIALING либо ACTIVE+COMPED, separate WorkspaceServiceMode, EntitlementService и Audit атомарно с выбранной domain mutation. Точная schema/table/grant/API/permission shape пока требует предложения и C0/C2 review; нет скрытого bypass или `if plan == ...`. Entitlements не заменяют security permissions. Новая реализация, DDL, миграционный revision и UI C5 в этом этапе не выданы. M2/production не запускать.

C1 разово разрешён точный перенос этого post-merge решения и двух сопутствующих документов первым отдельным commit, затем создание одного `docs/tasks/M1_3_CONTRACT.md`. Это единственный реестр; receipt/contract не создают параллельных task statuses. Приёмка контракта и дальнейшая выдача implementation остаются за C0; новый PR без merge.

### M1.2 — история C0: UI-review завершено, pre-merge integration / 2026-09-18

C0 принимает переданный пользователем полный targeted C8 PASS по UI-05 для published head `7821aae54834de7107244090f76a1c7f327af897`, tree `0bcbf5bf0dd9ca937a56af5ef723697cbcfd8ef4`. PR #8 `codex/-ui-business-console` → `main` остаётся OPEN / DRAFT / NOT MERGED. Backend base `aa7e792555c19d798eafa0cae17d29b73ca12376` сохраняет INTEGRATED / VERIFIED; общая **M1.2 — REVIEW**, не INTEGRATED/VERIFIED. Полный receipt: `docs/reviews/M1_2_UI_C0_PREMERGE.md`.

Последовательность dispositions C0: **C8-M1.2-UI-01/02 CLOSED** на `b74da6662c23a5a1affb7157016eb8a36a338007` по targeted C8; **C8-M1.2-UI-04 CLOSED** на `c1e1e480f7ef61447c6b802fe142399a8a328fcf` после четырёх успешных адресных C8 regressions; **C8-M1.2-UI-05 CLOSED** на текущем `7821aae…` после независимой проверки барьеров readiness/start/completion. Новых блокеров C8 не сообщил. Прежние C0 dispositions по Bootstrap DTO/UUIDv7/fault-A/safe diagnostics сохранены; одинаковые цифровые номера C0 и C8 не объединяются в одну находку.

Последний C8 лично проверил exact object/tree/ancestry, one-file test-only delta, Node 24.8.0/npm 11.6.0 и subprocess path; locked install/typecheck, 3 targeted processes (каждый 2 passed / 21 filtered), 1 full frontend process (30 passed), build и clean source/index. Новый DB/Playwright прогон C8 не выполнял. Серия C5 10+3 — received report; raw logs не проверены C0. Исторический C8 29 passed / 1 failed на `c1e1e…` не стирается; конечная зелёная серия не гарантирует отсутствие всех будущих flakes. White-box listener barrier принят для ограниченного test-only review.

CI `35358909227`, attempt 1, pull_request — SUCCESS: foundation `105645004565`, browser `105645004072`, clean-source в обоих jobs. 105 Python non-integration + 105 PostgreSQL + 30 frontend + 6 Playwright = **246 cases** без повторного подсчёта frontend при browser build. Checkout `fcab2583010bb6cece456d8daaba239217bc78ef` — virtual test-merge с тем же tree, не интеграция в main. Artifact `10553656868`, ZIP SHA-256 `93ef3671f2e5e86242857f8b5c998910c1a759a53c0ec7ceefd06204603b1de0`; C0 проверил архив, 108-file tree/modes, tested SHA, clean worktree и 11 оригиналов. При оформлении повторно прочитаны refs/run/jobs и сохранённые source bytes; новых локальных Vitest/DB/Playwright прогонов C0 не заявляет.

C8-M1.2-UI-03 (P3) остаётся принятым ограничением evidence, не доказательством authenticated A→B browser isolation. Fault A означает delivered replacement cookie + lost body, не loss of Set-Cookie. Новые auth/busy гонки проверяются RTL, не расширением шести browser journeys. Production/реальные данные/Architecture Freeze/M1.3 не включаются.

Ранее неисполненный UI-04 transfer оставил этот реестр на точном preimage `c3b8cd680e160e2722d2c81bee7e5c5a3f71e6c549a61d132ad258804feb326a`; расхождение исполнения не диагностировано до конкретной причины. Новый единый pre-merge пакет заменяет только прежнее НЕВЫПОЛНЕННОЕ поручение на перенос, сохраняя решения C0. Отдельно старый transfer не запускать. Исторические OPEN/CHANGES_REQUESTED ниже описывают прежние snapshots и не отменяют этот текущий disposition.

Разрешён только точный механический перенос четырёх документов: реестр, M1_HANDOFF, интеграционные metadata IMPL-002 и UI C0 pre-merge receipt. Реализация, тесты, migrations, contracts, locks, CI/Compose и canonical originals неизменны. После scope-check, SUCCESS обоих jobs последнего опубликованного docs head и неизменного base main C0 разрешает пользователю **Create a merge commit PR #8**, без squash/rebase/force-push/auto-merge/обхода protections. При неожиданной delta/base — остановка и C0. Затем обязателен отдельный actual main CI с foundation/browser; только после его проверки C0 фиксирует полную M1.2 INTEGRATED/VERIFIED. Дополнительный C8 review этой точной docs-only delta не нужен; M1.3 остаётся TODO / не выдана.

### M1.2 — C0: независимое UI-review C8, ограниченная доработка / 2026-09-18

Проверенный UI snapshot: `8f3cb8067d671122c31368ad45614f87a6b14cd6`, tree `b3ef79f919ce3bd90be1f33e89caa12b7447cfd8`, PR #8 `codex/-ui-business-console` → `main`, OPEN / DRAFT / NOT MERGED. Backend base `aa7e792555c19d798eafa0cae17d29b73ca12376` сохраняет INTEGRATED / VERIFIED; M0/M1.1 — VERIFIED. Общая M1.2 — IN_PROGRESS, UI возвращён C5 на ограниченную доработку. **CHANGES_REQUESTED — вердикт review, не новый статус задачи или архитектуры.** Merge не разрешён, M1.3/production не выданы.

C0 принимает вывод C8: **C8-M1.2-UI-01 — P1 / OPEN** (pending logout intent после второй неоднозначной logout-попытки не учитывается явным session recheck) и **C8-M1.2-UI-02 — P1 / OPEN** (устаревший session response может заменить более новое auth-состояние из-за отсутствия request ownership на success path). C8 воспроизвёл UI-01 временным синтетическим Vitest probe; UI-02 обоснована code review, отдельный выполненный probe для неё в отчёте не заявлен. C0 сверил опубликованные App.tsx и UI-контракт; нового локального Vitest/Playwright/PostgreSQL-прогона C0 не выполнял. Конкретная эксплуатация, обход backend authorization/RLS или утечка production-данных не установлены.

C0-M1.2-UI-03/04 — CLOSED на reviewed snapshot (Bootstrap DTO и UUIDv7). C0-M1.2-UI-05 — CLOSED для описанного fault-A recovery-теста. C0-M1.2-UI-06 — CLOSED на проверенном пути безопасной диагностики, не общая гарантия отсутствия любых утечек в любых логах. C8-M1.2-UI-03 — P3, принято как ограничение evidence: tampered Workspace проверяется anonymous-запросом после неверного пароля, не authenticated cross-Workspace browser-тестом. Fault A охватывает delivered replacement cookie + lost response body, не потерю Set-Cookie. Эти ограничения не назначены новыми блокерами.

Существующий CI `35341271140`: foundation `105587472030` и browser `105587471804` — SUCCESS; 105 Python non-integration + 105 real PostgreSQL + 19 frontend + 6 Playwright = 235 tests. Checkout `0941d59e173d931f0cb1c556403e4c4f66b0540f` — виртуальный PR merge, не интеграция. Green CI не отменяется, но отсутствующие repeated-logout/out-of-order regressions не считаются покрытыми. C8 использовал received C0 evidence и локальный Node 20, не выдавал это за собственный Node 24/DB/browser run.

Разрешена одна доработка C5: logout-intent transitions + auth request ownership и deterministic RTL regressions, без изменения принятого backend/API/DDL/зависимостей или расширения milestones. Нужен новый полный CI обоих jobs для исправленного head, затем targeted C8 re-review изменённой UI state-machine delta. Повторный полный backend review и произвольные повторения прежнего green run не требуются. Закрытие новых P1 и интеграция остаются решениями C0 после evidence.

Этот текст — решение C0; C5 разово разрешён его точный механический перенос и две согласованные замены текущего summary/строки M1.2. Прочие строки реестра и история неизменны. Исполнитель не получает права объявлять P1 CLOSED, UI VERIFIED или сливать PR.

### M1.2 — C0: backend принят, выдан UI C5 / 2026-09-18

**Backend-срез M1.2 — INTEGRATED / VERIFIED** на `aa7e792555c19d798eafa0cae17d29b73ca12376`, tree `77ddd22af30ef07afa89f61e96e1066ba4be8692`. PR #7 фактически слит, push/main run `35321610083`, job `105525139486` — SUCCESS; 91 non-integration + 105 real PostgreSQL + 3 frontend = 199 passed. C0 проверил ZIP SHA-256 `548b8824dfda4c0c80e0ea4819a460ef9a2042c20e58d192101069ffed6341bb`, tested actual merge, 94-file tree/modes, clean worktree, 11 оригиналов и точную документационную дельту. Receipt: `docs/reviews/M1_2_BACKEND_C0_ACCEPTANCE.md`.

C0 явно выдаёт **C5: login/logout/session-expired/recovery UI и реальный browser journey** от указанного полного API SHA. Общая **M1.2 — IN_PROGRESS**: переход от REVIEW завершённого backend к исполнению оставшейся UI-части, не отмена backend-приёмки и не новый milestone. Целевая ветка нового UI PR — main; предпочтительное имя c5/m1-2-login, допустима автоматически созданная Codex ветка с зафиксированным фактическим ref. PR #7/#6 не открывать заново. M1.3 — TODO/не выдана, production не включать.

C8-M1.2-01/C0-M1.2-04 и C0-M1.2-01/02/03 CLOSED для принятого snapshot. C8-M1.2-02 учтено контрактом; UI обязан восстановить фактическую сессию после неоднозначного HTTP-ответа без ложного logout success/слепого replay. C8 в re-review не скачивал private artifact и не запускал PostgreSQL; C0 отдельно проверил предоставленное evidence и новый actual main run.

Детальный C5 scope фиксируется выданным заданием C0 и docs/tasks/M1_2_UI_CONTRACT.md: responsive Business Console, защищённое чтение Business, typed API consumer, CSRF только в памяти страницы, отказ от прямой БД/подмены permissions, отдельная непубличная по данным Ops shell. Frontend tests + Playwright/Chromium browser gate через реальный API/PG; узкие тестовые CI/Compose/fixture изменения разрешены, runtime backend/DDL/security contract неизменны. Закреплённые frontend runtime dependencies не обновлять массово. Локальный Docker на компьютере пользователя не требуется.

Этот раздел и точные сопровождающие документы сформулированы C0; C5 разово разрешён механический перенос первым отдельным documentation commit своего нового PR, затем UI-реализация. Отдельный предварительный docs PR/merge перед началом C5 не требуется. Реестр не объявляет UI/всю M1.2 VERIFIED заранее. Последующие статусы — решение C0 по фактическому evidence.

### M1.2 — история решения C0 перед интеграцией / 2026-09-18

Backend review: **PASS; разрешено оформление и интеграция** проверенного head `194ea3cfa3f0aa9b8f271590a26ca3857ade3e54`, tree `799f271cbfc1c8815136828da35f9a32ef58b16e` (93 файла до этого документационного изменения). Единственный implementation PR — **#7**, `codex/-m1.2-r2` → `main`; исходный принятый base — `5c7188915fa219d9d6906569e2341632e4969651`. PR #6 — история контрактов и переноса, не вторая реализация и не отдельный кандидат на merge.

Статус задачи **M1.2 — REVIEW**, не INTEGRATED/VERIFIED. Backend ещё ожидает фактического merge и проверки push/main; C5 пока не выдан. Это части одной M1.2, не новые milestones. M0/M1.1 остаются VERIFIED; M1.3 — TODO, не выдана.

C0 принимает переданное пользователем заключение targeted C8 PASS для точного head/tree выше: новых блокеров нет. **C8-M1.2-01 и C0-M1.2-04 — CLOSED на этом snapshot. C8-M1.2-02 — учтено контрактом, неблокирующее; recovery UX остаётся требованием к C5.** C0-M1.2-01/02/03 также закрыты по опубликованным исправлениям и привязанному CI. Закрытие находок не означает уже выполненную интеграцию или завершение UI.

CI `35248449942`, job `105294503581`, event `pull_request`: SUCCESS; **91 non-integration + 105 real PostgreSQL + 3 frontend = 199 passed**. Tested checkout `c99d9cc7e781fd9acf20ae7276761336e38b99d1` — виртуальный test-merge, не actual main merge. Его tree совпал с implementation tree. Artifact `10508471245`, ZIP SHA-256 `b80c4c000e1aefe47ea6f2303b49d58d9f6cdb5c2355c3beea046903f4121c22`. C0 проверил архив, tested SHA, пустой worktree, tree/modes и 11 неизменённых оригиналов; новый локальный PostgreSQL run C0 не заявляется.

C8 самостоятельно проверял код и локальные targeted/non-integration suites, но не скачивал private artifact и не запускал новый PostgreSQL в re-review. DB/ZIP evidence передано C0. Это не второй независимый DB run и не формальное GitHub APPROVED от другого аккаунта. Отдельный C2 review не заявляется; C0 проверил DDL/grants, C8 — их security scope.

C0 подготовил только четыре документационных изменения: этот реестр, M1_HANDOFF, статус IMPL-002 и `docs/reviews/M1_2_BACKEND_C0_PREMERGE.md`. Исполнитель Codex вправе перенести только точный подготовленный текст. Код, тесты, migrations 0001/0002/0003, contracts JSON, lockfiles, workflows и архитектурные оригиналы не меняются. Повторный C8 review не требуется для этой точной документальной дельты; новый полный CI её опубликованного head обязателен.

После проверки точной docs-only дельты и зелёного CI текущего опубликованного head C0 разрешает **обычный merge commit PR #7**, без squash/rebase/force-push/обхода защит. Разрешение не распространяется на неожиданные изменения кода или новый base main. Далее C0 проверяет actual merge SHA, дерево и отдельный push/main CI. Только затем выдаётся C5 точный принятый API SHA. Нельзя выдавать за него текущий PR head или виртуальный test-merge.

Предыдущие разделы M1.2 ниже — история решения на прежних snapshots. Их BLOCKED/CHANGES_REQUESTED и требования доработки заменены данным решением для указанного head; история не удалена. Подробное решение и границы: `docs/reviews/M1_2_BACKEND_C0_PREMERGE.md`.

## Исторические evidence и решения (не текущие инструкции)

### Evidence приёмки M1.1

PR: https://github.com/Elefesys/ai-service-manager/pull/3
Actual merge/head CI: `b480d864a246cb0573b40fa5211f66625a71de91`.
Main run: https://github.com/Elefesys/ai-service-manager/actions/runs/35015308300
Event `push`, branch `main`, job `104537130545` (`foundation`), все шаги SUCCESS.
Artifact `10415043854`, name `m0-verification-35015308300`.
ZIP SHA-256: `b0b23c7b795f7084201a804a9285ad7634106627c9f5366c284d0b2f77287cc0`.

C0 скачал artifact и подтвердил SHA-256, tested-commit actual merge, пустой worktree-status, Git tree всех 74 файлов с modes и 11/11 архитектурных оригиналов против исходных вложений. Дерево совпало с C8-reviewed head. Новый main CI — отдельный выполненный run интеграции, не прежний виртуальный PR merge.

Результат: **24 non-integration + 62 real PostgreSQL + 3 frontend = 89 passed**. 62 = 48 прежних DB cases + 8 неизменённых C8 + 6 guard cases. Полный lint/format/mypy/types, fresh/M0 upgrade/replay/disposable downgrade/re-upgrade, readiness 0002, OpenAPI, wheel/static assets reproducibility, Docker/HTTP/proxy smoke и clean-source gates прошли. Повторные прогоны не суммируются в число tests.

Документ приёмки: `docs/reviews/M1_1_C0_ACCEPTANCE.md`. Ограниченный контракт C1: `docs/tasks/M1_1_CONTRACT.md`, `contracts/tenancy.v1.json`. Новые docs не меняют код/DDL/guards и не создают M1.2 реализацию.

## История C8-M1.1-01 — закрыта, не текущий блокер

Первоначальный C8 review: CHANGES_REQUESTED на `84d94b2187787c654928ac11b7e4d411970b2b0c`; P2 AUTOCOMMIT публиковал Python context без общей физической транзакции. Это не доказанная cross-tenant утечка. Собственный C8 PostgreSQL run `34987895881`, job `104444620955`: 55 integration passed, 1 failed; исходные 48 DB cases и 7 новых C8 прошли. Artifact `10403814298`, SHA-256 `2b4afb189a0724a8346e4941d006613e8020c808145ba3b6569a46ca0ce0afd7`. Последующие pipeline gates после failure не считались выполненными.

C0 coordination `0474594532aaada1368b4cdd11834bdd6e53b74d` записал ограниченное исправление в этот реестр. C2 fix `61c5f81c7ea9905a71c3d93ea13fe284d0e2545b` добавил actual-driver AUTOCOMMIT rejection до публикации, same-connection Workspace/XID/fence/INTRANS check, все 8 C8 cases и 6 новых tests. Первый correction run `34993878294` выявил ошибку настройки одного нового recovery test; `fa98e714d78485f8d07108294263c89d90a6e7f0` исправил только источник normal engine, не assertions или production guard.

Полный green C2 run `34994578775`, job `104467480316`, artifact `10406734324`, SHA-256 `c89dbba840903f8e8e935c0d367a1af0077a9fa76112c40078ebc371356910ef`: 89 tests и все gates. Его tested PR merge `05326998fc070aad35cc64307d678e10fc13d86d` не был main integration.

Отчёт C8 targeted re-review от 16 сентября 2026: **PASS**, устранено на fa98e714…, новых блокеров нет. SHA-256 исходного пользовательского файла отчёта: `4fcdd7ff1a44d0979cfea7d7967409a96737962ba3fbbbaa73c34a50268dbd57`. C8 независимо проверил код, тесты и existing CI/tree, но **не запускал новый PostgreSQL run в re-review**. C0 принял закрытие (PR review `5214994803`), сверил текущие refs/код/evidence, затем выполнил expected-head integration и проверил отдельный main run выше. Прежние CHANGES_REQUESTED и запрет merge относились к неисправленному snapshot, теперь заменены этим решением. Ошибки в истории не переименованы в успешные прогоны.

C8 test-only PR #4 закрыт без merge; отдельная ветка не является текущим кодом. Исходный файл 8 tests перенесён без изменения, SHA-256 `114f67314af6997aa11064cc786bea0da196f87abf6698b2ae38c281857d0737`. Повторный cherry-pick не нужен. Ни одна принятая миграция/архитектурная версия не переписана.

## История M0

Исходный README-only main: `c74db484b483fccaef7b4124b418a91979cb4be6`. PR #1 merge `1d7bb4fa0567bdd263d7910492ecf217696642de`, head `8639812ce71f5cce8f2b2ed051ff01fea67d5157`. Main run `34970531911`, job `104385439116`, artifact `10396772645`, ZIP SHA-256 `e1702634f918fb92c1a361ee5ac49a762ed58dc6b125ee85c75dd35efd2f1755`: 20 unit/fixture/import + 7 DB + 3 frontend = 30 passed, все gates. Приёмка C0, не независимый C8 review. PR #2 documentation-only merge `7eaa9aa63b3f27215f6eb970fb9eb857fd291f62`, main run `34972872410` SUCCESS; это исходный base M1.1.

11 оригиналов импортированы в `395b760175871a3d6cde10b8e01e1f9364e3bd57`, import run `34968001558`, artifact `10395434061`, SHA-256 `fd89f2dc453e0848341b55e93565779393e772ec682a607836af267407726751`. Оригиналы/manifest сохраняются; опечатка import SHA исправлялась только в review-документе. Bootstrap `34889055896` сформировал locks в `76fd251d2b323986306731505ce59773886e5ca7`, затем mypy/BaseSettings fix `c89b839c56d14c184650423a18ec35d1fc22de41` без отключения strict typing. Ранние runs `34889375796`/`34889853771` с 25 tests относятся к старым snapshots; промежуточные source failures остаются историей. Подробные предыдущие версии этого же реестра сохранены в Git, не в другом активном реестре.

## История — ограничения и очередь migration на этапе M1.2

App пока LOCAL/TEST. M1.1 — tenant foundation; backend M1.2 с auth adapter уже принят в main `aa7e792555c19d798eafa0cae17d29b73ca12376`; UI PR #8 ожидает интеграции и отдельного main CI. AuthenticatedAccount создаётся только после проверки server session; UUID не аутентификация. Same-Workspace/different-Client authorization не пройдена: Client tables ещё нет. Runtime credentials/arbitrary Python/SQL compromise не покрываются одной RLS; application authorization обязательна.

Миграция `0003_auth_sessions.py`, revision `0003`, down_revision `0002`, уже интегрирована и проверена с backend M1.2 на `aa7e792555c19d798eafa0cae17d29b73ca12376`. IMPL-002 принят C0 для ограниченной LOCAL/TEST реализации, не как новый domain ADR или production policy. 0001/0002/0003 не изменяются при оформлении. Следующая migration пока не резервируется: C5 работает с уже принятым API, не создаёт DDL.

M1.3 local entitlements/Audit, M2 Inbox/Outbox/Jobs и остальные capabilities не реализованы. Нет live provider calls, Object Storage, production backup/restore, полной vulnerability/security certification, MFA или production telemetry. Architecture Freeze v1.0 pending. M1.1 verification не означает весь M1/Pilot готов.

Запуск на ПК пользователя не выполнялся; новые full runs выполнены GitHub Linux/amd64 Docker runner. Reproducibility подтверждает locked inputs и wheel/assets bytes, не идентичность OCI metadata между CPU/builders. Старые deprecation/Docker warnings остаются сопровождением C6, не скрытыми блокерами. Реальные данные мастера, секреты провайдеров и расходы для следующего auth-среза не требуются.

## M1.2 — C0: частичный handoff и блокеры / 2026-09-16

M1.2 — **BLOCKED**, не REVIEW готового backend и не INTEGRATED/VERIFIED. M0/M1.1 остаются VERIFIED. C5 и M1.3 не запускать. C0 проверил PR #6, main, полный diff трёх опубликованных документов, AGENTS/M1_HANDOFF и применимые Spec/ADR. Явной смены канона в предложенных документах не установлено; auth protocol/library/TTL/grants остаются предложением, не принятой реализацией или security approval.

Проверенный исходный base/main: `5c7188915fa219d9d6906569e2341632e4969651`. Pre-DDL/current contract head до этой записи C0: `7527154650b99958b5cfc0f4bfdd9ea135f7fa21`, tree `d0f785b96eea45b451d09dd71864322e2591af2c`. PR #6 открыт, DRAFT, NOT MERGED; его исходный diff содержит только M1_2_AUTH_CONTRACT.md, IMPL-002-auth.md и auth.v1.json. Эта запись C0 меняет только существующий реестр на ветке c1/m1-2-auth. Результирующий coordination commit не является implementation head; исходный base задачи не меняется.

По отчёту C1, публикация implementation через create_tree остановлена сообщением: «Этот вызов инструмента был заблокирован OpenAI, поскольку мы не смогли определить статус безопасности запроса». C0 не воспроизводил этот вызов, не установил внутреннюю причину и не публиковал заблокированный payload иным путём. Не трактовать это как подтверждённый GitHub 403, нехватку repository permissions или доказанный дефект auth-кода. Сохранить исходную диагностику; дальнейшая публикация требует разрешения блокировки штатным порядком, без обхода защитного решения.

Второй блокер: C1 сообщает `sh scripts/ci.sh` → exit 127 / `docker: not found` до DB/tests. Локальные compileall/import/uv lock --check --offline по отчёту не являются pytest/mypy/установкой зависимостей или проверкой PostgreSQL. C0 подтвердил существующий remote CI run `35020860138`, pull_request на контрактном head, SUCCESS. Это evidence опубликованных контрактов и старого runtime, не неопубликованной миграции 0003/auth patch. Отсутствие локального Docker не доказывает недоступность штатного GitHub Actions runner. Новый implementation CI/tested SHA отсутствует.

В этой передаче C0 получил отчёт, не сам архив C1_M1_2_UNVERIFIED_HANDOFF.zip или M1_2_UNVERIFIED_IMPLEMENTATION.patch. Заявленный C1 patch SHA-256 `c9affad410bc9df12579d11cc10f2260f2b80263b16fbcef4ec397edcc0984f6` не перепроверен C0; код/DDL/lockfile/secret scanning не выполнены. Запросить существующие сохранённые артефакты для чтения/review и диагностики, не как разрешение опубликовать заблокированный код. Не реконструировать отсутствующий patch по prose.

Пункт C0 для проверки совместимости: принятый tests/test_postgres.py, test_real_postgres_capabilities_and_roles, содержит точное равенство семи таблицам M0/M1.1; файл не перечислен среди 23 путей в отчёте C1. При сохранении этого assertion и добавлении auth_credentials/auth_sessions тест не пройдёт. Это статический вывод из base + отчётного перечня, не запущенный auth regression и не подтверждённая проверка самого patch. Проверить реальный diff. Разрешена узкая адаптация этого expected table set к двум заявленным auth-таблицам, с сохранением точного контроля отсутствия лишних таблиц и всех role/RLS/pgvector assertions. Не удалять или skip/xfail старые тесты. Generated OpenAPI, по отчёту C1, также ещё не обновлён.

Возобновление: сохранить тот же PR/ветку и эту запись; дополнить безопасную диагностику блокировки и передать существующие файлы для read-only review. После штатного разрешения публикации и готовности исполняемой LOCAL/TEST среды нужен опубликованный implementation commit, generated OpenAPI, полные old+new real-PostgreSQL/API/session/security tests и успешный scripts/ci.sh. Только затем C0/C2/C8 review и отдельный принятый API SHA для C5. Архитектура, миграции 0001/0002 и M1.1 guards не меняются; новая рабочая ветка/PR, новый milestone или переход к UI не требуются.

## M1.2 — C0: решение по независимому review C8 / 2026-09-17

Текущий статус backend-кандидата: **REVIEW**, результат **CHANGES_REQUESTED**. Единственный активный implementation PR — #7 (`codex/-m1.2-r2` → `main`), OPEN / DRAFT / NOT MERGED. PR #6 и `c1/m1-2-auth` сохраняются как история контрактов/переноса; их не сливать и не продолжать как вторую реализацию. Исходный base: `5c7188915fa219d9d6906569e2341632e4969651`. Проверенный head: `7012bf586166d35ad82919087c0f68a6f3eb92ee`, tree `687b548f05ef45be8ad4dbb52960d523efee45b5`. Coordination `7bf818bdfd8b156620c840d5d7211087113d9fb5` сохранён в истории.

Ранее записанные отсутствие публикации и отсутствие полного auth CI больше не являются текущими блокерами этого head. Реализация опубликована через интерфейс Codex; run `35234140772` (workflow_dispatch, job `105245591311`) успешно выполнил 60 non-integration + 105 real PostgreSQL + 3 frontend = 168 tests и все обязательные gates. C0 ранее проверил artifact `10503061021`, ZIP SHA-256 `0506590fdc66ccf69f8e5f35977bb5b137af49d0ffa4ef7f17b35eac0f8bdffa`, tested commit/tree и clean worktree. Старые разделы BLOCKED — история, а не основание повторно переносить R1/R2 или обходить защитные ограничения.

C0 принимает находку **C8-M1.2-01, P2**: auth_hosts и AuthBoundary сравнивают только hostname, теряя port. C8 независимо воспроизвёл допуск `Host: localhost:9999` при единственном origin `http://localhost:8000`: внутреннее ASGI-приложение вернуло 204 вместо boundary 403 ORIGIN_DENIED. C0 подтвердил причину по текущему коду. Это не подтверждённый обход Origin/CSRF, authentication или RLS и не доказанная cross-tenant утечка. Исправление — точный allowlist нормализованных authorities, явный Compose upstream `api:8000`, отрицательные и положительные regression tests; без новых DDL/зависимостей или изменения канонических ADR.

**C8-M1.2-02, P3 — неблокирующее замечание:** после DB commit возможна потеря HTTP response/Set-Cookie. Добавить в контракт для C5 восстановление после неопределённого результата; не обещать rollback по transport error или атомарную/ровно однократную доставку cookie. Не переносить cookie до commit и не менять session/rotation/expiry semantics ради этого пункта. Frontend здесь не реализуется.

C8 лично повторил importer, OpenAPI check, lint/types, 60 non-integration tests и Host probe на точном snapshot. Новый PostgreSQL run и скачивание private CI artifact reviewer не выполнял; использовал переданные сведения C0. C0 в этой проверке не запускал новые PostgreSQL/pytest tests. Его действия: read-only сверка PR/head/tree, config/http, канона и сохранённого CI source archive. Сохранность фактических migrations/versions/0001_foundation.py и 0002_tenant_foundation.py отдельно проверена по bytes принятого base.

Разрешённый следующий шаг — ограниченная доработка C1 в той же опубликованной ветке, полный CI нового head через GitHub Actions и targeted C8 re-review. Старый SUCCESS не переносится на будущий commit. M0/M1.1 остаются VERIFIED; M1.2 не INTEGRATED/VERIFIED, вся задача требует также C5. M1.3, C5 и production не запускать.

Эта запись сформулирована C0. Исполнителю Codex разово разрешён только её механический перенос и указанная замена строки M1.2; решения о дальнейших статусах остаются за C0. Запись не закрывает C8-M1.2-01 и не является разрешением merge.

## M1.2 — C0: CI Host-fix и остаточный parser case / 2026-09-17

Backend остаётся **REVIEW / CHANGES_REQUESTED**, не INTEGRATED/VERIFIED. Проверен новый published head `e7e3d43fe8874ec4d87eaea1489cf0ba42955eea`, tree `ad4c9684c954834d243c0c9b5c0ef9977f3f3e66`; PR #7 DRAFT/OPEN/NOT MERGED. Run `35244842457`, job `105282274085`, event pull_request — SUCCESS: 75 non-integration + 105 PostgreSQL + 3 frontend = 183 tests, все gates. CI checkout `1365994e2099223bb5cae9416388dfee204c0044` — виртуальный test-merge, не main integration. Artifact `10507325963`, ZIP SHA-256 `bd455803d033d6059edf3f8fdd9b2c47c39988e52c131114e6cf205843013288`; C0 проверил архив, 93-file tree/modes, tested commit, чистый worktree и 11 оригиналов. Предыдущая coordination delta перенесена строго без самовольного закрытия находок.

Портовая часть C8-M1.2-01 исправлена; C8-M1.2-02 дополнена в контракте C5 (recovery после неоднозначного HTTP response без обещания rollback/exactly-once). Однако C0 нашёл **C0-M1.2-04, P2 — неполная fail-closed проверка malformed Host**: normalize_authority принимает `localhost:8000?`/`localhost:8000#` и `api:8000?`/`api:8000#`. Пустые query/fragment маскируют присутствие URL-разделителя; вся исходная строка не сверяется с authority. Изолированный вызов неизменённых boundary definitions пропустил их в marker app (204/inner_calls=1), правильные negative ports отказали (403/inner_calls=0). Это не демонстрация обхода authentication/CSRF/RLS, утечки или эксплуатации всей HTTP server/proxy связки. Нового locked pytest/PostgreSQL запуска C0 не делал; probe выполнен на Python 3.13.5/local dependencies и отдельно оговорённом AST-only boundary, не full app.

Следующий шаг C1: подтвердить regression штатными импортами на exact head, запретить discarded query/fragment delimiters и прочие остатки вне authority до нормализации, сохранить 183 прежних cases и добавить отрицательные raw-header regressions, затем новый полный CI на том же PR. Точечный scope — config.py, auth tests, при необходимости точное уточнение auth contract; DDL/dependencies/tenancy/session semantics неизменны. После исправления — targeted C8, затем решение C0 об интеграции. C5/M1.3/production не запускать, PR #6 не продолжать как вторую реализацию. Эта запись — решение C0, механический перенос разрешён; права самостоятельно закрывать находки/принимать M1.2 исполнителю не передаются.


## C0 — PR #10 post-merge и восстановление передачи R2 (2026-09-19)

C0 проверил фактический merge PR #10: `049b212f135f09c025d2f81badc810fa7c2c9d13`, tree `721b205f2cdc8ba8405ef47d001f2e4e82e286f9`, push/main run `35422383973`, attempt 1, SUCCESS. Foundation job `105842308563`: 105 Python + 105 PostgreSQL + 30 frontend; browser job `105842308489`: 6 passed. Оба clean-source gates PASS. ZIP artifact `10578235228`, SHA-256 `69b5d0ceb07d709a2121c38c1a3c09c022b5c8a9ce7a012571514194501e8307`; 109 файлов/modes точно совпали с ранее принятым maintenance tree. Это проверенное C0 GitHub CI evidence, не новый локальный application run.

`C0-M1.2-E2E-01` — CLOSED / INTEGRATED / VERIFIED в границах этого исправления. M1.2 сохраняет приёмку; исторический исходный base M1.3 остаётся `28c289ce6f77e33676cfa416585cc0e20c0be4e3`. Новый main не является разрешением DDL или доказательством M1.3.

R2 C1 ещё не получена. Сообщение Codex «не удалось создать продолжение» не доказывает контекстный лимит, исчерпание quota или safety block. C0 заменяет способ передачи: новая cloud-задача с PR #9 как контекстом; один временный текстовый файл `docs/tasks/C1_M1_3_R2_RESUME.txt` допускается только для переноса полного поручения и удаляется из итогового tracked tree. Архитектурные решения D-01…D-13 не меняются; итоговая дельта от reviewed `f4fb513…` — только реестр, C0 disposition и контракт R2. Без merge/rebase/force-push, нового конкурирующего PR или изменения кода. Runtime M1.3 остаётся NOT AUTHORIZED; контракт R2 ждёт C0/C2 review.
