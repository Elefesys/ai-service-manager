# M1.3 R2 — pre-DDL contract: local Entitlements и Audit

Дата редакции: 2026-09-19. Владелец предложения: C1. Исходный принятый base:
`28c289ce6f77e33676cfa416585cc0e20c0be4e3`, tree
`0df4c1b9a2e6922f742ebe459e46dd93d2c2959f`. Статус:
**CONTRACT R2 PROPOSED / AWAITING C0-C2 REVIEW**.

Это единое исправленное предложение по C0 D-01…D-13 после C2
`CHANGES_REQUESTED`, не ADR, не принятый канон и не свидетельство реализации.
DDL/runtime/frontend/generated contracts не разрешены; successor `0003` не
назначен. `0001`–`0003` неизменяемы. Только отдельное решение C0/C2 после review
может выдать implementation.

## 1. Scope и инварианты

- Workspace — единственная tenant boundary. `workspace_id` из route — selector,
  но не authority; membership и permissions проверяются из trusted server context.
- Подписка принадлежит Workspace. Entitlement не является permission и не
  ослабляет auth, RLS или safety policy; критические факты не выводятся LLM.
- Runtime использует локальный pinned `SEALED` revision; provider/HTTP не входит
  в read path. Pilot — `TRIALING/TRIAL` или `ACTIVE/COMPED`, без fake paid state.
- Billing lifecycle, service mode и security/continuity — разные состояния.
- Изменение контакта, receipt и фактический Audit атомарны в одной короткой
  tenant transaction; Audit — не Outbox/Jobs/technical log.
- `asm_runtime` не owner/SUPERUSER/BYPASSRLS. Context только transaction-local и
  XID-fenced. Внешняя auth transaction M1.2 и tenant UOW — разные connections:
  `AuthService.workspace` удерживает shared session-admission lock, пока отдельный
  tenant UOW выполняет команду. Этот порядок не меняется и до DDL проверяется C2.

Вне M1.3: provider IDs, checkout, prices, invoices/webhooks, paid billing,
usage/meters/quotas, overrides, client payments, generic commands, Jobs/Outbox,
Ops writer, реальные контакты/лимиты/длительности и production activation.

## 2. Exact inventory и ownership

Ровно восемь таблиц:

1. `platform.saas_plans`;
2. `platform.saas_plan_revisions`;
3. `platform.plan_entitlements`;
4. `platform.workspace_billing_accounts`;
5. `platform.workspace_subscriptions`;
6. `platform.workspace_service_modes`;
7. `app.audit_events`;
8. `platform.billing_contact_command_receipts`.

Первые три — общий несекретный каталог без RLS. Последние пять Workspace-owned
независимо от schema: `workspace_id NOT NULL`, tenant-safe composite keys/FKs,
`ENABLE/FORCE RLS`, runtime `USING` и `WITH CHECK` по transaction-fenced
`app.current_workspace_id()`, отдельная migrator policy, `ON DELETE RESTRICT`.
Вариант C2 с Workspace billing в `app` рассмотрен, но C0 выбрал `platform` согласно
Spec §§2.4, 3.2. Schema не даёт authorization или RLS bypass.

Все UUID PK используют `pg_catalog.uuidv7()`, timestamps — `timestamptz`, server
time — `CURRENT_TIMESTAMP`; обязательные timestamps конечны. Owner —
`asm_migrator`. Имена enum-подобных значений не длиннее 64 bytes.

### 2.1 Общий каталог

`platform.saas_plans`: `id` PK; `code` unique, ASCII lower identifier 1..64;
`display_name` 1..200; `status ACTIVE|ARCHIVED`; `created_at`. Архивация не
инвалидирует pinned revision; runtime DML/delete отсутствуют.

`platform.saas_plan_revisions`: `id` PK; `plan_id` FK RESTRICT; `revision integer
> 0`, unique `(plan_id,revision)`; `publication_state DRAFT|SEALED`;
`published_at` nullable; `created_at`; unique `(id,publication_state)`. CHECK:
`DRAFT` iff `published_at IS NULL`, `SEALED` iff finite `published_at IS NOT NULL`.
Переход только `DRAFT -> SEALED` один раз; иные UPDATE/DELETE запрещены.

`platform.plan_entitlements`: `(plan_revision_id,capability_key)` PK, parent FK
RESTRICT; key `[a-z][a-z0-9_.:-]{0,127}`; `value_kind BOOLEAN|INTEGER`;
ровно одно из `enabled boolean`/`limit_value bigint >= 0`; `criticality
ESSENTIAL|STANDARD|EXPENSIVE_OPTIONAL`; `created_at`. Criticality хранится только
здесь. INSERT разрешён provisioner только в DRAFT; UPDATE/DELETE и перенос между
revision запрещены.

Seal и INSERT entitlement блокируют одну parent revision row, поэтому гонка
late INSERT/seal сериализуется. Перед seal проверяется полный manifest. Canonical
строка каждой записи: UTF-8
`key + "\t" + kind + "\t" + ("true"|"false"|canonical unsigned decimal) +
"\t" + criticality + "\n"`; строки сортируются по UTF-8 bytes key, затем
конкатенируются. Проверяются exact count `5` и SHA-256
`2aed3e0812691c4546997692e664660c7e328783422ae824c8279bd2cef963cc` от bytes.
Ожидаемый digest вычисляет provisioner из следующего exact manifest и передаёт
seal operation; DB заново строит тот же representation и сравнивает count/digest:

| key | kind/value | criticality |
|---|---|---|
| `test.m1_3.essential_true` | BOOLEAN `true` | ESSENTIAL |
| `test.m1_3.standard_true` | BOOLEAN `true` | STANDARD |
| `test.m1_3.standard_false` | BOOLEAN `false` | STANDARD |
| `test.m1_3.expensive_positive` | INTEGER `3` | EXPENSIVE_OPTIONAL |
| `test.m1_3.expensive_zero` | INTEGER `0` | EXPENSIVE_OPTIONAL |

Это TEST-only, не production defaults. Создание revision, manifest и seal — одна
provisioning transaction. После seal set замкнут. Администратор DDL/superuser вне
гарантии supported writes.

### 2.2 Workspace billing

`platform.workspace_billing_accounts`: `workspace_id` PK/FK Workspace RESTRICT;
`id` UUID, unique `(workspace_id,id)`; `contact_display_name`; `version bigint >
0 DEFAULT 1`; `created_at`, `updated_at`. Никакого email. Display name — potentially
personal data. Нормализация: trim только U+0020 по краям, без case-fold/Unicode
normalization; после trim 1..200 Unicode code points и UTF-8 <=800 bytes; NUL,
C0 U+0000..001F и DEL U+007F запрещены. App и DB command применяют одинаково.

`platform.workspace_subscriptions`: composite PK `(workspace_id,id)`;
`workspace_id` FK; `plan_revision_id`; `required_publication_state` с CHECK
`='SEALED'`; composite FK `(plan_revision_id,required_publication_state)` к
revision `(id,publication_state)` RESTRICT; `status TRIALING|ACTIVE`;
`funding_mode TRIAL|COMPED`, только пары `TRIALING/TRIAL`, `ACTIVE/COMPED`;
finite non-null `effective_from/effective_until`, `<`; `version > 0`;
timestamps. Только append; исправляющего runtime writer нет.

Immediate NOT DEFERRABLE GiST exclusion запрещает пересечение для одного
Workspace: `workspace_id WITH =`,
`tstzrange(effective_from,effective_until,'[)') WITH &&`. Соседние интервалы
допустимы; правило независимо от status.

`platform.workspace_service_modes`: `workspace_id` PK/FK; `id`, unique composite;
`mode`, `reason_code`, finite `effective_from`, nullable finite `effective_until`
и `<` при non-null; `version > 0`; timestamps. Exact pairs:
`NORMAL/PROVISIONED_LOCAL`, `GRACE/TEST_GRACE`, `LIMITED/TEST_LIMITED`,
`SUSPENDED/TEST_SUSPENDED`. LOCAL provisioner создаёт NORMAL; прочие пары — только
explicit migrator TEST fixtures. Runtime только читает, history/writer отсутствует.
Active iff `from <= db_now AND (until IS NULL OR db_now < until)`; future/expired
никогда не fallback в NORMAL.

### 2.3 Audit и command receipt

`app.audit_events`: composite PK `(workspace_id,id)`; `occurred_at`;
`actor_kind USER_ACCOUNT|LOCAL_PROVISIONER`; nullable `actor_user_account_id`;
`correlation_id`; `event_type`; `object_type`; `object_id`; `object_version > 0`;
`payload jsonb`; index `(workspace_id,occurred_at DESC,id DESC)`.

USER_ACCOUNT требует actor id и composite FK
`(workspace_id,actor_user_account_id)` к membership RESTRICT; revocation меняет
status, не удаляет history. LOCAL_PROVISIONER требует null actor. Exact events:
`BILLING_ACCOUNT_CONTACT_UPDATED`, `WORKSPACE_BILLING_PROVISIONED`; object type
только `WORKSPACE_BILLING_ACCOUNT`, composite object FK к account. Payload — JSON
object, `octet_length(payload::text) <= 4096` bytes в UTF-8 PostgreSQL
representation. Contact event shape ровно
`{"changed_fields":["contact_display_name"]}`. Raw name/email, fingerprints,
keys, credentials, cookies/headers, SQL params/exceptions запрещены.

`platform.billing_contact_command_receipts`: composite PK `(workspace_id,id)`;
unique `(workspace_id,operation,idempotency_key)`; `operation` ровно
`UPDATE_BILLING_CONTACT`; key ASCII `[A-Za-z0-9._:-]{1,128}` без trim;
`request_fingerprint bytea` length 32; `expected_version bigint > 0`;
`billing_account_id` composite FK; `status IN_PROGRESS|SUCCEEDED`;
`result_version bigint`; `result_outcome UPDATED|NOOP`; `created_at`,
`completed_at`. State checks require result/completed only for SUCCEEDED.
Supported path никогда не commits IN_PROGRESS; SUCCEEDED immutable.

LOCAL/TEST Audit/receipts append-only до teardown disposable environment. Это не
production indefinite retention. Production duration/privacy workflow остаются
OPEN; purge API не проектируется.

## 3. DB roles, RLS и surfaces

| object | `asm_runtime` |
|---|---|
| three catalog tables | `SELECT` exactly |
| account/subscription/mode/Audit | `SELECT` under FORCE RLS |
| receipt | no direct privileges |
| account/Audit mutation | no direct DML |
| contact command | EXECUTE exact function signature |
| plans/subscriptions/modes | no INSERT/UPDATE/DELETE |

Catalog read is an invoker-right repository with one parameterized fixed-shape SQL
statement; there is no read function alternative or generic catalog endpoint.
The statement starts from RLS-filtered Workspace state and joins the pinned SEALED
revision. Catalog SELECT means it is not secret from a DB-credential holder;
application endpoints remain permission-gated.

The only runtime write surface is:

```text
platform.update_billing_contact(
  expected_version bigint,
  contact_display_name text,
  idempotency_key text
)
```

It is `SECURITY DEFINER`, owner `asm_migrator`, search path exactly
`pg_catalog, pg_temp`, all custom references schema-qualified, no dynamic SQL;
`PUBLIC EXECUTE` revoked and exact `asm_runtime` EXECUTE granted atomically.
Workspace/actor/correlation are never arguments: the function validates the
XID-fenced context, actor kind and live ACTIVE OWNER membership. Invalid fence or
permission fails closed. It derives Audit from actual OLD/RETURNING NEW. It never
commits or catches Audit failure.

GUC/XID fencing scopes a trusted backend-issued transaction but is not a
cryptographic identity against an attacker already holding arbitrary
`asm_runtime` SQL credentials. Cookie auth/live membership protects against the
HTTP caller; DB administrator is outside the guarantee.

Future `btree_gist` is installed into `extensions` by existing bootstrap/admin,
not by `asm_migrator`. Existing-0003 databases require idempotent admin preflight.
The migration first checks installed extension version, namespace and UUID
opclass, and stops before partial DDL if absent; no weaker fallback. Exact version
and pinned-image/managed-SKU availability must be proven before implementation.
No permanent database CREATE/SUPERUSER/ownership is added. Downgrade does not
remove extension, roles or pgvector 0.8.6.

## 4. Permissions, services и coherent read

Новые permissions: `billing:read`, `billing:manage`, `audit:read`, все только
OWNER. ADMIN/PROVIDER не наследуют их из tenancy permissions. Anonymous — 401.
Plan/revision/subscription/mode writes и arbitrary Audit запрещены всем HTTP roles.
LOCAL/TEST provisioner — отдельная environment-gated identity, не HTTP role.

```text
BillingRepository.get_snapshot(uow) -> BillingSnapshot | BillingStateFailure
BillingService.update_contact(uow, expected_version, normalized_name, key)
  -> ContactCommandResult
AuditRepository.list_events(uow, cursor, limit) -> AuditPage
EntitlementService.decide(snapshot, CapabilityKey) -> EntitlementDecision
```

`get_snapshot` — один fixed SQL statement (CTE/join/aggregation допустимы), в нём
же `CURRENT_TIMESTAMP`, account/history/current interval/mode/SEALED catalog и
entitlements. Несколько SELECT при READ COMMITTED не выдаются за coherent snapshot;
isolation существующего UOW не меняется. `decide` не принимает criticality или
db_now. Capability/criticality от UI/LLM не авторитетны.

Decision precedence: (1) structural failure; (2) subscription inactive; (3) mode
inactive; (4) missing capability; (5) service-mode restriction; (6) typed value.
Structural precedence при нескольких дефектах: `BILLING_STATE_MISSING`, затем
`BILLING_STATE_INVALID`, затем `REVISION_INVALID`, затем `DATABASE_UNAVAILABLE`.
Ответ наружу всегда безопасен и без DB details.

| состояние | HTTP/snapshot | decision |
|---|---|---|
| account/mode/history missing | 503 `BILLING_STATE_UNAVAILABLE`, `BILLING_STATE_MISSING` | unavailable |
| duplicate/contradictory effective rows | 503, `BILLING_STATE_INVALID` | unavailable |
| missing/unsealed/invalid typed revision | 503, `REVISION_INVALID` | unavailable |
| DB unreadable | safe 503, `DATABASE_UNAVAILABLE` | unavailable |
| no current subscription, but valid past/future history | 200 `availability=INACTIVE`, `subscription=null` | DISABLED/`SUBSCRIPTION_INACTIVE` |
| expired/future finite mode | 200 `mode_active=false` | DISABLED/`SERVICE_MODE_INACTIVE` |
| missing key in valid snapshot | 200 | DISABLED/`NOT_ENTITLED` |

Archived plan does not invalidate its SEALED pinned revision. For an active mode:

| mode | allowed criticalities |
|---|---|
| NORMAL | ESSENTIAL, STANDARD, EXPENSIVE_OPTIONAL |
| GRACE | ESSENTIAL, STANDARD |
| LIMITED | ESSENTIAL |
| SUSPENDED | none |

Disallowed category gives DISABLED/`SERVICE_MODE_RESTRICTED`. Allowed BOOLEAN true
gives ENABLED; false gives DISABLED/`NOT_ENTITLED`. INTEGER gives LIMIT with
canonical decimal string, including `"0"`; it is not a boolean. OVER_LIMIT and
usage are future and never returned now. Security/session/Business continuity and
contact administration are not billing-gated, while retaining auth/permission/
CSRF controls.

## 5. Atomic contact command и replay

Admission/CSRF/Origin precede domain validation. Exact request body has no extra
fields:

```json
{"expected_version":"7","contact_display_name":"Example name"}
```

All new M1.3 bigint JSON values are canonical base-10 strings in signed bigint
range; old M1.2 DTOs unchanged. Exactly one `Idempotency-Key` header is required.
`If-Match` is unsupported and its presence is 422 `INVALID_REQUEST`.

Fingerprint v1 is SHA-256 over canonical UTF-8 JSON with sorted keys and no
insignificant whitespace:
`{"contact_display_name":<normalized JSON string>,"expected_version":<decimal
JSON string>,"operation":"UPDATE_BILLING_CONTACT","workspace_id":<trusted UUID
lowercase string>}`. Key/fingerprint are not logged.

Within one tenant connection/transaction: validate; compute fingerprint; claim
unique `(workspace,operation,key)` before CAS; authorize live; replay same
SUCCEEDED fingerprint without UPDATE/Audit; reject changed fingerprint; lock
account; compare version before no-op; run CAS/change if needed; insert exactly
one Audit only for actual change; finalize receipt; commit; then respond.
Concurrent same-key loser waits for unique row/lock and reads the committed receipt
in a fresh statement snapshot. Different keys/same version yield one changing CAS
winner. Stale/no-op failures leave no receipt/Audit. Audit error rolls back claim
and account. A same-version normalized no-op leaves version/updated_at unchanged,
creates SUCCEEDED/NOOP receipt, no Audit. Successful replay precedes current stale
check but still requires current authorization.

Success is 200 with immutable original metadata only:

```json
{"workspace_id":"<uuid>","billing_account_id":"<uuid>","receipt_id":"<uuid>","result_version":"7","outcome":"NOOP","completed_at":"<UTC timestamp>"}
```

Current contact is read only by authorized GET. Errors: malformed/missing/extra
input or header 422 `INVALID_REQUEST`; stale 409 `STALE_STATE`; changed fingerprint
409 `IDEMPOTENCY_KEY_CONFLICT`; absent own account safe 404 `NOT_FOUND`;
authentication 401 and permission/cross-Workspace 403 without existence leak.
Overflow/CHECK/DB parameters and raw exceptions never escape.

## 6. HTTP/DTO и Audit pagination

Ровно три endpoints:

| endpoint | permission | result |
|---|---|---|
| `GET /api/workspaces/{workspace_id}/billing` | `billing:read` | 200 snapshot/decisions or safe 503 table above |
| `PUT /api/workspaces/{workspace_id}/billing/contact` | `billing:manage` + CSRF/Origin + key | §5 result/errors |
| `GET /api/workspaces/{workspace_id}/audit-events?cursor=&limit=` | `audit:read` | Audit page |

No generic fourth endpoint. Audit ordering `(occurred_at DESC,id DESC)`, next-page
predicate `(occurred_at,id) < (:at,:id)`, default 25, range 1..100. Cursor is
unpadded base64url of UTF-8 canonical compact JSON, encoded <=1024 ASCII bytes,
exact fields:

```json
{"v":1,"endpoint":"AUDIT_EVENTS","workspace_id":"<uuid>","direction":"DESC","occurred_at":"<canonical UTC RFC3339 with Z>","id":"<uuid>"}
```

Reject duplicate/extra/missing/wrong-type fields, invalid base64/UTF-8/JSON,
noncanonical timestamp/UUID, wrong version/endpoint/direction/workspace, and
nonexistent/foreign anchor with safe 422 `INVALID_REQUEST`. Workspace is compared
to trusted context; anchor lookup occurs only inside authorized Workspace—never a
cross-Workspace probe. Cursor is position, not credential/signature/tamper-proof
promise; choosing another permitted anchor adds no authority. No arbitrary filters
and no frozen cross-request history guarantee.

## 7. Provisioning, rollback и deployment prerequisites

LOCAL/TEST provisioner takes explicit pilot interval timestamps; it does not invent
a duration. One transaction creates account, DRAFT revision/complete TEST manifest,
seals it, appends finite subscription, creates NORMAL/PROVISIONED_LOCAL mode and
`WORKSPACE_BILLING_PROVISIONED` Audit as LOCAL_PROVISIONER. Partial manifest/seal
or Audit failure rolls all back. Provisioning is idempotent only by an explicitly
specified future implementation contract; no fake account fallback.

Fresh install: admin installs/verifies extension, then assigned migration creates
all eight objects/grants/policies atomically. Existing 0003: admin preflight first,
migration prerequisite check before any domain DDL. Replay is no-op. Disposable
downgrade removes only the M1.3 slice in reverse dependency order; it does not
delete btree_gist/pgvector/roles or mutate 0001–0003. Re-upgrade reprovisions only
synthetic data. Production rollback/retention and extension availability are not
claimed.

Unresolved prerequisites before implementation authorization: verify exact
`btree_gist` version/UUID opclass in pinned image and target managed SKU; C2 approve
lock ordering and migration revision/predecessor; C0 decide production retention/
privacy and real catalog/durations separately. None is evidence from this doc.

## 8. Future proof matrix

- metadata/owners/grants, FORCE RLS/policies/context fence, composite FKs and raw
  runtime SQL negatives; foreign Workspace and spoofed HTTP actor/correlation;
- fresh install, 0003+admin-preflight upgrade, missing prerequisite with zero
  partial DDL, replay, disposable downgrade/re-upgrade, originals unchanged;
- finite/infinity checks and two-connection adjacent/non-overlap/overlap races;
- DRAFT seal versus late INSERT, incomplete/wrong manifest digest, immutable
  SEALED set, subscription-to-DRAFT rejection;
- one-statement coherent snapshot, interval boundaries, archived plan, every
  missing/invalid precedence, five TEST keys plus missing key, every mode/value/
  criticality pair, bigint boundary/decimal serialization;
- command validation, live authorization on first call and replay, same-key replay
  after later contact changes, changed-key fingerprint conflict, concurrent same/
  different keys, stale-before-no-op, normalized no-op, overflow redaction;
- forced account/Audit/receipt rollback, exactly one truthful Audit, durable actor
  FK after revocation, 4096-byte DB boundary, absence of raw personal data in
  Audit/receipt/log/evidence;
- cursor bounds/shape/scope/anchor/DESC keyset, inserts between pages without
  frozen-snapshot claim; exact three endpoints and permission negatives;
- accepted M1.1/M1.2 PostgreSQL/auth/frontend regression remains green. A docs-only
  CI cannot prove future M1.3 tables or atomicity.

No local PostgreSQL/Vitest/Playwright result is claimed by this proposal.

## 9. Disposition mapping

| finding | C0 decision | normative sections |
|---|---|---|
| OPEN-01 | D-01: platform billing, app Audit, exact 8 tables | §§2, 2.3 |
| OPEN-02 | D-02: finite immediate GiST exclusion; admin extension preflight | §§2.2, 3, 7 |
| OPEN-03 | D-03: disposable retention; exact jsonb bytes/PII/FKs | §§2.3, 7 |
| OPEN-04 | D-04: narrow receipt and replay-before-CAS | §§2.3, 5 |
| OPEN-05 | D-05: catalog criticality, fixed SQL snapshot, TEST values | §4 |
| OPEN-06 | D-06: display name only and identical normalization | §§2.2, 5 |
| OPEN-07 | D-07: SELECT-only mode, exact fixture pairs/no fallback | §§2.2, 4 |
| G-01 | D-08: locked DRAFT→SEALED manifest and sealed composite FK | §§2.1, 7 |
| G-02 | D-09: invoker fixed SQL + exact catalog SELECT grants | §§3, 4 |
| G-03 | D-10: one typed SECURITY DEFINER command, no direct DML | §§3, 5 |
| G-04 | D-03/D-10: truthful bounded Audit and actor/object FKs | §§2.3, 3, 5 |
| G-05 | D-11: expected_version only in body; exact errors | §5 |
| G-06 | D-12: inactive vs missing/invalid state and precedence | §4 |
| G-07 | D-13: scoped bounded cursor, not authority | §6 |

Отклонения от рекомендаций C2 намеренны: C0 выбрал `platform` placement вместо
`app`; extension устанавливает admin/bootstrap, не migrator; CAS имеет один body
source, не If-Match; write surface — одна narrow function, не direct runtime DML.
Все findings считаются **addressed in proposal, pending C0/C2 review**, а не CLOSED.

## 10. Историческая пометка

R1 seven-table proposal и альтернативы function-or-SELECT, optional email,
caller-supplied criticality, dual CAS и generic runtime Audit write отвергнуты.
Они остаются только в Git history и не являются нормативной альтернативой R2.
