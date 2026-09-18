# AI Service Manager — единый task register

Ответственный: C0. Канон: v0.28; стек: `docs/decisions/IMPL-001-stack.md`. Это единственный реестр исполнения. LOCKED/OPEN/DEFERRED/REVISED относятся к архитектуре; состояния задач: TODO → IN_PROGRESS → REVIEW → INTEGRATED → VERIFIED, BLOCKED требует причины.

## Текущее решение C0

**M0 — VERIFIED. M1.1 — VERIFIED. Backend-срез M1.2 — INTEGRATED / VERIFIED.** Actual main `aa7e792555c19d798eafa0cae17d29b73ca12376` и его push/main CI подтверждены C0. Полная M1.2 — IN_PROGRESS: UI возвращён C5 на ограниченную доработку по C8 CHANGES_REQUESTED (C8-M1.2-UI-01/02, два P1); прежний успешный UI CI сохранён как evidence, но UI не принят. M1.3 не выдана; полный M1 не принят.

Принятый implementation merge M1.1: `b480d864a246cb0573b40fa5211f66625a71de91`.
Проверенный C2 head: `fa98e714d78485f8d07108294263c89d90a6e7f0`.
Исходный base задачи/M0: `7eaa9aa63b3f27215f6eb970fb9eb857fd291f62`.
Implementation tree: `66b87d3797bff856df449c878347766e147c5c01` (74 файла).

Следующий выданный scope: **M1.2, UI-часть C5 и browser journey** от `aa7e792555c19d798eafa0cae17d29b73ca12376`. Backend принят; повторно его реализовывать не нужно. Backend-only не закрывает всю M1.2. M1.3 по зависимостям допускается после M1.1, но ещё не выдана. Канонические зависимости не пересматриваются.

Финальный стартовый SHA C1 указывается C0 в сопровождающем сообщении после проверки итогового main с этими документами приёмки. Он может быть documentation-only descendant implementation merge выше. Moving main, PR test-merge и старый M0 не заменяют выданный SHA. Ссылка на evidence итоговой документационной интеграции сохраняется также в её PR без бесконечного изменения commit ради записи собственного SHA.

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

## Задачи

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
| M1.2 | Auth/session/membership/login UI | Интегрированный M1.1; принятый backend API | C1+C5 | IN_PROGRESS | Backend VERIFIED: PR #7/main `aa7e792555c19d798eafa0cae17d29b73ca12376`; UI PR #8 CI 35341271140 SUCCESS / 235 tests, C8 CHANGES_REQUESTED: UI-01/02 P1 OPEN | C5 auth-state fix + deterministic regressions → оба CI jobs → targeted C8 → C0 интеграция/приёмка |
| M1.3 | Local Plan/Subscription/Entitlements/Audit | M1.1; защищённый UI использует M1.2 | C1 | TODO | Ещё не выдана | После текущего auth-среза, без paid provider |

Таблица M0 перечисляет фактического исполнителя C0, а не подразумевает отдельно запущенных C1–C8. Review M0 был C0 self/second-pass; M1.1 имеет отдельные отчёты C8. Назначения областей остаются в AGENTS/Implementation Plan.

## Evidence приёмки M1.1

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

## Открытые ограничения и следующая migration

App пока LOCAL/TEST. M1.1 — tenant foundation; проверенный backend M1.2 добавляет auth adapter и ожидает интеграции. AuthenticatedAccount создаётся только после проверки server session; UUID не аутентификация. Same-Workspace/different-Client authorization не пройдена: Client tables ещё нет. Runtime credentials/arbitrary Python/SQL compromise не покрываются одной RLS; application authorization обязательна.

Миграция `0003_auth_sessions.py`, revision `0003`, down_revision `0002`, реализована в проверенном backend M1.2 и ожидает интеграции. IMPL-002 принят C0 для ограниченной LOCAL/TEST реализации, не как новый domain ADR или production policy. 0001/0002/0003 не изменяются при оформлении. Следующая migration пока не резервируется: C5 работает с уже принятым API, не создаёт DDL.

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
