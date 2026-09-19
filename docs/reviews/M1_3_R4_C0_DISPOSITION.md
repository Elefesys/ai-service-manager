# C0 — M1.3 R4: решение по targeted C2 re-review R3

Дата: 2026-09-19. Это решение C0 о следующей docs-only редакции pre-DDL контракта. Оно не является новым LOCKED ADR, не разрешает DDL/runtime и не назначает migration successor.

## Snapshot и evidence

C2 проверил published R3 head `dbde2bda183e3d2dcb58c9828d3a88f21fb4d940`, tree `26ff0a611a9add704d1a60941fa7e89b252bda5a`. Исходный accepted task base M1.3 остаётся `28c289ce6f77e33676cfa416585cc0e20c0be4e3`; accepted current main — `049b212f135f09c025d2f81badc810fa7c2c9d13`. Ветка контракта не обязана содержать maintenance main как ancestor; PR CI проверяет virtual merge.

Исходный C2 report SHA-256 UTF-8: `37efe0abae0a79b82cc6acc6a29e792a740df93006e1efaad0bb44a1d8109a21`. C2 выполнил read-only source/object/contract проверки и независимо пересчитал fingerprint/manifest vectors; PostgreSQL/Browser M1.3 implementation не существует и не проверялась.

C0 проверил run `35450322392`: SUCCESS, foundation + browser + оба clean-source gates; 105 Python + 105 real PostgreSQL + 30 frontend + 6 Playwright = 246 distinct regression cases. Tested virtual merge `ceb2dae55727c463bb48ea85c2c8a3f504105f2b`, tree `07b09da416e0260a239fc91de4869e9b175a64c0`; artifact SHA-256 `4db21b9c9adf3162836e21fa96a6acefb3be3337ee2431c8236417b73eeaf941`. Это regression evidence существующего приложения, не доказательство будущей M1.3 реализации.

## Disposition

C2 verdict **CHANGES_REQUESTED** принимается.

Закрыты на уровне pre-DDL contract и без нового конкретного противоречия не переоткрываются:
- `C0-M1.3-R2-01` P2;
- `C2-M1.3-R2-02` P1;
- `C2-M1.3-R2-03` P1;
- `C2-M1.3-R2-04` P1;
- `C2-M1.3-R2-05` P2;
- `C2-M1.3-R2-06` P2;
- `C2-M1.3-R2-07` P2.

`C2-M1.3-R2-08` и `C2-M1.3-R2-09` остаются REMAINING и конкретизированы текущими findings:
- `C2-M1.3-R3-01` — P1 — exact error envelope новых routes несовместим с неизменённым M1.2 AuthBoundary;
- `C2-M1.3-R3-02` — P2 — не зафиксирована обязательная additive CORS-дельта для browser `PATCH` + `Idempotency-Key`;
- `C2-M1.3-R3-03` — P1 — Workspace serialization не решает конкурентное создание общего synthetic TEST catalog разными Workspaces.

Текущими blockers считать именно эти три R3 finding. Они OPEN до targeted C2 re-review R4.

## Решения C0 для R4

### R4-01 — layered error envelope, без изменения M1.2 contract

Не вводить route-aware изменение общего M1.2 `AuthBoundary` ради `state_reason`.

Для новых M1.3 routes контракт задаёт дискриминированное объединение из двух exact вариантов:

1. **CommonError** — ровно `{"error":{"code":"<CODE>"}}`, без `state_reason`.
   Этот вариант используется для всех существующих boundary/auth/common/domain codes новых routes, включая применимые `SESSION_REQUIRED`, `ORIGIN_DENIED`, `CSRF_REJECTED`, `ACCESS_DENIED`, `NOT_FOUND`, `STALE_STATE`, `IDEMPOTENCY_KEY_CONFLICT`, `BODY_TOO_LARGE`, `UNSUPPORTED_MEDIA_TYPE`, `INVALID_REQUEST`, `RATE_LIMITED`, `UNAVAILABLE`, `INTERNAL_ERROR`.
2. **BillingStateError** — ровно `{"error":{"code":"BILLING_STATE_UNAVAILABLE","state_reason":"<STATE_REASON>"}}`.
   Он используется только для application/domain structural billing GET failure с уже принятым bounded `state_reason` set.

`state_reason` не является nullable optional field общего error object. Для одного HTTP status 503 допустимы два discriminator variants: code-only `UNAVAILABLE` от shared boundary/unhandled infrastructure path и billing-domain `BILLING_STATE_UNAVAILABLE` + required `state_reason`. OpenAPI/typed contract будущей реализации должен выразить это как exact union. Existing M1.2 routes/response bytes не меняются.

### R4-02 — additive browser CORS obligation

R4 явно фиксирует future implementation delta, но не реализует её сейчас:

- к текущему `allow_methods` добавить `PATCH`, сохранив существующие методы;
- к текущему `allow_headers` добавить `Idempotency-Key`, сохранив `Content-Type`, `X-CSRF-Token`, `X-CSRF-Bootstrap`;
- configured exact `allow_origins`, `allow_credentials=true`, Origin/Host/CSRF/JSON boundary и отсутствие wildcard не ослаблять;
- preflight/browser proof обязан проверить configured Origin + `PATCH` + `content-type,x-csrf-token,idempotency-key`;
- negative proof обязан отвергать чужой Origin и неразрешённый header/method;
- отсутствие CORS разрешения не заменять server-side authorization/CSRF.

Это implementation obligation API/browser слоя, не новый endpoint и не разрешение менять middleware в docs-only R4.

### R4-03 — exact global TEST catalog serialization

Выбирается один механизм для LOCAL/TEST synthetic catalog без новой таблицы и без generic lock framework:

- каждый поддерживаемый M1.3 LOCAL/TEST catalog create/validate/seal path первым в своей migration/provisioning transaction вызывает `pg_advisory_xact_lock(1295070019, 1)`;
- `1295070019` — фиксированный технический namespace (ASCII `M13C` в big-endian int32), второй key `1` относится только к synthetic catalog `code='test'`, `revision=1`; production/business meaning у key нет;
- после global lock код повторно разрешает/создаёт exact plan/revision; существующая revision parent блокируется `FOR UPDATE` и проверяется exact SEALED manifest/digest; создание DRAFT→entitlements→SEALED выполняется под тем же global lock;
- все поддерживаемые entitlement/seal writers для этого synthetic catalog соблюдают порядок **global catalog advisory lock → revision parent**;
- затем initializer блокирует существующий `platform.workspaces` row `FOR UPDATE` как единственный Workspace serialization primitive; вариант “workspace parent/advisory” удаляется;
- далее единый порядок initializer: **global catalog lock → catalog plan/revision parent → workspace parent → account → subscription → service mode → provisioning Audit**;
- два разных fresh Workspaces с одинаковыми exact catalog inputs: один ждёт global lock, затем оба завершаются `INITIALIZED`, каталог создаётся один раз;
- concurrent same Workspace/same input: первый `INITIALIZED`, второй после lock — `NOOP`;
- same Workspace/different input или incompatible catalog/partial/drift — bounded conflict, без overwrite/repair;
- unique violation не используется как необработанный нормальный control flow; после ошибки transaction не продолжается “как будто успешно”;
- advisory lock удерживается только короткой LOCAL/TEST provisioning transaction. Runtime contact command его не берёт.

R4 не добавляет production catalog provisioning и не обещает этот lock protocol за пределами synthetic LOCAL/TEST slice.

## Scope и следующий gate

R4 сохраняет D-01…D-13, восьмитабличный inventory, R3 physical/RLS/grant matrices, fingerprint vectors, DTOs и семь закрытых findings. Изменять их можно только для устранения прямой внутренней несовместимости с R4-01…03, без расширения scope.

Разрешены постоянные изменения ровно:
- `docs/TASK_REGISTER.md`;
- новый `docs/reviews/M1_3_R4_C0_DISPOSITION.md`;
- `docs/tasks/M1_3_CONTRACT.md`.

`docs/reviews/M1_3_C0_C2_DISPOSITION.md` и `docs/reviews/M1_3_R3_C0_DISPOSITION.md` сохраняются как история. Запрещены DDL, migrations, backend/frontend/runtime/generated contracts, locks/dependencies/CI/Compose, rebase/reset/merge main, новый PR, Ready/merge/auto-merge и production enablement.

После публикации R4 требуется новый PR-context CI и targeted read-only C2 review только R3→R4 delta + consistency с принятым контрактом. Лишь после PASS C0 может закрыть три текущих blockers и отдельно разрешить implementation.
