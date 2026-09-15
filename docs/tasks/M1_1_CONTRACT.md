# M1.1 — tenant foundation contract for C1

Task owner: C2. Integration/review owner: C0. Base:
`7eaa9aa63b3f27215f6eb970fb9eb857fd291f62`.
This implementation contract is recorded before migration 0002. It is not an ADR,
Architecture Freeze, task register, authentication implementation or production approval.
Canonical Spec/ADR prevail; no accepted decision is superseded.

## Schema and identity

Migration `0002_tenant_foundation.py`: revision `0002`, predecessor `0001`.
Only six tables are added. Standalone IDs default to PostgreSQL 18 `uuidv7()`;
IDs are not authorization. `created_at` is timestamptz, `version` is positive bigint
(default 1), statuses/roles are TEXT + CHECK. No credentials, sessions or future
billing/channel/client tables are introduced.

| Table | Primary key | Other minimal fields |
|---|---|---|
| platform.user_accounts | id | status ACTIVE/DISABLED, version, created_at |
| platform.workspaces | id | status ACTIVE/ARCHIVED, version, created_at |
| platform.workspace_memberships | workspace_id, user_account_id | role OWNER/ADMIN/PROVIDER, status ACTIVE/REVOKED, version, created_at |
| app.businesses | workspace_id, id | name, status ACTIVE/ARCHIVED, version, created_at |
| app.business_members | workspace_id, id | business_id, nullable user_account_id, name, role OWNER/ADMIN/PROVIDER, status ACTIVE/ARCHIVED, version, created_at |
| app.locations | workspace_id, id | business_id, name, status ACTIVE/ARCHIVED, version, created_at |

All tenant workspace_id columns are NOT NULL and reference platform.workspaces.
Membership references UserAccount and Workspace. BusinessMember/Location use
(workspace_id, business_id) -> businesses(workspace_id, id). An optional account
link uses (workspace_id, user_account_id) -> workspace_memberships; null allows a
BusinessMember without a UserAccount. UNIQUE(workspace_id, business_id,
user_account_id) prevents duplicate non-null account links in one Business.
Foreign keys use RESTRICT, never cascading cross-scope deletion. Parent FK indexes
are present. Tenant IDs are unique within Workspace, not a cross-tenant existence
oracle. One Workspace may have multiple Businesses and an account multiple memberships.
BusinessMember.role describes participation; it grants no Workspace permissions.
Names are trimmed, nonempty, at most 200 characters. No timezone/pricing fields are
invented before the capability that consumes them.

Version is a CAS foundation, not an automatic trigger or universal last-write-wins
API. The included rename operation requires expected_version, increments it and
returns STALE_STATE on an in-scope conflict. C1 must apply CAS to its future
critical mutable commands. Archive is a configuration lifecycle, not billing
suspension. Physical DELETE is exercised in disposable tests; no public deletion
or privacy workflow is provided here.

## Trusted actor, permissions and platform lookup

`AuthenticatedAccount(user_account_id: UUID)` is a server-only handoff from the
future verified authentication adapter. Its fixed kind is `user_account`.
Constructing this Python value does NOT authenticate anybody. Never deserialize
it from HTTP/LLM input or treat a claimed account ID as authentication. M1.1
exposes no auth/workspace/business HTTP endpoint. Other actor kinds, client/AI,
platform support and jobs are not accepted by this issuer; they require their own
future trusted routing/grant contracts, never an Owner fallback.

`TenantDatabase.transaction(actor, workspace_id, correlation_id)` owns the complete
short transaction. A Workspace selector is only a candidate: the database checks
an exact active Account + Workspace + Membership. There is no first-Workspace,
Owner, service-principal or platform-admin fallback. No caller-supplied permission
list is accepted. OWNER/ADMIN receive `tenancy:read` and `tenancy:write`; PROVIDER
receives only `tenancy:read`. These permissions cover current foundation metadata
only, not future client data, auth administration, money, entitlements or Ops.

The sole pre-context lookup is
`platform.resolve_workspace_membership(actor_id uuid, target_workspace_id uuid)`.
It returns only the active membership role or NULL, locking those three existing
rows FOR SHARE until transaction end. It cannot enumerate accounts/workspaces or
read tenant tables. Its SECURITY DEFINER owner is asm_migrator; search_path is
fixed, all table references qualified, no dynamic SQL, PUBLIC execute revoked.
Runtime has no direct SELECT/INSERT/UPDATE/DELETE on the three platform tables.
Existing platform.alembic_version SELECT remains. Onboarding/auth-management
writes are deferred to explicit C1 commands, not blanket platform grants.

## Context and transaction ownership

The immutable server-created WorkspaceContext contains workspace_id, actor,
permissions (frozenset) and correlation_id (UUID). The unit of work is bound to its
creating asyncio Task and valid only inside its context manager. Nested contexts,
child-task reuse, expired units and contexts without a transaction are rejected.
Each concurrent operation owns a separate connection/transaction. No raw
connection/commit/rollback API is exposed by the unit of work.

Only transaction-local set_config(..., true) is used for asm.workspace_id,
asm.actor_id, asm.actor_kind, asm.correlation_id and asm.context_xid. The last is
an additional transaction-ID fence, not a tenant identifier. RLS resolves NULL
when any component is absent/malformed, the transaction-ID fence is stale, or the
active membership no longer exists. The transaction-local settings disappear on
COMMIT/ROLLBACK; no session-level tenant setter or pooled global tenant state is
used. Python context is reset in finally, including cancellation/error paths.

Tenant tables have ENABLE + FORCE ROW LEVEL SECURITY, a runtime policy with
USING and WITH CHECK, and an explicit migration-only policy. Migrator already
owns DDL; that policy allows controlled migrations under FORCE without granting
anything to runtime. Runtime remains a separate non-owner identity with only
SELECT/INSERT/UPDATE/DELETE on these tenant tables, no DDL/TRUNCATE/REFERENCES,
SUPERUSER/BYPASSRLS/role membership or SET ROLE into privileged identities.
No bootstrap-role change is needed. app.current_workspace_id() is a fixed,
read-only, hardened SECURITY DEFINER helper; it exposes only the validated current
Workspace, never arbitrary platform rows.

RLS is a Workspace data boundary, not permission enforcement. The included
unit-of-work methods require explicit permissions and include workspace_id in
queries; child reads also check business_id. C1 must do action/object authorization
for every future command. A runtime credential or arbitrary Python/SQL execution
is a trusted-server compromise: PostgreSQL custom GUCs and account-ID arguments
are not cryptographic proof of a human identity. Do not expose SQL, these functions
or the actor constructor to a client/model. No SQL-injection/DB-credential-compromise
containment claim is made. Constraint errors must not expose foreign IDs/details.

No external HTTP/provider call is allowed within the business transaction.
Collect external inputs first; persist intent/state in a short transaction;
perform future external effects after commit through the appropriate durable
capability. This module performs no network calls other than PostgreSQL.

## Errors and consumer API

TenancyError exposes only a stable code, never SQL/IDs/credentials:
CONTEXT_REQUIRED, CONTEXT_INVALID, ACCESS_DENIED, TRANSACTION_STATE, NOT_FOUND,
STALE_STATE, INVALID_RELATION, INVALID_STATE, CONFLICT, RETRY_TRANSACTION.
Missing/inactive/unrelated account/workspace/membership all produce ACCESS_DENIED.
Missing/wrong-tenant/wrong-Business object all produce NOT_FOUND. PostgreSQL FK,
CHECK, unique and permission errors are mapped to redacted codes; serialization,
deadlock and lock-timeout require retry of the entire unit, never an automatic
partial retry. Unexpected infrastructure errors propagate to a sanitized outer
adapter, not into a public error body. HTTP/session mapping belongs to M1.2.

Public exports: AuthenticatedAccount, WorkspaceContext, Permission, MembershipRole,
TenantDatabase, TenantUnitOfWork, TenancyError, current_workspace_context.
Unit-of-work methods: list_businesses(), get_business(id),
get_business_member(business_id, id), get_location(business_id, id),
rename_business(id, name, expected_version). Reads return SQLAlchemy RowMapping;
rename returns the updated row. Additional domain mutations belong to C1; runtime
SQL DML is independently tested without calling it application authorization.

## Compatibility, verification and remaining gates

Readiness expects 0002. The public unauthenticated M0 shell/OpenAPI stays unchanged;
M1.1 does not claim the shell now implements login. Fresh upgrade, M0->0002,
idempotent upgrade and 0002->0001->0002 are tested on disposable asm_test only.
Downgrade removes M1.1 data/functions, not infrastructure schemas/vector or 0001;
it is destructive and not a production rollback recommendation. C1 starts from
C0's subsequently accepted SHA, not this unreviewed branch.

The JSON snapshot and executable contract checks cover fields, keys, enums,
permissions, context and errors. Real runtime-role tests cover all six schema
relations, CRUD, forged IDs, cross-Workspace FKs, Business mismatch, missing/bad
context, role restrictions, transaction reuse/concurrency, CAS and readiness.
Existing M0 protections remain regression obligations.

Same-Workspace/different-Client authorization, all later cross-layer tenant gates,
independent C8 review, Architecture Freeze and production readiness remain pending.
There are no Client tables here and that future gate has NOT passed. No new domain
OPEN decision is claimed resolved; the above field/permission/lifecycle choices
are bounded implementation details for C0 review.
