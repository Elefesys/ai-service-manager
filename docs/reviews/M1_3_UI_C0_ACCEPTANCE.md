# C0 — M1.3 owner UI slice acceptance

Дата: 2026-09-20. Единственный реестр — [TASK_REGISTER](../TASK_REGISTER.md);
единственный активный handoff — верхний [M1_HANDOFF](../tasks/M1_HANDOFF.md).
Это evidence приёмки UI PR #15, не второй реестр и не завершение milestone.

## Verdict и scope

**C0 full-PR review PASS. Targeted C8 UI-01 PASS. UI готов к обычному merge commit
при SUCCESS CI итогового опубликованного head.** UI пока REVIEW; PR #15 Draft /
open / not merged. DB/API сохраняют INTEGRATED / VERIFIED. M1.3 IN_PROGRESS,
M2 не выдан. После ручного merge обязательны actual merge/tree и отдельный main CI.

Проверены принятые R4/D-01…D-13, конечное поручение C5, актуальные Spec §§15–17,
ADR-002/005/006/064/099…109/126/182, MVP/Roadmap/Implementation Plan. R4 SHA-256
`0d33a26aa13fb3eda34b0a5c07a4a11dc263b1ee37ce9e3fda126f53e0c0282a` неизменен.
11/11 приложенных архитектурных оригиналов побайтно совпадают с GitHub snapshot.
Новые требования или пересмотр ранее принятых механизмов не вводились.

Разрешённая implementation delta: billing adapter/panel/state/styles и tests в
frontend, billing browser journeys/safe diagnostics, конечные TEST fixtures и
минимальное Compose/script wiring, runbook и coordination docs. R4, backend,
миграции/grants, generated contracts, auth/tenancy contracts, dependencies/locks,
images/workflow и прежний auth.spec.ts неизменны. Runtime использует принятый API;
только provisioning/test verification работает с asm_migrator в disposable TEST.
Rate capacity300/1000/100 применяется только в ранее разрешённом browser overlay.

## Проверенные snapshots

- Accepted implementation base/main: `43f22b5e28a93e269eccc25bf73653e47fd01426`,
  tree `a6051034784d30e1ecb4af4c28caf4a596dafdab`, main CI 35508232378 SUCCESS.
- Первый coordination commit `2274667f06ddd72b1a02c57fb555456e948f2c50` сохранён.
- C5 implementation head `398dc723fed339f8a3e660a114fb231e924c8e31`, tree
  `cf9d8fdedbb2d9ee107262f5a8889d32947beeb9`;
  [CI 35510912219](https://github.com/Elefesys/ai-service-manager/actions/runs/35510912219)
  attempt1 SUCCESS: 411 cases, оба clean-source gates PASS. Tested virtual merge
  `7a2c00ca4bb38850fc08fa690bc2345858987389` имеет parents accepted base + C5 head
  и точно тот же tree. Foundation job106078545137, browser106078545081.
  Artifact10605596595 ZIP SHA-256
  `9674fbc64ca8b74b88d1bf75b25839ae4f88c614a4a21f341da8a4c577d8e90a`.
  В отличие от ограничения загрузки в C5 report, C0 скачал ZIP и независимо
  подтвердил digest, exact tested SHA, пустой worktree, reconstructed Git tree
  и canonical originals. Первоначальный отчёт C5 не исправляется задним числом.
- C0 fix `7630032d29dc3f79f48a9089b60492b2520384c5`, parent C5 head, tree
  `203fdd8c7da809a17866df8feb77dbfa90218139`;
  [CI 35511904393](https://github.com/Elefesys/ai-service-manager/actions/runs/35511904393)
  attempt1 SUCCESS: 415 cases, оба clean-source gates PASS.
  Tested virtual merge `682b5418bfcec45389ba77b90540ee4786b3ee42` имеет parents
  accepted base + fix head и тот же tree (GitHub Git objects и оба checkout logs).
  Foundation job106081147536, browser106081147435. GitHub artifact10605597903
  reports ZIP SHA-256
  `35372e3b2b30df08f8a1872a76603349393e5515fca59d301fc04a7977e51299`;
  для этого промежуточного архива отдельная локальная распаковка не заявляется.
- Последующее согласованное docs-only изменение фиксирует review. Его final
  head/tree/tested SHA и успешный CI публикуются в PR #15 и финальном ответе C0
  после проверки. Нельзя считать CI fix-head проверкой будущего docs-head;
  самоссылочного SHA-only follow-up commit не требуется.

## C8-M1.3-UI-01 — P2, CLOSED

Исходная цепочка: ambiguous PATCH → auth recovery очищает view → тот же body/key
получает STALE_STATE → intent удаляется, но исходный draft не переносится в view.
Пользователь видел пустой draft. Отдельно STALE_STATE → GET503 → retry GET заменял
draft текущим серверным contact. Это нарушение принятого recovery, не новый scope.

C0 воспроизвёл три RED cases на неизменённом component. Ограниченный fix только
`frontend/src/BillingPanel.tsx` и `BillingPanel.c0-review.test.tsx`: отдельный
memory-only draft с actor/Workspace, восстановление исходного frozen body при
STALE_STATE, сохранение edits при retry GET/same-actor auth recovery, очистка при
смене actor/Workspace/live403 и новом явном Save. Pending replay сохраняет прежние
body/key/version; новый Save после stale использует fresh GET version и новый key.

После fix четыре regression cases PASS, оба focused suites20tests и typecheck PASS.
Независимый targeted C8 подтвердил exact fix head/tree, те же команды20tests и
отсутствие оставшихся findings в дельте. Очистка retained draft при live403 проверена
по source; существующий component403 case доказывает скрытие protected UI. C8 не
запускал локальный Docker/PostgreSQL и не принимал весь PR/milestone этим verdict.

## Проверяемая UI-матрица

Это новая матрица **UI-A01…18** по выданному C5 scope, не историческая матрица1–48.
История отсутствующего оригинала и DB-A01…32 сохранена в DB receipt; требований
из будущих этапов здесь нет. Ниже перечислены конкретные tests/assertions,
исполненные в successful fix CI (после docs update необходим отдельный final CI).

| ID | Принятый критерий | Конкретная проверка / assertion | Evidence |
|---|---|---|---|
| UI-A01 | Один OWNER panel, прежние Console/Business/Ops | App wiring; BillingPanel tests `hides owner UI…`, `keeps Business…Ops`; auth.spec.ts неизменён | C0 source; component; real browser regression |
| UI-A02 | Серверные states/entitlements и limit0, mode независим | `renders server zero…`; browser `@narrow owner…`, три `real … state preserves…` проверяют API state, UI и разрешённый contact/Business | Component + real API/PG browser |
| UI-A03 | Structural503 не inactive и не logout | `keeps structural503…`, `keeps Business…billing503`; strict disjoint error unions | Component/adapter; structural browser outage не заявляется |
| UI-A04 | Exact DTO/UUID/bigint/timestamps | billing-api.test `preserves zero,max…`, `rejects extra/missing…`, `enforces tagged decisions…`; adapter сохраняет strings/microseconds | Adapter + source |
| UI-A05 | U+0020 trim/scalars/control/normalization | `implements scalar/padding/byte boundaries…`: padded200emoji,201 reject, NBSP/NFD, U+2028/U+2029, C0/DEL/surrogates | Adapter; runtime API normalization уже принято |
| UI-A06 | Cookie/current CSRF/один key/без If-Match | `passes opaque cursor and frozen PATCH…` exact request; browser real commands/CORS; no persistent secrets | Adapter + real API/browser + source |
| UI-A07 | UPDATE/NOOP и current GET | Component `confirms UPDATED/NOOP…`; browser happy path version+1 then NOOP version/Audit unchanged, receipt+1, reload GET | Component + real PG stats |
| UI-A08 | Duplicate submit/body editing blocked | Component deferred save + три submits дают один вызов/key; input disabled; memory-only frozen body | Component + source |
| UI-A09 | STALE требует явного нового Save | Browser `stale edit from another real session…`:409, server change+1, draft retained, explicit save+2; C0 four regressions на recovery/read failures/actor/Workspace | Real API/PG browser + component |
| UI-A10 | Key conflict не обходится автоматически | `retains stale draft…stops key conflict`: disabled form, no automatic new key; explicit discard честно завершает intention | Component + source |
| UI-A11 | Lost response после commit, same-intent replay | Browser `lost delivery after real commit…`: route.fetch200 → delivery abort; auth recheck; exact body/key equality; +1 version/+1 receipt/+1 contact Audit | Real browser/API/PG; не fake response |
| UI-A12 | Повторная ambiguity/auth/CSRF recovery | `preserves exact body/key across repeated ambiguity…`, full Console401/bootstrap/login/focus; старые logout-intent tests | Component; одиночная delivery-loss цепочка дополнительно browser |
| UI-A13 | PATCH200 + failed GET остаётся confirmed | `PATCH200/GET failure…` повторяет только GET; `preserves command confirmation…loses permission` скрывает данные без ложного rollback | Component + source |
| UI-A14 | Late success/error и actor/Workspace ownership | Parameterized late read/Audit и save tests; C0 draft context tests; generation checks on every completion | Component + source; не все interleavings browser-tested |
| UI-A15 | Live OWNER authority/isolation | Browser `authenticated foreign Workspace denial and live owner downgrade…`: A→B403 всех3routes, B DB stats unchanged, downgrade hides UI; Business200 | Real API/PG browser |
| UI-A16 | Audit metadata/limit10/cursor/end/reset | Adapter rejects contact/extra payload; component paginate/reset; browser real HTTP commands create history, opaque cursor equality, load to null, refresh10, no contact value | Adapter/component + real API/PG browser |
| UI-A17 | Browser CORS и narrow/keyboard | CORS journey: real CDP preflight200+credentialed PATCH, forbidden header preflight400+no extra DB mutation; happy path desktop+narrow Tab/Enter/no overflow | 9 new browser executions; API foreign-origin/method gates уже приняты |
| UI-A18 | Scope, safe fixtures, old gates, reproducibility | Source diff/TEST database-role guards/finite presets/tmpfs/private files/cleanup/safeDiagnostic; unchanged locks/workflow and old assertions; both clean-source gates | C0 source + full CI |

## Исполнение и пределы результата

| Suite | Accepted API base | C5 additions | C0 additions | Final implementation |
|---|---:|---:|---:|---:|
| Backend non-integration | 153 | 0 | 0 | 153 |
| Real PostgreSQL | 189 | 0 | 0 | 189 |
| Frontend | 30 | 24 | 4 | 58 |
| Real browser | 6 | 9 | 0 | 15 |
| Всего | 378 | 33 | 4 | **415** |

Штатные `sh scripts/ci.sh` и `sh scripts/test_browser.sh`: PASS в GitHub runner.
Ruff/format/strict mypy, frontend typecheck/build/reproducibility, canonical source,
generated OpenAPI check, fresh/repeated upgrade и disposable downgrade/re-upgrade,
wheel reproducibility, HTTP/proxy smoke и оба clean-source gates PASS.
Локально C0: Node24.19, locked/offline npm dependencies, meaningful focused regression
и typecheck. Docker отсутствует; локальные real PostgreSQL/browser результаты не заявляются.

Не вводится полная browser-перестановка всех отказов/modes. Component mocks не
считаются PG/browser evidence. Memory-only intention/draft теряются при reload;
после reload только reads, нет придуманного key/automatic write. Тестовые fixtures
и rate capacity не production policy. Нет provider payments, Usage/QuotaReservation,
Jobs/Outbox, catalog/subscription/mode editors, privileged Ops или production readiness.

Конечные действия: пользователь делает обычный merge commit PR #15 после проверки
финального CI; C0 проверяет actual merge и отдельный push/main run, затем принимает
всю M1.3 в согласованном реестре/handoff/receipt. До этого M1.3 IN_PROGRESS, M2 не выдан.
