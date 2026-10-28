# AI Service Manager — единый task register

Ответственный: C0. Канон: v0.28; стек: `docs/decisions/IMPL-001-stack.md`. Это единственный реестр исполнения. LOCKED/OPEN/DEFERRED/REVISED относятся к архитектуре; состояния задач: TODO → IN_PROGRESS → REVIEW → INTEGRATED → VERIFIED, BLOCKED требует причины.

## CURRENT — M4.1 CI BLOCKED; C5 recovery repair issued / 2026-10-29

Принятый main **1cb3b6e168276d77faa3f11f33f8ecd0408ce406**; PR37/план/IMPL-004 интегрированы.
[PR38](https://github.com/Elefesys/ai-service-manager/pull/38) candidate
**31537848de7bcfb5732622b9361cfaba41c1105b**, tree **aa265f68c3fec9e3b7128d9a800e6e5cf5574f25**.
C0 source review Gateway/DTO/fake/tests завершён без существенных замечаний;
это не независимый C8 и не итоговая интеграция.
[CI40740338709](https://github.com/Elefesys/ai-service-manager/actions/runs/40740338709),
attempt1, завершён: **10 SUCCESS / 1 FAILURE**. Foundation2286+155subtests/804PG PASS;
browser398unit PASS,53browserPASS/1FAIL. Единственный подтверждённый blocker —
existing escalation login/rotation/replay recovery: UI стал anonymous до retry.
Причинный request пока не установлен; cleanup=false после timeout — вторичный факт.

| Task | Status / ближайший результат |
|---|---|
| M4-PLAN | INTEGRATED / VERIFIED docs-only; PR37 + C0 acceptance + main CI40725828529 PASS |
| M4.1-CONTRACT | BLOCKED: C4 implementation returned/source reviewed; полный CI FAIL; PR38 не слит, C4 HOLD |
| C5-M4.1-CI-RECOVERY-R1 | REVIEW / repair candidate, C5 HOLD для C0/CI: добавлен барьер11 startup/child reads и UI перед первой rotation; задержанный observations GET должен завершиться200 до неё. Negative old-credential Business401 сохранён. Typecheck/diff/local predicate checks PASS; новый E2E NOT RUN. Basefe9de57d…; diagnostic54/54 PASS отдельно, исторический GET неизвестен; receipt в M4_HANDOFF |
| M4.2-PROBE | TODO / HOLD до приёмки M4.1; Polza adapter/synthetic comparison, отдельный ключ и подтверждённый бюджет |
| M4.3-CONTEXT | TODO: актуальный M3 context и необходимые read-only tools |
| M4.3-RUNTIME | TODO: durable AI run и настоящий guarded Telegram consumer; C2/C3 по точной дельте |
| M4.3-QUALITY | TODO: независимый scoped C8/eval; авторские тесты внутри каждой задачи |
| M4-ACCEPTANCE | TODO: bounded synthetic live, A08, actual main CI и передача M5 |

Новый диагностический run40760265440: browser54/54 и398frontend PASS; R4 полный,
controlled rotation401→anonymous воспроизведён. Полный run пока IN_PROGRESS;
исходный FAIL сохранён. Диагностика не является завершённым исправлением.

Единственная текущая выдача и матрица A01–A08 — [M4_HANDOFF](tasks/M4_HANDOFF.md).
C1/C2/C3/C4/C6/C8 HOLD. Общие файлы не редактируются параллельно.
C5 не меняет Gateway, backend/SQL/CI/VM и не ослабляет auth/replay критерии.
Direct/RAG/Vision/registry и следующие business domains сохраняют DEFERRED scope.
Платных API, новой VM активации или переоткрытия M3 нет.

## Accepted — M3 INTEGRATED / VERIFIED LOCAL/TEST; PR36 merged / 2026-10-28

Accepted actual main **d2f25673f6d2698d3c3dae2d7b2d709e134358f4**, tree
**141d0a6b2b2be0efe1fcb1c3f851796e9f4cb427**. Tree exact-equal reviewed PR36
head **5d828a1ece2840b57fb2fd7d890d3e3fd47da388**.
[Post-merge CI 40681691046](https://github.com/Elefesys/ai-service-manager/actions/runs/40681691046), push/main attempt1:
**11/11 SUCCESS**. [M3 final acceptance / handoff](tasks/M3_HANDOFF.md).

| Scope / task | Текущий результат |
|---|---|
| Whole M3 / A01–A12 | **INTEGRATED / VERIFIED LOCAL/TEST, CLOSED by C0.** C8 witnesses, exact current main CI, C6 host/policy evidence и bounded owner smoke приняты. Scope/ограничения явно зафиксированы в HANDOFF; production readiness и actual LLM не заявлены. |
| PR36 / C6-M3-TELEGRAM-POLLING-01 | **INTEGRATED / VERIFIED**: MERGED into main d2f25673f6d2698d3c3dae2d7b2d709e134358f4; candidate/main tree equality, current11/11 CI и user-observed text/photo/manual reply. PC helper вне PR; merge не deployment. |
| Main verification | 804 PG;2197 ordinary+155 subtests;54 browser/API/PG;398 frontend PASS. Native/catalog/cleanup, durable, Docker29 и6 migration shards PASS. Все11 exact checkouts/source gates подтверждены;10 artifact ID/digest совпали с upload logs, payload заново не аудировался. |
| C6-M3-TEST-POLICY-ENABLE-R2 | VERIFIED / LIVE PASS по переданному отчёту revision4; LOCAL / asm_local, тот же accepted binding; MATERIAL=true / COMMITTED, native ON/P1 / ACCEPTED/current. Source/images/schema/binding/identity и оба окна PASS на момент проверки. C6 HOLD. |
| M3-OWNER-SMOKE-R1 | VERIFIED / USER-OBSERVED LIVE PASS: HUMAN/reload, native text/edit/delete, canonical inbound delete, сохранение owner context с HUMAN, отдельный Resume/reload без наблюдаемых resend, photo replacement с MEDIA_REPLACED_UNAVAILABLE. |
| A08/P-A03-09/P-05 limits | Наблюдённый bounded scope принят; own-bot echo markers/native photo/offline/other-bot/unsupported/delayed account variants остаются NOT OBSERVED. C0 принял этот предел live-покрытия; автоматические guards сохраняются. Общий collector не нужен для принятого scope. |
| Development limits | Маршрут ПК/Happ/SSH принят для разработки; автономность к пилоту. Новое вложение после замены фото не загружается/не анализируется. Текущее состояние PC-сессии и VM после smoke не проверялось C0; нет нового runtime deployment. |
| Передача M4 | Первоначальная передача C0 уточнена [M4_HANDOFF](tasks/M4_HANDOFF.md) и IMPL-004. Актуальные задачи — в CURRENT выше; реализация не начата. |
| Другие чаты / CI optimization | C1/C2/C3/C4/C5/C6/C8 HOLD. Общая оптимизация CI остаётся DEFERRED и не запускается автоматически вслед за M3. |

Новых code/DDL/provider/VM/test/CI действий для этой приёмки не выполнялось:
C0 прочитал существующее evidence и интегрировал main в координационную ветку,
обновив только два документа сверх принятого runtime tree.

---

## History — C6 polling до итоговой приёмки / 2026-10-26

Исторический возврат PR36; его pending/REVIEW статусы заменены CURRENT выше.

| Task | Status and scope |
|---|---|
| C6-M3-TELEGRAM-POLLING-01 | REVIEW; user approved outbound getUpdates after repeated fresh webhook timeouts. Base 5c074beb4a47521b8c11a820f580673ec1c2cce2; branch c6/telegram-polling-recovery. Receiver, bounded TEST deployment/rollback, focused tests and IMPL-003; no DDL, billing, conversation policy, UI or existing transport changes. |

The recovered Selectel TEST has an enabled binding, working manual replies and
successful processing of earlier text/photo events. Six later events remain at
Telegram. [IMPL-003](decisions/IMPL-003-telegram-polling-test.md) records the approved
receive-mode revision and acceptance criteria. No polling deployment or new live
success is claimed before the user's VM receipt; M3 remains IN_PROGRESS.
Write-set: scripts/telegram_polling_receiver.py, scripts/telegram_polling_recovery.py,
tests/polling/, tests/test_telegram_polling_postgres.py, IMPL-003 and this register.
Local evidence: 30 focused unit/model tests and Ruff pass; accepted activation
receipt/runtime fixture passes. Full CI and live VM acceptance remain pending.



## History — native context: согласованное исправление / 2026-10-21

Пользователь подтвердил прежний OWNER reconciliation + observation barrier.
Упрощённый вариант не принят. Правила объяснения пользы до реализации, приоритета
пилота, пересмотра архитектуры и остановки бесконечной диагностики — в AGENTS.md.

| Task / finding | Current status |
|---|---|
| C2-M3.1-NATIVE-CONTEXT-GENERIC-PG-REPAIR-R1 | TODO / ASSIGNED: все88 F1–F9,12 negative controls, CI-11 и полный generic802; точный write-set в HANDOFF |
| C6-M3.1-NATIVE-CONTEXT-STATE-REPAIR-R1 | TODO / ASSIGNED: исправление CI-12; минимальная диагностика внутри задачи, конкретный предел/вариант пересмотра вместо следующего общего отчёта |
| C2-M3.1-NATIVE-CONTEXT-GENERIC-PG-RECONCILE-R1 | HOLD / отдельная report-only выдача заменена REPAIR-R1; готовый анализ используется в исправлении; опубликованный возврат не получен |
| C6-M3.1-NATIVE-CONTEXT-STATE-BUDGET-DIAG-R1 | INTEGRATED как неизменённый отчёт0973cd2… / вход для repair; новая независимая runtime/evidence verification не заявляется |
| C0-NC-CI-06/07/11/12 | OPEN; никакая находка не закрыта данной координацией |
| C0-NC-CI-08/09/10 | Прежние CLOSED dispositions сохранены |
| C1/C3/C5/C8, новые функции, production/merge | HOLD; C2 отдельно разрешены перечисленные C1/C3 test-fixture paths |

Точная общая база — C0 coordination commit/tree из новой выдачи PR34, sole parent
0973cd2bb5376060bb7ebcdd4bf73a3ae5eabf8a. Полные задачи и критерии:
[HANDOFF CURRENT](tasks/M3_HANDOFF.md#current--продолжение-native-context-исправления-вместо-отдельного-цикла-отчётов--2026-10-21).
Последний выполненный RUN6:9SUCCESS/2FAILURE, generic714PASS/88FAIL; PR35 остаётся
OPEN Draft/BLOCKED наfaceef49dc719d1b3c2b7945116794f6737d7b32. Main/stock неизменны.
Новый CI не выполнен. M3 IN_PROGRESS; merge остаётся за пользователем.

---

## History — RUN6 reviewed; diagnostics complete; C2/C6 report scopes / 2026-10-20 UTC

[RUN6 / 39457359784](https://github.com/Elefesys/ai-service-manager/actions/runs/39457359784),attempt1, completed2026-10-20T17:17:04Z:
**9SUCCESS, 2FAILURE**. Approval6295749140 CONSUMED ONCE; one expected-head/force=false
FF, no retry/rerun/dispatch/cancel/source mutation. Tested PR35 headfaceef49dc719d1b3c2b7945116794f6737d7b32,
tree341112cfd977f25441d9f617a2db8580a87dbc42, actual merge6e12ce98f0436c8c33b8b75c62b52ce911eb0068, ordered parents[e205e22051bc06295758b504d84699652b176c15,faceef49dc719d1b3c2b7945116794f6737d7b32].

| Task / finding | Current status |
|---|---|
| C0-M3.1-NATIVE-CONTEXT-CI-RUN6 | COMPLETED/FAILURE; all saved evidence reviewed; diagnostic objective met |
| C6-M3.1-NATIVE-CONTEXT-FAILURE-EVIDENCE-R1 | INTEGRATED / VERIFIED SOURCE+LOCAL UNIT+actual RUN6 recorder; COMPLETE/HOLD |
| C0-NC-CI-10/P2 | CLOSED with actual RUN6 confirmation: every failed phase recorded, no sink issue |
| C0-NC-CI-06/P2 | OPEN: generic802=714PASSED, 88FAILED;0UNKNOWN |
| C0-NC-CI-07/P2 | OPEN:2failed jobs; full generic/tail and all11SUCCESS unmet |
| C0-NC-CI-11/P2 | OPEN: earlier PROVIDER image-helper wrong-job claim remains unrepaired |
| C0-NC-CI-12/P2 | OPEN: Docker29 frozen P material image probe exhausts shared preparation budget |
| C0-NC-CI-08/09/P2 | Prior CLOSED LOCAL states retained; ordinary cleanup/units confirmed |
| C2-M3.1-NATIVE-CONTEXT-GENERIC-PG-RECONCILE-R1 | TODO/ASSIGNED; SOURCE+SAVED EVIDENCE report only, exact one-path scope |
| C6-M3.1-NATIVE-CONTEXT-STATE-BUDGET-DIAG-R1 | TODO/ASSIGNED; SOURCE+SAVED EVIDENCE report only, disjoint one-path scope |
| C1/C3/C5/C8 and all implementation/repair/runtime scopes | HOLD |

Ordinary units: **2144 passed, 907 deselected, 5 warnings, 130 subtests passed in 421.95s (0:07:01)**. Native runner386+130subtests also PASS.
Generic802 has2406 phases/88 bounded diagnostics;
0missing/0issues,evidence_failed=false,original exit1 and strict gates retained.
Prior88={"FAILED": 88};
prior47UNKNOWN={"PASSED": 47}.
All12 potentially vacuous negative cases keep observed PASS; intended-origin
controls remain missing. Complete diagnostic capture does not prove all report
section8 discriminating facts or authorize a generic helper/ten-path repair.
CI-11 comparison and exact failure families: [current HANDOFF](tasks/M3_HANDOFF.md).

Native112/336/105 and167/45/635, browser398+54, durable6/12, Docker29compat6/12,
four image/intent shards and normal state20pairings PASS. Docker29 state fails
at frozen P preparation with10.632304912s remaining, final image probe timeout
0.144769160s; C/G/E and owned cleanup PASS, P tail/later C negatives NOT_RUN.
Source and caps unchanged from RUN5; no Docker29-specific root cause is proven.
Core primary1/cleanup0, full post-generic tailNOT_RUN. All10 artifact hashes,
294current leaves/modes and historical sources verified. Nine explicit ordinary
clean-source gates PASS; Docker29 state's gate SKIPPED after failure, but its
always-run saved clean status/equal source independently verified; native clean PASS.
Original11/manifest remain exact; earlier upload limitation resolved.

Two independent report-only branches start at the exact C0 post-run commit/tree
published in the disposition; full scopes/allowed paths/criteria in HANDOFF.
Neither report grants PG/Docker/Actions, test/code/DDL/CI changes, ref movement,
retry, merge or live work. Return then HOLD for C0. User owns merge.

Only preparation c0/m3-1-native-context-ci-r6 advances with this two-document
coordination. PR35 stays OPEN Draft/BLOCKED atfaceef49dc719d1b3c2b7945116794f6737d7b32; maine205e22051bc06295758b504d84699652b176c15/schema0012
and stockaf7482dede085bc033e3fee34f9a2425124351ee freeze. This coordination is not the tested source.
M3 IN_PROGRESS; D1/D2/D3/prior closures/caps retained, enforcement UNVERIFIED,
IMPL-05 DEFERRED. Historical run outcomes remain unchanged.

---

## History — CI-10 CLOSED LOCAL; C6 accepted; RUN6 prepared, not authorized / 2026-10-20 UTC

C0 accepts [C6 return6294851327](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6294851327)
at **ad89819de5778df32146dff245937e9a205e8265**, treec3e3eee324fe6c1f0fb2856be5dbddbe5aa6f4ab, sole parent
49363b1eed1950446fd242fd9ef7ad32ee5eee58. Two permitted paths,+273/-3;
other292 leaves/all modes exact. Correct actual source DDL record consumption;
unchanged producer/gates/privacy/cleanup and all old assertions.

| Task / finding | Current status |
|---|---|
| C6-M3.1-NATIVE-CONTEXT-FAILURE-EVIDENCE-R1 | INTEGRATED / VERIFIED SOURCE + ISOLATED LOCAL UNIT; COMPLETE/HOLD |
| C0-NC-CI-10/P2 | CLOSED LOCAL; actual new recorder CI confirmation pending; RUN5 diagnostic loss retained |
| C0-M3.1-NATIVE-CONTEXT-CI-RUN6 | PROPOSED/PREPARED, NOT AUTHORIZED, NOT RUN; exact one-use proposal in HANDOFF/comment |
| C0-M3.1-NATIVE-CONTEXT-CI-RUN5 | COMPLETED/FAILURE:10SUCCESS/1FAILURE; approval6292650855 CONSUMED ONCE |
| C0-NC-CI-06/P2 | OPEN: latest actual generic802=713PASS/89FAIL,0UNKNOWN; those failures unfixed |
| C0-NC-CI-07/P2 | OPEN: complete generic/tail and all11SUCCESS unmet |
| C0-NC-CI-11/P2 | OPEN: PROCESS_TURN claimed during PROVIDER image preparation; no repair/authorization-bug inference |
| C0-NC-CI-08/09/P2 | Prior CLOSED LOCAL states retained with RUN5 ordinary cleanup/unit confirmation |
| C1/C2/C3/C5/C8/all implementation and generic repair scopes | HOLD |

Independent C0 RED old formatter20FAIL/3PASS versus corrected23PASS.
Full runner: **386 passed, 2 warnings, 130 subtests passed in 118.01s (0:01:58)**.
Full ordinary: **2144 passed, 907 deselected, 5 warnings, 130 subtests passed in 340.30s (0:05:40)**.
All363 old runner/2121 old ordinary IDs/parameters/order and130subtests retained;
23 additions, no failure/error/skip in complete final JUnit. Ruff/format/compile/diff
PASS. Separate frozen Python3.13.12/uv0.10.0 environment; all58 distributions locked
and imports/editable mapping point to C0 checkout. All182 C6 evidence-manifest
entries, full294-leaf tar, final XML/commands/logs and constructed journals verified.

Own actual nested pytest path persists3 bounded failure records with19case rows,
11phases and unchanged exit1. Failed setup/call/teardown, original nonzero7,
identity/order, descriptor/privacy/frame bounds and actual write/fsync faults are
covered. All6 sink-failure variants keep evidence_failed=true/failed gate;
successfully recorded failed tests still fail execution. Constructed local units
are not PostgreSQL/runtime evidence. Details/hashes: [current HANDOFF](tasks/M3_HANDOFF.md).

Collection only preserves generic802/native112(7source+105PG)/disjoint907/all4
carrier modules. Pure4component pairing167functions/45tables/635columns PASS;
workflow/input hashes and original11/full contract/accepted reports unchanged.

New C0 preparation c0/m3-1-native-context-ci-r6 changes only HANDOFF/register
with sole parent accepted C6; exact final commit/tree appear in the acceptance
proposal. No existing ref moves. PR35 remains OPEN Draft/BLOCKED at
efc1c8af12dfe8b0c4098c2bf6b6d085e1b35f0b; main
e205e22051bc06295758b504d84699652b176c15/schema0012 and stock
af7482dede085bc033e3fee34f9a2425124351ee frozen. RUN5 stays713PASS/89FAIL,
empty failure journal/evidence_failed=true/full tail NOT_RUN; historical outcomes
are not relabeled. C0 prepares one ordinary diagnostic RUN6 to capture those
failures after separate explicit source-specific approval. Existing11 jobs and
all budgets remain; prior RUN5 approval cannot authorize it. No rerun/retry,
execution-ref move, PG/Docker/Actions, repair, merge or live action in this review.
M3 IN_PROGRESS; user owns merge. D1/D2/D3 and previous closures retained;
enforcement UNVERIFIED, IMPL-05 DEFERRED.

---

## History — RUN5 reviewed; CI-10/11 OPEN; C6 recorder correction assigned / 2026-10-20 UTC

[RUN5 / 39435478971](https://github.com/Elefesys/ai-service-manager/actions/runs/39435478971), attempt1, completed2026-10-20T14:50:37Z:
**10SUCCESS, 1FAILURE**. User-confirmed one-use approval6292650855 CONSUMED ONCE;
exactly one expected-head/force=false FF, no rerun/retry/dispatch/cancel.
Tested PR35 head efc1c8af12dfe8b0c4098c2bf6b6d085e1b35f0b, tree 27bf2b804d6e3cf32cb548fd61ac349209b2b0c1, actual merge
f747ca7570a39c4867e145263c4234b8e9504ee8; ordered parents
[e205e22051bc06295758b504d84699652b176c15,efc1c8af12dfe8b0c4098c2bf6b6d085e1b35f0b].

| Task / finding | Current status |
|---|---|
| C0-M3.1-NATIVE-CONTEXT-CI-RUN5 | COMPLETED/FAILURE: 10SUCCESS, 1FAILURE; full saved evidence reviewed |
| C6-M3.1-NATIVE-CONTEXT-UNIT-CLOCK-R1 | INTEGRATED / VERIFIED SOURCE+LOCAL UNIT; ordinary RUN5 unit confirmation; COMPLETE/HOLD |
| C0-NC-CI-09/P2 | CLOSED LOCAL, now also confirmed by actual ordinary RUN5 units |
| C0-NC-CI-08/P2 | CLOSED LOCAL; ordinary RUN4/RUN5 cleanup PASS; journal-loss probe remains local |
| C0-NC-CI-06/P2 | OPEN: generic802 terminal, 713PASSED, 89FAILED; 0 UNKNOWN |
| C0-NC-CI-07/P2 | OPEN: full generic/tail and all11 SUCCESS still unmet |
| C0-NC-CI-10/P2 | OPEN: formatter joins actual DDL dictionaries as strings;89 detailed failure records lost |
| C0-NC-CI-11/P2 | OPEN: PROVIDER generic case claims PROCESS_TURN during image preparation, before HTTP authorization checks |
| C6-M3.1-NATIVE-CONTEXT-FAILURE-EVIDENCE-R1 | TODO/ASSIGNED; SOURCE + ISOLATED LOCAL UNIT only; exact runner + test paths |
| C1/C2/C3/C5/C8/all other implementation and generic repair scopes | HOLD; no generic ten-path/helper repair or new runtime authorization |

Actual ordinary units: **2121 passed, 907 deselected, 4 warnings, 130 subtests passed in 397.72s (0:06:37)**. Generic802 ordered inventory unchanged;
907 integration partition=802+105 remains exact. Prior88 outcomes:
{"FAILED": 88}; prior47 UNKNOWN outcomes:
{"PASSED": 47}. New failed IDs count:
1. Detailed origin/phase limits are in
[current HANDOFF](tasks/M3_HANDOFF.md); complete terminal outcomes do not establish complete failure diagnostics or a
green gate. Full tail=NOT_RUN;
foundation execution={"cleanup_exit": 0, "primary_exit": 1},
issues7498bytes, clean-source PASS.

All802 case outcomes/2406 phases survive, but failures.jsonl is empty and89
EVIDENCE_WRITE_FAILED markers make evidence_failed=true. C0's exact pure
source_catalog -> foundation_failure reproduction gives TypeError at line2416:
717 actual index/revision/sql dictionaries were joined as strings; the unit
fixture had mocked a string list. CI-10 is an independently reproduced recorder
defect. CI-11's saved traceback is ready/image setup before role mutation or
authorization assertions; no product authorization defect is inferred. Both
remain OPEN. All47 previous UNKNOWN and all12 potentially vacuous negatives
have observed PASS; the12 still need intended-origin/positive-control evidence.

Native112/336/105 and167functions/45tables/635columns, runner363+130,
browser398+54, entire durable, Docker29 compatibility and all6 migration shards
PASS. All10 GitHub archive sizes/digests and exact294-file current trees checked;
historical archives, source/schema pairing and owned cleanup verified.

All11 original attachments now available; all17 copies including duplicates
match manifest and docs/architecture byte-for-byte. Prior missing-six limitation
resolved. Originals stay the baseline; task/decision/HANDOFF/status docs evolve.

C6 receives only the two-path recorder correction in HANDOFF and the C0
assignment comment at its exact post-run base/tree. Preserve actual catalog
shape, privacy/frame/record limits, existing nonzero/fault/cleanup behavior,
all363 runner and2121 ordinary cases+130subtests and unchanged inventories.
Require real producer-to-formatter/journal RED-to-GREEN and complete locked
local units. No PG/Docker/Actions or generic/production changes; return then
HOLD. C2 saved-log reconciliation and CI-11 diagnosis are later scopes.

This coordination commit changes only HANDOFF/register on preparation
c0/m3-1-native-context-ci-r5; it is not the tested PR35 source. PR35 remains
OPEN Draft/BLOCKED at efc1c8af12dfe8b0c4098c2bf6b6d085e1b35f0b; main e205e220/schema0012 and
stock af7482dede085bc033e3fee34f9a2425124351ee unchanged. M3 IN_PROGRESS;
user owns merge. D1/D2/D3/prior closures/caps retained, enforcement UNVERIFIED,
IMPL-05 DEFERRED. Later M3/M4 and live/account/deployment scopes remain separate.

---

## History — CI-09 CLOSED LOCAL; C6 accepted; diagnostic RUN5 prepared / 2026-10-20 UTC

C0 accepts [C6 UNIT-CLOCK-R1 return6291541015](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6291541015)
as INTEGRATED / VERIFIED SOURCE + ISOLATED LOCAL UNIT only. Exact accepted commit
1a3295a43434142a0642f473bf5b12b6f0197b2a,tree0b86b377f1fae3812cfb2d6f40c8742abdfaab98,
sole parent86c62f6876b093fc9e0d9306630981e569223810. One test file,+147/-13;
293 other leaves/modes exact. C0's prepared c0/m3-1-native-context-ci-r5 adds only
HANDOFF/register with sole parent accepted C6; exact final commit/tree are in
the C0 acceptance/proposal comment. No execution branch moved by preparation.

| Task / finding | Current status |
|---|---|
| C6-M3.1-NATIVE-CONTEXT-UNIT-CLOCK-R1 | INTEGRATED / VERIFIED SOURCE+LOCAL UNIT; COMPLETE/HOLD |
| C0-NC-CI-09/P2 | CLOSED LOCAL: synthetic unit clocks independent of host epoch; operational guards unchanged |
| C0-M3.1-NATIVE-CONTEXT-CI-RUN5 | PROPOSED/PREPARED; NOT AUTHORIZED / NOT RUN |
| C0-M3.1-NATIVE-CONTEXT-CI-RUN4 | Historical COMPLETED/FAILED:10SUCCESS, foundation unit FAILURE before generic |
| C0-NC-CI-06/P2 | OPEN: RUN3 latest generic667PASS+88FAIL/47UNKNOWN; RUN4 generic NOT_RUN |
| C0-NC-CI-07/P2 | OPEN: full generic/tail and all11 actual SUCCESS not established |
| C0-NC-CI-08/P2 | CLOSED LOCAL; ordinary RUN4 owned cleanup also PASS; journal-loss probe local |
| C2 generic repair; C1/C2/C3/C5/C6/C8 and other implementation tasks | HOLD; no generic repair scope issued |

C0 independent full ordinary unit selector: **2121 PASS +130 subtests PASS,
907 integration deselected,4 warnings,368.71s,exit0** on exact C6 source.
All2103 prior unit IDs preserved in order,+18 additions,runner363 included;
no failed/error/skipped/xfail cases. Independent base RED at0/490.452973924 and
corrected GREEN confirm the same original nodes. C6 complete2121+130/385.07s,
32/32 corrected epoch matrix,144 evidence hashes and exact294-file archive checked.
All171 unrelated definitions, original asserts/decorators/imports/globals,
operational consumers/controllers/clocks/caps unchanged; specific refusal origins
and905.198142485 control preserved. Ruff/format/diff checks PASS.

Generic802/native112 inventories unchanged; constructed source pairing verifies
all4 components/167functions/45tables/635columns. No new Docker/PG/Actions evidence.
Only five originals available this turn were checked as attachments; six failed
to load and are explicitly unverified as attachments. All11 accepted Git copies
match the manifest. [Current HANDOFF](tasks/M3_HANDOFF.md) records exact scope,
commands/results/hashes, missing-attachment limitation and next-run conditions.

RUN5 proposes one expected-head/force=false FF of Draft PR35 execution branch
c0/m3-1-native-context-ci-r1 fromcf9d037dbf605ec01bc81306a546cac54a3f7f91 to the
exact prepared candidate, first automatic synchronize run/attempt1 only, after
new explicit approval and fresh candidate/main/no-active-run checks. RUN4 approval
6290230660 is CONSUMED. No rerun/retry/dispatch/cancel or source change in-run.
Purpose is complete unmodified generic802 diagnostics, including47 UNKNOWN;
88 prior failures are unfixed. All11 jobs and individual caps unchanged:
durable25 then foundation45, native20/payload1080, state/browser/compat25,
S600/P720/fixed120/+480/supervisor1200/cleanup90. No generic repair assignment.

PR35 remains Draft/BLOCKED atcf9d037; main e205e22051bc06295758b504d84699652b176c15/
schema0012 and stockaf7482dede085bc033e3fee34f9a2425124351ee unchanged.
M3 IN_PROGRESS; user owns merge. D1/D2/D3/prior closures retained, enforcement
UNVERIFIED, IMPL-05 DEFERRED; account/live/deploy and later M3/M4 scopes separate.

---

## History — RUN4 FAILED before generic; CI-09 unit clock OPEN / 2026-10-20 UTC

[C0 RUN4](https://github.com/Elefesys/ai-service-manager/actions/runs/39418189410),
attempt1: **10 SUCCESS / 1 FAILURE**, completed12:19:24 UTC. One-use approval
[6290230660](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6290230660)
CONSUMED; no rerun/dispatch/retry/cancel. Tested PR35 head
cf9d037dbf605ec01bc81306a546cac54a3f7f91, merge
9e9e4d617cbbcbab84d8dfbec7698c1a9defb5ef, tree
9dc0f1e70a1b6a29ce9667ebae662a58ad07e11b; ordered parents
[e205e22051bc06295758b504d84699652b176c15,cf9d037dbf605ec01bc81306a546cac54a3f7f91].
Main/stock unchanged; PR35 Draft/BLOCKED; M3 IN_PROGRESS; user owns merge.

| Task / finding | Current status |
|---|---|
| C0-M3.1-NATIVE-CONTEXT-CI-RUN4 | COMPLETED/FAILED:10SUCCESS, foundation FAILURE before generic |
| C6-M3.1-NATIVE-CONTEXT-FOUNDATION-CI-R4 | INTEGRATED/VERIFIED SOURCE+LOCAL; actual durable25min and ordinary failure cleanup pass; complete foundation still blocked |
| C0-NC-CI-08/P2 | CLOSED LOCAL; ordinary actual owned cleanup also PASS, journal-loss probe remains explicitly local |
| C0-NC-CI-09/P2 | OPEN: unit fixture now-601 becomes negative on fresh low-epoch runner |
| C6-M3.1-NATIVE-CONTEXT-UNIT-CLOCK-R1 | TODO/ASSIGNED; sole new source+isolated LOCAL unit scope, one test file; HOLD after return |
| C0-NC-CI-06/P2 | OPEN: RUN4 generic802 NOT_RUN; RUN3 latest755 terminal=667PASS+88FAIL,47UNKNOWN |
| C0-NC-CI-07/P2 | OPEN: executed journals retained, but full generic/tail and all11 SUCCESS not established |
| C2 generic diagnostic / proposed repair | Accepted SOURCE+SAVED DATA; generic ten-test-path+helper write-set remains unassigned/HOLD |
| C1/C2/C3/C5/C8 and other tasks | HOLD |

Foundation unit2102PASS/1FAIL/130subtestsPASS/406.85s. Sole failure is
`test_control_budget_exhaustion_and_file_guards`: expected EXHAUSTED, actual
CONTROL_BUDGET_CLOCK, started_at=-110.54702607600001. C0 exact-source constructed
local probes reproduce the low-epoch defect and separately establish related
now-30/now-430 fixture assumptions. Do not relax operational clock/budget guards.
Full host/backend executed-prefix records persist; primary1/cleanup0,
issues empty, clean-source PASS. All generic sinks empty because generic was
never entered; no new generic verdicts. Native112/336/105/catalog167/45/635,
runner363+130, browser398+54, Docker29 compatibility and all6 migration shards PASS.

[Current HANDOFF](tasks/M3_HANDOFF.md) contains exact job/artifact hashes,
independent source/evidence checks, CI-09 diagnosis and complete C6 scope.
C6 branch c6/m3-1-native-context-unit-clock-r1 starts from the exact C0 docs
commit/tree in its task comment (sole parent cf9 above). Only unit clock fixtures
and directly related tests in tests/test_telegram_egress_migration.py may change;
operational consumers/controllers/clocks/caps, generic/native inventories and
all production/CI files remain fixed. Full locked non-integration validation
preserves2103 old cases+130subtests and inventories additions. No Docker/PG/CI,
execution-ref movement, new PR, merge or external/live action. Later ordinary
CI needs new exact source review and one-use approval; RUN4 grants no retry.

This C0 post-run docs commit is not the tested PR35 source. Earlier closures,
D1/D2/D3, all caps, IMPL-05 DEFERRED and enforcement UNVERIFIED retained.

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

Полные exact scopes/verification: M3_HANDOFF§0.1(C2),§0.2(C6).


## История — Текущий статус — C6 CI-R3/C1 CI-R1 INTEGRATED; C0 RUN3 / 2026-10-19 UTC

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


## История — Текущий статус — RUN2 FAILED; C6 CI-R3/C1 CI-R1 / 2026-10-19 UTC

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

Полные выдачи и критерии: M3_HANDOFF§0.1(C6),§0.2(C1).

## История — Текущий статус — CI-R2 INTEGRATED source; C0 ordinary CI RUN2 / 2026-10-19 UTC

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

Exact execution boundaries: M3_HANDOFF§0.1; all implementation chats HOLD.

## История — Текущий статус — ordinary CI FAILED; C6 CI-R2 / 2026-10-19 UTC

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
| C6-M3.1-NATIVE-CONTEXT-CI-R2 | IN_PROGRESS/source-only; exact4-path task in M3_HANDOFF§0.1 |
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

Exact correction scope and verification: M3_HANDOFF§0.1 and canonical C6 task comment. No new CI execution permission.

## История — Текущий статус — CI-R1 INTEGRATED source; C0 ordinary CI gate / 2026-10-19 UTC

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

Exact C0 execution boundaries: M3_HANDOFF§0.1; all implementation chats HOLD.

## История — native host stock112 PASS; C6 CI-R1 / 2026-10-19 UTC

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

Exact C6 six-path continuation and limits: M3_HANDOFF§0.1; same task and branches.

## История — Текущий статус — C8 review принято; C6 исправляет command-key validation / 2026-10-19 UTC

[C8 review6260761693](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6260761693);
[C0 disposition6260873892](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6260873892).
**C6 HOST-R2 ACTIVE/source-only; C1/C2/C3/C5/C8 HOLD. M3 IN_PROGRESS.**
Один дефект соответствия уже принятому контракту, без нового product scope.

| Task / finding | Current status |
|---|---|
| C8-M3.1-NATIVE-CONTEXT-HOST-CONSOLE-R1 | Review COMPLETE; CHANGES REQUESTED, one confirmed P2; C8 HOLD |
| C8-NC-HOST-01/P2 | OPEN; host policy key grammar narrower than existing command contract; owner C6 |
| C6-M3.1-NATIVE-CONTEXT-HOST-R2 | IN_PROGRESS/source-only; exact two-path task in HANDOFF§0.2 |
| C5 CONSOLE-R1/R2; C6 HOST-R1 | Prior INTEGRATED source retained |
| C0-NC-UI-01/02 | CLOSED LOCAL/TEST retained |
| Native stock5d98651 and prior carrier/runtime closures | INTEGRATED / VERIFIED LOCAL/TEST for that source retained |
| Actual unified host/PG/browser/full integration | NOT VERIFIED / separate C0 gate after correction |
| M3/account/A08/renewal/collector/A12 | IN_PROGRESS / later gates OPEN |

C8 reviewed exact2b1d3cac2c453e1d35242c2c682442625aeefdd9/tree
663277ba89db5aaa743cfd653227dab502fb0593; ordered parents C5
208dd68959d9ee15e4ba9a746cac38d0f1806935 then C6
9bd76b30069617ceadf5e35de046505255600cca. C0 verified all292 bytes/modes/parents/
tree and clean source, then independently reproduced the key defect with3.13.12:
4/9 vector mismatches;66 valid single-ASCII keys versus26 accepted by host DTO.
Probe SHA256dbf890293c791f864a6541f9df6762fb6a54ee21a764c6224dc8c1b064402291.
No DB/CLI called. Saved-request recovery impact is source trace, not actual replay.

C0 checked8 C8 evidence hashes/XML/logs/collection:345 Python PASS(36+82+144+83),
359 frontend PASS/10files, typecheck/build PASS, full Playwright list54=45+9,
compile/Ruff/format13 and mypy64 PASS; native112/host20 collection only.
Pure paired source167functions/45tables/635columns/all4 components PASS.
These are C8 suite executions, not new C0 reruns; actual PG/browser/rollout NOT RUN.
C8 review found one actionable new P2; other reviewed areas and prior closures retained.

New docs-only preparation has sole parent2b1d3cac; only HANDOFF/register,
290 other leaves exact/292 total. Full new SHA/tree in canonical C0 task;
c0/m3-1-native-context-host-r2 and c6/m3-1-native-context-host-r2.
C6 may change only provisioning.py NativePolicyRequest key validation/import and
tests/test_m2_3_setup.py regressions. Shared billing/messaging/SQL/API/frontend/
contracts/locks/CI/runner frozen. Strict key bytes/repr/redaction and recovery
semantics retained. Required local two-unit-module baseline226+new cases,
two-file static checks/mypy64, native112/host20 collection, clean pure source pairing.
Unchanged C8 suites are retained at reviewed source; no repeated unrelated suites.

Old stock105/run39160997284 applies only to5d98651d2c34314724a12283d1741e73594e16b8.
Approval6254432619 consumed once; execution5d98651 unchanged.
Main e205e22051bc06295758b504d84699652b176c15/schema0012; PR34 closed/merged.
No actual PG/services/browser/Actions/full CI/new PR/VM/live/deploy/renewal.
Contract9/Q01/MATERIAL11/D1/D2/D3/allcaps retained; M4 out.
Next: C6 correction→C0 review/closure→separately authorized actual paired gate.
User owns merge.

## История — Текущий статус — C5+C6 INTEGRATED source; C8 independent review / 2026-10-19 UTC

[C0 acceptance6260443971](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6260443971).
**C8 ACTIVE/read-only source review; C1/C2/C3/C5/C6 HOLD. M3 IN_PROGRESS.**
Независимая проверка общего source checkpoint; новых требований к продукту нет.

| Task / finding | Current status |
|---|---|
| Native DB/API/runtime stock5d98651 | Prior INTEGRATED / VERIFIED LOCAL/TEST retained for that source |
| C0-NC-CARRIER-01/02; C3-NC-RUNTIME-01 | CLOSED LOCAL/TEST retained |
| C0-NC-UI-01/P2 | CLOSED LOCAL/TEST: proper Response/APIResponse type; browser JS exact |
| C0-NC-UI-02/P2 | CLOSED LOCAL/TEST: connected double submit, one frozen intent/request, full replacement/current-read proof |
| C5 CONSOLE-R1/R2 | INTEGRATED source; C0 required frontend checks PASS; C5 HOLD |
| C6 HOST-R1 | INTEGRATED source; reviewed source/evidence; C6 HOLD pending actual paired gate |
| C8-M3.1-NATIVE-CONTEXT-HOST-CONSOLE-R1 | IN_PROGRESS/read-only; exact source/evidence/local verification task in HANDOFF§0.2 |
| Actual unified host/PG/browser/full integration | NOT VERIFIED / separate C0 gate after C8 |
| M3/account/A08/renewal/collector/A12 | IN_PROGRESS / later gates OPEN |

Combined source ordered parents C5 208dd68959d9ee15e4ba9a746cac38d0f1806935/tree
b436c1bcb11e0e22c4ca0553dd8527dfc26a0b88 then C6
9bd76b30069617ceadf5e35de046505255600cca/tree8124ef7664434a2e999502daff4b1f5d856bab0f.
All24 C5/12 C6 implementation/test/runbook blobs exact; only2 C0 docs updated.
292 leaves;36 implementation/test/runbook paths+2 coordination docs versus common8d1ba99,
254 old leaves unchanged. Original11/contract/SQL/API/locks/CI frozen.
Full final SHA/tree in canonical C0 task binding; branches
c0/m3-1-native-context-host-console-r2 and c8/m3-1-native-context-host-console-r1.

C5 R2 sole parentc5605521b8b730a3bd1c20b6160e4fb4afe8d204; exactly2files,+31/−5,
290 other leaves retained. C0 verified all292 bytes/modes, independently repeated
typecheck PASS,359Vitest/10files PASS/6.24s, build PASS40modules, full list54=
45desktop+9narrow PASS. Node24.19.0/npm11.9.0 frozen167packages; no lock changes.
Historical R1 typecheck2errors/Vitest358PASS1FAIL retained.
C6 checked report863unit/112nativecollection/20hostcollection is not a new
combined execution; old105 ordered IDs/assertions retained. Actual host/operator/
new runtime readiness and real browser integration NOT RUN.

C8 may perform exact source/profile review, frozen Node checks and four affected
Python unit modules345expected,13changed-Python static checks, native112/host20
collection only. No repository source writes or actual PG/Docker/services/browser/
API/Actions/execution-ref/full CI/new PR/main/live/VM/deploy/renewal/agents.
Pure unified source/component pairing is not activation or deployed-process proof.

Prior actual run39160997284/attempt1 on5d98651d2c34314724a12283d1741e73594e16b8:
105/105/all315phases/51runner+130subtests/98resets/catalog/cleanup/clean PASS.
Approval6254432619 consumed once; execution stays5d98651, no next run/ref permission.
Main e205e22051bc06295758b504d84699652b176c15/schema0012; PR34 closed/merged unchanged.
Contract9/Q01/MATERIAL11/D1/D2/D3/allcaps retained; M4 out.
Next: C8 return→C0 disposition→separately authorized actual paired gates.
User owns merge.

## История — Текущий статус — C5 исправляет два frontend-теста; C6 HOLD / 2026-10-19 UTC

[C0 review6260097657](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6260097657).
**C5 CONSOLE-R2 ACTIVE/source-only; C6/C1/C2/C3/C8 HOLD. M3 IN_PROGRESS.**
Нового product scope нет: два test-only blockers ранее выданной Console-задачи.

| Task / finding | Current status |
|---|---|
| Native DB/API/runtime and prior C2/C3/runner acceptance | INTEGRATED / VERIFIED LOCAL/TEST on accepted stock5d98651 only |
| C0-NC-CARRIER-01/02; C3-NC-RUNTIME-01 | CLOSED LOCAL/TEST retained |
| C6-M3.1-NATIVE-CONTEXT-HOST-R1 | REVIEW/HOLD; C0 source review complete, no new finding; actual paired PG/host verification pending |
| C5-M3.1-NATIVE-CONTEXT-CONSOLE-R1 | REVIEW; required frontend gates FAIL |
| C0-NC-UI-01/P2 | OPEN: browser Response/APIResponse helper mismatch, two TS2345 |
| C0-NC-UI-02/P2 | OPEN: second save() queries a form button removed during pending submission |
| C5-M3.1-NATIVE-CONTEXT-CONSOLE-R2 | IN_PROGRESS/source-only; exactly two test files, current HANDOFF§0.2 |
| Whole host/Console/C8/full integration | NOT VERIFIED; follows corrected source review/consolidation |
| Whole M3/account/A08/renewal/collector/A12 | IN_PROGRESS / later gates OPEN |

C6 source9bd76b30069617ceadf5e35de046505255600cca/tree8124ef7664434a2e999502daff4b1f5d856bab0f;
C5 sourcee9a5dcbf16fd9d3d7824a2c3d3b3628074d3cc79/tree723869324be6f5627a3d1348d32a55c36e7a2dae.
Common parent8d1ba99c820b42c590408d98043e6963743f77a0.
C0 all288/292 blobs/modes and disjoint12/24paths verified; original11,
contracts/SQL/API/locks/CI source frozen. Review combined indexd460c942752983b127c16309e6486916110e6a68
was not published/accepted. Entire frontend exact C5.

C0 actual Node24.19.0/npm11.9.0 restored exact167 locked packages, no source/lock
change: typecheck FAIL2; complete10 Vitest files358PASS/1FAIL/359; build PASS;
full Playwright list54=45desktop+9narrow PASS after supplying private inert
collection inputs. No browser/PG execution. C6 final XML/log digests checked:
863 unit PASS,0fail/error/skip;112 native collection and20host collection,
all old105 IDs/order retained. These are verified C6 report files; C0 Python
recheck NOT RUN because retained3.13 interpreter targets were unavailable.

New preparation: sole parent C5 e9a5dcb, only HANDOFF/register,
290 other leaves exact/292 total; C6 not included. Reviewed repair base only,
not whole-source acceptance. Full SHA/tree supplied by canonical C0 task.
Branches c0/m3-1-native-context-console-r2 and c5/m3-1-native-context-console-r2.
R2 allows npm ci from frozen lock and exact typecheck/10Vitest/build/full list,
only conversation-control.spec.ts and HumanContextPanel.test.tsx edits.
No product change or weakening/skips/retries/budget increases.

Prior run39160997284/attempt1/job117774086948 SUCCESS105/105/all315phases,
51runner+130subtests/98guardedresets/catalog/ownedcleanup/clean retained for
source5d98651d2c34314724a12283d1741e73594e16b8/treea1989f20284c201bfd58bafe12c174544f1eb3c1.
Approval6254432619 consumed once; execution stays5d98651, no rerun/ref permission.
Main e205e22051bc06295758b504d84699652b176c15/schema0012; PR34 closed/merged.
Contract9/Q01/MATERIAL11/D1/D2/D3/allcaps retained; M4 out.
No PG/Docker/services/browser/Actions/full CI/new PR/VM/live/deploy/renewal.
C0 consolidates corrected source then assigns C8/actual gates; user owns merge.

## История — Текущий статус — stock105 PASS; C6 host/operator и C5 Console source-only / 2026-10-18 UTC

[C0 acceptance6254556203](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6254556203).
**C6/C5 ACTIVE; C1/C2/C3/C8 HOLD.** Existing planned contract§16.7/16.9 work;
no new product requirement. M3 IN_PROGRESS.

| Task / finding | Current status |
|---|---|
| Native DB/API/runtime, C2 DB-R3/R4, C3 runtime R1/PG-R2/R3 | INTEGRATED / VERIFIED LOCAL/TEST on full dedicated stock carrier |
| C0-NC-CARRIER-01/P2 | CLOSED: Audit observer and11 formerly blocked runtime cases PASS |
| C0-NC-CARRIER-02/P2 | CLOSED: actual distinct ordinary/marker Turn routes; both timezone cases PASS |
| C3-NC-RUNTIME-01/P2 | CLOSED LOCAL/TEST: five-status UTC6/all-shape strict interoperability PASS |
| C6 runner-R3 | INTEGRATED / VERIFIED scoped runner/catalog/cleanup retained |
| C6-M3.1-NATIVE-CONTEXT-HOST-R1 | IN_PROGRESS/source-only; exact0013 host profile/readiness and policy operator; no activation |
| C5-M3.1-NATIVE-CONTEXT-CONSOLE-R1 | IN_PROGRESS/source-only; accepted owner context/Resume flow and paired TS readers |
| Whole host/Console integration, C8/full CI | NOT VERIFIED / separate next gate after both returns |
| Whole M3/account/renewal/collector/A12 | IN_PROGRESS / later gates OPEN |

Run39160997284/attempt1/job117774086948 SUCCESS/all13 steps SUCCESS.
Exact5d98651d2c34314724a12283d1741e73594e16b8/treea1989f20284c201bfd58bafe12c174544f1eb3c1:
105/105 (7+56+12+30),315 phase reports PASS,0skip/xfail/deselection;
51 runner+130subtests PASS/5.130s; native549.027s/receipt579.043s within20m.
C0 independently checked288 source bytes/modes, all105 ordered IDs/98 guarded
resets/actual LOGIN roles, fresh167 functions/45 tables/635 columns/ACL, cleanup/
finalclean. Full profile c045a59f86201a244ed0d43fbe22aa8cd72fddd346d770706c6ab3b92ee9a411.
Artifact12149291601,38 files,3034275 bytes,expires2026-10-25;
ZIP SHA25606553fcec3c0b6408c9061bcf4305b03721c0fad80ee5823a389523c0879f6a8.
Historical39154853068 FAIL92/105 retained. Approval6254432619 consumed once;
execution stays5d98651, no further ref/run permission. Current foundation0012
refusal on actual0013 is retained historical evidence, not new-host acceptance.

New docs-only preparation sole parent5d98651; only HANDOFF/register,
286 other leaves unchanged. Full exact tasks/allowlists are current HANDOFF§0.2/§0.3.
Branches c0/m3-1-native-context-host-console-r1,
c6/m3-1-native-context-host-r1, c5/m3-1-native-context-console-r1 use the same
new exact prepared SHA/tree supplied in canonical comments; no moving sibling base.
C6 explicitly owns the two named readiness-test exceptions plus appended host
cases; all other current native cases/assertions frozen. C5 owns TS/UI/browser
fixture source only. Both retain old behavior and report actual local verification;
source-only cannot be reported as actual PG/browser/host rollout PASS.

Main e205e22051bc06295758b504d84699652b176c15/schema0012, PR34 closed/merged unchanged.
No services/PG/browser/Actions/execution ref/full CI/new PR/VM/provider/S3/LLM/
live/deploy/renewal/other agents in these tasks. No0014/applied migration changes.
C0 combines/reviews then assigns C8/real gates; user owns merge.
Contract9/Q01/MATERIAL11/prior closures/D1/D2/D3 and caps preserved; M4 out.

## История — Текущий статус — исправления тестов объединены; полный stock gate впереди / 2026-10-18 UTC

[C0 source acceptance6254398312](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6254398312).
C2 DB-R4 d694e24638ae133fe9412b3f7cde73acb0089be3 и C3 PG-R3
e4ac5afa12174317b39097de042f131f5820cb74 INTEGRATED source.
**C1/C2/C3/C5/C6/C8 HOLD. M3 IN_PROGRESS; native application/runtime NOT VERIFIED.**
No new product scope: two PG files,+43/−3; only assigned two C2 definitions
and one C3 Audit key. Complete old prefixes/AST/assertions/105 node IDs retained.
C0 merge ordered parents C2 then C3; exact final SHA/tree is in canonical approval.
Only accepted source plus HANDOFF/register;284 other leaves unchanged,288 total.

| Finding / gate | Current status |
|---|---|
| C0-NC-CARRIER-01/P2 | OPEN/source-addressed: Audit order key corrected |
| C0-NC-CARRIER-02/P2 | OPEN/source-addressed: distinct ordinary/marker Turns |
| C3-NC-RUNTIME-01/P2 | OPEN: full corrected UTC6 actual matrix pending |
| C6 runner-R3 | Prior INTEGRATED/VERIFIED scoped runner/catalog/cleanup retained |
| Corrected whole stock | NOT RUN; separate exact one-use C0 approval required |
| Host/schema/operator/C5/C8 | HOLD; foundation deliberately remains0012 |
| Whole M3 / account/renewal/collector/A12 | IN_PROGRESS / later gates OPEN |

C0 source audit:288 remote blobs/modes per return,287 other leaves unchanged;
original11/contract769072/57 frozen distributions/current imports exact.
Compile/Ruff/format2/whitespace PASS.105 collect-only in3.65s =7+56+12+30;
all98 actual PG fixture consumers guarded; ordered LF inventorySHA256
9881ab5a77aca51a7d6c66737c352055cd4f037acf156e55f265cedeabb24b1a unchanged.
Fresh source catalog identical to accepted167 functions/45 tables/635 columns,
all10 observer table/key pairs checked; no local PG/service or full-suite recount.

Next: one separately approved full existing stock workflow from execution
2fc3f1491321456e280c01852c7747e0ffdf9139; old approval6253600648 consumed.
Full105 cases/all phases and51 runner+130subtests, fresh independent catalog,
actual LOGIN roles/reset/ownership, cleanup/clean source required;20m cap retained.
Historical39154853068 FAIL92/105 and artifact12146143735 remain historical facts.
Expected unchanged SQL full profile c045a59f86201a244ed0d43fbe22aa8cd72fddd346d770706c6ab3b92ee9a411
must be measured again. No automatic closure from source checks.

Main e205e22051bc06295758b504d84699652b176c15/schema0012 and PR34 closed/merged
unchanged; no0014/applied migration edit, full CI/new PR/VM/live/deploy/renewal.
All prior closures/Contract9/Q01/MATERIAL11/D1/D2/D3/budgets retained.
Exact scope in current HANDOFF§0. User owns merge.

## История — Текущий статус — stock FAIL; два адресных исправления тестов / 2026-10-18 UTC

[C0 disposition6253741115](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6253741115).
**C2/C3 ACTIVE по source-only corrections; C1/C5/C6/C8 HOLD.**
Новых требований к функции нет; это две ошибки test setup/observer.
M3 IN_PROGRESS; native application/runtime NOT VERIFIED.

| Task / finding | Current status |
|---|---|
| C3 runtime R1 / C2 DB-R3 / C3 PG-R2 | INTEGRATED source; actual combined evidence incomplete |
| C6 runner-R3 | INTEGRATED / VERIFIED scoped runner/catalog/cleanup; C6 HOLD |
| C0-NC-CARRIER-01/P2 | OPEN; wrong Audit ordering column blocks11 C3 cases |
| C0-NC-CARRIER-02/P2 | OPEN; escalation-marker fixture requests missing guarded Job;2 C2 cases |
| C3-NC-RUNTIME-01/P2 | OPEN/source-addressed; positive UTC6 wrapper+vectors PASS, full matrix blocked |
| C2-M3.1-NATIVE-CONTEXT-DB-R4 | IN_PROGRESS; one PG file, only manual-history helper and timezone test |
| C3-M3.1-NATIVE-CONTEXT-RUNTIME-PG-R3 | IN_PROGRESS; one runtime PG file, only runtime_effects Audit map value |
| Corrected full stock retry | NOT AUTHORIZED; requires both returns, C0 review/consolidation and exact new approval |
| Host/schema/operator/C5/C8 | HOLD; readiness remains0012 |
| Whole M3 | IN_PROGRESS; A08/P01/P05/account/renewal/collector/A12 OPEN |

Actual run39154853068/attempt1/job117755853170 on
2fc3f1491321456e280c01852c7747e0ffdf9139/tree127e40091cf40cf8602c89eaf72833bae84d6044:
**FAIL92/105** =source7PASS, DB54PASS/2FAIL, API12PASS, runtime19PASS/11FAIL.
All105 called,105 setup+105 teardown PASS;0skip/xfail/deselection.
Runner51 tests+130subtests PASS. Native542.983s,receipt573.957s within20m.
Exact source, actual LOGIN roles/98 guarded resets, independent catalog,
foundation0013 refusal, owned cleanup and clean source PASS; whole-run FAIL retained.
Strict UTC6 wrapper, two UTC6 vector cases and three new JSONB/Unicode cases PASS
do not stand in for the13 blocked scenarios.

C0 artifact12146143735:39 files/3238146 bytes, ZIP SHA256
0dddf0eae3fd9837ca56c1e745cba4c89f99c4917b2c4ebbe2f0d927918e2a05.
All288 bytes/modes and source/manifest hashes exact. Fresh independent167 typed
function/OID/45 table/635 column/security/ACL comparison PASS.
Corrected installed full profile
c045a59f86201a244ed0d43fbe22aa8cd72fddd346d770706c6ab3b92ee9a411;
nonfunction57e03fe369be4bd03116ce380e37a9b447a2bc1a72e3bbf2a70c7ac08d69e370.
C0 source review missed the two test fixture mistakes; no production change is
authorized to work around them.

New C0 docs-only preparation sole parent2fc3f14; only HANDOFF/register,
286 other blobs/modes unchanged. Exact SHA/tree in the canonical tasks.
Branches: c0/m3-1-native-context-stock-followup-r1;
c2/m3-1-native-context-db-r4; c3/m3-1-native-context-runtime-pg-r3.
Full exact scopes are in current HANDOFF§0.3/§0.4. Retain all105 node IDs,
C2 old121779-byte prefix and C3 old12965-byte prefix, all assertions and other ASTs.
All production/SQL/contract/runner/workflow/lock/original11 files remain frozen.
No PG/services/lab/Actions/execution ref/full CI/new PR/main/VM/live/renewal in tasks.

Execution remains2fc3f14; approval6253600648 consumed, no retry.
Main e205e22051bc06295758b504d84699652b176c15/schema0012; PR34 closed/merged.
C1-NC-DB-01/02 and C0-NC-RUNNER-01 prior closures retained; Contract9/Q01,
MATERIAL11, D1/D2/D3 and caps unchanged. M4 out, IMPL-05 deferred; user owns merge.


## История — Текущий статус — native source объединён; один stock gate впереди / 2026-10-18 UTC

[C0 source acceptance6253565474](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6253565474).
**C1/C2/C3/C5/C6/C8 HOLD. C0 готовит отдельное точное разрешение одного stock-прогона.**
M3 IN_PROGRESS; actual corrected PG/interop NOT RUN at preparation.
Native application/runtime NOT VERIFIED; C3-NC-RUNTIME-01/P2 remains OPEN.

| Task / gate | Current state |
|---|---|
| C3-M3.1-NATIVE-CONTEXT-RUNTIME-PG-R2 | INTEGRATED source;14 appended PG cases, old16 runtime cases untouched; C3 HOLD |
| C6-M3.1-NATIVE-CONTEXT-DB-STOCK-RUNNER-R3 | INTEGRATED source; four full modules, complete phase evidence and shared reset guard; C6 HOLD |
| C3 runtime R1 / C2 DB-R3 | INTEGRATED source; actual combined PG/interop pending |
| C3-NC-RUNTIME-01/P2 | OPEN / addressed in source; actual UTC6/strict Python acceptance required |
| Combined local evidence | 58 PASS+130 subtests; Ruff/format3/compile/whitespace PASS |
| Final complete collection | 105 only =7 source+56 DB PG+12 API PG+30 runtime PG; all91 prior nodes retained |
| Corrected stock run | NOT RUN; requires separate exact one-use C0 approval |
| C1-NC-DB-01/02; C0-NC-RUNNER-01 | CLOSED; historical scoped evidence retained |
| Host/schema pairing, operator/C5/C8 | HOLD / later gate; foundation readiness remains0012 |
| Whole M3 | IN_PROGRESS; A08/P01/P05/account/renewal/collector/A12 OPEN |

C3 accepted33146375886f99f6eeff7db4ab92f0e162e6520e,
tree43156c62b869d674de5a201d2a3a2dee32d4e025: one path+783/−0,
12965-byte original prefix and all32 original AST nodes exact.
C6 accepted397389b77f331ef78c5cafe37feffe42959e136f,
tree4748746ffc95fc1f6b932ac4c8a5bee4d9c54a24: two paths+371/−8,
40 old runner tests/78 subtests retained;11 tests/52 subtests added.
Both sole parents64e6a13f52904507368f88f981947d5d41250c08.
C0 merge ordered parents C3 then C6;3 source paths+1154/−8 plus2 C0 docs,
283 other blobs/modes unchanged,288 total. Exact commit/tree in canonical approval.

C0 local58 PASS+130 subtests/7.62s;105 collected/5.77s, not PG execution.
Actual collected98 PG FixtureDefs share one guarded native fixture/reset.
Node-list SHA256 (LF terminated)9881ab5a77aca51a7d6c66737c352055cd4f037acf156e55f265cedeabb24b1a.
Python3.13.14,57 frozen external distributions, current imports, all11 originals verified.
No new product scope or confirmed production finding; only assigned evidence preparation.

The future run must use one unchanged20m stock job, all105 final cases and full51
runner tests, independent167-function/45-table fresh catalog and owned cleanup.
Execution branch staysbde0c48af74f23cd6430fc669ea4635e21aa68c6 until exact approval;
historical39141370282 SUCCESS57/57 verifies onlybde0c48, approval6251780231 consumed.
Corrected full installed profile unknown. Full contract769072 bytes SHA256
fe2eb4ef2469ccb14b7147017c3c81066cde1b8a6ad60acbf73922a15e3ace5f unchanged.
No service/lab reuse, source amendment, selected retry, full CI/new PR/main/VM/
provider/send/deploy/renewal or readiness expansion is authorized by this register.
Main e205e22051bc06295758b504d84699652b176c15/schema0012; PR34 closed/merged.
Contract9/Q01, MATERIAL11, D1/D2/D3 and caps retained; M4 out, IMPL-05 deferred.
User owns merge. Later material scope or owner workflow changes must be explained
explicitly; test/run counts are evidence and do not define product scope.


## История — Текущий статус — C1/C2 приняты; C3 PG tests и C6 runner R3 ACTIVE / 2026-10-18 UTC

[C0 disposition6253081736](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6253081736) принимает
[C1 scoped review](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6252871772) и
[C2 UTC6 source correction](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6252983496).
**C3/C6 ACTIVE только по новым source-only задачам; C1/C2/C5/C8 HOLD.**
**Один C3-NC-RUNTIME-01/P2 OPEN / addressed in source. Actual corrected PG NOT RUN.**
M3 IN_PROGRESS; native application/runtime NOT VERIFIED.

| Task / finding | Current state |
|---|---|
| C1-M3.1-NATIVE-CONTEXT-RUNTIME-REVIEW-R1 | COMPLETE / scoped source PASS accepted; no additional confirmed finding; C1 HOLD |
| C3-M3.1-NATIVE-CONTEXT-RUNTIME-R1 | INTEGRATED in consolidated C0 source checkpoint; actual runtime verification pending |
| C2-M3.1-NATIVE-CONTEXT-DB-R3 | INTEGRATED in consolidated C0 source checkpoint; correction source accepted, actual PG pending; C2 HOLD |
| C3-NC-RUNTIME-01/P2 | OPEN / addressed in source; closes only after actual corrected PG/interop accepted by C0 |
| C3-M3.1-NATIVE-CONTEXT-RUNTIME-PG-R2 | IN_PROGRESS; append-only one runtime PG test file for three C1 evidence gaps |
| C6-M3.1-NATIVE-CONTEXT-DB-STOCK-RUNNER-R3 | IN_PROGRESS; two runner/test paths, complete four-module coverage and retained guards |
| Current new PG evidence | 91 collected only =7 source+56 DB PG+12 API PG+16 runtime PG; actual corrected execution NOT RUN |
| C1-NC-DB-01/02; C0-NC-RUNNER-01 | CLOSED; prior accepted source/stock evidence retained |
| C5/C8 and C6 host/schema/operator work | HOLD / later gates after consolidated reviewed source and actual stock evidence |
| Contract R2 / MATERIAL | Contract9 CLOSED/Q01 RESOLVED; MATERIAL11 INTEGRATED/VERIFIED LOCAL/TEST |
| Whole M3 | IN_PROGRESS; A08/P01/P05/account/renewal/collector/A12 OPEN |

Accepted C2 head **15a8ea7a12f01644250315e26d3d6c5cc487b59e**,
tree **3fc15bdb8c9d475c94c94e5e12cce2b059fedfc6**, sole parent
**73eaeed87cb8c9caf7a6256ba8c246f25e059621** /tree4a02292219cb9219a56772a7a7c7be0ece7e0039.
C1 reviewed immutable **225879990011f2e41f4c38e46308ffdd976a7393** /
tree57009c4990345768badb912c1c3ff0818edb4650, not the later C2 correction.

C0 independently verified4 paths,+564/−5, all288 bytes/modes/commit/tree,
284 unchanged blobs, clean/diff PASS. Source tar SHA256
**cad5d1705b2754abc7ddfa59fdeafc712653609bd9fd228b679746d28452bb32**.
Actual local **47 PASS+78 subtests /4.35s** (7 source/codec+40 runner),
Ruff/format3 PASS; **91 collected only /4.73s**. Python3.13.14/57 frozen external
distributions and actual import path verified. C2's222 and C1's38 targeted cases/
10 literal vectors remain separately attributed source evidence, not PG.

Only UTC6 projection + paired nested validator + generated profile bodies changed;
164 other functions and all signatures/metadata/ACL/nonfunction DDL/columns unchanged.
955 commands/167 functions/45 tables;0013=198 batches/53 final definitions,
35 additions/18 replacements. Source body hashes:
projection8d38da64c526acb61365aa06eb293d117e1d8af93b598b5a507da3a23bc17b51;
validator21492e85adeaf186bce6bbfdde7b89c8e70762c56f8ec28c6da54b3a5327f49c;
verifier527fce5681d5345369cd88b555a302df6d305ef8566cf12a666198eb64a6f4ac.
Nonfunction57e03fe369be4bd03116ce380e37a9b447a2bc1a72e3bbf2a70c7ac08d69e370
retained; new installed full profile unknown pending actual comparison.

Original11/19 ORIGINAL/applied0001–0012 retained. Contract old756397-byte prefix exact,
new full769072 bytes/SHA256
**fe2eb4ef2469ccb14b7147017c3c81066cde1b8a6ad60acbf73922a15e3ace5f** frozen.
Old121779-byte native PG prefix and all28 C3 cases unchanged. New C3 task explicitly
authorizes only append to runtime PG file, preserving12965-byte prefix/SHA256
30fc57c7a69521130faedc48da7d8d90766d7e9deb940a691fc4ce03da746a1f.

C2 lab attempts stopped before asm_test/bootstrap/roles/reset/migrations/pytest
at ownership checks; normal cleanup not attested. No PG/stock/cleanup PASS claimed.
New tasks do not authorize further lab startup/reuse/repair/cleanup or guard bypass.

C3 fills three concrete actual-evidence gaps: remaining boundary HOLD/exhaustion,
committed send-begin ACK loss/work-replay miss/conservative UNKNOWN, and actual
SQL→Python JSONB/digest including Unicode/material/File. No new product defect ID.
C6 extends existing two-module runner to all four complete modules and proves
guarded shared reset/failure propagation; workflow, image, deps,20m cap unchanged.
Starting91 must grow with appended C3 cases; no fixed ceiling or selected subset.
Full exact scope in current HANDOFF§0 and canonical PR34 tasks.

| Branch | Purpose / exact base |
|---|---|
| c0/m3-1-native-context-pg-prep-r1 | C0 docs-only descendant of15a8ea7a; full preparation SHA/tree in canonical tasks |
| c3/m3-1-native-context-runtime-pg-r2 | Same prepared SHA/tree; one append-only test path |
| c6/m3-1-native-context-db-stock-runner-r3 | Same prepared SHA/tree; two existing runner/test paths |
| c2/m3-1-native-context-db-r3 | Returned15a8ea7a; HOLD |
| c1/m3-1-native-context-runtime-review-r1 | Reviewed2258799; HOLD |

C0 preparation changes ONLY HANDOFF/REGISTER,286 other blobs/modes exact.
C0 consolidates both returns before separate actual stock execution approval.
Main **e205e22051bc06295758b504d84699652b176c15/schema0012**, execution
**bde0c48af74f23cd6430fc669ea4635e21aa68c6** unchanged; PR34 closed/merged.
No current Actions/ref movement/service startup/full CI/new PR/VM/provider/live/deploy.

Historical run39141370282 SUCCESS57/57,40 runner+78 subtests/catalog/roles/reset/
cleanup/source PASS stays scoped to bde0c48; old39136349844 remains FAIL.
C6 later host/source/schema/operator pairing, C5 TS/UI, C8/full CI/user merge pending;
foundation0012 refusal retained. D1/D2/D3/caps retained, M4 out/IMPL-05 DEFERRED.
No0014 or in-place reapplication to used0013 DB. Earlier blocks are historical.

<a id="текущий-статус--c3-review-c1-review-и-c2-utc6-r3-active--2026-10-18-utc"></a>

## История — C3 REVIEW; C1 review и C2 UTC6 R3 ACTIVE / 2026-10-18 UTC

[C0 disposition6252562993](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6252562993)
по [C3 return6252466443](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6252466443).
**C3 source/scope ACCEPTED FOR REVIEW. Один новый C3-NC-RUNTIME-01/P2 OPEN.**
C1 и C2 ACTIVE по отдельным canonical tasks; C3/C5/C6/C8 HOLD.
M3 IN_PROGRESS; native application/runtime NOT VERIFIED; actual new PG NOT RUN.

| Task / finding | Current state |
|---|---|
| C3-M3.1-NATIVE-CONTEXT-RUNTIME-R1 | REVIEW; exact source accepted for independent review, no application integration/verification; C3 HOLD |
| C3-NC-RUNTIME-01/P2 | OPEN: raw SQL recent.delivery.completed_at fails strict UTC6 DTO; producer + paired nested validator correction assigned to C2 |
| C2-M3.1-NATIVE-CONTEXT-DB-R3 | IN_PROGRESS; exactly four existing paths; two semantic SQL bodies + generated verifier, focused regressions, append-only contract receipt |
| C1-M3.1-NATIVE-CONTEXT-RUNTIME-REVIEW-R1 | IN_PROGRESS; independent read-only review of exact C3 SHA, no repository write paths |
| C1-NC-DB-01/P2; C1-NC-DB-02/P2 | CLOSED; retained Resume priority/mapping correction and stock evidence |
| C0-NC-RUNNER-01/P2 | CLOSED; explicit TEST child, real Settings checks and actual foundation refusal PASS |
| C2 DB-R2 / C6 runner R2 | Retained INTEGRATED/VERIFIED scoped DB/runner checkpoint bde0c48…; corrected SQL will require new evidence |
| New API/runtime PG carriers | 28 collected only (12 API + 16 runtime); actual execution NOT RUN, C3 environment BLOCKED |
| C5/C6/C8 | HOLD; coherent host/schema/operator, TS/UI and final integration gates need later exact assignments |
| Contract R2 / MATERIAL | Contract 9 CLOSED, Q01 RESOLVED; MATERIAL 11 INTEGRATED/VERIFIED LOCAL/TEST |
| Whole M3 / native application | IN_PROGRESS / NOT VERIFIED; A08/P01/P05/account/renewal/collector/A12 OPEN |

C3 source **225879990011f2e41f4c38e46308ffdd976a7393**,
tree **57009c4990345768badb912c1c3ff0818edb4650**, sole parent
**ad1e28fc69179398a9dc6ca31ee91c32cdf512d3**.
22 paths, 16 existing + 6 authorized NEW, +6162/−1092; 288 blobs, 266 unchanged.
C0 reconstructed all bytes/modes and exact commit/tree; clean/diff --check PASS.
Source tar SHA256 **6c53901982fe6836534efe603f0608754afc8048eb3b3c9c00a2bec36bd71af2**.
C0 local **222 PASS / 10.62s**, no skip/xfail; Mypy 64/Ruff+format 69/current-source
OpenAPI --check PASS. PG **28 collected only / 7.60s**. An initial C0 export used an
old editable package; verified current PYTHONPATH fixed comparison, no product defect.

One P2 combines new native projection raw b.completed_at and its overly broad nested
V3 SQL validator. C0 verified PostgreSQL REL_18_6 serialization source and strict
re-signed Python regression; no actual PG observation is claimed. Reachable completed
manual delivery → recent tail → R/Resume/new Turn rejects V3 before consume/send.
Existing strict real-wrapper UTC6 regression remains unmodified/collected.

C0 explicitly authorizes correction inside **unmerged0013←0012**, no0014.
C2 write paths ONLY migrations/versions/0013_native_context.py,
tests/test_m3_1_native_context_migrations.py, tests/test_m3_1_native_context_postgres.py,
docs/tasks/M3_CONTRACT.md append-only§16.19+. Preserve contract756397-byte prefix
SHA256 **e7f3796fcff8640ffca203266ecf7b5988f7ab1bd24850b12e923122abf5d281**.
Only human_context_projection and nested completed_at validation in
human_context_snapshot_valid may change semantically, plus deterministic
human_context_schema_profile generation. 167 functions/45 tables/955 commands,
35 additions/18 replacements, nonfunction
**57e03fe369be4bd03116ce380e37a9b447a2bc1a72e3bbf2a70c7ac08d69e370**
and all other bodies/DDL/ACL/roles/RLS frozen. Preserve original 57 cases and C3 28 files;
append meaningful regressions; no shared parser widening or source-freeze weakening.
Applied0001–0012 and ORIGINAL bodies frozen. No in-place change of a used0013 DB;
fresh owned LOCAL/TEST only. P2 remains OPEN pending C0 source + actual corrected
PG/interop acceptance. Full task detail in current HANDOFF§0 and canonical PR34 tasks.

C0 preparation has sole parent225879990011f2e41f4c38e46308ffdd976a7393;
ONLY HANDOFF/REGISTER change, 286 other blobs/modes exact. Full preparation SHA/tree
and published task links are in canonical C0 PR34 comments after creation.

| Branch | Exact purpose / start |
|---|---|
| c0/m3-1-native-context-runtime-followup-r1 | Current docs-only instruction snapshot |
| c2/m3-1-native-context-db-r3 | Same prepared start; correction owner C2 |
| c1/m3-1-native-context-runtime-review-r1 | Code target225879990011f2e41f4c38e46308ffdd976a7393/tree57009c4990345768badb912c1c3ff0818edb4650; read current instructions separately |
| c3/m3-1-native-context-runtime-r1 | Returned2258799; C3 HOLD |

[Retained stock acceptance](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6251867599):
source **bde0c48af74f23cd6430fc669ea4635e21aa68c6** /
tree **f2be86c21f754e7997aa4a04ee07d0952fefe940**;
[run39141370282/attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/39141370282)
SUCCESS57/57 native (5 source + 52 PG), 40 runner + 78 subtests, full catalog/roles/
reset/cleanup/clean and actual foundation0013 refusal PASS. Historical first run
39136349844 remains FAIL56/57. This checkpoint does not prove new wrappers or future
corrected SQL; consumed approval grants no repeated execution.

Main **e205e22051bc06295758b504d84699652b176c15/schema0012** unchanged;
execution ref remainsbde0c48…; PR34 closed/merged. Foundation delta only two route
wiring lines; readiness0012/Settings/serve unchanged. Original 11, frontend,
runner/workflow/operator, dependencies/locks and all fixed caps preserved.

C0 first consolidates C1+C2 returns, then separately assigns complete native + new
API/runtime stock execution and independent changed catalog. C6 host/schema/operator,
C5 TS/UI, C8/full CI/user merge remain later. D1/D2/D3 limits retained; M4 outside scope,
IMPL-05 DEFERRED. No Actions/ref movement/full CI/new PR/VM/provider/live/deploy/renewal
or other chat/agent launch. Earlier sections are history, not active assignments.

<a id="текущий-статус--stock-db-verified-c3-native-runtime-r1--2026-10-18-utc"></a>

## История — stock DB VERIFIED; C3 native runtime R1 / 2026-10-18 UTC

[C0 disposition](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6251867599) и [source approval](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6251780231).
**Все три текущих DB/runner P2 CLOSED; C3 implementation ACTIVE по canonical task.**
M3 IN_PROGRESS; native application/runtime NOT VERIFIED. DB checkpoint evidence
не является acceptance Python/API/worker/host/Console или разрешением merge/deploy.

| Task / finding | Current state |
|---|---|
| C1-NC-DB-01/P2; C1-NC-DB-02/P2 | CLOSED; corrected priority/Resume mapping confirmed again by all5 stock regressions |
| C0-NC-RUNNER-01/P2 | CLOSED: explicit TEST child +real Settings tests +actual foundation0013 refusal PASS |
| C2-M3.1-NATIVE-CONTEXT-DB-R2 | INTEGRATED in C0 checkpoint; VERIFIED scoped stock DB; C2 HOLD |
| C6-M3.1-NATIVE-CONTEXT-DB-STOCK-RUNNER-R2 | INTEGRATED/VERIFIED scoped; COMPLETE/HOLD |
| C6 runner R1 / first run39136349844 | Historical source superseded; actual FAIL56/57 remains FAIL |
| Corrected run39141370282/attempt1 | SUCCESS:57/57 native,40runner+78subtests,167functions/45tables/cleanup/clean PASS |
| C3-M3.1-NATIVE-CONTEXT-RUNTIME-R1 | IN_PROGRESS; Python/API/V3/worker/Audit, exact37-path allowlist in HANDOFF§0/canonical task |
| C1/C2/C5/C6/C8 | HOLD; C1 source review,C6 host/operator,C5 TS/UI,C8/full CI later exact assignments |
| Contract R2 / MATERIAL | Contract9 CLOSED/Q01 RESOLVED; MATERIAL11 INTEGRATED/VERIFIED LOCAL/TEST |
| Whole M3 / native application | IN_PROGRESS / NOT VERIFIED; A08/P01/P05/account/renewal/collector/A12 OPEN |

Executed source **bde0c48af74f23cd6430fc669ea4635e21aa68c6**,
tree **f2be86c21f754e7997aa4a04ee07d0952fefe940**, sole parente7c2730… .
[Run39141370282](https://github.com/Elefesys/ai-service-manager/actions/runs/39141370282),
job117716323052: all13 steps SUCCESS;57native=5source+52actualPG,0skip/xfail/deselection.
Runner40 testcases+78subtests (JUnit tests118 includes subtests),2.50s.
Payload329.164s; receipt358.535s within unchanged20m. Actual Settings TEST and
RuntimeDatabase.check schema0013 refusal reached/PASS; first run remains FAIL.

Pinned stock PG18.6/vector0.8.6/btree_gist1.8; Python3.13.16/uv0.10.0/frozen lock.
Actual logins/roles/52reset proofs/independent167 unique functions+45tables/catalog/
owned cleanup/clean source PASS. All282 archived bytes/modes matched C0-approved source.
Full profilec8a335b808f11b0c6f3d784731ddc95bf1023e6f1881aff5448659388f927a7a,
nonfunction57e03fe369be4bd03116ce380e37a9b447a2bc1a72e3bbf2a70c7ac08d69e370,
verifier bodyd485135ecccf986a2b16e71dd451f95508847bb455f8fbf987cf5092ec5de8a6.

[Artifact12142480040](https://github.com/Elefesys/ai-service-manager/actions/runs/39141370282/artifacts/12142480040),
2932595bytes/37files,expires2026-10-25; ZIP SHA256
a1177528f52e11d26e769a4d1da865944415018277d0ce6e2ad898a76d7e1406.
Source tarc1031b8dcd64372047dafce60c069b60f0e89e2d825cd9b3132e6f72daa4bbb2;
manifest315a8f29df3a9ec3b12a6f949ae9f43f6d36224d88c8fcfc3c60c8e8284bc6ba.
Full evidence/scope:[HANDOFF§0](tasks/M3_HANDOFF.md#0-текущая-выдача-c0--native-runtime-r1-после-stock-db-pass--2026-10-18-utc).

C0 preparation sole parentbde0c48…; ONLY HANDOFF/REGISTER changed,280 source blobs
unchanged. Full prepared start SHA/tree in canonical PR34 task. Branches:
c0/m3-1-native-context-runtime-prep-r1 and c3/m3-1-native-context-runtime-r1.
C3 exact31 existing+6NEW paths, including three native modules and separate
unit/API/runtime PG carriers. Existing native57/SQL/runner/workflow unchanged.
Shared foundation.py authorized ONLY route wiring; schema0012/Settings/readiness
remain unchanged until separate C6 coherent host/schema pairing. OpenAPI generated;
TS/UI still later/unpaired. Source checkpoint is not application rollout.

Main e205e22051bc06295758b504d84699652b176c15/schema0012 unchanged;
execution and C6R2=bde0c48… frozen; old candidatebbc3d42…/deliveries historical.
No0014/applied migration edits; full contract756397bytes/SHA256
e7f3796fcff8640ffca203266ecf7b5988f7ab1bd24850b12e923122abf5d281/original11 frozen.
C3 return REVIEW→HOLD; C0 review then separately scoped C1/C6/C5, C8/full CI/user merge.
No Actions/new PR/full CI/VM/provider/send/deploy/renewal/other agent launches.
D1/D2/D3 limits and all caps retained;M4out,IMPL-05DEFERRED. Earlier blocks are history.

<a id="текущий-статус--stock-db-fail-c6-runner-r2--2026-10-18-utc"></a>

## История — stock DB FAIL; C6 runner R2 / 2026-10-18 UTC

[C0 source approval](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6251106119),
[actual run disposition](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6251192609).
**Два C1 DB P2 CLOSED. Один C0-NC-RUNNER-01/P2 OPEN; C6 correction ACTIVE.**
M3 IN_PROGRESS; native runtime NOT VERIFIED. Stock environment gap воспроизведения
снят, но complete carrier/foundation gate остаётся BLOCKED из-за child configuration.

| Task / finding | Current state |
|---|---|
| C1-NC-DB-01/P2 | CLOSED: C0 source review +3 stock PG priority/no-write cases |
| C1-NC-DB-02/P2 | CLOSED: Resume mapping +worker permanent HOLD stock PG cases |
| C2-M3.1-NATIVE-CONTEXT-DB-R2 | INTEGRATED in C0 test candidate bbc3d42…; corrections verified scoped; C2 HOLD |
| C6-M3.1-NATIVE-CONTEXT-DB-STOCK-RUNNER-R1 | REVIEW/CHANGES_REQUESTED after actual stock run; old task COMPLETE/HOLD |
| C0-NC-RUNNER-01/P2 | OPEN: isolated child lacks ASM_ENVIRONMENT=TEST; foundation check not reached |
| C6-M3.1-NATIVE-CONTEXT-DB-STOCK-RUNNER-R2 | IN_PROGRESS; exactly2 runner/test paths; source-only correction |
| Stock run39136349844/attempt1 | FAIL:56/57 native PASS;38 runner tests+76 subtests PASS; independent167/45 catalog PASS |
| Corrected stock run | TODO/HOLD until C0 reviews exact C6 R2; no automatic retry |
| C1/C2/C3/C5/C8; C6 host/operator | HOLD; next backend/API/UI/source-schema work not issued |
| Contract R2 / MATERIAL | Contract9 CLOSED/Q01 RESOLVED; MATERIAL11 INTEGRATED/VERIFIED LOCAL/TEST |
| Whole M3 / native runtime | IN_PROGRESS / NOT VERIFIED; A08/P01/P05/renewal/collector/account/A12 OPEN |

Combined tested **bbc3d42a5cd13736928a6a57f02e299a9c92a0a4**,
tree**f34ac327244a323697a602ea5fdab752f213fdb3**, parents C2
861bdf4f77f907768b073eab1daa24cce59f9d3a and C6
4ccbb40a69b74dca0bef730d82ac425309ee7554; exact union of their8 paths.
All282 source blobs/modes, archive and manifest verified. Candidate/execution branches
remain bbc3d42…; main e205e22051bc06295758b504d84699652b176c15/schema0012 unchanged.

Actual stock PG18.6/vector0.8.6/btree_gist1.8,Python3.13.16/uv0.10.0/frozen deps.
Run39136349844 job117701524374: carrier232.906s/exit1, catalog exit0, owned cleanup/
clean source PASS, receipt260.532s within20m. All5 new C2 PG cases PASS. Only failure:
test_fresh_catalog_exact_security_and_foundation_fail_closed at Settings() missing
environment; intended schema0013 RuntimeDatabase.check refusal NOT REACHED.
C0 non-DB reproduction confirms exact child omission; explicit TEST validates.
No SQL defect inferred from this configuration failure;56/57 is not aggregate PASS.

Artifact12140326093,2935013 bytes, SHA256
d043652088e71f026198022f80c3f53b0068e8510f9364481efd21a2263519d6;
[run and artifact](https://github.com/Elefesys/ai-service-manager/actions/runs/39136349844),
retention2026-10-25. Full corrected installed profile
c8a335b808f11b0c6f3d784731ddc95bf1023e6f1881aff5448659388f927a7a;
nonfunction57e03fe369be4bd03116ce380e37a9b447a2bc1a72e3bbf2a70c7ac08d69e370.
Full artifact/source/OID/role/failure evidence and scope are in
[HANDOFF§0](tasks/M3_HANDOFF.md#0-текущая-выдача-c0--stock-runner-r2-после-одного-fail--2026-10-18-utc).

New C0 preparation has sole parentbbc3d42… and only HANDOFF/REGISTER delta;
canonical task supplies full start SHA/tree. Branches:
c0/m3-1-native-context-db-stock-followup-r1 and
c6/m3-1-native-context-db-stock-runner-r2, same start.
C6 write allowlist ONLY scripts/native_context_db_catalog.py and
tests/test_native_context_db_runner.py. Explicit TEST child +real Settings config
regression; preserve reset/secret exclusion and all ownership/source guards.
Native57 cases/SQL/foundation/contracts/workflow/locks/pins/applied12/original11 frozen.
Current full contract756397 bytes SHA256
e7f3796fcff8640ffca203266ecf7b5988f7ab1bd24850b12e923122abf5d281 unchanged.

C6 returns REVIEW then HOLD; C0 separately reviews and authorizes one corrected
full stock run with unchanged20m cap. No Actions/full CI/new PR/VM/provider/live/
renewal/deploy in this source task. C8/full CI/user merge still later gates.
M4 out, IMPL-05 DEFERRED; no other limits changed. Prior assignments below are history.

<a id="текущий-статус--db-r2-correction-и-stock-runner-preparation--2026-10-18-utc"></a>

## История — DB-R2 correction и stock runner preparation / 2026-10-18 UTC

[C0 disposition](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6250016242) принял
[C1 CHANGES_REQUESTED](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6249871164)
и [C6 BLOCKED/PG NOT RUN](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6249901315).
**Два implementation P2 OPEN; stock evidence OPEN.** Source-only/catalog-definition
PASS не является installed PG или runtime acceptance.

| Task / finding | Current state |
|---|---|
| C1-NC-DB-01/P2 | OPEN: semantic priority HUMAN_REQUIRED, filtered ordinality неверна |
| C1-NC-DB-02/P2 | OPEN: Resume-only NEW_OBSERVATION→CONTEXT_CONFIRMATION_REQUIRED; worker reason сохраняется |
| C1-M3.1-NATIVE-CONTEXT-DB-REVIEW-R1 | Review COMPLETE/CHANGES_REQUESTED accepted; C1 HOLD |
| C6-M3.1-NATIVE-CONTEXT-DB-REPRO-R1 | BLOCKED environment/PG NOT RUN; source scope принят; old task C6 HOLD |
| C2-M3.1-NATIVE-CONTEXT-DB-R2 | IN_PROGRESS по exact task; четыре scoped paths, findings пока OPEN |
| C6-M3.1-NATIVE-CONTEXT-DB-STOCK-RUNNER-R1 | IN_PROGRESS по exact task; четыре NEW runner/workflow/test paths, execution NOT RUN |
| Stock run on combined corrected source | TODO/HOLD до C0 review обоих source returns; один future job20min |
| C3/C5/C8; C6 paired host/readiness implementation | HOLD; backend/API/V3/Audit/Console/operator не выданы |
| Contract R2 / MATERIAL | Все9 contract findings CLOSED/Q01 RESOLVED; MATERIAL all11 INTEGRATED/VERIFIED LOCAL/TEST |
| Whole M3 / native runtime | IN_PROGRESS / NOT VERIFIED; P-01/A08/P-05/renewal/collector/account/A12 OPEN |

Общий task start — C0 preparation с sole parent6a244ceed01388d85ecdd47fd373c6547fd34654,
treeb97e1c8964cc493b81976ddb349dba3ec03266c4. Preparation меняет только HANDOFF/REGISTER;
полные SHA/tree в canonical C0 tasks. Ветка c0/m3-1-native-context-db-followup-r1.
Новые task branches c2/m3-1-native-context-db-r2 и c6/m3-1-native-context-db-stock-runner-r1
созданы на этом start; отдельные checkouts, normal FF/expected-head. Старые reviewed
0268331 DB source и6a244ce instructions refs frozen. Код start соответствует0268331,
runtime main e205e22051bc06295758b504d84699652b176c15/schema0012 unchanged.

[Полные scopes/criteria](tasks/M3_HANDOFF.md#0-текущая-выдача-c0--native-context-db-r2-и-stock-runner--2026-10-18-utc).
C2 allowlist:0013_native_context.py, два native test modules, append contract§16.17+.
C6 allowlist:NEW .github/workflows/native-context-db.yml,
scripts/test_native_context_db.sh,scripts/native_context_db_catalog.py,
tests/test_native_context_db_runner.py. Disjoint paths; ни один исполнитель не
меняет HANDOFF/REGISTER, applied12/original11/deps/locks/ci.yml/ci.sh/runtime gates.

Contract full745994-byte prefix/SHA256
4c0187790c2e00a64a343173663072e4e51765a2aa922bc480681473dcef8886 frozen.
0013←0012 — исправляемый unmerged/unreleased successor, не новая0014.
R1 full profile11e26c… исторический; после body correction independently derive
corrected expected/installed profile. Nonfunction57e03f… должен сохраниться.

C6 source submission не запускает Actions: workflow push filter только future
c0/m3-1-native-context-db-stock-r1. C6 execution branch не создаёт.
C0 после двух returns/rereview объединяет deltas, фиксирует exact combined SHA/tree,
проверяет runner и запускает один isolated hosted stock job20min.
Fresh own DB/reset ownership/real LOGIN/full167+catalog/clean-source/artifacts/
owned cleanup обязательны. Нет повторного patched-root build, shared DB или
подмены PG NOT RUN. Full CI/C8/user merge не отменены.

C2/C6 возвращают REVIEW source → HOLD; addressed findings не CLOSED.
Existing budgets/caps unchanged, IMPL-05 DEFERRED/M4 вне scope.
Ниже historical R1 review assignment; его ACTIVE C1/C6 не current.

<a id="текущий-статус--native-context-db-r1-review-c1c6-independent-checks--2026-10-18-utc"></a>

## История — NATIVE-CONTEXT DB-R1 REVIEW; C1/C6 independent checks / 2026-10-18 UTC

[C0 intake](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6249640362),
[C2 return](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6248340477).
**Source identity/scope PASS; DB implementation REVIEW, runtime NOT VERIFIED.**
C2 reported51 PG/source cases на lab PG с изменёнными startup root checks:
stock pinned reproduction ещё OPEN. Это disclosed evidence limit, не установленный
SQL bug. C04 source-only assertions/AST/predecessor checks не являются PG run.

| Task | Status / authority |
|---|---|
| C2-M3.1-NATIVE-CONTEXT-DB-R1 | REVIEW / C2 HOLD; frozen0268331e5b57f87e7f51f3973610cb83477662e8 |
| C1-M3.1-NATIVE-CONTEXT-DB-REVIEW-R1 | IN_PROGRESS по exact C0 task; read-only SQL/contract/ABI review |
| C6-M3.1-NATIVE-CONTEXT-DB-REPRO-R1 | IN_PROGRESS по exact C0 task; independent catalog + stock focused reproduction |
| C3 backend/API/worker/Audit-V3, C6 host/readiness implementation, C5 Console | TODO/HOLD до C0 disposition двух reviews; не начинать по этому source intake |
| C8/CI/native integration/account | TODO/HOLD; checkpoint не merge-ready/deployable |
| Accepted contract R2 | ACCEPTED design; все9 CLOSED/Q01 RESOLVED сохраняются, implementation evidence отдельно |
| MATERIAL/main | INTEGRATED/VERIFIED LOCAL/TEST/all11 CLOSED; e205e22051bc06295758b504d84699652b176c15/schema0012 |
| Whole M3 | IN_PROGRESS; native runtime/P-01/A08/P-05/renewal/collector/account/A12 OPEN |

[Полные две выдачи и критерии](tasks/M3_HANDOFF.md#0-текущая-выдача-c0--независимая-проверка-native-context-db-r1--2026-10-18-utc).
Review/test target0268331e5b57f87e7f51f3973610cb83477662e8,
tree3f2f8416f6d286cca7e826b1272f450c0e5a0907,
sole parent9cebc175959eba565dcd7b979a91d04423fa94fa.
C0 coordination preparation sole parent0268331 меняет только HANDOFF/REGISTER;
ветка c0/m3-1-native-context-db-review-r1, exact preparation identity в C0 tasks.
**Preparation с инструкциями не заменяет review/test target.**
c2/m3-1-native-context-db frozen; C1/C6 отдельные local review branches/checkouts,
write allowlist EMPTY, no remote branches/commits/PR; после каждого return reviewer HOLD.

Delivery5 paths,+7624/−0,278 blobs/273 unchanged, applied0001–0012/original11 frozen.
0013←0012 reservation сохранена. Full R2 prefix714947/SHA256
d032a4b699767f58f60288fbe17808b69bf98627d8c11acb8df2c9a439ae8346 exact;
append§16.11–16.16 не меняет accepted semantics. Full delivery contract745994 bytes
заморожен на время reviews. Права на исправление C2 выдаст C0 отдельно по findings.

C6 разрешены own disposable stock pinned DB/frozen Python3.13 и focused51 carrier,
не whole stack/full CI/Actions/VM/live/API/browser/sends. DROP/RESET только созданной
для этой проверки asm_test после проверки владения host/port/process/volume.
No root-check patch/role spoof/source or gate edits. Если stock setup недоступен,
BLOCKED/PG NOT RUN + actual blocker/minimal proposal; required proof остаётся OPEN.
Independent167 definitions including profile body + exact nonfunction catalog;
DB valid=true не доказывает trusted source/drain/process readiness.

Следующее C0 решение: correction либо paired C3/C6 → C5 → C8/CI/integration.
Main не менять; no deploy/merge implication. Все budgets/caps unchanged,
IMPL-05 DEFERRED; M4 вне scope. Историческая DB выдача ниже завершена возвратом,
её ACTIVE/IN_PROGRESS не текущий статус.

<a id="текущий-статус--native-context-contract-accepted-c2-db-r1--2026-10-18-utc"></a>

## История — NATIVE-CONTEXT contract ACCEPTED; C2 DB-R1 выдача / 2026-10-18 UTC

[C0 acceptance](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6246954666),
[C1 PASS](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6246639567),
[C2 PASS](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6246768008).
**Все9 distinct contract findings CLOSED; C2-NC-Q01 RESOLVED.**
C0-NC-CONTEXT-01=C1-NC-01=C2-NC-01 — один coverage finding.
C1-NC-02/03/04,C2-NC-02/03/04/05 и C0-NC-DOC-01 закрыты в contract scope.
Future implementation assertions не выполнены этим решением.

| Task / boundary | Current status / owner |
|---|---|
| C3-M3.1-NATIVE-CONTEXT-CONTRACT-R2 | ACCEPTED contract/design; C3 HOLD |
| C1/C2 CONTRACT-REVIEW-R2 | COMPLETE/PASS accepted; C1 HOLD, C2 получает отдельную DB выдачу |
| C2-M3.1-NATIVE-CONTEXT-DB-R1 | IN_PROGRESS после exact C0 task; единственный implementation author, [действующий scope](tasks/M3_HANDOFF.md#0-текущая-выдача-c0--c2-m31-native-context-db-r1--2026-10-18-utc) |
| Native backend/API/worker, source/schema host integration, Console | TODO/HOLD; отдельные C3/C6/C5 scopes после C0 DB intake |
| Native C8/CI/integration/account | TODO/HOLD; DB checkpoint не merge-ready/deployable; mandatory gates не отменены |
| MATERIAL/runtime main | INTEGRATED/VERIFIED LOCAL/TEST/all11 CLOSED; e205e22051bc06295758b504d84699652b176c15/schema0012 unchanged |
| Whole M3 | IN_PROGRESS; P-01/A08/P-05 renewal/collector/account/A12 OPEN; native runtime NOT VERIFIED/account NOT OBSERVED |

Reviewed contract0cdd66cc135c8797224e8dc0e87bc3280ad446c1,
tree11335a808d4468c78af17501849c52202b811ff7.
C0 preparation sole parent — этот R2; только HANDOFF и этот реестр меняются.
Actual full continuation SHA/tree — в canonical C0 PR34 assignment.
Branch **c2/m3-1-native-context-db**, отдельный checkout/normal FF; C3 branch frozen.
Migration reservation **0013_native_context.py /0013←0012**; applied0001–0012 frozen,
renewal не назначать competing0013. При drift/conflict — C0 до публикации.

Exact write permission **5 paths**, полное содержание/проверки в handoff§0:
migrations/versions/0013_native_context.py (new),
tests/test_m3_1_native_context_migrations.py (new),
tests/test_m3_1_native_context_postgres.py (new),
tests/test_tenancy_postgres.py (native inventory/security delta only),
docs/tasks/M3_CONTRACT.md (append§16.11+ with substantive implementation only).
C0 owns HANDOFF/REGISTER/AGENTS; backend/API/OpenAPI/UI/readiness/scripts/workflows/
dependencies/original11/applied migrations вне scope.
R2 contract **714947 bytes/SHA256d032a4b699767f58f60288fbe17808b69bf98627d8c11acb8df2c9a439ae8346**
побайтно frozen; PROPOSED/OPEN/unassigned ниже — исторический reviewed state,
текущая C0 выдача заменяет статусы, не technical semantics.

D4 choices accepted: private3 tables, same-Job token/result markers, stable snapshot
projection и1024-gap/probe1025 fail-closed bound. Обязательны indexable source→old mark
для duplicates, early supersede/terminal marker cleanup, один first Escalation cancel
(Takeover уже может его выполнить), actual callee/policy snapshot discipline.
D1/D2/D3 limits/latest canonical-state obligation сохранены; no M4 summary/native vision.
Huge/unrepresentable context → manual/UNRESOLVED, no deletion/cap increase bypass.

Current foundation/source всё ещё0012; DB0013 checkpoint **не включать** с неподходящим
runtime и не ослаблять readiness. C2 разрешены focused source/unit/realPG18 synthetic
disposable checks и publication task branch; no CI/new PR/HTTP/browser/host operator/
account/VM/working DB-S3/sends/deploy/renewal. Следующий coherent source и PR/gates
назначает C0; никакого implied merge/deployment. Budget/worker caps unchanged,
IMPL-05 DEFERRED; M4 не выдан. Return REVIEW/DB checkpoint→C2 HOLD.

Historical R2 review/current-status snapshot ниже сохранён;9 OPEN в нём не current.

<a id="текущий-статус--c3-native-context-r2-review--2026-10-18-utc"></a>

## История — C3 NATIVE-CONTEXT R2 REVIEW / 2026-10-18 UTC

**C3-M3.1-NATIVE-CONTEXT-CONTRACT-R2 — REVIEW / docs proposal → HOLD после return.**
[C0 assignment](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6245868587),
[C0 dispositions/design choices](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6245858507),
[C1 return](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6245768491),
[C2 return](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6245810317),
[contract§16](tasks/M3_CONTRACT.md#16-native-context--proposed).
C1/C2 COMPLETE/CHANGES_REQUESTED accepted→HOLD; C5/C6/C8 HOLD.

| Binding / task | Current disposition |
|---|---|
| Correction parent/tree | `315c42e2ef03ace056279fe019efef5100665c7c` / `348519b752e05aae7d410f4a97ac7685ac77e8e0`, reviewed proposal baseline |
| Branch/publication | `c3/m3-1-native-context-contract-r1`, one ordinary fast-forward commit; sole parent above; exact published identity/statistics in canonical PR34 return. No amend/rebase/force/new PR |
| Write scope | Exactly `docs/tasks/M3_CONTRACT.md` proposed§16, `docs/tasks/M3_HANDOFF.md`, this register; history preserved. No code/tests/OpenAPI/migration/source-original edits |
| Accepted runtime | MATERIAL INTEGRATED/VERIFIED LOCAL/TEST/all11 CLOSED; main `e205e22051bc06295758b504d84699652b176c15`, tree `85206b9c66ac151f3847aa39f46fb75663a18b91`; CI38960113060 attempt1 push/main9+clean9 SUCCESS unchanged |
| R2 concrete choices | Mandatory coverage guard/tail eviction hold; STABLE same-snapshot classification/own-write separation; same-Job bounded pending recheck; closed policy/read/errors/body/cursor; Escalation hold+pre-C connection lock; replayable LOCAL/TEST policy receipt; explicit pre-C/NULL bootstrap |
| Minimal data delta proposed | Two context evidence tables + one immediate policy command receipt; C/connection/control links and Job wait marker. Exact full FK/RLS/ACL/signature/typed Audit obligations; no generic framework |
| Status limit | Native contract PROPOSED/NOT ACCEPTED; implementation NOT VERIFIED. Nine findings and one clarification below OPEN despite addressed proposal |

| Finding / full alias / severity | Current disposition / R2 correction |
|---|---|
| C0-NC-CONTEXT-01 = C1-NC-01 = C2-NC-01 / P1 | OPEN;§16.4/16.5 coverage_ok every admission, full handoff/replacement; NC01/02/08/20 |
| C1-NC-02 / P2 | OPEN;§16.5.1 closed matrix/precedence/legacy NULL variant; NC10/16/19 |
| C1-NC-03 / P2 | OPEN;§16.4 exact4096 total body/Unicode/cursor/preview/wire; NC06/10/11/20 |
| C1-NC-04 / P2 | OPEN;§16.6.3 Escalation context_hold/read/list/strict UI; NC14/19 |
| C2-NC-02 / P1 | OPEN;§16.6.1 post-wait one snapshot/terminal retry/own writes; NC12/13 |
| C2-NC-03 / P2 | OPEN;§16.6.2 durable WAIT/reclaim/visible exhaustion; NC14/15/18 |
| C2-NC-04 / P2 | OPEN;§16.6.3 RESOLVE connection before C/retained terminal priority; NC11/14/19 |
| C2-NC-05 / P2 | OPEN;§16.7.1 trusted policy command+receipt/CAS/hash/Audit/replay; NC15/19 |
| C0-NC-DOC-01 / P3 | OPEN pending C0 intake; EOF corrected, actual R2 git diff --check and three-doc integrity in return |
| C2-NC-Q01 / clarification | OPEN;§16.6.1 MATERIAL no-C queue/defer, failed/unsequenced bootstrap; NC09/13/19/20 |

C0 D1/D2/D3 accepted limited design choices, не acceptance всего контракта.
Next minimal scope — C0 intake + targeted C1/C2 rereview of concrete R2; D4 schema/
wire/recovery/1024-gap-bound/policy-carrier review перед отдельным runtime assignment.
Applied0001–0012 frozen; successor revision/predecessor/reservation unassigned.
Frozen through§15.18 exact603955 bytes, SHA256
`9643365fa8b534d6cf37a181c7c03ed76bd16b9d559016794b377b9a1eb1064b`.

Source-backed inspection/manual finite traces only; original11/manifest/supplied
originals rechecked; actual R2 `git diff --check` **EXIT0**; prefix/3-path/links PASS,
69 future paths=57 existing+12 proposed new. Full verification/identity in canonical
return. Historical R1 C3 NOT RUN (exec outage) и C0 EOF EXIT2
remain historical facts. Product pytest/PG/Docker/Playwright/build/services/install/
CI actions/operator commands/account/VM/Telegram API/working DB/S3/sends/renewal/
deploy/expenses NOT RUN. No new PR/main/old PR34 branch mutation.

Whole M3 IN_PROGRESS; P-01/latest-human-context/A08, P-05 renewal/collector,
P-A03-09 account и M3-ACCEPTANCE/A12 OPEN. Gate OFF; merge не deployment.
Budgets S/600/P720/fixed120/+480/S+1200/cleanup90/state25/browser25/foundation45/
3s/60s/10s и worker caps unchanged; IMPL-05 DEFERRED, M4 вне scope.

<a id="текущий-статус--material-принят-c3-native-context-review--2026-10-17-utc"></a>

## История — C3 NATIVE-CONTEXT R1 REVIEW / 2026-10-17 UTC

**MATERIAL INTEGRATED/VERIFIED LOCAL/TEST; whole M3 IN_PROGRESS.**
[C0 postmerge receipt](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6228792048),
[C3 docs assignment](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6228802023),
[contract§16](tasks/M3_CONTRACT.md#16-native-context--proposed).

| Task / binding | Current disposition |
|---|---|
| PR34 / accepted main | MERGED. `e205e22051bc06295758b504d84699652b176c15`; tree `85206b9c66ac151f3847aa39f46fb75663a18b91`; migration0012 integrated, applied0001–0012 frozen |
| Actual CI / independent review | [CI38960113060 attempt1 push/main](https://github.com/Elefesys/ai-service-manager/actions/runs/38960113060),9 jobs +9 clean SUCCESS; [C8 PASS](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6223489359) on same candidate/tested tree |
| MATERIAL findings | All11 CLOSED by C0. Historical OPEN3/NOT RUN/Draft blocks below are source history, not current gates |
| C3-M3.1-NATIVE-CONTEXT-CONTRACT-R1 | **REVIEW / proposal**, then **C3 HOLD**. Separate `c3/m3-1-native-context-contract-r1`, exact sole parent accepted main; one substantive docs commit, full identity/numstat in canonical return |
| Authorized diff | Exactly `docs/tasks/M3_CONTRACT.md` append§16, `docs/tasks/M3_HANDOFF.md` current block, `docs/TASK_REGISTER.md` current block/history labels. No code/tests/generated API/migrations/workflows/originals edits |
| Mechanism proposed | Explicit live OWNER reconciliation in HUMAN, immutable R/Audit/V+1, then existing Resume selects R with CAS and G/F atom. New provider observation N causes conservative review hold without native HUMAN guess; source missing cannot be inferred complete |
| Data/API/reader | Two private evidence tables; C pointer/N, connection policy/P, nullable Resume relation; new context read/observations/reconcile routes. V3 current R+bounded canonical tail, honest TEXT_ONLY/media unavailable; no Message/Outbox/File/send fabrication |
| Security/recovery | Live auth/CSRF/tenant+Client relations, DB hash/key/CAS including ingress checkpoint; pending/failed gaps; exact replay never overwrites newer HUMAN/R or bumps again; retained UNKNOWN/in-flight |
| Compatibility | V1/V2 hashes/receipts/snapshots retained, old IGNORED never backfilled/replayed; bootstrap H/AI, PAUSED/reenable P+1, used downgrade fail before DDL; revision/predecessor not assigned |
| Evidence / limitation | Source/manifest/originals/accepted bindings inspected; NC01–NC20 manual traces only. Final prefix/tree/path/read-back/whitespace/link checks in receipt. Exec-server outage blocks final local `git diff --check` (NOT RUN); separate whitespace check, no runtime tests |
| C0 decisions | D1 assurance/LOCKED/A08 scope; D2 conservative hold availability; D3 TEXT_ONLY media limit; D4 C1 API/security + C2 FK/RLS/serialization/V3 reviews, then exact owner scopes/revision |
| Still OPEN | P-01/latest-human-context/A08, P-05 renewal/collector, P-A03-09 account evidence, M3-ACCEPTANCE/A12. Native design not accepted/integrated/verified by this source |
| Other owners / next step | C1/C2/C5/C6/C8 HOLD pending separate C0 tasks. Next minimal work decision/reviews, C3 contract R2 only if needed; no new PR/runtime/probe/renewal/deploy |

Contract prefix through§15.18 exact603955 bytes, SHA256
`9643365fa8b534d6cf37a181c7c03ed76bd16b9d559016794b377b9a1eb1064b`.
Merged MATERIAL is not VM deployment; gate OFF. No runtime/PG/browser/build/services/
install/Actions operations, sends/account/VM/S3/expenses. Budgets S/600/P720/fixed120/
+480/S+1200/cleanup90/state25/browser25/foundation45 and3s/60s/10s unchanged.
IMPL-05/broad optimization DEFERRED. Existing source evidence is preserved below.

<a id="текущий-статус--c2-m31-material-sent-lock-r5--2026-10-16-utc"></a>

## История — C2-M3.1-MATERIAL-SENT-LOCK-R5 / 2026-10-16 UTC

**MATERIAL/M3 IN_PROGRESS; PR34 Draft/BLOCKED; three distinct findings OPEN.**
[C0 source task](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6220709356),
[C0 R4 disposition](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6220674632),
[§15.18](tasks/M3_CONTRACT.md#1518-c2-m31-material-sent-lock-r5--single-targetcontext-updates-and-typed-tenancy-identity--2026-10-16-utc).

| Task / binding | Current source result / actual gate |
|---|---|
| C2-M3.1-MATERIAL-SENT-LOCK-R5 | REVIEW on return, then HOLD. Separate branch c2/m3-1-material-sent-lock-r5, exact base/sole parent36240388fa580e563699c4dec3fd989cc2dd09f6/tree cb5c38e78a145184d8792f53702e102275fbb785; one focused descendant, full head/tree/numstat in receipt |
| Main / PR34 | Main/frozen E933ddd284ff5b77fb1aa88a4270ab0032bc499c9/0011; OPEN/Draft PR34 c6/m3-1-material-compat stays36240388; no advancement |
| Source cause / correction | Actual55P03/material_apply frame, exact FK UNKNOWN. Pinned PG18 current-XID RI path supports repeated target and C updates as connection lock edges. One target bind+final-current UPDATE; one shared changed-SENT C+2 UPDATE, ordinary/default C+1 and no-op/unmatched/UNKNOWN behavior preserved |
| Private typed identities | Apply adds previous jsonb, context adds delivery boolean DEFAULT false; no new overload/capability.132 functions/23 additions/2 runtime/21 private/7 invoker/16 SECDEF, same owner/search_path/grants. Tenancy resolves closed full regprocedure signatures to unique OIDs and compares exact sets/profiles |
| Regression source | Original single finish_send/3s/held connection FOR UPDATE/arguments/same-call diagnostic preserved; exact post-success SENT/current/version/Audit/effect/history readbacks. Neighbor no-op SENT plus Message/C overflow arms with intended22003 and41 data+actual metadata whole-atom rollback; PG NOT RUN locally |
| Local checks | Existing online-DDL test1 PASS/69 deselected/0.84s; cached Ruff0.16.7 check/format3 modules, compile/diff/AST/source audits PASS.3.12.14, packaged3.13 absent;131 statements/42 tables/132 functions,127 other profiles and53 other test definitions exact; no install/bootstrap/services/runtime run |
| Actual baseline | CI38926368179/attempt1, tested merge d3c39fa8977d86aa25f6ab9cc713a0c7f55d2f22:8 SUCCESS/1 FAILURE, clean8 SUCCESS/1 SKIPPED;1444 units PASS, PG797 PASS/2 FAIL. Browser308 Vitest/44 Playwright and both complete state lanes/clean PASS. Historical browser cause UNKNOWN |
| CLOSED8 by C0 | C1-R2-02 (C1-R3-01 alias), C2-MAT-02, C1-R3-03, C0-R3-01/02/04/05, C5-R3-01. Earlier scoped closures/regression bridge remain |
| OPEN3 | C1-MAT-01/P1 (C1-R3-02 alias), C0-R3-03/P2, C2-MAT-01/P1. No source self-closure or INTEGRATED/VERIFIED |
| Remaining actual gates | C0 source intake then same PR normal automatic CI, full9+clean9, full foundation post-PG tail, dedicated tenancy profile/ACL/SENT atomicity and both complete state lanes again, remaining owners then independent C8. C1/C3/C5/C6/C8 HOLD |

Contract prefix through§15.17 is exact592048 bytes/SHA256
ad5697568bcd71639c06fbf827c97481c9e1149879a538518599866a72fb3604.
Six changed paths inside eight allowed; applied0001–0011/ORIGINAL17/OLD_CHECK4,
original11/product/DTO/Worker/mapper/frozen/runtime/scripts/workflows/Compose/pins/
locks/frontend exact. Physical schema and0012←0011 unchanged. Foundation tail and
clean gate were not reached after PG failure; other green jobs do not replace them.
Gate OFF; normal P prep719.560822218s left0.439177782s, foundation43:11 is not full45min
acceptance or optimization authority. S/600/P720/fixed120/+480/S+1200/cleanup90/state25/
browser25/foundation45 and3s/60s/10s unchanged. No clock reset/subtraction/retry/budget
increase/Actions operations/PR-head move/new PR/merge/live/VM/working DB/S3/sends/
deploy/native/A08/P-A03-09/renewal/collector/M4. IMPL-05/broad optimization DEFERRED.
Earlier sections retain their historical statements.

## История — C2-M3.1-MATERIAL-CURRENT-PROFILE-R4 / 2026-10-16 UTC

**MATERIAL/M3 IN_PROGRESS; PR34 Draft/BLOCKED; eleven distinct findings OPEN.**
[C0 source task](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6218233521),
[C0 R3 disposition](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6218176738),
[§15.17](tasks/M3_CONTRACT.md#1517-c2-m31-material-current-profile-r4--test-boundaries-and-same-call-sent-diagnostics--2026-10-16-utc).

| Task / binding | Current result / actual gate |
|---|---|
| C2-M3.1-MATERIAL-CURRENT-PROFILE-R4 | REVIEW on return, then HOLD. Separate c2/m3-1-material-current-profile-r4, exact base/sole parent89f9e157ddfc328ba4564fc003b047f517352cdf/tree9be95d45e6a70bf76adf146c1035e571d52205af; one focused descendant, final identity/numstat in canonical receipt |
| Main / PR34 | Main/frozen E933ddd284ff5b77fb1aa88a4270ab0032bc499c9/0011; PR34 OPEN/Draft c6/m3-1-material-compat stays89f9e15; no advancement |
| Source | Nine named test modules + three documents only. Wire dates, V2 held ingress/lifecycle, exact current/23-signature profiles, actual-stage0011 seed, UTC caller; complementary R3 metadata gives41+1. Existing assertions and product/migrations/frozen sources unchanged |
| SENT | Single original finish_send/3s/held FOR UPDATE with bounded closed metadata only; primary exception survives diagnostic/cleanup failures. No runtime fix; primary cause UNKNOWN |
| Local checks | Ruff0.16.7 check/format9 files, compile/diff/AST/prefix/source audits PASS;235 other function bodies/decorators byte-exact.6 new pure pytest PASS/64 deselected/0.86s on3.12.14 plus DTO/V2/fingerprint/UTC probes; not packaged3.13 or PG. Initial6 PG-harness import failures led to pure helper placement; no installs/environment bootstrap |
| Actual baseline | CI38909147338/attempt1, merge d0fd7e5da7c29b1e065e72a7bfcc11519bdd39d6:5 SUCCESS/4 FAILURE, clean5 SUCCESS/4 SKIPPED;1438 units PASS, PG785 PASS/14 FAIL, browser43 PASS/1 FAIL, both state stop at fresh DTO after saved-V1 reader |
| CLOSED by C0 | C0-DIAG-02 (C1-R2-01 alias), C1-MAT-02, C2-MAT-03. C5-MATERIAL-01/C0-DIAG-01 retain scoped closures; full gates remain blocked |
| Eleven OPEN | C1-MAT-01/P1 (C1-R3-02 alias), C1-R2-02/P2 (C1-R3-01 alias), C2-MAT-01/P1, C2-MAT-02/P2, C1-R3-03/P2, C0-R3-01/P2, C0-R3-02/P2, C0-R3-03/P2, C0-R3-04/P2, C0-R3-05/P2, C5-R3-01/P2 |
| Independent work | C5-ESCALATION-RECOVERY-DIAG-R3 separately ACTIVE only frontend/e2e/messaging.spec.ts from89; no branch absorbed. C1/C3/C6/C8 HOLD; C2 HOLD after source receipt |
| Remaining actual gates | C0 accepts/combines both returns before same PR normal automatic CI;9+clean9, full PG/fresh DTO+tenant/wrong-Client/SENT/EXPIRED/ingress/catalog/ACL/populated reverse/R3 raw42/both full P-state/used recovery/cutover/restart/retained full120/export/all3 late-C negatives/owned cleanup, C1/C2/applicable C5 then independent C8 |

This source closes no actual finding. Historical R3 “all42” is corrected to41 data
tables; new scoped metadata read is future raw42 evidence, not an executed proof.
The entire§15.16 contract prefix582717 bytes/SHA2566f68bd44… and original11 remain
exact. No skip/xfail/marker/selector weakening or broader unrelated reruns.
Gate OFF; not INTEGRATED/VERIFIED. Original S/retained600/P720/remaining+480/
nominal S+1200/cleanup90/state25/browser25/foundation45 and individual limits unchanged.
No installs/new services/Docker/PG/browser runtime/Actions operations/PR-head/new PR/
merge/live/VM/working DB/S3/sends/deploy/native/A08/P-A03-09/renewal/collector/M4.
IMPL-05/broad optimization DEFERRED; earlier sections retain their historical status.

## История — C6-M3.1-MATERIAL-HARNESS-R5 / 2026-10-16 UTC

**MATERIAL/M3 IN_PROGRESS; PR34 Draft/BLOCKED; seven distinct findings OPEN.**
[C0 task](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6211450459),
[C0 disposition](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6211420811),
[§15.16](tasks/M3_CONTRACT.md#1516-c6-m31-material-harness-r5--packaged-inputs-and-saved-v1-reader--2026-10-16-utc).

| Task / binding | Current source result / actual gate |
|---|---|
| C6-M3.1-MATERIAL-HARNESS-R5 | REVIEW on return then HOLD. Branch c6/m3-1-material-harness-r5, exact base/sole parent d7cea5a2e9da7b384aeaf11dd41df3e1e4abcbff/tree a471c98e16343cf9d17d4d184df88ed491184544; one focused descendant, final identity/numstat in receipt |
| Main / PR34 | Main/frozen E933ddd284ff5b77fb1aa88a4270ab0032bc499c9/0011; PR34 OPEN/Draft c6/m3-1-material-compat/d7cea5a… unchanged |
| Unit inputs | Explicit verified frozen-H pins dependency before ROOT substitution; all11 real-entrypoint preparation cases/assertions preserved; no uncopied infra or Git dependency |
| Saved V1 | Complete non-NULL Job inventory; closed ordinary/guarded reader, actual Job-id response envelope only in memory; stored JSON/all fields/digest/no schema preserved, no Escalation form or product changes |
| Before / after | Exact d7 COPY baseline preparation[pass]:1 expected FAIL/0 subprocesses. Old controller block synthetic raw-input mismatch reproduced. Corrected110 PASS (78 fixture/32 helper cases), existing91 PASS;15 overlap/186 distinct;0 skip/xfail, restricted168-file layout |
| Preserved | Six-path scope;306538-byte runtime/shell/frozen fixture and decoder/original11/C3/product/migrations/ORIGINAL17/OLD_CHECK4/Inbox/current-T/PHOTO/observer/ACK/privacy/budgets exact; full§15.15 prefix576446 bytes/SHA25676ed7dd2… unchanged |
| CLOSED by C0 | C5-MATERIAL-01 and C0-DIAG-01, scoped actual d7/merge58542ff evidence; applicable regression bridge remains required |
| Seven OPEN | C2-MAT-01/02/03,C1-MAT-01/02,C0-DIAG-02 (C1-R2-01 packaging alias),C1-R2-02. R5 units do not close findings |
| Actual gates | CI38868575912/attempt1:6 SUCCESS/3 FAILURE,clean6 SUCCESS/3 SKIPPED. Prep623.690022374s/688.934643093s PASS720, not600/full-state. Full product PG/both complete P-state/used55000/recovery/cutover/restart/retained/full120/export/all3 late-C/9+clean9 pending |

C0 intake before C0 advances same Draft PR34 for normal automatic CI; remaining
C1/C2 acceptance, applicable C5 bridge, later independent C8. C6 HOLD after return;
C3/C1/C2/C5/C8 HOLD. Source/unit evidence only; no new Docker/PG/browser/Actions/
install/services/PR-head/new PR/merge/live operations. Gate OFF; not INTEGRATED/
VERIFIED. Original S/retained600/P720/+480/S+1200/cleanup90/individual/state25/browser25/
foundation45 unchanged. Native/A08/renewal/collector/M4 unissued; IMPL-05/broad
optimization DEFERRED. VM/working DB/S3/sends/deploy unissued; history below preserved.

## История — C6-M3.1-MATERIAL-CI-DIAG-R4 / 2026-10-16 UTC

**MATERIAL/M3 IN_PROGRESS; PR34 Draft/BLOCKED; all eight findings OPEN.**
[C0 R4](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6210115890),
[R3 intake/new packaging finding](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6210103047),
[§15.15](tasks/M3_CONTRACT.md#1515-c6-m31-material-ci-diag-r4--diagnostic-unit-image-inputs--2026-10-16-utc).

| Task / binding | Current source result / actual gate |
|---|---|
| C6-M3.1-MATERIAL-CI-DIAG-R4 | REVIEW on return, then HOLD. Branch c6/m3-1-material-ci-diag-r4; exact base/sole parent9cb1467c1705827a4e782421754850f5dee762ce, tree e0c1e5231cddfd25e44071990031371aaa16c482. One focused descendant; final head/tree/numstat in receipt |
| R3 / DIAG-01 | Host correction source/unit accepted by C0; complete306538-byte pre-pytest prefix and entire shell byte-exact. Actual state/CI acceptance pending |
| Main / PR34 | E933ddd284ff5b77fb1aa88a4270ab0032bc499c9/0011; PR34 OPEN/Draft c6/m3-1-material-compat/d810dde939f727085af15f7614eeddd36f4909b8 unchanged |
| Unit inputs | One pinned test-only JSON, four exact H objects/231153 decoded bytes; fixed paths/lengths/blob checks, bounded decode. No Git/runtime history. Host uses finite external Git-command/H doubles with actual copied blobs and explicitly synthetic identities; real loader/binding/observer unchanged |
| Observed before/after | Unchanged9cb source-only export:2 setup ERROR in1.35s, show/clone exit128. Corrected168-file development COPY layout without .git/usable Git:91 PASS/510 deselected in10.00s, JUnit0 failure/error/skip, no xfail; includes15 host+60 earlier invocation cases |
| Restrictions / control | Empty inherited environment; PATH only sh/python3, Git lookup None, audit blocks Git;0 Git subprocess attempts. Cached locked deps only. Revised loader still detects exact a9 missing-pytest defect:6 FAIL/9 PASS. No skip/marker/collection filtering changes |
| Preservation | Exact five-path scope; runtime prefix/SHA2563b1b9e4d… and shell7d1e08e… unchanged;168 other definitions/all host assertions/cases exact. Full§15.14 prefix569463 bytes/SHA256bd6f9cb9… preserved. Original11/C3/product/PG/migrations/Inbox-Job-inventories/frozen H-T-C-G-E/observer-P/privacy-ACK/limits/workflows/locks/budgets unchanged |
| OPEN findings | C2-MAT-01/P1, C2-MAT-02/P2, C2-MAT-03/P1, C1-MAT-01/P1, C1-MAT-02/P2, C5-MATERIAL-01/P2, C0-DIAG-01/P1, C0-DIAG-02/P1. DIAG-01 source-fixed; no actual acceptance claimed |
| Actual gates | Historical38850821014 remains4 SUCCESS/5 FAILURE, clean4 SUCCESS/5 SKIPPED; H cause UNKNOWN, Docker29 prep499.951432356s partial. C0 packaging intake before same Draft PR34 automatic CI; actual9+clean9/both complete state-P/retained-late-C/0012-PG/current-T→T2/PHOTO-browser then C1/C2/C5/later C8 required |

C6 HOLD after canonical return; C3/C1/C2/C5/C8 HOLD. Packaging/unit evidence only;
no install/services/Docker/build/PG/browser/Actions execution. No implementation
INTEGRATED/VERIFIED; gate OFF. S/600/P720/remaining+480/S+1200/cleanup90/individual
bounds/state25/browser25/foundation45/9+clean9 unchanged. No PR-head update/new PR/
merge/dispatch/rerun/cancel/live operation. Native/A08/renewal/collector/VM/working
DB/S3/sends/deploy/M4 unissued; IMPL-05/broad optimization DEFERRED. Earlier sections
below preserve their historical statuses/receipts.

## История — C6-M3.1-MATERIAL-CI-DIAG-R3 / 2026-10-16 UTC

**MATERIAL/M3 IN_PROGRESS; PR34 Draft/BLOCKED; all seven findings OPEN.**
[C0 assignment](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6209721060),
[C0-DIAG-01/P1 disposition](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6209702274),
[R2 return](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6209600353),
[§15.14](tasks/M3_CONTRACT.md#1514-c6-m31-material-ci-diag-r3--stdlib-h-host-boundary--2026-10-16-utc).

| Task / binding | Current source result / actual gate |
|---|---|
| C6-M3.1-MATERIAL-CI-DIAG-R3 | REVIEW on source return, then HOLD. Branch c6/m3-1-material-ci-diag-r3; exact correction base/sole parent a9f58a1364b98b5331b83fa17893363abb7d5dae, tree4c938731b25a4b0424f8e86d33bcf779f6f1fe8b. One focused descendant; final head/tree/numstat in canonical receipt |
| R2 disposition | CHANGES REQUIRED, correction base only. Historical60/196 PASS tied to a9; missing real stdlib-loader coverage found by C0. No PR advancement accepted |
| Main / PR34 | E933ddd284ff5b77fb1aa88a4270ab0032bc499c9/0011; PR34 OPEN/Draft, c6/m3-1-material-compat / d810dde939f727085af15f7614eeddd36f4909b8 unchanged |
| Host correction | Early stdlib dispatch before pytest; unchanged observer executes with runpy module alive. Result/summary or exact executor exception transferred; started marker prevents repeat H. Setup/load finite INVALID; image/intent direct; cleanup/gates/observer protocol/P unchanged |
| Observed regression | External test containing only the two new nodes on clean exact a9:6 FAIL/9 PASS in6.10s, actual pytest import attempt and INVALID-load path. Corrected affected selection91 PASS/510 deselected in14.80s, includes15 new real-loader python -S cases and60 existing invocation cases |
| Evidence limits | Only external H execution doubled, synthetic empty report/ACK; real runpy/full module, no namespace stub. No dependency/service/Docker/PG/browser/Actions execution. Source/unit proof, no actual state/product acceptance |
| Preservation | Exactly five allowed paths; full§15.13 prefix563611 bytes/SHA2562aee6573…;168 existing definitions byte-exact, related seam assertions intact;274 unchanged baseline blobs verified. Original11/C3/product/PG/applied migrations/0012/inventories/Inbox pair/five NULL Job fields/frozen H/T/C/G/E/launcher/HMAC/ACK/privacy/workflows/locks unchanged |
| OPEN findings | C2-MAT-01/P1, C2-MAT-02/P2, C2-MAT-03/P1, C1-MAT-01/P1, C1-MAT-02/P2, C5-MATERIAL-01/P2, C0-DIAG-01/P1. Source/unit evidence closes none |
| Actual evidence / next gate | Historical38850821014:4 SUCCESS/5 FAILURE, clean4 SUCCESS/5 SKIPPED; H cause UNKNOWN, Docker29 prep499.951432356s partial. C0 source intake before PR update; actual9+clean9/both state-P/retained-late-C/0012-PG-current-T→T2/PHOTO-browser, C1/C2/C5 and later C8 still required |

C6 HOLD after canonical return; C3/C1/C2/C5/C8 HOLD. No implementation
INTEGRATED/VERIFIED, gate OFF. Original S/retained600/P720/remaining+480/S+1200/
cleanup90/individual bounds/state25/browser25/foundation45/9 jobs+clean9 unchanged.
No PR-head update/new PR/merge/dispatch/rerun/cancel/live operation. Native/A08/
renewal/collector/VM/working DB/S3/sends/deploy/M4 unissued; IMPL-05/broad optimization
DEFERRED. Earlier sections below are historical, including their then-current six findings.

## История — C6-M3.1-MATERIAL-CI-DIAG-R2 / 2026-10-16 UTC

**MATERIAL/M3 IN_PROGRESS; PR34 Draft/BLOCKED; all six findings OPEN.**
[C0 task](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6208852583),
[accepted C3 checkpoint](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6208831490),
[diagnosis](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6208328996),
[§15.13](tasks/M3_CONTRACT.md#1513-c6-m31-material-ci-diag-r2--bounded-original-invocation-diagnostics--2026-10-16-utc).

| Task / binding | Current source result / actual gate |
|---|---|
| C6-M3.1-MATERIAL-CI-DIAG-R2 | REVIEW on return, then HOLD. Branch c6/m3-1-material-ci-diag-r2; accepted base f0c111ac0b74695cc12444ccdf077314d06d2a9b, tree ca3f638b206b232a7a6cd8f1920e31580991b58b. Two focused source commits; final immediate parent711934148b3921047501ff3e3c3b6e6ff34c74a4. Final head/tree/combined numstat in canonical receipt |
| C3 accepted source | R2 seven-space correction/two original-string regression nodes preserved; C0 source/client intake accepted, actual0012 acceptance pending |
| Main / PR34 | E933ddd…/0011; PR34 remains OPEN/Draft, c6/m3-1-material-compat / d810dde939f727085af15f7614eeddd36f4909b8. No head update/new PR/merge or CI execution here |
| H observation | State-only private startup launcher executes original immutable H stdin. Original command/build objects, actual target/exit/timeout, separate observer/executor identities; no retry/probe/source rewrite. H cause still UNKNOWN |
| P ordinary migration | Original e.command frame observation, closed source/tree/direction/revision; client vs server/explicit SQLSTATE distinction,30s and ACK86 unchanged |
| Private evidence |0700/0600; authenticated closed report≤64KiB/16 records; classify≤16KiB per captured stream; no raw outputs/SQL/argv/env/credentials. H requires independent64-byte final ACK; invalid diagnostics cannot replace original executor failure |
| Scoped evidence |60 new invocation cases PASS; combined196 PASS/390 deselected includes those60. Ruff/format/shell/embedded code/diff/source audit PASS. Synthetic doubles, no actual H/P/PG/Docker/browser gates |
| Preservation | Full§15.12 prefix551663 bytes/SHA2560be54876…;134 existing definitions exact, P/outer AST exact after removing diagnostics. Original11, applied0001–0011/ORIGINAL17/OLD_CHECK4/0012←0011,10 columns/6 old/4 new/42 total/132 signatures, Inbox winning pair/five NULL delivery fields, frozen T/C/G/E/workflows/locks unchanged |
| Historical CI |38850821014/attempt1 tested merge51fca8…/tree fb06ad7…, not this source:4 SUCCESS/5 FAILURE; clean4 SUCCESS/5 SKIPPED. H build before S/P opaque; Docker29 prep499.951432356s partial, full P and3 late C negatives not reached |
| OPEN findings | C2-MAT-01/P1, C1-MAT-01/P1, C1-MAT-02/P2, C5-MATERIAL-01/P2, C2-MAT-02/P2, C2-MAT-03/P1. Source/unit evidence closes none |
| Next gate | C0 combined intake → one update of same Draft PR34 → automatic CI9/9+clean9/9, both full state/P/retained/late-C cleanup, actual0012/raw42/catalog/security/recovery/replay/current-T→T2/paired PHOTO/browser → C1/C2/C5, later C8 |

C6 HOLD after canonical source return; C3/C1/C2/C5/C8 HOLD. No implementation
INTEGRATED/VERIFIED. Original S/retained600/P720/remaining+480/S+1200/cleanup90,
individual bounds/state25/browser25/foundation45 and9 jobs/clean9 remain fixed.
Gate OFF; native/A08/renewal/collector/live/VM/working DB/S3/sends/deploy/M4 unissued;
broad CI optimization/IMPL-05 DEFERRED. No installs/services/dispatch/rerun/cancel.

## История — C3-M3.1-MATERIAL-R2 source correction / 2026-10-16 UTC

**MATERIAL/M3 IN_PROGRESS; PR34 Draft/BLOCKED; all six findings OPEN.**
[C0 R2](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6208530769),
[binding disposition](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6208519238),
[evidence§15.12](tasks/M3_CONTRACT.md#1512-c3-m31-material-r2--online-sql-parameter-correction--2026-10-16-utc).

| Task / finding | Current source result / actual gate |
|---|---|
| C3-M3.1-MATERIAL-R2 | REVIEW on return, then HOLD. Branch c3/m3-1-material-r2; exact base/sole parent d810dde939f727085af15f7614eeddd36f4909b8, tree fb06ad7bf5cf4d821e880328888c9bbf25eea3b7, base parent e7f5547…; main/E933ddd…/0011 and existing PR34 head unchanged. Final head/tree/numstat in canonical receipt |
| C2-MAT-03/P1 OPEN | Six0012 literal spaces + one actual forged-basis setup space; equal JSON. Two actual-string online TextClause/psycopg regressions: base2 FAIL with required-null InvalidRequestError → candidate2 PASS. All131 expanded operations accept empty parameters; actual migration still required |
| C2-MAT-01/P1 OPEN | Earlier three CASE source corrections accepted; actual complete0012 lifecycle/catalog/reverse/refusal remains required |
| C1-MAT-01/P1 OPEN | Private immutable Inbox winning pair/five NULL Job delivery fields source PASS; actual terminal/replay/rollback/reclaim/ACK-loss and precise R3 negative+positive required |
| C1-MAT-02/P2 OPEN | Known T→fresh T2/current-version refusal source PASS; actual maintenance/late File/Resume and positive neighbor required |
| C5-MATERIAL-01/P2 OPEN | Four normal-Worker PHOTO/private-grant journeys source PASS; actual paired browser not reached; no additional product fix requested |
| C2-MAT-02/P2 OPEN | Original-S terminal720 source accepted. Docker29 preparation499.951432356s PARTIAL; neither full state lane passed. Retained600/individual/supervisor/cleanup bounds and3 late C negatives unchanged |
| Separate H-build blocker | Normal state failed before T/P; target/numeric exit/stderr and root cause UNKNOWN. Not attributed to MAT-03; C6 diagnostics require a separate exact-base issuance |
| Final historical CI | Run38850821014/attempt1, tested merge51fca8a26bb19fa511040592a8b04613ddf0eb96/tree fb06ad7…:4 SUCCESS/5 FAILURE; clean4 SUCCESS/5 SKIPPED. No retained migrate traceback/DDL/SQLSTATE; source counterexample is not an observed CI exception |
| R2 local evidence | New regression2 PASS; scoped67 PASS/98 deselected (includes those2); Ruff/format3, diff/allowlist/original11/applied0001–0011/ORIGINAL17/OLD_CHECK4/prefix/source inventory PASS. Cached locked environment; no installs/services/actual PG/Docker/browser/Actions execution |
| Preserved contracts | Entire§15.11 prefix546352 bytes/SHA25679f920fd…;10 columns/6 old tables,4 new/42 total,132 signatures; C6/frozen H/T/C/G/E bytes, V1 replay/hash/decoder, no-refetch, current Turn and initial-suppression proofs |
| Sequential next route | C0 source intake → C6 diagnostics-only task on accepted C3 descendant → combined intake → same PR34 automatic CI → C1/C2/C5 actual/source disposition → later C8. No intermediate head update/new PR/merge/dispatch/rerun |

All actual0012 fresh/populated/repeat/unused reverse/used55000-before-DDL/raw42/catalog/
security/recovery/replay, known-T/current-version and paired PHOTO/browser gates remain;
require both complete state lanes and9/9+clean9/9 on the actual tested SHA/tree.
Source success closes no finding. C3 HOLD after canonical return; C1/C2/C5/C6/C8 HOLD.
Implementation not INTEGRATED/VERIFIED. Gate OFF; native/A08/renewal/collector/live/VM/
working DB/S3/sends/deploy/M4 unissued; broad CI optimization/IMPL-05 DEFERRED.

## История — C6-M3.1-MATERIAL-COMPAT-R2 source checkpoint / 2026-10-16 UTC

**MATERIAL/M3 IN_PROGRESS; PR34 Draft/BLOCKED; all five findings OPEN pending final
source reviews and actual acceptance. C6 REVIEW on return, then HOLD.**
[C0 intake/explicit terminal720 decision](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6207691746),
[C6 five-path task](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6207709114),
[contract/evidence map§15.11](tasks/M3_CONTRACT.md#1511-c0--terminal-material-preparation720-exception--2026-10-16-utc).

| Task / binding | Current source result / remaining gate |
|---|---|
| C6 branch/base | `c6/m3-1-material-compat-r2` from accepted C3 R1 `e7f554772ad4dd697d38c88f4f6423b3d3895499`; tree `0242e71790e0fe441ebc55a6311c80f5681b218f`; parent ef7b52… |
| Main / existing PR34 | Frozen E933ddd…/0011; old PR34 head ef7b52… unchanged by C6. Final C6 head/tree/parent/numstat in one canonical PR34 receipt. No new PR/dispatch/rerun |
| C2-MAT-02 | Explicit exception implemented: retained S+600 and P-only S+720 from original S; all preceding elapsed costs charged. Closed version2 private single-use handoff binds P owner and completed E source/report/hash/cleanup; final preparation charge<720. Finding remains OPEN pending both actual state lanes |
| Bounds / preservation | P remaining+480 → nominal S+1200; shared cleanup90, individual commands, state25/browser25/foundation45,9 jobs/clean9 unchanged. Full T positives/120-timeout/export negatives, C/G/E frozen bodies/requests/ownership, source/image proofs and all3 late C cleanup negatives preserved |
| R1 source companions | Read-only10-column/6-existing-table/42-table/132-signature inventory, private Inbox token, full P_COLUMNS/no-backfill/raw42 used55000-before-DDL/unused exact reverse/ORIGINAL17/OLD_CHECK4 |
| Local evidence | Reused frozen/offline scoped egress+migration units:625 PASS. Targeted protocol/current coordinator/material entrypoint and executed shell gates cover refusal/no runtime, elapsed720 endpoints and primary/secondary/owned cleanup. Static/prefix/frozen checks and exact commands/results in canonical receipt |
| Actual gates | PG/Docker/image builds/paired PHOTO/browser/CI NOT RUN here.720 sufficiency/minimality not established; no additional increase or retry authorized |
| Next C0 route | Source intake → move combined descendant into same Draft PR34 → normal automatic CI9/9+clean9/9 on exact SHA/tree; both P prep<720 and retained negatives/cleanup within state25; actual product PG/PHOTO/browser; C1/C2/C5 re-review then C8 |

Only assigned five paths changed with the substantive protocol correction;
§15.11 appended after the complete immutable§15.10.4 prefix. Earlier evidence below
remains bound to its historical sources. No implementation INTEGRATED/VERIFIED
claim; C3/C1/C2/C5/C8 HOLD, C6 HOLD after canonical return. Gate OFF; no live/VM/
working DB/S3/sends/deploy/native/renewal/collector/M4. IMPL-05 remains DEFERRED.

## История — C3-M3.1-MATERIAL-R1 source correction / 2026-10-16 UTC

**MATERIAL/M3 IN_PROGRESS; PR34 Draft/BLOCKED; findings OPEN pending C0 and actual
acceptance. C3 HOLD after canonical return.**
[C0 R1](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6201238585),
[source and assertion map](tasks/M3_CONTRACT.md#15104-c3-m31-material-r1-correction--2026-10-16-utc).

| Binding / correction | Current result |
|---|---|
| R1 branch / exact parent | `c3/m3-1-material-r1` / `ef7b52d2d862e3d3e656ba56ccac8781e1d0a374`, tree `e4317cc6478b2c40669d96242c3adb89079ab46c` |
| C2-MAT-01 / C1-MAT-01 | Three CASE fixes; immutable Inbox material_result/material_claim_token pair, exact winning replay; all Job delivery fields NULL. Only0012;10 columns/6 old tables,4 new/42 total,132 function signatures |
| C1-MAT-02 / R3-T4 | Fresh input in old quiet window→T2; current-version sticky refusal after GROUP/MEDIA/late File/Resume; Telegram and CONTROLLED GUARDS/Escalation arms. Exact negative SQLSTATE/constraint/reason plus positive neighbor |
| C5-MATERIAL-01 | Four finite PHOTO/private-S3 browser journeys with ordinary Worker mutation; loaded image, caption positive, replacement/type/delete, grant404, real delayed old HTTP response. Source proof written; actual paired execution NOT RUN |
| Local evidence | Ruff/format9,79 targeted Python,68 browser-harness Python, typecheck,32 MessagingPanel tests PASS.121 PG cases collected only. No actual PG/Docker/browser/migration/race/catalog PASS |
| Next gate | C0 source intake→assigned C6 descendant→same PR34 automatic CI and C1/C2/C5 review; C2-MAT-02 budget stays OPEN with C6 |
| Boundaries | Gate OFF; no new PR/dispatch/rerun/PR34-branch push, native/renewal/live/VM/sends/deploy/M4 |

Final SHA/tree/parents/changed paths/numstat are in the single canonical PR34 R1
receipt. Frozen originals/0001–0011/normative§15.2–15.9 unchanged. Historical evidence
below remains attached to its old checkpoint, not to this R1 implementation.

## История — C3-M3.1-MATERIAL source checkpoint / 2026-10-15 UTC

**MATERIAL/M3 IN_PROGRESS; C3 HOLD после source return. A03 NOT VERIFIED.**
[C0 implementation](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6195028336),
[C0 continuation](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6195754984),
[handoff](tasks/M3_HANDOFF.md), [source/evidence§15.10](tasks/M3_CONTRACT.md#1510-material-implementation-source-checkpoint--2026-10-15-utc).

| Задача / факт | Статус и граница evidence |
|---|---|
| Design PR33 | [INTEGRATED по C0](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6194957626); C1-PROV-01…05/C2-PROV-01…04 CLOSED design по [C2 R3](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6193806982)/[C0 acceptance](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6193890730) |
| Implementation base | `933ddd284ff5b77fb1aa88a4270ab0032bc499c9`, tree `d0759acb9f83ec3f3e10d9c5d1325c937c343ee7`, schema0011 |
| C3 source | `c3/m3-1-material`, assigned0012←0011, allowlist57; closed V2 ingress/material/shared bodies and paired API/OpenAPI/TS/UI; executable PG/migration/race/security/browser cases written |
| Local evidence | Ruff149/mypy61/export/typecheck/build PASS; scoped284 unit and93 Vitest PASS.103 PG cases collected only; no actual PostgreSQL execution |
| C6 handoff | Source inventory4 tables/9 columns/23 new+17 replaced functions/17 frozen bodies/used blockers/source-schema pairs§15.10; actual catalog NOT RUN. Reserved6 unchanged, C6 HOLD until separate C0 issuance |
| PG/migrations/races/RLS/API/browser | **NOT RUN — deferred to штатный final candidate CI**; local unavailable services do not block source return under continuation; acceptance remains blocked on actual execution |
| Final candidate | C0 intake→sequential C6 compatibility→one Draft PR assigned by C0→9 automatic jobs+clean-source checks. No PR/dispatch/rerun from C3 source checkpoint |
| M3-A03/P-02/P-03/P-04 | Design accepted, implementation IN_PROGRESS; no runtime/DTO/grant/UI acceptance or activation. Final SHA/tree/parents/paths/numstat in canonical PR33 source receipt |
| C1/C2/C5/C6/C8 | HOLD pending C0 candidate/review assignments |
| Native/A08/P-01/renewal/P-05/collector/P-A03-09/live/VM | Existing OPEN/NOT VERIFIED and TEST interval boundaries preserved; no credentials/VM/sends/deploy issued |
| M3-ACCEPTANCE/M4/IMPL-05/CI optimization | M3 acceptance pending; later work not opened |

Applied0001–0011, original11/manifest, accepted prefix345960 and normative§15
unchanged; no workflows/Compose/dependencies changes. Source evidence is not actual
PG/catalog/browser/account PASS. Historical rows/receipts below remain snapshots,
not current assignments. No status-only commit is required.

## История — C3-M3.1-PROVENANCE-CONTRACT-R3 / 2026-10-15 UTC

**R3 — REVIEW при передаче diff, затем C3 HOLD. M3 — IN_PROGRESS.**
[Поручение C0](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6191877569),
[активный handoff](tasks/M3_HANDOFF.md),
[proposal§15](tasks/M3_CONTRACT.md#15-native-provenance-и-material-editdelete--proposal).

| Задача / факт | Текущий статус и граница evidence |
|---|---|
| Accepted main/base / schema | `bae25093bafb9534af68de5c586763667b896e70` /0011; applied0001–0011 immutable; следующий revision/order не назначены |
| R3 start / sole parent / tree | `165dd09b0138c66216a8a7d8240af95663165769` / tree `f619c5ebad814141d0db0f9cbafccc6cd2089200` |
| C3 R2 delivery/intake | [C3 receipt](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6190608696), [C0 intake](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6191327158), сохранены |
| C1 R2 | [PASS revised design](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6191616132); C1-PROV-01…05 CLOSED, без implementation acceptance |
| C2 R2 | [CHANGES_REQUESTED](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6191712300); C2-PROV-01…03 CLOSED revised design, единственный обязательный C2-PROV-04/P2 OPEN |
| C3 R3 | REVIEW: один commit поверх R2, тот же Draft PR33/branch→main, ровно3 docs. INITIAL_FOLD_SUPPRESSED member/evidence и общие grouping/seal/snapshot/readiness; R3-01…04→§15.4/7/9, traces R3-T1–T5. Finding не закрывается C3 до C0 acceptance |
| C1/C2/C5/C6/C8 | HOLD. После intake C0 выдаст только адресный C2 re-review C2-PROV-04/shared bodies/locks; полный C1 review не нужен при неизменном API/current DTO |
| R2 CI | [38724672096/attempt2](https://github.com/Elefesys/ai-service-manager/actions/runs/38724672096), aggregate9/9+clean9/9 SUCCESS по C0; не evidence нового R3 head и не future V2 PG PASS |
| TURNS/CONTROL/GUARDS/Escalation/Console | Прежняя INTEGRATED/VERIFIED LOCAL/TEST приёмка сохранена; accepted0011/runtime не переоткрыт |
| M3-A03 / P-02 / P-03 | Revised design остаётся REVIEW из-за C2-PROV-04; согласованные R2 ordering/codec/current DTO и выбранная no-refetch policy сохранены. Implementation/UI/grant/final acceptance NOT VERIFIED |
| M3-A08 / P-01 | OPEN/NOT VERIFIED: native/latest-state не закрыт. Console canonical reply — поддержанный resumable path; native-only HUMAN до принятого reconciliation; actual0011 не содержит новой Resume block |
| P-04/P-05 / TEST / VM | OPEN; implementation/renewal/probe не выданы. Старый TEST interval истёк, оба новых окна не подтверждены; VM UNKNOWN/live BLOCKED_TEST_INTERVAL |
| M3-ACCEPTANCE / M4 / CI optimization / IMPL-05 | M3 acceptance впереди; M4/optimization/IMPL-05 не открываются |

Scope/prefix345960 bytes/original11/manifest/history/link/diff checks и manual traces
достаточны. Новый canonical R3 receipt содержит final SHA/parent/tree/numstat и actual
automatic CI; old R2 green не переносится, status-only commit не нужен. Product suites/
Docker/Actions dispatch/rerun/VM/live/DB/S3/sends/deploy не запускаются. Future allowlist
остаётся proposal, PR Draft; merge пользователем после приёмки. Старые receipts и
historical tails ниже сохранены, их прежние active формулировки не новые поручения.


## История — C3-M3.1-PROVENANCE-CONTRACT-R2 / 2026-10-15 UTC

**R2 — REVIEW при передаче diff; затем C3 HOLD. M3 — IN_PROGRESS.**
[Выдача R2](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6189981613),
[решение C0](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6189999448),
[активный handoff](tasks/M3_HANDOFF.md),
[исправленный proposal§15](tasks/M3_CONTRACT.md#15-native-provenance-и-material-editdelete--proposal).

| Задача / факт | Статус и граница evidence |
|---|---|
| Accepted main/base | `bae25093bafb9534af68de5c586763667b896e70`, schema0011; applied0001–0011 immutable |
| R2 start / sole parent / tree | `f5e71ff47f000ee55a5509cae4ec22487ca8b6c2` / tree `9b91c33724e4f847c8febfbeb24bcf42188e4713` |
| C3-M3.1-PROVENANCE-CONTRACT, initial | [C3 receipt](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6188075575) сохранён; [C0 intake](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6188855331), initial CI38707131575/attempt1 9/9 SUCCESS+clean9/9 по C0 |
| C1 / C2 read-only reviews | Завершены [C1 CHANGES_REQUESTED](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6189743405) / [C2 CHANGES_REQUESTED](https://github.com/Elefesys/ai-service-manager/pull/33#issuecomment-6189782680); C0 подтвердил findings. C1/C2 HOLD, повторный review только по новому поручению |
| C3 R2 | Тот же Draft PR33/branch→main, один содержательный commit, ровно3 docs: existing§15 по месту + handoff/register. R2-01…08 и все C1/C2 findings→§15.9. REVIEW, затем HOLD; implementation NOT VERIFIED |
| C5/C6/C8 | HOLD; новой UI/infra/probe/test задачи нет |
| TURNS/CONTROL/GUARDS/Escalation/Console PR32 | Прежняя INTEGRATED/VERIFIED LOCAL/TEST приёмка сохранена; initial review не findings против accepted runtime |
| M3-A03 / P-02 | C0 сохранил per-target/deferred/sticky suppression policy; revised undated ordering/unions/constraints и implementation ждут адресной приёмки/evidence |
| M3-A03 / P-03 | C0 выбрал no-refetch ограниченного material slice: MEDIA_REPLACED_UNAVAILABLE, PARTIAL, новое фото не открывается/не анализируется. Current DTO/grant/UI/full M3 ещё NOT VERIFIED |
| M3-A08 / P-01 | OPEN/NOT VERIFIED: candidate-only не canonical human context. Console-only canonical reply — resumable path; native-only HUMAN до принятого reconciliation, без duplicate send. Actual0011 не блокирует Resume по полноте transcript |
| P-04 / P-05 | OPEN: отдельные revisions/order/source/allowlists; выбран future append subscription+CAS current NORMAL/PROVISIONED_LOCAL mode, immutable before/after/Audit/replay исходных дат. Команда/renewal/collector/live не выданы |
| TEST / VM | Старый interval истёк2026-10-09T00:00Z, оба новых окна не подтверждены; VM UNKNOWN, live BLOCKED_TEST_INTERVAL. Collector-only не требует A03, но требует exact actual schema/interval |
| M3-A10 / M3-ACCEPTANCE / M3-A12 | Прежняя UI/control приёмка сохранена; новый material current view вне неё. Финальная M3 acceptance после A03/A08 и применимого TEST/account evidence |
| CI optimization / IMPL-05 / M4 | DEFERRED/не открыты; budgets/jobs/clean guards прежние |

Chosen policy, revised-contract acceptance, implementation и account evidence не
смешиваются. Static checks/traces достаточны для docs; final SHA/tree/numstat и actual
automatic PR CI будут в одном **новом** canonical R2 receipt. Initial-head green не R2
PASS. Status-only commit после CI не нужен; старые C3/C1/C2 comments не изменяются.
Product suites/Docker/Actions dispatch/rerun/VM/live/DB/S3/sends/deploy не выполняются.
C0 назначает адресный повторный review; PR остаётся Draft, merge только после приёмки.
Ниже сохранена история; её старые active/status формулировки не разрешают новую работу.


## История — C3-M3.1-PROVENANCE-CONTRACT / 2026-10-15 UTC

**C3 — IN_PROGRESS. M3 — IN_PROGRESS.** Единственный автор design slice;
C1/C2/C5/C6/C8 HOLD до адресного поручения C0.
[Выдача C0](https://github.com/Elefesys/ai-service-manager/pull/32#issuecomment-6185468957),
[активный handoff](tasks/M3_HANDOFF.md), [proposal§15](tasks/M3_CONTRACT.md#15-native-provenance-и-material-editdelete--proposal).

| Принятый факт / задача | Статус и evidence |
|---|---|
| C5-M3.2-CONSOLE-ESCALATIONS, PR32 | **INTEGRATED / VERIFIED LOCAL/TEST** по [C0 receipt](https://github.com/Elefesys/ai-service-manager/pull/32#issuecomment-6184721998); [C8 UI-E01–07 PASS](https://github.com/Elefesys/ai-service-manager/pull/32#issuecomment-6180763886), findings нет |
| Actual main / exact C3 base | `bae25093bafb9534af68de5c586763667b896e70` |
| Tree / ordered parents | `ad857f156e6ff7ebb23a18c4b127256e774dd7bd`; `ab06bc135f45c88203e434eacefd107412a8eb15` + `ad161ce0e04f6271890458cbec56681199846df8` |
| Actual main CI | [38684447412/attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/38684447412),9/9 SUCCESS+clean9/9; checkout exact main по C0 |
| Accepted baseline |1153 unit/680 PG/79 Escalation PG/294 frontend/39 browser PASS; schema0011 |
| TURNS/CONTROL/GUARDS/Escalation backend/API и оба Console среза | Прежние **INTEGRATED / VERIFIED LOCAL/TEST** границы; не переоткрывать без конкретного противоречия |
| C3-M3.1-PROVENANCE-CONTRACT | **IN_PROGRESS**; `c3/m3-1-provenance` от exact base; только append§15+две coordination docs, новый Draft PR→main |
| M3-A03 | Новый proposal material edit/delete; runtime не выдан. P-02 increments/ordering/Turn и P-03 replaced-photo limitation требуют решения C0 |
| M3-A08 | Native provenance/account observability **NOT VERIFIED**. P-01 strict post-Resume causality не обеспечивается Bot API; explicit Console/manual alternative на решение C0 |
| M3-A10 | Owner control/in-flight и Escalation UI приняты в границах PR30/PR32; новый material view не входит в прошлую приёмку |
| M3-ACCEPTANCE / M3-A12 | Впереди после решения A03/A08 и применимого TEST/live evidence; весь M3 не VERIFIED |
| TEST/account probe | Только finite plan§15.8; прежний interval истёк2026-10-09T00:00Z; поддержанный renewal/collector и actual runtime требуют отдельной выдачи |
| CI optimization / IMPL-05 fix | **DEFERRED**; budgets/jobs/clean guards прежние |
| M4/LLM/production rollout | Не открыты этой выдачей |

P01–P06 и фактические OPEN P-01–05 описаны в§15. Existing V1 hashes/receipts/original11
immutable, ignored history не переигрывается. Native и material activation независимы.
Design static checks достаточны; final source/actual automatic PR CI фиксируются
в одном canonical C3 receipt без status-only commit после CI. Старый main GREEN не
новый-head evidence. Product tests/Docker/dispatch/rerun/VM/live/sends не выполняются.
Возврат REVIEW/BLOCKED, затем HOLD; C0 назначает C1/C2/C6 после конкретного решения.


## История — C5-M3.2-CONSOLE-ESCALATIONS / 2026-10-14 UTC

**C5 — IN_PROGRESS. M3 — IN_PROGRESS.** Единственный автор нового owner-wait UI;
C1/C2/C3/C6/C8 HOLD до следующего конкретного gate.
[Выдача C0](https://github.com/Elefesys/ai-service-manager/pull/31#issuecomment-6172495208)
и [C0 main acceptance](https://github.com/Elefesys/ai-service-manager/pull/31#issuecomment-6170928749).

| Принятый факт / задача | Статус и evidence |
|---|---|
| C3-M3.2-ESCALATION backend/API, PR31 | **INTEGRATED / VERIFIED LOCAL/TEST** по C0;0011/down0010 |
| Accepted main / C5 base | `ab06bc135f45c88203e434eacefd107412a8eb15` |
| Tree / ordered parents | `3c97459793bd200dfe9720b37ea0895b4189a8bb`; `c502d5fd258aef15bb5549e1529df8d038a4fb9b` + `09d92a141ae5b2f000b9de27e562c1d7a3fd791f` |
| Actual main CI | [38584344077/attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/38584344077),9/9 SUCCESS + clean9/9; checkout actual main |
| Accepted baseline |1133 unit/680 PG,79 Escalation (61+9+9),194 frontend/33 browser PASS; foundation115922197802/browser115922197945 |
| Findings | C8-M3-ESC-01/P2 CLOSED; C6-ESC-COMPAT-01 CLOSED по C0 |
| C5-M3.2-CONSOLE-ESCALATIONS | IN_PROGRESS, отдельный checkout/`c5/m3-2-console-escalations` от exact base; новый Draft PR→main |
| M3-A10 | CONTROL/in-flight принят ранее; owner-wait UI в этой задаче, UI-E01–07 |
| M3-A03/A08 native/edit-delete provenance и M3-ACCEPTANCE | Следующие отдельные задачи; весь M3 не VERIFIED |
| CI optimization / IMPL-05 fix | DEFERRED; budgets/jobs/clean guards неизменны |

Реализация: queue/detail, строгие четыре routes, internal answer/cancel,
memory-only same-key recovery, shared owner deny и canonical context notice.
[Активный handoff](tasks/M3_HANDOFF.md) и [UI rules/evidence map](tasks/M3_CONSOLE_ESCALATIONS.md).
Docs входят вместе с содержательным UI diff, без coordination-only/SHA-only commits.
Local Docker отсутствует: actual HTTP/PG/browser evidence нужен из final-source
штатного PR CI9/9+clean9/9. Итоговый head/parent/tree/tested merge/jobs/results
будут в одном canonical C5 PR receipt; pre-CI snapshot ниже не заменяет этот receipt.
Возврат REVIEW или конкретный BLOCKED, затем HOLD → C0 intake → scoped C8 → C0.
Draft/merge/production/live/VM не выданы. M4/LLM/Approval/Notifications вне scope.

## История — C6-M3-FOUNDATION-TIME-BUDGET / 2026-10-14 UTC

**C6 — IN_PROGRESS. PAGE-R1 acceptance — BLOCKED незавершённым CI.
C3 HOLD; C8 HOLD. C8-M3-ESC-01/P2 OPEN. Весь M3 — IN_PROGRESS.**
[Выдача C0](https://github.com/Elefesys/ai-service-manager/pull/31#issuecomment-6168070726)
разрешает только foundation40→45 и три coordination docs одним содержательным
commit. Scope/проверки — [M3_HANDOFF§0](tasks/M3_HANDOFF.md), текущий override
и неизменные границы — [M3_CONTRACT§14.17](tasks/M3_CONTRACT.md).

| Факт / gate | Значение |
|---|---|
| Exact C6 base | `0dd8a3490cfccf7fb613c169f3bd5116373827fd` |
| Sole parent / tree | `c413a6f80b30fbdd12717af3f12642a5b5f785f4` / `c21d936d22b85fe849296f06650f800ff459b6b1` |
| Accepted main / frozen G | `c502d5fd258aef15bb5549e1529df8d038a4fb9b`,0010 |
| Previous tested merge | `f5409011ccf81223b6bc1f1286766c866779da85`; ordered parents main+base, tree=base tree |
| Previous final-source CI |38549789284/attempt2:8 SUCCESS/1 CANCELLED; clean8 SUCCESS/1 SKIPPED; BLOCKED |
| Foundation attempt1 / attempt2 |115804663667:40m21s /115821443996:40m19s; основной step40m13s в обеих попытках при лимите40 |
| Actual PAGE-R1 tests |1133 non-integration/680 PG PASS;79 Escalation=61 domain+9 API+9 migration; HTTP/reverse-proxy smoke не завершён |
| Cancellation evidence |`The operation was canceled.`; отдельная административная причина не подтверждена, test failure в прочитанных C0 логах не обнаружен |
| Current budget |Только foundation job40→45; остальные workflow bytes и budgets сохранены |
| New final-source evidence |PENDING: один новый штатный PR CI9/9+clean9/9 без SKIPPED и actual smoke/source records; старые8 SUCCESS не переносятся |
| Next owner gate |C0 source/CI intake, затем только C8-M3-ESC-01 и затронутые ESC-C02/07; finding OPEN до решения C0 |
| C6-ESC-COMPAT-01 |CLOSED; повторный controller review/fault matrix не назначен |

После canonical C6 receipt — HOLD. При новом cancelled/failed вернуть точный
BLOCKED; без rerun/нового повышения45 и без status/SHA-only commits после CI.
C3/C8 authored receipts и вся история сохранены. C5 owner-wait/native/provenance/
M3 acceptance впереди; IMPL-05 fix и CI optimization DEFERRED. VM/live Telegram/
рабочие DB-S3/deploy/merge не выданы.

<details>
<summary>История PAGE-R1 и предыдущих статусов; текущий статус C6 приведён выше</summary>

## Текущий статус — C3-M3.2-ESCALATION-PAGE-R1 / 2026-10-14 UTC

**PAGE-R1 — IN_PROGRESS. C8-M3-ESC-01/P2 OPEN. Весь M3 — IN_PROGRESS.**
[Выдача C0](https://github.com/Elefesys/ai-service-manager/pull/31#issuecomment-6164474811)
снимает C3 HOLD только для required page observed_at по принятому§14.5.
Scope9 paths и критерии — [M3_HANDOFF§0](tasks/M3_HANDOFF.md); correction/evidence
append — [M3_CONTRACT§14.16](tasks/M3_CONTRACT.md). Один Draft PR31/прежняя ветка.

| Принятый факт / gate | Значение |
|---|---|
| Continuation base | `c413a6f80b30fbdd12717af3f12642a5b5f785f4` |
| Base tree / sole parent | `1a87601835bd9646e40f62e399f0b71304e28abc` / `9d65a69c47d26ceacdb5f3093d14720c5d40e779` |
| Main/frozen G | `c502d5fd258aef15bb5549e1529df8d038a4fb9b`,0010 |
| Reviewed base execution |38525189666/attempt1,9/9 SUCCESS+clean9/9;1122 non-integration/679 PG,78 Escalation,194 frontend/33 browser |
| Reviewed tested merge | `1b4dcd13a482a2efe0cc148499078711c468928d`; main+base, tree=base |
| C8 implementation review | CHANGES_REQUESTED: один page wire defect; остальные ESC-C01/03/04/05/06 и проверенная часть02/07 PASS |
| PAGE-R1 local regression | До fix24 PASS/7 FAIL; после31 PASS/9 integration deselected; Ruff/mypy/contracts/original11 PASS |
| Local actual HTTP/PG | NOT RUN: Docker отсутствует; new raw page case только collected |
| New source gates | CI9+clean9/actual PG79/E compatibility ещё PENDING; base GREEN не переносится |
| Finding disposition | OPEN до проверки C0/scoped C8; C3 после evidence возвращает REVIEW/HOLD |
| C6-ESC-COMPAT-01 | CLOSED, новый controller review не назначен |

Correction касается только list SQL envelope→service→page/schema; business lifecycle
не меняется. Все78 прежних PG cases сохранены, добавлен1 page regression. Бюджеты,
controller/pins/dependencies/workflows/Compose/frontend и0001–0010 неизменны.
Единственный [C3 receipt](https://github.com/Elefesys/ai-service-manager/pull/31#issuecomment-6152762197)
содержит final source/results и сохраняет reviewed checkpoint/history; docs после
CI отдельным status-only commit не обновляются. M3 acceptance/C5 owner-wait/native
provenance впереди, M4/LLM/Approval/Notifications вне scope, IMPL-05 fix и CI
optimization DEFERRED. VM/live/рабочие DB-S3/deploy/merge не выданы.

<details>
<summary>История implementation до PAGE-R1; не активный статус</summary>

## Текущий статус — Escalation implementation продолжена после C6 review

**C3-M3.2-ESCALATION-IMPLEMENTATION — IN_PROGRESS. Весь M3 — IN_PROGRESS.**
[Выдача C0](https://github.com/Elefesys/ai-service-manager/pull/31#issuecomment-6151237330) заменяет contract-only HOLD.
[Решение C0 о продолжении](https://github.com/Elefesys/ai-service-manager/pull/31#issuecomment-6161454304)
сняло scope HOLD: corrected C6 replacement и дополнительный route path разрешены.
Один Draft PR31, `c3/m3-2-escalation`, отдельный checkout, без reset/rebase/merge.
Полные разрешённые paths и критерии — [активный M3_HANDOFF§0](tasks/M3_HANDOFF.md).

| Принятый факт | Exact value / статус |
|---|---|
| Accepted main / frozen G / schema | `c502d5fd258aef15bb5549e1529df8d038a4fb9b` /0010 |
| Implementation start / tree | `65454012c0e5a2c9643bf1401d86773a5a4df29a` / `de09e1bf435d15929059f4e7691bd1fa17c0f2a4` |
| Start CI | [38430231534/attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/38430231534), SUCCESS9/9 + clean9/9 |
| Actual tested start merge | `2650c69c48c0e882317e6ca6a68cda18f26918ed`; parents main+start, tree=start |
| R2 contract | Принят C0;331348bytes/blob `3d2f88ddedf0ab9944db3181040abe16a7034e81` |
| Три design findings | CLOSED по verdict C0; legacy-overload claim NOT CONFIRMED |
| C3 refresh / C6 observer diagnostics | Оба приняты; исторические причины UNKNOWN; расследование прекращено |
| Migration queue | `0011_escalations.py`, revision0011/down0010 назначена C0; applied0001–0010 immutable |
| Start CI blockers | Нет; E runtime ещё не VERIFIED |

| Задача / решение | Статус | Следующий шаг |
|---|---|---|
| M0/M1/M2, M3.1-TURNS/CONTROL/GUARDS | Прежние INTEGRATED / VERIFIED LOCAL/TEST границы | Не переоткрывать без конкретного дефекта |
| C5-M3.2-CONSOLE-CONTROL | INTEGRATED / VERIFIED LOCAL/TEST, PR30 | M3-A10 только принятый control/in-flight scope |
| C3-M3.2-ESCALATION-CONTRACT | Принят C0 | Baseline§14 сохранить, evidence отдельно после14.11 |
| C3-M3.2-ESCALATION-IMPLEMENTATION | IN_PROGRESS | Подготовленный domain/API/0011/tests; runtime gates ещё не пройдены |
| E compatibility checkpoint | C6 review завершён; exact corrected replacement APPROVED C0 и применён |41783bytes/hash`2c63dc567c151c8c6be0be342f98f19eb947b6f355ad43a202bd76367140b0f8`; actual G→E и время ещё требуют CI |
| C6-ESC-COMPAT-01/P2 | Исправление принято C0, source integration предъявляется | G export сохраняет primary/secondary/private evidence; verdict фактического diff за C0 |
| Route inventory scope blocker | Закрыт решением C0; exact diff применён |1268bytes/hash`501b68c29f740cf57490b2129b5633db694ecde8e70e23c023773390bd060a3e`; максимум43 paths; четыре routes добавлены в closed equality,7 auth assertions прежние |
| C8 scoped implementation review | TODO | C0 выдаёт после готового candidate |
| C5 owner-wait/Escalation UI | TODO | После принятого backend/API SHA |
| Native-owner/edit-delete provenance; M3-ACCEPTANCE | TODO / NOT VERIFIED | Прежние отдельные gates/evidence |
| IMPL-05 | OPEN; fix DEFERRED | Не включать в эту задачу |
| C6-CI-FOUNDATION-SPLIT / CI optimization | BLOCKED / DEFERRED до завершения M3 | PR29 закрыт без merge; C6-CI-SPLIT-01 CLOSED только experimental4dc2c32, -02 OPEN |

Исторический checkpoint373aeaf: local1113 PASS/1 FAIL из-за старого total route
inventory; CI38448949685/attempt1 FAILURE5 SUCCESS/4 FAILURE, clean5/4 SKIPPED.
Исходный controller proposal hash78762113… отклонён: export мог заменить
primary failure. Этот checkpoint сохранён непосредственным parent продолжения;
неполный старый source повторно не запускается. Accepted contract prefix прежний.

Текущий candidate не является REVIEW готового runtime. Docker локально недоступен;
actual PG/S3/relay/browser/Docker29 и final CI9/9+clean9/9 требуются на final source.
Точные commands/results/head/tree/parent, archives, matrix и ограничения — один
обновляемый [C3 receipt](https://github.com/Elefesys/ai-service-manager/pull/31#issuecomment-6152762197),
без документационных SHA commits. Затем C0/scoped C8 и actual main gates.
C3 сам роли не назначает. OPEN082/083/085, M4/LLM/RAG, Approval/M6, Notification
Engine/M9 и client follow-ups прежние. VM/live/рабочие DB-S3/deploy/merge не выданы.

Матрица§14.9 дополнена21 PG case в двух разрешённых новых test modules: всего78
collected, не local actual PG. Полный local non-integration1122 PASS/0 FAIL.
Controller/dependency/pins/budgets и production source остаются прежними;
source-bound runtime результаты и оставшиеся gates ведутся в canonical receipt.
Первый actual CI нового controller:8 jobs SUCCESS/1 foundation FAILURE,
clean8 SUCCESS/1 SKIPPED;650 PG PASS/8 FAIL. Исправляются семь новых fixture
assumptions об ordinary TEST_CONSUME и старый exact function inventory;
полные assertions/grants сохранены. Новый source требует всех final gates заново.

Второй actual CI:675 PG PASS/4 FAIL,8 jobs SUCCESS/1 FAILURE и clean8/1 SKIPPED.
Прежние8 failures устранены; четыре новых — SELECT `id` вместо Guard `job_id`
и display-ожидание schema prefix в pg_get_constraintdef. Test-query corrections
сохраняют exact target OID/SQLSTATE/rollback и все78 cases;§14.15 фиксирует причины.
Production/controller/DDL/pins неизменны; final-source CI и scoped C8 ещё OPEN.


</details>

<details>
<summary>История выдачи ESCALATION-CONTRACT; заменена implementation выдачей C0</summary>

## Текущий статус — CONTROL UI закрыт; Escalation contract выдан / 2026-10-13 UTC

**M3.1-TURNS/CONTROL/GUARDS и C5-M3.2-CONSOLE-CONTROL —
INTEGRATED / VERIFIED в принятых LOCAL/TEST границах. Весь M3 — IN_PROGRESS.**

Accepted main после PR30: `c502d5fd258aef15bb5549e1529df8d038a4fb9b`,
tree `9ed2c0cd679d1577b93998c5a429c90e4b810588`, schema0010.
[C0 post-merge receipt](https://github.com/Elefesys/ai-service-manager/pull/30#issuecomment-6142120541)
и [main CI38374030362](https://github.com/Elefesys/ai-service-manager/actions/runs/38374030362),
attempt1: **9/9 SUCCESS + clean9/9;1089 unit/597 PG/192 frontend/33 browser**.
Actual merge tree совпадает с принятым candidate; checkout main подтверждён
во всех9 job logs. [C8 PASS](https://github.com/Elefesys/ai-service-manager/pull/30#issuecomment-6141996856)
и UI-C01–07 приняты. Новые прогоны C0 не запускались.

### Активная выдача

**C3-M3.2-ESCALATION-CONTRACT — IN_PROGRESS.**
Ветка `c3/m3-2-escalation`, отдельный checkout от C0 preparation,
sole parent=accepted main. Точный start/head/tree — в GitHub выдаче.
Подготовка меняет только этот реестр и [M3_HANDOFF](tasks/M3_HANDOFF.md).

Единственный разрешённый сейчас path C3 — `docs/tasks/M3_CONTRACT.md`:
добавить минимальный §14 в конец, сохранив полный прежний prefix238882bytes,
blob `1763a5379926e4ae3e47483faf91b006e5bc4f30`.
Два C0 docs C3 не редактирует; runtime/DDL/API/UI ещё не выданы.
Полная задача — **M3_HANDOFF§0**: separate owner wait lifecycle, origin/authority,
dedupe/resolve/cancel/expiry/reminders, minimal owner API/DB proposal,
relevance/CONTROL compatibility и будущий конкретный implementation scope.

Это начало следующего backend/API-среза исходного M3.2. Один Draft PR после
содержательного contract diff; после согласования реализация продолжится в нём.
Coordination-only PR/CI и status-only commits не создавать.
C0 intake → адресные C1/C2 reviews → C0 revision/allowlist → implementation C3
→ independent C8 → merge пользователем → actual main CI.
C6 нужен только при обоснованной дельте CI/migration controller.
Сейчас один исполнитель C3; C5/C1/C2/C6/C8 новой параллельной задачи не получили.

### Очередь и решения

| Задача / решение | Статус | Следующий шаг |
|---|---|---|
| M0/M1/M2 | Принятые VERIFIED границы сохранены | Не переоткрывать без конкретного дефекта |
| M3.1-TURNS/CONTROL/GUARDS | INTEGRATED / VERIFIED LOCAL/TEST | Принятые PR26/27/28 |
| C5-M3.2-CONSOLE-CONTROL | INTEGRATED / VERIFIED LOCAL/TEST | PR30/main, UI-C01–07; M3-A10 только control/in-flight |
| C3-M3.2-ESCALATION-CONTRACT | IN_PROGRESS | Один §14; proposal для C0/C1/C2 |
| M3.2-ESCALATION backend/API | IN_PROGRESS на стадии контракта; код ещё не разрешён | После принятого proposal точная выдача C3 в том же PR |
| M3.2-CONSOLE, owner-wait/Escalation | TODO | C5 после принятого backend/API SHA |
| Native-owner/edit-delete provenance | TODO / NOT VERIFIED | Отдельные account evidence и решение C0 |
| M3-ACCEPTANCE | TODO | Оставшиеся M3-A01–12, scoped C8/main/operator evidence |
| C6-CI-FOUNDATION-SPLIT | BLOCKED; решение DEFERRED до завершения M3 | PR29 закрыт без merge; ветка/evidence сохранены |
| C6-CI-SPLIT-01 | CLOSED только на experimental head4dc2c32 | В main не интегрирован |
| C6-CI-SPLIT-02 | OPEN; investigation/fix DEFERRED | Вернуться после всего M3 |
| IMPL-05 | OPEN; fix DEFERRED | Прежний nonblocking P3 только LOCAL/TEST |

**Migration queue:** schema0010 применена и immutable. Новая revision не назначена;
C3 предлагает минимальную дельту, C0/C2 принимают её до кода.
Applied0001–0010, canon, existing CONTROL/manual/auth contracts не менять.
Прежние9 CI jobs, foundation40/browser25 и остальные budgets/pins сохранены;
PR29/clock fixtures не переносить. OPEN-082/083/085 остаются в принятых границах.

В следующем handoff исправлено ошибочное фактическое описание прежнего C0:
`manual_delivery` flags actual0010 фильтруют SEND_MANUAL_TEXT по принятому
M3_CONTRACT§13.5, все OUTBOUND statuses видны в истории. Это исправление описания,
код/архитектура не пересматриваются; см.PR30 receipt.

Escalation resolve/cancel/expiry не снимают HUMAN; роли/Client/relevance и typed
domain state остаются авторитетными. Нет внешних notifications, client follow-ups,
Approval/M4/LLM или придуманного production SLA. VM/live/deploy/merge не выданы.
Фактические PR/head/CI/verdict обновляются в GitHub receipts; следующий substantive
handoff актуализирует этот реестр без самоссылочных SHA commits.

</details>

<details>
<summary>История выдачи CONSOLE-CONTROL; завершена PR30</summary>

## Текущий статус — GUARDS принят; CONSOLE-CONTROL выдан / 2026-10-13 UTC

**M3.1-TURNS/CONTROL/GUARDS — INTEGRATED / VERIFIED в принятых LOCAL/TEST
границах. Весь M3 — IN_PROGRESS.** Пользователь поручил продолжить реализацию;
C0 выдаёт C5 первый UI-срез M3.2 на существующем CONTROL API.

Accepted main: `4b63d9ad59fee3631b4314211aaae40884488c98`, tree
`0db9939107435dec730c8963af5e686fa0f818ce`, schema0010.
[GUARDS post-merge C0](https://github.com/Elefesys/ai-service-manager/pull/28#issuecomment-6137086496);
[main CI38338767227](https://github.com/Elefesys/ai-service-manager/actions/runs/38338767227)
**9/9 SUCCESS + clean9/9; 1082 unit/597 PG/114 frontend/27 browser**.
C1/C2/C6/C8 GUARDS reviews завершены и приняты; их findings не переоткрываются.

### Активное поручение

**C5-M3.2-CONSOLE-CONTROL — IN_PROGRESS, implementation разрешена.**
Ветка `c5/m3-2-console-control`, отдельный checkout. Точный старт — C0
preparation commit с sole parent=accepted main, меняющий только этот реестр и
[M3_HANDOFF](tasks/M3_HANDOFF.md). Полный SHA/tree — в GitHub выдаче C0.
C5 продолжает подготовленную ветку и открывает новый Draft PR после реального
UI diff; отдельного contract-only/coordination-only PR не требуется.

Полная выдача — **[M3_HANDOFF §0](tasks/M3_HANDOFF.md)**:
mode/Takeover/Resume, current-state read, pending intent/replay, in-flight/UNKNOWN
и сохранённый manual flow. Exact scope **14 paths** плюс два C0 preparation docs
в full PR; C5 не редактирует эти два coordination docs. Backend/API/schema,
applied migrations0001–0010, M3_CONTRACT и весь canon frozen.
Contract238882bytes/blob `1763a5379926e4ae3e47483faf91b006e5bc4f30` неизменен.

C0 уточняет порядок внутри M3.2: UI принятого CONTROL можно реализовать сейчас,
поскольку его API уже проверен; Escalation пока не имеет своего API.
**CONSOLE-CONTROL → ESCALATION backend/API → Console ожидания/Escalation →
оставшиеся native/provenance gates и M3-ACCEPTANCE.**
Это небольшие срезы прежних milestones, не новые этапы. Один implementation
writer/PR за раз; C3 и остальные роли сейчас не получают параллельной выдачи.
M3-A10 по этой задаче — только control/in-flight; owner-wait UI остаётся TODO.

### Очередь и решения

| Задача / решение | Статус | Следующий шаг |
|---|---|---|
| M0/M1/M2 и прежние LOCAL/TEST verdicts | Принятые VERIFIED границы сохранены | Не переоткрывать без конкретного дефекта |
| M3.1-CONTRACT | VERIFIED в принятом TURNS/CONTROL/GUARDS scope | Escalation design относится к следующей выдаче |
| M3.1-TURNS | INTEGRATED / VERIFIED LOCAL/TEST | PR26/T |
| M3.1-CONTROL | INTEGRATED / VERIFIED LOCAL/TEST | PR27/C |
| M3.1-GUARDS | INTEGRATED / VERIFIED LOCAL/TEST | PR28/main0010, ссылка выше |
| C5-M3.2-CONSOLE-CONTROL | IN_PROGRESS | C5 реализация от C0 start; UI-C01–07 |
| M3.2-ESCALATION | TODO | Следующий backend/API-срез C3 после control UI |
| M3.2-CONSOLE, owner-wait/Escalation часть | TODO | После принятого Escalation API |
| Native-owner/edit-delete provenance | TODO / NOT VERIFIED | Отдельное account evidence и решение C0 до соответствующего кода/приёмки |
| M3-ACCEPTANCE | TODO | Все применимые M3-A01–12, scoped C8 и main evidence |
| C6-CI-FOUNDATION-SPLIT | BLOCKED; решение DEFERRED до завершения M3 | PR29 закрыт без merge, ветка/evidence сохранены |
| C6-CI-SPLIT-01 | CLOSED только на experimental head4dc2c32 | В main не интегрирован |
| C6-CI-SPLIT-02 | OPEN; investigation/fix DEFERRED | Вернуться к оптимизации после всего M3 |
| IMPL-05 | OPEN; fix DEFERRED | Прежний nonblocking P3 только LOCAL/TEST по C0 |

[Решение по оптимизации](https://github.com/Elefesys/ai-service-manager/pull/29#issuecomment-6139376486):
обе попытки не дали полного successful CI,17:13 не является доказанным ускорением.
Из experimental branch в эту реализацию ничего не переносить. Прежние 9 jobs,
foundation40/browser25 и остальные budgets/pins сохранены; новых CI экспериментов нет.

Migration queue: **0010 уже применена и immutable. Новая revision сейчас
не резервируется и не разрешается.** Для будущей Escalation схему/API/DDL queue
назначит C0 отдельной выдачей после проверки потребности.
GUARDS-POLICY-01/02, GUARDS-DB-01/COMPAT-01 приняты; IMPL-01/02/03/04 CLOSED.
Исторический P2 verdict IMPL-05 не переписан; fix не выдан за выполненный.

### Приёмка текущего среза

C5 возвращает один exact-source candidate/receipt: REVIEW либо конкретный BLOCKED.
Нужны сохранённые старые frontend/browser scenarios, адресные UI-C01–07 и actual
full CI9/9 + clean9/9. C0 intake → независимый C8 по новому UI → решение C0 →
merge пользователем → main CI. Новый общий backend/DB/security audit не требуется.
Финальные SHA/run/status публикуются в receipt и C0 metadata; status-only commits
не создавать. Следующая содержательная выдача обновит этот реестр.

Native/live/production, M4/LLM, внешние owner notifications и клиентские follow-ups
не включаются. Цель — работающий MVP и корректные owner/tenant/Client/idempotency
границы без нового framework. VM/рабочие DB-S3/deploy/merge не выдаются C5.

</details>

<details>
<summary>История завершённых выдач до CONSOLE-CONTROL; активный статус выше</summary>

## Текущий статус — GUARDS contract принят; реализация выдана / 2026-10-12 UTC

**M3.1-CONTROL — INTEGRATED / VERIFIED LOCAL/TEST. M3.1-GUARDS и M3 —
IN_PROGRESS.** Пользователь слил PR27; accepted main/frozen C
`c6a55b6b17d1c1ab286ce97dfa4bd27197141fe5`, tree
`d7f0dbd35a637877b57d721cbb6a39c6ef59eae4`, schema0009.
[Main CI38209943421](https://github.com/Elefesys/ai-service-manager/actions/runs/38209943421)
9/9 SUCCESS + clean9/9; [C0 post-merge receipt](https://github.com/Elefesys/ai-service-manager/pull/27#issuecomment-6118563610).
TURNS/CONTROL evidence и прежние границы не переоткрываются.

### Принятый GUARDS design

[C0 R1 acceptance](https://github.com/Elefesys/ai-service-manager/pull/28#issuecomment-6121868191):
head `9645c99d49c0a27ea9f4fd95de676771df0a135d`, sole parent
`d4f9bdec7ec801e61165e142b16e98f6d2322e0b`, tree
`c29c13a6a67c0d8349ddb5f73f0d5a1ffe10febd`.
[C6 COMPAT design PASS](https://github.com/Elefesys/ai-service-manager/pull/28#issuecomment-6122758140)
принят C0: новых findings нет; один retained H/T/C chain + новый C/0009→G
phase при прежних budgets. Это design acceptance, не actual G runtime/timing PASS.

| Решение / finding | Текущий статус C0 |
|---|---|
| GUARDS-POLICY-01 | LOCKED: LOCAL/TEST + CONTROLLED, fresh Resume profile/live Resume OWNER; automated Telegram не выдан |
| GUARDS-POLICY-02 | LOCKED: deterministic TEST consumer, один accepted intent на Turn; stale pending без automatic replacement |
| GUARDS-DB-01 | LOCKED в design: одна receipt table, typed relations,6 SQL profiles и legacy Turn routing по R1 |
| GUARDS-COMPAT-01 | LOCKED в design: C6 direct frozen C selector/shared600/source plan; actual G assertions/timings pending |
| C1-M3-GUARDS-01 / P3 | CLOSED в contract scope решением C0 на R1; actual history-label regression предстоит |
| C2-M3-GUARDS-01 / P2 | CLOSED в contract scope решением C0 на R1; actual legacy-route negative предстоит |

[R1 CI38229073360 attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/38229073360)
9/9 SUCCESS + clean9/9, tested merge
`750e4432e1e9e3636b9e810530ff253e0726fe47` (ordered parents main+R1; tree=R1).
Это docs-only head/runtime0009; preparation и implementation требуют своего
source binding. Исторические OPEN/proposal/no-authorization строки contract§13
и прежних receipts заменены этой активной выдачей, техническая semantics принята.

### Активная выдача и migration queue

**C3-M3.1-GUARDS — IN_PROGRESS, implementation разрешена.**
Полная выдача: [M3_HANDOFF §0](tasks/M3_HANDOFF.md). C3 — единственный автор
реализации; C0 владеет реестром/handoff, migration queue и приёмкой.
Продолжить `c3/m3-1-guards` в том же [Draft PR28](https://github.com/Elefesys/ai-service-manager/pull/28).
Старт — C0 continuation commit с sole parent=R1 выше, меняющий только этот
реестр и handoff; полный SHA/tree указан в поручении C0. Новый PR не нужен.

C0 **резервирует и разрешает revision0010/down_revision0009**:
`migrations/versions/0010_conversation_guards.py`, writer C3, dependency accepted
CONTROL0009. Применённые0001–0009 immutable; иных новых revision/DDL writers нет.

Exact write scope — **31 path:26 existing+5 new**, полный список handoff§0.3.
Он включает одну migration, narrow guards module, normal worker/DB/results,
exact readiness/TEST provisioning, три GUARDS suites, необходимые existing
fixtures/inventories, два frontend history-label paths, семь C6 compat paths,
contract append и runbook. Это максимум, не требование менять каждый файл.
Другие paths/semantic changes требуют конкретного diff и решения C0 до записи.
AGENTS/register/handoff/applied migrations/HTTP-OpenAPI/deps/Compose/workflows
не входят в scope C3.

Полный принятый contract226090bytes сохраняется как byte-prefix
(blob `3a16de4c4336e70af53143e08b8858fc2452d7a9`, SHA256
`8b3df3bf404857fe182323a1238bbac4862c860d7c5c5c7e9f1f3ae2abda6cab`);
append§13.11 связывает implementation/test evidence с принятым design.
14 scenarios§13.8, actual normal producer/worker/PG/process evidence и
C6§0.5 source/schema/recovery/timing остаются implementation gates.
Не расширять прежние600/cleanup90/state25min/foundation35min или9 CI jobs.

| Задача | Статус | Evidence / следующий шаг |
|---|---|---|
| M0/M1; M2/ENV04 | Прежние VERIFIED / LOCAL-TEST границы сохранены | Старые receipts не переоткрываются |
| M3.1-CONTRACT | VERIFIED в принятом TURNS/CONTROL/GUARDS design scope | GUARDS R1+C0+C6; actual GUARDS ещё предстоит |
| M3.1-TURNS | INTEGRATED / VERIFIED LOCAL/TEST | PR26, accepted T |
| M3.1-CONTROL | INTEGRATED / VERIFIED LOCAL/TEST | PR27/main C/CI38209943421 |
| M3.1-GUARDS | IN_PROGRESS, implementation | C3,0010,31 paths; единый receipt PR28 |
| Native account/provenance | TODO / NOT VERIFIED evidence | Отдельная выдача C0 |
| M3.2-ESCALATION | TODO | После control/guards |
| M3.2-CONSOLE | TODO | C5 пока не выдан; neutral history label не закрывает Console |
| M3-ACCEPTANCE | TODO | Полный milestone ещё не закрыт |

Возврат: final head/parent/tree/changed paths, all9+clean9 и exact-source actual
evidence → C0 intake → адресные C1/C2/C6 implementation reviews → C8 по выдаче
C0 → решение C0 → merge пользователем → main CI. Содержательная выдача записана
здесь; дальнейший текущий source/CI — PR/comment metadata без status-only commits.

### Сохранённые ограничения

IMPL-01/02/03/04 CLOSED. **IMPL-05 OPEN; fix DEFERRED, неблокирующий P3 только
для текущего LOCAL/TEST по C0.** Исходный C6 P2/CHANGES_REQUESTED не переписан.
[Решение C0](https://github.com/Elefesys/ai-service-manager/pull/27#issuecomment-6118079467):
обычный STOP run неуспешен; automatic resume/reuse восстановленного failed journal
не поддержан, новый run получает новый workspace. Вернуться до расширения recovery
либо при доказанном normal-path impact. GUARDS этот fix/новый fault framework
не включает. Цель — рабочий MVP с базовыми auth/tenant/Client/data/idempotency
protections и принятой extensibility; новые security/chaos программы не выдаются.

Native-owner/edit-delete provenance, production AI/Telegram, LLM/M4,
Escalation/Console и весь M3 не объявлены VERIFIED. VM/live/working DB/S3/
credentials/ACK/binding/renewal/deploy/merge не входят в текущую выдачу.

<details>
<summary>История GUARDS-CONTRACT до выдачи implementation; активное решение выше</summary>

## Текущий статус — CONTROL закрыт; GUARDS-CONTRACT выдан / 2026-10-12 UTC

**M3.1-CONTROL — INTEGRATED / VERIFIED в принятом LOCAL/TEST scope. M3 — IN_PROGRESS.**
Пользователь слил [PR27](https://github.com/Elefesys/ai-service-manager/pull/27)
2026-10-12T05:53:30Z. Accepted main:
**`c6a55b6b17d1c1ab286ce97dfa4bd27197141fe5`**, tree
`d7f0dbd35a637877b57d721cbb6a39c6ef59eae4`.
Ordered parents: T `ea1ae98ce9e5e26d5d0d14f3e6d278ecb9efbbad` +
reviewed head `634ea9b3b1af91124abd1b60873cc6fa723b5361`;
tree равен reviewed head и tested merge `040eb6ccf6ebc8f6563a0e69bc098590014fe8cf`.

[Push/main CI38209943421 attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/38209943421)
завершён 2026-10-12T06:22:09Z: **9/9 SUCCESS + clean-source9/9**.
C0 прочитал foundation114681644478/browser114681644109 logs: actual main,
1056 non-integration/555 PostgreSQL integration/113 frontend/27 browser PASS,
Ruff/mypy/E01–E05/wheel reproducibility/HTTP smoke.
[Post-merge receipt C0](https://github.com/Elefesys/ai-service-manager/pull/27#issuecomment-6118563610)
сводит [C8 PASS](https://github.com/Elefesys/ai-service-manager/pull/27#issuecomment-6118524230),
сохранённые C1/C2 PASS и C6 findings. Новых local runtime tests C0 не запускал.

| Finding | Решение C0 |
|---|---|
| C6-M3-CONTROL-IMPL-01/02/03/04 | CLOSED: исходные defects исправлены и подтверждены в принятой границе |
| C6-M3-CONTROL-IMPL-05 | OPEN; исправление DEFERRED, неблокирующий P3 только для текущего LOCAL/TEST по решению C0 |

IMPL-05 — реальное ограничение fresh collection восстановленного private journal,
если перед этим не удалась публикация STOP. Это не выполненный fix; C6 P2 и
CHANGES_REQUESTED по прежнему расширенному gate сохранены в его review.
[Решение C0](https://github.com/Elefesys/ai-service-manager/pull/27#issuecomment-6118079467):
штатный STOP run остаётся неуспешным, automatic resume/reuse его journal не поддержан.
Вернуться к finding до такого расширения, применения harness как эксплуатационного
recovery либо при доказанном влиянии на обычный CI/product path. GUARDS не включает
его исправление и не расширяет отдельный протокол журналирования.

CONTROL принимает A07 и согласованные context/fence/A11 части. Native intervention
по-прежнему NOT VERIFIED; GUARDS/action-send admission/in-flight, Escalation,
Console CONTROL UI и M4 этим merge не выполнены. Deployment/VM/live не выполнялись.

### Активная выдача

**C3-M3.1-GUARDS-CONTRACT — IN_PROGRESS**, начальная фаза M3.1-GUARDS.
Полное поручение: [M3_HANDOFF §0](tasks/M3_HANDOFF.md). Ветка `c3/m3-1-guards`,
отдельный checkout; C3 — единственный автор дополнения. C0 preparation commit
имеет единственный parent = accepted main выше, меняет ровно этот реестр и handoff;
его полный SHA опубликован в поручении C0. C3 начинает от подготовленного head.
До содержательного contract candidate PR не открывается: C3 откроет один Draft PR
после завершения дополнения; тот же PR затем используется для согласованной реализации.

**Сейчас разрешён один write path: `docs/tasks/M3_CONTRACT.md`.**
Append §13 после неизменных170371 bytes; blob принятого полного prefix
`aa3729960a43cf09d729a3514671d44c0b9685a4`, SHA256
`12cfeb72a4c101c557a710522d0e553dbada06d2ade307649187086e85b6a3df`.
Runtime/DDL/tests/guards/budgets и applied0001–0009 сейчас не меняются.
Номер новой миграции не выдан; сначала обоснование минимальной дельты.

Цель: конкретный минимальный контракт admission автоматического результата/действия/
send, который сериализуется с Takeover, отвергает устаревший worker и сохраняет
правдивый результат уже начатой отправки. Опора на existing Jobs/Outbox/CONTROL;
M4 executor/provider и будущие business domains не проектируются здесь целиком.
Проверки соразмерны обычным product/recovery сценариям; новая chaos/security
программа и IMPL-05 follow-up не являются условием этой фазы.

| Задача | Статус | Evidence / следующий шаг |
|---|---|---|
| M0/M1; M2/ENV04 | Прежние VERIFIED / LOCAL-TEST границы сохранены | Старые receipts не переоткрываются |
| M3.1-CONTRACT | VERIFIED в TURNS/CONTROL document scope | Новое GUARDS дополнение ещё не принято |
| M3.1-TURNS | INTEGRATED / VERIFIED LOCAL/TEST | PR26; main T/CI38062653562 |
| M3.1-CONTROL | INTEGRATED / VERIFIED LOCAL/TEST | PR27; main c6a55b6/CI38209943421 |
| M3.1-GUARDS | IN_PROGRESS, только CONTRACT | C3; handoff§0, затем адресный C1/C2 review и решение C0 до кода |
| Native account/provenance | TODO / NOT VERIFIED evidence | Отдельный scope C0 до account probe/реализации |
| M3.2-ESCALATION | TODO | После control/guards |
| M3.2-CONSOLE | TODO | Принятые API предыдущих частей; C5 пока не выдан |
| M3-ACCEPTANCE | TODO | Полный milestone ещё не закрыт |

Реестр и handoff обновлены вместе с новой содержательной выдачей; текущий source/CI
указываются в PR/comment metadata без цепочки status-only commits.
Merge сохраняется за пользователем после приёмки C0. Canon/LOCKED решения, базовые
auth/tenancy/data protections и существующие CI gates не ослабляются.

</details>

<details>
<summary>История CONTROL до post-merge приёмки; текущий статус и выдача выше</summary>

## Текущий статус — CONTROL-контракт принят; реализация выдана / 2026-10-10 UTC

**M3.1-TURNS — INTEGRATED / VERIFIED в LOCAL/TEST scope. M3 — IN_PROGRESS.**
[PR26](https://github.com/Elefesys/ai-service-manager/pull/26) слит пользователем
2026-10-10T15:12:11Z. Actual accepted main:
**`ea1ae98ce9e5e26d5d0d14f3e6d278ecb9efbbad`**, tree
`11ad506a859db155973f965bcdd0cebc7bc0d5ed`.
Ordered parents: accepted H `754f1c883e5a94a7fc9e729af2605424f949ba33` +
reviewed head `cd277b195396e76d914364903f42e1e52f21e1ff`;
tree точно равен reviewed head/tested I
`9694adf33e6fa0d5342083ac7fd26f9e25c1e6f5`.

[Push/main CI38062653562 attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/38062653562)
— **9/9 SUCCESS и9/9 clean-source gates SUCCESS**; завершён15:34:05Z.
C0 прочитал foundation114243888408 и browser114243888385 logs:
actual main checkout,937 unit/462 integration/111 frontend/27 browser PASS,
full migration cycle/contracts/wheel cmp/HTTP smoke. Wheel SHA256
`ea9159a98d39b5d65baf1cedd1b50abef869c5392e58278f4f055975484c687d`.
Собственных новых PG/Docker/live запусков C0 на post-merge этапе нет.

Основания: [C0 acceptance](https://github.com/Elefesys/ai-service-manager/pull/26#issuecomment-6098927722),
[C8 PASS](https://github.com/Elefesys/ai-service-manager/pull/26#issuecomment-6098859899),
[C2 R1 PASS](https://github.com/Elefesys/ai-service-manager/pull/26#issuecomment-6098377195),
[C6 R1 PASS](https://github.com/Elefesys/ai-service-manager/pull/26#issuecomment-6098346591).
C1 PASS6097008758 — b301 в его scope; Python/API/material rules неизменны,
R1 SQL ordinary/capability delta проверена C2/C8 на final head.
Приняты A01/A02/context-часть A03/A11. Полные CONTROL/GUARDS/native/UI/M3 acceptance
этим evidence не покрыты. Независимый C8 не нашёл новых findings.

| Finding | Статус C0 / evidence |
|---|---|
| C2-M3-TURNS-01 / P2 | CLOSED: final maintenance NOWAIT/age horizon,3 actual PG cases, обычные wrappers/limits сохранены |
| C2-M3-TURNS-02 / P2 | CLOSED:4 open-outer-tx/savepoint cases, PREPARED upload, recovery101/cutoff/restart |
| C2-M3-TURNS-03 / P2 | CLOSED: strict canonical E05 gate и5 actual PG negatives, C2 PASS |
| C6-M3-TURNS-02 / P2 | CLOSED: тот же E05 fix, отдельный C6 direct LOCAL/default PASS |
| C6-M3-TURNS-01 / P2 | CLOSED: оба state shards committed0008/exit86/fresh read/exact I recovery и retention |
| C2-M3-CONTRACT-01–04 / P2 | CLOSED в document scope; соответствующие TURNS implementation gates теперь приняты отдельно |

Contract R2 и неизменный TURNS prefix:
blob `5e87375852331523491a47926b9c5bd49946c157`.
Applied0001–0008 immutable. **C0 выдал0009_conversation_control.py**,
revision0009/predecessor0008, только для следующей LOCAL/TEST implementation.

**CONTROL-CONTRACT R1 принят C0; M3.1-CONTROL — IN_PROGRESS, фаза IMPLEMENTATION.**
Текущая полная выдача: **[C3-M3.1-CONTROL, M3_HANDOFF§0](tasks/M3_HANDOFF.md)**,
в том же Draft [PR27](https://github.com/Elefesys/ai-service-manager/pull/27),
ветка `c3/m3-1-control`. C3 — единственный implementation автор; новой ветки/PR нет.

Принятый exact R1: `ffc0a66e2916f300e9f2f779084322a6a9b5447d`, parent
`cf043901186f7f5178332e64a056d336cce0dc0f`, tree
`8cfc7edd0778c0d1ec053c70a24596f32281c0ad`. Contract blob
`aa3729960a43cf09d729a3514671d44c0b9685a4`,170371bytes, SHA256
`12cfeb72a4c101c557a710522d0e553dbada06d2ade307649187086e85b6a3df`.
Старый77343-byte prefix/§§1–11 сохранён. Основания:
[C0 R1 intake](https://github.com/Elefesys/ai-service-manager/pull/27#issuecomment-6100794824),
[C1 R1 PASS](https://github.com/Elefesys/ai-service-manager/pull/27#issuecomment-6101167262),
[C2 R1 PASS](https://github.com/Elefesys/ai-service-manager/pull/27#issuecomment-6101177021).
Оба review на exactR1 без остаточных/new findings. Прежний
[C6 design PASS на cf043901](https://github.com/Elefesys/ai-service-manager/pull/27#issuecomment-6100099472)
сохранён; actual timing/runtime приёмка ещё впереди.

| Finding / решение | Статус C0 и обязательство реализации |
|---|---|
| C1-M3-CONTROL-01 / P2 | CLOSED, contract scope: single-clock/full post-lock snapshot и final callers; actual expiry+activation barriers для Resume/обоих public manual providers и frozen R4 regression обязательны |
| C1-M3-CONTROL-02 / P2 | CLOSED, contract scope: exact8 security profiles и tenancy inventory path; полный pg_proc union/privilege negatives обязательны |
| C2-M3-CONTROL-01 / P2 | CLOSED, contract scope: saved actor/context в seven-column receipt→Audit FK; два независимых valid-fixture named-FK negatives, positive/replay/rollback обязательны |
| CONTROL-POLICY-01 | ACCEPTED/CLOSED в design scope по C1 R1; существующий messaging.manual_send — availability Resume, не AI send capability; реализация clock/policy ещё не проверена |
| CONTROL-DB-01 | ACCEPTED/CLOSED в design scope по C2 R1; receipt/locks/origin/migration приняты как контракт, будущие0009 PG assertions не PASS |
| CONTROL-AUDIT-01 | ACCEPTED/CLOSED в прежнем C1 API/DTO/UI compatibility design scope; actual mixed Audit и FK evidence ещё требуются |
| CONTROL-COMPAT-01 | ACCEPTED/CLOSED в C6 design scope; frozenH→retainedT→newC, whole-T/remaining600 и failure retention приняты, actual wall time/0009 recovery не проверены |

[R1 CI38073531311 attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/38073531311)
—9/9 jobs и9/9 clean-source SUCCESS, завершён2026-10-10T18:22:38Z.
Tested merge `13f67b02f9ec67353f308f4f82f6002d06df734c`, ordered parents T+R1,
tree=R1; foundation/browser logs:937 unit/462 integration/111 frontend/27 browser PASS.
Это документ/retained0008 runtime; CONTROL/0009/22 scenarios/новые timings
**NOT EXECUTED на момент выдачи**, не VERIFIED. Runtime приёмка будет на новом SHA.

C0 preparation от R1 меняет только этот реестр и handoff; contract/runtime и все
другие blobs/modes сохраняются. Full continuation SHA/tree — в поручении/metadata
PR27. C3 начинает от него и проверяет parent=R1, затем реализует exact36-path scope
(28 existing+8new)§0.3: commands/API/Audit, atomic manual, ingress fence,0009 и gates.
Согласованы additive entrypoint/generated OpenAPI и narrow frontend Audit parsing/
labels; CONTROL UI не выдан. Неизменные0001–0008/канон/tenancy.v1/pins/CI budgets
и TURNS/M2 assertions сохраняются. Других параллельных авторов нет.

Текущий handoff/решение C0 сменяет исторические proposal/OPEN/contract-only
формулировки§12; технические правила R1 приняты, их status-only редактура не нужна.
После finished candidate — адресные implementation C1/C2/C6, независимый C8,
приёмка C0, только затем пользовательский merge и actual main CI.

Native account observability — **NOT VERIFIED**; automatic native takeover и
material edit/delete/provenance не выданы. Явный Console Takeover API и atomic manual
остаются основанием CONTROL. GUARDS/full action-send admission/in-flight,
Escalation, Console UI и M4 — следующие задачи; M3 в целом IN_PROGRESS.

| Задача | Статус | Evidence / следующий шаг |
|---|---|---|
| M0/M1 | VERIFIED в прежнем scope | Не переоткрываются |
| M2 / ENV04 | INTEGRATED / VERIFIED LOCAL/TEST | [Final receipt6066209663](https://github.com/Elefesys/ai-service-manager/pull/24#issuecomment-6066209663), main ca64f98b / CI37863489865; прежний owner evidence сохранён |
| M3.1-CONTRACT | VERIFIED, TURNS и CONTROL document scope | TURNS R2 и CONTROL R1 приняты C0; runtime приёмка отдельна |
| C6-M3-SCHEMA-SOURCE-PAIRING (TURNS) | VERIFIED в выданном scope | Frozen historical0007 и actual candidate0008 gates реализованы/проверены |
| M3.1-TURNS | INTEGRATED / VERIFIED LOCAL/TEST | Actual PR26 merge + push/main CI; A01/A02/contextA03/A11 |
| M3.1-CONTROL | IN_PROGRESS, IMPLEMENTATION выдана C3 | PR27, handoff§0, exact36 paths/0009; implementation ещё не принята |
| M3.1-GUARDS | TODO | После принятого CONTROL: actual action/send admission, stale worker/in-flight |
| Native account/provenance gate (часть M3/A08) | TODO / NOT VERIFIED evidence | Отдельная выдача C0 до account probe/native implementation |
| M3.2-ESCALATION | TODO | После control/guards; owner-wait lifecycle |
| M3.2-CONSOLE | TODO | После принятого owner/control API; C5 сейчас не выдан |
| M3-ACCEPTANCE | TODO | ПолныеA04–A10/A12 и остальные части milestone ещё впереди |

Необходимые actual DB/API/privateS3/Docker тесты разрешены только в disposable
LOCAL/TEST штатного harness. M2 live evidence сохраняется в принятом receipt;
это не новое подтверждение0008/0009 на VM. VM/SSH/live Telegram/рабочие DB-S3/
binding/ACK/activation/TEST продление/deploy/merge не выданы. Production rollout
остаётся Expand/Migrate/Contract, ADR217; git merge не обновляет VM.

История failed PR runs, включая docs-only38019736763 с неустановленной причиной,
сохранена в PR26; новые PASS её не переписывают. Текущий implementation head/CI
фиксируется в PR27 metadata, не цепочкой SHA-only commits. История ниже не является
очередью действующих операторских задач.

<details>
<summary>История выдачи TURNS до реализации; актуальные статусы находятся выше</summary>

## История — CONTRACT принят и TURNS выдан / 2026-10-10

**M2 — INTEGRATED / VERIFIED в принятом LOCAL/TEST scope.**
Это перенос уже опубликованного решения C0, не новая приёмка от автора плана.
[PR #24](https://github.com/Elefesys/ai-service-manager/pull/24) MERGED;
main `ca64f98b0c8d12d4de922ed0ed7d34e48822ac00`,
tree `5aa2b7764797919758a1d89a01c34fb94788540e`.
[Push/main CI 37863489865](https://github.com/Elefesys/ai-service-manager/actions/runs/37863489865)
SUCCESS: 9/9 jobs, все clean-source gates.
[Финальный receipt C0](https://github.com/Elefesys/ai-service-manager/pull/24#issuecomment-6066209663)
содержит фактическую приёмку owner migration/activation/webhook и live A09/A11:
text/photo в Console, ручной ответ, отдельное подтверждение Client о ровно одной копии.
Это owner-operated evidence; дополнительные live observations/DB counters не выдумываются.

C0 закрыл прежние client01/02/03, C8-MIG-01, C0-MIG-OWNER-01/02 и
C0-CI-AUDIT-01 в указанном receipt scope. Старые REVIEW/OPEN/BLOCKED ниже —
история. M0/M1 и принятые части M2 не переоткрываются.
[M2_HANDOFF](tasks/M2_HANDOFF.md) закрыт. Текущий следующий handoff:
[M3_HANDOFF](tasks/M3_HANDOFF.md).

**M3 — IN_PROGRESS. M3.1-CONTRACT — VERIFIED в scope согласования документа;
C3-M3.1-TURNS — IN_PROGRESS, implementation-поручение выдано.**
Статус CONTRACT не означает реализацию M3, merge PR или проверенный0008 DDL.

План принят в [PR25](https://github.com/Elefesys/ai-service-manager/pull/25).
Accepted main/implementation base:
`754f1c883e5a94a7fc9e729af2605424f949ba33`;
[push/main CI37965195898](https://github.com/Elefesys/ai-service-manager/actions/runs/37965195898)
—9/9 SUCCESS. Main и принятый M2 остаются прежними; [PR26](https://github.com/Elefesys/ai-service-manager/pull/26)
открыт как Draft, merge ещё не разрешён.

**C0 принимает CONTRACT-R2** [C3](https://github.com/Elefesys/ai-service-manager/pull/26#issuecomment-6094572773)
на exact `4f9d32e9d67308da8062dc12aeb4839e06c850cb`,
tree `25c4bf9f4039141f4ce8c03c1edfb18196deb790`,
contract blob `5e87375852331523491a47926b9c5bd49946c157`;
parent `b99e119757d52ee8bd00a51093f63bada5f95823`.
[C1 R2 PASS](https://github.com/Elefesys/ai-service-manager/pull/26#issuecomment-6094967481)
подтверждает affected versions/commands/API/callers.
[C2 R2 PASS](https://github.com/Elefesys/ai-service-manager/pull/26#issuecomment-6095018013)
подтверждает CONTRACT/DB; остаточных/new findings в дельте нет.
C0 принимает оба заключения в их scope; приёмка реализации ещё впереди.

| Finding | Важность / статус C0 | Основание закрытия и сохраняемый implementation gate |
|---|---|---|
| C2-M3-CONTRACT-01 | P2 / CLOSED, contract-review | R2 §§2/5.3/8/11 + C2 PASS: origin barrier обоих producers, post-lock snapshot и FK-safe Inbox writers; реальные concurrency assertions обязательны |
| C2-M3-CONTRACT-02 | P2 / CLOSED, contract-review | R2 §§5/6/11 + C2/C1 PASS: single-candidate transactions, NOWAIT rollback/scan continuation, полный terminal/lock protocol; B-progress/material-once ещё проверяются в коде |
| C2-M3-CONTRACT-03 | P2 / CLOSED, contract-review | R2 §§4/5.4/11 + C2/C1 PASS: immutable job/winning-claim binding и private terminal replay; ACK-loss/privilege/race assertions остаются gate |
| C2-M3-CONTRACT-04 | P2 / CLOSED, contract-review | Принятый C0/C6 design включён в R2 §§7/10/11, C2/C1 PASS: historical0007/candidate0008/LOCAL upgrade разделены; actual source/image/schema execution ещё требуется |

[CI38030244030 attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/38030244030)
на R2 —9/9 SUCCESS и9/9 clean-source gates.
C0 прочитал foundation checkout `5403d868ffbcefa9489d83bcc8d674da394b2984`:
parents accepted main + R2, tree точно совпадает с candidate.
Ранее проверены точные path/parent/tree/blob, unchanged §§6/9, только barrier delta §8
и exact31 unique names. Эти static/CI evidence принимают документ и прежний runtime,
не доказывают будущие M3 SQL/worker/upgrade механизмы.
Первичный docs-only failure38019736763/attempt1 сохранён в PR; root cause неизвестна,
finding04 не объявляется её причиной. Дополнительного rerun при этой приёмке нет.

Текущая полная выдача — **[M3_HANDOFF §0: C3-M3.1-TURNS](tasks/M3_HANDOFF.md)**.
C3 продолжает PR26 после fast-forward к полному C0 continuation SHA из PR metadata;
C0 commit поверх R2 меняет только этот реестр и handoff. Reviewed contract bytes
сохранены: его вступление — snapshot до данного verdict; прежний запрет кода
заменён явной ограниченной выдачей §0, без изменения принятой семантики.

Разрешены26 exact paths, один законченный TURNS candidate с новой
`0008_conversation_turns.py` (revision0008/predecessor0007), три таблицы,
durable PROCESS_TURN/TEST receipt и необходимая source/schema совместимость.
C2 резерв подтвердил; C0 теперь разрешает C3 написать и проверять этот DDL
в disposable LOCAL/TEST. Applied0001–0007 immutable; runtime/DDL acceptance
после фактического evidence и профильных reviews.
D2/G10/M15/N32/cap25с, HUMAN/gen1, пять M2 API, manual/UNKNOWN/receipt invariants
сохраняются. CONTROL/GUARDS/ESCALATION/CONSOLE/M4 не выданы.

[C6 read-only предложение](https://github.com/Elefesys/ai-service-manager/pull/26#issuecomment-6093950520)
и [решение C0](https://github.com/Elefesys/ai-service-manager/pull/26#issuecomment-6094458702)
приняты как часть CONTRACT: frozen P/O/H0007, actual I0008 и отдельный LOCAL
schema phase с drain API/worker/scheduler/pools. Future I ещё не существует;
H PASS не заменяет I coverage. Existing workflows/Compose/pins/budgets не меняются.

| Задача | Статус | Evidence / следующий шаг |
|---|---|---|
| M0/M1 | VERIFIED в прежнем scope | Сохранённая приёмка; без повторного старта |
| M2 / ENV04 / live A09–A11 | INTEGRATED / VERIFIED LOCAL/TEST | PR24 + отдельный main CI + финальный C0 receipt выше |
| M3.1-CONTRACT | VERIFIED, contract-only | Exact R2, scoped C1/C2 PASS, C0 acceptance; implementation evidence не заявляется |
| C6-M3-SCHEMA-SOURCE-PAIRING (часть CONTRACT) | VERIFIED, read-only design scope | Вариант принят C0 и включён в R2; реализация assigned C3 в TURNS |
| M3.1-TURNS | IN_PROGRESS, выдано C3 | Handoff §0:26 paths,0008, реальные PG/worker/S3/schema assertions; готового implementation candidate пока нет |
| M3.1-CONTROL | TODO | После интегрированного TURNS: takeover/resume, generation, owner/API/native semantics |
| M3.1-GUARDS | TODO | После CONTROL: admission/stale worker/in-flight через рабочие DB/worker paths |
| M3.2-ESCALATION | TODO | Отдельный owner wait lifecycle на существующих durable jobs |
| M3.2-CONSOLE | TODO | После принятого API: mode/actions/wait/in-flight UI и browser journeys |
| M3-ACCEPTANCE | TODO | Scoped C8, применимый owner smoke, final actual main CI; затем отдельная выдача M4 |

TEST/COMPED на существующем стенде завершился 2026-10-09T00:00Z.
VM/SSH/Telegram, реальные DB/S3, binding/ACK/deploy/activation/sends/продление
этим поручением не разрешаются. LOCAL/TEST разработка и synthetic проверки
не требуют действий владельца. Production expand/migrate/contract остаётся каноном.
Git merge не обновляет VM; закрытые owner receipts/fingerprints не переисполняются.

После готового TURNS C0 выдаёт scoped C2/C1, при необходимости C6, и независимый
C8 по actual implementation, затем решает приёмку/merge. CONTROL — от принятого
интегрированного SHA после actual main CI. Полный M3 остаётся IN_PROGRESS.

Текущий continuation/head/CI фиксируются в PR metadata; отдельного commit только
ради собственного SHA/статуса нет. История ниже сохранена целиком для provenance,
но не является очередью текущих операторских действий.

</details>

## История M0–M2 — прежние snapshots и поручения

<details>
<summary>Архив прежнего реестра до закрытия M2; текущий статус находится выше</summary>

## Текущий статус — historical operator принят; Audit pagination / REVIEW — 2026-10-08 UTC

C0 принимает [C8 scoped PASS](https://github.com/Elefesys/ai-service-manager/pull/24#issuecomment-6066209663)
на exact head **8be37ca97a7ac5d8dfe095e191c7799caaa2043d** / tree
**c6655b3310cb4f2f4fe302997452162a7cf683d4**. **C0-MIG-OWNER-02/P2 CLOSED**
в проверенном code/CI scope. [C6 receipt6065993676](https://github.com/Elefesys/ai-service-manager/pull/24#issuecomment-6065993676):
CI37817339030 attempt1 —9/9 jobs и9 unchanged-source gates SUCCESS;
900 unit,393 integration,111 frontend,27 browser. C8 самостоятельно выполнил
286 scoped tests и19 provenance probes, сверил8 ZIP/source228 blobs+modes,
6 migration и2 relay reports. Local Docker/DB observations C8 — fixtures;
actual Docker/PG evidence — прочитанный CI. Owner execution этим не подтверждён.

C5 patch от31eb (reported local commit d204f38794844a83d4d24a9178edd39c89890beb)
меняет только `frontend/e2e/billing.spec.ts`: server cursor ведёт пагинацию;
следующий шаг ждёт rows/render/loading/конец истории. Управляемая задержка
обрабатывает настоящий HTTP response; sleeps/retries/skip/budgets не добавлены.
C0 сверил patch SHA256 `70f9a48cac54646abe51e014f234d58b3279786cae0b5d1611a8488bdb2a506f`,
reconstructed C5 tree `ba718b0ceb540e355985f3ba07f9901bd6b0430e` и final test blob
`b275fd38aa055fc5e175b3441c3e62d080498f95`; exact patch применён к8be без конфликтов.
Собственный `npm run typecheck` C0 — PASS. C5 сообщил HTTP-fixture probes2/2+4/4
и30 component tests; архив этих probes C0 не получен и их execution не присваивается.
Actual browser/API/PostgreSQL проверка нового теста требуется на общем candidate.

| Задача / finding | Статус | Следующее действие |
|---|---|---|
| C6-M2-HISTORICAL-OPERATOR-COMPAT / scoped C8 | VERIFIED в проверенном scope | Принято C0 на8be; повторный полный review не нужен |
| C0-MIG-OWNER-02/P2 | CLOSED | Explicit historical operator provenance подтверждена |
| C0-MIG-OWNER-01; C8-MIG-01; client01/02/03 | CLOSED | Новых признаков регрессии нет |
| C5-M2-AUDIT-PAGINATION / C0-CI-AUDIT-01/P3 | REVIEW / OPEN до actual CI | Один итоговый candidate и штатный browser gate |
| Owner migration execution | BLOCKED до отдельной выдачи C0 | После final CI — actual owner attestation с сохранённым pin |
| M2 / ENV04 | IN_PROGRESS / REVIEW | PR24 Draft/open; main не меняется |

Owner operational source/recovery остаётся exact0b7. Accepted root
`asm-telegram-tls-budget-fixed-owner2-0b7e24ee.json`, SHA256
`5b11de6166045065c02d070d8822eb0487f86860ab223b21222ab84164ae1e46`, DAG15.
Offline capture2026-10-08T16:18:33.831044+00:00 подтвердил historical80e operator:
128/128 copied Git bytes, no drift. Actual owner31-table migration fingerprint
ещё не пройден; image layers/dependencies отдельно не аттестованы.
VM/SSH/live Telegram/queue/ACK/activation/setWebhook/sends/binding/billing/merge
не выполнялись. ACK NOT_ATTEMPTED; TEST interval до2026-10-09T00:00Z не продлён.

Текущий этап и границы: [M2_HANDOFF](tasks/M2_HANDOFF.md).

<details>
<summary>История — завершённое OWNER-RECEIPT-COMPAT и статус до C0 closure</summary>

## Текущий статус — C8-MIG-01 CLOSED; совместимость owner receipt DAG / 2026-10-07 UTC

**C0 принимает независимый C8 PASS и закрывает C8-MIG-01/P2 на R2.**
Exact implementation **f1c7aca724778e41671f2754bb85885507c4f14d**, tree
**4f28480ef1458141422a14514473c05f49193fe6**, sole parent/base
**34835c260f737abbbe02a689f842b28fad50f323**. Helper blob
**00c347cde45e3c1a683330c6ee196815ef0a1e36**, client blob
**525381357de76ea1c570fd864f8df5e9781a87e2**. C6-R2 и targeted C8 завершены;
их проверенный scope VERIFIED. Прежние client findings01/02/03 CLOSED.

Независимый C8 сообщает отдельный чистый checkout,154 migration tests PASS,
три исходных repro без изменения assertions PASS и50 дополнительных probes PASS.
Файловые guards настоящие, Docker/DB/runtime observations — fixture. Это execution
C8, не повторный execution C0. Названный C8 evidence ZIP в этой передаче не
предоставлен как доступный файл; C0 принимает переданный verdict с указанными
границами и своим прежним5-probe/source/CI evidence. CI37629816347 — все9 jobs и
clean-source SUCCESS; C0 ранее независимо сверил8 ZIP digests/228 blobs+modes,
6 schema2 migration reports и2 relay reports. Эти results относятся exact R2.

**Новый отдельный finding C0-MIG-OWNER-01/P2 — OPEN.** При подготовке owner
attestation C0 сопоставил reader с ранее выданным owner script. В сохранённой
цепочке предусмотрен `asm-telegram-ack-old-lifecycle-owner2-0b7e24ee.intent.json`.
Обе проверки basename в `migration_receipts` (R2 lines1956 и1977) допускают
только `[a-z0-9-]+\.json` и отклоняют этот законный исторический узел с
`EGRESS_MIGRATION_RECEIPT_PATH`. Обычный `.json` control принимается; вариант
с exact issued `.intent.json` отклоняется при тех же остальных условиях и
правильных hashes. C0 воспроизвёл это на exact helper с настоящими private files,
Python3.12.14, без Docker/DB/SSH/network и без изменения fixture files reader-ом.
Это STOP до runtime effects, не потеря данных и не повтор Telegram send.
Actual содержимое owner VM и images по-прежнему не наблюдалось.

Finding не переоткрывает исправленный cross-direction audit. Требуется узкая
совместимость имён сохранённого DAG, без переименования/перезаписи старых receipts,
исключения intent из inventory или переснятия hashes. Exact полный basename,
same-parent, no-symlink, private mode/owner, byte hashes и independent root pin
сохраняются. Поручение C6 и воспроизводимый probe — M2_HANDOFF/runbook§0.6.30.

**Отдельный CI incident:** docs-only head
**dcf32ca02c4222e3267ed4e794c817345ae71357** / tree
**499342f9a26a74640b079d2fa277767d89f65834**, parent exact R2, изменил только4 docs;
остальные224/228 blobs+modes прежние. CI37640492805 attempt1:8 jobs SUCCESS,
browser26 PASS/1 FAIL на `frontend/e2e/billing.spec.ts:57` (пагинация Audit,
ожидание enabled для исчезнувшей кнопки последней страницы). C0 запросил ровно
один rerun browser job112857823029. Job112868124234:27 PASS/clean-source SUCCESS;
attempt2 completed SUCCESS, все9 jobs/clean-source SUCCESS. Исторический failure
не удалён. Лог и статический код согласуются с гонкой между response headers,
завершением render и проверкой count/enabled; детерминированный UI repro ещё
не выполнялся. **C0-CI-AUDIT-01/P3 OPEN, C5 TODO (не выдано)** — разобрать
синхронизацию теста до merge. Ни тест, ни timeout/assertions не изменены.

| Задача / finding | Статус | Следующее действие |
|---|---|---|
| C6-M2-CONNECT5-MIGRATION-R2 / targeted C8-R2 | VERIFIED в проверенном scope | Завершено, полный review не повторять |
| C8-MIG-01/P2 | CLOSED | Cross-direction audit подтверждён C0+C8 |
| C0-MIG-OWNER-01/P2 | OPEN | Совместимость существующего `.intent.json` receipt |
| C6-M2-OWNER-RECEIPT-COMPAT | TODO, выдано | Единственное активное implementation поручение |
| C0-CI-AUDIT-01/P3 | OPEN, C5 TODO | Отдельный browser test incident, не scope C6 |
| Owner migration execution | BLOCKED | Receipt compatibility, затем actual image/DAG attestation |
| M2 / ENV04 | IN_PROGRESS / REVIEW | Actual owner migration и A09/A11 впереди |

Последнее owner evidence остаётся exact0b7e24ee/recovery-v2/connect2/TG disabled-empty,
binding committed, ACK NOT_ATTEMPTED. Independent last-receipt SHA pin и соответствие
cached images predecessor ещё не получены. CI images строились заново и не являются
owner attestation. Fixed TEST interval2026-10-02T00Z→2026-10-09T00Z не меняется;
source-key revocation не подтверждена. PR24 Draft/open, main прежний.
Новый C0 coordination меняет только4 документа; его CI учитывается отдельно от
двух указанных green runs. VM/SSH/live Telegram/queue/ACK/activation/setWebhook/
sends/billing mutation/main merge в этой передаче не выполнялись и не выданы.

Единственное активное implementation поручение — [C6-M2-OWNER-RECEIPT-COMPAT](tasks/M2_HANDOFF.md).
Reproducer, источники и неизменённый предыдущий receipt prefix — runbook§0.6.30.

</details>

<details>
<summary>История — C0 R2 PASS и завершённое поручение targeted C8</summary>

## Текущий статус — C6-R2 завершён; C0 review PASS, targeted C8 / 2026-10-07 UTC

**C0 scoped R2 review — PASS; новых blockers не выявлено.** C6 передал готовый
результат; ожидание статуса REVIEW является передачей на приёмку, не незавершённой
реализацией. **C8-MIG-01/P2 остаётся OPEN до targeted C8/C0 verdict.** Migration
остаётся REVIEW; прежние client findings01/02/03 CLOSED. Owner execution не выдана.

R2 implementation head **f1c7aca724778e41671f2754bb85885507c4f14d**, tree
**4f28480ef1458141422a14514473c05f49193fe6**, sole parent coordination/base
**34835c260f737abbbe02a689f842b28fad50f323**. Это единственный fix commit.
Helper blob **00c347cde45e3c1a683330c6ee196815ef0a1e36**; client blob
**525381357de76ea1c570fd864f8df5e9781a87e2** прежний. Изменены четыре разрешённых
файла: helper, migration tests, contract§10.12.1, runbook§0.6.28. Workflow/runners/
Compose/locks/domain/DB schema/180s и600s bounds не изменены; ancestry сохранена.

Исправление проверяет оба направления audit, done→result и исторические
completion source/state/database/intent bindings. Immutable rollback-intent schema2
закрепляет exact forward inventory/byte hashes и проверенный historical runtime.
Resume/retry не переснимают pin; missing/changed/additional evidence и старый
unbound rollback intent дают STOP. Historical forward IDs не приравниваются
к новым rollback IDs; допустимые partial/result-done/state-completion gaps сохранены.

**Собственная проверка C0:** source/contract/test delta; прежние три repro на R2
теперь дают ожидаемый отказ без новых effects: COMPLETED_DRIFT,
SERVICE_RESULT_REQUIRED, INVALID_JSON. Ещё два controls PASS: valid partial
rollback (один нужный recreate) и CANONICAL_DATA_DRIFT до effects. Итого5 targeted
PASS, Python3.12.14, exact helper blob; реальные файловые guards/private I/O,
Docker/DB/prepared observations заменены repository fixture. C0 не запускал
новые локальные Docker/PG/browser/full suites; исходный extracted source сверён
по blobs/modes, это не заявление о новом полном Git checkout.

[Final CI37629816347](https://github.com/Elefesys/ai-service-manager/actions/runs/37629816347)
— все9 jobs и clean-source gates SUCCESS; logs768 unit/393 integration/111 frontend/
27 browser PASS. Tested merge **ebf1ec21f59eb8f887c779c3e55bf878eb15add5**, тот же
tree; ordered parents main **22993f558c5e7e933c65e9c999933bd2e3ab41c4** +R2 head.
C0 скачал все8 ZIP, сверил GitHub digests и228 Git blobs/modes каждого source
archive, tested commit/PAX и пустой worktree status. Общий source.tar.gz SHA256
`e78b0a27ea62bcd6e574e43de8e9ae73dee67ef2f077169d826a86664765b394`.
Все6 migration reports: schema2,7 закреплённых forward hashes равны final receipts,
rollback-intent hash совпадает, unchanged-after-resume/retry true. Fingerprints31
таблицы/private original200/403/Console/UNKNOWN/wire1/28 original files сохранены;
held104.530–168.047s≤180s. Оба прежних6+6 reports PASS, readonly TIMEOUT/False5.005s.
Полные job/artifact IDs и hashes сохранены в C6 receipt archive runbook§0.6.29.

C6-reported local251 scoped PASS и исходные5 failing regressions сохраняются как
author evidence; собственный дополнительный execution C0 описан отдельно выше.
Предыдущий docs CI37626628260 на34835 CANCELLED; final R2 all9 SUCCESS относится
к новому полному code candidate. Текущий C0 coordination меняет только четыре
документа, остальные224/228 blobs/modes exact R2; его CI учитывается отдельно.
Targeted C8 проверяет exact **f1c7aca724778e41671f2754bb85885507c4f14d**.

| Задача | Статус | Следующее действие |
|---|---|---|
| C6-M2-CONNECT5-MIGRATION-R2 | REVIEW | Исполнение завершено, C0 source/CI PASS |
| C8-MIG-01 | OPEN | Targeted C8 R2, затем closure C0 |
| C8-M2-CONNECT5-MIGRATION-R2 | TODO, выдано | Единственное активное поручение |
| M2 / ENV04 | IN_PROGRESS / REVIEW | Owner migration и actual A09/A11 впереди |

Состояние owner VM здесь не проверялось: последнее exact0b7e24ee/recovery-v2/
connect2/TG disabled-empty, binding committed, ACK NOT_ATTEMPTED. Cached owner
images и independently pinned receipt DAG ещё требуют отдельной аттестации;
disposable CI не подтверждает их соответствие. Fixed TEST interval
2026-10-02T00Z→2026-10-09T00Z не пересчитывается. PR24 Draft/open; main прежний.
VM/SSH/live Telegram/queue/ACK/activation/setWebhook/sends/billing/merge не выданы.

Единственное активное поручение — [targeted C8 R2](tasks/M2_HANDOFF.md).
Подробное evidence и сохранённый C6 receipt — runbook§0.6.29 и единый PR24 receipt.

</details>

<details>
<summary>История — C8-MIG-01 и завершённое поручение C6-R2</summary>

## Текущий статус — C8-MIG-01 OPEN; ограниченная доработка C6 / 2026-10-07 UTC

**C8-M2-CONNECT5-MIGRATION — CHANGES_REQUESTED. C0 принимает C8-MIG-01/P2.**
Migration остаётся REVIEW; owner migration не выдаётся до исправления, final CI
и targeted C8. Прежний C0 source/CI PASS дополнен новым подтверждённым blocker:
успешные CI scenarios остаются действительным evidence, но не закрывают audit drift.
Connect5 client findings01/02/03 и прежняя recovery acceptance не переоткрываются.

Проверенный code head **3f65be7a60a1271247d04f23cbe0b151f82d65a1**, tree
**5e4d0c741a2dcf9967c9c1502bc97ca6a78c9797**, diff base
**fbe13a24c8407ab94c1c4a997d4a3b50d7e41f00**. Текущий до этой coordination
docs-only head **e332989485dccba52c090c855f93a536b462c91b**, tree
**424edb39f7f2cbd183269f4c7dee924fb4ddb90d**; остальные224/228 blobs/modes равны
reviewed implementation. Helper blob **c5d91d930eb164d116b25564592f038ae425b83d**.

| Finding | Причина и наблюдаемый результат | Исправление / gate |
|---|---|---|
| C8-MIG-01 / P2 / OPEN | migration_results выбирает только текущее направление (lines2810–2818); migration_switch проверяет completion только выбранного направления (2890–2912). Изменённый forward-complete.database_sha256 допускает rollback двух images и новый preservation:PASS. После rollback удалённый/повреждённый forward-api-result не мешает повторному success. | Проверять существующий forward audit до первого rollback effect, закреплять inventory/hashes в immutable rollback intent, проверять на resume/retry; каждый done требует сохранённый result независимо от направления. Valid partial rollback сохраняется. |

**Собственный C0 reproducer:** Python3.12.14, exact helper blob выше; настоящие
migration_switch/migration_results/migration_manifest/migration_stage и private
file I/O. Docker/DB/prepared observations заменены repository fixture, без network.
Все три дефектных варианта воспроизведены: первый допускает2 simulated recreates,
оба completed retry возвращают success/0 new effects при нарушенном forward audit.
Два control cases: valid partial forward→rollback PASS/один rollback recreate;
actual-database observation drift → EGRESS_MIGRATION_CANONICAL_DATA_DRIFT до effects.
Это не actual Docker/PG execution и не доказательство потери БД или Telegram resend.
Проблема — ложное подтверждение целостности журнала и ненадёжное основание recovery.

По переданному владельцем C8 report:144 repository scoped PASS; дополнительные
22 PASS/3 FAIL воспроизводят один finding. C8 проверил чистый exact checkout и
самостоятельно сверил9 jobs,8 archives/228 blobs/modes,6 migration и2 relay reports.
Это C8-reported execution; C0 не заявляет прочтение отдельного C8 evidence.zip.
C0 собственный reproducer изложен в runbook§0.6.27.

Implementation CI37607152590 остаётся SUCCESS; отдельный docs CI37621480704 наe332
теперь также **all9 jobs/clean-source SUCCESS**, что C0 проверил свежим API read.
Ни один из них не содержит новых audit-tamper regressions и не закрывает C8-MIG-01.
Новый coordination commit меняет только четыре документа; его CI учитывается
отдельно. После code fix нужен actual final-head CI и targeted C8 по finding.

| Задача | Статус | Следующее действие |
|---|---|---|
| C8-MIG-01 | OPEN | Ограниченное исправление C6, затем targeted C8/C0 closure |
| M2-ENV-04-CONNECT5-MIGRATION | REVIEW | CHANGES_REQUESTED по одному P2 |
| C6-M2-CONNECT5-MIGRATION-R2 | TODO, выдано | Единственное active поручение в M2_HANDOFF |
| C8-M2-CONNECT5-MIGRATION | REVIEW | Первый review завершён; повтор после исправления |
| C3 client scope / findings01/02/03 | VERIFIED / CLOSED | Без новой code delta и без переоткрытия |
| M2 / ENV04 | IN_PROGRESS / REVIEW | Actual owner migration/A09/A11 ещё впереди |

Последняя подтверждённая VM остаётся exact0b7e24ee/recovery-v2/connect2,
TG disabled/empty, binding committed, ACK NOT_ATTEMPTED. Никакой automatic replay.
Соответствие cached owner images exact predecessor и independently pinned receipt
DAG ещё не аттестовано; CI построил disposable old images заново. Этот отдельный
owner prerequisite не закрывается исправлением C8-MIG-01. Fixed TEST interval
2026-10-02T00Z→2026-10-09T00Z и committed request не изменяются.
PR24 Draft/open; VM/SSH/live Telegram/queue/ACK/activation/setWebhook/sends/billing/
main merge/production/M3 этим поручением не выданы.

Единственное активное поручение C6-R2 — [M2_HANDOFF](tasks/M2_HANDOFF.md).
Finding/reproducer и точные пределы evidence — runbook§0.6.27 и единый PR24 receipt.

</details>

<details>
<summary>История — C0 source/CI PASS и завершённая выдача C8 migration review</summary>

## Текущий статус — C0 migration review PASS; независимый C8 выдан / 2026-10-07 UTC

**C0-M2-ENV-04-CONNECT5-MIGRATION — PASS в repository/CI scope.**
Новых блокирующих findings при source/evidence review не обнаружено. Это допуск
к независимому C8; migration task остаётся REVIEW до его verdict. Findings01/02/03
по connect5 client остаются CLOSED; новый migration path прежним C8 не покрыт.

Проверенный implementation head **3f65be7a60a1271247d04f23cbe0b151f82d65a1**,
tree **5e4d0c741a2dcf9967c9c1502bc97ca6a78c9797**, sole parent
**374bee801baaf8a70955750be57577d5875b82bf**. Accepted base
**14f794b650c935c47ab1e78474fda0d1df0a7277**; coordination
**fbe13a24c8407ab94c1c4a997d4a3b50d7e41f00** сохранён sole parent первого
implementation commit **5ea00119ddcee8508435246116a8a2d4b8970b0b**.
История линейная. Client blob **525381357de76ea1c570fd864f8df5e9781a87e2** прежний.
От coordination изменены ровно восемь разрешённых C6 файлов; domain/client/locks/
Compose/canonical originals и три прежних CI jobs не изменены.

[CI37607152590](https://github.com/Elefesys/ai-service-manager/actions/runs/37607152590)
— все **9 jobs и clean-source gates SUCCESS**. Tested merge
**88656774720f22a778b5421abc2ae820e4a9d285** имеет тот же tree; ordered parents:
main **22993f558c5e7e933c65e9c999933bd2e3ab41c4**, затем implementation head.
Logs подтверждают 661 unit, 393 integration, 111 frontend и 27 browser PASS.
Прежние 6 relay +6 lifecycle cases прошли на обоих Docker runners; шесть новых
migration shards покрывают intent/image/state interruption в обоих направлениях.

**Собственная проверка C0:** прочитаны code/contract/runbook delta; свежие refs,
jobs/logs; скачаны все восемь ZIP, проверены их SHA256 против GitHub digests.
В каждом архиве 228 Git blobs/modes, PAX source commit, tested-commit и пустой
worktree-status сверены с exact tree. Общий source.tar.gz SHA256
`03b4283d916f8a1d73a7417b4b9919ddbf0195a84a0f294542a6365bd3bfe8f9`.
C0 отдельно разобрал все шесть migration JSON: равные fingerprints31 таблицы и
DB identity, UNKNOWN/wire1, Console session, private original HTTPS200/anonymous403,
28 сохранённых файлов, before/after image maps, неизменный unrelated runtime,
SIGKILL/resume/explicit rollback и completed retry без recreate. Held durations
90.163–175.735s, все ≤180s. Оба прежних relay reports: TIMEOUT/False за5.005/5.006s,
все12 assertions PASS. Это независимая сверка actual CI evidence; новые локальные
Docker/PG/S3/browser/unit suites C0 не запускал и отдельный C8 не подменял.

Текущий C0 coordination меняет только четыре документа. Его code/test/workflow
bytes равны проверенному implementation; новый SHA не является tested target
CI37607152590. C8 проверяет exact **3f65be7a60a1271247d04f23cbe0b151f82d65a1**;
актуальное поручение читает из этого документационного descendant. Новый
coordination CI учитывается отдельно и не заменяет уже проверенное evidence.

| Задача | Статус | Следующий результат |
|---|---|---|
| C3-M2-ENV04-05 / C8-M2-CONNECT-BUDGET-R3 | VERIFIED | Принятый client scope, findings01/02/03 CLOSED |
| M2-ENV-04-CONNECT5-MIGRATION | REVIEW | C0 source/CI PASS; требуется независимый C8 |
| C8-M2-CONNECT5-MIGRATION | TODO, выдано | Scoped verdict на exact3f65be7a |
| M2 / ENV04 | IN_PROGRESS / REVIEW | Owner migration и actual A09/A11 ещё не выполнены |

**Owner applicability не подтверждена этим CI.** Последний owner receipt:
exact0b7e24ee425ebb429bf87dfe382cbd3fab883028/tree14a4033b849c736235653a5a85ec9e5112bfe727,
completed recovery-v2, cached connect2 images, TG disabled/empty, binding committed,
ACK NOT_ATTEMPTED. После C8 C0 выдаёт сначала read-only attestation реальной
receipt DAG и старых image bytes. Несовпадение cached operator с exact predecessor
— STOP для C0, без rebuild, правки старого receipt или нового baseline.
Независимый pin последнего owner receipt и реальные image IDs ещё нужны.
Fixed TEST interval2026-10-02T00Z→2026-10-09T00Z и committed request не меняются;
source-key revocation asm-telegram-test-env04 пока не подтверждён.

PR24 Draft/open, main прежний. Owner VM/SSH, live Telegram/queue/ACK/activation/
setWebhook/sends/billing mutation/merge не выданы этим review. После scoped C8:
отдельная owner выдача, migration/preflight, свежий readonly network/connection/
queue review и только затем actual A09/A11. Старый queue snapshot не актуализирован.

Единственное активное поручение — [C8-M2-CONNECT5-MIGRATION](tasks/M2_HANDOFF.md).
Полные job/artifact IDs и сохранённый C6 receipt — runbook§0.6.26 и единый PR24 receipt.

</details>

<details>
<summary>История — C3/C8 acceptance и завершённое поручение C6 migration</summary>

## Текущий статус — C3/C8 VERIFIED; C6 migration preparation / 2026-10-07 UTC

### Приёмка C0 после независимого C8

Accepted implementation head **14f794b650c935c47ab1e78474fda0d1df0a7277**, tree
**72b824d85091076a025998a71e564deab805b1cf**, parent **f6ba33a37b8f35070c2a2471f9e1b386297c049f**.
C3 R3 **3f0453904cefc8bd33b8fedd2095eb8c1a6089d8** и ancestry R1/R2 сохранены;
общий implementation base **9e165dd09f87663665e3dabae4f155e99e2639a6**.
Client blob **525381357de76ea1c570fd864f8df5e9781a87e2**.

C0 принимает переданный владельцем независимый отчёт **C8-M2-CONNECT-BUDGET-R3 — PASS**:
122 scoped tests PASS/77.49s и две отдельные пробы штатного AutoBackend PASS;
checkout до/после чистый. C8 проверил cancellation/repeated cancellation,
закрытие socket без GC, parallel isolation/client reuse, budgets/TLS/classification
и strict source/image pin. Новых findings нет; 01/02/03 не переоткрываются.
Это собственные проверки C8 по его отчёту, а не дополнительные запуски C0.
Docker/PG/S3/browser C8 локально не запускал; соответствующее evidence — final CI.

[CI37531243359](https://github.com/Elefesys/ai-service-manager/actions/runs/37531243359)
на этом head — все три jobs и workflow clean-source gates SUCCESS:
foundation112500874202 — 614 unit +393 integration PASS, smoke PASS;
browser112500873790 — 27 journeys PASS;
docker29-compatibility112500874064 — exact Engine29.8.2/8af9fe3, Compose5.5.1.
Оба runner исполнили 6 relay +6 lifecycle cases. Actual tested merge
**e0735be7e3bde206dee35d813f53f6c4b6a17179** имеет тот же tree и ordered parents
main **22993f558c5e7e933c65e9c999933bd2e3ab41c4** + accepted head.
C0 ранее сверил оба source archives/digests/226 file blobs/modes/status;
C8 независимо повторил эту сверку. В обоих relay reports TIMEOUT/False за5.006s;
все шесть before/after fingerprints31 таблицы равны, UNKNOWN/Console/receipts/wire1
и real interruption/legacy/drift guards сохранены.
Artifacts: foundation11445453916 SHA256
`eec9f1f5a005378467a03afb9004336b4185e878b97ad145d261e01bca35d198`;
Docker29 11445178285 SHA256
`5effc5734732747f92f27e55876c14f2b84eec84835c8eb9a81c4daa71106329`.
Единственная дополнительная workflow-правка C0 — foundation25→35;
остальные job limits, commands/assertions, product deadlines и recovery180s прежние.

**C3-M2-ENV04-05 — VERIFIED в code/runner scope, включён в integration branch PR24.**
C0 findings01/02/03 CLOSED; C8 task и C0 runner verification — VERIFIED.
Это приёмка проверенного implementation, без main merge или live acceptance.
Coordination commit этого поручения изменяет только четыре документа;
его production/test/workflow bytes совпадают с accepted head. Его собственный CI
фиксируется отдельно: SUCCESS37531243359 относится только к accepted head.

| Задача/этап | Статус | Scope / следующий результат |
|---|---|---|
| C3-M2-ENV04-05 | VERIFIED | Accepted connect5 implementation в PR24; rollout не исполнен |
| C0 runner verification | VERIFIED | CI37531243359, все3 jobs/source artifacts/clean-source |
| C8-M2-CONNECT-BUDGET-R3 | VERIFIED | Независимый PASS;122 cases +2 AutoBackend probes; новых findings нет |
| M2-ENV-04-CONNECT5-MIGRATION | IN_PROGRESS | Выдана C6 подготовка/реализация/disposable CI; возврат REVIEW |
| M2 / ENV04 | IN_PROGRESS / REVIEW | Owner migration и actual A09/A11 ещё впереди |

Единственное активное поручение C6, разрешённые файлы/CI extension и критерии —
[M2_HANDOFF](tasks/M2_HANDOFF.md). C0 coordination commit меняет только документы;
C6 сохраняет его parent и начинает от byte-identical accepted implementation.
### Состояние owner VM и граница этапа

Последний owner receipt: VM source **0b7e24ee425ebb429bf87dfe382cbd3fab883028**,
tree **14a4033b849c736235653a5a85ec9e5112bfe727**, завершённый `recovery-v2`,
прежние cached images/connect2, Telegram disabled и TG runtime fields empty.
Это последняя подтверждённая запись, не новая проверка VM.
Original deployment-before и recovery-v1 audit/recovery receipts сохраняются.
Binding уже committed2026-10-06T15:23:30.786130Z; повторное billing/setup не выдано.
ACK NOT_ATTEMPTED; прежняя попытка оборвалась на getWebhookInfo до ACK.
Автоматический replay не разрешён; после будущей миграции нужен свежий queue audit,
а не предположение о сохранности прежних четырёх событий.

Fixed TEST interval **2026-10-02T00:00:00Z → 2026-10-09T00:00:00Z** и committed
request не пересчитывать. Если интервал истёк до live-продолжения — STOP и отдельное
решение C0 о новом тестовом доступе, без изменения уже committed request.
Source-key revocation `asm-telegram-test-env04` не подтверждён; read-only source
access/его отзыв проверяются при будущем owner issuance, приватные ключи не передавать.

**M2 IN_PROGRESS; ENV04 REVIEW до actual A09/A11; PR24 Draft/open.**
Этим поручением выданы repository implementation и disposable CI проверки.
SSH/VM fetch/build/deploy/restart, real Telegram HTTP/queue/ACK, activation,
setWebhook, sends, billing/binding mutation, main merge, production и M3 не выданы.
Старые owner-command blocks не запускать. После migration REVIEW: C0 review,
actual final CI и scoped C8 изменённого migration path; затем отдельная выдача
owner migration, fresh readonly readiness/queue review и live A09/A11.

[Единый receipt](https://github.com/Elefesys/ai-service-manager/pull/24#issuecomment-6002169006).

</details>

<details>
<summary>История — завершённый этап R3 review / actual CI / C8 issuance</summary>

## История — R3 review и CI до завершения независимого C8

**C0 scoped R3 verdict: PASS; C0-M2-ENV04-05-03 CLOSED на R3.**
Findings01/02 остаются CLOSED на R2. C3-M2-ENV04-05 остаётся **REVIEW** до
actual final integration CI и независимого scoped C8; rollout не принят.

R3 **3f0453904cefc8bd33b8fedd2095eb8c1a6089d8**, tree
**bd72edd3a9b01bb5053478f96d5089289e8f2b38**, единственный parent
**41f74346b56009bda53fa637ed5adeb3fbb7c507**. Три разрешённых файла:
два tests и runbook. Production client/helper/pins/контракт/dependencies/locks
byte-exact R2; client blob **525381357de76ea1c570fd864f8df5e9781a87e2**.
R1/R2/R3 ancestry и failed candidate/CI37523378682 сохраняются.

Исправленная offline assertion проверяет ровно две согласованные пары:
DEPENDENCY_TIMEOUT/False либо DEPENDENCY_UNAVAILABLE/True; elapsed≤6s,
один application call, до/после REQUEST count1, SEND_EFFECT отсутствует.
Mapping обоих семейств/no fallback, CA/hostname, auth/DB/private S3 и readonly
после recreate сохранены. Ошибка не классифицируется по знанию fixture или ledger.
Новый real TCP refusal удерживает bound loopback port без listen на весь вызов,
проходит factory/injected production wrapper и проверяет один connect attempt,
точную UNAVAILABLE/True, elapsed<5s, отсутствие stream/pool connections.

C0 отдельно повторил `uv run --frozen --offline pytest -q -s --tb=short
tests/test_telegram_connect_budget.py -k 'real_tcp_refusal or stalled_readonly'`:
**6 PASS,19 deselected,21.39s**, refusal0.001s в обоих factory paths.
Неизменённые4 stalled TLS/response cases подтвердили TIMEOUT/False,
bounded5s и peer EOF/FD=-1 до teardown. Все non-doc tracked blobs локального
staging сверены с R3; четыре docs отличаются, полного R3 Git checkout/clean-source
C0 этим запуском не заявляет. Это real local TCP/TLS, не actual relay/PG/Docker.
C3-reported final614 PASS/0 FAIL,393 deselected и static/source/clean checks
сохраняются как author evidence до actual runner.

### C0 CI capacity correction — actual run37527283930 / 2026-10-06 UTC

Первый R3 integration candidate **f6ba33a37b8f35070c2a2471f9e1b386297c049f**,
tree **5a92a9fd51d001fe4fe9ef81b996dbafc7b689b2**, tested merge
**ecfacbb77fe490cd33ec12237197cdd6809160da**: browser112487381755 SUCCESS/27 cases,
Docker29 112487380957 SUCCESS/6 relay +6 lifecycle cases/clean-source.
Foundation112487381312 CANCELLED примерно на25-minute job limit: start20:33:01Z,
cancellation20:58:16Z. До остановки actual normal runner выполнил все6 relay cases
и6 lifecycle cases, static checks и **614 non-integration PASS** за90.26s.
Обычный393-case PG/S3/direct-wire suite начат, не завершён; final smoke/clean-source
gate не выполнены. Failure assertion в доступном логе не зафиксирована; полный CI
SUCCESS не заявляется. Это не новый C3 code finding и не разрешение C8/rollout.

Оба relay reports: все12 assertions PASS, одинаковые before/after fingerprints31
таблицы во всех6 циклах, UNKNOWN/session/receipts/wire1 сохранены. Actual offline:
normal Docker28.0.4/Compose2.38.2 — TIMEOUT/False за5.005s;
exact Docker29.8.2/8af9fe3/Compose5.5.1 — TIMEOUT/False за5.006s.
Artifacts11443883177/11443418323, ZIP hashes/226 source files/modes, tested merge
и пустой recorded worktree status проверены C0. Foundation workflow clean-source
SKIPPED; это не заменяется отдельной проверкой status. Полные digests — receipt.

**C0 разрешает и вносит одну инфраструктурную строку:**
`.github/workflows/ci.yml`, только `jobs.foundation.timeout-minutes:25→35`.
Measured normal relay stage завершился20:54:17Z, unit stage20:56:08Z: лимит25min
оставлял менее2min15s для393 PG/S3/direct-wire cases и final smoke. Запас35min
позволяет исполнить полный последовательный gate. Browser/Docker29 budgets прежние.
Ни одна command/assertion/collector/dependency не меняется; clean-source и artifact
steps сохраняются, continue-on-error/skip/xfail не добавляются. Product deadlines
5/10/20s, phase limits и recovery operation bound180s неизменны.
Это C0 integration/CI capacity scope, не расширение production R3 или C6 VM scope.

Новый final candidate — один commit поверхf6ba33a3; production/test blobs exact R3.
Выполняется новый полный трёх-job CI на этом SHA; прежние PASS не переносятся
на новый head как его результаты. Только после всех actual gates — C8 по выданному
scoped handoff. Findings01/02/03 CLOSED; C3 REVIEW, M2 IN_PROGRESS/ENV04 REVIEW.

| Задача/этап | Статус | Следующее evidence |
|---|---|---|
| C3-M2-ENV04-05 | REVIEW | C0 scoped PASS; actual final-head CI, затем C8 |
| C0 runner verification | IN_PROGRESS | Exact final candidate, все3 jobs и artifacts/clean-source |
| C8-M2-CONNECT-BUDGET-R3 | TODO | Начинать только после C0-подтверждённого final CI SUCCESS |
| M2 / ENV04 | IN_PROGRESS / REVIEW | Actual A09/A11; VM migration ещё не выдана |

Один активный этап и conditional C8 scope — [M2_HANDOFF](tasks/M2_HANDOFF.md).

VM сохраняется на **0b7e24ee425ebb429bf87dfe382cbd3fab883028** /
tree **14a4033b849c736235653a5a85ec9e5112bfe727**, прежние cached images,
connect2, Telegram disabled/empty. Binding committed; ACK NOT_ATTEMPTED/replay-blocked.
Private receipts/inputs/runtime и fixed TEST interval2026-10-02→2026-10-09 UTC
сохраняются. Source/image/recovery migration — отдельное последующее поручение C6
после CI/C8; старые owner blocks не запускать. Сейчас нет VM fetch/rebuild/deploy,
ACK/setWebhook/activation/sends. M2 IN_PROGRESS, ENV04 REVIEW до actual A09/A11;
PR24 Draft/open, main merge/production/M3 не выданы. Source-key revocation не подтверждён.
[Единый receipt](https://github.com/Elefesys/ai-service-manager/pull/24#issuecomment-6002169006).

</details>

<details>
<summary>История — finding03 OPEN и R3 IN_PROGRESS до R3 review</summary>

## История — R2 actual CI failure и выдача R3

**C0 verdict: CHANGES_REQUESTED по новому C0-M2-ENV04-05-03 / P2 (OPEN).**
C3-M2-ENV04-05 возвращена в **IN_PROGRESS** на ограниченную R3.
Findings01/02 остаются CLOSED на R2: actual runner failure не относится к cleanup
или exact source pin. Независимый C8 пока не выдаётся; rollout не принят.

R2 **41f74346b56009bda53fa637ed5adeb3fbb7c507** сохранена в integration candidate
**ad724e68614c2942b73eaae41e6d8802d1663b84**, tree
**50f13bafc84b48c3e941764b5297fa9bdb13a273**; ordered parents
**e4f018af92d344429df4beb224262d0c87e985b3**,
**41f74346b56009bda53fa637ed5adeb3fbb7c507**.
PR tested merge **f6c2bd6f574831ced9996c042818240b668f9175** имеет тот же tree и
ordered parents main22993f558c5e7e933c65e9c999933bd2e3ab41c4 +candidatead724e68.
Сборка candidate не была merge PR/main или rollout.

[Actual CI37523378682](https://github.com/Elefesys/ai-service-manager/actions/runs/37523378682):
foundation112474140017 **FAIL**, exact Docker29 112474139579 **FAIL**.
В обоих одна ошибка:
`tests/test_telegram_egress_postgres.py::TelegramEgressPostgresChecks::test_readonly_tls_mapping_and_auth_db_s3_survive_relay_failure`,
R2/integration line446: `assert offline.value.definitely_unsent`.
Actual `TelegramError(DEPENDENCY_TIMEOUT), definitely_unsent=False`.
Каждая real relay/PG lane: **5 PASS/1 FAIL** (32.47s /37.70s).
Browser112474140023 **SUCCESS:27 journeys PASS**, его workflow clean-source PASS.
Docker29 actual Engine29.8.2/8af9fe3, Compose5.5.1 подтверждены; old mapped-host
failure воспроизведён. Source/image prepare прошёл; полный relay/recovery receipt
не создан из-за failure на postgres_wire.

C0 проверил оба ZIP SHA256 и все226 archive file blobs/modes: exact candidate tree,
recorded tested commit совпадает, recorded worktree-status пуст. Artifact IDs
foundation11440544000 /Docker29 11441466330. Их workflow clean-source steps
**SKIPPED**, не PASS: отдельная C0 проверка пустого status не заменяет execution gate.
Остальные полные backend/PG/direct-wire gates не завершились после ранней relay
ошибки. Итог browser/run и точные artifact digests — в едином PR receipt.

Диагноз по source control flow: прежняя assertion предполагала connect2 < readonly5.
Теперь connect5 включён в тот же outer readonly5; в наблюдённой stopped-relay
попытке общий deadline не даёт доказательства wire phase. Консервативный
DEPENDENCY_TIMEOUT/false соответствует принятому контракту. Сетевой fast refusal
может дать доказанный ConnectError раньше deadline; нельзя закреплять результат
всех offline requests одним флагом. Причина конкретного сетевого молчания/hop не
устанавливалась и не нужна для исправления ошибочного ожидания теста.

| Finding | Статус C0 | Решение |
|---|---|---|
| C0-M2-ENV04-05-01 / P2 | CLOSED | R2 cleanup,32 адресных C0 cases PASS |
| C0-M2-ENV04-05-02 / P2 | CLOSED | Exact final pin/old-tampered guards PASS; runner prepare прошёл |
| C0-M2-ENV04-05-03 / P2 | OPEN | Relay offline readonly assertion требует proven-unsent даже после общего deadline; R3 уточняет contract-aware test, без изменения production semantics |

**Единственная активная задача C3-M2-ENV04-05 / IN_PROGRESS:** R3 test-only correction.
Полный scope/criteria — [M2_HANDOFF](tasks/M2_HANDOFF.md). C8 и VM migration не выданы.

VM сохраняется на **0b7e24ee425ebb429bf87dfe382cbd3fab883028** /
tree **14a4033b849c736235653a5a85ec9e5112bfe727**, прежние cached images,
connect2, Telegram disabled/empty. Binding committed; ACK NOT_ATTEMPTED/replay-blocked.
Private receipts/inputs/runtime и fixed TEST interval2026-10-02→2026-10-09 UTC
не изменяются. До отдельного C0 поручения после CI/C8 нет owner commands,
source fetch/rebuild/deploy, ACK/setWebhook/activation/sends.
M2 IN_PROGRESS, ENV04 REVIEW до actual A09/A11; PR24 Draft/open.
Merge main/production/M3 не выданы; source-key revocation не подтверждён.
[Единый receipt](https://github.com/Elefesys/ai-service-manager/pull/24#issuecomment-6002169006).

</details>

<details>
<summary>История — R2 scoped verdict и runner issuance; actual failure выше</summary>

## История — C0 R2 scoped PASS до actual CI failure

**C0 scoped verdict: PASS; C0-M2-ENV04-05-01/02 CLOSED.**
C3-M2-ENV04-05 остаётся **REVIEW** до actual final integration CI и независимого C8.
Закрытие двух конкретных defects не заменяет эти gates и не разрешает rollout.

R2: **41f74346b56009bda53fa637ed5adeb3fbb7c507**, tree
**9200aed964f22fc073341f2d448a5d82598d39cc**, единственный parent
**c009c8540146d0a16d44fccf662d6e4d50fc53b1**; исходный base
**9e165dd09f87663665e3dabae4f155e99e2639a6** сохранён. R2 меняет6 разрешённых
файлов, cumulative R1+R2 —8. Client blob **525381357de76ea1c570fd864f8df5e9781a87e2**;
helper меняет только одну строку SOURCE/client pin. Config/IMAGE/dependencies/locks,
остальные guards и утверждённые budgets/classifications прежние.

C0 повторил **32 адресных case:32 PASS,76.57 s** на Python3.13.15,
httpx0.28.1/httpcore1.0.9/anyio4.15.1. Cold TLS3.008s, строгий readonly3.012s<5,
одна попытка. Проверены factory и injected transport, GC-off peer EOF/FD=-1 до
teardown, outer timeout, explicit/repeated cancellation с исходной отменой,
изоляция параллельного запроса и повторное использование client, phase/trickle/
cert/redirect/pool cases, final/old/tampered source и generated cached-image probe.
Четыре соответствующих code/test blobs сверены с R2 byte-exact; staging основан
на ранее принятом source. Это scoped local loopback TCP/TLS evidence, не полный
R2 checkout/full-suite rerun, actual image/Docker/PG/relay или независимый C8.
Git subprocess и Docker boundary в source/image unit cases substituted;
сам hash probe исполнялся по реальным bytes.

C3 сообщил на final R2:612 non-integration PASS/0 FAIL,393 deselected,
Ruff/format/mypy/contracts и source_check(final_SHA) PASS. Эти полные результаты
пока C3-reported; C0 проверяет actual runner отдельно. Locked private seams wrapper
допустимы в выданном asyncio scope; при обновлении зависимостей нужны повторные
regressions. В C0 scoped review новых blocking findings не найдено.

| Finding | Статус C0 | Основание |
|---|---|---|
| C0-M2-ENV04-05-01 / P2 | CLOSED на R2 | Только незавершённый TLS TCP transport abort, без await/tasks/GC; исходная отмена, соседний запрос и client сохранены;32-case subset PASS |
| C0-M2-ENV04-05-02 / P2 | CLOSED на R2 | Exact final blob закреплён одной строкой; final bytes PASS, base/R1/tampered/CRLF и несовместимый image-probe FAIL как требуется; guards сохранены |

| Задача/этап | Статус | Следующее evidence |
|---|---|---|
| C3-M2-ENV04-05 | REVIEW | R2 reviewed C0; actual integration CI и независимый scoped C8 |
| C0 runner verification | IN_PROGRESS | Final candidate/head/tree;3 workflow jobs, artifacts/checkout/clean-source |
| M2 / ENV04 | IN_PROGRESS / REVIEW | Actual A09/A11; VM migration ещё не выдана |

Одно активное поручение и его scope — [M2_HANDOFF](tasks/M2_HANDOFF.md).

VM сохраняется на **0b7e24ee425ebb429bf87dfe382cbd3fab883028** /
tree **14a4033b849c736235653a5a85ec9e5112bfe727**, прежние cached images,
connect2, Telegram disabled/empty. Binding committed; ACK NOT_ATTEMPTED/replay-blocked.
Private receipts/inputs/runtime и fixed TEST interval2026-10-02→2026-10-09 UTC
не изменяются. До отдельного C0 поручения после CI/C8 нет owner commands,
source fetch/rebuild/deploy, ACK/setWebhook/activation/sends.
M2 IN_PROGRESS, ENV04 REVIEW до actual A09/A11; PR24 Draft/open.
Merge main/production/M3 не выданы; source-key revocation не подтверждён.
[Единый receipt](https://github.com/Elefesys/ai-service-manager/pull/24#issuecomment-6002169006).

</details>

<details>
<summary>История — R1 review и R2 IN_PROGRESS; заменено R2 REVIEW</summary>

## История — C0 R1 verdict и разрешение R2

**C0 verdict: CHANGES_REQUESTED. Кандидат не принят к интеграции/rollout.**
C3-M2-ENV04-05 возвращена в **IN_PROGRESS** на одну ограниченную доработку R2.
Это продолжение той же задачи, не новый parallel handoff.

Проверен опубликованный candidate **c009c8540146d0a16d44fccf662d6e4d50fc53b1**,
tree **5ae67b29d020b186a19330531d990f09e3455692**, единственный parent
**9e165dd09f87663665e3dabae4f155e99e2639a6**. Ровно6 разрешённых файлов;
production delta пока ровно connect2→5 в TelegramClient. Branch
`c3/m2-telegram-connect-budget` указывает на этот candidate; PR24 остаётся Draft/open.

C3 сообщил final local593 PASS/3 FAIL,393 integration deselected; Ruff/format/strict
mypy/contracts PASS. Docker scripts не исполнены: отсутствует Docker, relay script
остановлен штатным non-root guard. Actual PG/S3/relay/Docker29, workflow gates и C8
не подтверждены. Привязанных PR workflow runs connector не вернул; CI PASS не заявляется.

C0 отдельно повторил4 адресных case на Python3.13.15 и locked
httpx0.28.1/httpcore1.0.9/anyio4.15.1: **1 PASS,3 FAIL,14.27 s**.
Cold TLS3.017 s, strict readonly3.030 s<5, один TCP/HTTP attempt — PASS.
Оба stalled-TLS cleanup case повторили `TCP_PEER_STILL_OPEN accepted=1 closed=0`
при пустом pool; source-guard unit test повторил `EGRESS_APP_SOURCE_CHANGED`.
Четыре candidate code/test blobs сверены byte-exact с GitHub; остальной local staging
взят из прежнего принятого source. Это адресное local loopback TCP/TLS evidence,
не полный candidate tree/clean checkout, не повтор всего suite и не Docker/PG/live.
В source-guard unit test git subprocess substituted; сам guard читает реальные bytes.

| Finding | Статус | Решение C0 |
|---|---|---|
| C0-M2-ENV04-05-01 / P2 | OPEN | TCP leak при outer timeout/explicit cancellation во время TLS. Разрешён узкий cancellation-safe cleanup в TelegramClient с сохранением исходной отмены и классификации |
| C0-M2-ENV04-05-02 / P2 | OPEN | Новый client не совпадает со strict SOURCE pin. Guard работает правильно; разрешена замена только client blob после окончательного cleanup, без ослабления проверки |

У locked httpcore1.0.9 `AnyIOStream.start_tls` закрывает stream в
`except Exception`; внешний asyncio.CancelledError туда не попадает, а
`AsyncHTTPConnection._connection` назначается только после TLS. C0 сверил этот
control flow с installed locked source и upstream tag. Он согласуется с воспроизведённым
дефектом; одного client.aclose()/пустого pool недостаточно для доказательства cleanup.

**Одна активная задача C3-M2-ENV04-05 / IN_PROGRESS:** R2 cleanup + final strict pin. Полное
разрешение paths/границы/criteria — [M2_HANDOFF](tasks/M2_HANDOFF.md). Новая VM-команда не выдана.

### Сохранённая owner boundary

Последний actual owner TLS receipt18:10:05.409401Z — TLSv1.3/2523 ms, одна попытка,
14 prior receipts/private inputs/images/runtime preserved; HTTP/queue/DB/ACK не было.
VM по-прежнему **0b7e24ee425ebb429bf87dfe382cbd3fab883028** /
tree14a4033b849c736235653a5a85ec9e5112bfe727, connect2, cached images, TG disabled/empty.
Binding committed; ACK NOT_ATTEMPTED/replay-blocked; frozen COMPED dates
2026-10-02→2026-10-09 UTC неизменны. До C0/C8 acceptance — никаких owner commands,
VM rebuild/deploy/source fetch, ACK/setWebhook/activation/sends. C6 migration source/images
и recovery state получит отдельную задачу после принятого кода.
Implementation CI37385698548 SUCCESS остаётся evidence только прежнего implementation.
**M2 IN_PROGRESS; ENV04 REVIEW до actual A09/A11; PR24 Draft/open.**
Прежние closures не расширяются. Merge/production/M3 не выданы; source-key revocation
не подтверждён. [Единый receipt](https://github.com/Elefesys/ai-service-manager/pull/24#issuecomment-6002169006).

</details>

<details>
<summary>История — выдача connect budget до C3 candidate; заменена R2</summary>

## Текущий статус — verified TLS выше connect budget / 2026-10-06

**Actual owner receipt 2026-10-06T18:10:05.409401+00:00, SSH_EXIT=0.**
Исправленный одноразовый token-free probe: DNS AF_UNSPEC/INET/INET6 PASS (7/0/0 ms),
TCP caller→relay IPv4 PASS (0 ms), ровно один verified TLS handshake PASS:
**TLSv1.3, 2523 ms, TLS_PASS_OVER_2S**. Лимит диагностического handshake был15 s;
в пределах2 s он не завершился, в пределах5 s завершился. Private inputs, все14
предшествующих receipts, images и существующий disabled runtime сохранены.

Это доказывает работоспособность TLS через выбранный маршрут в данной попытке и
наблюдённую задержку выше принятого connect=2 s. Не доказывает причину каждой прежней
ошибки, постоянную доступность Bot API или прохождение HTTP в общем5 s бюджете.
В этом probe не было HTTP, queue, DB или ACK. Прежний ACK остаётся NOT_ATTEMPTED,
его intent/result неизменны; retained=false означал неисполненную проверку.
Binding ранее committed (15:23:30Z), queue audit (15:44:48Z) увидел1 current +3
unmapped lifecycle events; свежая очередь после него не подтверждена.

Предыдущий probe17:58:12Z не выполнял DNS/TCP/TLS: C0 потерял @contextmanager при
сборке deadline, получил TypeError до resolver; это C0 artifact defect, не DNS
failure evidence. Исправленный embedded operator отличается ровно восстановленным
декоратором. Artifact111424 bytes, SHA256
`1cd0c50ecdc134778f912a4644b41f159f3d53df865df09759c64be6835049f0`.
Его once-only receipt сохранён; повторять исправленный или прежние scripts нельзя.
Подробные actual markers, ограничения local substituted tests и вся цепочка —
[единый receipt](https://github.com/Elefesys/ai-service-manager/pull/24#issuecomment-6002169006).

### Решение C0: узкая правка connect budget для code review

Наблюдаемое противоречие: доступный TLS путь занял2.523 s, тогда как M2_CONTRACT§10.6
и ENV04 runbook фиксируют connect≤2 s. C0 выдаёт **C3-M2-ENV04-05**: предложить и
проверить минимальную правку **connect2→5 s** в общем TelegramClient, без нового
env knob и без отдельного operator-only клиента. Это scope для изменения исходников
и review; текущий принятый контракт/VM остаются на2 s до приёмки новой реализации.

Pool2 s, read/write5 s, readonly5 s / send10 s / FETCH20 s wall deadlines,
lease30 s, pool≤4, TLS/hostname/SNI verification, fixed official origin,
trust_env=false, redirects/retries0 и UNKNOWN/no-resend semantics сохраняются.
Connect5 s не добавляется к общему deadline; общий deadline по-прежнему отменяет
операцию. При его срабатывании без доказанной wire phase нельзя объявлять send
definitely_unsent. Наблюдение2523 ms не обосновывает диагностические15 s в продукте.
Если целевые tests не проходят в этих границах, вернуть C0 evidence и предложение,
не повышать общие budgets и не менять маршрут самостоятельно.

Новая VM-команда сейчас не выдана. После reviewed patch и final-head CI требуется
независимый scoped C8; лишь затем C0 отдельно выдаёт C6 план перехода source/images
с сохранением recovery/binding/receipts, и owner получает готовый блок. Успех этой
диагностики не разрешает ACK replay, setWebhook, включение Telegram или live sends.

| Задача | Статус | Следующий результат |
|---|---|---|
| C3-M2-ENV04-05 | TODO | Reviewable connect2→5 patch с неизменными wall deadlines и transport/PG evidence |

Scope, base SHA, allowed paths и gates — [активный M2_HANDOFF](tasks/M2_HANDOFF.md).

VM остаётся на **0b7e24ee425ebb429bf87dfe382cbd3fab883028** /
tree **14a4033b849c736235653a5a85ec9e5112bfe727**, cached images, Telegram disabled/empty.
Implementation CI37385698548 all3 SUCCESS относится к этому implementation.
Новая docs-only координация не является новым implementation/CI/live PASS.
**M2 IN_PROGRESS; ENV04 REVIEW до actual A09/A11; PR24 Draft/open.**
Прежние C0/C8 closures сохраняют свой scope. Merge/production/M3 не выданы.
Source deploy-key revocation остаётся неподтверждённым. Fixed COMPED TEST interval
2026-10-02T00Z→2026-10-09T00Z и committed request не пересчитываются.


</details>

<details>
<summary>История — Owner ID correction; завершена, старую выдачу не выполнять</summary>

## Текущий статус — Business Owner ID correction / 2026-10-06

**Owner подтвердил перепутанные роли двух Telegram аккаунтов / 2026-10-06 20:02 +07.**
Первый аккаунт — владелец bot в BotFather; его можно использовать как test Client.
Второй — Business Owner,
к которому подключён @saasaimanagerbot. В staged expected Owner оказался numeric ID
первого аккаунта. Независимый ID второго предоставлен владельцем C0; значение остаётся
в private operator artifact/config, в публичных docs не публикуется. Скриншот второго
аккаунта показывает нужный bot, только выбранный test chat, включённые чтение/ответы;
это UI observation, не actual getBusinessConnection rights receipt.

Actual discovery на **0b7e24ee425ebb429bf87dfe382cbd3fab883028** завершился
`TELEGRAM_SETUP_DISCOVERY_UNRESOLVED`, `SSH_EXIT=1`, при PASS всех source/recovery,
operator-only override, TEST interval и runtime/private preservation guards.
По source control flow успешно выполнены getWebhookInfo/getMe и один getUpdates через
permanent TEST route; distinct candidates для прежнего expected Owner не равно1.
Смена confirmed expected Owner исправляет известное input mismatch; наличие свежего
lifecycle события и actual connection rights ещё предстоит проверить.

Recovery/preflight PASS от2026-10-06T07:58:54.204446+00:00 остаётся действующим;
C0-M2-ENV04-04 CLOSED, C8-01/02/03/04/05 CLOSED в принятом scope. Original before/audit,
cached images и runtime Telegram disabled/empty сохраняются. **M2 IN_PROGRESS;
ENV04 REVIEW до live acceptance; PR24 Draft/open, main22993f55 unchanged.**
VM использует exact source0b7e24ee/tree14a4033b849c736235653a5a85ec9e5112bfe727;
новые docs commits на VM не переносить.

Implementation CI37385698548 all3 SUCCESS и его независимая C0 приёмка сохраняются.
Предыдущий docs-only7eb6250de53a2c1bcf61f852911aa10eecb66cb8:
[CI37434755147](https://github.com/Elefesys/ai-service-manager/actions/runs/37434755147)
browser112173734971 и docker29-compatibility112173735337 SUCCESS,
foundation112173735207 CANCELLED; all3 SUCCESS этому docs head не приписывается.
Merge/production/M3 не выданы. Отзыв временного source deploy key остаётся неподтверждённым.

Следующее owner действие подробно в активном M2_HANDOFF и runbook§0.6.17.


</details>

<details>
<summary>История — recovery принят, первый discovery выдан до уточнения Owner</summary>

## Текущий статус — owner recovery PASS; discovery next / 2026-10-06

**Owner recovery + preflight PASS; C0-M2-ENV04-04 CLOSED по фактическому owner receipt.**
Владелец вернул `RECOVERY_RECEIPT_UTC=2026-10-06T07:58:54.204446+00:00`,
`RECOVERY_COMPLETE_PREFLIGHT_ONLY`, `SSH_EXIT=0`. Source exact
**0b7e24ee425ebb429bf87dfe382cbd3fab883028**, tree
**14a4033b849c736235653a5a85ec9e5112bfe727**. `TELEGRAM_EGRESS_RECOVER_PASS` и
`TELEGRAM_EGRESS_PREFLIGHT_PASS`; исходный baseline, private inputs/TLS и cached images
сохранены, Telegram runtime disabled с пустыми TG fields. Это owner execution;
прямого VM доступа у C0 нет. Mapping/recovery finding закрыт, live Telegram ещё не проверен.

Независимый C0 verdict на implementation остаётся PASS; C8-M2-ENV04-01/02/03/04/05
CLOSED в принятом scope. [Implementation CI37385698548](https://github.com/Elefesys/ai-service-manager/actions/runs/37385698548)
all3 SUCCESS; подробная проверка source/logs/artifacts — runbook§0.6.15 и единый receipt.
Documentation head e36a2c75d8ebb7071a6d1f88dab6fb20dfd7d297 также завершил
[CI37416231966](https://github.com/Elefesys/ai-service-manager/actions/runs/37416231966)
all3 SUCCESS: foundation112115338673, browser112115338704, docker29-compatibility112115338839.
Это не основание переводить VM с принятого implementation на новые docs commits.

**M2 IN_PROGRESS; ENV04 REVIEW до live acceptance; PR24 Draft/open, main unchanged.**
Единственный следующий owner шаг — однократный discovery через восстановленный TEST
egress, описанный ниже/в runbook§0.6.16. Setup/billing/binding/setWebhook, включение
api/worker и live A09/A11 выполняются отдельными шагами после его receipt. Успешные
recovery/preflight и implementation CI не повторять. Merge/production/M3 не выданы.
Временный GitHub deploy key `asm-telegram-test-env04` требуется отозвать после
успешного fetch; это отдельный source key, не SSH key входа на VM. Отзыв ещё не подтверждён.


</details>

<details>
<summary>История — независимая приёмка C0 и выдача recovery до owner receipt</summary>

## Текущий статус — C0 accepts recovery/resume; owner step / 2026-10-06

**Независимая приёмка C0 — PASS; C8-M2-ENV04-04/05 CLOSED на указанном implementation.**
Проверку выполнил C0 отдельно от автора C6: source review, CI logs/artifacts и17
дополнительных локальных fault/retry/drift cases. Отдельный новый агент/чат C8 не
запускался; это независимый C0 verdict, не заявка на отдельный C8 execution.
Прежние C8-01/02/03 остаются CLOSED. M2 IN_PROGRESS, ENV04 REVIEW до owner recovery
и live acceptance; PR24 Draft, main не меняется, merge/production/M3 не выполнялись.

Accepted implementation **0b7e24ee425ebb429bf87dfe382cbd3fab883028**, tree
**14a4033b849c736235653a5a85ec9e5112bfe727**. Base/main
**22993f558c5e7e933c65e9c999933bd2e3ab41c4**. CI
[37385698548 attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/37385698548)
SUCCESS: foundation112018306287, browser112018306004, docker29-compatibility112018306249.
Actual checkout всех трёх logs **fdfbe35974fa548b722622132aa0edb3a30c9bf5**;
ordered parents base → accepted implementation, tree равен implementation.
Оба штатных scripts и clean-source gates выполнены; дополнительный Docker29 gate PASS.
581 unit,390 PG/S3,111 frontend,27 browser; на каждом Docker runner6 transport +6
lifecycles. Новый documentation coordination не заменяет этот tested implementation.

C0 самостоятельно скачал оба ZIP11379768145/11379612211: digest совпал с Actions;
в каждом source archive225 blobs/modes/inventory совпали с GitHub tree, tested-commit
совпадает с checkout, worktree-status пуст. Штатный Engine28.0.4/Compose2.38.2;
exact Engine29.8.2/server8af9fe3/Compose5.5.1. Все fresh/recovery/recover-stopped/
recover-missing/legacy-disable/legacy-stop выполнены. Before/after durable receipts
равны целиком,31 tables, actual api/worker DB identity во всех трёх фазах совпадает;
Secure Console session, UNKNOWN/receipt и wire counter1 сохранены. Held timeout180s
не повышен. Fixture sequencing исправлено до создания следующего held baseline.

| Finding | Основание закрытия |
|---|---|
| C8-04 / P2 / E05 | Immutable exact original/disabled dotenv intent и stage receipts; own disable write не меняет архивируемый baseline/hash. Real legacy-disable/legacy-stop interruptions/retries PASS на двух runners. C0 проверил retry после env/callers/remove/stop/pre-receipt, completed retry без recreate и byte-exact before/audit/staged. |
| C8-05 / P2 / E05 | Caller/DB preservation отделена от running relay. Stopped relay проходит строгую identity/config/network проверку; missing требует exact generation/stop intent. Real stopped/missing recovery PASS на двух runners; C0 также проверил explicit schema2 rollback из обоих gaps. Foreign relay/config и прочий drift остаются STOP. |

17 C0 checks:9 legacy interruption/retry variants (отсутствующий/preexisting false
ключ),4 stopped/missing × recover/explicit rollback,4 input/baseline/intent negatives.
Исполнялся неизменённый helper с настоящими private files/locks/atomic writes;
Docker/DB/source boundaries в этих17 checks — substitutes, не local Docker evidence.
Реальная Docker/PG evidence — проверенный Actions run выше. New VM execution нет.

Current operator source **c29aabd36f4e81ee2d4b835bd921fa2de1ae5b14**, schema1,
original deployment-before PRESENT, after/rollback ABSENT по последнему owner receipt.
C0-M2-ENV04-04 operational finding остаётся OPEN до успешного owner recover/preflight.
Следующий шаг: filled checksum-guarded wrapper переводит только clean existing
checkout на accepted implementation и вызывает штатные recover + preflight.
Проверить private inputs/TLS/images/disabled-emptyTG/unrelated runtime и original
before до/после; before не переснимать. Новых app build/migrations/init/reset/down-v,
prepare/deploy/snapshot, manual hosts, global DNS/IPv6/downgrade или автоматического
rollback нет. При interruption продолжать только те же refs и guarded helper;
при unexpected drift STOP. Telegram activation/discovery/setup/webhook/send не входят.

Для source fetch используется прежний отдельный read-only GitHub deploy key, только
если он ещё разрешён или владелец временно вновь разрешит его. После fetch — отозвать.
Это не SSH key входа на VM. Credentials/keys/profile не публиковать. Новых платных
ресурсов нет. Условный CI-resume завершён; успешный implementation CI не повторять.


</details>

<details>
<summary>История — C6 REVIEW до независимой приёмки C0</summary>

## Текущий статус — C6 REVIEW: interruption/retry correction / 2026-10-06

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


**M2 — IN_PROGRESS. M2-ENV-04-TELEGRAM-EGRESS — REVIEW, C6.**
Независимый targeted C8 новой Docker29 mapping/recovery boundary: **CHANGES_REQUESTED**.
Открыты ровно **C8-M2-ENV04-04 и C8-M2-ENV04-05, P2 / E05**; прежние01/02/03
остаются CLOSED. Единственный активный handoff — M2_HANDOFF, bounded task
**M2-ENV-04-RECOVERY-RESUME**. Реализованы exact disable-first intent/stage retry и
attested stopped/missing relay continuation. Runbook§0.6.14 содержит assertions и
готовую процедуру; actual final-head execution — единый PR24 receipt. C8-04/05
не закрываются авторским REVIEW. Owner VM не изменялась; новые команды не выдаются.

Reviewed C6 head **94a402f3cf7c9d5ad9cd5837cd3d91d738fcf684**, tree
**2a1b4952514e3ce6c56207478ed330ab0d507a7a**. Accepted main/base
**22993f558c5e7e933c65e9c999933bd2e3ab41c4** прежний. Tested merge
**cd3e2f7255ec5815385397264c135a75ab850a97**: ordered parents base + reviewed head,
same tree. [CI37358453152](https://github.com/Elefesys/ai-service-manager/actions/runs/37358453152)
SUCCESS: три jobs, оба штатных scripts и clean-source gates;551 unit,390 PG/S3,
111 frontend,27 browser,6+2 transport/E05. Full C6 receipt:
[PR24 comment6001161023](https://github.com/Elefesys/ai-service-manager/pull/24#issuecomment-6001161023).
C0 проверил refs,12 allowed paths и225 source blobs/modes. PR24 Draft/open/not merged.

Native private IPv6/all-callers/flags0 mapping, exact Docker29 reproduction,
fresh lifecycle и выполненные recovery/transport cases подтверждены.
Эти результаты сохраняются; новый отказ относится к невыполненным interruption
boundaries. Для C0-M2-ENV04-04 подтверждено исправление IPv6 mapping; operational finding
остаётся OPEN до закрытия двух E05 findings и приёмки полного owner recovery.

| Finding | Фактическая причина и ограниченная доработка |
|---|---|
| C8-M2-ENV04-04 / P2 / E05 | Schema1 rollback архивирует исходный runtime env, затем сам добавляет enabled=false. При interruption после этой записи или первого recreate повтор останавливается EGRESS_BUNDLE_CHANGED до runtime calls. Нужен guarded retry разрешённого disable-first transition без ослабления остальных hashes и без перезаписи original audit/before. |
| C8-M2-ENV04-05 / P2 / E05 | После schema2 manifest interruption внутри relay recreate может оставить relay stopped/missing. Повтор recover проходит через legacy attestation и безусловный after['telegram-egress']; KeyError/STOP возникает до repair. Такая же предпосылка блокирует legacy rollback при stopped relay и после его stop до receipt. Нужно проверяемое продолжение ожидаемого промежуточного состояния своего relay. |

C8 воспроизвёл actual unchanged Python helper paths с bounded synthetic Docker/DB/
source boundaries; это не новый Docker/VM execution. Real CI проверял SIGKILL после
manifest и успешные command boundaries, а не оба найденных случая. ZIP-byte/all-archive
verification остаётся отдельным C6 receipt; C0/C8 не выдают его за собственную загрузку.
Полное disposition, exact lines и scope correction — runbook§0.6.13.

Сохранить schema1/c29 owner state, original deployment-before, private inputs, images,
HTTPS/emptyTG, DB/S3/Console/UNKNOWN. Не повторять prepare/deploy/snapshot, не стирать
audit/state, не выполнять rollback/activation автоматически. Temporary GitHub key
asm-telegram-test-env04 подлежит отзыву после confirmed fetch; SSH key входа прежний.
После bounded correction — final-head full CI и targeted C8 только04/05/затронутых
инвариантов; затем C0 owner step. Live A09/A11, owner merge и push/main CI впереди.
Production/M3 не выдаются. Coordination меняет только четыре документа; его exact
refs/CI в PR receipt, без SHA-only commit.


</details>

<details>
<summary>История — C6 Docker29 correction REVIEW до targeted C8</summary>

## История — ENV04: Docker29 mapping и partial-deploy recovery / 2026-10-05

**M2 — IN_PROGRESS. M2-ENV-04-TELEGRAM-EGRESS — REVIEW, C6.**
Новое ограниченное поручение **M2-ENV-04-DOCKER29-MAPPING** закрывает наблюдаемую
на owner VM находку **C0-M2-ENV04-04, P2 / E02 и E05**. Это C0 operational finding,
не новый вердикт C8. Прежние C8-M2-ENV04-01/02/03 остаются CLOSED; их exact-source
CI/review evidence сохраняется. Единственный активный handoff — верхний M2_HANDOFF;
новый VM receipt и причина — runbook§0.6.11. Владелец пока не выполняет новые команды.

Repository **Elefesys/ai-service-manager**, PR24 **Draft / OPEN / NOT MERGED**,
branch **c6/m2-telegram-live → main**. Accepted main/base
**22993f558c5e7e933c65e9c999933bd2e3ab41c4** неизменён. Исследованный PR/VM checkout
**c29aabd36f4e81ee2d4b835bd921fa2de1ae5b14**, tree
**2994f5f259321f1a13639107a28dbcac52e1c403**; implementation d57ae07f10cd603910876068da444829b326bdab.
[CI37300041270](https://github.com/Elefesys/ai-service-manager/actions/runs/37300041270)
SUCCESS; tested merge d286d72cf9b6b0ee1089283ba4bbe4aeab230fe8, same tree.
Последующий coordination меняет только четыре документа; его head/tree/CI — PR receipt.
Сохранить всю историю, не создавать SHA-only commit и не обновлять VM вслед за docs.

**Owner evidence:** source fetch/exact checkout и prepare/verify PASS. Deployment
частично выполнен: relay running, api/worker пересозданы с теми же images,
Telegram=false/четыре TG fields пустые. deployment-before.json PRESENT;
deployment-after.json и rollback.json ABSENT. Штатное сравнение original baseline
с actual snapshot PASS: env/process/images/mounts/default gateway, actual SQL DB
identity и unrelated containers сохранены. Диагностика не изменила private files
или runtime. Это не проверка всех business rows или новый Console login.

**Отказ:** у api И worker Compose/HostConfig имеют IPv4 + mapped IPv6, но
/etc/hosts — две IPv4-записи и ни одной mapped. AF_UNSPEC/AF_INET дают relay;
AF_INET6 с исходными flags=0 даёт один посторонний native IPv6. Только отдельная
диагностическая проба AI_V4MAPPED даёт mapped relay — она не заменяет preflight.
Engine29.8.2/API1.56, server commit8af9fe3; Compose5.5.1; Python3.13.15/glibc2.36;
host/container IPv6 не отключён. Exact Engine source подтверждает Unmap() для
extra_hosts перед передачей в sandbox; полные refs и доказательства — §0.6.11.

C6 исправляет воспроизводимый opt-in mapping трёх callers без public/DNS fallback
и готовит guarded helper recovery от этого partial state с неизменным первоначальным
deployment-before. Нельзя просто повторить deploy/snapshot, очистить state, вручную
патчить hosts или заменить AF_INET6 проверку диагностическим AI_V4MAPPED. Actual
Docker29 regression, прежние E01–E06/full CI и targeted C8 по новой boundary — до
возобновления owner deployment. App/source pins, env/HTTPS/TG split, DB/S3/Console,
UNKNOWN/no-resend и отсутствие app build/migrations/reset на VM обязательны.

**C6 correction / REVIEW:** native ULA endpoint того же relay, отдельный internal
IPv6-only bridge с bounded /64 IPAM; flags=0 сохранены. Явный `recover` принимает
только partial schema1/c29aabd36, сохраняет original before и старые generated bytes,
атомарно публикует новую generation и повторяет guards после interruption. Deploy/
snapshot отказываются заменять existing before. Explicit rollback остаётся disable-first.
Фактический старый отказ всех трёх callers воспроизведён до исправления на exact
Engine29.8.2/8af9fe3 + Compose5.5.1: CI37351449973, compatibility111903261317 SUCCESS.
Новая обязательная lane повторяет reproduction и corrected Docker/PG/S3 lifecycle;
оба прежних jobs/scripts/gates неизменны. Exact final head/tree/merge/parents/run/jobs
и результаты находятся в едином C6 receipt PR24, без SHA-only commits. Подробные
assertions и подготовленные recovery/rollback команды — runbook§0.6.12.
CI37355302621 подтвердил native mapping, шесть transport cases и fresh lifecycle
на Docker29 и штатном runner; browser PASS. Следующий E05 case остановился на
empty-DB guard: первый case законно оставляет SEALED billing catalog. Fixture теперь
сохраняет неизменный исходный empty guard для fresh, затем требует exact fingerprint
всех31 таблицы после scoped cleanup и перед recovery. Три созданные catalog rows
сохраняются byte-for-byte; другие domain/auth rows обязаны отсутствовать. Catalog
не удаляется, trigger не отключается, тайм-аут180s и durable assertions прежние.

CI37356534441: foundation111920229766 и browser111920229503 SUCCESS;551 unit,
390 PG/S3,111 frontend,27 browser,6 transport + fresh/recovery E05, оба штатных
scripts/clean gates прошли. Recovery SIGKILL/resume/drift/rollback PASS в157s при180s.
Compatibility остановился на startup старой DNS fixture; она не резервировала static
DNS address от dynamic IPAM. Добавлены reservation/assertion и bounded diagnostics;
исторический stderr не сохранён, точный прежний Docker response не заявляется.
Полный final-head CI после этого изменения — в итоговом PR24 receipt.

Это авторская передача, не C0 acceptance/C8 PASS и не owner deployment.

Temporary GitHub deploy key asm-telegram-test-env04 подлежит отзыву после уже
подтверждённого fetch; напоминание выдано, отдельного owner подтверждения отзыва пока
нет. SSH key входа не менять. Не повторять Console provisioning/secret entry или
temporary getMe. Discovery/setup/webhook/activation/send ещё не выполнены; billing
interval проверить перед первой setup-попыткой, затем сохранять те же IDs/dates.
M2 закрывается только после actual route/live A09/A11, owner merge и отдельного
successful push/main CI. Production/M3 и новый бюджет не выдаются.

</details>

<details>
<summary>История — приёмка code и source access до фактического deployment</summary>

## История — TEST egress code принят; далее owner deployment / 2026-10-05

**M2 — IN_PROGRESS. M2-ENV-04-TELEGRAM-EGRESS — REVIEW: code принят C0/C8,
owner deployment и интеграция ещё не выполнены.** Нового implementation задания C6
нет. Единственный следующий шаг — C0/владелец: временный read-only GitHub source
access, затем точный checkout и accepted disabled deploy/preflight. Верхний
M2_HANDOFF и runbook§0.6.10 — текущие инструкции; прежние findings/задачи ниже — история.

Accepted implementation head **d57ae07f10cd603910876068da444829b326bdab**,
tree **bc8b10fe8be27c237e0b62665068c0ef9e14ece5**. Tested virtual merge
**91720ac87671166e3a066b9301fe29a6762b05fb**: ordered parents accepted base
**22993f558c5e7e933c65e9c999933bd2e3ab41c4** + implementation head; tree совпадает.
[CI37297119410, attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/37297119410)
**SUCCESS**:531 unit,390 PostgreSQL/S3,111 frontend,27 browser,6+1 relay/E05;
оба штатных scripts и clean-source gates. Foundation111720865066 и browser111720864815
checkout exact tested merge. [C6 full receipt](https://github.com/Elefesys/ai-service-manager/pull/24#issuecomment-5992911966).

**C0 ACCEPTED / независимый targeted C8 PASS. Все C8-M2-ENV04-01/02/03 CLOSED.**
Последний review выполнен по01 и изменённым runtime-overlay/baseline/HTTPS/rollback
boundaries, не по всему будущему продукту. C8 независимо сверил26 Git blobs,
оба execution logs и выполнил local substituted boundary checks. HTTPS/empty TG
сохраняются; изменения9 runtime fields, двух operational inputs и runtime.json
отвергаются прежними guards.11 AST boundaries подтверждают сохранение закрытых
02/03 и E02–E04. C0 сверил fresh GitHub refs/девять paths/CI и принял результат.

Real Docker baseline использует прежний двухфайловый recipe до prepare, затем
stage TG без recreate. Exact CLI сохраняет два HTTPS values, disabled/empty TG,
private input bytes и ту же actual БД callers. Secure Console session, UNKNOWN/
receipt, fingerprints31 таблицы и persistent counter1 проходят deploy/rollback.
Guard обходов и ослабления TLS/timeouts/UNKNOWN нет; приложение/root Compose/
workflows/pins/dependencies/migrations неизменны. Zip verification остаётся receipt
C6: C0/C8 ZIP bytes повторно не скачивали. Local C8 substitutes не называются Docker
execution; реальная Docker/PG/S3/TLS проверка исполнена GitHub runner.

Repository **Elefesys/ai-service-manager**, **c6/m2-telegram-live → main**, PR24
остаётся Draft/open/not merged. Main22993f558c5e7e933c65e9c999933bd2e3ab41c4 не менялся.
История/первый coordinatione58c4a1a731ad238ccf9a79e6c478969642cd088 сохранены. Точный
последующий docs-only coordination head/tree/CI — PR receipt, без SHA-only commits.
Для VM C0 выдаёт полный принятый SHA отдельно; документационная версия не считается
уже развёрнутой. Runtime на VM80e51c43e31541940f1ccf18b8281adf1a061748,
tree88ed308b4c56114aa977dcf91204964d9b7348e5; Telegram disabled, private inputs прежние.

Source key ранее отозван в GitHub: разрешён только временный read-only deploy key
для этого repository, без PAT/write access. SSH key входа на VM не заменяется.
Далее guarded exact fetch/checkout с umask022 только для tracked source, preserve
private env/profile/TLS/image IDs/volumes, accepted prepare/verify/deploy/preflight.
По получении source key снова отозвать. Одна operator инструкция за шаг; при
расхождении bounded STOP, без reset/reclone/down-v или ручного исправления secrets.

Не выполнены actual persistent route на VM, discovery/binding/billing/webhook и
Client text+image → Console → manual reply → Client receipt. Owner provisioning,
secret staging и temporary getMe уже PASS, не повторять. До первого setup проверить
актуальность TEST billing interval; после попытки сохранить точные IDs/dates.
ENV04/M2 не объявлены INTEGRATED/VERIFIED; нужны owner evidence, merge владельцем
и отдельный actual main CI. ADR239/LOCAL-TEST и прежний бюджет сохраняются; M3 не выдан.

</details>

<details>
<summary>История — C6 REVIEW перед финальной приёмкой01 / 2026-10-05</summary>

## История — передача C6 до финального targeted review — TEST egress: остаток C8-01 передан на REVIEW / 2026-10-05

**M2 — IN_PROGRESS. M2-ENV-04-TELEGRAM-EGRESS — REVIEW, C6.** Исправлен только
остаток C8-M2-ENV04-01/P2/E05. Закрытые независимым targeted C8 находки02/03
сохраняются; новый targeted C8 по01 и затронутой boundary организует C0. Этот
implementation receipt не является C8 PASS или VERIFIED. PR24 остаётся Draft.

Repository **Elefesys/ai-service-manager**, branch **c6/m2-telegram-live → main**,
[PR24](https://github.com/Elefesys/ai-service-manager/pull/24). Accepted base
**22993f558c5e7e933c65e9c999933bd2e3ab41c4**. Старт correction после C0:
**6296f26f76c944b18a53feaba46a2b975eca247a**, tree
**3e1cbecb95d9220bfcc4ade5fb0907737eb1cedc**, CI37292611679 SUCCESS.
Первый coordinatione58c4a1a731ad238ccf9a79e6c478969642cd088 и вся история сохранены.
Final head/tree/tested merge, ordered parents и результат полного runner CI
публикуются одним receipt в PR24; отдельный SHA-only commit не создаётся.

Причина01 воспроизведена regression: `.env` с PG/S3 credentials, `.env.telegram`
с действующими HTTPS origin/endpoint и staged TG; actual callers уже HTTPS,
disabled/empty TG. Reviewed code отказал EGRESS_RUNNING_ENVIRONMENT_DRIFT.
Теперь prepare читает accepted inputs через Compose config без source/eval,
сохраняет ровно ASM_AUTH_ORIGINS/ASM_STORAGE_ENDPOINT в private runtime.json
вне checkout. API/worker получают эти два значения, staged TG не импортируются.
Hash/re-derivation overlay и прежний полный actual-environment guard обязательны;
неожиданный drift HTTPS/TG/DB/S3 по-прежнему отклоняется. Исходные files не меняются,
кроме прежнего enabled=false при rollback; ручной перенос owner не требуется.

39 targeted unit checks, Ruff и actual Compose config resolution локально PASS.
Локального Docker нет: real lane исполняется обычным GitHub runner. Новый Docker
baseline создаётся по прежнему двухфайловому recipe до generator. Exact CLI
prepare/deploy/preflight/rollback проверяет HTTPS/disabled/empty TG/staged bytes,
actual DB identity, прежние UNKNOWN/receipt/31 table fingerprints/counter1 и ту же
Console session через verified TLS/Secure cookie. Необходимый HTTPS fixture
использует существующий WEB_IMAGE pin, без host ports; шесть E02–E04 cases сохраняют
прежние HTTP TEST defaults и все transport assertions. Полные scripts/clean gates
и source artifact проверяются на итоговом head; результаты — PR receipt/§0.6.9.

Изменены только пять разрешённых code/test paths и четыре текущих документа.
Application, root Compose/workflows, pins/dependencies, migrations, TLS/deadlines,
UNKNOWN/no-resend и закрытые DB/path guards сохраняются. Owner VM/live не тронуты.
Процедура §0.6.9 подготовлена для отдельной выдачи C0 после targeted C8; activation,
discovery/setup/webhook/send, merge, VERIFIED и M3 в эту работу не входят.

</details>

<details>
<summary>История — C0 targeted verdict и выдача остатка01 / 2026-10-05</summary>

## История — решение C0 после targeted C8 — TEST egress: одна доработка после targeted C8 / 2026-10-05

**M2 — IN_PROGRESS. M2-ENV-04-TELEGRAM-EGRESS — IN_PROGRESS, C6.**
Независимый targeted C8 реально выполнен: **CHANGES_REQUESTED** только по остатку
C8-M2-ENV04-01; 02/03 закрыты. Это review готовой коррекции, не повторный plan review.
Единственное текущее поручение — верхний активный M2_HANDOFF; receipt — runbook§0.6.8.
Предыдущие REVIEW/«три fixes» ниже сохранены как история, не текущие инструкции.

Repository **Elefesys/ai-service-manager**, существующий [Draft PR24](https://github.com/Elefesys/ai-service-manager/pull/24),
branch **c6/m2-telegram-live → main**. Accepted base/main
**22993f558c5e7e933c65e9c999933bd2e3ab41c4**, tree
**c30415b48a08dabac6a59f1294843a0bd25ff353**, push/main CI37016012805 SUCCESS.
Первый coordinatione58c4a1a731ad238ccf9a79e6c478969642cd088 и вся история сохранены.
Продолжить от final coordination head в PR receipt/C0 сообщении; его source bytes
тождественны reviewed implementation. Без дополнительного коммита ради собственного SHA.

Проверен implementation head **2536a1aa2b41792fff381c4d222906e2ff9ad23c**,
tree **2efe2c9df60dd9118b24adbfa6e8b76cd98bfebd**. Tested merge
**8bb3f34e2ee122b033102a40eb53b2696a9bb70e** имеет ordered parents
**22993f558c5e7e933c65e9c999933bd2e3ab41c4** + указанный implementation head,
его tree совпадает. [CI37289340867, attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/37289340867)
SUCCESS: оба штатных scripts и clean-source gates, 530 unit, 390 PostgreSQL/S3,
111 frontend, 27 browser и 6+1 relay cases. Foundation job111695793211 и browser
job111695792866 действительно checkout этот tested merge.

| Finding | Targeted C0/C8 disposition |
|---|---|
| C8-M2-ENV04-01 / P2 / E05 | **OPEN, одна оставшаяся доработка.** Staged TG fields больше не входят в disabled runtime, но исключён весь .env.telegram, содержащий также действующие HTTPS ASM_AUTH_ORIGINS и ASM_STORAGE_ENDPOINT. Принятый pre-live recipe сохраняет их именно там; .env из init_local.py содержит только PG/S3 credentials. Поэтому model возвращается к localhost/http defaults, snapshot отказывает EGRESS_RUNNING_ENVIRONMENT_DRIFT до up. |
| C8-M2-ENV04-02 / E05 | **CLOSED на reviewed head.** Реальные API/worker SQL identities совпадают с isolated postgres/asm_local harness до/после exact deploy/preflight/rollback; отдельная asm_test отвергается. UNKNOWN, command receipt, та же HTTP Console session, fingerprints 31 таблицы и wire counter=1 сохранены. |
| C8-M2-ENV04-03 / E01 | **CLOSED на reviewed head.** Canonical destination проверяется до calls/mkdir/write; direct checkout и .. aliases отклоняются без effects. Symlink/.. не скрывается resolve; approved outside path проходит. Owner/mode/no-symlink guards сохранены. |

C0 проверил fresh GitHub metadata, scope и оба job logs; C8 сверил 26 exact blobs,
выполнил targeted source review и локальное воспроизведение: только две non-TG
HTTPS настройки отличаются, TG fields уже корректно пусты, отказ происходит до up.
Это воспроизведение принятой процедуры, не новая проверка private bytes owner .env
или VM execution. ZIP bytes C0/C8 повторно не сверяли; receipt C6 сохраняется отдельно.

Решение C0: сохранить принятые HTTPS origin/endpoint в private runtime model,
изолировать staged TG inputs, оставить строгий drift guard. Условие «только .env»
в первой коррекции было неполным и явно уточняется; private files владелец вручную
не переносит. Закрытые DB/path fixes и E02–E04/TLS/UNKNOWN сохраняются.

VM и live Telegram не менялись: runtime80e51c43e31541940f1ccf18b8281adf1a061748,
tree88ed308b4c56114aa977dcf91204964d9b7348e5, Telegram disabled. Console provisioning,
private inputs и single temporary getMe уже PASS; повторять их не нужно. Owner
deployment, discovery/binding/billing/webhook, Client text+photo → Console → manual
reply → Client receipt ещё не выполнены. После fix/final CI/targeted C8 C0 выдаст
один готовый operator шаг. PR остаётся Draft, merge и VERIFIED не объявляются.
M2 завершается только с real A09/A11, merge владельцем и отдельным actual main CI.
ADR239/LOCAL-TEST границы, запрет reset/down-v и прежний бюджет сохраняются.

</details>

<details>
<summary>История — C6 correction receipt до targeted C8 / 2026-10-05</summary>

## История: передача C6 до targeted C8 — TEST egress: исправления C8 переданы на REVIEW / 2026-10-05

**M2 остаётся IN_PROGRESS.** M1 и код M2.1–M2.4 приняты в прежнем LOCAL/TEST scope;
реальная переписка A09/A11 ещё не завершена. Единственная ближайшая implementation
задача — **M2-ENV-04-TELEGRAM-EGRESS — REVIEW**, C6; исправлены три P2 предыдущего
C0/C8 **CHANGES_REQUESTED**. Это передача на targeted C8, не его PASS.
Это ограниченное устранение подтверждённого сетевого blocker существующего TEST,
не новый Telegram adapter, production VPN или M3.

Repository **Elefesys/ai-service-manager**, существующий [Draft PR24](https://github.com/Elefesys/ai-service-manager/pull/24),
branch **c6/m2-telegram-live → main**. Accepted base/main:
**22993f558c5e7e933c65e9c999933bd2e3ab41c4**, tree
**c30415b48a08dabac6a59f1294843a0bd25ff353**;
[push/main37016012805](https://github.com/Elefesys/ai-service-manager/actions/runs/37016012805)
SUCCESS. Сохранить первый coordination commit
**e58c4a1a731ad238ccf9a79e6c478969642cd088** сохранён. Старт реализации:
**dbfba47a3d92bcee258f5ab490384f496e16a217**, tree
**8a0ac1988f8479f72d882bca53ed53c1ea63c216**, CI37270554509 SUCCESS.
Final head/tree/tested merge и final CI фиксируются в PR receipt без SHA-only commits.
VM checkout и application image остаются от **80e51c43e31541940f1ccf18b8281adf1a061748**,
tree **88ed308b4c56114aa977dcf91204964d9b7348e5**. Документационный head не выдавать
за фактически развёрнутое приложение.

Фактический progress, предоставленный владельцем:

- Console Owner/Workspace/Business созданы, login работает. Независимый Telegram
  Owner ID и Business/Secretary UI connection подготовлены; private config сохранён.
- Прямой VM/container TCP443 до Telegram timeout; поддержка FS471775 сообщила о
  воспроизведении и внешней фильтрации. Точный hop самостоятельно не установлен.
- 2026-10-05 token-free profile probe: verified TLS, HTTP302/CONNECT200/curl0,
  cleanup PASS. Это evidence конкретного тестового маршрута, не ремонта direct egress.
- **2026-10-05 12:50 Asia/Novosibirsk:** исправленная процедура
  **cc799386a922eaca78376a7acc0a2687a8465f2e32a8558643b7de5421174ba1** прошла на VM:
  exact source/runtime-off, fixed relay config, token-free TLS, отказ при выключенном
  relay с тем же hosts mapping, **один actual getMe со строгой bot identity**, unchanged
  application/private inputs, cleanup и SSH_EXIT0. Временные ресурсы удалены.

Предыдущая версия процедуры остановилась до HTTP/getMe: C0 ошибочно вычислил reference
hashes по локальным копиям с лишним trailing LF. Ошибка проверочного artifact исправлена
по canonical Git blobs, без нормализации/ослабления проверки. Targeted C3 review фикса
PASS; exact VM исполнение затем PASS. Это не C8. Полные refs и границы — runbook§0.6.

**Решение C0 по scope:** разрешено подготовить opt-in TEST Compose overlay, приватный
генератор config, отдельный официальный Xray pin и необходимые проверки новой сети;
точный allowlist и критерии E01–E06 — единственный активный M2_HANDOFF. Прежние app,
миграции, grants, storage pins, contracts и защитные assertions сохраняются. API/worker/
operator route должен сохранить TLS, official origin, deadlines и UNKNOWN/no-resend.
Scheduler route не нужен по проверенному текущему коду. ADR239 остаётся принят:
этот временный synthetic TEST путь не разрешает production Client traffic.

Проверен implementation head **3fffdda5d5e3f866cf2f25c30bc9e619091de081**,
tree **6ffff63ac85097ab63e53538213bde9cde70edc6**. Tested merge
**160a9f41de201308e92121fc05f996006af92894** имеет ordered parents
accepted base22993f558c5e7e933c65e9c999933bd2e3ab41c4 + указанный implementation head;
его tree совпадает. [CI37281699500](https://github.com/Elefesys/ai-service-manager/actions/runs/37281699500)
SUCCESS: оба штатных scripts и clean-source gates,526 unit/390 PostgreSQL-S3/
111 frontend/27 browser и6+1 relay cases. Это фактический successful run,
но его E05 fixture не доказывает сохранность БД пересоздаваемых callers.

Независимый scoped C8 реально прочитал готовый diff/CI и выполнил локальные synthetic
reproductions. C0 также воспроизвёл EGRESS_RUNNING_ENVIRONMENT_DRIFT по текущему
VM staged-vs-running состоянию. **Три P2 findings**: C8-M2-ENV04-01 — disabled
deployment не принимает подготовленные отдельно секреты; -02 — E05 проверяет
другую БД; -03 — lexical path guard допускает private state внутрь checkout через .. .
Полный receipt/границы — runbook§0.6.6; один точный fix task — активный handoff.
E02–E04 transport/TLS/media/UNKNOWN evidence сохраняется. VM не менялась; C0 не
выдаёт deployment до fix/final CI и targeted C8. Это существующие E01/E05,
без расширения M2 или пересмотра ADR239. ZIP bytes C0/C8 повторно не сверяли;
отдельная проверка ZIP C6 сохранена как его receipt.

Ограниченная доработка начинается от coordination **7a9eca3d2e1509b029d1ef0ba2f2c0d2d590ce7c**,
tree **1da0e2da06269457e91de1752fe224f93681b8ba**, CI37285033299 SUCCESS; история
сохранена. C8-01: runtime Compose использует текущий `.env`; staged `.env.telegram`
доступен только явно выданному one-shot operator, deploy его не применяет. Rollback
выключает runtime в `.env`, сохраняет остальные bytes и staged inputs целиком.
C8-02: E05 удерживает реальные UNKNOWN/receipt/Console session в fresh isolated
`postgres/asm_local`, общей с пересоздаваемыми api/worker; SQL identity обоих callers,
OID/address/postmaster start и полный fingerprint сверяются до/после exact CLI.
Старая отдельная `asm_test` отвергается identity assertion. C8-03: canonical private
state boundary и symlink spelling проверяются до любых команд/mkdir/write.
Два исходных дефекта воспроизведены failing regressions; локально38 unit cases PASS.
Real Docker E05 и полные final-head scripts/clean gates обязательны; фактические
head/tree/tested SHA, CI и artifact receipts фиксируются в том же PR24 без SHA-only
commits. Procedure/assertions/ограничения — runbook§0.6.7. Старый §0.6.4 исторический.
Новых dependencies/migrations/pins нет; E02–E04 и frozen source bytes сохранены.
Первый correction CI37288745538 прошёл шесть transport cases и остановил E05 setup:
PostgreSQL inet::text вернул host address с /32. Narrow fixture parser теперь принимает
этот фактический формат, требуя private IP и полную host mask; exact SQL identity
comparison сохранён. Это test defect, не повод менять application/тайм-ауты/assertions.

Пока **не выполнены** owner deployment подготовленного route, external connection discovery,
atomic billing/binding, webhook и реальный Client text+photo → Console/private image →
manual reply → Client receipt. ENV04 требует real Docker/PG boundary evidence,
полного CI и независимого scoped C8 до инструкции владельцу по deployment. GetMe
не доказывает Business rights или окно ответа. Не повторять provisioning/secret entry.

После ENV04 приёмки C0 выдаёт следующий один operator шаг и сохраняет exact IDs/dates
при setup recovery. До первого setup проверить актуальность конечного TEST billing
interval; после попытки его молча не менять. M2 VERIFIED — только после оставшихся
live критериев, merge владельцем и отдельного actual main CI. PR24 пока Draft, merge
не выполнять. Старые задания ниже — история.

Host ограничения неизменны: boot auto_delete=true, backup/restore PASS отсутствует,
delete/reset/down-v запрещены. Принятый бюджет4735,81₽/30суток и review2026-11-01 не
являются spending cap. Новые платные ресурсы и production/M3 не выдаются.


</details>

<details>
<summary>История — выдача первых live шагов / 2026-10-02</summary>

## Исторический статус — TEST host интегрирован; live A09/A11 / 2026-10-02

**M2-ENV-03-TEST-HOST — INTEGRATED / VERIFIED в принятом pre-live TEST scope.**
Владелец слил [PR23](https://github.com/Elefesys/ai-service-manager/pull/23), actual
main **22993f558c5e7e933c65e9c999933bd2e3ab41c4**, tree
**c30415b48a08dabac6a59f1294843a0bd25ff353**. Ordered parents:
**80e51c43e31541940f1ccf18b8281adf1a061748** +
**902e9f1d51235f1441ce4378a4d3a909adefea74**. Tree совпадает с принятым PR tree.
[Push/main CI37016012805, attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/37016012805)
**SUCCESS**: оба job checkout actual merge;492 unit/390 PostgreSQL-S3/111 frontend/
27 browser, оба scripts и clean-source gates PASS. Scoped C8-M2-ENV-03-HOST реально
выполнен и PASS до merge; новых bytes для повторного того же review нет.

Единственная следующая задача **M2-LIVE-A09-A11 — IN_PROGRESS**, C6 с участием C3,
ветка **c6/m2-telegram-live → main**, Draft PR receipt содержит точные coordination
head/tree/CI. Accepted task base — actual main22993f558c5e7e933c65e9c999933bd2e3ab41c4.
Сохраняется существующий host checkout/runtime **80e51c43e31541940f1ccf18b8281adf1a061748**,
tree **88ed308b4c56114aa977dcf91204964d9b7348e5**: Git comparison до нового main
показал только три docs. Runtime нельзя ошибочно называть22993f5; fetch/redeploy/
новый deploy key ради docs не нужны. App/pins/CI/assertions/миграции не меняются.

Первый выданный оператору шаг — [runbook §0.5.1](runbooks/M2_TELEGRAM_LOCAL_TEST.md#051-первый-шаг--владелец-console-без-telegram):
однократная сборка существующего telegram-operator target и fresh Console Owner/
Workspace/Business через неизменённый provision_local_auth.py. Скрытый terminal
password; вернуть только три UUID и CONSOLE_OWNER_PROVISIONED_PASS. TG остаётся
false, secrets/billing/binding/webhook/sends пока не создаются. Фактическое исполнение
этого шага ещё не подтверждено; static C6/C0 review не является host или C8 evidence.

Конечный остаток: Console identity/login → независимо подтверждённые Telegram
Owner/bot IDs → private secrets/официальное подключение → discovery и сохранённый
external connection ID → atomic setup/webhook → Client text+photo → Console/private
image → один ручной ответ → фактическое получение Client. Полное ограниченное
поручение — единственный активный M2_HANDOFF; оператор получает шаги последовательно.
UNKNOWN не resend, потерянный setup ACK не означает rollback. C8 назначается по
конкретному новому риску/изменению, не для повторного аудита неизменённых частей.

Host ограничения сохранены: **boot auto_delete=true**, отдельной VM protection нет;
удаление VM удалит DB/files. Текущий synthetic TEST принят с этим явным риском,
без объявления backup/restore PASS и без разрешения delete/reset/down-v. IP protection
отдельно подтверждён. Бюджет4735,81₽/30суток, контроль2026-11-01, не spending cap;
snapshot schedule INACTIVE, прежние snapshots отдельно не проверены. Production
managed DB/storage/restore решения сохраняются. Подробный host receipt — §0.4.9.

**M2 IN_PROGRESS; live A09/A11 ещё не PASS.** M1/M2 code LOCAL/TEST не переделывать;
M3 не выдан. Секреты не присылать в чат/PR. Новых платных ресурсов не требуется.

</details>

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
| M2.3 | Telegram adapter, test connection, capabilities, UNKNOWN и owner API | VERIFIED M2.1/M2.2 | C3; C1/C2/C6; C0/C8 | INTEGRATED | PR #20 merged, main ffc437f125aa6af4dcf1c61a035a0d5df517e062; push/main 35649907678 SUCCESS; code/API VERIFIED LOCAL/TEST | Code/UI уже интегрированы; фактический live A09/A11 остаётся отдельным gate в M2-LIVE-A09-A11 |
| M2.3-TELEGRAM-API | Official Telegram → durable kernel/private images → five owner API routes | M2_CONTRACT §10 | C3; C2/C1/C6; C0/C8 | VERIFIED | Accepted main ffc437f125aa6af4dcf1c61a035a0d5df517e062; code/API LOCAL/TEST, C8-M2.3-01 CLOSED; actual main CI SUCCESS | Сохранять API/0007/time guards/UNKNOWN; live evidence отдельно |
| M2.4 | Console Inbox, manual reply и E2E | Интегрированный API M2.3 + main CI | C5; C3/C6; C0/C8 | INTEGRATED | PR21 merged; main96d9f09dd16d8b6ab019ac76a9c72ce910d81191; push/main35706123814 SUCCESS; code/UI VERIFIED LOCAL/TEST | Реальный A11 остаётся внешним gate M2-LIVE-A09-A11 |
| M2.4-CONSOLE | Owner panel + private image + exact manual intention/recovery + browser | M2_CONTRACT §§10–11 | C5; C3/C6 TEST harness; C0/C8 | VERIFIED | Actual main96d9f09dd16d8b6ab019ac76a9c72ce910d81191, separate main CI SUCCESS; C8-M2.4-01/02/03 CLOSED, code/UI LOCAL/TEST | Сохранять принятые механизмы; это не live Telegram acceptance |
| M2-LIVE-A09-A11 | Реальная ручная Telegram переписка | Accepted base22993f5; VERIFIED TEST host; ENV04 | C6/C3; C0 acceptance | IN_PROGRESS | Console/secret staging и actual single getMe через temporary relay PASS2026-10-05; runtime disabled; discovery/binding/webhook/переписка ещё не исполнены | Сначала M2-ENV-04, затем последовательные operator шаги; не повторять provisioning |
| M2-ENV-01-REGISTRY | Восстановить storage provisioning и полный CI | M2.4; pull failure PR22 | C6; C0/C8 | VERIFIED | PR22 merged80e51c4; scoped C8 PASS; отдельный push/main36825583134 SUCCESS, оба scripts/source gates и реальные PG/S3/browser | Сохранять проверенные GHCR pins; registry blocker CLOSED |
| M2-ENV-02-STORAGE-IMAGES | Два exact official binary в project-owned images | Решение C0 о новой упаковке | C6; C0/C8 | VERIFIED | Build36734267078; anonymous full OCI bytes; scoped C8; final PR36824246755 и actual main36825583134 SUCCESS | Не пересобирать и не менять visibility/pins без причины |
| M2-ENV-03-TEST-HOST | Один TEST host/.com DNS/HTTPS до Telegram connection | Actual main80e51c4 + host evidence | C6; C0; independent C8 | VERIFIED | PR23 merged22993f5; main37016012805 SUCCESS; C8-HOST PASS; operator host/HTTPS/private403/renewal receipt; известные TEST ограничения сохранены | Закрыто только pre-live host; продолжить M2-LIVE-A09-A11 |
| M2-ENV-04-TELEGRAM-EGRESS | Opt-in постоянный synthetic TEST route для Telegram callers | ENV03; prior C8-01–03 CLOSED; actual partial VM deployment | C6: M2-ENV-04-RECOVERY-RESUME | REVIEW | C8-04/05 P2/E05: disable-first retry и stopped/missing relay interruption; mapping/CI evidence сохранено, runbook§0.6.13 | Bounded correction → final-head three-job CI → targeted C8 → отдельный C0 owner step; live A09/A11/merge/main CI впереди |

Таблица M0 перечисляет фактического исполнителя C0, а не подразумевает отдельно запущенных C1–C8. Review M0 был C0 self/second-pass; M1.1 имеет отдельные отчёты C8. Назначения областей остаются в AGENTS/Implementation Plan.

## История — прежние решения и evidence

Всё ниже — записи прежних snapshots. Их статусы и команды не переопределяют
текущий блок, таблицу выше и M2_HANDOFF. Не выполнять старые поручения повторно.


<details>
<summary>История — host receipt до merge PR23 / 2026-10-02</summary>

## Исторический статус — TEST host исполнен, приёмка PR #23 / 2026-10-02

**M2-ENV-03-TEST-HOST — REVIEW.** Владелец фактически подготовил один принятый
Yandex TEST host, DNS, trusted HTTPS и renewal; Telegram остаётся выключенным без
TG secrets. C0 проверил его очищенные выводы и screenshots. Это operator evidence,
не заявление о прямом SSH/cloud доступе агента. Полный receipt, границы и исправления
процедуры — [runbook §0.4.9](runbooks/M2_TELEGRAM_LOCAL_TEST.md#049-фактическое-исполнение-и-решения-c0--2026-10-02).

Единственный [PR #23](https://github.com/Elefesys/ai-service-manager/pull/23), ветка
**c6/m2-test-host → main**; сохранён первый coordination
**1f42a617ed64bc6fd4dd573cd5c721d22a7bf256**. Accepted main/runtime
**80e51c43e31541940f1ccf18b8281adf1a061748**, tree
**88ed308b4c56114aa977dcf91204964d9b7348e5**; source на VM повторно clean после renewal.
[Push/main CI36825583134](https://github.com/Elefesys/ai-service-manager/actions/runs/36825583134)
SUCCESS на принятом runtime. M2-ENV-01/02 закрыты; public GHCR refs сохранены.
PR23 меняет только этот реестр, активный M2_HANDOFF и прежний TEST runbook.
App/Compose/pins/workflows/tests/contracts/миграции0001–0007 не меняются.
Итоговый C8 и CI **последнего** documentation head записываются в PR receipt;
до их PASS PR остаётся Draft, merge самостоятельно не выполнять.

Фактические результаты: migrate/storage-init exit0, private bootstrap PASS,
все семь сервисов running/OOM=false, TG-disabled webhook503/no-store, unknown webhook404;
HTTPS health200, точные SAN/доверенная цепочка/unknown-SNI rejection, anonymous bucket403;
Certbot dry-run/deploy reload и повторный HTTPS PASS. Из сети владельца доступны22/443,
5432/8000/8080/9000/9001 недоступны; sole SG разрешает22 только31.135.48.89/32.
Browser login page виден с trusted TLS. Authenticated Console, signed image и live
Telegram этим **не проверены**; deny22 с другого IP отдельно не исполнялся.

Явное решение C0: у существующей VM **boot auto_delete=true**, защиты удаления
отдельной Compute Instance в проверенных интерфейсах нет. Прежние инструкции C0/C6
об этих переключателях были ошибочны. Безопасного изменения boot flag на месте не
подтверждено; пересоздавать рабочий TEST host ради этого нельзя. Для данного
синтетического TEST это известное ограничение, не disk-protection PASS и не backup.
При удалении VM её DB/files потеряются; никакое удаление VM/диска/volumes сейчас не
разрешено. Будущая замена требует отдельного плана сохранения и сверки durable state;
после потери state не включать sends до reconciliation. IP deletion protection
подтверждён отдельно. Production managed storage/backup/restore решения не изменены.

VM создана **2026-10-02T04:57:26Z**, one standard-v3/2vCPU100%/8GiB/60GiB network-ssd,
ru-central1-a, Ubuntu24.04 amd64, static89.169.141.53. Оценка в Console
**4735,81 ₽/30 суток**, ранее принятый бюджет. Контроль дальнейших расходов —
**2026-11-01**; это дата решения, не настроенный spending cap или auto-delete.
IP зарезервирован раньше VM; фактический счёт может отличаться от оценки30суток.
Snapshot schedule INACTIVE по owner receipt; наличие/стоимость прежних snapshots
отдельно не проверены. Платные дополнения не подключались в этом продолжении.

**Весь M2 IN_PROGRESS.** Инфраструктурная причина отсутствия DNS/TLS устранена,
но live A09/A11 ещё **BLOCKED приёмкой/интеграцией host и неисполненным подключением**.
Конечный остаток: C8/final-head CI PR23 → обычный merge владельцем → actual main CI
→ одно ограниченное C3/C6 live поручение → Client text+image → Owner Console/private
image → manual reply → подтверждение Client. Сейчас TG secrets, Owner/billing,
binding/setWebhook/sends не создавать. M1/M2.1–M2.4 code не переделывать; M3 не выдан.

</details>

<details>
<summary>История — подготовленная процедура до исполнения host / 2026-10-01</summary>

## Исторический статус — PR #22 интегрирован; следующий шаг C6 TEST host / 2026-10-01

**M2-ENV-01-REGISTRY и M2-ENV-02-STORAGE-IMAGES — VERIFIED после интеграции.**
Пользователь слил [PR #22](https://github.com/Elefesys/ai-service-manager/pull/22)
обычным merge commit **80e51c43e31541940f1ccf18b8281adf1a061748**,
tree **88ed308b4c56114aa977dcf91204964d9b7348e5**. Ordered parents:
**96d9f09dd16d8b6ab019ac76a9c72ce910d81191** +
**925952086b8ec83f2648b84094f546ec458cfde4**. Tree совпадает с принятым final PR tree.
[Отдельный push/main CI36825583134, attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/36825583134)
**SUCCESS** на этом actual merge: foundation110250425002 и browser110250424676
checkout именно 80e51c4; 492 unit,390 PostgreSQL/S3,111 frontend,27 browser PASS.
Оба штатных scripts, clean-source gates, canonical/migrations/contracts/
reproducibility/HTTP smoke PASS. Независимый scoped C8 packaging/pins уже PASS;
actual merge не меняет проверенные bytes и не требует повторного того же review.
Public GHCR refs и vendor releases сохранены; недоступные Quay artifacts не возвращать.

**Следующая единственная задача — M2-ENV-03-TEST-HOST, C6, IN_PROGRESS (подготовка).**
Repository Elefesys/ai-service-manager, отдельная ветка **c6/m2-test-host → main**,
accepted base — actual main **80e51c43e31541940f1ccf18b8281adf1a061748**.
Точный coordination head и Draft PR указываются в PR receipt, без SHA-only commits.
Scope: один ранее согласованный Yandex RU TEST host, SSH/network, два .com DNS имени,
бесплатный TLS/renewal и готовность существующего Compose при **Telegram disabled**.
Разрешены только TASK_REGISTER, активный M2_HANDOFF и существующий TEST runbook;
cloud/host настройки исполняются по точной процедуре C6, когда есть доступ владельца.
App/Compose/pins/workflows/tests/миграции не меняются. Полное поручение и критерии —
в единственном [активном handoff](tasks/M2_HANDOFF.md); команды — в одном
[runbook](runbooks/M2_TELEGRAM_LOCAL_TEST.md). Это продолжение подготовки A09/A11,
не новая продуктовая часть или production rollout.

Public DNS проверен 2026-10-01 через Google DNS-over-HTTPS: .com NS — четыре Timeweb
servers; A для console.telegram-test.clientmanagerai.com и
files.telegram-test.clientmanagerai.com ещё NXDOMAIN. .ru NS — NXDOMAIN у этого
resolver; это не вывод о внутреннем статусе ЕСИА/регистратора. Для .com smoke ждать
.ru не нужно. **2026-10-01 владелец подтвердил: billing активен, каталог
asm-telegram-test создан.** Это owner receipt; агент не входил в его аккаунт.
VM/DNS records/TLS/SSH пока не созданы и не проверены. C6 подготовил единый порядок
настройки в runbook §0.4: локальный SSH key → ограниченная сеть/одна VM → точный
source → DNS/TLS → pre-live readiness. Публичный IP VM и результаты возвращаются после
фактического исполнения; ключи/токены и платёжные данные в чат и PR не передавать.

**C8-M2-ENV-03-PROCEDURE — независимый scoped PASS** для точных команд runbook;
C0 принял ограниченные исправления environment precedence и HTTPS/TLS probes.
11 Bash blocks/hook и 6 Python heredocs syntax PASS, PowerShell static review.
Actual Yandex/Windows/VM/DNS/TLS execution не заявляется; процедура не закрывает
приёмку host или живой A09/A11. Hash/scope — активный handoff; итоговый CI — PR receipt.

Бюджет **4735,81 ₽/30 суток runtime** сохранён; cloud rates перепроверены 2026-10-01.
Одна VM standard-v3/2vCPU100%/8GiB/60GiB network-ssd/staticIPv4, ru-central1-a,
Ubuntu24.04 amd64. Покупка доменов повторно не требуется. Bot/Owner/Client и два
Telegram секрета уже подготовлены. TG включается только следующим live шагом после
приёмки стенда; внешние отправки сейчас не выполнялись.

Весь **M2 IN_PROGRESS**; live A09/A11 **BLOCKED внешним runtime/DNS/TLS**.
M1 и M2.1–M2.4 code LOCAL/TEST не выполнять заново; M3 не выдан. Конечный остаток:
готовый TEST host → C3/C6 connection/rights → реальный Client text+photo → правильный
Workspace/Owner Console/private image → ручной ответ → подтверждённое получение Client.

</details>

<details>
<summary>История — приёмка PR #22 до actual merge / 2026-10-01</summary>

## Исторический статус — storage registry восстановлен в PR; приёмка до merge / 2026-10-01

**M2-ENV-01-REGISTRY и M2-ENV-02-STORAGE-IMAGES — REVIEW, приняты C0 и независимым
scoped C8 в LOCAL/TEST scope.** [обычный CI 36823298856, attempt 1](https://github.com/Elefesys/ai-service-manager/actions/runs/36823298856) SUCCESS после переключения двух storage pins:
492 unit, 390 PostgreSQL/S3, 111 frontend, 27 browser; оба штатных scripts и оба
clean-source gates PASS. Это результат ветки PR; интеграция в main ещё впереди.
Весь **M2 IN_PROGRESS**. M2.4 code/UI VERIFIED только LOCAL/TEST; live A09/A11
**BLOCKED: runtime/DNS/TLS**. M3 не выдан; M1 и M2.1–M2.4 повторно не выполнять.

Единственный [PR #22](https://github.com/Elefesys/ai-service-manager/pull/22), ветка **c6/m2-live-smoke → main**. Actual accepted main остаётся
**96d9f09dd16d8b6ab019ac76a9c72ce910d81191**, tree
**28de72ca6737cbe18bb4856a1636f70fae1131ee**; исторический push/main CI35706123814
SUCCESS. Первый coordination **914e2894f98330d62e1cc57ca5da5c62662d6960** сохранён.
Проверенный implementation head **809d44c77b45d86b54750969db5b4a3ec411e0e3**, tree **42a17e82cae204a1f4a8d3f3bc3dcd798fc03cc8**.
Последующее согласованное изменение только трёх документов фиксирует эту приёмку.
Exact final head/tree/tested checkout и CI после последнего изменения — в receipt
PR #22. **Merge допускается только при SUCCESS CI именно актуального head.**
SHA собственного документационного коммита в документах не дублируется.

Владелец открыл два packages Public 2026-10-01. C6 полностью скачал manifest,
config и все layers без пользовательских credentials/cache: 95 747 170 bytes,
exact hashes/sizes/diffIDs и семь добавленных файлов каждого образа совпали с
подписанными vendor inputs и build/publish receipt. C0 и C8 независимо пересчитали
сохранённые bytes. Это anonymous OCI download; реальный Docker pull/runtime
подтверждён отдельно обычным CI на свежих hosted runners. C0 явно согласовал такой
порядок из-за отсутствия локального Docker; обязательный runtime gate сохранён.
Receipt SHA-256 **07992f7085ad9826503870ed0984ad469ebbe9d761fb13134ae553f5c1eba211**.

Образы из build source **f74c240febd963c79408e80600c29d7739e08867** не пересобирались:
MinIO RELEASE.2025-09-07T16-13-09Z и mc RELEASE.2025-02-15T10-36-16Z сохранены.
Новые OCI artifacts явно приняты вместо недоступных старых Quay artifacts;
byte identity со старыми images не заявляется. Изменены только девять разрешённых
paths: четыре packaging файла, две storage refs/pins и три документа. Приложение,
миграции 0001–0007, основной CI, Compose/bootstrap, tests/assertions и прочие pins
сохранены. Состав, exact refs и concrete assertions — в единственном активном
[M2_HANDOFF](tasks/M2_HANDOFF.md) и [runbook §0.3](runbooks/M2_TELEGRAM_LOCAL_TEST.md#03-принятые-storage-artifacts-и-воспроизведение--2026-10-01).

Следующий шаг: пользователь выполняет **обычный merge commit PR #22** после
подтверждения C0 final-head CI; C0 проверяет actual merge и отдельный push/main CI.
Затем выдаётся ограниченное продолжение M2-LIVE-A09-A11: принятый Yandex RU TEST host,
**console.telegram-test.clientmanagerai.com** и **files.telegram-test.clientmanagerai.com**,
DNS/TLS и Client text+photo → Console/private image → manual reply → получение Client.
Бюджет **4735,81 ₽/30 суток runtime** и **1760 ₽ за первый год пары доменов** принят;
платная VM ещё не создана. .com зарегистрирован по сообщению владельца/Timeweb,
.ru ждёт проверки администратора; публичная DNS/TLS-готовность пока не проверена.
.ru остаётся предпочтительным будущим основным доменом. Bot/Owner/Client и два
Telegram секрета подготовлены; повторный ввод в чат/PR не нужен.

</details>

<details>
<summary>История — private artifacts и public access gate до 2026-10-01</summary>

## Исторический статус — private storage artifacts готовы; public access gate / 2026-09-30

**M2.4-CONSOLE INTEGRATED / VERIFIED только в LOCAL/TEST code/UI scope.**
M2.4 — INTEGRATED с оставшимся live E2E; M2.3 live-проверка также не закрыта.
Весь M2 **IN_PROGRESS**. A09/A11 внешнего Telegram **BLOCKED: runtime/DNS/TLS**.
M3 не выдан; M1 и принятые M2.1–M2.3 code/API receipts сохранены.

[PR #21](https://github.com/Elefesys/ai-service-manager/pull/21) фактически merged.
Actual main / base следующей задачи **96d9f09dd16d8b6ab019ac76a9c72ce910d81191**,
tree **28de72ca6737cbe18bb4856a1636f70fae1131ee**. Ordered parents:
**ffc437f125aa6af4dcf1c61a035a0d5df517e062** +
**770e7db905732b3ed2a25a1d9a2c31bcd89a161b**; tree равен принятому final PR tree.
Первый coordination сохранён. C8-M2.4-01/02/03 CLOSED, независимый scoped/targeted
PASS из pre-merge receipt относится к тем же implementation bytes.

Отдельный [push/main CI35706123814, attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/35706123814)
**SUCCESS**: foundation106675369660 и browser106675369293. C0 прочитал оба checkout
logs: исполнен именно actual merge SHA выше, не виртуальный PR merge.
**492 unit,390 PostgreSQL/S3,111 frontend,27 browser PASS**; оба штатных scripts и
clean-source gates, canonical/migrations/contracts/reproducibility/smoke PASS.
Все213 исходных blobs/modes соответствуют принятому дереву; ZIP bytes не проверены.

Ближайшая выданная задача — **M2-ENV-02-STORAGE-IMAGES**, C6; приёмка C0 и новый
scoped C8. Статус **IN_PROGRESS**. Это ограниченная упаковка exact official MinIO/mc
binaries для устранения **M2-ENV-01-REGISTRY**, который пока **BLOCKED**.
Существующие **c6/m2-live-smoke / Draft PR #22** продолжаются; первый coordination
**914e2894f98330d62e1cc57ca5da5c62662d6960** и вся история сохраняются.
Один активный [M2_HANDOFF](tasks/M2_HANDOFF.md) содержит точный scope девяти paths.

**Решение C0 2026-09-30:** диагностика C6 принята. Прежнее условие восстановления
только identical OCI bytes явно заменено разрешением новой упаковки двух exact
release binaries; MinIO/mc releases и application contracts сохраняются. C0 сверил
binary hashes/sizes с official release API; полный download/hash — evidence C6.
Новые OCI bytes не объявляются идентичными недоступным старым; их приёмка новая.
Два Dockerfile, input lock и отдельный build/verify/publish workflow разрешены.
Основной CI/Compose/bootstrap/application/tests неизменны, исключение для lock —
только две storage refs/pins. Новая упаковка реализована и проверена на runner;
C0/C8 acceptance и anonymous public pull/final CI ещё не завершены.

C0 проверил [final CI C6 36717840363, attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/36717840363):
оба jobs FAILURE при MinIO pull; checkout **349b84b9a942d21e0d4db92f84b2cd2e15d21b20**,
ordered parents accepted main + **6159a64cfb08c853dac4ff51c415e32c083e735f**,
tree **bf1ae81a65c7b1695a6f413f92a2c0cd49399593** совпадает с head tree.
Canonical/frontend111/Compose PASS; PostgreSQL/S3/browser/UNKNOWN не исполнились;
оба clean-source gates SKIPPED. Полный CI не восстановлен. Quay/Hub anonymous grant
отсутствует, mirror404 — evidence C6; policy причина не установлена. История
диагностики и исходные hashes/refs сохранены свёрнуто в handoff.

**Результат C6:** [Storage CI36734267078, attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/36734267078)
SUCCESS; tested source **f74c240febd963c79408e80600c29d7739e08867**, tree
**3e742d07440bcd2e4516922d5698ed1aee735db0**. Две независимые no-cache сборки,
полные binary hashes/minisig/tamper negative, config/layers/полные archives,
in-image hashes/CA/shell/private policy/volume restart PASS. На новых local images
неизменный ci.sh: **492 unit,390 real PostgreSQL/S3,111 frontend PASS** и source
gate PASS. Browser/оба обычных gates и anonymous pull пока не подтверждены.

Оба final packages опубликованы **private**:
[asm-minio](https://github.com/users/Elefesys/packages/container/package/asm-minio),
ID15482993, manifest sha256:c6c3b418f4b7bbea2f07c4095fc6e59d38ed538a33486f19bb9450a63a6a2efa;
[asm-mc](https://github.com/users/Elefesys/packages/container/package/asm-mc),
ID15484077, manifest sha256:4da81d17279b9fcdaeee8967c0de4f5d9c7fd589f8022b66e2766b9ac4fe5ce4.
Exact inputs/config/archive/registry binding, receipt ZIP hashes и конкретные
assertions приведены в активном handoff. Только publish job имеет временный
GITHUB_TOKEN packages:write; private source/app/docs/env/secrets в images не входят.
Publisher учитывает фактический API: repository metadata отсутствует; identity
закреплена проверенными package IDs, exact name/type/owner и source label.
Это исправление нового guard, а не основание требовать PAT/Connect repository.

**Следующий внешний шаг:** C0 проверяет состав и организует владельцу public
visibility двух готовых packages; private repository не открывать. C6 эту операцию
не выполнял. До fresh anonymous pull storage pins/refs сохранены без изменений.
Обычный CI36734280555 на том же source остаётся FAILURE на старом Quay unauthorized;
PG/S3/browser в нём не дошли до исполнения, оба gates SKIPPED. Полный registry
recovery не объявлен. Семь разрешённых paths изменены; остальные inputs и assertions
сохранены. Final documentation head/tree ведутся в PR22 receipt без SHA-only commit.

Конечный gate: оба public immutable refs скачаны без credentials/cache, прежние
scripts и source gates полностью SUCCESS на итоговом head, реальные S3/PG/browser
и UNKNOWN/no-resend исполнены, новый scoped C8 фактически выполнен. До этого
PR Draft, merge запрещён. Head/tree/CI coordination ведутся в PR receipt; не создавать
коммит только ради SHA предыдущего документационного коммита.

**Решение владельца 2026-09-30:** внешний smoke проводить на **.com**, когда его
работоспособность подтверждена. Плановые адреса:
`console.telegram-test.clientmanagerai.com` и `files.telegram-test.clientmanagerai.com`.
Это явное изменение прежнего плана smoke на .ru; .ru остаётся предпочтительным
основным доменом будущего продукта. Вторую Console, общий cookie domain или второй
регион не вводим. Перенос на .ru после smoke не выполняется автоматически.

По сообщению владельца и процитированному ответу Timeweb: **clientmanagerai.com
зарегистрирован, NS Timeweb установлены**; публичная DNS/HTTPS-работоспособность C0
не проверена. **clientmanagerai.ru ожидает проверки администратора/ЕСИА**. Это
сообщённый статус провайдера, не independent registry/DNS evidence. Личные данные,
логины, переписка с паспортными данными и secrets в репозиторий не переносятся.
Повторная регистрация/покупка пары не требуется; владелец продолжает существующий тикет.

Бюджет и Yandex RU test host приняты: ориентир **4735,81 ₽/30 суток runtime**,
**1760 ₽ первый год пары**, итого **6495,81 ₽**, по расчёту/корзине 24–27 сентября.
Точные условия сохранены в [runbook §0.1](runbooks/M2_TELEGRAM_LOCAL_TEST.md#01-предложение-стенда-с-нуля--2026-09-24).
Повторного согласования того же бюджета не нужно. **До восстановления CI платную VM
не создавать.** Текущая задача C6 не включает ресурсы/аккаунты/DNS/TLS/webhook/live sends.
Bot/Owner/Client и два Telegram секрета уже подготовлены. LOCAL Compose/MinIO/asm_local
и принятый production managed PostgreSQL/private storage ADR сохраняются.

Live DoD: Client text+photo → правильный Workspace/Owner Console/private image →
ручной ответ → реальное получение Client, плюс фактические connection/rights A09.
CONTROLLED и SENT это не заменяют. Реальных Telegram sends или настройки внешней
инфраструктуры в данном coordination update не выполнялось.

</details>

## История — M2.4-CONSOLE принята C0/C8; ожидает merge / 2026-09-22

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

</details>

</details>

</details>

</details>
