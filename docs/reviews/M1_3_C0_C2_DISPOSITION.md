# C0 — M1.3: решения для редакции R2 после независимого C2 review

Дата решения: 2026-09-19. Основание: переданный пользователем полный C2 report с verdict CHANGES_REQUESTED; канонические Spec v0.28, принятые ADR и Implementation Plan; опубликованный PR #9.

## Статус и точка продолжения

- Repository: Elefesys/ai-service-manager; PR #9, codex/-m1.3-ddl → main.
- Reviewed proposal head: `f4fb513de79c2a9b93c746db17b3395d5233dfdf`.
- Reviewed proposal tree: `529e8bcb5de4be04fb0a56f4737327052b22d131`.
- Original accepted task base: `28c289ce6f77e33676cfa416585cc0e20c0be4e3`; tree `0df4c1b9a2e6922f742ebe459e46dd93d2c2959f`.
- Proposal SHA-256: `cab7c014eb0c264377f2a160825cdb984195ee4fcf165965bc3deb7838558c2b`.

C0 принимает CHANGES_REQUESTED для контрактного предложения. G-01…G-07 и связанные OPEN требуют исправленной редакции и повторной проверки C0/C2. Это не находки в работающей M1.3: её DDL/runtime пока нет.

Ниже — **решения C0 о направлении редакции R2**, а не утверждение, что R2 уже написана, проверена или разрешена к реализации. C1 переносит решения в один непротиворечивый контракт, явно отделяя их от LOCKED-канона. Статус результата: **R2 PROPOSED / AWAITING C0-C2 REVIEW**. Не присваивать миграционный revision; successor 0003 будет выдан отдельно. Не менять 0001–0003, generated contracts, runtime или frontend. Принятые ADR не отменяются и не помечаются REVISED. Production retention, реальные цены/лимиты/длительности и доступность будущего managed PostgreSQL остаются OPEN; paid billing/Jobs/Outbox/Ops writer — отложенный scope.

## D-01 / OPEN-01 — физическое размещение

C2 рекомендует вариант B (Workspace billing в app) при явном толковании Spec §2.4. **C0 выбирает иной, консервативный вариант:** SaaS billing в platform; бизнес-аудит в app. Spec §2.4 относит plans/subscriptions к platform data, §3.2 определяет platform как SaaS/global. Не переосмысливаем §2.4 и не создаём исключение из канона ради этой задачи.

Предлагаемый R2 inventory, ровно восемь таблиц:

1. `platform.saas_plans`;
2. `platform.saas_plan_revisions`;
3. `platform.plan_entitlements`;
4. `platform.workspace_billing_accounts`;
5. `platform.workspace_subscriptions`;
6. `platform.workspace_service_modes`;
7. `app.audit_events`;
8. `platform.billing_contact_command_receipts`.

Только первые три — общий несекретный каталог без tenant RLS. Остальные пять Workspace-owned независимо от имени schema: workspace_id NOT NULL, ENABLE/FORCE RLS, USING/WITH CHECK, transaction-fenced `app.current_workspace_id()`, tenant-safe composite keys/FKs, RESTRICT, отдельная migrator policy. Имя platform не предоставляет ни authorization, ни bypass. Runtime не получает blanket schema/table privileges. В документе указать, что рекомендация B рассмотрена, но не выбрана; это не ошибка C2 и не пересмотр tenant boundary.

## D-02 / OPEN-02 — интервалы и установка extension

Выбран декларативный GiST exclusion, а не advisory-lock fallback:
`workspace_id WITH =` и `tstzrange(effective_from,effective_until,'[)') WITH &&`.
Constraint — immediate, NOT DEFERRABLE. Оба конца конечны (отдельные isfinite CHECK; NOT NULL и `<` сами по себе не исключают PostgreSQL infinity). Соседние интервалы допускаются; пересечения одного Workspace запрещены независимо от статуса. В M1.3 только append interval; исправление/замена уже записанного или будущего интервала отдельным runtime writer не вводится.

C0 одобряет **btree_gist как дополнительную инфраструктурную предпосылку будущей M1.3**, но не устанавливает его в docs-only задаче. Есть существенное уточнение к рекомендации C2 «устанавливает migrator»: текущий bootstrap выдаёт asm_migrator только CONNECT на database; extension schema создаёт bootstrap admin. Поэтому сохраняем разделение IMPL-001:
- extension устанавливает существующий bootstrap/admin provisioning identity в `extensions`, как инфраструктурную подготовку;
- для уже существующей 0003 БД нужен отдельно описанный идемпотентный admin preflight до новой Alembic migration;
- asm_migrator проверяет наличие/версию/namespace и создаёт свои таблицы/constraints, но не получает постоянные database CREATE, SUPERUSER, CREATEROLE или владение БД ради extension;
- при отсутствии extension migration безопасно останавливается до частичного DDL; не переключается молча на слабый invariant;
- версия extension и наличие подходящей opclass фиксируются после фактической проверки pinned PostgreSQL image, до разрешения implementation; доступность в будущей production SKU не предполагается;
- downgrade доменного среза не удаляет инфраструктурный extension; сохраняет прежний pgvector 0.8.6 и roles. Future tests проверяют свежую БД, upgrade 0003 с preflight, отсутствие prerequisite, replay и disposable downgrade/re-upgrade.

Это уточнение необходимо потому, что extension approval не равен праву расширять DB-роли. Документация PostgreSQL подтверждает GiST classes для uuid и пригодность btree_gist для exclusion; фактической установки/PG proof в этой проверке C0 не было.

## D-03 / OPEN-03 — аудит, объём и срок

LOCAL/TEST Audit и command receipts сохраняются append-only в течение жизни disposable окружения до его teardown. Это не production indefinite retention и не юридически установленный срок. Production duration/privacy workflow остаются OPEN; purge API/framework не создаются.

Для Audit payload выбрать `jsonb`, object-only и `octet_length(payload::text) <= 4096` при UTF-8 server encoding. Это байты представления PostgreSQL jsonb::text, не исходный HTTP body, не число символов и не binary jsonb storage size. HTTP/input/log ограничения задаются отдельно. Event-specific shape — фиксированный allow-list; raw display name, email, credentials, session/CSRF tokens, cookies, headers, SQL parameters и exception text запрещены.

Базовые ограничители R2: event_type/object_type/reason_code — фиксированные значения длиной не более 64; object_version > 0; correlation_id uuid от сервера. USER_ACCOUNT actor берётся из допущенного WorkspaceContext; LOCAL_PROVISIONER имеет null user id и никогда не изображает OWNER. Composite actor FK `(workspace_id,actor_user_account_id)` → existing membership с RESTRICT; отзыв membership делается статусом REVOKED и не стирает историю. Для обоих текущих event types object_type только WORKSPACE_BILLING_ACCOUNT, с composite `(workspace_id,object_id)` FK к billing account. Не проектировать generic polymorphic Audit registry для будущих сущностей.

## D-04 / OPEN-04 — одна конкретная квитанция команды

Replay guarantee ADR-124/Spec §18.4 сохраняется. Восьмая таблица разрешена к **проектированию в R2** только для UPDATE_BILLING_CONTACT, не generic command/Jobs/Outbox.

Минимальные поля: workspace_id, UUIDv7 id, operation CHECK='UPDATE_BILLING_CONTACT', bounded opaque idempotency_key, 32-byte SHA-256 request_fingerprint, expected_version bigint > 0, billing_account_id, status IN_PROGRESS/SUCCEEDED, result_version, result_outcome UPDATED/NOOP, created_at/completed_at. Composite PK/UNIQUE/FK и FORCE RLS обязательны. Ключ — ASCII `[A-Za-z0-9._:-]{1,128}`, точное значение; пробелы/пустое/дубликат HTTP header отвергаются, не молча trim-ятся. Fingerprint и ключ не логируются; fingerprint также не считается обезличиванием PII.

Начальный success response выбрать **200 с immutable result metadata, без контактного значения**: workspace_id, billing_account_id, receipt_id, result_version (decimal string), outcome UPDATED/NOOP, completed_at. Повтор возвращает первоначальные body/status metadata; не перечитывает изменившийся display name. Актуальный контакт получается отдельным authorized GET billing. Изменяющиеся request/correlation headers не обещаются побайтово идентичными прежнему ответу.

Порядок supported command в одной tenant transaction:
1. session admission + live membership/permission; input validation/normalization;
2. fingerprint v1 из operation, trusted workspace, expected_version и нормализованного display name; canonical UTF-8 encoding определена один раз;
3. lookup/claim `(workspace,operation,key)` **до CAS**;
4. same fingerprint/SUCCEEDED после новой authorization → прежний результат, без UPDATE/Audit;
5. different fingerprint → **409 IDEMPOTENCY_KEY_CONFLICT** (точный LOCKED-код, не IDEMPOTENCY_CONFLICT);
6. новый claim → account row lock и CAS, затем ровно один фактический Audit для изменившегося значения, finalize receipt;
7. один commit; response только после него.

При отсутствии/ошибке Audit откатываются mutation и claim; при stale CAS не остаётся Audit или receipt. Same-key concurrent caller ждёт уникальную запись/lock, затем читает committed receipt; нельзя принимать отсутствие строки в старом statement snapshot после ON CONFLICT за отсутствие результата. Разные ключи с одной expected_version имеют одного CAS winner при реальном изменении. Не оставлять committed IN_PROGRESS в supported path: нет долгоживущих jobs/lease/recovery workers. SUCCEEDED неизменяем. Нормализованный no-op при совпавшей expected_version не меняет version/updated_at и не создаёт Audit, но получает SUCCEEDED/NOOP receipt для стабильного replay. Stale version проверяется до решения no-op; existing successful replay — до этой проверки.

Authorization/CSRF обязательны и на replay. Receipt не credential и не повод раскрыть чужой Workspace. Никакой ключ не предоставляет полномочия.

## D-05 / OPEN-05 — единая criticality, значения и coherent snapshot

Единственный источник criticality — `plan_entitlements.criticality` внутри SEALED revision. Интерфейс: `EntitlementService.decide(snapshot, CapabilityKey)`; свободный OperationCriticality и внешний db_now убрать. Ключи/criticality и возможности не принимаются как авторитетные сведения от UI/LLM.

Минимальный synthetic catalog содержит явно TEST-only значения, не production defaults:
- test.m1_3.essential_true: BOOLEAN true / ESSENTIAL;
- test.m1_3.standard_true: BOOLEAN true / STANDARD;
- test.m1_3.standard_false: BOOLEAN false / STANDARD;
- test.m1_3.expensive_positive: INTEGER 3 / EXPENSIVE_OPTIONAL;
- test.m1_3.expensive_zero: INTEGER 0 / EXPENSIVE_OPTIONAL;
- missing key проверяется отсутствием строки.

3 — произвольное тестовое число для проверки типа, не бизнесовый лимит. Pilot timestamps задаются явным provisioner input; не изобретать реальную длительность trial. New M1.3 bigint values, включая versions/limits, в JSON передаются canonical decimal strings с validation диапазона bigint; прежние M1.2 DTO не переписывать. INTEGER 0 = LIMIT("0"), а не BOOLEAN disabled. OVER_LIMIT/usage accounting не реализуются искусственно; показать как future, не возвращаемый текущим decider reason.

Один coherent billing snapshot читать **одним фиксированным SQL statement** (join/CTE/aggregation допустимы) в существующем коротком tenant UOW. В нём же получить CURRENT_TIMESTAMP и проверить интервалы. Одна транзакция и одинаковое время сами по себе не дают одного MVCC snapshot нескольким SELECT на READ COMMITTED; отдельные round trips для account/subscription/mode/catalog не выдавать за coherent read. Не менять глобальную isolation policy принятого UOW ради этого.

Обычная entitlement matrix для валидного snapshot: NORMAL — все три criticality проходят оценку значения; GRACE — только ESSENTIAL/STANDARD; LIMITED — только ESSENTIAL; SUSPENDED — ни одна обычная plan capability. Разрешённая категория не превращает BOOLEAN false в true. Ограниченная категория → DISABLED/SERVICE_MODE_RESTRICTED. Security/continuity endpoints и административное исправление контакта **вообще не проходят через billing gating**, но сохраняют auth/permissions/CSRF; это не скрытый entitlement=true для неизвестного ключа.

## D-06 / OPEN-06 — только display name

Контактная mutation M1.3 меняет только contact_display_name; email из текущего schema/API/fixtures убрать. Display name также может быть PERSONAL_DATA. Вход — строка; trim только U+0020 с краёв, без case folding/Unicode normalization, длина после trim 1..200 Unicode code points, UTF-8 <= 800 bytes, без NUL/C0/DEL; null/пустое запрещены. Эти правила — ограниченный технический контракт C0, не юридическая классификация конкретного клиента. Повторная normalization/validation в DB command должна совпадать с application boundary. Значение не дублировать в Audit/receipt result или ошибках; before/after raw values не сохранять. UI/GET доступны только live OWNER с billing:read.

## D-07 / OPEN-07 — service mode без runtime writer

Runtime только читает. LOCAL/TEST provisioner создаёт NORMAL; остальные mode допускаются только в явных migrator test fixtures:
NORMAL/PROVISIONED_LOCAL, GRACE/TEST_GRACE, LIMITED/TEST_LIMITED, SUSPENDED/TEST_SUSPENDED. CHECK пары обязателен. OWNER/ADMIN не меняют mode; provider/webhook/Ops editor отсутствуют.

Singleton на Workspace сохраняется. Активность: effective_from <= db_now AND (effective_until IS NULL OR db_now < effective_until). Не-null timestamps конечны; null end означает действующий до отдельной разрешённой замены. Конечный истёкший/future mode не становится NORMAL: обычные capabilities DISABLED/SERVICE_MODE_INACTIVE. Runtime замены/history writer нет в M1.3.

## D-08 / G-01 — замкнутая SEALED revision

Lifecycle DRAFT → SEALED ровно один раз. DRAFT: published_at NULL; SEALED: published_at NOT NULL и finite. Создание revision, полный synthetic entitlement manifest и seal выполняются одним provisioning transaction. EntitlementService использует только SEALED.

DB-enforceable contract должен включать:
- entitlement INSERT только в DRAFT; UPDATE/DELETE запрещены (включая перенос в другую revision);
- seal и entitlement insert сериализуются блокировкой одной parent revision row; одного незаблокированного SELECT состояния в trigger недостаточно при гонке seal/insert;
- перед seal сверяется полный manifest (keys/kinds/values/criticalities) и его count/digest; алгоритм canonical representation и ожидаемый fixture manifest описать точно;
- после seal revision и вся entitlement set не меняются; поздний INSERT отвергается даже через поддерживаемый provisioner;
- subscription имеет DB-enforceable ссылку только на SEALED: выбрать composite reference `(plan_revision_id, required_publication_state)` с CHECK required_publication_state='SEALED' → UNIQUE revision(id,publication_state), RESTRICT; не оставлять «или writer» как альтернативу;
- supported writes защищены, superuser/DDL admin может отключать/удалять объекты и не включается в гарантию.

## D-09 / G-02 — точный read surface

Принята рекомендация C2: invoker-right repository с параметризованным fixed-shape SQL и SELECT grants ровно на три общих catalog tables. Никаких catalog SECURITY DEFINER/read alternative или generic catalog endpoint. Read начинается с разрешённого Workspace billing state под RLS и связывает pinned SEALED revision. Direct SELECT capability runtime означает, что несекретный каталог не обещается скрытым от обладателя DB credentials; прикладной endpoint всё равно permission-gated.

Workspace billing account/subscription/mode/Audit — только SELECT у runtime, с policies; контактная запись описана ниже. Никаких runtime plan/subscription/mode INSERT/UPDATE/DELETE или arbitrary Audit insert. Receipt table непосредственно runtime не читает и не пишет.

## D-10 / G-03,G-04 — contact command и правдивый аудит

Из альтернатив C2 **выбран один узкий typed DB command**, не независимые runtime UPDATE(account)+INSERT(audit) и не generic mutation API:
`platform.update_billing_contact(expected_version bigint, contact_display_name text, idempotency_key text)`.

Функция вызывается только domain/application service внутри допущенного tenant UOW. Runtime получает EXECUTE только этой exact signature; прямые UPDATE account и INSERT/UPDATE receipt/Audit не выдаются. Function owner — asm_migrator; SECURITY DEFINER, fixed safe search_path (`pg_catalog, pg_temp`, schema-qualified custom references), PUBLIC EXECUTE revoked в той же migration transaction; без dynamic SQL/table-name/actor/mode/payload arguments. Нельзя передать workspace/actor/correlation как клиентские arguments: функция получает их из валидного XID-fenced context, проверяет соответствие actor kind и live ACTIVE OWNER membership. При отсутствии/invalid fence/несовпадении — fail closed.

Один closed command path делает claim/CAS/фактическое изменение/Audit/finalize атомарно, сам не commit-ит и не подавляет ошибку аудита. Строит event из реально прочитанного OLD и RETURNING NEW, а не из сообщения клиента «что изменено». Payload contact event содержит только фиксированный changed_fields=['contact_display_name']; reference/new version, actual trusted actor/correlation выводятся сервером. Provisioning audit — отдельный controlled migrator path, LOCAL_PROVISIONER; runtime не вызывает его.

**Граница доверия:** GUC/XID fence защищает transaction/pool scope и требует доверенного backend issuer, но не является криптографическим удостоверением личности против злоумышленника с произвольным SQL под украденным asm_runtime credential. Не обещать такую новую гарантию. Проверки raw runtime SQL доказывают отсутствие независимого DML обхода, scope/shape enforcement и атомарный command path. Достоверность actor против HTTP-клиента обеспечивают действующие cookie auth + live membership + серверный WorkspaceContext; не подмена полей клиента. Тесты поддельных HTTP actor/correlation обязательны. DB administrator не входит в guarantee.

Сохранить фактическую M1.2 admission model: AuthService.workspace удерживает shared session admission во внешней auth transaction до завершения отдельного tenant UOW. Receipt/account/Audit находятся на ОДНОМ tenant connection/transaction. Не объявлять внешнюю auth и tenant transaction одним SQL connection, не перепроектировать принятое auth admission для M1.3. Подробную совместимость lock ordering описать и отдать C2 на проверку до DDL.

## D-11 / G-05 — ровно один CAS transport

Вместо рекомендованного C2 If-Match выбирается более узкий существующему typed body подход: **expected_version в JSON — единственный CAS input**. Это выбор одной из исходных альтернатив, не ослабление CAS. Exact body: `{expected_version: decimal-string, contact_display_name: string}`. Header Idempotency-Key обязателен, CSRF/Origin по принятому протоколу. If-Match в этом endpoint не поддерживается и при наличии отвергается 422 INVALID_REQUEST; его нельзя молча игнорировать/использовать вместо поля. ETag/428/412 ветки сейчас не вводятся.

Missing/empty/extra body field, malformed version/key/header, null/empty name → 422 до claim. Stale → 409 STALE_STATE; different fingerprint → 409 IDEMPOTENCY_KEY_CONFLICT. Нормализованный no-op/replay — по D-04. Success body immutable metadata, GET — текущее значение; новый UI не изображает replay исторического результата как актуальный контакт. Разделить safe 404 отсутствующего собственного account от permission denial, не раскрывая foreign object. Нельзя выводить DB exception/parameters при overflow/CHECK failure.

## D-12 / G-06 — отсутствие данных не равно истечению подписки

C1 должен заменить расплывчатую общую 503 ветку на точные DTO/error/reason tables:
- authenticated/authorized OWNER + корректно provisioned state, но нет текущего interval (есть валидная история/future interval) → 200 с availability INACTIVE, subscription=null и SUBSCRIPTION_INACTIVE;
- finite expired/future mode → 200 с явным mode_active=false, обычные решения SERVICE_MODE_INACTIVE; никакого fallback NORMAL;
- missing account/mode/вообще subscription history → 503 BILLING_STATE_UNAVAILABLE, state_reason BILLING_STATE_MISSING;
- противоречивые/двойные effective rows → 503 с BILLING_STATE_INVALID;
- missing/unsealed/invalid typed referenced revision → 503 с REVISION_INVALID;
- missing capability key на валидном snapshot → DISABLED/NOT_ENTITLED, не 503;
- archived plan не инвалидирует SEALED pinned revision;
- DB unreadable → безопасная 503, без raw exception.

Приоритет structural failure → subscription inactive → mode inactive → missing capability/value evaluation/mode restriction определить явно, с таблицей всех criticality/value states. Если несколько structural failures, выбрать фиксированный documented reason precedence. Это функция будущего read/decider, не разрешение implementation сейчас. Все auth/security/существующие Business read paths независимы от billing; administrative contact command permission-gated, не subscription-gated.

## D-13 / G-07 — cursor не credential

Три новых endpoint из предложения сохраняются, без четвёртого generic API. Audit: order `(occurred_at DESC,id DESC)`, predicate `(occurred_at,id) < (:at,:id)`, default limit=25, диапазон 1..100.

Для минимального LOCAL/TEST — opaque versioned base64url cursor с bounded decoded JSON (encoded <=1024 ASCII bytes), exact fields `{v, endpoint, workspace_id, direction, occurred_at, id}`. v=1, endpoint=AUDIT_EVENTS, direction=DESC. Структурная validation server-side; workspace сравнить с trusted context, anchor tuple проверить только внутри разрешённого Workspace. Invalid/foreign/nonexistent anchor → safe 422 INVALID_REQUEST. Ни подписи/новой secret infrastructure, ни обещания tamper-proof token не вводить: курсор только выбирает позицию и не предоставляет authority. Изменение на другой существующий разрешённый anchor не повышает доступ. Никакого cross-Workspace lookup, без arbitrary filters. Timestamp aware/canonical UTC, UUID validated; full shape/encoding должен быть описан в R2. Это keyset pagination, не обещание frozen snapshot всего Audit между HTTP-страницами.

## Required future proof / критерий окончания R2

В R2 для каждого OPEN-01…07 и G-01…07 есть точная disposition и ссылка на исправленный раздел. Не оставлять конкурирующие семи-/восьмитабличные inventory, function-or-SELECT, email optional, два CAS источника, независимую criticality или старый код IDEMPOTENCY_CONFLICT в нормативной части. Исторический rejected вариант допустим только явно как история.

Будущий proof matrix включает DB metadata/roles/RLS/context/FKs, finite/non-overlap two-connection races, seal vs late INSERT races, partial revision rejection, coherent snapshot, decimal serialization, same-key replay after later contact changes, changed-key conflict, CAS race, no-op, Audit/receipt rollback, live authorization на replay и отсутствие raw PII в evidence. Fresh install / preflight+0003 upgrade / replay / disposable downgrade-reupgrade; старые 0001–0003 и accepted auth tests сохраняются. Новая M1.3 не объявляется реализованной даже при зелёном docs-only CI.

## Отдельная maintenance линия M1.2

PR #10, head `f05abe2f64bfe81f2db57b450440133306410a60`, tree `721b205f2cdc8ba8405ef47d001f2e4e82e286f9`: C0 принял шестистрочную test-only дельту C0-M1.2-E2E-01. Run 35421203125: foundation/browser/clean-source SUCCESS, 246 cases. Это не M1.3 evidence. C0 разрешил пользователю обычный merge этого exact PR #10 при неизменном base `28c289ce…` и выполненных repository protections; actual merge/main CI пока не проверены и SHA не предсказан. PR #9 пока не сливать. C1 не cherry-pick-ит/восстанавливает test patch в контрактную ветку и не выдаёт тестовый PR за часть своей реализации.

## Источники и границы собственной проверки C0

Прочитаны полный исходный M1_3_CONTRACT и присланный отчёт C2; Spec §§2.4–2.9, 3.2, 3.12–3.15, 15, 17.2/17.4/17.9–17.13, 18.4; ADR-099–107/109/124/126/182/270; M1.3 и DoD из 09_IMPLEMENTATION_PLAN; AGENTS, IMPL-001, реальный bootstrap, TenantDatabase и AuthService.workspace. Исходники из сохранённых SHA/tree-проверенных CI archives; refs PR #9/#10/main повторно прочитаны через GitHub.

Внешняя проверка механизмов (не проектные решения и не execution proof): PostgreSQL 18 btree-gist, transaction-iso, ddl-rowsecurity, sql-createfunction, functions-datetime. URL:
- https://www.postgresql.org/docs/18/btree-gist.html
- https://www.postgresql.org/docs/18/transaction-iso.html
- https://www.postgresql.org/docs/18/ddl-rowsecurity.html
- https://www.postgresql.org/docs/18/sql-createfunction.html
- https://www.postgresql.org/docs/18/functions-datetime.html

Новых DDL/PostgreSQL/Vitest/Playwright запусков C0 не выполнял. C2 result — supplied independent review, не локальное исполнение C0. C5 isolated Chromium probe и reported npm audit findings — отчёт исполнителя; raw probe/audit logs C0 не получил и не заявляет независимую проверку. Два reported moderate dependency findings требуют отдельного конкретного advisory triage до production; не дают разрешения менять lockfiles в текущей test/docs задаче и не превращаются в заявление «зависимости безопасны».


## C0 — PR #10 post-merge и восстановление передачи R2 (2026-09-19)

C0 проверил фактический merge PR #10: `049b212f135f09c025d2f81badc810fa7c2c9d13`, tree `721b205f2cdc8ba8405ef47d001f2e4e82e286f9`, push/main run `35422383973`, attempt 1, SUCCESS. Foundation job `105842308563`: 105 Python + 105 PostgreSQL + 30 frontend; browser job `105842308489`: 6 passed. Оба clean-source gates PASS. ZIP artifact `10578235228`, SHA-256 `69b5d0ceb07d709a2121c38c1a3c09c022b5c8a9ce7a012571514194501e8307`; 109 файлов/modes точно совпали с ранее принятым maintenance tree. Это проверенное C0 GitHub CI evidence, не новый локальный application run.

`C0-M1.2-E2E-01` — CLOSED / INTEGRATED / VERIFIED в границах этого исправления. M1.2 сохраняет приёмку; исторический исходный base M1.3 остаётся `28c289ce6f77e33676cfa416585cc0e20c0be4e3`. Новый main не является разрешением DDL или доказательством M1.3.

R2 C1 ещё не получена. Сообщение Codex «не удалось создать продолжение» не доказывает контекстный лимит, исчерпание quota или safety block. C0 заменяет способ передачи: новая cloud-задача с PR #9 как контекстом; один временный текстовый файл `docs/tasks/C1_M1_3_R2_RESUME.txt` допускается только для переноса полного поручения и удаляется из итогового tracked tree. Архитектурные решения D-01…D-13 не меняются; итоговая дельта от reviewed `f4fb513…` — только реестр, C0 disposition и контракт R2. Без merge/rebase/force-push, нового конкурирующего PR или изменения кода. Runtime M1.3 остаётся NOT AUTHORIZED; контракт R2 ждёт C0/C2 review.
