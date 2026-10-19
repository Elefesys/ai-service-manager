# M3 native context: generic PostgreSQL RUN3 diagnostic and repair proposal

Task: **C2-M3.1-NATIVE-CONTEXT-GENERIC-PG-DIAG-R1**. Date: 2026-10-19 UTC.
Status: **REVIEW / proposal only; C2 HOLD after return**. This is not a second task
register. [C0 task6269039656](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6269039656)
and [final RUN3 disposition6268965488](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6268965488)
remain authoritative. **CI-06/P2 stays OPEN. No implementation or execution is
authorized by this document.** C6 separately owns CI-07 timing/evidence retention.

## 1. Conclusion and limits

The foundation log contains the exact ordered first **755 of 802 selected generic
integration nodes: 667 PASSED, 88 FAILED**. The remaining **47 are UNKNOWN**.
The first UNKNOWN node is announced without a terminal result; absence of the
other terminal records does not establish their setup/call/teardown state.
There are no generic exception tracebacks, JUnit, durations per case or completed
summary to recover. This report does not invent SQLSTATEs or an actual first
failing statement for any node.

Source/data analysis identifies nine incompatibility families covering every
observed failed ID. They are **source-supported blockers**, not 88 recovered
exception diagnoses. In particular, 56 failures reach a shared fixture that
sends a raw V1-shaped projection to the fresh codec2 writer on 0013. Five other
cases have an incomplete transactional TRUNCATE FK closure. Exact historical
schema/profile checks also run in current-head contexts. These facts do not rule
out product, transaction, authorization or concurrency regressions after the
test setup reaches its intended boundary.

The recommended repair separates **current 0013 / native OFF_UNUSED** tests from
explicit historical schema/source phases. Keep every original ID, assertion and
historical refusal/data/security obligation. Do not run the complete generic
suite only on frozen P, relax readiness to accept 0012, relabel a 42-table/132-
function checker as a 45-table/167-function checker, or alter production SQL to
accommodate a malformed test input.

Labels used below:

| Label | Meaning |
|---|---|
| OBSERVED | Terminal node status or other bytes actually present in RUN3 evidence |
| SOURCE | An independently located incompatible branch, literal, schema/ABI or FK edge |
| HYPOTHESIS | A plausible cause/order for the observed failure; original exception absent |
| OPEN RISK | Behavior still needs real PostgreSQL evidence; source analysis cannot close it |

## 2. Exact source and artifact bindings

All code line references below refer to prepared base **9ec5508e13a60962a4b2fded1d8a582cd1e6346b**.
The sole new repository path in this task is this report.

| Binding | Exact value |
|---|---|
| Prepared tree | `0ee72bb8ddd5975ab7876fccf68103f7d6e51e31` |
| Sole parent / frozen PR35 candidate | `59c9fce52bdaae54f50cdb847a378d47f75c642b` |
| Candidate and actual tested merge tree | `c5941d30aba59fe68f07b86f96c1cd8ae9c55c9a` |
| RUN3 merge | `b6cf7fb41297c18ad72da0e22f9694083f76737a` |
| Ordered merge parents | `e205e22051bc06295758b504d84699652b176c15`, `59c9fce52bdaae54f50cdb847a378d47f75c642b` |
| Run / attempt | `39256948310 / 1` |
| Foundation / native jobs | `118074513375 / 118074514069` |
| Own diagnostic branch | `c2/m3-1-native-context-generic-pg-diag-r1` |
| Frozen main / stock | `e205e22051bc06295758b504d84699652b176c15` / `af7482dede085bc033e3fee34f9a2425124351ee` |

The two ZIPs were downloaded read-only through GitHub. Their complete source
archives were independently checked against the candidate Git tree: **all292
file bytes and executable modes exact in each archive**. The prepared base
differs only in HANDOFF/register, +221/-2; its other290 leaves equal candidate.
The diagnostic checkout was reconstructed as the exact Git commit/tree, not
copied from an unverified moving sibling. Original11 attachments, repository
copies and SOURCE_MANIFEST are byte-exact. M3_CONTRACT remains769072 bytes,
SHA256 `fe2eb4ef2469ccb14b7147017c3c81066cde1b8a6ad60acbf73922a15e3ace5f`.
AGENTS, IMPL-001, the canonical M3 Spec/ADR/MVP/Roadmap/Plan and contract§16–16.20
were checked. In particular§16.7 and§16.15 require exact source/schema pairing,
OFF_UNUSED compatibility, preserved history and refusal before used downgrade.
Read-only GitHub run/artifact/job metadata and the actual merge Git header were
also retrieved: both artifact IDs/digests/sizes belong to RUN3/attempt1 and its
frozen candidate; the merge has the exact tree/two ordered parents above;
nine jobs succeeded and foundation is cancelled. PR35 remains Draft at candidate.

| Evidence file | Bytes where applicable | SHA256 |
|---|---:|---|
| Foundation artifact12191528180 ZIP |2626556|`e651e1120877459883c1e282b45036f95da748b8cbac6947dabd95ec58c37cf2`|
| Foundation `source.tar.gz` |2546480|`025aad7e8a0499f21f54bbc6b9b4fb95518263f6b526ab063c010d3bddbd6645`|
| Foundation `ci.log` /1678 lines | |`c1cef3187f7154de0090af5bea5d42ae084e65a4c2fc01c0aed40792ea8570c0`|
| Native artifact12188761326 ZIP |3320227|`ffcff8403820e12694d1027ce31cad907deb6cae6aeedd11a4e578f0c9142961`|
| Native `source.tar` |9861120|`98d0a2223e913514cbfbecbe9ebf70b0523ddde5543880fc012b118cc0cb8009`|
| Native `partition-generic-pg.json` | |`66d904173fbde7c088aa0983f228d9a11dcd96d196cceb20c7abefa0edfb7c2f`|
| Native `test-results.json` | |`ba897f387e463bdbad82590b064c545f9fd7f464af23e2e8e1d86cbcb9704400`|
| Native installed catalog JSON text | |`2a565378c567913ba29daf1f07d0a880e11c7b2ebfe80034411ecef148d776df`|
| Native typed functions/OID JSON | |`17a2ee6b6938faae64fd956267363a256298ce6da585adb32b5dc691546382b5`|

The candidate's pure `source_catalog()` expansion equals the archived expected
catalog. Re-executing only the frozen **data comparators** over the saved catalog,
typed function/OID and role data passes:167 functions,45 tables,635 columns,
full profile `c045a59f86201a244ed0d43fbe22aa8cd72fddd346d770706c6ab3b92ee9a411`,
nonfunction `57e03fe369be4bd03116ce380e37a9b447a2bc1a72e3bbf2a70c7ac08d69e370`,
verifier body `527fce5681d5345369cd88b555a302df6d305ef8566cf12a666198eb64a6f4ac`.
Backend0013/profile/verifier constants match that source. All three frozen
CI_INPUT_SHA256 file bindings pass. All four saved entrypoint diagnostics
(run/carrier/catalog/cleanup) say PASS at the exact merge/ordered parents, and
all four archived API/worker/scheduler/fixture image proofs bind that same tree.
These are source/data rechecks of **earlier actual evidence**, not new DB,
image, event admission or runtime execution.

Final clean-source pairing additionally checks the four **source components**
api/worker/scheduler/console from provisioning.NATIVE_COMPONENTS against the
final Git manifest and unchanged backend/profile/verifier constants. The exact
native_host_source function body is AST-loaded with constructed source-only
inputs, without importing the product or opening a DB. This is a constructed
pure source probe, not C0 operator approval or an observation of running binaries.
Its four final component digests are returned in the receipt.

Native evidence independently contains112 setup+112 call+112 teardown PASS,
105 guarded resets, no missing nodes. Its 7 source+105 PG nodes remain disjoint
from generic802 and complete the907 integration partition. Native success is
not substituted for any failed/unknown generic result. Foundation archived
worktree status is empty; its skipped clean-source workflow step remains SKIPPED.

## 3. Exact inventory and reproducible extraction

Foundation `ci.log:913` records the907=802+105 partition; generic selection is at
`ci.log:921`. Terminal records run from923 through1677. First FAIL is1019; the
final announced node is1678 without outcome. C0's timestamped job log puts the
first FAIL at13:26:51Z, well before13:48:51Z cancellation. The plain artifact log
has no timestamps of its own; none are synthesized per node here.

Every digest in this table hashes UTF-8 **ordered node IDs, one per line, with
one trailing LF**. These differ intentionally from the runner's JSON inventory
serialization digest (`generic=25f19498e106d1718aec8b6f5a6f1f17277459e5b85090aa0d31db777da4d80c`).

| List | Count | Ordered LF SHA256 |
|---|---:|---|
| Full generic |802|`bde64cc7fbfd35daa02e8141adcaec0723427ed6c2cfeef4b5e15402e8b1d283`|
| Observed ordered prefix |755|`9aaf2ced3ea828c957ad3532fd1f3efe27b1ba0e463543b17bbe90ac3ee016cf`|
| PASSED |667|`f6e78b5b17a819a503431d0d62a56fea583cc5e8d01ec96c377799990f1a3a43`|
| FAILED |88|`0f04384f29b21192fc1a909de516a2e70d2c80254481b634bc86c4017179ea70`|
| UNKNOWN |47|`bbd59e4461a9e82263839276c5e69fbc8855db4f7d3e82b3d34b3179aab30f13`|

The following standalone **data-only** recipe regenerates the entire802-row
coverage map,88 IDs and47 UNKNOWN IDs after the two ZIPs are extracted as
`foundation/` and `native/`. Run it outside the repository. It does not import
the product, collect tests, create engines or set up fixtures. Appendix A lists
the complete observed88; Appendix B lists the complete47 UNKNOWN.

```python
import collections, hashlib, json, re
from pathlib import Path
f, n = Path('foundation'), Path('native')
assert hashlib.sha256((f/'ci.log').read_bytes()).hexdigest() == 'c1cef3187f7154de0090af5bea5d42ae084e65a4c2fc01c0aed40792ea8570c0'
assert hashlib.sha256((n/'partition-generic-pg.json').read_bytes()).hexdigest() == '66d904173fbde7c088aa0983f228d9a11dcd96d196cceb20c7abefa0edfb7c2f'
nodes = json.loads((n/'partition-generic-pg.json').read_text())['nodeids']
assert len(nodes) == len(set(nodes)) == 802
seen = []
for line_no, line in enumerate((f/'ci.log').read_text().splitlines(), 1):
    m = re.fullmatch(r'(tests/.*) (PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\s+\[\s*\d+%\]', line.strip())
    if m and m[1] in nodes:
        seen.append((m[1], m[2], line_no))
assert len(seen) == len({r[0] for r in seen}) == 755
assert [r[0] for r in seen] == nodes[:755]
assert collections.Counter(r[1] for r in seen) == {'PASSED': 667, 'FAILED': 88}
rows = seen + [(node, 'UNKNOWN', None) for node in nodes[755:]]
assert len(rows) == 802 and sum(r[1] == 'UNKNOWN' for r in rows) == 47
Path('coverage802.tsv').write_text('nodeid\tstatus\tci_log_line\n' + ''.join(f'{a}\t{b}\t{c if c else ""}\n' for a,b,c in rows))
for name, selected in [('generic802', nodes), ('failed88', [r[0] for r in rows if r[1]=='FAILED']), ('unknown47', [r[0] for r in rows if r[1]=='UNKNOWN'])]:
    data = ('\n'.join(selected)+'\n').encode()
    Path(name+'.txt').write_bytes(data)
    print(name, len(selected), hashlib.sha256(data).hexdigest())
```

## 4. Shared fixture and import paths

AST-only import closure analysis followed absolute **and relative** repository
imports, including function-local imports and cycles. No test module was imported
or fixture executed. It covers all14 failed roots and all3 UNKNOWN roots (17
roots total). External packages are boundaries, not claimed local definitions.
Function-local imports in the migration helpers reach each other; the graph is
not simply fourteen independent fixtures.

| Chain | Exact source reference / use |
|---|---|
| `db → seeded` | `tests/test_tenancy_postgres.py:30,47`: TEST URLs, current RuntimeDatabase.check, real two-workspace/user setup and scoped cleanup |
| `seeded → messaging` | `tests/test_m2_1_postgres.py:116`; `provision:45`, `cleanup:66`, actual kernel/Worker; no native-policy enable |
| `messaging → telegram` | `tests/test_m2_3_db_postgres.py:303`; real binding/billing; `cleanup_material:157` precedes retained parent cleanup |
| `telegram → control` | `tests/test_m3_1_control_postgres.py:31`; E/guard/CONTROL children explicitly removed before Telegram parents |
| `auth + control → api` | `tests/test_m3_1_control_api_postgres.py:60`; actual AuthStore/tenancy pools, cookie/CSRF login, Refresher and HTTP routes; `test_auth_postgres` imports the same seeded baseline |
| Telegram input path | `test_m2_3_db_postgres.ingress:188 → sql:92 → platform.telegram_ingest`; `receive:223` uses ingress; `control.incoming:126` delegates its TELEGRAM branch to ingress |
| Current product input path | `backend/src/asm/telegram/database.py:48`: saved-V1 replay first, then normalize_update_v2, then `ingest:62`; unlike the broken raw fixture, production does select codec2 |
| Historical migrations | `test_m2_1_schema_postgres._migrate` plus module-local `migration()` loads exact0007/0008/0010/0011/0012; G imports C columns, E imports G, P imports E, strict material profile imports P |
| Independent M1 roots | `test_m1_3_c0_acceptance.engines:46`; `test_m1_3_postgres.migrator:20`; no Telegram dependency for these failures |
| M0/current capability root | `test_postgres.database:21 → RuntimeDatabase.check`; probe:38 creates and removes its own RLS table |
| UNKNOWN roots | `test_tenancy_migrations` has its own Alembic subprocess lifecycle; `test_tenancy_postgres` owns db/seeded; `test_tenancy_transaction_guard` imports them and instruments only ContextVar publication |

Transitively, the families reach current `asm.foundation`, tenancy UoW/repository/
transaction guards, billing/entitlement services, MessagingDatabase/Worker,
Telegram normalization/ingress, CONTROL/GUARDS/ESCALATION/MATERIAL/native parsers,
and the exact migration source modules. The proposed fix must not fork these
authorities. Appendices bind each failed/unknown node to its exact definition
line, fixture chain and family; the full802 inventory remains the artifact list.

## 5. Failure families and source-supported repair boundaries

### F1 — transactional TRUNCATE FK closure (5 FAIL; C2)

`tests/test_m1_3_c0_acceptance.py::test_initializer_conflict_has_no_catalog_or_workspace_side_effects:144`
uses `engines`, then at151–173 truncates22 named relations in a transaction,
before testing missing-workspace/partial/input/null-code/null-revision conflicts.
Current0013 adds referencers that the list omits. The actual archived catalog
contains these immediate omitted edges:

| Omitted referencing table | Referenced truncated relation / constraint |
|---|---|
| `platform.human_context_observations` | telegram_provenance / `human_context_observations_workspace_id_first_source_recei_fkey` |
| `platform.human_context_policy_receipts` | audit_events / `human_context_policy_receipts_workspace_id_audit_event_id__fkey` |
| `platform.human_context_reconciliations` | audit_events / `human_context_reconciliations_workspace_id_audit_event_id__fkey` |
| `platform.inbox_events` | telegram_provenance / `native_inbox_source_fkey` |

Sources: `migrations/versions/0013_native_context.py::_schema:1041`, especially
1068/1082/1125/1156/1180–1192. FK closure is structural, even with no native rows.
Adding only the three native tables is insufficient: the complete omitted
closure has **nine** relations: app.conversation_turns, app.conversations,
app.messages, app.outbox_events, platform.human_context_observations,
platform.human_context_policy_receipts, platform.human_context_reconciliations,
platform.inbox_events, platform.telegram_update_receipts.

SOURCE: the22-table set is not closed under current FK references. HYPOTHESIS:
TRUNCATE fails before INITIALIZE; no original SQLSTATE is asserted here. Repair
only this owned TEST transaction's explicit list by the reviewed nine-table
closure, keep rollback and every conflict/before=after assertion, verify full
current-state/catalog restoration. No CASCADE, trigger disabling or native usage
deletion to permit downgrade. Confirm catalog/constraint names on a separately
authorized diagnostic DB before implementing.

### F2 — exact billing/Audit physical inventory (1 FAIL; C1 with C2 review)

`tests/test_m1_3_postgres.py::test_exact_physical_schema_constraints_keys_and_grants:366`
uses its independent migrator. `PHYSICAL_COLUMNS:151` still has the P Audit
columns. Lines384–404 compare the entire ordered list; lines405–457 also compare
defaults/generated expressions. `_schema:1082–1097` adds four stored generated
UUID columns: native_revision_id, native_policy_receipt_id, native_connection_id,
native_conversation_id. Thus changing the table count alone cannot repair it.

Repair the **current** exact Audit inventory and four exact generated CASE rules,
including nullable/type/order/stored properties and event/payload targets. Keep
all old defaults, tenant-safe keys, FK actions, exclusion/CHECK constraints,
forced RLS and runtime grant denials (458–554). The actual first assertion and
whether other constraints/grants fail remain OPEN; do not weaken equality to a
subset or broaden runtime privileges.

### F3 — fresh Telegram fixture ABI (56 FAIL across7 modules; C3)

`test_m2_3_db_postgres.ingress:188–200` converts raw `projection:50` through
`v2_fixture:97` **only when revision==0012**. On current0013 it sends the raw
projection unchanged. The effective writer retains the saved-V1 branch first
and then `telegram_validate_v2` for fresh keys (`0013_native_context.py:18–37`,
extended by `_observation:1459–1479`; V2 closed shape in
`0012_message_provenance.py:591–593`). A fresh raw fixture has no codec marker,
discriminator/origin/content envelope required by that ABI.

| Module / observed FAIL | Distinct path to the shared seam / intended phase |
|---|---|
| `test_m2_3_db_postgres.py` /29 | ingress directly or receive→ingress; current0013 OFF; then dedupe, binding, lifecycle, CAS, preflight, billing, expiry,429/cursor/hash/observation assertions |
| `test_m2_3_schema_postgres.py` /2 | ingress:294 before forged-FK checks; receive:392 before old0007 refusal; the latter also hardcodes0012 at406 |
| `test_m3_1_control_api_postgres.py` /12 | incoming TELEGRAM:200/312/440 before real HTTP lock/product/refresh-interleaving assertions |
| `test_m3_1_control_postgres.py` /6 | incoming TELEGRAM:126; first incoming:562 fails before the later explicitly V2 held-ingress path:581; other wrappers at619/712/759 reach the same helper |
| `test_m3_1_guards_postgres.py` /1 | incoming TELEGRAM:669/671 before checking no automated send plan/probe |
| `test_m3_1_migrations.py` /2 | genuine0007 raw ingress:544, finally upgrade head:546, then fresh key at561/577 needs codec2; old saved V1 origin and payload winner must remain exact |
| `test_m3_1_turns_postgres.py` /4 | first held ingress:599 already explicitly V2; **second** ingress:608 uses the broken helper, before the share-barrier/commit-vs-rollback assertions |

Small repair: the fixture explicitly recognizes both accepted codec2 revisions
`{'0012','0013'}`, leaving exact predecessor raw writers and already typed input
unchanged. Do not use an open-ended `revision >= ...` or modify production
validation. Preserve saved-V1 replay before fresh V2 parsing and V1 fingerprints;
`legacy_v1` is retained by v2_fixture, not replaced with reconstructed text.
F3 schema-refusal node also requires F4's current-marker postcondition.

**Additional coverage risk among PASSED nodes:** three
`test_any_ingress_write_failure_rolls_back_whole_receipt_inbox_job` variants at469
only require DBAPIError (483–490), while the injected trigger raises `test write
failure` (474). A codec rejection can satisfy that test before its injected write.
Nine malformed-input cases at1013 can likewise reject an already invalid
baseline before their specific mutation matters. Their12 PASSED records remain
PASSED observations, but cannot prove those target branches were reached.
Require a valid positive codec2 control and a trigger/error-origin witness in
the future focused validation, retaining all rollback assertions/IDs.

OPEN RISK: correct input may still expose bugs in receipt atomicity, product
precedence, billing/window expiry during waits, no-send behavior, CAS, shared
locks, earliest committed origin or duplicate payload ordering. None of those
behaviors is established by a fixture rejection or closed by this report.

### F4 — current-head postcondition after old Turn refusal (3 FAIL; C2)

`test_m3_1_migrations.test_populated_refusal_is_before_destructive_ddl_and_preserves_exact_snapshot:584`
creates actual mark/membership/receipt usage and directly invokes frozen0008
`migration().downgrade()` under a savepoint (604–608). After requiring55000, it
calls `assert_head(c,'0012'):611`; `assert_head:439` excludes0013. This is not a
full Alembic downgrade from0013 to0007. The direct refusal is supposed to leave
the **entry schema** intact.

Add an explicit0013 current postcondition/full45-row-and-DDL snapshot bridge;
do not make the strict0007/0008/historical schema inventories accept arbitrary
successors. Keep55000, no destructive statement, all original row/function/grant
equalities, and the exact old-cycle tests. Apply the equivalent correction to
`test_m2_3_schema_postgres.py:406` after its F3 input is repaired. It is not yet
known from original tracebacks whether either refusal actually reached55000.

### F5 — G/E refusal dispatch stops at old successor (6 FAIL; C2)

Four G usage variants at `test_m3_1_guards_migrations.py:188` call
`assert_refusal:108` with revision0011 at203. That helper dispatches to
`test_m3_2_escalations_migrations.assert_schema:58`, which recognizes0012 by
delegation to strict P and otherwise asserts0011:69. The two E used/terminal
variants at184 call E `assert_refusal:112`, then the same schema checker.
Current0013 is outside both dispatch paths.

Use a separate current0013 entry/recheck and full45-table/catalog fingerprint
around the actual old0010/0011 downgrade refusal. Keep original strict C/G/E/P
checkers, snapshots,55000, Audit/receipt links, terminal-decision invariants and
private clock/ACL checks. No old migration source change is proposed. Whether
there is an earlier downgrade-function or result-schema failure is unresolved
until the focused real diagnostic records it.

### F6 — exact E profile executed at current head (1 FAIL; C2)

`test_m3_2_escalations_migrations.test_exact_e_profiles_private_clock_forced_rls_and_no_runtime_raw_access:193`
calls the same strict E/P `assert_schema` at197, then checks exact E function/OID
inventory, private clock, runtime raw denial and forced RLS (198–292). Keep that
historical E profile assertion on its explicit0011 phase. Check current E
behavior/permissions at0013 using the accepted full167/45/635 source profile;
do not strip the exact clock/grant/security assertions or accept only an
E-named subset on current head. The existing61 E runtime+9 E API generic cases
continue on current0013 OFF. No production failure is proven by this mismatch.

### F7 — P profile/refusal plus process-schema pairing (7 FAIL; C2+C3+C1)

`test_m3_1_provenance_migrations.assert_schema:72` asserts0012 and all42 exact
column lists. The fresh-profile test:113 invokes it at117 on generic head0013.
Five used variants:289 invoke the actual0012 downgrade at313 and call it at317.
Their snapshots cover the P42 projection, not all current45 relations.

The populated0011→0012 cycle:161 is a **different** problem as well: it explicitly
upgrades to0012:241–242 and calls `h.runtime.check():243`. Current candidate
`backend/src/asm/foundation.py:36` requires0013; its check:203–208 validates the
exact native profile. A current process should refuse0012. Merely accepting0013
in assert_schema would neither fix nor preserve this historical compatibility
test. Earlier failures in the cycle are not excluded by source inspection.

Retain P's exact0012/42 columns,132 typed functions, used55000/no-DDL, repeat
upgrade, unchanged old rows/definitions/triggers/indices, no backfill and saved
V1 replay obligations in an explicit historical phase. Use the exact accepted
P source/checker (`e205e22051bc06295758b504d84699652b176c15`) for its positive
0012 readiness assertion, in an isolated process with actual import identity
and source-byte proof. Independently require the current0013 process to refuse
0012 and to accept restored0013. Do not import mixed old/new packages into one
process or relax DATABASE_SCHEMA_REVISION/profile verification.

For current compatibility, retain/add current0013 OFF subphases for real V2
MATERIAL input, unchanged old receipt/V1/V2 bytes and full current-state refusal
fingerprints. A historical phase is a scoped part of these existing tests, not
the schema for the entire generic suite. The exact phase fixture/process
boundary must be confirmed by the authorized diagnostic before code issuance.

### F8 — exact table set stops at42 (1 FAIL; C2)

`test_postgres.test_real_postgres_capabilities_and_roles:75` correctly exercises
runtime/migrator roles, uuidv7/vector and no TEMP, then compares the entire table
list at108–151 to42 P relations. Current source/catalog has those42 plus
human_context_observations/reconciliations/policy_receipts. Update the current
closed45-table expectation; retain every role/extension/capability and no-extra-
table assertion. A permissive subset/count-only check is not an alternative.

### F9 — strict0012 egress compatibility helper on0013 (8 FAIL; C2+C3, C6 pairing)

`TestEgressMaterialCompatibility` at `test_telegram_egress_postgres.py:2111` has
one profile/V2-off/DTO/snapshot node and seven used-material witnesses. The
profile test calls `material_catalog_profile:1644` at2121; that calls strict P
assert_schema at1648 and compares exact132 old bodies/OIDs/ACL/policies. Used
cases call `material_used_refusal:1779` at2197; its
`canonical_fingerprint(c):1788` asserts revision0012 at803 before performing
the guarded downgrade. Successful0012 readiness at2199 also belongs to the old
P process; current readiness is0013.

Keep `canonical_fingerprint`, `material_source_profile`, `material_catalog_profile`,
`material_exact_columns`, `material_used_refusal`, historical schema controller
and accepted frozen-P lane bytes/semantics strict. Existing
`current_durable_fingerprint:828` already supplies a distinct current45-table
snapshot; use a current wrapper for current assertions instead of widening the
historical functions. Preserve **both** an explicit historical0012 paired phase
and a current0013/native-OFF phase for each applicable compatibility obligation.
All eight IDs, witnesses (codec-off,enabled,target,effect-Audit,suppression-member,
material-result,invalidated-Turn), exact no-DDL proof, DTO/V2 snapshot/receipt
replay, delivery UNKNOWN and private File/winner/tenant/security invariants stay.
Current-source/current-schema and historical-source/historical-schema proofs
must be separately named. Reusing a prior P lane PASS cannot supply current
generic evidence.

## 6. The47 UNKNOWN and security obligations

| Group | Nodes | Intended phase / exact references | Proposed owner / disposition |
|---|---:|---|---|
| U1 |1|`test_tenancy_migrations.py:31`: current head↔base, explicit0001 refusal, current readiness/service and preserved data/extension assertions; migrate:18 uses real Alembic subprocesses |C2+C1; no speculative edit; first node announced, outcome UNKNOWN |
| U2 |38|`test_tenancy_postgres.py`: db:30/seeded:47; all raw tenant/Client authorization, missing/malformed/xid context, composite FK, CAS, pool reuse/cancellation/revocation/rollback/oracle/RLS-off checks |C2+C1; all UNKNOWN, preserve exact assertions and current0013 default |
| U3 |2|same file `test_runtime_roles_policies_functions_and_platform_surface:443` and `test_real_schema_matches_contract_and_constraints:858` |C2; UNKNOWN, not classified as stale inventories |
| U4 |6|`test_tenancy_transaction_guard.py:74,142,188`; seeded+publications:36; actual autocommit rejection, no premature ContextVar publication, physical binding/error rollback and prepublication mismatch |C1 with C2 review; all UNKNOWN, no current write proposed |

U2+U3 comprise40 nodes, not42. The U3 runtime inventory **already has explicit
0013 native function/OID/ACL handling** (`test_tenancy_postgres.py:730–854`),
including35 native signatures and exactly four public capabilities. Its app
table set is unaffected by the three new platform tables. The contract check at
858 compares the frozen tenancy semantic tables/keys; it is not a stale full-P
catalog assertion. Source inspection supplies no basis to change either to get
a green result. U1's current-head readiness matches the candidate0013 constant,
unlike F7's explicit0012 success assumption. Native's retained security tests do
not prove this entire47-node tail. Appendix B preserves every ID.

## 7. Smallest coherent proposed write-set (NOT authorization)

C0 should first accept the taxonomy and obtain the missing bounded diagnostic
facts in§8, then issue these separate scopes. They have shared dependencies and
must converge into **one reviewed current source** before the complete gate.
The write-set below is a concrete proposed maximum, not permission to edit it.
No backend/SQL/migration/API/contract/lock/workflow/Compose/pin change is justified
by the evidence available here.

| Owner / proposed file | Exact function/constant boundary | Purpose / dependency |
|---|---|---|
| C3: `tests/test_m2_3_db_postgres.py` | `ingress`; targeted error-origin assertion in `test_any_ingress_write_failure_rolls_back_whole_receipt_inbox_job` |Explicit codec2 for0012/0013, frozen old writers/replay; preserve all negative cases and prove injection reached. First dependency for F3 callers |
| C2: `tests/test_m1_3_c0_acceptance.py` |only TRUNCATE construction in `test_initializer_conflict_has_no_catalog_or_workspace_side_effects` |Reviewed nine-relation closure, transactional rollback and full restoration; retain existing TABLES conflict semantics |
| C1+C2: `tests/test_m1_3_postgres.py` |`PHYSICAL_COLUMNS['app.audit_events']`; generated-column branch in `test_exact_physical_schema_constraints_keys_and_grants` |Exact four0013 additions/expressions, no weakened constraints/grants |
| C2: `tests/test_postgres.py` |closed table literal in `test_real_postgres_capabilities_and_roles` |42→explicit45 current inventory, all other checks unchanged |
| C2/C6, C1 review: proposed new `tests/generic_pg_schema.py` |`assert_current_schema`, `current_state_fingerprint`, `historical_schema_phase`, `assert_paired_historical_readiness` |Small immediately used fixture bridge: closed0013 source/catalog/rows checks; explicit known unused-native downgrade/restore; exact P subprocess identity. No global/autouse rerouting or native admin/reset opt-in |
| C2: `tests/test_m2_3_schema_postgres.py` |`test_downgrade_refuses_55000_before_first_destructive_statement` postcondition |After F3, preserve actual entry0013/full current snapshot and old0007 refusal; old0006→0007 cycle unchanged |
| C2: `tests/test_m3_1_migrations.py` |`test_populated_refusal_is_before_destructive_ddl_and_preserves_exact_snapshot`; explicit current branch of `assert_head` if needed by that caller |Current marker and full45 rows/definitions after direct0008 refusal; old H/I checker and all phase controllers remain exact |
| C2: `tests/test_m3_1_guards_migrations.py` |current branch of `assert_refusal` and its `test_any_guard_usage_refuses_before_ddl_and_preserves_full_g` call |Full current post-refusal proof; strict C/G/P functions and controller frozen |
| C2: `tests/test_m3_2_escalations_migrations.py` |current branch of `assert_refusal`; phase boundary of `test_exact_e_profiles_private_clock_forced_rls_and_no_runtime_raw_access` |Current full snapshot for refusal; explicit historical E profile plus current E security coverage; old strict schema/clock/profile bodies unchanged |
| C2+C3, C1 readiness review: `tests/test_m3_1_provenance_migrations.py` |phase boundaries of `test_fresh_head_full42_columns_profiles_rls_and_no_unused_backfill`, `test_populated_0011_repeat_upgrade_and_exact_unused_reverse`, `test_owned_used_refusal_precedes_every_ddl_and_preserves_all42` |Pin strict P checks to0012, preserve132/42/profile/refusal/history; current0013 OFF counterpart and current-process mismatch proof. Keep `P_COLUMNS/assert_schema/fingerprints/catalog` exact |
| C2+C3, C6 pairing review: `tests/test_telegram_egress_postgres.py` |two `TestEgressMaterialCompatibility` test methods; narrowly named current helper if existing current fingerprint is insufficient |Separate current45/167 and historical42/132 phases; keep all eight IDs/witnesses and frozen P/controller helper bodies |

This is **10 existing test paths plus one proposed helper path**. C3 input repair
should remove the need to edit the other control API/CONTROL/GUARDS/Turns F3
callers. `test_tenancy_*` UNKNOWN tests, production modules and all native112
carrier sources stay outside this proposed write-set unless a distinct actual
finding is returned to C0. C6's separate timing/evidence proposal owns any later
launcher/CI source/hash/required-job changes; they are not hidden in this list.

The phase helper must refuse if native0013 has been used (P>0, observations,
reconciliations, links/V3 inputs/work markers/Audit), never delete that evidence
to downgrade. Dispose participating pools before schema changes, use only the
same owned TEST database, retain every real data/receipt/winner/refusal
assertion, and restore exact current0013 before ordinary dependent fixtures or
later tests run. Verify source imports in each subprocess. No shared external
DB/cache/P checkout or mixed Python package versions may be assumed. Reuse the
already accepted frozen-P **source identity discipline**, not another job's
live resources. If that minimal helper cannot preserve the historical semantics,
return the conflict to C0; do not introduce a general schema-runner framework.

Any actual defect in producer behavior, native-off compatibility, FK semantics,
privacy/authorization, lock ordering or migration refusal uncovered after valid
setup is a **separate production finding**. It requires C0's new contract/review
and bounded implementation scope. This report does not authorize changing0013,
adding0014, editing applied migrations or widening a parser/readiness/grant.

## 8. Required diagnostic facts and RED→GREEN validation

There was **no PostgreSQL/Docker/service/Actions execution in this task**. The
following is a proposed next sequence for C0, with no implicit approval:

1. Authorize one bounded, owned LOCAL/TEST diagnostic at the exact candidate
   source. Record actual source/schema/role/profile at each selected case's
   entry, and retain sanitized failure location/SQLSTATE/constraint plus
   setup/call/teardown outcomes as they occur. No DSNs, locals, credentials, raw
   events or arbitrary SQL payloads in public evidence. C6 owns interruption-safe
   recording. Do not patch source during a run. Constructed valid-V2 diagnostic
   calls are explicitly labelled; they are not a green result for an unmodified
   failed test or a substitute for the complete suite.
2. Capture the following focused RED facts before implementing the proposed
   fixture changes; after source review, run the same IDs/parameters to GREEN,
   retaining every original assertion. All original88 and all12 potentially
   vacuous PASSED negatives must be included in the later family validation.

| Family | Minimum discriminating diagnostic / later required result |
|---|---|
| F1 |one `partial` conflict case; actual failing TRUNCATE edge; closed31-relation transaction reaches INITIALIZE conflicts; rollback restores all current rows/catalog |
| F2 |exact physical schema node; first differing Audit column/default, then all ordered columns/generated expressions/keys/grants PASS |
| F3 |raw fresh vs already typed V2 input at0013; receipt-dedupe node, TELEGRAM share-barrier variant, TELEGRAM HTTP wait case, old0007→head duplicate-first; all56 later reach their actual target behavior; all12 negatives prove the intended rejection/injection |
| F4 |`mark` and `receipt` direct0008 refusals plus old0007 schema-refusal case; actual55000/no-DDL and unchanged0013/full45 state; retained old cycles still exact |
| F5 |G `profile` and `terminal_rejection`, E terminal=True; verify55000 precedes every DDL and all current/historical snapshots match the intended phase |
| F6 |exact E profiles/private-clock test; strict0011 phase and current0013 E security counterpart, no raw runtime access |
| F7 |fresh-P profile, populated0011→0012 cycle, `enabled-only` and `effect` refusal witnesses; distinguish current-process refusal on0012 from actual old-P positive readiness; preserve old42/132 bytes and restored45/167 |
| F8 |current capabilities/roles node; exactly45 tables plus all role/extension checks |
| F9 |profile/V2-off/DTO node plus `effect-audit` and `invalidated-turn`; current full snapshot and strict historical P proofs are distinct; all seven usage-witness/refusal cases retained |
| U1–U4 |announced full lifecycle node, representative raw cross-tenant and runtime-surface nodes, autocommit/binding guard; every47 UNKNOWN subsequently requires its own terminal outcome |

The missing original exceptions, possible earlier refusal/setup failures, actual
generic database state after each historical cycle, correct phase teardown and
reachable target failures after codec repair are unresolved assumptions. Obtain
these bounded PG facts **before** finalizing implementation scopes. Do not infer
that corrected input will make the concurrency/authority/security assertions
pass. Do not invent a complete run duration or use a diagnostic subset to close
CI-06; there is no additional retry/cap budget created here.

3. C0 accepts exact disjoint write scopes. Review the input fixture, current
   inventories/FK closure and phase/pairing helper together; never land only an
   equality relaxation. Preserve all802 IDs and the module totals in Appendix C.
   If meaningful additional coverage is accepted, inventory it explicitly; no
   existing ID may disappear. Verify old fixture/import/authority assertions,
   closed schemas, exact historical132/42 and current167/45/635, all applied
   migration/source/original11 hashes, and dependency/CI source pairings.
4. Separately authorize the **complete** current-source generic802 gate, with
   scoped historical phases only where required, plus the full native112 cases /
   336 phases /105 guarded resets and independent167/45/635 catalog/roles/ACL/
   verifier/cleanup. Preserve907 disjoint integration coverage, all1999 unit
   cases+130subtests and the full migration/base→head/contracts/wheel/service/HTTP
   tail. Native/state/old-P results do not replace generic cases. C6 must make
   complete evidence possible within existing caps before another whole CI gate.
5. C0 reviews actual complete results and retains CI-06/CI-07 OPEN until their
   respective criteria are met. User owns merge. No new PR or main/PR35/stock/
   old ref movement is part of this diagnostic.

No change is proposed to foundation45min, native20min/payload1080s, state/browser25,
S/600/P720/fixed120/supervisorS+1200/cleanup90 or individual caps. No clocks reset,
charging subtraction, resource adoption, skips/xfails/filter-based acceptance,
retries or broad IMPL-05 optimization. The task's sole delivery is this report.

## 9. Actual local commands and verification boundary

Local analysis used Python3.12.14 standard library, Git and repository source/data
only. The previous scratch checkout/environment had been pruned; no cache or
frozen Python3.13 environment was assumed, installed or reused. No pytest
collection was needed: the complete actual frozen-Python3.13 RUN3 partition
was already in the verified artifact. No test/fixture was executed locally.

The source import ran before the checkout existed; the remaining commands ran
from that isolated checkout. Final successful commands were:

```text
python /workspace/scratch/a8cb049d01c4/c2-generic-pg-diag-r1-evidence/import-source.py
cd /workspace/scratch/a8cb049d01c4/c2-generic-pg-diag-r1
git rev-parse HEAD HEAD^{tree}
git status --porcelain=v1
python ../c2-generic-pg-diag-r1-evidence/extract-results.py
python ../c2-generic-pg-diag-r1-evidence/analyse-source.py
python ../c2-generic-pg-diag-r1-evidence/append-mapping.py
```

All exited0 after validating the extraction's whitespace-tolerant pytest terminal
record regex. The source analysis uses AST to follow local imports without
importing tests, expands SQL through the frozen capture_source/source_catalog
stubs, invokes require_ci_inputs and the data-only compare_catalog/compare_roles
over archived JSON, and computes the TRUNCATE FK closure from archived constraints.
It invokes **none** of run/carrier/catalog/cleanup/generic-integration DB entrypoints.
The final constructed four-component source probe uses
`source-pairing.py <clean-checkout>` against the delivered commit; it AST-loads
only NATIVE_COMPONENTS/ProvisioningError/native_host_source with deferred
annotations and standard-library inputs, then calls the unchanged pure source
checker. No fixture/product module or DB driver is imported by that probe.
Local source facts are not claimed as actual PostgreSQL RED/GREEN. Diagnostic
scripts are temporary analysis outside the Git checkout; the extraction recipe
above is reproduced in this durable report.

The delivery receipt records the final report SHA256/commit/tree/sole parent,
one-new-file diff, all292 existing bytes/modes exact, original11 and profile
source pairing, whitespace checks and final clean checkout. Only the own task
ref may move by expected-base normal FF; all execution/protected refs remain
frozen. No other agent/chat was used.

<!-- GENERATED_APPENDICES -->

## Appendix A. All88 observed FAILED IDs

The line column locates the exact test definition/function in the module named
by the full node ID at the prepared base. Fixture/phase entries describe source
flow and intended assertions; no per-case actual schema or exception was saved.

| Family | Count | Shared fixture/phase (details and owners in§5) |
|---|---:|---|
| F1 | 5 | engines; current0013 transaction |
| F2 | 1 | migrator; current0013 |
| F3 | 56 | telegram/control/api -> ingress; current0013 OFF |
| F4 | 3 | messaging; direct0008 refusal on current head |
| F5 | 6 | control; direct G/E refusal on current head |
| F6 | 1 | control; strict E0011/P0012 checker at current entry |
| F7 | 7 | control; strict P0012 or0011->0012->head |
| F8 | 1 | database; current0013 capabilities |
| F9 | 8 | control; strict historical P helpers at current entry |

| Full observed FAILED node ID | ci.log line | Definition line | Family |
|---|---:|---:|---|
| `tests/test_m1_3_c0_acceptance.py::test_initializer_conflict_has_no_catalog_or_workspace_side_effects[missing_workspace]` | 1019 | 144 | F1 |
| `tests/test_m1_3_c0_acceptance.py::test_initializer_conflict_has_no_catalog_or_workspace_side_effects[partial]` | 1020 | 144 | F1 |
| `tests/test_m1_3_c0_acceptance.py::test_initializer_conflict_has_no_catalog_or_workspace_side_effects[input]` | 1021 | 144 | F1 |
| `tests/test_m1_3_c0_acceptance.py::test_initializer_conflict_has_no_catalog_or_workspace_side_effects[null_code]` | 1022 | 144 | F1 |
| `tests/test_m1_3_c0_acceptance.py::test_initializer_conflict_has_no_catalog_or_workspace_side_effects[null_revision]` | 1023 | 144 | F1 |
| `tests/test_m1_3_postgres.py::test_exact_physical_schema_constraints_keys_and_grants` | 1036 | 366 | F2 |
| `tests/test_m2_3_db_postgres.py::test_receipt_concurrent_dedupe_and_exact_conflict_precede_disconnection` | 1204 | 356 | F3 |
| `tests/test_m2_3_db_postgres.py::test_unknown_binding_cross_bot_and_owner_do_not_write` | 1205 | 385 | F3 |
| `tests/test_m2_3_db_postgres.py::test_terminal_ignored_receipts_and_lifecycle_never_create_work` | 1206 | 410 | F3 |
| `tests/test_m2_3_db_postgres.py::test_window_clamps_future_to_first_receive_and_duplicates_never_extend` | 1210 | 497 | F3 |
| `tests/test_m2_3_db_postgres.py::test_observation_cas_fences_invalidation_and_concurrent_refresh` | 1211 | 517 | F3 |
| `tests/test_m2_3_db_postgres.py::test_new_intent_requires_same_uow_observation_and_replay_precedes_gates` | 1212 | 546 | F3 |
| `tests/test_m2_3_db_postgres.py::test_old_begin_and_unprobed_claim_cannot_bypass_telegram_preflight` | 1213 | 582 | F3 |
| `tests/test_m2_3_db_postgres.py::test_dispatch_rechecks_current_authority_business_billing_and_window[owner]` | 1214 | 622 | F3 |
| `tests/test_m2_3_db_postgres.py::test_dispatch_rechecks_current_authority_business_billing_and_window[business]` | 1215 | 622 | F3 |
| `tests/test_m2_3_db_postgres.py::test_dispatch_rechecks_current_authority_business_billing_and_window[connection]` | 1216 | 622 | F3 |
| `tests/test_m2_3_db_postgres.py::test_dispatch_rechecks_current_authority_business_billing_and_window[billing]` | 1217 | 622 | F3 |
| `tests/test_m2_3_db_postgres.py::test_dispatch_rechecks_current_authority_business_billing_and_window[window]` | 1218 | 622 | F3 |
| `tests/test_m2_3_db_postgres.py::test_worker_denies_expiry_during_billing_lock_without_adapter_call[subscription]` | 1219 | 751 | F3 |
| `tests/test_m2_3_db_postgres.py::test_worker_denies_expiry_during_billing_lock_without_adapter_call[mode]` | 1220 | 751 | F3 |
| `tests/test_m2_3_db_postgres.py::test_worker_denies_expiry_during_billing_lock_without_adapter_call[window]` | 1221 | 751 | F3 |
| `tests/test_m2_3_db_postgres.py::test_owner_denies_expiry_during_billing_lock_without_intention[subscription]` | 1222 | 782 | F3 |
| `tests/test_m2_3_db_postgres.py::test_owner_denies_expiry_during_billing_lock_without_intention[mode]` | 1223 | 782 | F3 |
| `tests/test_m2_3_db_postgres.py::test_owner_denies_expiry_during_billing_lock_without_intention[window]` | 1224 | 782 | F3 |
| `tests/test_m2_3_db_postgres.py::test_429_finalized_delay_is_durable_replay_and_horizon_exhausts` | 1225 | 808 | F3 |
| `tests/test_m2_3_db_postgres.py::test_owner_cursor_projection_has_no_internal_ids_and_checks_exact_anchor` | 1226 | 857 | F3 |
| `tests/test_m2_3_db_postgres.py::test_db_receipt_codec_preserves_opaque_utf8_and_delete_chat` | 1227 | 956 | F3 |
| `tests/test_m2_3_db_postgres.py::test_structural_billing_absence_is_unavailable_before_any_new_intent` | 1237 | 1020 | F3 |
| `tests/test_m2_3_db_postgres.py::test_known_product_revision_type_precedes_gates_in_python_sql_and_worker[current-INTEGER]` | 1238 | 1039 | F3 |
| `tests/test_m2_3_db_postgres.py::test_known_product_revision_type_precedes_gates_in_python_sql_and_worker[current-STANDARD]` | 1239 | 1039 | F3 |
| `tests/test_m2_3_db_postgres.py::test_known_product_revision_type_precedes_gates_in_python_sql_and_worker[inactive-INTEGER]` | 1240 | 1039 | F3 |
| `tests/test_m2_3_db_postgres.py::test_known_product_revision_type_precedes_gates_in_python_sql_and_worker[inactive-STANDARD]` | 1241 | 1039 | F3 |
| `tests/test_m2_3_db_postgres.py::test_known_product_revision_type_precedes_gates_in_python_sql_and_worker[historical-INTEGER]` | 1242 | 1039 | F3 |
| `tests/test_m2_3_db_postgres.py::test_known_product_revision_type_precedes_gates_in_python_sql_and_worker[historical-STANDARD]` | 1243 | 1039 | F3 |
| `tests/test_m2_3_db_postgres.py::test_readonly_failure_observation_commits_unavailable_without_permission` | 1244 | 1166 | F3 |
| `tests/test_m2_3_schema_postgres.py::test_composite_refs_reject_forged_workspace_connection_and_inbox` | 1248 | 292 | F3 |
| `tests/test_m2_3_schema_postgres.py::test_downgrade_refuses_55000_before_first_destructive_statement` | 1250 | 390 | F3 |
| `tests/test_m3_1_control_api_postgres.py::test_post_lock_product_boundaries_with_actual_conversation_wait[telegram-expiry-subscription]` | 1273 | 196 | F3 |
| `tests/test_m3_1_control_api_postgres.py::test_post_lock_product_boundaries_with_actual_conversation_wait[telegram-expiry-mode]` | 1274 | 196 | F3 |
| `tests/test_m3_1_control_api_postgres.py::test_post_lock_product_boundaries_with_actual_conversation_wait[telegram-activation-subscription]` | 1275 | 196 | F3 |
| `tests/test_m3_1_control_api_postgres.py::test_post_lock_product_boundaries_with_actual_conversation_wait[telegram-activation-mode]` | 1276 | 196 | F3 |
| `tests/test_m3_1_control_api_postgres.py::test_control_product_channel_precedence_and_takeover_independence[suspended]` | 1278 | 307 | F3 |
| `tests/test_m3_1_control_api_postgres.py::test_control_product_channel_precedence_and_takeover_independence[expired]` | 1279 | 307 | F3 |
| `tests/test_m3_1_control_api_postgres.py::test_control_product_channel_precedence_and_takeover_independence[missing]` | 1280 | 307 | F3 |
| `tests/test_m3_1_control_api_postgres.py::test_control_product_channel_precedence_and_takeover_independence[inactive_connection]` | 1281 | 307 | F3 |
| `tests/test_m3_1_control_api_postgres.py::test_control_product_channel_precedence_and_takeover_independence[inactive_business]` | 1282 | 307 | F3 |
| `tests/test_m3_1_control_api_postgres.py::test_control_product_channel_precedence_and_takeover_independence[closed_window]` | 1283 | 307 | F3 |
| `tests/test_m3_1_control_api_postgres.py::test_manual_refresh_interleaving_commits_only_final_admitted_order[False]` | 1288 | 438 | F3 |
| `tests/test_m3_1_control_api_postgres.py::test_manual_refresh_interleaving_commits_only_final_admitted_order[True]` | 1289 | 438 | F3 |
| `tests/test_m3_1_control_postgres.py::test_ingress_capture_serializes_resume_and_rollbacks[False-TELEGRAM]` | 1339 | 560 | F3 |
| `tests/test_m3_1_control_postgres.py::test_ingress_capture_serializes_resume_and_rollbacks[True-TELEGRAM]` | 1341 | 560 | F3 |
| `tests/test_m3_1_control_postgres.py::test_unknown_conversation_and_grouping_use_earliest_capture[TELEGRAM]` | 1343 | 619 | F3 |
| `tests/test_m3_1_control_postgres.py::test_resume_held_transaction_forces_later_ingress_capture[TELEGRAM]` | 1347 | 712 | F3 |
| `tests/test_m3_1_control_postgres.py::test_post_resume_duplicate_first_keeps_earliest_committed_origin[False-TELEGRAM]` | 1349 | 759 | F3 |
| `tests/test_m3_1_control_postgres.py::test_post_resume_duplicate_first_keeps_earliest_committed_origin[True-TELEGRAM]` | 1351 | 759 | F3 |
| `tests/test_m3_1_guards_migrations.py::test_any_guard_usage_refuses_before_ddl_and_preserves_full_g[profile]` | 1362 | 188 | F5 |
| `tests/test_m3_1_guards_migrations.py::test_any_guard_usage_refuses_before_ddl_and_preserves_full_g[step]` | 1363 | 188 | F5 |
| `tests/test_m3_1_guards_migrations.py::test_any_guard_usage_refuses_before_ddl_and_preserves_full_g[receipt]` | 1364 | 188 | F5 |
| `tests/test_m3_1_guards_migrations.py::test_any_guard_usage_refuses_before_ddl_and_preserves_full_g[terminal_rejection]` | 1365 | 188 | F5 |
| `tests/test_m3_1_guards_postgres.py::test_telegram_resume_and_fresh_ingress_never_plan_or_probe_automated_send` | 1401 | 667 | F3 |
| `tests/test_m3_1_migrations.py::test_legacy_pending_and_duplicate_first_preserve_fence_and_payload_winner[TELEGRAM-False]` | 1405 | 533 | F3 |
| `tests/test_m3_1_migrations.py::test_legacy_pending_and_duplicate_first_preserve_fence_and_payload_winner[TELEGRAM-True]` | 1406 | 533 | F3 |
| `tests/test_m3_1_migrations.py::test_populated_refusal_is_before_destructive_ddl_and_preserves_exact_snapshot[mark]` | 1407 | 584 | F4 |
| `tests/test_m3_1_migrations.py::test_populated_refusal_is_before_destructive_ddl_and_preserves_exact_snapshot[membership]` | 1408 | 584 | F4 |
| `tests/test_m3_1_migrations.py::test_populated_refusal_is_before_destructive_ddl_and_preserves_exact_snapshot[receipt]` | 1409 | 584 | F4 |
| `tests/test_m3_1_provenance_migrations.py::test_fresh_head_full42_columns_profiles_rls_and_no_unused_backfill` | 1412 | 113 | F7 |
| `tests/test_m3_1_provenance_migrations.py::test_populated_0011_repeat_upgrade_and_exact_unused_reverse` | 1413 | 161 | F7 |
| `tests/test_m3_1_provenance_migrations.py::test_owned_used_refusal_precedes_every_ddl_and_preserves_all42[codec-off]` | 1414 | 289 | F7 |
| `tests/test_m3_1_provenance_migrations.py::test_owned_used_refusal_precedes_every_ddl_and_preserves_all42[target]` | 1415 | 289 | F7 |
| `tests/test_m3_1_provenance_migrations.py::test_owned_used_refusal_precedes_every_ddl_and_preserves_all42[effect]` | 1416 | 289 | F7 |
| `tests/test_m3_1_provenance_migrations.py::test_owned_used_refusal_precedes_every_ddl_and_preserves_all42[suppression]` | 1417 | 289 | F7 |
| `tests/test_m3_1_provenance_migrations.py::test_owned_used_refusal_precedes_every_ddl_and_preserves_all42[enabled-only]` | 1418 | 289 | F7 |
| `tests/test_m3_1_turns_postgres.py::test_ingress_share_barrier_earliest_committed_origin[False-True-TELEGRAM]` | 1542 | 571 | F3 |
| `tests/test_m3_1_turns_postgres.py::test_ingress_share_barrier_earliest_committed_origin[False-False-TELEGRAM]` | 1544 | 571 | F3 |
| `tests/test_m3_1_turns_postgres.py::test_ingress_share_barrier_earliest_committed_origin[True-True-TELEGRAM]` | 1546 | 571 | F3 |
| `tests/test_m3_1_turns_postgres.py::test_ingress_share_barrier_earliest_committed_origin[True-False-TELEGRAM]` | 1548 | 571 | F3 |
| `tests/test_m3_2_escalations_migrations.py::test_used_e_refuses_before_ddl_even_after_terminal_decision[False]` | 1590 | 184 | F5 |
| `tests/test_m3_2_escalations_migrations.py::test_used_e_refuses_before_ddl_even_after_terminal_decision[True]` | 1591 | 184 | F5 |
| `tests/test_m3_2_escalations_migrations.py::test_exact_e_profiles_private_clock_forced_rls_and_no_runtime_raw_access` | 1592 | 193 | F6 |
| `tests/test_postgres.py::test_real_postgres_capabilities_and_roles` | 1658 | 75 | F8 |
| `tests/test_telegram_egress_postgres.py::TestEgressMaterialCompatibility::test_current_0012_profile_v2_off_receipt_dto_and_snapshot` | 1670 | 2112 | F9 |
| `tests/test_telegram_egress_postgres.py::TestEgressMaterialCompatibility::test_used_0012_refuses_before_ddl_and_preserves_all42[codec-off]` | 1671 | 2160 | F9 |
| `tests/test_telegram_egress_postgres.py::TestEgressMaterialCompatibility::test_used_0012_refuses_before_ddl_and_preserves_all42[enabled-gate]` | 1672 | 2160 | F9 |
| `tests/test_telegram_egress_postgres.py::TestEgressMaterialCompatibility::test_used_0012_refuses_before_ddl_and_preserves_all42[target]` | 1673 | 2160 | F9 |
| `tests/test_telegram_egress_postgres.py::TestEgressMaterialCompatibility::test_used_0012_refuses_before_ddl_and_preserves_all42[effect-audit]` | 1674 | 2160 | F9 |
| `tests/test_telegram_egress_postgres.py::TestEgressMaterialCompatibility::test_used_0012_refuses_before_ddl_and_preserves_all42[suppression-member]` | 1675 | 2160 | F9 |
| `tests/test_telegram_egress_postgres.py::TestEgressMaterialCompatibility::test_used_0012_refuses_before_ddl_and_preserves_all42[material-result]` | 1676 | 2160 | F9 |
| `tests/test_telegram_egress_postgres.py::TestEgressMaterialCompatibility::test_used_0012_refuses_before_ddl_and_preserves_all42[invalidated-turn]` | 1677 | 2160 | F9 |

F3's legacy-pending migration pair explicitly runs raw0007 then fresh current0013;
its two phases are not interchangeable. The exact F3 forwarding paths are in§5.

## Appendix B. All47 UNKNOWN IDs

No ID below is relabelled PASSED, FAILED, skipped or unexecuted. ci.log:1678
announces the first without a terminal result. Definitions/fixtures are source
locations, not evidence that those bodies ran.

| Full node ID — status UNKNOWN | Definition line | Group |
|---|---:|---|
| `tests/test_tenancy_migrations.py::test_fresh_m0_idempotent_downgrade_reupgrade_and_readiness` | 31 | U1 |
| `tests/test_tenancy_postgres.py::test_raw_crud_positive_and_cross_workspace_denial[businesses]` | 147 | U2 |
| `tests/test_tenancy_postgres.py::test_raw_crud_positive_and_cross_workspace_denial[business_members]` | 147 | U2 |
| `tests/test_tenancy_postgres.py::test_raw_crud_positive_and_cross_workspace_denial[locations]` | 147 | U2 |
| `tests/test_tenancy_postgres.py::test_missing_and_malformed_context_fail_closed[None-businesses]` | 193 | U2 |
| `tests/test_tenancy_postgres.py::test_missing_and_malformed_context_fail_closed[None-business_members]` | 193 | U2 |
| `tests/test_tenancy_postgres.py::test_missing_and_malformed_context_fail_closed[None-locations]` | 193 | U2 |
| `tests/test_tenancy_postgres.py::test_missing_and_malformed_context_fail_closed[workspace-businesses]` | 193 | U2 |
| `tests/test_tenancy_postgres.py::test_missing_and_malformed_context_fail_closed[workspace-business_members]` | 193 | U2 |
| `tests/test_tenancy_postgres.py::test_missing_and_malformed_context_fail_closed[workspace-locations]` | 193 | U2 |
| `tests/test_tenancy_postgres.py::test_missing_and_malformed_context_fail_closed[actor-businesses]` | 193 | U2 |
| `tests/test_tenancy_postgres.py::test_missing_and_malformed_context_fail_closed[actor-business_members]` | 193 | U2 |
| `tests/test_tenancy_postgres.py::test_missing_and_malformed_context_fail_closed[actor-locations]` | 193 | U2 |
| `tests/test_tenancy_postgres.py::test_missing_and_malformed_context_fail_closed[kind-businesses]` | 193 | U2 |
| `tests/test_tenancy_postgres.py::test_missing_and_malformed_context_fail_closed[kind-business_members]` | 193 | U2 |
| `tests/test_tenancy_postgres.py::test_missing_and_malformed_context_fail_closed[kind-locations]` | 193 | U2 |
| `tests/test_tenancy_postgres.py::test_missing_and_malformed_context_fail_closed[correlation-businesses]` | 193 | U2 |
| `tests/test_tenancy_postgres.py::test_missing_and_malformed_context_fail_closed[correlation-business_members]` | 193 | U2 |
| `tests/test_tenancy_postgres.py::test_missing_and_malformed_context_fail_closed[correlation-locations]` | 193 | U2 |
| `tests/test_tenancy_postgres.py::test_missing_and_malformed_context_fail_closed[xid-businesses]` | 193 | U2 |
| `tests/test_tenancy_postgres.py::test_missing_and_malformed_context_fail_closed[xid-business_members]` | 193 | U2 |
| `tests/test_tenancy_postgres.py::test_missing_and_malformed_context_fail_closed[xid-locations]` | 193 | U2 |
| `tests/test_tenancy_postgres.py::test_missing_and_malformed_context_fail_closed[outsider-businesses]` | 193 | U2 |
| `tests/test_tenancy_postgres.py::test_missing_and_malformed_context_fail_closed[outsider-business_members]` | 193 | U2 |
| `tests/test_tenancy_postgres.py::test_missing_and_malformed_context_fail_closed[outsider-locations]` | 193 | U2 |
| `tests/test_tenancy_postgres.py::test_composite_business_fk_blocks_cross_tenant_and_workspace_business_confusion[business_members]` | 221 | U2 |
| `tests/test_tenancy_postgres.py::test_composite_business_fk_blocks_cross_tenant_and_workspace_business_confusion[locations]` | 221 | U2 |
| `tests/test_tenancy_postgres.py::test_optional_account_requires_same_workspace_membership_and_unique_link` | 243 | U2 |
| `tests/test_tenancy_postgres.py::test_forged_ids_and_same_workspace_wrong_business_are_not_found` | 273 | U2 |
| `tests/test_tenancy_postgres.py::test_membership_factory_rejects_forged_inactive_or_privileged_actor` | 293 | U2 |
| `tests/test_tenancy_postgres.py::test_permission_boundary_and_cas_are_not_replaced_by_rls` | 327 | U2 |
| `tests/test_tenancy_postgres.py::test_commit_rollback_same_physical_connection_and_stale_session_fence` | 343 | U2 |
| `tests/test_tenancy_postgres.py::test_concurrent_async_contexts_and_reuse_are_task_safe` | 404 | U2 |
| `tests/test_tenancy_postgres.py::test_cancellation_rolls_back_and_releases_pooled_connection` | 424 | U2 |
| `tests/test_tenancy_postgres.py::test_runtime_roles_policies_functions_and_platform_surface` | 443 | U3 |
| `tests/test_tenancy_postgres.py::test_real_schema_matches_contract_and_constraints` | 858 | U3 |
| `tests/test_tenancy_postgres.py::test_concurrent_cas_has_exactly_one_winner` | 906 | U2 |
| `tests/test_tenancy_postgres.py::test_membership_revocation_is_serialized_with_active_transaction` | 925 | U2 |
| `tests/test_tenancy_postgres.py::test_suppressed_database_error_still_rolls_back_whole_unit` | 953 | U2 |
| `tests/test_tenancy_postgres.py::test_duplicate_id_other_workspace_is_not_unique_constraint_oracle` | 966 | U2 |
| `tests/test_tenancy_postgres.py::test_row_security_off_does_not_bypass_rls` | 989 | U2 |
| `tests/test_tenancy_transaction_guard.py::test_autocommit_rejected_before_body_and_publication_then_same_pool_recovers[constructor]` | 74 | U4 |
| `tests/test_tenancy_transaction_guard.py::test_autocommit_rejected_before_body_and_publication_then_same_pool_recovers[execution_options]` | 74 | U4 |
| `tests/test_tenancy_transaction_guard.py::test_autocommit_rejected_before_body_and_publication_then_same_pool_recovers[dbapi_connect_args]` | 74 | U4 |
| `tests/test_tenancy_transaction_guard.py::test_real_binding_survives_statements_and_later_error_rolls_back_write` | 142 | U4 |
| `tests/test_tenancy_transaction_guard.py::test_real_prepublication_binding_mismatch_rejects_and_rolls_back_setup[workspace_id]` | 188 | U4 |
| `tests/test_tenancy_transaction_guard.py::test_real_prepublication_binding_mismatch_rejects_and_rolls_back_setup[context_xid]` | 188 | U4 |

## Appendix C. Complete802 preservation and phase coverage map

All original IDs are the ordered802 manifest in§3; the reproducible TSV maps
each to its actual terminal observation/UNKNOWN. This table accounts for every
one of them. Totals must be retained in the successor gate; historical phases
are explicit within the affected tests. The rest stays on current0013/native
OFF_UNUSED where applicable. No all-suite frozen-P substitution or new native
fixture/admin reset option is proposed.

| Complete generic module | Total retained | OBSERVED PASS | OBSERVED FAIL | UNKNOWN | Phase obligation |
|---|---:|---:|---:|---:|---|
| `tests/test_auth_migrations.py` | 1 | 1 | 0 | 0 | current default; retain explicit predecessor/reverse/refusal phases |
| `tests/test_auth_postgres.py` | 42 | 42 | 0 | 0 | current0013 OFF; all existing assertions retained |
| `tests/test_c8_tenancy_review.py` | 8 | 8 | 0 | 0 | current0013 OFF; all existing assertions retained |
| `tests/test_m1_3_api_postgres.py` | 43 | 43 | 0 | 0 | current0013 OFF; all existing assertions retained |
| `tests/test_m1_3_c0_acceptance.py` | 12 | 7 | 5 | 0 | current0013 OFF; all existing assertions retained |
| `tests/test_m1_3_migrations.py` | 5 | 5 | 0 | 0 | current default; retain explicit predecessor/reverse/refusal phases |
| `tests/test_m1_3_postgres.py` | 24 | 23 | 1 | 0 | current0013 OFF; all existing assertions retained |
| `tests/test_m2_1_audit_postgres.py` | 1 | 1 | 0 | 0 | current0013 OFF; all existing assertions retained |
| `tests/test_m2_1_postgres.py` | 57 | 57 | 0 | 0 | current0013 OFF; all existing assertions retained |
| `tests/test_m2_1_schema_postgres.py` | 12 | 12 | 0 | 0 | current default; retain explicit predecessor/reverse/refusal phases |
| `tests/test_m2_2_db_postgres.py` | 21 | 21 | 0 | 0 | current0013 OFF; all existing assertions retained |
| `tests/test_m2_2_migrations.py` | 1 | 1 | 0 | 0 | current default; retain explicit predecessor/reverse/refusal phases |
| `tests/test_m2_2_recovery_postgres.py` | 18 | 18 | 0 | 0 | current0013 OFF; all existing assertions retained |
| `tests/test_m2_2_storage_postgres.py` | 6 | 6 | 0 | 0 | current0013 OFF; all existing assertions retained |
| `tests/test_m2_3_api_postgres.py` | 21 | 21 | 0 | 0 | current0013 OFF; all existing assertions retained |
| `tests/test_m2_3_api_telegram_postgres.py` | 9 | 9 | 0 | 0 | current0013 OFF; all existing assertions retained |
| `tests/test_m2_3_db_postgres.py` | 41 | 12 | 29 | 0 | current0013 OFF; all existing assertions retained |
| `tests/test_m2_3_schema_postgres.py` | 7 | 5 | 2 | 0 | current default; retain explicit predecessor/reverse/refusal phases |
| `tests/test_m2_3_wire_postgres.py` | 11 | 11 | 0 | 0 | current0013 OFF; all existing assertions retained |
| `tests/test_m3_1_control_api_postgres.py` | 39 | 27 | 12 | 0 | current0013 OFF; all existing assertions retained |
| `tests/test_m3_1_control_migrations.py` | 15 | 15 | 0 | 0 | current default; retain explicit predecessor/reverse/refusal phases |
| `tests/test_m3_1_control_postgres.py` | 44 | 38 | 6 | 0 | current0013 OFF; all existing assertions retained |
| `tests/test_m3_1_guards_migrations.py` | 6 | 2 | 4 | 0 | current default; retain explicit predecessor/reverse/refusal phases |
| `tests/test_m3_1_guards_postgres.py` | 35 | 34 | 1 | 0 | current0013 OFF; all existing assertions retained |
| `tests/test_m3_1_migrations.py` | 10 | 5 | 5 | 0 | current default; retain explicit predecessor/reverse/refusal phases |
| `tests/test_m3_1_provenance_migrations.py` | 9 | 2 | 7 | 0 | strict0011/0012 phases + current OFF compatibility, F7 |
| `tests/test_m3_1_provenance_postgres.py` | 104 | 104 | 0 | 0 | current0013 OFF; all existing assertions retained |
| `tests/test_m3_1_turns_postgres.py` | 54 | 50 | 4 | 0 | current0013 OFF; all existing assertions retained |
| `tests/test_m3_2_escalations_api_postgres.py` | 9 | 9 | 0 | 0 | current0013 OFF; all existing assertions retained |
| `tests/test_m3_2_escalations_migrations.py` | 9 | 6 | 3 | 0 | current default; retain explicit predecessor/reverse/refusal phases |
| `tests/test_m3_2_escalations_postgres.py` | 61 | 61 | 0 | 0 | current0013 OFF; all existing assertions retained |
| `tests/test_postgres.py` | 7 | 6 | 1 | 0 | current0013 OFF; all existing assertions retained |
| `tests/test_telegram_egress_postgres.py` | 13 | 5 | 8 | 0 | current durable/Turn cases; F9 paired P/current subphases |
| `tests/test_tenancy_migrations.py` | 1 | 0 | 0 | 1 | U1 full lifecycle + current readiness |
| `tests/test_tenancy_postgres.py` | 40 | 0 | 0 | 40 | U2/U3/U4 current tenant/security; no speculative edit |
| `tests/test_tenancy_transaction_guard.py` | 6 | 0 | 0 | 6 | U2/U3/U4 current tenant/security; no speculative edit |
| **TOTAL** | **802** | **667** | **88** | **47** | Complete original inventory required |

The14 reported failing-module counts match C0 exactly. The667 observations
remain scoped to RUN3; the future current-source gate must execute them again
with the corrected fixtures and full phase evidence. F3's12 potentially vacuous
negative PASS cases receive target-origin checks, not deletion or retroactive
status changes. Native112/336/105 and independent167/45/635 evidence remain a
separate mandatory complete gate. **CI-06 OPEN; proposal only; C2 HOLD.**
