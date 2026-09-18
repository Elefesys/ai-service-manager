# M1.3 — pre-DDL contract: local Entitlements и Audit

Дата предложения: 2026-09-18. Владелец предложения: C1. Исходный принятый base:
`28c289ce6f77e33676cfa416585cc0e20c0be4e3`, tree
`0df4c1b9a2e6922f742ebe459e46dd93d2c2959f`. Статус документа:
**CONTRACT PROPOSED / AWAITING C0-C2 REVIEW**.

Этот документ — техническое предложение внутри одной задачи M1.3, а не второй
реестр, ADR, разрешение DDL или свидетельство реализации. Слова `PROPOSED` и
`OPEN` ниже не меняют LOCKED-решения. Текущий этап изменяет только этот Markdown.
Revision после текущего `0003` назначают C0/C2; `0001`–`0003` неизменяемы.

## 1. Scope, этапы и traceability

### 1.1 Принятые инварианты

- Workspace — единственная tenant boundary; подписка принадлежит Workspace, не
  глобальному UserAccount. Caller-supplied `workspace_id` — лишь selector.
- `SaaSPlan -> immutable SaaSPlanRevision -> PlanEntitlements`; приложение не
  ветвится по имени плана. Entitlement не является permission и не ослабляет
  application authorization, RLS или safety policy.
- Canonical entitlement lookup локален. Billing provider не находится на runtime
  path. Pilot представлен обычным `TRIALING` либо `ACTIVE + COMPED`, без скрытого
  test/pilot bypass и без фиктивного результата оплаты.
- Billing lifecycle и `WorkspaceServiceMode` — разные состояния. Изменение
  тарифа/лимита не удаляет существующие entities.
- Критические mutable rows используют version/CAS. Связанные domain mutation и
  `AuditEvent` атомарны в одной короткой PostgreSQL transaction. Audit не равен
  Outbox, SecurityEvent или technical log.
- Runtime — `asm_runtime`: не SUPERUSER, не BYPASSRLS, не владелец tenant tables.
  Tenant context устанавливается из проверенного server actor только внутри
  transaction; migrator и runtime остаются раздельными.

### 1.2 Границы одной M1.3

1. **Этот contract stage:** схема, permissions/grants, policy, API/DTO и proof
   plan. Никакого DDL/runtime/UI/test code.
2. **Последующий backend/DB stage только после C0/C2 review:** назначенная
   migration; typed repositories/services; LOCAL/TEST provisioning; real
   PostgreSQL и unit/contract tests; generated contracts только в этом stage.
3. **Последующий consumer stage:** минимальная owner read view C5 через принятый
   backend; browser proof. UI не пишет canonical plan/entitlement/COMPED state.
4. **C0/C8 acceptance:** один exact head, full foundation/browser regression,
   artifact/source checks. Только C0 назначает INTEGRATED/VERIFIED.

Сознательно будущий scope: payment methods, checkout/provider customer refs,
invoices/webhooks/reconciliation, prices, paid status, UsageEvent/Aggregate,
meters, overrides, quotas/reservations, AI/provider cost, future Clients/Jobs,
Platform Ops editing and production enablement. Они не получают пустых tables или
adapters в M1.3.

### 1.3 Матрица трассировки

| Требование | Канон | PROPOSED компонент | Будущее доказательство |
|---|---|---|---|
| Workspace billing boundary | Spec §§2.1, 15.1–15.2; ADR-002/099/100 | workspace-scoped billing account/subscription/mode | A→B RLS, composite FK, no UserAccount subscription |
| Defense in depth | Spec §§2.5–2.8, 17.4, 17.13; ADR-005 | existing tenant UOW + narrow repositories/grants | runtime-role and foreign-workspace negatives |
| Versioned capabilities | Spec §15.4; ADR-102 | plan, immutable revision, typed entitlement rows/service | immutability, value-shape and no-plan-name tests |
| Separate service mode | Spec §§15.5–15.7; ADR-103 | distinct mode row + policy truth table | status×mode×criticality table tests |
| Local provider-independent runtime | Spec §15.11; ADR-106 | one local snapshot read; no HTTP adapter | network-free integration proof |
| Pilot TRIALING/COMPED | Spec §§23.15, 24.5; ADR-182/270 | explicit status/funding checks | ordinary-state fixture and invalid-pair tests |
| CAS and atomicity | Spec §§3.12–3.13, 18.3; ADR-126 | version predicates; mutation+audit transaction | stale/concurrent/forced-rollback tests |
| Audit baseline | Spec §§1.7, 3.14, 17.2, 17.12, 18.3, 24.5; ADR-005 | workspace AuditEvent + controlled payload | real actor/correlation, redaction and rollback |
| Owner visibility, Console/Ops split | Spec §§23.13–23.14; ADR-107 | owner snapshot endpoint; no generic Ops CRUD | permission/API/browser negatives |

Related ADR-101/104/105 and Spec §§15.3, 15.8–15.10 constrain future
payment/usage/quota work; they do not authorize those tables now.

## 2. PROPOSED minimal schema

Names and exact placement are proposals pending OPEN-01. Every UUID primary key
uses `pg_catalog.uuidv7()`. All timestamps are `timestamptz`; DB
`CURRENT_TIMESTAMP` is authoritative. All referenced Workspace rows use
`ON DELETE RESTRICT`. No universal soft delete is introduced.

### 2.1 Global catalog (`platform`)

#### `platform.saas_plans`

Purpose: stable non-secret product identity, not behavior by plan name.

- `id uuid PRIMARY KEY DEFAULT pg_catalog.uuidv7()`;
- `code text NOT NULL UNIQUE`, trimmed, bounded 1–64, machine identifier used only
  for catalog/provisioning/display lookup, never an authorization branch;
- `display_name text NOT NULL`, trimmed, 1–200;
- `status text NOT NULL CHECK IN ('ACTIVE','ARCHIVED')`;
- `created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP`.

Owner: `asm_migrator`. Global catalog, so no Workspace RLS. Runtime receives no
blanket table grant; read occurs through the reviewed narrow snapshot function or
repository surface in §3.3. Only migrator/provisioning can insert/archive. Delete
is RESTRICT/not granted. Archive does not mutate old revisions.

#### `platform.saas_plan_revisions`

Purpose: immutable version of a plan.

- `id uuid PRIMARY KEY DEFAULT pg_catalog.uuidv7()`;
- `plan_id uuid NOT NULL REFERENCES platform.saas_plans(id) ON DELETE RESTRICT`;
- `revision integer NOT NULL CHECK (revision > 0)` and
  `UNIQUE(plan_id, revision)`; also `UNIQUE(plan_id, id)` for explicit composite
  references if C2 retains both identifiers;
- `published_at timestamptz NOT NULL`, `created_at ... NOT NULL DEFAULT
  CURRENT_TIMESTAMP`; `published_at <= created_at` is **not** assumed because
  controlled fixture import may set both explicitly;
- optional display-only `label text NOT NULL` trimmed 1–200.

No `version`: each row is itself a version. No UPDATE/DELETE grants; a database
immutability trigger rejects UPDATE/DELETE even by ordinary application-facing
functions. Migrator-only destructive downgrade remains disposable TEST behavior,
not production mutation. No RLS; global catalog.

#### `platform.plan_entitlements`

Purpose: typed capabilities/limits pinned to an immutable revision.

- `plan_revision_id uuid NOT NULL REFERENCES
  platform.saas_plan_revisions(id) ON DELETE RESTRICT`;
- `capability_key text NOT NULL`, trimmed lower-case namespace pattern such as
  `[a-z][a-z0-9_.:-]{0,127}`;
- `value_kind text NOT NULL CHECK IN ('BOOLEAN','INTEGER')`;
- `enabled boolean`, `limit_value bigint CHECK (limit_value >= 0)`;
- `criticality text NOT NULL CHECK IN
  ('ESSENTIAL','STANDARD','EXPENSIVE_OPTIONAL')`;
- `created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP`;
- `PRIMARY KEY(plan_revision_id, capability_key)`;
- CHECK exactly one value matches kind:
  `(BOOLEAN AND enabled IS NOT NULL AND limit_value IS NULL) OR
   (INTEGER AND enabled IS NULL AND limit_value IS NOT NULL)`.

No JSON policy blob, price, quota counter or usage projection. Same immutable
protection and grants as revisions. Capability keys and synthetic TEST values
require review; this contract invents no production allowances.

### 2.2 Workspace state (`app`, recommended placement)

Every table below has composite `PRIMARY KEY(workspace_id,id)` (or
`PRIMARY KEY(workspace_id)` for singleton state), `workspace_id NOT NULL`, FORCE
RLS, runtime policy using the existing transaction-fenced
`app.current_workspace_id()`, and a migrator policy. Owner is `asm_migrator`.
The runtime receives only grants needed by narrow repositories (§3.3), not
unqualified platform/auth CRUD.

#### `app.workspace_billing_accounts`

One local billing identity/settings record per Workspace:

- `workspace_id uuid PRIMARY KEY REFERENCES platform.workspaces(id) ON DELETE RESTRICT`;
- `id uuid NOT NULL DEFAULT pg_catalog.uuidv7()`, `UNIQUE(workspace_id,id)`;
- `contact_display_name text NOT NULL` (trimmed, 1–200);
- `contact_email text` nullable, normalized/validated by application and bounded
  to 320; this is PERSONAL_DATA and never copied wholesale to audit/logs;
- `version bigint NOT NULL DEFAULT 1 CHECK (version > 0)`;
- `created_at`, `updated_at` non-null DB timestamps.

No provider customer ID, payment method, country/tax/legal schema or normalized
provider billing status in this local slice. No DELETE. OWNER can read/update only
the contact fields using `billing:manage`; other state is server controlled.

#### `app.workspace_subscriptions`

Workspace interval history, pinned to one immutable revision:

- `workspace_id uuid NOT NULL` + `id uuid NOT NULL DEFAULT uuidv7()`;
- `plan_revision_id uuid NOT NULL REFERENCES
  platform.saas_plan_revisions(id) ON DELETE RESTRICT`;
- `status text NOT NULL CHECK IN ('TRIALING','ACTIVE')`;
- `funding_mode text NOT NULL CHECK IN ('TRIAL','COMPED')`;
- CHECK only `(TRIALING,TRIAL)` or `(ACTIVE,COMPED)` in M1.3;
- `effective_from timestamptz NOT NULL`, `effective_until timestamptz NOT NULL`,
  CHECK `effective_from < effective_until`;
- `version bigint NOT NULL DEFAULT 1 CHECK (version > 0)`;
- `created_at`, `updated_at` non-null DB timestamps;
- `PRIMARY KEY(workspace_id,id)` and indexes
  `(workspace_id,effective_from DESC)` and `(plan_revision_id)`.

Recommendation: finite interval for both pilot modes because no duration/default
may be invented and expiry must fail closed. Prevent overlapping intervals for a
Workspace at DB level; mechanism is OPEN-02. Past rows remain immutable history.
Renewal/plan change appends an interval rather than rewriting the pinned past row;
CAS applies to a not-yet-effective/corrective row only if C0 accepts such command.
No owner/runtime command may assign `COMPED` or plan revision.

#### `app.workspace_service_modes`

Separate current product-control state, never derived merely by copying status:

- `workspace_id uuid PRIMARY KEY REFERENCES platform.workspaces(id) ON DELETE RESTRICT`;
- `id uuid NOT NULL DEFAULT uuidv7()`, `UNIQUE(workspace_id,id)`;
- `mode text NOT NULL CHECK IN ('NORMAL','GRACE','LIMITED','SUSPENDED')`;
- `reason_code text NOT NULL` from a typed server allow-list; no arbitrary secret
  reason text;
- `effective_from timestamptz NOT NULL`, optional `effective_until timestamptz`,
  CHECK null or `effective_from < effective_until`;
- `version bigint NOT NULL DEFAULT 1 CHECK (version > 0)`;
- `created_at`, `updated_at` non-null DB timestamps.

M1.3 normally provisions `NORMAL`; no automatic provider transition exists.
OWNER has read only. A later explicit billing policy/internal command may change
mode, but M1.3 exposes no universal editor and no UI write.

#### `app.audit_events`

Append-only Workspace business audit:

- `workspace_id uuid NOT NULL`, `id uuid NOT NULL DEFAULT uuidv7()`, composite PK;
- `occurred_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP`;
- `actor_kind text NOT NULL CHECK IN ('USER_ACCOUNT','LOCAL_PROVISIONER')`;
- `actor_user_account_id uuid` plus composite nullable FK
  `(workspace_id,actor_user_account_id)` to
  `platform.workspace_memberships(workspace_id,user_account_id) ON DELETE RESTRICT`;
- CHECK USER_ACCOUNT has actor id and LOCAL_PROVISIONER has null actor id;
- `correlation_id uuid NOT NULL`;
- `event_type text NOT NULL`, initially exact allow-list
  `BILLING_ACCOUNT_CONTACT_UPDATED` and `WORKSPACE_BILLING_PROVISIONED`;
- `object_type text NOT NULL`, initially `WORKSPACE_BILLING_ACCOUNT`;
- `object_id uuid NOT NULL`, `object_version bigint NOT NULL CHECK > 0`;
- `idempotency_key text` nullable, bounded/opaque; partial unique
  `(workspace_id,event_type,idempotency_key) WHERE idempotency_key IS NOT NULL`;
- `payload jsonb NOT NULL DEFAULT '{}'`, CHECK object and bounded by application
  plus a small DB octet-length ceiling (PROPOSED 4096 bytes; OPEN-03);
- index `(workspace_id,occurred_at DESC,id DESC)` and
  `(workspace_id,object_type,object_id,object_version)`.

FORCE RLS applies. INSERT and SELECT are narrow; UPDATE/DELETE are never granted
and an immutability trigger rejects them outside disposable migration downgrade.
Payload uses event-specific typed construction. For contact update it contains
only changed field names and booleans such as `contact_email_present_before/after`,
not the email/name values. Never passwords, password hashes, session/csrf/bearer
values, cookies, auth headers, full request bodies, DB URLs, provider secrets,
full prompts or arbitrary exception text.

### 2.3 Referential, delete and immutability summary

| Table | Boundary/RLS | Mutation | Delete/history |
|---|---|---|---|
| `platform.saas_plans` | global/no RLS | migrator archive only | no runtime delete |
| `platform.saas_plan_revisions` | global/no RLS | insert once | update/delete rejected |
| `platform.plan_entitlements` | global/no RLS | insert with revision | update/delete rejected |
| `app.workspace_billing_accounts` | Workspace/FORCE RLS | contact CAS | no delete |
| `app.workspace_subscriptions` | Workspace/FORCE RLS | controlled append | intervals retained |
| `app.workspace_service_modes` | Workspace/FORCE RLS | controlled CAS | no delete |
| `app.audit_events` | Workspace/FORCE RLS | append only | immutable retained history |

A subscription cannot use a nonexistent plan revision; all Workspace relations
are explicit and restricted. Cross-Workspace object associations use composite
keys wherever both sides are tenant-scoped. No row is deleted to resolve
`OVER_LIMIT`; that is a typed decision reason, not an entity lifecycle.

## 3. Authorization, tenant context and DB surface

### 3.1 Proposed application permissions

Keep existing `tenancy:read/write` unchanged. Add separately:

- `billing:read`: initially OWNER only;
- `billing:manage`: initially OWNER only, and only the billing-contact demo
  command—not plan/subscription/mode assignment;
- `audit:read`: initially OWNER only.

Exact permissions are re-resolved from live membership for every request. ADMIN
and PROVIDER do not inherit billing rights from `tenancy:write/read`. Anonymous
has none. Entitlement decisions are evaluated only after authentication,
membership and permission checks and cannot grant a permission.

| Operation | OWNER | ADMIN | PROVIDER | anonymous |
|---|---:|---:|---:|---:|
| Read own billing/plan/mode/decisions | `billing:read` allow | deny | deny | 401 |
| Update own billing contact (CAS) | `billing:manage` allow | deny | deny | 401 |
| Read own Audit page | `audit:read` allow | deny | deny | 401 |
| Write plan/revision/entitlement | deny | deny | deny | deny |
| Assign revision/status/COMPED | deny | deny | deny | deny |
| Change service mode | deny | deny | deny | deny |
| Append arbitrary Audit | deny | deny | deny | deny |

LOCAL/TEST provisioning is a separate explicit tool identity and environment
gate, not an HTTP role or membership permission.

### 3.2 Trusted context

HTTP `{workspace_id}` is a candidate selector. Auth middleware obtains the real
session actor; `TenantDatabase.transaction(actor, selector, correlation_id)`
re-resolves an ACTIVE membership and creates the transaction-local, XID-fenced
context on the same connection before yielding. Repository methods accept the
resulting UOW, never raw credentials or a user-supplied actor/correlation.
`correlation_id` is generated/validated server-side and propagated to Audit.
RLS compares rows only with `app.current_workspace_id()`.

Login/bootstrap/session/rotate/logout remain outside entitlement gating.
Membership and Business reads retain their existing semantics. Lack of any
billing row cannot prevent security/session continuity.

### 3.3 Narrow proposed repositories/functions/grants

Application contracts (names illustrative, types mandatory):

```text
BillingRepository.get_snapshot(uow, db_now) -> BillingSnapshot | MissingBillingState
BillingRepository.update_contact(uow, expected_version, patch, idempotency_key)
  -> WorkspaceBillingAccount
AuditRepository.list_events(uow, cursor, limit<=100) -> AuditPage
EntitlementService.decide(snapshot, CapabilityKey, OperationCriticality)
  -> EntitlementDecision
```

`update_contact` owns both the CAS update and event insert within the caller's
single UOW. No repository commits. No external call occurs while it is open.
Catalog reads should be exposed as one specifically reviewed invoker-right SQL
query/grant or a narrow fixed-shape function; do not grant CRUD. If a
`SECURITY DEFINER` function is unavoidable for a cross-schema read, C2 must
review fixed `search_path`, owner, argument validation and explicit
PUBLIC/runtime EXECUTE revokes/grants; generic dynamic SQL or generic table
access is forbidden.

Proposed direct runtime table grants, subject to C2 minimizing them further:

| Object | `asm_runtime` grant |
|---|---|
| three catalog tables | SELECT only if narrow function cannot replace it |
| billing accounts | SELECT, UPDATE(contact fields/version/updated_at only) |
| subscriptions/service modes | SELECT only |
| audit events | SELECT, INSERT only; INSERT used only by domain repository |

No runtime INSERT of plan/subscription/mode, no platform/auth blanket access, no
DELETE, no role inheritance, no `SET ROLE`, no BYPASSRLS and no ownership.
Column grants alone are not authorization: service permissions plus RLS remain
mandatory. Migrator owns DDL/data seeding and has explicit migration policy;
application runtime never uses migrator credentials.

Immutability triggers/functions are owned by migrator, not executable by runtime,
and must not become a generic SECURITY DEFINER mutation channel. Audit has no
public/arbitrary POST endpoint.

## 4. Entitlement and service-mode policy

### 4.1 Typed decision

```text
EntitlementDecision {
  capability_key,
  outcome: ENABLED | DISABLED | LIMIT,
  limit: int | null,
  reason: ENTITLED | NOT_ENTITLED | LIMIT_APPLIES | OVER_LIMIT |
          BILLING_STATE_MISSING | SUBSCRIPTION_INACTIVE |
          REVISION_INVALID | SERVICE_MODE_RESTRICTED,
  evaluated_at, plan_revision_id | null, service_mode | null
}
```

BOOLEAN true => ENABLED, false/missing key => DISABLED. INTEGER => LIMIT even
when zero. Current observed count is not implemented in M1.3; therefore
`OVER_LIMIT` is supported as a domain reason/interface boundary but no usage or
quota service is fabricated. A future caller supplying authoritative entity
count may receive it; M1.3 tests only deterministic catalog decisions.

One DB-authoritative instant is selected once in the transaction (`SELECT
CURRENT_TIMESTAMP`) and used for subscription and mode intervals. Active means
`effective_from <= now < effective_until`; all intervals are half-open UTC
instants (display timezone is a UI concern). Missing billing account,
subscription, mode, entitlement key, invalid pair, expired trial, overlapping
rows or unreadable/stale referenced revision fails closed for gated domain work.
No fallback plan and no name-based branch.

An archived plan does not invalidate a previously pinned immutable revision.
A missing/rejected revision is `REVISION_INVALID`. Downgrade never removes rows;
new creation is disabled or reports LIMIT/OVER_LIMIT once an authoritative count
exists.

### 4.2 Policy truth table

This is the M1.3 implemented boundary for a structurally valid local subscription
and entitlement. `E` also requires the capability's BOOLEAN true or valid limit.

| Subscription at DB now | Service mode | ESSENTIAL | STANDARD | EXPENSIVE_OPTIONAL |
|---|---|---|---|---|
| TRIALING + TRIAL, active | NORMAL | E | E | E |
| TRIALING + TRIAL, active | GRACE | E | E | DISABLED / SERVICE_MODE_RESTRICTED |
| TRIALING + TRIAL, active | LIMITED | E | DISABLED | DISABLED |
| TRIALING + TRIAL, active | SUSPENDED | E only for explicit continuity allow-list | DISABLED | DISABLED |
| ACTIVE + COMPED, active | NORMAL | E | E | E |
| ACTIVE + COMPED, active | GRACE | E | E | DISABLED |
| ACTIVE + COMPED, active | LIMITED | E | DISABLED | DISABLED |
| ACTIVE + COMPED, active | SUSPENDED | E only for explicit continuity allow-list | DISABLED | DISABLED |
| missing/expired/invalid | any | continuity allow-list only | DISABLED / state reason | DISABLED / state reason |

`E` means evaluate entitlement value, not unconditional enablement. The explicit
continuity allow-list is code-owned and narrow: login, session read/rotation,
logout/revocation, security recovery, and durable safety intake where later
implemented. Those operations are not ordinary plan capabilities and must not be
blocked by missing billing. M1.3 does not implement inbound channel intake, AI or
quota work merely to fill the table. `GRACE` is modeled but no provider-driven
transition is implemented.

Trial duration, real limits, prices and production capability inventory remain
OPEN business inputs. LOCAL/TEST may seed clearly named synthetic plan/revision,
explicit timestamps and synthetic capabilities accepted by review; they never
become production defaults.

## 5. Audit baseline and atomic demonstration

### 5.1 Meaning and actor

Audit records an important completed business action. It is not a request/access
log, debugging stream, auth `SecurityEvent`, async Outbox, or proof that an
external side effect happened. The normal owner command takes actor id and
correlation solely from verified `WorkspaceContext`; payload never accepts them.

LOCAL/TEST provisioning writes `WORKSPACE_BILLING_PROVISIONED` with
`actor_kind=LOCAL_PROVISIONER`, null user id, a tool-generated correlation and a
non-secret fixture identifier/idempotency key. `asm_migrator` is a DB identity,
not a human Owner and must never be serialized as one. Production provisioning is
outside this scope.

### 5.2 One concrete demonstration command

PROPOSED `PATCH /api/v1/workspaces/{workspace_id}/billing-account` updates only
`contact_display_name` and/or `contact_email`, requiring authenticated OWNER,
`billing:manage`, `If-Match`/body `expected_version`, CSRF and an idempotency key.
It is an ESSENTIAL administrative command and is permission-gated, not
entitlement-gated, so broken billing cannot prevent correction of its contact.
It cannot set plan, subscription, funding/status or service mode.

Within one existing tenant UOW:

1. lock/read own billing account under RLS;
2. claim/check bounded idempotency key and request fingerprint (OPEN-04 decides
   whether M1.3 adds a narrow command receipt or only duplicate Audit key);
3. `UPDATE ... WHERE workspace_id=:context AND version=:expected`, incrementing
   version exactly once;
4. insert exactly one `BILLING_ACCOUNT_CONTACT_UPDATED` AuditEvent referencing
   the new object version and controlled before/after presence/change flags;
5. commit once; only then build the HTTP success response.

Any validation/Audit insertion failure rolls back both rows. Zero updated rows is
`STALE_STATE`/HTTP 409 and creates no Audit. Two concurrent equal-version commands
produce one committed mutation/event; the loser is 409 with none. Repeating a
completed idempotency key with identical fingerprint returns/reconstructs the
same safe result; a different fingerprint is 409 `IDEMPOTENCY_CONFLICT`.
No claim of these outcomes is PASS until real PostgreSQL tests exist.

A bare unique Audit key prevents duplicate events but cannot safely replay the
response after commit ambiguity; therefore the recommendation for OPEN-04 is a
minimal workspace-scoped command receipt only if C0 requires ambiguity recovery
for this demonstration. It must not become a generic future Jobs/Outbox table.

### 5.3 Audit read

PROPOSED owner-only cursor-paginated GET has `limit <= 100`, newest first,
workspace RLS, fixed DTO fields and event-specific sanitized payload. No query by
arbitrary Workspace, free-form SQL/filter, mutation, export-all or generic Audit
POST. Missing/foreign objects do not disclose existence.

## 6. API and UI consumer proposal

No accepted M1.2 endpoint, DTO, cookie/CSRF behavior, session expiry/rotation,
error semantics or seven auth/business endpoints changes. The existing endpoints
continue working when billing tables/rows are absent; no eager entitlement check
is added to auth middleware or Business reads.

Proposed additions after backend authorization:

| Method/path | Permission | Purpose |
|---|---|---|
| `GET /api/v1/workspaces/{workspace_id}/billing` | `billing:read` | owner snapshot |
| `PATCH /api/v1/workspaces/{workspace_id}/billing-account` | `billing:manage` | one audited CAS demo mutation |
| `GET /api/v1/workspaces/{workspace_id}/audit-events?cursor=&limit=` | `audit:read` | sanitized owner history |

Owner snapshot DTO contains only:

```text
workspace_id
evaluated_at
billing_account {id, contact_display_name, contact_email, version}
subscription {id, status, funding_mode, effective_from, effective_until,
              plan_revision_id, version}
plan {id, code, display_name, revision, revision_label}
service_mode {mode, reason_code, effective_from, effective_until, version}
entitlements [{capability_key, criticality, outcome, limit, reason}]
```

No provider reference, raw policy JSON, hidden override, credentials or payment
claim. Safe errors extend the existing envelope: 401 `SESSION_REQUIRED`; 403
`ACCESS_DENIED`/CSRF; 404 `NOT_FOUND` without foreign disclosure; 409
`STALE_STATE` or `IDEMPOTENCY_CONFLICT`; 422 `INVALID_REQUEST`; 503
`BILLING_STATE_UNAVAILABLE` for own incomplete/invalid local state. Exact addition
to generated OpenAPI/error enums waits for implementation review.

C5 later renders actual DTO state, explicit unavailable/expired/restricted
reasons and CAS conflict recovery. It never synthesizes entitlement, writes
COMPED/plan/mode, trusts membership cached in browser, or bypasses backend.
Existing fixtures without billing remain able to login/logout/rotate/read their
Businesses and complete the accepted six browser journeys. A new minimal owner
journey uses a newly provisioned synthetic Workspace, not retrofit assumptions in
old fixtures.

## 7. Provisioning, upgrade and reliability

### 7.1 LOCAL/TEST data

Extend a reviewed provisioning script only after implementation approval. It must
require explicit `LOCAL|TEST` and `asm_local|asm_test`, use migrator only for the
controlled seed path, and print non-secret IDs. Seed one clearly synthetic global
plan/revision/entitlement set, then normal billing account, finite subscription
and NORMAL mode for synthetic Workspace A and B. Choose TRIALING+TRIAL or
ACTIVE+COMPED explicitly per fixture; never `PAID`, a provider success, real
customer data, production credentials or network calls. Re-run is deterministic
via stable natural keys/idempotency and refuses conflicting content.

Owner contact values are synthetic. Provision audit actor is
LOCAL_PROVISIONER—not a forged owner. Runtime demonstrations subsequently use a
real synthetic authenticated Owner and normal permissions/UOW.

### 7.2 Upgrade shape

Future assigned migration from predecessor `0003` adds exactly seven proposed
canonical tables (plus a narrowly approved command receipt only if OPEN-04 is
accepted), policies, constraints/indexes/immutability guards and least-privilege
grants. Existing Workspace rows are **not** silently assigned a plan, trial
length, limits or COMPED state. Thus upgrade leaves them without billing state;
legacy auth/Business behavior remains unchanged and gated new billing view
returns its safe unavailable state until explicit LOCAL/TEST provisioning.

Migration metadata and tests must update the exact expected table/column/FK/index/
policy/grant/function inventory. They retain role checks, revoked TEMP/schema
CREATE, uuidv7 default, pgvector availability, non-AUTOCOMMIT migration/runtime,
current-role, owner/BYPASSRLS and transaction-fence assertions. Runtime must not
own new app tables. Catalog immutability, half-open interval semantics and CAS
must survive fresh and upgrade paths.

No dependency is added merely for Markdown. If interval exclusion needs
`btree_gist`, C0/C2 must explicitly accept and test that extension (OPEN-02); do
not install it silently. The existing 246 cases are regression baseline/evidence
for accepted M1.2, not evidence that M1.3 passes.

## 8. Acceptance matrix (future implementation)

| Gate | Required proof |
|---|---|
| Contract/source | architecture originals checksum import; generated contracts exactly match reviewed implementation; clean tree |
| Migration fresh | empty disposable PostgreSQL -> head; exact seven-table inventory, metadata, policies, grants, owners |
| Upgrade | actual M1.2/`0003` rows -> new head; old login/Business rows and semantics intact; no implicit paid state |
| Replay | second upgrade is no-op/current head; no duplicate seed/catalog rows |
| Downgrade/re-upgrade | disposable TEST only; documented destructive boundary; fresh metadata restored |
| RLS | real `asm_runtime`; A reads/writes only A; A selector cannot see/change B billing or Audit; missing context denied |
| Grants | runtime cannot write catalog/subscription/mode, delete Audit, set role, bypass/own; anonymous/API role matrix |
| Catalog | revision/entitlement UPDATE/DELETE rejected; invalid typed value and duplicate revision/key rejected |
| Intervals/time | DB-authoritative half-open boundaries, expired trial, invalid/overlap rejected; timezone-independent instants |
| Entitlement | every truth-table cell; missing state/revision/key fail closed; no plan-name branch; continuity auth unaffected |
| CAS | deterministic two-connection race: one winner/event and one stale loser/no event |
| Audit atomicity | forced Audit failure rolls mutation back; forced mutation failure leaves no event; actor/correlation/object version exact |
| Retry | identical idempotency repeat has one mutation/event; mismatched fingerprint conflicts; post-commit ambiguity behavior explicit |
| Privacy | typed payload allow-list/size; no password/token/cookie/header/request/DB URL/contact values in response logs/Audit |
| Typed application | service/repository/API DTO and safe error unit tests; test doubles supplement but do not replace PostgreSQL |
| UI/browser | minimal owner read + audited contact update on real API/disposable PostgreSQL; foreign Workspace negative |
| Regression | full foundation and browser jobs, clean-source gates, one exact implementation head/tree; no paid/production calls |

SQLite, mock-only tests, SQL snippets in this document and a green docs-only CI do
not constitute DB/E2E or M1.3 evidence.

## 9. Mandatory OPEN decisions before DDL

### OPEN-01 — schema placement for Workspace billing state

Spec §2.4 lists later plans/subscriptions among global platform data, while
§§2.1, 15.1–15.2 make Workspace the billing boundary and require tenant defense.

- A: all billing tables in `platform`, accessed only through fixed functions;
  strong catalog grouping but risks an oversized privileged surface and obscures
  tenant RLS conventions.
- **Recommended B:** global plan catalog in `platform`; WorkspaceBillingAccount,
  Subscription, ServiceMode and Audit in `app` with FORCE RLS/composite keys.
  It makes the boundary mechanically visible while retaining a global catalog.

C0/C2 must affirm that this is a placement clarification, not a silent revision
of §2.4; otherwise an ADR/explicit accepted interpretation is needed.

### OPEN-02 — non-overlapping subscription intervals

- A: `tstzrange` exclusion `(workspace_id WITH =, interval WITH &&)` requiring
  reviewed `btree_gist`; strongest DB invariant, extra extension/metadata.
- B: transaction-scoped Workspace advisory lock + checked insert; no extension,
  but every writer must use the one command and raw migrator mistakes remain.
- **Recommendation:** A if `btree_gist` is approved in foundation inventory;
  otherwise B plus a narrow insert function and adversarial concurrency tests.
  Never rely on application pre-check alone.

### OPEN-03 — Audit retention and payload ceiling

Legal retention duration is deployment/market dependent and must not be invented.
- **Recommendation:** append-only indefinite for this LOCAL/TEST slice, no purge
  endpoint; record explicit retention policy before production. Use 4096-byte
  serialized JSON ceiling now because only typed flags are needed, revisable by
  reviewed migration. Trade-off: bounded abuse/storage versus later richer
  event-specific metadata.

### OPEN-04 — idempotency persistence for demonstration command

- A: unique Audit idempotency key only; minimal table set, but cannot safely
  recover an exact committed response/fingerprint after transport ambiguity.
- **Recommended B:** one minimal `app.command_receipts` only for this command,
  workspace-scoped/FORCE RLS, operation+key+request hash+result reference/status,
  created atomically; correct replay but makes the inventory eight tables and
  must not become Jobs/Outbox. C0 must explicitly authorize it before DDL.
- C: omit idempotency promise and make ambiguity require authoritative GET;
  smallest scope, weaker command ergonomics.

Until decided, the required seven-table inventory excludes a receipt and the API
must not promise exactly-once replay.

### OPEN-05 — initial capability keys and pilot values

Architecture fixes the mechanism, not actual prices, trial duration, limits or
product inventory. **Recommendation:** C0 accepts a tiny explicitly synthetic
TEST-only fixture (one BOOLEAN STANDARD capability and one INTEGER limit) solely
for policy proof; production catalog remains empty. Trade-off: meaningful tests
without accidentally canonizing commercial defaults.

### OPEN-06 — contact fields and personal-data handling

A billing account conceptually permits contact/legal metadata, but M1.3 needs
only a real safe mutation. **Recommendation:** accept bounded display name plus
optional email, return them only to billing:read OWNER, and Audit only changed
field names/presence. Alternative is display name alone (less PII, less realistic
contact function). No legal/country/provider fields until their use case.

### OPEN-07 — service-mode writer and reason allow-list

M1.3 needs policy behavior but has no provider or Platform Ops authority.
**Recommendation:** provisioning may create NORMAL; tests may seed other typed
modes through migrator fixtures; runtime exposes read only. Defer mutation command
and final reason taxonomy until a real BillingPolicy/Ops workflow exists. This
avoids a hidden owner/admin suspension switch while still proving evaluation.

## 10. Review handoff

Requested C0/C2 review decisions: OPEN-01 through OPEN-07, exact schema/table
inventory, whether catalog SELECT uses direct grants or a narrow function,
permission names/mapping, and the demonstration command/idempotency boundary.
Only after those decisions may C0 allocate a revision and executable file scope.

This proposal adds no migration, ORM/runtime endpoint, frontend, fixture, test,
JSON contract, dependency, paid provider call or production state. It does not
claim Audit atomicity, RLS, entitlement behavior, regression CI or M1.3 as
implemented, REVIEW, INTEGRATED or VERIFIED.
