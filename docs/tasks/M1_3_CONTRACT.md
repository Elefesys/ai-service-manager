# M1.3 R4 — pre-DDL contract: local Entitlements и Audit

Дата редакции: 2026-09-19. Владелец предложения: C1. Исходный принятый base:
`28c289ce6f77e33676cfa416585cc0e20c0be4e3`, tree
`0df4c1b9a2e6922f742ebe459e46dd93d2c2959f`. Reviewed R2:
`cded2b2417df2d7a98e83c0b41acbe0c0c7c34b3`, tree
`07057b6f37da8d44603f18b0ef4d4327176ba97f`. Reviewed R3:
`dbde2bda183e3d2dcb58c9828d3a88f21fb4d940`, tree
`26ff0a611a9add704d1a60941fa7e89b252bda5a`. Статус:
**CONTRACT R4 PROPOSED / AWAITING C0-C2 REVIEW**.

Это docs-only предложение, адресующее три OPEN findings targeted review R3.
Оно сохраняет C0 D-01…D-13 и LOCKED ADR, но не является принятым DDL,
implementation/evidence или разрешением назначить successor `0003`. `0001`–`0003`,
runtime, frontend, generated contracts и package manifests не изменяются.

## 1. Scope, границы и inventory

Workspace — единственная tenant boundary. Route `workspace_id` — selector, не
authority. Entitlement не permission; structured state/domain services, а не LLM,
определяют критические факты. Runtime не owner/SUPERUSER/BYPASSRLS. Provider,
prices, checkout, paid state, invoice/webhook, usage/quota, override, Jobs/Outbox,
generic command, реальные данные и production activation вне M1.3.

Ровно восемь таблиц:

1. `platform.saas_plans`;
2. `platform.saas_plan_revisions`;
3. `platform.plan_entitlements`;
4. `platform.workspace_billing_accounts`;
5. `platform.workspace_subscriptions`;
6. `platform.workspace_service_modes`;
7. `app.audit_events`;
8. `platform.billing_contact_command_receipts`.

Первые три — глобальный несекретный каталог; последние пять Workspace-owned.
Все нижеследующие physical/DTO детали — **Proposed R4**, подлежащие C0/C2 review.
Имена constraints/indexes также normative proposal, чтобы не оставлять A-or-B.

## 2. Proposed R4 physical specification

Правила для всех таблиц: owner `asm_migrator`; UUID entity, создаваемый самой
таблицей, получает `DEFAULT pg_catalog.uuidv7()`, но внешний `workspace_id` и все
FK UUID — **NO DEFAULT**. Все timestamps — `timestamp with time zone`; обязательные
timestamps имеют `isfinite(...)`. `bigint` versions положительны, limits допускают
ноль. `ON UPDATE NO ACTION`, `NOT DEFERRABLE` применяются ко всем FK ниже; `ON
DELETE RESTRICT` указан явно. CHECK не заменяет race-safe writer/parent lock.

### 2.1 `platform.saas_plans`

| column | SQL type | nullability | default |
|---|---|---|---|
| `plan_id` | `uuid` | NOT NULL | `pg_catalog.uuidv7()` |
| `code` | `text` | NOT NULL | NO DEFAULT |
| `display_name` | `text` | NOT NULL | NO DEFAULT |
| `status` | `text` | NOT NULL | NO DEFAULT |
| `created_at` | `timestamptz` | NOT NULL | `CURRENT_TIMESTAMP` |

Constraints: `saas_plans_pkey` PK `(plan_id)`; `saas_plans_code_key` UNIQUE
`(code)`; `saas_plans_code_check` CHECK (`code ~ '^[a-z][a-z0-9_-]{0,63}$'`);
`saas_plans_display_name_check` CHECK (`char_length(display_name) BETWEEN 1 AND
200`); `saas_plans_status_check` CHECK (`status IN ('ACTIVE','ARCHIVED')`);
`saas_plans_created_at_finite_check` CHECK (`isfinite(created_at)`). PK/UNIQUE
already create btree indexes; no separate indexes.

### 2.2 `platform.saas_plan_revisions`

| column | SQL type | nullability | default |
|---|---|---|---|
| `plan_revision_id` | `uuid` | NOT NULL | `pg_catalog.uuidv7()` |
| `plan_id` | `uuid` | NOT NULL | NO DEFAULT |
| `revision` | `integer` | NOT NULL | NO DEFAULT |
| `publication_state` | `text` | NOT NULL | NO DEFAULT |
| `published_at` | `timestamptz` | NULL | NO DEFAULT |
| `created_at` | `timestamptz` | NOT NULL | `CURRENT_TIMESTAMP` |

Constraints: `saas_plan_revisions_pkey` PK `(plan_revision_id)`;
`saas_plan_revisions_plan_revision_key` UNIQUE `(plan_id,revision)`;
`saas_plan_revisions_id_state_key` UNIQUE `(plan_revision_id,publication_state)`;
`saas_plan_revisions_plan_fkey` FK `(plan_id)` →
`platform.saas_plans(plan_id)` ON DELETE RESTRICT ON UPDATE NO ACTION NOT
DEFERRABLE; `revision_positive_check` CHECK (`revision > 0`);
`publication_check` CHECK exactly
`(publication_state='DRAFT' AND published_at IS NULL) OR
(publication_state='SEALED' AND published_at IS NOT NULL AND isfinite(published_at))`;
`created_at_finite_check` CHECK (`isfinite(created_at)`). Constraint btrees suffice.

Lifecycle trigger/provisioner permits only `DRAFT -> SEALED`, never reverses,
updates or deletes SEALED rows. Entitlement INSERT and seal both first lock the
same parent revision `FOR UPDATE`; seal validates the complete set while holding
that lock. Canonical manifest lines are UTF-8
`key + TAB + kind + TAB + (true|false|unsigned decimal) + TAB + criticality + LF`,
sorted by UTF-8 key bytes. Exact TEST set/count/digest:

| key | kind/value | criticality |
|---|---|---|
| `test.m1_3.essential_true` | `BOOLEAN` / `true` | `ESSENTIAL` |
| `test.m1_3.standard_true` | `BOOLEAN` / `true` | `STANDARD` |
| `test.m1_3.standard_false` | `BOOLEAN` / `false` | `STANDARD` |
| `test.m1_3.expensive_positive` | `INTEGER` / `3` | `EXPENSIVE_OPTIONAL` |
| `test.m1_3.expensive_zero` | `INTEGER` / `0` | `EXPENSIVE_OPTIONAL` |

Count is exactly `5`; SHA-256 is
`2aed3e0812691c4546997692e664660c7e328783422ae824c8279bd2cef963cc`.

### 2.3 `platform.plan_entitlements`

| column | SQL type | nullability | default |
|---|---|---|---|
| `plan_revision_id` | `uuid` | NOT NULL | NO DEFAULT |
| `capability_key` | `text` | NOT NULL | NO DEFAULT |
| `value_kind` | `text` | NOT NULL | NO DEFAULT |
| `enabled` | `boolean` | NULL | NO DEFAULT |
| `limit_value` | `bigint` | NULL | NO DEFAULT |
| `criticality` | `text` | NOT NULL | NO DEFAULT |
| `created_at` | `timestamptz` | NOT NULL | `CURRENT_TIMESTAMP` |

Constraints: `plan_entitlements_pkey` PK `(plan_revision_id,capability_key)`;
`plan_entitlements_revision_fkey` FK `(plan_revision_id)` → revisions
`(plan_revision_id)` ON DELETE RESTRICT ON UPDATE NO ACTION NOT DEFERRABLE;
`capability_key_check` CHECK (`capability_key ~ '^[a-z][a-z0-9_.:-]{0,127}$'`);
`value_check` CHECK exactly `(value_kind='BOOLEAN' AND enabled IS NOT NULL AND
limit_value IS NULL) OR (value_kind='INTEGER' AND enabled IS NULL AND
limit_value IS NOT NULL AND limit_value >= 0)`; `criticality_check` CHECK
`criticality IN ('ESSENTIAL','STANDARD','EXPENSIVE_OPTIONAL')`;
`created_at_finite_check`. PK btree suffices. Supported writer locks DRAFT parent;
UPDATE/DELETE are rejected and SEALED INSERT is rejected.

### 2.4 `platform.workspace_billing_accounts`

| column | SQL type | nullability | default |
|---|---|---|---|
| `workspace_id` | `uuid` | NOT NULL | NO DEFAULT |
| `billing_account_id` | `uuid` | NOT NULL | `pg_catalog.uuidv7()` |
| `contact_display_name` | `text` | NOT NULL | NO DEFAULT |
| `version` | `bigint` | NOT NULL | `1` |
| `created_at` | `timestamptz` | NOT NULL | `CURRENT_TIMESTAMP` |
| `updated_at` | `timestamptz` | NOT NULL | `CURRENT_TIMESTAMP` |

Constraints: `workspace_billing_accounts_pkey` PK `(workspace_id)`;
`workspace_billing_accounts_workspace_id_key` UNIQUE `(workspace_id,
billing_account_id)`; `workspace_billing_accounts_workspace_fkey` FK
`(workspace_id)` → `platform.workspaces(id)` ON DELETE RESTRICT ON UPDATE NO
ACTION NOT DEFERRABLE; `version_positive_check`; finite checks for both timestamps;
`timestamp_order_check` (`updated_at >= created_at`); `contact_check` requires
`contact_display_name = btrim(contact_display_name,' ')`, 1..200 characters,
`octet_length <= 800`, and no code point U+0000..U+001F/U+007F. The command also
performs strict scalar/UTF-8 validation; PostgreSQL UTF8 rejects malformed bytes.
Constraint btrees suffice.

### 2.5 `platform.workspace_subscriptions`

| column | SQL type | nullability | default |
|---|---|---|---|
| `workspace_id` | `uuid` | NOT NULL | NO DEFAULT |
| `subscription_id` | `uuid` | NOT NULL | `pg_catalog.uuidv7()` |
| `plan_revision_id` | `uuid` | NOT NULL | NO DEFAULT |
| `required_publication_state` | `text` | NOT NULL | NO DEFAULT |
| `status` | `text` | NOT NULL | NO DEFAULT |
| `funding_mode` | `text` | NOT NULL | NO DEFAULT |
| `effective_from` | `timestamptz` | NOT NULL | NO DEFAULT |
| `effective_until` | `timestamptz` | NOT NULL | NO DEFAULT |
| `version` | `bigint` | NOT NULL | `1` |
| `created_at` | `timestamptz` | NOT NULL | `CURRENT_TIMESTAMP` |
| `updated_at` | `timestamptz` | NOT NULL | `CURRENT_TIMESTAMP` |

Constraints: `workspace_subscriptions_pkey` PK `(workspace_id,subscription_id)`;
`workspace_subscriptions_workspace_fkey` FK `(workspace_id)` → workspaces
RESTRICT/NO ACTION/NOT DEFERRABLE; `workspace_subscriptions_revision_state_fkey`
FK `(plan_revision_id,required_publication_state)` → revisions
`(plan_revision_id,publication_state)` RESTRICT/NO ACTION/NOT DEFERRABLE;
`required_state_check` CHECK `required_publication_state='SEALED'`;
`status_funding_check` CHECK exactly `(status='TRIALING' AND
funding_mode='TRIAL') OR (status='ACTIVE' AND funding_mode='COMPED')`;
`interval_check` CHECK all endpoints finite and `effective_from < effective_until`;
`version_positive_check`; finite created/updated and updated >= created checks.
`workspace_subscriptions_no_overlap_excl` EXCLUDE USING gist
`(workspace_id WITH =, tstzrange(effective_from,effective_until,'[)') WITH &&)`
NOT DEFERRABLE. Separate btree index
`workspace_subscriptions_current_idx` on `(workspace_id,effective_from DESC,
effective_until DESC,subscription_id DESC)`; PK/FK referenced-side indexes are
not duplicated. Intervals are half-open and adjacent intervals are valid.

### 2.6 `platform.workspace_service_modes`

| column | SQL type | nullability | default |
|---|---|---|---|
| `workspace_id` | `uuid` | NOT NULL | NO DEFAULT |
| `service_mode_id` | `uuid` | NOT NULL | `pg_catalog.uuidv7()` |
| `mode` | `text` | NOT NULL | NO DEFAULT |
| `reason_code` | `text` | NOT NULL | NO DEFAULT |
| `effective_from` | `timestamptz` | NOT NULL | NO DEFAULT |
| `effective_until` | `timestamptz` | NULL | NO DEFAULT |
| `version` | `bigint` | NOT NULL | `1` |
| `created_at` | `timestamptz` | NOT NULL | `CURRENT_TIMESTAMP` |
| `updated_at` | `timestamptz` | NOT NULL | `CURRENT_TIMESTAMP` |

Constraints: `workspace_service_modes_pkey` PK `(workspace_id)`;
`workspace_service_modes_workspace_id_key` UNIQUE `(workspace_id,service_mode_id)`;
workspace FK to workspaces RESTRICT/NO ACTION/NOT DEFERRABLE; `mode_reason_check`
CHECK exactly `(mode,reason_code) IN (('NORMAL','PROVISIONED_LOCAL'),
('GRACE','TEST_GRACE'),('LIMITED','TEST_LIMITED'),
('SUSPENDED','TEST_SUSPENDED'))`; `interval_check` requires finite start and
`effective_until IS NULL OR (isfinite(effective_until) AND effective_from <
effective_until)`; positive version; finite created/updated and order checks.
Constraint btrees suffice. It is singleton current state, not history; only NORMAL
is initializer output and other pairs are explicit migrator fixtures.

### 2.7 `app.audit_events`

| column | SQL type | nullability | default |
|---|---|---|---|
| `workspace_id` | `uuid` | NOT NULL | NO DEFAULT |
| `audit_event_id` | `uuid` | NOT NULL | `pg_catalog.uuidv7()` |
| `occurred_at` | `timestamptz` | NOT NULL | `CURRENT_TIMESTAMP` |
| `actor_kind` | `text` | NOT NULL | NO DEFAULT |
| `actor_user_account_id` | `uuid` | NULL | NO DEFAULT |
| `correlation_id` | `uuid` | NOT NULL | NO DEFAULT |
| `event_type` | `text` | NOT NULL | NO DEFAULT |
| `object_type` | `text` | NOT NULL | NO DEFAULT |
| `object_id` | `uuid` | NOT NULL | NO DEFAULT |
| `object_version` | `bigint` | NOT NULL | NO DEFAULT |
| `payload` | `jsonb` | NOT NULL | NO DEFAULT |

Constraints: `audit_events_pkey` PK `(workspace_id,audit_event_id)`;
`audit_events_workspace_fkey` to workspaces; `audit_events_actor_fkey` composite
`(workspace_id,actor_user_account_id)` → `platform.workspace_memberships(workspace_id,
user_account_id)`; `audit_events_object_fkey` composite `(workspace_id,object_id)`
→ accounts `(workspace_id,billing_account_id)`; all RESTRICT/NO ACTION/NOT
DEFERRABLE. `occurred_at_finite_check`; `object_version_positive_check`;
`audit_events_discriminator_payload_check` is exactly the two-way logic:

```sql
CHECK (
 (event_type = 'WORKSPACE_BILLING_PROVISIONED'
  AND actor_kind = 'LOCAL_PROVISIONER' AND actor_user_account_id IS NULL
  AND object_type = 'WORKSPACE_BILLING_ACCOUNT' AND payload = '{}'::jsonb)
 OR
 (event_type = 'BILLING_ACCOUNT_CONTACT_UPDATED'
  AND actor_kind = 'USER_ACCOUNT' AND actor_user_account_id IS NOT NULL
  AND object_type = 'WORKSPACE_BILLING_ACCOUNT'
  AND payload = '{"changed_fields":["contact_display_name"]}'::jsonb)
)
```

`audit_events_payload_size_check` requires database encoding `UTF8` and
`octet_length(payload::text) <= 4096`. Equality rejects extra keys, wrong/null
values and cross-pairs. Index `audit_events_page_idx` USING btree
`(workspace_id ASC,occurred_at DESC,audit_event_id DESC)`. PK is not duplicated.
Object/version come from locked/RETURNING account; correlation is trusted. No raw
name, intervals, key, fingerprint, credential or diagnostic is stored.

### 2.8 `platform.billing_contact_command_receipts`

| column | SQL type | nullability | default |
|---|---|---|---|
| `workspace_id` | `uuid` | NOT NULL | NO DEFAULT |
| `receipt_id` | `uuid` | NOT NULL | `pg_catalog.uuidv7()` |
| `billing_account_id` | `uuid` | NOT NULL | NO DEFAULT |
| `operation` | `text` | NOT NULL | NO DEFAULT |
| `idempotency_key` | `text` | NOT NULL | NO DEFAULT |
| `request_fingerprint` | `bytea` | NOT NULL | NO DEFAULT |
| `expected_version` | `bigint` | NOT NULL | NO DEFAULT |
| `status` | `text` | NOT NULL | NO DEFAULT |
| `result_version` | `bigint` | NULL | NO DEFAULT |
| `result_outcome` | `text` | NULL | NO DEFAULT |
| `created_at` | `timestamptz` | NOT NULL | `CURRENT_TIMESTAMP` |
| `completed_at` | `timestamptz` | NULL | NO DEFAULT |

Constraints: `billing_contact_command_receipts_pkey` PK `(workspace_id,receipt_id)`;
`billing_contact_command_receipts_key` UNIQUE `(workspace_id,operation,
idempotency_key)`; workspace FK and composite account FK `(workspace_id,
billing_account_id)` → accounts `(workspace_id,billing_account_id)`, both
RESTRICT/NO ACTION/NOT DEFERRABLE. `operation_check` requires
`UPDATE_BILLING_CONTACT`; `key_check` requires ASCII
`[A-Za-z0-9._:-]{1,128}`; `fingerprint_check` requires `octet_length=32`;
`expected_version_positive_check`; finite created check; and:

```sql
CHECK (
  (status = 'IN_PROGRESS'
   AND result_version IS NULL AND result_outcome IS NULL AND completed_at IS NULL)
  OR
  (status = 'SUCCEEDED'
   AND result_version IS NOT NULL AND result_version > 0
   AND result_outcome IS NOT NULL AND result_outcome IN ('UPDATED','NOOP')
   AND completed_at IS NOT NULL AND isfinite(completed_at))
)
```

The CHECK is only row truth, not proof that no transaction can commit IN_PROGRESS.
Supported function inserts and finalizes within one transaction, never commits
IN_PROGRESS, and makes SUCCEEDED immutable. Constraints create all needed btrees;
no duplicate index.

## 3. RLS, privileges and typed command

Each of the five Workspace-owned tables receives exact commands `ALTER TABLE
<qualified-table> ENABLE ROW LEVEL SECURITY` and `ALTER TABLE <qualified-table>
FORCE ROW LEVEL SECURITY`. Policies are:

| table | runtime policy | migrator policy |
|---|---|---|
| `platform.workspace_billing_accounts` | `workspace_billing_accounts_runtime_select` FOR SELECT TO `asm_runtime` USING `(workspace_id = app.current_workspace_id())` | `workspace_billing_accounts_migrator_all` FOR ALL TO `asm_migrator` USING `(true)` WITH CHECK `(true)` |
| `platform.workspace_subscriptions` | `workspace_subscriptions_runtime_select` FOR SELECT TO `asm_runtime` USING `(workspace_id = app.current_workspace_id())` | `workspace_subscriptions_migrator_all` FOR ALL TO `asm_migrator` USING `(true)` WITH CHECK `(true)` |
| `platform.workspace_service_modes` | `workspace_service_modes_runtime_select` FOR SELECT TO `asm_runtime` USING `(workspace_id = app.current_workspace_id())` | `workspace_service_modes_migrator_all` FOR ALL TO `asm_migrator` USING `(true)` WITH CHECK `(true)` |
| `app.audit_events` | `audit_events_runtime_select` FOR SELECT TO `asm_runtime` USING `(workspace_id = app.current_workspace_id())` | `audit_events_migrator_all` FOR ALL TO `asm_migrator` USING `(true)` WITH CHECK `(true)` |
| `platform.billing_contact_command_receipts` | no runtime policy | `billing_contact_command_receipts_migrator_all` FOR ALL TO `asm_migrator` USING `(true)` WITH CHECK `(true)` |

There are no runtime INSERT/UPDATE/DELETE policies. The definer executes as
`asm_migrator`, so its broad migrator policies are explicit; command scoping in
this section remains mandatory rather than relying only on RLS. FORCE RLS and the
effective role-specific policy are independent mechanisms; SECURITY DEFINER is
not claimed to “always bypass” FORCE RLS.

Grants/revokes:

| object | `asm_runtime` | `PUBLIC` |
|---|---|---|
| `platform.saas_plans` | SELECT | all revoked |
| `platform.saas_plan_revisions` | SELECT | all revoked |
| `platform.plan_entitlements` | SELECT | all revoked |
| `platform.workspace_billing_accounts` | SELECT | all revoked |
| `platform.workspace_subscriptions` | SELECT | all revoked |
| `platform.workspace_service_modes` | SELECT | all revoked |
| `app.audit_events` | SELECT | all revoked |
| `platform.billing_contact_command_receipts` | none | all revoked |
| all sequences (none introduced) | none | none |
| schemas `platform`,`app` | USAGE already baseline-required, no CREATE | no new grant |
| contact function | EXECUTE exact signature | EXECUTE revoked |

No table DML is granted to runtime. Owner/migrator retains migration and controlled
initializer rights; baseline role/schema/context restrictions remain unchanged.
Catalog read is fixed-shape invoker SQL, not a definer function.

The sole command is exactly:

```text
platform.update_billing_contact(expected_version bigint,
                                contact_display_name text,
                                idempotency_key text)
RETURNS TABLE (workspace_id uuid, billing_account_id uuid, receipt_id uuid,
               result_version bigint, result_outcome text,
               completed_at timestamptz)
```

It is `SECURITY DEFINER`, owner `asm_migrator`, `SET search_path TO pg_catalog,
pg_temp`; every custom reference is schema-qualified, no dynamic SQL. Migration
revokes PUBLIC and grants EXECUTE of this exact signature to `asm_runtime`.

After validating XID fence, it reads trusted workspace/actor/correlation exactly
once. **Every** membership/account/receipt/Audit SELECT, lock, INSERT and UPDATE
uses `workspace_id = trusted_workspace` or a composite key beginning with it;
INSERT writes that trusted value. Finalize never searches by receipt id/key alone,
account never by account id alone, and actor/object FKs are scoped composites.
There is no unscoped/fallback lookup on NOT FOUND. The catalog is explicitly global
and nonsensitive; it does not gain a fictitious workspace_id. Returned rows are
from the trusted composite account/receipt keys only.

## 4. Admission, transaction and lock order

Mandatory order:

1. HTTP body/header size, exactly-one-header, Origin/CSRF boundary checks;
2. outer `AuthService.workspace` auth transaction admits the session and holds its
   shared admission lock;
3. open a distinct tenant UOW/connection and establish XID-fenced trusted context;
4. read live ACTIVE membership/WorkspaceContext and require OWNER plus
   `billing:manage`;
5. bounded validation/normalization; only now compute fingerprint;
6. observe/claim the workspace-scoped receipt;
7. authorized replay/conflict, otherwise lock account, stale-before-no-op CAS,
   actual Audit on change, receipt finalize;
8. commit tenant transaction; release outer admission; form response.

Receipt existence/read/claim/lock and fingerprint never precede live permission.
A key is not a credential: replay repeats admission and permission. If account
identity is required for receipt's NOT NULL FK it is read after authorization and
before claim, scoped to workspace; receipt still precedes account CAS. Auth and
tenant use two connections; **all** receipt/account/Audit mutations use the one
tenant transaction. Any rejection before mutation has zero new side effects.

Lock order for the runtime contact command remains outer shared
session-admission lock → tenant membership read → workspace receipt unique-key/row
→ billing account row.

Every supported LOCAL/TEST synthetic catalog create/validate/seal transaction first
executes exactly `SELECT pg_advisory_xact_lock(1295070019, 1);`. The first key is
the fixed technical namespace ASCII `M13C` encoded as big-endian int32; key `1`
means only synthetic `code='test'`, revision `1`, with no production/business
meaning. Under that global transaction lock the implementation resolves or creates
the exact plan/revision; an existing revision parent is locked `FOR UPDATE`, and
DRAFT → entitlements → SEALED plus exact manifest/digest validation remain under
the same global lock. All supported entitlement/seal writers for this synthetic
catalog follow global catalog advisory lock → revision parent.

The LOCAL/TEST initializer then locks the trusted
`platform.workspaces` row `FOR UPDATE` as the sole Workspace serialization
primitive. Its exact order is global catalog advisory lock → catalog plan/revision
parent → Workspace parent → account → subscription → service mode → provisioning
Audit. Runtime contact commands never acquire the catalog advisory lock. C2 must
validate this deadlock graph before DDL. Revocation linearizes at the accepted
M1.2 admission boundary: a revocation waiting behind the shared lock cannot
overtake an admitted command; there is no claim of cancellation after admission.

Same fingerprint + SUCCEEDED replays immutable original metadata, even after later
contact changes. Changed fingerprint conflicts. Concurrent same key waits then
observes committed receipt; different keys/same expected version yield one changing
winner. Compare version before no-op. Same-version normalized no-op keeps version
and `updated_at`, completes NOOP and writes no Audit. Changed value increments once,
writes one contact Audit and completes UPDATED. Stale fails before no-op and rolls
back claim. Audit/finalize failure rolls back claim/account/Audit. Provisioning
writes exactly one provision event on fresh; repeat writes none.

## 5. Exact fingerprint v1

Fingerprint is SHA-256 of strict UTF-8 canonical JSON containing exactly four
STRING fields in ASCII key order: `contact_display_name`, `expected_version`,
`operation`, `workspace_id`. Operation is `UPDATE_BILLING_CONTACT`; UUID is lower
canonical; expected version is positive canonical decimal up to
`9223372036854775807`. Name is decoded then trimmed only U+0020, 1..200 Unicode
scalar values and <=800 UTF-8 bytes, without case fold/NFC/NFD. Malformed UTF-8,
lone surrogates, NUL/C0/DEL reject before hash/claim; U+FFFD is not repair.

Encoding has no BOM, surrounding whitespace or final newline. Only `"` and `\`
are escaped as `\"` and `\\`; `/` is raw. Other allowed scalars, including
U+2028/U+2029 and emoji, are raw UTF-8, never `\uXXXX`. Different JSON spellings
are decoded first. Reference (not DB proof):
`json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
allow_nan=False).encode('utf-8','strict')`. Future application and DB encoder must
produce identical bytes; `jsonb::text`/default escaping is not evidence. Function
signature is unchanged; the application supplies normalized values and the
function independently computes/verifies the same algorithm rather than accepting
a fingerprint argument.

All vectors use workspace `01990000-0000-7000-8000-000000000001`, version `"7"`.
Hex is the entire normalized canonical JSON byte sequence.

| case | decoded normalized name | canonical UTF-8 hex | SHA-256 |
|---|---|---|---|
| `ascii` | `"Example name"` | `7b22636f6e746163745f646973706c61795f6e616d65223a224578616d706c65206e616d65222c2265787065637465645f76657273696f6e223a2237222c226f7065726174696f6e223a225550444154455f42494c4c494e475f434f4e54414354222c22776f726b73706163655f6964223a2230313939303030302d303030302d373030302d383030302d303030303030303030303031227d` | `813d712466b9605186455d77032311a5e7865f48a5db0524e90b3f120a1d4b2a` |
| `trim` | `"Example name"` | `7b22636f6e746163745f646973706c61795f6e616d65223a224578616d706c65206e616d65222c2265787065637465645f76657273696f6e223a2237222c226f7065726174696f6e223a225550444154455f42494c4c494e475f434f4e54414354222c22776f726b73706163655f6964223a2230313939303030302d303030302d373030302d383030302d303030303030303030303031227d` | `813d712466b9605186455d77032311a5e7865f48a5db0524e90b3f120a1d4b2a` |
| `cyrillic` | `"Анна"` | `7b22636f6e746163745f646973706c61795f6e616d65223a22d090d0bdd0bdd0b0222c2265787065637465645f76657273696f6e223a2237222c226f7065726174696f6e223a225550444154455f42494c4c494e475f434f4e54414354222c22776f726b73706163655f6964223a2230313939303030302d303030302d373030302d383030302d303030303030303030303031227d` | `cc4623b8517c225cc787e1eb961997592535ef07fc4184193c43862484b25bd8` |
| `quote_backslash_slash` | `"A\"B\\C/D"` | `7b22636f6e746163745f646973706c61795f6e616d65223a22415c22425c5c432f44222c2265787065637465645f76657273696f6e223a2237222c226f7065726174696f6e223a225550444154455f42494c4c494e475f434f4e54414354222c22776f726b73706163655f6964223a2230313939303030302d303030302d373030302d383030302d303030303030303030303031227d` | `a90b071bf4761bda6e42a025e6c7f231b386e453238dddb58cc2db7b94e0d275` |
| `emoji` | `"Studio 🎨"` | `7b22636f6e746163745f646973706c61795f6e616d65223a2253747564696f20f09f8ea8222c2265787065637465645f76657273696f6e223a2237222c226f7065726174696f6e223a225550444154455f42494c4c494e475f434f4e54414354222c22776f726b73706163655f6964223a2230313939303030302d303030302d373030302d383030302d303030303030303030303031227d` | `ffa9252a316a9d8001d20c7d2efe2e842294de6f45710df0faca802fd8a52dbd` |
| `separators` | `"A B C"` | `7b22636f6e746163745f646973706c61795f6e616d65223a2241e280a842e280a943222c2265787065637465645f76657273696f6e223a2237222c226f7065726174696f6e223a225550444154455f42494c4c494e475f434f4e54414354222c22776f726b73706163655f6964223a2230313939303030302d303030302d373030302d383030302d303030303030303030303031227d` | `fc36542d1fe82f730b56f8ad004d7aab3d6bb26208e0b740e0ac3e479f593d54` |
| `composed` | `"é"` | `7b22636f6e746163745f646973706c61795f6e616d65223a22c3a9222c2265787065637465645f76657273696f6e223a2237222c226f7065726174696f6e223a225550444154455f42494c4c494e475f434f4e54414354222c22776f726b73706163655f6964223a2230313939303030302d303030302d373030302d383030302d303030303030303030303031227d` | `69ebd81a850211d04df9055a77ff95468dc1ff88acb568514c11f62d416f0c87` |
| `decomposed` | `"é"` | `7b22636f6e746163745f646973706c61795f6e616d65223a2265cc81222c2265787065637465645f76657273696f6e223a2237222c226f7065726174696f6e223a225550444154455f42494c4c494e475f434f4e54414354222c22776f726b73706163655f6964223a2230313939303030302d303030302d373030302d383030302d303030303030303030303031227d` | `07c64318f29cbe6803800928ebf5d4b27436c63f850f1b190eb8418c79d79030` |

`trim` input is `"  Example name  "` and normalizes to the ASCII bytes. Expected
digests respectively are `813d7124…`, `813d7124…`, `cc4623b8…`, `a90b071b…`,
`ffa9252a…`, `fc36542d…`, `69ebd81a…`, `07c64318…`; the table contains full
values. Composed/decomposed differ. JSON inputs `"A\nB"`, `"A\tB"`, `"A\u0000B"`,
`"A\u007fB"`, lone surrogate `"A\ud800B"`, version `"0"`, `"01"`, overflow,
and missing/empty/duplicate/malformed key are `INVALID_REQUEST` before fingerprint
or receipt and have no valid hash.

## 6. Coherent billing read and decisions

One fixed SQL statement uses one `CURRENT_TIMESTAMP` to read RLS-filtered account,
subscription history/current half-open interval, singleton mode, pinned SEALED
revision/catalog and entitlements. Multiple READ COMMITTED SELECTs are not called
coherent. Archived plan does not invalidate its pinned SEALED revision.

Precedence: structural failure → subscription inactive → mode inactive → missing
capability → mode restriction → typed value. Structural reason precedence is
`BILLING_STATE_MISSING`, `BILLING_STATE_INVALID`, `REVISION_INVALID`, then
`DATABASE_UNAVAILABLE`, except an unreadable DB where facts were not observed
returns only `DATABASE_UNAVAILABLE` and never invents MISSING.

| condition | result |
|---|---|
| missing account/mode/all subscription history | structural 503 / `BILLING_STATE_MISSING` |
| duplicate/contradictory effective state | 503 / `BILLING_STATE_INVALID` |
| missing/unsealed/invalid referenced revision | 503 / `REVISION_INVALID` |
| DB unreadable | 503 / `DATABASE_UNAVAILABLE` |
| valid history, no current subscription | 200, INACTIVE, subscription null; decisions DISABLED/`SUBSCRIPTION_INACTIVE` |
| inactive finite mode | 200, mode_active false; DISABLED/`SERVICE_MODE_INACTIVE` |
| missing requested known key | DISABLED/`NOT_ENTITLED` |

NORMAL allows all criticalities; GRACE ESSENTIAL/STANDARD; LIMITED ESSENTIAL;
SUSPENDED none. A restricted category is DISABLED/`SERVICE_MODE_RESTRICTED`.
Allowed BOOLEAN true is ENABLED, false DISABLED/`NOT_ENTITLED`; INTEGER is LIMIT
with decimal string including `"0"`. LIMITED/GRACE/SUSPENDED do not disable
security/auth, existing Business reads or permission-gated contact administration.

## 7. Exact HTTP/wire contract

Only these routes exist; all objects are strict (`additionalProperties=false`),
all UUIDs lowercase canonical. New timestamps are canonical UTC exactly
`YYYY-MM-DDTHH:MM:SS.ffffffZ` (six fractional digits, no precision loss). New
bigint versions/limits are decimal strings; integer limit zero is valid. Existing
seven M1.2 routes/DTO/TTL/cookie/CSRF/AuthResponse are unchanged.

| method/path | permission |
|---|---|
| `GET /api/v1/workspaces/{workspace_id}/billing` | OWNER `billing:read` |
| `PATCH /api/v1/workspaces/{workspace_id}/billing-account` | OWNER `billing:manage` |
| `GET /api/v1/workspaces/{workspace_id}/audit-events` | OWNER `audit:read` |

No aliases, PUT, `/api/workspaces`, fourth endpoint or entitlement/`tenancy:write`
permission.

Future browser/API implementation must add `PATCH` to the existing CORS
`allow_methods` and `Idempotency-Key` to the existing `allow_headers`, while
preserving every current method/header including `Content-Type`, `X-CSRF-Token`
and `X-CSRF-Bootstrap`. Exact configured `allow_origins`,
`allow_credentials=true`, Host/Origin/CSRF/JSON controls and the no-wildcard
boundary remain unchanged. Positive preflight/browser proof must cover configured
Origin + `PATCH` + `content-type,x-csrf-token,idempotency-key`; negative proof must
reject a foreign Origin and every disallowed method/header. CORS never replaces
authorization or CSRF. R4 documents this additive future implementation obligation;
it does not edit middleware.

### 7.1 GET billing

No query parameters. Response fields:

- `workspace_id: uuid`, `evaluated_at: timestamp` (server DB time);
- `account`: `{billing_account_id: uuid, contact_display_name: string 1..200,
  version: positive-decimal-string}`;
- `subscription`: null or `{subscription_id: uuid,status: TRIALING|ACTIVE,
  funding_mode: TRIAL|COMPED,effective_from: timestamp,effective_until: timestamp,
  version: positive-decimal-string,plan: {plan_id: uuid,code: string,
  revision_id: uuid,revision: integer >=1}}`;
- `mode`: `NORMAL|GRACE|LIMITED|SUSPENDED`; `mode_active: boolean`;
- `availability`: `ACTIVE|INACTIVE`;
- `decisions`: array max 100, sorted ascending by unique `key`; server returns the
  fixed requested-known key set (currently the exact five TEST manifest keys).
  Missing keys remain entries with NOT_ENTITLED; duplicates are forbidden.

Decision is a tagged union: `{key,type:"ENABLED",reason:null,limit:null}`;
`{key,type:"DISABLED",reason:"SUBSCRIPTION_INACTIVE"|"SERVICE_MODE_INACTIVE"|
"NOT_ENTITLED"|"SERVICE_MODE_RESTRICTED",limit:null}`; or
`{key,type:"LIMIT",reason:null,limit:<canonical nonnegative decimal string>}`.
No query selects arbitrary keys.

Valid active example (abbreviated only by choosing one decision, not omitted
schema fields):

```json
{"workspace_id":"01990000-0000-7000-8000-000000000001","evaluated_at":"2026-09-19T12:00:00.000000Z","account":{"billing_account_id":"01990000-0000-7000-8000-000000000002","contact_display_name":"Example name","version":"7"},"subscription":{"subscription_id":"01990000-0000-7000-8000-000000000003","status":"ACTIVE","funding_mode":"COMPED","effective_from":"2026-09-01T00:00:00.000000Z","effective_until":"2026-10-01T00:00:00.000000Z","version":"1","plan":{"plan_id":"01990000-0000-7000-8000-000000000004","code":"test","revision_id":"01990000-0000-7000-8000-000000000005","revision":1}},"mode":"NORMAL","mode_active":true,"availability":"ACTIVE","decisions":[{"key":"test.m1_3.expensive_positive","type":"LIMIT","reason":null,"limit":"3"}]}
```

Inactive success uses `"subscription":null,"availability":"INACTIVE"` and all
decisions DISABLED/SUBSCRIPTION_INACTIVE; account/mode remain present. Structural
failure returns no pretend snapshot.

### 7.2 PATCH billing account

Exact body only:
`{"expected_version":"7","contact_display_name":"Example name"}`. Exactly one
`Idempotency-Key` plus existing M1.2 Origin/CSRF is required; `If-Match` is forbidden.
Success schema is exactly `{workspace_id,billing_account_id,receipt_id,
result_version,outcome,completed_at}`, where IDs are uuid, result version positive
decimal, outcome `UPDATED|NOOP`, timestamp canonical. UPDATED and NOOP examples:

```json
{"workspace_id":"01990000-0000-7000-8000-000000000001","billing_account_id":"01990000-0000-7000-8000-000000000002","receipt_id":"01990000-0000-7000-8000-000000000006","result_version":"8","outcome":"UPDATED","completed_at":"2026-09-19T12:01:00.000000Z"}
```
```json
{"workspace_id":"01990000-0000-7000-8000-000000000001","billing_account_id":"01990000-0000-7000-8000-000000000002","receipt_id":"01990000-0000-7000-8000-000000000007","result_version":"7","outcome":"NOOP","completed_at":"2026-09-19T12:02:00.000000Z"}
```

Replay returns the original exact metadata; current contact is only GET.

### 7.3 Audit item and page

Query permits only optional `limit` integer 1..100 (default 25) and one `cursor`.
Item fields exactly: `audit_event_id:uuid`, `occurred_at:timestamp`, `event_type:
WORKSPACE_BILLING_PROVISIONED|BILLING_ACCOUNT_CONTACT_UPDATED`, `actor_kind:
LOCAL_PROVISIONER|USER_ACCOUNT`, `actor_user_account_id:uuid|null`,
`correlation_id:uuid`, `object_type:WORKSPACE_BILLING_ACCOUNT`, `object_id:uuid`,
`object_version:positive-decimal-string`, `payload` equal to `{}` for provisioning
or `{"changed_fields":["contact_display_name"]}` for contact. Actor null pairs
exactly with LOCAL_PROVISIONER. No contact/key/fingerprint is exposed.

Page is exactly `{items:[AuditItem] (max limit),next_cursor:string<=1024|null}`.
Empty/end pages use null. Fetch `limit+1`; cursor anchor is the last returned item
only when another row exists. Order `(occurred_at DESC,audit_event_id DESC)` and
predicate tuple `<`. Valid example:

```json
{"items":[{"audit_event_id":"01990000-0000-7000-8000-000000000008","occurred_at":"2026-09-19T12:01:00.000000Z","event_type":"BILLING_ACCOUNT_CONTACT_UPDATED","actor_kind":"USER_ACCOUNT","actor_user_account_id":"01990000-0000-7000-8000-000000000009","correlation_id":"01990000-0000-7000-8000-000000000010","object_type":"WORKSPACE_BILLING_ACCOUNT","object_id":"01990000-0000-7000-8000-000000000002","object_version":"8","payload":{"changed_fields":["contact_display_name"]}}],"next_cursor":null}
```

Cursor is unpadded base64url of strict compact UTF-8 JSON, encoded <=1024 ASCII:
`{"v":1,"endpoint":"AUDIT_EVENTS","workspace_id":"<uuid>","direction":"DESC",
"occurred_at":"<canonical timestamp>","id":"<audit uuid>"}`. Duplicate/extra/
missing/wrong fields, invalid encoding or foreign/nonexistent tenant anchor are safe
422. Anchor lookup is tenant-scoped. Cursor is not credential/tamper-proof and
offers no frozen-history guarantee.

### 7.4 Errors

New M1.3 routes use an exact discriminated union; `state_reason` is not a
nullable/optional field on a common error object.

**CommonError** is exactly:

```json
{"error":{"code":"<CODE>"}}
```

It has no `state_reason`. It is used by every applicable shared boundary/auth/common
or non-structural domain failure, including the existing applicable codes
`SESSION_REQUIRED`, `ORIGIN_DENIED`, `CSRF_REJECTED`, `ACCESS_DENIED`,
`BODY_TOO_LARGE`, `UNSUPPORTED_MEDIA_TYPE`, `INVALID_REQUEST`, `RATE_LIMITED`,
`UNAVAILABLE`, `INTERNAL_ERROR`, and the M1.3 domain codes `NOT_FOUND`,
`STALE_STATE`, `IDEMPOTENCY_KEY_CONFLICT`.

**BillingStateError** is exactly:

```json
{"error":{"code":"BILLING_STATE_UNAVAILABLE","state_reason":"DATABASE_UNAVAILABLE"}}
```

It is used only by structural billing-domain GET failure.
`state_reason` is required there and bounded to
`BILLING_STATE_MISSING|BILLING_STATE_INVALID|REVISION_INVALID|DATABASE_UNAVAILABLE`.

Future OpenAPI/typed contracts must encode `CommonError | BillingStateError`
as an exact union, not add nullable `state_reason` to M1.2. Existing M1.2
AuthBoundary/routes/response bytes remain unchanged. HTTP 503 therefore has two
distinct discriminator variants: code-only `UNAVAILABLE` from the shared
boundary/unhandled infrastructure path, or
`BILLING_STATE_UNAVAILABLE` plus required reason from structural billing GET.

| status | exact error variant | routes/meaning |
|---|---|---|
| 401 | `CommonError` / existing auth code | all, unauthenticated |
| 403 | `CommonError` / existing forbidden code | revoked/wrong permission/foreign workspace |
| 404 | `CommonError` / `NOT_FOUND` | PATCH authorized own workspace lacks account |
| 409 | `CommonError` / `STALE_STATE` | PATCH current version differs, checked before no-op |
| 409 | `CommonError` / `IDEMPOTENCY_KEY_CONFLICT` | PATCH same scoped key, different fingerprint |
| 422 | `CommonError` / `INVALID_REQUEST` | strict body/header/query/cursor validation |
| 503 | `CommonError` / `UNAVAILABLE` | shared boundary/unhandled infrastructure path |
| 503 | `BillingStateError` / `BILLING_STATE_UNAVAILABLE` | GET structural billing failure |

Unauthorized/revoked/foreign caller never observes receipt existence. DB inputs,
SQL/stack traces/raw diagnostics never appear. HTTP limits/Origin/CSRF remain at
the accepted boundary.

## 8. LOCAL/TEST initializer and prerequisites

Concrete non-HTTP signature:

```text
initialize_local_billing(workspace_id uuid, catalog_code text,
  catalog_revision integer, contact_display_name text,
  subscription_status text, funding_mode text,
  effective_from timestamptz, effective_until timestamptz,
  service_mode text) -> INITIALIZED | NOOP | CONFLICT_<bounded_reason>
```

Stable identity is existing Workspace UUID. Exact TEST inputs are: code `test`,
revision `1`, synthetic name `Example name`, `ACTIVE/COMPED`, explicit
`2026-09-01T00:00:00.000000Z` and `2026-10-01T00:00:00.000000Z`, mode `NORMAL`.
No secrets/credentials in args/output; no LLM or today+N/default price/duration.

Every supported synthetic catalog create/validate/seal path starts the short
provisioning transaction with exactly
`SELECT pg_advisory_xact_lock(1295070019, 1);`. While holding it, the implementation
resolves or creates the unique TEST `(code='test', revision=1)` plan/revision,
locks an existing revision parent `FOR UPDATE`, validates the exact five-row
manifest/digest and, when fresh, performs DRAFT → entitlements → SEALED. Supported
entitlement/seal writers use the same global-lock-before-revision-parent order.
An unhandled UNIQUE violation is not normal reuse/success control flow and an
aborted transaction is never continued.

After catalog resolution, the initializer locks exactly the trusted
`platform.workspaces` row `FOR UPDATE` as the sole Workspace serialization
primitive. The complete initializer order is global catalog advisory lock →
catalog plan/revision parent → Workspace parent → account → subscription →
service mode → provisioning Audit.

Fresh initialization creates account, subscription, NORMAL mode and exactly one
provisioning Audit. Complete means exact stable keys, FKs, sealed manifest/digest,
requested interval/status/funding/mode and provisioning event. Complete matching
repeat is NOOP: it does not change UUID/version/timestamps/contact,
mode/subscription, add Audit, or touch contact receipts. Partial state, differing
normalized input/catalog/manifest, incompatible catalog, or drift after later
contact/mode/subscription change is a bounded conflict without overwrite/repair.
A read-only reason code may say `PARTIAL_STATE`, `INPUT_MISMATCH`,
`CATALOG_MISMATCH`, or `STATE_DRIFT`, never values. Repeat does not replay contact
response or undo later changes.

Two different fresh Workspaces with identical catalog inputs serialize on the
global catalog lock, both eventually return `INITIALIZED`, and create the catalog
once. Concurrent same-Workspace/same-input calls serialize on the Workspace row:
first `INITIALIZED`, second `NOOP`. Same-Workspace/different-input serializes and
the second conflicts. There is no unlocked check-then-insert. Partial/Audit failure
rolls back the entire new state; NOOP and conflict change nothing; existing state
is never cleared. SQL row counts/errors do not log PII. The advisory lock is held
only by the short LOCAL/TEST provisioning transaction; the runtime contact command
never acquires it. Explicit non-NORMAL migrator fixtures remain separate.

LOCAL/TEST prerequisites, not yet proven: pinned image exact `btree_gist` version,
installation namespace `extensions`, and UUID GiST opclass availability; existing
0003 receives idempotent admin preflight. Admin installs/verifies before domain
DDL; migration fails before any domain DDL. This requires separate review/revision
assignment. No extension is installed now, no version claimed, no weaker fallback,
and `asm_migrator` gets no CREATE. Production managed SKU, retention/privacy,
prices/durations/provider/backup/activation remain future production-only OPEN and
do not block this docs correction or a later local stage after its prerequisites.

## 9. Traceability and acceptance

D-01…D-13 and prior `OPEN-01…07`/`G-01…07` links in
`docs/reviews/M1_3_C0_C2_DISPOSITION.md` remain authoritative and are not replaced.

| R2 finding | normative R4 sections | disposition / acceptance example |
|---|---|---|
| `C0-M1.3-R2-01` | §7 | CLOSED at contract level: exactly three `/api/v1` routes; PATCH, no alias/PUT |
| `C2-M1.3-R2-02` | §4 | CLOSED at contract level: unauthorized replay has no receipt observation/write |
| `C2-M1.3-R2-03` | §2–3 | CLOSED at contract level: eight complete matrices |
| `C2-M1.3-R2-04` | §3–4 | CLOSED at contract level: Workspace A cannot read/write B |
| `C2-M1.3-R2-05` | §2.8, §4 | CLOSED at contract level: no supported committed IN_PROGRESS |
| `C2-M1.3-R2-06` | §5 | CLOSED at contract level: exact vectors and pre-hash rejection |
| `C2-M1.3-R2-07` | §2.7 | CLOSED at contract level: exact discriminator/payload pairs |
| `C2-M1.3-R2-08` | §7.4 | historical REMAINING cause now mapped to `C2-M1.3-R3-01` |
| `C2-M1.3-R2-09` | §4, §8 | historical REMAINING cause now mapped to `C2-M1.3-R3-03` |

| current R3 finding | normative R4 sections | acceptance example |
|---|---|---|
| `C2-M1.3-R3-01` | §7.4 | exact `CommonError | BillingStateError`; no common nullable `state_reason`; both 503 discriminators |
| `C2-M1.3-R3-02` | §7 | configured-Origin PATCH preflight passes; foreign Origin/disallowed method/header fail |
| `C2-M1.3-R3-03` | §4, §8 | two fresh Workspaces create one catalog; exact global → revision → Workspace lock order |

The seven findings `C0-M1.3-R2-01` and `C2-M1.3-R2-02`…`07` are CLOSED at
pre-DDL contract level by C0. The three current blockers `C2-M1.3-R3-01`,
`C2-M1.3-R3-02`, and `C2-M1.3-R3-03` are **ADDRESSED IN R4 / PENDING C0-C2
REVIEW**, not CLOSED. `C2-M1.3-R2-08`/`09` remain historical REMAINING causes only.

Self-review scenarios required before C0/C2 decision: success/error/replay/no-op/
rollback end-to-end from HTTP to proposed SQL; both 503 error variants; configured
Origin PATCH preflight and negative Origin/method/header cases; two Workspaces with
the same synthetic catalog inputs initialized concurrently; same-Workspace
same/different input; sealed/partial revision; missing/inactive/unreadable state;
decimal zero/overflow; all Unicode vectors; initializer fresh/repeat/late-drift.
Future DB negatives include invalid context/XID fence/actor and must fail closed
with zero cross-tenant writes. These are acceptance plans, not current
PostgreSQL/browser evidence.

## 10. Decision state and remaining OPEN

Status remains **CONTRACT R4 PROPOSED / AWAITING C0-C2 REVIEW**.

Seven prior findings are CLOSED at pre-DDL contract level as listed in §9.
Current `C2-M1.3-R3-01`, `C2-M1.3-R3-02`, and `C2-M1.3-R3-03` are only
**ADDRESSED IN R4 / PENDING C0-C2 REVIEW**, not CLOSED. D-01…D-13 remain unchanged.
Locally unverifiable prerequisites are limited to the pinned LOCAL/TEST
extension/version/namespace/opclass and admin preflight; production items listed
in §8 remain future-only OPEN. C2 must perform targeted review of the exact
published R4 before C0 can close the three current blockers or separately authorize
implementation. No migration, DB schema, runtime suite or browser proof is asserted
by this document.
