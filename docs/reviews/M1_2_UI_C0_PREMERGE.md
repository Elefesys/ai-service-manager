# M1.2 UI — C0 pre-merge integration decision

Дата решения: 2026-09-18. Ответственный за координацию/приёмку: C0.
Это receipt решения C0, не второй task register и не новый архитектурный ADR.

## Решение и текущий статус

C0 принимает переданный пользователем полный targeted C8 PASS по C8-M1.2-UI-05 на точном head `7821aae54834de7107244090f76a1c7f327af897`, tree `0bcbf5bf0dd9ca937a56af5ef723697cbcfd8ef4`. UI-05 закрыто; ранее закрытые UI-01/UI-02/UI-04 не переоткрываются. Все известные блокирующие замечания UI-review закрыты в границах проверенных snapshots. Новая доработка приложения и очередной полный backend review не требуются.

**M1.2 — REVIEW: backend уже INTEGRATED / VERIFIED, UI одобрен для оформления и условной интеграции, но ещё не INTEGRATED / VERIFIED.** Переход общей задачи из IN_PROGRESS в REVIEW означает завершение выданной реализации и review исправлений, а не завершённое слияние или post-merge verification. M0/M1.1 остаются VERIFIED. M1.3 — TODO / не выдана; полный M1 и production не приняты.

C0 разрешает пользователю обычный merge commit существующего PR #8 только после точного переноса четырёх документов данного пакета, успешного нового CI обоих jobs на опубликованном documentation head и проверки неизменности base main. Codex в этой передаче только переносит документы и готовит обновление PR; самостоятельно merge/auto-merge не выполняет. При неожиданной source/tree/base delta разрешение не применяется.

## Точный snapshot и repository state до оформления

| Объект | Значение |
|---|---|
| Repository | `Elefesys/ai-service-manager` |
| Единственный текущий UI PR | `#8`, `codex/-ui-business-console` → `main` |
| Проверенный опубликованный UI head | `7821aae54834de7107244090f76a1c7f327af897` |
| Проверенный UI tree | `0bcbf5bf0dd9ca937a56af5ef723697cbcfd8ef4` |
| Принятый backend / проверенный actual main | `aa7e792555c19d798eafa0cae17d29b73ca12376` |
| Backend base tree | `77ddd22af30ef07afa89f61e96e1066ba4be8692` |
| CI run | `35358909227`, attempt 1, event `pull_request`, SUCCESS |
| CI checkout | `fcab2583010bb6cece456d8daaba239217bc78ef` |

При проверке C0 PR #8 OPEN / DRAFT / NOT MERGED, head/base неизменны. `fcab258…` — виртуальный PR test-merge, не actual merge в main. Его tree совпадает с tree UI head. Новый documentation commit и actual merge SHA не предсказываются; они фиксируются по фактической публикации и интеграции.

## Disposition цепочки C8 review

| Finding | Решение C0 и основание |
|---|---|
| C8-M1.2-UI-01, P1 | CLOSED на `b74da6662c23a5a1affb7157016eb8a36a338007`: targeted C8 подтвердил сохранение logout intent через повторные ambiguity и bounded explicit recovery. Последующие проверки не дали оснований переоткрыть. |
| C8-M1.2-UI-02, P1 | CLOSED на том же `b74da…`: synchronous monotonic auth owner и fencing stale success/error/follow-up/finally. Исправления сохранены. |
| C8-M1.2-UI-04, P1 | CLOSED на `c1e1e480f7ef61447c6b802fe142399a8a328fcf`: invalidateAuth освобождает busy при актуальном Business 401, отменяет transports, не даёт late rotation менять новый login. C8 выполнил 4 targeted cases успешно. |
| C8-M1.2-UI-05, P2 | CLOSED на `7821aae54834de7107244090f76a1c7f327af897`: независимый targeted PASS для readiness/start/completion barriers двух focus/session tests. |
| C8-M1.2-UI-03, P3 | Принято как неблокирующее ограничение browser evidence: tampered Workspace проверяется anonymous-запросом, не authenticated A→B browser test. Не утверждается, что это более широкое свойство реализовано/проверено данным E2E. |

C0-M1.2-UI-03/04 (Bootstrap DTO/UUIDv7), C0-M1.2-UI-05 (ожидание fault-A E2E) и C0-M1.2-UI-06 (безопасная диагностика на проверенном пути) сохраняют ранее принятое закрытие. Номера C0 и C8 принадлежат разным finding namespaces; одинаковый цифровой suffix не объединяет находки. Backend dispositions сохраняются согласно `M1_2_BACKEND_C0_ACCEPTANCE.md`.

## Что лично проверил C8 на последнем target

Источник этого раздела — полный отчёт reviewer-а, переданный пользователем C0; это не утверждение о формальном GitHub APPROVED другим аккаунтом. C8 подтвердил exact published object/tree, accepted base ancestry, однофайловую test-only delta и чистые source/index.

Runtime: Node 24.8.0, npm 11.6.0; тот же Node executable использовался npm subprocess. Выполнены locked `npm ci`, typecheck, три отдельных targeted запуска (каждый 2 passed / 21 отфильтрованных), один полный frontend suite (30 passed) и build. Два focus dispatch выполняются по одному, A/B перекрываются, B принимается первым, поздние continuations полностью ожидаются. Call-through listener spy и visibility descriptor восстанавливаются. White-box barrier по двум регистрациям listener признан приемлемым для этой ограниченной проверки; retry/sleep/skip/only и подавление ошибок не вводились.

C8 не выполнял новый PostgreSQL/Playwright run и не выдавал received CI за собственный. C5 сообщал отдельную серию 10 targeted + 3 full runs; raw logs этой серии C0 независимо не проверял. Исторический первый полный C8 run на `c1e1e…` с 29 passed / 1 failed не стирается последующими зелёными результатами. Без исторической трассы регистрации handler точная причина того запуска не объявляется доказанным production defect. Конечная зелёная серия не гарантирует отсутствие любой будущей нестабильности.

## Проверенное C0 CI evidence

- Foundation job `105645004565` — SUCCESS: 105 Python non-integration + 105 real PostgreSQL + 30 frontend = 240 случаев.
- Browser job `105645004072` — SUCCESS: 6 Playwright cases через собранный nginx/API/disposable PostgreSQL, workers 1, retries 0.
- Совокупно 246 случаев без повторного подсчёта frontend внутри browser image build.
- Clean-source gates успешно завершены в обоих jobs; types, migrations, contracts/OpenAPI, wheel/assets repeatability и HTTP/reverse-proxy smoke успешны.
- Artifact `m0-verification-35358909227`, ID `10553656868`, ZIP SHA-256 `93ef3671f2e5e86242857f8b5c998910c1a759a53c0ec7ceefd06204603b1de0`.
- C0 ранее скачал и проверил архив, tested checkout, пустой worktree, 108-file tree/modes, 11 архитектурных оригиналов и test-only delta. При оформлении повторно сверены текущие refs/run/jobs и сохранённые байты архива. Новый локальный Vitest/PostgreSQL/Playwright прогон C0 не заявляется.

Источники GitHub:
- https://github.com/Elefesys/ai-service-manager/pull/8
- https://github.com/Elefesys/ai-service-manager/actions/runs/35358909227
- https://github.com/Elefesys/ai-service-manager/commit/7821aae54834de7107244090f76a1c7f327af897

## Документальная синхронизация

Текущий preimage `docs/TASK_REGISTER.md` имеет SHA-256 `c3b8cd680e160e2722d2c81bee7e5c5a3f71e6c549a61d132ad258804feb326a`. Он ещё содержит прежние OPEN UI-01/02. Ранее C5 не применил UI-04 transfer из-за postimage guard, сохранил точный preimage; отдельная проверка C0 на изолированной копии воспроизвела ожидаемый результат. Точная причина расхождения исполнения не установлена.

Этот новый единый пакет заменяет НЕВЫПОЛНЕННОЕ прежнее поручение на перенос реестра, не отменяя решений C0 или историю findings. Старый transfer дополнительно не запускать. Разрешены ровно:

1. `docs/TASK_REGISTER.md`: актуальный summary/строка M1.2, последовательность закрытий, REVIEW/pre-merge gates; исправление двух устаревших текущих упоминаний backend «ожидает интеграции». История предыдущих review остаётся.
2. `docs/tasks/M1_HANDOFF.md`: актуальный UI pre-merge handoff над историей C5/C1. Задание M1.3 не выдаётся.
3. `docs/decisions/IMPL-002-auth.md`: только статус уже принятой backend-интеграции и историческая ссылка на pre-merge. Auth choice/параметры/ADR не меняются.
4. `docs/reviews/M1_2_UI_C0_PREMERGE.md`: этот receipt.

`App.tsx`, тесты, backend, миграции 0001/0002/0003, JSON API contracts, UI consumer contract/runbook, locks, workflows, Compose, image digests, AGENTS и 11 канонических файлов неизменны. Стек/LOCKED/DEFERRED/OPEN/REVISED решения не пересматриваются. Только документы можно перенести механически; исполнитель не уполномочен произвольно редактировать статусы, утверждать состоявшуюся интеграцию или обходить hash guards.

## Условия интеграции и окончательной приёмки

1. Проверить точный four-file documentation tree и отсутствие любых иных изменений; commit и published SHA записать по факту. PR body должен различать backend main run `35321610083`, UI candidate run `35358909227` и новый docs run, а не выдавать их за один прогон.
2. Получить SUCCESS обоих jobs и clean-source на последнем опубликованном documentation head; если CI использует virtual PR merge, проверить соответствие tree. Если изменился main или source scope — остановить интеграцию и передать C0 новое состояние.
3. Только при выполнении условий C0 разрешает Ready for review и Create a merge commit / Merge pull request / Confirm merge для PR #8. Не squash/rebase/force-push/auto-merge; не обходить protections, required checks/reviews или merge queue. Наличие review-переписки с C8 не подменяет требуемый GitHub review.
4. После actual merge выполнить/проверить отдельный push/main run с foundation и browser; старый PR run не заменяет этот результат. Если автоматический main run не появился, допустим workflow_dispatch на exact unchanged main, с явным обозначением event.
5. Передать C0 actual merge SHA/tree и ссылку на main run. Только C0 после этой проверки фиксирует INTEGRATED/VERIFIED полной M1.2 и выдаёт следующий точный base. Receipt собственного merge SHA не требует бесконечной цепочки docs commits: фактический SHA/run могут быть указаны в сопровождающей записи PR и следующем приёмочном документе.

Дополнительный C8 review точной documentation-only delta не требуется. Это разрешение не распространяется на неожиданные исправления приложения или новые функции.

## Сохраняемые ограничения

LOCAL/TEST с синтетическими данными, не production enablement. Ops — отдельная readiness shell без operator authority; production MFA/IdP, sensitive-action re-auth и hardening остаются отдельной работой. Same-Workspace/different-Client paths ещё отсутствуют. Browser fault A покрывает delivered replacement cookie + lost UI response body, не потерю Set-Cookie; authenticated cross-Workspace browser evidence не заявляется. Новые ownership/busy races проверены RTL, не как добавленные browser journeys. Ни полная security certification, ни реальный провайдер/платежи/облако/restore, ни Architecture Freeze v1.0 данным review не объявляются завершёнными. Установка Docker на ПК пользователя для этой интеграции не требуется.
