# M1.2 — C1 backend auth contract / C5 consumer handoff

Owner C1; integration C0; independent review C8, DDL/grants review C0/C2.
Exact base: `5c7188915fa219d9d6906569e2341632e4969651`.
Branch: `c1/m1-2-auth`; target main; no merge by C1.
This pre-DDL/API implementation contract is not an accepted architectural ADR,
production approval, task register or completion of the C5 part of M1.2.
IMPL-002 explains the new choices; canonical Spec/ADR and M1.1 prevail.

## Identity and cryptographic boundary

LOCAL/TEST synthetic username, not an email-verification claim: strip ASCII
space/tab/CR/LF, lowercase, then require ASCII `[a-z0-9][a-z0-9._-]{2,63}`.
Passwords are not trimmed or normalized. Provisioning requires 15–128 characters;
login accepts 1–128 characters, at most 1024 UTF-8 bytes. Extra request fields are
forbidden; account UUID, actor, role and permissions never authenticate a caller.

Use argon2-cffi 25.1.0 high-level PasswordHasher, Argon2id v19, m=65536 KiB,
t=3, p=4, salt=16 bytes, output=32 bytes. Random salts are library-generated.
No custom password-hash format or crypto algorithm. Standard-library secrets,
SHA-256, HMAC-SHA256 and compare_digest provide token generation/verifiers/CSRF.
The dependency change is limited to this library and its required transitive
packages; existing locked packages must not be upgraded.

Cookie token: secrets.token_urlsafe(32), exactly 43 base64url characters. Store
only SHA-256(token ASCII), never the bearer token, in PostgreSQL. CSRF value is
HMAC-SHA256(key=token ASCII, message=`asm.csrf.v1`), hex-encoded. It contains no
identity/permissions and cannot serve as a session credential. Derive it only
for a database-valid session; send it in no-store JSON, never URL or logs.
This is a session-bound CSRF proof, not signed client-side session state.

## DDL and grants reserved for review

Only migration `0003_auth_sessions.py`, revision `0003`, predecessor `0002`.
0001/0002, existing identity columns, tenant RLS, UOW guards and permission
semantics stay unchanged. Two migration-owned platform tables:

- `auth_credentials`: user_account_id UUID PK/FK RESTRICT to user_accounts;
  login TEXT UNIQUE with the normalization CHECK; password_hash TEXT bounded
  to Argon2id representation; positive BIGINT version; created_at timestamptz.
- `auth_sessions`: token_hash TEXT PK, 64 lowercase hex; nullable user_account_id
  FK RESTRICT; nullable credential_version/account_version snapshots (all three
  null for a pre-login session, all present for an authenticated session);
  created_at, expires_at, nullable revoked_at timestamptz. Expiry must be after
  creation. Account and expiry indexes. No tenant/domain/job/billing tables.

No direct table privileges for runtime/PUBLIC, including SELECT. No role,
bootstrap, ownership, DDL, BYPASSRLS or migration-credential changes for runtime.
All auth functions have fixed `search_path=pg_catalog,pg_temp`, fully qualified
relations, no dynamic SQL and PUBLIC EXECUTE revoked. Owner asm_migrator.
Runtime receives EXECUTE only on these fixed-purpose signatures:

```
platform.auth_password_lookup(text)
platform.auth_bootstrap(text,integer)
platform.auth_session(text)
platform.auth_memberships(text)
platform.auth_login(text,uuid,bigint,bigint,text,integer)
platform.auth_rotate(text,text)
platform.auth_logout(text)
```

An internal `platform.auth_lock_session(text,boolean)` returns the locked session
row to those functions; runtime/PUBLIC receive no EXECUTE on it. No function
accepts arbitrary SQL, arbitrary platform updates or an Owner fallback.
The login write accepts the adapter's already-verified identity/version, never
HTTP account claims. As in M1.1, compromise of runtime SQL/Python is outside the
claimed protection; these functions are not an identity proof to an attacker
holding runtime credentials. HTTP must never expose their parameters directly.

## Transaction and lifecycle contract

Pre-login sessions expire after 600 seconds by LOCAL/TEST default. Authenticated
sessions expire absolutely after 28800 seconds by default, configurable within
1–86400 seconds in this LOCAL/TEST implementation. No sliding expiry and no
rotation extending absolute expiry. These are new implementation settings, NOT
LOCKED production TTLs. Expiry decisions use PostgreSQL clock_timestamp().

Credential lookup ends before expensive Argon2 work. Unknown/disabled users get
the same dummy verification work and INVALID_CREDENTIALS response. Successful
verification is followed by an atomic active-account + credential-version +
account-version recheck and consumption of the pre-login session. Login always
creates a fresh random token; no promotion/reuse of the anonymous token.

Authenticated admission locks active account/credential rows FOR SHARE, then
session FOR SHARE, and validates version, expiry and revocation. Rotation/logout
use the same order and exclusive session locking; login locks the identity before
consuming its anonymous row. API operations keep a short auth transaction open
until the nested, unchanged M1.1 UOW completes. Separate bounded runtime-role
connection pools avoid nested-checkout starvation. No password hashing or external
HTTP inside either admitted transaction. Auth also rejects actual psycopg
AUTOCOMMIT before relying on locks, and verifies INTRANS before admission.

A revocation waits for an already-admitted short operation; after revocation
commits, later admission fails. Membership/workspace/account changes are checked
again by M1.1 and its locks. No claim to undo committed effects. Rotation is
single-use: exactly one concurrent consumer wins; the previous token is revoked.
If rotation commits before logout using the old token, that logout returns 401,
not false success; the client reloads current session and retries intentional
logout with the current CSRF. Failed/stale responses do not delete/replace a
newer cookie. Logout succeeds only after durable server revocation, then clears
the matching cookie. Credential version changes invalidate all earlier sessions.
No public credential-management or privileged Ops endpoint is introduced.

## Browser/API contract for C5

Only explicitly configured trusted origins; no wildcard/regex CORS or reliance
on arbitrary forwarded host/proto/IP. HTTP origins are loopback-only LOCAL/TEST;
TLS origins use `__Host-asm_session`, Secure, HttpOnly, SameSite=Lax, Path=/,
no Domain. Local HTTP uses `asm_session_local`, same flags except Secure.
C5 should use the existing same-origin frontend proxy and credentials:'include'.

Protected routes also require an exact normalized Host authority: lowercase
hostname plus effective port. An origin with an explicit port permits only that
port. Without one, HTTP means 80 and HTTPS means 443, so an absent Host port and
the matching explicit default are equivalent; the ASGI request scheme supplies
only that default and never adds an unconfigured port. The sole non-browser
exception is the Compose upstream authority `api:8000`; bare `api`, another port,
or browser Origin `http://api:8000` is not thereby trusted. Duplicate, absent,
empty, malformed, non-decimal or out-of-range Host ports fail closed. Bracketed
IPv6 is parsed as an authority, not split on `:`. Forwarded/X-Forwarded headers
do not alter the authority, scheme, origin or allowlist.

All mutations require exact trusted Origin, JSON content type and, except the
bootstrap protocol itself, X-CSRF-Token bound to the database-valid cookie.
Bootstrap requires `X-CSRF-Bootstrap: 1` plus exact Origin and JSON; this is a
non-simple CORS-protected request before a CSRF token exists. No state-changing
GET. Missing/null/hostile Origin on mutations fails closed; hostile Origin on
reads is rejected. Duplicate/malformed session cookies and oversized inputs fail
closed. Only server-generated correlation IDs reach the M1.1 UOW.

Endpoints, all under `/api/v1`:

| Method/path | Input | Success |
|---|---|---|
| POST /auth/bootstrap | `{}`; X-CSRF-Bootstrap: 1 | 200 `{csrf_token, expires_at}` and anonymous cookie; an existing valid session is retained |
| POST /auth/login | `{login, password}`; X-CSRF-Token | 200 current-session DTO and fresh authenticated cookie |
| GET /auth/session | cookie | 200 `{user_account_id, expires_at, csrf_token, memberships:[{workspace_id,role,permissions}]}` |
| POST /auth/rotate | `{}`; X-CSRF-Token | 200 current-session DTO, fresh cookie/CSRF, same absolute expiry |
| POST /auth/logout | `{}`; X-CSRF-Token | 204 after revocation, cookie deletion |
| GET /workspaces/{workspace_id}/businesses | candidate selector + cookie | 200 `{businesses:[Business]}` via M1.1 UOW |
| GET /workspaces/{workspace_id}/businesses/{business_id} | candidate IDs + cookie | 200 Business via M1.1 UOW |

Business DTO: workspace_id, id, name, status, version, created_at. No business
mutation is added. A membership response is informational, not a cached authority;
each protected operation re-resolves current membership/permissions. A downgraded
PROVIDER retains only tenancy:read, even if BusinessMember.role says OWNER.

Errors are `{error:{code}}`: 401 INVALID_CREDENTIALS or SESSION_REQUIRED;
403 ORIGIN_DENIED, CSRF_REJECTED or ACCESS_DENIED; 404 NOT_FOUND; 413 BODY_TOO_LARGE;
415 UNSUPPORTED_MEDIA_TYPE; 422 INVALID_REQUEST; 429 RATE_LIMITED; 503 UNAVAILABLE;
500 INTERNAL_ERROR. No reflected validation input, SQL details, usernames,
passwords, hashes, cookies, tokens or DB URLs. Authenticated/not-found distinctions
must not disclose a foreign Business. All auth/business responses are no-store.
On session 401, C5 clears displayed identity/data and offers login; never stores
bearer tokens in JS/localStorage. Keep CSRF only in current page state; bootstrap
before login, replace it after login/rotation, discard after successful logout.
CSRF failure does not automatically retry a mutation. No C5 start before C0
accepts and supplies an exact API SHA; this document alone is not that acceptance.

Database commit is not atomic with HTTP response or Set-Cookie delivery. A
transport error after login or rotation therefore does not prove rollback and
must not trigger a blind mutation retry. C5 first reloads current session: a
valid response supplies the current identity, memberships and CSRF; 401 clears
displayed identity/data, then C5 bootstraps and, when necessary, offers a new
login. Preserve an explicit logout intention across an uncertain response or a
401 from an old token after concurrent rotation. Recover current state and finish
logout with its current CSRF protocol; do not claim success from a network error
or blindly replay the stale mutation. The protocol does not promise exactly-once
Set-Cookie delivery, roll back committed state, extend DB-authoritative expiry,
or weaken single-use rotation/revocation and post-commit cookie issuance.

## Abuse, provisioning and tests

Bound streamed bodies to 4096 bytes before parsing and auth headers to 16384 bytes;
bound body-read time. Reject compressed/unsupported content and non-object JSON.
Per-process bounded fixed-window peer, login-identifier and global limits plus
non-queuing bounded Argon2 concurrency. No Redis. Defaults and replica/restart
limitation are explicit: counters reset on restart and budgets multiply with
replicas; canonical sessions, membership and revocation never use that memory.
Only hashes of throttle keys are retained; no secret-bearing request/access logs.

Provision with `scripts/provision_local_auth.py`, dedicated asm_migrator setup
identity, only explicit LOCAL/TEST and asm_local/asm_test; input password using
getpass on a terminal or a private file, never CLI password arguments or output.
Create a new synthetic owner/workspace/business, refuse existing login rather
than overwriting accounts. Output only non-secret IDs. No runtime provisioning,
public signup, real master data, provider accounts, production or paid calls.

Tests must exercise real PostgreSQL through actual runtime role: valid/invalid/
unknown/disabled credentials, persisted sessions across app instances, token
forgery/expiry/revocation/rotation, login/logout and cross-session CSRF, origins,
cookies, body/rate/concurrency bounds, redaction, foreign Workspace/Business,
live permission changes, grant restrictions and deterministic lock races.
Add fresh/M1.1 upgrade/replay/disposable downgrade/re-upgrade and schema/readiness
checks without weakening any of the 89 prior cases. Run architecture import and
full scripts/ci.sh; report actual tested SHA/tree/results, not intended coverage.
M1.3, all later domains, production identity/MFA/Ops and same-Workspace Client
security gates remain outside this backend-only handoff.
