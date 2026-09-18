# M1.2 — окончательная приёмка C0

Дата: 2026-09-18. Ответственный: C0. Этот receipt фиксирует решение, не создаёт второй task register или новый ADR.

## Решение

**Полная M1.2 — INTEGRATED / VERIFIED** на actual main `28c289ce6f77e33676cfa416585cc0e20c0be4e3`, tree `0df4c1b9a2e6922f742ebe459e46dd93d2c2959f`. Приняты и backend, и UI/login/session-recovery срез. PR #8 фактически слит обычным merge commit; первый parent — ранее принятый backend `aa7e792555c19d798eafa0cae17d29b73ca12376`, второй — документационный head `11bb299379833f470c62f98dd343fb769bb86c87`.

C8-M1.2-UI-01/02/04/05 сохраняют CLOSED по цепочке решений C0 и независимых reviews, описанной в `docs/reviews/M1_2_UI_C0_PREMERGE.md`. Последний C8 PASS относится к published UI head `7821aae54834de7107244090f76a1c7f327af897`, tree `0bcbf5bf0dd9ca937a56af5ef723697cbcfd8ef4`; при последующем оформлении/слиянии код и тесты не менялись. Прежние исправления C0 и backend dispositions также сохранены.

M0/M1.1 остаются VERIFIED. Полный M1 ещё не принят: следующий scope — M1.3 «Местные Plan/Subscription/Entitlements и Audit». C0 выдаёт C1 только первый этап M1.3: pre-DDL contract и план реализации/проверок от указанного actual main. Это часть M1.3, не новый milestone. До review этого контракта C0/C2 DDL, runtime implementation и новые UI endpoints не разрешены; миграция не резервируется исполнителем самостоятельно. M2 и production не выданы.

## Actual main CI и предшествующее оформление

- Actual main run: `35368244266`, attempt 1, event `push`, branch `main`, SUCCESS.
- Tested checkout: `28c289ce6f77e33676cfa416585cc0e20c0be4e3` — actual merge, не virtual PR test-merge и не локальный C5 commit.
- Foundation job `105675787590`: SUCCESS; 105 Python non-integration + 105 real PostgreSQL + 30 frontend = 240 cases.
- Browser job `105675787266`: SUCCESS; 6 реальных Chromium journeys через nginx/API/disposable PostgreSQL, workers 1, retries 0.
- Совокупно **246 cases**, frontend внутри browser image build повторно не считается.
- Обе проверки clean-source — SUCCESS. Types/lint, migrations, OpenAPI, wheel/assets repeatability, readiness/HTTP/reverse-proxy smoke прошли.
- Предшествующий documentation-head run `35367688000` для `11bb299379833f470c62f98dd343fb769bb86c87` — SUCCESS, оба jobs и clean-source SUCCESS. Его архив в этой проверке заново не скачивался; окончательное evidence опирается на отдельный actual main run.

## Проверка артефакта C0

Artifact `m0-verification-35368244266`, ID `10557427976`, ZIP SHA-256:
`d71f362404280dea321c3bc1a9cc21edb5cae10469d17886c013eea29e008ef9`.

C0 скачал архив, проверил digest, `tested-commit.txt`, пустой `worktree-status.txt` и заново вычислил Git tree 109 файлов с учётом modes. Tree совпал с actual merge и ожидаемым pre-merge пакетом. Все 11 архитектурных файлов совпали побайтово с загруженными оригиналами.

От последнего C8-reviewed UI snapshot отличаются ровно четыре разрешённых документа: TASK_REGISTER, M1_HANDOFF, integration metadata IMPL-002 и новый UI pre-merge receipt. Каждый postimage совпал с подготовленным пакетом C0; остальные 105 файлов/режимов неизменны. Невыполненный прежний UI-04 register transfer отдельно не нужен: накопившиеся решения вошли в единый pre-merge пакет.

C0 прочитал фактические foundation/browser результаты GitHub и проверил содержимое источников. Новый локальный PostgreSQL/Vitest/Playwright-прогон C0 не заявляется. Локальная серия C5 10+3 остаётся received report; raw logs C0 независимо не проверял. Последний C8 лично выполнил 3 targeted + 1 full frontend на Node 24.8.0/npm 11.6.0, но PostgreSQL/Playwright evidence получил от C0. История прежних падений не стирается.

## Принятый функциональный результат и ограничения

Вход/bootstrap/session, серверные memberships и чтение Business, explicit rotation с неизменным absolute expiry, confirmed logout и bounded ambiguity recovery, monotonic auth ownership, Business-generation fencing и восстановление доступного входа после authoritative session loss. Cookie остаётся HttpOnly; CSRF — page memory; permissions и критические факты определяет сервер. Ops — отдельная readiness shell без operator authority.

Приёмка ограничена LOCAL/TEST/synthetic M1.2, не production enablement или security certification. Authenticated cross-Workspace browser proof и loss of replacement Set-Cookie этим E2E не заявляются: tampered Workspace проверяется anonymous-запросом, fault A — delivered cookie + lost body. Новые ownership/busy races проверены RTL, а не дополнительными browser journeys. Конечная серия зелёных запусков не гарантирует отсутствие любого flake. Production identity/MFA/SSO, paid billing, quotas для будущих expensive operations, client payments, AI и Telegram не реализованы этим milestone. Известные deprecation/build warnings не скрываются и не считаются падениями данного run.

## Синхронизация и следующий base

Исторический pre-merge receipt не переписывается после интеграции. C0 подготовил post-merge обновление TASK_REGISTER и M1_HANDOFF плюс этот receipt; точный перенос разрешён C1 первым отдельным документационным commit новой задачи M1.3. До его публикации эти postimages являются подготовленными изменениями, а не уже записанным состоянием GitHub. Дополнительный docs-only PR перед pre-DDL работой не требуется.

Исходный принятый base M1.3 — `28c289ce6f77e33676cfa416585cc0e20c0be4e3`. Документационный commit не переименовывает исходный base задачи. Нельзя повторно реализовывать M1.2 или продолжать слитый PR #8. Дальнейшие source changes требуют собственных CI/review; этот receipt не выдаёт готовый PASS будущей M1.3.

Источники: https://github.com/Elefesys/ai-service-manager/pull/8 ; https://github.com/Elefesys/ai-service-manager/actions/runs/35368244266 ; https://github.com/Elefesys/ai-service-manager/commit/28c289ce6f77e33676cfa416585cc0e20c0be4e3 .
Канон следующей задачи: Architecture Spec §§2, 3.12–3.14, 15, 24.5; ADR-002/005/099/100/102/103/106/126/182/270; Implementation Plan §6, строка M1.3; IMPL-001 и принятые M1.1/M1.2 contracts.
