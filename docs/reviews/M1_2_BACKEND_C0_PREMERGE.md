# M1.2 backend — решение C0 перед интеграцией

Дата решения C0: 2026-09-18. Repository: Elefesys/ai-service-manager. Implementation PR: #7.

## Решение и границы

C0 принимает backend-review как PASS и разрешает подготовленную docs-only дельту, затем интеграцию PR #7 при успешном CI опубликованного итогового head и неизменном принятом base. Это не запись о выполненном merge. Backend integration и actual push/main CI пока pending; полная M1.2 остаётся REVIEW. C5 и M1.3 не выданы. M0/M1.1 VERIFIED не отменяются.

Закрытые находки на проверенном snapshot: C0-M1.2-01 (точный набор таблиц), C0-M1.2-02 (generated OpenAPI), C0-M1.2-03 (UTC cookie expiry), C8-M1.2-01 (Host/port allowlist), C0-M1.2-04 (discarded Host delimiters). C8-M1.2-02 учтено контрактом, не blocker; recovery UX остаётся частью C5. Закрытие не распространяется на непроверенные последующие изменения.

## Точный snapshot

- Принятый исходный base/main: `5c7188915fa219d9d6906569e2341632e4969651`.
- Pre-DDL contract: `7527154650b99958b5cfc0f4bfdd9ea135f7fa21`.
- Coordination C0: `7bf818bdfd8b156620c840d5d7211087113d9fb5`.
- Transport: `305a874ce67f59f8d14fe4bea9f6aa473b43cae7`.
- Опубликованная реализация: `7012bf586166d35ad82919087c0f68a6f3eb92ee`.
- Host/port fix: `e7e3d43fe8874ec4d87eaea1489cf0ba42955eea`.
- Итоговый reviewed head: `194ea3cfa3f0aa9b8f271590a26ca3857ade3e54`.
- Reviewed tree: `799f271cbfc1c8815136828da35f9a32ef58b16e` — 93 файла до оформления.
- CI checkout: `c99d9cc7e781fd9acf20ae7276761336e38b99d1`, виртуальный test-merge с родителями base и reviewed head, не actual main merge; то же дерево.

## CI evidence и границы reviewer-а

Run: https://github.com/Elefesys/ai-service-manager/actions/runs/35248449942
Event: pull_request. Job: `105294503581`. Все обязательные шаги SUCCESS.
Artifact: `m0-verification-35248449942`, ID `10508471245`.
ZIP SHA-256: `b80c4c000e1aefe47ea6f2303b49d58d9f6cdb5c2355c3beea046903f4121c22`.
Состав: architecture.log, ci.log, source.tar.gz, tested-commit.txt, worktree-status.txt.

91 non-integration + 105 real PostgreSQL + 3 frontend = **199 passed** за один run. Lint/format/types, migration cycles, OpenAPI, wheel/assets reproducibility, Docker/readiness/HTTP/proxy smoke и clean-source gates SUCCESS. Downgrade/re-upgrade проверяется только на disposable TEST, не является production rollback.

C0 проверил ZIP SHA, tested-commit, пустой worktree и пересчитанное 93-file tree с modes; 11 архитектурных оригиналов совпали с manifest и предоставленными исходниками. При подготовке этого документа C0 повторно прочитал GitHub refs/PR/run: PR #7 открыт/Draft, head неизменён, main остаётся на base. Использована сохранённая копия CI artifact; нового локального Docker/PostgreSQL/pytest-run C0 здесь нет.

Пользователь передал итоговый фрагмент повторного заключения Codex/C8: PASS для exact head/tree, новые блокеры/findings отсутствуют, новых patches/commits/source/doc изменений нет. C8 выполнил собственные targeted/non-integration проверки, но НЕ скачивал private artifact, НЕ пересчитывал ZIP checksum и НЕ запускал новый PostgreSQL. Успешный PostgreSQL run использован как предоставленное C0 evidence. C0 не представляет этот фрагмент как полный экспорт отчёта, собственные C8 логи или формальный GitHub APPROVED от отдельного аккаунта. Полный ответ остаётся в исходной задаче Codex; его timestamp/ID здесь не выдумываются.

Первоначальный C8 security review охватывал identity/password/session/CSRF/tenant/DDL/grants и обнаружил один P2. Повторный review адресный. C0 отдельно сверил DDL/grants с исходниками и evidence; независимый C2 review или production security certification не заявляются.

## Принятый ограниченный backend

LOCAL/TEST synthetic login, PostgreSQL server sessions с непрозрачными cookie tokens и DB verifiers, expiry/rotation/revocation, CSRF/exact Origin и Host/authority, ограничение входа, runtime least privilege, Business read через неизменённый M1.1 UOW. Единственная новая migration 0003 -> 0002: platform.auth_credentials и platform.auth_sessions. Предыдущие 0001/0002 и tenant isolation не переписаны. Structured state и application logic, не LLM, определяют критические факты.

IMPL-002 принимается C0 как реализационный выбор для этого snapshot. Это не отмена canonical ADR, не Architecture Freeze, не production activation и не приёмка всей M1.2. Сессии/permissions не заменяются памятью процесса; rate counters имеют уже описанную process-local/restart/replica границу. Business identity не даёт Platform Ops rights.

## Контролируемая интеграция

Текущее разрешение — только четыре документа: docs/TASK_REGISTER.md, docs/tasks/M1_HANDOFF.md, docs/decisions/IMPL-002-auth.md и этот receipt. Нельзя менять runtime, tests, миграции, contracts JSON, frontend, locks, workflows или канон. Точные текстовые postimages подготавливает C0; Codex механически переносит их. Это не новая реализация и не ещё один полный C8 audit.

Документальный commit меняет tree. Его новый полный CI должен завершиться SUCCESS; старый run не выдаётся за исполнение нового head. При неизменном source за пределами этих четырёх документов и сохранении base C0 заранее разрешает обычный **Create a merge commit** для существующего PR #7. Squash/rebase/force-push, auto-merge, обход branch protections и слияние PR #6 не разрешены. Если code/base неожиданно изменились, разрешение не применяется.

После фактического merge C0 проверяет merge SHA/parents/tree и отдельный **event=push, branch=main** CI именно этого SHA, clean-source и результаты. При сбое не выдаёт C5 base и организует исправление конкретного failure. Для отметки VERIFIED по backend-срезу необходимы фактические интеграционные результаты, а не будущая условная запись.

После подтверждения main C0 оформляет backend integration/verification в этом едином реестре и выдаёт C5 точный принятый API SHA. Общая M1.2 не может быть VERIFIED до C5 login/logout/session-expired/recovery UI и API+browser journey. Не создавать бесконечные commits ради записи документом собственного будущего SHA: post-merge evidence допускается привязывать PR-комментарием и следующей согласованной записью реестра.

PR #6 сохраняется как исторический handoff до подтверждения интеграции #7; затем его можно закрыть без merge отдельным согласованным действием. Не удалять ветки на этом шаге. Реальные данные мастера, production credentials, платные вызовы и установка Docker на пользовательский ноутбук не требуются.
