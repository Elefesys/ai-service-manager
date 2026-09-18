# IMPL-002 — LOCAL/TEST server sessions and synthetic password login

Date proposed: 2026-09-16. Author C1.
Decision: accepted explicitly by C0 on 2026-09-18 for the reviewed LOCAL/TEST backend implementation.
Integration: pending actual merge and push/main verification; not completion of all M1.2.
Base `5c7188915fa219d9d6906569e2341632e4969651`; no canonical ADR superseded.
Not LOCKED architecture, production enablement or completion of M1.2.

## Choice and rationale

Keep IMPL-001 Python/FastAPI/SQLAlchemy/psycopg/PostgreSQL stack. Use the maintained
argon2-cffi 25.1.0 high-level PasswordHasher (explicit Argon2id profile m=65536,
t=3,p=4) instead of implementing password KDF/encoding or using obsolete wrappers.
Only that dependency and required bindings/cffi/pycparser are added to the existing
lock; no mass upgrade. Verification runs off the event loop, outside transactions,
with bounded concurrency. A generated dummy hash supplies equivalent verification
work for absent/disabled identities; responses do not claim constant network timing.

Canonical PostgreSQL rows store anonymous login challenges and authenticated
sessions. 256-bit opaque cookie tokens have only SHA-256 verifiers in the DB.
Standard HMAC-SHA256 over a fixed domain separator with the session token as key
provides a session-bound CSRF value without another persisted bearer secret or
process-local signing key. It is not an identity assertion or JWT. Cookie identity
is never in JSON; CSRF by itself cannot authenticate. Stateful lifecycle and
membership validation are independently required for every admitted operation.

Bootstrap is POST with strict Origin + non-simple custom header, avoiding a
state-changing GET or unprotected login. Login consumes the anonymous session
and issues a new token. Rotation consumes the old token without extending
absolute expiry. Error responses never overwrite a potentially newer cookie.
A concurrent rotation beating old-token logout yields 401; C5 must reload and
repeat the user's intended logout, not report success on that 401.

Use narrow migration-owned SECURITY DEFINER functions rather than blanket runtime
CRUD on platform identity/session tables. Shared account/credential/session locks
span the short nested M1.1 UOW; revocation has a defined serialization boundary.
Separate bounded auth/runtime pools avoid nested connection starvation. This
preserves the accepted UOW, RLS and actual-driver AUTOCOMMIT guard unchanged.
It does not contain arbitrary runtime-code/SQL credential compromise.

ASCII synthetic usernames avoid pretending an unimplemented email provider has
verified an address. TTLs, local origins and throttle limits are configurable
LOCAL/TEST choices, not product facts or production tuning. Process-local bounded
throttling is intentionally a minimum executable abuse gate, not distributed
anti-abuse: restart resets counters and replicas multiply budgets. Sessions,
permissions and revocation remain canonical in PostgreSQL across restarts/replicas.

## Rejected alternatives and deferred work

JWT/localStorage or signed browser payload as canonical session would not meet
server revocation requirements. In-memory sessions would fail replica persistence.
A new IdP/SSO/email/SMS provider is unnecessary for synthetic login and would add
external configuration beyond scope. No generic auth-management SQL function,
new privileged role, Redis dependency, frontend, business mutation or Ops bypass.
Production TTL/abuse tuning, owner MFA/re-auth for future sensitive actions,
Platform Ops MFA/authorization, public enrollment/recovery, session inventory and
scheduled cleanup belong to separately issued work. LOCAL provisioning is not a
production onboarding service. Expired/revoked row cleanup is provisioning-admin
maintenance only in this slice, not a new Jobs subsystem.

## Sources read before implementation

Canonical: Spec 1.1,2,16.1/16.7/16.9,17.3/17.4/17.12/17.13,18.5,22.2;
ADR-002–006,107,109,116–117,119–120,125–126,160–161,194–195,206,216;
MVP topology/scope, Roadmap 5, Implementation Plan 5–6/9; AGENTS, M1_HANDOFF,
M1.1 contract, tenancy.v1 and accepted C8/guard regressions.

Primary implementation references checked 2026-09-16 (documentation, not test evidence):
- https://argon2-cffi.readthedocs.io/en/stable/howto.html
- https://pypi.org/project/argon2-cffi/25.1.0/
- https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html

Exact protocol, DDL/grants, error mapping and review obligations are in
`docs/tasks/M1_2_AUTH_CONTRACT.md` and `contracts/auth.v1.json`. Their existence
before DDL/API does not replace implementation/testing or authorize C5 to start.

## C0 disposition after review

C0 accepts this bounded implementation choice for reviewed head `194ea3cfa3f0aa9b8f271590a26ca3857ade3e54`, tree `799f271cbfc1c8815136828da35f9a32ef58b16e`, after the user-supplied targeted C8 PASS and full CI `35248449942`. Earlier proposal status is superseded at the implementation level, not by rewriting canonical architecture or inventing a production approval. The reviewed auth contract includes exact Host authority checks, rejection of discarded delimiters and post-commit response-loss recovery for C5.

C8 did not download the private CI archive or execute a fresh PostgreSQL run during re-review; C0 verified the existing archive/run. Full limits, finding disposition and the uncompleted integration gate are recorded in `docs/reviews/M1_2_BACKEND_C0_PREMERGE.md`. TTLs, local origins and process-local abuse limits are LOCAL/TEST implementation settings; production tuning and MFA remain outside this acceptance. No canonical LOCKED/DEFERRED/OPEN decision is silently changed.
