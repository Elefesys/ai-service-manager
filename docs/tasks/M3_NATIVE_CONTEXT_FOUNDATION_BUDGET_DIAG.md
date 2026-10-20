# C6-M3.1-NATIVE-CONTEXT-FOUNDATION-DIAG-R1

2026-10-19 UTC — source-only diagnostic/proposal; REVIEW, then C6 HOLD.

The measured bottleneck is the serial combination of the complete normal durable
lane and backend gate in one 45-minute job. RUN3 also has 88 real generic failures;
moving work cannot fix them. Recommend preserving live, bounded generic evidence
and moving the **whole** normal durable lane to one required 25-minute job, followed
by the existing required foundation job at 45 minutes. This is a proposal for C0
acceptance, not an implemented split or evidence that a corrected full run fits.
CI-06 and CI-07 remain OPEN; PR35/M3 remain BLOCKED/IN_PROGRESS.

## 1. Authority, exact sources and scope

[C0 task6269040066](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6269040066)
and [final RUN3 disposition6268965488](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6268965488)
are the current authorization. Only this new report is added. Every existing292
tracked leaf, including HANDOFF/register, stays byte/mode-exact.

| Binding | Full identity |
|---|---|
| Own branch | `c6/m3-1-native-context-foundation-diag-r1` |
| Prepared base / report commit's sole parent | `9ec5508e13a60962a4b2fded1d8a582cd1e6346b` |
| Prepared base tree | `0ee72bb8ddd5975ab7876fccf68103f7d6e51e31` |
| Base's sole parent / frozen PR35 candidate | `59c9fce52bdaae54f50cdb847a378d47f75c642b` |
| Candidate and tested merge tree | `c5941d30aba59fe68f07b86f96c1cd8ae9c55c9a` |
| Actual RUN3 checkout | `b6cf7fb41297c18ad72da0e22f9694083f76737a` |
| Ordered raw merge parents | `e205e22051bc06295758b504d84699652b176c15`, `59c9fce52bdaae54f50cdb847a378d47f75c642b` |
| Run / attempt | `39256948310` / `1` |
| Foundation job | `118074513375` |
| Main / frozen MATERIAL P / schema | `e205e22051bc06295758b504d84699652b176c15` / `0012` |
| Stock ref | `af7482dede085bc033e3fee34f9a2425124351ee` |

AGENTS, current HANDOFF/register, IMPL-001 and applicable canonical Spec
5.8–5.14/18.5–18.9/24.7, ADR002–007/024–026/180/266/267, MVP GJ-G/J and
variants, Roadmap/Plan M3 and accepted M3_CONTRACT§16–16.20 remain authoritative.
The full contract is unchanged: SHA256
`fe2eb4ef2469ccb14b7147017c3c81066cde1b8a6ad60acbf73922a15e3ace5f`.
Original11 attachments=SOURCE_MANIFEST=repository bytes were independently checked.
Historical status paragraphs in the contract do not replace C0's later acceptance.

No implementation, test edits, workflow edits, image changes, PostgreSQL, Docker,
application/frontend/image builds, browser, service or Actions execution occurred
for this task. Local activity was retrieval and analysis of retained evidence,
Git/source checks and the required pure source pairing. Frozen dependencies were
restored offline into a separate Python3.13.12 environment, including the local
editable package metadata; this was not a product/image build or runtime gate.
No other agents/chats, PR, dispatch, rerun, retry, cancel, merge or unrelated ref
movement. C2 separately owns the 88-failure taxonomy and corrective proposal.

## 2. Evidence obtained and independently checked

Read-only GitHub plugin calls obtained the run and attempt1 jobs metadata,
foundation/Docker29 decoded job logs, artifact metadata and three ZIP downloads.
Foundation ZIP has exactly seven files: architecture.log, ci.log,
candidate-egress-source.json, telegram-egress.json, source.tar.gz,
tested-commit.txt and worktree-status.txt. There is no generic JUnit, per-phase
case journal, partition JSON or completed generic exception summary in this ZIP.

| Retained evidence | Bytes / SHA256 |
|---|---|
| Foundation artifact12191528180 | 2626556 / `e651e1120877459883c1e282b45036f95da748b8cbac6947dabd95ec58c37cf2` |
| Native artifact12188761326, same RUN3 | 3320227 / `ffcff8403820e12694d1027ce31cad907deb6cae6aeedd11a4e578f0c9142961` |
| Docker29 artifact12189492179, same RUN3 | 2604648 / `2bba75a71b8a4becb6b19367b34fe450255ad9d1243ece0223dcdedc6ab57c91` |
| Foundation decoded job log, UTF-8 including BOM | `8791be4f230d35a6a2ebba3d1d767af7ef1ac7c98a1138effee381428af4f79a` |
| Foundation artifact ci.log | 148283 / `c1cef3187f7154de0090af5bea5d42ae084e65a4c2fc01c0aed40792ea8570c0` |
| Foundation source.tar.gz | 2546480 / `025aad7e8a0499f21f54bbc6b9b4fb95518263f6b526ab063c010d3bddbd6645` |
| Foundation telegram-egress.json | 438829 / `44abfab94dd0ca996572ccc46a23023cd8a700a2a937feee849c90171b671463` |
| Native partition-generic-pg.json, file bytes | `66d904173fbde7c088aa0983f228d9a11dcd96d196cceb20c7abefa0edfb7c2f` |
| Docker29 decoded job log | `c82c8da293ccdfb042cbf8affd324b44ae6a321eef3d1f7b72367b2300733871` |

Foundation and Docker29 source archives each contain292 files, all bytes/modes
matching the frozen candidate. Both tested-commit files name the actual merge;
candidate image proofs contain its exact ordered raw parents. Empty archived
worktree-status is separate evidence: foundation's actual clean gate was SKIPPED.
The prepared base differs from the candidate only in C0's HANDOFF/register.

Native's actual source identity names the same merge. Its retained generic
inventory supplies the complete ordered802 IDs without fresh collection or
fixtures. Both foundation log representations have the identical ordered first755
terminal statuses, matching that inventory's first755 byte-for-byte. Parsing
preserves spaces in parametrized IDs and variable padding before percentage
columns; splitting terminal lines on whitespace would lose11 passing outcomes.

The foundation partition proof reports907=802+105, native112=7source+105PG,
complete union/disjointness and no fixed-total requirement. Its embedded inventory
digests hash canonical JSON values, **not the artifact file bytes** above. For
example embedded generic digest is
`25f19498e106d1718aec8b6f5a6f1f17277459e5b85090aa0d31db777da4d80c`.
Do not confuse these representations or replace exact inventory equality with
count-only acceptance.

## 3. Measured timing and censoring

All timestamps below are2026-10-19 UTC. Intervals from streamed output include
startup, buffering and host orchestration. They are measured marker windows, not
individual test durations. API step times have second resolution. Calculations
use retained timestamps and round to milliseconds; no new benchmark was run.

| Phase / boundary | Start → end | Observed seconds / meaning |
|---|---|---|
| Whole foundation job | 13:03:39 →13:48:55 | 2716, includes setup and final archive |
| Main workflow step | 13:03:41 →13:48:51 | 2710, API CANCELLED |
| Main log group through api/checks/frontend Built | 13:03:41.769 →13:04:19.033 | 37.264; init/config/build envelope |
| Full normal durable visible envelope | 13:04:20.537 →13:21:05.797 | 1005.260; synthetic-keys→E01_E05_PASS |
| Durable wire test window, inside that envelope | 13:05:02.428 →13:05:46.197 | 43.769; six tests self-report42.32s |
| Pre-check work, main step→first Ruff result | 13:03:41 →13:21:11.946 | 1050.946; includes build/durable final cleanup/test-dependency startup |
| Ruff result→unit summary | 13:21:11.946 →13:24:59.269 | 227.323; format/mypy/units included |
| Unit pytest's own duration | summary13:24:59.269 | 215.35;1999PASS+130subtests,907deselected |
| Unit summary→partition proof | 13:24:59.269 →13:25:31.185 | 31.916; two upgrade-head calls plus three partition collections, not separately timed |
| Generic session header→802 selected | 13:25:31.454 →13:25:39.401 | 7.947; final collection/output window |
| Generic selected→first FAIL | 13:25:39.401 →13:26:51.337 | 71.936; failure precedes cancellation by almost22min |
| Generic selected→last terminal status | 13:25:39.401 →13:48:49.259 | 1389.858;755 outcomes, incomplete execution |
| Generic selected→cancel log | 13:25:39.401 →13:48:51.709 | 1392.307; censored, not a complete802 duration |
| Record-source step | 13:48:51 →13:48:52 | SUCCESS |
| Artifact upload step | 13:48:52 →13:48:53 | SUCCESS |

Ruff passed,160 files formatted and mypy64 files passed; mypy output is
13:21:22.747. Build frontend398 tests/14files and both deterministic frontend
builds passed. The native and other eight jobs were SUCCESS; foundation was
cancelled. The API states CANCELLED, the workflow has45min and the final error is
"The operation was canceled." Timing/C0's UI observation identify the cap boundary;
an independent check-run timeout annotation was not retrieved. The observed
45m16s job envelope is **not** a new allowed cap or a guarantee of grace time.

Normal durable's six lifecycle host windows and inner pytest durations differ:

| Complete lifecycle | Host marker→inner summary, seconds | Inner pytest seconds |
|---|---:|---:|
| fresh | 118.466 | 99.71 |
| recovery | 166.496 | 148.60 |
| recover-stopped | 165.763 | 147.79 |
| recover-missing | 164.660 | 146.98 |
| legacy-disable | 145.850 | 128.20 |
| legacy-stop | 152.940 | 134.80 |

The 1005.260s durable envelope also includes keys, independent HTTPS baseline,
prepare/topology/storage/migration/wire work and transitions. Do not add these
overlapping windows as disjoint costs. E01_E05_PASS is printed **before** the
script's finally block; its timestamp alone does not attest cleanup completion.
The later backend start brackets subsequent cleanup/startup, without a separate
duration. The archived durable report contains all six current-source lifecycles;
C0's45-table fingerprints/UNKNOWN/wire/Console acceptance is retained.

Result at interruption: **755 statuses=667PASSED+88FAILED;47UNKNOWN**. These are
pytest terminal case statuses, not retained evidence of every setup/call/teardown
phase. No final generic exit code, complete duration, per-case timing or original
exception chain can be reconstructed from a missing summary. The remaining
inventory is one `test_tenancy_migrations.py` case,40 `test_tenancy_postgres.py`
cases and six `test_tenancy_transaction_guard.py` cases. Missing outcome does not
prove whether a case started, completed setup, or had an in-flight call.

After generic, `check_backend.sh` still owes downgrade-base→upgrade-head,
contracts export/check, SOURCE_DATE_EPOCH315532800, two no-isolation wheels,
byte comparison and SHA256. `ci.sh` then owes minio/mc in-image version checks,
API/worker/scheduler/frontend startup, HTTP readiness on8000/8080, `/ops/` and
compose images. These were **NOT REACHED**. Their costs and the47 remainder are
UNKNOWN, not zero. Current source retains EXIT cleanup; its completion after the
cancelled main pipe is not attested by this archive. Clean-source gate was SKIPPED.

### Exact-source comparison and conditional planning arithmetic

Same RUN3 Docker29 compatibility job118074513895 completed successfully in1049s
(13:03:39→13:21:08) under its existing25min cap. Its same six-lifecycle visible
window is1009.058s (13:04:13.425→13:21:02.483). Both current292-file archives and
source/parents were checked, so this is a relevant accepted execution boundary.
It is a different Engine/Compose setup/probe; it is **not** a normal-lane speed
benchmark or proof of an additional job's duration. No historical schema0012
acceptance is substituted for current0013 generic work. Earlier RUN2 corrections
remain accepted at their own scopes; no cross-source timing extrapolation is used.

Backend's observed first-check-output→cancel interval is1659.763s (27m39.763s).
For a proposed fresh core job, the conditional planning requirement is:

`fresh init/build/dependency cost + observed backend prefix + remaining generic/finalization + full tail + cleanup/archive <2700s`.

Using the observed prefix merely as an anchor leaves1040.237s for **all** the
other terms. The prior37.264s build window is an observation, not a bound on a new
build. Corrected failures may execute additional work, and fsync/reporting has
unmeasured overhead. No complete-run estimate or guaranteed fit follows. Planning
arithmetic does not subtract any charge from a live request, reset S, grant extra
time or justify retries. Later actual complete evidence must establish fit.

## 4. Why evidence is lost; minimum safe retention proposal

`check_backend.sh` runs `native_context_db_catalog.py generic-integration` inside
`compose run --rm checks`. `generic_integration()` proves the full partition in
an external TemporaryDirectory, prints only its compact proof on success, then
calls pytest.main with unchanged `-v --durations=20 -m integration` and exactly
the existing three native PG module exclusions. Its ExactGeneric hook verifies
the **ordered** selected inventory. The temporary partition JSON/log files are
not copied to host reports on successful collection.

Pytest verbose output retains names/statuses during execution, but ordinary
traceback and slowest-duration reports arrive at terminal summary. No early
structured failure journal is installed for generic. Cancellation interrupts the
checks/main pipe before that summary; `tee reports/ci.log` preserves received
bytes, not pytest's in-memory failure objects. Container removal and temporary
storage make an after-the-fact `docker cp`/lastfailed/JUnit strategy unreliable.
JUnit alone is also normally finalized at session end. The decoded job log adds
timestamps; artifact ci.log does not. None supplies the absent original88 traces.

Propose only the following instrumentation, with complete selection unchanged:

1. In `ci.sh`, precreate a private host directory under ignored
   `reports/foundation-core/<run>-<attempt>-<actual-head>/`. Bind **only** this
   directory writable into checks at `/asm-evidence`, outside `/app`; pass one
   fixed evidence-path variable, not native admin/reset credentials. Reject
   symlinks, foreign UID/type/mode, path escape and preexisting incompatible run
   identity before starting work. Host creation must use the actual runner UID;
   precreate the fixed0600 journal/partition files so the existing root checks
   process can write them without changing their runner ownership. Validate that
   explicit host UID/inode binding in the container. This permits the runner's
   upload step to read them, without changing the checks user, world-writable
   modes, Docker socket mounts or Compose credentials. A future different checks
   UID must prove write access before fixtures rather than loosen permissions.
2. In `generic_integration()`, publish all three already-produced partition
   inventories/proof to that host-backed directory before execution. Keep fresh
   collection,180s collection budget, all refusal checks and ExactGeneric's
   ordered equality. Store full approved source inventory with its digest; live
   records identify a case by inventory index and nodeid SHA256. This avoids
   passing arbitrary parametrized values through the live diagnostic formatter.
3. Extend the same generic plugin with `pytest_runtest_logstart`,
   `pytest_runtest_makereport` and normal-session finalization. Append a bounded
   JSONL start record, then one setup/call/teardown record immediately when the
   report exists: schema version, sequence, index/hash, phase, pytest outcome,
   finite nonnegative report.duration and monotonic elapsed from one recorded
   origin. Aggregate case outcome only after teardown; an unfinished case stays
   INCOMPLETE. Do not equate 755 call statuses with2265 completed phases.
4. For a failing phase, append a separate bounded sanitized record from that
   **same** call.excinfo before pytest discards it. Limit each ASCII JSON+LF record
   to4096bytes, exception traversal to four cycle-checked orig/cause/context nodes,
   Python frames to eight and parsed PL/pgSQL function/line pairs to three per
   node. Allow only known exception class labels, five-character SQLSTATE and
   schema/table/constraint/function identifiers from the reviewed source catalog.
   Python frames contain reviewed repository-relative path/function/line only.
   Unknown/untrusted fields become UNKNOWN with truncation flags. No locals,
   source statements, exception str/repr/messages, longrepr, report.sections,
   captured stdout/stderr, environment, command argv, credentials, DSNs, SQL,
   parameters, arbitrary identifiers, event or user payloads enter this record.
   The existing SENT formatter `_sent_failure_diagnostic` is a source precedent
   for closed metadata, not a generic formatter to import or relax; preserve it.
5. Preopen validated regular0600 append-only files with NOFOLLOW. Write each
   complete bounded record, flush/fsync before acknowledging persistence; preserve
   sequence and checksums/counts. A killed partial last line is discarded as an
   incomplete record, never repaired into PASS. Hash-chain/per-record enterprise
   logging, new dependencies and network collectors are unnecessary. Bound failure
   detail independently of outcome records; evidence limits/IO failures are
   explicit, never silently drop cases. Measure overhead later inside existing
   caps. The plugin must not mutate reports, swallow BaseException/cancellation,
   run cleanup/SQL, invoke a second test, or alter pytest.main's returned code.
6. Add fixed phase start/end records around **existing** backend shell commands
   and host boundaries: static phase label, monotonic elapsed, source binding and
   original exit status only. This separates the currently mixed upgrade/collection
   interval and makes the unreached tail visible. Keep arguments/order and
   `set -eu`/pipefail behavior. A recorder failure cannot replace the primary
   exception/status or turn cancellation into success. Missing required evidence
   on an otherwise successful run fails a separate evidence-completeness gate;
   original pytest/process exit values remain in the receipt.

Retain the main pipe and terminal summary for existing diagnostic behavior; the
new sanitized structured artifacts supplement them. Do not introduce `--showlocals`,
`-x`, `--maxfail`, subset flags, skip/xfail, rerun plugins or rewritten failures.
No test count, order, assertion, fixture reset or product transaction changes.

Workflow `if: always()` steps should record source identity/status, independently
check source cleanliness and upload the host-backed directory even after failure
or cancellation. Record job/phase completion separately: a partial journal may be
archived successfully while the execution gate remains CANCELLED/FAILED. Keep
source/cleanup failures visible alongside the original result; never replace a
failed primary with artifact success. Existing shell/Python owner cleanup must
still run within its original bounds; reporting neither adopts foreign resources
nor extends execution. GitHub hard termination/runner loss can still prevent
upload: the guarantee is survival of already-persisted records while the runner
and its always steps remain available, not unconditional remote delivery.

## 5. Proposed smallest execution-boundary repair

Require C0 acceptance of **11 expanded required jobs instead of10** before any
implementation. Current expansion is foundation1 + browser1 + Docker29compat1 +
normal/Docker29×intent/image/state6 + unconditional reusable native1. Proposed
addition is exactly one `foundation-durable` job. Keep all existing job names and
matrix members, default merge/main checkout, event triggers, read-only permissions,
pinned actions, concurrency and unconditional same-commit native reusable call.

| Proposed execution boundary | Exact complete responsibility / dependency |
|---|---|
| New required `foundation-durable`,25min | Fresh checkout; source admission; existing init/config/build prelude; complete normal `test_telegram_egress.sh`, including six wire checks and **all six** lifecycles; existing owner cleanup; clean-source/evidence/archive gates |
| Existing required `foundation`,45min | `needs: [foundation-durable]`; fresh checkout/runner/resources; init/config/build, full backend checks, exact full generic802 and full post-generic tail, storage version/service/HTTP smoke, cleanup/clean/evidence/archive |
| Existing Docker29 compatibility,25min | Unchanged exact Engine/Compose install, old mapping probe, whole six-lifecycle corrected durable gate and cleanup |
| Existing native,20min | Unconditional same-commit reusable call; full112/336/105 and167/45/635 guards; no dependency on the new durable job |
| Existing browser/state/image/intent jobs,25min | Unchanged complete normal/Docker29 matrix and browser scenarios, original clocks and cleanup |

The new dependency deliberately keeps the normal durable and core test work
**sequential**, preserving their former order without parallel test execution.
If durable fails/cancels, foundation is skipped through its dependency and the
whole gate fails; this does not certify generic or tail. No `if: always()` is added
to start core resources after a failed prerequisite. Other existing independent
jobs and the native reusable call retain their current scheduling. Future C0
acceptance may choose a different dependency only with an explicit gate contract.

Minimal routing proposal: `scripts/ci.sh` accepts only no arguments (existing full
behavior), `--normal-durable`, or `--foundation-core`; reject anything else before
init/resources. All three keep the existing init, config, api/checks/frontend
build prelude and cleanup. The first route still runs everything, in original
order. The durable route executes the **whole** existing durable invocation and
then cleanup. The core route executes checks and the **whole** remaining tail.
There is no environment-based optional gate, arbitrary selector, resumable case
offset or per-lifecycle split. Both CI jobs are mandatory together. Repeated
build/frontend checks in fresh jobs are an explicit cost; removing duplicate
coverage/builds is outside this proposal.

Each job uses its own disposable runner, compose projects, networks, credentials,
volumes, images and evidence. Never download a previous job's DB/image/private
state, adopt an existing project, share a lease, or export credentials through job
outputs. The current normal durable project name can remain fixed only because
the dedicated runner is fresh and the existing no-prior-resource refusal remains.
The core runner provisions a fresh asm_test/storage using existing init; it must
not assume the durable runner left an upgraded DB. Preserve per-lifecycle actual
LOCAL/TEST ownership and the complete Python finally/90s cleanup contract. Core's
existing compose EXIT cleanup remains, with original failure/cancellation and
owned cleanup results recorded separately. No global prune or broad volume delete.

Both jobs independently record actual HEAD/tree/raw parents, original event
digest, run/attempt/job identity, exact workflow/script hashes, locked image and
actual development/runtime image source inventories. Archives/status are made
from the same checkout that executed work. Core's new bind-mounted evidence must
stay outside `/app` and only under ignored reports on the host. A successful
record-source step is not a successful clean-source gate. The native entrypoints
continue to bind actual GITHUB_SHA/HEAD and raw ordered parents; a stale advisory
merge_commit_sha never selects a different source. No new reusable SHA override,
workflow_dispatch or branch trigger is proposed.

The aggregate possible serial foundation allocation becomes25+45 minutes; no
existing per-job cap is increased. This additional job allocation and required
check/dependency change require **explicit C0 acceptance**, including required
check names/branch-protection policy. This report neither changes nor claims to
have inspected/updated repository administration settings. Until accepted, the
current10-job contract remains exact. No old S/deadline crosses a job boundary:
whole normal durable moves intact, and state/P/native work stays intact in its
own existing job. No request is resumed with a new clock.

### Alternatives considered

| Alternative | Evidence-based assessment |
|---|---|
| Retain one job; add only live evidence | Necessary for diagnostics but leaves approximately16m45s durable ahead of the observed27m40s backend prefix and unknown tail; no fit proof |
| Reorder generic first in the same job | Changes which failures are visible; total work/cap and complete-gate obligation remain |
| Move only unit tests out | Observed215.35s is much smaller than the whole durable envelope; also needs another boundary and does not establish room for47/tail |
| Append normal durable to browser/state jobs | Browser observed646s plus durable1005s already exceeds1500s before added setup/cleanup; normal state observed1356s. These are different resources/clock contracts and have no demonstrated room |
| Reuse the Docker29 job for normal coverage | Normal and exact Docker29 daemon boundaries are distinct; adoption/replacing normal coverage is invalid; sequential both would exceed its25min envelope at observed costs |
| Increase45, drop duplicate scenarios, historical-only generic, cache/shard/parallelize or retry | Outside authorization; changes acceptance rather than establishing the complete existing gate |

## 6. Proposed write-set and transitive guards — future authorization only

| Exact path / function | Narrow proposed change and required guard |
|---|---|
| `.github/workflows/ci.yml` | Add required25min foundation-durable and explicit serial needs; call two closed ci.sh routes; private host reports, independent always clean/source/archive steps. Retain all existing expanded jobs/actions/events/permissions, native unconditional local reusable path and all caps. C0 must accept11-job/required-check policy |
| `scripts/ci.sh` top-level routing, `compose()`, `cleanup()` | Closed routes with unchanged no-argument behavior; retain init/build/full-tail order, pipe/exit/trap semantics and resource ownership; bind only private evidence directory into checks; static host phase records |
| `scripts/check_backend.sh`, proposed `run_phase()` shell helper | Static start/end/exit phase records around unchanged commands/arguments, including every upgrade, complete generic, downgrade/upgrade, contracts and both wheels; no move to0012, subset, fail-fast or successful exit after an earlier failure |
| `scripts/native_context_db_catalog.py::generic_integration`, nested ExactGeneric hooks, proposed bounded evidence/failure formatter helpers, `CI_INPUT_SHA256`, `require_ci_inputs` | Persist existing partition proof/inventories; bounded live phase/failure reporter and normal completion receipt; preserve actual ordered selection and returned pytest code. Update exact ci.yml/check_backend.sh hashes atomically; keep native workflow hash exact if unchanged. Update the comment binding nine ordinary jobs to the accepted ten ordinary+one native expansion |
| `tests/test_native_context_db_runner.py` | Preserve259 runner cases/130subtests and existing negative source/admission/real-Git fixtures. Extend `test_ci_actual_generic_execution_must_match_proven_inventory`, `test_ci_generic_selection_never_receives_reset_admin_or_subset_flags`, `test_ci_guard_reads_actual_inputs_and_refuses_absent_or_changed_gate`; add meaningful routing, per-phase persistence, hostile-redaction, sink failure and interruption tests, and exact11-job/dependency/hash assertions |

Current guarded inputs are:

| Input | Current SHA256, unchanged by this report |
|---|---|
| `.github/workflows/ci.yml` | `475e9c7dc32bed8d0b5ab12260b1ab698835f634eb8c4b089d7c53c0af6d130d` |
| `.github/workflows/native-context-db.yml` | `ff43d2470b56d26cf9c616cad5bc570e31634a19d97bdec4f28e73a205e049fd` |
| `scripts/check_backend.sh` | `bd836b9afaf76ffc5e612f33e3662eef4671665b4147f4ef39247b402bb262ee` |

Do not temporarily disable the guard or accept multiple historical workflow
hashes. A changed input without paired hashes fails native admission and generic
partition collection. Existing missing/mutated-input negative fixtures must
still actually mutate each guarded file and refuse before resources. The native
workflow and `event_identity`/`admit_event`/all four entrypoint diagnostics need
regression verification, not a new source-selection rule.

`infra/Dockerfile.backend` already copies the two workflow files and all scripts
into development, so **no Dockerfile edit is proposed**. A rebuild must contain
the new exact copied bytes; testing host files while the image carries old hashes
would reproduce the previous admission problem. Existing development-only Git
installation stays. Runtime/toolchain stages, images/pins/locks and Compose stay
unchanged. No new script needs a COPY rule. The proposed CLI bind mount therefore
does not require a compose.yaml edit.

Known callers: ci.yml invokes ci.sh; storage-images.yml invokes ci.sh **without
arguments** with verified local-image environment overrides and must keep the
complete combined gate; bootstrap.sh tells operators to run that same default;
Dockerfile development CMD still invokes check_backend.sh. Docker29 calls
test_telegram_egress.sh directly, while migration/state harnesses call its explicit
schema/migration routes. Those invocations and bodies stay exact. Historical
operator-source comparisons in `prepare_telegram_egress.py::migration_operator_source`
and migration tests bind frozen sources, not a license to rewrite historical
ci.sh or image manifests. Review current source-image inventory comparisons
transitively after script changes; do not relax them to accept stale images.
C0 owns later HANDOFF/register/contract acceptance updates, outside C6's current
one-file scope. C2's eventual test corrections must be separately accepted and
combined at one exact later candidate; this report absorbs none of them.

## 7. Clocks, validation gates, remaining execution and rollback

Retain native20min with payload1080s/reserved cleanup, foundation45min,
browser/state/compatibility25min, proposed durable25min, original S and retained
S+600, P S+720 with exactly120 fixed extension, remaining+480/supervisor S+1200,
owned cleanup90 and **every** existing command/fixture/3s/10s/60s/collection cap.
No reset, pause, elapsed-charge subtraction, deadline rounding/extension, resource
adoption or new retry. Native7source+105PG=112,336 phases,105 guarded resets,
catalog167/45/635, both full durable six-lifecycle lanes and complete state/browser
scenarios remain obligations. D1/D2/D3, A08/P01/P05/account/renewal/collector/A12/M4
boundaries do not change. IMPL-05 remains DEFERRED.

### Performed for this document

Separate checkout was created/fetched at the exact own branch/base; GitHub's
recursive tree292 entries was compared against local Git objects, working bytes
and executable modes. All292 existing leaves and original11 matched. The retained
foundation/Docker29 archives were compared byte/mode-for-byte to candidate292.
No tests were added or run for this diagnostic document, and no fresh collection
or fixture execution was needed.

The external read-only analyzer verifies ZIP sizes/digests, source/parent bindings,
both representations of755 statuses against the native802 inventory, censored47,
the ten job results and timing windows. Its successful final version SHA256 is
`6bb94a99365c31374aa10d7982015191d9939a39485ba73d7b71527191cc0ad9`;
output run3-analysis.json SHA256 is
`f79b03c660db814c5cddb3f3172e924661732a43a2f5db0c16250ab1b518aab5`.
Two preliminary parser executions exited1 before handling spaces/padding; these
were analyzer parsing failures, not source/product/pytest failures. Correcting
only that external parser produced exact inventory equality and exit0.

Commands below are actual local verification commands; `E` denotes the external
evidence directory, not a repository file:

```sh
E=/workspace/scratch/65ac7d472387/c6-native-context-foundation-diag-r1-evidence
git show -s --format='%H%n%T%n%P' HEAD
git ls-tree -rz HEAD
python "$E/analyze_run3.py"
python "$E/local_run.py" frozen-sync uv tool run --offline --from uv==0.10.0 uv sync --frozen --offline --dev --python /root/.local/share/uv/python/cpython-3.13-linux-x86_64-gnu/bin/python3.13
python "$E/local_run.py" base-source-pair "$E/python-env/bin/python" "$E/verify_published.py"
git diff --check
```

Final versions of these checks exited0. Pure pairing imports this checkout only,
verifies all58 installed distributions against uv.lock and confirms all four
roles/api-console-worker-scheduler profiles,167functions/45tables/635columns and
verifier body SHA256
`527fce5681d5345369cd88b555a302df6d305ef8566cf12a666198eb64a6f4ac`.
This is source expansion/validation, not installed PostgreSQL/deployment/drain
attestation. The canonical REVIEW receipt records the final report commit/tree,
sole parent, one-file diff, all293 final leaves/292 preserved, source pairing,
precise final commands/exits and evidence hashes after publication/readback.

### Later validation, NOT RUN and not authorized here

After C0 accepts a precise implementation write-set/job policy, validate routing
with shell syntax and controlled command/exit/signal fixtures, and run focused
new reporter tests under frozen Python3.13/uv.lock. Require full existing runner
tests, Ruff/format/compile and source/image-input guard negatives. Verify append
records before simulated interruption, setup/call/teardown failures, preserved
nonzero pytest status, no fabricated final phase, partial final line, unwritable
sink, hostile exception attributes/chains/SQL/DSN/payloads, symlink/UID/path refusal
and absence of leaked sentinels. No extra product run is authorized by listing
these commands.

Representative future source commands, with the approved future frozen env:

```sh
sh -n scripts/ci.sh scripts/check_backend.sh
python -m pytest -q tests/test_native_context_db_runner.py
python -m ruff check scripts/native_context_db_catalog.py tests/test_native_context_db_runner.py
python -m ruff format --check scripts/native_context_db_catalog.py tests/test_native_context_db_runner.py
python -m compileall -q scripts/native_context_db_catalog.py tests/test_native_context_db_runner.py
git diff --check
```

Later C0 must separately authorize bounded actual PostgreSQL diagnostic work if
C2's source mapping cannot recover the real88 exception causes. It must also
accept the combined exact candidate and separately authorize actual CI. Complete
generic802 on current0013 with every historical scenario retained, native112/
336/105 plus independent167/45/635, both complete durable lanes, both complete
state lanes, browser, full migration/contracts/wheel/service/HTTP tail, all clean
gates and owned cleanup must pass within unchanged caps. All required11 checks
must refer to the same actual merge/main source/event and artifact identities.
No failed prerequisite/skipped core, partial755 or archived partial journal closes
CI-07. Time-boundary repair alone never closes CI-06. A later run must measure
fresh setup, journal/fsync overhead, all47, generic finalization and entire tail;
current evidence cannot certify these unknown terms.

Rollback of this diagnostic commit only removes this report. A later implementation
rollback must revert the workflow routing, reporter/phase instrumentation, paired
CI hashes and corresponding guard tests **atomically**, with C0 restoring the
required-job/dependency policy. Retain all runtime/product/SQL/schema/profile
definitions and clocks. The no-argument combined entrypoint remains available,
but reverting the boundary restores the known45min risk and cannot claim a green
full gate. Do not roll back a used0013 database or remove failing tests as part of
CI rollback. C0 acceptance and separately bounded implementation/runtime scopes
are the next steps; this report creates no execution permission.
