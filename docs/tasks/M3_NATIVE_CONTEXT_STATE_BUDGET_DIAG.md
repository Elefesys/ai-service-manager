# C6: native-context state preparation budget diagnosis

Task **C6-M3.1-NATIVE-CONTEXT-STATE-BUDGET-DIAG-R1**, finding **C0-NC-CI-12/P2**.
Prepared 2026-10-21. **REVIEW / SOURCE + SAVED ACTUAL EVIDENCE ONLY; C6 HOLD after return.**
[C0 assignment6296936145](https://github.com/Elefesys/ai-service-manager/pull/34#issuecomment-6296936145)
and the exact current HANDOFF/register control scope and status. This report does
not change the register or close CI-12. No implementation, local pytest, runtime
simulation, PostgreSQL, Docker/service/container inspection or execution, Actions
run/retry, execution-ref movement, PR, merge, settings, provider or live work was
performed for this report. Local programs only read Git/source and saved evidence,
hash/parse bytes and write audit results outside the tracked checkout.

## 1. Finding and limits

**OBSERVED:** RUN6 Docker29 state exhausted the original cumulative **S+720
material-preparation deadline**. P consumed its handoff after **709.367695088s**,
with **10.632304912s** left. The last source-byte image probe was admitted with
only **0.14476916000012352s** and raised `TimeoutExpired`; P retained
`CONTROL_COMMAND_TIMEOUT`, and the current coordinator retained
`MATERIAL_SCHEMA_PHASE_FAILED` / exit1. No preparation-complete receipt exists.
The coordinator ended at **S+720.507575965**, well before S+1200 supervision;
the failed job lasted998s of its1500s cap. These are distinct clocks.

**OBSERVED:** The preceding charged work is reconstructible without double
counting. RUN6 Docker29 reached P **205.032585186s later** than RUN5 Docker29 and
**25.818519910s later** than RUN6 normal. The increase is spread over T, both
expected negatives and C/G/E. Only1.015382063s of the RUN5-to-RUN6 Docker29
increase is in the measured gaps between those reports. It cannot all be
attributed to the final image probe or an unmeasured200s coordinator gap.

**SOURCE + OBSERVED:** The relevant current coordinator, preparer, harness,
workflow and lockfile are byte-identical in RUN5, RUN6 and this task's base.
All frozen source archives also match their exact Git trees. Normal state
passed twice and RUN5 Docker29 passed with much more headroom. Neither a later
PASS nor the Docker29 label establishes a cause or repairs the RUN6 failure.

**OPEN RISK:** The saved reports do not measure all helper-internal commands or
host CPU/scheduling/storage/cache/network conditions. They establish cumulative
budget exhaustion, not a Docker29 defect, a uniquely slow probe, a minimum
sufficient cap, or a promise that another ordinary run will fit. The smallest
next scope proposed in section8 is a source/local-unit investigation of bounded
measurement coverage; no optimization or additional run is authorized here.

Labels: OBSERVED means persisted/API evidence; SOURCE means inspected immutable
code; DERIVED means arithmetic on named observations; HYPOTHESIS means an
unproven explanation. PASS below describes saved cases, never a new execution.

## 2. Authority, source and independently retrieved artifacts

The independent checkout/branch is
`c6/m3-1-native-context-state-budget-diag-r1`. Sole task base/parent is
`8874ffd307a07e93f841850bc0c899ec79786731`, tree
`85da5a1ce46626fd81578ea0eeabbe7ee7d5c14d`; that base's sole parent is the RUN6
candidate. The sole tracked addition is
`docs/tasks/M3_NATIVE_CONTEXT_STATE_BUDGET_DIAG.md`. The report commit/tree are
published in the associated PR34 REVIEW to avoid a self-referential file hash.

Read governing AGENTS, current HANDOFF/register, IMPL-001, applicable canonical
architecture, ADR-213–217 provenance/migration boundaries, MVP readiness gates,
Roadmap M3 and implementation-plan handoff/ownership rules. Applied the accepted
M3_CONTRACT source/schema/ownership duties, especially sections15.11–15.13,
16.7/16.9, and both accepted diagnostic reports. Historical status/job-count
wording in section15.11 is superseded by current HANDOFF; its clock/proof duties
remain. All11 repository originals and all11 attached local copies were checked
against the unchanged SOURCE_MANIFEST; none was reconstructed from a summary.
No C0 local directory was used or presumed accessible.

| Binding | RUN5 / attempt1 | RUN6 / attempt1 |
| --- | --- | --- |
| Run | 39435478971 | 39457359784 |
| Execution head | efc1c8af12dfe8b0c4098c2bf6b6d085e1b35f0b | faceef49dc719d1b3c2b7945116794f6737d7b32 |
| Actual tested merge | f747ca7570a39c4867e145263c4234b8e9504ee8 | 6e12ce98f0436c8c33b8b75c62b52ce911eb0068 |
| Actual merge/candidate tree | 27bf2b804d6e3cf32cb548fd61ac349209b2b0c1 | 341112cfd977f25441d9f617a2db8580a87dbc42 |
| Ordered parents of merge | e205e22051bc06295758b504d84699652b176c15; efc1c8af12dfe8b0c4098c2bf6b6d085e1b35f0b | e205e22051bc06295758b504d84699652b176c15; faceef49dc719d1b3c2b7945116794f6737d7b32 |
| Saved Docker29 state job | 118671230917 | 118747603162 |
| Saved normal state job | 118671230983 | 118747603489 |

GitHub run/job/artifact metadata and Git commit/tree resources were fetched
independently. RUN6 is terminal9SUCCESS/2FAILURE, RUN5 is10SUCCESS/1FAILURE;
the additional RUN6 failed job is the subject of this report. This audit
downloads only the four assigned state artifacts, not all10 archives or the
core/native evidence owned by the separate C0/C2 review. Run-wide functional
results beyond these four artifacts remain attributed to C0's disposition.
The post-run base changes only HANDOFF/register relative to the RUN6 tested
candidate (+481/-2); its other292 leaves/modes are exact. It is coordination,
not a second tested execution source.

| Lane | Artifact / bytes | ZIP SHA-256 |
| --- | --- | --- |
| RUN5 docker29 | 12273167228 / 20164221 | 1c8fe8b6eac3300b677949dc23f204ce0da86af9c8cfc461232fc10284769f79 |
| RUN5 normal | 12272818378 / 20163387 | 0f0396803baa3eb209781cac1f36abff56b9e382dc1951ce33b145ccdde3f8e2 |
| RUN6 normal | 12282461749 / 20180438 | 7599b8eac911f38b1c5b2f54d082e14da3056ea094da898d07bed5182741eb69 |
| RUN6 docker29 | 12281649128 / 20132359 | c4d339963a2fd44c24c187cbfacb0d3ad6f4409aa251196ddc3985d04a912205 |

All four API sizes/digests match the downloaded ZIP bytes. All161 extracted
files match their ZIP members;44 nested source archives (11 per artifact)
match exact Git blob content, leaf set and Git executable modes. Each current
source archive has294 leaves. Each `tested-commit.txt` equals the actual tested
merge and each `worktree-status.txt` is0bytes. Archive paths were checked before
extraction; no symlinks/path escapes were accepted. Source/tree/ordered-parent
bindings are checked independently of report labels. Metadata expiry is
2026-10-27 under existing7day retention; retention is not extended by this report.

The historical archive named `historical/source-P.tar.gz` means the earlier
predecessor below; root `source-P.tar.gz` means terminal MATERIAL P. They are
not interchangeable. Duplicate E/P exports were byte-checked, not counted as
additional executions.

| Executor / representative archive | Commit | Tree / leaves |
| --- | --- | --- |
| Earlier predecessor | 0b7e24ee425ebb429bf87dfe382cbd3fab883028 | 14a4033b849c736235653a5a85ec9e5112bfe727 / 225 |
| H | 754f1c883e5a94a7fc9e729af2605424f949ba33 | b4fdef89583f6bab1c9c96cadb1fbe0c1e5d641f / 229 |
| T | ea1ae98ce9e5e26d5d0d14f3e6d278ecb9efbbad | 11ad506a859db155973f965bcdd0cebc7bc0d5ed / 236 |
| C | c6a55b6b17d1c1ab286ce97dfa4bd27197141fe5 | d7f0dbd35a637877b57d721cbb6a39c6ef59eae4 / 244 |
| G | c502d5fd258aef15bb5549e1529df8d038a4fb9b | 9ed2c0cd679d1577b93998c5a429c90e4b810588 / 255 |
| E | 933ddd284ff5b77fb1aa88a4270ab0032bc499c9 | d0759acb9f83ec3f3e10d9c5d1325c937c343ee7 / 269 |
| MATERIAL P | e205e22051bc06295758b504d84699652b176c15 | 85206b9c66ac151f3847aa39f46fb75663a18b91 / 275 |

The seven-source chain also includes MATERIAL_BASE
`edda243773702e7be1cd969d3ede622b4dacb74e` /
`ef3f4f69c005307cfb34c2dd9db0e0d96dcdf63c`; it is a checked ancestry/source
checkpoint, not another executed/archive phase. Current0013 coordinator admission
does not relabel frozen P's0012 source or readiness. Each successful comparator's
20 pairings retains exact E/0011 and P/0012 acceptance and opposite-source refusal,
with unchanged rows/catalog. RUN6 Docker29 has0 pairings because this work was
not entered, not because20 assertions passed vacuously.

| Relevant current file, identical RUN5/RUN6/base | SHA-256 |
| --- | --- |
| scripts/test_telegram_egress_migration.sh | c5d8ce43422a2fd1d14445cf8fa0500e0768d69cda2a54542bc37dc3763db068 |
| scripts/prepare_telegram_egress.py | 2be5c937e4aa99b73eb7b532765fc4d16ab1d9f6b7563224c0c692b3e0b73266 |
| tests/test_telegram_egress_migration.py | 34b91631501c84b211916f4179506196764fc97693578725b2559b399e9b7517 |
| .github/workflows/ci.yml | cdb6e92b90c3070ea22812e0edd8df5767bbbea7a67c8304a54d2282ef23c691 |
| uv.lock | 46e4489acd7fb1f5a757b0193c49c8bf0367188f75e45fca4d352a60fae9cead |

| Frozen P file at e205e220… | SHA-256 |
| --- | --- |
| scripts/test_telegram_egress_migration.sh | 145a83009a1d3ccb40376aa37e72afcb8bd1c046fbacd19382e3a6f7f2e0e4be |
| scripts/prepare_telegram_egress.py | b1f9f89d2ccabc880bbdab20c7ff4131c7bcf28dd1988979e893acc3494a4b59 |
| tests/test_telegram_egress_migration.py | 3bd9504d22007fa94366754652993b5e187cc1d99a45cac5b0106af97ed886b7 |

All11 originals remain exact, including overview
`c5f3cfc741b0978b8eaabb6a8f3da7c9640b01327935327014d88b45b23d5440`.
Full accepted M3_CONTRACT SHA-256 is
`fe2eb4ef2469ccb14b7147017c3c81066cde1b8a6ad60acbf73922a15e3ace5f`;
foundation budget report `0d2e2cae15a70136215d0799883f40eee332355e295dcdb0a15e63cabb6291ec`;
generic PG report `a37c89fcc4c9521fed4ba7e521a72dcbef08ba07a4a3a025dea6a7cffee15d36`.
These existing reports and canonical documents are unchanged.

## 3. One S clock; preparation, execution, supervision and cleanup

SOURCE anchors below use the task-base current module unless marked frozen P.
`schema_envelope` at1942 sets the coordinator monotonic S; `run_control_coordinator`
at4265 retains it. The outer migration shell starts its own admission timer
before H and calls this coordinator only after H's result/source/volume checks.
H stays outside S and inside the state job. S values across different runners
are host-monotonic readings, not comparable wall-clock durations.

| Boundary | Exact semantics / retained source |
| --- | --- |
| Retained600 | Dretained=S+600; T whole shell and version1 C/G/E admission/preparation. T and C children use remaining600; G/E children use remaining600+480 supervision. |
| Material720 | Dmaterial=S+720, integer extension120. Only P admission/source/ancestry/archive/build/reuse/image-probe preparation; it is cumulative from S, not720 fresh seconds at P. |
| P supervisor1200 | Dmaterial+480=S+1200. Current run_frozen_material passes supervisor−now, retains exports and validates/removes the worktree within that bound. The extra480 does not enlarge preparation. |
| P runtime | After the strict prepared_at<Dmaterial receipt, preparing becomes false and the remaining schema/readiness/recovery/cutover/refusal commands use unchanged individual limits under the outer supervisor. Finishing after S+720 can be valid. |
| Owned cleanup90 | Per admitted owner, a single cleanup_started_at+90 is reused on reentry; no new cleanup clock. Child/parent cleanup intervals overlap and must not be added. |
| Late C negatives | Three original cleanup negatives follow successful P/export; their existing480 supervisor remains. The S+1200 P bound alone is not a whole-job fit guarantee. |
| State job25min | ci.yml connect5-migration timeout-minutes25 covers runner setup, Docker installation where applicable, H, the S sequence, late negatives, source capture and upload. No cap increase. |
| Other caps | Build480, controller-start120, migration-probe30, drain60, normal command40 and all other original limits stay exact. Durable25/foundation45/native20(payload1080)/browser25 remain outside this task. |

The unchanged sequence is H/predecessor → establish S → T positive → real
timeout negative → export negative → C → G → E → P → three late C cleanup
negatives. Every elapsed T/negative/C/G/E/runtime/report/cleanup/handoff cost
remains charged when P observes S. No cost is removed because it was an
expected failure or because H produced an image alias earlier.

Current `run_frozen_material` at4142 issues P only after successful E,
source/clean verification, report export and owned cleanup. It checks frozen
P's complete275-leaf tree, archives it, creates its checkout and copies the
exact E report before issuing the version2 handoff. `material_escalation_evidence`
at3982 verifies E phase/source/tree, original600 preparation, completed
refusal/timer proof, image binding and cleanup ownership. Frozen P's
`consume_material_budget` at5853 checks the closed schema, UID/owner, file
identity/content, exact S+600/S+720/120, issued−S charge, E report hash and
completion ordering, then unlinks the one-use request after validation.

OBSERVED in all four receipts: every inherited handoff field equals the parent
ledger; version1 C/G/E share S+600 and complete preparation before600; P uses
version2 with the same S. E report hash/owner equals the retained copy; its
report end ≤ observed completion ≤ P issue ≤ P observation. P/outer cleanup
ownership matches the handoff. This audit checks saved equalities and source
guards; it cannot re-observe a consumed private request's inode after the run.
No private nonce or request contents are copied into this report.

For RUN6 Docker29, E preparation finished at S+575.979734197 with24.020265803s
remaining600; E execution validly continued under its existing supervision.
Its report's total-seconds end is1010.891390490, observed E completion
1011.122793999, P issue1011.554107428 and P observation1011.782108985, all on
the same monotonic axis S=302.414413897. E completion after600 is not evidence
of a new600 allowance. P admission at709.367695088 leaves10.632304912 of720.

Frozen P `migration_budget` at1881 accepts *remaining* time and rejects nesting;
`command` at379–385 clamps the ordinary command limit to its remaining deadline.
Final preparation additionally checks the exact original absolute Dmaterial.
The context manager restores its local deadline after leaving the preparation
scope; this does not reset S or grant another preparation allowance.

## 4. Measured timing reconciliation

Seconds below are saved numeric values or their stated subtraction, rounded to
9 decimal places for reproducibility, not a claim of nanosecond measurement
accuracy. Comparison columns use independent runners; no four-run distribution
or guaranteed future bound can be inferred.

| Measurement (seconds unless noted) | RUN5 Docker29 | RUN5 normal | RUN6 normal | RUN6 Docker29 |
| --- | --- | --- | --- | --- |
| Job wall duration (API, whole seconds) | 1011.000000000 | 1402.000000000 | 1396.000000000 | 998.000000000 |
| State execution step (API, whole seconds) | 997.000000000 | 1394.000000000 | 1389.000000000 | 979.000000000 |
| Outer shell admission elapsed | 996.628723186 | 1392.952431615 | 1388.447161028 | 978.716038081 |
| H observation envelope, before S | 175.796689765 | 241.190491603 | 248.172068484 | 256.714447174 |
| S coordinator elapsed including final retention | 819.827167412 | 1150.424446428 | 1138.917544084 | 720.507575965 |
| P issue−S | 504.179428341 | 681.569907274 | 683.332413828 | 709.139693531 |
| P issue→observation | 0.155681561 | 0.223260734 | 0.216761350 | 0.228001557 |
| P observation−S | 504.335109902 | 681.793168008 | 683.549175178 | 709.367695088 |
| P admission remaining720 | 215.664890098 | 38.206831992 | 36.450824822 | 10.632304912 |
| P observation→preparation complete | 8.453133353 | 11.119808574 | 10.860946378 | NOT_RUN / incomplete |
| P preparation-complete remaining720 | 207.211756745 | 27.087023418 | 25.589878444 | NOT_RUN / incomplete |
| P full report interval | 291.144860268 | 442.761842679 | 429.185449020 | 10.860986117 |
| P export complete−S | 795.726077191 | 1124.814182744 | 1113.009805847 | NOT_RUN / incomplete |
| P export→coordinator end, late C/tail | 24.101090221 | 25.610263684 | 25.907738237 | NOT_RUN / incomplete |

The passing normal P reports run for442.761842679/429.185449020s including
their preparation. They complete preparation at S+692.912976582 and
S+694.410121556; later material runtime/export occurs after720 but before1200.
RUN5 Docker29 prepared at S+512.788243255 and exported at S+795.726077191.
RUN6 Docker29's10.860986117s P report is censored by failure and includes
failure retention/cleanup; it is not a completed P preparation or execution cost.

### Nonoverlapping accounting through P observation

T's measured shell interval includes its checkpoint collection. Each negative
interval is its report started_at→started_at+elapsed_seconds. C/G/E use the same
report formula. Intervening gaps include child launch/return, remaining parent
cleanup, report/export, source/archive checks and handoffs. The exact gap
boundaries are reproduced in section9. Their internal command split is unknown;
they are charged elapsed time, not discarded overhead or proven idle time.

| Disjoint interval | RUN5 Docker29 | RUN5 normal | RUN6 normal | RUN6 Docker29 |
| --- | --- | --- | --- | --- |
| T shell + checkpoint collection | 77.285501482 | 114.757109324 | 115.012910252 | 121.306649880 |
| Full T timeout negative | 145.203409293 | 153.507764697 | 154.363886350 | 155.635321560 |
| Full T export negative | 26.768472905 | 37.566799664 | 38.728872390 | 39.957397556 |
| C report | 79.537955149 | 114.524653643 | 116.067823507 | 121.278719755 |
| G report | 78.877223391 | 119.794061740 | 118.581811274 | 124.941592976 |
| E report | 93.815465382 | 138.036987412 | 137.081499755 | 142.385548998 |
| All intervening gaps, including S→T and E→P | 2.847082300 | 3.605791528 | 3.712371650 | 3.862464363 |
| SUM = P observed−S | 504.335109902 | 681.793168008 | 683.549175178 | 709.367695088 |

| Increase in charged interval | RUN6 Docker29 − RUN5 Docker29 | RUN6 Docker29 − RUN6 normal |
| --- | --- | --- |
| T shell and checkpoint collection | 44.021148398 | 6.293739628 |
| timeout negative | 10.431912267 | 1.271435210 |
| export negative | 13.188924651 | 1.228525166 |
| C report interval | 41.740764606 | 5.210896248 |
| G report interval | 46.064369585 | 6.359781702 |
| E report interval | 48.570083616 | 5.304049243 |
| all gaps | 1.015382063 | 0.150092713 |
| TOTAL | 205.032585186 | 25.818519910 |

C/G/E together account for136.375217807s of the205.032585186s same-lane
increase; T accounts for44.021148398s and the two negatives for23.620836918s.
The whole timeout negative is155.635321560s in RUN6 Docker29, not merely its
injected120s command wait: immutable T preparation, real execution, retained
state/export, cleanup and observations still cost time. The export negative
is39.957397556s. Its expected controller-seed exit7 and retained-copy checks
remain separate from the unexpected P timeout.

All gap costs together are only3.862464363s in RUN6 Docker29. Its breakdown is
0.346500176 S→T,0.259159495 T-end→timeout-negative,0.172725533 between
negatives,0.697316018 export-end→C,0.699158562 C→G,0.796887757 G→E, and
0.890716822 E-report-end→P observation. Individual cleanup measurements below
are nested inside these phase/gap intervals and are not added to this sum.

### What the existing command timings do and do not measure

All four lanes have82 C,83 G and87 E `stage_timings` rows. Their wrapped-command
sums increase broadly on RUN6 Docker29, rather than revealing one200s command.

| Phase | Direct run rows in each lane | RUN5 Docker29 wrapped seconds | RUN6 Docker29 wrapped seconds | RUN6 Docker29 full report seconds |
| --- | --- | --- | --- | --- |
| C | 82 | 73.677203538 | 112.860373062 | 121.278719755 |
| G | 83 | 72.778701064 | 115.943165109 | 124.941592976 |
| E | 87 | 87.536963550 | 133.196030980 | 142.385548998 |

For example, repeated `callers_c6a55b6b` rows aggregate9.937572→
18.349985s in C; `callers_c502d5fd`9.852304→18.323902s in G;
`callers_933ddd28`9.993196→18.250669s in E (rounded6 decimals). These are stage groups,
not unique commands or proof of Docker daemon time. Source and saved row order
must be used before assigning a stage label to an actual operation.

P's passing preparation prefix has18 directly wrapped calls; the failed prefix
has17, all labelled PASS. Their sums are4.882363616,6.671634230,6.490366772 and
7.025300279s in the column order above. The first source-observation call
precedes handoff consumption. These sums are not exhaustive preparation timing.
`e.migration_image`, source inventory and some archive/source helpers call
`e.command` directly; they do not go through P's local `run` wrapper. In
particular the failed P byte-probe has no FAILED `stage_timings` row.

SOURCE: frozen P6173 calls `e.migration_image`; helper2328–2363 performs exact
inventory/blob verification in a read-only, network-none, capability-dropped
Python container and then checks image identity. The loop also leaves the
previous `stage` value in place before the next `docker image ls` call. Thus
the0.184334926s row labelled `image_probe_933ddd28_runtime` in failed P measures
the subsequent wrapped lookup, not the unwrapped byte-probe duration. There is
no basis to call0.184s a successful probe comparator for the0.144769s failure.

The actual P build calls are separately identifiable by loop order: RUN6
Docker29 runtime1.641724815s and development2.562093727s, versus RUN5 Docker29
0.955465035/1.874245779s and RUN6 normal1.178875290/2.484003876s. Source archives,
same-invocation E image reuse and all byte checks remain mandatory. Build
durations do not measure registry/cache/network/CPU components separately.

H's recorded runtime/development builds were0.756241307/6.342499341s in RUN5
Docker29 and1.020728884/7.354362967s in RUN6 Docker29. Its complete observed
envelope grew175.796689765→256.714447174s, before S. That cost cannot be
subtracted from the709.367695088s S ledger: it was never in that ledger.
It is further evidence of broader timing variation, not its causal explanation.
H volume cleanup removed the exact four historical volumes in all four saved
lanes; initial volume and post-H container inventories were empty.

## 5. Exact failure chain and unentered work

RUN6 Docker29 artifact12281649128 `migration.log` has the following source-bound
locations. No raw argv, inline probe program, exception message payload, SQL,
environment, DSN, private path or owner token is reproduced here.

| Saved log line | Source / observation |
| --- | --- |
| 141 | Frozen P tests/test_telegram_egress_migration.py:6173, run_material_schema_phase |
| 144 | Frozen P scripts/prepare_telegram_egress.py:2341, migration_image |
| 146 | Frozen P scripts/prepare_telegram_egress.py:384, command; remaining-time clamp at379–385 |
| 159 | subprocess.TimeoutExpired; actual admitted timeout0.14476916000012352s |
| 169 | Current tests/test_telegram_egress_migration.py:4218, run_frozen_material |
| 172 | AssertionError: MATERIAL_SCHEMA_PHASE_FAILED |

| RUN6 Docker29 P/coordinator receipt | Value |
| --- | --- |
| Original S / retained / preparation / supervisor | 302.414413897 / 902.414413897 / 1022.414413897 / 1502.414413897 |
| P issue charge / admission charge | 709.139693531 / 709.367695088s |
| P admission remaining | 10.632304912s |
| Image preparation starts | S+709.795571937 |
| Last explicitly recorded preparation observation | S+719.673915673; not the final helper command-start timestamp |
| Stage at failure | image_probe_e205e220_development |
| P primary / wrapper primary | TimeoutExpired / CONTROL_COMMAND_TIMEOUT; AssertionError / MATERIAL_SCHEMA_PHASE_FAILED |
| Preparation stop charge | 720.225116696s; recorded after cleanup/retention path, not exact timeout instant |
| Budget at report | charged720.225124351s, remaining−0.225124641s; separate monotonic reads |
| Coordinator elapsed | 720.507575965s |
| Child / outer owned cleanup whole seconds | 0.160180745 / 0.500766830; overlapping, same admitted cleanup start |
| Job result / job duration | FAILURE / 998s of1500; not a job timeout |

The exception's timeout is an allowance passed to the original subprocess,
not the measured entire `migration_image` duration. The last recorded
preparation observation is earlier than that allowance calculation. No exact
final helper start/end or intrinsic probe latency is reconstructed by subtracting
that number from the deadline. Slightly negative report remaining time records
post-failure retention/cleanup; it is not a granted deadline extension.

P persisted three complete image proofs: E runtime, E development, P runtime.
Both P build commands and subsequent image inspections had returned before
the P development source-byte probe failed. P development's complete proof,
the later G development proof, preparation-complete receipt and runtime work
are absent. `checks=[]`, no database result, no pairings and diagnostic status
`NOT_REACHED` agree with the source control flow. `migration-P-observation.json`
is absent because its ordinary Alembic observation scope was never reached;
this is not evidence of a D2 recorder failure.

| Saved obligation | RUN6 Docker29 disposition |
| --- | --- |
| H + predecessor, T positive, C/G/E | PASS in their saved receipts; exact historical source identities retained |
| Full retained timeout/export negatives | Both expected negative tests PASS. Their inner errors are intentional; they remain charged. |
| Negative cleanup detail | OWNED_REMOVED with expected CONTROL_FOREIGN_RESOURCE_REMAINS; zero owned/unconfirmed leftovers, unchanged foreign identities, all recorded host children not live. The fixture removes its exact foreign resources afterward. |
| P schema/readiness,20 pairings, recovery/result-loss/cutover/refusal | NOT_RUN; no replacement by another lane or prior run |
| P child/outer cleanup | PASS; same owner/deadline, no owned/unconfirmed leftovers. Explicit private-state retention is diagnostic backing, not a claimed live container. |
| Three late retained-C cleanup negatives | NOT_RUN: run_frozen_material raises before their call |
| Explicit unchanged-source gate | SKIPPED by GitHub after the failed state step; not relabelled PASS |
| Always-run source capture/upload | SUCCESS. Empty saved status and exact294-leaf current archive independently checked. This is saved clean evidence despite the skipped explicit gate. |

C/G/E outer cleanup whole-seconds in failed RUN6 are0.948185645,
0.916772050,0.980118394; retained T1.028117761. They fit their individual90s
limits. These receipts include overlapping inner/outer cleanup intervals and
pre-clean inventory, so arrays named `containers` are not by themselves leftover
inventories. `owned_remaining` / `unconfirmed_creations` and cleanup state are
the final disposition fields. Negative-fixture OWNED_REMOVED is deliberately
distinct from an ordinary PASS cleanup.

## 6. What remains unproved

1. **HYPOTHESIS:** CPU scheduling/contention, runner allocation, filesystem/cache,
   container start/import/daemon costs, image cache or network/build variability
   could contribute to the broad timing change. None has a time-correlated
   measurement in these artifacts. Kernel/daemon/Compose version strings alone
   do not establish resource pressure or explain the difference.
2. **OBSERVED:** Docker29 client/server are29.8.2 and Compose5.5.1 in both runs;
   normal is28.0.4/Compose2.38.2 in both. Normal timing is much closer between
   RUN5/RUN6 than the two Docker29 samples. This is not a controlled Docker-version
   experiment: distinct jobs/runners are confounders, and source equality does
   not imply identical cache/network/host state.
3. **OPEN RISK:** No complete duration for the failed P preparation exists.
   Successful other-lane preparation costs8.453/11.120/10.861s are historical
   observations, not an admissible replacement cost or a safe new budget.
   The10.632s remainder was insufficient for this actual invocation, but the
   exact additional time it would have needed is censored.
4. **SOURCE + OBSERVED:** No lost preparation charge or duplicate ledger addition
   is demonstrated. Absolute end−S accounting closes exactly. This is not proof
   that every mandatory invocation is optimal. Any change to its work must first
   demonstrate equivalence and receive a separate scope, preserving frozen bytes.
5. **OPEN RISK:** Passing cleanup/source-capture evidence does not turn the
   failed state test, missing tail, full CI or native product acceptance green.
   This report does not independently revalidate the separate core/native jobs.

## 7. Safe evidence map and hashes

All evidence below is addressed by GitHub artifact ID + relative file path.
No dependency on a C0/C6 private local path is needed to reproduce the analysis.
The scratch audit root used here is
`/workspace/scratch/65ac7d472387/c6-native-context-state-budget-diag-r1-evidence`;
it is a local audit workspace, not a substitute for the identified GitHub archives.

| Artifact | Relative file | SHA-256 |
| --- | --- | --- |
| 12273167228 | control-schema-ledger.json | 5fce7ad2de1d5c06eff6033438fa5af73870322856c1ed17460d16bfdb2fdea8 |
| 12273167228 | material-schema-phase.json | 555ee0eabda8eaee94a4f964af9ddc9880f161ad40eb860bda29a66f31ef8333 |
| 12273167228 | migration.log | 303ce1bf4f44ce5509ca64af165f2dfe49918ca315ba9f0bd63309c296348db4 |
| 12273167228 | source.tar.gz | 04b0ef4a488302fefb13cd6bcffc6466cbfd55382b4145d38bfba144bfc2785d |
| 12272818378 | control-schema-ledger.json | 149d1c314d9bee612f19e572f0e93709fdb5d548f282413e80170ba2302cd242 |
| 12272818378 | material-schema-phase.json | 3ff0046eac9392353ec0215055731af51794022285d4c098503eeffa0eee97ab |
| 12272818378 | migration.log | 190ac436948125a7e387c5459e47c3b2b44ca60ad0bc884ab36528c00d557862 |
| 12272818378 | source.tar.gz | 04b0ef4a488302fefb13cd6bcffc6466cbfd55382b4145d38bfba144bfc2785d |
| 12282461749 | control-schema-ledger.json | a79bca17a403308c94606f6d4af64a0a15a90c758ae7258b21b63f6ca2165977 |
| 12282461749 | material-schema-phase.json | 478a8995f2e0a467611a71ced4731f28ae871f5f3c26141b530cf5e2b668b170 |
| 12282461749 | migration.log | dce550c6639121b32ebf9b7d8e4be1167447cb8d78463f2294c0c4fd139cca11 |
| 12282461749 | source.tar.gz | 061fdd3eee6a902ce3f0956e274196af1278392c9b68da87dbfc3a413607b1fc |
| 12281649128 | control-schema-ledger.json | e7a254259b2a2add5657891fc5bc41bffd0750705280b206e4efe9d584faaf0d |
| 12281649128 | material-schema-phase.json | c6afa8d1ba552ea1630b3c0ec0e81244b2b31908ce5446dbeda46cf19b158303 |
| 12281649128 | migration.log | 86125a11e98271abf0af3aa11d6eb0165ba9b7039e83038a5ade2d9637407e4a |
| 12281649128 | source.tar.gz | 061fdd3eee6a902ce3f0956e274196af1278392c9b68da87dbfc3a413607b1fc |

Common frozen MATERIAL `source-P.tar.gz` SHA-256:
`fc1b0fa73202fd2fedfc99afb90a767884e226aed09bc27592eb8f6af9c3c088`.
Common frozen E archive:
`e6639f8e696ba72d987154eac9f820f58883dc75a7e17ab713a00a937f970114`.
RUN6 Docker29 `historical/build-observation.json`:
`67e9f409de055336ae573638d1b9c2499d57fd5a427b6bfaf93747f65da83caf`.
Its retained E report, also checked in the P copy and handoff, is
`bae426fdcface68da0ff462b7afcc9c6be3b3fbd2b4c20bbdc73a1fe2fb39833`.

Job-step evidence comes from GET
`/repos/Elefesys/ai-service-manager/actions/runs/{run}/jobs?per_page=100`;
artifact IDs/sizes/digests come from the corresponding `/artifacts?per_page=100`.
The exact run IDs are in section2. Source proof uses GET Git commits and the
recursive base tree, plus the independently cloned Git objects. Raw migration
logs remain in their original archives; only the bounded failure identity and
source locations needed for this diagnosis are quoted.

## 8. Minimum proposed next investigation — NOT authorization

Return CI-12 OPEN to C0. The useful next question is which part of the unchanged
mandatory work varies, including the currently unmeasured helper calls. A retry
with the same aggregate receipts might pass, but would not answer that question.
No cap increase, S move/reset, charge subtraction, omitted negative/historical
proof, reused external daemon/project, weakened source guard, altered frozen
source/schema pairing or automatic retry is proposed.

**First, a source-only/local-unit scope for C0 to review:** restrict investigation
to the existing current `tests/test_telegram_egress_migration.py` diagnostic
scaffolding and constructed observer tests. Enumerate original callsites and
bounded loop counts for T/C/G/E/P, map saved row ordinals to actual operations,
and demonstrate a bounded observer prototype against constructed calls only.
Frozen T/C/G/E/P functions/files remain byte-identical; no repair to their body,
selector, assertions or clock is authorized by this proposal. An actual launch
integration write-set, if needed, must be returned explicitly to C0 before
editing another file. `scripts/prepare_telegram_egress.py`, workflows, source
guards and all budget values remain read-only in this proposed first step.

The prototype should establish whether the existing immutable-code observation
pattern can safely measure each *original* call, without replacing/wrapping its
command helper, modifying argv/stdin/cwd, replaying a command, writing inside a
frozen checkout or changing its result/exception. Reuse D1's separation of
observer and executor identity; existing D1/D2/D3 contracts remain intact.
Observational overhead is measured/charged, never subtracted or advertised as
free. No runtime feasibility claim follows from constructed unit checks.

Required finite, non-sensitive fields for that later design:

- Actual executor SHA/tree/blob/function and original invocation ordinal; a
  closed operation code distinguishing source/archive, existing-image lookup,
  reuse validation/tag, Docker build, byte probe, image inspect, caller/controller,
  cleanup/export. A stale stage label alone is insufficient.
- Original-S before/after times, phase preparation state, requested command cap
  and actual clamped remaining allowance at the subprocess boundary, original
  outcome/finite exception type, and completeness/overflow state. No raw args,
  image command programs, stdout/stderr, paths, SQL, payloads or secrets.
- Missing helper paths such as `migration_image` and source/archive verification
  need coverage. Coverage/count bounds must be derived from the actual bounded
  call graph; silently truncating mandatory records or treating missing rows as
  zero is unacceptable. Preserve original private-file/source/owner validation
  and primary-failure/cleanup discipline.
- Constructed checks must distinguish direct wrapped calls from helper-internal
  calls, final timeout from admission refusal, expected negatives from primary
  failure, and cleanup from preparation. They must prove original invocation
  count/arguments/result identity and exact accounting, including trace/export
  faults, without advancing deadlines or using the real Docker/PG paths.

**Measurement that would resolve the remaining ambiguity, only under a later
separate C0 execution approval:** numeric per-command allowance and elapsed time
for the original frozen preparation/probe calls, correlated with T/C/G/E costs
and exact runner/source identities. It distinguishes (a) ordinary probe cost
after depleted budget, (b) a local probe-specific delay, and (c) broad command
cost growth. Separating host CPU/I/O/cache/daemon/network causes would still need
appropriately scoped host observations; the present artifacts do not contain
them. Do not infer the cause from a lucky PASS or request a VM/provider change.

Only after those facts should C0 authorize a concrete bounded repair. A repair
must preserve every historical proof, exact current0013 admission, real command
and assertion identity, original caps and owned cleanup. This report supplies
no implementation authority and does not propose folding old state tests into
native/current tests or sharing their resource/clock boundaries.

## 9. Reproduction and actual verification

Actual local commands, from the independent checkout (all exited0 after the
parsers were checked against the source schema):

```sh
python ../c6-native-context-state-budget-diag-r1-evidence/audit_sources.py
python ../c6-native-context-state-budget-diag-r1-evidence/audit_timing.py
python ../c6-native-context-state-budget-diag-r1-evidence/audit_evidence.py
python ../c6-native-context-state-budget-diag-r1-evidence/reproduce.py ../c6-native-context-state-budget-diag-r1-evidence
git diff --check
```

Results:294 base leaves exact;11 canonical +11 local originals exact;
4 ZIP metadata/digests/sizes exact;161 extracted files exact;44 complete source
archive leaf/mode sets exact; all source/tree/parent bindings exact; handoff,
E report and cleanup identity/clock checks PASS; disjoint timing sums close;
actual timeout/wrapper locations verified; three saved comparators retain20
pairings each and failed RUN6 Docker29 retains0/NOT_RUN. This is parsing
verification, not pytest or a re-execution of any product/runtime gate.

The following standalone reproducer covers the source archives, handoffs,
timing decomposition, failure identity and cleanup distinction directly from
the four ZIPs. It imports no repository modules. Place the four independently
downloaded ZIPs as `artifact-{id}.zip` in a directory, and run it with Python
from an existing full clone containing the stated immutable Git objects:
`python /path/to/reproduce.py /path/to/zips`. The code is included here so no
other chat's local helper file is required. It only reads Git and ZIP members
and prints bounded facts.

```python
import hashlib
import io
import json
import math
import re
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

# Run from a full clone; argv[1] contains the four immutable artifact ZIPs.
inputs = [
    (12273167228, 20164221, '1c8fe8b6eac3300b677949dc23f204ce0da86af9c8cfc461232fc10284769f79'),
    (12272818378, 20163387, '0f0396803baa3eb209781cac1f36abff56b9e382dc1951ce33b145ccdde3f8e2'),
    (12282461749, 20180438, '7599b8eac911f38b1c5b2f54d082e14da3056ea094da898d07bed5182741eb69'),
    (12281649128, 20132359, 'c4d339963a2fd44c24c187cbfacb0d3ad6f4409aa251196ddc3985d04a912205'),
]
base = '8874ffd307a07e93f841850bc0c899ec79786731'
heads = ['efc1c8af12dfe8b0c4098c2bf6b6d085e1b35f0b',
         'faceef49dc719d1b3c2b7945116794f6737d7b32']
merges = ['f747ca7570a39c4867e145263c4234b8e9504ee8',
          '6e12ce98f0436c8c33b8b75c62b52ce911eb0068']
main = 'e205e22051bc06295758b504d84699652b176c15'
def git(*args):
    return subprocess.check_output(['git', *args])
def sha(raw):
    return hashlib.sha256(raw).hexdigest()
def near(a, b):
    assert math.isclose(a, b, rel_tol=0, abs_tol=1e-6)
def tree(ref):
    out = {}
    for row in git('ls-tree', '-rz', ref).split(b'\0'):
        if row:
            meta, path = row.split(b'\t')
            mode, kind, blob = meta.decode().split()
            assert kind == 'blob' and mode in ('100644', '100755')
            out[path.decode()] = (mode, blob)
    return out
assert git('rev-parse', base+'^{tree}').decode().strip() == '85da5a1ce46626fd81578ea0eeabbe7ee7d5c14d'
assert len(tree(base)) == 294
for head, merge in zip(heads, merges):
    assert git('rev-parse', head+'^{tree}') == git('rev-parse', merge+'^{tree}')
    assert git('rev-list', '--parents', '-n', '1', merge).decode().split()[1:] == [main, head]
for path in ('scripts/test_telegram_egress_migration.sh', 'scripts/prepare_telegram_egress.py',
             'tests/test_telegram_egress_migration.py', '.github/workflows/ci.yml', 'uv.lock'):
    assert git('show', heads[0]+':'+path) == git('show', heads[1]+':'+path) == git('show', base+':'+path)
manifest = json.loads(git('show', base+':docs/architecture/SOURCE_MANIFEST.json'))
assert len(manifest) == 11
for name, digest in manifest.items():
    assert sha(git('show', base+':docs/architecture/'+name)) == digest
for ordinal, (aid, size, digest) in enumerate(inputs):
    raw = (Path(sys.argv[1])/f'artifact-{aid}.zip').read_bytes()
    assert len(raw) == size and sha(raw) == digest
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        def read(name): return json.loads(z.read(name))
        l = read('control-schema-ledger.json')
        p = read('material-schema-phase.json')
        b, s = p['prepare_budget'], l['started_at']
        expected = merges[0 if ordinal < 2 else 1]
        assert l['candidate'] == z.read('tested-commit.txt').decode().strip() == expected
        assert z.read('worktree-status.txt') == b''
        bindings = l['ordered_sources'] + p['sources']
        refs = {x['sha'] for x in bindings}
        refs.add(read('historical/source-pairing.json')['predecessor'])
        for x in bindings:
            assert git('rev-parse', x['sha']+'^{tree}').decode().strip() == x['tree']
            assert git('rev-list', '--parents', '-n', '1', x['sha']).decode().split()[1:] == x['parents']
        trees = {ref: tree(ref) for ref in refs}
        archives = 0
        for name in z.namelist():
            assert not name.startswith('/') and '..' not in Path(name).parts
            if not name.endswith('.tar.gz'): continue
            observed = {}
            with tarfile.open(fileobj=io.BytesIO(z.read(name))) as tar:
                for member in tar:
                    assert not member.name.startswith('/') and '..' not in Path(member.name).parts
                    if member.isdir(): continue
                    assert member.isfile() and member.name not in observed
                    data = tar.extractfile(member).read()
                    oid = hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
                    observed[member.name] = ('100755' if member.mode & 0o111 else '100644', oid)
            matches = [ref for ref, leaves in trees.items() if leaves == observed]
            assert len(matches) == 1
            if name == 'source.tar.gz': assert matches == [expected]
            archives += 1
        assert archives == 11
        assert l['deadline'] == b['retained_deadline'] == s+600
        assert l['material_deadline'] == b['deadline'] == s+720
        assert l['material_supervisor_deadline'] == s+1200 and b['extension_seconds'] == 120
        assert b['started_at'] == s and all(b[k] == v for k, v in l['material_handoff'].items())
        near(b['issued_at']-s, b['charged_seconds'])
        near(b['observed_at']-s, b['charged_at_observation'])
        near(b['observed_at']-b['issued_at'], b['handoff_seconds'])
        phases = [read(f'retained-{n}/{n.split("-")[0]}-schema-phase.json')
                  for n in ('control', 'guards', 'escalation')]
        for r, h in zip(phases, ('handoff', 'guards_handoff', 'escalation_handoff')):
            assert all(r['prepare_budget'][k] == v for k, v in l[h].items())
            assert r['prepare_budget']['started_at'] == s and r['prepare_budget']['deadline'] == s+600
            assert r['prepare_budget']['charged_total_seconds'] < 600 and r['budget_state'] == 'VALIDATED_CONSUMED'
            assert not r.get('failure') and r['cleanup']['state'] == 'PASS'
        e = phases[-1]
        ec = b['escalation_completion']
        assert ec == l['escalation_completion']
        assert ec['report_sha256'] == sha(z.read('retained-escalation/escalation-schema-phase.json'))
        near(ec['report_ended_at'], e['started_at']+e['total_seconds'])
        assert ec['report_ended_at'] <= ec['completed_at'] <= b['issued_at'] <= b['observed_at'] < s+720
        assert ec['owner_token'] == e['cleanup']['token']
        assert b['owner_token'] == p['cleanup']['token'] == l['cleanup']['token']
        negatives = [read(f'control-full-retained-{n}.json') for n in ('timeout', 'export')]
        for r in negatives:
            assert r['result'] == 'PASS' and r['shell_exit'] == 1
            assert r['whole_prepare_started_at'] == s and r['deadline'] == s+600
            assert r['cleanup']['state'] == 'OWNED_REMOVED'
            assert r['cleanup']['diagnostic']['reason'] == 'CONTROL_FOREIGN_RESOURCE_REMAINS'
            assert r['foreign_before'] == r['foreign_after'] and all(not c['live'] for c in r['host_children'])
        for c in [p['cleanup'], l['cleanup']] + [r['cleanup'] for r in phases+negatives]:
            assert not c.get('owned_remaining') and not c.get('unconfirmed_creations')
            assert c['whole_cleanup_seconds'] < 90
        intervals = [('T', l['retained_shell_started_at'], l['retained_shell_seconds'])]
        intervals += [(n, r['started_at'], r['elapsed_seconds'])
                      for n, r in zip(('timeout','export','C','G','E'), negatives+phases)]
        cursor, gaps, measured = s, 0.0, {}
        for name, start, duration in intervals:
            assert start >= cursor
            gaps += start-cursor
            measured[name] = duration
            cursor = start+duration
        assert b['observed_at'] >= cursor
        gaps += b['observed_at']-cursor
        near(sum(measured.values())+gaps, b['charged_at_observation'])
        if aid == 12281649128:
            assert p['primary_failure']['reason'] == 'CONTROL_COMMAND_TIMEOUT'
            assert p['primary_failure']['type'] == 'TimeoutExpired'
            assert p['stage'] == 'image_probe_e205e220_development'
            assert l['primary_failure']['reason'] == 'MATERIAL_SCHEMA_PHASE_FAILED' and l['material_exit'] == 1
            assert 'preparation_ended_at' not in b and not p.get('pairings') and not p['checks']
            assert len(p['images']) == 3 and p['migration_diagnostics']['status'] == 'NOT_REACHED'
            assert 'retained_control_negatives' not in l
            lines = z.read('migration.log').decode().splitlines()
            assert float(re.search(r'timed out after ([0-9.]+) seconds', lines[158])[1]) == 0.14476916000012352
            assert 'line 6173, in run_material_schema_phase' in lines[140]
            assert 'line 4218, in run_frozen_material' in lines[168]
        else:
            assert l['material_exit'] == 0 and len(p['pairings']) == 20
            assert all(x['unchanged_rows_catalog'] for x in p['pairings'])
            assert b['preparation_ended_at'] < s+720 and l['material_export_completed_at'] < s+1200
            near(b['charged_total_seconds'], b['preparation_ended_at']-s)
            near(b['remaining_seconds'], b['deadline']-b['preparation_ended_at'])
            assert l['retained_control_negatives']['count'] == 3
        print(aid, 'verified', {k: round(v,9) for k,v in measured.items()},
              'gaps', round(gaps,9), 'P charge', round(b['charged_at_observation'],9),
              'P admission remaining', round(b['deadline']-b['observed_at'],9))
```

No new unit/integration tests were run: C0 explicitly limits this task to
SOURCE + SAVED EVIDENCE parsing. No dependency install was needed. The initial
external parser was corrected to respect the evidence schema: `containers`
is an inventory, not `owned_remaining`, and expected negative cleanup is
OWNED_REMOVED with unchanged foreign fixtures, not ordinary PASS. No input,
source, test or saved result was modified to make a parser pass.

The associated REVIEW records the final report hash, one-path diff, full
commit/tree/sole parent/branch, parser/proof hashes and protected-ref readback.
All pre-existing294 source leaves/modes, including existing accepted reports,
HANDOFF/register, remain unchanged by the report commit. No new PR is created;
the own report branch has no applicable push workflow.

CI-06/07/11/12 remain OPEN for C0; CI-10's actual recorder closure and prior
CI-08/09, D1/D2/D3 dispositions are retained. M3 remains IN_PROGRESS,
enforcement UNVERIFIED, IMPL-05 DEFERRED. User owns merge. **C6 HOLD.**
