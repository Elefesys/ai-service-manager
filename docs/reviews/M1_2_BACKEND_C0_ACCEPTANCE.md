# M1.2 backend — C0 acceptance after actual main integration

Дата решения C0: 2026-09-18. Repository: Elefesys/ai-service-manager.

## Решение

C0 принимает **backend-срез M1.2 как INTEGRATED и VERIFIED** на actual main commit `aa7e792555c19d798eafa0cae17d29b73ca12376`. PR #7 фактически слит пользователем через GitHub; C0 повторно прочитал PR/main/commit и проверил отдельный push/main CI. Разрешён старт C5 — login/logout/session-expired/recovery UI и browser journey — строго от этого API SHA. **Полная M1.2 не VERIFIED**: UI и его сквозные проверки ещё не выполнены. M0/M1.1 остаются VERIFIED. M1.3 не выдана; production и Platform Ops privileges не включаются. Канонические ADR не пересматриваются.

Это post-merge решение заменяет прежнее ожидание интеграции из M1_2_BACKEND_C0_PREMERGE.md. Старый документ сохраняется как история, не как текущий запрет C5. Чтобы не создавать бесконечные documentation-only интеграции, C0 поручает C5 перенести точные документы этой приёмки первым отдельным commit новой UI-задачи; работа UI начинается от уже проверенного backend SHA, а не от будущего documentation commit.

## Точные исходники и GitHub

- PR #7: CLOSED / MERGED, merged_at `2026-09-18T07:53:16Z`.
- Предыдущий принятый main/M1.1: `5c7188915fa219d9d6906569e2341632e4969651`.
- Reviewed implementation head: `194ea3cfa3f0aa9b8f271590a26ca3857ade3e54`.
- Reviewed tree до документов: `799f271cbfc1c8815136828da35f9a32ef58b16e` (93 файла).
- Documentation-only PR head: `994d060a08399f201623c17db4016bc6455280b4`; его PR CI `35309851708` SUCCESS.
- Actual merge / принятый API base: `aa7e792555c19d798eafa0cae17d29b73ca12376`.
- Родители actual merge: предыдущий main и documentation-only PR head, без squash/rebase.
- Фактический main tree: `77ddd22af30ef07afa89f61e96e1066ba4be8692` (94 файла).
- Повторное чтение refs/heads/main подтвердило именно actual merge.

От reviewed implementation отличаются ровно четыре ранее разрешённых документа: docs/TASK_REGISTER.md, docs/tasks/M1_HANDOFF.md, docs/decisions/IMPL-002-auth.md и docs/reviews/M1_2_BACKEND_C0_PREMERGE.md. Их bytes совпали с заранее подготовленным C0 пакетом, а все прочие bytes и modes — с reviewed source archive. Runtime/tests/DDL/locks/OpenAPI/frontend/workflows не изменены при оформлении и интеграции. Transport patch отсутствует в итоговом дереве.

GitHub также показывает PR #6 CLOSED / merged=true на его историческом head `305a874ce67f59f8d14fe4bea9f6aa473b43cae7`; эти commits входят в ancestry #7. Это не отдельный принятый API snapshot и не основание повторно сливать/открывать старую передачу. Ветки в этой проверке не удалялись.

## Проверенный main CI

Run: https://github.com/Elefesys/ai-service-manager/actions/runs/35321610083
Event: `push`; branch: `main`; attempt: 1; conclusion: SUCCESS.
Job: `105525139486` (`foundation`); все обязательные шаги SUCCESS.
Artifact: `m0-verification-35321610083`, ID `10537437018`.
ZIP SHA-256: `548b8824dfda4c0c80e0ea4819a460ef9a2042c20e58d192101069ffed6341bb`.
Artifact expires_at: `2026-09-25T07:55:42Z`; C0 отдельно сохранил скачанный ZIP.

C0 проверил целостность ZIP, expected five-file set, tested-commit actual merge, пустой worktree-status, пересчитал Git tree всех 94 файлов с путями/modes, сверил точную docs-only дельту. Все 11 канонических архитектурных файлов совпали с SOURCE_MANIFEST и исходными вложениями побайтово. Нового локального pytest/PostgreSQL-run C0 не выполнял: это независимая проверка фактически исполненного main CI.

Результат одного main run: **91 non-integration + 105 real PostgreSQL + 3 frontend = 199 passed**. В ci.log: строки 606, 619, 370 соответственно. Ruff lint/format — PASS, 36 файлов; mypy — PASS, 13 source files. Fresh/previous-schema upgrade/replay/disposable downgrade/re-upgrade, schema readiness 0003, OpenAPI drift, wheel/static assets reproducibility, Docker/startup/HTTP/reverse-proxy и clean-source gates выполнены. HTTP smoke — ci.log:675. Все команды проверены по неизменённым scripts/ci.sh, scripts/check_backend.sh и Dockerfile.frontend. Повторные CI не суммируются в число тестов. Destructive downgrade только disposable TEST, не production rollback.

## Review и закрытые находки

C0-M1.2-01/02/03 (table set/OpenAPI/cookie UTC), C8-M1.2-01 (Host+port) и C0-M1.2-04 (discarded Host delimiters) закрыты для принятого snapshot. C8-M1.2-02 учтено backend-контрактом и остаётся обязательством UI recovery, не новым блокером backend.

Пользователь передал итог targeted C8 PASS на exact head/tree. C8 самостоятельно проверял код и targeted/non-integration tests; private artifact не скачивал, checksum не пересчитывал и новый PostgreSQL в re-review не запускал. DB evidence было передано C0. C0 не приписывает C8 скачивание ZIP или отдельный DB-run; отдельный C2 review и формальный APPROVED от другого GitHub account не заявляются. Прежние отрицательные findings/попытки сохраняются в истории.

## Оставшиеся границы

Backend работает только LOCAL/TEST: synthetic credentials, PostgreSQL server sessions, CSRF/cookies/exact authority/Origin, проверка membership и Business reads через принятый tenant UOW. Нет публичного signup/reset, внешних identity providers, клиентских бизнес-данных, тарифов, Audit/Jobs/AI/payments. Business session не даёт Platform Ops rights. Auth state и permissions определяются сервером, не UI/LLM; rate counters имеют документированную process-local границу. Production readiness/Architecture Freeze/Client-object authorization не закрываются этой приёмкой.

C5 реализует оставшийся UI той же M1.2 и тесты на реальном браузере + API + PostgreSQL. Отдельные логические frontend-тесты могут использовать test doubles, но не подменяют E2E. Backend, миграции 0001/0002/0003 и security contract остаются неизменными. Любое расширение domain/API scope возвращается C0. Общую M1.2 принимает только C0 после UI-review, интеграции и соответствующего main CI.
